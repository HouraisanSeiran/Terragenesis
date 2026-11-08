"""Finite terrain-derived distributary excavation with explicit material escrow.

Water volumes set a generative section scale, not a discharge or erosion clock.
Excavation is a declared geometric work budget; transport is separately bounded.
"""

from dataclasses import asdict, dataclass
import heapq
import math

import numpy as np
from scipy.ndimage import distance_transform_edt

from terrain_pipeline.common_infra import readonly
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import channel_section_cut
from .metric_fluvial_delta import FluvialDeltaBoundary, FluvialDeltaInterval, _finite


@dataclass(frozen=True)
class FluvialDistributaryConfig:
    porosity: float = .35
    source_solid_fraction: float = 1.
    max_source_cut_depth_m: float = 4.
    max_source_cut_depth_per_interval_m: float = .25
    max_source_eroded_bulk_m3: float = 200000.
    channel_depth_m: float = 1.5
    width_at_reference_water_m: float = 15.
    reference_interval_water_m3: float = 200000.
    max_channel_width_m: float = 25.
    bottom_width_fraction: float = .35
    minimum_branch_separation_m: float = 30.
    branch_landward_distance_m: float = 15.
    minimum_branch_length_m: float = 30.
    branch_fraction: float = .5
    routing_relief_scale_m: float = 2.
    minimum_bed_slope: float = 0.
    capacity_solid_per_water: float = .02
    marine_capacity_decay_per_m: float = .3
    flow_concentration_exponent: float = .5
    lateral_spill_fraction: float = .1
    max_deposit_depth_per_interval_m: float = .1
    max_intervals: int = 128
    max_cells: int = 65536

    def __post_init__(self):
        for name in asdict(self):
            if name in ("max_intervals", "max_cells"):
                value = getattr(self, name)
                maximum = 128 if name == "max_intervals" else 65536
                if type(value) is not int or not 1 <= value <= maximum:
                    raise ValueError(name + " outside bounded integer range")
            else:
                object.__setattr__(self, name, _finite(getattr(self, name), name))
        if (self.porosity >= 1. or not 0. < self.source_solid_fraction <= 1.
                or not 0. < self.bottom_width_fraction < 1. or not .05 <= self.branch_fraction <= .95
                or self.lateral_spill_fraction > .2
                or not 0. < self.max_source_cut_depth_m <= 4.):
            raise ValueError("invalid material, section or branch fraction")
        for name in ("max_source_cut_depth_per_interval_m", "max_source_eroded_bulk_m3", "channel_depth_m",
                     "width_at_reference_water_m", "reference_interval_water_m3", "max_channel_width_m",
                     "minimum_branch_separation_m", "minimum_branch_length_m", "routing_relief_scale_m"):
            if getattr(self, name) == 0.:
                raise ValueError(name + " must be positive")
        if self.channel_depth_m > self.max_source_cut_depth_m:
            raise ValueError("channel depth exceeds source cut limit")


def _neighbors(cell, active, terrain):
    row, column = cell
    for dr, dc, length in ((-1, 0, terrain.dz_m), (0, -1, terrain.dx_m),
                           (0, 1, terrain.dx_m), (1, 0, terrain.dz_m)):
        other = row + dr, column + dc
        if 0 <= other[0] < active.shape[0] and 0 <= other[1] < active.shape[1] and active[other]:
            yield other, length


def _path(start, sinks, active, bed, terrain, boundary, config, penalty=None):
    active = active & (~boundary.ocean_export_mask | sinks)
    distance = np.full(active.shape, np.inf)
    previous = {}
    queue = [(0., start)]
    distance[start] = 0.
    resistance = .05 + np.exp(np.clip((bed - boundary.sea_level_m) / config.routing_relief_scale_m, -10., 10.))
    if penalty is not None:
        resistance += penalty
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != distance[cell]:
            continue
        if sinks[cell]:
            path = [cell]
            while cell != start:
                cell = previous[cell]
                path.append(cell)
            return tuple(reversed(path))
        for other, length in _neighbors(cell, active, terrain):
            candidate = cost + length * (resistance[cell] + resistance[other]) * .5
            # Current actual bed favours an already incised route on later stages.
            candidate += max(0., bed[other] - bed[cell]) * 10.
            if candidate < distance[other]:
                distance[other] = candidate
                previous[other] = cell
                heapq.heappush(queue, (candidate, other))
    raise ValueError("distributary inlet or branch cannot reach a declared ocean export")


