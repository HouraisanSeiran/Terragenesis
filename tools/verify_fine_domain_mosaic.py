"""Pure IO stage-two saved AMR mosaic audit; no hydrology replay."""

import os

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.surface_domain import audit_saved_mosaic, partition_saved_window, partition_fan_geometry
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
from terrain_pipeline.adaptive_mesh import load_consumer_adaptive_frame
from tools.verify_td_native_domain_partition import verify_size

MANIFEST = ROOT / "verification/single-domain-consumer/adaptive-amr-20261004-03/manifest.json"
MANIFEST_SHA = "170060df9b7e2ef08fed9cc1c54f586731c3644639ea0fb94444c007fc86e078"
ACCEPTANCE = ROOT / "verification/single-domain-stage/acceptance-20261004-03/acceptance-index.json"
ACCEPTANCE_SHA = "74f4b419f7341990e254c216cd2d37798f587abbabde6bc44ed507e92629971c"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT not in output.parents or output.exists():
        raise ValueError("new output directory inside workspace required")
    if file_sha256(ACCEPTANCE) != ACCEPTANCE_SHA:
        raise ValueError("stage-one acceptance pin mismatch")
    started = time.perf_counter()
    context = load_consumer_manifest(MANIFEST, expected_sha256=MANIFEST_SHA)
    output.mkdir(parents=True)
    records, payloads = [], []
    for scenario, declared in context["manifest"]["scenarios"].items():
        for index in range(len(declared["frames"])):
            saved = load_consumer_adaptive_frame(context, scenario=scenario, frame_index=index)
            frame, snapshot = saved["frame"], saved["snapshot"]
            bed = saved["geometry"]["arrays"]["canonical_bed_m"]
            depth = snapshot["arrays"]["canonical_depth_m"]
            version = snapshot["identity_sha256"]
            mosaic = partition_saved_window(bed, depth, snapshot["arrays"]["canonical_owner"],
                row_cuts=(120,), column_cuts=(120,), version=version)
            audit = audit_saved_mosaic(mosaic, bed, depth, spacing_m=1., version=version)
            meshes, seams = partition_fan_geometry(mosaic, frame["arrays"])
            leaf_sizes = snapshot["arrays"]["leaf_spacing_m"][snapshot["arrays"]["canonical_owner"]].ravel()
            pairs = np.sort(np.column_stack((leaf_sizes[mosaic["first_cell"]], leaf_sizes[mosaic["second_cell"]])), axis=1)
            distinct, counts = np.unique(pairs, axis=0, return_counts=True)
            spacings = {f"{pair[0]}:{pair[1]}":int(count) for pair, count in zip(distinct, counts)}
            records.append(dict(scenario=scenario, index=index, time_s=frame["metadata"]["time_s"],
                frame_identity=frame["identity_sha256"], snapshot_identity=version,
                bed_identity=saved["bed"]["identity_sha256"], audit=audit, geometry=seams,
                shared_leaf_spacing_pairs=spacings))
            if scenario == "tailwater-rise-root4" and index == 0:
                for mesh in meshes:
                    path = output / f"domain-{mesh['domain_id']}.npz"
                    np.savez_compressed(path, **mesh, face_ids=mosaic["face_ids"],
                        face_owner_domain=mosaic["face_owner_domain"], neighbor_domain=mosaic["neighbor_domain"],
                        snapshot_identity=np.array(version), frame_identity=np.array(frame["identity_sha256"]))
                    payloads.append(dict(path=path.name, sha256=file_sha256(path), bytes=path.stat().st_size))
            print(f"saved mosaic {scenario} {index}: {audit['shared_face_segments']} shared segments", flush=True)
            del saved, frame, snapshot, meshes, mosaic
            if psutil.Process().memory_info().peak_wset > 1073741824:
                raise MemoryError("stage-two audit exceeds unchanged 1GiB process budget")
    scale = verify_size(1024)
    if file_sha256(MANIFEST) != MANIFEST_SHA or file_sha256(ACCEPTANCE) != ACCEPTANCE_SHA:
        raise ValueError("source pins changed during audit")
    report = dict(schema="saved-fine-domain-mosaic-audit-v1", status="passed_saved_geometry_scope",
        source_manifest=dict(path=MANIFEST.relative_to(ROOT).as_posix(),sha256=MANIFEST_SHA),
        stage_one_acceptance=dict(path=ACCEPTANCE.relative_to(ROOT).as_posix(),sha256=ACCEPTANCE_SHA),
        domain_shape_zx=[120,120], canonical_shape_zx=[240,240], frame_count=len(records),
        records=records, representative_meshes=payloads, scale_topology=scale,
        wall_seconds=time.perf_counter()-started, peak_rss_bytes=psutil.Process().memory_info().peak_wset,
        solver_advanced=False, independent_domain_hydraulics_verified=False,
        cross_precision_hydraulic_evolution_verified=False, hydraulic_ready=False,
        natural_outlet_verified=False, publishable=False,
        limitations=["Domains partition the accepted saved canonical window; no independently evolved domain states.",
            "Shared fan is conservative display geometry, not hydraulic leaf stage.",
            "Domain cuts through a saved leaf are rejected, not silently split.",
            "1024 scale case is synthetic topology only; no large fine hydraulic solve."])
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(dict(report=str(path),sha256=file_sha256(path),frames=len(records),peak_rss_bytes=report["peak_rss_bytes"])),flush=True)


if __name__ == "__main__":
    main()
