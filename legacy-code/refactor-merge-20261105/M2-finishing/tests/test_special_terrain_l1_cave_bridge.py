"""Independent tests for the P5.3 cave / skylight / natural-bridge volume form.

Every witness in the saved report is replayed here straight from the saved solid meshes
(``manifold3d`` rebuild + re-cast + winding re-sum + a re-done Mesh64 subtract), which is
exactly the cold-read contract the report declares. The combination module under test is
used only to *produce* the report.
"""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline import hybrid_geometry as boolean
from terrain_pipeline import special_terrain as bridge
from terrain_pipeline.hybrid_geometry import manifold_from_record, ray_hits, signed_volume
from terrain_pipeline.hybrid_geometry import identity

CONTRACT_KEYS = ("schema", "algorithm", "status", "synthetic_base", "parameters",
                 "explicit_assumptions", "solids", "boolean", "witnesses", "flags",
                 "library_versions", "figures", "identity_sha256")
SOLID_KEYS = ("schema", "role", "local_origin_xyz_m", "vertices_local_xyz_m", "triangles",
              "signed_volume_m3", "sampled_not_native_exact", "identity_sha256")
BRIDGE_ROLES = ("cutter_skylight_a", "cutter_skylight_b")

_REPORT = None
_SOLIDS = None


def report():
    """One shared default build; the build is deterministic, so sharing is safe."""
    global _REPORT, _SOLIDS
    if _REPORT is None:
        _REPORT, _SOLIDS = bridge.cave_bridge_report()
    return _REPORT, _SOLIDS


def rebuild(record):
    """Rebuild a closed Manifold straight from a saved record, no generator involved."""
    mesh = __import__("manifold3d").Mesh64(
        np.array(record["vertices_local_xyz_m"], dtype=np.float64, order="C", copy=True),
        np.array(record["triangles"], dtype=np.uint64, order="C", copy=True))
    return __import__("manifold3d").Manifold(mesh)


def replayed_ray(witness, solids, origin):
    solid = rebuild(solids[witness["solid_role"]])
    return ray_hits(solid, np.array(witness["from_xyz_m"], float),
                    np.array(witness["to_xyz_m"], float), origin)


class DefaultLattice(unittest.TestCase):
    """The default assumed lattice excavates one cavity and leaves a bridge."""

    def test_status_census_and_flags(self):
        record, _ = report()
        self.assertEqual(record["status"], "candidate")
        self.assertEqual(record["schema"], bridge.CAVE_BRIDGE_REPORT_SCHEMA)
        boolean_record = record["boolean"]
        self.assertEqual(boolean_record["status"], "candidate")
        census = boolean_record["census"]
        self.assertEqual(census["removed_components"], 1)
        self.assertEqual(census["rock_after_components"], 1)
        self.assertEqual(census["cutter_union_components"], 1)
        self.assertEqual(census["cutter_count"], 4)
        self.assertEqual(record["flags"], {flag: False for flag in boolean.FLAGS})
        self.assertEqual(boolean_record["rejection_reasons"], [])
        self.assertEqual(boolean_record["operation"], "rock_minus_closed_cutter_union")
        self.assertEqual(boolean_record["fill_rock_m3"], 0.)

    def test_tunnel_network_and_both_skylights_share_one_cavity(self):
        record, solids = report()
        self.assertEqual(sorted(solids), sorted(record["solids"]))
        for role in BRIDGE_ROLES + ("cutter_main_tunnel", "cutter_side_branch", "rock_before",
                                    "rock_after", "removed", "cutter_union"):
            self.assertIn(role, solids)
        # The two bores sit on top of the gallery, and the branch reaches across it, so the
        # unified cutter set must be one connected solid: nothing here is a free-floating hole.
        self.assertEqual(len(rebuild(solids["cutter_union"]).decompose()), 1)
        self.assertEqual(len(rebuild(solids["rock_after"]).decompose()), 1)
        self.assertEqual(len(rebuild(solids["removed"]).decompose()), 1)


