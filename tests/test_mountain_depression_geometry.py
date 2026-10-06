"""Geometry semantics, complete upstream areas and safe static persistence."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import mountain_depression_geometry as geometry


def bowl():
    height = np.full((9, 9), 10., dtype=np.float64)
    height[0, :] = 0.
    height[:, 0] = height[:, -1] = 0.
    height[-1, :] = 0.
    height[4, 4] = 1.
    height[3, 4] = 2.
    height[2, 4] = 3.
    height[1, 4] = 4.
    return height


def prepare(height, **kwargs):
    return geometry.prepare_mountain_geometry(height, spacing_m=30., origin_m_xz=[100., -200.],
        source_binding={"test": "bowl"}, boundary_mask=geometry.window_boundary(height.shape),
        protected_mask=np.zeros(height.shape, dtype=bool), **kwargs)


class MountainDepressionGeometryTests(unittest.TestCase):
    def test_original_lake_bed_and_spill_are_never_filled_or_cut(self):
        height = bowl()
        result = prepare(height)
        arrays = result["arrays"]
        self.assertEqual(arrays["lake_stage_m"].tolist(), [4.])
        self.assertEqual(arrays["lake_capacity_m3"].tolist(), [5400.])
        self.assertEqual(arrays["spill_width_m"].tolist(), [30.])
        np.testing.assert_array_equal(arrays["H0_m"], height)
        np.testing.assert_array_equal(arrays["H2_m"][arrays["lake_mask"]], height[arrays["lake_mask"]])
        self.assertFalse((arrays["lake_mask"] & arrays["dry_channel_mask"]).any())
        self.assertEqual(geometry.lake_volume_at_stage(result, 1, 2.), 900.)
        with self.assertRaises(ValueError):
            geometry.lake_volume_at_stage(result, 1, 5.)

    def test_every_cell_belongs_to_one_explicit_truncated_outlet(self):
        result = prepare(bowl())
        arrays = result["arrays"]
        self.assertEqual(arrays["outlet_area_m2"].sum(), 81 * 900)
        np.testing.assert_array_equal(arrays["outlet_area_m2"], np.bincount(arrays["outlet_owner"].ravel()) * 900)
        self.assertEqual(result["metadata"]["boundary_types"], {"1": "external_open_boundary"})
        np.testing.assert_array_equal(arrays["receiver"] == -1, arrays["boundary_mask"].ravel())

    def test_diagonal_contact_is_not_a_lake_connection(self):
        height = np.full((7, 7), 10., dtype=np.float64)
        height[geometry.window_boundary(height.shape)] = 0.
        height[2, 2] = 1.
        height[3, 3] = 2.
        result = prepare(height)
        labels = result["arrays"]["lake_id"]
        self.assertNotEqual(labels[2, 2], labels[3, 3])
        self.assertEqual(result["arrays"]["lake_stage_m"].size, 2)

    def test_cold_load_does_not_prepare_or_route(self):
        height = bowl()
        result = prepare(height)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "geometry.npz"
            geometry.save_mountain_geometry(path, result, trusted_height=height, source_binding={"test": "bowl"})
            with patch.object(geometry, "prepare_mountain_geometry", side_effect=AssertionError("prepare")), \
                 patch.object(geometry, "_flood", side_effect=AssertionError("flood")), \
                 patch.object(geometry, "_route_lakes", side_effect=AssertionError("route")), \
                 patch.object(geometry, "_bed_candidates", side_effect=AssertionError("bed prepare")), \
                 patch.object(geometry, "_ownership", side_effect=AssertionError("ownership build")):
                loaded = geometry.load_mountain_geometry(path, trusted_height=height, source_binding={"test": "bowl"})
            self.assertFalse(loaded["arrays"]["H0_m"].flags.writeable)
            with self.assertRaises(ValueError):
                loaded["arrays"]["H0_m"].setflags(write=True)
            with self.assertRaises(FileExistsError):
                geometry.save_mountain_geometry(path, result, trusted_height=height, source_binding={"test": "bowl"})
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_racing_publication_preserves_the_other_writer(self):
        height = bowl()
        result = prepare(height)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "race.npz"
            original_link = geometry.os.link
            def racing_link(temporary, destination):
                Path(destination).write_bytes(b"other writer")
                return original_link(temporary, destination)
            with patch.object(geometry.os, "link", side_effect=racing_link):
                with self.assertRaises(FileExistsError):
                    geometry.save_mountain_geometry(target, result, trusted_height=height, source_binding={"test": "bowl"})
            self.assertEqual(target.read_bytes(), b"other writer")
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_resource_refusal_precedes_flood(self):
        with patch.object(geometry, "_flood", side_effect=AssertionError("allocation/flood")):
            with self.assertRaises(ValueError):
                prepare(bowl(), budget=geometry.GeometryBudget(max_cells=20))
            with self.assertRaises(ValueError):
                prepare(bowl(), budget=geometry.GeometryBudget(max_neighbor_visits=100))
        for kwargs in ({"max_cut_volume_m3": 200001.}, {"max_total_cut_m": 2.01}, {"max_cells": True}):
            with self.assertRaises(ValueError):
                geometry.GeometryBudget(**kwargs)

    def test_external_trust_refuses_changed_original_or_binding(self):
        result = prepare(bowl())
        with self.assertRaises(ValueError):
            geometry.validate_mountain_geometry(result, trusted_height=bowl() + 1, source_binding={"test": "bowl"})
        with self.assertRaises(ValueError):
            geometry.validate_mountain_geometry(result, trusted_height=bowl(), source_binding={"test": "other"})

    def test_semantic_forgery_is_refused_even_with_fresh_integrity_hashes(self):
        height = bowl()
        result = prepare(height)
        mutations = (
            lambda item: item["arrays"]["lake_capacity_m3"].__setitem__(0, 999.),
            lambda item: item["arrays"]["H2_m"].__setitem__((4, 4), 4.),
            lambda item: item["arrays"]["spill_width_m"].__setitem__(0, 1.),
            lambda item: item["arrays"]["outlet_area_m2"].__setitem__(0, 0.),
            lambda item: item["metadata"].__setitem__("boundary_types", {"1": "legal_natural_mouth"}),
            lambda item: item["arrays"]["escape_level_m"].__setitem__((4, 4), 5.),
            lambda item: item["arrays"]["receiver"].__setitem__(40, 40),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, mutate in enumerate(mutations):
                with self.subTest(index=index):
                    forged = deepcopy(result)
                    mutate(forged)
                    manifest = {"metadata": forged["metadata"], "hashes": {key: geometry._hash(value) for key, value in forged["arrays"].items()}}
                    path = Path(directory) / f"forged-{index}.npz"
                    np.savez_compressed(path, manifest=np.frombuffer(geometry._json(manifest).encode("ascii"), dtype=np.uint8), **forged["arrays"])
                    with self.assertRaises(ValueError):
                        geometry.load_mountain_geometry(path, trusted_height=height, source_binding={"test": "bowl"})

    def test_boundary_condition_cannot_be_silently_changed(self):
        height = bowl()
        boundary = np.zeros(height.shape, dtype=bool)
        boundary[0, 0] = True
        with self.assertRaises(ValueError):
            geometry.prepare_mountain_geometry(height, spacing_m=30., origin_m_xz=[0., 0.],
                source_binding={"test": "bowl"}, boundary_mask=boundary,
                protected_mask=np.zeros(height.shape, dtype=bool))

    def test_no_cut_legality_is_separate_from_construction_selection(self):
        result = prepare(bowl())
        self.assertFalse(result["arrays"]["accepted_mask"].any())
        certificate = geometry.certify_no_cut_groups(result)
        self.assertTrue(certificate["cell_valid_mask"].all())
        self.assertEqual(certificate["original_dry_uphill_edges"], 0)
        self.assertEqual(certificate["valid_area_m2"], 81 * 900)

    def test_every_high_elevation_event_catches_multiple_initial_pools(self):
        height = np.full((7, 7), 10., dtype=np.float64)
        height[geometry.window_boundary(height.shape)] = 0.
        height[3, 2] = 1.
        height[3, 3] = 6.
        height[3, 4] = 2.
        height[2, 3] = 7.
        result = prepare(height)
        screening = geometry.screen_single_pool_lakes(result)
        decisions = [item for item in screening["decisions"] if item["cells"] >= 4]
        self.assertTrue(decisions)
        self.assertIn("multiple_initial_pools", decisions[0]["reason_flags"])
        self.assertGreater(decisions[0]["disconnected_events"], 0)
        self.assertEqual(decisions[0]["event_work"], decisions[0]["bbox_cells"] * decisions[0]["all_elevation_events"])

    def test_archive_extra_keys_and_wrong_header_shape_are_refused(self):
        result = prepare(bowl())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extra.npz"
            forged = deepcopy(result["arrays"])
            forged["extra"] = np.ones(1)
            manifest = {"metadata": result["metadata"], "hashes": {key: geometry._hash(value) for key, value in forged.items()}}
            np.savez_compressed(path, manifest=np.frombuffer(geometry._json(manifest).encode("ascii"), dtype=np.uint8), **forged)
            with self.assertRaises(ValueError):
                geometry.load_mountain_geometry(path, trusted_height=bowl(), source_binding={"test": "bowl"})


if __name__ == "__main__":
    unittest.main()
