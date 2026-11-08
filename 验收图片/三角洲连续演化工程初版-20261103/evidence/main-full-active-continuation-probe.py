"""Cold-read integration probe of an active new arm in an equivalent interval."""
import json
from pathlib import Path
from terrain_pipeline.coastal_delta_evolution import load,save,advance_years,TidalConfig
from terrain_pipeline.coastal_delta_avulsion import activate_candidate
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_longterm import LongtermConfig

root=Path(__file__).parent
s,p=load(root/'full-final-short-formed')
cfg=HydraulicConfig(p['integrated']['route_metadata']['extension_port_stage_m'])
s,p,activation=activate_candidate(s,p,hydraulic_config=cfg)
assert activation['activated']
save(root/'main-full-active-before',s,p)
before=s
current,progress=advance_years(s,p,.0625,input_id='main-active-continuation',hydraulic_config=cfg,
    marine_config=LongtermConfig(settling_velocity_m_s=1e-5),river_deposition_fraction=.0001,
    tidal_config=TidalConfig(amplitude_m=.3,phase_count=4),step_years=.25)
save(root/'main-full-active-after',current,progress)
stock=lambda a:sum(float(getattr(a,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+a.exported_solid_m3+a.unresolved_solid_m3
residual=stock(current)-stock(before)+progress['formation_undelivered_solid_m3']-p['formation_undelivered_solid_m3']-(progress['supply_solid_m3']-p['supply_solid_m3'])
report={'years_before':p['years'],'years_after':progress['years'],'routes_before':len(p['routes']),
        'routes_after':len(progress['routes']),'route_q_m3_s':progress['river_hydraulics']['route_q_m3_s'],
        'physical_time_unchanged':before.time_s==current.time_s,'physical_water_unchanged':before.water_input_m3==current.water_input_m3,
        'solid_residual_m3':residual,'activation_solid_cut_m3':activation['solid_cut_m3']}
report['pass']=bool(abs(residual)<1 and report['physical_time_unchanged'] and report['physical_water_unchanged'] and report['routes_after']>=2 and sum(q>0 for q in report['route_q_m3_s'])>=2)
(root/'main-full-active-continuation-probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
assert report['pass']
