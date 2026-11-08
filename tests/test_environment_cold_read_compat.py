"""Cold readers accept the verified pre-consolidation geology source names."""
from copy import deepcopy
from pathlib import Path
import hashlib
import unittest
from unittest.mock import patch

from terrain_pipeline import environment_product, geology
from terrain_pipeline.common_infra import load_bundle


ROOT = Path(__file__).resolve().parents[1]
DELIVERED = ROOT / '.scratch/stage2-finish-20261030/g6-evidence/product.npz'
DELIVERED_SHA = '3ae0cb29959c836c9262da75b9bb6ffae8cefe4ba4be7271534214f9eb572f84'
HISTORICAL_SOURCES = (
    'terrain_pipeline.td_material_field.make_material_field',
    'terrain_pipeline.td_lithology_field.sample_lithology_points',
)


def historical_bundle():
    bundle = deepcopy(geology.properties_at([30.], [60.], world_seed=20261020))
    for layer, source in zip(bundle['layer_definitions'], HISTORICAL_SOURCES):
        layer['property_source'] = source
    resign(bundle)
    return bundle


def resign(bundle):
    bundle['identity_sha256'] = geology._properties_identity(
        bundle['arrays'], bundle['metadata'], bundle['layer_definitions'])


class GeologyHistoricalSourceTests(unittest.TestCase):
    def test_historical_sources_keep_original_identity_and_definitions(self):
        bundle = historical_bundle()
        before = deepcopy(bundle)
        with patch.object(geology, 'sample_lithology_points', side_effect=AssertionError('resampled')):
            self.assertTrue(geology.validate_geology_properties(bundle))
        self.assertEqual(bundle['identity_sha256'], before['identity_sha256'])
        self.assertEqual(bundle['layer_definitions'], before['layer_definitions'])

    def test_known_aliases_do_not_bypass_identity_check(self):
        bundle = historical_bundle()
        bundle['identity_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            geology.validate_geology_properties(bundle)

    def test_unknown_sources_and_changed_layer_semantics_still_fail_even_if_resigned(self):
        for field, value in [('property_source', 'unknown.make_material_field'),
                             ('semantics', 'changed'), ('order', 9),
                             ('thickness_field', 'soil_depth_m')]:
            with self.subTest(field=field):
                bundle = historical_bundle()
                bundle['layer_definitions'][0][field] = value
                resign(bundle)
                with self.assertRaisesRegex(ValueError, 'layer definitions differ'):
                    geology.validate_geology_properties(bundle)

    def test_current_construction_keeps_current_sources(self):
        bundle = geology.properties_at([30.], [60.], world_seed=20261020)
        self.assertEqual(bundle['layer_definitions'], geology.layer_definitions())
        self.assertEqual(bundle['layer_definitions'][0]['property_source'],
                         'terrain_pipeline.geology.make_material_field')
        self.assertTrue(geology.validate_geology_properties(bundle))

    def test_partial_migration_and_extra_layer_keys_are_not_historical_stacks(self):
        for change in ('partial', 'extra'):
            with self.subTest(change=change):
                bundle = historical_bundle()
                if change == 'partial':
                    bundle['layer_definitions'][0]['property_source'] = geology.layer_definitions()[0]['property_source']
                else:
                    bundle['layer_definitions'][0]['unknown_key'] = 'unknown'
                resign(bundle)
                with self.assertRaisesRegex(ValueError, 'layer definitions differ'):
                    geology.validate_geology_properties(bundle)

    @unittest.skipUnless(DELIVERED.is_file(), 'local delivered product not installed')
    def test_real_delivered_packed_product_cold_load_and_query_preserve_identity(self):
        before = hashlib.sha256(DELIVERED.read_bytes()).hexdigest()
        self.assertEqual(before, DELIVERED_SHA)
        saved = load_bundle(DELIVERED, expected_sha256=DELIVERED_SHA,
                            validator=lambda bundle: None)
        expected = saved['metadata']['tree']['seasonal']['material_source']
        with patch.object(geology, 'properties_at', side_effect=AssertionError('resampled')):
            product = environment_product.load_product(DELIVERED, expected_sha256=DELIVERED_SHA)
            result = environment_product.query_product(product, 2, 2)
        material = product['seasonal']['material_source']
        self.assertEqual(material['identity_sha256'], expected['identity_sha256'])
        self.assertEqual(material['layer_definitions'], expected['layer_definitions'])
        self.assertEqual(result['row'], 2)
        self.assertEqual(environment_product.product_identity(product), saved['identity_sha256'])
        self.assertEqual(hashlib.sha256(DELIVERED.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
