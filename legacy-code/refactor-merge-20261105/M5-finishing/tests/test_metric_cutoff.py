import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import CutoffConfig, _crosses_centerline, _metric_cutoff_segments_intersect as _segments_intersect, find_cutoff_candidate
from terrain_pipeline.surface_rivers.metric_morphology_events import event_from_record


def terrain():
    height = np.zeros((15, 15), dtype=np.float64)
    return TerrainGrid(height, np.ones(height.shape, dtype=bool), 0., 0., 1., 1.,
                       "diagnostic_dem_proxy", "cutoff-test", "a" * 64)


def centerline():
    return np.array([[2., 2.], [2., 8.], [5., 8.], [8., 8.], [8., 2.],
                     [10., 2.]], dtype=np.float64)


class MetricCutoffTests(unittest.TestCase):
    def test_segment_filter_rejects_collinear_overlap_and_endpoint_touch(self):
        shortcut_start = np.array([0., 0.])
        shortcut_end = np.array([4., 0.])
        self.assertTrue(_segments_intersect(shortcut_start, shortcut_end,
                                             np.array([2., 0.]), np.array([6., 0.])))
        self.assertTrue(_segments_intersect(shortcut_start, shortcut_end,
                                             np.array([4., 0.]), np.array([4., 2.])))
        self.assertFalse(_segments_intersect(shortcut_start, shortcut_end,
                                              np.array([5., 0.]), np.array([5., 2.])))

    def test_only_shortcut_endpoint_incident_contacts_are_allowed(self):
        centerline = np.array([[0., 0.], [0., 1.], [1., 2.], [2., 1.], [3., 0.]], dtype=np.float64)
        self.assertFalse(_crosses_centerline(centerline[0], centerline[-1], centerline, 0, 4))
        self.assertTrue(_crosses_centerline(np.array([0., 0.]), np.array([0.5, 1.5]),
                                            centerline, 0, 4))

    def test_u_shape_success_and_event_contract(self):
        result = find_cutoff_candidate(terrain(), centerline(), tuple("e%d" % i for i in range(5)),
                                       "b" * 64, "c" * 64, 3., 2.,
                                       CutoffConfig(neck_distance_m=7., min_loop_length_m=5.))
        self.assertEqual(result["status"], "candidate")
        self.assertTrue(result["lake_candidate"])
        self.assertFalse(any(result["capabilities"].values()))
        event = result["event"]
        self.assertEqual(event.event_type, "cutoff")
        self.assertEqual(event.retired_edges, event.affected_edges)
        self.assertEqual(event.water_transfer_m3, 3.)
        self.assertEqual(event.sediment_transfer_solid_m3, 2.)
        self.assertEqual(event_from_record(event.to_record()).identity_sha256, event.identity_sha256)

    def test_no_legal_neck_and_unknown_or_ridge_are_rejected(self):
        config = CutoffConfig(neck_distance_m=1., min_loop_length_m=5.)
        self.assertEqual(find_cutoff_candidate(terrain(), centerline(), tuple("e%d" % i for i in range(5)),
                                                "b" * 64, "c" * 64, 0., 0., config)["status"], "rejected")
        masked = terrain().valid_mask.copy()
        masked[3, 5] = False
        unknown = TerrainGrid(terrain().elevation_m, masked, 0., 0., 1., 1.,
                              "diagnostic_dem_proxy", "cutoff-test", "a" * 64)
        self.assertEqual(find_cutoff_candidate(unknown, centerline(), tuple("e%d" % i for i in range(5)),
                                                "b" * 64, "c" * 64, 0., 0.,
                                                CutoffConfig(neck_distance_m=7., min_loop_length_m=5.))["status"], "rejected")
        ridge = np.zeros((15, 15), dtype=np.float64)
        ridge[2, 5] = 10.
        ridge_terrain = TerrainGrid(ridge, np.ones(ridge.shape, dtype=bool), 0., 0., 1., 1.,
                                    "diagnostic_dem_proxy", "cutoff-ridge", "a" * 64)
        self.assertEqual(find_cutoff_candidate(ridge_terrain, centerline(), tuple("e%d" % i for i in range(5)),
                                                "b" * 64, "c" * 64, 0., 0.,
                                                CutoffConfig(neck_distance_m=7., min_loop_length_m=5.))["status"], "rejected")

    def test_deterministic_and_invalid_inputs(self):
        kwargs = dict(terrain=terrain(), centerline_xz_m=centerline(), edge_ids=tuple("e%d" % i for i in range(5)),
                      parent_graph_identity_sha256="b" * 64, parent_geometry_identity_sha256="c" * 64,
                      water_transfer_m3=0., sediment_transfer_solid_m3=0.,
                      config=CutoffConfig(neck_distance_m=7., min_loop_length_m=5., seed=7))
        first, second = find_cutoff_candidate(**kwargs), find_cutoff_candidate(**kwargs)
        self.assertEqual(first["event"].identity_sha256, second["event"].identity_sha256)
        with self.assertRaises(ValueError):
            CutoffConfig(min_node_gap=1)
        with self.assertRaises(ValueError):
            find_cutoff_candidate(**{**kwargs, "centerline_xz_m": centerline().astype(np.float32)})
        with self.assertRaises(ValueError):
            find_cutoff_candidate(**{**kwargs, "water_transfer_m3": -1.})


if __name__ == "__main__":
    unittest.main()
