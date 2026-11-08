"""Versioned frozen macro products; no evolution occurs in read/sample paths.

Coordinates are absolute metres, X east/Z south, arrays [z,x]. Grid samples
are cell centres at origin + (index + .5)*spacing. The finite background is a
periodic plane, not a sphere or a replacement for infinite-world semantics.
"""
from collections import deque
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

SCHEMA = "tectonic-frozen-product-v2"
LEGACY_SCHEMA = "tectonic-frozen-product-v1"
LEGACY_ALGORITHM = "kinematic-crust-1"
AGGREGATE_ALGORITHM = "kinematic-crust-2"
COMPACT_ALGORITHM = "kinematic-crust-3"
ALGORITHM = "kinematic-crust-4"
WORLD_SEED = 20261020
STATE_FIELDS = ("plate_coverage", "continental_m", "oceanic_m", "plate_seeds_m",
                "velocities_m_per_step")
SURFACE_FIELDS = ("elevation_m", "plate_id", "continental_fraction", "crust_thickness_m")
CORE_METADATA_FIELDS = ("algorithm_version", "config", "boundary", "array_order", "axes",
                        "velocity_unit", "time_unit", "seed_derivation", "purpose_seeds",
                        "initial_state_source", "status", "densities_kg_m3", "elevation_offset_m",
                        "budget_unit", "numerical_error_relative_tolerance", "transport")
