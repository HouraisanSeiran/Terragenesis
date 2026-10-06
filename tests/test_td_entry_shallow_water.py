import unittest

import numpy as np

from terrain_pipeline.td_entry_shallow_water import (
    build_forcing, build_geometry, compare_levels, finish, run_case, source_samples)


class EntryShallowWaterTests(unittest.TestCase):
    def test_native_source_provenance_wet_and_protected_refusal(self):
        height = np.arange(16, dtype=float).reshape(4, 4)
        hierarchy = dict(metadata=dict(origin_m_xz=[0., 0.], spacing_m=1.), arrays=dict(
            height_m=height, cell_owner=np.zeros((4, 4), int), contribution_owner=np.zeros((4, 4), int),
            node_unknown_contact=np.zeros(1, bool), valid_mask=np.ones((4, 4), bool),
            protected_mask=np.zeros((4, 4), bool), open_boundary_mask=np.zeros((4, 4), bool)))
        protection = dict(covered_native_cell_ids=[5], stage_by_leaf=[dict(leaf_id=0, stage_m=6.)])
        result = source_samples(hierarchy, [0], protection, np.array([[.75, .75], [2.5, 2.5]]))
        self.assertEqual(result['source_bed_m'].tolist(), [3.75, 12.5])
        self.assertEqual(result['wet_protected_mask'].tolist(), [True, False])
        self.assertEqual(result['native_corner_cell'][0].tolist(), [0, 1, 4, 5])
        hierarchy['arrays']['protected_mask'][0, 0] = True
        with self.assertRaisesRegex(ValueError, 'protected'):
            source_samples(hierarchy, [0], protection, np.array([[.75, .75]]))

    def test_existing_solver_short_signed_packets_and_real_maxdt_change(self):
        height = np.zeros((3, 8), float)
        forcing_mask = np.zeros_like(height, bool)
        forcing_mask[1, 0] = True
        carrier = finish(dict(derived_bed_m=height, forcing_mask=forcing_mask), dict(
            direction_xz=[1., 0.], local_center_origin_m_xz=[0., 0.],
            ordinary_q_m3_s=.0001, ordinary_lake_stage_m=0.))
        geometry = build_geometry(carrier)
        forcing = build_forcing(carrier, geometry, duration_s=.2, interval_s=.1)
        coarse, coarse_packets, coarse_rk = run_case(carrier, geometry, forcing, case_index=0, max_dt_s=.01)
        fine, fine_packets, fine_rk = run_case(carrier, geometry, forcing, case_index=0, max_dt_s=.005)
        self.assertGreater(fine['metadata']['substeps'], coarse['metadata']['substeps'])
        self.assertTrue(compare_levels(coarse, fine, coarse_packets, fine_packets)['maxdt_constraint_effective'])
        self.assertLess(abs(fine['arrays']['ledger'][-1, -1]), 1e-12)
        self.assertEqual(len(fine_rk['arrays']['dt_s']), 2)
        area = .175**2
        left, right, boundary = (geometry['arrays'][name] for name in ('face_left', 'face_right', 'boundary_cell'))
        for interval in range(2):
            packet = {key: value[interval] for key, value in fine_packets['arrays'].items()}
            net = np.bincount(right, weights=packet['internal_transfer_m3'], minlength=height.size)
            net -= np.bincount(left, weights=packet['internal_transfer_m3'], minlength=height.size)
            net -= np.bincount(boundary, weights=packet['boundary_transfer_m3'], minlength=height.size)
            np.testing.assert_allclose(area*(packet['depth_after_m']-packet['depth_before_m']), net+packet['forcing_volume_m3'], atol=1e-14)
        self.assertFalse(fine['metadata']['gross_boundary_per_face_certified'])


if __name__ == '__main__':
    unittest.main()
