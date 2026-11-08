"""Equivalence proof for terrain_pipeline.common_infra against the legacy copies it replaces.

Legacy functions are pulled out of their *current source files* with ``ast`` and executed in a
minimal namespace, so the oracle is the real code (no hand-copied reimplementation) and no heavy
legacy module is imported.  Every claim in ``common_infra`` docstrings and in
``.scratch/algorithm-refactor-20261105/r2/infra-migration.md`` is asserted here.
"""

import ast
import contextlib
import hashlib
import importlib
import inspect
import json
import math
import os
import re
import sys
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from collections.abc import Mapping

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import common_infra as ci  # noqa: E402
from terrain_pipeline.artifacts import contracts as legacy_contracts  # noqa: E402

PIPE = ROOT / "terrain_pipeline"
# Differential oracle sources, in priority order.  M0 rewrote the import statements of 743 live files, so an
# oracle must never be read from the live tree when a pre-refactor copy exists: a legacy function whose body
# calls a helper that now lives in ``common_infra`` would otherwise be ``common_infra`` comparing itself
# (rules.md §2.3).
#
#   1. before/snapshot/...            -- extracted from dist/Terragenesis-algorithms-20261105.zip, the snapshot
#                                        taken before any merge batch (also on sys.path for its own imports)
#   2. before/terrain_pipeline/...    -- the six absorbed modules copied at the start of this batch
#   3. legacy-code/frozen-sources-20261105/terrain_pipeline/...  -- the evidence snapshot
#   4. the live file                 -- only when none of the above exist; recorded in ORACLE_SOURCES
BEFORE = ROOT / ".scratch/algorithm-refactor-20261105/merge/M0-infra/before/terrain_pipeline"
SNAPSHOT = ROOT / ".scratch/algorithm-refactor-20261105/merge/M0-infra/before/snapshot/terrain_pipeline"
FROZEN = ROOT / "legacy-code/frozen-sources-20261105/terrain_pipeline"
_CACHE = {}
ORACLE_SOURCES = {}      # terrain_pipeline-relative path -> which tier the oracle came from


def _legacy_path(rel):
    """Pre-refactor copy of ``terrain_pipeline/<rel>``; the live file only as a last resort, and reported."""
    if rel in ORACLE_SOURCES:
        return _CACHE[("path", rel)]
    for tier, root in (("snapshot", SNAPSHOT), ("before", BEFORE), ("frozen", FROZEN), ("LIVE", PIPE)):
        candidate = root / rel
        if candidate.is_file():
            ORACLE_SOURCES[rel] = tier
            _CACHE[("path", rel)] = candidate
            return candidate
    raise FileNotFoundError(f"no legacy copy of terrain_pipeline/{rel}")


def _base_namespace(extra):
    ns = dict(hashlib=hashlib, json=json, np=np, numpy=np, os=os, re=re, math=math, tempfile=tempfile,
              Path=Path, Any=Any, Mapping=Mapping)
    ns.update(extra)
    return ns


