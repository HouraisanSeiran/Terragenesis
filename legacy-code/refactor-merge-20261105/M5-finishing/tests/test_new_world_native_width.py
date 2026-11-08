import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from terrain_pipeline.channel_geometry import build_native_width_network
from terrain_pipeline.channel_geometry import continue_width_reach

ROOT = Path('.scratch/river-upgrade-20261101')
TASK = Path('.scratch/river-width-delta-20261102')

@unittest.skipUnless((TASK/'width-reach.npz').exists(), 'saved source unavailable')
class NativeWidthIntegrationTest(unittest.TestCase):
    def test_published_network_uses_known_budget_and_preserves_water_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'network'
            # Simulate a source variant containing a stale velocity array.
            stale = Path(tmp)/'node_velocity_m_s.npy'
            np.save(stale, np.array([123.]))
            original_iterdir = Path.iterdir
            def source_files(path):
                files = list(original_iterdir(path))
                if path == ROOT/'native-network-v4':
                    files.append(stale)
                return iter(files)
            with patch.object(Path, 'iterdir', source_files):
                m = build_native_width_network(ROOT,out,sediment_reach=TASK/'width-reach.npz')
            self.assertFalse((out/'node_velocity_m_s.npy').exists())
            self.assertIn('unavailable', m['velocity_policy'])
            for name in ('corridor_capacity_bound_m3.npy','sill_extra_storage_bound_m3.npy','sill_depth_m.npy'):
                self.assertFalse((out/name).exists())
                self.assertTrue((out/('source_event_'+name)).exists())
                np.testing.assert_array_equal(np.load(out/('source_event_'+name)),np.load(ROOT/'native-network-v4'/name))
            load = lambda name: np.load(out/(name+'.npy'))
            known = load('node_sediment_known'); eligible = load('node_width_eligible')
            old = ROOT/'native-network-v4'
            self.assertEqual(known.sum(),60)
            self.assertTrue(np.all(eligible[known]))
            self.assertTrue(np.isnan(load('node_sediment_incoming_solid_m3')[~known]).all())
            np.testing.assert_array_equal(load('node_stage_m'), np.load(old/'node_stage_m.npy'))
            np.testing.assert_allclose(load('node_depth_m'), load('node_stage_m')-load('node_bed_m'))
            with np.load(TASK/'width-reach.npz') as reach:
                indices = reach['network_index']
                np.testing.assert_allclose(load('node_width_m')[indices],reach['width_m'])
                np.testing.assert_allclose(load('node_bed_m')[indices],reach['bed_m'])
                np.testing.assert_allclose(load('node_sediment_final_loose_solid_m3')[indices],reach['sediment_trace_loose_solid_m3'][-1])
            nonriver=~eligible
            np.testing.assert_array_equal(load('node_width_m')[nonriver],np.load(old/'node_width_m.npy')[nonriver])
            self.assertEqual(m['committed_bed_new_edge_failures'],0)

    def test_continuation_keeps_stocks_and_conserves(self):
        info=json.loads((TASK/'width-reach.json').read_text(encoding='utf8'))
        with np.load(TASK/'width-reach.npz') as source:
            a={k:source[k] for k in source.files}
        water,sediment=continue_width_reach(a,info['final_geometry_sha256'],duration_s=10.)
        h,s=water['arrays'],sediment['arrays']
        np.testing.assert_allclose(h['volume_m3'][0],a['storage_m3'])
        np.testing.assert_allclose(s['trace_bed_alluvium_solid_m3'][0],a['sediment_trace_loose_solid_m3'][-1])
        np.testing.assert_allclose(s['trace_mobile_solid_m3'][0],a['sediment_trace_mobile_solid_m3'][-1])
        np.testing.assert_allclose(s['domain_width_m'],a['width_m'])
        self.assertAlmostEqual(h['balance_residual_m3'].sum(),0.,places=8)
        self.assertAlmostEqual(s['step_balance_residual_m3'].sum(),0.,places=8)

class PreparationForwardingTest(unittest.TestCase):
    def test_formative_inputs_change_produced_geometry(self):
        from terrain_pipeline.new_world_rivers import prepare_rivers
        shape=(8,8)
        channel=np.zeros(shape,bool); channel[3,2]=True
        receiver=np.full(64,-1,dtype=np.int64); receiver[26]=29
        empty=np.zeros(shape,bool)
        args=dict(bed_m=np.full(shape,10.),receiver=receiver,q_m3_s=np.ones(shape),
            channel_mask=channel,ocean_mask=empty,lake_mask=empty,unknown_mask=empty,
            protected_mask=empty,origin_native_xz=(0,0),spacing_m=1.,source_identity='scenario',
            bed_hardness=.5,bank_hardness=.5)
        narrow=prepare_rivers(**args,formative_section_inputs={'fracture':0.,'bank_cohesion':1.})
        wide=prepare_rivers(**args,formative_section_inputs={'fracture':1.,'bank_cohesion':0.})
        self.assertGreater(wide['graph']['node_width_m'][26],narrow['graph']['node_width_m'][26])
        self.assertGreater(wide['arrays']['cut_depth_m'].sum(),narrow['arrays']['cut_depth_m'].sum())
