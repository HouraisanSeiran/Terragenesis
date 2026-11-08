import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.interpolate import CubicSpline


def sculpt_wetland_platform(
    base_bed_m,
    x_m,
    z_m,
    mouth_xz_m,
    *,
    seed=84708600,
    platform_height_m=-0.10,
    platform_noise_large_m=1.35,
    platform_noise_small_m=0.35,
    shore_width_m=850.0,
    corridor_depth_m=-1.05,
):
    """Sculpt a stylized estuarine wetland platform on top of a base bed.

    The platform is an elliptical, lobed footprint centred near the sea mouth.
    Inside the platform the target bed elevation is built from:

      * a near-constant platform elevation (``platform_height_m``),
      * signed, bounded multi-scale noise (``platform_noise_large_m`` and
        ``platform_noise_small_m``) that produces dry banks (above stage)
        and shallow wet lows (below stage) without any hard threshold,
      * a broad seaward bay ramp between u = 2400 m and u = 3400 m so the
        platform blends into the existing shallow branch/sea region rather
        than ending abruptly,
      * three wide, gently-winding corridors lowered to
        ``corridor_depth_m`` to guarantee connected shallow-water paths
        from the platform interior to the downstream branch/sea ends.

    All parameters are recorded in the scene metadata so the diagnostic
    script can read them back without reconstructing anything.
    """
    base = np.asarray(base_bed_m, dtype=float)
    x = np.asarray(x_m, dtype=float)
    z = np.asarray(z_m, dtype=float)

    if base.ndim != 2:
        raise ValueError(f"base must be 2D, got ndim={base.ndim}")
    if base.shape != x.shape or base.shape != z.shape:
        raise ValueError(
            f"base, x, z shapes must match exactly; got base={base.shape}, "
            f"x={x.shape}, z={z.shape}"
        )
    if not (np.all(np.isfinite(base)) and np.all(np.isfinite(x)) and np.all(np.isfinite(z))):
        raise ValueError("base/x/z contain non-finite values")

    # ---- Elliptical, lobed footprint -----------------------------------
    # Axes: u increases seaward (toward the river mouth / branch tips),
    # v is the cross-shore coordinate. mouth_xz_m marks the platform origin.
    ex, ez = 0.7071067811865476, 0.7071067811865476
    nx, nz = -0.7071067811865476, 0.7071067811865476
    dx = x - float(mouth_xz_m[0])
    dz = z - float(mouth_xz_m[1])
    u = dx * ex + dz * ez
    v = dx * nx + dz * nz

    rho = np.sqrt(((u - 1200.0) / 2300.0) ** 2 + (v / 2100.0) ** 2)
    ang = np.arctan2(v / 2100.0, (u - 1200.0) / 2300.0)
    lobe = (
        0.86
        + 0.14 * np.sin(3.0 * ang + 0.7)
        + 0.05 * np.sin(7.0 * ang - 1.3)
    )
    rho_l = rho / np.maximum(lobe, 0.55)

    # Smooth radial ramp: weight == 1 inside the platform, fading to 0 over
    # a band of width ``shore_width_m`` at the platform rim. This is the ONLY
    # blend factor; no additional shore-face suppression is applied, so the
    # platform interior never has its relief collapsed to zero.
    t_plat = np.clip((1.0 - rho_l) / (shore_width_m / 2300.0), 0.0, 1.0)
    weight = t_plat * t_plat * (3.0 - 2.0 * t_plat)

    # ---- Bounded multi-scale signed noise ------------------------------
    # We sample a single iid Gaussian field at the grid resolution, smooth it
    # at two scales (large sigma=12 cells, small sigma=4 cells), then map each
    # smoothed field to a signed quantity via mean/std normalisation followed
    # by a bounded tanh compression:
    #
    #   s = tanh( (f - mean(f)) / (2 * std(f)) )                in (-1, 1)
    #
    # The tanh is the "soft compression" that guarantees no unbounded tails;
    # amplitude is then controlled explicitly by platform_noise_large_m and
    # platform_noise_small_m, so the declared parameters are used DIRECTLY
    # and produce the reported relief statistics rather than being scaled by
    # hidden factors. The combined signed relief
    #
    #   relief = large_amp * s_large + small_amp * s_small
    #
    # is centred at 0 and typically spans roughly +-1.7 m, so with a
    # platform_height_m near the stage we obtain ~30-60% interior water
    # without any hard threshold: lows cross below stage, highs rise above.
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(base.shape)

    large = gaussian_filter(noise, sigma=12.0)
    small = gaussian_filter(noise, sigma=4.0)

    def _signed(field):
        mu = float(field.mean())
        sd = float(field.std())
        if sd <= 0.0:
            return np.zeros_like(field)
        return np.tanh((field - mu) / (2.0 * sd))

    large_signed = _signed(large)
    small_signed = _signed(small)

    relief = (
        float(platform_noise_large_m) * large_signed
        + float(platform_noise_small_m) * small_signed
    )

    target = float(platform_height_m) + relief

    # ---- Shallow seaward bay ramp (restored from v1) -------------------
    # Between u = 2400 m and u = 3400 m the platform target is smoothly
    # blended toward the original shallow bay profile so the wetland surface
    # drains naturally into the existing branch / sea bathymetry instead of
    # ending at a hard platform edge.
    bay_t = np.clip((u - 2400.0) / (3400.0 - 2400.0), 0.0, 1.0)
    bay_s = bay_t * bay_t * (3.0 - 2.0 * bay_t)  # smoothstep
    bay_target = -1.2 - 0.0004 * np.clip(u - 2400.0, 0.0, None)
    target = (1.0 - bay_s) * target + bay_s * bay_target

    # ---- Broad wetland corridors ---------------------------------------
    # Three wide, gently-winding shallow lows that start inside the platform
    # interior and sweep toward the seaward (downstream) end. The corridor
    # mask is NOT multiplied by ``weight`` so that the corridors remain
    # continuous through the platform rim and connect to the branch/sea
    # region instead of being truncated at the footprint edge.
    corr1_v = 900.0 + 420.0 * np.sin((u - 1200.0) / 520.0)
    corr1_u = np.exp(-((u - 1500.0) / 900.0) ** 2)
    corr1 = np.exp(-((v - corr1_v) / 520.0) ** 2) * corr1_u

    corr2_v = -700.0 + 380.0 * np.cos((u - 900.0) / 560.0)
    corr2_u = np.exp(-((u - 1300.0) / 950.0) ** 2)
    corr2 = np.exp(-((v - corr2_v) / 500.0) ** 2) * corr2_u

    corr3_v = 0.0 + 650.0 * np.sin((u - 600.0) / 700.0 + 0.9)
    corr3_u = np.exp(-((u - 900.0) / 800.0) ** 2)
    corr3 = np.exp(-((v - corr3_v) / 560.0) ** 2) * corr3_u

    corridors = np.maximum(corr1, np.maximum(corr2, corr3))

    # Lower the bed toward corridor_depth_m where corridors are strongest:
    # target = (1 - k) * target + k * min(target, corridor_depth_m)
    # so the corridor never raises the bed, only deepens it toward the
    # declared corridor depth. Corridors are applied AFTER the bay blend so
    # that they also cut through the ramp and reach the sea connection.
    k = np.clip(corridors, 0.0, 1.0)
    corridor_bed = np.minimum(target, float(corridor_depth_m))
    target = (1.0 - k) * target + k * corridor_bed

    # ---- Composite with base bed ---------------------------------------
    platform = base * (1.0 - weight) + target * weight

    return {
        "platform_bed_m": platform,
        "platform_weight": weight,
        "wetland_u_m": u,
        "wetland_v_m": v,
        "design_platform_target_m": target,
    }


