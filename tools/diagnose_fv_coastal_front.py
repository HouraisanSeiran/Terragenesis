"""Replay a rejected sediment interval from archived live water and bed."""
import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from terrain_pipeline.surface_rivers.metric_fv_coastal_coupling import advance_coupled
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig, transport_bedload, reconstructed_face_hydraulics
from tools.run_natural_delta_fv_water import make_geometry
from tools.verify_fluvial_channel_remobilization import resource_limits


def run(parent, failed, output, *, interval=205, wave_height=.3, legacy_replay=None, duration_s=None):
    output.mkdir(parents=True, exist_ok=False)
    with np.load(parent / "result.npz") as saved:
        floor = saved["source_floor_m"].copy()
        types = saved["cell_type"].copy()
        fixed = saved["fixed_boundary_mask"].copy()
    with np.load(failed / "intervals" / f"{interval - 1:05d}-sediment.npz") as saved:
        bed = saved["bed_m"].copy()
    with np.load(failed / "intervals" / f"{interval - 1:05d}-water.npz") as saved:
        previous = {key: saved[key] for key in saved.files}
    with np.load(failed / "intervals" / f"{interval:05d}-first-substep.npz") as saved:
        witness = {key: saved[key] for key in saved.files}
    state = witness["state_before"]
    np.testing.assert_array_equal(previous["depth_after_m"], state[:, 0])
    np.testing.assert_array_equal(previous["momentum_after"], state[:, 1:])
    dt = float(previous["time_end_s"] - previous["time_start_s"])
    if duration_s is not None:
        dt = float(duration_s)
    geometry = make_geometry(bed.copy(), types, 5.)
    geometry["arrays"]["fixed_bed_cell"] = fixed.ravel()
    packets, witnesses = [], []
    result = advance_coupled(geometry, floor_m=floor, initial_depth_m=state[:, 0].reshape(bed.shape).copy(),
        initial_momentum_m2_s=state[:, 1:].copy(), source_m3_s=witness["forcing_m3_s"].reshape(bed.shape),
        sea_stage_provider=lambda index: witness["tailwater_m"], intervals=1, interval_s=dt,
        budget=SurfaceBudget(max_dt_s=1., max_duration_s=dt, max_snapshots=3),
        config=BedloadConfig(wave_height_m=0., mpm_coefficient=0.),
        interval_observer=lambda water, sediment: packets.append(water), momentum_observer=witnesses.append)
    np.testing.assert_allclose(witnesses[0]["rk1_internal_flux"], witness["rk1_internal_flux"], atol=2.e-11, rtol=2.e-12)
    packet = packets[0]
    np.savez_compressed(output / "replayed-water.npz", **packet)
    np.savez_compressed(output / "geometry.npz", bed_m=bed, floor_m=floor, cell_type=types, fixed_boundary_mask=fixed)
    config = BedloadConfig(wave_height_m=wave_height)
    diagnostic_transport = transport_bedload(bed, floor, geometry, packet, replace(config, max_bed_change_m=10.))
    np.savez_compressed(output / "diagnostic-large-ceiling-transport.npz", **{k: v for k, v in diagnostic_transport.items() if k != "ledger"})
    rejected = None
    try:
        sediment = transport_bedload(bed, floor, geometry, packet, config)
        np.savez_compressed(output / "replayed-sediment.npz", **{k: v for k, v in sediment.items() if k != "ledger"})
    except ValueError as error:
        rejected = str(error)
    a = geometry["arrays"]
    left, right = a["face_left"], a["face_right"]
    h = .5 * (packet["depth_before_m"] + packet["depth_after_m"])
    small = np.minimum(h[left], h[right])
    mean_stage = h + bed.ravel()
    crest = np.maximum(bed.ravel()[left], bed.ravel()[right])
    hl, hr = np.maximum(mean_stage[left] - crest, 0.), np.maximum(mean_stage[right] - crest, 0.)
    q = packet["internal_transfer_m3"] / dt
    thin_velocity = np.divide(q, 5. * small, out=np.zeros_like(q), where=small > config.dry_depth_m)
    reconstructed_depth = .5 * (hl + hr)
    reconstructed_velocity = np.divide(q, 5. * reconstructed_depth, out=np.zeros_like(q), where=reconstructed_depth > config.dry_depth_m)
    velocity = np.divide(packet["momentum_after"], packet["depth_after_m"][:, None],
        out=np.zeros_like(packet["momentum_after"]), where=packet["depth_after_m"][:, None] > 0.)
    order = np.argsort(abs(thin_velocity))[-10:][::-1]
    changed = diagnostic_transport["bed_m"] - bed
    change_cell = np.unravel_index(np.argmax(abs(changed)), bed.shape)
    change_flat = np.ravel_multi_index(change_cell, bed.shape)
    touching = np.flatnonzero((left == change_flat) | (right == change_flat))
    evidence = []
    for face in order:
        evidence.append({"face": int(face), "left_rc": list(map(int, np.unravel_index(left[face], bed.shape))),
            "right_rc": list(map(int, np.unravel_index(right[face], bed.shape))),
            "h_left_mean_m": float(h[left[face]]), "h_right_mean_m": float(h[right[face]]),
            "HLL_crest_m": float(crest[face]), "HLL_h_left_mean_m": float(hl[face]), "HLL_h_right_mean_m": float(hr[face]),
            "q_m3_s": float(q[face]), "old_thin_velocity_m_s": float(thin_velocity[face]),
            "mean_reconstructed_depth_velocity_m_s": float(reconstructed_velocity[face])})
    np.savez_compressed(output / "face-evidence.npz", mean_h_left_m=h[left], mean_h_right_m=h[right],
        reconstructed_h_left_m=hl, reconstructed_h_right_m=hr, old_thin_velocity_m_s=thin_velocity,
        mean_reconstructed_depth_velocity_m_s=reconstructed_velocity, mean_face_q_m3_s=q)
    report = {"replayed_from": str(failed), "interval": interval, "physical_interval_s": dt,
        "first_RK1_flux_matches_archived_failed_interval": True, "transport_rejected": rejected,
        "water_all_finite": bool(all(np.isfinite(value).all() for value in result["arrays"].values())),
        "water_min_depth_m": float(result["arrays"]["depth_m"].min()), "water_max_depth_m": float(result["arrays"]["depth_m"].max()),
        "water_max_cell_velocity_m_s": float(np.linalg.norm(velocity, axis=1).max()),
        "water_maximum_abs_ledger_residual_m3": float(abs(result["arrays"]["ledger"][:, -1]).max()),
        "old_max_face_velocity_m_s": float(abs(thin_velocity).max()),
        "mean_reconstructed_max_face_velocity_m_s": float(abs(reconstructed_velocity).max()),
        "largest_bed_change_cell_rc": list(map(int, change_cell)), "largest_bed_change_m": float(changed[change_cell]),
        "largest_change_cell_touching_faces": [{"face": int(face), "old_min_depth_m": float(small[face]),
            "Q_m3_s": float(q[face]), "old_normal_velocity_m_s": float(thin_velocity[face]),
            "mean_reconstructed_depth_m": float(reconstructed_depth[face]),
            "new_normal_velocity_m_s": float(reconstructed_velocity[face]),
            "transferred_solid_m3": float(diagnostic_transport["internal_transfer_solid_m3"][face])} for face in touching],
        "worst_thin_faces": evidence, "sediment_config": asdict(config)}
    if legacy_replay is not None:
        with np.load(legacy_replay / "diagnostic-large-ceiling-transport.npz") as saved:
            old_transport = saved["internal_transfer_solid_m3"].copy()
            old_bed = saved["bed_m"].copy()
        mean_momentum = .5 * (packet["momentum_before"] + packet["momentum_after"])
        cell_velocity = np.divide(mean_momentum, h[:, None], out=np.zeros_like(mean_momentum), where=h[:, None] > config.dry_depth_m)
        axes = np.r_[np.zeros(bed.shape[0] * (bed.shape[1] - 1), int), np.ones((bed.shape[0] - 1) * bed.shape[1], int)]
        old_velocity = .5 * (cell_velocity[left] + cell_velocity[right])
        old_velocity[np.arange(len(left)), axes] = thin_velocity
        old_shields = config.manning_s_m_third ** 2 * np.sum(old_velocity ** 2, axis=1) / (
            np.maximum(small, config.dry_depth_m) ** (1. / 3.) * (config.sediment_density_kg_m3 / config.water_density_kg_m3 - 1.) * config.grain_diameter_m)
        np.savez_compressed(output / "old-new-face-comparison.npz", old_depth_m=small,
            new_depth_m=diagnostic_transport["face_effective_depth_m"], old_velocity_m_s=thin_velocity,
            new_velocity_m_s=diagnostic_transport["face_normal_velocity_m_s"], old_current_shields=old_shields,
            new_current_shields=diagnostic_transport["face_current_shields"], old_transfer_solid_m3=old_transport,
            new_transfer_solid_m3=diagnostic_transport["internal_transfer_solid_m3"])
        old_front = int(np.argmax(abs(old_transport)))
        report["legacy_comparison"] = {"legacy_replay": str(legacy_replay), "worst_legacy_transfer_face": old_front,
            "old_max_abs_bed_change_m": float(abs(old_bed - bed).max()),
            "new_max_abs_bed_change_m": float(abs(changed).max()),
            "old_new_face_depth_m": [float(small[old_front]), float(diagnostic_transport["face_effective_depth_m"][old_front])],
            "old_new_face_velocity_m_s": [float(thin_velocity[old_front]), float(diagnostic_transport["face_normal_velocity_m_s"][old_front])],
            "old_new_current_shields": [float(old_shields[old_front]), float(diagnostic_transport["face_current_shields"][old_front])],
            "old_new_face_transfer_solid_m3": [float(old_transport[old_front]), float(diagnostic_transport["internal_transfer_solid_m3"][old_front])],
            "diagnostic_large_ceiling_semantics": "10m ceiling used only to measure unmodified full-step proposals; not an accepted production step"}
    (output / "diagnosis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--failed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=int, default=205)
    parser.add_argument("--wave-height", type=float, default=.3)
    parser.add_argument("--legacy-replay", type=Path)
    parser.add_argument("--duration-s", type=float)
    args = parser.parse_args()
    resource_limits()
    print(json.dumps(run(args.parent, args.failed, args.output, interval=args.interval,
        wave_height=args.wave_height, legacy_replay=args.legacy_replay, duration_s=args.duration_s), indent=2))
