"""Canonical genuine TD pixels from immutable, globally aligned fixed tiles.

Upstream direct inference depends slightly on query shape. Hydrology therefore
owns each northwest 256-square core of a fixed 257-square inference window.
Requested shapes only crop these canonical pixels, never re-evaluate them.
"""

import hashlib
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import checked_archive, file_sha256, make_source


ALGORITHM = "hydrology-global-native-core256-query257-v1"
CORE = 256
QUERY_SIZE = 257


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def source_contract(base_identity):
    return {"algorithm": ALGORITHM, "base_generation_identity": base_identity,
            "core_size": CORE, "inference_query_size": QUERY_SIZE,
            "ownership": "floor(native_coordinate/256); northwest core; halo diagnostic only",
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class CanonicalTDSource:
    def __init__(self, backend, cache_root):
        self.backend = backend
        self.contract = source_contract(backend.identity)
        self.identity = _digest(self.contract)
        self.cache_root = Path(cache_root) / self.identity

    def close(self):
        self.backend.close()

    def _tile(self, seed, tx, tz):
        folder = self.cache_root / str(seed & 0xFFFFFFFFFFFFFFFF)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("tile-x" + str(tx) + "-z" + str(tz) + ".npz")
        pin = path.with_suffix(".sha256")
        native_origin = [tx * CORE, tz * CORE]
        if not path.exists():
            elevation, climate, metadata = self.backend.generate(seed, *native_origin, QUERY_SIZE)
            with path.open("xb") as stream:
                np.savez_compressed(stream, elevation_m=elevation, climate=climate,
                                    metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
            with pin.open("x", encoding="ascii") as stream:
                stream.write(file_sha256(path))
        if not pin.exists():
            raise ValueError("canonical tile lacks immutable external hash pin")
        sha = pin.read_text(encoding="ascii").strip()
        arrays = checked_archive(path, expected_sha256=sha)
        if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
            raise ValueError("canonical tile archive fields mismatch")
        metadata = json.loads(str(arrays["metadata_json"].item()))
        if (metadata["identity"] != self.backend.identity or int(metadata["seed"]) != seed & 0xFFFFFFFFFFFFFFFF
                or metadata["native_origin"] != native_origin or metadata["shape"] != [QUERY_SIZE, QUERY_SIZE]
                or metadata["artifact_kind"] != "terrain_diffusion_output"
                or arrays["elevation_m"].shape != (QUERY_SIZE, QUERY_SIZE)
                or arrays["climate"].shape != (5, QUERY_SIZE, QUERY_SIZE)
                or not np.isfinite(arrays["elevation_m"]).all() or not np.isfinite(arrays["climate"]).all()):
            raise ValueError("canonical tile seed/model/grid/finite contract mismatch")
        record = {"tile_xz": [tx, tz], "native_origin": native_origin, "sha256": sha,
                  "tile_file": path.name, "generation_identity": self.backend.identity,
                  "generation_metadata": metadata}
        return arrays["elevation_m"], arrays["climate"], record

    def generate(self, seed, x, z, size):
        if any(type(value) is not int for value in (seed, x, z, size)) or not 1 <= size <= 499:
            raise ValueError("bounded native canonical query requires size1..499")
        elevation = np.empty((size, size), dtype=np.float32)
        climate = np.empty((5, size, size), dtype=np.float32)
        records = []
        for tz in range(z // CORE, (z + size - 1) // CORE + 1):
            for tx in range(x // CORE, (x + size - 1) // CORE + 1):
                tile_h, tile_c, record = self._tile(seed, tx, tz)
                left, right = max(x, tx * CORE), min(x + size, (tx + 1) * CORE)
                top, bottom = max(z, tz * CORE), min(z + size, (tz + 1) * CORE)
                src = (slice(top - tz * CORE, bottom - tz * CORE), slice(left - tx * CORE, right - tx * CORE))
                dst = (slice(top - z, bottom - z), slice(left - x, right - x))
                elevation[dst] = tile_h[src]
                climate[(slice(None),) + dst] = tile_c[(slice(None),) + src]
                records.append(record)
        metadata = dict(self.backend.metadata, schema="hydrology-canonical-td-window-v1",
            identity=self.identity, base_generation_identity=self.backend.identity,
            canonical_source_contract=self.contract, seed=str(seed & 0xFFFFFFFFFFFFFFFF),
            native_origin=[x, z], shape=[size, size], native_resolution_m=self.backend.config.native_resolution_m,
            artifact_kind="terrain_diffusion_output", tile_assembly=records,
            canonical_cache_root=str(self.cache_root.parent.resolve()),
            query_size_invariant=True, hydrologic_seam_certified=False)
        return elevation, climate, metadata


def load_canonical_window(path, expected_sha256):
    arrays = checked_archive(path, expected_sha256=expected_sha256)
    if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("canonical assembled archive fields mismatch")
    metadata = json.loads(str(arrays["metadata_json"].item()))
    shape = arrays["elevation_m"].shape
    contract = metadata["canonical_source_contract"]
    if (metadata.get("schema") != "hydrology-canonical-td-window-v1" or metadata["identity"] != _digest(contract)
            or contract["algorithm"] != ALGORITHM or contract["core_size"] != CORE or contract["inference_query_size"] != QUERY_SIZE
            or metadata["base_generation_identity"] != contract["base_generation_identity"]
            or metadata["artifact_kind"] != "terrain_diffusion_output" or metadata["shape"] != list(shape)
            or len(shape) != 2 or shape[0] != shape[1] or shape[0] > 499
            or arrays["climate"].shape != (5,) + shape or not np.isfinite(arrays["elevation_m"]).all()
            or not np.isfinite(arrays["climate"]).all()):
        raise ValueError("canonical assembled source contract mismatch")
    native = metadata["native_origin"]
    spacing = metadata["native_resolution_m"]
    if len(native) != 2 or any(type(value) is not int for value in native) or spacing != 30.0:
        raise ValueError("canonical metre/native coordinate contract mismatch")
    tile_records = metadata["tile_assembly"]
    expected_tiles = {(tx, tz) for tz in range(native[1] // CORE, (native[1] + shape[0] - 1) // CORE + 1)
                      for tx in range(native[0] // CORE, (native[0] + shape[1] - 1) // CORE + 1)}
    if len(tile_records) != len(expected_tiles) or {tuple(record["tile_xz"]) for record in tile_records} != expected_tiles:
        raise ValueError("canonical tile assembly ownership mismatch")
    reconstructed = np.empty_like(arrays["elevation_m"])
    reconstructed_climate = np.empty_like(arrays["climate"])
    for record in tile_records:
        tx, tz = record["tile_xz"]
        filename = "tile-x" + str(tx) + "-z" + str(tz) + ".npz"
        if record["tile_file"] != filename or record["native_origin"] != [tx * CORE, tz * CORE]:
            raise ValueError("canonical component filename/origin mismatch")
        generated = record["generation_metadata"]
        base_record = {key: value for key, value in generated.items() if key not in {
            "identity", "seed", "native_origin", "shape", "native_resolution_m", "artifact_kind", "seconds"}}
        if (generated["identity"] != metadata["base_generation_identity"] or _digest(base_record) != generated["identity"]
                or generated["native_origin"] != record["native_origin"] or generated["shape"] != [QUERY_SIZE, QUERY_SIZE]
                or generated["seed"] != metadata["seed"]):
            raise ValueError("canonical component real generation identity mismatch")
        tile_path = Path(metadata["canonical_cache_root"]) / metadata["identity"] / metadata["seed"] / filename
        tile = checked_archive(tile_path, expected_sha256=record["sha256"])
        if json.loads(str(tile["metadata_json"].item())) != generated:
            raise ValueError("canonical component metadata differs from pinned original")
        left, right = max(native[0], tx * CORE), min(native[0] + shape[1], (tx + 1) * CORE)
        top, bottom = max(native[1], tz * CORE), min(native[1] + shape[0], (tz + 1) * CORE)
        src = (slice(top - tz * CORE, bottom - tz * CORE), slice(left - tx * CORE, right - tx * CORE))
        dst = (slice(top - native[1], bottom - native[1]), slice(left - native[0], right - native[0]))
        reconstructed[dst] = tile["elevation_m"][src]
        reconstructed_climate[(slice(None),) + dst] = tile["climate"][(slice(None),) + src]
    if not np.array_equal(reconstructed, arrays["elevation_m"]) or not np.array_equal(reconstructed_climate, arrays["climate"]):
        raise ValueError("canonical assembled pixels differ from real pinned component TD")
    source = make_source(arrays["elevation_m"], climate=arrays["climate"],
        origin_m_xz=[coordinate * spacing for coordinate in native], spacing_m=spacing,
        provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
            "archive_sha256": expected_sha256, "generation_metadata": metadata,
            "historical_game_height_conditioning": False},
        boundary={"policy": "explicit", "halo_cells": 0, "upstream_contribution": "excluded_finite_experiment"})
    return source, source["metadata"]
