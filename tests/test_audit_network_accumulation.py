"""Audit CLI integration: crop boundaries and product cold-read, no real TD required."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.audit_network_accumulation import run
from terrain_pipeline.surface_rivers.metric_network_discharge_product import load_discharge_product


class AuditNetworkProductTests(unittest.TestCase):
    def test_crop_link_is_unknown_and_saved_with_negative_world_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.npz'
            np.savez(source,
                     receiver=np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64),
                     covered_mask=np.ones((2, 4), bool),
                     routed_q_m3_s=np.zeros((2, 4), np.float64),
                     origin_native_cells=np.array([-3, 4], np.int64))
            with contextlib.redirect_stdout(io.StringIO()):
                run(source, root / 'cropped', side=1)
            product = load_discharge_product(root / 'cropped/flow-product')
            arrays = product['arrays']
            np.testing.assert_array_equal(arrays['receiver'], [[-1]])
            np.testing.assert_array_equal(arrays['terminal_kind'], [['unknown_boundary']])
            np.testing.assert_array_equal(arrays['upstream_unknown_mask'], [[True]])
            np.testing.assert_array_equal(arrays['complete_mask'], [[False]])
            self.assertEqual(product['metadata']['origin_native_cells'], [-3, 4])
            report = json.loads((root / 'cropped/report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['product_identity_sha256'], product['identity_sha256'])
            self.assertTrue(report['independent_path_executed'])
            self.assertEqual(report['independent_path_max_abs_difference_m3_s'], 0.)

    def test_full_graph_mode_preserves_receiver_and_records_no_full_path_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.npz'
            rec = np.array([[1, 2, -1]], np.int64)
            np.savez(source, receiver=rec, covered_mask=np.ones((1, 3), bool),
                     routed_q_m3_s=np.zeros((1, 3), np.float64),
                     origin_native_cells=np.array([10, 20], np.int64))
            with contextlib.redirect_stdout(io.StringIO()):
                run(source, root / 'full', side=0)
            product = load_discharge_product(root / 'full/flow-product')
            np.testing.assert_array_equal(product['arrays']['receiver'], rec)
            report = json.loads((root / 'full/report.json').read_text(encoding='utf-8'))
            self.assertFalse(report['independent_path_executed'])
            self.assertIsNone(report['independent_path_max_abs_difference_m3_s'])
            self.assertLessEqual(report['ledger_relative_residual'], 1e-12)


if __name__ == '__main__':
    unittest.main()
