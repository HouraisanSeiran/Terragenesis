"""Finite river-led deposition and bed-feedback routing approximation.

Intervals pass prescribed volumes through a connectivity DAG, not a transient
hydraulic solver. The explicit river head bounds floodable cells; it is not a
computed water surface. Optional reentrainment only removes this run's deposits;
there is no bedrock erosion, tides, waves, or conversion to years.
"""

from dataclasses import asdict, dataclass
import heapq
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, readonly
from .metric_contracts import TerrainGrid


def _finite(value, name, minimum=0., strict=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    if not math.isfinite(value) or (value <= minimum if strict else value < minimum):
        raise ValueError(name + " outside finite range")
    return float(value)


@dataclass(frozen=True)
class FluvialDeltaConfig:
    porosity: float = .35
    capacity_solid_per_water: float = .02
    marine_capacity_decay_per_m: float = .3
    flow_concentration_exponent: float = .5
    routing_relief_scale_m: float = .5
    split_cost_scale_m: float = 2.
    max_deposit_depth_per_interval_m: float = .25
    max_intervals: int = 128
    max_cells: int = 65536
    max_reentrainment_depth_per_interval_m: float = 0.

    def __post_init__(self):
        for name in ("porosity", "capacity_solid_per_water", "marine_capacity_decay_per_m", "flow_concentration_exponent"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.porosity >= 1.:
            raise ValueError("porosity must be below one")
        object.__setattr__(self, "max_reentrainment_depth_per_interval_m",
                           _finite(self.max_reentrainment_depth_per_interval_m, "max_reentrainment_depth_per_interval_m"))
        for name in ("routing_relief_scale_m", "split_cost_scale_m", "max_deposit_depth_per_interval_m"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, strict=True))
        for name, upper in (("max_intervals", 1024), ("max_cells", 65536)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError(name + " outside bounded integer range")


@dataclass(frozen=True)
class FluvialDeltaBoundary:
    initial_ocean_mask: np.ndarray
    ocean_export_mask: np.ndarray
    sea_level_m: float
    river_head_m: float
    source_id: str

    def __post_init__(self):
        for name in ("initial_ocean_mask", "ocean_export_mask"):
            mask = getattr(self, name)
            if not isinstance(mask, np.ndarray) or mask.dtype != bool or mask.ndim != 2:
                raise ValueError(name + " must be a boolean 2D array")
            object.__setattr__(self, name, readonly(mask))
        if self.initial_ocean_mask.shape != self.ocean_export_mask.shape:
            raise ValueError("boundary masks must share shape")
        for name in ("sea_level_m", "river_head_m"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, -math.inf))
        if self.river_head_m < self.sea_level_m:
            raise ValueError("river head must not be below sea level")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("explicit boundary source_id required")


@dataclass(frozen=True)
class FluvialDeltaInterval:
    inlet_cell: tuple[int, int]
    water_volume_m3: float
    sediment_solid_m3: float

    def __post_init__(self):
        if (not isinstance(self.inlet_cell, tuple) or len(self.inlet_cell) != 2
                or any(type(value) is not int for value in self.inlet_cell)):
            raise ValueError("inlet_cell must be an integer row/column tuple")
        for name in ("water_volume_m3", "sediment_solid_m3"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))


def _neighbors(cell, active, terrain):
    row, column = cell
    for dr, dc in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
        neighbor = row + dr, column + dc
        if 0 <= neighbor[0] < active.shape[0] and 0 <= neighbor[1] < active.shape[1] and active[neighbor]:
            if dr and dc and (not active[row + dr, column] or not active[row, column + dc]):
                continue
            yield neighbor, math.hypot(terrain.dz_m if dr else 0., terrain.dx_m if dc else 0.)


def _routing(bed, terrain, boundary, config):
    active = terrain.valid_mask & (bed <= boundary.river_head_m)
    distance = np.full(bed.shape, np.inf)
    resistance = np.exp(np.clip((bed - boundary.sea_level_m) / config.routing_relief_scale_m, -30., 30.))
    pending = []
    for row, column in np.argwhere(boundary.ocean_export_mask & active):
        cell = int(row), int(column)
        distance[cell] = 0.
        heapq.heappush(pending, (0., cell))
    while pending:
        cost, cell = heapq.heappop(pending)
        if cost != distance[cell]:
            continue
        for neighbor, length in _neighbors(cell, active, terrain):
            candidate = cost + length * (resistance[cell] + resistance[neighbor]) * .5
            if candidate < distance[neighbor]:
                distance[neighbor] = candidate
                heapq.heappush(pending, (candidate, neighbor))
    return active, distance, resistance


