import json, tempfile, unittest
from pathlib import Path
from tools.run_large_delta_trial import SHAPE, SPACING, initial_product, report
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_delta_fv import advance, save, load

class LargeDeltaTrialTests(unittest.TestCase):
    def test_geometry_is_large_native_domain_and_budget_closes(self):
        p=initial_product(max_wall_s=30.)
        self.assertEqual(p['arrays']['bed_m'].shape, (128,128)); self.assertEqual(SHAPE,(128,128)); self.assertEqual(SPACING,30.)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'initial.npz'; save(path,p); q=load(path,expected_sha256=file_sha256(path))
            r=advance(q,[{'id':'smoke','source':'test river','time_start_s':0.,'time_end_s':20.,'water_m3':3600.,'solid_m3':16.}])
            save(Path(d)/'final.npz',r); out=report(r,'smoke',Path(d)/'final.npz')
            self.assertLess(abs(out['water_budget_residual_m3']),1e-5); self.assertLess(abs(out['solid_budget_residual_m3']),1e-5)
            self.assertEqual(out['shape_zx'],[128,128]); self.assertEqual(out['spacing_m'],30.)

if __name__=='__main__': unittest.main()