def prepare_marine_transition(terrain, boundary, inlet_cell, *, radius_m, slope_m_per_m,
                              maximum_raise_m, maximum_fill_bulk_m3, supplied_solid_m3, porosity=.35,
                              minimum_submergence_m=.2):
    """Declare a finite imported-material seabed coordination, never new TD.

    The target slopes down with distance from land; a radial taper reconnects
    exactly to the original bed outside radius_m. Ocean identity is unchanged.
    """
    if not isinstance(terrain, TerrainGrid) or not isinstance(boundary, FluvialDeltaBoundary):
        raise ValueError("typed terrain and boundary required")
    parameters = dict(radius_m=radius_m, slope_m_per_m=slope_m_per_m, maximum_raise_m=maximum_raise_m,
                      maximum_fill_bulk_m3=maximum_fill_bulk_m3, supplied_solid_m3=supplied_solid_m3,
                      porosity=porosity, minimum_submergence_m=minimum_submergence_m)
    parameters = {name: _finite(value, name) for name, value in parameters.items()}
    if radius_m <= 0. or slope_m_per_m <= 0. or porosity >= 1. or minimum_submergence_m <= 0.:
        raise ValueError("positive marine support, slope, submergence and valid porosity required")
    if boundary.initial_ocean_mask.shape != terrain.elevation_m.shape:
        raise ValueError("marine boundary shape mismatch")
    row, column = inlet_cell
    if not 0 <= row < terrain.elevation_m.shape[0] or not 0 <= column < terrain.elevation_m.shape[1]:
        raise ValueError("marine coordination anchor outside terrain")
    ocean = boundary.initial_ocean_mask & terrain.valid_mask
    offshore_distance = distance_transform_edt(ocean, sampling=(terrain.dz_m, terrain.dx_m))
    rows, columns = np.indices(ocean.shape)
    radial_distance = np.hypot((rows - row) * terrain.dz_m, (columns - column) * terrain.dx_m)
    taper = np.clip(2. * (1. - radial_distance / radius_m), 0., 1.)
    # Perimeter samples and declared exports retain their supplied boundary bed.
    taper[0, :] = taper[-1, :] = 0.
    taper[:, 0] = taper[:, -1] = 0.
    target = boundary.sea_level_m - minimum_submergence_m - slope_m_per_m * offshore_distance
    raise_m = np.maximum(0., target - terrain.elevation_m) * taper
    raise_m[~ocean] = 0.
    if np.max(raise_m, initial=0.) > maximum_raise_m + 1e-10:
        raise ValueError("marine coordination maximum raise budget exceeded")
    bulk = raise_m * terrain.cell_area_m2
    bulk_total = float(bulk.sum())
    solid = bulk * (1. - porosity)
    used_solid = float(solid.sum())
    if (not math.isfinite(bulk_total) or not math.isfinite(used_solid)
            or bulk_total > maximum_fill_bulk_m3 + 1e-8 or used_solid > supplied_solid_m3 + 1e-8):
        raise ValueError("marine coordination material budget insufficient")
    return {"initial_cover_solid_m3": readonly(solid),
            "coordinated_bed_m": readonly(terrain.elevation_m + raise_m),
            "fill_bulk_m3": readonly(bulk),
            "preparation_ledger": {"supplied_solid_m3": supplied_solid_m3, "placed_solid_m3": used_solid,
                                   "unplaced_solid_m3": supplied_solid_m3 - used_solid,
                                   "placed_bulk_m3": bulk_total, "residual_solid_m3": 0.},
            "metadata": {"algorithm_version": "bounded-imported-marine-slope-coordination-v1",
                         "config": parameters, "inlet_cell": inlet_cell,
                         "terrain_identity_sha256": terrain.identity_sha256,
                         "semantics": "explicit imported-material macro coordination, not natural river deposition or TD detail"}}


