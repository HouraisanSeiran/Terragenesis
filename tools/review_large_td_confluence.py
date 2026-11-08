"""Regenerate and independently audit the pinned large TD routing candidate."""
import argparse
import html
import json
import os
from pathlib import Path
import sys
import time

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import checked_archive, file_sha256, identity

SOURCE_SHA = "b4855b0631361415d14d199d3c5eb2ea60921eb4c8a6787b22b67dfc4b6dd9ee"
SQUARE_REFERENCE_SHA = "311d7263d1aa832caef197304fcb4650914a791cf844d9a69820d171ea465576"
THRESHOLD = 1_000_000.
ELEVATION_LIMITS = [0.6085212230682373, 536.1844482421875]


def peak_memory_bytes():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
            ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
             "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.PeakWorkingSetSize)


def load_archive(path, expected_sha256=None):
    if expected_sha256 is not None and file_sha256(path) != expected_sha256:
        raise ValueError("archive source digest differs")
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        arrays = {key: archive[key] for key in archive.files if key not in
            ("metadata_json", "outlet_kind", "owner_conflict_source_ids", "unclosed_terminal_ids")}
    return arrays, metadata


def topology(receiver):
    """Array queue avoids a Python object for each native cell."""
    rec = np.asarray(receiver).ravel()
    n = rec.size
    if rec.dtype.kind not in "iu" or np.any(rec < -1) or np.any(rec >= n):
        raise ValueError("receiver must use valid integer native IDs or -1")
    sources = np.flatnonzero(rec >= 0)
    donors = np.bincount(rec[sources], minlength=n).astype(np.int32)
    queue = np.empty(n, np.int64)
    roots = np.flatnonzero(donors == 0)
    queue[:roots.size] = roots
    head, tail = 0, roots.size
    while head < tail:
        target = rec[queue[head]]
        head += 1
        if target >= 0:
            donors[target] -= 1
            if donors[target] == 0:
                queue[tail] = target
                tail += 1
    return queue[:tail], n - tail


def accumulate(receiver, order, local):
    rec = np.asarray(receiver).ravel()
    result = np.asarray(local, np.float64).ravel().copy()
    for cell in order:
        target = rec[cell]
        if target >= 0:
            result[target] += result[cell]
    return result


def strahler(receiver, order, selected):
    rec = np.asarray(receiver).ravel()
    rank = np.zeros(rec.size, np.int16)
    highest = np.zeros(rec.size, np.int16)
    equal_count = np.zeros(rec.size, np.int8)
    for cell in order:
        if not selected[cell]:
            continue
        rank[cell] = max(1, highest[cell] + (equal_count[cell] >= 2))
        target = rec[cell]
        if target >= 0 and selected[target]:
            if rank[cell] > highest[target]:
                highest[target], equal_count[target] = rank[cell], 1
            elif rank[cell] == highest[target]:
                equal_count[target] = min(2, equal_count[target] + 1)
    return rank


