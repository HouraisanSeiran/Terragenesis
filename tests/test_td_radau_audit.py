import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from dataclasses import asdict

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_storage import OverflowParameters as OverflowParameters
from tools import audit_td_radau_overflow as subject


class RadauAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.parent_directory = self.directory / "parent"
        self.parent_directory.mkdir()
        self.events = {}
        self.topology = {
            "identity_sha256": "topology", "metadata": {"hierarchy_identity_sha256": "hierarchy",
                "source_identity_sha256": "source", "leaf_count": 1},
            "faces": [], "engineering_boundaries": [],
            "arrays": {"leaf_ids": np.array([0]), "leaf_area_m2": np.array([1.]),
                       "curve_offsets": np.array([0, 2]), "curve_level_m": np.array([0., 1.]),
                       "curve_area_m2": np.array([1., 1.])},
        }
        source = self._write(self.parent_directory / "source.dat", "source")
        hierarchy = self._write(self.parent_directory / "hierarchy.dat", "hierarchy")
        topology = self._write(self.parent_directory / "topology.json", "topology")
        pins = {"original_td": self._pin(source),
                "hierarchy": dict(self._pin(hierarchy), identity_sha256="hierarchy")}
        topology_pin = dict(self._pin(topology), identity_sha256="topology")
        parent = {"schema": "td-original-bed-overflow-diagnostic-v2", "input_pins": pins,
                  "topology": topology_pin}
        parent_path = self._write(self.parent_directory / "index.json", json.dumps(parent))
        cases = []
        for name, (rain, duration) in subject.EVENTS.items():
            levels = []
            for level in range(2):
                path = self._write(self.directory / f"{name}-level-{level}.npz", f"{name}/{level}")
                controls = {"max_step_s": 300. / 2**level, "rtol": 5e-7 / 2**level,
                            "atol_stage_m": 2e-7 / 2**level, "flux_atol_m3": .001 / 2**level}
                event = self._event(name, rain, duration, controls)
                self.events[path] = event
                levels.append({"level": level, "controls": controls,
                               "event": dict(self._pin(path), identity_sha256=event["identity_sha256"],
                                             bytes=path.stat().st_size),
                               "work": event["metadata"]["work"]})
                if level:
                    levels[-1]["comparison_with_previous"] = {"passed": True}
            cases.append({"name": name, "levels": levels, "selected_level": 1,
                          "temporal_refinement_passed": True})
        code_names = ('terrain_pipeline/basin_storage.py',
                      'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                      "terrain_pipeline/mountain_source_adapter.py", "tools/audit_td_original_bed_overflow.py",
                      "tools/verify_td_stable_overflow.py", "tools/prepare_td_radau_overflow.py")
        self.index = {"schema": "td-radau-overflow-refinement-v1", "algorithm": subject.ALGORITHM,
                      "status": "ready_for_independent_audit", "parent_index": self._pin(parent_path),
                      "input_pins": pins, "topology": topology_pin, "cases": cases,
                      "code_sha256": {name: file_sha256(subject.ROOT / name) for name in code_names},
                      "resources": {"monitor_error": None, "sample_count": 2, "sample_interval_s": .1,
                          "rss_limit_bytes": 1024**3, "disk_limit_bytes": 2 * 1024**3,
                          "peak_rss_bytes": 1000, "peak_output_disk_bytes": 1000, "elapsed_s": .1,
                          "counted_rhs_face_leaf_work": 4},
                      "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}

    def _write(self, path, value):
        path.write_text(value, encoding="utf-8")
        return path

    def _pin(self, path):
        return {"path": str(path), "sha256": file_sha256(path)}

    def _event(self, name, rain, duration, controls):
        steps = duration // 300
        parameters = OverflowParameters(duration_s=duration)
        rate = rain * parameters.runoff_coefficient / 3_600_000. + parameters.baseflow_mm_per_day / 86_400_000.
        supply = np.full((steps, 1), rate * 300.)
        volume = np.arange(steps + 1, dtype=float)[:, None] * supply[0]
        zeros = np.zeros((steps, 0))
        arrays = {"rain_mm_h": np.full(steps, rain), "stage_m": volume.copy(),
                  "volume_m3": volume, "input_volume_m3": supply,
                  "face_forward_m3": zeros, "face_reverse_m3": zeros.copy(),
                  "face_net_m3": zeros.copy(), "face_volume_m3": zeros.copy(),
                  "engineering_boundary_outflow_m3": zeros.copy(),
                  "balance_residual_m3": np.zeros(steps), "spill_onset_step": np.array([], dtype=int)}
        metadata = {"algorithm": subject.ALGORITHM, "steps": steps, "duration_s": duration,
                    "timestep_s": 300., "topology_identity_sha256": "topology",
                    "hierarchy_identity_sha256": "hierarchy", "source_identity_sha256": "source",
                    "parameters": asdict(parameters),
                    "work": {"rhs_evaluations": 1, "accepted_steps": 1,
                             "maximum_scaled_collocation_defect": 0.,
                             "maximum_inventory_correction_m3": 0., "minimum_inventory_m3": 0.},
                    "hydraulic_ready": False,
                    "transient_converged": False, "natural_outlet_verified": False, "publishable": False,
                    **controls}
        return {"identity_sha256": f"{name}/{controls['max_step_s']}",
                "arrays": arrays, "metadata": metadata}

    def _audit(self):
        index_path = self._write(self.directory / "index.json", json.dumps(self.index))

        def load_event(path, *, expected_sha256, expected_identity, topology):
            if file_sha256(path) != expected_sha256:
                raise ValueError("event SHA mismatch")
            event = self.events[Path(path)]
            self.assertEqual(event["identity_sha256"], expected_identity)
            self.assertIs(topology, self.topology)
            return event

        with patch.object(subject, "load_basin_hierarchy", return_value={
                "identity_sha256": "hierarchy", "metadata": {"source_identity_sha256": "source"}}), \
             patch.object(subject, "load_overflow_topology", return_value=self.topology), \
             patch.object(subject, "load_radau_overflow", side_effect=load_event), \
             patch('terrain_pipeline.basin_storage.simulate_radau_overflow',
                   side_effect=AssertionError("solver forbidden")), \
             patch("tools.verify_td_stable_overflow.compare_events",
                   side_effect=AssertionError("comparison forbidden")):
            return subject.audit(self.directory, file_sha256(index_path))

    def test_cold_read_checks_all_levels_and_writes_only_report(self):
        report = self._audit()
        self.assertEqual(report["status"], "passed")
        self.assertEqual([len(case["levels"]) for case in report["cases"]], [2, 2])
        self.assertFalse(report["publishable"])
        self.assertTrue((self.directory / "independent-audit.json").exists())

    def test_tampered_event_hash_is_rejected(self):
        self.index["cases"][0]["levels"][0]["event"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "event SHA mismatch"):
            self._audit()
        self.assertFalse((self.directory / "independent-audit.json").exists())

    def test_incomplete_event_set_is_rejected(self):
        self.index["cases"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete event set"):
            self._audit()

    def test_false_convergence_is_rejected(self):
        self.index["cases"][0]["selected_level"] = 0
        with self.assertRaisesRegex(ValueError, "false convergence"):
            self._audit()

    def test_unmonitored_resources_are_rejected(self):
        self.index["resources"]["sample_count"] = 0
        with self.assertRaisesRegex(ValueError, "monitoring failed"):
            self._audit()

    def test_negative_directional_quadrature_is_rejected(self):
        self.events[next(iter(self.events))]["arrays"]["engineering_boundary_outflow_m3"] = np.full((288, 1), -1.)
        with self.assertRaisesRegex(ValueError, "negative directional exchange"):
            self._audit()

    def test_negative_inventory_is_rejected(self):
        event = self.events[next(iter(self.events))]
        event["arrays"]["volume_m3"][1, 0] = -1e-12
        with self.assertRaisesRegex(ValueError, "negative inventory"):
            self._audit()

    def test_changed_reservoir_model_is_rejected(self):
        event = self.events[next(iter(self.events))]
        event["metadata"]["parameters"]["runoff_coefficient"] = .5
        with self.assertRaisesRegex(ValueError, "model parameters changed"):
            self._audit()


if __name__ == "__main__":
    unittest.main()
