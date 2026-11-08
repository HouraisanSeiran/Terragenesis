import copy
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.hydrology_detail import DetailBudget
from terrain_pipeline.hydrology_planning import load_plan
from tools import prepare_hydrology_domains as entry


class ProjectionSourcePreparationTests(unittest.TestCase):
    def test_channel_candidate_versions_route_explicit_policies_and_cache_identities(self):
        from terrain_pipeline.hydrology_detail_tributary_finite import CHANNEL_NETWORK_ALGORITHM, HARMONIC_CHANNEL_ALGORITHM, HARMONIC_CHANNEL_TARGET_WITNESS_ALGORITHM
        from terrain_pipeline.hydrology_detail_projection import MACRO_WITNESS_POLICY, TARGET_WITNESS_POLICY
        for version, target, algorithm, witness in (("finite-network-v3-channel-feasibility", None, CHANNEL_NETWORK_ALGORITHM, MACRO_WITNESS_POLICY),
                                            ("finite-network-v4-harmonic-channel", "harmonic-boundary-residual-v1", HARMONIC_CHANNEL_ALGORITHM, MACRO_WITNESS_POLICY),
                                            ("finite-network-v5-harmonic-channel-target-witness", "harmonic-boundary-residual-v1", HARMONIC_CHANNEL_TARGET_WITNESS_ALGORITHM, TARGET_WITNESS_POLICY)):
            with self.subTest(version=version), patch("terrain_pipeline.hydrology_detail_tributary_finite.prepare_finite_tributary_source", return_value="candidate") as prepare:
                self.assertEqual(entry._owned_full_window_source({}, "unused", "river", DetailBudget(), None, version), "candidate")
                self.assertEqual(prepare.call_args.kwargs["channel_feasibility_policy"], "frozen-channel-feasibility-v1")
                self.assertEqual(prepare.call_args.kwargs["target_policy"], target)
                self.assertEqual(prepare.call_args.kwargs["witness_policy"], witness)
                self.assertEqual(entry._projection_algorithm(version), algorithm)
                self.assertEqual(entry._projection_tag(version), version)

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.formal = cls.root / "verification/hydrological-planning-domain/formal-03"
        cls.plan = load_plan(cls.root / "verification/hydrological-planning-domain/dev-05/catalog/plan_0_-5.npz")

    def frozen_river(self, directory):
        directory = Path(directory)
        (directory / "river").mkdir()
        shutil.copyfile(self.formal / "collection-plan.json", directory / "collection-plan.json")
        shutil.copyfile(self.formal / "river/detail-plan.json", directory / "river/detail-plan.json")
        return directory

    def test_cpu_declaration_needs_no_original_or_confluence_and_freezes_exact_fifteen_tiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.frozen_river(temporary)
            with patch.object(entry, "CanonicalTDSource", side_effect=AssertionError("backend must not be created")):
                result = entry.prepare_projection_source(self.plan, output, window_kind="river", generate=False)
            declaration = json.loads(Path(result["source_declaration"]).read_text(encoding="utf-8"))
            expected = [[x, z] for x in range(18, 23) for z in range(-180, -177)]
            self.assertEqual(declaration["required_source_tile_xz"], expected)
            self.assertEqual(declaration["owned_core_tile_xz"], [[19, -179], [20, -179]])
            self.assertEqual(len(declaration["required_coarse_node_zx"]), 12)
            self.assertEqual(declaration["canonical_source_identity"], "4102caeb9b9ca22409c3f1f9e9f9e583e5f00bcd91beb2374dc1373ad7dd411a")
            self.assertFalse(result["model_inference_run"])
            self.assertFalse((output / "confluence").exists())
            self.assertFalse((output / "river/river-original-td.npz").exists())

    def test_selected_scope_and_plan_mismatch_fail_before_backend_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.frozen_river(temporary)
            with self.assertRaisesRegex(ValueError, "no frozen planned location"):
                entry.projection_source_declaration(self.plan, output, "confluence")
            bad_plan = copy.copy(self.plan)
            bad_plan["identity_sha256"] = "different"
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                entry.projection_source_declaration(bad_plan, output, "river")
            with self.assertRaisesRegex(ValueError, "selected river original detail is not prepared"):
                entry.prepare_canonical_projection(self.plan, output, DetailBudget(), 526.2816108585628, "river")
            path = output / "river/detail-plan.json"
            declared = json.loads(path.read_text(encoding="utf-8"))
            declared["canonical_source_identity"] = "different-source"
            path.write_text(json.dumps(declared), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical source contract mismatch"):
                entry.projection_source_declaration(self.plan, output, "river")

    def test_explicit_preparation_consumes_same_declaration_and_preserves_existing_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.frozen_river(temporary)
            cache = output / "cache"
            declaration = entry.projection_source_declaration(self.plan, output, "river")
            identity = declaration["canonical_source_identity"]
            tile_root = cache / identity / "3"
            tile_root.mkdir(parents=True)
            preserved = tile_root / "tile-x18-z-180.npz"
            preserved.write_bytes(b"immutable-existing-source")
            calls, sources = [], []

            class FakeSource:
                def __init__(self, backend, cache_root):
                    self.identity = identity
                    self.cache_root = cache_root / identity
                    self.closed = False
                    sources.append(self)
                    self.declaration_at_creation = list(output.glob("projection-source-preparation-*.json"))

                def _tile(self, seed, tx, tz):
                    calls.append([tx, tz])
                    path = self.cache_root / str(seed) / f"tile-x{tx}-z{tz}.npz"
                    if not path.exists():
                        path.write_bytes(b"synthetic-test-source")

                def generate(self, seed, x, z, size):
                    self_test.assertEqual(size, 2)
                    elevation = np.array([[x + z, x + z + 1], [x + z + 1, x + z + 2]], float)
                    return elevation, np.zeros((5, 2, 2)), {"identity": identity, "seed": str(seed), "native_origin": [x, z], "shape": [2, 2]}

                def close(self):
                    self.closed = True

            self_test = self
            release = []
            fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda: release.append(True)))
            with patch.object(entry, "CANONICAL_CACHE", cache), patch.object(entry, "CanonicalTDSource", FakeSource), \
                    patch.object(entry, "ResourcePhysicalTerrainDiffusionBackend", return_value=object()) as backend, \
                    patch("diffusion.paths.configure"), patch.object(entry.time, "sleep") as pause, \
                    patch.dict(sys.modules, {"torch": fake_torch}):
                first = entry.prepare_projection_source(self.plan, output, window_kind="river")
                second = entry.prepare_projection_source(self.plan, output, window_kind="river")
            self.assertEqual(calls[:15], declaration["required_source_tile_xz"])
            self.assertEqual(len(first["generated_tile_xz"]), 14)
            self.assertEqual(second["generated_tile_xz"], [])
            self.assertEqual(first["source_declaration"], second["source_declaration"])
            self.assertEqual(first["resource_settings"]["threads"], 2)
            self.assertTrue(all(source.closed and source.declaration_at_creation for source in sources))
            self.assertTrue(all(call.args[1] == "light" for call in backend.call_args_list))
            self.assertEqual(pause.call_count, 14)
            self.assertTrue(all(call.args == (5.0,) for call in pause.call_args_list))
            self.assertEqual(len(release), 14)
            self.assertEqual(preserved.read_bytes(), b"immutable-existing-source")
            self.assertEqual(len(list((output / "canonical-projection-td-nodes").glob("*.json"))), 12)
            self.assertFalse((output / "river/river-original-td.npz").exists())


if __name__ == "__main__":
    unittest.main()
