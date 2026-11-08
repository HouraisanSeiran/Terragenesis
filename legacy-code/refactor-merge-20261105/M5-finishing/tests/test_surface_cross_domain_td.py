import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terrain_pipeline.surface_domain import audit_cross_domain, audit_td_partition, save_cross_domain_report
from tests.test_surface_cross_domain import domain


ROOT = Path(__file__).resolve().parents[1]


def frozen_pins():
    base = ROOT / "verification/td-basin-generation"
    hierarchy = {"path": str(base / "A-20261001T184113155960Z/hierarchy.npz"),
                 "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                 "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"}
    storage = {"path": str(base / "A-storage-v2-20261001T193000Z/ordinary.npz"),
               "expected_sha256": "8ec55ed5cf750f93f821e97a0abf5fd74b2fe870f20ce1785a70f84097382dd2",
               "expected_identity": "3c19fe7ab54b0373051fb25d59733130d3117a105b3d905a68f389687983a49b"}
    return hierarchy, storage


class TDPartitionTests(unittest.TestCase):
    def test_actual_frozen_flux_without_generation(self):
        hierarchy, storage = frozen_pins()
        with patch('terrain_pipeline.basin_topology.build_basin_hierarchy', side_effect=AssertionError("generation")), patch('terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError("solve")):
            report = audit_td_partition(hierarchy, partition_column=128, storage_record=storage)
        self.assertEqual(report["ledger"]["shared_edge_count"], 256)
        self.assertEqual(report["ledger"]["internal_shared_flux_residual_m3_s"], 0)
        self.assertEqual(report["ledger"]["unique_boundary_flux_m3_s"], 0)
        self.assertGreater(report["td_evidence"]["forward_m3"] + report["td_evidence"]["reverse_m3"], 0)
        self.assertGreater(report["td_evidence"]["nonzero_one_direction_face_count"], 0)
        self.assertEqual(report["td_evidence"]["elapsed_s"], 86400)
        self.assertTrue(report["flags"]["partition_flux_evidence_complete"])
        self.assertFalse(report["flags"]["edge_evidence_complete"])
        self.assertFalse(report["flags"]["hydraulic_ready"])

    def test_hierarchy_only_is_diagnostic(self):
        hierarchy, _ = frozen_pins()
        report = audit_td_partition(hierarchy, partition_column=128)
        self.assertFalse(report["flags"]["partition_flux_evidence_complete"])
        self.assertIsNone(report["td_evidence"]["forward_m3"])

    def test_bad_external_pin_no_publication(self):
        hierarchy, storage = frozen_pins()
        storage["expected_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report.json"
            with self.assertRaises(ValueError):
                report = audit_td_partition(hierarchy, partition_column=128, storage_record=storage)
                save_cross_domain_report(report, output)
            self.assertFalse(output.exists())

    def test_ids_survive_extra_domain(self):
        first = domain()
        before = audit_cross_domain([first])
        third = domain()
        third["domain_id"] = "third"
        third["grid"]["origin_x_m"] = -10.
        for node in third["nodes"]:
            node["x_m"] -= 10.
        after = audit_cross_domain([third, first])
        ids = {(node["x_m"], node["z_m"]): node["global_id"] for node in after["global_nodes"]}
        self.assertTrue(all(ids[node["x_m"], node["z_m"]] == node["global_id"] for node in before["global_nodes"]))

    def test_same_domain_duplicate_and_nonfinite_tolerance(self):
        first = domain()
        extra = copy.deepcopy(first["edges"][0])
        extra.update(local_id=99, flux_m3_s=-extra["flux_m3_s"])
        first["edges"].append(extra)
        with self.assertRaisesRegex(ValueError, "one domain"):
            audit_cross_domain([first])
        for tolerance in (float("nan"), float("inf"), -1.):
            with self.assertRaises(ValueError):
                audit_cross_domain([domain()], tolerance=tolerance)

    def test_normal_sign_is_independent_of_endpoint_order(self):
        first, second = domain(), domain(reverse=True)
        report = audit_cross_domain([first, second])
        self.assertEqual(report["ledger"]["shared_edge_count"], 2)
        self.assertFalse(report["flags"]["edge_evidence_complete"])

    def test_nan_report_fails_before_directory_creation(self):
        report = audit_cross_domain([domain()])
        report["bad"] = float("nan")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "absent/report.json"
            with self.assertRaises(ValueError):
                save_cross_domain_report(report, output)
            self.assertFalse(output.parent.exists())
