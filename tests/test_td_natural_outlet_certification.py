import copy
import tempfile
import unittest
from pathlib import Path

from terrain_pipeline.td_natural_outlet_certification import (
    build_natural_outlet_certification,
    load_natural_outlet_certification,
    save_natural_outlet_certification,
    validate_natural_outlet_certification,
)


ROOT = Path("D:/geography")


class NaturalOutletCertificationTests(unittest.TestCase):
    def test_existing_evidence_is_pending_with_fixed_gates(self):
        report = build_natural_outlet_certification(ROOT)
        self.assertEqual(report["status"], "pending")
        self.assertFalse(report["natural_outlet_verified"])
        self.assertEqual(report["stages"]["named_relationship"], "supported")
        self.assertIn("dem_trace_is_candidate_only", report["observations"])
        validate_natural_outlet_certification(report)

    def test_verified_requires_all_three_independent_evidence_sets(self):
        evidence = {
            "independent_outlet": {"lat": 29.4, "lon": 121.4, "source": "survey-2026", "uncertainty_m": 1.2},
            "continuous_connection": {"verified": True, "from_river_to_coast": True, "source": "survey-2026"},
            "vertical_reference": {"datum": "CGVD2013", "uncertainty_m": 0.4, "source": "survey-2026"},
        }
        report = build_natural_outlet_certification(ROOT, candidate=evidence)
        self.assertEqual(report["status"], "verified")
        self.assertTrue(report["natural_outlet_verified"])

    def test_tampered_status_and_identity_are_rejected(self):
        report = build_natural_outlet_certification(ROOT)
        tampered = copy.deepcopy(report)
        tampered["natural_outlet_verified"] = True
        with self.assertRaises(ValueError):
            validate_natural_outlet_certification(tampered)

    def test_save_load_cold_round_trip(self):
        report = build_natural_outlet_certification(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "certification.json"
            save_natural_outlet_certification(report, path)
            self.assertEqual(load_natural_outlet_certification(path), report)
