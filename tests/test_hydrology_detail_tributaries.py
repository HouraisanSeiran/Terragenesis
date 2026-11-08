import copy
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.hydrology_detail_tributaries import (
    freeze_local_tributary_confluence, load_local_tributary_sidecar, save_local_tributary_sidecar,
    validate_local_tributary_sidecar, validate_local_tributary_source_edges,
    build_local_tributary_window, prepare_local_tributary_source_declaration,
    prepare_local_tributary_original,
)


def fixture():
    height = np.full((4, 4), 10.)
    height.ravel()[[0, 1, 5, 6, 7]] = [5., 6., 3., 2., -1.]
    receiver = np.full((4, 4), -1, dtype=np.int64)
    receiver.ravel()[[0, 1, 5, 6]] = [5, 5, 6, 7]
    owner = np.zeros((4, 4), dtype=np.int32)
    owner.ravel()[7] = -1
    area = np.zeros((4, 4))
    area.ravel()[[0, 1, 5, 6]] = [2., 3., 6., 7.]
    ocean = owner == -1
    return {"identity_sha256": "immutable-fixture", "height_m": height, "receiver": receiver,
            "owner_domain_id": owner, "ocean_mask": ocean, "accumulation_area_m2": area,
            "river_mask": area >= 3., "river_threshold_area_m2": 3., "spacing_m": 1.,
            "origin_xz_m": [0., 0.], "domains": [{"domain_id": 0, "kind": "coastal", "terminal_indices": [7]}]}


