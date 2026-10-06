import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, save_bundle
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_basin_source import make_td_source, save_td_source
from terrain_pipeline.td_native_storm_forcing import fixed_storm, generate_native_storm, save_native_storm
from terrain_pipeline.td_basin_storage_compiled_driver import simulate_basin_storage
from terrain_pipeline.td_basin_storage_compiled_io import save_storage, save_checkpoint
from tools.audit_td_native_weather_storage import audit_scenario


class IndependentSpatialWaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name).resolve()
        source = make_td_source(np.array([[0., 1.], [2., 0.]]), spacing_m=30.)
        source_path = cls.root / "source.npz"
        save_td_source(source_path, source)
        source_pin = cls.pin(source_path, source)
        hierarchy = build_basin_hierarchy(source)
        hierarchy_path = cls.root / "hierarchy.npz"
        save_basin_hierarchy(hierarchy_path, hierarchy)
        cls.hierarchy_pin = cls.pin(hierarchy_path, hierarchy)
        weather = generate_native_storm(source_pin, parameters=fixed_storm(source, "eastward"))
        weather_path = cls.root / "weather.npz"
        save_native_storm(weather_path, weather)
        cls.weather_pin = cls.pin(weather_path, weather)
        rain = weather["arrays"]["rain_mm_h"]
        groups = {}
        depths = {}
        receiver = {}
        cls.saved = {}
        for step in (900., 450.):
            pages = []
            checkpoint = None
            frames = []
            for hour in range(24):
                result = simulate_basin_storage(hierarchy, rain[hour:hour + 1],
                    parameters={"substep_s": step, "face_conductance_m_s": .00001},
                    checkpoint=checkpoint, forcing_identity=weather["metadata"]["forcing_identity"],
                    full_rain_mm_h=rain)
                storage = result["storage"]
                checkpoint = result["checkpoint"]
                location = cls.root / str(step) / str(hour)
                storage_path = location / "storage.npz"
                checkpoint_path = location / "checkpoint.npz"
                save_storage(storage_path, storage)
                save_checkpoint(checkpoint_path, checkpoint)
                pages.append({"hour": hour, "storage": cls.pin(storage_path, storage),
                              "checkpoint": cls.pin(checkpoint_path, checkpoint)})
                cls.saved[(step, hour)] = result
                if hour == 0:
                    frames.append(storage["arrays"]["depth_m"][0])
                frames.append(storage["arrays"]["depth_m"][-1])
            groups[str(step)] = pages
            depths[step] = np.asarray(frames)
            receiver[step] = checkpoint["arrays"]["cumulative_routed_volume_m3"]
        maximum = float(abs(depths[900.] - depths[450.]).max())
        relative = float(abs(receiver[900.] - receiver[450.]).sum() / max(1e-12, receiver[450.].sum()))
        cls.record = {"pages": groups, "max_saved_depth_difference_m": maximum,
                      "cumulative_receiver_relative_l1": relative, "gate_passed": maximum <= .001 and relative <= .01}
        cls.comparison = cls.root / "eastward-comparison.json"

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @staticmethod
    def pin(path, result):
        return {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}

    def audit(self, record=None):
        self.comparison.write_text(json.dumps(self.record if record is None else record), encoding="utf-8")
        return audit_scenario(self.comparison, file_sha256(self.comparison),
                              weather_record=self.weather_pin, hierarchy_record=self.hierarchy_pin)

    def forge(self, role, field, modify):
        record = copy.deepcopy(self.record)
        original = self.saved[(900., 3)][role]
        arrays = {name: values.copy() for name, values in original["arrays"].items()}
        modify(arrays[field])
        changed = {"arrays": arrays, "metadata": original["metadata"],
                   "identity_sha256": identity(arrays, original["metadata"])}
        artifact = self.root / (role + "-" + field + ".npz")
        save_bundle(artifact, changed, validator=lambda unused: True)
        record["pages"]["900.0"][3][role] = self.pin(artifact, changed)
        if role == "storage":
            original_cp = self.saved[(900., 3)]["checkpoint"]
            metadata = {**original_cp["metadata"], "last_page_storage_identity": changed["identity_sha256"]}
            changed_cp = {"arrays": original_cp["arrays"], "metadata": metadata,
                          "identity_sha256": identity(original_cp["arrays"], metadata)}
            cp_path = self.root / ("cp-" + field + ".npz")
            save_bundle(cp_path, changed_cp, validator=lambda unused: True)
            record["pages"]["900.0"][3]["checkpoint"] = self.pin(cp_path, changed_cp)
        return record

    def test_actual_spatial_pages_and_complete_water_chain(self):
        report = self.audit()
        self.assertTrue(report["full_spatial_rain_checked"])
        self.assertTrue(report["checkpoint_chain_checked"])
        self.assertFalse(report["solver_advanced"])
        self.assertEqual(report["saved_frames"], 25)
        self.assertTrue(all(budget["whole_period_passed"] for budget in report["page_budget_audits"].values()))

    def test_rehashed_spatial_rain_permutation_is_rejected(self):
        record = self.forge("storage", "rain_mm_h", lambda values: values.__setitem__((0, slice(None)), values[0, ::-1]))
        with self.assertRaises(AssertionError):
            self.audit(record)

    def test_rehashed_checkpoint_cumulative_flux_is_rejected(self):
        record = self.forge("checkpoint", "cumulative_face_forward_m3", lambda values: values.__setitem__(0, values[0] + .01))
        with self.assertRaises(AssertionError):
            self.audit(record)

    def test_missing_hour_is_rejected(self):
        record = copy.deepcopy(self.record)
        record["pages"]["900.0"].pop()
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.audit(record)

    def test_forged_published_gate_is_rejected(self):
        record = copy.deepcopy(self.record)
        record["max_saved_depth_difference_m"] += .1
        with self.assertRaisesRegex(ValueError, "reductions"):
            self.audit(record)


if __name__ == "__main__":
    unittest.main()
