"""Safety gates for the highland preparation tool.

Two rules here. First, no real page is a fixture: the 2049^2 pages under ``.scratch`` are
33 MB each, so every package below is built from a synthetic window and the door that
would read a page is exercised with a request that is refused *before* any array exists.
Second, the declared supports are asserted against the card that declared them -- origin,
shape, cell count, role and the ``holdout`` flag -- so a support cannot be widened, swapped
or quietly promoted to a hold-out by an edit to this table.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from tools import prepare_highland_sources as p

#: One synthetic page record. The tool binds the pinned page list to the loader records and
#: to the request pin recorded before *and* after the run, so a synthetic package has to
#: declare a page too: an empty list would satisfy the binding trivially, which is exactly
#: the hole the binding exists to close.
SYNTHETIC_PAGE = {'path': 'synthetic/td-page-0000.npz', 'sha256': '0' * 64}


def synthetic_source(resolved_cells, unresolved_cells=0):
    """A loader-shaped ``source`` block that carries the synthetic page binding."""
    return {
        'resolved_cells': int(resolved_cells),
        'unresolved_cells': int(unresolved_cells),
        'source_records': [synthetic_page_record()],
    }


def synthetic_page_record():
    return {'page_key': 'p00', 'path': SYNTHETIC_PAGE['path'],
            'sha256': SYNTHETIC_PAGE['sha256']}


def synthetic_window(window):
    """The same window, carrying the synthetic page binding the bundle metadata records.

    The tool binds three copies of the page list -- the pinned records, the loader's own
    records and the bundle metadata -- and each is required on its own, so a synthetic
    package has to populate all three. A missing copy is a refusal, never "nothing to
    compare, so equal".
    """
    return dict(window, source_records=[synthetic_page_record()])


class PreparationTests(unittest.TestCase):
    def test_empty_region_bundle_roundtrips(self):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        from tests.test_metric_highland_sources import flat_window
        bundle = h.build_highland_sources(flat_window())
        self.assertEqual(bundle['arrays']['region_ptr'].tolist(), [0])
        self.assertTrue(h.validate_highland_sources(bundle)['head_table_rederived'])

    def test_cold_manifest_claims_are_bound_to_bundle(self):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        from tests.test_metric_highland_sources import patch_window
        from types import SimpleNamespace
        w = patch_window(257, 257)
        bundle = h.build_highland_sources(synthetic_window(w))
        validation = p.validate_bundle(bundle)
        source = synthetic_source(66049)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            _, _, entry = p.declared_support('D')
            p.write_package(root, support_name='D', origin=(42173,42874), shape=(257,257),
                            entry=entry, request_path='synthetic', request_sha='0'*64,
                            records=[SYNTHETIC_PAGE], page_bytes=0, headers={}, window=w,
                            source=source, bundle=bundle, validation=validation, timing={},
                            request_sha_after='0'*64)
            self.assertTrue(p.read_package(root)[1]['head_table_rederived'])
            original = (root/'manifest.json').read_text(encoding='utf-8')
            attacks = [('counts','heads_certified',100000),
                       ('stage','perennial_flow_certified',True),
                       ('rule','logical_version','forged'),
                       ('identity','head_ids',['invented']),
                       ('support','role','holdout'),
                       ('validation','head_table_rederived',False)]
            for section,key,value in attacks:
                with self.subTest(section=section):
                    manifest=json.loads(original); manifest[section][key]=value
                    (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
                    with self.assertRaisesRegex(ValueError,'package'):
                        p.read_package(root)
            (root/'manifest.json').write_text(original,encoding='utf-8')

    def test_existing_output_refused_before_request_read(self):
        with tempfile.TemporaryDirectory() as d, patch.object(p, 'read_request') as read:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                p.run(d, support='D', source_request='missing', request_sha256='0'*64)
            read.assert_not_called()

    def test_duplicate_json_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'request.json'
            f.write_text('{"source_records":[],"source_records":[]}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                p.read_request(f, p.file_sha256(f))

    def test_nan_pattern(self):
        f = np.ones((3,3)); m = np.ones((3,3), bool)
        m[1,1] = False; f[1,1] = np.nan
        self.assertEqual(p.check_unresolved_pattern({'field':f,'resolved_mask':m})['unresolved_cells'],1)
        f[1,1] = 0
        with self.assertRaises(ValueError):
            p.check_unresolved_pattern({'field':f,'resolved_mask':m})

    def test_page_headers_keep_each_page(self):
        with tempfile.TemporaryDirectory() as d:
            records=[]
            for i in range(2):
                f=Path(d)/('%d.npz'%i)
                np.savez(f,elevation_native=np.ones((3+i,3+i)),metadata_json=np.array('{}'))
                records.append({'path':str(f),'sha256':p.file_sha256(f)})
            headers,_=p.inspect_page_headers(records)
            self.assertEqual(len(headers),2)
            self.assertEqual(headers[str(Path(d)/'0.npz')]['elevation_native']['shape'],[3,3])

    def test_object_page_refused_without_numpy_load(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'bad.npz'
            np.savez(f,elevation_native=np.array([[object()]],dtype=object),metadata_json=np.array('{}'))
            with patch('numpy.load') as load:
                with self.assertRaisesRegex(ValueError,'object'):
                    p.inspect_page_headers([{'path':str(f),'sha256':'0'*64}])
                load.assert_not_called()

    def test_write_failure_leaves_no_final_or_staging(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'result'
            def fail(work, **kw):
                work.mkdir(); (work/'partial').write_text('incomplete')
                raise RuntimeError('injected failure')
            with patch.object(p,'write_package',side_effect=fail):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    p.publish_package(target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_commit_race_preserves_external_target(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'result'
            def write(work,**kw):
                work.mkdir();return {},work/'arrays.npz'
            def cold(work):
                target.mkdir();(target/'owner').write_text('external')
            with patch.object(p,'write_package',side_effect=write),patch.object(p,'read_package',side_effect=cold):
                with self.assertRaisesRegex(ValueError,'appeared'):
                    p.publish_package(target)
            self.assertEqual((target/'owner').read_text(),'external')
            self.assertEqual(list(Path(d).iterdir()),[target])


def declared_window(name, terrain=None, **terrain_kwargs):
    """A synthetic window of the **declared** shape at the **declared** origin.

    Built from absolute world cells, so the same ground gives the same values whether it
    is read as E or as V -- which is what makes the binding assertions meaningful.
    """
    from tests.test_metric_highland_sources import valley_terrain, world_field, window

    origin, shape, entry = p.declared_support(name)
    height = (terrain or valley_terrain)(origin=origin, **terrain_kwargs)
    return window(world_field(origin, shape, height), origin=origin), entry


class DeclaredSupportTest(unittest.TestCase):
    """The declared support table is a declaration, and it is not editable by accident."""

    def test_card_supports_are_the_declared_ones(self):
        expected = {
            'D': ((42173, 42874), (257, 257), 'development', False),
            'H': ((42685, 42874), (257, 257), 'holdout', True),
            'E': ((42173, 42874), (317, 257), 'development_recheck', False),
            'V': ((42168, 42869), (327, 267), 'consistency_control', False),
        }
        self.assertEqual(sorted(p.DECLARED_SUPPORTS), sorted(expected))
        for name, (origin, shape, role, holdout) in expected.items():
            with self.subTest(support=name):
                got_origin, got_shape, entry = p.declared_support(name)
                self.assertEqual(got_origin, origin)
                self.assertEqual(got_shape, shape)
                self.assertEqual(entry['role'], role)
                self.assertIs(entry['holdout'], holdout)
                # The cell count is the card's, not re-derived from a render window.
                self.assertEqual(got_shape[0] * got_shape[1], shape[0] * shape[1])

    def test_only_h_is_a_holdout(self):
        holdouts = {name for name, entry in p.DECLARED_SUPPORTS.items()
                    if entry['holdout']}
        self.assertEqual(holdouts, {'H'})
        for name in ('D', 'E', 'V'):
            self.assertFalse(p.DECLARED_SUPPORTS[name]['holdout'])
            self.assertNotEqual(p.DECLARED_SUPPORTS[name]['role'], 'holdout')

    def test_E_is_D_extended_towards_high_z(self):
        d_origin, d_shape, _ = p.declared_support('D')
        e_origin, e_shape, _ = p.declared_support('E')
        self.assertEqual(e_origin, d_origin)
        self.assertEqual(e_shape[1], d_shape[1])          # same x span
        self.assertEqual(e_shape[0] - d_shape[0], 60)     # 60 cells towards high z

    def test_V_is_E_with_five_cell_margin_on_every_side(self):
        e_origin, e_shape, _ = p.declared_support('E')
        v_origin, v_shape, _ = p.declared_support('V')
        margin = 5
        self.assertEqual(v_shape[0], e_shape[0] + 2 * margin)
        self.assertEqual(v_shape[1], e_shape[1] + 2 * margin)
        self.assertEqual(v_origin[0], e_origin[0] - margin)
        self.assertEqual(v_origin[1], e_origin[1] - margin)

    def test_E_and_V_stay_inside_the_frozen_support_ceiling(self):
        self.assertEqual(p.MAX_SUPPORT_CELLS, 148_225)
        for name in ('E', 'V'):
            origin, shape, _ = p.declared_support(name)
            cells = shape[0] * shape[1]
            self.assertLessEqual(cells, p.MAX_SUPPORT_CELLS)
            self.assertLess(cells, 148_225 + 1)
        self.assertEqual(317 * 257, 81469)
        self.assertEqual(327 * 267, 87309)

    def test_unknown_support_is_refused(self):
        for name in ('', 'e', 'X', 'D2', 'D '):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'unknown declared support'):
                    p.declared_support(name)

    def test_support_ceiling_is_not_raised_for_E_or_V(self):
        # The card keeps the P2 ceiling; a wider support must be refused here, not
        # admitted by widening the table.
        wide = {'X': {'origin_native_xz': (0, 0), 'shape_zx': (401, 401),
                      'role': 'development', 'holdout': False, 'note': 'test'}}
        with patch.dict(p.DECLARED_SUPPORTS, wide, clear=False):
            with self.assertRaisesRegex(ValueError, 'above the declared ceiling'):
                p.declared_support('X')


class PreallocationTest(unittest.TestCase):
    """Refusals that must happen before an output directory or an array exists."""

    def test_oversized_declared_support_dispatched_before_any_read(self):
        wide = {'X': {'origin_native_xz': (0, 0), 'shape_zx': (401, 401),
                      'role': 'development', 'holdout': False, 'note': 'test'}}
        with tempfile.TemporaryDirectory() as d, \
                patch.dict(p.DECLARED_SUPPORTS, wide, clear=False), \
                patch.object(p, 'read_request') as read:
            target = Path(d) / 'result'
            with self.assertRaisesRegex(ValueError, 'above the declared ceiling'):
                p.run(target, support='X', source_request='missing', request_sha256='0' * 64)
            read.assert_not_called()
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_existing_target_refused_for_every_support(self):
        for name in sorted(p.DECLARED_SUPPORTS):
            with self.subTest(support=name):
                with tempfile.TemporaryDirectory() as d, \
                        patch.object(p, 'read_request') as read:
                    target = Path(d) / 'result'
                    target.mkdir()
                    (target / 'owner').write_text('external', encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'already exists'):
                        p.run(target, support=name, source_request='missing',
                              request_sha256='0' * 64)
                    read.assert_not_called()
                    self.assertEqual((target / 'owner').read_text(encoding='utf-8'),
                                     'external')
                    self.assertEqual(list(Path(d).iterdir()), [target])

    def test_page_budget_refused_before_any_page_is_loaded(self):
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / 'huge.npz'
            page.write_bytes(b'\0' * (p.MAX_PAGE_BYTES + 1))
            with patch('numpy.load') as load:
                with self.assertRaisesRegex(ValueError, 'above the declared'):
                    p.inspect_page_headers([{'path': str(page), 'sha256': '0' * 64}])
                load.assert_not_called()

    def test_request_pin_is_required_and_must_match(self):
        with tempfile.TemporaryDirectory() as d:
            request = Path(d) / 'request.json'
            request.write_text(json.dumps({'source_records': [
                {'path': 'a.npz', 'sha256': '0' * 64}]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '64-character external sha256'):
                p.read_request(request, '')
            with self.assertRaisesRegex(ValueError, 'pin mismatch'):
                p.read_request(request, '1' * 64)
            records, target, sha = p.read_request(request, p.file_sha256(request))
            self.assertEqual(target, request)
            self.assertEqual(sha, p.file_sha256(request))
            self.assertEqual(records[0]['path'], 'a.npz')


class SourceBindingTest(unittest.TestCase):
    """The card's four pinned pages bind E and V to the same saved source."""

    REQUEST = ('.scratch/highland-mainstem-world/evidence-highland-sources-v1/'
               'source-request.json')
    PAGES = {
        '.scratch/fine-terrain-40km/td-pages/td-page-41981-41364-2049.npz':
            '7fcfc426d970cbe9b77cb4221661b1f5f8001d7a3f6b06189041a3f01d1a7142',
        '.scratch/fine-terrain-40km/td-pages/td-page-41981-43364-2049.npz':
            'efeb11a0f4db4f32b042a14d18615659cf2f73ea00b6fb3a28bc53536847b1a3',
        '.scratch/fine-terrain-40km/td-pages/td-page-43981-41364-2049.npz':
            '6bf2594c3796466764e66ed44cfe06d951b77bef705eec71553262dc9a0ebcaf',
        '.scratch/fine-terrain-40km/td-pages/td-page-43981-43364-2049.npz':
            '9b74e605a81246e103c31a799b7486f94bacc76e7bdecb0ec22dc8485061a1d2',
    }

    def test_pinned_request_declares_the_four_fixed_pages(self):
        request = p.ROOT / self.REQUEST
        if not request.is_file():
            self.skipTest('the fixed four-page request is not in this checkout')
        records, _, sha = p.read_request(request, p.file_sha256(request))
        self.assertEqual({item['path']: item['sha256'] for item in records}, self.PAGES)
        self.assertEqual(len(records), 4)
        self.assertEqual(len(sha), 64)

    def test_E_and_V_are_covered_by_the_pinned_pages(self):
        # The declaration itself must sit inside the pinned page footprint, so neither
        # support can silently become a window the fixed pages do not cover.
        pages = [(41981, 41364), (41981, 43364), (43981, 41364), (43981, 43364)]
        size = 2049
        for name in ('E', 'V'):
            origin, shape, _ = p.declared_support(name)
            with self.subTest(support=name):
                covered = any(
                    px <= origin[0] and pz <= origin[1]
                    and origin[0] + shape[1] <= px + size
                    and origin[1] + shape[0] <= pz + size
                    for px, pz in pages)
                self.assertTrue(covered,
                                'support %s origin=%s shape=%s falls outside the pinned '
                                'pages' % (name, origin, shape))

    def test_manifest_binds_E_and_V_to_support_and_request(self):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        from tests.test_metric_highland_sources import patch_window
        for name in ('E', 'V'):
            with self.subTest(support=name):
                origin, shape, entry = p.declared_support(name)
                w, entry = declared_window(name)
                bundle = h.build_highland_sources(synthetic_window(w))
                validation = p.validate_bundle(bundle)
                source = synthetic_source(int(shape[0] * shape[1]))
                with tempfile.TemporaryDirectory() as d:
                    root = Path(d) / 'package'
                    manifest, _ = p.write_package(
                        root, support_name=name, origin=origin, shape=shape, entry=entry,
                        request_path='synthetic', request_sha='0' * 64, records=[SYNTHETIC_PAGE],
                        page_bytes=0, headers={}, window=w, source=source,
                        bundle=bundle, validation=validation, timing={},
                        request_sha_after='0' * 64)
                    self.assertEqual(manifest['support']['name'], name)
                    self.assertEqual(manifest['support']['origin_native_xz'], list(origin))
                    self.assertEqual(manifest['support']['shape_zx'], list(shape))
                    self.assertEqual(manifest['support']['role'], entry['role'])
                    self.assertIs(manifest['support']['holdout'], entry['holdout'])
                    self.assertEqual(manifest['source']['request_sha256'], '0' * 64)
                    self.assertEqual(manifest['source']['request_sha256_after_run'],
                                     '0' * 64)
                    self.assertEqual(manifest['source']['field_mask_sha256'],
                                     bundle['metadata']['source']['field_mask_sha256'])
                    self.assertTrue(p.read_package(root)[1]['head_table_rederived'])

    def test_support_registry_edit_cannot_promote_E_to_holdout(self):
        # A package written under the old role is refused when the table says holdout.
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        from tests.test_metric_highland_sources import patch_window
        origin, shape, entry = p.declared_support('E')
        w, entry = declared_window('E')
        bundle = h.build_highland_sources(synthetic_window(w))
        source = synthetic_source(int(shape[0] * shape[1]))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            p.write_package(root, support_name='E', origin=origin, shape=shape, entry=entry,
                            request_path='synthetic', request_sha='0' * 64, records=[SYNTHETIC_PAGE],
                            page_bytes=0, headers={}, window=w, source=source,
                            bundle=bundle, validation=p.validate_bundle(bundle), timing={},
                            request_sha_after='0' * 64)
            original = (root / 'manifest.json').read_text(encoding='utf-8')
            for field, value in (('holdout', True), ('role', 'holdout')):
                with self.subTest(field=field):
                    manifest = json.loads(original)
                    manifest['support'][field] = value
                    (root / 'manifest.json').write_text(json.dumps(manifest),
                                                        encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'support declaration'):
                        p.read_package(root)
            (root / 'manifest.json').write_text(original, encoding='utf-8')


