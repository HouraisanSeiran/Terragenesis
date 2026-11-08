"""Independent M3/M4 references and bounded real-TD lake/river evidence."""

import argparse
from collections import deque
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_topology import basin_volume_at_level as basin_volume_at_level
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.lake import LakeStorage as LakeStorage
from terrain_pipeline.lake import LakeOutlet as LakeOutlet
from terrain_pipeline.surface_rivers.metric_boundary_coupling import BoundarySeries, CoupledForcing, solve_coupled
from terrain_pipeline.surface_rivers.metric_coupled_product import make_coupled_product, save_coupled_product, sample_coupled_output
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product


ROOT = Path(__file__).resolve().parents[1]
HIERARCHY_PATH = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
HIERARCHY_SHA = "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422"
HIERARCHY_ID = "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"
THRESHOLDS = {"ODE_relative_volume_error": .005, "depth_refinement_m": .001,
              "integrated_outflow_refinement_relative": .01, "global_scaled_residual": 1e-8}


def channel(receiver=(-1,), kind=None, lengths=20., widths=2., bed=None, slopes=.005, source="a" * 64):
    receiver = np.asarray(receiver, np.int64)
    n = len(receiver)
    if bed is None:
        bed = np.zeros(n)
        drop = np.broadcast_to(lengths, (n,)) * np.broadcast_to(slopes, (n,))
        for _ in range(n):
            for node, target in enumerate(receiver):
                if target >= 0:
                    bed[node] = bed[target] + drop[node]
    return ChannelNetwork(receiver, np.broadcast_to(lengths, (n,)).astype(np.float64).copy(),
        np.broadcast_to(widths, (n,)).astype(np.float64).copy(), np.asarray(bed, np.float64),
        np.broadcast_to(slopes, (n,)).astype(np.float64).copy(), np.full(n, .035), np.full(n, 5.),
        np.where(receiver < 0, "open_outflow", "interior") if kind is None else np.asarray(kind),
        source, "explicit_uncalibrated_rectangular_scenario", "explicit_uncalibrated_n_0.035")


def empty_boundaries(times):
    return BoundarySeries(np.empty(0, np.int64), np.empty(0, "U24"), np.empty(0, bool), times,
                           np.empty((len(times) - 1, 0)), np.empty((len(times) - 1, 0)), np.empty(0), "d" * 64)


def totals(result):
    arrays = result["arrays"]
    dt = np.diff(arrays["time_seconds"])
    local = float(np.sum(dt[:, None] * arrays["channel_local_q_m3_s"]) + np.sum(dt[:, None] * arrays["lake_local_q_m3_s"]))
    external = float(arrays["channel_boundary_volume_m3"].sum() + arrays["lake_external_volume_m3"].sum())
    change = float(np.sum(arrays["channel_volume_m3"][-1] - arrays["channel_volume_m3"][0])
                   + np.sum(arrays["lake_volume_m3"][-1] - arrays["lake_volume_m3"][0]))
    initial = float(arrays["channel_volume_m3"][0].sum() + arrays["lake_volume_m3"][0].sum())
    residual = local - external - change
    if (result["metadata"]["status"] != "complete" or not np.isfinite([local, external, change, residual]).all()
            or abs(residual) > THRESHOLDS["global_scaled_residual"] * max(1., initial, local, abs(external))):
        raise AssertionError((result["metadata"], residual))
    return {"local_input_m3": local, "signed_external_volume_m3": external,
            "storage_change_m3": change, "global_residual_m3": residual,
            "steps": len(dt), "max_stability_number": float(np.max(arrays["stability_number"], initial=0.))}


