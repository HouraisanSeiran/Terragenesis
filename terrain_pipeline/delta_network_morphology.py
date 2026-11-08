"""Sparse distributary morphology using the existing growth and width laws.

Construction is a geological scenario, independent from later physical events.
The seed describes the algorithm; the frozen TD source retains its historical seed.
"""

from dataclasses import dataclass, asdict
import numpy as np
from scipy import ndimage as ndi
from skimage.graph import MCP_Geometric
from terrain_pipeline import delta_network_skeleton_v3 as sk
from terrain_pipeline.delta_network_terrain import _densify, _Stamps, _smoothstep, _Grid
from terrain_pipeline.delta_network_site import local_to_world
from terrain_pipeline.channel_geometry import turn_penalty
from terrain_pipeline.large_delta_landform_regional import _routes

WORLD_SEED = 20260903


@dataclass(frozen=True)
class PlainParameters:
    """Source-controlled, finite-inventory lowland and bay construction."""

    catchment_km2: float = 80000.0
    denudation_m: float = 0.35
    delivery_fraction: float = 0.3
    porosity: float = 0.4
    shelf_depth_bound_m: float = 1000.0
    landward_elevation_limit_m: float = 45.0
    landward_full_reconstruction_below_m: float = 12.0
    landward_blend_m: float = 2500.0
    landward_max_distance_from_coast_m: float = 18000.0
    longshore_transport_m: float = 26000.0
    # Support-window fade and physical foreset width are separate lengths.
    deposition_transition_m: float = 18000.0
    front_transition_m: float = 2000.0
    plain_height_m: float = 0.8
    plain_slope: float = 0.000055

    def __post_init__(self):
        if not np.isfinite(list(asdict(self).values())).all():
            raise ValueError("plain parameters must be finite")
        lengths = (
            self.shelf_depth_bound_m,
            self.landward_blend_m,
            self.landward_max_distance_from_coast_m,
            self.longshore_transport_m,
            self.deposition_transition_m,
        )
        if min(lengths) <= 0.0 or not 0.0 <= self.porosity < 1.0 or not 0.0 <= self.delivery_fraction <= 1.0:
            raise ValueError("invalid plain lengths, porosity or delivery fraction")
        if min(self.catchment_km2, self.denudation_m, self.plain_height_m, self.plain_slope) < 0.0:
            raise ValueError("negative geological stock or plain height/slope")
        if not 0.0 <= self.landward_full_reconstruction_below_m < self.landward_elevation_limit_m:
            raise ValueError("landward reconstruction elevations must be increasing")


