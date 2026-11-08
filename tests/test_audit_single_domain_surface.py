import copy
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.fine_subgrid import build_geometry, build_water_frame
from tests.test_single_domain_surface_geometry import static_page
from tools.audit_single_domain_surface import check_frame, check_geometry


class IndependentSingleDomainAuditTests(unittest.TestCase):
    def setUp(self):
        self.hierarchy, self.page = static_page()
        self.page["arrays"]["depth_m"][:, 4] = .002
        self.page["identity_sha256"] = identity(self.page["arrays"], self.page["metadata"])
        self.geometry = build_geometry(self.hierarchy, source_hierarchy_sha256="a"*64)
        self.frame = build_water_frame(self.geometry, self.page, source_page_sha256="b"*64)
        self.geometry_record = dict(expected_identity=self.geometry["identity_sha256"])
        self.declaration = dict(frame=1, time_s=3600., state_index=1,
                                source_page=dict(expected_identity=self.page["identity_sha256"], expected_sha256="b"*64))

    def check(self, arrays=None, metadata=None):
        return check_frame(self.frame["arrays"] if arrays is None else arrays,
                           self.frame["metadata"] if metadata is None else metadata,
                           self.geometry["arrays"], self.geometry["metadata"], self.declaration,
                           self.page["arrays"], self.page["metadata"], self.geometry_record)

    def test_raw_isolated_volume_and_original_nodes(self):
        result = self.check()
        self.assertEqual(result["wet_cells"], 1)
        self.assertAlmostEqual(result["raster_volume_m3"], 1.8)
        self.assertEqual(result["omitted_wet_cells"], 0)
        geometry = check_geometry(self.geometry["arrays"], self.geometry["metadata"],
                                  self.hierarchy["arrays"], self.hierarchy["metadata"],
                                  dict(expected_identity=self.hierarchy["identity_sha256"], expected_sha256="a"*64))
        self.assertTrue(geometry["shared_junction_xyz_exact"])

    def test_covering_dry_cell_with_blue_quad_is_rejected(self):
        arrays = {key: value.copy() for key, value in self.frame["arrays"].items()}
        arrays["wet_cell_ids"][0] = 3
        with self.assertRaises(AssertionError):
            self.check(arrays=arrays)

    def test_false_surface_height_and_hidden_missing_wall_rejected(self):
        for key in ("water_vertices_xyz_m", "support_side_vertices_xyz_m"):
            arrays = {name: value.copy() for name, value in self.frame["arrays"].items()}
            arrays[key][0, 1] += .1
            with self.subTest(key=key), self.assertRaises(AssertionError):
                self.check(arrays=arrays)

    def test_false_volume_or_source_identity_rejected(self):
        for key, value in (("raster_volume_m3", 10.), ("source_page_identity", "c"*64)):
            metadata = copy.deepcopy(self.frame["metadata"])
            metadata[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(metadata=metadata)

    def test_reversed_triangle_rejected(self):
        arrays = {name: value.copy() for name, value in self.frame["arrays"].items()}
        arrays["water_triangles"][0] = arrays["water_triangles"][0][::-1]
        with self.assertRaises(AssertionError):
            self.check(arrays=arrays)


if __name__ == "__main__":
    unittest.main()
