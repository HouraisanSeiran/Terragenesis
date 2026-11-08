"""Current FV checkpoint codec and real source identities; no solver import."""
import ast
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "finite-FV-growth-checkpoint-v4"
IMPLEMENTATION_RECIPE = "FV-current-v4-explicit-operators-transactional-v1"
STATE = ("bed_m", "depth_m", "momentum_m2_s", "suspended_solid_m3")
ARRAY_KEYS = frozenset({*STATE, "source_floor_m", "cell_type", "initial_bed_m", "local_world_xz_m",
                        "fixed_boundary_mask", "source_schedule"})
CONTRACT = {"schema": "same-direction-net-carrier-finite-bedload-v4",
    "solid_capacity_fraction": "1-porosity", "layer_height_bound": "carrier wet section",
    "normal_grain_speed_bound": "same-direction net carrier speed",
    "counterflow": "MPM requests opposite to interval net water transfer rejected and recorded",
    "waves": "vectorized Airy field; frozen 16 phase MPM and exchange formulas",
    "limitation": "no oscillatory gross flux or wave-driven counterflow representation"}
CAPTURE_FIELDS = ("mpm_internal_requested_solid_m3", "carrier_internal_capacity_solid_m3",
    "carrier_internal_accepted_solid_m3", "mpm_boundary_requested_solid_m3",
    "carrier_boundary_capacity_solid_m3", "carrier_boundary_accepted_solid_m3")
PHYSICAL_PARAMETERS = ("source_time_scale", "max_input_concentration", "supply_off", "river_q", "sea_mean",
    "tide_amplitude", "tide_period", "tide_phase", "wave_height", "wave_period", "settling_velocity",
    "max_bed_change", "disable_exchange", "erosion_velocity", "exchange_max_concentration", "disable_slope",
    "critical_slope", "slope_mobility")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identities():
    """Hash the actual current local import closure, including new common code."""
    pending = ["tools/run_natural_fv_growth_v4.py", "tools/run_natural_fv_growth.py"]
    records = {}
    while pending:
        relative = pending.pop()
        if relative in records:
            continue
        path = ROOT / relative
        raw = path.read_bytes()
        records[relative] = hashlib.sha256(raw).hexdigest()
        for parent in path.parents:
            if parent == ROOT:
                break
            initial = parent / "__init__.py"
            if initial.is_file():
                pending.append(initial.relative_to(ROOT).as_posix())
        tree = ast.parse(raw.decode("utf-8-sig"), filename=relative)
        module = relative[:-3].replace("/", ".")
        package = module[:-9] if module.endswith(".__init__") else module.rsplit(".", 1)[0]
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = ".".join(package.split(".")[:len(package.split(".")) - node.level + 1]) if node.level else ""
                base = ".".join(value for value in (prefix, node.module) if value)
                targets = [base] + [base + "." + alias.name for alias in node.names]
            for name in targets:
                if name.split(".")[0] not in ("terrain_pipeline", "tools", "diffusion"):
                    continue
                candidate = ROOT / (name.replace(".", "/") + ".py")
                package_file = ROOT / name.replace(".", "/") / "__init__.py"
                if candidate.is_file():
                    pending.append(candidate.relative_to(ROOT).as_posix())
                elif package_file.is_file():
                    pending.append(package_file.relative_to(ROOT).as_posix())
    return dict(sorted(records.items()))


