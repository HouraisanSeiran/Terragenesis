"""Small CPU tests prove XYZ denoising/training and mask behavior, not artistic quality."""
import unittest,tempfile,json
from pathlib import Path
import numpy as np
import torch
from diffusion.paths import ROOT,configure
from vdm_diffusion.config import VdmConfig
from vdm_diffusion.network import VdmDenoiser
from vdm_diffusion.process import VectorDiffusion
from vdm_diffusion.checkpoint import save,load
from vdm_diffusion.export import export
from vdm_diffusion.landforms import CliffOperator,CliffSettings

class VdmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):configure();torch.set_num_threads(2)
    def test_training_updates_xyz_and_sampling_repeats(self):
        torch.manual_seed(91);config=VdmConfig(base_channels=8,timesteps=12)
        model=VdmDenoiser(config);process=VectorDiffusion(config,'cpu')
        condition=torch.zeros(1,7,9,11);condition[:,3]=1
        clean=torch.randn(1,3,9,11);optimizer=torch.optim.AdamW(model.parameters(),lr=.001)
        before=model.output[-1].weight.detach().clone()
        optimizer.zero_grad();loss=process.loss(model,clean,condition);loss.backward();optimizer.step()
        changed=(model.output[-1].weight.detach()-before).abs().sum(dim=(1,2,3))
        self.assertTrue(bool((changed>0).all()))
        a=process.sample(model,condition,13,6);b=process.sample(model,condition,13,6);c=process.sample(model,condition,14,6)
        self.assertTrue(torch.equal(a,b));self.assertFalse(torch.equal(a,c));self.assertEqual(tuple(a.shape),(1,3,9,11))
        self.assertGreater(a[:,0].std().item(),0);self.assertGreater(a[:,2].std().item(),0)
    def test_checkpoint_rejects_synthetic_for_normal_use(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime/tmp') as folder:
            path=Path(folder)/'fixture.pt';config=VdmConfig(base_channels=8,timesteps=12)
            save(path,VdmDenoiser(config),config,1,'synthetic-fixture','test')
            with self.assertRaisesRegex(ValueError,'Synthetic'):load(path,'cpu')
            model,restored,meta=load(path,'cpu',True);self.assertEqual(restored.base_channels,8)
            self.assertEqual(meta['training_steps'],1)
    def test_special_cliffs_obey_mask_and_leave_original(self):
        vectors=np.zeros((3,16,16),dtype=np.float32);vectors[1]=50
        before=vectors.copy();mask=np.zeros((16,16),dtype=np.float32);mask[4:12,4:12]=1
        result=CliffOperator(CliffSettings((8,8),(1,1))).apply(vectors,{'origin':[0,0],'spacing':1},mask)
        np.testing.assert_array_equal(vectors,before);np.testing.assert_array_equal(result[:,mask==0],before[:,mask==0])
        self.assertTrue((result[:,mask>0]!=before[:,mask>0]).any())
    def test_export_retains_signed_vectors(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime/tmp') as folder:
            v=np.arange(3*8*8,dtype=np.float32).reshape(3,8,8)-64
            export(folder,v,{'origin':[-8,0],'spacing':2})
            raw=(Path(folder)/'displacement.rmdv').read_bytes()
            self.assertEqual(raw[:4],b'VDM1');self.assertEqual(len(raw),28+v.size*4)
            np.testing.assert_array_equal(np.frombuffer(raw[28:],dtype='<f4').reshape(8,8,3),v.transpose(1,2,0))

if __name__=='__main__':unittest.main()