def cold_audit(arrays, metadata):
    h = arrays["original_td_m"]
    rec = arrays["receiver"].ravel()
    sources = np.flatnonzero(rec >= 0)
    target = rec[sources]
    order, cycle_cells = topology(rec)
    row_delta = np.abs(target // h.shape[1] - sources // h.shape[1])
    col_delta = np.abs(target % h.shape[1] - sources % h.shape[1])
    local_failures = int(np.sum((row_delta > 1) | (col_delta > 1) | ((row_delta + col_delta) == 0)))
    saved_order = arrays.get("topological_order")
    order_valid = False
    if saved_order is not None and saved_order.size == rec.size and np.array_equal(np.sort(saved_order), np.arange(rec.size)):
        position = np.empty(rec.size, np.int64)
        position[saved_order] = np.arange(rec.size)
        order_valid = bool(np.all(position[sources] < position[target]))
    area = arrays["contributing_area_m2"].ravel()
    selected = area >= THRESHOLD
    selected_sources = sources[selected[sources]]
    incoming = np.bincount(rec[selected_sources], minlength=rec.size)
    confluences = np.flatnonzero(incoming >= 2)
    terminals = np.flatnonzero((rec < 0) & (incoming > 0))
    owner = arrays["frozen_owner_domain_id"].ravel()
    conflict = (owner[sources] >= 0) & (owner[target] != owner[sources]) & (owner[target] != -1)
    strict_conflict = owner[target] != owner[sources]
    spacing = metadata["spacing_m"]
    def residual(values, local):
        expected = np.asarray(local).ravel() + np.bincount(target, weights=values[sources], minlength=rec.size)
        return float(np.max(np.abs(values - expected)))
    q = arrays.get("routed_q_m3_s")
    q_residual = residual(q.ravel(), arrays["local_q_m3_s"]) if q is not None else None
    fill = arrays.get("working_raise_m", np.zeros(h.shape))
    raw_uphill = h.ravel()[target] - h.ravel()[sources]
    statuses = arrays.get("terminal_status")
    if statuses is None:
        statuses = np.full(rec.size, 1, dtype=np.uint8)
        edge = np.zeros(h.shape, bool)
        edge[[0, -1], :] = True
        edge[:, [0, -1]] = True
        statuses[edge.ravel()] = 2
    codes = metadata.get("routing", {}).get("terminal_status_codes", {})
    if not codes:
        codes = {"original_raw_depression": 1, "unknown_perimeter": 2}
    code_names = {int(code): name for name, code in codes.items()}
    def status_name(value):
        return code_names.get(int(value), str(value)) if statuses.dtype.kind in "iu" else str(value)
    kinds, counts = np.unique(statuses.ravel()[terminals], return_counts=True)
    all_terminals = np.flatnonzero(rec < 0)
    all_kinds, all_counts = np.unique(statuses.ravel()[all_terminals], return_counts=True)
    roots = np.flatnonzero(selected & (rec >= 0) & (incoming == 0))
    end = np.arange(rec.size, dtype=np.int64)
    length = np.zeros(rec.size, np.float64)
    for cell in order:
        downstream = rec[cell]
        if downstream >= 0 and selected[cell]:
            step = spacing * np.hypot(downstream % h.shape[1]-cell % h.shape[1], downstream // h.shape[1]-cell // h.shape[1])
            length[downstream] = max(length[downstream], length[cell] + step)
    for cell in order[::-1]:
        if rec[cell] >= 0:
            end[cell] = end[rec[cell]]
    component_sources = np.bincount(end[roots], minlength=rec.size)
    perimeter = np.zeros(h.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    perimeter = perimeter.ravel()
    deep_code = codes.get("unresolved_deep_depression")
    is_deep = statuses.ravel() == deep_code if deep_code is not None else np.zeros(rec.size, bool)
    domain_codes = [int(value) for name, value in codes.items() if "domain_boundary" in name]
    internal_domain_ports = all_terminals[~perimeter[all_terminals] & np.isin(statuses.ravel()[all_terminals], domain_codes)]
    policy = metadata.get("planning_policy", "frozen-owner-bounded")
    report = {
        "cycle_cell_count": cycle_cells, "nonlocal_or_self_edge_count": local_failures,
        "saved_topological_order_valid": order_valid,
        "area_accumulation_max_residual_m2": residual(area, np.full(rec.size, spacing ** 2)),
        "q_accumulation_max_residual_m3_s": q_residual,
        "selected_downstream_threshold_closure_failures": int(np.sum(~selected[rec[selected_sources]])),
        "shared_confluence_node_count": int(confluences.size), "selected_terminal_count": int(terminals.size),
        "visible_network_semantics": "edges whose source area is at least 1km2; terminals must receive at least one selected edge",
        "isolated_above_threshold_terminal_count": int(np.sum((rec < 0) & selected & (incoming == 0))),
        "selected_source_count": int(roots.size), "single_source_component_count": int(np.sum(component_sources == 1)),
        "longest_continuous_selected_path_km": float(length.max(initial=0) / 1000.),
        "maximum_terminal_catchment_km2": float(area[all_terminals].max(initial=0) / 1e6),
        "selected_terminal_owner_counts": {str(int(k)): int(v) for k, v in zip(*np.unique(owner[terminals], return_counts=True))},
        "selected_terminal_classification": {status_name(k): int(v) for k, v in zip(kinds, counts)},
        "all_terminal_count": int(all_terminals.size),
        "all_terminal_classification": {status_name(k): int(v) for k, v in zip(all_kinds, all_counts)},
        "frozen_owner_conflicts_existing_convention": int(conflict.sum()),
        "strict_owner_change_edge_count": int(strict_conflict.sum()),
        "selected_frozen_owner_conflicts": int(np.sum(conflict & selected[sources])),
        "selected_strict_owner_change_edge_count": int(np.sum(strict_conflict & selected[sources])),
        "maximum_fill_m": float(fill.max(initial=0)), "fill_work_volume_m3": float(fill.sum() * spacing ** 2),
        "fill_footprint_m2": float(np.sum(fill > 1e-8) * spacing ** 2),
        "raw_uphill_edge_count": int(np.sum(raw_uphill > 1e-8)),
        "maximum_raw_uphill_edge_m": float(raw_uphill.max(initial=0)),
        "selected_raw_uphill_edge_count": int(np.sum((raw_uphill > 1e-8) & selected[sources])),
        "terminal_area_sum_m2": float(area[all_terminals].sum()),
        "terminal_q_sum_m3_s": float(q.ravel()[all_terminals].sum()) if q is not None else None,
        "local_q_sum_m3_s": float(arrays["local_q_m3_s"].sum()) if q is not None else None,
        "actual_bed_certified": False, "naturalness_certified": False,
        "fill_semantics": "routing work surface only; not deposited terrain or certified lake level",
        "terminal_semantics": "deep depressions and domain/perimeter exits remain unresolved; no legal lake/sea inferred",
        "planning_policy": policy,
        "internal_artificial_domain_port_count": int(internal_domain_ports.size),
        "selected_internal_artificial_domain_port_count": int(np.sum(np.isin(terminals, internal_domain_ports))),
        "nondeep_terminal_outside_actual_perimeter_count": int(np.sum(~is_deep[all_terminals] & ~perimeter[all_terminals])),
        "selected_actual_perimeter_terminal_count": int(np.sum(perimeter[terminals])),
        "reference_owner_semantics": "original coarse frozen labels retained as reference; crossings are incompatibility diagnostics",
    }
    if "working_height_m" in arrays:
        work = arrays["working_height_m"].ravel()
        cap = float(metadata["routing"].get("max_fill_depth_m", metadata.get("max_fill_depth_m", 4.)))
        expected_sources = sources[selected[sources]]
        expected_strahler = strahler(rec, order, selected) if not cycle_cells else None
        gates = {
            "acyclic": cycle_cells == 0, "local_d8": local_failures == 0, "saved_order": order_valid,
            "finite_nonnegative_area": bool(np.isfinite(area).all() and np.all(area >= 0)),
            "area_residual": report["area_accumulation_max_residual_m2"] <= 1e-6,
            "area_terminal_total": abs(report["terminal_area_sum_m2"]-rec.size*spacing**2) <= 1e-6,
            "finite_nonnegative_q": bool(np.isfinite(q).all() and np.all(q >= 0)),
            "finite_nonnegative_local_q": bool(np.isfinite(arrays["local_q_m3_s"]).all() and np.all(arrays["local_q_m3_s"] >= 0)),
            "q_residual": q_residual <= 1e-10,
            "q_terminal_total": abs(report["terminal_q_sum_m3_s"]-report["local_q_sum_m3_s"]) <= 1e-8,
            "work_downhill": bool(np.all(work[target] <= work[sources]+1e-8)),
            "fill_finite_and_bounded": bool(np.isfinite(fill).all() and fill.min() >= -1e-8 and fill.max() <= cap+1e-8),
            "fill_equals_work_minus_raw": bool(np.allclose(fill.ravel(), work-h.ravel(), rtol=0., atol=1e-8)),
            "selection_matches_threshold": bool(np.array_equal(arrays["selected_edge_source_ids"], expected_sources)
                and np.array_equal(arrays["selected_edge_target_ids"], rec[expected_sources])),
            "downstream_threshold_closure": report["selected_downstream_threshold_closure_failures"] == 0,
            "strahler_matches_independent_recalculation": bool(expected_strahler is not None
                and np.array_equal(arrays["strahler_order"], expected_strahler)),
        }
        if policy == "native-source-replan":
            native_owner = arrays["native_planning_owner_domain_id"].ravel()
            native_changes = native_owner[sources] != native_owner[target]
            report.update(native_planning_identity_sha256=metadata["native_planning_identity_sha256"],
                native_planning_owner_change_edge_count=int(native_changes.sum()),
                native_planning_owner_semantics="terminal-catchment construction consistency only; natural divides and legal coast outlets unverified",
                terminal_semantics="actual perimeter is a clipped TD support window with unknown continuation, not a sea mouth; internal deep depressions unresolved")
            gates.update(no_artificial_internal_domain_ports=internal_domain_ports.size == 0,
                nondeep_terminals_on_actual_perimeter=report["nondeep_terminal_outside_actual_perimeter_count"] == 0,
                derived_owner_edge_construction_consistency=not native_changes.any(),
                derived_owner_covers_support=bool(native_owner.size == rec.size and np.all(native_owner >= 0)),
                derived_owner_unique_per_terminal=np.unique(native_owner[all_terminals]).size == all_terminals.size,
                derived_owner_matches_actual_terminal_catchment=bool(np.array_equal(native_owner, end)),
                native_planning_identity_matches_saved_arrays=metadata["native_planning_identity_sha256"] == identity(
                    {"native_planning_owner_domain_id": arrays["native_planning_owner_domain_id"]}, metadata["native_planning_metadata"]),
                terminal_status_known_and_noninterior=bool(np.all(np.isin(statuses.ravel()[all_terminals],
                    [int(value) for name, value in codes.items() if name != "interior"]))))
        else:
            gates["same_owner_every_edge"] = not strict_conflict.any()
        report["boundary_gates"] = {key: gates[key] for key in
            ("no_artificial_internal_domain_ports", "nondeep_terminals_on_actual_perimeter", "terminal_status_known_and_noninterior") if key in gates}
        report["derived_owner_construction_gates"] = {key: gates[key] for key in
            ("derived_owner_edge_construction_consistency", "derived_owner_covers_support",
             "derived_owner_unique_per_terminal", "derived_owner_matches_actual_terminal_catchment") if key in gates}
        report["gates"] = gates
        report["topology_status"] = "passed_routing_candidate_checks" if all(gates.values()) else "failed_routing_candidate_checks"
    return report, confluences


def noise_rain(metadata, shape):
    from terrain_pipeline.climate_forcing import grid_rainfall
    rain = np.empty(shape, np.float64)
    for start in range(0, shape[0], 128):
        count = min(128, shape[0] - start)
        origin = [metadata["origin_xz_m"][0], metadata["origin_xz_m"][1] + start * metadata["spacing_m"]]
        forcing, provenance = grid_rainfall(int(metadata["seed"]), origin_xz_m=origin,
            shape_zx=(count, shape[1]), spacing_m=metadata["spacing_m"], time_edges_s=[0., 900.], spatial_subsamples=2)
        rain[start:start + count] = forcing.rain_mm_h[0]
    provenance.update(origin_xz_m=metadata["origin_xz_m"], shape_zx=list(shape), stripe_rows=128,
        runoff_coefficient=.5, scenario="synthetic [0,900]s rain with fixed runoff coefficient; not annual water or flood prediction")
    provenance["source_identity_sha256"] = identity({"rain_mm_h": rain}, provenance)
    return rain, provenance


def square_wall_port_review(reference, reference_metadata, candidate, candidate_metadata):
    """Inspect saved 02 artificial ports and nearby actual new routes."""
    h = candidate["original_td_m"]
    old_rec = reference["receiver"].ravel()
    old_selected = reference["selected_edge_source_ids"]
    old_incoming = np.bincount(old_rec[old_selected], minlength=old_rec.size)
    codes = reference_metadata["routing"]["terminal_status_codes"]
    domain_codes = [int(code) for name, code in codes.items() if "domain_boundary" in name]
    perimeter = np.zeros(h.shape, bool)
    perimeter[[0,-1],:] = True
    perimeter[:,[0,-1]] = True
    ports = np.flatnonzero((old_rec < 0) & (old_incoming > 0) & ~perimeter.ravel()
        & np.isin(reference["terminal_status"].ravel(), domain_codes))
    rec = candidate["receiver"].ravel()
    ids = candidate["selected_edge_source_ids"]
    downstream_length = np.zeros(rec.size, np.float64)
    spacing = candidate_metadata["spacing_m"]
    for cell in candidate["topological_order"][::-1]:
        target = rec[cell]
        if target >= 0:
            downstream_length[cell] = downstream_length[target] + spacing * np.hypot(
                target // h.shape[1]-cell // h.shape[1], target % h.shape[1]-cell % h.shape[1])
    owner = candidate["frozen_owner_domain_id"].ravel()
    crossing = owner[ids] != owner[rec[ids]]
    rows, columns = ids // h.shape[1], ids % h.shape[1]
    records = []
    for port in ports:
        distance = spacing * np.hypot(rows-port // h.shape[1], columns-port % h.shape[1])
        nearby = np.flatnonzero(distance <= 300.+1e-8)
        nearest = nearby[np.argmin(distance[nearby])] if nearby.size else None
        records.append({"former_port_id": int(port), "former_port_row_column": [int(port // h.shape[1]), int(port % h.shape[1])],
            "same_pixel_has_receiver": bool(rec[port] >= 0), "new_selected_source_within_300m_count": int(nearby.size),
            "new_selected_old_reference_crossing_within_300m_count": int(np.sum(crossing[nearby])),
            "nearest_new_selected_source_id": int(ids[nearest]) if nearest is not None else None,
            "nearest_new_selected_displacement_m": float(distance[nearest]) if nearest is not None else None,
            "nearest_new_selected_actual_downstream_length_m": float(downstream_length[ids[nearest]]) if nearest is not None else None})
    return ports, {"method": "Former visible artificial internal domain ports from pinned 02; inspect saved new receivers and selected routes within 300m. Pixel coincidence is diagnostic, not required. Downstream length follows actual new receiver edges, including candidate water surfaces.",
        "former_visible_internal_domain_port_count": int(ports.size),
        "former_ports_same_pixel_has_receiver_count": int(np.sum(rec[ports] >= 0)),
        "former_ports_with_new_selected_route_within_300m_count": sum(record["new_selected_source_within_300m_count"] > 0 for record in records),
        "former_ports_with_new_reference_crossing_within_300m_count": sum(record["new_selected_old_reference_crossing_within_300m_count"] > 0 for record in records),
        "nearby_route_records": records, "comparison_is_naturalness_certification": False}


def generate(source, source_metadata, plan, max_fill_depth_m, planning_policy="frozen-owner-bounded"):
    from terrain_pipeline.common_infra import TerrainGrid, BoundaryGrid
    from terrain_pipeline.channel_geometry import bounded_confluence_candidate
    h = source["original_td_m"]
    m = source_metadata
    terrain = TerrainGrid(h, np.ones(h.shape, bool), *m["origin_xz_m"], m["spacing_m"], m["spacing_m"],
        "generated_terrain", m["source_identity"], m["source_identity"], generation_seed=int(m["seed"]))
    kind = np.full(h.shape, "interior", dtype="U24")
    kind[[0, -1], :] = "unknown_boundary"
    kind[:, [0, -1]] = "unknown_boundary"
    boundary = BoundaryGrid(kind, np.zeros(h.shape, bool), "unclosed-TD-perimeter", identity({}, {"perimeter": "unknown"}))
    rain, rain_metadata = noise_rain(m, h.shape)
    local_q = rain * m["spacing_m"] ** 2 / 3_600_000. * .5
    if planning_policy == "native-source-replan":
        from terrain_pipeline.surface_rivers.metric_td_native_planning import native_planning_candidate
        graph, work, routing_metadata, extra = native_planning_candidate(terrain, boundary,
            source["frozen_owner_domain_id"], baseline_receiver=source["receiver"], max_fill_depth_m=max_fill_depth_m,
            local_q_m3_s=local_q)
    else:
        graph, work, routing_metadata, extra = bounded_confluence_candidate(terrain, boundary,
            source["frozen_owner_domain_id"], baseline_receiver=source["receiver"], max_fill_depth_m=max_fill_depth_m,
            local_q_m3_s=local_q)
    rec = graph.receiver.ravel()
    order, cycles = topology(rec)
    if cycles:
        raise ValueError("candidate contains cycles")
    area = accumulate(rec, order, np.full(rec.size, m["spacing_m"] ** 2))
    q = accumulate(rec, order, local_q)
    selected = area >= THRESHOLD
    sources = np.flatnonzero((rec >= 0) & selected)
    arrays = {**extra, "original_td_m": h, "receiver": rec, "topological_order": order,
        "working_height_m": work, "working_raise_m": work - h,
        "frozen_owner_domain_id": source["frozen_owner_domain_id"], "contributing_area_m2": area,
        "rain_mm_h": rain, "local_q_m3_s": local_q, "routed_q_m3_s": q,
        "selected_edge_source_ids": sources, "selected_edge_target_ids": rec[sources],
        "strahler_order": strahler(rec, order, selected),
        "river_width_m": np.maximum(1., 4. * np.sqrt(q))}
    metadata = {**m, "algorithm": routing_metadata.get("algorithm", routing_metadata["schema"]), "routing": routing_metadata,
        "routing_identity": graph.identity_sha256, "rainfall": rain_metadata,
        "selection_minimum_contributing_area_m2": THRESHOLD,
        "width_semantics": "visual candidate width=max(1m,4*sqrt(Q)); not solved hydraulic geometry",
        "bed_solver_run": False, "naturalness_certified": False,
        "resources": {"max_cpu_cores": 2, "numeric_threads": 1, "priority": "BelowNormal"}}
    for stale in ("network_identity", "domain_diagnostics", "bounded_spill", "selected_edge_count", "network_archive", "figures"):
        metadata.pop(stale, None)
    metadata["max_fill_depth_m"] = max_fill_depth_m
    metadata["planning_policy"] = planning_policy
    if planning_policy == "native-source-replan":
        metadata["native_planning_identity_sha256"] = routing_metadata["native_planning_identity_sha256"]
        metadata["frozen_plan_role"] = "old coarse reference only; not enforced as routing walls or watershed acceptance"
        metadata["native_planning_metadata"] = routing_metadata["native_planning_metadata"]
    metadata["width_semantics"] += "; displayed stroke=clip(0.55+0.75*log1p(Q),0.55,3) points, visual exaggeration"
    metadata["network_identity"] = identity(arrays, metadata)
    return arrays, metadata


def render_comparison(old, new, metadata, confluences, output, *, old_metadata=None, fixed_port_ids=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.collections import LineCollection
    from tools.compare_hydrology_projection_naturalness import fixed_hillshade
    h = new["original_td_m"]
    spacing = metadata["spacing_m"]
    ox, oz = metadata["origin_xz_m"]
    extent = np.array([ox-spacing/2, ox+(h.shape[1]-.5)*spacing, oz+(h.shape[0]-.5)*spacing, oz-spacing/2])/1000.
    cmap = LinearSegmentedColormap.from_list("fixed-relief", ["#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32"])
    norm = Normalize(*ELEVATION_LIMITS)
    rgb = np.clip(cmap(norm(h))[..., :3] * (.55 + .65 * fixed_hillshade(h, spacing)[..., None]), 0., 1.)
    def coordinates(ids):
        return np.c_[ox + ids % h.shape[1] * spacing, oz + ids // h.shape[1] * spacing] / 1000.
    def draw(ax, arrays, label, bounds=None):
        ax.imshow(rgb, extent=extent, interpolation="nearest")
        fill = arrays.get("working_raise_m", np.zeros(h.shape)).ravel() > 1e-8
        if fill.any():
            rgba = np.zeros(h.shape + (4,))
            rgba[fill.reshape(h.shape)] = [.1, .8, 1., .7]
            ax.imshow(rgba, extent=extent, interpolation="nearest")
        ids = arrays["selected_edge_source_ids"]
        targets = arrays["receiver"].ravel()[ids]
        dry = ~(fill[ids] | fill[targets])
        lines = np.stack((coordinates(ids[dry]), coordinates(targets[dry])), axis=1)
        q = arrays.get("routed_q_m3_s", arrays["contributing_area_m2"]).ravel()[ids[dry]]
        if "routed_q_m3_s" not in arrays:
            q = q * float(new["local_q_m3_s"].mean()) / spacing ** 2
        width = np.clip(.55 + .75 * np.log1p(q), .55, 3.)
        ax.add_collection(LineCollection(lines, colors="white", linewidths=width+.8, alpha=.9))
        ax.add_collection(LineCollection(lines, colors="#063a6a", linewidths=width, alpha=.95))
        wet_lines = np.stack((coordinates(ids[~dry]), coordinates(targets[~dry])), axis=1)
        ax.add_collection(LineCollection(wet_lines, colors="#063a6a", linewidths=.7, linestyles="dashed", alpha=.75))
        incoming = np.bincount(targets, minlength=h.size)
        terminal_ids = np.flatnonzero((arrays["receiver"].ravel() < 0) & (incoming > 0))
        status = arrays.get("terminal_status")
        if status is None:
            status = np.ones(h.size, np.uint8)
            edge = np.zeros(h.shape, bool); edge[[0,-1],:] = True; edge[:,[0,-1]] = True
            status[edge.ravel()] = 2
        symbols = ["x", "+", "s", "^", "o", "D"]
        for index, value in enumerate(np.unique(status.ravel()[terminal_ids])):
            points = coordinates(terminal_ids[status.ravel()[terminal_ids] == value])
            draw_metadata = metadata if arrays is new else (old_metadata or {})
            codes = draw_metadata.get("routing", {}).get("terminal_status_codes", {})
            names = {int(code): name for name, code in codes.items()}
            label_status = names.get(int(value), "unresolved depression" if value == 1 else "unresolved boundary")
            symbol = ">" if "perimeter" in label_status or "unknown_boundary" in label_status else symbols[index % len(symbols)]
            if symbol == ">":
                label_status = "Clipped window / continuation unknown (not coast)"
            ax.scatter(points[:,0], points[:,1], s=14, marker=symbol,
                c="#f500a0", linewidths=.7, label=label_status)
        if fixed_port_ids is not None and len(fixed_port_ids):
            points = coordinates(fixed_port_ids)
            ax.scatter(points[:,0], points[:,1], s=34, marker="o", facecolors="none",
                edgecolors="#ff971d", linewidths=.9, label="Former square-wall ports (02 reference)")
        ax.plot([], [], color="#063a6a", label="Dry-ground route candidate / Q width")
        ax.plot([], [], color="#19ccee", linewidth=5, label="Fill footprint / water candidate, bed unverified")
        if bounds:
            ax.set_xlim(bounds[0], bounds[1]); ax.set_ylim(bounds[3], bounds[2])
        ax.set(title=label, xlabel="World x east (km)", ylabel="World z south (km)", aspect="equal")
        ax.legend(loc="lower left", fontsize=7)
    maps = []
    for name, bounds in [("comparison-full", None)]:
        fig, axes = plt.subplots(1, 2, figsize=(19, 10), constrained_layout=True)
        draw(axes[0], old, "02 square-wall reference" if fixed_port_ids is not None else "Original / same 1 km2 threshold", bounds)
        draw(axes[1], new, "Native-source replan / work-surface candidate" if fixed_port_ids is not None else "Bounded confluence / work-surface candidate", bounds)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes, label="Original elevation (m), fixed old scale", shrink=.7)
        fig.savefig(output / (name + ".png"), dpi=160); plt.close(fig); maps.append(name + ".png")
    fig, ax = plt.subplots(figsize=(12, 11), constrained_layout=True)
    draw(ax, new, "Full extent / Q width / unresolved terminals")
    fig.savefig(output / "full-region.png", dpi=160); plt.close(fig); maps.append("full-region.png")
    chosen = []
    if fixed_port_ids is not None:
        columns, counts = np.unique(fixed_port_ids % h.shape[1], return_counts=True)
        for column in columns[np.argsort(counts)[::-1]][:3]:
            ports = fixed_port_ids[fixed_port_ids % h.shape[1] == column]
            cell = ports[np.argmax(old["contributing_area_m2"].ravel()[ports])]
            chosen.append(coordinates(np.array([cell]))[0])
    else:
        for cell in confluences[np.argsort(new["routed_q_m3_s"].ravel()[confluences])[::-1]]:
            point = coordinates(np.array([cell]))[0]
            if all(np.linalg.norm(point - prior) > 2. for prior in chosen):
                chosen.append(point)
            if len(chosen) == 3:
                break
    for index, point in enumerate(chosen):
        bounds = [point[0]-1.2, point[0]+1.2, point[1]-1.2, point[1]+1.2]
        fig, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
        draw(axes[0], old, "02 / former internal square-wall ports" if fixed_port_ids is not None else "Original / actual confluence location", bounds)
        draw(axes[1], new, "Native replan / same former port location" if fixed_port_ids is not None else "Candidate / shared receiver confluence", bounds)
        name = f"square-wall-port-{index+1}.png" if fixed_port_ids is not None else f"confluence-{index+1}.png"
        fig.savefig(output / name, dpi=160); plt.close(fig); maps.append(name)
    return maps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "verification/hydrological-planning-domain/large-td-preview-20261014-01/native-routing.npz")
    parser.add_argument("--expected-source-sha256", default=SOURCE_SHA)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-fill-depth-m", type=float, default=4.)
    parser.add_argument("--saved-candidate", type=Path)
    parser.add_argument("--planning-policy", choices=("frozen-owner-bounded", "native-source-replan"), default="frozen-owner-bounded")
    parser.add_argument("--comparison-candidate", type=Path, help="Pinned 02 saved archive for square-wall comparison")
    args = parser.parse_args()
    if args.planning_policy == "native-source-replan" and args.comparison_candidate is None:
        parser.error("native-source-replan requires the pinned 02 --comparison-candidate")
    from tools.prepare_hydrology_v5_lake import limit_resources
    from terrain_pipeline.hydrology_planning import load_plan
    limit_resources()
    start = time.perf_counter()
    old, old_metadata = load_archive(args.source, args.expected_source_sha256)
    pin = old_metadata["frozen_plan"]
    if file_sha256(pin["path"]) != pin["sha256"]:
        raise ValueError("frozen plan digest differs")
    plan = load_plan(pin["path"])
    if plan["identity_sha256"] != pin["identity"] or int(plan["seed"]) != int(old_metadata["seed"]):
        raise ValueError("frozen plan identity or seed differs")
    from tools.render_hydrology_large_preview import load_core_mosaic
    records = old_metadata["tile_sources"]
    raw, raw_metadata = load_core_mosaic(Path(records[0]["path"]).parent, int(old_metadata["seed"]), records[0]["tile_xz"])
    if not np.array_equal(raw, old["original_td_m"]) or raw_metadata["source_identity"] != old_metadata["source_identity"]:
        raise ValueError("original archive differs from pinned native source tiles")
    x = old_metadata["origin_xz_m"][0] + np.arange(raw.shape[1]) * old_metadata["spacing_m"]
    z = old_metadata["origin_xz_m"][1] + np.arange(raw.shape[0]) * old_metadata["spacing_m"]
    cx = np.rint((x-plan["origin_xz_m"][0])/plan["spacing_m"]).astype(int)
    cz = np.rint((z-plan["origin_xz_m"][1])/plan["spacing_m"]).astype(int)
    owner = plan["owner_domain_id"][np.ix_(cz, cx)]
    if not np.array_equal(owner, old["frozen_owner_domain_id"]):
        raise ValueError("original frozen owner differs from plan")
    if args.saved_candidate:
        arrays, metadata = load_archive(args.saved_candidate)
        if metadata.get("planning_policy", "frozen-owner-bounded") != args.planning_policy:
            raise ValueError("saved candidate planning policy differs from explicit CLI policy")
    else:
        arrays, metadata = generate(old, old_metadata, plan, args.max_fill_depth_m, args.planning_policy)
        metadata["routing_parent"] = {"path": str(args.source.resolve()), "sha256": args.expected_source_sha256}
        metadata["resources"]["generation_wall_seconds"] = time.perf_counter()-start
        metadata["resources"]["generation_peak_working_set_bytes"] = peak_memory_bytes()
    if not np.array_equal(arrays["original_td_m"], raw) or not np.array_equal(arrays["frozen_owner_domain_id"], owner):
        raise ValueError("candidate source elevation or owner changed")
    args.output.mkdir(parents=True, exist_ok=False)
    if args.saved_candidate:
        archive_path = args.saved_candidate.resolve()
        cold, cold_metadata = arrays, metadata
        del arrays, raw, owner, plan
    else:
        archive_path = args.output / "native-routing.npz"
        with archive_path.open("xb") as stream:
            np.savez_compressed(stream, **arrays, metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
        del arrays, raw, owner, plan
        cold, cold_metadata = load_archive(archive_path)
    cold_source_equal = np.array_equal(cold["original_td_m"], old["original_td_m"])
    cold_owner_equal = np.array_equal(cold["frozen_owner_domain_id"], old["frozen_owner_domain_id"])
    cold_provenance_equal = all(cold_metadata.get(key) == old_metadata.get(key) for key in
        ("seed", "source_identity", "origin_xz_m", "spacing_m", "shape", "frozen_plan", "tile_sources"))
    report, confluences = cold_audit(cold, cold_metadata)
    baseline, _ = cold_audit(old, old_metadata)
    report.update(schema="large-td-confluence-cold-audit-v1", candidate_path=str(archive_path.resolve()), candidate_sha256=file_sha256(archive_path),
        parent_sha256=args.expected_source_sha256, source_elevation_pointwise_equal=cold_source_equal, reference_owner_unchanged=cold_owner_equal,
        frozen_plan=pin, baseline=baseline, historical_reference={"confluence_count": 31, "selected_terminal_count": 170},
        actual_bed_status="unverified", naturalness_status="unverified",
        review_only=bool(args.saved_candidate))
    if args.comparison_candidate:
        comparison, comparison_metadata = load_archive(args.comparison_candidate, SQUARE_REFERENCE_SHA)
        if not np.array_equal(comparison["original_td_m"], old["original_td_m"]) or any(
                comparison_metadata.get(key) != old_metadata.get(key) for key in
                ("seed", "source_identity", "origin_xz_m", "spacing_m", "frozen_plan")):
            raise ValueError("square-wall comparison does not use the same pinned terrain/reference")
        comparison_audit, _ = cold_audit(comparison, comparison_metadata)
        fixed_ports, wall_review = square_wall_port_review(comparison, comparison_metadata, cold, cold_metadata)
        report["square_wall_comparison"] = {"candidate_path": str(args.comparison_candidate.resolve()),
            "candidate_sha256": SQUARE_REFERENCE_SHA, "audit": comparison_audit, **wall_review}
        figures = render_comparison(comparison, cold, cold_metadata, confluences, args.output,
            old_metadata=comparison_metadata, fixed_port_ids=fixed_ports)
        del comparison
    else:
        if args.planning_policy == "native-source-replan":
            raise ValueError("native-source replan review requires explicit pinned --comparison-candidate 02 archive")
        figures = render_comparison(old, cold, cold_metadata, confluences, args.output, old_metadata=old_metadata)
    report["figures"] = figures
    report["reference_owner_unchanged"] = cold_owner_equal
    report["source_gates"] = {"source_elevation_pointwise_equal": cold_source_equal, "reference_owner_unchanged": cold_owner_equal,
        "source_and_reference_plan_provenance_equal": cold_provenance_equal}
    report["planning_gates"] = {"explicit_policy_matches_saved_policy": cold_metadata.get("planning_policy", "frozen-owner-bounded") == args.planning_policy}
    if args.planning_policy == "native-source-replan":
        report["planning_gates"]["native_planning_identity_matches_saved_arrays"] = report["gates"]["native_planning_identity_matches_saved_arrays"]
    report["gates"].update(report["source_gates"], **report["planning_gates"])
    report["topology_status"] = "passed_routing_candidate_checks" if all(report["gates"].values()) else "failed_routing_candidate_checks"
    report["resources"] = {**cold_metadata["resources"], "review_total_wall_seconds": time.perf_counter()-start,
        "review_peak_working_set_bytes": peak_memory_bytes()}
    report["elevation_limits_m"] = ELEVATION_LIMITS
    visible_nodes = np.zeros(cold["receiver"].size, bool)
    visible_nodes[cold["selected_edge_source_ids"]] = True
    visible_nodes[cold["selected_edge_target_ids"]] = True
    report["strahler_order_counts"] = dict(zip(*[a.tolist() for a in np.unique(cold["strahler_order"][visible_nodes], return_counts=True)]))
    (args.output / "cold-audit.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    content = "<!doctype html><meta charset='utf-8'><title>同源大图汇流验收</title><style>body{font:16px system-ui;background:#f5f7fa;color:#202830;margin:24px}main{max-width:1500px;margin:auto}img{width:100%;height:auto}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #bbb;text-align:left}</style><main><h1>同源大图汇流验收</h1><p>38.4公里范围；原始高程与冻结域计划保持一致。地形蓝色代表低高程，并非海洋。青色为填高工作面/水体候选，穿越候选水面的路线用虚线表示。粉色符号按不同原因标记尚未解决的终点。实际河床、水位与自然度尚未验收。</p><p>流量采用[0,900]秒合成噪波降雨和0.5固定径流系数，不代表全年水量或洪水预测。河宽与绘图线宽仅为可视情景及放大显示。</p>"
    if args.planning_policy == "native-source-replan":
        content = content.replace("原始高程与冻结域计划保持一致。", "原始地形不变；旧粗域仅作参考；已在固定支持范围重新生成TD汇水规划候选。")
        content += "<p>橙色空心圆固定标出第二版原人工域端口；放大图采用同一位置对照。图幅外端点为窗口裁剪，域外去向未知，不能视为合法入海口。新归属的沿边一致性来自终点汇水构造，并不认证自然分水岭、完整流域或长期独立性。</p>"
    gate_labels = {"source_elevation_pointwise_equal": "原高程逐点相同", "reference_owner_unchanged": "旧参考标签未修改",
        "source_and_reference_plan_provenance_equal": "来源与旧参考计划身份相同", "explicit_policy_matches_saved_policy": "显式规划模式与存档相同",
        "native_planning_identity_matches_saved_arrays": "新规划身份符合冷读归属", "no_artificial_internal_domain_ports": "没有人工内部域端口",
        "nondeep_terminals_on_actual_perimeter": "非深洼终点只在实际外围", "terminal_status_known_and_noninterior": "终点原因明确且非内部占位",
        "derived_owner_edge_construction_consistency": "派生汇水归属沿路由一致", "derived_owner_covers_support": "派生归属覆盖固定支持范围",
        "derived_owner_unique_per_terminal": "各终点对应唯一归属", "derived_owner_matches_actual_terminal_catchment": "派生归属符合实际终点汇水"}
    def gate_text(values):
        return "；".join(gate_labels[key] + ("：通过" if value else "：失败") for key, value in values.items()) or "历史模式未应用此检查"
    content += "<table>" + "".join(f"<tr><th>{label}</th><td>{gate_text(report[key])}</td></tr>" for key, label in
        (("source_gates", "来源检查"), ("planning_gates", "显式规划模式与身份"), ("boundary_gates", "真实图幅边界检查"),
         ("derived_owner_construction_gates", "派生归属构造一致性（非自然分水岭认证）"))) + "</table>"
    labels = {"shared_confluence_node_count": "共享汇流节点", "selected_terminal_count": "选中河网终点",
        "selected_terminal_classification": "终点原因（未解决）", "cycle_cell_count": "环路格数",
        "nonlocal_or_self_edge_count": "非D8或自环边", "area_accumulation_max_residual_m2": "汇水面积残差（平方米）",
        "q_accumulation_max_residual_m3_s": "累计流量残差（立方米/秒）", "selected_strict_owner_change_edge_count": "选中河路穿越旧参考标签边（规划不相容诊断）",
        "maximum_fill_m": "工作面最大填高（米）", "fill_work_volume_m3": "工作面填高账（立方米）",
        "selected_raw_uphill_edge_count": "选中路线上原地形逆坡边", "selected_source_count": "选中河源",
        "single_source_component_count": "单源组件", "longest_continuous_selected_path_km": "最长连续选中路径（公里）",
        "maximum_terminal_catchment_km2": "最大终点汇水面积（平方公里）", "all_terminal_count": "全图总终点",
        "all_terminal_classification": "全图终点原因", "selected_terminal_owner_counts": "选中终点归属（负值未认证）"}
    content += "<table><tr><th>检查项</th><th>旧图</th><th>新图</th></tr>" + "".join(
        f"<tr><th>{label}</th><td>{html.escape(str(baseline.get(key, '未记录')))}</td><td>{html.escape(str(report[key]))}</td></tr>"
        for key, label in labels.items()) + "</table>"
    if "square_wall_comparison" in report:
        square = report["square_wall_comparison"]
        square_labels = {"selected_internal_artificial_domain_port_count": "可见人工内部域端口",
            "selected_actual_perimeter_terminal_count": "可见窗口外围终点（域外未知）",
            "shared_confluence_node_count": "共享汇流节点", "selected_terminal_count": "可见河网终点"}
        content += "<h2>原方格墙位置对照</h2><table><tr><th>检查项</th><th>第二版</th><th>原生重规划候选</th></tr>" + "".join(
            f"<tr><th>{label}</th><td>{square['audit'][key]}</td><td>{report[key]}</td></tr>" for key, label in square_labels.items()) + "</table>"
        content += f"<p>固定原端口{square['former_visible_internal_domain_port_count']}处，其中{square['former_ports_with_new_selected_route_within_300m_count']}处在300米内有新选中路线，{square['former_ports_with_new_reference_crossing_within_300m_count']}处附近新路线穿越旧粗标签边。逐点位移与实际下游长度见检查记录。</p>"
    content += "".join(f"<figure><img src='{name}' alt='{name}'></figure>" for name in figures)
    content += "<p><a href='cold-audit.json'>Independent checks and unresolved terminals</a></p></main>"
    (args.output / "preview.html").write_text(content, encoding="utf-8")
    print(json.dumps({"preview": str(args.output / "preview.html"), "cold_audit": report}, allow_nan=False), flush=True)
    if not all(report["gates"].values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
