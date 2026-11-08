import unittest
from dataclasses import replace
import numpy as np

from terrain_pipeline.surface_rivers.branches import build_branches
from terrain_pipeline.surface_rivers.hydraulics import BranchHydraulics, ChannelHydraulics
from terrain_pipeline.surface_rivers.transport import TransportInput, route_sediment


class SurfaceRiverTransportTests(unittest.TestCase):
    def test_hydraulic_fraction_changes_with_side_depth(self):
        h = np.zeros((7, 11)); corridor = np.ones_like(h, dtype=bool)
        main = [(3, x) for x in range(1, 10)]
        for x in range(1, 10): h[3, x] = 20 - x
        for x in range(2, 9): h[2, x] = 19 - x
        kw = dict(width=2, roughness=.03, surface_slope=.01)
        shallow = BranchHydraulics(ChannelHydraulics(depth=2, **kw), ChannelHydraulics(depth=1, **kw))
        deep = BranchHydraulics(ChannelHydraulics(depth=2, **kw), ChannelHydraulics(depth=2, **kw))
        a = build_branches(h, main, corridor, 100, hydraulics=shallow)
        b = build_branches(h, main, corridor, 100, hydraulics=deep)
        self.assertLess(a.fractions[1], b.fractions[1])
        self.assertAlmostEqual(sum(a.discharges), 100)
        self.assertAlmostEqual(a.edge_discharges()[(main[-2], main[-1])], 100)
        if a.split != main[0]:
            self.assertAlmostEqual(a.edge_discharges()[(main[0], main[1])], 100)
        self.assertEqual(build_branches(h, main, corridor, 100).reason, "Hydraulics required")
        with self.assertRaises(ValueError):
            build_branches(h, main, corridor, 100,
                           hydraulics=BranchHydraulics(ChannelHydraulics(-1, 2, .03, .01), shallow.side))

    def test_transport_keeps_unresolved_inventory_and_exports_open_boundary(self):
        shape = (7, 9); height = np.zeros(shape); land = np.zeros(shape, bool); land[:2] = True
        ocean = ~land; depth = np.where(ocean, 1., 0.); direction = np.zeros(shape + (2,)); direction[..., 0] = 1
        speed = np.where(ocean, 1., 0.); boundary = np.zeros(shape, bool); boundary[-1, :] = True
        data = TransportInput(height, land, ocean, depth, direction, speed, boundary,
                              ((0, 4), (1, 4), (2, 4)), 10., 0., max_steps=1)
        result = route_sediment(data)
        self.assertAlmostEqual(result.deposited_solid + result.exported_solid + result.mobile_solid.sum(), 10.)
        self.assertEqual(result.exported_solid, 0.)
        later = route_sediment(replace(data, max_steps=8))
        self.assertGreater(later.exported_solid, 0.)
        self.assertAlmostEqual(later.deposited_solid + later.exported_solid + later.mobile_solid.sum(), 10.)
        # A continuous graph reach enters the first coastal cell, not its far endpoint.
        longer = route_sediment(replace(data, main_path=((0, 4), (5, 4)), max_steps=0))
        self.assertEqual(longer.mouth, (2, 4))
        self.assertEqual(longer.mobile_solid[2, 4], 10.)

    def test_disconnected_ocean_does_not_receive_sediment(self):
        shape = (5, 5); land = np.ones(shape, bool); land[2, 2] = False
        ocean = np.zeros(shape, bool); ocean[2, 2] = True; depth = ocean.astype(float)
        direction = np.zeros(shape + (2,)); speed = depth.copy(); boundary = np.zeros(shape, bool)
        data = TransportInput(np.zeros(shape), land, ocean, depth, direction, speed, boundary,
                              ((1, 2), (2, 2)), 3., 1.)
        result = route_sediment(data)
        self.assertEqual(result.mouth, (2, 2)); self.assertEqual(float(result.mobile_solid.sum()) + result.deposited_solid, 3.)
        self.assertEqual(float(result.height_delta.sum()), result.height_delta[2, 2])

    def test_no_mouth_rejected_and_zero_speed_keeps_inventory(self):
        shape = (5, 5); land = np.zeros(shape, bool); land[:2] = True
        ocean = ~land; depth = ocean.astype(float); direction = np.zeros(shape + (2,)); direction[..., 0] = 1
        boundary = np.zeros(shape, bool)
        data = TransportInput(np.zeros(shape), land, ocean, depth, direction,
                              np.zeros(shape), boundary, ((1, 2), (2, 2)), 3., 0., max_steps=3)
        result = route_sediment(data)
        self.assertEqual(result.mobile_solid[2, 2], 3.)
        with self.assertRaisesRegex(ValueError, "No wet"):
            route_sediment(replace(data, main_path=((0, 2), (1, 2))))

    def test_settling_cap_and_spacing_porosity_budget(self):
        shape = (5, 5); land = np.zeros(shape, bool); land[:2] = True
        ocean = ~land; depth = ocean.astype(float); direction = np.zeros(shape + (2,))
        speed = ocean.astype(float); boundary = np.zeros(shape, bool)
        data = TransportInput(np.zeros(shape), land, ocean, depth, direction, speed,
                              boundary, ((1, 2), (2, 2)), 10., 100., porosity=.25,
                              spacing_blocks=2., max_steps=1)
        result = route_sediment(data)
        self.assertAlmostEqual(result.height_delta[2, 2], .25)
        self.assertAlmostEqual(result.deposited_solid, .25 * 4 * .75)
        self.assertAlmostEqual(result.deposited_solid + result.mobile_solid.sum(), 10.)


if __name__ == '__main__':
    unittest.main()
