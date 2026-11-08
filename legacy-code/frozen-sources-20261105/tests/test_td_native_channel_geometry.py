import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_basin_storage_v10_io import PROFILE, STATES, LEDGERS, FLUX, save_storage
from terrain_pipeline.td_native_channel_geometry import (
    GeometryRecipe, build_channel_geometry, load_channel_geometry, load_geometry_inputs,
    save_channel_geometry, validate_channel_geometry,
)


def fixture():
    height = np.array([[4., 3., 4.], [3., 0., 3.], [4., 2., 4.]])
    opened = np.zeros((3, 3), bool)
    opened[0, 0] = True
    hierarchy = build_basin_hierarchy(make_td_source(
        height, spacing_m=30., origin_m_xz=(120., -60.), open_boundary_mask=opened))
    topology = hierarchy["arrays"]
    cells, faces = height.size, len(topology["face_cells"])
    arrays = {name: topology[name].copy() for name in
              ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells")}
    arrays["boundary_width_m"] = np.array([60.])
    arrays.update({name: np.zeros((2, cells)) for name in STATES})
    arrays["depth_m"][:] = 1.
    arrays["soil_mm"][:] = 30.
    arrays.update({name: np.zeros((1, cells)) for name in LEDGERS})
    arrays["rain_mm_h"] = np.zeros((1, cells))
    arrays.update({name: np.zeros(faces if name.startswith(("face_", "active_")) else cells)
                   for name in FLUX})
    arrays["face_forward_m3"][:] = 2.
    arrays["face_reverse_m3"][:] = 5.
    arrays["active_forward_s"][:] = 10.
    arrays["active_reverse_s"][:] = 20.
    first, second = topology["face_cells"].T
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net = np.bincount(second, weights=signed, minlength=cells) - np.bincount(first, weights=signed, minlength=cells)
    arrays["internal_net_m3"][0] = net
    arrays["depth_m"][1] += net / 900.
    arrays["storage_change_m3"][0] = net
    for source, target, volume, activity in (
            (first, second, arrays["face_forward_m3"], arrays["active_forward_s"]),
            (second, first, arrays["face_reverse_m3"], arrays["active_reverse_s"])):
        follows = topology["receiver"][source] == target
        np.add.at(arrays["routed_volume_m3"], source[follows], volume[follows])
        np.add.at(arrays["wet_duration_s"], source[follows], activity[follows])
    degree = np.bincount(topology["face_cells"].ravel(), minlength=cells).astype(float)
    degree[0] += 2.
    metadata = dict(schema="td-v10-hour-page-v1", profile=PROFILE,
                    hierarchy_identity=hierarchy["identity_sha256"], forcing_identity="a" * 64,
                    origin_m_xz=[120., -60.], spacing_m=30., start_s=0., end_s=3600., dt_s=3600.,
                    substep_s=2.5, substeps=1440, forcing_hour_offset=0, cells=cells, faces=faces,
                    positivity_cfl=float(degree.max()) * .6 * 2.5 / 30.,
                    parameters=dict(runoff=[15., 150., .15, 1., 3600., 259200.],
                                    face_conductance_m_s=.6, surface_evaporation_mm_h=.15, substep_s=2.5,
                                    forcing_profile="v10-unified-rain-surface-infiltration-experimental-v1"),
                    hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    page = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    return hierarchy, page


class NativeChannelGeometryTests(unittest.TestCase):
    def test_shared_junction_and_metric_coordinates(self):
        hierarchy, page = fixture()
        result = build_channel_geometry(hierarchy, page)
        arrays = result["arrays"]
        entering = arrays["edge_cell_ids"][:, 1] == 4
        self.assertEqual(int(entering.sum()), 4)
        junction = arrays["node_world_xyz_m"][4]
        np.testing.assert_array_equal(arrays["edge_centerline_xyz_m"][entering, 1], np.tile(junction, (4, 1)))
        self.assertEqual(junction[0], 150.)
        self.assertEqual(junction[2], -30.)
        np.testing.assert_array_equal(arrays["node_native_bed_m"], hierarchy["arrays"]["height_m"].ravel())
        self.assertTrue(np.all(arrays["node_candidate_bed_m"] < arrays["node_native_bed_m"]))

    def test_internal_sink_and_engineering_boundary_are_separate(self):
        arrays = build_channel_geometry(*fixture())["arrays"]
        self.assertTrue(arrays["node_internal_sink"][4])
        self.assertFalse(arrays["node_engineering_boundary"][4])
        self.assertTrue(arrays["node_engineering_boundary"][0])
        self.assertFalse(arrays["node_internal_sink"][0])

    def test_actual_reverse_faces_preserved_without_tree_continuity(self):
        hierarchy, page = fixture()
        result = build_channel_geometry(hierarchy, page)
        arrays = result["arrays"]
        np.testing.assert_array_equal(arrays["actual_face_reverse_m3"], page["arrays"]["face_reverse_m3"])
        np.testing.assert_array_equal(arrays["actual_face_forward_m3"], page["arrays"]["face_forward_m3"])
        np.testing.assert_array_equal(arrays["node_receiver_interval_mean_q_m3_s"], page["arrays"]["routed_volume_m3"] / 3600.)
        self.assertTrue(np.any(arrays["actual_face_reverse_m3"] > arrays["actual_face_forward_m3"]))
        self.assertEqual(arrays["node_receiver_interval_mean_q_m3_s"][4], 0.)
        for name in ("hydraulic_ready", "natural_outlet_verified", "publishable"):
            self.assertIs(result["metadata"][name], False)

    def test_actual_depth_samples_and_sections_are_distinct(self):
        hierarchy, page = fixture()
        arrays = build_channel_geometry(hierarchy, page)["arrays"]
        np.testing.assert_array_equal(arrays["node_hour_end_surface_sample_m"],
                                      hierarchy["arrays"]["height_m"].ravel() + page["arrays"]["depth_m"][-1])
        sections = arrays["edge_sections_xyz_m"].reshape(-1, 2, 3, 3)
        np.testing.assert_array_equal(sections[:, :, 1], arrays["edge_centerline_xyz_m"])
        widths = np.linalg.norm(sections[:, :, 2][:, :, [0, 2]] - sections[:, :, 0][:, :, [0, 2]], axis=2)
        np.testing.assert_allclose(widths, arrays["node_width_m"][arrays["edge_cell_ids"]])

    def test_dry_geometry_does_not_invent_flow(self):
        hierarchy, page = fixture()
        for name in FLUX + LEDGERS:
            page["arrays"][name][:] = 0.
        page["arrays"]["depth_m"][:] = 0.
        page["identity_sha256"] = identity(page["arrays"], page["metadata"])
        arrays = build_channel_geometry(hierarchy, page)["arrays"]
        self.assertEqual(len(arrays["edge_cell_ids"]), 8)
        self.assertFalse(arrays["node_receiver_interval_mean_q_m3_s"].any())
        self.assertFalse(arrays["node_geometry_active"].any())
        self.assertFalse(arrays["edge_geometry_active"].any())
        self.assertFalse(arrays["node_width_m"].any())
        self.assertFalse(arrays["node_candidate_incision_m"].any())
        np.testing.assert_array_equal(arrays["node_candidate_bed_m"], arrays["node_native_bed_m"])

    def test_sink_shape_inherits_actual_incoming_edges_without_inventing_q(self):
        arrays = build_channel_geometry(*fixture())["arrays"]
        self.assertEqual(arrays["node_receiver_interval_mean_q_m3_s"][4], 0.)
        self.assertFalse(arrays["node_receiver_geometry_active"][4])
        self.assertTrue(arrays["node_geometry_active"][4])
        self.assertEqual(arrays["node_width_m"][4], arrays["node_incoming_shape_width_m"][4])
        self.assertEqual(arrays["node_candidate_incision_m"][4], arrays["node_incoming_shape_incision_m"][4])

    def test_predeclared_threshold_preserves_unconnected_dry_bed(self):
        hierarchy, page = fixture()
        arrays = build_channel_geometry(hierarchy, page, GeometryRecipe(active_q_threshold_m3_s=1.))["arrays"]
        self.assertFalse(arrays["node_geometry_active"].any())
        np.testing.assert_array_equal(arrays["node_candidate_bed_m"], hierarchy["arrays"]["height_m"].ravel())

    def test_io_roundtrip_load_order_and_wrong_pins(self):
        hierarchy, page = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for name, result, saver in (("hierarchy", hierarchy, save_basin_hierarchy),
                                        ("page", page, save_storage)):
                path = root / (name + ".npz")
                saver(path, result)
                records.append(dict(path=path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"]))
            first = build_channel_geometry(*load_geometry_inputs(*records))
            second = build_channel_geometry(*load_geometry_inputs(*records, load_order=("hour_page", "hierarchy")))
            self.assertEqual(first["identity_sha256"], second["identity_sha256"])
            path = root / "geometry.npz"
            save_channel_geometry(path, first)
            loaded = load_channel_geometry(path, expected_sha256=file_sha256(path), expected_identity=first["identity_sha256"])
            self.assertFalse(loaded["arrays"]["node_world_xyz_m"].flags.writeable)
            with self.assertRaises(FileExistsError):
                save_channel_geometry(path, first)
            for field in ("expected_sha256", "expected_identity"):
                bad = dict(records[1], **{field: "0" * 64})
                with self.assertRaises(ValueError):
                    load_geometry_inputs(records[0], bad)
            with self.assertRaises(ValueError):
                load_channel_geometry(path, expected_sha256="0" * 64, expected_identity=first["identity_sha256"])

    def test_rehashed_invalid_geometry_rejected(self):
        baseline = build_channel_geometry(*fixture())
        for kind in ("nonfinite", "duplicate", "diagonal", "zero", "missing", "cycle", "flag", "junction", "section"):
            with self.subTest(kind=kind):
                result = copy.deepcopy(baseline)
                result["arrays"] = {name: values.copy() for name, values in result["arrays"].items()}
                arrays = result["arrays"]
                if kind == "nonfinite":
                    arrays["node_candidate_bed_m"][0] = np.nan
                elif kind == "duplicate":
                    arrays["node_cell_ids"][1] = 0
                elif kind == "diagonal":
                    arrays["actual_face_cells"][0] = [0, 4]
                elif kind == "zero":
                    arrays["actual_face_cells"][0] = [0, 0]
                elif kind == "missing":
                    arrays["node_receiver_cell_ids"][0] = 99
                elif kind == "cycle":
                    arrays["node_receiver_cell_ids"][4] = 1
                elif kind == "flag":
                    result["metadata"]["publishable"] = True
                elif kind == "junction":
                    arrays["edge_centerline_xyz_m"][0, 1, 0] += 1
                else:
                    arrays["edge_sections_xyz_m"][0, 0, 0] += 1
                result["identity_sha256"] = identity(arrays, result["metadata"])
                with self.assertRaises(ValueError):
                    validate_channel_geometry(result)

    def test_invalid_page_identity_grid_and_recipe(self):
        for kind in ("identity", "hierarchy", "origin", "nan"):
            hierarchy, page = fixture()
            if kind == "identity":
                page["identity_sha256"] = "0" * 64
            elif kind == "hierarchy":
                page["metadata"]["hierarchy_identity"] = "0" * 64
            elif kind == "origin":
                page["metadata"]["origin_m_xz"][0] += 1
            else:
                page["arrays"]["depth_m"][0, 0] = np.nan
            if kind != "identity":
                page["identity_sha256"] = identity(page["arrays"], page["metadata"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                build_channel_geometry(hierarchy, page)
        for kwargs in (dict(reference_q_m3_s=0.), dict(width_exponent=float("inf")),
                       dict(minimum_width_m=100.)):
            with self.assertRaises(ValueError):
                GeometryRecipe(**kwargs)

    def test_rehashed_q_with_consistent_recipe_geometry_rejected_by_faces(self):
        hierarchy, page = fixture()
        modified = copy.deepcopy(page)
        for name in ("face_forward_m3", "face_reverse_m3", "routed_volume_m3", "internal_net_m3", "storage_change_m3"):
            modified["arrays"][name] *= 2.
        modified["arrays"]["depth_m"][1] = 1. + modified["arrays"]["internal_net_m3"][0] / 900.
        modified["identity_sha256"] = identity(modified["arrays"], modified["metadata"])
        result = build_channel_geometry(hierarchy, modified)
        result["arrays"] = {name: values.copy() for name, values in result["arrays"].items()}
        for name in ("face_forward_m3", "face_reverse_m3"):
            result["arrays"]["actual_" + name] = page["arrays"][name].copy()
        result["identity_sha256"] = identity(result["arrays"], result["metadata"])
        with self.assertRaisesRegex(ValueError, "Q differs"):
            validate_channel_geometry(result)

    def test_rehashed_invalid_actual_directional_evidence_rejected(self):
        baseline = build_channel_geometry(*fixture())
        for kind in ("shape", "negative", "zero_volume", "zero_activity", "duration", "combined", "direction"):
            with self.subTest(kind=kind):
                result = copy.deepcopy(baseline)
                arrays = result["arrays"] = {name: values.copy() for name, values in result["arrays"].items()}
                if kind == "shape":
                    arrays["actual_face_reverse_m3"] = arrays["actual_face_reverse_m3"][:-1]
                elif kind == "negative":
                    arrays["actual_face_forward_m3"][0] = -1.
                elif kind == "zero_volume":
                    arrays["actual_face_reverse_m3"][0] = 0.
                elif kind == "zero_activity":
                    arrays["actual_active_reverse_s"][0] = 0.
                elif kind == "duration":
                    arrays["actual_active_forward_s"][0] = 3601.
                elif kind == "combined":
                    arrays["actual_active_forward_s"][0] = 2000.
                    arrays["actual_active_reverse_s"][0] = 2000.
                else:
                    arrays["actual_face_forward_m3"], arrays["actual_face_reverse_m3"] = arrays["actual_face_reverse_m3"], arrays["actual_face_forward_m3"]
                result["identity_sha256"] = identity(arrays, result["metadata"])
                with self.assertRaises(ValueError):
                    validate_channel_geometry(result)

    def test_source_chain_changed_after_load_rejected(self):
        hierarchy, page = fixture()
        records = (dict(path="hierarchy", expected_sha256="a" * 64), dict(path="page", expected_sha256="b" * 64))
        with patch("terrain_pipeline.td_native_channel_geometry.file_sha256", side_effect=["a" * 64, "b" * 64, "c" * 64]), \
                patch("terrain_pipeline.td_native_channel_geometry.load_basin_hierarchy", return_value=hierarchy), \
                patch("terrain_pipeline.td_native_channel_geometry.load_storage", return_value=page):
            with self.assertRaisesRegex(ValueError, "source chain SHA"):
                load_geometry_inputs(*records)


if __name__ == "__main__":
    unittest.main()
