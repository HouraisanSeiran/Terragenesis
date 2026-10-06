import unittest
import numpy as np
from terrain_pipeline.conversion import height_to_vdm
from vdm_diffusion.landforms import CliffOperator,CliffSettings

class TerrainPipelineTests(unittest.TestCase):
    def test_conversion_preserves_remapped_height_and_has_no_lateral_motion(self):
        h=np.array([[-300,0],[900,3000]],dtype=np.float32);v=height_to_vdm(h)
        self.assertTrue(np.all(v[[0,2]]==0));self.assertEqual(v[1,0,1],0)
        self.assertAlmostEqual(float(v[1,1,0]),225*np.tanh(30/225),places=5)
        self.assertLess(v[1,0,0],0)
    def test_cliff_changes_xyz_but_preserves_boundary(self):
        v=height_to_vdm(np.full((129,129),1500,np.float32))
        z,x=np.mgrid[:129,:129];mask=np.clip(1-np.hypot((x-64)/40,(z-64)/40),0,1)
        result=CliffOperator(CliffSettings((128,128),(1,.35),42,5,8)).apply(v,{'origin':[0,0],'spacing':2},mask)
        np.testing.assert_array_equal(result[:,mask==0],v[:,mask==0])
        self.assertGreater(float(np.abs(result[0]).max()),1);self.assertGreater(float(np.abs(result[2]).max()),1)
        self.assertGreater(float(np.abs(result[1]-v[1]).max()),5)

if __name__=='__main__':unittest.main()
