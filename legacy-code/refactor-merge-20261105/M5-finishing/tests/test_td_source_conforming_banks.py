from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.td_fine_bed_raster import build_fine_bed_raster, _context
from terrain_pipeline.td_fine_bed_shards import build_fine_bed_shards, iter_merged_cells
from terrain_pipeline.channel_geometry import _proof, _segments, _line_key, _function, build_source_conforming_banks, load_source_conforming_banks, save_source_conforming_banks, validate_source_conforming_banks


def fixture():
    rows, columns = np.indices((5, 5))
    arrays = {"height_m": 10. - .5 * rows * columns,
              "valid_mask": np.ones((5, 5), bool), "protected_mask": np.zeros((5, 5), bool),
              "open_boundary_mask": np.zeros((5, 5), bool), "cell_owner": np.zeros((5, 5), np.int64),
              "contribution_owner": np.zeros((5, 5), np.int64), "node_unknown_contact": np.zeros(1, bool)}
    metadata = {"origin_m_xz": [0., 0.], "spacing_m": 1., "source_identity_sha256": "a" * 64}
    hierarchy = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}

    def profile(z_m, locations, cuts):
        return [[x_m, 10. - .5 * x_m * z_m - cut, z_m] for x_m, cut in zip(locations, cuts)]

    four = [.5, .75, 1.25, 1.5]
    profiles = [profile(z_m, four, [0., .01, .01, 0.]) for z_m in (0., .5, 1.5)]
    vertices = [point for row in profiles for point in row]
    triangles = []
    for strip in range(2):
        for column in range(3):
            first = strip * 4 + column
            triangles.extend([[first, first + 1, first + 4], [first + 1, first + 5, first + 4]])
    sections = {"schema": "td-watershed-sections-v1", "identity_sha256": "b" * 64, "source_identity_sha256": "a" * 64,
                "hierarchy_identity_sha256": hierarchy["identity_sha256"], "selected_leaf_ids": [0],
                "ordinary_identity_sha256": "e" * 64,
                "node_sections": [{"node_id": node, "width_m": .5, "representative_q_m3_s": .01}
                                  for node in ("upstream", "port", "anchor")],
                "edge_sections": [{"arc_id": "legacy", "node_ids": ["upstream", "port"],
                                   "cross_section_xyz_m": profiles[:2], "triangle_indices": list(range(6))},
                                  {"arc_id": "accepted", "node_ids": ["port", "anchor"],
                                   "cross_section_xyz_m": profiles[1:], "triangle_indices": list(range(6, 12))}],
                "mesh": {"vertices_xyz_m": vertices, "triangles": triangles,
                         "triangle_arc_ids": ["legacy"] * 6 + ["accepted"] * 6}}
    five = [.5, .75, 1., 1.25, 1.5]
    taper_vertices = [point for z_m, depth in ((1.5, .01), (2., .005), (2.5, 0.))
                      for point in profile(z_m, five, [0., depth, depth, depth, 0.])]
    taper_triangles = []
    for strip in range(2):
        for column in range(4):
            first = strip * 5 + column
            taper_triangles.extend([[first, first + 1, first + 5], [first + 1, first + 6, first + 5]])
    transitions = {"identity_sha256": "c" * 64, "paths_identity_sha256": "d" * 64,
                   "entries": [{"entry_id": "entry", "status": "candidate", "accepted_port_arc_id": "accepted",
                                "accepted_port_xyz_m": profiles[-1], "vertices_xyz_m": taper_vertices,
                                "triangles": taper_triangles, "width_m": .5},
                               {"entry_id": "refused", "status": "refused",
                                "rejection_reasons": ["missing_or_ambiguous_accepted_port"]}]}
    paths = {"identity_sha256": "d" * 64, "nodes": [
        {"node_id": node, "kinds": ["engineering"] if node == "wet" else ["land_channel"]}
        for node in ("anchor", "middle", "wet", "isolated")],
        "arcs": [{"arc_id": "entry", "node_ids": ["anchor", "middle", "wet"]},
                 {"arc_id": "refused", "node_ids": ["isolated"]},
                 {"arc_id": "engineering_singleton", "node_ids": ["wet"]}]}
    base = build_fine_bed_raster(hierarchy, sections, transitions, fine_spacing_m=.125, tile_cells=8,
                                scope="lake-entry-neighborhood")
    shards = build_fine_bed_shards(base, hierarchy)
    readiness = {"requests": [{"entry_id": "entry", "status": "pending", "cell_refusals": {"fill_without_material": 1}},
                              {"entry_id": "refused", "status": "parent_refused"}]}
    return base, shards, hierarchy, sections, transitions, paths, readiness


