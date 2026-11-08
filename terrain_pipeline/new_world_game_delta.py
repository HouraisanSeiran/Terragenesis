"""Local, frozen-water game delta adapters; no water routing is replayed here."""
import numpy as np

from terrain_pipeline.new_world_delta import MouthConsumer, _validate_kernel_result
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment


def section_stages(section_bed_m, sample_spacing_m, water_q_m3_s, slope, roughness):
    """Estimate normal stages on sampled irregular sections using Manning conveyance.

    Adjacent sample points form linear bed segments. The estimate assumes uniform
    flow and does not model downstream backwater, lateral exchange or lake heads.
    Sections that overflow either end are rejected instead of extrapolated.
    """
    bed = np.asarray(section_bed_m, dtype=float)
    q = np.asarray(water_q_m3_s, dtype=float)
    s = np.asarray(slope, dtype=float)
    if (bed.ndim != 2 or bed.shape[1] < 3 or q.ndim != 2 or q.shape[1] != bed.shape[0]
            or s.shape != (bed.shape[0],) or not np.isfinite(bed).all()
            or not np.isfinite(q).all() or not np.isfinite(s).all()
            or np.any(q < 0) or np.any(s <= 0) or not np.isfinite(sample_spacing_m)
            or not np.isfinite(roughness) or sample_spacing_m <= 0 or roughness <= 0):
        raise ValueError('invalid irregular sections or hydraulic forcing')
    stages = np.empty_like(q)
    widths = np.empty_like(q)
    for j in range(q.shape[0]):
        for i, profile in enumerate(bed):
            low = float(profile.min())
            high = float(min(profile[0], profile[-1]))
            if high <= low:
                raise ValueError('section has no contained channel')
            def conveyance(stage):
                raw_a = stage - profile[:-1]
                raw_b = stage - profile[1:]
                a = np.maximum(raw_a, 0.)
                b = np.maximum(raw_b, 0.)
                both = (a > 0) & (b > 0)
                fraction = np.where(both, 1., np.divide(np.maximum(a, b), np.abs(raw_a-raw_b),
                    out=np.zeros_like(a), where=np.abs(raw_a-raw_b) > 0))
                fraction = np.clip(fraction, 0., 1.)
                # Ignore isolated depressions outside the wetted channel containing
                # the section minimum; they have no demonstrated lateral connection.
                center = int(np.argmin(profile))
                left = center
                right = center
                while left > 0 and profile[left - 1] < stage:
                    left -= 1
                while right + 1 < len(profile) and profile[right + 1] < stage:
                    right += 1
                keep = np.zeros_like(fraction, dtype=bool)
                keep[max(0, left - 1):min(len(fraction), right + 1)] = True
                fraction = np.where(keep, fraction, 0.)
                area = np.sum((a+b) * .5 * fraction * sample_spacing_m)
                perimeter = np.sum(fraction * np.hypot(sample_spacing_m, np.diff(profile)))
                width = np.sum(fraction) * sample_spacing_m
                flow = 0. if perimeter == 0 else area * (area / perimeter)**(2/3) * np.sqrt(s[i]) / roughness
                return flow, width
            if q[j, i] > conveyance(high)[0]:
                raise ValueError('section overtopped; widen section or mark unresolved')
            for _ in range(55):
                mid = (low + high) / 2
                if conveyance(mid)[0] < q[j, i]: low = mid
                else: high = mid
            stages[j, i] = high
            widths[j, i] = conveyance(high)[1]
    return stages, widths


def route_trace_sediment(*, receiver, length_m, width_m, bed_m, depth_m,
                         routed_water_m3, slope, time_seconds, rock_floor_m,
                         alluvium_bulk_m3, hardness, material, geometry_identity,
                         hydraulic_identity, provenance):
    """Route finite declared stocks using interval outflow volumes, never local inflow."""
    time = np.asarray(time_seconds, dtype=np.float64)
    water = np.asarray(routed_water_m3, dtype=np.float64)
    if time.ndim != 1 or water.ndim != 2 or water.shape[0] != len(time)-1:
        raise ValueError('water must be one routed volume per interval and node')
    if not np.isfinite(water).all() or np.any(water < 0) or np.any(np.diff(time) <= 0):
        raise ValueError('invalid routed water intervals')
    friction = np.broadcast_to(np.asarray(slope, dtype=np.float64), water.shape).copy()
    return route_daily_sediment(receiver=np.asarray(receiver, dtype=np.int64),
        length_m=length_m, width_m=width_m, bed_elevation_m=bed_m,
        water_depth_m=depth_m, water_q_m3_s=water / np.diff(time)[:, None],
        friction_slope=friction, time_seconds=time, rock_floor_m=rock_floor_m,
        initial_alluvium_bulk_m3=alluvium_bulk_m3, hardness=hardness, material=material,
        geometry_identity_sha256=geometry_identity, hydraulic_identity_sha256=hydraulic_identity,
        material_provenance=provenance)