class MaterialAccount(unittest.TestCase):
    """Actual closed-solid volume, never a formula the Boolean did not produce."""

    def test_analytic_lattice_volumes(self):
        record, solids = report()
        parameters = bridge.PARAMETERS
        self.assertAlmostEqual(solids["rock_before"]["signed_volume_m3"], 432000., delta=1e-6)
        self.assertAlmostEqual(solids["cutter_main_tunnel"]["signed_volume_m3"], 6400., delta=1e-6)
        self.assertAlmostEqual(solids["cutter_side_branch"]["signed_volume_m3"], 5760., delta=1e-6)
        # Inscribed n-gon bore: circumradius R, height top - roof, area (n/2) R^2 sin(2 pi/n).
        ring_area = (parameters.skylight_segments / 2.) * parameters.skylight_radius_m**2 \
            * math.sin(2. * math.pi / parameters.skylight_segments)
        bore = ring_area * (parameters.top_y_m - parameters.tunnel_roof_y_m)
        for role in BRIDGE_ROLES:
            self.assertAlmostEqual(solids[role]["signed_volume_m3"], bore, delta=1e-6)
        overlap = (2. * parameters.tunnel_half_width_m) * (2. * parameters.branch_half_width_m) \
            * (parameters.tunnel_roof_y_m - parameters.tunnel_floor_y_m)
        expected = (solids["cutter_main_tunnel"]["signed_volume_m3"]
                    + solids["cutter_side_branch"]["signed_volume_m3"] - overlap + 2. * bore)
        self.assertAlmostEqual(solids["cutter_union"]["signed_volume_m3"], expected, delta=1e-6)

    def test_balance_closes_on_the_saved_solids(self):
        record, solids = report()
        material = record["boolean"]["material"]
        self.assertEqual(material["fill_rock_m3"], 0.)
        self.assertLessEqual(abs(material["signed_residual_m3"]), material["balance_budget_m3"])
        self.assertAlmostEqual(material["rock_before_m3"] - material["rock_after_m3"],
                               material["excavated_rock_m3"], delta=1e-7)
        # The cutter union is the excavated void: the re-saved closed surfaces must agree.
        self.assertAlmostEqual(solids["cutter_union"]["signed_volume_m3"],
                               solids["removed"]["signed_volume_m3"], delta=1e-7)
        self.assertAlmostEqual(solids["rock_after"]["signed_volume_m3"],
                               material["rock_after_m3"], delta=1e-7)

    def test_saved_void_is_a_closed_reverse_two_use_surface(self):
        _, solids = report()
        uses = {}
        for triangle in np.asarray(solids["removed"]["triangles"], int):
            for first, second in zip(triangle, np.roll(triangle, -1)):
                uses.setdefault(tuple(sorted((int(first), int(second)))), []).append(
                    (int(first), int(second)))
        for sides in uses.values():
            self.assertEqual(len(sides), 2)
            self.assertEqual(sides[0], sides[1][::-1])


