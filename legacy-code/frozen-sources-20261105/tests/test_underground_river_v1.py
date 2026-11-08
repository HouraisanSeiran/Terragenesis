"""Small synthetic Boolean cases; no old solver or independent audit runs."""

from copy import deepcopy
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".scratch/hybrid-river-network/python-deps"))

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import Parameters as CaveParameters, build_charts, build_rock
from terrain_pipeline.hybrid_river_graph import identity
from terrain_pipeline.underground_river_v1 import Parameters, build_preview, deform_charts
from tools.prepare_underground_river_v1 import prepare


def port_at(z_m):
    profile = [[2., 0., z_m], [1., 0., z_m], [-1., 0., z_m], [-2., 0., z_m]]
    return {"status": "candidate", "rejection_reasons": [], "flow_unit_xz": [0., 1.],
        "profile": {"profile_xyz_m": profile, "profile_segments": [
            {"profile_segment_index": ordinal, "points_xyz_m": [first, second],
             "native_pieces": [{"interval_t01": [0., 1.], "start_xz_m": [first[0], z_m],
                "end_xz_m": [second[0], z_m], "depth_coefficients_m_t01": [0., 0.],
                "source": {"source_coefficients_m_t012": [0., 0., 0.]}}]}
            for ordinal, (first, second) in enumerate(zip(profile, profile[1:]))]}}


def flat_sampler(point):
    return {"derived_bed_m": 0., "source_sample": {"height_m": 0.}, "cut_depth_m": 0., "fan_keys": []}


class UndergroundRiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parameters = CaveParameters(stations=9, crop_margin_m=4.)
        cls.vdm = build_charts(port_at(0.), port_at(60.), [0., 0., 0.], [0., 0., 60.], parameters)
        cls.rock, _ = build_rock(cls.vdm, flat_sampler, parameters, np.zeros(3))

    def test_seed_fixed_endpoints_reference_and_source_immutability(self):
        original = deepcopy(self.vdm)
        first = deform_charts(self.vdm, Parameters())
        self.assertEqual(first, deform_charts(self.vdm, Parameters()))
        self.assertNotEqual(first, deform_charts(self.vdm, Parameters(seed=18)))
        self.assertEqual(self.vdm, original)
        for ordinal in (0, -1):
            self.assertEqual(first["stations"][ordinal], original["stations"][ordinal])
        for station in first["stations"]:
            np.testing.assert_array_equal(np.asarray(station["reference_ring_xyz_m"]) +
                np.asarray(station["displacement_ring_xyz_m"]), station["derived_ring_xyz_m"])

    def test_real_boolean_air_route_and_preview_contract(self):
        preview = build_preview(self.rock, self.vdm, flat_sampler, {}, Parameters())
        self.assertEqual(preview["status"], "geometry_checked")
        self.assertEqual(preview["schema"], "td-underground-river-preview-v1")
        self.assertEqual(set(preview["meshes"]), {"rock_before", "cutter", "rock_after", "removed"})
        self.assertEqual(preview["geometry_checks"]["air_segment_count"], 8)
        self.assertEqual(preview["geometry_checks"]["terrain_opening_kinds"], ["sink", "spring"])
        checks = preview["geometry_checks"]
        self.assertFalse(checks["independent_audit_passed"])
        self.assertFalse(checks["complete_portal_certified"])
        self.assertEqual(len(checks["station_source_cover_witnesses"]), 9)
        for station in checks["station_source_cover_witnesses"]:
            for witness in station["actual_ring_containment"]:
                self.assertIn("rock_before_vertical_hits", witness)
                self.assertEqual(witness["source_bed_witness"]["derived_bed_m"], 0.)
        self.assertEqual(len(checks["air_path_segments"]), 8)
        for segment in checks["air_path_segments"]:
            self.assertEqual(segment["rock_after_hits"], [])
            self.assertIn("rock_before_hits", segment)
            self.assertIn("removed_hits", segment)
        for opening in checks["portal_opening_witnesses"].values():
            self.assertTrue(opening["rock_before_hits"])
            self.assertEqual(opening["rock_after_hits"], [])
            self.assertIn("source_bed_witness", opening)
        self.assertGreater(preview["metrics"]["excavated_rock_m3"], 0.)
        self.assertLess(abs(preview["metrics"]["material_residual_m3"]), 1e-7)
        self.assertFalse(any(preview["capabilities"].values()))
        self.assertIsNone(preview["water"])
        expected = preview.pop("identity_sha256")
        self.assertEqual(identity(preview), expected)

    def test_parameter_bounds_cover_crop_and_deadline_refused(self):
        Parameters(seed=2**32-1, lateral_amplitude_m=3., roof_variation_m=.5)
        for kwargs in ({"seed": True}, {"seed": -1}, {"seed": 2**32},
                       {"lateral_amplitude_m": 3.001}, {"roof_variation_m": .501},
                       {"width_scale": float("nan")}, {"width_scale": .79}):
            with self.assertRaises(ValueError):
                Parameters(**kwargs)
        broken = deepcopy(self.vdm)
        broken["stations"][4]["derived_ring_xyz_m"][0][0] = 100.
        broken["stations"][4]["displacement_ring_xyz_m"][0][0] = 98.
        with self.assertRaisesRegex(ValueError, "crop"):
            build_preview(self.rock, broken, flat_sampler, {})
        exposed = deepcopy(self.vdm)
        exposed["stations"][4]["derived_ring_xyz_m"] = (
            np.asarray(exposed["stations"][4]["derived_ring_xyz_m"]) + [0., 20., 0.]).tolist()
        exposed["stations"][4]["displacement_ring_xyz_m"] = (
            np.asarray(exposed["stations"][4]["displacement_ring_xyz_m"]) + [0., 20., 0.]).tolist()
        with self.assertRaisesRegex(ValueError, "cover"):
            build_preview(self.rock, exposed, flat_sampler, {})
        with self.assertRaisesRegex(ValueError, "budget"):
            build_preview(self.rock, self.vdm, flat_sampler, {}, started=time.perf_counter()-61.)

    def test_numeric_types_rejected_as_value_error(self):
        for name in ("lateral_amplitude_m", "width_scale", "roof_variation_m"):
            for value in (None, "1.0", True, [], {}, complex(1., 0.), float("inf"), 10**1000):
                with self.subTest(name=name, value_type=type(value).__name__):
                    with self.assertRaises(ValueError):
                        Parameters(**{name: value})

    def test_connected_removed_does_not_accept_blocked_air_polyline(self):
        blocked = deepcopy(self.vdm)
        blocked["stations"][4]["origin_xyz_m"][0] = 5.
        with self.assertRaisesRegex(ValueError, "actual_rock_blocks_continuous_air_path"):
            build_preview(self.rock, blocked, flat_sampler, {},
                          Parameters(lateral_amplitude_m=0., width_scale=1., roof_variation_m=0.))

    def test_no_overwrite_existing_source_directory(self):
        with self.assertRaisesRegex(ValueError, "never overwrite"):
            prepare(ROOT / "verification/natural-river-network/hybrid-cave-geometry-20261006-03")


if __name__ == "__main__":
    unittest.main()
