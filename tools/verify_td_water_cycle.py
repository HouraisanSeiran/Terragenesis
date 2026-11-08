"""Finite TD native runoff to shared-step channel/lake water-cycle acceptance."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, save_bundle, validate_source
from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as ARRAY_KEYS
from terrain_pipeline.runoff import validate_rainfall_runoff_result as validate_rainfall_runoff_result
from terrain_pipeline.basin_storage import load_td_source as load_td_source
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing, TerrainGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.runoff import runoff_from_forcing as runoff_from_forcing
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelNetwork
from terrain_pipeline.lake import LakeStorage as LakeStorage
from terrain_pipeline.lake import LakeOutlet as LakeOutlet
from terrain_pipeline.surface_rivers.metric_boundary_coupling import BoundarySeries, CoupledForcing, solve_coupled
from terrain_pipeline.surface_rivers.metric_coupled_product import (
    make_coupled_product, save_coupled_product, load_coupled_product, sample_coupled_output,
)
from terrain_pipeline.surface_rivers.metric_water_cycle import (
    THRESHOLDS, forcing_identity, make_water_cycle, save_water_cycle, load_water_cycle,
)


def select_domain():
    source = load_td_source()
    raw = load_bundle(PRIMARY_PATH, expected_sha256=PRIMARY_SHA256, validator=validate_source)
    provenance = raw["metadata"]["provenance"]["generation_metadata"]
    a, m = source["arrays"], source["metadata"]
    row, col = np.array(a["height_m"].shape) // 2
    height = a["height_m"][row:row + 16, col:col + 16].copy()
    valid = a["valid_mask"][row:row + 16, col:col + 16].copy()
    spacing = m["spacing_m"]
    terrain = TerrainGrid(height, valid, m["origin_m_xz"][0] + col * spacing,
                          m["origin_m_xz"][1] + row * spacing, spacing, spacing,
                          "generated_terrain", "finite-TD-water-cycle", m["source_sha256"],
                          vertical_datum=raw["metadata"]["vertical_datum"],
                          generation_seed=int(provenance["seed"]), model_version=provenance["model"]["revision"],
                          condition_summary=provenance["conditioning_identity"],
                          source_path=str(PRIMARY_PATH))
    kinds = np.full(height.shape, "interior", "U24")
    kinds[[0, -1], :] = "closed_wall"
    kinds[:, [0, -1]] = "closed_wall"
    kinds[~valid] = "unknown_boundary"
    boundary = BoundaryGrid(kinds, np.zeros(height.shape, bool), "explicit finite closed TD diagnostic domain", source["identity_sha256"])
    graph = route_diagnostic(terrain, boundary)
    paths = []
    for cell in np.flatnonzero(valid):
        path = [int(cell)]
        while graph.receiver[path[-1]] >= 0:
            path.append(int(graph.receiver[path[-1]]))
        paths.append(path)
    path = max(paths, key=lambda value: (len(value), tuple(value)))
    if len(path) < 3:
        raise ValueError("TD window has no downhill receiver reach")
    terminal, channel_cell = path[-1], path[-2]
    owner = np.full(height.size, -1, np.int64)
    for route in paths:
        if route[-1] == terminal:
            owner[route[0]] = 0 if channel_cell in route else 1
    if not np.any(owner == 0) or not np.any(owner == 1):
        raise ValueError("both native channel and lake contribution domains required")
    return source, terrain, graph, owner, channel_cell, terminal, raw["metadata"]


def budget(product):
    a = product["arrays"]
    dt = np.diff(a["trace_time_seconds"])
    cv, lv = a["trace_channel_volume_m3"], a["trace_lake_volume_m3"]
    cr = np.diff(cv, axis=0) - dt[:, None] * (a["trace_channel_local_q_m3_s"] + a["trace_channel_donor_q_m3_s"] - a["trace_channel_q_m3_s"])
    lr = np.diff(lv, axis=0) - dt[:, None] * (a["trace_lake_local_q_m3_s"] + a["trace_lake_donor_q_m3_s"] - a["trace_lake_outlet_q_m3_s"].sum(axis=1)[:, None])
    local = float((a["trace_channel_local_q_m3_s"] * dt[:, None]).sum() + (a["trace_lake_local_q_m3_s"] * dt[:, None]).sum())
    external = float(a["trace_channel_boundary_volume_m3"].sum() + a["trace_lake_external_volume_m3"].sum())
    initial, final = float(cv[0].sum() + lv[0].sum()), float(cv[-1].sum() + lv[-1].sum())
    residual = initial + local - external - final
    tolerance = 1e-8 * max(1., initial, local, external)
    if abs(residual) > tolerance or np.max(np.abs(cr), initial=0.) > tolerance or np.max(np.abs(lr), initial=0.) > tolerance:
        raise ValueError("independent channel/lake/global continuity failed")
    return dict(initial_m3=initial, local_m3=local, external_m3=external, final_m3=final,
                residual_m3=residual, tolerance_m3=tolerance,
                channel_max_residual_m3=float(np.max(np.abs(cr), initial=0.)),
                lake_max_residual_m3=float(np.max(np.abs(lr), initial=0.)))


def verify(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.json").write_text(json.dumps({"version": "finite-water-cycle-v1", "thresholds": THRESHOLDS,
        "physical_seconds": 7200, "solver_max_dt_seconds": [30, 15], "rain_mm_h": {"dry": [0,0,0,0], "rain": [10,10,0,0], "storm": [0,120,120,0]}}, indent=2), encoding="utf-8")
    source, terrain, graph, owner, channel_cell, terminal, raw_metadata = select_domain()
    t = np.array([0., 1800., 3600., 5400., 7200.])
    active = owner.reshape(terrain.valid_mask.shape) >= 0
    runoff_terrain = TerrainGrid(terrain.elevation_m, active, **{
        k: v for k, v in asdict(terrain).items() if k not in ("elevation_m", "valid_mask")})
    h = terrain.elevation_m.ravel()
    distance = float(np.linalg.norm(np.subtract(divmod(channel_cell, 16), divmod(terminal, 16))) * terrain.dx_m)
    network = ChannelNetwork(np.array([-1], np.int64), np.array([distance]), np.array([5.]),
        np.array([h[channel_cell]]), np.array([(h[channel_cell] - h[terminal]) / distance]),
        np.array([.05]), np.array([100.]), np.array(["open_outflow"]), terrain.identity_sha256,
        "explicit rectangular section between adjacent TD receiver cells; lake cell excluded from channel control volume", "bounded assumed Manning n=0.05")
    lake = LakeStorage(np.array([terminal], np.int64), np.array([h[terminal]]),
        np.array([terrain.cell_area_m2]), terminal, float(h[terminal] + 100.), terrain.identity_sha256,
        "one native terminal cell finite support; engineered level pool, not certified natural lake")
    boundaries = BoundarySeries(np.empty(0, np.int64), np.empty(0, "U24"), np.empty(0, bool), t,
        np.empty((4, 0)), np.empty((4, 0)), np.empty(0), source["identity_sha256"])
    cases, pins = {}, {}
    input_arrays = {"terrain_height_m": terrain.elevation_m, "valid_mask": terrain.valid_mask,
                    "receiver": graph.receiver, "contribution_owner": owner, "time_seconds": t}
    input_meta = {"terrain_metadata": {k: v for k, v in asdict(terrain).items() if k not in ("elevation_m", "valid_mask")},
                  "source_file_sha256": file_sha256(PRIMARY_PATH), "source_identity_sha256": source["identity_sha256"],
                  "raw_source_metadata": raw_metadata,
                  "terrain_identity_sha256": terrain.identity_sha256, "graph_identity_sha256": graph.identity_sha256,
                  "runoff_selected_domain_identity_sha256": runoff_terrain.identity_sha256,
                  "channel_cell": channel_cell, "lake_cell": terminal, "time_semantics": "physical_seconds",
                  "scope": "receiver-selected finite TD contribution domain; explicit section, level pool and outlet assumptions"}
    inputs = {"arrays": input_arrays, "metadata": input_meta, "identity_sha256": identity(input_arrays, input_meta)}
    save_bundle(output / "inputs.npz", inputs, validator=lambda b: None)
    for weather, rates in (("dry", [0., 0., 0., 0.]), ("rain", [10., 10., 0., 0.]), ("storm", [0., 120., 120., 0.])):
        rain = np.asarray(rates)[:, None, None] * active[None, :, :]
        rf = RainfallForcing(t, rain.astype(np.float64), "finite TD " + weather, source["identity_sha256"])
        runoff = runoff_from_forcing(runoff_terrain, rf)
        native = runoff["native_result"]
        validate_rainfall_runoff_result(native)
        q = native["local_q_m3_s"]
        ids = runoff["valid_cell_ids"]
        cq = q[:, owner[ids] == 0].sum(axis=1)[:, None]
        lq = q[:, owner[ids] == 1].sum(axis=1)[:, None]
        na = {key: np.ascontiguousarray(native[key]) for key in ARRAY_KEYS}
        na.update(time_seconds=t, selected_cell_ids=ids, contribution_owner=owner[ids],
                  channel_local_q_m3_s=cq, lake_local_q_m3_s=lq)
        nm = {"native_metadata": native["metadata"], "rainfall_forcing_identity_sha256": rf.identity_sha256,
              "rainfall_source_id": rf.source_id, "rainfall_source_sha256": rf.source_sha256,
              "terrain_identity_sha256": runoff_terrain.identity_sha256,
              "source_terrain_identity_sha256": terrain.identity_sha256}
        nb = {"arrays": na, "metadata": nm, "identity_sha256": identity(na, nm)}
        save_bundle(output / (weather + "-native-runoff.npz"), nb, validator=lambda b: None)
        for kind in ("closed", "unknown", "one_way"):
            forcing = CoupledForcing(t, cq, lq, forcing_identity(cq, lq, rf.identity_sha256, kind))
            outlets = () if kind != "one_way" else (LakeOutlet(0, -1, float(h[terminal] + .001), .5, "explicit outward-only engineered spill; not natural sea"),)
            compared = []
            for step in (30., 15.):
                name = weather + "-" + kind + "-" + str(int(step))
                result = solve_coupled(network, (lake,), outlets, np.array([0], np.int64), forcing, boundaries,
                    config=ChannelConfig(max_dt_seconds=step, max_steps=20000))
                if result["metadata"]["status"] != "complete":
                    raise ValueError(name + ": " + str(result["metadata"]["failure_reason"]))
                product = make_coupled_product(network, (lake,), outlets, np.array([0], np.int64), forcing, boundaries, result)
                path = output / (name + ".npz")
                save_coupled_product(path, product)
                with patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled", side_effect=AssertionError("cold solve forbidden")):
                    cold = load_coupled_product(path, expected_sha256=file_sha256(path), expected_identity=product["identity_sha256"])
                ledger = budget(cold)
                rt = runoff["ledger"]["totals_m3"]
                combined = rt["rain_volume_m3"] - rt["et_volume_m3"] - rt["storage_change_m3"] - ledger["external_m3"] - (ledger["final_m3"] - ledger["initial_m3"])
                if abs(combined) > ledger["tolerance_m3"] or abs(ledger["local_m3"] - rt["outflow_volume_m3"]) > ledger["tolerance_m3"]:
                    raise ValueError("rainfall/runoff/hydraulic total ledger mismatch")
                frames = {}
                frame_products = {}
                for label, times in (("dense", np.arange(0., 7201., 300.)), ("sparse", np.array([0., 7200.])), ("hourly", np.array([0., 3600., 7200.]))):
                    sampled = sample_coupled_output(cold, times)
                    frame_products[label] = sampled
                    save_bundle(output / (name + "-" + label + ".npz"), sampled, validator=lambda b: None)
                    aa = sampled["arrays"]
                    frames[label] = float(aa["cumulative_channel_boundary_volume_m3"][-1] + aa["cumulative_lake_external_volume_m3"][-1])
                    if abs(frames[label] - ledger["external_m3"]) > ledger["tolerance_m3"]:
                        raise ValueError("output frame sampling changed boundary water volume")
                hourly = sample_coupled_output(cold, np.array([0., 3600., 7200.]))["arrays"]
                hour_export = np.diff(hourly["cumulative_channel_boundary_volume_m3"] + hourly["cumulative_lake_external_volume_m3"])
                if kind != "one_way" and ledger["external_m3"] != 0.:
                    raise ValueError("closed or unknown boundary exported water")
                cases[name] = {"water_budget": ledger, "runoff_budget": rt, "combined_residual_m3": combined,
                    "rainfall_forcing_identity_sha256": rf.identity_sha256, "frames_export_m3": frames,
                    "hourly_export_m3": hour_export.tolist(), "unknown_semantics": "unresolved retained inventory; no exterior tracking" if kind == "unknown" else None,
                    "last_time_seconds": float(cold["arrays"]["trace_time_seconds"][-1])}
                pins[name] = {"path": path.name, "sha256": file_sha256(path), "identity_sha256": product["identity_sha256"]}
                evidence = make_water_cycle(inputs, nb, cold, frame_products, kind)
                ep = output / (name + "-evidence.npz")
                save_water_cycle(ep, evidence)
                with patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled", side_effect=AssertionError("cold solve forbidden")):
                    restored = load_water_cycle(ep, expected_sha256=file_sha256(ep))
                pins[name]["evidence"] = {"path": ep.name, "sha256": file_sha256(ep), "identity_sha256": restored["identity_sha256"]}
                compared.append(ledger)
            error = abs(compared[0]["final_m3"] - compared[1]["final_m3"])
            relative = error / max(1., compared[1]["local_m3"])
            if relative > .01:
                raise ValueError("predeclared physical step refinement tolerance exceeded")
            cases[weather + "-" + kind + "-refinement"] = {"final_storage_difference_m3": error, "relative": relative, "limit": .01}
        forcing = CoupledForcing(t, cq, lq, forcing_identity(cq, lq, rf.identity_sha256, "closed"))
        failed = solve_coupled(network, (lake,), (), np.array([0], np.int64), forcing, boundaries,
            config=ChannelConfig(max_dt_seconds=15., max_steps=1))
        prefix = make_coupled_product(network, (lake,), (), np.array([0], np.int64), forcing, boundaries, failed)
        p = output / (weather + "-failed-prefix.npz")
        save_coupled_product(p, prefix)
        cold = load_coupled_product(p, expected_sha256=file_sha256(p), expected_identity=prefix["identity_sha256"])
        prefix_times = np.array([0., cold["arrays"]["trace_time_seconds"][-1]])
        prefix_frames = {name: sample_coupled_output(cold, prefix_times) for name in ("dense", "sparse", "hourly")}
        evidence = make_water_cycle(inputs, nb, cold, prefix_frames, "closed")
        ep = output / (weather + "-failed-prefix-evidence.npz")
        save_water_cycle(ep, evidence)
        load_water_cycle(ep, expected_sha256=file_sha256(ep))
        pins[weather + "-failed-prefix"] = {"path": ep.name, "sha256": file_sha256(ep), "identity_sha256": evidence["identity_sha256"]}
        cases[weather + "-failed-prefix"] = {"status": cold["metadata"]["result"]["status"], "failure_reason": cold["metadata"]["result"]["failure_reason"], "budget": budget(cold)}
    report = {"status": "accepted_bounded_finite_td_water_cycle", "cases": cases, "artifacts": pins,
              "source": input_meta, "selected_native_cells": int(active.sum()), "thresholds": {"scaled_mass_residual": 1e-8, "step_final_storage_relative": .01},
              "natural_outlet_verified": False, "publishable": False,
              "limitations": ["engineered one-cell level pool and rectangular reach on actual receiver connection", "unknown exterior remains unresolved", "not full-world hydrodynamics or certified natural lake/sea"]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output_existed = args.output.exists()
    try:
        report = verify(args.output)
    except Exception as error:
        if not output_existed and args.output.is_dir() and not (args.output / "report.json").exists():
            (args.output / "rejection.json").write_text(json.dumps({"status": "rejected", "reason": str(error)}, indent=2), encoding="utf-8")
        raise
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "selected_native_cells": report["selected_native_cells"]}))
