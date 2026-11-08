import copy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import sys
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, load_bundle
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import save_td_source as save_td_source
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_basin_morphology import load_morphology, save_morphology
from terrain_pipeline.geology import make_material_field, save_material_field
from terrain_pipeline.td_accepted_water_morphology import (
    export_accepted_water_morphology, load_accepted_water_morphology, rebuild_accepted_candidate, _hash,
)
from tests.test_td_hour_pages_acceptance_io import fixture, write_bundle, write_json


def flowing_fixture(root):
    index, arguments = fixture(root, rain_rate=1.)
    hierarchy = load_basin_hierarchy(**arguments["hierarchy_record"])
    first, second = hierarchy["arrays"]["face_cells"][0]
    net = np.zeros(3)
    net[first], net[second] = .1, -.1
    routed = np.zeros(3)
    duration = np.zeros(3)
    if hierarchy["arrays"]["receiver"][second] == first:
        routed[second], duration[second] = .1, 1.
    for scenario in ("ordinary", "strong"):
        for step in ("2.5", "1.25"):
            cumulative = {}
            for hour, page in enumerate(index["scenarios"][scenario]["pages"][step]):
                storage = load_bundle(page["storage"]["path"], expected_sha256=page["storage"]["expected_sha256"], validator=lambda value: None)
                arrays = {name: values.copy() for name, values in storage["arrays"].items()}
                arrays["depth_m"][0] = hour * (.001 + net / 900)
                arrays["depth_m"][1] = (hour + 1) * (.001 + net / 900)
                arrays["internal_net_m3"][0] = net
                arrays["storage_change_m3"][0] = .9 + net
                arrays["face_reverse_m3"][0] = .1
                arrays["active_reverse_s"][0] = 1.
                arrays["routed_volume_m3"] = routed.copy()
                arrays["wet_duration_s"] = duration.copy()
                Path(page["storage"]["path"]).unlink()
                page["storage"] = write_bundle(Path(page["storage"]["path"]), arrays, dict(storage["metadata"]))
                checkpoint = load_bundle(page["checkpoint"]["path"], expected_sha256=page["checkpoint"]["expected_sha256"], validator=lambda value: None)
                saved = {name: values.copy() for name, values in checkpoint["arrays"].items()}
                saved["depth_m"] = arrays["depth_m"][-1].copy()
                for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
                    cumulative[name] = arrays[name].copy() if hour == 0 else cumulative[name] + arrays[name]
                    saved["cumulative_" + name] = cumulative[name].copy()
                metadata = dict(checkpoint["metadata"], last_page_storage_identity=page["storage"]["expected_identity"])
                Path(page["checkpoint"]["path"]).unlink()
                page["checkpoint"] = write_bundle(Path(page["checkpoint"]["path"]), saved, metadata)
    write_json(Path(root) / "index.json", index)
    arguments["expected_sha256"] = file_sha256(Path(root) / "index.json")
    resource = json.loads((Path(root) / "resource.json").read_text())
    resource["index_sha256"] = arguments["expected_sha256"]
    arguments["execution_resource_record"] = write_json(Path(root) / "resource.json", resource)
    return index, arguments


class AcceptedWaterMorphologyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.index, self.arguments = flowing_fixture(self.root)
        hierarchy = load_basin_hierarchy(**self.arguments["hierarchy_record"])
        source = make_td_source(hierarchy["arrays"]["height_m"], spacing_m=30.)
        source_path = self.root / "source.npz"
        save_td_source(source_path, source)
        self.source_record = dict(path=str(source_path), expected_sha256=file_sha256(source_path), expected_identity=source["identity_sha256"])
        material = make_material_field((1, 3), origin_m_xz=(0, 0), spacing_m=30., seed=1)
        material_path = self.root / "material.npz"
        save_material_field(material, material_path)
        self.material_record = dict(path=str(material_path), expected_sha256=file_sha256(material_path), expected_identity=material["identity_sha256"])
        first = load_bundle(
            self.index["scenarios"]["ordinary"]["pages"]["1.25"][0]["storage"]["path"], expected_sha256=self.index["scenarios"]["ordinary"]["pages"]["1.25"][0]["storage"]["expected_sha256"], validator=lambda value: None)
        self.parameters = first["metadata"]["parameters"]
        self.runoff = first["metadata"]["runoff_parameters"]

    def load_arguments(self, result):
        return dict(expected_sha256=file_sha256(self.root / "candidate" / "index.json"), expected_identity=result["identity_sha256"],
            input_index=self.root / "index.json", acceptance_arguments=self.arguments, source_record=self.source_record,
            material_record=self.material_record, scope="synthetic_fixture", expected_parameters=self.parameters, expected_runoff=self.runoff)

    def tearDown(self):
        self.temp.cleanup()

    def export(self, directory=None):
        return export_accepted_water_morphology(self.root / "index.json", directory or self.root / "candidate",
            acceptance_arguments=self.arguments, source_record=self.source_record, material_record=self.material_record,
            scope="synthetic_fixture", expected_parameters=self.parameters, expected_runoff=self.runoff)

    def test_complete_fixture_export_and_coldload(self):
        result = self.export()
        self.assertEqual(result["selection"], "baseline pending")
        self.assertTrue(result["flags"]["hydraulic_ready"] is False)
        self.assertTrue(result["candidates"]["valley_incision"]["recoupling_required"])
        loaded = load_accepted_water_morphology(self.root / "candidate" / "index.json",
            expected_sha256=file_sha256(self.root / "candidate" / "index.json"), expected_identity=result["identity_sha256"],
            input_index=self.root / "index.json", acceptance_arguments=self.arguments,
            source_record=self.source_record, material_record=self.material_record, scope="synthetic_fixture",
            expected_parameters=self.parameters, expected_runoff=self.runoff)
        self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
        incision = load_morphology(**dict(result["candidates"]["valley_incision"]["morphology"]))
        deposition = load_morphology(**dict(result["candidates"]["source_deposition"]["morphology"]))
        self.assertGreater(incision["metadata"]["ledger"]["source_solid_m3"], 0)
        self.assertGreater(incision["metadata"]["ledger"]["stored_solid_m3"], 0)
        self.assertGreater(deposition["metadata"]["ledger"]["deposited_solid_m3"], 0)
        original_sha = file_sha256(self.source_record["path"])
        rebuilt = rebuild_accepted_candidate(self.root / "candidate" / "index.json", self.root / "rebuilt", candidate_id="source_deposition", **self.load_arguments(result))
        topology = load_basin_hierarchy(**dict(rebuilt["hierarchy"]))
        self.assertEqual(topology["metadata"]["source_identity_sha256"], rebuilt["source"]["expected_identity"])
        self.assertEqual(file_sha256(self.source_record["path"]), original_sha)

    def test_rehashed_derived_bed_and_water_rejected(self):
        result = self.export()
        index_path = self.root / "candidate" / "index.json"
        original_index = index_path.read_bytes()
        record = json.loads(original_index)["candidates"]["valley_incision"]
        source_path = Path(record["source"]["path"])
        original_source = source_path.read_bytes()
        from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
        source = load_td_source_bundle(**record["source"])
        bed = source["arrays"]["height_m"].copy()
        bed[0, 0] += .01
        forged = make_td_source(bed, spacing_m=30., source_sha256=self.source_record["expected_sha256"])
        source_path.unlink()
        save_td_source(source_path, forged)
        manifest = json.loads(original_index)
        manifest["candidates"]["valley_incision"]["source"].update(expected_sha256=file_sha256(source_path), expected_identity=forged["identity_sha256"])
        manifest.pop("identity_sha256")
        manifest["identity_sha256"] = _hash(manifest)
        write_json(index_path, manifest)
        arguments = self.load_arguments(manifest)
        with self.assertRaisesRegex(ValueError, "bed chain"):
            load_accepted_water_morphology(index_path, **arguments)
        source_path.write_bytes(original_source)
        index_path.write_bytes(original_index)
        morphology_path = Path(record["morphology"]["path"])
        morphology = load_morphology(**record["morphology"])
        arrays = {name: values.copy() for name, values in morphology["arrays"].items()}
        arrays["routed_volume_m3"][0, 1] += .001
        from terrain_pipeline.geology import _material_bundle as _bundle
        forged = _bundle(arrays, morphology["metadata"])
        morphology_path.unlink()
        save_morphology(forged, morphology_path)
        manifest = json.loads(original_index)
        manifest["candidates"]["valley_incision"]["morphology"].update(expected_sha256=file_sha256(morphology_path), expected_identity=forged["identity_sha256"])
        manifest.pop("identity_sha256")
        manifest["identity_sha256"] = _hash(manifest)
        write_json(index_path, manifest)
        with self.assertRaises(ValueError):
            load_accepted_water_morphology(index_path, **self.load_arguments(manifest))

    def test_cold_subprocess_no_generation_or_numba(self):
        result = self.export()
        code = """import sys,json,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='numba' or fullname.startswith('numba.') or fullname.startswith('terrain_pipeline.td_basin_storage_continuation') or fullname=='terrain_pipeline.td_basin_transport_v6': raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
import terrain_pipeline.td_basin_morphology as morph
import terrain_pipeline.td_material_field as material
def forbidden(*args,**kwargs): raise AssertionError('generation forbidden')
morph.generate_morphology=forbidden
material.make_material_field=forbidden
from terrain_pipeline.td_accepted_water_morphology import load_accepted_water_morphology
load_accepted_water_morphology(sys.argv[1],**json.loads(sys.argv[2]))
assert 'numba' not in sys.modules
"""
        completed = subprocess.run([sys.executable, "-c", code, str(self.root / "candidate" / "index.json"), json.dumps(self.load_arguments(result), default=str)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_rehashed_balanced_deposit_reallocation_rejected(self):
        result = self.export()
        path = self.root / "candidate" / "index.json"
        manifest = json.loads(path.read_bytes())
        record = manifest["candidates"]["source_deposition"]
        morphology = load_morphology(**record["morphology"])
        arrays = {name: values.copy() for name, values in morphology["arrays"].items()}
        metadata = copy.deepcopy(dict(morphology["metadata"]))
        cell = int(np.argmax(arrays["deposited_solid_m3"]))
        moved = arrays["deposited_solid_m3"].ravel()[cell] / 2
        self.assertGreater(moved, 0)
        arrays["deposited_solid_m3"].ravel()[cell] -= moved
        arrays["stored_solid_m3"].ravel()[cell] += moved
        arrays["deposit_geometry_m3"] = arrays["deposited_solid_m3"] / .65
        arrays["deposit_depth_m"] = arrays["deposit_geometry_m3"] / 900
        arrays["height_delta_m"] = arrays["deposit_depth_m"] - arrays["erosion_depth_m"]
        arrays["height_m"] = arrays["original_height_m"] + arrays["height_delta_m"]
        for name in metadata["ledger"]:
            if name in arrays:
                metadata["ledger"][name] = float(arrays[name].sum())
        metadata["ledger"]["solid_residual_m3"] = metadata["ledger"]["source_solid_m3"] - metadata["ledger"]["deposited_solid_m3"] - metadata["ledger"]["stored_solid_m3"] - metadata["ledger"]["exported_solid_m3"]
        from terrain_pipeline.geology import _material_bundle as _bundle
        forged = _bundle(arrays, metadata)
        target = Path(record["morphology"]["path"])
        target.unlink()
        save_morphology(forged, target)
        record["morphology"].update(expected_sha256=file_sha256(target), expected_identity=forged["identity_sha256"])
        derived = make_td_source(arrays["height_m"], spacing_m=30., source_sha256=self.source_record["expected_sha256"])
        target = Path(record["source"]["path"])
        target.unlink()
        save_td_source(target, derived)
        record["source"].update(expected_sha256=file_sha256(target), expected_identity=derived["identity_sha256"])
        record["ledger"] = metadata["ledger"]
        manifest.pop("identity_sha256")
        manifest["identity_sha256"] = _hash(manifest)
        write_json(path, manifest)
        with self.assertRaisesRegex(ValueError, "allocation mismatch"):
            load_accepted_water_morphology(path, **self.load_arguments(manifest))

    def test_false_gate_and_material_pin_rejected(self):
        self.index["scenarios"]["strong"]["gate_passed"] = False
        self.index["scenarios"]["strong"]["numerical_gate_passed"] = False
        from tests.test_td_hour_pages_acceptance_io import write_json
        write_json(self.root / "index.json", self.index)
        self.arguments["expected_sha256"] = file_sha256(self.root / "index.json")
        with self.assertRaises(ValueError):
            self.export(self.root / "reject")

    def test_material_source_identity_mismatch_rejected(self):
        record = dict(self.material_record, expected_identity="0" * 64)
        with self.assertRaises(ValueError):
            export_accepted_water_morphology(self.root / "index.json", self.root / "reject", acceptance_arguments=self.arguments,
                source_record=self.source_record, material_record=record, scope="synthetic_fixture",
                expected_parameters=self.parameters, expected_runoff=self.runoff)

    def test_missing_partial_and_unknown_scope_rejected(self):
        index_bytes = (self.root / "index.json").read_bytes()
        (self.root / "index.json").unlink()
        with self.assertRaises(ValueError):
            self.export(self.root / "candidate")
        self.assertFalse((self.root / "candidate").exists())
        (self.root / "index.json").write_bytes(index_bytes)
        with self.assertRaises(ValueError):
            export_accepted_water_morphology(self.root / "index.json", self.root / "reject", acceptance_arguments=self.arguments,
                source_record=self.source_record, material_record=self.material_record, scope="unknown",
                expected_parameters=self.parameters, expected_runoff=self.runoff)

    def test_original_td_work_limit_metadata_mismatch_rejected(self):
        from terrain_pipeline import td_accepted_water_morphology as module

        self.assertEqual(module.PHYSICS["max_substeps"], 100000)
        wrong = dict(module.PHYSICS, max_substeps=20000)
        saved = dict(metadata=dict(parameters=wrong, runoff_parameters=asdict(RunoffParameters())))
        accepted = dict(scenarios={name: dict(numerical_gate_passed=True) for name in ("ordinary", "strong")})
        with patch.object(module, "load_hour_pages_index", return_value=accepted), \
                patch.object(module, "MATERIAL_PATH", Path(self.material_record["path"])), \
                patch.object(module, "MATERIAL_SHA", self.material_record["expected_sha256"]), \
                patch.object(module, "MATERIAL_ID", self.material_record["expected_identity"]), \
                patch.object(module, "PRIMARY_SHA256", None), patch.object(module, "_load", return_value=saved):
            with self.assertRaisesRegex(ValueError, "accepted physical configuration differs"):
                module._inputs(self.root / "index.json", self.arguments, self.source_record, self.material_record,
                               "original_td", None, None)
            with self.assertRaisesRegex(ValueError, "cannot be overridden"):
                module._inputs(self.root / "index.json", self.arguments, self.source_record, self.material_record,
                               "original_td", wrong, None)


if __name__ == "__main__":
    unittest.main()
