"""Independent integration regressions for supplemental physical-state contracts."""

import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_channel_state import ChannelForcing
from terrain_pipeline.surface_rivers.metric_morphology_coupling import MorphologyConfig, couple_morphology, validate_morphology_coupling
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from tests import test_metric_morphology_coupling as fixtures


class ExtensionReviewTests(unittest.TestCase):
    def test_morphology_later_failure_preserves_committed_water_and_material(self):
        geometry, network, _ = fixtures.MorphologyCouplingTests().fixture()
        forcing = ChannelForcing(np.array([0., .5, 1.]), np.zeros((2,3)), "b"*64)
        material = MaterialParameters(settling_velocity_m_s=.0001,
                                      sediment_critical_shear_pa=1e9, rock_critical_shear_pa=1e9)
        inputs = dict(initial_water_volume_m3=np.full(3,.1), initial_mobile_solid_m3=np.full(3,.001),
                      initial_alluvium_bulk_m3=np.zeros(3), rock_floor_m=fixtures.bed_floor(network))
        full = couple_morphology(geometry, network, forcing, material, **inputs)
        first = float(np.max(np.abs(full["arrays"]["mesh_bed_m"][1]-full["arrays"]["mesh_bed_m"][0])))
        last = float(np.max(np.abs(full["arrays"]["mesh_bed_m"][-1]-full["arrays"]["mesh_bed_m"][0])))
        self.assertGreater(last, first)
        result = couple_morphology(geometry, network, forcing, material, **inputs,
            config=MorphologyConfig(max_cumulative_bed_change_m=(first+last)/2.))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertEqual(result["metadata"]["last_time_seconds"], .5)
        self.assertEqual(len(result["metadata"]["intervals"]), 1)
        for key in ("water_volume_m3", "mobile_solid_m3", "loose_solid_m3", "rock_removed_m3", "mesh_bed_m"):
            np.testing.assert_array_equal(result["arrays"][key][-1], full["arrays"][key][1])
        validate_morphology_coupling(result)


if __name__ == "__main__":
    unittest.main()
