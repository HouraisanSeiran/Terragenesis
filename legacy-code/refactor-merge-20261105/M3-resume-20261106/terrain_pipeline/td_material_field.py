"""Continuous synthetic materials sampled in global metre coordinates."""

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.common_infra import checked_archive, file_sha256


ALGORITHM = "td-continuous-global-value-noise-v1"
MAX_BYTES = 1024 ** 3
MAX_CELLS = 1024 ** 2
DEFAULT_PARAMETERS = {
    "erodibility_range": [0.25, 1.0],
    "erodible_thickness_range_m": [0.25, 4.0],
    "weak_path_preference_range": [0.8, 1.2],
    "correlation_length_m": 900.0,
    "solid_density_kg_m3": 2650.0,
    "source_porosity": 0.10,
    "deposit_porosity": 0.35,
}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(arrays, metadata):
    digest = hashlib.sha256(_json(metadata).encode("utf-8"))
    for name, values in sorted(arrays.items()):
        digest.update(name.encode("utf-8"))
        digest.update(values.dtype.str.encode("ascii"))
        digest.update(_json(list(values.shape)).encode("ascii"))
        digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def _bundle(arrays, metadata):
    frozen = {}
    for name, values in arrays.items():
        contiguous = np.ascontiguousarray(values)
        frozen[name] = np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)
    metadata = json.loads(_json(metadata))
    return {"arrays": frozen, "metadata": metadata, "identity_sha256": _identity(frozen, metadata)}


