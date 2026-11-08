"""Explicit finite rerouting proposal/commit after a declared bed change.

This reassigns drainage ownership on the actual irregular graph. Water and
solid stocks retain native-cell ownership and are not duplicated or teleported.
It does not certify long-term natural river capture or watershed migration.
"""
import hashlib

import numpy as np

from terrain_pipeline.environment_context import array, context_arrays
from terrain_pipeline.drainage import segments_clear as segments_clear
from terrain_pipeline.drainage import strict_receivers as strict_receivers
from terrain_pipeline.drainage import route_graph as route_graph

ALGORITHM = "environment-finite-network-transition-v1"
INVENTORIES = ("water_m3", "sediment_solid_m3", "floodplain_solid_m3")


def _identity(arrays):
    digest = hashlib.sha256()
    for name, value in sorted(arrays.items()):
        data = np.ascontiguousarray(value)
        digest.update(name.encode("ascii"))
        digest.update(str((data.dtype.str, data.shape)).encode("ascii"))
        digest.update(data.tobytes())
    return digest.hexdigest()


def _owners(height, receiver, valid):
    owners = np.full(height.size, -1, np.int64)
    rec = receiver.ravel()
    linked = rec >= 0
    indegree = np.bincount(rec[linked], minlength=height.size)
    order = list(np.flatnonzero(indegree == 0))
    for node in order:
        if rec[node] >= 0:
            indegree[rec[node]] -= 1
            if indegree[rec[node]] == 0:
                order.append(int(rec[node]))
    if len(order) != height.size:
        raise ValueError("receiver graph must be acyclic")
    for node in reversed(order):
        if valid.ravel()[node]:
            target = receiver.ravel()[node]
            owners[node] = node if target < 0 else owners[target]
    return owners.reshape(height.shape)


def initial_state(context, *, water_m3=0., sediment_solid_m3=0., floodplain_solid_m3=0.):
    height, masks, _, receiver = context_arrays(context, 1.)
    state = {"height_m": height.copy(), "receiver": receiver.reshape(height.shape).copy(),
             "owner_terminal_cell": _owners(height, receiver, masks["valid_mask"])}
    for name, value in zip(INVENTORIES, (water_m3, sediment_solid_m3, floodplain_solid_m3)):
        state[name] = array(value, height.shape, name)
        if np.any(state[name][~masks["valid_mask"]] != 0.):
            raise ValueError("inventory outside valid support")
    return state


def _bound_state(state, context, dt_s):
    height, masks, mesh, receiver = context_arrays(context, dt_s)
    if not np.array_equal(state["height_m"], height) or not np.array_equal(state["receiver"].ravel(), receiver):
        raise ValueError("state graph does not match current context; update context after commit")
    result = initial_state(context, **{name: state[name] for name in INVENTORIES})
    if not np.array_equal(state["owner_terminal_cell"], result["owner_terminal_cell"]):
        raise ValueError("old ownership does not match graph")
    return result, masks, mesh


