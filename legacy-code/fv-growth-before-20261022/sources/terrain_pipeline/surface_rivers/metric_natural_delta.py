"""New-start finite-supply shallow-basin DeltaRCM mechanism experiment.

No downstream path, island, mouth bar or branch count is prescribed. The
hydraulic time compression is explicit; cumulative solid supply is unchanged.
Old candidate/checkpoint identities are neither consumed nor modified.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import importlib.metadata

import numpy as np

from .metric_fluvial_morphodynamics import conservative_diffusion_step, phase_record
from .metric_fluvial_native_routers import initialize_source_limited_routers
from .metric_fluvial_water_repair import WaterRoutingRepair, mask_inlet_upstream_weights


@dataclass(frozen=True)
class NaturalDeltaConfig:
    shape: tuple = (160, 120)
    dx_m: float = 5.
    inlet_width_m: float = 80.
    inlet_depth_m: float = 1.5
    land_length_m: float = 60.
    basin_depth_m: float = .75
    porosity: float = .35
    erodible_cover_m: float = .30
    max_step_solid_m3: float = 200.
    mechanism_bulk_concentration: float = .001
    water_parcels: int = 1000
    sediment_parcels: int = 1000
    seed: int = 1847
    routing_dry_depth_m: float = .1
    reference_bulk_concentration: float | None = None


def finite_schedule(daily_q, daily_solid, daily_duration, config=NaturalDeltaConfig(), *, mode="mechanism"):
    q, solid, duration = [np.asarray(value, float) for value in (daily_q, daily_solid, daily_duration)]
    if (q.shape != solid.shape or q.shape != duration.shape or q.ndim != 1
            or not np.isfinite(np.concatenate([q, solid, duration])).all()
            or np.any(q <= 0.) or np.any(solid < 0.) or np.any(duration <= 0.)
            or mode not in ("mechanism", "annual")):
        raise ValueError("positive water/time and finite nonnegative sediment required")
    records = []
    for day, (flow, volume, seconds) in enumerate(zip(q, solid, duration)):
        count = max(1, int(np.ceil(volume/config.max_step_solid_m3)))
        for substep in range(count):
            load = volume/count
            # Mechanism removes the long clear-water tail; it does not call its
            # compressed discharge integral the real annual water budget.
            if mode == "mechanism" and load < 1.e-9:
                continue
            dt = seconds/count if mode == "annual" else load/((1.-config.porosity)*flow*config.mechanism_bulk_concentration)
            records.append((day, substep, flow, load, dt, seconds/count))
    return np.asarray(records, float).reshape((-1, 6))


def initial_basin(config=NaturalDeltaConfig()):
    bed = np.full(config.shape, -config.basin_depth_m, np.float32)
    land = int(round(config.land_length_m/config.dx_m))
    width = int(round(config.inlet_width_m/config.dx_m))
    first = config.shape[1]//2-width//2
    bed[:land] = .35
    bed[:land, first:first+width] = -config.inlet_depth_m
    return bed


def run_natural_delta(schedule, output_dir, *, config=NaturalDeltaConfig(), steps=None, zero_supply=False,
                      progress=None, initialization=None):
    if importlib.metadata.version("pyDeltaRCM") != "2.3.0":
        raise ValueError("pyDeltaRCM 2.3.0 required")
    import pyDeltaRCM
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    initial = initial_basin(config) if initialization is None else np.asarray(initialization["initial_bed_m"], np.float32)
    if initial.shape != config.shape or not np.isfinite(initial).all():
        raise ValueError("finite initialization must match configured shape")
    floor = initial.astype(float)-config.erodible_cover_m
    if initialization is not None:
        floor[initialization["fixed_boundary_mask"]] = initial[initialization["fixed_boundary_mask"]]
    schedule = np.asarray(schedule, float)
    count = len(schedule) if steps is None else min(int(steps), len(schedule))
    if count < 1:
        raise ValueError("positive finite step budget required")

    class FiniteModel(pyDeltaRCM.DeltaModel):
        def init_output_infrastructure(self):
            self._user_dict["out_dir"] = str(output_dir/"backend")
            super().init_output_infrastructure()

        def hook_after_create_domain(self):
            self.eta[:] = initial
            first = config.shape[1]//2-self.N0//2
            self.inlet = np.arange(first, first+self.N0)
            self.source_floor = floor.copy()
            self.eta0[:] = self.eta
            self.eta_init[:] = self.eta
            self.cell_type[:] = 0
            self.cell_type[:self.L0] = -2
            self.cell_type[:self.L0, self.inlet] = 1
            self.cell_type[self.L0:, 0] = -1
            self.cell_type[self.L0:, -1] = -1
            self.cell_type[-1] = -1
            if initialization is not None:
                self.cell_type[:] = initialization["cell_type"]
                self.inlet = initialization["inlet_columns"].copy()
            # Existing fixed inlet and computational ocean edge cannot erode.
            self.source_floor[(self.cell_type == -2) | (self.cell_type == -1)] = initial[(self.cell_type == -2) | (self.cell_type == -1)]
            self.stage[:] = np.maximum(self.eta, 0.)
            self.depth[:] = np.maximum(self.stage-self.eta, 0.)
            self.qx[:] = self.qw0/5.
            self.qx[:self.L0, self.inlet] = self.qw0
            self.qy[:] = 0.
            self.qw[:] = np.hypot(self.qx, self.qy)
            self.ux[:] = np.divide(self.qx, self.depth, out=np.zeros_like(self.qx), where=self.depth > 0.)
            self.uy[:] = 0.
            self.uw[:] = np.abs(self.ux)
            self.dry_depth = .01
            self.phase_records = []

        def init_sediment_routers(self):
            if config.reference_bulk_concentration is None:
                initialize_source_limited_routers(self, self.source_floor, quantized_native_exchange=True)
            else:
                from .metric_reference_erosion import initialize_reference_routers
                self.reference_erosion_identity = initialize_reference_routers(self,
                    self.source_floor, config.reference_bulk_concentration)

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
            result = super().check_for_boundary(indices)
            self.water_repair.boundary(indices, result)
            return result

        def record(self, before, phase, injected=0., exported=0., lost=0., correction=0.):
            if np.min(self.eta.astype(float)-self.source_floor) < -2.e-6:
                raise ValueError("finite source floor breached in "+phase)
            record = phase_record(before, self.eta, phase=phase,
                step_index=self.time_iter, dx_m=config.dx_m, injected_bulk_m3=injected,
                exported_bulk_m3=exported, lost_bulk_m3=lost, inlet_correction_bulk_m3=correction)
            self.phase_records.append({key: value for key, value in record.items() if not isinstance(value, np.ndarray)})

        def route_all_sand_parcels(self):
            before = self.eta.copy()
            super().route_all_sand_parcels()
            self.record(before, "sand", int(self._Np_sed*self._f_bedload)*self.Vp_sed,
                self._sr.Vp_exported, self._sr.Vp_lost)

        def route_all_mud_parcels(self):
            before = self.eta.copy()
            super().route_all_mud_parcels()
            self.record(before, "mud", int(self._Np_sed*(1.-self._f_bedload))*self.Vp_sed,
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

    model = FiniteModel(Length=config.shape[0]*config.dx_m, Width=config.shape[1]*config.dx_m,
        dx=config.dx_m, L0_meters=config.land_length_m, N0_meters=config.inlet_width_m,
        h0=config.inlet_depth_m, hb=config.basin_depth_m,
        u0=float(schedule[0, 2])/(config.inlet_width_m*config.inlet_depth_m),
        C0_percent=.1, f_bedload=.5, Np_water=config.water_parcels,
        Np_sed=config.sediment_parcels, itermax=3, seed=config.seed,
        H_SL=0., SLR=0., toggle_subsidence=False, force_deposit=False,
        defer_output=True, save_checkpoint=False)
    model.water_repair = WaterRoutingRepair()
    snapshots = {key: [] for key in ("bed_m", "stage_m", "depth_m", "qx_m2_s", "qz_m2_s")}
    times, spent = [0.], [0.]
    substrate_min = initial.astype(float).copy()
    def snapshot():
        for key, field in zip(snapshots, (model.eta, model.stage, model.depth, model.qx, model.qy)):
            snapshots[key].append(field.copy())
    snapshot()
    for index, record in enumerate(schedule[:count]):
        _, _, flow, solid, dt, _ = record
        solid = 0. if zero_supply else solid
        bulk = solid/(1.-config.porosity)
        model._u0 = flow/(model.h0*model.N0*model.dx)
        # Recompute the entire native capacity/dt system, then replace the
        # per-step volume with the finite packet, keeping Qs*dt=dVs exactly.
        model._C0_percent = max(1.e-12, bulk/(dt*flow)*100.)
        model.create_boundary_conditions()
        model.dry_depth = config.routing_dry_depth_m
        model._dt = float(dt)
        model.dVs = bulk
        model.Qs0 = bulk/dt
        model.qs0 = model.Qs0/(model.N0*model.dx)
        model.Vp_sed = bulk/model._Np_sed
        model.N_crossdiff = max(1, int(np.ceil(bulk/model.V0)))
        model.diffusion_multiplier = dt/model.N_crossdiff*model._alpha*.5/model.dx**2
        model.init_sediment_routers()
        model.update()
        substrate_min = np.minimum(substrate_min, model.eta.astype(float))
        spent.append(spent[-1]+solid)
        times.append(float(model.time))
        snapshot()
        if progress:
            progress(index+1, float(model.time), spent[-1])
    model.save_the_checkpoint()
    arrays = {key: np.asarray(value) for key, value in snapshots.items()}
    arrays.update(time_s=np.asarray(times), cumulative_input_solid_m3=np.asarray(spent),
        initial_bed_m=initial, source_floor_m=model.source_floor, minimum_visited_bed_m=substrate_min,
        cell_type=model.cell_type, schedule=schedule, initial_erodible_solid_m3=(initial.astype(float)-model.source_floor)*config.dx_m**2*(1.-config.porosity))
    if initialization is not None:
        for key in ("source_base_bed_m", "source_macro_bed_m", "raw_td_sample_m", "source_td_residual_m",
                    "construction_height_delta_m", "local_world_xz_m", "fixed_boundary_mask"):
            arrays[key] = initialization[key]
        arrays["initial_float32_representation_delta_m"] = initial.astype(float)-initialization["initial_bed_m"]
    ledger = {name: float(sum(record[name] for record in model.phase_records)) for name in
        ("injected_bulk_m3", "exported_bulk_m3", "lost_bulk_m3", "inlet_correction_bulk_m3", "raw_residual_bulk_m3")}
    ledger["bed_change_bulk_m3"] = float((model.eta.astype(float)-initial).sum()*config.dx_m**2)
    return arrays, {"schema": "finite-natural-delta-mechanism-v1" if config.reference_bulk_concentration is None else "finite-natural-delta-reference-erosion-v2", "config": asdict(config),
        "reference_erosion": None if config.reference_bulk_concentration is None else {
            "algorithm": "native-independent-reference-capacity-erosion-v1",
            "reference_bulk_concentration": config.reference_bulk_concentration,
            "interpretation": "explicit uncalibrated transport/erosion reference, not external sediment input or a calibrated material law",
            "last_step": model.reference_erosion_identity},
        "steps": count, "zero_supply": zero_supply, "ledger_bulk_m3": ledger,
        "remaining_external_source_solid_m3": float(schedule[:, 3].sum()-spent[-1]),
        "remaining_source_semantics": "unspent finite boundary entitlement; zero-supply control deliberately leaves this entire source uninjected",
        "phase_records": model.phase_records, "water_repair_iterations": model.water_repair.iterations,
        "backend": "pyDeltaRCM 2.3.0, quantized source-limited routers, repaired water routing",
        "clear_water_limitation": "native zero-load parcels may produce zero capacity erosion; measured control is authoritative",
        "time_s": float(model.time), "water_input_m3": float(np.sum(schedule[:count, 2]*schedule[:count, 4]))}
