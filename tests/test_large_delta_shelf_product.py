import json
from pathlib import Path
import unittest
import numpy as np
from scipy import ndimage
from terrain_pipeline.large_delta_suite import load_source
from terrain_pipeline.large_delta_shelf_product import _bounded_bed

ROOT=Path('.scratch/river-width-delta-20261102')
CASE=ROOT/'shelf-fan-v1'

@unittest.skipUnless((CASE/'manifest.json').exists(),'saved shelf fan unavailable')
class ShelfFanProductTest(unittest.TestCase):
    def test_saved_source_and_finite_formation(self):
        manifest=json.loads((CASE/'manifest.json').read_text(encoding='utf8'))
        sm,(source,valid,ocean)=load_source(manifest['source'])
        with np.load(CASE/'product.npz') as a:
            np.testing.assert_array_equal(a['source_bed_m'],source)
            np.testing.assert_array_equal(a['valid'],valid)
            np.testing.assert_array_equal(a['source_ocean'],ocean)
            np.testing.assert_allclose(a['geological_bed_m'],source+a['deposit_m'])
            self.assertTrue(np.all(a['deposit_m'][~ocean]==0))
            self.assertTrue(np.all(np.diff(a['progress_bed_m'],axis=0)>=-1e-10))
            np.testing.assert_allclose(a['progress_bed_m'][-1],a['geological_bed_m'])
            solid=a['deposit_m'].sum()*sm['spacing_m']**2*(1-manifest['scenario']['porosity'])
            self.assertAlmostEqual(solid,manifest['formation']['retained_solid_m3'],delta=.01)
            self.assertAlmostEqual(manifest['formation']['inventory_solid_m3'],solid+manifest['formation']['unplaced_solid_m3'],delta=.01)
            self.assertEqual(sm['source_identity'],manifest['source_identity'])

    def test_shared_sections_and_connected_sea(self):
        m=json.loads((CASE/'manifest.json').read_text(encoding='utf8'))
        with np.load(CASE/'product.npz') as a:
            s=a['sections'];p=a['parent']; bed=a['final_bed_m'];
            np.testing.assert_allclose(s[:,9],bed[s[:,3].astype(int),s[:,4].astype(int)])
            for i in range(len(p)):
                reach=s[s[:,0]==i]
                self.assertTrue(np.all(np.diff(reach[:,9])<=-.001+1e-7))
                children=np.flatnonzero(p==i)
                if len(children):
                    self.assertAlmostEqual(reach[0,8],sum(s[s[:,0]==j][0,8] for j in children))
            cuts=a['geological_bed_m']-bed
            self.assertGreaterEqual(cuts.min(),-1e-8)
            self.assertLessEqual(cuts.max(),7.+1e-8)
            self.assertLessEqual(np.max(a['source_bed_m']-bed),3.+1e-8)
            sea=ndimage.binary_dilation(a['ocean'],structure=np.ones((3,3)))
            self.assertTrue(all(sea[tuple(pos)] for pos in m['audit']['outlet_zx']))
            self.assertGreater(max(m['audit']['outlet_forward_km']),100.)
            self.assertEqual(len(a['source_path_zx']),9)
            self.assertTrue(np.all(s[:,6]<600))

class ClosureTest(unittest.TestCase):
    def test_strict_downhill_closure_respects_formed_cut_limit(self):
        section=np.zeros((3,10));section[:,0]=0;section[:,3]=[0,0,0];section[:,4]=[0,1,2]
        n={'sections':section,'parent':np.array([-1]),'bed_m':np.array([[2.,3.,1.]])}
        closed,cut,_=_bounded_bed(n,np.array([[2.,3.,1.]]),1.,max_cut_m=2.)
        self.assertTrue(np.all(np.diff(closed['sections'][:,9])<0))
        self.assertLess(cut,2.)
        with self.assertRaises(ValueError):
            _bounded_bed(n,np.array([[2.,3.,1.]]),1.,max_cut_m=.5)
