"""Contract tests for facet roughness plus hydraulic dissection on L0 charts.

Structural assertions run on a deliberately small analytic chart so the whole suite
stays cheap; the four production presets are exercised for identity, collar and
provenance consistency without the large route-diagnostic sweeps.
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import KINDS, FormTarget, SpecialFormRecipe, analytic_base_chart, build_special_form_vdm
from terrain_pipeline.special_terrain import METRIC_SURFACE_ALGORITHM as ALGORITHM, ARRAY_KEYS, KERNEL_FILES, RETIRED_RECIPE_FIELDS, METRIC_SURFACE_SCHEMA as SCHEMA, SUPERSEDES_ALGORITHM, DissectionRecipe, FacetRoughnessRecipe, build_special_form_surface, kernel_revisions, load_special_form_surface, save_special_form_surface, surface_preset, validate_special_form_surface
from terrain_pipeline.common_infra import file_sha256, identity

SMALL_SIZE_M = 40.0
SMALL_SPACING_M = 0.5
SMALL_RADIUS_M = 8.0
SMALL_HEIGHT_M = 20.0


def small_parent():
    recipe = SpecialFormRecipe("volcanic_plug", SMALL_SIZE_M, SMALL_SIZE_M, SMALL_SPACING_M, 8.0,
                               (FormTarget("tiny", 0.0, 0.0, 0.0, SMALL_HEIGHT_M, SMALL_RADIUS_M,
                                           SMALL_RADIUS_M, "assumed", "parameters-and-sources.md#4.1"),),
                               20261003)
    chart = analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m,
                                spacing_m=recipe.spacing_m)
    mask = np.zeros(chart.shape[:2], dtype=bool)
    return build_special_form_vdm(chart, recipe=recipe, protected_mask=mask,
                                  source_identity="unit-base", protection_identity="unit-mask")


def small_recipes():
    roughness = FacetRoughnessRecipe(20261003, ((12.0, 1.0), (8.0, 0.5), (5.0, 0.25)), 0.10)
    # This chart needs 14 / 31 / 22 sweeps at a 1 mm tolerance, so the budget below is the
    # one the relaxation actually asks for rather than a hopeful constant; the test asserts
    # the converged path *and* the forgeries that pretend to it.
    dissection = DissectionRecipe(repose_angle_deg=34.0, steps=3, detachment_per_step_m=4.0,
                                  maximum_cut_fraction=0.05, maximum_incision_fraction=0.15,
                                  mobile_fraction=0.03, mobile_minimum_m=0.75,
                                  deposition_fraction=0.35, tolerance_m=1e-3, max_sweeps=64)
    return roughness, dissection


class SpecialTerrainSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = small_parent()
        cls.roughness, cls.dissection = small_recipes()
        cls.result = build_special_form_surface(cls.parent, roughness=cls.roughness,
                                                dissection=cls.dissection)

    def test_identity_is_deterministic_and_supersedes_v1(self):
        repeat = build_special_form_surface(self.parent, roughness=self.roughness,
                                           dissection=self.dissection)
        self.assertTrue(validate_special_form_surface(repeat))
        self.assertEqual(self.result["identity_sha256"], repeat["identity_sha256"])
        metadata = self.result["metadata"]
        self.assertEqual(metadata["schema"], SCHEMA)
        self.assertEqual(metadata["algorithm"], ALGORITHM)
        self.assertEqual(metadata["supersedes_algorithm"], SUPERSEDES_ALGORITHM)
        self.assertEqual(metadata["parent_identity_sha256"], self.parent["identity_sha256"])
        self.assertEqual(self.result["identity_sha256"], identity(self.result["arrays"], metadata))
        for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable",
                     "self_intersection_verified"):
            self.assertIs(metadata[flag], False)
        self.assertEqual(set(metadata["kernel_revisions"]), set(KERNEL_FILES))
        self.assertEqual(metadata["kernel_revisions"], kernel_revisions())

    def test_facet_wavelengths_are_absolute_metres_and_metadata_only(self):
        metadata = self.result["metadata"]
        scales = self.roughness.scales
        self.assertEqual(metadata["facet_wavelengths_m"],
                         [[cells * SMALL_SPACING_M, weight] for cells, weight in scales])
        # The declared wavelength must be recorded in metres, never in cells.
        self.assertNotEqual(metadata["facet_wavelengths_m"], [list(pair) for pair in scales])
        # Recipe records are stored in their JSON-native form, so an in-memory bundle and
        # the same bundle after a round-trip compare field for field instead of by tuple
        # versus list.
        self.assertEqual(metadata["facet_recipe"]["scales"],
                         [list(pair) for pair in scales])
        self.assertEqual(metadata["facet_recipe"], json.loads(json.dumps(metadata["facet_recipe"])))

    def test_retired_recipe_field_is_refused(self):
        self.assertEqual(RETIRED_RECIPE_FIELDS, ("immobile_rock_fraction",))
        recipe = self.result["metadata"]["dissection_recipe"]
        self.assertFalse(any(field in recipe for field in RETIRED_RECIPE_FIELDS))
        for field in RETIRED_RECIPE_FIELDS:
            with self.subTest(field=field):
                forged = {**self.result, "metadata": {
                    **self.result["metadata"],
                    "dissection_recipe": {**recipe, field: 0.38}}}
                with self.assertRaises(ValueError):
                    validate_special_form_surface(forged)

    def test_collar_and_protection_are_untouched(self):
        arrays = self.result["arrays"]
        change = arrays["erosion_change_m"]
        self.assertTrue(np.all(change[0] == 0.0))
        self.assertTrue(np.all(change[-1] == 0.0))
        self.assertTrue(np.all(change[:, 0] == 0.0))
        self.assertTrue(np.all(change[:, -1] == 0.0))
        mask = arrays["protected_mask"]
        self.assertFalse(mask.any())
        surface = arrays["surface_xyz_m"]
        reference = arrays["reference_xyz_m"]
        for edge in (surface[0], surface[-1], surface[:, 0], surface[:, -1]):
            self.assertTrue(np.isfinite(edge).all())
        self.assertTrue(np.array_equal(surface[0], reference[0]))
        self.assertTrue(np.array_equal(surface[-1], reference[-1]))

    def test_surface_is_reference_plus_roughened_relief_plus_change(self):
        arrays = self.result["arrays"]
        self.assertEqual(set(arrays), ARRAY_KEYS)
        vertical = np.zeros_like(arrays["reference_xyz_m"])
        vertical[:, :, 1] = arrays["erosion_change_m"]
        recomputed = arrays["reference_xyz_m"] + arrays["displacement_xyz_m"] + vertical
        self.assertTrue(np.array_equal(arrays["surface_xyz_m"], recomputed))
        self.assertTrue(np.array_equal(arrays["vertices_xyz_m"],
                                       arrays["surface_xyz_m"].reshape(-1, 3)))
        # Facet noise must actually differ from the smooth parent relief.
        self.assertGreater(float(np.max(np.abs(arrays["displacement_xyz_m"][:, :, 1]
                                              - self.parent["arrays"]["displacement_xyz_m"][:, :, 1]))),
                           0.0)

    def test_ledgers_are_separate_and_never_cancel(self):
        ledger = self.result["metadata"]["ledger"]
        for key in ("detachment_ledger_m3", "transport_deposition_ledger_m3",
                    "relaxation_transferred_ledger_m3"):
            self.assertGreaterEqual(ledger[key], 0.0)
        self.assertGreater(ledger["detachment_ledger_m3"], 0.0)
        self.assertGreater(ledger["incised_cells"], 0)
        self.assertGreater(ledger["maximum_incision_m"], 0.0)
        self.assertLessEqual(ledger["maximum_incision_m"],
                             ledger["rock_floor_depth_m"] + 1e-9)
        self.assertEqual(len(ledger["steps"]), self.dissection.steps)
        self.assertEqual([step["step_index"] for step in ledger["steps"]],
                         list(range(self.dissection.steps)))
        # The transport phase may not deposit more than it was given plus what the
        # relaxation handed it, otherwise the ledger would describe a source.
        total_detached = ledger["detachment_ledger_m3"]
        total_deposited = ledger["transport_deposition_ledger_m3"]
        total_relaxed = ledger["relaxation_transferred_ledger_m3"]
        self.assertLessEqual(total_deposited, total_detached + total_relaxed + 1e-6)
        phase = ledger["phase_balance"]
        self.assertEqual(phase["phase"], "hydraulic-dissection")
        self.assertEqual(phase["step_index"], self.dissection.steps - 1)
        self.assertEqual(phase["injected_bulk_m3"], 0.0)
        # The exported term and the residual must agree with the stored change array, so
        # the ledger cannot describe a different surface from the one saved.
        exported = float(np.sum(self.result["arrays"]["erosion_change_m"]) * SMALL_SPACING_M ** 2)
        self.assertAlmostEqual(phase["exported_bulk_m3"], -exported, places=9)
        self.assertAlmostEqual(ledger["net_change_ledger_m3"], exported, places=9)
        self.assertAlmostEqual(phase["raw_residual_bulk_m3"], 0.0, places=9)
        self.assertTrue(all(step["mobile_column_volume_m3"] >= 0.0 for step in ledger["steps"]))

    def test_rock_floor_is_never_penetrated(self):
        arrays = self.result["arrays"]
        change = arrays["erosion_change_m"]
        metadata = self.result["metadata"]
        # ``surface_xyz_m`` *is* the dissected bed; the change is already folded into it.
        # Adding the change again would subtract the incision twice and fake a violation.
        final = arrays["surface_xyz_m"][:, :, 1]
        # The floor is a declared depth below the *roughened* surface, so the relief it is
        # measured against is the post-facet one, not the parent chart's peak relief.
        depth = self.dissection.maximum_incision_fraction \
            * metadata["roughened_relief_reference_m"]
        base = arrays["reference_xyz_m"][:, :, 1]
        roughened = base + arrays["displacement_xyz_m"][:, :, 1]
        floor = np.minimum(np.maximum(roughened - depth, base), roughened)
        self.assertTrue(np.all(final >= floor - 1e-9))
        self.assertTrue(np.isfinite(final).all())
        # Only a rock floor can bound the cut; a mobile column that starts empty could not.
        self.assertGreater(int((final < roughened - 1e-9).sum()), 0)
        # Deposition is real in v2 -- material is carried downslope -- so the sign of the
        # change is not fixed at every cell.  What the phase does guarantee is that it
        # never imports material: transport and relaxation are internal transfers, so the
        # net change can only be what left through the open ring.
        self.assertGreater(int((change > 0.0).sum()), 0)
        self.assertLess(float(np.sum(change)), 0.0)
        # A reader that never imports the builder can still recompute both reliefs.
        self.assertEqual(metadata["roughened_relief_reference_m"], float(np.max(roughened)))
        self.assertEqual(metadata["relief_reference_m"],
                         float(np.max(self.parent["arrays"]["displacement_xyz_m"][:, :, 1])))

    def test_relaxation_convergence_is_derived_not_trusted(self):
        ledger = self.result["metadata"]["ledger"]
        recipe = self.result["metadata"]["dissection_recipe"]
        steps = ledger["steps"]
        # The flag is defined by the kernel as ``excess <= tolerance``; both operands of
        # that comparison are stored, so a reader can re-derive it instead of believing it.
        for step in steps:
            self.assertIs(step["relaxation_converged"],
                          step["relaxation_maximum_excess_m"] <= recipe["tolerance_m"])
            self.assertLessEqual(step["relaxation_sweeps"], recipe["max_sweeps"])
            self.assertFalse(step["relaxation_stalled_at_float64_resolution"])
        self.assertIs(ledger["relaxation_converged"],
                      all(step["relaxation_maximum_excess_m"] <= recipe["tolerance_m"]
                          for step in steps))
        self.assertEqual(ledger["relaxation_tolerance_m"], recipe["tolerance_m"])
        self.assertEqual(ledger["relaxation_sweep_budget"], recipe["max_sweeps"])
        self.assertEqual(ledger["relaxation_maximum_excess_m"],
                         max(step["relaxation_maximum_excess_m"] for step in steps))
        self.assertEqual(ledger["relaxation_sweeps_max"],
                         max(step["relaxation_sweeps"] for step in steps))
        # The declared budget must actually be enough for this chart, otherwise the flag
        # would be honest but the preset would still be a declaration nobody verified.
        self.assertTrue(ledger["relaxation_converged"])
        # Forging the summary flag, or one step's flag, must be refused.
        for mutation in ({"relaxation_converged": not ledger["relaxation_converged"]},
                         {"relaxation_maximum_excess_m": ledger["relaxation_maximum_excess_m"] + 1.0},
                         {"relaxation_tolerance_m": recipe["tolerance_m"] * 10.0}):
            with self.subTest(mutation=mutation):
                forged = {**self.result, "metadata": {
                    **self.result["metadata"], "ledger": {**ledger, **mutation}}}
                with self.assertRaises(ValueError):
                    validate_special_form_surface(forged)
        flipped = {**steps[0], "relaxation_converged": not steps[0]["relaxation_converged"]}
        forged = {**self.result, "metadata": {
            **self.result["metadata"],
            "ledger": {**ledger, "steps": [flipped] + steps[1:]}}}
        with self.assertRaises(ValueError):
            validate_special_form_surface(forged)

    def test_rejects_mismatched_or_forged_bundles(self):
        with self.assertRaises(ValueError):
            build_special_form_surface(self.parent, roughness=object(),
                                       dissection=self.dissection)
        with self.assertRaises(ValueError):
            build_special_form_surface(self.parent, roughness=self.roughness, dissection=object())
        with self.assertRaises(ValueError):
            FacetRoughnessRecipe(20261003, ((2.0, 1.0),), 0.10)   # below the sampling limit
        with self.assertRaises(ValueError):
            FacetRoughnessRecipe(20261003, ((12.0, 1.0),), 0.6)   # above half the relief
        with self.assertRaises(ValueError):
            DissectionRecipe(repose_angle_deg=34.0, steps=3, detachment_per_step_m=4.0,
                             maximum_cut_fraction=0.05, maximum_incision_fraction=0.0,
                             mobile_fraction=0.03, mobile_minimum_m=0.75,
                             deposition_fraction=0.35, tolerance_m=1e-6, max_sweeps=8)
        for mutation in ({"publishable": True}, {"algorithm": "other"}, {"parent_schema": "x"}):
            with self.subTest(mutation=mutation):
                forged = {**self.result, "metadata": {**self.result["metadata"], **mutation}}
                with self.assertRaises(ValueError):
                    validate_special_form_surface(forged)
        raised = {**self.result, "arrays": {**self.result["arrays"],
                                             "erosion_change_m":
                                             self.result["arrays"]["erosion_change_m"] + 1.0}}
        with self.assertRaises(ValueError):
            validate_special_form_surface(raised)

    def test_roundtrip_and_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "surface.npz"
            save_special_form_surface(path, self.result)
            digest = file_sha256(path)
            loaded = load_special_form_surface(path, expected_sha256=digest,
                                               expected_identity=self.result["identity_sha256"])
            self.assertEqual(loaded["metadata"], self.result["metadata"])
            for key in self.result["arrays"]:
                np.testing.assert_array_equal(loaded["arrays"][key], self.result["arrays"][key])
            with self.assertRaises(ValueError):
                load_special_form_surface(path, expected_sha256="0" * 64,
                                          expected_identity=self.result["identity_sha256"])
            with self.assertRaises(ValueError):
                load_special_form_surface(path, expected_sha256=digest, expected_identity="0" * 64)

    def test_every_production_preset_is_declared_and_resolved(self):
        recorded = {}
        for kind in sorted(KINDS):
            roughness, dissection = surface_preset(kind)
            self.assertEqual(roughness.seed, 20261004 if kind == "karst_tower_field" else 20261003)
            self.assertGreaterEqual(roughness.finest_cells, 4.0)
            self.assertGreater(dissection.detachment_per_step_m, 0.0)
            self.assertLess(dissection.maximum_incision_fraction, 1.0)
            self.assertEqual(dissection.deposition_fraction, 0.35)
            recorded[kind] = json.dumps(asdict_of(roughness, dissection), sort_keys=True)
            self.assertTrue(roughness.wavelengths_m(2.0)[0][0] > roughness.wavelengths_m(1.0)[0][0])
        with self.assertRaises(ValueError):
            surface_preset("karst_cave")
        self.assertEqual(len(set(recorded.values())), len(KINDS))


def asdict_of(roughness, dissection):
    from dataclasses import asdict
    return {"roughness": asdict(roughness), "dissection": asdict(dissection)}


if __name__ == "__main__":
    unittest.main()
