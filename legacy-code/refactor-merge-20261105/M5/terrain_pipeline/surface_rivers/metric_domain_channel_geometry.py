"""Adapter from one finite domain topology to channel geometry.

This module deliberately handles one already selected, finite domain only.  It does
not construct an infinite river graph and it refuses receivers that leave the
selected core instead of turning a missing neighbour into a terminal.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from .metric_channel_geometry import build_channel_geometry, validate_channel_geometry
from terrain_pipeline.common_infra import TerrainGrid

SCHEMA = "river-domain-channel-geometry-adapter-v1"
ALGORITHM = "domain-channel-geometry-adapter-v1"
LIMITATIONS = (
    "finite world-anchored tile and selected core domain only",
    "receivers outside the selected core are refused as unresolved_border",
    "does not certify an infinite or cross-tile main river network",
    "underlying channel geometry remains hydraulic_ready=false and publishable=false",
)


def build_domain_channel_geometry(terrain: TerrainGrid, topology: dict, *,
                                 node_cell_ids, receiver, width_m, depth_m,
                                 owner_xz_m, owner_grid, corridor_mask, lake_mask,
                                 anchor_mask, outlet_x_m, outlet_z_m,
                                 terminal_kind, config=None, lake_stage_m=None):
    """Build one finite domain's canonical channel geometry.

    ``node_cell_ids`` are flattened ``[z,x]`` ids in ``terrain`` and must be the
    accepted core cells of one outlet.  All masks and ``owner_xz_m`` are explicit
    same-shape inputs; the adapter refuses to infer lake or border semantics from
    labels.  ``receiver`` is local to that node list; use ``-1`` only for a known
    terminal.  A receiver omitted from the selected domain is unresolved, not a mouth.
    """
    if not isinstance(terrain, TerrainGrid) or not isinstance(topology, dict):
        raise ValueError("TerrainGrid and topology mapping required")
    ids = np.asarray(node_cell_ids, np.int64).reshape(-1)
    local_receiver = np.asarray(receiver, np.int64).reshape(-1)
    width = np.asarray(width_m, np.float64).reshape(-1)
    depth = np.asarray(depth_m, np.float64).reshape(-1)
    n = ids.size
    if n < 2 or any(a.size != n for a in (local_receiver, width, depth)):
        raise ValueError("domain channel arrays must have the same size and at least two nodes")
    if np.any(ids < 0) or np.any(ids >= terrain.elevation_m.size) or np.unique(ids).size != n:
        raise ValueError("node_cell_ids must be unique terrain cell ids")
    if not (np.isfinite(width).all() and np.isfinite(depth).all()) or np.any(width <= 0) or np.any(depth < 0):
        raise ValueError("width must be positive and depth nonnegative")
    if np.any(local_receiver >= n) or np.any(local_receiver < -1):
        raise ValueError("receiver outside selected domain: unresolved_border")

    if terminal_kind not in {"ocean", "closed_basin"}:
        raise ValueError("unsupported terminal classification: %s" % terminal_kind)
    shape = terrain.elevation_m.shape
    if not np.array_equal(np.asarray(topology.get("height_m")), terrain.elevation_m):
        raise ValueError("topology height and TerrainGrid height differ")
    accepted = np.asarray(topology.get("accepted"), bool)
    if accepted.shape != shape:
        raise ValueError("topology.accepted shape mismatch")
    if not accepted.reshape(-1)[ids].all():
        raise ValueError("domain nodes must be accepted core cells")
    accepted = np.asarray(topology.get("accepted"), bool)
    topology_owner_x = np.asarray(topology.get("owner_outlet_x_m"), np.float64)
    topology_owner_z = np.asarray(topology.get("owner_outlet_z_m"), np.float64)
    ocean_terminal = np.asarray(topology.get("ocean_terminal"), bool)
    if any(a.shape != shape for a in (accepted, topology_owner_x, topology_owner_z, ocean_terminal)):
        raise ValueError("topology accepted/owner/ocean arrays must match TerrainGrid")
    if not accepted.reshape(-1)[ids].all():
        raise ValueError("domain nodes must be accepted core cells (out_of_tile or refused cells rejected)")
    owner_points = np.asarray(owner_xz_m, np.float64)
    owner = np.asarray(owner_grid, np.int64)
    corridor = np.asarray(corridor_mask)
    lake = np.asarray(lake_mask)
    anchor = np.asarray(anchor_mask)
    if (owner_points.shape != (n, 2) or not np.isfinite(owner_points).all()
            or owner.shape != shape or corridor.dtype != bool or corridor.shape != shape
            or lake.dtype != bool or lake.shape != shape
            or anchor.dtype != bool or anchor.shape != (n,)):
        raise ValueError("explicit owner/corridor/lake/anchor inputs must match terrain and nodes")
    domain_key = (float(outlet_x_m), float(outlet_z_m))
    if not np.isfinite(domain_key).all():
        raise ValueError("finite outlet world coordinates required")
    if (not np.all(topology_owner_x.reshape(-1)[ids] == domain_key[0])
            or not np.all(topology_owner_z.reshape(-1)[ids] == domain_key[1])
            or not np.all(owner_points == domain_key)):
        raise ValueError("nodes do not share the requested topology outlet identity")
    actual_ocean = ocean_terminal.reshape(-1)[ids[local_receiver < 0]]
    if actual_ocean.size and np.any(actual_ocean != (terminal_kind == "ocean")):
        raise ValueError("terminal classification disagrees with topology (ocean/coastal/closed_basin)")
    if terminal_kind == "ocean" and lake.reshape(-1)[ids[local_receiver < 0]].any():
        raise ValueError("ocean terminals cannot be inferred as lakes; supply geometry-specific policy")
    if terminal_kind == "closed_basin" and not lake.reshape(-1)[ids[local_receiver < 0]].all():
        raise ValueError("closed-basin terminal requires explicit lake support")
    topology_receiver = np.asarray(topology.get("receiver"), np.int64).reshape(-1)
    if topology_receiver.size != terrain.elevation_m.size:
        raise ValueError("topology.receiver shape mismatch")
    links = np.flatnonzero(local_receiver >= 0)
    if links.size and not np.array_equal(topology_receiver[ids[links]], ids[local_receiver[links]]):
        raise ValueError("local receiver differs from domain topology")
    if links.size:
        receiver_ids = ids[local_receiver[links]]
        if np.any(owner.reshape(-1)[receiver_ids] != owner.reshape(-1)[ids[links]]):
            raise ValueError("receiver crosses domain ownership")
    geometry = build_channel_geometry(
        terrain, ids, local_receiver, width, depth, owner_grid=owner,
        corridor_mask=corridor, lake_mask=lake, anchor_mask=anchor,
        config=config, lake_stage_m=lake_stage_m)
    metadata = {
        "schema": SCHEMA, "algorithm": ALGORITHM,
        "source_terrain_identity_sha256": terrain.identity_sha256,
        "channel_geometry_identity_sha256": geometry["identity_sha256"],
        "outlet_x_m": domain_key[0], "outlet_z_m": domain_key[1],
        "terminal_kind": terminal_kind, "node_count": int(n),
        "topology_shape_zx": [int(terrain.elevation_m.shape[0]), int(terrain.elevation_m.shape[1])],
        "channel_metadata": geometry["metadata"],
        "limitations": list(LIMITATIONS),
        "hydraulic_ready": False, "publishable": False,
    }
    arrays = {"channel_" + key: value for key, value in geometry["arrays"].items()}
    record = {"arrays": arrays, "metadata": metadata}
    record["identity_sha256"] = identity(arrays, metadata)
    return record


def validate_domain_channel_geometry(record):
    if not isinstance(record, dict) or set(record) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid domain channel geometry bundle")
    arrays = record["arrays"]
    metadata = record["metadata"]
    if metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM:
        raise ValueError("domain channel geometry schema mismatch")
    geometry_arrays = {key[len("channel_"):]: value for key, value in arrays.items()
                       if key.startswith("channel_")}
    geometry = {"arrays": geometry_arrays, "metadata": metadata.get("channel_metadata"),
                "identity_sha256": metadata.get("channel_geometry_identity_sha256")}
    validate_channel_geometry(geometry)
    if tuple(metadata.get("limitations", ())) != LIMITATIONS:
        raise ValueError("domain channel geometry limitations mismatch")
    if metadata.get("hydraulic_ready") is not False or metadata.get("publishable") is not False:
        raise ValueError("domain channel geometry cannot claim hydraulic or publishable status")
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError("domain channel geometry identity mismatch")
    return True


def save_domain_channel_geometry(path, record):
    save_bundle(path, record, validator=validate_domain_channel_geometry)


def load_domain_channel_geometry(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256,
                       validator=validate_domain_channel_geometry)
