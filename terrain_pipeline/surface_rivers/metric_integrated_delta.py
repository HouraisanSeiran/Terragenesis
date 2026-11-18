"""Integrated reduced channel-tree morphodynamics for the stylized 16 km scene.

Public surface:

    ChannelTreeGeometry      - geometry bundle for the trunk/branch tree
    IntegratedDeltaConfig    - tuning knobs
    build_channel_tree(...)  - construct a geometry from raster + paths
    run_integrated_delta(...)- monthly simulation driver
    integrated_solid_ledger(...)
    manning_resistance_integral(...)
    wet_continuity_from_apex(...)
    wet_mask_from_stage(...)

The hydraulics are quasi-steady: each month we solve for the head at every
junction so that mass is conserved exactly at each junction, with Manning
friction integrated along each reach from the sampled bed.  Sediment is
routed topologically (trunk0 -> branch0/trunk1 -> branch1/2), and each reach
distributes its deposits into eligible wet raster cells whose headroom
(stage - bed) is positive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    from scipy.optimize import brentq
    from scipy.spatial import cKDTree
    from scipy import ndimage as _ndimage
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "scipy is required for metric_integrated_delta (brentq, cKDTree)"
    ) from exc


def _trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@dataclass
class ChannelPath:
    name: str
    points_xz: np.ndarray
    width_m: float
    upstream: Optional[str] = None
    outlets_to_sea: bool = False
    junction: Optional[int] = None

    def arc_length_m(self) -> np.ndarray:
        seg = np.linalg.norm(np.diff(self.points_xz, axis=0), axis=1)
        return np.concatenate([[0.0], np.cumsum(seg)])


@dataclass
class ChannelTreeGeometry:
    paths: Dict[str, ChannelPath]
    apex_xz: np.ndarray
    junction_1_xz: np.ndarray
    junction_2_xz: np.ndarray
    sea_xz: Dict[str, np.ndarray]
    origin_xz: np.ndarray
    spacing_m: float
    raster_shape: Tuple[int, int]
    protected_mask: np.ndarray
    eligible_mask: np.ndarray
    ocean_mask: np.ndarray
    # Per-cell nearest path/station mapping.
    cell_owner: np.ndarray = None
    cell_station: np.ndarray = None
    cell_distance: np.ndarray = None
    cell_station_s: np.ndarray = None  # cumulative arc length at that station

    def path_names(self) -> List[str]:
        return list(self.paths.keys())


def build_channel_tree(
    initial_bed_m: np.ndarray,
    origin_xz: Sequence[float],
    spacing_m: float,
    mouth_xz: Sequence[float],
    apex_xz: Sequence[float],
    trunk_path_xz: np.ndarray,
    branch_paths_xz: Sequence[np.ndarray],
    widths_m: Sequence[float],
    ocean_mask: Optional[np.ndarray] = None,
    trunk_split_station: Optional[int] = None,
    branch_split_station: Optional[int] = None,
    eligible_band_m: float = 1000.0,
    protected_band_m: float = 50.0,
    branch_parent_index: Optional[Sequence[int]] = None,
) -> ChannelTreeGeometry:
    origin = np.asarray(origin_xz, dtype=np.float64)
    spacing = float(spacing_m)
    if not math.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("spacing_m must be positive finite")
    bed = np.asarray(initial_bed_m, dtype=np.float64)
    if bed.ndim != 2 or not np.isfinite(bed).all():
        raise ValueError("initial_bed_m must be a finite 2D array")
    rows, cols = bed.shape
    if ocean_mask is None:
        ocean = bed <= 0.0
    else:
        ocean = np.asarray(ocean_mask, dtype=bool).copy()
    if ocean.shape != bed.shape:
        raise ValueError("ocean_mask must match initial_bed_m shape")

    trunk = np.asarray(trunk_path_xz, dtype=np.float64)
    branches = [np.asarray(b, dtype=np.float64) for b in branch_paths_xz]
    if trunk.ndim != 2 or trunk.shape[1] != 2:
        raise ValueError("trunk_path_xz must be (N, 2)")
    if len(branches) < 1:
        raise ValueError("branch_paths_xz must contain at least one terminal branch")
    for b in branches:
        if b.ndim != 2 or b.shape[1] != 2:
            raise ValueError("each branch path must be (N, 2)")

    if trunk_split_station is None:
        trunk_split_station = len(trunk) // 2
    if branch_split_station is None:
        branch_split_station = len(trunk) - 1
    trunk_split_station = int(trunk_split_station)
    branch_split_station = int(branch_split_station)
    if not 1 <= trunk_split_station < branch_split_station < len(trunk):
        raise ValueError("invalid trunk/branch split stations")

    junction_1 = trunk[trunk_split_station].copy()
    junction_2 = trunk[branch_split_station].copy()

    trunk0 = trunk[: trunk_split_station + 1].copy()
    trunk1 = trunk[trunk_split_station : branch_split_station + 1].copy()

    if len(widths_m) != len(branches)+1:
        raise ValueError("expected four widths (trunk, b0, b1, b2)")
    w_trunk = float(widths_m[0])

    if len(branches) == 3 and branch_parent_index is None:
        b0, b1, b2 = (b.copy() for b in branches)
        if np.linalg.norm(b0[0] - junction_1) > 1e-6: b0 = np.vstack([junction_1[None, :], b0])
        if np.linalg.norm(b1[0] - junction_2) > 1e-6: b1 = np.vstack([junction_2[None, :], b1])
        if np.linalg.norm(b2[0] - junction_2) > 1e-6: b2 = np.vstack([junction_2[None, :], b2])
        paths = {"trunk0": ChannelPath("trunk0", trunk0, w_trunk, upstream=None, outlets_to_sea=False, junction=1),
                 "trunk1": ChannelPath("trunk1", trunk1, w_trunk, upstream="trunk0", outlets_to_sea=False, junction=2),
                 "branch0": ChannelPath("branch0", b0, float(widths_m[1]), upstream="trunk0", outlets_to_sea=True, junction=None),
                 "branch1": ChannelPath("branch1", b1, float(widths_m[2]), upstream="trunk1", outlets_to_sea=True, junction=None),
                 "branch2": ChannelPath("branch2", b2, float(widths_m[3]), upstream="trunk1", outlets_to_sea=True, junction=None)}
    else:
        parents = np.full(len(branches), -1, dtype=int) if branch_parent_index is None else np.asarray(branch_parent_index, dtype=int)
        if parents.shape != (len(branches),) or np.any(parents < -1) or np.any(parents >= len(branches)):
            raise ValueError("one valid parent index required per branch")
        paths = {}
        child_stations = {-1: [] , **{i: [] for i in range(len(branches))}}
        for i, parent in enumerate(parents):
            seen = {i}; ancestor = int(parent)
            while ancestor >= 0:
                if ancestor in seen: raise ValueError("cyclic branch parents")
                seen.add(ancestor); ancestor = int(parents[ancestor])
            parent_points = trunk if parent == -1 else branches[parent]
            station = int(np.argmin(np.linalg.norm(parent_points-branches[i][0], axis=1)))
            if np.linalg.norm(parent_points[station]-branches[i][0]) > spacing:
                raise ValueError("child must start on its declared parent")
            child_stations[int(parent)].append((station, i))
        # Insert the actual child junction into each parent before splitting,
        # so all incident reaches share the same geometric endpoint.
        for parent in child_stations:
            points = trunk if parent == -1 else branches[parent]
            for _, child in child_stations[parent]:
                point = branches[child][0]
                delta = np.diff(points, axis=0)
                fraction = np.clip(np.sum((point-points[:-1])*delta, axis=1)/np.sum(delta*delta, axis=1), 0., 1.)
                segment = int(np.argmin(np.linalg.norm(points[:-1]+fraction[:, None]*delta-point, axis=1)))
                if np.min(np.linalg.norm(points-point, axis=1)) > 1.e-8:
                    points = np.insert(points, segment+1, point, axis=0)
            if parent == -1: trunk = points
            else: branches[parent] = points
            child_stations[parent] = [(int(np.argmin(np.linalg.norm(points-branches[child][0], axis=1))), child)
                                      for _, child in child_stations[parent]]
        def add_segments(index, upstream=None):
            points = trunk if index == -1 else branches[index]
            width = w_trunk if index == -1 else float(widths_m[index+1])
            start = 0; prior = upstream
            for serial, station in enumerate(sorted(set(s for s, _ in child_stations[index]))):
                if station > start:
                    name = f"reach{index}_{serial}"
                    paths[name] = ChannelPath(name, points[start:station+1].copy(), width, prior)
                    prior = name
                for _, child in [item for item in child_stations[index] if item[0] == station]:
                    add_segments(child, prior)
                start = station
            if index >= 0:
                name = f"terminal{index}"
                paths[name] = ChannelPath(name, points[start:].copy(), width, prior, True)
            elif start < len(points)-1:
                raise ValueError("trunk must end at its final branch junction")
        add_segments(-1)

    # --- Raster mapping ---------------------------------------------------
    samples_list: List[np.ndarray] = []
    owner_list: List[np.ndarray] = []
    station_list: List[np.ndarray] = []
    station_s_list: List[np.ndarray] = []
    for idx, name in enumerate(paths):
        pts = paths[name].points_xz
        s = paths[name].arc_length_m()
        samples_list.append(pts)
        owner_list.append(np.full(len(pts), idx, dtype=np.int64))
        station_list.append(np.arange(len(pts), dtype=np.int64))
        station_s_list.append(s)
    samples_all = np.vstack(samples_list)
    owner_all = np.concatenate(owner_list)
    station_all = np.concatenate(station_list)
    station_s_all = np.concatenate(station_s_list)
    path_index = {name: i for i, name in enumerate(paths)}

    grid_x = origin[0] + spacing * np.arange(cols)
    grid_z = origin[1] + spacing * np.arange(rows)
    gx, gz = np.meshgrid(grid_x, grid_z, indexing="xy")
    flat = np.column_stack([gx.ravel(), gz.ravel()])

    tree = cKDTree(samples_all)
    dist, idx = tree.query(flat, k=1)
    dist = dist.reshape(rows, cols)
    idx = idx.reshape(rows, cols)
    owner = owner_all[idx]
    station_r = station_all[idx]
    station_s_r = station_s_all[idx]

    within_band = dist <= eligible_band_m + 1e-9

    apex = np.asarray(apex_xz, dtype=np.float64)
    mouth = np.asarray(mouth_xz, dtype=np.float64)
    downstream = mouth - apex
    norm = float(np.linalg.norm(downstream))
    if norm <= 0.0:
        raise ValueError("apex and mouth must differ")
    downstream = downstream / norm
    rel_x = gx - apex[0]
    rel_z = gz - apex[1]
    along = rel_x * downstream[0] + rel_z * downstream[1]
    upstream_side = along < -spacing*.1
    protected = upstream_side | (~within_band)
    eligible = ~protected

    return ChannelTreeGeometry(
        paths=paths,
        apex_xz=apex.copy(),
        junction_1_xz=junction_1.copy(),
        junction_2_xz=junction_2.copy(),
            sea_xz={name: paths[name].points_xz[-1].copy()
                    for name in paths if paths[name].outlets_to_sea},
        origin_xz=origin.copy(),
        spacing_m=spacing,
        raster_shape=(rows, cols),
        protected_mask=protected,
        eligible_mask=eligible,
        ocean_mask=ocean,
        cell_owner=owner,
        cell_station=station_r,
        cell_distance=dist,
        cell_station_s=station_s_r,
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class IntegratedDeltaConfig:
    roughness: float = 0.035
    bin_length_m: float = 100.0
    settling_velocity_m_s: float = 1.0e-4
    residence_depth_m: float = 1.0
    porosity: float = 0.35
    capacity_coefficient: float = 2.0e-4
    capacity_reference_velocity_m_s: float = 1.0
    shear_threshold_pa: float = 0.1
    solid_density_kg_m3: float = 2650.0
    water_density_kg_m3: float = 1000.0
    sea_level_m: float = 0.0
    g: float = 9.81


@dataclass
class ReachHydraulics:
    name: str
    head_up: float
    head_dn: float
    q_m3_s: float
    depth_m: float
    manning_resistance: float
    wet: bool


@dataclass
class MonthlyRecord:
    water_input_m3: float
    solid_input_m3: float
    q_branch0_m3_s: float
    q_branch1_m3_s: float
    q_branch2_m3_s: float
    q_trunk0_m3_s: float
    q_trunk1_m3_s: float
    head_junction1_m: float
    head_junction2_m: float
    head_source_m: float
    deposition_solid_m3: float
    reentrainment_solid_m3: float
    export_solid_m3: float
    escrow_solid_m3: float
    mass_error_m3: float
    terminal_q_m3_s: tuple = field(default_factory=tuple)
    terminal_export_m3: tuple = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Manning
# ---------------------------------------------------------------------------


def manning_resistance_integral(
    s_m: np.ndarray,
    depth_m: np.ndarray,
    width_m: float,
    n: float,
) -> float:
    if width_m <= 0.0 or n <= 0.0:
        raise ValueError("positive width and roughness required")
    s = np.asarray(s_m, dtype=np.float64)
    h = np.asarray(depth_m, dtype=np.float64)
    if s.shape != h.shape or s.ndim != 1:
        raise ValueError("matching 1D arrays required")
    if np.any(~np.isfinite(h)) or np.any(h <= 0.0):
        return math.inf
    area = width_m * h
    perimeter = width_m + 2.0 * h
    radius = area / perimeter
    integrand = (n ** 2) / (area ** 2 * radius ** (4.0 / 3.0))
    if s.size < 2:
        return 0.0
    ds = np.diff(s)
    seg = 0.5 * (integrand[:-1] + integrand[1:])
    return float(np.sum(seg * ds))


def sample_bed_along_path(
    bed_m: np.ndarray,
    origin_xz: np.ndarray,
    spacing_m: float,
    path_xz: np.ndarray,
) -> np.ndarray:
    cols = np.rint((path_xz[:, 0] - origin_xz[0]) / spacing_m).astype(np.int64)
    rows = np.rint((path_xz[:, 1] - origin_xz[1]) / spacing_m).astype(np.int64)
    rows = np.clip(rows, 0, bed_m.shape[0] - 1)
    cols = np.clip(cols, 0, bed_m.shape[1] - 1)
    return bed_m[rows, cols]


def _reach_q(
    bed_along: np.ndarray,
    s_m: np.ndarray,
    head_up: float,
    head_dn: float,
    width_m: float,
    n: float,
) -> Tuple[float, float]:
    """q and mean depth for a reach given endpoint heads.

    Linear water-surface profile; requires positive depth at every sample.
    """
    if head_up <= head_dn:
        return 0.0, 0.0
    s_total = max(float(s_m[-1]), 1e-9)
    frac = s_m / s_total
    stage = head_up + (head_dn - head_up) * frac
    depth = stage - bed_along
    if np.any(~np.isfinite(depth)) or np.any(depth <= 1e-6):
        return 0.0, 0.0
    R = manning_resistance_integral(s_m, depth, width_m, n)
    if not math.isfinite(R) or R <= 0.0:
        return 0.0, 0.0
    q = math.sqrt((head_up - head_dn) / R)
    return q, float(np.mean(depth))


# ---------------------------------------------------------------------------
# Wet mask
# ---------------------------------------------------------------------------


def wet_mask_from_stage(
    bed_m: np.ndarray,
    stage_m: np.ndarray,
    ocean_mask: np.ndarray,
) -> np.ndarray:
    wet = bed_m < stage_m
    return wet


def _compute_stage_raster(bed_m, geometry, heads, wet_seeds_channel, ocean_mask, sea_level):
    """D4-connected inundation under the local channel-tree head approximation."""
    stage = bed_m.copy()
    for i, (name, path) in enumerate(geometry.paths.items()):
        fraction = np.clip(geometry.cell_station_s/path.arc_length_m()[-1], 0., 1.)
        hu, hd = heads[name]
        mask = (geometry.cell_owner == i) & geometry.eligible_mask
        stage[mask] = (hu+(hd-hu)*fraction)[mask]
    ocean = _ocean_boundary_wet(bed_m, ocean_mask, sea_level)
    stage[ocean] = np.maximum(stage[ocean], sea_level)
    candidate = bed_m < stage
    seeds = ocean.copy()
    cc, rr = np.rint((geometry.apex_xz-geometry.origin_xz)/geometry.spacing_m).astype(int)
    rr, cc = int(np.clip(rr, 0, bed_m.shape[0]-1)), int(np.clip(cc, 0, bed_m.shape[1]-1))
    seeds[rr, cc] |= candidate[rr, cc]
    wet = _ndimage.binary_propagation(seeds, mask=candidate,
        structure=np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=bool))
    stage = np.where(wet, stage, bed_m)
    return stage, np.where(wet, stage-bed_m, 0.)


def _solve_hydraulics(geometry, bed_along, s_along, q_target, config):
    """Solve junction continuity, then the source head, with scalar roots."""
    sea = config.sea_level_m
    def q_of(name, hu, hd):
        return _reach_q(bed_along[name], s_along[name], hu, hd,
                        geometry.paths[name].width_m, config.roughness)
    def bracket_root(function, low, initial_high):
        high = max(initial_high, low+1.)
        for _ in range(32):
            if function(high) >= 0.:
                return brentq(function, low, high, xtol=1.e-15, rtol=1.e-14)
            high = low+2.*(high-low)
            if high > 10000.:
                break
        raise ValueError("cannot route prescribed positive flow through channel tree")
    def inner(h1):
        if h1 <= sea:
            return sea, 0.
        def balance(h2):
            return q_of("trunk1", h1, h2)[0]-q_of("branch1", h2, sea)[0]-q_of("branch2", h2, sea)[0]
        low, high = sea, h1
        if balance(low) == 0.:
            # A dry downstream trunk endpoint creates a zero-flow plateau.
            # Find the flowing root above it instead of accepting that plateau.
            trials = np.linspace(sea, h1, 129)
            values = np.array([balance(h) for h in trials])
            positive = np.flatnonzero(values > 0.)
            if not len(positive):
                return sea, 0.
            index = int(positive[-1])
            low, high = float(trials[index]), float(trials[index+1])
        h2 = brentq(balance, low, high, xtol=1.e-15, rtol=1.e-14)
        return h2, q_of("trunk1", h1, h2)[0]
    if q_target <= 0.:
        heads = {nm:(sea,sea) for nm in geometry.paths}
        return heads, {nm:0. for nm in heads}, {nm:0. for nm in heads}
    # Zero-head plateaux represent genuinely dry paths, not artificial minimum flow.
    h1 = bracket_root(lambda h:q_of("branch0", h, sea)[0]+inner(h)[1]-q_target,
                      sea, max(1., max(float(np.max(v)) for v in bed_along.values())+2.))
    h2, _ = inner(h1)
    hs = bracket_root(lambda h:q_of("trunk0", h, h1)[0]-q_target, h1, h1+1.)
    heads = dict(trunk0=(hs,h1), trunk1=(h1,h2), branch0=(h1,sea),
                 branch1=(h2,sea), branch2=(h2,sea))
    qs, depths = {}, {}
    for name, (hu,hd) in heads.items():
        qs[name], depths[name] = q_of(name,hu,hd)
    residuals = (qs["trunk0"]-q_target,
                 qs["trunk0"]-qs["branch0"]-qs["trunk1"],
                 qs["trunk1"]-qs["branch1"]-qs["branch2"])
    if max(abs(v) for v in residuals) > max(1.e-7, q_target*1.e-8):
        raise ArithmeticError("hydraulic junction continuity failed")
    return heads, qs, depths


def _solve_terminal_hydraulics(bed_along, s_along, widths_m, q_target, roughness,
                               sea_level=0.0):
    """Route one rooted trunk into any number of terminal outlets."""
    widths = np.asarray(widths_m, dtype=float)
    if widths.ndim != 1 or len(widths) < 1 or np.any(widths <= 0.):
        raise ValueError("terminal widths must be a nonempty positive vector")
    if len(bed_along) != len(widths) or len(s_along) != len(widths):
        raise ValueError("one bed and station profile is required per terminal")
    if q_target < 0. or not np.isfinite(q_target):
        raise ValueError("target flow must be finite and nonnegative")
    if q_target == 0.:
        return np.zeros(len(widths)), np.full(len(widths), sea_level)
    shares = widths / widths.sum()
    q = q_target*shares
    heads = np.empty(len(widths))
    for index, (bed, station, width, flow) in enumerate(zip(bed_along, s_along, widths, q)):
        low = max(sea_level+1.e-9, float(np.max(bed))+1.e-6)
        high = low+1.
        while _reach_q(np.asarray(bed), np.asarray(station), high, sea_level, width, roughness)[0] < flow:
            high = low+2.*(high-low)
            if high > 1.e6:
                raise ValueError("cannot route terminal flow")
        heads[index] = brentq(lambda value: _reach_q(np.asarray(bed), np.asarray(station), value,
                                                       sea_level, width, roughness)[0]-flow, low, high)
    return q, heads


def route_terminal_load(load_m3, terminal_q_m3_s, dt_s):
    """Split a finite load by terminal flow, returning terminal exports."""
    q = np.asarray(terminal_q_m3_s, dtype=float)
    if q.ndim != 1 or np.any(q < 0.) or not np.isfinite(q).all() or load_m3 < 0. or dt_s <= 0.:
        raise ValueError("finite nonnegative terminal flow and load are required")
    total = float(q.sum())
    return np.zeros_like(q) if total == 0. else float(load_m3)*q/total


def _route_reach(bed, initial, stage, wet, path, geom, q, depth, load, dt_s,
                 config, store, gross, entrained, heads):
    """Route downstream, exchanging only finite raster solids at each bin."""
    if q <= 0.:
        return load, 0., 0.
    area_factor = geom.spacing_m**2 * (1.-config.porosity)
    path_idx = list(geom.paths).index(path.name)
    arc = path.arc_length_m()
    edges = np.linspace(0., arc[-1], max(1, int(np.ceil(arc[-1]/config.bin_length_m)))+1)
    owned = (geom.cell_owner == path_idx) & geom.eligible_mask & wet
    total_dep = total_ent = 0.
    slope = max(0., (heads[0]-heads[1])/arc[-1])
    shear = config.water_density_kg_m3*config.g*depth*slope
    velocity = q/max(path.width_m*depth, 1.e-12)
    capacity = config.capacity_coefficient*q*dt_s*(velocity/config.capacity_reference_velocity_m_s)**2
    for b, (s0, s1) in enumerate(zip(edges[:-1], edges[1:])):
        mask = owned & (geom.cell_station_s >= s0) & (geom.cell_station_s < s1 if b < len(edges)-2 else geom.cell_station_s <= s1)
        rr, cc = np.nonzero(mask)
        if not len(rr):
            continue
        available = store[rr, cc]
        amount = float(available.sum())
        local_depth = np.maximum(stage[rr, cc]-bed[rr, cc], 0.)
        # Floodplain flow loses momentum away from the channel; it cannot scour
        # shallow shelves with the full channel-average boundary shear.
        mobility = np.exp(-(geom.cell_distance[rr, cc]/path.width_m)**2)
        local_shear = shear*mobility*np.minimum(local_depth/max(depth, 1.e-12), 1.)
        erodible = available*np.where(local_shear > config.shear_threshold_pa, mobility, 0.)
        erodible_total = float(erodible.sum())
        if erodible_total > 0.:
            take = min(erodible_total, max(capacity-load, 0.)*.1)
            remove = erodible*(take/erodible_total)
            store[rr, cc] -= remove
            entrained[rr, cc] += remove
            bed[rr, cc] = initial[rr, cc] + store[rr, cc]/area_factor
            load += take
            total_ent += take
        fraction = -math.expm1(-config.settling_velocity_m_s*(s1-s0)/max(velocity*depth, 1.e-12))
        desired = max(load-capacity, 0.) + min(load, capacity)*fraction
        headroom = np.maximum(stage[rr, cc]-bed[rr, cc], 0.)*area_factor
        room = float(headroom.sum())
        if room > 0. and desired > 0.:
            # Slow shallow overbank water settles efficiently, with finite
            # lateral exchange declining over four prescribed channel widths.
            preference = np.exp(-geom.cell_distance[rr, cc]/(4.*path.width_m))/np.maximum(local_depth, .25)
            allocation = np.zeros_like(headroom)
            remaining = min(desired, room)
            for _ in range(len(rr)+1):
                capacity_left = np.maximum(headroom-allocation, 0.)
                weights = capacity_left*preference
                weight_sum = float(weights.sum())
                if remaining <= 1.e-12 or weight_sum <= 0.:
                    break
                increment = np.minimum(remaining*weights/weight_sum, capacity_left)
                allocation += increment
                remaining -= float(increment.sum())
            deposited = float(allocation.sum())
            store[rr, cc] += allocation
            gross[rr, cc] += allocation
            bed[rr, cc] = initial[rr, cc] + store[rr, cc]/area_factor
            total_dep += deposited
            load -= deposited
    return max(load, 0.), total_dep, total_ent


def _ocean_boundary_wet(bed_m: np.ndarray, ocean_mask: np.ndarray, sea_level: float) -> np.ndarray:
    below = (bed_m < sea_level) & ocean_mask
    if not below.any():
        return np.zeros_like(below)
    seed = np.zeros_like(below)
    seed[0, :] |= below[0, :]
    seed[-1, :] |= below[-1, :]
    seed[:, 0] |= below[:, 0]
    seed[:, -1] |= below[:, -1]
    if not seed.any():
        return seed
    struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
    return _ndimage.binary_propagation(seed, mask=below, structure=struct)


def run_integrated_delta(initial_bed_m, geometry, monthly_water_m3, monthly_solid_m3,
                         month_seconds, config=None):
    """Conservative monthly one-way forcing with local bed/hydraulic feedback."""
    config = config or IntegratedDeltaConfig()
    if any(name.startswith("terminal") for name in geometry.paths):
        return _run_terminal_only(initial_bed_m, geometry, monthly_water_m3, monthly_solid_m3, month_seconds, config)
    initial = np.array(initial_bed_m, dtype=float, copy=True)
    bed = initial.copy()
    water, solid, dt = [np.asarray(a, dtype=float) for a in
                        (monthly_water_m3, monthly_solid_m3, month_seconds)]
    if water.ndim != 1 or water.shape != solid.shape or water.shape != dt.shape:
        raise ValueError("forcing must be equally sized one-dimensional arrays")
    if not all(np.isfinite(a).all() for a in (initial, water, solid, dt)):
        raise ValueError("finite bed and forcing required")
    if np.any(water < 0.) or np.any(solid < 0.) or np.any(dt <= 0.) or not len(dt):
        raise ValueError("nonnegative volumes and positive nonempty durations required")
    if initial.shape != geometry.raster_shape:
        raise ValueError("geometry/bed shape mismatch")
    for name, value in vars(config).items():
        if not math.isfinite(value):
            raise ValueError("finite config required: "+name)
    if not 0. <= config.porosity < 1. or config.roughness <= 0. or config.bin_length_m <= 0. or config.settling_velocity_m_s < 0. or config.capacity_coefficient < 0. or config.shear_threshold_pa < 0.:
        raise ValueError("invalid material or hydraulic config")
    if config.capacity_reference_velocity_m_s <= 0. or config.g <= 0. or config.water_density_kg_m3 <= 0.:
        raise ValueError("positive velocity reference, gravity and water density required")
    store = np.zeros_like(bed)
    gross = np.zeros_like(bed)
    entrained = np.zeros_like(bed)
    seed = np.zeros_like(bed, dtype=bool)
    for path in geometry.paths.values():
        cc, rr = np.rint((path.points_xz-geometry.origin_xz)/geometry.spacing_m).astype(int).T
        seed[np.clip(rr, 0, bed.shape[0]-1), np.clip(cc, 0, bed.shape[1]-1)] = True
    def hydraulics(q):
        beds = {nm: sample_bed_along_path(bed, geometry.origin_xz, geometry.spacing_m, p.points_xz)
                for nm, p in geometry.paths.items()}
        arcs = {nm: p.arc_length_m() for nm, p in geometry.paths.items()}
        heads, qs, depths = _solve_hydraulics(geometry, beds, arcs, q, config)
        if q > 0.:
            stage, depth = _compute_stage_raster(bed, geometry, heads, seed, geometry.ocean_mask, config.sea_level_m)
        else:
            ocean = _ocean_boundary_wet(bed, geometry.ocean_mask, config.sea_level_m)
            stage = np.where(ocean, config.sea_level_m, bed)
            depth = np.maximum(stage-bed, 0.)
        return heads, qs, depths, stage, depth
    records, wet_history, land_history, terminal_history = [], [], [], []
    escrow = cumulative_export = 0.
    for volume, supply, seconds in zip(water, solid, dt):
        previous = float(store.sum()) + escrow
        load = float(supply)+escrow
        heads, qs, depths, stage, depth = hydraulics(float(volume/seconds))
        wet = depth > 0.
        deposited = reentrained = 0.
        terminal = np.zeros(3)
        if volume == 0.:
            escrow = load
        else:
            escrow = 0.
            def route(name, incoming):
                nonlocal deposited, reentrained
                outgoing, dep, ent = _route_reach(bed, initial, stage, wet, geometry.paths[name],
                    geometry, qs[name], depths[name], incoming, float(seconds), config,
                    store, gross, entrained, heads[name])
                deposited += dep
                reentrained += ent
                return outgoing
            load = route("trunk0", load)
            total = qs["branch0"]+qs["trunk1"]
            if total <= 0.:
                raise ValueError("positive source flow has no flowing receiver")
            first = load*qs["branch0"]/total
            terminal[0] = route("branch0", first)
            load = route("trunk1", load-first)
            total = qs["branch1"]+qs["branch2"]
            if total > 0.:
                first = load*qs["branch1"]/total
                terminal[1] = route("branch1", first)
                terminal[2] = route("branch2", load-first)
            else:
                escrow += load
        export = float(terminal.sum())
        cumulative_export += export
        residual = previous+float(supply)-float(store.sum())-escrow-export
        if abs(residual) > 1.e-8*max(1., previous+float(supply)):
            raise ArithmeticError("solid balance failed")
        # Bed is always derived from the sole finite natural-solid inventory.
        bed[:] = initial+store/(geometry.spacing_m**2*(1.-config.porosity))
        records.append(MonthlyRecord(float(volume), float(supply),
            qs["branch0"], qs["branch1"], qs["branch2"], qs["trunk0"], qs["trunk1"],
            heads["trunk0"][1], heads["trunk1"][1], heads["trunk0"][0],
            deposited, reentrained, export, escrow, residual))
        wet_history.append(wet.copy())
        land_history.append(float(store[initial > 0.].sum()))
        terminal_history.append(terminal)
    heads, qs, depths, stage, depth = hydraulics(float(water[-1]/dt[-1]))
    return dict(initial_bed_m=initial, final_bed_m=bed, height_delta_m=bed-initial,
        deposited_solid_m3=gross, reentrained_solid_m3=entrained, stored_solid_m3=store,
        stage_m=stage, depth_m=depth, wet_timeseries=np.asarray(wet_history),
        eligible_mask=geometry.eligible_mask.copy(), protected_mask=geometry.protected_mask.copy(),
        ocean_mask=geometry.ocean_mask.copy(), records=records,
        cumulative_export_solid_m3=cumulative_export, cumulative_deposit_solid_m3=float(gross.sum()),
        cumulative_reentrain_solid_m3=float(entrained.sum()), config=config,
        porosity=config.porosity, cell_area_m2=geometry.spacing_m**2, geometry=geometry,
        monthly_land_stored_solid_m3=np.asarray(land_history),
        monthly_terminal_export_solid_m3=np.asarray(terminal_history),
        final_heads_m=np.asarray([heads["trunk0"][0], heads["trunk0"][1], heads["trunk1"][1]]))


def _run_terminal_only(initial_bed_m, geometry, monthly_water_m3, monthly_solid_m3, month_seconds, config):
    """Conservative rooted trunk with N terminal reaches."""
    initial = np.asarray(initial_bed_m, dtype=float).copy()
    water, solid, dt = (np.asarray(v, dtype=float) for v in (monthly_water_m3, monthly_solid_m3, month_seconds))
    if water.ndim != 1 or water.shape != solid.shape or water.shape != dt.shape or not len(dt):
        raise ValueError("matching nonempty one-dimensional forcing required")
    if not all(np.isfinite(v).all() for v in (initial, water, solid, dt)) or np.any(water < 0.) or np.any(solid < 0.) or np.any(dt <= 0.):
        raise ValueError("finite nonnegative forcing and positive durations required")
    terminals = sorted((name for name in geometry.paths if name.startswith("terminal")), key=lambda name: int(name[8:]))
    children = {name: [] for name in geometry.paths}
    roots = []
    for name, path in geometry.paths.items():
        if path.upstream is None: roots.append(name)
        else: children[path.upstream].append(name)
    previous_node_heads = None
    def hydraulics(target, bed):
        nonlocal previous_node_heads
        from scipy.optimize import least_squares
        names = list(geometry.paths)
        nodes = [None] + [name for name in names if children[name]]
        positions = {name: i for i, name in enumerate(nodes)}
        profiles = {name: sample_bed_along_path(bed, geometry.origin_xz, geometry.spacing_m, path.points_xz) for name, path in geometry.paths.items()}
        def evaluate(values):
            heads = {}; qs = {}; depths = {}
            for name, path in geometry.paths.items():
                hu = values[positions[path.upstream]]
                hd = values[positions[name]] if children[name] else config.sea_level_m
                heads[name] = (float(hu), float(hd))
                qs[name], depths[name] = _reach_q(profiles[name], path.arc_length_m(), hu, hd, path.width_m, config.roughness)
            residual = [sum(qs[name] for name in roots)-target]
            residual.extend(qs[name]-sum(qs[child] for child in children[name]) for name in nodes[1:])
            return np.asarray(residual), heads, qs, depths
        if target == 0.:
            values = np.full(len(nodes), config.sea_level_m)
        else:
            floor = max(config.sea_level_m, max(float(profile.max()) for profile in profiles.values())) + 1.
            cold_start = np.array([floor + len(nodes)-i for i in range(len(nodes))])
            guesses = [cold_start] if previous_node_heads is None else [previous_node_heads, cold_start]
            for guess in guesses:
                fit = least_squares(lambda v: evaluate(v)[0], guess, bounds=(config.sea_level_m+1.e-7, np.inf), max_nfev=2000, xtol=1.e-12, ftol=1.e-12, gtol=1.e-12)
                values = fit.x
                if np.max(np.abs(evaluate(values)[0])) <= 1.e-6*max(1., target):
                    break
            if np.max(np.abs(evaluate(values)[0])) > 1.e-6*max(1., target):
                dry = {name: float(np.min(np.linspace(evaluate(values)[1][name][0], evaluate(values)[1][name][1], len(profiles[name]))-profiles[name])) for name in names}
                failure = ValueError(f"tree hydraulic continuity solve failed: Q={target}, heads={values.tolist()}, minimum_depths={dry}")
                failure.hydraulic_diagnostics = dict(target=target, heads=values,
                    names=names, nodes=[str(n) for n in nodes],
                    profiles=profiles, arcs={n:geometry.paths[n].arc_length_m() for n in names},
                    widths={n:geometry.paths[n].width_m for n in names},
                    upstream={n:str(geometry.paths[n].upstream) for n in names})
                raise failure
        residual, heads, qs, depths = evaluate(values)
        previous_node_heads = np.maximum(values.copy(), config.sea_level_m+1.e-6)
        return values, heads, qs, depths, float(np.max(np.abs(residual)))
    beds = [sample_bed_along_path(initial, geometry.origin_xz, geometry.spacing_m, geometry.paths[name].points_xz) for name in terminals]
    arcs = [geometry.paths[name].arc_length_m() for name in terminals]
    widths = [geometry.paths[name].width_m for name in terminals]
    store = np.zeros_like(initial); gross = np.zeros_like(initial); entrained = np.zeros_like(initial)
    seed = np.zeros_like(initial, dtype=bool)
    for path in geometry.paths.values():
        cc, rr = np.rint((path.points_xz-geometry.origin_xz)/geometry.spacing_m).astype(int).T
        seed[np.clip(rr, 0, initial.shape[0]-1), np.clip(cc, 0, initial.shape[1]-1)] = True
    records = []; history = []; terminal_history = []; land_history = []; head_history = []; hydraulic_residuals = []
    cumulative = 0.; escrow = 0.; bed = initial.copy()
    for volume, supply, seconds in zip(water, solid, dt):
        previous = float(store.sum()) + escrow
        bed[:] = initial+store/(geometry.spacing_m**2*(1.-config.porosity))
        node_heads, heads, qs, depths, hydraulic_residual = hydraulics(float(volume/seconds), bed)
        q = np.array([qs[name] for name in terminals])
        terminal_heads = np.array([heads[name][0] for name in terminals])
        stage, depth = _compute_stage_raster(bed_m=bed,
            geometry=geometry, heads=heads, wet_seeds_channel=seed, ocean_mask=geometry.ocean_mask,
            sea_level=config.sea_level_m)
        wet = depth > 0.
        exports = np.zeros(len(terminals)); load = float(supply)+escrow
        escrow = 0.
        deposited = reentrained = 0.
        def route(name, part):
            nonlocal deposited, reentrained
            outgoing, dep, ent = _route_reach(bed, initial, stage, wet, geometry.paths[name], geometry,
                qs[name], depths[name], part,
                float(seconds), config, store, gross, entrained, heads[name])
            deposited += dep; reentrained += ent
            if not children[name]: exports[terminals.index(name)] = outgoing
            else:
                total = sum(qs[child] for child in children[name])
                for child in children[name]: route(child, outgoing*qs[child]/total if total else 0.)
        if volume > 0.:
            total = sum(qs[name] for name in roots)
            for name in roots: route(name, load*qs[name]/total)
        if q.sum() <= 0. or volume == 0.:
            escrow = load
            exports[:] = 0.
        bed[:] = initial+store/(geometry.spacing_m**2*(1.-config.porosity))
        residual = previous + float(supply) - float(store.sum()) - float(exports.sum()) - float(escrow)
        if abs(residual) > 1.e-8*max(1., previous+float(supply)):
            raise ArithmeticError("tree solid balance failed")
        cumulative += float(exports.sum())
        padded = np.r_[q[:3], np.zeros(max(0, 3-len(q)))]
        records.append(MonthlyRecord(float(volume), float(supply), *padded[:3], float(volume/seconds), 0.,
            float(terminal_heads.max(initial=0.)), float(config.sea_level_m), float(node_heads[0]),
            deposited, reentrained, float(exports.sum()), escrow, residual, tuple(q.tolist()), tuple(exports.tolist())))
        history.append(wet.copy()); terminal_history.append(exports.copy()); land_history.append(float(store[initial > 0.].sum()))
        head_history.append(node_heads.copy())
        hydraulic_residuals.append(hydraulic_residual)
    wet = history[-1] if history else np.zeros_like(initial, bool)
    node_heads, heads, qs, depths, final_hydraulic_residual = hydraulics(float(water[-1]/dt[-1]), bed)
    stage, depth = _compute_stage_raster(bed, geometry, heads, seed, geometry.ocean_mask, config.sea_level_m)
    return dict(initial_bed_m=initial, final_bed_m=bed, height_delta_m=bed-initial,
        deposited_solid_m3=gross, reentrained_solid_m3=entrained, stored_solid_m3=store,
        stage_m=stage, depth_m=depth,
        wet_timeseries=np.asarray(history), eligible_mask=geometry.eligible_mask.copy(), protected_mask=geometry.protected_mask.copy(),
        ocean_mask=geometry.ocean_mask.copy(), records=records, cumulative_export_solid_m3=cumulative,
        cumulative_deposit_solid_m3=float(gross.sum()), cumulative_reentrain_solid_m3=float(entrained.sum()), config=config, porosity=config.porosity,
        cell_area_m2=geometry.spacing_m**2, geometry=geometry, monthly_land_stored_solid_m3=np.asarray(land_history),
        monthly_terminal_export_solid_m3=np.asarray(terminal_history), final_heads_m=node_heads,
        monthly_node_heads_m=np.asarray(head_history),
        node_names=["source"]+[name for name in geometry.paths if children[name]],
        monthly_max_junction_q_residual_m3_s=np.asarray(hydraulic_residuals),
        final_max_junction_q_residual_m3_s=final_hydraulic_residual)


def integrated_solid_ledger(
    summary: Dict[str, object], monthly_solid_m3: np.ndarray,
) -> Dict[str, float]:
    solid_store = np.asarray(summary["stored_solid_m3"])
    records = summary.get("records", [])
    escrow = float(records[-1].escrow_solid_m3) if records else 0.0
    return {
        "input_solid_m3": float(np.sum(monthly_solid_m3)),
        "retained_solid_m3": float(np.sum(solid_store)),
        "exported_solid_m3": float(summary["cumulative_export_solid_m3"]),
        "reentrained_solid_m3": float(summary["cumulative_reentrain_solid_m3"]),
        "deposited_solid_m3": float(summary["cumulative_deposit_solid_m3"]),
        "escrow_solid_m3": escrow,
    }



def wet_continuity_from_apex(summary, geometry):
    """Require all three sea endpoints in the D4 wet component of the apex."""
    from scipy.ndimage import label
    wet = summary["depth_m"] > 0.
    labels, _ = label(wet)
    def cell(point):
        cc, rr = np.rint((point-geometry.origin_xz)/geometry.spacing_m).astype(int)
        return int(np.clip(rr, 0, wet.shape[0]-1)), int(np.clip(cc, 0, wet.shape[1]-1))
    component = labels[cell(geometry.apex_xz)]
    return bool(component and all(labels[cell(point)] == component for point in geometry.sea_xz.values()))

