import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terrain_pipeline.common_infra import file_sha256
from tools.run_td_v10_temporal_refinement import prepare, STEP_S, REFERENCE_STEP_S


class TemporalRefinementTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        baseline = root / "baseline"
        baseline.mkdir()
        status = root / "status.json"
        status.write_text(json.dumps(dict(schema="td-ten-hour-pipeline-status-v1", state="diagnostic_stop", pid=0,
                                          deadline_utc=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat())))
        source = root / "source.npz"
        source.write_bytes(b"source")
        pin = dict(path=str(source), expected_sha256=file_sha256(source), expected_identity="a" * 64)
        weather_index = dict(path=str(source), sha256=file_sha256(source))
        code = {f"frozen-{index}.py": "a" * 64 for index in range(15)}
        inputs = dict(schema="td-v10-spatial-weather-run-inputs-v1", steps_s=[2.5, 1.25],
                      hierarchy=pin, weather_index=weather_index,
                      weather_records=dict(eastward=pin, westward=pin),
                      forcing_identities=dict(eastward="b" * 64, westward="c" * 64),
                      primary_sha256="d" * 64, code_sha256=code,
                      budgets={"1.25": {"chunk_face_steps": 2880}}, chunk_max_face_steps=6000000000,
                      job_max_bytes=1073741824,
                      physics_version="unchanged-v10", depth_gate_m=.001, receiver_gate=.01)
        scenarios = {}
        for direction in ("eastward", "westward"):
            pages = {}
            for step in ("2.5", "1.25"):
                pages[step] = [dict(hour=hour, storage=pin, checkpoint=pin, elapsed_s=1.,
                                    forcing_identity=inputs["forcing_identities"][direction]) for hour in range(24)]
            scenarios[direction] = dict(pages=pages, weather_record=pin,
                                        forcing_identity=inputs["forcing_identities"][direction])
        index = dict(schema="td-v10-spatial-weather-hour-pages-index-v1", steps_s=[2.5, 1.25],
                     scenarios=scenarios, code_sha256=code)
        for name, value in (("run-inputs", inputs), ("index", index)):
            (baseline / f"{name}.json").write_text(json.dumps(value))
        resource = dict(schema="td-v10-spatial-weather-resource-v1", index_sha256=file_sha256(baseline / "index.json"),
                        scope="complete eastward+westward both steps execution", complete=True,
                        monitor_error=None, sampling_interval_s=2, sample_count=1,
                        peak_rss_bytes=100, peak_private_bytes=100)
        (baseline / "resource.json").write_text(json.dumps(resource))
        acceptance_path = root / "acceptance.json"
        acceptance = dict(schema="td-independent-final-spatial-weather-v10-v1", io_chain_accepted=True,
                          index_path=str(baseline / "index.json"), index_sha256=file_sha256(baseline / "index.json"),
                          resource_sha256=file_sha256(baseline / "resource.json"),
                      acceptance_arguments=dict(
                          run_inputs_record=dict(path=str(baseline / "run-inputs.json"), expected_sha256=file_sha256(baseline / "run-inputs.json")),
                          execution_resource_record=dict(path=str(baseline / "resource.json"), expected_sha256=file_sha256(baseline / "resource.json"))),
                      cold_acceptance=dict(io_chain_accepted=True))
        acceptance_path.write_text(json.dumps(acceptance))
        deadline = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        arguments = (baseline, file_sha256(baseline / "index.json"), file_sha256(baseline / "resource.json"),
                     file_sha256(baseline / "run-inputs.json"),
                     dict(path=str(acceptance_path), expected_sha256=file_sha256(acceptance_path)),
                     status, deadline, root / "new")
        return arguments, index, resource, inputs

    def test_prepare_has_fixed_index_contract_and_does_not_simulate(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, _, _ = self.fixture(directory)
            with patch("tools.run_td_v10_temporal_refinement._check_code"), \
                    patch("tools.run_td_v10_temporal_refinement.file_sha256", wraps=file_sha256) as digest, \
                    patch('terrain_pipeline.basin_storage.PRIMARY_PATH', args[0] / "index.json"):
                original_sha = args[0] / "index.json"
                inputs_path = args[0] / "run-inputs.json"
                data = json.loads(inputs_path.read_text())
                data["primary_sha256"] = file_sha256(original_sha)
                inputs_path.write_text(json.dumps(data))
                acceptance = json.loads(Path(args[4]["path"]).read_text())
                acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"] = file_sha256(inputs_path)
                Path(args[4]["path"]).write_text(json.dumps(acceptance))
                updated = (*args[:3], file_sha256(inputs_path),
                           dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), *args[5:])
                plan = prepare(*updated)
                self.assertEqual(plan["new_step_s"], STEP_S)
                self.assertEqual(plan["reference_step_s"], REFERENCE_STEP_S)
                self.assertEqual(plan["expected_new_pages"], 48)
                self.assertEqual(plan["estimated_new_elapsed_s"], 96.)
                self.assertTrue(plan["execution_ready"])
                self.assertFalse(Path(plan["output"]).exists())
                self.assertGreater(digest.call_count, 96)

    def test_rejects_missing_and_incomplete_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            args, index, resource, _ = self.fixture(directory)
            with patch("tools.run_td_v10_temporal_refinement._check_code"):
                with self.assertRaises(ValueError):
                    prepare(*args[:1], "0" * 64, *args[2:])
                index["scenarios"]["eastward"]["pages"]["1.25"].pop()
                (args[0] / "index.json").write_text(json.dumps(index))
                resource["index_sha256"] = file_sha256(args[0] / "index.json")
                (args[0] / "resource.json").write_text(json.dumps(resource))
                acceptance = json.loads(Path(args[4]["path"]).read_text())
                acceptance["index_sha256"] = file_sha256(args[0] / "index.json")
                acceptance["resource_sha256"] = file_sha256(args[0] / "resource.json")
                acceptance["acceptance_arguments"]["execution_resource_record"]["expected_sha256"] = file_sha256(args[0] / "resource.json")
                Path(args[4]["path"]).write_text(json.dumps(acceptance))
                updated = (args[0], file_sha256(args[0] / "index.json"), file_sha256(args[0] / "resource.json"),
                           args[3], dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), *args[5:])
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    prepare(*updated)

    def test_rejects_resource_code_status_and_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, resource, _ = self.fixture(directory)
            resource["complete"] = False
            (args[0] / "resource.json").write_text(json.dumps(resource))
            acceptance = json.loads(Path(args[4]["path"]).read_text())
            acceptance["resource_sha256"] = file_sha256(args[0] / "resource.json")
            acceptance["acceptance_arguments"]["execution_resource_record"]["expected_sha256"] = file_sha256(args[0] / "resource.json")
            Path(args[4]["path"]).write_text(json.dumps(acceptance))
            updated = (args[0], args[1], file_sha256(args[0] / "resource.json"),
                       args[3], dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), *args[5:])
            with self.assertRaisesRegex(ValueError, "resource"):
                prepare(*updated)
            resource["complete"] = True
            (args[0] / "resource.json").write_text(json.dumps(resource))
            acceptance = json.loads(Path(args[4]["path"]).read_text())
            acceptance["resource_sha256"] = file_sha256(args[0] / "resource.json")
            acceptance["acceptance_arguments"]["execution_resource_record"]["expected_sha256"] = file_sha256(args[0] / "resource.json")
            Path(args[4]["path"]).write_text(json.dumps(acceptance))
            updated = (args[0], args[1], file_sha256(args[0] / "resource.json"),
                       args[3], dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), *args[5:])
            with self.assertRaisesRegex(ValueError, "frozen code"):
                prepare(*updated)
            args[5].write_text(json.dumps(dict(schema="td-ten-hour-pipeline-status-v1", state="running", pid=0,
                                               deadline_utc=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat())))
            with self.assertRaisesRegex(ValueError, "active"):
                prepare(*updated)
            args[5].write_text(json.dumps(dict(schema="td-ten-hour-pipeline-status-v1", state="diagnostic_stop", pid=0,
                                               deadline_utc=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat())))
            expired = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
            with self.assertRaises(TimeoutError):
                prepare(*updated[:6], expired, updated[7])

    def test_rejects_changed_gates_acceptance_path_and_late_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, _, inputs = self.fixture(directory)
            with patch("tools.run_td_v10_temporal_refinement._check_code"):
                inputs["depth_gate_m"] = .002
                (args[0] / "run-inputs.json").write_text(json.dumps(inputs))
                acceptance = json.loads(Path(args[4]["path"]).read_text())
                acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"] = file_sha256(args[0] / "run-inputs.json")
                Path(args[4]["path"]).write_text(json.dumps(acceptance))
                updated = (*args[:3], file_sha256(args[0] / "run-inputs.json"),
                           dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), *args[5:])
                with self.assertRaisesRegex(ValueError, "inputs/resource"):
                    prepare(*updated)
                inputs["depth_gate_m"] = .001
                (args[0] / "run-inputs.json").write_text(json.dumps(inputs))
                acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"] = file_sha256(args[0] / "run-inputs.json")
                acceptance["acceptance_arguments"]["run_inputs_record"]["path"] = str(args[0] / "wrong.json")
                Path(args[4]["path"]).write_text(json.dumps(acceptance))
                updated = (*args[:3], file_sha256(args[0] / "run-inputs.json"),
                           dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), *args[5:])
                with self.assertRaisesRegex(ValueError, "full-final"):
                    prepare(*updated)
                acceptance["acceptance_arguments"]["run_inputs_record"]["path"] = str(args[0] / "run-inputs.json")
                Path(args[4]["path"]).write_text(json.dumps(acceptance))
                later = (datetime.now(timezone.utc) + timedelta(hours=7)).isoformat()
                updated = (*args[:3], file_sha256(args[0] / "run-inputs.json"),
                           dict(path=args[4]["path"], expected_sha256=file_sha256(args[4]["path"])), args[5], later, args[7])
                with self.assertRaisesRegex(ValueError, "exceeds pipeline deadline"):
                    prepare(*updated)


if __name__ == "__main__":
    unittest.main()
