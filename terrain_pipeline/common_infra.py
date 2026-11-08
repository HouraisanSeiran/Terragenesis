"""Shared low-level infrastructure: hashing, canonical JSON, seeds, coordinates, atomic IO, mmap.

One home for helpers that were copied into dozens of modules.  Every function here
reproduces the byte/value output of named legacy implementations (listed in each
docstring; the full table is ``.scratch/algorithm-refactor-20261105/r2/infra-migration.md``
and the equivalence proof is ``tests/test_common_infra.py``).  Legacy implementations
that look alike but produce different output are kept as explicitly named variants
or parameters, never silently merged.

Conventions that hold for every function below:

* No ``hash()``, wall-clock time or system entropy is used; results are reproducible.
* Array digests are claimed equivalent for arrays with ``ndim >= 1``.  For 0-d arrays
  the legacy implementations disagree with each other (``np.ascontiguousarray`` turns
  ``()`` into ``(1,)``); this module follows the ``ascontiguousarray`` majority.
* This module imports only the standard library and NumPy and has no import-time effects.
"""

import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


WORLD_SEED = 20260903
WORLD_SEED_LEGACY_20261020 = 20261020
NATIVE_GRID = 4096
NATIVE_ORIGIN_M = -61440.0
NATIVE_SPACING_M = 30.0
NATIVE_WINDOW_Z0, NATIVE_WINDOW_Z1, NATIVE_WINDOW_X0, NATIVE_WINDOW_X1 = (1382, 3049, 1176, 2843)
SHA256_CHUNK_BYTES = 1048576
_HEX = frozenset("0123456789abcdef")
SEED_DERIVATION = "sha256(terragenesis-procedural-mountains-v1|world_seed|purpose), first 8 bytes big-endian"
MAX_BYTES = 134217728
MAX_METADATA = 1048576
GRID_MAX_CELLS = 1638400
MAX_FORCING_ENTRIES = 3145728
BOUNDARY_KINDS = (
    "interior",
    "open_outflow",
    "closed_wall",
    "prescribed_stage",
    "prescribed_discharge",
    "unknown_boundary",
)
SOURCE_SCHEMA = "mountain-source-v1"
SOURCE_MAX_CELLS = 250000
SOURCE_KINDS = {"legacy_td_game_conditioned", "terrain_diffusion_output"}


def file_sha256(path):
    """Hex SHA-256 of a file's bytes (streamed, 1 MiB blocks; accepts ``str`` or ``Path``).

    Output-identical to every legacy streaming or ``read_bytes()`` variant, whatever the
    block size: ``artifacts.bundles.file_sha256``, ``coastal_marine_product.file_hash``,
    ``coastal_terrain_product.file_hash``, ``complete_delta.sha256``, ``dem_domain.file_sha256``
    (``hashlib.file_digest``), ``large_delta_*`` ``_sha``/``sha256``/``digest``, ``legacy_region._sha256``,
    ``metric_region_storage._sha256``, ``drainage_kernels.file_sha256``,
    ``new_world_*`` ``digest``/``_hash``/``_digest``/``file_sha256``,
    ``plate_td_product.digest``, ``special_terrain_l1_sinkhole.file_sha256``,
    ``surface_network_consumer._file_hash``, ``finite_river_product.sha256_file``,
    ``metric_cross_region._file_sha256`` and ``world_terrain_disk_store._sha``.
    """

    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(SHA256_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def file_sha256_and_size(path, max_bytes):
    """``(hex, size)`` of a regular, non-symlink, non-empty file no larger than ``max_bytes``.

    Hash part equals ``file_sha256``; checks follow ``surface_development_readiness._digest``
    (the error message texts are generic here, the exception type is ``ValueError`` in both).
    """

    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("missing or linked input: " + str(path))
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError("input size cap: " + str(path))
    digest = file_sha256(path)
    if path.stat().st_size != size:
        raise ValueError("input changed while hashing")
    return digest, size


def file_record(path):
    """``{"path": resolved str, "sha256": hex, "bytes": size}`` as ``td_natural_outlet_certification._file_record``."""

    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}


def is_sha256_hex(value):
    """True for a 64-character lowercase hex string (the legacy ``_sha`` / ``_sha256_text`` checks)."""

    return isinstance(value, str) and len(value) == 64 and all(c in _HEX for c in value)


def require_sha256_hex(value, name="value"):
    """Return ``value`` or raise ``ValueError("<name> must be a lowercase SHA256")``."""

    if not is_sha256_hex(value):
        raise ValueError(name + " must be a lowercase SHA256")
    return value


def require_sha256_hex_lowercase(value):
    """Same check as ``require_sha256_hex``, but the message is the legacy ``"lowercase SHA256 required"``.

    The metric-contract validators (``surface_rivers/metric_contracts._sha``) published that exact text, and
    argument checks are part of what a caller can see, so the wording is kept as a named variant rather
    than silently replaced.  Returns ``None`` exactly as the legacy helper did.
    """

    if not is_sha256_hex(value):
        raise ValueError("lowercase SHA256 required")
    return None


def sha256_chunks(*chunks):
    """SHA-256 over ``str`` (UTF-8) or bytes chunks in order (``finite_river_block_schedule._sha_bytes``)."""

    digest = hashlib.sha256()
    for chunk in chunks:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        digest.update(chunk)
    return digest.hexdigest()


def array_sha256_raw(array, dtype=None):
    """SHA-256 of the C-order bytes only (no shape, no dtype in the digest).

    Equals ``artifacts.contracts.array_hash``, ``coastal_terrain_product.array_hash``,
    ``coastal_detail_product.array_hash`` (64-row chunks give the same bytes),
    ``surface_network_tiles._record['sha256']`` and, with ``dtype=np.uint8``,
    ``coastal_delta_geological._mask_identity``.
    """

    return hashlib.sha256(np.ascontiguousarray(array, dtype=dtype).tobytes()).hexdigest()


def arrays_sha256_raw(*arrays):
    """SHA-256 over the concatenated raw bytes of several arrays
    (``large_scale_surface_network._sha256_arrays``, ``finite_river_block_schedule._event_stream_sha``)."""

    digest = hashlib.sha256()
    for array in arrays:
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def array_sha256(array):
    """SHA-256 of ``str(shape)`` + ``dtype.str`` + C bytes.

    Equals ``artifacts.encoding.shaped_array_hash``, ``environment_land_cover._array_digest``,
    ``environment_world_product._array_digest``, ``rainfall_runoff._hash``,
    ``finite_river_product.array_sha``, ``metric_pet_et._array_digest`` and
    ``hydrology_detail_tributaries._array_digest``.
    """

    array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def array_sha256_dtype_shapejson(array, compact_shape=True):
    """SHA-256 of ``dtype.str`` + JSON ``list(shape)`` + C bytes.

    ``compact_shape=True`` (``"[2,3]"``): ``geology_properties._array_digest``,
    ``lake_river_connector._array_hash``, ``surface_lake_network._array_hash``,
    ``mountain_depression_geometry._hash``.
    ``compact_shape=False`` (``"[2, 3]"``, default ``json.dumps``): ``lake_routing._array_hash``.
    """

    array = np.ascontiguousarray(array)
    shape = (
        json.dumps(list(array.shape), separators=(",", ":"))
        if compact_shape
        else json.dumps(list(array.shape))
    )
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(shape.encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def array_sha256_json_header(array):
    """SHA-256 of compact-sorted JSON ``[dtype.str, shape]`` + C bytes (``surface_coast_drop._array_hash``)."""

    array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(canonical_json([array.dtype.str, list(array.shape)]).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def arrays_sha256_dtypename_shapejson(*arrays):
    """Per array: ``str(dtype)`` + compact JSON shape + bytes (``large_surface_network_validation._array_hash``).

    Uses the dtype *name* (``float64``), not ``dtype.str`` (``<f8``).
    """

    digest = hashlib.sha256()
    for array in arrays:
        array = np.ascontiguousarray(array)
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def named_arrays_sha256(arrays, metadata):
    """Identity of ``{name: array}`` + JSON metadata: ``surface_adaptive_geometry.adaptive_geometry_identity``
    and ``surface_adaptive_io.geometry_identity`` (identical bodies).

    Metadata is dumped with ``sort_keys`` and default separators, ASCII; per sorted name the digest
    gets name, ``str(dtype)``, int64 shape bytes and the raw bytes (arrays are NOT made contiguous,
    as in the legacy code).
    """

    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode("ascii"))
    for name in sorted(arrays):
        value = arrays[name]
        digest.update(name.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape, np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def world_pairs_sha256(pairs):
    """SHA-256 of ``(n, 2)`` little-endian int64 pairs in the given order
    (``metric_backbone_precompute._sha_world_pairs``, ``backbone_shape_fidelity.world_path_sha256``)."""

    block = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2), dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def sorted_world_pairs_sha256(pairs):
    """As ``world_pairs_sha256`` but rows sorted by ``(x, z)`` first (``metric_highland_sources.member_sha256``)."""

    keys = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2))
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    return hashlib.sha256(np.ascontiguousarray(keys[order], "<i8").tobytes()).hexdigest()


