"""Compose a native window from pinned overlapping TD pages and a filter halo."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from scipy.ndimage import gaussian_filter

from terrain_pipeline.surface_rivers.native_30m_source import (
    BORDER_BAND_CELLS, _page_records, _read_page,
)
from terrain_pipeline.world_terrain_composition import (
    SPACING_M, _compose_fields, make_ocean_plan, sample_ocean_mask,
)
from terrain_pipeline.world_water_layout import LayoutSpec


def _read_support(spec, page_records, hx, hz, hrows, hcols, source_family):
    field = np.empty((hrows, hcols), dtype=np.float64)
    resolved = np.zeros((hrows, hcols), dtype=bool)
    records = ([] if isinstance(page_records, (list, tuple)) and not page_records else
               sorted(_page_records(page_records), key=lambda item: item["path"]))
    sources = []
    known = set()
    generations = set()
    for record in records:
        page, metadata, origin = _read_page(record, seed=spec.world_seed)
        embedded = metadata.get("conditioning_identity") or metadata.get("source_family")
        generation = metadata.get("physical_generation_identity")
        if generation is not None:
            generations.add(generation)
            if len(generations) > 1:
                raise ValueError("physical generation identities differ")
        known.add(embedded is not None)
        if embedded is not None and embedded != source_family:
            raise ValueError("source family does not match page metadata")
        px, pz = origin
        edge = BORDER_BAND_CELLS
        sources.append({**record, "physical_generation_identity": generation,
                        "trusted_bounds_native_xz": [px + edge, pz + edge,
                        px + page.shape[1] - edge, pz + page.shape[0] - edge]})
        left, top = max(hx, px + edge), max(hz, pz + edge)
        right = min(hx + hcols, px + page.shape[1] - edge)
        bottom = min(hz + hrows, pz + page.shape[0] - edge)
        if left >= right or top >= bottom:
            continue
        target = np.s_[top - hz:bottom - hz, left - hx:right - hx]
        values = page[top - pz:bottom - pz, left - px:right - px]
        existing = resolved[target]
        if existing.any() and not np.array_equal(field[target][existing], values[existing]):
            raise ValueError("trusted TD page overlap disagrees")
        field[target][~existing] = values[~existing]
        resolved[target] = True
    return field, resolved, records, sources, known


def _family_verification(known):
    if known == {True}:
        return "embedded"
    if known == {True, False}:
        return "mixed_embedded_and_caller_declared"
    return "caller_declared"


def inspect_window_support(spec, page_records, origin_native_xz, shape_zx, *,
                           sigma_cells=6.0, max_cells=1048576, source_family):
    """Read pinned pages and report exact missing target-plus-halo cells, without filtering."""
    if not isinstance(spec, LayoutSpec) or not isinstance(source_family, str) or not source_family.strip():
        raise ValueError("layout and explicit source family required")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2 or
            not isinstance(shape_zx, (tuple, list)) or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    if (isinstance(sigma_cells, bool) or not isinstance(sigma_cells, (int, float)) or
            not math.isfinite(sigma_cells) or sigma_cells <= 0):
        raise ValueError("sigma_cells must be finite and positive")
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError("max_cells must be a positive integer")
    halo = int(math.ceil(3 * sigma_cells))
    rows, cols = shape_zx
    if spec.mode == "finite":
        fx, fz = spec.frame_origin_m
        x0, z0 = origin_native_xz
        if not (fx <= x0 * SPACING_M and fz <= z0 * SPACING_M and
                (x0 + cols - 1) * SPACING_M < fx + spec.frame_side_m and
                (z0 + rows - 1) * SPACING_M < fz + spec.frame_side_m):
            raise ValueError("target lies outside finite world")
    hrows, hcols = rows + 2 * halo, cols + 2 * halo
    if hrows * hcols > max_cells:
        raise ValueError("target and filter halo exceed max_cells")
    hx, hz = origin_native_xz[0] - halo, origin_native_xz[1] - halo
    _, resolved, records, sources, known = _read_support(
        spec, page_records, hx, hz, hrows, hcols, source_family)
    return {"support_origin_native_xz": [hx, hz], "support_shape_zx": [hrows, hcols],
            "missing_mask": ~resolved, "missing_cells": int(np.count_nonzero(~resolved)),
            "source_records": records, "sources": sources, "source_family": source_family,
            "source_family_verification": _family_verification(known),
            "filter_radius_cells": halo, "source_border_cells": BORDER_BAND_CELLS}


def compose_window(spec, page_records, origin_native_xz, shape_zx, *, sigma_cells=6.0,
                   max_cells=1048576, source_family):
    """Compose a target window with fully supplied, verified TD filter support.

    ``source_family`` is an explicit source-family declaration. When pages carry
    a conditioning identity it must match. Older pages without one rely on the caller's
    declaration, which is recorded as such rather than verified from the file.
    """
    if not isinstance(spec, LayoutSpec):
        raise ValueError("spec must be a LayoutSpec")
    if not isinstance(source_family, str) or not source_family.strip():
        raise ValueError("source_family must be explicitly declared")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2 or
            not isinstance(shape_zx, (tuple, list)) or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    if (isinstance(sigma_cells, bool) or not isinstance(sigma_cells, (int, float)) or
            not math.isfinite(sigma_cells) or sigma_cells <= 0):
        raise ValueError("sigma_cells must be finite and positive")
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError("max_cells must be a positive integer")
    halo = int(math.ceil(3 * sigma_cells))
    rows, cols = shape_zx
    hrows, hcols = rows + 2 * halo, cols + 2 * halo
    if hrows * hcols > max_cells:
        raise ValueError("target and filter halo exceed max_cells")
    x0, z0 = origin_native_xz
    if spec.mode == "finite":
        fx, fz = spec.frame_origin_m
        if not (fx <= x0 * SPACING_M and fz <= z0 * SPACING_M and
                (x0 + cols - 1) * SPACING_M < fx + spec.frame_side_m and
                (z0 + rows - 1) * SPACING_M < fz + spec.frame_side_m):
            raise ValueError("target lies outside finite world")
    hx, hz = x0 - halo, z0 - halo
    field, resolved, records, _, known = _read_support(
        spec, page_records, hx, hz, hrows, hcols, source_family)
    if not resolved.all():
        raise ValueError("TD filter support has %d unresolved cells" % np.count_nonzero(~resolved))

    smooth = gaussian_filter(field, sigma=float(sigma_cells), radius=halo, mode="nearest")
    interior = np.s_[halo:halo + rows, halo:halo + cols]
    td = field[interior].copy()
    residual = (field - smooth)[interior].copy()
    x = (x0 + np.arange(cols, dtype=np.float64))[None, :] * SPACING_M
    z = (z0 + np.arange(rows, dtype=np.float64))[:, None] * SPACING_M
    x, z = np.broadcast_arrays(x, z)
    plan = None if spec.preset == "lakes" else make_ocean_plan(spec)
    ocean = None if plan is None else sample_ocean_mask(plan, spec, x, z)
    macro, correction, composed, ocean = _compose_fields(spec, td, residual, x, z, ocean)
    metadata = {"schema": "world-terrain-mosaic-v1", "layout_identity": spec.identity(),
                "world_seed": spec.world_seed, "origin_native_xz": [x0, z0],
                "shape_zx": [rows, cols], "spacing_m": SPACING_M,
                "source_family": source_family,
                "source_family_verification": _family_verification(known),
                "source_records": records, "source_border_cells": BORDER_BAND_CELLS,
                "filter": "gaussian_fixed_support", "sigma_cells": float(sigma_cells),
                "filter_radius_cells": halo, "ocean_plan": None if plan is None else plan["metadata"],
                "lake_status": "not_modelled"}
    metadata["identity"] = hashlib.sha256(json.dumps(metadata, sort_keys=True,
                                                      separators=(",", ":"),
                                                      allow_nan=False).encode()).hexdigest()
    return {"td_elevation_m": td, "macro_elevation_m": macro, "td_residual_m": residual,
            "applied_residual_m": correction, "composed_elevation_m": composed,
            "valid_mask": np.ones((rows, cols), dtype=bool), "ocean_mask": ocean,
            "metadata": metadata}