def _source_of(rel, name):
    key = (rel, name)
    if key not in _CACHE:
        src = _legacy_path(rel).read_text(encoding="utf-8-sig")
        node = next((n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        assert node is not None, f"{rel}: top-level def {name} not found"
        _CACHE[key] = ast.get_source_segment(src, node)
    return _CACHE[key]


def legacy(rel, name, *deps, **extra):
    """Compile ``name`` (and optional ``(rel, name)`` helper deps) out of the legacy copy of ``terrain_pipeline/<rel>``."""
    ns = _base_namespace(extra)
    for dep_rel, dep_name in deps:
        exec(compile(_source_of(dep_rel, dep_name), f"{dep_rel}:{dep_name}", "exec"), ns)
    exec(compile(_source_of(rel, name), f"{rel}:{name}", "exec"), ns)
    return ns[name]


def _world_seed_constant():
    """``WORLD_SEED`` as the archived ``world_seed`` module declared it."""
    src = _legacy_path("world_seed.py").read_text(encoding="utf-8-sig")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "WORLD_SEED":
            return ast.literal_eval(node.value)
    raise AssertionError("world_seed: WORLD_SEED not found")


# ----------------------------------------------------------------------------- file hashes

FILE_HASH_LEGACY = [
    ("artifacts/bundles.py", "file_sha256"),
    ("coastal_marine_product.py", "file_hash"),
    ("coastal_terrain_product.py", "file_hash"),
    ("complete_delta.py", "sha256"),
    ("dem_domain.py", "file_sha256"),
    ('drainage.py', "file_sha256"),
    ("large_delta_shelf_product.py", "_sha"),
    ("large_delta_shelf_scenario.py", "_sha"),
    ("large_delta_suite_source.py", "sha256"),
    ("large_delta_suite_tidal.py", "_sha"),
    ("large_delta_tidal_source.py", "digest"),
    ("legacy_region.py", "_sha256"),
    ("metric_region_storage.py", "_sha256"),
    ('drainage.py', "digest"),
    ("new_world_native_water.py", "_hash"),
    ("new_world_river_scene.py", "_hash"),
    ("new_world_stage1.py", "_digest"),
    ('drainage.py', "digest"),
    ("new_world_width_reach.py", "file_sha256"),
    ("plate_td_product.py", "digest"),
    ("special_terrain_l1_sinkhole.py", "file_sha256"),
    ("surface_network_consumer.py", "_file_hash"),
    ("surface_rivers/finite_river_product.py", "sha256_file"),
    ("surface_rivers/metric_cross_region.py", "_file_sha256"),
    ("world_terrain_disk_store.py", "_sha"),
]
FILE_SIZES = [0, 1, 1023, (1 << 20) - 1, 1 << 20, (1 << 20) + 1, 3 * (1 << 20) + 5, 4 * (1 << 20) + 7]


@pytest.fixture(scope="module")
def sized_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("sized")
    rng = np.random.default_rng(20261020)
    files = []
    for size in FILE_SIZES:
        path = folder / f"f{size}.bin"
        path.write_bytes(rng.integers(0, 256, size, dtype=np.uint8).tobytes())
        files.append(path)
    return files


@pytest.mark.parametrize("rel,name", FILE_HASH_LEGACY, ids=[f"{r}:{n}" for r, n in FILE_HASH_LEGACY])
def test_file_sha256_matches_legacy(rel, name, sized_files):
    old = legacy(rel, name)
    for path in sized_files:
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        assert old(path) == expected
        assert ci.file_sha256(path) == expected
        assert ci.file_sha256(str(path)) == expected


def test_file_sha256_and_size_matches_readiness_digest(tmp_path, sized_files):
    old = legacy("surface_development_readiness.py", "_digest")
    for path in sized_files[1:]:
        assert ci.file_sha256_and_size(path, 1 << 30) == old(path, 1 << 30)
    for bad, limit in ((sized_files[0], 100), (sized_files[3], 10), (tmp_path / "missing.bin", 100)):
        with pytest.raises(ValueError):
            old(bad, limit)
        with pytest.raises(ValueError):
            ci.file_sha256_and_size(bad, limit)


def test_file_record_matches_td_natural_outlet(sized_files):
    old = legacy("td_natural_outlet_certification.py", "_file_record")
    for path in sized_files:
        assert ci.file_record(path) == old(path)


HEX_LEGACY = [
    ("real_dem_outlet_classification.py", "_sha"),
    ("single_domain_fine_geometry.py", "_sha"),
    ("single_domain_surface_geometry.py", "_sha"),
    ("surface_rivers/metric_bank_braiding.py", "_sha"),
    ("surface_rivers/metric_boundary_coupling.py", "_sha"),
    ("surface_rivers/metric_channel_product.py", "_sha"),
    ("surface_rivers/metric_channel_state.py", "_sha"),
    ("surface_rivers/metric_contracts.py", "_sha"),
    ("surface_rivers/metric_delta_product.py", "_sha"),
    ("surface_rivers/metric_backbone_product.py", "_sha256_text"),
]
HEX_VALUES = ["0123456789abcdef" * 4, "a" * 64, "0" * 64, "A" * 64, "a" * 63, "a" * 65, "g" * 64, "",
              "a" * 64 + "\n", "\u0660" * 64, None, 5, b"a" * 64, ("a" * 64,)]


def _passes(function, value):
    arguments = len(inspect.signature(function).parameters)
    try:
        result = function(value) if arguments == 1 else function(value, "label")
    except ValueError:
        return False
    return result if isinstance(result, bool) else True


@pytest.mark.parametrize("rel,name", HEX_LEGACY, ids=[f"{r}:{n}" for r, n in HEX_LEGACY])
def test_sha256_hex_validation_matches_legacy(rel, name):
    def refuse(message):
        raise ValueError(message)
    old = legacy(rel, name, _refuse=refuse)
    for value in HEX_VALUES:
        assert _passes(old, value) == ci.is_sha256_hex(value), repr(value)
        if ci.is_sha256_hex(value):
            assert ci.require_sha256_hex(value, "v") is value
        else:
            with pytest.raises(ValueError):
                ci.require_sha256_hex(value, "v")


def test_sha256_chunks_matches_finite_river_block_schedule():
    old = legacy("surface_rivers/finite_river_block_schedule.py", "_sha_bytes")
    for chunks in (("a", b"b", "\u00e9"), (), (b"",), ("only",), (b"\x00\x01", b"\xff")):
        assert ci.sha256_chunks(*chunks) == old(*chunks)


# ----------------------------------------------------------------------------- array hashes

def _sample_arrays():
    rng = np.random.default_rng(7)
    base = rng.normal(size=(70, 5))
    return [
        rng.normal(size=7),
        base,                                   # > 64 rows (coastal_detail chunking)
        base.T,                                 # non-contiguous
        np.asfortranarray(base[:6, :4]),
        rng.integers(-5, 5, size=(2, 3, 4)).astype(np.int32),
        rng.integers(0, 255, size=(9,)).astype(np.uint8),
        rng.normal(size=(4, 4)).astype(np.float32),
        rng.integers(0, 2, size=(5, 5)).astype(bool),
        rng.integers(-9, 9, size=(8,)).astype("<i8"),
        np.zeros((0, 3)),
        rng.normal(size=(6, 6))[::2, ::3],      # strided view
    ]


@pytest.mark.parametrize("array", _sample_arrays(), ids=lambda a: f"{a.dtype}{a.shape}")
def test_array_digests_match_legacy(array):
    # raw bytes only
    expected = legacy("artifacts/contracts.py", "array_hash")(array)
    assert expected == legacy_contracts.array_hash(array)
    assert ci.array_sha256_raw(array) == expected
    assert legacy("coastal_terrain_product.py", "array_hash")(array) == expected
    assert legacy("coastal_detail_product.py", "array_hash")(array) == expected
    assert legacy("surface_network_tiles.py", "_record")(array)["sha256"] == expected
    mask = array != 0
    assert legacy("coastal_delta_geological.py", "_mask_identity")(mask) == ci.array_sha256_raw(mask, dtype=np.uint8)

    # str(shape) + dtype.str + bytes
    shaped = legacy("artifacts/encoding.py", "shaped_array_hash")(array)
    assert ci.array_sha256(array) == shaped
    for rel, name in (("environment_land_cover.py", "_array_digest"), ("environment_world_product.py", "_array_digest"),
                      ('runoff.py', "_hash"), ("surface_rivers/finite_river_product.py", "array_sha"),
                      ("surface_rivers/metric_pet_et.py", "_array_digest"),
                      ("hydrology_detail_tributaries.py", "_array_digest")):
        assert legacy(rel, name)(array) == shaped, (rel, name)

    # dtype.str + json(shape) + bytes
    json_helper = ('lake.py', "_json")
    compact = ci.array_sha256_dtype_shapejson(array)
    assert legacy("geology_properties.py", "_array_digest", ("geology_properties.py", "_canonical"))(array) == compact
    assert legacy('lake.py', "_array_hash", json_helper)(array) == compact
    assert legacy('lake.py', "_array_hash", ('lake.py', "_json"))(array) == compact
    assert legacy('lake.py', "_hash", ('lake.py', "_json"))(array) == compact
    spaced = ci.array_sha256_dtype_shapejson(array, compact_shape=False)
    assert legacy('lake.py', "_array_hash")(array) == spaced
    if array.ndim >= 2:
        assert spaced != compact      # "[2, 3]" vs "[2,3]" really differ -> two variants are necessary

    # json header [dtype.str, shape]
    assert legacy("surface_coast_drop.py", "_array_hash", ("surface_coast_drop.py", "_json"))(array) == \
        ci.array_sha256_json_header(array)

    # dtype *name* + compact shape, variadic
    old_names = legacy("large_surface_network_validation.py", "_array_hash")
    assert old_names(array) == ci.arrays_sha256_dtypename_shapejson(array)
    assert old_names(array, array[:1]) == ci.arrays_sha256_dtypename_shapejson(array, array[:1])


def test_array_digest_variants_really_differ():
    a = np.arange(12, dtype="<f8").reshape(3, 4)
    digests = {
        ci.array_sha256_raw(a), ci.array_sha256(a), ci.array_sha256_dtype_shapejson(a),
        ci.array_sha256_dtype_shapejson(a, compact_shape=False), ci.array_sha256_json_header(a),
        ci.arrays_sha256_dtypename_shapejson(a),
    }
    assert len(digests) == 6


def test_multi_array_raw_digests():
    rng = np.random.default_rng(3)
    h, r, t = rng.normal(size=(4, 4)), rng.integers(0, 9, (4, 4)), rng.integers(0, 3, (2, 2))
    assert legacy("large_scale_surface_network.py", "_sha256_arrays")(h, r, t) == ci.arrays_sha256_raw(h, r, t)
    exchange = {k: rng.integers(0, 50, 6) for k in ("interval", "wave", "source", "target")}
    exchange["q_m3_s"] = rng.normal(size=6)
    flow = rng.normal(size=10)
    old = legacy("surface_rivers/finite_river_block_schedule.py", "_event_stream_sha")
    assert old(exchange, flow) == ci.arrays_sha256_raw(
        exchange["interval"], exchange["wave"], exchange["source"], exchange["target"], exchange["q_m3_s"], flow)


def test_named_arrays_digest_matches_both_adaptive_copies():
    rng = np.random.default_rng(11)
    arrays = {"b": rng.normal(size=(3, 3)), "a": rng.integers(0, 4, size=5).astype(np.int32),
              "c": np.zeros((2, 0))}
    metadata = {"k": 1, "name": "x", "list": [1, 2, 3], "nested": {"z": 0.5}}
    one = legacy("surface_adaptive_geometry.py", "adaptive_geometry_identity")(arrays, metadata)
    two = legacy("surface_adaptive_io.py", "geometry_identity")(arrays, metadata)
    assert one == two == ci.named_arrays_sha256(arrays, metadata)


def test_world_pair_and_point_digests():
    rng = np.random.default_rng(5)
    pairs = rng.integers(-10_000, 10_000, size=(40, 2))
    shuffled = pairs[rng.permutation(40)]
    old_pairs = legacy("surface_rivers/metric_backbone_precompute.py", "_sha_world_pairs")
    old_path = legacy("surface_rivers/backbone_shape_fidelity.py", "world_path_sha256",
                      ("surface_rivers/backbone_shape_fidelity.py", "_array"))
    old_member = legacy("surface_rivers/metric_highland_sources.py", "member_sha256")
    for candidate in (pairs, pairs.astype(np.int32), pairs.ravel().tolist() and pairs.tolist()):
        assert old_pairs(candidate) == ci.world_pairs_sha256(candidate)
    assert old_path(pairs) == ci.world_pairs_sha256(pairs)
    assert old_member(pairs) == old_member(shuffled) == ci.sorted_world_pairs_sha256(pairs) == \
        ci.sorted_world_pairs_sha256(shuffled)
    assert ci.world_pairs_sha256(pairs) != ci.world_pairs_sha256(shuffled)

    x, z = rng.normal(size=30) * 1e4, rng.normal(size=30) * 1e4
    perm = rng.permutation(30)
    x[3] = x[4]                                                    # tie on x exercises the lexsort key
    geology = legacy("geology_properties.py", "_points_digest")
    seasonal = legacy("environment_seasonal_air.py", "_points_digest",
                      ("environment_seasonal_air.py", "_canonical_order"))
    query = legacy("surface_rivers/metric_environment_query.py", "_points_digest")
    expected = ci.points_sha256(x, z)
    assert geology(x, z) == seasonal(x, z) == query(x, z) == expected
    assert geology(x[perm], z[perm]) == expected
    assert geology(x.reshape(5, 6), z.reshape(5, 6)) == expected
    ordinal = rng.integers(0, 5, 30).astype(np.float64)
    old_ordinal = legacy("surface_rivers/metric_environment_query.py", "_ordinal_digest")
    assert old_ordinal(x, z, ordinal) == ci.points_ordinal_sha256(x, z, ordinal)
    assert ci.points_ordinal_sha256(x[perm], z[perm], ordinal[perm]) == ci.points_ordinal_sha256(x, z, ordinal)


# ----------------------------------------------------------------------------- canonical JSON / identity

JSON_VALUES = [
    {"b": 1, "a": [1, 2.5, None, True], "c": {"z": "x", "y": [3, {"k": "v"}]}},
    {"name": "caf\u00e9 \u5c71\u5ddd", "n": -0.0, "big": 10 ** 20, "f": 1e-9, "t": [1, [2, [3]]]},
    [],
    {},
    {"identity": "abc", "source_paths": ["p"], "terrain_path": "t", "source_path": "s",
     "x": {"identity": "inner", "a_path": "q", "keep": 1}, "l": [{"identity": 1, "m_path": 2, "ok": 3}]},
]
NAN_VALUE = {"a": float("nan"), "b": [float("inf")]}


def _dump(old, value):
    try:
        return old(value)
    except ValueError as error:
        return ("ValueError", type(error).__name__)


@pytest.mark.parametrize("value", JSON_VALUES + [NAN_VALUE], ids=lambda v: str(v)[:30])
def test_canonical_json_variants(value):
    def sha(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def attempt(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError:
            return "ValueError"

    # default form: compact, ASCII, strict
    default_text = [
        legacy("hybrid_river_graph.py", "canonical_json"),
        legacy("artifacts/encoding.py", "json_text"),
        legacy('lake.py', "_json"),
        legacy('lake.py', "_json"),
        legacy('lake.py', "_json"),
        legacy("surface_coast_drop.py", "_json"),
        legacy("td_material_field.py", "_json"),
    ]
    mine = attempt(ci.canonical_json, value)
    for old in default_text:
        assert attempt(old, value) == mine
    for rel, name in (("hydrology_detail_tributaries.py", "_digest"), ("environment_regional_hydraulics.py", "_digest"),
                      ("natural_outlet_certification.py", "_digest"), ("new_world_hydrology.py", "_hash")):
        old = legacy(rel, name)
        expected = attempt(ci.json_sha256, value)
        assert attempt(old, value) == expected, (rel, name)
    # ensure_ascii=False
    mine = attempt(ci.canonical_json, value, ensure_ascii=False)
    assert attempt(legacy("geology_properties.py", "_canonical"), value) == mine
    assert attempt(legacy("surface_development_readiness.py", "_canonical_json"), value) == mine
    assert attempt(legacy("geography_preparation_inventory.py", "_digest"), value) == \
        attempt(ci.json_sha256, value, ensure_ascii=False)
    # default separators
    for rel, name in (("hydrology_detail.py", "_digest"), ("hydrology_detail_projection.py", "_digest"),
                      ("hydrology_detail_td.py", "_digest"), ('runoff.py', "_digest"),
                      ('drainage.py', "canonical_json_digest")):
        assert attempt(legacy(rel, name), value) == attempt(ci.json_sha256, value, compact=False), (rel, name)
    assert attempt(legacy('drainage.py', "canonical_json_digest_compact"), value) == \
        attempt(ci.json_sha256, value)
    # allow_nan=True (marine / archipelago product identities)
    for rel in ("coastal_marine_product.py", "coastal_archipelago_product.py"):
        assert legacy(rel, "identity")(value) == ci.json_sha256(value, allow_nan=True) == \
            ci.record_identity_sha256(value, exclude=(), allow_nan=True)
    assert sha(json.dumps(value, sort_keys=True, separators=(",", ":"))) == ci.json_sha256(value, allow_nan=True)


def test_json_variants_really_differ():
    value = {"a": [1, 2], "u": "\u00e9"}
    texts = {ci.canonical_json(value), ci.canonical_json(value, ensure_ascii=False),
             ci.canonical_json(value, compact=False)}
    assert len(texts) == 3
    with pytest.raises(ValueError):
        ci.canonical_json(NAN_VALUE)
    assert "NaN" in ci.canonical_json(NAN_VALUE, allow_nan=True)


@pytest.mark.parametrize("value", JSON_VALUES + [(1, 2), {1: "x"}, {"f": float("nan")}, {"s": {1, 2}}, {"t": (1, 2)}],
                         ids=lambda v: str(v)[:30])
def test_canonical_json_checked_matches_contracts(value):
    try:
        expected = legacy_contracts.canonical_json(value)
    except ValueError as error:
        with pytest.raises(ValueError, match=re.escape(str(error))):
            ci.canonical_json_checked(value)
        return
    assert ci.canonical_json_checked(value) == expected
    assert hashlib.sha256(expected.encode("utf-8")).hexdigest() == legacy_contracts.digest(value)


@pytest.mark.parametrize("record", JSON_VALUES[:2] + JSON_VALUES[4:], ids=lambda v: str(v)[:30])
def test_record_identity_matches_product_identities(record):
    assert legacy("new_world_source_mosaic.py", "identity")(record) == \
        ci.record_identity_sha256(record, exclude=("identity", "source_paths"))
    assert legacy("new_world_stage1.py", "_identity")(record) == \
        ci.record_identity_sha256(record, exclude=("identity", "terrain_path"))
    assert legacy("new_world_terrain.py", "_identity")(record) == ci.record_identity_sha256(record, exclude=("source_path",))
    assert legacy("new_world_river_scene.py", "_identity")(record) == ci.record_identity_sha256(record, exclude=("identity",))
    assert legacy("new_world_native_water.py", "_identity")(record) == \
        ci.record_identity_sha256(record, exclude=("identity",), allow_nan=True)
    assert legacy("coastal_detail_product.py", "identity")(record) == \
        ci.record_identity_sha256(record, exclude=("identity",), exclude_suffixes=("_path",), recursive=True)
    assert legacy("hybrid_river_graph.py", "identity", ("hybrid_river_graph.py", "canonical_json"))(record) == \
        ci.record_identity_sha256(record, exclude=())
    assert legacy("coastal_marine_product.py", "identity")(record) == \
        ci.record_identity_sha256(record, exclude=(), allow_nan=True)


def test_bundle_identity_matches_artifacts_bundles():
    rng = np.random.default_rng(2)
    arrays = {"z": rng.normal(size=(3, 3)), "a": rng.integers(0, 5, 4).astype(np.int16)}
    metadata = {"k": "v", "n": [1, 2], "u": "\u00e9"}
    old = legacy("artifacts/bundles.py", "identity", ("artifacts/encoding.py", "json_text"),
                 ("artifacts/encoding.py", "shaped_array_hash"))
    assert old(arrays, metadata) == ci.identity(arrays, metadata)


# ----------------------------------------------------------------------------- seeds

SEEDS = [0, 1, 20260903, 20261020, 2 ** 63, 2 ** 64 - 1]
PURPOSES = ["terrain", "class_primary", "a", "rock_medium", "x" * 40, "river_noise_2"]


def test_seed_mountains_matches_world_seed_module():
    old_mountains = legacy("world_seed.py", "derive_subseed")
    for seed in SEEDS:
        for purpose in PURPOSES:
            expected = old_mountains(seed, purpose)
            assert ci.seed_mountains_v1(seed, purpose) == expected
            assert ci.derive_subseed(seed, purpose) == expected
            assert ci.derive_subseed(seed, purpose, scheme="mountains-v1") == expected
    assert ci.seed_mountains_v1(np.int64(5), "p") == old_mountains(5, "p")
    for bad_seed, bad_purpose in ((True, "p"), (-1, "p"), (2 ** 64, "p"), (1.0, "p"), (1, ""), (1, 5)):
        with pytest.raises(ValueError):
            old_mountains(bad_seed, bad_purpose)
        with pytest.raises(ValueError):
            ci.seed_mountains_v1(bad_seed, bad_purpose)


def test_seed_overview_matches_fictional_world_overview():
    class OverviewError(ValueError):
        pass
    old = legacy("fictional_world_overview.py", "derive_subseed", OverviewError=OverviewError,
                 SEED_NAMESPACE="terragenesis-fictional-world-overview-v1",
                 _PURPOSE=re.compile(r"[a-z][a-z0-9_]{0,48}\Z"))
    for seed in SEEDS:
        for purpose in ("terrain", "ridge_noise", "a", "x" * 49):
            for index in (0, 1, 17, np.int64(3)):
                assert ci.seed_overview_v1(seed, purpose, index=index) == old(seed, purpose, index)
                assert ci.derive_subseed(seed, purpose, scheme="overview-v1", index=index) == old(seed, purpose, index)
    for args in ((1, "Bad"), (1, "x" * 50), (1, ""), (True, "a"), (-1, "a"), (1, "a", -1), (1, "a", True)):
        with pytest.raises(ValueError):
            old(*args)
        with pytest.raises(ValueError):
            ci.seed_overview_v1(*args)


def test_seed_lithology_matches_td_lithology_field():
    old = legacy("td_lithology_field.py", "derive_subseed", SEED_PURPOSES=ci.LITHOLOGY_PURPOSES)
    source = (PIPE / "td_lithology_field.py").read_text(encoding="utf-8-sig")
    declared = next(ast.literal_eval(n.value) for n in ast.parse(source).body
                    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SEED_PURPOSES")
    assert tuple(declared) == ci.LITHOLOGY_PURPOSES
    for seed in SEEDS:
        for purpose in ci.LITHOLOGY_PURPOSES:
            assert ci.seed_lithology_v1(seed, purpose) == old(seed, purpose)
    with pytest.raises(ValueError):
        ci.seed_lithology_v1(1, "unknown")


def test_seed_water_layout_matches_world_water_layout():
    class LayoutError(ValueError):
        pass
    old = legacy("world_water_layout.py", "derive_subseed", LayoutError=LayoutError,
                 NAMESPACE=b"terragenesis-world-water-layout-v1")
    for seed in SEEDS:
        for layout in ("a", "layout-\u00e9", "world"):
            for i, j in ((0, 0), (3, -4), (-1, -1), (2 ** 63 - 1, -2 ** 63), (np.int64(7), 5)):
                assert ci.seed_water_layout_v1(seed, layout, "rivers", i, j) == old(seed, layout, "rivers", i, j)
                assert ci.derive_subseed(seed, "rivers", scheme="water-layout-v1", layout_id=layout,
                                         region_i=i, region_j=j) == old(seed, layout, "rivers", i, j)
    for args in ((1, "", "p"), (1, "a\x00b", "p"), (1, "a", ""), (1, "a", "p", 2 ** 63), (1, "a", "p", 0, True)):
        with pytest.raises(ValueError):
            old(*args)
        with pytest.raises(ValueError):
            ci.seed_water_layout_v1(*args)


def test_noise_json_seeds_are_two_different_schemes():
    old_graph = legacy("surface_rivers/world_channel_graph.py", "derive_noise_seed")
    old_cross = legacy("surface_rivers/metric_cross_region.py", "derive_sub_seed")
    differ = 0
    for seed in SEEDS:
        for purpose in PURPOSES + ["p q"]:
            assert ci.seed_noise_json_v1(seed, purpose) == old_graph(seed, purpose)
            assert ci.seed_noise_json_spaced_v1(seed, purpose) == old_cross(seed, purpose)
            assert ci.derive_subseed(seed, purpose, scheme="noise-json-v1") == old_graph(seed, purpose)
            assert ci.derive_subseed(seed, purpose, scheme="noise-json-spaced-v1") == old_cross(seed, purpose)
            differ += old_graph(seed, purpose) != old_cross(seed, purpose)
    assert differ == len(SEEDS) * (len(PURPOSES) + 1)      # same namespace string, never the same seed
    for bad in ((True, "p"), (1.5, "p"), (1, ""), (1, "  "), (1, 3)):
        with pytest.raises(ValueError):
            old_graph(*bad)
        with pytest.raises(ValueError):
            ci.seed_noise_json_v1(*bad)


def test_seed_ledger_53bit_matches_native_30m_ledger():
    deps = (("surface_rivers/native_30m_hydrology_ledger.py", "_world_seed"),
            ("surface_rivers/native_30m_hydrology_ledger.py", "_purpose"))
    old = legacy("surface_rivers/native_30m_hydrology_ledger.py", "purpose_subseeds", *deps,
                 SUBSEED_PURPOSES=("a",), SUBSEED_DERIVATION="x")
    for seed in SEEDS:
        result = old(seed, ("terrain", "rivers_2", "z"))["subseeds"]
        for purpose, value in result.items():
            assert ci.seed_ledger_53bit_v1(seed, purpose) == value
            assert value < 2 ** 53


def test_pipe_and_string_formula_seeds():
    site = legacy("delta_network_site.py", "derive_seed", WORLD_SEED=ci.WORLD_SEED_LEGACY_20261020)
    assert re.search(r"^WORLD_SEED = 20261020$", (PIPE / "delta_network_site.py").read_text(encoding="utf-8-sig"), re.M)
    for purpose in PURPOSES:
        for extra in ((), (1,), ("a", 2.5), ((1, 2), None)):
            assert ci.seed_pipe_v1(ci.WORLD_SEED_LEGACY_20261020, purpose, *extra) == site(purpose, *extra)
            assert ci.derive_subseed(ci.WORLD_SEED_LEGACY_20261020, purpose, scheme="pipe-v1") == site(purpose)

    complete = legacy("complete_delta.py", "purpose_seed", WORLD_SEED=ci.WORLD_SEED_LEGACY_20261020)
    natural = legacy("surface_rivers/metric_natural_construction.py", "derived_seed")
    tectonic = legacy("tectonic_evolution.py", "_purpose_seed")
    belts = legacy("world_mountain_belts.py", "_seed")
    erosion = legacy("procedural_mountain_erosion.py", "_seed", ALGORITHM_ID="alg-x")
    for seed in SEEDS:
        for purpose in PURPOSES:
            little4 = ci.hash_seed(f"{seed}:{purpose}", nbytes=4, byteorder="little", encoding="ascii")
            assert natural(seed, purpose) == little4
            if seed == ci.WORLD_SEED_LEGACY_20261020:
                assert complete(purpose) == ci.hash_seed(f"{seed}:{purpose}", nbytes=4, byteorder="little",
                                                         encoding="ascii")
            assert tectonic(seed, purpose) == ci.hash_seed(f"{seed}:tectonic:{purpose}", byteorder="little")
            assert belts(seed, purpose) == ci.hash_seed(str(seed) + ":world-mountain-belts:" + purpose)
            assert int(erosion(seed, purpose)) == ci.hash_seed(f"alg-x:{seed}:{purpose}", byteorder="little",
                                                               encoding="ascii")
    corridor = legacy("large_delta_suite_network.py", "_corridor_field")
    for case in ("main", "case-2"):
        _, seed = corridor((4, 4), (0.0, 0.0), 30.0, case)
        assert seed == ci.hash_seed("20261020:delta-suite/corridor/" + case, byteorder="little", encoding="utf8")
    ident = legacy("new_world_hydrology.py", "_id", VERSION="v7")
    assert ident("island", "river", 3, -4) == (ci.hash_seed("v7:island:river:3:-4") or 1)


def test_seed_schemes_are_pairwise_different_and_registered():
    values = {name: ci.derive_subseed(20261020, "class_primary", scheme=name, **({"layout_id": "a"} if name == "water-layout-v1" else {}))
              for name in ci.SEED_SCHEMES}
    assert len(set(values.values())) == len(values)
    with pytest.raises(ValueError):
        ci.derive_subseed(1, "p", scheme="nope")


def test_mix64_matches_irregular_drainage():
    old = legacy('drainage.py', "_mix64")
    rng = np.random.default_rng(9)
    values = rng.integers(0, 2 ** 63, size=256, dtype=np.uint64) * np.uint64(3)
    assert np.array_equal(old(values), ci.mix64(values))
    assert np.array_equal(old(np.zeros(4, np.uint64)), ci.mix64(np.zeros(4, np.uint64)))


# ----------------------------------------------------------------------------- coordinates

def test_local_world_transform_matches_delta_network_site():
    axes = legacy("delta_network_site.py", "axes", SiteSpec=object)
    namespace = _base_namespace({"axes": axes, "SiteSpec": object})
    exec(compile(_source_of("delta_network_site.py", "local_to_world"), "l2w", "exec"), namespace)
    exec(compile(_source_of("delta_network_site.py", "world_to_local"), "w2l", "exec"), namespace)
    rng = np.random.default_rng(4)
    u, v = rng.normal(size=(2, 25)) * 5000
    for alpha, anchor in ((45.0, (0.0, 0.0)), (45.0, (-1234.5, 777.25)), (0.0, (10.0, 20.0)), (123.4, (1e5, -3e4)),
                          (-90.0, (0.0, 1.0))):
        spec = SimpleNamespace(alpha_deg=alpha, anchor_world_m=anchor)
        old_x, old_z = namespace["local_to_world"](spec, u, v)
        new_x, new_z = ci.local_to_world(anchor, alpha, u, v)
        assert np.array_equal(old_x, new_x) and np.array_equal(old_z, new_z)
        old_u, old_v = namespace["world_to_local"](spec, old_x, old_z)
        new_u, new_v = ci.world_to_local(anchor, alpha, new_x, new_z)
        assert np.array_equal(old_u, new_u) and np.array_equal(old_v, new_v)
        assert np.allclose(new_u, u) and np.allclose(new_v, v)
    scalar_old = namespace["local_to_world"](SimpleNamespace(alpha_deg=45.0, anchor_world_m=(1.0, 2.0)), 3.0, 4.0)
    assert scalar_old == ci.local_to_world((1.0, 2.0), 45.0, 3.0, 4.0)


def test_world_to_cell_matches_coastal_delta_routes():
    old = legacy("coastal_delta_routes.py", "world_to_cell")
    origin, spacing, shape = np.array([-61440.0, -61440.0]), 30.0, (40, 50)
    for xz in ([-61440.0, -61440.0], [-61440.0 + 15.0, -61440.0 + 44.9], [-61440.0 + 30 * 49, -61440.0 + 30 * 39],
               [-61440.0 + 14.9, -61440.0 - 14.9], (-61000.0, -61100.0)):
        assert ci.world_to_cell(xz, origin, spacing, shape) == old(xz, origin, spacing, shape)
    for outside in ([-61440.0 - 16.0, -61440.0], [-61440.0, -61440.0 + 30 * 40], [0.0, 0.0]):
        with pytest.raises(ValueError):
            old(outside, origin, spacing, shape)
        with pytest.raises(ValueError):
            ci.world_to_cell(outside, origin, spacing, shape)


def test_native_constants_match_drainage_kernels_source():
    # M0 moved these constants into ``common_infra``; the live module now only re-imports them, so the
    # oracle is the pre-refactor source (rules.md §2.3: never let common_infra compare against itself).
    tree = ast.parse(_legacy_path('drainage.py').read_text(encoding="utf-8-sig"))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id if isinstance(t, ast.Name) else tuple(e.id for e in t.elts) for t in node.targets]
            value = ast.literal_eval(node.value)
            if names[0] == "NATIVE_GRID":
                found["NATIVE_GRID"] = value
            elif names[0] == "NATIVE_ORIGIN_M":
                found["NATIVE_ORIGIN_M"] = value
            elif names[0] == "NATIVE_SPACING_M":
                found["NATIVE_SPACING_M"] = value
            elif isinstance(names[0], tuple) and names[0][0] == "NATIVE_WINDOW_Z0":
                found["WINDOW"] = tuple(value)
    assert found["NATIVE_GRID"] == ci.NATIVE_GRID
    assert found["NATIVE_ORIGIN_M"] == ci.NATIVE_ORIGIN_M
    assert found["NATIVE_SPACING_M"] == ci.NATIVE_SPACING_M
    assert found["WINDOW"] == (ci.NATIVE_WINDOW_Z0, ci.NATIVE_WINDOW_Z1, ci.NATIVE_WINDOW_X0, ci.NATIVE_WINDOW_X1)
    assert ci.WORLD_SEED == _world_seed_constant()


# ----------------------------------------------------------------------------- mmap

def test_load_npy_readonly_is_readonly_memmap_without_pickle(tmp_path):
    data = np.arange(24, dtype="<f4").reshape(4, 6)
    path = tmp_path / "bed_m.npy"
    np.save(path, data)
    legacy_load = lambda p: np.load(p, mmap_mode="r", allow_pickle=False)     # the 12 copied lambdas
    loaded = ci.load_npy_readonly(path)
    assert isinstance(loaded, np.memmap) and np.array_equal(loaded, legacy_load(path)) and np.array_equal(loaded, data)
    with pytest.raises((ValueError, TypeError)):
        loaded[0, 0] = 1.0
    assert np.array_equal(ci.load_npy_member(tmp_path, "bed_m"), data)
    assert np.array_equal(ci.load_npy_member(str(tmp_path), "bed_m"), data)
    pickled = tmp_path / "obj.npy"
    np.save(pickled, np.array([{"a": 1}], dtype=object), allow_pickle=True)
    with pytest.raises(ValueError):
        ci.load_npy_readonly(pickled)


# ----------------------------------------------------------------------------- atomic writes

def _leftovers(folder, keep):
    return sorted(p.name for p in Path(folder).iterdir() if p.name not in keep)


def test_atomic_write_json_bytes_match_legacy_writers(tmp_path):
    record = {"b": [1, 2.5, {"z": None}], "a": "caf\u00e9", "c": True}
    # new_world_native_* manifests: tmp.write_text(json.dumps(record, indent=2), encoding='utf8'); os.replace
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps(record, indent=2), encoding="utf8")
    ci.atomic_write_json(tmp_path / "manifest.json", record, indent=2, sort_keys=False, encoding="utf8")
    assert (tmp_path / "manifest.json").read_bytes() == expected.read_bytes()
    # stage1 checkpoint / flood phases: json.dump(value, stream, sort_keys=True, indent=2)
    for rel in ("new_world_stage1_checkpoint.py", 'drainage.py'):
        old = legacy(rel, "atomic_json")
        old(tmp_path / "old.json", record)
        ci.atomic_write_json(tmp_path / "new.json", record, indent=2, sort_keys=True)
        assert (tmp_path / "new.json").read_bytes() == (tmp_path / "old.json").read_bytes()
        (tmp_path / "old.tmp").unlink(missing_ok=True)
    # world_terrain_store._atomic_json (allow_nan=False, mkstemp)
    legacy("world_terrain_store.py", "_atomic_json")(tmp_path / "ws_old.json", record)
    ci.atomic_write_json(tmp_path / "ws_new.json", record, indent=2, sort_keys=True, allow_nan=False)
    assert (tmp_path / "ws_new.json").read_bytes() == (tmp_path / "ws_old.json").read_bytes()
    # td_entry_pulse_incremental.atomic_index: pre-encoded bytes with trailing newline
    legacy("td_entry_pulse_incremental.py", "atomic_index")(tmp_path / "idx_old.json", record)
    ci.atomic_write_json(tmp_path / "idx_new.json", record, indent=2, sort_keys=True, allow_nan=False,
                         trailing_newline=True, newline="\n")
    assert (tmp_path / "idx_new.json").read_bytes() == (tmp_path / "idx_old.json").read_bytes()
    # surface_development_readiness.save_readiness payload expression (ensure_ascii=False)
    payload = (json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    ci.atomic_write_json(tmp_path / "ready.json", record, indent=2, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, trailing_newline=True, newline="\n", overwrite=False)
    assert (tmp_path / "ready.json").read_bytes() == payload
    ci.atomic_write_bytes(tmp_path / "bytes.bin", payload)
    assert (tmp_path / "bytes.bin").read_bytes() == payload
    assert not [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]


def test_atomic_write_never_leaves_temporaries_or_partial_targets(tmp_path):
    target = tmp_path / "out" / "nested" / "f.json"

    def explode(stream):
        stream.write(b"partial")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        ci.atomic_write(target, explode)
    assert not target.exists() and _leftovers(target.parent, ()) == []
    ci.atomic_write_text(target, "one")
    with pytest.raises(RuntimeError):
        ci.atomic_write(target, explode)
    assert target.read_text() == "one" and _leftovers(target.parent, {"f.json"}) == []
    with pytest.raises(FileExistsError):
        ci.atomic_write_text(target, "two", overwrite=False)
    assert target.read_text() == "one" and _leftovers(target.parent, {"f.json"}) == []
    ci.atomic_write_text(target, "three")
    assert target.read_text() == "three"
    with pytest.raises(FileNotFoundError):
        ci.atomic_write_text(tmp_path / "missing" / "x.txt", "a", make_parents=False)


def test_atomic_write_overwrite_false_matches_publish_bytes_semantics(tmp_path):
    target = tmp_path / "bundle.bin"
    publish_bytes = legacy("artifacts/bundles.py", "publish_bytes", tempfile=tempfile, os=os)
    publish_bytes(tmp_path / "legacy.bin", b"payload")
    ci.atomic_write_bytes(target, b"payload", overwrite=False)
    assert target.read_bytes() == (tmp_path / "legacy.bin").read_bytes()
    with pytest.raises(FileExistsError):
        publish_bytes(target, b"other")
    with pytest.raises(FileExistsError):
        ci.atomic_write_bytes(target, b"other", overwrite=False)
    assert target.read_bytes() == b"payload"


def test_atomic_save_npz_roundtrip_and_refuses_overwrite(tmp_path):
    arrays = {"a": np.arange(10.0), "b": np.arange(6, dtype=np.int32).reshape(2, 3)}
    target = tmp_path / "x.npz"
    ci.atomic_save_npz(target, arrays)
    with np.load(target, allow_pickle=False) as loaded:
        assert sorted(loaded.files) == ["a", "b"]
        assert all(np.array_equal(loaded[k], arrays[k]) for k in arrays)
    with pytest.raises(FileExistsError):
        ci.atomic_save_npz(target, arrays)
    ci.atomic_save_npz(target, {"a": np.zeros(2)}, overwrite=True, compressed=False)
    with np.load(target, allow_pickle=False) as loaded:
        assert loaded.files == ["a"]
    assert _leftovers(tmp_path, {"x.npz"}) == []


def test_atomic_write_concurrent_writers(tmp_path):
    # overwrite=False: exactly one publisher wins, the rest see FileExistsError, nothing is left behind
    target = tmp_path / "once.bin"
    barrier = threading.Barrier(8)

    def publish(i):
        barrier.wait()
        try:
            ci.atomic_write_bytes(target, f"writer-{i}".encode(), overwrite=False)
            return "ok"
        except FileExistsError:
            return "exists"

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(publish, range(8)))
    assert results.count("ok") == 1 and results.count("exists") == 7
    assert target.read_bytes().startswith(b"writer-")
    assert _leftovers(tmp_path, {"once.bin"}) == []

    # overwrite=True on distinct targets in one folder: unique temp names never collide
    def write_distinct(i):
        ci.atomic_write_json(tmp_path / f"m{i}.json", {"i": i}, indent=2)
        return i

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(write_distinct, range(32)))
    assert all(json.loads((tmp_path / f"m{i}.json").read_text())["i"] == i for i in range(32))
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

# ----------------------------------------------------------------------------- absorbed modules
# M0 merged ``mountain_source_adapter``, ``surface_rivers/metric_contracts``, ``artifacts/bundles``,
# ``artifacts/encoding``, ``artifacts/storage`` and ``world_seed`` into ``common_infra``.  The oracle is the same
# module imported from the pre-refactor snapshot tree, so its own imports resolve to snapshot bytes too.

ABSORBED = {
    "adapter": "terrain_pipeline/mountain_source_adapter.py",
    "contracts": "terrain_pipeline/surface_rivers/metric_contracts.py",
    "bundles": "terrain_pipeline/artifacts/bundles.py",
    "encoding": "terrain_pipeline/artifacts/encoding.py",
    "storage": "terrain_pipeline/artifacts/storage.py",
    "world_seed": "terrain_pipeline/world_seed.py",
    "artifacts_package": "terrain_pipeline/artifacts/__init__.py",
}
SNAPSHOT_ROOT = SNAPSHOT.parent              # .../before/snapshot  (holds terrain_pipeline/ and tools/)
ARCHIVE = ROOT / "legacy-code/refactor-merge-20261105/M0-infra"


@contextlib.contextmanager
def snapshot_imports():
    """Make ``import terrain_pipeline...`` resolve to the pre-refactor snapshot, then restore the live tree."""
    saved_path = list(sys.path)
    saved_modules = {name: module for name, module in sys.modules.items()
                     if name == "terrain_pipeline" or name.startswith("terrain_pipeline.")}
    saved_tools = {name: module for name, module in sys.modules.items() if name == "tools" or name.startswith("tools.")}
    for name in list(saved_modules) + list(saved_tools):
        del sys.modules[name]
    sys.path.insert(0, str(SNAPSHOT_ROOT))
    try:
        yield
    finally:
        for name in [n for n in sys.modules if n == "terrain_pipeline" or n.startswith("terrain_pipeline.")
                     or n == "tools" or n.startswith("tools.")]:
            del sys.modules[name]
        sys.modules.update(saved_modules)
        sys.modules.update(saved_tools)
        sys.path[:] = saved_path


def absorbed(name):
    """The legacy module object itself, imported from the pre-refactor snapshot.

    All snapshot modules are loaded inside **one** ``snapshot_imports()`` block and kept, so the archived
    ``storage`` module and the archived ``contracts`` classes it validates against are the same module objects.
    """
    if "modules" not in _CACHE:
        loaded = {}
        with snapshot_imports():
            for key, relative in ABSORBED.items():
                module_name = relative.removesuffix(".py").replace("/", ".")
                if module_name.endswith(".__init__"):
                    module_name = module_name.removesuffix(".__init__")
                loaded[key] = importlib.import_module(module_name)
        _CACHE["modules"] = loaded
    return _CACHE["modules"][name]


def test_absorbed_archive_keeps_the_snapshot_bytes():
    """rules.md §2.4: the archive and the batch-start copy both hold the pre-refactor bytes."""
    archived_modules = {name: relative for name, relative in ABSORBED.items() if name != "artifacts_package"}
    with zipfile.ZipFile(ROOT / "dist/Terragenesis-algorithms-20261105.zip") as archive:
        for name, relative in archived_modules.items():
            archived = (ARCHIVE / relative).read_bytes()
            before = (BEFORE / relative.removeprefix("terrain_pipeline/")).read_bytes()
            in_snapshot = archive.read(relative)
            assert archived == before == in_snapshot, name


def test_oracle_never_reads_a_live_file_for_the_absorbed_modules():
    absorbed_paths = {value.removeprefix("terrain_pipeline/") for name, value in ABSORBED.items()
                      if name != "artifacts_package"}
    for relative in absorbed_paths:
        _legacy_path(relative)
    tiers = {rel: tier for rel, tier in ORACLE_SOURCES.items() if rel in absorbed_paths}
    assert tiers and set(tiers.values()) <= {"snapshot", "before", "frozen"}, tiers


def test_bundle_helpers_match_archived_bundles():
    old = absorbed("bundles")
    rng = np.random.default_rng(21)
    arrays = {"height": rng.normal(size=(4, 5)), "mask": rng.normal(size=4) > 0}
    metadata = {"seed": 20261020, "name": "\u5c71\u5ddd"}
    assert old.identity(arrays, metadata) == ci.identity(arrays, metadata)
    assert old.MAX_BYTES == ci.MAX_BYTES and old.MAX_METADATA == ci.MAX_METADATA
    for value in (rng.normal(size=6), np.arange(6, dtype="<i8"), rng.normal(size=3).astype(np.float32)):
        assert old.readonly(value).tobytes() == ci.readonly(value).tobytes()
        assert not ci.readonly(value).flags.writeable


def test_encoding_helpers_match_archived_encoding():
    old = absorbed("encoding")
    rng = np.random.default_rng(22)
    for value in ({"b": 1, "a": [1, 2.5, None, True]}, {"u": "\u5c71\u5ddd", "n": -0.0}, {}, []):
        assert old.json_text(value) == ci.canonical_json(value)
        assert old.strict_json(old.json_text(value)) == ci.strict_json(ci.canonical_json(value))
    for payload in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
        for reader in (old.strict_json, ci.strict_json):
            with pytest.raises(ValueError):
                reader(payload)
    for array in (rng.normal(size=(3, 4)), np.arange(5, dtype="<i8"), np.zeros((0, 3))):
        assert old.shaped_array_hash(array) == ci.array_sha256(array)


def test_checked_archive_and_bundle_roundtrip_match_archived_bundles(tmp_path):
    from terrain_pipeline.artifacts import ArtifactIdentity, SurfaceWater, TerrainArtifact
    old_bundles = absorbed("bundles")
    old_storage = absorbed("storage")
    rng = np.random.default_rng(23)
    arrays = {"a": rng.normal(size=(3, 3)), "mask": rng.normal(size=3) > 0}
    metadata = {"k": "v"}
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": ci.identity(arrays, metadata)}

    def validate(value):
        if value["identity_sha256"] != ci.identity(value["arrays"], value["metadata"]):
            raise ValueError("identity mismatch")

    old_bundles.save_bundle(tmp_path / "old.npz", result, validator=validate)
    ci.save_bundle(tmp_path / "new.npz", result, validator=validate)
    assert (tmp_path / "old.npz").read_bytes() == (tmp_path / "new.npz").read_bytes()
    loaded_old = old_bundles.load_bundle(tmp_path / "old.npz", expected_sha256=ci.file_sha256(tmp_path / "old.npz"),
                                        validator=validate)
    loaded_new = ci.load_bundle(tmp_path / "new.npz", expected_sha256=ci.file_sha256(tmp_path / "new.npz"),
                                validator=validate)
    assert loaded_old["identity_sha256"] == loaded_new["identity_sha256"]
    for key in arrays:
        assert np.array_equal(loaded_old["arrays"][key], loaded_new["arrays"][key])
    headers_old = {}
    headers_new = {}
    old_bundles.checked_archive(tmp_path / "old.npz", expected_sha256=ci.file_sha256(tmp_path / "old.npz"),
                                header_validator=headers_old.update)
    ci.checked_archive(tmp_path / "new.npz", expected_sha256=ci.file_sha256(tmp_path / "new.npz"),
                       header_validator=headers_new.update)
    assert headers_old == headers_new

    fields = dict(kind="base", identity=ArtifactIdentity("fixture", "height", "1", 7, {"a": 1}),
                  reference_elevation_m=np.array([[1.0, 2.0], [3.0, 4.0]]),
                  origin_x_m=0, origin_z_m=0, spacing_x_m=30, spacing_z_m=30,
                  vertical_datum="sea_zero_m", sea_level_elevation_m=0,
                  water=SurfaceWater(np.array([[5.0, 0.0], [0.0, 6.0]]),
                                     np.array([[True, False], [False, True]]),
                                     np.zeros((2, 2))))
    artifact = TerrainArtifact(**fields)
    # The archived storage module validates against the archived contract classes, so build it its own copy.
    snapshot_artifacts = absorbed("artifacts_package")
    old_artifact = snapshot_artifacts.TerrainArtifact(
        **dict(fields, identity=snapshot_artifacts.ArtifactIdentity("fixture", "height", "1", 7, {"a": 1}),
               water=snapshot_artifacts.SurfaceWater(np.array([[5.0, 0.0], [0.0, 6.0]]),
                                                    np.array([[True, False], [False, True]]),
                                                    np.zeros((2, 2)))))
    old_storage.save_artifact(old_artifact, tmp_path / "artifact_old")
    ci.save_artifact(artifact, tmp_path / "artifact_new")
    assert (tmp_path / "artifact_old" / "manifest.json").read_bytes() == \
        (tmp_path / "artifact_new" / "manifest.json").read_bytes()
    for name in ("reference_elevation_m", "surface_elevation_m", "wet_mask", "discharge_m3_per_s"):
        assert np.array_equal(np.load(tmp_path / "artifact_old" / "arrays.npz")[name],
                              np.load(tmp_path / "artifact_new" / "arrays.npz")[name])
    old_loaded = old_storage.load_artifact(tmp_path / "artifact_old")
    new_loaded = ci.load_artifact(tmp_path / "artifact_new")
    assert (old_loaded.content_id, old_loaded.identity.sha256) == (new_loaded.content_id, new_loaded.identity.sha256)


def test_mountain_source_contract_matches_archived_adapter():
    old = absorbed("adapter")
    height = np.arange(25, dtype=np.float64).reshape(5, 5)
    arguments = dict(origin_m_xz=[0.0, 0.0], spacing_m=30.0,
                     provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                                 "archive_sha256": "0" * 64},
                     boundary={"policy": "all_edges_open", "halo_cells": 0,
                               "upstream_contribution": "excluded_finite_experiment"})
    legacy_source = old.make_source(height, **arguments)
    new_source = ci.make_source(height, **arguments)
    assert legacy_source["identity_sha256"] == new_source["identity_sha256"]
    assert legacy_source["metadata"] == new_source["metadata"]
    assert sorted(legacy_source["arrays"]) == sorted(new_source["arrays"])
    for key in legacy_source["arrays"]:
        assert np.array_equal(legacy_source["arrays"][key], new_source["arrays"][key])
    assert old.MAX_CELLS == ci.SOURCE_MAX_CELLS and old.MAX_METADATA == ci.MAX_METADATA
    assert old.SCHEMA == ci.SOURCE_SCHEMA and old.KINDS == ci.SOURCE_KINDS
    bad = dict(new_source)
    bad["metadata"] = dict(new_source["metadata"], schema="other")
    for implementation in (old.validate_source, ci.validate_source):
        with pytest.raises(ValueError):
            implementation(bad)


def test_metric_contracts_match_archived_module():
    old = absorbed("contracts")
    rng = np.random.default_rng(24)
    height = rng.normal(size=(6, 7))
    height[0, 0] = np.nan
    valid = np.ones(height.shape, bool)
    valid[0, 0] = False
    digest = "0" * 64
    arguments = dict(elevation_m=height, valid_mask=valid, x0_m=0.0, z0_m=0.0, dx_m=30.0, dz_m=30.0,
                     source_kind="generated_terrain", source_id="fixture", source_sha256=digest)
    legacy_grid = old.TerrainGrid(**arguments)
    new_grid = ci.TerrainGrid(**arguments)
    assert legacy_grid.identity_sha256 == new_grid.identity_sha256
    assert legacy_grid.metadata() == new_grid.metadata()
    assert legacy_grid.cell_area_m2 == new_grid.cell_area_m2
    for cell in (0, 5, 41):
        assert legacy_grid.world_xz(cell) == new_grid.world_xz(cell)
    assert np.array_equal(legacy_grid.elevation_m, new_grid.elevation_m)

    forcing_arguments = dict(time_seconds=np.array([0.0, 3600.0, 7200.0]),
                             rain_mm_h=np.abs(rng.normal(size=(2, 3, 4))), source_id="fixture",
                             source_sha256=digest)
    legacy_forcing = old.RainfallForcing(**forcing_arguments)
    new_forcing = ci.RainfallForcing(**forcing_arguments)
    assert legacy_forcing.identity_sha256 == new_forcing.identity_sha256
    assert np.array_equal(legacy_forcing.rainfall_depth_mm, new_forcing.rainfall_depth_mm)

    kind = np.full((4, 4), "interior", dtype="U24")
    kind[[0, -1], :] = "closed_wall"
    kind[:, [0, -1]] = "closed_wall"
    kind[1, 1] = "prescribed_stage"
    stage = np.zeros((4, 4))
    stage[1, 1] = 2.5
    boundary_arguments = dict(kind=kind, allow_inflow=np.zeros((4, 4), bool), source_id="fixture",
                              source_sha256=digest, stage_m=stage)
    legacy_boundary = old.BoundaryGrid(**boundary_arguments)
    new_boundary = ci.BoundaryGrid(**boundary_arguments)
    assert legacy_boundary.identity_sha256 == new_boundary.identity_sha256
    assert np.array_equal(legacy_boundary.outlet_mask, new_boundary.outlet_mask)
    assert old.MAX_CELLS == ci.GRID_MAX_CELLS and old.MAX_FORCING_ENTRIES == ci.MAX_FORCING_ENTRIES
    for implementation in (old.TerrainGrid, ci.TerrainGrid):
        with pytest.raises(ValueError, match="lowercase SHA256 required"):
            implementation(**dict(arguments, source_sha256="not-a-hash"))


def test_require_sha256_hex_lowercase_keeps_the_legacy_message():
    old = absorbed("contracts")._sha
    for value in ("0" * 64, "A" * 64, "", None, 5):
        if ci.is_sha256_hex(value):
            assert old(value) is None and ci.require_sha256_hex_lowercase(value) is None
        else:
            for call in (lambda: old(value), lambda: ci.require_sha256_hex_lowercase(value)):
                with pytest.raises(ValueError, match="^lowercase SHA256 required$"):
                    call()


def test_world_seed_module_matches_absorbed_names():
    old = absorbed("world_seed")
    assert old.WORLD_SEED == ci.WORLD_SEED
    assert old.SEED_DERIVATION == ci.SEED_DERIVATION
    for seed in SEEDS:
        for purpose in PURPOSES:
            assert old.derive_subseed(seed, purpose) == ci.seed_mountains_v1(seed, purpose)


def test_report_oracle_sources(capsys):
    """Print which tier every oracle came from, so the run itself documents it."""
    import collections
    counts = collections.Counter(ORACLE_SOURCES.values())
    live = sorted(rel for rel, tier in ORACLE_SOURCES.items() if tier == "LIVE")
    print("\noracle tiers:", dict(counts))
    print("oracle files read from the live tree:", len(live))
    for rel in live[:20]:
        print("   LIVE", rel)
    assert len(live) <= 12, live