class HeadDiagnosticsTest(unittest.TestCase):
    """``own_upstream_complete`` and ``region_complete`` never collapse into one field."""

    def _bundle(self, window):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        bundle = h.build_highland_sources(window)
        return bundle, p.validate_bundle(bundle)

    def test_certified_head_has_both_conditions(self):
        from tests.test_metric_highland_sources import valley_window
        bundle, _ = self._bundle(valley_window())
        table = p.head_diagnostics(bundle)
        self.assertTrue(table['rows'])
        for row in table['rows']:
            self.assertTrue(row['own_upstream_complete'])
            self.assertTrue(row['region_complete'])
            self.assertTrue(row['geometry_certified'])
        self.assertEqual(table['counts']['heads'], len(bundle['heads']))
        self.assertEqual(table['counts']['both_conditions'],
                         table['counts']['geometry_certified'])

    def test_pending_region_head_keeps_its_own_upstream_state(self):
        # A pending region does not make the head's own upstream incomplete, and the
        # table must say so in two separate fields. ``twin_window(140)`` is the
        # configuration whose patch reaches the support edge, so the region is pending
        # while the head's own strict-D8 upstream is already complete.
        from tests.test_metric_highland_sources import twin_window
        bundle, _ = self._bundle(twin_window(140))
        table = p.head_diagnostics(bundle)
        self.assertTrue(table['rows'])
        self.assertTrue(all(not row['region_complete'] for row in table['rows']))
        self.assertTrue(all(not row['geometry_certified'] for row in table['rows']))
        self.assertTrue(all(row['own_upstream_complete'] for row in table['rows']))
        self.assertEqual(table['counts']['region_pending'], len(table['rows']))
        self.assertEqual(table['counts']['own_upstream_complete'], len(table['rows']))
        self.assertEqual(table['counts']['both_conditions'], 0)
        self.assertEqual(table['counts']['own_upstream_complete']
                         + table['counts']['own_upstream_incomplete'],
                         table['counts']['heads'])

    def test_empty_head_table_is_reported_not_omitted(self):
        from tests.test_metric_highland_sources import patch_window
        bundle, _ = self._bundle(patch_window(160, 160))
        table = p.head_diagnostics(bundle)
        self.assertEqual(table['counts']['heads'], 0)
        self.assertEqual(table['rows'], [])
        self.assertEqual(table['schema'], p.HEAD_DIAGNOSTICS_SCHEMA)

    def test_tampered_head_mask_is_refused(self):
        from tests.test_metric_highland_sources import valley_window
        import copy
        bundle, _ = self._bundle(valley_window())
        forged = copy.deepcopy(bundle)
        forged['arrays']['head_flags'] = np.zeros_like(forged['arrays']['head_flags'])
        with self.assertRaisesRegex(ValueError, 'head diagnostics'):
            p.head_diagnostics(forged)

    def test_tampered_upstream_array_is_refused(self):
        from tests.test_metric_highland_sources import valley_window
        import copy
        bundle, _ = self._bundle(valley_window())
        forged = copy.deepcopy(bundle)
        forged['arrays']['upstream_complete'] = np.zeros_like(
            forged['arrays']['upstream_complete'])
        with self.assertRaisesRegex(ValueError, 'head diagnostics'):
            p.head_diagnostics(forged)

    def test_cold_read_rederives_the_diagnostic_table(self):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        window_used, _ = declared_window('D')
        bundle = h.build_highland_sources(synthetic_window(window_used))
        validation = p.validate_bundle(bundle)
        source = synthetic_source(int(window_used['field'].size))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            origin, shape, entry = p.declared_support('D')
            p.write_package(root, support_name='D', origin=origin, shape=shape, entry=entry,
                            request_path='synthetic', request_sha='0' * 64, records=[SYNTHETIC_PAGE],
                            page_bytes=0, headers={}, window=window_used,
                            source=source, bundle=bundle, validation=validation, timing={},
                            request_sha_after='0' * 64)
            written = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            self.assertTrue(written['head_diagnostics']['rows'])
            self.assertTrue(p.read_package(root)[1]['head_table_rederived'])
            original = (root / 'manifest.json').read_text(encoding='utf-8')
            attacks = [
                ('row field', lambda m: m['head_diagnostics']['rows'][0].__setitem__(
                    'own_upstream_complete', False)),
                ('row removal', lambda m: m['head_diagnostics']['rows'].pop()),
                ('count', lambda m: m['head_diagnostics']['counts'].__setitem__(
                    'geometry_certified', 7)),
                ('merged field', lambda m: m['head_diagnostics'].__setitem__(
                    'statement', 'one field')),
            ]
            for label, mutate in attacks:
                with self.subTest(attack=label):
                    manifest = json.loads(original)
                    mutate(manifest)
                    (root / 'manifest.json').write_text(json.dumps(manifest),
                                                        encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'head diagnostics'):
                        p.read_package(root)
            (root / 'manifest.json').write_text(original, encoding='utf-8')


