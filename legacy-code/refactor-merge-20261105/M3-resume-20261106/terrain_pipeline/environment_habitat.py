"""Functional-group carrying capacity and actual cost-limited dispersal.

Population moves by neighbor transfers on the shared irregular control graph.
Costs consume vegetation, water, temperature, relief and disturbance, with
impassable invalid/protected/ocean support. No species or food web is implied.
"""
import heapq

import numpy as np

from .environment_ecology_contract import field, frame, metadata, stocks
from .environment_context import prepare_mesh
from terrain_pipeline.drainage import valid_edge_mask as valid_edge_mask

ALGORITHM = "environment-functional-habitat-cost-dispersal-v1"
PARAMETERS = {"capacity_individuals_m2": .001, "growth_timescale_s": 180. * 86400.,
              "migration_timescale_s": 7. * 86400., "max_cost_m": 3000.,
              "minimum_suitability": .05}


def initialize_habitat(context, *, population_individuals=0.):
    shape, _, masks = frame(context, 0.)
    population = field({"v": population_individuals}, "v", shape)
    population *= masks["valid_mask"] & ~masks["ocean_mask"] & ~masks["protected_mask"]
    return {"population_individuals": population, "occupancy_s": np.zeros(shape)}


def advance_habitat(state, forcing, context, dt_s):
    shape, area, masks = frame(context, dt_s)
    pools = stocks(state, ("population_individuals", "occupancy_s"), shape)
    population = pools["population_individuals"]
    occupancy = pools["occupancy_s"]
    active = masks["valid_mask"] & ~masks["ocean_mask"] & ~masks["protected_mask"]
    cover = field(forcing, "vegetation_cover_fraction", shape)
    water = field(forcing, "water_available_fraction", shape)
    disturbance = field(forcing, "disturbance_fraction", shape)
    if any(np.any(v > 1.) for v in (cover, water, disturbance)):
        raise ValueError("habitat cover, water and disturbance fractions must be <=1")
    temperature = field(forcing, "water_temperature_c", shape, 15., nonnegative=False)
    thermal = np.clip(1. - np.abs(temperature - 15.) / 25., 0., 1.)
    suitability = cover * np.sqrt(water) * thermal * (1. - disturbance) * active
    capacity = suitability * area * PARAMETERS["capacity_individuals_m2"]
    passable = (suitability >= PARAMETERS["minimum_suitability"]) & active
    mesh = prepare_mesh(context, shape, edge_order="stable")
    edges_valid = valid_edge_mask(mesh, active)
    initial = population.copy()
    # Dijkstra witness: reachable habitat from currently occupied accounts.
    distances = np.full(population.size, np.inf)
    queue = []
    for node in np.flatnonzero((population > 0.) & active):
        distances[node] = 0.
        heapq.heappush(queue, (0., int(node)))
    flat_suitable = suitability.ravel()
    height = np.asarray(context["height_m"]).ravel()
    pass_flat = passable.ravel()
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances[node]:
            continue
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            target = int(mesh.indices[edge])
            if not edges_valid[edge] or not pass_flat[target]:
                continue
            length = mesh.edge_length_m[edge]
            cost = length * (1. + abs(height[node] - height[target]) / length) / max(flat_suitable[target], .05)
            candidate = distance + cost
            if candidate <= PARAMETERS["max_cost_m"] and candidate < distances[target]:
                distances[target] = candidate
                heapq.heappush(queue, (candidate, target))
    reachable = np.isfinite(distances).reshape(shape)
    migration = np.zeros(population.size)
    gross = 0.
    # Donor and target capacities share a single cap; migration is conservative.
    remaining = np.maximum(capacity.ravel() - population.ravel(), 0.)
    fraction = -np.expm1(-dt_s / PARAMETERS["migration_timescale_s"])
    for donor in np.flatnonzero((population > 0.) & active):
        section = slice(mesh.indptr[donor], mesh.indptr[donor + 1])
        targets = mesh.indices[section][edges_valid[section]]
        lengths = mesh.edge_length_m[section][edges_valid[section]]
        costs = lengths * (1. + np.abs(height[donor] - height[targets]) / lengths) / np.maximum(flat_suitable[targets], .05)
        allowed = pass_flat[targets] & reachable.ravel()[targets] & (costs <= PARAMETERS["max_cost_m"])
        targets = targets[allowed]
        costs = costs[allowed]
        if targets.size == 0:
            continue
        weights = remaining[targets] * flat_suitable[targets] / np.maximum(costs, 1.e-12)
        if weights.sum() <= 0.:
            continue
        proposed = population.ravel()[donor] * fraction * weights / weights.sum()
        moved = np.minimum(proposed, remaining[targets])
        migration[donor] -= moved.sum()
        np.add.at(migration, targets, moved)
        remaining[targets] -= moved
        gross += float(moved.sum())
    migrated = population + migration.reshape(shape)
    # Exact positive logistic step below capacity; bounded mortality above it.
    growth_fraction = -np.expm1(-dt_s / PARAMETERS["growth_timescale_s"])
    birth = migrated * np.clip(1. - np.divide(migrated, capacity, out=np.ones(shape), where=capacity > 0.), 0., 1.) * growth_fraction * active
    birth = np.minimum(birth, np.maximum(capacity - migrated, 0.))
    death = np.maximum(migrated - capacity, 0.) * growth_fraction * active
    final = migrated + birth - death
    occupied_time = np.where(active & (final > 1.e-12), occupancy + dt_s, occupancy)
    ledger = {"initial_population": float(initial.sum()), "births_individuals": float(birth.sum()),
              "deaths_individuals": float(death.sum()), "gross_migration_individuals": gross,
              "final_population": float(final.sum())}
    ledger["population_residual"] = float((initial + birth - death - final).sum())
    cost = np.where(reachable, distances.reshape(shape), -1.)
    return {"state": {"population_individuals": final, "occupancy_s": occupied_time},
            "fluxes": {"migration_net_individuals": migration.reshape(shape), "births_individuals": birth,
                       "deaths_individuals": death, "suitability": suitability, "carrying_capacity_individuals": capacity,
                       "reachable_mask": reachable, "corridor_cost_m": cost}, "ledger": ledger,
            "metadata": metadata(ALGORITHM, context, dt_s,
            ["declared terrestrial riparian functional group, fractional expected individuals, no species food web",
             "irregular graph dispersal within finite patch; no cross-patch migration certification",
             "max_cost_m bounds each actual donor movement; global cost field is a multi-source corridor witness",
             "protected and unknown accounts block migration"], PARAMETERS.copy())}


initialize = initialize_habitat
step = advance_habitat
