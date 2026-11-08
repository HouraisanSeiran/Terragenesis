"""Embed Terrain Diffusion detail into one saved coarse reach window.

Why
---
The cross-region reach runs (`tools/run_full_reach*.py`) solve on the 10 km
coarse world. Their near-field terrain is therefore the **bilinear
interpolation** of a 10 km grid, which looks smooth next to any real landscape.
This tool produces a declared 30 m terrain page for one 15.39 km window that

* carries real Terrain Diffusion (TD) detail for the fine texture,
* keeps the *large scales* equal to the solved coarse field, and
* keeps the canonical carved channel exactly where the solver put it, so the
  river still sits in the valley floor instead of floating over it.

What is generated and what is not
---------------------------------
1. **TD generated** - one native window of the pinned 30 m checkpoint
   (`models/terrain-diffusion-30m`) run through the repository's own
   `diffusion.physical_backend.PhysicalTerrainDiffusionBackend` (which refuses
   to run without CUDA; no guard is bypassed here).
2. **Interpolated** - the coarse 10 km page bilinearly sampled onto the fine
   lattice, and the TD field's long wavelengths, which are **removed** by a
   low pass so that the fine page cannot drift away from the solved world.
3. **Carved** - the canonical carved bed of the saved geometry, re-expressed on
   the fine lattice as a cut depth. Inside the carved footprint the field is
   the solved bed; TD detail is damped to zero there and ramps back in outside
   it, so there is no floating channel and no ridge across the trench.

No random source other than the fixed world seed is used: the TD pipeline seed
is the world seed itself (it drives both the conditioning field and the latent
noise). A derived `td-detail` sub-seed is recorded for provenance, but it is
NOT used, because changing the conditioning seed would change the world the
coarse solve belongs to (verified numerically; see the alignment diagnostics).

Run
---
    python tools/build_td_detail_terrain.py \\
        --run .scratch/cross-region-tributary/full-reach-run-02 \\
        --output .scratch/cross-region-tributary/td-detail-01
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORLD_SEED = 20261020
COARSE_SPACING_M = 10000.0
NATIVE_SPACING_M = 30.0
WINDOW_SCHEMA = "td-detail-window-v1"
FIELD_SCHEMA = "td-detail-field-v1"


def derived_subseed(purpose):
    """Purpose sub-seed, delegated to the repository's single seed rule."""
    from terrain_pipeline.surface_rivers.world_channel_graph import derive_noise_seed

    return derive_noise_seed(WORLD_SEED, purpose)


def grid_axes(origin, spacing, shape):
    return (float(origin[0]) + np.arange(int(shape[1])) * float(spacing),
            float(origin[1]) + np.arange(int(shape[0])) * float(spacing))


def bilinear(values, gx, gz, xs, zs):
    """Bilinear sample of a regular page (edge clamped), as the renderer does."""
    values = np.asarray(values, np.float64)
    X, Z = np.meshgrid(np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    sx = (gx[-1] - gx[0]) / (len(gx) - 1)
    sz = (gz[-1] - gz[0]) / (len(gz) - 1)
    fx = np.clip((X - gx[0]) / sx, 0.0, len(gx) - 1.0 - 1e-9)
    fz = np.clip((Z - gz[0]) / sz, 0.0, len(gz) - 1.0 - 1e-9)
    i0 = np.floor(fx).astype(np.int64)
    j0 = np.floor(fz).astype(np.int64)
    tx = fx - i0
    tz = fz - j0
    i1 = np.minimum(i0 + 1, len(gx) - 1)
    j1 = np.minimum(j0 + 1, len(gz) - 1)
    return (values[j0, i0] * (1.0 - tx) * (1.0 - tz) + values[j0, i1] * tx * (1.0 - tz)
            + values[j1, i0] * (1.0 - tx) * tz + values[j1, i1] * tx * tz)


def smoothstep(values):
    clipped = np.clip(values, 0.0, 1.0)
    return clipped * clipped * (3.0 - 2.0 * clipped)


def array_digest(*arrays):
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# stage 1: real TD window
# --------------------------------------------------------------------------- #
def build_window(output_dir, native_origin, size, seed):
    """Run the pinned TD checkpoint for one native window; save it verbatim."""
    import torch

    from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
    from diffusion.physical_config import PhysicalGenerationConfig

    if size > 513:
        raise ValueError("TD native window limit is 513 cells (15.39 km)")
    if native_origin[0] % 1 or native_origin[1] % 1:
        raise ValueError("native origin must be integer lattice cells")
    config = PhysicalGenerationConfig()
    backend = PhysicalTerrainDiffusionBackend(config)
    started = time.perf_counter()
    try:
        elevation, climate, metadata = backend.generate(int(seed), int(native_origin[0]),
                                                       int(native_origin[1]), int(size))
        peak_mib = float(torch.cuda.max_memory_allocated() / 2 ** 20) if torch.cuda.is_available() else 0.0
    finally:
        backend.close()
    seconds = time.perf_counter() - started
    metadata = dict(metadata, schema=WINDOW_SCHEMA, window_native_origin=list(native_origin),
                    window_size=int(size), world_seed=WORLD_SEED,
                    pixel_origin_m=[float(native_origin[0]) * NATIVE_SPACING_M,
                                    float(native_origin[1]) * NATIVE_SPACING_M],
                    seconds_total=seconds, peak_cuda_mib=peak_mib,
                    torch_version=torch.__version__, cuda_device=torch.cuda.get_device_name(0),
                    positioning="value at native lattice point; metre origin = native origin * 30 m",
                    prompt="conditioning is sample_physical(seed=world_seed); no text prompt is used")
    path = Path(output_dir) / "td-window.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, elevation_m=np.asarray(elevation, np.float64),
             climate=np.asarray(climate, np.float32),
             metadata_json=np.array(json.dumps(metadata, sort_keys=True)))
    print("[window] %s  %s  %.1f s  peak %.0f MiB" % (
        path, np.shape(elevation), seconds, peak_mib), flush=True)
    return path


