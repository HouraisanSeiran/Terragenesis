"""Replay deterministic noise rain through the saved finite native TD river/lake domain."""

import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.rainfall_runoff import ARRAY_KEYS
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid, RainfallForcing
from terrain_pipeline.surface_rivers.metric_noise_forcing import grid_rainfall
from terrain_pipeline.surface_rivers.metric_runoff import runoff_from_forcing
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _unpack
from terrain_pipeline.surface_rivers.metric_water_cycle import load_water_cycle, make_water_cycle, save_water_cycle, forcing_identity
from terrain_pipeline.surface_rivers.metric_coupled_product import decode_coupled_product, make_coupled_product, sample_coupled_output
from terrain_pipeline.surface_rivers.metric_boundary_coupling import CoupledForcing, BoundarySeries, solve_coupled
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelConfig
from tools.verify_td_water_cycle import budget

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "verification/td-natural-river-stages/water-cycle-20261011-final-bound/rain-closed-30-evidence.npz"


def verify(output, seed=20261011):
    output.mkdir(parents=True, exist_ok=False)
    parent = load_water_cycle(PARENT, expected_sha256=file_sha256(PARENT))
    inputs = copy.deepcopy(_unpack(parent["arrays"], parent["metadata"], "inputs"))
    historical = _unpack(parent["arrays"], parent["metadata"], "coupled")
    network, lakes, outlets, mapping, _, old_boundaries = decode_coupled_product(historical)
    ia, im = inputs["arrays"], inputs["metadata"]
    active = ia["contribution_owner"].reshape(ia["valid_mask"].shape) >= 0
    terrain = TerrainGrid(ia["terrain_height_m"], active, **im["terrain_metadata"])
    t = np.array([0., 300., 600., 900.])
    ia["time_seconds"] = t
    inputs["identity_sha256"] = identity(ia, im)
    generated, provenance = grid_rainfall(seed, origin_xz_m=(terrain.x0_m, terrain.z0_m),
        shape_zx=active.shape, spacing_m=terrain.dx_m, time_edges_s=t, spatial_subsamples=2)
    rain = generated.rain_mm_h.copy()
    rain[:, ~active] = 0.
    forcing = RainfallForcing(t, rain, generated.source_id, generated.source_sha256)
    runoff = runoff_from_forcing(terrain, forcing)
    native, ids = runoff["native_result"], runoff["valid_cell_ids"]
    owner = ia["contribution_owner"][ids]
    cq = native["local_q_m3_s"][:, owner == 0].sum(axis=1)[:, None]
    lq = native["local_q_m3_s"][:, owner == 1].sum(axis=1)[:, None]
    arrays = {key: np.ascontiguousarray(native[key]) for key in ARRAY_KEYS}
    arrays.update(time_seconds=t, selected_cell_ids=ids, contribution_owner=owner,
                  channel_local_q_m3_s=cq, lake_local_q_m3_s=lq)
    metadata = {"native_metadata": native["metadata"], "rainfall_forcing_identity_sha256": forcing.identity_sha256,
        "rainfall_source_id": forcing.source_id, "rainfall_source_sha256": forcing.source_sha256,
        "terrain_identity_sha256": terrain.identity_sha256, "source_terrain_identity_sha256": im["terrain_identity_sha256"],
        "noise_rainfall_provenance": provenance}
    native_bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    boundaries = BoundarySeries(old_boundaries.node_ids, old_boundaries.kinds, old_boundaries.allow_inflow, t,
        np.empty((3, 0)), np.empty((3, 0)), old_boundaries.conductance_m2_s, old_boundaries.source_identity_sha256)
    coupled_forcing = CoupledForcing(t, cq, lq, forcing_identity(cq, lq, forcing.identity_sha256, "closed"))
    result = solve_coupled(network, lakes, outlets, mapping, coupled_forcing, boundaries,
                          config=ChannelConfig(max_dt_seconds=15., max_steps=20000))
    if result["metadata"]["status"] != "complete":
        raise ValueError("noise-driven coupled solve incomplete")
    product = make_coupled_product(network, lakes, outlets, mapping, coupled_forcing, boundaries, result)
    frames = {"dense": sample_coupled_output(product, t), "sparse": sample_coupled_output(product, np.array([0., 900.])),
              "hourly": sample_coupled_output(product, np.array([0., 900.]))}
    evidence = make_water_cycle(inputs, native_bundle, product, frames, "closed")
    path = output / "noise-water-cycle.npz"
    save_water_cycle(path, evidence)
    with patch("terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff", side_effect=AssertionError("cold native solve forbidden")), \
         patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled", side_effect=AssertionError("cold coupled solve forbidden")):
        cold = load_water_cycle(path, expected_sha256=file_sha256(path))
    cold_native = _unpack(cold["arrays"], cold["metadata"], "native")["arrays"]
    integrated = rain.reshape(3, -1)[:, ids] / 1000. * np.diff(t)[:, None] / 3600. * terrain.cell_area_m2
    error = float(np.max(np.abs(integrated - cold_native["rain_volume_m3"])))
    ledger = budget(_unpack(cold["arrays"], cold["metadata"], "coupled"))
    if error > 1e-10 or integrated.sum() <= 0. or ledger["local_m3"] <= 0.:
        raise ValueError("independent native rainfall or nonzero local inflow check failed")
    report = {"schema": "TD-noise-water-cycle-verification-v1", "status": "accepted_bounded_noise_water_cycle",
        "scope": "900s noise rainfall on original finite 96-cell TD channel/lake contribution domain;closed exterior",
        "source_sha256": file_sha256(PARENT), "source": {"path": str(PARENT.relative_to(ROOT)), "identity_sha256": parent["identity_sha256"]},
        "summary": {"selected_native_cells": int(active.sum()), "rain_volume_m3": float(integrated.sum()),
            "native_rain_max_error_m3": error, "water_budget": ledger, "cold_solver_forbidden": True},
        "forcing_provenance": provenance, "rainfall_forcing_identity_sha256": forcing.identity_sha256,
        "artifact": {"path": path.name, "sha256": file_sha256(path), "identity_sha256": cold["identity_sha256"]},
        "natural_certification": False, "publishable": False,
        "limitations": ["2x2 midpoint numerical cell average", "monthly climate target does not guarantee realized annual rainfall",
                        "engineered rectangular reach and one-cell level pool;original domain is diagnostic"]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.output)["summary"]))
