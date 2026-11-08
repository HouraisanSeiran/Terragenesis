import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_spill_network import _leaf_graph
from terrain_pipeline.td_surface_reaches import _plain, _hash
from terrain_pipeline.td_basin_escape_plan import make_basin_escape_plan, save_basin_escape_plan, load_basin_escape_plan


def fixture(height, boundary_cells, protected=None):
    values = np.asarray(height, float)
    opened = np.zeros(values.shape, bool)
    opened.ravel()[boundary_cells] = True
    source = make_td_source(np.nan_to_num(values), valid_mask=np.isfinite(values), spacing_m=1,
        open_boundary_mask=opened, protected_mask=protected)
    hierarchy = build_basin_hierarchy(source)
    graph = _leaf_graph(hierarchy, None)
    seeds = [{"leaf_id": int(hierarchy["arrays"]["contribution_owner"].ravel()[cell]), "boundary_cell_id": cell}
             for cell in boundary_cells]
    return hierarchy, graph, seeds


def plan(hierarchy, graph, seeds):
    return make_basin_escape_plan(hierarchy, contribution_leaf_graph=graph, engineering_seeds=seeds,
        expected_hierarchy_identity=hierarchy["identity_sha256"])


class BasinEscapePlanTests(unittest.TestCase):
    def test_nested_saddles_boundary_bed_and_exclusive_volume(self):
        hierarchy, graph, seeds = fixture([[1, 4, 0, 7, 2]], [0])
        result = plan(hierarchy, graph, seeds)
        by_terminal = {node["terminal_cell_id"]: next(record for record in result["leaves"] if record["leaf_id"] == node["leaf_id"]) for node in graph["leaf_nodes"]}
        self.assertEqual(by_terminal[0]["minimum_escape_stage_m"], 1)
        self.assertEqual(by_terminal[2]["minimum_escape_stage_m"], 4)
        self.assertEqual(by_terminal[4]["minimum_escape_stage_m"], 7)
        self.assertEqual(by_terminal[2]["raise_to_stage_volume_m3"], 4)
        self.assertEqual(by_terminal[4]["raise_to_stage_volume_m3"], 5)
        self.assertEqual(result["summary"]["exclusive_raise_to_stage_volume_m3"], 9)

    def test_multioutlet_chooses_minimax_and_seed_order_independent(self):
        hierarchy, graph, seeds = fixture([[1, 4, 0, 7, 2]], [0, 4])
        first = plan(hierarchy, graph, seeds)
        second = plan(hierarchy, graph, list(reversed(seeds)))
        self.assertEqual(_plain(first), _plain(second))
        center = next(record for record in first["leaves"] if record["minimum_face"] is not None)
        self.assertEqual(center["minimum_escape_stage_m"], 4)
        self.assertEqual(center["root_boundary_cell_id"], 0)

    def test_flat_sill_forest_no_equal_level_cycle(self):
        hierarchy, graph, seeds = fixture([[0, 3, 0, 3, 0, 3, 0]], [0])
        result = plan(hierarchy, graph, seeds)
        records = {item["leaf_id"]: item for item in result["leaves"]}
        for record in records.values():
            parent = record["parent_leaf_id"]
            if parent is not None:
                self.assertLess(records[parent]["settlement_rank"], record["settlement_rank"])
                self.assertEqual(record["minimum_escape_stage_m"], 3)
                face = record["minimum_face"]["face_index"]
                self.assertEqual(record["minimum_face"]["face_cell_ids"], tuple(map(int, hierarchy["arrays"]["face_cells"][face])))

    def test_no_seeds_and_disconnected_internal_preserved(self):
        hierarchy, graph, seeds = fixture([[0, 3, 0]], [0])
        result = plan(hierarchy, graph, [])
        self.assertTrue(all(not record["reachable"] and record["minimum_escape_stage_m"] is None for record in result["leaves"]))
        hierarchy, graph, seeds = fixture([[0, np.nan, 0]], [0])
        with self.assertRaises(ValueError):
            plan(hierarchy, graph, seeds)

    def test_protected_catchment_blocked_unreachable(self):
        hierarchy, graph, seeds = fixture([[0, 3, 0]], [0], np.array([[False, False, True]]))
        result = plan(hierarchy, graph, seeds)
        blocked = next(record for record in result["leaves"] if not record["reachable"])
        self.assertIn("protected_catchment", blocked["unreachable_reasons"])
        self.assertIsNone(blocked["raise_to_stage_volume_m3"])

    def test_seed_must_be_explicit_valid_engineering_cell(self):
        hierarchy, graph, seeds = fixture([[1, 4, 0]], [0])
        bad_inputs = [[dict(seeds[0], boundary_cell_id=2)], [seeds[0], seeds[0]],
                      [dict(seeds[0], leaf_id=999)], [dict(seeds[0], boundary_cell_id=True)]]
        for bad in bad_inputs:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                plan(hierarchy, graph, bad)

    def test_tied_faces_use_stable_physical_id(self):
        hierarchy, graph, seeds = fixture([[0, 2, 0], [0, 2, 0]], [0])
        result = plan(hierarchy, graph, seeds)
        from terrain_pipeline.td_basin_escape_plan import _face_id
        pair = graph["pairs"][0]
        expected = min(pair["minimum_face_indices"], key=lambda face: _face_id(hierarchy, face))
        chosen = next(record["minimum_face"]["face_index"] for record in result["leaves"] if record["parent_leaf_id"] is not None)
        self.assertEqual(chosen, expected)

    def test_geometry_tamper_and_external_hierarchy_identity(self):
        hierarchy, graph, seeds = fixture([[0, 3, 0]], [0])
        changed = _plain(graph)
        changed["pairs"][0]["minimum_physical_sill_m"] = 1
        with self.assertRaises(ValueError):
            plan(hierarchy, changed, seeds)
        with self.assertRaises(ValueError):
            make_basin_escape_plan(hierarchy, contribution_leaf_graph=graph, engineering_seeds=seeds, expected_hierarchy_identity="0" * 64)

    def test_cold_read_no_solver_no_public_generation_and_immutable(self):
        hierarchy, graph, seeds = fixture([[0, 3, 0]], [0])
        result = plan(hierarchy, graph, seeds)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            save_basin_escape_plan(result, path)
            kwargs = dict(expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"], hierarchy=hierarchy, contribution_leaf_graph=graph)
            with patch("terrain_pipeline.td_basin_escape_plan.make_basin_escape_plan", side_effect=AssertionError("make")), patch("terrain_pipeline.td_basin_storage.simulate_basin_storage", side_effect=AssertionError("solve")):
                loaded = load_basin_escape_plan(path, **kwargs)
            self.assertEqual(_plain(loaded), _plain(result))
            with self.assertRaises(TypeError):
                loaded["leaves"][0]["reachable"] = False
            for field in ("expected_sha256", "expected_identity"):
                changed = dict(kwargs)
                changed[field] = "0" * 64
                with self.assertRaises(ValueError):
                    load_basin_escape_plan(path, **changed)

    def test_rehashed_stage_parent_volume_tamper_rejected(self):
        hierarchy, graph, seeds = fixture([[0, 3, 0]], [0])
        original = plan(hierarchy, graph, seeds)
        mutations = [lambda value: value["leaves"][0].update(minimum_escape_stage_m=99),
                     lambda value: value["leaves"][0].update(parent_leaf_id=value["leaves"][0]["leaf_id"]),
                     lambda value: value["leaves"][0].update(raise_to_stage_volume_m3=99),
                     lambda value: value["flags"].update(hydraulic_verified=True)]
        with tempfile.TemporaryDirectory() as directory:
            for index, mutate in enumerate(mutations):
                value = _plain(original)
                mutate(value)
                value.pop("identity_sha256")
                value["identity_sha256"] = _hash(value)
                path = Path(directory) / f"tamper-{index}.json"
                save_basin_escape_plan(value, path)
                with self.subTest(index=index), self.assertRaises(ValueError):
                    load_basin_escape_plan(path, expected_sha256=file_sha256(path), expected_identity=value["identity_sha256"], hierarchy=hierarchy, contribution_leaf_graph=graph)


if __name__ == "__main__":
    unittest.main()
