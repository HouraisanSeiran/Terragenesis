"""Paired displacement/condition data. A height-only raster is not accepted as XYZ ground truth."""
import json
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import Dataset
from diffusion.paths import inside

def load_pair(path,require_vectors=True):
    with np.load(path,allow_pickle=False) as data:
        condition=np.asarray(data['condition'],dtype=np.float32)
        meta=json.loads(str(data['metadata']))
        vectors=np.asarray(data['vectors'],dtype=np.float32) if require_vectors else None
    if condition.ndim!=3 or condition.shape[0]!=7 or min(condition.shape[1:])<8 or not np.isfinite(condition).all():
        raise ValueError('Conditions must be finite 7xHxW, H/W >=8')
    if (meta.get('reference')!='world-x-y-z-plane72' or not np.isfinite(meta.get('spacing',float('nan')))
        or meta.get('spacing',0)<=0 or len(meta.get('origin',[]))!=2 or not np.isfinite(meta['origin']).all()):
        raise ValueError('Missing coordinate contract')
    if require_vectors and (vectors.shape!=(3,*condition.shape[1:]) or not np.isfinite(vectors).all()):
        raise ValueError('Training targets must be finite XYZ maps, shape 3xHxW')
    weights=condition[3:]
    if (weights<0).any() or (weights>1).any() or not np.allclose(weights.sum(axis=0),1,atol=1e-4):
        raise ValueError('Four region weights must sum to one')
    return vectors,condition,meta

class VdmDataset(Dataset):
    def __init__(self,directory,config):
        self.files=sorted(inside(directory).glob('*.npz'))
        if not self.files:raise ValueError('No paired VDM training data')
        self.scale=np.asarray(config.vector_scale,dtype=np.float32)[:,None,None]
    def __len__(self):return len(self.files)
    def __getitem__(self,index):
        vectors,condition,_=load_pair(self.files[index])
        return torch.from_numpy(vectors/self.scale),torch.from_numpy(condition)
