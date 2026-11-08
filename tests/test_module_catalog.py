"""Static catalog coverage, provenance and drift checks without application imports."""
from pathlib import Path
import tempfile
import unittest

from tools import build_module_catalog as catalog


class ModuleCatalogTests(unittest.TestCase):
    def put(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_scope_excludes_runtime_archive_and_nested_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('terrain_pipeline/a.py', 'src/main/A.java', 'tools/node_modules/x.py',
                         'runtime/private.py', 'legacy-code/old.py', 'verification/frozen.py'):
                self.put(root, name, '')
            self.assertEqual(catalog.source_paths(root), ['src/main/A.java', 'terrain_pipeline/a.py'])

    def test_relative_imports_and_package_members_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.put(root, 'terrain_pipeline/__init__.py', '')
            self.put(root, 'terrain_pipeline/a.py', 'from . import b\n')
            self.put(root, 'terrain_pipeline/b.py', 'def action(): pass\n')
            entries = {e['path']: e for e in catalog.collect(root, {})['entries']}
            self.assertIn('terrain_pipeline/b.py', entries['terrain_pipeline/a.py']['local_import_targets'])
            self.assertEqual(entries['terrain_pipeline/b.py']['static_importers'], ['terrain_pipeline/a.py'])

    def test_missing_description_is_not_inferred_from_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.put(root, 'terrain_pipeline/complete_world_solver.py', 'def small_proxy(): pass\n')
            item = catalog.collect(root, {})['entries'][0]
            self.assertEqual(item['purpose_evidence'], 'unreviewed')
            self.assertEqual(item['symbols'], ['small_proxy'])
            self.assertNotIn('complete_world_solver', item['purpose'])

    def test_manual_note_and_docstring_have_distinct_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.put(root, 'tools/a.py', '\"\"\"Author description.\"\"\"\n')
            first = catalog.collect(root, {})['entries'][0]
            second = catalog.collect(root, {'tools/a.py': {'purpose': 'Reviewed role', 'stage': 'shared'}})['entries'][0]
            self.assertEqual(first['purpose_evidence'], 'source-docstring')
            self.assertEqual(second['purpose_evidence'], 'manual-reviewed')
            self.assertEqual(second['purpose'], 'Reviewed role')

    def test_check_detects_add_delete_content_and_keeps_manual_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.put(root, 'tools/a.py', '\"\"\"First.\"\"\"\n')
            self.put(root, str(catalog.OUTPUT / 'notes.md'), '# Manual notes\n')
            self.assertTrue(catalog.update(root, write=True))
            self.assertEqual(catalog.update(root), [])
            source.write_text('\"\"\"Changed.\"\"\"\n', encoding='utf-8')
            self.assertIn('catalog.json', catalog.update(root))
            catalog.update(root, write=True)
            second = self.put(root, 'tools/b.py', '')
            self.assertTrue(catalog.update(root))
            catalog.update(root, write=True)
            second.unlink()
            self.assertTrue(catalog.update(root))
            catalog.update(root, write=True)
            self.assertEqual(catalog.update(root), [])
            self.assertEqual((root / catalog.OUTPUT / 'notes.md').read_text(), '# Manual notes\n')

    def registry(self, root, modules):
        import json
        self.put(root, 'docs/architecture/algorithm-categories.json', json.dumps(
            {'schema': 'algorithm-categories-v1', 'categories': {'A': '山脉与基础地形：x', 'B': '河网：y'},
             'modules': {k: {'category': v, 'reason': 't'} for k, v in modules.items()}}, ensure_ascii=False))

    def test_category_declaration_wins_over_registry_and_tools_are_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.put(root, 'terrain_pipeline/declared.py', 'CATEGORY = "B"\n')
            self.put(root, 'terrain_pipeline/listed.py', 'x = 1\n')
            self.put(root, 'diffusion/bad.py', 'CATEGORY = "Z"\n')
            self.put(root, 'vdm_diffusion/none.py', '')
            self.put(root, 'tools/helper.py', '')
            self.registry(root, {'terrain_pipeline/declared.py': 'A', 'terrain_pipeline/listed.py': 'A'})
            result = catalog.collect(root, {})
            entries = {e['path']: e for e in result['entries']}
            self.assertEqual((entries['terrain_pipeline/declared.py']['category'], entries['terrain_pipeline/declared.py']['category_source']), ('B', 'declared'))
            self.assertEqual((entries['terrain_pipeline/listed.py']['category'], entries['terrain_pipeline/listed.py']['category_source']), ('A', 'registry'))
            self.assertEqual(entries['diffusion/bad.py']['category_source'], 'declared-invalid')
            self.assertFalse(entries['tools/helper.py']['algorithm_module'])
            self.assertEqual(result['algorithm_modules_missing_category'], ['diffusion/bad.py', 'vdm_diffusion/none.py'])

    def test_pages_are_grouped_by_category_and_check_fails_on_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.put(root, 'terrain_pipeline/a.py', '')
            self.put(root, 'terrain_pipeline/b.py', '')
            self.put(root, 'tools/t.py', '')
            self.registry(root, {'terrain_pipeline/a.py': 'A', 'terrain_pipeline/b.py': 'B'})
            products = catalog.render(catalog.collect(root, {}))
            self.assertIn('category-A-01.md', products)
            self.assertIn('category-B-01.md', products)
            self.assertIn('tools-01.md', products)
            self.assertNotIn('terrain_pipeline-01.md', products)
            self.assertIn('terrain_pipeline/a.py', products['category-A-01.md'])
            self.assertNotIn('terrain_pipeline/b.py', products['category-A-01.md'])
            catalog.update(root, write=True)
            self.assertEqual(catalog.update(root), [])
            self.assertEqual(catalog.missing_categories(root), [])
            self.put(root, 'diffusion/new.py', '')
            catalog.update(root, write=True)
            self.assertEqual(catalog.missing_categories(root), ['diffusion/new.py'])
            self.assertIn('category-missing-01.md', catalog.render(catalog.collect(root, {})))

    def test_parse_errors_are_explicit_and_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.put(root, 'tools/bad.py', 'def bad(:\n')
            one = catalog.collect(root, {})
            self.assertTrue(one['entries'][0]['parse_error'])
            self.assertEqual(catalog.render(one), catalog.render(catalog.collect(root, {})))


if __name__ == '__main__':
    unittest.main()
