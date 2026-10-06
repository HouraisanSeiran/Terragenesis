import copy
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, save_bundle, file_sha256
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_storage_v10_io import STATES, ERRORS, LEDGERS, FLUX, PROFILE
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS, PHYSICS_SEMANTICS
from tools.audit_td_v10_temporal_refinement import audit_sequence, compare, check_resource
from tools.audit_td_candidate_coupling import read_record


class IndependentRefinementTests(unittest.TestCase):
    def sequence(self, directory, step=.625):
        directory = Path(directory)
        topology = dict(height_m=np.array([[0., 1.]]), valid_mask=np.ones((1, 2), bool),
                        protected_mask=np.zeros((1, 2), bool), face_cells=np.array([[0, 1]], np.int64),
                        receiver=np.array([-1, 0], np.int64), boundary_cells=np.empty(0, np.int64))
        geometry = dict(spacing_m=30., origin_m_xz=[0., 0.])
        rain = np.ones((24, 1, 2), np.float64)
        pages = []
        for hour in range(24):
            arrays = {name:topology[name].copy() for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells")}
            arrays["boundary_width_m"] = np.empty(0, np.float64)
            arrays.update({name:np.zeros((2, 2), np.float64) for name in STATES})
            arrays["soil_mm"][:] = [[30. + hour] * 2, [31. + hour] * 2]
            arrays.update({name:np.zeros((1, 2), np.float64) for name in LEDGERS})
            arrays["rain_mm_h"] = np.ones((1, 2), np.float64)
            for name in ("rain_volume_m3", "rain_infiltration_m3", "storage_change_m3"):
                arrays[name][:] = .9
            arrays["infiltration_capacity_m3"][:] = 13.5
            arrays.update({name:np.zeros(1 if name.startswith(("face_", "active_")) else 2, np.float64) for name in FLUX})
            metadata = dict(schema="td-v10-hour-page-v1", profile=PROFILE, cells=2, faces=1,
                            substep_s=step, substeps=int(3600 / step), forcing_hour_offset=hour,
                            dt_s=3600., start_s=hour * 3600., end_s=(hour + 1) * 3600.,
                            spacing_m=30., origin_m_xz=[0., 0.], hierarchy_identity="a" * 64,
                            forcing_identity="b" * 64, parameters=dict(PHYSICS, substep_s=step),
                            runoff_parameters=asdict(RunoffParameters()), positivity_cfl=step * .6 / 30.,
                            physics=PHYSICS_SEMANTICS,
                            permanent_lake_impermeability="not modelled; requires independent material mask",
                            activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration",
                            hydraulic_ready=False, transient_converged=False, publishable=False)
            page = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
            cp_arrays = {name:arrays[name][-1].copy() for name in STATES}
            cp_arrays.update({name:np.zeros(2) for name in ERRORS})
            cp_arrays.update({"cumulative_" + name:arrays[name].copy() for name in FLUX})
            cp_meta = dict(metadata, schema="td-v10-hour-checkpoint-v1", last_page_identity=page["identity_sha256"])
            cp = dict(arrays=cp_arrays, metadata=cp_meta, identity_sha256=identity(cp_arrays, cp_meta))
            records = dict(hour=hour, forcing_identity="b" * 64, chunk_work_face_steps=int(3600 / step))
            for role, saved in (("storage", page), ("checkpoint", cp)):
                path = directory / f"hour-{hour:02d}" / (role + ".npz")
                save_bundle(path, saved, validator=lambda value:True)
                records[role] = dict(path=str(path.resolve()), expected_sha256=file_sha256(path), expected_identity=saved["identity_sha256"])
            pages.append(records)
        return pages, dict(topology=topology, geometry=geometry, rain=rain, forcing_identity="b" * 64,
                           step=step, run_root=directory, hierarchy_identity="a" * 64)

    def test_complete_fine_sequence_schema_cold_accounts_and_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            pages, arguments = self.sequence(directory)
            result = audit_sequence(pages, **arguments)
            self.assertEqual(result["frames"].shape, (25, 2))
            self.assertTrue(result["budget"]["whole_period_passed"])
            self.assertAlmostEqual(result["budget"]["total_rain_m3"], 43.2)
            self.assertTrue(compare(result, result)["gate_passed"])

    def test_partial_and_false_cumulative_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            pages, arguments = self.sequence(directory)
            with self.assertRaisesRegex(ValueError, "complete 24-hour"):
                audit_sequence(pages[:-1], **arguments)
            arrays, metadata = read_record(pages[8]["checkpoint"])
            arrays["cumulative_routed_volume_m3"][0] = 1.
            saved = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
            path = Path(directory) / "tampered-checkpoint.npz"
            save_bundle(path, saved, validator=lambda value:True)
            pages[8]["checkpoint"] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=saved["identity_sha256"])
            with self.assertRaises(AssertionError):
                audit_sequence(pages, **arguments)

    def test_physics_changed_and_wrong_initial_state_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            pages, arguments = self.sequence(directory)
            arrays, metadata = read_record(pages[0]["storage"])
            metadata["parameters"]["face_conductance_m_s"] = .7
            saved = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
            path = Path(directory) / "tampered-storage.npz"
            save_bundle(path, saved, validator=lambda value:True)
            pages[0]["storage"] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=saved["identity_sha256"])
            with self.assertRaisesRegex(ValueError, "physics"):
                audit_sequence(pages, **arguments)

    def test_unchanged_strict_depth_and_receiver_gates(self):
        first = dict(frames=np.zeros((25, 2)), cumulative=dict(routed_volume_m3=np.ones(2)))
        second = copy.deepcopy(first)
        second["frames"][5, 1] = .0013
        self.assertFalse(compare(first, second)["gate_passed"])
        second["frames"][:] = 0.
        second["cumulative"]["routed_volume_m3"][0] = 1.1
        self.assertFalse(compare(first, second)["gate_passed"])

    def test_missing_private_resource_and_exceeded_budget_rejected(self):
        resource = dict(complete=True, index_sha256="a" * 64, scope="new48", monitor_error=None,
                        peak_rss_bytes=100, peak_private_bytes=200, sample_count=3)
        check_resource(resource, "a" * 64, "new48")
        for name, value in (("peak_private_bytes", 0), ("peak_rss_bytes", 1073741825), ("complete", False)):
            changed = dict(resource, **{name:value})
            with self.assertRaisesRegex(ValueError, "resource"):
                check_resource(changed, "a" * 64, "new48")

    def test_fresh_audit_import_without_solver(self):
        subprocess.run([sys.executable, "-c", "import tools.audit_td_v10_temporal_refinement; import sys; assert 'numba' not in sys.modules; assert 'terrain_pipeline.td_basin_storage_v10' not in sys.modules"], check=True)


if __name__ == "__main__":
    unittest.main()
