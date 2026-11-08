"""Unit tests for the integrated reduced channel-tree delta model.

These tests build small synthetic geometries that mirror the real trunk/
branch tree (two junctions, three sea outlets) and check:

  * exact solid closure,
  * zero-Q escrow and wet release,
  * zero solid no bed change,
  * stage response to changed Q,
  * branch bed share response to changed Q,
  * wet land deposition when inundated,
  * deterministic and source input unchanged.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_integrated_delta import (
    IntegratedDeltaConfig,
    build_channel_tree,
    integrated_solid_ledger,
    run_integrated_delta,
)


def synthetic_scene() -> dict:
    rows = cols = 128
    spacing = 100.0
    origin = np.array([0.0, 0.0])
    # West-to-east sloping bed; a small land band above sea level, then ocean.
    x = np.arange(cols) * spacing
    z = np.arange(rows) * spacing
    gx, gz = np.meshgrid(x, z, indexing="xy")
    bed = 0.2 - gx / 4000.0

    apex = np.array([100.0, 6400.0])
    mouth = np.array([12000.0, 6400.0])
    # Trunk runs east along z=6400.
    trunk = np.column_stack([
        np.linspace(apex[0], 6400.0, 65),
        np.full(65, apex[1]),
    ])
    # Branch 0 leaves at junction1 to the south.
    j1 = trunk[32]
    branch0 = np.column_stack([
        np.linspace(j1[0], 11200.0, 33),
        j1[1] + np.linspace(0.0, 2000.0, 33),
    ])
    # Branches 1 and 2 leave junction2 (mid trunk) to the northeast/southeast.
    j2 = trunk[48]
    branch1 = np.column_stack([
        np.linspace(j2[0], 11800.0, 33),
        j2[1] + np.linspace(0.0, -1600.0, 33),
    ])
    branch2 = np.column_stack([
        np.linspace(j2[0], 11600.0, 33),
        j2[1] + np.linspace(0.0, 1600.0, 33),
    ])
    branches = np.stack([branch0, branch1, branch2], axis=0)
    # Carve finite-width channels all the way through the actual coastline.
    from scipy.spatial import cKDTree
    samples = np.vstack([trunk, *branches])
    distance = cKDTree(samples).query(np.column_stack([gx.ravel(), gz.ravel()]))[0].reshape(bed.shape)
    bed[distance <= 180.] = (-1.0 - gx/10000.)[distance <= 180.]
    ocean = bed <= 0.0
    widths = np.array([120.0, 100.0, 80.0, 60.0])
    return {
        "bed": bed,
        "ocean": ocean,
        "origin": origin,
        "spacing": spacing,
        "apex": apex,
        "mouth": mouth,
        "trunk": trunk,
        "branches": branches,
        "widths": widths,
    }


def build_geometry(scene: dict) -> object:
    return build_channel_tree(
        initial_bed_m=scene["bed"],
        origin_xz=scene["origin"],
        spacing_m=scene["spacing"],
        mouth_xz=scene["mouth"],
        apex_xz=scene["apex"],
        trunk_path_xz=scene["trunk"],
        branch_paths_xz=[scene["branches"][i] for i in range(3)],
        widths_m=scene["widths"],
        ocean_mask=scene["ocean"],
        trunk_split_station=32,
        branch_split_station=48,
        eligible_band_m=1500.0,
    )


def test_explicit_secondary_tree_positive_solid_and_escrow():
    bed = np.full((40, 40), -2.)
    trunk = np.column_stack([np.arange(2., 16.)*20., np.full(14, 400.)])
    parent = np.column_stack([np.arange(15., 36.)*20., np.full(21, 400.)])
    secondary = np.column_stack([np.linspace(500., 700., 12), np.linspace(400., 600., 12)])
    geometry = build_channel_tree(bed, [0., 0.], 20., trunk[-1], trunk[0], trunk,
        [parent, secondary], [80., 60., 30.], ocean_mask=np.zeros_like(bed, bool),
        branch_parent_index=[-1, 0], protected_band_m=0.)
    assert len(geometry.paths) == 4
    child = geometry.paths['terminal1']
    assert child.upstream == geometry.paths['terminal0'].upstream
    initial = bed.copy()
    result = run_integrated_delta(bed, geometry, np.array([0., 1000.]),
        np.array([10., 20.]), np.array([100., 100.]), IntegratedDeltaConfig())
    ledger = integrated_solid_ledger(result, np.array([10., 20.]))
    assert result['records'][0].escrow_solid_m3 == 10.
    assert np.isclose(ledger['input_solid_m3'], ledger['retained_solid_m3']+ledger['exported_solid_m3']+ledger['escrow_solid_m3'])
    assert np.sum(result['deposited_solid_m3']) > 0.
    assert np.max(result['final_bed_m']-initial) > 0.
    assert np.isclose(sum(result['records'][1].terminal_q_m3_s), 10.)
    assert np.issubdtype(result['final_heads_m'].dtype, np.number)


def test_explicit_tree_one_three_and_five_terminals_replay():
    bed = np.full((40, 40), -2.)
    trunk = np.column_stack([np.arange(2., 16.)*20., np.full(14, 400.)])
    for count in (1, 3, 5):
        branches = [np.column_stack([np.linspace(300., 700., 21),
            np.linspace(400., 250.+70.*i, 21)]) for i in range(count)]
        geometry = build_channel_tree(bed, [0., 0.], 20., trunk[-1], trunk[0], trunk,
            branches, [80.]+[40.]*count, ocean_mask=np.zeros_like(bed, bool),
            branch_parent_index=[-1]*count, protected_band_m=0.)
        assert all(name.startswith(('terminal', 'reach')) for name in geometry.paths)
        args = (bed, geometry, np.array([1000.]), np.array([20.]), np.array([100.]))
        first = run_integrated_delta(*args)
        replay = run_integrated_delta(*args)
        assert len(first['records'][0].terminal_q_m3_s) == count
        assert np.isclose(sum(first['records'][0].terminal_q_m3_s), 10.)
        for key in ('final_bed_m', 'monthly_terminal_export_solid_m3', 'monthly_node_heads_m'):
            assert np.array_equal(first[key], replay[key])


class IntegratedDeltaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = synthetic_scene()
        self.geometry = build_geometry(self.scene)
        self.config = IntegratedDeltaConfig()
        self.n_months = 3
        self.month_s = 30.0 * 86400.0

    # --- Closure and invariants ----------------------------------------

    def test_solid_closure(self):
        water = np.array([1.0e7, 1.5e7, 8.0e6])
        solid = np.array([1.0e4, 1.5e4, 8.0e3])
        dt = np.full(self.n_months, self.month_s)
        result = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        ledger = integrated_solid_ledger(result, solid)
        residual = (
            ledger["input_solid_m3"]
            - ledger["retained_solid_m3"]
            - ledger["exported_solid_m3"]
            - ledger["escrow_solid_m3"]
        )
        self.assertLess(abs(residual), 1.0e-8)
        for record in result["records"]:
            self.assertLess(abs(record.mass_error_m3), 1.e-8)

    def test_zero_solid_leaves_bed_unchanged(self):
        water = np.array([1.0e7, 1.0e7])
        solid = np.zeros(2)
        dt = np.full(2, self.month_s)
        result = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        self.assertTrue(np.array_equal(result["final_bed_m"], self.scene["bed"]))
        self.assertEqual(float(result["stored_solid_m3"].sum()), 0.0)

    def test_zero_q_escrow_and_release(self):
        # First month: no water -> incoming solid becomes escrow, no deposits.
        # Second month: plenty of water -> escrow released downstream.
        water = np.array([0.0, 1.0e8])
        solid = np.array([5.0e3, 0.0])
        dt = np.full(2, self.month_s)
        result = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        self.assertEqual(float(result["records"][0].export_solid_m3), 0.0)
        self.assertGreater(float(result["records"][0].escrow_solid_m3), 0.0)
        # Second month should release the escrow supply to some outlet.
        self.assertGreater(
            float(result["records"][1].export_solid_m3)
            + float(result["stored_solid_m3"].sum()),
            0.0,
        )

    # --- Controls -------------------------------------------------------

    def test_higher_q_raises_stage(self):
        dt = np.full(1, self.month_s)
        low = run_integrated_delta(
            self.scene["bed"], self.geometry,
            np.array([5.0e5]), np.zeros(1), dt, self.config,
        )
        high = run_integrated_delta(
            self.scene["bed"], self.geometry,
            np.array([5.0e6]), np.zeros(1), dt, self.config,
        )
        self.assertGreater(
            high["records"][0].head_source_m,
            low["records"][0].head_source_m,
        )
        self.assertGreater(
            high["records"][0].head_junction1_m,
            low["records"][0].head_junction1_m,
        )

    def test_branch_bed_share_responds_to_q(self):
        dt = np.full(1, self.month_s)
        water = np.array([5.0e6])
        solid = np.array([5.0e3])
        baseline = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        bed = self.scene["bed"].copy()
        # Raise bed along branch0 -> it carries less water and deposits less.
        for pt in self.geometry.paths["branch0"].points_xz[2:-2]:
            c = int(round((pt[0] - self.scene["origin"][0]) / self.scene["spacing"]))
            r = int(round((pt[1] - self.scene["origin"][1]) / self.scene["spacing"]))
            if 0 <= r < bed.shape[0] and 0 <= c < bed.shape[1]:
                bed[r, c] += 0.5
        raised = run_integrated_delta(
            bed, self.geometry, water, solid, dt, self.config,
        )
        self.assertLess(
            float(raised["records"][0].q_branch0_m3_s),
            float(baseline["records"][0].q_branch0_m3_s),
        )

    def test_wet_land_deposition_when_inundated(self):
        water = np.array([5.0e8])
        solid = np.array([5.0e4])
        dt = np.full(1, self.month_s)
        result = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        bed = self.scene["bed"]
        land = bed > 0.0
        deposits_on_land = float(result["stored_solid_m3"][land].sum())
        # With a large incoming solid supply and shallow land headroom, at
        # least some deposit should end up on the original land surface.
        self.assertGreater(deposits_on_land, 0.0)
        self.assertTrue(np.all(result["wet_timeseries"][0][land & (result["stored_solid_m3"] > 0.)]))

    # --- Determinism and source invariance ------------------------------

    def test_determinism(self):
        water = np.array([1.0e7, 1.2e7])
        solid = np.array([1.0e4, 1.1e4])
        dt = np.full(2, self.month_s)
        a = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        b = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        self.assertTrue(np.array_equal(a["final_bed_m"], b["final_bed_m"]))
        self.assertEqual(
            a["cumulative_export_solid_m3"], b["cumulative_export_solid_m3"],
        )

    def test_source_bed_unchanged(self):
        bed = self.scene["bed"].copy()
        water = np.array([1.0e7])
        solid = np.array([1.0e4])
        dt = np.full(1, self.month_s)
        run_integrated_delta(
            bed, self.geometry, water, solid, dt, self.config,
        )
        self.assertTrue(np.array_equal(bed, self.scene["bed"]))

    def test_protected_and_store_height_contract(self):
        protected = self.geometry.protected_mask.copy()
        self.geometry.eligible_mask[:, :10] = False
        self.geometry.protected_mask[:, :10] = True
        result = run_integrated_delta(self.scene["bed"], self.geometry,
            np.array([5.e8]), np.array([5.e4]), np.array([self.month_s]), self.config)
        self.assertTrue(np.array_equal(result["final_bed_m"][self.geometry.protected_mask], self.scene["bed"][self.geometry.protected_mask]))
        expected = self.scene["bed"]+result["stored_solid_m3"]/(self.scene["spacing"]**2*(1.-self.config.porosity))
        self.assertTrue(np.array_equal(result["final_bed_m"], expected))
        self.assertTrue(np.allclose(result["deposited_solid_m3"]-result["reentrained_solid_m3"], result["stored_solid_m3"], rtol=1.e-12, atol=1.e-12))

    def test_junction_and_final_wet_continuity(self):
        from terrain_pipeline.surface_rivers.metric_integrated_delta import wet_continuity_from_apex
        result = run_integrated_delta(self.scene["bed"], self.geometry,
            np.array([5.e8]), np.array([5.e4]), np.array([self.month_s]), self.config)
        r = result["records"][0]
        self.assertAlmostEqual(r.q_trunk0_m3_s, 5.e8/self.month_s, places=7)
        self.assertAlmostEqual(r.q_trunk0_m3_s, r.q_branch0_m3_s+r.q_trunk1_m3_s, places=7)
        self.assertAlmostEqual(r.q_trunk1_m3_s, r.q_branch1_m3_s+r.q_branch2_m3_s, places=7)
        self.assertTrue(wet_continuity_from_apex(result, self.geometry))

    def test_isolated_pool_stays_dry(self):
        from terrain_pipeline.surface_rivers.metric_integrated_delta import _compute_stage_raster
        bed = np.full_like(self.scene["bed"], 10.)
        # Apex and a separate low pool have the same candidate head, but the
        # pool has neither an inlet connection nor a sea connection.
        cc, rr = np.rint(self.scene["apex"]/self.scene["spacing"]).astype(int)
        bed[rr, cc] = -1.
        bed[rr+5:rr+7, cc+5:cc+7] = -1.
        heads = {name:(1.,1.) for name in self.geometry.paths}
        _, depth = _compute_stage_raster(bed, self.geometry, heads,
            np.ones_like(bed, bool), np.zeros_like(bed, bool), 0.)
        self.assertEqual(float(depth[rr+5:rr+7, cc+5:cc+7].sum()), 0.)

    def test_raised_junction_does_not_choose_dry_root(self):
        bed = self.scene["bed"].copy()
        cc, rr = np.rint(self.geometry.junction_2_xz/self.scene["spacing"]).astype(int)
        bed[rr, cc] = 0.05
        result = run_integrated_delta(bed, self.geometry, np.array([5.e8]),
            np.array([0.]), np.array([self.month_s]), self.config)
        record = result["records"][0]
        self.assertGreater(record.q_branch1_m3_s, 0.)
        self.assertGreater(record.q_branch2_m3_s, 0.)
        self.assertGreater(record.head_junction2_m, bed[rr, cc])

    def test_geometries_are_connected(self):
        paths = self.geometry.paths
        self.assertTrue(np.allclose(
            paths["trunk0"].points_xz[-1], self.geometry.junction_1_xz,
        ))
        self.assertTrue(np.allclose(
            paths["trunk1"].points_xz[0], self.geometry.junction_1_xz,
        ))
        self.assertTrue(np.allclose(
            paths["trunk1"].points_xz[-1], self.geometry.junction_2_xz,
        ))
        self.assertTrue(np.allclose(
            paths["branch0"].points_xz[0], self.geometry.junction_1_xz,
        ))
        self.assertTrue(np.allclose(
            paths["branch1"].points_xz[0], self.geometry.junction_2_xz,
        ))
        self.assertTrue(np.allclose(
            paths["branch2"].points_xz[0], self.geometry.junction_2_xz,
        ))

    def test_mannning_resistance_positive_for_flowing_reach(self):
        from terrain_pipeline.surface_rivers.metric_integrated_delta import (
            manning_resistance_integral,
        )
        s = np.linspace(0.0, 1000.0, 11)
        h = np.full_like(s, 2.0)
        value = manning_resistance_integral(s, h, 100.0, 0.035)
        self.assertGreater(value, 0.0)
        self.assertTrue(math.isfinite(value))

    def test_zero_q_has_no_wet_head(self):
        water = np.zeros(1)
        solid = np.array([1.0e3])
        dt = np.full(1, self.month_s)
        result = run_integrated_delta(
            self.scene["bed"], self.geometry, water, solid, dt, self.config,
        )
        self.assertEqual(float(result["records"][0].export_solid_m3), 0.0)
        self.assertEqual(float(result["stored_solid_m3"].sum()), 0.0)
        self.assertGreater(float(result["records"][0].escrow_solid_m3), 0.0)


if __name__ == "__main__":
    unittest.main()