def yield_cells(window):
    return int(np.asarray(window['field']).size)


class ResourceAndCodeTest(unittest.TestCase):
    """RSS samples are samples, and the code digests are self-reports that cross-bind."""

    def test_rss_metric_label_is_not_a_peak_claim(self):
        self.assertEqual(p.RSS_METRIC, 'sampled_current_rss_not_peak')
        self.assertNotIn('peak', p.RSS_METRIC.replace('not_peak', ''))

    def test_rss_sample_is_labelled_and_optional(self):
        samples = []
        p.rss_sample(samples, 'stage-a', 0.0)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]['stage'], 'stage-a')
        self.assertIn('current_rss_bytes', samples[0])
        with patch.object(p, 'rss_sample_bytes', return_value=None):
            p.rss_sample(samples, 'stage-b', 1.0)
        self.assertIsNone(samples[1]['current_rss_bytes'])

    def test_code_digests_name_every_declared_file(self):
        digests = p.code_digests()
        self.assertEqual(sorted(digests['files']), sorted(p.CODE_FILES))
        for value in digests['files'].values():
            self.assertRegex(value, r'^[0-9a-f]{64}$')
        self.assertIn('not a signature', digests['statement'])

    def test_cold_read_refuses_tampered_resource_or_code_block(self):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        from tests.test_metric_highland_sources import patch_window
        origin, shape, entry = p.declared_support('E')
        w, entry = declared_window('E')
        bundle = h.build_highland_sources(synthetic_window(w))
        source = synthetic_source(int(shape[0] * shape[1]))
        samples = [{'stage': 'after_build', 'elapsed_s': 0.5, 'current_rss_bytes': 123}]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            p.write_package(root, support_name='E', origin=origin, shape=shape, entry=entry,
                            request_path='synthetic', request_sha='0' * 64, records=[SYNTHETIC_PAGE],
                            page_bytes=0, headers={}, window=w, source=source,
                            bundle=bundle, validation=p.validate_bundle(bundle), timing={},
                            request_sha_after='0' * 64, rss_samples=samples)
            original = (root / 'manifest.json').read_text(encoding='utf-8')
            attacks = [
                ('rss metric', lambda m: m['resources'].__setitem__(
                    'rss_metric', 'peak_rss_bytes')),
                ('sample shape', lambda m: m['resources']['samples'].append(
                    {'stage': 'x'})),
                ('sample value', lambda m: m['resources']['samples'][0].__setitem__(
                    'current_rss_bytes', -1)),
                ('code file', lambda m: m['code']['files'].__setitem__(
                    'tools/other.py', '0' * 64)),
                ('code digest', lambda m: m['code']['files'].__setitem__(
                    'terrain_pipeline/surface_rivers/native_30m_source.py', '0' * 64)),
                ('code block', lambda m: m.pop('code')),
            ]
            for label, mutate in attacks:
                with self.subTest(attack=label):
                    manifest = json.loads(original)
                    mutate(manifest)
                    (root / 'manifest.json').write_text(json.dumps(manifest),
                                                        encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'package'):
                        p.read_package(root)
            (root / 'manifest.json').write_text(original, encoding='utf-8')
            self.assertTrue(p.read_package(root)[1]['head_table_rederived'])

    def test_cold_read_refuses_a_disagreeing_page_binding(self):
        # The request pin and the page list are recorded more than once; two copies that
        # disagree mean the manifest was edited after it was written.
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        origin, shape, entry = p.declared_support('E')
        window_used, _ = declared_window('E')
        bundle = h.build_highland_sources(synthetic_window(window_used))
        source = synthetic_source(int(shape[0] * shape[1]))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            p.write_package(root, support_name='E', origin=origin, shape=shape, entry=entry,
                            request_path='synthetic', request_sha='0' * 64,
                            records=[SYNTHETIC_PAGE], page_bytes=0, headers={},
                            window=window_used, source=source, bundle=bundle,
                            validation=p.validate_bundle(bundle), timing={},
                            request_sha_after='0' * 64)
            original = (root / 'manifest.json').read_text(encoding='utf-8')
            attacks = [
                ('request pin after run', lambda m: m['source'].__setitem__(
                    'request_sha256_after_run', '1' * 64)),
                ('page list', lambda m: m['source'].__setitem__(
                    'page_records', [{'path': SYNTHETIC_PAGE['path'],
                                      'sha256': '1' * 64}])),
                ('page list dropped', lambda m: m['source'].__setitem__(
                    'page_records', [])),
                ('loader binding', lambda m: m['source'].__setitem__(
                    'loader_source_records', ['x'])),
            ]
            for label, mutate in attacks:
                with self.subTest(attack=label):
                    manifest = json.loads(original)
                    mutate(manifest)
                    (root / 'manifest.json').write_text(json.dumps(manifest),
                                                        encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'package'):
                        p.read_package(root)
            (root / 'manifest.json').write_text(original, encoding='utf-8')
            self.assertTrue(p.read_package(root)[1]['head_table_rederived'])

