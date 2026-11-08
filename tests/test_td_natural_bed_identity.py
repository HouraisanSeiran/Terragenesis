from dataclasses import replace
import unittest

import numpy as np

from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.td_natural_bed_identity import natural_bed_shape_identity
from terrain_pipeline.channel_geometry import NaturalGeometryRecipe, build_natural_channel_geometry
from terrain_pipeline.td_natural_river_network import NaturalNetworkRecipe, build_natural_river_network


class NaturalBedShapeIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        height = np.fromfunction(lambda row, column: 100. - row - column, (12, 12))
        cls.hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=30.))

    def build(self, network_recipe=NaturalNetworkRecipe(), geometry_recipe=NaturalGeometryRecipe()):
        network = build_natural_river_network(
            self.hierarchy, expected_hierarchy_identity=self.hierarchy["identity_sha256"],
            recipe=network_recipe)
        return network, build_natural_channel_geometry(network, geometry_recipe)

    def test_strong_event_changes_bundle_identity_but_not_bed_shape(self):
        ordinary_recipe = NaturalNetworkRecipe()
        first_network, first_geometry = self.build(ordinary_recipe)
        second_network, second_geometry = self.build(
            replace(ordinary_recipe, strong_rainfall_mm=ordinary_recipe.strong_rainfall_mm + 10.))
        self.assertEqual(first_network["metadata"]["stable_identity_sha256"],
                         second_network["metadata"]["stable_identity_sha256"])
        self.assertNotEqual(first_geometry["identity_sha256"], second_geometry["identity_sha256"])
        self.assertEqual(natural_bed_shape_identity(first_network, first_geometry),
                         natural_bed_shape_identity(second_network, second_geometry))

    def test_ordinary_morphology_and_bed_recipe_change_shape_identity(self):
        baseline_network, baseline_geometry = self.build()
        baseline_identity = natural_bed_shape_identity(baseline_network, baseline_geometry)
        changed_network, changed_geometry = self.build(
            replace(NaturalNetworkRecipe(), normal_rainfall_mm=35.))
        self.assertNotEqual(baseline_identity,
                            natural_bed_shape_identity(changed_network, changed_geometry))
        recipe_network, recipe_geometry = self.build(
            geometry_recipe=replace(NaturalGeometryRecipe(), max_cut_m=5.))
        self.assertNotEqual(baseline_identity,
                            natural_bed_shape_identity(recipe_network, recipe_geometry))

    def test_complete_network_association_is_required(self):
        first_network, first_geometry = self.build()
        second_network, second_geometry = self.build(
            replace(NaturalNetworkRecipe(), strong_rainfall_mm=130.))
        self.assertNotEqual(first_geometry["identity_sha256"], second_geometry["identity_sha256"])
        with self.assertRaisesRegex(ValueError, "another complete network bundle"):
            natural_bed_shape_identity(second_network, first_geometry)
        with self.assertRaisesRegex(ValueError, "another complete network bundle"):
            natural_bed_shape_identity(first_network, second_geometry)


if __name__ == "__main__":
    unittest.main()