def consume_mouth(*, consumer, source_identity, mouth_id, interval_ids, duration_s,
                  water_m3, solid_m3, bed_m, ocean_mask, geometry, prohibited_mask, config=None):
    """Consume each named mouth interval once against the shared bed and ocean."""
    # Validate the result before committing the in-memory claims.
    temporary = MouthConsumer(consumer.consumed)
    output = temporary.run(source_identity=source_identity, mouth_id=mouth_id,
        interval_ids=interval_ids, duration_s=duration_s, water_m3=water_m3,
        solid_m3=solid_m3, sediment_source='finite routed sediment inventory',
        bed_m=bed_m, ocean_mask=ocean_mask, geometry=geometry,
        prohibited_mask=prohibited_mask, config=config)
    _validate_kernel_result(output['result'], np.asarray(bed_m, dtype=float),
                            ocean_mask, np.asarray(solid_m3), len(interval_ids))
    consumer.consumed = temporary.consumed
    return output


def bounded_subgrid_channel(source_bed_m, stage_m, width_m, depth_m, station_m, *, cut_cap_m=6.):
    """Construct equivalent trapezoidal sections below prescribed connected stages.

    Each source sample is left intact; cut and bulk excavation are an independent
    narrow-channel operator, not 30 m raster edits or transported sediment.
    Stage must be non-increasing towards the fixed downstream boundary. A
    prescribed stage is a game-grade boundary interpolation, not a flow solve.
    """
    source, stage, width, depth, station = (np.asarray(v, dtype=float) for v in
        (source_bed_m, stage_m, width_m, depth_m, station_m))
    if (source.ndim != 1 or len(source) < 2 or any(a.shape != source.shape for a in
        (stage, width, depth, station)) or not all(np.isfinite(a).all() for a in
        (source, stage, width, depth, station)) or np.any(width <= 0) or
        np.any(depth <= 0) or np.any(np.diff(station) <= 0) or
        np.any(np.diff(stage) > 1e-9) or not np.isfinite(cut_cap_m) or cut_cap_m <= 0):
        raise ValueError('invalid bounded channel inputs')
    bed = np.minimum(source, stage - depth)
    cut = source - bed
    if np.any(cut > cut_cap_m + 1e-9):
        raise ValueError('bounded channel exceeds cut cap')
    # Trapezoidal section bottom occupies 60% of top width; both sloping
    # sides together contribute 20% of width times depth to the area.
    area = .8 * width * cut
    bulk = float(np.trapezoid(area, station))
    return dict(source_bed_m=source.copy(), bed_m=bed, stage_m=stage.copy(),
                width_m=width.copy(), depth_m=stage-bed, cut_m=cut,
                construction_bulk_m3=bulk)



def route_subgrid_distributaries(water_m3, solid_m3, duration_s, lengths_m,
                                 width_m, depth_m, eligible_masks, cell_area_m2,
                                 *, settling_velocity_m_s=1.e-4, porosity=.35):
    """Conservative kinematic branch split with finite settling on eligible cells.

    The imposed wet sections and branch lengths must already be validated. Each
    branch receives a width-proportional share of each interval exactly once;
    water is passed through, not added to an existing hydrology ledger. Settling
    is an exponential travel-time approximation, not morphodynamic maturation.
    """
    water, solid, dt, lengths, widths, depths = (np.asarray(v, float) for v in
        (water_m3, solid_m3, duration_s, lengths_m, width_m, depth_m))
    masks = np.asarray(eligible_masks)
    if (water.ndim != 1 or not len(water) or solid.shape != water.shape or dt.shape != water.shape
            or lengths.ndim != 1 or not len(lengths) or widths.shape != lengths.shape
            or depths.shape != lengths.shape or masks.ndim != 3 or masks.shape[0] != len(lengths)
            or masks.dtype.kind != 'b' or not all(np.isfinite(v).all() for v in
            (water, solid, dt, lengths, widths, depths)) or np.any(water < 0)
            or np.any(solid < 0) or np.any(dt <= 0) or np.any(lengths <= 0)
            or np.any(widths <= 0) or np.any(depths <= 0) or not np.isfinite(cell_area_m2)
            or cell_area_m2 <= 0 or not np.isfinite(settling_velocity_m_s)
            or settling_velocity_m_s < 0 or not 0 <= porosity < 1):
        raise ValueError('invalid subgrid distribution')
    shares = widths / widths.sum()
    branch_water = water[:, None] * shares
    branch_solid = solid[:, None] * shares
    store = np.zeros(masks.shape[1:], float)
    deposited = np.zeros_like(branch_solid)
    exported = np.zeros_like(branch_solid)
    escrow = np.zeros(len(lengths), float)
    for i in range(len(water)):
        for j in range(len(lengths)):
            load = branch_solid[i, j] + escrow[j]
            escrow[j] = 0.
            if branch_water[i, j] <= 0:
                escrow[j] = load
                continue
            if not masks[j].any():
                exported[i, j] = load
                continue
            velocity = branch_water[i, j] / dt[i] / (widths[j] * depths[j])
            fraction = -np.expm1(-settling_velocity_m_s * lengths[j] / (velocity * depths[j]))
            deposited[i, j] = load * fraction
            exported[i, j] = load - deposited[i, j]
            store[masks[j]] += deposited[i, j] / masks[j].sum()
    return dict(branch_water_m3=branch_water, branch_solid_m3=branch_solid,
                deposited_solid_m3=deposited, exported_solid_m3=exported,
                stored_solid_m3=store, height_delta_m=store/(cell_area_m2*(1-porosity)),
                branch_shares=shares, escrow_solid_m3=escrow)


