"""Localization, counting and optional SKU matching on original RPC photographs.

These fixed classical baselines include a training-reference SIFT matcher.
Reference boxes are used by the evaluator only, never passed to detect().
"""

import argparse
import hashlib
import json
import math
import re
import time
from pathlib import Path

from .evaluator import canonical, digest, require

MODELS = {
    "foreground-components-v1": {"name": "Foreground components", "separate_touching": False},
    "watershed-v1": {"name": "Distance watershed", "separate_touching": True},
    "sift-reference-v1": {"name": "Real-reference SIFT matcher", "requires_references": True},
    "fasterrcnn-coco-v1": {"name": "Faster R-CNN · COCO baseline", "requires_model": "fasterrcnn_mobilenet_v3_large_fpn-fb6a3cc7.pth"},
    "fasterrcnn-rpc-v1": {"name": "Faster R-CNN · real RPC fine-tune", "requires_model": "rpc-fasterrcnn-v1/manifest.json"},
    "vision-agent-v1": {"name": "Vision investigation agent", "requires_model": "rpc-fasterrcnn-v1/manifest.json"},
}
CONFIG = {"max_dimension": 960, "lab_distance": 24, "minimum_area_fraction": 0.0006,
          "maximum_area_fraction": 0.75, "morphology_kernel": 3, "peak_window": 31,
          "peak_relative_threshold": 0.25, "match_iou": 0.5}
VERSION = "rpc-perception-evaluator/1.0"


def load_manifest(directory):
    manifest = json.loads((Path(directory) / "manifest.json").read_text())
    require(manifest.get("schema_version") == "rpc-perception/1.0", "Unsupported perception manifest")
    require(manifest.get("dataset") == "RPC" and manifest.get("source_split") == "val2019", "Only the real RPC validation subset is supported")
    require(manifest.get("evidence_kind") == "real_photographs", "Only original real photographs are accepted")
    require(digest({k: v for k, v in manifest.items() if k != "hash"}) == manifest.get("hash"), "Dataset manifest hash mismatch")
    require(isinstance(manifest.get("images"), list) and 1 <= len(manifest["images"]) <= 90, "Invalid image count")
    ids = set()
    for entry in manifest["images"]:
        require(type(entry.get("id")) is int and entry["id"] not in ids, "Invalid or duplicated image identifier")
        ids.add(entry["id"])
        require(isinstance(entry.get("file_name"), str) and re.fullmatch(r"[A-Za-z0-9_-]+\.jpg", entry["file_name"]), "Unsafe image filename")
        require(entry.get("level") in ("easy", "medium", "hard"), "Unknown image difficulty")
        require(all(type(entry.get(k)) is int and 0 < entry[k] <= 4096 for k in ("width", "height")), "Unsupported image dimensions")
        require(isinstance(entry.get("annotations"), list) and len(entry["annotations"]) <= 100, "Too many reference annotations")
        for annotation in entry["annotations"]:
            validate_box(annotation.get("bbox"), entry["width"], entry["height"])
            require(annotation.get("iscrowd", 0) == 0, "Crowd regions require a separate scoring policy")
    return manifest


def validate_box(box, width, height):
    require(isinstance(box, list) and len(box) == 4, "Box must contain x, y, width, height")
    require(all(type(v) in (int, float) and math.isfinite(v) for v in box), "Box values must be finite numbers")
    x, y, w, h = box
    require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width + 1 and y + h <= height + 1,
            "Bounding box is outside the image")


