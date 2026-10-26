"""Photo-trained Faster R-CNN and real-only RPC fine-tuning. No generated samples."""
import argparse
import hashlib
import json
import random
import time
from pathlib import Path

from .evaluator import digest, require

BASE_FILE = 'fasterrcnn_mobilenet_v3_large_fpn-fb6a3cc7.pth'
BASE_URL = 'https://download.pytorch.org/models/' + BASE_FILE
CONFIG = {'min_size': 512, 'max_size': 768, 'score_threshold': 0.5,
          'nms_threshold': 0.5, 'maximum_detections': 100, 'seed': 23, 'threads': 4}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_model(binary=False):
    import torch
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_fpn
    torch.set_num_threads(CONFIG['threads'])
    torch.manual_seed(CONFIG['seed'])
    return fasterrcnn_mobilenet_v3_large_fpn(
        weights=None, weights_backbone=None, num_classes=2 if binary else 91,
        min_size=CONFIG['min_size'], max_size=CONFIG['max_size'],
        box_score_thresh=CONFIG['score_threshold'], box_nms_thresh=CONFIG['nms_threshold'],
        box_detections_per_img=CONFIG['maximum_detections'])


def image_tensor(image):
    import cv2
    import torch
    return torch.from_numpy(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).permute(2,0,1).float()/255


def train(root, epochs=2):
    import cv2
    import numpy as np
    import torch
    import torchvision
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    root=Path(root)
    bank=json.loads((root/'rpc/references/manifest.json').read_text())
    require(bank['source_split']=='train2019' and bank['evidence_kind']=='real_photographs', 'Only original RPC training photographs are permitted')
    require(digest({k:v for k,v in bank.items() if k!='hash'})==bank['hash'],'Training manifest checksum mismatch')
    require(type(epochs) is int and 1<=epochs<=10,'Use 1–10 complete training epochs')
    output=root/'models/rpc-fasterrcnn-v1'
    require(not output.exists(),'Training output is immutable; select a new data directory for a different experiment')
    base=root/'models'/BASE_FILE
    require(file_hash(base).startswith('fb6a3cc7'),'Official checkpoint checksum mismatch')
    model=build_model()
    model.load_state_dict(torch.load(base,map_location='cpu',weights_only=True))
    # Train real product/background regions while retaining the pretrained image features.
    model.roi_heads.box_predictor=FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features,2)
    for parameter in model.backbone.parameters():parameter.requires_grad_(False)
    optimizer=torch.optim.SGD([p for p in model.parameters() if p.requires_grad],lr=.002,momentum=.9,weight_decay=.0005)
    model.train()
    model.backbone.eval()
    records=[]
    for entry in bank['images']:
        name=entry['file_name']
        require(Path(name).name==name and '..' not in name,'Unsafe training path')
        path=root/'rpc/references/images'/name
        require(file_hash(path)==entry['sha256'],'Training image checksum mismatch')
        records.append((entry,path))
    history=[]
    started=time.monotonic()
    for epoch in range(epochs):
        order=list(range(len(records)))
        random.Random(CONFIG['seed']+epoch).shuffle(order)
        losses=[]
        for step,index in enumerate(order):
            entry,path=records[index]
            image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            require(image is not None,'Training image cannot be decoded')
            x,y,w,h=entry['bbox']
            target={'boxes':torch.tensor([[x,y,x+w,y+h]],dtype=torch.float32),'labels':torch.tensor([1],dtype=torch.int64)}
            loss_values=model([image_tensor(image)],[target])
            loss=sum(loss_values.values())
            require(bool(torch.isfinite(loss)),'Training loss became nonfinite')
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),10)
            optimizer.step()
            losses.append(float(loss.detach()))
            if (step+1)%25==0:print(json.dumps({'epoch':epoch+1,'step':step+1,'images':len(order),'mean_loss':sum(losses)/len(losses),'seconds':round(time.monotonic()-started,1)}),flush=True)
        history.append({'epoch':epoch+1,'mean_loss':sum(losses)/len(losses),'images':len(order)})
    output.mkdir()
    torch.save(model.state_dict(),output/'weights.pth')
    manifest={'schema_version':'real-detector/1.0','architecture':'fasterrcnn_mobilenet_v3_large_fpn',
              'weights_sha256':file_hash(output/'weights.pth'),'base_weights_url':BASE_URL,'base_weights_sha256':file_hash(base),
              'base_training':'COCO photographs with ImageNet backbone initialization; torchvision published hflip recipe',
              'training_manifest_hash':bank['hash'],'training_source_split':'train2019','training_images':len(records),
              'training_sources':[{'file_name':e['file_name'],'sha256':e['sha256']} for e,_ in records],
              'fine_tuning_transforms':'Decode, BGR to RGB, numeric normalization and model resize only; no augmentation, rendering or compositing',
              'evaluation_images_used_for_training':False,'epochs':epochs,'history':history,'config':CONFIG,
              'optimizer':{'name':'SGD','learning_rate':.002,'momentum':.9,'weight_decay':.0005},
              'torch':torch.__version__,'torchvision':torchvision.__version__,'opencv':cv2.__version__,
              'training_seconds':time.monotonic()-started,'code_sha256':file_hash(__file__),
              'license_note':'Torchvision code BSD-3-Clause; RPC data CC-BY-NC-SA-4.0. Model is not cleared for commercial use.'}
    manifest['hash']=digest(manifest)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'trained':str(output),'hash':manifest['hash'],'history':history}),flush=True)


