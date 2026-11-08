"""Explicit archived FV replay and source/parameter rejection checks."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
from tools import replay_natural_fv_growth_legacy as legacy
from tools import natural_fv_growth_state_io as codec
from tests.test_fv_current_runner_migration import initial, arguments


class FVLegacyReplayTests(unittest.TestCase):
    def test_explicit_original_v4_worker_advances_complete_state_without_parent_pollution(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            with legacy.LegacyContext() as context:
                old=context.module('tools.run_natural_fv_growth_v4')
                data,meta=initial()
                parent=folder/'original.npz'
                old.save_checkpoint(parent,data,meta)
                args=arguments(old,parent,folder/'replay','.0625')
                payload={key:str(value) if isinstance(value,Path) else value for key,value in vars(args).items()}
                template=folder/'parameters.json'
                template.write_text(json.dumps(payload),encoding='utf-8')
            before_path=list(sys.path)
            before_env=dict(os.environ)
            digest=legacy.sha256(parent)
            report=legacy.replay_legacy(resume=parent,resume_sha256=digest,parameters=template,
                parameters_sha256=legacy.sha256(template),output=folder/'replay',legacy_runner='v4',duration_s=.0625,timeout_s=90)
            self.assertEqual(report['end']['physical_time_s'],.0625)
            self.assertEqual(report['end']['source_cursor_s'],.0625)
            self.assertGreater(report['end']['cumulative_injected_solid_m3'],0.)
            provenance=json.loads((folder/'replay/legacy-replay.json').read_text())
            self.assertTrue(provenance['not_current_default'])
            self.assertEqual(provenance['manifest_sha256'],legacy.MANIFEST_SHA256)
            self.assertEqual(legacy.sha256(parent),digest)
            self.assertEqual(sys.path,before_path)
            self.assertEqual(dict(os.environ),before_env)

    def test_source_and_rewritten_manifest_are_both_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'archive'
            shutil.copytree(legacy.ARCHIVE,archive)
            path=archive/'sources/tools/run_natural_fv_growth_v4.py'
            path.write_bytes(path.read_bytes()+b'\n# changed\n')
            with self.assertRaisesRegex(ValueError,'source SHA256'):
                legacy.verify_archive(archive)
            manifest_path=archive/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            for record in manifest['source_files']:
                if record['original_path']=='tools/run_natural_fv_growth_v4.py':
                    record['sha256']=legacy.sha256(path)
                    record['bytes']=path.stat().st_size
            manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'trusted manifest'):
                legacy.verify_archive(archive)

    def test_frozen_checkpoint_signature_set_is_not_partially_accepted(self):
        with tempfile.TemporaryDirectory() as folder,legacy.LegacyContext() as context:
            folder=Path(folder)
            old=context.module('tools.run_natural_fv_growth_v4')
            data,meta=initial()
            parent=folder/'original.npz'
            old.save_checkpoint(parent,data,meta)
            raw=codec.read_arrays(parent)
            record=json.loads(str(raw.pop('metadata_json')))
            record['implementation_hashes'].pop(next(iter(record['implementation_hashes'])))
            np.savez_compressed(parent,**raw,metadata_json=json.dumps(record))
            with self.assertRaisesRegex(ValueError,'implementation'):
                legacy.read_legacy_checkpoint(parent,legacy.sha256(parent))

    def test_supplemental_diagnostic_is_explicit_and_full_v3_prefix_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            with legacy.LegacyContext() as context:
                old=context.module('tools.run_natural_fv_growth_v3')
                data,meta=initial()
                meta.update(schema='finite-FV-growth-checkpoint-v3',implementation_hashes=old.identities())
                parent=folder/'v3.npz'
                old.save_checkpoint(parent,data,meta)
                args=arguments(old,parent,folder/'original-v3','.0625')
                report=old.run(args)
            cp=Path(report['checkpoint'])
            summary=folder/'original-v3/summary.json'
            recovered=legacy.recover_legacy_prefix(folder/'original-v3',cp,summary,folder/'recovered',
                checkpoint_sha256=legacy.sha256(cp),parameters_sha256=legacy.sha256(summary))
            self.assertEqual(recovered['actual_duration_s'],.0625)
            before=codec.read_arrays(folder/'original-v3/result.npz')
            after=codec.read_arrays(folder/'recovered/result.npz')
            for key in codec.STATE:
                self.assertEqual(before[key].tobytes(),after[key].tobytes())
            result=legacy.replay_legacy_diagnostic(checkpoint=cp,checkpoint_sha256=legacy.sha256(cp),
                parameters=summary,parameters_sha256=legacy.sha256(summary),output=folder/'diagnose',
                interval_s=.0625,duration_s=.0625)
            self.assertTrue(result['not_current_diagnostic'])
            self.assertTrue((folder/'diagnose/replay.json').is_file())
            record=json.loads((folder/'diagnose/replay.json').read_text())
            self.assertEqual(record['checkpoint_cursor_s'],report['end']['source_cursor_s'])

    def test_supplement_manifest_and_source_joint_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'archive'
            shutil.copytree(legacy.ARCHIVE,archive)
            path=archive/'supplemental/tools/diagnose_fv_mpm_rejection.py'
            path.write_bytes(path.read_bytes()+b'\n# changed\n')
            with self.assertRaisesRegex(ValueError,'supplemental historical source'):
                legacy.verify_archive(archive)
            manifest=archive/'supplemental-manifest.json'
            record=json.loads(manifest.read_text())
            record['files'][0]['sha256']=legacy.sha256(path)
            manifest.write_text(json.dumps(record),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'supplemental trusted manifest'):
                legacy.verify_archive(archive)

    def test_context_load_success_and_failure_restore_search_and_environment(self):
        path=list(sys.path)
        env=dict(os.environ)
        before_meta=list(sys.meta_path)
        with legacy.LegacyContext() as context:
            context.module('tools.run_natural_fv_growth_v4')
            self.assertEqual(sys.path,path)
            self.assertEqual(dict(os.environ),env)
        self.assertEqual(sys.meta_path,before_meta)
        with legacy.LegacyContext() as context:
            namespace=context.namespace
            with self.assertRaises(ImportError):
                context.module('tools.not_in_archive')
        self.assertEqual(sys.path,path)
        self.assertEqual(dict(os.environ),env)
        self.assertEqual(sys.meta_path,before_meta)
        self.assertFalse(any(name==namespace or name.startswith(namespace+'.') for name in sys.modules))


if __name__=='__main__':
    unittest.main()
