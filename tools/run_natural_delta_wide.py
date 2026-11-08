"""Independent wide-inlet finite-source counterfactual; never resumes old bed."""
import argparse
from dataclasses import asdict
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_natural_delta import NaturalDeltaConfig
from terrain_pipeline.surface_rivers.metric_fluvial_native_routers import initialize_source_limited_routers
from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import WaterRoutingRepair, mask_inlet_upstream_weights
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step, phase_record
from tools.run_natural_delta import load_forcing, IMPLEMENTATIONS
from tools.verify_fluvial_channel_remobilization import resource_limits

MATERIAL_REFERENCE = ROOT / "verification/fluvial-delta/natural-td-local-20261018-02"


def material_reference():
    summary = json.loads((MATERIAL_REFERENCE / "summary.json").read_text(encoding="utf-8"))
    with np.load(MATERIAL_REFERENCE / "result.npz") as saved:
        first_flow = float(saved["schedule"][0, 2])
    config = summary["config"]
    speed = first_flow / (config["inlet_width_m"] * config["inlet_depth_m"])
    thresholds = {"U_dep_mud": .3 * speed, "U_ero_mud": 1.5 * speed, "U_ero_sand": 1.05 * speed}
    return thresholds, {"reference_summary": str(MATERIAL_REFERENCE / "summary.json"),
        "reference_summary_sha256": file_sha256(MATERIAL_REFERENCE / "summary.json"),
        "reference_result_sha256": file_sha256(MATERIAL_REFERENCE / "result.npz"),
        "reference_initial_u0_m_s": speed, "native_2_3_0_coefficients": [.3, 1.5, 1.05],
        "absolute_thresholds_m_s": thresholds,
        "policy": "preserve original TD02 absolute thresholds for every router rebuild; new inlet u0 still enters native sand capacity"}


def apply_inlet_stage(model, stage_m):
    model.stage[0, model.inlet] = stage_m
    model.depth[0, model.inlet] = np.maximum(model.stage[0, model.inlet] - model.eta[0, model.inlet], 0.)


def initial_discharge_guess(depth, inlet, flow_m3_s, *, dx_m=5., dry_depth_m=.01):
    """One-time downstream routing guess, not a solved water or momentum field."""
    depth = np.asarray(depth, float)
    inlet = np.asarray(inlet, int)
    if (depth.ndim != 2 or not np.isfinite(depth).all() or np.any(depth < 0.)
            or not np.isfinite(flow_m3_s) or flow_m3_s <= 0. or dx_m <= 0.
            or len(inlet) < 3 or np.any(depth[0, inlet] <= dry_depth_m)):
        raise ValueError("finite nonnegative depth, positive Q and wet inlet required")
    weights = np.where(depth > dry_depth_m, depth, 0.)
    totals = weights.sum(axis=1)
    if np.any(totals <= 0.):
        raise ValueError("initial directional guess requires a wet path at each section")
    qx = (flow_m3_s / dx_m) * weights / totals[:, None]
    qx[0] = 0.
    qx[0, inlet] = flow_m3_s / (len(inlet) * dx_m)
    return qx.astype(np.float32)


