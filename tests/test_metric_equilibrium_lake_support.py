import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_equilibrium_lake_support import (
    EquilibriumLakeConfig, EquilibriumLakeForcing, advance_equilibrium_lakes,
    load_equilibrium_lakes, project_equilibrium_lakes, save_equilibrium_lakes,
    solve_equilibrium_lakes, validate_equilibrium_lakes,
)
from terrain_pipeline.surface_rivers.metric_natural_lakes import build_natural_lakes, lake_volume_at_stage
from tests.test_metric_natural_lakes import two_lakes, two_saddles


def forcing(domain, *, duration=1., local=None, port=None):
    n = len(domain["arrays"]["seed_cell_ids"])
    return EquilibriumLakeForcing(
        np.array([0., duration]),
        np.array([np.zeros(n) if local is None else local], np.float64),
        np.zeros((1, len(domain["arrays"]["boundary_faces"]))),
        np.array([np.zeros(n) if port is None else port], np.float64),
        domain["metadata"]["source_identity_sha256"], "analytical local supply",
        "b" * 64, "externally supplied signed owner port rates")


def three_saddles():
    height = np.full((5, 9), 5., np.float64)
    height[2, 1:8] = [0., 1., 0., 2., 0., 1., 1.]
    terrain = TerrainGrid(height, np.ones_like(height, bool), 0., 0., 1., 1.,
                          "observed_dem", "two unequal original saddles", "a" * 64)
    owner = np.full(height.shape, -1, np.int64)
    owner[2, 1:3] = 0
    owner[2, 3:5] = 1
    owner[2, 5:8] = 2
    return build_natural_lakes(terrain, np.array([19, 21, 23], np.int64), owner,
        max_stage_m=np.full(3, 5.), boundary_faces=np.empty((0, 2), np.int64),
        boundary_kinds=np.empty(0, dtype="U16"), weir_coefficient_m3_s_m15=1.,
        source_provenance="analytical native beds", boundary_provenance="unresolved exterior")


def closed_capacity():
    height = np.array([[0., 1.], [1., 2.]], np.float64)
    terrain = TerrainGrid(height, np.ones_like(height, bool), 0., 0., 1., 1.,
                          "observed_dem", "closed finite support", "a" * 64)
    return build_natural_lakes(terrain, np.array([0], np.int64),
        np.zeros((2, 2), np.int64), max_stage_m=np.array([3.]),
        boundary_faces=np.array([[i, -1] for i in range(4)], np.int64),
        boundary_kinds=np.array(["closed"] * 4), weir_coefficient_m3_s_m15=1.,
        source_provenance="analytical native beds", boundary_provenance="closed perimeter")


