from pathlib import Path
import unittest
import numpy as np
from scipy import ndimage
from terrain_pipeline.large_delta_suite import load_source
from terrain_pipeline.large_delta_shelf_scenario import shelf_arrays, ShelfScenario

SOURCE=Path('.scratch/delta-scale-suite-20261102/source-case300')
PRODUCT=Path('.scratch/river-width-delta-20261102/shelf-source-v3')

@unittest.skipUnless((PRODUCT/'manifest.json').exists(), 'saved TD source not available')
class ShelfScenarioTest(unittest.TestCase):
    def test_source_is_unchanged_and_reproducible(self):
        parent,(raw,valid,ocean)=load_source(SOURCE)
        product,(bed,valid2,ocean2)=load_source(PRODUCT)
        unknown=np.load(SOURCE/'unknown_wet.npy')
        original=np.load(PRODUCT/'original_bed_m.npy')
        np.testing.assert_array_equal(original,raw)
        np.testing.assert_array_equal(valid,valid2)
        np.testing.assert_array_equal(ocean,ocean2)
        np.testing.assert_array_equal(np.load(PRODUCT/'unknown_wet.npy'),unknown)
        excluded=~valid|~ocean|unknown
        np.testing.assert_array_equal(bed[excluded],raw[excluded])
        self.assertTrue(np.isfinite(bed).all())
        self.assertTrue(np.all(bed[ocean&valid&~unknown]<0))
        generated=shelf_arrays(raw,valid,ocean,unknown,parent['origin_xz_m'],parent['spacing_m'])
        np.testing.assert_array_equal(generated['bed_m'],bed)
        np.testing.assert_allclose(generated['shelf_weight'],np.load(PRODUCT/'shelf_weight.npy'),rtol=0,atol=3e-8)
        self.assertNotEqual(product['source_identity'],parent['source_identity'])
        self.assertEqual(product['shelf_scenario']['parent_source_identity'],parent['source_identity'])

    def test_shallow_shelf_connects_real_receiver_to_far_domain(self):
        m,(bed,valid,ocean)=load_source(PRODUCT)
        raw=np.load(PRODUCT/'original_bed_m.npy'); unknown=np.load(PRODUCT/'unknown_wet.npy')
        a=shelf_arrays(raw,valid,ocean,unknown,m['origin_xz_m'],m['spacing_m'])
        shallow=valid&ocean&~unknown&(bed>=-30)&(bed<0)
        labels,_=ndimage.label(shallow,structure=np.ones((3,3)))
        component=labels==labels[ShelfScenario().ocean_seed_zx]
        self.assertTrue(shallow[ShelfScenario().ocean_seed_zx])
        self.assertGreater(a['forward_m'][component].max(),100000.)
        far=component&(a['forward_m']>=100000)&(a['forward_m']<=110000)
        self.assertGreater(np.ptp(a['lateral_m'][far]),50000.)
        core=(a['shelf_weight']>.999)&ocean
        self.assertGreater(np.ptp(bed[core]),1.)
        self.assertTrue(np.all(a['shelf_weight'][a['forward_m']>=130000] == 0))
        self.assertTrue(np.all(a['shelf_weight'][[0,-1],:] == 0))
        self.assertTrue(np.all(a['shelf_weight'][:,[0,-1]] == 0))