class LocalTributaryTests(unittest.TestCase):
    def freeze(self, plan, lake_mask=None):
        mask = np.zeros((4, 4), bool) if lake_mask is None else lake_mask
        return freeze_local_tributary_confluence(plan, junction_id=5, incoming_ids=[1, 0],
                                                 highest_lake_level_m=4., lake_mask=mask)

    def preparation_fixture(self):
        plan = fixture()
        plan.update(seed=3, spacing_m=10000., origin_xz_m=[340000., -1430000.])
        return plan, self.freeze(plan), np.zeros((4, 4), bool)

    def test_native_window_uses_global_floor_and_fixed_junction(self):
        plan, declaration, mask = self.preparation_fixture()
        window = build_local_tributary_window(plan, declaration, highest_lake_level_m=4., lake_mask=mask)
        self.assertEqual(window["native_origin_xz"], [11618, -47382])
        self.assertEqual(window["origin_xz_m"], [348540., -1421460.])
        self.assertEqual(window["shape"], [97, 97])
        self.assertEqual(window["declared_source_edge_cell_ids"], [[0, 5], [1, 5], [5, 6]])
        self.assertEqual(window["local_tributary_sidecar_identity_sha256"], declaration["identity_sha256"])

    def test_cpu_declaration_binds_budget_and_dependency_bound(self):
        from terrain_pipeline.hydrology_detail import DetailBudget
        plan, declaration, mask = self.preparation_fixture()
        budget = DetailBudget(512., 516., 4.5e9, 4.51e9, 4.)
        with TemporaryDirectory() as folder:
            report = prepare_local_tributary_source_declaration(plan, declaration, folder,
                budget=budget, highest_lake_level_m=4., lake_mask=mask)
            self.assertEqual(report["status"], "declared_no_inference")
            self.assertFalse(report["model_inference_run"])
            self.assertLessEqual(len(report["required_source_tile_xz"]), 15)
            collection = json.loads(Path(report["collection_path"]).read_text(encoding="utf-8"))
            detail = json.loads(Path(report["detail_plan_path"]).read_text(encoding="utf-8"))
            self.assertEqual(collection["local_tributary_sidecar"], declaration)
            self.assertEqual(collection["budget"], asdict(budget))
            self.assertEqual(detail["windows"], collection["windows"])
            repeat = prepare_local_tributary_source_declaration(plan, declaration, folder,
                budget=budget, highest_lake_level_m=4., lake_mask=mask)
            self.assertEqual(report, repeat)
            with self.assertRaisesRegex(ValueError, "dependency bound"):
                prepare_local_tributary_source_declaration(plan, declaration, Path(folder) / "bounded",
                    budget=budget, highest_lake_level_m=4., lake_mask=mask, maximum_source_tiles=1)

    def test_missing_cache_returns_before_backend_creation(self):
        from terrain_pipeline.hydrology_detail import DetailBudget
        plan, declaration, mask = self.preparation_fixture()
        with TemporaryDirectory() as folder, patch(
                "terrain_pipeline.hydrology_detail_conditioning.ResourcePhysicalTerrainDiffusionBackend") as backend:
            report = prepare_local_tributary_original(plan, declaration, Path(folder) / "output",
                budget=DetailBudget(), highest_lake_level_m=4., lake_mask=mask,
                canonical_cache_root=Path(folder) / "empty-cache")
            self.assertEqual(report["status"], "source_unprepared")
            self.assertFalse(report["backend_created"])
            self.assertFalse(report["model_inference_run"])
            self.assertEqual(len(report["missing_source_tiles"]), len(report["required_source_tile_xz"]))
            backend.assert_not_called()

    def test_cache_pin_mismatch_rejected_before_backend_creation(self):
        from terrain_pipeline.hydrology_detail import DetailBudget
        plan, declaration, mask = self.preparation_fixture()
        with TemporaryDirectory() as folder, patch(
                "terrain_pipeline.hydrology_detail_conditioning.ResourcePhysicalTerrainDiffusionBackend") as backend:
            output, cache = Path(folder) / "output", Path(folder) / "cache"
            report = prepare_local_tributary_source_declaration(plan, declaration, output,
                budget=DetailBudget(), highest_lake_level_m=4., lake_mask=mask)
            detail = json.loads(Path(report["detail_plan_path"]).read_text(encoding="utf-8"))
            tile_folder = cache / detail["canonical_source_identity"] / "3"
            tile_folder.mkdir(parents=True)
            tx, tz = report["required_source_tile_xz"][0]
            tile = tile_folder / f"tile-x{tx}-z{tz}.npz"
            tile.write_bytes(b"invalid cached source")
            tile.with_suffix(".sha256").write_text("0" * 64, encoding="ascii")
            with self.assertRaisesRegex(ValueError, "pin mismatch"):
                prepare_local_tributary_original(plan, declaration, output, budget=DetailBudget(),
                    highest_lake_level_m=4., lake_mask=mask, canonical_cache_root=cache)
            backend.assert_not_called()

    def test_true_receiver_edges_parent_and_mask_unchanged(self):
        plan = fixture()
        original = copy.deepcopy(plan)
        declaration = self.freeze(plan)
        self.assertEqual([record["source_edge"] for record in declaration["edges"]], [[0, 5], [1, 5], [5, 6]])
        self.assertEqual(declaration["edges"][0]["category"], "subthreshold_local_tributary_edge")
        self.assertEqual(declaration["downstream_receiver_chain"], [5, 6, 7])
        self.assertEqual(declaration["status"], "frozen_geometry_unverified")
        self.assertFalse(declaration["fine_geometry_certified"])
        for key in ("receiver", "river_mask", "height_m", "owner_domain_id", "accumulation_area_m2"):
            np.testing.assert_array_equal(plan[key], original[key])
        self.assertEqual(plan["identity_sha256"], original["identity_sha256"])
        self.assertEqual(plan["river_threshold_area_m2"], 3.)

    def test_illegal_edge_and_cross_owner_rejected(self):
        plan = fixture()
        with self.assertRaises(ValueError):
            freeze_local_tributary_confluence(plan, junction_id=5, incoming_ids=[0, 2],
                                              highest_lake_level_m=4., lake_mask=np.zeros((4, 4), bool))
        plan["owner_domain_id"].ravel()[6] = 1
        with self.assertRaises(ValueError):
            self.freeze(plan)

    def test_submerged_and_unknown_terminal_rejected(self):
        mask = np.zeros((4, 4), bool)
        mask.ravel()[5] = True
        with self.assertRaisesRegex(ValueError, "submerged"):
            self.freeze(fixture(), mask)
        plan = fixture()
        plan["ocean_mask"].ravel()[7] = False
        with self.assertRaisesRegex(ValueError, "marine terminal"):
            self.freeze(plan)
        plan = fixture()
        plan["owner_domain_id"].ravel()[7] = -2
        with self.assertRaisesRegex(ValueError, "unknown owner"):
            self.freeze(plan)

    def test_cycles_and_tampering_rejected(self):
        plan = fixture()
        declaration = self.freeze(plan)
        tampered = copy.deepcopy(declaration)
        tampered["edges"][0]["source_edge"] = [2, 5]
        with self.assertRaises(ValueError):
            validate_local_tributary_sidecar(plan, tampered, highest_lake_level_m=4., lake_mask=np.zeros((4, 4), bool))
        plan["receiver"].ravel()[6] = 5
        with self.assertRaises(ValueError):
            self.freeze(plan)

    def test_explicit_fine_nodes_and_immutable_save(self):
        plan = fixture()
        declaration = self.freeze(plan)
        mask = np.zeros((4, 4), bool)
        verified = validate_local_tributary_source_edges(plan, declaration, [[0, 5], [1, 5], [5, 6]],
                                                         highest_lake_level_m=4., lake_mask=mask)
        self.assertFalse(verified["fine_geometry_certified"])
        with self.assertRaises(ValueError):
            validate_local_tributary_source_edges(plan, declaration, [[6, 7]], highest_lake_level_m=4., lake_mask=mask)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "declaration.json"
            save_local_tributary_sidecar(declaration, path)
            self.assertEqual(load_local_tributary_sidecar(plan, path, highest_lake_level_m=4., lake_mask=mask), declaration)
            with self.assertRaises(FileExistsError):
                save_local_tributary_sidecar(declaration, path)

    def test_fine_bed_requires_explicit_sidecar_for_subthreshold_edge(self):
        from terrain_pipeline.hydrology_detail import DetailBudget
        from terrain_pipeline.channel_geometry import derive_continuous_bed
        plan = fixture()
        declaration = self.freeze(plan)
        detail = {"arrays": {"derived_height_m": plan["height_m"], "original_td_m": plan["height_m"],
                              "owner_domain_id": plan["owner_domain_id"], "ocean_mask": plan["ocean_mask"],
                              "shared_boundary_protected": np.zeros((4, 4), bool)},
                  "metadata": {"origin_xz_m": [0., 0.], "spacing_m": 1., "plan_identity": plan["identity_sha256"],
                               "identity": "b" * 64, "budget": asdict(DetailBudget())}}
        arguments = {"frozen_plan": plan, "node_source_edges": [[0, 5], [0, 5]],
                     "node_edge_fractions": [0., 1.]}
        with self.assertRaisesRegex(ValueError, "frozen river"):
            derive_continuous_bed(detail, [[0., 0.], [1., 1.]], [1, -1], [4., 4.], [5., 3.], **arguments)
        # The tiny fixture cannot certify a 4m-wide bed, but the explicit valid
        # declaration must reach geometric rejection instead of the river gate.
        result = derive_continuous_bed(detail, [[0., 0.], [1., 1.]], [1, -1], [4., 4.], [5., 3.],
            tributary_declaration=declaration, highest_lake_level_m=4., lake_mask=np.zeros((4, 4), bool), **arguments)
        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("frozen river", result["reason"])
        tampered = copy.deepcopy(declaration)
        tampered["edges"][0]["source_edge"] = [2, 5]
        with self.assertRaises(ValueError):
            derive_continuous_bed(detail, [[0., 0.], [1., 1.]], [1, -1], [4., 4.], [5., 3.],
                tributary_declaration=tampered, highest_lake_level_m=4., lake_mask=np.zeros((4, 4), bool), **arguments)


if __name__ == "__main__":
    unittest.main()
