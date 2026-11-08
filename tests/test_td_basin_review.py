import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import save_td_source as save_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
from terrain_pipeline.basin_storage import simulate_threshold_storage as simulate_basin_storage
from terrain_pipeline.basin_storage import save_basin_storage as save_basin_storage
from terrain_pipeline.geology import make_material_field, save_material_field
from terrain_pipeline.td_basin_morphology import generate_morphology, save_morphology
from terrain_pipeline.basin_storage import BASIN_REVIEW_ALGORITHM as ALGORITHM
from terrain_pipeline.basin_storage import export_basin_review as export_basin_review
from terrain_pipeline.basin_storage import export_comparison_navigation as export_comparison_navigation
from terrain_pipeline.basin_storage import load_basin_review as load_basin_review
from terrain_pipeline.basin_storage import load_candidate_comparison as load_candidate_comparison
from terrain_pipeline.basin_storage import load_review_inputs as load_review_inputs
from terrain_pipeline.basin_storage import load_selection_proof as load_selection_proof
from terrain_pipeline.basin_storage import make_basin_review as make_basin_review


def fixtures(directory, *, with_storage=True, with_morphology=False):
    source = make_td_source(np.asarray([[3, 2, 1], [4, 3, 2]], np.float64), spacing_m=1)
    hierarchy = build_basin_hierarchy(source)
    material = make_material_field((2, 3), origin_m_xz=(0, 0), spacing_m=1)
    bundles = {"source": source, "hierarchy": hierarchy, "material": material}
    writers = {"source": lambda bundle, path: save_td_source(path, bundle),
               "hierarchy": lambda bundle, path: save_basin_hierarchy(path, bundle), "material": save_material_field,
               "storage": lambda bundle, path: save_basin_storage(path, bundle), "morphology": save_morphology}
    if with_storage:
        bundles["storage"] = simulate_basin_storage(hierarchy, np.zeros(1), dt_s=60, initial_depth_m=np.full((2, 3), 0.01))
    if with_morphology:
        bundles["morphology"] = generate_morphology(source["arrays"]["height_m"], source["arrays"]["valid_mask"], hierarchy["arrays"]["receiver"],
            np.full((2, 3), 1000.0), np.full((2, 3), 3600.0), spacing_m=1, materials=material)
    records = {}
    for role, bundle in bundles.items():
        path = directory / (role + ".npz")
        writers[role](bundle, path)
        records[role] = {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": bundle["identity_sha256"]}
    return records


class BasinReviewTests(unittest.TestCase):
    def test_pinned_cold_adapter_no_generation_or_hydro_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            with patch('terrain_pipeline.geology.make_material_field', side_effect=AssertionError("forbidden")), patch('terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError("forbidden")), patch('terrain_pipeline.basin_topology.build_basin_hierarchy', side_effect=AssertionError("forbidden")):
                inputs = load_review_inputs(records)
                review = make_basin_review(inputs)
                manifest = export_basin_review(records, directory / "review")
                loaded = load_basin_review(directory / "review", expected_manifest_sha256=file_sha256(directory / "review/manifest.json"))
            loaded.pop("raw_input_records")
            self.assertEqual(review, loaded)
            self.assertTrue(manifest["source_unchanged"])
            self.assertEqual(manifest["algorithm"], ALGORITHM)
            self.assertFalse(manifest["flags"]["transient_converged"])
            self.assertEqual(review["sampling"]["omitted_cells"], 0)

    def test_no_hydro_no_fabricated_water(self):
        with tempfile.TemporaryDirectory() as temporary:
            records = fixtures(Path(temporary), with_storage=False)
            review = make_basin_review(load_review_inputs(records))
            self.assertIsNone(review["water"])
            self.assertFalse(review["flags"]["water_available"])

    def test_water_is_exact_solved_baseline_and_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            records = fixtures(Path(temporary), with_morphology=True)
            inputs = load_review_inputs(records)
            review = make_basin_review(inputs)
            self.assertEqual(review["water"]["time_s"], [0.0, 60.0])
            depth = inputs["storage"]["arrays"]["depth_m"].reshape((-1, 2, 3))
            np.testing.assert_allclose(review["water"]["depth_m"], depth)
            self.assertIn("H0_m + depth_m", review["water"]["surface_formula"])
            self.assertFalse(review["flags"]["water_on_candidate_verified"])
            self.assertFalse(review["flags"]["transient_converged"])
            self.assertFalse(review["water"]["flags"]["morphology_flux_ready"])
            self.assertIn("material_ledger", review["candidates"]["morphology"])

    def test_bad_external_pins_refused_no_partial_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            records["storage"]["expected_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                export_basin_review(records, directory / "review")
            self.assertFalse((directory / "review").exists())

    def test_broken_identity_chain_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            records = fixtures(Path(temporary))
            inputs = load_review_inputs(records)
            inputs["storage"]["metadata"]["hierarchy_identity_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                make_basin_review(inputs)

    def test_source_coordinates_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            records = fixtures(Path(temporary))
            inputs = load_review_inputs(records)
            inputs["material"]["metadata"]["origin_m_xz"] = [1, 0]
            with self.assertRaises(ValueError):
                make_basin_review(inputs)

    def test_manifest_pin_and_tamper_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            output = directory / "review"
            export_basin_review(records, output)
            digest = file_sha256(output / "manifest.json")
            with self.assertRaises(FileExistsError):
                export_basin_review(records, output)
            with self.assertRaises(ValueError):
                load_basin_review(output, expected_manifest_sha256="0" * 64)
            (output / "review.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_basin_review(output, expected_manifest_sha256=digest)

    def test_offline_page_no_tube_no_external_script_and_safe_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            export_basin_review(records, directory / "review")
            page = (directory / "review/review.html").read_text(encoding="utf-8")
            self.assertNotIn("TubeGeometry", page)
            self.assertNotIn("https://", page)
            self.assertIn("candidate.value==='baseline'", page)
            self.assertIn("picked_cell", page)
            self.assertIn("setInterval", page)
            self.assertIn("global_flags", page)
            self.assertIn("data.saddle_overlay", page)
            self.assertIn("function terrain", page)
            self.assertIn("pick.erodible_thickness_m", page)
            self.assertIn("pick.fast_mm", page)
            self.assertIn("threshold_hidden_sampled_water_m3", page)
            data = json.loads((directory / "review/review.json").read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], "td-basin-review-v1")

    def test_lod_reports_omitted_points_footprint_water_and_keeps_native_arrays(self):
        from terrain_pipeline.basin_storage import make_basin_review as make_basin_review
        height = np.linspace(70, 1, 70).reshape((70, 1))
        source = make_td_source(height, spacing_m=1)
        hierarchy = build_basin_hierarchy(source)
        material = make_material_field(height.shape, origin_m_xz=(0, 0), spacing_m=1)
        review = make_basin_review({"source": source, "hierarchy": hierarchy, "material": material})
        self.assertEqual(review["render_lod"]["stride"], 2)
        self.assertTrue(review["render_lod"]["terrain_interpolation"])
        self.assertFalse(review["render_lod"]["water_interpolation"])
        self.assertEqual(review["render_lod"]["displayed_points"], 35)
        self.assertEqual(review["render_lod"]["omitted_points"], 35)
        self.assertEqual(review["render_lod"]["omitted_footprint_area_m2"], 35)
        self.assertEqual(len(review["fields"]["H0_m"]), 70)
        self.assertEqual(review["sampling"]["omitted_cells"], 0)

    def test_candidate_index_baseline_pins_and_conservative_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            baseline = {key: value for key, value in records.items() if key != "storage"}
            baseline.update({"ordinary": records["storage"], "strong": records["storage"]})
            index = {"schema": "td-basin-candidate-records-v1", "selected_candidate_id": "baseline", "candidates": [{
                "candidate_id": "baseline", "source_identity_sha256": records["source"]["expected_identity"],
                "hierarchy_identity_sha256": records["hierarchy"]["expected_identity"],
                "ordinary_identity_sha256": records["storage"]["expected_identity"],
                "strong_identity_sha256": records["storage"]["expected_identity"]}]}
            path = directory / "records.json"
            path.write_text(json.dumps(index), encoding="utf-8")
            digest = file_sha256(path)
            with patch('terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError("forbidden")):
                comparison = load_candidate_comparison(path, expected_sha256=digest, baseline_records=baseline)
            self.assertFalse(comparison["flags"]["transient_converged"])
            self.assertEqual(comparison["selected_candidate_id"], "baseline")
            with self.assertRaises(ValueError):
                load_candidate_comparison(path, expected_sha256="0" * 64, baseline_records=baseline)
            index["candidates"][0]["strong_identity_sha256"] = "0" * 64
            path.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_candidate_comparison(path, expected_sha256=file_sha256(path), baseline_records=baseline)

    def test_candidate_selection_proof_is_external_and_bound_to_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            baseline = {key: value for key, value in records.items() if key != "storage"}
            baseline.update({"ordinary": records["storage"], "strong": records["storage"]})
            index = {"schema": "td-basin-candidate-records-v1", "selected_candidate_id": "baseline", "candidates": [{
                "candidate_id": "baseline", "source_identity_sha256": records["source"]["expected_identity"],
                "hierarchy_identity_sha256": records["hierarchy"]["expected_identity"],
                "ordinary_identity_sha256": records["storage"]["expected_identity"],
                "strong_identity_sha256": records["storage"]["expected_identity"]}]}
            index_path = directory / "records.json"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            index_sha = file_sha256(index_path)
            artifact = directory / "proof-artifact.json"
            artifact.write_text(json.dumps({"ordinary": {"gate_passed": False}, "strong": {"gate_passed": False}}), encoding="utf-8")
            proof = {"schema": "td-basin-selection-proof-v1", "candidate_records_sha256": index_sha,
                     "scopes": [{"scope_id": "baseline-full", "scope": "full_domain_baseline", "passed": False,
                                 "artifacts": [{"path": str(artifact), "expected_sha256": file_sha256(artifact)}],
                                 "limitations": "full-domain sensitivity pending"}]}
            proof_path = directory / "selection-proof.json"
            proof_path.write_text(json.dumps(proof), encoding="utf-8")
            comparison = load_candidate_comparison(index_path, expected_sha256=index_sha,
                baseline_records=baseline, selection_proof={"path": str(proof_path), "expected_sha256": file_sha256(proof_path)})
            self.assertFalse(comparison["flags"]["transient_converged"])
            self.assertEqual(comparison["selection_proof"]["scopes"][0]["scope"], "full_domain_baseline")
            proof["candidate_records_sha256"] = "0" * 64
            proof_path.write_text(json.dumps(proof), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_candidate_comparison(index_path, expected_sha256=index_sha, baseline_records=baseline,
                    selection_proof={"path": str(proof_path), "expected_sha256": file_sha256(proof_path)})

    def test_candidate_failures_are_rejected_before_any_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = fixtures(directory)
            baseline = {key: value for key, value in records.items() if key != "storage"}
            baseline.update({"ordinary": records["storage"], "strong": records["storage"]})
            empty = directory / "empty.json"
            empty.write_text(json.dumps({"schema": "td-basin-candidate-records-v1", "selected_candidate_id": "baseline", "candidates": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_candidate_comparison(empty, expected_sha256=file_sha256(empty), baseline_records=baseline)
            outside = {"path": str(Path(temporary).parent / "outside.npz"), "expected_sha256": "0" * 64, "expected_identity": "0" * 64}
            index = {"schema": "td-basin-candidate-records-v1", "selected_candidate_id": "baseline", "candidates": [
                {"candidate_id": "baseline", "source_identity_sha256": records["source"]["expected_identity"], "hierarchy_identity_sha256": records["hierarchy"]["expected_identity"], "ordinary_identity_sha256": records["storage"]["expected_identity"], "strong_identity_sha256": records["storage"]["expected_identity"]},
                {"candidate_id": "valley_incision", "morphology": outside, "changed_cells": 1, "max_abs_delta_m": 1, "material_ledger": {}}]}
            candidate_path = directory / "candidate.json"
            candidate_path.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_candidate_comparison(candidate_path, expected_sha256=file_sha256(candidate_path), baseline_records=baseline)

    def test_navigation_real_links_rejections_scope_and_html_escaping(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            page = directory / "ordinary.html"
            page.write_text("<!doctype html>", encoding="utf-8")
            comparison = {"selected_candidate_id": "baseline", "flags": {"transient_converged": False},
                          "candidates": [{"candidate_id": "baseline", "flags": {"selected": True}},
                                         {"candidate_id": "saddle_breach_1", "flags": {"rejection_reasons": ["<missing water>"]}}]}
            output = directory / "index.html"
            export_comparison_navigation(comparison, {"baseline": {"ordinary": str(page)}}, output)
            text = output.read_text(encoding="utf-8")
            self.assertIn('href="ordinary.html"', text)
            self.assertIn("&lt;missing water&gt;", text)
            self.assertIn("无冻结审查页面", text)
            self.assertIn("选择范围", text)
            with self.assertRaises(FileExistsError):
                export_comparison_navigation(comparison, {}, output)
            with self.assertRaises(ValueError):
                export_comparison_navigation(comparison, {"invented": {}}, directory / "bad.html")


if __name__ == "__main__":
    unittest.main()
