"""Two opposite moving storms on frozen real four-pool lake/reach geometry."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np

from terrain_pipeline.lake import load_mountain_geometry as load_mountain_geometry
from terrain_pipeline.lake import build_group_topology as build_group_topology
from terrain_pipeline.lake import couple_rainfall as couple_rainfall
from terrain_pipeline.lake import group_lake_specs as group_lake_specs
from terrain_pipeline.lake import load_coupling as load_coupling
from terrain_pipeline.lake import save_coupling as save_coupling
from terrain_pipeline.lake import validate_coupling as validate_coupling
from terrain_pipeline.common_infra import file_sha256, load_legacy_source
from terrain_pipeline.climate_forcing import StormParameters, storm_generate_forcing as generate_forcing, interval_mean_mm_h, storm_load_forcing as load_forcing, save_forcing, validate_forcing
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from tools.verify_mountain_lake_coupling import audit_browser,export_review_case
from tools.verify_mountain_source_adapter import assert_unchanged,snapshot,write_json


FROZEN=ROOT/"verification/mountain-lake-coupling/frozen-20261001-A-v3"
DELIVERY=("terrain_pipeline/climate_forcing.py","tests/test_mountain_storm_forcing.py",
    "tools/verify_mountain_storm_forcing.py","docs/mountain-storm-forcing-v1.md")
B_MANIFEST=ROOT/"verification/mountain-depression-geometry/frozen-20261001T070426687355Z/static-freeze-manifest.json"
B_OLD="f1173c702a150b2865b11be53e13ee950dd47be74172a829701f60659c576d6d"
B_NEW="6be2f275de2907183a214903f35fc7742d34a7f26141c1757b036cd42e477694"


def check_frozen_compatibility(frozen_hashes):
    for name,digest in frozen_hashes.items():
        actual=file_sha256(ROOT/name)
        if name=='terrain_pipeline/lake.py':
            if digest!=B_OLD or actual!=B_NEW:
                raise ValueError("geometry compatibility exception is only the explicitly accepted old/new pair")
        elif actual!=digest:
            raise ValueError("A-v3 frozen non-geometry source changed: "+name)
    if not B_MANIFEST.is_file():
        raise ValueError("B frozen static manifest required")
    return {"file":'terrain_pipeline/lake.py',"A_v3_sha256":B_OLD,
        "compatible_static_validator_sha256":B_NEW,"B_static_freeze_manifest":str(B_MANIFEST),
        "B_manifest_sha256":file_sha256(B_MANIFEST),
        "coordinator_authorization":"explicit old/new geometry exception after independent cold-load normal/pressure1378 1345-state tests; no other exception"}


def verify(destination):
    if destination.exists():
        raise FileExistsError(destination)
    before=snapshot()
    frozen_report=json.loads((FROZEN/"report.json").read_text(encoding="utf-8"))
    frozen_hashes=frozen_report["delivery_source_sha256"]
    compatibility=check_frozen_compatibility(frozen_hashes)
    delivery_before={name:file_sha256(ROOT/name) for name in DELIVERY}
    write_json(destination/"frozen-before.json",dict(before=before,A_v3=frozen_hashes,weather=delivery_before))
    try:
        source=load_legacy_source("pressure_mountain",boundary_policy="all_edges_open")
        geometry_path=FROZEN/"pressure_mountain-geometry.npz"
        if file_sha256(geometry_path)!=frozen_report["samples"]["pressure_mountain"]["geometry_archive_sha256"]:
            raise ValueError("external frozen geometry archive hash mismatch")
        geometry=load_mountain_geometry(geometry_path,trusted_height=source["arrays"]["height_m"],
            source_binding={"source_identity":source["identity_sha256"]})
        topology,selection,lake_nodes=build_group_topology(source,geometry,1378)
        mask=selection["arrays"]["mask"]
        rows,columns=np.nonzero(mask)
        origin=source["metadata"]["origin_m_xz"]
        east=origin[0]+columns*30.
        south=origin[1]+rows*30.
        pairs=np.column_stack((np.floor(east/300).astype(np.int64),np.floor(south/300).astype(np.int64)))
        unique,labels=np.unique(pairs,axis=0,return_inverse=True)
        owner=np.full(mask.shape,-1,np.int64)
        owner[mask]=labels
        hrus=len(unique)
        if hrus>256:
            raise ValueError("absolute land bins plus independent lake HRUs exceed 256")
        center=[float((east.min()+east.max())/2),float((south.min()+south.max())/2)]
        report={"status":"moving_parameterized_storm_real_group","group":1378,"area_m2":float(mask.sum()*900),
            "source_identity":source["identity_sha256"],"selection_identity":selection["identity_sha256"],
            "geometry_identity":topology["geometry_identity"],"HRUs":hrus,"hru_partition":"absolute 300m mixed land/lake bins; unique cell area; lake rain aggregation error explicitly measured",
            "duration_h":72.,"dt_s":900.,"gpu_inference_run":False,"cases":{},
            "geometry_compatibility_exception":compatibility}
        steps=288
        counts=np.bincount(labels,minlength=hrus)
        baseline_specs=group_lake_specs(source,geometry,topology,lake_nodes,steps=steps)
        baseline=couple_rainfall(source,topology,owner,np.zeros((steps,hrus),np.float64),dt_s=900.,geometry=geometry,
            selection=selection,lakes=baseline_specs,surface_rain=True,parameters=RunoffParameters(initial_soil_mm=135.))
        if "arrays" not in baseline:
            raise ValueError("identical-initial-state dry baseline failed")
        save_coupling(destination/"pressure_mountain-no_rain-coupling.npz",baseline)
        baseline_flow=baseline["arrays"]["total_boundary_volume_m3"]/900.
        report["no_rain_baseline"]={"initial_soil_mm":135.,"peak_q_m3_s":float(baseline_flow.max()),
            "peak_interval_start_h":float(baseline_flow.argmax()*.25),
            "archive_sha256":file_sha256(destination/"pressure_mountain-no_rain-coupling.npz")}
        direction_rain={}
        for direction in (1,-1):
            name="eastward" if direction==1 else "westward"
            parameters=StormParameters(center[0]-direction*2160.,center[1],direction*.1,0.,300.,24.,21600.,64800.)
            forcing=generate_forcing(owner,origin_m_xz=origin,spacing_m=30.,steps=steps,dt_s=900.,start_s=0.,
                parameters=parameters,source_identity=source["identity_sha256"],selection_identity=selection["identity_sha256"])
            weather_path=destination/f"{name}-weather.npz"
            save_forcing(weather_path,forcing)
            loaded=load_forcing(weather_path,expected_sha256=file_sha256(weather_path),cell_owner=owner,
                source_identity=source["identity_sha256"],selection_identity=selection["identity_sha256"])
            specs=group_lake_specs(source,geometry,topology,lake_nodes,steps=steps)
            result=couple_rainfall(source,topology,owner,loaded["arrays"]["rain_mm_h"],dt_s=900.,geometry=geometry,
                selection=selection,lakes=specs,surface_rain=True,parameters=RunoffParameters(initial_soil_mm=135.))
            if "arrays" not in result:
                failure={key:value for key,value in result.items() if key!="lake_failure"}
                if "lake_failure" in result:
                    from terrain_pipeline.lake import save_lake_routing as save_lake_routing

                    save_lake_routing(result["lake_failure"],destination/f"{name}-failed-lake.npz")
                    failure["lake_diagnostic"]=result["lake_failure"]["diagnostic"]
                write_json(destination/f"{name}-failure.json",failure)
                report["cases"][name]=failure
                continue
            coupling_path=destination/f"pressure_mountain-{name}-coupling.npz"
            save_coupling(coupling_path,result)
            cold=load_coupling(coupling_path,expected_sha256=file_sha256(coupling_path),source=source,
                topology=topology,geometry=geometry,selection=selection)
            stats=validate_coupling(cold,source=source,topology=topology,geometry=geometry,selection=selection)
            arrays=result["arrays"]
            flow=arrays["total_boundary_volume_m3"]/900.
            direction_rain[name]=forcing["arrays"]["rain_mm_h"]
            hours=np.arange(steps)*.25
            mean_rain=(forcing["arrays"]["rain_mm_h"]*forcing["arrays"]["area_m2"]).sum(axis=1)/forcing["arrays"]["area_m2"].sum()
            rain_peak=int(mean_rain.argmax())
            storm_indices=np.flatnonzero((hours>=6)&(hours<18))
            response_indices=np.flatnonzero(hours>=6)
            increment=flow-baseline_flow
            increment_peak=int(response_indices[increment[response_indices].argmax()])
            storm_peak=int(storm_indices[increment[storm_indices].argmax()])
            spatial_error=0.
            lake_error=0.
            peak_map=None
            max_cell_rain=0.
            for step in range(steps):
                values=interval_mean_mm_h(east,south,float(step*900),float((step+1)*900),parameters)
                approximate=forcing["arrays"]["rain_mm_h"][step,labels]
                spatial_error=max(spatial_error,float(np.abs(values-approximate).max()))
                lake_cells=geometry["arrays"]["lake_id"][mask]>0
                lake_error=max(lake_error,float(np.abs(values[lake_cells]-approximate[lake_cells]).max()))
                if values.max()>max_cell_rain:
                    max_cell_rain=float(values.max())
                    peak_map=(step,values.copy())
            refined=generate_forcing(owner,origin_m_xz=origin,spacing_m=30.,steps=steps,dt_s=900.,start_s=0.,
                parameters=parameters,source_identity=source["identity_sha256"],selection_identity=selection["identity_sha256"],spatial_subsamples=4)
            stats.update(parameters=forcing["metadata"]["parameters"],weather_identity=forcing["identity_sha256"],
                weather_sha256=file_sha256(weather_path),coupling_sha256=file_sha256(coupling_path),
                peak_q_m3_s=float(flow.max()),peak_interval_start_h=float(flow.argmax()*.25),
                max_lake_stage_by_node_m={str(node):float(arrays["lake_stage_m"][:,node].max()) for node in lake_nodes.values()},
                total_weather_rain_m3=validate_forcing(forcing)["total_rain_m3"],
                max_HRU_vs_cell_rain_error_mm_h=spatial_error,max_lake_HRU_vs_cell_rain_error_mm_h=lake_error,
                max_center_vs_4x4_HRU_rain_error_mm_h=float(np.abs(forcing["arrays"]["rain_mm_h"]-refined["arrays"]["rain_mm_h"]).max()),
                center_vs_4x4_total_rain_difference_m3=validate_forcing(refined)["total_rain_m3"]-validate_forcing(forcing)["total_rain_m3"],
                dynamic_water_solved=True,river_stage_solved=False)
            stats.update(storm_response={"semantics":"difference from identical-initial-state no-rain simulation; nonlinear runoff response, not linear superposition",
                "area_mean_rain_peak_mm_h":float(mean_rain[rain_peak]),"rain_peak_interval_start_h":float(hours[rain_peak]),
                "storm_window_increment_peak_m3_s":float(increment[storm_peak]),
                "storm_window_increment_peak_interval_start_h":float(hours[storm_peak]),
                "post_storm_start_increment_peak_m3_s":float(increment[increment_peak]),
                "increment_peak_interval_start_h":float(hours[increment_peak]),
                "increment_peak_lag_from_rain_peak_h":float(hours[increment_peak]-hours[rain_peak]),
                "72h_increment_boundary_volume_m3":float((increment*900).sum())})
            report["cases"][name]=stats
            export_review_case(destination,"pressure_mountain",name,source,geometry,topology,selection,result)
            consumer_path=destination/f"pressure_mountain-{name}-weather-consumer.json"
            write_json(consumer_path,{"parameters":forcing["metadata"]["parameters"],"weather_identity":forcing["identity_sha256"],
                "time_interval_start_h":(np.arange(steps)*.25).tolist(),"HRU_rain_mm_h":forcing["arrays"]["rain_mm_h"].tolist(),
                "HRU_area_m2":forcing["arrays"]["area_m2"].tolist(),"HRU_bins_east_south":unique.tolist(),
                "error":{key:value for key,value in stats.items() if "error" in key or "difference" in key}})
            plot_weather(destination,name,east,south,peak_map,parameters)
        if set(direction_rain)=={"eastward","westward"}:
            east_rain,west_rain=direction_rain["eastward"],direction_rain["westward"]
            start,end=24,72
            report["opposite_direction_rain_symmetry"]={
                "theory":"same absolute spatial path with reversed constant velocity and symmetric active period; each cell/HRU integrated rain equal",
                "max_HRU_integrated_depth_difference_mm":float(np.abs((east_rain-west_rain).sum(axis=0)*.25).max()),
                "max_HRU_active_time_reversal_difference_mm_h":float(np.abs(east_rain[start:end]-west_rain[start:end][::-1]).max()),
                "no_window_normalization":True}
        report["frozen_after"]=assert_unchanged(before)
        report["A_v3_non_geometry_delivery_unchanged"]=all(file_sha256(ROOT/name)==digest for name,digest in frozen_hashes.items()
            if name!='terrain_pipeline/lake.py')
        if compatibility!=check_frozen_compatibility(frozen_hashes):
            raise RuntimeError("B compatibility changed during weather verification")
        report["delivery_source_sha256"]=delivery_before
        if any(file_sha256(ROOT/name)!=digest for name,digest in delivery_before.items()):
            raise RuntimeError("weather delivery changed during verification")
        write_json(destination/"report.json",report)
        write_review(destination,report)
        return report
    except BaseException as error:
        write_json(destination/"failure.json",{"exception":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
        raise


def plot_weather(destination,name,east,south,peak_map,parameters):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    step,values=peak_map
    figure,axis=plt.subplots(figsize=(7,5))
    image=axis.scatter(east/1000,south/1000,c=values,s=20,marker="s",vmin=0,vmax=24,cmap="Blues")
    figure.colorbar(image,ax=axis,label="Time-mean cell rain mm/h")
    axis.set_xlabel("Absolute east km")
    axis.set_ylabel("Absolute south km")
    axis.invert_yaxis()
    axis.set_title(f"{name}; {step*.25:.2f}-{(step+1)*.25:.2f} h; parameterized storm")
    figure.tight_layout()
    figure.savefig(destination/f"{name}-weather.png",dpi=130)
    plt.close(figure)


def write_review(destination,report):
    from terrain_pipeline.common_infra import publish_bytes
    import html

    options="".join(f'<option value="pressure_mountain-{name}">{name}</option>' for name,case in report["cases"].items() if case.get("dynamic_water_solved"))
    frozen_html=(FROZEN/"review.html").read_text(encoding="utf-8")
    lower=frozen_html.index('<select id="case">')
    upper=frozen_html.index('</select>',lower)
    page=frozen_html[:lower]+'<select id="case">'+options+frozen_html[upper:]
    page=page.replace('<h1>真实旧 TD：有限窗口完整贡献组湖河耦合</h1>',
        '<h1>pressure1378：相反方向移动雨团（参数化天气，非预报）</h1>')
    page=page.replace('<select id="case">','<details><summary>天气参数、误差与方向对照</summary><pre>'+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+'</pre></details><select id="case">')
    publish_bytes(destination/"review.html",page.encode("utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--browser-review",type=Path)
    parser.add_argument("--forcing-only",action="store_true")
    args=parser.parse_args()
    if args.browser_review:
        audit_browser(args.browser_review)
        return
    destination=args.output or ROOT/"verification/mountain-storm-forcing"/("run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    report=prepare_forcing_only(destination) if args.forcing_only else verify(destination)
    print({"output":str(destination),"directions":list(report["cases"])})


def prepare_forcing_only(destination):
    """Use externally pinned saved selection; do not import or call B geometry APIs."""
    from terrain_pipeline.common_infra import checked_archive

    if destination.exists():
        raise FileExistsError(destination)
    before=snapshot()
    frozen_report=json.loads((FROZEN/"report.json").read_text(encoding="utf-8"))
    sample=frozen_report["samples"]["pressure_mountain"]
    group=sample["cascade_positive_group_dynamics"]
    stats=group["scenarios"]["wet_storm_surface"]
    saved=checked_archive(FROZEN/"pressure_mountain_cascade_positive-wet_storm_surface-coupling.npz",
        expected_sha256=stats["archive_sha256"],max_bytes=768*1024*1024)
    mask=saved["hydrology_mask"]
    source=load_legacy_source("pressure_mountain",boundary_policy="all_edges_open")
    if source["identity_sha256"]!=sample["source_identity"]:
        raise ValueError("fixed source identity changed")
    rows,columns=np.nonzero(mask)
    origin=source["metadata"]["origin_m_xz"]
    east=origin[0]+columns*30.
    south=origin[1]+rows*30.
    pairs=np.column_stack((np.floor(east/300).astype(np.int64),np.floor(south/300).astype(np.int64)))
    unique,labels=np.unique(pairs,axis=0,return_inverse=True)
    owner=np.full(mask.shape,-1,np.int64)
    owner[mask]=labels
    center=[float((east.min()+east.max())/2),float((south.min()+south.max())/2)]
    report={"status":"forcing_only_no_B_validator_or_hydrological_advance","cases":{},
        "source_identity":source["identity_sha256"],"selection_identity":group["selection_identity"],
        "trusted_selection_archive_sha256":stats["archive_sha256"],"HRUs":len(unique),
        "area_m2":float(mask.sum()*900),"gpu_inference_run":False,
        "parameters_common":{"sigma_m":300.,"peak_mm_h":24.,"start_s":21600.,"end_s":64800.,
            "dt_s":900.,"steps":288,"duration_h":72.,"center_crossing_h":12.},
        "cases_are_weather_only_not_solved_water":True}
    rain_arrays={}
    for direction,name in ((1,"eastward"),(-1,"westward")):
        parameters=StormParameters(center[0]-direction*2160.,center[1],direction*.1,0.,300.,24.,21600.,64800.)
        forcing=generate_forcing(owner,origin_m_xz=origin,spacing_m=30.,steps=288,dt_s=900.,start_s=0.,
            parameters=parameters,source_identity=source["identity_sha256"],selection_identity=group["selection_identity"])
        path=destination/f"{name}-weather.npz"
        save_forcing(path,forcing)
        cold=load_forcing(path,expected_sha256=file_sha256(path),cell_owner=owner,
            source_identity=source["identity_sha256"],selection_identity=group["selection_identity"])
        refined=generate_forcing(owner,origin_m_xz=origin,spacing_m=30.,steps=288,dt_s=900.,start_s=0.,
            parameters=parameters,source_identity=source["identity_sha256"],selection_identity=group["selection_identity"],spatial_subsamples=4)
        rain_arrays[name]=cold["arrays"]["rain_mm_h"]
        report["cases"][name]=dict(validate_forcing(cold),parameters=cold["metadata"]["parameters"],
            resources=cold["metadata"]["resources"],archive_sha256=file_sha256(path),identity_sha256=cold["identity_sha256"],
            max_center_vs_4x4_HRU_rain_error_mm_h=float(np.abs(cold["arrays"]["rain_mm_h"]-refined["arrays"]["rain_mm_h"]).max()),
            refined_total_rain_m3=validate_forcing(refined)["total_rain_m3"])
    report["rain_symmetry"]={"max_HRU_integrated_depth_difference_mm":float(np.abs((rain_arrays["eastward"]-rain_arrays["westward"]).sum(axis=0)*.25).max()),
        "max_HRU_time_reversal_difference_mm_h":float(np.abs(rain_arrays["eastward"][24:72]-rain_arrays["westward"][24:72][::-1]).max())}
    report["frozen_after"]=assert_unchanged(before)
    report["delivery_source_sha256"]={name:file_sha256(ROOT/name) for name in DELIVERY}
    write_json(destination/"report.json",report)
    return report


if __name__=="__main__":
    main()
