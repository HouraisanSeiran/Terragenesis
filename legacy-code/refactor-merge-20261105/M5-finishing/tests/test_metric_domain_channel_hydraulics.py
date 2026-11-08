"""Focused finite-domain kinematic bridge contract tests."""
from copy import deepcopy
import hashlib
import math
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import ChannelConfig
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics, validate_domain_channel_hydraulics, save_domain_channel_hydraulics, load_domain_channel_hydraulics, _volume_sum


def fixture():
    height = np.array([[5., 3., 1.], [6., 4., 2.]])
    receiver = np.array([[1, 2, -1], [4, 1, 2]], np.int64)
    ocean = np.zeros(height.shape, bool)
    ocean[0, 2] = True
    accepted = ~ocean
    terminal = np.full(height.shape, 2, np.int64)
    topology = dict(height_m=height, receiver=receiver, terminal=terminal,
                    ocean=ocean, ocean_terminal=np.ones(height.shape, bool), accepted=accepted,
                    unresolved=np.zeros(height.shape, bool), in_core=np.ones(height.shape, bool),
                    shape=height.shape, spacing_m=10., origin_x_m=0., origin_z_m=0.)
    volume = np.zeros((2,) + height.shape)
    volume[0, accepted] = .2
    volume[1, accepted] = .6
    flow = dict(topology=topology, producing_flat=np.flatnonzero(accepted),
                released_per_interval_grid_m3=volume, released_grid_m3=volume.sum(axis=0),
                dt_s=2., interval_count=2)
    terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 10., 10.,
                          "diagnostic_dem_proxy", "synthetic raw-face fixture", "a" * 64)
    return terrain, flow


def arguments(ids=None, receiver=None):
    ids = np.arange(6, dtype=np.int64) if ids is None else np.array(ids, np.int64)
    receiver = np.array([1, 2, -1, 4, 1, 2] if receiver is None else receiver, np.int64)
    return dict(node_cell_ids=ids, receiver=receiver, width_m=np.full(ids.size, 2.),
                control_length_m=np.full(ids.size, 10.), max_depth_m=np.full(ids.size, 10.),
                roughness=np.full(ids.size, .05),
                parameter_sources={name: "explicit synthetic engineering scenario, uncalibrated"
                                   for name in ("width_m", "control_length_m", "max_depth_m", "roughness")},
                terminal_policy={"2": {"classification": "ocean", "kind": "open_outflow",
                                       "slope": .01, "source": "explicit engineering boundary gradient"}},
                geometry_source="raw conditioning grid node bed; not carved geometry",
                coverage_note=None, config=ChannelConfig(max_dt_seconds=.5))


def rehash(bundle):
    bundle["identity_sha256"] = identity(bundle["arrays"], bundle["metadata"])


