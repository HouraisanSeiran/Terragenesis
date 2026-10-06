"""Independent analytic and hostile-bundle tests for the bounded dynamic slice."""

from dataclasses import fields, replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import numpy as np

from terrain_pipeline import dynamic_surface_hydraulics as hydro


def graph_case(steps=3, upstream_q=1., tailwater=0.):
    local = np.zeros((steps, 3))
    local[:, 0] = upstream_q
    boundary = np.zeros((steps + 1, 3))
    boundary[:, 2] = tailwater
    return hydro.HydraulicsInput(
        bed_m=np.zeros(3), area_m2=np.full(3, 10.),
        initial_stage_m=np.array([0., 0., tailwater]),
        edges=np.array([[0, 1], [1, 2]], dtype=np.int64),
        conductance_m2_s=np.ones(2), local_q_m3_s=local,
        boundary_mask=np.array([False, False, True]), boundary_stage_m=boundary,
        dt_s=1., max_depth_m=10., valid_mask=np.ones(3, dtype=bool),
        protected_mask=np.zeros(3, dtype=bool),
        coords_m=np.array([[0., 0.], [1., 0.], [2., 0.]]),
        source="engineered-independent-three-node-benchmark", datum="local-bed-zero-metres",
        coords="local Cartesian (x,z), metres",
    )


def rewrite_bundle(path, *, metadata=None, array_name=None, payload=None, extra=None):
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    if metadata is not None:
        members["metadata.json"] = metadata
    if array_name is not None:
        members[array_name] = payload
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
        if extra is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(*extra)


