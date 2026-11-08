"""Serial new-physics v10 weather hour pages, frozen inputs and resource history."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import psutil
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs
from terrain_pipeline.td_basin_storage_v10 import simulate_hour
from terrain_pipeline.td_basin_storage_v10_io import save_storage, save_checkpoint, load_storage, load_checkpoint
from tools.verify_td_native_weather_storage import ResourceMonitor, THREAD_NAMES
from tools.verify_td_basin_storage import HIERARCHY, HIERARCHY_SHA256, HIERARCHY_IDENTITY
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256


def write(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))


def pin(path, result):
    return {'path':str(path.resolve()),'expected_sha256':file_sha256(path),'expected_identity':result['identity_sha256']}


def verify(weather_index, weather_sha, coarse=2.5, fine=1.25):
    if any(os.environ.get(name) != '1' for name in THREAD_NAMES):
        raise ValueError('explicit single-thread environment required')
    if coarse != 2*fine or any(not np.isfinite(step) or step <= 0 or int(3600/step)*step != 3600 for step in (coarse,fine)):
        raise ValueError('exact finite hourly halving required')
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError('primary source SHA mismatch')
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    weather = load_weather_inputs(weather_index, expected_sha256=weather_sha, hierarchy=hierarchy)
    directory = ROOT/'verification/td-basin-generation'/('A-native-weather-v10-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    code_names = ('terrain_pipeline/td_basin_forcing_v10.py','terrain_pipeline/td_basin_storage_v10.py',
        'terrain_pipeline/td_basin_storage_v10_io.py','terrain_pipeline/td_basin_storage_compiled.py',
        'terrain_pipeline/td_basin_transport_v6.py','terrain_pipeline/mountain_source_adapter.py',
        'terrain_pipeline/td_native_weather_storage_inputs.py','terrain_pipeline/td_native_storm_forcing.py',
        'terrain_pipeline/mountain_storm_forcing.py','terrain_pipeline/td_basin_hierarchy.py',
        'terrain_pipeline/td_basin_source.py','terrain_pipeline/rainfall_runoff.py',
        'tools/verify_td_native_weather_storage.py','tools/verify_td_native_weather_storage_v10.py',
        'tools/verify_td_basin_storage.py')
    code = {name:file_sha256(ROOT/name) for name in code_names}
    budgets = {str(step):{'chunk_face_steps':int(3600/step)*len(hierarchy['arrays']['face_cells']),
        'global_face_steps_per_direction':24*int(3600/step)*len(hierarchy['arrays']['face_cells'])} for step in (coarse,fine)}
    if any(value['chunk_face_steps'] > 6000000000 for value in budgets.values()):
        raise ValueError('v10 chunk budget exceeded')
    write(directory/'run-inputs.json', {'schema':'td-v10-spatial-weather-run-inputs-v1',
        'weather_index':weather['index_pin'],'weather_records':{name:value['record'] for name,value in weather['cases'].items()},
        'hierarchy':{'path':str(HIERARCHY),'expected_sha256':HIERARCHY_SHA256,'expected_identity':HIERARCHY_IDENTITY},
        'primary_sha256':PRIMARY_SHA256,'steps_s':[coarse,fine],'budgets':budgets,'chunk_max_face_steps':6000000000,
        'job_max_bytes':1073741824,'code_sha256':code,'physics_version':'v10-unified-infiltration; not execution-equivalence',
        'forcing_identities':{name:value['forcing_identity'] for name,value in weather['cases'].items()},
        'depth_gate_m':.001,'receiver_gate':.01})
    write(directory/'execution-code.json', {'code_sha256':code,'sources':{name:(ROOT/name).read_text(encoding='utf-8') for name in code_names[:5]}})
    monitor = ResourceMonitor(psutil.Process()); monitor.start()
    scenarios = {}
    try:
        for direction in ('eastward','westward'):
            case = weather['cases'][direction]
            pages = {}
            for step in (coarse,fine):
                checkpoint = None
                records = []
                for hour in range(24):
                    began = time.perf_counter()
                    result = simulate_hour(hierarchy, case['rain_mm_h'], substep_s=step, checkpoint=checkpoint)
                    page_dir = directory/f'{direction}-{step:g}s'/f'hour-{hour:02d}'
                    save_storage(page_dir/'storage.npz',result['storage'])
                    save_checkpoint(page_dir/'checkpoint.npz',result['checkpoint'])
                    record = {'hour':hour,'storage':pin(page_dir/'storage.npz',result['storage']),
                        'checkpoint':pin(page_dir/'checkpoint.npz',result['checkpoint']),
                        'elapsed_s':time.perf_counter()-began,'forcing_identity':case['forcing_identity'],
                        'chunk_work_face_steps':budgets[str(step)]['chunk_face_steps'],
                        'global_water_residual_m3':float(result['storage']['arrays']['balance_residual_m3'].sum())}
                    write(page_dir/'report.json',record)
                    checkpoint = load_checkpoint(**record['checkpoint'])
                    records.append(record); monitor.check()
                    print(f'{directory.name} {direction} {step}s hour{hour+1} elapsed{record["elapsed_s"]:.2f}s',flush=True)
                pages[str(step)] = records
            maximum = 0.; differences = []
            for first,second in zip(pages[str(coarse)],pages[str(fine)]):
                first_page=load_storage(**first['storage']);second_page=load_storage(**second['storage'])
                difference=abs(first_page['arrays']['depth_m']-second_page['arrays']['depth_m'])
                value=float(difference.max());maximum=max(maximum,value)
                frame,cell=np.unravel_index(difference.argmax(),difference.shape)
                differences.append({'hour':first['hour'],'max_depth_difference_m':value,'frame':int(frame),'cell':int(cell)})
            first_cp=load_checkpoint(**pages[str(coarse)][-1]['checkpoint'])
            second_cp=load_checkpoint(**pages[str(fine)][-1]['checkpoint'])
            routed_first=first_cp['arrays']['cumulative_routed_volume_m3'];routed_second=second_cp['arrays']['cumulative_routed_volume_m3']
            relative=float(abs(routed_first-routed_second).sum()/max(1e-12,routed_second.sum()))
            comparison={'schema':'td-v10-spatial-weather-comparison-v1','pages':pages,'hour_comparisons':differences,
                'max_saved_depth_difference_m':maximum,'cumulative_receiver_relative_l1':relative,
                'gate_passed':maximum<=.001 and relative<=.01,'weather_record':case['record'],
                'forcing_identity':case['forcing_identity'],'steps_s':[coarse,fine],
                'hydraulic_ready':False,'publishable':False,'scope':'24h new v10 physical hypothesis; original TD full spatial weather'}
            write(directory/(direction+'-comparison.json'),comparison)
            scenarios[direction]=comparison
        if any(file_sha256(ROOT/name)!=sha for name,sha in code.items()) or file_sha256(weather_index)!=weather_sha or file_sha256(HIERARCHY)!=HIERARCHY_SHA256 or file_sha256(PRIMARY_PATH)!=PRIMARY_SHA256:
            raise ValueError('v10 final frozen dependency changed')
        for case in weather['cases'].values():
            if file_sha256(case['record']['path'])!=case['record']['expected_sha256']:
                raise ValueError('v10 weather file changed')
        write(directory/'index.json', {'schema':'td-v10-spatial-weather-hour-pages-index-v1','scenarios':scenarios,
            'weather_index':weather['index_pin'],'steps_s':[coarse,fine],'code_sha256':code,'budgets':budgets,
            'all_numerical_gates_passed':all(value['gate_passed'] for value in scenarios.values()),
            'hydraulic_ready':False,'transient_converged':False,'publishable':False})
        monitor.stop();monitor.check()
        write(directory/'resource.json', {'schema':'td-v10-spatial-weather-resource-v1','index_sha256':file_sha256(directory/'index.json'),
            'scope':'complete eastward+westward both steps execution','complete':True,**monitor.record()})
        write(directory/'final-pin.json', {'index_path':str(directory/'index.json'),'index_sha256':file_sha256(directory/'index.json'),
            'resource_path':str(directory/'resource.json'),'resource_sha256':file_sha256(directory/'resource.json')})
        print(json.dumps({'run':str(directory),'index_sha256':file_sha256(directory/'index.json')}),flush=True)
    except Exception as error:
        monitor.stop()
        write(directory/'failure.json', {'error':str(error),'complete':False,'resource':monitor.record(),
            'hydraulic_ready':False,'publishable':False})
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--weather-index',type=Path,required=True)
    parser.add_argument('--weather-index-sha256',required=True)
    parser.add_argument('--coarse-step',type=float,default=2.5)
    parser.add_argument('--fine-step',type=float,default=1.25)
    arguments=parser.parse_args()
    verify(arguments.weather_index,arguments.weather_index_sha256,arguments.coarse_step,arguments.fine_step)
