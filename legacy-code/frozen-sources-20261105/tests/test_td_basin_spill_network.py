import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_basin_storage import simulate_basin_storage
from terrain_pipeline.td_surface_reaches import _plain, _hash
from terrain_pipeline.td_basin_spill_network import (
    make_basin_spill_network, save_basin_spill_network, load_basin_spill_network,
    save_basin_spill_bundle, load_basin_spill_bundle,
)
from tests.test_td_surface_reaches import fixture, build


def spill(hierarchy, storage=None):
    return make_basin_spill_network(hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
        storage=storage, expected_storage_identity=None if storage is None else storage["identity_sha256"],
        reach_networks=[build(hierarchy, storage=storage)])


class BasinSpillTests(unittest.TestCase):
    def sharded_fixture(self, directory, height=None, protected=None):
        hierarchy = fixture([[0, 2, 0], [0, 2, 0]] if height is None else height, protected)
        storage = simulate_basin_storage(hierarchy, np.ones(2) * .1, dt_s=1)
        network = build(hierarchy, storage=storage)
        result = save_basin_spill_bundle(directory, hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
            storage=storage, expected_storage_identity=storage["identity_sha256"], reach_networks=[network])
        path = Path(directory) / "bundle.json"
        return path, dict(expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"], hierarchy=hierarchy, storage=storage, reach_networks=[network])

    def repin_bundle(self, path, kwargs, value):
        value.pop("identity_sha256", None)
        value["identity_sha256"] = _hash(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        kwargs.update(expected_sha256=file_sha256(path), expected_identity=value["identity_sha256"])

    def test_v2_path_traversal_absolute_and_registry_order(self):
        for name in ("../outside.json", "D:/outside.json", "faces-0001.json", "sub/faces-0000.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path, kwargs = self.sharded_fixture(directory)
                value = json.loads(path.read_bytes())
                value["face_chunks"][0]["file"] = name
                self.repin_bundle(path, kwargs, value)
                with self.assertRaises(ValueError):
                    load_basin_spill_bundle(path, **kwargs)

    def test_v2_deleted_unlisted_and_extra_registered_chunk(self):
        for operation in ("delete", "unlisted", "registered"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path, kwargs = self.sharded_fixture(directory)
                value = json.loads(path.read_bytes())
                if operation == "delete":
                    (path.parent / "faces-0000.json").unlink()
                else:
                    (path.parent / "faces-0001.json").write_bytes((path.parent / "faces-0000.json").read_bytes())
                    if operation == "registered":
                        pin = dict(value["face_chunks"][0], file="faces-0001.json")
                        value["face_chunks"].append(pin)
                        self.repin_bundle(path, kwargs, value)
                with self.assertRaises(ValueError):
                    load_basin_spill_bundle(path, **kwargs)

    def test_v2_rehashed_face_payload_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            path, kwargs = self.sharded_fixture(directory)
            value = json.loads(path.read_bytes())
            pin = value["face_chunks"][0]
            chunk = path.parent / pin["file"]
            records = json.loads(chunk.read_bytes())
            records[0]["physical_face_sill_m"] += 1
            chunk.write_text(json.dumps(records), encoding="utf-8")
            pin.update(expected_sha256=file_sha256(chunk), identity_sha256=_hash(records), bytes=chunk.stat().st_size)
            self.repin_bundle(path, kwargs, value)
            with self.assertRaises(ValueError):
                load_basin_spill_bundle(path, **kwargs)

    def test_v2_rehashed_leaf_pair_metadata_tamper(self):
        for field, replacement in (("leaf_ids", [999, 1000]), ("all_face_indices", [999]),
                                   ("minimum_face_indices", []), ("minimum_physical_sill_m", 99),
                                   ("forward_leaf0_to_leaf1_m3", 99), ("net_leaf0_to_leaf1_m3", 99)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                path, kwargs = self.sharded_fixture(directory)
                value = json.loads(path.read_bytes())
                value["contribution_leaf_graph"]["pairs"][0][field] = replacement
                self.repin_bundle(path, kwargs, value)
                with self.assertRaises(ValueError):
                    load_basin_spill_bundle(path, **kwargs)

    def test_v2_cold_read_no_generation_external_pins_and_readonly(self):
        with tempfile.TemporaryDirectory() as directory:
            path, kwargs = self.sharded_fixture(directory)
            with patch("terrain_pipeline.td_basin_spill_network.save_basin_spill_bundle", side_effect=AssertionError("save")), patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy", side_effect=AssertionError("generate")), patch("terrain_pipeline.td_basin_storage.simulate_basin_storage", side_effect=AssertionError("solve")):
                loaded = load_basin_spill_bundle(path, **kwargs)
            with self.assertRaises(TypeError):
                loaded["contribution_leaf_graph"]["pairs"][0]["gross_m3"] = 1
            for field in ("expected_sha256", "expected_identity"):
                changed = dict(kwargs)
                changed[field] = "0" * 64
                with self.subTest(field=field), self.assertRaises(ValueError):
                    load_basin_spill_bundle(path, **changed)

    def test_v2_leaf_ties_unique_coverage_direction_and_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            path, kwargs = self.sharded_fixture(directory)
            loaded = load_basin_spill_bundle(path, **kwargs)
            hierarchy, storage = kwargs["hierarchy"], kwargs["storage"]
            arrays = hierarchy["arrays"]
            leaf = arrays["contribution_owner"].ravel()
            seen = []
            divergence = np.zeros(len(arrays["node_parent"]))
            for pair in loaded["contribution_leaf_graph"]["pairs"]:
                first_leaf, second_leaf = pair["leaf_ids"]
                forward, reverse = 0., 0.
                for face in pair["all_face_indices"]:
                    seen.append(face)
                    first, second = arrays["face_cells"][face]
                    self.assertEqual(sorted((int(leaf[first]), int(leaf[second]))), [first_leaf, second_leaf])
                    along = storage["arrays"]["face_forward_m3"][face]
                    against = storage["arrays"]["face_reverse_m3"][face]
                    if leaf[first] != first_leaf:
                        along, against = against, along
                    forward += along
                    reverse += against
                self.assertEqual(pair["forward_leaf0_to_leaf1_m3"], forward)
                self.assertEqual(pair["reverse_leaf1_to_leaf0_m3"], reverse)
                self.assertEqual(len(pair["minimum_face_indices"]), 2)
                divergence[first_leaf] -= forward - reverse
                divergence[second_leaf] += forward - reverse
            expected_faces = [face for face, cells in enumerate(arrays["face_cells"]) if leaf[cells[0]] != leaf[cells[1]]]
            self.assertEqual(sorted(seen), expected_faces)
            self.assertEqual(len(seen), len(set(seen)))
            net = storage["arrays"]["face_forward_m3"] - storage["arrays"]["face_reverse_m3"]
            direct = np.zeros_like(divergence)
            for face, cells in enumerate(arrays["face_cells"]):
                direct[leaf[cells[0]]] -= net[face]
                direct[leaf[cells[1]]] += net[face]
            np.testing.assert_allclose(divergence, direct, atol=1e-12)

    def test_v2_leaf_protected_and_unknown_not_traversable(self):
        for height, protected in (([[0, 2, 0]], np.array([[False, True, False]])),
                                  ([[0, 2, 0], [np.nan, np.nan, np.nan]], None)):
            with tempfile.TemporaryDirectory() as directory:
                path, kwargs = self.sharded_fixture(directory, height, protected)
                loaded = load_basin_spill_bundle(path, **kwargs)
                self.assertTrue(all(not pair["potential_connection_allowed"] for pair in loaded["contribution_leaf_graph"]["pairs"]))

    def test_v2_leaf_node_area_terminal_join_and_stable_pair_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path, kwargs = self.sharded_fixture(directory)
            result = load_basin_spill_bundle(path, **kwargs)
            graph = result["contribution_leaf_graph"]
            self.assertEqual(sum(node["area_m2"] for node in graph["leaf_nodes"]), 6)
            leaves = {node["leaf_id"] for node in graph["leaf_nodes"]}
            self.assertTrue(all(join["contribution_leaf_id"] in leaves for case in result["reach_cases"] for join in case["terminal_owner_joins"]))
            pair = graph["pairs"][0]
            self.assertEqual(pair["pair_id"], "leaf-pair:" + _hash(sorted(pair["stable_leaf_ids"])))
            hierarchy = kwargs["hierarchy"]
            metadata = dict(hierarchy["metadata"], max_curve_entries=hierarchy["metadata"]["max_curve_entries"] + 1)
            changed = {"arrays": hierarchy["arrays"], "metadata": metadata, "identity_sha256": identity(hierarchy["arrays"], metadata)}
            from terrain_pipeline.td_basin_spill_network import _leaf_graph
            self.assertEqual(pair["pair_id"], _leaf_graph(changed, None)["pairs"][0]["pair_id"])

    def test_v2_duplicate_json_and_nonfinite_rejected(self):
        for payload in (b'{"schema":1,"schema":2}', b'{"value":NaN}'):
            with tempfile.TemporaryDirectory() as directory:
                path, kwargs = self.sharded_fixture(directory)
                path.write_bytes(payload)
                kwargs["expected_sha256"] = file_sha256(path)
                with self.assertRaises(ValueError):
                    load_basin_spill_bundle(path, **kwargs)

    def test_sharded_cold_read_leaf_pair_and_tamper(self):
        hierarchy = fixture([[0, 2, 0]])
        storage = simulate_basin_storage(hierarchy, np.ones(2) * .1, dt_s=1)
        network = build(hierarchy, storage=storage)
        with tempfile.TemporaryDirectory() as directory:
            result = save_basin_spill_bundle(directory, hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"],
                storage=storage, expected_storage_identity=storage["identity_sha256"], reach_networks=[network])
            path = Path(directory) / "bundle.json"
            kwargs = dict(expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"], hierarchy=hierarchy, storage=storage, reach_networks=[network])
            loaded = load_basin_spill_bundle(path, **kwargs)
            graph = loaded["contribution_leaf_graph"]
            self.assertEqual(len(graph["pairs"]), 1)
            self.assertEqual(graph["unique_cross_leaf_faces"], 1)
            chunk_path = Path(directory) / loaded["face_chunks"][0]["file"]
            chunk_path.write_bytes(b"[]")
            with self.assertRaises(ValueError):
                load_basin_spill_bundle(path, **kwargs)

    def test_two_basins_threshold_and_unique_faces(self):
        hierarchy = fixture([[0, 2, 0]])
        result = spill(hierarchy)
        self.assertEqual(len(result["spills"]), 2)
        self.assertEqual(len({item["face_id"] for item in result["spills"]}), 2)
        for item in result["spills"]:
            self.assertEqual(item["face_sill_m"], 2)
            self.assertEqual(item["merge_birth_m"], 2)
            self.assertTrue(item["potential_only"])
            self.assertTrue(item["potential_connection_allowed"])
        stages = [result["basin_nodes"][node] for item in result["spills"] for node in item["merge_child_ids"] if node is not None]
        self.assertTrue(stages)
        self.assertTrue(all(stage["stage_capacity_m3"] == 2 for stage in stages))

    def test_protection_and_unknown_refuse_connections(self):
        protected = spill(fixture([[0, 2, 0]], np.array([[False, True, False]])))
        self.assertTrue(all(not item["potential_connection_allowed"] for item in protected["spills"]))
        unknown = spill(fixture([[0, 2, 0], [np.nan, np.nan, np.nan]]))
        self.assertTrue(all("unknown_owner_subtree" in item["rejection_reasons"] for item in unknown["spills"]))

    def test_storage_exact_directional_integrals(self):
        hierarchy = fixture([[0, 2, 0]])
        storage = simulate_basin_storage(hierarchy, np.ones(2) * .1, dt_s=1)
        result = spill(hierarchy, storage)
        for item in result["spills"]:
            face = item["face_index"]
            flux = item["stored_whole_run_flux"]
            self.assertEqual(flux["forward_m3"], storage["arrays"]["face_forward_m3"][face])
            self.assertEqual(flux["reverse_m3"], storage["arrays"]["face_reverse_m3"][face])
            self.assertEqual(flux["gross_m3"], flux["forward_m3"] + flux["reverse_m3"])
        self.assertFalse(result["flux_scope"]["spill_onset_known"])

    def test_rehashed_wrong_lca_refused(self):
        hierarchy = fixture([[0, 2, 0]])
        arrays = dict(hierarchy["arrays"])
        arrays["face_merge_node"] = arrays["face_merge_node"].copy()
        arrays["face_merge_node"][0] = 0
        changed = {"arrays": arrays, "metadata": hierarchy["metadata"], "identity_sha256": identity(arrays, hierarchy["metadata"])}
        with self.assertRaises(ValueError):
            spill(changed)

    def test_external_identity_and_storage_geometry_refused(self):
        hierarchy = fixture([[0, 2, 0]])
        with self.assertRaises(ValueError):
            make_basin_spill_network(hierarchy, expected_hierarchy_identity="0" * 64)
        storage = simulate_basin_storage(hierarchy, np.zeros(1), dt_s=1)
        changed = {"arrays": storage["arrays"], "metadata": dict(storage["metadata"])}
        changed["metadata"]["origin_m_xz"] = [10., 0.]
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            spill(hierarchy, changed)

    def test_physical_face_id_independent_of_derived_hierarchy(self):
        hierarchy = fixture([[0, 2, 0]])
        original = spill(hierarchy)
        metadata = dict(hierarchy["metadata"])
        metadata["max_curve_entries"] += 1
        changed = {"arrays": hierarchy["arrays"], "metadata": metadata,
                   "identity_sha256": identity(hierarchy["arrays"], metadata)}
        derived = spill(changed)
        self.assertNotEqual(original["hierarchy_identity_sha256"], derived["hierarchy_identity_sha256"])
        self.assertEqual([item["face_id"] for item in original["spills"]], [item["face_id"] for item in derived["spills"]])
        self.assertTrue(all(item["lowest_allowed_owner_pair_face"] for item in original["spills"]))

    def test_cold_read_no_generation_and_external_pin(self):
        hierarchy = fixture([[0, 2, 0]])
        network = build(hierarchy)
        result = spill(hierarchy)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spill.json"
            save_basin_spill_network(result, path)
            with patch("terrain_pipeline.td_basin_spill_network.make_basin_spill_network", side_effect=AssertionError("generation")), patch("terrain_pipeline.td_basin_storage.simulate_basin_storage", side_effect=AssertionError("solve")):
                loaded = load_basin_spill_network(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"], hierarchy=hierarchy, reach_networks=[network])
            self.assertEqual(_plain(loaded), _plain(result))
            with self.assertRaises(TypeError):
                loaded["flags"]["readonly"] = False
            with self.assertRaises(ValueError):
                load_basin_spill_network(path, expected_sha256="0" * 64, expected_identity=result["identity_sha256"], hierarchy=hierarchy, reach_networks=[network])

    def test_rehashed_semantic_tamper_refused(self):
        hierarchy = fixture([[0, 2, 0]])
        network = build(hierarchy)
        original = spill(hierarchy)
        mutations = [lambda value: value["grid"].update(spacing_m=2),
                     lambda value: value["spills"][0].update(face_sill_m=9),
                     lambda value: value["spills"].append(value["spills"][0]),
                     lambda value: value["basin_nodes"][0].update(parent_id=-1),
                     lambda value: value["reach_cases"][0]["terminal_owner_joins"][0].update(owner_id=999),
                     lambda value: value["flags"].update(transient_converged=True),
                     lambda value: value["flux_scope"].update(elapsed_s=999)]
        with tempfile.TemporaryDirectory() as directory:
            for index, mutate in enumerate(mutations):
                changed = _plain(original)
                mutate(changed)
                changed.pop("identity_sha256")
                changed["identity_sha256"] = _hash(changed)
                path = Path(directory) / f"changed-{index}.json"
                save_basin_spill_network(changed, path)
                with self.subTest(index=index), self.assertRaises(ValueError):
                    load_basin_spill_network(path, expected_sha256=file_sha256(path), expected_identity=changed["identity_sha256"], hierarchy=hierarchy, reach_networks=[network])


if __name__ == "__main__":
    unittest.main()
