"""Save a local cut of the already-deformed VDM and independently check provenance."""

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_vdm_forms import load_formed_vdm
from terrain_pipeline.metric_vdm_fault_v2 import FaultRecipe, apply_fault, load_fault, save_fault
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes


def publish(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def prepare(configuration, output):
    start = time.perf_counter()
    configuration = Path(configuration).resolve(strict=True)
    config_sha = file_sha256(configuration)
    config = json.loads(configuration.read_text(encoding="utf-8"))
    source = load_formed_vdm(**config["source"])
    chosen = config["selection"]
    selection = np.zeros(source["arrays"]["reference_xyz_m"].shape[:2], bool)
    selection[chosen["row_start"]:chosen["row_stop"], chosen["column_start"]:chosen["column_stop"]] = True
    recipe = FaultRecipe(**{**config["fault"], "plane_origin_xz_m": tuple(config["fault"]["plane_origin_xz_m"])})
    result = apply_fault(source, recipe=recipe, selection_mask=selection)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    save_fault(output / "fault.npz", result)
    fault_sha = file_sha256(output / "fault.npz")
    loaded = load_fault(output / "fault.npz", expected_sha256=fault_sha, expected_identity=result["identity_sha256"])
    arrays = loaded["arrays"]
    edge = arrays["vertex_source_edge"]
    fraction = arrays["vertex_source_fraction"][:, None]
    baseline = source["arrays"]["vertices_xyz_m"]
    expected = baseline[edge[:, 0]] * (1. - fraction) + baseline[edge[:, 1]] * fraction
    before = arrays["vertices_xyz_m"] - arrays["applied_displacement_xyz_m"]
    difference = float(np.max(np.abs(before - expected)))
    if difference > 1e-8:
        raise ValueError("independent VDM preservation audit failed")
    if file_sha256(configuration) != config_sha or file_sha256(config["source"]["path"]) != config["source"]["expected_sha256"]:
        raise ValueError("source changed during preparation")
    audit = {"schema": "metric-vdm-fault-audit-v2", "passed": True, "file_sha256": fault_sha,
             "identity": {"passed": True, "stored": result["identity_sha256"], "expected": result["identity_sha256"]},
             "max_vdm_preservation_error_m": difference, "source_vdm_identity": source["identity_sha256"],
             "source_vdm_preserved": True, "cold_read": True, "self_intersection_verified": False}
    publish(output / "audit.json", audit)
    geometry = {"vertices": len(arrays["vertices_xyz_m"]), "triangles": len(arrays["triangles"]),
                "seam_edges": len(arrays["seam_edges"]), "moved_vertices": int(np.count_nonzero(np.linalg.norm(arrays["applied_displacement_xyz_m"], axis=1) > 1e-12)),
                "max_displacement_m": float(np.linalg.norm(arrays["applied_displacement_xyz_m"], axis=1).max())}
    flags = {"hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False, "solver_advanced": False}
    pin = {"path": str(output / "fault.npz"), "expected_sha256": fault_sha, "expected_identity": result["identity_sha256"]}
    report = {"schema": "metric-vdm-fault-preparation-v2", "fault": result["metadata"],
              "fault_bundle": pin, "selection": chosen, "source": config["source"], "geometry": geometry,
              "source_vdm_preserved": True, "elapsed_s": time.perf_counter() - start, **flags}
    publish(output / "report.json", report)
    index = {"schema": "metric-vdm-fault-delivery-v2", "algorithm": result["metadata"]["algorithm"],
             "configuration": {"path": str(configuration), "sha256": config_sha},
             "source": {"path": config["source"]["path"], "sha256": config["source"]["expected_sha256"], "identity_sha256": source["identity_sha256"]},
             "fault": {"path": "fault.npz", "sha256": fault_sha, "identity_sha256": result["identity_sha256"]},
             "audit": {"path": "audit.json", "sha256": file_sha256(output / "audit.json")},
             "report": {"path": "report.json", "sha256": file_sha256(output / "report.json")},
             "geometry": geometry, "status": "diagnostic_not_publishable", **flags}
    publish(output / "index.json", index)
    return {"index": str(output / "index.json"), "sha256": file_sha256(output / "index.json"), "geometry": geometry, "audit": audit}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.configuration, args.output), ensure_ascii=False))
