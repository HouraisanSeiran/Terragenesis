"""Finite coastal active layer, driven by connected tidal stages and wave rays.

This is a reduced morphological experiment, not a momentum/Exner solver.
Every face transfer debits its donor. Bedrock below the finite active layer is
immobile; construction and geological sediment are separate from river supply.
"""
from dataclasses import asdict, dataclass
import heapq

import numpy as np
from scipy.ndimage import binary_propagation, distance_transform_edt, gaussian_filter
from scipy.spatial import cKDTree

from .metric_dynamic_feedback import normal_depth


def flowing_reach_stage(bed_profile_m, station_m, width_m, discharge_m3_s, sea_level_m):
    """Rectangular Manning/critical-depth control on a preserved reach.

    A positive bed grade admits the existing normal-depth relation. Flat or
    adverse profiles use critical free-outfall depth instead of inventing a
    positive friction slope. The upstream envelope is a reduced stage closure,
    not a gradually varied flow integration.
    """
    profile = np.asarray(bed_profile_m, float)
    station = np.asarray(station_m, float)
    widths = np.broadcast_to(np.asarray(width_m, float), profile.shape)
    if (profile.ndim != 1 or len(profile) < 2 or station.shape != profile.shape
            or not np.isfinite([discharge_m3_s, sea_level_m]).all()
            or discharge_m3_s < 0. or not np.isfinite(profile).all()
            or not np.isfinite(widths).all() or np.any(widths <= 0.)
            or not np.isfinite(station).all() or np.any(np.diff(station) <= 0.)):
        raise ValueError("invalid flowing reach")
    if discharge_m3_s == 0.:
        return np.maximum(profile, sea_level_m), np.zeros_like(profile)
    critical = (discharge_m3_s**2/(9.81*widths**2))**(1./3.)
    grade = float((profile[0]-profile[-1])/(station[-1]-station[0]))
    normal = np.array([normal_depth(discharge_m3_s, width, grade) for width in widths]) if grade > 0. else critical
    control = np.maximum(critical, normal)
    stage = np.maximum(profile+control, sea_level_m)
    stage = np.maximum.accumulate(stage[::-1])[::-1]
    return stage, control


def channel_water_stage(bed, paths, section_masks, widths, flows, origin, spacing, sea_level, outlet_stages=None):
    """Project flowing stage onto existing sections only, without bed carving."""
    surface = np.full_like(bed, np.nan, dtype=float)
    diagnostics = []
    outlet_stages = [sea_level]*len(paths) if outlet_stages is None else outlet_stages
    for path, section, width, flow, outlet in zip(paths, section_masks, widths, flows, outlet_stages):
        path = np.asarray(path, float)
        indices = np.floor((path-origin)/spacing+.5).astype(int)
        inside = ((indices[:, 0] >= 0) & (indices[:, 0] < bed.shape[1])
            & (indices[:, 1] >= 0) & (indices[:, 1] < bed.shape[0]))
        path = path[inside]
        indices = indices[inside]
        if len(path) < 2:
            raise ValueError("reach has no in-domain segment")
        width = np.broadcast_to(np.asarray(width, float), (len(inside),))[inside]
        profile = bed[indices[:, 1], indices[:, 0]]
        station = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        flow_profile = np.broadcast_to(np.asarray(flow, float), (len(inside),))[inside]
        stage = np.empty_like(profile)
        control = np.empty_like(profile)
        # Saved branch junctions define piecewise constant discharge reaches.
        breaks = np.r_[0, np.flatnonzero(np.diff(flow_profile) != 0.)+1, len(profile)]
        for lo, hi in zip(breaks[:-1], breaks[1:]):
            if hi-lo == 1:
                segment_critical = (flow_profile[lo]**2/(9.81*width[lo]**2))**(1./3.)
                stage[lo] = max(profile[lo]+segment_critical, sea_level, outlet)
                control[lo] = segment_critical
            else:
                stage[lo:hi], control[lo:hi] = flowing_reach_stage(profile[lo:hi], station[lo:hi],
                    width[lo:hi], float(flow_profile[lo]), max(sea_level, outlet))
        stage = np.maximum.accumulate(stage[::-1])[::-1]
        section = section.copy()
        # D4 supercover of the existing centerline, including the fixed outfall
        # cell that marine-clipped carving masks deliberately exclude.
        for first, last in zip(indices[:-1], indices[1:]):
            c, r = first
            end_c, end_r = last
            section[r, c] = True
            while c != end_c or r != end_r:
                if c != end_c:
                    c += int(np.sign(end_c-c))
                    section[r, c] = True
                if r != end_r:
                    r += int(np.sign(end_r-r))
                    section[r, c] = True
        rr, cc = np.nonzero(section)
        nearest = cKDTree(path).query(origin+np.column_stack([cc, rr])*spacing, workers=1)[1]
        critical = (flow_profile[nearest]**2/(9.81*width[nearest]**2))**(1./3.)
        candidate = np.maximum(stage[nearest], bed[rr, cc]+critical)
        wet = (candidate > bed[rr, cc]) & (flow_profile[nearest] > 0.)
        surface[rr[wet], cc[wet]] = np.fmax(surface[rr[wet], cc[wet]], candidate[wet])
        diagnostics.append({"q_m3_s": float(flow_profile[-1]), "source_q_m3_s": float(flow_profile[0]),
            "flow_break_sample_indices": breaks.tolist(), "terminal_control_depth_m": float(control[-1]),
            "source_stage_m": float(stage[0]),
            "terminal_stage_m": float(stage[-1]), "terminal_bed_m": float(profile[-1]),
            "terminal_critical_depth_m": float((flow_profile[-1]**2/(9.81*width[-1]**2))**(1./3.)),
            "mean_bed_grade": float((profile[0]-profile[-1])/station[-1])})
    return surface, diagnostics