def _ledger(water_in, water_out, water_retained, solid_in, solid_out, deposit, unresolved, porosity,
            reentrained=None, initial_stored=0., stored=0.):
    water = {"input_m3": water_in, "ocean_export_m3": water_out, "retained_m3": water_retained,
             "residual_m3": water_in - math.fsum((water_out, water_retained))}
    solid = {"input_solid_m3": solid_in, "ocean_export_solid_m3": solid_out,
             "deposited_solid_m3": deposit, "unresolved_solid_m3": unresolved,
             "deposit_bulk_m3": deposit / (1. - porosity),
             "residual_solid_m3": solid_in - math.fsum((solid_out, deposit, unresolved))}
    if reentrained is not None:
        solid.update({"initial_stored_solid_m3": initial_stored, "reentrained_solid_m3": reentrained,
                      "stored_solid_m3": stored, "stored_bulk_m3": stored / (1. - porosity),
                      "residual_solid_m3": math.fsum((solid_in, initial_stored, -solid_out, -stored, -unresolved))})
    return water, solid


def simulate_fluvial_delta(terrain, boundary, forcing, config=None):
    """Return updated bed, per-interval connected allocations, and volume ledgers.

    Ocean export occurs exclusively at declared perimeter sink cells. Sediment
    without flowing water or an accessible sink remains unresolved at the inlet.
    Each interval routes on its starting bed and then commits its net bed change.
    Reentrainment is opt-in and limited to sediment stored before that interval.
    """
    config = config or FluvialDeltaConfig()
    if not isinstance(terrain, TerrainGrid) or not isinstance(boundary, FluvialDeltaBoundary) or not isinstance(config, FluvialDeltaConfig):
        raise ValueError("typed terrain, boundary and config required")
    if not isinstance(forcing, (tuple, list)) or not 1 <= len(forcing) <= config.max_intervals:
        raise ValueError("bounded nonempty interval sequence required")
    shape = terrain.elevation_m.shape
    if terrain.elevation_m.size > config.max_cells or terrain.elevation_m.size * len(forcing) > 4194304:
        raise ValueError("delta domain/interval memory budget exceeded")
    if boundary.initial_ocean_mask.shape != shape:
        raise ValueError("boundary shape differs from terrain")
    with np.errstate(over="ignore", invalid="ignore"):
        relative_bed = terrain.elevation_m[terrain.valid_mask] - boundary.sea_level_m
    if (not np.isfinite(relative_bed).all()
            or any(not math.isfinite(length * math.exp(30.)) or length * math.exp(-30.) == 0.
                   for length in (terrain.dx_m, terrain.dz_m))):
        raise ValueError("routing elevation/spacing outside numeric range")
    ocean, exports = boundary.initial_ocean_mask, boundary.ocean_export_mask
    perimeter = np.zeros(shape, dtype=bool)
    perimeter[0, :] = perimeter[-1, :] = True
    perimeter[:, 0] = perimeter[:, -1] = True
    if (not exports.any() or np.any(ocean & ~terrain.valid_mask)
            or np.any(exports & ~(ocean & perimeter))
            or np.any(terrain.elevation_m[ocean] > boundary.sea_level_m)):
        raise ValueError("explicit submerged ocean and perimeter ocean exports required")
    for interval in forcing:
        if not isinstance(interval, FluvialDeltaInterval):
            raise ValueError("typed intervals required")
        row, column = interval.inlet_cell
        if not 0 <= row < shape[0] or not 0 <= column < shape[1] or not terrain.valid_mask[row, column] or exports[row, column]:
            raise ValueError("inlet must be a valid non-export terrain cell")
    water_in = math.fsum(interval.water_volume_m3 for interval in forcing)
    solid_in = math.fsum(interval.sediment_solid_m3 for interval in forcing)
    if not math.isfinite(water_in) or not math.isfinite(solid_in):
        raise ValueError("forcing totals overflow")
    max_deposit = terrain.cell_area_m2 * config.max_deposit_depth_per_interval_m * (1. - config.porosity)
    max_reentrain = terrain.cell_area_m2 * config.max_reentrainment_depth_per_interval_m * (1. - config.porosity)
    reentrainment_enabled = config.max_reentrainment_depth_per_interval_m > 0.
    if (not math.isfinite(max_deposit) or not math.isfinite(max_reentrain)
            or not math.isfinite(solid_in / (1. - config.porosity))):
        raise ValueError("deposit volume overflows")
    bed = terrain.elevation_m.copy()
    total_deposit = np.zeros(shape)
    total_reentrained = np.zeros(shape)
    stored = np.zeros(shape)
    records = []
    for interval in forcing:
        active, distance, resistance = _routing(bed, terrain, boundary, config)
        water = np.zeros(shape)
        sediment = np.zeros(shape)
        deposit = np.zeros(shape)
        reentrained = np.zeros(shape)
        initial_stored = float(stored.sum())
        water[interval.inlet_cell] = interval.water_volume_m3
        sediment[interval.inlet_cell] = interval.sediment_solid_m3
        water_exports, solid_exports, unresolved, retained = [], [], [], []
        edges = []
        cells = [tuple(map(int, cell)) for cell in np.argwhere(np.isfinite(distance))]
        cells.sort(key=lambda cell: (-distance[cell], cell))
        if not np.isfinite(distance[interval.inlet_cell]) or interval.water_volume_m3 == 0.:
            retained.append(interval.water_volume_m3)
            unresolved.append(interval.sediment_solid_m3)
        else:
            for cell in cells:
                if water[cell] == 0.:
                    continue
                if exports[cell]:
                    water_exports.append(float(water[cell]))
                    solid_exports.append(float(sediment[cell]))
                    continue
                # Submergence lowers the equilibrium transport target. Bounded
                # A single net target chooses deposition or reentrainment.
                # Only cover present at interval start can supply a deficit.
                depth = max(0., boundary.sea_level_m - bed[cell])
                concentration = min(1., float(water[cell]) / interval.water_volume_m3)
                capacity_ratio = (config.capacity_solid_per_water
                                  * concentration ** config.flow_concentration_exponent
                                  * math.exp(-min(745., depth * config.marine_capacity_decay_per_m)))
                target = float(water[cell]) * capacity_ratio
                deposited = min(max(0., float(sediment[cell]) - target), max_deposit)
                deposit[cell] = deposited
                if reentrainment_enabled and target > sediment[cell]:
                    reentrained[cell] = min(target - float(sediment[cell]), float(stored[cell]), max_reentrain)
                carried = float(sediment[cell]) - deposited + float(reentrained[cell])
                receivers = [(neighbor, length) for neighbor, length in _neighbors(cell, active, terrain)
                             if distance[neighbor] < distance[cell]]
                costs = [length * (resistance[cell] + resistance[neighbor]) * .5 + distance[neighbor]
                         for neighbor, length in receivers]
                best = min(costs)
                weights = [math.exp(-min(745., max(0., cost - best) / config.split_cost_scale_m)) for cost in costs]
                water_remaining, solid_remaining = float(water[cell]), carried
                for index, ((neighbor, _), weight) in enumerate(zip(receivers, weights)):
                    last = index == len(receivers) - 1
                    fraction = weight / math.fsum(weights[index:])
                    water_share = water_remaining if last else water_remaining * fraction
                    solid_share = solid_remaining if last else solid_remaining * fraction
                    water_remaining -= water_share
                    solid_remaining -= solid_share
                    water[neighbor] += water_share
                    sediment[neighbor] += solid_share
                    if water_share > 0.:
                        edges.append({"from_cell": cell, "to_cell": neighbor,
                                      "water_volume_m3": water_share, "sediment_solid_m3": solid_share})
        stored += deposit - reentrained
        if reentrainment_enabled:
            bed = terrain.elevation_m + stored / ((1. - config.porosity) * terrain.cell_area_m2)
        else:
            bed += deposit / ((1. - config.porosity) * terrain.cell_area_m2)
        total_deposit += deposit
        total_reentrained += reentrained
        if not np.isfinite(bed[terrain.valid_mask]).all():
            raise ValueError("updated bed overflows")
        water_ledger, solid_ledger = _ledger(interval.water_volume_m3, math.fsum(water_exports), math.fsum(retained),
                                           interval.sediment_solid_m3, math.fsum(solid_exports), float(deposit.sum()),
                                           math.fsum(unresolved), config.porosity,
                                           float(reentrained.sum()) if reentrainment_enabled else None,
                                           initial_stored, float(stored.sum()))
        records.append({"water_throughput_m3": readonly(water), "sediment_throughput_solid_m3": readonly(sediment),
                        "deposited_solid_m3": readonly(deposit), "reentrained_solid_m3": readonly(reentrained),
                        "stored_solid_m3": readonly(stored), "flow_edges": tuple(edges),
                        "water_ledger": water_ledger, "solid_ledger": solid_ledger})
    water_ledger, solid_ledger = _ledger(water_in, math.fsum(item["water_ledger"]["ocean_export_m3"] for item in records),
                                       math.fsum(item["water_ledger"]["retained_m3"] for item in records), solid_in,
                                       math.fsum(item["solid_ledger"]["ocean_export_solid_m3"] for item in records),
                                       float(total_deposit.sum()), math.fsum(item["solid_ledger"]["unresolved_solid_m3"] for item in records), config.porosity,
                                       float(total_reentrained.sum()) if reentrainment_enabled else None,
                                       0., float(stored.sum()))
    metadata_config = asdict(config)
    if not reentrainment_enabled:
        metadata_config.pop("max_reentrainment_depth_per_interval_m")
    result = {"initial_bed_m": terrain.elevation_m, "final_bed_m": readonly(bed),
            "height_delta_m": readonly(bed - terrain.elevation_m), "deposited_solid_m3": readonly(total_deposit),
            "reentrained_solid_m3": readonly(total_reentrained), "stored_solid_m3": readonly(stored),
            "intervals": tuple(records), "water_ledger": water_ledger, "solid_ledger": solid_ledger,
            "metadata": {"algorithm_version": ("fluvial-delta-volume-routing-reentrainment-v1" if reentrainment_enabled
                                                else "fluvial-delta-volume-routing-v2"), "config": metadata_config,
                         "boundary_source_id": boundary.source_id, "terrain_identity_sha256": terrain.identity_sha256,
                         "boundary_identity_sha256": identity({"initial_ocean_mask": ocean, "ocean_export_mask": exports},
                                                              {"source_id": boundary.source_id, "sea_level_m": boundary.sea_level_m,
                                                               "river_head_m": boundary.river_head_m}),
                         "forcing": [asdict(interval) for interval in forcing],
                         "sea_level_m": boundary.sea_level_m, "river_head_m": boundary.river_head_m,
                         "interval_semantics": "prescribed volume passage; no physical duration inferred",
                         "routing_semantics": "bed-resistance connectivity approximation; river_head is an explicit admissibility ceiling, not a solved water surface",
                         "capacity_semantics": "equilibrium transported solid/water target with deposition bounded per generation interval; unrelaxed surplus continues downstream",
                         "capacity_formula": "water_m3 * capacity_solid_per_water * min(1, local_water_m3/inlet_water_m3)^flow_concentration_exponent * exp(-marine_capacity_decay_per_m * max(0, sea_level_m-bed_m))",
                         "flow_concentration_semantics": "local share of the interval inlet volume approximates reduced transport intensity after spreading; exponent is a generative closure, not calibrated hydraulics",
                         "retention_semantics": "retained water and unresolved solids are terminal escrow for this run; not reinjected in later intervals",
                         "hydraulic_certification_allowed": False}}
    if reentrainment_enabled:
        result["metadata"]["reentrainment_semantics"] = (
            "a transport-target deficit may reentrain only cover stored before the interval, bounded by that inventory "
            "and max_reentrainment_depth_per_interval_m converted using cell area and solid fraction; no bedrock erosion; "
            "deposited_solid_m3 and deposit_bulk_m3 are gross deposition, stored_solid_m3 is net cover inventory; "
            "sediment_throughput_solid_m3 records incoming sediment before local bed exchange")
    return result
