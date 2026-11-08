"""Compose a fixed native TD source with a continuous macro terrain field.

The source page is filtered once, with an explicit invalid border equal to the
filter support. Cropping the resulting product never recomputes its residual.
Separate source pages are not asserted to have matching residuals in overlap.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter, label

from terrain_pipeline.world_water_layout import LayoutSpec, layout_field

SCHEMA = "world-terrain-composition-v1"
SPACING_M = 30.0


def make_ocean_plan(spec, pixels=512, min_ocean_area_fraction=0.05):
    """Classify whole-frame macro water components on a fixed diagnostic grid."""
    if not isinstance(spec, LayoutSpec) or spec.mode != "finite" or spec.preset == "lakes":
        raise ValueError("ocean planning requires a finite ocean-preset layout")
    if type(pixels) is not int or not 2 <= pixels <= 2048:
        raise ValueError("pixels must be an integer in [2, 2048]")
    if (isinstance(min_ocean_area_fraction, bool) or
            not isinstance(min_ocean_area_fraction, (int, float)) or
            not 0 <= min_ocean_area_fraction <= 1):
        raise ValueError("min_ocean_area_fraction must be in [0, 1]")
    ox, oz = spec.frame_origin_m
    step = spec.frame_side_m / pixels
    axis = (np.arange(pixels, dtype=np.float64) + 0.5) * step
    x, z = np.meshgrid(ox + axis, oz + axis)
    components, count = label(layout_field(spec, x, z) <= 0.0)
    if count == 0:
        raise ValueError("macro planning grid contains no water component")
    sizes = np.bincount(components.ravel(), minlength=count + 1)
    sizes[0] = 0
    selected = sizes >= min_ocean_area_fraction * pixels * pixels
    selected[0] = False
    selected[int(np.argmax(sizes))] = True
    nearest_water = distance_transform_edt(components == 0, return_distances=False,
                                           return_indices=True)
    mask = selected[components[tuple(nearest_water)]]
    record = {"schema": "world-ocean-plan-v2", "layout_identity": spec.identity(),
              "origin_m": [ox, oz], "side_m": spec.frame_side_m,
              "pixels": pixels, "spacing_m": step,
              "min_ocean_area_fraction": float(min_ocean_area_fraction),
              "selection": "largest plus components at least the declared fraction of the whole frame",
              "ownership": "nearest classified water grid centre; exact field determines shoreline",
              "connectivity": 4, "water_components": int(count),
              "ocean_components": int(np.count_nonzero(selected)),
              "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
              "limitation": "macro sampled topology and nearest ownership; sub-grid water bodies and 30m connectivity are not certified"}
    record["identity"] = hashlib.sha256(json.dumps(record, sort_keys=True,
                                                    separators=(",", ":")).encode()).hexdigest()
    return {"ocean_cells": mask, "metadata": record}


def sample_ocean_mask(plan, spec, x_m, z_m):
    """Use nearest sampled water ownership and the exact field's water side."""
    record = plan["metadata"]
    if spec.identity() != record["layout_identity"]:
        raise ValueError("ocean plan does not match layout identity")
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64),
                               np.asarray(z_m, dtype=np.float64))
    ox, oz = record["origin_m"]
    side = record["side_m"]
    if (not np.isfinite(x).all() or not np.isfinite(z).all() or
            np.any(x < ox) or np.any(z < oz) or np.any(x >= ox + side) or np.any(z >= oz + side)):
        raise ValueError("ocean query lies outside the finite world")
    col = np.floor((x - ox) / record["spacing_m"]).astype(np.int64)
    row = np.floor((z - oz) / record["spacing_m"]).astype(np.int64)
    return plan["ocean_cells"][row, col] & (layout_field(spec, x, z) <= 0.0)


def _compose_fields(spec, source, residual, x, z, ocean_mask):
    signal = layout_field(spec, x, z)
    if spec.preset == "lakes":
        if ocean_mask is not None:
            raise ValueError("lakes base does not accept a water mask")
        macro = 400.0 - 700.0 * np.tanh(signal / 0.25)
        correction = residual
        ocean = None
    else:
        if ocean_mask is None:
            raise ValueError("ocean presets require an externally determined ocean mask")
        ocean = np.asarray(ocean_mask)
        if ocean.dtype != np.bool_ or ocean.shape != source.shape:
            raise ValueError("ocean_mask must be a boolean array matching the source")
        if np.any(ocean & (signal > 0)):
            raise ValueError("ocean mask includes macro land")
        macro = np.where(signal >= 0.0, 700.0, 600.0) * np.tanh(signal / 0.08)
        limit = 0.8 * np.abs(macro)
        correction = np.clip(residual, -limit, limit)
    return macro, correction, macro + correction, ocean


