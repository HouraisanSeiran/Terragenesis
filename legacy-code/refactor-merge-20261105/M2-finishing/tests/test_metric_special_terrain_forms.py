"""Contract tests for offline special-terrain field forms."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as ALGORITHM, KINDS, PARAMETER_SOURCES, METRIC_FORMS_SCHEMA as SCHEMA, FormTarget, SpecialFormRecipe, analytic_base_chart, build_special_form_vdm, form_preset, load_special_form_vdm, pillar_field_targets, save_special_form_vdm, validate_special_form_vdm
from terrain_pipeline.common_infra import file_sha256
from tools import audit_special_terrain_forms as auditor
from tools import prepare_special_terrain_forms as prepare


class SpecialTerrainFormsTests(unittest.TestCase):
    def build(self, kind):
        recipe = form_preset(kind)
        chart = analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m,
                                    spacing_m=recipe.spacing_m)
        mask = np.zeros(chart.shape[:2], dtype=bool)
        return build_special_form_vdm(chart, recipe=recipe, protected_mask=mask,
                                      source_identity="base-1", protection_identity="mask-1")

    def test_four_kinds_are_distinct_and_replayable(self):
        self.assertEqual(KINDS, {"volcanic_plug", "inselberg", "sandstone_pillar_field",
                                 "karst_tower_field"})
        reliefs = {}
        for kind in sorted(KINDS):
            first, second = self.build(kind), self.build(kind)
            self.assertTrue(validate_special_form_vdm(first))
            self.assertEqual(first["identity_sha256"], second["identity_sha256"])
            self.assertEqual(first["metadata"]["schema"], SCHEMA)
            self.assertEqual(first["metadata"]["algorithm"], ALGORITHM)
            self.assertEqual(first["metadata"]["base"], "synthetic_analytic")
            for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable",
                         "self_intersection_verified"):
                self.assertIs(first["metadata"][flag], False)
            displacement = first["arrays"]["displacement_xyz_m"]
            self.assertTrue(np.all(displacement[:, :, 0] == 0))
            self.assertTrue(np.all(displacement[:, :, 2] == 0))
            self.assertTrue(np.all(displacement[0] == 0))
            self.assertTrue(np.all(displacement[-1] == 0))
            self.assertTrue(np.all(displacement[:, 0] == 0))
            self.assertTrue(np.all(displacement[:, -1] == 0))
            self.assertGreater(displacement[:, :, 1].max(), 0)
            reliefs[kind] = displacement[:, :, 1].tobytes()
        self.assertEqual(len(set(reliefs.values())), 4)

    def test_provenance_is_recorded_for_every_kind(self):
        for kind in sorted(KINDS):
            sources = PARAMETER_SOURCES[kind]
            self.assertTrue(sources)
            for field, (grade, reference) in sources.items():
                self.assertIn(grade, ("verified", "secondary", "assumed"))
                self.assertIn("parameters-and-sources.md", reference)
            result = self.build(kind)
            recorded = result["metadata"]["parameter_sources"][kind]
            self.assertEqual(set(recorded), set(sources))

    def test_synthetic_base_is_declared_and_never_real_detail(self):
        result = self.build("volcanic_plug")
        self.assertEqual(result["metadata"]["base"], "synthetic_analytic")
        self.assertNotIn("td_fine_bed", json.dumps(result["metadata"]))
        with self.assertRaises(ValueError):
            build_special_form_vdm(
                analytic_base_chart(size_x_m=400.0, size_z_m=400.0, spacing_m=1.0),
                recipe=form_preset("volcanic_plug"),
                protected_mask=np.zeros((401, 401), bool), source_identity="s",
                protection_identity="p", base_kind="real_dem")

    def test_rejects_unknown_kind_and_bad_targets(self):
        with self.assertRaises(ValueError):
            SpecialFormRecipe("karst_cave", 100.0, 100.0, 1.0, 10.0, (
                FormTarget("x", 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, "assumed", "r"),), 1)
        with self.assertRaises(ValueError):
            FormTarget("x", 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, "guessed", "r")
        with self.assertRaises(ValueError):
            FormTarget("x", 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, "assumed", "  ")
        with self.assertRaises(ValueError):
            FormTarget("x", 0.0, 0.0, 0.0, -1.0, 5.0, 5.0, "assumed", "r")
        with self.assertRaises(ValueError):
            SpecialFormRecipe("inselberg", 900.0, 900.0, 1.0, 10.0, (
                FormTarget("a", 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, "assumed", "r"),
                FormTarget("a", 50.0, 0.0, 0.0, 10.0, 5.0, 5.0, "assumed", "r")), 1)
        with self.assertRaises(ValueError):
            SpecialFormRecipe("inselberg", 900.0, 900.0, 1.0, 10.0, (), 1)
        with self.assertRaises(ValueError):
            form_preset("karst_cave")

    def test_sampling_gate_and_collar(self):
        with self.assertRaises(ValueError):
            build_special_form_vdm(
                analytic_base_chart(size_x_m=600.0, size_z_m=600.0, spacing_m=30.0),
                recipe=form_preset("volcanic_plug"),
                protected_mask=np.zeros((21, 21), bool), source_identity="s",
                protection_identity="p")
        shifted = SpecialFormRecipe("volcanic_plug", 410.0, 410.0, 1.0, 50.0, (
            FormTarget("moved", 0.0, 250.0, 0.0, 264.0, 152.5, 152.5, "secondary", "r"),),
            20261003)
        with self.assertRaises(ValueError):
            build_special_form_vdm(
                analytic_base_chart(size_x_m=410.0, size_z_m=410.0, spacing_m=1.0),
                recipe=shifted, protected_mask=np.zeros((411, 411), bool),
                source_identity="s", protection_identity="p")
        with self.assertRaises(ValueError):
            analytic_base_chart(size_x_m=100.0, size_z_m=100.0, spacing_m=3.0)

    def test_protection_blocks_displacement(self):
        recipe = form_preset("volcanic_plug")
        chart = analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m,
                                    spacing_m=recipe.spacing_m)
        mask = np.zeros(chart.shape[:2], dtype=bool)
        mask[205, 205] = True
        result = build_special_form_vdm(chart, recipe=recipe, protected_mask=mask,
                                        source_identity="s", protection_identity="p")
        self.assertEqual(float(result["arrays"]["displacement_xyz_m"][205, 205, 1]), 0.0)
        unprotected = build_special_form_vdm(
            chart, recipe=recipe, protected_mask=np.zeros(chart.shape[:2], dtype=bool),
            source_identity="s", protection_identity="p")
        self.assertGreater(float(unprotected["arrays"]["displacement_xyz_m"][205, 205, 1]), 0.0)

    def test_roundtrip_and_tampering(self):
        result = self.build("inselberg")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "form.npz"
            save_special_form_vdm(path, result)
            loaded = load_special_form_vdm(path, expected_sha256=file_sha256(path),
                                           expected_identity=result["identity_sha256"])
            for key in result["arrays"]:
                np.testing.assert_array_equal(loaded["arrays"][key], result["arrays"][key])
            self.assertEqual(loaded["metadata"], result["metadata"])
            with self.assertRaises(ValueError):
                load_special_form_vdm(path, expected_sha256="0" * 64,
                                      expected_identity=result["identity_sha256"])
            with self.assertRaises(ValueError):
                load_special_form_vdm(path, expected_sha256=file_sha256(path),
                                      expected_identity="0" * 64)
        for mutation in ({"publishable": True}, {"base": "real_dem"}, {"source_identity": ""}):
            with self.subTest(mutation=mutation):
                forged = {**result, "metadata": {**result["metadata"], **mutation}}
                with self.assertRaises(ValueError):
                    validate_special_form_vdm(forged)
        changed = {**result, "arrays": {**result["arrays"],
                                       "vertices_xyz_m": result["arrays"]["vertices_xyz_m"] + 1.0}}
        with self.assertRaises(ValueError):
            validate_special_form_vdm(changed)

    def test_pillar_field_jitter_is_seeded(self):
        kwargs = dict(prefix="p", rows=2, cols=2, pitch_m=10.0, radius_m=2.0,
                      height_band_m=(10.0, 20.0), jitter_fraction=0.2,
                      source_grade="assumed", source_ref="r")
        self.assertEqual(pillar_field_targets(seed=7, **kwargs),
                         pillar_field_targets(seed=7, **kwargs))
        self.assertNotEqual(pillar_field_targets(seed=7, **kwargs),
                            pillar_field_targets(seed=8, **kwargs))
        with self.assertRaises(ValueError):
            pillar_field_targets(seed=7, **{**kwargs, "jitter_fraction": 0.6})
        with self.assertRaises(ValueError):
            pillar_field_targets(seed=7, **{**kwargs, "height_band_m": (20.0, 10.0)})

    def test_independent_cold_audit_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            self.assertEqual(prepare.main(["--output", str(output)]), 0)
            manifest = json.loads((output / "manifest-report.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["forms"]), set(KINDS))
            audited = {}
            for kind, entry in manifest["forms"].items():
                report = auditor.audit_bundle(output / entry["file"],
                                              expected_sha256=entry["sha256"])
                self.assertEqual(report["identity_sha256"], entry["identity_sha256"])
                self.assertLess(report["max_replay_difference_m"], auditor.TOLERANCE)
                self.assertEqual(report["status"], "candidate")
                self.assertTrue(all(value is False for value in report["flags"].values()))
                self.assertTrue(all(report["perimeter_zero"].values()))
                self.assertGreater(report["mesh"]["min_area_ratio"], 0.0)
                audited[kind] = report
            self.assertEqual(len(audited), 4)
            self.assertEqual(auditor.main([str(output)]), 0)
            self.assertEqual(json.loads((output / "independent-audit.json").read_text(
                encoding="utf-8"))["generator_imported"], False)


if __name__ == "__main__":
    unittest.main()
