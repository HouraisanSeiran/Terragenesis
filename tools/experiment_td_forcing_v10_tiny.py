"""Limited original/v10 forcing continuity scans and four-cell transport tests."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from numba import njit
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_storage_compiled import advance_hour
from terrain_pipeline.td_basin_forcing_v10 import advance_forcing, simulate_forcing
from terrain_pipeline.td_basin_transport_v6 import _compiled_exchange


@njit(cache=True)
def coupled(states, rain, bed, step, runoff):
    errors = np.zeros_like(states)
    faces = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)
    empty = np.empty(0, np.int64)
    ledger = np.zeros((8, 4))
    for count in range(int(3600 / step)):
        first = advance_forcing(states, errors, rain, step/2, 1, runoff, .15)
        states, errors = first[0], first[1]
        ledger += first[2]
        exchange = _compiled_exchange(states[0], bed, faces, empty, np.empty(0), 30., step, .6, empty, empty)
        states[0] = exchange[0]
        errors[0] = 0
        second = advance_forcing(states, errors, rain, step/2, 1, runoff, .15)
        states, errors = second[0], second[1]
        ledger += second[2]
    return states, ledger


def main():
    directory = ROOT/'verification/td-basin-generation'/('A-v10-forcing-tiny-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    runoff = np.array([15.,150.,.15,1.,3600.,259200.])
    depths = [0., .99e-9, 1.01e-9, 1e-6]
    rates = [2.288880014936935, .149999, .15, .150001, 14.999999, 15., 15.000001, 30.]
    steps = [2.5,1.25,.625,.3125]
    rows = []
    for rain in rates:
        for depth in depths:
            for step in steps:
                initial = np.array([[depth],[30.],[0.],[0.]])
                original = advance_hour(initial.copy(),np.zeros_like(initial),np.array([rain]),np.array([1400.]),
                    np.empty((0,2),np.int64),np.empty(0,np.int64),np.empty(0),np.array([-1]),30.,step,int(3600/step),runoff,np.array([.6,1e-9,.15]))
                candidate = simulate_forcing(initial,np.array([rain]),substep_s=step)
                rows.append({'rain_mm_h':rain,'initial_depth_m':depth,'step_s':step,
                    'original_states':original[0][:,0].tolist(),'original_lake_rain_m3':float(original[2][1,0]),
                    'candidate_states':candidate['states'][:,0].tolist(),
                    'candidate_water_residual_mm':float(candidate['balance_residual_mm'][0])})
    weather_path=ROOT/'verification/td-native-storm-forcing/B-20261002T130322644482Z/eastward.npz'
    expected_weather_sha='6f48afd3692471ca4704097842a9d4cdc0ccdebdd508a722ab6d70859e7c7171'
    if file_sha256(weather_path)!=expected_weather_sha:
        raise ValueError('external weather SHA mismatch')
    cells=np.array([60278,60279,60280,60023])
    with np.load(weather_path,allow_pickle=False) as saved:
        actual_rain=saved['rain_mm_h'][0].ravel()[cells]
    source=ROOT/'verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz'
    if file_sha256(source)!='6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382':
        raise ValueError('external source SHA mismatch')
    with np.load(source,allow_pickle=False) as saved:
        bed=saved['height_m'].ravel()[cells]
    initial=np.zeros((4,4));initial[1]=30.
    pairs=[]
    previous=None
    for step in steps:
        states,ledger=coupled(initial.copy(),actual_rain,bed,step,runoff)
        residual=(states[0]*1000+states[1:].sum(axis=0)).sum()-120.-ledger[0].sum()+ledger[4].sum()+ledger[5].sum()
        if abs(residual)>1e-8 or np.any(states<0):
            raise ValueError('tiny coupled water budget/positivity failed')
        pairs.append({'step_s':step,'states':states.tolist(),'global_residual_mm_sum':float(residual),
            'previous_step_depth_difference_m':None if previous is None else float(abs(states[0]-previous[0]).max())})
        previous=states
    report={'schema':'td-v10-forcing-tiny-causal-candidate-v1','original_formulas_unchanged':True,
        'candidate_semantics':'new rain/surface unified infiltration hypothesis; no wet bypass; unchanged capacity/tau/ET parameters',
        'scans':rows,'coupled_four_cell':pairs,'actual_cells':cells.tolist(),'actual_rain_mm_h':actual_rain.tolist(),
        'actual_bed_m':bed.tolist(),'topology_scope':'experimental chain of four sampled cells, not their original TD D4 connectivity',
        'weather_pin':{'path':str(weather_path),'sha256':expected_weather_sha},
        'source_sha256':file_sha256(source),'code_sha256':{name:file_sha256(ROOT/name) for name in (
            'terrain_pipeline/td_basin_forcing_v10.py','tools/experiment_td_forcing_v10_tiny.py',
            'terrain_pipeline/td_basin_storage_compiled.py','terrain_pipeline/td_basin_transport_v6.py')},
        'hydraulic_ready':False,'publishable':False}
    path=directory/'report.json'
    publish_bytes(path,json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
    print(json.dumps({'report':str(path),'sha256':file_sha256(path)}))


if __name__=='__main__':
    main()
