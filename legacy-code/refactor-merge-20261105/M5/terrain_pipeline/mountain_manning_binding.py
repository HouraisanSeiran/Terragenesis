"""Offline one-way replay of complete A lake/reach releases into a fixed study chain."""

import numpy as np

from terrain_pipeline.lake import validate_coupling as validate_coupling
from terrain_pipeline.common_infra import identity
from terrain_pipeline.mountain_manning_geometry import validate_tributary_geometry


def bind_saved_releases(coupling, source, topology, geometry, selection, record, *, dt_s):
    """No model advancement, bare accumulated runoff, or invented A river water level."""
    validate_tributary_geometry(record, geometry)
    validate_coupling(coupling, source=source, topology=topology, geometry=geometry, selection=selection)
    arrays, meta = coupling["arrays"], coupling["metadata"]
    if dt_s not in (15., 30.) or meta["runoff_metadata"]["dt_s"] != 900.:
        raise ValueError("fixed conservative 900s to 15/30s replay required")
    cells = record["arrays"]["chain_cells"]
    nodes = arrays["anchor_node"].ravel()[cells]
    if (nodes < 0).any() or len(set(nodes.tolist())) != 4:
        raise ValueError("A must explicitly anchor every study node")
    if any(meta["node_kind"][node] != "river" for node in nodes):
        raise ValueError("study chain crosses A lake or terminal")
    if not np.array_equal(arrays["node_downstream"][nodes[:-1]], nodes[1:]):
        raise ValueError("A river topology differs from study chain")
    if not np.array_equal(arrays["receiver"].ravel()[cells[:-1]], cells[1:]):
        raise ValueError("A geometric seam mismatch")
    intervals = 96
    if arrays["outflow_volume_m3"].shape[0] < intervals:
        raise ValueError("24h saved releases required; no extrapolation")
    inlet = arrays["outflow_volume_m3"][:intervals, nodes[0]].copy()
    lateral = np.zeros((intervals, 4), np.float64)
    side_nodes = []
    for index in range(1, 4):
        incoming = np.flatnonzero(arrays["node_downstream"] == nodes[index])
        external = incoming[incoming != nodes[index - 1]]
        if any(int(node) in nodes for node in external):
            raise ValueError("side release double counts chain")
        lateral[:, index] = arrays["lateral_volume_m3"][:intervals, nodes[index]]
        if external.size:
            lateral[:, index] += arrays["outflow_volume_m3"][:intervals, external].sum(axis=1)
        side_nodes.append(external.tolist())
    repeat = int(900 / dt_s)
    initial = record["arrays"]["min_bed_m"].copy()
    forcing = {"initial_stage_m": initial,
               "inlet_q_m3_s": np.repeat(inlet / 900., repeat),
               "lateral_q_m3_s": np.repeat(lateral / 900., repeat, axis=0),
               "tailwater_stage_m": np.full(intervals * repeat + 1, initial[-1]), "dt_s": dt_s}
    if not np.allclose(forcing["inlet_q_m3_s"].reshape(intervals, repeat).sum(axis=1) * dt_s,
                       inlet, atol=1e-10, rtol=1e-14):
        raise ValueError("inlet interval conservation")
    if not np.allclose(forcing["lateral_q_m3_s"].reshape(intervals, repeat, 4).sum(axis=1) * dt_s,
                       lateral, atol=1e-10, rtol=1e-14):
        raise ValueError("side interval conservation")
    upstream = np.zeros(arrays["node_downstream"].size, bool)
    upstream[nodes[0]] = True
    for node in arrays["node_order"][::-1]:
        target = arrays["node_downstream"][node]
        if target >= 0 and upstream[target]:
            upstream[node] = True
    upstream_cells = upstream[np.maximum(arrays["cell_node"], 0)] & arrays["hydrology_mask"]
    partition = np.full(arrays["node_downstream"].size, -1, np.int64)
    partition[nodes] = np.arange(4)
    for node in arrays["node_order"][::-1]:
        target = arrays["node_downstream"][node]
        if partition[node] < 0 and target >= 0:
            partition[node] = partition[target]
    cell_partition = np.full(arrays["cell_node"].shape, -1, np.int64)
    active = arrays["hydrology_mask"] & (arrays["cell_node"] >= 0)
    cell_partition[active] = partition[arrays["cell_node"][active]]
    flat, receiver = cell_partition.ravel(), arrays["receiver"].ravel()
    moving = np.flatnonzero((flat >= 0) & (receiver >= 0))
    nonanchors = moving[~np.isin(moving, cells)]
    if not np.array_equal(flat[nonanchors], flat[receiver[nonanchors]]):
        raise ValueError("saved contribution partition local recurrence")
    if not np.array_equal(flat[cells], np.arange(4)) or not np.array_equal(cell_partition == 0, upstream_cells):
        raise ValueError("first subtree partition identity")
    last_subtree = np.zeros(partition.size, bool)
    last_subtree[nodes[-1]] = True
    for node in arrays["node_order"][::-1]:
        target = arrays["node_downstream"][node]
        if target >= 0 and last_subtree[target]:
            last_subtree[node] = True
    if not np.array_equal(partition >= 0, last_subtree):
        raise ValueError("complete last-chain subtree not closed")
    result = {"forcing": forcing, "arrays": {"inlet_interval_volume_m3": inlet,
             "lateral_interval_volume_m3": lateral, "upstream_cell_mask": upstream_cells,
             "cell_partition": cell_partition, "node_partition": partition,
             "partition_counts": np.bincount(flat[flat >= 0], minlength=4)},
            "metadata": {"schema": "mountain-A-releases-to-tributary-v1",
              "source_identity": source["identity_sha256"],
              "A_coupling_identity": coupling["identity_sha256"],
              "study_geometry_identity": identity(record["arrays"], record["metadata"]),
              "inlet_node": int(nodes[0]), "chain_nodes": nodes.tolist(), "side_nodes": side_nodes,
              "upstream_cells": int(upstream_cells.sum()),
              "upstream_lake_nodes": [int(node) for node in np.flatnonzero(upstream) if meta["node_kind"][node] == "lake"],
              "inlet_includes_first_A_river_storage": True,
              "inlet_seam": "A_first_node_downstream_release_offline_alternative_with_extra_fine_residence_not_strict_replacement",
              "scope": "offline_one_way_nested_replay_not_joint_A_fine_solution",
              "storage_accounting": "independent alternative; never sum duplicated downstream A river storage with fine storage",
              "tailwater": "prescribed_last_support_minbed_engineering_diffusive_boundary_not_free_fall",
              "duration_s": 86400., "dt_s": dt_s}}
    validate_saved_binding(result, coupling, record)
    return result


