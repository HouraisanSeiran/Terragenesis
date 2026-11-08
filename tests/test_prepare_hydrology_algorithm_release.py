import json
from pathlib import Path
import tempfile
import unittest

from tools.prepare_hydrology_algorithm_release import collect_local_sources, copy_payload, release_gates, sha256


class FixedHydrologyPayloadTests(unittest.TestCase):
    def test_local_import_closure_and_report_are_fixed_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "package").mkdir()
            (root / "package/__init__.py").write_text("", encoding="utf-8")
            (root / "package/entry.py").write_text("from .helper import value\n", encoding="utf-8")
            (root / "package/helper.py").write_text("value = 3\n", encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({"accepted": True}), encoding="utf-8")
            figure = root / "review.png"
            figure.write_bytes(b"fixed visual evidence")
            sources, external = collect_local_sources(root, ["package/entry.py"])
            self.assertEqual(len(sources), 3)
            self.assertNotIn("package", external)
            output = root / "snapshot"
            artifacts = copy_payload(root, output, sources | {report, figure}, sources)
            frozen = output / "payload/package/helper.py"
            pin = sha256(frozen)
            (root / "package/helper.py").write_text("value = 4\n", encoding="utf-8")
            self.assertEqual(sha256(frozen), pin)
            self.assertEqual((output / "payload/review.png").read_bytes(), figure.read_bytes())
            self.assertEqual(len(artifacts), 5)
            self.assertTrue(all(item["storage"] == "fixed_payload_copy" for item in artifacts))

    def test_coarse_and_fine_scope_can_pass_without_claiming_missing_mouth_or_fraction_junction(self):
        continuity = {"schema": "hydrology-owned-basin-continuity-cold-v1", "coarse_dag_accepted": True,
                      "owned_cell_count": 10, "traced_owned_cell_count": 10, "fine_to_coarse_interfaces_accepted": True,
                      "coarse_bed_graph": {"accepted": True, "cold_saved_profile_audit": {"accepted": True}},
                      "fine_evidence": [{"source_edge": [1, 2], "local_geometry_accepted": True,
                                         "seam_audit": {"accepted": True, "continuous_affine_trace_verified": True},
                                         "cold_geometry_audits": [{"accepted": True, "continuous_longitudinal_gradient_verified": True, "frozen_profile_ceiling_verified": True}]}]}
        gates = release_gates(None, [], {"local_window_compatible": True}, {"naturalness_certified": False}, continuity=continuity, mouth_edges={(4, 5)})
        self.assertTrue(gates["complete_selected_network_continuity"])
        self.assertFalse(gates["key_fine_mouth_geometry"])
        self.assertFalse(gates["real_td_confluence"])
        self.assertFalse(gates["multiseed_real_td_naturalness"])
        continuity["fine_evidence"][0]["cold_geometry_audits"][0]["frozen_profile_ceiling_verified"] = False
        self.assertFalse(release_gates(None, [], None, None, continuity=continuity)["declared_fine_geometry"])


if __name__ == "__main__":
    unittest.main()
