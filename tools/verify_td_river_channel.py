"""Independent analytical and small real-TD M3 channel verification."""

import argparse
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_channel_solver import solve_channel
from terrain_pipeline.surface_rivers.metric_channel_product import (
    load_channel_product, make_channel_product, sample_channel_output, save_channel_product,
    save_channel_output,
)
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product


THRESHOLDS = {"ode_relative_volume_error": .005, "characteristic_delay_relative_error": .05,
              "characteristic_peak_relative_error": .10, "td_depth_refinement_m": .001,
              "td_outlet_relative_refinement": .01, "scaled_mass_residual": 1e-8}


def network(receiver, lengths, widths, slopes, *, bed=None, source="a" * 64, kinds=None):
    receiver = np.asarray(receiver, dtype=np.int64)
    n = receiver.size
    return ChannelNetwork(
        receiver=receiver, length_m=np.broadcast_to(lengths, (n,)).astype(np.float64).copy(),
        width_m=np.broadcast_to(widths, (n,)).astype(np.float64).copy(),
        bed_elevation_m=np.zeros(n) if bed is None else np.asarray(bed, dtype=np.float64),
        bed_slope=np.broadcast_to(slopes, (n,)).astype(np.float64).copy(),
        roughness=np.full(n, .035), max_depth_m=np.full(n, 10.),
        terminal_kind=np.where(receiver >= 0, "interior", "open_outflow") if kinds is None else np.asarray(kinds),
        source_identity_sha256=source,
        section_source="explicit_rectangular_benchmark_or_TD_scenario_not_render_width",
        roughness_source="explicit_uncalibrated_Manning_n_0.035_scenario")


def reference_q(net, volume):
    area = volume / net.length_m
    depth = area / net.width_m
    hydraulic_radius = area / (net.width_m + 2. * depth)
    q = area * hydraulic_radius ** (2. / 3.) * np.sqrt(net.bed_slope) / net.roughness
    return np.where((net.receiver >= 0) | (net.terminal_kind == "open_outflow"), q, 0.)


def ode_reference(net, forcing, initial, times):
    """DOP853 independent integration, restarted at each prescribed discontinuity."""
    result = np.empty((len(times), net.receiver.size), np.float64)
    result[0] = initial
    state = initial.copy()
    for interval, (start, end) in enumerate(zip(forcing.time_seconds[:-1], forcing.time_seconds[1:])):
        def rhs(_, volume):
            q = reference_q(net, np.maximum(volume, 0.))
            incoming = np.bincount(net.receiver[net.receiver >= 0],
                                   weights=q[net.receiver >= 0], minlength=len(q))
            return forcing.local_q_m3_s[interval] + incoming - q
        reference = solve_ivp(rhs, (start, end), state, method="DOP853", rtol=2e-12, atol=2e-13,
                              dense_output=True, max_step=2.)
        if not reference.success:
            raise AssertionError(reference.message)
        selected = np.flatnonzero((times > start) & (times <= end))
        result[selected] = reference.sol(times[selected]).T
        state = reference.y[:, -1]
    return result


def budget(result, net):
    arrays = result["arrays"]
    dt = np.diff(arrays["time_seconds"])
    incoming = float(np.sum(arrays["local_q_m3_s"] * dt[:, None]))
    outgoing = float(np.sum(arrays["boundary_outflow_volume_m3"]))
    change = float(np.sum(arrays["volume_m3"][-1] - arrays["volume_m3"][0]))
    residual = incoming - outgoing - change
    max_local = float(np.max(np.abs(arrays["balance_residual_m3"]), initial=0.))
    if abs(residual) > THRESHOLDS["scaled_mass_residual"] * max(1., incoming):
        raise AssertionError("global channel mass residual exceeds fixed threshold")
    if result["metadata"]["status"] != "complete":
        raise AssertionError(result["metadata"])
    return {"input_m3": incoming, "boundary_outflow_m3": outgoing, "storage_change_m3": change,
            "residual_m3": residual, "max_local_residual_m3": max_local,
            "steps": len(dt), "max_cfl": float(np.max(arrays["cfl_number"], initial=0.)),
            "max_depth_m": float(arrays["depth_m"].max())}


