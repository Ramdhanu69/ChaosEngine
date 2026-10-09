import random
import json
import time
from ..scoring import ItemResult, FailureLabel
from ..parsing import extract_json

def generate_logic_task(seed: int, family: str) -> tuple[str, dict]:
    rng = random.Random(seed)
    if family == "inventory":
        stock = rng.randint(10, 20)
        requests = [rng.randint(2, 5) for _ in range(5)]
        prompt = f"You manage inventory. Starting stock: {stock}.\nProcess these requests in order: {requests}.\nIf a request exceeds current stock, skip it. Return final stock and fulfilled requests as JSON: {{\"stock\": 0, \"fulfilled\": []}}"
        
        fulfilled = []
        for r in requests:
            if r <= stock:
                stock -= r
                fulfilled.append(r)
        return prompt, {"stock": stock, "fulfilled": fulfilled}
        
    elif family == "bank":
        bal_a = rng.randint(100, 200)
        bal_b = rng.randint(50, 100)
        txs = [(rng.choice(["A", "B"]), rng.choice(["A", "B"]), rng.randint(10, 100)) for _ in range(5)]
        prompt = f"Bank accounts: A={bal_a}, B={bal_b}.\nProcess transactions (from, to, amount): {txs}.\nReject if insufficient funds or if from == to. Return JSON: {{\"A\": 0, \"B\": 0, \"rejected\": 0}}"
        
        rejected = 0
        bals = {"A": bal_a, "B": bal_b}
        for frm, to, amt in txs:
            if frm == to or bals[frm] < amt:
                rejected += 1
            else:
                bals[frm] -= amt
                bals[to] += amt
        return prompt, {"A": bals["A"], "B": bals["B"], "rejected": rejected}
        
    else: # order
        orders = [rng.randint(1, 5) for _ in range(5)]
        prompt = f"Order queue: {orders}. Process them: pop first, if >3 put remainder back at end, else complete. How many total processing steps (pops) until queue is empty? Return JSON: {{\"steps\": 0}}"
        steps = 0
        q = list(orders)
        while q:
            steps += 1
            o = q.pop(0)
            if o > 3:
                q.append(o - 3)
        return prompt, {"steps": steps}

def flatten_dict(d: dict, parent_key: str = '') -> dict:
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key))
        elif isinstance(v, list):
            items[new_key] = str(v)
        else:
            items[new_key] = v
    return items

def run_logic_item(seed: int, item_id: str, family: str, client) -> ItemResult:
    prompt, gt = generate_logic_task(seed, family)
    
    start = time.perf_counter()
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        hint={"domain": "logic", "item_id": item_id},
        mock_hint={"mock_response": gt}
    )
    lat = time.perf_counter() - start
    
    if getattr(resp, "truncated", False):
        return ItemResult("logic", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "truncated at max_tokens", lat)

    try:
        parsed = extract_json(resp.text)
    except Exception:
        return ItemResult("logic", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "Parse error", lat)
        
    f_gt = flatten_dict(gt)
    f_pred = flatten_dict(parsed) if isinstance(parsed, dict) else {}
    
    total = len(f_gt)
    correct = sum(1 for k in f_gt if k in f_pred and f_gt[k] == f_pred[k])
    
    score = correct / total if total > 0 else 1.0
    passed = (score == 1.0)
    label = None if passed else "INCORRECT_STATE"
    
    return ItemResult("logic", item_id, score, passed, label, f"Match: {correct}/{total}", lat)

def run_domain_logic(client, seed: int, items_count: int) -> list[ItemResult]:
    families = ["inventory", "bank", "order"]
    results = []
    for i in range(items_count):
        fam = families[i % len(families)]
        results.append(run_logic_item(seed + i, f"L-{i}", fam, client))
    return results
