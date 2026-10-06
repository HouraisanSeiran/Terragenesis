import copy
import json
import tempfile
import unittest
from pathlib import Path

from terrain_pipeline.td_watershed_interface_patches import (
    build_watershed_interface_patches,
    load_watershed_interface_patches,
    save_watershed_interface_patches,
    validate_watershed_interface_patches,
)


def _fixture():
    nodes = []
    sections = []
    for cell, xyz in ((0, [0., 10., 0.]), (1, [10., 9., 0.]), (2, [0., 10., 10.]), (3, [10., 9., 10.])):
        node_id = f"cell:{cell}"
        nodes.append({"node_id": node_id, "cell_id": cell, "xyz_m": xyz,
                      "kinds": ["confluence"] if cell == 1 else [], "leaf_id": 0})
        cross = [[xyz[0] - 2., xyz[1], xyz[2] - 2.], [xyz[0] - 1., xyz[1] - 1., xyz[2] - 1.],
                 [xyz[0] + 1., xyz[1] - 1., xyz[2] + 1.], [xyz[0] + 2., xyz[1], xyz[2] + 2.]]
        sections.append({"node_id": node_id, "source_xyz_m": xyz, "bed_m": xyz[1] - (0. if cell == 0 else .5),
                         "width_m": 4., "depth_m": 0. if cell == 0 else .5,
                         "cross_section_xyz_m": cross, "anchor": cell == 0, "junction": cell == 1,
                         "rejection_reasons": ["anchor_cut_conflict"] if cell == 0 else ["needs_junction_patch"]})
    arcs = [{"arc_id": "a0", "kind": "land_channel", "node_ids": ["cell:0", "cell:1"], "cell_ids": [0, 1]},
            {"arc_id": "a1", "kind": "land_channel", "node_ids": ["cell:2", "cell:1"], "cell_ids": [2, 1]},
            {"arc_id": "a2", "kind": "land_channel", "node_ids": ["cell:3", "cell:1"], "cell_ids": [3, 1]}]
    paths = {"schema": "td-watershed-paths-v1", "source_identity_sha256": "source",
             "hierarchy_identity_sha256": "hierarchy", "topology_identity_sha256": "topology",
             "ordinary_identity_sha256": "ordinary", "identity_sha256": "paths", "nodes": nodes, "arcs": arcs}
    record = {"schema": "td-watershed-sections-v1", "identity_sha256": "sections", "node_sections": sections}
    return paths, record


class WatershedInterfacePatchTests(unittest.TestCase):
    def test_build_has_explicit_candidates_and_rejections(self):
        paths, sections = _fixture()
        result = build_watershed_interface_patches(paths, sections)
        validate_watershed_interface_patches(result)
        self.assertTrue(result["patches"])
        self.assertTrue(all(item["parametric_only"] for item in result["patches"]))
        self.assertEqual(result["bed_changed"], False)

    def test_tampered_geometry_is_rejected(self):
        paths, sections = _fixture()
        result = build_watershed_interface_patches(paths, sections)
        result["patches"][0]["endpoint_xyz_m"][0][0] += 1.
        with self.assertRaises(ValueError):
            validate_watershed_interface_patches(result)

    def test_save_load_hash(self):
        paths, sections = _fixture()
        result = build_watershed_interface_patches(paths, sections)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "patches.json"
            save_watershed_interface_patches(result, target)
            loaded = load_watershed_interface_patches(target, expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
