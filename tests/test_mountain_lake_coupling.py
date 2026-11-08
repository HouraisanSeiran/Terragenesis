import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_mountain_source_adapter import mock_source
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.lake import build_group_topology as build_group_topology
from terrain_pipeline.lake import contribution_mask as contribution_mask
from terrain_pipeline.lake import couple_rainfall as couple_rainfall
from terrain_pipeline.lake import group_lake_specs as group_lake_specs
from terrain_pipeline.lake import load_coupling as load_coupling
from terrain_pipeline.lake import local_allocation as local_allocation
from terrain_pipeline.lake import save_coupling as save_coupling
from terrain_pipeline.lake import single_pool_proof as single_pool_proof
from terrain_pipeline.lake import terminal_ownership as terminal_ownership
from terrain_pipeline.lake import validate_coupling as validate_coupling
from terrain_pipeline.lake import validate_selection as validate_selection


def mock_topology():
    source = mock_source()
    receiver = np.arange(25, dtype=np.int64).reshape(5, 5) + 1
    receiver[:, -1] = -1
    anchor = np.full((5, 5), -1, np.int64)
    anchor[:, -1] = np.arange(5)
    geometry = {"arrays": {"H0_m": source["arrays"]["height_m"], "receiver": receiver,
        "accepted_mask": np.ones((5, 5), bool)}, "metadata": {"mock_only": True}}
    topology = {"receiver": receiver, "anchor_node": anchor, "node_downstream": np.full(5, -1, np.int64),
        "node_kind": ["river"] * 5, "node_boundary_type": ["external_open_boundary"] * 5,
        "tau_s": np.full(5, 1800., np.float64), "source_identity": source["identity_sha256"],
        "geometry_identity": identity(geometry["arrays"], geometry["metadata"]),
        "geometry_passed": True, "boundary_policy": "all_edges_open"}
    owner = np.zeros((5, 5), np.int64)
    return source, topology, owner, geometry