def _check_identity(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid bundle structure")
    if _identity(bundle["arrays"], bundle["metadata"]) != bundle["identity_sha256"]:
        raise ValueError("bundle identity mismatch")


def _positive(value, name, allow_zero=False):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(name + " must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        raise ValueError(name + " outside finite valid range")
    return result


def _parameters(parameters):
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown material parameters")
    result = {**DEFAULT_PARAMETERS, **supplied}
    for name in ("erodibility_range", "erodible_thickness_range_m", "weak_path_preference_range"):
        values = result[name]
        if len(values) != 2:
            raise ValueError(name + " needs two bounds")
        low = _positive(values[0], name, allow_zero=True)
        high = _positive(values[1], name, allow_zero=True)
        if low > high or (name == "erodibility_range" and high > 1):
            raise ValueError(name + " invalid bounds")
        result[name] = [low, high]
    for name in ("correlation_length_m", "solid_density_kg_m3"):
        result[name] = _positive(result[name], name)
    for name in ("source_porosity", "deposit_porosity"):
        result[name] = _positive(result[name], name, allow_zero=True)
        if result[name] >= 1:
            raise ValueError(name + " must be < 1")
    return result


def _shape(shape):
    if len(shape) != 2 or any(isinstance(size, (bool, np.bool_)) or not isinstance(size, (int, np.integer)) or size <= 0 for size in shape):
        raise ValueError("shape must be two positive integers")
    result = tuple(map(int, shape))
    if math.prod(result) > MAX_CELLS:
        raise ValueError("material cell budget exceeded")
    return result


def _mask(values, shape, name):
    if values is None:
        return np.zeros(shape, bool)
    result = np.asarray(values)
    if result.shape != shape or result.dtype != np.dtype(bool):
        raise ValueError(name + " must be same-shape boolean array")
    return result


def _lattice_value(lattice_x, lattice_z, seed, channel):
    with np.errstate(over="ignore"):
        value = lattice_x.astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
        value = value ^ (lattice_z.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F))
        value = value ^ np.uint64(seed) ^ np.uint64(channel * 0x165667B19E3779F9)
        value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        value = value ^ (value >> np.uint64(31))
    return (value >> np.uint64(11)).astype(np.float64) / float(2 ** 53)


def _noise(global_x, global_z, scale, seed, channel):
    coordinate_x = global_x / scale
    coordinate_z = global_z / scale
    if np.any(np.abs(coordinate_x) > 2 ** 50) or np.any(np.abs(coordinate_z) > 2 ** 50):
        raise ValueError("global lattice coordinate exceeds precision budget")
    lattice_x = np.floor(coordinate_x).astype(np.int64)
    lattice_z = np.floor(coordinate_z).astype(np.int64)
    fraction_x = coordinate_x - lattice_x
    fraction_z = coordinate_z - lattice_z
    smooth_x = fraction_x ** 3 * (fraction_x * (fraction_x * 6 - 15) + 10)
    smooth_z = fraction_z ** 3 * (fraction_z * (fraction_z * 6 - 15) + 10)
    upper = _lattice_value(lattice_x, lattice_z, seed, channel) * (1 - smooth_x)
    upper += _lattice_value(lattice_x + 1, lattice_z, seed, channel) * smooth_x
    lower = _lattice_value(lattice_x, lattice_z + 1, seed, channel) * (1 - smooth_x)
    lower += _lattice_value(lattice_x + 1, lattice_z + 1, seed, channel) * smooth_x
    return upper * (1 - smooth_z) + lower * smooth_z


def make_material_field(shape, *, origin_m_xz, spacing_m, seed=20261002,
                        parameters=None, protected_mask=None):
    """Sample centres on the global grid; integer window offsets are exact."""
    shape = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, (bool, np.bool_)) or not 0 <= seed < 2 ** 64:
        raise ValueError("seed must be uint64")
    origin = np.asarray(origin_m_xz, dtype=np.float64)
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin_m_xz must contain two finite coordinates")
    grid_origin = origin / spacing
    if np.any(np.abs(grid_origin) > 2 ** 50) or not np.allclose(grid_origin, np.rint(grid_origin), rtol=0, atol=1e-8):
        raise ValueError("origin must align with global spacing grid")
    grid_origin = np.rint(grid_origin).astype(np.int64)
    config = _parameters(parameters)
    global_x = (grid_origin[0] + np.arange(shape[1], dtype=np.int64) + 0.5) * spacing
    global_z = (grid_origin[1] + np.arange(shape[0], dtype=np.int64) + 0.5) * spacing
    if not np.isfinite(global_x).all() or not np.isfinite(global_z).all():
        raise ValueError("global coordinate overflow")
    arrays = {"protected_mask": _mask(protected_mask, shape, "protected_mask")}
    for channel, (name, range_name) in enumerate((
        ("erodibility", "erodibility_range"),
        ("erodible_thickness_m", "erodible_thickness_range_m"),
        ("weak_path_preference", "weak_path_preference_range")), start=1):
        low, high = config[range_name]
        noise = _noise(global_x[None, :], global_z[:, None], config["correlation_length_m"], int(seed), channel)
        arrays[name] = np.clip(low + (high - low) * noise, low, high)
    metadata = {"algorithm": ALGORITHM, "format_version": 1, "shape": list(shape),
                "origin_m_xz": origin.tolist(), "spacing_m": spacing, "seed": int(seed),
                "parameters": config, "coordinate_convention": "X east; Z south; [z,x]; cell centres",
                "synthetic_material": True, "measured_lithology": False,
                "units": {"erodibility": "1", "erodible_thickness_m": "m", "weak_path_preference": "1"}}
    return _bundle(arrays, metadata)


def validate_material_field(bundle):
    _check_identity(bundle)
    metadata = bundle["metadata"]
    if metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != 1:
        raise ValueError("unsupported material identity")
    shape = _shape(metadata["shape"])
    config = _parameters(metadata["parameters"])
    arrays = bundle["arrays"]
    if set(arrays) != {"erodibility", "erodible_thickness_m", "weak_path_preference", "protected_mask"}:
        raise ValueError("material array names mismatch")
    _mask(arrays["protected_mask"], shape, "protected_mask")
    for name, range_name in (("erodibility", "erodibility_range"),
                             ("erodible_thickness_m", "erodible_thickness_range_m"),
                             ("weak_path_preference", "weak_path_preference_range")):
        values = arrays[name]
        low, high = config[range_name]
        if values.shape != shape or values.dtype != np.dtype("float64") or not np.isfinite(values).all() or np.any(values < low) or np.any(values > high):
            raise ValueError("invalid material array " + name)
    reference = make_material_field(shape, origin_m_xz=metadata["origin_m_xz"], spacing_m=metadata["spacing_m"],
                                    seed=metadata["seed"], parameters=config, protected_mask=arrays["protected_mask"])
    if reference["identity_sha256"] != bundle["identity_sha256"]:
        raise ValueError("material provenance mismatch")
    return True


