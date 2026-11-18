"""Prepared, finite native glacier/coast and basin water/heat consumers.

No imports from the author application and no model generation. Native state
owns its stocks, clocks and packet IDs. World publication consumes bed_commit
once against its parent revision; queries never advance these functions.
"""

import itertools
import math
from copy import deepcopy

import numpy as np
from scipy.ndimage import binary_propagation

from terrain_pipeline import environment_processes as kernels
from terrain_pipeline.common_infra import identity, json_sha256
from terrain_pipeline.world_glacier import advance_flowline

ALGORITHM = "world-native-prism-glacier-basin-v1"
PACKET_SCHEMA = "world-environment-exchange-v1"
HEAT_CAPACITY = 4_000_000.0
QUANTITIES = (
    "water_m3",
    "solid_m3",
    "salt_kg",
    "nutrient_kg",
    "organic_carbon_kg",
    "sensible_heat_j",
    "latent_heat_j",
)
DEFAULTS = {
    "max_glaciers": 2,
    "max_coasts": 1,
    "min_flowline_cells": 32,
    "max_flowline_cells": 512,
    "coast_window_cells": 64,
    "max_native_cells": 65536,
    "max_basin_cells": 65536,
    "snow_history_years": 10,
    "time_quantum_s": 900.0,
    "basin_current_wind_fraction": 0.01,
    "basin_mixed_depth_m": 20.0,
    "initial_sea_temperature_c": 10.0,
    "ocean_salinity_kg_m3": 35.0,
    "tide_amplitude_m": 1.0,
    "tide_period_s": 44712.0,
    "mean_sea_level_m": 0.0,
    "max_canonical_steps": 100000,
    "sea_temperature_consumer": False,
}


def _config(config):
    cfg = dict(DEFAULTS, **(config or {}))
    for key, upper in [
        ("max_glaciers", 2),
        ("max_coasts", 4),
        ("max_flowline_cells", 512),
        ("max_native_cells", 65536),
        ("max_basin_cells", 65536),
    ]:
        if type(cfg[key]) is not int or not 0 <= cfg[key] <= upper:
            raise ValueError("bounded integer " + key + " required")
    if not 32 <= cfg["min_flowline_cells"] <= cfg["max_flowline_cells"]:
        raise ValueError("flowline must retain explicit 32..512 cell support")
    if (
        not 2 <= cfg["coast_window_cells"] <= 256
        or cfg["coast_window_cells"] ** 2 > cfg["max_native_cells"]
    ):
        raise ValueError("coast window exceeds native budget")
    for name in ("time_quantum_s", "basin_mixed_depth_m", "tide_period_s"):
        if not np.isfinite(cfg[name]) or cfg[name] <= 0:
            raise ValueError("positive finite " + name + " required")
    if cfg["time_quantum_s"] > min(900.0, cfg["tide_period_s"] / 16):
        raise ValueError("canonical step must resolve existing prism tide step")
    for name in ("initial_sea_temperature_c", "mean_sea_level_m"):
        if not np.isfinite(cfg[name]):
            raise ValueError("finite " + name + " required")
    for name in (
        "basin_current_wind_fraction",
        "ocean_salinity_kg_m3",
        "tide_amplitude_m",
    ):
        if not np.isfinite(cfg[name]) or cfg[name] < 0:
            raise ValueError("finite nonnegative " + name + " required")
    if type(cfg["max_canonical_steps"]) is not int or cfg["max_canonical_steps"] < 1:
        raise ValueError("positive integer canonical work bound required")
    return cfg


