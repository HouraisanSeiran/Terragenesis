"""M4 tests.test_basin_storage_profiles; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from pathlib import Path as _m4_test_td_basin_storage_v10_Path
from pathlib import Path as _m4_test_td_basin_storage_v5_Path
from pathlib import Path as _m4_test_td_basin_storage_v6_full_Path
from pathlib import Path as _m4_test_td_basin_storage_v7_Path
from scipy.integrate import solve_ivp as _m4_test_td_basin_storage_v3_solve_ivp
from scipy.integrate import solve_ivp as _m4_test_td_basin_storage_v4_solve_ivp
from scipy.integrate import solve_ivp as _m4_test_td_basin_storage_v5_solve_ivp
from scipy.integrate import solve_ivp as _m4_test_td_basin_storage_v6_full_solve_ivp
from scipy.integrate import solve_ivp as _m4_test_td_basin_storage_v6_solve_ivp
from scipy.integrate import solve_ivp as _m4_test_td_basin_storage_v7_solve_ivp
from terrain_pipeline.basin_storage import exchange_event_threshold as _m4_test_td_basin_storage_v3_exchange
from terrain_pipeline.basin_storage import exchange_strang_two_sweep as _m4_test_td_basin_storage_implicit_exchange
from terrain_pipeline.basin_storage import exchange_strang_two_sweep as _m4_test_td_basin_storage_v4_v2_exchange
from terrain_pipeline.basin_storage import exchange_threshold_pair as _m4_test_td_basin_storage_v4_exchange
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_v10_make_td_source
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_v4_make_td_source
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_v5_make_td_source
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_v6_full_make_td_source
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_v7_make_td_source
from terrain_pipeline.basin_storage import parameters_event_strang as _m4_test_td_basin_storage_v3_parameters
from terrain_pipeline.basin_storage import parameters_strang_split as _m4_test_td_basin_storage_implicit_parameters
from terrain_pipeline.basin_storage import parameters_threshold_pair as _m4_test_td_basin_storage_v4_parameters
from terrain_pipeline.basin_storage import save_checkpoint as _m4_test_td_basin_storage_v10_save_checkpoint
from terrain_pipeline.basin_storage import simulate_hour as _m4_test_td_basin_storage_v10_simulate_hour
from terrain_pipeline.basin_storage import storageimplicit_simulate as _m4_test_td_basin_storage_implicit_simulate_basin_storage
from terrain_pipeline.basin_storage import storagev10_load_checkpoint as _m4_test_td_basin_storage_v10_load_checkpoint
from terrain_pipeline.basin_storage import storagev10_save_storage as _m4_test_td_basin_storage_v10_save_storage
from terrain_pipeline.basin_storage import storagev4_simulate as _m4_test_td_basin_storage_v4_simulate_basin_storage
from terrain_pipeline.basin_storage import storagev5_load_storage as _m4_test_td_basin_storage_v5_load_storage
from terrain_pipeline.basin_storage import storagev5_save_storage as _m4_test_td_basin_storage_v5_save_storage
from terrain_pipeline.basin_storage import storagev5_simulate as _m4_test_td_basin_storage_v5_simulate_basin_storage
from terrain_pipeline.basin_storage import storagev6_load_storage as _m4_test_td_basin_storage_v6_full_load_storage
from terrain_pipeline.basin_storage import storagev6_save_storage as _m4_test_td_basin_storage_v6_full_save_storage
from terrain_pipeline.basin_storage import storagev6_simulate as _m4_test_td_basin_storage_v6_full_simulate_basin_storage
from terrain_pipeline.basin_storage import storagev6_validate_saved_storage as _m4_test_td_basin_storage_v6_full_validate_saved_storage
from terrain_pipeline.basin_storage import storagev7_load_storage as _m4_test_td_basin_storage_v7_load_storage
from terrain_pipeline.basin_storage import storagev7_save_storage as _m4_test_td_basin_storage_v7_save_storage
from terrain_pipeline.basin_storage import storagev7_simulate as _m4_test_td_basin_storage_v7_simulate_basin_storage
from terrain_pipeline.basin_storage import storagev7_validate_saved_storage as _m4_test_td_basin_storage_v7_validate_saved_storage
from terrain_pipeline.basin_storage import validate_basin_storage as _m4_test_td_basin_storage_implicit_validate_basin_storage
from terrain_pipeline.basin_storage import validate_basin_storage as _m4_test_td_basin_storage_v4_validate_basin_storage
from terrain_pipeline.basin_storage import validate_storage as _m4_test_td_basin_storage_v10_validate_storage
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_v10_build_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_v4_build_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_v5_build_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_v6_full_build_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_v7_build_basin_hierarchy
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_v10_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_v5_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_v6_full_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_v7_file_sha256
from terrain_pipeline.common_infra import identity as _m4_test_td_basin_storage_v10_identity
from terrain_pipeline.common_infra import identity as _m4_test_td_basin_storage_v6_full_identity
from terrain_pipeline.common_infra import identity as _m4_test_td_basin_storage_v7_identity
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_basin_storage_v5_RunoffParameters
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_basin_storage_v6_full_RunoffParameters
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_basin_storage_v7_RunoffParameters
from terrain_pipeline.td_native_weather_storage_v10_io import validate_native_v10_accounts as _m4_test_td_basin_storage_v10_validate_native_v10_accounts
from tests.test_basin_storage import BasinStorageBasinStorageTests as _m4_test_basin_storage_BasinStorageBasinStorageTests
from tests.test_basin_storage import basin_storage_DRY_SOIL as _m4_test_basin_storage_basin_storage_DRY_SOIL
from tools.audit_td_basin_generation import audit_storage as _m4_test_td_basin_storage_v5_audit_storage
from tools.audit_td_basin_generation import audit_storage as _m4_test_td_basin_storage_v6_full_audit_storage
from tools.audit_td_basin_generation import audit_storage as _m4_test_td_basin_storage_v7_audit_storage
from unittest.mock import patch as _m4_test_td_basin_storage_v4_patch
from unittest.mock import patch as _m4_test_td_basin_storage_v5_patch
from unittest.mock import patch as _m4_test_td_basin_storage_v6_full_patch
from unittest.mock import patch as _m4_test_td_basin_storage_v7_patch
import numpy as _m4_test_td_basin_storage_implicit_np
import numpy as _m4_test_td_basin_storage_v10_np
import numpy as _m4_test_td_basin_storage_v3_np
import numpy as _m4_test_td_basin_storage_v4_np
import numpy as _m4_test_td_basin_storage_v5_np
import numpy as _m4_test_td_basin_storage_v6_full_np
import numpy as _m4_test_td_basin_storage_v6_np
import numpy as _m4_test_td_basin_storage_v7_np
import subprocess as _m4_test_td_basin_storage_v10_subprocess
import subprocess as _m4_test_td_basin_storage_v5_subprocess
import subprocess as _m4_test_td_basin_storage_v6_full_subprocess
import subprocess as _m4_test_td_basin_storage_v7_subprocess
import sys as _m4_test_td_basin_storage_v10_sys
import sys as _m4_test_td_basin_storage_v5_sys
import sys as _m4_test_td_basin_storage_v6_full_sys
import sys as _m4_test_td_basin_storage_v7_sys
import tempfile as _m4_test_td_basin_storage_v10_tempfile
import tempfile as _m4_test_td_basin_storage_v5_tempfile
import tempfile as _m4_test_td_basin_storage_v6_full_tempfile
import tempfile as _m4_test_td_basin_storage_v7_tempfile
import terrain_pipeline.basin_storage as _m4_test_td_basin_storage_v6_transport
import unittest as _m4_test_td_basin_storage_implicit_unittest
import unittest as _m4_test_td_basin_storage_v10_unittest
import unittest as _m4_test_td_basin_storage_v3_unittest
import unittest as _m4_test_td_basin_storage_v4_unittest
import unittest as _m4_test_td_basin_storage_v5_unittest
import unittest as _m4_test_td_basin_storage_v6_full_unittest
import unittest as _m4_test_td_basin_storage_v6_unittest
import unittest as _m4_test_td_basin_storage_v7_unittest

# --- tests/test_td_basin_storage_implicit.py:12 ---
class BasinStorageImplicitAnalyticFaceTests(_m4_test_td_basin_storage_implicit_unittest.TestCase):
    def test_refinement_compiled_exchange_matches_numpy(self):
        from terrain_pipeline.basin_storage import refinement_compiled_exchange as _compiled_exchange
        faces = _m4_test_td_basin_storage_implicit_np.array([[0, 1], [1, 2], [3, 4], [4, 5], [0, 3], [1, 4], [2, 5]], _m4_test_td_basin_storage_implicit_np.int64)
        first, second = faces[:, 0], faces[:, 1]
        groups = _m4_test_td_basin_storage_implicit_np.where(first // 3 == second // 3, first % 3 % 2, 2 + first // 3 % 2)
        prepared = tuple(_m4_test_td_basin_storage_implicit_np.flatnonzero(groups == group) for group in range(4))
        ordered = _m4_test_td_basin_storage_implicit_np.concatenate(prepared)
        offsets = _m4_test_td_basin_storage_implicit_np.concatenate(([0], _m4_test_td_basin_storage_implicit_np.cumsum([len(values) for values in prepared])))
        bed = _m4_test_td_basin_storage_implicit_np.array([0., 1., .4, 1.8, .1, 1.2])
        depth = _m4_test_td_basin_storage_implicit_np.array([3., 0., .05, 0., 2.4, .1])
        boundary = _m4_test_td_basin_storage_implicit_np.array([0, 5], _m4_test_td_basin_storage_implicit_np.int64)
        width = _m4_test_td_basin_storage_implicit_np.array([60., 60.])
        config = _m4_test_td_basin_storage_implicit_parameters(None)
        for substep in (60, 5, 2.5):
            expected = _m4_test_td_basin_storage_implicit_exchange(depth, bed, faces, boundary, width, 30., substep, config, 3, prepared)
            actual = _compiled_exchange(depth, bed, faces, boundary, width, 30., substep, .6, ordered, offsets)
            for actual_array, expected_array in zip(actual, expected):
                _m4_test_td_basin_storage_implicit_np.testing.assert_allclose(actual_array, expected_array, rtol=1e-12, atol=1e-12)

    def test_pair_exponential_and_threshold_crossing(self):
        config = _m4_test_td_basin_storage_implicit_parameters({"surface_evaporation_mm_h": 0})
        faces = _m4_test_td_basin_storage_implicit_np.array([[0, 1]], _m4_test_td_basin_storage_implicit_np.int64)
        depth, forward, reverse, exported, forward_s, reverse_s = _m4_test_td_basin_storage_implicit_exchange(
            _m4_test_td_basin_storage_implicit_np.array([3., 0.]), _m4_test_td_basin_storage_implicit_np.array([0., 0.]), faces, _m4_test_td_basin_storage_implicit_np.array([], _m4_test_td_basin_storage_implicit_np.int64), _m4_test_td_basin_storage_implicit_np.array([]), 1., 1., config, 2)
        expected = 1.5 * (1 - _m4_test_td_basin_storage_implicit_np.exp(-1.2))
        self.assertAlmostEqual(forward[0], expected)
        _m4_test_td_basin_storage_implicit_np.testing.assert_allclose(depth, [3 - expected, expected])
        depth, forward, reverse, exported, forward_s, reverse_s = _m4_test_td_basin_storage_implicit_exchange(
            _m4_test_td_basin_storage_implicit_np.array([3., 0.]), _m4_test_td_basin_storage_implicit_np.array([0., 2.]), faces, _m4_test_td_basin_storage_implicit_np.array([], _m4_test_td_basin_storage_implicit_np.int64), _m4_test_td_basin_storage_implicit_np.array([]), 1., 1., config, 2)
        expected = 0.5 * (1 - _m4_test_td_basin_storage_implicit_np.exp(-1.2))
        self.assertAlmostEqual(forward[0], expected)
        self.assertEqual(reverse[0], 0)
        self.assertEqual(forward_s[0], 1)
        depth, forward, reverse, exported, forward_s, reverse_s = _m4_test_td_basin_storage_implicit_exchange(
            _m4_test_td_basin_storage_implicit_np.array([3., 0.]), _m4_test_td_basin_storage_implicit_np.array([2., 0.]), faces, _m4_test_td_basin_storage_implicit_np.array([], _m4_test_td_basin_storage_implicit_np.int64), _m4_test_td_basin_storage_implicit_np.array([]), 1., 10., config, 2)
        self.assertAlmostEqual(depth.sum(), 3)
        self.assertGreater(depth[1], 2)
        self.assertGreaterEqual(depth.min(), 0)

    def test_nested_and_recession_same_fixtures(self):
        helper = _m4_test_basin_storage_BasinStorageBasinStorageTests()
        topology = helper.topology([[0, 2, 1, 4, 0]])
        for volume, expected in ((2.5, [2, 0, .5, 0, 0]), (4, [7/3, 1/3, 4/3, 0, 0]), (9.5, [4, 2, 3, 0, .5])):
            result = _m4_test_td_basin_storage_implicit_simulate_basin_storage(topology, _m4_test_td_basin_storage_implicit_np.zeros(1), dt_s=7200, initial_depth_m=[[volume, 0, 0, 0, 0]],
                runoff_parameters=_m4_test_basin_storage_basin_storage_DRY_SOIL, parameters={"surface_evaporation_mm_h": 0, "substep_s": 10})
            _m4_test_td_basin_storage_implicit_np.testing.assert_allclose(result["arrays"]["depth_m"][-1], expected, atol=1e-9)
            self.assertTrue(_m4_test_td_basin_storage_implicit_validate_basin_storage(result))
        recession = _m4_test_td_basin_storage_implicit_simulate_basin_storage(topology, _m4_test_td_basin_storage_implicit_np.zeros(4), initial_depth_m=[[7/3, 1/3, 4/3, 0, 0]],
            runoff_parameters=_m4_test_basin_storage_basin_storage_DRY_SOIL, parameters={"surface_evaporation_mm_h": 200, "substep_s": 10})
        self.assertEqual(recession["arrays"]["wet_pool_count"][0], 1)
        self.assertEqual(recession["arrays"]["wet_pool_count"][-1], 2)
        self.assertTrue(_m4_test_td_basin_storage_implicit_validate_basin_storage(recession))

    def test_matching_groups_non_square_and_bidirectional_ledger(self):
        topology = _m4_test_basin_storage_BasinStorageBasinStorageTests().topology([[0, 1, 0, 2], [0, 0, 1, 0]])
        result = _m4_test_td_basin_storage_implicit_simulate_basin_storage(topology, _m4_test_td_basin_storage_implicit_np.array([30., 0.]), initial_depth_m=[[2, 0, 0, 0], [0, 0, 0, 1]],
            runoff_parameters=_m4_test_basin_storage_basin_storage_DRY_SOIL, parameters={"surface_evaporation_mm_h": 0, "substep_s": 60})
        self.assertTrue(_m4_test_td_basin_storage_implicit_validate_basin_storage(result))
        self.assertEqual(result["arrays"]["limiter_active_count"].sum(), 0)
        self.assertFalse(result["metadata"]["morphology_flux_ready"])

# --- tests/test_td_basin_storage_v3.py:10 ---
class BasinStorageProfile3V3Tests(_m4_test_td_basin_storage_v3_unittest.TestCase):
    def test_cross_sill_exact_event_matches_threshold_ode(self):
        bed = _m4_test_td_basin_storage_v3_np.array([0., 2.])
        initial = _m4_test_td_basin_storage_v3_np.array([4., 0.])
        faces = _m4_test_td_basin_storage_v3_np.array([[0, 1]], dtype=_m4_test_td_basin_storage_v3_np.int64)
        config = _m4_test_td_basin_storage_v3_parameters({"surface_evaporation_mm_h": 0})
        rate = .6

        def derivative(_, values):
            head = bed + values
            difference = head[0] - head[1]
            if difference <= 0:
                return _m4_test_td_basin_storage_v3_np.zeros(2)
            flow = rate * max(difference - max(0., bed[1] - head[1]), 0)
            return _m4_test_td_basin_storage_v3_np.array([-flow, flow])

        reference = _m4_test_td_basin_storage_v3_solve_ivp(derivative, (0, 60), initial, rtol=1e-12, atol=1e-13, max_step=.001)
        actual, forward, reverse, _, _, _ = _m4_test_td_basin_storage_v3_exchange(initial, bed, faces, _m4_test_td_basin_storage_v3_np.array([], dtype=_m4_test_td_basin_storage_v3_np.int64),
            _m4_test_td_basin_storage_v3_np.array([]), 1., 60., config, 2)
        _m4_test_td_basin_storage_v3_np.testing.assert_allclose(actual, reference.y[:, -1], atol=2e-5)
        self.assertGreater(forward[0], 0)
        self.assertEqual(reverse[0], 0)
        self.assertAlmostEqual(actual.sum(), initial.sum(), places=12)

    def test_event_formula_does_not_use_partial_excess_as_initial_difference(self):
        bed = _m4_test_td_basin_storage_v3_np.array([0., 2.])
        faces = _m4_test_td_basin_storage_v3_np.array([[0, 1]], dtype=_m4_test_td_basin_storage_v3_np.int64)
        config = _m4_test_td_basin_storage_v3_parameters(None)
        actual, *_ = _m4_test_td_basin_storage_v3_exchange(_m4_test_td_basin_storage_v3_np.array([4., 0.]), bed, faces, _m4_test_td_basin_storage_v3_np.array([], dtype=_m4_test_td_basin_storage_v3_np.int64), _m4_test_td_basin_storage_v3_np.array([]), 1., 1., config, 2)
        difference = 4 - 2
        expected = difference / 2 * (1 - _m4_test_td_basin_storage_v3_np.exp(-2 * .6))
        self.assertAlmostEqual(4 - actual[0], expected, places=12)

    def test_random_matching_is_positive_and_conservative(self):
        rng = _m4_test_td_basin_storage_v3_np.random.default_rng(20261002)
        for _ in range(30):
            rows, columns = 3, 5
            ids = _m4_test_td_basin_storage_v3_np.arange(rows * columns).reshape(rows, columns)
            faces = _m4_test_td_basin_storage_v3_np.vstack((_m4_test_td_basin_storage_v3_np.column_stack((ids[:, :-1].ravel(), ids[:, 1:].ravel())),
                _m4_test_td_basin_storage_v3_np.column_stack((ids[:-1].ravel(), ids[1:].ravel())))).astype(_m4_test_td_basin_storage_v3_np.int64)
            first, second = faces[:, 0], faces[:, 1]
            groups = _m4_test_td_basin_storage_v3_np.where(first // columns == second // columns, first % columns % 2, 2 + first // columns % 2)
            prepared = tuple(_m4_test_td_basin_storage_v3_np.flatnonzero(groups == group) for group in range(4))
            actual, forward, reverse, _, forward_s, reverse_s = _m4_test_td_basin_storage_v3_exchange(rng.uniform(0, 5, rows * columns),
                rng.uniform(1300, 1400, rows * columns), faces, _m4_test_td_basin_storage_v3_np.array([], dtype=_m4_test_td_basin_storage_v3_np.int64), _m4_test_td_basin_storage_v3_np.array([]), 30., 2.5,
                _m4_test_td_basin_storage_v3_parameters(None), columns, prepared)
            self.assertTrue(_m4_test_td_basin_storage_v3_np.isfinite(actual).all())
            self.assertGreaterEqual(actual.min(), 0)
            self.assertAlmostEqual(actual.sum(), actual.sum(), places=12)
            self.assertTrue(_m4_test_td_basin_storage_v3_np.all(forward_s + reverse_s <= 2.5 + 1e-12))

# --- tests/test_td_basin_storage_v4.py:16 ---
class BasinStorageProfile4ThresholdPairTests(_m4_test_td_basin_storage_v4_unittest.TestCase):
    def test_high_bed_dry_recipient(self):
        actual, *_ = _m4_test_td_basin_storage_v4_exchange(_m4_test_td_basin_storage_v4_np.array([1., 0.]), _m4_test_td_basin_storage_v4_np.array([2., 0.]), _m4_test_td_basin_storage_v4_np.array([[0, 1]], _m4_test_td_basin_storage_v4_np.int64),
            _m4_test_td_basin_storage_v4_np.array([], _m4_test_td_basin_storage_v4_np.int64), _m4_test_td_basin_storage_v4_np.array([]), 1., 1., _m4_test_td_basin_storage_v4_parameters(None), 2)
        _m4_test_td_basin_storage_v4_np.testing.assert_allclose(actual, [_m4_test_td_basin_storage_v4_np.exp(-.6), 1 - _m4_test_td_basin_storage_v4_np.exp(-.6)], atol=1e-12)

    def test_independent_ode_both_directions_and_crossing(self):
        cases = [([2., 0.], [1., 0.]), ([0., 2.], [0., 1.]), ([2., 0.], [5., 0.]),
                 ([0., 2.], [0., 5.]), ([0., 2.], [4., 0.]), ([2., 0.], [0., 0.]),
                 ([2., 0.], [3., 3.])]
        for beds, initial in cases:
            bed = _m4_test_td_basin_storage_v4_np.array(beds)
            depth = _m4_test_td_basin_storage_v4_np.array(initial)

            def ode(time, values):
                head = bed + values
                donor, recipient = (0, 1) if head[0] >= head[1] else (1, 0)
                flow = .6 * max(head[donor] - max(max(bed), head[recipient]), 0.)
                derivative = _m4_test_td_basin_storage_v4_np.zeros(2)
                derivative[donor] = -flow
                derivative[recipient] = flow
                return derivative

            reference = _m4_test_td_basin_storage_v4_solve_ivp(ode, (0., 5.), depth, method="DOP853", rtol=1e-12, atol=1e-13)
            actual, forward, reverse, _, forward_s, reverse_s = _m4_test_td_basin_storage_v4_exchange(depth, bed,
                _m4_test_td_basin_storage_v4_np.array([[0, 1]], _m4_test_td_basin_storage_v4_np.int64), _m4_test_td_basin_storage_v4_np.array([], _m4_test_td_basin_storage_v4_np.int64), _m4_test_td_basin_storage_v4_np.array([]), 1., 5., _m4_test_td_basin_storage_v4_parameters(None), 2)
            _m4_test_td_basin_storage_v4_np.testing.assert_allclose(actual, reference.y[:, -1], atol=1e-9, rtol=0)
            self.assertAlmostEqual(actual.sum(), depth.sum(), places=12)
            self.assertTrue(_m4_test_td_basin_storage_v4_np.all(actual >= 0))
            self.assertTrue(_m4_test_td_basin_storage_v4_np.all(forward_s + reverse_s <= 5.))

    def test_compiled_v2_differential_matching_and_boundary(self):
        random = _m4_test_td_basin_storage_v4_np.random.default_rng(20261002)
        grid = _m4_test_td_basin_storage_v4_np.arange(15).reshape(3, 5)
        faces = _m4_test_td_basin_storage_v4_np.vstack((_m4_test_td_basin_storage_v4_np.column_stack((grid[:, :-1].ravel(), grid[:, 1:].ravel())),
                           _m4_test_td_basin_storage_v4_np.column_stack((grid[:-1].ravel(), grid[1:].ravel())))).astype(_m4_test_td_basin_storage_v4_np.int64)
        for duration in (60., 5., 2.5, 1.25):
            for case in range(10):
                depth = random.uniform(0, 8, 15)
                bed = random.uniform(1300, 1400, 15)
                inputs = (depth, bed, faces, _m4_test_td_basin_storage_v4_np.array([0, 14], _m4_test_td_basin_storage_v4_np.int64), _m4_test_td_basin_storage_v4_np.array([60., 30.]),
                          30., duration, _m4_test_td_basin_storage_v4_parameters(None), 5)
                actual = _m4_test_td_basin_storage_v4_exchange(*inputs)
                expected = _m4_test_td_basin_storage_v4_v2_exchange(*inputs)
                for got, wanted in zip(actual, expected):
                    _m4_test_td_basin_storage_v4_np.testing.assert_allclose(got, wanted, atol=1e-9, rtol=1e-11)
                self.assertAlmostEqual(actual[0].sum() * 900 + actual[3].sum(), depth.sum() * 900, places=8)

    def test_v4_saved_validation_never_advances_compiled_kernel(self):
        hierarchy = _m4_test_td_basin_storage_v4_build_basin_hierarchy(_m4_test_td_basin_storage_v4_make_td_source(_m4_test_td_basin_storage_v4_np.array([[2., 0.]]), spacing_m=1))
        result = _m4_test_td_basin_storage_v4_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v4_np.array([0.]), dt_s=10,
                                        initial_depth_m=_m4_test_td_basin_storage_v4_np.array([[1., 0.]]))
        with _m4_test_td_basin_storage_v4_patch('terrain_pipeline.basin_storage.exchange_strang_scalar_sweep', side_effect=AssertionError("no JIT")):
            self.assertTrue(_m4_test_td_basin_storage_v4_validate_basin_storage(result))
        self.assertEqual(result["metadata"]["algorithm"], "D4-threshold-exact-Strang-v4")
        self.assertFalse(result["metadata"]["hydraulic_ready"])

    def test_independent_work_budget_rejected(self):
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_v4_parameters({"max_work_face_steps": 6_000_000_001})

# --- tests/test_td_basin_storage_v5.py:23 ---
class BasinStorageProfile5SymmetricForcingTests(_m4_test_td_basin_storage_v5_unittest.TestCase):
    def test_full_solver_water_accounts_and_activity(self):
        hierarchy = _m4_test_td_basin_storage_v5_build_basin_hierarchy(_m4_test_td_basin_storage_v5_make_td_source(_m4_test_td_basin_storage_v5_np.array([[0., 2., 1.], [3., 4., 0.]]), spacing_m=1))
        for rain in (_m4_test_td_basin_storage_v5_np.array([30., 0.]), _m4_test_td_basin_storage_v5_np.zeros(2)):
            result = _m4_test_td_basin_storage_v5_simulate_basin_storage(hierarchy, rain, dt_s=60,
                initial_depth_m=_m4_test_td_basin_storage_v5_np.array([[1., 0., .5], [0., 0., 1.]]), parameters={"substep_s": 2.5})
            audit = _m4_test_td_basin_storage_v5_audit_storage(result["arrays"], result["metadata"])
            self.assertLess(audit["max_step_global_residual_m3"], 1e-8)
            self.assertTrue(_m4_test_td_basin_storage_v5_np.all(result["arrays"]["depth_m"] >= 0))
            self.assertFalse(result["metadata"]["hydraulic_ready"])

    def test_dry_and_actual_reverse_face_accounts(self):
        hierarchy = _m4_test_td_basin_storage_v5_build_basin_hierarchy(_m4_test_td_basin_storage_v5_make_td_source(_m4_test_td_basin_storage_v5_np.array([[2., 0.]]), spacing_m=1))
        dry_runoff = _m4_test_td_basin_storage_v5_RunoffParameters(initial_soil_mm=0)
        dry = _m4_test_td_basin_storage_v5_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v5_np.zeros(2), dt_s=10, runoff_parameters=dry_runoff)
        self.assertEqual(dry["arrays"]["depth_m"].sum(), 0)
        self.assertEqual(dry["arrays"]["face_forward_m3"].sum(), 0)
        reverse = _m4_test_td_basin_storage_v5_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v5_np.zeros(2), dt_s=10,
            initial_depth_m=_m4_test_td_basin_storage_v5_np.array([[0., 4.]]), runoff_parameters=dry_runoff,
            parameters={"surface_evaporation_mm_h": 0, "substep_s": 2.5})
        self.assertGreater(reverse["arrays"]["face_reverse_m3"][0], 0)
        self.assertEqual(reverse["arrays"]["routed_volume_m3"][0], 0)
        self.assertLessEqual(reverse["arrays"]["active_reverse_s"][0], 20)
        self.assertLess(_m4_test_td_basin_storage_v5_audit_storage(reverse["arrays"], reverse["metadata"])["max_step_global_residual_m3"], 1e-9)

    def test_saved_storage_cold_read_no_compiled_exchange(self):
        hierarchy = _m4_test_td_basin_storage_v5_build_basin_hierarchy(_m4_test_td_basin_storage_v5_make_td_source(_m4_test_td_basin_storage_v5_np.array([[2., 0.]]), spacing_m=1))
        result = _m4_test_td_basin_storage_v5_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v5_np.array([30., 0.]), dt_s=60)
        with _m4_test_td_basin_storage_v5_tempfile.TemporaryDirectory() as directory:
            path = _m4_test_td_basin_storage_v5_Path(directory) / "storage.npz"
            _m4_test_td_basin_storage_v5_save_storage(path, result)
            with _m4_test_td_basin_storage_v5_patch('terrain_pipeline.basin_storage.exchange_strang_scalar_sweep', side_effect=AssertionError("no advance")):
                loaded = _m4_test_td_basin_storage_v5_load_storage(path, expected_sha256=_m4_test_td_basin_storage_v5_file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            code = 'import sys\nfrom terrain_pipeline.basin_storage import storagev5_load_storage as load_storage\nload_storage(sys.argv[1], expected_sha256=sys.argv[2], expected_identity=sys.argv[3])\nassert \'terrain_pipeline.td_basin_storage_v4\' not in sys.modules\nassert \'terrain_pipeline.td_basin_storage_v5\' not in sys.modules\nassert "terrain_pipeline.basin_storage" in sys.modules\n'
            completed = _m4_test_td_basin_storage_v5_subprocess.run([_m4_test_td_basin_storage_v5_sys.executable, "-c", code, str(path), _m4_test_td_basin_storage_v5_file_sha256(path), result["identity_sha256"]],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_constant_source_full_solver_second_order(self):
        bed = _m4_test_td_basin_storage_v5_np.array([[0., 0.]])
        hierarchy = _m4_test_td_basin_storage_v5_build_basin_hierarchy(_m4_test_td_basin_storage_v5_make_td_source(bed, spacing_m=30))
        initial = _m4_test_td_basin_storage_v5_np.array([[1., .2]])
        source = _m4_test_td_basin_storage_v5_np.array([.03 / 3600, .01 / 3600])
        rain = _m4_test_td_basin_storage_v5_np.array([[[30., 10.]]])
        runoff = _m4_test_td_basin_storage_v5_RunoffParameters(initial_soil_mm=0, potential_et_mm_h=0, percolation_mm_h=0,
                                   infiltration_capacity_mm_h=0)

        def ode(time, depth):
            flow = .6 / 30 * (depth[0] - depth[1])
            return source + _m4_test_td_basin_storage_v5_np.array([-flow, flow])

        reference = _m4_test_td_basin_storage_v5_solve_ivp(ode, (0, 300), initial.ravel(), method="DOP853", rtol=1e-12, atol=1e-13).y[:, -1]
        errors = []
        for step in (5., 2.5, 1.25, .625):
            result = _m4_test_td_basin_storage_v5_simulate_basin_storage(hierarchy, rain, dt_s=300, initial_depth_m=initial,
                runoff_parameters=runoff, parameters={"substep_s": step, "surface_evaporation_mm_h": 0})
            errors.append(float(abs(result["arrays"]["depth_m"][-1] - reference).max()))
        self.assertTrue(all(errors[index] > 3.8 * errors[index + 1] for index in range(3)))
        self.assertLess(errors[-1], 1e-8)

# --- tests/test_td_basin_storage_v6.py:7 ---
class BasinStorageProfile6SimultaneousTransportTests(_m4_test_td_basin_storage_v6_unittest.TestCase):
    def exchange(self, depth, bed, faces, dt, spacing=1., boundary=None, widths=None):
        boundary = _m4_test_td_basin_storage_v6_np.array([], dtype=_m4_test_td_basin_storage_v6_np.int64) if boundary is None else boundary
        widths = _m4_test_td_basin_storage_v6_np.array([]) if widths is None else widths
        _m4_test_td_basin_storage_v6_transport.validate_cfl(faces, boundary, widths, spacing, dt, .6, len(depth))
        return _m4_test_td_basin_storage_v6_transport._compiled_exchange(depth, bed, faces, boundary, widths, spacing, dt, .6,
                                            _m4_test_td_basin_storage_v6_np.array([], dtype=_m4_test_td_basin_storage_v6_np.int64), _m4_test_td_basin_storage_v6_np.array([], dtype=_m4_test_td_basin_storage_v6_np.int64))

    def test_high_bed_regression_and_ode_refinement(self):
        faces = _m4_test_td_basin_storage_v6_np.array([[0, 1]], dtype=_m4_test_td_basin_storage_v6_np.int64)
        errors = []
        for dt in (.2, .1, .05):
            depth = _m4_test_td_basin_storage_v6_np.array([1., 0.])
            for step in range(round(1 / dt)):
                depth = self.exchange(depth, _m4_test_td_basin_storage_v6_np.array([2., 0.]), faces, dt)[0]
            errors.append(abs(depth[0] - _m4_test_td_basin_storage_v6_np.exp(-.6)))
            self.assertAlmostEqual(depth.sum(), 1., places=14)
        self.assertGreater(errors[0] / errors[1], 3.8)
        self.assertGreater(errors[1] / errors[2], 3.8)

    def test_multiface_sill_front_ode_mass_divergence_activity(self):
        bed = _m4_test_td_basin_storage_v6_np.array([2., 0., 1., 2., .5, 0.])
        initial = _m4_test_td_basin_storage_v6_np.array([1., .2, .1, .1, 0., .3])
        faces = _m4_test_td_basin_storage_v6_np.array([[0, 1], [1, 2], [3, 4], [4, 5], [0, 3], [1, 4], [2, 5]])
        boundary = _m4_test_td_basin_storage_v6_np.array([5], dtype=_m4_test_td_basin_storage_v6_np.int64)
        widths = _m4_test_td_basin_storage_v6_np.array([1.])
        reference = _m4_test_td_basin_storage_v6_solve_ivp(lambda time, depth: _m4_test_td_basin_storage_v6_transport._stage(depth, bed, faces, boundary, widths, 1., .6)[0],
                              (0, 2), initial, method="DOP853", rtol=1e-12, atol=1e-13).y[:, -1]
        errors = []
        for dt in (.1, .05, .025):
            depth = initial.copy()
            net = _m4_test_td_basin_storage_v6_np.zeros(len(faces))
            export = 0.
            for step in range(round(2 / dt)):
                depth, forward, reverse, exported, active_forward, active_reverse = self.exchange(depth, bed, faces, dt, boundary=boundary, widths=widths)
                self.assertTrue(_m4_test_td_basin_storage_v6_np.all(depth >= 0))
                self.assertTrue(_m4_test_td_basin_storage_v6_np.all(active_forward + active_reverse <= dt))
                net += forward - reverse
                export += exported.sum()
            divergence = _m4_test_td_basin_storage_v6_np.bincount(faces[:, 1], weights=net, minlength=6) - _m4_test_td_basin_storage_v6_np.bincount(faces[:, 0], weights=net, minlength=6)
            divergence[5] -= export
            _m4_test_td_basin_storage_v6_np.testing.assert_allclose(depth - initial, divergence, atol=1e-14)
            self.assertAlmostEqual(depth.sum() + export, initial.sum(), places=13)
            errors.append(abs(depth-reference).max())
        self.assertGreater(errors[0] / errors[1], 3.5)
        self.assertGreater(errors[1] / errors[2], 3.5)

    def test_cfl_rejects_before_stage(self):
        faces = _m4_test_td_basin_storage_v6_np.array([[0, 1], [0, 2], [0, 3], [0, 4]])
        with self.assertRaisesRegex(ValueError, "CFL"):
            self.exchange(_m4_test_td_basin_storage_v6_np.ones(5), _m4_test_td_basin_storage_v6_np.zeros(5), faces, .5)

    def test_direction_reversal_quadrature(self):
        result = self.exchange(_m4_test_td_basin_storage_v6_np.array([1., 0.]), _m4_test_td_basin_storage_v6_np.zeros(2), _m4_test_td_basin_storage_v6_np.array([[0, 1]]), 1.)
        self.assertGreater(result[1][0], 0)
        self.assertGreater(result[2][0], 0)
        self.assertEqual(result[4][0], .5)
        self.assertEqual(result[5][0], .5)

# --- tests/test_td_basin_storage_v6_full.py:25 ---
class BasinStorageProfile6FullSymmetricForcingTests(_m4_test_td_basin_storage_v6_full_unittest.TestCase):
    def test_cold_cfl_metadata_cannot_be_forged(self):
        hierarchy = _m4_test_td_basin_storage_v6_full_build_basin_hierarchy(_m4_test_td_basin_storage_v6_full_make_td_source(_m4_test_td_basin_storage_v6_full_np.zeros((2, 2)), spacing_m=30))
        result = _m4_test_td_basin_storage_v6_full_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v6_full_np.zeros(1), dt_s=10)
        metadata = {**result["metadata"], "positivity_cfl": .99}
        forged = {**result, "metadata": metadata, "identity_sha256": _m4_test_td_basin_storage_v6_full_identity(result["arrays"], metadata)}
        with self.assertRaisesRegex(ValueError, "CFL"):
            _m4_test_td_basin_storage_v6_full_validate_saved_storage(forged)

    def test_full_solver_water_accounts_and_activity(self):
        hierarchy = _m4_test_td_basin_storage_v6_full_build_basin_hierarchy(_m4_test_td_basin_storage_v6_full_make_td_source(_m4_test_td_basin_storage_v6_full_np.array([[0., 2., 1.], [3., 4., 0.]]), spacing_m=1))
        for rain in (_m4_test_td_basin_storage_v6_full_np.array([30., 0.]), _m4_test_td_basin_storage_v6_full_np.zeros(2)):
            result = _m4_test_td_basin_storage_v6_full_simulate_basin_storage(hierarchy, rain, dt_s=60,
                initial_depth_m=_m4_test_td_basin_storage_v6_full_np.array([[1., 0., .5], [0., 0., 1.]]), parameters={"substep_s": .25})
            audit = _m4_test_td_basin_storage_v6_full_audit_storage(result["arrays"], result["metadata"])
            self.assertLess(audit["max_step_global_residual_m3"], 1e-8)
            self.assertTrue(_m4_test_td_basin_storage_v6_full_np.all(result["arrays"]["depth_m"] >= 0))
            self.assertFalse(result["metadata"]["hydraulic_ready"])

    def test_dry_and_actual_reverse_face_accounts(self):
        hierarchy = _m4_test_td_basin_storage_v6_full_build_basin_hierarchy(_m4_test_td_basin_storage_v6_full_make_td_source(_m4_test_td_basin_storage_v6_full_np.array([[2., 0.]]), spacing_m=1))
        dry_runoff = _m4_test_td_basin_storage_v6_full_RunoffParameters(initial_soil_mm=0)
        dry = _m4_test_td_basin_storage_v6_full_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v6_full_np.zeros(2), dt_s=10, runoff_parameters=dry_runoff, parameters={"substep_s": .25})
        self.assertEqual(dry["arrays"]["depth_m"].sum(), 0)
        self.assertEqual(dry["arrays"]["face_forward_m3"].sum(), 0)
        reverse = _m4_test_td_basin_storage_v6_full_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v6_full_np.zeros(2), dt_s=10,
            initial_depth_m=_m4_test_td_basin_storage_v6_full_np.array([[0., 4.]]), runoff_parameters=dry_runoff,
            parameters={"surface_evaporation_mm_h": 0, "substep_s": .25})
        self.assertGreater(reverse["arrays"]["face_reverse_m3"][0], 0)
        self.assertEqual(reverse["arrays"]["routed_volume_m3"][0], 0)
        self.assertLessEqual(reverse["arrays"]["active_reverse_s"][0], 20)
        self.assertLess(_m4_test_td_basin_storage_v6_full_audit_storage(reverse["arrays"], reverse["metadata"])["max_step_global_residual_m3"], 1e-9)

    def test_saved_storage_cold_read_no_compiled_exchange(self):
        hierarchy = _m4_test_td_basin_storage_v6_full_build_basin_hierarchy(_m4_test_td_basin_storage_v6_full_make_td_source(_m4_test_td_basin_storage_v6_full_np.array([[2., 0.]]), spacing_m=1))
        result = _m4_test_td_basin_storage_v6_full_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v6_full_np.array([30., 0.]), dt_s=60, parameters={"substep_s": .25})
        with _m4_test_td_basin_storage_v6_full_tempfile.TemporaryDirectory() as directory:
            path = _m4_test_td_basin_storage_v6_full_Path(directory) / "storage.npz"
            _m4_test_td_basin_storage_v6_full_save_storage(path, result)
            with _m4_test_td_basin_storage_v6_full_patch('terrain_pipeline.basin_storage.exchange_strang_scalar_sweep', side_effect=AssertionError("no advance")):
                loaded = _m4_test_td_basin_storage_v6_full_load_storage(path, expected_sha256=_m4_test_td_basin_storage_v6_full_file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            code = 'import sys\nfrom terrain_pipeline.basin_storage import storagev6_load_storage as load_storage\nload_storage(sys.argv[1], expected_sha256=sys.argv[2], expected_identity=sys.argv[3])\nassert \'terrain_pipeline.td_basin_storage_v4\' not in sys.modules\nassert \'terrain_pipeline.td_basin_storage_v6\' not in sys.modules\nassert \'terrain_pipeline.td_basin_transport_v6\' not in sys.modules\nassert "terrain_pipeline.basin_storage" in sys.modules\n'
            completed = _m4_test_td_basin_storage_v6_full_subprocess.run([_m4_test_td_basin_storage_v6_full_sys.executable, "-c", code, str(path), _m4_test_td_basin_storage_v6_full_file_sha256(path), result["identity_sha256"]],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_constant_source_full_solver_second_order(self):
        bed = _m4_test_td_basin_storage_v6_full_np.array([[0., 0.]])
        hierarchy = _m4_test_td_basin_storage_v6_full_build_basin_hierarchy(_m4_test_td_basin_storage_v6_full_make_td_source(bed, spacing_m=30))
        initial = _m4_test_td_basin_storage_v6_full_np.array([[1., .2]])
        source = _m4_test_td_basin_storage_v6_full_np.array([.03 / 3600, .01 / 3600])
        rain = _m4_test_td_basin_storage_v6_full_np.array([[[30., 10.]]])
        runoff = _m4_test_td_basin_storage_v6_full_RunoffParameters(initial_soil_mm=0, potential_et_mm_h=0, percolation_mm_h=0,
                                   infiltration_capacity_mm_h=0)

        def ode(time, depth):
            flow = .6 / 30 * (depth[0] - depth[1])
            return source + _m4_test_td_basin_storage_v6_full_np.array([-flow, flow])

        reference = _m4_test_td_basin_storage_v6_full_solve_ivp(ode, (0, 300), initial.ravel(), method="DOP853", rtol=1e-12, atol=1e-13).y[:, -1]
        errors = []
        for step in (5., 2.5, 1.25, .625):
            result = _m4_test_td_basin_storage_v6_full_simulate_basin_storage(hierarchy, rain, dt_s=300, initial_depth_m=initial,
                runoff_parameters=runoff, parameters={"substep_s": step, "surface_evaporation_mm_h": 0})
            errors.append(float(abs(result["arrays"]["depth_m"][-1] - reference).max()))
        self.assertTrue(all(errors[index] > 3.8 * errors[index + 1] for index in range(3)))
        self.assertLess(errors[-1], 1e-6)

# --- tests/test_td_basin_storage_v7.py:25 ---
class BasinStorageProfile7SymmetricForcingTests(_m4_test_td_basin_storage_v7_unittest.TestCase):
    def test_cold_cfl_metadata_cannot_be_forged(self):
        hierarchy = _m4_test_td_basin_storage_v7_build_basin_hierarchy(_m4_test_td_basin_storage_v7_make_td_source(_m4_test_td_basin_storage_v7_np.zeros((2, 2)), spacing_m=30))
        result = _m4_test_td_basin_storage_v7_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v7_np.zeros(1), dt_s=10)
        metadata = {**result["metadata"], "positivity_cfl": .99}
        forged = {**result, "metadata": metadata, "identity_sha256": _m4_test_td_basin_storage_v7_identity(result["arrays"], metadata)}
        with self.assertRaisesRegex(ValueError, "CFL"):
            _m4_test_td_basin_storage_v7_validate_saved_storage(forged)

    def test_full_solver_water_accounts_and_activity(self):
        hierarchy = _m4_test_td_basin_storage_v7_build_basin_hierarchy(_m4_test_td_basin_storage_v7_make_td_source(_m4_test_td_basin_storage_v7_np.array([[0., 2., 1.], [3., 4., 0.]]), spacing_m=1))
        for rain in (_m4_test_td_basin_storage_v7_np.array([30., 0.]), _m4_test_td_basin_storage_v7_np.zeros(2)):
            result = _m4_test_td_basin_storage_v7_simulate_basin_storage(hierarchy, rain, dt_s=60,
                initial_depth_m=_m4_test_td_basin_storage_v7_np.array([[1., 0., .5], [0., 0., 1.]]), parameters={"substep_s": .25})
            audit = _m4_test_td_basin_storage_v7_audit_storage(result["arrays"], result["metadata"])
            self.assertLess(audit["max_step_global_residual_m3"], 1e-8)
            self.assertTrue(_m4_test_td_basin_storage_v7_np.all(result["arrays"]["depth_m"] >= 0))
            self.assertFalse(result["metadata"]["hydraulic_ready"])

    def test_dry_and_actual_reverse_face_accounts(self):
        hierarchy = _m4_test_td_basin_storage_v7_build_basin_hierarchy(_m4_test_td_basin_storage_v7_make_td_source(_m4_test_td_basin_storage_v7_np.array([[2., 0.]]), spacing_m=1))
        dry_runoff = _m4_test_td_basin_storage_v7_RunoffParameters(initial_soil_mm=0)
        dry = _m4_test_td_basin_storage_v7_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v7_np.zeros(2), dt_s=10, runoff_parameters=dry_runoff, parameters={"substep_s": .25})
        self.assertEqual(dry["arrays"]["depth_m"].sum(), 0)
        self.assertEqual(dry["arrays"]["face_forward_m3"].sum(), 0)
        reverse = _m4_test_td_basin_storage_v7_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v7_np.zeros(2), dt_s=10,
            initial_depth_m=_m4_test_td_basin_storage_v7_np.array([[0., 4.]]), runoff_parameters=dry_runoff,
            parameters={"surface_evaporation_mm_h": 0, "substep_s": .25})
        self.assertGreater(reverse["arrays"]["face_reverse_m3"][0], 0)
        self.assertEqual(reverse["arrays"]["routed_volume_m3"][0], 0)
        self.assertLessEqual(reverse["arrays"]["active_reverse_s"][0], 20)
        self.assertLess(_m4_test_td_basin_storage_v7_audit_storage(reverse["arrays"], reverse["metadata"])["max_step_global_residual_m3"], 1e-9)

    def test_saved_storage_cold_read_no_compiled_exchange(self):
        hierarchy = _m4_test_td_basin_storage_v7_build_basin_hierarchy(_m4_test_td_basin_storage_v7_make_td_source(_m4_test_td_basin_storage_v7_np.array([[2., 0.]]), spacing_m=1))
        result = _m4_test_td_basin_storage_v7_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_v7_np.array([30., 0.]), dt_s=60, parameters={"substep_s": .25})
        with _m4_test_td_basin_storage_v7_tempfile.TemporaryDirectory() as directory:
            path = _m4_test_td_basin_storage_v7_Path(directory) / "storage.npz"
            _m4_test_td_basin_storage_v7_save_storage(path, result)
            with _m4_test_td_basin_storage_v7_patch('terrain_pipeline.basin_storage.exchange_strang_scalar_sweep', side_effect=AssertionError("no advance")):
                loaded = _m4_test_td_basin_storage_v7_load_storage(path, expected_sha256=_m4_test_td_basin_storage_v7_file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            code = 'import sys\nfrom terrain_pipeline.basin_storage import storagev7_load_storage as load_storage\nload_storage(sys.argv[1], expected_sha256=sys.argv[2], expected_identity=sys.argv[3])\nassert \'terrain_pipeline.td_basin_storage_v4\' not in sys.modules\nassert \'terrain_pipeline.td_basin_storage_v7\' not in sys.modules\nassert \'terrain_pipeline.td_basin_transport_v6\' not in sys.modules\nassert "terrain_pipeline.basin_storage" in sys.modules\n'
            completed = _m4_test_td_basin_storage_v7_subprocess.run([_m4_test_td_basin_storage_v7_sys.executable, "-c", code, str(path), _m4_test_td_basin_storage_v7_file_sha256(path), result["identity_sha256"]],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_constant_source_full_solver_second_order(self):
        bed = _m4_test_td_basin_storage_v7_np.array([[0., 0.]])
        hierarchy = _m4_test_td_basin_storage_v7_build_basin_hierarchy(_m4_test_td_basin_storage_v7_make_td_source(bed, spacing_m=30))
        initial = _m4_test_td_basin_storage_v7_np.array([[1., .2]])
        source = _m4_test_td_basin_storage_v7_np.array([.03 / 3600, .01 / 3600])
        rain = _m4_test_td_basin_storage_v7_np.array([[[30., 10.]]])
        runoff = _m4_test_td_basin_storage_v7_RunoffParameters(initial_soil_mm=0, potential_et_mm_h=0, percolation_mm_h=0,
                                   infiltration_capacity_mm_h=0)

        def ode(time, depth):
            flow = .6 / 30 * (depth[0] - depth[1])
            return source + _m4_test_td_basin_storage_v7_np.array([-flow, flow])

        reference = _m4_test_td_basin_storage_v7_solve_ivp(ode, (0, 300), initial.ravel(), method="DOP853", rtol=1e-12, atol=1e-13).y[:, -1]
        errors = []
        for step in (5., 2.5, 1.25, .625):
            result = _m4_test_td_basin_storage_v7_simulate_basin_storage(hierarchy, rain, dt_s=300, initial_depth_m=initial,
                runoff_parameters=runoff, parameters={"substep_s": step, "surface_evaporation_mm_h": 0})
            errors.append(float(abs(result["arrays"]["depth_m"][-1] - reference).max()))
        self.assertTrue(all(errors[index] > 3.8 * errors[index + 1] for index in range(3)))
        self.assertLess(errors[-1], 1e-6)

# --- tests/test_td_basin_storage_v10.py:20 ---
class BasinStorageProfile10V10Tests(_m4_test_td_basin_storage_v10_unittest.TestCase):
    def test_spatial_24h_two_steps_and_exact_restart(self):
        hierarchy = _m4_test_td_basin_storage_v10_build_basin_hierarchy(_m4_test_td_basin_storage_v10_make_td_source(_m4_test_td_basin_storage_v10_np.array([[2., 0.], [1., 0.]]), spacing_m=30))
        rain = _m4_test_td_basin_storage_v10_np.zeros((24, 2, 2))
        rain[:6] = _m4_test_td_basin_storage_v10_np.array([[2.288880014936935, 30.], [15., .15]])
        final = []
        with _m4_test_td_basin_storage_v10_tempfile.TemporaryDirectory() as temporary:
            for step in (2.5, 1.25):
                direct = None
                reloaded = None
                for hour in range(24):
                    result = _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, rain, substep_s=step, checkpoint=direct)
                    resumed = _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, rain, substep_s=step, checkpoint=reloaded)
                    _m4_test_td_basin_storage_v10_validate_native_v10_accounts(result['storage'], hierarchy=hierarchy, rain_mm_h=rain[hour])
                    for role in ('storage', 'checkpoint'):
                        for key in result[role]['arrays']:
                            _m4_test_td_basin_storage_v10_np.testing.assert_array_equal(result[role]['arrays'][key], resumed[role]['arrays'][key])
                    direct = result['checkpoint']
                    path = _m4_test_td_basin_storage_v10_Path(temporary)/f'{step}-{hour}.npz'
                    _m4_test_td_basin_storage_v10_save_checkpoint(path, direct)
                    reloaded = _m4_test_td_basin_storage_v10_load_checkpoint(path, expected_sha256=_m4_test_td_basin_storage_v10_file_sha256(path), expected_identity=direct['identity_sha256'])
                    self.assertLess(abs(result['storage']['arrays']['balance_residual_m3'].sum()), 1e-6)
                final.append(direct['arrays']['depth_m'])
        self.assertLess(_m4_test_td_basin_storage_v10_np.max(abs(final[0]-final[1])), .001)

    def test_negative_forcing_checkpoint_and_rehashed_cfl(self):
        valid = _m4_test_td_basin_storage_v10_np.array([[True, False], [True, True]])
        hierarchy = _m4_test_td_basin_storage_v10_build_basin_hierarchy(_m4_test_td_basin_storage_v10_make_td_source(_m4_test_td_basin_storage_v10_np.zeros((2,2)), spacing_m=30, valid_mask=valid))
        rain = _m4_test_td_basin_storage_v10_np.zeros((24,2,2))
        result = _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, rain, substep_s=2.5)
        bad_rain = rain.copy(); bad_rain[23,0,0] = _m4_test_td_basin_storage_v10_np.nan
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, bad_rain, substep_s=2.5)
        different = rain.copy(); different[23,0,0] = 1
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, different, substep_s=2.5, checkpoint=result['checkpoint'])
        arrays = dict(result['checkpoint']['arrays'])
        arrays['error_depth'] = arrays['error_depth'].copy(); arrays['error_depth'][1] = -1
        forged = {'arrays':arrays,'metadata':result['checkpoint']['metadata'], 'identity_sha256':_m4_test_td_basin_storage_v10_identity(arrays,result['checkpoint']['metadata'])}
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, rain, substep_s=2.5, checkpoint=forged)
        page = result['storage']
        metadata = {**page['metadata'], 'positivity_cfl':float('nan')}
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_v10_validate_storage({'arrays':page['arrays'],'metadata':metadata,'identity_sha256':_m4_test_td_basin_storage_v10_identity(page['arrays'],metadata)})
        metadata = {**page['metadata'], 'substeps':720, 'substep_s':5.}
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_v10_validate_storage({'arrays':page['arrays'],'metadata':metadata,'identity_sha256':_m4_test_td_basin_storage_v10_identity(page['arrays'],metadata)})

    def test_fresh_cold_io_does_not_import_solver(self):
        hierarchy = _m4_test_td_basin_storage_v10_build_basin_hierarchy(_m4_test_td_basin_storage_v10_make_td_source(_m4_test_td_basin_storage_v10_np.zeros((2,2)), spacing_m=30))
        result = _m4_test_td_basin_storage_v10_simulate_hour(hierarchy, _m4_test_td_basin_storage_v10_np.zeros((24,2,2)), substep_s=2.5)
        with _m4_test_td_basin_storage_v10_tempfile.TemporaryDirectory() as temporary:
            path=_m4_test_td_basin_storage_v10_Path(temporary)/'page.npz';_m4_test_td_basin_storage_v10_save_storage(path,result['storage'])
            code = (f"""import sys; from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage; load_storage({str(path)!r},expected_sha256={_m4_test_td_basin_storage_v10_file_sha256(path)!r},expected_identity={result['storage']['identity_sha256']!r}); assert "terrain_pipeline.basin_storage" in sys.modules; assert "terrain_pipeline.td_basin_storage_v10" not in sys.modules; assert "terrain_pipeline.td_basin_transport_v6" not in sys.modules""")
            _m4_test_td_basin_storage_v10_subprocess.run([_m4_test_td_basin_storage_v10_sys.executable,'-c',code],check=True)
