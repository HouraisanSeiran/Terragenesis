import unittest

from terrain_pipeline.surface_rivers.metric_distribution_calibration import calibrate_distribution
from terrain_pipeline.surface_rivers.metric_cohort_calibration import calibrate_cohorts, evaluate_cohort


class CohortCalibrationTests(unittest.TestCase):
    def reference(self, count=8):
        train = [{"id": "train", "metrics": {"slope": list(range(10))}}]
        calibration = [{"id": "c" + str(index), "metrics": {"slope": list(range(index % 4, 10 + index % 4))},
            "role": "calibration", "condition": "low_relief", "status": "measured",
            "world_extent_xz_m": [index * 5760., index * 5760., index * 5760. + 4320., index * 5760. + 4320.]}
            for index in range(count)]
        holdout = [{**block, "id": "h" + str(index), "role": "real_holdout"} for index, block in enumerate(calibration)]
        frozen = {"low_relief": calibrate_distribution(train, calibration, alpha=.2)}
        return calibrate_cohorts(calibration + holdout, frozen)

    def test_cohort_allows_individual_rejection_without_all_sample_rule(self):
        frozen = self.reference()
        cases = [{"relief_class": "low_relief", "distribution_evaluation_relief_grid_only": {"joint_score": score, "status": status}}
                 for score, status in ((.4, "fail"), (0., "pass"))]
        result = evaluate_cohort(cases, frozen)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["individual_rejections_retained"], ["fail", "pass"])
        reference = frozen["pair_types"]["low_relief:low_relief"]
        self.assertEqual(reference["calibration_count"], 4)
        self.assertEqual(reference["real_validation_count"], 4)
        self.assertEqual(reference["negative_control_status"], "fail")
        ids = [identifier for pair in reference["calibration_pairs"] for identifier in pair["ids"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_insufficient_pairs_do_not_pass_and_tamper_rejected(self):
        frozen = self.reference(6)
        cases = [{"relief_class": "low_relief", "distribution_evaluation_relief_grid_only": {"joint_score": 0., "status": "pass"}}] * 2
        self.assertEqual(evaluate_cohort(cases, frozen)["status"], "not_assessed")
        frozen["minimum_pairs"] = 1
        with self.assertRaises(ValueError):
            evaluate_cohort(cases, frozen)


if __name__ == "__main__":
    unittest.main()