class CouplingTests(unittest.TestCase):
    def setUp(self):
        self.binding_patch = patch('terrain_pipeline.lake.geometry_binding',
            side_effect=lambda source, topology, geometry, selection=None: True if geometry else (_ for _ in ()).throw(ValueError("geometry missing")))
        self.binding_patch.start()
        self.addCleanup(self.binding_patch.stop)

    def test_many_terminals_partition_without_dynamic_nodes(self):
        receiver = np.full((60, 60), -1, np.int64)
        partition = terminal_ownership(receiver, np.ones(receiver.shape, bool))
        self.assertEqual(partition["terminal_flat"].size, 3600)
        self.assertEqual(partition["contributing_counts"].sum(), 3600)

    def test_nonlocal_graph_edge_preserves_ownership_but_cannot_cross_unknown(self):
        receiver = np.full((4, 6), -1, np.int64)
        receiver[1, 1] = 1 * 6 + 4
        valid = np.ones(receiver.shape, bool)
        partition = terminal_ownership(receiver, valid)
        self.assertEqual(partition['terminal_owner'][1, 1], 10)
        valid[1, 2] = False
        with self.assertRaisesRegex(ValueError, 'segment crosses'):
            terminal_ownership(receiver, valid)

    def test_contribution_complete_and_first_node_allocation(self):
        source, topology, owner, geometry = mock_topology()
        mask, proof = contribution_mask(topology["receiver"], np.ones((5, 5), bool), 4)
        self.assertEqual(mask.sum(), 5)
        self.assertTrue(proof["upstream_complete_within_finite_window"])
        mapping = local_allocation(topology["receiver"], topology["anchor_node"], owner,
            source["arrays"]["hydrology_mask"], topology["node_downstream"], spacing_m=30., hrus=1)
        np.testing.assert_array_equal(mapping["allocation_counts"], np.full((5, 1), 5))

    def test_multi_outlet_complete_ledger_and_static_load(self):
        source, topology, owner, geometry = mock_topology()
        rain = np.r_[np.full((12, 1), 24.), np.zeros((48, 1))]
        result = couple_rainfall(source, topology, owner, rain, dt_s=900., geometry=geometry)
        stats = validate_coupling(result, source=source, topology=topology, geometry=geometry)
        self.assertLess(stats["max_joint_interval_residual_m3"], 1e-8)
        self.assertEqual(len(stats["outlet_volume_m3"]), 5)
        self.assertGreater(result["arrays"]["storage_m3"][-1].sum(), 0)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "coupling.npz"
            save_coupling(path, result)
            with patch('terrain_pipeline.lake.local_allocation', side_effect=AssertionError("prepare")), \
                    patch('terrain_pipeline.lake.couple_rainfall', side_effect=AssertionError("advance")), \
                    patch('terrain_pipeline.lake.evaluate_lake_routing', side_effect=AssertionError("solve")):
                loaded = load_coupling(path, expected_sha256=file_sha256(path), source=source,
                    topology=topology, geometry=geometry)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])

    def test_flags_cannot_replace_geometry(self):
        source, topology, owner, geometry = mock_topology()
        with self.assertRaises(ValueError):
            couple_rainfall(source, topology, owner, np.zeros((2, 1)), dt_s=900., geometry={})
        topology["geometry_passed"] = False
        result = couple_rainfall(source, topology, owner, np.zeros((2, 1)), dt_s=900., geometry={})
        self.assertFalse(result["dynamic_water_solved"])

    def test_resigned_bad_ownership_rejected_without_rebuild(self):
        source, topology, owner, geometry = mock_topology()
        result = couple_rainfall(source, topology, owner, np.ones((2, 1)), dt_s=900., geometry=geometry)
        forged = copy.deepcopy(result)
        forged["arrays"]["cell_node"] = result["arrays"]["cell_node"].copy()
        forged["arrays"]["cell_node"][0, 0] = 1
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaises(ValueError):
            validate_coupling(forged, source=source, topology=topology, geometry=geometry)

    def test_extra_member_header_rejected_before_numpy_load(self):
        import json

        source, topology, owner, geometry = mock_topology()
        result = couple_rainfall(source, topology, owner, np.ones((2, 1)), dt_s=900., geometry=geometry)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "forged.npz"
            manifest = json.dumps({"metadata": result["metadata"], "identity_sha256": result["identity_sha256"]}).encode()
            np.savez_compressed(path, manifest=np.frombuffer(manifest, dtype=np.uint8),
                unrelated=np.zeros((100, 100)), **result["arrays"])
            with patch("numpy.load", side_effect=AssertionError("allocated before schema preflight")):
                with self.assertRaises(ValueError):
                    load_coupling(path, expected_sha256=file_sha256(path), source=source,
                        topology=topology, geometry=geometry)

    def test_disconnected_intermediate_sublevel_rejected(self):
        height = np.full((7, 7), 10., np.float64)
        basin = np.zeros((7, 7), bool)
        basin[3, 2:5] = True
        height[3, 2:5] = [0., 3., 1.]
        height[3, 5:] = [5., 4.]
        legal = np.zeros((7, 7), bool)
        legal[3, 6] = True
        with self.assertRaisesRegex(ValueError, "disconnected sublevel"):
            single_pool_proof(height, basin, np.array([3, 5]), np.array([[3, 5], [3, 6]]),
                np.ones((7, 7), bool), np.zeros((7, 7), bool), legal, max_stage_m=6.)

    def test_equal_low_sills_cannot_be_ignored(self):
        height = np.full((7, 7), 10., np.float64)
        basin = np.zeros((7, 7), bool)
        basin[3, 3] = True
        height[3, 3] = 0.
        height[3, 4:] = [5., 4., 3.]
        height[2, 3] = 5.
        legal = np.zeros((7, 7), bool)
        legal[3, 6] = True
        with self.assertRaisesRegex(ValueError, "unmodeled low"):
            single_pool_proof(height, basin, np.array([3, 4]), np.array([[3, 4], [3, 5], [3, 6]]),
                np.ones((7, 7), bool), np.zeros((7, 7), bool), legal, max_stage_m=6.)

    def test_free_weir_rejects_receiving_stage_at_any_state(self):
        from terrain_pipeline.lake import _free_weir_tailwater as _free_weir_tailwater

        _free_weir_tailwater(5., np.array([0., 4., 5.]))
        with self.assertRaisesRegex(ValueError, "receiving_pool_submerges_free_weir"):
            _free_weir_tailwater(5., np.array([0., 5.01, 4.]))


class ActualGeometryCouplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.common_infra import load_legacy_source
        from terrain_pipeline.lake import load_mountain_geometry as load_mountain_geometry

        root = Path(__file__).resolve().parents[1]
        cls.source = load_legacy_source("pressure_mountain", boundary_policy="all_edges_open")
        path = root / "verification/mountain-lake-coupling/run-20261001T062620750889Z/pressure_mountain-geometry.npz"
        if not path.exists():
            raise unittest.SkipTest("fixed real-source geometry verification artifact unavailable")
        cls.geometry = load_mountain_geometry(path, trusted_height=cls.source["arrays"]["height_m"],
            source_binding={"source_identity": cls.source["identity_sha256"]})
        cls.topology, cls.selection, cls.lake_nodes = build_group_topology(cls.source, cls.geometry, 1639)
        mask = cls.selection["arrays"]["mask"]
        cls.owner = np.full(mask.shape, -1, np.int64)
        cls.owner[mask] = 0
        specs = group_lake_specs(cls.source, cls.geometry, cls.topology, cls.lake_nodes, steps=24)
        cls.result = couple_rainfall(cls.source, cls.topology, cls.owner, np.full((24, 1), 24.),
            dt_s=900., geometry=cls.geometry, selection=cls.selection, lakes=specs)

    def test_actual_B_geometry_rain_lake_river_coldload_without_mocks(self):
        stats = validate_coupling(self.result, source=self.source, topology=self.topology,
            geometry=self.geometry, selection=self.selection)
        self.assertLess(stats["max_joint_interval_residual_m3"], 1e-8)
        self.assertGreater(self.result["arrays"]["storage_m3"][:, 0].max(), 0.)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "real.npz"
            save_coupling(path, self.result)
            with patch('terrain_pipeline.lake.local_allocation', side_effect=AssertionError("prepare")), \
                    patch('terrain_pipeline.lake.evaluate_lake_routing', side_effect=AssertionError("advance")), \
                    patch('terrain_pipeline.lake.prepare_mountain_geometry', side_effect=AssertionError("geometry prepare")):
                loaded = load_coupling(path, expected_sha256=file_sha256(path), source=self.source,
                    topology=self.topology, geometry=self.geometry, selection=self.selection)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])

    def test_external_H0_and_grid_binding_tampering_rejected(self):
        for key in ("H0_m", "origin_m_xz", "spacing_m"):
            forged = copy.deepcopy(self.geometry)
            if key == "H0_m":
                forged["arrays"][key] = forged["arrays"][key].copy()
                forged["arrays"][key][0, 0] += 1.
            elif key == "origin_m_xz":
                forged["metadata"][key][0] += 30.
            else:
                forged["metadata"][key] = 60.
            with self.assertRaises(ValueError):
                validate_coupling(self.result, source=self.source, topology=self.topology,
                    geometry=forged, selection=self.selection)

    def test_source_mask_identity_not_replaced_by_selection(self):
        forged = copy.deepcopy(self.source)
        forged["arrays"]["hydrology_mask"] = self.selection["arrays"]["mask"]
        forged["arrays"]["display_mask"] = self.selection["arrays"]["mask"]
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaises(ValueError):
            validate_coupling(self.result, source=forged, topology=self.topology,
                geometry=self.geometry, selection=self.selection)

    def test_resigned_selection_cannot_drop_upstream_cell(self):
        forged = copy.deepcopy(self.selection)
        mask = forged["arrays"]["mask"].copy()
        mask.flat[np.flatnonzero(mask.ravel())[0]] = False
        forged["arrays"]["mask"] = mask
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaises(ValueError):
            validate_selection(self.source, self.topology, forged)

    def test_resigned_geometry_cannot_route_lake_as_linear_river(self):
        forged_topology = copy.deepcopy(self.topology)
        forged_topology["node_kind"][0] = "river"
        from terrain_pipeline.lake import geometry_binding as geometry_binding

        with self.assertRaises(ValueError):
            geometry_binding(self.source, forged_topology, self.geometry, self.selection)

    def test_fixed_surface_rain_partition_unique_total_area(self):
        specs = group_lake_specs(self.source, self.geometry, self.topology, self.lake_nodes, steps=24)
        result = couple_rainfall(self.source, self.topology, self.owner, np.full((24, 1), 24.),
            dt_s=900., geometry=self.geometry, selection=self.selection, lakes=specs, surface_rain=True)
        arrays = result["arrays"]
        self.assertEqual(arrays["surface_allocation_counts"].sum(), 1)
        self.assertEqual(arrays["land_allocation_counts"].sum(), 361)
        total_rain = arrays["runoff_rain_volume_m3"].sum() + arrays["surface_rain_volume_m3"].sum()
        self.assertAlmostEqual(total_rain, 24.*24.*.25/1000.*325800., places=8)
        validate_coupling(result, source=self.source, topology=self.topology,
            geometry=self.geometry, selection=self.selection)

    def test_actual_four_pool_cascade_path_and_tailwater_semantics(self):
        topology, selection, lake_nodes = build_group_topology(self.source, self.geometry, 1378)
        self.assertEqual(len(lake_nodes), 4)
        owner = np.full(selection["arrays"]["mask"].shape, -1, np.int64)
        owner[selection["arrays"]["mask"]] = 0
        specs = group_lake_specs(self.source, self.geometry, topology, lake_nodes, steps=16)
        result = couple_rainfall(self.source, topology, owner, np.full((16, 1), 3.), dt_s=900.,
            geometry=self.geometry, selection=selection, lakes=specs, surface_rain=True)
        self.assertIn("arrays", result)
        validate_coupling(result, source=self.source, topology=topology,
            geometry=self.geometry, selection=selection)
        from terrain_pipeline.lake import _check_pool_path as _check_pool_path

        for node, spec in specs.items():
            _check_pool_path(topology["receiver"], spec["downstream_path_grid_zx"], spec["legal_outlet_mask"],
                anchor_node=topology["anchor_node"], node_kind=topology["node_kind"], current_node=node,
                node_downstream=topology["node_downstream"])


if __name__ == "__main__":
    unittest.main()
