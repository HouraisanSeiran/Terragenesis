"""Independent path-sum references for finite network discharge accumulation."""
import unittest

import numpy as np

from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge


def inputs(receiver, q=None):
    rec = np.array([receiver], dtype=np.int64)
    local = np.ones(rec.shape, np.float64) if q is None else np.array([q], np.float64)
    valid = np.ones(rec.shape, bool)
    kinds = np.where(rec < 0, 'retained', 'interior').astype('U24')
    return rec, local, valid, kinds


def solve(args, **kwargs):
    rec, local, valid, kinds = args
    return accumulate_network_discharge(rec, local, valid, terminal_kind=kinds, **kwargs)


def reference(rec, local, valid, unknown):
    # Deliberately not a topological sweep: walk each source's complete downstream path.
    q = np.zeros(rec.size, np.float64)
    dirty = np.zeros(rec.size, bool)
    for source in np.flatnonzero(valid.ravel()):
        current = int(source)
        seen = set()
        while current >= 0:
            if current in seen:
                raise ValueError('cycle')
            seen.add(current)
            q[current] += local.ravel()[source]
            dirty[current] |= unknown.ravel()[source]
            current = int(rec.ravel()[current])
    return q.reshape(rec.shape), valid & ~dirty.reshape(rec.shape)


