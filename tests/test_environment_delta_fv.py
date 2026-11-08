"""Behavioral coverage for the persistent finite FV delta boundary."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_delta_fv import FVDeltaConfig, initialize, advance, save, load, query
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling_v4 import advance_growth


class FVDeltaTests(unittest.TestCase):
    def initial(self, **kwargs):
        bed = np.full((8, 10), -.5)
        ocean = np.ones(bed.shape, bool)
        ocean[:, -1] = False
        return initialize(bed, ocean, [45], origin_m_xz=[120., 240.],
            source_world_identity="seed20261020", source_identity="finite-engineering-bed",
            config=kwargs.pop("config", FVDeltaConfig(coupling_interval_s=2., max_hydro_dt_s=1.)), **kwargs)

    def records(self):
        return [{"id": str(i), "source": "declared finite test", "time_start_s": i*4.,
                 "time_end_s": (i+1)*4., "water_m3": 20., "solid_m3": .2} for i in range(2)]

    def test_cold_resume_matches_live_and_preserves_input(self):
        initial = self.initial()
        original = initial["arrays"]["bed_m"].copy()
        records = self.records()
        whole = advance(initial, records)
        first = advance(initial, records[:1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            save(path, first)
            restored = load(path, expected_sha256=file_sha256(path))
            resumed = advance(restored, records[1:])
        self.assertEqual(whole["identity_sha256"], resumed["identity_sha256"])
        np.testing.assert_array_equal(initial["arrays"]["bed_m"], original)
        self.assertGreater(whole["arrays"]["deposited_solid_m3"].sum(), 0.)
        self.assertEqual(whole["metadata"]["ledger"]["solid_input_m3"], .4)
        a = whole["arrays"]
        balance = np.zeros(80)
        balance[a["inlet_cells"]] = .4/len(a["inlet_cells"])
        transfer = a["internal_solid_transfer_m3"]
        np.add.at(balance, a["face_left"], -transfer)
        np.add.at(balance, a["face_right"], transfer)
        np.add.at(balance, a["boundary_cell"], -a["boundary_solid_transfer_m3"])
        balance -= a["fixed_marine_edge_export_solid_m3"]
        stock = ((a["bed_m"]-a["initial_bed_m"])*900.*.65+a["suspended_solid_m3"]).ravel()
        np.testing.assert_allclose(stock, balance, atol=1.e-9)
        self.assertNotIn("receiver", whole["arrays"])
        self.assertEqual(query(whole, 270., 360.)["physical_time_s"], 8.)

    def test_duplicate_or_gap_rejected_without_mutation(self):
        first = advance(self.initial(), self.records()[:1])
        with self.assertRaises(ValueError):
            advance(first, self.records()[:1])
        record = dict(self.records()[1], time_start_s=5.)
        with self.assertRaises(ValueError):
            advance(first, [record])
        self.assertEqual(first["metadata"]["physical_time_s"], 4.)

    def test_tidal_face_flux_reverses(self):
        cfg = FVDeltaConfig(coupling_interval_s=2., max_hydro_dt_s=1.,
                            tide_amplitude_m=.15, tide_period_s=16.)
        initial = self.initial(config=cfg)
        records = [{"id": str(i), "source": "finite tide scenario", "time_start_s": 4.*i,
                    "time_end_s": 4.*(i+1), "water_m3": 0., "solid_m3": 0.} for i in range(4)]
        result = advance(initial, records)
        signed = result["arrays"]["boundary_water_transfer_m3"]
        absolute = result["arrays"]["boundary_water_absolute_transfer_m3"]
        self.assertTrue(np.any(absolute > abs(signed)+1.e-6))
        self.assertGreater(result["metadata"]["ledger"]["sea_import_m3"], 0.)
        self.assertGreater(result["metadata"]["ledger"]["water_export_m3"], 0.)
        np.testing.assert_array_equal(result["arrays"]["bed_m"], initial["arrays"]["bed_m"])

    def test_morphology_refusal_retries_complete_step(self):
        cfg = FVDeltaConfig(coupling_interval_s=4., max_hydro_dt_s=1.,
            bedload=replace(FVDeltaConfig().bedload, max_bed_change_m=1.e-5),
            suspended=replace(FVDeltaConfig().suspended, max_bed_change_m=1.e-5))
        initial = self.initial(config=cfg)
        result = advance(initial, self.records()[:1])
        self.assertGreater(result["metadata"]["rejected_coupling_steps"], 0)
        self.assertAlmostEqual(result["metadata"]["ledger"]["solid_input_m3"], .2)

    def test_failed_advance_leaves_no_partial_state(self):
        cfg = FVDeltaConfig(coupling_interval_s=4., max_hydro_dt_s=1., max_halvings=0,
            bedload=replace(FVDeltaConfig().bedload, max_bed_change_m=1.e-8),
            suspended=replace(FVDeltaConfig().suspended, max_bed_change_m=1.e-8))
        initial = self.initial(config=cfg)
        before = initial["identity_sha256"]
        with self.assertRaises(ValueError):
            advance(initial, self.records())
        self.assertEqual(initial["identity_sha256"], before)
        self.assertEqual(initial["metadata"]["physical_time_s"], 0.)
        self.assertEqual(initial["metadata"]["consumed_forcing_ids"], [])

    def test_configured_roughness_reaches_water_solver(self):
        cfg = FVDeltaConfig(bedload=replace(FVDeltaConfig().bedload, manning_s_m_third=.065))
        with patch("terrain_pipeline.environment_delta_fv.advance_growth", wraps=advance_growth) as solver:
            result = advance(self.initial(config=cfg), self.records()[:1])
        self.assertTrue(solver.called)
        self.assertEqual(solver.call_args.kwargs["budget"].roughness_s_m_third, .065)
        self.assertEqual(result["arrays"]["fixed_marine_edge_export_solid_m3"].shape, (80,))

    def test_declared_obstacle_island_splits_and_rejoins_actual_flow(self):
        from tools.verify_delta_fv_bar_recession import island_rejoining_paths
        bed = np.full((20, 28), -.5)
        bed[:, 24:] = .8
        bed[9:12, 24:] = -.5
        bed[8:13, 11:15] = .5
        ocean = np.zeros_like(bed, bool)
        ocean[:, :24] = True
        initial = initialize(bed, ocean, [10*28+26], origin_m_xz=[0., 0.],
            source_world_identity="seed20261020", source_identity="declared-obstacle-island-control",
            config=FVDeltaConfig(coupling_interval_s=10., max_hydro_dt_s=3.))
        result = advance(initial, [{"id": "island-control", "source": "declared initial obstacle; not grown sediment",
            "time_start_s": 0., "time_end_s": 900., "water_m3": 9000., "solid_m3": 0.}])
        witness = island_rejoining_paths(result, source_q_m3_s=10.)
        self.assertTrue(witness["passed"], witness)
        island = next(record for record in witness["islands"] if record["rejoins"])
        north, south = island["north_path"], island["south_path"]
        self.assertEqual(north[0], south[0])
        self.assertEqual(north[-1], south[-1])
        self.assertTrue(any(cell//28 < 8 and 10 <= cell % 28 <= 15 for cell in north))
        self.assertTrue(any(cell//28 > 12 and 10 <= cell % 28 <= 15 for cell in south))
        self.assertGreater(island["north_gate_q_m3_s"], .1)
        self.assertGreater(island["south_gate_q_m3_s"], .1)
        np.testing.assert_array_equal(result["arrays"]["bed_m"], bed)


if __name__ == "__main__":
    unittest.main()
