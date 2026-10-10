import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig, build_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_lake_channel_coupling import (
    LakeChannelConfig, LakeChannelForcing, LakeChannelPort, load_lake_channel,
    save_lake_channel, solve_lake_channel, validate_lake_channel, _mesh_sample,
)
from terrain_pipeline.surface_rivers.metric_natural_lakes import build_natural_lakes
from terrain_pipeline.surface_rivers import metric_lake_channel_coupling as coupling


def fixture(*, kind="tailwater", unknown=False):
    height = np.full((9, 11), 5., np.float64)
    height[4, 2:7] = [0., 1., 0., 1., 1.]
    height[4, 7:10] = [2., 2.2, 2.4]
    valid = np.ones_like(height, bool)
    if unknown:
        valid[3, 3] = False
    terrain = TerrainGrid(height, valid, 0., 0., 2., 2.,
                          "observed_dem", "analytical lake channel", "a" * 64)
    owner = np.full(height.shape, -1, np.int64)
    owner[4, 2:4] = 0
    owner[4, 4:7] = 1
    domain = build_natural_lakes(
        terrain, np.array([46, 48], np.int64), owner,
        max_stage_m=np.array([5., 5.]),
        boundary_faces=np.array([[50, 51]], np.int64),
        boundary_kinds=np.array([kind]), weir_coefficient_m3_s_m15=.2,
        source_provenance="analytical original bed",
        boundary_provenance="explicit original D4 face")
    geometry = build_channel_geometry(
        terrain, np.array([53, 51], np.int64), np.array([1, -1], np.int64),
        np.array([1., 1.]), np.array([.25, .25]),
        owner_grid=np.zeros(height.shape, np.int64),
        corridor_mask=np.ones(height.shape, bool), lake_mask=owner >= 0,
        anchor_mask=np.zeros(2, bool),
        config=GeometryConfig(fine_spacing_m=.25, max_offset_m=0.))
    points = geometry["arrays"]["node_xz_m"]
    bed = np.array([_mesh_sample(geometry, point) for point in points])
    reach_slope = (bed[0] - bed[1]) / np.linalg.norm(points[0] - points[1])
    network = ChannelNetwork(
        receiver=np.array([1, -1], np.int64),
        length_m=np.array([2., 2.]), width_m=np.ones(2),
        bed_elevation_m=bed, bed_slope=np.array([reach_slope, reach_slope]),
        roughness=np.array([.04, .04]), max_depth_m=np.array([3., 3.]),
        terminal_kind=np.array(["interior", "closed_wall"]),
        source_identity_sha256=geometry["identity_sha256"],
        section_source="analytical rectangular sections",
        roughness_source="analytical Manning roughness")
    ports = (LakeChannelPort(0, 1, .2, "analytical finite weir"),) if kind == "tailwater" else ()
    return domain, geometry, network, ports


def forcing(domain, network, *, duration=1., channel_q=0., lake_q=0., tailwater=0.):
    return LakeChannelForcing(
        np.array([0., duration], np.float64),
        np.array([[channel_q, 0.]], np.float64),
        np.array([[lake_q, 0.]], np.float64),
        np.array([[tailwater]], np.float64),
        domain["metadata"]["source_identity_sha256"], "analytical interval forcing")