def points_sha256(x, z):
    """Order-independent digest of a float64 point set: lexsort by ``(x, z)``, raw ``(n, 2)`` bytes.

    Equals ``geology_properties._points_digest`` for any input, and ``environment_seasonal_air._points_digest``
    / ``metric_environment_query._points_digest`` when ``x`` and ``z`` are already 1-D float64
    (those two keep the caller's dtype and shape; float32 input is NOT claimed equivalent).
    """

    flat_x = np.asarray(x, np.float64).reshape(-1)
    flat_z = np.asarray(z, np.float64).reshape(-1)
    order = np.lexsort((flat_z, flat_x))
    canonical = np.stack((flat_x[order], flat_z[order]), axis=1)
    return hashlib.sha256(np.ascontiguousarray(canonical).tobytes()).hexdigest()


def points_ordinal_sha256(x, z, ordinal):
    """``points_sha256`` with a third float64 ``ordinal`` column (``metric_environment_query._ordinal_digest``)."""

    flat_x = np.asarray(x, np.float64).reshape(-1)
    flat_z = np.asarray(z, np.float64).reshape(-1)
    order = np.lexsort((flat_z, flat_x))
    canonical = np.stack(
        (flat_x[order], flat_z[order], np.asarray(ordinal, np.float64)[order]), axis=1
    )
    return hashlib.sha256(np.ascontiguousarray(canonical).tobytes()).hexdigest()


def canonical_json(value, *, compact=True, ensure_ascii=True, allow_nan=False):
    """``json.dumps(value, sort_keys=True, ...)`` with explicit knobs; defaults = the most common legacy form.

    Defaults (compact, ASCII, strict NaN): ``hybrid_river_graph.canonical_json``, ``artifacts.encoding.json_text``,
    ``lake_river_connector._json``, ``surface_lake_network._json``, ``mountain_depression_geometry._json``,
    ``surface_coast_drop._json``, ``td_material_field._json``, ``hydrology_detail_tributaries._digest``,
    ``environment_regional_hydraulics._digest``, ``natural_outlet_certification._digest``,
    ``new_world_hydrology._hash`` (digest text).
    ``ensure_ascii=False``: ``geology_properties._canonical``, ``surface_development_readiness._canonical_json``,
    ``geography_preparation_inventory._digest``.
    ``compact=False`` (``", "`` / ``": "``): ``hydrology_detail._digest``, ``hydrology_detail_projection._digest``,
    ``hydrology_detail_td._digest``, ``hydrology_seasonal_hybrid._digest``; with ``json_sha256``:
    ``drainage_kernels.canonical_json_digest`` (``json_sha256(v, compact=False)``) and
    ``drainage_kernels.canonical_json_digest_compact`` (``json_sha256(v)``).
    ``allow_nan=True``: ``coastal_marine_product.identity``, ``coastal_archipelago_product.identity`` (only
    differ from the strict form when a NaN/Infinity is present; the strict form raises instead).
    """

    options = {"sort_keys": True, "ensure_ascii": ensure_ascii, "allow_nan": allow_nan}
    if compact:
        options["separators"] = (",", ":")
    return json.dumps(value, **options)


def json_sha256(value, **options):
    """SHA-256 of ``canonical_json(value, **options)`` encoded as UTF-8."""

    return hashlib.sha256(canonical_json(value, **options).encode("utf-8")).hexdigest()


def canonical_json_digest_default(value):
    """SHA-256 of ``json.dumps(value, sort_keys=True, allow_nan=False)`` (default separators).

    Same as ``json_sha256(value, compact=False)`` under its historical name, because
    ``drainage_kernels.canonical_json_digest`` published that name in its own callers.
    """

    return json_sha256(value, compact=False)


def strict_json(payload):
    """``json.loads`` that rejects duplicate keys and non-finite constants (``artifacts.encoding.strict_json``).

    Only used for payloads this module itself wrote or for externally pinned manifests, so a duplicate
    key or a bare ``NaN`` is a real integrity failure rather than something to tolerate.
    """

    def pairs(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError("duplicate JSON key")
            parsed[key] = value
        return parsed

    def constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)


def canonical_json_checked(value):
    """``artifacts.contracts.canonical_json``: compact, UTF-8 (not escaped), strict, plus type validation.

    Only str keys, finite floats and JSON scalars/lists/dicts are accepted (tuples are rejected).
    """

    def check(item):
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("JSON keys must be strings")
            for child in item.values():
                check(child)
            return None
        if isinstance(item, list):
            for child in item:
                check(child)
            return None
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
            return None
        if item is None or isinstance(item, (str, bool, int)):
            return None
        raise ValueError("parameters must contain JSON values")

    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def record_identity_sha256(record, *, exclude=("identity",), exclude_suffixes=(), recursive=False, allow_nan=False):
    """SHA-256 of a compact-sorted record with some keys removed (the product ``identity`` pattern).

    * ``exclude=("identity","source_paths")``: ``new_world_source_mosaic.identity``.
    * ``exclude=("identity","terrain_path")``: ``new_world_stage1._identity``.
    * ``exclude=("source_path",)``: ``new_world_terrain._identity``.
    * ``exclude=("identity",)``: ``new_world_river_scene._identity``; with ``allow_nan=True``
      ``new_world_native_water._identity``.
    * ``exclude=("identity",), exclude_suffixes=("_path",), recursive=True``: ``coastal_detail_product.identity``.
    * ``exclude=()``: ``coastal_marine_product.identity``, ``coastal_archipelago_product.identity``,
      ``hybrid_river_graph.identity`` (with ``allow_nan`` True / True / False respectively).
    """

    drop = tuple(exclude)
    suffixes = tuple(exclude_suffixes)

    def keep(key):
        return key not in drop and not (suffixes and key.endswith(suffixes))

    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if keep(k)}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    if not drop and not suffixes:
        filtered = record
    else:
        filtered = (
            clean(record)
            if recursive
            else {k: v for k, v in record.items() if keep(k)}
        )

    return json_sha256(filtered, allow_nan=allow_nan)


def identity(arrays, metadata):
    """Bundle identity: compact JSON of ``{"metadata", "arrays": {name: array_sha256}}``.

    Home of ``artifacts.bundles.identity`` and of the ``identity`` that
    ``mountain_source_adapter`` re-exported to the rest of the repository (one function, one name).
    """

    record = {
        "metadata": metadata,
        "arrays": {key: array_sha256(value) for key, value in sorted(arrays.items())},
    }
    return json_sha256(record)


def hash_seed(text, *, nbytes=8, byteorder="big", encoding="utf-8"):
    """``int.from_bytes(sha256(text)[:nbytes], byteorder)``.

    Building block of the string-formula seeds below.  Direct legacy equivalents (the caller builds ``text``):
    ``complete_delta.purpose_seed`` / ``metric_natural_construction.derived_seed``
    (``f"{ws}:{purpose}"``, ``nbytes=4, byteorder="little", encoding="ascii"``),
    ``tectonic_evolution._purpose_seed`` (``f"{ws}:tectonic:{purpose}"``, 8 little),
    ``world_mountain_belts._seed`` (``f"{ws}:world-mountain-belts:{purpose}"``, 8 big),
    ``procedural_mountain_erosion._seed`` (``f"{ALGORITHM_ID}:{ws}:{purpose}"``, 8 little, ascii),
    ``large_delta_suite_network`` corridor seed (``"20261020:delta-suite/corridor/<case>"``, 8 little),
    ``new_world_hydrology._id`` (``f"{VERSION}:{identity}:{kind}:{x}:{z}"``, 8 big, then ``or 1``).
    """

    return int.from_bytes(hashlib.sha256(text.encode(encoding)).digest()[:nbytes], byteorder)


def _check_uint64(world_seed):
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, (int, np.integer)):
        raise ValueError("world_seed must be an integer")
    if not 0 <= int(world_seed) < 2**64:
        raise ValueError("world_seed must fit an unsigned 64-bit integer")
    return int(world_seed)


def _check_purpose(purpose):
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("purpose must be a nonempty string")
    return purpose


