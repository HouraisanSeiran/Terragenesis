"""Unit/geometry contracts for the read-only acceptance atlas."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("acceptance_render", ROOT / "tools/render_project_acceptance.py")
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


class ProjectAcceptanceRenderTest(unittest.TestCase):
    def test_extent_uses_cell_edges_and_world_kilometres(self):
        self.assertEqual(render.extent((30000., 60000.), (2, 3), 30.),
                         [29.985, 30.075, 60.045, 59.985])

    def test_comparison_limits_include_both_scenarios(self):
        self.assertEqual(render.shared_limits([np.array([0., 1.]), np.array([-3., 5.])]), (-3., 5.))

    def test_display_threshold_keeps_accumulated_flow_and_source_immutable(self):
        network = {"reach_source": np.array([0, 1]), "reach_target": np.array([1, 2]),
                   "node_q_m3_s": np.array([.001, .2, .3]),
                   "node_x_m": np.array([0., 30., 60.]), "node_z_m": np.array([0., 0., 0.])}
        original = {k: v.copy() for k, v in network.items()}
        lines, sources = render.channel_segments(network, .1)
        np.testing.assert_array_equal(sources, [1])
        np.testing.assert_allclose(lines[0], [[.03, 0.], [.06, 0.]])
        for key in network:
            np.testing.assert_array_equal(network[key], original[key])


if __name__ == "__main__":
    unittest.main()
