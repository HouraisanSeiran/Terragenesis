"""M6 independent temporal references and sediment on newly solved M5 geometry."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
from scipy.spatial import cKDTree

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.channel_geometry import load_channel_geometry
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product, save_channel_product
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters, SedimentConfig, SedimentDomain, SedimentForcing, solve_sediment,
    save_sediment, load_sediment,
)
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product


def sample_saved_mesh(product, points):
    a = product["arrays"]
    triangles = a["triangles"]
    coordinates = a["vertices_xz_m"][triangles]
    tree = cKDTree(coordinates.mean(axis=1))
    _, nearby = tree.query(points, k=min(16, len(triangles)))
    values = []
    for point, candidates in zip(points, np.atleast_2d(nearby)):
        for index in np.atleast_1d(candidates):
            coords = coordinates[index]
            weights = np.linalg.solve(np.vstack((coords.T, np.ones(3))), np.r_[point, 1.])
            if weights.min() >= -1e-10:
                values.append(float(np.dot(weights, a["bed_elevation_m"][triangles[index]])))
                break
        else:
            raise AssertionError("point absent from saved canonical mesh")
    return np.asarray(values)


def independent_rhs(domain, forcing, material, interval, state):
    """Independent ODE in mobile/loose/removed-rock coordinates."""
    n = len(domain.receiver)
    mobile, loose, removed = np.split(np.maximum(state, 0.), 3)
    depth = forcing.water_depth_m[interval]
    flow = forcing.water_outflow_m3_s[interval]
    volume = forcing.water_volume_m3[interval]
    hydraulic_radius = domain.width_m * depth / (domain.width_m + 2. * depth)
    shear = 9810. * hydraulic_radius * forcing.friction_slope[interval]
    shear[(flow == 0.) | domain.is_lake] = 0.
    excess = np.maximum(0., shear - material.sediment_critical_shear_pa)
    capacity = material.transport_coefficient * domain.width_m * excess ** 1.5
    advective = flow * np.divide(mobile, volume, out=np.zeros(n), where=volume > 0.)
    outgoing = np.where(domain.is_lake, advective, np.minimum(advective, capacity))
    settled = material.settling_velocity_m_s * np.divide(mobile, depth, out=np.zeros(n), where=depth > 0.)
    entrained = np.minimum(np.maximum(0., capacity - outgoing),
                          domain.bed_area_m2 * material.sediment_erodibility_m_s_pa * excess * (1. - material.porosity))
    entrained[loose <= 0.] = 0.
    rock = np.minimum(np.maximum(0., capacity - outgoing - entrained), domain.bed_area_m2
                      * material.rock_erodibility_m_s_pa * np.maximum(0., shear - material.rock_critical_shear_pa))
    rock[loose > 0.] = 0.
    reserve = (domain.bed_elevation_m - domain.initial_alluvium_bulk_m3 / domain.bed_area_m2
               - domain.rock_floor_m) * domain.bed_area_m2
    rock[removed >= reserve] = 0.
    incoming = np.zeros(n)
    for i, j in enumerate(domain.receiver):
        if j >= 0:
            incoming[j] += outgoing[i]
    return np.r_[incoming + forcing.external_solid_m3_s[interval] + entrained + rock - outgoing - settled,
                 settled - entrained, rock]


def reference(domain, forcing, material, initial_mobile, times):
    state = np.r_[initial_mobile, domain.initial_alluvium_bulk_m3 * (1. - material.porosity),
                  np.zeros(len(domain.receiver))]
    result = np.empty((len(times), len(state)))
    result[0] = state
    for i, (start, end) in enumerate(zip(forcing.time_seconds[:-1], forcing.time_seconds[1:])):
        solved = solve_ivp(lambda t, y: independent_rhs(domain, forcing, material, i, y),
                           (start, end), state, method="DOP853", rtol=1e-11, atol=1e-13,
                           dense_output=True, max_step=.1)
        if not solved.success:
            raise AssertionError(solved.message)
        take = (times > start) & (times <= end)
        result[take] = solved.sol(times[take]).T
        state = solved.y[:, -1]
    return result


def solid_budget(product):
    a, m = product["arrays"], product["metadata"]
    initial = float(np.sum(a["trace_mobile_solid_m3"][0] + a["trace_bed_alluvium_solid_m3"][0]))
    external = float(a["step_external_solid_m3"].sum())
    rock = float(a["step_eroded_rock_m3"].sum())
    exported = float(a["step_exported_solid_m3"].sum())
    final = float(np.sum(a["trace_mobile_solid_m3"][-1] + a["trace_bed_alluvium_solid_m3"][-1]))
    residual = initial + external + rock - exported - final
    if not np.isfinite([initial, external, rock, exported, final]).all() or abs(residual) > 1e-8 * max(1., initial + external + rock):
        raise AssertionError("independent solid budget failed")
    return {"initial_solid_m3": initial, "external_solid_m3": external, "eroded_rock_m3": rock,
            "exported_solid_m3": exported, "final_retained_solid_m3": final, "residual_solid_m3": residual,
            "deposited_solid_m3": float(a["step_deposited_solid_m3"].sum()),
            "deposited_bulk_m3": float(a["step_bulk_deposition_m3"].sum()),
            "deposited_pore_m3": float(a["step_pore_deposition_m3"].sum()),
            "max_bed_change_m": float(np.max(np.abs(a["trace_bed_elevation_m"] - a["domain_bed_elevation_m"]))),
            "steps": len(a["step_dt_seconds"]), "status": m["status"],
            "needs_revalidation": m["needs_geometry_and_hydraulic_revalidation"]}


def benchmark(name):
    receiver = np.array([-1] if name in ("settling", "rock") else [2, 2, 3, -1], np.int64)
    n = len(receiver)
    domain = SedimentDomain(receiver, np.full(n, 100.), np.full(n, 4.),
                            np.arange(n, 0, -1).astype(float) * 2., np.full(n, -10.),
                            np.zeros(n) if name == "rock" else np.full(n, .1),
                            np.array([name == "settling"] if n == 1 else [False, False, False, True]),
                            np.full(n, name == "rock", bool), "a" * 64, "explicit analytical geometry and material scenario")
    material = MaterialParameters(sediment_erodibility_m_s_pa=2e-8, rock_erodibility_m_s_pa=0.,
                                   transport_coefficient=.01, settling_velocity_m_s=.01,
                                   provenance="explicit uncalibrated temporal convergence fixture")
    if name == "rock":
        material = MaterialParameters(sediment_erodibility_m_s_pa=0., rock_erodibility_m_s_pa=1e-8,
                                       transport_coefficient=.01, settling_velocity_m_s=0.,
                                       provenance="constant exposed-rock source and exponential washout reference")
    volume = np.full((1, n), 20.)
    depth = np.full((1, n), .5)
    flow = np.array([[.2]]) if name == "rock" else np.zeros((1, n)) if n == 1 else np.array([[.2, .2, .4, 0.]])
    forcing = SedimentForcing(np.array([0., 30.]), volume, depth, flow, np.full((1, n), .01),
                              np.zeros((1, n)), "b" * 64, "a" * 64,
                              "prescribed steady water analytic fixture; no TD acceptance claim")
    initial = np.array([0.]) if name == "rock" else np.array([.02] if n == 1 else [.02, .02, 0., 0.])
    return domain, forcing, material, initial


def verify(geometry_directory, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    geometry_directory = Path(geometry_directory).resolve()
    manifest = json.loads((geometry_directory / "acceptance.json").read_text(encoding="utf-8"))
    pins, cases, products = {}, {}, {}

    def save(name, result):
        path = output / (name + ".npz")
        save_sediment(path, result)
        pins[name] = {"path": path.name, "sha256": file_sha256(path), "identity_sha256": result["identity_sha256"]}
        load_sediment(path, expected_sha256=pins[name]["sha256"])
        cases[name] = solid_budget(result)
        products[name] = result

    for name in ("settling", "y_to_lake", "rock"):
        domain, forcing, material, initial = benchmark("y" if name == "y_to_lake" else name)
        errors = []
        for label, dt in (("coarse", .5), ("fine", .125)):
            result = solve_sediment(domain, forcing, material, initial, SedimentConfig(max_dt_seconds=dt))
            if result["metadata"]["status"] != "complete":
                raise AssertionError(result["metadata"])
            a = result["arrays"]
            independent = reference(domain, forcing, material, initial, a["trace_time_seconds"])
            observed = np.concatenate([a["trace_" + key] for key in (
                "mobile_solid_m3", "bed_alluvium_solid_m3", "rock_removed_m3")], axis=1)
            # The error scale excludes stationary bed inventory to expose transport errors.
            scale = max(float(independent[:, :len(initial)].max()), float(initial.sum()), 1e-9)
            error = float(np.max(np.abs(observed - independent))) / scale
            errors.append(error)
            save(name + "_" + label, result)
            cases[name + "_" + label]["ODE_relative_state_error"] = error
            if name == "settling":
                exact = initial[0] * np.exp(-material.settling_velocity_m_s * a["trace_time_seconds"] / .5)
                np.testing.assert_allclose(independent[:, 0], exact, rtol=1e-10, atol=1e-13)
            if name == "rock":
                rate = 100. * 1e-8 * (9810. * .4 * .01 - material.rock_critical_shear_pa)
                exact_mobile = rate / .01 * (1. - np.exp(-.01 * a["trace_time_seconds"]))
                np.testing.assert_allclose(independent[:, 0], exact_mobile, rtol=1e-10, atol=1e-13)
                np.testing.assert_allclose(independent[:, 2], rate * a["trace_time_seconds"], rtol=1e-10, atol=1e-13)
        if errors[1] >= errors[0] or errors[1] > .005:
            raise AssertionError((name, "time convergence", errors))

    domain, forcing, material, initial = benchmark("settling")
    failed = solve_sediment(domain, forcing, material, initial,
                            SedimentConfig(max_dt_seconds=.5, max_bed_change_m=1e-6))
    if failed["metadata"]["status"] != "failed_prefix":
        raise AssertionError("expected real bed-change failed prefix")
    save("bed_change_failed_prefix", failed)
    # A genuine nonzero prefix, rather than only a zero-step refusal.
    failed_later = solve_sediment(domain, forcing, material, initial,
                                  SedimentConfig(max_dt_seconds=.5, max_bed_change_m=1e-5))
    if failed_later["metadata"]["status"] != "failed_prefix" or failed_later["metadata"]["last_time_seconds"] <= 0.:
        raise AssertionError("expected nonzero morphology failure prefix")
    save("bed_change_later_failed_prefix", failed_later)

    gp = manifest["artifacts"]["td_fine"]
    geometry = load_channel_geometry(geometry_directory / gp["path"], expected_sha256=gp["sha256"],
                                     expected_identity=gp["identity_sha256"])
    a = geometry["arrays"]
    receiver, widths = a["receiver"], a["width_m"]
    points = a["node_xz_m"]
    n = len(receiver)
    edge_lengths = np.linalg.norm(points[1:] - points[:-1], axis=1)
    # Disjoint longitudinal controls: endpoint half-reaches, interior half of each adjacent reach.
    lengths = np.r_[edge_lengths[0] / 2., (edge_lengths[:-1] + edge_lengths[1:]) / 2., edge_lengths[-1] / 2.]
    bed = sample_saved_mesh(geometry, points)
    slope = np.r_[(bed[:-1] - bed[1:]) / edge_lengths, (bed[-2] - bed[-1]) / edge_lengths[-1]]
    network = ChannelNetwork(receiver.copy(), lengths.astype(float), widths.copy(), bed, slope,
                              np.full(n, .035), np.full(n, .25),
                              np.where(receiver < 0, "open_outflow", "interior"), geometry["identity_sha256"],
                              "explicit rectangular hydraulic section on accepted canonical M5 bed; banks external",
                              "uncalibrated Manning n=.035", receiver_distance_m=np.r_[edge_lengths, 0.])
    sp = manifest["td_source"]
    source = load_diagnostic_product(sp["path"], expected_sha256=sp["sha256"], expected_identity=sp["identity_sha256"])
    sa = source["arrays"]
    local = sa["local_q_m3_s"].reshape(len(sa["time_seconds"]) - 1, -1)[:, a["source_node_cell_ids"]].copy()
    water_forcing = ChannelForcing(sa["time_seconds"].copy(), local, source["identity_sha256"])
    water = solve_channel(network, water_forcing, widths * lengths * .01,
                          ChannelConfig(max_dt_seconds=.5))
    if water["metadata"]["status"] != "complete":
        raise AssertionError(water["metadata"])
    hydraulic = make_channel_product(network, water_forcing, water)
    waterpath = output / "td-new-geometry-water.npz"
    save_channel_product(waterpath, hydraulic)
    wa = water["arrays"]
    domain = SedimentDomain(receiver.copy(), widths * lengths, widths.copy(), bed.copy(), bed - .3,
                            widths * lengths * .002, np.zeros(n, bool), receiver == -1,
                            geometry["identity_sha256"], "M5 reach; 2mm initial alluvium within bed; rock floor .3m below; M5 cut exported separately")
    material = MaterialParameters(sediment_erodibility_m_s_pa=1e-8, rock_erodibility_m_s_pa=1e-10,
                                   transport_coefficient=1e-6, settling_velocity_m_s=.0001,
                                   provenance="explicit homogeneous TD scenario; not measured geological calibration")
    forcing = SedimentForcing(wa["time_seconds"].copy(), wa["volume_m3"][:-1].copy(),
                              wa["depth_m"][:-1].copy(), wa["outflow_q_m3_s"].copy(),
                              np.broadcast_to(slope, wa["outflow_q_m3_s"].shape).copy(),
                              np.zeros_like(wa["outflow_q_m3_s"]), hydraulic["identity_sha256"],
                              geometry["identity_sha256"], "exact pre-step saved water replay; once-only selected local sources; excluded external donors")
    initial_mobile = np.full(n, 1e-5)
    for label, dt in (("coarse", .5), ("fine", .125)):
        result = solve_sediment(domain, forcing, material, initial_mobile,
                                SedimentConfig(max_dt_seconds=dt, max_bed_change_m=.001))
        if result["metadata"]["status"] != "complete":
            raise AssertionError(result["metadata"])
        save("td_" + label, result)
    coarse, fine = products["td_coarse"]["arrays"], products["td_fine"]["arrays"]
    interpolated = np.column_stack([np.interp(coarse["trace_time_seconds"], fine["trace_time_seconds"],
                                             fine["trace_bed_elevation_m"][:, i]) for i in range(n)])
    bed_difference = float(np.max(np.abs(interpolated - coarse["trace_bed_elevation_m"])))
    export_difference = abs(cases["td_coarse"]["exported_solid_m3"] - cases["td_fine"]["exported_solid_m3"]) / max(
        cases["td_fine"]["exported_solid_m3"], 1e-12)
    if bed_difference > .001 or export_difference > .01:
        raise AssertionError(("TD sediment refinement", bed_difference, export_difference))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for axis, name in zip(axes[:2], ("settling_fine", "y_to_lake_fine")):
        data = products[name]["arrays"]
        axis.plot(data["trace_time_seconds"], data["trace_mobile_solid_m3"].sum(axis=1), label="mobile solid")
        axis.plot(data["trace_time_seconds"], data["trace_bed_alluvium_solid_m3"].sum(axis=1)
                  - data["trace_bed_alluvium_solid_m3"][0].sum(), label="bed solid change")
        axis.set_title(name)
        axis.set_ylabel("Solid volume (m3)")
        axis.legend()
    for name in ("td_coarse", "td_fine"):
        data = products[name]["arrays"]
        delta = data["trace_bed_elevation_m"] - data["domain_bed_elevation_m"]
        axes[2].plot(data["trace_time_seconds"], delta.min(axis=1) * 1000., label=name)
    axes[2].set_title("Real TD | maximum bed lowering")
    axes[2].set_ylabel("Bed change (mm)")
    axes[2].legend()
    for axis in axes:
        axis.set_xlabel("Physical time (s)")
        axis.grid(alpha=.2)
    fig.suptitle("M6 frozen-water replay; updated bed requires geometry and hydraulic revalidation")
    fig.tight_layout()
    fig.savefig(output / "sediment-preview.png", dpi=160)
    plt.close(fig)
    report = {"schema": "td-river-m6-verification-v1", "status": "accepted_bounded_sediment_replay",
              "artifacts": pins, "cases": cases,
              "geometry_manifest": {"path": str(geometry_directory / "acceptance.json"),
                                    "sha256": file_sha256(geometry_directory / "acceptance.json")},
              "td_geometry": gp | {"path": str(geometry_directory / gp["path"])},
              "td_water": {"path": waterpath.name, "sha256": file_sha256(waterpath),
                           "identity_sha256": hydraulic["identity_sha256"]},
              "td_bed_refinement_m": bed_difference, "td_export_refinement_relative": export_difference,
              "td_control_geometry": {"policy": "disjoint_endpoint_half_reaches_and_interior_adjacent_half_reaches",
                  "total_control_length_m": float(lengths.sum()), "total_centerline_length_m": float(edge_lengths.sum()),
                  "bed_area_policy": "rectangular_longitudinal_floor_controls_width_times_length; bank_morphology_excluded",
                  "water_initial_depth_m": .01, "alluvium_initial_thickness_m": .002, "rock_floor_offset_m": .3},
              "limitations": ["one_way_frozen_water_not_recoupled_hydraulics", "uncalibrated_material",
                              "M5_excavated_rock_not_automatically_mobile_sediment", "bounded_selected_TD_reach"],
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.geometry, args.output)
    print(json.dumps({"status": report["status"], "cases": len(report["artifacts"]),
                      "td_bed_refinement_m": report["td_bed_refinement_m"],
                      "td_export_refinement_relative": report["td_export_refinement_relative"]}, indent=2))


if __name__ == "__main__":
    main()