def _paths(bed, terrain, boundary, inlet, config):
    active = terrain.valid_mask & (bed <= boundary.river_head_m)
    if not active[inlet]:
        raise ValueError("distributary inlet exceeds the admissible bed ceiling")
    first = _path(inlet, boundary.ocean_export_mask, active, bed, terrain, boundary, config)
    marine_index = next((i for i, cell in enumerate(first) if boundary.initial_ocean_mask[cell]), len(first) - 1)
    distance = 0.
    junction_index = marine_index
    while junction_index > 1 and distance < config.branch_landward_distance_m:
        a, b = first[junction_index - 1: junction_index + 1]
        distance += math.hypot((a[0] - b[0]) * terrain.dz_m, (a[1] - b[1]) * terrain.dx_m)
        junction_index -= 1
    junction = first[junction_index]
    trunk, branch_a = first[:junction_index + 1], first[junction_index:]
    blocked = active.copy()
    for cell in first:
        blocked[cell] = False
    blocked[junction] = True
    first_mask = np.zeros(active.shape, bool)
    for cell in branch_a:
        first_mask[cell] = True
    separation = distance_transform_edt(~first_mask, sampling=(terrain.dz_m, terrain.dx_m))
    sinks = boundary.ocean_export_mask & (separation >= config.minimum_branch_separation_m)
    if not sinks.any():
        raise ValueError("declared ocean exports cannot support separated branches")
    penalty = 4. * np.maximum(0., 1. - separation / config.minimum_branch_separation_m)
    branch_b = _path(junction, sinks, blocked, bed, terrain, boundary, config, penalty)
    separated_run = 0.
    longest_separated_run = 0.
    for a, b in zip(branch_b, branch_b[1:]):
        if separation[a] >= config.minimum_branch_separation_m and separation[b] >= config.minimum_branch_separation_m:
            separated_run += math.hypot((a[0] - b[0]) * terrain.dz_m, (a[1] - b[1]) * terrain.dx_m)
            longest_separated_run = max(longest_separated_run, separated_run)
        else:
            separated_run = 0.
    if longest_separated_run < config.minimum_branch_length_m:
        raise ValueError("terrain-derived branches lack the declared sustained separation length")
    for branch in (branch_a, branch_b):
        length = sum(math.hypot((a[0] - b[0]) * terrain.dz_m, (a[1] - b[1]) * terrain.dx_m)
                     for a, b in zip(branch, branch[1:]))
        if length < config.minimum_branch_length_m:
            raise ValueError("terrain-derived branch is shorter than the declared minimum")
    return trunk, branch_a, branch_b


def _section_target(paths, terrain, reference_bed, interval_water, config):
    width = min(config.max_channel_width_m, config.width_at_reference_water_m
                * math.sqrt(interval_water / config.reference_interval_water_m3))
    if width < 2. * max(terrain.dx_m, terrain.dz_m):
        raise ValueError("volume-derived channel section is underresolved")
    center = np.zeros(reference_bed.shape, bool)
    profile = np.full(reference_bed.shape, np.inf)
    junction_level = None
    for index, path in enumerate(paths):
        previous = None if index == 0 else junction_level
        previous_cell = None
        for cell in path:
            target = reference_bed[cell] - config.channel_depth_m
            if previous is not None:
                length = 0. if previous_cell is None else math.hypot(
                    (cell[0] - previous_cell[0]) * terrain.dz_m,
                    (cell[1] - previous_cell[1]) * terrain.dx_m)
                target = min(target, previous - config.minimum_bed_slope * length)
            profile[cell] = min(profile[cell], target)
            center[cell] = True
            previous, previous_cell = target, cell
        if index == 0:
            junction_level = previous
    distance, nearest = distance_transform_edt(~center, sampling=(terrain.dz_m, terrain.dx_m), return_indices=True)
    local_profile = profile[nearest[0], nearest[1]]
    cut = channel_section_cut(distance, width, config.channel_depth_m,
                              bottom_width_fraction=config.bottom_width_fraction)
    profile_adjustment = np.maximum(0., reference_bed[nearest[0], nearest[1]] - config.channel_depth_m - local_profile)
    target_bed = reference_bed - np.where(cut > 0., cut + profile_adjustment, 0.)
    target_bed[~terrain.valid_mask] = terrain.elevation_m[~terrain.valid_mask]
    target_cut = np.maximum(0., terrain.elevation_m - target_bed)
    if np.any(target_cut > config.max_source_cut_depth_m + 1e-10):
        raise ValueError("continuous longitudinal section exceeds the original-bed cut limit")
    return target_bed, width