class BridgeAndSkylights(unittest.TestCase):
    """The three decisive verdicts, each replayed from the saved meshes."""

    def test_bridge_axis_stays_solid_under_the_top_face(self):
        record, solids = report()
        witness = record["witnesses"]["bridge_axis_under_top_face"]
        hits = replayed_ray(witness, solids, bridge.ORIGIN)
        self.assertEqual(len(hits), witness["expected_hit_count"])
        self.assertEqual(len(hits), 4)
        # Two bore walls on each side plus the two block side walls: the segment is real rock
        # everywhere in between, so the block is not split along its whole length.
        xs = [hit["position_xyz_m"][0] for hit in hits]
        self.assertAlmostEqual(hits[1]["position_xyz_m"][0], -21., delta=1e-9)
        self.assertAlmostEqual(hits[2]["position_xyz_m"][0], 21., delta=1e-9)
        self.assertLess(xs[1], 0.)
        self.assertGreater(xs[2], 0.)

    def test_both_bridge_probe_centres_cross_rock_above_the_gallery_roof(self):
        record, solids = report()
        parameters = bridge.PARAMETERS
        witness = record["witnesses"]["bridge_probe_centres_are_both_bridges"]
        self.assertEqual(witness["observed"]["crossings_above_gallery_roof"], [1, 1])
        for probe in witness["observed"]["probes"]:
            hits = replayed_ray(probe["ray"], solids, bridge.ORIGIN)
            self.assertEqual(len(hits), 4)
            over_roof = [hit for hit in hits
                         if hit["position_xyz_m"][1] > parameters.tunnel_roof_y_m]
            self.assertEqual(len(over_roof), 1)
            # ... and that single crossing is the block top face, not a bore wall.
            self.assertAlmostEqual(over_roof[0]["position_xyz_m"][1], parameters.top_y_m,
                                   delta=1e-9)
        self.assertLess(witness["observed"]["probes"][0]["x_m"],
                        parameters.skylight_x_m[1] - parameters.skylight_radius_m)
        self.assertGreater(witness["observed"]["probes"][1]["x_m"],
                           parameters.skylight_x_m[1] + parameters.skylight_radius_m)

    def test_skylights_are_open_to_the_sky_and_the_top_face_between_them_is_not(self):
        record, solids = report()
        parameters = bridge.PARAMETERS
        for role, centre in zip(BRIDGE_ROLES, parameters.skylight_x_m):
            suffix = role.split("_")[-1]
            aperture = record["witnesses"]["skylight_" + suffix + "_open_to_sky"]
            self.assertEqual(replayed_ray(aperture, solids, bridge.ORIGIN), [])
            bore = record["witnesses"]["skylight_" + suffix + "_bores_into_the_block"]
            hits = replayed_ray(bore, solids, bridge.ORIGIN)
            self.assertEqual(len(hits), 2)
            self.assertEqual([round(hit["position_xyz_m"][1], 6) for hit in hits],
                             [parameters.tunnel_floor_y_m, parameters.bottom_y_m])
            self.assertAlmostEqual([hit["position_xyz_m"][0] for hit in hits][0], centre, delta=1e-9)
        over_roof = record["witnesses"]["bridge_axis_over_the_roof"]
        hits = replayed_ray(over_roof, solids, bridge.ORIGIN)
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0]["position_xyz_m"][1], parameters.top_y_m, delta=1e-9)
        self.assertAlmostEqual(hits[0]["position_xyz_m"][2], 0., delta=1e-9)


class WindingVerdicts(unittest.TestCase):
    """The tolerant independent point-in-solid test, with its tolerance made explicit."""

    def test_tolerance_separates_a_residual_zero_from_a_real_interior(self):
        self.assertFalse(bridge.inside(0.))
        self.assertFalse(bridge.inside(1e-12))
        self.assertFalse(bridge.inside(3.05e-16))
        self.assertTrue(bridge.inside(1.))
        self.assertTrue(bridge.inside(.9999999999999))
        with self.assertRaises(ValueError):
            bridge.inside(-1.)
        with self.assertRaises(ValueError):
            bridge.inside(float("nan"))

    def test_winding_numbers_of_the_saved_rock_after(self):
        record, solids = report()
        parameters = bridge.PARAMETERS
        mesh = solids["rock_after"]
        mid_y = (parameters.tunnel_roof_y_m + parameters.top_y_m) / 2.
        void_y = (parameters.tunnel_floor_y_m + parameters.tunnel_roof_y_m) / 2.
        samples = {
            "bridge centre": ((0., mid_y, 0.), True),
            "bridge above the floor": ((0., parameters.tunnel_roof_y_m + 1., 0.), True),
            "gallery void": ((0., void_y, 0.), False),
            "branch void": ((0., void_y, parameters.branch_end_z_m - 6.), False),
            "bore a column": ((parameters.skylight_x_m[0], void_y + 2., 0.), False),
            "bore b column": ((parameters.skylight_x_m[1], void_y + 2., 0.), False),
            "outer rock": ((parameters.plan_half_x_m - 5., mid_y, parameters.plan_half_z_m - 5.),
                           True),
        }
        for label, (point, expected) in samples.items():
            value = bridge.cave_bridge_winding_number(point, mesh["vertices_local_xyz_m"], mesh["triangles"])
            self.assertEqual(bridge.inside(value), expected, label + " winding=" + repr(value))
            if expected:
                self.assertAlmostEqual(value, 1., delta=1e-9)
            else:
                self.assertLess(abs(value), bridge.WINDING_INSIDE_TOLERANCE)

    def test_every_saved_winding_witness_replays_from_the_mesh(self):
        record, solids = report()
        seen = 0
        for name, witness in record["witnesses"].items():
            if witness["method"] != "Solid.winding":
                continue
            mesh = solids[witness["solid_role"]]
            self.assertEqual(mesh["identity_sha256"],
                             identity({key: value for key, value in mesh.items()
                                       if key != "identity_sha256"}))
            replayed = bridge.cave_bridge_winding_number(witness["point_xyz_m"], mesh["vertices_local_xyz_m"],
                                            mesh["triangles"])
            self.assertAlmostEqual(replayed, witness["observed"]["winding"], delta=1e-12, msg=name)
            self.assertEqual(bridge.inside(replayed), witness["expected_inside"], name)
            self.assertTrue(witness["verdict"])
            seen += 1
        # Six standalone point verdicts ...
        self.assertEqual(seen, 6)
        # ... plus the two probe windings nested inside the bridge witness.
        nested = record["witnesses"]["bridge_probe_centres_are_both_bridges"]["observed"]["probes"]
        self.assertEqual(len(nested), 2)
        for probe in nested:
            mesh = solids[probe["winding"]["solid_role"]]
            replayed = bridge.cave_bridge_winding_number(probe["winding"]["point_xyz_m"],
                                            mesh["vertices_local_xyz_m"], mesh["triangles"])
            self.assertAlmostEqual(replayed, probe["winding"]["observed"]["winding"], delta=1e-12)
            self.assertTrue(bridge.inside(replayed))


