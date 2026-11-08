"""Independent chunk conservation checks and actual FV growth preview."""
import argparse
from collections import deque
import json
from pathlib import Path
import sys

import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256

THRESHOLDS = {"water_m3": 1.e-7, "momentum_m4_s": 1.e-6, "solid_m3": 1.e-8,
    "state": 1.e-12, "time_s": 1.e-9, "floor_m": 1.e-10}


def read_arrays(path):
    with np.load(path) as saved:
        return {key: saved[key].copy() for key in saved.files}


def max_difference(left, right):
    left, right = np.asarray(left), np.asarray(right)
    if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        return float("inf")
    return float(np.max(np.abs(left - right), initial=0.))


def source_integral(schedule, start, end):
    """Cold-read packet overlap; does not invoke the producer's integrator."""
    ends = np.cumsum(schedule[:, 4])
    starts = ends - schedule[:, 4]
    overlap = np.maximum(0., np.minimum(ends, end) - np.maximum(starts, start))
    return float(np.sum(schedule[:, 3] * overlap / schedule[:, 4]))


def connected_dry(dry, seeds):
    connected = dry & seeds
    queue = deque(zip(*np.nonzero(connected)))
    while queue:
        row, col = queue.popleft()
        for r, c in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= r < dry.shape[0] and 0 <= c < dry.shape[1] and dry[r, c] and not connected[r, c]:
                connected[r, c] = True
                queue.append((r, c))
    return connected


