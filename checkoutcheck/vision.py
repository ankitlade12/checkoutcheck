"""Trusted OpenCV 5 marker adapter for real, staged recordings.

This is a constrained instrumentation baseline, not a retail product recognizer.
Only inference inputs are passed to this module; it does not read annotations.
"""

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

from .evaluator import identifier, keys, milliseconds, require


def validate_inputs(inputs):
    keys(inputs, ("events", "catalog", "offset_ms", "bagging_x", "min_observations"))
    require(type(inputs["offset_ms"]) is int and abs(inputs["offset_ms"]) <= 60_000, "Invalid clock offset")
    require(type(inputs["bagging_x"]) in (int, float) and 0.1 <= inputs["bagging_x"] <= 0.9, "Bagging boundary must be 0.1–0.9")
    require(type(inputs["min_observations"]) is int and 1 <= inputs["min_observations"] <= 30, "Invalid tracking threshold")
    catalog = inputs["catalog"]
    require(isinstance(catalog, dict) and 1 <= len(catalog) <= 50, "Catalog must map 1–50 unique marker IDs to SKUs")
    for marker, sku in catalog.items():
        require(marker.isdigit() and str(int(marker)) == marker and 0 <= int(marker) < 50, "Marker ID must be 0–49")
        identifier(sku)
    require(isinstance(inputs["events"], list) and 1 <= len(inputs["events"]) <= 1000, "Invalid transaction events")
    seen, active, previous, paid = set(), {}, -1, False
    for event in inputs["events"]:
        keys(event, ("id", "type", "t_ms"), ("sku", "quantity", "scan_id"))
        identifier(event["id"])
        require(event["id"] not in seen, "Duplicate transaction event")
        seen.add(event["id"])
        milliseconds(event["t_ms"])
        require(event["t_ms"] >= previous and not paid, "Events must be ordered and end at payment")
        require(event["t_ms"] + inputs["offset_ms"] >= 0, "Clock offset maps an event before video start")
        previous = event["t_ms"]
        if event["type"] == "scan_add":
            require(event.get("sku") in catalog.values(), "Scan references an unknown SKU")
            require(type(event.get("quantity")) is int and 1 <= event["quantity"] <= 50, "Invalid scan quantity")
            active[event["id"]] = event
        elif event["type"] == "scan_void":
            identifier(event.get("scan_id"))
            require(event.get("scan_id") in active, "Void must reference a non-voided scan")
            del active[event["scan_id"]]
        elif event["type"] == "payment_complete":
            paid = True
        else:
            raise ValueError("Unsupported event type")
    require(paid, "A complete mock payment record is required")
    return Counter({sku: sum(e["quantity"] for e in active.values() if e["sku"] == sku) for sku in catalog.values()})


def probe(path):
    import cv2
    require(cv2.__version__.split('.')[0] == '5', "This worker requires OpenCV 5")
    cap = cv2.VideoCapture(str(path))
    try:
        require(cap.isOpened(), "Video is not decodable")
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        require(math.isfinite(fps) and 1 <= fps <= 60, "Supported frame rate is 1–60 fps")
        require(0 < frames <= fps * 60.1, "Video must be at most 60 seconds")
        require(16 <= width <= 1920 and 16 <= height <= 1080, "Maximum resolution is 1920 × 1080")
        ok, _ = cap.read()
        require(ok, "Video has no decodable first frame")
        return {"fps": fps, "frames": int(frames), "width": width, "height": height,
                "duration_ms": round(frames / fps * 1000), "opencv_version": cv2.__version__}
    finally:
        cap.release()


