"""Absolute-coordinate multiscale water/land field and macro diagnostics.

Finite thresholds use a fixed frame sample; infinite thresholds use a fixed declared
reference square. No window controls the threshold. Lake and ocean labels describe
classes, not proven connectivity, closed basins, or hydraulic water surfaces.
The previous core geometry is not part of this algorithm.
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

import numpy as np

__all__ = [
    "SCHEMA",
    "ALGORITHM",
    "PRESETS",
    "MODES",
    "ROLES",
    "CLASS_LAND",
    "CLASS_OCEAN",
    "CLASS_LAKE",
    "REASON_CODES",
    "LayoutSpec",
    "LayoutError",
    "LayoutRefused",
    "derive_subseed",
    "layout_field",
    "classify_points",
    "measure_grid",
    "identity",
    "describe",
]

SCHEMA = "world-water-layout-v1"
ALGORITHM = "absolute-multiscale-field-layout-v3"

PRESETS = ("earth", "archipelago", "lakes")
MODE_INFINITE = "infinite"
MODE_FINITE = "finite"
MODES = (MODE_INFINITE, MODE_FINITE)

ROLE_MAJOR_LAND = "major_land"
ROLE_MIXED = "mixed"
ROLE_OPEN_SEA = "open_sea"
ROLES = (ROLE_MAJOR_LAND, ROLE_MIXED, ROLE_OPEN_SEA)

CLASS_LAND = 0
CLASS_OCEAN = 1
CLASS_LAKE = 2

#: Stable refusal codes. Callers match on these; renaming one is an identity change.
REASON_TARGET_UNREACHABLE = "target_unreachable"
REASON_RESOLUTION = "resolution_insufficient"
REASON_FRAME = "frame_invalid"
REASON_PLACEMENT = "placement_does_not_fit"
REASON_PRESET_CONFLICT = "preset_ratio_conflict"
REASON_AUTO_EMPTY = "auto_legal_set_empty"
REASON_SPEC = "spec_invalid"
REASON_CODES = (REASON_TARGET_UNREACHABLE, REASON_RESOLUTION, REASON_FRAME,
                REASON_PLACEMENT, REASON_PRESET_CONFLICT, REASON_AUTO_EMPTY,
                REASON_SPEC)

NAMESPACE = b"terragenesis-world-water-layout-v1"

#: Envelope factor of the two-harmonic star shape: ``max R(theta)/r = 1+|a1|+|a2|``.
_HARMONIC_MAX = 0.11
ENVELOPE_FACTOR = 1.0 + 2.0 * _HARMONIC_MAX


class LayoutError(ValueError):
    """The request itself is invalid; nothing is computed."""


class LayoutRefused(ValueError):
    """A declared constraint cannot be met; the request is refused with evidence."""

    def __init__(self, code, message, evidence=None):
        if code not in REASON_CODES:
            raise LayoutError("unknown refusal code: %r" % (code,))
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.evidence = dict(evidence or {})

    def record(self):
        return {"code": self.code, "message": self.message,
                "evidence": dict(self.evidence)}


def _require(condition, code, message, evidence=None):
    if not condition:
        raise LayoutRefused(code, message, evidence)


def _finite(name, value, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise LayoutError("%s must be a number" % name)
    number = float(value)
    if not math.isfinite(number):
        raise LayoutError("%s must be finite" % name)
    if positive and number <= 0.0:
        raise LayoutError("%s must be positive" % name)
    return number


# --------------------------------------------------------------------------- #
# sub-seeds (CONTRIBUTING: fixed world seed, stable purpose names)
# --------------------------------------------------------------------------- #
def derive_subseed(world_seed, layout_id, purpose, region_i=0, region_j=0):
    """Stable uint64 sub-seed from the world seed, layout id, purpose and region.

    Encoding is unambiguous: the three variable-length fields are NUL-free, separators
    are NUL, and the two region coordinates are fixed-width signed 8-byte big-endian
    (injective on int64, so a negative region cannot encode as a positive one). The
    digest is truncated to 64 bits, so ``n`` inputs collide with probability about
    ``n*(n-1)/2**65`` -- a statement about the truncation, not a proof of injectivity.
    """
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, (int, np.integer)):
        raise LayoutError("world_seed must be an integer")
    if not 0 <= int(world_seed) < 2 ** 64:
        raise LayoutError("world_seed must fit uint64")
    for text, name in ((layout_id, "layout_id"), (purpose, "purpose")):
        if not isinstance(text, str) or not text or "\x00" in text:
            raise LayoutError("%s must be a non-empty NUL-free string" % name)
    for value, name in ((region_i, "region_i"), (region_j, "region_j")):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise LayoutError("%s must be an integer" % name)
        if not -(2 ** 63) <= int(value) < 2 ** 63:
            raise LayoutError("%s must fit int64" % name)
    payload = b"".join((
        NAMESPACE, b"\x00", str(int(world_seed)).encode("ascii"), b"\x00",
        layout_id.encode("utf-8"), b"\x00", purpose.encode("ascii"), b"\x00",
        int(region_i).to_bytes(8, "big", signed=True),
        int(region_j).to_bytes(8, "big", signed=True)))
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


# --------------------------------------------------------------------------- #
# declaration
# --------------------------------------------------------------------------- #
def _preset_block(preset):
    """Declared geometry of one preset. Engineering choices, not calibration."""
    if preset == "earth":
        return {"region_side_m": 4_096_000.0,
                "major_radius_ratio": (0.20, 0.30),
                "minor_radius_ratio": (0.05, 0.10),
                "major_count": (1, 2), "minor_count": (4, 8),
                "role_weights": {ROLE_MAJOR_LAND: 0.55, ROLE_MIXED: 0.35,
                                 ROLE_OPEN_SEA: 0.10}}
    if preset == "archipelago":
        return {"region_side_m": 768_000.0,
                "major_radius_ratio": (0.14, 0.20),
                "minor_radius_ratio": (0.025, 0.055),
                "major_count": (1, 1), "minor_count": (12, 20),
                "role_weights": {ROLE_MAJOR_LAND: 0.20, ROLE_MIXED: 0.55,
                                 ROLE_OPEN_SEA: 0.25}}
    if preset == "lakes":
        return {"region_side_m": 768_000.0,
                "lake_radius_ratio": (0.10, 0.375),
                "lake_lattice_ratio": 0.3125,
                "basin_rise_m": 120.0, "h_offset_m": 1.0,
                "role_weights": {ROLE_MIXED: 1.0}}
    raise LayoutError("unknown preset: %r" % (preset,))


class LayoutSpec:
    """One complete layout request. Everything that changes the world is here.

    ``mode`` selects the world range, ``preset`` the landform family, and
    ``total_water_fraction`` the single number a user supplies. Sea/lake split defaults
    to the preset (ocean presets: all sea; lakes: all lake) and is echoed back.
    """

    __slots__ = ("world_seed", "layout_id", "mode", "preset", "total_water_fraction",
                 "region_side_m", "w_geom_m", "b_geom_m", "h_design_m", "epsilon_m",
                 "frame_origin_m", "frame_side_m", "sea_share")

    def __init__(self, preset, total_water_fraction, *, world_seed=20261020,
                 layout_id="default", mode=MODE_INFINITE, region_side_m=None,
                 w_geom_m=40_000.0, b_geom_m=20_000.0, h_design_m=4_000.0,
                 epsilon_m=1.0, frame_origin_m=None, frame_side_m=None):
        if preset not in PRESETS:
            raise LayoutError("preset must be one of %s" % (PRESETS,))
        if mode not in MODES:
            raise LayoutError("mode must be one of %s" % (MODES,))
        if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, (int, np.integer)):
            raise LayoutError("world_seed must be an integer")
        if not 0 <= int(world_seed) < 2 ** 64:
            raise LayoutError("world_seed must fit uint64")
        if not isinstance(layout_id, str) or not layout_id or "\x00" in layout_id:
            raise LayoutError("layout_id must be a non-empty NUL-free string")
        water = _finite("total_water_fraction", total_water_fraction)
        if not 0.0 <= water <= 1.0:
            raise LayoutError("total_water_fraction must be in [0, 1]")
        block = _preset_block(preset)
        side = _finite("region_side_m",
                       block["region_side_m"] if region_side_m is None else region_side_m,
                       positive=True)
        self.world_seed = int(world_seed)
        self.layout_id = layout_id
        self.mode = mode
        self.preset = preset
        self.total_water_fraction = water
        self.region_side_m = side
        self.w_geom_m = _finite("w_geom_m", w_geom_m, positive=True)
        self.b_geom_m = _finite("b_geom_m", b_geom_m, positive=True)
        self.h_design_m = _finite("h_design_m", h_design_m, positive=True)
        self.epsilon_m = _finite("epsilon_m", epsilon_m, positive=True)
        if (self.w_geom_m, self.b_geom_m, self.h_design_m, self.epsilon_m) != (
                40_000.0, 20_000.0, 4_000.0, 1.0):
            raise LayoutError("legacy geometry gap parameters are not supported by the field layout")
        if mode == MODE_FINITE:
            if frame_origin_m is None or frame_side_m is None:
                raise LayoutError("mode=finite requires frame_origin_m and frame_side_m")
            origin = tuple(_finite("frame_origin_m", value) for value in frame_origin_m)
            if len(origin) != 2:
                raise LayoutError("frame_origin_m must be (x, z) metres")
            self.frame_origin_m = origin
            self.frame_side_m = _finite("frame_side_m", frame_side_m, positive=True)
        else:
            if frame_origin_m is not None or frame_side_m is not None:
                raise LayoutError("mode=infinite must not declare a frame; the world is "
                                  "a fixed lattice of planning regions")
            self.frame_origin_m = None
            self.frame_side_m = None
        # Sea share defaults per preset; lakes are all lake, ocean presets all sea.
        self.sea_share = 0.0 if preset == "lakes" else 1.0
        self._validate()

    # -- derived quantities -------------------------------------------------- #
    @property
    def design_gap_m(self):
        """``w_geom + 2*sqrt(2)*h_design + epsilon``; uses ``h_design`` only."""
        return (self.w_geom_m + 2.0 * math.sqrt(2.0) * self.h_design_m
                + self.epsilon_m)

    @property
    def land_fraction_target(self):
        return 1.0 - self.total_water_fraction

    def _validate(self):
        if self.preset == "lakes" and self.total_water_fraction <= 0.0:
            raise LayoutRefused(REASON_TARGET_UNREACHABLE,
                                "lakes need a positive water fraction",
                                {"preset": self.preset})
        if self.preset != "lakes" and self.land_fraction_target <= 0.0:
            raise LayoutRefused(REASON_TARGET_UNREACHABLE,
                                "an ocean preset needs a positive land fraction; "
                                "use all-sea targets via preset=lakes or a larger side",
                                {"preset": self.preset,
                                 "land_fraction_target": self.land_fraction_target})

    # -- identity ------------------------------------------------------------ #
    def parameters(self):
        record = {"schema": SCHEMA, "algorithm": ALGORITHM,
                  "world_seed": self.world_seed, "layout_id": self.layout_id,
                  "mode": self.mode, "preset": self.preset,
                  "total_water_fraction": self.total_water_fraction,
                  "sea_share": self.sea_share,
                  "region_side_m": self.region_side_m,
                  "w_geom_m": self.w_geom_m, "b_geom_m": self.b_geom_m,
                  "h_design_m": self.h_design_m, "epsilon_m": self.epsilon_m,
                  "design_gap_m": self.design_gap_m,
                  "envelope_factor": ENVELOPE_FACTOR,
                  "harmonic_max": _HARMONIC_MAX}
        record.update({"threshold_calibration": "512x512 fixed-frame cell centres",
                       "infinite_calibration_frame_m": [0.0, 0.0, 12288000.0],
                       "lake_frame_margin_m": 150000.0,
                       "legacy_gap_parameters": "inactive; no minimum separation guarantee",
                       "field_rotation_rad": 0.37,
                       "field_subseed": derive_subseed(self.world_seed, self.layout_id, "macro-field"),
                       "field_scales_m_weights": {"earth": [[4000000, 1.0], [1300000, .55], [300000, .2]],
                                                  "archipelago": [[1500000, .35], [250000, .7], [65000, .35]],
                                                  "lakes": [[1500000, .35], [220000, .7], [60000, .35]]}[self.preset],
                       "topology_guarantees": "none; lakes and oceans are field classes"})
        if self.mode == MODE_FINITE:
            record["frame_origin_m"] = list(self.frame_origin_m)
            record["frame_side_m"] = self.frame_side_m
        return record

    def identity(self):
        payload = repr(sorted(self.parameters().items())).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def __repr__(self):
        return ("LayoutSpec(preset=%r, water=%.6g, mode=%r, side=%.0f)"
                % (self.preset, self.total_water_fraction, self.mode, self.region_side_m))


def identity(spec):
    """Public identity of a layout: sha256 over its canonical parameter record."""
    if not isinstance(spec, LayoutSpec):
        raise LayoutError("identity() needs a LayoutSpec")
    return spec.identity()


def _field_values(preset, seed, layout_id, region_side, x, z, frame):
    from diffusion.geographic_noise import field
    scales = {"earth": ((4_000_000., 1.0), (1_300_000., .55), (300_000., .2)),
              "archipelago": ((1_500_000., .35), (250_000., .7), (65_000., .35)),
              "lakes": ((1_500_000., .35), (220_000., .7), (60_000., .35))}[preset]
    scale_multiplier = region_side / _preset_block(preset)["region_side_m"]
    scales = tuple((spacing * scale_multiplier, weight) for spacing, weight in scales)
    sub_seed = derive_subseed(seed, layout_id, "macro-field")
    angle = 0.37
    u = math.cos(angle) * x - math.sin(angle) * z
    v = math.sin(angle) * x + math.cos(angle) * z
    values = field(u, v, sub_seed, 0, scales)
    if preset == "lakes" and frame is not None:
        ox, oz, side = frame
        distance = np.minimum.reduce((x - ox, z - oz, ox + side - x, oz + side - z))
        t = np.clip(distance / 150_000.0, 0.0, 1.0)
        t = t * t * (3.0 - 2.0 * t)
        values = values - 3.0 * (1.0 - t)
    return values


@lru_cache(maxsize=32)
def _calibrated_threshold(preset, seed, layout_id, region_side, water, frame, calibration_frame):
    ox, oz, side = calibration_frame
    axis = (np.arange(512, dtype=np.float64) + .5) * side / 512
    x, z = np.meshgrid(ox + axis, oz + axis)
    values = _field_values(preset, seed, layout_id, region_side, x, z, frame)
    target = water if preset == "lakes" else 1.0 - water
    return float(np.quantile(values, 1.0 - target))


def _threshold(spec):
    frame = ((*spec.frame_origin_m, spec.frame_side_m) if spec.mode == MODE_FINITE else None)
    calibration = frame if frame is not None else (0.0, 0.0, 12_288_000.0)
    return _calibrated_threshold(spec.preset, spec.world_seed, spec.layout_id, spec.region_side_m,
                                 spec.total_water_fraction, frame, calibration)


def layout_field(spec, x_m, z_m):
    """Signed continuous field: positive means lake or land core, respectively."""
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64),
                               np.asarray(z_m, dtype=np.float64))
    frame = ((*spec.frame_origin_m, spec.frame_side_m) if spec.mode == MODE_FINITE else None)
    return _field_values(spec.preset, spec.world_seed, spec.layout_id, spec.region_side_m,
                         x, z, frame) - _threshold(spec)


def classify_points(spec, x_m, z_m):
    """Class at world coordinates: LAND / OCEAN / LAKE. **No window parameter.**

    The query depends on the point and the spec only. Two overlapping windows therefore
    agree by construction, and no sampling window can re-solve geometry.
    """
    if not isinstance(spec, LayoutSpec):
        raise LayoutError("classify_points() needs a LayoutSpec")
    x = np.asarray(x_m, dtype=np.float64)
    z = np.asarray(z_m, dtype=np.float64)
    x, z = np.broadcast_arrays(x, z)
    out = np.full(x.shape, CLASS_OCEAN, dtype=np.uint8)

    if spec.mode == MODE_FINITE:
        ox, oz = spec.frame_origin_m
        inside = ((x >= ox) & (x < ox + spec.frame_side_m) &
                  (z >= oz) & (z < oz + spec.frame_side_m))
    else:
        inside = np.ones(x.shape, dtype=bool)
    positive = layout_field(spec, x, z) > 0.0
    if spec.preset == "lakes":
        out[inside] = CLASS_LAND
        out[inside & positive] = CLASS_LAKE
    else:
        out[inside & positive] = CLASS_LAND
    return out


def measure_grid(spec, origin_m, side_m, spacing_m):
    """Measure the realised layout on a cell-centre grid. Writes nothing.

    ``spacing_m`` is a **diagnostic** sampling interval. Production terrain and river
    routing are TD native 30 m; a coarse grid here is a layout/area diagnostic and is
    never interpolated up to stand in for native 30 m data.
    """
    if not isinstance(spec, LayoutSpec):
        raise LayoutError("measure_grid() needs a LayoutSpec")
    side_m = _finite("side_m", side_m, positive=True)
    spacing_m = _finite("spacing_m", spacing_m, positive=True)
    cells = side_m / spacing_m
    if abs(cells - round(cells)) > 1e-9:
        raise LayoutRefused(REASON_FRAME,
                            "side_m %.6g is not an integer multiple of spacing_m %.6g"
                            % (side_m, spacing_m),
                            {"side_m": side_m, "spacing_m": spacing_m})
    n = int(round(cells))
    if n < 2:
        raise LayoutError("grid needs at least two cells per side")
    axis = float(origin_m) + (np.arange(n, dtype=np.float64) + 0.5) * spacing_m
    gx, gz = np.meshgrid(axis, axis)
    classes = classify_points(spec, gx, gz)
    total = int(classes.size)
    counts = {name: int(np.count_nonzero(classes == value))
              for name, value in (("land", CLASS_LAND), ("ocean", CLASS_OCEAN),
                                  ("lake", CLASS_LAKE))}
    water = (counts["ocean"] + counts["lake"]) / float(total)
    land_count = 0
    ocean_count = 0
    lake_count = 0
    if counts["land"]:
        from scipy import ndimage
        _labels, land_count = ndimage.label(classes == CLASS_LAND,
                                           structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    if counts["ocean"]:
        from scipy import ndimage
        _labels, ocean_count = ndimage.label(classes == CLASS_OCEAN,
                                            structure=np.ones((3, 3), dtype=bool))
    if counts["lake"]:
        from scipy import ndimage
        _labels, lake_count = ndimage.label(classes == CLASS_LAKE,
                                           structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    return {"schema": SCHEMA + "-measure-v1", "identity": spec.identity(),
            "grid": {"origin_m": float(origin_m), "side_m": side_m,
                     "spacing_m": spacing_m, "cells_per_side": n, "cells": total},
            "class_cells": counts,
            "water_fraction": water,
            "target_water_fraction": spec.total_water_fraction,
            "abs_error": abs(water - spec.total_water_fraction),
            "land_components_4": int(land_count),
            "ocean_components_8": int(ocean_count),
            "lake_components_4": int(lake_count),
            "claim_level": "macro_layout_diagnostic_only",
            "sampling_note": "spacing_m is a diagnostic interval; production terrain "
                             "and river routing are TD native 30 m"}


def describe():
    """Declared capabilities of this module. Nothing here is a measured result."""
    return {"schema": SCHEMA, "algorithm": ALGORITHM, "presets": list(PRESETS),
            "modes": list(MODES), "roles": list(ROLES),
            "reason_codes": list(REASON_CODES),
            "production_spacing_m": 30.0, "minimum_unit_m": 1.0,
            "minimum_unit_achieved": False,
            "terrain_diffusion_inference": False, "gpu": False,
            "claim_level": "macro_layout_diagnostic_only"}
