from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import numpy as np

from terrain_pipeline import dynamic_surface_hydraulics as hydraulics
from terrain_pipeline import surface_dynamic_prepare as adapter
from terrain_pipeline import surface_fine_mosaic as mosaic
from terrain_pipeline.surface_network_recovery import recover_surface_network
from terrain_pipeline.surface_domain_prepare import evaluate_surface_domains, plan_surface_domains, load_surface_domains
from tests.test_surface_domain_prepare import complete_two_domain_inputs, fine_configurations
from tests.test_surface_network_recovery import recovery_case
from tests.test_surface_fine_mosaic import rehash_surface

ROOT = Path(__file__).resolve().parents[1]
SAVED_DOMAIN_PATH = ROOT / "verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz"
SAVED_DOMAIN_SHA256 = "dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af"


def source_binding():
    proof = recover_surface_network(**recovery_case())
    if not proof["accepted"]:
        raise AssertionError("engineering source recovery not accepted")
    return adapter.bind_surface_dynamic_source(proof, vertical_datum="engineering-relative-sea-zero")


def forcing(binding, steps=80, pulse=False, raised=False):
    count = len(binding["node_flat_ids"])
    local = np.zeros((steps, count))
    if pulse:
        local[:10, 0] = 1.
    tailwater = np.tile(binding["initial_stage_m"][binding["boundary_mask"]], (steps + 1, 1))
    if raised:
        tailwater[1:] += .5
    return {"conductance_m2_s": np.full(len(binding["edges"]), 2.), "local_q_m3_s": local,
            "tailwater_m": tailwater, "dt_s": 1., "max_depth_m": 4.}


def mutable(value):
    return deepcopy(mosaic._plain(value))