def design_branch_paths(mouth_xz_m):
    u_a = np.array([0.0, 600.0, 1400.0, 2300.0, 3400.0])
    v0 = np.array([0.0, -300.0, -700.0, -1200.0, -1600.0])
    v1 = np.array([0.0, 220.0, -180.0, 200.0, 0.0])
    v2 = np.array([0.0, 450.0, 900.0, 1100.0, 1500.0])

    u = np.linspace(0.0, 3400.0, 681)
    e = np.array([0.7071067811865476, 0.7071067811865476])
    n = np.array([-0.7071067811865476, 0.7071067811865476])
    mouth = np.asarray(mouth_xz_m, dtype=float).reshape(2)

    paths = []
    for v in (v0, v1, v2):
        v_s = CubicSpline(u_a, v)(u)
        pts = mouth[None, :] + u[:, None] * e[None, :] + v_s[:, None] * n[None, :]
        paths.append(pts.astype(float))
    return paths[0], paths[1], paths[2]


import numpy as np
from scipy.spatial import cKDTree
from terrain_pipeline.channel_geometry import channel_section_cut


def apply_designed_section(bed_m, origin_xz_m, spacing_m, path_xz_m, profile_bed_m, profile_stage_m, width_m, *, allow_fill=False):
    bed_m = np.asarray(bed_m, dtype=float)
    origin_xz_m = np.asarray(origin_xz_m, dtype=float)
    spacing_m = float(spacing_m)
    path_xz_m = np.asarray(path_xz_m, dtype=float)
    profile_bed_m = np.asarray(profile_bed_m, dtype=float)
    profile_stage_m = np.asarray(profile_stage_m, dtype=float)
    width_m = float(width_m)

    if bed_m.ndim != 2:
        raise ValueError("bed_m must be 2D")
    if not np.isfinite(bed_m).all():
        raise ValueError("bed_m must be finite")
    if origin_xz_m.shape != (2,):
        raise ValueError("origin_xz_m must have length 2")
    if not np.isfinite(origin_xz_m).all():
        raise ValueError("origin_xz_m must be finite")
    if not (np.isfinite(spacing_m) and spacing_m > 0.0):
        raise ValueError("spacing_m must be positive and finite")
    if path_xz_m.ndim != 2 or path_xz_m.shape[1] != 2 or path_xz_m.shape[0] < 2:
        raise ValueError("path_xz_m must be Nx2 with N>=2")
    if not np.isfinite(path_xz_m).all():
        raise ValueError("path_xz_m must be finite")
    n = path_xz_m.shape[0]
    if profile_bed_m.shape != (n,) or profile_stage_m.shape != (n,):
        raise ValueError("profile lengths must match path")
    if not np.isfinite(profile_bed_m).all():
        raise ValueError("profile_bed_m must be finite")
    if not np.isfinite(profile_stage_m).all():
        raise ValueError("profile_stage_m must be finite")
    if not (np.isfinite(width_m) and width_m > 0.0):
        raise ValueError("width_m must be positive and finite")

    ny, nx = bed_m.shape
    ii, jj = np.meshgrid(np.arange(nx), np.arange(ny), indexing="xy")
    world_x = origin_xz_m[0] + ii * spacing_m
    world_z = origin_xz_m[1] + jj * spacing_m
    points = np.column_stack((world_x.ravel(), world_z.ravel()))

    tree = cKDTree(path_xz_m)
    distance, nearest = tree.query(points, workers=1)
    distance = distance.reshape(ny, nx)
    nearest = nearest.reshape(ny, nx)

    weight = channel_section_cut(distance, width_m, 1.0, bottom_width_fraction=0.6)
    weight = np.asarray(weight, dtype=float)

    nearest_bed = profile_bed_m[nearest]
    nearest_stage = profile_stage_m[nearest]

    proposal = (1.0 - weight) * bed_m + weight * nearest_bed

    if allow_fill:
        final_bed = proposal
    else:
        final_bed = np.minimum(bed_m, proposal)

    stage = np.where(weight > 0.0, nearest_stage, 0.0)

    return {
        "bed_m": final_bed,
        "section_mask": weight > 0.0,
        "section_core_mask": weight >= 0.9,
        "stage_m": stage,
        "section_weight": weight,
        "nearest_profile_bed_m": nearest_bed,
    }


import numpy as np
from scipy.ndimage import label, generate_binary_structure

