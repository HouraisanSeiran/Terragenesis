"""Pinned pyDeltaRCM adaptation with native phase ledgers and source mappings.

The backend solves approximate steady water fields. Native sediment volumes
are bed bulk volumes; a single declared packing fraction converts them to solid.
"""

from dataclasses import asdict, dataclass
from contextlib import nullcontext
import importlib.metadata
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import readonly
from .metric_contracts import TerrainGrid
from .metric_fluvial_delta import FluvialDeltaBoundary, _finite
from .metric_fluvial_water_repair import WATER_REPAIR_MECHANISMS


BACKEND_VERSION = "2.3.0"
NATIVE_EXCHANGE_VERSION = "pydeltarcm-metric-adapter-v1"
SOURCE_LIMITED_VERSION = "pydeltarcm-metric-adapter-v2-source-floor-exchange"
GRAVITY_VERSION = "pydeltarcm-metric-adapter-v3-mobile-gravity"
DRY_DEPTH_VERSION = "pydeltarcm-metric-adapter-v4-dry-depth-sensitivity"
QUANTIZED_EXCHANGE_VERSION = "pydeltarcm-metric-adapter-v5-quantized-native-exchange"
WATER_ROUTING_REPAIR_VERSION = "pydeltarcm-metric-adapter-v6-water-routing-repair"
GRAVITY_VERSIONS = (GRAVITY_VERSION, DRY_DEPTH_VERSION, QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION)
GRAVITY_PARAMETERS = {"repose_angle_deg": 30., "tolerance_m": 1e-6, "max_sweeps": 512,
                      "substrate_sand_fraction": .5}


