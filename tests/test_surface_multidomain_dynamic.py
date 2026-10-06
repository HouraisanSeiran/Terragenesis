"""Fixed old prepared domains, independent forest accounts and static archive reads."""

from contextlib import ExitStack
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline import surface_fine_mosaic as mosaic
from terrain_pipeline import surface_multidomain_dynamic as forest
from terrain_pipeline.surface_domain_prepare import load_surface_domains
from tests.test_surface_dynamic_prepare import SAVED_DOMAIN_PATH, generation_disabled


def forcing(steps=8, pulse=False, raised=False):
    local = np.zeros((steps, 16))
    if pulse:
        local[0, 0] = 1.
        local[0, 8] = 2.
    tailwater = np.full((steps + 1, 2), 4.2)
    if raised:
        tailwater[1:, 1] = 5.1
    return dict(conductance_m2_s=np.full(14, .01), local_q_m3_s=local,
                tailwater_m=tailwater, dt_s=.1, max_depth_m=4.)


def propagation_forcing(raised=False):
    values = forcing(steps=80, pulse=True, raised=raised)
    values["conductance_m2_s"][:] = 1.
    values["dt_s"] = 1.
    return values


def mutable(record):
    return deepcopy(mosaic._plain(record))


def rehash(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = mosaic._identity(record)
    return record


def write_archive(record, path):
    arrays = {}
    tree = mosaic._tree(record, arrays)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", mosaic._json({"format_version": 1, "tree": tree,
                                                         "tree_sha256": mosaic._identity(tree)}))
        for name, array in arrays.items():
            stream = io.BytesIO()
            np.save(stream, array, allow_pickle=False)
            archive.writestr(name, stream.getvalue())


class SurfaceMultidomainDynamicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluation = load_surface_domains(SAVED_DOMAIN_PATH)

    def result(self, **overrides):
        values = forcing()
        values.update(overrides)
        return forest.prepare_surface_multidomain_dynamic(self.evaluation, **values)

    def test_complete_forest_and_independent_qv(self):
        result = self.result(**forcing(pulse=True))
        self.assertEqual(result["dynamic"]["status"], "completed")
        self.assertEqual(result["node_keys"].tolist(), [[domain, flat] for domain in (1, 2)
                          for flat in (9, 11, 16, 17, 23, 30, 37, 45)])
        self.assertEqual(result["node_offsets"].tolist(), [0, 8, 16])
        self.assertEqual(result["edge_offsets"].tolist(), [0, 7, 14])
        self.assertEqual(sum(len(item["wet_cell_ids"]) for item in result["bindings"]), 676)
        np.testing.assert_array_equal(result["dynamic"]["storage_m3"][0, [7, 15]], 0)
        np.testing.assert_allclose(result["dynamic"]["storage_m3"][0].sum(), 322)
        for step in range(result["dynamic"]["committed_steps"]):
            for index, start in enumerate((0, 8)):
                edge_start = index * 7
                edges = result["edges"][edge_start:edge_start + 7]
                before = result["dynamic"]["stage_m"][step]
                flux = .01 * (before[edges[:, 0]] - before[edges[:, 1]])
                np.testing.assert_allclose(flux, result["dynamic"]["qedges_m3_s"][step, edge_start:edge_start + 7])
                net = np.zeros(8)
                np.add.at(net, edges[:, 0] - start, -flux)
                np.add.at(net, edges[:, 1] - start, flux)
                before_storage = result["dynamic"]["storage_m3"][step, start:start + 8]
                after_storage = result["dynamic"]["storage_m3"][step + 1, start:start + 8]
                local = result["dynamic"]["inputs"]["local_q_m3_s"][step, start:start + 8]
                np.testing.assert_allclose(after_storage[:7], before_storage[:7] + .1 * (local[:7] + net[:7]), atol=1e-12)
                self.assertEqual(after_storage[7], 0)
                ledger = result["domain_ledger_m3"][step, index]
                np.testing.assert_allclose(ledger[:3], [before_storage.sum(), .1 * local[:7].sum(), -.1 * net[7]], atol=1e-12)
            np.testing.assert_allclose(result["domain_ledger_m3"][step].sum(axis=0),
                                       result["dynamic"]["ledger_m3"][step], atol=1e-12)

    def test_raised_tailwater_only_affects_second_domain(self):
        base = self.result(**forcing())
        raised = self.result(**forcing(raised=True))
        np.testing.assert_array_equal(base["dynamic"]["stage_m"][:, :8], raised["dynamic"]["stage_m"][:, :8])
        np.testing.assert_array_equal(base["dynamic"]["qedges_m3_s"][:, :7], raised["dynamic"]["qedges_m3_s"][:, :7])
        self.assertTrue(np.any(raised["dynamic"]["qedges_m3_s"][:, 7:] < 0))

    def test_pulse_propagates_independently(self):
        base = self.result(**propagation_forcing())
        raised = self.result(**propagation_forcing(raised=True))
        np.testing.assert_array_equal(base["dynamic"]["stage_m"][:, :8], raised["dynamic"]["stage_m"][:, :8])
        np.testing.assert_array_equal(base["dynamic"]["qedges_m3_s"][:, :7], raised["dynamic"]["qedges_m3_s"][:, :7])
        self.assertGreater(abs(base["dynamic"]["stage_m"][-1, 6] - self.result(**{
            **propagation_forcing(), "local_q_m3_s": np.zeros((80, 16))})["dynamic"]["stage_m"][-1, 6]), 1e-8)
        self.assertTrue(np.any(raised["dynamic"]["qedges_m3_s"][:, 7:] < 0))

    def test_static_reload_and_no_overwrite(self):
        result = self.result()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forest.npz"
            forest.save_surface_multidomain_dynamic(result, path)
            with self.assertRaises(FileExistsError):
                forest.save_surface_multidomain_dynamic(result, path)
            with ExitStack() as stack:
                generation_disabled(stack)
                stack.enter_context(patch("terrain_pipeline.surface_multidomain_dynamic.prepare_surface_multidomain_dynamic",
                                          side_effect=AssertionError("static read prepared")))
                stack.enter_context(patch("terrain_pipeline.surface_multidomain_dynamic._input",
                                          side_effect=AssertionError("static read rebuilt inputs")))
                loaded = forest.load_surface_multidomain_dynamic(path)
                query = forest.query_surface_multidomain_dynamic(loaded, state_index=2)
            self.assertEqual(query["time_s"], .2)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])

    def test_rehashed_mapping_and_binding_tamper(self):
        result = self.result()
        mutations = (
            lambda item: item["node_keys"].__setitem__((8, 0), 1),
            lambda item: item["node_offsets"].__setitem__(1, 7),
            lambda item: item["edges"].__setitem__((7, 1), 0),
            lambda item: item["bindings"].pop(),
            lambda item: item["bindings"].__setitem__(1, item["bindings"][0]),
            lambda item: item["bindings"][0]["area_m2"].__setitem__(0, 23.),
            lambda item: item["domain_ledger_m3"].__setitem__((0, 0, 1), 1.),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = mutable(result)
                mutation(changed)
                rehash(changed)
                with self.assertRaises(ValueError):
                    forest.validate_surface_multidomain_dynamic(changed)
        changed = mutable(result)
        changed["bindings"][0]["area_m2"][0] = 23.
        rehash(changed["bindings"][0])
        rehash(changed)
        with self.assertRaises(ValueError):
            forest.validate_surface_multidomain_dynamic(changed)
        changed = mutable(result)
        changed["domain_ids"][0] = 1.0
        rehash(changed)
        with self.assertRaises(ValueError):
            forest.validate_surface_multidomain_dynamic(changed)

    def test_bad_input_failure_cancel_resources(self):
        values = forcing()
        values["local_q_m3_s"][0, 0] = np.nan
        with self.assertRaises(ValueError):
            self.result(**values)
        with self.assertRaises(ValueError):
            self.result(**{**forcing(), "dt_s": 1e6})
        with self.assertRaises(ValueError):
            self.result(**{**forcing(), "resources": forest.ForestResources(max_wet_cells=500)})
        cancelled = self.result(**{**forcing(), "cancel": lambda: False})
        self.assertEqual(cancelled["dynamic"]["status"], "completed")
        calls = iter([False, False, True])
        cancelled = self.result(**{**forcing(), "cancel": lambda: next(calls)})
        self.assertEqual(cancelled["dynamic"]["status"], "cancelled")
        self.assertEqual(cancelled["dynamic"]["committed_steps"], 0)
        with self.assertRaises(InterruptedError):
            self.result(**{**forcing(), "cancel": lambda: True})
        values = forcing()
        values["tailwater_m"][2:, :] = 100.
        failed = self.result(**values)
        self.assertEqual(failed["dynamic"]["status"], "failed")
        self.assertEqual(failed["dynamic"]["committed_steps"], 1)
        self.assertEqual(failed["domain_ledger_m3"].shape[0], 1)
        with tempfile.TemporaryDirectory() as directory:
            for name, record in (("cancelled", cancelled), ("failed", failed)):
                path = Path(directory) / (name + ".npz")
                forest.save_surface_multidomain_dynamic(record, path)
                with ExitStack() as stack:
                    generation_disabled(stack)
                    loaded = forest.load_surface_multidomain_dynamic(path)
                self.assertEqual(loaded["dynamic"]["committed_steps"], record["dynamic"]["committed_steps"])

    def test_atomic_publish_failure_cleans_temporary(self):
        result = self.result()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forest.npz"
            with patch("terrain_pipeline.surface_multidomain_dynamic.os.link", side_effect=OSError("publish failed")):
                with self.assertRaises(OSError):
                    forest.save_surface_multidomain_dynamic(result, path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_archive_rejects_extra_and_object_array(self):
        result = self.result()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.npz"
            write_archive(result, path)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("extra.npy", b"extra")
            with self.assertRaises(ValueError):
                forest.load_surface_multidomain_dynamic(path)
            path2 = Path(directory) / "object.npz"
            write_archive(result, path2)
            with zipfile.ZipFile(path2) as source:
                members = [(info.filename, source.read(info)) for info in source.infolist()]
            with zipfile.ZipFile(path2, "w") as archive:
                for name, content in members:
                    if name == "array_00000.npy":
                        stream = io.BytesIO()
                        np.save(stream, np.array([object()]), allow_pickle=True)
                        content = stream.getvalue()
                    archive.writestr(name, content)
            with self.assertRaises(ValueError):
                forest.load_surface_multidomain_dynamic(path2)
