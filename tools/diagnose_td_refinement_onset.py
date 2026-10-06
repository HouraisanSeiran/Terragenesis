"""Locate earliest saved refinement differences and their upstream basin support."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.td_basin_storage import load_basin_storage
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.verify_td_basin_storage import HIERARCHY, HIERARCHY_SHA256, HIERARCHY_IDENTITY


def verify(package):
    package = Path(package)
    comparison_path = package / "strong-comparison.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    coarse_bundle = load_basin_storage(**comparison["coarse"])
    fine_bundle = load_basin_storage(**comparison["fine"])
    coarse, fine = coarse_bundle["arrays"], fine_bundle["arrays"]
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    topology = hierarchy["arrays"]
    columns = topology["height_m"].shape[1]
    frames = []
    for frame in range(1, len(coarse["depth_m"])):
        delta = coarse["depth_m"][frame] - fine["depth_m"][frame]
        ranked = np.argsort(-abs(delta), kind="stable")[:8]
        records = []
        for cell_value in ranked:
            cell = int(cell_value)
            upstream = np.zeros(delta.size, bool)
            upstream[cell] = True
            while True:
                donors = (topology["receiver"] >= 0) & upstream[topology["receiver"].clip(min=0)]
                expanded = upstream | donors
                if np.array_equal(expanded, upstream):
                    break
                upstream = expanded
            owner = int(topology["cell_owner"].ravel()[cell])
            leaf = int(topology["contribution_owner"].ravel()[cell])
            incident = np.flatnonzero((topology["face_cells"] == cell).any(axis=1))
            record = {"cell": cell, "zx": list(map(int, divmod(cell, columns))), "bed_m": float(topology["height_m"].ravel()[cell]),
                      "depth_difference_m": float(delta[cell]), "owner_node": owner, "contribution_leaf": leaf,
                      "upstream_static_cells": int(upstream.sum()), "upstream_max_saved_error_m": float(abs(delta[upstream]).max()),
                      "incident_face_ids": incident.tolist(),
                      "incident_sill_m": topology["face_level_m"][incident].tolist(),
                      "incident_merge_node": topology["face_merge_node"][incident].tolist(),
                      "account_coarse_minus_fine_m3": {name: float(coarse[name][:frame, cell].sum() - fine[name][:frame, cell].sum())
                          for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "surface_et_m3", "internal_net_m3")},
                      "stage_birth_m": float(topology["node_birth_m"][owner]),
                      "stage_upper_m": None if not np.isfinite(topology["node_upper_m"][owner]) else float(topology["node_upper_m"][owner]),
                      "parent": int(topology["node_parent"][owner])}
            records.append(record)
        frames.append({"frame": frame, "time_s": frame * coarse_bundle["metadata"]["dt_s"],
                       "max_error_m": float(abs(delta).max()), "cells_over1mm": int((abs(delta) > .001).sum()),
                       "ranked_cells": records})
    first = next((frame for frame in frames if frame["cells_over1mm"]), None)
    report = {"schema": "td-refinement-onset-static-support-v1", "comparison": {"path": str(comparison_path), "sha256": file_sha256(comparison_path)},
              "first_saved_frame_over1mm": first, "frames": frames,
              "hydraulic_ready": False, "transient_converged": False, "publishable": False,
              "solver_advanced": False, "code_sha256": file_sha256(__file__),
              "limitations": "Hourly saved states locate first observed error only, not exact substep onset. Static receiver donors omit uphill spill exchange; basin/incident D4 faces retained for causal followup.",
              "next_controlled_experiment": "Freeze earliest-error connected upstream basin and its actual face boundary input; integrate its full multi-face ODE from t0 and compare matching orders and event crossings before adopting adaptive refinement."}
    destination = ROOT / "verification/td-basin-generation" / ("A-v4-onset-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    publish_bytes(destination / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(destination), "sha256": file_sha256(destination / "report.json"),
                      "first_frame": None if first is None else first["frame"]}), flush=True)


if __name__ == "__main__":
    verify(sys.argv[1])