class PageBindingDualityTest(unittest.TestCase):
    """Each copy of the page list is required on its own, and none may be forged.

    The tool records the pinned page list in three places (the request's page records, the
    loader's own records, and the bundle metadata). Merging them before comparing would let
    a **deleted** copy pass whenever another copy still matched, so every attack below
    removes or forges exactly one copy and expects a refusal. The last two tests are the
    other half of the same rule: a ``None`` pin must not compare equal to another ``None``
    pin (a missing field is not agreement), and the same path pinned twice is refused.
    """

    def _package(self, root):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        origin, shape, entry = p.declared_support('E')
        window_used, _ = declared_window('E')
        bundle = h.build_highland_sources(synthetic_window(window_used))
        p.write_package(root, support_name='E', origin=origin, shape=shape, entry=entry,
                        request_path='synthetic', request_sha='0' * 64,
                        records=[SYNTHETIC_PAGE], page_bytes=0, headers={},
                        window=window_used, source=synthetic_source(int(shape[0] * shape[1])),
                        bundle=bundle, validation=p.validate_bundle(bundle), timing={},
                        request_sha_after='0' * 64)
        return json.loads((root / 'manifest.json').read_text(encoding='utf-8'))

    def _expect_refusal(self, root, manifest, label, *, reseal=False):
        """Write the edited manifest and require a refusal whose reason is the binding.

        ``reseal`` re-derives ``identity_sha256`` from the edited bundle, because an edit to
        the bundle metadata would otherwise be caught by the digest check first -- which is
        a correct refusal, but not the one this test is about. Re-sealing takes that check
        out of the way so the binding gate itself has to fire.
        """
        if reseal:
            # Two copies of the bundle digest exist in the manifest: the bundle itself and the
            # ``identity`` section. Re-sealing both is what a determined editor would do, so
            # the binding gate -- not the digest check -- has to be the thing that refuses.
            from terrain_pipeline.common_infra import identity
            arrays = dict(np.load(root / 'arrays.npz'))
            digest = identity(arrays, manifest['bundle']['metadata'])
            manifest['bundle']['identity_sha256'] = digest
            manifest['identity']['bundle_identity_sha256'] = digest
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(ValueError) as caught:
            p.read_package(root)
        self.assertRegex(str(caught.exception), 'page|source|pin|binding',
                         '%s was refused for a different reason: %s'
                         % (label, caught.exception))

    def test_each_of_the_three_copies_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            original = self._package(root)
            drops = [
                ('page records', lambda m: m['source'].pop('page_records'), False),
                ('loader records', lambda m: m['source'].pop('loader_source_records'), False),
                ('bundle metadata', lambda m: m['bundle']['metadata']['source'].pop(
                    'source_records'), True),
            ]
            for label, mutate, reseal in drops:
                with self.subTest(copy=label):
                    manifest = json.loads(json.dumps(original))
                    mutate(manifest)
                    self._expect_refusal(root, manifest, label, reseal=reseal)
            (root / 'manifest.json').write_text(json.dumps(original), encoding='utf-8')
            self.assertTrue(p.read_package(root)[1]['head_table_rederived'])

    def test_a_duplicate_path_in_one_copy_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            original = self._package(root)
            manifest = json.loads(json.dumps(original))
            manifest['source']['loader_source_records'].append(dict(SYNTHETIC_PAGE))
            self._expect_refusal(root, manifest, 'duplicate path')

    def test_a_pin_that_is_not_lowercase_hex_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            original = self._package(root)
            for label, value in (('upper case', 'A' * 64), ('short', 'a' * 63),
                                 ('none', None)):
                with self.subTest(pin=label):
                    manifest = json.loads(json.dumps(original))
                    manifest['source']['page_records'] = [
                        {'path': SYNTHETIC_PAGE['path'], 'sha256': value}]
                    self._expect_refusal(root, manifest, 'pin %s' % label)

    def test_two_missing_pins_do_not_compare_equal(self):
        # A missing field must never equal another missing field: both copies set to None
        # would otherwise pass a naive equality test.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            original = self._package(root)
            manifest = json.loads(json.dumps(original))
            for block in ('page_records', 'loader_source_records'):
                manifest['source'][block] = [{'path': SYNTHETIC_PAGE['path'],
                                              'sha256': None}]
            manifest['bundle']['metadata']['source']['source_records'] = [
                {'path': SYNTHETIC_PAGE['path'], 'sha256': None}]
            self._expect_refusal(root, manifest, 'two missing pins', reseal=True)

    def test_the_request_pin_before_and_after_the_run_must_agree(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            original = self._package(root)
            manifest = json.loads(json.dumps(original))
            manifest['source']['request_sha256_after_run'] = '1' * 64
            self._expect_refusal(root, manifest, 'request pin')

    def test_a_forged_page_in_one_copy_only_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            original = self._package(root)
            manifest = json.loads(json.dumps(original))
            manifest['bundle']['metadata']['source']['source_records'] = [
                {'page_key': 'p00', 'path': SYNTHETIC_PAGE['path'], 'sha256': '2' * 64}]
            self._expect_refusal(root, manifest, 'forged copy', reseal=True)


class ManifestGenerationTest(unittest.TestCase):
    """A v2 manifest requires the new blocks; a v1 manifest is still readable."""

    def _write(self, target, **overrides):
        from terrain_pipeline.surface_rivers import metric_highland_sources as h
        origin, shape, entry = p.declared_support('D')
        window_used, _ = declared_window('D')
        bundle = h.build_highland_sources(synthetic_window(window_used))
        source = synthetic_source(int(window_used['field'].size))
        kwargs = dict(support_name='D', origin=origin, shape=shape, entry=entry,
                      request_path='synthetic', request_sha='0' * 64, records=[SYNTHETIC_PAGE],
                      page_bytes=0, headers={}, window=window_used, source=source,
                      bundle=bundle, validation=p.validate_bundle(bundle), timing={},
                      request_sha_after='0' * 64)
        kwargs.update(overrides)
        p.write_package(target, **kwargs)
        return bundle

    def test_schema_is_versioned(self):
        self.assertEqual(p.SCHEMA, 'metric-highland-sources-prepare-v2')
        self.assertEqual(p.LEGACY_SCHEMAS, ('metric-highland-sources-prepare-v1',))
        self.assertNotIn(p.SCHEMA, p.LEGACY_SCHEMAS)

    def test_v2_manifest_without_the_new_blocks_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'package'
            self._write(root)
            original = (root / 'manifest.json').read_text(encoding='utf-8')
            self.assertEqual(json.loads(original)['schema'], p.SCHEMA)
            for block in ('head_diagnostics', 'code', 'resources'):
                with self.subTest(block=block):
                    manifest = json.loads(original)
                    manifest.pop(block)
                    (root / 'manifest.json').write_text(json.dumps(manifest),
                                                        encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'package'):
                        p.read_package(root)
            (root / 'manifest.json').write_text(original, encoding='utf-8')
            self.assertTrue(p.read_package(root)[1]['head_table_rederived'])

    def test_legacy_manifest_is_read_by_the_checks_it_could_pass(self):
        # The old D/H evidence predates these blocks; refusing it or inventing them would
        # both be wrong. The numeric gates stay identical either way.
        legacy = p.ROOT / '.scratch/highland-mainstem-world/evidence-highland-sources-v1'
        if not (legacy / 'D-main-v2' / p.MANIFEST_NAME).is_file():
            self.skipTest('the old D/H evidence is not in this checkout')
        for name in ('D-main-v2', 'H-main-v1'):
            with self.subTest(package=name):
                bundle, report = p.read_package(legacy / name)
                self.assertTrue(report['head_table_rederived'])
                self.assertEqual(bundle['schema'], 'metric-highland-source-regions-v1')

    def test_legacy_manifest_still_refuses_a_tampered_count(self):
        legacy = p.ROOT / '.scratch/highland-mainstem-world/evidence-highland-sources-v1'
        source = legacy / 'D-main-v2'
        if not (source / p.MANIFEST_NAME).is_file():
            self.skipTest('the old D/H evidence is not in this checkout')
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / 'package'
            shutil.copytree(source, copy)
            original = (copy / 'manifest.json').read_text(encoding='utf-8')
            manifest = json.loads(original)
            manifest['counts']['heads_certified'] = 100000
            (copy / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'package'):
                p.read_package(copy)
            (copy / 'manifest.json').write_text(original, encoding='utf-8')
            self.assertTrue(p.read_package(copy)[1]['head_table_rederived'])


if __name__=='__main__': unittest.main()
