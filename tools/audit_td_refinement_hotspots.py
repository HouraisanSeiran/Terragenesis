"""Locate saved full-domain refinement errors without advancing any solver."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_full_refinement import compare


def audit(inputs):
    results = {}
    for scenario, records in inputs["cases"].items():
        comparison = compare(records["coarse"], records["fine"])
        coarse, metadata = read_record(records["coarse"])
        fine, fine_metadata = read_record(records["fine"])
        rows, columns = coarse["height_m"].shape
        valid = coarse["valid_mask"].ravel()
        difference = abs(coarse["depth_m"] - fine["depth_m"])
        maximum_by_cell = difference.max(axis=0)
        selected = np.flatnonzero(valid)
        selected = selected[np.argsort(-maximum_by_cell[selected], kind="stable")[:20]]
        hotspots = []
        area = metadata["spacing_m"] ** 2
        for cell in selected:
            cell = int(cell)
            row, column = divmod(cell, columns)
            frame = int(np.argmax(difference[:, cell]))
            adjacent = [cell + delta for delta in (-columns, columns, -1, 1)
                        if 0 <= cell + delta < rows * columns
                        and abs((cell + delta) // columns - row) + abs((cell + delta) % columns - column) == 1
                        and valid[cell + delta]]
            cumulative = {name: float((coarse[name][:frame, cell] - fine[name][:frame, cell]).sum())
                          for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "surface_et_m3",
                                       "internal_net_m3", "boundary_outflow_m3")}
            depth_volume_difference = float((coarse["depth_m"][frame, cell] - fine["depth_m"][frame, cell]) * area)
            expected_difference = cumulative["lake_rain_m3"] + cumulative["local_release_m3"] - cumulative["surface_et_m3"] + cumulative["internal_net_m3"] - cumulative["boundary_outflow_m3"]
            if abs(depth_volume_difference - expected_difference) > 1e-5:
                raise ValueError("hotspot surface ledger difference does not close")
            hotspots.append({"cell_id": cell, "row_column": [row, column],
                             "x_m": metadata["origin_m_xz"][0] + column * metadata["spacing_m"],
                             "z_m": metadata["origin_m_xz"][1] + row * metadata["spacing_m"],
                             "bed_m": float(coarse["height_m"][row, column]),
                             "adjacent_bed_m": [float(coarse["height_m"].ravel()[neighbor]) for neighbor in adjacent],
                             "receiver_cell": int(coarse["receiver"][cell]),
                             "error_frame": frame, "error_time_s": frame * metadata["dt_s"],
                             "max_depth_difference_m": float(maximum_by_cell[cell]),
                             "coarse_minus_fine_cumulative_surface_terms_m3": cumulative,
                             "coarse_minus_fine_surface_volume_m3": depth_volume_difference,
                             "difference_ledger_residual_m3": depth_volume_difference - expected_difference,
                             "coarse_depth_series_m": coarse["depth_m"][:, cell].tolist(),
                             "fine_depth_series_m": fine["depth_m"][:, cell].tolist(),
                             "soil_difference_series_mm": (fine["soil_mm"][:, cell] - coarse["soil_mm"][:, cell]).tolist(),
                             "lake_rain_difference_series_m3": (fine["lake_rain_m3"][:, cell] - coarse["lake_rain_m3"][:, cell]).tolist()})
        results[scenario] = {"refinement": comparison, "hotspots": hotspots,
                             "frames": [{"time_s": frame * metadata["dt_s"],
                                         "maximum_depth_difference_m": float(difference[frame].max()),
                                         "cells_over_1mm": int(np.count_nonzero(difference[frame, valid] > 0.001)),
                                         "absolute_surface_volume_difference_m3": float(difference[frame, valid].sum() * area)}
                                        for frame in range(len(difference))],
                             "forcing_partition_difference_m3": float((fine["lake_rain_m3"] - coarse["lake_rain_m3"]).sum()),
                             "forcing_partition_absolute_l1_m3": float(abs(fine["lake_rain_m3"] - coarse["lake_rain_m3"]).sum()),
                             "hydraulic_ready": False}
    return {"schema": "td-refinement-hotspot-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "scope": "Entire pinned saved TD grid, both hourly series and actual face ledgers",
            "cases": results, "solver_advanced": False, "hydraulic_ready": False,
            "conclusion": "Saved timestep differences locate sensitive cells; attribution requires a controlled solver experiment."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if file_sha256(arguments.inputs) != arguments.inputs_sha256:
        raise ValueError("external refinement inputs SHA mismatch")
    report = audit(json.loads(arguments.inputs.read_text(encoding="utf-8")))
    report["inputs_sha256"] = arguments.inputs_sha256
    report["auditor_sha256"] = file_sha256(__file__)
    publish_bytes(arguments.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({scenario: {"maximum_error_m": record["hotspots"][0]["max_depth_difference_m"],
                                 "maximum_error_cell": record["hotspots"][0]["cell_id"],
                                 "gate_passed": record["refinement"]["gate_passed"]}
                      for scenario, record in report["cases"].items()}))