# --------------------------------------------------------------------------- #
# stage 2: compose the fine field
# --------------------------------------------------------------------------- #
def carved_rasters(geometry, xs, zs):
    """Cut depth and carved-bed rasters of the saved canonical mesh.

    The canonical mesh is a channel ribbon; its convex hull covers the whole
    window, so "outside the mesh" cannot be read off a triangle mask. Outside
    the trench the interpolated cut is zero, which is what is used here.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.tri as mtri

    vertices = np.asarray(geometry["vertices_xz_m"], np.float64)
    triangles = np.asarray(geometry["triangles"], np.int64)
    tri = mtri.Triangulation(vertices[:, 0], vertices[:, 1], triangles)
    X, Z = np.meshgrid(np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    cut = mtri.LinearTriInterpolator(tri, np.asarray(geometry["cut_depth_m"], np.float64))(X, Z)
    bed = mtri.LinearTriInterpolator(tri, np.asarray(geometry["bed_elevation_m"], np.float64))(X, Z)
    return np.maximum(np.ma.filled(cut, 0.0), 0.0), np.ma.filled(bed, np.nan)


def channel_weights(geometry, xs, zs, spacing, guard_m, ramp_m):
    """Distance to the canonical bank line, turned into a detail damping weight.

    The canonical profile is the same envelope `metric_channel_geometry._cut`
    uses: full depth inside the half width, then a linear taper to zero at
    ``half_width + BANK_SLOPE * depth``. ``distance_m`` is measured from that
    outer bank line, so it is 0 at the trench rim and positive outside.
    """
    from terrain_pipeline.channel_geometry import BANK_SLOPE

    node_xz = np.asarray(geometry["node_xz_m"], np.float64)
    receiver = np.asarray(geometry["receiver"], np.int64)
    width = np.asarray(geometry["width_m"], np.float64)
    depth = np.asarray(geometry["depth_m"], np.float64)
    X, Z = np.meshgrid(np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    distance_m = np.full(X.shape, np.inf)
    for donor, target in enumerate(receiver):
        if target < 0:
            continue
        start, end = node_xz[donor], node_xz[int(target)]
        delta = end - start
        squared = float(delta @ delta)
        if squared <= 0.0:
            continue
        fraction = np.clip(((X - start[0]) * delta[0] + (Z - start[1]) * delta[1]) / squared, 0.0, 1.0)
        centre_distance = np.hypot(X - (start[0] + fraction * delta[0]),
                                   Z - (start[1] + fraction * delta[1]))
        half_width = 0.5 * ((1.0 - fraction) * width[donor] + fraction * width[int(target)])
        local_depth = (1.0 - fraction) * depth[donor] + fraction * depth[int(target)]
        distance_m = np.minimum(distance_m, centre_distance - half_width - BANK_SLOPE * local_depth)
    if not np.isfinite(distance_m).any():
        raise ValueError("no channel segment intersects the fine window")
    footprint = distance_m <= 0.0
    if not footprint.any():
        raise ValueError("carved footprint does not intersect the fine window")
    weight = smoothstep((distance_m - guard_m) / max(ramp_m, spacing))
    return footprint, distance_m, weight


def affine_reconcile(td, coarse_fine, spacing, reconcile_sigma_m, detail_sigma_m):
    """Fit the checkpoint's vertical frame onto the solved world's metres.

    The 30 m checkpoint emits elevation in its own normalised vertical units: on
    this window the large scales are an *affine* image of the solved coarse field
    (fit residual ~0 at 20 km), so the TD field is mapped by that fitted line
    before any detail is taken. Nothing about the TD structure is invented; only
    its datum and vertical scale are converted.
    """
    from scipy import ndimage

    sigma_reconcile = reconcile_sigma_m / spacing
    sigma_detail = detail_sigma_m / spacing
    td_low = ndimage.gaussian_filter(td, sigma_reconcile, mode="nearest")
    coarse_low = ndimage.gaussian_filter(coarse_fine, sigma_reconcile, mode="nearest")
    slope, intercept = np.polyfit(td_low.ravel(), coarse_low.ravel(), 1)
    residual = coarse_low - (slope * td_low + intercept)
    finer = ndimage.gaussian_filter(td, sigma_detail, mode="nearest")
    finer_coarse = ndimage.gaussian_filter(coarse_fine, sigma_detail, mode="nearest")
    finer_residual = finer_coarse - (slope * finer + intercept)
    return float(slope), float(intercept), {
        "reconcile_sigma_m": float(reconcile_sigma_m),
        "detail_sigma_m": float(detail_sigma_m),
        "slope": float(slope), "intercept_m": float(intercept),
        "correlation": float(np.corrcoef(td_low.ravel(), coarse_low.ravel())[0, 1]),
        "residual_rms_m": float(residual.std()),
        "residual_max_m": float(np.max(np.abs(residual))),
        "residual_rms_at_detail_sigma_m": float(finer_residual.std()),
        "interpretation": ("TD output is in the checkpoint's normalised vertical units; "
                           "world_m = slope * TD + intercept")}


def lake_consistency(fine, sample, coarse, coarse_origin, run_dir, xs, zs, spacing):
    """Does the injected detail break the declared lake sill / stage relation?

    The lake is a single coarse cell with an explicit sill (lowest of the eight
    neighbour cells). Adding sub-grid detail cannot change that ledger, but it
    can move the *terrain* near the rim, so the relation is measured rather
    than assumed.
    """
    definition_path = Path(run_dir) / "lake-definition.json"
    if not definition_path.exists():
        return {"status": "no_lake_definition"}
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    lake = definition["lake"]
    sill_stage = float(lake["sill_stage_m"])
    initial_stage = float(definition["initial_stage_m"])
    bed = float(lake["bed_elevation_m"][0])

    geometry = np.load(Path(run_dir) / "generated-geometry.npz")
    terminal = int(definition["terminal_node_index"])
    centre = np.asarray(geometry["node_xz_m"], np.float64)[terminal]
    step = COARSE_SPACING_M
    rim = {}
    for dz in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dz == 0:
                continue
            point = centre + np.array([dx * step, dz * step])
            if not (xs[0] <= point[0] <= xs[-1] and zs[0] <= point[1] <= zs[-1]):
                continue
            rim["%+d,%+d" % (dx, dz)] = float(sample(fine, point[0], point[1]))
    square = ((np.abs(zs[:, None] - centre[1]) <= 0.5 * step)
              & (np.abs(xs[None, :] - centre[0]) <= 0.5 * step))
    below_stage = int(np.count_nonzero(fine[square] < initial_stage))
    rim_values = np.array(list(rim.values())) if rim else np.array([])
    return {
        "terminal_centre_xz_m": centre.tolist(),
        "declared_bed_m": bed,
        "declared_sill_stage_m": sill_stage,
        "declared_initial_stage_m": initial_stage,
        "fine_bed_at_centre_m": float(sample(fine, centre[0], centre[1])),
        "fine_rim_m": rim,
        "fine_rim_min_m": float(rim_values.min()) if rim_values.size else None,
        "declared_sill_minus_fine_rim_min_m": (float(sill_stage - rim_values.min())
                                               if rim_values.size else None),
        "sill_still_lowest_of_sampled_rim": bool(rim_values.size == 0 or
                                                 rim_values.min() >= sill_stage - 1e-9),
        "fine_cells_in_lake_cell_below_initial_stage": below_stage,
        "note": ("the inland lake is the modelled single coarse cell; fine cells below the "
                 "stage inside it are not flooded by the saved ledger (two-way backwater "
                 "is outside that model), and the ridge at the sill is a coarse-grid "
                 "construct, so this is reported as a limitation, not fixed here")}


def compose(args):
    run_dir = Path(args.run)
    output_dir = Path(args.output)
    window_path = output_dir / "td-window.npz"
    if not window_path.exists():
        raise SystemExit("missing %s; run --stage window first" % window_path)

    window = np.load(window_path)
    window_meta = json.loads(str(window["metadata_json"]))
    td = np.asarray(window["elevation_m"], np.float64)
    if list(window_meta["window_native_origin"]) != list(args.native_origin):
        raise SystemExit("saved TD window origin does not match --native-origin")

    page = np.load(run_dir / "source-terrain-and-forcing.npz")
    coarse = np.asarray(page["height_m"], np.float64)
    coarse_origin = np.asarray(page["origin_xz_m"], np.float64)
    geometry = np.load(run_dir / "generated-geometry.npz")

    size = td.shape[0]
    spacing = NATIVE_SPACING_M
    origin = np.array(args.native_origin, np.float64) * spacing
    xs = origin[0] + np.arange(size) * spacing
    zs = origin[1] + np.arange(size) * spacing

    gx, gz = grid_axes(coarse_origin, COARSE_SPACING_M, coarse.shape)
    if (xs[0] < gx[0] or xs[-1] > gx[-1] or zs[0] < gz[0] or zs[-1] > gz[-1]):
        raise SystemExit("fine window leaves the coarse page")
    coarse_fine = bilinear(coarse, gx, gz, xs, zs)

    # 1. Reconcile the checkpoint's vertical frame, then take only its detail band.
    from scipy import ndimage

    affine_slope, affine_intercept, affine = affine_reconcile(
        td, coarse_fine, spacing, args.reconcile_sigma_m, args.lowpass_sigma_m)
    td_world = affine_slope * td + affine_intercept
    sigma_cells = args.lowpass_sigma_m / spacing
    low = ndimage.gaussian_filter(td, sigma=sigma_cells, mode="nearest")
    detail = affine_slope * (td - low)
    coarse_low = ndimage.gaussian_filter(coarse_fine, sigma=sigma_cells, mode="nearest")

    # 2. Window edge ramp: the injected detail vanishes at the page border, so the
    #    fine page meets the surrounding coarse field with no step.
    edge_distance = np.minimum.reduce([
        (xs[None, :] - xs[0]) + 0.0 * zs[:, None], (xs[-1] - xs[None, :]) + 0.0 * zs[:, None],
        (zs[:, None] - zs[0]) + 0.0 * xs[None, :], (zs[-1] - zs[:, None]) + 0.0 * xs[None, :]])
    edge_weight = smoothstep(edge_distance / max(args.edge_margin_m, spacing))

    # 3. Channel protection: no detail inside or next to the carved trench.
    cut, carved_bed = carved_rasters(geometry, xs, zs)
    footprint, bank_distance, channel_weight = channel_weights(
        geometry, xs, zs, spacing, args.channel_guard_m, args.channel_ramp_m)
    carved = cut > 1e-3

    weight = edge_weight * channel_weight
    fine = coarse_fine + weight * detail
    fine = fine - cut
    valid = np.ones(fine.shape, bool)

    # ---------------- diagnostics ---------------- #
    neighbours = (np.asarray(geometry["node_xz_m"], np.float64),
                  np.asarray(geometry["receiver"], np.int64),
                  np.asarray(geometry["width_m"], np.float64),
                  np.asarray(geometry["depth_m"], np.float64))

    def sample(field, x, z):
        fi = (np.asarray(x) - xs[0]) / spacing
        fj = (np.asarray(z) - zs[0]) / spacing
        i0 = np.clip(np.floor(fi).astype(int), 0, size - 2)
        j0 = np.clip(np.floor(fj).astype(int), 0, size - 2)
        tx = np.clip(fi - i0, 0, 1)
        tz = np.clip(fj - j0, 0, 1)
        return (field[j0, i0] * (1 - tx) * (1 - tz) + field[j0, i0 + 1] * tx * (1 - tz)
                + field[j0 + 1, i0] * (1 - tx) * tz + field[j0 + 1, i0 + 1] * tx * tz)

    node_xz, receiver, width, depth = neighbours

    def cross_section(face):
        """Per-section flank-minus-centre and ridge flags on one surface."""
        flanks, ridges = [], []
        for donor in range(len(node_xz)):
            target = int(receiver[donor])
            if target < 0:
                continue
            p0, p1 = node_xz[donor], node_xz[target]
            segment = p1 - p0
            length = float(np.linalg.norm(segment))
            if length <= 0:
                continue
            flow = segment / length
            normal = np.array([-flow[1], flow[0]])
            for t in np.linspace(0.0, 1.0, max(int(length / 500.0), 5)):
                centre = p0 + t * segment
                half = 0.5 * (width[donor] * (1 - t) + width[target] * t)
                if not (xs[0] <= centre[0] <= xs[-1] and zs[0] <= centre[1] <= zs[-1]):
                    continue
                centre_h = float(sample(face, centre[0], centre[1]))
                flank = min(float(sample(face, *(centre + d * normal))) for d in
                            (half + 60.0, -(half + 60.0), half + 260.0, -(half + 260.0)))
                flanks.append(flank - centre_h)
                ridges.append(bool(flank <= centre_h + 1e-9))
        return flanks, ridges

    flanks_fine, ridges_fine = cross_section(fine)
    flanks_coarse, ridges_coarse = cross_section(coarse_fine)

    # centreline monotonicity toward the terminal node
    terminal = int(np.flatnonzero(receiver < 0)[0])
    chain = [terminal]
    while True:
        donors_of = np.flatnonzero(receiver == chain[-1])
        if len(donors_of) != 1:
            break
        chain.append(int(donors_of[0]))
    chain = chain[::-1]
    chain_bed = [float(sample(fine, *node_xz[i])) for i in chain]
    inversions = [int(chain[k]) for k in range(len(chain) - 1)
                  if chain_bed[k + 1] > chain_bed[k] + 1e-9]

    # does the injected detail dip below the neighbouring solved stage?
    dynamic = np.load(run_dir / "dynamic-water-sediment-bed.npz")
    frame = int(np.argmax(np.asarray(dynamic["water_volume_m3"], np.float64).sum(axis=1)))
    node_bed = np.asarray(dynamic["node_bed_m"][frame], np.float64)
    node_volume = np.asarray(dynamic["water_volume_m3"][frame], np.float64)
    material_area = np.asarray(dynamic["material_area_m2"], np.float64)
    node_depth = node_volume / material_area
    stage = node_bed + node_depth

    inside = ~carved
    outside_stage = np.full(fine.shape, -np.inf)
    X, Z = np.meshgrid(xs, zs)
    for donor in range(len(node_xz)):
        target = int(receiver[donor])
        if target < 0:
            continue
        p0, p1 = node_xz[donor], node_xz[target]
        segment = p1 - p0
        squared = float(segment @ segment)
        t = np.clip(((X - p0[0]) * segment[0] + (Z - p0[1]) * segment[1]) / squared, 0.0, 1.0)
        distance = np.hypot(X - (p0[0] + t * segment[0]), Z - (p0[1] + t * segment[1]))
        half = 0.5 * (width[donor] * (1 - t) + width[target] * t)
        near = distance <= half * 3.0
        local_stage = stage[donor] * (1 - t) + stage[target] * t
        outside_stage = np.where(near, np.maximum(outside_stage, local_stage), outside_stage)
    pond = inside & np.isfinite(outside_stage) & (fine < outside_stage - 0.05)
    pond_cells = int(np.count_nonzero(pond))
    pond_coarse = int(np.count_nonzero(inside & np.isfinite(outside_stage)
                                      & (coarse_fine < outside_stage - 0.05)))

    border = np.zeros(fine.shape, bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    border_step = float(np.max(np.abs(fine[border] - coarse_fine[border])))
    border_detail_step = float(np.max(np.abs((weight * detail)[border])))

    interior = channel_weight > 0.999
    detail_stats = {
        "affine_reconciliation": affine,
        "injected_detail_std_m": float(np.std(detail[channel_weight > 0.999])),
        "injected_detail_min_m": float(np.min(detail[channel_weight > 0.999])),
        "injected_detail_max_m": float(np.max(detail[channel_weight > 0.999])),
        "lowpass_of_injected_detail_max_m": float(np.max(np.abs(
            ndimage.gaussian_filter(weight * detail, sigma_cells, mode="nearest")))),
        "lowpass_of_injected_detail_rms_m": float(np.std(
            ndimage.gaussian_filter(weight * detail, sigma_cells, mode="nearest"))),
        "world_affine_td_minus_coarse_bias_m": float(np.mean(td_world - coarse_fine)),
        "world_affine_td_minus_coarse_rms_m": float(np.sqrt(np.mean((td_world - coarse_fine) ** 2))),
        "injected_detail_by_bank_distance_m": {
            band: {"cells": int(np.count_nonzero((bank_distance >= low_m) & (bank_distance < high_m))),
                   "std_m": (float(np.std(detail[(bank_distance >= low_m) & (bank_distance < high_m)]))
                             if np.count_nonzero((bank_distance >= low_m) & (bank_distance < high_m)) else None)}
            for band, low_m, high_m in (("0-0.5km", 0.0, 500.0), ("0.5-1.5km", 500.0, 1500.0),
                                        ("1.5-3km", 1500.0, 3000.0), (">3km", 3000.0, 1e9))}
    }

    roughness = {}
    for name, field in (("td_world", td_world), ("coarse_bilinear", coarse_fine), ("composed", fine)):
        dz_dy, dz_dx = np.gradient(field, spacing)
        roughness[name] = {"mean_abs_slope": float(np.mean(np.hypot(dz_dx, dz_dy))),
                           "p99_abs_slope": float(np.percentile(np.hypot(dz_dx, dz_dy), 99))}

    corridor = weight == 0.0
    corridor_bed_error = float(np.max(np.abs(fine[corridor] + cut[corridor] - coarse_fine[corridor])))

    diagnostics = {
        "window": {"native_origin": list(args.native_origin), "size": int(size),
                   "spacing_m": spacing, "origin_m_xz": origin.tolist(),
                   "x_m": [float(xs[0]), float(xs[-1])], "z_m": [float(zs[0]), float(zs[-1])]},
        "alignment": alignment_diagnostics(run_dir, args.seed),
        "parameters": {"lowpass_sigma_m": args.lowpass_sigma_m,
                       "edge_margin_m": args.edge_margin_m,
                       "channel_guard_m": args.channel_guard_m,
                       "channel_ramp_m": args.channel_ramp_m,
                       "cut_max_m": float(np.max(cut)),
                       "carved_footprint_cells": int(np.count_nonzero(footprint)),
                       "detail_damped_cells": int(np.count_nonzero(weight < 0.999)),
                       "detail_full_cells": int(np.count_nonzero(weight > 0.999))},
        "detail": detail_stats,
        "roughness": roughness,
        "channel_checks": {
            "cross_section_samples": len(flanks_fine),
            "flank_above_centre_min_m": float(np.min(flanks_fine)) if flanks_fine else None,
            "ridge_across_channel_samples": int(np.count_nonzero(np.logical_not(ridges_fine))),
            "baseline_coarse_flank_above_centre_min_m": (float(np.min(flanks_coarse))
                                                         if flanks_coarse else None),
            "baseline_coarse_ridge_across_channel_samples": int(np.count_nonzero(
                np.logical_not(ridges_coarse))),
            "baseline_note": ("the 10 km bilinear field has no valley walls of its own, so the "
                              "coarse row is the honest baseline for what the detail added"),
            "trench_corridor_bed_exact_m": corridor_bed_error,
            "trench_corridor_note": ("where the detail weight is zero the page is exactly the "
                                     "solved coarse surface minus the canonical cut"),
            "main_stem_node_chain": chain,
            "main_stem_bed_m": chain_bed,
            "main_stem_inversions": inversions,
            "inversion_note": "empty means the fine centreline still falls monotonically to the terminal lake cell",
            "would_be_pond_cells_outside_trench": pond_cells,
            "would_be_pond_area_m2": float(pond_cells * spacing * spacing),
            "baseline_coarse_would_be_pond_cells": pond_coarse},
        "border_step_m": border_step,
        "border_detail_step_m": border_detail_step,
        "border_note": ("the injected detail is exactly zero on the page border; any nonzero "
                        "border_step_m is the canonical carve of a channel that continues "
                        "beyond the window"),
        "lake_consistency": lake_consistency(fine, sample, coarse, coarse_origin, run_dir,
                                              xs, zs, spacing),
        "reuse": {"source_run": str(run_dir), "td_window": str(window_path),
                  "coarse_page_sha256": array_digest(coarse),
                  "td_window_sha256": array_digest(td)},
    }

    metadata = {"schema": FIELD_SCHEMA,
                "declared_quantities": {
                    "td_generated": ("high-frequency band of the TD window (%.0f m sigma low pass "
                                     "removed, mapped into world metres by the fitted affine line)"
                                     % args.lowpass_sigma_m),
                    "interpolated": ("large scales are the solved coarse field bilinearly sampled "
                                     "at 30 m; the TD band is added on top of it"),
                    "carved": "saved canonical cut depth from generated-geometry.npz applied on the fine lattice"},
                "world_seed": WORLD_SEED, "td_seed": int(args.seed),
                "td_seed_policy": "pipeline seed = world_seed (conditioning + latent); derived td-detail sub-seed recorded but not used",
                "derived_td_detail_subseed": derived_subseed("td-detail"),
                "spacing_m": spacing, "origin_m_xz": origin.tolist(),
                "coordinates": "x east, z south; arrays [z,x]; value at lattice point origin + i*spacing",
                "valid_mask": "1 where the fine field is defined (the whole window)",
                "td_window_metadata": window_meta,
                "diagnostics": diagnostics}
    identity = array_digest(fine, valid, np.array(json.dumps(metadata, sort_keys=True)))

    output_dir.mkdir(parents=True, exist_ok=True)
    field_path = output_dir / "fine-terrain-field.npz"
    np.savez(field_path, height_m=fine, valid_mask=valid, origin_xz_m=origin, spacing_m=spacing,
             carved_mask=carved, detail_weight=weight, cut_depth_m=cut,
             coarse_bilinear_m=coarse_fine, td_window_m=td,
             td_world_m=td_world, detail_m=detail,
             provenance_json=np.array(json.dumps(metadata, sort_keys=True)),
             identity_sha256=np.array(identity))
    (output_dir / "detail-build.json").write_text(
        json.dumps({"identity_sha256": identity, "metadata": metadata},
                   indent=1, sort_keys=True), encoding="utf-8")
    print("[compose] %s  identity %s" % (field_path, identity), flush=True)
    print(json.dumps(diagnostics["channel_checks"], indent=1), flush=True)
    print(json.dumps(diagnostics["detail"], indent=1), flush=True)
    return field_path


def alignment_diagnostics(run_dir, seed):
    """Prove the coarse solve is the field TD is conditioned on."""
    from diffusion.geography_physical import sample_physical

    geometry = np.load(Path(run_dir) / "generated-geometry.npz")
    nodes = np.asarray(geometry["node_xz_m"], np.float64)
    source = np.asarray(geometry["node_source_elevation_m"], np.float64)
    record = {"nodes": int(len(nodes)),
              "rule": "coarse_condition_field -> sample_physical(x,z,world_seed) at the same points"}
    for label, value in (("world_seed", WORLD_SEED), ("td_seed", int(seed))):
        field = sample_physical(nodes[:, 0], nodes[:, 1], int(value))[0].astype(np.float64)
        delta = field - source
        record[label] = {"seed": int(value), "max_abs_m": float(np.max(np.abs(delta))),
                         "rms_m": float(np.sqrt(np.mean(delta ** 2)))}
    record["conditioning_matches_world"] = record["td_seed"]["max_abs_m"] == 0.0
    other = sample_physical(nodes[:, 0], nodes[:, 1], 20261001)[0].astype(np.float64) - source
    record["pinned_source_seed_note"] = (
        "the saved TD products use seed 20261001; at these nodes that field differs by up to "
        "%.2f m (rms %.2f m), so it is a different world and is not reused"
        % (abs(other).max(), float(np.sqrt(np.mean(other ** 2)))))
    return record


def build_shadow_run(run_dir, output_dir, field_path):
    """Stage a render-ready run directory whose terrain page is the fine field.

    `tools/render_remote_sensing.py` reads `source-terrain-and-forcing.npz`
    (`height_m`, `origin_xz_m`) and the spacing from
    `source-selection.json["coarse_terrain_spacing_m"]`. This copies the rest of
    the run untouched and swaps in the fine page, so the existing renderer can
    consume the detail without a single line of renderer change. Because the
    fine page covers one 15.39 km window only, a render of this shadow run has
    to stay inside that window.
    """
    import shutil

    run_dir, output_dir = Path(run_dir), Path(output_dir)
    shadow = output_dir / "fine-run"
    shadow.mkdir(parents=True, exist_ok=True)
    for name in ("generated-geometry.npz", "dynamic-water-sediment-bed.npz",
                 "lake-definition.json", "lake-storage.npz"):
        source = run_dir / name
        if source.exists():
            shutil.copyfile(source, shadow / name)
    field = np.load(field_path)
    page = dict(np.load(run_dir / "source-terrain-and-forcing.npz"))
    page["height_m"] = np.asarray(field["height_m"], np.float64)
    page["origin_xz_m"] = np.asarray(field["origin_xz_m"], np.float64)
    np.savez(shadow / "source-terrain-and-forcing.npz", **page)
    selection = json.loads((run_dir / "source-selection.json").read_text(encoding="utf-8"))
    selection["coarse_terrain_spacing_m"] = float(np.asarray(field["spacing_m"]))
    selection["terrain_override"] = {
        "fine_terrain_field": str(Path(field_path)),
        "identity_sha256": str(np.asarray(field["identity_sha256"])),
        "note": "shadow run for review rendering only; the solver input was the 10 km page"}
    (shadow / "source-selection.json").write_text(json.dumps(selection, indent=1), encoding="utf-8")
    print("[shadow] %s" % shadow, flush=True)
    return shadow


def figures(field_path, output_dir):
    """Declared review figures: the three terrain sources side by side."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    field = np.load(field_path)
    fine = np.asarray(field["height_m"], np.float64)
    coarse = np.asarray(field["coarse_bilinear_m"], np.float64)
    td = np.asarray(field["td_window_m"], np.float64)
    td_world = np.asarray(field["td_world_m"], np.float64)
    origin = np.asarray(field["origin_xz_m"], np.float64)
    spacing = float(np.asarray(field["spacing_m"]))
    extent = [origin[0] / 1000.0, (origin[0] + (fine.shape[1] - 1) * spacing) / 1000.0,
              (origin[1] + (fine.shape[0] - 1) * spacing) / 1000.0, origin[1] / 1000.0]
    light = LightSource(azdeg=315.0, altdeg=45.0)

    fig, axes = plt.subplots(1, 3, figsize=(21.0, 7.2), facecolor="#0d1117")
    panels = (("10 km 粗网双线性插值（原求解面）", coarse, "gray"),
              ("TD 生成 30 m 场（已换算到本世界高程）", td_world, "gray"),
              ("合成本页：TD 细部 + 求解粗面 + canonical 切槽", fine, "terrain"))
    for ax, (title, canvas, colourmap) in zip(axes, panels):
        shade = light.hillshade(canvas, vert_exag=3.0, dx=spacing, dy=spacing)
        ax.imshow(shade, extent=extent, origin="upper", cmap=colourmap, interpolation="nearest")
        ax.set_title(title, color="#e6edf3", fontsize=12, pad=7)
        ax.set_xlabel("世界坐标 X (km)", color="#9fb0c0", fontsize=9)
        ax.set_ylabel("世界坐标 Z (km)", color="#9fb0c0", fontsize=9)
        ax.tick_params(labelsize=7, colors="#9fb0c0")
        ax.set_facecolor("#0d1117")
    fig.suptitle("细地形来源对比 · world_seed=20261020 · 513 窗 15.39 km · 光照为声明式绘图光",
                 color="#e6edf3", fontsize=13, y=0.98)
    path = Path(output_dir) / "detail-source-comparison.png"
    fig.savefig(path, dpi=170, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print("[figures] %s" % path, flush=True)

    difference = fine - coarse
    fig, ax = plt.subplots(figsize=(9.6, 8.0), facecolor="#0d1117")
    limit = float(np.percentile(np.abs(difference), 99.5)) or 1.0
    image = ax.imshow(difference, extent=extent, origin="upper", cmap="RdBu_r",
                      vmin=-limit, vmax=limit, interpolation="nearest")
    ax.set_title("合成页 − 粗面插值（m）\n切槽处为挖深，河道两侧细部归零", color="#e6edf3", fontsize=12)
    ax.set_xlabel("世界坐标 X (km)", color="#9fb0c0", fontsize=9)
    ax.set_ylabel("世界坐标 Z (km)", color="#9fb0c0", fontsize=9)
    ax.tick_params(axis="y", labelsize=7, colors="#9fb0c0")
    ax.tick_params(labelsize=7, colors="#9fb0c0")
    ax.set_facecolor("#0d1117")
    bar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    bar.ax.tick_params(labelsize=7, colors="#9fb0c0")
    path = Path(output_dir) / "detail-difference.png"
    fig.savefig(path, dpi=170, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print("[figures] %s" % path, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Embed TD detail into one saved coarse reach window")
    parser.add_argument("--run", required=True, help="cross-region run directory")
    parser.add_argument("--output", required=True, help="output directory (new or existing)")
    parser.add_argument("--native-origin", nargs=2, type=int, default=[43077, 42560],
                        help="integer native lattice origin (x z) of the TD window")
    parser.add_argument("--size", type=int, default=513, help="TD window size in native cells (<=513)")
    parser.add_argument("--seed", type=int, default=WORLD_SEED, help="TD pipeline seed (must equal world seed)")
    parser.add_argument("--lowpass-sigma-m", type=float, default=3000.0)
    parser.add_argument("--reconcile-sigma-m", type=float, default=20000.0,
                        help="low pass the TD -> world affine map is fitted on")
    parser.add_argument("--edge-margin-m", type=float, default=1500.0)
    parser.add_argument("--channel-guard-m", type=float, default=300.0,
                        help="distance outside the carved bank line where detail stays exactly zero")
    parser.add_argument("--channel-ramp-m", type=float, default=2000.0,
                        help="width of the smooth ramp from zero back to full TD detail")
    parser.add_argument("--stage", choices=("window", "compose", "shadow", "figures", "compose-all", "all"),
                        default="all")
    parser.add_argument("--reuse-window", action="store_true",
                        help="keep an existing td-window.npz during --stage all")
    args = parser.parse_args(argv)
    if int(args.seed) != WORLD_SEED:
        raise SystemExit("TD seed must equal world_seed=%d so the conditioning stays the same world" % WORLD_SEED)

    if args.stage in ("window", "all"):
        if not (args.reuse_window and (Path(args.output) / "td-window.npz").exists()):
            build_window(args.output, args.native_origin, args.size, args.seed)
    if args.stage in ("compose", "compose-all", "all"):
        field_path = compose(args)
        if args.stage in ("compose-all", "all"):
            build_shadow_run(args.run, args.output, field_path)
            figures(field_path, args.output)
    if args.stage == "shadow":
        build_shadow_run(args.run, args.output, Path(args.output) / "fine-terrain-field.npz")
    if args.stage == "figures":
        figures(Path(args.output) / "fine-terrain-field.npz", args.output)


if __name__ == "__main__":
    main()
