import io
import random
import json
import time
from PIL import Image, ImageDraw
from ..scoring import ItemResult, FailureLabel
from ..parsing import extract_json

def generate_vision_task(seed: int, cat: str) -> tuple[str, bytes, dict]:
    rng = random.Random(seed)
    img = Image.new('RGB', (200, 200), color='white')
    d = ImageDraw.Draw(img)
    
    if cat == "grid":
        cell = rng.randint(0, 3)
        row = cell // 2
        col = cell % 2
        d.line([(100, 0), (100, 200)], fill='black', width=2)
        d.line([(0, 100), (200, 100)], fill='black', width=2)
        
        # draw red circle
        x0, y0 = col * 100 + 20, row * 100 + 20
        x1, y1 = x0 + 60, y0 + 60
        d.ellipse([x0, y0, x1, y1], fill='red')
        
        prompt = "This is a 2x2 grid. Cells are 0: top-left, 1: top-right, 2: bottom-left, 3: bottom-right. Which cell contains the red circle? Return JSON: {\"cell\": 0}"
        gt = {"cell": cell}
        
    elif cat == "box":
        x = rng.randint(10, 100)
        y = rng.randint(10, 100)
        w = rng.randint(20, 50)
        h = rng.randint(20, 50)
        d.rectangle([x, y, x+w, y+h], fill='blue')
        prompt = "Return the bounding box of the blue rectangle as JSON: {\"x\": 0, \"y\": 0, \"w\": 10, \"h\": 10}"
        gt = {"x": x, "y": y, "w": w, "h": h}
        
    else: # diagram
        labels = ["A", "B", "C"]
        rng.shuffle(labels)
        # draw nodes
        d.rectangle([10, 10, 50, 50], outline='black')
        d.text((25, 25), labels[0], fill='black')
        d.rectangle([100, 100, 140, 140], outline='black')
        d.text((115, 115), labels[1], fill='black')
        
        prompt = "List all node labels in the diagram as JSON: {\"labels\": [\"A\", \"B\"]}"
        gt = {"labels": sorted(labels[:2])}

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return prompt, buf.getvalue(), gt

def box_iou(b1, b2):
    x_left = max(b1["x"], b2["x"])
    y_top = max(b1["y"], b2["y"])
    x_right = min(b1["x"] + b1["w"], b2["x"] + b2["w"])
    y_bottom = min(b1["y"] + b1["h"], b2["y"] + b2["h"])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    b1_area = b1["w"] * b1["h"]
    b2_area = b2["w"] * b2["h"]
    union_area = b1_area + b2_area - intersection_area

    return intersection_area / union_area if union_area > 0 else 0.0

def run_vision_item(seed: int, item_id: str, cat: str, client, skip_vision: bool = False) -> ItemResult | None:
    if skip_vision:
        return None
        
    prompt, img_bytes, gt = generate_vision_task(seed, cat)
    
    start = time.perf_counter()
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        images=[img_bytes],
        hint={"domain": "vision", "item_id": item_id},
        mock_hint={"mock_response": gt}
    )
    lat = time.perf_counter() - start
    
    if getattr(resp, "truncated", False):
        return ItemResult("vision", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "truncated at max_tokens", lat)

    try:
        parsed = extract_json(resp.text)
    except Exception:
        return ItemResult("vision", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "Parse error", lat)
        
    score = 0.0
    if isinstance(parsed, dict):
        if cat == "grid":
            if parsed.get("cell") == gt["cell"]:
                score = 1.0
        elif cat == "box":
            if all(k in parsed for k in ["x", "y", "w", "h"]):
                iou = box_iou(parsed, gt)
                if iou >= 0.5:
                    score = 1.0
        else:
            pred_labels = set(parsed.get("labels", []))
            gt_labels = set(gt["labels"])
            if pred_labels == gt_labels:
                score = 1.0
            
    passed = (score == 1.0)
    label = None if passed else "INCORRECT_VISION"
    
    return ItemResult("vision", item_id, score, passed, label, f"Score {score}", lat)

def run_domain_vision(client, seed: int, items_count: int, skip_vision: bool = False) -> list[ItemResult]:
    if skip_vision:
        return []
    cats = ["grid", "box", "diagram"]
    results = []
    for i in range(items_count):
        cat = cats[i % len(cats)]
        res = run_vision_item(seed + i, f"V-{i}", cat, client, skip_vision)
        if res:
            results.append(res)
    return results
