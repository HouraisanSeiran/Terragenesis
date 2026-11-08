import copy
import json
from pathlib import Path
import tempfile
import unittest
import builtins
from unittest.mock import patch

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_surface_reaches import _hash
from terrain_pipeline.td_candidate_weather_jobs import prepare_candidate_weather_jobs, load_candidate_weather_plan, run_candidate_weather_job, PHYSICS, FLAGS
from tests import test_td_native_weather_storage_v10_io as weather_fixture
from terrain_pipeline.td_candidate_weather_jobs import publish_candidate_weather_selection, load_candidate_weather_selection, export_candidate_weather_review
from terrain_pipeline.td_candidate_weather_jobs import execution_dependency_names, _check_execution_dependencies, ROOT


class CandidateWeatherPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.baseline = self.root/"baseline.json"
        self.baseline.write_text("{}")
        self.baseline_record = dict(path=str(self.baseline), expected_sha256=file_sha256(self.baseline))
        self.topologies = {}
        for name in ("valley_incision", "source_deposition"):
            path = self.root/(name+".json")
            path.write_text("{}")
            self.topologies[name] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity="a"*64)
        self.output = self.root/"plan"

    def _prepared(self, ready=False):
        result = dict(schema="td-candidate-native-weather-plan-v1", baseline_acceptance_record=self.baseline_record,
            candidate_topology_records=self.topologies, declared_steps_s=[2.5, 1.25], execution_ready=ready,
            parameters=PHYSICS, flags=FLAGS, selection="baseline pending", solver_advanced=False,
            code_sha256={name: file_sha256(ROOT / name) for name in execution_dependency_names()})
        result["identity_sha256"] = _hash(result)
        return result

    def test_plan_publication_cold_and_default_no_execution(self):
        expected = self._prepared()
        with patch("terrain_pipeline.td_candidate_weather_jobs._plan", return_value=expected), patch("terrain_pipeline.td_candidate_weather_jobs._recheck_publication"):
            actual = prepare_candidate_weather_jobs(self.baseline_record, self.topologies, self.output)
            record = dict(path=str(self.output/"index.json"), expected_sha256=file_sha256(self.output/"index.json"), expected_identity=actual["identity_sha256"])
            self.assertEqual(load_candidate_weather_plan(record), expected)
            with patch.dict("sys.modules", {"terrain_pipeline.td_basin_storage_v10":None}):
                status = run_candidate_weather_job(record, self.root/"run", candidate_id="valley_incision")
            self.assertFalse(status["solver_advanced"])
            self.assertFalse((self.root/"run").exists())

    def test_false_baseline_refuses_execution_before_solver(self):
        with patch("terrain_pipeline.td_candidate_weather_jobs.load_candidate_weather_plan", return_value=self._prepared()):
            with self.assertRaisesRegex(ValueError, "baseline all numerical gates"):
                run_candidate_weather_job({}, self.root/"run", candidate_id="valley_incision", execute=True)
        self.assertFalse((self.root/"run").exists())

    def test_rehashed_readiness_and_missing_candidate_rejected(self):
        expected = self._prepared()
        with patch("terrain_pipeline.td_candidate_weather_jobs._plan", return_value=expected), patch("terrain_pipeline.td_candidate_weather_jobs._recheck_publication"):
            actual = prepare_candidate_weather_jobs(self.baseline_record, self.topologies, self.output)
            forged = copy.deepcopy(actual)
            forged["execution_ready"] = True
            forged.pop("identity_sha256")
            forged["identity_sha256"] = _hash(forged)
            path = self.output/"index.json"
            path.write_text(json.dumps(forged))
            with self.assertRaisesRegex(ValueError, "semantic readiness"):
                load_candidate_weather_plan(dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=forged["identity_sha256"]))
        from terrain_pipeline.td_candidate_weather_jobs import _plan
        with self.assertRaises(ValueError):
            _plan(self.baseline_record, {"valley_incision":self.topologies["valley_incision"]}, (2.5, 1.25))

    def test_resource_failure_never_publishes_plan(self):
        with patch("terrain_pipeline.td_candidate_weather_jobs._plan", return_value=self._prepared()):
            with patch("terrain_pipeline.td_candidate_weather_jobs._memory", side_effect=MemoryError("private")):
                with self.assertRaises(MemoryError):
                    prepare_candidate_weather_jobs(self.baseline_record, self.topologies, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".candidate-weather-plan-*")), [])

    def test_recursive_freeze_includes_execution_and_monitor_dependencies(self):
        names = execution_dependency_names()
        required = ("td_basin_transport_v6", "td_basin_storage_v6", "td_basin_storage_v5",
                    "td_basin_storage_v4", "td_basin_storage_v3", "td_basin_forcing_v10",
                    "td_basin_storage_v10_io", "td_basin_hierarchy", "td_basin_source")
        for name in required:
            self.assertIn("terrain_pipeline/" + name + ".py", names)
        self.assertIn("tools/verify_td_native_weather_storage.py", names)
        self.assertIn("tools/run_td_candidate_weather_jobs.py", names)
        codes = {name: file_sha256(ROOT / name) for name in names}
        _check_execution_dependencies(codes)
        codes["terrain_pipeline/td_basin_transport_v6.py"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "frozen dependency changed"):
            _check_execution_dependencies(codes)
        codes.pop("terrain_pipeline/td_basin_transport_v6.py")
        with self.assertRaisesRegex(ValueError, "recursive dependency set"):
            _check_execution_dependencies(codes)


