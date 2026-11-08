"""Prepare one pinned open-surface metric VDM strike-slip candidate."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_vdm_forms import load_formed_vdm
from terrain_pipeline.metric_vdm_fault import FaultRecipe, load_fault, save_fault, apply_fault
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes


def _publish_json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def prepare(configuration, expected_sha256, output):
    configuration = Path(configuration).resolve(strict=True)
    if file_sha256(configuration) != expected_sha256:
        raise ValueError("fault configuration SHA mismatch")
    config = json.loads(configuration.read_text(encoding="utf-8"))
    if set(config) != {"source", "fault", "selection"}:
        raise ValueError("fault configuration fields mismatch")
    source = load_formed_vdm(**config["source"])
    selection_config = config["selection"]
    shape = source["arrays"]["reference_xyz_m"].shape[:2]
    if set(selection_config) != {"row_start", "row_stop", "column_start", "column_stop"}:
        raise ValueError("rectangular selection configuration required")
    selection = np.zeros(shape, bool)
    row_start, row_stop = int(selection_config["row_start"]), int(selection_config["row_stop"])
    column_start, column_stop = int(selection_config["column_start"]), int(selection_config["column_stop"])
    if not (0 <= row_start < row_stop <= shape[0] and 0 <= column_start < column_stop <= shape[1]):
        raise ValueError("selection outside source chart")
    selection[row_start:row_stop, column_start:column_stop] = True
    if np.any(source["arrays"]["protected_mask"] & selection):
        raise ValueError("selection intersects pinned protected mask")
    fault = FaultRecipe(
        plane_origin_xz_m=tuple(config["fault"]["plane_origin_xz_m"]),
        strike_degrees=config["fault"]["strike_degrees"], slip_m=config["fault"]["slip_m"],
        moving_side=config["fault"]["moving_side"], transition_width_m=config["fault"]["transition_width_m"],
    )
    result = apply_fault(source, recipe=fault, selection_mask=selection)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    bundle = output / "fault.npz"
    save_fault(bundle, result)
    pin = {"path": str(bundle), "expected_sha256": file_sha256(bundle),
           "expected_identity": result["identity_sha256"]}
    loaded = load_fault(**pin)
    arrays = result["arrays"]
    for name, vertices in (("reference", arrays["reference_xyz_m"].reshape(-1, 3)),
                           ("fault", arrays["vertices_xyz_m"])):
        lines = ["# physical metres XYZ; open surface; not a closed solid"]
        lines.extend("v " + " ".join(format(float(value), ".17g") for value in vertex)
                     for vertex in vertices)
        lines.extend("f " + " ".join(str(int(value) + 1) for value in face)
                     for face in arrays["triangles"])
        publish_bytes(output / (name + ".obj"), ("\n".join(lines) + "\n").encode("ascii"))
    review = {
        "schema": "metric-vdm-fault-review-v1", "geometry_schema": result["metadata"]["schema"],
        "source_identity": source["identity_sha256"], "fault_identity": result["identity_sha256"],
        "source_vdm_schema": source["metadata"]["schema"], "shape": list(shape),
        "selection_mask": selection.ravel().tolist(), "vertices_xyz_m": arrays["vertices_xyz_m"].tolist(),
        "triangles": arrays["triangles"].tolist(), "seam_edges": arrays["seam_edges"].tolist(),
        "vertex_side": arrays["vertex_side"].tolist(), "transition_weight": arrays["transition_weight"].tolist(),
        "applied_displacement_xyz_m": arrays["applied_displacement_xyz_m"].tolist(),
        "metadata": result["metadata"], "hydraulic_ready": False, "publishable": False,
        "self_intersection_verified": False,
    }
    _publish_json(output / "review.json", review)
    for record in (config["source"],):
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("fault source changed during export")
    if file_sha256(configuration) != expected_sha256:
        raise ValueError("fault configuration changed during export")
    report = {
        "schema": "metric-vdm-fault-preparation-v1", "configuration": {"path": str(configuration), "expected_sha256": expected_sha256},
        "source": config["source"], "fault": result["metadata"], "selection": selection_config,
        "fault_bundle": pin, "vertices": int(len(arrays["vertices_xyz_m"])),
        "triangles": int(len(arrays["triangles"])), "seam_edges": int(len(arrays["seam_edges"])),
        "moved_vertices": int(np.count_nonzero(np.linalg.norm(arrays["applied_displacement_xyz_m"], axis=1) > 1e-12)),
        "max_displacement_m": float(np.linalg.norm(arrays["applied_displacement_xyz_m"], axis=1).max()),
        "cold_roundtrip_passed": bool(np.array_equal(loaded["arrays"]["vertices_xyz_m"], arrays["vertices_xyz_m"])),
        "source_unchanged": True, "open_surface": True, "cross_seam_triangles": 0,
        "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
        "self_intersection_verified": False, "solver_advanced": False,
        "artifacts": {name: file_sha256(output / name) for name in ("reference.obj", "fault.obj", "review.json")},
        "code_sha256": {name: file_sha256(ROOT / name) for name in (
            "terrain_pipeline/metric_vdm_fault.py", "tools/prepare_metric_vdm_fault.py", "tools/audit_metric_vdm_fault.py")},
        "limitations": ["open surface only", "no fault side wall or closed volume", "no water or erosion response",
                        "overlap and geological stability remain diagnostic; no self-intersection certification"],
    }
    _publish_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/metric-vdm-fault" /
                        datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ"))
    args = parser.parse_args()
    print(json.dumps(prepare(args.configuration, args.configuration_sha256, args.output), ensure_ascii=False))
