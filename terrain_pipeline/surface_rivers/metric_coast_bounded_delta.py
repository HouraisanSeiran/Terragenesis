"""Explicit coastal construction with channels terminating at first open sea."""
from __future__ import annotations

import copy
import json
import numpy as np
from scipy.ndimage import binary_propagation
from scipy.spatial import cKDTree

from .metric_stylized_wetland import _river_fan_fields
from terrain_pipeline.channel_geometry import channel_organized_relief, construct_mouth_transitions, derived_seed, natural_distributary_geometry, natural_secondary


def open_marine_mask(bed_m):
    below = np.asarray(bed_m) < 0.
    seeds = np.zeros_like(below)
    seeds[[0, -1], :] = below[[0, -1], :]
    seeds[:, [0, -1]] = below[:, [0, -1]]
    return binary_propagation(seeds, mask=below)


def path_station(path):
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]


def station_on_path(path, point):
    segments = np.diff(path, axis=0)
    fraction = np.clip(np.sum((point-path[:-1])*segments, axis=1)/np.sum(segments*segments, axis=1), 0., 1.)
    projected = path[:-1]+fraction[:, None]*segments
    index = np.argmin(np.linalg.norm(projected-point, axis=1))
    return float(path_station(path)[index]+fraction[index]*np.linalg.norm(segments[index]))


def sample_path(path, station, samples):
    return np.column_stack([np.interp(samples, station, path[:, axis]) for axis in range(2)])


def truncate_at_first_marine(path, marine, origin, spacing, *, sample_count=1201, terminal_inside_cell=False):
    """Stop just inside the first marine raster cell, never at a later coast."""
    path = np.asarray(path, dtype=float)
    station = path_station(path)
    if station[-1] <= 0. or np.any(np.diff(station) <= 0.):
        raise ValueError("path must have distinct consecutive points")
    dense_s = np.linspace(0., station[-1], int(np.ceil(station[-1]/(spacing/4.)))+1)
    def in_sea(s):
        points = sample_path(path, station, np.atleast_1d(s))
        cells = np.floor((points-origin)/spacing+.5).astype(int)
        if (np.any(cells < 0) or np.any(cells[:, 0] >= marine.shape[1])
                or np.any(cells[:, 1] >= marine.shape[0])):
            raise ValueError("candidate path lies outside scene")
        return marine[cells[:, 1], cells[:, 0]]
    hits = np.flatnonzero(in_sea(dense_s))
    if not len(hits) or hits[0] == 0:
        raise ValueError("branch must begin on land and reach open marine water")
    lo, hi = dense_s[hits[0]-1], dense_s[hits[0]]
    for _ in range(40):
        mid = (lo+hi)/2.
        if in_sea(mid)[0]:
            hi = mid
        else:
            lo = mid
    final_s = np.linspace(0., hi, sample_count)
    if terminal_inside_cell:
        first_point = sample_path(path, station, [hi])[0]
        first_cell = np.floor((first_point-origin)/spacing+.5).astype(int)
        probes = np.linspace(hi, min(station[-1], hi+3.*spacing), 129)
        probe_cells = np.floor((sample_path(path, station, probes)-origin)/spacing+.5).astype(int)
        changed = np.flatnonzero(np.any(probe_cells != first_cell, axis=1))
        end = probes[changed[0]] if len(changed) else probes[-1]
        final_s[-1] = .5*(hi+end)
    return sample_path(path, station, final_s), final_s