def connected_design_water(bed_m, designed_stage_m, channel_mask, source_cell):
    bed_m = np.asarray(bed_m, dtype=float)
    designed_stage_m = np.asarray(designed_stage_m, dtype=float)
    channel_mask = np.asarray(channel_mask, dtype=bool)

    if bed_m.ndim != 2:
        raise ValueError("bed_m must be 2D")
    if designed_stage_m.shape != bed_m.shape:
        raise ValueError("designed_stage_m shape must match bed_m")
    if channel_mask.shape != bed_m.shape:
        raise ValueError("channel_mask shape must match bed_m")
    if not np.all(np.isfinite(bed_m)):
        raise ValueError("bed_m must be finite")
    if not np.all(np.isfinite(designed_stage_m)):
        raise ValueError("designed_stage_m must be finite")
    if np.any(designed_stage_m < 0):
        raise ValueError("designed_stage_m must be everywhere >= 0")
    if not (isinstance(source_cell, (tuple, list)) and len(source_cell) == 2):
        raise ValueError("source_cell must be (row, col)")
    r, c = int(source_cell[0]), int(source_cell[1])
    if r < 0 or r >= bed_m.shape[0] or c < 0 or c >= bed_m.shape[1]:
        raise ValueError("source_cell out of bounds")

    candidate_depth = np.maximum(designed_stage_m - bed_m, 0.0)
    candidate_wet = (candidate_depth > 1e-5) & ((bed_m < 0.0) | channel_mask)

    structure = generate_binary_structure(2, 1)
    labels, nlab = label(candidate_wet, structure=structure)

    sea_condition = candidate_wet & (bed_m < 0.0) & (np.abs(designed_stage_m) <= 1e-10)

    perimeter = np.zeros_like(candidate_wet, dtype=bool)
    perimeter[0, :] = True
    perimeter[-1, :] = True
    perimeter[:, 0] = True
    perimeter[:, -1] = True

    sea_seed_mask = sea_condition & perimeter

    seed_labels = np.unique(labels[sea_seed_mask])
    seed_labels = seed_labels[seed_labels > 0]

    if seed_labels.size == 0:
        raise ValueError("no valid sea seed labels found")

    connected = np.isin(labels, seed_labels)

    if not connected[r, c]:
        raise ValueError("source_cell does not reach the sea")

    water_depth_m = np.where(connected, candidate_depth, 0.0)
    water_surface_m = np.where(connected, designed_stage_m, bed_m)
    wet_mask = water_depth_m > 1e-5
    connected_ocean_mask = connected & (bed_m < 0.0) & (np.abs(designed_stage_m) <= 1e-10)

    return {
        "water_depth_m": water_depth_m,
        "water_surface_m": water_surface_m,
        "wet_mask": wet_mask,
        "connected_ocean_mask": connected_ocean_mask,
        "sea_seed_mask": sea_seed_mask,
    }


import numpy as np

