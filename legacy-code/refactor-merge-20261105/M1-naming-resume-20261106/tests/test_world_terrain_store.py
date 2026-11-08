import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from terrain_pipeline.td_source import make_spec, open_region_registry as open_registry, plan_region_store as plan, prepare_region_store as prepare, read_region_component as read_component
from terrain_pipeline.common_infra import file_sha256
from tools import prepare_world_terrain_region, query_world_terrain_region


class StoreTests(unittest.TestCase):
    def test_old_preparation_revision_requires_new_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = make_spec("lakes")
            forcing = {"runoff_m_per_year": .5, "duration_seconds": 100., "channel_threshold_m3_s": .1}
            registry = open_registry(root, spec, "physical", forcing)
            registry["world"].pop("preparation_revision")
            (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "use a new store"):
                open_registry(root, spec, "physical", forcing)
            registry["world"]["preparation_revision"] = "older"
            (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "use a new store"):
                open_registry(root, spec, "physical", forcing)

    def test_generation_does_not_duplicate_halo_pages(self):
        request = {"origin_native_xz": [464, 464], "shape_zx": [1, 1]}
        support = {"support_origin_native_xz": [446, 446], "missing_mask": np.ones((37, 37), bool)}
        args = SimpleNamespace(source_family="physical-default-v1", model_dir="model", store="store")
        with patch("diffusion.world_demand_backend.run_source_page", return_value={"path": "page", "sha256": "a" * 64}) as run:
            records = prepare_world_terrain_region.generate_page(request, support, args)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [440, 440])
        self.assertEqual(records, [{"path": "page", "sha256": "a" * 64}])

    def test_real_cli_adjacent_regions_and_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "page.npz"
            z, x = np.indices((64, 64))
            elevation = (200. + .3 * x + .1 * z + np.sin(x / 4.)).astype(np.float64)
            metadata = {"schema": "td-native-page-v1", "native_origin": [100, 100],
                        "size": 64, "spacing_m": 30., "world_seed": 20261020}
            np.savez(page, elevation_native=elevation, metadata_json=json.dumps(metadata))
            pages = root / "pages.json"
            pages.write_text(json.dumps([{"path": str(page), "sha256": file_sha256(page)}]), encoding="utf-8")
            store = root / "store"
            common = ["--store", str(store), "--source-family", "physical-default-v1", "--sigma-cells", "1",
                      "--runoff-m-per-year", ".5", "--duration-seconds", "86400",
                      "--channel-threshold-m3-s", ".000001"]
            with contextlib.redirect_stdout(io.StringIO()):
                prepare_world_terrain_region.main(common + ["--pages-json", str(pages),
                    "--origin", "116", "128", "--shape", "12", "12"])
                prepare_world_terrain_region.main(common + ["--origin", "128", "128", "--shape", "12", "12"])
            registry = json.loads((store / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(len(registry["components"]), 1)
            self.assertEqual(registry["prepared_cells"], 288)
            arrays, meta = read_component(store, registry["components"][0], registry["world_identity"])
            cols = np.arange(116, 140)[None, :]
            crosses = (arrays["receiver"] >= 0) & (((cols < 128) & (arrays["receiver_native_x"] >= 128)) |
                                                   ((cols >= 128) & (arrays["receiver_native_x"] < 128)))
            self.assertTrue(crosses.any())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                query_world_terrain_region.main([str(store), "--native-xz", "128", "130"])
            result = json.loads(output.getvalue())
            self.assertIn("receiver_native_x", result["values"])
            self.assertIn("spill_receiver_native_x", result["values"])
            self.assertIn("basin_transfer_links", result)

    def test_merge_resume_failure_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = make_spec("lakes")
            forcing = {"runoff_m_per_year": .5, "duration_seconds": 100., "channel_threshold_m3_s": .1}
            registry = open_registry(root, spec, "physical", forcing)
            calls = []
            def coverage(origin, shape, pages):
                return {"missing_cells": 0}
            def compose(spec, pages, origin, shape, **kwargs):
                calls.append((origin, shape))
                return {"composed_elevation_m": np.ones(shape), "metadata": {}}
            def form(composition, origin, **kwargs):
                return {"arrays": {"final_bed_m": composition["composed_elevation_m"]},
                        "metadata": {}, "identity_sha256": "water"}
            def render(arrays, origin, path):
                path.write_bytes(b"image")
            first_plan = plan(registry, [10, 20], [3, 4], [], coverage)
            first = prepare(root, registry, first_plan, [], spec, compose=compose, form=form, render=render)
            hit = plan(registry, [11, 21], [1, 1], [], coverage)
            self.assertEqual(prepare(root, registry, hit, [], spec, compose=compose, form=form, render=render), first)
            self.assertEqual(len(calls), 1)
            joined = plan(registry, [14, 20], [3, 2], [], coverage)
            second = prepare(root, registry, joined, [], spec, compose=compose, form=form, render=render)
            self.assertEqual(calls[-1], ([10, 20], [3, 6]))
            self.assertTrue((root / "versions" / first["version"]).is_dir())
            self.assertEqual(registry["prepared_cells"], 18)
            arrays, _ = read_component(root, second, registry["world_identity"])
            self.assertEqual(arrays["final_bed_m"].shape, (3, 6))
            with self.assertRaises(ValueError):
                open_registry(root, spec, "other", forcing)
            before = (root / "registry.json").read_bytes()
            pending = plan(registry, [16, 20], [3, 2], [], coverage)
            def fail(*args, **kwargs):
                raise RuntimeError("failed")
            with self.assertRaises(RuntimeError):
                prepare(root, registry, pending, [], spec, compose=compose, form=fail, render=render)
            self.assertEqual((root / "registry.json").read_bytes(), before)
            metadata_path = root / "versions" / second["version"] / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["world_identity"] = "wrong"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_component(root, second, registry["world_identity"])


if __name__ == "__main__":
    unittest.main()
