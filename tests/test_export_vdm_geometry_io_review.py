import copy
import json
import tempfile
import unittest
from pathlib import Path
from tools.export_vdm_cuts_review import FIXED_PINS, load_inputs, read_record

class VdmGeometryIoReviewTests(unittest.TestCase):

    def test_fixed_case_loads_all_pinned_geometry_without_exporting(self):
        records, payloads, dependencies = load_inputs(FIXED_PINS)
        self.assertEqual(records['geometry']['schema'], 'td-hybrid-river-geometry-v1')
        self.assertEqual(records['vdm']['schema'], 'td-hybrid-multichart-vdm-v1')
        self.assertEqual(len(records['vdm']['stations']), 17)
        self.assertEqual(len(records['geometry']['hydraulic_cells']), 19)
        self.assertTrue(all((records['review'][name] is False for name in ('hydraulic_solved', 'three_dimensional_flow_solved', 'full_network_verified', 'natural_outlet_certified'))))
        self.assertIsNone(records['review']['pins'].get('water'))
        self.assertGreater(len(payloads), 0)
        self.assertGreater(len(dependencies), 0)

    def test_tampered_pinned_json_is_rejected(self):
        source = Path(FIXED_PINS['audit']['path'])
        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / 'audit.json'
            record = json.loads(source.read_text(encoding='utf-8'))
            record['status'] = 'failed'
            tampered.write_text(json.dumps(record), encoding='utf-8')
            pin = copy.deepcopy(FIXED_PINS['audit'])
            pin['path'] = str(tampered)
            with self.assertRaises(ValueError):
                read_record(pin, 'td-hybrid-cave-geometry-independent-audit-v1')