def execute(initialization, geometry_report, schedule, output, *, steps=8, zero_supply=False, progress=None, initialize_only=False):
    if importlib.metadata.version("pyDeltaRCM") != "2.3.0":
        raise ValueError("pyDeltaRCM 2.3.0 required")
    import pyDeltaRCM
    config = NaturalDeltaConfig(shape=(220, 240), inlet_depth_m=4., land_length_m=10., routing_dry_depth_m=.01)
    initial = initialization["initial_bed_m"].astype(np.float32)
    floor = initial.astype(float) - config.erodible_cover_m
    floor[initialization["fixed_boundary_mask"]] = initial[initialization["fixed_boundary_mask"]]
    inlet_stage = float(np.float32(geometry_report["inlet"]["stage_m"]))
    thresholds, materials = material_reference()
    first_flow = float(schedule[0, 2])
    initial_depth = np.maximum(initialization["initial_stage_m"].astype(np.float32) - initial, 0.)
    initial_qx = initial_discharge_guess(initial_depth, initialization["inlet_columns"], first_flow)
    wet = initial_depth > config.routing_dry_depth_m
    initial_flow_report = {"algorithm": "one-time-depth-weighted-downstream-section-normalization-v1",
        "role": "numerical initial routing direction guess; not solved steady flow, FV momentum or prescribed branches",
        "q_m3_s": first_flow, "wet_threshold_m": config.routing_dry_depth_m,
        "wet_cells": int(wet.sum()),
        "interior_wet_cells_without_downstream_guess": int(np.count_nonzero(wet[1:] & (initial_qx[1:] <= 0.))),
        "dry_cells_with_nonzero_guess": int(np.count_nonzero(~wet & (initial_qx != 0.))),
        "section_q_m3_s": (initial_qx.astype(float).sum(axis=1) * 5.).tolist(),
        "maximum_section_q_error_m3_s": float(abs(initial_qx.astype(float).sum(axis=1) * 5. - first_flow).max()),
        "lateral_initial_q_is_zero": True, "applied_each_timestep": False,
        "row0_policy": "only configured native inlet columns, Q divided by exact represented width",
        "interior_policy": "all native-wet cells, depth weights normalized independently per section; interior evolves freely"}
    count = min(steps, len(schedule))
    if count < 1 or output.exists():
        raise ValueError("positive steps and a new output directory required")
    output.mkdir(parents=True, exist_ok=False)

    class WideModel(pyDeltaRCM.DeltaModel):
        def init_output_infrastructure(self):
            self._user_dict["out_dir"] = str(output / "backend")
            super().init_output_infrastructure()

        def hook_after_create_domain(self):
            self.eta[:] = initial
            self.eta0[:] = initial
            self.eta_init[:] = initial
            self.cell_type[:] = initialization["cell_type"]
            self.inlet = initialization["inlet_columns"].copy()
            if self.N0 != len(self.inlet) or self.L0 != 2:
                raise ValueError("native inlet width or short stub differs from initialization")
            self.source_floor = floor.copy()
            self.stage[:] = initialization["initial_stage_m"]
            self.depth[:] = np.maximum(self.stage - self.eta, 0.)
            self.qx[:] = initial_qx
            self.qy[:] = 0.
            self.qw[:] = np.hypot(self.qx, self.qy)
            self.ux[:] = np.divide(self.qx, self.depth, out=np.zeros_like(self.qx), where=self.depth > 0.)
            self.uy[:] = 0.
            self.uw[:] = abs(self.ux)
            self.phase_records = []
            self.dry_depth = config.routing_dry_depth_m

        def init_sediment_routers(self):
            for name, value in thresholds.items():
                setattr(self, name, value)
            initialize_source_limited_routers(self, self.source_floor, quantized_native_exchange=True)

        def get_water_weight_array(self):
            super().get_water_weight_array()
            mask_inlet_upstream_weights(self.water_weights, self.jwalk_flat, self.cell_type)

        def account_water_relocation_segment(self, *args, **kwargs):
            super().update_Q(*args, **kwargs)

        def init_water_iteration(self):
            apply_inlet_stage(self, inlet_stage)
            super().init_water_iteration()
            self.water_repair.begin(self)

        def run_water_iteration(self):
            with self.water_repair.native_loop_calls(self):
                super().run_water_iteration()
            self.water_repair.finish()

        def finalize_water_iteration(self, iteration):
            apply_inlet_stage(self, inlet_stage)
            super().finalize_water_iteration(iteration)

        def update_Q(self, dist, current_inds, next_inds, astep, jstep, istep, update_current=False, update_next=False):
            if update_current and update_next:
                self.water_repair.adjacent(self, current_inds, next_inds)
            super().update_Q(dist, current_inds, next_inds, astep, jstep, istep, update_current, update_next)

        def check_for_boundary(self, indices):
            result = super().check_for_boundary(indices)
            self.water_repair.boundary(indices, result)
            return result

        def record(self, before, phase, injected=0., exported=0., lost=0., correction=0.):
            if np.min(self.eta.astype(float) - self.source_floor) < -2.e-6:
                raise ValueError("source floor breached during " + phase)
            row = phase_record(before, self.eta, phase=phase, step_index=self.time_iter, dx_m=5.,
                injected_bulk_m3=injected, exported_bulk_m3=exported, lost_bulk_m3=lost, inlet_correction_bulk_m3=correction)
            self.phase_records.append({key: value for key, value in row.items() if not isinstance(value, np.ndarray)})

        def route_all_sand_parcels(self):
            before = self.eta.copy()
            super().route_all_sand_parcels()
            self.record(before, "sand", int(self._Np_sed * self._f_bedload) * self.Vp_sed, self._sr.Vp_exported, self._sr.Vp_lost)

        def route_all_mud_parcels(self):
            before = self.eta.copy()
            super().route_all_mud_parcels()
            self.record(before, "mud", int(self._Np_sed * (1. - self._f_bedload)) * self.Vp_sed, self._mr.Vp_exported, self._mr.Vp_lost)

        def topo_diffusion(self):
            before = self.eta.copy()
            for _ in range(self.N_crossdiff):
                self.eta[:] = conservative_diffusion_step(self.eta, self.qs, self.cell_type, self.source_floor, self.diffusion_multiplier, 5.)
            self.record(before, "diffusion")

        def finalize_timestep(self):
            before = self.eta.copy()
            apply_inlet_stage(self, inlet_stage)
            super().finalize_timestep()
            self.record(before, "inlet_boundary", correction=self._Vp_inletbc)

    model = WideModel(Length=1100., Width=1200., dx=5., L0_meters=10., N0_meters=80., h0=4., hb=.75,
        u0=float(schedule[0, 2]) / 320., C0_percent=.1, f_bedload=.5, Np_water=1000, Np_sed=1000,
        itermax=3, seed=config.seed, H_SL=0., SLR=0., toggle_subsidence=False, force_deposit=False,
        defer_output=True, save_checkpoint=False)
    model.water_repair = WaterRoutingRepair()
    snapshots = {key: [] for key in ("bed_m", "stage_m", "depth_m", "qx_m2_s", "qz_m2_s")}
    times, spent, inlet_corrections, boundary_q = [0.], [0.], [0.], [float(schedule[0, 2])]
    minimum = initial.astype(float).copy()

    def snapshot():
        for key, field in zip(snapshots, (model.eta, model.stage, model.depth, model.qx, model.qy)):
            if not np.isfinite(field).all():
                raise ValueError("nonfinite " + key)
            snapshots[key].append(field.copy())

    snapshot()
    if initialize_only:
        return {key: value[0] for key, value in snapshots.items()}, {
            "steps": 0, "N0": model.N0, "L0": model.L0, "inlet_columns": model.inlet.tolist(),
            "prescribed_q_m3_s": float(model.qw0 * model.N0 * model.dx),
            "initialized_inlet_q_m3_s": float(model.qx[0, model.inlet].sum() * model.dx),
            "materials": materials, "actual_material_thresholds_m_s": {key: float(getattr(model, key)) for key in thresholds},
            "initial_flow_guess": initial_flow_report,
            "source_floor_minimum_margin_m": float(np.min(model.eta.astype(float) - model.source_floor)),
            "interior_stage_initialization_error_m": float(np.max(abs(model.stage[1:].astype(float) - initialization["initial_stage_m"][1:])))}
    for index, packet in enumerate(schedule[:count]):
        _, _, flow, solid, dt, _ = packet
        solid = 0. if zero_supply else solid
        bulk = solid / .65
        model._u0 = flow / 320.
        model._C0_percent = max(1.e-12, bulk / (dt * flow) * 100.)
        model.create_boundary_conditions()
        model.dry_depth = config.routing_dry_depth_m
        model._dt = float(dt)
        model.dVs = bulk
        model.Qs0 = bulk / dt
        model.qs0 = model.Qs0 / 80.
        model.Vp_sed = bulk / model._Np_sed
        model.N_crossdiff = max(1, int(np.ceil(bulk / model.V0)))
        model.diffusion_multiplier = dt / model.N_crossdiff * model._alpha * .5 / 25.
        model.init_sediment_routers()
        model.update()
        minimum = np.minimum(minimum, model.eta)
        times.append(float(model.time))
        spent.append(spent[-1] + solid)
        inlet_corrections.append(float(model._Vp_inletbc))
        boundary_q.append(float(flow))
        snapshot()
        if progress:
            progress(index + 1, times[-1], spent[-1])
    model.save_the_checkpoint()
    arrays = {key: np.asarray(value) for key, value in snapshots.items()}
    arrays.update(initialization)
    arrays.update(initial_bed_m=initial, source_floor_m=model.source_floor, minimum_visited_bed_m=minimum,
        initial_routing_qx_guess_m2_s=initial_qx,
        time_s=np.asarray(times), cumulative_input_solid_m3=np.asarray(spent), schedule=schedule,
        inlet_correction_bulk_m3=np.asarray(inlet_corrections), prescribed_inlet_q_m3_s=np.asarray(boundary_q),
        initial_erodible_solid_m3=(initial - model.source_floor) * 25. * .65)
    ledger = {key: float(sum(row[key] for row in model.phase_records)) for key in
        ("injected_bulk_m3", "exported_bulk_m3", "lost_bulk_m3", "inlet_correction_bulk_m3", "raw_residual_bulk_m3")}
    ledger["bed_change_bulk_m3"] = float((model.eta.astype(float) - initial).sum() * 25.)
    return arrays, {"schema": "wide-independent-natural-short-validation-v1", "config": asdict(config),
        "geometry": geometry_report, "materials": materials, "steps": count, "time_s": float(model.time),
        "initial_flow_guess": initial_flow_report,
        "zero_supply": zero_supply, "ledger_bulk_m3": ledger, "phase_records": model.phase_records,
        "water_repair_iterations": model.water_repair.iterations,
        "inlet_boundary_policy": "prescribed upstream stage and Q; only row0 constrained; all interior free",
        "remaining_finite_source_solid_m3": float(schedule[:, 3].sum() - spent[-1]),
        "scope": "short native parcel mechanism; not transient FV water conservation or morphology acceptance"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--zero-supply", action="store_true")
    args = parser.parse_args()
    resource_limits()
    geometry_report = json.loads((args.initialization / "summary.json").read_text(encoding="utf-8"))
    if geometry_report["schema"] != "wide-counterfactual-natural-initial-v1" or geometry_report["status"] != "prepared-for-short-validation":
        raise ValueError("accepted wide-counterfactual preparation required")
    if file_sha256(args.initialization / "initialization.npz") != geometry_report["initialization_sha256"]:
        raise ValueError("initialization archive identity changed")
    if file_sha256(Path(geometry_report["source_scene"])) != geometry_report["source_scene_sha256"]:
        raise ValueError("scene source identity changed")
    for path, digest in geometry_report["implementation_hashes"].items():
        if file_sha256(ROOT / path) != digest:
            raise ValueError("initialization implementation changed: " + path)
    implementations = tuple(IMPLEMENTATIONS) + ("tools/run_natural_delta_wide.py", "tools/prepare_natural_delta_wide_initial.py")
    hashes = {path: file_sha256(ROOT / path) for path in implementations}
    with np.load(args.initialization / "initialization.npz") as saved:
        initialization = {key: saved[key] for key in saved.files}
    schedule, forcing = load_forcing("mechanism")
    start = time.perf_counter()
    arrays, report = execute(initialization, geometry_report, schedule, args.output, steps=args.steps,
        zero_supply=args.zero_supply, progress=lambda step, seconds, solid: print("PROGRESS", step, "model_seconds", seconds,
            "solid_m3", solid, "wall_s", time.perf_counter() - start, flush=True))
    report.update(forcing=forcing, initialization_sha256=geometry_report["initialization_sha256"],
        implementation_hashes=hashes, runtime_s=time.perf_counter() - start,
        implementation_unchanged_during_run=all(file_sha256(ROOT / path) == digest for path, digest in hashes.items()))
    np.savez_compressed(args.output / "result.npz", **arrays)
    (args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "steps": report["steps"], "ledger": report["ledger_bulk_m3"]}, indent=2))


if __name__ == "__main__":
    main()
