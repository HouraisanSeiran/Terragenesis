"""Cold-read, content-addressed, gated discharge products on small synthetic graphs."""

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, canonical_json, digest
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers import metric_network_discharge_product as module
from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
    ARRAY_NAMES, IDENTITY_FIELDS, MANIFEST_KEYS, METADATA_KEYS, PRODUCT_KEYS, SCHEMA,
    build_discharge_product, load_discharge_product, require_complete_discharge,
    save_discharge_product)


SOURCE_SHA = "65f64b61739bbffa597406e0e60127301ccf999eb14816b7876a062d70f99c59"


def graph(receiver, q=None, kinds=None, valid=None, unknown=None):
    rec = np.array([receiver], dtype=np.int64)
    shape = rec.shape
    local = np.ones(shape, np.float64) if q is None else np.array([q], np.float64)
    mask = np.ones(shape, bool) if valid is None else np.array([valid], bool)
    if kinds is None:
        labels = np.where(rec < 0, "retained", "interior")
    else:
        labels = np.array([kinds])
    seed = (np.zeros(shape, bool) if unknown is None
            else np.array([unknown], bool))
    return rec, local, mask, labels, seed


def build(receiver, **kwargs):
    options = {"q": None, "kinds": None, "valid": None, "unknown": None}
    options.update({key: kwargs.pop(key) for key in list(options) if key in kwargs})
    rec, local, mask, labels, seed = graph(receiver, **options)
    parameters = {"origin_native_cells": (12, 34), "world_seed": 20261020,
                  "interval_seconds": (0., 3600.), "source_sha256": SOURCE_SHA,
                  "forcing_semantics": "declared_rain_mm_h_scaled_local_input_m3_s"}
    parameters.update(kwargs)
    return build_discharge_product(rec, local, mask, labels, seed, **parameters)


def headers_for(shape, **overrides):
    """Canonical headers for a [z, x] shape; overrides replace one array's header."""
    return {name: overrides.get(name, (tuple(shape), module.ARRAY_DTYPES[name]))
            for name in ARRAY_NAMES}


def lying_path_class(manifest_size):
    """A Path whose manifest.json stat under-reports its size (a file that grew)."""
    base = type(Path())

    class LyingPath(base):
        def stat(self, *, follow_symlinks=True):
            real = super().stat(follow_symlinks=follow_symlinks)
            if self.name != "manifest.json":
                return real
            fields = list(real)
            fields[6] = int(manifest_size)
            return os.stat_result(fields)

    return LyingPath


class BoundedReader:
    """A binary stream that records every read size and refuses unbounded reads."""

    def __init__(self, stream, readings):
        self._stream = stream
        self._readings = readings

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self._stream.close()
        return False

    def read(self, size=-1):
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise AssertionError("unbounded read issued on a size-checked file")
        self._readings.append(size)
        return self._stream.read(size)


class ColdReadTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="discharge-product-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def published(self, name="product", receiver=None, **kwargs):
        if receiver is None:
            raise AssertionError("explicit receiver required")
        destination = self.root / name
        save_discharge_product(destination, build(receiver, **kwargs))
        return destination

    def edit_manifest(self, directory, mutate):
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        mutate(manifest)
        path.write_bytes(canonical_json(manifest).encode("utf-8"))

    def reseal(self, manifest):
        manifest["identity_sha256"] = digest(
            {name: manifest[name] for name in IDENTITY_FIELDS})

    def rewrite_arrays(self, directory, mutate):
        """Rewrite the payload the way an attacker would, array file digest included."""
        path = directory / "arrays.npz"
        with np.load(path, allow_pickle=False) as archive:
            arrays = {name: archive[name].copy() for name in archive.files}
        mutate(arrays)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ARRAY_NAMES:
                with archive.open(name + ".npy", "w") as stream:
                    np.lib.format.write_array(stream, arrays[name], allow_pickle=False)
        self.edit_manifest(directory, lambda manifest: manifest.__setitem__(
            "arrays_file_sha256", file_sha256(path)))
        return arrays

    # --- small synthetic graph coverage -------------------------------------

    def test_chain_and_y_and_unknown_reach_the_product(self):
        chain = build([1, 2, 3, -1])
        np.testing.assert_array_equal(chain["arrays"]["known_routed_q_m3_s"], [[1., 2., 3., 4.]])
        self.assertTrue(chain["arrays"]["complete_mask"].all())
        self.assertEqual(chain["metadata"]["ledger"]["residual_m3_s"], 0.)
        fork = build([2, 2, 3, -1])
        np.testing.assert_array_equal(fork["arrays"]["known_routed_q_m3_s"], [[1., 1., 3., 4.]])
        spread = build([2, 2, 3, -1, -1], unknown=[True, False, False, False, False])
        np.testing.assert_array_equal(spread["arrays"]["complete_mask"],
                                     [[False, True, False, False, True]])
        # cell 0 seeds unknown; it, the confluence and the downstream terminal inherit it.
        self.assertEqual(spread["metadata"]["counts"]["incomplete_valid_cells"], 3)
        self.assertEqual(spread["metadata"]["counts"]["unknown_upstream_seed_cells"], 1)

    def test_terminal_kinds_are_preserved_and_never_rewritten(self):
        product = build([1, -1, -1, -1], q=[2., 3., 7., 11.],
                        kinds=["interior", "open_outflow", "retained", "unknown_boundary"])
        arrays = product["arrays"]
        np.testing.assert_array_equal(arrays["terminal_kind"],
                                     [["interior", "open_outflow", "retained",
                                       "unknown_boundary"]])
        np.testing.assert_array_equal(arrays["terminal_q_m3_s"], [[0., 5., 7., 11.]])
        ledger = product["metadata"]["ledger"]
        self.assertEqual(ledger["retained_m3_s"], 7.)
        self.assertEqual(ledger["open_outflow_m3_s"], 5.)
        self.assertEqual(ledger["unknown_pending_m3_s"], 11.)
        self.assertEqual(ledger["input_total_m3_s"], 23.)

    def test_saved_product_reads_back_identical(self):
        built = build([2, 2, 3, -1, -1], unknown=[False, True, False, False, False])
        directory = self.root / "identical"
        save_discharge_product(directory, built)
        cold = load_discharge_product(directory)
        self.assertEqual(set(cold), set(PRODUCT_KEYS))
        self.assertEqual(cold["identity_sha256"], built["identity_sha256"])
        self.assertEqual(cold["metadata"], built["metadata"])
        self.assertEqual(cold["array_sha256"], built["array_sha256"])
        for name in ARRAY_NAMES:
            np.testing.assert_array_equal(cold["arrays"][name], built["arrays"][name])
            self.assertEqual(cold["arrays"][name].dtype, built["arrays"][name].dtype)
        self.assertFalse(cold["arrays"]["known_routed_q_m3_s"].flags.writeable)
        self.assertEqual(sorted(entry.name for entry in directory.iterdir()),
                         ["arrays.npz", "manifest.json"])

    def test_declared_identity_binds_every_input(self):
        base = build([1, 2, -1])
        variants = {
            "origin": {"origin_native_cells": (13, 34)},
            "seed": {"world_seed": 20261021},
            "interval": {"interval_seconds": (0., 1800.)},
            "spacing": {"spacing_m": 60.},
            "source": {"source_sha256": "0" * 64},
            "semantics": {"forcing_semantics": "declared_other"},
        }
        for name, change in variants.items():
            with self.subTest(field=name):
                other = build([1, 2, -1], **change)
                self.assertNotEqual(other["identity_sha256"], base["identity_sha256"])
                self.assertEqual(other["array_sha256"], base["array_sha256"])

    # --- tampering ----------------------------------------------------------

    def test_tampered_q_array_is_refused_even_when_resealed(self):
        directory = self.published("tampered-q", receiver=[1, 2, 3, -1], q=[1., 2., 3., 4.])
        self.rewrite_arrays(directory, lambda arrays: arrays["known_routed_q_m3_s"].__setitem__(
            (0, 3), 9.))
        with self.assertRaises(ValueError):
            load_discharge_product(directory)
        self.edit_manifest(directory, lambda manifest: manifest["array_sha256"].__setitem__(
            "known_routed_q_m3_s", "0" * 64))
        with self.assertRaises(ValueError):
            load_discharge_product(directory)

    def test_tampered_complete_mask_is_refused_after_resealing_digests(self):
        directory = self.published("tampered-complete", receiver=[2, 2, 3, -1],
                                   unknown=[True, False, False, False])
        arrays = self.rewrite_arrays(directory, lambda values: values["complete_mask"].__setitem__(
            (0, 0), True))

        def reseal(manifest):
            manifest["array_sha256"] = {name: array_hash(arrays[name]) for name in ARRAY_NAMES}
            manifest["metadata"]["counts"]["incomplete_valid_cells"] = int(
                (arrays["valid_mask"] & ~arrays["complete_mask"]).sum())
            self.reseal(manifest)

        self.edit_manifest(directory, reseal)
        with self.assertRaisesRegex(ValueError, "complete_mask"):
            load_discharge_product(directory)

    def test_tampered_terminal_q_is_refused_after_resealing_digests(self):
        directory = self.published("tampered-terminal-q", receiver=[1, -1], q=[2., 3.])
        arrays = self.rewrite_arrays(directory, lambda values: values["terminal_q_m3_s"].__setitem__(
            (0, 1), 4.))
        self.edit_manifest(directory, lambda manifest: (manifest.__setitem__(
            "array_sha256", {name: array_hash(arrays[name]) for name in ARRAY_NAMES}),
            manifest["metadata"]["ledger"].__setitem__("retained_m3_s", 4.),
            manifest["metadata"]["ledger"].__setitem__("residual_m3_s", -1.),
            self.reseal(manifest)))
        with self.assertRaises(ValueError):
            load_discharge_product(directory)

    def test_tampered_terminal_kind_is_refused(self):
        directory = self.published("tampered-terminal-kind", receiver=[1, -1], q=[2., 3.])
        self.rewrite_arrays(directory, lambda values: values["terminal_kind"].__setitem__(
            (0, 1), "open_outflow"))
        with self.assertRaises(ValueError):
            load_discharge_product(directory)

    def test_tampered_metadata_claims_are_refused(self):
        claims = {
            "hydraulic_ready": True, "publishable": True,
            "natural_outlet_certified": True,
            "topology_window_invariance_verified": True,
            "finite_graph_only": False,
        }
        for claim, value in claims.items():
            with self.subTest(claim=claim):
                name = "claim-" + claim
                directory = self.published(name, receiver=[1, -1])
                self.edit_manifest(directory, lambda manifest: (
                    manifest["metadata"].__setitem__(claim, value), self.reseal(manifest)))
                with self.assertRaises(ValueError):
                    load_discharge_product(directory)

    def test_tampered_ledger_and_policy_are_refused_after_resealing(self):
        for field, value in (("retained_m3_s", 999.), ("policy", "other-policy")):
            with self.subTest(field=field):
                directory = self.published("ledger-" + field, receiver=[1, -1], q=[2., 3.])

                def mutate(manifest, field=field, value=value):
                    if field == "policy":
                        manifest["metadata"]["policy"] = value
                    else:
                        manifest["metadata"]["ledger"][field] = value
                    self.reseal(manifest)

                self.edit_manifest(directory, mutate)
                with self.assertRaises(ValueError):
                    load_discharge_product(directory)

    def test_illegal_schema_and_missing_array_are_refused(self):
        schema = self.published("schema", receiver=[1, -1])
        self.edit_manifest(schema, lambda manifest: (manifest.__setitem__(
            "schema", "metric-network-discharge-product-v2"), self.reseal(manifest)))
        with self.assertRaises(ValueError):
            load_discharge_product(schema)
        missing = self.published("missing", receiver=[1, -1])
        self.edit_manifest(missing, lambda manifest: manifest["array_sha256"].pop("complete_mask"))
        with self.assertRaises(ValueError):
            load_discharge_product(missing)
        dropped = self.published("dropped", receiver=[1, -1])
        self.edit_manifest(dropped, lambda manifest: manifest.__setitem__(
            "status", "publishable"))
        with self.assertRaises(ValueError):
            load_discharge_product(dropped)

    def test_manifest_field_set_and_metadata_field_set_are_exact(self):
        directory = self.published("fields", receiver=[1, -1])
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest), set(MANIFEST_KEYS))
        self.assertEqual(set(manifest["metadata"]), set(METADATA_KEYS))
        self.edit_manifest(directory, lambda record: record.__setitem__("extra", 1))
        with self.assertRaises(ValueError):
            load_discharge_product(directory)
        extra = self.published("extra-metadata", receiver=[1, -1])
        self.edit_manifest(extra, lambda record: (record["metadata"].__setitem__("extra", 1),
                                                  self.reseal(record)))
        with self.assertRaises(ValueError):
            load_discharge_product(extra)

    def test_unexpected_directory_content_is_refused(self):
        directory = self.published("extra-file", receiver=[1, -1])
        (directory / "notes.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_discharge_product(directory)

    def test_manifest_json_hygiene_is_enforced(self):
        directory = self.published("hygiene", receiver=[1, -1])
        path = directory / "manifest.json"
        good = json.loads(path.read_text(encoding="utf-8"))
        text = canonical_json(good)
        duplicate = text[:-1] + ',"schema":"' + good["schema"] + '"}'
        for name, payload in (
                ("duplicate", duplicate.encode("utf-8")),
                ("nan", text.replace('"format_version":1',
                                     '"format_version":1,"extra":NaN').encode("utf-8")),
                ("utf8", b"\xff\xfe" + text.encode("utf-8")),
                ("empty", b""),
                ("truncated", text.encode("utf-8")[:-7])):
            with self.subTest(case=name):
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    load_discharge_product(directory)
        path.write_bytes(text.encode("utf-8"))
        load_discharge_product(directory)

    # --- publication discipline --------------------------------------------

    def test_existing_destination_is_never_overwritten(self):
        destination = self.published("taken", receiver=[1, -1], q=[2., 3.])
        before = (destination / "manifest.json").read_bytes()
        with self.assertRaises(FileExistsError):
            save_discharge_product(destination, build(receiver=[1, -1], q=[5., 6.]))
        self.assertEqual((destination / "manifest.json").read_bytes(), before)
        self.assertEqual(load_discharge_product(destination)["arrays"]["local_q_m3_s"].tolist(),
                         [[2., 3.]])

    def test_failed_publication_cleans_its_own_temporary_directory(self):
        destination = self.root / "never-published"
        with mock.patch.object(module, "load_discharge_product",
                               side_effect=ValueError("cold read failed")):
            with self.assertRaises(ValueError):
                save_discharge_product(destination, build([1, -1]))
        self.assertFalse(destination.exists())
        self.assertEqual(sorted(entry.name for entry in self.root.iterdir()), [])

    def test_save_rejects_arrays_that_contradict_their_digests(self):
        destination = self.root / "stale-identity"
        product = build([1, -1])
        product = dict(product)
        product["arrays"] = {name: np.array(value, copy=True) for name, value in product["arrays"].items()}
        product["arrays"]["known_routed_q_m3_s"][0, 0] = 99.
        with self.assertRaises(ValueError):
            save_discharge_product(destination, product)
        self.assertEqual(sorted(entry.name for entry in self.root.iterdir()), [])
        product["identity_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            save_discharge_product(destination, product)
        self.assertEqual(sorted(entry.name for entry in self.root.iterdir()), [])

    # --- declaration validation at build time -------------------------------

    def test_declared_parameters_are_validated(self):
        invalid = {
            "origin_native_cells": [(0,), (0.5, 0), (0, 0, 0), (True, 0), (0, False),
                                    (0.0, 0), (0, -1.5), (-1.0, 0)],
            "world_seed": [-1, True, 1.5, "20261020"],
            "interval_seconds": [(3600., 0.), (0., 0.), (0.,)],
            "spacing_m": [0., -30., float("inf"), float("nan")],
            "source_sha256": ["abc", SOURCE_SHA.upper(), "g" * 64, 12],
            "forcing_semantics": ["", "   ", None],
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    build([1, -1], **{field: value})

    def test_upstream_unknown_mask_cannot_be_omitted_or_defaulted(self):
        rec, local, mask, labels, _ = graph([1, -1])
        with self.assertRaises(TypeError):
            build_discharge_product(rec, local, mask, labels,
                                    origin_native_cells=(0, 0), world_seed=0,
                                    interval_seconds=(0., 1.), source_sha256=SOURCE_SHA,
                                    forcing_semantics="declared")
        with self.assertRaisesRegex(ValueError, "upstream_unknown_mask"):
            build_discharge_product(rec, local, mask, labels, None,
                                    origin_native_cells=(0, 0), world_seed=0,
                                    interval_seconds=(0., 1.), source_sha256=SOURCE_SHA,
                                    forcing_semantics="declared")
        with self.assertRaises(ValueError):
            build_discharge_product(rec, local, mask, labels, np.zeros(2),
                                    origin_native_cells=(0, 0), world_seed=0,
                                    interval_seconds=(0., 1.), source_sha256=SOURCE_SHA,
                                    forcing_semantics="declared")

    def test_build_does_not_mutate_the_shared_inputs(self):
        rec, local, mask, labels, seed = graph([1, 2, -1], q=[4., 5., 6.])
        copies = [value.copy() for value in (rec, local, mask, labels, seed)]
        product = build_discharge_product(rec, local, mask, labels, seed,
                                         origin_native_cells=(0, 0), world_seed=20261020,
                                         interval_seconds=(0., 3600.),
                                         source_sha256=SOURCE_SHA,
                                         forcing_semantics="declared")
        for original, copy in zip((rec, local, mask, labels, seed), copies):
            np.testing.assert_array_equal(original, copy)
        for name in ("receiver", "local_q_m3_s", "valid_mask", "upstream_unknown_mask"):
            self.assertFalse(product["arrays"][name].flags.writeable)
        self.assertIsNot(product["arrays"]["local_q_m3_s"].base, local)

    def test_two_dimensional_grid_round_trips_in_flat_index_order(self):
        # 3x3 [z,x]: two rows drain east into one open terminal in the last row.
        receiver = np.array([
            [1, 2, 5],
            [4, 5, 8],
            [-1, -1, -1]], np.int64)
        local = np.array([
            [1., 2., 1.],
            [3., 4., 5.],
            [0., 0., 7.]], np.float64)
        valid = np.array([
            [True, True, True],
            [True, True, True],
            [False, False, True]], bool)
        labels = np.array([
            ["interior", "interior", "interior"],
            ["interior", "interior", "interior"],
            ["inactive", "inactive", "open_outflow"]], "U24")
        seed = np.zeros(valid.shape, bool)
        product = build_discharge_product(
            receiver, local, valid, labels, seed, origin_native_cells=(4, 7),
            world_seed=20261020, interval_seconds=(0., 3600.),
            source_sha256=SOURCE_SHA, forcing_semantics="declared")
        np.testing.assert_array_equal(
            product["arrays"]["known_routed_q_m3_s"],
            [[1., 3., 4.], [3., 7., 16.], [0., 0., 23.]])
        self.assertEqual(product["metadata"]["shape_zx"], [3, 3])
        self.assertEqual(product["metadata"]["origin_native_cells"], [4, 7])
        directory = self.root / "two-dimensional"
        save_discharge_product(directory, product)
        cold = load_discharge_product(directory)
        np.testing.assert_array_equal(cold["arrays"]["terminal_kind"], labels)
        self.assertEqual(cold["metadata"]["ledger"]["retained_m3_s"], 0.)
        self.assertEqual(cold["metadata"]["ledger"]["open_outflow_m3_s"], 23.)
        self.assertEqual(cold["metadata"]["counts"]["valid_cells"], 7)
        mask = np.array([[True, True, True], [True, True, True], [False, False, True]], bool)
        self.assertEqual(require_complete_discharge(cold, mask).tolist(),
                         [1., 3., 4., 3., 7., 16., 23.])

    def test_cold_product_shares_no_memory_with_reloaded_arrays(self):
        directory = self.root / "no-sharing"
        save_discharge_product(directory, build([1, 2, -1], q=[4., 5., 6.]))
        cold = load_discharge_product(directory)
        with self.assertRaises(ValueError):
            cold["arrays"]["known_routed_q_m3_s"][0, 0] = -1.
        gate = require_complete_discharge(cold, np.ones(cold["arrays"]["valid_mask"].shape, bool))
        gate[0] = -1.
        self.assertEqual(
            require_complete_discharge(
                cold, np.ones(cold["arrays"]["valid_mask"].shape, bool)).tolist(),
            [4., 9., 15.])

    # --- signed world-coordinate origin ------------------------------------

    def test_negative_origin_components_are_accepted_and_bound(self):
        base = build([1, 2, -1])
        for origin in ((-1, 0), (0, -1), (-1, -2), (-9_000, 12),
                       (np.int64(-3), np.int64(0))):
            with self.subTest(origin=origin):
                product = build([1, 2, -1], origin_native_cells=origin)
                self.assertEqual(product["metadata"]["origin_native_cells"],
                                 [int(item) for item in origin])
                self.assertNotEqual(product["identity_sha256"], base["identity_sha256"])
                self.assertEqual(product["array_sha256"], base["array_sha256"])

    def test_negative_origin_survives_save_and_cold_read(self):
        for name, origin in (("negative-x", (-1, 0)), ("negative-z", (0, -7)),
                             ("negative-both", (-2, -3)),
                             ("cross-origin", (-1, -1))):
            with self.subTest(origin=origin):
                built = build([2, 2, 3, -1, -1], unknown=[True, False, False, False, False],
                              origin_native_cells=origin)
                directory = self.root / ("origin-" + name)
                save_discharge_product(directory, built)
                cold = load_discharge_product(directory)
                self.assertEqual(cold["metadata"]["origin_native_cells"], list(origin))
                self.assertEqual(cold["identity_sha256"], built["identity_sha256"])
                manifest = json.loads(
                    (directory / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["metadata"]["origin_native_cells"], list(origin))
                np.testing.assert_array_equal(cold["arrays"]["known_routed_q_m3_s"],
                                              built["arrays"]["known_routed_q_m3_s"])

    def test_grid_spanning_the_world_origin_round_trips(self):
        # origin (-1, -1) with a 3x3 [z,x] grid covers native cells z,x in {-1, 0, 1}:
        # the window straddles the world origin on both axes.
        receiver = np.array([[1, 2, 5], [4, 5, -1], [-1, -1, -1]], np.int64)
        local = np.array([[1., 2., 1.], [3., 4., 5.], [0., 0., 0.]], np.float64)
        valid = np.array([[True, True, True], [True, True, True],
                          [False, False, False]], bool)
        labels = np.array([["interior", "interior", "interior"],
                           ["interior", "interior", "retained"],
                           ["inactive", "inactive", "inactive"]], "U24")
        seed = np.zeros(valid.shape, bool)
        product = build_discharge_product(
            receiver, local, valid, labels, seed, origin_native_cells=(-1, -1),
            world_seed=20261020, interval_seconds=(0., 3600.),
            source_sha256=SOURCE_SHA, forcing_semantics="declared")
        # The window straddles the world origin on both axes; the only terminal
        # cell (index 5, kind "retained") carries the whole routed total 16 m3/s.
        np.testing.assert_array_equal(product["arrays"]["known_routed_q_m3_s"],
                                      [[1., 3., 4.], [3., 7., 16.], [0., 0., 0.]])
        self.assertEqual(product["metadata"]["ledger"]["retained_m3_s"], 16.)
        self.assertEqual(product["metadata"]["ledger"]["residual_m3_s"], 0.)
        self.assertEqual(product["metadata"]["origin_native_cells"], [-1, -1])
        directory = self.root / "origin-spanning"
        save_discharge_product(directory, product)
        cold = load_discharge_product(directory)
        self.assertEqual(cold["metadata"]["origin_native_cells"], [-1, -1])
        self.assertEqual(require_complete_discharge(
            cold, np.array([[True, True, True], [True, True, True],
                            [False, False, False]], bool)).tolist(),
            [1., 3., 4., 3., 7., 16.])

    def test_non_integer_origin_in_a_manifest_is_refused(self):
        invalid = {
            "float": [0.5, 0], "bool": [True, 0], "float-zero": [0, -1.0],
            "rank": [0, 0, 0], "text": ["0", 0], "null": [None, 0],
            "dict": {"z": 0, "x": 0}}
        for index, (name, value) in enumerate(invalid.items()):
            with self.subTest(case=name):
                directory = self.published("origin-type-" + str(index), receiver=[1, -1],
                                           origin_native_cells=(-1, 0))

                def mutate(manifest, value=value):
                    manifest["metadata"]["origin_native_cells"] = value
                    self.reseal(manifest)

                self.edit_manifest(directory, mutate)
                with self.assertRaises(ValueError):
                    load_discharge_product(directory)

    # --- coordinate order (x, z) --------------------------------------------

    def test_asymmetric_origin_keeps_x_first_order_through_cold_read(self):
        # origin_native_cells is (x, z) even though every array is indexed [z, x]:
        # an asymmetric pair must come back in the same order, never transposed.
        origin = (-3, 7)
        built = build([1, 2, -1], origin_native_cells=origin)
        self.assertEqual(built["metadata"]["origin_native_cells"], [-3, 7])
        directory = self.root / "origin-asymmetric"
        save_discharge_product(directory, built)
        cold = load_discharge_product(directory)
        self.assertEqual(cold["metadata"]["origin_native_cells"], [-3, 7])
        on_disk = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["metadata"]["origin_native_cells"], [-3, 7])
        # Order is part of the identity: transposing it is a different product.
        transposed = build([1, 2, -1], origin_native_cells=(7, -3))
        self.assertNotEqual(transposed["identity_sha256"], built["identity_sha256"])
        # And it is not the shape either: shape stays [z, x].
        self.assertEqual(cold["metadata"]["shape_zx"], [1, 3])

    # --- free-text declaration byte budget ----------------------------------

    def test_overlong_forcing_semantics_is_refused_at_build(self):
        with mock.patch.object(module, "MAX_TEXT_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "forcing_semantics"):
                build([1, -1], forcing_semantics="x" * 17)
            # A declaration that fits the same mock budget still builds.
            product = build([1, -1], forcing_semantics="x" * 16)
        self.assertEqual(product["metadata"]["forcing_semantics"], "x" * 16)

    def test_overlong_forcing_semantics_is_refused_at_cold_load(self):
        directory = self.published("long-semantics", receiver=[1, -1])
        self.edit_manifest(directory, lambda manifest: (
            manifest["metadata"].__setitem__("forcing_semantics", "x" * 131_072),
            self.reseal(manifest)))
        with self.assertRaisesRegex(ValueError, "forcing_semantics"):
            load_discharge_product(directory)

    def test_text_budget_counts_utf8_bytes_not_characters(self):
        # Four-byte characters: 5 of them are 20 bytes, so a 16-byte cap refuses
        # them even though the string is only 5 characters long.
        with mock.patch.object(module, "MAX_TEXT_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "UTF-8 bytes"):
                build([1, -1], forcing_semantics="\U0001f600" * 5)

    # --- strict format version -----------------------------------------------

    def test_format_version_must_be_the_integer_one(self):
        for index, value in enumerate((True, 1.0, "1", None)):
            with self.subTest(value=value):
                directory = self.published("version-" + str(index), receiver=[1, -1])
                self.edit_manifest(directory, lambda manifest, value=value: (
                    manifest.__setitem__("format_version", value), self.reseal(manifest)))
                with self.assertRaises(ValueError):
                    load_discharge_product(directory)
        honest = self.published("version-ok", receiver=[1, -1])
        self.assertIs(type(json.loads(
            (honest / "manifest.json").read_text(encoding="utf-8"))["format_version"]), int)
        load_discharge_product(honest)

    def test_build_and_save_refuse_a_non_integer_format_version(self):
        for value in (True, 1.0):
            with self.subTest(value=value):
                product = dict(build([1, -1]))
                product["format_version"] = value
                product["identity_sha256"] = digest(
                    {name: product[name] for name in IDENTITY_FIELDS})
                with self.assertRaisesRegex(ValueError, "format_version"):
                    save_discharge_product(self.root / ("bad-version-" + repr(value)), product)
                with self.assertRaisesRegex(ValueError, "format_version"):
                    require_complete_discharge(product, np.array([[True, True]]))
        self.assertEqual(sorted(entry.name for entry in self.root.iterdir()), [])

    # --- manifest metadata budget --------------------------------------------

    def test_manifest_beyond_the_metadata_budget_is_refused_before_any_read(self):
        directory = self.published("oversized-manifest", receiver=[1, -1])
        (directory / "manifest.json").write_bytes(b"{" + b" " * module.MAX_METADATA_BYTES)
        with mock.patch("builtins.open", side_effect=AssertionError(
                "an oversized manifest must be refused by stat, before any read")):
            with self.assertRaisesRegex(ValueError, "metadata byte budget"):
                load_discharge_product(directory)

    def test_manifest_that_grows_after_the_stat_is_refused_by_a_bounded_read(self):
        directory = self.published("grown-manifest", receiver=[1, -1])
        path = directory / "manifest.json"
        honest = path.read_bytes()
        path.write_bytes(honest + b" " * (module.MAX_METADATA_BYTES + 1 - len(honest)))
        readings = []
        real_open = open

        def bounded_opener(path_value, *arguments, **keywords):
            return BoundedReader(real_open(path_value, *arguments, **keywords), readings)

        with mock.patch.object(module, "Path", lying_path_class(len(honest))):
            with mock.patch("builtins.open", bounded_opener):
                with self.assertRaisesRegex(ValueError, "metadata byte budget"):
                    load_discharge_product(directory)
        # Exactly one bounded read, sized to one byte past the budget: the reader
        # never issues a read whose size it did not bound itself.
        self.assertEqual(readings, [module.MAX_METADATA_BYTES + 1])


class HeaderGateTests(unittest.TestCase):
    """The archive header gate refuses unsafe packages from headers alone."""

    def test_canonical_headers_pass(self):
        module._validate_headers(headers_for((2, 3)), (2, 3))

    def test_declared_grid_beyond_the_cell_budget_is_refused_from_headers(self):
        huge = (5_000, 4_000)
        self.assertGreater(huge[0] * huge[1], module.MAX_NETWORK_CELLS)
        with self.assertRaisesRegex(ValueError, "cell budget"):
            module._validate_headers(headers_for(huge), huge)

    def test_dimension_beyond_the_npy_header_limit_is_refused(self):
        tall = (module.MAX_DIMENSION + 1, 1)
        self.assertLess(tall[0], module.MAX_NETWORK_CELLS)
        with self.assertRaisesRegex(ValueError, "NPY header limit"):
            module._validate_headers(headers_for(tall), tall)

    def test_byte_budget_is_enforced_on_a_mocked_small_sample(self):
        with mock.patch.object(module, "MAX_BYTES", 64):
            with self.assertRaisesRegex(ValueError, "byte budget"):
                module._validate_headers(headers_for((2, 3)), (2, 3))
        module._validate_headers(headers_for((2, 3)), (2, 3))

    def test_headers_disagreeing_on_the_shape_are_refused(self):
        headers = headers_for(
            (2, 3), complete_mask=((2, 4), module.ARRAY_DTYPES["complete_mask"]))
        with self.assertRaisesRegex(ValueError, "disagree"):
            module._validate_headers(headers, (2, 3))

    def test_headers_differing_from_the_declared_shape_are_refused(self):
        with self.assertRaisesRegex(ValueError, "shape_zx"):
            module._validate_headers(headers_for((2, 3)), (3, 2))

    def test_wrong_dtype_rank_or_array_set_is_still_refused(self):
        cases = {
            "dtype": headers_for((2, 3), receiver=((2, 3), np.dtype(np.int32))),
            "rank": headers_for((2, 3), receiver=((6,), np.dtype(np.int64))),
            "zero": headers_for((2, 3), receiver=((0, 3), np.dtype(np.int64))),
            "negative": headers_for((2, 3), receiver=((2, -3), np.dtype(np.int64))),
        }
        missing = headers_for((2, 3))
        missing.pop("receiver")
        cases["missing"] = missing
        for name, headers in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                module._validate_headers(headers, (2, 3))


class ArchiveRejectionBeforeAllocationTests(unittest.TestCase):
    """Refusals come from the header gate, before any array is allocated."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="discharge-headers-"))
        self.directory = self.root / "product"
        save_discharge_product(self.directory, build([1, 2, -1]))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def rewrite_arrays(self, shapes):
        """Rewrite arrays.npz, reshaping some arrays and resealing its file digest."""
        path = self.directory / "arrays.npz"
        with np.load(path, allow_pickle=False) as archive:
            arrays = {name: archive[name].copy() for name in archive.files}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
            for name in ARRAY_NAMES:
                value = arrays[name]
                if name in shapes:
                    value = np.zeros(shapes[name], module.ARRAY_DTYPES[name])
                with target.open(name + ".npy", "w") as stream:
                    np.lib.format.write_array(stream, value, allow_pickle=False)
        manifest_path = self.directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["arrays_file_sha256"] = file_sha256(path)
        manifest_path.write_bytes(canonical_json(manifest).encode("utf-8"))

    def edit_manifest(self, mutate):
        path = self.directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        mutate(manifest)
        path.write_bytes(canonical_json(manifest).encode("utf-8"))

    def test_mismatched_array_shapes_are_refused_before_allocation(self):
        self.rewrite_arrays({"complete_mask": (1, 4)})
        with mock.patch.object(np, "load", side_effect=AssertionError(
                "no array may be allocated for a rejected archive")):
            with self.assertRaisesRegex(ValueError, "disagree"):
                load_discharge_product(self.directory)

    def test_declared_oversize_shape_is_refused_before_allocation(self):
        self.edit_manifest(lambda manifest: manifest["metadata"].__setitem__(
            "shape_zx", [5_000, 4_000]))
        with mock.patch.object(np, "load", side_effect=AssertionError(
                "no array may be allocated for a rejected archive")):
            with self.assertRaisesRegex(ValueError, "cell budget"):
                load_discharge_product(self.directory)

    def test_consistent_but_wrong_shape_is_refused_before_allocation(self):
        self.rewrite_arrays({name: (1, 4) for name in ARRAY_NAMES})
        with mock.patch.object(np, "load", side_effect=AssertionError(
                "no array may be allocated for a rejected archive")):
            with self.assertRaisesRegex(ValueError, "shape_zx"):
                load_discharge_product(self.directory)

    def test_an_honest_package_still_reloads(self):
        cold = load_discharge_product(self.directory)
        self.assertEqual(cold["metadata"]["shape_zx"], [1, 3])


class ConsumerGateTests(unittest.TestCase):
    def setUp(self):
        self.product = build([2, 2, 3, -1, -1], unknown=[True, False, False, False, False])
        self.shapes = self.product["arrays"]["valid_mask"].shape

    def requested(self, *columns):
        mask = np.zeros(self.shapes, bool)
        for column in columns:
            mask[0, column] = True
        return mask

    def test_requested_mask_shape_and_dtype_are_checked(self):
        for bad in ([[1, 0, 0, 0, 0]], np.zeros((2, 5), bool), np.zeros(5, bool),
                    np.zeros(self.shapes, np.int8), None, "mask"):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                require_complete_discharge(self.product, bad)
        with self.assertRaises(ValueError):
            require_complete_discharge(self.product, np.zeros(self.shapes, bool))

    def test_requested_invalid_cells_are_refused_not_zeroed(self):
        product = build([-1, -1], q=[1., 0.], kinds=["retained", "inactive"],
                        valid=[True, False])
        with self.assertRaisesRegex(ValueError, "invalid cells"):
            require_complete_discharge(product, np.array([[True, True]]))

    def test_requested_incomplete_cells_are_refused_not_zeroed(self):
        mask = self.requested(0, 1)
        with self.assertRaisesRegex(ValueError, "unknown upstream"):
            require_complete_discharge(self.product, mask)
        with self.assertRaisesRegex(ValueError, "unknown upstream"):
            require_complete_discharge(self.product, self.requested(0))

    def test_complete_request_returns_a_private_copy(self):
        mask = self.requested(1, 4)
        values = require_complete_discharge(self.product, mask)
        self.assertEqual(values.tolist(), [1., 1.])
        self.assertTrue(values.flags.writeable)
        values[0] = -1.
        self.assertEqual(
            require_complete_discharge(self.product, mask).tolist(), [1., 1.])
        self.assertFalse(np.shares_memory(values, self.product["arrays"]["known_routed_q_m3_s"]))

    def test_gate_rejects_an_inconsistent_product(self):
        stale = dict(self.product)
        stale["identity_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            require_complete_discharge(stale, self.requested(1))
        edited = dict(self.product)
        edited["arrays"] = dict(self.product["arrays"])
        edited["arrays"]["known_routed_q_m3_s"] = np.zeros(self.shapes, np.float64)
        with self.assertRaisesRegex(ValueError, "digest"):
            require_complete_discharge(edited, self.requested(2))
        claimed = dict(self.product)
        claimed["status"] = "publishable"
        with self.assertRaises(ValueError):
            require_complete_discharge(claimed, self.requested(1))
        # The shared product was never mutated by the gate.
        self.assertNotEqual(self.product["identity_sha256"], "0" * 64)
        self.assertEqual(
            require_complete_discharge(self.product, self.requested(1)).tolist(), [1.])

    def test_gate_does_not_certify_routing_or_hydraulics(self):
        metadata = self.product["metadata"]
        self.assertIs(metadata["finite_graph_only"], True)
        self.assertIs(metadata["topology_window_invariance_verified"], False)
        self.assertIs(metadata["natural_outlet_certified"], False)
        self.assertIs(metadata["hydraulic_ready"], False)
        self.assertIs(metadata["publishable"], False)
        self.assertEqual(metadata["schema"], SCHEMA)
        self.assertIn("declared unknown upstream", metadata["complete_definition"])

    # --- the gate recomputes; re-sealed derived arrays are still refused -----

    def forge(self, mutate):
        """Deep-copy the product, apply mutate, then re-seal digests and identity.

        This is exactly the bypass reported against the old ``recompute=False``
        gate: the forger has full control of the record and reseals everything a
        checksum-only reader would look at.
        """
        forged = copy.deepcopy(self.product)
        mutate(forged)
        forged["array_sha256"] = {name: array_hash(forged["arrays"][name])
                                  for name in ARRAY_NAMES}
        forged["identity_sha256"] = digest(
            {name: forged[name] for name in IDENTITY_FIELDS})
        return forged

    def test_gate_refuses_a_resealed_complete_mask(self):
        forged = self.forge(lambda product: (
            product["arrays"]["complete_mask"].__setitem__(slice(None), True),
            product["metadata"]["counts"].__setitem__("incomplete_valid_cells", 0)))
        with self.assertRaisesRegex(ValueError, "complete_mask"):
            require_complete_discharge(forged, self.requested(0))

    def test_gate_refuses_a_resealed_routed_q(self):
        forged = self.forge(lambda product: product["arrays"][
            "known_routed_q_m3_s"].__setitem__((0, 4), 99.))
        with self.assertRaisesRegex(ValueError, "known_routed_q_m3_s"):
            require_complete_discharge(forged, self.requested(4))

    def test_gate_refuses_resealed_counts_and_ledger(self):
        forged = self.forge(lambda product: (
            product["metadata"]["counts"].__setitem__("valid_cells", 0),
            product["metadata"]["ledger"].__setitem__("retained_m3_s", 0.)))
        with self.assertRaises(ValueError):
            require_complete_discharge(forged, self.requested(4))
        # Only the counts are falsified here: the gate still refuses.
        counts_only = self.forge(lambda product: product["metadata"]["counts"].__setitem__(
            "unknown_upstream_seed_cells", 0))
        with self.assertRaisesRegex(ValueError, "counts"):
            require_complete_discharge(counts_only, self.requested(4))

    def test_gate_still_accepts_the_honest_product_and_keeps_its_arrays(self):
        before = {name: self.product["arrays"][name].copy() for name in ARRAY_NAMES}
        self.assertEqual(require_complete_discharge(self.product, self.requested(4)).tolist(),
                         [1.])
        for name in ARRAY_NAMES:
            np.testing.assert_array_equal(self.product["arrays"][name], before[name])
        self.assertEqual(self.product["identity_sha256"],
                         digest({name: self.product[name] for name in IDENTITY_FIELDS}))


if __name__ == "__main__":
    unittest.main()

