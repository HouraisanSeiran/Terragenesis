"""CPU consumers of one frozen ocean-island plan, in absolute X/Z metres.

Raster centres and finite area samples are derived views. The feature inventory
remains authoritative when a grid misses a narrow island or reef.
"""
from dataclasses import dataclass
import math

import numpy as np
from scipy import ndimage

from .ocean_islands import FrozenOceanIslands


def connected_ocean(elevation_m, lagoon=None, sea_level_m=0.0):
    """Four-connected wet cells reachable from a finite domain perimeter.

    This is a finite raster topology, not a point query or periodic topology.
    Registered lagoons are kept separate even if coarse cells bridge a reef.
    """
    height = np.asarray(elevation_m)
    if height.ndim != 2 or not height.size or not np.isfinite(height).all():
        raise ValueError("finite nonempty 2D elevation required")
    wet = height < sea_level_m
    if lagoon is not None:
        lagoon = np.asarray(lagoon, dtype=bool)
        if lagoon.shape != height.shape:
            raise ValueError("lagoon shape mismatch")
        wet &= ~lagoon
    seeds = np.zeros_like(wet)
    seeds[[0, -1], :] = wet[[0, -1], :]
    seeds[:, [0, -1]] = wet[:, [0, -1]]
    return ndimage.binary_propagation(seeds, mask=wet)


def compose_surface(product, x_m, z_m, base_elevation_m=None):
    """Apply frozen island support after base smoothing/coast cleanup.

    A supplied terrain is preserved outside island supports; a continuous weight
    blends its outer fringe, while island and lagoon interiors are authoritative.
    No old ocean mask is applied. No global ocean connectivity is inferred here.
    """
    if not isinstance(product, FrozenOceanIslands):
        raise TypeError("prepared FrozenOceanIslands required")
    result = dict(product.query(x_m, z_m))
    if base_elevation_m is not None:
        base = np.asarray(base_elevation_m, dtype=float)
        try:
            base = np.broadcast_to(base, result["elevation_m"].shape)
        except ValueError as error:
            raise ValueError("base surface shape mismatch") from error
        if not np.isfinite(base).all():
            raise ValueError("nonfinite base surface")
        weight = result["protection_weight"]
        result["elevation_m"] = base + weight * (result["elevation_m"] - base)
        result["frozen_base_elevation_m"] = result["base_elevation_m"]
        result["frozen_relief_m"] = result["relief_m"]
        result["base_elevation_m"] = base.copy()
        result["relief_m"] = result["elevation_m"] - result["base_elevation_m"]
        result["lagoon"] = result["lagoon"] & (result["elevation_m"] < product.source.sea_level_m)
    result["land"] = result["elevation_m"] >= product.source.sea_level_m
    result["below_sea"] = ~result["land"]
    return result


def sample_td_condition(product, x_m, z_m, base_elevation_m=None, *, periodic=False):
    """Vector-aware TD condition input; CPU only, no model generation.

    Explicit periodic=True maps coordinates into the finite source first. This
    repeats that finite plan; it does not generate islands outside its domain.
    The finite product does not guarantee continuity across its periodic seams.
    Conditioning spacing and the model can still fail to resolve tiny islands.
    """
    x, z = np.broadcast_arrays(np.asarray(x_m, float), np.asarray(z_m, float))
    if periodic:
        if not np.isfinite(x).all() or not np.isfinite(z).all():
            raise ValueError("nonfinite condition coordinate")
        xmin, zmin, xmax, zmax = product.source.bounds_m
        x = xmin + (x - xmin) % (xmax - xmin)
        z = zmin + (z - zmin) % (zmax - zmin)
    return compose_surface(product, x, z, base_elevation_m)


@dataclass(frozen=True)
class OceanIslandRaster:
    x_m: np.ndarray
    z_m: np.ndarray
    fields: dict
    bounds_m: tuple
    spacing_m: float
    cell_area_m2: np.ndarray
    land_fraction: np.ndarray
    protected_fraction: np.ndarray
    lagoon_fraction: np.ndarray
    ocean_connected: object
    metadata: dict


