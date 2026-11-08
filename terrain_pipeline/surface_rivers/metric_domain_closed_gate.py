"""Read-only finite-tile publication gate; never changes closure or readiness.

Only domains selected by points are checked. A selected domain is accepted when its
stored receiver chains close within the built tile (core plus margin). Margin members
are permitted even though domain products retain their existing core-only clipping.
"""
from __future__ import annotations

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.surface_rivers.metric_domain_closure import domain_topology
from terrain_pipeline.surface_rivers.metric_domain_pipeline import REASON_ORDER


def check_topology_closed(topology, points_xz_m):
    """Check selected domains against an existing closure snapshot, without writes.

    Counts distinguish input points (including duplicates) from selected domains.
    Ocean is still a resolved non-domain, not a boundary failure. Stored-chain
    failures use the existing ``unresolved_border`` reason, never a new kind.
    """
    shape = tuple(topology["shape"])
    core = np.asarray(topology["in_core"], bool).reshape(-1)
    accepted = np.asarray(topology["accepted"], bool).reshape(-1)
    ocean = np.asarray(topology["ocean"], bool).reshape(-1)
    unresolved = np.asarray(topology["unresolved"], bool).reshape(-1)
    terminal = np.asarray(topology["terminal"], np.int64).reshape(-1)
    receiver = np.asarray(topology["receiver"], np.int64).reshape(-1)
    owner_x = np.asarray(topology["owner_outlet_x_m"]).reshape(-1)
    owner_z = np.asarray(topology["owner_outlet_z_m"]).reshape(-1)
    spacing = float(topology["spacing_m"])
    domains = {}
    points = []
    for x, z in points_xz_m:
        x, z = float(x), float(z)
        if not np.isfinite([x, z]).all():
            raise ValueError("points must be finite")
        row = int(np.rint((z - topology["origin_z_m"]) / spacing))
        col = int(np.rint((x - topology["origin_x_m"]) / spacing))
        position = row * shape[1] + col
        key = None
        if not (0 <= row < shape[0] and 0 <= col < shape[1]):
            reason = "out_of_tile"
        elif not core[position] or unresolved[position]:
            reason = "unresolved_border"
        elif ocean[position]:
            reason = "ocean"
        elif not accepted[position]:
            reason = "unresolved_border"
        else:
            key = (float(owner_x[position]), float(owner_z[position]))
            if not np.isfinite(key).all():
                raise ValueError("accepted owner must be finite")
            if key not in domains:
                target = int(terminal[position])
                # Check every finite-tile land member assigned to this terminal,
                # including margin. The publication is explicitly tile-bounded; it
                # does not claim anything about unknown upstream beyond this tile.
                owner_members = (owner_x == key[0]) & (owner_z == key[1])
                tile_members = ((~ocean) & (terminal == target)) | (accepted & owner_members)
                margin_count = int(np.count_nonzero(tile_members & ~core))
                target_row, target_col = divmod(target, shape[1])
                target_world = (topology["origin_x_m"] + target_col * spacing,
                                topology["origin_z_m"] + target_row * spacing)
                valid = (0 <= target < core.size and not unresolved[target]
                         and target_world == key)
                for start in np.flatnonzero(tile_members):
                    current = int(start)
                    seen = set()
                    while valid:
                        if (current < 0 or current >= core.size or current in seen
                                or unresolved[current] or terminal[current] != target):
                            valid = False
                            break
                        seen.add(current)
                        downstream = int(receiver[current])
                        if downstream == -1:
                            valid = current == target
                            break
                        current = downstream
                    if not valid:
                        break
                kind = "coastal" if (0 <= target < core.size and ocean[target]) else "closed_basin"
                domains[key] = {
                    "outlet_xz_m": list(key), "kind": kind,
                    "core_members": int(np.count_nonzero(tile_members & core)),
                    "margin_members": margin_count, "accepted": bool(valid),
                    "reason": kind if valid else "unresolved_border",
                }
            reason = domains[key]["reason"]
        points.append({"x_m": x, "z_m": z, "reason": reason,
                       "accepted": key is not None and domains[key]["accepted"]})
    records = [domains[key] for key in sorted(domains)]
    return _report(points, records)


def _report(points, domains):
    tally = {reason: sum(point["reason"] == reason for point in points)
             for reason in REASON_ORDER}
    domain_tally = {reason: sum(domain["reason"] == reason for domain in domains)
                    for reason in REASON_ORDER}
    accepted_points = sum(point["accepted"] for point in points)
    accepted_domains = sum(domain["accepted"] for domain in domains)
    return {
        "passed": not (tally["unresolved_border"] or tally["out_of_tile"]),
        "requested_points": len(points), "accepted_points": accepted_points,
        "refused_points": len(points) - accepted_points,
        "selected_domains": len(domains), "accepted_domains": accepted_domains,
        "refused_domains": len(domains) - accepted_domains,
        "reason_tally": tally, "domain_reason_tally": domain_tally,
        "points": points, "domains": domains,
    }


def check_domain_closed(seed, points_xz_m, *, config=None):
    """Check only point-selected domains in their world-anchored finite tiles.

    Closure owns all topology. This wrapper only reads its snapshots and returns
    JSON-able audit records; it publishes or deletes no products.
    """
    config = config or PlanningConfig()
    config.validate()
    snapshots = {}
    selections = {}
    for x, z in points_xz_m:
        x, z = float(x), float(z)
        if not np.isfinite([x, z]).all():
            raise ValueError("points must be finite")
        topology = domain_topology(seed, x, z, config)
        key = (topology["origin_x_m"], topology["origin_z_m"])
        snapshots.setdefault(key, topology)
        selections.setdefault(key, []).append((x, z))
    tiles = []
    for key in sorted(selections):
        report = check_topology_closed(snapshots[key], selections[key])
        tiles.append({"origin_x_m": key[0], "origin_z_m": key[1], **report})
    report = _report([point for tile in tiles for point in tile["points"]],
                     [domain for tile in tiles for domain in tile["domains"]])
    report["tiles"] = tiles
    return report
