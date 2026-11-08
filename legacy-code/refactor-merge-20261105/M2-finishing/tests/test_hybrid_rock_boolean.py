"""Bounded behaviour cases for the general closed-solid Boolean.

Synthetic analytic solids only: no TD package, no runtime parent package, no solver.
The conduit module is only imported to prove its pinned identity is untouched.
"""

import math
import unittest

import numpy as np

from terrain_pipeline import hybrid_geometry as conduit
from terrain_pipeline.hybrid_geometry import ALGORITHM, CONDUIT_POLICY_SHA256, FLAGS, HYBRID_ROCK_BOOLEAN_POLICY as POLICY, HYBRID_ROCK_BOOLEAN_POLICY_SHA256 as POLICY_SHA256, RESULT_SCHEMA, HYBRID_ROCK_BOOLEAN_SCHEMA as SCHEMA, BooleanParameters, combine, census, excavate, frustum_record, octagon_ring, polygon_prism_record, solid_from_record, sphere_record
from terrain_pipeline.hybrid_geometry import identity

ORIGIN = np.array([4., -3., 7.])


def square_ring(half_x, half_z, centre=(0., 0.)):
    return np.array([[centre[0] - half_x, centre[1] - half_z], [centre[0] + half_x, centre[1] - half_z],
                     [centre[0] + half_x, centre[1] + half_z], [centre[0] - half_x, centre[1] + half_z]], float)