class DynamicSurfaceHydraulicsTests(unittest.TestCase):
    def test_two_reach_delay_independent_analytic(self):
        result = hydro.evaluate(graph_case())
        np.testing.assert_allclose(result.stage_m,
                                   [[0., 0., 0.], [.1, 0., 0.], [.19, .01, 0.], [.272, .027, 0.]])
        np.testing.assert_allclose(result.qedges_m3_s, [[0., 0.], [.1, 0.], [.18, .01]])
        np.testing.assert_allclose(result.storage_m3.sum(axis=1), [0., 1., 2., 2.99])
        np.testing.assert_allclose(result.ledger_m3[:, 2], [0., 0., -.01])
        self.assertEqual(result.committed_steps, 3)

    def test_tailwater_reverse_signed_flux_independent_analytic(self):
        result = hydro.evaluate(graph_case(upstream_q=0., tailwater=1.))
        np.testing.assert_allclose(result.stage_m,
                                   [[0., 0., 1.], [0., .1, 1.], [.01, .18, 1.], [.027, .245, 1.]])
        np.testing.assert_allclose(result.qedges_m3_s, [[0., -1.], [-.1, -.9], [-.17, -.82]])
        np.testing.assert_allclose(result.storage_m3.sum(axis=1), [0., 1., 1.9, 2.72])
        np.testing.assert_allclose(result.ledger_m3[:, 2], [1., .9, .82])
        np.testing.assert_array_equal(result.storage_m3[:, 2], 0.)

    def test_tailwater_two_metres_and_n_next_index(self):
        result = hydro.evaluate(graph_case(upstream_q=0., tailwater=2.))
        np.testing.assert_allclose(result.stage_m[:, :2], [[0., 0.], [0., .2], [.02, .36], [.054, .49]])
        inputs = graph_case(upstream_q=0.)
        boundary = inputs.boundary_stage_m.copy()
        boundary[1:, 2] = 2.
        changed = hydro.evaluate(replace(inputs, boundary_stage_m=boundary))
        np.testing.assert_allclose(changed.qedges_m3_s[0], [0., 0.])
        np.testing.assert_allclose(changed.stage_m[1], [0., 0., 2.])
        np.testing.assert_allclose(changed.qedges_m3_s[1], [0., -2.])

    def test_steady_analytic(self):
        inputs = replace(graph_case(steps=12), initial_stage_m=np.array([2., 1., 0.]))
        result = hydro.evaluate(inputs)
        np.testing.assert_allclose(result.stage_m, np.tile([2., 1., 0.], (13, 1)))
        np.testing.assert_allclose(result.qedges_m3_s, 1.)
        np.testing.assert_allclose(result.ledger_m3[:, 1:3], np.tile([1., -1.], (12, 1)))

    def test_zero_q_equilibrium(self):
        inputs = replace(graph_case(upstream_q=0., tailwater=1.), initial_stage_m=np.ones(3))
        result = hydro.evaluate(inputs)
        np.testing.assert_array_equal(result.qedges_m3_s, 0.)
        np.testing.assert_array_equal(result.stage_m, 1.)
        np.testing.assert_array_equal(result.ledger_m3[:, 4:], 0.)

    def test_volume_conservation_closed_and_signed_local(self):
        inputs = replace(graph_case(steps=25, upstream_q=0.),
                         boundary_mask=np.zeros(3, dtype=bool), initial_stage_m=np.array([2., 1., .5]))
        local = inputs.local_q_m3_s.copy()
        local[:, 0] = .2
        local[:, 2] = -.1
        result = hydro.evaluate(replace(inputs, local_q_m3_s=local))
        np.testing.assert_allclose(result.storage_m3.sum(axis=1), 35. + .1 * np.arange(26))
        np.testing.assert_allclose(result.ledger_m3[:, 2], 0.)
        np.testing.assert_allclose(result.ledger_m3[:, 5], 0., atol=1e-12)

    def test_different_beds_negative_storage_rejects_original_step(self):
        inputs = replace(graph_case(upstream_q=0.), bed_m=np.array([2., 0., 0.]),
                         initial_stage_m=np.array([2., 0., 0.]))
        result = hydro.evaluate(inputs)
        self.assertEqual((result.status, result.committed_steps), ("failed", 0))
        self.assertEqual(result.failed_step.reason, "negative_depth")
        np.testing.assert_array_equal(result.storage_m3, [[0., 0., 0.]])
        np.testing.assert_allclose(result.failed_step.next_storage_m3, [-2., 2., 0.])
        self.assertEqual(result.ledger_m3.shape, (0, 6))
        self.assertTrue(hydro.validate(result)["valid"])

    def test_signed_withdrawal_failure_retains_prefix_and_failed_ledger(self):
        inputs = graph_case()
        local = inputs.local_q_m3_s.copy()
        local[1, 0] = -20.
        result = hydro.evaluate(replace(inputs, local_q_m3_s=local))
        self.assertEqual((result.status, result.committed_steps), ("failed", 1))
        self.assertEqual(result.failed_step.step_n, 1)
        self.assertEqual(len(result.ledger_m3), 1)
        self.assertEqual(result.failed_step.ledger_m3[1], -20.)
        np.testing.assert_array_equal(result.failed_step.previous_stage_m, result.stage_m[-1])
        self.assertLess(result.failed_step.next_storage_m3[0], 0.)

    def test_maxdepth_rejects_without_clamp_or_dt_change(self):
        inputs = replace(graph_case(), max_depth_m=.15)
        result = hydro.evaluate(inputs)
        self.assertEqual((result.status, result.committed_steps), ("failed", 1))
        self.assertEqual(result.failed_step.reason, "max_depth")
        self.assertAlmostEqual(result.failed_step.next_stage_m[0], .19)
        self.assertEqual(result.inputs.dt_s, 1.)

    def test_boundary_future_depth_failure_preserves_prefix(self):
        inputs = graph_case(upstream_q=0.)
        boundary = inputs.boundary_stage_m.copy()
        boundary[2:, 2] = 11.
        result = hydro.evaluate(replace(inputs, boundary_stage_m=boundary))
        self.assertEqual((result.status, result.committed_steps), ("failed", 1))
        self.assertEqual(result.failed_step.reason, "max_depth")

    def test_terminal_boundary_stage_rejects_original_step(self):
        for terminal, reason in ((-.1, "negative_depth"), (11., "max_depth")):
            inputs = graph_case(upstream_q=0.)
            boundary = inputs.boundary_stage_m.copy()
            boundary[-1, 2] = terminal
            result = hydro.evaluate(replace(inputs, boundary_stage_m=boundary))
            with self.subTest(terminal=terminal):
                self.assertEqual((result.status, result.committed_steps), ("failed", 2))
                self.assertEqual(result.failed_step.reason, reason)
                self.assertEqual(result.failed_step.next_stage_m[2], terminal)
                np.testing.assert_array_equal(result.stage_m, np.zeros((3, 3)))

    def test_dt_diffusive_bound(self):
        with self.assertRaisesRegex(ValueError, "diffusive stability"):
            replace(graph_case(), dt_s=5.01)
        self.assertEqual(hydro.evaluate(replace(graph_case(upstream_q=0.), dt_s=5.)).status, "completed")

    def test_unknown_protection_rejected(self):
        for name, mask in (("valid_mask", [True, False, True]),
                           ("protected_mask", [False, True, False])):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unknown or protected"):
                replace(graph_case(), **{name: np.array(mask)})

    def test_resource_preflight_before_freezing(self):
        inputs = graph_case()
        variants = [hydro.ResourceLimits(max_nodes=2), hydro.ResourceLimits(max_edges=1),
                    hydro.ResourceLimits(max_steps=2), hydro.ResourceLimits(max_work=14),
                    hydro.ResourceLimits(max_retained_bytes=100)]
        for limits in variants:
            with self.subTest(limits=limits), patch.object(hydro, "_immutable", side_effect=AssertionError("freeze too soon")):
                with self.assertRaisesRegex(ValueError, "resource cap"):
                    replace(inputs, limits=limits)
        with self.assertRaises(ValueError):
            hydro.ResourceLimits(max_nodes=4097)

    def test_cancel_keeps_committed_prefix_only(self):
        calls = iter([False, True])
        result = hydro.evaluate(graph_case(), cancel=lambda: next(calls))
        self.assertEqual((result.status, result.committed_steps), ("cancelled", 1))
        self.assertIsNone(result.failed_step)
        self.assertEqual(result.stage_m.shape, (2, 3))
        self.assertEqual(result.ledger_m3.shape, (1, 6))
        self.assertTrue(hydro.validate(result)["valid"])
        immediate = hydro.evaluate(graph_case(), cancel=lambda: True)
        self.assertEqual(immediate.committed_steps, 0)

    def test_source_immutability_and_irreversible_bytes_freeze(self):
        inputs = graph_case()
        raw = np.array([0., 0., 0.])
        inputs = replace(inputs, bed_m=raw)
        raw[:] = -10.
        np.testing.assert_array_equal(inputs.bed_m, 0.)
        before = {field.name: getattr(inputs, field.name).tobytes() for field in fields(inputs)
                  if isinstance(getattr(inputs, field.name), np.ndarray)}
        result = hydro.evaluate(inputs)
        for field in fields(inputs):
            value = getattr(inputs, field.name)
            if isinstance(value, np.ndarray):
                self.assertEqual(value.tobytes(), before[field.name])
        for array in hydro._arrays(result).values():
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_rehash_does_not_bypass_static_proof(self):
        result = hydro.evaluate(graph_case())
        for name in ("stage_m", "storage_m3", "qedges_m3_s", "ledger_m3", "time_s"):
            changed = getattr(result, name).copy()
            changed.flat[-1] += .5
            forged = replace(result, **{name: changed}, identity_sha256="")
            self.assertEqual(forged.identity_sha256, hydro.fingerprint(forged))
            with self.subTest(name=name), self.assertRaises(ValueError):
                hydro.validate(forged)
        failed = hydro.evaluate(replace(graph_case(), max_depth_m=.15))
        forged_failure = replace(failed.failed_step, reason="negative_depth")
        with self.assertRaisesRegex(ValueError, "failed reason"):
            hydro.validate(replace(failed, failed_step=forged_failure, identity_sha256=""))

    def test_roundtrip_load_never_calls_evaluate(self):
        results = [hydro.evaluate(graph_case()), hydro.evaluate(replace(graph_case(), max_depth_m=.15)),
                   hydro.evaluate(graph_case(), cancel=lambda: True)]
        with tempfile.TemporaryDirectory() as directory:
            for index, result in enumerate(results):
                path = Path(directory) / (str(index) + ".npz")
                hydro.save(result, path)
                with patch.object(hydro, "evaluate", side_effect=AssertionError("load advanced time")):
                    loaded = hydro.load(path)
                self.assertEqual(loaded.identity_sha256, result.identity_sha256)
                self.assertEqual(loaded.status, result.status)
                for name, array in hydro._arrays(loaded).items():
                    np.testing.assert_array_equal(array, hydro._arrays(result)[name])
                    with self.assertRaises(ValueError):
                        array.setflags(write=True)

    def test_atomic_nooverwrite_and_fd_cleanup(self):
        result = hydro.evaluate(graph_case())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.npz"
            hydro.save(result, path)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                hydro.save(result, path)
            self.assertEqual(path.read_bytes(), original)
            with patch.object(hydro.os, "link", side_effect=OSError("publication failed")):
                with self.assertRaisesRegex(OSError, "publication failed"):
                    hydro.save(result, Path(directory) / "failed.npz")
            self.assertEqual([member.name for member in Path(directory).iterdir()], ["bundle.npz"])
            path.unlink()

    def test_reject_selfloop_duplicate_and_boundary_localq(self):
        inputs = graph_case()
        for edges in (np.array([[0, 0], [1, 2]]), np.array([[0, 1], [1, 0]])):
            with self.assertRaises(ValueError):
                replace(inputs, edges=edges)
        local = inputs.local_q_m3_s.copy()
        local[0, 2] = 1.
        with self.assertRaisesRegex(ValueError, "only supported on internal"):
            replace(inputs, local_q_m3_s=local)

    def test_invalid_finite_shape_units_provenance(self):
        inputs = graph_case()
        for changes in ({"bed_m": np.array([0., np.nan, 0.])}, {"dt_s": 0.},
                        {"area_m2": np.array([10., 0., 10.])}, {"max_depth_m": float("inf")},
                        {"edges": np.array([[0., 1.], [1., 2.]])}, {"source": ""},
                        {"coords_m": np.zeros((3, 3))}, {"boundary_mask": np.ones(3, dtype=bool)},
                        {"valid_mask": np.ones(3)}, {"geometry_mode": "validated-recovery"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(inputs, **changes)

    def test_empty_edges_is_supported(self):
        result = hydro.evaluate(replace(graph_case(), edges=np.empty((0, 2), dtype=np.int64),
                                        conductance_m2_s=np.empty(0)))
        np.testing.assert_allclose(result.stage_m[:, 0], [0., .1, .2, .3])
        self.assertEqual(result.qedges_m3_s.shape, (3, 0))

    def test_archive_duplicate_json_members_and_member_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, mode in enumerate(("json", "zip", "extra")):
                path = Path(directory) / (str(index) + ".npz")
                hydro.save(hydro.evaluate(graph_case()), path)
                if mode == "json":
                    with zipfile.ZipFile(path) as archive:
                        meta = archive.read("metadata.json")
                    rewrite_bundle(path, metadata=meta[:-1] + b',"dt_s":1}')
                elif mode == "zip":
                    rewrite_bundle(path, extra=("stage_m.npy", b"duplicate"))
                else:
                    rewrite_bundle(path, extra=("unexpected.npy", b"extra"))
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    hydro.load(path)

    def test_archive_header_payload_and_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("huge_shape", "object", "trailing", "truncated", "metadata", "dimensions"):
                path = Path(directory) / (mode + ".npz")
                hydro.save(hydro.evaluate(graph_case()), path)
                with zipfile.ZipFile(path) as archive:
                    raw = archive.read("stage_m.npy")
                    meta = json.loads(archive.read("metadata.json"))
                if mode in ("huge_shape", "object"):
                    stream = io.BytesIO()
                    np.lib.format.write_array_header_1_0(stream, {
                        "descr": "|O" if mode == "object" else "<f8", "fortran_order": False,
                        "shape": (1000000000,) if mode == "huge_shape" else (4, 3)})
                    rewrite_bundle(path, array_name="stage_m.npy", payload=stream.getvalue())
                elif mode in ("trailing", "truncated"):
                    rewrite_bundle(path, array_name="stage_m.npy", payload=raw + b"X" if mode == "trailing" else raw[:-1])
                elif mode == "metadata":
                    rewrite_bundle(path, metadata=b" " * (hydro.MAX_METADATA_BYTES + 1))
                else:
                    meta["nodes"] = 1000000000
                    rewrite_bundle(path, metadata=json.dumps(meta).encode())
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    hydro.load(path)

    def test_archive_header_member_file_and_hash_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("header", "members", "hash", "file"):
                path = Path(directory) / (mode + ".npz")
                hydro.save(hydro.evaluate(graph_case()), path)
                if mode == "header":
                    payload = b"\x93NUMPY\x01\x00" + (65535).to_bytes(2, "little")
                    rewrite_bundle(path, array_name="stage_m.npy", payload=payload)
                elif mode == "members":
                    with zipfile.ZipFile(path, "a") as archive:
                        for index in range(hydro.MAX_MEMBERS):
                            archive.writestr(str(index), b"")
                elif mode == "hash":
                    with zipfile.ZipFile(path) as archive:
                        metadata = json.loads(archive.read("metadata.json"))
                    metadata["identity_sha256"] = ""
                    rewrite_bundle(path, metadata=json.dumps(metadata).encode())
                if mode == "file":
                    with patch.object(hydro, "MAX_FILE_BYTES", 10), self.assertRaisesRegex(ValueError, "file cap"):
                        hydro.load(path)
                else:
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        hydro.load(path)

    def test_saved_rehashed_flux_rejected_with_evaluate_disabled(self):
        result = hydro.evaluate(graph_case())
        flux = result.qedges_m3_s.copy()
        flux[1, 0] += .5
        forged = replace(result, qedges_m3_s=flux, identity_sha256="")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged.npz"
            hydro.save(result, path)
            with zipfile.ZipFile(path) as archive:
                metadata = json.loads(archive.read("metadata.json"))
            metadata["identity_sha256"] = forged.identity_sha256
            payload = io.BytesIO()
            np.lib.format.write_array(payload, forged.qedges_m3_s, version=(1, 0), allow_pickle=False)
            rewrite_bundle(path, metadata=json.dumps(metadata).encode(),
                           array_name="qedges_m3_s.npy", payload=payload.getvalue())
            with patch.object(hydro, "evaluate", side_effect=AssertionError("load advanced")):
                with self.assertRaisesRegex(ValueError, "edge conductance"):
                    hydro.load(path)

    def test_verifier_failure_retains_utc_evidence(self):
        import sys
        from tools import verify_dynamic_surface_hydraulics as verifier

        with tempfile.TemporaryDirectory() as directory:
            argv = ["verify", "--skip-tests", "--output-root", directory]
            with patch.object(sys, "argv", argv), patch.object(verifier, "run_cases", side_effect=RuntimeError("injected failure")):
                self.assertEqual(verifier.main(), 1)
            run_directory = next(Path(directory).iterdir())
            report = json.loads((run_directory / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertIn("injected failure", report["error"])
            self.assertTrue(report["started_utc"].endswith("+00:00"))
            self.assertTrue(report["finished_utc"].endswith("+00:00"))
            self.assertTrue((run_directory / "started.json").is_file())
            self.assertTrue((run_directory / "failure-traceback.log").is_file())
            self.assertEqual(len(report["source_files"]), 4)
            self.assertTrue(report["source_files_unchanged"])
            for name, evidence in report["evidence_files"].items():
                self.assertEqual(evidence["file_sha256"],
                                 hashlib.sha256((run_directory / name).read_bytes()).hexdigest())

    def test_verifier_binds_source_and_bundle_file_sha256(self):
        from tools import verify_dynamic_surface_hydraulics as verifier

        for record in verifier.source_file_hashes().values():
            self.assertEqual(record["file_sha256"], hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            record = verifier.record_case(Path(directory), "fixed", graph_case())
            self.assertEqual(record["bundle_file_sha256"],
                             hashlib.sha256(Path(record["bundle"]).read_bytes()).hexdigest())
            self.assertTrue(record["bundle_file_unchanged_after_reload"])
            self.assertNotEqual(record["bundle_file_sha256"], record["identity_sha256"])

    def test_arithmetic_failure_roundtrip_nonfinite_evidence(self):
        inputs = replace(graph_case(steps=1), dt_s=5.,
                         local_q_m3_s=np.array([[1e308, 0., 0.]]))
        result = hydro.evaluate(inputs)
        self.assertEqual((result.status, result.committed_steps), ("failed", 0))
        self.assertEqual(result.failed_step.reason, "arithmetic_nonfinite")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nonfinite-candidate.npz"
            hydro.save(result, path)
            loaded = hydro.load(path)
            self.assertEqual(loaded.identity_sha256, result.identity_sha256)
            self.assertTrue(np.isinf(loaded.failed_step.next_storage_m3[0]))


if __name__ == "__main__":
    unittest.main()
