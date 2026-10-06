from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.td_fine_bed_raster import build_fine_bed_raster, _digest, _shape
from terrain_pipeline.td_fine_bed_shards import (
    BYTE_REASON, build_fine_bed_shards, iter_merged_cells, load_fine_bed_shards,
    save_fine_bed_shards, validate_fine_bed_shards)


def fixture():
    arrays = {"height_m": np.full((6, 6), 10.), "valid_mask": np.ones((6, 6), bool),
              "protected_mask": np.zeros((6, 6), bool), "open_boundary_mask": np.zeros((6, 6), bool),
              "cell_owner": np.zeros((6, 6), np.int64), "contribution_owner": np.zeros((6, 6), np.int64),
              "node_unknown_contact": np.zeros(1, bool)}
    metadata = {"origin_m_xz": [0., 0.], "spacing_m": 1., "source_identity_sha256": "a" * 64}
    hierarchy = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    sections = {"schema": "td-watershed-sections-v1", "identity_sha256": "b" * 64,
                "source_identity_sha256": "a" * 64, "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                "selected_leaf_ids": [0], "node_sections": [{"node_id": "first", "width_m": 2.},
                                                             {"node_id": "second", "width_m": 2.}],
                "edge_sections": [{"arc_id": "receiver:1:2", "node_ids": ["first", "second"],
                                   "triangle_indices": [0]}],
                "mesh": {"vertices_xyz_m": [[.5, 9., .5], [1.5, 9., .5], [.5, 9., 1.5]],
                         "triangles": [[0, 1, 2]], "triangle_arc_ids": ["receiver:1:2"]}}
    base = build_fine_bed_raster(hierarchy, sections, fine_spacing_m=.5, tile_cells=2)
    for entry_index, points in ((3, [[.5, 8., .5], [1.5, 8., .5], [.5, 8., 1.5]]),
                                (4, [[2.5, 9., .5], [3.5, 9., .5], [2.5, 9., 1.5]])):
        base["triangles"].append({"triangle_id": f"09:{entry_index}:0", "source_package": "09",
            "source_entry_index": entry_index, "source_triangle_index": 0, "source_vertex_indices": [0, 1, 2],
            "vertices_xyz_m": points, "status": "refused", "rejection_reasons": [BYTE_REASON]})
    base["selection"]["selected_09_entry_indices"] = [3, 4]
    base["selection"]["selected_09_triangle_count"] = 2
    base["selection"]["identity_sha256"] = _digest({key: value for key, value in base["selection"].items()
                                                    if key != "identity_sha256"})
    base["shape_identity_sha256"] = _digest(_shape(base))
    base["identity_sha256"] = _digest({key: value for key, value in base.items() if key != "identity_sha256"})
    return base, hierarchy


class FineBedShardTests(unittest.TestCase):
    def test_incremental_unique_ownership_conflict_delta_and_roundtrip(self):
        base, hierarchy = fixture()
        saved_parent = deepcopy(base)
        package = build_fine_bed_shards(base, hierarchy, max_transactions_per_shard=1, max_shard_bytes=8192)
        self.assertEqual(base, saved_parent)
        self.assertEqual(package["raw"]["summary"]["retried_triangles"], 2)
        self.assertEqual(package["manifest"]["summary"]["replace_transactions"], 3)
        self.assertEqual(package["manifest"]["summary"]["insert_transactions"], 3)
        self.assertEqual(package["manifest"]["summary"]["merged_cells"], 6)
        self.assertEqual(package["manifest"]["summary"]["shard_count"], 6)
        merged = list(iter_merged_cells(base, package["shards"]))
        self.assertEqual(len({key for key, cell, owner in merged}), 6)
        refused = [(key, cell, owner) for key, cell, owner in merged if cell["status"] == "refused"]
        self.assertEqual(len(refused), 3)
        self.assertTrue(all(owner == "shard0" and "conflicting_triangle_overlap" in cell["rejection_reasons"]
                            and cell["derived_bed_m"] == cell["source_sample"]["height_m"]
                            for key, cell, owner in refused))
        self.assertAlmostEqual(package["manifest"]["material_ledger_merged"]["cut_rock_m3"], .75)
        self.assertEqual(package["manifest"]["material_ledger_merged"]["sediment_pore_m3"], 0.)
        validate_fine_bed_shards(package, base, hierarchy)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery"
            save_fine_bed_shards(package, path)
            manifest_path = path / "manifest.json"
            loaded = load_fine_bed_shards(path, expected_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                expected_manifest_identity=package["manifest"]["identity_sha256"], base=base, hierarchy=hierarchy)
            self.assertEqual(loaded, package)
        broken = deepcopy(package)
        broken["shards"][0]["transactions"][0]["before_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            validate_fine_bed_shards(broken, base)

    def test_budget_refusal_keeps_parent_and_pending_triangle_indices(self):
        base, hierarchy = fixture()
        package = build_fine_bed_shards(base, hierarchy, max_cells=3)
        self.assertEqual(package["manifest"]["summary"]["merged_cells"], 3)
        self.assertEqual(package["manifest"]["summary"]["insert_transactions"], 0)
        self.assertEqual(package["raw"]["summary"]["still_refused_triangles"], 1)
        self.assertFalse(package["manifest"]["missing_coverage_complete"])
        pending = [triangle for triangle in package["raw"]["triangles"] if triangle["status"] == "refused"]
        self.assertEqual(pending[0]["triangle_id"], "09:4:0")
        self.assertEqual(pending[0]["source_entry_index"], 4)
        self.assertEqual(pending[0]["source_triangle_index"], 0)
        self.assertEqual(package["manifest"]["material_ledger_merged"]["cut_rock_m3"], 0.)
        self.assertFalse(package["manifest"]["hydraulic_ready"])
        with self.assertRaises(MemoryError):
            build_fine_bed_shards(base, hierarchy, max_cells=2)


if __name__ == "__main__":
    unittest.main()
