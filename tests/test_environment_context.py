
from terrain_pipeline.environment_contract import bounded_field as _merged_radiation__field
from terrain_pipeline.environment_contract import grid as _merged_radiation__grid
from terrain_pipeline.environment_contract import positive_parameters as _merged_radiation__parameters
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import environment_contract as support
from terrain_pipeline import environment_processes as habitat
from terrain_pipeline import environment_processes as radiation
from terrain_pipeline import environment_contract as contract
from tests.test_environment_process_product import fixture


def saved_context():
    ctx = deepcopy(fixture()["context"])
    mesh = support.prepare_mesh(ctx, ctx["height_m"].shape)
    # Reverse the stored list to make consumer ordering differences observable.
    ctx["graph_edge_source"] = np.repeat(np.arange(25), np.diff(mesh.indptr))[::-1]
    ctx["graph_edge_target"] = mesh.indices[::-1]
    ctx["node_x_m"] = mesh.node_x_m.reshape(5, 5)
    ctx["node_z_m"] = mesh.node_z_m.reshape(5, 5)
    return ctx


class EnvironmentContextTests(unittest.TestCase):
    def test_saved_edges_skip_triangulation_and_preserve_consumer_order(self):
        ctx = saved_context()
        source, target = ctx["graph_edge_source"], ctx["graph_edge_target"]
        with patch.object(support, "build_mesh", side_effect=AssertionError("saved graph triangulated")):
            sorted_mesh = support.context_arrays(ctx, 1.)[2]
            stable_mesh = support.prepare_mesh(ctx, (5, 5), edge_order="stable")
            habitat.advance_habitat(habitat.initialize_habitat(ctx), {}, ctx, 0.)
        np.testing.assert_array_equal(sorted_mesh.indices, target[np.lexsort((target, source))])
        np.testing.assert_array_equal(stable_mesh.indices, target[np.argsort(source, kind="stable")])
        self.assertFalse(np.array_equal(sorted_mesh.indices, stable_mesh.indices))
        self.assertEqual(sorted_mesh.shape, (5, 5))
        self.assertEqual(sorted_mesh.spacing_m, 1.)

    def test_masks_are_filtered_by_consumer_and_zero_dt_semantics_remain_distinct(self):
        ctx = saved_context()
        ctx["valid_mask"][:, 2] = False
        ctx["receiver"][:] = -1
        filtered = support.context_arrays(ctx, 1.)[2]
        donors = np.repeat(np.arange(25), np.diff(filtered.indptr))
        self.assertTrue(support.segments_clear(donors, filtered.indices, ctx["valid_mask"]).all())
        raw = support.prepare_mesh(ctx, (5, 5), edge_order="stable")
        self.assertGreater(raw.indices.size, filtered.indices.size)
        with self.assertRaisesRegex(ValueError, "positive physical"):
            support.context_arrays(ctx, 0.)
        habitat.advance_habitat(habitat.initialize_habitat(ctx), {}, ctx, 0.)
        with self.assertRaisesRegex(ValueError, "nonnegative physical"):
            habitat.advance_habitat(habitat.initialize_habitat(ctx), {}, ctx, -1.)

    def test_saved_edge_validation_preserves_distinct_contracts(self):
        ctx = saved_context()
        ctx["graph_edge_source"] = np.array([0, 0])
        ctx["graph_edge_target"] = np.array([1, 1])
        with self.assertRaisesRegex(ValueError, "unique symmetric"):
            support.prepare_mesh(ctx, (5, 5))
        directed = support.prepare_mesh(ctx, (5, 5), edge_order="stable")
        np.testing.assert_array_equal(directed.indices, [1, 1])
        ctx["graph_edge_source"] = np.array([0.])
        ctx["graph_edge_target"] = np.array([1.])
        with self.assertRaisesRegex(ValueError, "saved graph edge arrays"):
            support.prepare_mesh(ctx, (5, 5), edge_order="stable")

    def test_radiation_compatibility_names_share_contract_implementations(self):
        self.assertIs(_merged_radiation__field, contract.bounded_field)
        self.assertIs(_merged_radiation__grid, contract.grid)
        self.assertIs(_merged_radiation__parameters, contract.positive_parameters)