def audit_handoffs(report, result, blocks, checkpoint, checks):
    state_keys = ("bed_m", "depth_m", "momentum_m2_s", "suspended_solid_m3")
    def compare(label, left, right, tolerance=THRESHOLDS["state"]):
        error = max_difference(left, right)
        checks.append({"check": label, "error": error, "tolerance": tolerance, "passed": error <= tolerance})
        return error
    compare("chunk snapshot count", len(blocks) + 1, len(result["time_s"]), 0.)
    for index, block in enumerate(blocks):
        compare(f"chunk {index} start time", block["absolute_time_start_s"], result["time_s"][index], THRESHOLDS["time_s"])
        compare(f"chunk {index} end time", block["absolute_time_end_s"], result["time_s"][index + 1], THRESHOLDS["time_s"])
        for key in state_keys:
            compare(f"chunk {index} before/result {key}", block["before_" + key], result[key][index])
            compare(f"chunk {index} after/result {key}", block["after_" + key], result[key][index + 1])
            if index:
                compare(f"chunk {index} continuity {key}", blocks[index - 1]["after_" + key], block["before_" + key])
        compare(f"chunk {index} floor identity", block["source_floor_m"], result["source_floor_m"])
    for key in state_keys:
        compare("final checkpoint/result " + key, checkpoint[key], result[key][-1])
    compare("checkpoint floor", checkpoint["source_floor_m"], result["source_floor_m"])
    compare("saved stage equals actual bed plus depth", result["stage_m"], result["bed_m"] + result["depth_m"])
    compare("checkpoint original bed", checkpoint["initial_bed_m"], result["initial_bed_m"])
    compare("checkpoint fixed mask", checkpoint["fixed_boundary_mask"].astype(int), result["fixed_boundary_mask"].astype(int), 0.)
    count = sum(int(block["aggregated_interval_count"]) for block in blocks)
    compare("total interval coverage", count, report["parameters"]["intervals"], 0.)
    duration = float(result["time_s"][-1] - result["time_s"][0])
    expected_duration = sum(float(block["absolute_time_end_s"] - block["absolute_time_start_s"]) for block in blocks)
    compare("interval duration", duration, expected_duration, THRESHOLDS["time_s"])
    compare("summary start time", result["time_s"][0], report["start"]["physical_time_s"], THRESHOLDS["time_s"])
    compare("summary end time", result["time_s"][-1], report["end"]["physical_time_s"], THRESHOLDS["time_s"])
    meta = json.loads(str(checkpoint["metadata_json"]))
    checks.append({"check": "checkpoint final metadata equals summary", "passed": meta == report["end"]})
    schedule = checkpoint["source_schedule"]
    checks.append({"check": "finite valid source schedule", "passed": bool(schedule.ndim == 2 and schedule.shape[1] == 6
        and np.isfinite(schedule).all() and np.all(schedule[:, 4] > 0.) and np.all(schedule[:, 3] >= 0.))})
    cursor0, cursor1 = report["start"]["source_cursor_s"], meta["source_cursor_s"]
    checks.append({"check": "source cursor monotone", "passed": bool(0. <= cursor0 <= cursor1)})
    integrated = source_integral(schedule, cursor0, cursor1)
    total_used = source_integral(schedule, 0., cursor1)
    quota = float(schedule[:, 3].sum())
    compare("source cursor run injection", integrated, report["injected_solid_m3"], THRESHOLDS["solid_m3"])
    compare("source cursor cumulative injection", total_used, meta["cumulative_injected_solid_m3"], THRESHOLDS["solid_m3"])
    compare("source schedule quota", quota, meta["source_total_solid_m3"], THRESHOLDS["solid_m3"])
    compare("remaining source quota", quota - total_used, report["remaining_finite_source_solid_m3"], THRESHOLDS["solid_m3"])
    checks.append({"check": "quota not overissued", "passed": bool(total_used <= quota + THRESHOLDS["solid_m3"])})
    for kind in ("parent", "water"):
        path = Path(meta[kind + "_result"])
        checks.append({"check": kind + " artifact identity", "passed": file_sha256(path) == meta[kind + "_sha256"]})
    parent = read_arrays(Path(meta["parent_result"]))
    fixed = result["fixed_boundary_mask"].astype(bool)
    compare("fixed boundary equals saved native parent", result["bed_m"][-1][fixed], parent["bed_m"][-1][fixed])
    consumed = int(meta["already_consumed_native_packets"])
    native = parent["schedule"]
    remaining = native[consumed:]
    compare("original remaining schedule prefix", schedule[:len(remaining)], remaining)
    compare("original already consumed quota", native[:consumed, 3].sum(), meta["already_consumed_native_solid_m3"], THRESHOLDS["solid_m3"])
    expected_quota = float(remaining[:, 3].sum())
    identities = meta["source_identities"]
    checks.append({"check": "unique finite source identities", "passed": len(set(identities)) == len(identities)})
    for source in meta.get("appended_sources", []):
        directory = Path(source["path"])
        source_report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        source_arrays = read_arrays(directory / "result.npz")
        exported = float(source_arrays["exported_solid_m3"].sum())
        checks.append({"check": "appended source artifact " + str(directory), "passed": file_sha256(directory / "result.npz") == source["sha256"]
            and source["sha256"] in identities and source_report["status"] == "completed" and source_report["old_exports_reissued_solid_m3"] == 0.})
        compare("appended source measured quota " + str(directory), exported, source["solid_m3"], THRESHOLDS["solid_m3"])
        compare("appended source report quota " + str(directory), exported, source_report["new_deliverable_export_solid_m3"], THRESHOLDS["solid_m3"])
        expected_quota += exported
    compare("provenance total quota", expected_quota, quota, THRESHOLDS["solid_m3"])
    return {"interval_count": count, "physical_duration_s": duration, "source_cursor_start_s": cursor0,
        "source_cursor_end_s": cursor1, "cursor_integrated_run_solid_m3": integrated,
        "cursor_integrated_total_solid_m3": total_used, "schedule_quota_solid_m3": quota}