BUDGET_FIELDS = {"step", "initial_continental_m3", "initial_oceanic_m3", "final_continental_m3",
                 "final_oceanic_m3", "rift_oceanic_added_m3", "subducted_oceanic_m3",
                 "sutured_continental_m3", "advection_continental_residual_m3",
                 "advection_oceanic_residual_m3", "continental_balance_residual_m3",
                 "oceanic_balance_residual_m3", "advection_continental_l2_loss_m4",
                 "max_coverage_overlap", "gap_area_m2", "convergent_faces", "divergent_faces",
                 "transform_faces"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _config(config, *, legacy=False):
    values = asdict(config) if not isinstance(config, dict) else dict(config)
    values = json.loads(_json(values))
    expected = {"shape", "cell_size_m", "origin_x_m", "origin_z_m", "plate_count", "world_seed",
                "steps", "time_step", "max_speed_m_per_step", "continental_thickness_m",
                "oceanic_thickness_m", "subduction_fraction", "rift_fraction"}
    if not legacy:
        expected.update(("microcells_per_plate", "min_plate_cells"))
    if set(values) != expected:
        raise ValueError("incomplete or unsupported configuration")
    shape = values.get("shape")
    if (not isinstance(shape, list) or len(shape) != 2 or
            any(type(n) is not int or n < 2 for n in shape)):
        raise ValueError("shape must contain two integers >= 2")
    if values.get("world_seed") != WORLD_SEED:
        raise ValueError("world_seed must be 20261020")
    for name in ("cell_size_m", "time_step", "continental_thickness_m", "oceanic_thickness_m"):
        if not isinstance(values.get(name), (int, float)) or not np.isfinite(values[name]) or values[name] <= 0:
            raise ValueError(name + " must be finite and positive")
    for name in ("origin_x_m", "origin_z_m"):
        if not isinstance(values.get(name), (int, float)) or not np.isfinite(values[name]):
            raise ValueError(name + " must be finite")
    if type(values.get("plate_count")) is not int or not 1 <= values["plate_count"] <= shape[0] * shape[1]:
        raise ValueError("plate_count outside grid capacity")
    if type(values.get("steps")) is not int or values["steps"] < 0:
        raise ValueError("steps must be a nonnegative integer")
    for name in ("max_speed_m_per_step", "subduction_fraction", "rift_fraction"):
        if not isinstance(values[name], (int, float)) or not np.isfinite(values[name]) or values[name] < 0:
            raise ValueError("invalid " + name)
    if any(values[name] > 1 for name in ("subduction_fraction", "rift_fraction")):
        raise ValueError("mechanism fractions must be <= 1")
    with np.errstate(over="ignore", invalid="ignore"):
        extent = np.array(shape, dtype=float) * values["cell_size_m"]
        area = np.float64(values["cell_size_m"]) ** 2
        upper = extent[::-1] + [values["origin_x_m"], values["origin_z_m"]]
    if not np.isfinite(extent).all() or not np.isfinite(area) or not np.isfinite(upper).all():
        raise ValueError("nonfinite background extent or area")
    if values["time_step"] * values["max_speed_m_per_step"] * np.sqrt(2) > values["cell_size_m"]:
        raise ValueError("configured maximum speed exceeds conservative L1 CFL bound")
    if not legacy:
        from types import SimpleNamespace
        from terrain_pipeline.tectonic_formation import validate_formation
        validate_formation(SimpleNamespace(**values))
    return values


def plan(config, *, max_memory_bytes=2_000_000_000, max_cell_plate_steps=200_000_000):
    """Conservative CPU allocation/work estimate, not a wall-clock guarantee."""
    config = _config(config)
    cells = int(config["shape"][0]) * int(config["shape"][1])
    # Two snapshots, solver temporaries, frozen copies/hash IO, flood-fill queue.
    from types import SimpleNamespace
    from terrain_pipeline.tectonic_formation import microcell_count
    microcells = microcell_count(SimpleNamespace(**config))
    # Fragment graph/JSON audit and heap worst case are bounded by resolved cells.
    memory = cells * (config["plate_count"] * 8 * 40 + 2048) + microcells * 16384
    # Pairwise collision loops are quadratic in plate count.
    plate_passes = config["plate_count"] * (config["plate_count"] + 1) // 2
    geometry_work = 9 * microcells * max(1, (9 * microcells).bit_length()) + cells * max(1, cells.bit_length())
    from terrain_pipeline.tectonic_shapes import shape_parameters, formation_image_budget
    _, shapes = shape_parameters(config["world_seed"], config["plate_count"])
    # Every resolved cell may be a split fragment: use cells, not site count.
    shape_image_visits = cells * formation_image_budget(config["shape"][::-1], shapes)
    work = cells * (plate_passes * (config["steps"] + 1) + microcells) + geometry_work + shape_image_visits
    if (not np.isfinite(max_memory_bytes) or not np.isfinite(max_cell_plate_steps) or
            max_memory_bytes <= 0 or max_cell_plate_steps <= 0):
        raise ValueError("resource budgets must be positive")
    return {"estimated_peak_memory_bytes": memory, "cell_plate_steps": work,
            "formation_microcells": microcells, "formation_shape_image_visits_bound": shape_image_visits, "formation_distance_cell_visits": cells * microcells,
            "allowed": memory <= max_memory_bytes and work <= max_cell_plate_steps,
            "max_memory_bytes": max_memory_bytes, "max_cell_plate_steps": max_cell_plate_steps,
            "estimate_basis": "40 float64 plate grids + 2048 bytes/cell graph/audit + 16384 bytes/site (9-tile Voronoi audit); streamed site/shape distances and plate pairs; shape search bound uses one fragment per cell; CPU only",
            "background_extent_m": [n * config["cell_size_m"] for n in config["shape"]],
            "config": config}


def connected_ocean(elevation_m, seed_zx=None):
    """4-neighbour periodic flood fill below datum 0.

    With no exterior on a torus, the deepest wet cell is the explicit ocean
    seed (row-major ties). Other wet components are enclosed depressions.
    """
    elevation = np.asarray(elevation_m)
    if elevation.ndim != 2 or not np.isfinite(elevation).all():
        raise ValueError("finite 2D elevation required")
    wet = elevation < 0
    ocean = np.zeros(wet.shape, dtype=np.bool_)
    if not wet.any():
        return ocean, None
    if seed_zx is None:
        seed_zx = list(np.unravel_index(np.argmin(elevation), elevation.shape))
    z, x = map(int, seed_zx)
    if not (0 <= z < wet.shape[0] and 0 <= x < wet.shape[1]) or not wet[z, x]:
        raise ValueError("ocean seed must be a submerged cell")
    queue = deque([(z, x)])
    ocean[z, x] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in (((z - 1) % wet.shape[0], x), ((z + 1) % wet.shape[0], x),
                       (z, (x - 1) % wet.shape[1]), (z, (x + 1) % wet.shape[1])):
            if wet[nz, nx] and not ocean[nz, nx]:
                ocean[nz, nx] = True
                queue.append((nz, nx))
    return ocean, [int(v) for v in seed_zx]


def _summary(array):
    return {"shape": list(array.shape), "dtype": array.dtype.str,
            "sha256": _digest(array.tobytes(order="C")),
            "min": array.min().item(), "max": array.max().item()}


def _immutable(array):
    # bytes-backed arrays cannot be made writable again by setflags().
    return np.frombuffer(array.tobytes(order="C"), dtype=array.dtype).reshape(array.shape)


class FrozenTectonicProduct:
    """Validated immutable snapshot. Construct via freeze() or load_product()."""

    def __init__(self, manifest, arrays):
        _validate(manifest, arrays)
        self._manifest_json = _json(manifest)
        self.arrays = MappingProxyType({key: _immutable(value) for key, value in arrays.items()})

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def identity(self):
        return self.manifest["identity"]

    def sample(self, x_m, z_m, *, outside="wrap", state="final"):
        """Broadcast queries; bilinear continuous fields, nearest categorical.

        outside='reject' accepts the half-open background rectangle only;
        outside='wrap' repeats the declared periodic plane in both axes.
        """
        if outside not in ("wrap", "reject") or state not in ("initial", "final"):
            raise ValueError("invalid sampling policy or state")
        config = self.manifest["config"]
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(z_m, dtype=float))
        if not np.isfinite(x).all() or not np.isfinite(z).all():
            raise ValueError("sample coordinates must be finite")
        spacing = config["cell_size_m"]
        nz, nx = config["shape"]
        local_x = (x - config["origin_x_m"]) / spacing
        local_z = (z - config["origin_z_m"]) / spacing
        if not np.isfinite(local_x).all() or not np.isfinite(local_z).all():
            raise ValueError("coordinates exceed finite grid index range")
        if outside == "reject" and (np.any((local_x < 0) | (local_x >= nx)) or
                                     np.any((local_z < 0) | (local_z >= nz))):
            raise ValueError("query outside background domain")
        gx = np.remainder(local_x, nx) - .5
        gz = np.remainder(local_z, nz) - .5
        ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
        fx, fz = gx - ix, gz - iz
        result = {}
        for name in (*SURFACE_FIELDS, "ocean_connected"):
            field = self.arrays[state + "/" + name]
            if name in ("plate_id", "ocean_connected"):
                value = field[np.floor(gz + .5).astype(np.int64) % nz,
                              np.floor(gx + .5).astype(np.int64) % nx]
            else:
                value = ((1 - fz) * ((1 - fx) * field[iz % nz, ix % nx] +
                                    fx * field[iz % nz, (ix + 1) % nx]) +
                         fz * ((1 - fx) * field[(iz + 1) % nz, ix % nx] +
                               fx * field[(iz + 1) % nz, (ix + 1) % nx]))
            result[name] = np.array(value, copy=True)
        return result