def _save_bundle(bundle, path):
    _check_identity(bundle)
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".td-stage-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, **bundle["arrays"],
                                metadata_json=np.asarray(_json(bundle["metadata"])),
                                identity_sha256=np.asarray(bundle["identity_sha256"]))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
    return path


def _archive_headers(headers):
    if not {"metadata_json", "identity_sha256"} <= set(headers) or len(headers) > 32:
        raise ValueError("invalid bundle headers")
    for name, (shape, dtype) in headers.items():
        if name in ("metadata_json", "identity_sha256"):
            if shape != () or dtype.kind != "U" or dtype.itemsize > 4 * 1024 * 1024:
                raise ValueError("invalid metadata header")
        elif len(shape) not in (1, 2) or math.prod(shape) > MAX_CELLS or dtype not in (np.dtype("float64"), np.dtype("int64"), np.dtype(bool)):
            raise ValueError("invalid array header")


def _load_bundle(path, *, expected_sha256=None, expected_identity=None):
    if expected_sha256 is None and expected_identity is None:
        raise ValueError("external expected_sha256 or expected_identity required")
    for expected in (expected_sha256, expected_identity):
        if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected)):
            raise ValueError("external identity must be lowercase SHA256")
    archive = checked_archive(path, expected_sha256=expected_sha256 or file_sha256(path),
                              max_bytes=MAX_BYTES // 4, header_validator=_archive_headers)
    metadata = json.loads(str(archive.pop("metadata_json").item()))
    identity = str(archive.pop("identity_sha256").item())
    arrays = archive
    bundle = _bundle(arrays, metadata)
    if bundle["identity_sha256"] != identity:
        raise ValueError("stored identity mismatch")
    if expected_identity is not None and identity != expected_identity:
        raise ValueError("external bundle identity mismatch")
    return bundle


def save_material_field(bundle, path):
    validate_material_field(bundle)
    return _save_bundle(bundle, path)


def load_material_field(path, *, expected_sha256=None, expected_identity=None):
    """Read a saved field without sampling or advancing the generator."""
    bundle = _load_bundle(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
    _validate_cold_material(bundle)
    return bundle


def _validate_cold_material(bundle):
    _check_identity(bundle)
    metadata = bundle["metadata"]
    if metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != 1:
        raise ValueError("unsupported material format")
    shape = _shape(metadata["shape"])
    config = _parameters(metadata["parameters"])
    spacing = _positive(metadata["spacing_m"], "spacing_m")
    origin = np.asarray(metadata["origin_m_xz"], np.float64)
    seed = metadata["seed"]
    if origin.shape != (2,) or not np.isfinite(origin).all() or not np.allclose(origin / spacing, np.rint(origin / spacing), atol=1e-8, rtol=0):
        raise ValueError("invalid cold material coordinates")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2 ** 64:
        raise ValueError("invalid cold material seed")
    if set(bundle["arrays"]) != {"erodibility", "erodible_thickness_m", "weak_path_preference", "protected_mask"}:
        raise ValueError("material fields mismatch")
    _mask(bundle["arrays"]["protected_mask"], shape, "protected_mask")
    for name, range_name in (("erodibility", "erodibility_range"), ("erodible_thickness_m", "erodible_thickness_range_m"), ("weak_path_preference", "weak_path_preference_range")):
        values = bundle["arrays"][name]
        low, high = config[range_name]
        if values.shape != shape or values.dtype != np.dtype("float64") or not np.isfinite(values).all() or np.any(values < low) or np.any(values > high):
            raise ValueError("invalid cold material field")
