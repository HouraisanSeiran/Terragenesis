"""Finite, frozen-parent checks for current FV scheduler and explicit old replay."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[name] = '1'
import numpy as np
from tools import run_natural_fv_growth_v4 as current
from tools import natural_fv_growth_scheduler as scheduler
from tools import natural_fv_growth_state_io as codec
from tools import replay_natural_fv_growth_legacy as legacy
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import MorphodynamicStepTooLarge

ROOT = Path(__file__).resolve().parents[1]


def initial():
    bed = np.full((3, 3), -.5)
    types = np.zeros_like(bed, dtype=np.int64)
    types[0] = 1
    data = dict(bed_m=bed, initial_bed_m=bed.copy(), source_floor_m=bed-.3,
        cell_type=types, local_world_xz_m=np.zeros((*bed.shape, 2)), fixed_boundary_mask=np.zeros_like(bed, bool),
        depth_m=np.ones_like(bed), momentum_m2_s=np.tile([.05,.02], (9,1)),
        suspended_solid_m3=np.zeros_like(bed), source_schedule=np.array([[0.,0.,10.,.02,20.,100.]]))
    meta = dict(physical_time_s=0., source_cursor_s=0., cumulative_injected_solid_m3=0.,
                cumulative_exported_solid_m3=0., source_total_solid_m3=.02, source_identities=[])
    return data, meta


def arguments(runner, parent, output, duration='.125'):
    return runner.parser().parse_args(['--resume', str(parent), '--output', str(output),
        '--duration-s', duration, '--interval-s', '.0625', '--chunk-duration-s', '.0625',
        '--wave-height', '.3', '--river-q', '1'])


def arrays_equal(test, expected, actual):
    test.assertEqual(set(expected), set(actual))
    for key in expected:
        test.assertEqual(expected[key].dtype, actual[key].dtype, key)
        test.assertEqual(expected[key].shape, actual[key].shape, key)
        test.assertEqual(expected[key].tobytes(), actual[key].tobytes(), key)


class CurrentFVRunnerMigrationTests(unittest.TestCase):
    def test_current_default_does_not_import_legacy_or_clone_code(self):
        command = "import sys; from tools import run_natural_fv_growth_v4; assert 'tools.run_natural_fv_growth_v3' not in sys.modules; assert 'tools.replay_natural_fv_growth_legacy' not in sys.modules"
        result = subprocess.run([sys.executable, '-B', '-c', command], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('terrain_pipeline/surface_rivers/metric_fv_growth_coupling.py',
                     'terrain_pipeline/surface_rivers/metric_fv_growth_coupling_v3.py',
                     'tools/run_natural_fv_growth_v2.py', 'tools/run_natural_fv_growth_v3.py',
                     'tools/run_natural_fv_growth_interval_v3.py'):
            self.assertFalse((ROOT/name).exists(), name)
        for name in ('run_natural_fv_growth_v4.py', 'natural_fv_growth_scheduler.py', 'natural_fv_growth_interval.py'):
            text = (ROOT/'tools'/name).read_text(encoding='utf-8')
            self.assertNotIn('FunctionType', text)
            self.assertNotIn('.interval-v3-protocol', text)

    def test_same_parent_scheduler_result_packets_and_ledgers_are_exact(self):
        with tempfile.TemporaryDirectory() as folder, legacy.LegacyContext() as ctx:
            folder = Path(folder)
            old = ctx.module('tools.run_natural_fv_growth_v4')
            data, meta = initial()
            parent = folder/'old.npz'
            old.save_checkpoint(parent, data, meta)
            old_sha = legacy.sha256(parent)
            args = arguments(old, parent, folder/'before', '.25')
            args.chunk_duration_s = .125
            template = folder/'parameters.json'
            template.write_text(json.dumps({key:str(value) if isinstance(value,Path) else value for key,value in vars(args).items()}), encoding='utf-8')
            migrated = folder/'current.npz'
            codec.migrate_legacy_checkpoint(parent, old_sha, migrated, parameters=template, parameters_sha256=legacy.sha256(template))
            before = old.run(args)
            new_args = arguments(current, migrated, folder/'after', '.25')
            new_args.chunk_duration_s = .125
            after = current.run(new_args)
            expected = codec.read_arrays(folder/'before/result.npz')
            actual = codec.read_arrays(folder/'after/result.npz')
            arrays_equal(self, expected, actual)
            one = json.loads((folder/'before/interval-ledgers.json').read_text())
            two = json.loads((folder/'after/interval-ledgers.json').read_text())
            self.assertEqual(one,two)
            old_files = sorted(path.name for path in (folder/'before/packets').glob('*.npz'))
            new_files = sorted(path.name for path in (folder/'after/packets').glob('*.npz'))
            self.assertEqual(old_files,new_files)
            for name in old_files:
                arrays_equal(self, codec.read_arrays(folder/'before/packets'/name), codec.read_arrays(folder/'after/packets'/name))
            for key in ('physical_time_s','source_cursor_s','cumulative_injected_solid_m3','cumulative_exported_solid_m3'):
                self.assertEqual(before['end'][key],after['end'][key])
            for key in ('combined_residual_solid_m3','water_volume_residual_m3','remaining_finite_source_solid_m3'):
                self.assertEqual(before[key],after[key])
            self.assertGreater(actual['suspended_solid_m3'][-1].sum(),0.)
            self.assertEqual(legacy.sha256(parent), old_sha)

    def test_resume_preserves_state_and_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            data, meta = initial()
            codec.save_checkpoint(folder/'initial.npz',data,meta)
            first = current.run(arguments(current,folder/'initial.npz',folder/'one','.0625'))
            before, bm = codec.load_checkpoint(first['checkpoint'])
            second = current.run(arguments(current,Path(first['checkpoint']),folder/'two','.0625'))
            state, final = codec.load_checkpoint(second['checkpoint'])
            result=codec.read_arrays(folder/'two/result.npz')
            for key in codec.STATE:
                self.assertEqual(result[key][0].tobytes(),before[key].tobytes())
            self.assertEqual(final['physical_time_s'],.125)
            self.assertEqual(final['source_cursor_s'],.125)
            bad=arguments(current,Path(second['checkpoint']),folder/'changed','.0625')
            bad.wave_height=.4
            with self.assertRaisesRegex(ValueError,'parameters changed'):
                current.run(bad)
            self.assertFalse(bad.output.exists())

    def test_rejected_trial_does_not_consume_parent_and_retries_from_same_state(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            data,meta=initial()
            parent=folder/'initial.npz'
            codec.save_checkpoint(parent,data,meta)
            digest=legacy.sha256(parent)
            args=arguments(current,parent,folder/'retry','.125')
            args.interval_s=.125
            args.chunk_duration_s=.125
            seen=[]
            def executor(trial):
                state,record=codec.load_checkpoint(trial.resume)
                seen.append((record['physical_time_s'],record['source_cursor_s'],record['cumulative_injected_solid_m3'],state['bed_m'].tobytes()))
                if len(seen)==1:
                    state['bed_m'][:]=999.
                    raise MorphodynamicStepTooLarge('injected finite trial rejection')
                return scheduler.interval.run(trial)
            report=scheduler.run(args,execute_interval=executor)
            self.assertEqual(seen[0],seen[1])
            self.assertEqual(report['attempts'][0]['status'],'rejected')
            self.assertEqual(report['end']['source_cursor_s'],.125)
            self.assertEqual(legacy.sha256(parent),digest)
            self.assertFalse(list(args.output.glob('.trial-*')))
            checkpoints = list(args.output.glob('checkpoint-*.npz'))
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(report['attempts'][-1]['interval_count'], 2)

    def test_actual_bed_jump_rejection_at_minimum_keeps_parent_and_no_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            data,meta=initial()
            parent=folder/'initial.npz'
            codec.save_checkpoint(parent,data,meta)
            digest=legacy.sha256(parent)
            args=arguments(current,parent,folder/'real-reject','.0625')
            args.max_bed_change=1.e-12
            with self.assertRaises(MorphodynamicStepTooLarge):
                scheduler.run(args)
            self.assertEqual(legacy.sha256(parent),digest)
            self.assertFalse(list(args.output.glob('checkpoint-*.npz')))
            self.assertFalse(list(args.output.glob('.trial-*')))
            self.assertFalse((args.output/'summary.json').exists())
            attempts=json.loads((args.output/'attempts.json').read_text())
            self.assertEqual(attempts[0]['status'],'rejected')
            self.assertEqual(attempts[0]['source_cursor_unchanged_s'],0.)

    def test_checkpoint_source_contract_and_external_pin_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.npz'
            data,meta=initial()
            codec.save_checkpoint(path,data,meta)
            with self.assertRaisesRegex(ValueError,'external SHA'):
                codec.load_checkpoint(path,expected_sha256='0'*64)
            raw=codec.read_arrays(path)
            record=json.loads(str(raw.pop('metadata_json')))
            record['bedload_transport_contract']['counterflow']='allowed'
            np.savez_compressed(path,**raw,metadata_json=json.dumps(record))
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                codec.load_checkpoint(path)

    def test_multichunk_global_packet_numbers_and_forcing_cursor(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            data, meta = initial()
            parent = folder/'initial.npz'
            codec.save_checkpoint(parent, data, meta)
            args = arguments(current, parent, folder/'multi', '.375')
            args.chunk_duration_s = .125
            args.source_time_scale = 3.
            report = current.run(args)
            state, final = codec.load_checkpoint(report['checkpoint'])
            self.assertEqual(final['physical_time_s'], .375)
            self.assertEqual(final['source_cursor_s'], 1.125)
            self.assertEqual([a['interval_count'] for a in report['attempts']], [2,2,2])
            ledgers = json.loads((args.output/'interval-ledgers.json').read_text())
            self.assertEqual([row['global_interval'] for row in ledgers], list(range(6)))
            self.assertEqual(sorted(p.name for p in (args.output/'packets').glob('*-carrier.npz')),
                             [f'{i:07d}-carrier.npz' for i in range(6)])
            off = arguments(current, Path(report['checkpoint']), folder/'off', '.125')
            off.source_time_scale = 3.
            off.supply_off = True
            # A physical switch is explicit: start a separately declared scenario state.
            off_state, off_meta = codec.load_checkpoint(report['checkpoint'])
            off_meta['run_parameters'].update(supply_off=True)
            codec.save_checkpoint(folder/'off-parent.npz', off_state, off_meta)
            off.resume = folder/'off-parent.npz'
            stopped = current.run(off)
            self.assertEqual(stopped['end']['source_cursor_s'], final['source_cursor_s'])
            self.assertEqual(stopped['end']['cumulative_injected_solid_m3'], final['cumulative_injected_solid_m3'])

    def test_bad_trial_ledger_count_is_not_published_as_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            data,meta=initial()
            parent=folder/'initial.npz'
            codec.save_checkpoint(parent,data,meta)
            args=arguments(current,parent,folder/'bad','.125')
            args.chunk_duration_s=.125
            digest=legacy.sha256(parent)
            def executor(trial):
                report=scheduler.interval.run(trial)
                path=trial.output/'interval-ledgers.json'
                rows=json.loads(path.read_text())
                path.write_text(json.dumps(rows[:-1]),encoding='utf-8')
                return report
            with self.assertRaisesRegex(ValueError,'ledger count'):
                scheduler.run(args,execute_interval=executor)
            self.assertFalse(list(args.output.glob('checkpoint-*.npz')))
            self.assertFalse((args.output/'summary.json').exists())
            self.assertEqual(legacy.sha256(parent),digest)

    def test_validly_rewritten_trial_cannot_change_source_floor_or_export_total(self):
        for mutation in ('floor','export'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                folder=Path(folder)
                data,meta=initial()
                parent=folder/'initial.npz'
                codec.save_checkpoint(parent,data,meta)
                args=arguments(current,parent,folder/'bad','.0625')
                def executor(trial):
                    report=scheduler.interval.run(trial)
                    state,record=codec.load_checkpoint(report['checkpoint'])
                    if mutation=='floor':
                        state['source_floor_m']-=.01
                    else:
                        record['cumulative_exported_solid_m3']+=.01
                    codec.save_checkpoint(report['checkpoint'],state,record)
                    report['checkpoint_sha256']=codec.file_sha256(report['checkpoint'])
                    return report
                with self.assertRaisesRegex(ValueError,'immutable|exported'):
                    scheduler.run(args,execute_interval=executor)
                self.assertFalse(list(args.output.glob('checkpoint-*.npz')))
                self.assertFalse((args.output/'summary.json').exists())

    def test_wall_after_commit_leaves_loadable_checkpoint_without_success_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            data,meta=initial()
            parent=folder/'initial.npz'
            codec.save_checkpoint(parent,data,meta)
            args=arguments(current,parent,folder/'wall','.125')
            args.max_wall_s=30.
            clock=iter([0.,100.])
            def elapsed():
                return next(clock,100.)
            # Patch only the scheduler clock, not the interval's SurfaceBudget clock.
            class Clock:
                @staticmethod
                def monotonic():
                    return elapsed()
            with mock.patch.object(scheduler,'time',Clock):
                with self.assertRaisesRegex(RuntimeError,'last committed'):
                    scheduler.run(args)
            checkpoints=sorted(args.output.glob('checkpoint-*.npz'))
            self.assertTrue(checkpoints)
            _,final=codec.load_checkpoint(checkpoints[-1])
            self.assertGreater(final['physical_time_s'],0.)
            self.assertFalse((args.output/'summary.json').exists())

    def test_real_parent_cold_migration_keeps_arrays_and_original_hashes(self):
        _,manifest,_=legacy.verify_archive()
        with tempfile.TemporaryDirectory() as folder:
            for fixture in manifest['fixtures']:
                parent=ROOT/fixture['checkpoint_path']
                template=legacy.ARCHIVE/fixture['parameter_template_archive_path']
                with self.subTest(profile=fixture['profile']):
                    data,old=legacy.read_legacy_checkpoint(parent,fixture['checkpoint_sha256'])
                    target=Path(folder)/(fixture['profile']+'.npz')
                    if fixture['profile']!='v4':
                        with self.assertRaisesRegex(ValueError,'physical upgrade'):
                            codec.migrate_legacy_checkpoint(parent,fixture['checkpoint_sha256'],target,parameters=template,parameters_sha256=fixture['parameter_template_sha256'])
                    codec.migrate_legacy_checkpoint(parent,fixture['checkpoint_sha256'],target,parameters=template,
                        parameters_sha256=fixture['parameter_template_sha256'],upgrade_physics=fixture['profile']!='v4')
                    after,new=codec.load_checkpoint(target)
                    arrays_equal(self,data,after)
                    for key in ('physical_time_s','source_cursor_s','cumulative_injected_solid_m3','cumulative_exported_solid_m3','source_total_solid_m3'):
                        self.assertEqual(old[key],new[key])
                    self.assertEqual(new['legacy_implementation_hashes'],old['implementation_hashes'])
                    self.assertEqual(legacy.sha256(parent),fixture['checkpoint_sha256'])


if __name__=='__main__':
    unittest.main()