class RockBooleanTests(unittest.TestCase):
    def test_prism_volume_and_closed_record_reproducible(self):
        first = polygon_prism_record(square_ring(10., 10.), -5., 5., ORIGIN, "rock")
        second = polygon_prism_record(square_ring(10., 10.), -5., 5., ORIGIN, "rock")
        self.assertEqual(first["schema"], "td-hybrid-local-solid-mesh-v1")
        self.assertEqual(first["role"], "rock")
        self.assertTrue(first["sampled_not_native_exact"])
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["signed_volume_m3"], 4000., places=6)
        self.assertEqual(census(solid_from_record(first, "rock")), 1)

    def test_frustum_and_sphere_records_are_closed_positive_solids(self):
        frustum = frustum_record([0., 0.], [0., 0.], 0., 10., 6., 2., ORIGIN, "cutter", segments=32)
        self.assertGreater(frustum["signed_volume_m3"], 0.)
        expected = math.pi * 10. * (6.**2 + 6. * 2. + 2.**2) / 3.
        self.assertLess(abs(frustum["signed_volume_m3"] - expected) / expected, .02)
        ball = sphere_record([1., 2., 3.], 2.5, ORIGIN, "egg", circular_segments=64)
        ideal_ball = 4. / 3. * math.pi * 2.5**3
        self.assertLess(abs(ball["signed_volume_m3"] - ideal_ball) / ideal_ball, .01)
        with self.assertRaises(ValueError):
            polygon_prism_record(square_ring(1., 1.), 5., 5., ORIGIN, "rock")
        with self.assertRaises(ValueError):
            polygon_prism_record([[0., 0.], [1., 1.], [2., 2.]], 0., 1., ORIGIN, "rock")
        with self.assertRaises(ValueError):
            octagon_ring([0., 0.], 1., 1., 2)
        with self.assertRaises(ValueError):
            frustum_record([0., 0.], [0., 0.], 0., 10., 6., float("nan"), ORIGIN, "cutter")

    def test_excavation_matches_actual_volume_and_refuses_shortfalls(self):
        parameters = BooleanParameters(solids_spacing_m=1., component_limit=8)
        rock = polygon_prism_record(square_ring(10., 10.), -5., 5., ORIGIN, "rock")
        tunnel = polygon_prism_record(square_ring(5., 5.), -20., 20., ORIGIN, "cutter")
        result, meshes = excavate(rock, [tunnel], parameters, ORIGIN)
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(result["algorithm"], ALGORITHM)
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(result["rejection_reasons"], [])
        material = result["material"]
        self.assertAlmostEqual(material["rock_before_m3"], 4000., places=6)
        self.assertAlmostEqual(material["excavated_rock_m3"], 1000., places=6)
        self.assertAlmostEqual(material["rock_after_m3"], 3000., places=6)
        self.assertAlmostEqual(material["fill_rock_m3"], 0.)
        self.assertLess(abs(material["signed_residual_m3"]), material["balance_budget_m3"])
        self.assertEqual(set(meshes), {"rock_after", "removed", "cutter_union"})
        self.assertAlmostEqual(meshes["removed"]["signed_volume_m3"], 1000., places=6)
        self.assertEqual(census(solid_from_record(meshes["removed"], "removed")), 1)
        self.assertEqual(result["census"]["removed_components"], 1)
        self.assertEqual(result["census"]["rock_after_components"], 1)
        for flag in FLAGS:
            self.assertIs(result[flag], False)
        self.assertEqual(result["identity_sha256"], identity({key: value for key, value in result.items()
                                                              if key != "identity_sha256"}))
        repeat, _ = excavate(rock, [tunnel], parameters, ORIGIN)
        self.assertEqual(repeat["identity_sha256"], result["identity_sha256"])

    def test_two_disjoint_cutters_are_one_union_and_two_cavities(self):
        parameters = BooleanParameters(solids_spacing_m=1., component_limit=8)
        rock = polygon_prism_record(square_ring(20., 10.), -10., 10., ORIGIN, "rock")
        first = polygon_prism_record(square_ring(2., 2., (-12., 0.)), -30., 30., ORIGIN, "cutter")
        second = polygon_prism_record(square_ring(2., 2., (12., 0.)), -30., 30., ORIGIN, "cutter")
        self.assertEqual(census(solid_from_record(first, "cutter")), 1)
        result, meshes = excavate(rock, [first, second], parameters, ORIGIN,
                                  minimum_removed_components=2)
        self.assertEqual(result["census"]["cutter_union_components"], 2)
        self.assertEqual(result["census"]["removed_components"], 2)
        # Each cutter is a 4 m x 4 m x 60 m prism (960 m3); the 20 m thick rock slab
        # caps the void at 16 m2 x 20 m = 320 m3 per cavity, 640 m3 together.
        self.assertAlmostEqual(meshes["cutter_union"]["signed_volume_m3"], 2 * 960., places=6)
        self.assertAlmostEqual(meshes["removed"]["signed_volume_m3"], 2 * 320., places=6)
        with self.assertRaises(ValueError):
            excavate(rock, [first, second], parameters, ORIGIN, minimum_removed_components=3)

    def test_cutter_union_merges_into_one_cavity_when_overlapping(self):
        parameters = BooleanParameters(solids_spacing_m=1., component_limit=8)
        rock = polygon_prism_record(square_ring(20., 10.), -10., 10., ORIGIN, "rock")
        first = polygon_prism_record(square_ring(3., 2., (-2., 0.)), -30., 30., ORIGIN, "cutter")
        second = polygon_prism_record(square_ring(3., 2., (2., 0.)), -30., 30., ORIGIN, "cutter")
        result, meshes = excavate(rock, [first, second], parameters, ORIGIN)
        self.assertEqual(result["census"]["cutter_union_components"], 1)
        self.assertEqual(result["census"]["removed_components"], 1)
        # Two 6 m x 4 m prisms whose x-ranges overlap on a 2 m band: the union is
        # 40 m2 in plan, so the 20 m thick slab leaves 800 m3 of void, not 2 x 480 m3.
        self.assertAlmostEqual(meshes["cutter_union"]["signed_volume_m3"], 2400., places=6)
        self.assertAlmostEqual(meshes["removed"]["signed_volume_m3"], 800., places=6)
        with self.assertRaises(ValueError):
            excavate(rock, [first, second], parameters, ORIGIN, minimum_removed_components=2)

    def test_combine_union_preserves_gaps_and_refuses_claimed_components(self):
        parameters = BooleanParameters(solids_spacing_m=1., component_limit=8)
        eggs = [sphere_record([0., 0., 0.], 1.5, ORIGIN, "egg", circular_segments=32),
                sphere_record([0., 5., 0.], 1.5, ORIGIN, "egg", circular_segments=32),
                sphere_record([0., 10., 0.], 1.5, ORIGIN, "egg", circular_segments=32)]
        result, meshes = combine(eggs, ORIGIN, "egg_pile", parameters, minimum_components=3)
        self.assertEqual(result["operation"], "closed_solid_union_no_cutter")
        self.assertEqual(result["census"]["assembled_components"], 3)
        self.assertEqual(result["material"]["excavated_rock_m3"], 0.)
        self.assertEqual(result["material"]["signed_residual_m3"], 0.)
        self.assertEqual(set(meshes), {"egg_pile"})
        # Disjoint components: the union volume is exactly the sum of the parts, which is
        # what makes the pile's interstitial gaps genuine exterior rather than filler.
        self.assertAlmostEqual(meshes["egg_pile"]["signed_volume_m3"],
                               sum(egg["signed_volume_m3"] for egg in eggs), places=6)
        for flag in FLAGS:
            self.assertIs(result[flag], False)
        with self.assertRaises(ValueError):
            combine(eggs, ORIGIN, "egg_pile", parameters, minimum_components=4)
        with self.assertRaises(ValueError):
            combine([eggs[0], sphere_record([0., .5, 0.], 1.5, ORIGIN, "egg", circular_segments=32)],
                    ORIGIN, "egg_pile", parameters, minimum_components=2)
        with self.assertRaises(ValueError):
            combine([], ORIGIN, "egg_pile", parameters)

    def test_open_or_mismatched_records_and_parameters_are_refused(self):
        parameters = BooleanParameters(solids_spacing_m=1., component_limit=8)
        rock = polygon_prism_record(square_ring(10., 10.), -5., 5., ORIGIN, "rock")
        tunnel = polygon_prism_record(square_ring(5., 5.), -20., 20., ORIGIN, "cutter")
        broken = {"schema": "td-hybrid-local-solid-mesh-v1", "role": "cutter",
                  "local_origin_xyz_m": ORIGIN.tolist(), "sampled_not_native_exact": True,
                  "vertices_local_xyz_m": [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]],
                  "triangles": [[0, 1, 2]], "signed_volume_m3": 1.}
        with self.assertRaises(ValueError):
            excavate(broken, [tunnel], parameters, ORIGIN)
        with self.assertRaises(ValueError):
            excavate(rock, [broken], parameters, ORIGIN)
        wrong_schema = dict(tunnel, schema="td-hybrid-multichart-vdm-v1")
        with self.assertRaises(ValueError):
            excavate(rock, [wrong_schema], parameters, ORIGIN)
        tampered = dict(tunnel, signed_volume_m3=tunnel["signed_volume_m3"] + 1.)
        with self.assertRaises(ValueError):
            excavate(rock, [tampered], parameters, ORIGIN)
        missing_volume = {key: value for key, value in tunnel.items() if key != "signed_volume_m3"}
        with self.assertRaises(ValueError):
            excavate(rock, [missing_volume], parameters, ORIGIN)
        with self.assertRaises(ValueError):
            excavate(rock, [], parameters, ORIGIN)
        with self.assertRaises(ValueError):
            excavate(rock, [tunnel], parameters, [1., 2.])
        with self.assertRaises(ValueError):
            excavate(rock, [tunnel], dict(solids_spacing_m=1.), ORIGIN)
        with self.assertRaises(ValueError):
            BooleanParameters(solids_spacing_m=1)
        with self.assertRaises(ValueError):
            BooleanParameters(solids_spacing_m=0.01)
        with self.assertRaises(ValueError):
            BooleanParameters(component_limit=0)
        with self.assertRaises(ValueError):
            BooleanParameters(component_limit=True)
        with self.assertRaises(ValueError):
            BooleanParameters(balance_relative_tolerance=1e-3)
        unused = polygon_prism_record(square_ring(.5, .5, (100., 100.)), -30., 30., ORIGIN, "cutter")
        with self.assertRaises(ValueError):
            excavate(rock, [unused], parameters, ORIGIN)

    def test_module_identity_is_independent_of_the_pinned_conduit_identity(self):
        self.assertEqual(SCHEMA, "td-hybrid-rock-boolean-v1")
        self.assertNotEqual(POLICY_SHA256, CONDUIT_POLICY_SHA256)
        self.assertEqual(conduit.POLICY_SHA256, CONDUIT_POLICY_SHA256)
        self.assertEqual(conduit.POLICY["version"], "local-rock-boolean-multichart-v1")
        self.assertNotEqual(POLICY, conduit.POLICY)


if __name__ == "__main__":
    unittest.main()
