"""Tests for the Uluru flared-slope L1 volume form (offline, new files only).

Every test re-derives its numbers from the built geometry or from the saved mesh arrays;
nothing here is a certification, and no capability flag is expected to be True.
"""

import json
import sys
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import special_terrain as flare
from terrain_pipeline.hybrid_geometry import ray_hits
from terrain_pipeline.hybrid_geometry import FLAGS, census, solid_from_record
from terrain_pipeline.hybrid_geometry import identity


class FlaredBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record, cls.geometry = flare.uluru_flare_report()
        cls.solid = cls.geometry["solid"]
        cls.origin = cls.geometry["origin"]
        cls.parameters = cls.geometry["parameters"]
        cls.solids = cls.record["solids"]

    def test_report_is_candidate_with_every_flag_false(self):
        record = self.record
        self.assertEqual(record["status"], "candidate")
        self.assertEqual(record["schema"], flare.ULURU_FLARE_REPORT_SCHEMA)
        self.assertEqual(record["algorithm"], flare.ULURU_FLARE_ALGORITHM)
        self.assertEqual(record["synthetic_base"]["kind"], "synthetic_analytic")
        self.assertEqual(set(record["flags"]), set(FLAGS))
        self.assertTrue(record["flags"])
        self.assertFalse(any(record["flags"].values()))
        for role in (flare.SKIRT_ROLE, flare.BODY_ROLE, flare.ULURU_FLARE_SOLID_ROLE):
            self.assertTrue(self.solids[role]["sampled_not_native_exact"])

    def test_report_identity_recomputes_and_encoding_is_deterministic(self):
        record = self.record
        self.assertEqual(record["identity_sha256"], flare.uluru_flare_report_identity(record))
        first = record["solids"][flare.ULURU_FLARE_SOLID_ROLE]
        self.assertEqual(first["identity_sha256"], identity(
            {key: value for key, value in first.items() if key != "identity_sha256"}))
        again, _ = flare.uluru_flare_report()
        self.assertEqual(flare.encode_report(again), flare.encode_report(record))
        self.assertEqual(again["identity_sha256"], record["identity_sha256"])
        self.assertNotIn(b"\n", flare.encode_report(record))

    def test_union_volume_matches_the_two_input_bodies(self):
        skirt = self.solids[flare.SKIRT_ROLE]
        body = self.solids[flare.BODY_ROLE]
        union = self.solids[flare.ULURU_FLARE_SOLID_ROLE]
        measured = float(self.solid.volume())
        self.assertAlmostEqual(measured, union["signed_volume_m3"], delta=1e-6)
        overlap = skirt["signed_volume_m3"] + body["signed_volume_m3"] - union["signed_volume_m3"]
        self.assertGreater(overlap, 0.)
        self.assertLess(overlap, min(skirt["signed_volume_m3"], body["signed_volume_m3"]))
        self.assertEqual(census(self.solid), 1)
        self.assertEqual(self.record["boolean"]["census"]["assembled_components"], 1)

    def test_every_solid_record_is_closed_and_volume_gated(self):
        for role, mesh in self.solids.items():
            self.assertEqual(mesh["schema"], "td-hybrid-local-solid-mesh-v1")
            rebuilt = solid_from_record(mesh, role)
            self.assertAlmostEqual(float(rebuilt.volume()), mesh["signed_volume_m3"], delta=1e-6)
        tampered = json.loads(json.dumps(self.solids[flare.ULURU_FLARE_SOLID_ROLE]))
        tampered["signed_volume_m3"] += 1.
        with self.assertRaises(ValueError):
            solid_from_record(tampered, "tampered")

    def test_overhang_point_is_outside_and_controls_are_not_vacuous(self):
        witnesses = self.record["witnesses"]
        for name in ("overhang_point_outside_union", "control_point_inside_tower",
                     "control_point_far_outside"):
            witness = witnesses[name]
            self.assertEqual(witness["method"], "Solid.winding")
            self.assertEqual(witness["solid_role"], flare.ULURU_FLARE_SOLID_ROLE)
            self.assertTrue(witness["verdict"], name)
            self.assertTrue(self.solids[witness["solid_role"]]["identity_sha256"])
            inside, winding = flare.uluru_flare_inside_by_winding(
                self.solids[witness["solid_role"]], witness["point_xyz_m"], self.origin)
            self.assertEqual(inside, witness["observed"]["inside"])
            self.assertEqual(inside, witness["expected_inside"])
            self.assertAlmostEqual(witness["observed"]["winding"],
                                   1. if inside else 0., places=9)
            if not inside:
                self.assertLess(abs(witness["observed"]["winding"]), 1e-9)
                self.assertEqual(witness["probe_cube_intersection_volume_m3"], 0.)
            else:
                self.assertGreater(witness["probe_cube_intersection_volume_m3"], 0.)
        far = witnesses["control_point_far_outside"]["point_xyz_m"]
        self.assertAlmostEqual(far[0], float(self.origin[0]) + self.parameters.tower_base_radius_m
                               + self.parameters.overhang_amplitude_m + 100.)
        under = witnesses["overhang_point_outside_union"]["point_xyz_m"]
        self.assertGreater(under[0] - float(self.origin[0]), self.parameters.skirt_outer_radius_m)
        self.assertLess(under[0] - float(self.origin[0]), self.parameters.tower_base_radius_m)
        self.assertLess(under[1], self.parameters.skirt_top_elevation_m)

    def test_winding_number_is_an_independent_containment_oracle(self):
        mesh = self.solids[flare.ULURU_FLARE_SOLID_ROLE]
        origin = self.origin
        corner = np.asarray(mesh["vertices_local_xyz_m"], float).max(axis=0) + np.asarray(origin, float) + 5.
        winding = flare.uluru_flare_winding_number(mesh["vertices_local_xyz_m"], mesh["triangles"], corner, origin)
        self.assertAlmostEqual(winding, 0., places=9)
        centre = [float(origin[0]), self.parameters.total_height_m * .5, float(origin[2])]
        self.assertTrue(flare.uluru_flare_inside_by_winding(mesh, centre, origin)[0])
        beside = [centre[0] + self.parameters.tower_base_radius_m + 50., centre[1], centre[2]]
        self.assertAlmostEqual(flare.uluru_flare_winding_number(mesh["vertices_local_xyz_m"], mesh["triangles"],
                                                    beside, origin), 0., places=9)
        self.assertFalse(flare.uluru_flare_inside_by_winding(mesh, beside, origin)[0])

    def test_ray_witnesses_cross_void_then_hit_rock(self):
        witnesses = self.record["witnesses"]
        for name in ("vertical_ray_crosses_void_then_hits_rock",
                     "horizontal_ray_crosses_void_then_hits_rock"):
            witness = witnesses[name]
            self.assertEqual(witness["method"], "Manifold.ray_cast")
            self.assertTrue(witness["verdict"], name)
            hits = ray_hits(self.solid, witness["from_xyz_m"], witness["to_xyz_m"], self.origin)
            self.assertEqual(len(hits), witness["expected_hit_count"])
            self.assertEqual(len(hits), witness["observed"]["hit_count"])
            hit = np.array(hits[0]["position_xyz_m"], float)
            from_xyz = np.array(witness["from_xyz_m"], float)
            self.assertGreater(np.linalg.norm(hit - from_xyz), 1.)
            self.assertGreater(flare.uluru_flare_contains_point(self.solid, hit + (hit - from_xyz) / np.linalg.norm(hit - from_xyz) * .01, self.origin), 0.)

    def test_vertical_ray_endpoint_is_inside_the_tower(self):
        witness = self.record["witnesses"]["vertical_ray_crosses_void_then_hits_rock"]
        endpoint = witness["to_xyz_m"]
        self.assertGreater(flare.uluru_flare_contains_point(self.solid, endpoint, self.origin), 0.)
        start = witness["from_xyz_m"]
        self.assertAlmostEqual(flare.uluru_flare_contains_point(self.solid, start, self.origin), 0., delta=1e-12)
        self.assertLess(start[1], self.parameters.skirt_top_elevation_m)
        self.assertGreater(start[1], 0.)

    def test_overhang_amplitude_and_slopes_are_positive_and_consistent(self):
        parameters = self.parameters
        amplitude = parameters.tower_base_radius_m - parameters.skirt_outer_radius_m
        self.assertAlmostEqual(parameters.overhang_amplitude_m, amplitude)
        self.assertGreater(amplitude, 0.)
        self.assertTrue(0. < parameters.tower_top_radius_m < parameters.tower_base_radius_m)
        self.assertGreater(parameters.tower_side_slope_deg, 0.)
        self.assertGreater(parameters.skirt_wall_slope_deg, 0.)
        self.assertGreater(parameters.skirt_top_elevation_m, parameters.tower_base_elevation_m)
        for name in ("overhang_amplitude_m", "skirt_height_m", "skirt_wall_slope_deg",
                     "tower_side_slope_deg", "total_height_m"):
            entry = [item for item in self.record["explicit_assumptions"] if item["name"] == name]
            self.assertEqual(len(entry), 1, name)
            self.assertEqual(entry[0]["grade"], "assumed")
        conflict = self.record["height_conflict"]
        self.assertEqual(conflict["resolution"], "unresolved")
        self.assertEqual(sorted(conflict["published_m"]), [335., 348.])
        self.assertEqual(conflict["chosen_m"], 348.)
        derived = self.record["derived"]
        declared = {item["name"]: item["value"] for item in self.record["explicit_assumptions"]}
        self.assertAlmostEqual(declared["overhang_amplitude_m"], derived["overhang_amplitude_m"], places=6)
        self.assertAlmostEqual(declared["skirt_wall_slope_deg"], derived["skirt_wall_slope_deg"], places=3)
        self.assertAlmostEqual(declared["tower_side_slope_deg"], derived["tower_side_slope_deg"], places=3)
        self.assertAlmostEqual(declared["skirt_height_m"], parameters.skirt_top_elevation_m, places=9)
        self.assertAlmostEqual(declared["total_height_m"], parameters.total_height_m, places=9)
        self.assertEqual(self.record["world_frame"], flare.WORLD_FRAME_NOTE)
        self.assertEqual(self.record["figure_scope"], flare.FIGURE_SCOPE)
        self.assertEqual(self.record["parent_algorithm"], flare.ULURU_FLARE_PARENT_ALGORITHM)

    def test_parameters_refuse_incoherent_geometry(self):
        with self.assertRaises(ValueError):
            flare.FlareParameters(total_height_m=5.)
        with self.assertRaises(ValueError):
            flare.FlareParameters(tower_top_radius_m=200.)
        with self.assertRaises(ValueError):
            flare.FlareParameters(skirt_outer_radius_m=180.)
        with self.assertRaises(ValueError):
            flare.FlareParameters(skirt_top_elevation_m=5.)
        with self.assertRaises(ValueError):
            flare.FlareParameters(tower_segments=2)
        with self.assertRaises(ValueError):
            flare.FlareParameters(total_height_m=348)
        with self.assertRaises(ValueError):
            flare.uluru_flare_build("not parameters")
        self.assertEqual(flare.FlareParameters().total_height_m, 348.)

    def test_plane_section_returns_actual_mesh_crossings(self):
        mesh = self.solids[flare.ULURU_FLARE_SOLID_ROLE]
        value = float(self.origin[2])
        segments = flare.uluru_flare_plane_section_segments(mesh, 2, value)
        self.assertGreater(len(segments), 20)
        for first, second in segments:
            for point in (first, second):
                self.assertEqual(len(point), 2)
                self.assertTrue(np.isfinite(point).all())
        radii = [abs(float(point[0]) - float(self.origin[0])) for pair in segments for point in pair]
        self.assertGreater(max(radii), self.parameters.tower_base_radius_m * .5)

    def test_report_json_matches_the_shared_contract_and_is_reproducible(self):
        import tempfile
        required = {"schema", "algorithm", "status", "synthetic_base", "parameters",
                    "explicit_assumptions", "solids", "boolean", "witnesses", "flags",
                    "library_versions", "figures", "identity_sha256"}
        self.assertTrue(required <= set(self.record))
        self.assertEqual(self.record["status"], "candidate")
        for item in self.record["explicit_assumptions"]:
            self.assertEqual(sorted(item), ["grade", "name", "reason", "value"])
            self.assertEqual(item["grade"], "assumed")
        for role, mesh in self.record["solids"].items():
            self.assertTrue({"schema", "role", "local_origin_xyz_m", "vertices_local_xyz_m",
                             "triangles", "signed_volume_m3", "sampled_not_native_exact",
                             "identity_sha256"} <= set(mesh))
            self.assertEqual(mesh["role"], role)
        for witness in self.record["witnesses"].values():
            self.assertIn(witness["method"], ("Manifold.ray_cast", "Solid.winding", "Mesh64_boolean"))
            self.assertIn("verdict", witness)
            self.assertIn("claim", witness)
        with tempfile.TemporaryDirectory() as folder:
            first = flare.uluru_flare_write_report(Path(folder) / "report.json")
            written = (Path(folder) / "report.json").read_bytes()
            self.assertNotIn(b"\n", written)
            self.assertEqual(written, flare.encode_report(first))
            self.assertEqual(first["identity_sha256"], self.record["identity_sha256"])
            self.assertEqual(first["figures"], [])

    def test_rendered_figures_are_hashed_and_reported(self):
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            panels = flare.uluru_flare_render(self.solids[flare.ULURU_FLARE_SOLID_ROLE], self.parameters, Path(folder))
            self.assertEqual(len(panels), 3)
            for panel in panels:
                path = Path(panel["path"])
                self.assertTrue(path.exists())
                self.assertEqual(panel["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
