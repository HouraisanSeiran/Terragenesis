import unittest
import tempfile
import copy
from pathlib import Path
from unittest.mock import patch
import numpy as np
from terrain_pipeline.hydrology_planning import FrozenPlanningCatalog, PlanningConfig, PlanningError, coarse_condition_field, edit_domain_height, plan_canonical_support, plan_macro_cell, query_macro_cell, save_plan, load_plan, select_development_pair, validate_plan, _steepest_receivers, _support_pair_conflict, _identity, _product_mesh


WORLD_SEED = 20261020


def synthetic_coastal_lake_source(seed, x, z, config=None):
    """Periodic islands give complete inland/coastal divides across support windows."""
    span = (config or PlanningConfig()).macro_span_m
    macro_x, macro_z = np.floor(x / span).astype(int), np.floor(z / span).astype(int)
    local_x, local_z = x - (macro_x + .5) * span, z - (macro_z + .5) * span
    height = 500 - (local_x ** 2 + local_z ** 2) / 16000000
    height = np.minimum(height, 150 + ((local_x - 20000) ** 2 + local_z ** 2) / 4000000)
    height += local_x * .0001 + local_z * .000017
    return height, macro_x, macro_z


class HydrologyPlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_patch = patch('terrain_pipeline.hydrology_planning.coarse_condition_field', synthetic_coastal_lake_source)
        cls.source_patch.start()
        cls.addClassCleanup(cls.source_patch.stop)
        cls.plan = plan_macro_cell(WORLD_SEED)

    def test_actual_graph_and_complete_domains(self):
        plan = self.plan
        lake = plan['domains'][1]['lake_terminal_index']
        actual = _steepest_receivers(plan['height_m'], plan['ocean_mask'], [lake], _product_mesh(plan))
        owned = plan['owner_domain_id'].reshape(-1) >= 0
        np.testing.assert_array_equal(actual[owned], plan['receiver'].reshape(-1)[owned])
        self.assertTrue(validate_plan(plan))
        self.assertGreater(len(plan['shared_boundary_edges']), 0)
        self.assertFalse(plan['budget']['complete_world_coverage'])

    def test_same_world_coordinates_same_shared_condition(self):
        x = np.linspace(-200000, 200000, 41)
        left = coarse_condition_field(1, x, x / 3)[0]
        right = np.array([coarse_condition_field(1, xx, xx / 3)[0] for xx in x])
        np.testing.assert_array_equal(left, right)
        self.assertEqual(query_macro_cell(1, 0, 0), query_macro_cell(1, 0, 0))

    def test_cold_roundtrip_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan.npz'
            save_plan(self.plan, path)
            cold = load_plan(path)
            self.assertEqual(cold['identity_sha256'], self.plan['identity_sha256'])
            with self.assertRaises(FileExistsError):
                save_plan(self.plan, path)
            cold['height_m'][0, 0] += 1
            with self.assertRaisesRegex(ValueError, 'identity'):
                validate_plan(cold)

    def test_finite_failure_and_work_budget(self):
        with patch('terrain_pipeline.hydrology_planning.coarse_condition_field', coarse_condition_field):
            with self.assertRaisesRegex(PlanningError, 'exactly one complete inland lake; found 0'):
                plan_macro_cell(3)
        with self.assertRaisesRegex(PlanningError, 'work budget'):
            plan_macro_cell(1, config=PlanningConfig(max_grid_cells=100))
        with self.assertRaisesRegex(PlanningError, 'area/volume'):
            plan_macro_cell(WORLD_SEED, config=PlanningConfig(maximum_affected_support_fraction=0))

    def test_catalog_has_finite_explicit_provisional_ownership(self):
        catalog = FrozenPlanningCatalog(WORLD_SEED)
        catalog.register(self.plan)
        row, column = np.argwhere(self.plan['owner_domain_id'] == 1)[0]
        x0, z0 = self.plan['origin_xz_m']
        query = catalog.query(x0 + column * self.plan['spacing_m'], z0 + row * self.plan['spacing_m'])
        self.assertEqual(query['candidate_count'], 25)
        self.assertEqual(query['status'], 'provisional')
        self.assertEqual(query['claims'][0]['domain_id'], 1)
        self.assertEqual(catalog.query(1e10, -1e10)['status'], 'unprepared')

    def test_real_interior_edit_preserves_neighbor_and_boundary(self):
        owner = self.plan['owner_domain_id']
        delta = np.zeros(owner.shape)
        for row, column in np.argwhere(owner == 1):
            if row > 0 and column > 0 and np.all(owner[row-1:row+2, column-1:column+2] == 1):
                index = row * owner.shape[1] + column
                if index != self.plan['domains'][1]['lake_terminal_index']:
                    delta[row, column] = 1.0
                    break
        edited = edit_domain_height(self.plan, 1, delta)
        np.testing.assert_array_equal(edited['height_m'][owner == 0], self.plan['height_m'][owner == 0])
        np.testing.assert_array_equal(edited['receiver'][owner == 0], self.plan['receiver'][owner == 0])
        self.assertNotEqual(edited['identity_sha256'], self.plan['identity_sha256'])
        boundary_delta = np.zeros(owner.shape)
        boundary_delta.reshape(-1)[self.plan['shared_boundary_edges'][0, 0]] = 1
        with self.assertRaisesRegex(PlanningError, 'boundary'):
            edit_domain_height(self.plan, 1, boundary_delta)

    def test_actual_adjacent_support_registration_order(self):
        first = plan_macro_cell(WORLD_SEED, 0, 0)
        second = plan_macro_cell(WORLD_SEED, 0, 1)
        index = first['domains'][1]['lake_terminal_index']
        row, column = divmod(index, first['height_m'].shape[1])
        x0, z0 = first['origin_xz_m']
        point = (x0 + column * first['spacing_m'], z0 + row * first['spacing_m'])
        results = []
        for products in ((first, second), (second, first)):
            catalog = FrozenPlanningCatalog(WORLD_SEED)
            for product in products:
                catalog.register(product)
            result = catalog.query(*point)
            result['claims'] = sorted(result['claims'], key=lambda claim: claim['canonical_support_id'])
            results.append(result)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]['support_conflicts'], [])

    def test_general_support_accepts_multiple_natural_lakes(self):
        def multiple_lakes(seed, x, z, config=None):
            height, mx, mz = synthetic_coastal_lake_source(seed, x, z, config)
            span = (config or PlanningConfig()).macro_span_m
            lx, lz = x - (mx + .5) * span, z - (mz + .5) * span
            first_r2, second_r2 = (lx - 60000) ** 2 + lz ** 2, (lx + 60000) ** 2 + lz ** 2
            height = np.maximum(400 - first_r2 / 4000000, 400 - second_r2 / 4000000)
            height = np.minimum(height, 100 + first_r2 / 1000000)
            height = np.minimum(height, 100 + second_r2 / 1000000)
            return height + lx * .0001 + lz * .000017, mx, mz
        with patch('terrain_pipeline.hydrology_planning.coarse_condition_field', multiple_lakes):
            support = plan_canonical_support(WORLD_SEED)
        self.assertEqual(support['status'], 'finite_canonical_support')
        self.assertGreater(sum(domain['kind'] == 'inland' for domain in support['domains']), 1)
        self.assertEqual(len(support['domains']), len(support['catchments']))
        self.assertTrue(validate_plan(support))
        pair = select_development_pair(support)
        self.assertEqual(len(pair['domains']), 2)
        np.testing.assert_array_equal(pair['height_m'], support['height_m'])
        self.assertFalse(pair['selection']['terrain_changed'])

    def test_land_ocean_identity_contradiction_is_symmetric(self):
        other = copy.deepcopy(self.plan)
        row, column = np.argwhere(self.plan['owner_domain_id'] == 1)[0]
        other['owner_domain_id'][row, column] = -1
        other['ocean_mask'][row, column] = True
        expected = 'inconsistent land versus certified ocean identity'
        self.assertEqual(_support_pair_conflict(self.plan, other), expected)
        self.assertEqual(_support_pair_conflict(other, self.plan), expected)

    def test_catalog_queries_and_registration_do_not_scan_global_registry(self):
        class NoIterationDict(dict):
            def items(self):
                raise AssertionError('global registry scan')

            def __iter__(self):
                raise AssertionError('global registry scan')

        catalog = FrozenPlanningCatalog(WORLD_SEED)
        catalog.register(self.plan)
        catalog._products = NoIterationDict(catalog._products)
        catalog._conflicts = NoIterationDict(catalog._conflicts)
        catalog.register(plan_macro_cell(WORLD_SEED, 0, 1))
        result = catalog.query(10000., 10000.)
        self.assertEqual(result['candidate_count'], 25)

    def test_coastal_group_edit_cannot_transfer_land_between_sea_terminals(self):
        height = np.tile([0., 1., 2., 3., 2., 1., 0.], (5, 1))
        ocean = height == 0
        owner = np.where(ocean, -1, 0).astype(np.int32)
        product = {'height_m': height, 'original_height_m': height.copy(),
                   'ocean_mask': ocean, 'owner_domain_id': owner,
                   'receiver': _steepest_receivers(height, ocean, []).reshape(height.shape),
                   'domains': [{'domain_id': 0, 'kind': 'coastal',
                                'terminal_indices': np.flatnonzero(ocean).tolist(),
                                'lake_terminal_index': None}],
                   'origin_xz_m': [0., 0.], 'spacing_m': 1.,
                   'config': {'maximum_raise_m': 10.}, 'budget': {}}
        product['identity_sha256'] = _identity(product)
        delta = np.zeros(height.shape)
        delta[2, 4] = -1.1
        with self.assertRaisesRegex(PlanningError, 'terminal catchment ownership'):
            edit_domain_height(product, 0, delta)


if __name__ == '__main__':
    unittest.main()
