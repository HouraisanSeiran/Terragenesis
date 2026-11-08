import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from tools import verify_native_30m_product as v


class TestVerifyNative30mProduct(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.bundle = os.path.join(self.root, "emptybundle")
        os.makedirs(self.bundle)
        self.output = os.path.join(self.root, "outside_report.json")

    def _fake_run(self, argv, timeout=None):
        mode = None
        if "--mode" in argv:
            mode = argv[argv.index("--mode") + 1]
        if mode == "inspect":
            obj = {"cold_read_verified_now": True, "source_code_drift": [],
                   "numerical_identity_sha256": "a" * 64, "identity_sha256": "b" * 64}
            if "--point" in argv:
                obj = dict(obj)
                obj["point"] = {"resolved": True, "scope": "channel_section", "sampled_native_xz": [3, 4]}
            return obj, {"argv": argv, "elapsed_seconds": 0.0, "returncode": 0}
        if mode == "audit":
            obj = {"cold_read_verified_now": True, "source_code_drift": [],
                   "numerical_identity_sha256": "a" * 64, "identity_sha256": "b" * 64,
                   "independent_audit_rerun_now": True,
                   "audit": {"passed": True, "spatial_section_reference": {"passed": True}}}
            return obj, {"argv": argv, "elapsed_seconds": 0.0, "returncode": 0}
        raise AssertionError("unexpected mode: %r" % (mode,))

    def _write_report(self, data):
        with open(self.output, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_basic_no_point(self):
        argv = ["verify", "--bundle", self.bundle, "--output", self.output]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(v, "run", side_effect=self._fake_run):
            v.main()
        with open(self.output, encoding="utf-8") as fh:
            result = json.load(fh)
        self.assertTrue(result["passed"])
        self.assertIsNone(result["checks"]["point_native"])
        self.assertTrue(result["checks"]["audit"] is True)
        self.assertTrue(
            result["results"]["audit"]["audit"]["spatial_section_reference"]["passed"]
        )

    def test_point_and_identity(self):
        argv = ["verify", "--bundle", self.bundle, "--output", self.output,
                "--point-native", "3", "4", "--identity", "a" * 64]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(v, "run", side_effect=self._fake_run):
            v.main()
        with open(self.output, encoding="utf-8") as fh:
            result = json.load(fh)
        self.assertTrue(result["passed"])
        self.assertEqual(result["release_identity_sha256"], "b" * 64)
        self.assertTrue(result["checks"]["point_native"] is True)

    def test_bad_cases(self):
        cases = [("audit_not_passed", "audit", {"audit": {"passed": False}}),
                 ("spatial_not_passed", "audit", {"audit": {"spatial_section_reference": {"passed": False}}}),
                 ("audit_numerical_c", "audit", {"numerical_identity_sha256": "c" * 64}),
                 ("audit_identity_c", "audit", {"identity_sha256": "c" * 64}),
                 ("inspect_drift", "inspect", {"source_code_drift": ["x"]})]
        for name, mode, overrides in cases:
            with self.subTest(name=name):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                out = os.path.join(tmp.name, "report.json")
                argv = [
                    "verify", "--bundle", self.bundle, "--output", out,
                ]
                def bad_run(argv, timeout=None, _o=overrides, _m=mode):
                    obj, rec = self._fake_run(argv, timeout)
                    obj = dict(obj)
                    current_mode = argv[argv.index('--mode') + 1]
                    if current_mode == _m:
                        for key, value in _o.items():
                            if key == 'audit' and isinstance(value, dict):
                                obj['audit'].update(value)
                            else:
                                obj[key] = value
                    return obj, rec
                with mock.patch.object(sys, "argv", argv), mock.patch.object(v, "run", side_effect=bad_run), \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as cm:
                        v.main()
                self.assertEqual(cm.exception.code, 1)
                self.assertFalse(os.path.exists(out))

    def test_output_exists(self):
        self._write_report({"marker": True})
        with open(self.output, encoding="utf-8") as stream:
            before = stream.read()
        argv = ["verify", "--bundle", self.bundle, "--output", self.output]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(v, "run", side_effect=self._fake_run) as mrun, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                v.main()
        self.assertEqual(cm.exception.code, 1)
        mrun.assert_not_called()
        with open(self.output, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), before)

    def test_output_inside_bundle(self):
        inside = os.path.join(self.bundle, "report.json")
        argv = ["verify", "--bundle", self.bundle, "--output", inside]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(v, "run", side_effect=self._fake_run) as mrun, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                v.main()
        self.assertEqual(cm.exception.code, 1)
        mrun.assert_not_called()
        self.assertFalse(os.path.exists(inside))


if __name__ == "__main__":
    unittest.main()