class EquilibriumLakeSupportTests(unittest.TestCase):
    def test_unequal_saddles_merge_and_split_in_crest_order(self):
        domain = three_saddles()
        self.assertEqual(domain["arrays"]["internal_crest_m"].tolist(), [1., 2.])
        initial = np.array([lake_volume_at_stage(domain, i, 2.3) for i in range(3)])
        all_joined, _ = project_equilibrium_lakes(domain, initial)
        np.testing.assert_array_equal(all_joined.component_id, [0, 0, 0])
        middle = np.array([lake_volume_at_stage(domain, i, 1.5) for i in range(3)])
        partial, _ = project_equilibrium_lakes(domain, middle, all_joined.component_id)
        np.testing.assert_array_equal(partial.component_id, [0, 0, 1])
        low = np.array([lake_volume_at_stage(domain, i, .5) for i in range(3)])
        separate, _ = project_equilibrium_lakes(domain, low, partial.component_id)
        np.testing.assert_array_equal(separate.component_id, [0, 1, 2])
        self.assertAlmostEqual(separate.owner_volume_m3.sum(), low.sum(), places=10)

    def test_single_sided_saddle_stays_separate_then_merges_at_common_stage(self):
        domain = two_lakes()
        first = lake_volume_at_stage(domain, 0, 1.2)
        second = lake_volume_at_stage(domain, 1, .2)
        state, redistribution = project_equilibrium_lakes(domain, np.array([first, second]))
        np.testing.assert_array_equal(state.component_id, [0, 1])
        np.testing.assert_array_equal(redistribution, [0., 0.])
        raw = np.array([lake_volume_at_stage(domain, i, level)
                        for i, level in enumerate((1.4, 1.1))])
        joined, redistribution = project_equilibrium_lakes(domain, raw)
        np.testing.assert_array_equal(joined.component_id, [0, 0])
        self.assertAlmostEqual(joined.owner_volume_m3.sum(), raw.sum(), places=10)
        from terrain_pipeline.surface_rivers.metric_equilibrium_lake_support import _geometry
        stages = _geometry(domain, joined.owner_volume_m3)[1]
        self.assertAlmostEqual(stages[0], stages[1], places=9)
        self.assertAlmostEqual(redistribution.sum(), 0., places=10)
        self.assertGreater(abs(redistribution[0]), 0.)
        self.assertEqual(joined.component_id.tolist(), [0, 0])

    def test_multi_saddle_wet_dry_split_and_native_prism_volume(self):
        domain = two_saddles()
        raw = np.array([lake_volume_at_stage(domain, i, 1.4) for i in range(2)])
        state, _ = project_equilibrium_lakes(domain, raw)
        np.testing.assert_array_equal(state.component_id, [0, 0])
        draw = forcing(domain, duration=.1, port=np.array([-150., 0.]))
        trace = solve_equilibrium_lakes(domain, draw, raw,
                                        EquilibriumLakeConfig(max_dt_seconds=.001))
        self.assertEqual(trace["metadata"]["status"], "complete")
        a = trace["arrays"]
        self.assertAlmostEqual(a["trace_owner_volume_m3"][-1].sum(), raw.sum() - 15., places=8)
        self.assertEqual(a["trace_component_id"][0].tolist(), [0, 0])
        self.assertEqual(a["trace_component_id"][-1].tolist(), [0, 1])
        self.assertTrue(np.all(a["trace_owner_volume_m3"] >= 0.))
        self.assertLess(a["trace_wet_support"][-1].sum(), a["trace_wet_support"][0].sum())
        owner = domain["arrays"]["owner_grid"].ravel()
        for step, paired in enumerate(a["step_redistribution_face_m3"]):
            by_owner = np.zeros(2)
            for amount, (left, right) in zip(paired, domain["arrays"]["internal_faces"]):
                by_owner[owner[left]] -= amount
                by_owner[owner[right]] += amount
            np.testing.assert_allclose(by_owner, a["step_redistribution_m3"][step], atol=1e-9)
        self.assertTrue(validate_equilibrium_lakes(trace))

    def test_merged_common_stage_ode_and_split_event_refinement(self):
        domain = two_saddles()
        raw = np.array([lake_volume_at_stage(domain, i, 1.4) for i in range(2)])
        drive = forcing(domain, duration=.1, port=np.array([-150., 0.]))
        traces = [solve_equilibrium_lakes(domain, drive, raw,
                   EquilibriumLakeConfig(max_dt_seconds=dt)) for dt in (.025, .001)]
        for trace in traces:
            self.assertEqual(trace["metadata"]["status"], "complete")
            a = trace["arrays"]
            crossing = np.flatnonzero((a["trace_component_id"][:, 0] ==
                                       a["trace_component_id"][:, 1]) &
                                      np.isclose(a["trace_owner_stage_m"][:, 0], 1., atol=1e-9))
            self.assertTrue(len(crossing))
            event = int(crossing[-1])
            self.assertAlmostEqual(a["time_seconds"][event], .096, places=7)
            np.testing.assert_allclose(a["trace_owner_volume_m3"][event], [12., 12.], atol=1e-7)
            np.testing.assert_allclose(a["trace_owner_volume_m3"][-1], [11.4, 12.], atol=1e-7)
            self.assertEqual(a["trace_component_id"][-1].tolist(), [0, 1])
            # Independent exact merged-pool ODE: 36 dh/dt = -150 between h=1 and 2.
            sample = np.argmin(abs(a["time_seconds"] - .075))
            self.assertAlmostEqual(a["trace_owner_stage_m"][sample, 0],
                                   1.4 - 150. * a["time_seconds"][sample] / 36., places=7)

    def test_independent_weir_ode_refinement_and_paired_projection(self):
        domain = two_lakes()
        initial = np.array([lake_volume_at_stage(domain, 0, 1.2), 0.])
        drive = forcing(domain, duration=.2)
        coarse = solve_equilibrium_lakes(domain, drive, initial,
                                          EquilibriumLakeConfig(max_dt_seconds=.05))
        fine = solve_equilibrium_lakes(domain, drive, initial,
                                        EquilibriumLakeConfig(max_dt_seconds=.001))
        self.assertEqual(coarse["metadata"]["status"], "complete")
        self.assertEqual(fine["metadata"]["status"], "complete")
        def stage0(v):
            return v / 6. if v <= 6. else (v / 6. + 1.) / 2.
        def rhs(_, y):
            q = max(stage0(y[0]) - 1., 0.) ** 1.5
            return [-q, q]
        reference = solve_ivp(rhs, (0., .2), initial, rtol=1e-12, atol=1e-12).y[:, -1]
        c_error = np.max(abs(coarse["arrays"]["trace_owner_volume_m3"][-1] - reference))
        f_error = np.max(abs(fine["arrays"]["trace_owner_volume_m3"][-1] - reference))
        self.assertLess(f_error, c_error / 5.)
        self.assertTrue(np.allclose(fine["arrays"]["step_redistribution_m3"].sum(axis=1), 0., atol=1e-10))
        self.assertTrue(np.allclose(fine["arrays"]["step_redistribution_face_m3"].sum(axis=1), 0., atol=1e-10))

    def test_unknown_exterior_failure_and_cold_rehashed_forgery(self):
        domain = two_lakes(unknown=True)
        result = solve_equilibrium_lakes(domain, forcing(domain, duration=10., local=np.array([100., 0.])),
                                          np.zeros(2), EquilibriumLakeConfig(max_dt_seconds=.1,
                                                                             min_dt_seconds=1e-6))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertLess(result["arrays"]["time_seconds"][-1], 10.)
        self.assertTrue(validate_equilibrium_lakes(result))
        for field in ("trace_owner_volume_m3", "trace_component_id", "trace_wet_support",
                      "step_redistribution_m3"):
            forged = deepcopy(result)
            value = forged["arrays"][field].copy()
            if value.dtype == bool:
                value[-1, 0] ^= True
            else:
                value[-1, 0] += 1
            forged["arrays"][field] = value
            forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_equilibrium_lakes(forged)

    def test_finite_capacity_failure_and_signed_port_inventory(self):
        domain = closed_capacity()
        result = solve_equilibrium_lakes(domain,
            forcing(domain, duration=10., local=np.array([100.])),
            np.zeros(1), EquilibriumLakeConfig(max_dt_seconds=.1, min_dt_seconds=1e-6))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertIn("support", result["metadata"]["failure_reason"])
        self.assertTrue(validate_equilibrium_lakes(result))
        domain = two_lakes()
        drive = forcing(domain, duration=.5, port=np.array([1., 0.]))
        entered = solve_equilibrium_lakes(domain, drive, np.zeros(2),
            EquilibriumLakeConfig(max_dt_seconds=.01))
        self.assertAlmostEqual(entered["arrays"]["trace_owner_volume_m3"][-1].sum(), .5, places=9)
        leaving = solve_equilibrium_lakes(domain,
            forcing(domain, duration=.5, port=np.array([-.5, 0.])),
            np.array([.5, 0.]), EquilibriumLakeConfig(max_dt_seconds=.01))
        self.assertAlmostEqual(leaving["arrays"]["trace_owner_volume_m3"][-1].sum(), .25, places=9)

    def test_roundtrip_and_source_pin(self):
        domain = two_lakes()
        drive = forcing(domain)
        result = solve_equilibrium_lakes(domain, drive, np.zeros(2))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "equilibrium.npz"
            save_equilibrium_lakes(path, result)
            loaded = load_equilibrium_lakes(path, expected_sha256=file_sha256(path))
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
        bad = EquilibriumLakeForcing(drive.time_seconds, drive.local_q_m3_s,
            drive.tailwater_stage_m, drive.port_q_m3_s, "c" * 64, drive.provenance,
            drive.port_source_identity_sha256, drive.port_provenance)
        with self.assertRaisesRegex(ValueError, "forcing/source"):
            solve_equilibrium_lakes(domain, bad, np.zeros(2))


if __name__ == "__main__":
    unittest.main()
