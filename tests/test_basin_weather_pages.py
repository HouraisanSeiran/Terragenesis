"""M4 tests.test_basin_weather_pages; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from dataclasses import asdict as _m4_test_audit_td_v10_temporal_refinement_asdict
from dataclasses import asdict as _m4_test_td_native_weather_storage_v10_io_asdict
from datetime import datetime as _m4_test_run_td_v10_temporal_refinement_datetime
from datetime import timedelta as _m4_test_run_td_v10_temporal_refinement_timedelta
from datetime import timezone as _m4_test_run_td_v10_temporal_refinement_timezone
from pathlib import Path as _m4_test_audit_td_v10_temporal_refinement_Path
from pathlib import Path as _m4_test_continue_td_v10_refinement_after_baseline_Path
from pathlib import Path as _m4_test_run_td_v10_temporal_refinement_Path
from pathlib import Path as _m4_test_td_native_weather_storage_v10_io_Path
from pathlib import Path as _m4_test_td_v10_refinement_full_binding_Path
from pathlib import Path as _m4_test_td_weather_v10_final_binding_Path
from terrain_pipeline.basin_storage import ERRORS as _m4_test_audit_td_v10_temporal_refinement_ERRORS
from terrain_pipeline.basin_storage import ERRORS as _m4_test_td_native_weather_storage_v10_io_ERRORS
from terrain_pipeline.basin_storage import FLUX as _m4_test_audit_td_v10_temporal_refinement_FLUX
from terrain_pipeline.basin_storage import FLUX as _m4_test_td_native_weather_storage_v10_io_FLUX
from terrain_pipeline.basin_storage import LEDGERS as _m4_test_audit_td_v10_temporal_refinement_LEDGERS
from terrain_pipeline.basin_storage import LEDGERS as _m4_test_td_native_weather_storage_v10_io_LEDGERS
from terrain_pipeline.basin_storage import STATES as _m4_test_audit_td_v10_temporal_refinement_STATES
from terrain_pipeline.basin_storage import STATES as _m4_test_td_native_weather_storage_v10_io_STATES
from terrain_pipeline.basin_storage import STORAGEV10_PROFILE as _m4_test_audit_td_v10_temporal_refinement_PROFILE
from terrain_pipeline.basin_storage import STORAGEV10_PROFILE as _m4_test_td_native_weather_storage_v10_io_PROFILE
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_native_weather_storage_v10_io_make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_native_weather_storage_v10_io_build_basin_hierarchy
from terrain_pipeline.common_infra import file_sha256 as _m4_test_audit_td_v10_temporal_refinement_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_run_td_v10_temporal_refinement_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_native_weather_storage_v10_io_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_native_weather_v10_review_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_v10_refinement_full_binding_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_weather_v10_final_binding_file_sha256
from terrain_pipeline.common_infra import identity as _m4_test_audit_td_v10_temporal_refinement_identity
from terrain_pipeline.common_infra import identity as _m4_test_td_native_weather_storage_v10_io_identity
from terrain_pipeline.common_infra import publish_bytes as _m4_test_td_v10_refinement_full_binding_publish_bytes
from terrain_pipeline.common_infra import save_bundle as _m4_test_audit_td_v10_temporal_refinement_save_bundle
from terrain_pipeline.common_infra import save_bundle as _m4_test_td_native_weather_storage_v10_io_save_bundle
from terrain_pipeline.runoff import RunoffParameters as _m4_test_audit_td_v10_temporal_refinement_RunoffParameters
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_native_weather_storage_v10_io_RunoffParameters
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS as _m4_test_audit_td_v10_temporal_refinement_PHYSICS
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS as _m4_test_td_native_weather_storage_v10_io_PHYSICS
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS_SEMANTICS as _m4_test_audit_td_v10_temporal_refinement_PHYSICS_SEMANTICS
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS_SEMANTICS as _m4_test_td_native_weather_storage_v10_io_PHYSICS_SEMANTICS
from terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_storage_v10_index as _m4_test_td_native_weather_storage_v10_io_load_native_weather_storage_v10_index
from terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_v10_hour as _m4_test_td_native_weather_storage_v10_io_load_native_weather_v10_hour
from terrain_pipeline.td_native_weather_v10_review import export_native_weather_v10_review as _m4_test_td_native_weather_v10_review_export_native_weather_v10_review
from terrain_pipeline.td_native_weather_v10_review import load_native_weather_v10_review as _m4_test_td_native_weather_v10_review_load_native_weather_v10_review
from terrain_pipeline.td_surface_reaches import _hash as _m4_test_td_native_weather_v10_review_hash
from tools import audit_td_v10_temporal_refinement as _m4_test_td_v10_refinement_full_binding_auditor
from tools.audit_td_candidate_coupling import read_record as _m4_test_audit_td_v10_temporal_refinement_read_record
from tools.audit_td_candidate_coupling import read_record as _m4_test_td_v10_refinement_full_binding_read_record
from tools.audit_td_native_weather_v10 import audit_accounts as _m4_test_audit_td_native_weather_v10_audit_accounts
from tools.audit_td_native_weather_v10_final import bind_numerical as _m4_test_td_weather_v10_final_binding_bind_numerical
from tools.audit_td_v10_temporal_refinement import audit_sequence as _m4_test_audit_td_v10_temporal_refinement_audit_sequence
from tools.audit_td_v10_temporal_refinement import check_resource as _m4_test_audit_td_v10_temporal_refinement_check_resource
from tools.audit_td_v10_temporal_refinement import compare as _m4_test_audit_td_v10_temporal_refinement_compare
from tools.continue_td_v10_refinement_after_baseline import Followup as _m4_test_continue_td_v10_refinement_after_baseline_Followup
from tools.continue_td_v10_refinement_after_baseline import choose as _m4_test_continue_td_v10_refinement_after_baseline_choose
from tools.continue_td_v10_refinement_after_baseline import frozen as _m4_test_continue_td_v10_refinement_after_baseline_frozen
from tools.diagnose_td_v10_saved_refinement import attribute as _m4_test_diagnose_td_v10_saved_refinement_attribute
from tools.run_td_v10_temporal_refinement import REFERENCE_STEP_S as _m4_test_run_td_v10_temporal_refinement_REFERENCE_STEP_S
from tools.run_td_v10_temporal_refinement import STEP_S as _m4_test_run_td_v10_temporal_refinement_STEP_S
from tools.run_td_v10_temporal_refinement import prepare as _m4_test_run_td_v10_temporal_refinement_prepare
from unittest.mock import patch as _m4_test_continue_td_v10_refinement_after_baseline_patch
from unittest.mock import patch as _m4_test_run_td_v10_temporal_refinement_patch
from unittest.mock import patch as _m4_test_td_native_weather_v10_review_patch
from unittest.mock import patch as _m4_test_td_v10_refinement_full_binding_patch
import copy as _m4_test_audit_td_native_weather_v10_copy
import copy as _m4_test_audit_td_v10_temporal_refinement_copy
import copy as _m4_test_td_native_weather_storage_v10_io_copy
import copy as _m4_test_td_native_weather_v10_review_copy
import copy as _m4_test_td_weather_v10_final_binding_copy
import json as _m4_test_continue_td_v10_refinement_after_baseline_json
import json as _m4_test_run_td_v10_temporal_refinement_json
import json as _m4_test_td_native_weather_storage_v10_io_json
import json as _m4_test_td_native_weather_v10_review_json
import json as _m4_test_td_v10_refinement_full_binding_json
import json as _m4_test_td_weather_v10_final_binding_json
import numpy as _m4_test_audit_td_native_weather_v10_np
import numpy as _m4_test_audit_td_v10_temporal_refinement_np
import numpy as _m4_test_diagnose_td_v10_saved_refinement_np
import numpy as _m4_test_td_native_weather_storage_v10_io_np
import numpy as _m4_test_td_v10_refinement_full_binding_np
import subprocess as _m4_test_audit_td_v10_temporal_refinement_subprocess
import subprocess as _m4_test_td_native_weather_storage_v10_io_subprocess
import sys as _m4_test_audit_td_v10_temporal_refinement_sys
import sys as _m4_test_td_native_weather_storage_v10_io_sys
import tempfile as _m4_test_audit_td_v10_temporal_refinement_tempfile
import tempfile as _m4_test_continue_td_v10_refinement_after_baseline_tempfile
import tempfile as _m4_test_run_td_v10_temporal_refinement_tempfile
import tempfile as _m4_test_td_native_weather_storage_v10_io_tempfile
import tempfile as _m4_test_td_v10_refinement_full_binding_tempfile
import tempfile as _m4_test_td_weather_v10_final_binding_tempfile
import unittest as _m4_test_audit_td_native_weather_v10_unittest
import unittest as _m4_test_audit_td_v10_temporal_refinement_unittest
import unittest as _m4_test_continue_td_v10_refinement_after_baseline_unittest
import unittest as _m4_test_diagnose_td_v10_saved_refinement_unittest
import unittest as _m4_test_run_td_v10_temporal_refinement_unittest
import unittest as _m4_test_td_native_weather_storage_v10_io_unittest
import unittest as _m4_test_td_native_weather_v10_review_unittest
import unittest as _m4_test_td_v10_refinement_full_binding_unittest
import unittest as _m4_test_td_weather_v10_final_binding_unittest

# --- tests/test_audit_td_v10_temporal_refinement.py:23 ---
class TestAuditTdProfile10TemporalRefinementIndependentRefinementTests(_m4_test_audit_td_v10_temporal_refinement_unittest.TestCase):
    def sequence(self, directory, step=.625):
        directory = _m4_test_audit_td_v10_temporal_refinement_Path(directory)
        topology = dict(height_m=_m4_test_audit_td_v10_temporal_refinement_np.array([[0., 1.]]), valid_mask=_m4_test_audit_td_v10_temporal_refinement_np.ones((1, 2), bool),
                        protected_mask=_m4_test_audit_td_v10_temporal_refinement_np.zeros((1, 2), bool), face_cells=_m4_test_audit_td_v10_temporal_refinement_np.array([[0, 1]], _m4_test_audit_td_v10_temporal_refinement_np.int64),
                        receiver=_m4_test_audit_td_v10_temporal_refinement_np.array([-1, 0], _m4_test_audit_td_v10_temporal_refinement_np.int64), boundary_cells=_m4_test_audit_td_v10_temporal_refinement_np.empty(0, _m4_test_audit_td_v10_temporal_refinement_np.int64))
        geometry = dict(spacing_m=30., origin_m_xz=[0., 0.])
        rain = _m4_test_audit_td_v10_temporal_refinement_np.ones((24, 1, 2), _m4_test_audit_td_v10_temporal_refinement_np.float64)
        pages = []
        for hour in range(24):
            arrays = {name:topology[name].copy() for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells")}
            arrays["boundary_width_m"] = _m4_test_audit_td_v10_temporal_refinement_np.empty(0, _m4_test_audit_td_v10_temporal_refinement_np.float64)
            arrays.update({name:_m4_test_audit_td_v10_temporal_refinement_np.zeros((2, 2), _m4_test_audit_td_v10_temporal_refinement_np.float64) for name in _m4_test_audit_td_v10_temporal_refinement_STATES})
            arrays["soil_mm"][:] = [[30. + hour] * 2, [31. + hour] * 2]
            arrays.update({name:_m4_test_audit_td_v10_temporal_refinement_np.zeros((1, 2), _m4_test_audit_td_v10_temporal_refinement_np.float64) for name in _m4_test_audit_td_v10_temporal_refinement_LEDGERS})
            arrays["rain_mm_h"] = _m4_test_audit_td_v10_temporal_refinement_np.ones((1, 2), _m4_test_audit_td_v10_temporal_refinement_np.float64)
            for name in ("rain_volume_m3", "rain_infiltration_m3", "storage_change_m3"):
                arrays[name][:] = .9
            arrays["infiltration_capacity_m3"][:] = 13.5
            arrays.update({name:_m4_test_audit_td_v10_temporal_refinement_np.zeros(1 if name.startswith(("face_", "active_")) else 2, _m4_test_audit_td_v10_temporal_refinement_np.float64) for name in _m4_test_audit_td_v10_temporal_refinement_FLUX})
            metadata = dict(schema="td-v10-hour-page-v1", profile=_m4_test_audit_td_v10_temporal_refinement_PROFILE, cells=2, faces=1,
                            substep_s=step, substeps=int(3600 / step), forcing_hour_offset=hour,
                            dt_s=3600., start_s=hour * 3600., end_s=(hour + 1) * 3600.,
                            spacing_m=30., origin_m_xz=[0., 0.], hierarchy_identity="a" * 64,
                            forcing_identity="b" * 64, parameters=dict(_m4_test_audit_td_v10_temporal_refinement_PHYSICS, substep_s=step),
                            runoff_parameters=_m4_test_audit_td_v10_temporal_refinement_asdict(_m4_test_audit_td_v10_temporal_refinement_RunoffParameters()), positivity_cfl=step * .6 / 30.,
                            physics=_m4_test_audit_td_v10_temporal_refinement_PHYSICS_SEMANTICS,
                            permanent_lake_impermeability="not modelled; requires independent material mask",
                            activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration",
                            hydraulic_ready=False, transient_converged=False, publishable=False)
            page = dict(arrays=arrays, metadata=metadata, identity_sha256=_m4_test_audit_td_v10_temporal_refinement_identity(arrays, metadata))
            cp_arrays = {name:arrays[name][-1].copy() for name in _m4_test_audit_td_v10_temporal_refinement_STATES}
            cp_arrays.update({name:_m4_test_audit_td_v10_temporal_refinement_np.zeros(2) for name in _m4_test_audit_td_v10_temporal_refinement_ERRORS})
            cp_arrays.update({"cumulative_" + name:arrays[name].copy() for name in _m4_test_audit_td_v10_temporal_refinement_FLUX})
            cp_meta = dict(metadata, schema="td-v10-hour-checkpoint-v1", last_page_identity=page["identity_sha256"])
            cp = dict(arrays=cp_arrays, metadata=cp_meta, identity_sha256=_m4_test_audit_td_v10_temporal_refinement_identity(cp_arrays, cp_meta))
            records = dict(hour=hour, forcing_identity="b" * 64, chunk_work_face_steps=int(3600 / step))
            for role, saved in (("storage", page), ("checkpoint", cp)):
                path = directory / f"hour-{hour:02d}" / (role + ".npz")
                _m4_test_audit_td_v10_temporal_refinement_save_bundle(path, saved, validator=lambda value:True)
                records[role] = dict(path=str(path.resolve()), expected_sha256=_m4_test_audit_td_v10_temporal_refinement_file_sha256(path), expected_identity=saved["identity_sha256"])
            pages.append(records)
        return pages, dict(topology=topology, geometry=geometry, rain=rain, forcing_identity="b" * 64,
                           step=step, run_root=directory, hierarchy_identity="a" * 64)

    def test_complete_fine_sequence_schema_cold_accounts_and_chain(self):
        with _m4_test_audit_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            pages, arguments = self.sequence(directory)
            result = _m4_test_audit_td_v10_temporal_refinement_audit_sequence(pages, **arguments)
            self.assertEqual(result["frames"].shape, (25, 2))
            self.assertTrue(result["budget"]["whole_period_passed"])
            self.assertAlmostEqual(result["budget"]["total_rain_m3"], 43.2)
            self.assertTrue(_m4_test_audit_td_v10_temporal_refinement_compare(result, result)["gate_passed"])

    def test_partial_and_false_cumulative_checkpoint_rejected(self):
        with _m4_test_audit_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            pages, arguments = self.sequence(directory)
            with self.assertRaisesRegex(ValueError, "complete 24-hour"):
                _m4_test_audit_td_v10_temporal_refinement_audit_sequence(pages[:-1], **arguments)
            arrays, metadata = _m4_test_audit_td_v10_temporal_refinement_read_record(pages[8]["checkpoint"])
            arrays["cumulative_routed_volume_m3"][0] = 1.
            saved = dict(arrays=arrays, metadata=metadata, identity_sha256=_m4_test_audit_td_v10_temporal_refinement_identity(arrays, metadata))
            path = _m4_test_audit_td_v10_temporal_refinement_Path(directory) / "tampered-checkpoint.npz"
            _m4_test_audit_td_v10_temporal_refinement_save_bundle(path, saved, validator=lambda value:True)
            pages[8]["checkpoint"] = dict(path=str(path), expected_sha256=_m4_test_audit_td_v10_temporal_refinement_file_sha256(path), expected_identity=saved["identity_sha256"])
            with self.assertRaises(AssertionError):
                _m4_test_audit_td_v10_temporal_refinement_audit_sequence(pages, **arguments)

    def test_physics_changed_and_wrong_initial_state_rejected(self):
        with _m4_test_audit_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            pages, arguments = self.sequence(directory)
            arrays, metadata = _m4_test_audit_td_v10_temporal_refinement_read_record(pages[0]["storage"])
            metadata["parameters"]["face_conductance_m_s"] = .7
            saved = dict(arrays=arrays, metadata=metadata, identity_sha256=_m4_test_audit_td_v10_temporal_refinement_identity(arrays, metadata))
            path = _m4_test_audit_td_v10_temporal_refinement_Path(directory) / "tampered-storage.npz"
            _m4_test_audit_td_v10_temporal_refinement_save_bundle(path, saved, validator=lambda value:True)
            pages[0]["storage"] = dict(path=str(path), expected_sha256=_m4_test_audit_td_v10_temporal_refinement_file_sha256(path), expected_identity=saved["identity_sha256"])
            with self.assertRaisesRegex(ValueError, "physics"):
                _m4_test_audit_td_v10_temporal_refinement_audit_sequence(pages, **arguments)

    def test_unchanged_strict_depth_and_receiver_gates(self):
        first = dict(frames=_m4_test_audit_td_v10_temporal_refinement_np.zeros((25, 2)), cumulative=dict(routed_volume_m3=_m4_test_audit_td_v10_temporal_refinement_np.ones(2)))
        second = _m4_test_audit_td_v10_temporal_refinement_copy.deepcopy(first)
        second["frames"][5, 1] = .0013
        self.assertFalse(_m4_test_audit_td_v10_temporal_refinement_compare(first, second)["gate_passed"])
        second["frames"][:] = 0.
        second["cumulative"]["routed_volume_m3"][0] = 1.1
        self.assertFalse(_m4_test_audit_td_v10_temporal_refinement_compare(first, second)["gate_passed"])

    def test_missing_private_resource_and_exceeded_budget_rejected(self):
        resource = dict(complete=True, index_sha256="a" * 64, scope="new48", monitor_error=None,
                        peak_rss_bytes=100, peak_private_bytes=200, sample_count=3)
        _m4_test_audit_td_v10_temporal_refinement_check_resource(resource, "a" * 64, "new48")
        for name, value in (("peak_private_bytes", 0), ("peak_rss_bytes", 1073741825), ("complete", False)):
            changed = dict(resource, **{name:value})
            with self.assertRaisesRegex(ValueError, "resource"):
                _m4_test_audit_td_v10_temporal_refinement_check_resource(changed, "a" * 64, "new48")

    def test_fresh_audit_import_without_solver(self):
        _m4_test_audit_td_v10_temporal_refinement_subprocess.run([_m4_test_audit_td_v10_temporal_refinement_sys.executable, "-c", 'import tools.audit_td_v10_temporal_refinement; import sys; assert "terrain_pipeline.basin_storage" in sys.modules; assert \'terrain_pipeline.td_basin_storage_v10\' not in sys.modules'], check=True)

# --- tests/test_continue_td_v10_refinement_after_baseline.py:10 ---
class TestContinueTdProfile10RefinementAfterBaselineFollowupTests(_m4_test_continue_td_v10_refinement_after_baseline_unittest.TestCase):
    def test_live_and_ineligible_runs_never_start_refinement(self):
        self.assertEqual(_m4_test_continue_td_v10_refinement_after_baseline_choose(dict(state="running"), False), "wait")
        self.assertEqual(_m4_test_continue_td_v10_refinement_after_baseline_choose(dict(state="diagnostic_stop"), True), "wait")
        for state in ("complete", "failed", "time_limit"):
            self.assertEqual(_m4_test_continue_td_v10_refinement_after_baseline_choose(dict(state=state), False), "stop")
        self.assertEqual(_m4_test_continue_td_v10_refinement_after_baseline_choose(dict(state="diagnostic_stop", reason="candidate failed"), False), "stop")

    def test_only_complete_baseline_diagnostic_is_eligible(self):
        status = dict(state="diagnostic_stop", baseline_numerical_gate_passed=False,
                      reason="baseline failed temporal numerical gates", baseline_acceptance_record=dict(path="p", expected_sha256="a"))
        self.assertEqual(_m4_test_continue_td_v10_refinement_after_baseline_choose(status, False), "refine")
        status["baseline_numerical_gate_passed"] = True
        self.assertEqual(_m4_test_continue_td_v10_refinement_after_baseline_choose(status, False), "stop")

    def test_frozen_followup_code_mismatch_rejected(self):
        with _m4_test_continue_td_v10_refinement_after_baseline_patch("tools.continue_td_v10_refinement_after_baseline.check_pins"), \
                _m4_test_continue_td_v10_refinement_after_baseline_patch("tools.continue_td_v10_refinement_after_baseline.file_sha256", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "frozen code"):
                _m4_test_continue_td_v10_refinement_after_baseline_frozen(dict(baseline_configuration={}, followup_code_sha256={"tools/continue_td_v10_refinement_after_baseline.py":"a"}))

    def test_deadline_stops_without_solver_or_output_claim(self):
        with _m4_test_continue_td_v10_refinement_after_baseline_tempfile.TemporaryDirectory() as directory, _m4_test_continue_td_v10_refinement_after_baseline_patch("tools.continue_td_v10_refinement_after_baseline.frozen"):
            status = _m4_test_continue_td_v10_refinement_after_baseline_Path(directory) / "baseline-status.json"
            status.write_text(_m4_test_continue_td_v10_refinement_after_baseline_json.dumps(dict(state="running", pid=0)), encoding="utf-8")
            followup = _m4_test_continue_td_v10_refinement_after_baseline_Followup(dict(deadline_utc="2026-01-01T00:00:00+00:00", baseline_status_path=str(status)), _m4_test_continue_td_v10_refinement_after_baseline_Path(directory) / "new")
            with _m4_test_continue_td_v10_refinement_after_baseline_patch.object(followup, "call", side_effect=AssertionError("executed")):
                result = followup.execute()
            self.assertEqual(result["state"], "time_limit")
            self.assertFalse(result["solver_advanced"])

# --- tests/test_diagnose_td_v10_saved_refinement.py:8 ---
class TestDiagnoseTdProfile10SavedRefinementAttributionTests(_m4_test_diagnose_td_v10_saved_refinement_unittest.TestCase):
    def fixture(self):
        source = dict(height_m=_m4_test_diagnose_td_v10_saved_refinement_np.zeros((1, 2)), valid_mask=_m4_test_diagnose_td_v10_saved_refinement_np.ones((1, 2), bool),
                      face_cells=_m4_test_diagnose_td_v10_saved_refinement_np.array([[0, 1]], _m4_test_diagnose_td_v10_saved_refinement_np.int64), receiver=_m4_test_diagnose_td_v10_saved_refinement_np.array([1, -1]),
                      rain_mm_h=_m4_test_diagnose_td_v10_saved_refinement_np.zeros((1, 2)), depth_m=_m4_test_diagnose_td_v10_saved_refinement_np.array([[1., 1.], [1., 1.]]),
                      face_forward_m3=_m4_test_diagnose_td_v10_saved_refinement_np.array([0.]), face_reverse_m3=_m4_test_diagnose_td_v10_saved_refinement_np.array([0.]),
                      soil_mm=_m4_test_diagnose_td_v10_saved_refinement_np.zeros((2, 2)))
        for name in ("local_release_m3", "surface_infiltration_m3", "surface_et_m3", "internal_net_m3",
                     "boundary_outflow_m3", "rain_infiltration_m3"):
            source[name] = _m4_test_diagnose_td_v10_saved_refinement_np.zeros((1, 2))
        return source

    def test_incident_exchange_localizes_difference(self):
        first, second = self.fixture(), self.fixture()
        first["depth_m"][-1] += [-.002, .002]
        first["internal_net_m3"][0] = [-1.8, 1.8]
        first["face_forward_m3"][0] = 1.8
        result = _m4_test_diagnose_td_v10_saved_refinement_attribute(first, second, spacing_m=30., hour=5, top_cells=2)
        self.assertFalse(result["numerical_depth_gate_passed"])
        self.assertAlmostEqual(result["max_saved_depth_difference_mm"], 2.)
        self.assertAlmostEqual(result["hotspot_rows"][0]["signed_account_contributions_mm"]["internal_net_m3"], 2.)
        self.assertAlmostEqual(result["hotspot_rows"][0]["incident_faces"][0]["signed_contribution_mm"], 2.)

    def test_inherited_error_without_new_flux(self):
        first, second = self.fixture(), self.fixture()
        first["depth_m"][:, 0] += .0012
        result = _m4_test_diagnose_td_v10_saved_refinement_attribute(first, second, spacing_m=30., hour=6, top_cells=1)
        self.assertAlmostEqual(result["hotspot_rows"][0]["inherited_signed_difference_mm"], 1.2)
        self.assertAlmostEqual(result["maximum_account_explanation_residual_mm"], 0.)

    def test_unexplained_difference_and_rain_change_rejected(self):
        first, second = self.fixture(), self.fixture()
        first["depth_m"][-1, 0] += .001
        with self.assertRaisesRegex(ValueError, "attribution"):
            _m4_test_diagnose_td_v10_saved_refinement_attribute(first, second, spacing_m=30., hour=1)
        first = self.fixture()
        first["rain_mm_h"][0, 0] = 1.
        with self.assertRaises(AssertionError):
            _m4_test_diagnose_td_v10_saved_refinement_attribute(first, second, spacing_m=30., hour=1)

# --- tests/test_run_td_v10_temporal_refinement.py:12 ---
class TestRunTdProfile10TemporalRefinementTemporalRefinementTests(_m4_test_run_td_v10_temporal_refinement_unittest.TestCase):
    def fixture(self, root):
        root = _m4_test_run_td_v10_temporal_refinement_Path(root)
        baseline = root / "baseline"
        baseline.mkdir()
        status = root / "status.json"
        status.write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(dict(schema="td-ten-hour-pipeline-status-v1", state="diagnostic_stop", pid=0,
                                          deadline_utc=(_m4_test_run_td_v10_temporal_refinement_datetime.now(_m4_test_run_td_v10_temporal_refinement_timezone.utc) + _m4_test_run_td_v10_temporal_refinement_timedelta(hours=6)).isoformat())))
        source = root / "source.npz"
        source.write_bytes(b"source")
        pin = dict(path=str(source), expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(source), expected_identity="a" * 64)
        weather_index = dict(path=str(source), sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(source))
        code = {f"frozen-{index}.py": "a" * 64 for index in range(15)}
        inputs = dict(schema="td-v10-spatial-weather-run-inputs-v1", steps_s=[2.5, 1.25],
                      hierarchy=pin, weather_index=weather_index,
                      weather_records=dict(eastward=pin, westward=pin),
                      forcing_identities=dict(eastward="b" * 64, westward="c" * 64),
                      primary_sha256="d" * 64, code_sha256=code,
                      budgets={"1.25": {"chunk_face_steps": 2880}}, chunk_max_face_steps=6000000000,
                      job_max_bytes=1073741824,
                      physics_version="unchanged-v10", depth_gate_m=.001, receiver_gate=.01)
        scenarios = {}
        for direction in ("eastward", "westward"):
            pages = {}
            for step in ("2.5", "1.25"):
                pages[step] = [dict(hour=hour, storage=pin, checkpoint=pin, elapsed_s=1.,
                                    forcing_identity=inputs["forcing_identities"][direction]) for hour in range(24)]
            scenarios[direction] = dict(pages=pages, weather_record=pin,
                                        forcing_identity=inputs["forcing_identities"][direction])
        index = dict(schema="td-v10-spatial-weather-hour-pages-index-v1", steps_s=[2.5, 1.25],
                     scenarios=scenarios, code_sha256=code)
        for name, value in (("run-inputs", inputs), ("index", index)):
            (baseline / f"{name}.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(value))
        resource = dict(schema="td-v10-spatial-weather-resource-v1", index_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "index.json"),
                        scope="complete eastward+westward both steps execution", complete=True,
                        monitor_error=None, sampling_interval_s=2, sample_count=1,
                        peak_rss_bytes=100, peak_private_bytes=100)
        (baseline / "resource.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(resource))
        acceptance_path = root / "acceptance.json"
        acceptance = dict(schema="td-independent-final-spatial-weather-v10-v1", io_chain_accepted=True,
                          index_path=str(baseline / "index.json"), index_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "index.json"),
                          resource_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "resource.json"),
                      acceptance_arguments=dict(
                          run_inputs_record=dict(path=str(baseline / "run-inputs.json"), expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "run-inputs.json")),
                          execution_resource_record=dict(path=str(baseline / "resource.json"), expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "resource.json"))),
                      cold_acceptance=dict(io_chain_accepted=True))
        acceptance_path.write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
        deadline = (_m4_test_run_td_v10_temporal_refinement_datetime.now(_m4_test_run_td_v10_temporal_refinement_timezone.utc) + _m4_test_run_td_v10_temporal_refinement_timedelta(hours=5)).isoformat()
        arguments = (baseline, _m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "index.json"), _m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "resource.json"),
                     _m4_test_run_td_v10_temporal_refinement_file_sha256(baseline / "run-inputs.json"),
                     dict(path=str(acceptance_path), expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(acceptance_path)),
                     status, deadline, root / "new")
        return arguments, index, resource, inputs

    def test_prepare_has_fixed_index_contract_and_does_not_simulate(self):
        with _m4_test_run_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            args, _, _, _ = self.fixture(directory)
            with _m4_test_run_td_v10_temporal_refinement_patch("tools.run_td_v10_temporal_refinement._check_code"), \
                    _m4_test_run_td_v10_temporal_refinement_patch("tools.run_td_v10_temporal_refinement.file_sha256", wraps=_m4_test_run_td_v10_temporal_refinement_file_sha256) as digest, \
                    _m4_test_run_td_v10_temporal_refinement_patch('terrain_pipeline.basin_storage.PRIMARY_PATH', args[0] / "index.json"):
                original_sha = args[0] / "index.json"
                inputs_path = args[0] / "run-inputs.json"
                data = _m4_test_run_td_v10_temporal_refinement_json.loads(inputs_path.read_text())
                data["primary_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(original_sha)
                inputs_path.write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(data))
                acceptance = _m4_test_run_td_v10_temporal_refinement_json.loads(_m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).read_text())
                acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(inputs_path)
                _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
                updated = (*args[:3], _m4_test_run_td_v10_temporal_refinement_file_sha256(inputs_path),
                           dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), *args[5:])
                plan = _m4_test_run_td_v10_temporal_refinement_prepare(*updated)
                self.assertEqual(plan["new_step_s"], _m4_test_run_td_v10_temporal_refinement_STEP_S)
                self.assertEqual(plan["reference_step_s"], _m4_test_run_td_v10_temporal_refinement_REFERENCE_STEP_S)
                self.assertEqual(plan["expected_new_pages"], 48)
                self.assertEqual(plan["estimated_new_elapsed_s"], 96.)
                self.assertTrue(plan["execution_ready"])
                self.assertFalse(_m4_test_run_td_v10_temporal_refinement_Path(plan["output"]).exists())
                self.assertGreater(digest.call_count, 96)

    def test_rejects_missing_and_incomplete_baseline(self):
        with _m4_test_run_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            args, index, resource, _ = self.fixture(directory)
            with _m4_test_run_td_v10_temporal_refinement_patch("tools.run_td_v10_temporal_refinement._check_code"):
                with self.assertRaises(ValueError):
                    _m4_test_run_td_v10_temporal_refinement_prepare(*args[:1], "0" * 64, *args[2:])
                index["scenarios"]["eastward"]["pages"]["1.25"].pop()
                (args[0] / "index.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(index))
                resource["index_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "index.json")
                (args[0] / "resource.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(resource))
                acceptance = _m4_test_run_td_v10_temporal_refinement_json.loads(_m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).read_text())
                acceptance["index_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "index.json")
                acceptance["resource_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json")
                acceptance["acceptance_arguments"]["execution_resource_record"]["expected_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json")
                _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
                updated = (args[0], _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "index.json"), _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json"),
                           args[3], dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), *args[5:])
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    _m4_test_run_td_v10_temporal_refinement_prepare(*updated)

    def test_rejects_resource_code_status_and_deadline(self):
        with _m4_test_run_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            args, _, resource, _ = self.fixture(directory)
            resource["complete"] = False
            (args[0] / "resource.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(resource))
            acceptance = _m4_test_run_td_v10_temporal_refinement_json.loads(_m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).read_text())
            acceptance["resource_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json")
            acceptance["acceptance_arguments"]["execution_resource_record"]["expected_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json")
            _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
            updated = (args[0], args[1], _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json"),
                       args[3], dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), *args[5:])
            with self.assertRaisesRegex(ValueError, "resource"):
                _m4_test_run_td_v10_temporal_refinement_prepare(*updated)
            resource["complete"] = True
            (args[0] / "resource.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(resource))
            acceptance = _m4_test_run_td_v10_temporal_refinement_json.loads(_m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).read_text())
            acceptance["resource_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json")
            acceptance["acceptance_arguments"]["execution_resource_record"]["expected_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json")
            _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
            updated = (args[0], args[1], _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "resource.json"),
                       args[3], dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), *args[5:])
            with self.assertRaisesRegex(ValueError, "frozen code"):
                _m4_test_run_td_v10_temporal_refinement_prepare(*updated)
            args[5].write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(dict(schema="td-ten-hour-pipeline-status-v1", state="running", pid=0,
                                               deadline_utc=(_m4_test_run_td_v10_temporal_refinement_datetime.now(_m4_test_run_td_v10_temporal_refinement_timezone.utc) + _m4_test_run_td_v10_temporal_refinement_timedelta(hours=6)).isoformat())))
            with self.assertRaisesRegex(ValueError, "active"):
                _m4_test_run_td_v10_temporal_refinement_prepare(*updated)
            args[5].write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(dict(schema="td-ten-hour-pipeline-status-v1", state="diagnostic_stop", pid=0,
                                               deadline_utc=(_m4_test_run_td_v10_temporal_refinement_datetime.now(_m4_test_run_td_v10_temporal_refinement_timezone.utc) + _m4_test_run_td_v10_temporal_refinement_timedelta(hours=6)).isoformat())))
            expired = (_m4_test_run_td_v10_temporal_refinement_datetime.now(_m4_test_run_td_v10_temporal_refinement_timezone.utc) + _m4_test_run_td_v10_temporal_refinement_timedelta(minutes=2)).isoformat()
            with self.assertRaises(TimeoutError):
                _m4_test_run_td_v10_temporal_refinement_prepare(*updated[:6], expired, updated[7])

    def test_rejects_changed_gates_acceptance_path_and_late_deadline(self):
        with _m4_test_run_td_v10_temporal_refinement_tempfile.TemporaryDirectory() as directory:
            args, _, _, inputs = self.fixture(directory)
            with _m4_test_run_td_v10_temporal_refinement_patch("tools.run_td_v10_temporal_refinement._check_code"):
                inputs["depth_gate_m"] = .002
                (args[0] / "run-inputs.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(inputs))
                acceptance = _m4_test_run_td_v10_temporal_refinement_json.loads(_m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).read_text())
                acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "run-inputs.json")
                _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
                updated = (*args[:3], _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "run-inputs.json"),
                           dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), *args[5:])
                with self.assertRaisesRegex(ValueError, "inputs/resource"):
                    _m4_test_run_td_v10_temporal_refinement_prepare(*updated)
                inputs["depth_gate_m"] = .001
                (args[0] / "run-inputs.json").write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(inputs))
                acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"] = _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "run-inputs.json")
                acceptance["acceptance_arguments"]["run_inputs_record"]["path"] = str(args[0] / "wrong.json")
                _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
                updated = (*args[:3], _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "run-inputs.json"),
                           dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), *args[5:])
                with self.assertRaisesRegex(ValueError, "full-final"):
                    _m4_test_run_td_v10_temporal_refinement_prepare(*updated)
                acceptance["acceptance_arguments"]["run_inputs_record"]["path"] = str(args[0] / "run-inputs.json")
                _m4_test_run_td_v10_temporal_refinement_Path(args[4]["path"]).write_text(_m4_test_run_td_v10_temporal_refinement_json.dumps(acceptance))
                later = (_m4_test_run_td_v10_temporal_refinement_datetime.now(_m4_test_run_td_v10_temporal_refinement_timezone.utc) + _m4_test_run_td_v10_temporal_refinement_timedelta(hours=7)).isoformat()
                updated = (*args[:3], _m4_test_run_td_v10_temporal_refinement_file_sha256(args[0] / "run-inputs.json"),
                           dict(path=args[4]["path"], expected_sha256=_m4_test_run_td_v10_temporal_refinement_file_sha256(args[4]["path"])), args[5], later, args[7])
                with self.assertRaisesRegex(ValueError, "exceeds pipeline deadline"):
                    _m4_test_run_td_v10_temporal_refinement_prepare(*updated)

# --- tests/test_td_v10_refinement_full_binding.py:15 ---
class V10RefinementFullBindingFullRefinementBindingTests(_m4_test_td_v10_refinement_full_binding_unittest.TestCase):
    def save_json(self, path, value):
        _m4_test_td_v10_refinement_full_binding_publish_bytes(path, _m4_test_td_v10_refinement_full_binding_json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
        return dict(path=str(path.resolve()), expected_sha256=_m4_test_td_v10_refinement_full_binding_file_sha256(path))

    def fixture(self, root):
        root = _m4_test_td_v10_refinement_full_binding_Path(root)
        baseline_run, new_run = root / "baseline", root / "new"
        helper = TestAuditTdProfile10TemporalRefinementIndependentRefinementTests()
        scenarios_old, scenarios_new = {}, {}
        for direction in ("eastward", "westward"):
            reference, arguments = helper.sequence(baseline_run / (direction + "-1.25s"), 1.25)
            fine, _ = helper.sequence(new_run / (direction + "-0.625s"), .625)
            scenarios_old[direction] = dict(pages={"2.5":[], "1.25":reference}, forcing_identity="b" * 64)
            scenarios_new[direction] = dict(pages=fine, forcing_identity="b" * 64)
        files = {}
        for name in ("source", "hierarchy", "eastward", "westward"):
            path = root / (name + ".npz")
            _m4_test_td_v10_refinement_full_binding_publish_bytes(path, ("synthetic-" + name).encode("ascii"))
            files[name] = dict(path=str(path), expected_sha256=_m4_test_td_v10_refinement_full_binding_file_sha256(path), expected_identity="a" * 64)
        sources = dict(hierarchy=files["hierarchy"], weather_records={name:files[name] for name in ("eastward", "westward")})
        weather_index = dict(schema="td-native-storm-forcing-index-v1", source=files["source"],
                             cases={name:dict(record=files[name]) for name in ("eastward", "westward")})
        weather_pin = self.save_json(root / "weather-index.json", weather_index)
        sources["weather_index"] = dict(path=weather_pin["path"], sha256=weather_pin["expected_sha256"])
        for name in ("eastward", "westward"):
            scenarios_old[name]["weather_record"] = files[name]
            scenarios_new[name]["weather_record"] = files[name]
        code_names = ("terrain_pipeline/common_infra.py", 'terrain_pipeline/runoff.py',
                      'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_topology.py',
                      'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                      'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                      'terrain_pipeline/climate_forcing.py', 'terrain_pipeline/climate_forcing.py',
                      "terrain_pipeline/td_native_weather_storage_inputs.py", 'terrain_pipeline/basin_storage.py',
                      'tools/verify_basin_storage_execution.py', 'tools/verify_basin_storage_execution.py',
                      'tools/verify_basin_storage.py')
        codes = {name:_m4_test_td_v10_refinement_full_binding_file_sha256(_m4_test_td_v10_refinement_full_binding_auditor.ROOT / name) for name in code_names}
        inputs = dict(steps_s=[2.5, 1.25], code_sha256=codes, depth_gate_m=.001, receiver_gate=.01,
                      job_max_bytes=1073741824, primary_sha256=files["source"]["expected_sha256"],
                      forcing_identities=dict(eastward="b" * 64, westward="b" * 64), **sources)
        baseline = dict(inputs=self.save_json(baseline_run / "run-inputs.json", inputs))
        baseline["index"] = self.save_json(baseline_run / "index.json", dict(schema="td-v10-spatial-weather-hour-pages-index-v1",
                                                                          steps_s=[2.5, 1.25], scenarios=scenarios_old, code_sha256=codes))
        resource_fields = dict(complete=True, peak_rss_bytes=100, peak_private_bytes=200, sample_count=2, monitor_error=None)
        baseline["resource"] = self.save_json(baseline_run / "resource.json", dict(**resource_fields,
            index_sha256=baseline["index"]["expected_sha256"], scope="complete eastward+westward both steps execution"))
        accepted = dict(schema="td-independent-final-spatial-weather-v10-v1", io_chain_accepted=True,
                        index_path=baseline["index"]["path"], index_sha256=baseline["index"]["expected_sha256"],
                        resource_sha256=baseline["resource"]["expected_sha256"], cold_acceptance=dict(io_chain_accepted=True),
                        acceptance_arguments=dict(run_inputs_record=baseline["inputs"], execution_resource_record=baseline["resource"]))
        baseline["acceptance"] = self.save_json(baseline_run / "acceptance.json", accepted)
        status_pin = self.save_json(root / "status.json", dict(schema="td-ten-hour-pipeline-status-v1", state="diagnostic_stop",
                                       deadline_utc="2026-10-03T04:53:05+00:00", baseline_acceptance_record=baseline["acceptance"]))
        runner = _m4_test_td_v10_refinement_full_binding_auditor.ROOT / "tools/run_td_v10_temporal_refinement.py"
        plan = dict(schema="td-v10-temporal-refinement-plan-v1", baseline_records=baseline, source_records=sources,
                    new_step_s=.625, reference_step_s=1.25, depth_gate_m=.001, receiver_gate=.01,
                    job_max_bytes=1073741824, chunk_max_face_steps=6000000000,
                    expected_new_pages=48, expected_reference_pages=48, expected_baseline_pages=96,
                    pipeline_status_record=status_pin, deadline_utc="2026-10-03T04:53:05+00:00",
                    baseline_code_sha256=codes, runner_sha256=_m4_test_td_v10_refinement_full_binding_file_sha256(runner),
                    hydraulic_ready=False, transient_converged=False, publishable=False)
        new_inputs = self.save_json(new_run / "run-inputs.json", plan)
        self.save_json(new_run / "execution-code.json", dict(baseline_code_sha256=codes, runner_sha256=_m4_test_td_v10_refinement_full_binding_file_sha256(runner),
                                                               runner_source=runner.read_text(encoding="utf-8")))
        new_index = self.save_json(new_run / "index.json", dict(schema="td-v10-temporal-refinement-index-v1", scenarios=scenarios_new,
            new_step_s=.625, reference_step_s=1.25, baseline_records=baseline, source_records=sources, code_sha256=codes,
            run_inputs_record=new_inputs, hydraulic_ready=False, transient_converged=False, publishable=False))
        new_resource = self.save_json(new_run / "resource.json", dict(**resource_fields,
            schema="td-v10-temporal-refinement-resource-v1", index_sha256=new_index["expected_sha256"],
            scope="complete new eastward+westward 0.625s 48 pages only", code_sha256=codes,
            within_1GiB=True, job_max_bytes=1073741824))

        def synthetic_record(record):
            path = record["path"]
            if path == files["hierarchy"]["path"]:
                return arguments["topology"], dict(arguments["geometry"], source_identity_sha256="a" * 64)
            if path in (files["eastward"]["path"], files["westward"]["path"]):
                weather_arrays = dict(rain_mm_h=arguments["rain"], valid_mask=arguments["topology"]["valid_mask"],
                                      protected_mask=arguments["topology"]["protected_mask"], time_edges_s=_m4_test_td_v10_refinement_full_binding_np.arange(25) * 3600.)
                weather_metadata = dict(forcing_identity="b" * 64, plan=dict(dt_s=3600., start_s=0., spacing_m=30.,
                                                                             origin_m_xz=[0., 0.], source_identity="a" * 64))
                return weather_arrays, weather_metadata
            if path == files["source"]["path"]:
                return {}, {}
            return _m4_test_td_v10_refinement_full_binding_read_record(record)
        return new_run, new_index, new_inputs, new_resource, files, synthetic_record

    def test_complete_auditor_binds_both_executions_and_rejects_missing_resource(self):
        with _m4_test_td_v10_refinement_full_binding_tempfile.TemporaryDirectory() as directory:
            run, index, inputs, resource, files, reader = self.fixture(directory)
            with _m4_test_td_v10_refinement_full_binding_patch.object(_m4_test_td_v10_refinement_full_binding_auditor, "read_record", side_effect=reader), \
                    _m4_test_td_v10_refinement_full_binding_patch.object(_m4_test_td_v10_refinement_full_binding_auditor, "numerical_identity", return_value="b" * 64), \
                    _m4_test_td_v10_refinement_full_binding_patch.object(_m4_test_td_v10_refinement_full_binding_auditor, "PRIMARY_PATH", _m4_test_td_v10_refinement_full_binding_Path(files["source"]["path"])), \
                    _m4_test_td_v10_refinement_full_binding_patch.object(_m4_test_td_v10_refinement_full_binding_auditor, "PRIMARY_SHA256", files["source"]["expected_sha256"]):
                result = _m4_test_td_v10_refinement_full_binding_auditor.audit(run, index["expected_sha256"], inputs["expected_sha256"], resource["expected_sha256"])
                self.assertTrue(result["io_chain_accepted"])
                self.assertTrue(result["all_saved_numerical_gates_passed"])
                self.assertTrue(result["separate_execution_resources_authenticated"])
                self.assertFalse(result["physics_changed"])
                changed = _m4_test_td_v10_refinement_full_binding_json.loads(_m4_test_td_v10_refinement_full_binding_Path(resource["path"]).read_text(encoding="utf-8"))
                changed["peak_private_bytes"] = 0
                bad = self.save_json(_m4_test_td_v10_refinement_full_binding_Path(directory) / "bad-resource.json", changed)
                original = _m4_test_td_v10_refinement_full_binding_auditor.pinned_json
                with _m4_test_td_v10_refinement_full_binding_patch.object(_m4_test_td_v10_refinement_full_binding_auditor, "pinned_json", side_effect=lambda record, *args: original(
                        bad if record["path"] == resource["path"] else record, *args)):
                    with self.assertRaisesRegex(ValueError, "resource"):
                        _m4_test_td_v10_refinement_full_binding_auditor.audit(run, index["expected_sha256"], inputs["expected_sha256"], resource["expected_sha256"])

# --- tests/test_td_weather_v10_final_binding.py:11 ---
class WeatherProfile10FinalBindingFinalV10BindingTests(_m4_test_td_weather_v10_final_binding_unittest.TestCase):
    def setUp(self):
        self.directory = _m4_test_td_weather_v10_final_binding_tempfile.TemporaryDirectory()
        self.run = _m4_test_td_weather_v10_final_binding_Path(self.directory.name).resolve()
        self.inputs = dict(weather_records={}, hierarchy=dict(path="fixed-hierarchy", expected_sha256="a" * 64),
                           forcing_identities={})
        self.index = dict(scenarios={})
        self.records = {}
        self.cold = dict(cases={})
        self.reports = {}
        for direction in ("eastward", "westward"):
            weather = dict(path=direction, expected_sha256="b" * 64)
            self.inputs["weather_records"][direction] = weather
            self.inputs["forcing_identities"][direction] = direction
            comparison = dict(max_saved_depth_difference_m=.02, cumulative_receiver_relative_l1=.0001, gate_passed=False)
            comparison_path = self.run / (direction + "-comparison.json")
            comparison_path.write_text(_m4_test_td_weather_v10_final_binding_json.dumps(comparison), encoding="utf-8")
            self.index["scenarios"][direction] = comparison
            self.cold["cases"][direction] = dict(numerical_gate_passed=False)
            report = dict(schema="td-independent-spatial-weather-v10-v1", comparison_path=str(comparison_path),
                          comparison_sha256=_m4_test_td_weather_v10_final_binding_file_sha256(comparison_path), weather_record=weather,
                          hierarchy_record=self.inputs["hierarchy"], forcing_identity=direction,
                          substeps_s=[2.5, 1.25], saved_frames=25, full_spatial_rain_checked=True,
                          compartment_ledgers_checked=True, checkpoint_chain_checked=True, solver_advanced=False,
                          hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                          page_budget_audits={str(step):dict(whole_period_passed=True) for step in (2.5, 1.25)},
                          max_frame=10, max_cell=42, **comparison)
            self.reports[direction] = report
            self.write_report(direction, report)

    def tearDown(self):
        self.directory.cleanup()

    def write_report(self, direction, report):
        path = self.run / (direction + "-audit.json")
        path.write_text(_m4_test_td_weather_v10_final_binding_json.dumps(report), encoding="utf-8")
        self.records[direction] = dict(path=str(path), expected_sha256=_m4_test_td_weather_v10_final_binding_file_sha256(path))

    def bind(self):
        return _m4_test_td_weather_v10_final_binding_bind_numerical(self.index, self.inputs, self.run, self.records, self.cold)

    def test_failed_numerical_gate_is_preserved(self):
        self.assertFalse(self.bind()["eastward"]["gate_passed"])

    def test_rehashed_report_cannot_upgrade_failed_gate(self):
        changed = _m4_test_td_weather_v10_final_binding_copy.deepcopy(self.reports["eastward"])
        changed["gate_passed"] = True
        self.write_report("eastward", changed)
        with self.assertRaisesRegex(ValueError, "reduction disagreement"):
            self.bind()

    def test_report_missing_compartment_audit_rejected(self):
        changed = _m4_test_td_weather_v10_final_binding_copy.deepcopy(self.reports["eastward"])
        changed["compartment_ledgers_checked"] = False
        self.write_report("eastward", changed)
        with self.assertRaisesRegex(ValueError, "audit missing"):
            self.bind()

    def test_report_from_other_execution_rejected(self):
        changed = _m4_test_td_weather_v10_final_binding_copy.deepcopy(self.reports["westward"])
        changed["comparison_sha256"] = "c" * 64
        self.write_report("westward", changed)
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.bind()

    def test_partial_direction_coverage_rejected(self):
        self.records.pop("westward")
        with self.assertRaisesRegex(ValueError, "both independent"):
            self.bind()

    def test_empty_budget_evidence_rejected(self):
        changed = _m4_test_td_weather_v10_final_binding_copy.deepcopy(self.reports["eastward"])
        changed["page_budget_audits"] = {}
        self.write_report("eastward", changed)
        with self.assertRaisesRegex(ValueError, "both period"):
            self.bind()

# --- tests/test_td_native_weather_storage_v10_io.py:24 ---
class NativeWeatherStorageProfile10IoNativeWeatherV10IoTests(_m4_test_td_native_weather_storage_v10_io_unittest.TestCase):
    def setUp(self):
        self.temp = _m4_test_td_native_weather_storage_v10_io_tempfile.TemporaryDirectory()
        self.root = _m4_test_td_native_weather_storage_v10_io_Path(self.temp.name)
        self.hierarchy = _m4_test_td_native_weather_storage_v10_io_build_basin_hierarchy(_m4_test_td_native_weather_storage_v10_io_make_td_source(_m4_test_td_native_weather_storage_v10_io_np.array([[0., 1.]]), spacing_m=30.))
        self.parameters = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(_m4_test_td_native_weather_storage_v10_io_PHYSICS)
        self.runoff = _m4_test_td_native_weather_storage_v10_io_asdict(_m4_test_td_native_weather_storage_v10_io_RunoffParameters())
        self.rain = _m4_test_td_native_weather_storage_v10_io_np.full((1, 2), 1., _m4_test_td_native_weather_storage_v10_io_np.float64)
        topology = self.hierarchy["arrays"]
        arrays = {name:topology[name].copy() for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells")}
        arrays["boundary_width_m"] = _m4_test_td_native_weather_storage_v10_io_np.zeros(len(topology["boundary_cells"]), _m4_test_td_native_weather_storage_v10_io_np.float64)
        arrays.update({name:_m4_test_td_native_weather_storage_v10_io_np.zeros((2, 2), _m4_test_td_native_weather_storage_v10_io_np.float64) for name in _m4_test_td_native_weather_storage_v10_io_STATES})
        arrays["soil_mm"][:] = [[30., 30.], [31., 31.]]
        arrays.update({name:_m4_test_td_native_weather_storage_v10_io_np.zeros((1, 2), _m4_test_td_native_weather_storage_v10_io_np.float64) for name in _m4_test_td_native_weather_storage_v10_io_LEDGERS})
        arrays["rain_mm_h"] = self.rain.copy()
        for name in ("rain_volume_m3", "rain_infiltration_m3", "storage_change_m3"):
            arrays[name][:] = .9
        arrays["infiltration_capacity_m3"][:] = 13.5
        arrays.update({name:_m4_test_td_native_weather_storage_v10_io_np.zeros(len(topology["face_cells"]) if name.startswith(("face_", "active_")) else 2, _m4_test_td_native_weather_storage_v10_io_np.float64) for name in _m4_test_td_native_weather_storage_v10_io_FLUX})
        metadata = dict(schema="td-v10-hour-page-v1", profile=_m4_test_td_native_weather_storage_v10_io_PROFILE, hierarchy_identity=self.hierarchy["identity_sha256"],
                        forcing_identity="a"*64, cells=2, faces=len(topology["face_cells"]), substeps=1440,
                        forcing_hour_offset=0, dt_s=3600., substep_s=2.5, spacing_m=30.,
                        origin_m_xz=self.hierarchy["metadata"]["origin_m_xz"], start_s=0., end_s=3600.,
                        positivity_cfl=.05, parameters=dict(self.parameters, substep_s=2.5), runoff_parameters=self.runoff,
                        physics=_m4_test_td_native_weather_storage_v10_io_PHYSICS_SEMANTICS, permanent_lake_impermeability="not modelled; requires independent material mask",
                        activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration",
                        hydraulic_ready=False, transient_converged=False, publishable=False)
        self.storage = dict(arrays=arrays, metadata=metadata)
        self.checkpoint = dict(arrays={name:arrays[name][1].copy() for name in _m4_test_td_native_weather_storage_v10_io_STATES},
                               metadata=dict(metadata, schema="td-v10-hour-checkpoint-v1"))
        self.checkpoint["arrays"].update({name:_m4_test_td_native_weather_storage_v10_io_np.zeros(2) for name in _m4_test_td_native_weather_storage_v10_io_ERRORS})
        self.checkpoint["arrays"].update({"cumulative_"+name:arrays[name].copy() for name in _m4_test_td_native_weather_storage_v10_io_FLUX})

    def tearDown(self):
        self.temp.cleanup()

    def _save(self, name, result):
        result["identity_sha256"] = _m4_test_td_native_weather_storage_v10_io_identity(result["arrays"], result["metadata"])
        path = self.root / (name+".npz")
        if path.exists():
            path.unlink()
        _m4_test_td_native_weather_storage_v10_io_save_bundle(path, result, validator=lambda value:None)
        return dict(path=str(path), expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(path), expected_identity=result["identity_sha256"])

    def _load(self):
        storage_record = self._save("storage", self.storage)
        self.checkpoint["metadata"]["last_page_identity"] = storage_record["expected_identity"]
        checkpoint_record = self._save("checkpoint", self.checkpoint)
        return _m4_test_td_native_weather_storage_v10_io_load_native_weather_v10_hour(storage_record, checkpoint_record, hierarchy=self.hierarchy,
            rain_mm_h=self.rain, forcing_identity="a"*64, hour=0, step_s=2.5,
            parameters=self.parameters, runoff_parameters=self.runoff)

    def test_valid_actual_compartment_fixture(self):
        result = self._load()
        self.assertTrue(result["hour_io_accepted"])
        self.assertFalse(result["complete_index_accepted"])
        self.assertFalse(result["solver_advanced"])

    def test_rehashed_rain_and_compartment_reallocation_rejected(self):
        original = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(self.storage)
        for kind in ("rain", "soil", "capacity", "receiver", "time", "origin"):
            with self.subTest(kind=kind):
                self.storage = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(original)
                arrays = self.storage["arrays"]
                if kind == "rain":
                    arrays["rain_mm_h"][:] = [[.5, 1.5]]
                elif kind == "soil":
                    arrays["rain_infiltration_m3"][:] = .4
                    arrays["rain_excess_m3"][:] = .5
                elif kind == "capacity":
                    arrays["infiltration_capacity_m3"][:] = 20.
                elif kind == "time":
                    self.storage["metadata"].update(forcing_hour_offset=1,start_s=3600.,end_s=7200.)
                elif kind == "origin":
                    self.storage["metadata"]["origin_m_xz"] = [1.,0.]
                else:
                    arrays["routed_volume_m3"][0] = .1
                with self.assertRaises(ValueError):
                    self._load()

    def test_checkpoint_endpoint_cumulative_and_config_rejected(self):
        original = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(self.checkpoint)
        for kind in ("state", "cumulative", "profile", "config", "offset"):
            with self.subTest(kind=kind):
                self.checkpoint = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(original)
                if kind == "state":
                    self.checkpoint["arrays"]["soil_mm"][0] += 1.
                elif kind == "cumulative":
                    self.checkpoint["arrays"]["cumulative_face_forward_m3"][0] = .1
                elif kind == "profile":
                    self.checkpoint["metadata"]["profile"] = "v9-compiled-hour-loop-v8-equivalent-v1"
                elif kind == "offset":
                    self.checkpoint["metadata"]["forcing_hour_offset"] = 1
                else:
                    self.checkpoint["metadata"]["parameters"]["face_conductance_m_s"] = .7
                with self.assertRaises(ValueError):
                    self._load()

    def test_wrong_slice_unknown_shape_and_step_rejected(self):
        original = self.rain.copy()
        for rain in (_m4_test_td_native_weather_storage_v10_io_np.full((2,1),1.), _m4_test_td_native_weather_storage_v10_io_np.full((1,2),2.), _m4_test_td_native_weather_storage_v10_io_np.full((1,2),_m4_test_td_native_weather_storage_v10_io_np.nan)):
            self.rain = rain
            with self.assertRaises(ValueError):
                self._load()
        self.rain = original
        with self.assertRaises(ValueError):
            _m4_test_td_native_weather_storage_v10_io_load_native_weather_v10_hour({}, {}, hierarchy=self.hierarchy, rain_mm_h=self.rain,
                forcing_identity="a"*64, hour=0, step_s=.625, parameters=self.parameters, runoff_parameters=self.runoff)

    def _whole_fixture(self):
        from terrain_pipeline.basin_storage import save_td_source as save_td_source
        from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
        from terrain_pipeline.climate_forcing import generate_native_storm
        from terrain_pipeline.climate_forcing import fixed_storm
        from terrain_pipeline.climate_forcing import save_native_storm
        source = _m4_test_td_native_weather_storage_v10_io_make_td_source(_m4_test_td_native_weather_storage_v10_io_np.array([[0.,1.]]),spacing_m=30.)
        source_path, hierarchy_path = self.root/"source.npz", self.root/"hierarchy.npz"
        save_td_source(source_path,source)
        save_basin_hierarchy(hierarchy_path,self.hierarchy)
        source_record = dict(path=str(source_path),expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(source_path),expected_identity=source["identity_sha256"])
        hierarchy_record = dict(path=str(hierarchy_path),expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(hierarchy_path),expected_identity=self.hierarchy["identity_sha256"])
        def write(name,value):
            target = self.root/name
            target.write_text(_m4_test_td_native_weather_storage_v10_io_json.dumps(value),encoding="utf8")
            return dict(path=str(target),expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(target))
        fixture_code = self.root/"fixture-code.txt"
        fixture_code.write_text("fixed synthetic account construction, no solver",encoding="utf8")
        codes = {fixture_code.name:_m4_test_td_native_weather_storage_v10_io_file_sha256(fixture_code)}
        weather_cases, scenarios = {}, {}
        budgets = {str(step):dict(chunk_face_steps=int(3600/step),global_face_steps_per_direction=24*int(3600/step)) for step in (2.5,1.25)}
        for direction in ("eastward","westward"):
            weather = generate_native_storm(source_record,parameters=fixed_storm(source,direction))
            weather_path = self.root/(direction+".npz")
            save_native_storm(weather_path,weather)
            record = dict(path=str(weather_path),expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(weather_path),expected_identity=weather["identity_sha256"])
            forcing = weather["metadata"]["forcing_identity"]
            weather_cases[direction] = dict(record=record,plan=weather["metadata"]["plan"],forcing_identity=forcing)
            groups = {}
            for step in (2.5,1.25):
                pages = []
                soil = _m4_test_td_native_weather_storage_v10_io_np.full(2,30.)
                for hour in range(24):
                    storage = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(self.storage)
                    arrays = storage["arrays"]
                    rain = weather["arrays"]["rain_mm_h"][hour].reshape(1,2)
                    arrays["soil_mm"][0] = soil
                    arrays["soil_mm"][1] = soil + rain[0]
                    soil = arrays["soil_mm"][1].copy()
                    arrays["rain_mm_h"] = rain.copy()
                    for name in ("rain_volume_m3","rain_infiltration_m3","storage_change_m3"):
                        arrays[name] = rain*.9
                    storage["metadata"].update(forcing_identity=forcing,forcing_hour_offset=hour,start_s=hour*3600.,
                        end_s=(hour+1)*3600.,substeps=int(3600/step),substep_s=step,positivity_cfl=.6*step/30.,parameters=dict(self.parameters,substep_s=step))
                    directory = self.root/f"{direction}-{step:g}s"/f"hour-{hour:02d}"
                    directory.mkdir(parents=True)
                    storage["identity_sha256"] = _m4_test_td_native_weather_storage_v10_io_identity(arrays,storage["metadata"])
                    _m4_test_td_native_weather_storage_v10_io_save_bundle(directory/"storage.npz",storage,validator=lambda value:None)
                    cp = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(self.checkpoint)
                    cp["arrays"]["soil_mm"] = soil.copy()
                    cp["metadata"] = dict(storage["metadata"],schema="td-v10-hour-checkpoint-v1",last_page_identity=storage["identity_sha256"])
                    cp["identity_sha256"] = _m4_test_td_native_weather_storage_v10_io_identity(cp["arrays"],cp["metadata"])
                    _m4_test_td_native_weather_storage_v10_io_save_bundle(directory/"checkpoint.npz",cp,validator=lambda value:None)
                    pages.append(dict(hour=hour,storage=dict(path=str(directory/"storage.npz"),expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(directory/"storage.npz"),expected_identity=storage["identity_sha256"]),
                        checkpoint=dict(path=str(directory/"checkpoint.npz"),expected_sha256=_m4_test_td_native_weather_storage_v10_io_file_sha256(directory/"checkpoint.npz"),expected_identity=cp["identity_sha256"]),
                        forcing_identity=forcing,chunk_work_face_steps=int(3600/step)))
                groups[str(step)] = pages
            scenarios[direction] = dict(schema="td-v10-spatial-weather-comparison-v1",pages=groups,
                hour_comparisons=[dict(hour=hour,max_depth_difference_m=0.,frame=0,cell=0) for hour in range(24)],
                max_saved_depth_difference_m=0.,cumulative_receiver_relative_l1=0.,gate_passed=True,
                weather_record=record,forcing_identity=forcing,steps_s=[2.5,1.25],hydraulic_ready=False,publishable=False)
        weather_record = write("weather-index.json",dict(schema="td-native-storm-forcing-index-v1",source=source_record,cases=weather_cases))
        weather_pin = dict(path=weather_record["path"],sha256=weather_record["expected_sha256"])
        index = dict(schema="td-v10-spatial-weather-hour-pages-index-v1",scenarios=scenarios,weather_index=weather_pin,steps_s=[2.5,1.25],
                     code_sha256=codes,budgets=budgets,all_numerical_gates_passed=True,hydraulic_ready=False,transient_converged=False,publishable=False)
        index_record = write("index.json",index)
        inputs_record = write("run-inputs.json",dict(schema="td-v10-spatial-weather-run-inputs-v1",weather_index=weather_pin,
            weather_records={name:value["record"] for name,value in weather_cases.items()},hierarchy=hierarchy_record,primary_sha256="0"*64,
            steps_s=[2.5,1.25],budgets=budgets,chunk_max_face_steps=6000000000,job_max_bytes=1073741824,code_sha256=codes,
            physics_version="v10-unified-infiltration; not execution-equivalence",forcing_identities={name:value["forcing_identity"] for name,value in weather_cases.items()},depth_gate_m=.001,receiver_gate=.01))
        resource_record = write("resource.json",dict(schema="td-v10-spatial-weather-resource-v1",index_sha256=index_record["expected_sha256"],
            scope="complete eastward+westward both steps execution",complete=True,peak_rss_bytes=1000000,peak_private_bytes=1000000,sample_count=1,sampling_interval_s=2,monitor_error=None))
        return dict(expected_sha256=index_record["expected_sha256"],weather_index_record=weather_record,hierarchy_record=hierarchy_record,
                    source_record=source_record,run_inputs_record=inputs_record,execution_resource_record=resource_record,scope="synthetic_fixture",code_root=str(self.root))

    def _repin_index(self,index,args):
        path = self.root/"index.json"
        path.write_text(_m4_test_td_native_weather_storage_v10_io_json.dumps(index),encoding="utf8")
        args["expected_sha256"] = _m4_test_td_native_weather_storage_v10_io_file_sha256(path)
        path = self.root/"resource.json"
        resource = _m4_test_td_native_weather_storage_v10_io_json.loads(path.read_text())
        resource["index_sha256"] = args["expected_sha256"]
        path.write_text(_m4_test_td_native_weather_storage_v10_io_json.dumps(resource),encoding="utf8")
        args["execution_resource_record"]["expected_sha256"] = _m4_test_td_native_weather_storage_v10_io_file_sha256(path)

    def test_complete_index_cold_and_fresh_no_solver(self):
        args = self._whole_fixture()
        result = _m4_test_td_native_weather_storage_v10_io_load_native_weather_storage_v10_index(self.root/"index.json",**args)
        self.assertTrue(result["io_chain_accepted"])
        self.assertTrue(result["cases"]["eastward"]["numerical_gate_passed"])
        path = self.root/"arguments.json"
        path.write_text(_m4_test_td_native_weather_storage_v10_io_json.dumps(args),encoding="utf8")
        script = "import sys,json,importlib.abc\nclass Block(importlib.abc.MetaPathFinder):\n def find_spec(self,fullname,path=None,target=None):\n  if fullname in ('terrain_pipeline.td_basin_storage_v10','terrain_pipeline.td_basin_forcing_v10','terrain_pipeline.td_basin_storage_compiled','terrain_pipeline.td_basin_storage_compiled_driver'):\n   raise RuntimeError('solver import forbidden')\nsys.meta_path.insert(0,Block())\nimport terrain_pipeline.basin_topology as td_basin_hierarchy; import terrain_pipeline.climate_forcing as td_native_storm_forcing\ndef forbidden(*args,**kwargs): raise RuntimeError('generation forbidden')\ntd_basin_hierarchy.build_basin_hierarchy=forbidden\ntd_native_storm_forcing.generate_native_storm=forbidden\nfrom terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_storage_v10_index\nassert load_native_weather_storage_v10_index(sys.argv[2],**json.load(open(sys.argv[1])))['io_chain_accepted']\n"
        completed = _m4_test_td_native_weather_storage_v10_io_subprocess.run([_m4_test_td_native_weather_storage_v10_io_sys.executable,"-c",script,str(path),str(self.root/"index.json")],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_complete_index_coverage_resource_and_gate_tamper(self):
        args = self._whole_fixture()
        original = _m4_test_td_native_weather_storage_v10_io_json.loads((self.root/"index.json").read_text())
        for kind in ("missing","order","step","gate"):
            with self.subTest(kind=kind):
                index = _m4_test_td_native_weather_storage_v10_io_copy.deepcopy(original)
                if kind == "missing":
                    index["scenarios"]["westward"]["pages"]["1.25"].pop()
                elif kind == "order":
                    index["scenarios"]["eastward"]["pages"]["2.5"].reverse()
                elif kind == "step":
                    index["steps_s"] = [5.,2.5]
                else:
                    index["all_numerical_gates_passed"] = False
                self._repin_index(index,args)
                with self.assertRaises(ValueError):
                    _m4_test_td_native_weather_storage_v10_io_load_native_weather_storage_v10_index(self.root/"index.json",**args)
        self._repin_index(original,args)
        path = self.root/"resource.json"
        resource = _m4_test_td_native_weather_storage_v10_io_json.loads(path.read_text())
        resource["peak_private_bytes"] = 1073741825
        path.write_text(_m4_test_td_native_weather_storage_v10_io_json.dumps(resource),encoding="utf8")
        args["execution_resource_record"]["expected_sha256"] = _m4_test_td_native_weather_storage_v10_io_file_sha256(path)
        with self.assertRaisesRegex(ValueError,"resource exceeded"):
            _m4_test_td_native_weather_storage_v10_io_load_native_weather_storage_v10_index(self.root/"index.json",**args)

    def test_gross_swap_preserving_total_water_rejected(self):
        self.storage["arrays"]["soil_et_m3"][:] = .05
        self.storage["arrays"]["percolation_m3"][:] = .05
        self.storage["arrays"]["soil_mm"][1] -= .1/.9
        self.storage["arrays"]["slow_mm"][1] += .05/.9
        self.storage["arrays"]["storage_change_m3"][:] -= .05
        for name in _m4_test_td_native_weather_storage_v10_io_STATES:
            self.checkpoint["arrays"][name] = self.storage["arrays"][name][1].copy()
        self.assertTrue(self._load()["hour_io_accepted"])
        self.storage["arrays"]["percolation_m3"][:] = 0.
        self.storage["arrays"]["surface_infiltration_m3"][:] = .05
        with self.assertRaisesRegex(ValueError,"compartment"):
            self._load()

# --- tests/test_td_native_weather_v10_review.py:13 ---
class NativeWeatherProfile10ReviewNativeWeatherV10ReviewTests(_m4_test_td_native_weather_v10_review_unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = NativeWeatherStorageProfile10IoNativeWeatherV10IoTests()
        cls.fixture.setUp()
        cls.root = cls.fixture.root
        cls.arguments = cls.fixture._whole_fixture()
        cls.directory = cls.root.parent/(cls.root.name+"-review")
        cls.result = _m4_test_td_native_weather_v10_review_export_native_weather_v10_review(cls.root/"index.json",cls.directory,acceptance_arguments=cls.arguments,include_hour_flux=True)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.directory)
        cls.fixture.tearDown()

    def _load(self):
        return _m4_test_td_native_weather_v10_review_load_native_weather_v10_review(self.directory/"index.json",expected_sha256=_m4_test_td_native_weather_v10_review_file_sha256(self.directory/"index.json"),
            expected_identity=self.result["identity_sha256"],input_index=self.root/"index.json",acceptance_arguments=self.arguments,include_hour_flux=True)

    def test_complete_binary_frames_and_raw_cold(self):
        loaded = self._load()
        self.assertEqual(loaded["frames"],25)
        self.assertEqual(loaded["directions"],["eastward","westward"])
        for direction in loaded["directions"]:
            frames = {page["frame_index"] for page in loaded["pages"] if page["kind"]=="native_states" and page["scenario"]==direction}
            self.assertEqual(frames,set(range(25)))
        self.assertFalse(loaded["flags"]["water_interpolation"])

    def test_raw_tamper_missing_extra_rejected(self):
        target = self.directory/self.result["pages"][1]["file"]
        raw = target.read_bytes()
        target.write_bytes(bytes([raw[0]^1])+raw[1:])
        try:
            with self.assertRaises(ValueError):
                self._load()
        finally:
            target.write_bytes(raw)
        target.unlink()
        try:
            with self.assertRaises(ValueError):
                self._load()
        finally:
            target.write_bytes(raw)
        extra = self.directory/"extra.bin"
        extra.write_bytes(b"extra")
        try:
            with self.assertRaises(ValueError):
                self._load()
        finally:
            extra.unlink()

    def test_rehashed_path_descriptor_rejected(self):
        path = self.directory/"index.json"
        raw = path.read_bytes()
        result = _m4_test_td_native_weather_v10_review_copy.deepcopy(self.result)
        result["pages"][0]["file"] = "../escaped.json"
        result.pop("identity_sha256")
        result["identity_sha256"] = _m4_test_td_native_weather_v10_review_hash(result)
        path.write_text(_m4_test_td_native_weather_v10_review_json.dumps(result),encoding="utf8")
        try:
            with self.assertRaises(ValueError):
                _m4_test_td_native_weather_v10_review_load_native_weather_v10_review(path,expected_sha256=_m4_test_td_native_weather_v10_review_file_sha256(path),expected_identity=result["identity_sha256"],
                    input_index=self.root/"index.json",acceptance_arguments=self.arguments,include_hour_flux=True)
        finally:
            path.write_bytes(raw)

    def test_budget_and_postexport_failure_no_publication(self):
        directory = self.root.parent/(self.root.name+"-rejected")
        with self.assertRaises(ValueError):
            _m4_test_td_native_weather_v10_review_export_native_weather_v10_review(self.root/"index.json",directory,acceptance_arguments=self.arguments,output_budget_bytes=1)
        self.assertFalse(directory.exists())

    def test_leaf_interval_failure_rejects_without_publication(self):
        from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
        directory = self.root.parent/(self.root.name+"-leaf-rejected")
        def inconsistent_leaf_account(**record):
            result = load_storage(**record)
            result = dict(result,arrays={name:values.copy() for name,values in result["arrays"].items()})
            result["arrays"]["rain_volume_m3"][0,0] += .01
            return result
        with _m4_test_td_native_weather_v10_review_patch("terrain_pipeline.td_native_weather_v10_review.load_storage",side_effect=inconsistent_leaf_account):
            with self.assertRaisesRegex(ValueError,"exclusive leaf interval budget failed"):
                _m4_test_td_native_weather_v10_review_export_native_weather_v10_review(self.root/"index.json",directory,acceptance_arguments=self.arguments)
        self.assertFalse(directory.exists())
        with _m4_test_td_native_weather_v10_review_patch("terrain_pipeline.td_native_weather_v10_review._verify",side_effect=ValueError("postexport failure")):
            with self.assertRaises(ValueError):
                _m4_test_td_native_weather_v10_review_export_native_weather_v10_review(self.root/"index.json",directory,acceptance_arguments=self.arguments)
        self.assertFalse(directory.exists())

# --- tests/test_audit_td_native_weather_v10.py:9 ---
class TestAuditTdNativeWeatherProfile10IndependentV10AccountTests(_m4_test_audit_td_native_weather_v10_unittest.TestCase):
    def setUp(self):
        self.arrays = dict(height_m=_m4_test_audit_td_native_weather_v10_np.zeros((1, 2)), valid_mask=_m4_test_audit_td_native_weather_v10_np.ones((1, 2), bool),
                           face_cells=_m4_test_audit_td_native_weather_v10_np.array([[0, 1]], _m4_test_audit_td_native_weather_v10_np.int64), boundary_cells=_m4_test_audit_td_native_weather_v10_np.empty(0, _m4_test_audit_td_native_weather_v10_np.int64),
                           receiver=_m4_test_audit_td_native_weather_v10_np.array([1, -1], _m4_test_audit_td_native_weather_v10_np.int64), depth_m=_m4_test_audit_td_native_weather_v10_np.array([[0., 0.], [0., 0.]]),
                           soil_mm=_m4_test_audit_td_native_weather_v10_np.array([[30., 30.], [31., 32.]]), fast_mm=_m4_test_audit_td_native_weather_v10_np.zeros((2, 2)), slow_mm=_m4_test_audit_td_native_weather_v10_np.zeros((2, 2)),
                           rain_mm_h=_m4_test_audit_td_native_weather_v10_np.array([[1., 2.]]), face_forward_m3=_m4_test_audit_td_native_weather_v10_np.zeros(1), face_reverse_m3=_m4_test_audit_td_native_weather_v10_np.zeros(1),
                           active_forward_s=_m4_test_audit_td_native_weather_v10_np.zeros(1), active_reverse_s=_m4_test_audit_td_native_weather_v10_np.zeros(1), routed_volume_m3=_m4_test_audit_td_native_weather_v10_np.zeros(2),
                           wet_duration_s=_m4_test_audit_td_native_weather_v10_np.zeros(2))
        self.arrays.update({name: _m4_test_audit_td_native_weather_v10_np.zeros((1, 2)) for name in ("rain_volume_m3", "rain_infiltration_m3",
            "surface_infiltration_m3", "rain_excess_m3", "soil_et_m3", "surface_et_m3", "local_release_m3",
            "percolation_m3", "internal_net_m3", "boundary_outflow_m3", "storage_change_m3",
            "balance_residual_m3", "infiltration_capacity_m3")})
        for name in ("rain_volume_m3", "rain_infiltration_m3", "storage_change_m3"):
            self.arrays[name] = _m4_test_audit_td_native_weather_v10_np.array([[.001, .002]])
        self.arrays["infiltration_capacity_m3"][:] = .015

    def audit(self, arrays=None):
        return _m4_test_audit_td_native_weather_v10_audit_accounts(self.arrays if arrays is None else arrays, 1., _m4_test_audit_td_native_weather_v10_np.array([[1., 2.]]))

    def test_explicit_compartments_accept(self):
        self.assertTrue(self.audit()["budget_passed"])

    def test_total_conserved_wrong_rain_allocation_rejected(self):
        changed = _m4_test_audit_td_native_weather_v10_copy.deepcopy(self.arrays)
        changed["rain_excess_m3"] = changed["rain_infiltration_m3"].copy()
        changed["rain_infiltration_m3"][:] = 0.
        with self.assertRaisesRegex(ValueError, "soil water"):
            self.audit(changed)

    def test_rain_cell_permutation_rejected(self):
        changed = _m4_test_audit_td_native_weather_v10_copy.deepcopy(self.arrays)
        changed["rain_mm_h"] = changed["rain_mm_h"][:, ::-1]
        with self.assertRaisesRegex(ValueError, "rainfall slice"):
            self.audit(changed)

    def test_capacity_forgery_rejected(self):
        changed = _m4_test_audit_td_native_weather_v10_copy.deepcopy(self.arrays)
        changed["infiltration_capacity_m3"][:] = 1.
        with self.assertRaisesRegex(ValueError, "capacity"):
            self.audit(changed)

    def test_export_off_boundary_rejected(self):
        changed = _m4_test_audit_td_native_weather_v10_copy.deepcopy(self.arrays)
        changed["boundary_outflow_m3"][0, 0] = .001
        changed["depth_m"][0, 0] = .001
        changed["storage_change_m3"][0, 0] -= .001
        with self.assertRaisesRegex(ValueError, "undeclared export"):
            self.audit(changed)