class LakeChannelTests(unittest.TestCase):
    def test_unknown_terminal_inventory_and_trace_budget_are_witnessed(self):
        domain, geometry, network, ports = fixture()
        values = {name: getattr(network, name).copy() for name in
                  ("receiver", "length_m", "width_m", "bed_elevation_m", "bed_slope",
                   "roughness", "max_depth_m", "terminal_kind")}
        values["terminal_kind"][1] = "unknown_boundary"
        unknown = ChannelNetwork(**values, source_identity_sha256=geometry["identity_sha256"],
                                 section_source="analytical", roughness_source="analytical")
        with self.assertRaisesRegex(ValueError, "unknown terminal"):
            solve_lake_channel(domain, geometry, unknown, ports,
                               forcing(domain, unknown), np.array([0., .1]), np.zeros(2))
        drive = forcing(domain, network, duration=1., channel_q=1.)
        base = coupling._trace_bytes(domain, geometry, network, ports, drive, 0)
        one = coupling._trace_bytes(domain, geometry, network, ports, drive, 1)
        with patch.object(coupling, "MAX_BYTES", one + (one - base) // 2):
            result = solve_lake_channel(domain, geometry, network, ports, drive,
                                        np.zeros(2), np.zeros(2),
                                        LakeChannelConfig(max_dt_seconds=.1))
            self.assertEqual(result["metadata"]["status"], "failed_prefix")
            self.assertEqual(result["metadata"]["failure_reason"], "trace byte budget exhausted")
            self.assertEqual(len(result["arrays"]["step_dt_seconds"]), 1)
            validate_lake_channel(result)

    def test_rejects_unbound_channel_sections_and_shifted_port(self):
        domain, geometry, network, ports = fixture()
        drive = forcing(domain, network)
        base = {name: getattr(network, name).copy() for name in
                ("receiver", "length_m", "width_m", "bed_elevation_m", "bed_slope",
                 "roughness", "max_depth_m", "terminal_kind")}
        for field in ("length_m", "bed_elevation_m", "bed_slope"):
            modified = {key: value.copy() for key, value in base.items()}
            modified[field][0] += .01
            candidate = ChannelNetwork(**modified,
                source_identity_sha256=geometry["identity_sha256"],
                section_source="forged", roughness_source="analytical")
            with self.subTest(field=field), self.assertRaises(ValueError):
                solve_lake_channel(domain, geometry, candidate, ports, drive,
                                   np.zeros(2), np.zeros(2))
        wrong_source = ChannelNetwork(**base,
            source_identity_sha256=domain["metadata"]["source_identity_sha256"],
            section_source="forged", roughness_source="analytical")
        with self.assertRaisesRegex(ValueError, "source"):
            solve_lake_channel(domain, geometry, wrong_source, ports, drive,
                               np.zeros(2), np.zeros(2))
        shifted = deepcopy(geometry)
        shifted["arrays"]["node_xz_m"] = shifted["arrays"]["node_xz_m"].copy()
        shifted["arrays"]["node_xz_m"][1, 0] += .1
        shifted["identity_sha256"] = identity(shifted["arrays"], shifted["metadata"])
        with self.assertRaises(ValueError):
            solve_lake_channel(domain, shifted, network, ports, drive,
                               np.zeros(2), np.zeros(2))

    def test_two_basins_channel_port_and_independent_water_balance(self):
        domain, geometry, network, ports = fixture()
        drive = forcing(domain, network, duration=2., channel_q=1.)
        result = solve_lake_channel(domain, geometry, network, ports, drive,
                                    np.zeros(2), np.array([8., 0.]),
                                    LakeChannelConfig(max_dt_seconds=.05))
        self.assertEqual(result["metadata"]["status"], "complete")
        validate_lake_channel(result)
        a = result["arrays"]
        self.assertGreater(np.max(a["step_lake_internal_q_m3_s"]), 0.)
        self.assertGreater(np.max(a["step_port_q_m3_s"]), 0.)
        self.assertAlmostEqual(a["trace_channel_volume_m3"][-1].sum() +
                               a["trace_lake_volume_m3"][-1].sum(), 10., places=8)
        self.assertTrue(np.any(a["trace_wet_support"]))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "port.npz"
            save_lake_channel(path, result)
            loaded = load_lake_channel(path, expected_sha256=file_sha256(path))
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])

    def test_reverse_port_and_free_outlet_direction(self):
        domain, geometry, network, ports = fixture()
        result = solve_lake_channel(domain, geometry, network, ports,
                                    forcing(domain, network), np.zeros(2),
                                    np.array([0., 28.]),
                                    LakeChannelConfig(max_dt_seconds=.01))
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertLess(np.min(result["arrays"]["step_port_q_m3_s"]), 0.)
        domain, geometry, network, ports = fixture(kind="free_outflow")
        result = solve_lake_channel(domain, geometry, network, ports,
                                    forcing(domain, network, tailwater=100.),
                                    np.zeros(2), np.zeros(2))
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertTrue(np.all(result["arrays"]["step_boundary_q_m3_s"] >= 0.))

    def test_large_step_adapts_and_refinement_tracks_reference_ode(self):
        domain, geometry, network, ports = fixture()
        drive = forcing(domain, network, duration=.5)
        initial_channel = np.array([1., 0.])
        initial_lake = np.zeros(2)
        coarse = solve_lake_channel(domain, geometry, network, ports, drive,
                                    initial_channel, initial_lake,
                                    LakeChannelConfig(max_dt_seconds=.5, cfl=.1))
        fine = solve_lake_channel(domain, geometry, network, ports, drive,
                                  initial_channel, initial_lake,
                                  LakeChannelConfig(max_dt_seconds=.001, cfl=.1))
        self.assertEqual(coarse["metadata"]["status"], "complete")
        self.assertLess(coarse["arrays"]["step_dt_seconds"][0], .5)
        self.assertEqual(fine["metadata"]["status"], "complete")
        # Independent Manning and weir reference on this low-stage interval.
        def rhs(_, y):
            depth = max(y[0], 0.) / 2.
            area = depth
            radius = area / (1. + 2. * depth) if depth else 0.
            q = area * radius ** (2. / 3.) * np.sqrt(network.bed_slope[0]) / .04
            port = .2 * (max(y[1], 0.) / 2.) ** 1.5
            return [-q, q - port, port]
        reference = solve_ivp(rhs, (0., .5), [1., 0., 0.], rtol=1e-12, atol=1e-12).y[:, -1]
        coarse_error = np.max(np.abs(coarse["arrays"]["trace_channel_volume_m3"][-1] - reference[:2]))
        fine_error = np.max(np.abs(fine["arrays"]["trace_channel_volume_m3"][-1] - reference[:2]))
        self.assertLess(fine_error, coarse_error / 5.)

    def test_unknown_exterior_and_capacity_produce_failed_prefix(self):
        domain, geometry, network, ports = fixture(unknown=True)
        result = solve_lake_channel(domain, geometry, network, ports,
                                    forcing(domain, network, duration=10., lake_q=100.),
                                    np.zeros(2), np.zeros(2),
                                    LakeChannelConfig(max_dt_seconds=.1, min_dt_seconds=1e-6))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertLess(result["arrays"]["trace_time_seconds"][-1], 10.)
        validate_lake_channel(result)
        domain, geometry, network, ports = fixture()
        result = solve_lake_channel(domain, geometry, network, ports,
                                    forcing(domain, network, duration=10., lake_q=100.),
                                    np.zeros(2), np.zeros(2),
                                    LakeChannelConfig(max_dt_seconds=.1, min_dt_seconds=1e-6))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertIn("support", result["metadata"]["failure_reason"])

    def test_cold_validator_rejects_rehashed_state_port_and_failure_forgery(self):
        domain, geometry, network, ports = fixture()
        result = solve_lake_channel(domain, geometry, network, ports,
                                    forcing(domain, network),
                                    np.array([1., 0.]), np.zeros(2),
                                    LakeChannelConfig(max_dt_seconds=.1))
        for field in ("trace_channel_volume_m3", "trace_wet_support",
                      "step_port_q_m3_s", "step_channel_donor_q_m3_s"):
            forged = deepcopy(result)
            forged["arrays"][field] = forged["arrays"][field].copy()
            if forged["arrays"][field].dtype == bool:
                forged["arrays"][field][-1, 0] ^= True
            else:
                forged["arrays"][field][-1, 0] += .01
            forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_lake_channel(forged)


if __name__ == "__main__":
    unittest.main()
