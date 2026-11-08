"""Actual owning-core boundary selection, without invented receivers."""
import unittest
import numpy as np
from terrain_pipeline.surface_rivers.metric_domain_closure import clear_cache
from tools.run_real_world_tributary import select_real_reach, cell_at, world_xz
from terrain_pipeline.surface_rivers.world_channel_graph import derive_noise_seed


class RealWorldTributaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.left, cls.right, cls.selected, cls.answers, cls.upstream = select_real_reach()

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    def test_fixed_world_subsystem_seeds_do_not_depend_on_request_order(self):
        ordered={p:derive_noise_seed(20261020,p) for p in ("climate","rainfall","light")}
        reversed_order={p:derive_noise_seed(20261020,p) for p in ("light","rainfall","climate")}
        self.assertEqual(ordered,reversed_order)
        self.assertEqual(len(set(ordered.values())),3)
        self.assertNotEqual(derive_noise_seed(20261020,"rainfall"),derive_noise_seed(20261021,"rainfall"))

    def test_boundary_is_derived_from_actual_adjacent_owning_cores(self):
        left, right = self.left, self.right
        self.assertEqual(right["core_origin_x_m"], left["core_origin_x_m"] + left["core_cells"]*left["spacing_m"])
        self.assertEqual(right["core_origin_x_m"],1280000.)
        self.assertEqual(len(set(self.graph["region_ids"])),2)
        self.assertEqual(len(self.graph["cross_region_donors"]),2)

    def test_edges_are_original_world_receivers_and_adjacent_answers_agree(self):
        for i,j in enumerate(self.graph["receiver"]):
            if j>=0:
                cell=cell_at(self.left,self.graph["node_xz_m"][i])
                actual=world_xz(self.left,self.left["receiver"].ravel()[cell])
                np.testing.assert_array_equal(actual,self.graph["node_xz_m"][j])
        self.assertTrue(all(answer["identical"] for answer in self.answers))
        donors=np.bincount(self.graph["receiver"][self.graph["receiver"]>=0],minlength=len(self.selected))
        self.assertEqual(np.count_nonzero(donors==2),1)

    def test_omitted_upstream_is_recorded_as_boundary_not_silently_zero(self):
        self.assertGreater(len(self.upstream),0)
        chosen={tuple(p) for p in self.graph["node_xz_m"]}
        for edge in self.upstream:
            self.assertNotIn(tuple(edge["from_xz_m"]),chosen)
            self.assertIn(tuple(edge["to_xz_m"]),chosen)
            self.assertIn("boundary_scenario",edge["source"])


if __name__=="__main__":
    unittest.main()
