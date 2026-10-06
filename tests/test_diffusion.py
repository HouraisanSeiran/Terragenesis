"""Protocol/cache fixtures; these tests do not claim to run the neural model."""
import unittest,tempfile,threading,struct
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from diffusion.paths import ROOT,configure
from diffusion.config import GenerationConfig
from diffusion.service import TerrainService
from diffusion.store import TerrainTileStore

class FixtureBackend:
    identity='fixture-only'
    def __init__(self,config):self.calls=0;self.busy=False
    def generate(self,seed,x,z,size):
        if self.busy:raise AssertionError('Concurrent model access')
        self.busy=True;self.calls+=1
        zz,xx=np.mgrid[z:z+size,x:x+size]
        elev=(xx+zz*2+seed).astype('float32')
        self.busy=False
        return elev,np.stack([elev]*4),{'seed':str(seed)}

class DiffusionTests(unittest.TestCase):
    def setUp(self):
        configure();self.temp=tempfile.TemporaryDirectory(dir=ROOT/'runtime/tmp')
        self.patch=patch('diffusion.store.ROOT',Path(self.temp.name));self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def service(self):
        with patch('diffusion.service.TerrainDiffusionBackend',FixtureBackend):return TerrainService(GenerationConfig())
    def test_cache_seed_seams_and_protocol(self):
        s=self.service();a=s.tile(9,-1,0)[0];b=s.tile(9,0,0)[0]
        np.testing.assert_array_equal(a[:,-1],b[:,0])
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:s.tile(9,0,0),range(8)))
        self.assertEqual(s.backend.calls,2)
        self.assertFalse(np.array_equal(b,s.tile(10,0,0)[0]))
        payload=s.payload(9,0,0)
        self.assertEqual(struct.unpack('<4siiiif',payload[:24]),(b'RMD2',65,2,72,0,30))
        values=np.frombuffer(payload[24:],dtype='<f4').reshape(65,65,3)
        np.testing.assert_array_equal(values[:,:,0],b)
    def test_corrupt_cache_fails_without_regeneration(self):
        s=self.service();s.tile(1,0,0);s.store.path(1,0,0).write_bytes(b'corruption')
        with self.assertRaises(RuntimeError):s.tile(1,0,0)
        self.assertEqual(s.backend.calls,1)
    def test_model_failure_has_no_fallback(self):
        s=self.service()
        with patch.object(s.backend,'generate',side_effect=RuntimeError('model failed')):
            with self.assertRaisesRegex(RuntimeError,'model failed'):s.tile(1,0,0)
        self.assertFalse(s.store.path(1,0,0).exists())
    def test_cache_identity_isolation(self):
        self.assertNotEqual(TerrainTileStore('first').path(1,0,0),TerrainTileStore('second').path(1,0,0))
    def test_nonfinite_model_output_rejected(self):
        s=self.service()
        with patch.object(s.backend,'generate',return_value=(np.full((65,65),np.nan),np.zeros((4,65,65)),{})):
            with self.assertRaisesRegex(RuntimeError,'Non-finite'):s.tile(1,0,0)

if __name__=='__main__':unittest.main()