def whole_plain(spec, td_bed, td_ocean, pp=None):
    """Fill connected source accommodation, preserving hills and deep bays.

    No circle, lobe union, fan, ellipse or channel buffer defines this body.
    The existing terrain-routing operator orders shallow-bay accommodation;
    a finite geological solid stock determines how far the fill can proceed.
    Source lowlands blend toward a floodplain; high hills remain unchanged.
    This is a declared geological initialization, not a simulated event.
    """
    pp = pp or PlainParameters()
    values = np.array(list(asdict(pp).values()), float)
    if (
        not np.isfinite(values).all()
        or pp.catchment_km2 <= 0.0
        or pp.denudation_m < 0.0
        or not 0.0 <= pp.delivery_fraction <= 1.0
        or not 0.0 <= pp.porosity < 1.0
        or min(
            pp.front_transition_m,
            pp.deposition_transition_m,
            pp.landward_blend_m,
            pp.longshore_transport_m,
            pp.shelf_depth_bound_m,
        )
        <= 0.0
        or pp.landward_elevation_limit_m <= pp.landward_full_reconstruction_below_m
    ):
        raise ValueError("invalid finite plain material or transition parameters")
    base = np.asarray(td_bed, float).copy()
    td_ocean = np.asarray(td_ocean, bool)
    if base.shape != (spec.nu, spec.nv) or td_ocean.shape != base.shape or not np.isfinite(base).all():
        raise ValueError("matching finite saved TD terrain required")
    U, V = np.meshgrid(
        spec.u0_m + (np.arange(spec.nu) + 0.5) * spec.spacing_m,
        spec.v0_m + (np.arange(spec.nv) + 0.5) * spec.spacing_m,
        indexing="ij",
    )
    phase = (WORLD_SEED % 997) / 997.0 * 2.0 * np.pi
    relief = (
        np.sin(U / 4300.0 + 0.7 * np.sin(V / 6200.0) + phase)
        + 0.6 * np.sin(V / 5100.0 - U / 7900.0 + phase * 1.7)
    ) / 1.6
    inland_m = ndi.distance_transform_edt(~td_ocean) * spec.spacing_m
    height_weight = 1.0 - _smoothstep(
        (base - pp.landward_full_reconstruction_below_m)
        / (pp.landward_elevation_limit_m - pp.landward_full_reconstruction_below_m)
    )
    lowlands = (~td_ocean) & (base < pp.landward_elevation_limit_m)
    lowlands &= inland_m < pp.landward_max_distance_from_coast_m
    # Blend into high ground, not back into the original coastal cliffs.
    # The marine side continues the floodplain, so it is not a lowland edge.
    edge = ndi.distance_transform_edt(lowlands | td_ocean) * spec.spacing_m
    alongshore = np.maximum(pp.longshore_transport_m - np.abs(V), 0.0) / pp.landward_blend_m
    weight = height_weight * _smoothstep(edge / pp.landward_blend_m) * _smoothstep(alongshore)
    weight *= lowlands
    target = pp.plain_height_m + pp.plain_slope * inland_m + 0.12 * relief
    landward = base * (1.0 - weight) + target * weight
    factor = spec.spacing_m**2 * (1.0 - pp.porosity)
    inventory = pp.catchment_km2 * 1e6 * pp.denudation_m * pp.delivery_fraction
    proposed_landward_fill = float(np.maximum(landward - base, 0.0)[~td_ocean].sum() * factor)
    if proposed_landward_fill > inventory:
        fill_ratio = inventory / proposed_landward_fill
        landward = np.where(landward > base, base + (landward - base) * fill_ratio, landward)
    # Source bay bathymetry, its connected shallow shelf and hard islands
    # determine accommodation. Deep sea and bedrock land are never flattened.
    eligible = td_ocean & (base < 0.0) & (base > -pp.shelf_depth_bound_m)
    labels, _ = ndi.label(eligible)
    candidates = np.argwhere(eligible)
    if not len(candidates):
        raise ValueError("no shallow source-connected marine accommodation")
    inlet = np.array([(-spec.u0_m) / spec.spacing_m, (-spec.v0_m) / spec.spacing_m])
    start = tuple(candidates[np.argmin(np.sum((candidates - inlet) ** 2, axis=1))])
    eligible = labels == labels[start]
    transport, _ = _routes(base, eligible, start, spec.spacing_m)
    # The mild alongshore loss represents an explicitly declared asymmetry;
    # source depth/path resistance supplies the principal geometric control.
    transport = transport + np.maximum(V, 0.0) * 0.35 + np.maximum(-V, 0.0) * 0.15
    eligible &= np.isfinite(transport) & (np.abs(V) < pp.longshore_transport_m)
    room = np.maximum(pp.plain_height_m + 0.10 * relief - base, 0.0) * eligible
    ids = np.flatnonzero(eligible)
    order = ids[np.argsort(transport.ravel()[ids], kind="stable")]
    landward_fill = float(np.maximum(landward - base, 0.0)[~td_ocean].sum() * factor)
    if landward_fill > inventory:
        positive = np.maximum(landward - base, 0.0)
        landward = base + np.minimum(landward - base, 0.0) + positive * (inventory / landward_fill)
        landward_fill = float(np.maximum(landward - base, 0.0)[~td_ocean].sum() * factor)
    available = max(inventory - landward_fill, 0.0)
    flat_room = room.ravel()
    costs = transport.ravel()[order]
    support_taper = _smoothstep((pp.longshore_transport_m - np.abs(V)) / max(pp.deposition_transition_m, 1.0))
    deep_boundary = td_ocean & (base <= -pp.shelf_depth_bound_m)
    if deep_boundary.any():
        # A depth eligibility bound may constrain accommodation, but must not
        # become a vertical depositional wall on its isobath.
        margin = ndi.distance_transform_edt(~deep_boundary) * spec.spacing_m
        support_taper *= _smoothstep(margin / pp.front_transition_m)
    # Routing cost grows with depth. A fixed cost interval therefore becomes
    # only a few physical cells in deep water. Normalize by cost/metre so the
    # foreset keeps its declared physical width at both small and large scale.
    nearest = ndi.distance_transform_edt(~eligible, return_distances=False, return_indices=True)
    extended = transport[tuple(nearest)]
    gradient = np.hypot(*np.gradient(extended, spec.spacing_m))
    transition_cost = np.maximum(gradient.ravel()[order], 1.0) * pp.front_transition_m
    capacity = flat_room[order] * support_taper.ravel()[order]
    # Solve the stock allocation after the transition taper. Applying a taper
    # after an untapered cutoff would silently leave a large usable stock idle.
    lo = 0.0
    hi = float(np.max(costs + transition_cost)) if len(order) else 0.0
    for _ in range(42):
        cutoff = (lo + hi) * 0.5
        fraction = _smoothstep((cutoff - costs) / transition_cost)
        if float(np.sum(capacity * fraction) * factor) > available:
            hi = cutoff
        else:
            lo = cutoff
    cutoff = lo
    fractions = np.zeros(base.size, float)
    fractions[order] = _smoothstep((cutoff - costs) / transition_cost)
    deposit = room * fractions.reshape(base.shape) * support_taper
    marine_retained = float(deposit.sum() * factor)
    surface = np.where(td_ocean, base + deposit, landward)
    active = ((weight > 0.01) & ~td_ocean) | (deposit > 0.01)
    difference = surface - base
    ledger = dict(
        declared_geological_solid_m3=float(inventory),
        marine_retained_solid_m3=marine_retained,
        marine_unplaced_solid_m3=float(max(inventory - landward_fill - marine_retained, 0.0)),
        landward_cut_solid_m3=float(np.maximum(-difference, 0.0)[~td_ocean].sum() * factor),
        landward_fill_solid_m3=landward_fill,
        landward_unmet_fill_solid_m3=float(max(0.0, proposed_landward_fill - landward_fill)),
        physical_event_input_solid_m3=0.0,
        physical_elapsed_seconds=0.0,
        marine_operator="terrain_pipeline.large_delta_landform_regional._routes + finite accommodation allocation",
        landward_operator="source lowland elevation and connectivity; smooth geological transition",
        geometry_not_defined_by_lobes_circles_fan_or_channel_buffers=True,
        actual_deposition_cost_cutoff_m=cutoff,
        front_transition_semantics="physical metres after local transport-cost gradient normalization; depth eligibility edge also tapers",
        plain_parameters=asdict(pp),
    )
    return dict(
        bed=surface,
        base=base,
        active=active,
        deposit=deposit,
        landward_weight=weight,
        ledger=ledger,
        eligible_bay_mask=eligible,
    )


