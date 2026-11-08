"""Read-only, externally pinned mountain sources and bounded artifact publication."""

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline.rainfall_runoff import _hash, _json, _strict_json


SCHEMA = "mountain-source-v1"
MAX_CELLS = 250_000
MAX_BYTES = 128 * 1024 * 1024
MAX_METADATA = 1_048_576
KINDS = {"legacy_td_game_conditioned", "terrain_diffusion_output"}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_archive(path, *, expected_sha256, max_bytes=MAX_BYTES, header_validator=None):
    """Check ZIP and NPY headers before allocating any array; never allow pickle."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("external archive SHA256 required")
    if Path(path).stat().st_size > max_bytes:
        raise ValueError("compressed archive byte budget exceeded")
    with open(path, "rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise ValueError("external archive hash mismatch")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            headers = {}
            if (not 1 <= len(members) <= 128 or
                    len({member.filename for member in members}) != len(members) or
                    sum(member.file_size for member in members) > max_bytes):
                raise ValueError("archive resource/duplicate member rejection")
            for member in members:
                if not member.filename.endswith(".npy") or "/" in member.filename:
                    raise ValueError("invalid archive member")
                with archive.open(member) as entry:
                    version = np.lib.format.read_magic(entry)
                    if version == (1, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_1_0(entry, max_header_size=4096)
                    elif version == (2, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_2_0(entry, max_header_size=4096)
                    else:
                        raise ValueError("unsupported NPY header")
                    if (dtype.hasobject or fortran or len(shape) > 3 or
                            any(size < 0 or size > 8_000_000 for size in shape) or
                            math.prod(shape) * dtype.itemsize + entry.tell() != member.file_size):
                        raise ValueError("unsafe NPY shape/dtype/size")
                    headers[member.filename[:-4]] = (shape, dtype)
            if header_validator is not None:
                header_validator(headers)
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            return {key: archive[key].copy() for key in archive.files}


def readonly(array):
    value = np.ascontiguousarray(array)
    return np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)


def identity(arrays, metadata):
    record = {"metadata": metadata, "arrays": {key: _hash(value) for key, value in sorted(arrays.items())}}
    return hashlib.sha256(_json(record).encode("utf-8")).hexdigest()


def publish_bytes(path, payload):
    """A hard link is the commit point; a racing existing destination wins."""
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def save_bundle(path, result, *, validator):
    validator(result)
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    manifest = _json({"metadata": result["metadata"], "identity_sha256": result["identity_sha256"]}).encode("utf-8")
    if len(manifest) > MAX_METADATA:
        raise ValueError("metadata budget exceeded")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=np.frombuffer(manifest, dtype=np.uint8), **result["arrays"])
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_bundle(path, *, expected_sha256, validator, max_bytes=MAX_BYTES, header_validator=None):
    arrays = checked_archive(path, expected_sha256=expected_sha256, max_bytes=max_bytes,
                             header_validator=header_validator)
    manifest = arrays.pop("manifest", None)
    if (manifest is None or manifest.dtype != np.uint8 or manifest.ndim != 1 or
            manifest.size > MAX_METADATA):
        raise ValueError("invalid manifest")
    record = _strict_json(manifest.tobytes().decode("utf-8"))
    if set(record) != {"metadata", "identity_sha256"}:
        raise ValueError("unexpected manifest keys")
    result = dict(record, arrays=arrays)
    validator(result)
    result["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return result


def make_source(height_m, *, origin_m_xz, spacing_m, provenance, boundary,
                display_mask=None, hydrology_mask=None, climate=None, domain=None):
    """Trusted in-process construction, not proof that supplied values came from TD."""
    height = np.asarray(height_m)
    if (height.ndim != 2 or not 1 <= height.size <= MAX_CELLS or
            height.dtype.kind not in "fiu" or not np.isfinite(height).all()):
        raise ValueError("invalid bounded real elevation grid")
    arrays = {"height_m": height.astype(np.float64)}
    for key, supplied in (("display_mask", display_mask), ("hydrology_mask", hydrology_mask)):
        arrays[key] = np.ones(height.shape, bool) if supplied is None else np.asarray(supplied)
    if climate is not None:
        arrays["climate"] = np.asarray(climate).astype(np.float64)
    metadata = _strict_json(_json({"schema": SCHEMA, "origin_m_xz": origin_m_xz,
        "spacing_m": spacing_m, "coordinates": "x east, z south; arrays [z,x]",
        "vertical_datum": "sea_zero_m", "provenance": provenance, "boundary": boundary,
        "domain": domain if domain is not None else {
            "calculation_domain": "finite_window_experiment",
            "hydrological_closure_certified": False,
            "closure_evidence_sha256": None,
            "land_boundary_crossing": "truncated_external_open_boundary"}}))
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_source(result)
    result["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return result


def validate_source(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if set(metadata) != {"schema", "origin_m_xz", "spacing_m", "coordinates", "vertical_datum", "provenance", "boundary", "domain"}:
        raise ValueError("unexpected source metadata")
    if (metadata["schema"] != SCHEMA or metadata["coordinates"] != "x east, z south; arrays [z,x]" or
            metadata["vertical_datum"] != "sea_zero_m" or
            set(arrays) not in ({"height_m", "display_mask", "hydrology_mask"},
                                {"height_m", "display_mask", "hydrology_mask", "climate"})):
        raise ValueError("source schema mismatch")
    provenance = metadata["provenance"]
    if (not isinstance(provenance, dict) or provenance.get("artifact_kind") not in KINDS or
            provenance.get("td_inference_run") is not True or
            not isinstance(provenance.get("archive_sha256"), str) or len(provenance["archive_sha256"]) != 64):
        raise ValueError("actual TD source required; conditioning_only forbidden")
    origin = metadata["origin_m_xz"]
    spacing = metadata["spacing_m"]
    if (not isinstance(origin, list) or len(origin) != 2 or
            any(type(value) not in (float, int) or not math.isfinite(value) for value in origin) or
            type(spacing) not in (float, int) or not math.isfinite(spacing) or not 0 < spacing <= 100000):
        raise ValueError("invalid metre grid")
    height = arrays["height_m"]
    if (height.ndim != 2 or height.dtype != np.float64 or not 1 <= height.size <= MAX_CELLS or
            not np.isfinite(height).all()):
        raise ValueError("invalid saved source height")
    for key in ("display_mask", "hydrology_mask"):
        if arrays[key].shape != height.shape or arrays[key].dtype != bool or not arrays[key].any():
            raise ValueError("invalid source domain")
    if (arrays["display_mask"] & ~arrays["hydrology_mask"]).any():
        raise ValueError("display domain outside hydrology domain")
    boundary = metadata["boundary"]
    domain = metadata["domain"]
    if (not isinstance(domain, dict) or set(domain) != {"calculation_domain", "hydrological_closure_certified",
            "closure_evidence_sha256", "land_boundary_crossing"} or
            domain["calculation_domain"] not in {"finite_window_experiment", "complete_contribution_subdomain"} or
            domain["hydrological_closure_certified"] is not False or domain["closure_evidence_sha256"] is not None or
            domain["land_boundary_crossing"] != "truncated_external_open_boundary"):
        raise ValueError("this adapter does not certify a complete hydrological planning domain")
    if (not isinstance(boundary, dict) or set(boundary) != {"policy", "halo_cells", "upstream_contribution"} or
            boundary["policy"] not in {"legacy_lowest_edge", "all_edges_open", "explicit"} or
            type(boundary["halo_cells"]) is not int or not 0 <= boundary["halo_cells"] < min(height.shape) or
            boundary["upstream_contribution"] not in {"full_domain", "excluded_finite_experiment", "explicit_forcing"}):
        raise ValueError("explicit boundary/domain declaration required")
    halo = boundary["halo_cells"]
    if halo and (arrays["display_mask"][:halo].any() or arrays["display_mask"][-halo:].any() or
                 arrays["display_mask"][:, :halo].any() or arrays["display_mask"][:, -halo:].any()):
        raise ValueError("display mask violates declared halo")
    if "climate" in arrays and (arrays["climate"].shape != (5,) + height.shape or
            arrays["climate"].dtype != np.float64 or not np.isfinite(arrays["climate"]).all()):
        raise ValueError("invalid five-channel climate")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("source identity mismatch")
    return True


def load_legacy_source(name, *, boundary_policy="legacy_lowest_edge"):
    from tools.verify_mountain_rainfall import EXPECTED, SOURCE_ROOT, load_source

    if name not in EXPECTED:
        raise ValueError("unknown fixed legacy source")
    checked_archive(SOURCE_ROOT / f"{name}.npz", expected_sha256=EXPECTED[name]["river"],
                    header_validator=_legacy_headers)
    source = load_source(name)
    if not source["raw_available"]:
        raise ValueError("pinned original TD archive required")
    checked_archive(source["raw_path"], expected_sha256=EXPECTED[name]["raw"])
    return make_source(source["height_m"], origin_m_xz=source["origin_m_xz"], spacing_m=source["spacing_m"],
        provenance={"artifact_kind": "legacy_td_game_conditioned", "td_inference_run": True,
            "name": name, "archive_sha256": EXPECTED[name]["river"],
            "raw_sha256": EXPECTED[name]["raw"], "provenance_sha256": source["sidecar_sha256"],
            "generation_identity": source["provenance"]["generation_identity"],
            "datum_shift_m": -source["provenance"]["core_sea_elevation_m"],
            "historical_game_height_conditioning": True,
            "limitation": "datum shift only; historical game-conditioned relief is unchanged"},
        boundary={"policy": boundary_policy, "halo_cells": 0, "upstream_contribution": "excluded_finite_experiment"})


def load_physical_source(path, *, expected_sha256, boundary, display_mask=None):
    arrays = checked_archive(path, expected_sha256=expected_sha256, header_validator=_physical_headers)
    if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("physical TD archive required; conditioning_only rejected")
    raw_meta = arrays["metadata_json"]
    if raw_meta.shape != () or raw_meta.dtype.kind != "U" or raw_meta.nbytes > MAX_METADATA:
        raise ValueError("invalid physical metadata")
    metadata = _strict_json(str(raw_meta.item()))
    if metadata.get("artifact_kind") != "terrain_diffusion_output":
        raise ValueError("conditioning_only is not TD output")
    from diffusion.physical_config import PhysicalGenerationConfig

    config = PhysicalGenerationConfig.from_record(metadata["config"])
    if metadata.get("schema") != "physical-generation-v1" or metadata["native_resolution_m"] != config.native_resolution_m:
        raise ValueError("physical source units/schema mismatch")
    base = {key: metadata[key] for key in ("schema", "config", "source_sha256", "elevation_units", "coordinates")}
    digest = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    generation = dict(base, **{key: metadata[key] for key in (
        "conditioning_identity", "model", "model_config_sha256", "upstream")})
    if (digest != metadata["conditioning_identity"] or
            hashlib.sha256(json.dumps(generation, sort_keys=True).encode()).hexdigest() != metadata["identity"]):
        raise ValueError("physical generation identity mismatch")
    origin = metadata["native_origin"]
    if (not isinstance(origin, list) or len(origin) != 2 or any(type(value) is not int for value in origin) or
            metadata["shape"] != list(arrays["elevation_m"].shape) or
            not isinstance(metadata["seed"], str) or not metadata["seed"].isdigit() or
            not 0 <= int(metadata["seed"]) < 2**64 or metadata["elevation_units"] != "m"):
        raise ValueError("physical window/seed mismatch")
    return make_source(arrays["elevation_m"], climate=arrays["climate"],
        origin_m_xz=[value * config.native_resolution_m for value in origin], spacing_m=config.native_resolution_m,
        provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
            "archive_sha256": expected_sha256, "generation_metadata": metadata,
            "historical_game_height_conditioning": False}, boundary=boundary, display_mask=display_mask)


def save_source(path, result):
    save_bundle(path, result, validator=validate_source)


def _source_headers(headers):
    if set(headers) not in ({"height_m", "display_mask", "hydrology_mask", "manifest"},
                            {"height_m", "display_mask", "hydrology_mask", "manifest", "climate"}):
        raise ValueError("unexpected source headers")
    shape, dtype = headers["height_m"]
    if len(shape) != 2 or not 1 <= math.prod(shape) <= MAX_CELLS or dtype != np.float64:
        raise ValueError("source grid allocation budget/type exceeded")
    for key in ("display_mask", "hydrology_mask"):
        if headers[key] != (shape, np.dtype(bool)):
            raise ValueError("source mask header mismatch")
    if "climate" in headers and headers["climate"] != ((5,) + shape, np.dtype("float64")):
        raise ValueError("source climate header mismatch")
    manifest_shape, manifest_dtype = headers["manifest"]
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= MAX_METADATA or manifest_dtype != np.uint8:
        raise ValueError("source manifest header mismatch")


def _legacy_headers(headers):
    shape, dtype = headers.get("input_height", ((), np.dtype("O")))
    if len(shape) != 2 or not 1 <= math.prod(shape) <= MAX_CELLS or dtype.kind not in "fiu":
        raise ValueError("legacy input shape/type exceeds adapter budget")
    for key in ("receiver", "outlet_mask", "flowline_mask"):
        if key not in headers or headers[key][0] != shape:
            raise ValueError("legacy grid header mismatch")
    if headers["receiver"][1].kind not in "iu" or any(headers[key][1] != bool for key in ("outlet_mask", "flowline_mask")):
        raise ValueError("legacy topology header type mismatch")


def _physical_headers(headers):
    if set(headers) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("actual TD archive required")
    shape, dtype = headers["elevation_m"]
    if len(shape) != 2 or not 1 <= math.prod(shape) <= MAX_CELLS or dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("physical elevation exceeds adapter shape/type budget")
    if headers["climate"][0] != (5,) + shape or headers["climate"][1] not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("physical climate header mismatch")
    if headers["metadata_json"][0] != () or headers["metadata_json"][1].kind != "U" or headers["metadata_json"][1].itemsize > MAX_METADATA:
        raise ValueError("physical metadata header mismatch")


def load_source_bundle(path, *, expected_sha256, expected_identity, trusted_source=None):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_source,
                         header_validator=_source_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external source identity mismatch")
    if trusted_source is not None:
        validate_source(trusted_source)
        if result["metadata"] != trusted_source["metadata"] or set(result["arrays"]) != set(trusted_source["arrays"]):
            raise ValueError("trusted original payload metadata mismatch")
        for key in result["arrays"]:
            if _hash(result["arrays"][key]) != _hash(trusted_source["arrays"][key]):
                raise ValueError("trusted original source payload mismatch")
    return result
