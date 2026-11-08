import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.surface_hydraulics import prepare_surface_geometry
from terrain_pipeline.td_entry_pulse_incremental import PulseLock, read_snapshot, run_fine_cold, snapshot_binding
from terrain_pipeline.td_entry_pulse_propagation import ORDINARY_Q_M3_S, build_dry_drain_geometry, build_pulse_forcing
from terrain_pipeline.td_entry_shallow_water import finish, run_case
from tools.audit_td_entry_pulse_incremental import check_snapshot_series
from tools.prepare_td_entry_shallow_water import save

ROOT = Path(__file__).resolve().parents[1]


def tiny_scene():
    bed = np.zeros((3, 8), np.float64)
    mask = np.zeros(bed.shape, bool)
    mask[1, 0] = True
    carrier = finish(dict(derived_bed_m=bed, forcing_mask=mask, overlay_mask=mask.copy(),
                          wet_protected_mask=np.zeros_like(mask)),
                     dict(injection_node_id='cell:61625', ordinary_q_m3_s=ORDINARY_Q_M3_S))
    geometry = prepare_surface_geometry(bed, spacing_m=.175, origin_m_xz=[0., 0.],
                                        source_identity=carrier['identity_sha256'])
    geometry['arrays']['boundary_kind'][3:6] = 2
    geometry['metadata']['bed_identity_sha256'] = carrier['identity_sha256']
    geometry = build_dry_drain_geometry(carrier, finish(geometry['arrays'], geometry['metadata']))
    forcing = build_pulse_forcing(carrier, geometry, duration_s=.04, pulse_s=.02, interval_s=.02)
    return carrier, geometry, forcing


class IncrementalPulseTests(unittest.TestCase):
    def test_cold_execution_exact_old_arrays_and_durable_real_state(self):
        carrier, geometry, forcing = tiny_scene()
        old = run_case(carrier, geometry, forcing, case_index=0, max_dt_s=.005, work_limit=1000000)
        commits = []
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as directory:
            def committed(snapshot_pin, progress):
                self.assertTrue(Path(snapshot_pin['path']).is_file())
                commits.append(dict(snapshot=snapshot_pin, **progress))

            new = run_fine_cold(carrier, geometry, forcing, output=Path(directory)/'snapshots',
                                code_sha256={}, on_commit=committed, work_limit=1000000)
            for old_bundle, new_bundle in zip(old, new):
                self.assertEqual(set(old_bundle['arrays']), set(new_bundle['arrays']))
                for key in old_bundle['arrays']:
                    np.testing.assert_array_equal(old_bundle['arrays'][key], new_bundle['arrays'][key], err_msg=key)
            self.assertEqual(old[0]['metadata']['substeps'], new[0]['metadata']['substeps'])
            self.assertEqual(len(commits), 2)
            binding = snapshot_binding(carrier, geometry, forcing, .005, {})
            first = read_snapshot(commits[0]['snapshot'], binding)
            self.assertEqual(first['metadata']['time_s'], .02)
            self.assertTrue(np.any(first['arrays']['momentum_m2_s'] != 0))
            self.assertFalse(first['metadata']['snapshot_resumable'])
            work = check_snapshot_series(commits, *new, binding, geometry)
            self.assertEqual(work, new[0]['metadata']['face_evaluations']*3//2)
            np.testing.assert_array_equal(new[2]['arrays']['forcing_m3_s'][1], np.zeros(24))

    def test_corrupted_identity_time_momentum_and_repeat_start_rejected(self):
        carrier, geometry, forcing = tiny_scene()
        commits = []
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as directory:
            output = Path(directory)/'snapshots'
            run_fine_cold(carrier, geometry, forcing, output=output, code_sha256={},
                          on_commit=lambda snapshot_pin, progress: commits.append(dict(snapshot=snapshot_pin, **progress)),
                          work_limit=1000000)
            binding = snapshot_binding(carrier, geometry, forcing, .005, {})
            valid = read_snapshot(commits[0]['snapshot'], binding)
            wrong_binding = dict(binding, forcing_identity='wrong-forcing')
            with self.assertRaisesRegex(ValueError, 'identity'):
                read_snapshot(commits[0]['snapshot'], wrong_binding)
            bad_pin = dict(commits[0]['snapshot'], sha256='0'*64)
            with self.assertRaisesRegex(ValueError, 'hash'):
                read_snapshot(bad_pin, binding)
            for kind in ('time', 'momentum'):
                arrays = {key: value.copy() for key, value in valid['arrays'].items()}
                meta = copy.deepcopy(valid['metadata'])
                if kind == 'time':
                    meta['time_s'] += .01
                else:
                    arrays['momentum_m2_s'][0, 0] += 1.
                changed_pin = save(Path(directory)/(kind+'.npz'), finish(arrays, meta))
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'time|continuity'):
                    read_snapshot(changed_pin, binding)
            with self.assertRaisesRegex(ValueError, 'no_resume'):
                run_fine_cold(carrier, geometry, forcing, output=output, code_sha256={}, on_commit=lambda *values: None)
            lock = Path(directory)/'runner.lock'
            with PulseLock(lock, 'fixture'):
                with self.assertRaises(FileExistsError):
                    with PulseLock(lock, 'duplicate'):
                        self.fail('duplicate PID lock admitted')
            self.assertFalse(lock.exists())


if __name__ == '__main__':
    unittest.main()
