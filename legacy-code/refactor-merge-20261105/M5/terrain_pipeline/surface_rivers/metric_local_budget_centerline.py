"""Finite original-row local bed route search; full bed validation remains required."""
import numpy as np

from .metric_transverse_budget import evaluate_necessary_budget
from .metric_terrain_centerline import turn_summary


def search_local_candidates(points, receiver, contributing_edges, windows, *,
                            gate, evaluate, turn_score, max_candidates=32, max_refinements=4):
    """evaluate returns status clear/unknown/infeasible and optional extra_cut.

    Contributing edges are ordered by dual contribution by the caller. Windows
    include the failed window and every previously clear window. Only candidates
    clear in every supplied window can be selected. Counts include gate refusals.
    """
    if not windows:
        raise ValueError("at least one failed window is required")
    degree = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    anchors = (degree != 1) | (receiver < 0)
    records, feasible = [], []
    groups_seen = set()
    baseline_extra = None
    window_evaluations = 0
    refine_attempts = 0
    if windows:
        baseline = evaluate(points, windows[0])
        window_evaluations += 1
        baseline_extra = baseline.get("extra_cut") if baseline["status"] == "infeasible" else None

    def attempt(node, group, offset, stage):
        nonlocal window_evaluations
        if len(records) >= max_candidates:
            return None
        donor = int(np.flatnonzero(receiver == node)[0])
        tangent = points[receiver[node]] - points[donor]
        normal = np.array([-tangent[1], tangent[0]]) / np.linalg.norm(tangent)
        candidate = points.copy()
        candidate[group] += offset * normal
        record = dict(node=node, group=group, offset_m=offset, stage=stage,
                      index=len(records), window_results=[])
        records.append(record)
        try:
            gate(candidate)
        except ValueError as error:
            record.update(status="gate_refused", reason=str(error))
            return record
        record["status"] = "clear"
        for window in windows:
            result = evaluate(candidate, window)
            window_evaluations += 1
            if result["status"] not in ("clear", "unknown", "infeasible"):
                raise ValueError("unsupported local evaluation status")
            record["window_results"].append(dict(window=window, **result))
            if result["status"] != "clear":
                record["status"] = result["status"]
                break
        if record["status"] == "clear":
            record["turn_score"] = turn_score(candidate)
            feasible.append((record["turn_score"], record["index"], candidate))
        return record

    for source, target in contributing_edges:
        movable = [int(node) for node in (source, target) if not anchors[node]]
        if not movable:
            continue
        root = movable[0]
        donor = int(np.flatnonzero(receiver == root)[0])
        adjacent = [node for node in (donor, int(receiver[root])) if not anchors[node]]
        groups = [(node, [node]) for node in movable]
        groups.append((root, list(dict.fromkeys([root] + adjacent))))
        root_records = []
        for node, group in groups[:3]:
            key = (node, tuple(group))
            if key in groups_seen:
                continue
            groups_seen.add(key)
            for offset in (-.5, .5, -2., 2., -4., 4.):
                record = attempt(node, group, offset, "coarse")
                if record is not None:
                    root_records.append(record)
        improving = [record for record in root_records
                     if record["status"] == "infeasible" and record["window_results"]
                     and record["window_results"][0]["status"] == "infeasible"
                     and record["window_results"][0].get("extra_cut") is not None
                     and baseline_extra is not None
                     and record["window_results"][0]["extra_cut"] < baseline_extra]
        if improving:
            best = min(improving, key=lambda record: record["window_results"][0]["extra_cut"])
            for delta in (-.5, .5, -.25, .25):
                if refine_attempts >= max_refinements:
                    break
                record = attempt(best["node"], best["group"], best["offset_m"] + delta, "refine")
                if record is not None:
                    refine_attempts += 1
        if len(records) >= max_candidates:
            break
    selected = min(feasible, key=lambda item: (item[0], item[1])) if feasible else None
    return (selected[2] if selected else points.copy()), dict(
        candidate_limit=max_candidates, attempted_candidates=len(records), records=records,
        selected_index=selected[1] if selected else None,
        status="local_windows_clear_needs_full_bed" if selected else "no_clear_candidate",
        maximum_window_evaluations=1 + max_candidates * len(windows),
        window_evaluations=window_evaluations, refine_attempts=refine_attempts,
    )



