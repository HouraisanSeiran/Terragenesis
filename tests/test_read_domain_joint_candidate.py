"""CPU-only unit coverage for the read-only joint consumer."""
from copy import deepcopy
import json

import numpy as np
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import read_domain_joint_candidate as joint
from tools.audit_domain_candidate_bundle import Audit


def fixture_records():
    params = {key: 1. for key in joint.RUNOFF_FIELDS}
    coverage = {"missing_upstream_contributing_cell_count": 0,
                "missing_upstream_contributing_release_m3": 0., "missing_producing_cell_count": 1,
                "cross_tile_inflow_status": "not_certified", "upstream_contributions_status": "not_certified"}
    budget = {"initial_storage": 0., "final_storage": 1., "local_input": 2., "boundary_outflow": 1., "residual": 0.}
    arrays = {"node_cell_ids": np.array([0, 1]), "selected_receiver": np.array([1, -1]),
              "topology_terminal": np.array([[1, 1, 2]]), "producing_cell_ids": np.array([0, 2]),
              "source_height_m": np.array([[3., 2., 1.]]),
              "channel_forcing_time_seconds": np.array([0., 1.]),
              "channel_forcing_local_q_m3_s": np.array([[2., 0.]]),
              "channel_trace_time_seconds": np.array([0., 1.]),
              "channel_trace_volume_m3": np.array([[0., 0.], [1., 0.]]),
              "channel_trace_local_q_m3_s": np.array([[2., 0.]]),
              "channel_trace_inflow_q_m3_s": np.array([[0., 1.]]),
              "channel_trace_outflow_q_m3_s": np.array([[1., 1.]]),
              "channel_trace_boundary_outflow_volume_m3": np.array([[0., 1.]]),
              "channel_trace_balance_residual_m3": np.array([[0., 0.]]),
              "channel_network_receiver": np.array([1, -1]),
              "channel_network_terminal_kind": np.array(["interior", "open_outflow"])}
    meta = {"topology_frame": {"shape": [1, 3], "origin_x_m": 0., "origin_z_m": 0., "spacing_m": 1.},
            "coverage": coverage, "dt_s": 1., "interval_count": 1, "source_face": "raw_conditioning",
            "r6_carving_consumed": False, "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False, "channel_metadata": {"status": "complete", "water_budget_m3": budget}}
    summary = {"selected_terminal_cell_id": 1, "node_cell_ids": [0, 1], "current_core_producing_contributors": [0],
               "coverage": deepcopy(coverage), "runoff_parameters": deepcopy(params), "seed": 1, "rain_mm_h": 4.,
               "dt_s": 1., "interval_count": 1, "status": "complete", "water_budget_m3": deepcopy(budget),
               "r6_carving_consumed": False, "source_face": "raw_conditioning", "hydraulic_ready": False,
               "natural_outlet_verified": False, "publishable": False}
    bundle = {"seed": 1, "rain_mm_h": 4., "dt_s": 1., "intervals": 1, "runoff_parameters": deepcopy(params)}
    ledger_arrays = {"outlet_x_m": np.array([1.]), "outlet_z_m": np.array([0.]), "cell_offsets": np.array([0, 1]),
                     "cell_count": np.array([1]), "cells_x_m": np.array([0.]), "cells_z_m": np.array([0.]),
                     "terminal_release_m3": np.array([2.])}
    ledger_meta = {"parameters": params, "seed": 1, "dt_s": 1., "interval_count": 1,
                   "tile_shape": [1, 3], "tile_origin_m_xz": [0., 0.], "spacing_m": 1.}
    flow = {"arrays": ledger_arrays, "metadata": ledger_meta}
    coupled = deepcopy(flow)
    coupled["metadata"]["parameters"] = {"runoff": deepcopy(params)}
    coupled["arrays"]["water_release_m3"] = coupled["arrays"].pop("terminal_release_m3")
    domain = {"cells_x_m": np.array([0.]), "cells_z_m": np.array([0.]), "base_height_m": np.array([[3.]]),
              "bbox_origin_xz_m": np.array([0., 0.]), "spacing_m": np.array(1.), "outlet_xz_m": np.array([1., 0.])}
    return bundle, summary, {"arrays": arrays, "metadata": meta}, flow, coupled, domain, {"outlet_x_m": 1., "outlet_z_m": 0.}


def test_positive_joint_keeps_storage_distinct_from_release():
    audit = Audit()
    result = joint.compare_joint(audit, *fixture_records())
    assert all(c["passed"] for c in audit.checks)
    assert result["forcing_integral_m3"] == 2.
    assert result["water_budget_m3"]["boundary_outflow"] == 1.
    assert result["water_budget_m3"]["final_storage"] == 1.


MISMATCHES = [
    ("runoff", "joint/runoff_nine_fields"),
    ("count", "joint/scenario"),
    ("member", "joint/flow/all_contributor_coordinates_and_count"),
    ("height", "joint/raw_source_member_heights"),
    ("flow_release", "joint/forcing_integral_equals_flow_domain_release"),
    ("coupled_release", "joint/forcing_integral_equals_coupled_domain_release"),
    ("trace", "r7/trace_cell_step_conservation"),
    ("carving", "r7/not_carved_or_certified"),
    ("missing", "r7/no_missing_same_terminal_contributors"),
]


def check_mismatch(mutation, failed):
    records = fixture_records()
    bundle, summary, r7, flow, coupled, domain, entry = records
    if mutation == "runoff": summary["runoff_parameters"]["slow_tau_s"] += 1
    if mutation == "count": summary["interval_count"] += 1
    if mutation == "member": flow["arrays"]["cells_x_m"][0] += 1
    if mutation == "height": domain["base_height_m"][0, 0] += 1
    if mutation == "flow_release": flow["arrays"]["terminal_release_m3"][0] += 1
    if mutation == "coupled_release": coupled["arrays"]["water_release_m3"][0] += 1
    if mutation == "trace": r7["arrays"]["channel_trace_volume_m3"][-1, 0] += 1
    if mutation == "carving": r7["metadata"]["r6_carving_consumed"] = True
    if mutation == "missing": r7["metadata"]["coverage"]["missing_upstream_contributing_cell_count"] = 1
    audit = Audit()
    joint.compare_joint(audit, *records)
    assert any(c["check"] == failed and not c["passed"] for c in audit.checks)


def check_cold_loader_rejection(tmp_path):
    bundle_path = tmp_path / "bundle" / "bundle.json"
    summary_path = tmp_path / "r7" / "report.json"
    bundle_path.parent.mkdir()
    summary_path.parent.mkdir()
    bundle_path.write_text('{"passed":true}', encoding="utf-8")
    summary_path.write_text(json.dumps({"path": "raw.npz", "sha256": "a" * 64, "identity_sha256": "b" * 64}), encoding="utf-8")
    (summary_path.parent / "raw.npz").write_bytes(b"unchanged")
    calls = []
    def reject(path, *, expected_sha256, expected_identity):
        calls.append((path.name, expected_sha256, expected_identity))
        raise ValueError("coverage or geometry summary mismatch")
    with patch.object(joint, "load_domain_channel_hydraulics", reject):
        report = joint.audit_joint(bundle_path, summary_path)
    assert calls == [("raw.npz", "a" * 64, "b" * 64)]
    assert report["status"] == "FAIL"
    assert report["joint_checks_status"] == "blocked_by_cold_read_failure"
    assert report["input_sha256_before"] == report["input_sha256_after"]
    assert len(report["sources"]) == 3
    assert report["all_phases_complete"] is False
    assert json.loads(bundle_path.read_text())["passed"] is True


class JointCandidateTests(unittest.TestCase):
    def test_positive_joint(self):
        test_positive_joint_keeps_storage_distinct_from_release()

    def test_mismatches(self):
        for mutation, failed in MISMATCHES:
            with self.subTest(mutation=mutation):
                check_mismatch(mutation, failed)

    def test_cold_loader_rejection(self):
        with TemporaryDirectory() as directory:
            check_cold_loader_rejection(Path(directory))

    def test_output_cannot_overwrite_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "bundle.json"
            source.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                joint.main(["--bundle", str(source), "--report", str(source)])
            self.assertEqual(source.read_text(), "{}")

    def test_points_reject_duplicates(self):
        self.assertFalse(joint.same_points([[0., 0.], [0., 0.]], [[0., 0.], [1., 0.]]))


if __name__ == "__main__":
    unittest.main()
