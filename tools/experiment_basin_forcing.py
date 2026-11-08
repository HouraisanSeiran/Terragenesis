"""M4 tools.experiment_basin_forcing; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from datetime import datetime as _m4_experiment_td_forcing_v10_tiny_datetime
from datetime import timezone as _m4_experiment_td_forcing_v10_tiny_timezone
from numba import njit as _m4_experiment_td_forcing_v10_tiny_njit
from pathlib import Path as _m4_experiment_td_forcing_v10_tiny_Path
import json as _m4_experiment_td_forcing_v10_tiny_json
import numpy as _m4_experiment_td_forcing_v10_tiny_np
import sys as _m4_experiment_td_forcing_v10_tiny_sys

# --- tools/experiment_td_forcing_v10_tiny.py:8 ---
forcing_profile_10_tiny_ROOT = _m4_experiment_td_forcing_v10_tiny_Path(__file__).resolve().parents[1]

# --- tools/experiment_td_forcing_v10_tiny.py:9 ---
_m4_experiment_td_forcing_v10_tiny_sys.path.insert(0, str(forcing_profile_10_tiny_ROOT))

# --- tools/experiment_td_forcing_v10_tiny.py:20 ---
@_m4_experiment_td_forcing_v10_tiny_njit(cache=True)
def forcing_profile_10_tiny_coupled(states, rain, bed, step, runoff):
    from terrain_pipeline.basin_storage import _compiled_exchange as _m4_experiment_td_forcing_v10_tiny_compiled_exchange
    from terrain_pipeline.basin_storage import advance_forcing as _m4_experiment_td_forcing_v10_tiny_advance_forcing
    errors = _m4_experiment_td_forcing_v10_tiny_np.zeros_like(states)
    faces = _m4_experiment_td_forcing_v10_tiny_np.array([[0, 1], [1, 2], [2, 3]], dtype=_m4_experiment_td_forcing_v10_tiny_np.int64)
    empty = _m4_experiment_td_forcing_v10_tiny_np.empty(0, _m4_experiment_td_forcing_v10_tiny_np.int64)
    ledger = _m4_experiment_td_forcing_v10_tiny_np.zeros((8, 4))
    for count in range(int(3600 / step)):
        first = _m4_experiment_td_forcing_v10_tiny_advance_forcing(states, errors, rain, step/2, 1, runoff, .15)
        states, errors = first[0], first[1]
        ledger += first[2]
        exchange = _m4_experiment_td_forcing_v10_tiny_compiled_exchange(states[0], bed, faces, empty, _m4_experiment_td_forcing_v10_tiny_np.empty(0), 30., step, .6, empty, empty)
        states[0] = exchange[0]
        errors[0] = 0
        second = _m4_experiment_td_forcing_v10_tiny_advance_forcing(states, errors, rain, step/2, 1, runoff, .15)
        states, errors = second[0], second[1]
        ledger += second[2]
    return states, ledger

# --- tools/experiment_td_forcing_v10_tiny.py:38 ---
def forcing_profile_10_tiny_main():
    from terrain_pipeline.basin_storage import advance_hour_compensated as _m4_experiment_td_forcing_v10_tiny_advance_hour
    from terrain_pipeline.basin_storage import simulate_forcing as _m4_experiment_td_forcing_v10_tiny_simulate_forcing
    from terrain_pipeline.common_infra import file_sha256 as _m4_experiment_td_forcing_v10_tiny_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _m4_experiment_td_forcing_v10_tiny_publish_bytes
    directory = forcing_profile_10_tiny_ROOT/'verification/td-basin-generation'/('A-v10-forcing-tiny-'+_m4_experiment_td_forcing_v10_tiny_datetime.now(_m4_experiment_td_forcing_v10_tiny_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    runoff = _m4_experiment_td_forcing_v10_tiny_np.array([15.,150.,.15,1.,3600.,259200.])
    depths = [0., .99e-9, 1.01e-9, 1e-6]
    rates = [2.288880014936935, .149999, .15, .150001, 14.999999, 15., 15.000001, 30.]
    steps = [2.5,1.25,.625,.3125]
    rows = []
    for rain in rates:
        for depth in depths:
            for step in steps:
                initial = _m4_experiment_td_forcing_v10_tiny_np.array([[depth],[30.],[0.],[0.]])
                original = _m4_experiment_td_forcing_v10_tiny_advance_hour(initial.copy(),_m4_experiment_td_forcing_v10_tiny_np.zeros_like(initial),_m4_experiment_td_forcing_v10_tiny_np.array([rain]),_m4_experiment_td_forcing_v10_tiny_np.array([1400.]),
                    _m4_experiment_td_forcing_v10_tiny_np.empty((0,2),_m4_experiment_td_forcing_v10_tiny_np.int64),_m4_experiment_td_forcing_v10_tiny_np.empty(0,_m4_experiment_td_forcing_v10_tiny_np.int64),_m4_experiment_td_forcing_v10_tiny_np.empty(0),_m4_experiment_td_forcing_v10_tiny_np.array([-1]),30.,step,int(3600/step),runoff,_m4_experiment_td_forcing_v10_tiny_np.array([.6,1e-9,.15]))
                candidate = _m4_experiment_td_forcing_v10_tiny_simulate_forcing(initial,_m4_experiment_td_forcing_v10_tiny_np.array([rain]),substep_s=step)
                rows.append({'rain_mm_h':rain,'initial_depth_m':depth,'step_s':step,
                    'original_states':original[0][:,0].tolist(),'original_lake_rain_m3':float(original[2][1,0]),
                    'candidate_states':candidate['states'][:,0].tolist(),
                    'candidate_water_residual_mm':float(candidate['balance_residual_mm'][0])})
    weather_path=forcing_profile_10_tiny_ROOT/'verification/td-native-storm-forcing/B-20261002T130322644482Z/eastward.npz'
    expected_weather_sha='6f48afd3692471ca4704097842a9d4cdc0ccdebdd508a722ab6d70859e7c7171'
    if _m4_experiment_td_forcing_v10_tiny_file_sha256(weather_path)!=expected_weather_sha:
        raise ValueError('external weather SHA mismatch')
    cells=_m4_experiment_td_forcing_v10_tiny_np.array([60278,60279,60280,60023])
    with _m4_experiment_td_forcing_v10_tiny_np.load(weather_path,allow_pickle=False) as saved:
        actual_rain=saved['rain_mm_h'][0].ravel()[cells]
    source=forcing_profile_10_tiny_ROOT/'verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz'
    if _m4_experiment_td_forcing_v10_tiny_file_sha256(source)!='6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382':
        raise ValueError('external source SHA mismatch')
    with _m4_experiment_td_forcing_v10_tiny_np.load(source,allow_pickle=False) as saved:
        bed=saved['height_m'].ravel()[cells]
    initial=_m4_experiment_td_forcing_v10_tiny_np.zeros((4,4));initial[1]=30.
    pairs=[]
    previous=None
    for step in steps:
        states,ledger=forcing_profile_10_tiny_coupled(initial.copy(),actual_rain,bed,step,runoff)
        residual=(states[0]*1000+states[1:].sum(axis=0)).sum()-120.-ledger[0].sum()+ledger[4].sum()+ledger[5].sum()
        if abs(residual)>1e-8 or _m4_experiment_td_forcing_v10_tiny_np.any(states<0):
            raise ValueError('tiny coupled water budget/positivity failed')
        pairs.append({'step_s':step,'states':states.tolist(),'global_residual_mm_sum':float(residual),
            'previous_step_depth_difference_m':None if previous is None else float(abs(states[0]-previous[0]).max())})
        previous=states
    report={'schema':'td-v10-forcing-tiny-causal-candidate-v1','original_formulas_unchanged':True,
        'candidate_semantics':'new rain/surface unified infiltration hypothesis; no wet bypass; unchanged capacity/tau/ET parameters',
        'scans':rows,'coupled_four_cell':pairs,'actual_cells':cells.tolist(),'actual_rain_mm_h':actual_rain.tolist(),
        'actual_bed_m':bed.tolist(),'topology_scope':'experimental chain of four sampled cells, not their original TD D4 connectivity',
        'weather_pin':{'path':str(weather_path),'sha256':expected_weather_sha},
        'source_sha256':_m4_experiment_td_forcing_v10_tiny_file_sha256(source),'code_sha256':{name:_m4_experiment_td_forcing_v10_tiny_file_sha256(forcing_profile_10_tiny_ROOT/name) for name in (
            'terrain_pipeline/basin_storage.py','tools/experiment_basin_forcing.py',
            'terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py')},
        'hydraulic_ready':False,'publishable':False}
    path=directory/'report.json'
    _m4_experiment_td_forcing_v10_tiny_publish_bytes(path,_m4_experiment_td_forcing_v10_tiny_json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
    print(_m4_experiment_td_forcing_v10_tiny_json.dumps({'report':str(path),'sha256':_m4_experiment_td_forcing_v10_tiny_file_sha256(path)}))

def run_forcing_profile_10_tiny_cli():
    forcing_profile_10_tiny_main()

PROFILES = {
    'forcing_profile_10_tiny': run_forcing_profile_10_tiny_cli,
}

def main(argv=None):
    """Select a preserved M4 validator; remaining options go to that validator."""
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=tuple(PROFILES),default=next(iter(PROFILES)))
    selected,remaining=parser.parse_known_args(argv)
    previous=_m4_tail_sys.argv
    try:
        _m4_tail_sys.argv=[previous[0],*remaining]
        return PROFILES[selected.profile]()
    finally:
        _m4_tail_sys.argv=previous

if __name__ == '__main__':
    main()
