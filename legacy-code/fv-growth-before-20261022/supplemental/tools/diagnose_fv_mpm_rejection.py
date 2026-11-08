"""Replay a short frozen v3 interval and capture the first refused MPM step."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
from types import FunctionType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from terrain_pipeline.surface_rivers import metric_fv_coastal_sediment as sediment
from terrain_pipeline.surface_rivers import metric_fv_growth_coupling_v3 as coupling
from terrain_pipeline.surface_rivers.metric_fv_exchange_v3 import ExchangeConfig
from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import SuspendedConfig
from tools.run_natural_delta_fv_water import make_geometry
from tools.run_natural_fv_growth_interval_v3 import forcing_step
from tools.run_natural_fv_growth_v3 import load_checkpoint


def diagnose(bed, floor, geometry, packet, config, stages, output, metadata):
    a = geometry["arrays"]
    dx = geometry["metadata"]["spacing_m"]
    dt = packet["time_end_s"] - packet["time_start_s"]
    # Read-only reconstruction of the refused proposal; never committed.
    proposed = sediment.transport_bedload(bed, floor, geometry, packet, replace(config, max_bed_change_m=1.e9))
    change = proposed["bed_m"] - bed
    worst = int(np.argmax(abs(change)))
    left, right = a["face_left"], a["face_right"]
    incident = np.flatnonzero((left == worst) | (right == worst))
    hydraulic = sediment.reconstructed_face_hydraulics(bed, geometry, packet, config.dry_depth_m)
    axes = hydraulic["face_axes"]
    face_h, face_u = hydraulic["face_effective_depth_m"], hydraulic["face_velocity_m_s"]
    h_sum = np.zeros_like(face_h)
    duration = 0.
    stage_details = []
    for index, stage in enumerate(stages):
        if stage["dt_s"] <= 0.:
            continue
        h_sum += .5 * stage["dt_s"] * stage["face_h"]
        duration += .5 * stage["dt_s"]
        stage_details.append({"rhs_call": index, "dt_s": stage["dt_s"],
            "faces": [{"face": int(face), "wet_thickness_m": float(stage["face_h"][face]),
                "mass_flux_m2_s": float(stage["mass_flux"][face]),
                "left_depth_m": float(stage["depth"][left[face]]),
                "right_depth_m": float(stage["depth"][right[face]])} for face in incident]})
    mean_h = h_sum / duration
    faces = []
    for face in incident:
        l, r = int(left[face]), int(right[face])
        details = {"face": int(face), "left": [int(value) for value in np.unravel_index(l, bed.shape)],
            "right": [int(value) for value in np.unravel_index(r, bed.shape)], "axis": int(axes[face]),
            "left_bed_m": float(bed.flat[l]), "right_bed_m": float(bed.flat[r]),
            "crest_m": float(a["face_crest_m"][face]),
            "left_depth_before_after_m": [float(packet[key][l]) for key in ("depth_before_m", "depth_after_m")],
            "right_depth_before_after_m": [float(packet[key][r]) for key in ("depth_before_m", "depth_after_m")],
            "left_velocity_before_after_m_s": [np.divide(packet[momentum][l], packet[depth][l],
                out=np.zeros(2), where=packet[depth][l] > config.dry_depth_m).tolist()
                for momentum, depth in [("momentum_before", "depth_before_m"), ("momentum_after", "depth_after_m")]],
            "right_velocity_before_after_m_s": [np.divide(packet[momentum][r], packet[depth][r],
                out=np.zeros(2), where=packet[depth][r] > config.dry_depth_m).tolist()
                for momentum, depth in [("momentum_before", "depth_before_m"), ("momentum_after", "depth_after_m")]],
            "endpoint_mean_wet_thickness_m": float(face_h[face]),
            "rk_time_mean_wet_thickness_m": float(mean_h[face]),
            "reconstructed_velocity_m_s": face_u[face].tolist(),
            "mean_mass_flux_m2_s": float(packet["internal_transfer_m3"][face] / dt / dx),
            "normal_velocity_using_rk_wet_mean_m_s": float(packet["internal_transfer_m3"][face] / dt / dx / max(mean_h[face], config.dry_depth_m)),
            "current_shields": float(proposed["face_current_shields"][face]),
            "accepted_solid_transfer_m3": float(proposed["internal_transfer_solid_m3"][face])}
        faces.append(details)
    captured = {"bed_m": bed.copy(), "floor_m": floor.copy(), "proposed_change_m": change}
    captured.update({"packet_" + key: value for key, value in packet.items()})
    captured.update({"geometry_" + key: value for key, value in a.items()})
    captured.update({"hydraulics_" + key: value for key, value in hydraulic.items()})
    captured["rk_time_mean_wet_thickness_m"] = mean_h
    captured["bedload_internal_transfer_solid_m3"] = proposed["internal_transfer_solid_m3"]
    for index, stage in enumerate(stages):
        captured.update({f"rhs_{index:03d}_" + key: value for key, value in stage.items()})
    np.savez_compressed(output / "rejected-input-and-proposal.npz", **captured)
    report = {"checkpoint": metadata, "physical_time_start_s": metadata["physical_time_s"] + packet["time_start_s"],
        "physical_time_end_s": metadata["physical_time_s"] + packet["time_end_s"], "interval_s": dt,
        "maximum_bed_change_m": float(abs(change).max()), "worst_cell": [int(value) for value in np.unravel_index(worst, bed.shape)],
        "signed_bed_change_m": float(change.flat[worst]), "worst_cell_inventory_solid_m3": float((bed.flat[worst] - floor.flat[worst]) * dx ** 2 * (1. - config.porosity)),
        "maximum_face_current_shields": float(proposed["face_current_shields"].max()),
        "maximum_face_velocity_m_s": float(np.linalg.norm(face_u, axis=1).max()),
        "faces_at_worst_cell": faces, "rhs_stages_at_worst_cell": stage_details,
        "rk_integrated_duration_s": duration, "bedload_config": asdict(config),
        "scope": "Refused MPM proposal reconstructed without committing water, bed or source cursor."}
    (output / "rejection.json").write_text(json.dumps(report, indent=2, default=lambda value: value.tolist()), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("physical_time_end_s", "maximum_bed_change_m", "worst_cell", "maximum_face_velocity_m_s")}, default=lambda value: value.tolist()), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--parameters-from", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-s", type=float, default=.0625)
    parser.add_argument("--duration-s", type=float, default=4.)
    parser.add_argument("--captured-input", type=Path)
    args = parser.parse_args()
    data, metadata = load_checkpoint(args.checkpoint)
    parameters = json.loads(args.parameters_from.read_text(encoding="utf-8"))["parameters"]
    count = round(args.duration_s / args.interval_s)
    if count < 1 or not np.isclose(count * args.interval_s, args.duration_s):
        raise ValueError("duration must be an integer number of positive intervals")
    args.output.mkdir(parents=True, exist_ok=False)
    if args.captured_input:
        with np.load(args.captured_input, allow_pickle=False) as saved:
            packet = {key[7:]: saved[key] for key in saved.files if key.startswith("packet_")}
            domain = {"arrays": {key[9:]: saved[key] for key in saved.files if key.startswith("geometry_")},
                "metadata": {"spacing_m": 5.}}
            indices = sorted({key[4:7] for key in saved.files if key.startswith("rhs_")})
            stages = [{key[8:]: saved[key] for key in saved.files if key.startswith("rhs_" + index + "_")} for index in indices]
            config = sediment.BedloadConfig(wave_height_m=parameters["wave_height"], wave_period_s=parameters["wave_period"], max_bed_change_m=parameters["max_bed_change"])
            diagnose(saved["bed_m"], saved["floor_m"], domain, packet, config, stages, args.output, metadata)
        return
    loads, flows, cursor = [], [], metadata["source_cursor_s"]
    for _ in range(count):
        load, flow, cursor = forcing_step(data["source_schedule"], cursor, args.interval_s,
            parameters["source_time_scale"], parameters["max_input_concentration"], parameters["river_q"], parameters["supply_off"])
        loads.append(load)
        flows.append(flow)
    phase = 2. * np.pi * (metadata["physical_time_s"] + np.arange(count) * args.interval_s) / parameters["tide_period"] + np.deg2rad(parameters["tide_phase"])
    seas = parameters["sea_mean"] + parameters["tide_amplitude"] * np.sin(phase)
    geometry = make_geometry(data["bed_m"].copy(), data["cell_type"], 5.)
    geometry["arrays"]["fixed_bed_cell"] = data["fixed_boundary_mask"].ravel()
    stages = []
    successful = []

    def witness_rhs(state, relative_bed, **kwargs):
        result, witness = coupling.shallow_water_rhs(state, relative_bed, **kwargs)
        a = geometry["arrays"]
        flat_bed = a["H2_m"].ravel()
        left, right = a["face_left"], a["face_right"]
        stage = flat_bed + state[:, 0]
        face_h = .5 * (np.maximum(stage[left] - a["face_crest_m"], 0.) + np.maximum(stage[right] - a["face_crest_m"], 0.))
        stages.append({"dt_s": kwargs["dt"], "face_h": face_h,
            "mass_flux": witness["internal_flux"][:, 0].copy(), "depth": state[:, 0].copy()})
        return result, witness

    def capture_transport(bed, floor, domain, packet, config):
        try:
            return sediment.transport_bedload(bed, floor, domain, packet, config)
        except sediment.MorphodynamicStepTooLarge:
            diagnose(bed, floor, domain, packet, config, stages, args.output, metadata)
            raise

    def committed(packet, bedload, suspended, ledger):
        successful.append({"interval": packet["interval"], "time_end_s": packet["time_end_s"],
            "mpm_peak_m": bedload["ledger"]["maximum_abs_bed_change_m"], "net_peak_m": ledger["maximum_bed_change_m"]})
        stages.clear()

    private_advance = FunctionType(coupling.advance_growth.__code__, dict(coupling.advance_growth.__globals__,
        shallow_water_rhs=witness_rhs, transport_bedload=capture_transport), name="diagnostic_advance")
    private_advance.__kwdefaults__ = coupling.advance_growth.__kwdefaults__
    config = sediment.BedloadConfig(wave_height_m=parameters["wave_height"], wave_period_s=parameters["wave_period"], max_bed_change_m=parameters["max_bed_change"])
    status = "no-rejection-in-requested-window"
    try:
        private_advance(geometry, floor_m=data["source_floor_m"], depth_m=data["depth_m"],
            momentum_m2_s=data["momentum_m2_s"], suspended_solid_m3=data["suspended_solid_m3"],
            river_q_m3_s=flows, input_solid_m3=loads, sea_stages_m=seas,
            inlet_cells=np.flatnonzero(data["cell_type"][0] == 1), interval_s=args.interval_s,
            budget=SurfaceBudget(max_dt_s=1., max_snapshots=count + 2, max_duration_s=args.duration_s,
                max_wall_s=300., max_bytes=768 * 1024 ** 2), bedload_config=config,
            suspended_config=SuspendedConfig(settling_velocity_m_s=parameters["settling_velocity"], max_bed_change_m=parameters["max_bed_change"]),
            exchange_config=ExchangeConfig(**metadata["exchange_config"]), interval_observer=committed)
    except sediment.MorphodynamicStepTooLarge as error:
        status = str(error)
    (args.output / "replay.json").write_text(json.dumps({"status": status, "checkpoint": str(args.checkpoint),
        "parameters_from": str(args.parameters_from), "interval_s": args.interval_s, "duration_s": args.duration_s,
        "successful_intervals_in_uncommitted_diagnostic": successful, "checkpoint_cursor_s": metadata["source_cursor_s"]}, indent=2), encoding="utf-8")
    print(status, flush=True)


if __name__ == "__main__":
    main()
