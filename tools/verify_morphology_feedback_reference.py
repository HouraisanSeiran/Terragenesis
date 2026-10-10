"""Independent continuous feedback ODE and frozen-water comparison, on M5 beds."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import build_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product
from terrain_pipeline.surface_rivers.metric_channel_solver import solve_channel
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    MorphologyConfig, _basis, couple_morphology, load_morphology_coupling, save_morphology_coupling,
)
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters, SedimentConfig, SedimentDomain, SedimentForcing, solve_sediment,
)
from tools.verify_td_morphology_extension import independent_cold
from tools.verify_td_river_geometry import fixture
from tools.verify_td_river_sediment import sample_saved_mesh


def case(name):
    terrain, cells, receiver, options = fixture("y" if name == "y" else "single", 1.)
    geometry = build_channel_geometry(terrain, cells, receiver, **options)
    a = geometry["arrays"]
    nodes, widths = a["node_xz_m"], a["width_m"]
    n = len(receiver)
    lengths = np.zeros(n)
    slope = np.zeros(n)
    bed = sample_saved_mesh(geometry, nodes)
    for i, j in enumerate(receiver):
        if j >= 0:
            length = np.linalg.norm(nodes[i] - nodes[j])
            lengths[i] += length / 2.
            lengths[j] += length / 2.
            slope[i] = (bed[i] - bed[j]) / length
    for i in np.flatnonzero(receiver < 0):
        slope[i] = slope[np.flatnonzero(receiver == i)[0]]
    network = ChannelNetwork(receiver.copy(), lengths, widths.copy(), bed, slope,
        np.full(n, .035), np.full(n, 2.), np.where(receiver < 0, "open_outflow", "interior"),
        geometry["identity_sha256"], "disjoint half-incident M5 controls", "explicit n=.035")
    basis, material_area, _ = _basis(geometry)
    material = MaterialParameters(sediment_critical_shear_pa=0., rock_critical_shear_pa=0.,
        sediment_erodibility_m_s_pa=0., rock_erodibility_m_s_pa=1e-7 if name == "rock" else 0.,
        transport_coefficient=.01, settling_velocity_m_s=0. if name == "rock" else .002,
        provenance="explicit synthetic coupled ODE convergence scenario")
    local = np.zeros((2, n))
    local[0, np.bincount(receiver[receiver >= 0], minlength=n) == 0] = .05
    forcing = ChannelForcing(np.array([0., 4., 12.]), local, "b" * 64)
    inputs = dict(initial_water_volume_m3=widths * lengths * .03,
        initial_mobile_solid_m3=np.full(n, .003), initial_alluvium_bulk_m3=np.zeros(n),
        rock_floor_m=bed - .2)
    return geometry, network, forcing, material, inputs, basis, material_area


def ode(network, forcing, material, inputs, area, edge_length, output_times):
    n = len(network.receiver)
    hydraulic_area = network.width_m * network.length_m
    initial_loose = inputs["initial_alluvium_bulk_m3"] * (1. - material.porosity)
    initial = np.r_[inputs["initial_water_volume_m3"], inputs["initial_mobile_solid_m3"],
                    initial_loose, np.zeros(n), 0., 0.]

    def rhs(_, state, interval):
        volume, mobile, loose, rock = np.maximum(state[:4*n], 0.).reshape(4, n)
        if material.settling_velocity_m_s == 0. and material.sediment_erodibility_m_s_pa == 0.:
            # This state is exactly constant; an implicit solver's tiny positive
            # Jacobian perturbations must not cover exposed rock forever.
            loose = initial_loose.copy()
        bed = network.bed_elevation_m + (loose - initial_loose) / ((1-material.porosity)*area) - rock/area
        slope = network.bed_slope.copy()
        for i, j in enumerate(network.receiver):
            if j >= 0:
                slope[i] = (bed[i] - bed[j]) / edge_length[i]
        for i in np.flatnonzero(network.receiver < 0):
            slope[i] = slope[np.flatnonzero(network.receiver == i)[0]]
        depth = volume / hydraulic_area
        radius = network.width_m * depth / (network.width_m + 2*depth)
        flow = network.width_m * depth * radius**(2/3) * np.sqrt(slope) / network.roughness
        shear = 9810. * radius * slope
        shear[flow == 0.] = 0.
        capacity = material.transport_coefficient * network.width_m * np.maximum(shear-material.sediment_critical_shear_pa, 0.)**1.5
        outgoing = np.minimum(flow*np.divide(mobile, volume, out=np.zeros(n), where=volume>0.), capacity)
        deposition = material.settling_velocity_m_s * np.divide(mobile, depth, out=np.zeros(n), where=depth>0.)
        erosion = np.minimum(np.maximum(capacity-outgoing, 0.), area * material.rock_erodibility_m_s_pa
                             * np.maximum(shear-material.rock_critical_shear_pa, 0.))
        erosion[loose > 0.] = 0.
        water_in, solid_in = np.zeros(n), np.zeros(n)
        for i, j in enumerate(network.receiver):
            if j >= 0:
                water_in[j] += flow[i]
                solid_in[j] += outgoing[i]
        terminal = network.receiver < 0
        return np.r_[forcing.local_q_m3_s[interval]+water_in-flow,
                     solid_in+erosion-outgoing-deposition, deposition, erosion,
                     flow[terminal].sum(), outgoing[terminal].sum()]

    output = np.empty((len(output_times), len(initial)))
    output[0] = initial
    state = initial
    for interval, (start, end) in enumerate(zip(forcing.time_seconds[:-1], forcing.time_seconds[1:])):
        solution = solve_ivp(lambda t, y: rhs(t, y, interval), (start, end), state,
                             method="Radau", rtol=2e-10, atol=1e-12, dense_output=True, max_step=.02)
        if not solution.success:
            raise AssertionError(solution.message)
        take = (output_times > start) & (output_times <= end)
        output[take] = solution.sol(output_times[take]).T
        state = solution.y[:, -1]
    return output


def frozen(geometry, network, forcing, material, inputs, area):
    water = solve_channel(network, forcing, inputs["initial_water_volume_m3"], ChannelConfig(max_dt_seconds=.005))
    product = make_channel_product(network, forcing, water)
    a = water["arrays"]
    domain = SedimentDomain(network.receiver.copy(), area.copy(), network.width_m.copy(),
        network.bed_elevation_m.copy(), inputs["rock_floor_m"].copy(), inputs["initial_alluvium_bulk_m3"].copy(),
        np.zeros(len(area), bool), network.receiver < 0, geometry["identity_sha256"], "same exact PL material area frozen reference")
    replay = SedimentForcing(a["time_seconds"].copy(), a["volume_m3"][:-1].copy(), a["depth_m"][:-1].copy(),
        a["outflow_q_m3_s"].copy(), np.broadcast_to(network.bed_slope, a["outflow_q_m3_s"].shape).copy(),
        np.zeros_like(a["outflow_q_m3_s"]), product["identity_sha256"], geometry["identity_sha256"], "whole-event frozen water reference")
    sediment = solve_sediment(domain, replay, material, inputs["initial_mobile_solid_m3"], SedimentConfig(max_dt_seconds=.0025))
    if water["metadata"]["status"] != "complete" or sediment["metadata"]["status"] != "complete":
        raise AssertionError("frozen reference failed")
    return dict(final_bed_m=sediment["arrays"]["trace_bed_elevation_m"][-1].tolist(),
                water_export_m3=float(water["arrays"]["boundary_outflow_volume_m3"].sum()),
                solid_export_m3=float(sediment["arrays"]["step_exported_solid_m3"].sum()),
                peak_boundary_water_q_m3_s=float(np.max(a["outflow_q_m3_s"][:,network.receiver<0].sum(axis=1))),
                peak_boundary_water_time_seconds=float(a["time_seconds"][np.argmax(a["outflow_q_m3_s"][:,network.receiver<0].sum(axis=1))]),
                half_export_arrival_time_seconds=float(np.interp(float(a["boundary_outflow_volume_m3"].sum())/2.,
                    np.r_[0.,np.cumsum(a["boundary_outflow_volume_m3"].sum(axis=1))],a["time_seconds"])))


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    reports, artifacts = {}, {}
    for name in ("single", "y", "rock"):
        geometry, network, forcing, material, inputs, basis, area = case(name)
        edge_length = np.ones(len(area))
        for i, j in enumerate(network.receiver):
            if j >= 0:
                edge_length[i] = np.linalg.norm(geometry["arrays"]["node_xz_m"][i] - geometry["arrays"]["node_xz_m"][j])
        records = {}
        for label, macro, water_dt in (("coarse", 2., .02), ("fine", 1., .005)):
            times = np.unique(np.r_[forcing.time_seconds, np.arange(0., 12. + macro, macro)])
            local = forcing.local_q_m3_s[np.searchsorted(forcing.time_seconds, times[:-1], side="right")-1]
            result = couple_morphology(geometry, network, ChannelForcing(times, local.copy(), forcing.source_identity_sha256),
                material, **inputs, config=MorphologyConfig(), channel_config=ChannelConfig(max_dt_seconds=water_dt),
                sediment_config=SedimentConfig(max_dt_seconds=water_dt/2.))
            if result["metadata"]["status"] != "complete":
                raise AssertionError((name, label, result["metadata"]["failure_reason"]))
            path = output / (name + "-" + label + ".npz")
            save_morphology_coupling(path, result)
            pin = dict(path=path.name, sha256=file_sha256(path), identity_sha256=result["identity_sha256"])
            artifacts[name+"-"+label] = pin
            with patch("terrain_pipeline.surface_rivers.metric_morphology_coupling.couple_morphology", side_effect=AssertionError("cold solve")), \
                 patch("terrain_pipeline.surface_rivers.metric_morphology_coupling.solve_channel", side_effect=AssertionError("cold water")), \
                 patch("terrain_pipeline.surface_rivers.metric_morphology_coupling.solve_sediment", side_effect=AssertionError("cold sediment")):
                cold = load_morphology_coupling(path, expected_sha256=pin["sha256"])
                evidence = independent_cold(cold)
            a = result["arrays"]
            reference = ode(network, forcing, material, inputs, area, edge_length, a["time_seconds"])
            n = len(area)
            water_error = float(np.max(np.abs(reference[:,:n]-a["water_volume_m3"]))) / max(float(reference[:,:n].max()),1e-12)
            solid_state = np.concatenate((a["mobile_solid_m3"],a["loose_solid_m3"],a["rock_removed_m3"]),axis=1)
            solid_error = float(np.max(np.abs(reference[:,n:4*n]-solid_state))) / max(float(reference[:,n:4*n].max()),1e-12)
            evidence.update(water_ODE_relative_error=water_error, solid_ODE_relative_error=solid_error)
            records[label] = evidence
            print(json.dumps(dict(case=name,label=label,**evidence)),flush=True)
        if records["fine"]["water_ODE_relative_error"] > .005 or records["fine"]["solid_ODE_relative_error"] > .005:
            raise AssertionError((name,"independent coupled ODE threshold",records))
        if any(records["fine"][key] >= records["coarse"][key] for key in ("water_ODE_relative_error","solid_ODE_relative_error")):
            raise AssertionError((name,"coupled time refinement",records))
        records["frozen"] = frozen(geometry, network, forcing, material, inputs, area)
        records["fine_minus_frozen_max_bed_m"] = float(np.max(np.abs(np.array(records["fine"]["final_node_bed_m"])-records["frozen"]["final_bed_m"])))
        records["fine_minus_frozen_water_export_m3"] = records["fine"]["water_export_m3"] - records["frozen"]["water_export_m3"]
        records["fine_minus_frozen_solid_export_m3"] = records["fine"]["solid_export_m3"] - records["frozen"]["solid_export_m3"]
        records["fine_minus_frozen_peak_water_q_m3_s"] = records["fine"]["peak_boundary_water_q_m3_s"] - records["frozen"]["peak_boundary_water_q_m3_s"]
        records["fine_minus_frozen_half_export_arrival_seconds"] = records["fine"]["half_export_arrival_time_seconds"] - records["frozen"]["half_export_arrival_time_seconds"]
        reports[name] = records
    report = dict(status="accepted_bounded_coupled_ODE",cases=reports,artifacts=artifacts,
        limitations=["synthetic_M5_no_lake_Manning_Exner_operator_split","not_a_momentum_PDE_or_global_hydraulic_certificate"],
        hydraulic_ready=False,natural_outlet_verified=False,publishable=False)
    publish_bytes(output/"acceptance.json",json.dumps(report,indent=2,allow_nan=False).encode())
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    print(json.dumps(verify(parser.parse_args().output)["status"]))
