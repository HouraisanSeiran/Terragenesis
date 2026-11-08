import copy
import unittest
from unittest.mock import patch
import numpy as np

from tools.native_30m_selection_contract import selection_rule, verify_saved_selection


class SelectionContractTests(unittest.TestCase):
    def fixture(self):
        mask = np.zeros((3, 3), bool)
        mask[1, 1] = True
        chosen = {'catchment_mask': mask.copy(), 'flowline_mask': mask.copy(),
                  'stem_flat_cells': np.array([4], np.int64), 'terminal_flat_cell': 4, 'catchment_cells': 1}
        candidates = [{'terminal': 4, 'count': 1, 'accepted': True, 'reason': None}]
        env = {'arrays': {'source.npz': {'field': np.zeros((3, 3))}, 'topology.npz': {},
                          'selection.npz': {k: chosen[k].copy() for k in
                                            ('catchment_mask', 'flowline_mask', 'stem_flat_cells')}},
               'manifest': {'parameters': {'origin_native_xz': [0, 0]}},
               'json_records': {'selection.json': {'candidates': copy.deepcopy(candidates),
                   'chosen': {'terminal_flat_cell': 4, 'catchment_cells': 1}}}}
        return env, {'chosen': chosen, 'candidates': candidates}

    def test_actual_rule_defaults_not_guessed(self):
        rule = selection_rule()
        self.assertEqual(rule['parameters']['contact_margin_cells'], 6)
        self.assertEqual(rule['parameters']['max_catchment_cells'], 13000)
        self.assertIn('largest catchment', rule['ordering'])

    def test_candidate_table_and_masks_recomputed(self):
        env, fresh = self.fixture()
        with patch('terrain_pipeline.surface_rivers.native_30m_reach_selection.select_from_topology', return_value=fresh), \
             patch('tools.native_30m_selection_contract.selection_rule', return_value={'test': 'rule'}):
            report = verify_saved_selection(env)
        self.assertTrue(report['selection_recomputed'])
        self.assertEqual(report['accepted_count'], 1)

    def test_resealed_candidates_masks_or_scalar_cannot_pass(self):
        for kind in ('candidates', 'mask', 'scalar'):
            with self.subTest(kind=kind):
                env, fresh = self.fixture()
                if kind == 'candidates':
                    env['json_records']['selection.json']['candidates'][0]['accepted'] = False
                elif kind == 'mask':
                    env['arrays']['selection.npz']['catchment_mask'][1, 1] = False
                else:
                    env['json_records']['selection.json']['chosen']['terminal_flat_cell'] = 3
                with patch('terrain_pipeline.surface_rivers.native_30m_reach_selection.select_from_topology', return_value=fresh):
                    with self.assertRaisesRegex(ValueError, 'selection_'):
                        verify_saved_selection(env)


if __name__ == '__main__':
    unittest.main()