def _validate(manifest, arrays):
    if not isinstance(manifest, dict) or set(manifest) != {
            "schema", "algorithm", "config", "coordinates", "core_metadata", "steps", "budgets",
            "material_unit", "ocean_seeds_zx", "arrays", "identity"}:
        raise ValueError("incomplete or unsupported manifest")
    legacy = manifest.get("schema") == LEGACY_SCHEMA and manifest.get("algorithm") == LEGACY_ALGORITHM
    if not legacy and (manifest.get("schema") != SCHEMA or manifest.get("algorithm") not in (ALGORITHM, COMPACT_ALGORITHM, AGGREGATE_ALGORITHM)):
        raise ValueError("unsupported schema or algorithm")
    config = _config(manifest["config"], legacy=legacy)
    metadata = manifest["core_metadata"]
    if (not isinstance(metadata, dict) or set(metadata) != (set(CORE_METADATA_FIELDS) if legacy else set(CORE_METADATA_FIELDS) | {"formation"}) or
            metadata["algorithm_version"] != manifest["algorithm"] or _config(metadata["config"], legacy=legacy) != config or
            metadata["boundary"] != "periodic_plane" or metadata["array_order"] != "z,x" or
            metadata["time_unit"] != "uncalibrated offline-step" or
            metadata["velocity_unit"] != "m/offline-step" or
            metadata["densities_kg_m3"] != {"mantle": 3300, "continental": 2800, "oceanic": 3000} or
            metadata["elevation_offset_m"] != -4500 or metadata["budget_unit"] != "m3"):
        raise ValueError("invalid core provenance or material units")
    expected_seeds = {purpose: int.from_bytes(hashlib.sha256(
        f"{WORLD_SEED}:tectonic:{purpose}".encode()).digest()[:8], "little")
        for purpose in ("plates", "crust", "velocity")}
    if metadata["purpose_seeds"] != expected_seeds:
        raise ValueError("invalid purpose seeds")
    if metadata["seed_derivation"] != "SHA256(f'{world_seed}:tectonic:{purpose}'), first 8 bytes little-endian":
        raise ValueError("unsupported purpose seed derivation")
    steps = manifest["steps"]
    if (not isinstance(steps, dict) or set(steps) != {"initial", "final"} or
            any(type(v) is not int or v < 0 for v in steps.values()) or
            steps["final"] - steps["initial"] != config["steps"]):
        raise ValueError("invalid offline steps")
    if (not isinstance(manifest["budgets"], list) or len(manifest["budgets"]) != config["steps"] or
            manifest["material_unit"] != "m3 per material; equivalent thickness m"):
        raise ValueError("invalid material ledger")
    for offset, row in enumerate(manifest["budgets"], 1):
        if (not isinstance(row, dict) or not BUDGET_FIELDS.issubset(row) or row.get("step") != steps["initial"] + offset or
                any(type(v) not in (int, float) or not np.isfinite(v) for v in row.values())):
            raise ValueError("invalid budget row")
        for name in ("initial_continental_m3", "initial_oceanic_m3", "final_continental_m3",
                     "final_oceanic_m3", "rift_oceanic_added_m3", "subducted_oceanic_m3",
                     "sutured_continental_m3"):
            if row[name] < 0:
                raise ValueError("negative material ledger quantity")
    if manifest.get("coordinates") != COORDINATES:
        raise ValueError("unsupported coordinate/boundary semantics")
    expected = {f"{state}/{name}" for state in ("initial", "final")
                for name in (*STATE_FIELDS, *SURFACE_FIELDS, "ocean_connected")}
    if set(arrays) != expected or set(manifest["arrays"]) != expected:
        raise ValueError("missing or unexpected product fields")
    shape = tuple(config["shape"])
    plates = config["plate_count"]
    for key, array in arrays.items():
        name = key.split("/")[1]
        target_shape = shape
        if name in STATE_FIELDS[:3]:
            target_shape = (plates, *shape)
        elif name in STATE_FIELDS[3:]:
            target_shape = (plates, 2)
        dtype = np.dtype("float64")
        if name == "plate_id":
            dtype = np.dtype("int64")
        elif name == "ocean_connected":
            dtype = np.dtype("bool")
        if array.shape != target_shape or array.dtype != dtype or not np.isfinite(array).all():
            raise ValueError("invalid field " + key)
        if _summary(array) != manifest["arrays"][key]:
            raise ValueError("field hash/summary mismatch: " + key)
        if name in ("continental_m", "oceanic_m", "crust_thickness_m") and np.any(array < 0):
            raise ValueError("negative material thickness")
        if name in ("continental_fraction", "plate_coverage") and np.any((array < 0) | (array > 1 + 1e-12)):
            raise ValueError("invalid fraction")
        if name == "plate_id" and np.any((array < 0) | (array >= plates)):
            raise ValueError("invalid plate ID")
    for state in ("initial", "final"):
        prefix = state + "/"
        if not np.allclose(arrays[prefix + "plate_coverage"].sum(axis=0), 1, rtol=0, atol=1e-9):
            raise ValueError("coverage must partition unity")
        continental = arrays[prefix + "continental_m"].sum(axis=0)
        oceanic = arrays[prefix + "oceanic_m"].sum(axis=0)
        thickness = continental + oceanic
        fraction = np.divide(continental, thickness, out=np.zeros_like(thickness), where=thickness > 0)
        derived = {"elevation_m": continental * (1 - 2800 / 3300) + oceanic * (1 - 3000 / 3300) - 4500,
                   "plate_id": arrays[prefix + "plate_coverage"].argmax(axis=0),
                   "continental_fraction": fraction, "crust_thickness_m": thickness}
        for name, expected_field in derived.items():
            if not np.array_equal(arrays[prefix + name], expected_field):
                raise ValueError("surface inconsistent with crust: " + name)
        seed_positions = arrays[prefix + "plate_seeds_m"] - [config["origin_x_m"], config["origin_z_m"]]
        if np.any(seed_positions < 0) or np.any(seed_positions >= np.array(shape[::-1]) * config["cell_size_m"]):
            raise ValueError("plate seeds outside background")
        ocean, seed = connected_ocean(arrays[prefix + "elevation_m"])
        if seed != manifest["ocean_seeds_zx"][state] or not np.array_equal(ocean, arrays[prefix + "ocean_connected"]):
            raise ValueError("invalid ocean connectivity")
    if not legacy:
        from terrain_pipeline.tectonic_formation import validate_geometry
        geometry = metadata["formation"]
        expected_formation = ({ALGORITHM: "periodic-voronoi-shaped-core-growth-1",
                               COMPACT_ALGORITHM: "periodic-voronoi-core-growth-1",
                               AGGREGATE_ALGORITHM: "periodic-voronoi-adjacency-1"}[manifest["algorithm"]])
        if geometry is not None and (not isinstance(geometry, dict) or geometry.get("version") != expected_formation):
            raise ValueError("algorithm and formation geometry disagree")
        validate_geometry(config, metadata["formation"], arrays["initial/plate_id"], metadata["initial_state_source"])
    previous = {material: float(arrays["initial/" + material + "_m"].sum() * config["cell_size_m"] ** 2)
                for material in ("continental", "oceanic")}
    for row in manifest["budgets"]:
        for material in previous:
            if not np.isclose(row["initial_" + material + "_m3"], previous[material], rtol=1e-12, atol=1e-3):
                raise ValueError("disconnected material ledger")
            previous[material] = row["final_" + material + "_m3"]
        for material, change in (("continental", 0.),
                                 ("oceanic", row["rift_oceanic_added_m3"] - row["subducted_oceanic_m3"])):
            if not np.isclose(row["final_" + material + "_m3"],
                              row["initial_" + material + "_m3"] + change, rtol=1e-12, atol=1e-3):
                raise ValueError("material ledger does not close")
    for material, volume in previous.items():
        actual = float(arrays["final/" + material + "_m"].sum() * config["cell_size_m"] ** 2)
        if not np.isclose(actual, volume, rtol=1e-12, atol=1e-3):
            raise ValueError("final material volume does not match ledger")
    payload = dict(manifest)
    identity = payload.pop("identity", None)
    if identity != _digest(_json(payload).encode()):
        raise ValueError("product identity mismatch")