class DomainChannelHydraulicsTests(unittest.TestCase):
    def test_receiver_slope_uses_irregular_metric_source_frame(self):
        terrain, flow = fixture()
        terrain = TerrainGrid(terrain.elevation_m, terrain.valid_mask, -135., 225., 10., 10.,
                              terrain.source_kind, terrain.source_id, terrain.source_sha256,
                              generation_seed=20261020)
        flow["topology"].update(origin_x_m=-135., origin_z_m=225.)
        product = build_domain_channel_hydraulics(terrain, flow, **arguments())
        mesh = grid_mesh(terrain.elevation_m.shape, x0_m=-135., z0_m=225.,
                         dx_m=10., world_seed=20261020)
        receiver = arguments()["receiver"]
        links = receiver >= 0
        distance = np.hypot(mesh.node_x_m[links] - mesh.node_x_m[receiver[links]],
                            mesh.node_z_m[links] - mesh.node_z_m[receiver[links]])
        self.assertGreater(float(np.max(np.abs(distance - 10.))), 1.)
        np.testing.assert_allclose(product["arrays"]["channel_network_receiver_distance_m"][links], distance,
                                   rtol=0., atol=1e-13)
        expected = ((terrain.elevation_m.ravel()[links]
                     - terrain.elevation_m.ravel()[receiver[links]]) / distance)
        np.testing.assert_allclose(product["arrays"]["channel_network_bed_slope"][links], expected,
                                   rtol=0., atol=1e-13)

    def test_local_interval_forcing_not_accumulated_or_time_averaged(self):
        terrain, flow = fixture()
        flow["accumulated_q"] = np.full(terrain.elevation_m.shape, 9999.)
        product = build_domain_channel_hydraulics(terrain, flow, **arguments())
        q = product["arrays"]["channel_forcing_local_q_m3_s"]
        np.testing.assert_array_equal(q[:, 0], [.1, .3])
        np.testing.assert_array_equal(q[:, 2], [0., 0.])
        self.assertAlmostEqual(product["metadata"]["channel_metadata"]["water_budget_m3"]["local_input"], 4.)
        self.assertTrue(product["metadata"]["coverage"]["current_production_downstream_closure_complete"])
        self.assertTrue(validate_domain_channel_hydraulics(product))
        self.assertEqual(product["metadata"]["source_face"], "raw_conditioning")
        self.assertFalse(product["metadata"]["r6_carving_consumed"])
        for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"):
            self.assertIs(product["metadata"][key], False)

    def test_missing_upstream_requires_explicit_coverage_and_remains_uncertified(self):
        terrain, flow = fixture()
        kwargs = arguments([1, 2], [1, -1])
        with self.assertRaisesRegex(ValueError, "coverage_note"):
            build_domain_channel_hydraulics(terrain, flow, **kwargs)
        kwargs["coverage_note"] = "Only downstream pair; upstream producing branches omitted, no inflow supplied"
        product = build_domain_channel_hydraulics(terrain, flow, **kwargs)
        coverage = product["metadata"]["coverage"]
        self.assertEqual(coverage["missing_producing_cell_count"], 4)
        self.assertEqual(coverage["missing_upstream_contributing_cell_count"], 4)
        self.assertAlmostEqual(coverage["missing_upstream_contributing_release_m3"], 3.2)
        self.assertAlmostEqual(coverage["missing_producing_release_m3"], 3.2)
        self.assertEqual(coverage["upstream_contributions_status"], "not_certified")
        self.assertFalse(coverage["current_production_downstream_closure_complete"])

    def test_omitted_receiver_is_never_an_outlet_even_with_note(self):
        terrain, flow = fixture()
        kwargs = arguments([0], [-1])
        kwargs["coverage_note"] = "explicit partial selection"
        with self.assertRaisesRegex(ValueError, "omitted or changed receiver"):
            build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_internal_edge_must_match_original(self):
        terrain, flow = fixture()
        kwargs = arguments()
        kwargs["receiver"][0] = 2
        with self.assertRaisesRegex(ValueError, "omitted or changed receiver"):
            build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_terminal_policy_is_explicit_and_classification_checked(self):
        terrain, flow = fixture()
        for mutation in ("missing", "wrong_kind", "zero_slope", "no_source"):
            kwargs = arguments()
            if mutation == "missing":
                kwargs["terminal_policy"] = {}
            elif mutation == "wrong_kind":
                kwargs["terminal_policy"]["2"].update(classification="closed_basin", kind="closed_wall", slope=0.)
            elif mutation == "zero_slope":
                kwargs["terminal_policy"]["2"]["slope"] = 0.
            else:
                kwargs["terminal_policy"]["2"]["source"] = ""
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_closed_basin_explicit_wall_not_lake_model(self):
        terrain, flow = fixture()
        flow["topology"]["ocean"][:] = False
        flow["topology"]["ocean_terminal"][:] = False
        kwargs = arguments()
        kwargs["terminal_policy"]["2"].update(classification="closed_basin", kind="closed_wall", slope=0.)
        product = build_domain_channel_hydraulics(terrain, flow, **kwargs)
        self.assertEqual(product["metadata"]["channel_metadata"]["water_budget_m3"]["boundary_outflow"], 0.)
        self.assertIn("no conservative floodplain inundation or lake evolution", product["metadata"]["limitations"])

    def test_provenance_and_physical_arrays_required(self):
        terrain, flow = fixture()
        for key, value in (("roughness", np.zeros(6)), ("width_m", np.full(6, np.nan)),
                           ("control_length_m", np.full(6, -1.)), ("max_depth_m", np.zeros(6)),
                           ("geometry_source", ""), ("parameter_sources", {}), ("config", None),
                           ("node_cell_ids", np.arange(6, dtype=np.float64))):
            kwargs = arguments()
            kwargs[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_time_volume_and_source_support_must_match(self):
        terrain, flow = fixture()
        for mutation in ("totals", "ocean_release", "producing", "negative", "terminal"):
            bad = deepcopy(flow)
            if mutation == "totals":
                bad["released_grid_m3"][0, 0] += 1.
            elif mutation == "ocean_release":
                bad["released_per_interval_grid_m3"][0, 0, 2] = 1.
                bad["released_grid_m3"][0, 2] = 1.
            elif mutation == "producing":
                bad["producing_flat"] = bad["producing_flat"][1:]
            elif mutation == "negative":
                bad["released_per_interval_grid_m3"][0, 0, 0] = -1.
            else:
                bad["topology"]["terminal"][0, 0] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_domain_channel_hydraulics(terrain, bad, **arguments())

    def test_identity_changes_with_parameter_provenance_and_hydrograph(self):
        terrain, flow = fixture()
        original = build_domain_channel_hydraulics(terrain, flow, **arguments())
        changed = deepcopy(flow)
        changed["released_per_interval_grid_m3"] = changed["released_per_interval_grid_m3"][::-1].copy()
        swapped = build_domain_channel_hydraulics(terrain, changed, **arguments())
        self.assertNotEqual(original["identity_sha256"], swapped["identity_sha256"])
        kwargs = arguments()
        kwargs["parameter_sources"]["width_m"] = "different explicit source"
        other = build_domain_channel_hydraulics(terrain, flow, **kwargs)
        self.assertNotEqual(original["identity_sha256"], other["identity_sha256"])

    def test_rehashed_parent_cannot_forge_summary_or_child_binding(self):
        terrain, flow = fixture()
        product = build_domain_channel_hydraulics(terrain, flow, **arguments())
        for mutation in ("coverage", "width", "dt", "receiver"):
            bad = deepcopy(product)
            if mutation == "coverage":
                bad["metadata"]["coverage"]["selected_input_volume_m3"] = 1234.
            elif mutation == "width":
                bad["arrays"]["width_m"] = np.full(6, 3.)
            elif mutation == "dt":
                bad["metadata"]["dt_s"] = 3.
            else:
                bad["arrays"]["original_receiver_cell_ids"] = np.full(6, -1, np.int64)
            rehash(bad)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_domain_channel_hydraulics(bad)

    def test_valid_child_from_other_scenario_cannot_be_transplanted(self):
        terrain, flow = fixture()
        original = build_domain_channel_hydraulics(terrain, flow, **arguments())
        for mutation in ("forcing", "geometry"):
            other_flow = deepcopy(flow)
            kwargs = arguments()
            if mutation == "forcing":
                other_flow["released_per_interval_grid_m3"] = other_flow["released_per_interval_grid_m3"][::-1].copy()
            else:
                kwargs["width_m"] = np.full(6, 3.)
            other = build_domain_channel_hydraulics(terrain, other_flow, **kwargs)
            forged = deepcopy(original)
            for key in ("channel_metadata", "channel_identity_sha256"):
                forged["metadata"][key] = other["metadata"][key]
            for key in other["arrays"]:
                if key.startswith("channel_"):
                    forged["arrays"][key] = other["arrays"][key]
            rehash(forged)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "nested channel"):
                validate_domain_channel_hydraulics(forged)

    def test_cannot_upgrade_readiness_by_rehashing(self):
        terrain, flow = fixture()
        original = build_domain_channel_hydraulics(terrain, flow, **arguments())
        for key in ("hydraulic_ready", "natural_outlet_verified", "publishable", "r6_carving_consumed"):
            forged = deepcopy(original)
            forged["metadata"][key] = True
            rehash(forged)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_domain_channel_hydraulics(forged)

    def test_missing_accessor_contract_is_rejected(self):
        terrain, flow = fixture()
        del flow["released_per_interval_grid_m3"]
        with self.assertRaisesRegex(ValueError, "domain_flow_topology"):
            build_domain_channel_hydraulics(terrain, flow, **arguments())

    def test_failed_prefix_is_preserved(self):
        terrain, flow = fixture()
        kwargs = arguments()
        kwargs["config"] = ChannelConfig(max_steps=1, max_dt_seconds=.5)
        product = build_domain_channel_hydraulics(terrain, flow, **kwargs)
        self.assertEqual(product["metadata"]["channel_metadata"]["status"], "failed_prefix")
        self.assertTrue(validate_domain_channel_hydraulics(product))

    def test_summary_sum_is_canonical_across_layouts(self):
        values = np.array([[1.e16, 1., 1.], [1., 1., 1.]])
        expected = math.fsum(float(value) for value in values.ravel(order="C"))
        self.assertEqual(expected, 10000000000000004.)
        for candidate in (values, np.asfortranarray(values), values[:, ::-1][:, ::-1]):
            self.assertEqual(_volume_sum(candidate), expected)
        self.assertEqual(_volume_sum(np.empty((2, 0))), 0.)

    def test_summary_one_ulp_tampering_is_not_tolerated(self):
        terrain, flow = fixture()
        original = build_domain_channel_hydraulics(terrain, flow, **arguments())
        bad = deepcopy(original)
        coverage = bad["metadata"]["coverage"]
        coverage["selected_input_volume_m3"] = float(np.nextafter(coverage["selected_input_volume_m3"], np.inf))
        rehash(bad)
        with self.assertRaisesRegex(ValueError, "coverage or geometry summary mismatch"):
            validate_domain_channel_hydraulics(bad)

    def test_cold_read_in_project_interpreter(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root / "runtime" / "venv" / "Scripts" / "python.exe"
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        terrain, flow = fixture()
        product = build_domain_channel_hydraulics(terrain, flow, **arguments())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cross-environment.npz"
            save_domain_channel_hydraulics(path, product)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            code = ('import sys; from terrain_pipeline.surface_hydraulics import load_domain_channel_hydraulics; load_domain_channel_hydraulics(sys.argv[1], expected_sha256=sys.argv[2], expected_identity=sys.argv[3])')
            result = subprocess.run([str(interpreter), "-c", code, str(path), sha, product["identity_sha256"]],
                                    cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_save_load_and_external_identity(self):
        terrain, flow = fixture()
        product = build_domain_channel_hydraulics(terrain, flow, **arguments())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidate.npz"
            save_domain_channel_hydraulics(path, product)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = load_domain_channel_hydraulics(path, expected_sha256=sha,
                                                      expected_identity=product["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], product["identity_sha256"])
            with self.assertRaises(ValueError):
                load_domain_channel_hydraulics(path, expected_sha256=sha, expected_identity="f" * 64)


if __name__ == "__main__":
    unittest.main()