def reference(net, lakes, outlets, mapping, forcing, initial_c, initial_l, numerical_times):
    """Independent DOP853 RHS: explicit Manning, raw-cell V inverse and rating laws."""
    nc = len(initial_c)
    def stage_from_volume(lake, volume):
        # Bisection on raw source columns avoids calling the implemented inverse.
        lo, hi = float(lake.bed_elevation_m.min()), lake.max_stage_m
        for _ in range(65):
            mid = (lo + hi) / 2.
            amount = float(np.sum(np.maximum(mid - lake.bed_elevation_m, 0.) * lake.cell_area_m2))
            if amount < volume:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.
    saved = np.empty((len(numerical_times), nc + len(lakes)))
    state = np.r_[initial_c, initial_l]
    saved[0] = state
    for interval, (start, end) in enumerate(zip(forcing.time_seconds[:-1], forcing.time_seconds[1:])):
        def rhs(_, values):
            cv, lv = np.maximum(values[:nc], 0.), np.maximum(values[nc:], 0.)
            area = cv / net.length_m
            depth = area / net.width_m
            q = area * (area / (net.width_m + 2. * depth)) ** (2. / 3.) * np.sqrt(net.bed_slope) / net.roughness
            q = np.where(np.isin(net.terminal_kind, ("interior", "open_outflow")), q, 0.)
            derivative = np.r_[forcing.channel_local_q_m3_s[interval] - q, forcing.lake_local_q_m3_s[interval]].copy()
            for node, target in enumerate(net.receiver):
                if target >= 0:
                    derivative[target] += q[node]
                elif mapping[node] >= 0:
                    derivative[nc + mapping[node]] += q[node]
            stages = [stage_from_volume(lake, volume) for lake, volume in zip(lakes, lv)]
            for outlet in outlets:
                flux = outlet.coefficient_m3_s_m15 * max(stages[outlet.lake_index] - outlet.crest_stage_m, 0.) ** 1.5
                derivative[nc + outlet.lake_index] -= flux
                if outlet.receiver >= 0:
                    derivative[outlet.receiver] += flux
            return derivative
        solved = solve_ivp(rhs, (start, end), state, method="DOP853", rtol=2e-11, atol=2e-12, max_step=2., dense_output=True)
        if not solved.success:
            raise AssertionError(solved.message)
        selected = np.flatnonzero((numerical_times > start) & (numerical_times <= end))
        saved[selected] = solved.sol(numerical_times[selected]).T
        state = solved.y[:, -1]
    return saved