VARIANTS = {
    # A long plain spacing keeps the front legible while links still provide
    # real, legal confluences.  These are morphology scenarios, not hydrology.
    "base": dict(link_prob=0.85, link_spacing_k=14.0, link_gap_k=6.0, link_donor_q_min=800.0),
    "few_loops": dict(
        link_prob=0.10, link_spacing_k=70.0, link_gap_k=24.0, link_donor_q_min=4000.0, merge_frac=0.35
    ),
    "many_loops": dict(link_prob=0.95, link_spacing_k=10.0, link_gap_k=5.0, link_donor_q_min=600.0),
}


def parameters(variant="base", **overrides):
    """Lengths are metres. Independent reach/spread controls remain in DeltaParamsV3."""
    values = dict(
        variant=variant,
        algorithm_world_seed=WORLD_SEED,
        apex_u=-4000.0,
        width_a=5.2,
        width_b=0.56,
        beta=6.0,
        r_young=53000.0,
        spread_deg=50.0,
        spacing_plain_m=2200.0,
        spacing_front_m=1600.0,
        split_gap_factor=1.8,
        front_boost=1.1,
        min_remaining_split_m=1200.0,
        min_split_len_factor=2.0,
        c_terr=4.0,
        c_goal=1.6,
        c_coast=0.15,
        avul_first_m=500.0,
        avul_gap_m=700.0,
    )
    values.update(VARIANTS[variant])
    values.update(overrides)
    return sk.DeltaParamsV3(**values)


