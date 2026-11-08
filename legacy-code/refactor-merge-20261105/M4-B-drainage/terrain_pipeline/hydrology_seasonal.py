"""Fixed-bed planning water balance, not river-network hydraulics.

A capacity-limited soil bucket and exponential soil drainage route instantaneously
to each frozen domain terminal. There is no groundwater sink or erosion. Climate
is a repeating, synthetic twelve-month scenario, not calibrated weather.
"""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.surface_rivers.metric_noise_forcing import NoiseClimateParameters, sample_climate


ALGORITHM = "hydrology-seasonal-planning-v1"
PERIODIC_SOLVER = "hydrology-periodic-shooting-full-trajectory-v2"
WATER_STEP_ALGORITHM = "hydrology-conservative-real-shore-events-v2"
SHORE_EVENT_SCHEMA = "hydrology-shore-events-domain-step-v1"
MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
LAKE_NEIGHBORS = tuple((dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
LEDGER_KEYS = ("land_rain_m3", "lake_rain_m3", "land_et_m3", "lake_evaporation_m3",
               "runoff_to_terminal_m3", "coastal_outflow_m3", "soil_change_m3",
               "lake_change_m3")


class SeasonalBalanceError(ValueError):
    """A bounded planning failure; no partially published result."""
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {"status": "failed", "reason": message}


@dataclass(frozen=True)
class SeasonalConfig:
    soil_capacity_mm: float = 120.0
    soil_drainage_days: float = 45.0
    pet_base_mm_per_day: float = 0.5
    pet_temperature_mm_per_day_c: float = 0.12
    climate_noise_scale_m: float = 60000.0
    substeps_per_day: int = 1
    max_years: int = 150
    convergence_depth_mm: float = 0.01
    convergence_lake_level_m: float = 0.001
    max_cells: int = 100000

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"invalid seasonal parameter {name}")
        for name in ("substeps_per_day", "max_years", "max_cells"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.substeps_per_day > 24 or self.max_years > 1000:
            raise ValueError("seasonal work budget exceeded")


def seasonal_climate(plan, config=None):
    """Monthly depths [12,z,x]; month identity repeats every simulation year."""
    config = config or SeasonalConfig()
    height = np.asarray(plan["height_m"])
    z, x = np.indices(height.shape)
    origin = plan["origin_xz_m"]
    x = origin[0] + x * plan["spacing_m"]
    z = origin[1] + z * plan["spacing_m"]
    sampled = sample_climate(plan["seed"], x, z, height,
                             parameters=NoiseClimateParameters(regional_scale_m=config.climate_noise_scale_m))
    temperature = sampled["monthly_temperature_c"]
    # Explicit illustrative temperature-index PET; no observed radiation/humidity.
    pet = (config.pet_base_mm_per_day + config.pet_temperature_mm_per_day_c * np.maximum(temperature, 0))
    return {"precipitation_mm": sampled["monthly_precipitation_mm"],
            "potential_et_mm": pet * MONTH_DAYS[:, None, None],
            "temperature_c": temperature}


class LakeGeometry:
    """Exact piecewise linear volume from connected raster bed columns."""
    def __init__(self, height, owner, domain, cell_area):
        self.spill_m = float(domain["lake_spill_elevation_m"])
        terminal = int(domain["lake_terminal_index"])
        flat = height.ravel()
        if not math.isfinite(self.spill_m) or terminal < 0 or terminal >= flat.size:
            raise ValueError("invalid lake terminal or spill")
        eligible = (owner == domain["domain_id"]) & (height < self.spill_m)
        if not eligible.ravel()[terminal]:
            raise ValueError("lake terminal must lie below its spill")
        self.mask = np.zeros(height.shape, dtype=bool)
        stack = [terminal]
        width = height.shape[1]
        self.mask.ravel()[terminal] = True
        while stack:
            index = stack.pop()
            row, col = divmod(index, width)
            for dr, dc in LAKE_NEIGHBORS:
                rr, cc = row + dr, col + dc
                if 0 <= rr < height.shape[0] and 0 <= cc < width and eligible[rr, cc] and not self.mask[rr, cc]:
                    self.mask[rr, cc] = True
                    stack.append(rr * width + cc)
        self.beds = np.sort(height[self.mask])
        # This first version supports one simple depression only. Reject nested
        # low pockets separated by a saddle rather than flooding disconnected beds.
        indices = np.flatnonzero(self.mask)
        order = indices[np.argsort(flat[indices], kind="stable")]
        parent = np.full(flat.size, -1, dtype=np.int64)
        components = 0
        def root(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index
        offset = 0
        while offset < len(order):
            end = offset + 1
            while end < len(order) and flat[order[end]] == flat[order[offset]]:
                end += 1
            group = order[offset:end]
            for index in group:
                parent[index] = index
                components += 1
            for index in group:
                row, col = divmod(int(index), width)
                for dr, dc in LAKE_NEIGHBORS:
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < height.shape[0] and 0 <= cc < width:
                        neighbor = rr * width + cc
                        if parent[neighbor] >= 0:
                            a, b = root(index), root(neighbor)
                            if a != b:
                                parent[a] = b
                                components -= 1
            if components != 1 or parent[terminal] < 0:
                raise SeasonalBalanceError("nested disconnected lake pockets require unsupported multi-pool routing")
            offset = end
        self.cell_area_m2 = cell_area
        self.prefix = np.concatenate(([0.0], np.cumsum(self.beds)))
        self.break_volumes = (self.beds * np.arange(len(self.beds)) - self.prefix[:-1]) * cell_area
        self.capacity_m3 = self.volume(self.spill_m)

    def volume(self, level_m):
        return float(np.maximum(level_m - self.beds, 0).sum() * self.cell_area_m2)

    def level(self, volume_m3):
        if volume_m3 < 0 or not math.isfinite(volume_m3):
            raise ValueError("invalid lake storage")
        count = min(int(np.searchsorted(self.break_volumes, volume_m3, side="right")), len(self.beds))
        return float((volume_m3 / self.cell_area_m2 + self.prefix[count]) / count)


def _inputs(plan, config, climate):
    height = np.asarray(plan["height_m"], dtype=float)
    owner = np.asarray(plan["owner_domain_id"])
    if height.ndim != 2 or height.size > config.max_cells or owner.shape != height.shape or not np.isfinite(height).all():
        raise ValueError("invalid or over-budget seasonal terrain")
    spacing = float(plan["spacing_m"])
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid spacing")
    domains = plan["domains"]
    ids = [d["domain_id"] for d in domains]
    if not ids or len(set(ids)) != len(ids) or np.any(~np.isin(owner, [-2, -1] + ids)):
        raise ValueError("invalid seasonal ownership")
    area = np.full(height.shape, spacing**2)
    hybrid = plan.get("seasonal_hybrid")
    lakes = {}
    if hybrid is not None:
        from terrain_pipeline.hydrology_seasonal_hybrid import hybrid_column_inputs
        area, lakes = hybrid_column_inputs(plan)
    for column, domain in enumerate(domains):
        if domain["kind"] == "inland":
            if hybrid is None:
                lakes[column] = LakeGeometry(height, owner, domain, spacing**2)
        elif domain["kind"] != "coastal":
            raise ValueError("unsupported terminal type")
    climate = seasonal_climate(plan, config) if climate is None else climate
    for name in ("precipitation_mm", "potential_et_mm"):
        value = np.asarray(climate[name], dtype=float)
        if value.shape != (12,) + height.shape or not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError(f"invalid climate {name}")
    if hybrid is not None:
        hybrid_column_inputs(plan, climate)
    return height, owner, domains, lakes, area, climate


def _area_sum(values, mask, area):
    return float(np.sum(values[mask] * area[mask]))


def _year_discrete(height, owner, domains, lakes, area, climate, config, soil, lake_volume, retain=False):
    count = len(domains)
    monthly = {key: np.zeros((12, count)) for key in LEDGER_KEYS}
    soil_months, volume_months = [soil.copy()], [lake_volume.copy()]
    steps, inventories = [], []
    masks = [owner == domain["domain_id"] for domain in domains]
    drainage_fraction = -math.expm1(-1 / (config.substeps_per_day * config.soil_drainage_days))
    def inventory():
        return np.array([_area_sum(soil, mask, area) / 1000 + lake_volume[c] for c, mask in enumerate(masks)])
    inventories.append(inventory())
    for month, days in enumerate(MONTH_DAYS):
        for unused_step in range(int(days) * config.substeps_per_day):
            wet = np.zeros(height.shape, dtype=bool)
            for column, lake in lakes.items():
                if lake_volume[column] > 0:
                    wet |= lake.mask & (height < lake.level(lake_volume[column]))
            land = (owner >= 0) & ~wet
            rain = climate["precipitation_mm"][month] / (days * config.substeps_per_day)
            pet = climate["potential_et_mm"][month] / (days * config.substeps_per_day)
            before_soil = soil.copy()
            available = soil + np.where(land, rain, 0)
            excess = np.where(land, np.maximum(available - config.soil_capacity_mm, 0), 0)
            available -= excess
            et = np.where(land, np.minimum(available, pet), 0)
            available -= et
            drainage = np.where(land, available * drainage_fraction, 0)
            soil = available - drainage
            runoff = (excess + drainage) * area / 1000
            ledger = {key: np.zeros(count) for key in LEDGER_KEYS}
            for column, mask in enumerate(masks):
                ledger["land_rain_m3"][column] = _area_sum(rain, mask & land, area) / 1000
                ledger["land_et_m3"][column] = _area_sum(et, mask, area) / 1000
                ledger["runoff_to_terminal_m3"][column] = runoff[mask].sum()
                ledger["soil_change_m3"][column] = _area_sum(soil - before_soil, mask, area) / 1000
                if column not in lakes:
                    ledger["coastal_outflow_m3"][column] = runoff[mask].sum()
                    continue
                direct = _area_sum(rain, mask & wet, area) / 1000
                supply = lake_volume[column] + runoff[mask].sum() + direct
                evaporation = min(supply, _area_sum(pet, mask & wet, area) / 1000)
                after = supply - evaporation
                lake = lakes[column]
                if after >= lake.capacity_m3:
                    raise SeasonalBalanceError("inland lake reaches spill: no certified in-domain downstream outlet")
                ledger["lake_rain_m3"][column] = direct
                ledger["lake_evaporation_m3"][column] = evaporation
                ledger["lake_change_m3"][column] = after - lake_volume[column]
                lake_volume[column] = after
            for key in LEDGER_KEYS:
                monthly[key][month] += ledger[key]
            if retain:
                steps.append(ledger)
                inventories.append(inventory())
        if retain:
            soil_months.append(soil.copy())
            volume_months.append(lake_volume.copy())
    return soil, lake_volume, monthly, soil_months, volume_months, steps, inventories


def _shore_segment(soil, volume, rain, pet, area, wet_fraction, dt_days, config):
    land = 1 - wet_fraction
    supplied = soil + rain * dt_days
    excess = np.maximum(supplied - config.soil_capacity_mm, 0)
    available = supplied - excess
    et = np.minimum(available, pet * dt_days)
    available -= et
    drainage = available * -math.expm1(-dt_days / config.soil_drainage_days)
    after_soil = soil + land * (available - drainage - soil)
    summed = lambda values: float(np.sum(values * area) / 1000)
    runoff = summed(land * (excess + drainage))
    direct = summed(wet_fraction * rain * dt_days)
    evaporation = min(volume + runoff + direct, summed(wet_fraction * pet * dt_days))
    after_volume = volume + runoff + direct - evaporation
    ledger = {"land_rain_m3": summed(land * rain * dt_days), "lake_rain_m3": direct,
              "land_et_m3": summed(land * et), "lake_evaporation_m3": evaporation,
              "runoff_to_terminal_m3": runoff, "coastal_outflow_m3": 0.,
              "soil_change_m3": summed(after_soil - soil), "lake_change_m3": after_volume - volume}
    return after_soil, after_volume, ledger


def _shore_step(beds, membership, soil, volume, rain, pet, area, lake, dt_days, config):
    """Split only at real bed-volume thresholds; stationary ties mix fluxes."""
    from scipy.optimize import brentq
    if not hasattr(lake, "shore_thresholds"):
        levels = np.concatenate((np.unique(lake.beds), [lake.spill_m]))
        thresholds = np.array([lake.volume(float(level)) for level in levels])
        thresholds, indices = np.unique(thresholds, return_index=True)
        lake.shore_thresholds = thresholds, levels[indices]
    thresholds, levels = lake.shore_thresholds
    remaining = dt_days
    ledger = {key: 0. for key in LEDGER_KEYS}
    events = []
    for unused in range(1024):
        level = lake.level(volume)
        wet = (membership & (beds < level)).astype(float)
        near = np.flatnonzero(np.abs(thresholds - volume) <= max(1e-7, abs(volume) * 8 * np.finfo(float).eps))
        if len(near):
            threshold_index = int(near[np.argmin(np.abs(thresholds[near] - volume))])
            threshold = float(thresholds[threshold_index])
            ties = membership & (beds == levels[threshold_index])
            if ties.any() and volume > 0:
                dry = wet.copy()
                dry[ties] = 0
                submerged = dry.copy()
                submerged[ties] = 1
                first = _shore_segment(soil, volume, rain, pet, area, dry, remaining, config)
                second = _shore_segment(soil, volume, rain, pet, area, submerged, remaining, config)
                low, high = first[1] - volume, second[1] - volume
                if low >= 0 and high <= 0 and low != high:
                    fraction = low / (low - high)
                    wet = dry + ties * fraction
                    after, end, account = _shore_segment(soil, volume, rain, pet, area, wet, remaining, config)
                    if abs(end - volume) > max(1e-6, abs(volume) * 16 * np.finfo(float).eps):
                        raise SeasonalBalanceError("shoreline fractional flux does not conserve threshold storage")
                    events.append({"kind": "stationary_real_shore", "level_m": float(levels[threshold_index]),
                                   "dt_days": remaining, "wet_fraction": float(fraction),
                                   "tied_area_m2": float(area[ties].sum())})
                    for key in ledger:
                        ledger[key] += account[key]
                    return after, end, ledger, events
                wet = submerged if low >= 0 and high >= 0 else dry
        after, end, account = _shore_segment(soil, volume, rain, pet, area, wet, remaining, config)
        tolerance = max(1e-7, abs(volume) * 8 * np.finfo(float).eps)
        if end > volume:
            crossings = thresholds[(thresholds > volume + tolerance) & (thresholds < end)]
            target = float(crossings[0]) if len(crossings) else None
        else:
            crossings = thresholds[(thresholds < volume - tolerance) & (thresholds > end)]
            target = float(crossings[-1]) if len(crossings) else None
        if target is None:
            if end >= lake.capacity_m3:
                raise SeasonalBalanceError("inland lake reaches spill: no certified in-domain downstream outlet")
            for key in ledger:
                ledger[key] += account[key]
            return after, end, ledger, events
        dt = brentq(lambda duration: _shore_segment(soil, volume, rain, pet, area, wet, duration, config)[1] - target,
                    0., remaining, xtol=1e-12, maxiter=64)
        if dt <= 0 or dt >= remaining:
            raise SeasonalBalanceError("shore crossing failed to advance physical time")
        soil, volume, account = _shore_segment(soil, volume, rain, pet, area, wet, dt, config)
        events.append({"kind": "real_bed_crossing", "level_m": float(lake.level(target)), "dt_days": dt})
        for key in ledger:
            ledger[key] += account[key]
        remaining -= dt
    raise SeasonalBalanceError("shoreline event work budget exceeded; remaining time not discarded",
                               {"remaining_dt_days": remaining, "event_limit": 1024})


def _year(height, owner, domains, lakes, area, climate, config, soil, lake_volume, retain=False):
    count = len(domains)
    masks = [owner == domain["domain_id"] for domain in domains]
    monthly = {key: np.zeros((12, count)) for key in LEDGER_KEYS}
    soils, volumes, steps = [soil.copy()], [lake_volume.copy()], []
    inventory = lambda: np.array([float(np.sum(soil[mask] * area[mask]) / 1000) + lake_volume[c]
                                 for c, mask in enumerate(masks)])
    inventories = [inventory()]
    dt = 1 / config.substeps_per_day
    for month, days in enumerate(MONTH_DAYS):
        rain = climate["precipitation_mm"][month] / days
        pet = climate["potential_et_mm"][month] / days
        for unused in range(int(days) * config.substeps_per_day):
            account = {key: np.zeros(count) for key in LEDGER_KEYS}
            step_events = []
            for column, mask in enumerate(masks):
                if column in lakes:
                    lake = lakes[column]
                    after, end, part, witness = _shore_step(height[mask], lake.mask[mask], soil[mask],
                        lake_volume[column], rain[mask], pet[mask], area[mask], lake, dt, config)
                    soil[mask], lake_volume[column] = after, end
                    if retain:
                        step_events.extend(dict(event, domain_id=domains[column]["domain_id"]) for event in witness)
                else:
                    after, unused_volume, part = _shore_segment(soil[mask], 0., rain[mask], pet[mask],
                        area[mask], np.zeros(np.count_nonzero(mask)), dt, config)
                    soil[mask] = after
                    part["coastal_outflow_m3"] = part["runoff_to_terminal_m3"]
                    part["lake_change_m3"] = 0.
                for key in LEDGER_KEYS:
                    account[key][column] = part[key]
            for key in monthly:
                monthly[key][month] += account[key]
            if retain:
                account["shore_events"] = step_events
                steps.append(account)
                inventories.append(inventory())
        if retain:
            soils.append(soil.copy())
            volumes.append(lake_volume.copy())
    return soil, lake_volume, monthly, soils, volumes, steps, inventories


def simulate_seasonal_water_balance(plan, config=None, climate=None, *, initial_soil_mm=None, initial_lake_volume_m3=None):
    """Converge the complete annual soil/lake state or fail within max_years."""
    config = config or SeasonalConfig()
    height, owner, domains, lakes, area, climate = _inputs(plan, config, climate)
    soil = np.zeros(height.shape) if initial_soil_mm is None else np.asarray(initial_soil_mm, dtype=float).copy()
    volumes = np.zeros(len(domains)) if initial_lake_volume_m3 is None else np.asarray(initial_lake_volume_m3, dtype=float).copy()
    if soil.shape != height.shape or not np.isfinite(soil).all() or np.any(soil < 0) or np.any(soil > config.soil_capacity_mm):
        raise ValueError("invalid initial soil storage")
    if volumes.shape != (len(domains),) or not np.isfinite(volumes).all() or np.any(volumes < 0):
        raise ValueError("invalid initial lake storage")
    soil[owner < 0] = 0
    for column in range(len(domains)):
        if (column not in lakes and volumes[column] != 0) or (column in lakes and volumes[column] >= lakes[column].capacity_m3):
            raise ValueError("invalid terminal initial storage")
    domain_areas = np.array([area[owner == d["domain_id"]].sum() for d in domains])
    if np.any(domain_areas <= 0):
        raise ValueError("empty planning domain")
    evaluations = 0
    shooting_iterations = 0
    shooting_trials = []
    # A deep lake may need thousands of dry-start years. Solve its annual map
    # instead; soil is itself cycled at each trial boundary volume. Trial resets
    # are boundary-value evaluations, never part of the accepted water ledger.
    if lakes and initial_lake_volume_m3 is None:
        if len(lakes) != 1:
            raise SeasonalBalanceError("periodic shooting currently requires one inland lake")
        column, lake = next(iter(lakes.items()))
        low, high = 0.0, lake.capacity_m3
        best = None
        while evaluations < config.max_years - 3:
            if shooting_iterations and np.nextafter(low, np.inf) >= high:
                reason = "no annual lake fixed point below spill: positive drift meets overflow or discrete wet-area jump"
                raise SeasonalBalanceError(reason, {"status": "failed", "reason": reason,
                    "algorithm": ALGORITHM, "source_plan_identity_sha256": plan.get("identity_sha256"),
                    "parameters": asdict(config), "annual_map_evaluations": evaluations,
                    "shooting_iterations": shooting_iterations, "lake_spill_m": lake.spill_m,
                    "lower_level_m": lake.level(low), "upper_level_m": lake.level(high),
                    "trials": shooting_trials})
            trial = low if shooting_iterations == 0 else (low + high) / 2
            trial_soil = soil.copy()
            trial_volumes = np.zeros(len(domains))
            trial_volumes[column] = trial
            overflow = False
            soil_stable = False
            previous_trial_soil = previous_residual = None
            for unused_cycle in range(12):
                if evaluations >= config.max_years - 3:
                    break
                before_soil = trial_soil.copy()
                evaluations += 1
                try:
                    trial_soil, end_volumes, *_ = _year(height, owner, domains, lakes, area, climate,
                                                       config, trial_soil, trial_volumes.copy())
                except SeasonalBalanceError:
                    overflow = True
                    break
                residual = trial_soil - before_soil
                if np.max(np.abs(residual)) <= config.convergence_depth_mm:
                    soil_stable = True
                    break
                # The frozen submerged store can expose for only one day/year.
                # A bounded diagonal secant proposal avoids centuries of plain
                # soil iteration. Every proposal is verified by another year.
                if previous_residual is not None:
                    denominator = residual - previous_residual
                    usable = np.abs(denominator) > 1e-10
                    proposal = before_soil.copy()
                    np.divide(residual * (before_soil - previous_trial_soil), denominator,
                              out=proposal, where=usable)
                    proposal = before_soil - proposal
                    admissible = usable & (proposal >= 0) & (proposal <= config.soil_capacity_mm)
                    trial_soil = np.where(admissible, proposal, trial_soil)
                previous_trial_soil, previous_residual = before_soil, residual
            shooting_iterations += 1
            if overflow:
                shooting_trials.append({"initial_level_m": lake.level(trial), "status": "spill_failure",
                                        "annual_map_evaluations": evaluations})
                high = trial
                if trial == 0:
                    raise SeasonalBalanceError("dry lake reaches spill within one annual forcing cycle")
                continue
            if not soil_stable:
                reason = "shooting soil cycle did not converge within annual work budget"
                raise SeasonalBalanceError(reason, {"status": "failed", "reason": reason,
                    "periodic_solver_algorithm": PERIODIC_SOLVER, "parameters": asdict(config),
                    "source_plan_identity_sha256": plan.get("identity_sha256"),
                    "annual_map_evaluations": evaluations, "trial_level_m": lake.level(trial),
                    "soil_cycle_error_mm": float(np.max(np.abs(residual))),
                    "shooting_trials": shooting_trials})
            drift = end_volumes[column] - trial
            level_drift = abs(lake.level(end_volumes[column]) - lake.level(trial))
            shooting_trials.append({"initial_level_m": lake.level(trial), "status": "soil_cycle_verified",
                                    "annual_storage_drift_m3": float(drift), "annual_level_drift_m": lake.level(end_volumes[column]) - lake.level(trial),
                                    "soil_cycle_error_mm": float(np.max(np.abs(trial_soil - before_soil))),
                                    "annual_map_evaluations": evaluations})
            if (abs(drift) / domain_areas[column] * 1000 <= config.convergence_depth_mm
                    and level_drift <= config.convergence_lake_level_m and evaluations + 2 < config.max_years - 3):
                # Wet/dry events can amplify a small boundary drift into a
                # nonperiodic soil trajectory. Check the actual map before
                # accepting this root and spending the remaining budget.
                first = _year(height, owner, domains, lakes, area, climate,
                              config, before_soil.copy(), trial_volumes.copy(), retain=True)
                second = _year(height, owner, domains, lakes, area, climate,
                               config, first[0].copy(), first[1].copy(), retain=True)
                evaluations += 2
                trajectory_soil_error = float(np.max(np.abs(np.array(first[3]) - np.array(second[3]))))
                trajectory_level_error = max(abs(lake.level(a[column]) - lake.level(b[column]))
                                             for a, b in zip(first[4], second[4]))
                shooting_trials[-1].update(full_trajectory_soil_error_mm=trajectory_soil_error,
                    full_trajectory_level_error_m=trajectory_level_error,
                    annual_map_evaluations=evaluations)
                if (trajectory_soil_error <= config.convergence_depth_mm
                        and trajectory_level_error <= config.convergence_lake_level_m):
                    best = (before_soil, trial_volumes)
                    break
            if drift > 0:
                low = trial
            else:
                high = trial
            soil = trial_soil
        if best is None:
            reason = "annual lake shooting did not converge within max_years"
            raise SeasonalBalanceError(reason, {"status": "failed", "reason": reason,
                "periodic_solver_algorithm": PERIODIC_SOLVER, "annual_map_evaluations": evaluations,
                "parameters": asdict(config), "source_plan_identity_sha256": plan.get("identity_sha256"),
                "shooting_trials": shooting_trials, "lower_level_m": lake.level(low), "upper_level_m": lake.level(high)})
        soil, volumes = best
    annual_evaluations = evaluations
    soil_error = lake_error = level_error = None
    for year in range(1, config.max_years - evaluations - 1):
        initial_soil, initial_volumes = soil.copy(), volumes.copy()
        soil, volumes, *_ = _year(height, owner, domains, lakes, area, climate, config, soil, volumes)
        annual_evaluations += 1
        soil_error = float(np.max(np.abs(soil - initial_soil)))
        lake_error = float(np.max(np.abs(volumes - initial_volumes) / domain_areas * 1000))
        level_error = max((abs(lake.level(volumes[c]) - lake.level(initial_volumes[c]))
                           for c, lake in lakes.items()), default=0.0)
        if max(soil_error, lake_error) <= config.convergence_depth_mm and level_error <= config.convergence_lake_level_m:
            break
    else:
        reason = "annual soil and lake state did not converge within max_years"
        raise SeasonalBalanceError(reason, {"status": "failed", "reason": reason,
            "annual_map_evaluations": annual_evaluations,
            "annual_boundary_soil_error_mm": soil_error,
            "annual_boundary_lake_error_equivalent_mm": lake_error,
            "annual_boundary_lake_level_error_m": level_error,
            "parameters": asdict(config), "source_plan_identity_sha256": plan.get("identity_sha256")})
    soil, volumes, monthly, soils, lake_volumes, steps, inventories = _year(
        height, owner, domains, lakes, area, climate, config, soil, volumes, retain=True)
    annual_evaluations += 1
    previous_soils, previous_volumes = np.array(soils), np.array(lake_volumes)
    trajectory_checks = []
    # Small annual endpoint drift can still cross a fine wet/dry threshold in
    # midyear. Keep advancing actual years until the complete trajectories and
    # their endpoints agree, consuming the original annual-map work budget.
    while annual_evaluations < config.max_years:
        initial_soil, initial_volumes = soil.copy(), volumes.copy()
        soil, volumes, monthly, soils, lake_volumes, steps, inventories = _year(
            height, owner, domains, lakes, area, climate, config, soil, volumes, retain=True)
        annual_evaluations += 1
        period_soil_error = float(np.max(np.abs(np.array(soils) - previous_soils)))
        period_level_error = max((max(abs(lake.level(a[c]) - lake.level(b[c]))
                                     for a, b in zip(lake_volumes, previous_volumes))
                                  for c, lake in lakes.items()), default=0.0)
        soil_error = float(np.max(np.abs(soil - initial_soil)))
        lake_error = float(np.max(np.abs(volumes - initial_volumes) / domain_areas * 1000))
        level_error = max((abs(lake.level(volumes[c]) - lake.level(initial_volumes[c]))
                           for c, lake in lakes.items()), default=0.0)
        trajectory_checks.append({"annual_map_evaluations": annual_evaluations,
            "successive_year_soil_max_error_mm": period_soil_error,
            "successive_year_level_max_error_m": period_level_error,
            "annual_boundary_soil_error_mm": soil_error,
            "annual_boundary_lake_error_equivalent_mm": lake_error,
            "annual_boundary_lake_level_error_m": level_error})
        if (max(period_soil_error, soil_error, lake_error) <= config.convergence_depth_mm
                and max(period_level_error, level_error) <= config.convergence_lake_level_m):
            break
        previous_soils, previous_volumes = np.array(soils), np.array(lake_volumes)
    else:
        reason = "successive annual seasonal trajectories did not converge within max_years"
        raise SeasonalBalanceError(reason, {"status": "failed", "reason": reason,
            "algorithm": plan.get("seasonal_hybrid", {}).get("algorithm", ALGORITHM),
            "source_plan_identity_sha256": plan.get("identity_sha256"), "parameters": asdict(config),
            **(trajectory_checks[-1] if trajectory_checks else {"annual_map_evaluations": annual_evaluations}),
            "trajectory_checks": trajectory_checks, "shooting_iterations": shooting_iterations,
            "shooting_trials": shooting_trials})
    levels = np.full((13, len(domains)), np.nan)
    for column, lake in lakes.items():
        levels[:, column] = [lake.level(v[column]) for v in lake_volumes]
    result = {"metadata": {"algorithm": plan.get("seasonal_hybrid", {}).get("algorithm", ALGORITHM),
                           "periodic_solver_algorithm": PERIODIC_SOLVER,
                           "water_step_algorithm": WATER_STEP_ALGORITHM,
                           "shore_event_schema": SHORE_EVENT_SCHEMA,
                           "status": "converged", "parameters": asdict(config),
                           "spinup_years": year, "annual_map_evaluations": annual_evaluations,
                           "trajectory_verification_years": annual_evaluations - evaluations - year,
                           "trajectory_checks": trajectory_checks,
                           "shooting_iterations": shooting_iterations,
                           "shooting_trials": shooting_trials,
                           "shooting_bracket": "lower positive storage drift; upper negative drift or spill failure; spill alone is not a root",
                           "domain_ids": [d["domain_id"] for d in domains],
                           "model": "capacity soil bucket; instantaneous terminal routing; dynamic raster lake area; fixed bed; submerged soil retained and frozen; no groundwater leakage",
                           "climate_model": "metric_noise_forcing.sample_climate; temperature-index planning PET",
                           "lake_connectivity": "coarse D8 matching frozen drainage; not certified fine face connectivity",
                           "soil_cycle_error_mm": float(np.max(np.abs(soils[-1] - soils[0]))),
                           "lake_cycle_error_equivalent_mm": float(np.max(np.abs(lake_volumes[-1] - lake_volumes[0]) / domain_areas * 1000)),
                           "successive_year_soil_max_error_mm": period_soil_error,
                           "successive_year_level_max_error_m": period_level_error},
              "climate": {key: np.asarray(value).copy() for key, value in climate.items()},
              "monthly": monthly, "soil_mm": np.array(soils), "lake_volume_m3": np.array(lake_volumes),
              "lake_level_m": levels, "step_inventory_m3": np.array(inventories),
              "previous_year_soil_mm": previous_soils, "previous_year_lake_volume_m3": previous_volumes,
              "steps": {key: np.array([step[key] for step in steps]) for key in LEDGER_KEYS},
              "shore_events": [step.get("shore_events", []) for step in steps],
              "lake_geometry": {str(domains[c]["domain_id"]): {"bed_elevations_m": lake.beds.copy(),
                                "cell_area_m2": lake.cell_area_m2, "spill_m": lake.spill_m,
                                "capacity_m3": lake.capacity_m3,
                                **({"bed_areas_m2": lake.areas.copy()} if hasattr(lake, "areas") else {})}
                                for c, lake in lakes.items()}}
    if "seasonal_hybrid" in plan:
        result["metadata"]["seasonal_hybrid"] = plan["seasonal_hybrid"]
        result["metadata"]["lake_connectivity"] = "mixed coarse basin/fine column assumption; all-stage fine face connectivity unverified"
    validate_seasonal_water_balance(plan, result)
    return result


def validate_seasonal_water_balance(plan, result):
    """Cold arithmetic audit of saved step and monthly water inventories."""
    config = SeasonalConfig(**result["metadata"]["parameters"])
    height, owner, domains, lakes, area, climate = _inputs(plan, config, result["climate"])
    count = len(domains)
    steps = result["steps"]
    nsteps = int(MONTH_DAYS.sum()) * config.substeps_per_day
    if result["metadata"].get("algorithm") != plan.get("seasonal_hybrid", {}).get("algorithm", ALGORITHM):
        raise ValueError("unknown seasonal algorithm")
    if result["metadata"].get("periodic_solver_algorithm") not in (None, PERIODIC_SOLVER):
        raise ValueError("unknown seasonal periodic solver")
    if result["metadata"].get("water_step_algorithm") not in (None, WATER_STEP_ALGORITHM):
        raise ValueError("unknown seasonal water step")
    event_schema = result["metadata"].get("shore_event_schema")
    if event_schema not in (None, SHORE_EVENT_SCHEMA):
        raise ValueError("unknown shoreline event record schema")
    if result["metadata"].get("water_step_algorithm") == WATER_STEP_ALGORITHM:
        witnesses = result.get("shore_events")
        if not isinstance(witnesses, list) or len(witnesses) != nsteps:
            raise ValueError("missing seasonal shoreline event audit")
        for step_events in witnesses:
            for event in step_events:
                if event_schema == SHORE_EVENT_SCHEMA and event.get("domain_id") not in [domains[c]["domain_id"] for c in lakes]:
                    raise ValueError("shoreline event lacks its registered inland domain")
                if event.get("kind") not in ("stationary_real_shore", "real_bed_crossing"):
                    raise ValueError("unknown shoreline event")
                if not np.isfinite(event["level_m"]) or not 0 < event["dt_days"] <= 1 / config.substeps_per_day:
                    raise ValueError("invalid shoreline event time or level")
                if event["kind"] == "stationary_real_shore" and (not 0 <= event["wet_fraction"] <= 1 or event["tied_area_m2"] <= 0):
                    raise ValueError("invalid stationary shoreline mixture")
    if result["metadata"].get("seasonal_hybrid") != plan.get("seasonal_hybrid"):
        raise ValueError("seasonal hybrid provenance mismatch")
    for name, shape in (("soil_mm", (13,) + height.shape), ("lake_volume_m3", (13, count)),
                        ("previous_year_soil_mm", (13,) + height.shape), ("previous_year_lake_volume_m3", (13, count)),
                        ("lake_level_m", (13, count)), ("step_inventory_m3", (nsteps + 1, count))):
        value = np.asarray(result[name])
        if value.shape != shape or (name != "lake_level_m" and not np.isfinite(value).all()):
            raise ValueError(f"invalid saved seasonal state {name}")
    for key in LEDGER_KEYS:
        values = np.asarray(steps[key])
        if values.shape != (nsteps, count) or not np.isfinite(values).all():
            raise ValueError("invalid saved seasonal ledger")
        if key not in ("soil_change_m3", "lake_change_m3") and np.any(values < 0):
            raise ValueError("negative seasonal flux")
    rain = steps["land_rain_m3"] + steps["lake_rain_m3"]
    losses = steps["land_et_m3"] + steps["lake_evaporation_m3"] + steps["coastal_outflow_m3"]
    delta = steps["soil_change_m3"] + steps["lake_change_m3"]
    tolerance = max(1e-7, float(rain.max()) * 1e-9)
    if not np.allclose(rain - losses, delta, rtol=1e-9, atol=tolerance):
        raise ValueError("step seasonal water budget mismatch")
    if not np.allclose(steps["land_rain_m3"] - steps["land_et_m3"] - steps["runoff_to_terminal_m3"],
                       steps["soil_change_m3"], rtol=1e-9, atol=tolerance):
        raise ValueError("soil runoff ledger mismatch")
    for column in range(count):
        if column in lakes:
            expected = steps["runoff_to_terminal_m3"][:, column] + steps["lake_rain_m3"][:, column] - steps["lake_evaporation_m3"][:, column]
            if np.any(steps["coastal_outflow_m3"][:, column] != 0) or not np.allclose(expected, steps["lake_change_m3"][:, column], rtol=1e-9, atol=tolerance):
                raise ValueError("inland terminal ledger mismatch")
        elif (np.any(result["lake_volume_m3"][:, column] != 0) or
              any(np.any(steps[key][:, column] != 0) for key in ("lake_rain_m3", "lake_evaporation_m3", "lake_change_m3")) or
              not np.allclose(steps["coastal_outflow_m3"][:, column], steps["runoff_to_terminal_m3"][:, column], rtol=1e-9, atol=tolerance)):
            raise ValueError("coastal terminal ledger mismatch")
    if not np.allclose(np.diff(result["step_inventory_m3"], axis=0), delta, rtol=1e-9, atol=tolerance):
        raise ValueError("step inventory mismatch")
    offset = 0
    for month, days in enumerate(MONTH_DAYS):
        end = offset + int(days) * config.substeps_per_day
        for key in LEDGER_KEYS:
            if not np.allclose(steps[key][offset:end].sum(axis=0), result["monthly"][key][month], rtol=1e-9, atol=tolerance):
                raise ValueError("monthly aggregation mismatch")
        for column, domain in enumerate(domains):
            mask = owner == domain["domain_id"]
            expected_rain = _area_sum(climate["precipitation_mm"][month], mask, area) / 1000
            if not np.isclose(rain[offset:end, column].sum(), expected_rain, rtol=1e-9, atol=tolerance):
                raise ValueError("rain partition mismatch: lake rain counted twice or omitted")
            soil_delta = _area_sum(result["soil_mm"][month + 1] - result["soil_mm"][month], mask, area) / 1000
            lake_delta = result["lake_volume_m3"][month + 1, column] - result["lake_volume_m3"][month, column]
            for boundary, state_index in ((offset, month), (end, month + 1)):
                inventory = (_area_sum(result["soil_mm"][state_index], mask, area) / 1000
                             + result["lake_volume_m3"][state_index, column])
                if not np.isclose(result["step_inventory_m3"][boundary, column], inventory, rtol=1e-9, atol=tolerance):
                    raise ValueError("step inventory does not match monthly state")
            if not np.isclose(soil_delta, steps["soil_change_m3"][offset:end, column].sum(), rtol=1e-9, atol=tolerance):
                raise ValueError("monthly soil inventory mismatch")
            if not np.isclose(lake_delta, steps["lake_change_m3"][offset:end, column].sum(), rtol=1e-9, atol=tolerance):
                raise ValueError("monthly lake inventory mismatch")
        offset = end
    soils = result["soil_mm"]
    volumes = result["lake_volume_m3"]
    if not np.isfinite(soils).all() or np.any(soils < 0) or np.any(soils > config.soil_capacity_mm + 1e-9):
        raise ValueError("invalid soil state")
    domain_areas = np.array([area[owner == d["domain_id"]].sum() for d in domains])
    if np.max(np.abs(soils[-1] - soils[0])) > config.convergence_depth_mm or np.max(np.abs(volumes[-1] - volumes[0]) / domain_areas * 1000) > config.convergence_depth_mm:
        raise ValueError("saved annual full state is not cyclic")
    if np.max(np.abs(soils - result["previous_year_soil_mm"])) > config.convergence_depth_mm:
        raise ValueError("successive annual soil trajectories differ")
    for column, lake in lakes.items():
        saved_geometry = result["lake_geometry"][str(domains[column]["domain_id"])]
        if (not np.array_equal(saved_geometry["bed_elevations_m"], lake.beds)
                or saved_geometry["capacity_m3"] != lake.capacity_m3
                or saved_geometry["spill_m"] != lake.spill_m
                or saved_geometry["cell_area_m2"] != lake.cell_area_m2
                or (hasattr(lake, "areas") and not np.array_equal(saved_geometry.get("bed_areas_m2"), lake.areas))):
            raise ValueError("saved lake geometry differs from current source geometry")
        if not np.isfinite(result["lake_level_m"][:, column]).all():
            raise ValueError("nonfinite lake level")
        if abs(result["lake_level_m"][-1, column] - result["lake_level_m"][0, column]) > config.convergence_lake_level_m:
            raise ValueError("annual lake level has not converged")
        if np.any(volumes[:, column] < 0) or np.any(volumes[:, column] >= lake.capacity_m3):
            raise ValueError("lake storage crosses uncertified spill")
        for volume, level in zip(volumes[:, column], result["lake_level_m"][:, column]):
            if not np.isclose(lake.volume(level), volume, rtol=1e-9, atol=tolerance):
                raise ValueError("lake level/bed/volume mismatch")
        previous = result["previous_year_lake_volume_m3"][:, column]
        if np.any(previous < 0) or np.any(previous >= lake.capacity_m3):
            raise ValueError("invalid previous annual lake storage")
        if max(abs(lake.level(a) - lake.level(b)) for a, b in zip(volumes[:, column], previous)) > config.convergence_lake_level_m:
            raise ValueError("successive annual lake level trajectories differ")
    return {"status": "verified", "max_step_residual_m3": float(np.max(np.abs(rain - losses - delta)))}


def save_seasonal_water_balance(plan, result, path):
    """Publish only a cold-audited periodic product; failure reports stay separate."""
    validate_seasonal_water_balance(plan, result)
    payload = {key: result[key] for key in ("soil_mm", "lake_volume_m3", "lake_level_m", "step_inventory_m3",
               "previous_year_soil_mm", "previous_year_lake_volume_m3")}
    metadata = dict(result["metadata"])
    if "shore_events" in result:
        metadata["shore_events"] = result["shore_events"]
    metadata["source_plan_identity_sha256"] = plan.get("identity_sha256")
    metadata["lake_geometry"] = {key: {name: value for name, value in geometry.items() if name not in ("bed_elevations_m", "bed_areas_m2")}
                                 for key, geometry in result["lake_geometry"].items()}
    payload["metadata_json"] = np.array(json.dumps(metadata, allow_nan=False))
    for group in ("climate", "monthly", "steps"):
        for key, value in result[group].items():
            payload[group + "__" + key] = value
    for key, geometry in result["lake_geometry"].items():
        payload["lake_beds__" + key] = geometry["bed_elevations_m"]
        if "bed_areas_m2" in geometry:
            payload["lake_areas__" + key] = geometry["bed_areas_m2"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("seasonal products are immutable; use a new output path")
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, **payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and refuses a concurrent existing path.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_seasonal_water_balance(plan, path):
    """Read saved accounts; new event physics also replays the pinned final year."""
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"]))
        if metadata.pop("source_plan_identity_sha256", None) != plan.get("identity_sha256"):
            raise ValueError("seasonal parent plan identity mismatch")
        geometry = metadata.pop("lake_geometry")
        result = {"metadata": metadata, "lake_geometry": geometry, "climate": {}, "monthly": {}, "steps": {}}
        if "shore_events" in metadata:
            result["shore_events"] = metadata.pop("shore_events")
        for key in archive.files:
            if key == "metadata_json":
                continue
            if "__" not in key:
                result[key] = archive[key].copy()
                continue
            group, name = key.split("__", 1)
            if group == "lake_beds":
                result["lake_geometry"][name]["bed_elevations_m"] = archive[key].copy()
            elif group == "lake_areas":
                result["lake_geometry"][name]["bed_areas_m2"] = archive[key].copy()
            elif group in ("climate", "monthly", "steps"):
                result[group][name] = archive[key].copy()
            else:
                raise ValueError("unknown seasonal archive array")
    validate_seasonal_water_balance(plan, result)
    if result["metadata"].get("water_step_algorithm") == WATER_STEP_ALGORITHM:
        config = SeasonalConfig(**result["metadata"]["parameters"])
        inputs = _inputs(plan, config, result["climate"])
        replay = _year(*inputs[:5], inputs[5], config, result["soil_mm"][0].copy(),
                       result["lake_volume_m3"][0].copy(), retain=True)
        for name, actual in (("soil_mm", replay[3]), ("lake_volume_m3", replay[4]),
                             ("step_inventory_m3", replay[6])):
            if not np.allclose(result[name], actual, rtol=0, atol=1e-7):
                raise ValueError("saved shoreline physics differs from replay: " + name)
        for key in LEDGER_KEYS:
            actual = np.array([step[key] for step in replay[5]])
            if not np.allclose(result["steps"][key], actual, rtol=0, atol=1e-7):
                raise ValueError("saved shoreline flux differs from replay: " + key)
        replay_events = [step.get("shore_events", []) for step in replay[5]]
        if result["metadata"].get("shore_event_schema") is None:
            if len(inputs[3]) > 1:
                raise ValueError("legacy multi-lake shoreline events cannot verify per-step attribution")
            replay_events = [[{key: value for key, value in event.items() if key != "domain_id"}
                              for event in step] for step in replay_events]
        if result["shore_events"] != replay_events:
            raise ValueError("saved shoreline events differ from physical replay")
    return result
