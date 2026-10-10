import unittest
import hashlib
import tempfile
from copy import deepcopy
from pathlib import Path
import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig, build_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork, ChannelForcing
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    couple_morphology, load_morphology_coupling, save_morphology_coupling,
    validate_morphology_coupling, _sample_nodes, _sections, MorphologyConfig, _pack, _unpack,
)
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters


class MorphologyCouplingTests(unittest.TestCase):
    def fixture(self):
        h = np.tile(np.arange(8., 0., -1.), (8, 1))
        terrain = TerrainGrid(h, np.ones_like(h, bool), 0., 0., 1., 1., "generated_terrain", "plane", "a" * 64)
        ids = np.array([18, 19, 20], np.int64); receiver = np.array([1, 2, -1], np.int64)
        owner = np.ones_like(h, np.int64); mask = np.ones_like(h, bool); lake = np.zeros_like(h, bool)
        geometry = build_channel_geometry(terrain, ids, receiver, np.full(3, 1.), np.full(3, .2),
            owner_grid=owner, corridor_mask=mask, lake_mask=lake, anchor_mask=np.zeros(3, bool),
            config=GeometryConfig(fine_spacing_m=.25, smoothing_iterations=0))
        points = geometry["arrays"]["node_xz_m"]
        bed = _sample_nodes(geometry, geometry["arrays"]["bed_elevation_m"])
        lengths = np.array([.5, 1., .5]); network = ChannelNetwork(receiver, lengths, np.ones(3),
            bed, np.array([1., 1., 1.]), np.full(3, .03), np.full(3, 1.),
            np.array(["interior", "interior", "open_outflow"]), geometry["identity_sha256"], "test", "test")
        forcing = ChannelForcing(np.array([0., 1.]), np.zeros((1, 3)), "b" * 64)
        return geometry, network, forcing

    def test_zero_change_prefix(self):
        geometry, network, forcing = self.fixture()
        result = couple_morphology(geometry, network, forcing, MaterialParameters(settling_velocity_m_s=0., sediment_critical_shear_pa=1e9, rock_critical_shear_pa=1e9),
            initial_water_volume_m3=np.full(3, .01), initial_mobile_solid_m3=np.zeros(3),
            initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=bed_floor(network))
        self.assertEqual(result["metadata"]["status"], "complete")
        np.testing.assert_allclose(result["arrays"]["mesh_bed_m"][0], result["arrays"]["mesh_bed_m"][-1])
        self.assertFalse(result["metadata"]["needs_geometry_and_hydraulic_revalidation"])

    def test_rejects_topology_mismatch(self):
        geometry, network, forcing = self.fixture()
        bad = ChannelNetwork(np.array([2, 2, -1], np.int64), network.length_m, network.width_m,
            network.bed_elevation_m, network.bed_slope, network.roughness, network.max_depth_m,
            network.terminal_kind, geometry["identity_sha256"], "test", "test")
        with self.assertRaises(ValueError):
            couple_morphology(geometry, bad, forcing, MaterialParameters(),
                initial_water_volume_m3=np.full(3, .01), initial_mobile_solid_m3=np.zeros(3),
                initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=bed_floor(network))

    def test_two_interval_deposition_updates_mesh_and_carries_water(self):
        geometry, network, _ = self.fixture()
        forcing = ChannelForcing(np.array([0., .5, 1.]), np.zeros((2, 3)), "b" * 64)
        result = couple_morphology(geometry, network, forcing,
            MaterialParameters(settling_velocity_m_s=.0001, sediment_critical_shear_pa=1e9,
                               rock_critical_shear_pa=1e9),
            initial_water_volume_m3=np.full(3, .1), initial_mobile_solid_m3=np.full(3, .001),
            initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=bed_floor(network))
        self.assertEqual(result["metadata"]["status"], "complete")
        a = result["arrays"]
        self.assertGreater(np.max(a["mesh_bed_m"][-1] - a["mesh_bed_m"][0]), 0.)
        self.assertTrue(np.all(a["water_volume_m3"][1] <= a["water_volume_m3"][0]))
        self.assertAlmostEqual(np.sum(a["mobile_solid_m3"][0]),
                               np.sum(a["mobile_solid_m3"][-1] + a["loose_solid_m3"][-1]), places=7)
        self.assertNotEqual(result["metadata"]["intervals"][0]["geometry_identity_sha256"],
                            result["metadata"]["intervals"][1]["geometry_identity_sha256"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recoupled.npz"
            save_morphology_coupling(path, result)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = load_morphology_coupling(path, expected_sha256=digest)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])

    def test_rock_erosion_and_rehashed_mesh_forgery(self):
        geometry, network, forcing = self.fixture()
        material = MaterialParameters(porosity=0., sediment_critical_shear_pa=0.,
            rock_critical_shear_pa=0., sediment_erodibility_m_s_pa=0.,
            rock_erodibility_m_s_pa=1e-8, transport_coefficient=.1,
            settling_velocity_m_s=0., provenance="rock fixture")
        result = couple_morphology(geometry, network, forcing, material,
            initial_water_volume_m3=np.full(3, .1), initial_mobile_solid_m3=np.zeros(3),
            initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=bed_floor(network))
        self.assertEqual(result["metadata"]["status"], "complete")
        a = result["arrays"]
        self.assertGreater(a["rock_removed_m3"][-1].sum(), 0.)
        self.assertLess(np.min(a["mesh_bed_m"][-1] - a["mesh_bed_m"][0]), 0.)
        forged = {"arrays": {key: value.copy() for key, value in a.items()},
                  "metadata": dict(result["metadata"])}
        forged["arrays"]["mesh_bed_m"][-1, 0] += .001
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "lineage|Exner|node bed|mesh"):
            validate_morphology_coupling(forged)

    def test_y_junction_uses_one_material_mesh_and_disjoint_lengths(self):
        from tools.verify_td_river_geometry import fixture
        terrain, ids, receiver, options = fixture("y", 1.)
        geometry = build_channel_geometry(terrain, ids, receiver, **options)
        a = geometry["arrays"]
        n = len(receiver)
        lengths = np.zeros(n)
        for i, j in enumerate(receiver):
            if j >= 0:
                half = np.linalg.norm(a["node_xz_m"][i] - a["node_xz_m"][j]) / 2.
                lengths[i] += half; lengths[j] += half
        bed = _sample_nodes(geometry, a["bed_elevation_m"])
        draft = ChannelNetwork(receiver, lengths, a["width_m"], bed,
            np.ones(n), np.full(n, .035), np.full(n, 2.),
            np.where(receiver < 0, "open_outflow", "interior"), geometry["identity_sha256"], "Y", "Y")
        _, slope, _ = _sections(geometry, a["bed_elevation_m"], draft, MorphologyConfig())
        network = ChannelNetwork(receiver, lengths, a["width_m"], bed, slope,
            draft.roughness, draft.max_depth_m, draft.terminal_kind,
            geometry["identity_sha256"], "Y", "Y")
        forcing = ChannelForcing(np.array([0., 1.]), np.zeros((1, n)), "b" * 64)
        result = couple_morphology(geometry, network, forcing,
            MaterialParameters(settling_velocity_m_s=.0001, sediment_critical_shear_pa=1e9,
                               rock_critical_shear_pa=1e9),
            initial_water_volume_m3=np.full(n, .1), initial_mobile_solid_m3=np.full(n, .001),
            initial_alluvium_bulk_m3=np.zeros(n), rock_floor_m=bed - 1.)
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertEqual(len(result["arrays"]["basis"]), n)
        self.assertEqual(len(result["metadata"]["intervals"]), 1)

    def test_large_embedded_payload_uses_safe_archive_axes(self):
        source = {"arrays": {"large": np.arange(9_000_001, dtype=np.uint8)},
                  "metadata": {"kind": "payload fixture"}, "identity_sha256": "a" * 64}
        arrays, metadata = {}, {}
        _pack(arrays, metadata, "large", source)
        self.assertEqual(arrays["large__payload"].ndim, 2)
        self.assertLessEqual(arrays["large__payload"].shape[0], 8_000_000)
        self.assertEqual(arrays["large__payload"].shape[1], 4096)
        recovered = _unpack(arrays, metadata, "large")
        np.testing.assert_array_equal(recovered["arrays"]["large"], source["arrays"]["large"])
        arrays["large__payload"] = arrays["large__payload"].copy()
        arrays["large__payload"].ravel()[-1] = 1
        with self.assertRaisesRegex(ValueError, "padding"):
            _unpack(arrays, metadata, "large")

    def test_excess_deformation_keeps_zero_step_witnessed_prefix(self):
        geometry, network, forcing = self.fixture()
        result = couple_morphology(geometry, network, forcing,
            MaterialParameters(settling_velocity_m_s=.001, sediment_critical_shear_pa=1e9,
                               rock_critical_shear_pa=1e9),
            initial_water_volume_m3=np.full(3, .1), initial_mobile_solid_m3=np.full(3, .001),
            initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=bed_floor(network),
            config=MorphologyConfig(max_cumulative_bed_change_m=1e-8))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertEqual(result["metadata"]["failure_phase"], "candidate_geometry")
        self.assertEqual(len(result["metadata"]["intervals"]), 0)
        validate_morphology_coupling(result)
        self.assertEqual(result["metadata"]["last_time_seconds"], 0.)

    def test_rehashed_unrelated_valid_failed_candidates_are_rejected(self):
        geometry, network, forcing = self.fixture()
        material = MaterialParameters(settling_velocity_m_s=.001,
            sediment_critical_shear_pa=1e9, rock_critical_shear_pa=1e9)
        options = dict(initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=bed_floor(network),
                       config=MorphologyConfig(max_cumulative_bed_change_m=1e-8))
        original = couple_morphology(geometry, network, forcing, material,
            initial_water_volume_m3=np.full(3, .1),
            initial_mobile_solid_m3=np.full(3, .001), **options)
        other_water = couple_morphology(geometry, network, forcing, material,
            initial_water_volume_m3=np.full(3, .2),
            initial_mobile_solid_m3=np.full(3, .001), **options)
        other_mobile = couple_morphology(geometry, network, forcing, material,
            initial_water_volume_m3=np.full(3, .1),
            initial_mobile_solid_m3=np.full(3, .002), **options)
        for candidate, roles in ((other_water, ("rejected_water", "rejected_sediment")),
                                 (other_mobile, ("rejected_sediment",))):
            forged = deepcopy(original)
            for role in roles:
                _pack(forged["arrays"], forged["metadata"], role,
                      _unpack(candidate["arrays"], candidate["metadata"], role))
            forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
            with self.subTest(roles=roles), self.assertRaisesRegex(ValueError, "detached"):
                validate_morphology_coupling(forged)


def bed_floor(network):
    return network.bed_elevation_m - .3


if __name__ == "__main__":
    unittest.main()
