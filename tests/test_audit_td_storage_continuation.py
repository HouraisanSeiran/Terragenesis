import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, save_bundle
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import checkpointio_save_checkpoint as save_checkpoint
from terrain_pipeline.basin_storage import continuation_simulate as simulate_basin_storage
from terrain_pipeline.basin_storage import continuation_save_storage as save_storage
from tools.audit_td_storage_continuation import audit_scenario


class IndependentContinuationAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        hierarchy = build_basin_hierarchy(make_td_source(np.zeros((2, 2)), spacing_m=30))
        hierarchy_path = self.root / "hierarchy.npz"
        save_basin_hierarchy(hierarchy_path, hierarchy)
        self.write_json("run-inputs.json", {"hierarchy": {
            "path": str(hierarchy_path), "sha256": file_sha256(hierarchy_path),
            "identity": hierarchy["identity_sha256"]}})
        rain = np.zeros(24)
        rain[:6] = 10
        forcing_id = identity({"rain_mm_h": rain}, {"dt_s": 3600.})
        self.write_json("ordinary-forcing.json", {
            "rain_mm_h": rain.tolist(), "dt_s": 3600., "identity": forcing_id})
        groups = {}
        depth_series = {}
        routed = {}
        self.saved = {}
        for step in (900., 450.):
            checkpoint = None
            pages = []
            depths = []
            for hour in range(24):
                result = simulate_basin_storage(
                    hierarchy, rain[hour:hour + 1], checkpoint=checkpoint,
                    parameters={"substep_s": step, "face_conductance_m_s": .00001},
                    forcing_identity=forcing_id, full_rain_mm_h=rain)
                storage = result["storage"]
                checkpoint = result["checkpoint"]
                storage_path = self.root / f"step-{step}" / f"hour-{hour}" / "storage.npz"
                checkpoint_path = storage_path.with_name("checkpoint.npz")
                save_storage(storage_path, storage)
                save_checkpoint(checkpoint_path, checkpoint)
                pages.append({"hour": hour, "storage": self.pin(storage_path, storage),
                              "checkpoint": self.pin(checkpoint_path, checkpoint)})
                if hour == 0:
                    depths.append(storage["arrays"]["depth_m"][0])
                depths.append(storage["arrays"]["depth_m"][-1])
                self.saved[(step, hour)] = result
            groups[str(step)] = pages
            depth_series[step] = np.asarray(depths)
            routed[step] = checkpoint["arrays"]["cumulative_routed_volume_m3"]
        maximum = float(abs(depth_series[900.] - depth_series[450.]).max())
        receiver = float(abs(routed[900.] - routed[450.]).sum() / max(1e-12, routed[450.].sum()))
        self.record = {"pages": groups, "max_saved_depth_difference_m": maximum,
                       "cumulative_receiver_relative_l1": receiver,
                       "gate_passed": maximum <= .001 and receiver <= .01}
        self.comparison = self.root / "ordinary-comparison.json"

    def write_json(self, name, value):
        (self.root / name).write_text(json.dumps(value, allow_nan=False), encoding="utf-8")

    @staticmethod
    def pin(path, result):
        return {"path": str(path), "expected_sha256": file_sha256(path),
                "expected_identity": result["identity_sha256"]}

    def audit(self):
        self.write_json(self.comparison.name, self.record)
        return audit_scenario(self.comparison, file_sha256(self.comparison))

    def forge(self, role, field, value, *, metadata=False):
        result = self.saved[(900., 3)][role]
        arrays = {name: values.copy() for name, values in result["arrays"].items()}
        record_metadata = dict(result["metadata"])
        if metadata:
            record_metadata[field] = value
        else:
            arrays[field][0] += value
        changed = {"arrays": arrays, "metadata": record_metadata,
                   "identity_sha256": identity(arrays, record_metadata)}
        path = self.root / ("forged-" + role + "-" + field + ".npz")
        save_bundle(path, changed, validator=lambda unused: True)
        self.record["pages"]["900.0"][3][role] = self.pin(path, changed)

    def test_streams_real_saved_pages_without_advancing_solver(self):
        report = self.audit()
        self.assertTrue(report["checkpoint_chain_checked"])
        self.assertFalse(report["solver_advanced"])
        self.assertEqual(report["saved_frames"], 25)
        for budget in report["page_budget_audits"].values():
            self.assertTrue(budget["whole_period_passed"])

    def test_rehashed_time_offset_and_substep_count_are_rejected(self):
        for field, value in (("forcing_hour_offset", 4), ("substeps", 5)):
            with self.subTest(field=field):
                self.forge("storage", field, value, metadata=True)
                with self.assertRaisesRegex(ValueError, "global saved time"):
                    self.audit()

    def test_rehashed_cumulative_inventory_is_rejected(self):
        self.forge("checkpoint", "cumulative_face_forward_m3", .01)
        with self.assertRaises(AssertionError):
            self.audit()

    def test_rehashed_physical_parameters_are_rejected(self):
        parameters = {**self.saved[(900., 3)]["storage"]["metadata"]["parameters"],
                      "face_conductance_m_s": .00002}
        self.forge("storage", "parameters", parameters, metadata=True)
        self.forge("checkpoint", "parameters", parameters, metadata=True)
        with self.assertRaisesRegex(ValueError, "physical parameters"):
            self.audit()

    def test_missing_hour_and_incorrect_external_pin_are_rejected(self):
        self.record["pages"]["900.0"].pop()
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.audit()
        with self.assertRaisesRegex(ValueError, "external"):
            audit_scenario(self.comparison, "0" * 64)

    def test_single_series_audit_does_not_claim_refinement(self):
        self.write_json(self.comparison.name, self.record)
        report = audit_scenario(self.comparison, file_sha256(self.comparison), selected_step_s=900.)
        self.assertFalse(report["refinement_checked"])
        self.assertEqual(report["substeps_s"], [900.])
        self.assertTrue(report["page_budget_audits"]["900.0"]["whole_period_passed"])


if __name__ == "__main__":
    unittest.main()
