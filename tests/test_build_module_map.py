"""Accuracy checks for tools/build_module_map.py on isolated temporary trees.

Each test builds a throwaway tree under tempfile.mkdtemp() that mirrors the real
root names (terrain_pipeline/, tools/) so the module's ROOTS and SKIP_DIRS rules
apply unchanged, and chdir into it. The workspace sources are never read or
written, and no generated document is produced inside the repository.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tools import build_module_map as module_map


@contextlib.contextmanager
def moved_into(directory):
    previous = os.getcwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(previous)


class ModuleMapAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='module-map-'))
        self.addCleanup(shutil.rmtree, self.root, True)

    # -- fixtures ---------------------------------------------------------
    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode('utf-8') if isinstance(text, str) else text
        path.write_bytes(data)
        return name

    def put_bom(self, name, text):
        return self.put(name, b'\xef\xbb\xbf' + text.encode('utf-8'))

    def analyse(self, name):
        with moved_into(self.root):
            return module_map.analyse(name)

    def graph(self, names):
        info = {}
        with moved_into(self.root):
            for name in names:
                info[name] = module_map.analyse(name)
        return module_map.import_graph(info)

    def build_map(self):
        """Run the real main() over the temp tree and return its JSON rows."""
        (self.root / 'docs' / 'architecture').mkdir(parents=True, exist_ok=True)
        stream = io.StringIO()
        with moved_into(self.root), contextlib.redirect_stdout(stream):
            module_map.main()
        payload = json.loads((self.root / module_map.OUT_JSON).read_text(encoding='utf-8'))
        self.assertTrue((self.root / module_map.OUT_MD).exists())
        return {row['path']: row for row in payload['modules']}

    # -- byte checksum ----------------------------------------------------
    def test_bom_file_parses_and_keeps_raw_byte_sha256(self):
        raw_text = '"""BOM module."""\nimport terrain_pipeline.partner\n'
        name = self.put_bom('terrain_pipeline/alpha.py', raw_text)
        record = self.analyse(name)
        self.assertIsNotNone(record, 'UTF-8 BOM must not make the file unparsable')
        self.assertEqual(record['docstring'], 'BOM module.')
        expected = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.assertEqual(record['sha256'], expected)
        stripped = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()
        self.assertNotEqual(record['sha256'], stripped,
                            'digest must cover the original bytes, BOM included')

    def test_non_bom_sha256_matches_plain_utf8_bytes(self):
        name = self.put('terrain_pipeline/plain.py', '"""Plain module."""\n')
        record = self.analyse(name)
        self.assertEqual(record['sha256'],
                         hashlib.sha256((self.root / name).read_bytes()).hexdigest())
        self.assertEqual(record['lines'], 1)

    def test_crlf_file_sha_is_raw_bytes_not_lf_normalised(self):
        # A CRLF source: reading it as text silently converts \r\n to \n, so a
        # digest taken from the decoded string would NOT match the file on disk
        # (and would miss frozen evidence recorded against the real bytes).
        name = self.put('terrain_pipeline/crlf.py',
                        b'"""CRLF module."""\r\nVALUE = 1\r\nimport terrain_pipeline.other\r\n')
        raw = (self.root / name).read_bytes()
        self.assertIn(b'\r\n', raw, 'fixture must really carry CRLF line endings')
        record = self.analyse(name)
        self.assertIsNotNone(record)
        self.assertEqual(record['sha256'], hashlib.sha256(raw).hexdigest())
        normalised = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()
        self.assertNotEqual(record['sha256'], normalised,
                            'digest must not be taken from LF-normalised text')
        self.assertEqual(record['lines'], 3)

    # -- relative imports -------------------------------------------------
    def test_channel_like_relative_imports_become_edges(self):
        names = [
            self.put('terrain_pipeline/surface_rivers/__init__.py', ''),
            self.put('terrain_pipeline/surface_rivers/water.py', 'def safe_water():\n    return 1\n'),
            self.put('terrain_pipeline/surface_rivers/bridge.py', 'def bridge_diagonals():\n    return 2\n'),
            self.put('terrain_pipeline/surface_rivers/channel.py',
                     'from .water import safe_water\nfrom .bridge import bridge_diagonals\n'),
        ]
        with moved_into(self.root):
            channel = module_map.analyse('terrain_pipeline/surface_rivers/channel.py')
        self.assertIn('terrain_pipeline.surface_rivers.water', channel['internal_imports'])
        self.assertIn('terrain_pipeline.surface_rivers.bridge', channel['internal_imports'])
        graph = self.graph(names)
        self.assertEqual(graph.get('terrain_pipeline/surface_rivers/water.py'),
                         {'terrain_pipeline/surface_rivers/channel.py'})
        self.assertEqual(graph.get('terrain_pipeline/surface_rivers/bridge.py'),
                         {'terrain_pipeline/surface_rivers/channel.py'})

    def test_from_dot_import_and_two_level_parent(self):
        names = [
            self.put('terrain_pipeline/__init__.py', ''),
            self.put('terrain_pipeline/sub/__init__.py', ''),
            self.put('terrain_pipeline/sub/core.py', 'VALUE = 3\n'),
            self.put('terrain_pipeline/sub/deep/__init__.py', ''),
            self.put('terrain_pipeline/sub/deep/mod.py',
                     'from ..core import VALUE\nfrom .. import core\nfrom . import sibling\n'),
            self.put('terrain_pipeline/sub/deep/sibling.py', ''),
            self.put('terrain_pipeline/sibling.py', ''),
        ]
        graph = self.graph(names)
        callers = 'terrain_pipeline/sub/deep/mod.py'
        self.assertEqual(graph.get('terrain_pipeline/sub/core.py'), {callers})
        self.assertEqual(graph.get('terrain_pipeline/sub/deep/sibling.py'), {callers},
                         'from . must stay inside the importing package')
        self.assertIsNone(graph.get('terrain_pipeline/sibling.py'),
                          'a same-named module one package up must not be credited')

    def test_package_init_and_submodule_targets(self):
        names = [
            self.put('terrain_pipeline/pkg/__init__.py', 'from .part import thing\n'),
            self.put('terrain_pipeline/pkg/part.py', 'thing = 1\n'),
            self.put('tools/consumer.py',
                     'from terrain_pipeline.pkg import thing\n'
                     'import terrain_pipeline.pkg.part\n'),
        ]
        graph = self.graph(names)
        consumer = 'tools/consumer.py'
        self.assertEqual(module_map.module_name_of('terrain_pipeline/pkg/__init__.py'),
                         'terrain_pipeline.pkg')
        self.assertEqual(graph.get('terrain_pipeline/pkg/__init__.py'), {consumer})
        self.assertEqual(graph.get('terrain_pipeline/pkg/part.py'),
                         {consumer, 'terrain_pipeline/pkg/__init__.py'})

    def test_import_beyond_root_and_unknown_names_add_no_edge(self):
        names = [
            self.put('terrain_pipeline/a.py', 'from ..elsewhere import x\n'),
            self.put('terrain_pipeline/elsewhere.py', 'x = 1\n'),
            self.put('terrain_pipeline/ghost_user.py',
                     'import terrain_pipeline.does_not_exist\n'
                     'import numpy\nfrom requests import get\n'),
        ]
        with moved_into(self.root):
            beyond = module_map.analyse('terrain_pipeline/a.py')
        self.assertEqual(beyond['internal_imports'], [],
                         'an import climbing above the root must resolve to nothing')
        graph = self.graph(names)
        self.assertIsNone(graph.get('terrain_pipeline/elsewhere.py'))
        self.assertIsNone(graph.get('terrain_pipeline/ghost_user.py'))

    def test_external_and_same_named_modules_are_not_confused(self):
        names = [
            self.put('terrain_pipeline/surface_rivers/water.py', 'x = 1\n'),
            self.put('tools/water.py', 'x = 2\n'),
            self.put('terrain_pipeline/importer.py', 'import tools.water\nimport os.path\n'),
        ]
        graph = self.graph(names)
        self.assertEqual(graph.get('tools/water.py'), {'terrain_pipeline/importer.py'})
        self.assertIsNone(graph.get('terrain_pipeline/surface_rivers/water.py'))

    def test_function_local_import_is_seen(self):
        names = [
            self.put('terrain_pipeline/late.py', 'x = 1\n'),
            self.put('terrain_pipeline/caller.py',
                     'def run():\n    import terrain_pipeline.late\n    return 1\n'),
        ]
        graph = self.graph(names)
        self.assertEqual(graph.get('terrain_pipeline/late.py'),
                         {'terrain_pipeline/caller.py'})

    # -- degraded inputs --------------------------------------------------
    def test_illegal_syntax_is_reported_not_guessed(self):
        name = self.put('terrain_pipeline/broken.py', 'def broken(:\n')
        self.assertIsNone(self.analyse(name))

    # -- end to end through main() ----------------------------------------
    def test_main_reports_relative_callers_and_parse_errors(self):
        self.put('terrain_pipeline/surface_rivers/__init__.py', '')
        self.put('terrain_pipeline/surface_rivers/water.py', 'x = 1\n')
        self.put('terrain_pipeline/surface_rivers/channel.py', 'from .water import x\n')
        self.put('terrain_pipeline/surface_rivers/broken.py', 'def broken(:\n')
        rows = self.build_map()
        self.assertEqual(rows['terrain_pipeline/surface_rivers/water.py']['imported_by'], 1)
        self.assertEqual(rows['terrain_pipeline/surface_rivers/channel.py']['imported_by'], 0)
        self.assertTrue(rows['terrain_pipeline/surface_rivers/broken.py']['parse_error'])
        self.assertEqual(rows['terrain_pipeline/surface_rivers/water.py']['imports'],
                         [])
        self.assertIn('terrain_pipeline.surface_rivers.water',
                      rows['terrain_pipeline/surface_rivers/channel.py']['imports'][:6])

    def test_main_counts_bom_module_without_losing_it(self):
        self.put_bom('terrain_pipeline/alpha.py', '"""Alpha."""\nimport terrain_pipeline.beta\n')
        self.put('terrain_pipeline/beta.py', '"""Beta."""\n')
        rows = self.build_map()
        alpha = rows['terrain_pipeline/alpha.py']
        self.assertFalse(alpha['parse_error'])
        self.assertEqual(alpha['purpose'], 'Alpha.')
        self.assertEqual(rows['terrain_pipeline/beta.py']['imported_by'], 1)
        self.assertNotIn('sha256', alpha, 'row schema stays as before; sha is internal')

    # -- algorithm categories -----------------------------------------------
    def test_main_resolves_categories_and_groups_algorithm_sections(self):
        self.put('terrain_pipeline/declared.py', '"""D."""\nCATEGORY = "C"\n')
        self.put('terrain_pipeline/listed.py', '"""L."""\n')
        self.put('diffusion/unlisted.py', '"""U."""\n')
        self.put('tools/helper.py', '"""T."""\n')
        self.put('docs/architecture/algorithm-categories.json', json.dumps(
            {'categories': {'A': '山脉与基础地形：x'},
             'modules': {'terrain_pipeline/declared.py': {'category': 'A'},
                         'terrain_pipeline/listed.py': {'category': 'A'}}}, ensure_ascii=False))
        rows = self.build_map()
        self.assertEqual((rows['terrain_pipeline/declared.py']['category'],
                          rows['terrain_pipeline/declared.py']['category_source']), ('C', 'declared'))
        self.assertEqual((rows['terrain_pipeline/listed.py']['category'],
                          rows['terrain_pipeline/listed.py']['category_source']), ('A', 'registry'))
        self.assertIsNone(rows['diffusion/unlisted.py']['category'])
        self.assertFalse(rows['tools/helper.py']['is_algorithm_module'])
        text = (self.root / module_map.OUT_MD).read_text(encoding='utf-8')
        self.assertIn('## 大类 A 山脉与基础地形（1）', text)
        self.assertIn('## 大类 C（1）', text)
        self.assertIn('## 大类 未归类（缺大类）（1）', text)
        self.assertIn('## tools（1）', text)
        self.assertNotIn('## terrain_pipeline（', text)
        self.assertIn('`diffusion/unlisted.py`', text)


if __name__ == '__main__':
    unittest.main()
