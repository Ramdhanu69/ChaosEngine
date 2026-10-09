import random
import json
import time
from ..scoring import ItemResult, FailureLabel
from ..parsing import extract_json

def generate_messy_log(seed: int) -> tuple[str, dict]:
    rng = random.Random(seed)
    
    gt = {
        "incident": {
            "id": f"INC-{rng.randint(1000,9999)}",
            "severity": rng.choice(["low", "medium", "high"]),
            "service": f"service-{rng.choice(['auth', 'api', 'db'])}",
            "timestamps": {
                "start": "2026-01-01T12:00:00Z",
                "end": "2026-01-01T12:05:00Z"
            }
        },
        "user": {
            "id": f"USR-{rng.randint(10,99)}",
            "ip": f"192.168.1.{rng.randint(1,254)}"
        },
        "metrics": {
            "latency_ms": rng.randint(50, 500),
            "error_rate": round(rng.random() * 0.1, 3)
        }
    }
    
    logs = [
        f"[INFO] 2026-01-01T11:59:00Z Starting normal operations...",
        f"ERROR: {gt['incident']['timestamps']['start']} | Incident {gt['incident']['id']} | Sev: {gt['incident']['severity']} | Svc: {gt['incident']['service']}",
        f"Metrics dump -> latency={gt['metrics']['latency_ms']}ms, errors={gt['metrics']['error_rate']}",
        f"User ctx: ip {gt['user']['ip']} user_id={gt['user']['id']}",
        f"Resolved at {gt['incident']['timestamps']['end']}"
    ]
    rng.shuffle(logs)
    
    return "\n".join(logs), gt

def flatten(d, parent_key=''):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten(v, new_key))
        else:
            items[new_key] = v
    return items

def run_data_item(seed: int, item_id: str, client) -> ItemResult:
    log_text, gt = generate_messy_log(seed)
    prompt = f"Extract structured data from these logs. Respond ONLY with a valid JSON object matching exactly this structure:\n{json.dumps(gt, indent=2)}\n\nLogs:\n{log_text}"
    
    start = time.perf_counter()
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        hint={"domain": "data", "item_id": item_id},
        mock_hint={"mock_response": gt}
    )
    lat = time.perf_counter() - start
    
    if getattr(resp, "truncated", False):
        return ItemResult("data", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "truncated at max_tokens", lat)

    try:
        parsed = extract_json(resp.text)
    except Exception:
        return ItemResult("data", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "Parse error", lat)
        
    flat_gt = flatten(gt)
    flat_pred = flatten(parsed) if isinstance(parsed, dict) else {}
    
    tp = 0
    fp = 0
    fn = 0
    
    for k, v in flat_pred.items():
        if k in flat_gt and type(flat_gt[k]) == type(v) and flat_gt[k] == v:
            tp += 1
        else:
            fp += 1
            
    for k in flat_gt:
        if k not in flat_pred or type(flat_gt[k]) != type(flat_pred.get(k)) or flat_gt[k] != flat_pred.get(k):
            fn += 1
            
    prec = tp / (tp + fp) if tp + fp > 0 else 0.0
    rec = tp / (tp + fn) if tp + fn > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0.0
    
    passed = (f1 == 1.0)
    label = None if passed else "INCORRECT_EXTRACTION"
    
    return ItemResult("data", item_id, f1, passed, label, f"F1: {f1}", lat)

def run_domain_data(client, seed: int, items_count: int) -> list[ItemResult]:
    results = []
    for i in range(items_count):
        results.append(run_data_item(seed + i, f"D-{i}", client))
    return results
