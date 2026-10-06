import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.single_domain_surface_geometry import (
    build_geometry, build_water_frame, load_geometry, load_water_frame,
    save_geometry, save_water_frame, validate_geometry, validate_water_frame,
)
from terrain_pipeline.td_basin_storage_v10_io import FLUX, LEDGERS
from tests.test_td_native_channel_geometry import fixture


def static_page():
    hierarchy, page = fixture()
    for name in FLUX + LEDGERS:
        page["arrays"][name][:] = 0.
    page["arrays"]["depth_m"][:] = 0.
    page["identity_sha256"] = identity(page["arrays"], page["metadata"])
    return hierarchy, page


def mutable(result):
    result = copy.deepcopy(result)
    result["arrays"] = {name: value.copy() for name, value in result["arrays"].items()}
    return result


class SingleDomainSurfaceGeometryTests(unittest.TestCase):
    def test_shared_junction_original_bed_and_all_links(self):
        hierarchy, _ = fixture()
        geometry = build_geometry(hierarchy, source_hierarchy_sha256="a" * 64)
        arrays = geometry["arrays"]
        incoming = arrays["edge_node_indices"][:, 1] == 4
        self.assertEqual(int(incoming.sum()), 4)
        endpoints = arrays["node_xyz_m"][arrays["edge_node_indices"]]
        np.testing.assert_array_equal(endpoints[incoming, 1], np.tile([150., 0., -30.], (4, 1)))
        np.testing.assert_array_equal(arrays["bed_vertices_xyz_m"][:, 1],
                                      np.repeat(hierarchy["arrays"]["height_m"].ravel(), 4))
        self.assertEqual(len(arrays["bed_triangles"]), 18)
        self.assertFalse(arrays["node_xyz_m"].flags.writeable)

    def test_isolated_wet_cell_has_complete_surface_volume_and_sides(self):
        hierarchy, page = static_page()
        page["arrays"]["depth_m"][:, 4] = .000001
        page["identity_sha256"] = identity(page["arrays"], page["metadata"])
        frame = build_water_frame(build_geometry(hierarchy, source_hierarchy_sha256="a" * 64),
                                  page, source_page_sha256="b" * 64)
        arrays, meta = frame["arrays"], frame["metadata"]
        np.testing.assert_array_equal(arrays["wet_cell_ids"], [4])
        self.assertEqual(len(arrays["water_triangles"]), 2)
        self.assertEqual(len(arrays["support_side_triangles"]), 8)
        self.assertEqual(meta["omitted_wet_cell_count"], 0)
        self.assertEqual(meta["raster_volume_m3"], .000001 * 900.)
        self.assertAlmostEqual(meta["triangulated_support_volume_m3"], meta["raster_volume_m3"])
        np.testing.assert_array_equal(arrays["water_vertices_xyz_m"][:, 1], [.000001] * 4)

    def test_adjacent_wet_supports_retain_level_jump_without_internal_wall(self):
        hierarchy, page = static_page()
        page["arrays"]["depth_m"][:, [1, 4]] = [1., 2.]
        page["identity_sha256"] = identity(page["arrays"], page["metadata"])
        frame = build_water_frame(build_geometry(hierarchy, source_hierarchy_sha256="a" * 64),
                                  page, source_page_sha256="b" * 64)
        self.assertEqual(frame["metadata"]["support_perimeter_segment_count"], 6)
        self.assertEqual(frame["metadata"]["max_wet_neighbor_surface_jump_m"], 2.)
        self.assertFalse(frame["metadata"]["continuous_surface"])
        self.assertEqual(frame["metadata"]["raster_volume_m3"], 2700.)

    def test_initial_state_time_and_dry_geometry(self):
        hierarchy, page = static_page()
        geometry = build_geometry(hierarchy, source_hierarchy_sha256="a" * 64)
        frame = build_water_frame(geometry, page, source_page_sha256="b" * 64, state_index=0)
        self.assertEqual(frame["metadata"]["time_s"], 0.)
        self.assertEqual(len(frame["arrays"]["water_vertices_xyz_m"]), 0)
        self.assertEqual(frame["metadata"]["raster_volume_m3"], 0.)
        for key in ("hydraulic_ready", "natural_outlet_verified", "publishable", "water_generated", "candidate_bed_used"):
            self.assertIs(frame["metadata"][key], False)
        for state in (-1, 2, True):
            with self.assertRaises(ValueError):
                build_water_frame(geometry, page, source_page_sha256="b" * 64, state_index=state)

    def test_narrow_wet_strip_at_outer_edge_has_full_coverage(self):
        hierarchy, page = static_page()
        page["arrays"]["depth_m"][:, :3] = [1., 2., 3.]
        page["identity_sha256"] = identity(page["arrays"], page["metadata"])
        frame = build_water_frame(build_geometry(hierarchy, source_hierarchy_sha256="a" * 64),
                                  page, source_page_sha256="b" * 64)
        np.testing.assert_array_equal(frame["arrays"]["wet_cell_ids"], [0, 1, 2])
        self.assertEqual(frame["metadata"]["wet_cell_count"], 3)
        self.assertEqual(frame["metadata"]["support_perimeter_segment_count"], 8)
        self.assertEqual(frame["metadata"]["raster_volume_m3"], 5400.)
        self.assertEqual(len(frame["arrays"]["water_triangles"]), 6)

    def test_rehashed_topology_and_xyz_corruption_rejected(self):
        hierarchy, _ = fixture()
        baseline = build_geometry(hierarchy, source_hierarchy_sha256="a" * 64)
        for kind in ("cycle", "diagonal", "duplicate", "bed", "junction", "publish"):
            result = mutable(baseline)
            arrays = result["arrays"]
            if kind == "cycle":
                arrays["receiver"][4] = 1
            elif kind == "diagonal":
                arrays["receiver"][0] = 4
            elif kind == "duplicate":
                arrays["face_cells"][1] = arrays["face_cells"][0]
            elif kind == "bed":
                arrays["bed_vertices_xyz_m"][0, 1] -= 1
            elif kind == "junction":
                arrays["node_xyz_m"][4, 1] += 1
            else:
                result["metadata"]["publishable"] = True
            result["identity_sha256"] = identity(arrays, result["metadata"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_geometry(result)

    def test_rehashed_water_coverage_surface_and_volume_corruption_rejected(self):
        hierarchy, page = fixture()
        baseline = build_water_frame(build_geometry(hierarchy, source_hierarchy_sha256="a" * 64),
                                     page, source_page_sha256="b" * 64)
        for kind in ("water", "wet", "volume", "time"):
            result = mutable(baseline)
            if kind == "water":
                result["arrays"]["water_vertices_xyz_m"][0, 1] -= .5
            elif kind == "wet":
                result["arrays"]["wet_cell_ids"] = result["arrays"]["wet_cell_ids"][:-1]
            elif kind == "volume":
                result["metadata"]["triangulated_support_volume_m3"] += 1
            else:
                result["metadata"]["time_s"] += 1
            result["identity_sha256"] = identity(result["arrays"], result["metadata"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_water_frame(result)

    def test_changed_native_page_cannot_map_to_geometry(self):
        hierarchy, page = fixture()
        geometry = build_geometry(hierarchy, source_hierarchy_sha256="a" * 64)
        page["arrays"]["height_m"][0, 0] -= .5
        page["identity_sha256"] = identity(page["arrays"], page["metadata"])
        with self.assertRaisesRegex(ValueError, "native static mismatch"):
            build_water_frame(geometry, page, source_page_sha256="b" * 64)

    def test_rehashed_misleading_geometry_and_frame_metadata_rejected(self):
        hierarchy, page = fixture()
        geometry = build_geometry(hierarchy, source_hierarchy_sha256="a" * 64)
        frame = build_water_frame(geometry, page, source_page_sha256="b" * 64)
        for baseline, validator, names in (
                (geometry, validate_geometry, ("coordinates", "algorithm", "bed_semantics", "topology_semantics")),
                (frame, validate_water_frame, ("coordinates", "algorithm", "water_semantics", "volume_semantics", "support_side_semantics", "limitation"))):
            for name in names:
                result = mutable(baseline)
                result["metadata"][name] = "false physical continuous surface claim"
                result["identity_sha256"] = identity(result["arrays"], result["metadata"])
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "semantics"):
                    validator(result)

    def test_pinned_readonly_roundtrip_and_no_implicit_generation(self):
        hierarchy, page = fixture()
        geometry = build_geometry(hierarchy, source_hierarchy_sha256="a" * 64)
        frame = build_water_frame(geometry, page, source_page_sha256="b" * 64)
        with tempfile.TemporaryDirectory() as directory:
            for name, result, saver, loader in (("geometry", geometry, save_geometry, load_geometry),
                                                ("frame", frame, save_water_frame, load_water_frame)):
                path = Path(directory) / (name + ".npz")
                saver(path, result)
                with patch("terrain_pipeline.single_domain_surface_geometry.build_geometry", side_effect=AssertionError), \
                        patch("terrain_pipeline.single_domain_surface_geometry.build_water_frame", side_effect=AssertionError):
                    loaded = loader(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
                self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
                self.assertTrue(all(not value.flags.writeable for value in loaded["arrays"].values()))
                with self.assertRaises(ValueError):
                    loader(path, expected_sha256="0" * 64, expected_identity=result["identity_sha256"])
                with self.assertRaises(FileExistsError):
                    saver(path, result)


if __name__ == "__main__":
    unittest.main()
