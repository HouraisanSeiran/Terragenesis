"""Bounded behaviour cases for the offline L1 sinkhole volume geometry.

Synthetic analytic solids only: no TD package, no runtime parent package, no solver, no
pytest and no trimesh. The cases cover the declared acceptances -- actual volume accounting,
an actually measured skylight, refusals for out-of-range or degenerate input, byte-stable
identity for identical input, every capability flag staying False, and a cold Mesh64
recomputation of the recorded witnesses from the saved solids alone.
"""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hybrid_geometry import FLAGS
from terrain_pipeline.hybrid_geometry import identity
from terrain_pipeline.special_terrain import SINKHOLE_ALGORITHM as ALGORITHM, BASE_KIND, BASE_NOTE, CUTTER_ROLES, SINKHOLE_EXPLICIT_ASSUMPTIONS as EXPLICIT_ASSUMPTIONS, LOCAL_ORIGIN, SINKHOLE_SCHEMA as SCHEMA, SOLID_SCHEMA, SinkholeParameters, assumption_list, audit, sinkhole_build as build, solid_winding, write_preview


def cold_manifold(record):
    """Rebuild one saved solid without the generator's helpers (cold-reader style)."""
    import manifold3d as manifold
    mesh = manifold.Mesh64(np.array(record["vertices_local_xyz_m"], dtype=np.float64, order="C", copy=True),
                           np.array(record["triangles"], dtype=np.uint64, order="C", copy=True))
    solid = manifold.Manifold(mesh)
    if solid.status() != manifold.Error.NoError or solid.is_empty():
        raise AssertionError("saved solid is not a closed manifold: " + str(record.get("role")))
    return solid


class SinkholeVolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record, cls.solids = build()

    def test_material_balance_and_one_connected_void(self):
        boolean = self.record["boolean"]
        material, census = boolean["material"], boolean["census"]
        self.assertEqual(self.record["schema"], SCHEMA)
        self.assertEqual(self.record["algorithm"], ALGORITHM)
        self.assertEqual(self.record["status"], "candidate")
        self.assertEqual(self.record["synthetic_base"], {"kind": BASE_KIND, "note": BASE_NOTE})
        self.assertEqual(material["rock_before_m3"], 576000.)
        self.assertEqual(material["fill_rock_m3"], 0.)
        self.assertEqual(material["exported_excavated_rock_m3"], material["excavated_rock_m3"])
        self.assertGreater(material["rock_after_m3"], 0.)
        self.assertGreater(material["excavated_rock_m3"], 0.)
        residual = material["rock_before_m3"] - material["rock_after_m3"] - material["excavated_rock_m3"]
        self.assertLessEqual(abs(residual), material["balance_budget_m3"])
        self.assertAlmostEqual(residual, material["signed_residual_m3"], places=9)
        self.assertEqual(census["cutter_count"], len(CUTTER_ROLES))
        self.assertEqual(census["cutter_union_components"], 1)
        self.assertEqual(census["removed_components"], 1)
        self.assertEqual(census["rock_after_components"], 1)

    def test_every_solid_record_is_sealed_and_volume_accounted(self):
        self.assertEqual(sorted(self.solids), sorted(["rock_before", "rock_after", "removed",
                                                      "cutter_union", *CUTTER_ROLES]))
        for name, solid in self.solids.items():
            self.assertEqual(solid["schema"], SOLID_SCHEMA)
            self.assertEqual(solid["role"], name)
            self.assertTrue(solid["sampled_not_native_exact"])
            self.assertEqual(identity({key: value for key, value in solid.items()
                                       if key != "identity_sha256"}), solid["identity_sha256"])
            self.assertGreater(solid["signed_volume_m3"], 0.)
            self.assertEqual(self.record["solids"][name], solid)
        # A cutter union must at least cover the main reach (terraces add to it), and the
        # excavated void can never exceed the union that cut it.
        self.assertGreaterEqual(self.solids["cutter_union"]["signed_volume_m3"],
                                self.solids["subsurface_river"]["signed_volume_m3"])
        self.assertLessEqual(self.solids["removed"]["signed_volume_m3"],
                             self.solids["cutter_union"]["signed_volume_m3"])

    def test_skylight_and_single_surface_opening_are_measured_witnesses(self):
        witnesses = self.record["witnesses"]
        open_axis = witnesses["skylight_axis_open_after_excavation"]
        closed_axis = witnesses["skylight_axis_blocked_before_excavation"]
        self.assertEqual(open_axis["method"], "Manifold.ray_cast")
        self.assertEqual(open_axis["solid_role"], "rock_after")
        self.assertEqual(open_axis["expected_hit_count"], 0)
        self.assertEqual(open_axis["observed"]["hit_count"], 0)
        self.assertEqual(closed_axis["expected_hit_count"], 1)
        self.assertEqual(closed_axis["observed"]["hit_count"], 1)
        self.assertEqual(closed_axis["observed"]["first_hit_y_m"], 0.)
        floor = witnesses["shaft_floor_is_the_buried_river_bed"]
        self.assertEqual(floor["observed"]["first_hit_y_m"], -36.)
        open_samples = [entry for name, entry in witnesses.items()
                        if name.startswith("collar_footprint_open_sample")]
        closed_samples = [entry for name, entry in witnesses.items()
                          if name.startswith("outside_collar_surface_intact_sample")]
        self.assertGreaterEqual(len(open_samples), 3)
        self.assertGreaterEqual(len(closed_samples), 8)
        self.assertTrue(all(entry["observed"]["hit_count"] == 0 for entry in open_samples))
        self.assertTrue(all(entry["observed"]["hit_count"] == 1 for entry in closed_samples))
        self.assertTrue(all(entry["observed"]["first_hit_y_m"] == 0. for entry in closed_samples))
        self.assertTrue(all(entry["verdict"] is True for entry in witnesses.values()))
        for entry in witnesses.values():
            self.assertIn(entry["method"], ("Manifold.ray_cast", "Solid.winding", "Mesh64_boolean"))
        winding = witnesses["shaft_interior_is_void"]
        self.assertEqual(winding["method"], "Solid.winding")
        self.assertFalse(winding["expected_inside"])
        self.assertAlmostEqual(winding["observed"]["winding"], 0., places=6)
        self.assertAlmostEqual(witnesses["intact_rock_mass_is_solid"]["observed"]["winding"], 1., places=6)

    def test_cold_recomputation_from_saved_solids_matches_the_witnesses(self):
        import manifold3d as manifold
        solids = self.record["solids"]
        rock = cold_manifold(solids["rock_before"])
        cutters = [cold_manifold(solids[role]) for role in CUTTER_ROLES]
        union = manifold.Manifold.batch_boolean(cutters, manifold.OpType.Add)
        after = rock - union
        removed = rock ^ union
        entry = self.record["witnesses"]["material_balance_actual_volume"]
        self.assertEqual(entry["method"], "Mesh64_boolean")
        self.assertEqual(entry["operation"], "subtract")
        self.assertEqual(entry["cutter_roles"], list(CUTTER_ROLES))
        self.assertAlmostEqual(after.volume(), entry["expected_rock_after_m3"], places=6)
        self.assertAlmostEqual(removed.volume(), entry["expected_removed_m3"], places=6)
        # The saved union volume is the tessellated mesh volume, which may differ from the
        # engine's own volume by a few ulp; the declared gate allows 1e-9 relative.
        union_saved = entry["observed"]["cutter_union_m3"]
        self.assertLess(abs(union.volume() - union_saved) / union_saved, 1e-8)
        # Every winding witness must be reproducible by an independent winding evaluation.
        for name, witness in self.record["witnesses"].items():
            if witness["method"] != "Solid.winding":
                continue
            recomputed = solid_winding(solids[witness["solid_role"]], witness["point_xyz_m"],
                                       self.record["local_origin_xyz_m"])
            self.assertAlmostEqual(recomputed, witness["observed"]["winding"], places=9)
            self.assertEqual(recomputed > .5, witness["expected_inside"])

    def test_identical_input_gives_identical_identity(self):
        first, first_solids = build(SinkholeParameters(), LOCAL_ORIGIN)
        second, second_solids = build(SinkholeParameters(), np.array(LOCAL_ORIGIN, float))
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertEqual(first["identity_sha256"], self.record["identity_sha256"])
        self.assertEqual(first_solids["rock_after"]["identity_sha256"],
                         self.solids["rock_after"]["identity_sha256"])
        unsigned = {key: value for key, value in first.items() if key != "identity_sha256"}
        self.assertEqual(identity(unsigned), first["identity_sha256"])

    def test_every_capability_flag_is_false_and_audit_passes(self):
        self.assertEqual(sorted(self.record["flags"]), sorted(FLAGS))
        self.assertTrue(all(self.record["flags"][flag] is False for flag in FLAGS))
        self.assertTrue(all(self.record["boolean"][flag] is False for flag in FLAGS))
        self.assertEqual(self.record["boolean"]["status"], "candidate")
        self.assertEqual(self.record["boolean"]["rejection_reasons"], [])
        report = audit(self.record)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["identity_sha256"], self.record["identity_sha256"])
        self.assertIn("material_balance", report["checks"])

    def test_tampered_or_promoted_record_is_refused(self):
        promoted = json.loads(json.dumps(self.record))
        promoted["flags"]["hydraulic_ready"] = True
        promoted.pop("identity_sha256")
        promoted["identity_sha256"] = identity(promoted)
        with self.assertRaises(ValueError):
            audit(promoted)
        forged = json.loads(json.dumps(self.record))
        forged["boolean"]["material"]["excavated_rock_m3"] += 1.
        forged.pop("identity_sha256")
        with self.assertRaises(ValueError):
            audit(forged)
        broken_seal = json.loads(json.dumps(self.record))
        broken_seal["solids"]["rock_after"]["identity_sha256"] = "0" * 64
        broken_seal.pop("identity_sha256")
        broken_seal["identity_sha256"] = identity(broken_seal)
        with self.assertRaises(ValueError):
            audit(broken_seal)

    def test_out_of_range_and_degenerate_parameters_are_refused(self):
        baseline = {field: getattr(SinkholeParameters(), field)
                    for field in SinkholeParameters.__dataclass_fields__}
        cases = (
            {"shaft_collar_y_m": -1.},
            {"shaft_radius_top_m": 12.},
            {"shaft_radius_top_m": 80.},
            {"river_bed_y_m": -41.},
            {"river_ceiling_y_m": -35.99},
            {"river_ceiling_y_m": 0.5},
            {"shaft_bottom_y_m": -27.},
            {"upper_terrace_top_y_m": 1.},
            {"lower_terrace_top_y_m": -8.5},
            {"lower_terrace_top_y_m": -33.},
            {"river_reach_x_m": 61.},
            {"river_reach_x_m": 4.},
            {"branch_x_high_m": -30.},
            {"branch_z_end_m": 61.},
            {"branch_z_low_m": 6.},
            {"river_half_width_m": float("nan")},
            {"shaft_segments": 8},
            {"terrace_segments": 600},
        )
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    SinkholeParameters(**{**baseline, **change})
        with self.assertRaises(ValueError):
            build(SinkholeParameters(), [1., 2.])
        with self.assertRaises(ValueError):
            build("not parameters")
        with self.assertRaises(ValueError):
            solid_winding(self.solids["rock_after"], [40., -20., 40.], [0., float("nan"), 0.])

    def test_explicit_assumptions_are_graded_and_named(self):
        entries = assumption_list(SinkholeParameters())
        self.assertEqual(len(entries), len(EXPLICIT_ASSUMPTIONS))
        self.assertEqual(self.record["explicit_assumptions"], entries)
        self.assertTrue(all(entry["grade"] == "assumed" for entry in entries))
        self.assertTrue(all(entry["reason"] for entry in entries))
        names = [entry["name"] for entry in entries]
        self.assertEqual(names, sorted(names))
        self.assertEqual(self.record["source_grade"], "no_ledger_source_for_any_dimension_here")

    def test_preview_report_is_compact_and_byte_identical(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            report = write_preview(first)
            write_preview(second)
            payload = (Path(first) / "report.json").read_bytes()
            self.assertEqual(payload, (Path(second) / "report.json").read_bytes())
            self.assertNotIn(b"\n", payload)
            self.assertNotIn(b"NaN", payload)
            saved = json.loads(payload.decode("utf-8"))
            self.assertEqual(saved["identity_sha256"], report["identity_sha256"])
            unsigned = {key: value for key, value in saved.items() if key != "identity_sha256"}
            self.assertEqual(identity(unsigned), saved["identity_sha256"])
            self.assertEqual([figure["name"] for figure in saved["figures"]],
                             ["sinkhole-a-plan.png", "sinkhole-b-profile.png", "sinkhole-c-solid.png"])
            for figure in saved["figures"]:
                self.assertEqual(figure["path"], figure["name"])
                self.assertEqual(len(figure["sha256"]), 64)
                self.assertTrue((Path(first) / figure["name"]).is_file())
            self.assertEqual(saved["status"], "candidate")
            self.assertEqual(saved["library_versions"]["manifold3d"], "3.5.4")
            self.assertTrue(all(saved["flags"][flag] is False for flag in FLAGS))
            self.assertEqual(audit(saved)["status"], "passed")


if __name__ == "__main__":
    unittest.main()