import copy
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, save_bundle
from terrain_pipeline.surface_rivers.metric_contracts import BoundaryGrid, RoutingGraph, TerrainGrid
from terrain_pipeline.surface_rivers.metric_reference_routing import (
    OptionalDependencyError, ReferenceBoundaryUnsupported, ReferenceRoutingConfig,
    ReferenceRoutingResult, analyze_td_graph, compare_reference_to_td,
    result_to_record, run_reference_routing, validate_reference_record)


def fixture():
    valid = np.ones((3, 3), dtype=bool)
    valid[1, 1] = False
    terrain = TerrainGrid(np.array([[8., 7., 6.], [5., 0., 4.], [3., 2., 1.]]),
                          valid, 10., 20., 2.7, 3.1, "generated_terrain", "fixture", "a" * 64)
    boundary_kind = np.full((3, 3), "closed_wall", dtype="U24")
    boundary_kind[1, 1] = "unknown_boundary"
    boundary_kind[2, 2] = "open_outflow"
    boundary = BoundaryGrid(boundary_kind, np.zeros((3, 3), bool), "fixture", "b" * 64)
    receiver = np.array([1, 2, 5, 6, -1, 8, 7, 8, -1], dtype=np.int64)
    order = np.array([8, 5, 7, 2, 6, 1, 3, 0], dtype=np.int64)
    kinds = np.full(9, "interior", dtype="U24")
    kinds[4], kinds[8] = "inactive", "open_outflow"
    length = np.array([2.7, 2.7, 3.1, 3.1, 0., 3.1, 2.7, 2.7, 0.])
    graph = RoutingGraph(receiver, order, valid, length, np.zeros(9), kinds,
                         np.full(9, -1, dtype=np.int64), terrain.identity_sha256,
                         boundary.identity_sha256)
    return terrain, boundary, graph


def reference_fixture():
    terrain, boundary, graph = fixture()
    return ReferenceRoutingResult(
        backend="pyflwdir", version="0.5.12", config=ReferenceRoutingConfig(),
        receiver=graph.receiver, order_downstream_first=graph.order_downstream_first,
        upstream_area_m2=np.array([1, 2, 3, 1, 0, 4, 2, 3, 8.]) * terrain.cell_area_m2,
        basin_id=np.array([8, 8, 8, 8, -1, 8, 8, 8, 8], dtype=np.int64),
        stream_order=np.array([1, 1, 1, 1, 0, 1, 1, 1, 2], dtype=np.int64),
        terrain_identity=terrain.identity_sha256, boundary_identity=boundary.identity_sha256,
        valid_mask=terrain.valid_mask, cell_area_m2=terrain.cell_area_m2,
        outlet_kind=graph.outlet_kind,
        metadata={"mode": "preserved_td_graph", "source_graph_identity_sha256": graph.identity_sha256,
                  "nested": {"values": [1, 2]}})


class ReferenceRoutingTests(unittest.TestCase):
    def test_config_and_incompatible_dem_policy_fail_before_backend(self):
        for kwargs in ({"max_depth": 0}, {"max_depth": float("nan")}, {"nodata": True},
                       {"max_depth": "1"}, {"max_depth": 10**1000}, {"outlets": "outside"}):
            with self.assertRaises(ValueError):
                ReferenceRoutingConfig(**kwargs)
        self.assertEqual(ReferenceRoutingConfig(max_depth=.5).max_depth, .5)
        terrain, boundary, _ = fixture()
        with patch.dict(sys.modules, {"pyflwdir": None}):
            with self.assertRaisesRegex(ReferenceBoundaryUnsupported, "nodata"):
                run_reference_routing(terrain, boundary)

    def test_missing_dependency_does_not_silently_fall_back(self):
        terrain, boundary, graph = fixture()
        with patch.dict(sys.modules, {"pyflwdir": None}):
            with self.assertRaisesRegex(OptionalDependencyError, "requirements-reference"):
                analyze_td_graph(terrain, boundary, graph)

    def test_masks_order_self_pits_and_immutability(self):
        result = reference_fixture()
        self.assertEqual(result.order_downstream_first.size, 8)
        self.assertEqual(result.receiver.size, 9)
        mutable = result.receiver.copy()
        detached = replace(result, receiver=mutable)
        mutable[0] = 0
        self.assertEqual(detached.receiver[0], 1)
        with self.assertRaises(ValueError):
            detached.receiver.setflags(write=True)
        with self.assertRaises(TypeError):
            result.metadata["nested"]["values"] = []
        with self.assertRaisesRegex(ValueError, "neighbour"):
            replace(result, receiver=mutable)
        with self.assertRaisesRegex(ValueError, "each valid cell"):
            replace(result, order_downstream_first=np.arange(9, dtype=np.int64))

    def test_comparison_uses_terminal_ids_and_not_sort_order(self):
        result = reference_fixture()
        terrain, boundary, graph = fixture()
        alternate = np.array([8, 7, 5, 6, 3, 2, 1, 0], dtype=np.int64)
        changed = replace(result, order_downstream_first=alternate)
        report = compare_reference_to_td(changed, graph)
        self.assertEqual(set(report["mismatch_counts"].values()), {0})
        with self.assertRaisesRegex(ValueError, "terrain identity"):
            compare_reference_to_td(replace(result, terrain_identity="c" * 64), graph)
        with self.assertRaisesRegex(ValueError, "D8 neighbour"):
            compare_reference_to_td(replace(result, valid_mask=result.valid_mask.reshape(1, 9)), graph)
        self.assertEqual(result.cell_area_m2, terrain.dx_m * terrain.dz_m)

    def test_standard_bundle_cold_read_and_rehashed_tampering(self):
        record = result_to_record(reference_fixture())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.npz"
            save_bundle(path, record, validator=validate_reference_record)
            with patch.dict(sys.modules, {"pyflwdir": None}):
                loaded = load_bundle(path, expected_sha256=file_sha256(path), validator=validate_reference_record)
            self.assertEqual(record["identity_sha256"], loaded["identity_sha256"])
        for key in ("upstream_area_m2", "basin_id", "stream_order", "capability"):
            changed = {"arrays": {name: values.copy() for name, values in record["arrays"].items()},
                       "metadata": copy.deepcopy(record["metadata"])}
            if key == "capability":
                changed["metadata"]["hydraulic_ready"] = True
            else:
                changed["arrays"][key][8] += 1
            changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
            with self.subTest(field=key), self.assertRaises(ValueError):
                validate_reference_record(changed)