def analyze(path, inputs):
    import cv2
    started = time.monotonic()
    scanned = validate_inputs(inputs)
    metadata = probe(path)
    payment_ms = inputs["events"][-1]["t_ms"] + inputs["offset_ms"]
    require(payment_ms <= metadata["duration_ms"], "Payment is outside video; check synchronization offset")
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    cap = cv2.VideoCapture(str(path))
    tracks, evidence, warnings = {}, [], set()
    frame_no, last_ms, blur_sum = 0, -1, 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_no += 1
            require(frame_no <= 3606, "Frame limit exceeded")
            timestamp = round(cap.get(cv2.CAP_PROP_POS_MSEC))
            require(timestamp >= last_ms and (frame_no == 1 or timestamp > last_ms),
                    "Non-monotonic decoder timestamps; normalize and revalidate alignment")
            last_ms = timestamp
            if timestamp > payment_ms:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur_sum += float(cv2.Laplacian(gray, cv2.CV_64F).var())
            corners, ids, _ = detector.detectMarkers(gray)
            if ids is None:
                continue
            for polygon, marker_id in zip(corners, ids.flatten()):
                marker = str(int(marker_id))
                if marker not in inputs["catalog"]:
                    warnings.add("Unknown marker observed; catalog may be incomplete")
                    continue
                points = polygon[0]
                center_x = float(points[:, 0].mean()) / metadata["width"]
                track = tracks.setdefault(marker, {"observations": 0, "bag_observations": 0,
                    "last_ms": 0, "last_in_bag": False, "first_ms": timestamp})
                track["observations"] += 1
                track["last_ms"] = timestamp
                track["last_in_bag"] = center_x >= inputs["bagging_x"]
                if track["last_in_bag"]:
                    track["bag_observations"] += 1
                if frame_no % max(1, round(metadata["fps"] / 5)) == 0:
                    evidence.append({"t_ms": timestamp, "marker": marker, "sku": inputs["catalog"][marker],
                        "box": [float(points[:, 0].min()) / metadata["width"], float(points[:, 1].min()) / metadata["height"],
                                float(points[:, 0].max()) / metadata["width"], float(points[:, 1].max()) / metadata["height"]],
                        "in_bag": track["last_in_bag"]})
    finally:
        cap.release()
    require(last_ms >= payment_ms - 1000 / metadata["fps"] - 5, "Video ended before payment")
    if not tracks:
        warnings.add("No supported product markers detected")
    for track in tracks.values():
        if (payment_ms - track["last_ms"] > 500 or track["observations"] < inputs["min_observations"]
                or (track["last_in_bag"] and track["bag_observations"] < inputs["min_observations"])):
            warnings.add("Tracking evidence is incomplete at payment; human review required")
    observed = Counter(inputs["catalog"][marker] for marker, track in tracks.items()
                       if track["last_in_bag"] and track["bag_observations"] >= inputs["min_observations"])
    events = [{"id": f"mismatch-{index}", "sku": sku, "t_ms": payment_ms}
              for index, sku in enumerate(sorted(set(scanned) | set(observed))) if scanned[sku] != observed[sku]]
    decision = "abstain" if warnings else "discrepancy_alert" if events else "no_action"
    return {"decision": decision, "events": events if decision == "discrepancy_alert" else [],
            "evidence": evidence, "tracks": tracks, "observed_counts": dict(observed), "scan_counts": dict(scanned),
            "warnings": sorted(warnings), "metadata": metadata, "runtime_seconds": time.monotonic() - started,
            "mean_laplacian_variance": blur_sum / max(1, frame_no),
            "opencv_build_hash": hashlib.sha256(cv2.getBuildInformation().encode()).hexdigest(),
            "controller_trace": [{"observation": sorted(warnings) or "Supported marker tracks available",
                                  "action": "request_human_review" if warnings else "reconcile_transaction",
                                  "reason": "Incomplete evidence" if warnings else "Compare visible bag inventory to net scans"}]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--inputs")
    args = parser.parse_args()
    try:
        result = analyze(args.video, json.loads(Path(args.inputs).read_text())) if args.inputs else probe(args.video)
        print(json.dumps(result, allow_nan=False))
    except (ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1)
