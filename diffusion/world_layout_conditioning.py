"""World-layout conditioning: map a ``LayoutSpec`` to Terrain Diffusion elevation.

What this module is
-------------------
The bridge between the continuous water/land layout
(:mod:`terrain_pipeline.world_water_layout`) and a Terrain Diffusion conditioning
surface. It answers one question: *given this layout, what elevation band should the
conditioner ask the model for at this world coordinate?*

It is an **adapter**, not a new terrain model. It does not run inference, does not touch
a GPU, and does not modify the frozen physical conditioner.

Why a separate config type
--------------------------
``PhysicalGenerationConfig`` validates ``algorithm == "geography_physical_v1"`` and binds
four source files into its identity. Changing any of that would silently change an
existing identity family. A layout-driven conditioner is a **new source**, so it gets its
own config (:class:`WorldLayoutGenerationConfig`) and its own identity. The old config
stays untouched and can still be used as a base record source: :meth:`WorldLayoutGenerationConfig.from_base`
**reads** it and records the borrowed fields, which is composition, not modification.

Sea datum and units
-------------------
``sea_datum_m = 0`` is preserved (the project keeps a single physical datum). Elevation
is metres above it; negative is sea floor. Production terrain and river routing are TD
native **30 m**; the minimum accounting unit is 1 m, which this adapter does **not**
claim to deliver.
"""
from __future__ import annotations

import hashlib
import json
import math

__all__ = [
    "SCHEMA",
    "ALGORITHM",
    "SEA_DATUM_M",
    "NATIVE_RESOLUTION_M",
    "WorldLayoutGenerationConfig",
    "layout_elevation_m",
    "make_conditioning_map",
    "CONDITIONING_SPACING_M",
    "select_nonempty_window",
]

SCHEMA = "world-layout-conditioning-v1"
ALGORITHM = "continuous-layout-shore-elevation-v2"

#: Single physical sea datum, metres. Never re-based here.
SEA_DATUM_M = 0.0

#: TD native sampling/routing spacing. A layout adapter must not claim anything finer.
NATIVE_RESOLUTION_M = 30.0

#: Conditioning-grid spacing for the 30 m checkpoint: ``latent_compression(8) * 32 *
#: 30 m``. ``sample_raw`` indices are in **this** unit, never in native 30 m -- mixing the
#: two would ask the model for a field 256x too fine. Defined here, before any default
#: argument refers to it.
CONDITIONING_SPACING_M = NATIVE_RESOLUTION_M * 8 * 32

#: Elevation budget, metres. Declared engineering values, not calibration.
LAND_BASE_M = 220.0
LAND_RELIEF_M = 900.0
OCEAN_DEPTH_M = 600.0
LAKE_BED_OFFSET_M = 40.0


def _finite(name, value, *, positive=False, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % name)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % name)
    if positive and number <= 0.0:
        raise ValueError("%s must be positive" % name)
    if not allow_zero and number == 0.0:
        raise ValueError("%s must be non-zero" % name)
    return number


