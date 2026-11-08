"""Cold verification of the four-tile 1024-square TD source package."""

import json
from pathlib import Path

import numpy as np

from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.common_infra import checked_archive, file_sha256, identity, readonly


SOURCE_SIZE = 1024
TILE_SIZE = 513
TILE_CORE = 512
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_METADATA_CHARS = 100_000


def _headers(headers, side):
    if set(headers) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("unexpected TD archive fields")
    elevation, climate, metadata = (headers[name] for name in
                                    ("elevation_m", "climate", "metadata_json"))
    if (elevation[0] != (side, side) or elevation[1] not in (np.dtype("float32"), np.dtype("float64"))
            or climate[0] != (5, side, side) or climate[1] not in (np.dtype("float32"), np.dtype("float64"))
            or metadata[0] != () or metadata[1].kind != "U"
            or metadata[1].itemsize > 4 * MAX_METADATA_CHARS):
        raise ValueError("invalid TD archive shape, dtype, or metadata budget")


def _archive(path, sha, side):
    arrays = checked_archive(path, expected_sha256=sha, max_bytes=MAX_ARCHIVE_BYTES,
                             header_validator=lambda headers: _headers(headers, side))
    if not np.isfinite(arrays["elevation_m"]).all() or not np.isfinite(arrays["climate"]).all():
        raise ValueError("nonfinite TD source arrays")
    raw = str(arrays.pop("metadata_json").item())
    if len(raw) > MAX_METADATA_CHARS:
        raise ValueError("TD source metadata budget exceeded")
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        raise ValueError("TD source metadata object required")
    return arrays, metadata


def stitch_tiles(tiles, *, seam_tolerance_m=.25):
    """Reconstruct northwest-owned cores and independently audit shared halos."""
    if set(tiles) != {(0, 0), (0, 1), (1, 0), (1, 1)}:
        raise ValueError("four indexed TD windows required")
    if not np.isfinite(seam_tolerance_m) or seam_tolerance_m < 0.:
        raise ValueError("nonnegative finite seam tolerance required")
    side = np.asarray(tiles[0, 0][0]).shape[0]
    if side < 2:
        raise ValueError("tile halo required")
    core = side - 1
    for elevation, climate in tiles.values():
        if (elevation.shape != (side, side) or climate.shape != (5, side, side)
                or elevation.dtype not in (np.float32, np.float64)
                or climate.dtype not in (np.float32, np.float64)
                or not np.isfinite(elevation).all() or not np.isfinite(climate).all()):
            raise ValueError("invalid TD tile arrays")
    height = np.empty((2 * core, 2 * core), dtype=tiles[0, 0][0].dtype)
    conditions = np.empty((5, 2 * core, 2 * core), dtype=tiles[0, 0][1].dtype)
    for (row, col), (elevation, climate) in tiles.items():
        z, x = slice(row * core, (row + 1) * core), slice(col * core, (col + 1) * core)
        height[z, x] = elevation[:core, :core]
        conditions[:, z, x] = climate[:, :core, :core]
    strips = {"elevation_m": [], "climate": []}
    for row in range(2):
        left, right = tiles[row, 0], tiles[row, 1]
        strips["elevation_m"].append(np.abs(left[0][:core, core].astype(np.float64) - right[0][:core, 0]))
        strips["climate"].append(np.abs(left[1][:, :core, core].astype(np.float64) - right[1][:, :core, 0]))
    for col in range(2):
        north, south = tiles[0, col], tiles[1, col]
        strips["elevation_m"].append(np.abs(north[0][core, :core].astype(np.float64) - south[0][0, :core]))
        strips["climate"].append(np.abs(north[1][:, core, :core].astype(np.float64) - south[1][:, 0, :core]))
    stats = {}
    for name, values in strips.items():
        stats[name] = {"max_abs": max(float(value.max()) for value in values),
                       "mean_abs": float(sum(float(value.sum()) for value in values)
                                         / sum(value.size for value in values)),
                       "individual_max_abs": [float(value.max()) for value in values],
                       "strip_order": ["north_vertical", "south_vertical", "west_horizontal", "east_horizontal"]}
    accepted = stats["elevation_m"]["max_abs"] <= seam_tolerance_m
    audit = {"ownership": "northwest_512_core_per_513_tile",
             "comparison": "shared_halo_values_only_no_blend_or_resample",
             "diagnostic_seam_max_m": float(seam_tolerance_m),
             "elevation_m": stats["elevation_m"], "climate": stats["climate"],
             "accepted": accepted,
             "status": "diagnostic_seam_within_limit" if accepted else "seam_unverified",
             "hydrologic_seam_certified": False}
    return height, conditions, audit


