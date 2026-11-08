import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_delta_sediment_product import (
    build_delta_sediment_candidate, load_delta_sediment_candidate,
    save_delta_sediment_candidate, validate_delta_sediment_candidate,
)
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _pack, _unpack
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters, SedimentDomain, SedimentForcing, solve_sediment,
)
from tests import test_metric_morphology_coupling as morphology_tests


class DeltaSedimentProductTests(unittest.TestCase):
    def fixture(self):
        geometry, network, forcing = morphology_tests.MorphologyCouplingTests().fixture()
        ga = geometry["arrays"]
        terrain = TerrainGrid(ga["source_height_m"], ga["source_valid_mask"], **geometry["metadata"]["terrain_metadata"])
        water = solve_channel(network, forcing, np.full(3, .1))
        product = make_channel_product(network, forcing, water)
        wa = water["arrays"]
        domain = SedimentDomain(network.receiver, np.ones(3), network.width_m, network.bed_elevation_m,
                                network.bed_elevation_m - 1., np.zeros(3), np.zeros(3, bool),
                                network.terminal_kind == "open_outflow", geometry["identity_sha256"], "fixture")
        sf = SedimentForcing(wa["time_seconds"], wa["volume_m3"][:-1], wa["depth_m"][:-1],
                            wa["outflow_q_m3_s"], np.broadcast_to(network.bed_slope, wa["outflow_q_m3_s"].shape).copy(),
                            np.zeros_like(wa["outflow_q_m3_s"]), product["identity_sha256"], geometry["identity_sha256"], "fixture")
        sediment = solve_sediment(domain, sf, MaterialParameters(settling_velocity_m_s=0.,
                                  rock_critical_shear_pa=1e9, sediment_critical_shear_pa=0.),
                                  initial_mobile_solid_m3=np.array([0., 0., .01]))
        land = np.zeros(terrain.elevation_m.shape, bool)
        land[:, :4] = True
        return terrain, land, ~land, ((2, 3), (2, 4)), geometry, product, sediment, 2

    def test_export_supply_cold_read_and_rehashed_parent_tampering(self):
        bundle = build_delta_sediment_candidate(*self.fixture())
        candidate = _unpack(bundle["arrays"], bundle["metadata"], "candidate")
        self.assertEqual(candidate["metadata"]["schema"], "terragenesis-delta-candidate-product-v3")
        self.assertEqual(candidate["metadata"]["source_geometry"]["identity_sha256"],
                         self.fixture()[4]["identity_sha256"])
        self.assertGreater(bundle["metadata"]["sediment_supply_solid_m3"], 0.)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delta.npz"
            save_delta_sediment_candidate(path, bundle)
            cold = load_delta_sediment_candidate(path, expected_sha256=file_sha256(path))
            self.assertEqual(cold["identity_sha256"], bundle["identity_sha256"])
        changed = copy.deepcopy(bundle)
        changed["metadata"]["sediment_supply_solid_m3"] += 1.
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_delta_sediment_candidate(changed)

    def test_upstream_path_must_follow_actual_geometry_receiver(self):
        args = list(self.fixture())
        args[3] = ((2, 2), (2, 4))
        with self.assertRaisesRegex(ValueError, "directed source geometry path"):
            build_delta_sediment_candidate(*args)

    def test_unknown_terminal_and_different_source_rejected(self):
        args = list(self.fixture())
        args[7] = 0
        with self.assertRaisesRegex(ValueError, "open export terminal"):
            build_delta_sediment_candidate(*args)
        args = list(self.fixture())
        t = args[0]
        args[0] = TerrainGrid(t.elevation_m, t.valid_mask, **{**args[4]["metadata"]["terrain_metadata"], "source_sha256": "d" * 64})
        with self.assertRaisesRegex(ValueError, "terrain differs"):
            build_delta_sediment_candidate(*args)
        args = list(self.fixture())
        args[3] = ((3, 3), (3, 4))
        with self.assertRaisesRegex(ValueError, "detached"):
            build_delta_sediment_candidate(*args)

    def test_failed_water_and_rehashed_embedded_graph_rejected(self):
        args = list(self.fixture())
        _, network, forcing = morphology_tests.MorphologyCouplingTests().fixture()
        prefix = solve_channel(network, forcing, np.full(3, .1), ChannelConfig(max_dt_seconds=.1, max_steps=1))
        args[5] = make_channel_product(network, forcing, prefix)
        with self.assertRaisesRegex(ValueError, "complete upstream"):
            build_delta_sediment_candidate(*args)
        bundle = build_delta_sediment_candidate(*self.fixture())
        changed = copy.deepcopy(bundle)
        candidate = _unpack(changed["arrays"], changed["metadata"], "candidate")
        candidate["metadata"]["parent_graph_identity_sha256"] = "f" * 64
        candidate["identity_sha256"] = identity(candidate["arrays"], candidate["metadata"])
        _pack(changed["arrays"], changed["metadata"], "candidate", candidate)
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_delta_sediment_candidate(changed)


if __name__ == "__main__":
    unittest.main()