def seed_mountains_v1(world_seed, purpose):
    """uint64 = sha256(``terragenesis-procedural-mountains-v1|ws|purpose``)[:8] big-endian.

    Equals ``terrain_pipeline.world_seed.derive_subseed`` (also accepts NumPy integers).
    """

    world_seed = _check_uint64(world_seed)
    return hash_seed(f"terragenesis-procedural-mountains-v1|{world_seed}|{_check_purpose(purpose)}")


_OVERVIEW_NAMESPACE = "terragenesis-fictional-world-overview-v1"


def seed_overview_v1(world_seed, purpose, index=0):
    """uint64 = sha256(``<overview ns>|ws|purpose|index``)[:8] big-endian; purpose ``[a-z][a-z0-9_]{0,48}``.

    Equals ``fictional_world_overview.derive_subseed`` (it raises ``OverviewError``; this raises ``ValueError``).
    """

    import re

    world_seed = _check_uint64(world_seed)
    if not isinstance(purpose, str) or re.match(r"[a-z][a-z0-9_]{0,48}\Z", purpose) is None:
        raise ValueError(f"purpose must be a lowercase stable name, got {purpose!r}")
    if isinstance(index, (bool, np.bool_)) or not isinstance(index, (int, np.integer)) or int(index) < 0:
        raise ValueError("seed index must be a non-negative integer")
    return hash_seed(
        "%s|%d|%s|%d" % (_OVERVIEW_NAMESPACE, world_seed, purpose, int(index)), encoding="ascii"
    )


LITHOLOGY_PURPOSES = ("class_primary", "class_secondary", "rock_medium", "patch_high")


def seed_lithology_v1(world_seed, purpose):
    """uint64 = sha256(``terragenesis-lithology-v1|ws|purpose``)[:8] big-endian; purpose in ``LITHOLOGY_PURPOSES``.

    Equals ``td_lithology_field.derive_subseed``.
    """

    world_seed = _check_uint64(world_seed)
    if purpose not in LITHOLOGY_PURPOSES:
        raise ValueError("unknown seed purpose: " + repr(purpose))
    return hash_seed("terragenesis-lithology-v1|" + str(world_seed) + "|" + purpose, encoding="ascii")


_WATER_LAYOUT_NAMESPACE = b"terragenesis-world-water-layout-v1"


def seed_water_layout_v1(world_seed, layout_id, purpose, region_i=0, region_j=0):
    """uint64 from a NUL-separated byte payload with signed big-endian int64 region coordinates.

    Equals ``world_water_layout.derive_subseed`` (it raises ``LayoutError``; this raises ``ValueError``).
    """

    world_seed = _check_uint64(world_seed)
    for text, name in ((layout_id, "layout_id"), (purpose, "purpose")):
        if not isinstance(text, str) or not text or "\x00" in text:
            raise ValueError("%s must be a non-empty NUL-free string" % name)
    for value, name in ((region_i, "region_i"), (region_j, "region_j")):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError("%s must be an integer" % name)
        if not -(2**63) <= int(value) < 2**63:
            raise ValueError("%s must fit int64" % name)
    payload = b"".join(
        (
            _WATER_LAYOUT_NAMESPACE,
            b"\x00",
            str(world_seed).encode("ascii"),
            b"\x00",
            layout_id.encode("utf-8"),
            b"\x00",
            purpose.encode("ascii"),
            b"\x00",
            int(region_i).to_bytes(8, "big", signed=True),
            int(region_j).to_bytes(8, "big", signed=True),
        )
    )
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def seed_noise_json_v1(world_seed, purpose):
    """uint32 = sha256(compact JSON ``["terragenesis-world-noise-v1", ws, purpose]``)[:4] big-endian.

    Equals ``surface_rivers.world_channel_graph.derive_noise_seed``.  NOT equal to
    ``seed_noise_json_spaced_v1`` (JSON separators differ).
    """

    if type(world_seed) is not int or not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("integer world seed and stable purpose required")
    payload = json.dumps(
        ["terragenesis-world-noise-v1", world_seed, purpose], ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def seed_noise_json_spaced_v1(world_seed, purpose):
    """uint32 from ``json.dumps([ns, int(ws), str(purpose)], sort_keys=True)`` (default ``", "`` separators).

    Equals ``surface_rivers.metric_cross_region.derive_sub_seed`` (no validation, as there).
    """

    payload = json.dumps(
        ["terragenesis-world-noise-v1", int(world_seed), str(purpose)], sort_keys=True
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:4], "big")


def seed_ledger_53bit_v1(world_seed, purpose):
    """53-bit seed: sha256(``terragenesis/world-seed-subseed-v1|world_seed=%d|purpose=%s``)[:8] big & (2**53-1).

    Formula of ``native_30m_hydrology_ledger.purpose_subseeds`` for one purpose (validation here is the generic
    uint64 / nonempty-str check, not that module's ``_world_seed``/``_purpose``).
    """

    world_seed = _check_uint64(world_seed)
    payload = "terragenesis/world-seed-subseed-v1|world_seed=%d|purpose=%s" % (
        world_seed,
        _check_purpose(purpose),
    )
    return hash_seed(payload, encoding="ascii") & 9007199254740991


def seed_pipe_v1(world_seed, purpose, *extra):
    """uint64 = sha256(``"|".join([str(ws), purpose, *map(repr, extra)])``)[:8] big-endian.

    Equals ``delta_network_site.derive_seed`` when ``world_seed=WORLD_SEED_LEGACY_20261020`` (that module fixes the seed).
    """

    text = "|".join([str(world_seed), purpose] + [repr(e) for e in extra])
    return hash_seed(text)


SEED_SCHEMES = {
    "mountains-v1": seed_mountains_v1,
    "overview-v1": seed_overview_v1,
    "lithology-v1": seed_lithology_v1,
    "water-layout-v1": seed_water_layout_v1,
    "noise-json-v1": seed_noise_json_v1,
    "noise-json-spaced-v1": seed_noise_json_spaced_v1,
    "ledger-53bit-v1": seed_ledger_53bit_v1,
    "pipe-v1": seed_pipe_v1,
}


def derive_subseed(world_seed, purpose, scheme="mountains-v1", **options):
    """Dispatch to a named seed scheme.  ``scheme`` is part of the seed's recorded derivation.

    ``options`` are the scheme's extra keyword arguments (``index`` for ``overview-v1``, ``region_i``/``region_j``
    for ``water-layout-v1``).  ``water-layout-v1`` takes ``layout_id`` as an option.
    """

    if scheme not in SEED_SCHEMES:
        raise ValueError("unknown seed scheme: " + repr(scheme))
    if scheme == "water-layout-v1":
        layout_id = options.pop("layout_id")
        return seed_water_layout_v1(world_seed, layout_id, purpose, **options)
    return SEED_SCHEMES[scheme](world_seed, purpose, **options)


def mix64(value):
    """SplitMix64-style finalizer on ``np.uint64`` scalars/arrays (``irregular_drainage._mix64``)."""

    value = value ^ (value >> np.uint64(30))
    value = value * np.uint64(13787848793156543929)
    value = value ^ (value >> np.uint64(27))
    value = value * np.uint64(10723151780598845931)
    return value ^ (value >> np.uint64(31))


def frame_axes(alpha_deg):
    """Unit vectors ``(eu, ev)`` of the local frame: ``eu=(cos a, sin a)``, ``ev=(sin a, -cos a)`` in (X, Z)."""

    a = math.radians(alpha_deg)
    return (
        np.array([math.cos(a), math.sin(a)]),
        np.array([math.sin(a), -math.cos(a)]),
    )


def local_to_world(anchor_xz, alpha_deg, u, v):
    """``delta_network_site.local_to_world`` with ``anchor_xz=spec.anchor_world_m``, ``alpha_deg=spec.alpha_deg``."""

    eu, ev = frame_axes(alpha_deg)
    ax, az = anchor_xz
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    return (
        ax + u * eu[0] + v * ev[0],
        az + u * eu[1] + v * ev[1],
    )


def world_to_local(anchor_xz, alpha_deg, x, z):
    """``delta_network_site.world_to_local`` (inverse of ``local_to_world``)."""

    eu, ev = frame_axes(alpha_deg)
    ax, az = anchor_xz
    dx = np.asarray(x, float) - ax
    dz = np.asarray(z, float) - az
    return (
        dx * eu[0] + dz * eu[1],
        dx * ev[0] + dz * ev[1],
    )


def world_to_cell(xz, origin, spacing, shape):
    """Nearest cell ``(row, col)`` of metric point ``xz=(x, z)`` on a grid whose cell *centre* ``[0, 0]`` is ``origin``.

    ``coastal_delta_routes.world_to_cell``; raises ``ValueError`` outside the grid.
    """

    col, row = np.floor((np.asarray(xz) - origin) / spacing + 0.5).astype(int)
    if not (0 <= row < shape[0] and 0 <= col < shape[1]):
        raise ValueError("point outside grid")
    return int(row), int(col)


