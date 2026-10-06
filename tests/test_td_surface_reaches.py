import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_storage import simulate_basin_storage
from terrain_pipeline.td_surface_reaches import make_surface_reaches, save_surface_reaches, load_surface_reaches, _plain, _hash


def fixture(height, protected=None):
    values = np.asarray(height, np.float64)
    source = make_td_source(np.nan_to_num(values), valid_mask=np.isfinite(values), spacing_m=1, protected_mask=protected)
    return build_basin_hierarchy(source)


def build(hierarchy, threshold=1, storage=None):
    return make_surface_reaches(hierarchy, threshold_area_m2=threshold,
        expected_hierarchy_identity=hierarchy["identity_sha256"], storage=storage,
        expected_storage_identity=None if storage is None else storage["identity_sha256"])


class SurfaceReachTests(unittest.TestCase):
    def test_rehashed_storage_coordinate_and_boundary_mismatch(self):
        from terrain_pipeline.mountain_source_adapter import identity
        hierarchy = fixture([[3, 2, 1]])
        storage = simulate_basin_storage(hierarchy, np.zeros(1), dt_s=1)
        for name, value in (("origin_m_xz", [9., 9.]), ("spacing_m", 2.)):
            changed = {"metadata": dict(storage["metadata"]), "arrays": dict(storage["arrays"])}
            changed["metadata"][name] = value
            changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
            with self.subTest(name=name), self.assertRaises(ValueError):
                build(hierarchy, storage=changed)

    def test_rehashed_metadata_tampering_refused(self):
        hierarchy = fixture([[3, 2, 1]])
        storage = simulate_basin_storage(hierarchy, np.zeros(1), dt_s=1)
        original = build(hierarchy, storage=storage)
        mutations = [lambda value: value["grid"].update(origin_m_xz=[9, 9]),
                     lambda value: value["grid"].update(spacing_m=2),
                     lambda value: value["grid"].update(axes="wrong"),
                     lambda value: value.update(source_identity_sha256="0" * 64),
                     lambda value: value["hierarchy"]["node_parent"].__setitem__(0, 0),
                     lambda value: value["hierarchy"]["node_unknown_contact"].__setitem__(0, True),
                     lambda value: value["flux_scope"].update(elapsed_s=999),
                     lambda value: value["flags"].update(readonly=False)]
        with tempfile.TemporaryDirectory() as temporary:
            for index, mutate in enumerate(mutations):
                changed = _plain(original)
                mutate(changed)
                changed.pop("identity_sha256")
                changed["identity_sha256"] = _hash(changed)
                path = Path(temporary) / f"tamper-{index}.json"
                save_surface_reaches(changed, path)
                with self.subTest(index=index), self.assertRaises(ValueError):
                    load_surface_reaches(path, expected_sha256=file_sha256(path), expected_identity=changed["identity_sha256"], hierarchy=hierarchy, storage=storage)

    def test_y_junction_and_degree_two_compression(self):
        hierarchy = fixture([[5, 4, 5], [5, 3, 5], [5, 2, 5], [5, 1, 5]])
        result = build(hierarchy)
        self.assertTrue(any(node["kind"] == "junction" for node in result["nodes"]))
        self.assertEqual(sum(len(reach["edges"]) for reach in result["reaches"]), result["summary"]["selected_edges"])
        self.assertEqual(result["summary"]["terminal_contribution_area_m2"], 12)

    def test_masked_y_two_donors_one_shared_trunk(self):
        hierarchy = fixture([[5, np.nan, 5], [4, 3, 4], [np.nan, 2, np.nan], [np.nan, 1, np.nan]])
        result = build(hierarchy)
        junction = next(node for node in result["nodes"] if node["cell_id"] == 4)
        self.assertEqual(junction["selected_donor_count"], 2)
        self.assertEqual(junction["contributing_area_m2"], 5)
        trunk = next(reach for reach in result["reaches"] if reach["cell_ids"][0] == 4)
        self.assertEqual(trunk["cell_ids"], (4, 7, 10))
        self.assertEqual(trunk["contributing_area_m2"], (5., 6., 7.))

    def test_flat_connects_without_cycle_or_uphill(self):
        hierarchy = fixture([[4, 4, 4, 1]])
        result = build(hierarchy)
        self.assertEqual(result["summary"]["selected_edges"], 3)
        self.assertEqual(result["summary"]["reach_count"], 1)
        self.assertEqual(result["reaches"][0]["contributing_area_m2"], (1., 2., 3., 4.))
        self.assertEqual(result["reaches"][0]["cell_ids"], (0, 1, 2, 3))

    def test_internal_basin_and_unknown_contact(self):
        result = build(fixture([[3, 3, 3], [3, 0, 3], [3, 3, 3]]))
        center = next(node for node in result["nodes"] if node["cell_id"] == 4)
        self.assertEqual(center["terminal_kind"], "internal_basin")
        result = build(fixture([[3, 0, np.nan]]))
        self.assertTrue(any(node["terminal_kind"] == "unknown_contact" for node in result["nodes"]))

    def test_protection_isolation(self):
        result = build(fixture([[3, 2, 1]], np.array([[False, True, False]])))
        self.assertEqual(result["summary"]["terminal_contribution_area_m2"], 2)
        self.assertTrue(any(node["terminal_kind"] == "protected_barrier" for node in result["nodes"]))
        self.assertFalse(any(1 in reach["cell_ids"] for reach in result["reaches"]))

    def test_stable_ids_across_thresholds(self):
        hierarchy = fixture([[4, 3, 2, 1]])
        full, reduced = build(hierarchy), build(hierarchy, 2)
        full_edges = {edge["donor_cell_id"]: edge["edge_id"] for reach in full["reaches"] for edge in reach["edges"]}
        self.assertTrue(all(full_edges[edge["donor_cell_id"]] == edge["edge_id"] for reach in reduced["reaches"] for edge in reach["edges"]))

    def test_stored_directional_flux_and_readonly_cold_reload(self):
        hierarchy = fixture([[3, 2, 1]])
        storage = simulate_basin_storage(hierarchy, np.zeros(1), dt_s=1, initial_depth_m=np.ones((1, 3)))
        result = build(hierarchy, storage=storage)
        for reach in result["reaches"]:
            for edge in reach["edges"]:
                flux = edge["stored_flux"]
                self.assertEqual(flux["gross_m3"], flux["forward_m3"] + flux["reverse_m3"])
                self.assertEqual(flux["net_face_m3"], flux["forward_m3"] - flux["reverse_m3"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reaches.json"
            save_surface_reaches(result, path)
            with patch("terrain_pipeline.td_surface_reaches.make_surface_reaches", side_effect=AssertionError("build")), patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy", side_effect=AssertionError("routing")), patch("terrain_pipeline.td_basin_storage.simulate_basin_storage", side_effect=AssertionError("solve")):
                loaded = load_surface_reaches(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"], hierarchy=hierarchy, storage=storage)
            self.assertEqual(loaded, result)
            with self.assertRaises(TypeError):
                loaded["nodes"][0]["kind"] = "fake"
            with self.assertRaises(FileExistsError):
                save_surface_reaches(result, path)
            changed = _plain(result)
            changed["reaches"][0]["contributing_area_m2"][0] += 1
            changed.pop("identity_sha256")
            changed["identity_sha256"] = _hash(changed)
            bad = Path(temporary) / "bad.json"
            save_surface_reaches(changed, bad)
            with self.assertRaises(ValueError):
                load_surface_reaches(bad, expected_sha256=file_sha256(bad), expected_identity=changed["identity_sha256"], hierarchy=hierarchy, storage=storage)

    def test_invalid_threshold_pin_cycle_and_uphill(self):
        hierarchy = fixture([[3, 2, 1]])
        for threshold in (True, 0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                build(hierarchy, threshold)
        with self.assertRaises(ValueError):
            make_surface_reaches(hierarchy, threshold_area_m2=1, expected_hierarchy_identity="0" * 64)
        result = build(hierarchy, 100)
        self.assertEqual(result["summary"]["reach_count"], 0)

    def test_rehashed_cycle_and_uphill_receiver_rejected(self):
        from terrain_pipeline.mountain_source_adapter import identity
        hierarchy = fixture([[3, 2, 1]])
        for receiver in (np.array([1, 0, -1], np.int64), np.array([-1, 0, 1], np.int64)):
            changed = {"metadata": hierarchy["metadata"], "arrays": dict(hierarchy["arrays"])}
            changed["arrays"]["receiver"] = receiver
            changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
            with self.assertRaises(ValueError):
                build(changed)
