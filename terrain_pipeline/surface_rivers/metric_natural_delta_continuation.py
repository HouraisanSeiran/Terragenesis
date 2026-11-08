"""Native checkpoint continuation with unchanged floor and new finite supply.

The experiment hooks mirror the existing natural model. Kept separate so
in-progress natural experiments retain their loaded source identities.
"""
from dataclasses import asdict
import importlib.metadata
from pathlib import Path

import numpy as np

from .metric_fluvial_morphodynamics import conservative_diffusion_step, phase_record
from .metric_fluvial_native_routers import initialize_source_limited_routers
from .metric_fluvial_water_repair import WaterRoutingRepair, mask_inlet_upstream_weights


CHECKPOINT_GRIDS = ("eta", "eta0", "eta_init", "depth", "stage", "uw", "ux", "uy", "qw", "qx", "qy", "sand_frac", "active_layer")


def continue_natural_delta(parent, parent_arrays, schedule, output, config, *, steps=None, progress=None):
    if importlib.metadata.version("pyDeltaRCM") != "2.3.0":
        raise ValueError("pyDeltaRCM 2.3.0 required")
    if config.reference_bulk_concentration is not None:
        raise ValueError("continuation requires same native non-reference erosion experiment")
    import pyDeltaRCM
    from pyDeltaRCM.shared_tools import get_random_state

    checkpoint = Path(parent) / "backend/checkpoint.npz"
    floor = parent_arrays["source_floor_m"].copy()
    cell_type = parent_arrays["cell_type"].copy()
    initial = parent_arrays["bed_m"][-1].copy()
    # Native RNG state is an object array; only this locally produced native
    # archive is unpickled, and caller pins its hash in the child provenance.
    with np.load(checkpoint, allow_pickle=True) as saved:
        original_checkpoint = {name: saved[name].copy() for name in saved.files}
    for name, key in (("eta", "bed_m"), ("depth", "depth_m"), ("stage", "stage_m"), ("qx", "qx_m2_s"), ("qy", "qz_m2_s")):
        np.testing.assert_array_equal(original_checkpoint[name], parent_arrays[key][-1])
    if not len(schedule):
        raise ValueError("nonempty finite new supply schedule required")
    count = len(schedule) if steps is None else min(int(steps), len(schedule))
    if count < 1:
        raise ValueError("positive step count required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)

    class ContinuedModel(pyDeltaRCM.DeltaModel):
        def init_output_infrastructure(self):
            self._user_dict["out_dir"] = str(output / "backend")
            super().init_output_infrastructure()

        def hook_after_create_domain(self):
            self.cell_type[:] = cell_type
            self.inlet = np.flatnonzero(cell_type[0] == 1)
            self.source_floor = floor.copy()
            self.phase_records = []

        def init_sediment_routers(self):
            initialize_source_limited_routers(self, self.source_floor, quantized_native_exchange=True)

        def get_water_weight_array(self):
            super().get_water_weight_array()
            mask_inlet_upstream_weights(self.water_weights, self.jwalk_flat, self.cell_type)

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

        def record(self, before, phase, injected=0., exported=0., lost=0., correction=0.):
            if np.min(self.eta.astype(float) - self.source_floor) < -2.e-6:
                raise ValueError("inherited finite source floor breached in " + phase)
            row = phase_record(before, self.eta, phase=phase, step_index=self.time_iter, dx_m=config.dx_m,
                injected_bulk_m3=injected, exported_bulk_m3=exported, lost_bulk_m3=lost, inlet_correction_bulk_m3=correction)
            self.phase_records.append({name: value for name, value in row.items() if not isinstance(value, np.ndarray)})

        def route_all_sand_parcels(self):
            before = self.eta.copy()
            super().route_all_sand_parcels()
            self.record(before, "sand", int(self._Np_sed * self._f_bedload) * self.Vp_sed,
                self._sr.Vp_exported, self._sr.Vp_lost)

        def route_all_mud_parcels(self):
            before = self.eta.copy()
            super().route_all_mud_parcels()
            self.record(before, "mud", int(self._Np_sed * (1. - self._f_bedload)) * self.Vp_sed,
                self._mr.Vp_exported, self._mr.Vp_lost)

        def topo_diffusion(self):
            before = self.eta.copy()
            for _ in range(self.N_crossdiff):
                self.eta[:] = conservative_diffusion_step(self.eta, self.qs, self.cell_type,
                    self.source_floor, self.diffusion_multiplier, config.dx_m)
            self.record(before, "diffusion")

        def finalize_timestep(self):
            before = self.eta.copy()
            super().finalize_timestep()
            self.record(before, "inlet_boundary", correction=self._Vp_inletbc)

    model = ContinuedModel(Length=config.shape[0] * config.dx_m, Width=config.shape[1] * config.dx_m,
        dx=config.dx_m, L0_meters=config.land_length_m, N0_meters=config.inlet_width_m,
        h0=config.inlet_depth_m, hb=config.basin_depth_m,
        u0=float(schedule[0, 2]) / (config.inlet_width_m * config.inlet_depth_m),
        C0_percent=.1, f_bedload=.5, Np_water=config.water_parcels, Np_sed=config.sediment_parcels,
        itermax=3, seed=config.seed, H_SL=0., SLR=0., toggle_subsidence=False, force_deposit=False,
        defer_output=True, save_checkpoint=False, resume_checkpoint=str(checkpoint.parent.resolve()))
    restored = {}
    for name in CHECKPOINT_GRIDS:
        np.testing.assert_array_equal(getattr(model, name), original_checkpoint[name])
        restored[name] = True
    np.testing.assert_array_equal(model.source_floor, floor)
    np.testing.assert_array_equal(model.cell_type, cell_type)
    if float(model.time) != float(original_checkpoint["time"]) or model.time_iter != int(original_checkpoint["time_iter"]):
        raise AssertionError("native time/counter restoration failed")
    rng = get_random_state()
    for current_rng, previous_rng in zip(rng, original_checkpoint["rng_state"]):
        np.testing.assert_array_equal(current_rng, previous_rng)
    model.water_repair = WaterRoutingRepair()
    start_time = float(model.time)
    start_step = int(model.time_iter)
    snapshots = {name: [] for name in ("bed_m", "stage_m", "depth_m", "qx_m2_s", "qz_m2_s", "sand_fraction", "active_layer")}
    times, added = [start_time], [0.]
    lifetime_base = float(parent_arrays["cumulative_input_solid_m3"][-1])
    substrate_min = parent_arrays["minimum_visited_bed_m"].copy()

    def snapshot():
        for name, field in zip(snapshots, (model.eta, model.stage, model.depth, model.qx, model.qy, model.sand_frac, model.active_layer)):
            snapshots[name].append(field.copy())

    snapshot()
    for index, (_, _, flow, solid, dt, _) in enumerate(schedule[:count]):
        bulk = solid / (1. - config.porosity)
        model._u0 = flow / (model.h0 * model.N0 * model.dx)
        model._C0_percent = max(1.e-12, bulk / (dt * flow) * 100.)
        model.create_boundary_conditions()
        model.dry_depth = config.routing_dry_depth_m
        model._dt = float(dt)
        model.dVs = bulk
        model.Qs0 = bulk / dt
        model.qs0 = model.Qs0 / (model.N0 * model.dx)
        model.Vp_sed = bulk / model._Np_sed
        model.N_crossdiff = max(1, int(np.ceil(bulk / model.V0)))
        model.diffusion_multiplier = dt / model.N_crossdiff * model._alpha * .5 / model.dx ** 2
        model.init_sediment_routers()
        model.update()
        substrate_min = np.minimum(substrate_min, model.eta.astype(float))
        times.append(float(model.time))
        added.append(added[-1] + solid)
        snapshot()
        if progress:
            progress(index + 1, float(model.time), added[-1])
    model.save_the_checkpoint()
    arrays = {name: np.asarray(values) for name, values in snapshots.items()}
    arrays.update(time_s=np.asarray(times), cumulative_new_input_solid_m3=np.asarray(added),
        cumulative_input_solid_m3=lifetime_base + np.asarray(added), continuation_initial_bed_m=initial,
        source_floor_m=floor, minimum_visited_bed_m=substrate_min, cell_type=cell_type, schedule=schedule,
        initial_bed_m=parent_arrays["initial_bed_m"],
        initial_erodible_solid_m3=parent_arrays["initial_erodible_solid_m3"])
    for name in ("local_world_xz_m", "source_base_bed_m", "source_macro_bed_m", "raw_td_sample_m", "source_td_residual_m",
            "construction_height_delta_m", "fixed_boundary_mask", "initial_float32_representation_delta_m"):
        if name in parent_arrays:
            arrays[name] = parent_arrays[name].copy()
    ledger = {name: float(sum(row[name] for row in model.phase_records)) for name in
        ("injected_bulk_m3", "exported_bulk_m3", "lost_bulk_m3", "inlet_correction_bulk_m3", "raw_residual_bulk_m3")}
    ledger["bed_change_bulk_m3"] = float((model.eta.astype(float) - initial).sum() * config.dx_m ** 2)
    return arrays, {"schema": "finite-natural-native-checkpoint-continuation-v1", "config": asdict(config),
        "restored_native_checkpoint_grids": restored, "restored_native_rng_exact": True,
        "restored_native_time_s": start_time, "restored_native_step": start_step,
        "steps": count, "lifetime_steps": int(model.time_iter), "time_s": float(model.time),
        "new_source_input_solid_m3": added[-1], "old_source_input_solid_m3": lifetime_base,
        "lifetime_input_solid_m3": lifetime_base + added[-1], "remaining_new_source_solid_m3": float(schedule[:, 3].sum() - added[-1]),
        "source_floor_unchanged": True, "ledger_bulk_m3": ledger, "phase_records": model.phase_records,
        "water_repair_iterations": model.water_repair.iterations,
        "water_input_m3": float(np.sum(schedule[:count, 2] * schedule[:count, 4])),
        "native_checkpoint_scope": "native restart includes bed, free surface, velocity/flux, surface sand fraction, active layer, RNG, counters; custom source floor/cell types/minimum visited bed inherited from parent result; per-step parcel/work arrays regenerated as native restart normally does",
        "time_semantics": "accelerated sediment-bearing mechanism chronology only, not elapsed repeated-water-year time; dt and all inlet sediment/capacity/diffusion parameters recomputed for each new finite packet",
        "vector_axes": "native saved qx_m2_s downstream row; qz_m2_s cross-stream column (native qy)",
        "clear_water_limitation": "native zero-load packets have zero sediment-capacity erosion; no claim of full annual clear-water evolution"}
