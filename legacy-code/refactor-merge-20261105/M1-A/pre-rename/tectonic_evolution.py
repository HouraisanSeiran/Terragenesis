"""Original CPU kinematic crust prototype; periodic plane, not geodynamics.

Inspired by platec/tectonics.js process separation; no upstream code copied.
Fields are [plate,z,x], equivalent metres per full cell; time is offline steps.
Fractional donor-cell transport conserves volume but diffuses interfaces. No
stress, mantle flow, physical ages, calibrated tectonic rates or ocean topology
are inferred. Surface elevation is a declared simple Airy buoyancy proxy.
"""

from dataclasses import asdict, dataclass
import hashlib
from copy import deepcopy

import numpy as np

from terrain_pipeline.tectonic_formation import form_plates, validate_formation


ALGORITHM_VERSION = "kinematic-crust-4"
_BUDGET_RELATIVE_TOLERANCE = 1e-12
_BUDGET_ABSOLUTE_TOLERANCE_M3 = 1e-12


@dataclass(frozen=True)
class TectonicConfig:
    shape: tuple = (128, 128)
    cell_size_m: float = 10000.0
    origin_x_m: float = 0.0
    origin_z_m: float = 0.0
    plate_count: int = 8
    microcells_per_plate: int = 64
    min_plate_cells: int = 4
    world_seed: int = 20261020
    steps: int = 40
    time_step: float = 1.0
    max_speed_m_per_step: float = 2000.0
    continental_thickness_m: float = 35000.0
    oceanic_thickness_m: float = 7000.0
    subduction_fraction: float = 1.0
    rift_fraction: float = 1.0


@dataclass
class CrustState:
    plate_coverage: np.ndarray
    continental_m: np.ndarray
    oceanic_m: np.ndarray
    plate_seeds_m: np.ndarray
    velocities_m_per_step: np.ndarray
    step: int = 0
    formation: dict | None = None


@dataclass
class EvolutionResult:
    initial: CrustState
    final: CrustState
    initial_elevation_m: np.ndarray
    elevation_m: np.ndarray
    plate_id: np.ndarray
    continental_fraction: np.ndarray
    crust_thickness_m: np.ndarray
    budgets: list
    metadata: dict


def _integer(value, minimum):
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool) and value >= minimum


def _validate_config(config):
    if len(config.shape) != 2 or not all(_integer(n, 2) for n in config.shape):
        raise ValueError("shape must contain two integers >= 2")
    if not _integer(config.plate_count, 1) or config.plate_count > np.prod(config.shape):
        raise ValueError("plate_count outside grid capacity")
    validate_formation(config)
    if not _integer(config.steps, 0) or not _integer(config.world_seed, 0):
        raise ValueError("steps and world_seed must be nonnegative integers")
    for name in ("cell_size_m", "time_step", "continental_thickness_m", "oceanic_thickness_m"):
        value = getattr(config, name)
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("origin_x_m", "origin_z_m", "max_speed_m_per_step", "subduction_fraction", "rift_fraction"):
        if not np.isfinite(getattr(config, name)):
            raise ValueError(f"{name} must be finite")
    if config.max_speed_m_per_step < 0:
        raise ValueError("max_speed_m_per_step must be nonnegative")
    if any(not 0 <= value <= 1 for value in (config.subduction_fraction, config.rift_fraction)):
        raise ValueError("mechanism fractions must lie in [0,1]")
    with np.errstate(over="ignore", invalid="ignore"):
        area = np.float64(config.cell_size_m) ** 2
        extent = np.array(config.shape, dtype=float) * config.cell_size_m
    if not np.isfinite(area) or not np.isfinite(extent).all():
        raise ValueError("nonfinite domain dimensions or cell area")


