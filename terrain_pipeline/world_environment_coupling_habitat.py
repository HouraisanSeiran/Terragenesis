"""Compiled global adapter of the functional habitat core's canonical commits.

No independent patches: multi-source costs and sequential global-ID donor
transactions share one receiver-capacity account across the entire graph.
"""
import heapq
import numpy as np
from numba import njit
from terrain_pipeline.environment_processes import HABITAT_PARAMETERS
from terrain_pipeline.drainage import valid_edge_mask


@njit(cache=True)
def _advance(population,occupancy,height,suitable,active,area,indptr,indices,lengths,edge_valid,dt):
    size=population.size
    capacity=suitable*area*.001
    passable=(suitable>=.05)&active
    distances=np.full(size,np.inf)
    queue=[(0.,-1)]
    queue.pop()
    for node in range(size):
        if population[node]>0 and active[node]:
            distances[node]=0.
            heapq.heappush(queue,(0.,node))
    while queue:
        distance,node=heapq.heappop(queue)
        if distance!=distances[node]:
            continue
        for edge in range(indptr[node],indptr[node+1]):
            target=indices[edge]
            if not edge_valid[edge] or not active[target] or not passable[target]:
                continue
            cost=(lengths[edge]+abs(height[node]-height[target]))/max(suitable[target],.05)
            candidate=distance+cost
            if candidate<=3000. and candidate<distances[target]:
                distances[target]=candidate
                heapq.heappush(queue,(candidate,np.int64(target)))
    migration=np.zeros(size)
    remaining=np.maximum(capacity-population,0.)
    fraction=-np.expm1(-dt/(7*86400.))
    gross=0.
    for donor in range(size):
        if population[donor]<=0 or not active[donor]:
            continue
        weight_total=0.
        for edge in range(indptr[donor],indptr[donor+1]):
            target=indices[edge]
            cost=(lengths[edge]+abs(height[donor]-height[target]))/max(suitable[target],.05)
            if edge_valid[edge] and active[target] and passable[target] and np.isfinite(distances[target]) and cost<=3000.:
                weight_total+=remaining[target]*suitable[target]/max(cost,1e-12)
        if weight_total<=0:
            continue
        # Compute all proposals from the same pre-donor target capacities.
        moved_total=0.
        for edge in range(indptr[donor],indptr[donor+1]):
            target=indices[edge]
            cost=(lengths[edge]+abs(height[donor]-height[target]))/max(suitable[target],.05)
            if edge_valid[edge] and active[target] and passable[target] and np.isfinite(distances[target]) and cost<=3000.:
                weight=remaining[target]*suitable[target]/max(cost,1e-12)
                moved=min(population[donor]*fraction*weight/weight_total,remaining[target])
                migration[target]+=moved
                remaining[target]-=moved
                moved_total+=moved
        migration[donor]-=moved_total
        gross+=moved_total
    migrated=population+migration
    birth=np.zeros(size)
    death=np.zeros(size)
    fraction=-np.expm1(-dt/(180*86400.))
    for node in range(size):
        if active[node]:
            birth[node]=min(migrated[node]*max(0.,min(1.,1-migrated[node]/capacity[node] if capacity[node]>0 else 0.))*fraction,max(capacity[node]-migrated[node],0.))
            death[node]=max(migrated[node]-capacity[node],0.)*fraction
    final=migrated+birth-death
    occupied=np.where(active&(final>1e-12),occupancy+dt,occupancy)
    return final,occupied,migration,birth,death,distances,capacity,gross


def advance_global_habitat(state,forcing,context,mesh,dt_s):
    shape=context['height_m'].shape
    active=context['valid_mask']&~context['ocean_mask']&~context['protected_mask']
    cover=np.asarray(forcing['vegetation_cover_fraction'])
    water=np.asarray(forcing['water_available_fraction'])
    disturbance=np.asarray(forcing['disturbance_fraction'])
    thermal=np.clip(1-np.abs(forcing['water_temperature_c']-15)/25,0.,1.)
    suitable=cover*np.sqrt(water)*thermal*(1-disturbance)*active
    population=np.asarray(state['population_individuals'])
    edge_valid=context.get('_habitat_edges_valid')
    if edge_valid is None:
        edge_valid=valid_edge_mask(mesh,active)
    result=_advance(population.ravel(),state['occupancy_s'].ravel(),context['height_m'].ravel(),
        suitable.ravel(),active.ravel(),context['spacing_m']**2,mesh.indptr,mesh.indices,mesh.edge_length_m,edge_valid,dt_s)
    final,occupied,migration,birth,death,distance,capacity,gross=result
    ledger=dict(initial_population=float(population.sum()),births_individuals=float(birth.sum()),
        deaths_individuals=float(death.sum()),gross_migration_individuals=float(gross),final_population=float(final.sum()),
        population_residual=float((population.ravel()+birth-death-final).sum()))
    return dict(state=dict(population_individuals=final.reshape(shape),occupancy_s=occupied.reshape(shape)),
        fluxes=dict(migration_net_individuals=migration.reshape(shape),births_individuals=birth.reshape(shape),
            deaths_individuals=death.reshape(shape),suitability=suitable,carrying_capacity_individuals=capacity.reshape(shape),
            reachable_mask=np.isfinite(distance).reshape(shape),corridor_cost_m=np.where(np.isfinite(distance),distance,-1).reshape(shape)),
        ledger=ledger,metadata=dict(algorithm='global-canonical-habitat-adapter-v1',parameters=HABITAT_PARAMETERS.copy()))