def load_large_td_source(path, *, expected_sha256):
    """Require an external source hash and replay each pinned tile without inference."""
    path = Path(path).resolve()
    arrays, metadata = _archive(path, expected_sha256, SOURCE_SIZE)
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("source") != path.name or manifest.get("source_sha256") != expected_sha256
            or manifest.get("metadata") != metadata or manifest.get("status") != "generated_unverified"):
        raise ValueError("source manifest linkage mismatch")
    if (metadata.get("schema") != "td-1024-source-v1"
            or metadata.get("source_kind") != "generated_terrain"
            or metadata.get("artifact_kind") != "terrain_diffusion_original_bed_stitched"
            or metadata.get("shape") != [SOURCE_SIZE, SOURCE_SIZE]
            or metadata.get("spacing_m") != 30.
            or metadata.get("seam_accepted") is not True
            or metadata.get("seam_status") != "diagnostic_seam_within_limit"
            or metadata.get("all_model_files_sha_verified") is not True
            or any(metadata.get(name) is not False for name in
                   ("hydraulic_ready", "natural_outlet_verified", "hydrologic_seam_certified", "publishable"))):
        raise ValueError("unsupported TD 1024 source claims or geometry")
    native_origin = metadata.get("origin_native_xz")
    metre_origin = metadata.get("origin_m_xz")
    seed = metadata.get("seed")
    if (not isinstance(native_origin, list) or len(native_origin) != 2
            or any(type(value) is not int for value in native_origin)
            or metre_origin != [float(value * 30) for value in native_origin]
            or type(seed) is not int or seed < 0):
        raise ValueError("TD origin or seed mismatch")
    config = PhysicalGenerationConfig.from_record(metadata["physical_config"])
    config_record = config.record()
    config_record["cond_snr"] = list(config_record["cond_snr"])
    if config.native_resolution_m != 30. or config_record != metadata["physical_config"]:
        raise ValueError("physical config mismatch")
    generation_id, generation = config.generation_identity()
    model_manifest = Path(config.model_dir) / "manifest.json"
    if (generation_id != metadata.get("generation_identity")
            or file_sha256(model_manifest) != metadata.get("model_manifest_sha256")
            or generation["model"]["revision"] != metadata.get("model_revision")):
        raise ValueError("TD model/generation identity mismatch")
    records = metadata.get("tiles")
    if not isinstance(records, list) or len(records) != 4:
        raise ValueError("four tile records required")
    tiles = {}
    for record in records:
        row, col = record.get("row"), record.get("column")
        if type(row) is not int or type(col) is not int or (row, col) not in {(0, 0), (0, 1), (1, 0), (1, 1)} or (row, col) in tiles:
            raise ValueError("invalid tile indexing")
        name = f"tile-z{row}-x{col}.npz"
        if (record.get("path") != name or record.get("shape") != [TILE_SIZE, TILE_SIZE]
                or record.get("native_origin_xz") != [native_origin[0] + col * TILE_CORE,
                                                       native_origin[1] + row * TILE_CORE]):
            raise ValueError("tile path/origin mismatch")
        tile_arrays, tile_meta = _archive(path.parent / name, record["sha256"], TILE_SIZE)
        if (tile_meta != record["generation_metadata"] or tile_meta.get("identity") != generation_id
                or tile_meta.get("seed") != str(seed)
                or tile_meta.get("native_origin") != record["native_origin_xz"]
                or tile_meta.get("shape") != [TILE_SIZE, TILE_SIZE]
                or tile_meta.get("native_resolution_m") != 30.
                or tile_meta.get("artifact_kind") != "terrain_diffusion_output"
                or tile_meta.get("conditioning_identity") != generation["conditioning_identity"]
                or tile_meta.get("model") != generation["model"]):
            raise ValueError("tile generation metadata mismatch")
        tiles[row, col] = (tile_arrays["elevation_m"], tile_arrays["climate"])
    height, climate, seam = stitch_tiles(tiles, seam_tolerance_m=metadata["seam_audit"]["diagnostic_seam_max_m"])
    if (not np.array_equal(height, arrays["elevation_m"])
            or not np.array_equal(climate, arrays["climate"])
            or seam != metadata["seam_audit"]):
        raise ValueError("TD stitch or seam audit mismatch")
    source_arrays = {"height_m": readonly(arrays["elevation_m"].astype(np.float64)),
                     "hydrology_mask": readonly(np.ones(height.shape, bool)),
                     "display_mask": readonly(np.ones(height.shape, bool))}
    source_metadata = {"schema": "mountain-source-v1", "origin_m_xz": metre_origin,
                       "spacing_m": 30., "coordinates": "x east, z south; arrays [z,x]",
                       "vertical_datum": "sea_zero_m",
                       "provenance": {"artifact_kind": "terrain_diffusion_output",
                                      "td_inference_run": True, "archive_sha256": expected_sha256,
                                      "generation_metadata": {
                                          "seed": str(seed),
                                          "conditioning_identity": generation["conditioning_identity"],
                                          "model": generation["model"],
                                          "seam_audit": seam,
                                          "stitched_source_manifest": str(manifest_path)}},
                       "boundary": {"policy": "all_edges_open", "halo_cells": 0,
                                    "upstream_contribution": "excluded_finite_experiment"},
                       "domain": {"calculation_domain": "finite_window_experiment",
                                  "hydrological_closure_certified": False,
                                  "closure_evidence_sha256": None,
                                  "land_boundary_crossing": "truncated_external_open_boundary"}}
    return {"arrays": source_arrays, "metadata": source_metadata,
            "identity_sha256": identity(source_arrays, source_metadata)}