def rehash(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = mosaic._identity(record)
    return record


def rewrite_dynamic(record):
    dynamic = record["dynamic"]
    dynamic["identity_sha256"] = hydraulics.fingerprint(adapter._unpack_dynamic(dynamic))
    return rehash(record)


def rewrite_binding(record):
    rehash(record["binding"])
    record["dynamic"]["inputs"]["source"] = record["binding"]["identity_sha256"]
    return rewrite_dynamic(record)


def write_bundle(result, path):
    arrays = {}
    tree = mosaic._tree(result, arrays)
    manifest = {"format_version": 1, "tree": tree, "tree_sha256": mosaic._identity(tree)}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", mosaic._json(manifest))
        for name, array in arrays.items():
            with io.BytesIO() as stream:
                np.save(stream, np.ascontiguousarray(array), allow_pickle=False)
                archive.writestr(name, stream.getvalue())


def generation_disabled(stack):
    for target in ("terrain_pipeline.surface_dynamic_prepare.bind_surface_dynamic_source",
                   "terrain_pipeline.surface_dynamic_prepare.prepare_surface_dynamic",
                   "terrain_pipeline.surface_dynamic_prepare._source_mosaic",
                   "terrain_pipeline.dynamic_surface_hydraulics.evaluate",
                   "terrain_pipeline.surface_network_recovery.recover_surface_network",
                   "terrain_pipeline.surface_network_recovery._replay",
                   "terrain_pipeline.surface_domain_prepare.evaluate_surface_domains",
                   "terrain_pipeline.surface_network_prepare.prepare_surface_network",
                   "terrain_pipeline.surface_network_consumer._fine_source",
                   "terrain_pipeline.surface_fine_mosaic.prepare_fine_mosaic",
                   "terrain_pipeline.surface_fine_mosaic._h0_support",
                   "terrain_pipeline.surface_fine_mosaic._stencil",
                   "terrain_pipeline.surface_fine_mosaic._assemble",
                   "terrain_pipeline.surface_fine_mosaic._mesh",
                   "terrain_pipeline.surface_fine_mosaic._grid",
                   "terrain_pipeline.surface_fine_mosaic._ownership",
                   "terrain_pipeline.surface_fine_mosaic._proof_gate"):
        stack.enter_context(patch(target, side_effect=AssertionError("static read generated: " + target)))


class SurfaceDynamicPrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binding = source_binding()
        cls.pulse = adapter.prepare_surface_dynamic(cls.binding, **forcing(cls.binding, pulse=True))
        cls.raised = adapter.prepare_surface_dynamic(cls.binding, **forcing(cls.binding, raised=True))

    def test_actual_source_cells_unique_area_graph_bed_stage(self):
        binding = self.binding
        self.assertEqual(binding["node_flat_ids"].tolist(), [9, 11, 17, 24, 31, 38, 45])
        np.testing.assert_array_equal(binding["area_m2"], [60., 60., 190., 200., 200., 130., 20.])
        self.assertEqual(binding["edges"].shape, (6, 2))
        self.assertEqual(len(set(binding["wet_cell_ids"].tolist())), 860)
        self.assertEqual(float(binding["area_m2"].sum()), 860.)
        self.assertEqual(float(binding["area_m2"][~binding["boundary_mask"]].sum()), 840.)
        source = binding["source_mosaic"]
        np.testing.assert_array_equal(binding["bed_m"], source["nodes"]["h2_m"][binding["fine_node_ids"]])
        np.testing.assert_array_equal(binding["initial_stage_m"], source["nodes"]["water_surface_m"][binding["fine_node_ids"]])
        self.assertFalse(binding["full_dynamic_wave_prepared"])

    def test_pulse_propagates_delayed_and_qv_closes(self):
        dynamic = self.pulse["dynamic"]
        self.assertEqual(dynamic["status"], "completed")
        self.assertGreater(dynamic["stage_m"][1, 0], dynamic["stage_m"][0, 0])
        self.assertEqual(dynamic["stage_m"][1, 2], dynamic["stage_m"][0, 2])
        self.assertGreater(dynamic["stage_m"][2, 2], dynamic["stage_m"][1, 2])
        self.assertEqual(dynamic["qedges_m3_s"][0, 0], 0.)
        self.assertGreater(dynamic["qedges_m3_s"][1, 0], 0.)
        self.assertGreater(dynamic["stage_m"][-1, 5], dynamic["stage_m"][0, 5])
        ledger = dynamic["ledger_m3"]
        self.assertAlmostEqual(float(ledger[:, 1].sum()), 10.)
        self.assertLess(float(np.abs(ledger[:, 5]).max()), 1e-10)
        self.assertAlmostEqual(float(dynamic["storage_m3"][-1].sum() - dynamic["storage_m3"][0].sum()),
                               float(ledger[:, 1:3].sum()), places=9)

    def test_tailwater_raise_reverses_flow_then_upstream_responds(self):
        dynamic = self.raised["dynamic"]
        self.assertEqual(dynamic["status"], "completed")
        self.assertTrue(np.all(dynamic["qedges_m3_s"][0] == 0))
        self.assertEqual(dynamic["stage_m"][1, 5], dynamic["stage_m"][0, 5])
        self.assertLess(dynamic["qedges_m3_s"][1, -1], 0.)
        self.assertGreater(dynamic["stage_m"][2, 5], dynamic["stage_m"][1, 5])
        self.assertGreater(dynamic["stage_m"][-1, 0], dynamic["stage_m"][0, 0])
        self.assertGreater(float(dynamic["ledger_m3"][:, 2].sum()), 0.)

    def test_real_prepared_old_domain_source_without_filling_gap(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        prepared = evaluate_surface_domains(candidate, fine_configurations(candidate))
        binding = adapter.bind_surface_dynamic_source(prepared, domain_id=1,
            vertical_datum=candidate["inputs"]["vertical_datum"])
        self.assertEqual(binding["source_mosaic"]["sources"][0]["domain_id"], 1)
        self.assertFalse(binding["source_mosaic"]["full_domain_mosaic_prepared"])
        result = adapter.prepare_surface_dynamic(binding, **forcing(binding, steps=3))
        self.assertEqual(result["status"], "completed")
        with self.assertRaisesRegex(ValueError, "select exactly one"):
            adapter.bind_surface_dynamic_source(prepared, vertical_datum=candidate["inputs"]["vertical_datum"])

    def test_actual_saved_prepared_domain_fixed_positive(self):
        import hashlib
        self.assertEqual(hashlib.sha256(SAVED_DOMAIN_PATH.read_bytes()).hexdigest(), SAVED_DOMAIN_SHA256)
        source = load_surface_domains(SAVED_DOMAIN_PATH)
        binding = adapter.bind_surface_dynamic_source(source, domain_id=1,
            vertical_datum=source["candidate"]["inputs"]["vertical_datum"])
        np.testing.assert_array_equal(binding["node_flat_ids"], [9, 11, 16, 17, 23, 30, 37, 45])
        np.testing.assert_array_equal(binding["area_m2"], [22., 40., 48., 84., 55., 40., 33., 16.])
        params = forcing(binding, steps=5)
        params["conductance_m2_s"][:] = .01
        params["dt_s"] = .1
        params["local_q_m3_s"][:, 0] = .1
        result = adapter.prepare_surface_dynamic(binding, **params)
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(float(result["dynamic"]["storage_m3"][0].sum()), 161.)
        self.assertEqual(len(binding["wet_cell_ids"]), 338)
        self.assertEqual(float(binding["area_m2"][binding["boundary_mask"]].sum()), 16.)

    def test_plain_or_unaccepted_source_rejected(self):
        with self.assertRaises(ValueError):
            adapter.bind_surface_dynamic_source({"status": "prepared"}, vertical_datum="engineering-zero")
        proof = mutable(next(iter(self.binding["source_mosaic"]["proofs"].values())))
        proof["accepted"] = False
        with self.assertRaises(ValueError):
            adapter.bind_surface_dynamic_source(proof, vertical_datum="engineering-zero")

    def test_source_domain_fine_dataclass_supported(self):
        proof = next(iter(self.binding["source_mosaic"]["proofs"].values()))
        source = mosaic.DomainFineSource(proof, 7)
        binding = adapter.bind_surface_dynamic_source(source, vertical_datum="engineering-relative-sea-zero")
        self.assertEqual(binding["source_mosaic"]["sources"][0]["domain_id"], 7)

    def test_A0_rejected_and_nearest_tie_cannot_reassign(self):
        proof = next(iter(self.binding["source_mosaic"]["proofs"].values()))
        with patch.object(adapter.np, "argmin", return_value=0):
            with self.assertRaisesRegex(ValueError, "A0"):
                adapter.bind_surface_dynamic_source(proof, vertical_datum="engineering-relative-sea-zero")
        record = mutable(self.pulse)
        record["binding"]["area_m2"][0] = 0.
        rewrite_binding(record)
        with self.assertRaises(ValueError):
            adapter.validate_surface_dynamic(record)

    def test_explicit_boundary_q_tailwater_and_k_gates(self):
        for kind in ("boundary_q", "initial_tailwater", "bad_k", "bad_local_shape", "bad_tailwater_shape", "unstable"):
            params = forcing(self.binding, steps=3)
            if kind == "boundary_q":
                params["local_q_m3_s"][0, -1] = 1.
            elif kind == "initial_tailwater":
                params["tailwater_m"][0, 0] += .1
            elif kind == "bad_k":
                params["conductance_m2_s"][0] = 0.
            elif kind == "bad_local_shape":
                params["local_q_m3_s"] = np.zeros((3, 2))
            elif kind == "bad_tailwater_shape":
                params["tailwater_m"] = np.zeros((3, 1))
            else:
                params["dt_s"] = 1000.
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                adapter.prepare_surface_dynamic(self.binding, **params)

    def test_cancellation_and_failure_keep_only_committed_prefix(self):
        cancelled = adapter.prepare_surface_dynamic(self.binding, **forcing(self.binding, steps=3), cancel=lambda: True)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["dynamic"]["committed_steps"], 0)
        params = forcing(self.binding, steps=4)
        params["tailwater_m"][2:, 0] = 100.
        failed = adapter.prepare_surface_dynamic(self.binding, **params)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["dynamic"]["committed_steps"], 1)
        self.assertTrue(adapter.validate_surface_dynamic(failed))

    def test_load_query_no_generation_readonly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pulse.npz"
            adapter.save_surface_dynamic(self.pulse, path)
            with ExitStack() as stack:
                generation_disabled(stack)
                loaded = adapter.load_surface_dynamic(path)
                queried = adapter.query_surface_dynamic(loaded, state_index=2)
            self.assertEqual(loaded["identity_sha256"], self.pulse["identity_sha256"])
            with self.assertRaises(ValueError):
                queried["stage_m"].flags.writeable = True
            with self.assertRaises(TypeError):
                loaded["status"] = "completed"
            with self.assertRaises(ValueError):
                adapter.query_surface_dynamic(loaded, state_index=1000)

    def test_coherently_rehashed_area_owner_duplicate_cell_and_bed_rejected(self):
        for kind in ("area", "owner", "duplicate", "bed", "stage", "edge", "fine_node"):
            record = mutable(self.pulse)
            binding = record["binding"]
            if kind == "area":
                binding["area_m2"][0] += 1.
            elif kind == "owner":
                binding["wet_cell_owner"][0] = (binding["wet_cell_owner"][0] + 1) % len(binding["area_m2"])
                binding["area_m2"] = np.bincount(binding["wet_cell_owner"], minlength=len(binding["area_m2"])).astype(float)
            elif kind == "duplicate":
                binding["wet_cell_ids"][1] = binding["wet_cell_ids"][0]
            elif kind == "bed":
                binding["bed_m"][0] -= .01
            elif kind == "stage":
                binding["initial_stage_m"][0] += .01
            elif kind == "edge":
                binding["edges"][0, 1] = 3
            else:
                binding["fine_node_ids"][0] += 1
            rewrite_binding(record)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                adapter.validate_surface_dynamic(record)

    def test_rehashed_unknown_protection_and_source_stage_rejected(self):
        for kind in ("unknown", "protection", "source_stage", "coarse_support"):
            record = mutable(self.pulse)
            binding = record["binding"]
            source = binding["source_mosaic"]
            source_node = int(binding["fine_node_ids"][0])
            fine_shape = next(iter(source["proofs"].values()))["inputs"]["fine"]["shape_zx"]
            row, column = divmod(source_node, fine_shape[1])
            if kind in ("unknown", "protection"):
                name = "unknown_mask" if kind == "unknown" else "protected_mask"
                source["sources"][0][name][row, column] = True
            elif kind == "coarse_support":
                next(iter(source["proof_h0_support"].values()))["weights"][0] = [.5, .5, 0., 0.]
            else:
                old_identity = binding["source_proof_sha256"]
                proof = source["proofs"].pop(old_identity)
                proof["surface"]["arrays"]["water_surface_m"][row, column] += .01
                rehash_surface(proof)
                new_identity = proof["identity_sha256"]
                source["proofs"][new_identity] = proof
                source["proof_h0_support"][new_identity] = source["proof_h0_support"].pop(old_identity)
                source["sources"][0]["proof_sha256"] = new_identity
                binding["source_proof_sha256"] = new_identity
            rehash(source)
            rewrite_binding(record)
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "source-tampered.npz"
                write_bundle(record, path)
                with self.assertRaises(ValueError):
                    adapter.load_surface_dynamic(path)

    def test_dynamic_rehashed_stage_storage_flux_ledger_rejected(self):
        for name in ("stage_m", "storage_m3", "qedges_m3_s", "ledger_m3"):
            record = mutable(self.pulse)
            record["dynamic"][name][1, 0] += .01
            rewrite_dynamic(record)
            with self.subTest(name=name), self.assertRaises(ValueError):
                adapter.validate_surface_dynamic(record)

    def test_resources_preflight_before_generation_or_payload_allocation(self):
        proof = next(iter(self.binding["source_mosaic"]["proofs"].values()))
        with patch.object(adapter, "_source_mosaic", side_effect=AssertionError("source generation before cap")):
            with self.assertRaisesRegex(ValueError, "resource preflight"):
                adapter.bind_surface_dynamic_source(proof, vertical_datum="zero",
                    resources=adapter.DynamicPrepareResources(max_retained_bytes=100))
        record = mutable(self.pulse)
        record["resources"]["max_working_bytes"] = 100
        record["binding"]["resources"]["max_working_bytes"] = 100
        rewrite_binding(record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resource.npz"
            write_bundle(record, path)
            with patch.object(adapter.np, "load", side_effect=AssertionError("allocated before preflight")):
                with self.assertRaisesRegex(ValueError, "resource preflight"):
                    adapter.load_surface_dynamic(path)

    def test_archive_payload_and_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "good.npz"
            adapter.save_surface_dynamic(self.pulse, path)
            with zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for kind in ("truncated", "trailing", "header", "json", "duplicate"):
                changed = dict(members)
                array_name = next(name for name in changed if name.endswith(".npy"))
                if kind == "truncated":
                    changed[array_name] = changed[array_name][:-1]
                elif kind == "trailing":
                    changed[array_name] += b"trailing"
                elif kind == "header":
                    changed[array_name] = b'\x93NUMPY\x01\x00\xff\xff' + b' ' * 65535
                elif kind == "json":
                    changed["manifest.json"] = changed["manifest.json"].replace(b'{', b'{"format_version":1,', 1)
                target = Path(directory) / (kind + ".npz")
                with warnings.catch_warnings(), zipfile.ZipFile(target, "w") as archive:
                    warnings.simplefilter("ignore")
                    for name, payload in changed.items():
                        archive.writestr(name, payload)
                    if kind == "duplicate":
                        archive.writestr(array_name, changed[array_name])
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    adapter.load_surface_dynamic(target)

    def test_save_nooverwrite_atomic_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "good.npz"
            adapter.save_surface_dynamic(self.pulse, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                adapter.save_surface_dynamic(self.pulse, path)
            self.assertEqual(path.read_bytes(), before)
            failed = Path(directory) / "failed.npz"
            with patch.object(adapter.os, "link", side_effect=OSError("failed publish")):
                with self.assertRaises(OSError):
                    adapter.save_surface_dynamic(self.pulse, failed)
            self.assertFalse(failed.exists())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
