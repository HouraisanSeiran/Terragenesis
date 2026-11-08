"""Caller terminal selection preserves the complete candidate census and default ranking."""
import copy
import unittest
import numpy as np

from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from terrain_pipeline.surface_rivers.native_30m_reach_selection import select_from_topology
from tools.native_30m_selection_contract import selection_arguments, effective_rule, parameters_from_rule_file, selection_rule
from tools.native_30m_sources import compute_source_request, validate_request


class RequestedSelectionTests(unittest.TestCase):
    def setUp(self):
        self.field = np.zeros((9, 15), np.float64)
        self.field[4, 4] = -1.
        self.field[4, 10] = -1.
        self.top = build_strict_topology(self.field, np.ones(self.field.shape, bool), origin_native_xz=(-10, 7))
        self.kwargs = {'origin_native_xz': [-10, 7], 'min_stem_m': 1.,
                       'min_catchment_cells': 2, 'contact_margin_cells': 1}

    def test_explicit_other_terminal_keeps_all_candidates(self):
        automatic = select_from_topology(self.field, self.top, **self.kwargs)
        requested = select_from_topology(self.field, self.top, **self.kwargs, terminal_native_xz=[0, 11])
        self.assertEqual(automatic['chosen']['terminal_flat_cell'], 64)
        self.assertEqual(requested['chosen']['terminal_flat_cell'], 70)
        self.assertEqual(automatic['candidates'], requested['candidates'])
        self.assertTrue(any(item['terminal'] == 64 and item['accepted'] for item in requested['candidates']))

    def test_invalid_outside_nonterminal_or_rejected_terminal_refused(self):
        for point, reason in (([True, 11], 'must_be_int_pair'), ([999, 11], 'outside_window'),
                              ([-5, 11], 'not_candidate'), ([-10, 7], 'requested_terminal_rejected')):
            with self.subTest(point=point), self.assertRaisesRegex(ValueError, reason):
                select_from_topology(self.field, self.top, **self.kwargs, terminal_native_xz=point)

    def test_configuration_has_versioned_source_identity_and_rule(self):
        params = {'origin_native_xz': [-10, 7], 'shape_zx': [9, 15], 'terminal_native_xz': [0, 11],
                  'selection_parameters': {'min_stem_m': 1., 'min_catchment_cells': 2, 'contact_margin_cells': 1}}
        request = compute_source_request([{'path': 'x.npz', 'sha256': 'a'*64}], params)
        self.assertEqual(request['schema'], 'native-30m-source-request-v4')
        validate_request(request)
        rule = effective_rule(request['parameters'])
        self.assertEqual(rule['selection_mode'], 'caller_terminal_after_full_candidate_census')
        self.assertEqual(rule['requested_terminal_native_xz'], [0, 11])
        self.assertEqual(rule['parameters']['min_catchment_cells'], 2)

    def test_rule_fields_are_used_or_explicitly_refused(self):
        self.assertEqual(parameters_from_rule_file({'min_stem_m': 1.}), {'min_stem_m': 1.})
        full = selection_rule()
        full['parameters']['min_stem_m'] = 1.
        self.assertEqual(parameters_from_rule_file(full)['min_stem_m'], 1.)
        full['ordering'] = 'pick a prettier river'
        with self.assertRaisesRegex(ValueError, 'unsupported_selection_rule_semantics'):
            parameters_from_rule_file(full)
        for values in ({'unknown': 1}, {'max_nodes': False}, {'min_stem_m': -1.}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                selection_arguments({'selection_parameters': values})


if __name__ == '__main__':
    unittest.main()