def read_arrays(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if (len(members) > 128 or len({item.filename for item in members}) != len(members)
                or sum(item.file_size for item in members) > 512 * 1024 ** 2):
            raise ValueError("FV archive exceeds expanded byte budget or has duplicate entries")
    with np.load(path, allow_pickle=False) as saved:
        return {key: saved[key].copy() for key in saved.files}


def validate_state(data, meta):
    if set(data) != ARRAY_KEYS:
        raise ValueError("complete FV state array set required")
    bed = data["bed_m"]
    if bed.ndim != 2 or not bed.size or bed.size > 1048576:
        raise ValueError("bounded 2D FV bed required")
    for key in ("depth_m", "suspended_solid_m3", "source_floor_m", "initial_bed_m", "cell_type", "fixed_boundary_mask"):
        if data[key].shape != bed.shape:
            raise ValueError("FV state shape mismatch: " + key)
    if data["momentum_m2_s"].shape != (bed.size, 2) or data["local_world_xz_m"].shape != (*bed.shape, 2):
        raise ValueError("FV momentum or coordinates shape mismatch")
    if data["cell_type"].dtype.kind not in "iu" or data["fixed_boundary_mask"].dtype != np.bool_:
        raise ValueError("FV cell types or fixed mask dtype mismatch")
    for key, value in data.items():
        if not isinstance(value, np.ndarray) or not np.isfinite(value).all():
            raise ValueError("nonfinite FV state: " + key)
    if np.any(data["depth_m"] < 0.) or np.any(data["suspended_solid_m3"] < 0.) or np.min(bed - data["source_floor_m"]) < -2.e-6:
        raise ValueError("negative FV water/material inventory or below finite floor")
    if np.any(data["momentum_m2_s"][data["depth_m"].ravel() == 0.] != 0.):
        raise ValueError("dry FV cells retain momentum")
    schedule = data["source_schedule"]
    if schedule.ndim != 2 or schedule.shape[1] != 6 or np.any(schedule[:, 4] <= 0.) or np.any(schedule[:, 3] < 0.):
        raise ValueError("finite nonnegative six-column source schedule required")
    for key in ("physical_time_s", "source_cursor_s", "cumulative_injected_solid_m3", "cumulative_exported_solid_m3", "source_total_solid_m3"):
        value = meta.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0.:
            raise ValueError("finite nonnegative FV metadata required: " + key)
    if abs(float(schedule[:, 3].sum()) - meta["source_total_solid_m3"]) > 1.e-8:
        raise ValueError("finite source quota differs from source schedule")
    ends = np.cumsum(schedule[:, 4])
    overlap = np.maximum(0., np.minimum(ends, meta["source_cursor_s"]) - (ends - schedule[:, 4]))
    consumed = float(np.sum(schedule[:, 3] * overlap / schedule[:, 4]))
    if abs(consumed - meta["cumulative_injected_solid_m3"]) > 1.e-8:
        raise ValueError("FV source cursor/cumulative injected inventory mismatch")
    evolved = any(meta[key] != 0. for key in
        ('physical_time_s', 'source_cursor_s', 'cumulative_injected_solid_m3', 'cumulative_exported_solid_m3'))
    if evolved and 'run_parameters' not in meta:
        raise ValueError('evolved current FV checkpoint needs bound run parameters')
    if 'run_parameters' in meta and set(meta['run_parameters']) != set(PHYSICAL_PARAMETERS):
        raise ValueError('complete current FV physical/source parameter binding required')
    return True


def load_checkpoint(path, *, expected_sha256=None):
    before = file_sha256(path)
    if expected_sha256 is not None and before != expected_sha256:
        raise ValueError("current FV checkpoint external SHA256 mismatch")
    saved = read_arrays(path)
    meta = json.loads(str(saved.pop("metadata_json")))
    if (meta.get("schema") != SCHEMA or meta.get("implementation_recipe") != IMPLEMENTATION_RECIPE
            or meta.get("implementation_hashes") != identities() or meta.get("bedload_transport_contract") != CONTRACT):
        raise ValueError("current v4 checkpoint identity mismatch; legacy requires explicit verified migration/replay")
    validate_state(saved, meta)
    if file_sha256(path) != before:
        raise ValueError("FV checkpoint changed while loading")
    meta.update(resumed_checkpoint=str(path), resumed_checkpoint_sha256=before)
    return saved, meta


def save_checkpoint(path, data, meta):
    validate_state(data, meta)
    if "run_parameters" not in meta and any(meta[key] != 0. for key in
            ("physical_time_s", "source_cursor_s", "cumulative_injected_solid_m3", "cumulative_exported_solid_m3")):
        raise ValueError("evolved current FV checkpoint needs bound run parameters")
    meta.update(schema=SCHEMA, implementation_recipe=IMPLEMENTATION_RECIPE,
                implementation_hashes=identities(), bedload_transport_contract=deepcopy(CONTRACT))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, **data, metadata_json=json.dumps(meta, allow_nan=False))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def bind_parameters(meta, args):
    selected = {name: getattr(args, name) for name in PHYSICAL_PARAMETERS}
    if "run_parameters" in meta and meta["run_parameters"] != selected:
        raise ValueError("FV physical/source parameters changed; explicit separate model transition required")
    meta["run_parameters"] = selected


