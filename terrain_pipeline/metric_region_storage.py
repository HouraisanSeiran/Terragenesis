"""Explicit publication and read-only loading for metric region results."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from .artifacts import ArtifactIdentity, TerrainArtifact, load_artifact, save_artifact
from .artifacts.contracts import canonical_json
from .metric_region import METRIC_30M_RECIPE_V1, RegionRecipe, process_region


@dataclass(frozen=True)
class MetricRegion:
    base: TerrainArtifact
    derived: TerrainArtifact
    weights: np.ndarray
    dominant_type: np.ndarray

    def __post_init__(self) -> None:
        self.derived.verify_source(self.base)
        if self.base.kind != "base" or self.derived.kind != "derived" or self.base.grid_record() != self.derived.grid_record():
            raise ValueError("region base and derived grids differ")
        if self.derived.reference_surface_id != self.base.reference_surface_id or self.derived.displacement_type != "vertical":
            raise ValueError("derived surface must use vertical displacement on base")
        shape = self.base.reference_elevation_m.shape
        weights = np.asarray(self.weights, dtype="<f8")
        labels = np.asarray(self.dominant_type)
        if weights.shape != (*shape, 4) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.allclose(weights.sum(axis=-1), 1, atol=1e-12, rtol=0):
            raise ValueError("invalid landform weights")
        if labels.shape != shape or labels.dtype != np.uint8 or np.any(labels > 3) or not np.array_equal(labels, np.argmax(weights, axis=-1)):
            raise ValueError("invalid dominant types")
        object.__setattr__(self, "weights", np.frombuffer(weights.tobytes(), dtype="<f8").reshape(weights.shape))
        object.__setattr__(self, "dominant_type", np.frombuffer(labels.tobytes(), dtype=np.uint8).reshape(shape))

    def reconstructed_elevation_m(self) -> np.ndarray:
        return self.base.reference_elevation_m + self.derived.displacement_m[1]


def prepare_metric_region(base: TerrainArtifact, destination: str | Path,
                          protection_mask: np.ndarray | None = None,
                          recipe: RegionRecipe | None = None,
                          halo_samples: tuple[int, int] | None = None) -> MetricRegion:
    """Compute once, validate, then publish a base/derived/labels package atomically."""
    if base.kind != "base" or base.displacement_type != "none" or base.water is not None:
        raise ValueError("processor requires a dry base reference surface")
    if recipe is None:
        recipe = (METRIC_30M_RECIPE_V1 if base.spacing_x_m == 30 and base.spacing_z_m == 30
                  else RegionRecipe())
    if not isinstance(recipe, RegionRecipe):
        raise TypeError("recipe must be RegionRecipe")
    required_x, required_z = recipe.required_halo_samples(base.spacing_x_m, base.spacing_z_m)
    halo_x, halo_z = halo_samples if halo_samples is not None else (required_x, required_z)
    if (type(halo_x) is not int or type(halo_z) is not int or
            halo_x < required_x or halo_z < required_z or
            base.reference_elevation_m.shape[1] <= 2 * halo_x or
            base.reference_elevation_m.shape[0] <= 2 * halo_z):
        raise ValueError("insufficient processing halo")
    mask_snapshot = None if protection_mask is None else np.array(protection_mask, dtype="<f8", copy=True)
    result = process_region(base.reference_elevation_m, base.sea_level_elevation_m,
                            base.spacing_x_m, base.spacing_z_m, mask_snapshot, recipe)
    interior = np.s_[halo_z:base.reference_elevation_m.shape[0] - halo_z,
                     halo_x:base.reference_elevation_m.shape[1] - halo_x]
    reference = base.reference_elevation_m[interior]
    core_base = TerrainArtifact(kind="base", identity=ArtifactIdentity(
        backend=base.identity.backend, algorithm="metric_region_core_crop", algorithm_version="1",
        seed=base.identity.seed, parameters={"source_content_id": base.content_id,
                                              "source_identity": base.identity.record(),
                                              "source_grid": base.grid_record(),
                                              "halo_x_samples": halo_x, "halo_z_samples": halo_z}),
        reference_elevation_m=reference, origin_x_m=base.origin_x_m + halo_x * base.spacing_x_m,
        origin_z_m=base.origin_z_m + halo_z * base.spacing_z_m,
        spacing_x_m=base.spacing_x_m, spacing_z_m=base.spacing_z_m,
        vertical_datum=base.vertical_datum, sea_level_elevation_m=base.sea_level_elevation_m)
    displacement = np.zeros((3, *reference.shape), dtype=np.float64)
    displacement[1] = result.elevation_m[interior] - reference
    mask_hash = None if mask_snapshot is None else hashlib.sha256(mask_snapshot.tobytes()).hexdigest()
    weights = np.ascontiguousarray(result.weights[interior], dtype="<f8")
    labels = np.ascontiguousarray(result.dominant_type[interior], dtype=np.uint8)
    weights_hash = hashlib.sha256(weights.tobytes()).hexdigest()
    labels_hash = hashlib.sha256(labels.tobytes()).hexdigest()
    core_derived = TerrainArtifact(kind="derived", identity=ArtifactIdentity(
        backend="metric-region-processor", algorithm="regional_landforms_metre",
        algorithm_version="1", seed=base.identity.seed,
        parameters={"recipe": recipe.record(), "input_content_id": base.content_id,
                    "protection_mask_sha256": mask_hash,
                    "weights_sha256": weights_hash, "dominant_type_sha256": labels_hash,
                    "halo_x_samples": halo_x, "halo_z_samples": halo_z}),
        reference_elevation_m=reference, origin_x_m=core_base.origin_x_m,
        origin_z_m=core_base.origin_z_m, spacing_x_m=base.spacing_x_m,
        spacing_z_m=base.spacing_z_m, vertical_datum=base.vertical_datum,
        sea_level_elevation_m=base.sea_level_elevation_m,
        displacement_type="vertical", displacement_m=displacement,
        source_artifact_id=core_base.content_id)
    package = MetricRegion(core_base, core_derived, weights, labels)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        save_artifact(package.base, temporary / "base")
        save_artifact(package.derived, temporary / "derived")
        np.savez(temporary / "landforms.npz", weights=package.weights, dominant_type=package.dominant_type)
        metadata = {"version": 1, "base_content_id": package.base.content_id,
                    "derived_content_id": package.derived.content_id,
                    "landforms_sha256": _sha256(temporary / "landforms.npz")}
        (temporary / "manifest.json").write_text(canonical_json(metadata), encoding="utf-8")
        loaded = load_metric_region(temporary)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(temporary, destination)
        return loaded
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_metric_region(path: str | Path) -> MetricRegion:
    """Read and validate a published package without invoking processing."""
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    if {entry.name for entry in directory.iterdir()} != {"manifest.json", "base", "derived", "landforms.npz"}:
        raise ValueError("invalid metric region package entries")
    for name in ("manifest.json", "landforms.npz"):
        if not (directory / name).is_file() or (directory / name).is_symlink():
            raise ValueError("metric region files must be regular files")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate manifest field")
            result[key] = value
        return result
    metadata = json.loads((directory / "manifest.json").read_text(encoding="utf-8"),
                          object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if (not isinstance(metadata, dict) or set(metadata) != {"version", "base_content_id", "derived_content_id", "landforms_sha256"}
            or type(metadata["version"]) is not int or metadata["version"] != 1):
        raise ValueError("invalid metric region manifest")
    if _sha256(directory / "landforms.npz") != metadata["landforms_sha256"]:
        raise ValueError("landform payload hash mismatch")
    with np.load(directory / "landforms.npz", allow_pickle=False) as archive:
        if len(archive.files) != 2 or set(archive.files) != {"weights", "dominant_type"}:
            raise ValueError("invalid landform payload fields")
        weights, labels = archive["weights"], archive["dominant_type"]
        if weights.dtype != np.dtype("<f8") or labels.dtype != np.dtype("uint8"):
            raise ValueError("invalid landform payload dtypes")
    package = MetricRegion(load_artifact(directory / "base"), load_artifact(directory / "derived"), weights, labels)
    parameters = package.derived.identity.record()["parameters"]
    if (parameters.get("weights_sha256") != hashlib.sha256(package.weights.tobytes()).hexdigest() or
            parameters.get("dominant_type_sha256") != hashlib.sha256(package.dominant_type.tobytes()).hexdigest()):
        raise ValueError("landform payload differs from derived identity")
    if package.base.content_id != metadata["base_content_id"] or package.derived.content_id != metadata["derived_content_id"]:
        raise ValueError("metric region identity mismatch")
    return package
