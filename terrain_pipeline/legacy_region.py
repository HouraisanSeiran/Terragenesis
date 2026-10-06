"""Explicit import and read-only consumption of legacy region results."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np

from .artifacts import ArtifactIdentity, TerrainArtifact, load_artifact, save_artifact
from .artifacts.contracts import canonical_json


_PAIR_VERSION = 1
_HALO = 25
_EXPECTED_SHAPE = (513, 513)
_CORE_SHAPE = (463, 463)
_SPACING_BLOCKS = 2
_METERS_PER_HEIGHT_BLOCK = 6.0
_WORLD_SEA_LEVEL = 62.0
_NATIVE_RESOLUTION_M = 30.0
_PAIR_FILES = {"manifest.json", "base", "derived"}
_RECIPE = "regional_landforms_v1_s8r24_s2r6_low220_290_relief9_28_slope03_09_prom8_26"


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _load_json(value: str) -> Any:
    return json.loads(value, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)


def _scalar(archive: Any, name: str) -> Any:
    value = archive[name]
    if value.ndim != 0:
        raise ValueError(f"{name} must be a scalar archive member")
    return value.item()


def _json_scalar(archive: Any, name: str) -> dict[str, Any]:
    value = _scalar(archive, name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must contain JSON text")
    try:
        parsed = _load_json(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {name} JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must contain an object")
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_source(path: Path) -> tuple[np.ndarray, dict[str, Any], dict[str, Any], dict[str, Any], str]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    source_sha = _sha256(path)
    with np.load(path, allow_pickle=False) as archive:
        expected = {"elevation", "climate", "metadata", "generation_config", "world_mapping"}
        if len(archive.files) != len(expected) or set(archive.files) != expected:
            raise ValueError("legacy source archive fields do not match the supported fixture")
        elevation = archive["elevation"]
        climate = archive["climate"]
        if elevation.dtype != np.dtype("float32") or elevation.shape != _EXPECTED_SHAPE:
            raise ValueError("legacy elevation must be a 513x513 float32 grid")
        if climate.ndim != 3 or climate.shape[1:] != _EXPECTED_SHAPE:
            raise ValueError("legacy climate shape does not match elevation")
        if not np.isfinite(elevation).all() or not np.isfinite(climate).all():
            raise ValueError("legacy source contains non-finite values")
        metadata = _json_scalar(archive, "metadata")
        config = _json_scalar(archive, "generation_config")
        mapping = _json_scalar(archive, "world_mapping")
    if metadata.get("backend") != "TerrainDiffusion/WorldPipeline":
        raise ValueError("unsupported source backend")
    if not isinstance(metadata.get("identity"), str) or not metadata["identity"]:
        raise ValueError("source model identity is required")
    seed_value = metadata.get("seed")
    if type(seed_value) is int:
        seed = seed_value
    elif isinstance(seed_value, str) and seed_value.isdecimal():
        seed = int(seed_value)
    else:
        raise ValueError("source seed must be an integer")
    native_origin = metadata.get("native_origin")
    if (not isinstance(native_origin, list) or len(native_origin) != 2 or
            any(type(value) is not int for value in native_origin)):
        raise ValueError("native origin must contain two integers")
    native_origin = tuple(native_origin)
    if metadata.get("native_resolution_m") != _NATIVE_RESOLUTION_M:
        raise ValueError("unsupported native resolution")
    if config.get("blocks_per_pixel") != _SPACING_BLOCKS or config.get("meters_per_height_block") != _METERS_PER_HEIGHT_BLOCK:
        raise ValueError("unsupported legacy height mapping")
    if mapping.get("world_sea_level") != _WORLD_SEA_LEVEL:
        raise ValueError("unsupported world sea level")
    if mapping.get("world_y_formula") != "62 + elevation_m / meters_per_height_block":
        raise ValueError("unsupported world height formula")
    if _sha256(path) != source_sha:
        raise ValueError("source changed during read")
    return elevation, metadata, config, mapping, source_sha


def _validate_processed(path: Path, expected_raw: np.ndarray, expected_origin: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, str, str]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    processed_sha = _sha256(path)
    with np.load(path, allow_pickle=False) as archive:
        expected = {"raw_height", "processed_height", "weights", "dominant_type", "origin_world", "spacing_blocks", "algorithm_id"}
        if len(archive.files) != len(expected) or set(archive.files) != expected:
            raise ValueError("legacy processed archive fields do not match the supported fixture")
        raw = archive["raw_height"]
        processed = archive["processed_height"]
        if raw.dtype != np.dtype("float32") or processed.dtype != np.dtype("float32") or raw.shape != _CORE_SHAPE or processed.shape != _CORE_SHAPE:
            raise ValueError("processed heights must be 463x463 float32 grids")
        if not np.isfinite(raw).all() or not np.isfinite(processed).all():
            raise ValueError("processed heights contain non-finite values")
        if not np.array_equal(raw, expected_raw):
            raise ValueError("processed input does not match source mapping after halo crop")
        weights = archive["weights"]
        if weights.shape != (*_CORE_SHAPE, 4) or weights.dtype.kind != "f" or not np.isfinite(weights).all():
            raise ValueError("processed weights are invalid")
        labels = archive["dominant_type"]
        if labels.shape != _CORE_SHAPE or labels.dtype != np.dtype("uint8"):
            raise ValueError("processed landform labels are invalid")
        origin = archive["origin_world"]
        if origin.shape != (2,) or origin.dtype.kind not in "iu" or tuple(int(value) for value in origin) != expected_origin:
            raise ValueError("processed origin does not match source and halo")
        spacing = _scalar(archive, "spacing_blocks")
        if type(spacing) is not int or spacing != _SPACING_BLOCKS:
            raise ValueError("processed spacing does not match source mapping")
        algorithm_id = _scalar(archive, "algorithm_id")
        if algorithm_id != _RECIPE:
            raise ValueError("unsupported regional processing recipe")
    if _sha256(path) != processed_sha:
        raise ValueError("processed source changed during read")
    return raw, processed, algorithm_id, processed_sha


@dataclass(frozen=True)
class LegacyRegion:
    """Validated pair of artifacts for programmatic, read-only consumption."""

    base: TerrainArtifact
    derived: TerrainArtifact

    def __post_init__(self) -> None:
        if self.base.kind != "base" or self.derived.kind != "derived":
            raise ValueError("legacy region requires base and derived artifacts")
        self.derived.verify_source(self.base)
        if (self.derived.reference_surface_id != self.base.reference_surface_id or
                self.derived.grid_record() != self.base.grid_record()):
            raise ValueError("derived reference differs from the source surface")
        if self.derived.displacement_type != "vertical" or self.derived.displacement_m is None:
            raise ValueError("legacy region requires vertical displacement")

    @property
    def shape(self) -> tuple[int, int]:
        return self.base.reference_elevation_m.shape

    def reconstructed_elevation_m(self) -> np.ndarray:
        """Return a copy so consumers cannot mutate the artifact payload."""
        return (self.base.reference_elevation_m + self.derived.displacement_m[1]).copy()


def prepare_legacy_region(source_path: str | Path, processed_path: str | Path,
                          destination: str | Path) -> LegacyRegion:
    """Convert one known legacy pair and atomically publish a read-only package."""
    source_path, processed_path, destination = Path(source_path), Path(processed_path), Path(destination)
    elevation, metadata, config, mapping, source_sha = _validate_source(source_path)
    core = np.s_[_HALO:-_HALO, _HALO:-_HALO]
    raw_expected = (float(mapping["world_sea_level"]) + elevation.astype(np.float32) /
                    float(config["meters_per_height_block"])).astype(np.float32)[core]
    native_origin = tuple(int(value) for value in metadata["native_origin"])
    origin_world = (native_origin[0] * _SPACING_BLOCKS + _HALO * _SPACING_BLOCKS,
                    native_origin[1] * _SPACING_BLOCKS + _HALO * _SPACING_BLOCKS)
    _, processed, algorithm_id, processed_sha = _validate_processed(processed_path, raw_expected, origin_world)
    reference = np.asarray(elevation[core], dtype=np.float64)
    identity = ArtifactIdentity(
        backend=str(metadata["backend"]), algorithm="terrain_diffusion_import", algorithm_version="legacy-v1",
        seed=int(metadata["seed"]), parameters={"model_identity": metadata["identity"],
                                                  "generation_config": config, "world_mapping": mapping,
                                                  "source_sha256": source_sha, "native_origin": list(native_origin)})
    base = TerrainArtifact(kind="base", identity=identity, reference_elevation_m=reference,
                           origin_x_m=(native_origin[0] + _HALO) * _NATIVE_RESOLUTION_M,
                           origin_z_m=(native_origin[1] + _HALO) * _NATIVE_RESOLUTION_M,
                           spacing_x_m=_NATIVE_RESOLUTION_M, spacing_z_m=_NATIVE_RESOLUTION_M,
                           vertical_datum="model-relative sea level", sea_level_elevation_m=0)
    displacement = np.zeros((3, *_CORE_SHAPE), dtype=np.float64)
    displacement[1] = ((processed.astype(np.float64) - _WORLD_SEA_LEVEL) *
                       _METERS_PER_HEIGHT_BLOCK - reference)
    derived = TerrainArtifact(kind="derived", identity=ArtifactIdentity(
        backend="legacy-region-processor", algorithm="regional_landforms_v1", algorithm_version="legacy-v1",
        seed=int(metadata["seed"]), parameters={"recipe": algorithm_id, "conversion": "world-height-to-metre-dy-v1",
                                                "processed_sha256": processed_sha}),
        reference_elevation_m=reference, origin_x_m=base.origin_x_m, origin_z_m=base.origin_z_m,
        spacing_x_m=base.spacing_x_m, spacing_z_m=base.spacing_z_m,
        vertical_datum=base.vertical_datum, sea_level_elevation_m=base.sea_level_elevation_m,
        displacement_type="vertical", displacement_m=displacement, source_artifact_id=base.content_id)
    if _sha256(source_path) != source_sha or _sha256(processed_path) != processed_sha:
        raise ValueError("legacy input changed during preparation")
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        save_artifact(base, temporary / "base")
        save_artifact(derived, temporary / "derived")
        manifest = {"format_version": _PAIR_VERSION, "source_sha256": source_sha,
                    "processed_sha256": processed_sha,
                    "base_content_id": base.content_id, "derived_content_id": derived.content_id}
        (temporary / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        loaded = load_legacy_region(temporary)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(temporary, destination)
        return loaded
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_legacy_region(path: str | Path) -> LegacyRegion:
    """Load a published pair without consulting legacy inputs or generating data."""
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    if {entry.name for entry in directory.iterdir()} != _PAIR_FILES:
        raise ValueError("legacy region package has unexpected files")
    if (directory / "manifest.json").is_symlink():
        raise ValueError("legacy region manifest must be a regular file")
    try:
        manifest = _load_json((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid legacy region manifest") from exc
    if (not isinstance(manifest, dict) or
            set(manifest) != {"format_version", "source_sha256", "processed_sha256", "base_content_id", "derived_content_id"} or
            type(manifest["format_version"]) is not int or manifest["format_version"] != _PAIR_VERSION):
        raise ValueError("unsupported legacy region package")
    base = load_artifact(directory / "base")
    derived = load_artifact(directory / "derived")
    if manifest.get("base_content_id") != base.content_id or manifest.get("derived_content_id") != derived.content_id:
        raise ValueError("legacy region package identity mismatch")
    pair = LegacyRegion(base, derived)
    if (manifest["source_sha256"] != base.identity.record()["parameters"].get("source_sha256") or
            manifest["processed_sha256"] != derived.identity.record()["parameters"].get("processed_sha256")):
        raise ValueError("legacy region provenance mismatch")
    return pair


__all__ = ["LegacyRegion", "load_legacy_region", "prepare_legacy_region"]
