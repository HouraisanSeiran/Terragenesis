"""Measure warmed v7 reference/JIT RHS and canonical drag without stage claims."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ.setdefault(name,"1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.regional_surface_hydraulics import prepare_surface_geometry
from terrain_pipeline.single_domain_fine_geometry import prepare_subgrid_support
from terrain_pipeline import single_domain_shallow_water_support_v7 as reference
from terrain_pipeline import single_domain_shallow_water_accelerated_v7 as accelerated


def benchmark(size=240,repeats=8):
    if not 4<=size<=240 or size%4 or not 1<=repeats<=100:
        raise ValueError("benchmark domain/repeats outside bounded work")
    canonical = np.random.default_rng(721).uniform(0.,1.,(size,size))
    cases = []
    started = time.monotonic()
    for factor in (1,2,4):
        coarse = canonical.reshape(size//factor,factor,size//factor,factor).mean(axis=(1,3))
        support,datum = prepare_subgrid_support(dict(arrays=dict(canonical_bed_center_m=canonical,H2_m=coarse),metadata=dict(spacing_m=float(factor))))
        geometry = prepare_surface_geometry(coarse,spacing_m=float(factor),origin_m_xz=[0.,0.],source_identity="benchmark")
        arrays = geometry["arrays"]
        state = np.column_stack((np.full(coarse.size,.3),np.full(coarse.size,.03),np.full(coarse.size,-.01)))
        arguments = dict(support=support,spacing=float(factor),gravity=9.81,boundary_kind=arrays["boundary_kind"],
            tailwater=np.zeros(len(arrays["boundary_kind"])),roughness=.035,dt=.01,boundary_crest=arrays["boundary_crest_m"]-datum)
        warmed = time.perf_counter()
        accelerated.shallow_water_rhs(state,coarse-datum,**arguments)
        accelerated.manning_damping(state,.01,9.81,.035,support=support)
        warm_s = time.perf_counter()-warmed
        durations = {}
        for label,module in (("reference",reference),("accelerated",accelerated)):
            t = time.perf_counter()
            for _ in range(repeats):
                module.shallow_water_rhs(state,coarse-datum,**arguments)
            durations[label+"_rhs_s"] = (time.perf_counter()-t)/repeats
            t = time.perf_counter()
            for _ in range(repeats):
                module.manning_damping(state,.01,9.81,.035,support=support)
            durations[label+"_drag_s"] = (time.perf_counter()-t)/repeats
        cases.append(dict(spacing_m=factor,cells=coarse.size,segments=factor,warm_s=warm_s,**durations,
            rhs_speedup=durations["reference_rhs_s"]/durations["accelerated_rhs_s"],
            drag_speedup=durations["reference_drag_s"]/durations["accelerated_drag_s"]))
    memory = psutil.Process().memory_info()
    return dict(schema="v7-execution-microbenchmark-v1",cases=cases,repeats=repeats,
        resource=dict(elapsed_s=time.monotonic()-started,peak_rss_bytes=int(getattr(memory,"peak_wset",memory.rss)),
            peak_private_bytes=int(getattr(memory,"peak_pagefile",memory.vms))),
        hydraulic_equations_changed=False,stage_accepted=False,limitations=["Warmed kernel measurements do not establish full-stage wall time or refinement acceptance."])


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size",type=int,default=240)
    parser.add_argument("--repeats",type=int,default=8)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.size,args.repeats),indent=2),flush=True)
