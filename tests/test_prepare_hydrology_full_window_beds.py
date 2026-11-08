import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.hydrology_detail import DetailBudget
from tools import prepare_hydrology_domains as entry


class FullWindowBedEntryTests(unittest.TestCase):
    def setUp(self):
        self.budget = DetailBudget()
        self.window = {"kind": "mouth", "native_origin_xz": [10, 10],
                       "origin_xz_m": [300, 300], "shape": [97, 97]}
        self.plan = {"identity_sha256": "plan"}
        rows, cols = np.indices((99, 99))
        self.height = -(rows + cols).astype(float)
        self.source = {"original_td_m": self.height, "projection_height_m": self.height,
                       "owner_domain_id": np.zeros((99, 99), int),
                       "ocean_mask": np.zeros((99, 99), bool), "terminal_mask": np.zeros((99, 99), bool)}
        self.source["terminal_mask"][-1, -1] = True
        self.pieces = [{"points_xz_m": [[300, 300], [310, 310]], "receiver": [1, -1],
                        "width_m": [8, 8], "bed_target_m": [-1, -2],
                        "node_source_edges": [[1, 2], [1, 2]], "node_edge_fractions": [0, 1],
                        "centerline_profile": {"shared": index}} for index in range(2)]

    def detail(self, plan, raw, **kwargs):
        return {"metadata": {"identity": "initial", "status": "rejected",
                "ledger": {"macro_absolute_volume_m3": 100 if raw.shape == (97, 97) else 999},
                "rejection_reasons": ["continuous_fine_bed_not_certified", "actual_d8_has_unplanned_interior_sinks"]},
                "arrays": {"derived_height_m": raw.copy(), "actual_receiver": np.zeros(raw.shape, int),
                           "cross_owner_d8_mask": np.ones(raw.shape, bool), "unplanned_sink_mask": np.ones(raw.shape, bool)}}

    def solve(self, detail, points, receiver, widths, targets, **kwargs):
        return {"status": "local_continuous_geometry_global_unverified",
                "ledger": {"local_cut_volume_m3": 2, "local_max_cut_m": 0.5},
                "arrays": {"vertices_xz_m": np.array([[299, 299], [300, 300], [310, 310]])}}

    def run_preparation(self, directory, solve=None, seam=None, **options):
        output = Path(directory)
        window_kind = options.pop("window_kind", "mouth")
        (output / window_kind).mkdir(exist_ok=True)
        provenance = {"archive_sha256": "raw"}
        with ExitStack() as stack:
            stack.enter_context(patch.object(entry, "_owned_full_window_source", return_value=(
                self.window, provenance, provenance, self.source, [{"identity": "core"}])))
            stack.enter_context(patch.object(entry, "derive_detail", side_effect=self.detail))
            stack.enter_context(patch("terrain_pipeline.hydrology_detail_ridge.transformed_coarse_plan", return_value=self.plan))
            stack.enter_context(patch('terrain_pipeline.channel_geometry.select_frozen_window_component',
                                      return_value={"coverage": {"scope": "window97"}}))
            stack.enter_context(patch('terrain_pipeline.channel_geometry.split_frozen_window_component', return_value=self.pieces))
            solver = stack.enter_context(patch('terrain_pipeline.channel_geometry.derive_continuous_bed', side_effect=solve or self.solve))
            auditor = stack.enter_context(patch('terrain_pipeline.channel_geometry.audit_frozen_window_seams',
                side_effect=seam or (lambda results, spec: {"accepted": len(results) == 2 and all(result.get("arrays") for result in results)})))
            stack.enter_context(patch.object(entry, "CanonicalTDSource", side_effect=AssertionError("no model backend")))
            stack.enter_context(patch.object(entry, "prepare_canonical_projection", side_effect=AssertionError("no macro solve")))
            result = entry.prepare_full_window_beds(self.plan, output, self.budget, 526, window_kind, **options)
            return result, solver, auditor

    def test_full_coverage_uses_shared_profiles_cold_artifacts_and_original97_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, solver, auditor = self.run_preparation(temporary)
            self.assertTrue(result["local_window_compatible"])
            self.assertEqual(result["combined97_total_absolute_volume_upper_bound_m3"], 104)
            self.assertEqual(solver.call_count, 2)
            self.assertEqual([call.kwargs["centerline_profile"] for call in solver.call_args_list],
                             [piece["centerline_profile"] for piece in self.pieces])
            self.assertFalse(result["model_inference_run"])
            self.assertFalse(result["macro_projection_run"])
            self.assertFalse(result["publishable"])
            cold = auditor.call_args.args[0]
            for record in cold:
                np.testing.assert_array_equal(record["arrays"]["export_scope_mask"], [False, True, True])
                self.assertEqual(record["identity"], entry._artifact_identity(
                    {key: value for key, value in record.items() if key != "arrays"}, record["arrays"]))
            with np.load(result["native97_detail_path"], allow_pickle=False) as archive:
                self.assertNotIn("actual_receiver", archive.files)
                self.assertEqual(archive["actual_receiver_support99"].shape, (99, 99))
                self.assertFalse(archive["unplanned_sink_mask"].any())
            with np.load(result["computational_support99_path"], allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata_json"].item()))
                self.assertEqual(metadata["computational_support99_ledger"]["macro_absolute_volume_m3"], 999)
                self.assertEqual(metadata["ledger"]["macro_absolute_volume_m3"], 100)
            second, cached_solver, _ = self.run_preparation(temporary)
            self.assertEqual(second["path"], result["path"])
            cached_solver.assert_not_called()

    def test_incomplete_rejected_piece_stops_and_refuses_whole_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, solver, _ = self.run_preparation(temporary,
                solve=lambda *args, **kwargs: {"status": "rejected", "reason": "budget", "arrays": {}})
            self.assertFalse(result["local_window_compatible"])
            self.assertEqual(result["completed_piece_count"], 0)
            self.assertEqual(solver.call_count, 1)
            failure = Path(result["piece_results"][0]["path"])
            record = json.loads(failure.read_text())
            record["parent_detail_identity"] = "wrong-profile"
            failure.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "different shared profile"):
                self.run_preparation(temporary)

    def test_center_lowest_variant_never_reuses_legacy_ceiling_only_pieces(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, _, _ = self.run_preparation(temporary)
            updated, solver, _ = self.run_preparation(temporary, bed_version="v4-center-lowest")
            self.assertEqual(solver.call_count, 2)
            self.assertTrue(all(call.kwargs["center_lowest"] for call in solver.call_args_list))
            self.assertNotEqual(Path(original["path"]).parent, Path(updated["path"]).parent)
            self.assertEqual(updated["bed_version"], "v4-center-lowest")
            request = json.loads(Path(updated["component_request_path"]).read_text())
            self.assertEqual(request["bed_version"], "v4-center-lowest")
            self.assertTrue(Path(original["path"]).exists())

    def test_frozen_sidecar_and_stage_reach_each_confluence_piece_in_separate_variant(self):
        sidecar = {"identity_sha256": "frozen-tributary"}
        lake_mask = np.ones((2, 2), bool)
        self.window["kind"] = "confluence"
        with tempfile.TemporaryDirectory() as temporary, \
                patch("terrain_pipeline.hydrology_detail_tributaries.validate_local_tributary_sidecar") as validator:
            result, solver, _ = self.run_preparation(temporary, window_kind="confluence",
                tributary_declaration=sidecar, lake_mask=lake_mask, bed_version="v4-center-lowest")
            validator.assert_called_once_with(self.plan, sidecar, highest_lake_level_m=526, lake_mask=lake_mask)
            for call in solver.call_args_list:
                self.assertIs(call.kwargs["tributary_declaration"], sidecar)
                self.assertEqual(call.kwargs["highest_lake_level_m"], 526)
                self.assertIs(call.kwargs["lake_mask"], lake_mask)
            self.assertIn("local-tributary-frozen-tribu", result["path"])
            self.assertEqual(result["projection_algorithm"], entry._projection_algorithm("v3", sidecar))

    def test_continuous_center_floor_has_separate_artifacts_and_solver_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous, _, _ = self.run_preparation(temporary, bed_version="v4-center-lowest")
            updated, solver, _ = self.run_preparation(temporary, bed_version="v5-continuous-center-lowest")
            self.assertEqual(solver.call_count, 2)
            self.assertTrue(all(call.kwargs["center_lowest"] and call.kwargs["continuous_center_lowest"]
                                for call in solver.call_args_list))
            self.assertNotEqual(Path(previous["path"]).parent, Path(updated["path"]).parent)
            self.assertEqual(updated["bed_version"], "v5-continuous-center-lowest")
            cached, cached_solver, _ = self.run_preparation(temporary, bed_version="v5-continuous-center-lowest")
            self.assertEqual(cached["path"], updated["path"])
            cached_solver.assert_not_called()

    def test_complete_adjacent_shared_sections_are_explicit_and_keep_physical_contract(self):
        sections = [[{"algorithm": "bounded-complete-adjacent-feasible-fan4-section-v3"}]]*2
        with tempfile.TemporaryDirectory() as temporary, \
                patch('terrain_pipeline.channel_geometry.frozen_shared_sections', return_value=sections) as builder:
            result, solver, _ = self.run_preparation(temporary, bed_version="v8-complete-adjacent-shared-sections")
            self.assertTrue(builder.call_args.kwargs["complete_adjacent_pieces"])
            self.assertEqual(result["shared_section_algorithm"], "bounded-complete-adjacent-feasible-fan4-section-v3")
            self.assertIn("v8-complete-adjacent-shared-sections", result["path"])
            for call, group in zip(solver.call_args_list, sections):
                self.assertTrue(call.kwargs["center_lowest"])
                self.assertTrue(call.kwargs["continuous_center_lowest"])
                self.assertEqual(call.kwargs["fine_spacing_m"], 1)
                self.assertEqual(call.kwargs["shared_sections"], group)
            self.assertEqual(result["budget"], asdict(self.budget))

    def test_missing_owning_core_refuses_without_preparing_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "mouth").mkdir()
            declared = {"budget": asdict(self.budget), "budget_status": "frozen_after_calibration",
                        "canonical_source_identity": "source"}
            (output / "mouth/detail-plan.json").write_text(json.dumps(declared))
            (output / "mouth/mouth-original-td.npz").write_bytes(b"test")
            (output / "mouth/mouth-original-td.sha256").write_text("pin")
            raw = {"arrays": {"height_m": self.height[1:-1, 1:-1]}}
            metadata = {"provenance": {"generation_metadata": {
                "native_origin": [10, 10], "shape": [97, 97], "identity": "source"}}}
            with patch.object(entry, "projection_source_declaration", return_value={"windows": [self.window]}), \
                    patch.object(entry, "load_raw_td", return_value=(raw, metadata)), \
                    patch.object(entry, "CanonicalTDSource", side_effect=AssertionError("no model")):
                with self.assertRaisesRegex(ValueError, "accepted owning core is not prepared"):
                    entry._owned_full_window_source(self.plan, output, "mouth", self.budget, 526)
                core = output / "canonical-projections-v2/tile-x0-z0.npz"
                core.parent.mkdir()
                core.write_bytes(b"test")
                with patch("terrain_pipeline.hydrology_detail_projection.load_projection", return_value={
                        "metadata": {"algorithm": entry._projection_algorithm("v3")}}):
                    with self.assertRaisesRegex(ValueError, "not accepted for the frozen source"):
                        entry._owned_full_window_source(self.plan, output, "mouth", self.budget, 526, "v2")


if __name__ == "__main__":
    unittest.main()
