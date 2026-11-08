"""Standard-library tests for the saved-candidate replay harness."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_stage1_saved_replay as replay


class SavedReplayTests(unittest.TestCase):
    def test_orders_preserve_all_products_and_reverse(self):
        specs = [dict(key=str(i)) for i in range(6)]
        orders = replay.schedules(specs)
        self.assertEqual(4, len(orders))
        self.assertEqual(specs[::-1], orders[1][1])
        self.assertNotEqual(specs, orders[2][1])
        for _, products in orders:
            self.assertEqual(sorted(p["key"] for p in specs), sorted(p["key"] for p in products))

    def test_rejection_requires_expected_reason(self):
        self.assertTrue(replay.rejection_matches(ValueError("SHA256 mismatch"), "sha"))
        self.assertTrue(replay.rejection_matches(ValueError("external archive hash mismatch"), "sha"))
        self.assertFalse(replay.rejection_matches(ValueError("unrelated hash failure"), "sha"))
        self.assertFalse(replay.rejection_matches(RuntimeError("SHA256 mismatch"), "sha"))
        self.assertFalse(replay.rejection_matches(FileNotFoundError("missing"), "sha"))
        self.assertTrue(replay.rejection_matches(FileNotFoundError("missing"), "missing"))
        self.assertFalse(replay.rejection_matches(ValueError("SHA256 mismatch"), "version"))
        self.assertTrue(replay.rejection_matches(ValueError("domain hydraulic identity/schema/scope mismatch"), "version"))
        self.assertFalse(replay.rejection_matches(None, "version"))
        self.assertTrue(replay.rejection_matches(ValueError("identity mismatch"), "identity"))

    def test_containment_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(root / "a", replay.contained(root / "a", root))
            with self.assertRaises(ValueError):
                replay.contained(root / "../escape", root)

    def test_json_rejects_duplicate_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            for text in ('{"a": 1, "a": 2}', '{"a": NaN}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    replay.read_json(path)

    def test_no_generation_blocks_before_body_and_restores_profile(self):
        namespace = {"__name__": "probe"}
        exec(compile("def solve_probe():\n    raise AssertionError('body executed')\n",
                     str(replay.ROOT / "terrain_pipeline/probe.py"), "exec"), namespace)
        previous = sys.getprofile()
        with replay.no_generation() as blocked:
            with self.assertRaisesRegex(RuntimeError, "forbidden generation/solve"):
                namespace["solve_probe"]()
        self.assertEqual(1, len(blocked))
        self.assertIs(previous, sys.getprofile())

    def test_worker_repeats_and_preserves_rejection_details(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, result = root / "manifest.json", root / "result.json"
            replay.write_json(manifest, dict(products=[dict(key="test", identity="abc")], repeats=2))
            with patch.object(replay, "load_product", return_value="abc") as loader:
                self.assertEqual(0, replay.worker(manifest, result))
            self.assertEqual(2, loader.call_count)
            self.assertEqual("PASS", replay.read_json(result)["status"])

    def test_wrong_rejection_fails_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, result = root / "manifest.json", root / "result.json"
            replay.write_json(manifest, dict(products=[dict(key="test", identity="abc", reject="version")]))
            with patch.object(replay, "load_product", side_effect=ValueError("SHA256 mismatch")):
                self.assertEqual(1, replay.worker(manifest, result))
            self.assertEqual("FAIL", replay.read_json(result)["status"])

    def test_domain_external_sha_precedes_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "domain.npz"
            path.write_bytes(b"not an archive")
            fake_module = unittest.mock.Mock()
            with patch.object(replay.importlib, "import_module", return_value=fake_module):
                with self.assertRaisesRegex(ValueError, "external domain archive SHA256 mismatch"):
                    replay.load_product(dict(role="domain", path=str(path), sha256="0" * 64, identity="x"))
            fake_module.load_domain_product.assert_not_called()

    def test_snapshot_detects_byte_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.bin"
            path.write_bytes(b"original")
            before = replay.source_snapshot(directory)
            path.write_bytes(b"changed")
            self.assertNotEqual(before, replay.source_snapshot(directory))

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source", Path(directory) / "output"
            source.mkdir()
            output.mkdir()
            with self.assertRaises(FileExistsError):
                replay.acceptance(source, output)


if __name__ == "__main__":
    unittest.main()