def _flow_graph(paths, bed, terrain, boundary, config):
    trunk, branch_a, branch_b = paths
    outgoing = {}
    for path, share in ((trunk, 1.), (branch_a, 1. - config.branch_fraction), (branch_b, config.branch_fraction)):
        for a, b in zip(path, path[1:]):
            outgoing.setdefault(a, []).append((b, share if a == trunk[-1] else 1.))
    occupied = set(cell for path in paths for cell in path)
    active = terrain.valid_mask & (bed <= boundary.river_head_m)
    # Small, explicitly head-admissible side flows carry the same sediment
    # fraction onto marine banks and return to the downstream centerline.
    for path in paths:
        for index in range(0, len(path) - 2, 4):
            a, b, c = path[index:index + 3]
            dr, dc = b[0] - a[0], b[1] - a[1]
            if (c[0] - b[0], c[1] - b[1]) != (dr, dc):
                continue
            if not boundary.initial_ocean_mask[a] or not boundary.initial_ocean_mask[c]:
                continue
            if a not in outgoing or len(outgoing[a]) != 1 or outgoing[a][0][0] != b:
                continue
            side_paths = []
            for sign in (-1, 1):
                nr, nc = -dc * sign, dr * sign
                route = (a, (a[0] + nr, a[1] + nc), (a[0] + 2 * nr, a[1] + 2 * nc),
                         (b[0] + 2 * nr, b[1] + 2 * nc), (c[0] + 2 * nr, c[1] + 2 * nc),
                         (c[0] + nr, c[1] + nc), c)
                interior = route[1:-1]
                if any(not 0 <= cell[0] < active.shape[0] or not 0 <= cell[1] < active.shape[1]
                       or not active[cell] or not boundary.initial_ocean_mask[cell]
                       or boundary.ocean_export_mask[cell] or cell in occupied for cell in interior):
                    continue
                side_paths.append(route)
                occupied.update(interior)
            if not side_paths or config.lateral_spill_fraction == 0.:
                continue
            fraction = config.lateral_spill_fraction / len(side_paths)
            outgoing[a] = [(b, 1. - config.lateral_spill_fraction)]
            for route in side_paths:
                outgoing[a].append((route[1], fraction))
                for start, end in zip(route[1:-1], route[2:]):
                    outgoing[start] = [(end, 1.)]
    indegree = {}
    for cell, receivers in outgoing.items():
        indegree.setdefault(cell, 0)
        for other, _ in receivers:
            indegree[other] = indegree.get(other, 0) + 1
    pending = [cell for cell, degree in indegree.items() if degree == 0]
    heapq.heapify(pending)
    order = []
    while pending:
        cell = heapq.heappop(pending)
        order.append(cell)
        for other, _ in outgoing.get(cell, ()):
            indegree[other] -= 1
            if indegree[other] == 0:
                heapq.heappush(pending, other)
    if len(order) != len(indegree):
        raise ValueError("terrain-derived side-flow graph contains a cycle")
    return outgoing, order