@dataclass(frozen=True)
class ChannelStampParameters:
    """Only the unchanged v4 channel cross-section operator is reused."""

    freeboard_m: float = 0.8
    stamp_step_m: float = 18.0
    channel_floor: float = 0.15

    def to_dict(self):
        return asdict(self)


def terrain_parameters():
    return ChannelStampParameters()


def geometry_audit(spec, g, T, tp=None):
    """Check the frozen physical centreline, raster water and real XZ turns.

    A raster tolerance of one cell accounts for centre-versus-cell sampling.
    This audit never changes the geometry or hides a channel in a figure.
    The turn penalty uses k=1 and includes every inbound/outbound junction.
    """
    tp = tp or terrain_parameters()
    grid = T["grid"]
    distance = ndi.distance_transform_edt(~T["chan"]) * spec.spacing_m
    max_distance = 0.0
    outside = 0
    endpoint_error = 0.0
    first, last, penalties = [], [], []
    for eid in range(len(g.edge_from)):
        P = sk.edge_points(g, eid)
        endpoint_error = max(
            endpoint_error,
            float(np.linalg.norm(P[0] - g.node_uv[g.edge_from[eid]])),
            float(np.linalg.norm(P[-1] - g.node_uv[g.edge_to[eid]])),
        )
        dense = _densify(P, max(spec.spacing_m * 0.5, 1.0))
        inside = (
            (dense[:, 0] >= spec.u0_m)
            & (dense[:, 0] < spec.u0_m + spec.nu * spec.spacing_m)
            & (dense[:, 1] >= spec.v0_m)
            & (dense[:, 1] < spec.v0_m + spec.nv * spec.spacing_m)
        )
        outside += int((~inside).sum())
        max_distance = max(max_distance, float(np.max(grid.sample(distance, dense[:, 0], dense[:, 1]))))
        X, Z = local_to_world(spec, P[:, 0], P[:, 1])
        directions = np.diff(np.column_stack([X, Z]), axis=0)
        if np.any(np.linalg.norm(directions, axis=1) <= 1e-8):
            raise ValueError("duplicate graph centreline point")
        first.append(directions[0])
        last.append(directions[-1])
        penalties.extend(float(turn_penalty(a, b, 1.0)) for a, b in zip(directions[:-1], directions[1:]))
    for node in range(len(g.node_uv)):
        for inbound in np.flatnonzero(g.edge_to == node):
            for outbound in np.flatnonzero(g.edge_from == node):
                penalties.append(float(turn_penalty(last[inbound], first[outbound], 1.0)))
    border = np.zeros(T["water"].shape, bool)
    border[[0, -1], :] = T["water"][[0, -1], :]
    border[:, [0, -1]] |= T["water"][:, [0, -1]]
    connected = ndi.binary_propagation(border, mask=T["water"])
    mouths = []
    for node in g.mouth_nodes:
        u, v = g.node_uv[node]
        row = int(np.clip((u - spec.u0_m) / spec.spacing_m, 0, spec.nu - 1))
        col = int(np.clip((v - spec.v0_m) / spec.spacing_m, 0, spec.nv - 1))
        stage = max(0.0, float(T["z_plain"][row, col]) - tp.freeboard_m)
        mouths.append(
            dict(
                node=int(node),
                u_m=float(u),
                v_m=float(v),
                connected_to_open_water=bool(connected[row, col]),
                raster_depth_m=float(stage - T["bed"][row, col]),
            )
        )
    return dict(
        ok=bool(
            outside == 0
            and endpoint_error <= 1e-6
            and max_distance <= spec.spacing_m
            and all(m["connected_to_open_water"] and m["raster_depth_m"] > 0 for m in mouths)
            and np.isfinite(penalties).all()
        ),
        centreline_samples_outside_window=outside,
        endpoint_max_error_m=endpoint_error,
        maximum_centreline_to_channel_mask_m=max_distance,
        raster_tolerance_m=float(spec.spacing_m),
        xz_turn_penalty_k1_sum=float(np.sum(penalties)),
        xz_forbidden_turns=int(np.isinf(penalties).sum()),
        mouths=mouths,
        tidal_creeks_are_separate_from_fluvial_dag=True,
    )


