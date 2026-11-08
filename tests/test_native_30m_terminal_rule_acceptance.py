"""Helpers of the explicit terminal + actual-rule acceptance harness (no heavy compute).

The harness lives in ``.scratch/river-stage1-completion/run_terminal_rule_acceptance.py`` and is
loaded by path. These tests pin the pure parts that decide pass/fail: the rule file must be the
live actual-rule document, the argv builders must pass the explicit flags, array comparison must
be bitwise (not a tolerance), targets must never be overwritten, and a saved source request must
be schema v4 carrying the requested terminal and rule parameters. They never run a publish,
never read a saved release and never write into the workspace.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / '.scratch' / 'river-stage1-completion' / 'run_terminal_rule_acceptance.py'
SPEC = importlib.util.spec_from_file_location('terminal_rule_acceptance_under_test', HARNESS)
HARNESS_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS_MODULE)

SWITCH = ROOT / '.scratch' / 'river-stage1-completion' / 'run_terminal_switch_acceptance.py'
SWITCH_SPEC = importlib.util.spec_from_file_location('terminal_switch_acceptance_under_test', SWITCH)
SWITCH_MODULE = importlib.util.module_from_spec(SWITCH_SPEC)
SWITCH_SPEC.loader.exec_module(SWITCH_MODULE)

import numpy as np  # noqa: E402

from tools.native_30m_selection_contract import selection_rule, parameters_from_rule_file  # noqa: E402
from tools.native_30m_sources import compute_source_request  # noqa: E402

TERMINAL = HARNESS_MODULE.REQUESTED_TERMINAL_NATIVE_XZ


def fixture_request():
    params = {'origin_native_xz': [42173, 42874], 'shape_zx': [1337, 1337],
              'coupled_intervals': 12, 'resample_stride': 3,
              'terminal_native_xz': list(TERMINAL),
              'selection_parameters': parameters_from_rule_file(selection_rule())}
    request = compute_source_request([{'path': 'x.npz', 'sha256': 'a' * 64}], params)
    request['source_kind'] = 'saved_assembly'
    return request


def fake_env(arrays, stage_arrays=None):
    env = {'arrays': dict(arrays)}
    for stage, values in (stage_arrays or {}).items():
        env[stage] = {'arrays': dict(values)}
    return env


class RuleFileTests(unittest.TestCase):
    def test_written_rule_file_is_the_live_actual_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rule.json'
            record = HARNESS_MODULE.write_rule_file(path)
            document = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(document, selection_rule())
            self.assertEqual(record['schema'], 'native-30m-actual-reach-rule-v1')
            self.assertEqual(record['parameters'], selection_rule()['parameters'])
            self.assertEqual(record['parameters_roundtrip'], record['parameters'])
            self.assertEqual(len(record['sha256']), 64)

    def test_written_rule_file_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rule.json'
            HARNESS_MODULE.write_rule_file(path)
            with self.assertRaisesRegex(FileExistsError, 'rule_file_exists'):
                HARNESS_MODULE.write_rule_file(path)


class ArgvTests(unittest.TestCase):
    def test_publish_argv_passes_explicit_terminal_and_rule_file(self):
        argv = HARNESS_MODULE.publish_argv('r.json', 'out-dir')
        self.assertIn('--terminal-native-xz', argv)
        self.assertIn('--reach-rule-file', argv)
        self.assertIn('--assembly', argv)
        self.assertIn('--assembly-sha256', argv)
        self.assertEqual(argv[argv.index('--terminal-native-xz') + 1:argv.index('--terminal-native-xz') + 3],
                         [str(TERMINAL[0]), str(TERMINAL[1])])
        self.assertEqual(argv[argv.index('--reach-rule-file') + 1], 'r.json')
        self.assertEqual(argv[argv.index('--output-dir') + 1], 'out-dir')
        self.assertEqual(argv[argv.index('--mode') + 1], 'publish')

    def test_rebuild_and_verify_argv_pass_external_pins(self):
        rebuild = HARNESS_MODULE.source_rebuild_argv('src.json', 'b' * 64, 'rebuilt')
        self.assertEqual(rebuild[rebuild.index('--mode') + 1], 'source-rebuild')
        self.assertEqual(rebuild[rebuild.index('--source-request-sha256') + 1], 'b' * 64)
        verify = HARNESS_MODULE.verify_argv('release', 'report.json', 'c' * 64)
        self.assertEqual(verify[verify.index('--identity') + 1], 'c' * 64)
        self.assertEqual(verify[verify.index('--point-native') + 1:verify.index('--point-native') + 3],
                         [str(TERMINAL[0]), str(TERMINAL[1])])


class PreflightTests(unittest.TestCase):
    def test_preflight_refuses_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            present = Path(tmp) / 'present'
            present.write_text('x', encoding='utf-8')
            with self.assertRaisesRegex(FileExistsError, 'target_exists:present'):
                HARNESS_MODULE.preflight({'present': present, 'absent': Path(tmp) / 'absent'})

    def test_preflight_passes_when_all_targets_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = HARNESS_MODULE.preflight({'a': Path(tmp) / 'a', 'b': Path(tmp) / 'b'})
            self.assertTrue(record['all_absent'])


class ArrayComparisonTests(unittest.TestCase):
    def test_exact_equal_requires_dtype_shape_and_bytes(self):
        base = np.arange(6, dtype=np.float64).reshape(2, 3)
        self.assertTrue(HARNESS_MODULE.exact_equal(base, base.copy()))
        self.assertFalse(HARNESS_MODULE.exact_equal(base, base.astype(np.float32)))
        self.assertFalse(HARNESS_MODULE.exact_equal(base, base.reshape(3, 2)))
        self.assertFalse(HARNESS_MODULE.exact_equal(base, base + np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1e-12]).reshape(2, 3)))

    def test_compare_arrays_reports_bitwise_mismatch_not_tolerance(self):
        baseline = fake_env({'source.npz': {'field': np.zeros(4, np.float64)}})
        tiny = np.zeros(4, np.float64)
        tiny[0] = 1e-15
        new = fake_env({'source.npz': {'field': tiny}})
        report = HARNESS_MODULE.compare_arrays(baseline, new)
        self.assertEqual(report['mismatched_names'], ['data/source.npz:field'])
        self.assertFalse(report['all_identical'])
        self.assertEqual(report['compared_count'], 1)

    def test_compare_arrays_accepts_identical_and_covers_stage_arrays(self):
        values = {'field': np.zeros(4, np.float64)}
        baseline = fake_env({'source.npz': dict(values)}, {'dynamics': {'node_bed_m': np.ones(3)}})
        new = fake_env({'source.npz': dict(values)}, {'dynamics': {'node_bed_m': np.ones(3)}})
        report = HARNESS_MODULE.compare_arrays(baseline, new)
        self.assertTrue(report['all_identical'])
        self.assertEqual(report['mismatched_names'], [])
        self.assertEqual(report['compared_names'], ['data/source.npz:field', 'dynamics:node_bed_m'])

    def test_compare_arrays_notes_missing_and_extra_fields(self):
        baseline = fake_env({'source.npz': {'field': np.zeros(2), 'gone': np.zeros(2)}})
        new = fake_env({'source.npz': {'field': np.zeros(2), 'added': np.zeros(2)}})
        report = HARNESS_MODULE.compare_arrays(baseline, new)
        self.assertEqual(report['missing_in_new'], ['data/source.npz:gone'])
        self.assertEqual(report['extra_in_new'], ['data/source.npz:added'])
        self.assertFalse(report['all_identical'])


class SourceRequestCheckTests(unittest.TestCase):
    def test_fixture_request_is_v4_and_passes_the_check(self):
        request = fixture_request()
        self.assertEqual(request['schema'], 'native-30m-source-request-v4')
        report = HARNESS_MODULE.check_source_request(request, expected_terminal=TERMINAL,
            expected_parameters=parameters_from_rule_file(selection_rule()), expected_identity=None)
        self.assertEqual(report['selection_mode'], 'caller_terminal_after_full_candidate_census')
        self.assertEqual(report['terminal_native_xz'], list(TERMINAL))
        self.assertEqual(report['selection_parameters'], parameters_from_rule_file(selection_rule()))

    def test_check_rejects_wrong_terminal_kind_schema_and_parameters(self):
        request = fixture_request()
        with self.assertRaisesRegex(ValueError, 'source_request_terminal'):
            HARNESS_MODULE.check_source_request(request, expected_terminal=[0, 0],
                expected_parameters=parameters_from_rule_file(selection_rule()), expected_identity=None)
        with self.assertRaisesRegex(ValueError, 'source_request_selection_parameters'):
            HARNESS_MODULE.check_source_request(request, expected_terminal=TERMINAL,
                expected_parameters={'min_stem_m': 1.0}, expected_identity=None)
        moved = json.loads(json.dumps(request))
        moved['source_kind'] = 'td_pages'
        with self.assertRaisesRegex(ValueError, 'source_request_kind'):
            HARNESS_MODULE.check_source_request(moved, expected_terminal=TERMINAL,
                expected_parameters=parameters_from_rule_file(selection_rule()), expected_identity=None)
        old = json.loads(json.dumps(request))
        old['schema'] = 'native-30m-source-request-v2'
        with self.assertRaisesRegex(ValueError, 'source_request_schema'):
            HARNESS_MODULE.check_source_request(old, expected_terminal=TERMINAL,
                expected_parameters=parameters_from_rule_file(selection_rule()), expected_identity=None)

    def test_check_rejects_expected_identity_mismatch(self):
        request = fixture_request()
        with self.assertRaisesRegex(ValueError, 'source_request_expected_identity'):
            HARNESS_MODULE.check_source_request(request, expected_terminal=TERMINAL,
                expected_parameters=parameters_from_rule_file(selection_rule()), expected_identity='d' * 64)


class ReleaseIdentityTests(unittest.TestCase):
    def test_release_identity_read_from_release_json(self):
        self.assertEqual(HARNESS_MODULE.release_identity_of({'identity_sha256': 'a' * 64}), 'a' * 64)
        for bad in ({}, {'identity_sha256': 'short'}, {'identity_sha256': None}, None):
            with self.subTest(value=bad), self.assertRaisesRegex(ValueError, 'release_identity_unreadable'):
                HARNESS_MODULE.release_identity_of(bad)

    def test_resolve_release_identity_falls_back_to_strict_report(self):
        direct = {'results': {'release_identity': 'b' * 64}}
        self.assertEqual(HARNESS_MODULE.resolve_release_identity(direct), 'b' * 64)
        fallback = {'results': {'release_identity': None,
                                'strict_verification': {'release_identity_sha256': 'c' * 64}}}
        self.assertEqual(HARNESS_MODULE.resolve_release_identity(fallback), 'c' * 64)
        self.assertIsNone(HARNESS_MODULE.resolve_release_identity({'results': {}}))

    def test_summary_renders_the_release_identity_without_a_hole(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = {
                'boundaries': HARNESS_MODULE.BOUNDARIES,
                'inputs': {'rule_file': {'path': 'rule.json', 'sha256': 'd' * 64}},
                'steps': {'publish': {'argv': ['python', 'cli.py'], 'exit': 0, 'elapsed_seconds': 1.0}},
                'comparison': {'method': 'tobytes', 'compared_count': 1, 'baseline_array_count': 1,
                               'new_array_count': 1, 'mismatched_names': []},
                'results': {'release_numerical_identity': 'e' * 64, 'release_identity': 'f' * 64,
                            'source_request_sha256': '1' * 64, 'rebuilt_numerical_identity': 'e' * 64},
                'evidence_path': str(Path(tmp) / 'e.json'), 'summary_path': str(Path(tmp) / 's.md'),
            }
            HARNESS_MODULE.write_summary(evidence)
            text = (Path(tmp) / 's.md').read_text(encoding='utf-8')
            self.assertIn('新发布身份：`' + 'f' * 64 + '`', text)
            self.assertNotIn('新发布身份：`None`', text)
            self.assertIn('caller path', text)


class EngineeringGateTests(unittest.TestCase):
    def test_identity_hex_refuses_none_and_malformed(self):
        self.assertEqual(HARNESS_MODULE.require_identity_hex('a' * 64, 'x'), 'a' * 64)
        for bad in (None, '', 'a' * 63, 'a' * 65, 'g' * 64, 123):
            with self.subTest(value=bad), self.assertRaisesRegex(ValueError, 'numerical_identity_invalid:x'):
                HARNESS_MODULE.require_identity_hex(bad, 'x')

    def test_identity_hex_closes_the_none_equals_none_hole(self):
        # Reproduces the defect the gate exists to stop: two absences must not 'match'.
        self.assertRaisesRegex(ValueError, 'numerical_identity_invalid',
                               HARNESS_MODULE.require_identity_hex, None, 'source_rebuild')

    def test_baseline_gate_refuses_false_or_missing(self):
        ok = {'baseline': {'identity_matches_declared': True, 'numerical_identity_sha256': 'b' * 64}}
        self.assertEqual(HARNESS_MODULE.require_baseline_identity(ok), 'b' * 64)
        for bad in ({'baseline': {'identity_matches_declared': False, 'numerical_identity_sha256': 'b' * 64}},
                    {'baseline': {'numerical_identity_sha256': 'b' * 64}}, {}):
            with self.subTest(value=bad), self.assertRaisesRegex(ValueError, 'baseline_identity_mismatch'):
                HARNESS_MODULE.require_baseline_identity(bad)

    def test_different_terminal_requires_stage_change(self):
        changed = {'stage_identities_identical': False}
        record = HARNESS_MODULE.verify_switch_claim(changed, terminal_relation='different')
        self.assertEqual(record['verdict'], 'changed_as_required')
        self.assertTrue(record['identity_change_is_not_physics_proof'])
        for identical in ({'stage_identities_identical': True}, {}, {'stage_identities_identical': None}):
            with self.subTest(value=identical), self.assertRaisesRegex(
                    ValueError, 'switch_claim_refused_stage_identities_identical'):
                HARNESS_MODULE.verify_switch_claim(identical, terminal_relation='different')

    def test_same_terminal_requires_stage_reproduction(self):
        # Main agent point 3: a same-terminal run whose stages CHANGED must also be refused.
        identical = {'stage_identities_identical': True}
        record = HARNESS_MODULE.verify_switch_claim(identical, terminal_relation='same')
        self.assertEqual(record['verdict'], 'reproduced_as_required')
        for changed in ({'stage_identities_identical': False}, {}, {'stage_identities_identical': None}):
            with self.subTest(value=changed), self.assertRaisesRegex(
                    ValueError, 'hold_claim_refused_stage_identities_changed'):
                HARNESS_MODULE.verify_switch_claim(changed, terminal_relation='same')

    def test_unspecified_relation_records_without_asserting(self):
        for identical in (True, False, None):
            record = HARNESS_MODULE.verify_switch_claim({'stage_identities_identical': identical},
                                                        terminal_relation='unspecified')
            self.assertEqual(record['verdict'], 'unasserted')
        with self.assertRaisesRegex(ValueError, 'terminal_relation_invalid'):
            HARNESS_MODULE.verify_switch_claim({}, terminal_relation='maybe')


class CensusTests(unittest.TestCase):
    def make_release(self, root, *, origin=(1000, 2000), width=10, candidates=None, chosen_flat=0):
        release = root / 'release'
        (release / 'data').mkdir(parents=True)
        (release / 'source-request.json').write_text(json.dumps(
            {'parameters': {'origin_native_xz': list(origin), 'shape_zx': [width, width]}}),
            encoding='utf-8')
        (release / 'data' / 'selection.json').write_text(json.dumps(
            {'candidates': candidates or [], 'chosen': {'terminal_flat_cell': chosen_flat}}),
            encoding='utf-8')
        return release

    def test_census_counts_accepted_and_ranks_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = [
                {'terminal': 0, 'count': 5, 'accepted': False, 'reason': 'small_or_budget'},
                {'terminal': 12, 'count': 500, 'accepted': True, 'reason': None},
                {'terminal': 3, 'count': 900, 'accepted': True, 'reason': None},
            ]
            release = self.make_release(Path(tmp), candidates=candidates, chosen_flat=3)
            record = HARNESS_MODULE.census_of_release(release)
            self.assertEqual(record['candidate_count'], 3)
            self.assertEqual(record['accepted_count'], 2)
            self.assertEqual(record['eligibility_fields_saved'], ['accepted', 'count', 'reason', 'terminal'])
            self.assertTrue(record['requested_is_default_ranked'])  # flat 3 has the largest count
            self.assertEqual(record['requested_rank_among_accepted'], 0)
            # distinct accepted terminals is the honest count behind accepted_count
            self.assertEqual(record['distinct_accepted_terminals'], 2)

    def test_census_reports_next_legal_terminal_native_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = [
                {'terminal': 0, 'count': 900, 'accepted': True, 'reason': None},
                {'terminal': 23, 'count': 500, 'accepted': True, 'reason': None},
            ]
            release = self.make_release(Path(tmp), origin=(1000, 2000), width=10,
                                        candidates=candidates, chosen_flat=0)
            record = HARNESS_MODULE.census_of_release(release)
            self.assertEqual(record['requested_rank_among_accepted'], 0)
            self.assertEqual(record['next_legal_terminal']['terminal_flat_cell'], 23)
            self.assertEqual(record['next_legal_terminal']['native_xz'], [1003, 2002])
            self.assertIs(record['next_legal_terminal']['accepted'], True)
            self.assertIsNone(record['next_legal_terminal']['reason'])

    def test_census_only_refuses_to_overwrite_and_missing_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = self.make_release(Path(tmp), candidates=[{'terminal': 0, 'count': 1,
                                                                'accepted': True, 'reason': None}])
            out = Path(tmp) / 'census.json'
            self.assertEqual(HARNESS_MODULE.main(['--census-only', '--release', str(release),
                                                  '--census-out', str(out)]), 0)
            self.assertTrue(out.exists())
            with self.assertRaisesRegex(FileExistsError, 'census_out_exists'):
                HARNESS_MODULE.main(['--census-only', '--release', str(release), '--census-out', str(out)])
            with self.assertRaisesRegex(ValueError, 'census_out_required'):
                HARNESS_MODULE.main(['--census-only', '--release', str(release)])


class RenderOnlyTests(unittest.TestCase):
    def test_render_only_writes_summary_and_leaves_evidence_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / 'evidence.json'
            summary_path = Path(tmp) / 'summary.md'
            evidence = {'boundaries': HARNESS_MODULE.BOUNDARIES,
                        'inputs': {'rule_file': {'path': 'rule.json', 'sha256': 'd' * 64}},
                        'steps': {}, 'comparison': {}, 'results': {'passed': True}}
            original = (json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
            evidence_path.write_text(original, encoding='utf-8')
            before = evidence_path.read_bytes()
            rc = HARNESS_MODULE.main(['--render-only', '--evidence', str(evidence_path),
                                      '--summary', str(summary_path)])
            self.assertEqual(rc, 0)
            self.assertEqual(evidence_path.read_bytes(), before)  # read-only, never rewritten
            self.assertTrue(summary_path.exists())

    def test_render_only_refuses_existing_summary_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / 'summary.md'
            summary_path.write_text('existing', encoding='utf-8')
            with self.assertRaisesRegex(FileExistsError, 'summary_target_exists'):
                HARNESS_MODULE.main(['--render-only', '--evidence', str(Path(tmp) / 'absent.json'),
                                     '--summary', str(summary_path)])
            with self.assertRaises(FileNotFoundError):
                HARNESS_MODULE.main(['--render-only', '--evidence', str(Path(tmp) / 'absent.json'),
                                     '--summary', str(Path(tmp) / 'new-summary.md')])


class BoundaryTests(unittest.TestCase):
    def test_boundaries_state_the_caller_path_limitation(self):
        text = ' '.join(HARNESS_MODULE.BOUNDARIES)
        self.assertIn('caller path', text)
        self.assertIn('not stage-one completion', text)
        self.assertIn('default-ranked terminal', text)
        self.assertIn('219 distinct accepted terminals', text)
        self.assertIn('rebuild is verified by numerical-identity comparison only', text)


class SwitchComparisonTests(unittest.TestCase):
    """The switch harness must gate invariants + a real change, not reuse the v1 equal-arrays gate."""

    def make_env(self, *, terminal, node_ids, stage_geometry, source_field):
        origin = [42173, 42874]
        # terminal_flat_cell -> native xz via the real window width
        width = 1337
        fx, fz = terminal
        flat = (fz - origin[1]) * width + (fx - origin[0])
        return {
            'arrays': {
                'source.npz': {'field': source_field, 'resolved_mask': np.zeros(2, bool),
                               'origin_native_xz': np.array(origin, np.int64)},
                'topology.npz': {'receiver': np.zeros(4, np.int64), 'valid_mask': np.ones(4, bool),
                                 'terminal_kind': np.zeros(4, np.int8),
                                 'upstream_unknown_mask': np.zeros(4, bool)},
                'selection.npz': {'catchment_mask': np.full(4, flat, np.int64)},
                'section.npz': {'node_cell_ids': np.array(node_ids, np.int64)},
            },
            'json_records': {'selection.json': {
                'candidates': [{'terminal': 0, 'count': 1, 'accepted': True, 'reason': None}],
                'chosen': {'terminal_flat_cell': flat, 'terminal_native_xz': [fx, fz],
                           'catchment_cells': len(node_ids), 'stem_length_m': 100.0}}},
            'manifest': {'stage_identities': {'geometry': stage_geometry, 'dynamics': stage_geometry}},
        }

    def test_comparison_reports_invariants_change_and_census(self):
        old = self.make_env(terminal=(42409, 43277), node_ids=[10, 11], stage_geometry='a' * 64,
                            source_field=np.zeros(2, np.float64))
        new = self.make_env(terminal=(42617, 43119), node_ids=[20, 21, 22], stage_geometry='b' * 64,
                            source_field=np.zeros(2, np.float64))
        self.assertNotEqual(old['arrays']['selection.npz']['catchment_mask'].tolist(),
                            new['arrays']['selection.npz']['catchment_mask'].tolist())
        record = SWITCH_MODULE.switch_comparison(old, new)
        self.assertTrue(record['unchanged_required_all_identical'])  # source/topology identical
        self.assertTrue(record['candidate_census_identical'])
        self.assertTrue(record['chosen']['terminal_changed'])
        self.assertTrue(record['chosen']['chosen_matches_requested'])
        self.assertEqual(record['node_topology']['old_node_count'], 2)
        self.assertEqual(record['node_topology']['new_node_count'], 3)
        self.assertIn('data/selection.npz:catchment_mask', record['changing_arrays_that_changed'])
        self.assertEqual(record['stage_names_changed'], ['dynamics', 'geometry'])
        self.assertFalse(record['stage_identities_identical'])
        SWITCH_MODULE.gate_switch(record)  # a real switch passes

    def test_gate_refuses_unchanged_terminal(self):
        old = self.make_env(terminal=(42409, 43277), node_ids=[10], stage_geometry='a' * 64,
                            source_field=np.zeros(2, np.float64))
        same = self.make_env(terminal=(42409, 43277), node_ids=[10], stage_geometry='a' * 64,
                             source_field=np.zeros(2, np.float64))
        record = SWITCH_MODULE.switch_comparison(old, same)
        with self.assertRaisesRegex(RuntimeError, 'switch_terminal_unchanged'):
            SWITCH_MODULE.gate_switch(record)

    def test_gate_refuses_changed_source_or_census(self):
        old = self.make_env(terminal=(42409, 43277), node_ids=[10], stage_geometry='a' * 64,
                            source_field=np.zeros(2, np.float64))
        moved = self.make_env(terminal=(42617, 43119), node_ids=[10], stage_geometry='b' * 64,
                              source_field=np.ones(2, np.float64))
        record = SWITCH_MODULE.switch_comparison(old, moved)
        self.assertFalse(record['unchanged_required_all_identical'])
        with self.assertRaisesRegex(RuntimeError, 'switch_source_or_topology_changed'):
            SWITCH_MODULE.gate_switch(record)

        other = self.make_env(terminal=(42617, 43119), node_ids=[10], stage_geometry='b' * 64,
                              source_field=np.zeros(2, np.float64))
        other['json_records']['selection.json']['candidates'] = [
            {'terminal': 7, 'count': 9, 'accepted': True, 'reason': None}]
        record = SWITCH_MODULE.switch_comparison(old, other)
        with self.assertRaisesRegex(RuntimeError, 'switch_candidate_census_changed'):
            SWITCH_MODULE.gate_switch(record)

    def test_gate_refuses_chosen_not_matching_request(self):
        old = self.make_env(terminal=(42409, 43277), node_ids=[10], stage_geometry='a' * 64,
                            source_field=np.zeros(2, np.float64))
        wrong = self.make_env(terminal=(42617, 43119), node_ids=[10], stage_geometry='b' * 64,
                              source_field=np.zeros(2, np.float64))
        wrong['json_records']['selection.json']['chosen']['terminal_native_xz'] = [1, 2]
        record = SWITCH_MODULE.switch_comparison(old, wrong)
        with self.assertRaisesRegex(RuntimeError, 'switch_chosen_terminal_not_requested'):
            SWITCH_MODULE.gate_switch(record)

    def test_switch_harness_does_not_reuse_the_v1_equal_arrays_gate(self):
        # The v1 gate demanded ALL arrays equal; a switch must not be judged by that.
        source = SWITCH.read_text(encoding='utf-8')
        self.assertNotIn("comparison['all_identical']", source)
        self.assertIn('gate_switch', source)
        self.assertTrue(SWITCH_MODULE.BOUNDARIES)


class SwitchRuleFileTests(unittest.TestCase):
    def test_switch_resolves_rule_file_parameters_via_the_contract(self):
        # Regression: the switch harness once called TR.parameters_from_rule_file, which the v1
        # harness only imports locally, so the run died AFTER a full publish. The rule-file
        # parameters must come from the contract module directly.
        source = SWITCH.read_text(encoding='utf-8')
        self.assertNotIn('TR.parameters_from_rule_file', source)
        from tools.native_30m_selection_contract import parameters_from_rule_file
        rule_json = json.loads((ROOT / '.scratch' / 'river-stage1-completion'
                                / 'reach-rule-actual-20261025-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(parameters_from_rule_file(rule_json), rule_json['parameters'])


class SwitchArgvTests(unittest.TestCase):
    def test_publish_argv_uses_the_new_terminal(self):
        argv = SWITCH_MODULE.publish_argv('r.json', 'out', [42617, 43119])
        self.assertEqual(argv[argv.index('--terminal-native-xz') + 1:argv.index('--terminal-native-xz') + 3],
                         ['42617', '43119'])
        self.assertEqual(argv[argv.index('--assembly-sha256') + 1],
                         'd62bb9e5d6a0555e8af4030ce19fede58963f5cb5974c30a25336a03e3c0d162')

    def test_verify_argv_points_at_the_new_terminal(self):
        argv = SWITCH_MODULE.verify_argv('bundle', 'report.json', 'a' * 64, [42617, 43119], 1800)
        self.assertEqual(argv[argv.index('--point-native') + 1:argv.index('--point-native') + 3],
                         ['42617', '43119'])
        self.assertEqual(argv[argv.index('--identity') + 1], 'a' * 64)


if __name__ == '__main__':
    unittest.main()
