from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, file_sha256
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_basin_storage_dispatch_io import VERSIONS, validate_saved_storage, save_storage, load_storage
from terrain_pipeline.td_surface_reaches import make_surface_reaches, save_surface_reaches, load_surface_reaches, _plain
from terrain_pipeline.td_basin_spill_network import save_basin_spill_bundle, load_basin_spill_bundle
from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges


def fixture(version="D4-threshold-symmetric-forcing-SSPRK2-v6", profile="v6-simultaneous-SSPRK2-6e9-v1"):
    hierarchy = build_basin_hierarchy(make_td_source(np.array([[0., 2., 0.]]), spacing_m=30))
    topology = hierarchy["arrays"]
    cells, faces = 3, len(topology["face_cells"])
    arrays = {name: topology[name] for name in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells")}
    for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
        arrays[name] = np.zeros((2, cells))
    for name in ("rain_mm_h", "rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
                 "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3"):
        arrays[name] = np.zeros((1, cells))
    for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        arrays[name] = np.zeros(faces)
    arrays.update(boundary_width_m=np.zeros(0), routed_volume_m3=np.zeros(cells), wet_duration_s=np.zeros(cells), wet_pool_count=np.zeros(2, np.int64))
    metadata = {"schema": "td-basin-storage-v1", "algorithm": version,
                "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": 30., "origin_m_xz": [0, 0],
                "dt_s": 1., "substep_s": 1., "substeps": 1,
                "parameters": {"substep_s": 1., "face_conductance_m_s": .6, "surface_evaporation_mm_h": 0.,
                    "wet_threshold_m": 1e-9, "max_substeps": 20000, "max_work_face_steps": 500000000},
                "runoff_parameters": asdict(RunoffParameters(initial_soil_mm=0)),
                "hydraulic_ready": False, "transient_converged": False, "morphology_flux_ready": False, "natural_outlet_verified": False}
    if profile is not None:
        metadata["work_profile"] = profile
    if version.endswith(("-v5", "-v6")):
        metadata.update(forcing_semantics="runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
            saved_time_semantics="state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
            activity_semantics="RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity" if version.endswith("-v6") else "each face visited twice for substep_s/2 within transport; sum directional activity<=substep_s; forcing halves add no activity")
    if version.endswith("-v6"):
        metadata["positivity_cfl"] = 2 * .6 / 30
    return hierarchy, {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


class StorageDispatchTests(unittest.TestCase):
    def test_rehashed_substep_count_and_actual_duration_refused(self):
        for name, value in (("substeps", 1), ("substep_s", .5)):
            _, storage = fixture()
            storage["metadata"]["dt_s"] = 2.5
            storage["metadata"]["substeps"] = 3
            storage["metadata"]["substep_s"] = 2.5 / 3
            storage["metadata"]["positivity_cfl"] = 2 * .6 * (2.5 / 3) / 30
            storage["metadata"][name] = value
            storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "substep"):
                validate_saved_storage(storage)

    def test_rehashed_boundary_and_undeclared_outflow_refused(self):
        cases = [(np.array([0., 1.]), np.array([60., 60.])),
                 (np.array([0, 0], np.int64), np.array([90., 90.])),
                 (np.array([3], np.int64), np.array([30.])),
                 (np.array([0], np.int64), np.array([30.]))]
        for boundary, widths in cases:
            _, storage = fixture()
            storage["arrays"].update(boundary_cells=boundary, boundary_width_m=widths)
            storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
            with self.subTest(boundary=boundary.tolist()), self.assertRaises(ValueError):
                validate_saved_storage(storage)
        _, storage = fixture()
        storage["arrays"]["boundary_outflow_m3"][0, 1] = 1
        storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
        with self.assertRaisesRegex(ValueError, "undeclared"):
            validate_saved_storage(storage)

    def test_rehashed_duplicate_faces_receiver_and_pool_refused(self):
        mutations = [lambda arrays: arrays.update(face_cells=np.array([[0, 1], [1, 0]], np.int64)),
                     lambda arrays: arrays.update(receiver=np.array([-1., 0., -1.])),
                     lambda arrays: arrays.update(receiver=np.array([2, 0, -1], np.int64)),
                     lambda arrays: arrays.update(wet_pool_count=np.array([-1, 0], np.int64)),
                     lambda arrays: arrays.update(wet_pool_count=np.array([0., 0.]))]
        for mutate in mutations:
            _, storage = fixture()
            mutate(storage["arrays"])
            storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
            with self.assertRaises(ValueError):
                validate_saved_storage(storage)
        _, storage = fixture()
        storage["arrays"]["height_m"] = np.zeros((1, 3))
        storage["arrays"]["receiver"] = np.array([1, 0, -1], np.int64)
        storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_saved_storage(storage)

    def test_v6_review_pinned_load_no_generation(self):
        from terrain_pipeline.td_basin_source import save_td_source
        from terrain_pipeline.td_material_field import make_material_field, save_material_field
        from terrain_pipeline.td_basin_review import load_review_inputs, make_basin_review
        hierarchy, storage = fixture()
        source = make_td_source(np.array([[0., 2., 0.]]), spacing_m=30)
        material = make_material_field((1, 3), origin_m_xz=(0, 0), spacing_m=30)
        with tempfile.TemporaryDirectory() as directory:
            records = {}
            for role, bundle, writer in (("source", source, lambda path, value: save_td_source(path, value)),
                                         ("hierarchy", hierarchy, save_basin_hierarchy), ("storage", storage, save_storage),
                                         ("material", material, lambda path, value: save_material_field(value, path))):
                path = Path(directory) / (role + ".npz")
                writer(path, bundle)
                records[role] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=bundle["identity_sha256"])
            with patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("generate")), patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy", side_effect=AssertionError("generate")), patch("terrain_pipeline.td_basin_storage_dispatch_io.save_storage", side_effect=AssertionError("write")):
                inputs = load_review_inputs(records)
                review = make_basin_review(inputs)
            self.assertEqual(inputs["storage"]["metadata"], storage["metadata"])
            self.assertEqual(review["water"]["hydro_identity_sha256"], storage["identity_sha256"])
            self.assertFalse(review["flags"]["transient_converged"])
            code = '''import sys, importlib.abc, json
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numba' or fullname.startswith('numba.') or fullname in {'terrain_pipeline.td_basin_storage', 'terrain_pipeline.td_basin_storage_v4', 'terrain_pipeline.td_basin_storage_v5', 'terrain_pipeline.td_basin_storage_v6', 'terrain_pipeline.td_basin_transport_v6'}:
            raise AssertionError('solver import: '+fullname)
sys.meta_path.insert(0,Block())
from terrain_pipeline.td_basin_review import load_review_inputs,make_basin_review
review=make_basin_review(load_review_inputs(json.loads(sys.argv[1])))
assert review['flags']['transient_converged'] is False
assert 'numba' not in sys.modules
'''
            completed = subprocess.run([sys.executable, "-c", code, json.dumps(records)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_nonzero_v6_reverse_exchange_survives_all_adapters(self):
        hierarchy, storage = fixture()
        arrays = storage["arrays"]
        arrays["depth_m"][0] = [0., 1., 0.]
        arrays["depth_m"][1] = [1 / 900, 1 - 1 / 900, 0.]
        arrays["face_reverse_m3"][0] = 1.
        arrays["active_reverse_s"][0] = .5
        arrays["internal_net_m3"][0] = [1., -1., 0.]
        arrays["storage_change_m3"][0] = [1., -1., 0.]
        receiver = hierarchy["arrays"]["receiver"]
        if receiver[1] == 0:
            arrays["routed_volume_m3"][1] = 1.
            arrays["wet_duration_s"][1] = .5
        storage["identity_sha256"] = identity(arrays, storage["metadata"])
        self.assertTrue(validate_saved_storage(storage))
        reaches = make_surface_reaches(hierarchy, threshold_area_m2=900, expected_hierarchy_identity=hierarchy["identity_sha256"],
            storage=storage, expected_storage_identity=storage["identity_sha256"])
        reverse_edges = [edge for reach in reaches["reaches"] for edge in reach["edges"] if edge["face_index"] == 0]
        self.assertEqual(reverse_edges[0]["stored_flux"]["reverse_m3"], 1.)
        build_td_surface_river_edges(hierarchy, storage=storage)
        with tempfile.TemporaryDirectory() as directory:
            bundle = save_basin_spill_bundle(directory, hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=storage, expected_storage_identity=storage["identity_sha256"], reach_networks=[reaches])
            path = Path(directory) / "bundle.json"
            load_basin_spill_bundle(path, expected_sha256=file_sha256(path), expected_identity=bundle["identity_sha256"],
                hierarchy=hierarchy, storage=storage, reach_networks=[reaches])
            records = json.loads((Path(directory) / "faces-0000.json").read_bytes())
            self.assertEqual(records[0]["stored_whole_run_flux"]["reverse_m3"], 1.)

    def test_known_versions_preserve_original_metadata_and_identity(self):
        for algorithm, profile in VERSIONS:
            with self.subTest(algorithm=algorithm, profile=profile):
                _, storage = fixture(algorithm, profile)
                original = json.dumps(storage["metadata"], sort_keys=True)
                self.assertTrue(validate_saved_storage(storage))
                self.assertEqual(json.dumps(storage["metadata"], sort_keys=True), original)
                self.assertEqual(storage["identity_sha256"], identity(storage["arrays"], storage["metadata"]))
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "storage.npz"
                    save_storage(path, storage)
                    loaded = load_storage(path, expected_sha256=file_sha256(path), expected_identity=storage["identity_sha256"])
                    self.assertEqual(loaded["metadata"], storage["metadata"])

    def test_v6_pinned_cold_read_to_reaches_spill_edges(self):
        hierarchy, storage = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storage.npz"
            save_storage(path, storage)
            loaded = load_storage(path, expected_sha256=file_sha256(path), expected_identity=storage["identity_sha256"])
            self.assertEqual(loaded["metadata"], storage["metadata"])
            reaches = make_surface_reaches(hierarchy, threshold_area_m2=900, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=loaded, expected_storage_identity=loaded["identity_sha256"])
            reach_path = Path(directory) / "reaches.json"
            save_surface_reaches(reaches, reach_path)
            load_surface_reaches(reach_path, expected_sha256=file_sha256(reach_path), expected_identity=reaches["identity_sha256"], hierarchy=hierarchy, storage=loaded)
            spill_directory = Path(directory) / "spill"
            bundle = save_basin_spill_bundle(spill_directory, hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=loaded, expected_storage_identity=loaded["identity_sha256"], reach_networks=[reaches])
            bundle_path = spill_directory / "bundle.json"
            load_basin_spill_bundle(bundle_path, expected_sha256=file_sha256(bundle_path), expected_identity=bundle["identity_sha256"], hierarchy=hierarchy, storage=loaded, reach_networks=[reaches])
            edges = build_td_surface_river_edges(hierarchy, storage=loaded)
            self.assertTrue(edges)
            self.assertFalse(reaches["flags"]["hydraulic_ready"])
            self.assertFalse(bundle["flags"]["transient_converged"])

    def test_fresh_subprocess_rejects_solver_and_numba_imports(self):
        hierarchy, storage = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_storage(root / "storage.npz", storage)
            save_basin_hierarchy(root / "hierarchy.npz", hierarchy)
            code = '''import sys
import importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "numba" or fullname.startswith("numba.") or fullname in {"terrain_pipeline.td_basin_storage", "terrain_pipeline.td_basin_storage_implicit", "terrain_pipeline.td_basin_storage_refinement", "terrain_pipeline.td_basin_storage_v3", "terrain_pipeline.td_basin_storage_v4", "terrain_pipeline.td_basin_storage_v5", "terrain_pipeline.td_basin_storage_v6", "terrain_pipeline.td_basin_transport_v6"}:
            raise AssertionError("solver import: " + fullname)
sys.meta_path.insert(0, Block())
from pathlib import Path
from terrain_pipeline.td_basin_storage_dispatch_io import load_storage
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_surface_reaches import make_surface_reaches
from terrain_pipeline.td_basin_spill_network import make_basin_spill_network
from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges
root=Path(sys.argv[1])
storage=load_storage(root/'storage.npz',expected_sha256=sys.argv[2],expected_identity=sys.argv[3])
hierarchy=load_basin_hierarchy(root/'hierarchy.npz',expected_sha256=sys.argv[4],expected_identity=sys.argv[5])
reaches=make_surface_reaches(hierarchy,threshold_area_m2=900,expected_hierarchy_identity=hierarchy['identity_sha256'],storage=storage,expected_storage_identity=storage['identity_sha256'])
make_basin_spill_network(hierarchy,expected_hierarchy_identity=hierarchy['identity_sha256'],storage=storage,expected_storage_identity=storage['identity_sha256'],reach_networks=[reaches])
build_td_surface_river_edges(hierarchy,storage=storage)
assert not any(name.startswith('numba') for name in sys.modules)
'''
            completed = subprocess.run([sys.executable, "-c", code, str(root), file_sha256(root / "storage.npz"), storage["identity_sha256"],
                file_sha256(root / "hierarchy.npz"), hierarchy["identity_sha256"]], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_unknown_algorithm_profile_and_rehashed_semantics_refused(self):
        for name, value in (("algorithm", "unknown"), ("work_profile", "unknown"), ("positivity_cfl", .99),
                            ("hydraulic_ready", True), ("saved_time_semantics", "fake")):
            with self.subTest(name=name):
                _, storage = fixture()
                storage["metadata"][name] = value
                storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
                with self.assertRaises(ValueError):
                    validate_saved_storage(storage)

    def test_rehashed_water_ledger_and_external_pins_refused(self):
        _, storage = fixture()
        storage["arrays"]["depth_m"][1, 0] = 1
        storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
        with self.assertRaises(ValueError):
            validate_saved_storage(storage)
        _, storage = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storage.npz"
            save_storage(path, storage)
            for digest, identifier in (("0" * 64, storage["identity_sha256"]), (file_sha256(path), "0" * 64)):
                with self.assertRaises(ValueError):
                    load_storage(path, expected_sha256=digest, expected_identity=identifier)


if __name__ == "__main__":
    unittest.main()