def rasterize(product, bounds_m=None, spacing_m=2000.0, land_supersamples=2, max_cells=1000000, area_refinement=8):
    """Directly sample frozen features at arbitrary permitted cell spacing.

    Cell footprints partition bounds (the last row/column may be narrower).
    Fractional land is a bounded regular supersampling estimate, never a claim
    of exact vector area. All feature IDs survive regardless of raster coverage.
    Only a whole-source raster receives a finite-domain ocean topology.
    """
    if not isinstance(product, FrozenOceanIslands):
        raise TypeError("prepared FrozenOceanIslands required")
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("positive finite spacing required")
    if type(land_supersamples) is not int or not 1 <= land_supersamples <= 8:
        raise ValueError("land_supersamples must be an integer in [1,8]")
    if type(area_refinement) is not int or not 1 <= area_refinement <= 8:
        raise ValueError("area_refinement must be an integer in [1,8]")
    bounds = tuple(product.source.bounds_m if bounds_m is None else bounds_m)
    source_bounds = product.source.bounds_m
    if (len(bounds) != 4 or not all(math.isfinite(v) for v in bounds)
            or not source_bounds[0] <= bounds[0] < bounds[2] <= source_bounds[2]
            or not source_bounds[1] <= bounds[1] < bounds[3] <= source_bounds[3]):
        raise ValueError("raster bounds outside finite source")
    nx = math.ceil((bounds[2] - bounds[0]) / spacing_m)
    nz = math.ceil((bounds[3] - bounds[1]) / spacing_m)
    if type(max_cells) is not int or max_cells < 1 or nx * nz > max_cells:
        raise ValueError("raster exceeds output cell budget")
    x_edges = np.minimum(bounds[0] + np.arange(nx + 1) * spacing_m, bounds[2])
    z_edges = np.minimum(bounds[1] + np.arange(nz + 1) * spacing_m, bounds[3])
    dx, dz = np.diff(x_edges), np.diff(z_edges)
    x = x_edges[:-1] + dx / 2
    z = z_edges[:-1] + dz / 2
    fields = compose_surface(product, x[None, :], z[:, None])
    fractions = {name: np.zeros((nz, nx), np.float32) for name in ("land", "protected", "lagoon")}
    for iz in range(land_supersamples):
        sz = z_edges[:-1] + dz * ((iz + .5) / land_supersamples)
        for ix in range(land_supersamples):
            sx = x_edges[:-1] + dx * ((ix + .5) / land_supersamples)
            sampled = product.query(sx[None, :], sz[:, None])
            for name, fraction in fractions.items():
                fraction += sampled[name] / land_supersamples**2
    # Refine potential exposed interiors independently of grid-centre land.
    # This keeps small off-centre islands and narrow reef/lagoon fractions in
    # the consumer, without expanding them into an entire cell of dry land.
    refine = np.zeros((nz, nx), dtype=bool)
    feature_cells = []
    for feature in product.features:
        radius = feature.support_radius_m
        ix0 = max(0, int(np.searchsorted(x_edges, feature.center_x_m-radius, side="right"))-1)
        ix1 = min(nx, int(np.searchsorted(x_edges, feature.center_x_m+radius, side="left")))
        iz0 = max(0, int(np.searchsorted(z_edges, feature.center_z_m-radius, side="right"))-1)
        iz1 = min(nz, int(np.searchsorted(z_edges, feature.center_z_m+radius, side="left")))
        intersects = ix0 < ix1 and iz0 < iz1
        feature_cells.append({"feature_id": feature.feature_id, "kind": feature.kind,
                              "support_cells_zx": [iz0, ix0, iz1, ix1] if intersects else None})
        if feature.peak_elevation_m >= 0 and intersects:
            inner = .5 * radius
            columns = (x_edges[:-1] < feature.center_x_m+inner) & (x_edges[1:] > feature.center_x_m-inner)
            rows = (z_edges[:-1] < feature.center_z_m+inner) & (z_edges[1:] > feature.center_z_m-inner)
            refine |= rows[:, None] & columns[None, :]
    rows, columns = np.nonzero(refine)
    refinement = max(area_refinement, land_supersamples)
    if len(rows) * refinement**2 > 8000000:
        raise ValueError("subgrid area refinement exceeds eight-million-point budget")
    offsets = (np.arange(refinement) + .5) / refinement
    ox, oz = np.meshgrid(offsets, offsets)
    for start in range(0, len(rows), 2048):
        rz, cx = rows[start:start+2048], columns[start:start+2048]
        sx = x_edges[cx, None] + dx[cx, None] * ox.ravel()[None, :]
        sz = z_edges[rz, None] + dz[rz, None] * oz.ravel()[None, :]
        sampled = product.query(sx, sz)
        for name, fraction in fractions.items():
            fraction[rz, cx] = sampled[name].mean(axis=1)
    full_source = bounds == tuple(source_bounds)
    ocean = connected_ocean(fields["elevation_m"], fields["lagoon"]) if full_source else None
    metadata = {"product_identity": product.identity, "source_identity": product.source.identity,
                "source_world_seed": product.source.world_seed, "coordinates": "X east, Z south; metres; cell centres",
                "shape_zx": [nz, nx], "bounds_m": bounds, "spacing_m": spacing_m,
                "land_area_method": f"{land_supersamples}x{land_supersamples} regular samples; potential exposed inner supports refined {refinement}x{refinement}; finite quadrature can miss narrower strips",
                "refined_cells": int(len(rows)), "refinement_query_points": int(len(rows) * refinement**2),
                "area_refinement_requested": area_refinement, "area_refinement_used": refinement,
                "area_error": f"No exact vector-area bound. Fractions are approximate; narrower than spacing/{refinement} may remain unresolved. Never inflate a detected island to one full cell.",
                "feature_support_cells": feature_cells,
                "feature_ids": [f.feature_id for f in product.features], "feature_authority": "frozen vector inventory retained independently of raster",
                "topology": "whole finite source; four-neighbour perimeter flood; lagoons excluded; no periodic seams" if full_source else "window only; global ocean topology not computed"}
    return OceanIslandRaster(x, z, fields, bounds, spacing_m, dz[:, None] * dx[None, :],
                             fractions["land"], fractions["protected"], fractions["lagoon"], ocean, metadata)