def mechanism_identity_for(algorithm_version):
    parameters = {"algorithm_version": algorithm_version,
                  "gravity_parameters": GRAVITY_PARAMETERS if algorithm_version in GRAVITY_VERSIONS else None}
    if algorithm_version in (DRY_DEPTH_VERSION, QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION):
        parameters["routing_dry_depth_m"] = .01
    if algorithm_version in (QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION):
        parameters["quantized_native_exchange"] = True
    if algorithm_version == WATER_ROUTING_REPAIR_VERSION:
        parameters.update(water_routing_repair=True, water_repair_mechanisms=WATER_REPAIR_MECHANISMS)
    return hashlib.sha256(json.dumps(parameters, sort_keys=True).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class MorphodynamicsConfig:
    steps: int = 16
    dx_m: float = 5.
    inlet_width_m: float = 35.
    inlet_depth_m: float = 2.
    inlet_length_m: float = 45.
    inlet_velocity_m_s: float = 1.
    sediment_concentration_percent: float = .1
    sand_fraction: float = .5
    porosity: float = .35
    maximum_original_source_cut_m: float = 4.
    water_parcels: int = 1000
    sediment_parcels: int = 1000
    water_iterations: int = 3
    seed: int = 42
    diffusion_enabled: bool = True
    diffusion_mode: str = "conservative"
    official_shape: tuple[int, int] = (60, 60)

    def __post_init__(self):
        for name, maximum in (("steps", 4096), ("water_parcels", 20000), ("sediment_parcels", 20000),
                              ("water_iterations", 10)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(name + " outside finite integer budget")
        if type(self.seed) is not int or not 0 <= self.seed <= 2147483647 or type(self.diffusion_enabled) is not bool:
            raise ValueError("explicit bounded seed and boolean diffusion flag required")
        if self.diffusion_mode not in ("native", "conservative"):
            raise ValueError("known diffusion mode required")
        if (not isinstance(self.official_shape, tuple) or len(self.official_shape) != 2
                or any(type(value) is not int or not 16 <= value <= 512 for value in self.official_shape)):
            raise ValueError("bounded official model shape required")
        for name in ("dx_m", "inlet_width_m", "inlet_depth_m", "inlet_length_m", "inlet_velocity_m_s",
                     "sediment_concentration_percent"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, strict=True))
        for name in ("porosity", "sand_fraction", "maximum_original_source_cut_m"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if (self.porosity >= 1. or not 0. <= self.sand_fraction <= 1.
                or not 0. < self.maximum_original_source_cut_m <= 4.
                or self.inlet_depth_m > self.maximum_original_source_cut_m
                or round(self.inlet_width_m / self.dx_m) < 3):
            raise ValueError("invalid packing, material floor or underresolved inlet")


def validate_diffusion_ablation_parent(declaration, config, resume_checkpoint):
    if not isinstance(declaration, dict):
        raise ValueError("diffusion ablation parent declaration must be a dict")
    if not isinstance(declaration.get("enabled"), bool):
        raise ValueError("diffusion ablation parent 'enabled' must be an explicit bool")
    if getattr(config, "steps", None) not in (4, 128):
        raise ValueError("requires config.steps in (4, 128)")
    if getattr(config, "diffusion_enabled", None) is not True:
        raise ValueError("diffusion ablation parent requires config.diffusion_enabled is True")
    if getattr(config, "diffusion_mode", None) != "conservative":
        raise ValueError("diffusion ablation parent requires config.diffusion_mode == 'conservative'")
    if not resume_checkpoint:
        raise ValueError("diffusion ablation parent requires a resume checkpoint")

    canonical_cfg = json.loads(json.dumps(asdict(config), sort_keys=True))
    canonical_cfg.pop("steps", None)

    required = ("parent_archive_path", "parent_archive_sha256", "checkpoint_sha256", "material_state_sha256")
    if any(key not in declaration for key in required):
        raise ValueError("diffusion ablation parent requires archive and state hashes")
    for key in required:
        if not isinstance(declaration[key], str) or not declaration[key]:
            raise ValueError("diffusion ablation parent requires archive and state hashes")

    parent_archive_path = Path(declaration["parent_archive_path"])
    parent_archive_sha256 = declaration["parent_archive_sha256"]
    if not parent_archive_path.is_file():
        raise ValueError("diffusion ablation parent archive file not found")
    actual_parent_sha = hashlib.sha256(parent_archive_path.read_bytes()).hexdigest()
    if actual_parent_sha != parent_archive_sha256:
        raise ValueError("diffusion ablation parent archive sha256 mismatch: actual %s declared %s" % (actual_parent_sha, parent_archive_sha256))

    with np.load(parent_archive_path, allow_pickle=False) as archive:
        metadata_raw = archive["metadata_json"]
        metadata_json = metadata_raw.item() if hasattr(metadata_raw, "item") else metadata_raw
    metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
    core = metadata["core"]

    if metadata.get("diagnostic_only") is True:
        raise ValueError("diffusion ablation parent archive must not be diagnostic_only")
    if core.get("diagnostic_only") is True:
        raise ValueError("diffusion ablation parent archive core must not be diagnostic_only")
    if core.get("algorithm_version") != WATER_ROUTING_REPAIR_VERSION:
        raise ValueError("diffusion ablation parent archive algorithm_version mismatch")
    if core.get("native_end_step_index") != 4224:
        raise ValueError("diffusion ablation parent archive must be v6 at native_end_step_index 4224")
    canonical_core_cfg = dict(core["config"])
    canonical_core_cfg.pop("steps", None)
    if json.dumps(canonical_core_cfg, sort_keys=True) != json.dumps(canonical_cfg, sort_keys=True):
        raise ValueError("diffusion ablation parent archive config mismatch (excluding steps)")

    resume_dir = Path(resume_checkpoint)
    if resume_dir.is_file():
        resume_dir = resume_dir.parent
    checkpoint_end = resume_dir / "checkpoint.npz"
    material_end = resume_dir / "adapter-material-state.npz"

    if Path(core["checkpoint_end_path"]).resolve() != checkpoint_end.resolve():
        raise ValueError("diffusion ablation parent archive checkpoint_end_path does not match resume checkpoint")
    if Path(core["material_state_end_path"]).resolve() != material_end.resolve():
        raise ValueError("diffusion ablation parent archive material_state_end_path does not match resume material state")

    checkpoint_sha = hashlib.sha256(checkpoint_end.read_bytes()).hexdigest()
    material_sha = hashlib.sha256(material_end.read_bytes()).hexdigest()

    if core["checkpoint_end_sha256"] != checkpoint_sha:
        raise ValueError("diffusion ablation parent archive core checkpoint sha256 mismatch")
    if core["material_state_end_sha256"] != material_sha:
        raise ValueError("diffusion ablation parent archive core material state sha256 mismatch")
    if declaration["checkpoint_sha256"] != checkpoint_sha:
        raise ValueError("diffusion ablation parent declaration checkpoint_sha256 mismatch")
    if declaration["material_state_sha256"] != material_sha:
        raise ValueError("diffusion ablation parent declaration material_state_sha256 mismatch")

    continuation_path = resume_dir / "adapter-continuation.json"
    if not continuation_path.is_file():
        raise ValueError("diffusion ablation parent requires adapter-continuation.json")
    continuation = json.loads(continuation_path.read_text(encoding="utf-8"))

    if continuation.get("diagnostic_only"):
        raise ValueError("diffusion ablation parent continuation must not be diagnostic_only")
    if continuation.get("algorithm_version") != WATER_ROUTING_REPAIR_VERSION:
        raise ValueError("diffusion ablation parent continuation algorithm_version mismatch")
    if continuation.get("native_end_step_index") != 4224:
        raise ValueError("diffusion ablation parent continuation must be v6 at native_end_step_index 4224")
    if continuation.get("checkpoint_sha256") != checkpoint_sha:
        raise ValueError("diffusion ablation parent continuation checkpoint_sha256 mismatch")
    if continuation.get("material_state_sha256") != material_sha:
        raise ValueError("diffusion ablation parent continuation material_state_sha256 mismatch")
    if core.get("continuation_identity") != continuation.get("continuation_identity"):
        raise ValueError("diffusion ablation parent continuation_identity mismatch between archive core and continuation metadata")

    result = dict(declaration)
    result["schema"] = "terminal-diffusion-ablation-v1"
    result["diagnostic_only"] = True
    result["effective_diffusion_enabled"] = declaration["enabled"]
    result["steps"] = config.steps
    return result


def phase_record(start, end, *, phase, step_index, dx_m, injected_bulk_m3=0., exported_bulk_m3=0.,
                 lost_bulk_m3=0., inlet_correction_bulk_m3=0.):
    """Keep measured native imbalance separate from every named boundary term."""
    start, end = np.asarray(start, np.float64), np.asarray(end, np.float64)
    if start.shape != end.shape or not np.isfinite(start).all() or not np.isfinite(end).all():
        raise ValueError("finite matching native phase beds required")
    delta = (end - start) * dx_m ** 2
    residual = math.fsum((float(delta.sum()), -injected_bulk_m3, exported_bulk_m3,
                          lost_bulk_m3, -inlet_correction_bulk_m3))
    return {"step_index": step_index, "phase": phase,
            "start_bed_m": readonly(start), "end_bed_m": readonly(end), "delta_bulk_m3": readonly(delta),
            "injected_bulk_m3": float(injected_bulk_m3), "exported_bulk_m3": float(exported_bulk_m3),
            "lost_bulk_m3": float(lost_bulk_m3), "inlet_correction_bulk_m3": float(inlet_correction_bulk_m3),
            "raw_residual_bulk_m3": residual}


def conservative_diffusion_step(bed, sediment_flux, cell_type, floor, coefficient, dx_m):
    """Native eight-neighbor operator as closed, donor-limited pair transfers.

    For an interior i,j pair native cf is k*(qs_i+qs_j)*(eta_j-eta_i).
    Removing edges to walls, row zero and outside the domain keeps both ends
    consistent. A donor's available bulk limits all its transfers together.
    """
    bed = np.asarray(bed, np.float64)
    flux = np.asarray(sediment_flux, np.float64)
    floor = np.asarray(floor, np.float64)
    if (bed.ndim != 2 or flux.shape != bed.shape or cell_type.shape != bed.shape or floor.shape != bed.shape
            or not np.isfinite(bed).all() or not np.isfinite(flux).all() or np.any(flux < 0.)
            or not math.isfinite(coefficient) or coefficient < 0.):
        raise ValueError("finite matching conservative diffusion fields required")
    indices = np.arange(bed.size).reshape(bed.shape)
    active = cell_type != -2
    active[0, :] = False
    transfers, outgoing = [], np.zeros(bed.size)
    area = dx_m ** 2
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        first = (slice(0, bed.shape[0] - dr), slice(max(0, -dc), bed.shape[1] - max(0, dc)))
        second = (slice(dr, bed.shape[0]), slice(max(0, dc), bed.shape[1] - max(0, -dc)))
        usable = active[first] & active[second]
        a, b = indices[first][usable], indices[second][usable]
        volume = coefficient * (flux[first][usable] + flux[second][usable]) * (bed[second][usable] - bed[first][usable]) * area
        donor = np.where(volume >= 0., b, a)
        np.add.at(outgoing, donor, np.abs(volume))
        transfers.append((a, b, donor, volume))
    # Leave a representable margin before a float32 backend accepts the update.
    guarded_floor = floor + 4. * np.finfo(np.float32).eps * np.maximum(1., np.abs(floor))
    available = np.maximum(0., bed - guarded_floor).ravel() * area
    scale = np.minimum(1., np.divide(available, outgoing, out=np.ones_like(outgoing), where=outgoing > 0.))
    delta = np.zeros(bed.size)
    for a, b, donor, volume in transfers:
        limited = volume * scale[donor]
        np.add.at(delta, a, limited)
        np.add.at(delta, b, -limited)
    return bed + delta.reshape(bed.shape) / area


def _mapped_input(terrain, boundary, inlet_cell, initial_cover, config):
    if (not isinstance(terrain, TerrainGrid) or not isinstance(boundary, FluvialDeltaBoundary)
            or terrain.dx_m != terrain.dz_m or terrain.dx_m != config.dx_m):
        raise ValueError("typed square source terrain at declared spacing required")
    row, column = inlet_cell
    shape = terrain.elevation_m.shape
    if not 0 < row < shape[0] - 1 or not 0 <= column < shape[1] - 16:
        raise ValueError("mapped eastward inlet needs a bounded downstream support")
    if boundary.initial_ocean_mask.shape != shape or np.any(boundary.ocean_export_mask[:, :-1]):
        raise ValueError("east perimeter ocean exports required for mapped native domain")
    cover = np.zeros(shape) if initial_cover is None else np.asarray(initial_cover, np.float64)
    if cover.shape != shape or not np.isfinite(cover).all() or np.any(cover < 0.):
        raise ValueError("finite matching nonnegative initial cover required")
    prepared = terrain.elevation_m + cover / ((1. - config.porosity) * terrain.cell_area_m2)
    mapping = {"source_rows_columns": [0, shape[0], column, shape[1]], "transpose": True,
               "backend_downstream_axis": "increasing original x", "backend_crossstream_axis": "increasing original z"}
    arrays = {"source_original_bed_m": terrain.elevation_m, "source_prepared_bed_m": readonly(prepared),
              "source_ocean_mask": boundary.initial_ocean_mask,
              "backend_source_bed_m": readonly(terrain.elevation_m[:, column:].T),
              "backend_prepared_bed_m": readonly(prepared[:, column:].T),
              "backend_valid_mask": readonly(terrain.valid_mask[:, column:].T),
              "backend_ocean_mask": readonly(boundary.initial_ocean_mask[:, column:].T),
              "backend_export_mask": readonly(boundary.ocean_export_mask[:, column:].T)}
    if arrays["backend_prepared_bed_m"].size > 65536:
        raise ValueError("native domain cell budget exceeded")
    return arrays, mapping, row


def simulate_fluvial_morphodynamics(terrain=None, boundary=None, *, config=None, inlet_cell=None,
                                    initial_cover_solid_m3=None, output_dir, progress_callback=None,
                                    resume_checkpoint=None, source_limited_erosion=True,
                                    mechanism_transition=None, gravity_stability=False,
                                    routing_dry_depth_m=None, observe_native_exchange=False,
                                    quantized_native_exchange=False, diagnostic_sediment_stepmax=None,
                                    diagnostic_water_routing=False, diagnostic_water_repair=False,
                                    water_routing_repair=False, diagnostic_diffusion_ablation=None):
    """Run fixed positive water/sediment boundaries using physical native dt.

    With terrain=None, use the deterministic native synthetic domain geometry;
    diffusion follows the declared mode. TD input is an explicitly mapped
    downstream subdomain, not a new TD.
    A proposed phase exceeding the source floor is rejected before publication;
    its bed is never clipped and its sediment is never relabelled as export.
    """
    config = MorphodynamicsConfig() if config is None else config
    if not isinstance(config, MorphodynamicsConfig):
        raise ValueError("MorphodynamicsConfig required")
    diffusion_diagnostic_declaration = None
    effective_diffusion_enabled = config.diffusion_enabled
    if diagnostic_diffusion_ablation is not None:
        if not (water_routing_repair and quantized_native_exchange and gravity_stability):
            raise ValueError("diffusion ablation requires repaired water routing, native exchange, and gravity stability")
        if routing_dry_depth_m != 0.01:
            raise ValueError("diffusion ablation requires routing_dry_depth_m == 0.01")
        if observe_native_exchange or diagnostic_sediment_stepmax is not None or diagnostic_water_routing or diagnostic_water_repair:
            raise ValueError("diffusion ablation cannot be combined with other diagnostics")
        if mechanism_transition is not None:
            raise ValueError("diffusion ablation cannot be combined with mechanism_transition")
        diffusion_diagnostic_declaration = validate_diffusion_ablation_parent(diagnostic_diffusion_ablation, config, resume_checkpoint)
        effective_diffusion_enabled = diffusion_diagnostic_declaration["effective_diffusion_enabled"]
    if type(source_limited_erosion) is not bool or type(gravity_stability) is not bool:
        raise ValueError("explicit native/source-limited erosion mode required")
    if gravity_stability and not source_limited_erosion:
        raise ValueError("gravity mechanism requires source-limited native erosion")
    if type(observe_native_exchange) is not bool or (observe_native_exchange and not source_limited_erosion):
        raise ValueError("native exchange observation requires explicit source-limited router mode")
    if type(quantized_native_exchange) is not bool or (quantized_native_exchange and (
            not gravity_stability or routing_dry_depth_m != .01 or resume_checkpoint is None)):
        raise ValueError("quantized exchange requires inherited .01m gravity state")
    if diagnostic_sediment_stepmax is not None and (
            type(diagnostic_sediment_stepmax) is not int or diagnostic_sediment_stepmax not in (570, 1140)
            or config.steps != 1 or not quantized_native_exchange or observe_native_exchange):
        raise ValueError("sediment routing-budget diagnostic requires a single inherited v5 step, cap 570/1140 and observation off")
    if type(diagnostic_water_routing) is not bool or (diagnostic_water_routing and (
            diagnostic_sediment_stepmax != 570 and not water_routing_repair)):
        raise ValueError("water routing observation requires terminal 570 diagnostic or continuous water repair")
    if type(diagnostic_water_repair) is not bool or (diagnostic_water_repair and not diagnostic_water_routing):
        raise ValueError("water repair candidate requires the observed terminal single-step diagnostic")
    if type(water_routing_repair) is not bool or (water_routing_repair and (
            not quantized_native_exchange or diagnostic_sediment_stepmax is not None)):
        raise ValueError("continuous water repair requires inherited quantized exchange without terminal diagnostics")
    if routing_dry_depth_m is not None:
        routing_dry_depth_m = _finite(routing_dry_depth_m, "routing_dry_depth_m", strict=True)
        if routing_dry_depth_m != .01 or not gravity_stability:
            raise ValueError("only explicit .01m gravity routing-depth sensitivity is supported")
        if resume_checkpoint is None:
            raise ValueError("routing-depth sensitivity requires an inherited gravity checkpoint")
    algorithm_version = SOURCE_LIMITED_VERSION if source_limited_erosion else NATIVE_EXCHANGE_VERSION
    if gravity_stability:
        algorithm_version = GRAVITY_VERSION if routing_dry_depth_m is None else DRY_DEPTH_VERSION
    if quantized_native_exchange:
        algorithm_version = QUANTIZED_EXCHANGE_VERSION
    if water_routing_repair:
        algorithm_version = WATER_ROUTING_REPAIR_VERSION
    mechanism_identity = mechanism_identity_for(algorithm_version)
    if importlib.metadata.version("pyDeltaRCM") != BACKEND_VERSION:
        raise ValueError("pinned pyDeltaRCM 2.3.0 required")
    import pyDeltaRCM

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mapped, mapping, inlet_center = None, {}, None
    if terrain is not None:
        if inlet_cell is None:
            raise ValueError("explicit source inlet required")
        mapped, mapping, inlet_center = _mapped_input(terrain, boundary, inlet_cell, initial_cover_solid_m3, config)
        shape = mapped["backend_source_bed_m"].shape
        sea_level = boundary.sea_level_m
    else:
        if boundary is not None or initial_cover_solid_m3 is not None:
            raise ValueError("official control has no external domain or prepared cover")
        shape, sea_level = config.official_shape, 0.
    if shape[0] * shape[1] * (config.steps + 1) > 8388608:
        raise ValueError("native history allocation budget exceeded")
    identity_config = asdict(config)
    identity_config.pop("steps")
    identity = hashlib.sha256(json.dumps({"config": identity_config, "backend_version": BACKEND_VERSION,
                                       "mapping": mapping, "inlet_cell": inlet_cell,
                                       "sea_level_m": sea_level}, sort_keys=True).encode("utf-8"))
    if mapped is not None:
        for key in sorted(mapped):
            array = np.ascontiguousarray(mapped[key])
            identity.update(key.encode("ascii"))
            identity.update(str((array.shape, array.dtype.str)).encode("ascii"))
            identity.update(array.tobytes())
    continuation_identity = identity.hexdigest()
    previous_checkpoint_hash = None
    previous_material_hash = None
    resumed_mobile_base = None
    if resume_checkpoint is not None:
        resume_checkpoint = Path(resume_checkpoint).resolve()
        if resume_checkpoint == output_dir / "backend":
            raise ValueError("resume requires a new batch directory to preserve its parent checkpoint")
        declaration = json.loads((resume_checkpoint / "adapter-continuation.json").read_text(encoding="utf-8"))
        if declaration.get("diagnostic_only"):
            raise ValueError("diagnostic sediment-budget checkpoint is terminal and cannot continue a candidate")
        previous_checkpoint_hash = hashlib.sha256((resume_checkpoint / "checkpoint.npz").read_bytes()).hexdigest()
        if (declaration["continuation_identity"] != continuation_identity
                or declaration["checkpoint_sha256"] != previous_checkpoint_hash):
            raise ValueError("checkpoint source/config identity or saved bytes differ")
        previous_version = declaration.get("algorithm_version", NATIVE_EXCHANGE_VERSION)
        if diagnostic_sediment_stepmax is not None and previous_version != QUANTIZED_EXCHANGE_VERSION:
            raise ValueError("sediment routing-budget diagnostic requires the actual inherited v5 checkpoint")
        if quantized_native_exchange and previous_version not in (DRY_DEPTH_VERSION, QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION):
            raise ValueError("quantized exchange requires an inherited v4/v5 mobile material state")
        if routing_dry_depth_m is not None and previous_version not in GRAVITY_VERSIONS:
            raise ValueError("routing-depth sensitivity requires an inherited gravity mobile material state")
        if previous_version in GRAVITY_VERSIONS:
            material_path = resume_checkpoint / "adapter-material-state.npz"
            previous_material_hash = hashlib.sha256(material_path.read_bytes()).hexdigest()
            if (declaration.get("mechanism_identity") != mechanism_identity_for(previous_version)
                    or declaration.get("material_state_sha256") != previous_material_hash):
                raise ValueError("checkpoint mechanism identity or mobile material bytes differ")
            if previous_version in (DRY_DEPTH_VERSION, QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION) and declaration.get("routing_dry_depth_m") != .01:
                raise ValueError("checkpoint routing-depth sensitivity identity differs")
            if previous_version in (QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION) and declaration.get("quantized_native_exchange") is not True:
                raise ValueError("checkpoint quantized exchange identity differs")
            if previous_version == WATER_ROUTING_REPAIR_VERSION and (
                    declaration.get("water_routing_repair") is not True
                    or declaration.get("water_repair_mechanisms") != WATER_REPAIR_MECHANISMS
                    or not water_routing_repair):
                raise ValueError("checkpoint water repair identity differs; downgrade unsupported")
            with np.load(material_path, allow_pickle=False) as state:
                resumed_mobile_base = state["mobile_base_m"].copy()
        if previous_version != algorithm_version:
            if (not isinstance(mechanism_transition, dict)
                    or mechanism_transition.get("from_algorithm_version") != previous_version
                    or mechanism_transition.get("to_algorithm_version") != algorithm_version
                    or mechanism_transition.get("after_step") != declaration["native_end_step_index"]):
                raise ValueError("checkpoint mechanism change requires an explicit matching transition")
            if algorithm_version == DRY_DEPTH_VERSION and (
                    mechanism_transition.get("routing_dry_depth_m") != .01
                    or mechanism_transition.get("from_routing_dry_depth_m") != .1
                    or mechanism_transition.get("gravity_parameters") != GRAVITY_PARAMETERS
                    or mechanism_transition.get("mechanism_identity") != mechanism_identity
                    or mechanism_transition.get("material_state_start_sha256") != previous_material_hash
                    or Path(mechanism_transition.get("material_state_start_path", "")).resolve()
                        != resume_checkpoint / "adapter-material-state.npz"):
                raise ValueError("routing-depth transition parameters or inherited material identity differ")
            if algorithm_version == QUANTIZED_EXCHANGE_VERSION and (
                    mechanism_transition.get("quantized_native_exchange") is not True
                    or mechanism_transition.get("routing_dry_depth_m") != .01
                    or mechanism_transition.get("from_routing_dry_depth_m") != .01
                    or mechanism_transition.get("gravity_parameters") != GRAVITY_PARAMETERS
                    or mechanism_transition.get("mechanism_identity") != mechanism_identity
                    or mechanism_transition.get("checkpoint_sha256") != previous_checkpoint_hash
                    or Path(mechanism_transition.get("checkpoint_path", "")).resolve() != resume_checkpoint / "checkpoint.npz"
                    or mechanism_transition.get("material_state_start_sha256") != previous_material_hash
                    or Path(mechanism_transition.get("material_state_start_path", "")).resolve()
                        != resume_checkpoint / "adapter-material-state.npz"):
                raise ValueError("quantized exchange transition parameters or inherited state identity differ")
            if algorithm_version == WATER_ROUTING_REPAIR_VERSION:
                if (previous_version != QUANTIZED_EXCHANGE_VERSION or declaration["native_end_step_index"] != 4096
                        or mechanism_transition.get("water_routing_repair") is not True
                        or mechanism_transition.get("water_repair_mechanisms") != WATER_REPAIR_MECHANISMS
                        or mechanism_transition.get("quantized_native_exchange") is not True
                        or mechanism_transition.get("routing_dry_depth_m") != .01
                        or mechanism_transition.get("from_routing_dry_depth_m") != .01
                        or mechanism_transition.get("gravity_parameters") != GRAVITY_PARAMETERS
                        or mechanism_transition.get("mechanism_identity") != mechanism_identity
                        or mechanism_transition.get("checkpoint_sha256") != previous_checkpoint_hash
                        or Path(mechanism_transition.get("checkpoint_path", "")).resolve() != resume_checkpoint / "checkpoint.npz"
                        or mechanism_transition.get("material_state_start_sha256") != previous_material_hash
                        or Path(mechanism_transition.get("material_state_start_path", "")).resolve()
                            != resume_checkpoint / "adapter-material-state.npz"
                        or not mechanism_transition.get("reason")
                        or not mechanism_transition.get("water_routing_repair_evidence")):
                    raise ValueError("water repair transition requires frozen v5/4096 parent and explicit mechanism evidence")
                for evidence in mechanism_transition["water_routing_repair_evidence"]:
                    if hashlib.sha256(Path(evidence["path"]).read_bytes()).hexdigest() != evidence["sha256"]:
                        raise ValueError("water repair transition evidence bytes differ")

    class RecordedModel(pyDeltaRCM.DeltaModel):
        def get_water_weight_array(self):
            super().get_water_weight_array()
            if water_routing_repair or diagnostic_water_repair:
                from .metric_fluvial_water_repair import mask_inlet_upstream_weights
                counts = mask_inlet_upstream_weights(self.water_weights, self.jwalk_flat, self.cell_type)
                self.water_repair.current["inlet_weight_mask"] = counts
                if diagnostic_water_routing:
                    self.water_routing_diagnostic.current["inlet_weight_mask"] = np.array(list(counts.values()))

        def account_water_relocation_segment(self, *args, **kwargs):
            super().update_Q(*args, **kwargs)

        def init_water_iteration(self):
            super().init_water_iteration()
            if water_routing_repair or diagnostic_water_repair:
                self.water_repair.begin(self)
            if diagnostic_water_routing:
                self.water_routing_diagnostic.begin(self)

        def run_water_iteration(self):
            repair = self.water_repair.native_loop_calls(self) if water_routing_repair or diagnostic_water_repair else nullcontext()
            with repair:
                observer = self.water_routing_diagnostic.native_loop_calls(self) if diagnostic_water_routing else nullcontext()
                with observer:
                    super().run_water_iteration()
            if water_routing_repair or diagnostic_water_repair:
                self.water_repair.finish()
            if diagnostic_water_routing:
                self.water_routing_diagnostic.finish_walk(self)

        def update_Q(self, dist, current_inds, next_inds, astep, jstep, istep,
                     update_current=False, update_next=False):
            if diagnostic_water_routing and update_current and update_next:
                self.water_routing_diagnostic.adjacent(self, current_inds, next_inds)
            if (water_routing_repair or diagnostic_water_repair) and update_current and update_next:
                self.water_repair.adjacent(self, current_inds, next_inds)
            super().update_Q(dist, current_inds, next_inds, astep, jstep, istep, update_current, update_next)

        def check_for_boundary(self, indices):
            boundary_mask = super().check_for_boundary(indices)
            if diagnostic_water_routing:
                self.water_routing_diagnostic.boundary(indices, boundary_mask)
            if water_routing_repair or diagnostic_water_repair:
                self.water_repair.boundary(indices, boundary_mask)
            return boundary_mask

        def update_flow_field(self, iteration):
            if diagnostic_water_routing:
                self.water_routing_diagnostic.before_flow(self)
            super().update_flow_field(iteration)
            if diagnostic_water_routing:
                self.water_routing_diagnostic.after_flow(self, iteration)

        def init_output_infrastructure(self):
            # In 2.3.0 the native infrastructure reads user YAML before kwargs.
            self._user_dict["out_dir"] = str(output_dir / "backend")
            super().init_output_infrastructure()

        def init_sediment_routers(self):
            if source_limited_erosion:
                from .metric_fluvial_native_routers import initialize_source_limited_routers
                initialize_source_limited_routers(self, self.source_bed - config.maximum_original_source_cut_m,
                    observe_native_exchange=observe_native_exchange, quantized_native_exchange=quantized_native_exchange)
            else:
                super().init_sediment_routers()

        def hook_after_create_domain(self):
            if routing_dry_depth_m is not None:
                self.dry_depth = routing_dry_depth_m
            self.phase_records = []
            if mapped is None:
                self.source_bed = self.eta.copy().astype(np.float64)
                self.prepared_bed = self.source_bed.copy()
                return
            self.source_bed = np.array(mapped["backend_source_bed_m"])
            self.prepared_bed = np.array(mapped["backend_prepared_bed_m"])
            self.eta[:] = self.prepared_bed
            self.cell_type[:] = 0
            self.cell_type[~mapped["backend_valid_mask"]] = -2
            self.cell_type[0, :] = -2
            self.cell_type[:, 0] = self.cell_type[:, -1] = -2
            self.cell_type[-1, :] = -2
            self.cell_type[-1, mapped["backend_export_mask"][-1, :]] = -1
            first = inlet_center - self.N0 // 2
            self.inlet = np.arange(first, first + self.N0)
            if first < 1 or first + self.N0 >= shape[1] - 1:
                raise ValueError("declared inlet section intersects side walls")
            self.cell_type[:self.L0, self.inlet] = 1
            # This rectangular inlet boundary stub is an explicit initialization
            # work event. No downstream branch or channel is prescribed.
            self.eta[:self.L0, self.inlet] = sea_level - self.h0
            self.stage[:] = np.maximum(sea_level, self.eta)
            self.stage[self.cell_type == -2] = np.maximum(sea_level, self.eta[self.cell_type == -2])
            self.depth[:] = np.maximum(0., self.stage - self.eta)
            self.qx[:] = 0.
            self.qy[:] = 0.
            self.qx[self.depth > 0.] = self.qw0 / 5.
            self.qx[:self.L0, self.inlet] = self.qw0
            self.qw[:] = np.hypot(self.qx, self.qy)
            self.ux[:] = np.divide(self.qx, self.depth, out=np.zeros_like(self.qx), where=self.depth > 0.)
            self.uy[:] = 0.
            self.uw[:] = np.abs(self.ux)
            self.eta0[:] = self.eta
            self.eta_init[:] = self.eta
            self._check_floor()

        def _check_floor(self):
            if np.any(self.eta.astype(np.float64) < self.source_bed - config.maximum_original_source_cut_m - 2e-6):
                raise ValueError("native proposed phase exceeds original-source incision floor")

        def _record(self, before, phase, injected=0., exported=0., lost=0., correction=0.):
            self.proposed_phase = phase
            self.proposed_start_bed = before
            self._check_floor()
            record = phase_record(before, self.eta, phase=phase, step_index=self.time_iter,
                                  dx_m=config.dx_m, injected_bulk_m3=injected, exported_bulk_m3=exported,
                                  lost_bulk_m3=lost, inlet_correction_bulk_m3=correction)
            if source_limited_erosion and phase in ("sand", "mud"):
                router = self._sr if phase == "sand" else self._mr
                record["source_floor_limited_bulk_m3"] = float(router.source_floor_limited_bulk_m3)
                record["source_floor_limited_exchange_count"] = int(router.source_floor_limited_exchange_count)
            self.phase_records.append(record)
            if gravity_stability and phase != "gravity":
                self.mobile_base = np.minimum(self.mobile_base, self.eta.astype(np.float64))

        def route_all_sand_parcels(self):
            if diagnostic_sediment_stepmax is not None:
                self.diagnostic_pre_sediment_fields = {name: getattr(self, native).copy() for name, native in
                    (("beds_m", "eta"), ("depths_m", "depth"), ("stages_m", "stage"),
                     ("qx_m2_s", "qx"), ("qz_m2_s", "qy"), ("ux_m_s", "ux"),
                     ("uz_m_s", "uy"), ("speed_m_s", "uw"))}
            before = self.eta.copy()
            if source_limited_erosion:
                self._sr.source_floor_limited_bulk_m3 = 0.
                self._sr.source_floor_limited_exchange_count = 0
            super().route_all_sand_parcels()
            injected = int(self._Np_sed * self._f_bedload) * self.Vp_sed
            self._record(before, "sand", injected, self._sr.Vp_exported, self._sr.Vp_lost)

        def topo_diffusion(self):
            before = self.eta.copy()
            if effective_diffusion_enabled:
                if config.diffusion_mode == "native":
                    super().topo_diffusion()
                else:
                    for _ in range(self.N_crossdiff):
                        proposed = conservative_diffusion_step(
                            self.eta, self.qs, self.cell_type,
                            self.source_bed - config.maximum_original_source_cut_m,
                            self.diffusion_multiplier, config.dx_m)
                        self.eta[:] = proposed
            self._record(before, "diffusion")

        def route_all_mud_parcels(self):
            before = self.eta.copy()
            if source_limited_erosion:
                self._mr.source_floor_limited_bulk_m3 = 0.
                self._mr.source_floor_limited_exchange_count = 0
            super().route_all_mud_parcels()
            injected = int(self._Np_sed * (1. - self._f_bedload)) * self.Vp_sed
            self._record(before, "mud", injected, self._mr.Vp_exported, self._mr.Vp_lost)

        def finalize_timestep(self):
            before = self.eta.copy()
            super().finalize_timestep()
            self._record(before, "finalize", correction=self._Vp_inletbc)
            if gravity_stability:
                from .metric_fluvial_slope_stability import relax_mobile_slopes
                before = self.eta.copy()
                start_fraction, start_active = self.sand_frac.copy(), self.active_layer.copy()
                relaxed = relax_mobile_slopes(before, self.mobile_base, start_fraction, start_active,
                    self.cell_type != -2, dx_m=config.dx_m, **GRAVITY_PARAMETERS)
                self.eta[:] = relaxed.bed_m
                self.sand_frac[:] = relaxed.sand_fraction
                self.active_layer[:] = relaxed.active_layer
                changed = self.eta != before
                self.depth[changed] = np.maximum(0., self.stage[changed] - self.eta[changed])
                wet = changed & (self.depth > 0.)
                self.uw[wet] = np.minimum(self.u_max, self.qw[wet] / self.depth[wet])
                flowing = changed & (self.qw > 0.)
                self.ux[flowing] = self.uw[flowing] * self.qx[flowing] / self.qw[flowing]
                self.uy[flowing] = self.uw[flowing] * self.qy[flowing] / self.qw[flowing]
                self.ux[changed & ~flowing] = self.uy[changed & ~flowing] = 0.
                self.pad_depth[1:-1, 1:-1] = self.depth
                self._record(before, "gravity")
                record = self.phase_records[-1]
                record["gravity_ledger"] = dict(relaxed.ledger)
                start_mobile = (before.astype(np.float64) - self.mobile_base) * config.dx_m ** 2
                end_mobile = (self.eta.astype(np.float64) - self.mobile_base) * config.dx_m ** 2
                record["gravity_ledger"]["actual_raw_residual_bulk_m3"] = record["raw_residual_bulk_m3"]
                record["gravity_ledger"]["actual_raw_residual_sand_bulk_m3"] = float(
                    np.sum(end_mobile * self.sand_frac - start_mobile * start_fraction))
                record["gravity_ledger"]["actual_raw_residual_mud_bulk_m3"] = float(
                    np.sum(end_mobile * (1. - self.sand_frac.astype(np.float64))
                           - start_mobile * (1. - start_fraction.astype(np.float64))))
                for label, value in (("start_sand_fraction", start_fraction),
                                     ("end_sand_fraction", self.sand_frac),
                                     ("start_active_layer", start_active),
                                     ("end_active_layer", self.active_layer)):
                    record[label] = readonly(value)
                if not relaxed.converged:
                    self.rejected_gravity = self.phase_records.pop()
                    raise ValueError("gravity mobile slopes did not converge within fixed sweep budget")

    model = RecordedModel(Length=shape[0] * config.dx_m,
                          Width=shape[1] * config.dx_m, dx=config.dx_m,
                          L0_meters=config.inlet_length_m, N0_meters=config.inlet_width_m,
                          h0=config.inlet_depth_m, hb=config.inlet_depth_m, u0=config.inlet_velocity_m_s,
                          C0_percent=config.sediment_concentration_percent, f_bedload=config.sand_fraction,
                          Np_water=config.water_parcels, Np_sed=config.sediment_parcels,
                          itermax=config.water_iterations, seed=config.seed, H_SL=sea_level,
                          SLR=0., toggle_subsidence=False, force_deposit=False, defer_output=True,
                          save_checkpoint=False,
                          resume_checkpoint=False if resume_checkpoint is None else str(resume_checkpoint))
    if water_routing_repair or diagnostic_water_repair:
        from .metric_fluvial_water_repair import WaterRoutingRepair
        model.water_repair = WaterRoutingRepair()
    if diagnostic_water_routing:
        from .metric_fluvial_water_diagnostic import WaterRoutingDiagnostic
        model.water_routing_diagnostic = WaterRoutingDiagnostic()
    if water_routing_repair and (model.stepmax != 570 or model._sr.stepmax != 570 or model._mr.stepmax != 570):
        raise ValueError("water repair requires unchanged native 570 routing budgets")
    routing_budget_diagnostic = None
    if diagnostic_sediment_stepmax is not None:
        native_stepmax = int(model.stepmax)
        if native_stepmax != 570 or model.force_deposit:
            raise ValueError("sediment routing-budget diagnostic requires native 570 cap and force_deposit false")
        model._sr.stepmax = diagnostic_sediment_stepmax
        model._mr.stepmax = diagnostic_sediment_stepmax
        routing_budget_diagnostic = {
            "schema": "single-step-sediment-routing-budget-v1", "diagnostic_only": True,
            "base_algorithm_version": algorithm_version, "base_mechanism_identity": mechanism_identity,
            "native_water_stepmax": int(model.stepmax),
            "native_sand_stepmax": int(model._sr.stepmax), "native_mud_stepmax": int(model._mr.stepmax),
            "force_deposit": bool(model.force_deposit), "native_alpha": float(model.alpha),
            "native_diffusion_multiplier": float(model.diffusion_multiplier),
            "checkpoint_start_sha256": previous_checkpoint_hash,
            "material_state_start_sha256": previous_material_hash,
            "semantics": "terminal scratch diagnostic; only sand/mud router stepmax assigned after checkpoint restore; original route functions reused; native model/water stepmax, forcing, diffusion and exchange unchanged"}
        if diagnostic_water_routing:
            routing_budget_diagnostic["read_only_water_routing_observation"] = True
            if diagnostic_water_repair:
                model.water_repair_candidate = True
                routing_budget_diagnostic.update(
                    read_only_water_routing_observation=False,
                    water_routing_observer_semantics="observer records without changing routing; separate candidate mechanisms modify water routing and flux accounting",
                    semantics="terminal scratch diagnostic; sand/mud router stepmax assigned after checkpoint restore; water candidate masks row0 upstream inlet weights and accounts accepted wet D8 loop-return connections with native update_Q; changed water estimates and inlet boundary choices feed back into later parcel paths; native water stepmax, forcing, diffusion and sediment exchange unchanged",
                    water_loop_relocation_repair="deterministic-d8-wet-connection-native-flux-v1",
                    water_inlet_repair="row0-inlet-upstream-weight-mask-v1",
                    relocation_rejection="retain original proposal and native free-surface flags; reject outside/wall/dry and illegal diagonal sides using current iteration depth>dry_depth",
                    relocation_accounting="each accepted missing segment calls original native update_Q both endpoints; native RNG and water surface solver unchanged")
        mechanism_identity = hashlib.sha256(json.dumps(routing_budget_diagnostic, sort_keys=True).encode("utf-8")).hexdigest()
    initial = model.eta.copy().astype(np.float64)
    if gravity_stability:
        model.mobile_base = np.minimum(model.source_bed, initial) if resumed_mobile_base is None else resumed_mobile_base
        if (model.mobile_base.shape != initial.shape or not np.isfinite(model.mobile_base).all()
                or np.any(model.mobile_base > initial + 2e-6)):
            raise ValueError("finite saved mobile base below current bed required")
        initial_mobile_base = model.mobile_base.copy()
    start_time, start_step = model.time, model.time_iter
    physical_initial = model.prepared_bed.copy()
    if mapped is not None:
        physical_initial[:model.L0, model.inlet] = sea_level - model.h0
    canonical_initial = physical_initial.astype(np.float32).astype(np.float64)
    initial_delta = canonical_initial - model.prepared_bed
    physical_initial_delta = physical_initial - model.prepared_bed
    representation_delta = canonical_initial - physical_initial
    fields = {name: [getattr(model, native).copy()] for name, native in
              (("beds_m", "eta"), ("depths_m", "depth"), ("stages_m", "stage"), ("qx_m2_s", "qx"), ("qz_m2_s", "qy"))}
    velocity_fields = (("ux_m_s", "ux"), ("uz_m_s", "uy"), ("speed_m_s", "uw")) if gravity_stability else ()
    for name, native in velocity_fields:
        fields[name] = [getattr(model, native).copy()]
    times = [model.time]
    try:
        model._check_floor()
        for local_step in range(config.steps):
            model.update()
            times.append(model.time)
            for name, native in (("beds_m", "eta"), ("depths_m", "depth"), ("stages_m", "stage"),
                                 ("qx_m2_s", "qx"), ("qz_m2_s", "qy")) + velocity_fields:
                fields[name].append(getattr(model, native).copy())
            if progress_callback is not None and (model.time_iter % 16 == 0 or local_step + 1 == config.steps):
                progress_callback(model.time_iter, model.time)
        phases = tuple(model.phase_records)
        ledger = {key: math.fsum(item[key] for item in phases) for key in
                  ("injected_bulk_m3", "exported_bulk_m3", "lost_bulk_m3", "inlet_correction_bulk_m3", "raw_residual_bulk_m3")}
        ledger["bed_change_bulk_m3"] = float((model.eta.astype(np.float64) - initial).sum() * config.dx_m ** 2)
        ledger["declared_boundary_input_bulk_m3"] = model.Qs0 * (model.time - start_time)
        ledger["boundary_sampling_uninjected_bulk_m3"] = ledger["declared_boundary_input_bulk_m3"] - ledger["injected_bulk_m3"]
        ledger["diffusion_raw_change_bulk_m3"] = math.fsum(float(item["delta_bulk_m3"].sum()) for item in phases if item["phase"] == "diffusion")
        checkpoint_directory = output_dir / "backend"
        checkpoint_directory.mkdir(parents=True, exist_ok=True)
        model.save_the_checkpoint()
        checkpoint_hash = hashlib.sha256((checkpoint_directory / "checkpoint.npz").read_bytes()).hexdigest()
        material_hash = None
        if gravity_stability:
            material_path = checkpoint_directory / "adapter-material-state.npz"
            np.savez_compressed(material_path, mobile_base_m=model.mobile_base)
            material_hash = hashlib.sha256(material_path.read_bytes()).hexdigest()
        continuation = {
            "continuation_identity": continuation_identity, "checkpoint_sha256": checkpoint_hash,
            "algorithm_version": algorithm_version,
            "native_end_step_index": model.time_iter, "end_time_s": model.time}
        if gravity_stability:
            continuation.update(mechanism_identity=mechanism_identity, material_state_sha256=material_hash)
        if routing_dry_depth_m is not None:
            continuation["routing_dry_depth_m"] = routing_dry_depth_m
        if quantized_native_exchange:
            continuation["quantized_native_exchange"] = True
        if water_routing_repair:
            continuation.update(water_routing_repair=True, water_repair_mechanisms=dict(WATER_REPAIR_MECHANISMS))
        if diffusion_diagnostic_declaration is not None:
            mechanism_identity = hashlib.sha256(
                json.dumps(diffusion_diagnostic_declaration, sort_keys=True).encode("utf-8")
            ).hexdigest()
            continuation.update(
                diagnostic_only=True,
                diagnostic_diffusion_ablation=diffusion_diagnostic_declaration,
                effective_diffusion_enabled=effective_diffusion_enabled,
                mechanism_identity=mechanism_identity,
            )
        if routing_budget_diagnostic is not None:
            continuation.update(diagnostic_only=True, sediment_routing_budget_diagnostic=routing_budget_diagnostic)
        (checkpoint_directory / "adapter-continuation.json").write_text(json.dumps(continuation, indent=2), encoding="utf-8")
        metadata = {"algorithm_version": algorithm_version, "backend": "pyDeltaRCM", "backend_version": BACKEND_VERSION,
                    "config": asdict(config), "dx_m": config.dx_m, "sea_level_m": sea_level,
                    "maximum_original_source_cut_m": config.maximum_original_source_cut_m,
                    "source_floor_tolerance_m": 2e-6,
                    "native_dt_s": model.dt, "native_water_discharge_m3_s": model.Qw0,
                    "native_sediment_bulk_discharge_m3_s": model.Qs0,
                    "native_parcel_bulk_m3": model.Vp_sed, "solid_fraction": 1. - config.porosity,
                    "volume_semantics": "native sediment is bulk bed volume; homogeneous source and deposit packing; solid=bulk*(1-porosity)",
                    "water_semantics": "iterative steady field, not transient water-volume conservation",
                    "floor_semantics": "reject a complete proposed phase before publication; no post-hoc bed clipping or fabricated export",
                    "erosion_semantics": "native parcel erosion law and stable-volume limit, additionally capped at current original-source available bulk before parcel/bed exchange" if source_limited_erosion else "unmodified native parcel erosion exchange; proposed phase floor rejection only",
                    "mechanism_transition": mechanism_transition,
                    "diffusion_semantics": "native eight-neighbor coefficient with closed pair fluxes and source-floor donor limits; native/disabled modes are explicit controls",
                    "boundary_semantics": "official control uses native boundaries" if mapped is None else "mapped downstream support; upstream and lateral walls, only registered downstream ocean exports",
                    "initialization_bulk_m3": float(initial_delta.sum() * config.dx_m ** 2),
                    "physical_initialization_bulk_m3": float(physical_initial_delta.sum() * config.dx_m ** 2),
                    "initial_float32_representation_bulk_m3": float(representation_delta.sum() * config.dx_m ** 2),
                    "water_input_m3": model.Qw0 * (model.time - start_time),
                    "native_start_step_index": start_step, "native_end_step_index": model.time_iter,
                    "start_time_s": start_time, "end_time_s": model.time,
                    "continuation_identity": continuation_identity,
                    "checkpoint_start_path": None if resume_checkpoint is None else str(resume_checkpoint / "checkpoint.npz"),
                    "checkpoint_start_sha256": previous_checkpoint_hash,
                    "checkpoint_end_path": str((checkpoint_directory / "checkpoint.npz").resolve()),
                    "checkpoint_end_sha256": checkpoint_hash,
                    "forcing_semantics": "constant positive physical boundary; actual native dt, no morphological time acceleration"}
        result = {"initial_bed_m": readonly(initial), "final_bed_m": readonly(model.eta),
                  "times_s": readonly(np.asarray(times)), "phases": phases, "ledger": ledger,
                  "bulk_ledger": ledger, "solid_ledger": {key.replace("bulk", "solid"): value * (1. - config.porosity) for key, value in ledger.items()},
                  "backend_source_bed_m": readonly(model.source_bed), "backend_prepared_bed_m": readonly(model.prepared_bed),
                  "backend_initialization_delta_m": readonly(initial_delta), "metadata": metadata,
                  "backend_physical_initialization_delta_m": readonly(physical_initial_delta),
                  "backend_initial_representation_delta_m": readonly(representation_delta),
                  "mapping": mapping, "cell_type": readonly(model.cell_type)}
        result.update({name: readonly(np.stack(values)) for name, values in fields.items()})
        if gravity_stability:
            metadata.update(gravity_parameters=dict(GRAVITY_PARAMETERS), mechanism_identity=mechanism_identity,
                material_state_start_sha256=previous_material_hash, material_state_end_sha256=material_hash,
                material_state_start_path=None if previous_material_hash is None else str(resume_checkpoint / "adapter-material-state.npz"),
                material_state_end_path=str(checkpoint_directory / "adapter-material-state.npz"),
                mobile_base_semantics="initialized at v3 start as min(original source, actual bed); lowered only by actual native phase endpoints; fixed during gravity and checkpoint-restored",
                gravity_semantics="closed eight-neighbor conservative mobile-column transfer after native finalize; surface fraction approximates a uniform mobile column; gravity-only sand/mud conservation",
                gravity_water_semantics="changed-cell depth/velocity synchronized with native sediment exchange formula and speed cap, existing stage/discharge preserved; native approximate steady flow recomputed on next native step")
            result["initial_mobile_base_m"] = readonly(initial_mobile_base)
            result["final_mobile_base_m"] = readonly(model.mobile_base)
        if routing_dry_depth_m is not None:
            metadata.update(routing_dry_depth_m=routing_dry_depth_m,
                native_water_dry_depth_m=float(model.dry_depth),
                native_sand_router_dry_depth_m=float(model._sr.dry_depth),
                native_mud_router_dry_depth_m=float(model._mr.dry_depth),
                routing_depth_semantics="independent .01m numerical routing thin-layer sensitivity; physical forcing, inherited bed/water/stage/RNG and morphology thresholds unchanged")
        if quantized_native_exchange:
            from .metric_fluvial_native_routers import source_limited_router_classes
            classes = source_limited_router_classes(observe_native_exchange, True)
            metadata.update(quantized_native_exchange=True,
                exchange_precision_semantics="native exchange law/limits reused; accepted volume projected toward zero to actual float32 bed lattice; same volume updates float64 parcel/deposition/boundary counters; unrepresentable amount remains in parcel or bed; negative/nonfinite cap rejected before physical update; no phase residual redistribution",
                native_exchange_precision={"bed_dtype": str(model.eta.dtype),
                    "sand_deposition_dtype": str(model.Vp_dep_sand.dtype), "mud_deposition_dtype": str(model.Vp_dep_mud.dtype),
                    "routers": {name: {key: str(cls.class_type.struct[key]) for key in
                        ("Vp_sed", "Vp_res", "Vp_exported", "Vp_lost", "Vp_dep_sand", "Vp_dep_mud")}
                        for name, cls in zip(("mud", "sand"), classes)}})
        if water_routing_repair:
            metadata.update(water_routing_repair=True, water_repair_mechanisms=dict(WATER_REPAIR_MECHANISMS),
                water_routing_repair_statistics=model.water_repair.iterations,
                water_repair_semantics="current wet valid D8 loop-return connections accounted with native update_Q; row0 inlet upstream weights removed; water estimates feed back into subsequent parcel paths; original surface solver and sediment exchange retained")
        if routing_budget_diagnostic is not None:
            metadata.update(diagnostic_only=True, sediment_routing_budget_diagnostic=routing_budget_diagnostic)
            result["diagnostic_pre_sediment_fields"] = {
                key: readonly(value) for key, value in model.diagnostic_pre_sediment_fields.items()}
        if diagnostic_water_routing:
            result["diagnostic_water_routing_observation"] = model.water_routing_diagnostic.archive()
        if diffusion_diagnostic_declaration is not None:
            metadata.update(
                diagnostic_only=True,
                diagnostic_diffusion_ablation=diffusion_diagnostic_declaration,
                effective_diffusion_enabled=effective_diffusion_enabled,
                mechanism_identity=mechanism_identity,
            )
        if observe_native_exchange:
            from .metric_fluvial_native_routers import (
                OBSERVATION_COUNT_FIELDS, OBSERVATION_VALUE_FIELDS, OBSERVATION_DEPTH_BOUNDS_M,
            )
            observation_metadata = {
                "schema": "native-exchange-observation-v1",
                "start_step": start_step, "end_step": model.time_iter,
                "checkpoint_start_sha256": previous_checkpoint_hash,
                "mechanism_identity": mechanism_identity,
                "count_fields": OBSERVATION_COUNT_FIELDS, "value_fields": OBSERVATION_VALUE_FIELDS,
                "depth_upper_bounds_m": OBSERVATION_DEPTH_BOUNDS_M,
                "depth_categories": ("depth <= lower", "lower < depth <= upper", "depth > upper"),
                "native_parameters": {key: float(getattr(model, key)) for key in
                                      ("S0", "gamma", "U_dep_mud", "U_ero_mud", "U_ero_sand", "qs0")},
                "semantics": "per-cell cumulative counts/values across this run only; visits count exchange routine calls, not unique parcel visits; categories and pre-field sums use native depth/stage/speed immediately before exchange; raw signed deposition proposal and native accepted volume read directly at native limiter (also final accepted deposition, since source-floor availability caps erosion only); erosion actual is limiter return after source-floor availability; limiter volumes are not float32 bed-write measured volumes, which remain in the phase ledger; no material attribution or acceptance gate",
                "capacity_diagnostic": "qs_cap is native method-local and is not observed; no copied capacity formula",
                "cohort_semantics": "all cells recorded; any fixed cohort must be separately bound to an immutable saved reference",
            }
            if quantized_native_exchange:
                observation_metadata["semantics"] = "per-cell cumulative counts/values across this run only; visits count exchange routine calls, not unique parcel visits; categories and pre-field sums use native depth/stage/speed immediately before exchange; raw signed deposition proposal and native accepted volume are read directly before representable-bed quantization; erosion actual is final quantized limiter return after source-floor availability; phase ledger measures stored-bed changes; no material attribution or acceptance gate"
                observation_metadata["quantized_exchange_semantics"] = "deposition_native_accepted is before representable-bed quantization, not final deposition; erosion_actual is the final quantized limiter return after source-floor availability; measured bed volume remains in phase ledger"
            observation_arrays = {}
            for name, router in (("sand", model._sr), ("mud", model._mr)):
                observation_arrays[name + "_counts"] = router.observation_counts.copy()
                observation_arrays[name + "_values"] = router.observation_values.copy()
            observation_path = output_dir / "native-exchange-observation.npz"
            np.savez_compressed(observation_path, **observation_arrays,
                                metadata_json=np.array(json.dumps(observation_metadata, sort_keys=True)))
            metadata["native_exchange_observation"] = {
                "path": str(observation_path),
                "sha256": hashlib.sha256(observation_path.read_bytes()).hexdigest(),
                "schema": observation_metadata["schema"],
            }
        if mapped is not None:
            result["source_arrays"] = mapped
        return result
    except Exception as error:
        completed = model.phase_records
        failed_phase_data = {}
        if completed:
            for key in ("start_bed_m", "end_bed_m", "delta_bulk_m3", "step_index", "injected_bulk_m3",
                        "exported_bulk_m3", "lost_bulk_m3", "inlet_correction_bulk_m3", "raw_residual_bulk_m3"):
                failed_phase_data["completed_phase_" + key] = np.asarray([item[key] for item in completed])
            failed_phase_data["completed_phase_names"] = np.asarray([item["phase"] for item in completed])
        if gravity_stability:
            failed_phase_data["mobile_base_m"] = model.mobile_base
            failed_phase_data["sand_fraction"] = model.sand_frac
            failed_phase_data["active_layer"] = model.active_layer
            gravity = [item for item in completed if item["phase"] == "gravity"]
            if gravity:
                failed_phase_data["gravity_ledger_json"] = np.array(json.dumps([item["gravity_ledger"] for item in gravity]))
                for key in ("start_sand_fraction", "end_sand_fraction", "start_active_layer", "end_active_layer"):
                    failed_phase_data["gravity_" + key] = np.asarray([item[key] for item in gravity])
            rejected = getattr(model, "rejected_gravity", None)
            if rejected is not None:
                for key in ("start_bed_m", "end_bed_m", "start_sand_fraction", "end_sand_fraction",
                            "start_active_layer", "end_active_layer"):
                    failed_phase_data["rejected_gravity_" + key] = rejected[key]
                failed_phase_data["rejected_gravity_ledger_json"] = np.array(json.dumps(rejected["gravity_ledger"]))
                failed_phase_data["rejected_gravity_step_index"] = np.array(rejected["step_index"])
        np.savez_compressed(output_dir / "failed-native-state.npz", proposed_bed_m=model.eta,
                            source_bed_m=model.source_bed, successful_beds_m=np.stack(fields["beds_m"]),
                            proposed_start_bed_m=getattr(model, "proposed_start_bed", initial),
                            metadata_json=np.array(json.dumps({"error": str(error), "config": asdict(config),
                                                               "successful_times_s": times, "mapping": mapping,
                                                               "proposed_phase": getattr(model, "proposed_phase", None)})),
                            **failed_phase_data)
        raise
    finally:
        try:
            model.finalize()
        finally:
            for handler in tuple(model.logger.handlers):
                handler.close()
                model.logger.removeHandler(handler)
