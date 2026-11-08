import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import simulate_hour as simulate_hour
from terrain_pipeline.basin_storage import storagev10_save_storage as save_storage
from terrain_pipeline.basin_storage import save_checkpoint as save_checkpoint
from terrain_pipeline.basin_storage import storagev10_load_checkpoint as load_checkpoint
from terrain_pipeline.basin_storage import validate_storage as validate_storage
from terrain_pipeline.td_native_weather_storage_v10_io import validate_native_v10_accounts


class V10Tests(unittest.TestCase):
    def test_spatial_24h_two_steps_and_exact_restart(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[2., 0.], [1., 0.]]), spacing_m=30))
        rain = np.zeros((24, 2, 2))
        rain[:6] = np.array([[2.288880014936935, 30.], [15., .15]])
        final = []
        with tempfile.TemporaryDirectory() as temporary:
            for step in (2.5, 1.25):
                direct = None
                reloaded = None
                for hour in range(24):
                    result = simulate_hour(hierarchy, rain, substep_s=step, checkpoint=direct)
                    resumed = simulate_hour(hierarchy, rain, substep_s=step, checkpoint=reloaded)
                    validate_native_v10_accounts(result['storage'], hierarchy=hierarchy, rain_mm_h=rain[hour])
                    for role in ('storage', 'checkpoint'):
                        for key in result[role]['arrays']:
                            np.testing.assert_array_equal(result[role]['arrays'][key], resumed[role]['arrays'][key])
                    direct = result['checkpoint']
                    path = Path(temporary)/f'{step}-{hour}.npz'
                    save_checkpoint(path, direct)
                    reloaded = load_checkpoint(path, expected_sha256=file_sha256(path), expected_identity=direct['identity_sha256'])
                    self.assertLess(abs(result['storage']['arrays']['balance_residual_m3'].sum()), 1e-6)
                final.append(direct['arrays']['depth_m'])
        self.assertLess(np.max(abs(final[0]-final[1])), .001)

    def test_negative_forcing_checkpoint_and_rehashed_cfl(self):
        valid = np.array([[True, False], [True, True]])
        hierarchy = build_basin_hierarchy(make_td_source(np.zeros((2,2)), spacing_m=30, valid_mask=valid))
        rain = np.zeros((24,2,2))
        result = simulate_hour(hierarchy, rain, substep_s=2.5)
        bad_rain = rain.copy(); bad_rain[23,0,0] = np.nan
        with self.assertRaises(ValueError):
            simulate_hour(hierarchy, bad_rain, substep_s=2.5)
        different = rain.copy(); different[23,0,0] = 1
        with self.assertRaises(ValueError):
            simulate_hour(hierarchy, different, substep_s=2.5, checkpoint=result['checkpoint'])
        arrays = dict(result['checkpoint']['arrays'])
        arrays['error_depth'] = arrays['error_depth'].copy(); arrays['error_depth'][1] = -1
        forged = {'arrays':arrays,'metadata':result['checkpoint']['metadata'], 'identity_sha256':identity(arrays,result['checkpoint']['metadata'])}
        with self.assertRaises(ValueError):
            simulate_hour(hierarchy, rain, substep_s=2.5, checkpoint=forged)
        page = result['storage']
        metadata = {**page['metadata'], 'positivity_cfl':float('nan')}
        with self.assertRaises(ValueError):
            validate_storage({'arrays':page['arrays'],'metadata':metadata,'identity_sha256':identity(page['arrays'],metadata)})
        metadata = {**page['metadata'], 'substeps':720, 'substep_s':5.}
        with self.assertRaises(ValueError):
            validate_storage({'arrays':page['arrays'],'metadata':metadata,'identity_sha256':identity(page['arrays'],metadata)})

    def test_fresh_cold_io_does_not_import_solver(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.zeros((2,2)), spacing_m=30))
        result = simulate_hour(hierarchy, np.zeros((24,2,2)), substep_s=2.5)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'page.npz';save_storage(path,result['storage'])
            code = (f"""import sys; from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage; load_storage({str(path)!r},expected_sha256={file_sha256(path)!r},expected_identity={result['storage']['identity_sha256']!r}); assert "terrain_pipeline.basin_storage" in sys.modules; assert "terrain_pipeline.td_basin_storage_v10" not in sys.modules; assert "terrain_pipeline.td_basin_transport_v6" not in sys.modules""")
            subprocess.run([sys.executable,'-c',code],check=True)


if __name__ == '__main__':
    unittest.main()
