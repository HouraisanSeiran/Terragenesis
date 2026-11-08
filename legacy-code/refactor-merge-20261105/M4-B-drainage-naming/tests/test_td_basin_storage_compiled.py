import unittest
import numpy as np
from terrain_pipeline.basin_storage import advance_hour_compensated as advance_hour
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import storagev7_simulate as simulate_basin_storage
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters


class CompiledExecutionTests(unittest.TestCase):
    def test_tiny_hour_equivalence(self):
        hierarchy=build_basin_hierarchy(make_td_source(np.array([[2.,0.,1.],[0.,2.,0.]]),spacing_m=30))
        topology=hierarchy["arrays"]
        runoff=RunoffParameters()
        for step in (5.,2.5):
            initial=np.array([[1.,0.,.2],[0.,.5,.1]])
            reference=simulate_basin_storage(hierarchy,np.array([30.]),dt_s=60,initial_depth_m=initial,parameters={"substep_s":step})
            states=np.vstack((initial.ravel(),np.full(6,30.),np.zeros(6),np.zeros(6)))
            result=advance_hour(states,np.zeros((4,6)),np.full(6,30.),topology["height_m"].ravel(),topology["face_cells"],topology["boundary_cells"],reference["arrays"]["boundary_width_m"],topology["receiver"],30.,step,round(60/step),
                np.array([runoff.infiltration_capacity_mm_h,runoff.soil_capacity_mm,runoff.potential_et_mm_h,runoff.percolation_mm_h,runoff.fast_tau_s,runoff.slow_tau_s]),np.array([.6,1e-9,.15]))
            for index,key in enumerate(("depth_m","soil_mm","fast_mm","slow_mm")):
                np.testing.assert_allclose(result[0][index],reference["arrays"][key][-1],rtol=0,atol=1e-12)
            for index,key in enumerate(("rain_volume_m3","lake_rain_m3","land_rain_m3","soil_et_m3","local_release_m3","surface_et_m3","internal_net_m3","boundary_outflow_m3")):
                np.testing.assert_allclose(result[2][index],reference["arrays"][key][0],rtol=1e-12,atol=1e-10)
            for index,key in enumerate(("face_forward_m3","face_reverse_m3","active_forward_s","active_reverse_s","routed_volume_m3","wet_duration_s")):
                np.testing.assert_allclose(result[index+3],reference["arrays"][key],rtol=1e-12,atol=1e-10)


if __name__ == "__main__":
    unittest.main()