class ColdReadContract(unittest.TestCase):
    """What a reader who does not import the generator can actually re-check."""

    def test_report_shape_and_sealed_solid_identities(self):
        record, solids = report()
        for key in CONTRACT_KEYS:
            self.assertIn(key, record)
        self.assertEqual(record["synthetic_base"]["kind"], "synthetic_analytic")
        self.assertIn("not TD native terrain", record["synthetic_base"]["note"])
        self.assertEqual(record["identity_sha256"],
                         identity({key: value for key, value in record.items()
                                   if key != "identity_sha256"}))
        self.assertEqual(record["parameters_identity_sha256"], identity(record["parameters"]))
        self.assertEqual(record["parameters"], asdict(bridge.PARAMETERS))
        self.assertIn("manifold3d", record["library_versions"])
        self.assertIn("numpy", record["library_versions"])
        for role, mesh in record["solids"].items():
            for key in SOLID_KEYS:
                self.assertIn(key, mesh, role)
            self.assertTrue(mesh["sampled_not_native_exact"], role)
            self.assertEqual(mesh["role"], role)
            self.assertEqual(mesh["identity_sha256"],
                             identity({key: value for key, value in mesh.items()
                                       if key != "identity_sha256"}))
            recomputed = signed_volume(np.array(mesh["vertices_local_xyz_m"], float),
                                       np.array(mesh["triangles"], int))
            self.assertAlmostEqual(recomputed, mesh["signed_volume_m3"], delta=1e-6, msg=role)
            self.assertEqual(rebuild(mesh).status().name, "NoError")

    def test_every_assumption_is_declared_as_an_explicit_assumption(self):
        record, _ = report()
        assumptions = {item["name"]: item for item in record["explicit_assumptions"]}
        self.assertTrue(assumptions)
        for item in record["explicit_assumptions"]:
            self.assertEqual(item["grade"], "assumed")
            self.assertTrue(item["reason"])
        for name in ("tunnel_roof_y_m", "tunnel_floor_y_m", "skylight_x_m", "skylight_radius_m"):
            self.assertIn(name, assumptions)
        # Every declared float/int parameter is covered by an explicit assumption entry, and
        # nothing else is (the two skylight entries are named per field, not per block).
        self.assertEqual(sorted(assumptions), sorted(name for name in record["parameters"]))

    def test_every_ray_witness_replays_and_names_a_saved_solid(self):
        record, solids = report()
        seen = 0
        for name, witness in record["witnesses"].items():
            if witness["method"] != "Manifold.ray_cast":
                continue
            if "probes" in witness.get("observed", {}):
                continue
            self.assertIn(witness["solid_role"], solids)
            hits = replayed_ray(witness, solids, bridge.ORIGIN)
            self.assertEqual(len(hits), witness["observed"]["hit_count"], name)
            self.assertEqual(len(hits), witness["expected_hit_count"], name)
            accompanied = {key: value for key, value in witness.items() if key != "observed"}
            self.assertEqual(sorted(accompanied),
                             sorted(["method", "solid_role", "from_xyz_m", "to_xyz_m",
                                     "expected_hit_count", "verdict", "claim"]))
            seen += 1
        self.assertGreaterEqual(seen, 6)

    def test_material_witnesses_replay_by_redoing_the_subtract(self):
        record, solids = report()
        for name in ("material_balance", "saved_void_closure"):
            witness = record["witnesses"][name]
            self.assertEqual(witness["method"], "Mesh64_boolean")
            self.assertEqual(witness["operation"], "subtract")
            rock = boolean.solid_from_record(solids[witness["rock_role"]], name)
            cutters = [boolean.solid_from_record(solids[role], name)
                       for role in witness["cutter_roles"]]
            union = rebuild(solids["cutter_union"])
            self.assertAlmostEqual(union.volume(), rock.volume() - (rock - union).volume(),
                                   delta=1e-7)
            self.assertAlmostEqual(union.volume(), (rock ^ union).volume(), delta=1e-7)
            self.assertAlmostEqual(union.volume(), witness["expected_removed_m3"], delta=1e-7)
            for role in witness["cutter_roles"]:
                self.assertIn(role, solids)
            self.assertEqual(len(cutters), len(record["parameters"]["skylight_x_m"]) + 2)

    def test_figures_are_labelled_display_only(self):
        record, _ = report()
        self.assertEqual(record["figure_scope"],
                         "display only; a figure is never a certification")
        self.assertEqual(record["figures"], [])

    def test_report_bytes_and_previews_are_reproducible(self):
        with tempfile.TemporaryDirectory() as shared:
            shared = Path(shared)
            first = bridge.cave_bridge_write_report(shared / "report.json", output_directory=shared)
            blob = (shared / "report.json").read_bytes()
            digests = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted(shared.glob("*.png"))}
            self.assertEqual(len(digests), 3)
            second = bridge.cave_bridge_write_report(shared / "report.json", output_directory=shared)
            self.assertEqual(blob, (shared / "report.json").read_bytes())
            self.assertEqual(first["identity_sha256"], second["identity_sha256"])
            self.assertEqual(first["figures"], second["figures"])
            for path in sorted(shared.glob("*.png")):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digests[path.name])
            self.assertTrue(blob.endswith(b"}"))
            self.assertNotIn(b"\n", blob)
            self.assertEqual(set(json.loads(blob.decode("utf-8"))), set(first))


