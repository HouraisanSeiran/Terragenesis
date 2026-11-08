import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_td_native_weather_storage_v10_io as fixtures
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.td_surface_reaches import _hash
from terrain_pipeline.td_native_weather_v10_review import export_native_weather_v10_review, load_native_weather_v10_review


class NativeWeatherV10ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.NativeWeatherV10IoTests()
        cls.fixture.setUp()
        cls.root = cls.fixture.root
        cls.arguments = cls.fixture._whole_fixture()
        cls.directory = cls.root.parent/(cls.root.name+"-review")
        cls.result = export_native_weather_v10_review(cls.root/"index.json",cls.directory,acceptance_arguments=cls.arguments,include_hour_flux=True)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.directory)
        cls.fixture.tearDown()

    def _load(self):
        return load_native_weather_v10_review(self.directory/"index.json",expected_sha256=file_sha256(self.directory/"index.json"),
            expected_identity=self.result["identity_sha256"],input_index=self.root/"index.json",acceptance_arguments=self.arguments,include_hour_flux=True)

    def test_complete_binary_frames_and_raw_cold(self):
        loaded = self._load()
        self.assertEqual(loaded["frames"],25)
        self.assertEqual(loaded["directions"],["eastward","westward"])
        for direction in loaded["directions"]:
            frames = {page["frame_index"] for page in loaded["pages"] if page["kind"]=="native_states" and page["scenario"]==direction}
            self.assertEqual(frames,set(range(25)))
        self.assertFalse(loaded["flags"]["water_interpolation"])

    def test_raw_tamper_missing_extra_rejected(self):
        target = self.directory/self.result["pages"][1]["file"]
        raw = target.read_bytes()
        target.write_bytes(bytes([raw[0]^1])+raw[1:])
        try:
            with self.assertRaises(ValueError):
                self._load()
        finally:
            target.write_bytes(raw)
        target.unlink()
        try:
            with self.assertRaises(ValueError):
                self._load()
        finally:
            target.write_bytes(raw)
        extra = self.directory/"extra.bin"
        extra.write_bytes(b"extra")
        try:
            with self.assertRaises(ValueError):
                self._load()
        finally:
            extra.unlink()

    def test_rehashed_path_descriptor_rejected(self):
        path = self.directory/"index.json"
        raw = path.read_bytes()
        result = copy.deepcopy(self.result)
        result["pages"][0]["file"] = "../escaped.json"
        result.pop("identity_sha256")
        result["identity_sha256"] = _hash(result)
        path.write_text(json.dumps(result),encoding="utf8")
        try:
            with self.assertRaises(ValueError):
                load_native_weather_v10_review(path,expected_sha256=file_sha256(path),expected_identity=result["identity_sha256"],
                    input_index=self.root/"index.json",acceptance_arguments=self.arguments,include_hour_flux=True)
        finally:
            path.write_bytes(raw)

    def test_budget_and_postexport_failure_no_publication(self):
        directory = self.root.parent/(self.root.name+"-rejected")
        with self.assertRaises(ValueError):
            export_native_weather_v10_review(self.root/"index.json",directory,acceptance_arguments=self.arguments,output_budget_bytes=1)
        self.assertFalse(directory.exists())

    def test_leaf_interval_failure_rejects_without_publication(self):
        from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
        directory = self.root.parent/(self.root.name+"-leaf-rejected")
        def inconsistent_leaf_account(**record):
            result = load_storage(**record)
            result = dict(result,arrays={name:values.copy() for name,values in result["arrays"].items()})
            result["arrays"]["rain_volume_m3"][0,0] += .01
            return result
        with patch("terrain_pipeline.td_native_weather_v10_review.load_storage",side_effect=inconsistent_leaf_account):
            with self.assertRaisesRegex(ValueError,"exclusive leaf interval budget failed"):
                export_native_weather_v10_review(self.root/"index.json",directory,acceptance_arguments=self.arguments)
        self.assertFalse(directory.exists())
        with patch("terrain_pipeline.td_native_weather_v10_review._verify",side_effect=ValueError("postexport failure")):
            with self.assertRaises(ValueError):
                export_native_weather_v10_review(self.root/"index.json",directory,acceptance_arguments=self.arguments)
        self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
