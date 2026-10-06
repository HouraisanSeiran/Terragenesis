"""Verify fixed-route preparation on synthetic and saved lowland terrain."""

import json
import hashlib
import gc
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel, save_plan, load_plan
from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.surface_network_prepare import (SurfaceNetworkBudget,
    prepare_surface_network, save_surface_network, load_surface_network,
    save_surface_network_diagnostic)
from terrain_pipeline.surface_rivers import accumulate, route
from tests.test_channel_stage_inundation import confluence_plan
from tools.diagnose_river_feasibility import _boundary_connected_ocean


def prepare_case(plan, fine_origin, fine_shape, fine_spacing, legal_outlet, name, destination):
    domain = np.ones(fine_shape, bool)
    protected = np.zeros(fine_shape, bool)
    result = prepare_surface_network(plan, fine_origin[0], fine_origin[1], fine_spacing,
        fine_spacing, fine_shape, domain, protected, legal_outlet, np.array([5.2]) if name == "synthetic" else np.array([0.2]),
        SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
        InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 1e9, 1e9))
    if result["status"] == "prepared":
        path = destination / f"{name}.npz"
        save_surface_network(result, path)
        load_surface_network(path)
    return {"status": result["status"], **result["summary"]}


def main():
    wide_only = "--wide-only" in sys.argv
    destination = ROOT / "verification/surface-network-prepare" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir(parents=True)
    report = {}
    if not wide_only:
        synthetic = confluence_plan()
        legal = np.zeros((61, 61), bool); legal[-1, 27:34] = True
        report["synthetic"] = prepare_case(synthetic, (0., 0.), (61, 61), 1., legal, "synthetic", destination)
    source = ROOT / "verification/river-feasibility/extended-20260929T114427548312Z"
    source_file = source / "seed20261002-x-16000-z-13952-size1025.npz"
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    with np.load(source_file, allow_pickle=False) as archive:
        height = archive["elevation"].astype(np.float64)
        metadata = json.loads(str(archive["metadata"].item()))
    with np.load(source / "candidate-domain.npz", allow_pickle=False) as archive:
        catchment = archive["land_catchment_mask"].copy()
        mouth = archive["first_ocean_mouth_grid_zx"].copy()
        full_receiver = archive["receiver"].copy()
    ocean = _boundary_connected_ocean(height, 0.)
    if not ocean[tuple(mouth)]: raise ValueError("mouth is not boundary-connected ocean")
    z0, z1, x0, x1 = 375, 510, 490, 660
    crop = height[z0:z1, x0:x1]
    local_mouth = tuple((mouth - np.array([z0, x0])).tolist())
    domain_crop = catchment[z0:z1, x0:x1].copy()
    local_receiver = np.full(crop.size, -1, dtype=np.int64)
    for z, x in np.argwhere(domain_crop):
        global_cell = (z + z0) * 1025 + x + x0
        target = int(full_receiver[global_cell])
        if target < 0: raise ValueError("catchment route ends before mouth")
        tz, tx = divmod(target, 1025)
        if not (z0 <= tz < z1 and x0 <= tx < x1): raise ValueError("route leaves crop")
        local_receiver[z * crop.shape[1] + x] = (tz - z0) * crop.shape[1] + tx - x0
    outlet = (local_receiver.reshape(crop.shape) == -1)
    order = []
    seen = np.zeros(crop.size, bool)
    def visit(cell):
        if seen[cell]: return
        target = local_receiver[cell]
        if target >= 0: visit(int(target))
        seen[cell] = True; order.append(cell)
    for cell in range(crop.size): visit(cell)
    order = np.array(order, dtype=np.int64)
    q = np.zeros(crop.size, dtype=np.float64)
    q[domain_crop.ravel()] = 30. * 30. * 1e-8
    for cell in order[::-1]:
        target = local_receiver[cell]
        if target >= 0: q[target] += q[cell]
    q = q.reshape(crop.shape)
    for threshold in ((.02,) if wide_only else (.05, .02)):
        recipe = ChannelRecipe(start_discharge_m3_s=threshold)
        origin_x_m = (metadata["native_origin"][0] + x0) * 30.
        origin_z_m = (metadata["native_origin"][1] + z0) * 30.
        plan = plan_channel(crop, local_receiver, order, outlet, q,
            30., 30., origin_x_m, origin_z_m, 0., source_hash, recipe)
        channel = np.argwhere(plan["arrays"]["channel_mask"])
        bbox = [channel.min(axis=0).tolist(), channel.max(axis=0).tolist()] if len(channel) else None
        halo_cells = 10 if wide_only else 2
        fine_z0, fine_z1 = bbox[0][0] - halo_cells, bbox[1][0] + halo_cells + 1
        fine_x0, fine_x1 = bbox[0][1] - halo_cells, bbox[1][1] + halo_cells + 1
        refinement = 30 if threshold == .05 else 60
        fine_spacing = 30. / refinement
        fine_shape = ((fine_z1 - fine_z0 - 1) * refinement + 1,
                      (fine_x1 - fine_x0 - 1) * refinement + 1)
        fine_origin = (origin_x_m + fine_x0 * 30., origin_z_m + fine_z0 * 30.)
        legal = np.zeros(fine_shape, bool)
        mz, mx = local_mouth
        legal[(mz - fine_z0) * refinement, (mx - fine_x0) * refinement] = True
        coarse_z = np.clip(np.rint(np.arange(fine_shape[0]) / refinement + fine_z0).astype(int), 0, crop.shape[0]-1)
        coarse_x = np.clip(np.rint(np.arange(fine_shape[1]) / refinement + fine_x0).astype(int), 0, crop.shape[1]-1)
        ocean_crop = ocean[z0:z1, x0:x1]
        ocean_fine = ocean_crop[np.ix_(coarse_z, coarse_x)]
        fine_domain = domain_crop[np.ix_(coarse_z, coarse_x)] | ocean_fine
        fine_domain |= legal
        if wide_only:
            saved_plan = save_plan(plan, destination / "lowland-0.02-plan.npz")
            load_plan(saved_plan)
            wide = prepare_surface_network(plan, *fine_origin, fine_spacing, fine_spacing, fine_shape,
                fine_domain, np.zeros(fine_shape, bool), legal, np.array([0.]),
                SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
                InundationRecipe(max_lateral_reach_m=1200.), SurfaceNetworkBudget(4., 100000., 100000.))
            wide_path = destination / "lowland-0.02-full-basin-1200m.npz"
            if wide["status"] == "prepared": save_surface_network(wide, wide_path)
            else: save_surface_network_diagnostic(wide, wide_path)
            report["0.02_full_basin_1200m"] = {"status": wide["status"], "summary": wide["summary"],
                "source_sha256": source_hash, "mouth_discharge_m3_s": float(q[local_mouth]),
                "plan_npz": saved_plan.name, "plan_identity_sha256": plan["identity_sha256"],
                "catchment_mask_sha256": array_hash(catchment),
                "fine_domain_sha256": array_hash(fine_domain),
                "fine_legal_outlet_sha256": array_hash(legal),
                "fine_spacing_m": fine_spacing, "fine_origin_xz_m": fine_origin,
                "fine_shape_zx": fine_shape, "result_npz": wide_path.name,
                "coverage_note": "1200m is a computational coverage bound, not a physical flood-wall or calibrated reach"}
            continue
        diagnostic = prepare_surface_network(plan, *fine_origin, fine_spacing, fine_spacing, fine_shape,
            fine_domain, np.zeros(fine_shape, bool), legal, np.array([0.]),
            SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 100000., 100000.))
        diagnostic_path = destination / f"lowland-{threshold:.2f}-diagnostic.npz"
        if diagnostic["status"] == "prepared":
            save_surface_network(diagnostic, diagnostic_path)
        else:
            save_surface_network_diagnostic(diagnostic, diagnostic_path)
        report[str(threshold)] = {"channel_nodes": len(channel), "bbox": bbox,
                                  "plan_over_budget": int(plan["arrays"]["over_budget_mask"].sum()),
                                  "plan_failed_edges": int(plan["arrays"]["failed_slope_edge_donor_mask"].sum()),
                                  "source_sha256": source_hash, "mouth_discharge_m3_s": float(q[local_mouth]),
                                  "preparation": diagnostic["summary"],
                                  "status": diagnostic["status"],
                                  "note": "Observed-window lowland only; outlet/domain natural completeness unproved"}
        if threshold == .02:
            expanded = prepare_surface_network(plan, *fine_origin, fine_spacing, fine_spacing, fine_shape,
                fine_domain, np.zeros(fine_shape, bool), legal, np.array([0.]),
                SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
                InundationRecipe(max_lateral_reach_m=30.), SurfaceNetworkBudget(4., 100000., 100000.))
            report[str(threshold)]["reach_30m_scenario"] = {"status": expanded["status"],
                "summary": expanded["summary"]}
            expanded_path = destination / "lowland-0.02-reach-30m.npz"
            if expanded["status"] == "prepared": save_surface_network(expanded, expanded_path)
            else: save_surface_network_diagnostic(expanded, expanded_path)
            del expanded, diagnostic
            gc.collect()
            if fine_shape[0] * fine_shape[1] <= 5_000_000:
                wide = prepare_surface_network(plan, *fine_origin, fine_spacing, fine_spacing, fine_shape,
                    fine_domain, np.zeros(fine_shape, bool), legal, np.array([0.]),
                    SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
                    InundationRecipe(max_lateral_reach_m=120.), SurfaceNetworkBudget(4., 100000., 100000.))
                report[str(threshold)]["reach_120m_scenario"] = {"status": wide["status"],
                    "summary": wide["summary"]}
                wide_path = destination / "lowland-0.02-reach-120m.npz"
                if wide["status"] == "prepared": save_surface_network(wide, wide_path)
                else: save_surface_network_diagnostic(wide, wide_path)
            else:
                report[str(threshold)]["reach_120m_scenario"] = {"status": "not_run_memory_budget",
                    "fine_cells": int(fine_shape[0] * fine_shape[1]), "cell_limit": 5_000_000}
    (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__": main()