COORDINATES = {"axes": "X east, Z south; arrays [z,x]", "length_unit": "m",
               "height_datum_m": 0, "grid": "cell centres at origin+(index+0.5)*spacing",
               "boundary": "periodic-plane", "time_unit": "uncalibrated offline step",
               "ocean_rule": "4-neighbour periodic component of deepest submerged cell; row-major tie"}


def freeze(config, result):
    """Copy and validate a core EvolutionResult into a stable content identity."""
    from terrain_pipeline.tectonic_evolution import surface_fields
    config = _config(config)
    arrays = {}
    ocean_seeds = {}
    for label, state in (("initial", result.initial), ("final", result.final)):
        for name in STATE_FIELDS:
            arrays[label + "/" + name] = np.array(getattr(state, name), dtype=np.float64, copy=True)
        fields = surface_fields(state)
        for name in SURFACE_FIELDS:
            arrays[label + "/" + name] = np.array(fields[name], dtype=np.int64 if name == "plate_id" else np.float64)
        ocean, seed = connected_ocean(fields["elevation_m"])
        arrays[label + "/ocean_connected"] = ocean
        ocean_seeds[label] = seed
    manifest = {"schema": SCHEMA, "algorithm": ALGORITHM, "config": config,
                "coordinates": COORDINATES,
                "core_metadata": {key: result.metadata[key] for key in (*CORE_METADATA_FIELDS, "formation")},
                "steps": {"initial": result.initial.step, "final": result.final.step},
                "budgets": result.budgets, "material_unit": "m3 per material; equivalent thickness m",
                "ocean_seeds_zx": ocean_seeds, "arrays": {k: _summary(v) for k, v in arrays.items()}}
    manifest = json.loads(_json(manifest))
    manifest["identity"] = _digest(_json(manifest).encode())
    return FrozenTectonicProduct(manifest, arrays)


