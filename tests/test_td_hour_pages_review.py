import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import numpy as np
from unittest.mock import patch

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_hour_pages_review import export_hour_pages_review, load_hour_pages_review, _hash, MAX_BYTES
from tests.test_td_hour_pages_acceptance_io import fixture, write_json


class HourPagesReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.index, cls.arguments = fixture(cls.root, rain_rate=1.)
        cls.input_index = cls.root / "index.json"
        cls.destination = cls.root / "review"
        cls.result = export_hour_pages_review(cls.input_index, cls.destination, acceptance_arguments=cls.arguments)
        cls.original_index = (cls.destination / "index.json").read_bytes()
        cls.default_output_bytes = sum(path.stat().st_size for path in cls.destination.iterdir())
        cls.default_artifact_count = len(cls.result["pages"])

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        (self.destination / "index.json").write_bytes(self.original_index)

    def load(self, expected_identity=None):
        path = self.destination / "index.json"
        return load_hour_pages_review(path, expected_sha256=file_sha256(path), expected_identity=expected_identity or self.result["identity_sha256"], input_index=self.input_index, acceptance_arguments=self.arguments)

    def test_native25frames_hour_integrals_membership(self):
        result = self.load()
        for scenario in ("ordinary", "strong"):
            for step in (1.25,):
                frames = [record["frame_index"] for record in result["pages"] if record["kind"] == "native_states" and record["scenario"] == scenario and record["step_s"] == step]
                self.assertEqual(frames, list(range(25)))
                hours = [record["frame_index"] for record in result["pages"] if record["kind"] == "hour_faces" and record["scenario"] == scenario and record["step_s"] == step]
                self.assertEqual(hours, [])
        mapping = next(record for record in result["pages"] if record["kind"] == "cell_membership")
        rows = np.fromfile(self.destination / mapping["file"], dtype="<i8").reshape(mapping["shape"])
        self.assertEqual(rows[:, 0].tolist(), [0, 1, 2])
        self.assertTrue(all(record["bytes"] <= MAX_BYTES for record in result["pages"]))
        self.assertFalse(result["flags"]["hydraulic_ready"])
        final_pin = next(record for record in result["pages"] if record["kind"] == "native_states" and record["frame_index"] == 24)
        rows = np.fromfile(self.destination / final_pin["file"], dtype="<f8").reshape(final_pin["shape"])
        self.assertEqual(rows[0, 0], .024)
        self.assertEqual(rows[1, 0] + 2., 2.024)
        self.assertFalse(any(record["step_s"] == 2.5 for record in result["pages"]))

    def test_rehashed_frame_value_and_time_rejected(self):
        record = next(record for record in self.result["pages"] if record["kind"] == "native_states")
        target = self.destination / record["file"]
        original = target.read_bytes()
        try:
            values = np.frombuffer(original, dtype="<f8").copy()
            values[0] += 1
            target.write_bytes(values.tobytes())
            index = json.loads(self.original_index)
            pin = next(pin for pin in index["pages"] if pin["file"] == record["file"])
            pin.update(expected_sha256=file_sha256(target), expected_identity="0" * 64, bytes=target.stat().st_size, frame_index=1)
            index.pop("identity_sha256")
            index["identity_sha256"] = _hash(index)
            write_json(self.destination / "index.json", index)
            with self.assertRaises(ValueError):
                self.load(index["identity_sha256"])
        finally:
            target.write_bytes(original)

    def test_missing_extra_and_unsafe_page(self):
        extra = self.destination / "page-999999.json"
        extra.write_text("{}")
        try:
            with self.assertRaises(ValueError):
                self.load()
        finally:
            extra.unlink()
        value = json.loads(self.original_index)
        value["pages"][0]["file"] = "../index.json"
        value.pop("identity_sha256")
        value["identity_sha256"] = _hash(value)
        write_json(self.destination / "index.json", value)
        with self.assertRaises(ValueError):
            self.load(value["identity_sha256"])

    def test_acceptance_mandatory_partial_and_unknown(self):
        path = self.root / "partial.json"
        path.write_text("{}")
        destination = self.root / "rejected"
        with self.assertRaises(ValueError):
            export_hour_pages_review(path, destination, acceptance_arguments=self.arguments)
        self.assertFalse(destination.exists())
        original = self.input_index.read_bytes()
        try:
            value = json.loads(original)
            value["schema"] = "unknown"
            record = write_json(self.input_index, value)
            arguments = copy.deepcopy(self.arguments)
            arguments["expected_sha256"] = record["expected_sha256"]
            with self.assertRaises(ValueError):
                export_hour_pages_review(self.input_index, destination, acceptance_arguments=arguments)
        finally:
            self.input_index.write_bytes(original)

    def test_atomic_failed_export_leaves_no_final(self):
        destination = self.root / "atomic-failed"
        with patch("terrain_pipeline.td_hour_pages_review._encode", side_effect=ValueError("budget")):
            with self.assertRaises(ValueError):
                export_hour_pages_review(self.input_index, destination, acceptance_arguments=self.arguments)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob(".hour-review-*")), [])

    def test_failed_refinement_is_explicit_diagnostic(self):
        from terrain_pipeline.td_hour_pages_review import _manifest
        from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
        accepted = {"scenarios": {"ordinary": {"numerical_gate_passed": False}, "strong": {"numerical_gate_passed": True}}}
        result = _manifest(self.input_index, self.arguments, accepted, load_basin_hierarchy(**self.arguments["hierarchy_record"]), [])
        self.assertTrue(result["diagnostic_only"])
        self.assertFalse(result["flags"]["transient_converged"])

    def test_2048_row_pagination(self):
        from terrain_pipeline.td_hour_pages_review import _chunks
        pages = list(_chunks("fixture", ({"cell_id": cell} for cell in range(4097))))
        self.assertEqual([len(page["rows"]) for page in pages], [2048, 2048, 1])
        self.assertEqual([page["chunk_index"] for page in pages], [0, 1, 2])

    def test_output_budget_and_selected_steps_are_predeclared(self):
        actual_bytes = sum(path.stat().st_size for path in self.destination.iterdir())
        self.assertEqual(actual_bytes, self.result["artifact_bytes"] + (self.destination / "index.json").stat().st_size)
        self.assertLessEqual(actual_bytes, self.result["output_budget_bytes"])
        with self.assertRaisesRegex(ValueError, "estimate"):
            export_hour_pages_review(self.input_index, self.root / "too-small", acceptance_arguments=self.arguments, output_budget_bytes=1)
        self.assertFalse((self.root / "too-small").exists())
        with self.assertRaises(ValueError):
            self.load_selected_coarse()
        self.assertFalse((self.root / "too-small").exists())

    def load_selected_coarse(self):
        path = self.destination / "index.json"
        return load_hour_pages_review(path, expected_sha256=file_sha256(path), expected_identity=self.result["identity_sha256"], input_index=self.input_index, acceptance_arguments=self.arguments, selected_steps_s=(2.5,))

    def test_optional_hour_flux_is_binary_exact(self):
        destination = self.root / "with-flux"
        result = export_hour_pages_review(self.input_index, destination, acceptance_arguments=self.arguments, include_hour_flux=True)
        load_hour_pages_review(destination / "index.json", expected_sha256=file_sha256(destination / "index.json"), expected_identity=result["identity_sha256"], input_index=self.input_index, acceptance_arguments=self.arguments, include_hour_flux=True)
        record = next(record for record in result["pages"] if record["kind"] == "hour_faces")
        values = np.fromfile(destination / record["file"], dtype="<f8").reshape(record["shape"])
        self.assertEqual(values.shape, (2, 4))
        self.assertTrue(np.all(values == 0))

    def test_fresh_subprocess_review_without_solver(self):
        code = """import sys,importlib.abc,json
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='numba' or fullname.startswith('numba.') or fullname.startswith('terrain_pipeline.td_basin_storage_continuation') or fullname in {'terrain_pipeline.td_basin_storage','terrain_pipeline.td_basin_transport_v6','terrain_pipeline.td_basin_storage_v4'}: raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from terrain_pipeline.td_hour_pages_review import load_hour_pages_review
from terrain_pipeline.mountain_source_adapter import file_sha256
result=load_hour_pages_review(sys.argv[1],expected_sha256=file_sha256(sys.argv[1]),expected_identity=sys.argv[2],input_index=sys.argv[3],acceptance_arguments=json.loads(sys.argv[4]))
assert result['frames']==25 and 'numba' not in sys.modules
"""
        completed = subprocess.run([sys.executable, "-c", code, str(self.destination / "index.json"), self.result["identity_sha256"], str(self.input_index), json.dumps(self.arguments)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
