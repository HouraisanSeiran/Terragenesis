"""Real equal-height DEM path on the frozen bilateral storage-graph solver.

This is a local engineered boundary experiment, not a whole-basin hydraulic
solution or natural-outlet evidence. The sampled DEM bed is never altered.
"""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import dynamic_surface_hydraulics as hydro
from terrain_pipeline.dem_domain import load_dem_candidate
from terrain_pipeline.real_dem_surface_network import RealDemNetwork
from tools.verify_real_dem_outlet_classification import DEFAULT_CANDIDATE, canonical_bytes, check_unchanged, source_record


def sample_path(candidate, result):
    height = candidate["arrays"]["height_m"]
    receiver = result["network"].receiver.ravel()
    distance = result["distance_to_exit"].ravel()
    component = result["component_id"].ravel()
    valid = candidate["arrays"]["valid_mask"].ravel()
    rows, cols = height.shape
    acceptable = []
    for record in result["components"]:
        root = record["root_cell_id"]
        if root is not None and record["touches_boundary"] and not record["touches_unknown"]:
            row, col = divmod(root, cols)
            if row in (0, rows - 1) or col in (0, cols - 1):
                acceptable.append(root)
    eligible = np.flatnonzero(valid & np.isin(component, acceptable) & (distance >= 2))
    if not len(eligible):
        raise ValueError("no real flat path with an actual clip-edge root and >=3 nodes")
    start = int(eligible[np.argmax(distance[eligible])])
    path = [start]
    while receiver[path[-1]] >= 0:
        path.append(int(receiver[path[-1]]))
    path = np.asarray(path[-32:], np.int64)
    if not np.all(height.ravel()[path] == height.ravel()[path[-1]]):
        raise ValueError("sample path must be equal-height, unmodified DEM")
    return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flat-package", type=Path, required=True)
    args = parser.parse_args()
    from tools.verify_real_dem_flat_routing import verify_package
    report = verify_package(args.flat_package)
    with np.load(args.flat_package / "network.npz", allow_pickle=False) as archive:
        result = {"network": RealDemNetwork(**{name: archive[name] for name in
                  ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")}),
                  "component_id": archive["component_id"], "distance_to_exit": archive["distance_to_exit"],
                  "components": report["components"]}
    candidate = load_dem_candidate(DEFAULT_CANDIDATE, verify_source=True)
    records = [source_record(DEFAULT_CANDIDATE), source_record(args.flat_package / "manifest.json"),
               source_record(hydro.__file__), source_record(__file__)]
    path = sample_path(candidate, result)
    grid = candidate["manifest"]["identity"]["grid"]
    spacing_x, spacing_z = grid["spacing_x_m"], grid["spacing_z_m"]
    origin_x, origin_z = grid["origin_x_m"], grid["origin_z_m"]
    row, col = np.divmod(path, candidate["arrays"]["height_m"].shape[1])
    coords = np.column_stack((origin_x + col * spacing_x, origin_z + row * spacing_z))
    bed = candidate["arrays"]["height_m"].ravel()[path].copy()
    nodes, steps, dt_s = len(path), 360, 30.
    edges = np.column_stack((np.arange(nodes - 1), np.arange(1, nodes))).astype(np.int64)
    area = np.full(nodes, 20. * min(spacing_x, spacing_z))
    boundary_mask = np.zeros(nodes, bool)
    boundary_mask[-1] = True
    boundary = np.broadcast_to(bed[None, :] + .2, (steps + 1, nodes)).copy()
    lateral = np.zeros((steps, nodes))
    lateral[:60, 0] = .01
    inputs = hydro.HydraulicsInput(bed_m=bed, area_m2=area, initial_stage_m=bed + .2,
        edges=edges, conductance_m2_s=np.full(nodes - 1, area.min() / (8 * dt_s)),
        local_q_m3_s=lateral, boundary_mask=boundary_mask, boundary_stage_m=boundary,
        dt_s=dt_s, max_depth_m=5., valid_mask=np.ones(nodes, bool), protected_mask=np.zeros(nodes, bool),
        coords_m=coords, source="real-DEM-flat-path-engineered-clip-boundary-local-benchmark",
        datum="source-SRTM-elevation-metres-unverified-vertical-datum",
        coords="EPSG:32651 X=easting Z=-northing; metres")
    raised = boundary.copy()
    raised[60:, -1] += 1.
    baseline = hydro.evaluate(inputs)
    tailwater = hydro.evaluate(replace(inputs, boundary_stage_m=raised))
    for value in (baseline, tailwater):
        hydro.validate(value)
        if value.status != "completed" or value.committed_steps != steps:
            raise ValueError("local bilateral test did not complete")
    delta = tailwater.stage_m[:, ~boundary_mask] - baseline.stage_m[:, ~boundary_mask]
    reverse = tailwater.qedges_m3_s < -1e-12
    if not reverse.any() or delta.max() <= 0:
        raise ValueError("no independently observable reversed flux/backwater")
    assert np.array_equal(tailwater.qedges_m3_s[:60], baseline.qedges_m3_s[:60])
    output = ROOT / "verification/real-dem-local-tailwater" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True)
    for name, value in (("baseline", baseline), ("raised-tailwater", tailwater)):
        hydro.save(value, output / (name + ".npz"))
        loaded = hydro.load(output / (name + ".npz"))
        if loaded.identity_sha256 != value.identity_sha256:
            raise ValueError("cold hydraulic archive identity mismatch")
    comparison = {"inputs": records, "global_cell_ids": path.tolist(), "node_count": nodes,
        "dt_s": dt_s, "physical_duration_s": steps * dt_s, "raise_at_s": 60 * dt_s,
        "max_internal_stage_delta_m": float(delta.max()),
        "negative_edge_flux_count": int(reverse.sum()),
        "boundary_net_inflow_m3": float(tailwater.ledger_m3[:, 2].sum()),
        "max_balance_residual_m3": float(np.abs(tailwater.ledger_m3[:, 5]).max()),
        "bed_equals_source": bool(np.array_equal(bed, candidate["arrays"]["height_m"].ravel()[path])),
        "storage_width_m": 20., "boundary": "explicit_engineered_clip_edge_not_natural_outlet",
        "scope": "local_equal_height_storage_conductance_graph_not_whole_DEM_not_Saint_Venant",
        "natural_outlet_verified": False, "ocean_outlet_certified": False,
        "baseline_identity": baseline.identity_sha256, "tailwater_identity": tailwater.identity_sha256}
    check_unchanged(records)
    (output / "comparison.json").write_bytes(canonical_bytes(comparison))
    artifacts = {name: source_record(output / name) for name in ("baseline.npz", "raised-tailwater.npz", "comparison.json")}
    (output / "manifest.json").write_bytes(canonical_bytes({"inputs": records, "artifacts": artifacts,
                                                            "source_unchanged": True, "natural_outlet_verified": False}))
    print(json.dumps({"output": str(output), **comparison}, ensure_ascii=False))


if __name__ == "__main__":
    main()