def worst_windows(evaluation, side_m=512.):
    ranked = []
    for kind in ("edge_strip", "node_cap"):
        for category in ("physical_half_bottom", "bottom_guard_shell", "bank"):
            worst = evaluation["bounds"][kind][category]["worst"]
            if worst is None:
                continue
            ranked.append((worst["necessary_cut_m"], kind, category, worst))
    windows = []
    for required, kind, category, worst in sorted(ranked, key=lambda item: (-item[0], item[1], item[2])):
        center = np.asarray(worst["vertex_xz_m"])
        if all(np.linalg.norm(center - window["center_xz_m"]) > side_m / 2. for window in windows):
            windows.append(dict(center_xz_m=center.tolist(), side_m=side_m,
                                origin_kind=kind, origin_category=category,
                                necessary_cut_m=required))
        if len(windows) == 6:
            break
    return windows



def repair_local_conflicts(terrain, points, receiver, width, depth, profile, ids, *,
                           validate, certify, assess, spacing, max_cut,
                           bottom_slope, minimum_slope, max_candidates=32,
                           max_local_solves=None, budget_evaluate=None):
    """Return a locally checked route requiring complete original-bed validation.

    assess receives the exact physical configuration as keyword arguments and
    reports clear/infeasible/unknown, solver_calls, and optional dual route roots.
    """
    if max_local_solves is None:
        max_local_solves = 2 * (max_candidates + 1) * 6
    if budget_evaluate is None:
        budget_evaluate = lambda candidate, candidate_profile: evaluate_necessary_budget(
            candidate, receiver, width, candidate_profile, terrain, ids, spacing, max_cut, bottom_slope)
    current = points.copy()
    current_profile = profile
    history, records = [], []
    solves, refinements = 0, 0
    cached = {}

    def window_key(window):
        return tuple(window["center_xz_m"]), window["side_m"]

    def evaluation(candidate, window):
        nonlocal solves
        key = (candidate.tobytes(), window_key(window))
        if key in cached:
            return cached[key]
        if solves + 2 > max_local_solves:
            return dict(status="unknown", reason="component local solver budget exhausted")
        candidate_profile = certify(candidate)
        result = assess(candidate, receiver, width, depth, candidate_profile, terrain, window,
                        spacing=spacing, max_cut=max_cut, bottom_slope=bottom_slope,
                        minimum_slope=minimum_slope)
        solves += result.get("solver_calls", 1)
        cached[key] = result
        return result

    def gate(candidate):
        validate(candidate)
        candidate_profile = certify(candidate)
        budget = budget_evaluate(candidate, candidate_profile)
        if sum(budget["counts"]):
            raise ValueError("global necessary budget conflicts")

    windows = worst_windows(budget_evaluate(current, current_profile))
    while True:
        assessments = [evaluation(current, window) for window in windows]
        history.append(dict(windows=windows, assessments=assessments))
        failed = next((index for index, result in enumerate(assessments) if result["status"] == "infeasible"), None)
        unknown = any(result["status"] == "unknown" for result in assessments)
        if failed is None:
            status = "unknown_needs_full_bed" if unknown or not windows else "local_windows_clear_needs_full_bed"
            break
        if len(records) >= max_candidates:
            status = "local_conflicts_remain"
            break
        contributing = assessments[failed].get("contributing_edges", [])
        if not contributing:
            status = "local_conflict_without_dual_route_witness"
            break
        ordered_windows = [windows[failed]] + [window for index, window in enumerate(windows) if index != failed]
        candidate, policy = search_local_candidates(current, receiver, contributing, ordered_windows,
            gate=gate, evaluate=evaluation, turn_score=lambda route: turn_summary(route, receiver)["all_donor_turn_energy"],
            max_candidates=max_candidates-len(records), max_refinements=4-refinements)
        records.extend(policy["records"])
        refinements += policy["refine_attempts"]
        if policy["selected_index"] is None:
            status = "local_conflicts_remain"
            break
        current, current_profile = candidate, certify(candidate)
    return current, current_profile, dict(status=status, candidate_limit=max_candidates,
        attempted_candidates=len(records), refine_attempts=refinements, local_solver_calls=solves,
        maximum_local_solver_calls=max_local_solves, history=history, records=records,
        window_policy="freeze initial spatially separated necessary-worst windows; recheck all after every selected candidate",
        maximum_windows=6,
        interpretation="Local windows are original-row relaxations; full bed and cold audit remain required")

