"""Persistent finite FV delta, with no prescribed downstream channel graph."""

from dataclasses import asdict, dataclass, field
import copy
import math
import time

import numpy as np

from terrain_pipeline.common_infra import identity, readonly, save_bundle, load_bundle
from terrain_pipeline.surface_hydraulics import SurfaceBudget, prepare_surface_geometry
from .surface_rivers.metric_fv_coastal_sediment import BedloadConfig, MorphodynamicStepTooLarge
from .surface_rivers.metric_fv_suspended_supply import SuspendedConfig
from .surface_rivers.metric_fv_exchange_v3 import ExchangeConfig
from .surface_rivers.metric_fv_growth_coupling_v4 import advance_growth


SCHEMA = "environment-dynamic-FV-delta-v1"
ALGORITHM = "finite-live-FV-delta-canonical-coupling-v1"
SOLVERS = {"water": "hydrostatic-HLL-SSPRK2-accelerated-v7", "sediment": "carrier-bounded-bedload-v4",
           "exchange": "finite-bed-suspended-wetbank-v3"}


@dataclass(frozen=True)
class FVDeltaConfig:
    coupling_interval_s: float = 10.
    max_hydro_dt_s: float = 5.
    bedload: BedloadConfig = field(default_factory=lambda: BedloadConfig(wave_height_m=0., max_bed_change_m=.05))
    suspended: SuspendedConfig = field(default_factory=lambda: SuspendedConfig(max_bed_change_m=.05))
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    sea_mean_m: float = 0.
    tide_amplitude_m: float = 0.
    tide_period_s: float = 44714.
    tide_phase_rad: float = 0.
    max_wall_s: float = 120.
    max_depth_m: float = 100.
    max_halvings: int = 8

    def validate(self):
        self.bedload.validate()
        self.suspended.validate()
        self.exchange.validate()
        for name in ("coupling_interval_s", "max_hydro_dt_s", "tide_period_s", "max_wall_s", "max_depth_m"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0.:
                raise ValueError("finite positive " + name + " required")
        if (not np.isfinite([self.sea_mean_m, self.tide_amplitude_m, self.tide_phase_rad]).all()
                or self.tide_amplitude_m < 0. or type(self.max_halvings) is not int or not 0 <= self.max_halvings <= 16
                or self.bedload.porosity != self.suspended.porosity or self.bedload.manning_s_m_third <= 0.):
            raise ValueError("matching porosity and finite sea/retry configuration required")


def _config(record):
    values = dict(record)
    for key, constructor in (("bedload", BedloadConfig), ("suspended", SuspendedConfig), ("exchange", ExchangeConfig)):
        values[key] = constructor(**values[key])
    result = FVDeltaConfig(**values)
    result.validate()
    return result


def _geometry(arrays, metadata):
    ocean = arrays["ocean_mask"]
    kinds = np.where(np.r_[ocean[:, 0], ocean[:, -1], ocean[0], ocean[-1]], 2, 0).astype(np.int64)
    geometry = prepare_surface_geometry(arrays["bed_m"].copy(), spacing_m=metadata["spacing_m"],
        origin_m_xz=metadata["origin_m_xz"], source_identity=metadata["source_identity"], boundary_kind=kinds)
    fixed = np.zeros(ocean.size, bool)
    # Computational marine edge is an export boundary, never an erodible source.
    fixed[geometry["arrays"]["boundary_cell"][kinds == 2]] = True
    geometry["arrays"]["fixed_bed_cell"] = fixed
    return geometry


def _seal(arrays, metadata):
    result = {"arrays": {key: readonly(value) for key, value in arrays.items()}, "metadata": metadata,
              "identity_sha256": identity(arrays, metadata)}
    validate(result)
    return result


def initialize(bed_m, ocean_mask, inlet_cells, *, origin_m_xz, source_world_identity, source_identity,
               spacing_m=30., initial_time_s=0., floor_m=None, erodible_cover_m=0., config=FVDeltaConfig()):
    """Copy an immutable source bed; inlet cells are row-major integer indices."""
    config.validate()
    bed = np.asarray(bed_m, dtype=np.float64)
    ocean = np.asarray(ocean_mask)
    inlet = np.asarray(inlet_cells)
    if (bed.ndim != 2 or not 1 <= bed.size <= 65536 or not np.isfinite(bed).all()
            or ocean.shape != bed.shape or ocean.dtype != bool or not ocean.any()
            or inlet.ndim != 1 or not len(inlet) or not np.issubdtype(inlet.dtype, np.integer)
            or len(np.unique(inlet)) != len(inlet) or np.any(inlet < 0) or np.any(inlet >= bed.size)
            or not isinstance(source_world_identity, str) or not source_world_identity
            or not np.isfinite([initial_time_s, erodible_cover_m]).all() or min(initial_time_s, erodible_cover_m) < 0.):
        raise ValueError("finite metric source bed, ocean, unique inlet and identities required")
    floor = bed - erodible_cover_m if floor_m is None else np.asarray(floor_m, float)
    if floor.shape != bed.shape or not np.isfinite(floor).all() or np.any(floor > bed):
        raise ValueError("finite bed floor cannot exceed initial bed")
    stage = config.sea_mean_m + config.tide_amplitude_m * math.sin(2.*math.pi*initial_time_s/config.tide_period_s + config.tide_phase_rad)
    arrays = {"initial_bed_m": bed.copy(), "bed_m": bed.copy(), "floor_m": floor.copy(),
              "ocean_mask": ocean.copy(), "inlet_cells": inlet.astype(np.int64),
              "depth_m": np.maximum(stage-bed, 0.), "momentum_m2_s": np.zeros((bed.size, 2)),
              "suspended_solid_m3": np.zeros_like(bed), "deposited_solid_m3": np.zeros_like(bed),
              "entrained_solid_m3": np.zeros_like(bed), "fixed_marine_edge_export_solid_m3": np.zeros(bed.size)}
    metadata = {"schema": SCHEMA, "spacing_m": float(spacing_m), "origin_m_xz": list(origin_m_xz),
                "algorithm": ALGORITHM, "underlying_solvers": dict(SOLVERS),
                "source_world_identity": source_world_identity, "source_identity": source_identity,
                "physical_time_s": float(initial_time_s), "config": asdict(config), "consumed_forcing_ids": [],
                "forcing_records": [], "completed_coupling_steps": 0, "rejected_coupling_steps": 0,
                "last_coupling_interval_s": 0.,
                "ledger": {"water_input_m3": 0., "sea_import_m3": 0., "water_export_m3": 0.,
                           "solid_input_m3": 0., "solid_export_m3": 0.},
                "initial_water_m3": float(arrays["depth_m"].sum()*spacing_m**2),
                "initial_bed_solid_m3": float(((bed-floor)*spacing_m**2*(1.-config.bedload.porosity)).sum()),
                "routing": "live two-dimensional FV D4 shared faces; no D8 receiver and no prescribed branches",
                "initial_water_source": "declared still water at initial sea stage over all low cells; not imported source-world water inventory",
                "face_absolute_transfer_semantics": "sum of absolute coupling-interval net face transfers; not gross hydraulic-substep transfer; water ledger sea import/export are gross substep totals",
                "limitations": "uncalibrated finite engineering scenario; clear-water sea inflow; dilute Exner split retains water depth/momentum; no wave radiation stress or cohesive banks"}
    geometry = _geometry(arrays, metadata)
    fixed = geometry["arrays"]["fixed_bed_cell"].reshape(bed.shape)
    arrays["floor_m"][fixed] = bed[fixed]
    metadata["initial_bed_solid_m3"] = float(((bed-arrays["floor_m"])*spacing_m**2*(1.-config.bedload.porosity)).sum())
    for key in ("face_left", "face_right", "boundary_cell", "boundary_kind"):
        arrays[key] = geometry["arrays"][key].copy()
    for name, length in (("internal", len(arrays["face_left"])), ("boundary", len(arrays["boundary_cell"]))):
        for quantity in ("water_transfer_m3", "water_absolute_transfer_m3", "solid_transfer_m3", "last_water_transfer_m3"):
            arrays[name+"_"+quantity] = np.zeros(length)
    return _seal(arrays, metadata)


def advance(product, forcing_records):
    """Consume contiguous finite records atomically; retry only actual morphology refusals."""
    validate(product)
    if not isinstance(forcing_records, (list, tuple)) or not 1 <= len(forcing_records) <= 1024:
        raise ValueError("bounded nonempty finite forcing records required")
    arrays = {key: value.copy() for key, value in product["arrays"].items()}
    metadata = copy.deepcopy(product["metadata"])
    metadata.update(algorithm=ALGORITHM, underlying_solvers=dict(SOLVERS))
    config = _config(metadata["config"])
    started = time.monotonic()
    next_time = metadata["physical_time_s"]
    seen = set(metadata["consumed_forcing_ids"])
    records = []
    for original in forcing_records:
        record = copy.deepcopy(original)
        if (not isinstance(record.get("id"), str) or not record["id"] or record["id"] in seen
                or not isinstance(record.get("source"), str) or not record["source"]
                or not np.isfinite([record[k] for k in ("time_start_s", "time_end_s", "water_m3", "solid_m3")]).all()
                or record["time_start_s"] != next_time or record["time_end_s"] <= next_time
                or min(record["water_m3"], record["solid_m3"]) < 0.):
            raise ValueError("unique sourced forcing IDs and contiguous finite physical intervals required")
        seen.add(record["id"])
        next_time = record["time_end_s"]
        records.append(record)

    def step(start, end, q, solid_rate, halvings=0):
        remaining_wall = config.max_wall_s - (time.monotonic()-started)
        if remaining_wall <= 0.:
            raise RuntimeError("FV delta wall budget exceeded; input product remains complete")
        dt = end-start
        geometry = _geometry(arrays, metadata)
        sea = config.sea_mean_m + config.tide_amplitude_m * math.sin(2.*math.pi*start/config.tide_period_s + config.tide_phase_rad)
        captured = []
        try:
            result = advance_growth(geometry, floor_m=arrays["floor_m"], depth_m=arrays["depth_m"],
                momentum_m2_s=arrays["momentum_m2_s"], suspended_solid_m3=arrays["suspended_solid_m3"],
                river_q_m3_s=[q], input_solid_m3=[solid_rate*dt], sea_stages_m=[sea], inlet_cells=arrays["inlet_cells"],
                interval_s=dt, budget=SurfaceBudget(max_dt_s=config.max_hydro_dt_s, max_snapshots=3,
                    max_duration_s=dt, max_wall_s=remaining_wall, max_depth_m=config.max_depth_m,
                    roughness_s_m_third=config.bedload.manning_s_m_third),
                bedload_config=config.bedload, suspended_config=config.suspended, exchange_config=config.exchange,
                interval_observer=lambda water, bedload, suspended, ledger: captured.append((water, bedload, suspended, ledger)))
        except MorphodynamicStepTooLarge:
            metadata["rejected_coupling_steps"] += 1
            if halvings >= config.max_halvings:
                raise
            middle = .5*(start+end)
            step(start, middle, q, solid_rate, halvings+1)
            step(middle, end, q, solid_rate, halvings+1)
            return
        water, bedload, suspended, ledger = captured[0]
        output = result["arrays"]
        for key in ("bed_m", "depth_m", "suspended_solid_m3"):
            arrays[key] = output[key][-1].copy()
        arrays["momentum_m2_s"] = np.column_stack([output["momentum_x_m2_s"][-1].ravel(), output["momentum_z_m2_s"][-1].ravel()])
        arrays["deposited_solid_m3"] += suspended["deposited_solid_m3"]
        arrays["entrained_solid_m3"] += suspended["entrained_solid_m3"]
        arrays["fixed_marine_edge_export_solid_m3"] += bedload["fixed_marine_edge_export_solid_m3"]
        for name in ("internal", "boundary"):
            transfer = water[name+"_transfer_m3"]
            arrays[name+"_water_transfer_m3"] += transfer
            arrays[name+"_water_absolute_transfer_m3"] += abs(transfer)
            arrays[name+"_last_water_transfer_m3"] = transfer.copy()
            sediment_key = "internal_transfer_solid_m3" if name == "internal" else "boundary_export_solid_m3"
            arrays[name+"_solid_transfer_m3"] += bedload[sediment_key] + suspended[sediment_key]
            if name == "internal":
                arrays[name+"_solid_transfer_m3"] += bedload["slope_internal_transfer_solid_m3"]
        totals = metadata["ledger"]
        totals["water_input_m3"] += q*dt
        totals["sea_import_m3"] += float(output["ledger"][-1, 1])
        totals["water_export_m3"] += float(output["ledger"][-1, 2])
        totals["solid_input_m3"] += solid_rate*dt
        totals["solid_export_m3"] += ledger["exported_solid_m3"]
        metadata["physical_time_s"] = float(end)
        metadata["last_coupling_interval_s"] = float(dt)
        metadata["completed_coupling_steps"] += 1

    for record in records:
        start, end = record["time_start_s"], record["time_end_s"]
        q, solid_rate = record["water_m3"]/(end-start), record["solid_m3"]/(end-start)
        while start < end:
            # Anchor canonical boundaries to physical time, independent of save/load.
            boundary = (math.floor(start/config.coupling_interval_s + 1.e-12)+1)*config.coupling_interval_s
            stop = min(end, boundary)
            step(start, stop, q, solid_rate)
            start = stop
        metadata["consumed_forcing_ids"].append(record["id"])
        metadata["forcing_records"].append(record)
    return _seal(arrays, metadata)


def validate(product):
    arrays, metadata = product["arrays"], product["metadata"]
    if metadata["schema"] != SCHEMA or product["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("FV delta product identity mismatch")
    config = _config(metadata["config"])
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("finite FV delta arrays required")
    if (np.any(arrays["depth_m"] < 0.) or np.any(arrays["suspended_solid_m3"] < 0.)
            or np.min(arrays["bed_m"]-arrays["floor_m"]) < -1.e-9
            or len(set(metadata["consumed_forcing_ids"])) != len(metadata["consumed_forcing_ids"])):
        raise ValueError("nonnegative finite FV stocks and unique consumption required")
    area = metadata["spacing_m"]**2
    ledger = metadata["ledger"]
    water_residual = arrays["depth_m"].sum()*area + ledger["water_export_m3"] - metadata["initial_water_m3"] - ledger["water_input_m3"] - ledger["sea_import_m3"]
    inventory = ((arrays["bed_m"]-arrays["floor_m"])*area*(1.-config.bedload.porosity)).sum() + arrays["suspended_solid_m3"].sum()
    solid_residual = inventory + ledger["solid_export_m3"] - metadata["initial_bed_solid_m3"] - ledger["solid_input_m3"]
    if abs(water_residual) > 1.e-8*max(1., metadata["initial_water_m3"]+ledger["water_input_m3"]+ledger["sea_import_m3"]):
        raise ValueError("FV delta cumulative water budget does not close")
    if abs(solid_residual) > 1.e-8*max(1., metadata["initial_bed_solid_m3"]+ledger["solid_input_m3"]):
        raise ValueError("FV delta cumulative solid budget does not close")
    return True


def save(path, product):
    save_bundle(path, product, validator=validate)


def load(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate)


def query(product, x_m, z_m):
    validate(product)
    a, m = product["arrays"], product["metadata"]
    col, row = np.rint((np.asarray([x_m, z_m])-m["origin_m_xz"])/m["spacing_m"]).astype(int)
    if not 0 <= row < a["bed_m"].shape[0] or not 0 <= col < a["bed_m"].shape[1]:
        raise ValueError("query outside finite FV delta support")
    return {"bed_m": float(a["bed_m"][row, col]), "depth_m": float(a["depth_m"][row, col]),
            "stage_m": float(a["bed_m"][row, col]+a["depth_m"][row, col]),
            "physical_time_s": m["physical_time_s"]}
