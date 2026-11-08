"""Explicit, validated artifact storage; loading never generates terrain."""

import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from .contracts import ArtifactIdentity, FORMAT_VERSION, SurfaceWater, TerrainArtifact, canonical_json


_ARRAY_FILE = "arrays.npz"
_MANIFEST_FILE = "manifest.json"
_TOP_KEYS = {"format_version", "kind", "grid", "identity", "reference_surface_id",
             "source_artifact_id", "displacement_type", "arrays", "content_id"}
_GRID_KEYS = {"origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m",
              "vertical_datum", "sea_level_elevation_m", "shape_zx"}
_IDENTITY_KEYS = {"backend", "algorithm", "algorithm_version", "seed", "parameters", "sha256"}
_ARRAY_KEYS = {"reference_elevation_m", "displacement_m", "surface_elevation_m", "wet_mask", "discharge_m3_per_s"}


def _pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _exact_keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {name} fields")


def save_artifact(artifact: TerrainArtifact, path: str | Path) -> Path:
    if not isinstance(artifact, TerrainArtifact):
        raise TypeError("artifact must be a TerrainArtifact")
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        arrays = {"reference_elevation_m": artifact.reference_elevation_m}
        if artifact.displacement_m is not None:
            arrays["displacement_m"] = artifact.displacement_m
        if artifact.water is not None:
            for name in ("surface_elevation_m", "wet_mask", "discharge_m3_per_s"):
                arrays[name] = getattr(artifact.water, name)
        np.savez(temporary / _ARRAY_FILE, **arrays)
        manifest = {**artifact.content_record(), "content_id": artifact.content_id}
        (temporary / _MANIFEST_FILE).write_text(canonical_json(manifest), encoding="utf-8")
        # Verify the complete temporary package before publishing it.
        load_artifact(temporary)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_artifact(path: str | Path) -> TerrainArtifact:
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    if {entry.name for entry in directory.iterdir()} != {_MANIFEST_FILE, _ARRAY_FILE}:
        raise ValueError("artifact directory must contain only manifest.json and arrays.npz")
    for name in (_MANIFEST_FILE, _ARRAY_FILE):
        if not (directory / name).is_file() or (directory / name).is_symlink():
            raise ValueError("artifact files must be regular files")
    manifest = json.loads((directory / _MANIFEST_FILE).read_text(encoding="utf-8"),
                          object_pairs_hook=_pairs_without_duplicates, parse_constant=_reject_constant)
    _exact_keys(manifest, _TOP_KEYS, "manifest")
    if type(manifest["format_version"]) is not int or manifest["format_version"] != FORMAT_VERSION:
        raise ValueError("unsupported artifact format")
    grid = manifest["grid"]
    _exact_keys(grid, _GRID_KEYS, "grid")
    shape = grid["shape_zx"]
    if not isinstance(shape, list) or len(shape) != 2 or any(type(size) is not int or size <= 0 for size in shape):
        raise ValueError("invalid grid shape")
    identity_data = manifest["identity"]
    _exact_keys(identity_data, _IDENTITY_KEYS, "identity")
    identity = ArtifactIdentity(**{key: identity_data[key] for key in _IDENTITY_KEYS - {"sha256"}})
    if identity.sha256 != identity_data["sha256"]:
        raise ValueError("algorithm identity mismatch")
    array_hashes = manifest["arrays"]
    if not isinstance(array_hashes, dict) or not set(array_hashes).issubset(_ARRAY_KEYS) or "reference_elevation_m" not in array_hashes:
        raise ValueError("invalid array fields")
    if manifest["displacement_type"] == "none":
        expected = {"reference_elevation_m"}
    else:
        expected = {"reference_elevation_m", "displacement_m"}
    water_names = {"surface_elevation_m", "wet_mask", "discharge_m3_per_s"}
    if set(array_hashes) & water_names:
        expected |= water_names
    if set(array_hashes) != expected or any(not isinstance(value, str) or len(value) != 64 for value in array_hashes.values()):
        raise ValueError("incomplete array declarations")
    with np.load(directory / _ARRAY_FILE, allow_pickle=False) as archive:
        if len(archive.files) != len(expected) or set(archive.files) != expected:
            raise ValueError("array payload differs from manifest")
        arrays = {name: archive[name] for name in expected}
        for name, value in arrays.items():
            expected_dtype = np.dtype(bool) if name == "wet_mask" else np.dtype("<f8")
            if value.dtype != expected_dtype:
                raise ValueError(f"invalid array dtype: {name}")
    water = (SurfaceWater(**{name: arrays[name] for name in water_names}) if water_names <= expected else None)
    artifact = TerrainArtifact(kind=manifest["kind"], identity=identity,
                               reference_elevation_m=arrays["reference_elevation_m"],
                               origin_x_m=grid["origin_x_m"], origin_z_m=grid["origin_z_m"],
                               spacing_x_m=grid["spacing_x_m"], spacing_z_m=grid["spacing_z_m"],
                               vertical_datum=grid["vertical_datum"],
                               sea_level_elevation_m=grid["sea_level_elevation_m"],
                               displacement_type=manifest["displacement_type"],
                               displacement_m=arrays.get("displacement_m"),
                               reference_surface_id=manifest["reference_surface_id"],
                               source_artifact_id=manifest["source_artifact_id"], water=water)
    if artifact.content_id != manifest["content_id"] or artifact.content_record() != {key: manifest[key] for key in _TOP_KEYS - {"content_id"}}:
        raise ValueError("artifact content mismatch")
    return artifact
