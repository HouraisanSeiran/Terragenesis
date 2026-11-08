import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, save_bundle
from terrain_pipeline.common_infra import BoundaryGrid, RoutingGraph, TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import diagnostic_mesh as diagnostic_mesh
from terrain_pipeline.drainage import compare_routing_policies as compare_routing_policies
from terrain_pipeline.drainage import decode_routing_comparison as decode_routing_comparison
from terrain_pipeline.drainage import load_routing_comparison as load_routing_comparison
from terrain_pipeline.drainage import route_priority_flood as route_priority_flood
from terrain_pipeline.drainage import save_routing_comparison as save_routing_comparison


def fixture(height, *, outlets=(), unknown=(), dx=3., dz=4.):
    values = np.asarray(height, np.float64)
    valid = np.ones(values.shape, bool)
    for row, col in unknown:
        valid[row, col] = False
    terrain = TerrainGrid(values, valid, 0., 0., dx, dz, "diagnostic_dem_proxy",
                          "fixture", "a" * 64)
    kind = np.full(values.shape, "interior", dtype="U24")
    kind[[0, -1], :] = "closed_wall"
    kind[:, [0, -1]] = "closed_wall"
    kind[~valid] = "unknown_boundary"
    for row, col in outlets:
        kind[row, col] = "open_outflow"
    boundary = BoundaryGrid(kind, np.zeros(kind.shape, bool), "fixture", "b" * 64)
    return terrain, boundary