def generate_stylized_wetland(base_bed_m, origin_xz_m, spacing_m, incoming_path_xz_m, incoming_bed_m, mouth_xz_m, incoming_q_m3_s, *, seed=84708600, landward_plain=False):
    if landward_plain:
        return _generate_landward_plain(base_bed_m, origin_xz_m, spacing_m, incoming_path_xz_m,
                                        incoming_bed_m, mouth_xz_m, incoming_q_m3_s, seed=seed)
    base = np.asarray(base_bed_m, dtype=float)
    origin = np.asarray(origin_xz_m, dtype=float)
    spacing = float(spacing_m)
    ipath = np.asarray(incoming_path_xz_m, dtype=float)
    ibed = np.asarray(incoming_bed_m, dtype=float)
    mouth = np.asarray(mouth_xz_m, dtype=float)
    q_in = np.asarray(incoming_q_m3_s, dtype=float)

    nrows, ncols = base.shape
    xgrid, zgrid = np.meshgrid(origin[0] + np.arange(ncols)*spacing,
                               origin[1] + np.arange(nrows)*spacing)

    platform = sculpt_wetland_platform(base, xgrid, zgrid, mouth, seed=seed)
    bed = np.asarray(platform["platform_bed_m"], dtype=float)
    platform_weight = np.asarray(platform["platform_weight"], dtype=float)
    wetland_u_m = np.asarray(platform["wetland_u_m"], dtype=float)
    wetland_v_m = np.asarray(platform["wetland_v_m"], dtype=float)

    inc_profile = ibed
    inc_stage = np.maximum(ibed + 3., 0.)

    inc_res = apply_designed_section(bed, origin, spacing, ipath, inc_profile,
                                     inc_stage, 100.0, allow_fill=True)
    bed = np.asarray(inc_res["bed_m"], dtype=float)
    main_section_mask = np.asarray(inc_res["section_mask"], dtype=bool)
    main_core_mask = np.asarray(inc_res["section_core_mask"], dtype=bool)
    design_stage_m = inc_res["stage_m"].copy()

    branch_paths = design_branch_paths(mouth)
    branch_widths = np.array([80.0, 80.0, 60.0], dtype=float)
    branch_shares = np.array([0.5, 0.3, 0.2], dtype=float)
    n_branch = len(branch_paths)

    branch_section_masks = np.zeros((n_branch,) + bed.shape, dtype=bool)
    branch_core_masks = np.zeros((n_branch,) + bed.shape, dtype=bool)
    branch_cut_depth_m = np.zeros((n_branch,) + bed.shape, dtype=float)

    for bi in range(n_branch):
        path = np.asarray(branch_paths[bi], dtype=float)
        if path.ndim != 2:
            path = np.atleast_2d(path)
        npts = 681
        if path.shape[0] != npts:
            t_old = np.linspace(0.0, 1.0, path.shape[0])
            t_new = np.linspace(0.0, 1.0, npts)
            path = np.column_stack([np.interp(t_new, t_old, path[:, 0]),
                                    np.interp(t_new, t_old, path[:, 1])])
        u = np.linspace(0.0, 3400.0, path.shape[0])
        profile = -2.2 - 0.0002 * u

        before = bed.copy()
        res = apply_designed_section(bed, origin, spacing, path, profile,
                                     np.zeros(path.shape[0]), float(branch_widths[bi]), allow_fill=False)
        bed = np.asarray(res["bed_m"], dtype=float)
        sec = np.asarray(res["section_mask"], dtype=bool)
        core = np.asarray(res["section_core_mask"], dtype=bool)
        branch_section_masks[bi] = sec
        branch_core_masks[bi] = core
        branch_cut_depth_m[bi] = np.maximum(before - bed, 0.0)
        design_stage_m = np.maximum(design_stage_m, res["stage_m"])

    channel_mask = main_section_mask.copy()
    for bi in range(n_branch):
        channel_mask = channel_mask | branch_section_masks[bi]

    first_world = np.asarray(ipath, dtype=float)[0]
    col = int(np.rint((first_world[0] - origin[0]) / spacing))
    row = int(np.rint((first_world[1] - origin[1]) / spacing))
    row = int(np.clip(row, 0, nrows - 1))
    col = int(np.clip(col, 0, ncols - 1))

    water = connected_design_water(bed, design_stage_m, channel_mask, (row, col))
    wet_mask = np.asarray(water["wet_mask"], dtype=bool)
    water_depth_m = np.asarray(water["water_depth_m"], dtype=float)

    branch_actual = np.zeros((n_branch,) + bed.shape, dtype=bool)
    for bi in range(n_branch):
        branch_actual[bi] = branch_core_masks[bi] & wet_mask & (water_depth_m > 0.1)

    for bi, path in enumerate(branch_paths):
        lab, _ = label(branch_actual[bi], structure=generate_binary_structure(2, 1))
        cells = np.rint((path - origin) / spacing).astype(int)
        nz, nx = lab.shape
        if np.any(cells[:, 0] < 0) or np.any(cells[:, 0] >= nx) or np.any(cells[:, 1] < 0) or np.any(cells[:, 1] >= nz):
            raise ValueError("branch path sample out of bounds")
        ids = lab[cells[:, 1], cells[:, 0]]
        if ids[0] <= 0 or not np.all(ids == ids[0]):
            raise ValueError("actual positive-depth branch core is not internally D4 continuous")
    u_slice = (wetland_u_m >= 700.0) & (wetland_u_m <= 2300.0)
    branch_cut_wet_cell_counts = []
    for bi in range(n_branch):
        cnt = int(np.sum(branch_actual[bi] & (branch_cut_depth_m[bi] > 0.05) & u_slice))
        branch_cut_wet_cell_counts.append(cnt)
    branch_cut_wet_cell_counts = np.asarray(branch_cut_wet_cell_counts, dtype=int)
    if np.any(branch_cut_wet_cell_counts < 20):
        raise ValueError("insufficient actual carved wet branch cells")

    slab_half = spacing * 0.75
    branch_transects = []
    for uval in (1400.0, 2300.0):
        slab = np.abs(wetland_u_m - uval) <= slab_half
        vm_list = []
        cnt_list = []
        masks_list = []
        for bi in range(n_branch):
            sel = branch_actual[bi] & slab
            cnt = int(np.sum(sel))
            if cnt == 0:
                raise ValueError("no actual carved wet branch cells in slab")
            vvals = wetland_v_m[sel]
            vm_list.append(float(np.median(vvals)))
            cnt_list.append(cnt)
            masks_list.append(sel)
        for i in range(n_branch):
            for j in range(i + 1, n_branch):
                if abs(vm_list[i] - vm_list[j]) < 3 * spacing:
                    raise ValueError("pairwise branch median separation < 3*spacing")
                if np.any(masks_list[i] & masks_list[j]):
                    raise ValueError("branch actual masks overlap")
        branch_transects.append({
            "u_m": float(uval),
            "v_medians_m": vm_list,
            "wet_counts": cnt_list,
        })

    delta = bed - base
    cell_area = spacing * spacing
    neg = np.maximum(-delta, 0.0)
    pos = np.maximum(delta, 0.0)
    cut_bulk_m3 = float(np.sum(neg) * cell_area)
    fill_bulk_m3 = float(np.sum(pos) * cell_area)
    net_bulk_m3 = float(np.sum(delta) * cell_area)
    material_account_residual_m3 = float(fill_bulk_m3 - cut_bulk_m3 - net_bulk_m3)

    branch_q = q_in.reshape(-1, 1) * branch_shares.reshape(1, -1) if q_in.size else np.zeros((1, n_branch))

    arrays = {
        "base_bed_m": base,
        "bed_m": bed,
        "design_stage_m": design_stage_m,
        "channel_mask": channel_mask,
        "main_section_mask": main_section_mask,
        "branch_section_masks": branch_section_masks,
        "branch_core_masks": branch_core_masks,
        "branch_cut_depth_m": branch_cut_depth_m,
        "platform_weight": platform_weight,
        "wetland_u_m": wetland_u_m,
        "wetland_v_m": wetland_v_m,
        "old_incoming_path_xz_m": ipath,
        "old_incoming_bed_m": ibed,
        "incoming_q_m3_s": q_in,
        "branch_q_m3_s": branch_q,
        "branch_width_m": branch_widths,
        "branch_share": branch_shares,
        "branch_paths_xz_m": np.stack(branch_paths),
    }
    arrays.update(water)

    audit = {
        "source_connected": True,
        "branch_cut_wet_cell_counts": branch_cut_wet_cell_counts.tolist(),
        "branch_transects": branch_transects,
        "cut_bulk_m3": cut_bulk_m3,
        "fill_bulk_m3": fill_bulk_m3,
        "net_bulk_m3": net_bulk_m3,
        "material_account_residual_m3": material_account_residual_m3,
    }

    metadata = {
        "algorithm": "stylized-river-mouth-wetland-v2",
        "construction": "procedural platform/declared branches and static stage",
        "seed": int(seed),
        "platform_parameters": {
            "height": -0.10,
            "noise_amplitudes_m": [1.35, 0.35],
            "gaussian_sigma_cells": [12, 4],
            "signed_noise": "tanh((f - mean) / (2 * std))",
            "shoreline_ellipse": {"center_u": 1200, "radii": [2300, 2100]},
            "lobe": {"base": 0.86, "amp": 0.14, "harmonic": 3, "phase": 0.7, "amp2": 0.05, "harmonic2": 7, "phase2": -1.3, "clamp": 0.55},
            "transition": 850,
            "bay": {"u_range": [2400, 3400], "height": -1.2, "slope": -0.0004},
            "corridor_depth": -1.05,
            "corridor_max_gaussians": [
                {"v": "900 + 420 * sin((u - 1200) / 520)", "envelope_center": 1500, "envelope_scale": 900, "cross_scale": 520},
                {"v": "-700 + 380 * cos((u - 900) / 560)", "envelope_center": 1300, "envelope_scale": 950, "cross_scale": 500},
                {"v": "650 * sin((u - 600) / 700 + 0.9)", "envelope_center": 900, "envelope_scale": 800, "cross_scale": 560}
            ]
        },
        "incoming_width_m": 100.0,
        "branch_width_m": branch_widths.tolist(),
        "branch_shares": branch_shares.tolist(),
        "coordinates": "X east Z south",
    }

    return {"arrays": arrays, "audit": audit, "metadata": metadata}


