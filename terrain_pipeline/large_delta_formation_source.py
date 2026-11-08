"""Finite geological source scenario on a contracted native catchment graph."""
import json
import os
from pathlib import Path
import numpy as np
from numba import njit
from terrain_pipeline.new_world_game_hydrology import ROOT, IDENTITY
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment

OUT = Path(os.environ.get('TERRA_FORMATION_OUT', '.scratch/large-delta-20261101/source-formation-v1'))
MOUTH = 5879
DT = 30 * 86400 * int(os.environ.get('TERRA_FORMATION_ACCELERATION', '1000'))
BATCHES = 96

@njit
def assign_nodes(order, receiver, belongs, selected):
    assigned = np.full(len(receiver), -1, dtype=np.int32)
    for j in range(len(order)):
        i = order[j]
        if belongs[i]:
            if selected[i] >= 0:
                assigned[i] = selected[i]
            elif receiver[i] >= 0:
                assigned[i] = assigned[receiver[i]]
    return assigned

def aggregate(values, assignment, count):
    good = assignment >= 0
    return np.bincount(assignment[good], weights=values[good], minlength=count)

def run():
    OUT.mkdir(parents=True, exist_ok=True)
    load = lambda p: np.load(p, mmap_mode='r', allow_pickle=False)
    derived = ROOT / 'native-final-routing-v1/derived'
    nodes = load(derived/'mouth_source.npy'); mouth = int(nodes[MOUTH])
    watershed = load(derived/'watershed_id.npy'); belongs = np.asarray(watershed == watershed[mouth])
    terrain = ROOT/'terrain-v3'
    valid = load(terrain/'valid_mask.npy').ravel(); ocean = load(terrain/'ocean_mask.npy').ravel(); unknown = load(terrain/'unknown_mask.npy').ravel()
    land = belongs & valid & ~ocean & ~unknown
    order = load(ROOT/'native-final-routing-v1/routing/order.npy'); receiver = load(ROOT/'native-final-routing-v1/routing/receiver.npy')
    # Deterministic distributed graph samples, plus mouth. A node represents all
    # upstream native cells whose first selected downstream node is that node.
    ids = np.flatnonzero(belongs).astype(np.int64)
    hashed = (ids.astype(np.uint64) * np.uint64(11400714819323198485))
    chosen = ids[(hashed >> np.uint64(48)) < 35]
    chosen = np.unique(np.append(chosen, mouth))
    if len(chosen) > 2048:
        raise ValueError('reduction exceeded kernel limit')
    selected = np.full(len(receiver), -1, dtype=np.int32); selected[chosen] = np.arange(len(chosen),dtype=np.int32)
    assignment = assign_nodes(order, receiver, belongs, selected)
    if np.any(assignment[land] < 0):
        raise ValueError('unassigned local catchment')
    parent = np.full(len(chosen), -1, dtype=np.int64)
    for k, i in enumerate(chosen):
        if i != mouth:
            parent[k] = assignment[receiver[i]]
    if np.sum(parent < 0) != 1 or parent[assignment[mouth]] != -1:
        raise ValueError('invalid reduced outlet')
    n = len(chosen)
    local = load(ROOT/'native-event-v1/local_contribution_m3.npy')
    area = aggregate(land.astype(np.float64)*900, assignment, n)
    runoff = aggregate(local, assignment, n)/1296000
    # Downstream accumulation in saved flood order (reverse: headwaters first).
    q = runoff.copy()
    ranks = np.empty(len(receiver),dtype=np.int32); ranks[order] = np.arange(len(order), dtype=np.int32)
    for k in np.argsort(ranks[chosen])[::-1]:
        if parent[k] >= 0: q[parent[k]] += q[k]
    bed = load(terrain/'bed_m.npy').ravel(); elev=np.asarray(bed[chosen], dtype=np.float64)
    x = (chosen % 4096)*30-61440; z=(chosen//4096)*30-61440
    length=np.full(n, 300., dtype=np.float64)
    edge=parent>=0; length[edge]=np.maximum(30,np.hypot(x[edge]-x[parent[edge]],z[edge]-z[parent[edge]]))
    slope=np.full(n, .0001); slope[edge]=np.clip((elev[edge]-elev[parent[edge]])/length[edge],.0001,.5)
    # Existing v4 power-law geometry, extrapolated above its saved Q range.
    width=8.314*q**.45; depth=np.maximum(.05, .598*q**.28581553); width=np.maximum(.5,width)
    # Channel cross-section area is capped at its allocated catchment land area.
    channel_area=np.minimum(width*length, area*.5)
    width=np.maximum(channel_area/length, 1e-6)
    # Coarse 300 m point-sampled slope, for hillslope transfer, stored with mask.
    bed2=load(terrain/'bed_m.npy')[::10,::10].astype(np.float64)
    gz,gx=np.gradient(bed2,300.); coarse_slope=np.hypot(gx,gz)
    coarse_assign=assignment.reshape(4096,4096)[::10,::10]
    coarse_mask=land.reshape(4096,4096)[::10,::10]
    weighted=np.bincount(coarse_assign[coarse_mask], weights=coarse_slope[coarse_mask],minlength=n)
    counts=np.bincount(coarse_assign[coarse_mask],minlength=n)
    hillslope=np.divide(weighted,counts,out=np.full(n,.02),where=counts>0)
    np.savez_compressed(OUT/'catchment-coarse.npz', mask=coarse_mask, slope=coarse_slope, assigned_reach=coarse_assign, spacing_m=300, origin_xz_m=np.array([-61440,-61440]))
    np.savez_compressed(OUT/'reduced-network.npz', native_node=chosen, receiver=parent, x_m=x, z_m=z, local_land_area_m2=area, local_runoff_m3_s=runoff, accumulated_q_m3_s=q, length_m=length, bed_m=elev, slope=slope, hillslope=hillslope, width_m=width, depth_m=depth, channel_area_m2=channel_area)
    summaries={}
    coarse_change={'mask': coarse_mask}
    for cover in (.5, 2.):
        # Morphological batches mobilize a slope-dependent fraction of finite
        # hillslope solid. No recharge; channel cover is disjoint from hillslope.
        hills_initial=(area-channel_area)*cover*.6
        fraction=np.clip(.005 + .04*hillslope, .005, .04)
        remaining=hills_initial.copy(); transfer=np.empty((BATCHES,n))
        for j in range(BATCHES):
            transfer[j]=remaining*fraction
            remaining-=transfer[j]
        material=MaterialParameters(porosity=.4, provenance='declared default homogeneous material, geological game scenario')
        result=route_daily_sediment(receiver=parent, length_m=length, width_m=width, bed_elevation_m=elev,
            water_depth_m=np.tile(depth,(BATCHES,1)), water_q_m3_s=np.tile(q,(BATCHES,1)), friction_slope=np.tile(slope,(BATCHES,1)),
            time_seconds=np.arange(BATCHES+1,dtype=np.float64)*DT, rock_floor_m=elev-cover,
            initial_alluvium_bulk_m3=channel_area*cover, hardness=np.ones(n), material=material,
            external_solid_m3_s=transfer/DT, retention_fraction=np.zeros(n), geometry_identity_sha256=IDENTITY,
            hydraulic_identity_sha256=IDENTITY, material_provenance='assumed finite cover, default shear/capacity and settling')
        a=result['arrays']; exported=float(a['exported_solid_m3'].sum()); channel_final=float(a['trace_loose_solid_m3'][-1].sum()+a['trace_mobile_solid_m3'][-1].sum()); initial=float(area.sum()*cover*.6)
        residual=initial-float(remaining.sum())-channel_final-exported
        # Regional hillslope erosion in bulk-equivalent depth; channel changes separately.
        erosion=np.divide((hills_initial-remaining), (area-channel_area)*.6, out=np.zeros(n), where=(area-channel_area)>0)
        channel_delta=a['trace_bed_m'][-1]-elev
        tag='05' if cover==.5 else '2'
        initial_grid=np.zeros(coarse_mask.shape,dtype=np.float32)
        change_grid=np.zeros(coarse_mask.shape,dtype=np.float32)
        initial_grid[coarse_mask]=cover
        change_grid[coarse_mask]=-erosion[coarse_assign[coarse_mask]]
        coarse_change[f'initial_cover_{tag}_m']=initial_grid
        coarse_change[f'hillslope_bed_delta_{tag}_m']=change_grid
        np.savez_compressed(OUT/f'scenario-{tag}.npz', hillslope_initial_solid_m3=hills_initial, hillslope_remaining_solid_m3=remaining, hillslope_transfer_solid_m3=transfer, hillslope_erosion_bulk_m=erosion, channel_initial_bulk_m3=channel_area*cover, channel_final_solid_m3=a['trace_loose_solid_m3'][-1], channel_bed_delta_m=channel_delta, channel_deposition_solid_m3=a['deposited_solid_m3'].sum(axis=0), channel_erosion_solid_m3=a['eroded_loose_solid_m3'].sum(axis=0), mouth_export_by_batch_solid_m3=a['exported_solid_m3'].sum(axis=1), capacity_m3_s=a['capacity_solid_m3_s'][0], shear_pa=a['shear_stress_pa'][0])
        summaries[tag]=dict(cover_m=cover, initial_solid_m3=initial, hillslope_remaining_m3=float(remaining.sum()), channel_final_solid_m3=channel_final, hillslope_transfer_m3=float(transfer.sum()), channel_cumulative_deposition_m3=float(a['deposited_solid_m3'].sum()), channel_cumulative_erosion_m3=float(a['eroded_loose_solid_m3'].sum()), rock_erosion_m3=float(a['eroded_rock_m3'].sum()), mouth_export_solid_m3=exported, residual_m3=residual)
    np.savez_compressed(OUT/'coarse-cover-change.npz', **coarse_change)
    manifest=dict(identity=IDENTITY, mouth=MOUTH, count=n, assigned_land_area_m2=float(area.sum()), local_runoff_m3_s=float(runoff.sum()), outlet_q_m3_s=float(q[assignment[mouth]]), batch_count=BATCHES, effective_exposure_seconds_per_batch=DT, interpretation='accelerated 30 day frozen-hydraulic exposure per model batch, not simulated calendar years', assumed_porosity=.4, assumed_cover_m=[.5,2.], external_supply='unknown and excluded from known-local ledger', scenarios=summaries)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8'); print(json.dumps(manifest,indent=2),flush=True)

if __name__=='__main__': run()