def foreshore_outflow(bed, sea, river_surface, terminal_cells, flows, widths, spacing, *, max_distance_m=1600.):
    """Bounded D4 minimax-sill surface drainage; never modifies the bed.

    A shortest-distance tie break selects among equal sill paths. Rectangular
    critical depth uses the actual single-cell raster width, consistent with
    the saved water prism volume. Saved river-mouth width is diagnostic only.
    The water-only stage envelope communicates any required sill head upstream.
    """
    surface = river_surface.copy()
    routes = []
    states = []
    for start, flow, width in zip(terminal_cells, flows, widths):
        start = tuple(map(int, start))
        if flow <= 0.:
            routes.append(np.empty((0, 2), int))
            states.append({"status": "zero_flow", "q_m3_s": float(flow)})
            continue
        if sea[start]:
            routes.append(np.array([start], int))
            states.append({"status": "gate_in_sea", "q_m3_s": float(flow),
                "saved_outlet_width_m": float(width), "effective_raster_width_m": float(width),
                "path_length_m": 0., "maximum_sill_m": float(bed[start]),
                "water_prism_m3": 0., "prism_replacement_time_s": 0.,
                "gate_stage_m": float(river_surface[start]), "sea_contact_cell_zx": list(start),
                "control": "existing river section and marine boundary; no foreshore contraction"})
            continue
        effective_width = spacing
        critical = float((flow**2/(9.81*effective_width**2))**(1./3.))
        queue = [(float(bed[start]), 0., start)]
        best = {start: (float(bed[start]), 0.)}
        parent = {}
        target = None
        while queue:
            sill, distance, cell = heapq.heappop(queue)
            if best[cell] != (sill, distance):
                continue
            if sea[cell]:
                target = cell
                break
            if distance >= max_distance_m:
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nxt = cell[0]+dr, cell[1]+dc
                if not (0 <= nxt[0] < bed.shape[0] and 0 <= nxt[1] < bed.shape[1]):
                    continue
                if np.hypot(nxt[0]-start[0], nxt[1]-start[1])*spacing > max_distance_m:
                    continue
                cost = (max(sill, float(bed[nxt])), distance+spacing)
                if cost < best.get(nxt, (np.inf, np.inf)):
                    best[nxt] = cost
                    parent[nxt] = cell
                    heapq.heappush(queue, (*cost, nxt))
        if target is None:
            routes.append(np.array([start]))
            states.append({"status": "unresolved_beyond_radius", "q_m3_s": float(flow)})
            continue
        path = [target]
        while path[-1] != start:
            path.append(parent[path[-1]])
        path = np.array(path[::-1], int)
        rr, cc = path.T
        stage = bed[rr, cc]+critical
        stage = np.maximum.accumulate(stage[::-1])[::-1]
        surface[rr, cc] = np.fmax(surface[rr, cc], stage)
        volume = float(np.sum(stage-bed[rr, cc])*spacing**2)
        routes.append(path)
        states.append({"status": "connected_surface_outflow" if len(path) > 1 else "gate_in_sea",
            "q_m3_s": float(flow), "saved_outlet_width_m": float(width), "effective_raster_width_m": float(effective_width),
            "critical_depth_m": critical, "path_length_m": float((len(path)-1)*spacing),
            "maximum_sill_m": float(bed[rr, cc].max()), "water_prism_m3": volume,
            "prism_replacement_time_s": volume/float(flow), "gate_stage_m": float(stage[0]),
            "sea_contact_cell_zx": path[-1].tolist()})
    return surface, routes, states