def whole_plain_metrics(spec, g, T, td_ocean):
    """Measure real low-plain area, lateral continuity and interior width.

    The footprint is the saved pre-channel geological surface from 0.02 to
    8 m, intersected with the actual construction support. Water cuts remain
    part of the plain footprint; dry land is also reported separately. The
    8 m diagnostic band is not a lithological or realism classification.
    """
    plain = T["whole_plain"]
    grid = T["grid"]
    dx = spec.spacing_m
    footprint = plain["active"] & (plain["bed"] >= 0.02) & (plain["bed"] <= 8.0)
    dry = footprint & T["land_dry"]
    source_land = footprint & ~td_ocean
    marine = footprint & td_ocean
    pts = np.argwhere(footprint)
    span = (np.ptp(pts, axis=0) * dx).tolist() if len(pts) else [0.0, 0.0]
    interior = ndi.distance_transform_edt(np.pad(footprint, 1))[1:-1, 1:-1] * dx
    core = interior >= 2000.0
    to_channels = ndi.distance_transform_edt(~T["chan"]) * dx
    widths = []
    for station in (-18000.0, -12000.0, -6000.0, -2000.0, 0.0, 2000.0, 6000.0, 12000.0, 20000.0, 28000.0):
        row = int(round((station - spec.u0_m) / dx - 0.5))
        if row < 0 or row >= spec.nu:
            continue
        col = int(np.clip(round(-spec.v0_m / dx - 0.5), 0, spec.nv - 1))
        if not footprint[row, col]:
            left = right = 0.0
        else:
            lo = col
            hi = col
            while lo > 0 and footprint[row, lo - 1]:
                lo -= 1
            while hi + 1 < spec.nv and footprint[row, hi + 1]:
                hi += 1
            left = (col - lo + 0.5) * dx
            right = (hi - col + 0.5) * dx
        widths.append(
            dict(
                u_m=float(station),
                left_plain_width_m=float(left),
                right_plain_width_m=float(right),
                total_continuous_width_m=float(left + right),
            )
        )
    inland_edge = (plain["landward_weight"] > 0.02) & (plain["landward_weight"] < 0.98) & ~td_ocean
    gu, gv = np.gradient(plain["bed"], dx)
    slope = np.hypot(gu, gv)[inland_edge]
    mouths = g.node_uv[g.mouth_nodes]
    return dict(
        footprint_definition="saved pre-channel geological surface in [0.02,8] m within construction support",
        plain_footprint_area_km2=float(footprint.sum() * dx**2 / 1e6),
        plain_dry_area_km2=float(dry.sum() * dx**2 / 1e6),
        source_landward_plain_area_km2=float(source_land.sum() * dx**2 / 1e6),
        source_marine_plain_area_km2=float(marine.sum() * dx**2 / 1e6),
        actual_plain_span_u_v_m=span,
        plain_distance_from_any_channel_m=dict(
            p50=float(np.median(to_channels[footprint])) if footprint.any() else 0.0,
            p90=float(np.percentile(to_channels[footprint], 90)) if footprint.any() else 0.0,
        ),
        plain_area_at_least_1km_from_channels_km2=float(
            (footprint & (to_channels >= 1000.0)).sum() * dx**2 / 1e6
        ),
        plain_area_at_least_2km_from_channels_km2=float(
            (footprint & (to_channels >= 2000.0)).sum() * dx**2 / 1e6
        ),
        plain_2km_interior_core_area_km2=float(core.sum() * dx**2 / 1e6),
        maximum_plain_interior_distance_m=float(interior.max()),
        alongstream_lateral_widths=widths,
        actual_mouth_span_u_v_m=np.ptp(mouths, axis=0).tolist(),
        landward_transition_slope_p50_p95=(
            np.percentile(slope, [50, 95]).tolist() if len(slope) else [0.0, 0.0]
        ),
        flat_footprint_touches_window=bool(footprint[[0, -1], :].any() or footprint[:, [0, -1]].any()),
        whole_plain_body_is_not_derived_from_river_fan=True,
        geological_initial_condition=True,
        physical_elapsed_seconds=0.0,
    )


