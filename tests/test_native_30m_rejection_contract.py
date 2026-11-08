"""Failure-injection gates for unit HRU allocation and prohibited coarse computation."""
import io
from contextlib import redirect_stdout, redirect_stderr
import unittest
from unittest.mock import patch
import numpy as np

import terrain_pipeline.runoff as runoff
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from tools import publish_native_30m_bundle as publisher
from tests.test_native_30m_runoff import run


class RejectionContractTests(unittest.TestCase):
    def test_wrong_hru_area_rejected_not_rescaled(self):
        real_route = runoff.route_local_discharge
        def wrong_area(*args, **kwargs):
            result = dict(real_route(*args, **kwargs))
            result['area_m2'] = result['area_m2'] * 2.
            return result
        with patch.object(runoff, 'route_local_discharge', side_effect=wrong_area):
            with self.assertRaisesRegex(ValueError, 'hru_fraction_not_unit'):
                run()

    def test_routing_mapping_change_cannot_pass_accounting(self):
        real_route = runoff.route_local_discharge
        def changed_mapping(*args, **kwargs):
            result = dict(real_route(*args, **kwargs))
            result['reach_length_m'] = result['reach_length_m'] + 1.
            return result
        with patch.object(runoff, 'route_local_discharge', side_effect=changed_mapping):
            with self.assertRaisesRegex(ValueError, 'route_mapping_rejected'):
                run()

    def test_private_d8_reuse_calls_no_coarse_planning(self):
        from terrain_pipeline.surface_rivers import metric_domain_closure as closure
        field = (np.indices((9, 9))[0] + np.indices((9, 9))[1]).astype(np.float64)
        with patch.object(closure, 'PlanningConfig', side_effect=AssertionError('coarse configuration used')), \
             patch.object(closure, 'coarse_condition_field', side_effect=AssertionError('coarse field used')):
            result = build_strict_topology(field, np.ones((9, 9), bool))
        self.assertGreater(np.count_nonzero(result['receiver'] >= 0), 60)

    def test_unimplemented_stage_has_stable_reason(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), \
             patch.object(publisher, '_compute_candidate_in_worker') as worker:
            self.assertEqual(publisher.main(['--mode', 'publish', '--output-dir', 'unused-rejection-output',
                                            '--stages', 'lake']), 2)
            worker.assert_not_called()
        self.assertIn('stage_not_implemented', out.getvalue())

    def test_window_dimension_then_cell_budget_reason_order(self):
        base = ['--mode', 'publish', '--output-dir', 'unused-rejection-output',
                '--td-page', 'x.npz', '--page-sha256', 'x.npz='+'a'*64, '--window-nodes', '2049']
        for extra, reason in (([], 'budget_window_dimension'),
                              (['--max-window-nodes', '2049', '--max-window-cells', '1000'], 'budget_window_cells')):
            with self.subTest(extra=extra):
                err = io.StringIO()
                with redirect_stderr(err), patch.object(publisher, '_compute_candidate_in_worker') as worker:
                    self.assertEqual(publisher.main(base + extra), 2)
                    worker.assert_not_called()
                self.assertIn(reason, err.getvalue())


if __name__ == '__main__':
    unittest.main()
