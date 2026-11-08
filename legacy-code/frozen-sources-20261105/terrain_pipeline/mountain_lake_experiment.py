"""Bounded authentic leaf-catchment forcing into the existing single-pool solver."""

import numpy as np
from scipy import ndimage

from terrain_pipeline.lake_routing import LakeRoutingRecipe, evaluate_lake_routing


MAX_STEPS = 1344
MAX_CANDIDATES = 64
MAX_LAKE_WORK = 4000000


def first_lake_ownership(result):
    """Full-window first lake mapping, not downstream accumulated-Q injection."""
    arrays = result["arrays"]
    labels = arrays["lake_id"].ravel()
    receiver = arrays["receiver"]
    first = np.zeros(receiver.size, dtype=np.int64)
    for cell in arrays["order"]:
        if labels[cell] > 0:
            first[cell] = labels[cell]
        elif receiver[cell] >= 0:
            first[cell] = first[receiver[cell]]
    return first.reshape(arrays["H0_m"].shape)


def select_leaf_pool(result, screening):
    """Largest complete local contributing area, no omitted upstream lake input."""
    arrays = result["arrays"]
    ownership = first_lake_ownership(result)
    count = arrays["lake_stage_m"].size
    contributions = np.bincount(ownership.ravel(), minlength=count + 1)
    upstream = np.bincount(arrays["lake_downstream_id"][arrays["lake_downstream_id"] > 0], minlength=count + 1)
    candidates = []
    for decision in screening["decisions"]:
        lake = decision["lake_id"]
        if decision["status"] != "single_pool_static_candidate" or upstream[lake] > 0:
            continue
        candidates.append((int(contributions[lake]), lake, decision))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return {"first_lake_id": ownership, "upstream_lake_count": upstream[1:],
            "local_contribution_cells": contributions[1:],
            "candidates": [item[2] for item in candidates],
            "selected": candidates[0][2] if candidates else None,
            "selection_rule": "all_event_single_pool_and_no_upstream_lakes_then_max_complete_local_area"}


def select_leaf_transfer(result, screening):
    """Single-pool leaf to explicit receiving-lake storage, including full local area."""
    arrays = result["arrays"]
    first = first_lake_ownership(result)
    count = arrays["lake_stage_m"].size
    contributions = np.bincount(first.ravel(), minlength=count + 1)
    upstream = np.bincount(arrays["lake_downstream_id"][arrays["lake_downstream_id"] > 0], minlength=count + 1)
    candidates = []
    refusals = []
    for decision in screening["decisions"]:
        lake = decision["lake_id"]
        if decision.get("disconnected_events", 1) or upstream[lake] > 0:
            continue
        flags = decision.get("reason_flags", [])
        if any(flag not in ("downstream_lake_requires_cascade", "downstream_not_strictly_lower") for flag in flags):
            continue
        path = list(decision["downstream_path"])
        target = int(arrays["receiver"][path[-1]])
        if target < 0 or arrays["lake_id"].flat[target] <= 0:
            continue
        path.append(target)
        if np.any(np.diff(arrays["H0_m"].ravel()[path]) > 1e-9):
            refusals.append({"lake_id": lake, "reason": "leaf_transfer_path_uphill"})
            continue
        receiving_lake = int(arrays["lake_id"].flat[target])
        capacity = float(arrays["lake_capacity_m3"][receiving_lake - 1])
        pool = arrays["lake_id"] == lake
        shore = ndimage.binary_dilation(pool, structure=ndimage.generate_binary_structure(2, 1)) & ~pool
        shore.flat[decision["spill_outside"]] = False
        gap = float(arrays["H0_m"][shore].min() - arrays["lake_stage_m"][lake - 1])
        if gap <= 1e-9:
            refusals.append({"lake_id": lake, "reason": "no_exclusive_single_spill_headroom"})
            continue
        proposal = dict(decision, downstream_path=path, receiving_lake_id=receiving_lake,
                        receiving_capacity_m3=capacity, local_contribution_cells=int(contributions[lake]),
                        upstream_lakes=[], shore_gap_m=gap)
        candidates.append(proposal)
    candidates.sort(key=lambda item: (-item["local_contribution_cells"], item["lake_id"]))
    return {"candidates": candidates[:MAX_CANDIDATES], "refusals": refusals,
            "first_lake_id": first, "upstream_lake_count": upstream[1:],
            "local_contribution_cells": contributions[1:],
            "selection_rule": "all_event_connected_no_upstream_lake_then_max_complete_area_to_receiving_storage",
            "max_candidates": MAX_CANDIDATES}


