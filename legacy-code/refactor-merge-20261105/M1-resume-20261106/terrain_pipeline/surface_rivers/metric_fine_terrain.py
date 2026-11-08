"""30 m river-network base: analytic sampling, TD detail band, seam-free mosaics.

Why this module exists
----------------------
`terrain_pipeline.hydrology_planning.coarse_condition_field` already samples the
physical conditioning field (`diffusion.geography_physical.sample_physical`) at
whatever coordinates it is handed. The river network was planned on a **10 km
page** of that field and then interpolated onto the working lattice. Two
separate things are wrong with that, and they must not be confused:

1. **Coarser than the field.** The finest structure in `sample_physical` is the
   `detail` octave `((2, 1), (1, .35))` times `geographic_scale_m = 7680 m`, i.e.
   15.36 km and **7.68 km** wavelengths. (See `geographic_noise.field`: the
   octave argument is a wavelength in grid units and `east/south` are already
   normalised by `geographic_scale_m`.)
2. **Aliased.** A 10 km page under-samples the 7.68 km octave (Nyquist for that
   octave is a 3.84 km spacing), so the page carries an *interpolation artefact*
   of that structure, not the structure itself. Measured on the reach window:
   RMS 41.88 m, max 107.43 m, i.e. 28.8% of the field standard deviation.

Sampling the same function directly at 30 m removes both, costs no GPU and no
randomness (a few microseconds per cell on CPU), and is **window-independent**:
the value at a world coordinate does not depend on which window asked for it.

So the 30 m base here is the analytic field, and Terrain Diffusion contributes a
bounded *detail band* on top of it where real sub-kilometre structure matters.
Three declared quantities, never mixed:

===============  ===================================================  ==========
quantity         what it is                                           identity
===============  ===================================================  ==========
`analytic`       `sample_physical(x, z, world_seed)` at 30 m           seed only
`td_generated`   high-frequency band of a TD window, affine-fitted    seed + model
                 onto the analytic low pass                           + window
`composed`       analytic + weight-normalised sum of detail bands      both
===============  ===================================================  ==========

Why the detail band and not the TD field
----------------------------------------
The pinned 30 m checkpoint emits elevation in **its own normalised vertical
frame**, not in world metres (`WorldPipeline._compute_elev` decodes a laplacian
pyramid; there is no metre conversion in the vendored code). On the reach window
the large scales of that output are an affine image of the analytic low pass, so
the conversion used here is a fitted line, applied **only to the band above
`detail_sigma_m`**. The band is additionally tapered to exactly zero on the
window border, which is what makes mosaics free of steps: neighbouring windows
contribute a term that is zero at the seam by construction.

What a mosaic does and does not guarantee
-----------------------------------------
Guaranteed: the large scales are the *same* analytic field everywhere, and each
window's detail term is exactly zero on that window's border, so there is no
step at a seam from the composition itself.
Not guaranteed: two windows observe independent TD samples, so their detail
bands differ where they overlap. `mosaic_detail_m` averages them by coverage
weight (`sum(w*d)/max(sum w, eps) * min(sum w, 1)`), and `seam_diagnostics`
reports the measured disagreement rather than hiding it.

Why a 10 km page must NOT be used as the "surround" of a 30 m window
--------------------------------------------------------------------
Because that is exactly where a step appears: the analytic 30 m field and the
10 km bilinear page differ by RMS 41.9 m, so a boundary between them is a
41.9 m-class cliff. The analytic field is free to evaluate anywhere, so the
30 m base is **global** and only the TD band is windowed. `transition_step_m`
quantifies this for anyone who wants to try the other way.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

import numpy as np

from diffusion.geography_physical import sample_physical
from terrain_pipeline.common_infra import identity, readonly

FINE_SPACING_M = 30.0
SAMPLE_CALL_CELLS = 1_048_576
DEFAULT_RECONCILE_SIGMA_M = 20_000.0
DEFAULT_DETAIL_SIGMA_M = 3_000.0
DEFAULT_EDGE_MARGIN_M = 1_500.0


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    return value


def _shape(shape):
    if len(shape) != 2:
        raise ValueError("[row, column] shape required")
    rows, columns = (int(value) for value in shape)
    if rows < 2 or columns < 2:
        raise ValueError("at least 2x2 cells required")
    return rows, columns


def _origin(origin_xz_m):
    values = np.asarray(origin_xz_m, np.float64).reshape(-1)
    if values.size != 2 or not np.isfinite(values).all():
        raise ValueError("finite [x, z] origin required")
    return float(values[0]), float(values[1])


def fine_axes(origin_xz_m, shape, spacing_m=FINE_SPACING_M):
    """World coordinates of the lattice points; cell centres, [row(z), column(x)]."""
    rows, columns = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    x0, z0 = _origin(origin_xz_m)
    return (x0 + np.arange(columns) * spacing, z0 + np.arange(rows) * spacing)


def analytic_fine_field(seed, origin_xz_m, shape, spacing_m=FINE_SPACING_M):
    """Direct 30 m sampling of the conditioning field; [z, x] elevation in metres.

    `sample_physical` refuses more than `SAMPLE_CALL_CELLS` per call, so the
    lattice is sampled in row blocks. Block bounds do not affect any value:
    the field is evaluated from absolute world coordinates only.
    """
    rows, columns = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    xs, zs = fine_axes(origin_xz_m, shape, spacing)
    block = max(1, min(rows, SAMPLE_CALL_CELLS // columns))
    out = np.empty((rows, columns), np.float64)
    blocks = []
    for start in range(0, rows, block):
        stop = min(start + block, rows)
        east = np.broadcast_to(xs[None, :], (stop - start, columns))
        south = np.broadcast_to(zs[start:stop, None], (stop - start, columns))
        out[start:stop] = np.asarray(sample_physical(east, south, int(seed))[0], np.float64)
        blocks.append([int(start), int(stop)])
    if not np.isfinite(out).all():
        raise ValueError("conditioning field produced nonfinite elevation")
    return out, {"spacing_m": spacing, "block_rows": blocks, "world_seed": int(seed),
                 "sampler": "diffusion.geography_physical.sample_physical",
                 "coordinates": "cell centres, X east, Z south, arrays [z, x]"}


def bilinear_sample(page, page_origin_xz_m, page_spacing_m, xs, zs):
    """Bilinear sample of a regular page at arbitrary world coordinates (edge clamped).

    Used to reproduce what the reach runs actually did with a 10 km page, so the
    interpolation error of that base can be measured against the analytic field.
    """
    page = np.asarray(page, np.float64)
    if page.ndim != 2 or not np.isfinite(page).all():
        raise ValueError("finite 2D page required")
    step = _positive(page_spacing_m, "page_spacing_m")
    x0, z0 = _origin(page_origin_xz_m)
    rows, columns = page.shape
    gx = np.asarray(xs, np.float64)
    gz = np.asarray(zs, np.float64)
    fx = np.clip((gx - x0) / step, 0., columns - 1. - 1e-9)
    fz = np.clip((gz - z0) / step, 0., rows - 1. - 1e-9)
    i0 = np.floor(fx).astype(np.int64)
    j0 = np.floor(fz).astype(np.int64)
    tx = fx - i0
    tz = fz - j0
    i1 = np.minimum(i0 + 1, columns - 1)
    j1 = np.minimum(j0 + 1, rows - 1)
    tx2, tz2 = np.meshgrid(tx, tz)
    return (page[j0][:, i0] * (1. - tx2) * (1. - tz2) + page[j0][:, i1] * tx2 * (1. - tz2)
            + page[j1][:, i0] * (1. - tx2) * tz2 + page[j1][:, i1] * tx2 * tz2)


def smoothstep(values):
    clipped = np.clip(np.asarray(values, np.float64), 0., 1.)
    return clipped * clipped * (3. - 2. * clipped)


def edge_taper(shape, spacing_m, margin_m):
    """1 in the interior, exactly 0 on the border; smoothstep over `margin_m`."""
    rows, columns = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    margin = _positive(margin_m, "margin_m")
    zs = np.arange(rows) * spacing
    xs = np.arange(columns) * spacing
    distance = np.minimum.reduce([
        np.broadcast_to(xs[None, :], (rows, columns)),
        np.broadcast_to((xs[-1] - xs)[None, :], (rows, columns)),
        np.broadcast_to(zs[:, None], (rows, columns)),
        np.broadcast_to((zs[-1] - zs)[:, None], (rows, columns))])
    weight = smoothstep(distance / margin)
    weight[[0, -1], :] = 0.
    weight[:, [0, -1]] = 0.
    return weight


def affine_reconcile(td, base, spacing_m, reconcile_sigma_m=DEFAULT_RECONCILE_SIGMA_M,
                     detail_sigma_m=DEFAULT_DETAIL_SIGMA_M):
    """Fit the checkpoint's vertical frame onto world metres, then measure the band.

    The fit is done on the low pass at `reconcile_sigma_m` only. It is an
    **uncalibrated engineering conversion** (there is no observational truth for
    this terrain), and it is recorded as such instead of being presented as a
    measurement.
    """
    from scipy import ndimage

    td = np.asarray(td, np.float64)
    base = np.asarray(base, np.float64)
    if td.shape != base.shape or td.ndim != 2:
        raise ValueError("TD and base must share one 2D shape")
    if not (np.isfinite(td).all() and np.isfinite(base).all()):
        raise ValueError("finite TD and base fields required")
    spacing = _positive(spacing_m, "spacing_m")
    sigma_reconcile = _positive(reconcile_sigma_m, "reconcile_sigma_m") / spacing
    sigma_detail = _positive(detail_sigma_m, "detail_sigma_m") / spacing
    td_low = ndimage.gaussian_filter(td, sigma_reconcile, mode="nearest")
    base_low = ndimage.gaussian_filter(base, sigma_reconcile, mode="nearest")
    slope, intercept = np.polyfit(td_low.ravel(), base_low.ravel(), 1)
    if not (math.isfinite(slope) and math.isfinite(intercept)) or slope == 0.:
        raise ValueError("degenerate affine reconciliation")
    residual = base_low - (slope * td_low + intercept)
    return float(slope), float(intercept), {
        "reconcile_sigma_m": float(reconcile_sigma_m), "detail_sigma_m": float(detail_sigma_m),
        "slope": float(slope), "intercept_m": float(intercept),
        "correlation": float(np.corrcoef(td_low.ravel(), base_low.ravel())[0, 1]),
        "residual_rms_m": float(residual.std()),
        "residual_max_m": float(np.max(np.abs(residual))),
        "status": "uncalibrated engineering conversion, not an observation",
        "interpretation": "world_m = slope * td_native + intercept, applied to the detail band only"}


def td_detail_band(td, base, spacing_m=FINE_SPACING_M, *,
                   reconcile_sigma_m=DEFAULT_RECONCILE_SIGMA_M,
                   detail_sigma_m=DEFAULT_DETAIL_SIGMA_M,
                   edge_margin_m=DEFAULT_EDGE_MARGIN_M):
    """High-frequency TD band, in world metres, tapered to zero on the border.

    Returns `detail_m` (already edge-tapered) and the taper `weight_m`. Adding
    `weight * detail_m` to the analytic base changes nothing at the window border
    and nothing at wavelengths longer than `detail_sigma_m`.
    """
    from scipy import ndimage

    td = np.asarray(td, np.float64)
    base = np.asarray(base, np.float64)
    spacing = _positive(spacing_m, "spacing_m")
    slope, intercept, diagnostics = affine_reconcile(
        td, base, spacing, reconcile_sigma_m, detail_sigma_m)
    sigma_cells = _positive(detail_sigma_m, "detail_sigma_m") / spacing
    low = ndimage.gaussian_filter(td, sigma=sigma_cells, mode="nearest")
    band = slope * (td - low)
    weight = edge_taper(td.shape, spacing, edge_margin_m)
    detail = weight * band
    if float(np.abs(detail[[0, -1], :]).max(initial=0.)) != 0. or float(np.abs(detail[:, [0, -1]]).max(initial=0.)) != 0.:
        raise ValueError("edge taper left a nonzero border term")
    diagnostics = dict(diagnostics, edge_margin_m=float(edge_margin_m),
                       band_std_m=float(band.std()), band_min_m=float(band.min()),
                       band_max_m=float(band.max()),
                       border_term_max_abs_m=0.0,
                       border_note="the injected term is exactly zero on the window border")
    return detail, weight, diagnostics


def mosaic_detail_m(contributions):
    """Coverage-weighted sum of edge-tapered detail bands.

    With `coverage = sum(w)`, the result is `sum(w*d)/max(coverage, eps) * min(coverage, 1)`:

    * one window inside        -> coverage 1        -> `d` (full detail)
    * one window on its border -> coverage 0        -> `0` (continuous into the base)
    * one window in the taper  -> coverage w < 1    -> `w*d` (continuous decay)
    * two windows fully stacked-> coverage 2        -> mean of the two bands

    Dividing alone would cancel the taper and put a step exactly at the border,
    which is why `min(coverage, 1)` is not optional.
    """
    if not contributions:
        raise ValueError("at least one detail contribution required")
    shape = None
    detail_sum = None
    coverage = None
    for detail, weight in contributions:
        detail = np.asarray(detail, np.float64)
        weight = np.asarray(weight, np.float64)
        if detail.shape != weight.shape or detail.ndim != 2:
            raise ValueError("each contribution needs matching [z, x] detail and weight")
        if shape is None:
            shape = detail.shape
            detail_sum = np.zeros(shape, np.float64)
            coverage = np.zeros(shape, np.float64)
        elif detail.shape != shape:
            raise ValueError("contributions must share one shape")
        detail_sum += weight * detail
        coverage += weight
    scaled = detail_sum / np.maximum(coverage, 1e-12) * np.minimum(coverage, 1.)
    return np.where(coverage > 1e-12, scaled, 0.), coverage


def adjacent_step_m(field, spacing_m=FINE_SPACING_M):
    """Largest absolute height step between 4-connected neighbours, in metres."""
    values = np.asarray(field, np.float64)
    if values.ndim != 2 or values.size < 4:
        raise ValueError("at least a 2x2 field required")
    _positive(spacing_m, "spacing_m")
    horizontal = np.abs(np.diff(values, axis=1))
    vertical = np.abs(np.diff(values, axis=0))
    return {"max_m": float(max(horizontal.max(initial=0.), vertical.max(initial=0.))),
            "p99_m": float(np.percentile(np.concatenate([horizontal.ravel(), vertical.ravel()]), 99)),
            "p50_m": float(np.percentile(np.concatenate([horizontal.ravel(), vertical.ravel()]), 50))}


def seam_diagnostics(fine, seam_cells, spacing_m=FINE_SPACING_M):
    """Compare steps across declared seam cells with the field's own step scale.

    `seam_cells` is a boolean [z, x] mask marking cells whose downstream/rightward
    neighbour sits in another window. A seam introduces no step when the steps
    across it stay inside the interior step distribution.
    """
    values = np.asarray(fine, np.float64)
    mask = np.asarray(seam_cells, bool)
    if mask.shape != values.shape:
        raise ValueError("seam mask must match the field")
    inside = adjacent_step_m(values, spacing_m)
    steps = []
    for axis in (0, 1):
        moved = np.roll(values, -1, axis=axis)
        crossed = np.abs(moved - values)
        valid = np.zeros(values.shape, bool)
        if axis == 0:
            valid[:-1, :] = True
        else:
            valid[:, :-1] = True
        steps.append(crossed[valid & mask])
    across = np.concatenate(steps) if steps else np.array([])
    return {"seam_cells": int(mask.sum()), "across_seam_samples": int(across.size),
            "across_seam_max_m": float(across.max()) if across.size else None,
            "across_seam_mean_m": float(across.mean()) if across.size else None,
            "interior": inside}


@dataclass(frozen=True)
class FineTerrainField:
    """One 30 m base page plus the identity of everything that produced it."""

    elevation_m: np.ndarray
    valid_mask: np.ndarray
    origin_xz_m: tuple
    spacing_m: float
    provenance: dict

    def __post_init__(self):
        height = self.elevation_m
        if not isinstance(height, np.ndarray) or height.dtype != np.float64 or height.ndim != 2:
            raise ValueError("float64 [z, x] elevation required")
        valid = self.valid_mask
        if not isinstance(valid, np.ndarray) or valid.dtype != bool or valid.shape != height.shape or not valid.any():
            raise ValueError("nonempty boolean valid mask required")
        if not np.isfinite(height[valid]).all():
            raise ValueError("nonfinite elevation on valid cells")
        spacing = _positive(self.spacing_m, "spacing_m")
        x0, z0 = _origin(self.origin_xz_m)
        if not isinstance(self.provenance, dict) or not self.provenance:
            raise ValueError("provenance record required")
        object.__setattr__(self, "elevation_m", readonly(np.where(valid, height, 0.)))
        object.__setattr__(self, "valid_mask", readonly(valid))
        object.__setattr__(self, "origin_xz_m", (x0, z0))
        object.__setattr__(self, "spacing_m", spacing)

    @property
    def identity_sha256(self):
        return identity({"elevation_m": self.elevation_m, "valid_mask": self.valid_mask},
                        {"origin_xz_m": list(self.origin_xz_m), "spacing_m": self.spacing_m,
                         "provenance": self.provenance})

    def metadata(self):
        return {"origin_xz_m": list(self.origin_xz_m), "spacing_m": self.spacing_m,
                "shape": list(self.elevation_m.shape), "cell_area_m2": self.spacing_m ** 2,
                "coordinates": "cell centres; X east, Z south; arrays [z, x]",
                "identity_sha256": self.identity_sha256, "provenance": self.provenance}

    def save(self, path):
        from pathlib import Path

        target = Path(path)
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata = self.metadata()
        np.savez(target, elevation_m=np.asarray(self.elevation_m, np.float64),
                 valid_mask=np.asarray(self.valid_mask, bool),
                 origin_xz_m=np.array(self.origin_xz_m, np.float64),
                 spacing_m=np.array(self.spacing_m, np.float64),
                 provenance_json=np.array(json.dumps(metadata, sort_keys=True)),
                 identity_sha256=np.array(self.identity_sha256))
        return target

    @classmethod
    def load(cls, path):
        page = np.load(path, allow_pickle=False)
        metadata = json.loads(str(page["provenance_json"]))
        field = cls(np.asarray(page["elevation_m"], np.float64),
                    np.asarray(page["valid_mask"], bool),
                    tuple(np.asarray(page["origin_xz_m"], np.float64).tolist()),
                    float(np.asarray(page["spacing_m"], np.float64)),
                    metadata["provenance"])
        if field.identity_sha256 != str(page["identity_sha256"]):
            raise ValueError("saved fine terrain identity does not recompute")
        return field


def compose_fine_terrain(seed, origin_xz_m, shape, contributions=(), *,
                         spacing_m=FINE_SPACING_M, source_label="analytic_30m"):
    """Analytic 30 m base plus an optional mosaicked TD detail term."""
    base, sampling = analytic_fine_field(seed, origin_xz_m, shape, spacing_m)
    if contributions:
        detail, coverage = mosaic_detail_m(contributions)
        elevation = base + detail
        detail_record = {"windows": len(contributions),
                         "coverage_max": float(coverage.max()),
                         "coverage_min_overlap": float(coverage[coverage > 1e-9].min(initial=0.)),
                         "detail_std_m": float(detail.std()),
                         "detail_min_m": float(detail.min()), "detail_max_m": float(detail.max())}
    else:
        elevation = base.copy()
        detail_record = {"windows": 0, "detail_std_m": 0.0}
    provenance = {"schema": "fine-terrain-base-v1", "source_label": source_label,
                  "world_seed": int(seed), "sampling": sampling,
                  "td_detail": detail_record,
                  "declared_quantities": {
                      "analytic": "sample_physical at 30 m; seed-determined, window-independent",
                      "td_detail": "edge-tapered high-pass band of a TD window, affine-fitted onto the analytic low pass",
                      "composed": "analytic + coverage-weighted sum of td_detail terms"},
                  "not_claimed": ("the TD band is not an observation and its affine conversion is an "
                                  "uncalibrated engineering parameter")}
    return FineTerrainField(elevation, np.ones(elevation.shape, bool), origin_xz_m,
                            spacing_m, provenance)
