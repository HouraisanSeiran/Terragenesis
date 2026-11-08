"""Opt-in finite river/marine events on any saved complex morphology product.

Run with runtime/venv/Scripts/python.exe -B tools/run_delta_network_coupled.py
--source <frozen variant directory> --out <new directory> --control-spacing 1200.
The display DEM stays at its original spacing; hydraulic controls are irregular.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from terrain_pipeline.delta_network_coupling import (
    load_frozen_product, advance_cadence, coupled_evidence, file_sha256)
from terrain_pipeline.coastal_delta_evolution import save, load
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_hydraulic_capacity import HydraulicCapacityRule
from terrain_pipeline.coastal_marine_sediment import MarineConfig


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=1,sort_keys=True)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--control-spacing',type=float,default=1200.)
    parser.add_argument('--geometry-tolerance',type=float,default=15.)
    parser.add_argument('--control-cell-search',type=float,default=None,
        help='Bounded along-source shift for interior account-cell coincidences; default one DEM cell. Zero disables it.')
    parser.add_argument('--subdivisions',type=int,default=4)
    parser.add_argument('--erodible-layer',type=float,default=.5)
    parser.add_argument('--porosity',type=float,default=.4)
    parser.add_argument('--q',type=float,default=None)
    parser.add_argument('--stage-limit',type=float,default=12.)
    parser.add_argument('--roughness',type=float,default=.035)
    parser.add_argument('--solid-rate',type=float,default=2.)
    parser.add_argument('--critical-shear',type=float,default=.05)
    parser.add_argument('--transport-coefficient',type=float,default=.001)
    parser.add_argument('--erodibility',type=float,default=1e-6)
    parser.add_argument('--river-settling',type=float,default=.001)
    parser.add_argument('--marine-settling',type=float,default=.001)
    parser.add_argument('--sea-level',type=float,default=0.)
    parser.add_argument('--tide-amplitude',type=float,default=0.)
    parser.add_argument('--marine-step',type=float,default=60.)
    parser.add_argument('--cadence',type=float,default=300.)
    parser.add_argument('--ticks',type=int,default=2)
    parser.add_argument('--run-id',default='frozen-complex-event')
    parser.add_argument('--verify-restart',action='store_true',
        help='Repeat identical complete ticks with a cold checkpoint between ticks; compare all stocks and progress.')
    args=parser.parse_args()
    if args.ticks < 1 or (args.verify_restart and args.ticks<2):
        parser.error('ticks must be positive; restart verification needs at least two ticks')
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('output directory must be new or empty')
    args.out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    hydraulic=HydraulicConfig(args.stage_limit,args.roughness)
    marine=MarineConfig(sea_level_m=args.sea_level,tide_amplitude_m=args.tide_amplitude,
        step_s=args.marine_step,settling_velocity_m_s=args.marine_settling,
        material_source='declared homogeneous finite shelf/channel material')
    rule=HydraulicCapacityRule(critical_shear_pa=args.critical_shear,
        transport_coefficient=args.transport_coefficient,sediment_erodibility_m_s_pa=args.erodibility,
        settling_velocity_m_s=args.river_settling)
    if args.resume:
        initial,progress=load(args.resume)
        source=progress['complex_network']['frozen_product']['directory']
        if Path(source).resolve()!=args.source.resolve():
            parser.error('resume checkpoint is bound to a different source directory')
    else:
        initial,progress=load_frozen_product(args.source,hydraulic_config=hydraulic,
            discharge_m3_s=args.q,solid_rate_m3_s=args.solid_rate,
            erodible_thickness_m=args.erodible_layer,porosity=args.porosity,
            control_spacing_m=args.control_spacing,geometry_tolerance_m=args.geometry_tolerance,
            subdivisions=args.subdivisions,sea_level_m=args.sea_level,
            control_cell_search_m=args.control_cell_search)
    initialization_seconds=time.perf_counter()-started
    options=dict(cadence_s=args.cadence,run_id=args.run_id,marine_config=marine,
        hydraulic_config=hydraulic,capacity_rule=rule,inlet_solid_rate_m3_s=args.solid_rate)
    result,p,reports=advance_cadence(initial,progress,args.ticks,**options)
    continuation={'tested':False,'boundary':'only equal complete physical event ticks; arbitrary cuts are not equivalent'}
    if args.verify_restart:
        first,fp,_=advance_cadence(initial,progress,1,**options)
        save(args.out/'split-checkpoint',first,fp)
        cold,cp=load(args.out/'split-checkpoint')
        resumed,rp,_=advance_cadence(cold,cp,args.ticks-1,**options)
        equal={name:bool(np.array_equal(getattr(result,name),getattr(resumed,name)))
               for name in ('base_bed_m','bed_solid_m3','mobile_solid_m3','stranded_solid_m3')}
        continuation.update(tested=True,arrays_bitwise_equal=equal,progress_equal=(p==rp),
            same_time_s=(result.time_s==resumed.time_s),split_after_ticks=1)
        if not all(equal.values()) or p!=rp or result.time_s!=resumed.time_s:
            raise RuntimeError('cold-read continuation differs at the same event cadence')
    save(args.out/'checkpoint',result,p)
    evidence=coupled_evidence(result,p)
    evidence['continuation']=continuation
    write_json(args.out/'physical-report.json',evidence)
    np.save(args.out/'bed_dem_float64.npy',result.bed_m)
    np.save(args.out/'bed_delta_m.npy',result.bed_m-np.load(args.source/'bed_dem_float64.npy',mmap_mode='r'))
    np.save(args.out/'mobile_solid_m3.npy',result.mobile_solid_m3)
    peak=None
    try:
        import psutil
        memory=psutil.Process().memory_info()
        peak=getattr(memory,'peak_wset',memory.rss)
    except ImportError:
        pass
    resources={'elapsed_seconds':time.perf_counter()-started,
        'initialization_seconds':initialization_seconds,'peak_working_set_bytes':peak,
        'grid_shape':list(result.base_bed_m.shape),'dem_spacing_m':result.spacing_m,
        'hydraulic_control_spacing_m':args.control_spacing,
        'output_bytes':sum(path.stat().st_size for path in args.out.iterdir() if path.is_file())}
    write_json(args.out/'resources.json',resources)
    write_json(args.out/'manifest.json',dict(product='complex-delta-physical-event-v1',
        source=progress['complex_network'],hydraulic=asdict(hydraulic),marine=asdict(marine),
        capacity_rule=rule.identity(),event_cadence_s=args.cadence,physical_time_s=result.time_s,
        formation_time='geological initial condition; no equivalent years assigned',
        fixed_topology=True,known_limitations=['rectangular Manning DAG approximation',
            'fixed planform and initial design widths; actual bed/depth/Q/shear evolve',
            'declared homogeneous finite erodible layer; uncalibrated transport coefficients'],
        deposition_semantics=evidence['deposition_semantics'],
        unconnected_processes=evidence['unconnected_processes'],
        continuation=continuation,resources=resources,
        code_sha256={str(path.relative_to(ROOT)).replace('\\','/'):file_sha256(path) for path in
            [Path(__file__),ROOT/'terrain_pipeline/delta_network_coupling.py',
             ROOT/'terrain_pipeline/coastal_delta_hydraulic_event.py',
             ROOT/'terrain_pipeline/coastal_delta_hydraulic_capacity.py',
             ROOT/'terrain_pipeline/coastal_delta_graph_hydraulics.py']}))
    write_json(args.out/'sha256sums.json',{path.name:file_sha256(path) for path in sorted(args.out.iterdir())
                                        if path.is_file() and path.name!='sha256sums.json'})
    print(json.dumps({'out':str(args.out),'physical_seconds':result.time_s,
        'hydraulic_nodes':evidence['hydraulic_nodes'],'solid_residual_m3':evidence['solid_residual_m3'],
        'channel_exterior_deposition':evidence['channel_exterior_deposition'],
        'inventory_solid_m3':evidence['inventory_solid_m3'],'continuation':continuation,
        'resources':resources},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