class SourceConformingBankTests(unittest.TestCase):
    def test_full_component_T_port_nonfill_signed_effects_and_roundtrip(self):
        arguments = fixture()
        base, shards, hierarchy, sections, transitions, paths, readiness = arguments
        original = deepcopy(base)
        package = build_source_conforming_banks(*arguments)
        self.assertGreater(package["manifest"]["summary"]["original_fill_refused_cells"], 0)
        self.assertEqual(package["manifest"]["summary"]["candidate_components"], 1,
                         package["manifest"]["components"])
        self.assertEqual(base, original)
        self.assertGreater(package["manifest"]["summary"]["replace_cells"], 0)
        self.assertEqual(package["manifest"]["summary"]["center_source_resamples"], 0)
        self.assertEqual(package["manifest"]["summary"]["affected_triangles"], len(base["triangles"]))
        port = [proof for chunk in package["proofs"] for proof in chunk["records"]
                if proof["kind"] == "port_function_proof"][0]
        self.assertEqual(port["status"], "candidate", port)
        self.assertEqual(len(port["segment_ids"]), 4)
        parent_cells = {key: cell for key, cell, owner in iter_merged_cells(base, shards["shards"])}
        effects = [effect for chunk in package["effects"] for effect in chunk["records"]]
        self.assertEqual(len(effects), len({tuple(effect["global_key_row_column"]) for effect in effects}))
        for effect in effects:
            after = effect["cell"]
            self.assertEqual(after["source_sample"], parent_cells[tuple(effect["global_key_row_column"])]["source_sample"])
            self.assertLessEqual(after["derived_bed_m"], after["source_sample"]["height_m"])
        self.assertAlmostEqual(sum(effect["cut_delta_m3"] for effect in effects),
                               package["manifest"]["material_ledger_delta"]["cut_rock_m3"])
        self.assertFalse(package["manifest"]["hydraulic_ready"])
        self.assertEqual(package["queue"]["parent_status_counts"], {"pending": 1, "parent_refused": 1})
        self.assertTrue(package["queue"]["requests"][0]["ordinary_flow_references"])
        queued = {row["entry_id"]: row for row in package["queue"]["requests"]}
        connected = queued["entry"]
        walk = connected["actual_support_path_to_engineering_node_ids"]
        self.assertEqual(walk, ["anchor", "middle", "wet"])
        self.assertEqual(connected["actual_support_path_to_engineering_arc_ids"], ["entry", "entry"])
        actual_arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
        self.assertEqual(len(walk), len(connected["actual_support_path_to_engineering_arc_ids"]) + 1)
        for first, second, arc_id in zip(walk, walk[1:], connected["actual_support_path_to_engineering_arc_ids"]):
            ordered_nodes = actual_arcs[arc_id]["node_ids"]
            self.assertTrue(any((first, second) in ((start, end), (end, start))
                                for start, end in zip(ordered_nodes, ordered_nodes[1:])))
        self.assertIn("engineering", next(node for node in paths["nodes"] if node["node_id"] == walk[-1])["kinds"])
        self.assertTrue(connected["undirected_support_reaches_engineering"])
        self.assertEqual(queued["refused"]["actual_node_ids"], ["isolated"])
        self.assertEqual(queued["refused"]["actual_support_path_to_engineering_node_ids"], [])
        self.assertEqual(queued["refused"]["actual_support_path_to_engineering_arc_ids"], [])
        self.assertFalse(queued["refused"]["undirected_support_reaches_engineering"])
        self.assertTrue(all(not row["directed_hydraulic_connection_proved"] for row in queued.values()))
        validate_source_conforming_banks(package, base=base, shard_package=shards, hierarchy=hierarchy)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "candidate"
            save_source_conforming_banks(package, target)
            loaded = load_source_conforming_banks(target,
                expected_manifest_sha256=hashlib.sha256((target / "manifest.json").read_bytes()).hexdigest(),
                expected_manifest_identity=package["manifest"]["identity_sha256"],
                base=base, shard_package=shards, hierarchy=hierarchy)
            self.assertEqual(loaded, package)

    def test_quadratic_source_proof_and_strict_vertex_shared_knot_budget_refusal(self):
        arguments = fixture()
        context = _context(arguments[2], [0])
        endpoints = [[.25, 10. - .5 * .25**2 - 1., .25], [1.75, 10. - .5 * 1.75**2 - 1., 1.75]]
        edges = [{"triangle_id": "first", "edge_index": 0, "points_xyz_m": endpoints},
                 {"triangle_id": "second", "edge_index": 2, "points_xyz_m": endpoints[::-1]}]
        groups = {_line_key(np.asarray(endpoints)[:, [0, 2]]): edges}
        segments = _segments(groups, context)
        self.assertEqual(len(segments), 2)
        proofs = [_proof(segment, context) for segment in segments]
        self.assertTrue(all(proof["status"] == "candidate" for proof in proofs))
        self.assertTrue(all(abs(proof["source"]["source_coefficients_m_t012"][2]) > 0 for proof in proofs))
        for proof in proofs:
            start, end = np.asarray(proof["start_xz_m"]), np.asarray(proof["end_xz_m"])
            point = .7 * start + .3 * end
            polynomial = proof["source"]["source_coefficients_m_t012"]
            self.assertAlmostEqual(polynomial[0] + .3 * polynomial[1] + .3**2 * polynomial[2],
                                   10. - .5 * point[0] * point[1])
        mismatched = deepcopy(segments[0])
        mismatched["depth_support_knots"][0]["original_vertex_refs"][1]["xyz_m"] = list(
            mismatched["depth_support_knots"][0]["original_vertex_refs"][1]["xyz_m"])
        mismatched["depth_support_knots"][0]["original_vertex_refs"][1]["xyz_m"][1] += .001
        self.assertEqual(_proof(mismatched, context)["status"], "refused")
        with self.assertRaises(MemoryError):
            build_source_conforming_banks(*arguments, max_cells=1)
        with self.assertRaises(ValueError):
            build_source_conforming_banks(*arguments, max_shard_bytes=MAX_INVALID_BYTES)
        modified = list(deepcopy(arguments))
        modified[0]["triangles"][0]["vertices_xyz_m"][0][1] += 1.
        with self.assertRaises(ValueError):
            build_source_conforming_banks(*modified)
        rejected = _function(modified[0]["triangles"][0], [], context, arguments[0]["parameters"])
        self.assertEqual(rejected["status"], "refused")
        self.assertIn("original_vertex_fill_or_unknown", rejected["rejection_reasons"])


MAX_INVALID_BYTES = 64 * 1024**2 + 1


if __name__ == "__main__":
    unittest.main()
