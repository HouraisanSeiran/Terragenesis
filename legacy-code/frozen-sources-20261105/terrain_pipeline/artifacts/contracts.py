"""Validated physical coordinates and immutable artifact payloads."""

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any
from types import MappingProxyType

import numpy as np


FORMAT_VERSION = 1


def canonical_json(value: Any) -> str:
    def check(item: Any) -> None:
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("JSON keys must be strings")
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
        elif item is None or isinstance(item, (str, bool, int)):
            pass
        else:
            raise ValueError("parameters must contain JSON values")

    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def immutable_array(value: Any, name: str, ndim: int, boolean: bool = False) -> np.ndarray:
    source = np.asarray(value)
    if boolean:
        if source.dtype != np.dtype(bool):
            raise ValueError(f"{name} must be boolean")
        normalized = np.ascontiguousarray(source, dtype=np.bool_)
    else:
        if source.dtype.kind not in "fiu":
            raise ValueError(f"{name} must be numeric")
        normalized = np.ascontiguousarray(source, dtype="<f8")
        if not np.isfinite(normalized).all():
            raise ValueError(f"{name} must be finite")
    if normalized.ndim != ndim or any(size == 0 for size in normalized.shape):
        raise ValueError(f"{name} has invalid dimensions")
    return np.frombuffer(normalized.tobytes(), dtype=normalized.dtype).reshape(normalized.shape)


def array_hash(value: np.ndarray) -> str:
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def finite_number(value: Any, name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(child) for child in value)
    return value


@dataclass(frozen=True)
class ArtifactIdentity:
    backend: str
    algorithm: str
    algorithm_version: str
    seed: int
    parameters: dict[str, Any]
    sha256: str = field(init=False)
    _parameters_json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in
               (self.backend, self.algorithm, self.algorithm_version)):
            raise ValueError("backend, algorithm and version are required")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be an object")
        encoded = canonical_json(self.parameters)
        object.__setattr__(self, "_parameters_json", encoded)
        object.__setattr__(self, "parameters", _freeze_json(json.loads(encoded)))
        object.__setattr__(self, "sha256", digest(self.record()))

    def record(self) -> dict[str, Any]:
        return {"backend": self.backend, "algorithm": self.algorithm,
                "algorithm_version": self.algorithm_version, "seed": self.seed,
                "parameters": json.loads(self._parameters_json)}


@dataclass(frozen=True)
class SurfaceWater:
    surface_elevation_m: np.ndarray
    wet_mask: np.ndarray
    discharge_m3_per_s: np.ndarray

    def __post_init__(self) -> None:
        for name in ("surface_elevation_m", "wet_mask", "discharge_m3_per_s"):
            object.__setattr__(self, name, immutable_array(getattr(self, name), name, 2, name == "wet_mask"))
        if len({self.surface_elevation_m.shape, self.wet_mask.shape, self.discharge_m3_per_s.shape}) != 1:
            raise ValueError("water arrays must share shape")
        if np.any(self.discharge_m3_per_s < 0):
            raise ValueError("discharge must be nonnegative")