class _PlainField:
    """Existing five-component steering interface sampled from saved terrain."""

    def __init__(self, grid, surface):
        self.grid = grid
        land = surface >= 0.0
        wet = ~land
        border = np.zeros(grid.shape, bool)
        border[[0, -1], :] = wet[[0, -1], :]
        border[:, [0, -1]] |= wet[:, [0, -1]]
        self.open_sea = ndi.binary_propagation(border, mask=wet)
        self.sea_float = self.open_sea.astype(float)
        d = (ndi.distance_transform_edt(land) - ndi.distance_transform_edt(wet)) * grid.dx
        d = ndi.gaussian_filter(d, max(1.0, 300.0 / grid.dx))
        # Least-cost travel to any actual coast steers across source lowlands
        # and around hills. Local DEM downhill alone gets trapped at flats and
        # allows the radial guide to excavate an arbitrary mountain crossing.
        coast = land & ndi.binary_dilation(self.open_sea)
        resistance = 1.0 + (np.maximum(surface - 4.0, 0.0) / 8.0) ** 2
        potential, _ = MCP_Geometric(resistance).find_costs(np.argwhere(coast))
        potential = ndi.gaussian_filter(potential, max(1.0, 200.0 / grid.dx))
        gu, gv = np.gradient(potential, grid.dx)
        routing_scale = np.hypot(gu, gv) + 1e-12
        terrain_strength = np.clip(
            ndi.gaussian_filter(np.maximum(surface - 4.0, 0.0), max(1.0, 650.0 / grid.dx)) / 12.0, 0.0, 1.0
        )
        gu = gu / routing_scale * 1e-4 * terrain_strength
        gv = gv / routing_scale * 1e-4 * terrain_strength
        nu, nv = np.gradient(d, grid.dx)
        scale = np.hypot(nu, nv) + 1e-12
        self.F = np.stack([d, -gu, -gv, -nu / scale, -nv / scale], axis=-1)

    def sample(self, u, v):
        grid = self.grid
        row = np.clip((u - grid.spec.u0_m) / grid.dx - 0.5, 0.0, grid.shape[0] - 1.001)
        col = np.clip((v - grid.spec.v0_m) / grid.dx - 0.5, 0.0, grid.shape[1] - 1.001)
        i, j = int(row), int(col)
        a, b = row - i, col - j
        return (
            self.F[i, j] * (1 - a) * (1 - b)
            + self.F[i + 1, j] * a * (1 - b)
            + self.F[i, j + 1] * (1 - a) * b
            + self.F[i + 1, j + 1] * a * b
        )

    def is_open_sea(self, u, v):
        return bool(self.grid.sample(self.sea_float, u, v) > 0.5)


