"""Consolidated tests.test_tectonic implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataclasses import replace as _i13_replace
import unittest as _i13_unittest
from unittest.mock import patch as _i13_patch
import numpy as _i13_np
from terrain_pipeline import tectonic as _i13_core
from terrain_pipeline.tectonic import CrustState as _i13_CrustState
from terrain_pipeline.tectonic import TectonicConfig as _i13_TectonicConfig
from terrain_pipeline.tectonic import evolve as _i13_evolve
from terrain_pipeline.tectonic import initialize as _i13_initialize
from terrain_pipeline.tectonic import surface_fields as _i13_surface_fields
from dataclasses import replace as _i14_replace
import hashlib as _i14_hashlib
import importlib as _i14_importlib
from pathlib import Path as _i14_Path
import unittest as _i14_unittest
import numpy as _i14_np
from terrain_pipeline.tectonic import TectonicConfig as _i14_TectonicConfig
from terrain_pipeline.tectonic import initialize as _i14_initialize
from terrain_pipeline.tectonic import evolve as _i14_evolve
from terrain_pipeline.tectonic import components as _i14_components
from terrain_pipeline.tectonic import geometry_metrics as _i14_geometry_metrics
from terrain_pipeline.tectonic import voronoi_complexity as _i14_voronoi_complexity
from terrain_pipeline.tectonic import freeze as _i14_freeze
from terrain_pipeline.tectonic import load_product as _i14_load_product
from terrain_pipeline.tectonic import plan as _i14_plan
import contextlib as _i15_contextlib
from dataclasses import replace as _i15_replace
import io as _i15_io
import json as _i15_json
from pathlib import Path as _i15_Path
import tempfile as _i15_tempfile
import unittest as _i15_unittest
from unittest.mock import patch as _i15_patch
import numpy as _i15_np
from terrain_pipeline.tectonic import TectonicConfig as _i15_TectonicConfig
from terrain_pipeline.tectonic import evolve as _i15_evolve
from terrain_pipeline.tectonic import connected_ocean as _i15_connected_ocean
from terrain_pipeline.tectonic import freeze as _i15_freeze
from terrain_pipeline.tectonic import load_product as _i15_load_product
from terrain_pipeline.tectonic import plan as _i15_plan
from terrain_pipeline.tectonic import prepare_frozen_product as _i15_prepare
from terrain_pipeline.tectonic import save_product as _i15_save_product
from tools.prepare_tectonic import main as _i15_main
import unittest as _i16_unittest
import numpy as _i16_np
from terrain_pipeline.tectonic import periodic_shape_distance as _i16_periodic_shape_distance
from terrain_pipeline.tectonic import shape_parameters as _i16_shape_parameters
import json as _i17_json
from pathlib import Path as _i17_Path
import shutil as _i17_shutil
import subprocess as _i17_subprocess
import sys as _i17_sys
import tempfile as _i17_tempfile
import numpy as _i17_np
import pytest as _i17_pytest
from diffusion.paths import ROOT as _i17_ROOT
from diffusion.physical_config import PhysicalGenerationConfig as _i17_PhysicalGenerationConfig
from diffusion.plate_td_conditioning import WORLD_SEED as _i17_WORLD_SEED
from diffusion.world_layout_backend import BUDGETS as _i17_BUDGETS
from terrain_pipeline import tectonic as _i17_td
from terrain_pipeline.coastal_terrain import relief as _i17_relief
from terrain_pipeline.coastal_terrain import coastal_support as _i17_coastal_support
from terrain_pipeline.coastal_terrain import compose as _i17_compose
from terrain_pipeline.tectonic import TectonicConfig as _i17_TectonicConfig
from terrain_pipeline.tectonic import evolve as _i17_evolve
from terrain_pipeline.tectonic import freeze as _i17_freeze
from terrain_pipeline.tectonic import save_product as _i17_save_product
import subprocess as _i18_subprocess
import sys as _i18_sys
import tempfile as _i18_tempfile
import unittest as _i18_unittest
from unittest.mock import patch as _i18_patch
from pathlib import Path as _i18_Path
import numpy as _i18_np
from diffusion.physical_config import PhysicalGenerationConfig as _i18_PhysicalGenerationConfig
from diffusion.plate_td_conditioning import WORLD_SEED as _i18_WORLD_SEED
from diffusion.plate_td_conditioning import make_plate_factory as _i18_make_plate_factory
from terrain_pipeline.tectonic import TectonicConfig as _i18_TectonicConfig
from terrain_pipeline.tectonic import evolve as _i18_evolve
from terrain_pipeline.tectonic import freeze as _i18_freeze
from terrain_pipeline.tectonic import save_product as _i18_save_product
from terrain_pipeline.tectonic import prepare_plate_source as _i18_prepare
from terrain_pipeline.tectonic import read_plate_source as _i18_read_product

CATEGORY = 'B'

# Source: tests.test_tectonic_evolution
def fixture(kind='continental', velocities=((2500.0, 0.0), (-2500.0, 0.0))):
    config = _i13_TectonicConfig(shape=(8, 16), cell_size_m=10000.0, plate_count=2, steps=1)
    coverage = _i13_np.zeros((2, 8, 16))
    coverage[0, :, :8] = 1
    coverage[1, :, 8:] = 1
    continental = coverage * 35000
    oceanic = _i13_np.zeros_like(coverage)
    if kind == 'mixed':
        continental[0] = 0
        oceanic[0] = coverage[0] * 7000
    state = _i13_CrustState(coverage, continental, oceanic, _i13_np.array(((40000.0, 40000.0), (120000.0, 40000.0))), _i13_np.array(velocities, dtype=float))
    return (config, state)

# Source: tests.test_tectonic_evolution
class TectonicEvolutionTests(_i13_unittest.TestCase):

    def assert_balanced(self, result):
        for budget in result.budgets:
            for material in ('continental', 'oceanic'):
                scale = max(1.0, budget[f'initial_{material}_m3'], budget[f'final_{material}_m3'])
                self.assertLessEqual(abs(budget[f'{material}_balance_residual_m3']), scale * 1e-12)
                self.assertLessEqual(abs(budget[f'advection_{material}_residual_m3']), scale * 1e-12)

    def test_zero_motion_preserves_every_field(self):
        config, state = fixture(velocities=((0, 0), (0, 0)))
        result = _i13_evolve(_i13_replace(config, steps=4), state)
        _i13_np.testing.assert_array_equal(result.final.continental_m, state.continental_m)
        _i13_np.testing.assert_array_equal(result.final.plate_coverage, state.plate_coverage)
        _i13_np.testing.assert_array_equal(result.elevation_m, result.initial_elevation_m)
        self.assertTrue(all((b['rift_oceanic_added_m3'] == b['subducted_oceanic_m3'] == 0 for b in result.budgets)))

    def test_common_integer_translation_moves_material_without_collision(self):
        config, state = fixture('mixed', velocities=((10000, 0), (10000, 0)))
        result = _i13_evolve(_i13_replace(config, steps=3), state)
        _i13_np.testing.assert_array_equal(result.final.continental_m, _i13_np.roll(state.continental_m, 3, axis=2))
        _i13_np.testing.assert_array_equal(result.final.oceanic_m, _i13_np.roll(state.oceanic_m, 3, axis=2))
        _i13_np.testing.assert_array_equal(result.elevation_m, _i13_np.roll(result.initial_elevation_m, 3, axis=1))
        self.assertTrue(all((b['sutured_continental_m3'] == b['subducted_oceanic_m3'] == b['rift_oceanic_added_m3'] == 0 for b in result.budgets)))
        self.assert_balanced(result)

    def test_fractional_common_translation_only_diffuses(self):
        config, state = fixture('mixed', velocities=((2500, 1000), (2500, 1000)))
        result = _i13_evolve(_i13_replace(config, steps=5), state)
        self.assertTrue(all((b['sutured_continental_m3'] == b['subducted_oceanic_m3'] == b['rift_oceanic_added_m3'] == 0 for b in result.budgets)))
        self.assertGreater(result.budgets[0]['advection_continental_l2_loss_m4'], 0)
        self.assertLessEqual(result.crust_thickness_m.max(), 35000)
        self.assert_balanced(result)

    def test_interior_crust_embryo_moves_without_any_plate_boundary(self):
        config = _i13_TectonicConfig(shape=(8, 16), plate_count=1, steps=2, origin_x_m=-80000, origin_z_m=-40000)
        coverage = _i13_np.ones((1, 8, 16))
        continental = _i13_np.zeros_like(coverage)
        continental[0, 2:5, 4:7] = 35000
        oceanic = _i13_np.where(continental > 0, 0.0, 7000.0)
        state = _i13_CrustState(coverage, continental, oceanic, _i13_np.array(((-40000.0, 0.0),)), _i13_np.array(((10000.0, 0.0),)))
        result = _i13_evolve(config, state)
        _i13_np.testing.assert_array_equal(result.final.continental_m, _i13_np.roll(continental, 2, axis=2))
        _i13_np.testing.assert_array_equal(result.final.oceanic_m, _i13_np.roll(oceanic, 2, axis=2))
        self.assertEqual(result.budgets[0]['convergent_faces'], 0)
        self.assertGreater(result.budgets[0]['advected_continental_m3'], 0)
        self.assert_balanced(result)

    def test_continental_convergence_thickens_and_sutures_at_contact(self):
        config, state = fixture()
        result = _i13_evolve(config, state)
        self.assertGreater(result.final.continental_m.sum(axis=0)[:, 7:9].max(), 35000)
        self.assertGreater(result.elevation_m[:, 7:9].max(), result.initial_elevation_m.max())
        self.assertGreater(result.budgets[0]['sutured_continental_m3'], 0)
        self.assertEqual(result.budgets[0]['subducted_oceanic_m3'], 0)
        self.assert_balanced(result)

    def test_ocean_continent_convergence_removes_ocean_at_contact(self):
        config, state = fixture('mixed')
        result = _i13_evolve(config, state)
        self.assertGreater(result.budgets[0]['subducted_oceanic_m3'], 0)
        self.assertLess(result.final.oceanic_m[:, :, 7:9].sum(), state.oceanic_m[:, :, 7:9].sum())
        self.assert_balanced(result)
        disabled = _i13_evolve(_i13_replace(config, subduction_fraction=0), state)
        self.assertEqual(disabled.budgets[0]['subducted_oceanic_m3'], 0)
        self.assert_balanced(disabled)

    def test_rifting_separates_continents_and_fills_gap_with_ocean(self):
        config, state = fixture(velocities=((-2500, 0), (2500, 0)))
        result = _i13_evolve(config, state)
        self.assertLess(result.final.continental_m.sum(axis=0)[:, 7:9].max(), 35000)
        self.assertGreater(result.final.oceanic_m[:, :, 7:9].sum(), 0)
        self.assertGreater(result.budgets[0]['rift_oceanic_added_m3'], 0)
        disabled = _i13_evolve(_i13_replace(config, rift_fraction=0), state)
        self.assertEqual(disabled.budgets[0]['rift_oceanic_added_m3'], 0)
        self.assert_balanced(result)

    def test_transform_only_slides_material(self):
        config, state = fixture('mixed', velocities=((0, 2500), (0, -2500)))
        result = _i13_evolve(config, state)
        self.assertGreater(result.budgets[0]['transform_faces'], 0)
        self.assertEqual(result.budgets[0]['convergent_faces'], 0)
        self.assertEqual(result.budgets[0]['subducted_oceanic_m3'], 0)
        self.assertEqual(result.budgets[0]['rift_oceanic_added_m3'], 0)
        self.assert_balanced(result)

    def test_aggregated_initialization_is_periodic_and_crust_is_independent(self):
        from terrain_pipeline.tectonic import geometry_metrics
        config = _i13_TectonicConfig(shape=(24, 32), plate_count=5, steps=3)
        state = _i13_initialize(config)
        metrics = geometry_metrics(state.plate_coverage.argmax(0), config.cell_size_m)
        self.assertEqual(metrics['periodic_components_per_plate'], [1] * config.plate_count)
        self.assertGreaterEqual(min(metrics['plate_area_cells']), config.min_plate_cells)
        self.assertGreater(state.formation['microcell_count'], config.plate_count * 8)
        self.assertGreater(sum(state.formation['continuous_concave_vertices_per_plate']), 0)
        mixed = (state.continental_m.sum(axis=(1, 2)) > 0) & (state.oceanic_m.sum(axis=(1, 2)) > 0)
        self.assertTrue(mixed.any())
        self.assertGreater(_i13_np.count_nonzero(state.continental_m.sum(axis=(1, 2))), 1)
        first, second = (_i13_evolve(config), _i13_evolve(config))
        _i13_np.testing.assert_array_equal(first.final.continental_m, second.final.continental_m)
        _i13_np.testing.assert_array_equal(first.elevation_m, second.elevation_m)
        self.assertEqual(first.budgets, second.budgets)
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(len(set(first.metadata['purpose_seeds'].values())), 3)
        self.assert_balanced(first)

    def test_input_is_unchanged_and_snapshots_are_independent(self):
        config, state = fixture()
        before = state.continental_m.copy()
        result = _i13_evolve(config, state)
        _i13_np.testing.assert_array_equal(state.continental_m, before)
        result.final.continental_m[:] = 0
        _i13_np.testing.assert_array_equal(result.initial.continental_m, before)
        _i13_np.testing.assert_array_equal(state.continental_m, before)

    def test_surface_is_buoyancy_from_material_not_plate_identity(self):
        _, state = fixture('mixed')
        fields = _i13_surface_fields(state)
        self.assertAlmostEqual(fields['elevation_m'][0, 0], 7000 * (1 - 3000 / 3300) - 4500)
        self.assertAlmostEqual(fields['elevation_m'][0, 10], 35000 * (1 - 2800 / 3300) - 4500)
        state.plate_coverage = state.plate_coverage[::-1]
        _i13_np.testing.assert_array_equal(_i13_surface_fields(state)['elevation_m'], fields['elevation_m'])

    def test_default_initial_and_final_surfaces_have_land_and_ocean(self):
        for config in (_i13_TectonicConfig(), _i13_TectonicConfig(shape=(64, 64), steps=20)):
            with self.subTest(shape=config.shape):
                result = _i13_evolve(config)
                self.assertEqual(result.metadata['elevation_offset_m'], -4500)
                for elevation in (result.initial_elevation_m, result.elevation_m):
                    land = _i13_np.mean(elevation > 0)
                    ocean = _i13_np.mean(elevation < 0)
                    self.assertGreater(land, 0.05)
                    self.assertGreater(ocean, 0.2)
                    self.assertTrue(_i13_np.isfinite(elevation).all())
                self.assert_balanced(result)

    def test_cfl_boundary_uses_nonnegative_transport_weights(self):
        config, state = fixture('mixed', velocities=((9000, 1000), (9000, 1000)))
        result = _i13_evolve(_i13_replace(config, steps=3), state)
        self.assertTrue((result.final.plate_coverage >= 0).all())
        self.assertTrue((result.final.continental_m >= 0).all())
        self.assertTrue((result.final.oceanic_m >= 0).all())
        self.assert_balanced(result)

    def test_cfl_above_one_is_rejected_at_input_without_mutation(self):
        for excess in (_i13_np.spacing(1.0), 5e-15, 1e-14):
            config, state = fixture('mixed', velocities=((1 + excess, 0), (0, 0)))
            config = _i13_replace(config, cell_size_m=1)
            state.plate_seeds_m /= 10000
            before = state.continental_m.copy()
            with self.subTest(excess=excess), self.assertRaisesRegex(ValueError, 'CFL'):
                _i13_evolve(config, state)
            _i13_np.testing.assert_array_equal(state.continental_m, before)

    def test_runtime_rejects_injected_transport_material_creation(self):
        original_advect = _i13_core._advect
        for material, call_index in (('continental', 5), ('oceanic', 6)):
            config, state = fixture('mixed', velocities=((0, 0), (0, 0)))
            before = getattr(state, f'{material}_m').copy()
            calls = 0

            def corrupt_transport(field, displacement):
                nonlocal calls
                calls += 1
                transported = original_advect(field, displacement)
                if calls == call_index:
                    transported[0, 0, 0] += 1
                return transported
            with self.subTest(material=material), _i13_patch.object(_i13_core, '_advect', side_effect=corrupt_transport):
                with self.assertRaisesRegex(ValueError, f'step 2: {material} .*budget exceeded'):
                    _i13_evolve(_i13_replace(config, steps=3), state)
            self.assertEqual(calls, 6)
            _i13_np.testing.assert_array_equal(getattr(state, f'{material}_m'), before)

    def test_runtime_checks_actual_state_even_if_reported_budget_is_balanced(self):
        original_step = _i13_core._step
        for material in ('continental', 'oceanic'):
            config, state = fixture('mixed', velocities=((0, 0), (0, 0)))

            def corrupt_state(config, current):
                after, budget = original_step(config, current)
                getattr(after, f'{material}_m')[0, 0, 0] += 1
                return (after, budget)
            with self.subTest(material=material), _i13_patch.object(_i13_core, '_step', side_effect=corrupt_state):
                with self.assertRaisesRegex(ValueError, f'{material} material budget exceeded'):
                    _i13_evolve(config, state)

    def test_tiny_inventory_absolute_tolerance_is_separate_for_each_material(self):
        original_advect = _i13_core._advect
        for material, call_index in (('continental', 2), ('oceanic', 3)):
            for injected_m3, rejected in ((1e-13, False), (1e-11, True)):
                config, state = fixture('mixed', velocities=((0, 0), (0, 0)))
                config = _i13_replace(config, cell_size_m=1)
                state.plate_seeds_m /= 10000
                getattr(state, f'{material}_m')[:] *= 1e-20
                calls = 0

                def corrupt_transport(field, displacement):
                    nonlocal calls
                    calls += 1
                    transported = original_advect(field, displacement)
                    if calls == call_index:
                        transported[0, 0, 0] += injected_m3
                    return transported
                with self.subTest(material=material, injected_m3=injected_m3):
                    with _i13_patch.object(_i13_core, '_advect', side_effect=corrupt_transport):
                        if rejected:
                            with self.assertRaisesRegex(ValueError, f'{material} .*budget exceeded'):
                                _i13_evolve(config, state)
                        else:
                            _i13_evolve(config, state)

    def test_runtime_rejects_nonfinite_budget(self):
        config, state = fixture()
        original_step = _i13_core._step
        for invalid in (float('nan'), float('inf')):

            def corrupt_budget(config, current):
                after, budget = original_step(config, current)
                budget['continental_balance_residual_m3'] = invalid
                return (after, budget)
            with self.subTest(invalid=invalid), _i13_patch.object(_i13_core, '_step', side_effect=corrupt_budget):
                with self.assertRaisesRegex(ValueError, 'nonfinite evolution budget'):
                    _i13_evolve(config, state)

    def test_invalid_input_fails_without_mutation(self):
        config, state = fixture()
        for change in ({'time_step': float('nan')}, {'cell_size_m': 0}, {'steps': -1}, {'plate_count': 0}, {'rift_fraction': 2}, {'shape': (8.5, 16)}, {'max_speed_m_per_step': -1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                _i13_evolve(_i13_replace(config, **change), state)
        for field, index, value in (('continental_m', (0, 0, 0), -1), ('oceanic_m', (0, 0, 0), _i13_np.nan), ('plate_coverage', (0, 0, 0), 0.5), ('plate_seeds_m', (0, 0), -1), ('velocities_m_per_step', (0, 0), _i13_np.inf), ('velocities_m_per_step', (0, 0), 20000)):
            config, state = fixture()
            getattr(state, field)[index] = value
            before = state.continental_m.copy()
            with self.subTest(field=field), self.assertRaises(ValueError):
                _i13_evolve(config, state)
            _i13_np.testing.assert_array_equal(state.continental_m, before)

# Source: tests.test_tectonic_formation
ROOT = _i14_Path(__file__).resolve().parents[1]

# Source: tests.test_tectonic_formation
class FormationTests(_i14_unittest.TestCase):

    def test_mixed_reference_preserves_cores_and_determinism(self):
        config = _i14_TectonicConfig(shape=(128, 160), steps=0, origin_x_m=-800000.0, origin_z_m=-640000.0)
        state = _i14_initialize(config)
        geometry = state.formation
        self.assertGreater(geometry['continuous_boundary_segments'], 24)
        self.assertEqual({p['family'] for p in geometry['growth_shapes']}, {'circle', 'ellipse', 'triangle'})
        self.assertEqual(geometry['periodic_components_per_plate'], [1] * 8)
        ids = state.plate_coverage.argmax(0)
        for plate, anchor in enumerate(state.plate_seeds_m):
            x, z = _i14_np.floor((anchor - [config.origin_x_m, config.origin_z_m]) / config.cell_size_m).astype(int)
            self.assertEqual(ids[z, x], plate)
        other = _i14_initialize(config)
        _i14_np.testing.assert_array_equal(other.plate_coverage, state.plate_coverage)
        self.assertEqual(other.formation, geometry)

    def test_v2_cold_read_does_not_call_formation_or_evolution(self):
        from unittest.mock import patch
        path = ROOT / '.scratch/plate-formation-coast-20261101/formation-run-v2/product.npz'
        if not path.exists():
            self.skipTest('local immutable v2 product unavailable')
        with patch('terrain_pipeline.tectonic.initialize', side_effect=AssertionError), patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError), patch('terrain_pipeline.tectonic.form_plates', side_effect=AssertionError):
            product = _i14_load_product(path)
        self.assertEqual(product.manifest['algorithm'], 'kinematic-crust-2')

    def test_v3_cold_read_preserves_saved_product(self):
        from unittest.mock import patch
        path = ROOT / '.scratch/plate-formation-coast-20261101/compact-run-v3-final/product.npz'
        if not path.exists():
            self.skipTest('local immutable v3 product unavailable')
        digest = _i14_hashlib.sha256(path.read_bytes()).hexdigest()
        with patch('terrain_pipeline.tectonic.initialize', side_effect=AssertionError), patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError), patch('terrain_pipeline.tectonic.form_plates', side_effect=AssertionError):
            product = _i14_load_product(path)
        self.assertEqual(product.manifest['algorithm'], 'kinematic-crust-3')
        self.assertEqual(digest, _i14_hashlib.sha256(path.read_bytes()).hexdigest())

    def test_full_coverage_connected_and_unequal_with_true_concave_geometry(self):
        config = _i14_TectonicConfig(steps=0)
        state = _i14_initialize(config)
        geometry = state.formation
        ids = state.plate_coverage.argmax(0)
        _i14_np.testing.assert_array_equal(state.plate_coverage.sum(0), 1)
        self.assertEqual(geometry['periodic_components_per_plate'], [1] * config.plate_count)
        self.assertGreaterEqual(min(geometry['plate_area_cells']), config.min_plate_cells)
        self.assertGreater(max(geometry['plate_area_cells']), min(geometry['plate_area_cells']))
        self.assertGreater(geometry['continuous_boundary_segments'], config.plate_count * 6)
        self.assertGreater(sum(geometry['continuous_concave_vertices_per_plate']), config.plate_count)
        nodes = _i14_np.asarray(geometry['microfragment_id_zx'])
        owners = _i14_np.asarray(geometry['microfragment_plate'])
        _i14_np.testing.assert_array_equal(owners[nodes], ids)
        self.assertEqual(int(_i14_np.bincount(nodes.ravel()).sum()), _i14_np.prod(config.shape))
        product = _i14_freeze(config, _i14_evolve(config, state))
        self.assertEqual(product.manifest['core_metadata']['formation'], geometry)

    def test_periodic_microfragments_are_split_and_never_dropped(self):
        labels = _i14_np.array([[0, 1, 1, 0], [1, 0, 1, 1], [1, 1, 1, 1]])
        fragments, sources = _i14_components(labels)
        self.assertEqual(fragments[0, 0], fragments[0, -1])
        self.assertNotEqual(fragments[0, 0], fragments[1, 1])
        _i14_np.testing.assert_array_equal(_i14_np.asarray(sources)[fragments], labels)
        self.assertEqual(sources.count(0), 2)

    def test_infeasible_minimum_fails_without_reseeding(self):
        for config in (_i14_TectonicConfig(shape=(4, 4), plate_count=5), _i14_TectonicConfig(min_plate_cells=0), _i14_TectonicConfig(microcells_per_plate=1)):
            with self.subTest(config=config), self.assertRaises(ValueError):
                _i14_initialize(config)
        state = _i14_initialize(_i14_TectonicConfig(shape=(8, 8), plate_count=8, min_plate_cells=1))
        self.assertEqual(len(_i14_np.unique(state.plate_coverage.argmax(0))), 8)

    def test_resolution_and_budget_include_microcells(self):
        config = _i14_TectonicConfig(shape=(128, 128), steps=0)
        sparse = _i14_plan(_i14_replace(config, microcells_per_plate=8))
        dense = _i14_plan(config)
        self.assertGreater(dense['formation_distance_cell_visits'], sparse['formation_distance_cell_visits'])
        self.assertGreater(dense['estimated_peak_memory_bytes'], sparse['estimated_peak_memory_bytes'])
        self.assertFalse(_i14_plan(config, max_cell_plate_steps=sparse['cell_plate_steps'])['allowed'])

    def test_geometry_supports_noninteger_metric_spacing(self):
        config = _i14_TectonicConfig(shape=(8, 12), plate_count=3, steps=0, cell_size_m=0.1, max_speed_m_per_step=0)
        product = _i14_freeze(config, _i14_evolve(config))
        self.assertEqual(product.manifest['core_metadata']['formation']['minimum_resolved_plate_area_m2'], 4 * 0.1 ** 2)

    def test_unchanged_embryo_velocity_and_old_product_cold_read(self):
        path = ROOT / '.scratch/plate-formation-coast-20261101/baseline/tectonic_evolution_v1.py'
        if not path.exists():
            self.skipTest('local immutable baseline unavailable')
        spec = _i14_importlib.util.spec_from_file_location('formation_baseline', path)
        old = _i14_importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        config = _i14_TectonicConfig(shape=(32, 48), plate_count=5, steps=0)
        before = old.initialize(old.TectonicConfig(shape=config.shape, plate_count=5, steps=0))
        after = _i14_initialize(config)
        _i14_np.testing.assert_array_equal(before.continental_m.sum(0), after.continental_m.sum(0))
        _i14_np.testing.assert_array_equal(before.oceanic_m.sum(0), after.oceanic_m.sum(0))
        _i14_np.testing.assert_array_equal(before.velocities_m_per_step, after.velocities_m_per_step)
        frozen = ROOT / '.scratch/world-generation-sequence-20261101/macro-run-v2/product.npz'
        if frozen.exists():
            digest = _i14_hashlib.sha256(frozen.read_bytes()).hexdigest()
            product = _i14_load_product(frozen)
            self.assertEqual(product.manifest['schema'], 'tectonic-frozen-product-v1')
            self.assertEqual(digest, _i14_hashlib.sha256(frozen.read_bytes()).hexdigest())

    def test_geometry_corruption_is_rejected_even_with_new_identity(self):
        from terrain_pipeline.tectonic import FrozenTectonicProduct
        from terrain_pipeline.tectonic import _digest
        from terrain_pipeline.tectonic import _json
        config = _i14_TectonicConfig(shape=(16, 24), plate_count=4, steps=0)
        product = _i14_freeze(config, _i14_evolve(config))
        manifest = product.manifest
        manifest['core_metadata']['formation']['microfragment_plate'][0] = 99
        manifest.pop('identity')
        manifest['identity'] = _digest(_json(manifest).encode())
        with self.assertRaisesRegex(ValueError, 'geometry'):
            FrozenTectonicProduct(manifest, dict(product.arrays))

    def test_core_cost_and_algorithm_corruption_are_rejected(self):
        from terrain_pipeline.tectonic import FrozenTectonicProduct
        from terrain_pipeline.tectonic import _digest
        from terrain_pipeline.tectonic import _json
        config = _i14_TectonicConfig(shape=(16, 24), plate_count=4, steps=0)
        product = _i14_freeze(config, _i14_evolve(config))
        for corruption in ('cost', 'core', 'algorithm', 'type', 'shape', 'shape_seed'):
            with self.subTest(corruption=corruption):
                manifest = product.manifest
                if corruption == 'cost':
                    manifest['core_metadata']['formation']['growth_cost']['path_weight'] = 0.8
                elif corruption == 'shape':
                    manifest['core_metadata']['formation']['growth_shapes'][0]['angle_rad'] += 0.1
                elif corruption == 'shape_seed':
                    manifest['core_metadata']['formation']['shape_purpose_seed'] += 1
                elif corruption == 'core':
                    manifest['core_metadata']['formation']['core_microfragment_per_plate'].reverse()
                elif corruption == 'algorithm':
                    manifest['algorithm'] = 'kinematic-crust-2'
                    manifest['core_metadata']['algorithm_version'] = 'kinematic-crust-2'
                else:
                    manifest['core_metadata']['formation'] = 'invalid'
                manifest.pop('identity')
                manifest['identity'] = _digest(_json(manifest).encode())
                with self.assertRaises(ValueError):
                    FrozenTectonicProduct(manifest, dict(product.arrays))

# Source: tests.test_tectonic_product
class TectonicProductTests(_i15_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = _i15_TectonicConfig(shape=(12, 16), plate_count=4, steps=3, origin_x_m=-80000.0, origin_z_m=30000.0)
        cls.product = _i15_freeze(cls.config, _i15_evolve(cls.config))

    def test_deterministic_identity_and_cold_read(self):
        other = _i15_freeze(self.config, _i15_evolve(self.config))
        self.assertEqual(other.identity, self.product.identity)
        with _i15_tempfile.TemporaryDirectory() as directory:
            path = _i15_Path(directory) / 'product.npz'
            _i15_save_product(self.product, path)
            loaded = _i15_load_product(path, expected_identity=self.product.identity)
            for key in self.product.arrays:
                _i15_np.testing.assert_array_equal(loaded.arrays[key], self.product.arrays[key])
                with self.assertRaises(ValueError):
                    loaded.arrays[key].setflags(write=True)
            with self.assertRaises(FileExistsError):
                _i15_save_product(self.product, path)
            with self.assertRaises(ValueError):
                _i15_load_product(path, expected_identity='wrong')

    def test_runtime_and_machine_paths_do_not_change_identity(self):
        result = _i15_evolve(self.config)
        result.metadata['runtime_seconds'] = 1234.0
        result.metadata['machine_path'] = 'D:/different-machine/output'
        self.assertEqual(_i15_freeze(self.config, result).identity, self.product.identity)

    def test_cli_generate_and_diagnostic_images(self):
        from PIL import Image
        root = _i15_Path(__file__).resolve().parents[1]
        with _i15_tempfile.TemporaryDirectory(prefix='.tectonic-test-', dir=root) as directory:
            output = _i15_Path(directory) / 'published'
            with _i15_contextlib.redirect_stdout(_i15_io.StringIO()):
                report = _i15_main(['generate', '--shape', '12', '16', '--plates', '4', '--steps', '3', '--output', str(output)])
            loaded = _i15_load_product(output / 'product.npz', expected_identity=report['identity'])
            self.assertEqual(loaded.manifest['config']['world_seed'], 20261020)
            for name in ('initial-macro.png', 'final-macro.png', 'process-budgets.png'):
                with Image.open(output / name) as image:
                    self.assertGreater(image.width, 1000)
            self.assertIsNone(_i15_json.loads((output / 'diagnostics.json').read_text())['td_binding'])
            with self.assertRaises(FileExistsError):
                _i15_main(['generate', '--output', str(output)])

    def test_sampling_absolute_centres_reverse_overlap_and_seams(self):
        c = self.config
        x = c.origin_x_m + (_i15_np.arange(16) + 0.5) * c.cell_size_m
        z = c.origin_z_m + (_i15_np.arange(12) + 0.5) * c.cell_size_m
        all_samples = self.product.sample(x[None, :], z[:, None])
        for name, values in all_samples.items():
            _i15_np.testing.assert_array_equal(values, self.product.arrays['final/' + name])
            reverse = self.product.sample(x[::-1][None, :], z[::-1, None])[name]
            _i15_np.testing.assert_array_equal(reverse[::-1, ::-1], values)
            overlap = self.product.sample(x[4:10][None, :], z[3:8, None])[name]
            _i15_np.testing.assert_array_equal(overlap, values[3:8, 4:10])
        left = self.product.sample(c.origin_x_m, z)
        right = self.product.sample(c.origin_x_m + 16 * c.cell_size_m, z)
        for name in left:
            _i15_np.testing.assert_array_equal(left[name], right[name])
        for xbad in (c.origin_x_m - 1, c.origin_x_m + 16 * c.cell_size_m):
            with self.assertRaises(ValueError):
                self.product.sample(xbad, z, outside='reject')
        with self.assertRaises(ValueError):
            self.product.sample(_i15_np.nan, 0)

    def test_interpolation_and_read_only_queries(self):
        c = self.config
        x = c.origin_x_m + c.cell_size_m
        z = c.origin_z_m + c.cell_size_m
        with _i15_tempfile.TemporaryDirectory() as directory:
            path = _i15_Path(directory) / 'product.npz'
            _i15_save_product(self.product, path)
            before = path.read_bytes()
            with _i15_patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError('must not evolve')):
                loaded = _i15_load_product(path)
                values = loaded.sample(x, z)
            self.assertEqual(before, path.read_bytes())
            self.assertAlmostEqual(float(values['elevation_m']), self.product.arrays['final/elevation_m'][:2, :2].mean())
            self.assertEqual(int(values['plate_id']), int(self.product.arrays['final/plate_id'][1, 1]))

    def test_corrupt_field_schema_hash_and_missing_data_rejected(self):
        with _i15_tempfile.TemporaryDirectory() as directory:
            path = _i15_Path(directory) / 'bad.npz'
            for corruption in ('field', 'schema', 'identity', 'missing', 'dtype', 'nan'):
                arrays = {k: v.copy() for k, v in self.product.arrays.items()}
                manifest = self.product.manifest
                if corruption == 'field':
                    arrays['final/elevation_m'][0, 0] += 1
                elif corruption == 'schema':
                    manifest['schema'] = 'wrong'
                elif corruption == 'identity':
                    manifest['identity'] = 'wrong'
                elif corruption == 'missing':
                    arrays.pop('final/plate_id')
                elif corruption == 'dtype':
                    arrays['final/plate_id'] = arrays['final/plate_id'].astype(float)
                else:
                    arrays['final/elevation_m'][0, 0] = _i15_np.nan
                _i15_np.savez(path, manifest_json=_i15_np.array(_i15_json.dumps(manifest)), **arrays)
                with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                    _i15_load_product(path)

    def test_connected_ocean_excludes_enclosed_depression_and_wraps(self):
        elevation = _i15_np.ones((7, 7))
        elevation[0, 0] = -10
        elevation[0, -1] = -1
        elevation[3, 3] = -2
        ocean, seed = _i15_connected_ocean(elevation)
        self.assertEqual(seed, [0, 0])
        self.assertTrue(ocean[0, -1])
        self.assertFalse(ocean[3, 3])
        self.assertEqual(int(ocean.sum()), 2)
        self.assertIsNone(_i15_connected_ocean(_i15_np.ones((2, 2)))[1])

    def test_budget_precedes_evolution_and_cli_plan_is_read_only(self):
        with _i15_tempfile.TemporaryDirectory() as directory:
            path = _i15_Path(directory) / 'never.npz'
            with _i15_patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError('must not evolve')):
                with self.assertRaisesRegex(ValueError, 'budget'):
                    _i15_prepare(self.config, path, max_memory_bytes=1)
                self.assertFalse(path.exists())
                with _i15_contextlib.redirect_stdout(_i15_io.StringIO()):
                    report = _i15_main(['plan', '--shape', '12', '16', '--plates', '4', '--steps', '3', '--output', str(path)])
                self.assertTrue(report['allowed'])
                self.assertFalse(path.exists())
        self.assertFalse(_i15_plan(self.config, max_cell_plate_steps=1)['allowed'])
        with self.assertRaises(ValueError):
            _i15_plan(_i15_replace(self.config, world_seed=1))

    def test_failed_publication_leaves_no_product_or_temporary(self):
        with _i15_tempfile.TemporaryDirectory() as directory:
            path = _i15_Path(directory) / 'product.npz'
            with _i15_patch('terrain_pipeline.tectonic.load_product', side_effect=ValueError('cold read failed')):
                with self.assertRaises(ValueError):
                    _i15_save_product(self.product, path)
            self.assertEqual(list(_i15_Path(directory).iterdir()), [])

    def test_cli_failed_render_leaves_no_completed_directory(self):
        root = _i15_Path(__file__).resolve().parents[1]
        with _i15_tempfile.TemporaryDirectory(prefix='.tectonic-test-', dir=root) as directory:
            path = _i15_Path(directory) / 'failed'
            with _i15_patch('tools.prepare_tectonic.render_diagnostics', side_effect=RuntimeError('render failed')):
                with self.assertRaisesRegex(RuntimeError, 'render failed'):
                    _i15_main(['generate', '--shape', '12', '16', '--plates', '4', '--steps', '3', '--output', str(path)])
            self.assertEqual(list(_i15_Path(directory).iterdir()), [])

# Source: tests.test_tectonic_shapes
def parameters(family='ellipse', angle=0.0, aspect=4.0, scale=1.0):
    return dict(family=family, angle_rad=angle, aspect_ratio=aspect, scale_cells=scale)

# Source: tests.test_tectonic_shapes
class ShapeTests(_i16_unittest.TestCase):

    def test_circle_rotation_and_ellipse_direction(self):
        points = _i16_np.array([[12.0, 0.0], [0.0, 12.0], [3.0, -7.0]])
        circle = _i16_periodic_shape_distance(points, [100, 100], parameters('circle', aspect=1.0))
        _i16_np.testing.assert_array_equal(circle, _i16_periodic_shape_distance(points, [100, 100], parameters('circle', angle=1.7, aspect=1.0)))
        ellipse = _i16_periodic_shape_distance(points, [100, 100], parameters())
        self.assertLess(ellipse[0], ellipse[1])
        rotated = _i16_periodic_shape_distance(points, [100, 100], parameters(angle=_i16_np.pi / 2))
        _i16_np.testing.assert_allclose(ellipse[:2], rotated[:2][::-1])

    def test_triangle_tip_and_rotation_differ_from_symmetric_shapes(self):
        points = _i16_np.array([[10.0, 0.0], [-10.0, 0.0]])
        triangle = _i16_periodic_shape_distance(points, [100, 100], parameters('triangle', aspect=1.0))
        _i16_np.testing.assert_allclose(triangle, [10.0, 20.0])
        rotated = _i16_periodic_shape_distance(points, [100, 100], parameters('triangle', _i16_np.pi, 1.0))
        _i16_np.testing.assert_allclose(triangle, rotated[::-1])
        for family, aspect in (('circle', 1.0), ('ellipse', 4.0)):
            symmetric = _i16_periodic_shape_distance(points, [100, 100], parameters(family, aspect=aspect))
            self.assertEqual(symmetric[0], symmetric[1])

    def test_periodic_minimum_can_use_non_euclidean_nearest_image(self):
        for family in ('ellipse', 'triangle'):
            p = parameters(family, angle=0.7, aspect=6.0)
            period = _i16_np.array([40.0, 30.0])
            points = _i16_np.array([[19.0, -14.0], [-17.0, 13.0], [2.0, 8.0]])
            actual = _i16_periodic_shape_distance(points, period, p)
            reference = _i16_np.full(3, _i16_np.inf)
            nearest = None
            for ix in range(-20, 21):
                for iz in range(-20, 21):
                    q = points + period * (ix, iz)
                    u = (q[:, 0] * _i16_np.cos(0.7) + q[:, 1] * _i16_np.sin(0.7)) / _i16_np.sqrt(6)
                    v = (-q[:, 0] * _i16_np.sin(0.7) + q[:, 1] * _i16_np.cos(0.7)) * _i16_np.sqrt(6)
                    value = _i16_np.hypot(u, v) if family == 'ellipse' else _i16_np.maximum.reduce((u + _i16_np.sqrt(3) * v, -2 * u, u - _i16_np.sqrt(3) * v))
                    reference = _i16_np.minimum(reference, value)
                    if ix == iz == 0:
                        nearest = value
            _i16_np.testing.assert_allclose(actual, reference)
            self.assertTrue(_i16_np.any(actual < nearest - 1e-08))
            _i16_np.testing.assert_allclose(actual, _i16_periodic_shape_distance(points + period * [11, -9], period, p))

    def test_invalid_inputs_and_resource_budget(self):
        for p in (parameters(aspect=0), parameters(aspect=7), parameters(angle=_i16_np.nan), parameters(scale=0), parameters('unknown'), parameters(angle=1e+100)):
            with self.subTest(parameters=p), self.assertRaises(ValueError):
                _i16_periodic_shape_distance([[1, 2]], [100, 100], p)
        for period, point in (([0, 2], [1, 2]), ([2, _i16_np.inf], [1, 2]), ([2, 2], [_i16_np.nan, 2]), ([1e-08, 100], [0, 49])):
            with self.subTest(period=period), self.assertRaises(ValueError):
                _i16_periodic_shape_distance([point], period, parameters())
        self.assertEqual(_i16_shape_parameters(20261020, 8), _i16_shape_parameters(20261020, 8))

# Source: tests.test_plate_td_product_fixture
def model_fixture(directory):
    directory.mkdir()
    (directory / 'config.json').write_text(_i17_json.dumps({'native_resolution': 30, 'latent_compression': 8}), encoding='utf-8')
    (directory / 'unit-weights.bin').write_bytes(b'small unit fixture; never TD weights')
    files = {p.name: {'bytes': p.stat().st_size, 'sha256': _i17_td.digest(p)} for p in directory.iterdir()}
    (directory / 'manifest.json').write_text(_i17_json.dumps({'files': files}), encoding='utf-8')
    return _i17_PhysicalGenerationConfig(model_dir=str(directory.relative_to(_i17_ROOT)))

# Source: tests.test_plate_td_product_fixture
def fake_td(source, origin, side, config, *, expected_identity):
    identity, metadata = config.generation_identity()
    files = [_i17_ROOT / 'diffusion' / name for name in ('plate_td_backend.py', 'plate_td_conditioning.py', 'geographic_noise.py')]
    files += [_i17_ROOT / 'terrain_pipeline' / name for name in ('tectonic.py', 'coastal_terrain.py')]
    generation = {'record': {'source': str(_i17_Path(source).resolve()), 'plate_identity': expected_identity, 'seed': _i17_WORLD_SEED, 'origin': list(origin), 'side': side, 'config': config.record()}, 'physical_generation_identity': identity, 'physical_generation': metadata, 'source_sha256': {p.name: _i17_td.digest(p) for p in files}, 'coordinates': '30m cell centres; x east, z south; arrays [z,x]; sea datum 0m', 'boundary': 'finite reject; product bilinear interpolation wraps at edge', 'gpu_monitor': 'allocator', 'gpu_scope': 'PyTorch allocator only; excludes driver, non-PyTorch allocations and other processes', 'budgets': dict(_i17_BUDGETS, page_side_cells=side), 'wall_clock_s': 1.0, 'peak_child_rss_mib': 12.0, 'allocated_peak_mib': 0.0, 'reserved_peak_mib': 0.0}
    product = _i17_td.load_product(source, expected_identity=expected_identity)
    macro = _i17_td._macro(product, origin, side)
    x = origin[0] + _i17_np.arange(side)[None, :]
    z = origin[1] + _i17_np.arange(side)[:, None]
    raw = (macro + 10 * _i17_np.sin(x / 17.0) * _i17_np.cos(z / 23.0)).astype(_i17_np.float32)
    return (raw, _i17_np.zeros((5, side, side), _i17_np.float32), generation)

# Source: tests.test_plate_td_product_fixture
@_i17_pytest.fixture(scope='module')
def frozen():
    config = _i17_TectonicConfig(shape=(12, 16), plate_count=4, steps=3, origin_x_m=-80000.0, origin_z_m=-60000.0)
    return _i17_freeze(config, _i17_evolve(config))

# Source: tests.test_plate_td_product_fixture
@_i17_pytest.fixture
def portable(frozen, monkeypatch):
    with _i17_tempfile.TemporaryDirectory(dir=_i17_ROOT, prefix='.unit-plate-') as directory:
        directory = _i17_Path(directory)
        source = directory / 'source.npz'
        _i17_save_product(frozen, source)
        config = model_fixture(directory / 'model')
        monkeypatch.setattr('diffusion.plate_td_backend.generate', fake_td)
        yield (directory, source, config, frozen)

# Source: tests.test_plate_td_product_fixture
def prepare_fixture(portable, name, origin, side=513, coastal=True, strength=0.7):
    directory, source, config, frozen = portable
    output = directory / name
    _i17_td.prepare_plate_source(source, output, origin, side, config, compose_coast=coastal, expected_identity=frozen.identity, relief_strength=strength)
    return output

# Source: tests.test_plate_td_product_fixture
def locate(product, kind):
    for z in range(-1400, 1401, 100):
        for x in range(-2000, 2001, 100):
            origin = (x - 256, z - 256)
            xx = (origin[0] + _i17_np.arange(0, 513, 16))[None, :] * 30.0
            zz = (origin[1] + _i17_np.arange(0, 513, 16))[:, None] * 30.0
            sample = product.sample(xx, zz, outside='reject')
            elevation = sample['elevation_m']
            if kind == 'coast':
                core = elevation[13:20, 13:20]
                if core.min() < -10 and core.max() > 10 and sample['ocean_connected'][13:20, 13:20].any():
                    return origin
            elif kind == 'sea' and elevation.max() < -100 and sample['ocean_connected'].all():
                return origin
            elif kind == 'land' and elevation.min() > 100:
                return origin
    raise AssertionError('missing deterministic ' + kind + ' fixture')

# Source: tests.test_plate_td_product_fixture
def save_manifest(path, manifest):
    manifest['identity'] = _i17_td._identity({k: v for k, v in manifest.items() if k != 'identity'})
    (path / 'manifest.json').write_text(_i17_json.dumps(manifest), encoding='utf-8')

# Source: tests.test_plate_td_product_fixture
def test_cold_read_and_no_overwrite(portable):
    path = prepare_fixture(portable, 'raw', (-10, -10), 16, False, 0.0)
    manifest, arrays = _i17_td.read_plate_source(path)
    assert not arrays['raw_td'].flags.writeable
    code = "from terrain_pipeline.tectonic import read_plate_source; import sys; m,a=read_plate_source(sys.argv[1],sys.argv[2]); assert a['raw_td'].dtype.name=='float32'"
    _i17_subprocess.run([_i17_sys.executable, '-c', code, str(path), manifest['identity']], check=True)
    before = (path / 'manifest.json').read_bytes()
    with _i17_pytest.raises(FileExistsError):
        prepare_fixture(portable, 'raw', (-10, -10), 16, False, 0.0)
    assert before == (path / 'manifest.json').read_bytes()

# Source: tests.test_plate_td_product_fixture
def test_relocation_and_runtime_identity_stability(portable):
    directory, source, config, frozen = portable
    first = prepare_fixture(portable, 'first', (-10, -10), 16, False, 0.0)
    alternate = directory / 'relocated-source'
    alternate.mkdir()
    relocated = alternate / 'same.npz'
    _i17_shutil.copyfile(source, relocated)
    other_config = model_fixture(directory / 'other-model')

    def delayed(*args, **kwargs):
        raw, climate, generation = fake_td(*args, **kwargs)
        generation.update(wall_clock_s=99.0, peak_child_rss_mib=222.0, allocated_peak_mib=10.0, reserved_peak_mib=20.0)
        return (raw, climate, generation)
    with _i17_pytest.MonkeyPatch.context() as patch:
        patch.setattr('diffusion.plate_td_backend.generate', delayed)
        _i17_td.prepare_plate_source(relocated, directory / 'second', (-10, -10), 16, other_config, compose_coast=False, expected_identity=frozen.identity)
    a = _i17_td.read_plate_source(first)[0]
    b = _i17_td.read_plate_source(directory / 'second')[0]
    assert a['generation']['physical_generation_identity'] != b['generation']['physical_generation_identity']
    assert a['generation']['physical_generation']['conditioning_identity'] != b['generation']['physical_generation']['conditioning_identity']
    assert a['identity'] == b['identity']

# Source: tests.test_plate_td_product_fixture
@_i17_pytest.fixture
def coastal(portable):
    origin = locate(portable[3], 'coast')
    return (portable, prepare_fixture(portable, 'coast', origin))

# Source: tests.test_plate_td_product_fixture
def test_composed_relief_zero_baseline_and_shifted_shared_support(coastal):
    portable, path = coastal
    manifest, arrays = _i17_td.read_plate_source(path)
    origin = manifest['origin_native_xz']
    baseline_path = prepare_fixture(portable, 'zero', origin, strength=0.0)
    baseline_manifest, baseline = _i17_td.read_plate_source(baseline_path)
    macro = baseline['macro']
    anchor = tuple(_i17_np.asarray(baseline_manifest['anchor_bed_zx']) + 96)
    support = _i17_coastal_support(macro, anchors=[anchor])
    expected = _i17_compose(baseline['raw_td'], macro, support=support)
    _i17_np.testing.assert_array_equal(baseline['bed'], expected)
    assert not baseline['relief'].any()
    assert arrays['relief'].any()
    _i17_np.testing.assert_array_equal(arrays['bed'], (expected + arrays['relief']).astype(_i17_np.float32))
    shared = support[96:-96, 96:-96]
    world = ((origin[0] + 96) * 30.0, (origin[1] + 96) * 30.0)
    for z, x in ((110, 110), (125, 130), (110, 110)):
        window = _i17_np.s_[z:z + 70, x:x + 65]
        calculated = _i17_relief(expected[window], arrays['valid'][window], shared[window], (world[0] + x * 30.0, world[1] + z * 30.0), strength=0.7)
        assert calculated.any()
        _i17_np.testing.assert_array_equal(calculated, arrays['relief'][window])

# Source: tests.test_plate_td_product_fixture
def test_all_sea_and_land(portable):
    sea = prepare_fixture(portable, 'sea', locate(portable[3], 'sea'))
    _, arrays = _i17_td.read_plate_source(sea)
    assert not arrays['relief'].any()
    support = _i17_np.zeros(arrays['macro'].shape, _i17_np.float32)
    _i17_np.testing.assert_array_equal(arrays['bed'], _i17_compose(arrays['raw_td'], arrays['macro'], support=support))
    with _i17_pytest.raises(ValueError, match='no certified ocean anchor'):
        prepare_fixture(portable, 'land', locate(portable[3], 'land'))
    assert not (portable[0] / 'land').exists()

# Source: tests.test_plate_td_product_fixture
@_i17_pytest.mark.parametrize('key,value', [('valid_margin_bed_cells', 103), ('bed_origin_native_xz', [0, 0]), ('origin_native_xz', [0, 0]), ('relief_strength', 0.8), ('world_seed', 1)])
def test_rehashed_semantic_tamper(coastal, key, value):
    _, path = coastal
    manifest = _i17_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    manifest[key] = value
    save_manifest(path, manifest)
    with _i17_pytest.raises(ValueError):
        _i17_td.read_plate_source(path)

# Source: tests.test_plate_td_product_fixture
@_i17_pytest.mark.parametrize('name,dtype', [('raw_td', 'float64'), ('td_climate', 'float64'), ('macro', 'float64'), ('bed', 'float64'), ('relief', 'float64'), ('valid', 'uint8'), ('classification', 'int32'), ('shoreline', 'uint8')])
def test_rehashed_array_dtype_rejection(coastal, name, dtype):
    _, path = coastal
    manifest = _i17_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    file = path / (name + '.npy')
    array = _i17_np.load(file).astype(dtype)
    _i17_np.save(file, array, allow_pickle=False)
    manifest['files'][name] = _i17_td.digest(file)
    save_manifest(path, manifest)
    with _i17_pytest.raises(ValueError):
        _i17_td.read_plate_source(path)

# Source: tests.test_plate_td_product_fixture
@_i17_pytest.mark.parametrize('kind', ['model', 'source', 'code', 'physical_identity', 'conditioning_identity'])
def test_model_source_and_code_mismatch(portable, kind):
    path = prepare_fixture(portable, 'raw', (-10, -10), 16, False, 0.0)
    directory, source, config, frozen = portable
    if kind == 'model':
        (directory / 'model/unit-weights.bin').write_bytes(b'wrong model')
    elif kind == 'source':
        other_config = _i17_TectonicConfig(shape=(12, 16), plate_count=4, steps=4, origin_x_m=-80000.0, origin_z_m=-60000.0)
        other_source = directory / 'other-source.npz'
        _i17_save_product(_i17_freeze(other_config, _i17_evolve(other_config)), other_source)
        _i17_shutil.copyfile(other_source, source)
    else:
        manifest = _i17_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        generation = manifest['generation']
        if kind == 'code':
            generation['source_sha256']['plate_td_backend.py'] = '0' * 64
        elif kind == 'physical_identity':
            generation['physical_generation_identity'] = '0' * 64
        else:
            generation['physical_generation']['conditioning_identity'] = '0' * 64
        save_manifest(path, manifest)
    with _i17_pytest.raises((ValueError, OSError)):
        _i17_td.read_plate_source(path)

# Source: tests.test_plate_td_source
class PlateConditioningTests(_i18_unittest.TestCase):

    def test_portable_fixture_overlap_reconstruction_and_rejection(self):
        config = _i18_TectonicConfig(shape=(12, 16), plate_count=4, steps=3, origin_x_m=-80000.0, origin_z_m=-60000.0)
        product = _i18_freeze(config, _i18_evolve(config))
        with _i18_tempfile.TemporaryDirectory() as directory:
            path = _i18_Path(directory) / 'fixture.npz'
            _i18_save_product(product, path)
            factory = _i18_make_plate_factory(path, product.identity, _i18_WORLD_SEED, _i18_PhysicalGenerationConfig())
            whole = factory.sample_raw(-2, -2, 3, 3)
            _i18_np.testing.assert_array_equal(whole[:, 1:4, 1:4], factory.sample_raw(-1, -1, 2, 2))
            for z in reversed(range(-2, 3)):
                for x in reversed(range(-2, 3)):
                    _i18_np.testing.assert_array_equal(whole[:, z + 2, x + 2], factory.sample_raw(x, z, x + 1, z + 1)[:, 0, 0])
            with self.assertRaises(ValueError):
                _i18_make_plate_factory(path, '0' * 64, _i18_WORLD_SEED, _i18_PhysicalGenerationConfig())
            with self.assertRaises(ValueError):
                _i18_make_plate_factory(path, product.identity, _i18_WORLD_SEED + 1, _i18_PhysicalGenerationConfig())
            with self.assertRaises(ValueError):
                factory.sample_raw(-100, 0, -99, 1)
            code = 'import numpy as np,sys; from diffusion.plate_td_conditioning import make_plate_factory,WORLD_SEED; from diffusion.physical_config import PhysicalGenerationConfig; a=make_plate_factory(sys.argv[1],sys.argv[2],WORLD_SEED,PhysicalGenerationConfig()).sample_raw(-2,-2,3,3); np.save(sys.argv[3],a)'
            dest = _i18_Path(directory) / 'fresh.npy'
            _i18_subprocess.run([_i18_sys.executable, '-c', code, str(path), product.identity, str(dest)], check=True)
            _i18_np.testing.assert_array_equal(whole, _i18_np.load(dest))

    def test_direct_cli_help_and_conditioning_bounds(self):
        from diffusion.plate_td_conditioning import conditioning_footprint
        result = _i18_subprocess.run([_i18_sys.executable, 'tools/prepare_plate_source.py', '--help'], capture_output=True, text=True, check=True)
        self.assertIn('--expected-plate-identity', result.stdout)
        self.assertIn('--generate', result.stdout)
        self.assertEqual(conditioning_footprint((-495, -289), 913), [-48, -48, 64, 64])
        self.assertEqual(conditioning_footprint((-21 * 256, -20 * 256), 1), [-96, -48, 16, 16])

    def test_backend_refuses_insufficient_ram_before_worker(self):
        from diffusion.plate_td_backend import generate
        from diffusion.world_layout_backend import BudgetExceeded
        from types import SimpleNamespace
        with _i18_patch('diffusion.plate_td_backend.make_plate_factory') as factory, _i18_patch('psutil.virtual_memory', return_value=SimpleNamespace(available=1)), _i18_patch('multiprocessing.get_context') as context:
            with self.assertRaises(BudgetExceeded):
                generate('source', (0, 0), 1, _i18_PhysicalGenerationConfig(), expected_identity='a' * 64)
            context.assert_not_called()