def _river_fan_fields(base, x, z, incoming_path, mouth, *, seed,
                      nominal_radius_m=5800., curved_side_half_width_m=3200.):
    """A shallow irregular cone aligned to the saved near-junction tangent."""
    base = np.asarray(base, dtype=float)
    x = np.asarray(x, dtype=float)
    z = np.asarray(z, dtype=float)
    incoming_path = np.asarray(incoming_path, dtype=float)
    mouth = np.asarray(mouth, dtype=float).reshape(-1)
    if base.ndim != 2 or x.shape != base.shape or z.shape != base.shape:
        raise ValueError("base, x and z must be matching 2D arrays")
    if incoming_path.ndim != 2 or incoming_path.shape[1] != 2 or incoming_path.shape[0] < 3:
        raise ValueError("incoming_path must contain at least three XZ points")
    if mouth.shape != (2,) or not np.isfinite(mouth).all():
        raise ValueError("mouth must be a finite XZ point")
    if not (np.isfinite(base).all() and np.isfinite(x).all() and np.isfinite(z).all()
            and np.isfinite(incoming_path).all()):
        raise ValueError("fan inputs must be finite")
    distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(incoming_path, axis=0), axis=1))]
    if distance[-1] <= 0. or np.any(np.diff(distance) <= 0.):
        raise ValueError("incoming_path must be strictly progressing")
    junction_distance = distance[-1]-1800.
    if junction_distance <= 250. or junction_distance+250. >= distance[-1]:
        raise ValueError("incoming_path must leave room for junction tangent sampling")
    before = np.array([np.interp(junction_distance-250., distance, incoming_path[:, axis]) for axis in range(2)])
    after = np.array([np.interp(junction_distance+250., distance, incoming_path[:, axis]) for axis in range(2)])
    apex = np.array([np.interp(junction_distance, distance, incoming_path[:, axis]) for axis in range(2)])
    direction = after-before
    direction_norm = np.linalg.norm(direction)
    if not np.isfinite(direction_norm) or direction_norm <= 0.:
        raise ValueError("incoming_path tangent is degenerate")
    direction /= direction_norm
    lateral = np.array([-direction[1], direction[0]])
    dx, dz = x-mouth[0], z-mouth[1]
    u = dx*direction[0]+dz*direction[1]
    v = dx*lateral[0]+dz*lateral[1]
    apex_u = float((apex-mouth) @ direction)
    apex_v = float((apex-mouth) @ lateral)
    forward, cross = u-apex_u, v-apex_v
    radius = np.hypot(forward, cross)
    angle = np.arctan2(cross, forward)
    angle = np.where(radius < 1e-8, 0., angle)
    def smooth(t):
        t = np.clip(t, 0., 1.)
        return t*t*(3.-2.*t)
    # Direction-aligned correlated relief is defined in local metric coordinates,
    # so rotating the incoming river and scene preserves the generated shape.
    phase = (int(seed) % 997) / 997. * 2. * np.pi
    coarse = (np.sin(forward/1150. + .73*np.sin(cross/1700.) + phase)
              + .65*np.sin(cross/1450. - forward/2100. + 1.7*phase)) / 1.65
    fine = (np.sin(forward/420. + cross/610. + .37*phase)
            + .7*np.sin(cross/520. - forward/730. + 1.31*phase)) / 1.7
    relief = 1.35*coarse + .38*fine
    relief *= smooth(np.maximum(forward, 0.)/900.)
    # Unequal shoreline lobes and shallow embayments replace a regular radial rim.
    shoreline_phase = .37*np.sin(2.*angle+.6)+.19*np.sin(5.*angle-1.1)+.10*fine
    radius_limit = nominal_radius_m*(1.+shoreline_phase)
    center_shift_m = 100.*np.sin(forward/1700.+.3)*smooth(np.maximum(forward, 0.)/1800.)
    half_width = (curved_side_half_width_m*smooth(np.maximum(forward, 0.)/4200.)
                  + 260.*np.sin(forward/1050.)*smooth(np.maximum(forward, 0.)/1800.))
    transverse_weight = 1.-smooth((np.abs(cross-center_shift_m)-(half_width-500.))/1400.)
    radial_weight = 1.-smooth((radius-(radius_limit-900.))/2400.)
    upstream_weight = smooth((forward+300.)/600.)
    weight = radial_weight*transverse_weight*upstream_weight*smooth(radius/220.)
    # The offshore fan can approach another headland after crossing the sea.
    # Return to that terrain instead of excavating a second low delta plain.
    coast_return = smooth((forward-4200.)/1000.)*smooth((base+12.)/24.)
    weight *= 1.-coast_return
    phase = (int(seed)%997)/997.*2.*np.pi
    basin = .9*np.exp(-((radius-2800.)/1100.)**2) * (.5+.5*np.sin(4.*angle+radius/630.+.2))
    effective_radius = radius*nominal_radius_m/radius_limit
    cone = 3.2-.00072*effective_radius+relief-basin
    bed = base*(1.-weight)+cone*weight
    # Round the meeting of the fan shoulder and the inherited coastal contour.
    # Its finite support is included in the construction footprint before carving.
    grid_spacing = float(np.median(np.hypot(np.diff(x, axis=1), np.diff(z, axis=1))))
    coast_sigma_cells = 400./grid_spacing
    shoulder = gaussian_filter(weight, coast_sigma_cells)
    seam_weight = (smooth(shoulder/.03) * (1.-smooth((np.abs(base)-12.)/24.))
                   * smooth((radius-2200.)/800.))
    bed += seam_weight*(gaussian_filter(bed, coast_sigma_cells)-bed)
    weight = np.maximum(weight, seam_weight)
    return {"bed_m": bed, "weight": weight, "u_m": u, "v_m": v, "radius_m": radius,
            "angle_rad": angle, "outer_radius_m": radius_limit, "target_bed_m": cone,
            "direction_xz": direction, "normal_xz": lateral, "apex_xz_m": apex,
            "parameters": {"apex_u_m": apex_u, "nominal_radius_m": nominal_radius_m, "nominal_front_diagnostic_opening_degrees": 80.,
                           "outer_blend_m": 2400., "outer_blend_radius_offset_m": -900.,
                           "transverse_blend_m": 1400., "apex_blend_m": 220.,
                           "curved_side_half_width_m": curved_side_half_width_m, "side_widening_length_m": 4200.,
                           "side_width_undulation_m": 260., "side_width_wavelength_m": 1050.,
                           "cone_apex_elevation_m": 3.2, "radial_grade": .00072,
                           "relief_amplitudes_m": [1.35, .38], "basin_depth_m": .9,
                           "outer_radius_asymmetry": [.37, .19, .10], "direction_sampling_half_span_m": 250.,
                           "coastal_seam_sigma_m": 400., "coastal_seam_base_band_m": [12., 36.],
                           "coastal_seam_radius_ramp_m": [2200., 3000.], "coastal_seam_shoulder_weight_scale": .03,
                           "far_coast_return_forward_m": [4200., 5200.], "far_coast_return_base_m": [-12., 12.],
                           "correlated_relief_m": [1.35, .38], "relief_local_wavelength_m": [1150., 1450., 420., 610.],
                           "shoreline_harmonics": [2, 5], "shoreline_seed_modulus": 997}}