@dataclass(frozen=True)
class CoastalConfig:
    porosity: float = .35
    mobile_thickness_m: float = .30
    tide_amplitude_m: float = .65
    wave_height_m: float = .8
    wave_direction_xz: tuple = (-.8, -.6)
    phases_per_month: int = 8
    tide_period_s: float = 44712.
    activity_radius_m: float = 4700.
    offshore_depth_m: float = 8.
    tide_transfer_fraction: float = .16
    wave_transfer_fraction: float = .12


def smoothstep(value):
    value = np.clip(value, 0., 1.)
    return value*value*(3.-2.*value)


def connected_sea(bed, level):
    below = bed < level
    seeds = np.zeros_like(below)
    seeds[[0, -1], :] = below[[0, -1], :]
    seeds[:, [0, -1]] = below[:, [0, -1]]
    return binary_propagation(seeds, mask=below)


def derived_construction(bed, td_residual, channel_mask, retained, spacing, macro_bed_m=None):
    """Round inherited macro support folds, preserving the existing TD residual.

    Channels and retained upstream remain bit exact. This local derivation has
    no neighbor-tile certification; the outer 700 m is smoothly held fixed.
    """
    macro = bed-td_residual if macro_bed_m is None else np.asarray(macro_bed_m, float)
    distance = distance_transform_edt(~(channel_mask | retained))*spacing
    rows, cols = np.indices(bed.shape)
    edge = np.minimum.reduce([rows, cols, bed.shape[0]-1-rows, bed.shape[1]-1-cols])*spacing
    weight = smoothstep((distance-100.)/450.)*smoothstep(edge/700.)
    # Preserve shallow banks close to the tree, while also rounding offshore
    # support corners: excluding all negative elevations leaves square coastlines.
    weight *= .9*np.maximum(smoothstep((np.abs(macro)-3.)/22.),
        smoothstep((distance-1300.)/1200.))
    delta = weight*(gaussian_filter(macro, 550./spacing, mode="reflect")-macro)
    delta[channel_mask | retained] = 0.
    return bed+delta, delta, weight


def _face_transfer(inventory, vector_x, vector_z, fraction, activity, donor_wet, receiver_wet):
    """Upwind four-face transfer with a shared donor cap; closed scene boundary."""
    requests = []
    demand = np.zeros_like(inventory)
    for axis, velocity in ((1, vector_x), (0, vector_z)):
        for sign in (-1, 1):
            donor = [slice(None), slice(None)]
            receiver = [slice(None), slice(None)]
            donor[axis] = slice(1, None) if sign < 0 else slice(None, -1)
            receiver[axis] = slice(None, -1) if sign < 0 else slice(1, None)
            donor, receiver = tuple(donor), tuple(receiver)
            conductance = np.minimum(activity[donor], activity[receiver])
            amount = inventory[donor]*np.asarray(fraction)[donor]*np.maximum(sign*velocity[donor], 0.)
            amount *= conductance*donor_wet[donor]*receiver_wet[receiver]
            demand[donor] += amount
            requests.append((donor, receiver, amount))
    scale = np.minimum(1., np.divide(inventory, demand, out=np.ones_like(inventory), where=demand > 0.))
    change = np.zeros_like(inventory)
    gross = 0.
    for donor, receiver, amount in requests:
        amount *= scale[donor]
        change[donor] -= amount
        change[receiver] += amount
        gross += float(amount.sum())
    return inventory+change, change, gross