def simulate_fluvial_distributary(terrain, boundary, forcing, config=None, *, initial_cover_solid_m3=None):
    """Build and route a bounded two-branch bed from current terrain costs.

    Geometric excavation enters local sediment transport up to the transport
    target; remaining excavated solids stay in explicit terminal work escrow.
    This is a finite generation design, not a hydraulic erosion calculation.
    """
    config = FluvialDistributaryConfig() if config is None else config
    if not isinstance(terrain, TerrainGrid) or not isinstance(boundary, FluvialDeltaBoundary) or not isinstance(config, FluvialDistributaryConfig):
        raise ValueError("typed terrain, boundary and distributary config required")
    if not isinstance(forcing, (tuple, list)) or not 1 <= len(forcing) <= config.max_intervals:
        raise ValueError("bounded nonempty interval sequence required")
    shape = terrain.elevation_m.shape
    if terrain.elevation_m.size > config.max_cells or terrain.elevation_m.size * len(forcing) > 4194304:
        raise ValueError("distributary domain/interval memory budget exceeded")
    if boundary.initial_ocean_mask.shape != shape:
        raise ValueError("boundary shape differs from terrain")
    perimeter = np.zeros(shape, bool)
    perimeter[0, :] = perimeter[-1, :] = True
    perimeter[:, 0] = perimeter[:, -1] = True
    if (not boundary.ocean_export_mask.any() or np.any(boundary.initial_ocean_mask & ~terrain.valid_mask)
            or np.any(boundary.ocean_export_mask & ~(boundary.initial_ocean_mask & perimeter))
            or np.any(terrain.elevation_m[boundary.initial_ocean_mask] > boundary.sea_level_m)):
        raise ValueError("explicit submerged ocean and perimeter exports required")
    for interval in forcing:
        if not isinstance(interval, FluvialDeltaInterval):
            raise ValueError("typed interval required")
        row, column = interval.inlet_cell
        if (not 0 <= row < shape[0] or not 0 <= column < shape[1] or not terrain.valid_mask[row, column]
                or boundary.ocean_export_mask[row, column]):
            raise ValueError("inlet must be valid non-export terrain")
    area, fraction = terrain.cell_area_m2, 1. - config.porosity
    for quantity in (area * config.max_source_cut_depth_m, area * config.max_deposit_depth_per_interval_m,
                     sum(item.water_volume_m3 for item in forcing), sum(item.sediment_solid_m3 for item in forcing)):
        if not math.isfinite(quantity):
            raise ValueError("distributary numeric budget overflows")
    source_bulk = np.zeros(shape)
    if initial_cover_solid_m3 is None:
        initial_cover = np.zeros(shape)
    else:
        initial_cover = np.asarray(initial_cover_solid_m3, np.float64)
        if (initial_cover.shape != shape or not np.isfinite(initial_cover).all() or np.any(initial_cover < 0.)
                or np.any(initial_cover[~terrain.valid_mask] > 0.)):
            raise ValueError("finite nonnegative matching valid initial cover required")
        initial_cover = initial_cover.copy()
    stored = initial_cover.copy()
    total_deposit, total_reentrained, total_escrow = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    records = []
    reference_bed = terrain.elevation_m + initial_cover / (fraction * area)
    if not np.isfinite(reference_bed).all():
        raise ValueError("prepared bed overflows")
    bed = reference_bed.copy()
    for interval in forcing:
        water, sediment = np.zeros(shape), np.zeros(shape)
        incoming_sediment = np.zeros(shape)
        deposit, reentrained, excavated, escrow = (np.zeros(shape) for _ in range(4))
        starting_stored = float(stored.sum())
        paths, edges, width = (), [], 0.
        exported_water, exported_solid = 0., 0.
        if interval.water_volume_m3 == 0.:
            escrow[interval.inlet_cell] = interval.sediment_solid_m3
            water[interval.inlet_cell] = 0.
            sediment[interval.inlet_cell] = interval.sediment_solid_m3
            incoming_sediment[interval.inlet_cell] = interval.sediment_solid_m3
        else:
            paths = _paths(bed, terrain, boundary, interval.inlet_cell, config)
            target_bed, width = _section_target(paths, terrain, reference_bed, interval.water_volume_m3, config)
            footprint = (target_bed < reference_bed)
            current_base = terrain.elevation_m - source_bulk / area
            target_cover = np.maximum(0., target_bed - current_base) * fraction * area
            reentrained = np.minimum(np.maximum(0., stored - target_cover),
                                     area * config.max_source_cut_depth_per_interval_m * fraction)
            reentrained[~footprint] = 0.
            stored -= reentrained
            desired_bulk = np.maximum(0., (terrain.elevation_m - target_bed) * area - source_bulk)
            excavated = np.minimum(desired_bulk, area * config.max_source_cut_depth_per_interval_m)
            excavated[stored > 1e-12] = 0.
            required = float(excavated.sum())
            if float(source_bulk.sum()) + required > config.max_source_eroded_bulk_m3 + 1e-8:
                raise ValueError("original-bed excavation volume budget exceeded")
            # Reaching the geometric target clears deposited cover first. Cover
            # from cells outside the routed centerline is held in work escrow.
            source_bulk += excavated
            injected = excavated * config.source_solid_fraction + reentrained
            escrow += injected
            outgoing, order = _flow_graph(paths, bed, terrain, boundary, config)
            water[interval.inlet_cell] = interval.water_volume_m3
            sediment[interval.inlet_cell] = interval.sediment_solid_m3
            for cell in order:
                if water[cell] == 0.:
                    continue
                incoming_sediment[cell] = sediment[cell]
                depth = max(0., boundary.sea_level_m - bed[cell])
                concentration = min(1., float(water[cell]) / interval.water_volume_m3)
                target = (float(water[cell]) * config.capacity_solid_per_water
                          * concentration ** config.flow_concentration_exponent
                          * math.exp(-min(745., config.marine_capacity_decay_per_m * depth)))
                mobilized = min(float(escrow[cell]), max(0., target - float(sediment[cell])))
                escrow[cell] -= mobilized
                sediment[cell] += mobilized
                if boundary.ocean_export_mask[cell]:
                    exported_water += float(water[cell])
                    exported_solid += float(sediment[cell])
                    continue
                # Active geometric excavation and deposition are separate net
                # operations; surplus at a worked cell is explicit work escrow.
                surplus = max(0., float(sediment[cell]) - target)
                if excavated[cell] > 0. or reentrained[cell] > 0.:
                    escrow[cell] += surplus
                    carried = float(sediment[cell]) - surplus
                else:
                    deposit[cell] = min(surplus, area * config.max_deposit_depth_per_interval_m * fraction)
                    carried = float(sediment[cell]) - deposit[cell]
                for other, share in outgoing[cell]:
                    water_share = float(water[cell]) * share
                    solid_share = carried * share
                    water[other] += water_share
                    sediment[other] += solid_share
                    edges.append({"from_cell": cell, "to_cell": other,
                                  "water_volume_m3": water_share, "sediment_solid_m3": solid_share})
        stored += deposit
        total_deposit += deposit
        total_reentrained += reentrained
        total_escrow += escrow
        bed = terrain.elevation_m - source_bulk / area + stored / (fraction * area)
        if not np.isfinite(bed).all():
            raise ValueError("derived distributary bed overflows")
        source_solid = float(excavated.sum()) * config.source_solid_fraction
        solid_ledger = {"input_solid_m3": interval.sediment_solid_m3,
                        "source_eroded_solid_m3": source_solid, "source_eroded_bulk_m3": float(excavated.sum()),
                        "initial_stored_solid_m3": starting_stored, "stored_solid_m3": float(stored.sum()),
                        "deposited_solid_m3": float(deposit.sum()), "reentrained_solid_m3": float(reentrained.sum()),
                        "ocean_export_solid_m3": exported_solid, "unresolved_solid_m3": float(escrow.sum())}
        solid_ledger["residual_solid_m3"] = math.fsum((interval.sediment_solid_m3, source_solid, starting_stored,
                                                       -float(stored.sum()), -exported_solid, -float(escrow.sum())))
        water_ledger = {"input_m3": interval.water_volume_m3, "ocean_export_m3": exported_water,
                        "retained_m3": 0., "residual_m3": interval.water_volume_m3 - exported_water}
        records.append({"water_throughput_m3": readonly(water), "sediment_throughput_solid_m3": readonly(incoming_sediment),
                        "deposited_solid_m3": readonly(deposit), "reentrained_solid_m3": readonly(reentrained),
                        "stored_solid_m3": readonly(stored), "source_eroded_bulk_m3": readonly(excavated),
                        "source_eroded_solid_m3": readonly(excavated * config.source_solid_fraction),
                        "unresolved_solid_m3": readonly(escrow), "bed_m": readonly(bed),
                        "channel_paths": ({"trunk": paths[0], "branches": paths[1:]} if paths else {"trunk": (), "branches": ()}),
                        "channel_width_m": width, "flow_edges": tuple(edges),
                        "water_ledger": water_ledger, "solid_ledger": solid_ledger})
    water_ledger = {key: math.fsum(record["water_ledger"][key] for record in records)
                    for key in records[0]["water_ledger"]}
    solid_ledger = {key: math.fsum(record["solid_ledger"][key] for record in records)
                    for key in ("input_solid_m3", "source_eroded_solid_m3", "source_eroded_bulk_m3", "deposited_solid_m3",
                                "reentrained_solid_m3", "ocean_export_solid_m3", "unresolved_solid_m3")}
    solid_ledger["stored_solid_m3"] = float(stored.sum())
    solid_ledger["initial_stored_solid_m3"] = float(initial_cover.sum())
    solid_ledger["residual_solid_m3"] = math.fsum((float(initial_cover.sum()), solid_ledger["input_solid_m3"], solid_ledger["source_eroded_solid_m3"],
                                                   -solid_ledger["stored_solid_m3"], -solid_ledger["ocean_export_solid_m3"],
                                                   -solid_ledger["unresolved_solid_m3"]))
    return {"original_source_bed_m": terrain.elevation_m, "initial_bed_m": readonly(reference_bed),
            "initial_cover_solid_m3": readonly(initial_cover), "final_bed_m": readonly(bed),
            "derived_base_bed_m": readonly(terrain.elevation_m - source_bulk / area),
            "height_delta_m": readonly(bed - reference_bed), "stored_solid_m3": readonly(stored),
            "deposited_solid_m3": readonly(total_deposit), "reentrained_solid_m3": readonly(total_reentrained),
            "source_eroded_bulk_m3": readonly(source_bulk),
            "source_eroded_solid_m3": readonly(source_bulk * config.source_solid_fraction),
            "unresolved_solid_m3": readonly(total_escrow), "intervals": tuple(records),
            "water_ledger": water_ledger, "solid_ledger": solid_ledger,
            "metadata": {"algorithm_version": "fluvial-distributary-geometric-work-v1", "config": asdict(config),
                         "terrain_identity_sha256": terrain.identity_sha256, "boundary_source_id": boundary.source_id,
                         "forcing": [asdict(interval) for interval in forcing],
                         "section_semantics": "volume-scaled geometric excavation budget; not discharge or physical erosion",
                         "source_material_semantics": "source bulk times independent source_solid_fraction; cover uses porosity",
                         "capacity_semantics": "water_volume * capacity_solid_per_water * (local_water/inlet_water)^flow_concentration_exponent * exp(-marine_capacity_decay_per_m*max(0,sea_level-starting_bed)); surplus at an excavated cell is explicit work escrow, otherwise bounded deposition",
                         "escrow_semantics": "excavated and supplied solids beyond local transport target remain terminal work escrow",
                         "routing_semantics": "current-bed four-neighbor least-cost trunk with a non-rejoining separated second export route",
                         "lateral_spill_semantics": "bounded volume fraction onto valid marine side cells below explicit river_head, four-neighbor acyclic downstream return; not solved hydraulics",
                         "hydraulic_certification_allowed": False}}