class Refusals(unittest.TestCase):
    """The lattice refuses a geometry that would not actually be a bridge."""

    def test_skylights_too_close_to_leave_a_bridge_are_refused(self):
        with self.assertRaises(ValueError):
            bridge.Parameters(skylight_x_m=(-6., 6.))
        with self.assertRaises(ValueError):
            bridge.Parameters(skylight_x_m=(25., -25.))
        with self.assertRaises(ValueError):
            bridge.Parameters(skylight_x_m=[-25., 25.])

    def test_a_bore_swallowing_the_block_centre_is_refused(self):
        Parameters = bridge.Parameters
        # Both these lattices pass the spacing rule but leave no rock over the block centre,
        # so the "bridge" would in fact be one slit between two overlapping bores.
        for centres in ((-3., 40.), (-40., 3.)):
            with self.assertRaises(ValueError, msg=str(centres)):
                Parameters(skylight_x_m=centres)

    def test_tunnel_outside_the_block_or_through_the_walls_is_refused(self):
        Parameters = bridge.Parameters
        with self.assertRaises(ValueError):
            Parameters(tunnel_roof_y_m=1.)
        with self.assertRaises(ValueError):
            Parameters(tunnel_floor_y_m=-31.)
        with self.assertRaises(ValueError):
            Parameters(tunnel_floor_y_m=-14., tunnel_roof_y_m=-22.)
        with self.assertRaises(ValueError):
            Parameters(tunnel_length_x_m=60.)
        with self.assertRaises(ValueError):
            Parameters(branch_end_z_m=70.)
        with self.assertRaises(ValueError):
            Parameters(plan_half_x_m=5.)
        with self.assertRaises(ValueError):
            Parameters(branch_end_z_m=3.)

    def test_mistyped_lattice_fields_are_refused(self):
        Parameters = bridge.Parameters
        with self.assertRaises(ValueError):
            Parameters(solids_spacing_m=1)
        with self.assertRaises(ValueError):
            Parameters(skylight_segments=4)
        with self.assertRaises(ValueError):
            Parameters(component_limit=4096)
        with self.assertRaises(ValueError):
            Parameters(skylight_x_m=(-25, 25))
        with self.assertRaises(ValueError):
            bridge.cave_bridge_build(parameters=None)


