from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import environment_product as product_api
from tests.test_environment_process_product import fixture
from tools import prepare_environment_processes as prepare


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentProcessesCliTests(unittest.TestCase):
    def test_prepare_cold_resume_and_read_only_query(self):
        seed = fixture()
        driving = {"rainfall_m_s": 1.e-8, "radiation": {"longitude_deg": 180., "time_s": 999999.}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forcing = root / "forcing.json"
            forcing.write_text(json.dumps(driving), encoding="utf-8")
            initial = root / "initial.json"
            initial.write_text(json.dumps(seed["initial_declarations"]), encoding="utf-8")
            first_path = root / "first.npz"
            captured = StringIO()
            with patch.object(product_api, "context_from_store", return_value=(seed["context"], seed["sources"])) as read_source:
                with redirect_stdout(captured):
                    self.assertEqual(prepare.main([
                        "--store", str(root / "source"), "--row", "1", "--col", "2", "--size", "5",
                        "--initial", str(initial), "--forcing", str(forcing), "--steps", "1",
                        "--dt-s", "3600", "--output", str(first_path)]), 0)
                read_source.assert_called_once_with(root / "source", 1, 2, 5)
            first_record = json.loads(captured.getvalue())
            first = product_api.load_product(first_path, expected_sha256=first_record["sha256"])
            self.assertEqual(first_record["product_identity"], product_api.product_identity(first))
            direct = product_api.advance(first, driving, 3600.)
            resumed_path = root / "resumed.npz"
            resume = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/prepare_environment_processes.py"),
                "--resume", str(first_path), "--expected-sha256", first_record["sha256"],
                "--forcing", str(forcing), "--steps", "1", "--dt-s", "3600",
                "--output", str(resumed_path)], cwd=ROOT, capture_output=True, text=True, check=True)
            record = json.loads(resume.stdout)
            resumed = product_api.load_product(resumed_path, expected_sha256=record["sha256"])
            self.assertEqual(record["time_s"], 7200.)
            self.assertEqual(record["step_index"], 2)
            for name, state in direct["states"].items():
                for key, value in state.items():
                    np.testing.assert_array_equal(value, resumed["states"][name][key])
            expected_radiation = product_api.radiation.step(
                first["states"]["radiation"], {"longitude_deg": 180., "time_s": 3600.},
                first["context"], 3600.)
            np.testing.assert_array_equal(resumed["states"]["radiation"]["absorbed_energy_j_m2"],
                                          expected_radiation["state"]["absorbed_energy_j_m2"])
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            query = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/query_environment_processes.py"),
                "--product", str(resumed_path), "--expected-sha256", record["sha256"],
                "--row", "2", "--col", "2"], cwd=ROOT, capture_output=True, text=True, check=True)
            queried = json.loads(query.stdout)
            self.assertTrue(queried["read_only"])
            self.assertEqual(queried["time_s"], 7200.)
            self.assertEqual(before, {path.name: path.read_bytes() for path in root.iterdir()})

    def test_resume_rejects_hash_mismatch_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.npz"
            digest = product_api.save_product(fixture(), path)
            before = path.read_bytes()
            output = Path(directory) / "next.npz"
            with self.assertRaises(SystemExit):
                prepare.main(["--resume", str(path), "--expected-sha256", "0" * 64,
                              "--output", str(output)])
            self.assertFalse(output.exists())
            with self.assertRaises(SystemExit):
                prepare.main(["--resume", str(path), "--expected-sha256", digest,
                              "--output", str(path)])
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