def carve_section(bed, origin, spacing, path, profile, stage, widths,
                  marine, *, allow_fill=False, irregular=True):
    """Variable asymmetric banks, clipped at both endpoint tangent planes."""
    bed = np.asarray(bed, dtype=float)
    path = np.asarray(path, dtype=float)
    zz, xx = np.indices(bed.shape)
    points = np.stack([origin[0]+xx*spacing, origin[1]+zz*spacing], axis=-1)
    _, nearest = cKDTree(path).query(points.reshape(-1, 2), workers=1)
    nearest = nearest.reshape(bed.shape)
    tangent = np.gradient(path, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    offset = points-path[nearest]
    signed = offset[..., 0]*(-tangent[nearest, 1])+offset[..., 1]*tangent[nearest, 0]
    station = path_station(path)
    width = np.broadcast_to(widths, (len(path),)).copy()
    if irregular:
        width *= 1.+.10*np.sin(station/310.)+.055*np.sin(station/137.+.7)
        asymmetry = .12*np.sin(station/470.+.3)
    else:
        asymmetry = np.zeros(len(path))
    half = .5*width[nearest]*(1.+np.sign(signed)*asymmetry[nearest])
    weight = np.clip((1.-np.abs(signed)/half)/.4, 0., 1.)
    # Nearest-terminal disks otherwise carve far beyond the pressure boundary.
    along_start = (points-path[0]) @ tangent[0]
    along_end = (points-path[-1]) @ tangent[-1]
    active = (along_start >= 0.) & (along_end <= 0.) & ~marine
    weight *= active
    proposal = bed+weight*(np.asarray(profile)[nearest]-bed)
    final = proposal if allow_fill else np.minimum(bed, proposal)
    return {"bed_m": final, "section_mask": weight > 0., "section_core_mask": weight >= .9,
            "section_weight": weight, "stage_m": np.where(weight > 0., np.asarray(stage)[nearest], 0.),
            "width_profile_m": width}


def connected_water(bed, stage, channel, marine, source_cell):
    surface = np.where(marine, 0., np.maximum(stage, bed))
    candidate = (surface > bed) & (channel | marine)
    seeds = marine & candidate
    seeds[source_cell] = candidate[source_cell]
    wet = binary_propagation(seeds, mask=candidate)
    surface = np.where(wet, surface, bed)
    return {"connected_ocean_mask": marine.copy(), "sea_seed_mask": marine.copy(),
            "water_surface_m": surface, "water_depth_m": np.where(wet, surface-bed, 0.), "wet_mask": wet}


def coastal_lowland_relief(prebed, fan):
    """River-aligned ridges and embayments within the constructed low coast."""
    u = fan["u_m"]-fan["parameters"]["apex_u_m"]
    v = fan["v_m"]
    def smooth(value):
        value = np.clip(value, 0., 1.)
        return value*value*(3.-2.*value)
    upstream = smooth((u-650.)/1100.)
    downstream = smooth((7600.-u)/1900.)
    lateral = smooth((4500.-np.abs(v))/(1200.+.12*np.maximum(u, 0.)))
    elevation = 1.-smooth((np.abs(prebed)-3.)/5.)
    envelope = fan["weight"]*upstream*downstream*lateral*elevation
    warped_v = v+180.*np.sin(u/850.)+85.*np.sin(u/310.+v/1500.)
    # Long ridges stay aligned with the river; shorter oblique relief breaks
    # uniform bank strips without introducing cell-scale shoreline roughness.
    ridge = 1.75*np.sin(warped_v/330.+.35*np.sin(u/1700.))
    middle = .95*np.sin(warped_v/165.-u/650.)*np.sin(u/1100.+.6)
    bank = .42*np.sin(warped_v/83.+u/290.)
    embayment = -1.15*(.5+.5*np.sin(warped_v/700.-u/1250.))**3
    return envelope*(ridge+middle+bank+embayment)


def delayed_distributary_geometry(trunk, branches, apex):
    """Extend the common plain before three unequal, angled distributaries."""
    trunk = np.asarray(trunk, dtype=float)
    branches = np.asarray(branches, dtype=float)
    old_station = path_station(trunk)
    old_length = old_station[-1]
    tangent = (trunk[-1]-trunk[-2])
    tangent /= np.linalg.norm(tangent)
    extension = np.linspace(0., 900., 181)[1:, None]*tangent + trunk[-1]
    extended = np.vstack([trunk, extension])
    ext_station = path_station(extended)
    target_station = np.linspace(0., ext_station[-1], len(trunk))
    new_trunk = sample_path(extended, ext_station, target_station)
    new_station = path_station(new_trunk)
    junctions = [float(new_station[len(new_trunk)//2]) if index == 0 else float(new_station[-1])
                 for index in range(len(branches))]
    # Keep the original branch shapes, but attach them to delayed junctions,
    # then apply unequal along-bank scales and signed lateral steering.
    direction = tangent
    normal = np.array([-direction[1], direction[0]])
    out = []
    for index, branch in enumerate(branches):
        old_start = branch[0]
        rel = branch-old_start
        along = rel @ direction
        lateral = rel @ normal
        scale = (1.08, .82, 1.22, .68, .55)[index % 5]
        steering = (.16, -.24, .31, -.38, .44)[index % 5]
        junction = new_trunk[len(new_trunk)//2 if index == 0 else -1]
        out.append(junction + (scale*along)[:, None]*direction +
                   (scale*lateral + steering*np.maximum(along, 0.))[:, None]*normal)
    return new_trunk, np.asarray(out), np.asarray(junctions)


def select_distributary_candidates(flow_m3_s, solid_supply_m3, plain_width_m,
                                  candidates, limits=(2, 5)):
    """Select viable outlets from scored candidates; count is data-dependent."""
    candidates = list(candidates)
    low, high = (int(limits[0]), int(limits[1]))
    if low < 1 or high < low or not candidates:
        raise ValueError("invalid outlet limits or empty candidates")
    if not all(np.isfinite(v) and v >= 0. for v in (flow_m3_s, solid_supply_m3, plain_width_m)):
        raise ValueError("flow, solid supply and plain width must be finite and nonnegative")
    capacity = max(1, int(np.floor(np.sqrt(max(flow_m3_s, 0.)/45.) +
                              np.log1p(max(solid_supply_m3, 0.))/7. +
                              max(plain_width_m, 0.)/1800.)))
    count = min(high, max(low, capacity), len(candidates))
    ranked = sorted(enumerate(candidates), key=lambda item: (-float(item[1].get("score", 0.)), item[0]))
    chosen = [item[1] for item in ranked[:count]]
    return {"selected": chosen, "selected_indices": [item[0] for item in ranked[:count]],
            "count": count, "reason": {"capacity_index": capacity, "limits": [low, high],
            "flow_m3_s": float(flow_m3_s), "solid_supply_m3": float(solid_supply_m3),
            "plain_width_m": float(plain_width_m)}}


def secondary_from_parent_land_prefix(parent_path, marine, origin, spacing, *, offset_m=180.):
    """Create a secondary only from a landward parent prefix before its coast."""
    parent_path = np.asarray(parent_path, dtype=float)
    station = path_station(parent_path)
    dense = np.linspace(0., station[-1], int(np.ceil(station[-1]/(spacing/4.)))+1)
    points = sample_path(parent_path, station, dense)
    cells = np.floor((points-origin)/spacing+.5).astype(int)
    inside = ((cells[:, 0] >= 0) & (cells[:, 0] < marine.shape[1]) &
              (cells[:, 1] >= 0) & (cells[:, 1] < marine.shape[0]))
    hits = np.flatnonzero(inside & marine[cells[:, 1].clip(0, marine.shape[0]-1), cells[:, 0].clip(0, marine.shape[1]-1)])
    if not len(hits):
        return None, {"reason": "no_open_marine_entry"}
    sea_s = dense[hits[0]]
    split_s = .5*sea_s
    split = sample_path(parent_path, station, np.array([split_s]))[0]
    split_cell = np.floor((split-origin)/spacing+.5).astype(int)
    if marine[split_cell[1], split_cell[0]]:
        return None, {"reason": "no_landward_parent_prefix"}
    end = sample_path(parent_path, station, np.array([sea_s]))[0]
    tangent = sample_path(parent_path, station, np.array([sea_s, max(split_s, sea_s-spacing)]))
    direction = tangent[0]-tangent[1]; direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    length = np.linalg.norm(end-split)
    # Preserve the actual parent prefix so the secondary reaches the same
    # first marine station, then continue beyond it along the parent tangent.
    half = len(parent_path)//2 + 1
    t_prefix = np.linspace(0., 1., half)
    prefix = split + t_prefix[:, None]*(end-split)
    prefix += (offset_m*np.sin(np.pi*t_prefix))[:, None]*normal
    extension = end + (np.linspace(0., length, len(parent_path)-half+1)[1:, None])*direction
    secondary = np.vstack([prefix, extension])
    return secondary, {"reason": "selected", "parent_split_station_m": float(split_s), "parent_first_marine_station_m": float(sea_s)}


def construct_coast_bounded_scene(source_arrays, source_metadata, *, finite_solid_supply_m3=0.,
                                  construction_mode='legacy', world_seed=20261020):
    """Rebuild the saved pre-cut fan, then replace all constructed channels."""
    if construction_mode not in ('legacy', 'natural'):
        raise ValueError('unknown coastal construction mode')
    natural = construction_mode == 'natural'
    def truncate_candidate(path, marine, origin, spacing, *, sample_count):
        if not natural:
            return truncate_at_first_marine(path, marine, origin, spacing, sample_count=sample_count)
        return truncate_at_first_marine(path, marine, origin, spacing,
            sample_count=sample_count, terminal_inside_cell=True)
    arrays = {key: value.copy() for key, value in source_arrays.items()}
    meta = copy.deepcopy(source_metadata)
    for key in ("trunk_reach_station_bounds_m", "trunk_reach_discharge_fraction", "trunk_reach_q_m3_s",
                "secondary_candidate_rejection_json", "candidate_selection_json"):
        arrays.pop(key, None)
    meta["branching_model"].pop("curvature_amplitude_m", None)
    base = arrays["base_bed_m"]
    origin = np.asarray(meta["origin_xz_m"], dtype=float)
    spacing = float(meta["spacing_m"])
    zz, xx = np.indices(base.shape)
    fan = _river_fan_fields(base, origin[0]+xx*spacing, origin[1]+zz*spacing,
                            arrays["old_incoming_path_xz_m"], np.asarray(meta["mouth_xz_m"]), seed=meta["seed"],
                            nominal_radius_m=7600., curved_side_half_width_m=4500.)
    previous_weight = arrays.get("platform_weight", np.zeros_like(base)).copy()
    for key, field in (("fan_radius_m", "radius_m"), ("fan_angle_rad", "angle_rad"),
                       ("fan_outer_radius_m", "outer_radius_m"), ("fan_target_bed_m", "target_bed_m"),
                       ("platform_weight", "weight")):
        arrays[key] = fan[field].copy()
    meta["fan_parameters"] = fan["parameters"]
    prebed = fan["bed_m"]+arrays["bank_support_added_height_before_channel_cut_m"]
    if natural:
        natural_trunk, natural_candidates, natural_junctions = natural_distributary_geometry(
            arrays['trunk_path_xz_m'], world_seed)
        landform_delta, island_bodies = channel_organized_relief(
            prebed, fan, natural_candidates, origin, spacing, world_seed)
    else:
        landform_delta = coastal_lowland_relief(prebed, fan)
    prebed += landform_delta
    marine = open_marine_mask(prebed)
    arrays["pre_channel_bed_m"] = prebed.copy()
    arrays["open_marine_mask"] = marine
    arrays["landform_added_height_m"] = landform_delta
    arrays["landward_platform_weight"] = fan["weight"]*(fan["u_m"] <= 0.)
    retained = arrays["retained_upstream_raster_mask"]
    path = arrays["designed_incoming_path_xz_m"]
    for protected_path in (path, arrays["trunk_path_xz_m"]):
        station = path_station(protected_path)
        samples = sample_path(protected_path, station, np.linspace(0., station[-1], int(np.ceil(station[-1]/(spacing/4.)))+1))
        cells = np.floor((samples-origin)/spacing+.5).astype(int)
        inside = (cells[:, 0] >= 0) & (cells[:, 0] < base.shape[1]) & (cells[:, 1] >= 0) & (cells[:, 1] < base.shape[0])
        cells = cells[inside]
        if marine[cells[:, 1], cells[:, 0]].any():
            raise ValueError("incoming path and trunk must remain landward of frozen open marine water")
    retained_u = float(meta["retained_profile_before_u_m"])
    direction = np.asarray(meta["river_direction_xz"])
    profile_u = (path-np.asarray(meta["mouth_xz_m"])) @ direction
    ramp = np.clip((profile_u-retained_u)/1800., 0., 1.)
    ramp = ramp*ramp*(3.-2.*ramp)
    main_widths = 100.+100.*ramp
    section = carve_section(prebed, origin, spacing, path, arrays["designed_incoming_bed_m"],
                            arrays["designed_incoming_stage_m"], main_widths, marine, allow_fill=True, irregular=False)
    bed, stage = section["bed_m"], section["stage_m"]
    bed[retained] = arrays["bed_m"][retained]
    main_mask = section["section_mask"] | retained
    arrays["main_section_mask"] = main_mask
    arrays["incoming_width_profile_m"] = main_widths
    arrays["trunk_width_m"] = np.array(200.)
    if natural:
        trunk, candidate_paths, delayed_junctions = natural_trunk, natural_candidates, natural_junctions
    else:
        trunk, candidate_paths, delayed_junctions = delayed_distributary_geometry(
            arrays["trunk_path_xz_m"], arrays["branch_paths_xz_m"], np.zeros(2))
    arrays["trunk_path_xz_m"] = trunk.copy()
    # Add two lower-score engineering candidates; selection decides whether
    # their reaches are actually constructed and routed.
    direction = (trunk[-1]-trunk[-2]); direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    extras = []
    for source, scale, steer in ((candidate_paths[0], .72, -.42), (candidate_paths[-1], .58, .48)):
        rel = source-source[0]; along = rel@direction; lateral = rel@normal
        extras.append(source[0]+(scale*along)[:, None]*direction +
                     (scale*lateral+steer*np.maximum(along, 0.))[:, None]*normal)
    if not natural:
        candidate_paths = np.asarray([*candidate_paths, *extras])
        delayed_junctions = np.r_[delayed_junctions, [delayed_junctions[0], delayed_junctions[-1]]]
    primary_valid = []
    primary_rejections = {}
    for index, candidate in enumerate(candidate_paths):
        try:
            truncate_candidate(candidate, marine, origin, spacing, sample_count=len(candidate))
            primary_valid.append(index)
        except ValueError as error:
            primary_rejections[index] = str(error)
    if not primary_valid:
        raise ValueError("no primary candidate reaches frozen open marine water")
    secondary_parent = primary_valid[0]
    if natural:
        secondary, secondary_reason = natural_secondary(
            candidate_paths[secondary_parent], marine, origin, spacing, world_seed)
    else:
        secondary, secondary_reason = secondary_from_parent_land_prefix(
            candidate_paths[secondary_parent], marine, origin, spacing, offset_m=180.)
    parent_q = float(np.asarray(arrays.get("incoming_q_m3_s", [0.])).max())/max(1, len(primary_valid))
    if parent_q < 15. or finite_solid_supply_m3 <= 0.:
        secondary = None
        secondary_reason = {"reason": "insufficient_parent_water_or_finite_solid", "parent_q_m3_s": parent_q,
                            "finite_solid_supply_m3": float(finite_solid_supply_m3)}
    if secondary is None:
        candidate_specs = [{"path": path, "score": 1./(index+1), "parent_index": -1, "level": 0}
                           for index, path in enumerate(candidate_paths)]
        arrays["secondary_candidate_rejection_json"] = np.asarray(json.dumps(secondary_reason))
    else:
        candidate_paths = [*candidate_paths, secondary]
        delayed_junctions = np.r_[delayed_junctions, delayed_junctions[0]]
        candidate_specs = [{"path": path, "score": 1./(index+1), "parent_index": -1, "level": 0}
                           for index, path in enumerate(candidate_paths[:-1])]
        candidate_specs[secondary_parent]["score"] = 3.0
        candidate_specs.append({"path": secondary, "score": 2.0, "parent_index": secondary_parent, "level": 1})
    for index, spec in enumerate(candidate_specs):
        spec["original_id"] = index
        spec["parent_original_id"] = int(spec["parent_index"])
    selection = select_distributary_candidates(
        float(np.asarray(arrays.get("incoming_q_m3_s", [0.])).max()),
        float(finite_solid_supply_m3),
        float(np.ptp(fan["v_m"][(fan["weight"] > .5) & (np.abs(prebed) < 8.)])),
        candidate_specs, limits=(1, min(5, len(candidate_specs))))
    selected_indices = selection["selected_indices"]
    candidates = [candidate_paths[index] for index in selected_indices]
    delayed_junctions = delayed_junctions[selected_indices]
    selected_specs = [candidate_specs[index] for index in selected_indices]
    valid_candidates, valid_specs = [], []
    rejected = []
    for candidate, spec in zip(candidates, selected_specs):
        try:
            truncate_candidate(candidate, marine, origin, spacing, sample_count=len(candidate))
            valid_candidates.append(candidate); valid_specs.append(spec)
        except ValueError as error:
            rejected.append({"original_id": spec["original_id"], "level": int(spec.get("level", 0)), "reason": str(error)})
    if not valid_candidates:
        raise ValueError("all selected distributary candidates rejected")
    candidates, selected_specs = valid_candidates, valid_specs
    original_ids = [next(i for i, spec in enumerate(candidate_specs) if spec is chosen) for chosen in selected_specs]
    for spec in selected_specs:
        parent = int(spec.get("parent_index", -1))
        if parent >= 0:
            if parent not in original_ids:
                raise ValueError("selected secondary has no selected parent")
            spec["parent_index"] = original_ids.index(parent)
    rejection_by_id = {record["original_id"]: record["reason"] for record in rejected}
    candidate_records = []
    for spec in candidate_specs:
        original_id = spec["original_id"]
        selected = original_id in original_ids
        selected_index = original_ids.index(original_id) if selected else None
        reason = ("selected" if selected else rejection_by_id.get(original_id,
            primary_rejections.get(original_id, "not_selected_by_capacity_and_score")))
        candidate_records.append({"original_id": original_id, "score": float(spec["score"]),
            "level": int(spec["level"]), "parent_original_id": spec["parent_original_id"],
            "selected": selected, "reason": reason, "selected_terminal_index": selected_index,
            "parent_selected_index": int(spec["parent_index"]) if selected else None})
    if secondary is None:
        candidate_records.append({"original_id": len(candidate_specs), "score": 2., "level": 1,
            "parent_original_id": int(secondary_parent), "selected": False,
            "reason": secondary_reason["reason"], "selected_terminal_index": None,
            "parent_selected_index": None})
    arrays["candidate_selection_json"] = np.asarray(json.dumps(candidate_records))
    paths, stations = zip(*(truncate_candidate(p, marine, origin, spacing,
                               sample_count=len(p)) for p in candidates))
    arrays["candidate_rejections_json"] = np.asarray(json.dumps(rejected))
    paths, stations = np.asarray(paths), np.asarray(stations)
    for p in paths:
        cells = np.floor((p-origin)/spacing+.5).astype(int)
        cells[:, 0] = np.clip(cells[:, 0], 0, base.shape[1]-1)
        cells[:, 1] = np.clip(cells[:, 1], 0, base.shape[0]-1)
        hits = marine[cells[:, 1], cells[:, 0]]
        if hits[:-1].any() or not hits[-1]:
            raise ValueError("resampled branch must enter frozen marine water only at its terminal")
    widths_all = np.array([170., 145., 120., 105., 90.])
    widths = widths_all[:len(candidates)]
    for index, spec in enumerate(selected_specs):
        if spec.get("parent_index", -1) >= 0:
            widths[index] = .6*widths[spec["parent_index"]]
    masks, cores, cuts, width_profiles, profiles, stage_profiles = [], [], [], [], [], []
    trunk_station = path_station(trunk)
    junction_s = np.full(len(paths), np.nan)
    def global_start(index):
        if np.isfinite(junction_s[index]): return junction_s[index]
        parent = int(selected_specs[index].get("parent_index", -1))
        junction_s[index] = (station_on_path(trunk, paths[index, 0]) if parent < 0 else
            global_start(parent)+station_on_path(paths[parent], paths[index, 0]))
        return junction_s[index]
    for index in range(len(paths)): global_start(index)
    mouth_cut = np.zeros_like(prebed)
    if natural:
        new_prebed, mouth_support = construct_mouth_transitions(prebed, marine, candidates,
            paths, junction_s, widths, arrays['designed_incoming_bed_m'][-1], origin, spacing)
        mouth_cut = prebed-new_prebed
        bed -= mouth_cut
        prebed = new_prebed
        arrays['pre_channel_bed_m'] = prebed.copy()
        arrays['shore_mouth_initial_cut_depth_m'] = mouth_cut
        arrays['shore_mouth_initial_cut_mask'] = mouth_support
    for index, (p, width) in enumerate(zip([trunk, *paths], [200., *widths])):
        ps = path_station(p)+(0. if index == 0 else junction_s[index-1])
        profile = float(arrays["designed_incoming_bed_m"][-1])-.00038*ps
        heads = float(arrays["designed_incoming_stage_m"][-1])*np.maximum(1.-ps/2400., 0.)**2
        part = carve_section(bed, origin, spacing, p, profile, heads, width, marine)
        cuts.append(np.maximum(bed-part["bed_m"], 0.))
        bed = part["bed_m"]
        stage = np.maximum(stage, part["stage_m"])
        masks.append(part["section_mask"])
        cores.append(part["section_core_mask"])
        width_profiles.append(part["width_profile_m"])
        profiles.append(profile)
        stage_profiles.append(heads)
    bed[retained] = source_arrays["bed_m"][retained]
    channel = main_mask | np.logical_or.reduce(masks)
    cells = np.floor((path-origin)/spacing+.5).astype(int)
    inside = (cells[:, 0] >= 0) & (cells[:, 0] < base.shape[1]) & (cells[:, 1] >= 0) & (cells[:, 1] < base.shape[0])
    cell = cells[np.flatnonzero(inside)[0]]
    water = connected_water(bed, stage, channel, marine, (cell[1], cell[0]))
    footprint = arrays["construction_footprint_mask"] | (bed != base) | (prebed != base)
    delta = bed-base
    area = spacing**2
    audit = {"cut_bulk_m3": float(np.maximum(-delta, 0.).sum()*area),
             "fill_bulk_m3": float(np.maximum(delta, 0.).sum()*area), "net_bulk_m3": float(delta.sum()*area),
             "branch_first_marine_station_m": stations[:, -1].tolist(),
             "marine_channel_cut_bulk_m3": float(np.maximum(prebed-bed, 0.)[marine].sum()*area),
             "retained_upstream_channel_core_exact": bool(np.array_equal(bed[retained], arrays["bed_m"][retained])),
             "outside_footprint_exact": bool(np.array_equal(bed[~footprint], base[~footprint]))}
    audit["fan_envelope"] = {"previous_effective_area_m2": float(np.count_nonzero(previous_weight > .5)*area),
        "effective_area_m2": float(np.count_nonzero(fan["weight"] > .5)*area),
        "added_effective_area_m2": float(np.count_nonzero((fan["weight"] > .5) & (previous_weight <= .5))*area)}
    if natural:
        audit['shore_mouth_initial_construction'] = dict(cut_bulk_m3=float(mouth_cut.sum()*area),
            support_area_m2=float(np.count_nonzero(mouth_cut)*area), transition_length_m=650.,
            width_policy='nominal channel width with trapezoidal bank taper; finite endpoint tangent planes',
            pressure_boundary='first open-marine cell of explicitly constructed nearshore bed, fixed sea head; nearshore sea not dynamically simulated',
            accounting='initial bulk excavation included in construction cut; never charged to annual natural sediment')
    audit["lowland_relief_construction"] = {
        "cut_bulk_m3": float(np.maximum(-landform_delta, 0.).sum()*area),
        "fill_bulk_m3": float(np.maximum(landform_delta, 0.).sum()*area),
        "net_bulk_m3": float(landform_delta.sum()*area),
        "minimum_height_change_m": float(landform_delta.min()),
        "maximum_height_change_m": float(landform_delta.max()),
        "changed_above_point_one_m_area_m2": float(np.count_nonzero(np.abs(landform_delta) > .1)*area),
        "raised_above_sea_area_m2": float(np.count_nonzero((prebed > 0.) & (prebed-landform_delta <= 0.))*area),
        "lowered_below_sea_area_m2": float(np.count_nonzero((prebed <= 0.) & (prebed-landform_delta > 0.))*area),
    }
    if audit["marine_channel_cut_bulk_m3"] != 0. or not np.array_equal(bed[marine], prebed[marine]):
        raise ValueError("channel construction changed frozen marine terrain")
    if not audit["retained_upstream_channel_core_exact"] or not audit["outside_footprint_exact"]:
        raise ValueError("construction changed retained upstream or exterior terrain")
    arrays.update(water)
    arrays.update(bed_m=bed, design_stage_m=np.where(marine, 0., stage), channel_mask=channel,
                  branch_candidate_paths_xz_m=candidates, branch_paths_xz_m=paths,
                  branch_station_m=stations+junction_s[:, None], branch_actual_length_m=stations[:, -1],
                  trunk_station_m=trunk_station, branch_junction_station_m=junction_s,
                  branch_first_marine_station_m=stations[:, -1], branch_width_m=widths,
                  trunk_section_mask=masks[0], trunk_core_mask=cores[0],
                  branch_section_masks=np.asarray(masks[1:]), branch_core_masks=np.asarray(cores[1:]),
                  branch_cut_depth_m=np.asarray(cuts[1:]), trunk_cut_depth_m=cuts[0],
                  branch_width_profile_m=np.asarray(width_profiles[1:]), main_section_mask=main_mask,
                  trunk_width_profile_m=width_profiles[0], trunk_profile_bed_m=profiles[0],
                  trunk_profile_stage_m=stage_profiles[0], branch_profile_bed_m=np.asarray(profiles[1:]),
                  branch_profile_stage_m=np.asarray(stage_profiles[1:]),
                  construction_footprint_mask=footprint,
                  old_branch_groove_removed_mask=(source_arrays["branch_cut_depth_m"].sum(axis=0)>0.) & ~channel)
    arrays["terminal_parent_index"] = np.asarray([int(spec.get("parent_index", -1)) for spec in selected_specs], dtype=int)
    arrays["terminal_level"] = np.asarray([int(spec.get("level", 0)) for spec in selected_specs], dtype=int)
    arrays["terminal_flow_fraction"] = widths/widths.sum()
    arrays["terminal_solid_fraction"] = widths/widths.sum()
    arrays["branch_share"] = widths/widths.sum()
    arrays["branch_q_m3_s"] = np.asarray(arrays.get("incoming_q_m3_s", [0.]))[..., None]*arrays["branch_share"]
    arrays["branch_parent_index"] = arrays["terminal_parent_index"].copy()
    meta["branch_shares"] = arrays["branch_share"].tolist()
    meta.update(algorithm="coast-bounded-explicit-delta-v3", incoming_width_m=200., branch_width_m=widths.tolist(),
                marine_policy="D4 boundary-connected below-zero pre-channel bed; fixed sea head; no marine cut or sediment storage",
                bank_width_policy="nominal Manning widths; variable asymmetric constructed bank sections",
                construction="all cut and fill explicit; no natural sediment finances construction")
    meta["branching_model"]["trunk_width_m"] = 200.
    meta["branching_model"]["common_plain_trunk_length_m"] = float(trunk_station[-1])
    meta["branching_model"]["branch_length_m"] = stations[:, -1].tolist()
    meta["branching_model"]["selected_terminal_count"] = int(len(paths))
    meta["branching_model"]["selection_reason"] = selection["reason"]
    meta["branching_model"]["terminal_parent_index"] = arrays["terminal_parent_index"].tolist()
    meta["branching_model"]["terminal_level"] = arrays["terminal_level"].tolist()
    meta["branching_model"]["terminal_flow_fraction"] = (widths/widths.sum()).tolist()
    meta["branching_model"]["terminal_solid_fraction"] = (widths/widths.sum()).tolist()
    meta["branching_model"]["candidate_count"] = len(candidate_records)
    meta["branching_model"]["candidate_selection"] = candidate_records
    meta["branching_model"]["branch_junction_arc_station_m"] = junction_s.tolist()
    meta["branching_model"]["trunk_length_m"] = float(trunk_station[-1])
    meta["branching_model"]["path_count_including_trunk"] = len(paths)+1
    meta["branching_model"]["branch_start_u_m"] = ((paths[:, 0]-np.asarray(meta["mouth_xz_m"])) @ np.asarray(meta["river_direction_xz"])).tolist()
    endpoint_offset = paths[:, -1]-trunk[0]
    normal = np.array([-direction[1], direction[0]])
    meta["branch_outer_radii_m"] = np.linalg.norm(endpoint_offset, axis=1).tolist()
    meta["branch_final_angles_degrees"] = np.rad2deg(np.arctan2(endpoint_offset @ normal, endpoint_offset @ direction)).tolist()
    meta["landform_parameters"] = {
        "construction_envelope": "saved fan weight times smooth longitudinal, lateral and low-elevation tapers",
        "downstream_start_m": 650., "upstream_taper_m": 1100., "downstream_end_m": 7600.,
        "downstream_taper_m": 1900., "lateral_outer_half_width_m": 4500.,
        "lateral_taper_base_m": 1000., "lateral_taper_opening_ratio": .10,
        "elevation_full_relief_abs_bed_m": 3., "elevation_zero_relief_abs_bed_m": 8.,
        "height_amplitudes_m": [1.75, .95, .42, -1.15],
        "cross_river_scales_m": [330., 165., 83., 700.],
        "longitudinal_scales_m": [1700., 650., 290., 1250.],
        "coordinate_warp_amplitudes_m": [180., 85.], "coordinate_warp_u_scales_m": [850., 310.],
        "semantics": "explicit construction of river-aligned ridges, oblique bank relief and shallow embayments",
    }
    meta["bank_section_parameters"] = {"width_relative_amplitudes": [.10, .055],
        "width_station_scales_m": [310., 137.], "asymmetry_amplitude": .12,
        "asymmetry_station_scale_m": 470., "flat_bottom_width_fraction": .6,
        "incoming_transition_length_m": 1800., "incoming_boundary_width_m": 100.}
    if natural:
        meta.update(algorithm='coast-bounded-flow-aligned-construction-v1',
            construction_mode='natural', world_seed=int(world_seed),
            natural_geometry_seeds={purpose: derived_seed(world_seed, purpose) for purpose in (
                'delta/branch-geometry/v1', 'delta/secondary-geometry/v1', 'delta/island-relief/v1')})
        meta['landform_parameters'] = dict(semantics='Curved interdistributary lobes between adjacent channels with unequal separation-controlled width and asymmetric shallow aprons; explicit construction, not emergent morphodynamics',
            island_bodies=island_bodies)
        meta['geometry_limitations'] = 'Prescribed tree and fan on inherited terrain; no avulsion, tidal creeks, topology evolution or calibrated Wax Lake reconstruction'
        meta['marine_policy'] = 'D4 boundary-connected pre-channel sea; explicit finite initial mouth excavation, then frozen sea head and bed; annual sea bed unchanged and sea-side sediment directly exported'
        meta['shore_mouth_parameters'] = audit['shore_mouth_initial_construction']
    return {"arrays": arrays, "metadata": meta, "audit": audit}
