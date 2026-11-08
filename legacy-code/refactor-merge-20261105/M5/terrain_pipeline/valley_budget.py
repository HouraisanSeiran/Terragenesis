"""Budget-only valley shaping and explicit recovery candidate diagnostics."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash


VERSION = "valley-budget-v1"


@dataclass(frozen=True)
class ValleyRecipe:
    valley_cut_m: float = 8.
    bed_cut_m: float = 4.
    total_area_cells: int = 10000
    protected_cut_m: float = 0.

    def __post_init__(self):
        for name in ("valley_cut_m", "bed_cut_m", "protected_cut_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if type(self.total_area_cells) is not int or self.total_area_cells <= 0:
            raise ValueError("total_area_cells must be positive")


def allocate_valley_budget(plan, protected_mask=None, joint=None, recipe=ValleyRecipe()):
    """Allocate bounded valley cuts around the planned bed without editing the source."""
    if not isinstance(recipe, ValleyRecipe) or plan.get("status") != "diagnostic_not_publishable":
        raise ValueError("diagnostic plan and recipe required")
    arrays = plan["arrays"]
    source = arrays["source_height_m"]
    shape = source.shape
    protected = np.zeros(shape, dtype=bool) if protected_mask is None else np.asarray(protected_mask)
    if protected.shape != shape or protected.dtype != bool:
        raise ValueError("protected mask must match plan grid")
    if not np.isfinite(source).all() or not np.isfinite(arrays["target_bed_m"]).all():
        raise ValueError("plan heights must be finite")
    active = arrays["channel_mask"]
    requested_valley = np.zeros(shape, dtype=np.float64)
    requested_valley[active] = np.maximum(0., source[active] - arrays["target_bed_m"][active])
    requested_bed = np.zeros(shape, dtype=np.float64)
    requested_bed[active] = np.minimum(recipe.bed_cut_m, requested_valley[active])
    protected_conflict = protected & (requested_valley > recipe.protected_cut_m + 1e-9)
    available = max(0, recipe.total_area_cells - int(np.count_nonzero(protected_conflict)))
    candidates = np.argwhere((requested_valley > 0) & ~protected)
    if len(candidates) > available:
        candidates = candidates[:available]
    selected = np.zeros(shape, dtype=bool)
    selected[tuple(candidates.T)] = True
    valley_allocation = np.where(selected, np.minimum(requested_valley, recipe.valley_cut_m), 0.)
    bed_allocation = np.where(selected, np.minimum(requested_bed, recipe.bed_cut_m), 0.)
    bed_remaining = np.maximum(0., requested_bed - bed_allocation)
    over_budget = (requested_valley > recipe.valley_cut_m + 1e-9) | (requested_bed > recipe.bed_cut_m + 1e-9) | (requested_valley > 0) & ~selected
    inherited = np.zeros(shape, dtype=bool)
    if joint is not None:
        inherited |= bool(not joint.get("pass", False))
    identity = ArtifactIdentity("Terragenesis", "valley-budget", VERSION, 0,
                                {**asdict(recipe), "plan_identity_sha256": plan["identity_sha256"],
                                 "source_height_sha256": array_hash(source),
                                 "target_bed_sha256": array_hash(arrays["target_bed_m"]),
                                 "protected_sha256": array_hash(protected)})
    outputs = {"requested_valley_cut_m": requested_valley,
               "requested_bed_cut_m": requested_bed,
               "valley_allocation_m": valley_allocation,
               "bed_allocation_m": bed_allocation,
               "remaining_bed_budget_m": bed_remaining,
               "over_budget_mask": over_budget,
               "protected_conflict_mask": protected_conflict,
               "selected_area_mask": selected}
    for value in outputs.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": outputs,
            "summary": {"requested_nodes": int(np.count_nonzero(requested_valley)),
                        "selected_nodes": int(np.count_nonzero(selected)),
                        "protected_conflict_nodes": int(np.count_nonzero(protected_conflict)),
                        "over_budget_nodes": int(np.count_nonzero(over_budget)),
                        "remaining_bed_budget_max_m": float(bed_remaining.max()),
                        "inherited_joint_blocker": bool(joint is not None and not joint.get("pass", False))}}


def plan_recovery(plan, blockers, candidate_routes=None, lake_spills=None):
    """Rank explicit recovery options; never alters the route or source terrain."""
    if plan is None or not isinstance(blockers, dict):
        raise ValueError("blockers must be a mapping")
    plan_identity = plan.get("identity_sha256")
    options = []
    if candidate_routes:
        for route in candidate_routes:
            bound = route.get("plan_identity_sha256") == plan_identity
            options.append({"kind": "reroute", "candidate": route,
                            "eligible": bound and not bool(route.get("crosses_protection", False)),
                            "reason": "candidate route is explicit and protection-compatible"})
    if lake_spills:
        for spill in lake_spills:
            bound = spill.get("plan_identity_sha256") == plan_identity
            options.append({"kind": "lake_spill", "candidate": spill,
                            "eligible": bound and bool(spill.get("legal_outlet", False)),
                            "reason": "requires an explicit legal outlet and balance check"})
    options.append({"kind": "failure", "candidate": None, "eligible": True,
                    "reason": "retain diagnostics when no explicit recovery satisfies constraints"})
    eligible = [option for option in options if option["eligible"]]
    chosen = eligible[0] if eligible else options[-1]
    return {"status": "diagnostic_not_publishable", "chosen": chosen,
            "options": options, "blockers": dict(blockers),
            "selection_reason": "first explicit eligible option; no hidden route or source mutation"}
