"""Read-only prefix recovery tests."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import td_weather_checkpoint_recovery as recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.inputs = dict(schema="td-v10-spatial-weather-run-inputs-v1", steps_s=[2.5, 1.25],
                           physics_version="v10-unified-infiltration; not execution-equivalence",
                           primary_sha256="primary", chunk_max_face_steps=6000000000,
                           job_max_bytes=1073741824, depth_gate_m=.001, receiver_gate=.01,
                           code_sha256={"frozen.py": "code"},
                           hierarchy=dict(path=str(self.root / "hierarchy"), expected_sha256="hierarchy", expected_identity="id"),
                           weather_index=dict(path=str(self.root / "weather"), sha256=recovery.EXPECTED_WEATHER_SHA256),
                           weather_records={}, forcing_identities={}, budgets={})
        for direction in recovery.DIRECTIONS:
            self.inputs["weather_records"][direction] = {"path": str(self.root / "weather"),
                                                           "expected_sha256": recovery.EXPECTED_WEATHER_SHA256}
            self.inputs["forcing_identities"][direction] = direction
        for step in recovery.STEPS:
            self.inputs["budgets"][str(step)] = dict(chunk_face_steps=int(3600 / step) * 2,
                                                       global_face_steps_per_direction=24 * int(3600 / step) * 2)
        (self.run / "run-inputs.json").write_text(json.dumps(self.inputs), encoding="utf-8")
        for name in ("primary", "frozen.py", "hierarchy", "source", "weather"):
            (self.root / name).touch()
        arrays = {name: np.zeros((2, 2)) for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask")}
        hierarchy = dict(arrays=dict(arrays, face_cells=np.zeros((2, 2), dtype=int)), metadata={})
        source = dict(arrays=arrays, metadata={"source_sha256": "primary"})
        cases = {direction: dict(record=self.inputs["weather_records"][direction], forcing_identity=direction,
                                 rain_mm_h=np.zeros((24, 2, 2))) for direction in recovery.DIRECTIONS}
        weather = dict(index_pin=self.inputs["weather_index"], source=dict(path=str(self.root / "source"),
                       expected_sha256="source", expected_identity="id"), cases=cases)

        def digest(path):
            name = Path(path).name
            known = dict(primary="primary", **{"frozen.py": "code", "hierarchy": "hierarchy",
                                               "source": "source", "weather": recovery.EXPECTED_WEATHER_SHA256,
                                               "run-inputs.json": "inputs"})
            return known.get(name, "page" if Path(path).suffix == ".npz" else "report")

        values = dict(PRIMARY_PATH=self.root / "primary", PRIMARY_SHA256="primary", ROOT=self.root,
                      file_sha256=digest, load_basin_hierarchy=lambda **record: hierarchy,
                      load_td_source_bundle=lambda **record: source,
                      load_weather_inputs=lambda *args, **kwargs: weather,
                      load_native_weather_v10_hour=lambda *args, **kwargs: {
                          "storage": {"arrays": {"balance_residual_m3": np.zeros(1)}},
                          "budget": dict(rain_m3=0., loss_m3=0., external_m3=0.,
                                         initial_water_m3=0., final_water_m3=0.)})
        for name, value in values.items():
            item = patch.object(recovery, name, value)
            item.start()
            self.addCleanup(item.stop)

    def page(self, hour, *, report=True):
        directory = self.run / "eastward-2.5s" / f"hour-{hour:02d}"
        directory.mkdir(parents=True)
        if not report:
            (directory / "checkpoint.npz").touch()
            return directory
        record = dict(hour=hour, elapsed_s=1., forcing_identity="eastward",
                      chunk_work_face_steps=2880, global_water_residual_m3=0.)
        for kind in ("storage", "checkpoint"):
            path = directory / f"{kind}.npz"
            path.touch()
            record[kind] = dict(path=str(path), expected_sha256="page", expected_identity=kind)
        (directory / "report.json").write_text(json.dumps(record))
        return directory

    def inspect(self):
        return recovery.inspect_prefix(self.run, run_inputs_sha256="inputs")

    def test_inventory_ignores_unreported_tail(self):
        self.page(0)
        self.page(1, report=False)
        result = self.inspect()
        group = result["groups"]["eastward-2.5s"]
        self.assertEqual(group["verified_hours"], 1)
        self.assertEqual(group["ignored_unrecoverable_tail_hours"], [1])
        self.assertEqual(group["last_checkpoint"], group["pages"][0]["checkpoint"])
        self.assertFalse(result["resource_authenticated"])
        self.assertFalse(result["resume_authorized"])
        self.assertFalse(result["complete_run_accepted"])

    def test_rejects_gap(self):
        self.page(0)
        self.page(2)
        with self.assertRaises(ValueError):
            self.inspect()

    def test_rejects_partial_inside_prefix(self):
        self.page(0, report=False)
        self.page(1)
        with self.assertRaises(ValueError):
            self.inspect()

    def test_rejects_report_and_pin_mismatch(self):
        directory = self.page(0)
        path = directory / "report.json"
        original = json.loads(path.read_text())
        for key, value in (("forcing_identity", "wrong"), ("checkpoint", dict(original["checkpoint"], expected_sha256="wrong"))):
            with self.subTest(key=key):
                changed = dict(original, **{key: value})
                path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    self.inspect()

    def test_rejects_code_change(self):
        original = recovery.file_sha256
        with patch.object(recovery, "file_sha256", lambda path: "changed" if Path(path).name == "frozen.py" else original(path)):
            with self.assertRaises(ValueError):
                self.inspect()

    def test_fresh_process_imports_no_solver_or_numba(self):
        code = ("import terrain_pipeline.td_weather_checkpoint_recovery; import sys; "
                "assert 'numba' not in sys.modules; "
                "assert 'terrain_pipeline.td_basin_storage_v10' not in sys.modules")
        subprocess.run([sys.executable, "-c", code], check=True)


if __name__ == "__main__":
    unittest.main()
