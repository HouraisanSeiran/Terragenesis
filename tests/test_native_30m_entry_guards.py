"""Pure AST guards against coarse-scale entrypoints and hidden generation imports."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ('publish_native_30m_bundle.py', 'native_30m_bundle_reader.py', 'native_30m_bundle_validation.py',
         'native_30m_sources.py', 'native_30m_query.py', 'native_30m_compute_worker.py',
         'native_30m_saved_source.py', 'native_30m_diagnostic_only.py', 'native_30m_event_config.py')
FORBIDDEN = {'metric_domain_pipeline', 'metric_domain_closed_gate', 'hydrology_planning',
             'metric_domain_flow', 'metric_domain_sediment', 'metric_domain_coupled', 'metric_domain_bed_feedback',
             'publish_domain_bundle', 'torch', 'diffusion.physical_backend', 'diffusion.pipeline'}


class EntrypointGuards(unittest.TestCase):
    def test_native_tools_have_no_direct_coarse_or_gpu_import(self):
        for name in TOOLS:
            tree = ast.parse((ROOT/'tools'/name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                for module in modules:
                    with self.subTest(file=name, module=module):
                        self.assertFalse(any(module == item or module.endswith('.'+item) for item in FORBIDDEN))

    def test_no_literal_scratch_python_runtime_import(self):
        for name in TOOLS:
            tree = ast.parse((ROOT/'tools'/name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                called = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
                if called not in ('import_module', 'spec_from_file_location', '__import__'):
                    continue
                strings = [value.value for value in node.args if isinstance(value, ast.Constant) and isinstance(value.value, str)]
                with self.subTest(file=name, called=called):
                    self.assertFalse(any('.scratch' in value for value in strings))


if __name__ == '__main__':
    unittest.main()