@dataclass(frozen=True)
class TerrainArtifact:
    kind: str
    identity: ArtifactIdentity
    reference_elevation_m: np.ndarray
    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    vertical_datum: str
    sea_level_elevation_m: float
    displacement_type: str = "none"
    displacement_m: np.ndarray | None = None
    reference_surface_id: str | None = None
    source_artifact_id: str | None = None
    water: SurfaceWater | None = None
    content_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.kind not in ("base", "derived") or self.displacement_type not in ("none", "vertical", "xyz"):
            raise ValueError("unknown artifact kind or displacement type")
        if not isinstance(self.identity, ArtifactIdentity):
            raise ValueError("identity is required")
        if not isinstance(self.vertical_datum, str) or not self.vertical_datum.strip():
            raise ValueError("named vertical datum is required")
        for name in ("origin_x_m", "origin_z_m", "sea_level_elevation_m"):
            object.__setattr__(self, name, finite_number(getattr(self, name), name))
        for name in ("spacing_x_m", "spacing_z_m"):
            object.__setattr__(self, name, finite_number(getattr(self, name), name, positive=True))
        reference = immutable_array(self.reference_elevation_m, "reference_elevation_m", 2)
        object.__setattr__(self, "reference_elevation_m", reference)
        surface_id = digest({"grid": self.grid_record(), "reference_sha256": array_hash(reference)})
        if self.reference_surface_id is not None and self.reference_surface_id != surface_id:
            raise ValueError("reference surface identity mismatch")
        object.__setattr__(self, "reference_surface_id", surface_id)
        if self.displacement_type == "none":
            if self.displacement_m is not None:
                raise ValueError("none displacement cannot carry vectors")
        else:
            if self.displacement_m is None:
                raise ValueError("displacement vectors are required")
            vectors = immutable_array(self.displacement_m, "displacement_m", 3)
            if vectors.shape != (3, *reference.shape):
                raise ValueError("displacement shape must be [3,z,x]")
            if self.displacement_type == "vertical" and (np.any(vectors[0] != 0) or np.any(vectors[2] != 0)):
                raise ValueError("vertical displacement requires zero dx and dz")
            object.__setattr__(self, "displacement_m", vectors)
        if self.kind == "base":
            if self.source_artifact_id is not None or (self.displacement_m is not None and np.any(self.displacement_m != 0)):
                raise ValueError("base artifact has no source or nonzero displacement")
        elif not isinstance(self.source_artifact_id, str) or len(self.source_artifact_id) != 64 or any(c not in "0123456789abcdef" for c in self.source_artifact_id):
            raise ValueError("derived artifact requires source content identity")
        if self.water is not None:
            if not isinstance(self.water, SurfaceWater) or self.water.wet_mask.shape != reference.shape:
                raise ValueError("water shape mismatch")
            bed = reference + (0 if self.displacement_m is None else self.displacement_m[1])
            if np.any(self.water.surface_elevation_m[self.water.wet_mask] < bed[self.water.wet_mask]):
                raise ValueError("wet water surface below reconstructed bed")
            if np.any(self.water.discharge_m3_per_s[~self.water.wet_mask] != 0):
                raise ValueError("dry cells cannot carry discharge")
        with np.errstate(over="ignore", invalid="ignore"):
            if not np.isfinite(self.reconstruct_positions_m()).all():
                raise ValueError("reconstructed positions must be finite")
        object.__setattr__(self, "content_id", digest(self.content_record()))

    def grid_record(self) -> dict[str, Any]:
        return {"origin_x_m": self.origin_x_m, "origin_z_m": self.origin_z_m,
                "spacing_x_m": self.spacing_x_m, "spacing_z_m": self.spacing_z_m,
                "vertical_datum": self.vertical_datum, "sea_level_elevation_m": self.sea_level_elevation_m,
                "shape_zx": list(self.reference_elevation_m.shape)}

    def content_record(self) -> dict[str, Any]:
        arrays = {"reference_elevation_m": array_hash(self.reference_elevation_m)}
        if self.displacement_m is not None:
            arrays["displacement_m"] = array_hash(self.displacement_m)
        if self.water is not None:
            arrays.update({name: array_hash(getattr(self.water, name)) for name in
                           ("surface_elevation_m", "wet_mask", "discharge_m3_per_s")})
        return {"format_version": FORMAT_VERSION, "kind": self.kind, "grid": self.grid_record(),
                "identity": {**self.identity.record(), "sha256": self.identity.sha256},
                "reference_surface_id": self.reference_surface_id, "source_artifact_id": self.source_artifact_id,
                "displacement_type": self.displacement_type, "arrays": arrays}

    def reconstruct_positions_m(self) -> np.ndarray:
        z_count, x_count = self.reference_elevation_m.shape
        x = self.origin_x_m + np.arange(x_count) * self.spacing_x_m
        z = self.origin_z_m + np.arange(z_count) * self.spacing_z_m
        positions = np.stack(np.broadcast_arrays(x[None, :], self.reference_elevation_m, z[:, None]), axis=0).copy()
        if self.displacement_m is not None:
            positions += self.displacement_m
        return positions

    def verify_source(self, source: "TerrainArtifact") -> None:
        if self.kind != "derived" or not isinstance(source, TerrainArtifact):
            raise ValueError("derived artifact and source are required")
        if self.source_artifact_id != source.content_id:
            raise ValueError("source content identity mismatch")