def detect(image, model):
    import cv2
    import numpy as np
    require(model in MODELS, "Unknown perception adapter")
    require(model in ('foreground-components-v1','watershed-v1'), "This adapter requires a separate model instance")
    require(cv2.__version__.split('.')[0] == '5', "Perception worker requires OpenCV 5")
    require(image is not None and image.ndim == 3, "Image cannot be decoded")
    height, width = image.shape[:2]
    require(0 < height <= 4096 and 0 < width <= 4096, "Unsupported decoded dimensions")
    factor = min(1, CONFIG["max_dimension"] / max(width, height))
    resized = cv2.resize(image, (round(width * factor), round(height * factor)), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = np.concatenate((lab[0], lab[-1], lab[:, 0], lab[:, -1]), axis=0)
    background = np.median(border, axis=0)
    distance = np.linalg.norm(lab - background, axis=2)
    mask = np.uint8(distance >= CONFIG["lab_distance"]) * 255
    kernel = np.ones((CONFIG["morphology_kernel"], CONFIG["morphology_kernel"]), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if MODELS[model]["separate_touching"] and mask.any():
        distances = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        local_max = cv2.dilate(distances, np.ones((CONFIG["peak_window"], CONFIG["peak_window"]), np.uint8))
        peaks = np.uint8((distances >= local_max - 1e-6) & (distances >= distances.max() * CONFIG["peak_relative_threshold"]))
        _, seeds = cv2.connectedComponents(peaks)
        markers = seeds.astype(np.int32) + 1
        markers[(mask != 0) & (seeds == 0)] = 0
        labels = cv2.watershed(resized, markers)
        region_ids = [int(i) for i in np.unique(labels) if i > 1]
    else:
        region_ids = list(range(1, labels_count))
    area = resized.shape[0] * resized.shape[1]
    boxes = []
    for region in region_ids:
        if not MODELS[model]["separate_touching"]:
            x, y, w, h, pixels = (int(v) for v in stats[region])
        else:
            ys, xs = np.where(labels == region)
            pixels = len(xs)
            if not pixels:
                continue
            x, y = int(xs.min()), int(ys.min())
            w, h = int(xs.max()) - x + 1, int(ys.max()) - y + 1
        if CONFIG["minimum_area_fraction"] * area <= pixels <= CONFIG["maximum_area_fraction"] * area:
            sx, sy = width / resized.shape[1], height / resized.shape[0]
            boxes.append([round(x*sx, 3), round(y*sy, 3), round(w*sx, 3), round(h*sy, 3)])
    warnings = []
    if float(np.median(np.linalg.norm(border - background, axis=1))) > 12:
        warnings.append("Nonuniform border: background estimation may be unreliable")
    if not boxes:
        warnings.append("No components detected; this is not evidence that the image is empty")
    if len(boxes) > 100:
        raise ValueError("Adapter produced too many regions; image is outside supported conditions")
    return {"boxes": sorted(boxes), "warnings": warnings,
            "foreground_fraction": float(np.mean(mask > 0)), "opencv_version": cv2.__version__}


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    overlap = max(0, min(ax+aw, bx+bw) - max(ax, bx)) * max(0, min(ay+ah, by+bh) - max(ay, by))
    return overlap / (aw*ah + bw*bh - overlap)


def match_boxes(predictions, references, threshold, predicted_categories=None, reference_categories=None):
    edges = [[j for j, ref in enumerate(references) if iou(box, ref) >= threshold
              and (predicted_categories is None or predicted_categories[i] == reference_categories[j])]
             for i, box in enumerate(predictions)]
    matched = {}

    def assign(index, seen):
        for j in edges[index]:
            if j not in seen:
                seen.add(j)
                if j not in matched or assign(matched[j], seen):
                    matched[j] = index
                    return True
        return False

    for index in range(len(predictions)):
        assign(index, set())
    return [{"prediction_index": i, "reference_index": j, "iou": iou(predictions[i], references[j])}
            for j, i in sorted(matched.items())]


def score_predictions(manifest, predictions, threshold=0.5):
    require(type(threshold) in (float, int) and 0 < threshold <= 1, "Invalid IoU threshold")
    known = {entry["id"]: entry for entry in manifest["images"]}
    by_id = {}
    for prediction in predictions:
        require(prediction.get("image_id") in known and prediction["image_id"] not in by_id, "Unknown or duplicated image prediction")
        entry = known[prediction["image_id"]]
        boxes = prediction.get("boxes")
        require(isinstance(boxes, list) and len(boxes) <= 100, "Invalid predicted boxes")
        for box in boxes:
            validate_box(box, entry["width"], entry["height"])
        if "category_ids" in prediction:
            require(isinstance(prediction["category_ids"],list) and len(prediction["category_ids"])==len(boxes),"Category count must match predicted boxes")
            catalog={c["id"] for c in manifest["categories"]}
            require(all(type(c) is int and c in catalog for c in prediction["category_ids"]),"Unknown predicted category")
        by_id[prediction["image_id"]] = prediction
    rows = []
    for entry in manifest["images"]:
        row = {"image_id": entry["id"], "file_name": entry["file_name"], "level": entry["level"],
               "reference_count": len(entry["annotations"])}
        prediction = by_id.get(entry["id"])
        if prediction is None:
            row.update(status="excluded", reason="missing_prediction")
        else:
            references = [a["bbox"] for a in entry["annotations"]]
            matches = match_boxes(prediction["boxes"], references, threshold)
            row.update(status="scored", predicted_count=len(prediction["boxes"]), matches=matches,
                       true_positive=len(matches), false_positive=len(prediction["boxes"])-len(matches),
                       false_negative=len(references)-len(matches), count_error=len(prediction["boxes"])-len(references))
            if "category_ids" in prediction:
                row["sku_matches"]=match_boxes(prediction["boxes"],references,threshold,prediction["category_ids"],
                                              [a["category_id"] for a in entry["annotations"]])
        rows.append(row)

    def summarize(selected):
        valid = [r for r in selected if r["status"] == "scored"]
        tp = sum(r["true_positive"] for r in valid)
        fp = sum(r["false_positive"] for r in valid)
        fn = sum(r["false_negative"] for r in valid)
        classified=[r for r in valid if "sku_matches" in r]
        sku_tp=sum(len(r["sku_matches"]) for r in classified)
        sku_pred=sum(r["predicted_count"] for r in classified)
        sku_ref=sum(r["reference_count"] for r in classified)
        return {"submitted_images": len(selected), "scored_images": len(valid), "excluded_images": len(selected)-len(valid),
                "true_positive": tp, "false_positive": fp, "false_negative": fn,
                "precision": tp/(tp+fp) if tp+fp else None, "recall": tp/(tp+fn) if tp+fn else None,
                "count_mae": sum(abs(r["count_error"]) for r in valid)/len(valid) if valid else None,
                "exact_count_images": sum(r["count_error"] == 0 for r in valid),
                "reference_objects": tp+fn, "predicted_objects": tp+fp,
                "sku_true_positive":sku_tp if classified else None,
                "sku_precision":sku_tp/sku_pred if sku_pred else None,"sku_recall":sku_tp/sku_ref if sku_ref else None}
    return {"evaluator_version": VERSION, "task": "image_product_localization_and_counting",
            "iou_threshold": threshold, "dataset_hash": manifest["hash"], "metrics": summarize(rows),
            "by_difficulty": {level: summarize([r for r in rows if r["level"] == level]) for level in ("easy", "medium", "hard")},
            "cases": rows}


def run_benchmark(directory, model):
    import cv2
    import numpy as np
    require(model in MODELS, "Unknown perception model")
    root = Path(directory)
    manifest = load_manifest(root)
    predictions, failures = [], []
    started = time.monotonic()
    matcher=None
    learned=None
    adapter_config=CONFIG
    if model=='vision-agent-v1':
        from .agent import VisionAgent
        learned=VisionAgent(root.parent)
        adapter_config=learned.provenance
    elif model=="sift-reference-v1":
        from .reference_matcher import ReferenceMatcher, CONFIG as REFERENCE_CONFIG
        matcher=ReferenceMatcher(root/"references")
        adapter_config={**REFERENCE_CONFIG,"match_iou":CONFIG["match_iou"],"reference_manifest_hash":matcher.bank["manifest_hash"]}
    elif model.startswith('fasterrcnn-'):
        from .learned_detector import LearnedDetector
        learned=LearnedDetector(root.parent,fine_tuned=model=='fasterrcnn-rpc-v1')
        adapter_config={**learned.provenance,'match_iou':CONFIG['match_iou']}
    for entry in manifest["images"]:
        try:
            raw = (root / "images" / entry["file_name"]).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "Image checksum mismatch")
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            require(image is not None and image.shape[:2] == (entry["height"], entry["width"]), "Image dimensions differ from source annotations")
            before = time.monotonic()
            detected = learned.detect(image) if learned else matcher.detect(image) if matcher else detect(image, model)
            predictions.append({"image_id": entry["id"], **detected, "runtime_seconds": time.monotonic()-before})
        except (OSError, ValueError, cv2.error) as error:
            failures.append({"image_id": entry["id"], "reason": str(error)})
    report = score_predictions(manifest, predictions, CONFIG["match_iou"])
    result = {"kind": "rpc_perception", "status": "partial" if failures else "completed", "manifest": manifest,
            "adapter": {"id": model, "name": MODELS[model]["name"], "config": adapter_config,
                        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "reference_matcher_code_sha256":hashlib.sha256(Path(__file__).with_name("reference_matcher.py").read_bytes()).hexdigest() if matcher else None,
                        "capability": "Photo-trained neural localization; no SKU or payment inference" if learned else "SKU matching against real training exemplars; no neural weights" if matcher else "Classical class-agnostic localization; no SKU recognition or learned weights"},
            "predictions": predictions, "failures": failures, "report": report,
            "execution": {"location": "local", "opencv_version": cv2.__version__,
                          "opencv_build_sha256": hashlib.sha256(cv2.getBuildInformation().encode()).hexdigest(),
                          "runtime_seconds": time.monotonic()-started},
            "limitations": manifest["limitations"] + [
                    "Small real-photo training sample; uncalibrated scores and domain shift. No SKU recognition." if learned else
                    "Only two training exemplars per product; orientation, occlusion and packaging changes can defeat matching." if matcher else
                    "Fixed untuned classical baseline; touching objects may merge, single objects may split, white products may disappear.",
                    "Image predictions do not establish scan status, payment, or unnecessary intervention."]}
    if model=='vision-agent-v1':
        from .agent import summarize
        result['agent_evaluation']=summarize(predictions)
        result['adapter']['capability']='Bounded deterministic perception-decision-action workflow; no transaction enforcement'
    return result


def verify_result(result):
    manifest = result["manifest"]
    require(digest({k: v for k, v in manifest.items() if k != "hash"}) == manifest["hash"], "Manifest integrity check failed")
    actual = score_predictions(manifest, result["predictions"], result["report"]["iou_threshold"])
    require(canonical(actual) == canonical(result["report"]), "Scoring does not reproduce")
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="private-data/rpc")
    parser.add_argument("--model", choices=MODELS, default="foreground-components-v1")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        verify_result(json.loads(Path(args.verify_report).read_text()))
        print("Verified: perception scores reproduce exactly. Inference is not rerun by this command.")
    else:
        result = run_benchmark(args.directory, args.model)
        serialized = json.dumps(result, allow_nan=False, indent=2)
        if args.output:
            Path(args.output).write_text(serialized + "\n")
            print(json.dumps(result["report"]["metrics"]))
        else:
            print(serialized)