def validate_saved_binding(bound, coupling, record):
    """Local saved partition recurrences and exact releases; never reassign ownership."""
    arrays, state, meta = bound["arrays"], coupling["arrays"], bound["metadata"]
    if meta["schema"] != "mountain-A-releases-to-tributary-v1" or meta["scope"] != "offline_one_way_nested_replay_not_joint_A_fine_solution":
        raise ValueError("saved binding scope/schema mismatch")
    nodes = state["anchor_node"].ravel()[record["arrays"]["chain_cells"]]
    if meta["A_coupling_identity"] != coupling["identity_sha256"] or meta["study_geometry_identity"] != identity(record["arrays"], record["metadata"]):
        raise ValueError("saved binding source mismatch")
    partition = arrays["node_partition"]
    if partition.shape != state["node_downstream"].shape or partition.dtype != np.int64 or ((partition < -1) | (partition > 3)).any():
        raise ValueError("saved node partition schema")
    if not np.array_equal(partition[nodes], np.arange(4)):
        raise ValueError("chain partition anchors")
    nonanchors = np.setdiff1d(np.arange(partition.size), nodes)
    target = state["node_downstream"][nonanchors]
    expected = np.full(nonanchors.size, -1, np.int64)
    expected[target >= 0] = partition[target[target >= 0]]
    if not np.array_equal(partition[nonanchors], expected):
        raise ValueError("saved node partition local recurrence")
    grid = arrays["cell_partition"]
    active = state["hydrology_mask"]
    if grid.dtype != np.int64 or grid.shape != active.shape or (grid[~active] != -1).any():
        raise ValueError("saved cell partition schema")
    if not np.array_equal(grid[active], partition[state["cell_node"][active]]):
        raise ValueError("saved cell/node partition provenance")
    counts = np.bincount(grid[grid >= 0], minlength=4)
    if not np.array_equal(arrays["partition_counts"], counts) or not np.array_equal(arrays["upstream_cell_mask"], grid == 0):
        raise ValueError("saved complete subtree counts")
    if meta["inlet_node"] != int(nodes[0]) or meta["upstream_cells"] != counts[0] or meta["source_identity"] != coupling["metadata"]["source_identity"]:
        raise ValueError("saved binding anchor/area/source mismatch")
    lake_nodes = [int(node) for node in np.flatnonzero(partition == 0) if coupling["metadata"]["node_kind"][node] == "lake"]
    if meta["upstream_lake_nodes"] != lake_nodes:
        raise ValueError("saved upstream lake inclusion mismatch")
    dt = meta["dt_s"]
    if dt not in (15., 30.) or meta["duration_s"] != 86400. or meta["chain_nodes"] != nodes.tolist():
        raise ValueError("saved binding time/chain identity")
    inlet = state["outflow_volume_m3"][:96, nodes[0]]
    lateral = np.zeros((96, 4))
    feeders = []
    for index in range(1, 4):
        external = np.flatnonzero((state["node_downstream"] == nodes[index]) & (np.arange(partition.size) != nodes[index - 1]))
        feeders.append(external.tolist())
        lateral[:, index] = state["lateral_volume_m3"][:96, nodes[index]] + state["outflow_volume_m3"][:96, external].sum(axis=1)
    if meta["side_nodes"] != feeders or not np.array_equal(arrays["inlet_interval_volume_m3"], inlet) or not np.array_equal(arrays["lateral_interval_volume_m3"], lateral):
        raise ValueError("saved release provenance mismatch")
    forcing = bound["forcing"]
    repeat = int(900 / dt)
    expected_forcing = {"initial_stage_m": record["arrays"]["min_bed_m"],
        "inlet_q_m3_s": np.repeat(inlet / 900., repeat),
        "lateral_q_m3_s": np.repeat(lateral / 900., repeat, axis=0),
        "tailwater_stage_m": np.full(96 * repeat + 1, record["arrays"]["min_bed_m"][-1])}
    for key, expected in expected_forcing.items():
        if not np.array_equal(forcing[key], expected):
            raise ValueError("saved forcing provenance mismatch: " + key)
    if forcing["dt_s"] != dt:
        raise ValueError("forcing timestep mismatch")
    return {"partition_cells": int(counts.sum()), "partition_counts": counts.tolist(),
            "inlet_volume_m3": float(inlet.sum()), "side_volume_m3": lateral.sum(axis=0).tolist()}
