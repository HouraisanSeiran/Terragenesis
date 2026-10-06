import copy
import json
from pathlib import Path
import tempfile
import unittest

from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.audit_td_native_weather_v10_final import bind_numerical


class FinalV10BindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.run = Path(self.directory.name).resolve()
        self.inputs = dict(weather_records={}, hierarchy=dict(path="fixed-hierarchy", expected_sha256="a" * 64),
                           forcing_identities={})
        self.index = dict(scenarios={})
        self.records = {}
        self.cold = dict(cases={})
        self.reports = {}
        for direction in ("eastward", "westward"):
            weather = dict(path=direction, expected_sha256="b" * 64)
            self.inputs["weather_records"][direction] = weather
            self.inputs["forcing_identities"][direction] = direction
            comparison = dict(max_saved_depth_difference_m=.02, cumulative_receiver_relative_l1=.0001, gate_passed=False)
            comparison_path = self.run / (direction + "-comparison.json")
            comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
            self.index["scenarios"][direction] = comparison
            self.cold["cases"][direction] = dict(numerical_gate_passed=False)
            report = dict(schema="td-independent-spatial-weather-v10-v1", comparison_path=str(comparison_path),
                          comparison_sha256=file_sha256(comparison_path), weather_record=weather,
                          hierarchy_record=self.inputs["hierarchy"], forcing_identity=direction,
                          substeps_s=[2.5, 1.25], saved_frames=25, full_spatial_rain_checked=True,
                          compartment_ledgers_checked=True, checkpoint_chain_checked=True, solver_advanced=False,
                          hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                          page_budget_audits={str(step):dict(whole_period_passed=True) for step in (2.5, 1.25)},
                          max_frame=10, max_cell=42, **comparison)
            self.reports[direction] = report
            self.write_report(direction, report)

    def tearDown(self):
        self.directory.cleanup()

    def write_report(self, direction, report):
        path = self.run / (direction + "-audit.json")
        path.write_text(json.dumps(report), encoding="utf-8")
        self.records[direction] = dict(path=str(path), expected_sha256=file_sha256(path))

    def bind(self):
        return bind_numerical(self.index, self.inputs, self.run, self.records, self.cold)

    def test_failed_numerical_gate_is_preserved(self):
        self.assertFalse(self.bind()["eastward"]["gate_passed"])

    def test_rehashed_report_cannot_upgrade_failed_gate(self):
        changed = copy.deepcopy(self.reports["eastward"])
        changed["gate_passed"] = True
        self.write_report("eastward", changed)
        with self.assertRaisesRegex(ValueError, "reduction disagreement"):
            self.bind()

    def test_report_missing_compartment_audit_rejected(self):
        changed = copy.deepcopy(self.reports["eastward"])
        changed["compartment_ledgers_checked"] = False
        self.write_report("eastward", changed)
        with self.assertRaisesRegex(ValueError, "audit missing"):
            self.bind()

    def test_report_from_other_execution_rejected(self):
        changed = copy.deepcopy(self.reports["westward"])
        changed["comparison_sha256"] = "c" * 64
        self.write_report("westward", changed)
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.bind()

    def test_partial_direction_coverage_rejected(self):
        self.records.pop("westward")
        with self.assertRaisesRegex(ValueError, "both independent"):
            self.bind()

    def test_empty_budget_evidence_rejected(self):
        changed = copy.deepcopy(self.reports["eastward"])
        changed["page_budget_audits"] = {}
        self.write_report("eastward", changed)
        with self.assertRaisesRegex(ValueError, "both period"):
            self.bind()


if __name__ == "__main__":
    unittest.main()
