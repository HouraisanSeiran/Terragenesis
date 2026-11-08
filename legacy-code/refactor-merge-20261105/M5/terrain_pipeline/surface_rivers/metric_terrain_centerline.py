"""Finite original-terrain path search followed by complete physical certification."""

import time
from collections import deque

import numpy as np

from .metric_channel_geometry import _sample
from .metric_valley_centerline import _anchors, _turn_energy

DISPLACEMENT_COST_M_PER_M2 = 0.0002
SMOOTH_SOURCE_RISE_M = 0.25
ALGORITHM = "anchored-staged-terrain-branch-certified-ordinary-sweep-analytic-turn-bound-v7"
SUPERSEDES_ALGORITHM = "anchored-staged-terrain-branch-certified-ordinary-sweep-v6"
ANALYTIC_TURN_BOUND_DEGREES = {"ordinary": 90.0, "junction": 90.0}
TURN_BOUND_POLICY = (
    "fixed analytic per-segment maximum turn bound; identical for every entry, so a saved reference path "
    "can never tighten or loosen the searched space")
ENTRY_POLICY = (
    "search always starts from the deterministic legacy eight-pass six-metre initialization; a supplied "
    "reference path is acceptance-alignment evidence only and is never a search start")


def initialize_centerline(original, receiver, terrain, *, validate, certify=None):
    """Deterministically reproduce the legacy eight-pass, six-metre initializer."""
    points = original.copy()
    anchors = _anchors(receiver)
    moving = np.flatnonzero(~anchors)
    incoming = np.full(len(receiver), -1, np.int64)
    for source, target in enumerate(receiver):
        if target >= 0:
            incoming[target] = source
    original_source = _sample(terrain.elevation_m, original, terrain)[0]
    if certify is not None:
        certify(points)
    for _ in range(8 if len(moving) else 0):
        energy = _turn_energy(points, receiver)
        chosen = False
        for strength in (0.35, 0.175, 0.0875, 0.04375, 0.021875):
            candidate = points.copy()
            candidate[moving] += strength * (
                (points[incoming[moving]] + points[receiver[moving]]) / 2.0 - points[moving])
            offset = np.linalg.norm(candidate - original, axis=1)
            excessive = offset > 6.0
            candidate[excessive] = original[excessive] + (candidate[excessive] - original[excessive]) * (6.0 / offset[excessive, None])
            sampled = _sample(terrain.elevation_m, candidate, terrain)[0]
            too_high = sampled - original_source > 0.5
            candidate[too_high] = points[too_high]
            try:
                validate(candidate)
                if certify is not None:
                    certify(candidate)
            except ValueError:
                continue
            if _turn_energy(candidate, receiver) < energy - 1e-12:
                points = candidate
                chosen = True
                break
        if not chosen:
            break
    return points


def path_turns(points, receiver):
    """Represent every donor -> node -> receiver turn, including all junction arms."""
    donors = np.flatnonzero(receiver >= 0)
    nodes = receiver[donors]
    continuing = receiver[nodes] >= 0
    donors, nodes = donors[continuing], nodes[continuing]
    first = points[nodes] - points[donors]
    second = points[receiver[nodes]] - points[nodes]
    cosine = np.sum(first * second, axis=1) / (
        np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1))
    angles = np.arccos(np.clip(cosine, -1., 1.))
    degree = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    return angles, degree[nodes] > 1


def turn_summary(points, receiver):
    angles, junction = path_turns(points, receiver)
    result = {}
    for name, mask in (("ordinary", ~junction), ("junction", junction)):
        degrees = np.degrees(angles[mask])
        result[name] = dict(count=len(degrees),
                            maximum_degrees=float(degrees.max()) if len(degrees) else 0.,
                            p95_degrees=float(np.percentile(degrees, 95)) if len(degrees) else 0.)
    result["all_donor_turn_energy"] = float(np.sum((1. - np.cos(angles)) ** 2))
    return result


def node_turns(points, receiver):
    """Per-node turn angles with donor, receiver and junction identity.

    Every donor -> node -> receiver turn is represented, including all junction arms.
    """
    anchors = _anchors(receiver)
    donors = np.flatnonzero(receiver >= 0)
    nodes = receiver[donors]
    continuing = receiver[nodes] >= 0
    donors, nodes = donors[continuing], nodes[continuing]
    first = points[nodes] - points[donors]
    second = points[receiver[nodes]] - points[nodes]
    cosine = np.sum(first * second, axis=1) / (
        np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1))
    angles = np.arccos(np.clip(cosine, -1., 1.))
    degree = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    return dict(node_indices=nodes, donor_indices=donors, angles=angles,
                junction=degree[nodes] > 1, movable=~anchors[nodes])