def build(spec, td_bed, td_ocean, variant="base", delta_params=None, plain_params=None):
    """Return the real-coast DAG and matching, source-preserving terrain.

    The flow fan steers directions. The geometric boundary comes exclusively
    from the constructed source accommodation and original TD. All terminal
    water paths are part of the graph; no separate painted channel tails exist.
    """
    p = delta_params or parameters(
        variant,
        window_u_m=(spec.u0_m, spec.u0_m + spec.nu * spec.spacing_m),
        window_v_m=(spec.v0_m, spec.v0_m + spec.nv * spec.spacing_m),
    )
    tp = terrain_parameters()
    plain = whole_plain(spec, td_bed, td_ocean, plain_params)
    grid = _Grid(spec)
    field = _PlainField(grid, plain["bed"])
    g = sk.build_delta_network_v3(p, field_override=field, shore_test=field.is_open_sea)
    paths = [sk.edge_points(g, e).copy() for e in range(len(g.edge_from))]
    # The explicit catchment inflow is at the source node. Do not draw an
    # unsupported upstream river through the TD mountain to the window edge.
    mouths = []
    profiles = {}
    for node in g.mouth_nodes:
        eid = int(np.flatnonzero(g.edge_to == node)[0])
        P = paths[eid]
        direction = P[-1] - P[-2]
        direction /= np.linalg.norm(direction)
        end = P[-1]
        profiles[eid] = dict(
            has_marine_extension=False,
            final_extension_m=0.0,
            construction_mouth_uv_m=end.tolist(),
            base_width_m=float(g.edge_w[eid]),
            base_depth_m=float(g.edge_h[eid]),
            profile_semantics="Stop at actual source-controlled coast; no marine channel extension",
        )
        mouths.append(
            dict(
                node=int(node),
                pos=end.copy(),
                dir=direction.copy(),
                q=float(g.node_q[node]),
                share=float(g.node_q[node] / p.q_total),
                w=float(g.edge_w[eid]),
                h=float(g.edge_h[eid]),
                Le_m=0.0,
            )
        )
    g.pt_off = np.cumsum([0] + [len(P) for P in paths]).astype(np.int64)
    g.pts_uv = np.vstack(paths)
    g.edge_len = np.array([np.linalg.norm(np.diff(P, axis=0), axis=1).sum() for P in paths])
    g.construction_profiles = profiles
    g.geological_mouth_trims = []
    st = _Stamps(grid)
    surface = plain["bed"]
    for eid, P in enumerate(paths):
        P = _densify(P, tp.stamp_step_m)
        width = np.full(len(P), g.edge_w[eid])
        depth = np.full(len(P), g.edge_h[eid])
        stage = np.maximum(0.0, grid.sample(surface, P[:, 0], P[:, 1]) - tp.freeboard_m)
        st.add(
            P[:, 0], P[:, 1], width, depth, stage, np.zeros(len(P)), np.full(len(P), 60.0), tp.channel_floor
        )
    bed = np.where(st.chan, np.minimum(surface, st.bed), surface)
    env = surface >= 0.0
    water = (bed < 0.0) | st.chan
    dry = ~water
    labels, count = ndi.label(dry)
    border_ids = np.unique(np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]))
    mainland = np.isin(labels, border_ids[border_ids > 0])
    ids = np.unique(labels[(labels > 0) & ~mainland])
    remap = np.zeros(count + 1, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    islands = remap[labels]
    zeros = np.zeros(grid.shape, bool)
    ledger = dict(plain["ledger"])
    porosity = (plain_params or PlainParameters()).porosity
    ledger["channel_excavated_solid_m3"] = float(
        np.maximum(surface - bed, 0.0).sum() * grid.dx**2 * (1.0 - porosity)
    )
    ledger["channel_excavation_is_unresolved_construction_stock"] = True
    T = dict(
        grid=grid,
        bed=bed,
        water=water,
        land_env=env,
        land_dry=dry,
        chan=st.chan,
        tidal=zeros,
        spit=zeros.copy(),
        sand=zeros.copy(),
        island_label=islands,
        mainland=mainland,
        z_plain=surface,
        mouths=mouths,
        n_tidal_pts=0,
        n_creeks=0,
        n_bars=0,
        n_drowned=0,
        levee=st.lev,
        conn_build=dict(N=24.0, n_detached_removed=0),
        v4=dict(reused_skeleton=True, legacy_land_cones_applied=False),
        whole_plain=plain,
        geological_ledger=ledger,
        source_hill_preservation_mask=(~td_ocean)
        & (td_bed >= (plain_params or PlainParameters()).landward_elevation_limit_m)
        & ~st.chan,
    )
    return g, T, tp