def _purpose_seed(world_seed, purpose):
    digest = hashlib.sha256(f"{world_seed}:tectonic:{purpose}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


def _coordinates(config):
    z, x = np.indices(config.shape, dtype=float)
    return (x + 0.5) * config.cell_size_m, (z + 0.5) * config.cell_size_m


def _periodic_distance(delta, length):
    return (delta + length / 2) % length - length / 2


def initialize(config):
    """Return connected aggregated microcells and independent continental embryos."""
    _validate_config(config)
    width = config.shape[1] * config.cell_size_m
    height = config.shape[0] * config.cell_size_m
    ids, seeds, formation = form_plates(config, _purpose_seed(config.world_seed, "plates"))
    x, z = _coordinates(config)
    coverage = np.arange(config.plate_count)[:, None, None] == ids
    rng = np.random.default_rng(_purpose_seed(config.world_seed, "crust"))
    continent = np.zeros(config.shape)
    for _ in range(max(2, config.plate_count // 2)):
        cx, cz = rng.random(2) * (width, height)
        radius_x, radius_z = rng.uniform(0.12, 0.26, 2) * (width, height)
        radius = (_periodic_distance(x - cx, width) / radius_x) ** 2
        radius += (_periodic_distance(z - cz, height) / radius_z) ** 2
        continent = np.maximum(continent, np.clip((1.15 - radius) / 0.3, 0, 1))
    rng = np.random.default_rng(_purpose_seed(config.world_seed, "velocity"))
    angle = rng.uniform(0, 2 * np.pi, config.plate_count)
    speed = rng.uniform(0.4, 1, config.plate_count) * config.max_speed_m_per_step
    velocities = np.column_stack((np.cos(angle) * speed, np.sin(angle) * speed))
    state = CrustState(coverage.astype(float), coverage * continent * config.continental_thickness_m,
                       coverage * (1 - continent) * config.oceanic_thickness_m,
                       seeds + (config.origin_x_m, config.origin_z_m), velocities, formation=formation)
    _validate_state(config, state)
    return state


def _validate_state(config, state):
    expected = (config.plate_count, *config.shape)
    for name in ("plate_coverage", "continental_m", "oceanic_m"):
        field = np.asarray(getattr(state, name))
        if field.shape != expected or not np.isfinite(field).all() or (field < 0).any():
            raise ValueError(f"invalid {name}: expected finite nonnegative {expected}")
    if not np.allclose(np.sum(state.plate_coverage, axis=0), 1, rtol=0, atol=1e-12):
        raise ValueError("plate coverage must partition unity")
    empty = np.asarray(state.plate_coverage) == 0
    if (np.asarray(state.continental_m)[empty] > 0).any() or (np.asarray(state.oceanic_m)[empty] > 0).any():
        raise ValueError("material cannot exist on an absent plate")
    for name in ("plate_seeds_m", "velocities_m_per_step"):
        values = np.asarray(getattr(state, name))
        if values.shape != (config.plate_count, 2) or not np.isfinite(values).all():
            raise ValueError(f"invalid {name}")
    seeds = np.asarray(state.plate_seeds_m) - (config.origin_x_m, config.origin_z_m)
    extent = np.array(config.shape[::-1]) * config.cell_size_m
    if (seeds < 0).any() or (seeds >= extent).any():
        raise ValueError("plate seeds outside periodic domain")
    _displacement(config, state)
    if not _integer(state.step, 0):
        raise ValueError("invalid offline step index")
    with np.errstate(over="ignore", invalid="ignore"):
        volume = (np.sum(state.continental_m) + np.sum(state.oceanic_m)) * config.cell_size_m ** 2
    if not np.isfinite(volume):
        raise ValueError("nonfinite material volume")


def _copy_state(state):
    return CrustState(*(np.array(getattr(state, name), dtype=float, copy=True) for name in
                        ("plate_coverage", "continental_m", "oceanic_m", "plate_seeds_m",
                         "velocities_m_per_step")), step=int(state.step), formation=deepcopy(state.formation))


def _displacement(config, state):
    # Validate the exact dimensionless values used by transport, with no slack.
    with np.errstate(over="ignore", invalid="ignore"):
        displacement = state.velocities_m_per_step * config.time_step / config.cell_size_m
        courant = np.abs(displacement).sum(axis=1)
    if not np.isfinite(courant).all() or (courant > 1).any():
        raise ValueError("CFL requires time_step*(abs(vx)+abs(vz))/cell_size_m <= 1")
    return displacement


def surface_fields(state):
    """Derive cell surface from current material, never from a boundary ridge."""
    continental = np.sum(state.continental_m, axis=0)
    oceanic = np.sum(state.oceanic_m, axis=0)
    thickness = continental + oceanic
    fraction = np.divide(continental, thickness, out=np.zeros_like(thickness), where=thickness > 0)
    density = fraction * 2800.0 + (1 - fraction) * 3000.0
    return {"elevation_m": continental * (1 - 2800 / 3300) + oceanic * (1 - 3000 / 3300) - 4500,
            "plate_id": np.argmax(state.plate_coverage, axis=0).astype(np.int32),
            "continental_fraction": fraction, "crust_thickness_m": thickness,
            "density_kg_m3": density}


def _advect(field, displacement):
    result = np.empty_like(field)
    for plate, (dx, dz) in enumerate(displacement):
        # Unsplit first-order donor cell: positive weights under the L1 CFL.
        source = field[plate]
        result[plate] = ((1 - (abs(dx) + abs(dz))) * source
                         + abs(dx) * np.roll(source, 1 if dx >= 0 else -1, axis=1)
                         + abs(dz) * np.roll(source, 1 if dz >= 0 else -1, axis=0))
    return result


def _boundaries(coverage, velocities):
    ids = coverage.argmax(axis=0)
    counts = {"convergent_faces": 0, "divergent_faces": 0, "transform_faces": 0}
    for axis, component in ((1, 0), (0, 1)):
        neighbor = np.roll(ids, -1, axis=axis)
        boundary = ids != neighbor
        normal = velocities[neighbor, component] - velocities[ids, component]
        tangent = velocities[neighbor, 1 - component] - velocities[ids, 1 - component]
        counts["convergent_faces"] += int(np.count_nonzero(boundary & (normal < -1e-10)))
        counts["divergent_faces"] += int(np.count_nonzero(boundary & (normal > 1e-10)))
        counts["transform_faces"] += int(np.count_nonzero(boundary & (abs(normal) <= 1e-10) & (abs(tangent) > 1e-10)))
    return counts


def _step(config, state):
    area = config.cell_size_m ** 2
    before_c = float(state.continental_m.sum() * area)
    before_o = float(state.oceanic_m.sum() * area)
    displacement = _displacement(config, state)
    coverage = _advect(state.plate_coverage, displacement)
    continental = _advect(state.continental_m, displacement)
    oceanic = _advect(state.oceanic_m, displacement)
    transport_c = float(continental.sum() * area - before_c)
    transport_o = float(oceanic.sum() * area - before_o)
    # Loss of squared concentration at fixed conserved volume measures mixing.
    diffusion = float(max(0, np.square(state.continental_m).sum() - np.square(continental).sum()) * area)
    oceanic_diffusion = float(max(0, np.square(state.oceanic_m).sum() - np.square(oceanic).sum()) * area)
    moved_fraction = np.abs(displacement).sum(axis=1)[:, None, None]
    moved_continental = float((state.continental_m * moved_fraction).sum() * area)
    moved_oceanic = float((state.oceanic_m * moved_fraction).sum() * area)
    removed = 0.0
    sutured = 0.0
    for first in range(config.plate_count):
        grad_z = (np.roll(coverage[first], -1, 0) - np.roll(coverage[first], 1, 0)) / 2
        grad_x = (np.roll(coverage[first], -1, 1) - np.roll(coverage[first], 1, 1)) / 2
        for second in range(first + 1, config.plate_count):
            relative = displacement[second] - displacement[first]
            convergence = relative[0] * grad_x + relative[1] * grad_z
            # -grad(coverage A) points from A to B, so this is approaching.
            overlap = np.minimum(coverage[first], coverage[second])
            overlap = np.where(convergence > 1e-14, overlap, 0)
            excess = np.maximum(coverage.sum(axis=0) - 1, 0)
            overlap = np.minimum(overlap, excess)
            # Ocean-rich side goes down. Equal composition ties use stable ID.
            ratio_first = oceanic[first] / np.maximum(continental[first] + oceanic[first], 1e-30)
            ratio_second = oceanic[second] / np.maximum(continental[second] + oceanic[second], 1e-30)
            down_first = ratio_first >= ratio_second
            for donor, receiver, selected in ((first, second, down_first), (second, first, ~down_first)):
                fraction = np.divide(overlap, coverage[donor], out=np.zeros(config.shape), where=coverage[donor] > 0)
                fraction *= selected
                subducted = oceanic[donor] * fraction * config.subduction_fraction
                oceanic[donor] -= subducted
                removed += float(subducted.sum() * area)
                # Continental accretion transfers ownership and retains all crust.
                joined = continental[donor] * fraction
                continental[donor] -= joined
                continental[receiver] += joined
                sutured += float(joined.sum() * area)
    total_coverage = coverage.sum(axis=0)
    gap = np.maximum(1 - total_coverage, 0)
    owner = coverage.argmax(axis=0)
    addition = gap * config.oceanic_thickness_m * config.rift_fraction
    for plate in range(config.plate_count):
        selected = owner == plate
        oceanic[plate] += addition * selected
        coverage[plate] += gap * selected
    coverage /= coverage.sum(axis=0)
    origin = np.array((config.origin_x_m, config.origin_z_m))
    extent = np.array(config.shape[::-1]) * config.cell_size_m
    seeds = (state.plate_seeds_m - origin + state.velocities_m_per_step * config.time_step) % extent + origin
    final = CrustState(coverage, continental, oceanic, seeds, state.velocities_m_per_step.copy(), state.step + 1, state.formation)
    final_c = float(continental.sum() * area)
    final_o = float(oceanic.sum() * area)
    added = float(addition.sum() * area)
    budget = {"step": final.step, "initial_continental_m3": before_c, "initial_oceanic_m3": before_o,
              "final_continental_m3": final_c, "final_oceanic_m3": final_o,
              "rift_oceanic_added_m3": added, "subducted_oceanic_m3": removed,
              "sutured_continental_m3": sutured,
              "advection_continental_residual_m3": transport_c,
              "advection_oceanic_residual_m3": transport_o,
              "advected_continental_m3": moved_continental,
              "advected_oceanic_m3": moved_oceanic,
              "continental_balance_residual_m3": final_c - before_c,
              "oceanic_balance_residual_m3": final_o - before_o - added + removed,
              "advection_continental_l2_loss_m4": diffusion,
              "advection_oceanic_l2_loss_m4": oceanic_diffusion,
              "max_coverage_overlap": float(np.maximum(total_coverage - 1, 0).max()),
              "gap_area_m2": float(gap.sum() * area)}
    budget.update(_boundaries(state.plate_coverage, state.velocities_m_per_step))
    return final, budget


def _validate_budget(config, before, after, budget):
    if not all(np.isfinite(value) for value in budget.values()):
        raise ValueError("nonfinite evolution budget")
    area = config.cell_size_m ** 2
    for material in ("continental", "oceanic"):
        initial = float(getattr(before, f"{material}_m").sum() * area)
        final = float(getattr(after, f"{material}_m").sum() * area)
        added = budget["rift_oceanic_added_m3"] if material == "oceanic" else 0.0
        removed = budget["subducted_oceanic_m3"] if material == "oceanic" else 0.0
        # Separate inventories: abundant continental crust cannot mask an
        # oceanic error. Fluxes set the oceanic scale even after depletion.
        scale = max(initial, final, added, removed)
        tolerance = max(_BUDGET_ABSOLUTE_TOLERANCE_M3,
                        _BUDGET_RELATIVE_TOLERANCE * scale)
        transport_tolerance = max(_BUDGET_ABSOLUTE_TOLERANCE_M3,
                                  _BUDGET_RELATIVE_TOLERANCE * initial)
        residuals = (final - initial - added + removed,
                     budget[f"{material}_balance_residual_m3"],
                     budget[f"initial_{material}_m3"] - initial,
                     budget[f"final_{material}_m3"] - final)
        if any(not np.isfinite(value) or abs(value) > tolerance for value in residuals):
            raise ValueError(f"step {after.step}: {material} material budget exceeded")
        if abs(budget[f"advection_{material}_residual_m3"]) > transport_tolerance:
            raise ValueError(f"step {after.step}: {material} advection budget exceeded")


def evolve(config, initial_state=None):
    """Prepare a complete isolated result; no caller arrays or files are changed."""
    _validate_config(config)
    supplied = initialize(config) if initial_state is None else initial_state
    _validate_state(config, supplied)
    initial = _copy_state(supplied)
    state = _copy_state(initial)
    budgets = []
    for _ in range(config.steps):
        next_state, budget = _step(config, state)
        _validate_state(config, next_state)
        _validate_budget(config, state, next_state, budget)
        state = next_state
        budgets.append(budget)
    fields = surface_fields(state)
    metadata = {"algorithm_version": ALGORITHM_VERSION, "config": asdict(config),
                "boundary": "periodic_plane", "array_order": "z,x", "axes": "X east, Z south",
                "velocity_unit": "m/offline-step", "time_unit": "uncalibrated offline-step",
                "seed_derivation": "SHA256(f'{world_seed}:tectonic:{purpose}'), first 8 bytes little-endian",
                "purpose_seeds": {name: _purpose_seed(config.world_seed, name) for name in ("plates", "crust", "velocity")},
                "formation": initial.formation,
                "initial_state_source": "generated" if initial_state is None else "injected",
                "status": "mechanism prototype / candidate; not TD coupled",
                "densities_kg_m3": {"mantle": 3300, "continental": 2800, "oceanic": 3000},
                "elevation_offset_m": -4500, "budget_unit": "m3",
                "numerical_error_relative_tolerance": _BUDGET_RELATIVE_TOLERANCE,
                "transport": "periodic unsplit donor-cell; L1 CFL <= 1; diffusive"}
    return EvolutionResult(initial, state, surface_fields(initial)["elevation_m"],
                           fields["elevation_m"], fields["plate_id"], fields["continental_fraction"],
                           fields["crust_thickness_m"], budgets, metadata)
