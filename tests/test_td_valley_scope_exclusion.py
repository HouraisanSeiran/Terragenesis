import json
import tempfile
import unittest
from pathlib import Path

from tools.record_td_valley_scope_exclusion import record_scope_exclusion


class ScopeExclusionTests(unittest.TestCase):
    def test_records_only_unresolved_owner_divide_edges(self):
        diagnostic = {
            "source_sha256": "source",
            "plan_identity_sha256": "plan",
            "rows": [
                {
                    "source_cell_id": 1,
                    "target_cell_id": 2,
                    "recommendation": "must_remain_unresolved",
                    "centerline_owner_crossing": True,
                    "factors": {"0.1": {"divide": 1}},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diagnostic_path = root / "diagnostic.json"
            output_path = root / "scope.json"
            diagnostic_path.write_text(json.dumps(diagnostic), encoding="utf-8")
            failure = {
                "source": {"sha256": "source"},
                "parent_network_plan": {"identity_sha256": "plan"},
                "preflight": [{"source_cell_id": 1, "status": "refused_edge_preflight"}],
                "declared_selected_edges": 2,
                "accepted_global_edges": 1,
            }
            failure_path = root / "failure-prefix.json"
            failure_path.write_text(json.dumps(failure), encoding="utf-8")
            result = record_scope_exclusion(diagnostic_path, output_path)
            diagnostic["rows"][0]["source_cell_id"] = 3
            diagnostic_path.write_text(json.dumps(diagnostic), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refused edge set"):
                record_scope_exclusion(diagnostic_path, root / "bad-edge.json")
            diagnostic["rows"][0]["source_cell_id"] = 1
            diagnostic["source_sha256"] = "another-source"
            diagnostic_path.write_text(json.dumps(diagnostic), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source or plan"):
                record_scope_exclusion(diagnostic_path, root / "bad-source.json")
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(result["width_reduction_candidate_count"], 0)
        self.assertFalse(result["publishable"])


if __name__ == "__main__":
    unittest.main()
