"""Byte identity, current-v8 equivalence and explicit historical isolation gates."""

import ast
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import shutil
import subprocess
import sys
import tempfile
import unittest

from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment, common_Model as Model, common_Section as Section
from builtins import ValueError as HydraulicDiagnosticStop, ValueError as HydraulicExecutionFailure
from terrain_pipeline.hybrid_hydraulics import local_frame_run_experiment as run_experiment, translate_section
from tests.hybrid_hydraulics_fixtures import tiny_model
from tools.hybrid_hydraulics_legacy import DATA_ROOT, SOURCE_ROOT, HydraulicsLegacyReplay
from tools.prepare_hybrid_river_hydraulics_v8 import source_identity

VOLATILE = frozenset(("elapsed_wall_seconds", "actual_peak_rss_bytes", "wall_seconds"))


def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in VOLATILE}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    return value


class HydraulicsConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.replay = HydraulicsLegacyReplay()
        self.addCleanup(self.replay.close)

    def test_frozen_all_pins_ast_and_roots_without_path_mutation(self):
        before = list(sys.path)
        for version in ("", "_v2", "_v3", "_v4", "_v5", "_v6", "_v7", "_v8"):
            module = self.replay.load("tools.prepare_hybrid_river_hydraulics" + version)
            self.assertEqual(module.ROOT, DATA_ROOT)
            self.assertEqual(module.SOURCE_ROOT, SOURCE_ROOT)
            for name, expected in getattr(module, "FROZEN_CODE", {}).items():
                self.assertEqual(module.file_sha(DATA_ROOT / name), expected, name)
        self.replay.load("tools.audit_hybrid_river_hydraulics").check_same_physics(True)
        from tools.audit_hybrid_river_hydraulics import check_same_physics
        check_same_physics(True)
        self.assertEqual(sys.path, before)
        self.assertNotIn('terrain_pipeline.hybrid_river_hydraulics_v7', sys.modules)
        with self.assertRaises(ImportError):
            self.replay.load('terrain_pipeline.hybrid_river_faces')
        with self.assertRaises(ValueError):
            self.replay.source_path(DATA_ROOT / "tools/not_allowlisted.py")

    def test_common_and_radau_ast_exact_function_identity(self):
        def declarations(path):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(path.read_bytes()).body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        original = declarations(SOURCE_ROOT / "terrain_pipeline/hybrid_river_hydraulics.py")
        common = declarations(DATA_ROOT / "legacy-code/refactor-merge-20261105/M2/terrain_pipeline/hybrid_river_hydraulics_common.py")
        self.assertNotIn("run_experiment", common)
        self.assertEqual(common, {key: value for key, value in original.items() if key != "run_experiment"})
        self.assertEqual(declarations(DATA_ROOT / "legacy-code/refactor-merge-20261105/M2/terrain_pipeline/hybrid_river_hydraulics_radau.py"),
                         declarations(SOURCE_ROOT / "terrain_pipeline/hybrid_river_hydraulics_v6.py"))

    def test_current_original_v8_all_arrays_metadata_and_physical_identity(self):
        old_fixture = self.replay.load("tests.test_hybrid_river_hydraulics")
        old_base = self.replay.load('terrain_pipeline.hybrid_river_hydraulics')
        old_solver = self.replay.load('terrain_pipeline.hybrid_river_hydraulics_v8')
        old_prepare = self.replay.load("tools.prepare_hybrid_river_hydraulics_v8")
        from tools.hybrid_hydraulics_preparation_common import physical_model_identity
        current_model = tiny_model()
        self.assertIs(type(current_model), Model)
        self.assertIs(type(current_model.cells[0].section), Section)
        for datum in (0, 1350):
            for scenario, tailwater in (("pulse", .1), ("reverse_tailwater", .4)):
                with self.subTest(datum=datum, scenario=scenario):
                    current = replace(current_model, cells=tuple(replace(cell, section=translate_section(cell.section, -datum))
                                                                  for cell in current_model.cells))
                    previous_model = old_fixture.tiny_model()
                    previous = replace(previous_model, cells=tuple(replace(cell, section=old_solver.translate_section(cell.section, -datum))
                                                                       for cell in previous_model.cells))
                    parameters = Experiment(scenario, .2, .05 if scenario == "pulse" else 0,
                                            .05 if scenario == "pulse" else 0, datum + tailwater,
                                            (datum + .2,) * 3, (0, .05, .1, .2), max_step_s=.02)
                    old_parameters = old_base.Experiment(**asdict(parameters))
                    expected = old_solver.run_experiment(previous, old_parameters, .02)
                    actual = run_experiment(current, parameters, .02)
                    # No numeric tolerance: every nested array, work count and non-resource metadata must be exact.
                    self.assertEqual(stable(actual), stable(expected))
                    record = {key: actual.get(key, {"fixed": key}) for key in (
                        "model_version", "model_parameters", "friction_policy", "inventory_policy",
                        "forcing_configuration_pin", "graph_identity_sha256", "geometry_identity_sha256")}
                    self.assertEqual(physical_model_identity(record), old_prepare.physical_model_identity(record))

    def test_current_original_diagnostic_and_guard_failure_metadata(self):
        old_solver = self.replay.load('terrain_pipeline.hybrid_river_hydraulics_v8')
        old_base = self.replay.load('terrain_pipeline.hybrid_river_hydraulics')
        old_model = self.replay.load("tests.test_hybrid_river_hydraulics").tiny_model()
        parameters = Experiment("pulse", .2, .05, .05, .1, (.2,) * 3, (0, .05, .1, .2), max_step_s=.02)
        for diagnostic, limit in ((.075, parameters.max_rhs_evaluations), (None, 1)):
            case = replace(parameters, max_rhs_evaluations=limit)
            with self.assertRaises((old_solver.HydraulicDiagnosticStop, old_solver.HydraulicExecutionFailure)) as before:
                old_solver.run_experiment(old_model, old_base.Experiment(**asdict(case)), .02, diagnostic)
            with self.assertRaises((HydraulicDiagnosticStop, HydraulicExecutionFailure)) as after:
                run_experiment(tiny_model(), case, .02, diagnostic)
            self.assertIs(type(after.exception), ValueError)
            self.assertEqual(after.exception.diagnostic_stop, isinstance(before.exception, old_solver.HydraulicDiagnosticStop))
            self.assertEqual(str(after.exception), str(before.exception))
            self.assertEqual(stable(after.exception.progress), stable(before.exception.progress))

    def test_manifest_and_source_double_tamper_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "archive"
            shutil.copytree(SOURCE_ROOT, archive)
            source = archive / "terrain_pipeline/hybrid_river_hydraulics_v6.py"
            source.write_bytes(source.read_bytes() + b"\n# tamper\n")
            with self.assertRaisesRegex(ValueError, "source sha256 mismatch"):
                HydraulicsLegacyReplay(source_root=archive)
            manifest_path = archive / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            entry = manifest["files"]["terrain_pipeline/hybrid_river_hydraulics_v6.py"]
            entry.update(sha256=hashlib.sha256(source.read_bytes()).hexdigest(), bytes=source.stat().st_size)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest sha256 mismatch"):
                HydraulicsLegacyReplay(source_root=archive)

    def test_source_data_root_separation_and_late_tamper_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, data = root / "source", root / "data"
            shutil.copytree(SOURCE_ROOT, archive)
            data.mkdir()
            (data / "terrain_pipeline").mkdir()
            (data / "terrain_pipeline/hybrid_river_hydraulics.py").write_bytes(b"not the frozen source")
            replay = HydraulicsLegacyReplay(source_root=archive, data_root=data)
            self.addCleanup(replay.close)
            module = replay.load("tools.prepare_hybrid_river_hydraulics_v8")
            self.assertEqual(module.ROOT, data)
            for name, expected in module.FROZEN_CODE.items():
                self.assertEqual(module.file_sha(data / name), expected)
            artifact = data / "input.json"
            artifact.write_bytes(b'{"unchanged":true}')
            self.assertEqual(module.file_sha(artifact), hashlib.sha256(artifact.read_bytes()).hexdigest())
            source = archive / "terrain_pipeline/hybrid_river_hydraulics_v6.py"
            source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                replay.source_path(source)
            with self.assertRaises(ValueError):
                replay.load('terrain_pipeline.hybrid_river_hydraulics_v6') if 'terrain_pipeline.hybrid_river_hydraulics_v6' not in replay.modules else replay.source_path(source)

    def test_new_source_identity_different_and_not_historical_hash_relabel(self):
        current, historical = source_identity()
        self.assertIn("terrain_pipeline/hybrid_hydraulics.py", current)
        for name in ("terrain_pipeline/hybrid_river_hydraulics_v6.py", "terrain_pipeline/hybrid_river_hydraulics.py"):
            self.assertNotIn(name, current)
        self.assertNotEqual(current["terrain_pipeline/hybrid_hydraulics.py"],
                            historical["terrain_pipeline/hybrid_river_hydraulics_v8.py"])
        for name, sha in current.items():
            self.assertEqual(hashlib.sha256((DATA_ROOT / name).read_bytes()).hexdigest(), sha)
        self.assertNotIn("BDF", json.dumps(current))

    def test_current_cold_import_does_not_load_legacy_kernels_or_mutate_path(self):
        code = """import sys
before=list(sys.path)
import terrain_pipeline.hybrid_hydraulics
import tools.prepare_hybrid_river_hydraulics_v8
assert sys.path == before
for name in ('terrain_pipeline.hybrid_river_hydraulics', 'terrain_pipeline.hybrid_river_hydraulics_v3', 'terrain_pipeline.hybrid_river_hydraulics_v4', 'terrain_pipeline.hybrid_river_hydraulics_v5', 'terrain_pipeline.hybrid_river_hydraulics_v6', 'terrain_pipeline.hybrid_river_hydraulics_v7'):
    assert name not in sys.modules, name
assert not any(name.startswith('_hybrid_hydraulics_legacy_') for name in sys.modules)
"""
        subprocess.run([sys.executable, "-B", "-c", code], cwd=DATA_ROOT, check=True, capture_output=True, text=True)

    def test_actual_small_prepare_outputs_and_source_identity_change(self):
        from terrain_pipeline.hybrid_geometry import identity
        from tools import prepare_hybrid_river_hydraulics_v8 as current_prepare
        from tools.hybrid_hydraulics_preparation_common import file_sha
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "verification/hybrid-river-network"
            parent.mkdir(parents=True)
            graph = {"identity_sha256": "fixed-graph"}
            geometry = {"identity_sha256": "fixed-geometry"}
            arguments = {}
            for name, record in (("graph", graph), ("geometry", geometry), ("geometry_audit", {"fixed": True})):
                path = root / (name + ".json")
                path.write_text(json.dumps(record), encoding="utf-8")
                arguments[name] = path
                arguments[name + "_sha256"] = file_sha(path)
            inputs = {name: {"path": str(arguments[name]), "sha256": arguments[name + "_sha256"]}
                      for name in ("graph", "geometry", "geometry_audit")}
            scenarios = [asdict(Experiment(scenario, .2, .05 if scenario == "pulse" else 0,
                        .05 if scenario == "pulse" else 0, tailwater, (.2,) * 3, (0, .05, .1, .2), max_step_s=.02))
                         for scenario, tailwater in (("pulse", .1), ("reverse_tailwater", .4))]
            configuration = {"schema": "td-hybrid-river-engineering-experiments-v1", "scenarios": scenarios,
                             "graph_identity_sha256": graph["identity_sha256"],
                             "geometry_identity_sha256": geometry["identity_sha256"], "inputs": inputs}
            configuration["identity_sha256"] = identity(configuration)
            config_path = root / "experiments.json"
            config_path.write_text(json.dumps(configuration), encoding="utf-8")
            arguments.update(experiments=config_path, experiments_sha256=file_sha(config_path),
                             crown_friction_transition_m=.02, diagnostic_stop_s=None)
            old_context = HydraulicsLegacyReplay(data_root=root)
            self.addCleanup(old_context.close)
            old_prepare = old_context.load("tools.prepare_hybrid_river_hydraulics_v8")
            old_model = old_context.load("tests.test_hybrid_river_hydraulics").tiny_model()
            # Isolate only the prevalidated geometry boundary; both runs use real
            # pinned JSON, real four-case Radau solves and atomic checkpoint writes.
            with patch.object(old_prepare, "validate_geometry", return_value=(old_model, geometry)):
                before = old_prepare.prepare(SimpleNamespace(**arguments, output=parent / "original"))
            with patch.object(current_prepare, "ROOT", root), patch.object(
                    current_prepare, "validate_geometry", return_value=(tiny_model(), geometry)):
                after = current_prepare.prepare(SimpleNamespace(**arguments, output=parent / "current"))
            self.assertEqual(before["status"], after["status"])
            self.assertEqual(after["status"], "refused_diagnostic_evidence")
            self.assertEqual(before["physical_model_identity_sha256"], after["physical_model_identity_sha256"])
            self.assertNotEqual(before["code_sha256"], after["code_sha256"])
            for case in ("pulse-base", "pulse-refined", "reverse_tailwater-base", "reverse_tailwater-refined"):
                first = json.loads((parent / "original" / (case + ".json")).read_bytes())
                second = json.loads((parent / "current" / (case + ".json")).read_bytes())
                for record in (first, second):
                    for key in ("identity_sha256", "code_sha256", "hydraulic_model_parameters", "hydraulic_model_parameters_identity_sha256"):
                        record.pop(key)
                self.assertEqual(stable(first), stable(second), case)

    def test_preexisting_historical_wrong_source_pin_is_not_relabelled(self):
        # Saved 20261006-07 expects a different v3 source variant than the
        # original bytes available at this consolidation boundary.
        saved_pin = {"path": str(DATA_ROOT / "terrain_pipeline/hybrid_river_hydraulics_v3.py"),
                     "sha256": "472f3114a235d8c68fe449b4a514beceb8069853722abeb1664c822473a7311d"}
        reader = self.replay.load("tools.td_shared_channel_fine_saved_audit")
        with self.assertRaisesRegex(ValueError, "historical source pin mismatch"):
            reader.checked_path(saved_pin)
        self.assertEqual(saved_pin["sha256"], "472f3114a235d8c68fe449b4a514beceb8069853722abeb1664c822473a7311d")