def run_leaf_lake(result, selected, *, local_q_m3_s, cell_owner, hru_area_m2, dt_s=900.,
                  volume_abs_tolerance_m3=1e-6):
    """Dry initial engineering pool, genuine first-lake runoff; no new rainfall model."""
    arrays, metadata = result["arrays"], result["metadata"]
    height = arrays["H0_m"]
    lake = selected["lake_id"]
    if local_q_m3_s.dtype != np.dtype("float64") or local_q_m3_s.ndim != 2 or not 1 <= local_q_m3_s.shape[0] <= MAX_STEPS:
        raise ValueError("bounded authentic interval forcing required")
    if not np.isfinite(local_q_m3_s).all() or (local_q_m3_s < 0).any() or cell_owner.shape != height.shape:
        raise ValueError("invalid local forcing")
    basin = arrays["lake_id"] == lake
    owned = first_lake_ownership(result) == lake
    if (arrays["lake_downstream_id"] == lake).any():
        raise ValueError("upstream lake outflows would be omitted")
    counts = np.bincount(cell_owner[owned], minlength=hru_area_m2.size)
    fractions = counts * metadata["spacing_m"] ** 2 / hru_area_m2
    inflow = local_q_m3_s @ fractions
    spill = np.unravel_index(selected["spill_outside"], height.shape)
    path_flat = np.asarray(selected["downstream_path"], dtype=np.int64)
    if path_flat.size < 2:
        raise ValueError("complete downstream route required")
    path = np.column_stack(np.unravel_index(path_flat, height.shape))
    shore = ndimage.binary_dilation(basin, structure=ndimage.generate_binary_structure(2, 1)) & ~basin
    shore[spill] = False
    stage = float(height[spill])
    gap = float(height[shore].min() - stage)
    if gap <= 1e-9:
        return {"status": "refused", "reason": "no_exclusive_single_spill_headroom", "lake_id": lake, "shore_gap_m": gap}
    maximum_stage = stage + min(1.0, gap * .5)
    if maximum_stage <= stage:
        raise ValueError("no representable stage headroom")
    rating_stages = np.linspace(stage, maximum_stage, 129)
    rating_rates = 1.7 * metadata["spacing_m"] * np.maximum(rating_stages - stage, 0.) ** 1.5
    recipe = LakeRoutingRecipe(initial_stage_m=float(height[basin].min()), dt_s=float(dt_s),
        inflow_m3_s=tuple(map(float, inflow)), loss_m3_s=tuple(np.zeros(inflow.size)),
        rating_stage_m=tuple(map(float, rating_stages)), rating_outflow_m3_s=tuple(map(float, rating_rates)),
        max_stage_m=maximum_stage, max_grid_cells=250000,
        volume_abs_tolerance_m3=volume_abs_tolerance_m3)
    legal = arrays["boundary_mask"].copy()
    receiving_lake = selected.get("receiving_lake_id")
    if receiving_lake is not None:
        legal[:] = False
        legal[tuple(path[-1])] = True
    evidence = evaluate_lake_routing(height, basin, spill, metadata["spacing_m"], metadata["spacing_m"],
        metadata["H0_sha256"], recipe, path, np.ones(height.shape, dtype=bool), arrays["protected_mask"],
        legal, *metadata["origin_m_xz"], "legacy_shifted_sea_zero_m")
    returned = {"status": evidence["diagnostic"]["code"], "lake_id": lake,
            "scope": "authentic_complete_leaf_local_catchment_not_whole_window_dynamics",
            "initial_storage_m3": 0., "upstream_lakes": [],
            "owned_area_m2": float(counts.sum() * metadata["spacing_m"] ** 2),
            "allocation_counts": counts, "first_lake_owned_mask": owned,
            "local_q_m3_s": inflow, "shore_gap_m": gap,
            "rating_assumption": "engineering_weir_Q=1.7*b*head^1.5_b=one_full_grid_edge_129_piecewise_linear_nodes_not_calibrated",
            "weir_coefficient_m_half_per_s": 1.7, "weir_width_m": metadata["spacing_m"],
            "max_valid_head_m": maximum_stage - stage,
            "evidence": evidence}
    if receiving_lake is not None:
        transfer = evidence["arrays"]["step_outflow_volume_m3"]
        storage = np.r_[0., np.cumsum(transfer)]
        capacity = float(arrays["lake_capacity_m3"][receiving_lake - 1])
        completed = evidence["summary"]["completed_steps"]
        incoming = inflow[:completed] * dt_s
        leaf_storage = evidence["arrays"]["storage_m3"]
        residual = incoming - np.diff(leaf_storage) - np.diff(storage)
        returned["terminal"] = {"type": "receiving_lake_incremental_storage_no_stage_claim",
                                "lake_id": receiving_lake, "capacity_m3": capacity,
                                "storage_m3": storage, "transfer_volume_m3": transfer.copy(),
                                "combined_step_residual_m3": residual,
                                "capacity_exceeded": bool((storage > capacity + 1e-6).any()),
                                "other_catchments": "outside_leaf_transfer_experiment_not_silently_zero_for_whole_window"}
        if returned["terminal"]["capacity_exceeded"]:
            returned["status"] = "receiving_storage_capacity_exceeded"
    return returned