def movable_turn_maxima(points, receiver):
    """Maximum single-segment turn per category over nodes the search may actually move."""
    detail = node_turns(points, receiver)
    degrees = np.degrees(detail["angles"])
    movable, junction = detail["movable"], detail["junction"]
    result = {}
    for kind, mask in (("ordinary", movable & ~junction), ("junction", movable & junction)):
        result[kind] = float(degrees[mask].max()) if mask.any() else 0.
    return result


def turn_ceiling(baseline, receiver):
    """Fixed, entry-independent turn ceiling for a search started from `baseline`.

    The declared analytic bound is a *cap on strictness*, not a one-shot hard wall: the
    effective ceiling is the looser of the fixed analytic bound and the baseline's own
    movable maximum. Two properties follow, and both are the point of the whole change:

    1. the ceiling never depends on any caller-supplied saved reference path, so two entries
       carrying different references search exactly the same feasible set;
    2. a deterministic initializer that is still dirty keeps enough headroom for the search to
       descend monotonically instead of being blocked before its first step.

    p95 needs no separate number: p95 <= maximum over the same node set, so bounding the
    maximum bounds p95. This deliberately removes the four-number global mutex.
    """
    observed = movable_turn_maxima(baseline, receiver)
    return {kind: max(ANALYTIC_TURN_BOUND_DEGREES[kind], observed[kind]) for kind in observed}


def enforce_turn_ceiling(points, receiver, ceiling):
    """Reject a candidate whose movable turn exceeds a ceiling from `turn_ceiling`."""
    observed = movable_turn_maxima(points, receiver)
    for kind, limit in ceiling.items():
        if observed[kind] > limit + 1e-7:
            raise ValueError(kind + " maximum_degrees exceeds analytic turn ceiling")
    return observed


def anchor_turn_exemption(points, receiver):
    """Diagnostics for turns the search cannot control because the node is anchored."""
    detail = node_turns(points, receiver)
    degrees = np.degrees(detail["angles"])
    exempt = ~detail["movable"]
    return dict(exempt_turn_count=int(exempt.sum()),
                exempt_maximum_degrees=float(degrees[exempt].max()) if exempt.any() else 0.,
                exempt_node_indices=sorted(int(node) for node in np.unique(detail["node_indices"][exempt])))


