import unittest

import numpy as np

from terrain_pipeline.channel_geometry import FrozenPathConfig, clip_frozen_edge_path, prepare_frozen_edge_path


class FrozenTerrainCenterlineTests(unittest.TestCase):
    def fixture(self):
        z, x = np.mgrid[:21, :41]
        valley_z = 10 + 4*np.sin(np.pi*x/40)
        height = 100.-x+.8*(z-valley_z)**2
        plan = {"height_m": np.zeros((2, 2)), "receiver": np.array([[1,-1],[-1,-1]]),
                "river_mask": np.array([[True,False],[False,False]]), "owner_domain_id": np.zeros((2,2),int),
                "origin_xz_m": [0.,300.], "spacing_m": 1200., "identity_sha256": "fixed-plan"}
        return plan, height, np.zeros(height.shape,int)

    def test_whole_edge_anchor_route_and_arclength_clips_are_repeatable(self):
        plan, height, owner = self.fixture()
        args = (plan,[0,1],height,[0.,0.],30.,"fixed-source")
        path = prepare_frozen_edge_path(*args,owner_domain_id=owner,config=FrozenPathConfig(corridor_m=180.))
        again = prepare_frozen_edge_path(*args,owner_domain_id=owner,config=FrozenPathConfig(corridor_m=180.))
        self.assertEqual(path["identity"],again["identity"])
        points = path["arrays"]["points_xz_m"]
        np.testing.assert_array_equal(points[[0,-1]],[[0.,300.],[1200.,300.]])
        self.assertGreater(np.max(points[:,1]),300.)
        self.assertTrue(np.all(np.diff(path["arrays"]["arclength_m"])>0))
        first = clip_frozen_edge_path(path,0.,500.)
        second = clip_frozen_edge_path(path,500.,path["arrays"]["arclength_m"][-1])
        np.testing.assert_array_equal(first["points_xz_m"][-1],second["points_xz_m"][0])
        self.assertEqual(first["whole_path_identity"],second["whole_path_identity"])
        self.assertFalse(path["metadata"]["bed_certified"])
        from terrain_pipeline.channel_geometry import validate_frozen_path_nodes
        with self.assertRaisesRegex(ValueError, "shortcuts"):
            validate_frozen_path_nodes(path, plan, points[[0,-1]], [[0,1],[0,1]], [0.,1.], [1,-1])
        from terrain_pipeline.channel_geometry import frozen_window_profiles
        profiles = frozen_window_profiles(plan, height, [0.,0.], 30., frozen_paths=[path])
        self.assertEqual(profiles[0]["whole_path_identity"],path["identity"])
        clipped = frozen_window_profiles(plan, height, [0.,0.], 30., frozen_paths=[path],
                                         clip_origin_xz_m=[600.,0.], clip_shape=(21,21))
        self.assertAlmostEqual(clipped[0]["bed_m"][0],np.interp(clipped[0]["fractions"][0],profiles[0]["fractions"],profiles[0]["bed_m"]),places=3)

    def test_missing_whole_source_and_foreign_domain_barrier_rejected(self):
        plan, height, owner = self.fixture()
        with self.assertRaisesRegex(ValueError,"genuine source support"):
            prepare_frozen_edge_path(plan,[0,1],height[:,:30],[0.,0.],30.,"source",owner_domain_id=owner[:,:30])
        owner[:,20] = 1
        with self.assertRaisesRegex(ValueError,"no legal complete"):
            prepare_frozen_edge_path(plan,[0,1],height,[0.,0.],30.,"source",owner_domain_id=owner)


def test_direction_is_not_modified_and_search_repeats():
    from terrain_pipeline.channel_geometry import _terrain_weighted_path
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    height = np.zeros((8, 8))
    mesh = grid_mesh(height.shape, x0_m=0., z0_m=0., dx_m=1., world_seed=7)
    direction = np.array([3., 4.])
    args = (mesh, height, np.ones_like(height, dtype=bool), 0, [63])
    opts = dict(config=FrozenPathConfig(), initial_direction_xz=direction,
                direction_weight=4., direction_decay_m=5.)
    first = _terrain_weighted_path(*args, **opts)
    second = _terrain_weighted_path(*args, **opts)
    np.testing.assert_array_equal(direction, [3., 4.])
    np.testing.assert_array_equal(first, second)
