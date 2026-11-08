import unittest
import numpy as np
from terrain_pipeline.channel_geometry import select_saved_reach
from terrain_pipeline.channel_geometry import section_from_routed_budget

class RoutedWidthTest(unittest.TestCase):
    def test_committed_exchange_changes_width_without_second_debit(self):
        kw = dict(incoming_solid_m3=10., external_solid_m3=2., capacity_solid_m3=30.,
                  eroded_loose_solid_m3=3., eroded_rock_m3=1., deposited_solid_m3=1.)
        section = section_from_routed_budget(5., .5, .5, 0., .2, **kw)
        self.assertGreater(section.width_m, section.baseline_width_m)
        self.assertEqual(section.eroded_solid_m3, 4.)
        self.assertEqual(section.deposited_solid_m3, 1.)
        kw['deposited_solid_m3'] = 8.
        self.assertLess(section_from_routed_budget(5., .5, .5, 0., .2, **kw).width_m, section.baseline_width_m)
        kw['incoming_solid_m3'] = np.nan
        with self.assertRaises(ValueError):
            section_from_routed_budget(5., .5, .5, 0., .2, **kw)

    def test_reach_selection_follows_only_bounded_downhill_edges(self):
        edges = np.array([[0,1],[1,2],[2,3],[4,5]])
        status = np.array([0,0,1,0])
        bed = np.array([5.,4.,3.,2.,5.,4.])
        q = np.array([1.,1.5,2.,3.,10.,10.])
        np.testing.assert_array_equal(select_saved_reach(edges,status,bed,q,minimum_nodes=3),[0,1,2])

    def test_saved_reach_uses_committed_ledger_and_storage(self):
        from pathlib import Path
        from terrain_pipeline.channel_geometry import construct_saved_width_reach
        root = Path('.scratch/river-upgrade-20261101')
        if not (root / 'native-network-v4/manifest.json').exists():
            self.skipTest('saved native source unavailable')
        result = construct_saved_width_reach(root)
        a = result['arrays']
        self.assertGreaterEqual(len(a['receiver']), 60)
        np.testing.assert_array_equal(a['receiver'][:-1], np.arange(1, len(a['receiver'])))
        self.assertEqual(a['receiver'][-1], -1)
        np.testing.assert_allclose(a['bed_m'], a['sediment_trace_bed_m'][-1])
        np.testing.assert_allclose(a['storage_m3'], a['length_m'] * a['width_m'] * a['water_depth_m'])
        self.assertAlmostEqual(a['water_inflow_m3_s'].sum(), a['formative_q_m3_s'][-1])
        self.assertAlmostEqual(result['metadata']['sediment_metadata']['global_residual'], 0., places=8)
        self.assertGreater(a['sediment_eroded_loose_solid_m3'].sum(), 0.)
        self.assertGreater(a['sediment_exported_solid_m3'].sum(), 0.)