def shape_centerline(points, receiver, terrain, *, iterations, corridor_m,
                     validate, certify=None, reference_points=None):
    """Search with cheap geometric checks; certify only final bounded candidates."""
    started = time.perf_counter()
    original = points.copy()
    anchors = _anchors(receiver)
    moving = np.flatnonzero(~anchors)
    certificate_calls = 0

    def run_certificate(candidate):
        nonlocal certificate_calls
        certificate_calls += 1
        certify(candidate)

    reference_turn = None
    if reference_points is not None:
        if (reference_points.shape != original.shape or not np.isfinite(reference_points).all()
                or not np.array_equal(reference_points[anchors], original[anchors])):
            raise ValueError("reference centerline anchor or node mismatch")
        reference_turn = turn_summary(reference_points, receiver)
    if iterations:
        points = initialize_centerline(original, receiver, terrain,
                                       validate=validate, certify=run_certificate if certify is not None else None)
        offset = np.linalg.norm(points - original, axis=1)
        excessive = offset > corridor_m
        points[excessive] = original[excessive] + (points[excessive] - original[excessive]) * (corridor_m / offset[excessive, None])
    else:
        points = original.copy()
    original_turn = turn_summary(original, receiver)
    baseline = points.copy()
    baseline_turn = turn_summary(baseline, receiver)
    original_source = _sample(terrain.elevation_m, original, terrain)[0]
    baseline_source = _sample(terrain.elevation_m, baseline, terrain)[0]
    reference_source = (baseline_source if reference_points is None
                        else _sample(terrain.elevation_m, reference_points, terrain)[0])
    turn_ceiling_degrees = turn_ceiling(baseline, receiver)
    declared_ceiling_degrees = dict(ANALYTIC_TURN_BOUND_DEGREES)
    incoming = np.full(len(receiver), -1, np.int64)
    for source, target in enumerate(receiver):
        if target >= 0:
            incoming[target] = source
    refused = []
    accepted = {"terrain": 0, "smooth": 0, "local": 0}
    smooth_trials = 0
    smooth_trial_limit = 8 * len(moving)
    smooth_node_acceptances = {}
    smooth_node_visits = {}
    certified_terrain = baseline.copy()
    salvage_certificates = 0
    salvage_certificate_limit = 128
    salvage_accepted_nodes = []
    salvage_unattempted_nodes = []
    salvage_rejected_nodes = []
    initial_certificate_batches = 0
    if certify is not None:
        run_certificate(baseline)

    def admissible(candidate, source_ceiling):
        if np.any(np.linalg.norm(candidate - original, axis=1) > corridor_m + 1e-8):
            raise ValueError("original source corridor offset")
        sampled, cells = _sample(terrain.elevation_m, candidate, terrain)
        if (np.any(sampled > source_ceiling + 1e-9)
                or np.any(~terrain.valid_mask.ravel()[cells])):
            raise ValueError("source elevation or validity corridor")
        enforce_turn_ceiling(candidate, receiver, turn_ceiling_degrees)
        turns = turn_summary(candidate, receiver)
        validate(candidate)
        return sampled, turns

    baseline_movable = movable_turn_maxima(baseline, receiver)
    # Informational: does the deterministic initializer itself already exceed the *declared*
    # analytic bound? The search is no longer blocked by that (the ceiling keeps descending
    # headroom), but a component that still exceeds the declared bound at the end is a real
    # residual a naturalness audit must see rather than a silently relaxed limit.
    baseline_exceeds_declared_bound = sorted(
        kind for kind, limit in ANALYTIC_TURN_BOUND_DEGREES.items()
        if baseline_movable[kind] > limit + 1e-7)
    refused.append(dict(phase="baseline_turn_state", reason="baseline movable turns measured",
                        baseline_movable_maxima_degrees=baseline_movable,
                        exceeds_declared_analytic_bound=baseline_exceeds_declared_bound,
                        effective_ceiling_degrees=dict(turn_ceiling_degrees)))
    low = np.array([terrain.x0_m, terrain.z0_m])
    high = low + np.array([(terrain.elevation_m.shape[1] - 1) * terrain.dx_m,
                          (terrain.elevation_m.shape[0] - 1) * terrain.dz_m])
    for phase in ("terrain", "smooth"):
        if phase == "terrain":
            ceiling = original_source + 0.5
        else:
            if certify is not None and not np.array_equal(points, baseline):
                try:
                    run_certificate(points)
                except ValueError as error:
                    refused.append(dict(phase="terrain_certificate", reason=str(error)))
                    points = baseline.copy()
            certified_terrain = points.copy()
            floor_source = _sample(terrain.elevation_m, points, terrain)[0]
            ceiling = np.minimum(original_source + 0.5, floor_source + SMOOTH_SOURCE_RISE_M)
            first = points[moving] - points[incoming[moving]]
            second = points[receiver[moving]] - points[moving]
            cosine = np.sum(first * second, axis=1) / (np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1))
            angles = np.arccos(np.clip(cosine, -1., 1.))
            smooth_order = sorted(range(len(moving)), key=lambda index: (-angles[index], int(moving[index])))
            smooth_batch_size = max(1, (len(moving) + max(1, iterations) - 1) // max(1, iterations))
        for iteration in range(iterations if len(moving) else 0):
            current_source = _sample(terrain.elevation_m, points, terrain)[0]
            current_turn = turn_summary(points, receiver)["all_donor_turn_energy"]
            if phase == "smooth":
                first_index = iteration * smooth_batch_size
                for index in smooth_order[first_index:first_index + smooth_batch_size]:
                    node = int(moving[index])
                    smooth_node_visits[node] = smooth_node_visits.get(node, 0) + 1
                    neighbors = [int(incoming[node]), int(receiver[node])]
                    groups = [[node], [node] + [neighbor for neighbor in neighbors if not anchors[neighbor]]]
                    node_chosen = False
                    for group in groups:
                        group = np.array(group)
                        target = (points[incoming[group]] + points[receiver[group]]) / 2.
                        for strength in (.5, .25, .125, .0625):
                            if smooth_trials >= smooth_trial_limit:
                                break
                            smooth_trials += 1
                            trial = points.copy()
                            trial[group] += strength * (target - points[group])
                            try:
                                sampled, turns = admissible(trial, ceiling)
                            except ValueError as error:
                                refused.append(dict(phase=phase, iteration=iteration, strength=strength,
                                                    local=True, node_indices=group.tolist(), reason=str(error)))
                                continue
                            if turns["all_donor_turn_energy"] >= current_turn - 1e-10:
                                continue
                            points = trial
                            current_turn = turns["all_donor_turn_energy"]
                            accepted["smooth"] += 1
                            accepted["local"] += 1
                            smooth_node_acceptances[node] = smooth_node_acceptances.get(node, 0) + 1
                            node_chosen = True
                            break
                        if node_chosen or smooth_trials >= smooth_trial_limit:
                            break
                continue
            tangent = points[receiver[moving]] - points[incoming[moving]]
            normal = np.column_stack((-tangent[:, 1], tangent[:, 0])) / np.linalg.norm(tangent, axis=1)[:, None]
            offsets = np.linspace(-corridor_m, corridor_m, 25)
            samples = points[moving, None, :] + offsets[None, :, None] * normal[:, None, :]
            bounded = np.clip(samples, low, high)
            heights, cells = _sample(terrain.elevation_m, bounded.reshape(-1, 2), terrain)
            heights = heights.reshape(len(moving), -1)
            displacement = np.linalg.norm(samples - original[moving, None, :], axis=2)
            valid = np.all((samples >= low) & (samples <= high), axis=2)
            valid &= terrain.valid_mask.ravel()[cells].reshape(len(moving), -1)
            valid &= (displacement <= corridor_m + 1e-9) & (heights <= ceiling[moving, None])
            costs = heights + DISPLACEMENT_COST_M_PER_M2 * displacement ** 2
            costs[~valid] = np.inf
            target = bounded[np.arange(len(moving)), np.argmin(costs, axis=1)]
            chosen = False
            for strength in (0.5, 0.25, 0.125, 0.0625):
                candidate = points.copy()
                candidate[moving] += strength * (target - points[moving])
                offset = np.linalg.norm(candidate - original, axis=1)
                excessive = offset > corridor_m
                candidate[excessive] = original[excessive] + (
                    candidate[excessive] - original[excessive]
                ) * (corridor_m / offset[excessive, None])
                trials = [candidate]
                # Bounded local attempts permit an unaffected tributary to improve.
                groups = [np.array([moving[(iteration * 16 + index) % len(moving)]])
                          for index in range(min(16, len(moving)))]
                for group in groups:
                    local = points.copy()
                    local[group] = candidate[group]
                    trials.append(local)
                for number, trial in enumerate(trials):
                    try:
                        sampled, turns = admissible(trial, ceiling)
                    except ValueError as error:
                        refused.append(dict(phase=phase, iteration=iteration, strength=strength,
                                            local=number > 0, reason=str(error)))
                        continue
                    if float(np.mean(current_source - sampled)) <= 1e-10:
                        continue
                    points = trial
                    accepted[phase] += 1
                    accepted["local"] += int(number > 0)
                    chosen = True
                    break
                if chosen:
                    break
            if not chosen:
                break
    search_seconds = time.perf_counter() - started
    if certify is not None and not np.array_equal(points, baseline):
        final = points.copy()
        try:
            admissible(final, ceiling)
            run_certificate(final)
        except ValueError as error:
            refused.append(dict(phase="final_certificate", reason=str(error)))
            points = certified_terrain.copy()
            changed = np.linalg.norm(final - certified_terrain, axis=1) > 1e-12
            pending = []
            # Partition ordinary chains; pack short branches to reserve a first pass for all nodes.
            visited = np.zeros(len(points), bool)
            for start in moving:
                if not anchors[incoming[start]]:
                    continue
                chain = []
                node = int(start)
                while not anchors[node] and not visited[node]:
                    visited[node] = True
                    if changed[node]:
                        chain.append(node)
                    node = int(receiver[node])
                pending.extend(chain[index:index + 64] for index in range(0, len(chain), 64))
            for node in moving[~visited[moving] & changed[moving]]:
                pending.append([int(node)])
            if len(pending) > 64:
                packed = [[] for _ in range(64)]
                for index, group in enumerate(pending):
                    packed[index % 64].extend(group)
                pending = packed
            initial_certificate_batches = len(pending)
            pending = deque(pending)
            while pending:
                group = pending.popleft()
                if salvage_certificates >= salvage_certificate_limit:
                    salvage_unattempted_nodes.extend(group)
                    continue
                trial = points.copy()
                trial[group] = final[group]
                try:
                    admissible(trial, ceiling)
                    salvage_certificates += 1
                    run_certificate(trial)
                except ValueError as error:
                    refused.append(dict(phase="local_final_certificate", node_indices=group,
                                        reason=str(error)))
                    if len(group) > 1:
                        middle = len(group) // 2
                        pending.extend((group[:middle], group[middle:]))
                    else:
                        salvage_rejected_nodes.extend(group)
                    continue
                points = trial
                salvage_accepted_nodes.extend(group)
    final_turn = turn_summary(points, receiver)
    policy = dict(
        algorithm=ALGORITHM,
        supersedes_algorithm=SUPERSEDES_ALGORITHM,
        corridor_m=corridor_m, maximum_original_source_rise_m=0.5,
        smoothing_source_rise_budget_m=SMOOTH_SOURCE_RISE_M,
        valley_displacement_cost_m_per_m2=DISPLACEMENT_COST_M_PER_M2,
        coefficient_status="uncalibrated bounded engineering settings",
        objective_policy="terrain projection then all-donor dimensionless turn energy; ordinary and junction maximum turn cannot exceed the fixed entry-independent ceiling derived from the declared analytic bound",
        turn_bound_policy=TURN_BOUND_POLICY,
        declared_analytic_turn_bound_degrees=declared_ceiling_degrees,
        effective_turn_ceiling_degrees=dict(turn_ceiling_degrees),
        baseline_movable_turn_maxima_degrees=baseline_movable,
        baseline_exceeds_declared_analytic_bound=baseline_exceeds_declared_bound,
        entry_policy=ENTRY_POLICY,
        mean_source_height_policy="observed diagnostic only; smoothing acceptance uses local source ceilings, geometry, turn limits and complete physical profile certification",
        reference_policy=("saved reference actual nodes recorded as acceptance-alignment diagnostics only; never a search start"
                          if reference_points is not None else
                          "no saved reference supplied; deterministic legacy eight-pass six-metre initialization"),
        original_turns=original_turn,
        baseline_turns=baseline_turn, final_turns=final_turn,
        accepted_steps=accepted, refused_steps=refused,
        smooth_candidate_trials=smooth_trials, maximum_smooth_candidate_trials=smooth_trial_limit,
        smooth_coverage_policy="one curvature-ordered finite sweep of every movable ordinary node when iterations > 0",
        smooth_eligible_node_count=len(moving), smooth_visited_node_indices=sorted(smooth_node_visits),
        smooth_complete_ordinary_coverage=len(smooth_node_visits) == len(moving),
        smooth_accepted_node_indices=sorted(smooth_node_acceptances),
        continuous_certificate_calls=certificate_calls,
        final_certificate_recovery_policy="certified terrain base; at most 64 initial branch batches; FIFO binary splitting and 128 complete profile calls; preserve accepted batches",
        local_final_certificate_calls=salvage_certificates,
        maximum_local_final_certificate_calls=salvage_certificate_limit,
        initial_local_final_certificate_batches=initial_certificate_batches,
        local_final_accepted_node_indices=sorted(salvage_accepted_nodes),
        local_final_unattempted_node_indices=sorted(salvage_unattempted_nodes),
        local_final_rejected_node_indices=sorted(salvage_rejected_nodes),
        path_search_seconds=search_seconds, total_path_seconds=time.perf_counter() - started,
        original_mean_source_height_m=float(original_source.mean()),
        initialized_baseline_mean_source_height_m=float(baseline_source.mean()),
        reference_mean_source_height_m=float(reference_source.mean()),
        final_mean_source_height_m=float(_sample(terrain.elevation_m, points, terrain)[0].mean()),
        anchors="source, confluence and terminal nodes fixed exactly",
        reference_mean_source_height_semantics=(
            "mean sampled source height of the caller-supplied saved reference path when one was supplied; "
            "otherwise the deterministic initialized search baseline (no saved reference)"),
    )
    if reference_turn is not None:
        policy["reference_turns"] = reference_turn
        policy["reference_turn_regression"] = sorted(
            kind + " " + metric for kind in ("ordinary", "junction")
            for metric in ("maximum_degrees", "p95_degrees")
            if final_turn[kind][metric] > reference_turn[kind][metric] + 1e-7)
    policy["turn_bound_satisfied"] = all(
        final_turn[kind]["maximum_degrees"] <= limit + 1e-7
        for kind, limit in ANALYTIC_TURN_BOUND_DEGREES.items())
    policy["anchor_turn_exemption"] = anchor_turn_exemption(points, receiver)
    return points, policy
