"""Pinned explicit replay of retired v4/v8 shallow-water thin entrypoints."""

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

from tools import single_domain_legacy_entrypoints as legacy


ROOT = Path(__file__).resolve().parents[1]


def replay_case(module):
    fine = module.replay_dependencies["geometry"]
    surface = module.replay_dependencies["surface"]
    canonical = np.zeros((8, 8), np.float64)
    coarse = fine.coarsen_cell_field(canonical, factor=2)
    bed = {"arrays": {"canonical_bed_center_m": canonical, "H2_m": coarse},
           "metadata": {"spacing_m": 2.0}}
    if "reconstruction" in module.replay_dependencies:
        support, datum = module.replay_dependencies["reconstruction"].prepare_support(bed)
    else:
        support, datum = fine.prepare_subgrid_support(bed)
    geometry = surface.prepare_surface_geometry(
        coarse, spacing_m=2.0, origin_m_xz=[0.0, 0.0], source_identity="fixed-flat-replay")
    geometry["arrays"].update(support)
    geometry["metadata"]["hydraulic_datum_m"] = datum
    depth = np.full(coarse.shape, 0.4)
    depth[:, :2] = 0.6
    duration = 0.05
    packets = []
    result = module.advance_shallow_water(
        geometry, initial_depth_m=depth, forcing_interval_s=duration, intervals=2,
        forcing_provider=lambda index: np.zeros_like(coarse),
        boundary_stage_provider=lambda index: np.zeros(2 * sum(coarse.shape)),
        source_identity="fixed-flat-replay", forcing_identity="zero-source-closed-wall",
        budget=surface.SurfaceBudget(max_dt_s=0.01, max_snapshots=3, max_duration_s=1.0,
                                     max_wall_s=10.0),
        snapshot_interval_s=duration, interval_observer=packets.append,
        momentum_observer=lambda packet: None)
    return result, depth, packets


class SingleDomainLegacyEntrypointTests(unittest.TestCase):
    def test_active_v9_import_and_retired_entrypoints_absent(self):
        current = importlib.import_module('terrain_pipeline.shallow_water')
        self.assertTrue(callable(current.advance_shallow_water))
        for version in ("v4", "v8"):
            self.assertFalse((ROOT / "terrain_pipeline" / ("single_domain_shallow_water_" + version + ".py")).exists())
            self.assertIsNone(importlib.util.find_spec("terrain_pipeline.single_domain_shallow_water_" + version))

    def test_loader_import_is_lazy(self):
        script = ("import sys; import tools.single_domain_legacy_entrypoints; "
                  "assert not any(k.startswith('_single_domain_legacy_replay_') for k in sys.modules); "
                  "assert 'terrain_pipeline.single_domain_shallow_water_v4' not in sys.modules; "
                  "assert 'terrain_pipeline.single_domain_shallow_water_v8' not in sys.modules")
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_replay_is_isolated_and_physically_conservative(self):
        import terrain_pipeline.shallow_water as active_support
        for version in ("v4", "v8"):
            with self.subTest(version=version):
                module = legacy.load_legacy_entrypoint(version)
                self.assertIn("legacy-code", module.__file__)
                self.assertTrue(callable(module.advance_shallow_water))
                self.assertNotIn("terrain_pipeline.single_domain_shallow_water_" + version, sys.modules)
                self.assertIs(sys.modules['terrain_pipeline.shallow_water'], active_support)
                self.assertNotEqual(module._advance.__module__, 'terrain_pipeline.shallow_water')
                result, initial, packets = replay_case(module)
                arrays = result["arrays"]
                self.assertEqual(result["metadata"]["hydraulic_model"], module.MODEL)
                self.assertEqual(result["metadata"]["status"], "completed")
                self.assertEqual(len(packets), 2)
                self.assertGreater(result["metadata"]["substeps"], 0)
                self.assertTrue(np.isfinite(arrays["depth_m"]).all())
                self.assertTrue((arrays["depth_m"] >= 0.0).all())
                np.testing.assert_allclose(arrays["time_s"], [0.0, 0.05, 0.1], rtol=0.0, atol=1e-15)
                self.assertLess(float(np.abs(arrays["ledger"][:, -1]).max()), 1e-11)
                self.assertAlmostEqual(float(arrays["depth_m"][-1].sum()), float(initial.sum()), places=12)
                self.assertGreater(float(np.abs(arrays["momentum_x_m2_s"][-1]).max()), 0.0)
                self.assertGreater(float(np.abs(arrays["depth_m"][-1] - initial).max()), 0.0)

    def test_archive_dependency_is_not_loaded_from_live_namespace(self):
        with mock.patch.dict(sys.modules, {'terrain_pipeline.shallow_water': None}):
            module = legacy.load_legacy_entrypoint("v4")
            self.assertTrue(module.shallow_water_rhs.__module__.startswith("_single_domain_legacy_replay_"))
            result, _, _ = replay_case(module)
            self.assertEqual(result["metadata"]["status"], "completed")

    def test_explicit_version_is_required(self):
        for version in (None, "latest", "v9", "../v4"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "explicit legacy"):
                legacy.load_legacy_entrypoint(version)

    def test_modified_source_is_rejected_even_after_successful_load(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "archive"
            shutil.copytree(legacy.ARCHIVE_ROOT, copied)
            with mock.patch.object(legacy, "ARCHIVE_ROOT", copied):
                legacy.load_legacy_entrypoint("v4")
                path = copied / "terrain_pipeline/single_domain_shallow_water_support_v4.py"
                path.write_bytes(path.read_bytes() + b"\n# tampered\n")
                with self.assertRaisesRegex(ValueError, "source sha256 mismatch"):
                    legacy.load_legacy_entrypoint("v4")

    def test_modified_source_and_manifest_are_rejected_together(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "archive"
            shutil.copytree(legacy.ARCHIVE_ROOT, copied)
            manifest_path = copied / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            module = "terrain_pipeline.single_domain_shallow_water_v8"
            record = manifest["files"][module]
            path = copied / record["archive_path"]
            path.write_bytes(path.read_bytes() + b"\n# tampered\n")
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.object(legacy, "ARCHIVE_ROOT", copied):
                with self.assertRaisesRegex(ValueError, "manifest sha256 mismatch"):
                    legacy.load_legacy_entrypoint("v8")


if __name__ == "__main__":
    unittest.main()
