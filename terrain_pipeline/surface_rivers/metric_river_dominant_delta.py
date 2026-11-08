"""River-dominant distributary budget and thin grid adapter around the fluvial kernel.

The non-spatial comparator is an explicitly abstract volume comparison.  The
spatial entry point is a thin adapter: it validates a small explicit set of
inlet/outlet cells, runs exactly one :func:`simulate_fluvial_delta` so that
inventory and bed updates carry across intervals, and summarizes the kernel's
own outlet fluxes.  It introduces no second router.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from .metric_fluvial_delta import (
    FluvialDeltaBoundary,
    FluvialDeltaConfig,
    FluvialDeltaInterval,
    simulate_fluvial_delta,
)


def _finite(value, name, minimum=0.0, strict=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(name + " must be numeric")
    if not math.isfinite(value) or (value <= minimum if strict else value < minimum):
        raise ValueError(name + " outside finite range")
    return float(value)


@dataclass(frozen=True)
class RiverDominantComparisonConfig:
    """Nonspatial river-dominant comparison configuration.

    ``initial_branch_resistance`` is an optional explicit tuple with exactly
    ``branch_count`` entries; it provides a declared asymmetric starting point
    for tests.  Its default is equal resistance, i.e. no hidden index bias.
    """

    branch_count: int = 3
    bar_resistance_per_m3: float = 1e-4
    capacity_solid_per_water: float = 0.02
    initial_branch_resistance: tuple[float, ...] | None = None

    def __post_init__(self):
        if type(self.branch_count) is not int or not 2 <= self.branch_count <= 8:
            raise ValueError("branch_count must be an integer in [2, 8]")
        for name in ("bar_resistance_per_m3", "capacity_solid_per_water"):
            object.__setattr__(
                self, name, _finite(getattr(self, name), name)
            )
        if self.capacity_solid_per_water <= 0.0:
            raise ValueError("capacity_solid_per_water must be strictly positive")
        resistance = self.initial_branch_resistance
        if resistance is None:
            resistance = tuple(0.0 for _ in range(self.branch_count))
        elif not isinstance(resistance, tuple) or len(resistance) != self.branch_count:
            raise ValueError(
                "initial_branch_resistance must be a tuple with branch_count entries"
            )
        else:
            resistance = tuple(
                _finite(value, "initial_branch_resistance") for value in resistance
            )
        object.__setattr__(self, "initial_branch_resistance", resistance)


def simulate_river_dominant_budget(forcing, config=None):
    """Route supplied volumes through an abstract set of dynamic branches.

    Under-capacity load is transported to ocean export.  Only load strictly
    above the local transport target deposits.  With zero water the entire
    supplied solid stays unresolved and no water leaves the domain.
    Branch resistance rises from deposited solid using a declared linear
    feedback; this is an abstract comparison, not a mouth-bar prediction.
    """
    config = RiverDominantComparisonConfig() if config is None else config
    if not isinstance(config, RiverDominantComparisonConfig):
        raise ValueError("typed RiverDominantComparisonConfig required")
    if not isinstance(forcing, (tuple, list)) or not 1 <= len(forcing) <= 1024:
        raise ValueError("bounded nonempty forcing sequence required")
    if any(not isinstance(item, FluvialDeltaInterval) for item in forcing):
        raise ValueError("forcing must contain FluvialDeltaInterval values")

    try:
        volume_totals = [math.fsum(getattr(item, name) for item in forcing)
                         for name in ("water_volume_m3", "sediment_solid_m3")]
    except OverflowError:
        raise ValueError("forcing totals overflow") from None
    if not all(math.isfinite(value) for value in volume_totals):
        raise ValueError("forcing totals overflow")

    resistance = np.asarray(config.initial_branch_resistance, dtype=float).copy()
    records = []
    total_input_water = 0.0
    total_input_solid = 0.0
    total_deposited = 0.0
    total_export_solid = 0.0
    total_unresolved = 0.0
    total_export_water = 0.0
    total_retained_water = 0.0
    for index, interval in enumerate(forcing):
        water = float(interval.water_volume_m3)
        solid = float(interval.sediment_solid_m3)
        if water < 0.0 or solid < 0.0:
            raise ValueError("forcing volumes must be nonnegative")
        if not math.isfinite(water) or not math.isfinite(solid):
            raise ValueError("forcing volumes must be finite")

        if not math.isfinite(water * config.capacity_solid_per_water):
            raise ValueError("transport capacity overflow")

        if water == 0.0:
            # No water leaves the domain.  It cannot export or deposit solids.
            inverse = np.exp(-resistance - np.max(-resistance))
            shares = inverse / inverse.sum()
            deposited = np.zeros(config.branch_count)
            exported_solid = np.zeros(config.branch_count)
            branch_water = np.zeros(config.branch_count)
            unresolved = solid
            retained = 0.0
            exported_water = 0.0
        else:
            # Share of water/incoming load by resistance alone; no index bias.
            inverse = np.exp(-resistance - np.max(-resistance))
            shares = inverse / inverse.sum()
            branch_water = water * shares
            branch_solid = solid * shares
            branch_capacity = branch_water * config.capacity_solid_per_water
            # Under-capacity is transported; only excess deposits.
            deposited = np.maximum(0.0, branch_solid - branch_capacity)
            exported_solid = branch_solid - deposited
            exported_water = float(branch_water.sum())
            retained = 0.0
            unresolved = 0.0

        # Linear bed-resistance feedback, declared as an approximation.
        with np.errstate(over="ignore", invalid="ignore"):
            resistance = resistance + config.bar_resistance_per_m3 * deposited
        if not np.isfinite(resistance).all():
            raise ValueError("branch resistance overflow")
        record = {
            "interval_index": index,
            "branch_water_m3": branch_water.tolist(),
            "branch_share": shares.tolist(),
            "deposited_solid_m3": deposited.tolist(),
            "ocean_export_solid_m3": exported_solid.tolist(),
            "unresolved_solid_m3": float(unresolved),
            "ocean_export_water_m3": float(exported_water),
            "retained_water_m3": float(retained),
            "resistance": resistance.copy().tolist(),
            "solid_residual_m3": float(
                solid - deposited.sum() - exported_solid.sum() - unresolved
            ),
            "water_residual_m3": float(
                water - exported_water - retained
            ),
        }
        records.append(record)
        total_input_water += water
        total_input_solid += solid
        total_deposited += float(deposited.sum())
        total_export_solid += float(exported_solid.sum())
        total_unresolved += float(unresolved)
        total_export_water += float(exported_water)
        total_retained_water += float(retained)

    totals = {
        "input_water_m3": total_input_water,
        "input_solid_m3": total_input_solid,
        "deposited_solid_m3": total_deposited,
        "ocean_export_solid_m3": total_export_solid,
        "unresolved_solid_m3": total_unresolved,
        "ocean_export_water_m3": total_export_water,
        "retained_water_m3": total_retained_water,
        "solid_residual_m3": total_input_solid
        - total_deposited
        - total_export_solid
        - total_unresolved,
        "water_residual_m3": total_input_water
        - total_export_water
        - total_retained_water,
    }
    metadata = {
        "mode": "river_dominant_nonspatial_comparison",
        "algorithm_version": "river-dominant-nonspatial-volume-v1",
        "terrain_mutated": False,
        "wave_boundary": "off",
        "tide_boundary": "off",
        "semantics": (
            "abstract finite supplied solid budget; under-capacity load is "
            "transported to ocean export; only excess above transport target "
            "deposits; zero water leaves solid unresolved and exports nothing"
        ),
        "resistance_feedback": (
            "declared nonspatial linear resistance feedback from deposited solid; "
            "not a real mouth-bar prediction"
        ),
        "hydraulic_certification_allowed": False,
    }
    return {"records": records, "totals": totals, "metadata": metadata}


def _validate_boundary_shapes(terrain, boundary):
    shape = terrain.elevation_m.shape
    if boundary.ocean_export_mask.shape != shape:
        raise ValueError("ocean_export_mask shape differs from terrain")
    if boundary.initial_ocean_mask.shape != shape:
        raise ValueError("initial_ocean_mask shape differs from terrain")
    if terrain.valid_mask.shape != shape:
        raise ValueError("valid_mask shape differs from terrain")


def _validate_outlet_cells(terrain, boundary, outlet_cells):
    if not isinstance(outlet_cells, (tuple, list)) or not outlet_cells:
        raise ValueError("nonempty outlet_cells sequence required")
    shape = terrain.elevation_m.shape
    seen = set()
    for cell in outlet_cells:
        if (
            not isinstance(cell, tuple)
            or len(cell) != 2
            or any(type(value) is not int for value in cell)
        ):
            raise ValueError("outlet cells must be integer (row, column) tuples")
        row, column = cell
        if row < 0 or row >= shape[0] or column < 0 or column >= shape[1]:
            raise ValueError("outlet cell outside grid")
        if cell in seen:
            raise ValueError("duplicate outlet cell")
        seen.add(cell)
        if not boundary.ocean_export_mask[row, column]:
            raise ValueError("outlet cell must be declared in ocean_export_mask")
    declared_rows, declared_columns = np.nonzero(boundary.ocean_export_mask)
    declared = {(int(r), int(c)) for r, c in zip(declared_rows, declared_columns)}
    if declared != seen:
        raise ValueError("outlet_cells must cover ocean_export_mask exactly")
    return seen


def _validate_inlet(terrain, boundary, inlet_cell):
    if (
        not isinstance(inlet_cell, tuple)
        or len(inlet_cell) != 2
        or any(type(value) is not int for value in inlet_cell)
    ):
        raise ValueError("inlet_cell must be an integer (row, column) tuple")
    row, column = inlet_cell
    if row < 0 or row >= terrain.elevation_m.shape[0] or column < 0 or column >= terrain.elevation_m.shape[1]:
        raise ValueError("inlet cell outside grid")
    if not terrain.valid_mask[row, column]:
        raise ValueError("inlet cell must be valid terrain")
    if boundary.ocean_export_mask[row, column]:
        raise ValueError("inlet cell cannot be an outlet")
    return inlet_cell


def simulate_river_dominant_grid(terrain, boundary, inlet_cell, outlet_cells, forcing, config=None):
    """Thin adapter around :func:`simulate_fluvial_delta`.

    One complete kernel run is reused so that bed changes and stored solid
    carry across all intervals.  Reported branch shares are the kernel's own
    outlet water fluxes, not an independent branch model.
    """
    if not isinstance(terrain, TerrainGrid):
        raise ValueError("typed TerrainGrid required")
    if not isinstance(boundary, FluvialDeltaBoundary):
        raise ValueError("typed FluvialDeltaBoundary required")
    config = FluvialDeltaConfig() if config is None else config
    if not isinstance(config, FluvialDeltaConfig):
        raise ValueError("typed FluvialDeltaConfig required")
    _validate_boundary_shapes(terrain, boundary)
    inlet_cell = _validate_inlet(terrain, boundary, inlet_cell)
    _validate_outlet_cells(terrain, boundary, outlet_cells)

    if not isinstance(forcing, (tuple, list)) or not 1 <= len(forcing) <= config.max_intervals:
        raise ValueError("bounded nonempty forcing sequence required")
    for interval in forcing:
        if not isinstance(interval, FluvialDeltaInterval):
            raise ValueError("typed forcing intervals required")
        if interval.inlet_cell != inlet_cell:
            raise ValueError("forcing interval inlet_cell must equal declared inlet_cell")

    kernel = simulate_fluvial_delta(terrain, boundary, forcing, config)

    outlet_array = np.asarray(outlet_cells, dtype=np.int64)
    outlet_rows = outlet_array[:, 0]
    outlet_columns = outlet_array[:, 1]
    n_outlets = len(outlet_cells)

    porosity = config.porosity
    cell_area = float(terrain.cell_area_m2)

    branch_history = []
    for index, record in enumerate(kernel["intervals"]):
        water_throughput = np.asarray(record["water_throughput_m3"], dtype=float)
        solid_throughput = np.asarray(record["sediment_throughput_solid_m3"], dtype=float)
        deposited = np.asarray(record["deposited_solid_m3"], dtype=float)
        stored = np.asarray(record["stored_solid_m3"], dtype=float)
        ledger = record["water_ledger"]
        solid_ledger = record["solid_ledger"]

        outlet_water = water_throughput[outlet_rows, outlet_columns]
        outlet_solid = solid_throughput[outlet_rows, outlet_columns]
        exported_water = float(ledger["ocean_export_m3"])
        if exported_water > 0.0:
            shares = outlet_water / exported_water
        else:
            shares = np.zeros(n_outlets)
        shares = [float(value) for value in shares]

        with np.errstate(divide="ignore", invalid="ignore"):
            bed_after = terrain.elevation_m + stored / ((1.0 - porosity) * cell_area)
        if not np.isfinite(bed_after[terrain.valid_mask]).all():
            raise ValueError("bed after interval is not finite")

        branch_history.append(
            {
                "interval_index": index,
                "outlet_cells": [list(cell) for cell in outlet_cells],
                "outlet_water_m3": outlet_water.tolist(),
                "outlet_solid_m3": outlet_solid.tolist(),
                "branch_share": shares,
                "ocean_export_water_m3": exported_water,
                "retained_water_m3": float(ledger["retained_m3"]),
                "deposited_solid_m3": deposited,
                "reentrained_solid_m3": record["reentrained_solid_m3"],
                "stored_solid_m3": stored,
                "unresolved_solid_m3": float(solid_ledger["unresolved_solid_m3"]),
                "ocean_export_solid_m3": float(solid_ledger["ocean_export_solid_m3"]),
                "solid_ledger": solid_ledger,
                "bed_after_m": bed_after.copy(),
            }
        )

    solid_ledger = kernel["solid_ledger"]
    sediment_budget = {
        "input_solid_m3": float(solid_ledger["input_solid_m3"]),
        "deposited_solid_m3": float(solid_ledger["deposited_solid_m3"]),
        "ocean_export_solid_m3": float(solid_ledger["ocean_export_solid_m3"]),
        "unresolved_solid_m3": float(solid_ledger["unresolved_solid_m3"]),
        "deposit_bulk_m3": float(solid_ledger["deposit_bulk_m3"]),
        "solid_residual_m3": float(solid_ledger["residual_solid_m3"]),
    }
    if "reentrained_solid_m3" in solid_ledger:
        sediment_budget.update(
            {
                "initial_stored_solid_m3": float(solid_ledger["initial_stored_solid_m3"]),
                "reentrained_solid_m3": float(solid_ledger["reentrained_solid_m3"]),
                "stored_solid_m3": float(solid_ledger["stored_solid_m3"]),
                "stored_bulk_m3": float(solid_ledger["stored_bulk_m3"]),
            }
        )
    else:
        sediment_budget.update(
            {
                "reentrained_solid_m3": float(kernel["reentrained_solid_m3"].sum()),
                "stored_solid_m3": float(kernel["stored_solid_m3"].sum()),
                "stored_bulk_m3": float(kernel["stored_solid_m3"].sum()) / (1.0 - porosity),
            }
        )
    water_budget = {
        "input_water_m3": float(kernel["water_ledger"]["input_m3"]),
        "ocean_export_water_m3": float(kernel["water_ledger"]["ocean_export_m3"]),
        "retained_water_m3": float(kernel["water_ledger"]["retained_m3"]),
        "water_residual_m3": float(kernel["water_ledger"]["residual_m3"]),
    }

    metadata = {
        "mode": "river_dominant_grid_adapter",
        "algorithm_version": "river-dominant-grid-adapter-v1",
        "kernel_algorithm_version": kernel["metadata"]["algorithm_version"],
        "terrain_mutated": False,
        "wave_boundary": "off",
        "tide_boundary": "off",
        "inlet_cell": list(inlet_cell),
        "outlet_cells": [list(cell) for cell in outlet_cells],
        "terrain_identity_sha256": kernel["metadata"]["terrain_identity_sha256"],
        "boundary_identity_sha256": kernel["metadata"]["boundary_identity_sha256"],
        "boundary_source_id": kernel["metadata"]["boundary_source_id"],
        "config": asdict(config),
        "forcing": kernel["metadata"]["forcing"],
        "semantics": (
            "thin adapter around fluvial kernel: single run, inventory and bed "
            "carry across intervals; branch shares are kernel outlet water "
            "fluxes over exported water"
        ),
        "hydraulic_semantics": (
            "bed-resistance approximation with prescribed river-head ceiling; "
            "NOT a solved water surface"
        ),
        "permit_bed_attribution": False,
        "hydraulic_certification_allowed": False,
    }

    return {
        "final_bed_m": kernel["final_bed_m"],
        "branch_history": branch_history,
        "sediment_budget": sediment_budget,
        "water_budget": water_budget,
        "spatial_result": kernel,
        "deposited_solid_m3": kernel["deposited_solid_m3"],
        "intervals": kernel["intervals"],
        "metadata": metadata,
    }
