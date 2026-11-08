import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.continue_td_v10_refinement_after_baseline import choose, frozen, Followup


class FollowupTests(unittest.TestCase):
    def test_live_and_ineligible_runs_never_start_refinement(self):
        self.assertEqual(choose(dict(state="running"), False), "wait")
        self.assertEqual(choose(dict(state="diagnostic_stop"), True), "wait")
        for state in ("complete", "failed", "time_limit"):
            self.assertEqual(choose(dict(state=state), False), "stop")
        self.assertEqual(choose(dict(state="diagnostic_stop", reason="candidate failed"), False), "stop")

    def test_only_complete_baseline_diagnostic_is_eligible(self):
        status = dict(state="diagnostic_stop", baseline_numerical_gate_passed=False,
                      reason="baseline failed temporal numerical gates", baseline_acceptance_record=dict(path="p", expected_sha256="a"))
        self.assertEqual(choose(status, False), "refine")
        status["baseline_numerical_gate_passed"] = True
        self.assertEqual(choose(status, False), "stop")

    def test_frozen_followup_code_mismatch_rejected(self):
        with patch("tools.continue_td_v10_refinement_after_baseline.check_pins"), \
                patch("tools.continue_td_v10_refinement_after_baseline.file_sha256", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "frozen code"):
                frozen(dict(baseline_configuration={}, followup_code_sha256={"tools/continue_td_v10_refinement_after_baseline.py":"a"}))

    def test_deadline_stops_without_solver_or_output_claim(self):
        with tempfile.TemporaryDirectory() as directory, patch("tools.continue_td_v10_refinement_after_baseline.frozen"):
            status = Path(directory) / "baseline-status.json"
            status.write_text(json.dumps(dict(state="running", pid=0)), encoding="utf-8")
            followup = Followup(dict(deadline_utc="2026-01-01T00:00:00+00:00", baseline_status_path=str(status)), Path(directory) / "new")
            with patch.object(followup, "call", side_effect=AssertionError("executed")):
                result = followup.execute()
            self.assertEqual(result["state"], "time_limit")
            self.assertFalse(result["solver_advanced"])


if __name__ == "__main__":
    unittest.main()
