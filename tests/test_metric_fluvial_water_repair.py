import unittest
from types import SimpleNamespace
from unittest.mock import patch
import importlib
import tempfile

import numpy as np

from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import (
    WaterRoutingRepair, graph_connection, mask_inlet_upstream_weights, repair_loop_returns,
)
from terrain_pipeline.drainage import grid_mesh as grid_mesh


class WaterRepairTests(unittest.TestCase):
    def test_native_wrapper_uses_current_depth_preserves_flags_and_restores_native(self):
        native = importlib.import_module("pyDeltaRCM.water_tools")
        calls = []
        model = SimpleNamespace(time_iter=4096, _itermax=3, _Np_water=1, L=5, W=5,
            depth=np.ones((5, 5)), cell_type=np.zeros((5, 5), dtype=int), dry_depth=.01,
            account_water_relocation_segment=lambda *args, **kwargs: calls.append(args))
        flags = np.array([0])
        def original(walk, proposal, *args):
            proposal[:] = 18
            return proposal, flags
        repair = WaterRoutingRepair()
        with patch.object(native, "_check_for_loops", original):
            for expected in (18, 6):
                repair.begin(model)
                with repair.native_loop_calls(model):
                    returned, actual_flags = native._check_for_loops(None, np.array([6]), 1, 0, 0, None)
                self.assertEqual(returned[0], expected)
                self.assertIs(actual_flags, flags)
                self.assertIs(native._check_for_loops, original)
                path = graph_connection(6, 18, 5, shape=(5, 5))
                model.depth[path[1]] = .01
            self.assertEqual(len(calls), len(path) - 1)
            self.assertEqual(repair.iterations[0]["accepted_graph_steps"], len(path) - 1)
            self.assertEqual(repair.iterations[1]["rejected_connections"], {"dry": 1})

    def test_continuous_repair_requires_explicit_v5_precision_and_terminal_stays_forbidden(self):
        import json
        from pathlib import Path
        from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import (
            MorphodynamicsConfig, QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION,
            mechanism_identity_for, simulate_fluvial_morphodynamics,
        )
        self.assertNotEqual(mechanism_identity_for(QUANTIZED_EXCHANGE_VERSION),
            mechanism_identity_for(WATER_ROUTING_REPAIR_VERSION))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "continuous water repair"):
                simulate_fluvial_morphodynamics(output_dir=directory, water_routing_repair=True)
            parent = Path(directory) / "parent"
            parent.mkdir()
            (parent / "adapter-continuation.json").write_text(json.dumps({"diagnostic_only": True}))
            with self.assertRaisesRegex(ValueError, "terminal and cannot continue"):
                simulate_fluvial_morphodynamics(output_dir=Path(directory) / "output", resume_checkpoint=parent,
                    config=MorphodynamicsConfig(steps=1), gravity_stability=True, routing_dry_depth_m=.01,
                    quantized_native_exchange=True, water_routing_repair=True)

    def native_flux(self):
        from pyDeltaRCM.water_tools import water_tools
        model = SimpleNamespace(qxn=np.zeros((5, 5)), qyn=np.zeros((5, 5)),
            qwn=np.zeros((5, 5)), Qp_water=.07, _dx=5., log_info=lambda *args, **kwargs: None)
        return model, lambda *args, **kwargs: water_tools.update_Q(model, *args, **kwargs)

    def test_legal_graph_connection_accounts_original_native_flux_at_both_ends(self):
        model, update = self.native_flux()
        returned = np.array([18])
        decisions = repair_loop_returns(np.array([6]), returned, np.ones((5, 5)),
            np.zeros((5, 5), dtype=int), .01, update)
        self.assertEqual(decisions[0][-1], "accepted")
        path = graph_connection(6, 18, 5, shape=(5, 5))
        mesh = grid_mesh((5, 5), dx_m=1.)
        nodes = np.array([r * 5 + c for r, c in path])
        dx = np.diff(mesh.node_x_m[nodes])
        dz = np.diff(mesh.node_z_m[nodes])
        lengths = np.hypot(dx, dz)
        np.testing.assert_array_equal(returned, [18])
        self.assertAlmostEqual(model.qxn.sum(), 2 * np.sum(dz / lengths))
        self.assertAlmostEqual(model.qyn.sum(), 2 * np.sum(dx / lengths))
        self.assertAlmostEqual(model.qwn.sum(), (len(path) - 1) * .07 / 5.)

    def test_dry_and_wall_on_graph_path_retain_proposal_without_flux(self):
        path = graph_connection(6, 18, 5, shape=(5, 5))
        for kind in ("dry", "wall_or_invalid"):
            with self.subTest(kind=kind):
                depth, celltype = np.ones((5, 5)), np.zeros((5, 5), dtype=int)
                cell = path[1]
                if "dry" in kind:
                    depth[cell] = .01
                else:
                    celltype[cell] = -2
                returned = np.array([18])
                calls = []
                decisions = repair_loop_returns(np.array([6]), returned, depth, celltype,
                    .01, lambda *args, **kwargs: calls.append(args))
                self.assertEqual(decisions[0][-1], kind)
                np.testing.assert_array_equal(returned, [6])
                self.assertEqual(calls, [])

    def test_row0_upstream_weights_are_zero_and_empty_legal_set_rejects(self):
        weights = np.ones((5, 5, 9)) / 9.
        celltype = np.zeros((5, 5), dtype=int)
        celltype[0, 2] = 1
        jwalk = np.repeat([-1, 0, 1], 3)
        old = weights.copy()
        report = mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights[0, 2, :3], 0.)
        self.assertAlmostEqual(weights[0, 2].sum(), 1.)
        np.testing.assert_array_equal(weights[1:], old[1:])
        self.assertEqual(report["changed_cells"], 1)
        weights[0, 2] = 0.
        weights[0, 2, :3] = 1./3.
        with self.assertRaisesRegex(ValueError, "no legal non-upstream"):
            mask_inlet_upstream_weights(weights, jwalk, celltype)


if __name__ == "__main__":
    unittest.main()