def _generate_landward_plain(base_bed_m, origin_xz_m, spacing_m, incoming_path_xz_m,
                             incoming_bed_m, mouth_xz_m, incoming_q_m3_s, *, seed):
    """Declared cut/fill construction; no upstream sediment finances this scene."""
    base = np.asarray(base_bed_m, dtype=float)
    origin = np.asarray(origin_xz_m, dtype=float)
    spacing = float(spacing_m)
    ipath = np.asarray(incoming_path_xz_m, dtype=float)
    ibed = np.asarray(incoming_bed_m, dtype=float)
    mouth = np.asarray(mouth_xz_m, dtype=float)
    q_in = np.asarray(incoming_q_m3_s, dtype=float)
    if (base.ndim != 2 or ipath.ndim != 2 or ipath.shape[1] != 2 or ibed.shape != (ipath.shape[0],)
            or not np.isfinite(base).all() or not np.isfinite(ipath).all() or not np.isfinite(ibed).all()
            or not np.isfinite(q_in).all() or np.any(q_in < 0.) or spacing <= 0.):
        raise ValueError("finite matching scene, incoming profile and nonnegative discharge required")
    x, z = np.meshgrid(origin[0]+np.arange(base.shape[1])*spacing, origin[1]+np.arange(base.shape[0])*spacing)
    fan = _river_fan_fields(base, x, z, ipath, mouth, seed=seed)
    e, normal = fan["direction_xz"], fan["normal_xz"]
    u, v = fan["u_m"], fan["v_m"]
    profile_u = (ipath-mouth) @ e
    if np.any(np.diff(profile_u) <= 0.) or profile_u[0] > -4500. or profile_u[-1] < -1800.:
        raise ValueError("incoming profile must span the retained river, transition and junction")
    def smooth(t):
        t = np.clip(t, 0., 1.)
        return t*t*(3.-2.*t)
    bed = fan["bed_m"].copy()
    combined_weight = fan["weight"]
    land_weight = np.where(u<=0., combined_weight, 0.)

    retained_u, junction_u = -4500., fan["parameters"]["apex_u_m"]
    plain_start_u = junction_u-400.
    transition_bed = float(np.interp(retained_u, profile_u, ibed))
    transition_t = smooth((profile_u-retained_u)/(plain_start_u-retained_u))
    new_profile = (1.-transition_t)*transition_bed+transition_t*(-1.2)
    retained = profile_u <= retained_u+1e-8
    new_profile = np.where(retained, ibed, new_profile)
    new_profile = np.where(profile_u > plain_start_u, -1.2-.00025*(profile_u-plain_start_u), new_profile)
    new_stage = np.maximum(new_profile+3., 0.)
    stage_t = smooth((profile_u-retained_u)/(plain_start_u-retained_u))
    new_stage = np.where(profile_u > retained_u, new_profile+3.-1.4*stage_t, new_stage)
    new_stage = np.where(profile_u > plain_start_u, .4-.0001*(profile_u-plain_start_u), new_stage)
    keep = profile_u <= junction_u
    designed_path = ipath[keep]
    designed_bed = new_profile[keep]
    designed_stage = new_stage[keep]
    designed_u = profile_u[keep]
    if designed_u[-1] < junction_u-1e-8:
        junction_xz = fan["apex_xz_m"]
        designed_path = np.vstack((designed_path, junction_xz))
        designed_bed = np.r_[designed_bed, np.interp(junction_u, profile_u, new_profile)]
        designed_stage = np.r_[designed_stage, np.interp(junction_u, profile_u, new_stage)]
        designed_u = np.r_[designed_u, junction_u]
    # Preserve the upstream bed; support the declared transition with a finite
    # bank blend, whose entire positive volume belongs to construction fill.
    grid_transition_bed = np.interp(u, profile_u, new_profile)
    support_weight = ((1.-smooth((np.abs(v)-100.)/500.))
                      * smooth((u-(profile_u[0]-600.))/200.)
                      * (1.-smooth((u+2300.)/100.)))
    support_target = np.maximum(bed, grid_transition_bed+4.)
    before_support = bed.copy()
    bed = bed*(1.-support_weight)+support_target*support_weight
    support_added_height = bed-before_support
    main = apply_designed_section(bed, origin, spacing, designed_path, designed_bed, designed_stage, 100., allow_fill=True)
    bed = main["bed_m"].copy()
    stage = main["stage_m"].copy()
    main_mask = main["section_mask"]
    # First a lateral branch leaves the trunk, then its continuation splits.
    # A single longitudinal profile makes every shared node agree exactly.
    trunk_u = np.linspace(0., 500., 1201)
    def trunk_lateral(station):
        return 75.*np.sin(station/430.) + 28.*np.sin(station/190.)
    trunk_v = trunk_lateral(trunk_u)
    junction_xz = fan["apex_xz_m"]
    trunk = junction_xz+trunk_u[:, None]*e+trunk_v[:, None]*normal
    branch_specs = ((250., 5750., -2100., 82., .50),
                    (500., 5900., 280., 66., .30),
                    (500., 5600., 1900., 52., .20))
    n_branch = len(branch_specs)
    paths, widths, shares = [], [], []
    for index, (start_u, length, lateral_offset, width, share) in enumerate(branch_specs):
        t = np.linspace(0., 1., 1201)
        branch_u = start_u + length*t
        start_v = trunk_lateral(start_u)
        opening = 1.-np.exp(-(length*t/1100.)**2)
        branch_v = (start_v + (lateral_offset-start_v)*opening
                    + (145.+index*37.)*np.sin(np.pi*t)*np.sin(3.*np.pi*t+index*.8))
        paths.append(junction_xz+branch_u[:, None]*e+branch_v[:, None]*normal)
        widths.append(width)
        shares.append(share)
    paths = np.asarray(paths)
    widths, shares = np.asarray(widths), np.asarray(shares)
    all_paths = [trunk, *paths]
    all_stations = [trunk_u, *[np.linspace(spec[0], spec[0]+spec[1], 1201) for spec in branch_specs]]
    all_profile_bed = [float(designed_bed[-1])-.00038*station for station in all_stations]
    all_profile_stage = [float(designed_stage[-1])*(1.-smooth(station/2400.)) for station in all_stations]
    branch_masks, branch_cores, branch_cuts = [], [], []
    for branch_index, (path, width) in enumerate(zip(all_paths, [100., *widths])):
        before = bed.copy()
        section = apply_designed_section(bed, origin, spacing, path, all_profile_bed[branch_index], all_profile_stage[branch_index],
                                         float(width), allow_fill=False)
        bed = section["bed_m"].copy()
        branch_masks.append(section["section_mask"])
        branch_cores.append(section["section_core_mask"])
        branch_cuts.append(np.maximum(before-bed, 0.))
        stage = np.maximum(stage, section["stage_m"])
    branch_masks, branch_cores, branch_cuts = map(np.asarray, (branch_masks, branch_cores, branch_cuts))
    trunk_mask, trunk_core = branch_masks[0], branch_cores[0]
    branch_masks = branch_masks[1:]
    branch_cores = branch_cores[1:]
    branch_cuts = branch_cuts[1:]
    channel = main_mask | trunk_mask | np.any(branch_masks, axis=0)
    source_rc = np.rint((designed_path[0]-origin)/spacing).astype(int)
    water = connected_design_water(bed, stage, channel, (int(source_rc[1]), int(source_rc[0])))
    trunk_actual = trunk_core & water['wet_mask'] & (water['water_depth_m']>.1)
    trunk_labels, _ = label(trunk_actual, generate_binary_structure(2, 1))
    trunk_cells = np.rint((trunk-origin)/spacing).astype(int)
    trunk_ids = trunk_labels[trunk_cells[:, 1], trunk_cells[:, 0]]
    if trunk_ids[0] <= 0 or np.any(trunk_ids != trunk_ids[0]):
        raise ValueError('trunk positive-depth core is not D4 continuous')
    from scipy.ndimage import distance_transform_edt
    open_sea_distance = distance_transform_edt(~(water['connected_ocean_mask'] & ~channel))*spacing
    endpoint_cells = np.rint((paths[:, -1]-origin)/spacing).astype(int)
    if (np.any(endpoint_cells < 0) or np.any(endpoint_cells[:, 0] >= base.shape[1])
            or np.any(endpoint_cells[:, 1] >= base.shape[0])):
        raise ValueError('landward branch endpoint outside scene')
    endpoint_sea_distance = open_sea_distance[endpoint_cells[:, 1], endpoint_cells[:, 0]]
    if np.any(endpoint_sea_distance > 100.):
        raise ValueError('branch terminal does not reach open sea within 100m beyond channel banks')
    actual = branch_cores & water["wet_mask"][None, :, :] & (water["water_depth_m"][None, :, :]>.1)
    for index, path in enumerate(paths):
        cells = np.rint((path-origin)/spacing).astype(int)
        if np.any(cells < 0) or np.any(cells[:, 0] >= base.shape[1]) or np.any(cells[:, 1] >= base.shape[0]):
            raise ValueError("landward branch outside scene")
        labels, _ = label(actual[index], generate_binary_structure(2, 1))
        ids = labels[cells[:, 1], cells[:, 0]]
        if ids[0] <= 0 or not np.all(ids == ids[0]):
            raise ValueError("landward branch positive-depth core is not D4 continuous")
    transects = []
    for distance in (-700., 800., 2000.):
        slab = np.abs(u-distance) <= spacing*.75
        masks = actual & slab[None, :]
        counts = masks.sum(axis=(1, 2))
        medians = [float(np.median(v[mask])) if mask.any() else float("nan") for mask in masks]
        if np.any(counts == 0) or any(abs(medians[i]-medians[j]) < 3.*spacing or np.any(masks[i]&masks[j]) for i in range(3) for j in range(i+1, 3)):
            raise ValueError("landward/sea transect does not contain three distinct wet branches")
        land_counts = (masks & (base>0.)[None, :, :]).sum(axis=(1, 2))
        if distance < 0. and np.any(land_counts == 0):
            raise ValueError("landward transect branches must cross original land")
        transects.append({"u_m": distance, "v_medians_m": medians, "wet_counts": counts.tolist(),
                          "original_land_wet_counts": land_counts.tolist()})
    delta, cell_area = bed-base, spacing*spacing
    original_land = base > 0.
    landward = (u >= -2200.) & (u <= 0.)
    original_main_strip = np.abs(v) <= 50.
    off_strip = original_land & landward & ~original_main_strip & (np.abs(delta)>.1)
    footprint = (combined_weight>0.) | (support_weight>0.) | channel
    retained_field = (u <= retained_u-2.*spacing) & (main["section_weight"] == 1.)
    old_section = apply_designed_section(base, origin, spacing, ipath, ibed, np.maximum(ibed+3., 0.), 100., allow_fill=True)
    if not np.array_equal(bed[retained_field], old_section["bed_m"][retained_field]):
        raise ValueError("retained upstream channel core differs from original incoming section")
    if not np.array_equal(new_profile[retained], ibed[retained]):
        raise ValueError("retained upstream profile was changed")
    if not np.array_equal(bed[~footprint], base[~footprint]):
        raise ValueError("terrain outside construction footprint was changed")
    cut, fill = np.maximum(-delta, 0.), np.maximum(delta, 0.)
    def ledger(mask):
        return {"cut_bulk_m3": float(cut[mask].sum()*cell_area), "fill_bulk_m3": float(fill[mask].sum()*cell_area),
                "net_bulk_m3": float(delta[mask].sum()*cell_area)}
    budget = ledger(np.ones(base.shape, bool))
    budget["material_account_residual_m3"] = budget["fill_bulk_m3"]-budget["cut_bulk_m3"]-budget["net_bulk_m3"]
    audit = dict(budget, source_connected=True, branch_transects=transects,
                 branch_terminal_open_sea_distance_m=endpoint_sea_distance.tolist(),
                 branch_cut_wet_cell_counts=[int(np.count_nonzero(actual[i] & (branch_cuts[i]>.05) & ((u>=600.)&(u<=2300.)))) for i in range(3)],
                 original_land_construction=ledger(original_land), landward_original_land_construction=ledger(original_land & landward),
                 original_land_off_old_strip_changed_area_m2=float(off_strip.sum()*cell_area),
                 original_land_off_old_strip_wet_area_m2=float((off_strip & water["wet_mask"]).sum()*cell_area),
                 original_land_off_old_strip_dry_area_m2=float((off_strip & ~water["wet_mask"]).sum()*cell_area),
                 retained_upstream_profile_exact=True, outside_footprint_exact=True,
                 retained_upstream_channel_core_exact=True,
                 bank_support_gross_fill_before_channel_cut_m3=float(support_added_height.sum()*cell_area),
                 bank_support_final_region_construction=ledger(support_weight>0.),
                 main_wet_depth_max_by_reach_m={name: float(np.max(water["water_depth_m"][mask & main_mask], initial=0.))
                                               for name, mask in (("retained", u<=-4500.), ("transition", (u>-4500.)&(u<-2200.)), ("plain_approach", u>=-2200.))},
                 transition_start_bed_m=transition_bed, maximum_transition_grade=float(np.max(-np.diff(designed_bed)/np.diff(designed_u))))
    from scipy.ndimage import distance_transform_edt
    apex_cell = np.rint((fan["apex_xz_m"]-origin)/spacing).astype(int)
    if (apex_cell.shape != (2,) or np.any(apex_cell < 0)
            or apex_cell[0] >= base.shape[1] or apex_cell[1] >= base.shape[0]):
        raise ValueError("fan apex falls outside scene grid")
    front_region = ((fan["radius_m"] >= 4800.) & (fan["radius_m"] <= 6600.)
                    & (np.abs(fan["angle_rad"]) <= np.deg2rad(40.)))
    apex_region = (fan["radius_m"]<800.) & (combined_weight>.05)
    if not np.any(front_region) or not np.any(apex_region):
        raise ValueError("fan placement diagnostics have empty regions")
    audit["fan_placement"] = {
        "apex_original_bed_m": float(base[apex_cell[1], apex_cell[0]]),
        "apex_nearest_original_ocean_m": float(distance_transform_edt(original_land)[apex_cell[1], apex_cell[0]]*spacing),
        "apex_zone_original_land_fraction": float(original_land[apex_region].mean()),
        "front_zone_original_ocean_fraction": float((~original_land)[front_region].mean()),
        "front_zone_final_above_sea_fraction": float((bed[front_region]>0.).mean()),
        "front_zone_semantics": "radius 4800..6600m, absolute angle <=40deg about actual saved junction",
    }
    if audit["original_land_off_old_strip_wet_area_m2"] <= 0. or audit["original_land_off_old_strip_dry_area_m2"] <= 0.:
        raise ValueError("constructed original-land plain lacks a mixed dry/wet outcome")
    branch_profiles_bed = np.asarray(all_profile_bed[1:])
    branch_profiles_stage = np.asarray(all_profile_stage[1:])
    branch_stations = np.asarray(all_stations[1:])
    endpoint_offsets = paths[:, -1]-junction_xz
    branch_radii = np.linalg.norm(endpoint_offsets, axis=1)
    branch_angles = np.arctan2(endpoint_offsets @ normal, endpoint_offsets @ e)
    junction_stations = np.asarray([spec[0] for spec in branch_specs])
    junction_beds = float(designed_bed[-1])-.00038*junction_stations
    junction_stages = float(designed_stage[-1])*(1.-smooth(junction_stations/2400.))
    junction_cells = np.rint((paths[:, 0]-origin)/spacing).astype(int)
    if np.any(base[junction_cells[:, 1], junction_cells[:, 0]] <= 0.):
        raise ValueError("initial distributary junctions must lie on original land")
    audit["junctions"] = [{"parent": "trunk", "station_from_apex_m": float(station),
                            "original_land": True, "bed_m": float(junction_beds[i]),
                            "stage_m": float(junction_stages[i])}
                           for i, station in enumerate(junction_stations)]
    arrays = {"base_bed_m": base, "bed_m": bed, "design_stage_m": stage, "channel_mask": channel,
              "trunk_path_xz_m": trunk, "trunk_section_mask": trunk_mask, "trunk_core_mask": trunk_core,
              "trunk_profile_bed_m": all_profile_bed[0], "trunk_profile_stage_m": all_profile_stage[0],
              "trunk_station_m": trunk_u, "branch_station_m": branch_stations,
              "trunk_reach_station_bounds_m": np.array([[0., 250.], [250., 500.]]),
              "trunk_reach_discharge_fraction": np.array([1., .5]),
              "trunk_reach_q_m3_s": q_in[:, None]*np.array([1., .5]),
              "branch_junction_station_m": junction_stations, "branch_parent_index": np.full(3, -1, dtype=int),
              "main_section_mask": main_mask, "branch_section_masks": branch_masks, "branch_core_masks": branch_cores,
              "branch_cut_depth_m": branch_cuts, "platform_weight": combined_weight, "landward_platform_weight": land_weight,
              "construction_footprint_mask": footprint, "transition_support_weight": support_weight,
              "wetland_u_m": u, "wetland_v_m": v, "old_incoming_path_xz_m": ipath, "old_incoming_bed_m": ibed,
              "fan_radius_m": fan["radius_m"], "fan_angle_rad": fan["angle_rad"],
              "fan_outer_radius_m": fan["outer_radius_m"], "fan_target_bed_m": fan["target_bed_m"],
              "designed_incoming_path_xz_m": designed_path, "designed_incoming_bed_m": designed_bed,
              "designed_incoming_stage_m": designed_stage, "retained_upstream_profile_mask": retained,
              "retained_upstream_raster_mask": retained_field,
              "bank_support_added_height_before_channel_cut_m": support_added_height,
              "incoming_q_m3_s": q_in, "branch_q_m3_s": q_in[:, None]*shares, "branch_width_m": widths,
              "branch_share": shares, "branch_paths_xz_m": paths, "branch_profile_bed_m": branch_profiles_bed,
              "branch_profile_stage_m": branch_profiles_stage, "original_land_mask": original_land,
              "landward_off_old_strip_changed_mask": off_strip}
    arrays.update(water)
    metadata = {"algorithm": "stylized-river-mouth-landward-plain-coastal-cone-v10", "seed": int(seed),
                "branching_model": {"type": "staggered_hierarchical_distributaries", "path_count_including_trunk": len(all_paths),
                                    "branch_start_u_m": [spec[0] for spec in branch_specs],
                                    "branch_length_m": [spec[1] for spec in branch_specs],
                                    "curvature_amplitude_m": [145.+i*37. for i in range(n_branch)],
                                    "trunk_length_m": 500., "trunk_width_m": 100.,
                                    "bed_grade": .00038, "stage_zero_station_m": 2400.,
                                    "branch_parent_index_convention": "-1 is trunk; terminal branches ordered as discharge shares",
                                    "opening_scale_m": 1100.},
                "construction": "explicit geometry and static designed stage; no sediment-driven origin or hydraulic solution",
                "retained_profile_before_u_m": retained_u, "transition_u_m": [-4500., -2200.],
                "landward_plain_u_m": [-2200., 0.], "distributary_start_u_m": junction_u,
                "junction_bed_m": float(designed_bed[-1]), "junction_stage_m": float(designed_stage[-1]),
                "fan_parameters": fan["parameters"], "river_direction_xz": e.tolist(),
                "fan_apex_xz_m": fan["apex_xz_m"].tolist(),
                "branch_outer_radii_m": branch_radii.tolist(), "branch_final_angles_degrees": np.rad2deg(branch_angles).tolist(),
                "incoming_width_m": 100., "branch_width_m": widths.tolist(), "branch_shares": shares.tolist(),
                "bank_support_parameters": {"target_above_profile_bed_m": 4., "full_lateral_half_width_m": 100., "lateral_taper_m": 500.,
                                             "upstream_start_offset_m": -600., "upstream_taper_m": 200., "downstream_taper_u_m": [-2300., -2200.]},
                "profile_mismatch_policy": "retain actual saved profile upstream of declared transition; build explicit supported grade transition to local low plain; all cut/fill counted",
                "coordinates": "X east Z south; u downstream along saved near-junction tangent; fan radius/angle from apex u=-1800m", "hydraulic_ready": False, "publishable": False}
    return {"arrays": arrays, "audit": audit, "metadata": metadata}


