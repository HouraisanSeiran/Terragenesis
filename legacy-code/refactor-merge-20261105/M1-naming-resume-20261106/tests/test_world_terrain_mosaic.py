"""CPU tests for pinned, halo-supported terrain window composition."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.td_source import compose_source, crop_composition
from terrain_pipeline.td_source import compose_window, inspect_window_support
from terrain_pipeline.world_water_layout import LayoutSpec


class MosaicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.spec = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                               frame_side_m=12_288_000)
        self.family = "test-conditioning"

    def page(self, name, x0, z0, *, change=None, family="test-conditioning"):
        z, x = np.indices((128, 128))
        height = (x + x0) * .3 + (z + z0) * .2 + np.sin((x + x0) / 4)
        if change is not None:
            height[change] += 100
        metadata = {"schema": "td-native-page-v1", "native_origin": [x0, z0],
                    "size": 128, "spacing_m": 30, "world_seed": 20261020,
                    "conditioning_identity": family}
        path = Path(self.temp.name) / name
        np.savez(path, elevation_native=height.astype(np.float64),
                 metadata_json=np.array(json.dumps(metadata)))
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def compose(self, records, origin, shape=(20, 20)):
        return compose_window(self.spec, records, origin, shape, sigma_cells=2,
                              source_family=self.family)

    def test_page_join_order_and_overlapping_windows(self):
        first = self.page("first.npz", 0, 0)
        second = self.page("second.npz", 65, 0)
        whole = self.compose([first, second], (100, 30), (25, 30))
        reverse = self.compose([second, first], (100, 30), (25, 30))
        overlapping = self.compose([second, first], (105, 35), (15, 20))
        np.testing.assert_array_equal(whole["composed_elevation_m"], reverse["composed_elevation_m"])
        np.testing.assert_array_equal(whole["composed_elevation_m"][5:20, 5:25],
                                      overlapping["composed_elevation_m"])
        self.assertEqual(whole["metadata"]["identity"], reverse["metadata"]["identity"])
        self.assertTrue(whole["valid_mask"].all())

    def test_same_as_single_fixed_source_interior(self):
        record = self.page("one.npz", 0, 0)
        with np.load(record["path"], allow_pickle=False) as saved:
            source = saved["elevation_native"].copy()
        fixed = compose_source(self.spec, source, (0, 0),
                               source_record={**record, "world_seed": 20261020}, sigma_cells=2)
        expected = crop_composition(fixed, (30, 30), (20, 20))
        actual = self.compose([record], (30, 30))
        np.testing.assert_array_equal(actual["td_residual_m"], expected["td_residual_m"])
        np.testing.assert_array_equal(actual["composed_elevation_m"], expected["composed_elevation_m"])

    def test_missing_and_inconsistent_support_are_rejected(self):
        first = self.page("first.npz", 0, 0)
        inspection = inspect_window_support(self.spec, [first], (110, 30), (20, 20),
                                            sigma_cells=2, source_family=self.family)
        self.assertGreater(inspection["missing_cells"], 0)
        self.assertEqual(inspection["missing_cells"], int(inspection["missing_mask"].sum()))
        empty = inspect_window_support(self.spec, [], (110, 30), (20, 20),
                                       sigma_cells=2, source_family=self.family)
        self.assertTrue(empty["missing_mask"].all())
        with self.assertRaisesRegex(ValueError, "unresolved"):
            self.compose([first], (110, 30))
        second = self.page("second.npz", 65, 0, change=(35, 40))
        with self.assertRaisesRegex(ValueError, "overlap disagrees"):
            self.compose([first, second], (100, 30), (20, 20))

    def test_world_edge_may_use_td_support_outside_frame(self):
        first = self.page("edge.npz", -20, -20)
        result = self.compose([first], (0, 0))
        self.assertTrue(result["valid_mask"].all())
        last = 409599
        far = self.page("far-edge.npz", last - 107, last - 107)
        result = self.compose([far], (last - 19, last - 19))
        self.assertTrue(result["valid_mask"].all())

    def test_wrong_family_is_rejected(self):
        wrong = self.page("wrong.npz", 0, 0, family="other")
        with self.assertRaisesRegex(ValueError, "source family"):
            self.compose([wrong], (30, 30))

    def test_legacy_and_declared_page_can_overlap(self):
        legacy = self.page("legacy.npz", 0, 0, family=None)
        current = self.page("current.npz", 65, 0)
        result = self.compose([legacy, current], (100, 30), (20, 20))
        self.assertEqual(result["metadata"]["source_family_verification"],
                         "mixed_embedded_and_caller_declared")

    def test_support_inspection_rejects_outside_world(self):
        with self.assertRaisesRegex(ValueError, "outside finite world"):
            inspect_window_support(self.spec, [], (-1, 0), (20, 20),
                                   sigma_cells=2, source_family=self.family)


if __name__ == "__main__":
    unittest.main()
