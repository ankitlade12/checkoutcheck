"""Acquire an explicit real-only RPC validation subset from the author's Kaggle release."""

import argparse
import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .evaluator import canonical, digest, require

SOURCE = "https://www.kaggle.com/datasets/diyer22/retail-product-checkout-dataset"
DOWNLOAD = "https://www.kaggle.com/api/v1/datasets/download/diyer22/retail-product-checkout-dataset/"
SEED = "checkoutcheck-rpc-v1"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def unpack_download(data, expected, limit):
    if data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = [entry for entry in archive.infolist() if not entry.is_dir()]
            require(len(files) == 1 and Path(files[0].filename).name == expected, "Unexpected dataset download archive")
            require(files[0].file_size <= limit, "Expanded download exceeds limit")
            data = archive.read(files[0])
    require(len(data) <= limit, "Download exceeds size limit")
    return data


def fetch(file_name, destination, limit):
    url = DOWNLOAD + urllib.parse.quote(file_name, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": "CheckoutCheck/0.1 research dataset acquisition"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    require(len(data) <= limit, "Download exceeds size limit")
    data = unpack_download(data, Path(file_name).name, limit)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(destination)
    return data


def select_images(images, count, seed=SEED):
    require(type(count) is int and 3 <= count <= 90 and count % 3 == 0, "Count must be a multiple of 3 between 3 and 90")
    groups = defaultdict(list)
    for image in images:
        require(type(image.get("id")) is int, "Invalid source image ID")
        require(isinstance(image.get("file_name"), str) and re.fullmatch(r"[A-Za-z0-9_-]+\.jpg", image["file_name"]), "Unsafe image filename")
        groups[image.get("level")].append(image)
    selected = []
    for level in ("easy", "medium", "hard"):
        require(len(groups[level]) >= count // 3, f"Not enough {level} images")
        ranked = sorted(groups[level], key=lambda image: sha256(f"{seed}:{image['file_name']}".encode()))
        selected.extend(ranked[:count // 3])
    require(len({i["id"] for i in selected}) == count, "Duplicate source image IDs")
    return selected


def acquire(root, count=24):
    root = Path(root)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        require(existing["selection"]["count"] == count, "Existing immutable subset has another count; choose a new directory")
        for item in existing["images"]:
            require(sha256((root / "images" / item["file_name"]).read_bytes()) == item["sha256"], "Existing source checksum mismatch")
        print(f"Verified existing {count}-image RPC subset", flush=True)
        return existing
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(exist_ok=True)
    source_file = root / "source" / "instances_val2019.json"
    # Always fetch the exact author bytes on first acquisition, not a reserialized annotation file.
    raw = fetch("instances_val2019.json", source_file, 25_000_000)
    coco = json.loads(raw)
    selected = select_images(coco["images"], count)
    annotations = defaultdict(list)
    for item in coco["annotations"]:
        annotations[item["image_id"]].append(item)
    entries = []
    for index, image in enumerate(selected):
        name = image["file_name"]
        remote = "retail_product_checkout/val2019/" + name
        path = root / "images" / name
        data = fetch(remote, path, 8_000_000)
        require(data.startswith(b"\xff\xd8"), "Source is not a JPEG; refusing to register")
        boxes = []
        for annotation in annotations[image["id"]]:
            boxes.append({"id": annotation["id"], "category_id": annotation["category_id"],
                          "bbox": annotation["bbox"], "iscrowd": annotation.get("iscrowd", 0)})
        entries.append({**image, "sha256": sha256(data), "bytes": len(data), "source_file": remote, "annotations": boxes})
        print(f"Downloaded {index+1}/{count}: {name} ({image['level']})", flush=True)
    manifest = {
        "schema_version": "rpc-perception/1.0", "dataset": "RPC", "source": SOURCE,
        "publisher": "Xiu-Shen Wei et al., RPC dataset authors", "publisher_page": "https://rpc-dataset.github.io/",
        "license": "CC-BY-NC-SA-4.0", "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "usage": "Local noncommercial research; not cleared for a commercial deployment",
        "source_split": "val2019", "purpose": "exploratory_perception_evaluation", "evidence_kind": "real_photographs",
        "selection": {"method": "sha256(seed:filename), equal count per official difficulty", "seed": SEED, "count": count},
        "annotation_sha256": sha256(raw), "categories": coco["categories"], "images": entries,
        "limitations": ["Not a transaction benchmark: no POS or payment ground truth.",
                        "Small exploratory validation subset; not an independent held-out result or full RPC leaderboard evaluation.",
                        "Images may be correlated; no independence assumption or population accuracy claim."],
    }
    manifest["hash"] = digest(manifest)
    # Acquisition time is separate so the immutable manifest can be recreated exactly.
    receipt = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "manifest_hash": manifest["hash"],
               "files": len(entries), "image_bytes": sum(i["bytes"] for i in entries)}
    (root / "acquisition.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (root / "NOTICE.txt").write_text(
        "RPC: A Large-Scale and Fine-Grained Retail Product Checkout Dataset.\n"
        "Xiu-Shen Wei, Quan Cui, Lei Yang, Peng Wang, Lingqiao Liu, Jian Yang.\n"
        "Source: https://rpc-dataset.github.io/\nLicense: CC BY-NC-SA 4.0\n"
        "https://creativecommons.org/licenses/by-nc-sa/4.0/\n"
        "Original photographs and annotations; no generated images or invented POS records.\n"
        "Keep this dataset outside the source repository. Public/commercial use requires a separate rights review.\n")
    temporary = root / "manifest.json.part"
    temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    temporary.replace(manifest_path)
    print(f"Registered {count} original photographs; manifest {manifest['hash']}", flush=True)
    return manifest


def acquire_references(root, per_category=2):
    """Select originals from training only, independently of validation labels/results."""
    root = Path(root)
    require(type(per_category) is int and 1 <= per_category <= 3, "Use 1–3 real references per category")
    bank = root / "references"
    (bank / "images").mkdir(parents=True, exist_ok=True)
    manifest_path = bank / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        require(existing["selection"]["per_category"] == per_category, "Reference selection is immutable; use a new directory")
        for entry in existing["images"]:
            require(sha256((bank / "images" / entry["file_name"]).read_bytes()) == entry["sha256"], "Reference checksum mismatch")
        print(f"Verified existing {len(existing['images'])}-image training reference bank", flush=True)
        return existing
    raw = fetch("instances_train2019.json", bank / "instances_train2019.json", 25_000_000)
    coco = json.loads(raw)
    images = {image["id"]: image for image in coco["images"]}
    by_image = defaultdict(list)
    for annotation in coco["annotations"]:
        by_image[annotation["image_id"]].append(annotation)
    groups = defaultdict(list)
    for image_id, annotations in by_image.items():
        if len(annotations) == 1:
            groups[annotations[0]["category_id"]].append((images[image_id], annotations[0]))
    selection = []
    for category in sorted(coco["categories"], key=lambda c: c["id"]):
        ranked = sorted(groups[category["id"]], key=lambda item: sha256(f"{SEED}:reference:{item[0]['file_name']}".encode()))
        require(len(ranked) >= per_category, "Insufficient single-product training references")
        selection.extend(ranked[:per_category])

    def download_reference(pair):
        image, annotation = pair
        name = image["file_name"]
        require(re.fullmatch(r"[A-Za-z0-9_~.-]+\.jpg", name) and ".." not in name, "Unsafe reference filename")
        remote = "retail_product_checkout/train2019/" + name
        destination = bank / "images" / name
        raw_image = destination.read_bytes() if destination.exists() else fetch(remote, destination, 8_000_000)
        require(len(raw_image) <= 8_000_000 and raw_image.startswith(b"\xff\xd8"), "Training source is not a bounded JPEG")
        return {**image, "category_id": annotation["category_id"], "bbox": annotation["bbox"],
                "source_file": remote, "sha256": sha256(raw_image), "bytes": len(raw_image)}

    entries = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, entry in enumerate(pool.map(download_reference, selection)):
            entries.append(entry)
            if (index+1) % 25 == 0:
                print(f"Downloaded training references {index+1}/{len(selection)}", flush=True)
    manifest = {"schema_version": "rpc-references/1.0", "source": SOURCE, "license": "CC-BY-NC-SA-4.0",
                "source_split": "train2019", "evidence_kind": "real_photographs", "annotation_sha256": sha256(raw),
                "selection": {"seed": SEED, "method": "sha256(seed:reference:filename) per training category", "per_category": per_category},
                "categories": coco["categories"], "images": entries}
    manifest["hash"] = digest(manifest)
    temporary = bank / "manifest.json.part"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(manifest_path)
    print(f"Registered {len(entries)} real training references across {len(coco['categories'])} categories", flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=str(Path(os.environ.get("CHECKOUTCHECK_DATA", "private-data")) / "rpc"))
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--references", type=int, default=0, help="Also acquire 1–3 original training photographs per category")
    arguments = parser.parse_args()
    acquire(arguments.directory, arguments.count)
    if arguments.references:
        acquire_references(arguments.directory, arguments.references)
