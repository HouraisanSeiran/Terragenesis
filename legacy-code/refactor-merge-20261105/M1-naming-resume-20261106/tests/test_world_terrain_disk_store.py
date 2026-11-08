import tempfile
import unittest
import contextlib
import io
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.td_source import open_disk_registry as open_registry, plan_disk_region as plan, prepare_disk_region as prepare, read_disk_manifest as read_manifest
from terrain_pipeline.td_source import make_spec
from tools.query_world_terrain_region import main as query


class DiskStoreTests(unittest.TestCase):
    def test_real_solver_expansion_order_matches(self):
        from terrain_pipeline.drainage import solve_disk_region as solve_disk_region
        with tempfile.TemporaryDirectory() as directory:
            spec = make_spec("lakes")
            forcing = {"runoff_m_per_year": .5, "duration_seconds": 86400.,
                       "channel_threshold_m3_s": .00001, "min_lake_area_m2": 10000.}
            def compose(spec, pages, origin, shape, **kwargs):
                z, x = np.indices(shape)
                bed = 100. + (x + origin[0]) * .1 + (z + origin[1]) * .02
                return {"composed_elevation_m": bed, "ocean_mask": None, "metadata": {}}
            results = []
            for index, origins in enumerate((([100, 100], [112, 100]), ([112, 100], [100, 100]))):
                root = Path(directory) / str(index)
                registry = open_registry(root, spec, "physical", forcing, 1.)
                for origin in origins:
                    request = plan(registry, origin, [24, 12])
                    component = prepare(root, registry, request, [], spec, compose=compose, solve=solve_disk_region)
                path, manifest = read_manifest(root, component, registry["world_identity"])
                tile = manifest["water_tiles"][0]
                with np.load(path / tile["file"], allow_pickle=False) as archive:
                    results.append({name: archive[name] for name in archive.files})
            self.assertEqual(results[0].keys(), results[1].keys())
            for name in results[0]:
                np.testing.assert_array_equal(results[0][name], results[1][name])

    def test_tiled_inputs_and_failed_solve_preserves_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = make_spec("lakes")
            forcing = {"runoff_m_per_year": 1., "duration_seconds": 100., "channel_threshold_m3_s": .1}
            registry = open_registry(root, spec, "physical", forcing, 6.)
            request = plan(registry, [100, 100], [520, 520])
            calls = []
            def compose(spec, pages, origin, shape, **kwargs):
                calls.append((origin, shape))
                return {"composed_elevation_m": np.ones(shape), "ocean_mask": None, "metadata": {}}
            def solve(height, ocean, work, **kwargs):
                self.assertEqual(np.load(height, mmap_mode="r").shape, (520, 520))
                self.assertFalse(np.load(ocean, mmap_mode="r").any())
                work.mkdir()
                field = work / "receiver_native_x.npy"
                np.save(field, np.zeros((520, 520), dtype=np.int64))
                return {"fields": {"receiver_native_x": field.name}, "metadata": {"algorithm": "test"}}
            component = prepare(root, registry, request, [], spec, compose=compose, solve=solve)
            self.assertEqual(len(calls), 4)
            _, manifest = read_manifest(root, component, registry["world_identity"])
            self.assertEqual(len(manifest["composition_tiles"]), 4)
            for coordinate in ([611, 611], [612, 612]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    query([str(root), "--native-xz", *map(str, coordinate)])
                self.assertEqual(json.loads(output.getvalue())["values"]["receiver_native_x"], 0)
            hit = plan(registry, [100, 100], [1, 1])
            self.assertEqual(prepare(root, registry, hit, [], spec, compose=compose, solve=solve), component)
            before = (root / "registry.json").read_bytes()
            extension = plan(registry, [620, 100], [2, 2])
            count = 0
            def fail_compose(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 2:
                    raise RuntimeError("second tile failed")
                return compose(*args, **kwargs)
            with self.assertRaisesRegex(RuntimeError, "second tile failed"):
                prepare(root, registry, extension, [], spec, compose=fail_compose, solve=solve)
            self.assertEqual((root / "registry.json").read_bytes(), before)
            def fail(*args, **kwargs):
                raise RuntimeError("solver failure")
            with self.assertRaises(RuntimeError):
                prepare(root, registry, extension, [], spec, compose=compose, solve=fail)
            self.assertEqual(before, (root / "registry.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