def retained_sediment_supply(*, station_m, points_xz_m, bed_m, stage_m, width_m,
                             control_edges_m, control_water_m3, time_seconds,
                             source_identity, mouth_id, inlet_xz_m, material):
    """Route declared local stocks only inside the supplied inlet-bound domain.

    Water columns are saved outflow at each downstream control edge; the final
    edge is an explicit terminal at the branch inlet. Earlier water is not added
    to the final interval volume. Initial alluvium is the existing local scenario.
    """
    from terrain_pipeline.common_infra import identity
    s, points, bed, stage, widths, edges, water, time, inlet = (np.asarray(v, float) for v in
        (station_m, points_xz_m, bed_m, stage_m, width_m, control_edges_m,
         control_water_m3, time_seconds, inlet_xz_m))
    if (s.ndim != 1 or len(s)<2 or points.shape != (len(s),2) or
            any(v.shape != s.shape for v in (bed,stage,widths)) or
            edges.ndim != 1 or len(edges)<2 or water.shape != (len(time)-1,len(edges)-1) or
            inlet.shape != (2,) or not all(np.isfinite(v).all() for v in
            (s,points,bed,stage,widths,edges,water,time,inlet)) or
            np.any(np.diff(s)<=0) or np.any(np.diff(edges)<=0) or
            np.any(np.diff(time)<=0) or np.any(water<0) or np.any(widths<=0) or
            np.any(stage<=bed) or not np.isclose(edges[0],s[0]) or
            not np.isclose(edges[-1],s[-1]) or not np.allclose(points[-1],inlet,atol=1e-7,rtol=0)):
        raise ValueError('sediment domain and inlet mismatch')
    centers=(edges[:-1]+edges[1:])/2
    length=np.diff(edges); b=np.interp(centers,s,bed); h=np.interp(centers,s,stage)-b
    w=np.interp(centers,s,widths); slope=np.full(len(length),(stage[0]-stage[-1])/(s[-1]-s[0]))
    if np.any(slope<=0): raise ValueError('nonpositive assumed friction slope')
    geom=retained_geometry_identity(s,points,bed,stage,widths,edges,inlet,
                                    source_identity=source_identity,mouth_id=mouth_id)
    hydraulic=identity(dict(time_seconds=time,control_water_m3=water),
                       dict(source_identity=source_identity,mouth_id=mouth_id,geometry_identity=geom))
    result=route_trace_sediment(receiver=np.r_[np.arange(1,len(length)),-1].astype(np.int64),
        length_m=length,width_m=w,bed_m=b,depth_m=np.broadcast_to(h,water.shape).copy(),
        routed_water_m3=water,slope=slope,time_seconds=time,rock_floor_m=b-1.,
        alluvium_bulk_m3=w*length*.25,hardness=np.full(len(length),.5),material=material,
        geometry_identity=geom,hydraulic_identity=hydraulic,
        provenance='retained local scenario: 0.25 m alluvium; rock floor 1 m below bed; upstream solid unknown')
    return dict(result=result,geometry_identity=geom,hydraulic_identity=hydraulic,
                inlet_xz_m=inlet.copy(),mouth_id=mouth_id,time_seconds=time.copy(),
                mouth_water_m3=water[:,-1].copy(),solid_m3=result['arrays']['exported_solid_m3'][:,-1].copy())


def validate_retained_supply(supply, *, geometry_identity, inlet_xz_m, mouth_id,
                             time_seconds, mouth_water_m3):
    """Reject supplying a different geometry, mouth, interval, or routed water."""
    if (supply['geometry_identity'] != geometry_identity or supply['mouth_id'] != mouth_id or
            not np.array_equal(supply['inlet_xz_m'],np.asarray(inlet_xz_m)) or
            not np.array_equal(supply['time_seconds'],np.asarray(time_seconds)) or
            not np.array_equal(supply['mouth_water_m3'],np.asarray(mouth_water_m3))):
        raise ValueError('sediment supply geometry or water binding mismatch')
    return np.asarray(supply['solid_m3'],float).copy()


def retained_geometry_identity(station_m, points_xz_m, bed_m, stage_m, width_m,
                               control_edges_m, inlet_xz_m, *, source_identity, mouth_id):
    from terrain_pipeline.common_infra import identity
    arrays=dict(station_m=station_m,points_xz_m=points_xz_m,bed_m=bed_m,stage_m=stage_m,
                width_m=width_m,control_edges_m=control_edges_m,inlet_xz_m=inlet_xz_m)
    return identity({k:np.asarray(v,float) for k,v in arrays.items()},
                    dict(source_identity=source_identity,mouth_id=mouth_id,terminal='branch_inlet'))
