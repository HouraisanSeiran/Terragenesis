import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.continue_td_weather_pipeline import Pipeline, write_json


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / "source.json"
        source.write_text("{}", encoding="utf-8")
        record = dict(path=str(source), expected_sha256=file_sha256(source))
        self.configuration = dict(schema="td-ten-hour-pipeline-config-v1", weather_index_record=record,
            candidate_topology_records={name:record for name in ("valley_incision", "source_deposition")}, code_sha256={})

    def pipeline(self):
        return Pipeline(self.configuration, self.root / "run", 1.)

    def test_baseline_false_gate_never_calls_candidates(self):
        pipeline = self.pipeline()
        with patch.object(pipeline, "baseline", return_value=({}, False)), patch.object(pipeline, "candidates") as candidates:
            result = pipeline.execute()
        candidates.assert_not_called()
        self.assertEqual(result["state"], "diagnostic_stop")
        self.assertFalse(result["publishable"])

    def test_timeout_and_subprocess_failure_keep_terminal_status(self):
        pipeline = self.pipeline()
        with patch.object(pipeline, "baseline", side_effect=subprocess.TimeoutExpired("fixed", 1)):
            self.assertEqual(pipeline.execute()["state"], "time_limit")
        with patch.object(pipeline, "baseline", side_effect=RuntimeError("failed fixed stage")):
            with self.assertRaises(RuntimeError):
                pipeline.execute()
        self.assertEqual(json.loads((pipeline.output / "status.json").read_text())["state"], "failed")

    def test_invalid_hours_and_changed_source_rejected_before_output(self):
        for hours in (0, -1, 11, float("nan"), float("inf"), True):
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                Pipeline(self.configuration, self.root / "invalid", hours)
        Path(self.configuration["weather_index_record"]["path"]).write_text("changed")
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.pipeline()
        self.assertFalse((self.root / "run").exists())

    def test_call_deadline_and_failed_process_cannot_complete_stage(self):
        pipeline = self.pipeline()
        pipeline.deadline = 0
        with patch("tools.continue_td_weather_pipeline.subprocess.run") as runner:
            with self.assertRaises(TimeoutError):
                pipeline.call("stage", "tools/fixed.py", [])
            runner.assert_not_called()
        pipeline.deadline = 10 ** 12
        with patch("tools.continue_td_weather_pipeline.subprocess.run", return_value=subprocess.CompletedProcess([], 2)):
            with self.assertRaises(RuntimeError):
                pipeline.call("stage", "tools/fixed.py", [])
        self.assertEqual(pipeline.status["completed_stages"], [])

    def test_candidate_false_gate_stops_second_solver_and_selection(self):
        pipeline = self.pipeline()
        destination = pipeline.output / "valley_incision"
        write_json(destination / "index.json", dict(identity_sha256="a" * 64))
        calls = []
        def call(name, script, arguments):
            calls.append(name)
            if "-audit-" in name:
                return dict(path="raw-report", expected_sha256="b" * 64, gate_passed=False)
            return {}
        with patch.object(pipeline, "call", side_effect=call):
            self.assertFalse(pipeline.candidates({}))
        self.assertIn("valley_incision-audit-westward", calls)
        self.assertNotIn("source_deposition-run", calls)
        self.assertNotIn("candidate-select", calls)


if __name__ == "__main__":
    unittest.main()
