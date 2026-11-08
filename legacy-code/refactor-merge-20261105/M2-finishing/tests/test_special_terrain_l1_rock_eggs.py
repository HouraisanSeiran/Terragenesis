"""Bounded behaviour and cold-audit cases for the L1 rock-egg pile (P5.4).

Synthetic analytic solids only: no TD package, no runtime parent package, no solver. The
frozen conduit module is imported only for its reusable ray cast primitive; nothing here
writes to any existing file.
"""

import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline import special_terrain as eggs
from terrain_pipeline.hybrid_geometry import ray_hits
from terrain_pipeline.hybrid_geometry import identity
from terrain_pipeline.hybrid_geometry import FLAGS, BooleanParameters, SOLID_SCHEMA, census, combine, solid_from_record

ALLOWED_METHODS = ("Manifold.ray_cast", "Solid.winding", "Mesh64_boolean")
CONTRACT_KEYS = {"schema", "algorithm", "status", "synthetic_base", "parameters",
                 "explicit_assumptions", "solids", "boolean", "witnesses", "flags",
                 "library_versions", "figures", "identity_sha256"}


def unsealed(record):
    return {key: value for key, value in record.items() if key != "identity_sha256"}


def independent_union(records, library=None):
    """Rebuild Manifold from saved meshes only, then Add -- what a cold audit reader does."""
    library = library or __import__("manifold3d")
    solids = [solid_from_record(record, record["role"]) for record in records]
    return library.Manifold.batch_boolean(solids, library.OpType.Add)


class RockEggPileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document, cls.artifacts = eggs.rock_eggs_build()
        cls.solids = cls.document["solids"]
        cls.pile = cls.solids[eggs.PILE_ROLE]
        cls.solid = solid_from_record(cls.pile, "pile")

    def test_at_least_seven_closed_eggs_are_saved_with_recomputable_identity(self):
        self.assertGreaterEqual(len(eggs.EGGS), 7)
        self.assertEqual(len(eggs.EGGS), 8)
        self.assertEqual(len(self.solids), len(eggs.EGGS) + 1)
        roles = set()
        for item in eggs.EGGS:
            record = self.solids[item.egg_id]
            self.assertEqual(record["schema"], SOLID_SCHEMA)
            self.assertEqual(record["role"], item.egg_id)
            self.assertTrue(record["sampled_not_native_exact"])
            self.assertGreater(record["signed_volume_m3"], 0.)
            self.assertEqual(record["identity_sha256"], identity(unsealed(record)))
            self.assertEqual(record["local_origin_xyz_m"], eggs.ROCK_EGGS_LOCAL_ORIGIN.tolist())
            # The mesh is inscribed in the ideal sphere, so it is a little smaller than 4/3 pi r^3.
            ideal = 4. / 3. * math.pi * item.radius_m**3
            self.assertGreater(record["signed_volume_m3"], ideal * .97)
            self.assertLess(record["signed_volume_m3"], ideal)
            roles.add(record["role"])
        self.assertEqual(len(roles), len(eggs.EGGS))
        # A declared radius spread, not eight clones.
        radii = sorted(item.radius_m for item in eggs.EGGS)
        self.assertGreaterEqual(radii[-1] - radii[0], 1.)
        self.assertGreaterEqual(len(set(radii)), 4)
        self.assertLessEqual(radii[-1], 3.)

    def test_pile_union_is_closed_with_the_declared_component_census(self):
        components = census(self.solid)
        self.assertEqual(components, eggs.EXPECTED_COMPONENTS)
        self.assertEqual(self.document["assembly"]["connected_components"], components)
        self.assertEqual(self.document["assembly"]["connected_components_declared"], components)
        # Fewer than the egg count (some really merged) and more than one (some really separate).
        self.assertGreater(components, 1)
        self.assertLess(components, len(eggs.EGGS))
        self.assertGreater(self.document["assembly"]["sum_of_parts_m3"],
                           self.document["assembly"]["signed_volume_m3"])
        self.assertEqual(self.document["assembly"]["fill_rock_m3"], 0.)
        self.assertEqual(self.document["assembly"]["excavated_rock_m3"], 0.)
        self.assertEqual(self.document["identity_sha256"], identity(unsealed(self.document)))

    def test_separated_pair_is_the_exact_sum_and_stacked_pair_really_merges(self):
        separated = self.document["witnesses"]["separated_pair_union_is_exact_sum"]
        stacked = self.document["witnesses"]["stacked_pair_union_is_strictly_smaller"]
        self.assertEqual(separated["method"], "Mesh64_boolean")
        self.assertEqual(stacked["method"], "Mesh64_boolean")
        self.assertTrue(separated["verdict"])
        self.assertTrue(stacked["verdict"])
        self.assertLessEqual(separated["observed"]["relative_difference"], 1e-12)
        self.assertGreater(separated["observed"]["analytic_surface_gap_m"], 0.)
        self.assertEqual(separated["observed"]["connected_components"], 2)
        self.assertLess(stacked["observed"]["union_m3"], stacked["observed"]["sum_of_parts_m3"] - 1e-6)
        self.assertLess(stacked["observed"]["analytic_surface_gap_m"], 0.)
        self.assertEqual(stacked["observed"]["connected_components"], 1)
        # Independent recomputation straight from the saved meshes.
        for witness in (separated, stacked):
            chosen = [self.solids[role] for role in witness["cutter_roles"]]
            union = independent_union(chosen)
            self.assertAlmostEqual(union.volume(), witness["observed"]["union_m3"], places=9)
            self.assertAlmostEqual(union.volume(), witness["expected_union_m3"], places=9)
        sum_parts = separated["observed"]["sum_of_parts_m3"]
        self.assertAlmostEqual(sum_parts,
                               sum(self.solids[role]["signed_volume_m3"] for role in separated["cutter_roles"]),
                               places=9)

    def test_hover_void_is_outside_zero_overlap_and_open_to_free_space(self):
        winding = self.document["witnesses"]["hover_void_midpoint_is_outside"]
        reach = self.document["witnesses"]["hover_void_is_open_to_free_space"]
        clearance = self.document["witnesses"]["hover_clearance_is_bracketed_by_two_surfaces"]
        self.assertTrue(winding["verdict"])
        self.assertTrue(reach["verdict"])
        self.assertTrue(clearance["verdict"])
        self.assertEqual(winding["solid_role"], eggs.PILE_ROLE)
        self.assertFalse(winding["expected_inside"])
        self.assertLessEqual(abs(winding["observed"]["winding"]), eggs.WINDING_TOLERANCE)
        self.assertEqual(winding["observed"]["probe_overlap_m3"], 0.)
        self.assertEqual(reach["expected_hit_count"], 0)
        self.assertEqual(reach["observed"]["hit_count"], 0)
        self.assertEqual(len(clearance["observed"]["hits"]), 2)
        measured = clearance["observed"]["measured_mesh_clearance_m"]
        self.assertGreater(measured, 0.)
        # The mesh is inscribed in the ideal spheres, so the mesh clearance can only be larger.
        self.assertGreaterEqual(measured, clearance["observed"]["analytic_surface_gap_m"])
        self.assertLess(clearance["observed"]["mesh_clearance_minus_analytic_gap_m"], .01)
        self.assertTrue(clearance["observed"]["lateral_support"]["actually_interpenetrates"])
        # Independent recomputation from the saved pile mesh.
        point = np.asarray(winding["point_xyz_m"], float)
        self.assertEqual(eggs.rock_eggs_winding_number(self.pile, point), winding["observed"]["winding"])
        self.assertEqual(eggs.probe_overlap_m3(self.solid, point), 0.)
        hits = ray_hits(self.solid, reach["from_xyz_m"], reach["to_xyz_m"], eggs.ROCK_EGGS_LOCAL_ORIGIN)
        self.assertEqual(len(hits), 0)
        axis = ray_hits(self.solid, clearance["from_xyz_m"], clearance["to_xyz_m"], eggs.ROCK_EGGS_LOCAL_ORIGIN)
        self.assertEqual(len(axis), 2)
        self.assertAlmostEqual(float(np.linalg.norm(np.asarray(axis[1]["position_xyz_m"], float)
                                                    - np.asarray(axis[0]["position_xyz_m"], float))),
                               measured, places=9)

    def test_bad_geometry_and_declared_shortfalls_are_refused(self):
        with self.assertRaises(ValueError):
            eggs.EggSpec("egg-x", (0., 0., 0.), 4.0, "cluster", "too_tall")
        with self.assertRaises(ValueError):
            eggs.EggSpec("egg-x", (0., 0., "z"), 2.0, "cluster", "not_a_number")
        with self.assertRaises(ValueError):
            eggs.EggSpec("egg-x", (0., 0., 0.), 2.0, "bogus_group", "bad_group")
        with self.assertRaises(ValueError):
            eggs.EggSpec("", (0., 0., 0.), 2.0, "cluster", "empty_id")
        # Declaring fewer components than the geometry really has must be refused, not adjusted.
        records = eggs.build_records()
        with self.assertRaises(ValueError):
            combine(records, eggs.ROCK_EGGS_LOCAL_ORIGIN, "bad", eggs.parameters(),
                    minimum_components=eggs.EXPECTED_COMPONENTS + 1)
        # A component limit below the real census is refused as well.
        with self.assertRaises(ValueError):
            combine(records, eggs.ROCK_EGGS_LOCAL_ORIGIN, "bad",
                    BooleanParameters(solids_spacing_m=1., component_limit=2), minimum_components=1)
        # A tampered saved volume is refused instead of being used as a Boolean operand.
        tampered = dict(self.pile)
        tampered["signed_volume_m3"] = tampered["signed_volume_m3"] + 1.
        with self.assertRaises(ValueError):
            solid_from_record(tampered, "tampered")

    def test_evidence_document_contract_is_cold_auditable_and_reproducible(self):
        document = self.document
        self.assertTrue(CONTRACT_KEYS.issubset(document.keys()))
        self.assertEqual(document["schema"], eggs.ROCK_EGGS_SCHEMA)
        self.assertEqual(document["algorithm"], eggs.ROCK_EGGS_ALGORITHM)
        self.assertEqual(document["status"], "candidate")
        self.assertEqual(document["synthetic_base"],
                         {"kind": "synthetic_analytic", "note": "not TD native terrain, not surveyed"})
        self.assertEqual(set(document["flags"]), set(FLAGS))
        self.assertTrue(all(value is False for value in document["flags"].values()))
        for flag in FLAGS:
            self.assertIs(document[flag], False)
        self.assertIn("manifold3d", document["library_versions"])
        self.assertIn("numpy", document["library_versions"])
        self.assertTrue(document["explicit_assumptions"])
        for entry in document["explicit_assumptions"]:
            self.assertEqual(set(entry), {"name", "value", "grade", "reason"})
            self.assertEqual(entry["grade"], "assumed")
            self.assertTrue(entry["reason"])
        for name, witness in document["witnesses"].items():
            self.assertIn(witness["method"], ALLOWED_METHODS, name)
            self.assertIs(witness["verdict"], True, name)
            self.assertTrue(witness["claim"], name)
            self.assertIn("observed", witness, name)
            if witness["method"] == "Mesh64_boolean":
                self.assertTrue(witness["cutter_roles"], name)
                for role in witness["cutter_roles"]:
                    self.assertIn(role, document["solids"], name)
            else:
                self.assertIn(witness["solid_role"], document["solids"], name)
        self.assertEqual(document["boolean"]["status"], "candidate")
        self.assertEqual(document["boolean"]["schema"], "td-hybrid-rock-boolean-result-v1")
        # The whole report is reproducible: two builds seal to the same identity.
        second, _ = eggs.rock_eggs_build()
        self.assertEqual(eggs.write_canonical_bytes(second), eggs.write_canonical_bytes(document))
        self.assertEqual(second["identity_sha256"], document["identity_sha256"])

    def test_preview_writes_three_auditable_figures_and_a_compact_report(self):
        with tempfile.TemporaryDirectory() as directory:
            document, artifacts = eggs.rock_eggs_build()
            figures = eggs.render_preview(artifacts["rock_after"], directory, artifacts["hover"])
            document["figures"] = figures
            from terrain_pipeline.hybrid_geometry import seal
            seal(document)
            report = Path(directory) / eggs.REPORT_NAME
            report.write_bytes(eggs.write_canonical_bytes(document))
            self.assertEqual(len(figures), 3)
            self.assertEqual(report.read_bytes(), eggs.write_canonical_bytes(document))
            # Compact: one line, sorted keys -- exactly the form the cold audit reader consumes.
            raw = report.read_text(encoding="utf-8")
            self.assertEqual(len(raw.splitlines()), 1)
            reread = json.loads(raw)
            self.assertEqual(reread["identity_sha256"], document["identity_sha256"])
            self.assertEqual(reread["identity_sha256"], identity(unsealed(reread)))
            for figure in figures:
                path = Path(directory) / figure["path"]
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 1000)
                self.assertEqual(len(figure["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
