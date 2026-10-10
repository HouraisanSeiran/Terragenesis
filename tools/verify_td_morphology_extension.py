"""Pinned real TD PL morphology feedback, independent material and water ledgers."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import load_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    MorphologyConfig, _basis, _unpack, couple_morphology,
    load_morphology_coupling, save_morphology_coupling,
)
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID
from tools.verify_td_river_sediment import sample_saved_mesh
from tools.audit_td_river_geometry_sediment import independent_continuous_bed, independent_sediment


ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "verification/td-river-geometry/m5-20261008-06"
GEOMETRY_MANIFEST_SHA = "288d262297624daecd5e998e3ef8ca26dff20d2ff4bdd683d5bdae8f3346b87c"


def independent_cold(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    parent = _unpack(a, m, "geometry")
    ga = parent["arrays"]
    vertices, triangles = ga["vertices_xz_m"], ga["triangles"]
    points = vertices[triangles]
    area = np.abs((points[:, 1, 0]-points[:, 0, 0])*(points[:, 2, 1]-points[:, 0, 1])
                  -(points[:, 2, 0]-points[:, 0, 0])*(points[:, 1, 1]-points[:, 0, 1]))/2.
    porosity = m["material"]["porosity"]
    independent_areas = np.sum(area[None,:] * np.mean(a["basis"][:, triangles],axis=2), axis=1)
    np.testing.assert_allclose(independent_areas, a["material_area_m2"], rtol=0., atol=1e-10)
    water_export = 0.
    water_external = 0.
    solid_export = 0.
    solid_external = 0.
    max_mesh_volume_error = 0.
    max_node_solid_error = 0.
    peak_water_q = 0.
    peak_water_time = None
    export_times = [float(a["time_seconds"][0])]
    cumulative_water_export = [0.]
    for index in range(len(a["time_seconds"])):
        current = {key: value.copy() for key, value in ga.items()}
        current["bed_elevation_m"] = a["mesh_bed_m"][index]
        independent_continuous_bed(dict(arrays=current, metadata=parent["metadata"]))
        np.testing.assert_allclose(sample_saved_mesh(dict(arrays=current), ga["node_xz_m"]),
                                   a["node_bed_m"][index], rtol=0., atol=1e-8)
        exner = (a["source_node_bed_m"]
                 +(a["loose_solid_m3"][index]-a["loose_solid_m3"][0]) / ((1-porosity)*independent_areas)
                 -a["rock_removed_m3"][index]/independent_areas)
        np.testing.assert_allclose(exner, a["node_bed_m"][index], rtol=0., atol=1e-8)
        mesh_change = float(np.sum(area*np.mean((a["mesh_bed_m"][index]-a["mesh_bed_m"][0])[triangles],axis=1)))
        expected_material = float(np.sum((a["loose_solid_m3"][index]-a["loose_solid_m3"][0])/(1-porosity)
                                         -a["rock_removed_m3"][index]))
        max_mesh_volume_error = max(max_mesh_volume_error, abs(mesh_change-expected_material))
        np.testing.assert_allclose(mesh_change, expected_material, rtol=0., atol=1e-8)
        if index:
            water = _unpack(a, m, "water_"+str(index-1))
            sediment = _unpack(a, m, "sediment_"+str(index-1))
            independent_sediment(sediment)
            wa, sa = water["arrays"], sediment["arrays"]
            np.testing.assert_array_equal(sa["forcing_water_volume_m3"], wa["trace_volume_m3"][:-1])
            np.testing.assert_array_equal(sa["forcing_water_outflow_m3_s"], wa["trace_outflow_q_m3_s"])
            water_export += float(wa["trace_boundary_outflow_volume_m3"].sum())
            boundary_q = np.sum(wa["trace_outflow_q_m3_s"][:,wa["network_terminal_kind"]=="open_outflow"],axis=1)
            maximum_index = int(np.argmax(boundary_q))
            if peak_water_time is None or boundary_q[maximum_index] > peak_water_q:
                peak_water_q = float(boundary_q[maximum_index])
                peak_water_time = float(wa["trace_time_seconds"][maximum_index])
            for seconds, exported in zip(wa["trace_time_seconds"][1:],wa["trace_boundary_outflow_volume_m3"].sum(axis=1)):
                export_times.append(float(seconds))
                cumulative_water_export.append(cumulative_water_export[-1]+float(exported))
            water_external += float(np.sum(wa["trace_local_q_m3_s"]*np.diff(wa["trace_time_seconds"])[:,None]))
            solid_export += float(sa["step_exported_solid_m3"].sum())
            solid_external += float(sa["step_external_solid_m3"].sum())
        water_residual = float(a["water_volume_m3"][0].sum()+water_external-water_export-a["water_volume_m3"][index].sum())
        solid_residual = float(a["mobile_solid_m3"][0].sum()+a["loose_solid_m3"][0].sum()
                               +solid_external+a["rock_removed_m3"][index].sum()-solid_export
                               -a["mobile_solid_m3"][index].sum()-a["loose_solid_m3"][index].sum())
        np.testing.assert_allclose(water_residual, 0., rtol=0., atol=1e-8)
        np.testing.assert_allclose(solid_residual, 0., rtol=0., atol=1e-8)
        max_node_solid_error = max(max_node_solid_error, abs(solid_residual))
    return dict(status=m["status"], committed_intervals=len(m["intervals"]),
        last_time_seconds=float(a["time_seconds"][-1]), water_export_m3=water_export,
        water_input_m3=water_external, solid_export_m3=solid_export,
        max_mesh_material_volume_difference_m3=max_mesh_volume_error,
        max_solid_residual_m3=max_node_solid_error,
        max_bed_change_m=float(np.max(np.abs(a["mesh_bed_m"][-1]-a["mesh_bed_m"][0]))),
        material_area_m2=a["material_area_m2"].tolist(),
        final_node_bed_m=a["node_bed_m"][-1].tolist(),
        final_water_volume_m3=a["water_volume_m3"][-1].tolist(),
        peak_boundary_water_q_m3_s=peak_water_q, peak_boundary_water_time_seconds=peak_water_time,
        half_export_arrival_time_seconds=float(np.interp(water_export/2.,cumulative_water_export,export_times)),
        needs_revalidation=m["needs_geometry_and_hydraulic_revalidation"])


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if file_sha256(GEOMETRY/"acceptance.json") != GEOMETRY_MANIFEST_SHA:
        raise AssertionError("M5 manifest changed")
    manifest = json.loads((GEOMETRY/"acceptance.json").read_text(encoding="utf-8"))
    pin = manifest["artifacts"]["td_fine"]
    geometry = load_channel_geometry(GEOMETRY/pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    source = load_diagnostic_product(TD_DIRECTORY/"product.npz", expected_sha256=TD_PRODUCT_SHA, expected_identity=TD_PRODUCT_ID)
    a = geometry["arrays"]
    n = len(a["receiver"])
    bed = sample_saved_mesh(geometry,a["node_xz_m"])
    lengths, slope = np.zeros(n), np.zeros(n)
    for i,j in enumerate(a["receiver"]):
        if j>=0:
            length=np.linalg.norm(a["node_xz_m"][j]-a["node_xz_m"][i])
            lengths[i]+=length/2.; lengths[j]+=length/2.
            slope[i]=(bed[i]-bed[j])/length
    for i,j in enumerate(a["receiver"]):
        if j<0: slope[i]=slope[np.flatnonzero(a["receiver"]==i)[0]]
    network=ChannelNetwork(a["receiver"].copy(),lengths,a["width_m"].copy(),bed,slope,
        np.full(n,.035),np.full(n,2.),np.where(a["receiver"]>=0,"interior","open_outflow"),
        geometry["identity_sha256"],"canonical TD fine bed; disjoint half incident lengths","explicit n=.035")
    _,material_area,_=_basis(geometry)
    material=MaterialParameters(sediment_erodibility_m_s_pa=1e-8,rock_erodibility_m_s_pa=1e-10,
        transport_coefficient=1e-6,settling_velocity_m_s=.0001,
        provenance="explicit uncalibrated homogeneous TD scenario; exact PL material area")
    inputs=dict(initial_water_volume_m3=a["width_m"]*lengths*.01,
        initial_mobile_solid_m3=np.full(n,1e-5),initial_alluvium_bulk_m3=material_area*.002,
        rock_floor_m=bed-.3)
    source_times=source["arrays"]["time_seconds"]
    local=source["arrays"]["local_q_m3_s"].reshape(len(source_times)-1,-1)[:,a["source_node_cell_ids"]]
    cases,artifacts,products={},{},{}
    for name,macro_step in (("td-feedback-native-intervals",None),("td-feedback-coarse",150.),("td-feedback-fine",75.)):
        times=source_times.copy() if macro_step is None else np.unique(np.r_[source_times,np.arange(0.,900.+macro_step,macro_step)])
        indices=np.minimum(np.searchsorted(source_times,times[:-1],side="right")-1,len(local)-1)
        forcing=ChannelForcing(times,local[indices].copy(),source["identity_sha256"])
        result=couple_morphology(geometry,network,forcing,material,**inputs,
            config=MorphologyConfig(max_intervals=16),channel_config=ChannelConfig(max_dt_seconds=.5),
            sediment_config=SedimentConfig(max_dt_seconds=.125,max_bed_change_m=.001))
        if result["metadata"]["status"]!="complete": raise AssertionError(result["metadata"]["failure_reason"])
        path=output/(name+".npz")
        save_morphology_coupling(path,result)
        artifacts[name]=dict(path=path.name,sha256=file_sha256(path),identity_sha256=result["identity_sha256"])
        with patch("terrain_pipeline.surface_rivers.metric_morphology_coupling.couple_morphology",side_effect=AssertionError("cold coupling")), \
             patch("terrain_pipeline.surface_rivers.metric_morphology_coupling.solve_channel",side_effect=AssertionError("cold water")), \
             patch("terrain_pipeline.surface_rivers.metric_morphology_coupling.solve_sediment",side_effect=AssertionError("cold sediment")):
            cold=load_morphology_coupling(path,expected_sha256=artifacts[name]["sha256"])
            cases[name]=independent_cold(cold)
        products[name]=result
        print(json.dumps({"case":name,**cases[name]}),flush=True)
    fine,coarse=products["td-feedback-fine"]["arrays"],products["td-feedback-coarse"]["arrays"]
    bed_difference=float(np.max(np.abs(fine["mesh_bed_m"][-1]-coarse["mesh_bed_m"][-1])))
    export_difference=abs(cases["td-feedback-fine"]["solid_export_m3"]-cases["td-feedback-coarse"]["solid_export_m3"])/max(cases["td-feedback-fine"]["solid_export_m3"],1e-12)
    if bed_difference>.001 or export_difference>.01: raise AssertionError(("feedback refinement",bed_difference,export_difference))
    baseline=products["td-feedback-native-intervals"]["arrays"]
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for name in ("td-feedback-coarse","td-feedback-fine"):
        values=products[name]["arrays"]
        axes[0].plot(values["time_seconds"],1000.*np.min(values["node_bed_m"]-values["node_bed_m"][0],axis=1),label=name)
    axes[0].set_ylabel("Maximum bed lowering (mm)");axes[0].set_xlabel("Seconds");axes[0].legend()
    axes[1].plot((fine["node_bed_m"][-1]-baseline["node_bed_m"][-1])*1e6,marker="o")
    axes[1].set_ylabel("Fine minus native macro bed (micrometres)");axes[1].set_xlabel("Control node")
    fig.tight_layout();fig.savefig(output/"morphology-feedback-preview.png",dpi=150);plt.close(fig)
    report=dict(schema="td-morphology-feedback-verification-v1",status="accepted_bounded_no_lake_feedback",
        artifacts=artifacts,cases=cases,bed_macro_refinement_m=bed_difference,solid_export_macro_refinement_relative=export_difference,
        fine_minus_native_macro_max_bed_m=float(np.max(np.abs(fine["mesh_bed_m"][-1]-baseline["mesh_bed_m"][-1]))),
        geometry_manifest_sha256=GEOMETRY_MANIFEST_SHA,
        limitations=["operator_split_manning_sediment_not_two_way_momentum_PDE","no_lakes_or_backwater",
                     "bounded_4node90m_TD_reach","material_basis_area_differs_from_M6_floor_only_replay"],
        hydraulic_ready=False,natural_outlet_verified=False,publishable=False)
    publish_bytes(output/"acceptance.json",json.dumps(report,indent=2,allow_nan=False).encode())
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();result=verify(args.output)
    print(json.dumps({key:result[key] for key in ("status","bed_macro_refinement_m","solid_export_macro_refinement_relative")}))


if __name__=="__main__":
    main()
