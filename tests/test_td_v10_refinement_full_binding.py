import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tests import test_audit_td_v10_temporal_refinement as sequence_fixtures
from tools import audit_td_v10_temporal_refinement as auditor
from tools.audit_td_candidate_coupling import read_record


class FullRefinementBindingTests(unittest.TestCase):
    def save_json(self, path, value):
        publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
        return dict(path=str(path.resolve()), expected_sha256=file_sha256(path))

    def fixture(self, root):
        root = Path(root)
        baseline_run, new_run = root / "baseline", root / "new"
        helper = sequence_fixtures.IndependentRefinementTests()
        scenarios_old, scenarios_new = {}, {}
        for direction in ("eastward", "westward"):
            reference, arguments = helper.sequence(baseline_run / (direction + "-1.25s"), 1.25)
            fine, _ = helper.sequence(new_run / (direction + "-0.625s"), .625)
            scenarios_old[direction] = dict(pages={"2.5":[], "1.25":reference}, forcing_identity="b" * 64)
            scenarios_new[direction] = dict(pages=fine, forcing_identity="b" * 64)
        files = {}
        for name in ("source", "hierarchy", "eastward", "westward"):
            path = root / (name + ".npz")
            publish_bytes(path, ("synthetic-" + name).encode("ascii"))
            files[name] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity="a" * 64)
        sources = dict(hierarchy=files["hierarchy"], weather_records={name:files[name] for name in ("eastward", "westward")})
        weather_index = dict(schema="td-native-storm-forcing-index-v1", source=files["source"],
                             cases={name:dict(record=files[name]) for name in ("eastward", "westward")})
        weather_pin = self.save_json(root / "weather-index.json", weather_index)
        sources["weather_index"] = dict(path=weather_pin["path"], sha256=weather_pin["expected_sha256"])
        for name in ("eastward", "westward"):
            scenarios_old[name]["weather_record"] = files[name]
            scenarios_new[name]["weather_record"] = files[name]
        code_names = ("terrain_pipeline/mountain_source_adapter.py", "terrain_pipeline/rainfall_runoff.py",
                      "terrain_pipeline/td_basin_source.py", "terrain_pipeline/td_basin_hierarchy.py",
                      "terrain_pipeline/td_basin_storage_v10.py", "terrain_pipeline/td_basin_storage_v10_io.py",
                      "terrain_pipeline/td_basin_forcing_v10.py", "terrain_pipeline/td_basin_transport_v6.py",
                      "terrain_pipeline/td_native_storm_forcing.py", "terrain_pipeline/mountain_storm_forcing.py",
                      "terrain_pipeline/td_native_weather_storage_inputs.py", "terrain_pipeline/td_basin_storage_compiled.py",
                      "tools/verify_td_native_weather_storage.py", "tools/verify_td_native_weather_storage_v10.py",
                      "tools/verify_td_basin_storage.py")
        codes = {name:file_sha256(auditor.ROOT / name) for name in code_names}
        inputs = dict(steps_s=[2.5, 1.25], code_sha256=codes, depth_gate_m=.001, receiver_gate=.01,
                      job_max_bytes=1073741824, primary_sha256=files["source"]["expected_sha256"],
                      forcing_identities=dict(eastward="b" * 64, westward="b" * 64), **sources)
        baseline = dict(inputs=self.save_json(baseline_run / "run-inputs.json", inputs))
        baseline["index"] = self.save_json(baseline_run / "index.json", dict(schema="td-v10-spatial-weather-hour-pages-index-v1",
                                                                          steps_s=[2.5, 1.25], scenarios=scenarios_old, code_sha256=codes))
        resource_fields = dict(complete=True, peak_rss_bytes=100, peak_private_bytes=200, sample_count=2, monitor_error=None)
        baseline["resource"] = self.save_json(baseline_run / "resource.json", dict(**resource_fields,
            index_sha256=baseline["index"]["expected_sha256"], scope="complete eastward+westward both steps execution"))
        accepted = dict(schema="td-independent-final-spatial-weather-v10-v1", io_chain_accepted=True,
                        index_path=baseline["index"]["path"], index_sha256=baseline["index"]["expected_sha256"],
                        resource_sha256=baseline["resource"]["expected_sha256"], cold_acceptance=dict(io_chain_accepted=True),
                        acceptance_arguments=dict(run_inputs_record=baseline["inputs"], execution_resource_record=baseline["resource"]))
        baseline["acceptance"] = self.save_json(baseline_run / "acceptance.json", accepted)
        status_pin = self.save_json(root / "status.json", dict(schema="td-ten-hour-pipeline-status-v1", state="diagnostic_stop",
                                       deadline_utc="2026-10-03T04:53:05+00:00", baseline_acceptance_record=baseline["acceptance"]))
        runner = auditor.ROOT / "tools/run_td_v10_temporal_refinement.py"
        plan = dict(schema="td-v10-temporal-refinement-plan-v1", baseline_records=baseline, source_records=sources,
                    new_step_s=.625, reference_step_s=1.25, depth_gate_m=.001, receiver_gate=.01,
                    job_max_bytes=1073741824, chunk_max_face_steps=6000000000,
                    expected_new_pages=48, expected_reference_pages=48, expected_baseline_pages=96,
                    pipeline_status_record=status_pin, deadline_utc="2026-10-03T04:53:05+00:00",
                    baseline_code_sha256=codes, runner_sha256=file_sha256(runner),
                    hydraulic_ready=False, transient_converged=False, publishable=False)
        new_inputs = self.save_json(new_run / "run-inputs.json", plan)
        self.save_json(new_run / "execution-code.json", dict(baseline_code_sha256=codes, runner_sha256=file_sha256(runner),
                                                               runner_source=runner.read_text(encoding="utf-8")))
        new_index = self.save_json(new_run / "index.json", dict(schema="td-v10-temporal-refinement-index-v1", scenarios=scenarios_new,
            new_step_s=.625, reference_step_s=1.25, baseline_records=baseline, source_records=sources, code_sha256=codes,
            run_inputs_record=new_inputs, hydraulic_ready=False, transient_converged=False, publishable=False))
        new_resource = self.save_json(new_run / "resource.json", dict(**resource_fields,
            schema="td-v10-temporal-refinement-resource-v1", index_sha256=new_index["expected_sha256"],
            scope="complete new eastward+westward 0.625s 48 pages only", code_sha256=codes,
            within_1GiB=True, job_max_bytes=1073741824))

        def synthetic_record(record):
            path = record["path"]
            if path == files["hierarchy"]["path"]:
                return arguments["topology"], dict(arguments["geometry"], source_identity_sha256="a" * 64)
            if path in (files["eastward"]["path"], files["westward"]["path"]):
                weather_arrays = dict(rain_mm_h=arguments["rain"], valid_mask=arguments["topology"]["valid_mask"],
                                      protected_mask=arguments["topology"]["protected_mask"], time_edges_s=np.arange(25) * 3600.)
                weather_metadata = dict(forcing_identity="b" * 64, plan=dict(dt_s=3600., start_s=0., spacing_m=30.,
                                                                             origin_m_xz=[0., 0.], source_identity="a" * 64))
                return weather_arrays, weather_metadata
            if path == files["source"]["path"]:
                return {}, {}
            return read_record(record)
        return new_run, new_index, new_inputs, new_resource, files, synthetic_record

    def test_complete_auditor_binds_both_executions_and_rejects_missing_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            run, index, inputs, resource, files, reader = self.fixture(directory)
            with patch.object(auditor, "read_record", side_effect=reader), \
                    patch.object(auditor, "numerical_identity", return_value="b" * 64), \
                    patch.object(auditor, "PRIMARY_PATH", Path(files["source"]["path"])), \
                    patch.object(auditor, "PRIMARY_SHA256", files["source"]["expected_sha256"]):
                result = auditor.audit(run, index["expected_sha256"], inputs["expected_sha256"], resource["expected_sha256"])
                self.assertTrue(result["io_chain_accepted"])
                self.assertTrue(result["all_saved_numerical_gates_passed"])
                self.assertTrue(result["separate_execution_resources_authenticated"])
                self.assertFalse(result["physics_changed"])
                changed = json.loads(Path(resource["path"]).read_text(encoding="utf-8"))
                changed["peak_private_bytes"] = 0
                bad = self.save_json(Path(directory) / "bad-resource.json", changed)
                original = auditor.pinned_json
                with patch.object(auditor, "pinned_json", side_effect=lambda record, *args: original(
                        bad if record["path"] == resource["path"] else record, *args)):
                    with self.assertRaisesRegex(ValueError, "resource"):
                        auditor.audit(run, index["expected_sha256"], inputs["expected_sha256"], resource["expected_sha256"])


if __name__ == "__main__":
    unittest.main()