def _frame(source):
    bed = np.asarray(source["elevation_m"], np.float64)
    ocean = np.asarray(source["ocean_mask"], bool)
    spacing = float(source["spacing_m"])
    if (
        bed.ndim != 2
        or min(bed.shape) < 2
        or not np.isfinite(bed).all()
        or bed.shape != ocean.shape
    ):
        raise ValueError("finite matching 2D world terrain and ocean mask required")
    first = np.asarray(source["first_xz_m"], float)
    if (
        first.shape != (2,)
        or not np.isfinite(first).all()
        or not np.isfinite(spacing)
        or spacing <= 0
    ):
        raise ValueError("explicit metric world frame required")
    for key in ("source_identity", "plate_identity", "parent_terrain_revision"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise ValueError("missing " + key)
    if type(source["world_seed"]) is not int or source["world_seed"] < 0:
        raise ValueError("explicit world seed required")
    return bed, ocean, first, spacing


def _history(source, cfg, support_ids=()):
    if source.get("snow_history") is not None and not support_ids:
        return source["snow_history"]
    climate = source.get("climate", {})
    arrays = climate.get("arrays", climate)
    if not {"monthly_temperature_c", "monthly_precipitation_mm"} <= arrays.keys():
        return None
    from terrain_pipeline.world_environment_coupling import prepare_snow_history

    return prepare_snow_history(
        arrays["monthly_temperature_c"],
        arrays["monthly_precipitation_mm"],
        spacing_m=source["spacing_m"],
        ocean_mask=source["ocean_mask"],
        support_ids=support_ids,
        years=cfg["snow_history_years"],
    )


def plan(source, config=None):
    """Select stable real snow/coast candidates; never request new TD itself."""
    cfg = _config(config)
    bed, ocean, first, spacing = _frame(source)
    history = _history(source, cfg)
    candidates, statuses = [], {}
    initial_ice = np.broadcast_to(
        np.asarray(source.get("initial_ice_water_m3", 0.0), float), bed.shape
    )
    if not np.isfinite(initial_ice).all() or np.any(initial_ice < 0):
        raise ValueError("finite existing ice water-equivalent stock required")
    if (history is None or history.get("years", 0) < 10) and not np.any(
        initial_ice > 0
    ):
        statuses["glacier"] = {
            "status": "pending-snow-history",
            "reason": "ten generated climate years required",
        }
    else:
        if history is None:
            history = {
                "years": 0,
                "years_with_perennial_snow": np.zeros(bed.shape, int),
                "min_perennial_swe_mm": np.zeros(bed.shape),
                "snow_swe_mm": np.zeros(bed.shape),
            }
        persistent = np.asarray(history["years_with_perennial_snow"])
        minimum = np.asarray(history["min_perennial_swe_mm"], float)
        terminal = np.asarray(
            history.get("snow_swe_mm", history.get("terminal_swe_mm")), float
        )
        if any(value.shape != bed.shape for value in (persistent, minimum, terminal)):
            raise ValueError("snow history support differs from world")
        existing = initial_ice > 0
        eligible = ~ocean & (
            (
                (history["years"] >= 10)
                & (persistent >= 5)
                & (minimum > 0)
                & (terminal > 0)
            )
            | existing
        )
        ids = np.flatnonzero(eligible)
        ranking = sorted(
            ids.tolist(),
            key=lambda node: (
                -float(minimum.ravel()[node]),
                -float(bed.ravel()[node]),
                node,
            ),
        )
        selected = []
        for node in ranking if cfg["max_glaciers"] else []:
            z, x = divmod(node, bed.shape[1])
            if any(abs(z - z0) + abs(x - x0) < 8 for z0, x0 in selected):
                continue
            selected.append((z, x))
            candidates.append(
                {
                    "id": "glacier-" + str(node),
                    "kind": "glacier",
                    "node": node,
                    "location_xz_m": (first + np.array([x, z]) * spacing).tolist(),
                    "evidence": {
                        "years": int(history["years"]),
                        "perennial_years": int(persistent[z, x]),
                        "min_swe_mm": float(minimum[z, x]),
                        "terminal_swe_mm": float(terminal[z, x]),
                    },
                }
            )
            if len(selected) >= cfg["max_glaciers"]:
                break
        statuses["glacier"] = {
            "status": "pending-terrain" if ids.size else "not-triggered",
            "reason": "persistent multi-year snow or existing ice"
            if ids.size
            else "no persistent snow after ten years and no initial ice",
            "evaluated_years": int(history["years"]),
            "eligible_cells": int(ids.size),
            "selected": len(selected),
        }
    near_sea = np.zeros(bed.shape, bool)
    near_sea[1:] |= ocean[:-1]
    near_sea[:-1] |= ocean[1:]
    near_sea[:, 1:] |= ocean[:, :-1]
    near_sea[:, :-1] |= ocean[:, 1:]
    shores = np.flatnonzero(near_sea & ~ocean & (bed >= 0))
    q = np.asarray(source.get("discharge_m3_s", np.zeros(bed.shape)))
    ordered = sorted(shores.tolist(), key=lambda node: (-float(q.ravel()[node]), node))
    for node in ordered[: cfg["max_coasts"]]:
        z, x = divmod(node, bed.shape[1])
        candidates.append(
            {
                "id": "coast-" + str(node),
                "kind": "coast",
                "node": node,
                "location_xz_m": (first + np.array([x, z]) * spacing).tolist(),
            }
        )
    statuses["coastal_exchange"] = {
        "status": "pending-terrain" if shores.size else "not-triggered",
        "reason": "real sea/land adjacency"
        if shores.size
        else "no coast in known world support",
    }
    return {
        "algorithm": ALGORITHM,
        "source_identity": source["source_identity"],
        "candidates": candidates,
        "statuses": statuses,
        "config": cfg,
        "history": history,
        "metadata": {
            "candidate_policy": "stable multi-year perennial snow plus actual descending native support; coastal real adjacency",
            "world_seed": source["world_seed"],
        },
    }


def _coarse_nodes(source, xz):
    bed, _, first, spacing = _frame(source)
    indices = np.rint((np.asarray(xz) - first) / spacing).astype(int)
    if np.any(
        (indices[:, 0] < 0)
        | (indices[:, 0] >= bed.shape[1])
        | (indices[:, 1] < 0)
        | (indices[:, 1] >= bed.shape[0])
    ):
        raise ValueError("native support extends outside known world")
    return indices[:, 1] * bed.shape[1] + indices[:, 0]


def _native_for(candidate, terrains):
    x, z = candidate["location_xz_m"]
    for terrain in sorted(terrains, key=lambda row: row["identity"]):
        first = terrain["grid"]["first_sample_xz_m"]
        spacing = terrain["grid"]["spacing_m"]
        shape = terrain["elevation_m"].shape
        if (
            first[0] <= x <= first[0] + (shape[1] - 1) * spacing
            and first[1] <= z <= first[1] + (shape[0] - 1) * spacing
        ):
            return terrain
    return None


def _native_region(source, candidate, terrain, cfg):
    bed = np.asarray(terrain["elevation_m"], float)
    grid = terrain["grid"]
    spacing = float(grid["spacing_m"])
    first = np.asarray(grid["first_sample_xz_m"], float)
    x, z = np.rint((np.asarray(candidate["location_xz_m"]) - first) / spacing).astype(
        int
    )
    common = {
        "id": candidate["id"],
        "kind": candidate["kind"],
        "node": candidate["node"],
        "terrain_identity": terrain["identity"],
        "source_identity": source["source_identity"],
        "parent_terrain_revision": source["parent_terrain_revision"],
    }
    if candidate["kind"] == "glacier":
        path, used = [], set()
        for _ in range(cfg["max_flowline_cells"]):
            node = int(z * bed.shape[1] + x)
            if node in used or z in (0, bed.shape[0] - 1) or x in (0, bed.shape[1] - 1):
                break
            used.add(node)
            path.append((z, x))
            neighbours = [(z - 1, x), (z, x - 1), (z, x + 1), (z + 1, x)]
            nz, nx = min(neighbours, key=lambda pair: (bed[pair], pair))
            if bed[nz, nx] >= bed[z, x] or bed[nz, nx] < 0:
                break
            z, x = nz, nx
        if len(path) < cfg["min_flowline_cells"]:
            raise ValueError(
                "pending-geometry: native descending flowline shorter than 32 cells"
            )
        rows, cols = np.asarray(path).T
        xz = np.column_stack((first[0] + cols * spacing, first[1] + rows * spacing))
        coarse_nodes = _coarse_nodes(source, xz)
        if "rock_reserve_m" not in source:
            raise ValueError(
                "pending-input: explicit finite source rock reserve required"
            )
        rock_depth = np.asarray(source["rock_reserve_m"], float)
        if not np.isfinite(rock_depth).all() or np.any(rock_depth < 0):
            raise ValueError("finite nonnegative source rock reserve required")
        rock = (
            np.broadcast_to(
                rock_depth, np.asarray(source["elevation_m"]).shape
            ).ravel()[coarse_nodes]
            * spacing**2
        )
        geometry = {
            "bed_m": bed[rows, cols],
            "xz_m": xz,
            "spacing_m": spacing,
            "width_m": spacing,
            "cell_area_m2": np.full(len(path), spacing**2),
            "bedrock_erodible_m3": rock,
            "source_identity": source["source_identity"],
            "terrain_identity": terrain["identity"],
            "support_id": candidate["id"],
            "parent_terrain_revision": source["parent_terrain_revision"],
        }
        return dict(
            common,
            geometry=geometry,
            coarse_nodes=coarse_nodes,
            mapping_weights=np.full(len(path), spacing**2 / source["spacing_m"] ** 2),
        )
    size = min(cfg["coast_window_cells"], *bed.shape)
    r0 = min(max(0, z - size // 2), bed.shape[0] - size)
    c0 = min(max(0, x - size // 2), bed.shape[1] - size)
    rows, cols = np.indices((size, size))
    xz = np.column_stack(
        (
            first[0] + (cols.ravel() + c0) * spacing,
            first[1] + (rows.ravel() + r0) * spacing,
        )
    )
    coarse_nodes = _coarse_nodes(source, xz)
    # Use full native-source edge connectivity anchored by known coarse ocean.
    rz, rx = np.indices(bed.shape)
    full_xz = np.column_stack(
        (first[0] + rx.ravel() * spacing, first[1] + rz.ravel() * spacing)
    )
    full_nodes = _coarse_nodes(source, full_xz)
    known = np.asarray(source["ocean_mask"]).ravel()[full_nodes].reshape(bed.shape)
    edge = np.zeros(bed.shape, bool)
    edge[0] = True
    edge[-1] = True
    edge[:, 0] = True
    edge[:, -1] = True
    sea = binary_propagation(edge & known & (bed < 0), mask=bed < 0)[
        r0 : r0 + size, c0 : c0 + size
    ]
    if not sea.any() or not np.r_[sea[0], sea[-1], sea[:, 0], sea[:, -1]].any():
        raise ValueError(
            "pending-geometry: no known external sea connected to native window"
        )
    local = bed[r0 : r0 + size, c0 : c0 + size].copy()
    river_mask = np.zeros(local.shape, bool)
    river_mask[z - r0, x - c0] = True
    context = {
        "height_m": local,
        "spacing_m": spacing,
        "origin_native_xz": [
            round((first[0] + c0 * spacing) / spacing),
            round((first[1] + r0 * spacing) / spacing),
        ],
        "world_seed": source["world_seed"],
        "valid_mask": np.ones(local.shape, bool),
        "protected_mask": np.asarray(
            source.get(
                "protected_mask",
                np.zeros(np.asarray(source["elevation_m"]).shape, bool),
            ),
            bool,
        )
        .ravel()[coarse_nodes]
        .reshape(local.shape),
        "ocean_mask": sea,
        "river_mask": river_mask,
        "receiver": np.full(local.shape, -1, np.int64),
    }
    authorized = np.isin(
        coarse_nodes, source.get("authorized_river_detail_global_ids", [])
    ).reshape(local.shape)
    context["protected_mask"] &= ~(authorized & river_mask)
    return dict(
        common,
        context=context,
        coarse_nodes=coarse_nodes,
        mapping_weights=np.full(local.size, spacing**2 / source["spacing_m"] ** 2),
    )


def prepare(source, *, native_terrain=(), config=None):
    """Prepare bounded native regions and a disjoint finite mixed-layer basin.

    Native entries are hash-verified real local30 manifests. Missing native TD
    remains pending. No sand is invented by the default prism initializer:
    erodible stock enters through actual parent-debited inventory packets.
    """
    selected = plan(source, config)
    cfg = selected["config"]
    from terrain_pipeline.world_process_detail import load_native_terrain

    terrains = []
    for entry in native_terrain:
        terrain = load_native_terrain(
            entry,
            source_identity=source["plate_identity"],
            world_seed=source["world_seed"],
            island_provenance=source.get("island_provenance"),
        )
        if terrain["manifest"].get("generator", {}).get("kind") != "terragenesis-gpu":
            raise ValueError("native environment requires actual same-source model TD")
        terrains.append(terrain)
    regions, states, statuses = [], {}, deepcopy(selected["statuses"])
    occupied = set()
    for candidate in selected["candidates"]:
        terrain = _native_for(candidate, terrains)
        if terrain is None:
            statuses[candidate["id"]] = {
                "status": "pending-terrain",
                "candidate": candidate,
            }
            continue
        try:
            region = _native_region(source, candidate, terrain, cfg)
            if region["kind"] == "glacier":
                support = {tuple(point) for point in region["geometry"]["xz_m"]}
            else:
                origin = (
                    np.asarray(region["context"]["origin_native_xz"])
                    * region["context"]["spacing_m"]
                )
                rz, rx = np.indices(region["context"]["height_m"].shape)
                dx = region["context"]["spacing_m"]
                support = set(
                    zip(
                        (origin[0] + rx.ravel() * dx).tolist(),
                        (origin[1] + rz.ravel() * dx).tolist(),
                    )
                )
            if occupied & support:
                raise ValueError("pending-geometry: overlapping native stock ownership")
            occupied |= support
        except ValueError as error:
            statuses[candidate["id"]] = {
                "status": "pending-geometry",
                "reason": str(error),
                "candidate": candidate,
            }
            continue
        regions.append(region)
        if region["kind"] == "coast":
            state = kernels.initialize_coastal_exchange(
                region["context"],
                sea_level_m=cfg["mean_sea_level_m"],
                ocean_salinity_kg_m3=cfg["ocean_salinity_kg_m3"],
                mobile_thickness_m=0.0,
            )
            states[region["id"]] = {
                "core": state,
                "physical_time_s": 0.0,
                "consumed_packet_ids": [],
                "accepted_packet_ids": [],
                "refused_packets": [],
                "pending_packets": [],
                "initial_inventory_origin": "declared external sea fill; zero mobile solid until debited parent handoff",
            }
        else:
            states[region["id"]] = {
                "core": None,
                "physical_time_s": 0.0,
                "consumed_packet_ids": [],
                "accepted_packet_ids": [],
                "refused_packets": [],
                "pending_packets": [],
            }
        statuses[candidate["id"]] = {"status": "prepared", "kind": candidate["kind"]}
    bed, ocean, first, spacing = _frame(source)
    # A known finite mixed layer is a separate inventory. Exclude every coarse
    # cell touched by a native coast so no ocean water is owned twice.
    basin_size = min(int(math.sqrt(cfg["max_basin_cells"])), *bed.shape)
    if basin_size >= 2 and ocean.any():
        rz, cx = np.unravel_index(np.flatnonzero(ocean)[0], bed.shape)
        r0 = min(max(0, rz - basin_size // 2), bed.shape[0] - basin_size)
        c0 = min(max(0, cx - basin_size // 2), bed.shape[1] - basin_size)
        br, bc = np.indices((basin_size, basin_size))
        nodes = (br + r0) * bed.shape[1] + bc + c0
        wet = ocean[r0 : r0 + basin_size, c0 : c0 + basin_size].copy()
        for region in regions:
            if region["kind"] == "coast":
                wet &= ~np.isin(nodes, region["coarse_nodes"])
        if wet.any():
            seed = np.zeros_like(wet)
            seed.ravel()[np.flatnonzero(wet)[0]] = True
            wet = binary_propagation(seed, mask=wet)
        depth = np.where(
            wet,
            np.minimum(
                np.maximum(-bed[r0 : r0 + basin_size, c0 : c0 + basin_size], 0.0),
                cfg["basin_mixed_depth_m"],
            ),
            0.0,
        )
        volume = depth * spacing**2
        basin = {
            "id": "basin-0",
            "kind": "basin",
            "coarse_nodes": nodes.ravel(),
            "wet_mask": wet,
            "spacing_m": spacing,
            "first_xz_m": (first + np.array([c0, r0]) * spacing).tolist(),
            "source_identity": source["source_identity"],
            "parent_terrain_revision": source["parent_terrain_revision"],
        }
        regions.append(basin)
        states["basin-0"] = {
            "volume_m3": volume,
            "sensible_heat_j": volume
            * HEAT_CAPACITY
            * cfg["initial_sea_temperature_c"],
            "physical_time_s": 0.0,
            "consumed_packet_ids": [],
            "accepted_packet_ids": [],
            "refused_packets": [],
            "pending_packets": [],
        }
        statuses["basin_water_heat"] = {
            "status": "prepared",
            "scope": "finite mixed-layer water/heat; closed crop; prescribed current proxy, not ocean circulation",
        }
    else:
        statuses["basin_water_heat"] = {
            "status": "not-triggered",
            "reason": "no known sea in finite source",
        }
    if "basin-0" in states and not np.any(states["basin-0"]["volume_m3"]):
        regions = [region for region in regions if region["id"] != "basin-0"]
        del states["basin-0"]
        statuses["basin_water_heat"] = {
            "status": "pending-geometry",
            "reason": "bounded crop has no independently owned positive-depth sea",
        }
    metadata = {
        "algorithm": ALGORITHM,
        "source_identity": source["source_identity"],
        "plate_identity": source["plate_identity"],
        "parent_terrain_revision": source["parent_terrain_revision"],
        "world_seed": source["world_seed"],
        "config": cfg,
        "candidate_policy": selected["metadata"]["candidate_policy"],
        "initial_sea": "declared external mixed-layer/prism stock, no duplication of coarse lake/soil water",
        "sea_temperature_consumer": "pending-task03"
        if not cfg["sea_temperature_consumer"]
        else "declared-by-caller",
    }
    glacier_nodes = sorted(
        {
            int(node)
            for region in regions
            if region["kind"] == "glacier"
            for node in region["coarse_nodes"]
        }
    )
    replay = _history(source, cfg, glacier_nodes) if glacier_nodes else None
    for region in regions:
        if region["kind"] != "glacier":
            continue
        nodes = region["coarse_nodes"]
        area = region["geometry"]["cell_area_m2"]
        terminal = np.asarray(selected["history"]["snow_swe_mm"]).ravel()[nodes]
        region["snow_transfer_request"] = {
            "process": "snow_to_glacier",
            "support_global_ids": nodes.tolist(),
            "water_m3_by_cell": terminal * area / 1000.0,
            "inventory": "actual terminal snow preparation stock; parent must debit once",
        }
        initial_ice = np.broadcast_to(
            np.asarray(source.get("initial_ice_water_m3", 0.0), float),
            np.asarray(source["elevation_m"]).shape,
        ).ravel()[nodes]
        region["initial_ice_transfer_request"] = {
            "process": "initial_ice_to_glacier",
            "support_global_ids": nodes.tolist(),
            "water_m3_by_cell": initial_ice * area / source["spacing_m"] ** 2,
            "inventory": "existing parent ice water-equivalent stock; parent must debit once",
        }
        if replay is not None:
            columns = np.searchsorted(np.asarray(replay["support_ids"]), nodes)
            region["snow_history"] = dict(
                time_edges_s=replay["time_edges_s"],
                climate_identity=replay["climate_identity"],
                **{
                    name: np.asarray(value)[:, columns].copy()
                    for name, value in replay["history"].items()
                },
            )
    states["_exchange"] = {"refused_packets": [], "pending_bed_commits": []}
    return {
        "plans": regions,
        "state": states,
        "arrays": {},
        "statuses": statuses,
        "metadata": metadata,
        "snow_history": selected["history"],
        "candidates": selected["candidates"],
    }


def _packet(packet, prepared, region, state, begin, end):
    if packet.get("schema") != PACKET_SCHEMA or packet.get("id") != json_sha256(
        {k: v for k, v in packet.items() if k != "id"}
    ):
        raise ValueError("exchange packet identity mismatch")
    if packet["id"] in state["consumed_packet_ids"]:
        raise ValueError("exchange packet already consumed")
    m = prepared["metadata"]
    if (
        packet.get("source_identity") != m["source_identity"]
        or packet.get("parent_terrain_revision") != m["parent_terrain_revision"]
        or packet.get("owner_to") != region["id"]
        or packet.get("interval_start_s") != begin
        or packet.get("interval_end_s") != end
    ):
        raise ValueError(
            "exchange packet source/revision/owner/physical interval differs"
        )
    debit = packet.get("source_debit", {})
    if (
        debit.get("status") != "debited"
        or not debit.get("account_id")
        or not packet.get("parent_state_identity")
    ):
        raise ValueError("actual parent-debited finite packet required")
    if (
        packet.get("status") != "in-flight"
        or packet.get("consumed_by") is not None
        or not packet.get("owner_from")
    ):
        raise ValueError("unconsumed named-owner packet required")
    allowed = {
        "glacier": {"snow_to_glacier", "initial_ice_to_glacier"},
        "coast": {"river_to_coast", "coast_initial_solid"},
        "basin": {"river_to_basin", "coast_to_basin", "atmosphere_to_basin"},
    }
    if packet.get("process") not in allowed[region["kind"]]:
        raise ValueError("packet process is not owned by this consumer")
    quantities = packet.get("quantities", {})
    if set(quantities) - set(QUANTITIES):
        raise ValueError("unknown quantity or ambiguous heat unit")
    for key, value in quantities.items():
        if not np.isfinite(value) or (not key.endswith("heat_j") and value < 0):
            raise ValueError("finite physical packet quantities required")
    weights = np.asarray(packet.get("mapping_weights"), float)
    size = (
        region["geometry"]["bed_m"].size
        if region["kind"] == "glacier"
        else np.asarray(
            region["context"]["height_m"]
            if region["kind"] == "coast"
            else region["wet_mask"]
        ).size
    )
    if (
        weights.shape != (size,)
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.isclose(weights.sum(), 1.0, rtol=0, atol=1e-12)
    ):
        raise ValueError("explicit normalized local packet mapping weights required")
    support = np.asarray(packet.get("support_global_ids"), np.int64)
    if not np.array_equal(support, np.asarray(region["coarse_nodes"]).ravel()):
        raise ValueError("packet support mapping differs from actual native ownership")
    if region["kind"] == "glacier" and any(
        quantities.get(key, 0.0) for key in QUANTITIES if key != "water_m3"
    ):
        raise ValueError("snow transfer contains unsupported non-water stock")
    if packet["process"] == "coast_initial_solid" and any(
        quantities.get(key, 0.0) for key in QUANTITIES if key != "solid_m3"
    ):
        raise ValueError("initial coastal stock must contain only allocated solid")
    allowed_quantities = {
        "glacier": {"water_m3"},
        "coast": {"water_m3", "solid_m3", "salt_kg"},
        "basin": {"water_m3", "sensible_heat_j"},
    }[region["kind"]]
    if any(
        value != 0 for key, value in quantities.items() if key not in allowed_quantities
    ):
        raise ValueError("packet contains a quantity not owned by this consumer")
    if region["kind"] == "basin" and np.any(weights[~region["wet_mask"].ravel()]):
        raise ValueError(
            "basin packet mapping includes dry or separately owned support"
        )
    if region["kind"] == "coast":
        context = region["context"]
        allowed_support = ~context["protected_mask"]
        if packet["process"] == "river_to_coast":
            allowed_support &= context["river_mask"]
        if np.any(weights[~allowed_support.ravel()]):
            raise ValueError(
                "coastal packet mapping includes protected or non-mouth support"
            )
    return dict(
        {key: float(quantities.get(key, 0.0)) * weights for key in QUANTITIES},
        _process=packet["process"],
    )


def _packet_out(
    prepared, region, state_identity, begin, end, process, owner_to, quantities, weights
):
    record = {
        "schema": PACKET_SCHEMA,
        "process": process,
        "source_identity": prepared["metadata"]["source_identity"],
        "parent_state_identity": state_identity,
        "parent_terrain_revision": prepared["metadata"]["parent_terrain_revision"],
        "support_global_ids": np.asarray(region["coarse_nodes"]).ravel().tolist(),
        "mapping_weights": np.asarray(weights).ravel().tolist(),
        "owner_from": region["id"],
        "owner_to": owner_to,
        "interval_start_s": float(begin),
        "interval_end_s": float(end),
        "quantities": quantities,
        "source_debit": {
            "status": "debited",
            "account_id": region["id"] + "/" + process,
        },
        "status": "in-flight",
        "consumed_by": None,
    }
    record["id"] = json_sha256(record)
    return record


def _stock_identity(region, state):
    core = state.get("core", state)
    return identity(
        {key: value for key, value in core.items() if isinstance(value, np.ndarray)},
        {
            "support_id": region["id"],
            "physical_time_s": float(
                core.get("physical_time_s", state["physical_time_s"])
            ),
            "consumed_packet_ids": state["consumed_packet_ids"],
        },
    )


def _snow_demand(region, edges, name):
    """Integrate uncapped potential demand from the frozen climate annual cycle.

    Historical SWE is never replayed as accumulation. Only the last generated
    year's climate demand repeats; actual snowfall must arrive in debit packets.
    """
    n = len(region["geometry"]["bed_m"])
    result = np.zeros((len(edges) - 1, n))
    history = region.get("snow_history")
    if history is None:
        return result
    calendar = np.asarray(history["time_edges_s"])[-13:].copy()
    calendar -= calendar[0]
    annual = float(calendar[-1])
    values = np.asarray(history[name])[-12:]
    for interval, (begin, end) in enumerate(itertools.pairwise(edges)):
        current = float(begin)
        while current < end:
            phase = current % annual
            month = min(int(np.searchsorted(calendar, phase, side="right") - 1), 11)
            dt = min(float(end - current), float(calendar[month + 1] - phase))
            if dt <= 0:
                raise ValueError("snow climate calendar made no physical progress")
            result[interval] += (
                values[month] * dt / (calendar[month + 1] - calendar[month])
            )
            current += dt
    return result


def _add(ledger, other):
    for key, value in other.items():
        if isinstance(value, (int, float, np.number)):
            ledger[key] = ledger.get(key, 0.0) + float(value)


def _coast(prepared, region, state, forcing, inputs, edges, cfg):
    context = deepcopy(region["context"])
    core = deepcopy(state["core"])
    shape = core["bed_m"].shape
    start_bed = core["bed_m"].copy()
    initial = {key: core[key].copy() for key in ("water_m3", "salt_kg", "bed_solid_m3")}
    begin, end = edges[0], edges[-1]
    totals = {
        key: sum((row[key] for row in inputs), np.zeros(core["bed_m"].size)).reshape(
            shape
        )
        for key in QUANTITIES
    }
    allocated_solid = sum(
        (row["solid_m3"] for row in inputs if row["_process"] == "coast_initial_solid"),
        np.zeros(core["bed_m"].size),
    ).reshape(shape)
    if np.any(allocated_solid[context["protected_mask"]]):
        raise ValueError("initial coastal solid maps to protected support")
    core["bed_solid_m3"] += allocated_solid
    if any(
        np.any(totals[key])
        for key in (
            "nutrient_kg",
            "organic_carbon_kg",
            "sensible_heat_j",
            "latent_heat_j",
        )
    ):
        raise ValueError(
            "prism-only coast has no nutrient/carbon/heat store; route those to basin/soil"
        )
    drivers = dict(forcing)
    for key in (
        "tide_amplitude_m",
        "tide_period_s",
        "mean_sea_level_m",
        "ocean_salinity_kg_m3",
    ):
        drivers.setdefault(key, cfg[key])
    phase = (
        int(
            json_sha256(
                {"seed": prepared["metadata"]["world_seed"], "support": region["id"]}
            )[:12],
            16,
        )
        / 16**12
        * 2
        * np.pi
    )
    drivers.setdefault("tide_phase_rad", phase)
    if "wave_height_m" not in drivers:
        wind = np.asarray(drivers.get("wind_xz_m_s", (0.0, 0.0)), float)
        drivers["wave_height_m"] = 0.016 * float(wind @ wind) / 9.80665
        drivers["wave_direction_xz"] = (
            wind.tolist() if np.linalg.norm(wind) > 0 else [1.0, 0.0]
        )
    drivers.setdefault("wave_direction_xz", [1.0, 0.0])
    drivers["mouth_mask"] = context["river_mask"]
    support = drivers["mouth_mask"] & ~context["protected_mask"]
    if np.any((totals["water_m3"] > 0) & ~support) or np.any(
        (totals["solid_m3"] - allocated_solid > 0) & ~support
    ):
        raise ValueError("river packet must map to actual unprotected mouth cells")
    drivers["river_boundary_water_m3_s"] = totals["water_m3"] / (end - begin)
    drivers["river_boundary_solid_m3_s"] = (totals["solid_m3"] - allocated_solid) / (
        end - begin
    )
    ledger, fluxes = {}, {}
    for start in np.arange(begin, end, cfg["time_quantum_s"]):
        dt = min(cfg["time_quantum_s"], end - start)
        # Core does not accept river salt, so add the same debited source salt
        # explicitly before its real mixing/export step and count it separately.
        core["salt_kg"] += totals["salt_kg"] * dt / (end - begin)
        context["height_m"] = core["bed_m"]
        result = kernels.advance_coastal_exchange(core, drivers, context, dt)
        core = result["state"]
        _add(ledger, result["ledger"])
        for key, value in result["fluxes"].items():
            if key not in (
                "salinity_kg_m3",
                "water_stage_m",
                "wet_fraction",
                "tide_level_m",
            ):
                fluxes[key] = fluxes.get(key, np.zeros_like(value)) + value
        last = result["fluxes"]
    ledger["river_salt_input_kg"] = float(totals["salt_kg"].sum())
    ledger["allocated_initial_solid_m3"] = float(allocated_solid.sum())
    ledger["water_residual_m3"] = float(
        initial["water_m3"].sum()
        + totals["water_m3"].sum()
        + ledger["signed_ocean_water_m3"]
        - ledger["soil_water_export_m3"]
        - core["water_m3"].sum()
    )
    ledger["salt_residual_kg"] = float(
        initial["salt_kg"].sum()
        + totals["salt_kg"].sum()
        + ledger["signed_ocean_salt_kg"]
        - ledger["soil_salt_export_kg"]
        - core["salt_kg"].sum()
    )
    ledger["solid_residual_m3"] = float(
        initial["bed_solid_m3"].sum()
        + totals["solid_m3"].sum()
        - core["bed_solid_m3"].sum()
    )
    snapshots = dict(
        initial_water_m3=initial["water_m3"],
        initial_salt_kg=initial["salt_kg"],
        initial_solid_m3=initial["bed_solid_m3"],
        final_water_m3=core["water_m3"],
        final_salt_kg=core["salt_kg"],
        final_solid_m3=core["bed_solid_m3"],
        bed_m=core["bed_m"],
        bed_change_m=core["bed_m"] - start_bed,
        water_depth_m=core["water_m3"] / context["spacing_m"] ** 2,
        **last,
    )
    state["core"] = core
    return state, snapshots, fluxes, ledger


def _basin(region, state, forcing, inputs, edges, cfg):
    volume, heat = state["volume_m3"].copy(), state["sensible_heat_j"].copy()
    initial_volume, initial_heat = volume.copy(), heat.copy()
    shape = volume.shape
    totals = {
        key: sum((row[key] for row in inputs), np.zeros(volume.size)).reshape(shape)
        for key in QUANTITIES
    }
    if any(
        np.any(totals[key])
        for key in (
            "solid_m3",
            "salt_kg",
            "nutrient_kg",
            "organic_carbon_kg",
            "latent_heat_j",
        )
    ):
        raise ValueError("finite basin only owns water and sensible heat")
    if np.any(totals["water_m3"][~region["wet_mask"]]) or np.any(
        totals["sensible_heat_j"][~region["wet_mask"]]
    ):
        raise ValueError("basin packet maps to land or separately owned coast")
    wind = np.asarray(forcing.get("wind_xz_m_s", (0.0, 0.0)), float)
    if wind.shape != (2,) or not np.isfinite(wind).all():
        raise ValueError("explicit finite xz wind vector required")
    if (
        not np.isfinite(cfg["basin_current_wind_fraction"])
        or cfg["basin_current_wind_fraction"] < 0
    ):
        raise ValueError("nonnegative declared wind/current conversion required")
    atmosphere = np.broadcast_to(
        np.asarray(forcing.get("surface_heat_w_m2", 0.0), float), shape
    )
    if not np.isfinite(atmosphere).all():
        raise ValueError("finite actual atmospheric sensible heat flux required")
    exported_water = exported_heat = transported = atmosphere_heat = 0.0
    begin, end = edges[0], edges[-1]
    for start in np.arange(begin, end, cfg["time_quantum_s"]):
        dt = min(cfg["time_quantum_s"], end - start)
        volume += totals["water_m3"] * dt / (end - begin)
        heat += totals["sensible_heat_j"] * dt / (end - begin)
        exchanged = atmosphere * region["spacing_m"] ** 2 * region["wet_mask"] * dt
        heat += exchanged
        atmosphere_heat += float(exchanged.sum())
        # Real signed X and Z projections, never nearest-axis rounding.
        for axis, component in enumerate(wind):
            speed = abs(float(component)) * cfg["basin_current_wind_fraction"]
            if speed == 0:
                continue
            parts = max(1, math.ceil(speed * dt / region["spacing_m"]))
            if parts > 4096:
                raise ValueError("basin CFL work budget exceeded")
            direction = [0, 0]
            direction[axis] = 1 if component > 0 else -1
            for _ in range(parts):
                temperature = np.divide(
                    heat,
                    HEAT_CAPACITY * volume,
                    out=np.zeros_like(heat),
                    where=volume > 0,
                )
                result = kernels.ocean_coast_transport_step(
                    volume,
                    temperature,
                    region["wet_mask"],
                    wind_bearing=direction,
                    wind_speed_m_s=speed,
                    dt_s=dt / parts,
                    spacing_m=region["spacing_m"],
                    boundary=kernels.CLOSED,
                )
                volume = result["volume_m3"]
                heat = HEAT_CAPACITY * volume * result["temperature_c"]
                exported_water += result["ledger"]["boundary_outflow_m3"]
                exported_heat += (
                    result["ledger"]["boundary_heat_outflow_m3_degc"] * HEAT_CAPACITY
                )
                transported += result["ledger"]["internal_transported_volume_m3"]
    state.update(volume_m3=volume, sensible_heat_j=heat)
    temperature = np.divide(
        heat, HEAT_CAPACITY * volume, out=np.full_like(heat, np.nan), where=volume > 0
    )
    arrays = {
        "initial_volume_m3": initial_volume,
        "final_volume_m3": volume,
        "initial_sensible_heat_j": initial_heat,
        "final_sensible_heat_j": heat,
        "sea_temperature_c": temperature,
    }
    ledger = {
        "water_input_m3": float(totals["water_m3"].sum()),
        "sensible_heat_input_j": float(totals["sensible_heat_j"].sum()),
        "atmosphere_sensible_heat_j": atmosphere_heat,
        "boundary_water_export_m3": exported_water,
        "boundary_sensible_heat_export_j": exported_heat,
        "internal_water_transfer_m3": transported,
        "water_residual_m3": float(
            initial_volume.sum()
            + totals["water_m3"].sum()
            - exported_water
            - volume.sum()
        ),
        "sensible_heat_residual_j": float(
            initial_heat.sum()
            + totals["sensible_heat_j"].sum()
            + atmosphere_heat
            - exported_heat
            - heat.sum()
        ),
    }
    return state, arrays, {}, ledger


def advance(prepared, state, forcing, *, time_edges_s):
    """Advance prepared inventories with validated, already-debited packets.

    forcing = {'packets': [...], 'regions': {region_id: physical drivers}}.
    All public edges lie on an absolute canonical quantum. Packet totals are
    distributed uniformly within their declared interval, so cold split calls
    on the same canonical edges reproduce the same numerical work.
    """
    cfg = prepared["metadata"]["config"]
    edges = np.asarray(time_edges_s, float)
    q = cfg["time_quantum_s"]
    if (
        edges.ndim != 1
        or edges.size < 2
        or not np.isfinite(edges).all()
        or np.any(np.diff(edges) <= 0)
    ):
        raise ValueError("strict finite physical time edges required")
    if not np.allclose(edges / q, np.rint(edges / q), rtol=0, atol=1e-8):
        raise ValueError("native continuation edges must be absolute canonical quanta")
    if (edges[-1] - edges[0]) / q > cfg["max_canonical_steps"]:
        raise ValueError("fixed native work budget exceeded before allocation")
    out = deepcopy(prepared["state"] if state is None else state)
    exchange = out.setdefault(
        "_exchange", {"refused_packets": [], "pending_bed_commits": []}
    )
    packets = forcing.get("packets", [])
    if len({row.get("id") for row in packets}) != len(packets):
        raise ValueError("duplicate packet IDs in native request")
    arrays, fluxes, ledgers, accepted, refused, outgoing, commits = (
        {},
        {},
        {},
        [],
        [],
        [],
        [],
    )
    statuses = deepcopy(prepared["statuses"])
    known = {row["id"] for row in prepared["plans"]}
    for packet in packets:
        if packet.get("owner_to") not in known:
            refused.append(
                {"id": packet.get("id"), "reason": "native support not prepared"}
            )
    for region in prepared["plans"]:
        rid = region["id"]
        previous = out[rid]
        if previous["physical_time_s"] != edges[0]:
            raise ValueError("native physical clock mismatch")
        inputs, consumed = [], []
        for packet in packets:
            if packet.get("owner_to") != rid:
                continue
            try:
                inputs.append(
                    _packet(packet, prepared, region, previous, edges[0], edges[-1])
                )
                consumed.append(packet["id"])
            except (ValueError, KeyError, TypeError) as error:
                refused.append({"id": packet.get("id"), "reason": str(error)})
        driver = forcing.get("regions", {}).get(rid, {})
        if region["kind"] == "coast":
            result, data, moved, ledger = _coast(
                prepared, region, previous, driver, inputs, edges, cfg
            )
        elif region["kind"] == "basin":
            result, data, moved, ledger = _basin(
                region, previous, driver, inputs, edges, cfg
            )
        else:
            n = len(region["geometry"]["bed_m"])
            mass = sum((row["water_m3"] for row in inputs), np.zeros(n))
            if any(
                any(
                    np.any(row[key])
                    for key in QUANTITIES
                    if key not in ("water_m3", "latent_heat_j")
                )
                for row in inputs
            ):
                raise ValueError("glacier input must be actual snow water equivalent")
            area = region["geometry"]["cell_area_m2"]
            glacier_forcing = {
                "accumulation_mm": np.broadcast_to(
                    mass / area * 1000.0 / (edges[-1] - edges[0]), (len(edges) - 1, n)
                )
                * np.diff(edges)[:, None],
                "ablation_mm": driver.get(
                    "ablation_mm", _snow_demand(region, edges, "potential_ablation_mm")
                ),
                "sublimation_mm": driver.get(
                    "sublimation_mm",
                    _snow_demand(region, edges, "potential_sublimation_mm"),
                ),
            }
            advanced = advance_flowline(
                region["geometry"],
                previous["core"],
                glacier_forcing,
                time_edges_s=edges,
                config=dict(time_quantum_s=q, **driver.get("glacier_config", {})),
            )
            result = previous
            result["core"] = advanced["state"]
            data, moved, ledger = advanced["arrays"], {}, advanced["ledger"]
            debit_state_identity = _stock_identity(region, result)
            # Transfer actual new melt/sediment into a persisted in-flight
            # packet and debit local pending stores in the very same commit.
            for field, process, quantity in [
                ("pending_melt_water_m3", "glacier_melt_to_runoff", "water_m3"),
                ("pending_sediment_solid_m3", "glacier_sediment_to_route", "solid_m3"),
            ]:
                stock = result["core"][field]
                if stock.sum() > 0:
                    weights = stock / stock.sum()
                    record = _packet_out(
                        prepared,
                        region,
                        debit_state_identity,
                        edges[0],
                        edges[-1],
                        process,
                        "surface-route",
                        {quantity: float(stock.sum())},
                        weights,
                    )
                    outgoing.append(record)
                    result["pending_packets"].append(record)
                    result["core"][field] = np.zeros_like(stock)
            ledger["melt_transferred_to_outbox_m3"] = float(
                data["final_liquid_m3"].sum()
            )
            ledger["sediment_transferred_to_outbox_m3"] = float(
                data["final_sediment_m3"].sum()
            )
            ledger["inventory_scope"] = (
                "native core plus persisted in-flight packets; array final stores are before outbox debit"
            )
        result["physical_time_s"] = float(edges[-1])
        result["consumed_packet_ids"] = previous["consumed_packet_ids"] + consumed
        result["accepted_packet_ids"] = previous["accepted_packet_ids"] + consumed
        result["refused_packets"] = previous["refused_packets"] + [
            row
            for row in refused
            if row["id"] in {p.get("id") for p in packets if p.get("owner_to") == rid}
        ]
        out[rid] = result
        accepted.extend(consumed)
        arrays[rid], fluxes[rid], ledgers[rid] = data, moved, ledger
        statuses[rid] = {"status": "computed", "kind": region["kind"]}
        if (
            region["kind"] == "glacier"
            and not np.any(data["ice_final_volume_m3"])
            and not np.any(data["accumulation_water_m3"])
        ):
            statuses[rid] = {
                "status": "pending-input",
                "kind": "glacier",
                "reason": "no debited terminal snow/ice transfer",
            }
        ledger["latent_energy_model"] = (
            "declared degree-day demand; not an ice enthalpy balance"
            if region["kind"] == "glacier"
            else "not-modelled"
        )
        if region["kind"] == "basin" and not cfg["sea_temperature_consumer"]:
            statuses[rid]["consumer_status"] = "pending-task03"
        if "bed_change_m" in data and np.any(data["bed_change_m"]):
            commit = {
                "schema": "environment_bed_commit-v1",
                "source_identity": prepared["metadata"]["source_identity"],
                "parent_terrain_revision": prepared["metadata"][
                    "parent_terrain_revision"
                ],
                "support_id": rid,
                "support_global_ids": np.asarray(region["coarse_nodes"])
                .ravel()
                .tolist(),
                "mapping_weights": np.asarray(region["mapping_weights"])
                .ravel()
                .tolist(),
                "bed_after_m": np.asarray(data["bed_m"]).ravel().tolist(),
                "bed_change_m": np.asarray(data["bed_change_m"]).ravel().tolist(),
                "interval_start_s": float(edges[0]),
                "interval_end_s": float(edges[-1]),
                "consumed_packet_ids": consumed,
                "inventory_deltas": ledger,
            }
            commit["id"] = json_sha256(commit)
            commits.append(commit)
            exchange["pending_bed_commits"].append(commit)
        if region["kind"] == "coast" and ledgers[rid]["soil_water_export_m3"] > 0:
            # Salt and water are returned as separate finite packets so unequal
            # local concentrations do not silently acquire the water weights.
            for field, quantity in [
                ("soil_water_m3", "water_m3"),
                ("soil_salt_kg", "salt_kg"),
            ]:
                stock = fluxes[rid][field]
                if stock.sum() > 0:
                    record = _packet_out(
                        prepared,
                        region,
                        _stock_identity(region, result),
                        edges[0],
                        edges[-1],
                        "coast_soil_exchange",
                        "seasonal-soil",
                        {quantity: float(stock.sum())},
                        stock.ravel() / stock.sum(),
                    )
                    outgoing.append(record)
                    result["pending_packets"].append(record)
    exchange["refused_packets"].extend(refused)
    for kind, label in [("glacier", "glacier"), ("coast", "coastal_exchange")]:
        prepared_ids = [row["id"] for row in prepared["plans"] if row["kind"] == kind]
        if prepared_ids:
            statuses[label] = {
                "status": "computed"
                if all(statuses[rid]["status"] == "computed" for rid in prepared_ids)
                else "pending-input",
                "supports": prepared_ids,
            }
    return {
        "state": out,
        "arrays": arrays,
        "fluxes": fluxes,
        "ledger": ledgers,
        "packets_out": outgoing,
        "accepted_packet_ids": accepted,
        "refused_packets": refused,
        "bed_commit": commits,
        "statuses": statuses,
        "metadata": dict(
            prepared["metadata"],
            physical_time_s=float(edges[-1]),
            sea_temperature_consumer="pending-task03"
            if not cfg["sea_temperature_consumer"]
            else "declared-by-caller",
        ),
    }