class NetworkAccumulationTests(unittest.TestCase):
    def test_chain_and_y_and_isolated(self):
        for rec, expected in (([1, 2, 3, -1], [1, 2, 3, 4]),
                              ([2, 2, 3, -1], [1, 1, 3, 4]),
                              ([-1, -1], [1, 1]),
                              ([3, 2, 3, -1], [1, 1, 2, 4])):
            with self.subTest(rec=rec):
                result = solve(inputs(rec))
                np.testing.assert_array_equal(result['known_routed_q_m3_s'], [expected])
                self.assertEqual(result['processed_cells'], len(rec))
                self.assertEqual(result['residual_m3_s'], 0.)

    def test_unknown_propagates_downstream_only(self):
        args = inputs([2, 2, 3, -1, -1])
        unknown = np.array([[True, False, False, False, False]])
        result = solve(args, upstream_unknown_mask=unknown)
        np.testing.assert_array_equal(result['complete_mask'], [[False, True, False, False, True]])
        self.assertEqual(result['retained_m3_s'], 5.)

    def test_three_terminal_ledgers(self):
        args = inputs([1, -1, -1, -1], [2, 3, 7, 11])
        args[3][0] = ['interior', 'open_outflow', 'retained', 'unknown_boundary']
        result = solve(args)
        self.assertEqual(result['input_total_m3_s'], 23.)
        self.assertEqual(result['open_outflow_m3_s'], 5.)
        self.assertEqual(result['retained_m3_s'], 7.)
        self.assertEqual(result['unknown_pending_m3_s'], 11.)
        self.assertTrue(result['complete_mask'].all())

    def test_invalid_cells(self):
        args = inputs([1, -1, -1], [2, 3, 0])
        args[2][0, 2] = False
        args[3][0, 2] = 'inactive'
        result = solve(args)
        self.assertFalse(result['complete_mask'][0, 2])
        self.assertEqual(result['valid_cells'], 2)
        self.assertEqual(result['retained_m3_s'], 5.)

    def test_cycles_and_tail_into_cycle(self):
        for rec in ([1, 0], [1, 2, 1], [0], [1, 0, -1]):
            with self.subTest(rec=rec), self.assertRaises(ValueError):
                solve(inputs(rec))

    def test_dtype_shape_and_budget_rejection(self):
        for position, dtype in ((0, np.float64), (1, np.float32), (2, np.int8)):
            args = list(inputs([1, -1]))
            args[position] = args[position].astype(dtype)
            with self.subTest(dtype=dtype), self.assertRaises(ValueError):
                solve(args)
        for budget in (True, 0, -1, 1, 1.5):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                solve(inputs([1, -1]), max_cells=budget)
        args = list(inputs([1, -1]))
        args[1] = np.ones((2, 1), np.float64)
        with self.assertRaises(ValueError):
            solve(args)

    def test_illegal_values_and_target(self):
        for rec in ([2, -1], [-2, -1]):
            with self.subTest(rec=rec), self.assertRaises(ValueError):
                solve(inputs(rec))
        for value in (-1., np.nan, np.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                solve(inputs([1, -1], [value, 1.]))
        args = inputs([1, -1], [1, 0])
        args[2][0, 1] = False
        args[3][0, 1] = 'inactive'
        with self.assertRaises(ValueError):
            solve(args)

    def test_terminal_policy_validation(self):
        for index, label in ((0, 'retained'), (1, 'interior'), (1, 'sea')):
            args = inputs([1, -1])
            args[3][0, index] = label
            with self.subTest(index=index, label=label), self.assertRaises(ValueError):
                solve(args)

    def test_overflow_and_input_immutability(self):
        args = inputs([1, -1], [1e308, 1e308])
        snapshots = [a.copy() for a in args]
        with self.assertRaises(ValueError):
            solve(args)
        for before, after in zip(snapshots, args):
            np.testing.assert_array_equal(before, after)
        args = inputs([2, 2, -1])
        snapshots = [a.copy() for a in args]
        solve(args)
        for before, after in zip(snapshots, args):
            np.testing.assert_array_equal(before, after)

    def test_storage_partition_and_load_order_do_not_change_flow(self):
        args = inputs([1, 2, 3, 4, 5, 6, 7, -1])
        expected = solve(args)['known_routed_q_m3_s']
        for order in ((0, 1), (1, 0)):
            rebuilt = [np.empty_like(a) for a in args]
            for tile in order:
                sl = np.s_[:, tile * 4:(tile + 1) * 4]
                for destination, source in zip(rebuilt, args):
                    destination[sl] = source[sl]
            np.testing.assert_array_equal(solve(rebuilt)['known_routed_q_m3_s'], expected)
        self.assertEqual(expected[0, 7], 8.)

    def test_unknown_mask_and_inactive_local_validation(self):
        args = inputs([-1, -1], [1, 0])
        args[2][0, 1] = False
        args[3][0, 1] = 'inactive'
        for unknown in (np.array([[False, True]]), np.zeros((2, 1), bool),
                        np.zeros((1, 2), np.int8)):
            with self.subTest(unknown=unknown), self.assertRaises(ValueError):
                solve(args, upstream_unknown_mask=unknown)
        args[1][0, 1] = 1.
        with self.assertRaises(ValueError):
            solve(args)

    def test_numbering_independence(self):
        args = inputs([2, 2, 3, -1, 3], [2., 3., 5., 7., 11.])
        permutation = np.array([3, 0, 4, 1, 2])
        inverse = np.argsort(permutation)
        old = args[0].ravel()[permutation]
        new_rec = np.where(old >= 0, inverse[np.maximum(old, 0)], -1)[None, :]
        permuted = (new_rec, args[1][:, permutation], args[2][:, permutation], args[3][:, permutation])
        result = solve(permuted)['known_routed_q_m3_s'][:, inverse]
        np.testing.assert_array_equal(result, solve(args)['known_routed_q_m3_s'])

    def test_fixed_seed_independent_path_reference(self):
        rng = np.random.default_rng(20261020)
        for n in (8, 31, 100, 257):
            rec = np.array([rng.integers(i + 1, n) if i + 1 < n else -1
                            for i in range(n)], dtype=np.int64)
            rec[rng.random(n) < .1] = -1
            args = inputs(rec, rng.integers(0, 20, n).astype(np.float64))
            unknown = rng.random(args[0].shape) < .05
            expected_q, expected_complete = reference(*args[:3], unknown)
            result = solve(args, upstream_unknown_mask=unknown)
            np.testing.assert_array_equal(result['known_routed_q_m3_s'], expected_q)
            np.testing.assert_array_equal(result['complete_mask'], expected_complete)
            self.assertEqual(result['residual_m3_s'], 0.)


if __name__ == '__main__':
    unittest.main()