def load_npy_readonly(path):
    """``np.load(path, mmap_mode='r', allow_pickle=False)``: the ``load = lambda p: ...`` copies.

    Includes the ``new_world_native_network_v4`` spelling that omitted ``allow_pickle=False`` (NumPy's
    default is also False, so results are identical).
    """

    return np.load(path, mmap_mode="r", allow_pickle=False)


def load_npy_member(directory, name):
    """``load_npy_readonly(directory / (name + ".npy"))`` (``new_world_native_width``, ``new_world_game_hydrology``)."""

    return load_npy_readonly(Path(directory) / (name + ".npy"))


def atomic_write(
    path,
    write,
    *,
    binary=True,
    encoding=None,
    newline=None,
    overwrite=True,
    make_parents=True,
    fsync=True,
):
    """Write through ``write(stream)`` into a uniquely named temp file beside ``path`` and publish atomically.

    * temp name from ``tempfile.mkstemp`` (unique per call, safe for concurrent writers; the legacy fixed
      ``manifest.tmp`` / ``<name>.tmp`` could be overwritten by a concurrent writer);
    * data is flushed and ``os.fsync``-ed before publishing (``fsync=False`` only to mimic
      ``world_acceptance_processes.atomic_npz`` / ``hydrology_planning.save_plan``);
    * ``overwrite=True`` publishes with ``os.replace``; ``overwrite=False`` publishes with ``os.link`` so an
      existing destination (also one created concurrently) raises ``FileExistsError`` and is left untouched
      (the ``hydrology_seasonal``, ``lake_routing``, ``td_material_field``, ``artifacts.bundles`` pattern);
    * text mode passes ``encoding``/``newline`` to ``os.fdopen``; ``newline=None`` keeps the platform
      translation of ``\\n`` that ``Path.write_text`` / ``open('w')`` have (CRLF on Windows).
      Use ``newline="\\n"`` or binary mode to match writers that emitted pre-encoded bytes.
    """

    target = Path(path)
    if make_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + target.name + ".", suffix=".tmp", dir=target.parent
    )
    try:
        if binary:
            stream = os.fdopen(descriptor, "wb")
        else:
            stream = os.fdopen(descriptor, "w", encoding=encoding or "utf-8", newline=newline)
        with stream:
            write(stream)
            stream.flush()
            if fsync:
                os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target


def atomic_write_bytes(path, data, **options):
    """Atomic binary write (``artifacts.bundles.publish_bytes`` with ``overwrite=False``;
    ``td_entry_pulse_incremental.atomic_index`` / ``surface_development_readiness`` payloads with ``overwrite=True``)."""

    return atomic_write(path, lambda stream: stream.write(data), binary=True, **options)


def atomic_write_text(path, text, *, encoding="utf-8", newline=None, **options):
    """Atomic text write (the ``manifest.tmp`` / ``with_suffix('.tmp')`` family, without the fixed temp name)."""

    return atomic_write(
        path,
        lambda stream: stream.write(text),
        binary=False,
        encoding=encoding,
        newline=newline,
        **options,
    )


def atomic_write_json(
    path,
    value,
    *,
    indent=2,
    sort_keys=True,
    ensure_ascii=True,
    allow_nan=True,
    trailing_newline=False,
    encoding="utf-8",
    newline=None,
    **options,
):
    """Atomic ``json.dumps`` write.

    * ``new_world_native_*`` manifests: ``indent=2, sort_keys=False, encoding="utf8"``;
    * ``new_world_stage1_checkpoint.atomic_json`` / ``new_world_stage1_flood_phases.atomic_json``:
      ``indent=2, sort_keys=True``;
    * ``world_terrain_store._atomic_json``: ``indent=2, sort_keys=True, allow_nan=False``;
    * ``td_entry_pulse_incremental.atomic_index`` / ``surface_development_readiness`` (pre-encoded bytes, LF):
      ``trailing_newline=True, newline="\\n"`` (add ``ensure_ascii=False`` for the latter).
    """

    text = json.dumps(
        value, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii, allow_nan=allow_nan
    )
    if trailing_newline:
        text += "\n"
    return atomic_write_text(path, text, encoding=encoding, newline=newline, **options)


def atomic_save_npz(path, arrays, *, compressed=True, overwrite=False, **options):
    """Atomic ``np.savez(_compressed)`` of a ``{name: array}`` dict (default: refuse to overwrite, like
    ``hydrology_seasonal``, ``lake_routing``, ``td_material_field``, ``artifacts.bundles.save_bundle``)."""

    saver = np.savez_compressed if compressed else np.savez
    return atomic_write(
        path,
        lambda stream: saver(stream, **arrays),
        binary=True,
        overwrite=overwrite,
        **options,
    )


def readonly(array):
    """Immutable contiguous copy of ``array`` (``artifacts.bundles.readonly``)."""

    value = np.ascontiguousarray(array)
    return np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)


