"""M4 tests.test_basin_storage_io; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from dataclasses import asdict as _m4_test_td_basin_storage_dispatch_io_asdict
from pathlib import Path as _m4_test_td_basin_storage_dispatch_io_Path
from terrain_pipeline.basin_storage import VERSIONS as _m4_test_td_basin_storage_dispatch_io_VERSIONS
from terrain_pipeline.basin_storage import dispatch_load_storage as _m4_test_td_basin_storage_dispatch_io_load_storage
from terrain_pipeline.basin_storage import dispatch_save_storage as _m4_test_td_basin_storage_dispatch_io_save_storage
from terrain_pipeline.basin_storage import dispatch_validate_saved_storage as _m4_test_td_basin_storage_dispatch_io_validate_saved_storage
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_dispatch_io_make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_dispatch_io_build_basin_hierarchy
from terrain_pipeline.basin_topology import load_basin_spill_bundle as _m4_test_td_basin_storage_dispatch_io_load_basin_spill_bundle
from terrain_pipeline.basin_topology import save_basin_hierarchy as _m4_test_td_basin_storage_dispatch_io_save_basin_hierarchy
from terrain_pipeline.basin_topology import save_basin_spill_bundle as _m4_test_td_basin_storage_dispatch_io_save_basin_spill_bundle
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_dispatch_io_file_sha256
from terrain_pipeline.common_infra import identity as _m4_test_td_basin_storage_dispatch_io_identity
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_basin_storage_dispatch_io_RunoffParameters
from terrain_pipeline.td_surface_reaches import load_surface_reaches as _m4_test_td_basin_storage_dispatch_io_load_surface_reaches
from terrain_pipeline.td_surface_reaches import make_surface_reaches as _m4_test_td_basin_storage_dispatch_io_make_surface_reaches
from terrain_pipeline.td_surface_reaches import save_surface_reaches as _m4_test_td_basin_storage_dispatch_io_save_surface_reaches
from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges as _m4_test_td_basin_storage_dispatch_io_build_td_surface_river_edges
from unittest.mock import patch as _m4_test_td_basin_storage_dispatch_io_patch
import json as _m4_test_td_basin_storage_dispatch_io_json
import numpy as _m4_test_td_basin_storage_dispatch_io_np
import subprocess as _m4_test_td_basin_storage_dispatch_io_subprocess
import sys as _m4_test_td_basin_storage_dispatch_io_sys
import tempfile as _m4_test_td_basin_storage_dispatch_io_tempfile
import unittest as _m4_test_td_basin_storage_dispatch_io_unittest

# --- tests/test_td_basin_storage_dispatch_io.py:27 ---
def basin_storage_dispatch_io_fixture(version="D4-threshold-symmetric-forcing-SSPRK2-v6", profile="v6-simultaneous-SSPRK2-6e9-v1"):
    hierarchy = _m4_test_td_basin_storage_dispatch_io_build_basin_hierarchy(_m4_test_td_basin_storage_dispatch_io_make_td_source(_m4_test_td_basin_storage_dispatch_io_np.array([[0., 2., 0.]]), spacing_m=30))
    topology = hierarchy["arrays"]
    cells, faces = 3, len(topology["face_cells"])
    arrays = {name: topology[name] for name in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells")}
    for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
        arrays[name] = _m4_test_td_basin_storage_dispatch_io_np.zeros((2, cells))
    for name in ("rain_mm_h", "rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
                 "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3"):
        arrays[name] = _m4_test_td_basin_storage_dispatch_io_np.zeros((1, cells))
    for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        arrays[name] = _m4_test_td_basin_storage_dispatch_io_np.zeros(faces)
    arrays.update(boundary_width_m=_m4_test_td_basin_storage_dispatch_io_np.zeros(0), routed_volume_m3=_m4_test_td_basin_storage_dispatch_io_np.zeros(cells), wet_duration_s=_m4_test_td_basin_storage_dispatch_io_np.zeros(cells), wet_pool_count=_m4_test_td_basin_storage_dispatch_io_np.zeros(2, _m4_test_td_basin_storage_dispatch_io_np.int64))
    metadata = {"schema": "td-basin-storage-v1", "algorithm": version,
                "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": 30., "origin_m_xz": [0, 0],
                "dt_s": 1., "substep_s": 1., "substeps": 1,
                "parameters": {"substep_s": 1., "face_conductance_m_s": .6, "surface_evaporation_mm_h": 0.,
                    "wet_threshold_m": 1e-9, "max_substeps": 20000, "max_work_face_steps": 500000000},
                "runoff_parameters": _m4_test_td_basin_storage_dispatch_io_asdict(_m4_test_td_basin_storage_dispatch_io_RunoffParameters(initial_soil_mm=0)),
                "hydraulic_ready": False, "transient_converged": False, "morphology_flux_ready": False, "natural_outlet_verified": False}
    if profile is not None:
        metadata["work_profile"] = profile
    if version.endswith(("-v5", "-v6")):
        metadata.update(forcing_semantics="runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
            saved_time_semantics="state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
            activity_semantics="RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity" if version.endswith("-v6") else "each face visited twice for substep_s/2 within transport; sum directional activity<=substep_s; forcing halves add no activity")
    if version.endswith("-v6"):
        metadata["positivity_cfl"] = 2 * .6 / 30
    return hierarchy, {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_test_td_basin_storage_dispatch_io_identity(arrays, metadata)}

# --- tests/test_td_basin_storage_dispatch_io.py:58 ---
class BasinStorageDispatchIoStorageDispatchTests(_m4_test_td_basin_storage_dispatch_io_unittest.TestCase):
    def test_rehashed_substep_count_and_actual_duration_refused(self):
        for name, value in (("substeps", 1), ("substep_s", .5)):
            _, storage = basin_storage_dispatch_io_fixture()
            storage["metadata"]["dt_s"] = 2.5
            storage["metadata"]["substeps"] = 3
            storage["metadata"]["substep_s"] = 2.5 / 3
            storage["metadata"]["positivity_cfl"] = 2 * .6 * (2.5 / 3) / 30
            storage["metadata"][name] = value
            storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "substep"):
                _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)

    def test_rehashed_boundary_and_undeclared_outflow_refused(self):
        cases = [(_m4_test_td_basin_storage_dispatch_io_np.array([0., 1.]), _m4_test_td_basin_storage_dispatch_io_np.array([60., 60.])),
                 (_m4_test_td_basin_storage_dispatch_io_np.array([0, 0], _m4_test_td_basin_storage_dispatch_io_np.int64), _m4_test_td_basin_storage_dispatch_io_np.array([90., 90.])),
                 (_m4_test_td_basin_storage_dispatch_io_np.array([3], _m4_test_td_basin_storage_dispatch_io_np.int64), _m4_test_td_basin_storage_dispatch_io_np.array([30.])),
                 (_m4_test_td_basin_storage_dispatch_io_np.array([0], _m4_test_td_basin_storage_dispatch_io_np.int64), _m4_test_td_basin_storage_dispatch_io_np.array([30.]))]
        for boundary, widths in cases:
            _, storage = basin_storage_dispatch_io_fixture()
            storage["arrays"].update(boundary_cells=boundary, boundary_width_m=widths)
            storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
            with self.subTest(boundary=boundary.tolist()), self.assertRaises(ValueError):
                _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)
        _, storage = basin_storage_dispatch_io_fixture()
        storage["arrays"]["boundary_outflow_m3"][0, 1] = 1
        storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
        with self.assertRaisesRegex(ValueError, "undeclared"):
            _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)

    def test_rehashed_duplicate_faces_receiver_and_pool_refused(self):
        mutations = [lambda arrays: arrays.update(face_cells=_m4_test_td_basin_storage_dispatch_io_np.array([[0, 1], [1, 0]], _m4_test_td_basin_storage_dispatch_io_np.int64)),
                     lambda arrays: arrays.update(receiver=_m4_test_td_basin_storage_dispatch_io_np.array([-1., 0., -1.])),
                     lambda arrays: arrays.update(receiver=_m4_test_td_basin_storage_dispatch_io_np.array([2, 0, -1], _m4_test_td_basin_storage_dispatch_io_np.int64)),
                     lambda arrays: arrays.update(wet_pool_count=_m4_test_td_basin_storage_dispatch_io_np.array([-1, 0], _m4_test_td_basin_storage_dispatch_io_np.int64)),
                     lambda arrays: arrays.update(wet_pool_count=_m4_test_td_basin_storage_dispatch_io_np.array([0., 0.]))]
        for mutate in mutations:
            _, storage = basin_storage_dispatch_io_fixture()
            mutate(storage["arrays"])
            storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
            with self.assertRaises(ValueError):
                _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)
        _, storage = basin_storage_dispatch_io_fixture()
        storage["arrays"]["height_m"] = _m4_test_td_basin_storage_dispatch_io_np.zeros((1, 3))
        storage["arrays"]["receiver"] = _m4_test_td_basin_storage_dispatch_io_np.array([1, 0, -1], _m4_test_td_basin_storage_dispatch_io_np.int64)
        storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
        with self.assertRaisesRegex(ValueError, "cycle"):
            _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)

    def test_v6_review_pinned_load_no_generation(self):
        from terrain_pipeline.basin_storage import save_td_source as save_td_source
        from terrain_pipeline.geology import make_material_field
        from terrain_pipeline.geology import save_material_field
        from terrain_pipeline.basin_storage import load_review_inputs as load_review_inputs
        from terrain_pipeline.basin_storage import make_basin_review as make_basin_review
        hierarchy, storage = basin_storage_dispatch_io_fixture()
        source = _m4_test_td_basin_storage_dispatch_io_make_td_source(_m4_test_td_basin_storage_dispatch_io_np.array([[0., 2., 0.]]), spacing_m=30)
        material = make_material_field((1, 3), origin_m_xz=(0, 0), spacing_m=30)
        with _m4_test_td_basin_storage_dispatch_io_tempfile.TemporaryDirectory() as directory:
            records = {}
            for role, bundle, writer in (("source", source, lambda path, value: save_td_source(path, value)),
                                         ("hierarchy", hierarchy, _m4_test_td_basin_storage_dispatch_io_save_basin_hierarchy), ("storage", storage, _m4_test_td_basin_storage_dispatch_io_save_storage),
                                         ("material", material, lambda path, value: save_material_field(value, path))):
                path = _m4_test_td_basin_storage_dispatch_io_Path(directory) / (role + ".npz")
                writer(path, bundle)
                records[role] = dict(path=str(path), expected_sha256=_m4_test_td_basin_storage_dispatch_io_file_sha256(path), expected_identity=bundle["identity_sha256"])
            with _m4_test_td_basin_storage_dispatch_io_patch('terrain_pipeline.geology.make_material_field', side_effect=AssertionError("generate")), _m4_test_td_basin_storage_dispatch_io_patch('terrain_pipeline.basin_topology.build_basin_hierarchy', side_effect=AssertionError("generate")), _m4_test_td_basin_storage_dispatch_io_patch('terrain_pipeline.basin_storage.dispatch_save_storage', side_effect=AssertionError("write")):
                inputs = load_review_inputs(records)
                review = make_basin_review(inputs)
            self.assertEqual(inputs["storage"]["metadata"], storage["metadata"])
            self.assertEqual(review["water"]["hydro_identity_sha256"], storage["identity_sha256"])
            self.assertFalse(review["flags"]["transient_converged"])
            code = 'import sys, importlib.abc, json\nclass Block(importlib.abc.MetaPathFinder):\n    def find_spec(self, fullname, path=None, target=None):\n        if fullname in {\'terrain_pipeline.td_basin_storage\', \'terrain_pipeline.td_basin_storage_v4\', \'terrain_pipeline.td_basin_storage_v5\', \'terrain_pipeline.td_basin_storage_v6\', \'terrain_pipeline.td_basin_transport_v6\'}:\n            raise AssertionError(\'solver import: \'+fullname)\nsys.meta_path.insert(0,Block())\nfrom terrain_pipeline.basin_storage import load_review_inputs as load_review_inputs; from terrain_pipeline.basin_storage import make_basin_review as make_basin_review\nreview=make_basin_review(load_review_inputs(json.loads(sys.argv[1])))\nassert review[\'flags\'][\'transient_converged\'] is False\nassert "terrain_pipeline.basin_storage" in sys.modules\n'
            completed = _m4_test_td_basin_storage_dispatch_io_subprocess.run([_m4_test_td_basin_storage_dispatch_io_sys.executable, "-c", code, _m4_test_td_basin_storage_dispatch_io_json.dumps(records)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_nonzero_v6_reverse_exchange_survives_all_adapters(self):
        hierarchy, storage = basin_storage_dispatch_io_fixture()
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
        storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(arrays, storage["metadata"])
        self.assertTrue(_m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage))
        reaches = _m4_test_td_basin_storage_dispatch_io_make_surface_reaches(hierarchy, threshold_area_m2=900, expected_hierarchy_identity=hierarchy["identity_sha256"],
            storage=storage, expected_storage_identity=storage["identity_sha256"])
        reverse_edges = [edge for reach in reaches["reaches"] for edge in reach["edges"] if edge["face_index"] == 0]
        self.assertEqual(reverse_edges[0]["stored_flux"]["reverse_m3"], 1.)
        _m4_test_td_basin_storage_dispatch_io_build_td_surface_river_edges(hierarchy, storage=storage)
        with _m4_test_td_basin_storage_dispatch_io_tempfile.TemporaryDirectory() as directory:
            bundle = _m4_test_td_basin_storage_dispatch_io_save_basin_spill_bundle(directory, hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=storage, expected_storage_identity=storage["identity_sha256"], reach_networks=[reaches])
            path = _m4_test_td_basin_storage_dispatch_io_Path(directory) / "bundle.json"
            _m4_test_td_basin_storage_dispatch_io_load_basin_spill_bundle(path, expected_sha256=_m4_test_td_basin_storage_dispatch_io_file_sha256(path), expected_identity=bundle["identity_sha256"],
                hierarchy=hierarchy, storage=storage, reach_networks=[reaches])
            records = _m4_test_td_basin_storage_dispatch_io_json.loads((_m4_test_td_basin_storage_dispatch_io_Path(directory) / "faces-0000.json").read_bytes())
            self.assertEqual(records[0]["stored_whole_run_flux"]["reverse_m3"], 1.)

    def test_known_versions_preserve_original_metadata_and_identity(self):
        for algorithm, profile in _m4_test_td_basin_storage_dispatch_io_VERSIONS:
            with self.subTest(algorithm=algorithm, profile=profile):
                _, storage = basin_storage_dispatch_io_fixture(algorithm, profile)
                original = _m4_test_td_basin_storage_dispatch_io_json.dumps(storage["metadata"], sort_keys=True)
                self.assertTrue(_m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage))
                self.assertEqual(_m4_test_td_basin_storage_dispatch_io_json.dumps(storage["metadata"], sort_keys=True), original)
                self.assertEqual(storage["identity_sha256"], _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"]))
                with _m4_test_td_basin_storage_dispatch_io_tempfile.TemporaryDirectory() as directory:
                    path = _m4_test_td_basin_storage_dispatch_io_Path(directory) / "storage.npz"
                    _m4_test_td_basin_storage_dispatch_io_save_storage(path, storage)
                    loaded = _m4_test_td_basin_storage_dispatch_io_load_storage(path, expected_sha256=_m4_test_td_basin_storage_dispatch_io_file_sha256(path), expected_identity=storage["identity_sha256"])
                    self.assertEqual(loaded["metadata"], storage["metadata"])

    def test_v6_pinned_cold_read_to_reaches_spill_edges(self):
        hierarchy, storage = basin_storage_dispatch_io_fixture()
        with _m4_test_td_basin_storage_dispatch_io_tempfile.TemporaryDirectory() as directory:
            path = _m4_test_td_basin_storage_dispatch_io_Path(directory) / "storage.npz"
            _m4_test_td_basin_storage_dispatch_io_save_storage(path, storage)
            loaded = _m4_test_td_basin_storage_dispatch_io_load_storage(path, expected_sha256=_m4_test_td_basin_storage_dispatch_io_file_sha256(path), expected_identity=storage["identity_sha256"])
            self.assertEqual(loaded["metadata"], storage["metadata"])
            reaches = _m4_test_td_basin_storage_dispatch_io_make_surface_reaches(hierarchy, threshold_area_m2=900, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=loaded, expected_storage_identity=loaded["identity_sha256"])
            reach_path = _m4_test_td_basin_storage_dispatch_io_Path(directory) / "reaches.json"
            _m4_test_td_basin_storage_dispatch_io_save_surface_reaches(reaches, reach_path)
            _m4_test_td_basin_storage_dispatch_io_load_surface_reaches(reach_path, expected_sha256=_m4_test_td_basin_storage_dispatch_io_file_sha256(reach_path), expected_identity=reaches["identity_sha256"], hierarchy=hierarchy, storage=loaded)
            spill_directory = _m4_test_td_basin_storage_dispatch_io_Path(directory) / "spill"
            bundle = _m4_test_td_basin_storage_dispatch_io_save_basin_spill_bundle(spill_directory, hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=loaded, expected_storage_identity=loaded["identity_sha256"], reach_networks=[reaches])
            bundle_path = spill_directory / "bundle.json"
            _m4_test_td_basin_storage_dispatch_io_load_basin_spill_bundle(bundle_path, expected_sha256=_m4_test_td_basin_storage_dispatch_io_file_sha256(bundle_path), expected_identity=bundle["identity_sha256"], hierarchy=hierarchy, storage=loaded, reach_networks=[reaches])
            edges = _m4_test_td_basin_storage_dispatch_io_build_td_surface_river_edges(hierarchy, storage=loaded)
            self.assertTrue(edges)
            self.assertFalse(reaches["flags"]["hydraulic_ready"])
            self.assertFalse(bundle["flags"]["transient_converged"])

    def test_fresh_subprocess_rejects_solver_and_numba_imports(self):
        hierarchy, storage = basin_storage_dispatch_io_fixture()
        with _m4_test_td_basin_storage_dispatch_io_tempfile.TemporaryDirectory() as directory:
            root = _m4_test_td_basin_storage_dispatch_io_Path(directory)
            _m4_test_td_basin_storage_dispatch_io_save_storage(root / "storage.npz", storage)
            _m4_test_td_basin_storage_dispatch_io_save_basin_hierarchy(root / "hierarchy.npz", hierarchy)
            code = 'import sys\nimport importlib.abc\nclass Block(importlib.abc.MetaPathFinder):\n    def find_spec(self, fullname, path=None, target=None):\n        if fullname in {"terrain_pipeline.td_basin_storage", "terrain_pipeline.td_basin_storage_implicit", "terrain_pipeline.td_basin_storage_refinement", "terrain_pipeline.td_basin_storage_v3", "terrain_pipeline.td_basin_storage_v4", "terrain_pipeline.td_basin_storage_v5", "terrain_pipeline.td_basin_storage_v6", "terrain_pipeline.td_basin_transport_v6"}:\n            raise AssertionError("solver import: " + fullname)\nsys.meta_path.insert(0, Block())\nfrom pathlib import Path\nfrom terrain_pipeline.basin_storage import dispatch_load_storage as load_storage\nfrom terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy\nfrom terrain_pipeline.td_surface_reaches import make_surface_reaches\nfrom terrain_pipeline.basin_topology import make_basin_spill_network as make_basin_spill_network\nfrom terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges\nroot=Path(sys.argv[1])\nstorage=load_storage(root/\'storage.npz\',expected_sha256=sys.argv[2],expected_identity=sys.argv[3])\nhierarchy=load_basin_hierarchy(root/\'hierarchy.npz\',expected_sha256=sys.argv[4],expected_identity=sys.argv[5])\nreaches=make_surface_reaches(hierarchy,threshold_area_m2=900,expected_hierarchy_identity=hierarchy[\'identity_sha256\'],storage=storage,expected_storage_identity=storage[\'identity_sha256\'])\nmake_basin_spill_network(hierarchy,expected_hierarchy_identity=hierarchy[\'identity_sha256\'],storage=storage,expected_storage_identity=storage[\'identity_sha256\'],reach_networks=[reaches])\nbuild_td_surface_river_edges(hierarchy,storage=storage)\nassert "terrain_pipeline.basin_storage" in sys.modules\n'
            completed = _m4_test_td_basin_storage_dispatch_io_subprocess.run([_m4_test_td_basin_storage_dispatch_io_sys.executable, "-c", code, str(root), _m4_test_td_basin_storage_dispatch_io_file_sha256(root / "storage.npz"), storage["identity_sha256"],
                _m4_test_td_basin_storage_dispatch_io_file_sha256(root / "hierarchy.npz"), hierarchy["identity_sha256"]], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_unknown_algorithm_profile_and_rehashed_semantics_refused(self):
        for name, value in (("algorithm", "unknown"), ("work_profile", "unknown"), ("positivity_cfl", .99),
                            ("hydraulic_ready", True), ("saved_time_semantics", "fake")):
            with self.subTest(name=name):
                _, storage = basin_storage_dispatch_io_fixture()
                storage["metadata"][name] = value
                storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
                with self.assertRaises(ValueError):
                    _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)

    def test_rehashed_water_ledger_and_external_pins_refused(self):
        _, storage = basin_storage_dispatch_io_fixture()
        storage["arrays"]["depth_m"][1, 0] = 1
        storage["identity_sha256"] = _m4_test_td_basin_storage_dispatch_io_identity(storage["arrays"], storage["metadata"])
        with self.assertRaises(ValueError):
            _m4_test_td_basin_storage_dispatch_io_validate_saved_storage(storage)
        _, storage = basin_storage_dispatch_io_fixture()
        with _m4_test_td_basin_storage_dispatch_io_tempfile.TemporaryDirectory() as directory:
            path = _m4_test_td_basin_storage_dispatch_io_Path(directory) / "storage.npz"
            _m4_test_td_basin_storage_dispatch_io_save_storage(path, storage)
            for digest, identifier in (("0" * 64, storage["identity_sha256"]), (_m4_test_td_basin_storage_dispatch_io_file_sha256(path), "0" * 64)):
                with self.assertRaises(ValueError):
                    _m4_test_td_basin_storage_dispatch_io_load_storage(path, expected_sha256=digest, expected_identity=identifier)
