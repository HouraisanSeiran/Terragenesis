import copy
import importlib.util
import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers import metric_td_generated_rivers as rivers
from tools.repair_td_river_shapes import copy_completed_sample
from tools import repair_td_river_shapes as repair


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.config = rivers.GeneratedRiverConfig()
        self.terrain = SimpleNamespace(identity_sha256="terrain-id")
        self.ids = np.array([0, 1])
        self.receiver = np.array([1, -1])
        self.width = np.array([3., 4.])
        self.depth = np.array([.3, .4])
        self.bundle = dict(arrays=dict(source_node_cell_ids=self.ids, receiver=self.receiver,
            width_m=self.width, base_depth_m=self.depth + .2, design_base_depth_m=self.depth), identity_sha256="component-id",
            metadata=dict(source_identity_sha256="terrain-id", config=asdict(self.config),
                cut_volume_m3=1., maximum_cut_m=.4, component_max_cut_reference_volume_m3=1.,
                preclosure_cut_volume_m3=1.))

    def test_saved_component_reused_missing_component_generated_and_merged(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            prior = root / "prior"
            prior.mkdir()
            (prior / "geometry-c0.npz").write_bytes(b"saved component")
            arrays = dict(selected_edge_source_ids=np.array([0, 2]),
                selected_edge_target_ids=np.array([1, 3]), width_m=np.tile(self.width, 2),
                base_depth_m=np.tile(self.depth, 2))
            registration = dict(terrain=self.terrain,
                metadata=dict(source_metadata=dict(sample_index=1)))
            stack.enter_context(patch.object(rivers, "prepare_network", return_value=(
                arrays, {}, {}, [np.array([0]), np.array([1])])))
            stack.enter_context(patch.object(rivers, "load_component_geometry", return_value=self.bundle))
            generated = stack.enter_context(patch.object(rivers, "component_geometry", return_value=self.bundle))
            merged = stack.enter_context(patch.object(rivers, "merge_component_beds", return_value=self.bundle))
            stack.enter_context(patch.object(rivers, "save_component_geometry",
                side_effect=lambda path, bundle: path.write_bytes(b"new component")))
            stack.enter_context(patch.object(rivers, "save_network_geometry_plan",
                side_effect=lambda path, plan: path.write_bytes(b"plan")))
            report, bundles = rivers.generate_sample(root / "new", registration, self.config,
                                                      resume_from=prior)
            self.assertEqual(generated.call_count, 1)
            np.testing.assert_array_equal(generated.call_args.args[1], [2, 3])
            self.assertEqual(len(merged.call_args.args[1]), 2)
            self.assertEqual(report["accepted_edges"], 2)
            self.assertEqual((root / "new/geometry-c0.npz").read_bytes(), b"saved component")
            self.assertIn("reused_from", report["component_records"][0])
            self.assertNotIn("reused_from", report["component_records"][1])
            with patch("shutil.copy2", side_effect=lambda source, target: target.write_bytes(b"corrupt")):
                with self.assertRaisesRegex(ValueError, "copied resume component bytes differ"):
                    rivers.generate_sample(root / "refused-copy", registration, self.config,
                                           resume_from=prior)

    def test_resume_identity_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "geometry-c0.npz"
            path.write_bytes(b"saved component")
            for field in ("source", "config", "source_node_cell_ids", "receiver", "width_m", "design_base_depth_m", "missing_design_depth"):
                bundle = copy.deepcopy(self.bundle)
                if field == "source":
                    bundle["metadata"]["source_identity_sha256"] = "other"
                elif field == "config":
                    bundle["metadata"]["config"]["max_cut_m"] = 5.
                elif field == "missing_design_depth":
                    del bundle["arrays"]["design_base_depth_m"]
                else:
                    bundle["arrays"][field][0] += 1
                with self.subTest(field=field), patch.object(rivers, "load_component_geometry", return_value=bundle):
                    with self.assertRaisesRegex(ValueError, "resume component"):
                        rivers._resume_component(path, self.terrain, self.ids, self.receiver,
                                                 self.width, self.depth, self.config)

    def test_complete_sample_copy_preserves_report_and_checks_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prior = root / "prior"
            prior.mkdir()
            (prior / "network.npz").write_bytes(b"network")
            registration = dict(metadata=dict(source="frozen"))
            report = dict(config=asdict(self.config), source_registration=registration["metadata"],
                status="completed_all_selected_edges_classified", geometry_artifacts=[], global_bed=None,
                network=dict(path="network.npz", sha256=file_sha256(prior / "network.npz")))
            original = json.dumps(report, indent=3).encode()
            (prior / "report.json").write_bytes(original)
            pin = dict(report_sha256=file_sha256(prior / "report.json"))
            copy_completed_sample(prior, root / "new", registration, self.config, pin)
            self.assertEqual((root / "new/report.json").read_bytes(), original)
            (prior / "network.npz").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "artifact differs"):
                copy_completed_sample(prior, root / "refused", registration, self.config, pin)

    def test_cli_copies_sample_zero_then_generates_remaining_samples(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            baseline, prior, output = root / "baseline", root / "prior", root / "new"
            baseline.mkdir()
            prior.mkdir()
            report_path = root / "source-report.json"
            report_path.write_text("{}", encoding="utf-8")
            config = rivers.GeneratedRiverConfig(centerline_corridor_m=30., centerline_iterations=24)
            registrations, pins = [], []
            for index in range(6):
                source_metadata = dict(terrain_identity_sha256="terrain-id",
                                       boundary_identity_sha256="boundary-id", sample_index=index)
                registrations.append(dict(metadata=source_metadata, boundary=SimpleNamespace(identity_sha256="boundary-id"),
                    terrain=SimpleNamespace(identity_sha256="terrain-id", generation_seed=index,
                        x0_m=0., z0_m=0., dx_m=1., elevation_m=np.zeros((2, 2)))))
                sample_dir = baseline / f"sample-{index}"
                sample_dir.mkdir()
                (sample_dir / "network.npz").write_bytes(b"network")
                sample_report = dict(config=asdict(config), source_registration=source_metadata, forcing={},
                    accepted_edges=1, rejected_edges=0, component_records=[], geometry_artifacts=[], global_bed=None,
                    status="completed_all_selected_edges_classified",
                    network=dict(path="network.npz", sha256=file_sha256(sample_dir / "network.npz")))
                (sample_dir / "report.json").write_text(json.dumps(sample_report), encoding="utf-8")
                pins.append(dict(sample_index=index, report_path=f"sample-{index}/report.json",
                                 report_sha256=file_sha256(sample_dir / "report.json")))
            (baseline / "manifest.json").write_text(json.dumps(dict(samples=pins,
                generation_report_sha256=file_sha256(report_path))), encoding="utf-8")
            import shutil
            shutil.copytree(baseline / "sample-0", prior / "sample-0")
            (prior / "progress-sample-0.json").write_text(json.dumps(dict(
                report_sha256=pins[0]["report_sha256"], runtime=dict(elapsed_seconds=100.))), encoding="utf-8")
            stack.enter_context(patch.object(repair, "snapshot_generation_sources", return_value=[]))
            stack.enter_context(patch.object(repair, "validate_resume_sources", return_value=[]))
            stack.enter_context(patch.object(repair, "load_generated_td_source", side_effect=lambda path, index: registrations[index]))
            stack.enter_context(patch.object(repair, "grid_rainfall", return_value=(None, {})))
            stack.enter_context(patch.object(repair, "peak_process_memory_bytes", return_value=0))
            def generate(path, registration, config, **kwargs):
                index = registration["metadata"]["sample_index"]
                shutil.copytree(baseline / f"sample-{index}", path)
                return json.loads((path / "report.json").read_text()), []
            generated = stack.enter_context(patch.object(repair, "generate_sample", side_effect=generate))
            repair.main(["--all-six", "--report", str(report_path), "--baseline", str(baseline),
                         "--resume-from", str(prior), "--output", str(output)])
            self.assertEqual([call.args[1]["metadata"]["sample_index"] for call in generated.call_args_list], [1, 2, 3, 4, 5])
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(len(manifest["samples"]), 6)
            self.assertEqual(manifest["resume"]["completed_samples"][0]["sample_index"], 0)

    def test_launcher_console_encoding_failure_keeps_complete_log(self):
        launcher_path = Path(__file__).resolve().parents[1] / ".scratch/td-river-shape-repair/run_default_component_logged.py"
        spec = importlib.util.spec_from_file_location("resume_launcher", launcher_path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new"
            child = SimpleNamespace(pid=123, stdout=["Traceback: \u5c71\u5ddd\U0001f600\n", "FileExistsError: provenance\n"], wait=lambda: 1)
            encoding_error = UnicodeEncodeError("gbk", "\U0001f600", 0, 1, "unsupported")
            with patch("sys.argv", [str(launcher_path), "--all-six", "--output", str(output)]), \
                    patch.object(launcher.subprocess, "Popen", return_value=child) as started, \
                    patch("builtins.print", side_effect=encoding_error):
                self.assertEqual(launcher.main(), 1)
            self.assertIn("utf8", started.call_args.args[0])
            self.assertEqual(output.with_name("new-run.log").read_text(encoding="utf-8"), "".join(child.stdout))
            status = json.loads(output.with_name("new-run-status.json").read_text())
            self.assertEqual(status["outcome"], "failed")
            self.assertIn("console_mirror_error", status)

    def test_resume_identical_source_accepted_unapproved_change_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            snapshot = directory / "snapshot.py"
            snapshot.write_text("def component():\n    return 1\n", encoding="utf-8")
            pin = dict(source_path="terrain_pipeline/surface_rivers/metric_noise_forcing.py",
                       path="snapshot.py", sha256=file_sha256(snapshot))
            records = repair.validate_resume_sources(directory, [pin])
            self.assertEqual(records[0]["comparison"], "identical_bytes")
            pin["sha256"] = "changed-source"
            with self.assertRaisesRegex(ValueError, "resume source snapshot differs"):
                repair.validate_resume_sources(directory, [pin])


if __name__ == "__main__":
    unittest.main()
