"""Terminal diagnostic: fixed natural-delta bed, true source Q, no sediment.

Paired warm checkpoint / hydrostatic initialization measures dependence on
initial water stage. This is neither actual clear-water morphodynamics nor an
annual continuation. No checkpoint produced here is a candidate continuation.
"""
import argparse
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import WaterRoutingRepair, mask_inlet_upstream_weights
from tools.verify_fluvial_channel_remobilization import resource_limits


def run(parent, output, iterations):
    import pyDeltaRCM
    parent_report = json.loads((parent/"summary.json").read_text(encoding="utf-8"))
    cfg = parent_report["config"]
    with np.load(parent/"result.npz") as saved:
        bed = saved["bed_m"][-1].copy()
        cell_type = saved["cell_type"]
        warm = {name: saved[key][-1].copy() for name, key in
            (("stage", "stage_m"), ("depth", "depth_m"), ("qx", "qx_m2_s"), ("qy", "qz_m2_s"))}
    output.mkdir(parents=True, exist_ok=False)
    q_daily = np.asarray(parent_report["forcing"]["daily_water_q_m3_s"])
    cases = [("minimum_daily_Q", float(q_daily.min())), ("maximum_daily_Q", float(q_daily.max()))]
    results = {}
    report = {"schema": "natural-delta-fixed-bed-water-terminal-v1", "diagnostic_only": True,
        "parent_result": str(parent/"result.npz"), "parent_sha256": file_sha256(parent/"result.npz"),
        "semantics": "fixed final bed, no sediment routing or bed change; warm versus explicit hydrostatic initial water state; approximate steady water iteration convergence diagnostic, not annual clear-water evolution",
        "cases": {}}

    class WaterModel(pyDeltaRCM.DeltaModel):
        def init_output_infrastructure(self):
            self._user_dict["out_dir"] = str(case_output)
            super().init_output_infrastructure()

        def hook_after_create_domain(self):
            self.inlet = np.arange(bed.shape[1]//2-self.N0//2, bed.shape[1]//2-self.N0//2+self.N0)
            self.cell_type[:] = cell_type
            self.eta[:] = bed
            self.eta0[:] = bed
            self.eta_init[:] = bed

        def get_water_weight_array(self):
            super().get_water_weight_array()
            mask_inlet_upstream_weights(self.water_weights, self.jwalk_flat, self.cell_type)

        def finalize_free_surface(self):
            before = self.stage.copy()
            super().finalize_free_surface()
            self.native_stage_updates.append(float(np.max(np.abs(self.stage-before))))

        def account_water_relocation_segment(self, *args, **kwargs):
            super().update_Q(*args, **kwargs)

        def init_water_iteration(self):
            super().init_water_iteration()
            self.water_repair.begin(self)

        def run_water_iteration(self):
            with self.water_repair.native_loop_calls(self):
                super().run_water_iteration()
            self.water_repair.finish()

        def update_Q(self, dist, current_inds, next_inds, astep, jstep, istep, update_current=False, update_next=False):
            if update_current and update_next:
                self.water_repair.adjacent(self, current_inds, next_inds)
            super().update_Q(dist, current_inds, next_inds, astep, jstep, istep, update_current, update_next)

        def check_for_boundary(self, indices):
            mask = super().check_for_boundary(indices)
            self.water_repair.boundary(indices, mask)
            return mask

    marine = (cell_type == 0) & (bed >= 0.)
    for case_name, q in cases:
        for initialization in ("warm", "hydrostatic"):
            name = case_name+"__"+initialization
            case_output = output/name
            model = WaterModel(Length=bed.shape[0]*cfg["dx_m"], Width=bed.shape[1]*cfg["dx_m"],
                dx=cfg["dx_m"], L0_meters=cfg["land_length_m"], N0_meters=cfg["inlet_width_m"],
                h0=cfg["inlet_depth_m"], hb=cfg["basin_depth_m"],
                u0=q/(cfg["inlet_width_m"]*cfg["inlet_depth_m"]), C0_percent=.1,
                Np_water=cfg["water_parcels"], Np_sed=cfg["sediment_parcels"], itermax=3,
                seed=cfg["seed"], H_SL=0., defer_output=True, save_checkpoint=False)
            model.water_repair = WaterRoutingRepair()
            model.native_stage_updates = []
            # Native finalize_free_surface suppresses updating at time_iter=0.
            # This is a solver-iteration marker only, not elapsed calendar time.
            model._time_iter = int(parent_report["steps"])
            model.dry_depth = cfg.get("routing_dry_depth_m", .1)
            if initialization == "warm":
                for field, value in warm.items():
                    getattr(model, field)[:] = value
            else:
                model.stage[:] = np.maximum(bed, 0.)
                model.depth[:] = np.maximum(model.stage-bed, 0.)
                model.qx[:] = np.where(model.depth > 0., model.qw0/5., 0.)
                model.qy[:] = 0.
                model.qx[:model.L0, model.inlet] = model.qw0
            model.qw[:] = np.hypot(model.qx, model.qy)
            model.uw[:] = np.divide(model.qw, model.depth, out=np.zeros_like(model.qw), where=model.depth > 0.)
            model.ux[:] = np.divide(model.qx, model.depth, out=np.zeros_like(model.qx), where=model.depth > 0.)
            model.uy[:] = np.divide(model.qy, model.depth, out=np.zeros_like(model.qy), where=model.depth > 0.)
            history = []
            stages, depths = [model.stage.copy()], [model.depth.copy()]
            for iteration in range(iterations//3):
                old = model.stage.copy()
                model.route_water()
                if not np.array_equal(model.eta, bed):
                    raise AssertionError("fixed-bed diagnostic altered terrain")
                history.append([(iteration+1)*3, float(np.max(np.abs(model.stage-old))),
                    float(np.count_nonzero(marine & (model.depth <= 2.e-6))*cfg["dx_m"]**2),
                    float(model.depth.sum()*cfg["dx_m"]**2),
                    float(np.maximum(model.qx[model.L0], 0.).sum()*cfg["dx_m"])])
                stages.append(model.stage.copy()); depths.append(model.depth.copy())
            results[name+"__stage_m"] = np.asarray(stages)
            results[name+"__depth_m"] = np.asarray(depths)
            results[name+"__qx_m2_s"] = model.qx.copy()
            results[name+"__qz_m2_s"] = model.qy.copy()
            report["cases"][name] = {"q_m3_s": q, "initialization": initialization,
                "warm_semantics": "saved hydraulic fields are an initial guess even when prescribed discharge differs; no exact steady-state claim",
                "native_iteration_marker": model._time_iter, "calendar_seconds_advanced": 0.,
                "per_native_finalize_stage_max_change_m": model.native_stage_updates,
                "routing_dry_depth_m": model.dry_depth, "history_columns": ["water_iterations", "max_stage_change_m", "actual_dry_above_datum_m2", "water_storage_m3", "mouth_forward_q_m3_s"],
                "history": history, "water_repair": model.water_repair.iterations}
            print(name, history[-1], flush=True)
    results["fixed_bed_m"] = bed
    np.savez_compressed(output/"water-diagnostic.npz", **results)
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=90)
    args = parser.parse_args()
    if not 3 <= args.iterations <= 90 or args.iterations % 3:
        parser.error("iterations must be 3..90 in multiples of 3")
    resource_limits()
    run(args.parent, args.output, args.iterations)
