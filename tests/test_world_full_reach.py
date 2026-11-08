"""Behaviour tests for the full real-world reach, the width law and the lake ledger."""
import unittest

import numpy as np

from terrain_pipeline.lake import LakeOutlet as LakeOutlet
from terrain_pipeline.lake import LakeStorage as LakeStorage
from terrain_pipeline.surface_rivers.metric_morphology_coupling import MorphologyConfig
from terrain_pipeline.surface_rivers.world_channel_dynamics import couple_nodal_reach
from terrain_pipeline.surface_rivers.world_channel_graph import WorldNode, assemble_world_graph
from terrain_pipeline.lake import build_sill_lake as build_sill_lake
from terrain_pipeline.lake import channel_width_m as channel_width_m
from terrain_pipeline.lake import design_discharge_m3_s as design_discharge_m3_s
from terrain_pipeline.lake import integrate_sill_lake as integrate_sill_lake
from terrain_pipeline.lake import sill_coefficient_m3_s_m15 as sill_coefficient_m3_s_m15
from tools.run_real_world_full_reach import (
    FullReachConfig, SEED, boundary_scenarios, select_reach)


class _NetworkStub:
    source_identity_sha256 = "b" * 64

    def __init__(self, count):
        self.receiver = np.zeros(count, np.int64)


class _ForcingStub:
    time_seconds = np.array([0., 1.])


class ReachSelectionTest(unittest.TestCase):
    """One real basin, four owning cores, receiver untouched, truncation declared."""

    @classmethod
    def setUpClass(cls):
        cls.selection = select_reach()

    def test_selected_reach_spans_several_owning_cores(self):
        selection = self.selection
        graph = selection["graph"]
        cores = sorted(set(graph["region_ids"]))
        self.assertGreaterEqual(len(cores), 3, "reach must cross more than two owning cores")
        self.assertGreaterEqual(len(graph["cross_region_donors"]), 2)
        for donor in graph["cross_region_donors"]:
            target = int(graph["receiver"][donor])
            self.assertNotEqual(graph["region_ids"][donor], graph["region_ids"][target])
        for target in graph["receiver"]:
            self.assertNotEqual(graph["region_ids"][target], None)

    def test_world_graph_merges_duplicate_halo_records(self):
        selection = self.selection
        graph = selection["graph"]
        points = graph["node_xz_m"]
        receiver = graph["receiver"]
        records = [WorldNode(SEED, float(point[0]), float(point[1]),
                             None if receiver[index] < 0 else graph["node_ids"][int(receiver[index])])
                   for index, point in enumerate(points)]
        merged = assemble_world_graph(records + records[:5], selection["core_span"])
        self.assertEqual(merged["node_ids"], graph["node_ids"])
        self.assertEqual(merged["identity_sha256"], graph["identity_sha256"])
        self.assertTrue(np.array_equal(merged["receiver"], receiver))

    def test_receiver_is_the_raw_d8_receiver(self):
        selection = self.selection
        graph = selection["graph"]
        topology = selection["topology"]
        cells = selection["node_cells"]
        raw = topology["receiver"].ravel()
        by_cell = {int(cell): index for index, cell in enumerate(cells)}
        for index, cell in enumerate(cells):
            downstream = int(raw[cell])
            expected = -1 if downstream < 0 else by_cell[downstream]
            self.assertEqual(graph["receiver"][index], expected)
        self.assertEqual(len(np.flatnonzero(graph["receiver"] < 0)), 1,
                         "the reach must end at exactly one terminal")

    def test_truncated_upstream_edges_are_declared_not_dropped(self):
        selection = self.selection
        edges = selection["cut_edges"]
        self.assertGreaterEqual(len(edges), 1, "this reach is a truncated basin and must declare its cuts")
        kept = {int(cell) for cell in selection["node_cells"]}
        seen = set()
        for edge in edges:
            self.assertGreaterEqual(edge["omitted_cell_count"], 1)
            self.assertEqual(len(edge["omitted_cells"]), edge["omitted_cell_count"])
            self.assertIn(int(round((edge["to_xz_m"][1] - selection["topology"]["origin_z_m"])
                                    / selection["topology"]["spacing_m"])) * selection["topology"]["shape"][1]
                          + int(round((edge["to_xz_m"][0] - selection["topology"]["origin_x_m"])
                                      / selection["topology"]["spacing_m"])), kept)
            for cell in edge["omitted_cells"]:
                self.assertNotIn(cell, seen, "declared subtrees must be disjoint")
                seen.add(cell)
        self.assertEqual(len(kept) + len(seen), int(selection["basin"].size),
                         "kept nodes plus declared omitted cells must cover the whole basin exactly once")

    def test_declared_boundary_scenarios_carry_the_omitted_catchments(self):
        selection = self.selection
        unit = np.array([0., 1., 4., 2., 0.], np.float64)
        edges = [dict(edge) for edge in selection["cut_edges"]]
        scenarios = boundary_scenarios(edges, unit)
        self.assertEqual(len(scenarios), len(edges))
        for (source_id, target_id, rates), edge in zip(scenarios, edges):
            self.assertTrue(source_id.startswith("boundary:"))
            self.assertEqual(rates.shape, unit.shape)
            self.assertTrue(np.all(rates >= 0.))
            self.assertAlmostEqual(float(rates.max()), float(unit.max()) * edge["omitted_cell_count"])
            self.assertTrue(np.array_equal(rates, unit * edge["omitted_cell_count"]))

    def test_width_increases_downstream_and_follows_the_repository_power_law(self):
        selection = self.selection
        spacing = selection["topology"]["spacing_m"]
        cell_area = spacing * spacing
        area = selection["node_accumulation"] * cell_area
        widths, design_q = channel_width_m(area, reference_discharge_m3_s=cell_area / 1000. / 3600.,
                                           reference_width_m=800., min_width_m=800., max_width_m=3200.)
        expected = np.clip(800. * np.sqrt(selection["node_accumulation"]), 800., 3200.)
        self.assertTrue(np.allclose(widths, expected, rtol=0., atol=1e-9))
        self.assertTrue(np.allclose(design_q, design_discharge_m3_s(area)))
        receiver = selection["graph"]["receiver"]
        for index, target in enumerate(receiver):
            if target >= 0:
                self.assertLessEqual(widths[index], widths[target] + 1e-9)
        self.assertGreater(float(widths.max()), float(widths.min()) * 2.,
                           "width must progress along the reach, not be constant")
        self.assertGreaterEqual(float(widths.min()), 400. * 2.)

    def test_node_cap_is_configurable_but_still_guarded(self):
        geometry = {"identity_sha256": "a" * 64}
        with self.assertRaises(ValueError) as default_cap:
            couple_nodal_reach(geometry, _NetworkStub(17), _ForcingStub(), None,
                               initial_water_volume_m3=None, initial_mobile_solid_m3=None,
                               initial_alluvium_bulk_m3=None, rock_floor_m=None,
                               config=MorphologyConfig(max_intervals=16),
                               channel_config=None, sediment_config=None)
        self.assertIn("small finite reach required", str(default_cap.exception))
        with self.assertRaises(ValueError) as widened:
            couple_nodal_reach(geometry, _NetworkStub(17), _ForcingStub(), None,
                               initial_water_volume_m3=None, initial_mobile_solid_m3=None,
                               initial_alluvium_bulk_m3=None, rock_floor_m=None,
                               config=FullReachConfig(), channel_config=None, sediment_config=None)
        self.assertNotIn("small finite reach required", str(widened.exception))