def audit_chunk(a):
    if int(a["aggregated_interval_count"]) != int(a["expected_interval_count"]):
        raise ValueError("incomplete interval aggregation")
    left, right, boundary = a["face_left"], a["face_right"], a["boundary_cell"]
    n = a["before_bed_m"].size
    def divergence(internal, outward):
        if internal.ndim == 1:
            return (np.bincount(right, weights=internal, minlength=n) - np.bincount(left, weights=internal, minlength=n)
                - np.bincount(boundary, weights=outward, minlength=n))
        return np.column_stack([divergence(internal[:, k], outward[:, k]) for k in range(internal.shape[1])])
    water = (a["after_depth_m"] - a["before_depth_m"]).ravel() * 25.
    expected_water = divergence(a["water_internal_transfer_m3"], a["water_boundary_transfer_m3"]) + a["water_forcing_volume_m3"]
    momentum = (a["after_momentum_m2_s"] - a["before_momentum_m2_s"]) * 25.
    expected_momentum = divergence(a["water_internal_momentum_transfer"], a["water_boundary_momentum_transfer"])
    expected_momentum += 25. * (a["water_bed_momentum_change"] + a["water_manning_momentum_change"])
    deposited = a["suspended_deposited_solid_m3"].ravel()
    suspended = (a["after_suspended_solid_m3"] - a["before_suspended_solid_m3"]).ravel()
    expected_suspended = divergence(a["suspended_internal_transfer_solid_m3"], a["suspended_boundary_export_solid_m3"])
    expected_suspended += a["injected_cell_solid_m3"] - deposited
    if "suspended_entrained_solid_m3" in a:
        expected_suspended += a["suspended_entrained_solid_m3"].ravel()
    bed = (a["after_bed_m"] - a["before_bed_m"]).ravel() * 25. * .65
    expected_bed = divergence(a["bedload_internal_transfer_solid_m3"], a["bedload_boundary_export_solid_m3"])
    expected_bed -= a["bedload_fixed_marine_edge_export_solid_m3"]
    expected_bed += deposited
    if "suspended_entrained_solid_m3" in a:
        expected_bed -= a["suspended_entrained_solid_m3"].ravel()
        expected_bed += divergence(a["slope_internal_transfer_solid_m3"], np.zeros(len(boundary)))
    return {"maximum_cell_water_mismatch_m3": float(abs(water - expected_water).max()),
        "maximum_cell_momentum_mismatch_m4_s": float(abs(momentum - expected_momentum).max()),
        "maximum_cell_suspended_mismatch_solid_m3": float(abs(suspended - expected_suspended).max()),
        "maximum_cell_bed_mismatch_solid_m3": float(abs(bed - expected_bed).max()),
        "minimum_floor_margin_m": float((a["after_bed_m"] - a["source_floor_m"]).min()),
        "duration_s": float(a["absolute_time_end_s"] - a["absolute_time_start_s"])}


def audit_carrier_chunk(a):
    """Check accumulated absolute crossings and per-interval worst violations."""
    names = ("carrier_internal_accepted_abs_solid_m3", "carrier_internal_capacity_solid_m3",
        "carrier_internal_max_capacity_violation_solid_m3", "carrier_internal_max_direction_violation_solid_m3",
        "carrier_boundary_accepted_actual_solid_m3", "carrier_boundary_capacity_solid_m3",
        "carrier_boundary_max_capacity_violation_solid_m3")
    for name in names:
        if "bedload_" + name not in a:
            raise ValueError("v4 chunk missing mandatory carrier audit field: " + name)
    value = {name: a["bedload_" + name] for name in names}
    finite_nonnegative = all(np.isfinite(item).all() and np.min(item, initial=0.) >= 0. for item in value.values())
    internal_abs = value["carrier_internal_accepted_abs_solid_m3"]
    internal_capacity = value["carrier_internal_capacity_solid_m3"]
    boundary_actual = value["carrier_boundary_accepted_actual_solid_m3"]
    boundary_capacity = value["carrier_boundary_capacity_solid_m3"]
    if internal_abs.shape != a["face_left"].shape or internal_capacity.shape != internal_abs.shape:
        raise ValueError("v4 internal carrier audit shape mismatch")
    if boundary_actual.shape != a["boundary_cell"].shape or boundary_capacity.shape != boundary_actual.shape:
        raise ValueError("v4 boundary carrier audit shape mismatch")
    errors = [np.maximum(internal_abs - internal_capacity, 0.).max(initial=0.),
        np.maximum(abs(a["bedload_internal_transfer_solid_m3"]) - internal_abs, 0.).max(initial=0.),
        np.maximum(boundary_actual - boundary_capacity, 0.).max(initial=0.),
        max_difference(boundary_actual, a["bedload_boundary_export_solid_m3"])]
    errors.extend(value[name].max(initial=0.) for name in names if "_max_" in name)
    return {"finite_nonnegative": bool(finite_nonnegative), "maximum_carrier_violation_solid_m3": float(max(errors))}