def connected_wet(ids, seed, columns):
    remaining = set(map(int, ids))
    if not remaining:
        return True
    if seed not in remaining:
        return False
    visited = {seed}
    pending = deque([seed])
    while pending:
        cell = pending.popleft()
        for target in (cell - columns, cell + columns, cell - 1, cell + 1):
            if abs(target // columns - cell // columns) + abs(target % columns - cell % columns) != 1:
                continue
            if target in remaining and target not in visited:
                visited.add(target)
                pending.append(target)
    return visited == remaining


def prepare(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    pins, cases = {}, {}

    def save(name, args, result):
        product = make_coupled_product(*args, result)
        path = output / (name + ".npz")
        save_coupled_product(path, product)
        pins[name] = {"path": path.name, "sha256": file_sha256(path), "identity_sha256": product["identity_sha256"]}
        dense = sample_coupled_output(product, np.linspace(result["arrays"]["time_seconds"][0], result["arrays"]["time_seconds"][-1], 31))
        sparse = sample_coupled_output(product, result["arrays"]["time_seconds"][[0, -1]])
        for key in ("channel_volume_m3", "lake_volume_m3", "cumulative_channel_boundary_volume_m3", "cumulative_lake_external_volume_m3"):
            np.testing.assert_array_equal(dense["arrays"][key][-1], sparse["arrays"][key][-1])
        cases[name] = totals(result) | {"dense_sparse_same_end_and_integral": True}
        return product

    # M3-only consistency proves the coupled route preserves the established baseline.
    net = channel((1, -1))
    times = np.array([0., 20., 60.])
    local = np.array([[.2, 0.], [0., 0.]])
    forcing = CoupledForcing(times, local, np.empty((2, 0)), "b" * 64)
    boundaries = empty_boundaries(times)
    mapping = np.full(2, -1, np.int64)
    config = ChannelConfig(max_dt_seconds=.2)
    result = solve_coupled(net, (), (), mapping, forcing, boundaries, config=config)
    old = solve_channel(net, ChannelForcing(times, local, "b" * 64), config=config)
    np.testing.assert_array_equal(result["arrays"]["time_seconds"], old["arrays"]["time_seconds"])
    np.testing.assert_allclose(result["arrays"]["channel_volume_m3"], old["arrays"]["volume_m3"], rtol=1e-13, atol=1e-13)
    save("m3_compatibility", (net, (), (), mapping, forcing, boundaries), result)

    # Prescribed stage has a closed-form conductance reservoir reference.
    net = channel(kind=["closed_wall"])
    times = np.array([0., 10., 20.])
    forcing = CoupledForcing(times, np.zeros((2, 1)), np.empty((2, 0)), "c" * 64)
    boundaries = BoundarySeries(np.array([0], np.int64), np.array(["prescribed_stage"]), np.array([True]), times,
        np.array([[.2], [0.]]), np.zeros((2, 1)), np.array([4.]), "d" * 64)
    mapping = np.array([-1], np.int64)
    args = (net, (), (), mapping, forcing, boundaries)
    stage_errors = []
    for name, dt in (("stage_boundary_coarse", .1), ("stage_boundary_fine", .025)):
        result = solve_coupled(*args, config=ChannelConfig(max_dt_seconds=dt))
        save(name, args, result)
        a = result["arrays"]
        t = a["time_seconds"]
        expected = np.where(t <= 10., 8. * (1. - np.exp(-.1 * t)), 8. * (1. - np.exp(-1.)) * np.exp(-.1 * (t - 10.)))
        error = float(np.max(np.abs(a["channel_volume_m3"][:, 0] - expected))) / float(expected.max())
        stage_errors.append(error)
        cases[name]["closed_form_relative_volume_error"] = error
        cases[name]["explicit_inflow_then_outflow"] = bool(np.any(a["boundary_q_m3_s"] < 0.) and np.any(a["boundary_q_m3_s"] > 0.))
    if not stage_errors[1] < stage_errors[0] or stage_errors[1] > THRESHOLDS["ODE_relative_volume_error"]:
        raise AssertionError(stage_errors)
    boundaries = BoundarySeries(np.array([0], np.int64), np.array(["prescribed_discharge"]), np.array([True]), times,
        np.zeros((2, 1)), np.array([[-.2], [.1]]), np.zeros(1), "d" * 64)
    args = (net, (), (), mapping, forcing, boundaries)
    result = solve_coupled(*args, config=ChannelConfig(max_dt_seconds=.5))
    np.testing.assert_allclose(result["arrays"]["channel_volume_m3"][-1, 0], 1., rtol=0., atol=1e-12)
    save("signed_discharge_boundary", args, result)

    # Preserve an actual runtime refusal as a saved, independently verifiable prefix.
    boundaries = empty_boundaries(times)
    forcing = CoupledForcing(times, np.array([[100.], [0.]]), np.empty((2, 0)), "c" * 64)
    args = (net, (), (), mapping, forcing, boundaries)
    failure = solve_coupled(*args, config=ChannelConfig(max_dt_seconds=1.))
    if failure["metadata"]["status"] != "failed_prefix" or failure["metadata"]["last_time_seconds"] != 2.:
        raise AssertionError(failure["metadata"])
    failure_product = make_coupled_product(*args, failure)
    failure_path = output / "channel_capacity_failed_prefix.npz"
    save_coupled_product(failure_path, failure_product)
    pins["channel_capacity_failed_prefix"] = {"path": failure_path.name, "sha256": file_sha256(failure_path),
        "identity_sha256": failure_product["identity_sha256"]}
    cases["channel_capacity_failed_prefix"] = {"status": "failed_prefix", "last_time_seconds": 2.,
        "requested_end_time_seconds": 20., "reason": failure["metadata"]["failure_reason"]}

    # Independent first spill time and ODE of a constant-area bowl.
    lake = LakeStorage(np.array([100], np.int64), np.array([0.]), np.array([100.]), 100, 2., "b" * 64, "analytic_flat_bowl")
    net = channel(kind=["closed_wall"])
    outlets = (LakeOutlet(0, -1, .02, 2., "explicit_analytic_weir"), LakeOutlet(0, -1, .02, 1., "second_analytic_weir"))
    times = np.array([0., 80., 160.])
    forcing = CoupledForcing(times, np.zeros((2, 1)), np.array([[.2], [0.]]), "c" * 64)
    boundaries = empty_boundaries(times)
    mapping = np.array([-1], np.int64)
    args = (net, (lake,), outlets, mapping, forcing, boundaries)
    errors = []
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for name, dt in (("bowl_coarse", .5), ("bowl_fine", .125)):
        result = solve_coupled(*args, config=ChannelConfig(max_dt_seconds=dt))
        save(name, args, result)
        a = result["arrays"]
        expected = reference(net, (lake,), outlets, mapping, forcing, np.zeros(1), np.zeros(1), a["time_seconds"])
        error = float(np.max(np.abs(a["lake_volume_m3"][:, 0] - expected[:, 1]))) / max(1., float(expected[:, 1].max()))
        errors.append(error)
        first = np.flatnonzero(a["lake_volume_m3"][:, 0] >= 2.)[0]
        crossing = np.interp(2., a["lake_volume_m3"][first-1:first+1, 0], a["time_seconds"][first-1:first+1])
        if abs(crossing - 10.) > dt:
            raise AssertionError("first spill differs from exact threshold time")
        cases[name].update(ODE_relative_volume_error=error, exact_spill_crossing_s=10., measured_spill_crossing_s=float(crossing),
                           first_positive_outlet_step_s=float(a["time_seconds"][:-1][np.any(a["lake_outlet_q_m3_s"] > 0., axis=1)][0]))
        axes[0].plot(a["time_seconds"], a["lake_stage_m"][:, 0], label=name)
    if not errors[1] < errors[0] or errors[1] > THRESHOLDS["ODE_relative_volume_error"]:
        raise AssertionError(errors)
    axes[0].axvline(10., color="#c03958", linestyle="--", label="Exact crest crossing: 10 s")
    axes[0].set_title("Analytical bowl: storage before two-outlet spill")
    axes[0].set_ylabel("Stage (m)")

    # Real shared-step upstream -> lake -> downstream event, independently integrated.
    net = channel((-1, -1), bed=[1., 0.])
    lake = LakeStorage(np.array([100, 101], np.int64), np.array([0., .02]), np.array([5., 5.]), 100, 2., "b" * 64, "analytic_finite_bowl")
    outlets = (LakeOutlet(0, 1, .03, 1., "explicit_transfer_weir"),)
    times = np.array([0., 30., 120.])
    forcing = CoupledForcing(times, np.array([[.2, 0.], [0., 0.]]), np.zeros((2, 1)), "c" * 64)
    mapping = np.array([0, -1], np.int64)
    boundaries = empty_boundaries(times)
    args = (net, (lake,), outlets, mapping, forcing, boundaries)
    errors = []
    for name, dt in (("river_lake_river_coarse", .5), ("river_lake_river_fine", .125)):
        result = solve_coupled(*args, config=ChannelConfig(max_dt_seconds=dt))
        save(name, args, result)
        a = result["arrays"]
        expected = reference(net, (lake,), outlets, mapping, forcing, np.zeros(2), np.zeros(1), a["time_seconds"])
        actual = np.column_stack((a["channel_volume_m3"], a["lake_volume_m3"]))
        error = float(np.max(np.abs(actual - expected))) / max(1., float(expected.max()))
        errors.append(error)
        cases[name]["ODE_relative_volume_error"] = error
        np.testing.assert_array_equal(a["channel_boundary_volume_m3"][:, 0], 0.)
        np.testing.assert_allclose(a["lake_donor_q_m3_s"][:, 0], a["channel_q_m3_s"][:, 0], atol=1e-14)
        np.testing.assert_allclose(a["channel_donor_q_m3_s"][:, 1], a["lake_outlet_q_m3_s"][:, 0], atol=1e-14)
        axes[1].plot(a["time_seconds"], a["lake_volume_m3"][:, 0], label=name)
    if not errors[1] < errors[0] or errors[1] > THRESHOLDS["ODE_relative_volume_error"]:
        raise AssertionError(errors)
    axes[1].set_title("River -> lake -> river: shared-step storage")
    axes[1].set_ylabel("Lake volume (m3)")
    for axis in axes:
        axis.set_xlabel("Physical time (s)")
        axis.legend(fontsize=8)
        axis.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(output / "analytical-lake-coupling.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("Independent analytical M3/M4 references accepted; selecting TD basin", flush=True)

    source_dir = ROOT / "verification/td-river-milestones/td256-20261008-01"
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    pin = manifest["artifacts"]["product"]
    source = load_diagnostic_product(source_dir / pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    hierarchy = load_basin_hierarchy(HIERARCHY_PATH, expected_sha256=HIERARCHY_SHA, expected_identity=HIERARCHY_ID)
    ha, sa = hierarchy["arrays"], source["arrays"]
    np.testing.assert_array_equal(ha["height_m"], sa["elevation_m"])
    parents = ha["node_parent"]
    leaves = np.setdiff1d(np.arange(len(parents)), parents[parents >= 0])
    bed, owner = ha["height_m"].ravel(), ha["cell_owner"].ravel()
    rec = sa["graph_receiver"]
    node_ids = np.arange(len(rec))
    selected = None
    for node in leaves:
        support = np.flatnonzero(owner == node)
        if not 4 <= len(support) <= 100 or not np.isfinite(ha["node_upper_m"][node]) or ha["node_unknown_contact"][node] or ha["node_open_boundary"][node]:
            continue
        seed = int(support[np.argmin(bed[support])])
        intake = np.flatnonzero((rec >= 0) & np.isin(rec, support) & ~np.isin(node_ids, support) & (sa["graph_edge_slope"] > 0.))
        if sa["graph_outlet_kind"][seed] == "lake_preserved" and len(intake):
            selected = (int(node), support, seed, int(intake[0]))
            break
    if selected is None:
        raise AssertionError("no unambiguous D4 leaf / D8 terminal with incoming channel")
    node, support, seed, incoming = selected
    path = [incoming]
    while len(path) < 16:
        donors = np.flatnonzero((rec == path[0]) & (sa["graph_edge_slope"] > 0.) & ~np.isin(node_ids, support))
        if not len(donors):
            break
        path.insert(0, int(donors[0]))
    path = np.asarray(path, np.int64)
    crest = float(ha["node_upper_m"][node])
    lake = LakeStorage(support.astype(np.int64), bed[support].copy(), np.full(len(support), 900.), seed, crest + .05,
                       source["identity_sha256"], "D4_leaf_original_support; above_first_saddle_isolated_vertical_wall_pool; receiving_basin_excluded")
    for level in np.r_[np.unique(bed[support]), crest]:
        wet = support[bed[support] < level]
        if not connected_wet(wet, seed, ha["height_m"].shape[1]):
            raise AssertionError("TD leaf sublevel footprint disconnected")
        np.testing.assert_allclose(lake.volume_at_stage(float(level)), basin_volume_at_level(hierarchy, node, float(level)), rtol=1e-10, atol=1e-7)
    n = len(path)
    net = channel(np.r_[np.arange(1, n), -1], lengths=sa["graph_edge_length_m"][path], bed=bed[path],
                  slopes=sa["graph_edge_slope"][path], source=source["identity_sha256"])
    mapping = np.full(n, -1, np.int64)
    mapping[-1] = 0
    times = sa["time_seconds"]
    lake_local = sa["local_q_m3_s"].reshape(3, -1)[:, support].sum(axis=1)[:, None]
    forcing = CoupledForcing(times.copy(), sa["local_q_m3_s"].reshape(3, -1)[:, path].copy(), lake_local.copy(), source["identity_sha256"])
    boundaries = empty_boundaries(times)
    outlets = (LakeOutlet(0, -1, crest, 2., "explicit_C2_scenario_at_D4_first_saddle_exports_to_excluded_receiving_basin_not_ocean"),)
    initial_lake = np.array([max(0., lake.volume_at_stage(crest) - .1)])
    args = (net, (lake,), outlets, mapping, forcing, boundaries)
    results = []
    for name, dt in (("td_coarse", 2.), ("td_fine", .5)):
        result = solve_coupled(*args, initial_lake_volume_m3=initial_lake, config=ChannelConfig(max_dt_seconds=dt))
        save(name, args, result)
        results.append(result)
    coarse, fine = [r["arrays"] for r in results]
    diff_c = np.column_stack([np.interp(coarse["time_seconds"], fine["time_seconds"], fine["channel_stage_m"][:, i]) - coarse["channel_stage_m"][:, i] for i in range(n)])
    diff_l = np.interp(coarse["time_seconds"], fine["time_seconds"], fine["lake_stage_m"][:, 0]) - coarse["lake_stage_m"][:, 0]
    difference = max(float(np.max(np.abs(diff_c))), float(np.max(np.abs(diff_l))))
    aout, bout = cases["td_coarse"]["signed_external_volume_m3"], cases["td_fine"]["signed_external_volume_m3"]
    flow_error = abs(aout - bout) / max(abs(bout), 1e-12)
    if difference > THRESHOLDS["depth_refinement_m"] or flow_error > THRESHOLDS["integrated_outflow_refinement_relative"]:
        raise AssertionError((difference, flow_error))
    final_stage = float(fine["lake_stage_m"][-1, 0])
    wet = lake.wet_mask_at_stage(final_stage)
    depth = lake.depth_at_stage(final_stage)
    geometry_arrays = {"source_cell_ids": support, "source_bed_m": bed[support], "cell_area_m2": np.full(len(support), 900.),
                       "wet_mask": wet, "depth_m": depth, "channel_source_cell_ids": path,
                       "contribution_mask": sa["graph_lake_id"] == seed}
    # Evidence only; geometry follows saved finite source support, not whole contribution area.
    from terrain_pipeline.common_infra import identity, save_bundle
    geometry_meta = {"schema": "td-m4-wet-footprint-v1", "final_stage_m": final_stage, "d4_leaf_node": node,
                     "d8_terminal_cell": seed, "first_saddle_m": crest, "footprint_policy": lake.footprint_policy,
                     "source_product_identity_sha256": source["identity_sha256"], "hierarchy_identity_sha256": HIERARCHY_ID,
                     "natural_outlet_verified": False, "publishable": False}
    geometry = {"arrays": geometry_arrays, "metadata": geometry_meta, "identity_sha256": identity(geometry_arrays, geometry_meta)}
    def validate_footprint(bundle):
        arrays, metadata = bundle["arrays"], bundle["metadata"]
        if (bundle["identity_sha256"] != identity(arrays, metadata) or metadata != geometry_meta
                or set(arrays) != set(geometry_arrays)):
            raise ValueError("wet footprint identity/schema mismatch")
        np.testing.assert_array_equal(arrays["source_cell_ids"], lake.cell_ids)
        np.testing.assert_array_equal(arrays["source_bed_m"], lake.bed_elevation_m)
        np.testing.assert_array_equal(arrays["wet_mask"], arrays["source_bed_m"] < metadata["final_stage_m"])
        np.testing.assert_array_equal(arrays["cell_area_m2"], lake.cell_area_m2)
        np.testing.assert_allclose(arrays["depth_m"], np.maximum(metadata["final_stage_m"] - arrays["source_bed_m"], 0.), rtol=0., atol=1e-10)
        np.testing.assert_allclose(np.sum(arrays["depth_m"] * arrays["cell_area_m2"]), fine["lake_volume_m3"][-1, 0], rtol=1e-10, atol=1e-7)
    save_bundle(output / "td-wet-footprint.npz", geometry, validator=validate_footprint)
    geometry_pin = {"path": "td-wet-footprint.npz", "sha256": file_sha256(output / "td-wet-footprint.npz"), "identity_sha256": geometry["identity_sha256"]}
    selection = {"source_product_path": str(source_dir / pin["path"]), "source_product": pin,
                 "source_path": manifest["source_path"], "source_sha256": manifest["source_sha256"],
                 "hierarchy_path": str(HIERARCHY_PATH), "hierarchy_sha256": HIERARCHY_SHA, "hierarchy_identity_sha256": HIERARCHY_ID,
                 "d4_leaf_node": node, "d8_terminal_cell": seed, "d8_graph_identity_sha256": source["metadata"]["routing_identity_sha256"],
                 "lake_support_cell_ids": support.tolist(), "channel_source_cell_ids": path.tolist(),
                 "channel_intake_receiver_cell": int(rec[path[-1]]), "crest_stage_m": crest,
                 "initial_lake_volume_m3": float(initial_lake[0]), "preconditioning": "explicit_near_spill_initial_storage_not_created_by_this_storm",
                 "once_only_input_policy": "disjoint_selected_channel_cells_and_D4_leaf_cells_local_release_only; all_other_sources_excluded",
                 "above_saddle_policy": lake.footprint_policy, "max_all_history_stage_difference_m": difference,
                 "integrated_outflow_relative_difference": flow_error,
                 "sub_saddle_wet_connectivity_verified": True, "wet_footprint": geometry_pin}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    rows, cols = divmod(support, ha["height_m"].shape[1])
    axes[0].scatter(cols, rows, c=depth, cmap="Blues", s=140, marker="s")
    axes[0].scatter(path % ha["height_m"].shape[1], path // ha["height_m"].shape[1], c="#c53f67", s=10)
    axes[0].invert_yaxis()
    axes[0].set_aspect("equal")
    axes[0].set_title(f"TD D4 leaf {node}: {len(support)} source columns")
    axes[0].set_xlabel("30 m grid column")
    axes[0].set_ylabel("30 m grid row")
    for name, result in zip(("2 s", "0.5 s"), results):
        a = result["arrays"]
        axes[1].plot(a["time_seconds"], a["lake_stage_m"][:, 0] - crest, label=name)
        axes[2].plot(a["time_seconds"], a["lake_volume_m3"][:, 0] - initial_lake[0], label=name)
    axes[1].set_title("Lake stage relative to first saddle")
    axes[1].set_ylabel("Stage minus crest (m)")
    axes[2].set_title("Lake storage change from explicit initial state")
    axes[2].set_ylabel("Volume change (m3)")
    for axis in axes[1:]:
        axis.set_xlabel("Physical time (s)")
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
    fig.suptitle("Bounded real TD M4: original-bed support; above-saddle vertical-wall scenario; no natural lake merger claim")
    fig.tight_layout(rect=(0., 0., 1., .9))
    fig.savefig(output / "td-lake-event.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    report = {"schema": "td-m3-m4-verification-v1", "status": "accepted_bounded_coupling", "thresholds": THRESHOLDS,
              "artifacts": pins, "cases": cases, "td_selection": selection, "elapsed_seconds": time.perf_counter() - started,
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = prepare(args.output)
    except Exception as error:
        if args.output.is_dir() and not (args.output / "rejection.json").exists():
            publish_bytes(args.output / "rejection.json", json.dumps({"status": "rejected", "reason": str(error),
                "error_type": type(error).__name__, "thresholds": THRESHOLDS}, indent=2).encode("utf-8"))
        raise
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
