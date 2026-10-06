import copy
import json
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, save_bundle
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_basin_source import make_td_source, save_td_source
from terrain_pipeline.td_surface_reaches import _hash
from tests import test_td_native_weather_storage_v10_io as weather_fixture
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_candidate_weather import audit_execution


class IndependentCandidateWeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = weather_fixture.NativeWeatherV10IoTests()
        cls.fixture.setUp()
        cls.arguments = cls.fixture._whole_fixture()
        cls.root = cls.fixture.root
        original_index = json.loads((cls.root / "index.json").read_text(encoding="utf-8"))
        source = make_td_source(np.array([[0., .9]]), spacing_m=30.)
        hierarchy = build_basin_hierarchy(source)
        source_path = cls.root / "candidate-source.npz"
        hierarchy_path = cls.root / "candidate-hierarchy.npz"
        save_td_source(source_path, source)
        save_basin_hierarchy(hierarchy_path, hierarchy)
        cls.source_record = dict(path=str(source_path), expected_sha256=file_sha256(source_path), expected_identity=source["identity_sha256"])
        cls.hierarchy_record = dict(path=str(hierarchy_path), expected_sha256=file_sha256(hierarchy_path), expected_identity=hierarchy["identity_sha256"])
        cls.groups = {direction: copy.deepcopy(value["pages"]) for direction, value in original_index["scenarios"].items()}
        for groups in cls.groups.values():
            for pages in groups.values():
                for page in pages:
                    for role in ("storage", "checkpoint"):
                        path = Path(page[role]["path"])
                        arrays, metadata = read_record(page[role])
                        metadata["hierarchy_identity"] = hierarchy["identity_sha256"]
                        if role == "storage":
                            for name in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells"):
                                arrays[name] = hierarchy["arrays"][name].copy()
                        else:
                            metadata["last_page_identity"] = page["storage"]["expected_identity"]
                        result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
                        path.unlink()
                        save_bundle(path, result, validator=lambda value: None)
                        page[role] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
        cls.plan = dict(execution_ready=True, baseline_numerical_gate_passed=True,
                        candidates={"valley_incision": dict(hierarchy_record=cls.hierarchy_record, source_record=cls.source_record)},
                        original_weather_source_record=cls.arguments["source_record"],
                        weather_index_record=cls.arguments["weather_index_record"],
                        forcing_identities={name: value["forcing_identity"] for name, value in original_index["scenarios"].items()})
        cls.plan_record = cls.write_json("candidate-plan.json", cls.plan)
        cls.execution = dict(schema="td-candidate-native-weather-execution-v1", plan_record=cls.plan_record,
                             candidate_id="valley_incision", candidates=cls.plan["candidates"]["valley_incision"],
                             forcing_identities=cls.plan["forcing_identities"], steps_s=[2.5, 1.25],
                             flags=dict(hydraulic_ready=False, transient_converged=False, publishable=False, natural_outlet_verified=False),
                             pages=cls.groups)
        cls.execution_record = cls.write_json("candidate-index.json", cls.execution)

    @classmethod
    def write_json(cls, name, value):
        unsigned = {key: item for key, item in value.items() if key != "identity_sha256"}
        value = dict(unsigned, identity_sha256=_hash(unsigned))
        path = cls.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=value["identity_sha256"])

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDown()

    def test_new_bed_with_original_weather_and_complete_raw_accounts(self):
        for direction in ("eastward", "westward"):
            report = audit_execution(self.execution_record, direction)
            self.assertTrue(report["gate_passed"])
            self.assertTrue(report["whole_period_budget_passed"])
            self.assertFalse(report["solver_advanced"])
            self.assertNotEqual(report["hierarchy_record"], self.arguments["hierarchy_record"])
            self.assertEqual(report["original_weather_source_record"], self.arguments["source_record"])

    def test_partial_and_old_bed_substitution_rejected(self):
        partial = copy.deepcopy(self.execution)
        partial["pages"]["eastward"]["2.5"].pop()
        with self.assertRaisesRegex(ValueError, "coverage"):
            audit_execution(self.write_json("partial.json", partial), "eastward")
        plan = copy.deepcopy(self.plan)
        plan["candidates"]["valley_incision"]["source_record"] = self.arguments["source_record"]
        fake = copy.deepcopy(self.execution)
        fake["plan_record"] = self.write_json("old-bed-plan.json", plan)
        fake["candidates"] = plan["candidates"]["valley_incision"]
        with self.assertRaisesRegex(ValueError, "new source/hierarchy"):
            audit_execution(self.write_json("old-bed.json", fake), "eastward")

    def test_rehashed_wrong_grid_mapping_and_false_baseline_rejected(self):
        for mode in ("forcing", "baseline"):
            plan = copy.deepcopy(self.plan)
            if mode == "forcing":
                plan["forcing_identities"]["eastward"] = "0" * 64
            else:
                plan["baseline_numerical_gate_passed"] = False
            execution = copy.deepcopy(self.execution)
            execution["plan_record"] = self.write_json(mode + "-plan.json", plan)
            execution["forcing_identities"] = plan["forcing_identities"]
            with self.assertRaises(ValueError):
                audit_execution(self.write_json(mode + "-execution.json", execution), "eastward")


if __name__ == "__main__":
    unittest.main()