@unittest.skipUnless(importlib.util.find_spec("pyflwdir"), "install algorithm/requirements-reference.txt")
class RealPyflwdirTests(unittest.TestCase):
    def test_real_library_preserves_mask_y_join_and_boundary_classification(self):
        terrain, boundary, graph = fixture()
        result = analyze_td_graph(terrain, boundary, graph)
        expected = reference_fixture()
        np.testing.assert_array_equal(result.receiver, expected.receiver)
        np.testing.assert_allclose(result.upstream_area_m2, expected.upstream_area_m2, atol=1e-12, rtol=0.)
        np.testing.assert_array_equal(result.basin_id, expected.basin_id)
        np.testing.assert_array_equal(result.stream_order, expected.stream_order)
        self.assertEqual(result.upstream_area_m2[4], 0.)
        self.assertEqual(result.metadata["transform"][2] + terrain.dx_m / 2., terrain.x0_m)
        self.assertEqual(result.metadata["transform"][5] - terrain.dz_m / 2., -terrain.z0_m)
        self.assertEqual(compare_reference_to_td(result, graph)["mismatch_counts"]["receiver"], 0)
        for kind in ("lake_preserved", "unknown_boundary", "prescribed_stage"):
            kinds = graph.outlet_kind.copy()
            kinds[8] = kind
            basin = np.full(9, -1, dtype=np.int64)
            if kind == "lake_preserved":
                basin[terrain.valid_mask.ravel()] = 8
            varied_graph = replace(graph, outlet_kind=kinds, lake_id=basin)
            varied = analyze_td_graph(terrain, boundary, varied_graph)
            self.assertEqual(varied.outlet_kind[8], kind)
            np.testing.assert_array_equal(varied.receiver, graph.receiver)

    def test_dem_reference_reports_different_exit_policy(self):
        from terrain_pipeline.surface_rivers.metric_drainage import route_diagnostic
        terrain = TerrainGrid(np.array([[4., 3., 2.], [5., 1., 2.], [6., 4., 0.]]),
                              np.ones((3, 3), bool), 10., 20., 3., 3., "generated_terrain", "tiny", "a" * 64)
        perimeter = np.ones((3, 3), bool)
        perimeter[1, 1] = False
        boundary = BoundaryGrid.from_outlet_mask(terrain, perimeter, source_id="tiny", source_sha256="b" * 64)
        original = terrain.elevation_m.copy()
        result = run_reference_routing(terrain, boundary)
        self.assertEqual(result.receiver[8], -1)
        self.assertEqual(result.outlet_kind[8], "reference_edge_exit")
        self.assertEqual(result.upstream_area_m2[8], 81.)
        report = compare_reference_to_td(result, route_diagnostic(terrain, boundary))
        self.assertFalse(report["equivalent_boundary_policy"])
        self.assertGreater(report["mismatch_counts"]["receiver"], 0)
        np.testing.assert_array_equal(terrain.elevation_m, original)
        with self.assertRaisesRegex(ReferenceBoundaryUnsupported, "metric dx/dz"):
            run_reference_routing(replace(terrain, dx_m=4.), boundary)
        with self.assertRaisesRegex(ValueError, "collides"):
            run_reference_routing(terrain, boundary, ReferenceRoutingConfig(nodata=4.))


if __name__ == "__main__":
    unittest.main()
