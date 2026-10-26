"""SIFT/RANSAC matching against real RPC training exemplars; no neural weights."""
import hashlib
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np

from .evaluator import digest, require

CONFIG = {"reference_features": 600, "query_features": 5000, "reference_max_dimension": 640,
          "query_max_dimension": 1280, "ratio_threshold": 0.72, "minimum_inliers": 6,
          "ransac_reprojection_px": 4.0, "max_instances_per_reference": 4, "nms_iou": 0.35,
          "flann_trees": 4, "flann_checks": 64, "seed": 17}


def load_bank(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest.get("schema_version") == "rpc-references/1.0" and manifest.get("source_split") == "train2019", "Reference bank must use RPC training photographs")
    require(digest({k:v for k,v in manifest.items() if k != "hash"}) == manifest.get("hash"), "Reference manifest hash mismatch")
    require(1 <= len(manifest["images"]) <= 600, "Reference bank size is invalid")
    descriptors, points, reference_ids, metadata = [], [], [], []
    sift = cv2.SIFT_create(nfeatures=CONFIG["reference_features"])
    for entry in manifest["images"]:
        require(isinstance(entry["file_name"],str) and re.fullmatch(r"[A-Za-z0-9_~.-]+\.jpg",entry["file_name"]) and ".." not in entry["file_name"], "Unsafe training image filename")
        raw = (directory / "images" / entry["file_name"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "Training reference checksum mismatch")
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        require(image is not None, "Undecodable training reference")
        x,y,w,h = entry["bbox"]
        crop = image[max(0,math.floor(y)):min(image.shape[0],math.ceil(y+h)), max(0,math.floor(x)):min(image.shape[1],math.ceil(x+w))]
        require(crop.size > 0, "Empty training annotation crop")
        scale = min(1,CONFIG["reference_max_dimension"]/max(crop.shape))
        crop = cv2.resize(crop,(round(crop.shape[1]*scale),round(crop.shape[0]*scale)),interpolation=cv2.INTER_AREA)
        keypoints, features = sift.detectAndCompute(crop,None)
        index = len(metadata)
        metadata.append({"category_id":entry["category_id"],"file_name":entry["file_name"],"width":crop.shape[1],"height":crop.shape[0]})
        if features is not None and len(features) >= CONFIG["minimum_inliers"]:
            descriptors.append(features)
            points.extend([keypoint.pt for keypoint in keypoints])
            reference_ids.extend([index]*len(features))
    require(bool(descriptors), "No usable features in the real training references")
    return {"descriptors":np.concatenate(descriptors).astype(np.float32),"points":np.array(points,np.float32),
            "reference_ids":np.array(reference_ids,np.int32),"metadata":metadata,"manifest_hash":manifest["hash"],
            "reference_images":len(manifest["images"]),"categories":len(manifest["categories"])}


def overlap(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    intersection=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    return intersection/(aw*ah+bw*bh-intersection)


class ReferenceMatcher:
    def __init__(self,directory):
        cv2.setRNGSeed(CONFIG["seed"])
        cv2.setNumThreads(1)
        self.bank=load_bank(directory)
        self.sift=cv2.SIFT_create(nfeatures=CONFIG["query_features"])
        self.matcher=cv2.FlannBasedMatcher(dict(algorithm=1,trees=CONFIG["flann_trees"]),dict(checks=CONFIG["flann_checks"]))
        self.matcher.add([self.bank["descriptors"]])
        self.matcher.train()

    def detect(self,image):
        height,width=image.shape[:2]
        factor=min(1,CONFIG["query_max_dimension"]/max(height,width))
        gray=cv2.cvtColor(cv2.resize(image,(round(width*factor),round(height*factor))),cv2.COLOR_BGR2GRAY)
        keypoints,features=self.sift.detectAndCompute(gray,None)
        candidates=[]
        if features is not None:
            grouped={}
            for neighbors in self.matcher.knnMatch(features,k=2):
                if len(neighbors)!=2:continue
                best,second=neighbors
                if best.distance < CONFIG["ratio_threshold"]*second.distance:
                    reference=int(self.bank["reference_ids"][best.trainIdx])
                    grouped.setdefault(reference,[]).append(best)
            for reference,matches in sorted(grouped.items()):
                metadata=self.bank["metadata"][reference]
                for _ in range(CONFIG["max_instances_per_reference"]):
                    if len(matches)<CONFIG["minimum_inliers"]:break
                    source=np.float32([self.bank["points"][m.trainIdx] for m in matches])
                    target=np.float32([keypoints[m.queryIdx].pt for m in matches])
                    transform,inliers=cv2.findHomography(source,target,cv2.RANSAC,CONFIG["ransac_reprojection_px"])
                    if transform is None or inliers is None:break
                    inlier_count=int(inliers.sum())
                    if inlier_count<CONFIG["minimum_inliers"]:break
                    corners=np.float32([[0,0],[metadata["width"],0],[metadata["width"],metadata["height"]],[0,metadata["height"]]]).reshape(-1,1,2)
                    projected=cv2.perspectiveTransform(corners,transform).reshape(-1,2)
                    if np.isfinite(projected).all() and cv2.isContourConvex(projected.reshape(-1,1,2)):
                        x1,y1=projected.min(axis=0);x2,y2=projected.max(axis=0)
                        area=float((x2-x1)*(y2-y1))
                        if x1>=-5 and y1>=-5 and x2<=gray.shape[1]+5 and y2<=gray.shape[0]+5 and .0006*gray.size<=area<=.75*gray.size:
                            x1,y1=max(0,float(x1)),max(0,float(y1));x2,y2=min(gray.shape[1],float(x2)),min(gray.shape[0],float(y2))
                            sx,sy=width/gray.shape[1],height/gray.shape[0]
                            candidates.append({"box":[x1*sx,y1*sy,(x2-x1)*sx,(y2-y1)*sy],"category_id":metadata["category_id"],
                                "inliers":inlier_count,"reference":metadata["file_name"]})
                    matches=[m for m,keep in zip(matches,inliers.ravel()) if not keep]
        kept=[]
        for candidate in sorted(candidates,key=lambda c:(-c["inliers"],c["category_id"],c["reference"])):
            if all(overlap(candidate["box"],other["box"])<CONFIG["nms_iou"] for other in kept):kept.append(candidate)
        require(len(kept)<=100,"Too many matched products")
        return {"boxes":[[round(v,3) for v in c["box"]] for c in kept],"category_ids":[c["category_id"] for c in kept],
                "match_evidence":[{"inliers":c["inliers"],"training_reference":c["reference"]} for c in kept],
                "warnings":["Reference matching may miss textureless, occluded or differently oriented packaging; inlier counts are not calibrated probabilities."],
                "opencv_version":cv2.__version__}
