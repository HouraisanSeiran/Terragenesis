"""Independent cross-family checks for explicit, isolated legacy replay."""
import importlib
from pathlib import Path
import subprocess
import sys
import unittest
import numpy as np
from terrain_pipeline import vdm_cuts as current_fault
from terrain_pipeline import shallow_water as current_water
from terrain_pipeline.vdm_cuts import FaultRecipe
from tests.metric_vdm_fault_fixtures import recipe, selection, source
from tools import frozen_vdm_fault as fault_legacy
from tools import single_domain_legacy_entrypoints as water_legacy
ROOT = Path(__file__).resolve().parents[1]

class LegacySourceIsolationTests(unittest.TestCase):

    def test_two_archive_adapters_are_lazy_in_a_fresh_process(self):
        code = "import sys; import tools.frozen_vdm_fault; import tools.single_domain_legacy_entrypoints; assert not any(n.startswith(('_terragenesis_legacy_fault_v1_', '_single_domain_legacy_replay_')) for n in sys.modules)"
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multiple_archive_families_do_not_replace_current_modules(self):
        current_support = importlib.import_module('terrain_pipeline.shallow_water')
        original_path = list(sys.path)
        original_fault = current_fault
        original_water = current_water
        old_fault = fault_legacy.load_legacy_api()
        old_water = [water_legacy.load_legacy_entrypoint(version) for version in ('v4', 'v8')]
        self.assertEqual(sys.path, original_path)
        self.assertIs(sys.modules['terrain_pipeline.vdm_cuts'], original_fault)
        self.assertIs(sys.modules['terrain_pipeline.shallow_water'], original_water)
        self.assertIs(sys.modules['terrain_pipeline.shallow_water'], current_support)
        self.assertIs(current_fault.FaultRecipe, FaultRecipe)
        self.assertIsNot(old_fault.FaultRecipe, FaultRecipe)
        self.assertTrue(old_fault.__name__.startswith('_terragenesis_legacy_fault_v1_'))
        for module in old_water:
            self.assertTrue(module.__name__.startswith('_single_domain_legacy_replay_'))
            self.assertTrue(module._advance.__module__.startswith('_single_domain_legacy_replay_'))
        for name in ('terrain_pipeline.metric_vdm_fault', 'terrain_pipeline.single_domain_shallow_water_v4', 'terrain_pipeline.single_domain_shallow_water_v8'):
            self.assertNotIn(name, sys.modules)
            self.assertIsNone(importlib.util.find_spec(name))

    def test_current_fault_output_is_unchanged_after_cross_family_replay_loads(self):
        original = source()
        parameters = recipe(slip=-1.5, strike=18.0)
        before = current_fault.apply_fault(original, recipe=parameters, selection_mask=selection())
        original_path = list(sys.path)
        for version in ('v8', 'v4'):
            water_legacy.load_legacy_entrypoint(version)
            fault_legacy.load_legacy_api()
        after = current_fault.apply_fault(original, recipe=parameters, selection_mask=selection())
        self.assertEqual(before['identity_sha256'], after['identity_sha256'])
        self.assertEqual(before['metadata'], after['metadata'])
        for name, expected in before['arrays'].items():
            np.testing.assert_array_equal(after['arrays'][name], expected)
        self.assertEqual(sys.path, original_path)
if __name__ == '__main__':
    unittest.main()