def verification(directory, output):
    started = time.perf_counter()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases, pins = {}, {}

    def save(name, net, forcing, result):
        product = make_channel_product(net, forcing, result)
        path = output / (name + ".npz")
        save_channel_product(path, product)
        pin = {"path": path.name, "sha256": file_sha256(path), "identity_sha256": product["identity_sha256"]}
        loaded = load_channel_product(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        pins[name] = pin
        return loaded

    # High-order ODE checks include dry startup, finite storage, and a confluence.
    for name, receiver in (("single_ode", [-1]), ("y_ode", [2, 2, -1])):
        net = network(receiver, 50., 3., .005)
        q = np.zeros((2, len(receiver)))
        q[0, 0] = .2
        if len(receiver) == 3:
            q[0, 1] = .1
        forcing = ChannelForcing(np.array([0., 60., 240.]), q, "b" * 64)
        results, errors = [], []
        for label, dt in (("coarse", .5), ("fine", .125)):
            result = solve_channel(net, forcing, config=ChannelConfig(max_dt_seconds=dt))
            reference = ode_reference(net, forcing, np.zeros(len(receiver)), result["arrays"]["time_seconds"])
            error = float(np.max(np.abs(result["arrays"]["volume_m3"] - reference))) / max(1., float(reference.max()))
            errors.append(error)
            results.append(result)
            save(name + "_" + label, net, forcing, result)
        if not errors[1] < errors[0] or errors[1] > THRESHOLDS["ode_relative_volume_error"]:
            raise AssertionError((name, errors))
        cases[name] = {"coarse_relative_volume_error": errors[0], "fine_relative_volume_error": errors[1],
                       "reference": "scipy_DOP853_2e-12_restarted_at_forcing_discontinuities",
                       **budget(results[-1], net)}

    # Small perturbations about steady flow have analytical characteristic delay.
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for axis, name in zip(axes, ("single_characteristic", "y_characteristic")):
        if name.startswith("single"):
            receiver = np.r_[np.arange(1, 120), -1]
            widths = np.full(120, 5.)
            inlets, output_node = [0], 119
        else:
            receiver = np.r_[np.arange(1, 60), 120, np.arange(61, 120), 120, np.arange(121, 180), -1]
            widths = np.r_[np.full(120, 5.), np.full(60, 10.)]
            inlets, output_node = [0, 60], 179
        net = network(receiver, 5., widths, .002)
        initial = widths * .2 * net.length_m
        steady_q = reference_q(net, initial)
        if len(inlets) == 2:
            # Equal branch Q and exact rectangular downstream section set steady continuity.
            branch_q = float(steady_q[0])
            target_q = 2. * branch_q
            depth = brentq(lambda h: float(reference_q(net, np.r_[initial[:120], np.full(60, 10. * h * 5.)])[-1]) - target_q,
                           1e-6, 2., xtol=1e-14)
            initial[120:] = 10. * depth * 5.
            steady_q = reference_q(net, initial)
        area = initial / net.length_m
        depth = area / widths
        speed = steady_q / area * (5. / 3. - 4. * depth / (3. * (widths + 2. * depth)))
        expected_delay = float(np.sum(net.length_m / speed)) if len(inlets) == 1 else float(
            np.sum(net.length_m[:60] / speed[:60]) + np.sum(net.length_m[120:] / speed[120:]))
        end = float(np.ceil((expected_delay + 600. + 600.) / 5.) * 5.)
        times = np.arange(0., end + 1., 5.)
        forcing_q = np.zeros((len(times) - 1, len(receiver)))
        amplitude = steady_q[0] * .001
        pulse = np.zeros(len(times) - 1)
        wet = times[:-1] < 600.
        pulse[wet] = amplitude * 600. / (np.pi * 5.) * (
            np.cos(np.pi * times[:-1][wet] / 600.) - np.cos(np.pi * times[1:][wet] / 600.))
        for inlet in inlets:
            forcing_q[:, inlet] = steady_q[inlet] + pulse
        forcing = ChannelForcing(times, forcing_q, "c" * 64)
        result = solve_channel(net, forcing, initial, ChannelConfig(max_dt_seconds=2.))
        arrays = result["arrays"]
        dt = np.diff(arrays["time_seconds"])
        midpoints = (arrays["time_seconds"][:-1] + arrays["time_seconds"][1:]) / 2.
        perturbation = np.maximum(arrays["outflow_q_m3_s"][:, output_node] - steady_q[output_node], 0.)
        signal_volume = float(np.sum(perturbation * dt))
        centroid = float(np.sum(perturbation * dt * midpoints) / signal_volume)
        measured_delay = centroid - 300.
        peak = float(perturbation.max())
        expected_peak = len(inlets) * amplitude
        delay_error = abs(measured_delay - expected_delay) / expected_delay
        peak_error = abs(peak - expected_peak) / expected_peak
        if delay_error > THRESHOLDS["characteristic_delay_relative_error"] or peak_error > THRESHOLDS["characteristic_peak_relative_error"]:
            raise AssertionError((name, delay_error, peak_error))
        cases[name] = {"expected_characteristic_delay_s": expected_delay, "measured_centroid_delay_s": measured_delay,
                       "delay_relative_error": delay_error, "expected_perturbation_peak_m3_s": expected_peak,
                       "measured_perturbation_peak_m3_s": peak, "peak_relative_error": peak_error,
                       "linearization_relative_pulse_amplitude": .001,
                       "control_length_m": 5., "control_count": len(receiver),
                       "reference": "linearized_exact_rectangular_Manning_characteristic",
                       **budget(result, net)}
        save(name, net, forcing, result)
        axis.plot(midpoints, perturbation, label="Numerical outlet perturbation", color="#1677b8")
        expected = np.where((midpoints >= expected_delay) & (midpoints <= expected_delay + 600.),
                            expected_peak * np.sin(np.pi * (midpoints - expected_delay) / 600.), 0.)
        axis.plot(midpoints, expected, "--", label="Analytical characteristic", color="#c03e5a")
        axis.set_title(name.replace("_", " "))
        axis.set_xlabel("Physical time (s)")
        axis.set_ylabel("Perturbation Q (m3/s)")
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "analytical-pulse-reference.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("Analytical benchmarks accepted; starting bounded saved-TD event", flush=True)

    # Validate and consume the existing full source product once; no new TD inference or routing.
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    source_pin = manifest["artifacts"]["product"]
    source = load_diagnostic_product(directory / source_pin["path"], expected_sha256=source_pin["sha256"],
                                     expected_identity=source_pin["identity_sha256"])
    data = source["arrays"]
    receiver, slope, order = data["graph_receiver"], data["graph_edge_slope"], data["graph_order_downstream_first"]
    size = np.zeros(len(receiver), np.int64)
    size[(receiver < 0) & (data["graph_outlet_kind"] == "open_outflow")] = 1
    for cell in order:
        target = receiver[cell]
        if target >= 0 and slope[cell] > 0. and size[target] > 0:
            size[cell] = size[target] + 1
    cell = int(size.argmax())
    selected = [cell]
    while receiver[cell] >= 0:
        cell = int(receiver[cell])
        selected.append(cell)
    # Last 96 controls end at an actual known open terminal; external donors are excluded explicitly.
    selected = np.asarray(selected[-96:], np.int64)
    n = len(selected)
    physical_lengths = data["graph_edge_length_m"][selected].copy()
    physical_slopes = slope[selected].copy()
    physical_lengths[-1] = physical_lengths[-2]
    physical_slopes[-1] = physical_slopes[-2]
    net = network(np.r_[np.arange(1, n), -1], physical_lengths, 3., physical_slopes,
                  bed=data["elevation_m"].ravel()[selected], source=source["identity_sha256"])
    forcing = ChannelForcing(data["time_seconds"].copy(),
                             data["local_q_m3_s"].reshape(3, -1)[:, selected].copy(), source["identity_sha256"])
    results = []
    for name, dt in (("td_coarse", 2.), ("td_fine", .5)):
        result = solve_channel(net, forcing, config=ChannelConfig(max_dt_seconds=dt))
        results.append(result)
        product = save(name, net, forcing, result)
        dense = sample_channel_output(product, np.arange(0., 901., 30.))
        sparse = sample_channel_output(product, np.array([0., 900.]))
        # Compare numerical trace terminal volume and sampler cumulative boundary integral.
        da, sa = dense["arrays"], sparse["arrays"]
        np.testing.assert_array_equal(da["volume_m3"][-1], sa["volume_m3"][-1])
        cumulative_keys = [key for key in da if "cumulative" in key and "out" in key]
        if not cumulative_keys:
            raise AssertionError("sampler must expose cumulative boundary outflow")
        for key in cumulative_keys:
            np.testing.assert_allclose(da[key][-1], sa[key][-1], rtol=1e-12, atol=1e-10)
        for label, sampled in (("dense", dense), ("sparse", sparse)):
            path = output / (name + "_" + label + ".npz")
            save_channel_output(path, sampled)
            pins[name + "_" + label] = {"path": path.name, "sha256": file_sha256(path),
                                        "identity_sha256": sampled["identity_sha256"],
                                        "source_product": name, "artifact_kind": "sampled_output"}
        cases[name] = {**budget(result, net), "dense_sparse_same_terminal_state": True,
                       "dense_sparse_same_cumulative_outflow": True}
    coarse, fine = results
    coarse_a, fine_a = coarse["arrays"], fine["arrays"]
    interpolated = np.column_stack([np.interp(coarse_a["time_seconds"], fine_a["time_seconds"], fine_a["depth_m"][:, i])
                                    for i in range(n)])
    depth_difference = float(np.max(np.abs(coarse_a["depth_m"] - interpolated)))
    coarse_out = cases["td_coarse"]["boundary_outflow_m3"]
    fine_out = cases["td_fine"]["boundary_outflow_m3"]
    outlet_relative_difference = abs(coarse_out - fine_out) / max(abs(fine_out), 1e-12)
    if depth_difference > THRESHOLDS["td_depth_refinement_m"] or outlet_relative_difference > THRESHOLDS["td_outlet_relative_refinement"]:
        raise AssertionError((depth_difference, outlet_relative_difference))
    selected_pin = {"source_manifest_path": str(directory / "manifest.json"), "source_product": source_pin,
                    "source_sha256": manifest["source_sha256"],
                    "routing_identity_sha256": source["metadata"]["routing_identity_sha256"],
                    "selected_cell_ids": selected.tolist(), "selection": "last_up_to_96_nodes_of_longest_strictly_downhill_original_D8_path_to_explicit_open_terminal",
                    "local_source_policy": "selected_cell_local_release_only_once; all_unselected_cell_release_excluded",
                    "off_channel_transport": "not_simulated_no_instantaneous_preaccumulated_Q",
                    "terminal_geometry": "one_control_length_and_free_outflow_slope_copied_explicitly_from_last_real_edge",
                    "section": {"width_m": 3., "depth_limit_m": 10., "roughness": .035, "calibrated": False},
                    "selected_length_m": float(physical_lengths.sum()),
                    "all_history_max_depth_difference_m": depth_difference,
                    "cumulative_outlet_relative_difference": outlet_relative_difference}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    cols = data["elevation_m"].shape[1]
    rows = selected // cols
    columns = selected % cols
    r0, r1 = max(0, int(rows.min()) - 8), min(data["elevation_m"].shape[0], int(rows.max()) + 9)
    c0, c1 = max(0, int(columns.min()) - 8), min(cols, int(columns.max()) + 9)
    axes[0].imshow(data["elevation_m"][r0:r1, c0:c1], extent=(c0-.5, c1-.5, r1-.5, r0-.5), cmap="terrain")
    axes[0].plot(columns, rows, color="#086cbd", linewidth=1.4)
    axes[0].scatter(columns[-1], rows[-1], c="#c92e58", s=20)
    axes[0].set_title(f"Real TD original-bed D8: {n} controls")
    axes[0].set_xlabel("Native 30 m grid column")
    axes[0].set_ylabel("Native 30 m grid row")
    for name, result in zip(("2 s maximum step", "0.5 s maximum step"), results):
        a = result["arrays"]
        axes[1].plot(a["time_seconds"], a["outflow_end_q_m3_s"][:, -1], label=name)
        axes[2].plot(a["time_seconds"], a["volume_m3"].sum(axis=1), label=name)
    axes[1].set_title("Instantaneous open-terminal Q")
    axes[1].set_ylabel("Q (m3/s)")
    axes[2].set_title("Actual channel storage")
    axes[2].set_ylabel("Volume (m3)")
    for axis in axes[1:]:
        axis.set_xlabel("Physical time (s)")
        axis.legend(fontsize=8)
        axis.grid(alpha=.2)
    fig.suptitle("M3 bounded TD scenario: selected-cell local release only; explicit uncalibrated 3 m section")
    fig.tight_layout(rect=(0., 0., 1., .91))
    fig.savefig(output / "td-channel-event.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    report = {"schema": "td-river-m3-verification-v1", "status": "accepted_bounded_kinematic_baseline",
              "thresholds": THRESHOLDS, "cases": cases, "artifacts": pins, "td_selection": selected_pin,
              "elapsed_seconds": time.perf_counter() - started,
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
              "limitations": ["no_backwater_or_reverse_flow", "no_lake_stage_spill_coupling", "rectangular_uncalibrated_section",
                              "finite_volume_spatial_diffusion", "no_natural_centerline_claim", "partial_local_TD_input"]}
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verification(args.input, args.output)
    except Exception as error:
        if args.output.is_dir() and not (args.output / "rejection.json").exists():
            publish_bytes(args.output / "rejection.json", json.dumps({"status": "rejected",
                "error_type": type(error).__name__, "reason": str(error), "thresholds": THRESHOLDS}, indent=2).encode("utf-8"))
        raise
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
