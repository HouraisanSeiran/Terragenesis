"""World-coordinate channel assembly and regional accounting over existing solvers.

Regions own nodes, not river outlets. Halo copies are deduplicated by world identity.
This module does not implement an independent partitioned hydraulic solver.
"""
from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from terrain_pipeline.channel_geometry import validate_receiver_acyclic


def derive_noise_seed(world_seed, purpose):
    """Stable uint32 seed namespace, independent of Python hash/loading order."""
    if type(world_seed) is not int or not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("integer world seed and stable purpose required")
    payload = json.dumps(["terragenesis-world-noise-v1", world_seed, purpose],
                         ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def node_id(seed, x_m, z_m):
    values = (float(x_m), float(z_m))
    if not np.isfinite(values).all():
        raise ValueError("finite world coordinates required")
    return f"{int(seed)}:{values[0].hex()}:{values[1].hex()}"


@dataclass(frozen=True)
class WorldNode:
    seed: int
    x_m: float
    z_m: float
    receiver_id: str | None

    @property
    def identity(self):
        return node_id(self.seed, self.x_m, self.z_m)


def assemble_world_graph(records, region_size_m, *, origin_x_m=0., origin_z_m=0.):
    """Merge overlapping regional records; return canonical coordinate-sorted graph."""
    if not math.isfinite(region_size_m) or region_size_m <= 0.:
        raise ValueError("positive finite region size required")
    if not np.isfinite([origin_x_m, origin_z_m]).all():
        raise ValueError("finite region origin required")
    nodes = {}
    for record in records:
        if not isinstance(record, WorldNode):
            raise ValueError("WorldNode records required")
        key = record.identity
        if key in nodes and record != nodes[key]:
            raise ValueError("conflicting world-node receiver")
        nodes[key] = record
    ordered = sorted(nodes.values(), key=lambda n: (n.seed, n.x_m, n.z_m))
    if not ordered or len({n.seed for n in ordered}) != 1:
        raise ValueError("nonempty single-seed world graph required")
    ids = [n.identity for n in ordered]
    lookup = {key: index for index, key in enumerate(ids)}
    if any(n.receiver_id is not None and n.receiver_id not in lookup for n in ordered):
        raise ValueError("missing downstream world node")
    receiver = np.array([-1 if n.receiver_id is None else lookup[n.receiver_id] for n in ordered], np.int64)
    if np.any(receiver == np.arange(len(receiver))):
        raise ValueError("self receiver")
    validate_receiver_acyclic(receiver)
    coordinates = np.array([[n.x_m, n.z_m] for n in ordered], np.float64)
    owners = np.floor((coordinates - [origin_x_m, origin_z_m]) / region_size_m).astype(np.int64)
    regions = [f"{x}:{z}" for x, z in owners]
    crossings = [i for i, j in enumerate(receiver) if j >= 0 and regions[i] != regions[j]]
    edges = [ids[i] + "->" + ids[j] for i, j in enumerate(receiver) if j >= 0]
    declaration = dict(seed=int(ordered[0].seed), node_ids=ids, receiver=receiver.tolist(),
                       region_size_m=float(region_size_m), region_origin_m=[origin_x_m, origin_z_m])
    identity = hashlib.sha256(json.dumps(declaration, sort_keys=True).encode()).hexdigest()
    return dict(node_ids=ids, node_xz_m=coordinates, receiver=receiver,
                region_ids=regions, cross_region_donors=np.array(crossings, np.int64),
                edge_ids=edges, identity_sha256=identity, declaration=declaration)


def assemble_local_forcing(graph, time_seconds, sources):
    """Sources are (stable source id, world node id, interval Q); duplicates count once."""
    time = np.asarray(time_seconds, np.float64)
    if time.ndim != 1 or len(time) < 2 or not np.isfinite(time).all() or np.any(np.diff(time) <= 0.):
        raise ValueError("increasing finite physical times required")
    seen = {}
    lookup = {key: index for index, key in enumerate(graph["node_ids"])}
    result = np.zeros((len(time) - 1, len(lookup)), np.float64)
    for source_id, target, values in sources:
        rate = np.asarray(values, np.float64)
        if not isinstance(source_id, str) or not source_id or target not in lookup:
            raise ValueError("stable source id and known target required")
        if rate.shape != (len(time) - 1,) or not np.isfinite(rate).all() or np.any(rate < 0.):
            raise ValueError("nonnegative interval rates required")
        if source_id in seen:
            old_target, old_rate = seen[source_id]
            if target != old_target or not np.array_equal(rate, old_rate):
                raise ValueError("conflicting duplicate local source")
            continue
        seen[source_id] = target, rate.copy()
        result[:, lookup[target]] += rate
    return result


def regional_exchange(graph, outgoing_volume):
    """Pair every saved internal-edge volume as donor debit / receiver credit.

    outgoing_volume is solver-integrated step-by-node water or solid volume. It is
    never added to local forcing: the existing global graph already transported it.
    """
    outgoing = np.asarray(outgoing_volume, np.float64)
    n = len(graph["receiver"])
    if outgoing.ndim != 2 or outgoing.shape[1] != n or not np.isfinite(outgoing).all() or np.any(outgoing < 0.):
        raise ValueError("nonnegative step-node volume required")
    regions = sorted(set(graph["region_ids"]))
    index = {key: i for i, key in enumerate(regions)}
    incoming = np.zeros((len(outgoing), len(regions)))
    exported = np.zeros_like(incoming)
    transfers = []
    for donor in graph["cross_region_donors"]:
        target = graph["receiver"][donor]
        source_region, target_region = graph["region_ids"][donor], graph["region_ids"][target]
        values = outgoing[:, donor]
        exported[:, index[source_region]] += values
        incoming[:, index[target_region]] += values
        transfers.append(dict(edge_id=graph["node_ids"][donor] + "->" + graph["node_ids"][target],
                              donor=int(donor), receiver=int(target),
                              from_region=source_region, to_region=target_region,
                              total_volume_m3=float(values.sum())))
    return dict(region_ids=regions, incoming_m3=incoming, outgoing_m3=exported,
                edge_transfers=transfers)
