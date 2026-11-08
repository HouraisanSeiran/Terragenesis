"""Focused checks for geometric support, conservation and static rejection."""

from terrain_pipeline.surface_identity import _plain as _merged_mosaic__plain

from contextlib import ExitStack
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline import surface_domain as mosaic
from terrain_pipeline import surface_domain as forest
from terrain_pipeline import surface_domain as storage
from tests.test_surface_dynamic_prepare import generation_disabled
from tests.test_surface_multidomain_dynamic import forcing

SOURCE = Path(__file__).resolve().parents[1] / "verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/pulse.npz"


def propagation_forcing(*, pulse=False, raised=False):
    values = forcing(steps=80, pulse=pulse, raised=raised)
    values["conductance_m2_s"][:] = 1.
    return values


@lru_cache(maxsize=1)
def fixture():
    source = forest.load_surface_multidomain_dynamic(SOURCE)
    base = storage.prepare_surface_variable_storage(source, **propagation_forcing())
    pulse = storage.prepare_surface_variable_storage(source, **propagation_forcing(pulse=True))
    raised = storage.prepare_surface_variable_storage(source, **propagation_forcing(pulse=True, raised=True))
    return source, base, pulse, raised


def rehashed(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = mosaic._identity(record)
    return record


def static_disabled(stack):
    generation_disabled(stack)
    for name in ("_geometry", "_knots", "_advance", "prepare_surface_variable_storage"):
        stack.enter_context(patch.object(storage, name, side_effect=AssertionError("generation on read")))


class SurfaceVariableStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.base, cls.pulse, cls.raised = fixture()

    def test_source_triangles_and_nonconstant_storage(self):
        result = self.base
        self.assertEqual(result["support_offsets"][-1], 676 * 6)
        self.assertEqual(len(result["source"]["node_keys"]), 16)
        self.assertEqual(len(result["source"]["edges"]), 14)
        self.assertEqual(result["source"]["dynamic"]["inputs"]["boundary_mask"].sum(), 2)
        self.assertAlmostEqual(result["storage_m3"][0].sum(), 224.5721879136545)
        self.assertNotAlmostEqual(result["storage_m3"][0].sum(), 322.)
        for index in range(16):
            start, stop = result["support_offsets"][index:index + 2]
            beds = result["support_bed_m"][start:stop]
            weights = result["support_weight_m2"][start:stop]
            first, last = result["knot_offsets"][index:index + 2]
            np.testing.assert_allclose(result["knot_volume_m3"][first:last],
                                       [storage.volume(stage, beds, weights) for stage in result["knot_stage_m"][first:last]])
            self.assertEqual(storage._invert(0., beds, weights), beds.min())
            for amount in (0.1, 1., 10.):
                self.assertAlmostEqual(storage.volume(storage._invert(amount, beds, weights), beds, weights), amount)

    def test_ledger_and_domain_independence(self):
        raised = self.raised
        np.testing.assert_array_equal(self.pulse["stage_m"][:, :8], raised["stage_m"][:, :8])
        np.testing.assert_array_equal(self.pulse["qedges_m3_s"][:, :7], raised["qedges_m3_s"][:, :7])
        self.assertTrue(np.any(raised["qedges_m3_s"][:, 7:] < 0))
        np.testing.assert_allclose(raised["ledger_m3"], raised["domain_ledger_m3"].sum(axis=1), atol=1e-12)
        self.assertLess(np.abs(raised["ledger_m3"][:, 5]).max(), 1e-10)
        self.assertEqual(self.pulse["committed_steps"], 80)
        self.assertEqual(self.pulse["time_s"][-1], 8.)
        self.assertGreater(abs(self.pulse["stage_m"][-1, 6] - self.base["stage_m"][-1, 6]), 1e-12)

    def test_failed_cancelled_and_negative_storage(self):
        values = forcing()
        values["tailwater_m"][2:] = 100.
        failed = storage.prepare_surface_variable_storage(self.source, **values)
        self.assertEqual((failed["status"], failed["committed_steps"]), ("failed", 1))
        values = forcing()
        values["local_q_m3_s"][0, 0] = -1e6
        negative = storage.prepare_surface_variable_storage(self.source, **values)
        self.assertEqual((negative["status"], negative["committed_steps"], negative["failed_step"]["reason"]),
                         ("failed", 0, "negative_storage"))
        calls = iter([True])
        cancelled = storage.prepare_surface_variable_storage(self.source, **forcing(), cancel=lambda: next(calls))
        self.assertEqual((cancelled["status"], cancelled["committed_steps"]), ("cancelled", 0))
        with ExitStack() as stack:
            static_disabled(stack)
            for record in (failed, negative, cancelled):
                storage.validate_surface_variable_storage(record)
                storage.query_surface_variable_storage(record)
        for record in (failed, cancelled):
            changed = deepcopy(_merged_mosaic__plain(record))
            changed["committed_steps"] += 1
            with self.assertRaises(ValueError):
                storage.validate_surface_variable_storage(rehashed(changed))
        changed = deepcopy(_merged_mosaic__plain(failed))
        changed["failed_step"]["reason"] = "negative_storage"
        with self.assertRaises(ValueError):
            storage.validate_surface_variable_storage(rehashed(changed))
        with self.assertRaises(ValueError):
            storage.prepare_surface_variable_storage(self.source, **{**forcing(), "dt_s": 1e6})

    def test_static_read_and_rehashed_forgery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storage.npz"
            storage.save_surface_variable_storage(self.base, path)
            with self.assertRaises(FileExistsError):
                storage.save_surface_variable_storage(self.base, path)
            with ExitStack() as stack:
                static_disabled(stack)
                storage.validate_surface_variable_storage(self.base)
                loaded = storage.load_surface_variable_storage(path)
                query = storage.query_surface_variable_storage(loaded, state_index=1)
            self.assertEqual(query["time_s"], .1)
            self.assertEqual(loaded["identity_sha256"], self.base["identity_sha256"])
        for name in ("support_bed_m", "support_weight_m2", "knot_volume_m3", "stage_m", "storage_m3",
                     "qedges_m3_s", "ledger_m3", "domain_ledger_m3"):
            changed = deepcopy(_merged_mosaic__plain(self.base))
            changed[name].flat[0] += 1
            changed.pop("identity_sha256")
            changed["identity_sha256"] = mosaic._identity(changed)
            with self.subTest(name=name), self.assertRaises(ValueError):
                storage.validate_surface_variable_storage(changed)

    def test_resources_before_geometry_or_source_validation(self):
        for resources in (storage.StorageResources(max_work=1),
                          storage.StorageResources(max_wet_cells=1),
                          storage.StorageResources(max_retained_bytes=1),
                          storage.StorageResources(max_working_bytes=1)):
            with patch.object(storage, '_surface_variable_storage_geometry', side_effect=AssertionError("geometry before budget")), \
                    patch.object(forest, "validate_surface_multidomain_dynamic",
                                 side_effect=AssertionError("source validation before budget")):
                with self.assertRaises(ValueError):
                    storage.prepare_surface_variable_storage(self.source, **forcing(), resources=resources)
                changed = deepcopy(_merged_mosaic__plain(self.base))
                changed["resources"] = vars(resources)
                with self.assertRaises(ValueError):
                    storage.validate_surface_variable_storage(rehashed(changed))

    def test_scalar_dtype_stage_and_prefix_rejections(self):
        for name, value in (("committed_steps", 80.), ("committed_steps", True),
                            ("dt_s", True), ("max_depth_m", 4),
                            ("natural_outlets_certified", 0), ("full_dynamic_wave_prepared", 0)):
            changed = deepcopy(_merged_mosaic__plain(self.base))
            changed[name] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                storage.validate_surface_variable_storage(rehashed(changed))
        for name in ("storage_m3", "support_offsets", "support_owner", "stage_m"):
            changed = deepcopy(_merged_mosaic__plain(self.base))
            changed[name] = changed[name].astype(np.float32)
            with self.subTest(name=name), self.assertRaises(ValueError):
                storage.validate_surface_variable_storage(rehashed(changed))
        for amount in (-1., float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                storage._invert(amount, np.array([0.]), np.array([1.]))
        for value in (True, np.bool_(True), np.float64(.1), "0.1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage.prepare_surface_variable_storage(self.source, **{**forcing(), "dt_s": value})
        changed = deepcopy(_merged_mosaic__plain(self.base))
        changed["storage_m3"][1, 0] = -1e-15
        with self.assertRaises(ValueError):
            storage.validate_surface_variable_storage(rehashed(changed))
        changed = deepcopy(_merged_mosaic__plain(self.base))
        changed["stage_m"][1, 0] = -100.
        with self.assertRaises(ValueError):
            storage.validate_surface_variable_storage(rehashed(changed))
        changed = deepcopy(_merged_mosaic__plain(self.base))
        minimum = changed["support_bed_m"][:changed["support_offsets"][1]].min()
        changed["stage_m"][1, 0] = minimum + 1e-14
        changed["storage_m3"][1, 0] = 0.
        with self.assertRaises(ValueError):
            storage.validate_surface_variable_storage(rehashed(changed))
        for name in ("local_q_m3_s", "tailwater_m", "stage_m", "ledger_m3"):
            changed = deepcopy(_merged_mosaic__plain(self.base))
            changed[name].flat[0] = float("inf")
            with self.subTest(nonfinite=name), self.assertRaises(ValueError):
                storage.validate_surface_variable_storage(changed)
        with self.assertRaises(ValueError):
            storage.query_surface_variable_storage(self.base, state_index=True)

    def test_strict_archive_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.npz"
            storage.save_surface_variable_storage(self.base, original)
            with zipfile.ZipFile(original) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for mutation in ("version_float", "version_bool", "shape_float", "shape_bool",
                             "header_bool", "header_float", "fortran_int", "duplicate_header", "unused"):
                payloads = dict(members)
                manifest = json.loads(payloads["manifest.json"])
                reference = manifest["tree"]["support_bed_m"]
                if mutation.startswith("version"):
                    manifest["format_version"] = True if mutation == "version_bool" else 1.
                elif mutation.startswith("shape"):
                    reference["shape"][0] = True if mutation == "shape_bool" else float(reference["shape"][0])
                elif mutation == "unused":
                    payloads["array_unused.npy"] = payloads[reference["$array"]]
                else:
                    name = reference["$array"]
                    raw = payloads[name]
                    header_length = int.from_bytes(raw[8:10], "little")
                    header = raw[10:10 + header_length].decode("latin1").strip()
                    if mutation == "fortran_int":
                        header = header.replace("False", "0")
                    elif mutation == "duplicate_header":
                        header = header.replace("{", "{'fortran_order': False, ", 1)
                    else:
                        size = reference["shape"][0]
                        header = header.replace(f"({size},)", "(True,)" if mutation == "header_bool" else f"({size}.0,)")
                    encoded = (header + "\n").encode("latin1")
                    payloads[name] = raw[:8] + len(encoded).to_bytes(2, "little") + encoded + raw[10 + header_length:]
                manifest["tree_sha256"] = mosaic._identity(manifest["tree"])
                payloads["manifest.json"] = mosaic._surface_fine_mosaic_json(manifest).encode("utf8")
                path = Path(directory) / (mutation + ".npz")
                with zipfile.ZipFile(path, "w") as archive:
                    for name, payload in payloads.items():
                        archive.writestr(name, payload)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    storage.load_surface_variable_storage(path)

    def test_atomic_race_does_not_overwrite_or_leave_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "race.npz"
            original_link = storage.os.link
            def race(source, target):
                Path(target).write_bytes(b"other writer")
                return original_link(source, target)
            with patch.object(storage.os, "link", side_effect=race), self.assertRaises(FileExistsError):
                storage.save_surface_variable_storage(self.base, destination)
            self.assertEqual(destination.read_bytes(), b"other writer")
            self.assertEqual(list(Path(directory).iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
