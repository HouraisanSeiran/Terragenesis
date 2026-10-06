"""Keep raw neural output and specialist landform output as separate artifacts."""
import json,hashlib
from dataclasses import asdict
import numpy as np
from diffusion.paths import inside
from .export import export
from .landforms import CliffOperator,CliffSettings

def sculpt(args):
    source=inside(args.input)
    with np.load(source,allow_pickle=False) as data:
        vectors=data['vectors'];metadata=json.loads(str(data['metadata']))
    mask=np.load(inside(args.mask),allow_pickle=False)
    settings=CliffSettings(tuple(args.center),tuple(args.normal),args.height,args.transition,args.overhang)
    result=CliffOperator(settings).apply(vectors,metadata,mask)
    metadata=dict(metadata,parent_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  postprocess={'algorithm':'fault-scarp-v1','settings':asdict(settings),
                               'mask_sha256':hashlib.sha256(inside(args.mask).read_bytes()).hexdigest()})
    export(args.output,result,metadata)
