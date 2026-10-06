import unittest
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from terrain_pipeline.surface_adaptive_geometry import build_adaptive_geometry, initial_leaf_state, validate_adaptive_geometry
from terrain_pipeline.surface_adaptive_hydraulics import adaptive_rhs, adaptive_drag, canonical_inventory
from terrain_pipeline.surface_adaptive_refinement import anticipated_spacing_map, refine_adaptive_state
from terrain_pipeline.surface_adaptive_execution import advance_adaptive_surface
from terrain_pipeline.surface_adaptive_records import CompressedGeometryHistory, CompressedRecordList, _encode, _decode
from terrain_pipeline.single_domain_shallow_water_accelerated_v7 import shallow_water_rhs as uniform_rhs, manning_damping as uniform_drag
from tests import test_single_domain_shallow_water_v3 as v7_fixtures


class AdaptiveSurfaceTests(unittest.TestCase):
    def test_archived_prefix_releases_only_owned_segments_and_keeps_random_access(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/".scratch") as directory:
            work,saved = Path(directory)/"work",Path(directory)/"saved"
            saved.mkdir()
            records = CompressedRecordList(work,memory_limit_bytes=1024,segment_limit_bytes=8192)
            sentinel = work/"sentinel"
            sentinel.write_bytes(b"preserved")
            values = np.random.default_rng(61).normal(size=2048)
            for index in range(12):
                records.append(dict(index=index,values=values+index))
            for index in (-13,12):
                with self.assertRaises(IndexError):
                    records[index]
            previous = records.temporary_storage_nbytes
            def loader(pin):
                payload = Path(pin["path"]).read_bytes()
                if hashlib.sha256(payload).hexdigest()!=pin["expected_sha256"]:
                    raise ValueError("saved record immutable hash mismatch")
                return _decode(payload)
            for index in range(12):
                item = records[index]
                payload = _encode(item)
                path = saved/f"record-{index}.npz"
                path.write_bytes(payload)
                records.bind_saved_record(index,dict(path=str(path),expected_sha256=hashlib.sha256(payload).hexdigest()),loader)
                self.assertLessEqual(records.temporary_storage_nbytes,previous)
                previous = records.temporary_storage_nbytes
                np.testing.assert_array_equal(records[0]["values"],values)
                np.testing.assert_array_equal(records[-1]["values"],values+11)
            self.assertEqual(records.temporary_storage_nbytes,0)
            for index in (-13,12):
                with self.assertRaises(IndexError):
                    records[index]
            with self.assertRaises(RuntimeError):
                records.append(dict(index=12,values=values+12))
            self.assertEqual([item["index"] for item in records[::-3]],[11,8,5,2])
            self.assertEqual(list(work.iterdir()),[sentinel])
            for index in reversed(range(12)):
                np.testing.assert_array_equal(records[index]["values"],values+index)
            records.close()
            self.assertEqual(sentinel.read_bytes(),b"preserved")
            (saved/"record-0.npz").write_bytes(b"altered")
            with self.assertRaises(ValueError):
                records[0]

    def test_history_spills_and_keeps_all_records_without_resident_growth(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/".scratch") as directory:
            records = CompressedRecordList(directory, memory_limit_bytes=1024)
            values = np.random.default_rng(13).normal(size=2048)
            for index in range(12):
                records.append(dict(index=index, values=values+index))
            self.assertEqual(len(records), 12)
            self.assertGreater(records.temporary_storage_nbytes, 1024)
            self.assertLess(records.storage_nbytes, records.serialized_nbytes/4)
            for index, record in enumerate(records):
                self.assertEqual(record["index"], index)
                np.testing.assert_array_equal(record["values"], values+index)
            self.assertGreater(sum(path.stat().st_size for path in Path(directory).iterdir()), 0)
            records.close()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def geometry(self, bed):
        request = np.full(bed.shape, 4, np.int64)
        request[:, :4] = 1
        request[:, 4:8] = 2
        return build_adaptive_geometry(bed, request)

    def run_surface(self, geometry, depth, duration=.1, dynamic=False, forcing=None, tail=None):
        rows, columns = depth.shape
        return advance_adaptive_surface(geometry, initial_depth_m=depth, forcing_interval_s=duration, intervals=1,
            forcing_provider=lambda i: np.zeros_like(depth) if forcing is None else forcing,
            boundary_stage_provider=lambda i: np.zeros(2*(rows+columns)) if tail is None else tail,
            budget=SurfaceBudget(max_dt_s=.025, max_snapshots=3, max_duration_s=duration, max_wall_s=120.),
            dynamic_refinement=dynamic, halo_m=2)

    def test_partition_coverage_and_face_segments_are_unique_and_once(self):
        geometry = self.geometry(np.zeros((8, 16)))
        self.assertTrue(validate_adaptive_geometry(geometry))
        self.assertEqual(geometry["metadata"]["leaf_counts"], {"1": 32, "2": 8, "4": 4})
        self.assertEqual(geometry["arrays"]["leaf_area_m2"].sum(), 128)
        a = geometry["arrays"]
        self.assertEqual(len(np.unique(np.column_stack((a["face_axis"], a["face_canonical_row"], a["face_canonical_column"])), axis=0)), len(a["face_left"]))

    def test_mixed_full_half_wet_lakes_are_stationary(self):
        bed = np.random.default_rng(120).uniform(0., 1., (8, 16))
        geometry = self.geometry(bed)
        for stage in (.4, 2.):
            depth = np.maximum(stage-bed, 0.)
            state = initial_leaf_state(geometry, depth)
            rhs, witness = adaptive_rhs(geometry, state, tailwater_m=np.zeros(48), dt=.01)
            np.testing.assert_allclose(rhs, 0., rtol=0., atol=2e-13)
            result = self.run_surface(geometry, depth, duration=.05)
            np.testing.assert_allclose(result["snapshots"][-1]["canonical_depth_m"], depth, rtol=0., atol=1e-12)
            self.assertLess(abs(result["ledger"][-1, -1]), 1e-10)

    def test_uniform_1m_rhs_and_drag_match_frozen_v7(self):
        rng = np.random.default_rng(121)
        bed = rng.uniform(0., .3, (8, 16))
        geometry = build_adaptive_geometry(bed, np.ones(bed.shape, np.int64))
        uniform, support, datum = v7_fixtures.ShallowWaterV3Tests().geometry(bed, 1)
        depth = rng.uniform(.01, .6, bed.shape)
        momentum = depth[:, :, None]*rng.uniform(-1., 1., (*bed.shape, 2))
        state = initial_leaf_state(geometry, depth, momentum)
        geometry["arrays"]["boundary_kind"][:] = np.arange(48)%3
        tail = np.full(48, .7)
        actual, witness = adaptive_rhs(geometry, state, tailwater_m=tail, dt=.01)
        uniform_state = np.column_stack((depth.ravel(), momentum.reshape(-1, 2)))
        expected, uniform_witness = uniform_rhs(uniform_state, bed-datum, support=support, spacing=1., gravity=9.81,
            boundary_kind=geometry["arrays"]["boundary_kind"], tailwater=tail-datum, roughness=.035, dt=.01)
        owner = geometry["arrays"]["canonical_owner"].ravel()
        np.testing.assert_allclose(actual[owner], expected, rtol=0., atol=1e-12)
        np.testing.assert_allclose(witness["internal_flux_m2_s"], uniform_witness["internal_flux"], rtol=0., atol=1e-12)
        damping, factor = adaptive_drag(geometry, state, dt=.01, gravity=9.81, roughness=.035)
        expected_damping, expected_factor = uniform_drag(uniform_state, .01, 9.81, .035, support=support)
        np.testing.assert_allclose(damping[owner], expected_damping, rtol=0., atol=1e-14)
        np.testing.assert_allclose(factor[owner], expected_factor, rtol=0., atol=1e-14)

    def test_refinement_transfer_preserves_each_parent_water_and_momentum(self):
        bed = np.random.default_rng(122).uniform(0., .3, (8, 16))
        geometry = build_adaptive_geometry(bed, np.full(bed.shape, 4, np.int64))
        depth = np.maximum(.25-bed, 0.)
        momentum = depth[:, :, None]*np.array([.3, -.2])
        state = initial_leaf_state(geometry, depth, momentum)
        requested = np.full(bed.shape, 4, np.int64)
        requested[:, :8] = 1
        refined, after, witness = refine_adaptive_state(geometry, state, requested)
        self.assertGreater(witness["added_leaf_count"], 0)
        np.testing.assert_allclose(witness["parent_grouped_residual"], 0., rtol=0., atol=1e-13)
        before_depth, before_momentum = canonical_inventory(geometry, state)
        after_depth, after_momentum = canonical_inventory(refined, after)
        np.testing.assert_allclose(after_depth, before_depth, rtol=0., atol=1e-14)
        np.testing.assert_allclose(after_momentum, before_momentum, rtol=0., atol=1e-14)

    def test_dry_front_is_pre_tagged_and_dynamic_run_matches_uniform_1m(self):
        bed = np.zeros((8, 32))
        depth = np.zeros_like(bed)
        depth[:, :8] = 1.
        requested = anticipated_spacing_map(depth, halo_m=4)
        self.assertTrue(np.all(requested[:, 8:12] == 1))
        self.assertTrue(np.all(requested[:, 16:] == 4))
        adaptive = build_adaptive_geometry(bed, requested)
        uniform = build_adaptive_geometry(bed, np.ones(bed.shape, np.int64))
        actual = self.run_surface(adaptive, depth, duration=.2, dynamic=True)
        reference = self.run_surface(uniform, depth, duration=.2)
        np.testing.assert_allclose(actual["snapshots"][-1]["canonical_depth_m"], reference["snapshots"][-1]["canonical_depth_m"], rtol=0., atol=1e-10)
        self.assertLess(abs(actual["ledger"][-1, -1]), 1e-10)
        self.assertLess(actual["metadata"]["maximum_active_leaf_count"], bed.size)
        for epoch in actual["epoch_packets"]:
            a = actual["geometries"][epoch["geometry_identity"]]["arrays"]
            net = np.zeros_like(epoch["state_before"])
            np.add.at(net, a["face_left"], -epoch["internal_transfer"])
            np.add.at(net, a["face_right"], epoch["internal_transfer"])
            np.add.at(net, a["boundary_cell"], -epoch["boundary_transfer"])
            net[:, 0] += epoch["forcing_volume_m3"]
            net[:, 1:] += epoch["bed_impulse"]+epoch["manning_impulse"]
            np.testing.assert_allclose((epoch["state_after"]-epoch["state_before"])*a["leaf_area_m2"][:, None], net, rtol=0., atol=1e-12)

    def test_tiny_uniform_forcing_is_retained_without_forcing_all_refinement(self):
        bed = np.zeros((8, 16))
        geometry = build_adaptive_geometry(bed, np.full(bed.shape, 4, np.int64))
        source = np.full_like(bed, 1e-12)
        result = self.run_surface(geometry, np.zeros_like(bed), duration=.05, dynamic=True, forcing=source)
        self.assertEqual(result["snapshots"][-1]["leaf_counts"], {"1": 0, "2": 0, "4": 8})
        np.testing.assert_allclose(result["snapshots"][-1]["canonical_depth_m"], source*.05, rtol=0., atol=1e-26)
        self.assertEqual(result["metadata"]["supplied_m3"], float(source.sum()*.05))

    def test_compressed_geometry_history_is_immutable_and_decodes_without_building(self):
        geometry = self.geometry(np.zeros((8, 16)))
        history = CompressedGeometryHistory()
        history.register(geometry)
        identity = geometry["identity_sha256"]
        geometry["arrays"]["canonical_bed_m"][0, 0] = 99.
        with patch("terrain_pipeline.surface_adaptive_geometry.build_adaptive_geometry", side_effect=AssertionError("generation forbidden")):
            decoded = history[identity]
        self.assertEqual(decoded["arrays"]["canonical_bed_m"][0, 0], 0.)
        self.assertEqual(decoded["identity_sha256"], identity)

    def test_forcing_pre_tag_refines_all_and_reports_zero_savings(self):
        bed = np.zeros((8, 16))
        geometry = build_adaptive_geometry(bed, np.full(bed.shape, 4, np.int64))
        result = self.run_surface(geometry, np.zeros_like(bed), duration=.05, dynamic=True, forcing=np.full_like(bed, .001))
        self.assertEqual(result["snapshots"][-1]["leaf_counts"], {"1": bed.size, "2": 0, "4": 0})
        self.assertEqual(result["metadata"]["maximum_active_leaf_count"], bed.size)
        self.assertFalse(result["metadata"]["uniform_coarse_convergence_claim"])
        self.assertLess(abs(result["ledger"][-1, -1]), 1e-12)

    def test_interval_rk_packet_mass_and_momentum_close(self):
        bed = np.zeros((8, 16))
        geometry = self.geometry(bed)
        depth = np.ones_like(bed)
        depth[:, :4] = 2.
        result = self.run_surface(geometry, depth, duration=.05)
        packet = result["first_rk_packets"][0]
        area, dt = packet["leaf_area_m2"], packet["dt_s"]
        net = np.zeros_like(packet["state_before"])
        internal = .5*dt*(packet["rk1_internal_flux"]+packet["rk2_internal_flux"])
        boundary = .5*dt*(packet["rk1_boundary_flux"]+packet["rk2_boundary_flux"])
        np.add.at(net, packet["face_left"], -internal)
        np.add.at(net, packet["face_right"], internal)
        np.add.at(net, packet["boundary_cell"], -boundary)
        net /= area[:, None]
        net += .5*dt*(packet["rk1_bed_source"]+packet["rk2_bed_source"])
        net[:, 1:] += packet["manning_momentum_change"]
        np.testing.assert_allclose(packet["state_after"]-packet["state_before"], net, rtol=0., atol=2e-14)

    def test_small_pulse_crosses_coarse_fine_interface_without_large_reflection(self):
        bed = np.zeros((4, 64))
        x = np.arange(64)+.5
        depth = np.tile(1.+.001*np.exp(-((x-20)/4)**2), (4, 1))
        requested = np.full(bed.shape, 2, np.int64)
        requested[:, :32] = 1
        adaptive = build_adaptive_geometry(bed, requested)
        uniform = build_adaptive_geometry(bed, np.ones(bed.shape, np.int64))
        actual = self.run_surface(adaptive, depth, duration=5., dynamic=False)
        reference = self.run_surface(uniform, depth, duration=5.)
        difference = actual["snapshots"][-1]["canonical_depth_m"]-reference["snapshots"][-1]["canonical_depth_m"]
        self.assertLess(float(abs(difference[:, :28]).max()), .0002)
        self.assertLess(float(abs(difference).max()), .0003)
        self.assertLess(abs(actual["ledger"][-1, -1]), 1e-10)


if __name__ == "__main__":
    unittest.main()
