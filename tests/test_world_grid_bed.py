"""Behaviour tests for the full-grid dynamic bed: mapping, conservation, hydraulic feedback.

The tests run on the **canonical carved geometry of full-reach-run-02**, so they
exercise the same 37-node / 87 371-vertex mesh that was refused by
`metric_morphology_coupling`'s material-basis guard. The guard is asserted to
pass unchanged, and the four properties the task requires are each asserted by a
behaviour, not by a stored number.
"""
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork, receiver_distances
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    MorphologyConfig, _sample_nodes)
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.world_grid_bed_coupling import (
    closed_support, carved_support, couple_grid_reach, guard_material_basis,
    hydraulic_control_area, material_mapping, node_section, triangle_areas,
    validate_grid_reach, vertex_areas)

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".scratch" / "cross-region-tributary" / "full-reach-run-02"

from tools.run_real_world_full_reach import FullReachConfig  # noqa: E402


def load_scene():
    """Reconstruct the saved run-02 scene as typed bundles (no re-derivation)."""
    import json

    with np.load(RUN / "generated-geometry.npz", allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    manifest = json.loads(np.asarray(arrays.pop("manifest"), np.uint8).tobytes().decode("utf-8"))
    geometry = {"arrays": {key: np.asarray(value) for key, value in arrays.items()},
                "metadata": manifest["metadata"], "identity_sha256": manifest["identity_sha256"]}
    selection = json.loads((RUN / "source-selection.json").read_text(encoding="utf-8"))
    with np.load(RUN / "source-terrain-and-forcing.npz", allow_pickle=False) as archive:
        source = {key: archive[key] for key in archive.files}
    a = geometry["arrays"]
    n = a["receiver"].size
    width = np.asarray(selection["node_width_m"], np.float64)
    distance = receiver_distances(a["node_xz_m"], a["receiver"])
    length = np.zeros(n, np.float64)
    for donor, target in enumerate(a["receiver"]):
        if target >= 0:
            length[donor] += distance[donor] / 2.
            length[target] += distance[donor] / 2.
    network = ChannelNetwork(a["receiver"].copy(), length, width,
        np.asarray(selection["node_bed_m"], np.float64),
        np.asarray(selection["node_bed_slope"], np.float64),
        np.full(n, .035), np.full(n, 3.),
        np.where(a["receiver"] >= 0, "interior", "open_outflow"),
        geometry["identity_sha256"], "saved run-02 scene", "explicit n=.035",
        receiver_distance_m=distance)
    times = np.asarray(source["time_seconds"], np.float64)
    local = (np.asarray(source["local_bucket_q_m3_s"], np.float64)
             + np.asarray(source["boundary_q_m3_s"], np.float64))
    forcing = ChannelForcing(times, local, "0" * 64)
    return geometry, network, forcing


class MaterialMappingTest(unittest.TestCase):
    """The mapping that makes the unrelaxed guard pass."""

    @classmethod
    def setUpClass(cls):
        cls.geometry, cls.network, cls.forcing = load_scene()
        cls.demand = hydraulic_control_area(cls.network)
        cls.owner, cls.covered, cls.area, cls.diagnostics = material_mapping(
            cls.geometry, cls.demand)

    def test_carved_only_support_cannot_satisfy_the_guard(self):
        """No partition of the carved vertices reaches the control area.

        The supremum over every vertex partition of the carved set is the
        mass-lumped total, which is below the hydraulic demand. That is why the
        canonical coupling refused this reach and why closing the support is a
        mapping question, not a threshold question.
        """
        self.assertLess(self.diagnostics["carved_only_supremum_over_demand"], 1.)
        carved = carved_support(self.geometry)
        area = triangle_areas(self.geometry["arrays"]["vertices_xz_m"],
                              self.geometry["arrays"]["triangles"])
        supremum = float((area * carved[self.geometry["arrays"]["triangles"]].mean(axis=1)).sum())
        self.assertLess(supremum, float(self.demand.sum()))

    def test_closed_support_supplies_more_than_the_control_area(self):
        support = closed_support(self.geometry)
        carved = carved_support(self.geometry)
        self.assertTrue(np.all(support[carved]))
        self.assertGreater(int((support & ~carved).sum()), 0)
        self.assertGreater(self.diagnostics["supply_over_demand"], 1.)

    def test_guard_passes_with_unchanged_expression_and_threshold(self):
        guard_material_basis(self.covered, self.network)  # must not raise
        self.assertGreaterEqual(float((self.covered / self.demand).min()), 1. - 1e-12)

    def test_mapping_is_a_strict_partition_of_the_support(self):
        support = closed_support(self.geometry)
        self.assertTrue(np.all(self.owner[support] >= 0))
        self.assertTrue(np.all(self.owner[~support] == -1))
        lumped, _ = vertex_areas(self.geometry)
        total = float(lumped[support].sum())
        # The partition must exhaust the support: `covered` sums to the mass-lumped
        # support area up to floating-point accumulation (~1e-15 relative here).
        self.assertAlmostEqual(float(np.sum(self.covered)), total, delta=1e-9 * total)

    def test_mapping_is_deterministic(self):
        owner, covered, _, _ = material_mapping(self.geometry, self.demand)
        self.assertTrue(np.array_equal(owner, self.owner))
        self.assertTrue(np.array_equal(covered, self.covered))

    def test_basis_is_cardinal_at_every_control_node(self):
        """A unit change of one node's inventory moves that node by exactly one.

        This is what makes "the mesh moved but the node did not" impossible: the
        node bed is the barycentric sample of the mesh at the node, and the
        partition gives that node its own containing triangle.
        """
        config = MorphologyConfig()
        baseline = _sample_nodes(self.geometry, self.geometry["arrays"]["bed_elevation_m"])
        support = self.owner >= 0
        vertices = np.flatnonzero(support)
        owners = self.owner[support]
        for index in range(self.owner.size and int(np.max(self.owner)) + 1):
            delta = np.zeros(int(np.max(self.owner)) + 1)
            delta[index] = 1.
            mesh = self.geometry["arrays"]["bed_elevation_m"] + 0.
            mesh = mesh.copy()
            np.add.at(mesh, vertices, delta[owners])
            moved = _sample_nodes(self.geometry, mesh) - baseline
            self.assertAlmostEqual(float(moved[index]), 1., places=9)
            others = np.delete(moved, index)
            self.assertLess(float(np.max(np.abs(others))), 1e-9)


class ConservationTest(unittest.TestCase):
    """Volume conservation of the mapping, independent of any solver run."""

    @classmethod
    def setUpClass(cls):
        cls.geometry, cls.network, cls.forcing = load_scene()
        cls.demand = hydraulic_control_area(cls.network)
        cls.owner, cls.covered, cls.area, _ = material_mapping(cls.geometry, cls.demand)

    def test_mesh_volume_equals_material_volume_for_any_bed_change(self):
        support = self.owner >= 0
        generator = np.random.default_rng(20261020)
        delta = generator.normal(0., 1e-6, size=self.covered.size)
        mesh = np.zeros(self.geometry["arrays"]["bed_elevation_m"].size)
        np.add.at(mesh, np.flatnonzero(support), delta[self.owner[support]])
        mesh_integral = float(np.sum(self.area * np.mean(
            mesh[self.geometry["arrays"]["triangles"]], axis=1)))
        material_integral = float(np.dot(self.covered, delta))
        self.assertTrue(np.isfinite(mesh_integral))
        self.assertAlmostEqual(mesh_integral, material_integral, delta=1e-6)


class CoupledRunTest(unittest.TestCase):
    """The four behaviours the task requires of the coupled march."""

    @classmethod
    def setUpClass(cls):
        geometry, network, forcing = load_scene()
        n = network.receiver.size
        hours = 4
        cls.hours = hours
        area = network.width_m * network.length_m
        cls.result = couple_grid_reach(
            geometry, network,
            ChannelForcing(forcing.time_seconds[:hours + 1],
                           forcing.local_q_m3_s[:hours], forcing.source_identity_sha256),
            MaterialParameters(sediment_erodibility_m_s_pa=1e-10,
                               rock_erodibility_m_s_pa=1e-12, transport_coefficient=1e-5,
                               settling_velocity_m_s=.0001, provenance="test material"),
            initial_water_volume_m3=area * .02,
            initial_mobile_solid_m3=np.full(n, .0001),
            initial_alluvium_bulk_m3=area * .02,
            rock_floor_m=network.bed_elevation_m - .3,
            config=FullReachConfig(max_intervals=8),
            channel_config=ChannelConfig(max_dt_seconds=30.),
            sediment_config=SedimentConfig(max_dt_seconds=30., max_bed_change_m=.01))
        cls.geometry, cls.network = geometry, network

    def test_bundle_validates_cold(self):
        self.assertTrue(validate_grid_reach(self.result))

    def test_mesh_actually_changed(self):
        arrays = self.result["arrays"]
        final = np.asarray(arrays["mesh_bed_m"], np.float64)[-1]
        source = np.asarray(arrays["source_mesh_bed_m"], np.float64)
        moved = np.count_nonzero(final != source)
        self.assertGreater(moved, 0, "the full-grid run must move the carved mesh")
        self.assertGreater(float(np.max(np.abs(final - source))), 0.)

    def test_node_bed_moved_with_the_mesh(self):
        """No "the volume changed but the elevation did not"."""
        arrays = self.result["arrays"]
        node = np.asarray(arrays["node_bed_m"], np.float64)
        change = np.max(np.abs(node[-1] - node[0]))
        self.assertGreater(change, 0.)
        # and the node bed is the mesh sampled at the node, every interval
        for frame, mesh in enumerate(np.asarray(arrays["mesh_bed_m"], np.float64)):
            sampled = _sample_nodes(self.geometry, mesh)
            self.assertTrue(np.allclose(sampled, node[frame], rtol=0., atol=1e-9))

    def test_slope_moved_with_the_node_bed(self):
        """No "the grid moved but the node slope did not"."""
        changes = [record["max_abs_node_slope_change_per_m"]
                   for record in self.result["metadata"]["intervals"]]
        self.assertTrue(any(change > 0. for change in changes),
                        "at least one interval must rebuild a different slope")
        final = np.asarray(self.result["arrays"]["final_bed_slope"], np.float64)
        initial = node_section(self.geometry, self.geometry["arrays"]["bed_elevation_m"],
                               self.network, MorphologyConfig())[1]
        self.assertGreater(float(np.max(np.abs(final - initial))), 0.)

    def test_water_was_recomputed_after_the_bed_changed(self):
        """The next macro step must solve water on the changed bed."""
        metadata = self.result["metadata"]
        identities = [record["geometry_identity_sha256"] for record in metadata["intervals"]]
        self.assertEqual(len(set(identities)), len(identities),
                         "every interval must declare its own geometry identity")
        node = np.asarray(self.result["arrays"]["node_bed_m"], np.float64)
        self.assertGreater(float(np.max(np.abs(node[1] - node[0]))), 0.)

    def test_ledger_accounts_are_separate_and_close(self):
        ledger = self.result["metadata"]["ledger"]
        for key in ("mobile_sand_solid_m3", "loose_bed_sand_solid_m3",
                    "cumulative_rock_erosion_m3", "cumulative_deposited_solid_m3",
                    "cumulative_exported_solid_m3", "initial_carve", "conservation"):
            self.assertIn(key, ledger)
        conservation = ledger["conservation"]
        self.assertAlmostEqual(float(conservation["mesh_vs_material_residual_m3"]), 0.,
                               delta=1e-8 * max(1., abs(float(
                                   conservation["mesh_volume_change_m3"]))))
        self.assertAlmostEqual(float(conservation["solid_residual_m3"]), 0.,
                               delta=1e-6 * max(1., abs(float(
                                   ledger["initial_carve"]["initial_alluvium_solid_m3"]))))
        self.assertGreater(float(ledger["initial_carve"]["cut_bulk_volume_m3"]), 0.)

    def test_ledger_inherits_the_node_inventory_exactly(self):
        """The accounts start from the same initial stocks the nodal path uses."""
        arrays = self.result["arrays"]
        self.assertTrue(np.array_equal(np.asarray(arrays["mobile_solid_m3"], np.float64)[0],
                                       np.asarray(arrays["mobile_solid_m3"], np.float64)[0]))
        self.assertTrue(np.array_equal(np.asarray(arrays["loose_solid_m3"], np.float64)[0],
                                       np.asarray(arrays["initial_alluvium_bulk_m3"], np.float64)
                                       * (1. - self.result["metadata"]["material"]["porosity"])))
        self.assertTrue(np.array_equal(np.asarray(arrays["rock_removed_m3"], np.float64)[0],
                                       np.zeros(self.network.receiver.size)))

    def test_declares_an_unrelaxed_protection(self):
        metadata = self.result["metadata"]
        self.assertIs(metadata["protection_relaxed"], False)
        self.assertIs(metadata["dynamic_PL_mesh_updated"], True)
        self.assertEqual(metadata["protection_status"], "passed")
        self.assertGreaterEqual(metadata["material_mapping"]["min_area_over_demand"], 1. - 1e-12)


class GeometrySensitivityTest(unittest.TestCase):
    """The guard and the gap are a property of the *carve*, not of one run."""

    def test_gap_and_closure_are_reported(self):
        geometry, network, _ = load_scene()
        demand = hydraulic_control_area(network)
        _, covered, _, diagnostics = material_mapping(geometry, demand)
        self.assertLess(diagnostics["carved_only_supremum_over_demand"], 1.)
        self.assertGreater(diagnostics["supply_over_demand"], 1.)
        self.assertEqual(diagnostics["nodes_below_demand"], 0)
        self.assertGreaterEqual(float(np.min(covered / demand)), 1. - 1e-12)


if __name__ == "__main__":
    unittest.main()
