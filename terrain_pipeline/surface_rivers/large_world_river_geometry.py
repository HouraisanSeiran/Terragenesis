"""Finite-page river geometry with explicit representative-flow completeness."""
from __future__ import annotations

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.geology import LITHOLOGY_ALGORITHM, rock_table_identity, sample_lithology_points
from terrain_pipeline.channel_geometry import build_discharge_geometry
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge
from .native_30m_source import build_strict_topology


def build_geometry(height, valid, origin, seed, source, *, runoff_m_per_year,
                   channel_threshold_m3_s, topology=None, water_mask=None, water_classes=None):
    height = np.asarray(height, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    if height.ndim != 2 or valid.shape != height.shape or not valid.any() or not np.isfinite(height[valid]).all():
        raise ValueError("finite resolved terrain and matching mask required")
    if not np.isfinite(runoff_m_per_year) or runoff_m_per_year <= 0. or not np.isfinite(channel_threshold_m3_s) or channel_threshold_m3_s <= 0.:
        raise ValueError("positive finite runoff and channel threshold required")
    water = np.zeros(height.shape, bool) if water_mask is None else np.asarray(water_mask, dtype=bool)
    if water.shape != height.shape or np.any(water & ~valid):
        raise ValueError("water mask must match resolved terrain")
    classes = np.asarray(water_classes) if water_classes is not None else water.astype(np.uint8)
    if classes.shape != height.shape or classes.dtype != np.uint8 or not np.isin(classes, [0, 1, 2]).all() or not np.array_equal((classes != 0) & valid, water):
        raise ValueError("water classes must match the water mask")
    land = valid & ~water
    if not land.any():
        raise ValueError("no resolved land for river topology")
    topology = build_strict_topology(height, land, origin_native_xz=origin,
                                     world_seed=seed) if topology is None else topology
    local = np.where(land, float(runoff_m_per_year) * 900. / (365.25 * 86400.), 0.)
    accumulation = accumulate_network_discharge(
        topology["receiver"], local, land, terminal_kind=topology["terminal_kind"],
        upstream_unknown_mask=topology["upstream_unknown_mask"])
    known = accumulation["known_routed_q_m3_s"]
    complete = accumulation["complete_mask"]
    channel = land & complete & (known >= channel_threshold_m3_s)
    pending = land & ~complete
    x = (origin[0] + np.arange(height.shape[1]))[None, :] * 30.
    z = (origin[1] + np.arange(height.shape[0]))[:, None] * 30.
    rock = sample_lithology_points(x, z, world_seed=seed)
    source_height = np.where(valid, height, 0.)
    geometry = build_discharge_geometry(source_height, np.where(complete, known, 0.), channel, 30.,
        bed_hardness=rock["bed_hardness"], bank_hardness=rock["bank_hardness"],
        protected_mask=~valid | water | pending)
    arrays = dict(geometry["arrays"], source_elevation_m=height.copy(), valid_mask=valid.copy(), water_mask=water.copy(), water_classes=classes.copy(),
                  complete_mask=complete, pending_mask=pending, known_q_m3_s=known,
                  receiver=topology["receiver"].copy(), terminal_kind=topology["terminal_kind"].copy(),
                  upstream_unknown_mask=topology["upstream_unknown_mask"].copy(),
                  rock_index=rock["rock_index"].copy())
    arrays["representative_q_m3_s"] = np.where(complete, known, np.nan)
    arrays["bed_elevation_m"][~valid] = height[~valid]
    metadata = {"schema": "large-world-river-geometry-v1", "origin_native_xz": list(origin),
        "spacing_m": 30., "world_seed": int(seed), "source": source,
        "runoff_m_per_year": float(runoff_m_per_year), "channel_threshold_m3_s": float(channel_threshold_m3_s),
        "discharge_semantics": "declared constant annual-mean runoff scenario, routed known contributions; not event Q",
        "incomplete_semantics": "known contribution only; representative Q and geometry pending",
        "lithology_algorithm": LITHOLOGY_ALGORITHM, "rock_table_identity": rock_table_identity(),
        "lithology_sample_identity": identity(rock, {"algorithm": LITHOLOGY_ALGORITHM, "world_seed": int(seed),
                                                      "origin_native_xz": list(origin), "spacing_m": 30.}),
        "lithology_status": "synthetic uncalibrated reference",
        "geometry": geometry["metadata"], "support": "finite source window; topology and raster projection may vary with window",
        "water_boundary": "water excluded from runoff and incision; adjacent land boundary remains unresolved, not a certified outlet",
        "water_depth_solved": False, "dynamic_erosion_solved": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def validate(product):
    if product["metadata"].get("schema") != "large-world-river-geometry-v1" or product["identity_sha256"] != identity(product["arrays"], product["metadata"]):
        raise ValueError("invalid river geometry identity")


def save(path, product):
    save_bundle(path, product, validator=validate)


def load(path, sha256):
    return load_bundle(path, expected_sha256=sha256, validator=validate)


def query(product, x, z):
    if type(x) is not int or type(z) is not int:
        raise ValueError("native coordinates must be integers")
    a, m = product["arrays"], product["metadata"]
    col, row = x - m["origin_native_xz"][0], z - m["origin_native_xz"][1]
    if not (0 <= row < a["valid_mask"].shape[0] and 0 <= col < a["valid_mask"].shape[1]) or not a["valid_mask"][row, col]:
        return {"status": "unresolved"}
    index = (row, col)
    if a["water_mask"][index]:
        return {"status": "water", "water_class": int(a["water_classes"][index]), "source_elevation_m": float(a["source_elevation_m"][index]),
                "derived_elevation_m": float(a["bed_elevation_m"][index])}
    status = "pending" if a["pending_mask"][index] else "channel" if a["channel_mask"][index] else "non_channel"
    return {"status": status, "known_q_m3_s": float(a["known_q_m3_s"][index]),
        "representative_q_m3_s": float(a["known_q_m3_s"][index]) if status != "pending" else None,
        "channel_width_m": float(a["channel_width_m"][index]) if status == "channel" else None,
        "incision_depth_m": float(a["channel_depth_m"][index]) if status == "channel" else None,
        "bed_hardness": float(a["bed_hardness"][index]), "bank_hardness": float(a["bank_hardness"][index]),
        "source_elevation_m": float(a["source_elevation_m"][index]),
        "derived_elevation_m": float(a["bed_elevation_m"][index])}