def step(initial_state, forcing, context, dt_s):
    state, masks, mesh = _bound_state(initial_state, context, dt_s)
    height = state["height_m"]
    change = array(forcing.get("bed_change_m", 0.), height.shape, "bed_change_m", nonnegative=False)
    if np.any(change[~masks["valid_mask"] | masks["protected_mask"]] != 0.):
        raise ValueError("bed change on invalid/protected terrain")
    proposed_height = height + change
    baseline_receiver = state["receiver"].copy()
    if not np.any(change):
        receiver = state["receiver"].ravel().copy()
    else:
        if context.get("routing_policy", "strict_candidate") == "source_terminal_flood":
            outlets = np.asarray(context["source_terminal_mask"], bool) | masks["ocean_mask"] | ~masks["valid_mask"]
            receiver = route_graph(proposed_height, outlets, mesh).receiver.copy()
            baseline_receiver = route_graph(height, outlets, mesh).receiver.copy().reshape(height.shape)
        else:
            receiver, _, _ = strict_receivers(proposed_height, mesh,
                                              valid_mask=masks["valid_mask"], outlet_mask=masks["ocean_mask"])
            baseline_receiver = strict_receivers(height, mesh, valid_mask=masks["valid_mask"],
                                                  outlet_mask=masks["ocean_mask"])[0].reshape(height.shape)
    donors = np.flatnonzero(receiver >= 0)
    blocked = donors[~segments_clear(donors, receiver[donors], masks["valid_mask"])]
    receiver[blocked] = -1
    receiver = receiver.reshape(height.shape)
    owners = _owners(proposed_height, receiver, masks["valid_mask"])
    baseline_owner = _owners(height, baseline_receiver, masks["valid_mask"])
    old_owner = state["owner_terminal_cell"]
    changed = masks["valid_mask"] & (owners != old_owner)
    proposed = {"height_m": proposed_height, "receiver": receiver, "owner_terminal_cell": owners}
    events = {"previous_owner_terminal_cell": old_owner.copy(),
              "proposed_owner_terminal_cell": owners, "owner_changed_mask": changed,
              "receiver_changed_mask": receiver != state["receiver"],
              "baseline_policy_receiver": baseline_receiver,
              "baseline_policy_changed_mask": baseline_receiver != state["receiver"],
              "bed_induced_receiver_changed_mask": receiver != baseline_receiver,
              "baseline_policy_owner_terminal_cell": baseline_owner,
              "bed_induced_owner_changed_mask": masks["valid_mask"] & (owners != baseline_owner),
              "proposed_height_m": proposed_height, "proposed_receiver": receiver,
              "unresolved_blocked_receiver_mask": np.isin(np.arange(height.size), blocked).reshape(height.shape)}
    events.update({"reassigned_" + name: np.where(changed, state[name], 0.) for name in INVENTORIES})
    return {"state": state, "fluxes": events,
            "ledger": {name + "_residual": 0. for name in INVENTORIES},
            "metadata": {"algorithm": ALGORITHM, "status": "proposal_requires_explicit_commit",
                         "dt_s": float(dt_s), "source_state_sha256": _identity(state),
                         "previous_graph_sha256": _identity({name: state[name] for name in proposed}),
                         "proposed_graph_sha256": _identity(proposed),
                         "world_seed": int(context["world_seed"]),
                         "origin_native_xz": list(context["origin_native_xz"]),
                         "spacing_m": float(context["spacing_m"]),
                         "changed_owner_cells": int(changed.sum()),
                         "baseline_policy_changed_edges": int(np.count_nonzero(baseline_receiver != state["receiver"])),
                         "bed_induced_changed_edges": int(np.count_nonzero(receiver != baseline_receiver)),
                         "bed_induced_changed_owner_cells": int(np.count_nonzero(masks["valid_mask"] & (owners != baseline_owner))),
                         "routing_policy": context.get("routing_policy", "strict_candidate"),
                         "previous_routing_policy": context.get("active_routing_policy", "delivered_source"),
                         "routing_policy_transition": bool(np.any(change) and context.get("active_routing_policy", "delivered_source") != context.get("routing_policy", "strict_candidate")),
                         "limitations": ["finite declared routing-policy comparison after bed change",
                                         "unresolved mask-crossing links stay explicit sinks, not natural outlets",
                                         "first finite-policy commit can include a declared routing-policy change; not attributed solely to bed erosion",
                                         "no long-term natural capture certification"]}}


def commit_transition(initial_state, proposal, context):
    """Validate a proposal against the current source and return a copied commit."""
    metadata = proposal["metadata"]
    state, _, _ = _bound_state(initial_state, context, metadata["dt_s"])
    if _identity(state) != metadata["source_state_sha256"]:
        raise ValueError("stale proposal source state")
    bed_change = proposal["fluxes"]["proposed_height_m"] - state["height_m"]
    replay = step(state, {"bed_change_m": bed_change}, context, metadata["dt_s"])
    if replay["metadata"] != metadata:
        raise ValueError("proposal identity/frame mismatch")
    if set(replay["fluxes"]) != set(proposal["fluxes"]) or any(
            not np.array_equal(value, proposal["fluxes"][name]) for name, value in replay["fluxes"].items()):
        raise ValueError("proposal graph/events mismatch")
    committed = {name: value.copy() for name, value in state.items()}
    committed["height_m"] = replay["fluxes"]["proposed_height_m"].copy()
    committed["receiver"] = replay["fluxes"]["proposed_receiver"].copy()
    committed["owner_terminal_cell"] = replay["fluxes"]["proposed_owner_terminal_cell"].copy()
    return {"state": committed, "fluxes": replay["fluxes"], "ledger": replay["ledger"],
            "metadata": {**metadata, "status": "committed_separate_revision"}}
