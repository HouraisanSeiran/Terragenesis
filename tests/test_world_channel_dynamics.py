"""State inheritance and old-solver reuse in the nodal world reach adapter."""
import unittest
from unittest.mock import patch
import numpy as np

from tools.run_cross_region_tributary import make_scene
from terrain_pipeline.channel_geometry import ChannelForcing, ChannelConfig
from terrain_pipeline.surface_rivers.metric_morphology_coupling import MorphologyConfig, _unpack
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers import world_channel_dynamics as dynamics


class WorldChannelDynamicsTests(unittest.TestCase):
    def test_water_mobile_loose_rock_and_bed_continue_between_intervals(self):
        graph, geometry, network, _ = make_scene()
        n=len(network.receiver)
        forcing=ChannelForcing(np.array([0.,10.,20.,30.]),np.full((3,n),.01),graph["identity_sha256"])
        area=network.width_m*network.length_m
        alluvium=area*.002
        alluvium[0]=0.
        inputs=dict(initial_water_volume_m3=area*.2,initial_mobile_solid_m3=np.full(n,.001),
            initial_alluvium_bulk_m3=alluvium,rock_floor_m=network.bed_elevation_m-.3,
            config=MorphologyConfig(),channel_config=ChannelConfig(max_dt_seconds=.5),
            sediment_config=SedimentConfig(max_dt_seconds=.25,max_bed_change_m=.01))
        material=MaterialParameters(sediment_critical_shear_pa=0.,rock_critical_shear_pa=0.,
            sediment_erodibility_m_s_pa=1e-8,rock_erodibility_m_s_pa=1e-8,
            transport_coefficient=1e-4,settling_velocity_m_s=.001)
        water_calls=[]
        sand_calls=[]
        old_water=dynamics.solve_channel
        old_sand=dynamics.solve_sediment
        def water(network,forcing,initial,config):
            water_calls.append((network,initial.copy()))
            return old_water(network,forcing,initial,config)
        def sand(domain,forcing,material,initial,config):
            sand_calls.append((domain,initial.copy()))
            return old_sand(domain,forcing,material,initial,config)
        with patch.object(dynamics,"solve_channel",side_effect=water),patch.object(dynamics,"solve_sediment",side_effect=sand):
            result=dynamics.couple_nodal_reach(geometry,network,forcing,material,**inputs)
        a,m=result["arrays"],result["metadata"]
        self.assertEqual(len(water_calls),3)
        self.assertEqual(len(sand_calls),3)
        self.assertFalse(m["dynamic_PL_mesh_updated"])
        self.assertGreater(a["rock_removed_m3"][-1].sum(),0.)
        for k in range(3):
            np.testing.assert_array_equal(water_calls[k][1],a["water_volume_m3"][k])
            np.testing.assert_array_equal(sand_calls[k][1],a["mobile_solid_m3"][k])
            np.testing.assert_allclose(sand_calls[k][0].initial_alluvium_bulk_m3,
                                       a["loose_solid_m3"][k]/(1-material.porosity),rtol=0.,atol=1e-12)
            np.testing.assert_array_equal(water_calls[k][0].bed_elevation_m,a["node_bed_m"][k])
            edges=network.receiver>=0
            np.testing.assert_allclose(water_calls[k][0].bed_slope[edges],
                (a["node_bed_m"][k,edges]-a["node_bed_m"][k,network.receiver[edges]])/network.receiver_distance_m[edges])
            sediment=_unpack(a,m,"sediment_"+str(k))["arrays"]
            np.testing.assert_allclose(a["rock_removed_m3"][k+1]-a["rock_removed_m3"][k],
                                       sediment["trace_rock_removed_m3"][-1],rtol=0.,atol=1e-12)
        self.assertGreater(np.max(np.abs(water_calls[-1][0].bed_slope-water_calls[0][0].bed_slope)),0.)


if __name__=="__main__":
    unittest.main()