class RoutingComparisonTests(unittest.TestCase):
    def test_priority_flood_fills_working_basin_without_changing_original(self):
        terrain, boundary = fixture([[5., 5., 5.], [5., 0., 4.], [5., 5., 2.]], outlets=[(2, 2)])
        original = terrain.elevation_m.copy()
        result = route_priority_flood(terrain, boundary)
        self.assertEqual(result["working_elevation_m"][1, 1], 4.)
        self.assertEqual(result["fill_depth_m"][1, 1], 4.)
        self.assertEqual(result["graph"].outlet_kind[8], "open_outflow")
        self.assertEqual(result["graph"].receiver[4], 5)
        np.testing.assert_array_equal(terrain.elevation_m, original)

    def test_closed_or_unknown_components_are_not_assumed_open(self):
        terrain, boundary = fixture([[3., 3., 3.], [3., 0., 3.], [3., 3., 3.]])
        result = route_priority_flood(terrain, boundary)
        np.testing.assert_array_equal(result["working_elevation_m"], terrain.elevation_m)
        self.assertEqual(result["graph"].outlet_kind[4], "lake_preserved")
        unknown_terrain, unknown_boundary = fixture([[2., 1., 2.], [2., 0., 2.], [2., 2., 2.]],
                                                    unknown=[(1, 2)])
        unresolved = route_priority_flood(unknown_terrain, unknown_boundary)
        np.testing.assert_array_equal(unresolved["working_elevation_m"], unknown_terrain.elevation_m)
        self.assertEqual(unresolved["graph"].outlet_kind[4], "unknown_boundary")

    def test_unknown_boundary_blocks_flood_from_known_outlet(self):
        values = np.array([[0., 0., 0., 0., 0.], [5., 0., 1., 4., 2.],
                           [0., 0., 0., 0., 0.]])
        valid = np.zeros(values.shape, bool)
        valid[1, :] = True
        terrain = TerrainGrid(values, valid, 0., 0., 3., 4., "diagnostic_dem_proxy", "fixture", "a" * 64)
        kind = np.full(values.shape, "unknown_boundary", dtype="U24")
        kind[1] = ["closed_wall", "interior", "unknown_boundary", "interior", "open_outflow"]
        boundary = BoundaryGrid(kind, np.zeros(kind.shape, bool), "fixture", "b" * 64)
        result = route_priority_flood(terrain, boundary)
        self.assertEqual(result["working_elevation_m"][1, 1], 0.)
        self.assertEqual(result["working_elevation_m"][1, 2], 1.)
        self.assertEqual(result["working_elevation_m"][1, 3], 4.)
        self.assertEqual(result["metadata"]["flood_reached_valid_cells"], 2)
        with self.assertRaises(ValueError):
            result["working_elevation_m"][1, 1] = 99.

    def test_unknown_catchment_is_excluded_even_with_known_outlet_nearby(self):
        terrain, boundary = fixture([[5., np.nan, 5., 5., 5.],
                                     [5., 0., 4., 3., 2.],
                                     [5., 5., 5., 5., 5.]],
                                    unknown=[(0, 1)], outlets=[(1, 4)])
        result = route_priority_flood(terrain, boundary)
        self.assertEqual(result["working_elevation_m"][1, 1], 0.)
        self.assertTrue(result["unknown_catchment_excluded_mask"][1, 1])
        self.assertGreater(result["metadata"]["unknown_catchment_excluded_cells"], 0)

    def test_comparison_keeps_metric_flat_irregular_distinct_and_cold_loads_without_rerouting(self):
        terrain, boundary = fixture([[6., 6., 6.], [6., 4., 6.], [6., 6., 0.]], outlets=[(2, 2)])
        result = compare_routing_policies(terrain, boundary)
        graphs = decode_routing_comparison(result)
        self.assertEqual(set(graphs), {"original_bed_irregular", "priority_flood_irregular", "metric_flat_irregular"})
        self.assertNotEqual(graphs["original_bed_irregular"].policy,
                            graphs["metric_flat_irregular"].policy)
        self.assertEqual(graphs["original_bed_irregular"].outlet_kind[4], "lake_preserved")
        self.assertEqual(result["metadata"]["policies"]["metric_flat_irregular"]["relation_to_frozen_td_d4"],
                         "independent_metric_plateau_not_frozen_td_hierarchy")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.npz"
            save_routing_comparison(path, result)
            with patch('terrain_pipeline.drainage.route_diagnostic',
                       side_effect=AssertionError("cold load rerouted")), patch(
                           'terrain_pipeline.drainage.route_priority_flood',
                           side_effect=AssertionError("cold load reflooded")), patch(
                               'terrain_pipeline.drainage._route_metric_flat',
                               side_effect=AssertionError("cold load rebuilt D4")):
                cold = load_routing_comparison(path, expected_sha256=file_sha256(path),
                                               expected_identity=result["identity_sha256"])
            self.assertEqual(cold["identity_sha256"], result["identity_sha256"])
            self.assertEqual(decode_routing_comparison(cold)["metric_flat_irregular"].identity_sha256,
                             graphs["metric_flat_irregular"].identity_sha256)
            with self.assertRaises(ValueError):
                load_routing_comparison(path, expected_sha256="0" * 64)

    def test_rectangular_plane_routes_by_metric_slope_and_repeats_identity(self):
        terrain, boundary = fixture([[9., 6., 3.], [8., 5., 3.], [7., 4., 0.]],
                                    outlets=[(2, 2)], dx=3., dz=4.)
        first = compare_routing_policies(terrain, boundary)
        second = compare_routing_policies(terrain, boundary)
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        graph = decode_routing_comparison(first)["original_bed_irregular"]
        mesh = diagnostic_mesh(terrain)
        source, target = 4, int(graph.receiver[4])
        distance = np.hypot(mesh.node_x_m[target] - mesh.node_x_m[source],
                            mesh.node_z_m[target] - mesh.node_z_m[source])
        self.assertAlmostEqual(graph.edge_length_m[source], distance)
        self.assertAlmostEqual(graph.edge_slope[source],
                               (terrain.elevation_m.flat[source] - terrain.elevation_m.flat[target]) / distance)
        self.assertEqual(first["metadata"]["policies"]["original_bed_irregular"]["tie_break"],
                         "steepest_metric_slope_then_cell_id; plateau_bfs_distance_then_cell_id")

    def test_flat_multi_outlet_and_prescribed_boundary_ledger(self):
        terrain, _ = fixture([[2., 2., 2., 2.]])
        kind = np.array([["open_outflow", "closed_wall", "closed_wall", "prescribed_stage"]])
        boundary = BoundaryGrid(kind, np.zeros((1, 4), bool), "fixture", "b" * 64,
                                stage_m=np.array([[0., 0., 0., 2.]]))
        graphs = decode_routing_comparison(compare_routing_policies(terrain, boundary))
        for graph in graphs.values():
            ledger = accumulate_local_discharge(graph, np.ones((1, 4)))
            self.assertEqual(ledger["input_total_m3_s"], 4.)
            self.assertEqual(ledger["open_outflow_m3_s"] +
                             ledger["prescribed_boundary_candidate_m3_s"], 4.)
            self.assertEqual(ledger["residual_m3_s"], 0.)

    def test_prescribed_discharge_remains_terminal_candidate(self):
        terrain, _ = fixture([[2., 1.]])
        kind = np.array([["closed_wall", "prescribed_discharge"]])
        boundary = BoundaryGrid(kind, np.zeros((1, 2), bool), "fixture", "b" * 64,
                                discharge_m3_s=np.array([[0., 5.]]))
        result = compare_routing_policies(terrain, boundary)
        for graph in decode_routing_comparison(result).values():
            self.assertEqual(graph.outlet_kind[1], "prescribed_discharge")
            self.assertEqual(graph.receiver[1], -1)
            self.assertEqual(accumulate_local_discharge(graph, np.ones((1, 2)))[
                "prescribed_boundary_candidate_m3_s"], 2.)

    def test_rehashed_cold_package_rejects_false_flood_and_policy_claims(self):
        terrain, boundary = fixture([[5., 5., 5.], [5., 0., 4.], [5., 5., 2.]], outlets=[(2, 2)])
        original = compare_routing_policies(terrain, boundary)
        for change in ("filled_count", "lake_semantics", "capability"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                forged = {"arrays": {key: value.copy() for key, value in original["arrays"].items()},
                          "metadata": copy.deepcopy(original["metadata"])}
                if change == "filled_count":
                    forged["metadata"]["flood"]["filled_cell_count"] += 1
                elif change == "lake_semantics":
                    forged["metadata"]["lake_id_semantics"] = "wet_lake_footprint"
                else:
                    forged["metadata"]["hydraulic_ready"] = True
                forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
                path = Path(directory) / "forged.npz"
                save_bundle(path, forged, validator=lambda _: None)
                with self.assertRaises(ValueError):
                    load_routing_comparison(path, expected_sha256=file_sha256(path))

    def test_rehashed_unknown_mask_and_lake_id_cannot_change_classification(self):
        terrain, boundary = fixture([[5., np.nan, 5., 5., 5.],
                                     [5., 0., 4., 3., 2.],
                                     [5., 5., 5., 5., 5.]], unknown=[(0, 1)], outlets=[(1, 4)])
        original = compare_routing_policies(terrain, boundary)
        with tempfile.TemporaryDirectory() as directory:
            forged = {"arrays": {key: value.copy() for key, value in original["arrays"].items()},
                      "metadata": copy.deepcopy(original["metadata"])}
            forged["arrays"]["unknown_catchment_excluded_mask"][1, 1] = False
            forged["metadata"]["flood"]["unknown_catchment_excluded_cells"] -= 1
            forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
            path = Path(directory) / "unknown.npz"
            save_bundle(path, forged, validator=lambda _: None)
            with self.assertRaises(ValueError):
                load_routing_comparison(path, expected_sha256=file_sha256(path))
        lake_terrain, lake_boundary = fixture([[4., 4., 4.], [4., 0., 4.], [4., 4., 4.]])
        original = compare_routing_policies(lake_terrain, lake_boundary)
        with tempfile.TemporaryDirectory() as directory:
            forged = {"arrays": {key: value.copy() for key, value in original["arrays"].items()},
                      "metadata": copy.deepcopy(original["metadata"])}
            graph = decode_routing_comparison(original)["original_bed_irregular"]
            ids = forged["arrays"]["original_bed_irregular_lake_id"]
            ids[ids >= 0] = 99
            changed = RoutingGraph(graph.receiver, graph.order_downstream_first, graph.valid_mask,
                                   graph.edge_length_m, graph.edge_slope, graph.outlet_kind, ids,
                                   graph.terrain_identity_sha256, graph.boundary_identity_sha256,
                                   policy=graph.policy)
            forged["metadata"]["policies"]["original_bed_irregular"]["graph_identity_sha256"] = changed.identity_sha256
            forged["metadata"]["flood"]["original_bed_graph_identity_sha256"] = changed.identity_sha256
            forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
            path = Path(directory) / "lake.npz"
            save_bundle(path, forged, validator=lambda _: None)
            with self.assertRaises(ValueError):
                load_routing_comparison(path, expected_sha256=file_sha256(path))


if __name__ == "__main__":
    unittest.main()