class LearnedDetector:
    def __init__(self, root, fine_tuned=False):
        import torch
        import torchvision
        root=Path(root)
        self.model=build_model(binary=fine_tuned)
        self.provenance={'torch':torch.__version__,'torchvision':torchvision.__version__,'device':'cpu',
                         'code_sha256':file_hash(__file__),'config':CONFIG}
        if fine_tuned:
            directory=root/'models/rpc-fasterrcnn-v1'
            manifest=json.loads((directory/'manifest.json').read_text())
            require(digest({k:v for k,v in manifest.items() if k!='hash'})==manifest['hash'],'Model manifest checksum mismatch')
            require(manifest['config']==CONFIG,'Registered model requires its original inference configuration')
            path=directory/'weights.pth'
            require(file_hash(path)==manifest['weights_sha256'],'Model weights checksum mismatch')
            self.provenance['training']=manifest
        else:
            path=root/'models'/BASE_FILE
            require(file_hash(path).startswith('fb6a3cc7'),'Official checkpoint checksum mismatch')
            self.provenance.update(weights_sha256=file_hash(path),weights_url=BASE_URL,training='Official COCO_V1 photographs; not fine-tuned on RPC')
        self.model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
        self.model.eval()
        self.torch=torch

    def detect(self,image):
        import cv2
        with self.torch.inference_mode():
            prediction=self.model([image_tensor(image)])[0]
        boxes=[]
        for x1,y1,x2,y2 in prediction['boxes'].tolist():
            boxes.append([x1,y1,x2-x1,y2-y1])
        return {'boxes':boxes,'scores':prediction['scores'].tolist(),'warnings':['Class-agnostic product localization only. Scores are not calibrated and do not identify SKUs or scan status.'],
                'opencv_version':cv2.__version__}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='private-data')
    parser.add_argument('--epochs',type=int,default=2)
    parser.add_argument('--prepare-base',action='store_true',help='Download and verify the official photo-trained COCO checkpoint, then exit')
    args=parser.parse_args()
    if args.prepare_base:
        import torch
        path=Path(args.directory)/'models'/BASE_FILE
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            temporary=path.with_suffix('.part')
            torch.hub.download_url_to_file(BASE_URL,str(temporary),hash_prefix='fb6a3cc7')
            temporary.replace(path)
        require(file_hash(path).startswith('fb6a3cc7'),'Official checkpoint checksum mismatch')
        print(json.dumps({'weights':str(path),'sha256':file_hash(path),'source':BASE_URL}))
    else:train(args.directory,args.epochs)