def save_product(product, path):
    """Validate a cold read before atomic no-overwrite hard-link publication."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".tectonic-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            np.savez(stream, manifest_json=np.array(_json(product.manifest)), **product.arrays)
            stream.flush()
            os.fsync(stream.fileno())
        loaded = load_product(temporary, expected_identity=product.identity)
        os.link(temporary, path)
        return loaded
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_product(path, *, expected_identity=None):
    try:
        with np.load(path, allow_pickle=False) as archive:
            if len(archive.files) != len(set(archive.files)):
                raise ValueError("duplicate archive fields")
            raw = archive["manifest_json"]
            if raw.shape != () or raw.dtype.kind != "U":
                raise ValueError("invalid manifest encoding")
            manifest = json.loads(str(raw), object_pairs_hook=_unique_object)
            arrays = {k: archive[k] for k in archive.files if k != "manifest_json"}
        product = FrozenTectonicProduct(manifest, arrays)
    except (KeyError, TypeError, OSError, EOFError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid frozen tectonic product") from error
    if expected_identity is not None and product.identity != expected_identity:
        raise ValueError("unexpected product identity")
    return product


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key: " + key)
        result[key] = value
    return result


def prepare(config, path, **budgets):
    """Explicit offline generation; resource rejection precedes core invocation."""
    report = plan(config, **budgets)
    if not report["allowed"]:
        raise ValueError("CPU resource budget exceeded: " + _json(report))
    if Path(path).exists():
        raise FileExistsError(path)
    from terrain_pipeline.tectonic_evolution import evolve
    return save_product(freeze(config, evolve(config)), path)
