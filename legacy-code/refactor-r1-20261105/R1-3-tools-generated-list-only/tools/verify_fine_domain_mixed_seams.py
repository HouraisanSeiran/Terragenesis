"""Audit actual mixed-resolution saved leaf faces across explicit domain cuts."""

import os

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.fine_domain_mosaic import partition_saved_window, audit_saved_mosaic, partition_fan_geometry, bind_saved_leaf_faces
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
from terrain_pipeline.surface_adaptive_water import load_consumer_adaptive_frame
from tools.verify_fine_domain_mosaic import MANIFEST, MANIFEST_SHA


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT not in output.parents or output.exists():
        raise ValueError("new output directory inside workspace required")
    context = load_consumer_manifest(MANIFEST, expected_sha256=MANIFEST_SHA)
    records = []
    for scenario, index in (("tailwater-rise-root4",0),("tailwater-rise-root4",1),
                            ("tailwater-rise-root4",2),("tailwater-rise-root2",0)):
        saved = load_consumer_adaptive_frame(context,scenario=scenario,frame_index=index)
        geometry, snapshot = saved["geometry"]["arrays"], saved["snapshot"]["arrays"]
        version = saved["snapshot"]["identity_sha256"]
        mosaic = partition_saved_window(geometry["canonical_bed_m"],snapshot["canonical_depth_m"],
            snapshot["canonical_owner"],row_cuts=(168,),column_cuts=(16,),version=version)
        audit = audit_saved_mosaic(mosaic,geometry["canonical_bed_m"],snapshot["canonical_depth_m"],spacing_m=1.,version=version)
        _, seam = partition_fan_geometry(mosaic,saved["frame"]["arrays"])
        sizes = snapshot["leaf_spacing_m"][snapshot["canonical_owner"]].ravel()
        pairs = np.sort(np.column_stack((sizes[mosaic["first_cell"]],sizes[mosaic["second_cell"]])),axis=1)
        distinct, counts = np.unique(pairs,axis=0,return_counts=True)
        bind_saved_leaf_faces(mosaic,geometry)
        records.append(dict(scenario=scenario,index=index,time_s=saved["frame"]["metadata"]["time_s"],
            frame_identity=saved["frame"]["identity_sha256"],snapshot_identity=version,
            shared_leaf_spacing_pairs={f"{pair[0]}:{pair[1]}":int(count) for pair,count in zip(distinct,counts)},
            saved_segmented_face_binding_verified=True,audit=audit,geometry=seam))
    if not any(int(pair.split(':')[0]) != int(pair.split(':')[1]) for record in records for pair in record["shared_leaf_spacing_pairs"]):
        raise ValueError("predeclared mixed cuts have no actual cross-precision faces")
    if file_sha256(MANIFEST) != MANIFEST_SHA:
        raise ValueError("manifest pin changed")
    report = dict(schema="saved-fine-domain-mixed-seams-v1",status="passed_saved_segmented_geometry_scope",
        manifest_sha256=MANIFEST_SHA,row_cut=168,column_cut=16,records=records,
        solver_advanced=False,independent_domain_hydraulics_verified=False,
        cross_precision_hydraulic_evolution_verified=False,hydraulic_ready=False,
        natural_outlet_verified=False,publishable=False)
    output.mkdir(parents=True)
    path = output / "report.json"
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(dict(report=str(path),sha256=file_sha256(path),records=records)))


if __name__ == "__main__":
    main()
