"""Fixed accepted two-domain end-to-end engineering preparation."""

from terrain_pipeline.surface_identity import _plain as _merged_coast__plain
from terrain_pipeline.surface_identity import _freeze as _merged_coast__freeze

from copy import deepcopy
from contextlib import ExitStack
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline import surface_domain as coast
from terrain_pipeline import surface_domain as engineering
from terrain_pipeline import surface_domain as mosaic
from terrain_pipeline import surface_domain as forest
from terrain_pipeline.surface_domain import load_surface_domains
from terrain_pipeline.surface_domain import _payload
from tests.test_surface_multidomain_dynamic import forcing


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz"
SOURCE_SHA256 = "dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af"
VARIABLE_SOURCE = ROOT / "verification/surface-variable-storage/run-20260930T192708.659151Z/pulse.npz"
VARIABLE_SHA256 = "392ea3fad66827fa8a3acd43301627b86ca6a4a186ea9994a2d34b32322e6c63"


def outlet_inputs(prepared, domain_id):
    datum = prepared["candidate"]["inputs"]["vertical_datum"]
    left = 38. if domain_id == 1 else 108.
    section = np.column_stack((np.arange(left, left + 4), np.full(4, 70.)))
    attachment = coast.RiverAttachment(prepared, domain_id, section, 2, datum)
    recovery = next(item["recovery"] for item in prepared["domains"] if item["domain_id"] == domain_id)
    payload = _payload(recovery)
    fine = recovery["inputs"]["fine"]
    row = round((70. - fine["origin_z_m"]) / fine["spacing_z_m"])
    column = round((left - fine["origin_x_m"]) / fine["spacing_x_m"])
    bed_start = payload["final_surface_m"][row, column:column + 4]
    water_start = payload["water_surface_m"][row, column:column + 4]
    h0_start = payload["source_surface_m"][row, column:column + 4]
    stations = np.arange(70., 91.)
    fraction = np.linspace(0., 1., len(stations))[:, None]
    bed = (1 - fraction) * bed_start + fraction * -.5
    water = (1 - fraction) * water_start
    h0 = (1 - fraction) * h0_start + fraction * -.25
    shape = bed.shape
    corridor = coast.EngineeringSource(
        "corridor", "explicit-synthetic-domain-%d-corridor" % domain_id, datum,
        left, 70., 1., 1., h0, bed, water, np.ones(shape, bool), np.zeros(shape, bool),
        np.zeros(shape, bool), np.ones(shape, bool), np.zeros(shape, bool), 0.)
    sea_shape = (2, 4)
    sea = coast.EngineeringSource(
        "sea", "explicit-synthetic-domain-%d-sea" % domain_id, datum,
        left, 90., 1., 1., np.full(sea_shape, -.25), np.full(sea_shape, -.5),
        np.zeros(sea_shape), np.ones(sea_shape, bool), np.zeros(sea_shape, bool),
        np.zeros(sea_shape, bool), np.ones(sea_shape, bool), np.ones(sea_shape, bool), 0.)
    return {"attachment": attachment, "corridor": corridor, "sea": sea,
            "stations_z_m": stations, "budget": coast.DropBudget(4., 100.)}


@lru_cache(maxsize=1)
def constant_fixture():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise AssertionError("fixed accepted source changed")
    evaluation = load_surface_domains(SOURCE)
    outlets = {domain_id: outlet_inputs(evaluation, domain_id) for domain_id in (1, 2)}
    result = engineering.prepare_surface_engineering(evaluation, outlets, **forcing(steps=80, pulse=True))
    return evaluation, outlets, result


class SurfaceEngineeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluation, cls.outlets, cls.result = constant_fixture()

    def test_full_real_entrance_and_domains(self):
        result = self.result
        self.assertEqual(list(result["domain_ids"]), [1, 2])
        self.assertEqual(result["domain_mosaic"]["grid"]["bbox_xz_m"], (10., 140., 10., 70.))
        self.assertTrue(result["declared_node_envelope_complete"])
        for name in ("physical_footprint_complete", "natural_outlets_certified", "full_dynamic_wave_prepared", "ready_for_3d"):
            self.assertFalse(result[name])
        self.assertEqual(len(result["dynamic_forest"]["node_keys"]), 16)
        self.assertEqual(len(result["dynamic_forest"]["edges"]), 14)
        self.assertEqual(int(result["dynamic_forest"]["dynamic"]["inputs"]["boundary_mask"].sum()), 2)
        for domain_id, drop in zip((1, 2), result["drops"]):
            self.assertEqual(drop["inputs"]["attachment"]["domain_id"], domain_id)
            self.assertAlmostEqual(drop["attachment"]["terminal_q_m3_s"], .200049)
            np.testing.assert_allclose(drop["attachment"]["river_water_xyz_m"][:, 1],
                                       _payload(next(item["recovery"] for item in self.evaluation["domains"]
                                                     if item["domain_id"] == domain_id))["water_surface_m"][-1, 28:32])
        self.assertEqual(self.result["drops"][1]["attachment"]["terminal_node"],
                         self.result["drops"][0]["attachment"]["terminal_node"])

    def test_missing_duplicate_mixed_and_wrong_outlet_rejected(self):
        with self.assertRaises(ValueError):
            engineering.prepare_surface_engineering(self.evaluation, {1: self.outlets[1]}, **forcing())
        with self.assertRaises(ValueError):
            engineering.compose_surface_engineering(self.evaluation, self.result["domain_mosaic"],
                                                    [self.result["drops"][0]] * 2, self.result["dynamic_forest"])
        bad = dict(self.outlets)
        bad[2] = {**bad[2], "attachment": self.outlets[1]["attachment"]}
        with self.assertRaises(ValueError):
            engineering.prepare_surface_engineering(self.evaluation, bad, **forcing())
        for change in ("datum", "sea", "budget"):
            supplied = dict(self.outlets[2])
            if change == "datum":
                supplied["sea"] = replace(supplied["sea"], datum="wrong")
            elif change == "sea":
                supplied["sea"] = replace(supplied["sea"], sea_level_m=5., water_m=np.full((2, 4), 5.))
            else:
                supplied["budget"] = coast.DropBudget(0., 0.)
            with self.subTest(change=change), self.assertRaises(ValueError):
                engineering.prepare_surface_engineering(self.evaluation, {1: self.outlets[1], 2: supplied}, **forcing())

    def test_static_roundtrip_and_atomic_nooverwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "engineering.npz"
            engineering.save_surface_engineering(self.result, path)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                engineering.save_surface_engineering(self.result, path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with patch.object(engineering, "prepare_surface_engineering", side_effect=AssertionError("prepared")), \
                 patch.object(mosaic, "prepare_domain_mosaic", side_effect=AssertionError("mosaic")), \
                 patch.object(coast, "prepare_coast_drop", side_effect=AssertionError("drop")), \
                 patch.object(forest, "prepare_surface_multidomain_dynamic", side_effect=AssertionError("advanced")), \
                 ExitStack() as stack:
                for target in ('terrain_pipeline.surface_domain.recover_surface_network',
                               'terrain_pipeline.surface_domain._replay',
                               'terrain_pipeline.surface_domain._fine_source',
                               'terrain_pipeline.surface_domain.evaluate_surface_domains',
                               'terrain_pipeline.surface_domain.bind_surface_dynamic_source',
                               'terrain_pipeline.surface_hydraulics.evaluate'):
                    stack.enter_context(patch(target, side_effect=AssertionError("generation")))
                for name in ("_assemble",):
                    stack.enter_context(patch.object(mosaic, name, side_effect=AssertionError("assembled")))
                for name in ("_attachment", "_sample", "_stencil"):
                    stack.enter_context(patch.object(coast, name, side_effect=AssertionError("sampled")))
                loaded = engineering.load_surface_engineering(path)
                queried = engineering.query_surface_engineering(loaded)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])
            self.assertEqual(len(queried["outlets"]), 2)
            with self.assertRaises(ValueError):
                loaded["drops"][0]["arrays"]["bed_xyz_m"].setflags(write=True)
            self.assertEqual(queried["node_graph"]["edges"].shape, (14, 2))
            self.assertEqual(queried["surface_geometry"]["triangles"].shape, (15600, 3))
            self.assertEqual(queried["dynamic"]["stage_m"].shape, (81, 16))

    def test_strict_selectors_and_resources(self):
        for value in (True, 1., -1, 81):
            with self.subTest(value=value), self.assertRaises(ValueError):
                engineering.query_surface_engineering(self.result, state_index=value)
        with self.assertRaises(ValueError):
            engineering.query_surface_engineering(self.result, variable_state_index=0)
        for value in (True, 1024.):
            with self.assertRaises(ValueError):
                engineering.EngineeringResources(max_retained_bytes=value)

    def test_generated_resource_rejected_before_prepare(self):
        input_size = engineering._size({"evaluation": self.evaluation})
        with patch.object(mosaic, "prepare_domain_mosaic", side_effect=AssertionError("allocated")), \
             self.assertRaises(ValueError):
            engineering.prepare_surface_engineering(self.evaluation, self.outlets,
                resources=engineering.EngineeringResources(max_retained_bytes=input_size * 5), **forcing())

    def test_archive_preflight_rejects_before_array_load(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.npz"
            engineering.save_surface_engineering(self.result, original)
            for mode in ("duplicate", "compressed", "object", "shape", "bool-shape"):
                path = Path(directory) / (mode + ".npz")
                with zipfile.ZipFile(original) as source, zipfile.ZipFile(path, "w") as target:
                    metadata = json.loads(source.read("metadata.json"))
                    def reference(value):
                        if isinstance(value, dict):
                            if "$array" in value:
                                return value
                            for child in value.values():
                                found = reference(child)
                                if found is not None:
                                    return found
                        elif isinstance(value, list):
                            for child in value:
                                found = reference(child)
                                if found is not None:
                                    return found
                        return None
                    spec = reference(metadata["tree"])
                    if mode == "shape":
                        spec["shape"] = [1000001]
                    elif mode == "bool-shape":
                        spec["shape"] = [True]
                    elif mode == "object":
                        spec["dtype"] = "|O"
                    target.writestr("metadata.json", json.dumps(metadata),
                                    compress_type=zipfile.ZIP_DEFLATED if mode == "compressed" else zipfile.ZIP_STORED)
                    for name in source.namelist():
                        if name != "metadata.json":
                            target.writestr(name, source.read(name))
                    if mode == "duplicate":
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            target.writestr("metadata.json", "{}")
                with self.subTest(mode=mode), patch.object(np, "load", side_effect=AssertionError("allocated")), \
                     self.assertRaises(ValueError):
                    engineering.load_surface_engineering(path)

    def test_strict_npy_headers_before_load(self):
        headers = ["{'descr':'<f8','fortran_order':False,'shape':(1.0,)}",
                   "{'descr':'<f8','fortran_order':False,'shape':(True,)}",
                   "{'descr':'<f8','fortran_order':0,'shape':(1,)}",
                   "{'descr':'<f8','fortran_order':False,'shape':(1,),'shape':(1,)}"]
        with tempfile.TemporaryDirectory() as directory:
            for index, header in enumerate(headers):
                path = Path(directory) / (str(index) + ".npz")
                raw = header.encode("latin1") + b"\n"
                payload = b"\x93NUMPY\x01\x00" + len(raw).to_bytes(2, "little") + raw + b"\x00" * 8
                spec = {"$array": "array_0.npy", "shape": [1], "dtype": "<f8", "sha256": "0" * 64}
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("metadata.json", json.dumps({"format": engineering.SURFACE_ENGINEERING_PREPARE_VERSION + "-npy-v1",
                        "tree": {"resources": {}, "array": spec}}))
                    archive.writestr("array_0.npy", payload)
                with self.subTest(header=header), patch.object(np, "load", side_effect=AssertionError("allocated")), \
                     self.assertRaises(ValueError):
                    engineering.load_surface_engineering(path)

    def test_coherent_nested_outlet_forgery_rejected(self):
        for field, value in (("terminal_q_m3_s", .4), ("terminal_node", 45.),
                             ("terminal_node", True)):
            plain = deepcopy(_merged_coast__plain(self.result))
            drop = plain["drops"][1]
            drop["attachment"][field] = value
            drop["identity_sha256"] = coast.fingerprint({key: item for key, item in drop.items()
                                                         if key != "identity_sha256"})
            plain["identity_sha256"] = coast.fingerprint({key: item for key, item in plain.items()
                                                          if key != "identity_sha256"})
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                engineering.validate_surface_engineering(_merged_coast__freeze(plain))

    def test_static_saved_mosaic_coherent_forgery_rejected(self):
        from tests.test_surface_variable_storage import static_disabled
        for field in ("h0_m", "h2_m", "weights", "summary"):
            plain = deepcopy(_merged_coast__plain(self.result))
            mesh = plain["domain_mosaic"]
            if field in ("h0_m", "h2_m"):
                mesh["nodes"][field][0] += .25
            elif field == "weights":
                mesh["contributors"]["weights"][0, 0, 0] += .25
            else:
                mesh["summary"]["actual_wet_water_volume_m3"] += 1.
            mesh["identity_sha256"] = coast.fingerprint({key: item for key, item in mesh.items()
                                                         if key != "identity_sha256"})
            plain["identity_sha256"] = coast.fingerprint({key: item for key, item in plain.items()
                                                          if key != "identity_sha256"})
            with self.subTest(field=field), ExitStack() as stack:
                static_disabled(stack)
                with self.assertRaises(ValueError):
                    engineering.validate_surface_engineering(_merged_coast__freeze(plain))

    def test_frozen_bundle_static_full_generation_guard(self):
        from tests.test_surface_variable_storage import static_disabled
        frozen = ROOT / "verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz"
        before = hashlib.sha256(frozen.read_bytes()).hexdigest()
        with ExitStack() as stack:
            static_disabled(stack)
            stack.enter_context(patch.object(mosaic, "_assemble", side_effect=AssertionError("assembly")))
            loaded = engineering.load_surface_engineering(frozen)
            query = engineering.query_surface_engineering(loaded)
        self.assertEqual(loaded["identity_sha256"], "381e60743e03cee6859c5cce46cb6337c8ea601ed5eb4cc1258e18cf51092860")
        self.assertEqual(query["node_graph"]["edges"].shape, (14, 2))
        self.assertEqual(hashlib.sha256(frozen.read_bytes()).hexdigest(), before)

    def test_nested_proof_coherent_forgery_under_generation_guard(self):
        from tests.test_surface_variable_storage import static_disabled
        plain = deepcopy(_merged_coast__plain(self.result))
        mesh = plain["domain_mosaic"]["domain_meshes"][0]
        proof_id = next(iter(mesh["proofs"]))
        mesh["proof_h0_support"][proof_id]["weights"][0, 0] += .2
        mesh["identity_sha256"] = coast.fingerprint({key: item for key, item in mesh.items()
                                                     if key != "identity_sha256"})
        mosaic_record = plain["domain_mosaic"]
        mosaic_record["identity_sha256"] = coast.fingerprint({key: item for key, item in mosaic_record.items()
                                                              if key != "identity_sha256"})
        plain["identity_sha256"] = coast.fingerprint({key: item for key, item in plain.items()
                                                      if key != "identity_sha256"})
        with ExitStack() as stack:
            static_disabled(stack)
            with self.assertRaises(ValueError):
                engineering.validate_surface_engineering(_merged_coast__freeze(plain))

    def test_none_variable_never_prepares_or_imports(self):
        import sys
        with patch.dict(sys.modules, {'terrain_pipeline.surface_domain': None}):
            composed = engineering.compose_surface_engineering(
                self.evaluation, self.result["domain_mosaic"], self.result["drops"],
                self.result["dynamic_forest"])
            self.assertIsNone(engineering.query_surface_engineering(composed)["variable_storage"])

    def test_frozen_variable_same_forest_independent_prefix(self):
        from terrain_pipeline import surface_domain as variable
        self.assertEqual(hashlib.sha256(VARIABLE_SOURCE.read_bytes()).hexdigest(), VARIABLE_SHA256)
        saved = variable.load_surface_variable_storage(VARIABLE_SOURCE)
        result = engineering.compose_surface_engineering(
            self.evaluation, self.result["domain_mosaic"], self.result["drops"], saved["source"],
            variable_storage=saved)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variable-engineering.npz"
            engineering.save_surface_engineering(result, path)
            with ExitStack() as stack:
                for name in ("_geometry", "_knots", "_advance", "prepare_surface_variable_storage"):
                    stack.enter_context(patch.object(variable, name, side_effect=AssertionError("generated")))
                loaded = engineering.load_surface_engineering(path)
                query = engineering.query_surface_engineering(loaded, state_index=80, variable_state_index=1)
            self.assertEqual(query["dynamic"]["stage_m"].shape, (16,))
            self.assertEqual(query["variable_storage"]["stage_m"].shape, (16,))
            self.assertNotEqual(float(query["dynamic"]["time_s"]), float(query["variable_storage"]["time_s"]))
            self.assertAlmostEqual(float(saved["storage_m3"][0].sum()), 224.5721879136545)
        bad = deepcopy(_merged_coast__plain(result))
        bad["dynamic_forest"] = _merged_coast__plain(self.result["dynamic_forest"])
        bad["identity_sha256"] = coast.fingerprint({key: item for key, item in bad.items()
                                                   if key != "identity_sha256"})
        with self.assertRaises(ValueError):
            engineering.validate_surface_engineering(_merged_coast__freeze(bad))

    def test_coherent_aggregate_rehash_cannot_hide_mixed_source(self):
        plain = deepcopy(_merged_coast__plain(self.result))
        plain["drops"][1] = plain["drops"][0]
        plain["identity_sha256"] = coast.fingerprint({key: value for key, value in plain.items()
                                                       if key != "identity_sha256"})
        with self.assertRaises(ValueError):
            engineering.validate_surface_engineering(_merged_coast__freeze(plain))

    def test_cancel_and_resource_preflight(self):
        with self.assertRaises(InterruptedError):
            engineering.prepare_surface_engineering(self.evaluation, self.outlets, cancel=lambda: True, **forcing())
        with self.assertRaises(ValueError):
            engineering.prepare_surface_engineering(self.evaluation, self.outlets,
                resources=engineering.EngineeringResources(max_working_bytes=1024), **forcing())


if __name__ == "__main__":
    unittest.main()