def checked_archive(path, *, expected_sha256, max_bytes=MAX_BYTES, header_validator=None):
    """Check ZIP and NPY headers before allocating any array; never allow pickle."""

    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("external archive SHA256 required")
    if Path(path).stat().st_size > max_bytes:
        raise ValueError("compressed archive byte budget exceeded")
    with open(path, "rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(SHA256_CHUNK_BYTES), b""):
            digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise ValueError("external archive hash mismatch")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            headers = {}
            if (
                not 1 <= len(members) <= 128
                or len({member.filename for member in members}) != len(members)
                or sum(member.file_size for member in members) > max_bytes
            ):
                raise ValueError("archive resource/duplicate member rejection")
            for member in members:
                if not member.filename.endswith(".npy") or "/" in member.filename:
                    raise ValueError("invalid archive member")
                with archive.open(member) as entry:
                    version = np.lib.format.read_magic(entry)
                    if version == (1, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                            entry, max_header_size=4096
                        )
                    elif version == (2, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_2_0(
                            entry, max_header_size=4096
                        )
                    else:
                        raise ValueError("unsupported NPY header")
                    if (
                        dtype.hasobject
                        or fortran
                        or len(shape) > 3
                        or any(size < 0 or size > 8000000 for size in shape)
                        or math.prod(shape) * dtype.itemsize + entry.tell() != member.file_size
                    ):
                        raise ValueError("unsafe NPY shape/dtype/size")
                    headers[member.filename[:-4]] = (shape, dtype)
            if header_validator is not None:
                header_validator(headers)
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            return {key: archive[key].copy() for key in archive.files}


def publish_bytes(path, payload):
    """A hard link is the commit point; a racing existing destination wins (``artifacts.bundles.publish_bytes``).

    Same semantics as :func:`atomic_write_bytes` with ``overwrite=False``.
    """

    return atomic_write_bytes(path, payload, overwrite=False)


def save_bundle(path, result, *, validator):
    """Validate, then publish ``result`` as a compressed NPZ with a JSON manifest member."""

    validator(result)
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    manifest = canonical_json(
        {"metadata": result["metadata"], "identity_sha256": result["identity_sha256"]}
    ).encode("utf-8")
    if len(manifest) > MAX_METADATA:
        raise ValueError("metadata budget exceeded")
    target.parent.mkdir(parents=True, exist_ok=True)
    publish_bytes(target, _bundle_payload(manifest, result["arrays"]))
    return None


def _bundle_payload(manifest, arrays):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, manifest=np.frombuffer(manifest, dtype=np.uint8), **arrays)
    return buffer.getvalue()


def load_bundle(path, *, expected_sha256, validator, max_bytes=MAX_BYTES, header_validator=None):
    """Read a bundle written by :func:`save_bundle`, validate it, and return read-only arrays."""

    arrays = checked_archive(
        path,
        expected_sha256=expected_sha256,
        max_bytes=max_bytes,
        header_validator=header_validator,
    )
    manifest = arrays.pop("manifest", None)
    if (
        manifest is None
        or manifest.dtype != np.uint8
        or manifest.ndim != 1
        or manifest.size > MAX_METADATA
    ):
        raise ValueError("invalid manifest")
    record = strict_json(manifest.tobytes().decode("utf-8"))
    if set(record) != {"metadata", "identity_sha256"}:
        raise ValueError("unexpected manifest keys")
    result = dict(record, arrays=arrays)
    validator(result)
    result["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return result


def make_source(
    height_m,
    *,
    origin_m_xz,
    spacing_m,
    provenance,
    boundary,
    display_mask=None,
    hydrology_mask=None,
    climate=None,
    domain=None,
):
    """Trusted in-process construction, not proof that supplied values came from TD."""

    height = np.asarray(height_m)
    if (
        height.ndim != 2
        or not 1 <= height.size <= SOURCE_MAX_CELLS
        or height.dtype.kind not in "fiu"
        or not np.isfinite(height).all()
    ):
        raise ValueError("invalid bounded real elevation grid")
    arrays = {"height_m": height.astype(np.float64)}
    for key, supplied in (("display_mask", display_mask), ("hydrology_mask", hydrology_mask)):
        arrays[key] = np.ones(height.shape, bool) if supplied is None else np.asarray(supplied)
    if climate is not None:
        arrays["climate"] = np.asarray(climate).astype(np.float64)
    metadata = strict_json(
        canonical_json(
            {
                "schema": SOURCE_SCHEMA,
                "origin_m_xz": origin_m_xz,
                "spacing_m": spacing_m,
                "coordinates": "x east, z south; arrays [z,x]",
                "vertical_datum": "sea_zero_m",
                "provenance": provenance,
                "boundary": boundary,
                "domain": (
                    domain
                    if domain is not None
                    else {
                        "calculation_domain": "finite_window_experiment",
                        "hydrological_closure_certified": False,
                        "closure_evidence_sha256": None,
                        "land_boundary_crossing": "truncated_external_open_boundary",
                    }
                ),
            }
        )
    )
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_source(result)
    result["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return result


def validate_source(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if set(metadata) != {
        "schema",
        "origin_m_xz",
        "spacing_m",
        "coordinates",
        "vertical_datum",
        "provenance",
        "boundary",
        "domain",
    }:
        raise ValueError("unexpected source metadata")
    if (
        metadata["schema"] != SOURCE_SCHEMA
        or metadata["coordinates"] != "x east, z south; arrays [z,x]"
        or metadata["vertical_datum"] != "sea_zero_m"
        or set(arrays) not in (
            {"height_m", "display_mask", "hydrology_mask"},
            {"height_m", "display_mask", "hydrology_mask", "climate"},
        )
    ):
        raise ValueError("source schema mismatch")
    provenance = metadata["provenance"]
    if (
        not isinstance(provenance, dict)
        or provenance.get("artifact_kind") not in SOURCE_KINDS
        or provenance.get("td_inference_run") is not True
        or not isinstance(provenance.get("archive_sha256"), str)
        or len(provenance["archive_sha256"]) != 64
    ):
        raise ValueError("actual TD source required; conditioning_only forbidden")
    origin = metadata["origin_m_xz"]
    spacing = metadata["spacing_m"]
    if (
        not isinstance(origin, list)
        or len(origin) != 2
        or any(type(value) not in (float, int) or not math.isfinite(value) for value in origin)
        or type(spacing) not in (float, int)
        or not math.isfinite(spacing)
        or not 0 < spacing <= 100000
    ):
        raise ValueError("invalid metre grid")
    height = arrays["height_m"]
    if (
        height.ndim != 2
        or height.dtype != np.float64
        or not 1 <= height.size <= SOURCE_MAX_CELLS
        or not np.isfinite(height).all()
    ):
        raise ValueError("invalid saved source height")
    for key in ("display_mask", "hydrology_mask"):
        if (
            arrays[key].shape != height.shape
            or arrays[key].dtype != bool
            or not arrays[key].any()
        ):
            raise ValueError("invalid source domain")
    if (arrays["display_mask"] & ~arrays["hydrology_mask"]).any():
        raise ValueError("display domain outside hydrology domain")
    boundary = metadata["boundary"]
    domain = metadata["domain"]
    if (
        not isinstance(domain, dict)
        or set(domain)
        != {
            "calculation_domain",
            "hydrological_closure_certified",
            "closure_evidence_sha256",
            "land_boundary_crossing",
        }
        or domain["calculation_domain"]
        not in {"complete_contribution_subdomain", "finite_window_experiment"}
        or domain["hydrological_closure_certified"] is not False
        or domain["closure_evidence_sha256"] is not None
        or domain["land_boundary_crossing"] != "truncated_external_open_boundary"
    ):
        raise ValueError("this adapter does not certify a complete hydrological planning domain")
    if (
        not isinstance(boundary, dict)
        or set(boundary) != {"policy", "halo_cells", "upstream_contribution"}
        or boundary["policy"] not in {"explicit", "all_edges_open", "legacy_lowest_edge"}
        or type(boundary["halo_cells"]) is not int
        or not 0 <= boundary["halo_cells"] < min(height.shape)
        or boundary["upstream_contribution"]
        not in {"full_domain", "excluded_finite_experiment", "explicit_forcing"}
    ):
        raise ValueError("explicit boundary/domain declaration required")
    halo = boundary["halo_cells"]
    if halo and (
        arrays["display_mask"][:halo].any()
        or arrays["display_mask"][-halo:].any()
        or arrays["display_mask"][:, :halo].any()
        or arrays["display_mask"][:, -halo:].any()
    ):
        raise ValueError("display mask violates declared halo")
    if (
        "climate" in arrays
        and (
            arrays["climate"].shape != (5,) + height.shape
            or arrays["climate"].dtype != np.float64
            or not np.isfinite(arrays["climate"]).all()
        )
    ):
        raise ValueError("invalid five-channel climate")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("source identity mismatch")
    return True


def load_legacy_source(name, *, boundary_policy="legacy_lowest_edge"):
    from tools.verify_mountain_rainfall import EXPECTED, SOURCE_ROOT, load_source

    if name not in EXPECTED:
        raise ValueError("unknown fixed legacy source")
    checked_archive(
        SOURCE_ROOT / f"{name}.npz",
        expected_sha256=EXPECTED[name]["river"],
        header_validator=_legacy_headers,
    )
    source = load_source(name)
    if not source["raw_available"]:
        raise ValueError("pinned original TD archive required")
    checked_archive(source["raw_path"], expected_sha256=EXPECTED[name]["raw"])
    return make_source(
        source["height_m"],
        origin_m_xz=source["origin_m_xz"],
        spacing_m=source["spacing_m"],
        provenance={
            "artifact_kind": "legacy_td_game_conditioned",
            "td_inference_run": True,
            "name": name,
            "archive_sha256": EXPECTED[name]["river"],
            "raw_sha256": EXPECTED[name]["raw"],
            "provenance_sha256": source["sidecar_sha256"],
            "generation_identity": source["provenance"]["generation_identity"],
            "datum_shift_m": -source["provenance"]["core_sea_elevation_m"],
            "historical_game_height_conditioning": True,
            "limitation": "datum shift only; historical game-conditioned relief is unchanged",
        },
        boundary={
            "policy": boundary_policy,
            "halo_cells": 0,
            "upstream_contribution": "excluded_finite_experiment",
        },
    )


def load_physical_source(path, *, expected_sha256, boundary, display_mask=None):
    arrays = checked_archive(path, expected_sha256=expected_sha256, header_validator=_physical_headers)
    if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("physical TD archive required; conditioning_only rejected")
    raw_meta = arrays["metadata_json"]
    if raw_meta.shape != () or raw_meta.dtype.kind != "U" or raw_meta.nbytes > MAX_METADATA:
        raise ValueError("invalid physical metadata")
    metadata = strict_json(str(raw_meta.item()))
    if metadata.get("artifact_kind") != "terrain_diffusion_output":
        raise ValueError("conditioning_only is not TD output")
    from diffusion.physical_config import PhysicalGenerationConfig

    config = PhysicalGenerationConfig.from_record(metadata["config"])
    if (
        metadata.get("schema") != "physical-generation-v1"
        or metadata["native_resolution_m"] != config.native_resolution_m
    ):
        raise ValueError("physical source units/schema mismatch")
    base = {
        key: metadata[key]
        for key in ("schema", "config", "source_sha256", "elevation_units", "coordinates")
    }
    digest = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    generation = dict(
        base,
        **{
            key: metadata[key]
            for key in ("conditioning_identity", "model", "model_config_sha256", "upstream")
        },
    )
    if (
        digest != metadata["conditioning_identity"]
        or hashlib.sha256(json.dumps(generation, sort_keys=True).encode()).hexdigest()
        != metadata["identity"]
    ):
        raise ValueError("physical generation identity mismatch")
    origin = metadata["native_origin"]
    if (
        not isinstance(origin, list)
        or len(origin) != 2
        or any(type(value) is not int for value in origin)
        or metadata["shape"] != list(arrays["elevation_m"].shape)
        or not isinstance(metadata["seed"], str)
        or not metadata["seed"].isdigit()
        or not 0 <= int(metadata["seed"]) < 2**64
        or metadata["elevation_units"] != "m"
    ):
        raise ValueError("physical window/seed mismatch")
    return make_source(
        arrays["elevation_m"],
        climate=arrays["climate"],
        origin_m_xz=[value * config.native_resolution_m for value in origin],
        spacing_m=config.native_resolution_m,
        provenance={
            "artifact_kind": "terrain_diffusion_output",
            "td_inference_run": True,
            "archive_sha256": expected_sha256,
            "generation_metadata": metadata,
            "historical_game_height_conditioning": False,
        },
        boundary=boundary,
        display_mask=display_mask,
    )


def save_source(path, result):
    save_bundle(path, result, validator=validate_source)
    return None


def _source_headers(headers):
    if set(headers) not in (
        {"height_m", "display_mask", "hydrology_mask", "manifest"},
        {"height_m", "display_mask", "hydrology_mask", "climate", "manifest"},
    ):
        raise ValueError("unexpected source headers")
    shape, dtype = headers["height_m"]
    if len(shape) != 2 or not 1 <= math.prod(shape) <= SOURCE_MAX_CELLS or dtype != np.float64:
        raise ValueError("source grid allocation budget/type exceeded")
    for key in ("display_mask", "hydrology_mask"):
        if headers[key] != (shape, np.dtype(bool)):
            raise ValueError("source mask header mismatch")
    if "climate" in headers and headers["climate"] != ((5,) + shape, np.dtype("float64")):
        raise ValueError("source climate header mismatch")
    manifest_shape, manifest_dtype = headers["manifest"]
    if (
        len(manifest_shape) != 1
        or not 1 <= manifest_shape[0] <= MAX_METADATA
        or manifest_dtype != np.uint8
    ):
        raise ValueError("source manifest header mismatch")
    return None


def _legacy_headers(headers):
    shape, dtype = headers.get("input_height", ((), np.dtype("O")))
    if len(shape) != 2 or not 1 <= math.prod(shape) <= SOURCE_MAX_CELLS or dtype.kind not in "fiu":
        raise ValueError("legacy input shape/type exceeds adapter budget")
    for key in ("receiver", "outlet_mask", "flowline_mask"):
        if key not in headers or headers[key][0] != shape:
            raise ValueError("legacy grid header mismatch")
    if headers["receiver"][1].kind not in "iu" or any(
        headers[key][1] != bool for key in ("outlet_mask", "flowline_mask")
    ):
        raise ValueError("legacy topology header type mismatch")
    return None


def _physical_headers(headers):
    if set(headers) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("actual TD archive required")
    shape, dtype = headers["elevation_m"]
    if (
        len(shape) != 2
        or not 1 <= math.prod(shape) <= SOURCE_MAX_CELLS
        or dtype not in (np.dtype("float32"), np.dtype("float64"))
    ):
        raise ValueError("physical elevation exceeds adapter shape/type budget")
    if headers["climate"][0] != (5,) + shape or headers["climate"][1] not in (
        np.dtype("float32"),
        np.dtype("float64"),
    ):
        raise ValueError("physical climate header mismatch")
    if (
        headers["metadata_json"][0] != ()
        or headers["metadata_json"][1].kind != "U"
        or headers["metadata_json"][1].itemsize > MAX_METADATA
    ):
        raise ValueError("physical metadata header mismatch")
    return None


def load_source_bundle(path, *, expected_sha256, expected_identity, trusted_source=None):
    result = load_bundle(
        path, expected_sha256=expected_sha256, validator=validate_source, header_validator=_source_headers
    )
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external source identity mismatch")
    if trusted_source is not None:
        validate_source(trusted_source)
        if result["metadata"] != trusted_source["metadata"] or set(result["arrays"]) != set(
            trusted_source["arrays"]
        ):
            raise ValueError("trusted original payload metadata mismatch")
        for key in result["arrays"]:
            if array_sha256(result["arrays"][key]) != array_sha256(trusted_source["arrays"][key]):
                raise ValueError("trusted original source payload mismatch")
    return result


def _contract_number(value, label, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(label + " must be numeric")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(label + " must be finite" + (" positive" if positive else ""))
    return None


def _contract_mask(values, shape, label):
    if not isinstance(values, np.ndarray) or values.dtype != bool or values.shape != shape:
        raise ValueError(label + " must be a matching boolean array")
    return readonly(values)


@dataclass(frozen=True)
class TerrainGrid:
    elevation_m: np.ndarray
    valid_mask: np.ndarray
    x0_m: float
    z0_m: float
    dx_m: float
    dz_m: float
    source_kind: str
    source_id: str
    source_sha256: str
    crs: str | None = None
    vertical_datum: str | None = None
    nodata_semantics: str = "unknown_is_not_traced"
    model_version: str | None = None
    generation_seed: int | None = None
    condition_summary: str | None = None
    source_path: str | None = None

    def __post_init__(self):
        height = self.elevation_m
        if (
            not isinstance(height, np.ndarray)
            or height.dtype != np.float64
            or height.ndim != 2
            or not 1 <= height.size <= GRID_MAX_CELLS
        ):
            raise ValueError("bounded float64 [z,x] elevation required")
        valid = _contract_mask(self.valid_mask, height.shape, "valid_mask")
        if not valid.any() or not np.isfinite(height[valid]).all():
            raise ValueError("nonempty finite valid terrain required")
        for name in ("x0_m", "z0_m", "dx_m", "dz_m"):
            _contract_number(getattr(self, name), name, name in ("dx_m", "dz_m"))
            object.__setattr__(self, name, float(getattr(self, name)))
        if not math.isfinite(self.dx_m * self.dz_m) or self.dx_m * self.dz_m <= 0.0:
            raise ValueError("cell area overflows or underflows")
        if not math.isfinite(self.x0_m + height.shape[1] * self.dx_m) or not math.isfinite(
            self.z0_m + height.shape[0] * self.dz_m
        ):
            raise ValueError("metric grid extent overflows")
        require_sha256_hex_lowercase(self.source_sha256)
        if self.source_kind not in (
            "generated_terrain",
            "conditioned_terrain",
            "observed_dem",
            "diagnostic_dem_proxy",
        ):
            raise ValueError("unrecognized source_kind")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id required")
        for name in ("crs", "vertical_datum", "model_version", "condition_summary", "source_path"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("optional provenance must be nonempty text: " + name)
        if self.generation_seed is not None and (
            type(self.generation_seed) is not int or self.generation_seed < 0
        ):
            raise ValueError("generation_seed must be a nonnegative integer or None")
        if self.nodata_semantics != "unknown_is_not_traced":
            raise ValueError("unsupported nodata_semantics")
        object.__setattr__(self, "elevation_m", readonly(np.where(valid, height, 0.0)))
        object.__setattr__(self, "valid_mask", valid)

    @property
    def cell_area_m2(self):
        return float(self.dx_m * self.dz_m)

    def world_xz(self, cell_id):
        if type(cell_id) is not int or not 0 <= cell_id < self.elevation_m.size:
            raise ValueError("cell_id outside grid")
        row, column = divmod(cell_id, self.elevation_m.shape[1])
        return (float(self.x0_m + column * self.dx_m), float(self.z0_m + row * self.dz_m))

    @property
    def provenance_status(self):
        complete = bool(self.source_path and self.crs and self.vertical_datum)
        if self.source_kind in ("generated_terrain", "conditioned_terrain"):
            complete &= (
                self.model_version is not None
                and self.generation_seed is not None
                and self.condition_summary is not None
            )
        return "registered_provenance" if complete else "pending_provenance"

    def metadata(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name not in ("elevation_m", "valid_mask")
        } | {
            "coordinates": "X east, Y up, Z south; arrays [z,x]; cell_id=z*nx+x",
            "provenance_status": self.provenance_status,
            "hydraulic_certification_allowed": False,
        }

    @property
    def identity_sha256(self):
        return identity(
            {"elevation_m": self.elevation_m, "valid_mask": self.valid_mask}, self.metadata()
        )


@dataclass(frozen=True)
class BoundaryGrid:
    kind: np.ndarray
    allow_inflow: np.ndarray
    source_id: str
    source_sha256: str
    stage_m: np.ndarray | None = None
    discharge_m3_s: np.ndarray | None = None

    def __post_init__(self):
        if (
            not isinstance(self.kind, np.ndarray)
            or self.kind.ndim != 2
            or not 1 <= self.kind.size <= GRID_MAX_CELLS
        ):
            raise ValueError("bounded 2D boundary kind array required")
        if not np.isin(self.kind, BOUNDARY_KINDS).all():
            raise ValueError("invalid boundary kind")
        inflow = _contract_mask(self.allow_inflow, self.kind.shape, "allow_inflow")
        prescribed = np.isin(self.kind, ("prescribed_stage", "prescribed_discharge"))
        if np.any(inflow & ~prescribed):
            raise ValueError("only prescribed boundaries may allow inflow")
        require_sha256_hex_lowercase(self.source_sha256)
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("boundary source_id required")
        for key, kind in (("stage_m", "prescribed_stage"), ("discharge_m3_s", "prescribed_discharge")):
            value = getattr(self, key)
            selected = self.kind == kind
            if value is None:
                if selected.any():
                    raise ValueError(key + " required for prescribed boundary")
                continue
            if (
                not isinstance(value, np.ndarray)
                or value.dtype != np.float64
                or value.shape != self.kind.shape
                or not np.isfinite(value).all()
            ):
                raise ValueError(key + " must be matching finite float64")
            if np.any(value[~selected] != 0.0):
                raise ValueError(key + " must be zero outside its boundary kind")
            if key == "discharge_m3_s" and np.any((value < 0.0) & ~inflow):
                raise ValueError("negative prescribed outflow requires allow_inflow")
            object.__setattr__(self, key, readonly(value))
        object.__setattr__(self, "kind", readonly(self.kind.astype("U24")))
        object.__setattr__(self, "allow_inflow", inflow)

    @classmethod
    def from_outlet_mask(cls, terrain, outlet_mask, *, source_id, source_sha256):
        mask = _contract_mask(outlet_mask, terrain.valid_mask.shape, "outlet_mask")
        perimeter = np.zeros(mask.shape, bool)
        perimeter[[0, -1], :] = True
        perimeter[:, [0, -1]] = True
        if np.any(mask & (~terrain.valid_mask | ~perimeter)):
            raise ValueError("outlet_mask must select valid perimeter cells")
        kind = np.full(mask.shape, "interior", dtype="U24")
        kind[perimeter] = "closed_wall"
        kind[~terrain.valid_mask] = "unknown_boundary"
        kind[mask] = "open_outflow"
        return cls(kind, np.zeros(mask.shape, bool), source_id, source_sha256)

    @property
    def outlet_mask(self):
        return readonly(np.isin(self.kind, ("open_outflow", "prescribed_stage", "prescribed_discharge")))

    @property
    def identity_sha256(self):
        arrays = {"kind": self.kind, "allow_inflow": self.allow_inflow}
        for name in ("stage_m", "discharge_m3_s"):
            if getattr(self, name) is not None:
                arrays[name] = getattr(self, name)
        return identity(
            arrays,
            {
                "source_id": self.source_id,
                "source_sha256": self.source_sha256,
                "positive_direction": "out_of_domain",
            },
        )


@dataclass(frozen=True)
class RainfallForcing:
    time_seconds: np.ndarray
    rain_mm_h: np.ndarray
    source_id: str
    source_sha256: str
    temporal_semantics: str = "interval_average"
    spatial_semantics: str = "cell_average"
    missing_policy: str = "reject"

    def __post_init__(self):
        times, rain = self.time_seconds, self.rain_mm_h
        if (
            not isinstance(times, np.ndarray)
            or times.dtype != np.float64
            or times.ndim != 1
            or not 2 <= times.size <= 100001
        ):
            raise ValueError("float64 interval endpoints required")
        if not np.isfinite(times).all() or times[0] < 0.0 or np.any(np.diff(times) <= 0.0):
            raise ValueError("strictly increasing nonnegative physical times required")
        if (
            not isinstance(rain, np.ndarray)
            or rain.dtype != np.float64
            or rain.ndim != 3
            or rain.shape[0] != times.size - 1
            or not 1 <= rain.size <= MAX_FORCING_ENTRIES
            or rain.shape[1] * rain.shape[2] > GRID_MAX_CELLS
        ):
            raise ValueError("bounded float64 rain [T,z,x] matching T+1 endpoints required")
        if not np.isfinite(rain).all() or np.any(rain < 0.0) or np.any(rain > 1000000.0):
            raise ValueError("finite bounded nonnegative rain required")
        if (self.temporal_semantics, self.spatial_semantics, self.missing_policy) != (
            "interval_average",
            "cell_average",
            "reject",
        ):
            raise ValueError("forcing must declare interval_average/cell_average/reject")
        require_sha256_hex_lowercase(self.source_sha256)
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("forcing source_id required")
        object.__setattr__(self, "time_seconds", readonly(times))
        object.__setattr__(self, "rain_mm_h", readonly(rain))

    @property
    def interval_seconds(self):
        return readonly(np.diff(self.time_seconds))

    @property
    def rainfall_depth_mm(self):
        return readonly(self.rain_mm_h * (self.interval_seconds[:, None, None] / 3600.0))

    @property
    def identity_sha256(self):
        return identity(
            {"time_seconds": self.time_seconds, "rain_mm_h": self.rain_mm_h},
            {
                name: getattr(self, name)
                for name in self.__dataclass_fields__
                if name not in ("time_seconds", "rain_mm_h")
            },
        )


@dataclass(frozen=True)
class RoutingGraph:
    receiver: np.ndarray
    order_downstream_first: np.ndarray
    valid_mask: np.ndarray
    edge_length_m: np.ndarray
    edge_slope: np.ndarray
    outlet_kind: np.ndarray
    lake_id: np.ndarray
    terrain_identity_sha256: str
    boundary_identity_sha256: str
    policy: str = "original_bed_irregular_plateau_bfs_v2"

    def __post_init__(self):
        from terrain_pipeline.drainage import segments_clear

        valid = self.valid_mask
        if (
            not isinstance(valid, np.ndarray)
            or valid.dtype != bool
            or valid.ndim != 2
            or not 1 <= valid.size <= GRID_MAX_CELLS
            or not valid.any()
        ):
            raise ValueError("bounded nonempty valid graph mask required")
        count = valid.size
        for name in ("receiver", "lake_id"):
            value = getattr(self, name)
            if (
                not isinstance(value, np.ndarray)
                or value.dtype != np.int64
                or value.shape != (count,)
            ):
                raise ValueError(name + " must be int64 [N]")
        receiver = self.receiver
        order = self.order_downstream_first
        cells = np.flatnonzero(valid)
        if (
            not isinstance(order, np.ndarray)
            or order.dtype != np.int64
            or not np.array_equal(np.sort(order), cells)
        ):
            raise ValueError("downstream order must be a permutation of valid cells")
        if (
            np.any(receiver < -1)
            or np.any(receiver >= count)
            or np.any(receiver[~valid.ravel()] != -1)
        ):
            raise ValueError("receiver outside domain")
        donors = np.flatnonzero(receiver >= 0)
        if np.any(~valid.ravel()[receiver[donors]]):
            raise ValueError("receiver crosses unknown terrain")
        targets = receiver[donors]
        if np.any(donors == targets):
            raise ValueError("routing edges cannot have self receivers")
        if not segments_clear(donors, targets, valid).all():
            raise ValueError("receiver crosses unknown corner or control cell")
        rank = np.full(count, -1, np.int64)
        rank[order] = np.arange(len(order))
        if np.any(rank[receiver[donors]] >= rank[donors]):
            raise ValueError("cycle or invalid downstream-first order")
        for name in ("edge_length_m", "edge_slope"):
            value = getattr(self, name)
            if (
                not isinstance(value, np.ndarray)
                or value.dtype != np.float64
                or value.shape != (count,)
                or not np.isfinite(value).all()
            ):
                raise ValueError(name + " must be finite float64 [N]")
            if np.any(value < 0.0) or np.any(value[receiver < 0] != 0.0):
                raise ValueError(name + " has negative or terminal values")
        if np.any(self.edge_length_m[donors] <= 0.0):
            raise ValueError("positive edge lengths required")
        kinds = self.outlet_kind
        terminal_kinds = (
            "open_outflow",
            "prescribed_stage",
            "prescribed_discharge",
            "unknown_boundary",
            "lake_preserved",
        )
        if (
            not isinstance(kinds, np.ndarray)
            or kinds.shape != (count,)
            or not np.isin(kinds, ("interior", "inactive") + terminal_kinds).all()
        ):
            raise ValueError("invalid graph outlet_kind")
        terminal = valid.ravel() & (receiver < 0)
        if not (
            np.isin(kinds[terminal], terminal_kinds).all()
            and not np.any(kinds[donors] != "interior")
            and not np.any(kinds[~valid.ravel()] != "inactive")
        ):
            raise ValueError("terminal and active edge kinds differ")
        if np.any(self.lake_id < -1) or np.any(self.lake_id[~valid.ravel()] != -1):
            raise ValueError("invalid lake_id")
        if np.any(self.lake_id[terminal & (kinds == "lake_preserved")] < 0):
            raise ValueError("lake terminal ID required")
        require_sha256_hex_lowercase(self.terrain_identity_sha256)
        require_sha256_hex_lowercase(self.boundary_identity_sha256)
        if not isinstance(self.policy, str) or not self.policy.strip():
            raise ValueError("routing policy required")
        for name in (
            "receiver",
            "order_downstream_first",
            "valid_mask",
            "edge_length_m",
            "edge_slope",
            "outlet_kind",
            "lake_id",
        ):
            object.__setattr__(self, name, readonly(getattr(self, name)))

    @property
    def donors(self):
        result = [[] for _ in range(self.receiver.size)]
        for cell in np.flatnonzero(self.receiver >= 0):
            result[int(self.receiver[cell])].append(int(cell))
        return tuple(tuple(values) for values in result)

    @property
    def topology_status(self):
        return "diagnostic_topology"

    @property
    def identity_sha256(self):
        return identity(
            {
                name: getattr(self, name)
                for name in (
                    "receiver",
                    "order_downstream_first",
                    "valid_mask",
                    "edge_length_m",
                    "edge_slope",
                    "outlet_kind",
                    "lake_id",
                )
            },
            {
                "terrain_identity_sha256": self.terrain_identity_sha256,
                "boundary_identity_sha256": self.boundary_identity_sha256,
                "policy": self.policy,
                "status": self.topology_status,
            },
        )


_ARTIFACT_ARRAY_FILE = "arrays.npz"
_ARTIFACT_MANIFEST_FILE = "manifest.json"
_ARTIFACT_TOP_KEYS = {
    "arrays",
    "content_id",
    "displacement_type",
    "format_version",
    "grid",
    "identity",
    "kind",
    "reference_surface_id",
    "source_artifact_id",
}
_ARTIFACT_GRID_KEYS = {
    "origin_x_m",
    "origin_z_m",
    "spacing_x_m",
    "spacing_z_m",
    "shape_zx",
    "vertical_datum",
    "sea_level_elevation_m",
}
_ARTIFACT_IDENTITY_KEYS = {"algorithm", "algorithm_version", "parameters", "seed", "backend", "sha256"}
_ARTIFACT_ARRAY_KEYS = {
    "reference_elevation_m",
    "displacement_m",
    "surface_elevation_m",
    "wet_mask",
    "discharge_m3_per_s",
}
_WATER_KEYS = {"surface_elevation_m", "wet_mask", "discharge_m3_per_s"}


def _artifact_pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _artifact_reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _artifact_exact_keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {name} fields")
    return None


def save_artifact(artifact, path):
    """Write ``artifact`` as a temporary directory, verify it by reading it back, then rename it into place."""

    from terrain_pipeline.artifacts.contracts import TerrainArtifact, canonical_json

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
        np.savez(temporary / _ARTIFACT_ARRAY_FILE, **arrays)
        manifest = {**artifact.content_record(), **{"content_id": artifact.content_id}}
        (temporary / _ARTIFACT_MANIFEST_FILE).write_text(canonical_json(manifest), encoding="utf-8")
        load_artifact(temporary)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_artifact(path):
    """Read and fully validate an artifact directory written by :func:`save_artifact`."""

    from terrain_pipeline.artifacts.contracts import (
        FORMAT_VERSION,
        ArtifactIdentity,
        SurfaceWater,
        TerrainArtifact,
    )

    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    if {entry.name for entry in directory.iterdir()} != {
        _ARTIFACT_MANIFEST_FILE,
        _ARTIFACT_ARRAY_FILE,
    }:
        raise ValueError("artifact directory must contain only manifest.json and arrays.npz")
    for name in (_ARTIFACT_MANIFEST_FILE, _ARTIFACT_ARRAY_FILE):
        if not (directory / name).is_file() or (directory / name).is_symlink():
            raise ValueError("artifact files must be regular files")
    manifest = json.loads(
        (directory / _ARTIFACT_MANIFEST_FILE).read_text(encoding="utf-8"),
        object_pairs_hook=_artifact_pairs_without_duplicates,
        parse_constant=_artifact_reject_constant,
    )
    _artifact_exact_keys(manifest, _ARTIFACT_TOP_KEYS, "manifest")
    if type(manifest["format_version"]) is not int or manifest["format_version"] != FORMAT_VERSION:
        raise ValueError("unsupported artifact format")
    grid = manifest["grid"]
    _artifact_exact_keys(grid, _ARTIFACT_GRID_KEYS, "grid")
    shape = grid["shape_zx"]
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(type(size) is not int or size <= 0 for size in shape)
    ):
        raise ValueError("invalid grid shape")
    identity_data = manifest["identity"]
    _artifact_exact_keys(identity_data, _ARTIFACT_IDENTITY_KEYS, "identity")
    identity_record = ArtifactIdentity(
        **{key: identity_data[key] for key in _ARTIFACT_IDENTITY_KEYS - {"sha256"}}
    )
    if identity_record.sha256 != identity_data["sha256"]:
        raise ValueError("algorithm identity mismatch")
    array_hashes = manifest["arrays"]
    if (
        not isinstance(array_hashes, dict)
        or not set(array_hashes).issubset(_ARTIFACT_ARRAY_KEYS)
        or "reference_elevation_m" not in array_hashes
    ):
        raise ValueError("invalid array fields")
    if manifest["displacement_type"] == "none":
        expected = {"reference_elevation_m"}
    else:
        expected = {"reference_elevation_m", "displacement_m"}
    if set(array_hashes) & _WATER_KEYS:
        expected |= _WATER_KEYS
    if set(array_hashes) != expected or any(
        not isinstance(value, str) or len(value) != 64 for value in array_hashes.values()
    ):
        raise ValueError("incomplete array declarations")
    with np.load(directory / _ARTIFACT_ARRAY_FILE, allow_pickle=False) as archive:
        if len(archive.files) != len(expected) or set(archive.files) != expected:
            raise ValueError("array payload differs from manifest")
        arrays = {name: archive[name] for name in expected}
        for name, value in arrays.items():
            expected_dtype = np.dtype(bool) if name == "wet_mask" else np.dtype("<f8")
            if value.dtype != expected_dtype:
                raise ValueError(f"invalid array dtype: {name}")
    if _WATER_KEYS <= expected:
        water = SurfaceWater(**{name: arrays[name] for name in _WATER_KEYS})
    else:
        water = None
    artifact = TerrainArtifact(
        manifest["kind"],
        identity_record,
        arrays["reference_elevation_m"],
        grid["origin_x_m"],
        grid["origin_z_m"],
        grid["spacing_x_m"],
        grid["spacing_z_m"],
        grid["vertical_datum"],
        grid["sea_level_elevation_m"],
        manifest["displacement_type"],
        arrays.get("displacement_m"),
        manifest["reference_surface_id"],
        manifest["source_artifact_id"],
        water=water,
    )
    if artifact.content_id != manifest["content_id"] or artifact.content_record() != {
        key: manifest[key] for key in _ARTIFACT_TOP_KEYS - {"content_id"}
    }:
        raise ValueError("artifact content mismatch")
    return artifact


def published_algorithm_hashes(family, *, registry_path=None):
    """Return hashes recorded in published products, never hashes of live files."""
    import json
    from pathlib import Path

    path = (Path(registry_path) if registry_path is not None else
            Path(__file__).resolve().parents[1] / "docs/architecture/published-algorithm-hashes.json")
    if not path.is_file():
        return frozenset()
    registry = json.loads(path.read_text(encoding="utf-8"))
    values = registry.get(family, [])
    if not isinstance(values, list) or any(
            not isinstance(value, str) or len(value) != 64 or
            any(char not in "0123456789abcdef" for char in value)
            for value in values):
        raise ValueError("invalid published algorithm hash registry")
    return frozenset(values)


def published_algorithm_matches(family, recorded, current, *, registry_path=None):
    """Accept each recorded hash if published in this family or equal to current.

    Both arguments accept a scalar SHA256 or a filename-to-SHA256 mapping.
    Missing historical filenames are permitted only for registered hashes.
    """
    from collections.abc import Mapping

    known = published_algorithm_hashes(family, registry_path=registry_path)

    def valid(value):
        return (isinstance(value, str) and len(value) == 64 and
                all(char in "0123456789abcdef" for char in value))

    if isinstance(recorded, Mapping):
        if not recorded or not isinstance(current, Mapping):
            return False
        return all(isinstance(key, str) and valid(value) and
                   (value in known or value == current.get(key))
                   for key, value in recorded.items())
    return valid(recorded) and (recorded in known or recorded == current)