def inspect(run, output):
    report = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    identities = {name: file_sha256(ROOT / name) == digest for name, digest in report["implementation_hashes"].items()}
    if not all(identities.values()):
        raise ValueError("archived implementation differs")
    chunks = []
    blocks = []
    checks = []
    for path in sorted(run.glob("chunk-audit-*.npz")):
        saved = read_arrays(path)
        if report["schema"] in ("finite-FV-suspended-growth-v3", "finite-FV-suspended-growth-v4"):
            for name in ("suspended_entrained_solid_m3", "slope_internal_transfer_solid_m3"):
                if name not in saved:
                    raise ValueError("v3/v4 chunk missing mandatory exchange/slope audit field: " + name)
        if report["schema"] == "finite-FV-suspended-growth-v4":
            carrier = audit_carrier_chunk(saved)
            checks.append({"check": path.name + " v4 carrier capacity/direction", **carrier,
                "passed": carrier["finite_nonnegative"] and carrier["maximum_carrier_violation_solid_m3"] <= THRESHOLDS["solid_m3"]})
        blocks.append(saved)
        result = audit_chunk(saved)
        chunks.append({"path": str(path), "sha256": file_sha256(path), **result})
        for name, tolerance in (("maximum_cell_water_mismatch_m3", THRESHOLDS["water_m3"]),
                ("maximum_cell_momentum_mismatch_m4_s", THRESHOLDS["momentum_m4_s"]),
                ("maximum_cell_suspended_mismatch_solid_m3", THRESHOLDS["solid_m3"]),
                ("maximum_cell_bed_mismatch_solid_m3", THRESHOLDS["solid_m3"])):
            checks.append({"check": path.name + " " + name, "error": result[name], "tolerance": tolerance,
                "passed": bool(np.isfinite(result[name]) and result[name] <= tolerance)})
        checks.append({"check": path.name + " floor", "passed": result["minimum_floor_margin_m"] >= -THRESHOLDS["floor_m"]})
    with np.load(run / "result.npz") as saved:
        a = {key: saved[key] for key in saved.files}
    checkpoint_path = Path(report["checkpoint"])
    checkpoint = read_arrays(checkpoint_path)
    checks.append({"check": "checkpoint artifact identity", "passed": file_sha256(checkpoint_path) == report["checkpoint_sha256"]})
    handoffs = audit_handoffs(report, a, blocks, checkpoint, checks)
    ledgers = json.loads((run / "interval-ledgers.json").read_text(encoding="utf-8"))
    checks.append({"check": "interval ledger coverage", "passed": len(ledgers) == handoffs["interval_count"]
        and [row["global_interval"] for row in ledgers] == list(range(handoffs["interval_count"]))})
    expected_start = float(a["time_s"][0])
    for index, row in enumerate(ledgers):
        interval_duration = row["physical_time_end_s"] - row["physical_time_start_s"] if report["parameters"].get("adaptive_intervals") else report["parameters"]["interval_s"]
        expected_end = expected_start + interval_duration
        checks.append({"check": f"interval {index} time coverage", "passed": abs(row["physical_time_start_s"] - expected_start) <= THRESHOLDS["time_s"]
            and abs(row["physical_time_end_s"] - expected_end) <= THRESHOLDS["time_s"]})
        for name in ("incoming_water_depth_continuity_error_m", "incoming_water_momentum_continuity_error_m2_s",
                "water_depth_handoff_error_m", "water_momentum_handoff_error_m2_s"):
            checks.append({"check": f"interval {index} " + name, "error": abs(row[name]),
                "tolerance": THRESHOLDS["state"], "passed": abs(row[name]) <= THRESHOLDS["state"]})
        expected_start = expected_end
    checks.append({"check": "interval ledger final time", "passed": abs(expected_start - a["time_s"][-1]) <= THRESHOLDS["time_s"]})
    offset = 0
    for index, block in enumerate(blocks):
        count = int(block["aggregated_interval_count"])
        rows = ledgers[offset:offset + count]
        covered = sum(row["physical_time_end_s"] - row["physical_time_start_s"] for row in rows)
        block_duration = float(block["absolute_time_end_s"] - block["absolute_time_start_s"])
        checks.append({"check": f"chunk {index} ledger duration/count", "passed": len(rows) == count and count > 0
            and abs(covered - block_duration) <= THRESHOLDS["time_s"]
            and abs(rows[0]["physical_time_start_s"] - block["absolute_time_start_s"]) <= THRESHOLDS["time_s"]
            and abs(rows[-1]["physical_time_end_s"] - block["absolute_time_end_s"]) <= THRESHOLDS["time_s"]})
        offset += count
    ledger_injected = sum(row["injected_solid_m3"] for row in ledgers)
    checks.append({"check": "interval ledger injection", "passed": abs(ledger_injected - report["injected_solid_m3"]) <= THRESHOLDS["solid_m3"]})
    delta = a["bed_m"][-1] - a["bed_m"][0]
    h = a["depth_m"][-1]
    dry = h <= 2.e-6
    thin_water = (h > 2.e-6) & (h <= .01)
    sea_side = np.broadcast_to((np.arange(h.shape[0]) * 5. - 360. >= 0.)[:, None], h.shape)
    original_sea = (a["initial_bed_m"] < 0.) & sea_side
    connected = connected_dry(dry, a["initial_bed_m"] >= 0.)
    fixed = a["fixed_boundary_mask"].astype(bool)
    fixed_difference = max_difference(a["bed_m"][-1][fixed], a["bed_m"][0][fixed])
    original_fixed_difference = max_difference(a["bed_m"][-1][fixed], a["initial_bed_m"][fixed])
    checks.append({"check": "fixed boundary bed unchanged during run", "error": fixed_difference,
        "tolerance": THRESHOLDS["state"], "passed": fixed_difference <= THRESHOLDS["state"]})
    checks.append({"check": "all saved states above floor", "passed": bool(np.min(a["bed_m"] - a["source_floor_m"]) >= -THRESHOLDS["floor_m"])})
    inherited_fixed_difference = max_difference(a["bed_m"][0][fixed], a["initial_bed_m"][fixed])
    checks.append({"check": "original fixed boundary discrepancy unchanged", "error": abs(original_fixed_difference - inherited_fixed_difference),
        "tolerance": THRESHOLDS["state"], "passed": abs(original_fixed_difference - inherited_fixed_difference) <= THRESHOLDS["state"]})
    inventory0 = float(((a["bed_m"][0] - a["source_floor_m"]) * 25. * .65).sum() + a["suspended_solid_m3"][0].sum())
    inventory1 = float(((a["bed_m"][-1] - a["source_floor_m"]) * 25. * .65).sum() + a["suspended_solid_m3"][-1].sum())
    export = sum(float(block["suspended_boundary_export_solid_m3"].sum() + block["bedload_boundary_export_solid_m3"].sum()
        + block["bedload_fixed_marine_edge_export_solid_m3"].sum()) for block in blocks)
    solid_residual = inventory1 + export - inventory0 - ledger_injected
    forcing = sum(float(block["water_forcing_volume_m3"].sum()) for block in blocks)
    outward = sum(float(block["water_boundary_transfer_m3"].sum()) for block in blocks)
    chunk_net_import = sum(float(-np.minimum(block["water_boundary_transfer_m3"], 0.).sum()) for block in blocks)
    chunk_net_export = sum(float(np.maximum(block["water_boundary_transfer_m3"], 0.).sum()) for block in blocks)
    if report["schema"] in ("finite-FV-suspended-growth-v2", "finite-FV-suspended-growth-v3", "finite-FV-suspended-growth-v4"):
        reported_water = report["water_supplied_imported_exported_m3"]
        error = max_difference(reported_water, [forcing, chunk_net_import, chunk_net_export])
        checks.append({"check": "v2 summary chunk-net water partition", "error": error,
            "tolerance": THRESHOLDS["water_m3"], "passed": error <= THRESHOLDS["water_m3"]})
    water_residual = float((h - a["depth_m"][0]).sum() * 25. - forcing + outward)
    for label, actual, expected, tolerance in (("coldread solid closure", solid_residual, 0., THRESHOLDS["solid_m3"]),
            ("coldread water closure", water_residual, 0., THRESHOLDS["water_m3"]),
            ("summary solid residual", solid_residual, report["combined_residual_solid_m3"], THRESHOLDS["solid_m3"]),
            ("summary water residual", water_residual, report["water_volume_residual_m3"], THRESHOLDS["water_m3"]),
            ("summary export", export, report["exported_solid_m3"], THRESHOLDS["solid_m3"]),
            ("summary initial inventory", inventory0, report["initial_bed_plus_suspended_solid_m3"], THRESHOLDS["solid_m3"]),
            ("summary final inventory", inventory1, report["final_bed_plus_suspended_solid_m3"], THRESHOLDS["solid_m3"])):
        checks.append({"check": label, "error": abs(actual - expected), "tolerance": tolerance, "passed": abs(actual - expected) <= tolerance})
    momentum = a["momentum_m2_s"][-1].reshape(*h.shape, 2)
    velocity = np.divide(np.linalg.norm(momentum, axis=2), h, out=np.zeros_like(h), where=h > .01)
    positive = np.maximum(delta, 0.) * 25.
    side = np.zeros(h.shape, bool)
    side[:, :5] = True
    side[:, -5:] = True
    rows = np.arange(h.shape[0]) * 5. - 360.
    landward = np.broadcast_to((rows < 0.)[:, None], h.shape)
    deposited = sum((block["suspended_deposited_solid_m3"].reshape(h.shape) for block in blocks), np.zeros_like(h))
    concentration = np.divide(a["suspended_solid_m3"][-1], h * 25., out=np.zeros_like(h), where=h > 2.e-6)
    row_suspended = a["suspended_solid_m3"][-1].sum(axis=1)
    row_deposited = deposited.sum(axis=1)
    occupied = row_suspended > 1.e-8
    core = np.arange(112, 128)
    sections = [{"station_m": float(rows[r]), "core_q_m3_s": float(momentum[r, core, 1].sum() * 5.),
        "total_q_m3_s": float(momentum[r, :, 1].sum() * 5.), "core_wet_area_m2": float(h[r, core].sum() * 5.),
        "core_q_divided_by_area_m_s": float(momentum[r, core, 1].sum() / h[r, core].sum()) if h[r, core].sum() else None,
        "center_stage_m": float(a["stage_m"][-1, r, 120]), "center_bed_m": float(a["bed_m"][-1, r, 120])}
        for r in range(h.shape[0])]
    for check in checks:
        check["passed"] = bool(check["passed"])
    audit = {"schema": "FV-growth-independent-chunk-audit-v2", "run": str(run), "implementation_identity_matches": identities,
        "status": "passed" if all(row["passed"] for row in checks) else "failed", "checks": checks,
        "thresholds": THRESHOLDS, "handoffs_and_source": handoffs,
        "coldread_combined_residual_solid_m3": solid_residual, "coldread_water_residual_m3": water_residual,
        "chunk_net_water_supplied_imported_exported_m3": [forcing, chunk_net_import, chunk_net_export],
        "water_exchange_semantics": "Each boundary face is integrated over a complete saved chunk, then its signed net transfer is split into import/export. Opposing transfers within that face/chunk cancel. These are not gross CFL-substep imports/exports; the net water closure remains exact.",
        "summary_water_exchange_semantics": "chunk-net face transfer partition; not substep-gross exchange" if report["schema"] in ("finite-FV-suspended-growth-v2", "finite-FV-suspended-growth-v3", "finite-FV-suspended-growth-v4") else "frozen v1 execution ledger; independent chunk-net partition reported separately",
        "actual_dry_threshold_m": 2.e-6, "thin_water_upper_threshold_m": .01,
        "original_sea_actual_dry_area_m2": float(np.count_nonzero(original_sea & dry) * 25.),
        "original_sea_thin_water_area_m2": float(np.count_nonzero(original_sea & thin_water) * 25.),
        "original_sea_depth_le1cm_area_m2": float(np.count_nonzero(original_sea & (h <= .01)) * 25.),
        "original_sea_dry_connected_to_original_land_area_m2": float(np.count_nonzero(original_sea & connected) * 25.),
        "original_sea_isolated_dry_area_m2": float(np.count_nonzero(original_sea & dry & ~connected) * 25.),
        "fixed_boundary_maximum_bed_difference_m": fixed_difference,
        "original_fixed_boundary_maximum_bed_difference_m": original_fixed_difference,
        "inherited_original_fixed_boundary_maximum_bed_difference_m": inherited_fixed_difference,
        "minimum_final_floor_margin_m": float((a["bed_m"][-1] - a["source_floor_m"]).min()),
        "final_peak_suspended_volume_concentration": float(concentration.max()),
        "seaward_final_suspended_solid_m3": float(a["suspended_solid_m3"][-1][~landward].sum()),
        "seaward_gross_settled_solid_m3": float(deposited[~landward].sum()),
        "landward_gross_settled_solid_m3": float(deposited[landward].sum()),
        "gross_settled_solid_m3": float(deposited.sum()),
        "furthest_suspended_station_above_1e_minus8_solid_m3_per_row": float(rows[occupied].max()) if occupied.any() else None,
        "suspended_solid_m3_by_row": row_suspended.tolist(), "gross_settled_solid_m3_by_row": row_deposited.tolist(),
        "result_sha256": file_sha256(run / "result.npz"), "chunks": chunks,
        "maximum_actual_speed_wet_gt1cm_m_s": float(velocity.max()), "sections": sections,
        "positive_dynamic_bed_bulk_m3": float(positive.sum()),
        "landward_positive_dynamic_bed_fraction": float(positive[landward].sum() / positive.sum()) if positive.sum() else None,
        "side25m_positive_dynamic_bed_fraction": float(positive[side].sum() / positive.sum()) if positive.sum() else None,
        "final_suspended_solid_m3": float(a["suspended_solid_m3"][-1].sum()),
        "initial_suspended_solid_m3": float(a["suspended_solid_m3"][0].sum()),
        "combined_residual_solid_m3": report["combined_residual_solid_m3"],
        "water_volume_residual_m3": report["water_volume_residual_m3"],
        "injected_solid_m3": report["injected_solid_m3"], "exported_solid_m3": report["exported_solid_m3"],
        "remaining_finite_source_solid_m3": report["remaining_finite_source_solid_m3"],
        "runtime_s": report["runtime_s"], "physical_duration_s": float(a["time_s"][-1] - a["time_s"][0]),
        "scope": "actual FV depth/momentum/finite bed and suspended mass; audit pass is not morphology acceptance",
        "reduced_transport_semantics": "interval-integrated net water face transfer; unresolved reversals require interval convergence check"}
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 3, figsize=(18, 16), constrained_layout=True)
    extent = [-602.5, 597.5, 737.5, -362.5]
    for ax, field, title, cmap in ((axes[0, 0], a["bed_m"][-1], "Actual final bed", "terrain"),
            (axes[0, 1], h, "Actual FV water depth", "Blues"), (axes[0, 2], delta, "Dynamic bed change", "RdBu_r")):
        limit = max(float(abs(delta).max()), 1.e-12)
        options = {"vmin": -limit, "vmax": limit} if title == "Dynamic bed change" else {}
        image = ax.imshow(field, extent=extent, cmap=cmap, **options)
        fig.colorbar(image, ax=ax, label="m", shrink=.8)
        ax.set(title=title, xlabel="Cross stream (m)", ylabel="Station (m)")
        ax.axhline(0., color="black", linewidth=.5)
    stage = np.ma.masked_where(dry, a["stage_m"][-1])
    image = axes[2, 0].imshow(stage, extent=extent, cmap="viridis")
    fig.colorbar(image, ax=axes[2, 0], label="Actual stage (m)")
    axes[2, 0].set(title="Actual water surface (dry <=2e-6 m masked)", xlabel="Cross stream (m)", ylabel="Station (m)")
    classes = np.zeros(h.shape)
    classes[thin_water] = 1
    classes[dry] = 2
    classes[original_sea & dry] = 2
    classes[original_sea & connected] = 3
    from matplotlib.colors import ListedColormap, BoundaryNorm
    palette = ListedColormap(["#4b99c6", "#777777", "#e7ca53", "#55a56b"])
    image = axes[2, 1].imshow(classes, extent=extent, cmap=palette, norm=BoundaryNorm(np.arange(-.5, 4.5), 4))
    bar = fig.colorbar(image, ax=axes[2, 1], ticks=range(4))
    bar.ax.set_yticklabels(["Wet >1cm", "Thin water 2e-6..1cm", "Dry <=2e-6m", "Sea dry land-connected"])
    axes[2, 1].set(title="Actual wet/dry; 4-neighbor land connection", xlabel="Cross stream (m)", ylabel="Station (m)")
    axes[2, 2].axis("off")
    axes[2, 2].text(0., .95, "Audit: " + audit["status"] + "\n"
        + f"Physical duration: {handoffs['physical_duration_s']:.3f} s\n"
        + f"Injected new solid: {ledger_injected:.6g} m3\n"
        + f"Sea actual dry: {audit['original_sea_actual_dry_area_m2']:.0f} m2\n"
        + f"Sea thin water: {audit['original_sea_thin_water_area_m2']:.0f} m2\n"
        + "Dry: h <=2e-6 m; thin water: 2e-6<h<=.01 m\nSea: original bed <0 m, station >=0 m\n"
        + "Connection seeds: original bed >= 0 m\nSingle final state; no persistence claim",
        va="top", fontsize=11)
    axes[1, 0].plot(rows, [s["center_stage_m"] for s in sections], label="Final water surface")
    axes[1, 0].plot(rows, [s["center_bed_m"] for s in sections], label="Final bed")
    axes[1, 0].set(title="Actual centerline water and bed", xlabel="Station (m)", ylabel="m")
    axes[1, 0].legend()
    axes[1, 1].plot(rows, [s["core_q_m3_s"] for s in sections], label="80m core")
    axes[1, 1].plot(rows, [s["total_q_m3_s"] for s in sections], label="Whole width")
    axes[1, 1].set(title="Actual downstream FV discharge", xlabel="Station (m)", ylabel="m3/s")
    axes[1, 1].legend()
    axes[1, 2].plot(rows, a["suspended_solid_m3"][-1].sum(axis=1), label="Suspended solid")
    axes[1, 2].set(title="Suspended source travel", xlabel="Station (m)", ylabel="Solid m3 per row")
    fig.savefig(output / "actual-growth.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 11), constrained_layout=True)
    for ax, field, title, unit, cmap in ((axes[0, 0], concentration, "Final suspended volume concentration", "Solid / water (m3/m3)", "magma"),
            (axes[0, 1], a["suspended_solid_m3"][-1], "Final suspended solid inventory", "Solid m3/cell", "magma"),
            (axes[1, 0], deposited, "Gross suspended settling during this run", "Solid m3/cell", "viridis"),
            (axes[1, 1], delta, "Net bed change (all sediment operators)", "Bed change m", "RdBu_r")):
        options = {"vmin": -limit, "vmax": limit} if ax is axes[1, 1] else {}
        image = ax.imshow(field, extent=extent, cmap=cmap, **options)
        fig.colorbar(image, ax=ax, label=unit, shrink=.8)
        ax.set(title=title, xlabel="Cross stream (m)", ylabel="Station (m)")
        ax.axhline(0., color="black", linewidth=.7)
    fig.savefig(output / "actual-sediment.png", dpi=160)
    plt.close(fig)
    return {key: value for key, value in audit.items() if key not in ("sections", "implementation_identity_matches", "checks",
        "suspended_solid_m3_by_row", "gross_settled_solid_m3_by_row")}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(inspect(args.run, args.output), indent=2))
