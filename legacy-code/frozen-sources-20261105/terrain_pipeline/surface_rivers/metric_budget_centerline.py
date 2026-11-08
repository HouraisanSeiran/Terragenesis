"""Bounded local route search selected by physical transverse-cut conflicts."""

import numpy as np

from .metric_valley_centerline import _anchors


def repair_budget_centerline(points, receiver, profile, *, evaluate,
                             validate, certify, max_cut_m, max_trials=256,
                             max_rounds=24, max_trials_per_round=32,
                             causal_nodes=None, source_height=None, max_causal_nodes=4,
                             max_causal_certificates_per_node=3):
    """Use local proxy bounds, then certify the complete profile and cut bounds.

    evaluate(points, profile, focus_nodes) returns category maxima/counts and
    hotspot node indices. certify(points) returns the complete highest profile.
    No mesh or LP is constructed by this search.
    """
    points = points.copy()
    anchors = _anchors(receiver)
    donors = [[] for _ in points]
    for source, target in enumerate(receiver):
        if target >= 0:
            donors[target].append(source)
    evaluation = evaluate(points, profile, None)
    initial = evaluation
    trials, accepted, complete_certificates = 0, [], 0

    def score(values):
        return (max(0., values["maxima"][0] - max_cut_m), values["counts"][0],
                max(0., max(values["maxima"]) - max_cut_m), sum(values["counts"]))

    for round_index in range(max_rounds):
        if not sum(evaluation["counts"]) or trials >= max_trials:
            break
        ranked = sorted(evaluation["hotspots"], key=lambda h: (
            h["category"] != "physical_half_bottom", -h["maximum_required_cut_m"]))
        node_order = []
        for hotspot in ranked:
            candidates = [hotspot["node_index"]] if "node_index" in hotspot else [
                hotspot["source_node_index"], hotspot["target_node_index"]]
            for node in candidates:
                if not anchors[node] and node not in node_order:
                    node_order.append(node)
        proposals = []
        round_trial_limit = min(max_trials, trials + max_trials_per_round)
        for node in node_order:
            upstream, downstream = donors[node][0], int(receiver[node])
            tangent = points[downstream] - points[upstream]
            normal = np.array([-tangent[1], tangent[0]]) / np.linalg.norm(tangent)
            neighbors = [n for n in [upstream, downstream] if not anchors[n]]
            groups = [[node], [node] + neighbors]
            for group in groups:
                focus = set(group)
                for member in group:
                    focus.update(donors[member])
                    if receiver[member] >= 0:
                        focus.add(int(receiver[member]))
                old_local = evaluate(points, profile, focus)
                for offset_m in (-.5, .5, -1., 1., -2., 2., -4., 4., -8., 8.):
                    if trials >= round_trial_limit:
                        break
                    trials += 1
                    candidate = points.copy()
                    candidate[group] += offset_m * normal
                    try:
                        validate(candidate)
                        proxy = evaluate(candidate, profile, focus)
                    except ValueError:
                        continue
                    if score(proxy) >= score(old_local):
                        continue
                    if any(new > old + 1e-8 for new, old in zip(proxy["maxima"], evaluation["maxima"])):
                        continue
                    improvement = tuple(new - old for new, old in zip(score(proxy), score(old_local)))
                    proposals.append((improvement, candidate, group, offset_m))
                if trials >= round_trial_limit:
                    break
            if trials >= round_trial_limit:
                break
        chosen = False
        for _, candidate, group, offset_m in sorted(proposals, key=lambda proposal: proposal[0]):
            try:
                complete_certificates += 1
                certified_profile = certify(candidate)
                complete = evaluate(candidate, certified_profile, None)
            except ValueError:
                continue
            if (score(complete) >= score(evaluation)
                    or any(new > old + 1e-8 for new, old in zip(complete["maxima"], evaluation["maxima"]))):
                continue
            accepted.append(dict(round=round_index, node_indices=group,
                                 offset_m=offset_m, before_maxima=evaluation["maxima"],
                                 after_maxima=complete["maxima"],
                                 before_counts=evaluation["counts"], after_counts=complete["counts"]))
            points, profile, evaluation = candidate, certified_profile, complete
            chosen = True
            break
        if not chosen:
            break
    causal_trials = 0
    if sum(evaluation["counts"]) and causal_nodes is not None:
        movable_causal_nodes = [node for node in causal_nodes(points, profile, evaluation) if not anchors[node]]
        for node in movable_causal_nodes[:max_causal_nodes]:
            if anchors[node] or not sum(evaluation["counts"]):
                continue
            upstream, downstream = donors[node][0], int(receiver[node])
            tangent = points[downstream] - points[upstream]
            normal = np.array([-tangent[1], tangent[0]]) / np.linalg.norm(tangent)
            neighbors = [n for n in [upstream, downstream] if not anchors[n]]
            proposals = []
            for group in ([node], [node] + neighbors):
                for offset_m in (-.5, .5, -1., 1., -2., 2., -4., 4., -8., 8.):
                    causal_trials += 1
                    candidate = points.copy()
                    candidate[group] += offset_m * normal
                    try:
                        validate(candidate)
                    except ValueError:
                        continue
                    gain = float(source_height(candidate[node]) - source_height(points[node]))
                    if gain > 0.:
                        proposals.append((-gain, candidate, group, offset_m))
            certified_proposals = []
            for _, candidate, group, offset_m in sorted(proposals, key=lambda proposal: proposal[0])[:max_causal_certificates_per_node]:
                try:
                    complete_certificates += 1
                    certified_profile = certify(candidate)
                    complete = evaluate(candidate, certified_profile, None)
                except ValueError:
                    continue
                if (score(complete) >= score(evaluation)
                        or any(new > old + 1e-8 for new, old in zip(complete["maxima"], evaluation["maxima"]))):
                    continue
                certified_proposals.append((score(complete), candidate, group, offset_m, certified_profile, complete))
            if certified_proposals:
                _, candidate, group, offset_m, certified_profile, complete = min(certified_proposals, key=lambda proposal: proposal[0])
                accepted.append(dict(stage="controlling_upstream", node_indices=group,
                                     offset_m=offset_m, before_maxima=evaluation["maxima"],
                                     after_maxima=complete["maxima"], before_counts=evaluation["counts"],
                                     after_counts=complete["counts"]))
                points, profile, evaluation = candidate, certified_profile, complete
    return points, profile, dict(
        algorithm="finite-physical-budget-hotspot-best-proxy-and-upstream-search-v3",
        maximum_trials=max_trials, attempted_trials=trials,
        maximum_rounds=max_rounds, maximum_trials_per_round=max_trials_per_round,
        maximum_cut_m=max_cut_m,
        causal_attempted_trials=causal_trials,
        maximum_causal_nodes=max_causal_nodes,
        maximum_causal_certificates_per_node=max_causal_certificates_per_node,
        complete_profile_and_budget_certificates=complete_certificates,
        accepted_moves=accepted, initial_maxima=initial["maxima"], final_maxima=evaluation["maxima"],
        initial_counts=initial["counts"], final_counts=evaluation["counts"],
        status="necessary_bounds_clear" if not sum(evaluation["counts"]) else "necessary_budget_conflicts_remain",
        anchors_fixed=True, constraint_parameters_changed=False,
    )
