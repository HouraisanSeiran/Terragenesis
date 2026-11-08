from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.surface_network_consumer import (
    _array_record, _file_hash, _geometry_gate, _local_q, _payload, _proof_gate,
    export_surface_network, load_surface_network_delivery, sample_surface_network,
    slice_surface_network_delivery, slice_surface_network_world,
)
from terrain_pipeline.surface_network_recovery import _fingerprint, _tree, recover_surface_network
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from tests.test_surface_network_recovery import recovery_case


DECLARATION = "Engineered synthetic terrain, local metre datum; not certified real geography"
DATUM = "synthetic-local-metre"


def rewrite_delivery(path, change):
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    with np.load(path / "hydro.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    change(manifest, arrays)
    np.savez_compressed(path / "hydro.npz", **arrays)
    manifest["arrays"] = _array_record(arrays)
    manifest["files"]["hydro.npz"] = _file_hash(path / "hydro.npz")
    manifest["content_id"] = digest({key: value for key, value in manifest.items() if key != "content_id"})
    (path / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def forbid_generation():
    stack = ExitStack()
    for target in (
            "terrain_pipeline.surface_network_consumer.validate_surface_network_recovery",
            "terrain_pipeline.surface_network_recovery.recover_surface_network",
            "terrain_pipeline.surface_network_recovery._surface",
            "terrain_pipeline.surface_network_recovery.prepare_surface_network",
            "terrain_pipeline.surface_network_prepare.prepare_surface_network",
            "terrain_pipeline.network_valley.prepare_network_valley",
            "terrain_pipeline.channel_reroute.reroute_channel",
            "terrain_pipeline.metric_channel_plan.plan_channel"):
        stack.enter_context(patch(target, side_effect=AssertionError("reader must not generate")))
    return stack


def rehash_surface_recovery(result):
    identity_record = deepcopy(result["surface"]["identity"])
    identity_record["parameters"]["output_sha256"] = digest({
        name: array_hash(value) for name, value in result["surface"]["arrays"].items()})
    identity_record["parameters"]["summary_sha256"] = digest(result["surface"]["summary"])
    identity = ArtifactIdentity(**identity_record)
    result["surface"]["identity"] = identity.record()
    result["surface"]["identity_sha256"] = identity.sha256
    result["identity_sha256"] = _fingerprint({key: value for key, value in result.items() if key != "identity_sha256"})
    return result


def forge_delivery_proof(path, result):
    loaded = load_surface_network_delivery(path)
    base, derived = loaded["base"], loaded["derived"]
    base_record = base.identity.record()
    base_record["parameters"]["recovery_sha256"] = result["identity_sha256"]
    base = replace(base, identity=ArtifactIdentity(**base_record))
    derived_record = derived.identity.record()
    derived_record["parameters"].update(recovery_sha256=result["identity_sha256"], base_content_id=base.content_id)
    derived = replace(derived, identity=ArtifactIdentity(**derived_record), source_artifact_id=base.content_id)
    for name, artifact in (("base", base), ("derived", derived)):
        (path / name / "manifest.json").write_text(json.dumps({**artifact.content_record(),
            "content_id": artifact.content_id}, sort_keys=True), encoding="utf-8")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    arrays = _payload(result)
    proof_arrays = {}
    manifest["proof"] = _tree(result, proof_arrays)
    arrays.update(proof_arrays)
    np.savez_compressed(path / "hydro.npz", **arrays)
    manifest.update(base_content_id=base.content_id, derived_content_id=derived.content_id,
                    recovery_sha256=result["identity_sha256"], arrays=_array_record(arrays))
    manifest["files"] = {name: _file_hash(path / name) for name in manifest["files"]}
    manifest["content_id"] = digest({key: value for key, value in manifest.items() if key != "content_id"})
    (path / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


class SurfaceNetworkConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {kind: recover_surface_network(**recovery_case(kind)) for kind in ("baseline", "valley", "reroute")}

    def publish(self, directory, kind="baseline", name="delivery"):
        path = Path(directory) / name
        export_surface_network(self.results[kind], DATUM, path, source_declaration=DECLARATION)
        return path

    def test_three_deliveries_generic_base_derived_and_hydrology(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in self.results:
                path = self.publish(directory, kind, kind)
                loaded = load_surface_network_delivery(path)
                source = self.results[kind]
                expected = source["surface"]["arrays"] if source["fine_ledger"] is None else source["fine_ledger"]["arrays"]
                h0 = expected["source_surface_m"]
                np.testing.assert_array_equal(loaded["base"].reference_elevation_m, h0)
                np.testing.assert_array_equal(loaded["derived"].reference_elevation_m, h0)
                np.testing.assert_allclose(loaded["derived"].reconstruct_positions_m()[1], expected["final_surface_m"])
                self.assertIsNone(loaded["base"].water)
                self.assertIsNone(loaded["derived"].water)
                loaded["derived"].verify_source(loaded["base"])

    def test_valley_base_is_h0_not_post_valley_h1(self):
        result = self.results["valley"]
        h0 = result["fine_ledger"]["arrays"]["source_surface_m"]
        h1 = result["surface"]["arrays"]["source_surface_m"]
        self.assertGreater(float(np.max(h0 - h1)), 0.)
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_surface_network_delivery(self.publish(directory, "valley"))
            np.testing.assert_array_equal(loaded["base"].reference_elevation_m, h0)
            self.assertFalse(np.array_equal(loaded["base"].reference_elevation_m, h1))

    def test_source_h0_unchanged_and_hard_immutable_loaded_payload(self):
        result = self.results["valley"]
        before = result["inputs"]["plan"]["arrays"]["source_height_m"].copy()
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_surface_network_delivery(self.publish(directory, "valley"))
            arrays = [loaded["base"].reference_elevation_m, loaded["derived"].displacement_m,
                      *loaded["geometry"].values(), *loaded["centerline"].values()]
            for array in arrays:
                with self.assertRaises(ValueError):
                    array.flags.writeable = True
            with self.assertRaises(TypeError):
                loaded["manifest"]["grid"]["origin_x_m"] = 1
        np.testing.assert_array_equal(before, result["inputs"]["plan"]["arrays"]["source_height_m"])

    def test_loader_sample_and_slices_never_generate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory, "valley")
            with forbid_generation():
                loaded = load_surface_network_delivery(path)
                sample = sample_surface_network(loaded, 30., 30.)
                window = slice_surface_network_world(loaded, (20., 20., 40., 40.))
                self.assertEqual(sample["arrays"]["final_surface_m"].shape, (1, 1))
                self.assertEqual(window["arrays"]["final_surface_m"].shape, (21, 21))

    def test_overlapping_windows_load_order_and_exact_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            first = load_surface_network_delivery(path)
            second = load_surface_network_delivery(path)
            for loaded in (second, first):
                right = slice_surface_network_delivery(loaded, slice(10, 51), slice(25, 61))
                left = slice_surface_network_delivery(loaded, slice(10, 51), slice(0, 41))
                for name in loaded["geometry"]:
                    np.testing.assert_array_equal(left["arrays"][name][:, 25:41], right["arrays"][name][:, :16])
                    self.assertFalse(left["arrays"][name].flags.writeable)

    def test_world_coordinates_datum_and_invalid_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_surface_network_delivery(self.publish(directory))
            sample = sample_surface_network(loaded, 30., 40.)
            self.assertEqual(sample["origin_x_m"], 30.)
            self.assertEqual(sample["origin_z_m"], 40.)
            self.assertEqual(sample["vertical_datum"], DATUM)
            self.assertEqual(sample["unit"], "m")
            for coords in ((.5, 0.), (-1., 0.), (61., 0.), (True, 0.), (np.nan, 0.)):
                with self.subTest(coords=coords), self.assertRaises(ValueError):
                    sample_surface_network(loaded, *coords)
            with self.assertRaises(ValueError):
                slice_surface_network_world(loaded, (40., 40., 20., 20.))
            with self.assertRaises(ValueError):
                slice_surface_network_delivery(loaded, slice(0, 10, 2), slice(0, 10))

    def test_q_stays_in_coarse_graph_not_wet_raster(self):
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_surface_network_delivery(self.publish(directory))
            graph = loaded["centerline"]
            self.assertEqual(graph["world_xz_m"].shape, (49, 2))
            self.assertEqual(graph["discharge_m3_s"].shape, (49,))
            self.assertNotIn("discharge_m3_s", loaded["geometry"])
            self.assertAlmostEqual(float(graph["local_discharge_m3_s"].sum()),
                float(graph["discharge_m3_s"][graph["outlet_mask"]].sum()))
            self.assertEqual(loaded["manifest"]["hydrology"]["Q_semantics"],
                             "coarse_node_reach_discharge_not_additive_across_nodes")

    def test_dry_stage_is_finite_zero_with_explicit_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_surface_network_delivery(self.publish(directory))
            geometry = loaded["geometry"]
            water, wet = geometry["water_surface_m"], geometry["wet_mask"]
            self.assertTrue(np.isfinite(water).all())
            self.assertTrue(np.all(water[~wet] == 0))
            self.assertTrue(np.all(water[wet] > geometry["final_surface_m"][wet]))
            sample = sample_surface_network(loaded, 0., 0.)
            self.assertFalse(sample["arrays"]["wet_mask"][0, 0])
            self.assertEqual(sample["arrays"]["water_depth_m"][0, 0], 0.)

    def test_invalid_datum_or_source_declaration_early_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad"
            for datum in (None, "", " ", "unknown", "x\ny", True):
                with self.subTest(datum=datum), self.assertRaises(ValueError):
                    export_surface_network(self.results["baseline"], datum, path, source_declaration=DECLARATION)
            with self.assertRaises(ValueError):
                export_surface_network(self.results["baseline"], DATUM, path)
            self.assertFalse(path.exists())

    def test_failure_and_forged_surface_refuse_export(self):
        case = recovery_case("valley")
        case["valley_recipe"] = replace(case["valley_recipe"], max_total_cut_volume_m3=0.)
        case["recovery_recipe"] = replace(case["recovery_recipe"], max_attempts=2)
        failed = recover_surface_network(**case)
        self.assertEqual(failed["surface"]["status"], "prepared")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad"
            with self.assertRaises(ValueError):
                export_surface_network(failed, DATUM, path, source_declaration=DECLARATION)
            forged = deepcopy(self.results["baseline"])
            forged["surface"]["arrays"]["final_surface_m"] = forged["surface"]["arrays"]["final_surface_m"].copy()
            forged["surface"]["arrays"]["final_surface_m"][30, 30] -= .1
            with self.assertRaises(ValueError):
                export_surface_network(forged, DATUM, path, source_declaration=DECLARATION)
            self.assertFalse(path.exists())

    def test_no_overwrite_and_atomic_rename_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            original_hash = _file_hash(path / "manifest.json")
            with self.assertRaises(FileExistsError):
                export_surface_network(self.results["valley"], DATUM, path, source_declaration=DECLARATION)
            self.assertEqual(_file_hash(path / "manifest.json"), original_hash)
            real_rename = os.rename
            def fail_outer(source, destination):
                if Path(destination).name == "failed":
                    raise OSError("publish unavailable")
                return real_rename(source, destination)
            with patch("terrain_pipeline.surface_network_consumer.os.rename", side_effect=fail_outer):
                with self.assertRaises(OSError):
                    export_surface_network(self.results["baseline"], DATUM, Path(directory) / "failed", source_declaration=DECLARATION)
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["delivery"])

    def test_windows_publish_race_cannot_replace_existing_directory(self):
        if os.name != "nt":
            self.skipTest("Windows directory rename race semantics")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "raced"
            real_rename = os.rename
            def race(source, target):
                if Path(target) == destination:
                    destination.mkdir()
                    (destination / "sentinel").write_text("other writer", encoding="utf-8")
                return real_rename(source, target)
            with patch("terrain_pipeline.surface_network_consumer.os.rename", side_effect=race):
                with self.assertRaises(FileExistsError):
                    export_surface_network(self.results["baseline"], DATUM, destination, source_declaration=DECLARATION)
            self.assertEqual((destination / "sentinel").read_text(encoding="utf-8"), "other writer")
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["raced"])

    def test_rehashed_sidecar_corruption_rejected_for_each_semantic_field(self):
        with tempfile.TemporaryDirectory() as directory:
            changes = {"water_surface_m": (0, 0), "source_surface_m": (30, 30),
                       "final_surface_m": (30, 30), "discharge_m3_s": (17,), "receiver": (9,)}
            for name, index in changes.items():
                path = self.publish(directory, name=name)
                def corrupt(manifest, arrays):
                    arrays[name] = arrays[name].copy()
                    arrays[name][index] += 1
                rewrite_delivery(path, corrupt)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    load_surface_network_delivery(path)

    def test_source_hash_and_proof_status_forgery_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("hash", "status"):
                path = self.publish(directory, name=kind)
                def corrupt(manifest, arrays):
                    if kind == "hash":
                        ref = manifest["proof"]["inputs"]["plan"]["arrays"]["source_height_m"]
                        arrays[ref["$array"]] = arrays[ref["$array"]].copy()
                        arrays[ref["$array"]][0, 0] += 1
                        ref["sha256"] = array_hash(arrays[ref["$array"]])
                    else:
                        manifest["proof"]["surface"]["summary"]["publishable"] = False
                rewrite_delivery(path, corrupt)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    load_surface_network_delivery(path)

    def test_actual_geometry_gate_rejects_negative_cut_protection_domain_drywater(self):
        result = self.results["baseline"]
        for kind in ("negative", "protected", "domain", "drywater", "disconnected"):
            arrays = {name: array.copy() for name, array in _payload(result).items()}
            wet_row, wet_column = np.argwhere(arrays["wet_mask"])[0]
            if kind == "negative":
                arrays["total_cut_m"][30, 30] = -1.
            if kind == "protected":
                arrays["protected_mask"][wet_row, wet_column] = True
            if kind == "domain":
                arrays["domain_mask"][wet_row, wet_column] = False
            if kind == "drywater":
                arrays["water_surface_m"][0, 0] = 1.
            if kind == "disconnected":
                arrays["wet_mask"][0, 0] = True
                arrays["water_surface_m"][0, 0] = arrays["final_surface_m"][0, 0] + .2
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _geometry_gate(arrays, result)

    def test_actual_geometry_gate_enforces_cumulative_ledger(self):
        result = deepcopy(self.results["valley"])
        result["inputs"]["valley_recipe"]["max_total_cut_volume_m3"] = 0.
        with self.assertRaisesRegex(ValueError, "cumulative"):
            _geometry_gate(_payload(result), result)

    def test_graph_q_nonconservative_and_bad_order_rejected(self):
        arrays = {name: array.copy() for name, array in self.results["baseline"]["final_plan"]["arrays"].items()}
        arrays["discharge_m3_s"][2, 3] = .1
        with self.assertRaisesRegex(ValueError, "nonconservative"):
            _local_q(arrays)
        arrays["order"] = arrays["order"][::-1].copy()
        with self.assertRaises(ValueError):
            _local_q(arrays)

    def test_strict_json_unexpected_files_and_broken_artifact_chain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            manifest_path = path / "manifest.json"
            encoded = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text('{"format_version":0,' + encoded[1:], encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_surface_network_delivery(path)
            manifest_path.write_text(encoded, encoding="utf-8")
            (path / "unexpected").write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_surface_network_delivery(path)

    def test_rehashed_actual_stage_jump_rejected_by_loader(self):
        forged = deepcopy(self.results["baseline"])
        water = forged["surface"]["arrays"]["water_surface_m"].copy()
        self.assertTrue(forged["surface"]["arrays"]["wet_mask"][9, 19])
        water[9, 19] += 2.
        forged["surface"]["arrays"]["water_surface_m"] = water
        rehash_surface_recovery(forged)
        with self.assertRaisesRegex(ValueError, "stage transition"):
            _proof_gate(forged, _payload(forged))
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            forge_delivery_proof(path, forged)
            with forbid_generation(), self.assertRaisesRegex(ValueError, "stage transition"):
                load_surface_network_delivery(path)

    def test_rehashed_noncoarse_fine_domain_change_rejected(self):
        forged = deepcopy(self.results["baseline"])
        domain = forged["surface"]["arrays"]["domain_mask"].copy()
        domain[9, 19] = False
        forged["surface"]["arrays"]["domain_mask"] = domain
        rehash_surface_recovery(forged)
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            forge_delivery_proof(path, forged)
            with self.assertRaisesRegex(ValueError, "domain"):
                load_surface_network_delivery(path)

    def test_rehashed_off_channel_fine_constraint_mismatch_rejected(self):
        forged = deepcopy(self.results["baseline"])
        protected = forged["surface"]["arrays"]["protected_mask"].copy()
        protected[1, 1] = True
        forged["surface"]["arrays"]["protected_mask"] = protected
        rehash_surface_recovery(forged)
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            forge_delivery_proof(path, forged)
            with self.assertRaisesRegex(ValueError, "fine masks"):
                load_surface_network_delivery(path)

    def test_broken_artifact_source_and_hydrology_semantics_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            def corrupt(manifest, arrays):
                manifest["hydrology"]["Q_semantics"] = "sum_wet_cells"
            rewrite_delivery(path, corrupt)
            with self.assertRaisesRegex(ValueError, "semantics"):
                load_surface_network_delivery(path)
            path = self.publish(directory, name="source_chain")
            manifest = json.loads((path / "derived" / "manifest.json").read_text(encoding="utf-8"))
            manifest["source_artifact_id"] = "0" * 64
            (path / "derived" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_surface_network_delivery(path)

    def test_legal_repeated_proof_array_references_can_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            def deduplicate(manifest, arrays):
                seen = {}
                removed = set()
                def visit(value):
                    if isinstance(value, dict) and "$array" in value:
                        key = (value["sha256"], value["dtype"], tuple(value["shape"]))
                        if key in seen:
                            removed.add(value["$array"])
                            value["$array"] = seen[key]
                        else:
                            seen[key] = value["$array"]
                    elif isinstance(value, dict):
                        for child in value.values():
                            visit(child)
                    elif isinstance(value, list):
                        for child in value:
                            visit(child)
                visit(manifest["proof"])
                for name in removed:
                    arrays.pop(name)
            rewrite_delivery(path, deduplicate)
            with forbid_generation():
                loaded = load_surface_network_delivery(path)
            self.assertEqual(loaded["geometry"]["final_surface_m"].shape, (61, 61))

    def test_combined_npz_uncompressed_and_metadata_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            with patch("terrain_pipeline.surface_network_consumer._bounded_npz", return_value=100 * 1024 * 1024):
                with self.assertRaisesRegex(ValueError, "total uncompressed"):
                    load_surface_network_delivery(path)
            with patch("terrain_pipeline.surface_network_consumer.MAX_BYTES", 100):
                with self.assertRaisesRegex(ValueError, "total resource"):
                    load_surface_network_delivery(path)

    def test_parent_symlink_or_junction_chain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            parent = Path(directory)
            original = Path.is_symlink
            def mark_parent(item):
                return item == parent or original(item)
            with patch.object(Path, "is_symlink", mark_parent):
                with self.assertRaisesRegex(ValueError, "symlinks or junctions"):
                    load_surface_network_delivery(path)


if __name__ == "__main__":
    unittest.main()
