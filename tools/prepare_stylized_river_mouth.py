import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The scene generator may run from an isolated worktree while consuming the
# separately authorized, read-only source bundle.  Extend the package search
# path before importing task-local source modules; generated outputs remain in
# the caller-selected worktree.
_source_root = Path(os.environ.get("TERRAGENESIS_SOURCE_ROOT", "")).resolve() if os.environ.get("TERRAGENESIS_SOURCE_ROOT") else None
if _source_root is not None:
    sys.path.append(str(_source_root))
    import terrain_pipeline as _terrain_pipeline
    _terrain_pipeline.__path__.append(str(_source_root / "terrain_pipeline"))
    import terrain_pipeline.surface_rivers as _surface_rivers
    _surface_rivers.__path__.append(str(_source_root / "terrain_pipeline" / "surface_rivers"))

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates

from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field
from terrain_pipeline.common_infra import file_sha256


def load_scene_inputs(root):
    root = Path(root).resolve()

    plan_path = root / "verification/hydrological-planning-domain/v5-lake-20261014-02/plan.npz"
    td_path = root / "verification/hydrological-planning-domain/large-td-confluence-20261014-03/native-routing.npz"
    profile_path = root / ".scratch/hydrological-planning-domain/saved-bed-mouth-20261016-01/centerline.npz"
    supply_path = root / ".scratch/hydrological-planning-domain/saved-river-seasonal-supply-20261016-01/supply.npz"
    supply_summary_path = supply_path.with_name("summary.json")

    parent = load_plan(plan_path)

    with np.load(td_path, allow_pickle=False) as td:
        raw_td = np.asarray(td["original_td_m"], dtype=np.float64)
        td_metadata = json.loads(str(td["metadata_json"]))

    td_shape = (int(td_metadata["shape"][0]), int(td_metadata["shape"][1]))
    td_origin_x = float(td_metadata["origin_xz_m"][0])
    td_origin_z = float(td_metadata["origin_xz_m"][1])
    td_spacing = float(td_metadata["spacing_m"])

    with np.load(profile_path, allow_pickle=False) as profile:
        node_xz_m = np.asarray(profile["node_xz_m"], dtype=np.float64)
        bed_m = np.asarray(profile["bed_m"], dtype=np.float64)
        supported_mask = np.asarray(profile["supported_mask"], dtype=bool)
        profile_metadata = json.loads(str(profile["metadata_json"]))

    if profile_metadata["plan_identity"] != parent["identity_sha256"]:
        raise ValueError("centerline plan_identity does not match accepted planning plan identity")
    if int(parent["receiver"].ravel()[8470]) != 8600:
        raise ValueError("original_parent_receiver[8470] does not equal 8600")

    bracket_after = profile_metadata["first_land_to_connected_ocean_bracket"]["after"]
    mouth_index = int(bracket_after["index"])
    mouth_xz_m = np.asarray(bracket_after["position_xz_m"], dtype=np.float64)

    incoming_path_xz_m = node_xz_m[: mouth_index + 1].copy()
    incoming_bed_m = bed_m[: mouth_index + 1].copy()
    if not bool(np.all(supported_mask[: mouth_index + 1])):
        raise ValueError("incoming centerline includes unsupported nodes")

    accepted_bed_source_hashes = {}
    for source_path, expected_hash in profile_metadata["source_sha256"].items():
        actual_hash = file_sha256(Path(source_path))
        if actual_hash != expected_hash:
            raise ValueError("accepted bed source hash mismatch for %s" % source_path)
        accepted_bed_source_hashes[str(source_path)] = actual_hash

    with open(supply_summary_path, "r", encoding="utf-8") as handle:
        supply_summary = json.load(handle)
    if supply_summary["plan_identity"] != parent["identity_sha256"]:
        raise ValueError("supply summary plan_identity does not match accepted planning plan identity")
    if file_sha256(supply_path) != supply_summary["supply_archive_sha256"]:
        raise ValueError("supply archive hash does not match summary")

    with np.load(supply_path, allow_pickle=False) as supply:
        incoming_q_m3_s = np.asarray(supply["selected_q_m3_s"], dtype=np.float64)
        q_step_start_s = np.asarray(supply["step_start_s"], dtype=np.float64).copy()
        q_step_end_s = np.asarray(supply["step_end_s"], dtype=np.float64).copy()

    scene_spacing = 20.0
    scene_shape = (800, 800)
    scene_centre = np.round(mouth_xz_m / scene_spacing) * scene_spacing
    scene_origin = scene_centre - 8000.0 + 10.0

    x_coords = scene_origin[0] + np.arange(scene_shape[1], dtype=np.float64) * scene_spacing
    z_coords = scene_origin[1] + np.arange(scene_shape[0], dtype=np.float64) * scene_spacing
    x, z = np.meshgrid(x_coords, z_coords)

    native_x = (x - td_origin_x) / td_spacing
    native_z = (z - td_origin_z) / td_spacing
    if (
        not bool(np.all(native_x >= 0.0))
        or not bool(np.all(native_x <= td_shape[1] - 1))
        or not bool(np.all(native_z >= 0.0))
        or not bool(np.all(native_z <= td_shape[0] - 1))
    ):
        raise ValueError("scene query coordinates fall outside valid native TD domain")

    sampled_raw_td = map_coordinates(
        raw_td,
        [native_z, native_x],
        order=1,
        mode="nearest",
        prefilter=False,
    )

    smoothed_native = gaussian_filter(raw_td, sigma=500.0 / 30.0, mode="nearest")
    sampled_smoothed = map_coordinates(
        smoothed_native,
        [native_z, native_x],
        order=1,
        mode="nearest",
        prefilter=False,
    )
    td_residual_m = sampled_raw_td - sampled_smoothed

    parent_origin_x = float(parent["origin_xz_m"][0])
    parent_origin_z = float(parent["origin_xz_m"][1])
    parent_spacing = float(parent["spacing_m"])
    macro_bed_m = continuous_macro_field(
        parent,
        (x - parent_origin_x) / parent_spacing,
        (z - parent_origin_z) / parent_spacing,
        validate_query_support_only=True,
    )

    base_bed_m = macro_bed_m + 0.35 * td_residual_m

    input_hashes = {
        str(plan_path): file_sha256(plan_path),
        str(td_path): file_sha256(td_path),
        str(profile_path): file_sha256(profile_path),
        str(supply_path): file_sha256(supply_path),
        str(supply_summary_path): file_sha256(supply_summary_path),
    }

    return {
        "base_bed_m": base_bed_m,
        "raw_td_sample_m": sampled_raw_td,
        "macro_bed_m": macro_bed_m,
        "td_residual_m": td_residual_m,
        "origin_xz_m": scene_origin,
        "spacing_m": scene_spacing,
        "mouth_xz_m": mouth_xz_m,
        "incoming_path_xz_m": incoming_path_xz_m,
        "incoming_bed_m": incoming_bed_m,
        "incoming_q_m3_s": incoming_q_m3_s,
        "q_step_start_s": q_step_start_s,
        "q_step_end_s": q_step_end_s,
        "plan_identity": parent["identity_sha256"],
        "input_hashes": input_hashes,
        "accepted_bed_source_hashes": accepted_bed_source_hashes,
    }

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from tools.compare_hydrology_projection_naturalness import fixed_hillshade
from scipy.ndimage import label, generate_binary_structure