def migrate_legacy_checkpoint(path, expected_sha256, output, *, parameters, parameters_sha256, upgrade_physics=False):
    """Explicit cold state migration; it never advances water or sediment."""
    from tools.replay_natural_fv_growth_legacy import read_legacy_checkpoint, MANIFEST_SHA256
    if file_sha256(parameters) != parameters_sha256:
        raise ValueError("legacy FV parameter template SHA256 mismatch")
    data, original = read_legacy_checkpoint(path, expected_sha256)
    source_schema = original["schema"]
    if source_schema != SCHEMA and not upgrade_physics:
        raise ValueError("v1/v2/v3 to v4 is a physical upgrade, not a structural migration")
    record = json.loads(Path(parameters).read_text(encoding="utf-8"))
    if "checkpoint_sha256" in record and record["checkpoint_sha256"] != expected_sha256:
        raise ValueError("legacy FV summary does not bind the selected checkpoint")
    supplied = dict(record.get("parameters", record))
    if "exchange_config" in original and source_schema in ("finite-FV-growth-checkpoint-v3", SCHEMA):
        expected_exchange = {"enabled": not supplied.get("disable_exchange"),
            "erosion_velocity_m_s": supplied.get("erosion_velocity"),
            "maximum_concentration": supplied.get("exchange_max_concentration"),
            "slope_enabled": not supplied.get("disable_slope"),
            "critical_slope_m_m": supplied.get("critical_slope"),
            "slope_mobility_m2_s": supplied.get("slope_mobility")}
        if original["exchange_config"] != expected_exchange:
            raise ValueError("legacy FV template exchange parameters disagree with checkpoint")
    if source_schema in ("finite-FV-growth-checkpoint-v1", "finite-FV-growth-checkpoint-v2") and upgrade_physics:
        supplied.update(disable_exchange=False, erosion_velocity=1.e-5, exchange_max_concentration=.03,
                        disable_slope=False, critical_slope=.35, slope_mobility=.02)
    if not set(PHYSICAL_PARAMETERS) <= set(supplied):
        raise ValueError("complete physical/source parameter template required for FV state migration")
    meta = deepcopy(original)
    meta["legacy_checkpoint_migration"] = meta.pop("checkpoint_migration", None)
    meta["legacy_implementation_hashes"] = deepcopy(original["implementation_hashes"])
    meta["run_parameters"] = {name: supplied[name] for name in PHYSICAL_PARAMETERS}
    meta["checkpoint_migration"] = {"from_schema": source_schema, "source": str(Path(path).resolve()),
        "source_sha256": expected_sha256, "legacy_manifest_sha256": MANIFEST_SHA256,
        "parameter_template": str(Path(parameters).resolve()), "parameter_template_sha256": parameters_sha256,
        "physical_upgrade": source_schema != SCHEMA,
        "policy": "verified original signatures; exact complete state copy; new implementation identity; no physical step"}
    output = Path(output)
    if output.exists() or output.resolve() == Path(path).resolve():
        raise FileExistsError("FV migration requires a new checkpoint path")
    if file_sha256(path) != expected_sha256 or file_sha256(parameters) != parameters_sha256:
        raise ValueError("FV migration parent or template changed")
    save_checkpoint(output, data, meta)
    return data, meta