def compose_source(spec, td_elevation_zx, origin_native_xz, *, source_record,
                   ocean_mask=None, sigma_cells=6.0):
    """Compose one complete, fixed TD source; arrays use [z, x] native cells.

    ``source_record`` identifies the original page with ``sha256`` and
    ``world_seed``. For ocean presets, ``ocean_mask`` is an externally determined
    ocean classification, not a test of elevation; it must only occupy the
    macro field's water side. Lakes mode has no water classification here.
    """
    if not isinstance(spec, LayoutSpec):
        raise ValueError("spec must be a LayoutSpec")
    source = np.asarray(td_elevation_zx, dtype=np.float64)
    if source.ndim != 2 or not np.isfinite(source).all():
        raise ValueError("TD elevation must be a finite 2D array")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2
            or any(type(v) is not int for v in origin_native_xz)):
        raise ValueError("origin_native_xz must contain two native integer indices")
    if not isinstance(source_record, dict) or source_record.get("world_seed") != spec.world_seed:
        raise ValueError("source world_seed must match the layout")
    digest = source_record.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("source_record must contain a lowercase SHA256")
    if isinstance(sigma_cells, bool) or not isinstance(sigma_cells, (int, float)) or not math.isfinite(sigma_cells) or sigma_cells <= 0:
        raise ValueError("sigma_cells must be finite and positive")
    halo = int(math.ceil(3.0 * sigma_cells))
    if min(source.shape) <= 2 * halo:
        raise ValueError("source page does not contain a filter interior")

    rows, columns = source.shape
    x = (origin_native_xz[0] + np.arange(columns, dtype=np.float64))[None, :] * SPACING_M
    z = (origin_native_xz[1] + np.arange(rows, dtype=np.float64))[:, None] * SPACING_M
    x, z = np.broadcast_arrays(x, z)
    if spec.mode == "finite":
        ox, oz = spec.frame_origin_m
        if not (x.min() >= ox and z.min() >= oz and x.max() < ox + spec.frame_side_m
                and z.max() < oz + spec.frame_side_m):
            raise ValueError("source page extends outside the finite world")
    smooth = gaussian_filter(source, sigma=float(sigma_cells), radius=halo, mode="nearest")
    residual = source - smooth
    macro, correction, composed, ocean = _compose_fields(spec, source, residual, x, z, ocean_mask)
    valid = np.zeros(source.shape, dtype=bool)
    valid[halo:-halo, halo:-halo] = True
    parameters = {"schema": SCHEMA, "layout_identity": spec.identity(),
                  "world_seed": spec.world_seed, "origin_native_xz": list(origin_native_xz),
                  "shape_zx": list(source.shape), "spacing_m": SPACING_M,
                  "source_record": dict(source_record), "sigma_cells": float(sigma_cells),
                  "source_array_sha256": hashlib.sha256(np.ascontiguousarray(source).tobytes()).hexdigest(),
                  "ocean_mask_sha256": (hashlib.sha256(np.ascontiguousarray(ocean).tobytes()).hexdigest()
                                        if ocean is not None else None),
                  "filter_radius_cells": halo, "filter": "gaussian_fixed_source",
                  "macro": "continuous_layout_field", "sea_level_m": 0.0 if ocean is not None else None,
                  "ocean_classification": "externally_supplied" if ocean is not None else "not_applicable",
                  "lake_status": "not_modelled", "cross_source_overlap": "not_certified"}
    parameters["identity"] = hashlib.sha256(json.dumps(parameters, sort_keys=True,
                                                         separators=(",", ":"),
                                                         allow_nan=False).encode()).hexdigest()
    return {"td_elevation_m": source.copy(), "macro_elevation_m": macro,
            "td_residual_m": residual, "applied_residual_m": correction,
            "composed_elevation_m": composed, "valid_mask": valid,
            "ocean_mask": None if ocean is None else ocean.copy(), "metadata": parameters}


def crop_composition(product, origin_native_xz, shape_zx):
    """Crop the precomputed source interior; never recompute filtering."""
    origin = product["metadata"]["origin_native_xz"]
    if (len(origin_native_xz) != 2 or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("crop origin and shape require integer pairs")
    x0 = origin_native_xz[0] - origin[0]
    z0 = origin_native_xz[1] - origin[1]
    rows, columns = shape_zx
    mask = product["valid_mask"]
    if (x0 < 0 or z0 < 0 or x0 + columns > mask.shape[1] or z0 + rows > mask.shape[0]
            or not mask[z0:z0 + rows, x0:x0 + columns].all()):
        raise ValueError("crop is outside the source's valid filter interior")
    return {name: (None if array is None else array[z0:z0 + rows, x0:x0 + columns].copy())
            for name, array in product.items() if name != "metadata"} | {
                "metadata": {**product["metadata"], "crop_origin_native_xz": list(origin_native_xz),
                             "crop_shape_zx": list(shape_zx)}}