if __name__ == "__main__":
    unittest.main()


class CandidateWeatherAccountsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = weather_fixture.NativeWeatherV10IoTests()
        cls.fixture.setUp()
        cls.root = cls.fixture.root
        cls.arguments = cls.fixture._whole_fixture()
        index = json.loads((cls.root/"index.json").read_text())
        cls.baseline_record = dict(path=str(cls.root/"baseline-acceptance.json"), expected_sha256="a"*64)
        cls.plan = dict(schema="td-candidate-native-weather-plan-v1", execution_ready=True,
            baseline_numerical_gate_passed=True, baseline_acceptance_record=cls.baseline_record,
            candidates={name:dict(hierarchy_record=cls.arguments["hierarchy_record"],
                source_record=cls.arguments["source_record"]) for name in ("valley_incision", "source_deposition")},
            forcing_identities={name:value["forcing_identity"] for name, value in index["scenarios"].items()},
            weather_index_record=cls.arguments["weather_index_record"], original_weather_source_record=cls.arguments["source_record"],
            runoff_parameters=cls.fixture.runoff,
            code_sha256={name: file_sha256(ROOT / name) for name in execution_dependency_names()})
        cls.final_records, cls.report_records = {}, {}
        def write(path, value, identity_required=False):
            if identity_required:
                value["identity_sha256"] = _hash(value)
            path.write_text(json.dumps(value), encoding="utf8")
            record = dict(path=str(path), expected_sha256=file_sha256(path))
            if identity_required:
                record["expected_identity"] = value["identity_sha256"]
            return record
        cls.plan_record = write(cls.root / "candidate-plan.json", cls.plan, True)
        for name in ("valley_incision", "source_deposition"):
            resource = write(cls.root/(name+"-resource.json"), dict(schema="td-candidate-weather-execution-resource-v1", complete=True,
                monitor_error=None, sampling_interval_s=2, sample_count=1, peak_rss_bytes=1000000, peak_private_bytes=1000000))
            value = dict(schema="td-candidate-native-weather-execution-v1", plan_record=cls.plan_record, candidate_id=name,
                candidates=cls.plan["candidates"][name], flags=FLAGS, forcing_identities=cls.plan["forcing_identities"], steps_s=[2.5, 1.25],
                code_sha256=cls.plan["code_sha256"], resource_record=resource, pages={direction:item["pages"] for direction, item in index["scenarios"].items()})
            record = write(cls.root/(name+"-index.json"), value, True)
            cls.final_records[name] = record
            cls.report_records[name] = {}
            for direction in ("eastward", "westward"):
                report = dict(schema="td-independent-candidate-weather-v1", candidate_final_record=record, candidate_id=name, direction=direction,
                    hierarchy_record=cls.arguments["hierarchy_record"], forcing_identity=cls.plan["forcing_identities"][direction],
                    max_saved_depth_difference_m=0., cumulative_receiver_relative_l1=0., gate_passed=True, solver_advanced=False,
                    full_spatial_rain_checked=True, compartment_ledgers_checked=True, checkpoint_chain_checked=True, whole_period_budget_passed=True)
                cls.report_records[name][direction] = write(cls.root/(name+"-"+direction+"-audit.json"), report)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDown()

    def _boundaries(self):
        return patch("terrain_pipeline.td_candidate_weather_jobs._baseline", return_value=({}, {}, True)), patch("terrain_pipeline.td_candidate_weather_jobs.load_candidate_weather_plan", return_value=self.plan)

    def _publish(self, directory):
        with patch("terrain_pipeline.td_candidate_weather_jobs._recheck_publication"):
            return publish_candidate_weather_selection(directory, baseline_acceptance_record=self.baseline_record,
                candidate_final_records=self.final_records, independent_numerical_records=self.report_records)

    def test_complete_saved_accounts_selection_and_native_review(self):
        first, second = self._boundaries()
        original_import = builtins.__import__
        forbidden = ("numba", "terrain_pipeline.td_basin_storage_v10", "terrain_pipeline.td_basin_forcing_v10",
                     "terrain_pipeline.td_basin_storage_compiled", "terrain_pipeline.td_basin_storage_compiled_driver",
                     "terrain_pipeline.td_basin_transport_v6", "terrain_pipeline.td_basin_storage_v6",
                     "terrain_pipeline.td_basin_storage_v5", "terrain_pipeline.td_basin_storage_v4",
                     "terrain_pipeline.td_basin_storage_v3")
        def pure_import(name, *args, **kwargs):
            if name in forbidden or name.startswith("numba."):
                raise AssertionError("pure IO imported solver: " + name)
            return original_import(name, *args, **kwargs)
        with first, second, patch("terrain_pipeline.td_candidate_weather_jobs._recheck_publication"), patch("builtins.__import__", side_effect=pure_import):
            directory = self.root/"candidate-selection"
            result = self._publish(directory)
            record = dict(path=str(directory/"index.json"), expected_sha256=file_sha256(directory/"index.json"), expected_identity=result["identity_sha256"])
            loaded = load_candidate_weather_selection(record["path"], expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"],
                baseline_acceptance_record=self.baseline_record, candidate_final_records=self.final_records, independent_numerical_records=self.report_records)
            self.assertEqual(loaded["selection"], "baseline pending")
            review = export_candidate_weather_review(record, self.root/"candidate-review")
            self.assertEqual(review["frames"], 25)
            self.assertFalse(review["water_interpolation"])

    def test_report_and_partial_execution_rehashed_rejected(self):
        first, second = self._boundaries()
        record = self.final_records["valley_incision"]
        path = Path(record["path"])
        raw = path.read_bytes()
        records = copy.deepcopy(self.final_records)
        value = json.loads(raw)
        value["pages"]["eastward"]["2.5"].pop()
        value.pop("identity_sha256")
        value["identity_sha256"] = _hash(value)
        path.write_text(json.dumps(value), encoding="utf8")
        records["valley_incision"].update(expected_sha256=file_sha256(path), expected_identity=value["identity_sha256"])
        try:
            with first, second:
                with self.assertRaisesRegex(ValueError, "complete24hour"):
                    publish_candidate_weather_selection(self.root/"partial-rejected", baseline_acceptance_record=self.baseline_record,
                        candidate_final_records=records, independent_numerical_records=self.report_records)
        finally:
            path.write_bytes(raw)
        self.assertFalse((self.root/"partial-rejected").exists())