def render_saved_scene(output):
    output = Path(output)
    data = np.load(output / "scene.npz", allow_pickle=False)
    bed_m = data["bed_m"]
    base_bed_m = data["base_bed_m"]
    water_depth_m = data["water_depth_m"]
    wet_mask = data["wet_mask"].astype(bool)
    metadata = json.loads(str(data["metadata_json"]))

    origin_xz_m = np.asarray(metadata["origin_xz_m"], dtype=float)
    spacing_m = float(metadata["spacing_m"])
    mouth_xz_m = np.asarray(metadata["mouth_xz_m"], dtype=float)

    rows, cols = bed_m.shape

    def _rgb_after():
        land_cmap = LinearSegmentedColormap.from_list(
            "land", ["#b4c887", "#789b63", "#9aab81", "#c9d0bf"]
        )
        depth_cmap = LinearSegmentedColormap.from_list(
            "depth", ["#bde1d1", "#63b6b6", "#297f9b", "#174e78"]
        )
        land_norm = Normalize(vmin=0.0, vmax=350.0)
        depth_norm = Normalize(vmin=0.0, vmax=6.0)

        rgb = land_cmap(land_norm(np.clip(bed_m, 0.0, 350.0)))[..., :3]
        shade = 0.65 + 0.4 * fixed_hillshade(bed_m, spacing_m)
        rgb = rgb * shade[..., None]

        actual_dry_low = (~wet_mask) & (bed_m >= 0.0) & (bed_m < 1.2)
        actual_dry_mid = (~wet_mask) & (bed_m >= 1.2) & (bed_m < 3.0)
        reed = np.array([0x7b, 0x9c, 0x63], dtype=float) / 255.0
        pale = np.array([0xc9, 0xd0, 0xbf], dtype=float) / 255.0
        rgb[actual_dry_low] = reed
        rgb[actual_dry_mid] = pale

        wet_colors = depth_cmap(depth_norm(np.clip(water_depth_m, 0.0, 6.0)))[..., :3]
        rgb[wet_mask] = wet_colors[wet_mask]

        shallow = wet_mask & (water_depth_m < 0.3)
        shallow_color = np.array([0xb6, 0xd3, 0xad], dtype=float) / 255.0
        rgb[shallow] = shallow_color

        return np.clip(rgb, 0.0, 1.0)

    def _rgb_before():
        land_cmap = LinearSegmentedColormap.from_list(
            "land", ["#b4c887", "#789b63", "#9aab81", "#c9d0bf"]
        )
        depth_cmap = LinearSegmentedColormap.from_list(
            "depth", ["#bde1d1", "#63b6b6", "#297f9b", "#174e78"]
        )
        land_norm = Normalize(vmin=0.0, vmax=350.0)
        depth_norm = Normalize(vmin=0.0, vmax=6.0)

        rgb = land_cmap(land_norm(np.clip(base_bed_m, 0.0, 350.0)))[..., :3]
        shade = 0.65 + 0.4 * fixed_hillshade(base_bed_m, spacing_m)
        rgb = rgb * shade[..., None]


        struct = generate_binary_structure(2, 1)
        below = base_bed_m < 0.0
        labels, n = label(below, structure=struct)
        perim_labels = set()
        if n > 0:
            perim_labels.update(np.unique(labels[0, :]))
            perim_labels.update(np.unique(labels[-1, :]))
            perim_labels.update(np.unique(labels[:, 0]))
            perim_labels.update(np.unique(labels[:, -1]))
        perim_labels.discard(0)
        before_wet = np.isin(labels, list(perim_labels)) if perim_labels else np.zeros_like(below)
        before_depth = np.where(before_wet, -base_bed_m, 0.0)
        low = (~before_wet) & (base_bed_m >= 0.0) & (base_bed_m < 1.2)
        mid = (~before_wet) & (base_bed_m >= 1.2) & (base_bed_m < 3.0)
        rgb[low] = np.array([0x7b, 0x9c, 0x63]) / 255.0
        rgb[mid] = np.array([0xc9, 0xd0, 0xbf]) / 255.0

        wet_colors = depth_cmap(depth_norm(np.clip(before_depth, 0.0, 6.0)))[..., :3]
        rgb[before_wet] = wet_colors[before_wet]

        shallow = before_wet & (before_depth < 0.3)
        rgb[shallow] = np.array([0xb6, 0xd3, 0xad], dtype=float) / 255.0

        return np.clip(rgb, 0.0, 1.0)

    extent = [
        origin_xz_m[0] - spacing_m / 2.0,
        origin_xz_m[0] + (cols - 0.5) * spacing_m,
        origin_xz_m[1] + (rows - 0.5) * spacing_m,
        origin_xz_m[1] - spacing_m / 2.0,
    ]
    extent_km = [e / 1000.0 for e in extent]

    rgb_after = _rgb_after()
    rgb_before = _rgb_before()

    filenames = []

    fig, ax = plt.subplots(figsize=(12, 12))
    ax.imshow(rgb_after, extent=extent_km, origin="upper")
    ax.set_aspect("equal")
    ax.set_title("Stylized river-mouth wetland | 16 km")
    ax.set_xlabel("km")
    ax.set_ylabel("km")
    overview_path = output / "overview-16km.png"
    fig.savefig(overview_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    filenames.append(str(overview_path))

    is_landward = metadata.get("algorithm", "").startswith("stylized-river-mouth-landward-plain")
    axis = np.asarray(metadata.get("river_direction_xz", np.array([1., 1.])/np.sqrt(2.)))
    c_m = mouth_xz_m + (650.0 if is_landward else 1200.0) * axis
    cx_km = c_m[0] / 1000.0
    cz_km = c_m[1] / 1000.0

    fig, ax = plt.subplots(figsize=(12, 12))
    ax.imshow(rgb_after, extent=extent_km, origin="upper")
    ax.set_aspect("equal")
    half_size = 3.9 if 'fan_parameters' in metadata else 3.4 if is_landward else 2.8
    ax.set_xlim(cx_km - half_size, cx_km + half_size)
    ax.set_ylim(cz_km + half_size, cz_km - half_size)
    ax.set_title("Carved branches and wetland islands")
    ax.set_xlabel("km")
    ax.set_ylabel("km")
    detail_path = output / "mouth-detail.png"
    fig.savefig(detail_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    filenames.append(str(detail_path))

    fig, axes = plt.subplots(1, 2, figsize=(18, 9))
    for ax, img, title in zip(
        axes,
        [rgb_before, rgb_after],
        ["Base terrain", "Constructed wetland"],
    ):
        ax.imshow(img, extent=extent_km, origin="upper")
        ax.set_aspect("equal")
        ax.set_xlim(extent_km[0], extent_km[1])
        ax.set_ylim(extent_km[2], extent_km[3])
        ax.set_title(title)
        ax.set_xlabel("km")
        ax.set_ylabel("km")
    before_after_path = output / "before-after.png"
    fig.savefig(before_after_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    filenames.append(str(before_after_path))

    if is_landward:
        fig, axes = plt.subplots(1, 2, figsize=(17, 8))
        change = bed_m-base_bed_m
        limit = max(1., float(np.percentile(np.abs(change[np.abs(change)>.01]), 98)))
        image = axes[0].imshow(change, extent=extent_km, origin="upper", cmap="RdBu_r", vmin=-limit, vmax=limit)
        axes[0].contour(base_bed_m, levels=[0.], colors="black", linewidths=.8, origin="upper", extent=extent_km)
        axes[0].set_title("Construction bed change; black = original coast")
        fig.colorbar(image, ax=axes[0], label="Final bed minus original base (m)", shrink=.7)
        land_outcome = np.zeros(bed_m.shape, np.int8)
        land = data["landward_off_old_strip_changed_mask"].astype(bool)
        land_outcome[land & ~wet_mask] = 1
        land_outcome[land & wet_mask] = 2
        axes[1].imshow(land_outcome, extent=extent_km, origin="upper", cmap=LinearSegmentedColormap.from_list("outcomes", ["#eeeeee", "#7c9d55", "#268ca8"], N=3), vmin=0, vmax=2)
        axes[1].set_title("Original land changed off old channel: dry green / wet blue")
        for ax in axes:
            ax.set_xlim(cx_km-half_size, cx_km+half_size)
            ax.set_ylim(cz_km+half_size, cz_km-half_size)
            ax.set_xlabel("X (km)")
            ax.set_ylabel("Z (km)")
        change_path = output/"construction-change-original-land.png"
        fig.savefig(change_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        filenames.append(str(change_path))

        fig, axes = plt.subplots(1, 2, figsize=(17, 8))
        for ax, img, title in zip(axes, (rgb_before, rgb_after), ("Original coastal land", "Constructed landward plain and sea outlets")):
            ax.imshow(img, extent=extent_km, origin="upper")
            ax.set_xlim(cx_km-half_size, cx_km+half_size)
            ax.set_ylim(cz_km+half_size, cz_km-half_size)
            ax.set_title(title)
        path = output/"landward-before-after-detail.png"
        fig.savefig(path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        filenames.append(str(path))
        if 'fan_apex_xz_m' in metadata:
            apex = np.asarray(metadata['fan_apex_xz_m'])
            fig, axes = plt.subplots(1, 2, figsize=(17, 8))
            axes[0].imshow(rgb_after, extent=extent_km, origin='upper')
            axes[0].contour(base_bed_m, levels=[0.], colors='#888888', linewidths=1., origin='upper', extent=extent_km)
            axes[0].contour(bed_m, levels=[0.], colors='black', linewidths=.8, origin='upper', extent=extent_km)
            axes[0].plot(apex[0]/1000., apex[1]/1000., 'rx', markersize=8)
            axes[0].arrow(apex[0]/1000., apex[1]/1000., axis[0]*2., axis[1]*2., width=.015, color='red', length_includes_head=True)
            axes[0].set_xlim(cx_km-half_size, cx_km+half_size)
            axes[0].set_ylim(cz_km+half_size, cz_km-half_size)
            axes[0].set_title('Actual coastline: black final / grey original; red river axis')
            radius = np.linspace(0., 8000., 801)
            section = apex+radius[:, None]*axis
            rc = (section-origin_xz_m)/spacing_m
            before_profile = map_coordinates(base_bed_m, [rc[:, 1], rc[:, 0]], order=1, mode='nearest')
            after_profile = map_coordinates(bed_m, [rc[:, 1], rc[:, 0]], order=1, mode='nearest')
            axes[1].plot(radius/1000., before_profile, color='grey', label='Original base')
            axes[1].plot(radius/1000., after_profile, color='black', label='Constructed bed')
            axes[1].axhline(0., color='steelblue', linewidth=.8)
            axes[1].set_xlabel('Distance seaward from actual inland apex (km)')
            axes[1].set_ylabel('Bed elevation (m)')
            axes[1].set_title('Upper plain, sea-level crossing and submerged apron')
            axes[1].legend()
            path = output/'actual-coast-and-radial-section.png'
            fig.savefig(path, dpi=170, bbox_inches='tight')
            plt.close(fig)
            filenames.append(str(path))

    return filenames


import argparse
from terrain_pipeline.surface_rivers.metric_stylized_wetland import generate_stylized_wetland, connected_design_water
from tools.verify_fluvial_channel_remobilization import resource_limits


def implementation_hashes():
    import inspect
    return {'generator_sha256': file_sha256(Path(inspect.getfile(generate_stylized_wetland))),
            'scene_tool_sha256': file_sha256(Path(__file__))}


def audit_saved_scene(output):
    output = Path(output)
    archive_hash = file_sha256(output/'scene.npz')
    summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    if archive_hash != summary['scene_archive_sha256']:
        raise ValueError('saved scene archive hash mismatch')
    with np.load(output/'scene.npz', allow_pickle=False) as saved:
        a = {key: saved[key].copy() for key in saved.files if key != 'metadata_json'}
        metadata = json.loads(saved['metadata_json'].item())
    if not metadata['algorithm'].startswith('stylized-river-mouth-landward-plain'):
        raise ValueError('landward scene required')
    if metadata.get('implementation_hashes') != implementation_hashes():
        raise ValueError('saved scene implementation identity differs from current generator/tool; replay requires its recorded sources')
    origin, spacing = np.asarray(metadata['origin_xz_m']), float(metadata['spacing_m'])
    path = a['designed_incoming_path_xz_m']
    cell = np.rint((path[0]-origin)/spacing).astype(int)
    water = connected_design_water(a['bed_m'], a['design_stage_m'], a['channel_mask'], (int(cell[1]), int(cell[0])))
    for key, value in water.items():
        if not np.array_equal(value, a[key]):
            raise ValueError('cold water/depth inconsistency: '+key)
    actual = a['branch_core_masks'] & a['wet_mask'][None, :] & (a['water_depth_m'][None, :]>.1)
    for index, branch in enumerate(a['branch_paths_xz_m']):
        cells = np.rint((branch-origin)/spacing).astype(int)
        labels, _ = label(actual[index], generate_binary_structure(2, 1))
        ids = labels[cells[:, 1], cells[:, 0]]
        if ids[0] == 0 or np.any(ids != ids[0]):
            raise ValueError('cold branch core is not D4 continuous')
    area = spacing*spacing
    delta = a['bed_m']-a['base_bed_m']
    cut, fill, net = float(np.maximum(-delta, 0.).sum()*area), float(np.maximum(delta, 0.).sum()*area), float(delta.sum()*area)
    audit = metadata['audit']
    for key, value in (('cut_bulk_m3', cut), ('fill_bulk_m3', fill), ('net_bulk_m3', net)):
        if not np.isclose(audit[key], value, rtol=1e-12, atol=1e-7):
            raise ValueError('cold construction budget mismatch: '+key)
    support_fill = float(a['bank_support_added_height_before_channel_cut_m'].sum()*area)
    if not np.isclose(support_fill, audit['bank_support_gross_fill_before_channel_cut_m3'], rtol=1e-12):
        raise ValueError('cold bank support fill mismatch')
    land = a['base_bed_m']>0.
    if not np.array_equal(land, a['original_land_mask']):
        raise ValueError('cold original-land mask mismatch')
    x, z = np.meshgrid(origin[0]+np.arange(delta.shape[1])*spacing, origin[1]+np.arange(delta.shape[0])*spacing)
    mouth = np.asarray(metadata['mouth_xz_m'])
    axis = np.asarray(metadata.get('river_direction_xz', np.array([1., 1.])/np.sqrt(2.)))
    normal = np.array([-axis[1], axis[0]])
    u = (x-mouth[0])*axis[0]+(z-mouth[1])*axis[1]
    v = (x-mouth[0])*normal[0]+(z-mouth[1])*normal[1]
    for transect in audit['branch_transects']:
        slab = np.abs(u-transect['u_m']) <= spacing*.75
        masks = actual & slab[None, :, :]
        counts = masks.sum(axis=(1, 2))
        if counts.tolist() != transect['wet_counts'] or np.any(counts == 0):
            raise ValueError('cold branch transect counts mismatch')
        if transect['u_m'] < 0. and np.any((masks & land[None, :, :]).sum(axis=(1, 2)) == 0):
            raise ValueError('cold landward transect lacks original-land branches')
        medians = [np.median(v[mask]) for mask in masks]
        for i in range(3):
            for j in range(i+1, 3):
                if np.any(masks[i]&masks[j]) or abs(medians[i]-medians[j]) < 3.*spacing:
                    raise ValueError('cold branch transect is not distinct')
    trunk = a['trunk_path_xz_m']
    if not np.array_equal(trunk[0], path[-1]):
        raise ValueError('cold trunk does not start at incoming endpoint')
    trunk_actual = a['trunk_core_mask'] & a['wet_mask'] & (a['water_depth_m']>.1)
    trunk_labels, _ = label(trunk_actual, generate_binary_structure(2, 1))
    trunk_cells = np.rint((trunk-origin)/spacing).astype(int)
    trunk_ids = trunk_labels[trunk_cells[:, 1], trunk_cells[:, 0]]
    if trunk_ids[0] <= 0 or np.any(trunk_ids != trunk_ids[0]):
        raise ValueError('cold trunk positive-depth core is not D4 continuous')
    for i, station in enumerate(a['branch_junction_station_m']):
        for key in ('bed', 'stage'):
            parent_value = np.interp(station, a['trunk_station_m'], a['trunk_profile_'+key+'_m'])
            if not np.isclose(parent_value, a['branch_profile_'+key+'_m'][i, 0], atol=1e-7, rtol=0.):
                raise ValueError('cold junction profile mismatch: '+key)
        parent_position = np.array([np.interp(station, a['trunk_station_m'], trunk[:, axis]) for axis in range(2)])
        if not np.allclose(parent_position, a['branch_paths_xz_m'][i, 0], atol=1e-7, rtol=0.):
            raise ValueError('cold junction position mismatch')
        cells = np.rint((a['branch_paths_xz_m'][i, 0]-origin)/spacing).astype(int)
        if not land[cells[1], cells[0]]:
            raise ValueError('cold junction is not original land')
    from scipy.ndimage import distance_transform_edt
    open_sea_distance = distance_transform_edt(~(a['connected_ocean_mask'] & ~a['channel_mask']))*spacing
    endpoints = np.rint((a['branch_paths_xz_m'][:, -1]-origin)/spacing).astype(int)
    distances = open_sea_distance[endpoints[:, 1], endpoints[:, 0]]
    if np.any(distances > 100.) or distances.tolist() != audit['branch_terminal_open_sea_distance_m']:
        raise ValueError('cold terminal open-sea access mismatch')
    q = a['incoming_q_m3_s']
    if not (np.allclose(a['trunk_reach_q_m3_s'][:, 0], q)
            and np.allclose(a['trunk_reach_q_m3_s'][:, 0], a['branch_q_m3_s'][:, 0]+a['trunk_reach_q_m3_s'][:, 1])
            and np.allclose(a['trunk_reach_q_m3_s'][:, 1], a['branch_q_m3_s'][:, 1:].sum(axis=1))):
        raise ValueError('cold junction discharge allocation mismatch')
    changed = land & (u >= -2200.) & (u <= 0.) & (np.abs(v)>50.) & (np.abs(delta)>.1)
    if not np.array_equal(changed, a['landward_off_old_strip_changed_mask']):
        raise ValueError('cold original-land change mask mismatch')
    for key, mask in (('original_land_off_old_strip_changed_area_m2', changed),
                      ('original_land_off_old_strip_wet_area_m2', changed&a['wet_mask']),
                      ('original_land_off_old_strip_dry_area_m2', changed&~a['wet_mask'])):
        if audit[key] != float(mask.sum()*area):
            raise ValueError('cold original-land area mismatch: '+key)
    for name, reach in (('retained', u<=-4500.), ('transition', (u>-4500.)&(u<-2200.)), ('plain_approach', u>=-2200.)):
        depth = float(np.max(a['water_depth_m'][reach&a['main_section_mask']], initial=0.))
        if depth != audit['main_wet_depth_max_by_reach_m'][name] or depth > 3.1:
            raise ValueError('cold supported main-channel depth mismatch: '+name)
    for source, digest in metadata['input_hashes'].items():
        if file_sha256(Path(source)) != digest:
            raise ValueError('cold source hash changed: '+source)
    baseline = Path(metadata['baseline_scene02_path'])
    with np.load(baseline) as prior:
        retained = a['retained_upstream_raster_mask']
        if not np.array_equal(prior['base_bed_m'], a['base_bed_m']) or not np.array_equal(prior['bed_m'][retained], a['bed_m'][retained]):
            raise ValueError('cold scene02 base or retained upstream channel core changed')
    replay = generate_stylized_wetland(a['base_bed_m'], origin, spacing, a['old_incoming_path_xz_m'], a['old_incoming_bed_m'],
                                      mouth, a['incoming_q_m3_s'], seed=metadata['seed'], landward_plain=True)
    for key, value in replay['arrays'].items():
        if not np.array_equal(value, a[key]):
            raise ValueError('cold deterministic scene replay mismatch: '+key)
    return {'scene_archive_sha256': archive_hash, 'water_depth_surface_exact': True, 'three_branch_cores_D4': True, 'original_land_areas_recomputed': True,
            'construction_cut_fill_recomputed': True, 'scene02_base_and_upstream_channel_core_exact': True,
            'all_replayed_arrays_exact': True, 'cut_bulk_m3': cut, 'fill_bulk_m3': fill,
            'bank_support_gross_fill_before_channel_cut_m3': support_fill,
            'main_wet_depth_max_by_reach_m': audit['main_wet_depth_max_by_reach_m'],
            'budget_residual_m3': fill-cut-net}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--landward-plain', action='store_true')
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()

    resource_limits()
    if args.audit:
        cold = audit_saved_scene(args.output)
        (args.output/'cold-audit.json').write_text(json.dumps(cold, indent=2), encoding='utf-8')
        print(json.dumps(cold, indent=2))
        return

    s = load_scene_inputs(args.root)
    baseline = args.root/'.scratch/hydrological-planning-domain/stylized-mouth-16km-20261016-02/scene.npz'
    if args.landward_plain:
        with np.load(baseline) as old:
            if not np.array_equal(old['base_bed_m'], s['base_bed_m']):
                raise ValueError('scene02 baseline base differs from reconstructed inputs')
        s['input_hashes'][str(baseline.resolve())] = file_sha256(baseline)

    for p in list(s['input_hashes']) + list(s['accepted_bed_source_hashes']):
        pth = Path(p)
        expected = s['input_hashes'].get(p) if isinstance(s['input_hashes'], dict) else None
        if expected is None and isinstance(s['accepted_bed_source_hashes'], dict):
            expected = s['accepted_bed_source_hashes'].get(p)
        if expected is not None and file_sha256(pth) != expected:
            raise ValueError(f'input hash mismatch: {pth}')

    r = generate_stylized_wetland(
        s['base_bed_m'],
        s['origin_xz_m'],
        s['spacing_m'],
        s['incoming_path_xz_m'],
        s['incoming_bed_m'],
        s['mouth_xz_m'],
        s['incoming_q_m3_s'],
        landward_plain=args.landward_plain,
    )

    arrays = dict(r['arrays'])
    arrays['raw_td_sample_m'] = s['raw_td_sample_m']
    arrays['macro_bed_m'] = s['macro_bed_m']
    arrays['td_residual_m'] = s['td_residual_m']
    arrays['q_step_start_s'] = s['q_step_start_s']
    arrays['q_step_end_s'] = s['q_step_end_s']

    metadata = dict(r['metadata'])
    if args.landward_plain:
        metadata['baseline_scene02_path'] = str(baseline.resolve())
    metadata.update({
        'implementation_hashes': implementation_hashes(),
        'origin_xz_m': list(s['origin_xz_m']),
        'spacing_m': float(s['spacing_m']),
        'mouth_xz_m': list(s['mouth_xz_m']),
        'shape_zx': list(s['base_bed_m'].shape),
        'scene_size_xz_m': [16000, 16000],
        'plan_identity': s['plan_identity'],
        'input_hashes': s['input_hashes'],
        'accepted_bed_source_hashes': s['accepted_bed_source_hashes'],
        'audit': r['audit'],
        'base_formula': 'continuous frozen macro + 0.35*(original TD - Gaussian500m TD)',
        'oldbed_policy': ('saved profile retained before u=-4500m; declared supported transition to new plain by u=-2200m; no old trunk below u=-1800m'
                          if args.landward_plain else 'saved actual incoming longitudinal bed anchors widened100m construction; narrow8m section not resolved'),
        'material_policy': 'explicit construction cut/fill relative to saved base; no inferred upstream sediment',
    })
    all_hashes = dict(s['input_hashes'], **s['accepted_bed_source_hashes'])
    after_hashes = {path: file_sha256(Path(path)) for path in all_hashes}
    if after_hashes != all_hashes:
        raise ValueError('source changed during construction')
    metadata['source_hashes_after'] = after_hashes

    args.output.mkdir(parents=True, exist_ok=False)
    import inspect
    import shutil
    implementation_dir = args.output/'implementation'
    implementation_dir.mkdir()
    for source in (Path(inspect.getfile(generate_stylized_wetland)), Path(__file__)):
        shutil.copy2(source, implementation_dir/source.name)

    arrays['metadata_json'] = np.array(json.dumps(metadata, allow_nan=False))
    np.savez_compressed(args.output / 'scene.npz', **arrays)

    npz_path = args.output / 'scene.npz'
    summary = dict(metadata)
    summary['scene_archive_sha256'] = file_sha256(npz_path)

    q = np.asarray(s['incoming_q_m3_s'])
    summary['incoming_Q_m3_s'] = {
        'min': float(q.min()),
        'mean': float(q.mean()),
        'max': float(q.max()),
    }

    wet_mask = np.asarray(arrays['wet_mask'])
    platform_weight = np.asarray(arrays['platform_weight'])
    summary['water_area_m2'] = int(wet_mask.sum()) * 400.0
    summary['wetland_dry_area_m2'] = int(((platform_weight > 0.5) & ~wet_mask).sum()) * 400.0

    summary['figures'] = render_saved_scene(args.output)

    (args.output / 'summary.json').write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8'
    )

    print(json.dumps({
        'output': str(args.output),
        'audit': r['audit'],
        'Qstats': summary['incoming_Q_m3_s'],
    }, allow_nan=False))


if __name__ == '__main__':
    main()