class WorldLayoutGenerationConfig:
    """Immutable identity of a layout-driven conditioning surface.

    Deliberately **not** ``PhysicalGenerationConfig``: a different source deserves a
    different identity, so no existing hash family moves.
    """

    __slots__ = ("layout_identity", "preset", "mode", "target_water_fraction",
                 "native_resolution_m", "sea_datum_m", "land_base_m",
                 "land_relief_m", "ocean_depth_m", "lake_bed_offset_m",
                 "borrowed_from_base")

    def __init__(self, layout_identity, preset, mode, target_water_fraction, *,
                 native_resolution_m=NATIVE_RESOLUTION_M, sea_datum_m=SEA_DATUM_M,
                 land_base_m=LAND_BASE_M, land_relief_m=LAND_RELIEF_M,
                 ocean_depth_m=OCEAN_DEPTH_M, lake_bed_offset_m=LAKE_BED_OFFSET_M,
                 borrowed_from_base=None):
        if not isinstance(layout_identity, str) or len(layout_identity) != 64:
            raise ValueError("layout_identity must be a 64-character layout hash")
        if preset not in ("earth", "archipelago", "lakes"):
            raise ValueError("unknown preset: %r" % (preset,))
        if mode not in ("infinite", "finite"):
            raise ValueError("unknown mode: %r" % (mode,))
        water = _finite("target_water_fraction", target_water_fraction)
        if not 0.0 <= water <= 1.0:
            raise ValueError("target_water_fraction must be in [0, 1]")
        spacing = _finite("native_resolution_m", native_resolution_m, positive=True)
        if spacing != NATIVE_RESOLUTION_M:
            raise ValueError("layout conditioning is defined at the TD native %r m only, "
                             "got %r" % (NATIVE_RESOLUTION_M, spacing))
        datum = _finite("sea_datum_m", sea_datum_m)
        if datum != SEA_DATUM_M:
            raise ValueError("the physical sea datum is %r m and is never re-based"
                             % (SEA_DATUM_M,))
        self.layout_identity = layout_identity
        self.preset = preset
        self.mode = mode
        self.target_water_fraction = water
        self.native_resolution_m = spacing
        self.sea_datum_m = datum
        self.land_base_m = _finite("land_base_m", land_base_m)
        self.land_relief_m = _finite("land_relief_m", land_relief_m, positive=True)
        self.ocean_depth_m = _finite("ocean_depth_m", ocean_depth_m, positive=True)
        self.lake_bed_offset_m = _finite("lake_bed_offset_m", lake_bed_offset_m,
                                         positive=True)
        self.borrowed_from_base = dict(borrowed_from_base or {})

    @classmethod
    def from_layout(cls, spec, **kwargs):
        """Build the config from a :class:`LayoutSpec`; identity comes from the layout."""
        return cls(spec.identity(), spec.preset, spec.mode,
                   spec.total_water_fraction, **kwargs)

    @classmethod
    def from_base(cls, base_config, spec, **kwargs):
        """Read a frozen physical config as a **base record**, without changing it.

        Composition, not modification: the borrowed fields are copied into
        ``borrowed_from_base`` so the new identity records where they came from while the
        original object and its hash family stay exactly as they were.
        """
        borrowed = {}
        for name in ("native_resolution_m", "sea_datum_m", "model_dir", "dtype"):
            if hasattr(base_config, name):
                borrowed[name] = getattr(base_config, name)
        kwargs.setdefault("borrowed_from_base", borrowed)
        return cls.from_layout(spec, **kwargs)

    def record(self):
        return {"schema": SCHEMA, "algorithm": ALGORITHM,
                "layout_identity": self.layout_identity,
                "preset": self.preset, "mode": self.mode,
                "target_water_fraction": self.target_water_fraction,
                "native_resolution_m": self.native_resolution_m,
                "sea_datum_m": self.sea_datum_m,
                "land_base_m": self.land_base_m,
                "land_relief_m": self.land_relief_m,
                "ocean_depth_m": self.ocean_depth_m,
                "lake_bed_offset_m": self.lake_bed_offset_m,
                "borrowed_from_base": dict(self.borrowed_from_base),
                "coordinates": "x east, z south; arrays [z, x]; metres",
                "production_spacing_m": NATIVE_RESOLUTION_M,
                "conditioning_spacing_m": CONDITIONING_SPACING_M,
                "shore_field_scale": 0.08,
                "water_surface_m": self.sea_datum_m,
                "conditioning_note": "7.68 km samples do not enforce small lakes in TD output",
                "minimum_unit_m": 1.0,
                "minimum_unit_achieved": False}

    def identity(self):
        payload = json.dumps(self.record(), sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
# elevation band from the layout
def layout_elevation_m(spec, config, x_m, z_m):
    """Continuous idealized bed and shore, in metres relative to water level.

    A field value of zero is the declared water level. The field is a layout
    signal rather than a metric distance, so this is an illustrative slope,
    not a calibrated bathymetry or a hard constraint on the TD output.
    """
    import numpy as np
    from terrain_pipeline.world_water_layout import layout_field

    signed = layout_field(spec, x_m, z_m)
    land_signal = -signed if spec.preset == "lakes" else signed
    land = (config.land_base_m + 0.5 * config.land_relief_m) * np.tanh(
        np.maximum(land_signal, 0.0) / 0.08)
    depth = config.lake_bed_offset_m if spec.preset == "lakes" else config.ocean_depth_m
    bed = -depth * np.tanh(np.maximum(-land_signal, 0.0) / 0.08)
    return config.sea_datum_m + land + bed


# --------------------------------------------------------------------------- #
# fixed global boundary selection
# --------------------------------------------------------------------------- #
def select_nonempty_window(spec, size_cells, *, spacing_m=NATIVE_RESOLUTION_M, prefer="coast"):
    """Select the first fixed-grid class transition, refined at its actual boundary."""
    import numpy as np
    from terrain_pipeline.world_water_layout import CLASS_LAND, CLASS_LAKE, CLASS_OCEAN, classify_points

    size = int(size_cells)
    if size < 2 or prefer not in ("coast", "lake", "any"):
        raise ValueError("invalid page size or preference")
    if spec.mode == "finite":
        ox, oz = spec.frame_origin_m
        side = spec.frame_side_m
    else:
        ox, oz, side = 0.0, 0.0, 12_288_000.0
    step = side / 512.0
    axis = (np.arange(512, dtype=np.float64) + .5) * step
    gx, gz = np.meshgrid(ox + axis, oz + axis)
    classes = classify_points(spec, gx, gz)
    water = CLASS_LAKE if prefer == "lake" else CLASS_OCEAN
    if prefer == "any":
        water = CLASS_LAKE if spec.preset == "lakes" else CLASS_OCEAN
    transitions = ((classes[:, :-1] == CLASS_LAND) & (classes[:, 1:] == water)) | (
        (classes[:, :-1] == water) & (classes[:, 1:] == CLASS_LAND))
    positions = np.argwhere(transitions)
    for row, col in positions:
        left = float(gx[row, col])
        right = float(gx[row, col + 1])
        z = float(gz[row, col])
        left_class = int(classes[row, col])
        for _ in range(35):
            middle = (left + right) / 2.0
            if int(classify_points(spec, middle, z)) == left_class:
                left = middle
            else:
                right = middle
        anchor_x = (left + right) / 2.0
        extent = (size - 1) * float(spacing_m)
        origin_x = round((anchor_x - extent / 2.0) / spacing_m) * spacing_m
        origin_z = round((z - extent / 2.0) / spacing_m) * spacing_m
        if spec.mode == "finite" and not (
                ox <= origin_x and oz <= origin_z and
                origin_x + extent < ox + side and origin_z + extent < oz + side):
            continue
        page_axis = np.arange(size, dtype=np.float64) * float(spacing_m)
        px, pz = np.meshgrid(origin_x + page_axis, origin_z + page_axis)
        page = classify_points(spec, px, pz)
        has_land = bool((page == CLASS_LAND).any())
        has_ocean = bool((page == CLASS_OCEAN).any())
        has_lake = bool((page == CLASS_LAKE).any())
        if has_land and ((water == CLASS_LAKE and has_lake) or
                         (water == CLASS_OCEAN and has_ocean)):
            return {"origin_m": [origin_x, origin_z], "size_cells": size,
                    "spacing_m": float(spacing_m), "extent_m": extent,
                    "anchor_m": [anchor_x, z],
                    "contains": {"land": has_land, "ocean": has_ocean, "lake": has_lake},
                    "rule": "first fixed 512-grid horizontal transition, refined by bisection"}
    raise ValueError("no %r boundary found in the fixed selection grid" % prefer)


# --------------------------------------------------------------------------- #
# conditioning factory protocol (CPU only; no inference)
# --------------------------------------------------------------------------- #
def make_conditioning_map(spec, config, *, origin_world_m,
                          conditioning_spacing_m=CONDITIONING_SPACING_M):
    """Build a conditioning map for one window. **Pure CPU, no model, no GPU.**

    Returns a **callable** factory exposing ``sample_raw(i1, j1, i2, j2)``, matching the
    protocol ``WorldPipeline`` uses: both ``geography_physical.make_physical_map_factory``
    and ``geography_v5.make_geographic_map_factory`` return a *function* that carries
    ``.finalize`` (and, in v5, ``.sample_components``). ``sample_raw`` takes **integer
    conditioning indices**, not metres.

    Index units matter
    ------------------
    The upstream lookups are in *conditioning grid* indices, whose spacing is
    ``latent_compression * 32 * native_resolution`` (7680 m for the 30 m checkpoint), not
    the 30 m native spacing. Index ``i`` is world ``origin_world_m + i *
    conditioning_spacing_m``. The layout is still queried in metres, so the 30 m
    production spacing stays a property of the terrain and never of the index.
    """
    import numpy as np

    origin_x, origin_z = (float(value) for value in origin_world_m)
    step = float(conditioning_spacing_m)
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("conditioning_spacing_m must be finite and positive")

    def coordinates(j1, i1, j2, i2):
        """Conditioning-index box -> world metres.

        Argument order follows the caller: ``WorldPipeline._conditioning_model_input``
        calls ``synthetic_map_factory(cj0, ci0, cj1, ci1)``, i.e. **columns first**.
        ``i`` is the row axis (z, south) and ``j`` the column axis (x, east).
        """
        for value, name in ((i1, "i1"), (j1, "j1"), (i2, "i2"), (j2, "j2")):
            if type(value) is not int:
                raise ValueError("%s must be a plain int conditioning index" % name)
        if i2 < i1 or j2 < j1:
            raise ValueError("invalid conditioning window")
        gx = origin_x + np.arange(j1, j2, dtype=np.float64)[None, :] * step
        gz = origin_z + np.arange(i1, i2, dtype=np.float64)[:, None] * step
        return np.broadcast_arrays(gx, gz)

    def sample_raw(j1, i1, j2, i2):
        gx, gz = coordinates(j1, i1, j2, i2)
        elevation = layout_elevation_m(spec, config, gx, gz)
        shape = elevation.shape
        out = np.zeros((5,) + shape, dtype=np.float32)
        out[0] = elevation
        out[1] = 15.0          # placeholder temperature, declared not modelled
        out[2] = 800.0         # placeholder temperature std (centi-degrees)
        out[3] = 1000.0        # placeholder annual precipitation, mm
        out[4] = 30.0          # placeholder precipitation cv, percent
        return out

    def finalize(raw):
        values = np.asarray(raw, dtype=np.float32)
        if values.ndim != 3 or values.shape[0] != 5 or not np.isfinite(values).all():
            raise ValueError("expected finite conditioning [5, H, W]")
        return values.copy()

    def sample_components(j1, i1, j2, i2):
        gx, gz = coordinates(j1, i1, j2, i2)
        return {"elevation_m": layout_elevation_m(spec, config, gx, gz)}

    def sample_full(j1, i1, j2, i2):
        import torch
        values = finalize(sample_raw(j1, i1, j2, i2))
        values[0] = np.sign(values[0]) * np.sqrt(np.abs(values[0]))
        return torch.from_numpy(values)

    sample_full.sample_raw = sample_raw
    sample_full.sample_components = sample_components
    sample_full.finalize = finalize
    sample_full.origin_world_m = (origin_x, origin_z)
    sample_full.conditioning_spacing_m = step
    sample_full.layout_identity = config.layout_identity
    sample_full.conditioning_identity = config.identity()
    sample_full.native_resolution_m = NATIVE_RESOLUTION_M
    sample_full.channel_provenance = {
        "elevation": "continuous_layout_shore_field",
        "temperature": "declared_placeholder_not_modelled",
        "temperature_std": "declared_placeholder_not_modelled",
        "precipitation": "declared_placeholder_not_modelled",
        "precipitation_cv": "declared_placeholder_not_modelled",
    }
    sample_full.claim_level = "macro_layout_diagnostic_only"
    return sample_full

