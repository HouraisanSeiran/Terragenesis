"""Proof-bound actual river attachment, full-source coverage and static-only load."""

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import numpy as np

from terrain_pipeline import surface_coast_drop as coast
from terrain_pipeline.surface_domain_prepare import load_surface_domains
from terrain_pipeline.surface_network_consumer import _payload
from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest


ROOT = Path(__file__).resolve().parents[1]
SAVED_PREPARED = ROOT / "verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz"
SAVED_PREPARED_SHA256 = "dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af"


def fixed_drop_inputs(prepared=None):
    if prepared is None:
        prepared = load_surface_domains(SAVED_PREPARED)
    datum = prepared["candidate"]["inputs"]["vertical_datum"]
    section = np.column_stack((np.arange(38., 42.), np.full(4, 70.)))
    attachment = coast.RiverAttachment(prepared, 1, section, 2, datum)
    recovery = next(entry["recovery"] for entry in prepared["domains"] if entry["domain_id"] == 1)
    payload = _payload(recovery)
    bed_start = payload["final_surface_m"][60, 28:32]
    water_start = payload["water_surface_m"][60, 28:32]
    h0_start = payload["source_surface_m"][60, 28:32]
    stations = np.arange(70., 91.)
    fraction = np.linspace(0., 1., len(stations))[:, None]
    bed = (1 - fraction) * bed_start + fraction * -.5
    water = (1 - fraction) * water_start
    h0 = (1 - fraction) * h0_start + fraction * -.25
    shape = bed.shape
    corridor = coast.EngineeringSource(
        "corridor", "explicit-new-engineering-coastal-strip-not-original-dem", datum,
        38., 70., 1., 1., h0, bed, water, np.ones(shape, bool), np.zeros(shape, bool),
        np.zeros(shape, bool), np.ones(shape, bool), np.zeros(shape, bool), 0.,
    )
    sea_shape = (2, 4)
    sea = coast.EngineeringSource(
        "sea", "explicit-new-engineering-sea-patch-not-observed-coast", datum,
        38., 90., 1., 1., np.full(sea_shape, -.25), np.full(sea_shape, -.5), np.zeros(sea_shape),
        np.ones(sea_shape, bool), np.zeros(sea_shape, bool), np.zeros(sea_shape, bool),
        np.ones(sea_shape, bool), np.ones(sea_shape, bool), 0.,
    )
    return attachment, corridor, sea, stations, coast.DropBudget(4., 100.)


def reseal(result):
    plain = coast._plain(result)
    plain.pop("identity_sha256", None)
    plain["identity_sha256"] = coast.fingerprint(plain)
    return coast._freeze(plain)


def changed_source(source, **changes):
    return replace(source, **changes)


def rehash_artifact(artifact):
    identity = artifact["identity"]
    updated = ArtifactIdentity(**identity)
    artifact["identity"] = updated.record()
    artifact["identity_sha256"] = updated.sha256


def coherent_source_forgery(result, mode):
    forged = deepcopy(coast._plain(result))
    prepared = forged["inputs"]["attachment"]["prepared"]
    proof = prepared["domains"][0]["recovery"]
    surface = proof["surface"]
    if mode == "water":
        surface["arrays"]["water_surface_m"][60, 28] += .01
        surface["identity"]["parameters"]["output_sha256"] = digest({name: array_hash(array) for name, array in surface["arrays"].items()})
        surface["identity"]["parameters"]["summary_sha256"] = digest(surface["summary"])
        rehash_artifact(surface)
        ledger = proof["fine_ledger"]
        if ledger is not None:
            ledger["identity"]["parameters"]["surface_identity_sha256"] = surface["identity_sha256"]
            rehash_artifact(ledger)
        forged["proof_support"]["payload"]["water_surface_m"][60, 28] += .01
        fraction = np.linspace(1., 0., 21)
        forged["arrays"]["water_xyz_m"][::4, 1] += .01 * fraction
        forged["attachment"]["river_water_xyz_m"] = forged["arrays"]["water_xyz_m"][:4].copy()
        corridor = forged["inputs"]["corridor"]
        corridor["water_m"][:, 0] += .01 * fraction
        corridor["identity_sha256"] = coast.fingerprint({key: value for key, value in corridor.items() if key != "identity_sha256"})
    elif mode in ("Q", "H0"):
        plan = proof["inputs"]["plan"]
        name = "discharge_m3_s" if mode == "Q" else "source_height_m"
        plan["arrays"][name] += .001
        parameter = "source_discharge_sha256" if mode == "Q" else "source_height_sha256"
        plan["identity"]["parameters"][parameter] = array_hash(plan["arrays"][name])
        rehash_artifact(plan)
    elif mode == "grid":
        proof["inputs"]["fine"]["origin_x_m"] += 1.
        prepared["configurations"]["1"]["fine"]["origin_x_m"] += 1.
        plan = proof["inputs"]["plan"]
        plan["identity"]["parameters"]["origin_x_m"] += 1.
        rehash_artifact(plan)
    else:
        raise ValueError(mode)
    proof["identity_sha256"] = coast._recovery_hash({key: value for key, value in proof.items() if key != "identity_sha256"})
    prepared["identity_sha256"] = coast._domain_hash({key: value for key, value in prepared.items() if key != "identity_sha256"})
    forged["attachment"]["recovery_sha256"] = proof["identity_sha256"]
    return reseal(forged)


class SurfaceCoastDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if hashlib.sha256(SAVED_PREPARED.read_bytes()).hexdigest() != SAVED_PREPARED_SHA256:
            raise AssertionError("fixed saved prepared source file changed")
        cls.prepared = load_surface_domains(SAVED_PREPARED)
        cls.inputs = fixed_drop_inputs(cls.prepared)
        cls.result = coast.prepare_coast_drop(*cls.inputs)

    def test_actual_full_width_river_attachment_and_centerline(self):
        result = self.result
        bed = result["attachment"]["river_bed_xyz_m"]
        water = result["attachment"]["river_water_xyz_m"]
        np.testing.assert_allclose(bed[:, 1], [4.041177288138214, 3.626589853601033, 3.5, 3.661091270347399])
        np.testing.assert_allclose(water[:, 1], [4.275, 4.2375, 4.2, 4.2])
        np.testing.assert_allclose(bed[:, 0], [38., 39., 40., 41.])
        np.testing.assert_array_equal(bed[:, 2], 70.)
        centerline = result["arrays"]["centerline_xyz_m"]
        np.testing.assert_allclose(centerline[:, 0], 40.)
        np.testing.assert_allclose(centerline[:, 1], np.linspace(4.2, 0., 21))
        np.testing.assert_allclose(centerline[:, 2], np.arange(70., 91.))
        self.assertIs(result["natural_outlet_certified"], False)

    def test_actual_terminal_cut_q_not_sum_accumulated_nodes(self):
        self.assertAlmostEqual(self.result["attachment"]["terminal_q_m3_s"], .200049)
        discharge = self.result["proof_support"]["payload"]["discharge_m3_s"]
        self.assertGreater(float(discharge.sum()), .200049)

    def test_full_sea_attachment_positive_depth_and_source_identity(self):
        result = self.result
        np.testing.assert_allclose(result["attachment"]["sea_bed_xyz_m"][:, 1], -.5)
        np.testing.assert_allclose(result["attachment"]["sea_water_xyz_m"][:, 1], 0.)
        np.testing.assert_allclose(result["attachment"]["sea_water_xyz_m"][:, 2], 90.)
        self.assertEqual(result["inputs"]["sea"]["source_kind"], "engineering_synthetic")
        self.assertEqual(result["inputs"]["corridor"]["surface_model"], coast.SOURCE_MODEL)

    def test_all_source_nodes_cells_and_triangles_covered(self):
        arrays = self.result["arrays"]
        np.testing.assert_array_equal(arrays["corridor_support_cells"], np.arange(84))
        self.assertEqual(arrays["triangles"].shape, (120, 3))
        np.testing.assert_array_equal(arrays["corridor_source_triangles"], arrays["triangles"])
        self.assertEqual(len(np.unique(arrays["triangles"])), 84)
        for name, values in (("h0_m", arrays["h0_m"]), ("h2_m", arrays["bed_xyz_m"][:, 1]),
                             ("water_m", arrays["water_xyz_m"][:, 1])):
            source = self.result["inputs"]["corridor"][name]
            np.testing.assert_allclose(source.ravel()[arrays["corridor_source_triangles"]], values[arrays["triangles"]])

    def test_cut_integral_matches_actual_source_triangle_affine(self):
        source = self.result["inputs"]["corridor"]
        cut = source["h0_m"] - source["h2_m"]
        volume = 0.
        for row in range(20):
            for column in range(3):
                volume += .5 * (cut[row, column] + cut[row, column + 1] + cut[row + 1, column]) / 3
                volume += .5 * (cut[row, column + 1] + cut[row + 1, column + 1] + cut[row + 1, column]) / 3
        self.assertAlmostEqual(self.result["ledger"]["cut_volume_m3"], volume)
        self.assertAlmostEqual(float(self.result["ledger"]["triangle_plan_area_m2"].sum()), 60.)
        np.testing.assert_allclose(self.result["ledger"]["cut_m"], cut.ravel())

    def test_unknown_protected_dry_invalid_interior_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for name, value in (("unknown_mask", True), ("protected_mask", True), ("wet_mask", False), ("valid_mask", False)):
            mask = getattr(corridor, name).copy()
            mask[10, 1] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                coast.prepare_coast_drop(attachment, replace(corridor, **{name: mask}), sea, stations, budget)

    def test_hidden_interior_ridge_and_negative_depth_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for height in (3., 20.):
            bed = corridor.h2_m.copy()
            h0 = corridor.h0_m.copy()
            bed[10, 1] = height
            h0[10, 1] = max(height, h0[10, 1])
            with self.subTest(height=height), self.assertRaises(ValueError):
                coast.prepare_coast_drop(attachment, replace(corridor, h2_m=bed, h0_m=h0), sea, stations, budget)

    def test_no_skipping_station_or_cross_section_source_nodes(self):
        attachment, corridor, sea, stations, budget = self.inputs
        with self.assertRaisesRegex(ValueError, "exact.*spacing"):
            coast.prepare_coast_drop(attachment, corridor, sea, stations[::2], budget)
        section = attachment.cross_section_xz_m[[0, 2, 3]]
        with self.assertRaisesRegex(ValueError, "contiguous.*fine"):
            coast.prepare_coast_drop(replace(attachment, cross_section_xz_m=section, center_index=1), corridor, sea, stations, budget)

    def test_sea_unknown_protected_nonwet_nonocean_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for name, value in (("unknown_mask", True), ("protected_mask", True), ("wet_mask", False), ("ocean_mask", False)):
            mask = getattr(sea, name).copy()
            mask[0, 1] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                coast.prepare_coast_drop(attachment, corridor, replace(sea, **{name: mask}), stations, budget)

    def test_missing_sea_high_sea_and_datum_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for bad_sea in (None, replace(sea, datum="other-datum"),
                        replace(sea, sea_level_m=5., water_m=np.full_like(sea.water_m, 5.))):
            with self.subTest(sea=bad_sea), self.assertRaises(ValueError):
                coast.prepare_coast_drop(attachment, corridor, bad_sea, stations, budget)

    def test_budget_depth_and_volume_original_caps(self):
        attachment, corridor, sea, stations, _ = self.inputs
        for budget in (coast.DropBudget(0., 100.), coast.DropBudget(4., 0.)):
            with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, "budget exceeded"):
                coast.prepare_coast_drop(attachment, corridor, sea, stations, budget)

    def test_resources_preflight_rejection(self):
        for resources in (coast.DropResources(max_vertices=83), coast.DropResources(max_triangles=119),
                          coast.DropResources(max_source_cells=90), coast.DropResources(max_work=1007),
                          coast.DropResources(max_retained_bytes=1000)):
            with self.subTest(resources=resources), self.assertRaises(ValueError):
                coast.prepare_coast_drop(*self.inputs, resources=resources)

    def test_rehash_mesh_support_source_ledger_q_rejected(self):
        for name in ("bed_xyz_m", "water_xyz_m", "centerline_xyz_m", "h0_m", "corridor_weights", "river_indices", "corridor_source_triangles"):
            plain = coast._plain(self.result)
            changed = plain["arrays"][name].copy()
            changed.flat[len(changed.ravel()) // 2] += 1
            plain["arrays"][name] = changed
            with self.subTest(name=name), self.assertRaises(ValueError):
                coast.validate_coast_drop(reseal(plain))
        for mode in ("source", "q", "ledger"):
            plain = coast._plain(self.result)
            if mode == "source":
                source = plain["inputs"]["corridor"]
                array = source["h0_m"].copy()
                array[10, 1] += 1.
                source["h0_m"] = array
                source["identity_sha256"] = coast.fingerprint({key: value for key, value in source.items() if key != "identity_sha256"})
            elif mode == "q":
                plain["attachment"]["terminal_q_m3_s"] += 1.
            else:
                plain["ledger"]["cut_volume_m3"] += 1.
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                coast.validate_coast_drop(reseal(plain))

    def test_default_load_query_no_mapping_sampling_or_generation(self):
        import terrain_pipeline.surface_network_consumer as consumer
        import terrain_pipeline.surface_network_recovery as recovery

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coast.npz"
            coast.save_coast_drop(self.result, path)
            with ExitStack() as stack:
                for name in ("prepare_coast_drop", "_attachment", "_stencil", "_triangles", "_corridor_cells", "_source_triangles",
                             "_proof_gate", "validate_surface_domains", "_sample"):
                    stack.enter_context(patch.object(coast, name, side_effect=AssertionError("default load generated " + name)))
                stack.enter_context(patch.object(consumer, "_fine_source", side_effect=AssertionError("resampled old source")))
                stack.enter_context(patch.object(consumer, "_proof_gate", side_effect=AssertionError("old proof regenerated")))
                stack.enter_context(patch.object(recovery, "recover_surface_network", side_effect=AssertionError("recovered")))
                loaded = coast.load_coast_drop(path)
                queried = coast.query_coast_drop(loaded)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])
            np.testing.assert_array_equal(queried["arrays"]["bed_xyz_m"], self.result["arrays"]["bed_xyz_m"])

    def test_coherent_transverse_source_water_full_chain_rehash_rejected(self):
        forged = coherent_source_forgery(self.result, "water")
        self.assertEqual(forged["identity_sha256"], coast.fingerprint({key: value for key, value in forged.items() if key != "identity_sha256"}))
        self.assertAlmostEqual(forged["attachment"]["river_water_xyz_m"][0, 1], 4.285)
        self.assertAlmostEqual(forged["attachment"]["river_water_xyz_m"][2, 1], 4.2)
        proof = forged["inputs"]["attachment"]["prepared"]["domains"][0]["recovery"]
        self.assertEqual(proof["identity_sha256"], coast._recovery_hash(coast._plain({key: value for key, value in proof.items() if key != "identity_sha256"})))
        with self.assertRaisesRegex(ValueError, "wet water stage lacks original graph support"):
            coast.validate_coast_drop(forged)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coherent-forgery.npz"
            arrays = {}
            tree = coast._tree(forged, arrays)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("metadata.json", coast._json({"format": coast.VERSION + "-npy-v1", "tree": tree}).encode("ascii"))
                for name, array in arrays.items():
                    stream = io.BytesIO()
                    np.lib.format.write_array(stream, array, version=(1, 0), allow_pickle=False)
                    archive.writestr(name, stream.getvalue())
            with ExitStack() as stack:
                for name in ("prepare_coast_drop", "_stencil", "_triangles", "_corridor_cells", "_proof_gate", "validate_surface_domains"):
                    stack.enter_context(patch.object(coast, name, side_effect=AssertionError("generation forbidden")))
                with self.assertRaisesRegex(ValueError, "wet water stage lacks original graph support"):
                    coast.load_coast_drop(path)

    def test_coherent_original_source_q_h0_grid_rehash_rejected(self):
        for mode in ("Q", "H0", "grid"):
            forged = coherent_source_forgery(self.result, mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "candidate original"):
                coast.validate_coast_drop(forged)

    def test_immutable_input_result_and_no_source_mutation(self):
        before = coast.fingerprint(self.inputs[0].prepared)
        coast.prepare_coast_drop(*self.inputs)
        self.assertEqual(coast.fingerprint(self.inputs[0].prepared), before)
        arrays = {}
        coast._tree(self.result, arrays)
        for array in arrays.values():
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_atomic_nooverwrite_and_failed_publication_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coast.npz"
            coast.save_coast_drop(self.result, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                coast.save_coast_drop(self.result, path)
            self.assertEqual(path.read_bytes(), before)
            with patch.object(coast.os, "link", side_effect=OSError("publication failed")):
                with self.assertRaises(OSError):
                    coast.save_coast_drop(self.result, Path(directory) / "failed.npz")
            self.assertEqual([path.name for path in Path(directory).iterdir()], ["coast.npz"])

    def test_archive_headers_unique_members_json_and_payload_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "base.npz"
            coast.save_coast_drop(self.result, baseline)
            with zipfile.ZipFile(baseline) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            first_array = next(name for name in members if name.endswith(".npy"))
            for mode in ("duplicate", "json", "header", "trailing", "truncated", "extra"):
                path = Path(directory) / (mode + ".npz")
                payloads = dict(members)
                if mode == "json":
                    payloads["metadata.json"] = payloads["metadata.json"][:-1] + b',"format":"duplicate"}'
                elif mode == "header":
                    payloads[first_array] = b"\x93NUMPY\x01\x00" + (65535).to_bytes(2, "little")
                elif mode == "trailing":
                    payloads[first_array] += b"extra"
                elif mode == "truncated":
                    payloads[first_array] = payloads[first_array][:-1]
                elif mode == "extra":
                    payloads["extra.npy"] = b"extra"
                with zipfile.ZipFile(path, "w") as archive:
                    for name, payload in payloads.items():
                        archive.writestr(name, payload)
                    if mode == "duplicate":
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            archive.writestr(first_array, members[first_array])
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    coast.load_coast_drop(path)


if __name__ == "__main__":
    unittest.main()