class SillLakeLedgerTest(unittest.TestCase):
    """The lake stores, spills and its water joins the total ledger exactly."""

    def _lake(self, **overrides):
        options = dict(cell_ids=[7], bed_elevation_m=[100.], cell_area_m2=[1e8], seed_cell_id=7,
                       sill_stage_m=102., head_allowance_m=1.5, sill_width_m=10000.,
                       source_identity_sha256="c" * 64, primary_target_xz_m=[0., 10000.],
                       secondary_sill=dict(stage_m=103., width_m=5000., target_xz_m=[10000., 10000.]),
                       discharge_coefficient=.4, provenance=dict(module="test"))
        options.update(overrides)
        return build_sill_lake(**options)

    def test_sill_lake_uses_the_existing_storage_and_outlet_modules(self):
        lake = self._lake()
        self.assertIsInstance(lake.storage, LakeStorage)
        self.assertTrue(all(isinstance(outlet, LakeOutlet) for outlet in lake.outlets))
        self.assertEqual(len(lake.outlets), 2, "both declared saddles are represented as outlets")
        self.assertGreater(lake.outlets[1].crest_stage_m, lake.outlets[0].crest_stage_m)
        self.assertAlmostEqual(lake.sill_depth_m, 2., places=9)
        self.assertAlmostEqual(lake.outlets[0].coefficient_m3_s_m15, sill_coefficient_m3_s_m15(10000.))
        self.assertAlmostEqual(lake.volume_at_sill_m3(), 2e8, places=3)

    def test_lake_stores_then_spills_and_closes_its_ledger(self):
        lake = self._lake()
        dt = np.full(20, 60.)
        inflow = np.full(20, 2.5e5)
        initial = lake.storage.volume_at_stage(lake.sill_stage_m - .005)
        result = integrate_sill_lake(lake, inflow, dt, initial_volume_m3=initial)
        ledger = result["ledger"]
        self.assertLess(abs(ledger["residual_m3"]), 1e-3)
        self.assertGreater(ledger["spill_m3"], 0., "a nearly full lake must spill during the storm")
        self.assertGreater(result["stage_m"][-1], lake.sill_stage_m)
        self.assertLessEqual(result["stage_m"].max(), lake.storage.max_stage_m)
        self.assertEqual(result["spill_volume_m3"].shape, (20, 2))
        self.assertGreater(result["outlet_spill_m3"][0], 0.)
        self.assertEqual(float(result["outlet_spill_m3"][1]), 0.,
                         "the higher saddle must stay dry at these stages")
        self.assertTrue(np.all(np.diff(result["volume_m3"]) >= -1e-9))

    def test_spill_cannot_exceed_the_water_that_is_there(self):
        tiny = self._lake(cell_area_m2=[1.], sill_stage_m=100.001, secondary_sill=None)
        result = integrate_sill_lake(tiny, np.zeros(2), np.full(2, 3600.), initial_volume_m3=0.002)
        for step in range(2):
            self.assertLessEqual(float(result["spill_volume_m3"][step].sum()),
                                 float(result["volume_m3"][step]) + 1e-12)
        self.assertGreaterEqual(float(result["volume_m3"].min()), 0.)
        self.assertLess(float(result["volume_m3"][-1]), 0.002,
                        "a store that cannot pass the weir rate is drained, not negative")

    def test_initial_volume_outside_the_support_is_refused(self):
        lake = self._lake()
        with self.assertRaises(ValueError):
            integrate_sill_lake(lake, np.full(2, 1e6), np.full(2, 60.),
                                initial_volume_m3=lake.capacity_m3() * 1.5)
        with self.assertRaises(ValueError):
            integrate_sill_lake(lake, np.full(2, -1e6), np.full(2, 60.), initial_volume_m3=0.)


if __name__ == "__main__":
    unittest.main()
