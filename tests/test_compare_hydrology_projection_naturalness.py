import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.compare_hydrology_projection_naturalness import (HARMONIC_TARGET_POLICY, INPUT_ARRAYS, check_same_inputs, compare, fixed_hillshade, metrics, pin)


class SameSourceNaturalnessComparisonTests(unittest.TestCase):
    def fixture(self):
        z, x = np.indices((99, 99))
        raw = 100. - .02 * x - .01 * z
        arrays = {key: np.zeros((99, 99), bool) for key in INPUT_ARRAYS}
        arrays.update(original_td_m=raw, target_height_m=raw.copy(), macro_height_m=raw.copy(),
                      projection_height_m=raw.copy(), owner_domain_id=np.zeros((99, 99), int))
        metadata = {"config": {"macro_max_abs_m": 512., "macro_absolute_volume_m3": 4.5e9},
                    "budget": {"channel_max_cut_m": 4.}, "plan_identity": "plan"}
        return arrays, metadata

    def test_every_frozen_array_and_budget_mutation_is_refused(self):
        arrays, metadata = self.fixture()
        check_same_inputs(arrays, copy.deepcopy(arrays), metadata, copy.deepcopy(metadata))
        for key in INPUT_ARRAYS:
            changed = copy.deepcopy(arrays)
            changed[key][40, 40] = not changed[key][40, 40] if changed[key].dtype == bool else changed[key][40, 40] + 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                check_same_inputs(arrays, changed, metadata, metadata)
        changed_metadata = copy.deepcopy(metadata)
        changed_metadata["config"]["macro_max_abs_m"] += 1
        with self.assertRaisesRegex(ValueError, "config"):
            check_same_inputs(arrays, arrays, metadata, changed_metadata)

    def test_constant_surface_has_undefined_direction_without_nan_or_false_score(self):
        result = metrics(np.ones((97, 97)), np.ones((97, 97)))
        self.assertIsNone(result["gradient_direction_cosine_median"])
        self.assertIsNone(result["laplacian_correlation"])
        self.assertEqual(result["gradient_direction_undefined_count"], 97**2)
        self.assertEqual(result["raise_volume_m3"], 0.)
        json.dumps(result, allow_nan=False)

    def test_hillshade_preserves_physical_light_scale_and_height_offset(self):
        z, x = np.indices((9, 9))
        flat = fixed_hillshade(np.ones((9, 9)))
        self.assertTrue(np.allclose(flat, np.sqrt(.5)))
        slope = 3. * x + 6. * z
        self.assertTrue(np.allclose(fixed_hillshade(slope), fixed_hillshade(slope + 1000.)))
        self.assertFalse(np.allclose(fixed_hillshade(slope), fixed_hillshade(10. * slope)))
        result = metrics(slope, slope + 1.)
        self.assertEqual(result["source_axis_gradient_energy"], result["output_axis_gradient_energy"])

    def test_optional_shore_bounds_and_recipe_mutations_are_refused(self):
        arrays, metadata = self.fixture()
        for key in ("ocean_stencil_mask", "lower_height_m", "upper_height_m"):
            changed = copy.deepcopy(arrays)
            changed[key] = np.zeros((99, 99))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                check_same_inputs(arrays, changed, metadata, metadata)
        for key in ("budget", "plan_identity", "fixed_lake_level_m", "support_origin_xz_m", "support_shape", "window"):
            changed = copy.deepcopy(metadata)
            changed[key] = "different"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                check_same_inputs(arrays, arrays, metadata, changed)

    def test_single_explicit_candidate_preserves_twelve_slots_and_never_inherits_certificates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            arrays, metadata = self.fixture()
            baseline = root / "baseline.npz"
            candidate = root / "candidate.npz"
            np.savez_compressed(baseline, **arrays, metadata_json=np.array(json.dumps(metadata)))
            changed = copy.deepcopy(arrays)
            changed["projection_height_m"][1:-1, 1:-1] += .1
            np.savez_compressed(candidate, **changed, metadata_json=np.array(json.dumps({**metadata, "algorithm": "candidate-witness"})))
            records = [{"seed": seed, "kind": kind, "status": "old_physical_result",
                        "projection": {"artifacts": [pin(baseline)]}}
                       for seed in (3, 17, 29) for kind in ("river", "confluence", "mouth", "lake_shore")]
            summary = root / "summary.json"
            summary.write_text(json.dumps({"fixed_denominator": 12, "records": records}), encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({"records": [{"seed": 29, "kind": "river", "projection_path": str(candidate),
                "projection_sha256": pin(candidate)["sha256"], "baseline_projection_path": str(baseline),
                "baseline_projection_sha256": pin(baseline)["sha256"]}]}), encoding="utf-8")
            def draw(path, *args):
                path.write_bytes(b"fixture-figure")
            with patch("tools.compare_hydrology_projection_naturalness.render", side_effect=draw):
                result = compare(summary, [report], root / "output")
            self.assertEqual(len(result["records"]), 12)
            self.assertEqual(sum(record["status"] == "not_run" for record in result["records"]), 11)
            actual = next(record for record in result["records"] if record["status"] == "compared_same_source")
            self.assertAlmostEqual(actual["after"]["height_absolute_change_quantiles_m"]["p50"], .1)
            self.assertFalse(actual["bed_certification_inherited"])
            self.assertFalse(actual["lake_certification_inherited"])
            self.assertFalse(result["naturalness_certified"])
            # A changed target must stop before creating any output directory.
            changed["target_height_m"][50, 50] += 1
            np.savez_compressed(candidate, **changed, metadata_json=np.array(json.dumps(metadata)))
            candidate_report = json.loads(report.read_text())
            candidate_report["records"][0]["projection_sha256"] = pin(candidate)["sha256"]
            report.write_text(json.dumps(candidate_report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "target_height_m"):
                compare(summary, [report], root / "refused")
            self.assertFalse((root / "refused").exists())
            changed_metadata = {**metadata, "target_policy": HARMONIC_TARGET_POLICY}
            np.savez_compressed(candidate, **changed, metadata_json=np.array(json.dumps(changed_metadata)))
            candidate_report["records"][0].update(target_policy=HARMONIC_TARGET_POLICY,
                                                  projection_sha256=pin(candidate)["sha256"])
            report.write_text(json.dumps(candidate_report), encoding="utf-8")
            with patch("tools.compare_hydrology_projection_naturalness.render", side_effect=draw):
                explicit = compare(summary, [report], root / "explicit-target")
            actual = next(record for record in explicit["records"] if record["status"] == "compared_same_source")
            self.assertTrue(actual["target_changed"])
            self.assertFalse(actual["inputs_equal"])
            self.assertEqual(len(actual["equal_input_arrays"]), 7)
            self.assertNotIn("target_height_m", actual["equal_input_arrays"])

    def test_explicit_target_policy_still_rejects_other_frozen_input_changes(self):
        arrays, metadata = self.fixture()
        changed = copy.deepcopy(arrays)
        changed["target_height_m"][10, 10] += 10.
        with self.assertRaisesRegex(ValueError, "target_height_m"):
            check_same_inputs(arrays, changed, metadata, metadata, target_policy="legacy-residual-v1")
        check_same_inputs(arrays, changed, metadata, metadata, target_policy=HARMONIC_TARGET_POLICY)
        changed["macro_height_m"][10, 10] += 1.
        with self.assertRaisesRegex(ValueError, "macro_height_m"):
            check_same_inputs(arrays, changed, metadata, metadata, target_policy=HARMONIC_TARGET_POLICY)
        with self.assertRaisesRegex(ValueError, "target_policy"):
            check_same_inputs(arrays, arrays, metadata, metadata, target_policy="arbitrary-target")


if __name__ == "__main__":
    unittest.main()