def run_coastal_transport(initial_bed_m, protected_mask, terminal_cells_zx,
                          monthly_terminal_solid_m3, spacing_m, config=CoastalConfig(),
                          *, tides=True, waves=True, month_seconds=None):
    bed = np.asarray(initial_bed_m, dtype=float).copy()
    supply = np.asarray(monthly_terminal_solid_m3, dtype=float)
    cells = np.asarray(terminal_cells_zx, dtype=int)
    numeric = [spacing_m, config.porosity, config.mobile_thickness_m, config.tide_amplitude_m,
        config.wave_height_m, config.tide_period_s, config.activity_radius_m, config.offshore_depth_m,
        config.tide_transfer_fraction, config.wave_transfer_fraction, *config.wave_direction_xz]
    if (bed.ndim != 2 or not np.isfinite(bed).all() or spacing_m <= 0.
            or supply.ndim != 2 or supply.shape[1] != len(cells)
            or not np.isfinite(supply).all() or np.any(supply < 0.)
            or not 0. <= config.porosity < 1. or config.mobile_thickness_m < 0.
            or config.phases_per_month < 4 or not np.isfinite(numeric).all()
            or config.tide_period_s <= 0. or config.activity_radius_m <= 1500.
            or config.tide_amplitude_m < 0. or config.wave_height_m < 0.
            or config.tide_transfer_fraction < 0. or config.wave_transfer_fraction < 0.
            or np.linalg.norm(config.wave_direction_xz) == 0.):
        raise ValueError("invalid finite coastal geometry, inventory, or forcing")
    durations = np.full(len(supply), 30.*86400.) if month_seconds is None else np.asarray(month_seconds, float)
    if durations.shape != (len(supply),) or not np.isfinite(durations).all() or np.any(durations <= 0.):
        raise ValueError("month durations must be positive finite seconds")
    if np.any(cells < 0) or np.any(cells >= np.array(bed.shape)):
        raise ValueError("terminal outside raster")
    rows, cols = np.indices(bed.shape)
    distance = np.minimum.reduce([np.hypot(rows-r, cols-c)*spacing_m for r, c in cells])
    radius = smoothstep((config.activity_radius_m-distance)/1500.)
    edge = np.minimum.reduce([rows, cols, bed.shape[0]-1-rows, bed.shape[1]-1-cols])*spacing_m
    protected_distance = distance_transform_edt(~np.asarray(protected_mask, bool))*spacing_m
    activity = radius*smoothstep(edge/500.)*smoothstep(protected_distance/160.)
    activity *= smoothstep((4.-bed)/3.)*smoothstep((bed+12.)/4.)
    activity[protected_mask] = 0.
    solid_per_m = spacing_m**2*(1.-config.porosity)
    inventory = config.mobile_thickness_m*solid_per_m*activity
    initial_inventory = inventory.copy()
    floor = bed-inventory/solid_per_m
    tide_delta = np.zeros_like(bed)
    wave_delta = np.zeros_like(bed)
    supply_delta = np.zeros_like(bed)
    exported_delta = np.zeros_like(bed)
    zero = connected_sea(bed, 0.)
    deep = connected_sea(bed, -3.)
    travel = distance_transform_edt(~deep)*spacing_m
    gz, gx = np.gradient(gaussian_filter(travel, 2.), spacing_m)
    norm = np.maximum(np.hypot(gx, gz), 1.e-12)
    inward_x, inward_z = gx/norm, gz/norm
    kernels = []
    for r, c in cells:
        kernel = np.exp(-((rows-r)**2+(cols-c)**2)*spacing_m**2/(2.*120.**2))*activity
        kernel[np.hypot(rows-r, cols-c)*spacing_m > 360.] = 0.
        kernels.append(kernel)
    pending = np.zeros(len(cells))
    history = []
    previous_level = 0.
    previous_wet = zero
    previous_water_volume = float((np.maximum(-bed, 0.)*zero).sum()*spacing_m**2)
    high = np.zeros_like(zero)
    low = np.zeros_like(zero)
    wet_count = np.zeros_like(bed)
    total_export = 0.
    tide_gross = wave_gross = 0.
    phase_count = len(supply)*config.phases_per_month
    for month in range(len(supply)):
        for phase in range(config.phases_per_month):
            # Sinusoid is temporal boundary forcing only; it never writes terrain.
            angle = 2.*np.pi*phase/config.phases_per_month
            level = config.tide_amplitude_m*np.sin(angle) if tides else 0.
            wet = connected_sea(bed, level)
            depth = np.maximum(level-bed, 0.)*wet
            before = inventory.copy()
            pending += supply[month]/config.phases_per_month
            for terminal, kernel in enumerate(kernels):
                weights = kernel*wet
                denominator = float(weights.sum())
                if denominator > 0.:
                    deposit = pending[terminal]*weights/denominator
                    inventory += deposit
                    supply_delta += deposit/solid_per_m
                    pending[terminal] = 0.
            shallow = np.exp(-depth/3.)
            if tides and config.tide_amplitude_m > 0.:
                trend = (level-previous_level)/max(config.tide_amplitude_m, 1.e-12)
                # Flood follows the connected inundation gradient; ebb reverses it.
                fraction = config.tide_transfer_fraction*abs(trend)*shallow
                inventory, change, gross = _face_transfer(inventory,
                    np.sign(trend)*inward_x, np.sign(trend)*inward_z, fraction,
                    activity, wet | previous_wet, wet)
                tide_delta += change/solid_per_m
                tide_gross += gross
            if waves and config.wave_height_m > 0.:
                bz, bx = np.gradient(gaussian_filter(bed, 3.), spacing_m)
                slope = np.maximum(np.hypot(bx, bz), 1.e-9)
                nx, nz = bx/slope, bz/slope
                direction = np.asarray(config.wave_direction_xz, float)
                direction /= np.linalg.norm(direction)
                incidence = np.maximum(direction[0]*nx+direction[1]*nz, 0.)
                tx, tz = -nz, nx
                along = direction[0]*tx+direction[1]*tz
                vx = incidence*(along*tx+.35*nx)
                vz = incidence*(along*tz+.35*nz)
                breaking = np.minimum(config.wave_height_m, .78*depth)
                fraction = config.wave_transfer_fraction*breaking*shallow
                inventory, change, gross = _face_transfer(inventory, vx, vz, fraction,
                    activity, wet, wet)
                wave_delta += change/solid_per_m
                wave_gross += gross
            # Deep marine suspended loss has an explicit destination in the ledger.
            active_forcing = (tides and config.tide_amplitude_m > 0.) or (waves and config.wave_height_m > 0.)
            loss = inventory*wet*smoothstep((depth-config.offshore_depth_m)/2.)*.04*bool(active_forcing)
            inventory -= loss
            exported_delta -= loss/solid_per_m
            total_export += float(loss.sum())
            bed = initial_bed_m+(inventory-initial_inventory)/solid_per_m
            if np.min(inventory) < -1.e-8:
                raise AssertionError("finite active layer overdrawn")
            wet = connected_sea(bed, level)
            depth = np.maximum(level-bed, 0.)*wet
            wet_count += wet
            water_volume = float(depth.sum()*spacing_m**2)
            history.append([month, phase, level, float(wet.sum()*spacing_m**2),
                water_volume, float(inventory.sum()),
                total_export, float(pending.sum()), float(np.abs(inventory-before).sum()),
                water_volume-previous_water_volume,
                float(durations[:month].sum()+phase*durations[month]/config.phases_per_month),
                phase*config.tide_period_s/config.phases_per_month,
                durations[month]/config.tide_period_s,
                durations[month]/config.phases_per_month])
            previous_water_volume = water_volume
            if phase == config.phases_per_month//4:
                high = connected_sea(bed, config.tide_amplitude_m if tides else 0.)
            if phase == 3*config.phases_per_month//4:
                low = connected_sea(bed, -config.tide_amplitude_m if tides else 0.)
            previous_level, previous_wet = level, wet
    final_wet = connected_sea(bed, 0.)
    high_level = config.tide_amplitude_m if tides else 0.
    low_level = -high_level
    high = connected_sea(bed, high_level)
    low = connected_sea(bed, low_level)
    ledger = {"initial_geological_mobile_solid_m3": float(initial_inventory.sum()),
        "terminal_river_input_solid_m3": float(supply.sum()),
        "final_mobile_solid_m3": float(inventory.sum()), "offshore_export_solid_m3": total_export,
        "pending_terminal_solid_m3": float(pending.sum()),
        "gross_tide_face_transfer_solid_m3": tide_gross,
        "gross_wave_face_transfer_solid_m3": wave_gross}
    ledger["residual_solid_m3"] = (ledger["initial_geological_mobile_solid_m3"]+float(supply.sum())
        -ledger["final_mobile_solid_m3"]-total_export-float(pending.sum()))
    return {"bed_m": bed, "initial_mobile_solid_m3": initial_inventory,
        "mobile_solid_m3": inventory, "rock_floor_m": floor,
        "activity_weight": activity, "tide_height_delta_m": tide_delta,
        "wave_height_delta_m": wave_delta, "river_supply_height_delta_m": supply_delta,
        "export_height_delta_m": exported_delta, "water_surface_m": np.where(final_wet, 0., np.nan),
        "water_depth_m": np.maximum(-bed, 0.)*final_wet, "wet_mask": final_wet,
        "high_tide_wet_mask": high, "low_tide_wet_mask": low,
        "high_tide_surface_m": np.where(high, high_level, np.nan),
        "low_tide_surface_m": np.where(low, low_level, np.nan),
        "high_tide_depth_m": np.maximum(high_level-bed, 0.)*high,
        "low_tide_depth_m": np.maximum(low_level-bed, 0.)*low,
        "wet_fraction": wet_count/phase_count, "phase_history": np.asarray(history),
        "pending_terminal_solid_m3": pending, "ledger": ledger, "config": asdict(config)}