class IndependentGeometry(unittest.TestCase):
    """The saved meshes are real closed solids, not displays."""

    def test_every_saved_solid_is_a_closed_use_manifold_with_positive_volume(self):
        _, solids = report()
        library = __import__("manifold3d")
        for role, mesh in solids.items():
            solid = rebuild(mesh)
            self.assertEqual(solid.status(), library.Error.NoError, role)
            self.assertFalse(solid.is_empty(), role)
            self.assertGreater(solid.volume(), 0., role)
            self.assertAlmostEqual(solid.volume(), mesh["signed_volume_m3"], delta=1e-6, msg=role)
            self.assertGreater(len(mesh["triangles"]), 3, role)
            uses = {}
            for triangle in np.asarray(mesh["triangles"], int):
                self.assertEqual(len(set(triangle.tolist())), 3, role)
                for first, second in zip(triangle, np.roll(triangle, -1)):
                    uses.setdefault(tuple(sorted((int(first), int(second)))), []).append(
                        (int(first), int(second)))
            for sides in uses.values():
                self.assertEqual(len(sides), 2, role)
                self.assertEqual(sides[0], sides[1][::-1], role)

    def test_the_block_top_face_is_only_broken_over_the_two_bores(self):
        _, solids = report()
        parameters = bridge.PARAMETERS
        rock = rebuild(solids["rock_after"])
        # Sweep the top-face plane: rock is present at every abscissa except inside a bore.
        for x_m in np.arange(-parameters.plan_half_x_m + 1., parameters.plan_half_x_m - 1., 1.):
            hits = ray_hits(rock, np.array([x_m, parameters.top_y_m + 3., 0.]),
                            np.array([x_m, parameters.top_y_m - 1., 0.]), bridge.ORIGIN)
            inside_bore = any(abs(float(x_m) - centre) < parameters.skylight_radius_m - .5
                              for centre in parameters.skylight_x_m)
            self.assertEqual(len(hits), 0 if inside_bore else 1,
                             "x=%.1f inside_bore=%s" % (x_m, inside_bore))

    def test_the_world_frame_is_the_identity(self):
        record, solids = report()
        self.assertIn("zero local origin", record["world_frame"])
        for mesh in solids.values():
            self.assertEqual(mesh["local_origin_xyz_m"], [0., 0., 0.])
        vertices = np.array(solids["rock_before"]["vertices_local_xyz_m"], float)
        self.assertEqual(vertices[:, 0].min(), -bridge.PARAMETERS.plan_half_x_m)
        self.assertEqual(vertices[:, 1].min(), bridge.PARAMETERS.bottom_y_m)
        self.assertEqual(vertices[:, 1].max(), bridge.PARAMETERS.top_y_m)


if __name__ == "__main__":
    unittest.main()
