import unittest

from terrain_pipeline.td_fine_bed_material import (
    build_fine_bed_material, load_fine_bed_material, save_fine_bed_material,
    validate_fine_bed_material)


def _inputs():
    paths = {"schema": "td-watershed-paths-v1", "identity_sha256": "a" * 64}
    sections = {"schema": "td-watershed-sections-v1", "identity_sha256": "b" * 64,
                "edge_sections": [], "node_sections": []}
    patches = {"schema": "td-watershed-interface-patch-preparation-v2", "identity_sha256": "c" * 64,
               "patches": []}
    return paths, sections, patches


class FineBedMaterialTests(unittest.TestCase):
    def test_empty_source_is_valid_and_pinned(self):
        record = build_fine_bed_material(*_inputs())
        self.assertEqual(record["summary"]["window_count"], 0)
        self.assertTrue(validate_fine_bed_material(record))

    def test_roundtrip_and_budget_refusal(self):
        paths, sections, patches = _inputs()
        sections["edge_sections"] = [{"arc_id": "a", "cross_section_xyz_m": [[[0., 10., 0.], [1., 9., 0.], [2., 9., 0.], [3., 10., 0.]]]}]
        record = build_fine_bed_material(paths, sections, patches, max_cells_per_window=1, max_total_cells=1)
        self.assertEqual(record["summary"]["refused_count"], 1)
        path = save_fine_bed_material(record, "tests/.fine-bed-material.json")
        self.assertEqual(load_fine_bed_material(path, expected_identity=record["identity_sha256"])["identity_sha256"], record["identity_sha256"])
        path.unlink()

    def test_corridor_ports_are_bound_into_source_identity(self):
        paths, sections, patches = _inputs()
        corridors = {"identity_sha256": "d" * 64,
                     "corridors": [{"status": "candidate",
                                    "centerline_bed_xyz_m": [[0., 10., 0.], [2., 9., 0.]]}]}
        record = build_fine_bed_material(paths, sections, patches, corridors=corridors)
        self.assertEqual(record["source_artifacts"]["corridors_identity_sha256"], "d" * 64)


if __name__ == "__main__":
    unittest.main()
