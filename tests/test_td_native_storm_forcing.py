import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_basin_source import make_td_source, save_td_source
from terrain_pipeline.td_native_storm_forcing import (
    StormParameters, fixed_storm, generate_native_storm, load_native_storm,
    preflight, save_native_storm, validate_native_storm,
)


class NativeStormTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        valid = np.ones((6, 8), bool)
        valid[1, 2] = False
        protected = np.zeros(valid.shape, bool)
        protected[3, 4] = True
        self.source = make_td_source(np.arange(48.).reshape(6, 8), spacing_m=30.,
            origin_m_xz=(-300., 600.), valid_mask=valid, protected_mask=protected)
        path = self.root / "source.npz"
        save_td_source(path, self.source)
        self.record = dict(path=str(path), expected_sha256=file_sha256(path),
                           expected_identity=self.source["identity_sha256"])
        self.parameters = fixed_storm(self.source, "eastward")

    def make(self, **options):
        return generate_native_storm(self.record, parameters=self.parameters, **options)

    def test_native_identity_masks_active_and_protection(self):
        result = self.make()
        rain = result["arrays"]["rain_mm_h"]
        self.assertEqual(rain.shape, (24, 6, 8))
        self.assertEqual(result["metadata"]["forcing_identity"], identity({"rain_mm_h": rain}, {"dt_s": 3600.}))
        self.assertTrue((rain[6:] == 0).all())
        self.assertTrue((rain[:, 1, 2] == 0).all())
        self.assertGreater(rain[0, 3, 4], 0.)
        np.testing.assert_array_equal(result["arrays"]["protected_mask"], self.source["arrays"]["protected_mask"])
        self.assertFalse(result["metadata"]["plan"]["water_solved"])
        with self.assertRaises(ValueError):
            rain.setflags(write=True)

    def test_reversed_windows_exact_and_volume_additive(self):
        full = self.make()
        totals = np.zeros(24)
        for window in reversed([[0, 3, 0, 4], [0, 3, 4, 8], [3, 6, 0, 4], [3, 6, 4, 8]]):
            part = self.make(window=window)
            row0, row1, col0, col1 = window
            np.testing.assert_array_equal(part["arrays"]["rain_mm_h"], full["arrays"]["rain_mm_h"][:, row0:row1, col0:col1])
            totals += part["arrays"]["interval_rain_m3"]
        np.testing.assert_allclose(totals, full["arrays"]["interval_rain_m3"], rtol=2e-15, atol=1e-12)

    def test_time_integral_partition_and_directions(self):
        full = self.make(steps=6)
        half = self.make(steps=12, dt_s=1800.)
        np.testing.assert_allclose(full["arrays"]["rain_mm_h"], half["arrays"]["rain_mm_h"].reshape(6, 2, 6, 8).mean(axis=1), rtol=1e-13, atol=1e-12)
        west = generate_native_storm(self.record, parameters=fixed_storm(self.source, "westward"))
        self.assertGreater(full["arrays"]["rain_mm_h"][0, 0, 0], west["arrays"]["rain_mm_h"][0, 0, 0])

    def test_invalid_preallocation_and_parameters(self):
        for shape, steps, samples in [((256, 256), 100, 2), ((500, 500), 16, 4), ((256, 256), 48, 2), ((1, 1), True, 2)]:
            with self.assertRaises(ValueError):
                preflight(shape, steps, samples)
        for options in (dict(dt_s=float("nan")), dict(window=[0, 9, 0, 8]), dict(spatial_subsamples=3)):
            with patch("terrain_pipeline.td_native_storm_forcing._source", return_value=self.source), patch("terrain_pipeline.td_native_storm_forcing.np.zeros", side_effect=AssertionError("allocated")):
                with self.assertRaises(ValueError):
                    self.make(**options)
        with self.assertRaises(ValueError):
            StormParameters(0, 0, 0, 0, 0, 30, 0, 100)

    def test_external_pin_rehash_and_time_semantic_rejection(self):
        result = self.make()
        path = self.root / "rain.npz"
        save_native_storm(path, result)
        options = dict(expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"],
                       source_record=self.record, expected_plan=result["metadata"]["plan"])
        loaded = load_native_storm(path, **options)
        self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
        with self.assertRaises(ValueError):
            load_native_storm(path, **{**options, "expected_identity": "0" * 64})
        for name in ("time_edges_s", "valid_mask", "interval_rain_m3"):
            changed = copy.deepcopy(result)
            changed["arrays"] = {key: values.copy() for key, values in result["arrays"].items()}
            if name == "valid_mask":
                changed["arrays"][name].flat[0] = False
            else:
                changed["arrays"][name].flat[0] += 1
            changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
            with self.assertRaises(ValueError):
                validate_native_storm(changed, source_record=self.record, expected_plan=options["expected_plan"])
        changed = copy.deepcopy(result)
        changed["metadata"]["plan"]["dt_s"] = 1800.
        changed["metadata"]["plan_identity"] = identity({}, changed["metadata"]["plan"])
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_native_storm(changed, source_record=self.record, expected_plan=options["expected_plan"])

    def test_malicious_header_before_np_load(self):
        path = self.root / "malicious.npz"
        stream = io.BytesIO()
        np.lib.format.write_array_header_1_0(stream, {"descr": "<f8", "fortran_order": False, "shape": (24, 8000000, 8000000)})
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("rain_mm_h.npy", stream.getvalue())
        plan = self.make()["metadata"]["plan"]
        with patch("numpy.load", side_effect=AssertionError("allocated")):
            with self.assertRaises(ValueError):
                load_native_storm(path, expected_sha256=file_sha256(path), expected_identity="0" * 64,
                                  source_record=self.record, expected_plan=plan)

    def test_cold_fresh_process_no_generation_no_numba(self):
        result = self.make()
        path = self.root / "rain.npz"
        save_native_storm(path, result)
        options = dict(expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"],
                       source_record=self.record, expected_plan=result["metadata"]["plan"])
        payload = self.root / "options.json"
        payload.write_text(json.dumps(dict(path=str(path), options=options)), encoding="utf-8")
        script = """import json,sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith('numba') or 'td_basin_storage' in fullname:
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
import terrain_pipeline.td_native_storm_forcing as module
def reject(*args,**kwargs):
    raise AssertionError('generation forbidden')
module.generate_native_storm=reject
module.interval_mean_mm_h=reject
record=json.load(open(sys.argv[1],encoding='utf-8'))
module.load_native_storm(record['path'],**record['options'])
assert not any(name.startswith('numba') for name in sys.modules)
"""
        subprocess.run([sys.executable, "-c", script, str(payload)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
