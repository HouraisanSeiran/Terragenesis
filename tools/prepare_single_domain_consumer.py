"""Export or serve a relocatable, fixed-pin read-only surface consumer package."""

import argparse
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ.setdefault(name,"1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import psutil
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.single_domain_surface_archive import load_single_domain_index,iter_single_domain_frames
from terrain_pipeline.single_domain_surface_consumer import BUDGETS,SCHEMA,copy_payload,publish_manifest,load_consumer_manifest,readonly_server

NATIVE_INDEX = ROOT/"verification/single-domain-surface/native-same-bed-20261004-02/index.json"
NATIVE_SHA = "f9fe55ee4de39845378f5f6e2fe01a67cac46878ae7f00e90724cf2df1ba0017"


def export_native(index,index_sha256,output):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    started = time.monotonic()
    context = load_single_domain_index(index,expected_sha256=index_sha256)
    artifacts,scenarios = [],{}
    source_record = dict(path=str(Path(index).resolve()),expected_sha256=index_sha256)
    for direction in ("eastward","westward"):
        group = context["index"]["directions"][direction]
        geometry_name = direction+"/geometry.npz"
        artifacts.append(copy_payload(output,geometry_name,group["geometry"],context["geometries"][direction],
                                      role="bed-and-network-geometry",provenance=dict(source_index=source_record,source_artifact=group["geometry"])))
        frames = []
        for number,item in enumerate(iter_single_domain_frames(context,direction)):
            name = direction+f"/frame-{number:02d}.npz"
            pin = item["declaration"]["water_frame"]
            artifacts.append(copy_payload(output,name,pin,item["frame"],role="saved-water-frame",
                provenance=dict(source_index=source_record,source_artifact=pin,source_page=item["declaration"]["source_page"])))
            frames.append(dict(frame=number,time_s=item["declaration"]["time_s"],artifact=name))
            memory = psutil.Process().memory_info()
            if (max(getattr(memory,"peak_wset",memory.rss),getattr(memory,"peak_pagefile",0))>BUDGETS["max_memory_bytes"]
                    or sum(item["bytes"] for item in artifacts)>BUDGETS["max_output_bytes"]
                    or time.monotonic()-started>BUDGETS["max_wall_s"]):
                raise RuntimeError("consumer predeclared resource budget exceeded")
        scenarios[direction] = dict(geometry=geometry_name,frames=frames)
    if file_sha256(index)!=index_sha256:
        raise ValueError("consumer original source index changed")
    memory = psutil.Process().memory_info()
    manifest = dict(schema=SCHEMA,backend="native-v10-saved-dual-cell",evidence_status="native-accepted-temporal-and-same-bed-review",
                    source_index=source_record,artifacts=artifacts,scenarios=scenarios,budgets=BUDGETS,
                    output_bytes=sum(item["bytes"] for item in artifacts),solver_advanced=False,
                    resource=dict(elapsed_s=time.monotonic()-started,peak_rss_bytes=int(getattr(memory,"peak_wset",memory.rss)),
                                  peak_private_bytes=int(getattr(memory,"peak_pagefile",memory.vms))),
                    coordinates="physical metres [x,y,z]; x east, y up, z south; raster [z,x]",
                    hydraulic_ready=False,natural_outlet_verified=False,publishable=False,
                    official_frontend_integrated=False,limitations=context["index"]["limitations"],
                    code_sha256={name:file_sha256(ROOT/name) for name in ("terrain_pipeline/single_domain_surface_consumer.py","tools/prepare_single_domain_consumer.py")})
    pin = publish_manifest(output,manifest)
    load_consumer_manifest(pin["path"],expected_sha256=pin["expected_sha256"])
    print(pin,flush=True)
    return pin


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",type=Path,default=NATIVE_INDEX)
    parser.add_argument("--index-sha256",default=NATIVE_SHA)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--serve-manifest",type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--port",type=int,default=8766)
    args = parser.parse_args()
    if args.serve_manifest:
        if not args.manifest_sha256:
            parser.error("--manifest-sha256 required for read-only serving")
        context = load_consumer_manifest(args.serve_manifest,expected_sha256=args.manifest_sha256)
        server = readonly_server(context,port=args.port)
        print(f"Read-only manifest: http://127.0.0.1:{args.port}/manifest.json",flush=True)
        server.serve_forever()
    else:
        if not args.output:
            parser.error("--output required for fresh consumer export")
        export_native(args.index,args.index_sha256,args.output)
