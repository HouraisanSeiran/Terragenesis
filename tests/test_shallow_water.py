"""Consolidated test_shallow_water implementations; numeric expressions preserved."""
from __future__ import annotations
import unittest as _i69_unittest
import numpy as _i69_np
import unittest as _i72_unittest
import numpy as _i72_np
import unittest as _i70_unittest
import numpy as _i70_np
import unittest as _i71_unittest
import numpy as _i71_np
import unittest as _i73_unittest
import numpy as _i73_np
import unittest as _i74_unittest
import numpy as _i74_np
import unittest as _i75_unittest
import numpy as _i75_np
import unittest as _i76_unittest
import numpy as _i76_np
import unittest as _i77_unittest
import numpy as _i77_np
import unittest as _i78_unittest
import numpy as _i78_np
CATEGORY = 'B'

class ShallowWaterTests(_i69_unittest.TestCase):

    def execute(self, bed, depth):
        from terrain_pipeline.shallow_water import advance_hydrostatic_hll as _i69_advance_shallow_water
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i69_prepare_surface_geometry
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i69_SurfaceBudget
        geometry = _i69_prepare_surface_geometry(bed, spacing_m=1.0, origin_m_xz=[0.0, 0.0], source_identity='synthetic')
        intervals = []
        momenta = []
        result = _i69_advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=0.1, intervals=2, forcing_provider=lambda i: _i69_np.zeros_like(bed), boundary_stage_provider=lambda i: _i69_np.zeros(2 * sum(bed.shape)), source_identity='synthetic', forcing_identity='synthetic', budget=_i69_SurfaceBudget(max_dt_s=0.01, max_snapshots=4), snapshot_interval_s=0.1, interval_observer=intervals.append, momentum_observer=momenta.append)
        return (result, geometry, intervals, momenta)

    def test_1350m_sloped_lake_execution_and_interval_momentum_closure(self):
        bed = 1350.0 + _i69_np.array([[0.0, 0.1, 0.2], [0.05, 0.15, 0.25]])
        depth = 1350.4 - bed
        result, g, intervals, _ = self.execute(bed, depth)
        _i69_np.testing.assert_allclose(result['arrays']['depth_m'][-1], depth, rtol=0.0, atol=1e-12)
        for packet in intervals:
            net = _i69_np.zeros((bed.size, 2))
            _i69_np.add.at(net, g['arrays']['face_left'], -packet['internal_momentum_transfer'])
            _i69_np.add.at(net, g['arrays']['face_right'], packet['internal_momentum_transfer'])
            _i69_np.add.at(net, g['arrays']['boundary_cell'], -packet['boundary_momentum_transfer'])
            expected = net + packet['bed_momentum_change'] + packet['manning_momentum_change']
            _i69_np.testing.assert_allclose(packet['momentum_after'] - packet['momentum_before'], expected, rtol=0.0, atol=1e-14)

    def test_flat_uniform_advective_momentum_flux(self):
        from terrain_pipeline.shallow_water import hydrostatic_hll as _i69_hydrostatic_hll
        state = _i69_np.array([[2.0, 6.0, 4.0]])
        flux, cl, cr, speed = _i69_hydrostatic_hll(state, state, _i69_np.array([0.0]), _i69_np.array([0.0]), gravity=9.81, axis=0)
        _i69_np.testing.assert_allclose(flux, [[6.0, 18.0 + 19.62, 12.0]], rtol=0.0, atol=1e-12)
        self.assertEqual(cl[0], 0.0)
        self.assertEqual(cr[0], 0.0)

    def test_sloped_bed_uniform_stage_well_balanced(self):
        from terrain_pipeline.shallow_water import shallow_water_rhs_flat as _i69_shallow_water_rhs
        bed = _i69_np.array([[0.0, 0.1, 0.2], [0.05, 0.15, 0.25]])
        depth = 0.4 - bed
        state = _i69_np.column_stack((depth.ravel(), _i69_np.zeros((6, 2))))
        rhs, witness = _i69_shallow_water_rhs(state, bed, spacing=1.0, gravity=9.81, boundary_kind=_i69_np.zeros(10, _i69_np.int64), tailwater=_i69_np.full(10, 0.4), roughness=0.035, dt=0.01)
        _i69_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=1e-14)

    def test_partially_dry_lake_uniform_stage_well_balanced(self):
        from terrain_pipeline.shallow_water import shallow_water_rhs_flat as _i69_shallow_water_rhs
        bed = _i69_np.array([[0.0, 0.1, 0.2], [0.05, 0.15, 0.25]])
        depth = _i69_np.maximum(0.13 - bed, 0.0)
        state = _i69_np.column_stack((depth.ravel(), _i69_np.zeros((6, 2))))
        rhs, _ = _i69_shallow_water_rhs(state, bed, spacing=1.0, gravity=9.81, boundary_kind=_i69_np.zeros(10, _i69_np.int64), tailwater=_i69_np.full(10, 0.13), roughness=0.035, dt=0.01)
        _i69_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=1e-14)

    def test_dam_front_mass_conservation_and_positive_forward_euler(self):
        from terrain_pipeline.shallow_water import shallow_water_rhs_flat as _i69_shallow_water_rhs
        bed = _i69_np.zeros((2, 8))
        depth = _i69_np.zeros_like(bed)
        depth[:, :4] = 1.0
        state = _i69_np.column_stack((depth.ravel(), _i69_np.zeros((16, 2))))
        rhs, w = _i69_shallow_water_rhs(state, bed, spacing=1.0, gravity=9.81, boundary_kind=_i69_np.zeros(20, _i69_np.int64), tailwater=_i69_np.zeros(20), roughness=0.035, dt=0.01)
        self.assertAlmostEqual(rhs[:, 0].sum(), 0.0, places=13)
        self.assertTrue(_i69_np.all((state + 0.01 * rhs)[:, 0] >= 0))
        self.assertGreater(_i69_np.max(w['internal_flux'][:, 0]), 0.0)

class ShallowWaterSubgridSegmentedTests(_i72_unittest.TestCase):

    def test_ritter_dry_bed_evolution_refines_toward_exact_cell_means(self):
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i72_SurfaceBudget
        from terrain_pipeline.shallow_water import advance_subgrid_segmented_hll as _i72_advance_shallow_water
        gravity, duration, dam, extent = (9.81, 5.0, 80.0, 160.0)
        celerity = _i72_np.sqrt(gravity)
        errors = []
        for factor in (4, 2, 1):
            geometry, _, _ = self.geometry(_i72_np.zeros((12, 160)), factor)
            bed = geometry['arrays']['H2_m']
            depth = _i72_np.zeros_like(bed)
            depth[:, :int(dam / factor)] = 1.0
            result = _i72_advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=duration, intervals=1, forcing_provider=lambda i: _i72_np.zeros_like(bed), boundary_stage_provider=lambda i: _i72_np.zeros(2 * sum(bed.shape)), source_identity='synthetic', forcing_identity='Ritter-dry-bed', budget=_i72_SurfaceBudget(max_dt_s=0.025, max_snapshots=3, max_duration_s=duration, roughness_s_m_third=1e-06), snapshot_interval_s=duration, interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
            lo = _i72_np.arange(int(extent / factor)) * factor - dam
            hi = lo + factor
            upstream_end, downstream_start = (-celerity * duration, 2 * celerity * duration)
            upstream = _i72_np.maximum(_i72_np.minimum(hi, upstream_end) - lo, 0.0)
            rare_lo, rare_hi = (_i72_np.maximum(lo, upstream_end), _i72_np.minimum(hi, downstream_start))
            primitive_lo = -duration / (27 * gravity) * (2 * celerity - rare_lo / duration) ** 3
            primitive_hi = -duration / (27 * gravity) * (2 * celerity - rare_hi / duration) ** 3
            rare = _i72_np.where(rare_hi > rare_lo, primitive_hi - primitive_lo, 0.0)
            exact = (upstream + rare) / factor
            numerical = result['arrays']['depth_m'][-1].mean(axis=0)
            errors.append(float(_i72_np.mean(abs(numerical - exact))))
            self.assertLess(abs(result['arrays']['ledger'][-1, -1]), 1e-09)
        self.assertLess(errors[1], errors[0] * 0.85, errors)
        self.assertLess(errors[2], errors[1] * 0.85, errors)
        self.assertLess(errors[2], 0.025, errors)
        self.ritter_l1_errors = errors

    def geometry(self, canonical, factor):
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i72_prepare_surface_geometry
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i72_coarsen_cell_field
        from terrain_pipeline.fine_subgrid import prepare_subgrid_support as _i72_prepare_subgrid_support
        coarse = canonical if factor == 1 else _i72_coarsen_cell_field(canonical, factor=factor)
        bed = dict(arrays=dict(canonical_bed_center_m=canonical, H2_m=coarse), metadata=dict(spacing_m=float(factor)))
        support, datum = _i72_prepare_subgrid_support(bed)
        geometry = _i72_prepare_surface_geometry(coarse, spacing_m=float(factor), origin_m_xz=[0.0, 0.0], source_identity='synthetic')
        geometry['arrays'].update(support)
        geometry['metadata']['hydraulic_datum_m'] = datum
        return (geometry, support, datum)

    def test_canonical_half_wet_lake_at_all_resolutions(self):
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i72_SurfaceBudget
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i72_coarsen_cell_field
        from terrain_pipeline.shallow_water import subgrid_segmented_hll_rhs as _i72_shallow_water_rhs
        from terrain_pipeline.shallow_water import advance_subgrid_segmented_hll as _i72_advance_shallow_water
        canonical = 1350.0 + _i72_np.tile(_i72_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i72_np.arange(12)[:, None]
        fine_depth = _i72_np.maximum(1350.8 - canonical, 0.0)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            depth = fine_depth if factor == 1 else _i72_coarsen_cell_field(fine_depth, factor=factor)
            state = _i72_np.column_stack((depth.ravel(), _i72_np.zeros((bed.size, 2))))
            rhs, _ = _i72_shallow_water_rhs(state, bed - datum, support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i72_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            _i72_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-12)
            result = _i72_advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=0.1, intervals=2, forcing_provider=lambda i: _i72_np.zeros_like(bed), boundary_stage_provider=lambda i: _i72_np.zeros(2 * sum(bed.shape)), source_identity='synthetic', forcing_identity='synthetic', budget=_i72_SurfaceBudget(max_dt_s=0.01, max_snapshots=4), snapshot_interval_s=0.1, interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
            _i72_np.testing.assert_allclose(result['arrays']['depth_m'][-1], depth, rtol=0.0, atol=2e-12)

    def test_flat_bed_nonuniform_state_matches_standard_shallow_water(self):
        from terrain_pipeline.shallow_water import shallow_water_rhs_flat as _i72_flat_rhs
        from terrain_pipeline.shallow_water import subgrid_segmented_hll_rhs as _i72_shallow_water_rhs
        canonical = _i72_np.zeros((12, 16))
        rng = _i72_np.random.default_rng(13)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            state = _i72_np.column_stack((rng.uniform(0.1, 2.0, bed.size), rng.uniform(-0.2, 0.2, (bed.size, 2))))
            args = dict(spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i72_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            rhs, witness = _i72_shallow_water_rhs(state, bed, support=support, **args)
            expected, _ = _i72_flat_rhs(state, bed, **args)
            _i72_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)
            _i72_np.testing.assert_allclose(rhs, expected, rtol=0.0, atol=1e-13)

    def test_flat_dam_break_has_pressure_driven_momentum(self):
        from terrain_pipeline.shallow_water import subgrid_segmented_hll_rhs as _i72_shallow_water_rhs
        geometry, support, _ = self.geometry(_i72_np.zeros((8, 16)), 2)
        bed = geometry['arrays']['H2_m']
        depth = _i72_np.ones_like(bed)
        depth[:, :bed.shape[1] // 2] = 2.0
        state = _i72_np.column_stack((depth.ravel(), _i72_np.zeros((bed.size, 2))))
        rhs, witness = _i72_shallow_water_rhs(state, bed, support=support, spacing=2.0, gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i72_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
        self.assertGreater(float(rhs[:, 1].max()), 1.0)
        self.assertAlmostEqual(float(rhs[:, 0].sum()), 0.0, places=13)
        _i72_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)

class ShallowWaterAcceleratedTests(_i70_unittest.TestCase):

    def test_extreme_thin_and_dry_states_remain_finite_and_equivalent(self):
        from terrain_pipeline.shallow_water import subgrid_segmented_hll_rhs as _i70_reference_rhs
        from terrain_pipeline.shallow_water import manning_damping_canonical as _i70_reference_drag
        from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as _i70_accelerated_rhs
        from terrain_pipeline.shallow_water import manning_damping_accelerated as _i70_accelerated_drag
        geometry, support, _ = ShallowWaterSubgridSegmentedTests().geometry(_i70_np.zeros((12, 16)), 1)
        bed = geometry['arrays']['H2_m']
        depth = _i70_np.resize(_i70_np.array([0.0, 1e-300, 1e-100, 1e-20, 0.1, 1.0]), bed.size)
        state = _i70_np.column_stack((depth, 0.01 * depth, -0.02 * depth))
        args = dict(support=support, spacing=1.0, gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i70_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
        expected, _ = _i70_reference_rhs(state, bed, **args)
        actual, _ = _i70_accelerated_rhs(state, bed, **args)
        self.assertTrue(_i70_np.isfinite(actual).all())
        _i70_np.testing.assert_allclose(actual, expected, atol=2e-12, rtol=2e-12)
        for actual_value, expected_value in zip(_i70_accelerated_drag(state, 0.01, 9.81, 0.035, support=support), _i70_reference_drag(state, 0.01, 9.81, 0.035, support=support)):
            self.assertTrue(_i70_np.isfinite(actual_value).all())
            _i70_np.testing.assert_allclose(actual_value, expected_value, atol=2e-12, rtol=2e-12)

    def test_explicit_fine_backend_binding_and_independent_physical_audit(self):
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i70_SurfaceBudget
        from tests.test_fine_subgrid import fixture as fixture
        from terrain_pipeline.fine_subgrid import build_fine_geometry
        from terrain_pipeline.fine_subgrid import run_fine_hydraulics
        from terrain_pipeline.fine_subgrid import validate_fine_states
        from terrain_pipeline.fine_subgrid import validate_fine_interval
        from terrain_pipeline.fine_subgrid import validate_fine_momentum
        from tools.audit_shallow_water import audit_momentum
        hierarchy, _ = fixture()
        bed = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64, spacing_m=2.0)
        shape = bed['arrays']['bed_center_m'].shape
        options = dict(rain_mm_h=_i70_np.zeros((2, *shape)), boundary_kind=_i70_np.zeros(2 * sum(shape), _i70_np.int64), boundary_stage_m=_i70_np.zeros((2, 2 * sum(shape))), forcing_interval_s=0.05, initial_depth_m=_i70_np.full(shape, 0.1), budget=_i70_SurfaceBudget(max_dt_s=0.01, max_snapshots=4, max_wall_s=1800.0))
        reference = run_fine_hydraulics(bed, backend='shallow_water_subgrid_manning', **options)
        actual = run_fine_hydraulics(bed, backend='shallow_water_subgrid_manning_accelerated', **options)
        self.assertEqual(reference['geometry']['identity_sha256'], actual['geometry']['identity_sha256'])
        for name, values in reference['states']['arrays'].items():
            _i70_np.testing.assert_allclose(actual['states']['arrays'][name], values, atol=2e-11, rtol=2e-12)
        self.assertIn('numba', actual['states']['metadata']['solver_metadata']['execution_backend'])
        validate_fine_states(actual['states'], bed=bed, geometry=actual['geometry'], forcing=actual['forcing'])
        raw_geometry = dict(actual['geometry']['arrays'], hydraulic_datum_m=actual['geometry']['metadata']['hydraulic_datum_m'])
        previous = None
        for number, packet in enumerate(actual['intervals']):
            validate_fine_interval(packet, bed=bed, geometry=actual['geometry'], forcing=actual['forcing'], interval=number, previous=previous)
            validate_fine_momentum(actual['momenta'][number], bed=bed, geometry=actual['geometry'], forcing=actual['forcing'], states=actual['states'], interval=number, interval_packet=packet)
            momentum = actual['momenta'][number]
            audit_momentum(momentum['arrays'], momentum['metadata'], raw_geometry, 2.0, actual['states']['metadata']['solver_metadata']['budget'], actual['forcing']['arrays']['local_q_m3_s'][number], actual['forcing']['arrays']['boundary_stage_m'][number])
            previous = packet

    def test_random_flat_partial_wet_boundaries_and_limiter_equivalence(self):
        from terrain_pipeline.shallow_water import subgrid_segmented_hll_rhs as _i70_reference_rhs
        from terrain_pipeline.shallow_water import manning_damping_canonical as _i70_reference_drag
        from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as _i70_accelerated_rhs
        from terrain_pipeline.shallow_water import manning_damping_accelerated as _i70_accelerated_drag
        rng = _i70_np.random.default_rng(718)
        limited_cases = 0
        for factor in (1, 2, 4):
            for flat in (False, True):
                canonical = _i70_np.zeros((12, 16)) if flat else rng.uniform(0.0, 2.0, (12, 16))
                geometry, support, datum = ShallowWaterSubgridSegmentedTests().geometry(canonical, factor)
                arrays = geometry['arrays']
                bed = arrays['H2_m']
                depth = rng.uniform(0.001, 0.3, bed.size)
                depth[rng.random(bed.size) < 0.3] = 0
                state = _i70_np.column_stack((depth, depth[:, None] * rng.uniform(-3.0, 3.0, (bed.size, 2))))
                kinds = _i70_np.arange(len(arrays['boundary_kind']), dtype=_i70_np.int64) % 3
                tailwater = rng.uniform(0.0, 2.0, len(kinds))
                for dt in (0.0, 0.01, 5.0):
                    args = dict(support=support, spacing=float(factor), gravity=9.81, boundary_kind=kinds, tailwater=tailwater, roughness=0.035, dt=dt, boundary_crest=arrays['boundary_crest_m'] - datum + 0.05)
                    expected, witness = _i70_reference_rhs(state, bed - datum, **args)
                    actual, jit_witness = _i70_accelerated_rhs(state, bed - datum, **args)
                    _i70_np.testing.assert_allclose(actual, expected, atol=2e-11, rtol=2e-12)
                    for name in ('internal_flux', 'boundary_flux', 'bed_source'):
                        _i70_np.testing.assert_allclose(jit_witness[name], witness[name], atol=2e-11, rtol=2e-12)
                    for name in ('maximum_wave_speed', 'minimum_limiter_factor'):
                        self.assertAlmostEqual(jit_witness[name], witness[name], places=12)
                    self.assertEqual(jit_witness['limited_donors'], witness['limited_donors'])
                    limited_cases += witness['limited_donors'] > 0
                    expected_drag = _i70_reference_drag(state, dt, 9.81, 0.035, support=support)
                    actual_drag = _i70_accelerated_drag(state, dt, 9.81, 0.035, support=support)
                    for a, b in zip(actual_drag, expected_drag):
                        _i70_np.testing.assert_allclose(a, b, atol=2e-12, rtol=2e-12)
        self.assertGreater(limited_cases, 0)

    def test_closed_half_wet_lake_and_flat_dam_pressure_equivalence(self):
        from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as _i70_accelerated_rhs
        canonical = 1350.0 + _i70_np.tile(_i70_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i70_np.arange(12)[:, None]
        for factor in (1, 2, 4):
            geometry, support, datum = ShallowWaterSubgridSegmentedTests().geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            h = _i70_np.maximum(1350.8 - canonical, 0).reshape(12 // factor, factor, 16 // factor, factor).mean(axis=(1, 3))
            state = _i70_np.column_stack((h.ravel(), _i70_np.zeros((h.size, 2))))
            rhs, _ = _i70_accelerated_rhs(state, bed - datum, support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i70_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            _i70_np.testing.assert_allclose(rhs, 0, atol=2e-12, rtol=0)
        geometry, support, _ = ShallowWaterSubgridSegmentedTests().geometry(_i70_np.zeros((12, 16)), 2)
        bed = geometry['arrays']['H2_m']
        h = _i70_np.ones_like(bed)
        h[:, :4] = 2
        rhs, witness = _i70_accelerated_rhs(_i70_np.column_stack((h.ravel(), _i70_np.zeros((h.size, 2)))), bed, support=support, spacing=2.0, gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i70_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
        _i70_np.testing.assert_allclose(witness['bed_source'], 0, atol=1e-14, rtol=0)
        self.assertGreater(rhs[:, 1].max(), 1.0)

    def test_short_evolution_and_saved_witness_equivalence(self):
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i70_SurfaceBudget
        from terrain_pipeline.shallow_water import advance_canonical_manning as _i70_reference_advance
        from terrain_pipeline.shallow_water import advance_shallow_water_accelerated as _i70_accelerated_advance
        canonical = _i70_np.random.default_rng(720).uniform(0.0, 0.3, (12, 16))
        geometry, _, _ = ShallowWaterSubgridSegmentedTests().geometry(canonical, 2)
        arrays = geometry['arrays']
        bed = arrays['H2_m']
        arrays['boundary_kind'][6:12] = 2
        packets = []
        outputs = []
        for advance in (_i70_reference_advance, _i70_accelerated_advance):
            intervals, momenta = ([], [])
            output = advance(geometry, initial_depth_m=_i70_np.full(bed.shape, 0.2), forcing_interval_s=0.1, intervals=3, forcing_provider=lambda i: _i70_np.full(bed.shape, 0.0001), boundary_stage_provider=lambda i: _i70_np.full(2 * sum(bed.shape), 0.7 + i * 0.1), source_identity='equivalence', forcing_identity='equivalence', budget=_i70_SurfaceBudget(max_dt_s=0.01, max_snapshots=5), snapshot_interval_s=0.1, interval_observer=intervals.append, momentum_observer=momenta.append)
            outputs.append(output)
            packets.append((intervals, momenta))
        for name, expected in outputs[0]['arrays'].items():
            _i70_np.testing.assert_allclose(outputs[1]['arrays'][name], expected, atol=2e-11, rtol=2e-12)
        for field in ('substeps', 'face_evaluations'):
            self.assertEqual(outputs[0]['metadata'][field], outputs[1]['metadata'][field])
        for expected_group, actual_group in zip(packets[0], packets[1]):
            for expected, actual in zip(expected_group, actual_group):
                self.assertEqual(set(expected), set(actual))
                for name in expected:
                    _i70_np.testing.assert_allclose(actual[name], expected[name], atol=2e-11, rtol=2e-12)

class ShallowWaterMusclCoarseBedTests(_i71_unittest.TestCase):

    def test_execution_static_lake_and_momentum_closure(self):
        from terrain_pipeline.shallow_water import advance_muscl_coarse_bed as _i71_advance_shallow_water
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i71_prepare_surface_geometry
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i71_SurfaceBudget
        bed = 1350.0 + _i71_np.tile(_i71_np.arange(10) * 0.1, (6, 1)) + 0.05 * _i71_np.arange(6)[:, None]
        for stage in (1350.5, 1352.0):
            depth = _i71_np.maximum(stage - bed, 0.0)
            geometry = _i71_prepare_surface_geometry(bed, spacing_m=1.0, origin_m_xz=[0.0, 0.0], source_identity='synthetic')
            packets = []
            result = _i71_advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=0.1, intervals=2, forcing_provider=lambda i: _i71_np.zeros_like(bed), boundary_stage_provider=lambda i: _i71_np.zeros(2 * sum(bed.shape)), source_identity='synthetic', forcing_identity='synthetic', budget=_i71_SurfaceBudget(max_dt_s=0.01, max_snapshots=4), snapshot_interval_s=0.1, interval_observer=packets.append, momentum_observer=lambda packet: None)
            _i71_np.testing.assert_allclose(result['arrays']['depth_m'][-1], depth, rtol=0.0, atol=1e-12)
            for packet in packets:
                net = _i71_np.zeros((bed.size, 2))
                a = geometry['arrays']
                _i71_np.add.at(net, a['face_left'], -packet['internal_momentum_transfer'])
                _i71_np.add.at(net, a['face_right'], packet['internal_momentum_transfer'])
                _i71_np.add.at(net, a['boundary_cell'], -packet['boundary_momentum_transfer'])
                expected = net + packet['bed_momentum_change'] + packet['manning_momentum_change']
                _i71_np.testing.assert_allclose(packet['momentum_after'] - packet['momentum_before'], expected, rtol=0.0, atol=1e-13)

    def test_sloped_uniform_stage_and_dry_shore(self):
        from terrain_pipeline.shallow_water import muscl_coarse_bed_rhs as _i71_shallow_water_rhs
        bed = _i71_np.tile(_i71_np.arange(10) * 0.1, (6, 1)) + 0.05 * _i71_np.arange(6)[:, None]
        for stage in (0.5, 2.0):
            depth = _i71_np.maximum(stage - bed, 0.0)
            state = _i71_np.column_stack((depth.ravel(), _i71_np.zeros((bed.size, 2))))
            rhs, witness = _i71_shallow_water_rhs(state, bed, spacing=1.0, gravity=9.81, boundary_kind=_i71_np.zeros(2 * sum(bed.shape), _i71_np.int64), tailwater=_i71_np.full(2 * sum(bed.shape), stage), roughness=0.035, dt=0.01)
            _i71_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=1e-13)

    def test_positive_reconstruction_and_closed_mass(self):
        from terrain_pipeline.shallow_water import reconstruct_muscl_coarse as _i71_reconstruct
        from terrain_pipeline.shallow_water import muscl_coarse_bed_rhs as _i71_shallow_water_rhs
        bed = _i71_np.zeros((6, 10))
        depth = _i71_np.random.default_rng(12).random(bed.shape)
        depth[depth < 0.3] = 0.0
        state = _i71_np.column_stack((depth.ravel(), _i71_np.zeros((bed.size, 2))))
        faces, _ = _i71_reconstruct(state, bed)
        self.assertTrue(all((_i71_np.all(face[:, 0] >= 0) for face in faces)))
        rhs, _ = _i71_shallow_water_rhs(state, bed, spacing=1.0, gravity=9.81, boundary_kind=_i71_np.zeros(2 * sum(bed.shape), _i71_np.int64), tailwater=_i71_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
        self.assertAlmostEqual(float(rhs[:, 0].sum()), 0.0, places=12)
        self.assertTrue(_i71_np.all((state + 0.01 * rhs)[:, 0] >= 0))

class ShallowWaterSubgridMusclTests(_i73_unittest.TestCase):

    def test_half_wet_lake_and_flat_nonuniform_pressure_source(self):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i73_coarsen_cell_field
        from terrain_pipeline.shallow_water import subgrid_muscl_segmented_hll_rhs as _i73_shallow_water_rhs
        helper = ShallowWaterSubgridSegmentedTests()
        canonical = 1350.0 + _i73_np.tile(_i73_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i73_np.arange(12)[:, None]
        fine_depth = _i73_np.maximum(1350.8 - canonical, 0.0)
        for factor in (1, 2, 4):
            geometry, support, datum = helper.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            depth = fine_depth if factor == 1 else _i73_coarsen_cell_field(fine_depth, factor=factor)
            state = _i73_np.column_stack((depth.ravel(), _i73_np.zeros((bed.size, 2))))
            args = dict(support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i73_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            rhs, _ = _i73_shallow_water_rhs(state, bed - datum, **args)
            _i73_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-12)
            geometry, support, datum = helper.geometry(_i73_np.zeros_like(canonical), factor)
            bed = geometry['arrays']['H2_m']
            rng = _i73_np.random.default_rng(19)
            state = _i73_np.column_stack((rng.uniform(0.1, 2.0, bed.size), rng.uniform(-0.2, 0.2, (bed.size, 2))))
            args['support'] = support
            rhs, witness = _i73_shallow_water_rhs(state, bed, **args)
            _i73_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)
            self.assertAlmostEqual(float(rhs[:, 0].sum()), 0.0, places=12)
            self.assertTrue(_i73_np.all((state + 0.01 * rhs)[:, 0] >= 0))

class ShallowWaterDryIndependentTests(_i74_unittest.TestCase):

    def test_reservoir_stage_is_a_face_value_for_linear_reconstruction(self):
        from terrain_pipeline.shallow_water import reconstruct_independent_slope as _i74__reconstruct
        geometry, support, _ = ShallowWaterSubgridSegmentedTests().geometry(_i74_np.zeros((4, 8)), 1)
        bed = geometry['arrays']['H2_m']
        stage = _i74_np.tile(1.0 + 0.01 * (_i74_np.arange(8) + 0.5), (4, 1)).ravel()
        kind = _i74_np.zeros(24, _i74_np.int64)
        kind[:8] = 2
        tail = _i74_np.ones(24)
        tail[4:8] = 1.08
        faces = _i74__reconstruct(stage, _i74_np.zeros((bed.size, 2)), stage, bed, support, kind, tail)
        _i74_np.testing.assert_allclose(faces[0].reshape(4, 8, 3)[:, 0, 0], 1.0, rtol=0.0, atol=1e-14)
        _i74_np.testing.assert_allclose(faces[1].reshape(4, 8, 3)[:, -1, 0], 1.08, rtol=0.0, atol=1e-14)

    def test_open_half_wet_lake_and_flat_arbitrary_state_source(self):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i74_coarsen_cell_field
        from terrain_pipeline.shallow_water import dry_independent_rhs as _i74_shallow_water_rhs
        canonical = 1350.0 + _i74_np.tile(_i74_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i74_np.arange(12)[:, None]
        fine_depth = _i74_np.maximum(1350.8 - canonical, 0.0)
        helper = ShallowWaterSubgridSegmentedTests()
        for factor in (1, 2, 4):
            geometry, support, datum = helper.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            depth = fine_depth if factor == 1 else _i74_coarsen_cell_field(fine_depth, factor=factor)
            state = _i74_np.column_stack((depth.ravel(), _i74_np.zeros((bed.size, 2))))
            kind = _i74_np.full(2 * sum(bed.shape), 2, _i74_np.int64)
            args = dict(support=support, spacing=float(factor), gravity=9.81, boundary_kind=kind, tailwater=_i74_np.full(len(kind), 1350.8 - datum), roughness=0.035, dt=0.01)
            rhs, _ = _i74_shallow_water_rhs(state, bed - datum, **args)
            _i74_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-12)
            geometry, support, _ = helper.geometry(_i74_np.zeros_like(canonical), factor)
            bed = geometry['arrays']['H2_m']
            rng = _i74_np.random.default_rng(24)
            state = _i74_np.column_stack((rng.uniform(0.1, 2.0, bed.size), rng.uniform(-0.2, 0.2, (bed.size, 2))))
            args['support'] = support
            args['tailwater'] = _i74_np.ones(len(kind))
            rhs, witness = _i74_shallow_water_rhs(state, bed, **args)
            _i74_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)
            self.assertTrue(_i74_np.all((state + 0.01 * rhs)[:, 0] >= 0))

    def test_reservoir_pulse_wave_enters_interior_and_conserves_import(self):
        from terrain_pipeline.shallow_water import advance_dry_independent as _i74_advance_shallow_water
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i74_SurfaceBudget
        geometry, _, _ = ShallowWaterSubgridSegmentedTests().geometry(_i74_np.zeros((8, 80)), 2)
        bed = geometry['arrays']['H2_m']
        rows, columns = bed.shape
        geometry['arrays']['boundary_kind'][rows:2 * rows] = 2
        tail = _i74_np.ones(2 * (rows + columns))
        tail[rows:2 * rows] = 1.5
        result = _i74_advance_shallow_water(geometry, initial_depth_m=_i74_np.ones_like(bed), forcing_interval_s=2.0, intervals=1, forcing_provider=lambda i: _i74_np.zeros_like(bed), boundary_stage_provider=lambda i: tail, source_identity='synthetic', forcing_identity='reservoir-pulse', budget=_i74_SurfaceBudget(max_dt_s=0.025, max_snapshots=3, max_duration_s=2.0), snapshot_interval_s=2.0, interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
        final = result['arrays']['depth_m'][-1]
        self.assertGreater(float(final[:, -2].min()), 1.01)
        self.assertLess(float(result['arrays']['momentum_x_m2_s'][-1, :, -2].max()), -0.01)
        _i74_np.testing.assert_allclose(final[:, :columns // 2], 1.0, rtol=0.0, atol=1e-12)
        self.assertGreater(result['metadata']['boundary_input_m3'], 0.0)
        self.assertLess(abs(result['arrays']['ledger'][-1, -1]), 1e-09)

class ShallowWaterDryNeighborTests(_i75_unittest.TestCase):

    def test_dry_neighbor_has_no_free_surface_constraint_and_positivity(self):
        from terrain_pipeline.shallow_water import reconstruct_dry_neighbor_slope as _i75__reconstruct
        from terrain_pipeline.shallow_water import dry_neighbor_rhs as _i75_shallow_water_rhs
        canonical = _i75_np.full((4, 8), 2.0)
        canonical[:, -1] = 0.0
        geometry, support, _ = ShallowWaterSubgridSegmentedTests().geometry(canonical, 1)
        bed = geometry['arrays']['H2_m']
        stage = bed.ravel().copy()
        stage.reshape(bed.shape)[:, -1] = 1.0
        depth = _i75_np.maximum(stage - bed.ravel(), 0.0)
        kind = _i75_np.zeros(24, _i75_np.int64)
        kind[4:8] = 2
        tail = _i75_np.full(24, 1.5)
        faces = _i75__reconstruct(stage, _i75_np.zeros((bed.size, 2)), depth, bed, support, kind, tail)
        _i75_np.testing.assert_allclose(faces[1].reshape(4, 8, 3)[:, -1, 0], 1.5, rtol=0.0, atol=1e-14)
        tail[4:8] = 10.0
        faces = _i75__reconstruct(stage, _i75_np.zeros((bed.size, 2)), depth, bed, support, kind, tail)
        for face in faces:
            self.assertTrue(_i75_np.all(face[depth > 0, 0] >= 0))
        state = _i75_np.column_stack((depth, _i75_np.zeros((bed.size, 2))))
        rhs, _ = _i75_shallow_water_rhs(state, bed, support=support, spacing=1.0, gravity=9.81, boundary_kind=kind, tailwater=tail, roughness=0.035, dt=0.01)
        self.assertTrue(_i75_np.all((state + 0.01 * rhs)[:, 0] >= 0))

    def test_reservoir_stage_is_a_face_value_for_linear_reconstruction(self):
        from terrain_pipeline.shallow_water import reconstruct_dry_neighbor_slope as _i75__reconstruct
        geometry, support, _ = ShallowWaterSubgridSegmentedTests().geometry(_i75_np.zeros((4, 8)), 1)
        bed = geometry['arrays']['H2_m']
        stage = _i75_np.tile(1.0 + 0.01 * (_i75_np.arange(8) + 0.5), (4, 1)).ravel()
        kind = _i75_np.zeros(24, _i75_np.int64)
        kind[:8] = 2
        tail = _i75_np.ones(24)
        tail[4:8] = 1.08
        faces = _i75__reconstruct(stage, _i75_np.zeros((bed.size, 2)), stage, bed, support, kind, tail)
        _i75_np.testing.assert_allclose(faces[0].reshape(4, 8, 3)[:, 0, 0], 1.0, rtol=0.0, atol=1e-14)
        _i75_np.testing.assert_allclose(faces[1].reshape(4, 8, 3)[:, -1, 0], 1.08, rtol=0.0, atol=1e-14)

    def test_open_half_wet_lake_and_flat_arbitrary_state_source(self):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i75_coarsen_cell_field
        from terrain_pipeline.shallow_water import dry_neighbor_rhs as _i75_shallow_water_rhs
        canonical = 1350.0 + _i75_np.tile(_i75_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i75_np.arange(12)[:, None]
        fine_depth = _i75_np.maximum(1350.8 - canonical, 0.0)
        helper = ShallowWaterSubgridSegmentedTests()
        for factor in (1, 2, 4):
            geometry, support, datum = helper.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            depth = fine_depth if factor == 1 else _i75_coarsen_cell_field(fine_depth, factor=factor)
            state = _i75_np.column_stack((depth.ravel(), _i75_np.zeros((bed.size, 2))))
            kind = _i75_np.full(2 * sum(bed.shape), 2, _i75_np.int64)
            args = dict(support=support, spacing=float(factor), gravity=9.81, boundary_kind=kind, tailwater=_i75_np.full(len(kind), 1350.8 - datum), roughness=0.035, dt=0.01)
            rhs, _ = _i75_shallow_water_rhs(state, bed - datum, **args)
            _i75_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-12)
            geometry, support, _ = helper.geometry(_i75_np.zeros_like(canonical), factor)
            bed = geometry['arrays']['H2_m']
            rng = _i75_np.random.default_rng(24)
            state = _i75_np.column_stack((rng.uniform(0.1, 2.0, bed.size), rng.uniform(-0.2, 0.2, (bed.size, 2))))
            args['support'] = support
            args['tailwater'] = _i75_np.ones(len(kind))
            rhs, witness = _i75_shallow_water_rhs(state, bed, **args)
            _i75_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)
            self.assertTrue(_i75_np.all((state + 0.01 * rhs)[:, 0] >= 0))

    def test_reservoir_pulse_wave_enters_interior_and_conserves_import(self):
        from terrain_pipeline.shallow_water import advance_dry_neighbor as _i75_advance_shallow_water
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i75_SurfaceBudget
        geometry, _, _ = ShallowWaterSubgridSegmentedTests().geometry(_i75_np.zeros((8, 80)), 2)
        bed = geometry['arrays']['H2_m']
        rows, columns = bed.shape
        geometry['arrays']['boundary_kind'][rows:2 * rows] = 2
        tail = _i75_np.ones(2 * (rows + columns))
        tail[rows:2 * rows] = 1.5
        result = _i75_advance_shallow_water(geometry, initial_depth_m=_i75_np.ones_like(bed), forcing_interval_s=2.0, intervals=1, forcing_provider=lambda i: _i75_np.zeros_like(bed), boundary_stage_provider=lambda i: tail, source_identity='synthetic', forcing_identity='reservoir-pulse', budget=_i75_SurfaceBudget(max_dt_s=0.025, max_snapshots=3, max_duration_s=2.0), snapshot_interval_s=2.0, interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
        final = result['arrays']['depth_m'][-1]
        self.assertGreater(float(final[:, -2].min()), 1.01)
        self.assertLess(float(result['arrays']['momentum_x_m2_s'][-1, :, -2].max()), -0.01)
        _i75_np.testing.assert_allclose(final[:, :columns // 2], 1.0, rtol=0.0, atol=1e-12)
        self.assertGreater(result['metadata']['boundary_input_m3'], 0.0)
        self.assertLess(abs(result['arrays']['ledger'][-1, -1]), 1e-09)

class ShallowWaterCanonicalManningTests(_i76_unittest.TestCase):

    def test_flat_fully_wet_drag_reduces_to_standard_manning(self):
        from terrain_pipeline.shallow_water import manning_damping_canonical as _i76_manning_damping
        subbed = _i76_np.zeros((3, 4))
        support = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=_i76_np.cumsum(subbed, axis=1))
        state = _i76_np.array([[0.2, 0.4, 0.3], [1.0, 2.0, 1.0], [2.0, -1.0, 3.0]])
        dt, gravity, roughness = (0.025, 9.81, 0.035)
        damping, factor = _i76_manning_damping(state, dt, gravity, roughness, support=support)
        expected = 1 / (1 + dt * gravity * roughness ** 2 * _i76_np.hypot(state[:, 1], state[:, 2]) / state[:, 0] ** (7 / 3))
        _i76_np.testing.assert_allclose(damping, expected, rtol=0.0, atol=2e-15)
        _i76_np.testing.assert_allclose(factor, state[:, 0] ** (-1 / 3), rtol=0.0, atol=2e-15)

    def test_half_wet_drag_integral_includes_dry_zero_area(self):
        from terrain_pipeline.shallow_water import manning_damping_canonical as _i76_manning_damping
        subbed = _i76_np.array([[0.0, 0.0, 2.0, 2.0]])
        support = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=_i76_np.cumsum(subbed, axis=1))
        state = _i76_np.array([[0.5, 1.0, 0.0]])
        damping, factor = _i76_manning_damping(state, 0.1, 9.81, 0.035, support=support)
        _i76_np.testing.assert_allclose(factor, [0.5], rtol=0.0, atol=1e-15)
        _i76_np.testing.assert_allclose(damping, [0.25 / (0.25 + 0.1 * 9.81 * 0.035 ** 2 * 0.5)], rtol=0.0, atol=1e-15)
        old_damping = 1 / (1 + 0.1 * 9.81 * 0.035 ** 2 / 0.5 ** (7 / 3))
        self.assertGreater(damping[0], old_damping)

    def test_extremely_thin_and_dry_drag_is_finite(self):
        from terrain_pipeline.shallow_water import manning_damping_canonical as _i76_manning_damping
        subbed = _i76_np.zeros((2, 1))
        support = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=subbed.copy())
        state = _i76_np.array([[1e-300, 0.0, 0.0], [0.0, 0.0, 0.0]])
        damping, factor = _i76_manning_damping(state, 0.1, 9.81, 0.035, support=support)
        self.assertTrue(_i76_np.isfinite(damping).all())
        self.assertTrue(_i76_np.isfinite(factor).all())

    def test_saved_first_rk_friction_witness_is_bound_to_depth(self):
        from terrain_pipeline.shallow_water import manning_damping_canonical as _i76_manning_damping
        from terrain_pipeline.shallow_water import advance_canonical_manning as _i76_advance_shallow_water
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i76_SurfaceBudget
        geometry, support, _ = ShallowWaterSubgridSegmentedTests().geometry(_i76_np.zeros((8, 16)), 2)
        bed = geometry['arrays']['H2_m']
        depth = _i76_np.ones_like(bed)
        depth[:, :4] = 2.0
        packets = []
        result = _i76_advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=0.1, intervals=1, forcing_provider=lambda i: _i76_np.zeros_like(bed), boundary_stage_provider=lambda i: _i76_np.zeros(2 * sum(bed.shape)), source_identity='synthetic', forcing_identity='dam-break', budget=_i76_SurfaceBudget(max_dt_s=0.025, max_snapshots=3), snapshot_interval_s=0.1, interval_observer=lambda packet: None, momentum_observer=packets.append)
        packet = packets[0]
        _, factor = _i76_manning_damping(packet['state_after'], packet['dt_s'], 9.81, 0.035, support=support)
        _i76_np.testing.assert_allclose(packet['manning_inverse_depth_third_mean'], factor, rtol=0.0, atol=1e-15)
        self.assertLess(abs(result['arrays']['ledger'][-1, -1]), 1e-10)

class ShallowWaterLinearStageTests(_i77_unittest.TestCase):

    def geometry(self, canonical, factor):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i77_coarsen_cell_field
        from terrain_pipeline.shallow_water import prepare_linear_stage_independent_support as _i77_prepare_support
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i77_prepare_surface_geometry
        coarse = canonical if factor == 1 else _i77_coarsen_cell_field(canonical, factor=factor)
        bed = dict(arrays=dict(canonical_bed_center_m=canonical, H2_m=coarse), metadata=dict(spacing_m=float(factor)))
        support, datum = _i77_prepare_support(bed)
        geometry = _i77_prepare_surface_geometry(coarse, spacing_m=float(factor), origin_m_xz=[0.0, 0.0], source_identity='synthetic')
        geometry['arrays'].update(support)
        geometry['metadata']['hydraulic_datum_m'] = datum
        return (geometry, support, datum)

    def test_linear_stage_inversion_preserves_volume_and_momentum(self):
        from terrain_pipeline.fine_subgrid import stage_depths as _i77_stage_depths
        from terrain_pipeline.fine_subgrid import storage_stages as _i77_storage_stages
        from terrain_pipeline.shallow_water import reconstruct_linear_stage_independent as _i77_reconstruct
        canonical = _i77_np.random.default_rng(30).uniform(0.0, 2.0, (12, 16))
        geometry, support, datum = self.geometry(canonical, 2)
        bed = geometry['arrays']['H2_m']
        eta = _i77_np.tile(0.8 + 0.15 * _i77_np.arange(8), (6, 1)).ravel()
        depth = _i77_stage_depths(eta, support['subcell_bed_relative_m'])
        velocity = _i77_np.column_stack((0.2 + 0.03 * _i77_np.tile(_i77_np.arange(8), 6), -0.1 + 0.02 * _i77_np.repeat(_i77_np.arange(6), 8)))
        state = _i77_np.column_stack((depth, depth[:, None] * velocity))
        kind = geometry['arrays']['boundary_kind']
        rec = _i77_reconstruct(state, bed - datum, support, kind, _i77_np.zeros(len(kind)))
        _i77_np.testing.assert_allclose(rec['subcell_depth'].mean(axis=(1, 2)), depth, rtol=0.0, atol=5e-15)
        _i77_np.testing.assert_allclose(_i77_np.mean(rec['subcell_depth'][:, :, :, None] * rec['subcell_velocity'], axis=(1, 2)), state[:, 1:], rtol=0.0, atol=5e-15)
        coordinate = (_i77_np.arange(2) + 0.5) / 2 - 0.5
        x, z = _i77_np.meshgrid(coordinate, coordinate)
        uniform_eta = _i77_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        naive = _i77_np.maximum(uniform_eta[:, None, None] + rec['slope_x'][:, 0, None, None] * x + rec['slope_z'][:, 0, None, None] * z - support['subcell_bed_position_relative_m'], 0.0).mean(axis=(1, 2))
        self.assertGreater(float(abs(naive - depth).max()), 0.0001)

    def test_half_wet_uniform_lake_equilibrium(self):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i77_coarsen_cell_field
        from terrain_pipeline.shallow_water import linear_stage_independent_rhs as _i77_shallow_water_rhs
        canonical = 1350.0 + _i77_np.tile(_i77_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i77_np.arange(12)[:, None]
        fine_depth = _i77_np.maximum(1350.8 - canonical, 0.0)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            depth = fine_depth if factor == 1 else _i77_coarsen_cell_field(fine_depth, factor=factor)
            state = _i77_np.column_stack((depth.ravel(), _i77_np.zeros((bed.size, 2))))
            rhs, _ = _i77_shallow_water_rhs(state, bed - datum, support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i77_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            _i77_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-12)

    def test_flat_bed_arbitrary_cutoff_source_zero(self):
        from terrain_pipeline.shallow_water import linear_stage_independent_rhs as _i77_shallow_water_rhs
        for factor in (1, 2, 4):
            geometry, support, _ = self.geometry(_i77_np.zeros((12, 16)), factor)
            bed = geometry['arrays']['H2_m']
            rng = _i77_np.random.default_rng(34)
            depth = rng.uniform(0.0, 0.3, bed.size)
            depth[depth < 0.1] = 0.0
            state = _i77_np.column_stack((depth, rng.uniform(-0.02, 0.02, (bed.size, 2)) * depth[:, None]))
            rhs, witness = _i77_shallow_water_rhs(state, bed, support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i77_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            _i77_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)
            self.assertAlmostEqual(float(rhs[:, 0].sum()), 0.0, places=13)
            self.assertTrue(_i77_np.all((state + 0.01 * rhs)[:, 0] >= 0))

class ShallowWaterLinearStageDefaultTests(_i78_unittest.TestCase):

    def geometry(self, canonical, factor):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i78_coarsen_cell_field
        from terrain_pipeline.shallow_water import prepare_linear_stage_support as _i78_prepare_support
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i78_prepare_surface_geometry
        coarse = canonical if factor == 1 else _i78_coarsen_cell_field(canonical, factor=factor)
        bed = dict(arrays=dict(canonical_bed_center_m=canonical, H2_m=coarse), metadata=dict(spacing_m=float(factor)))
        support, datum = _i78_prepare_support(bed)
        geometry = _i78_prepare_surface_geometry(coarse, spacing_m=float(factor), origin_m_xz=[0.0, 0.0], source_identity='synthetic')
        geometry['arrays'].update(support)
        geometry['metadata']['hydraulic_datum_m'] = datum
        return (geometry, support, datum)

    def test_linear_stage_inversion_preserves_volume_and_momentum(self):
        from terrain_pipeline.fine_subgrid import stage_depths as _i78_stage_depths
        from terrain_pipeline.fine_subgrid import storage_stages as _i78_storage_stages
        from terrain_pipeline.shallow_water import reconstruct_linear_stage as _i78_reconstruct
        canonical = _i78_np.random.default_rng(30).uniform(0.0, 2.0, (12, 16))
        geometry, support, datum = self.geometry(canonical, 2)
        bed = geometry['arrays']['H2_m']
        eta = _i78_np.tile(0.8 + 0.15 * _i78_np.arange(8), (6, 1)).ravel()
        depth = _i78_stage_depths(eta, support['subcell_bed_relative_m'])
        velocity = _i78_np.column_stack((0.2 + 0.03 * _i78_np.tile(_i78_np.arange(8), 6), -0.1 + 0.02 * _i78_np.repeat(_i78_np.arange(6), 8)))
        state = _i78_np.column_stack((depth, depth[:, None] * velocity))
        kind = geometry['arrays']['boundary_kind']
        rec = _i78_reconstruct(state, bed - datum, support, kind, _i78_np.zeros(len(kind)))
        _i78_np.testing.assert_allclose(rec['subcell_depth'].mean(axis=(1, 2)), depth, rtol=0.0, atol=5e-15)
        _i78_np.testing.assert_allclose(_i78_np.mean(rec['subcell_depth'][:, :, :, None] * rec['subcell_velocity'], axis=(1, 2)), state[:, 1:], rtol=0.0, atol=5e-15)
        coordinate = (_i78_np.arange(2) + 0.5) / 2 - 0.5
        x, z = _i78_np.meshgrid(coordinate, coordinate)
        uniform_eta = _i78_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        naive = _i78_np.maximum(uniform_eta[:, None, None] + rec['slope_x'][:, 0, None, None] * x + rec['slope_z'][:, 0, None, None] * z - support['subcell_bed_position_relative_m'], 0.0).mean(axis=(1, 2))
        self.assertGreater(float(abs(naive - depth).max()), 0.0001)

    def test_half_wet_uniform_lake_equilibrium(self):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i78_coarsen_cell_field
        from terrain_pipeline.shallow_water import linear_stage_rhs as _i78_shallow_water_rhs
        canonical = 1350.0 + _i78_np.tile(_i78_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i78_np.arange(12)[:, None]
        fine_depth = _i78_np.maximum(1350.8 - canonical, 0.0)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry['arrays']['H2_m']
            depth = fine_depth if factor == 1 else _i78_coarsen_cell_field(fine_depth, factor=factor)
            state = _i78_np.column_stack((depth.ravel(), _i78_np.zeros((bed.size, 2))))
            rhs, _ = _i78_shallow_water_rhs(state, bed - datum, support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i78_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            _i78_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-12)

    def test_flat_bed_arbitrary_cutoff_source_zero(self):
        from terrain_pipeline.shallow_water import linear_stage_rhs as _i78_shallow_water_rhs
        for factor in (1, 2, 4):
            geometry, support, _ = self.geometry(_i78_np.zeros((12, 16)), factor)
            bed = geometry['arrays']['H2_m']
            rng = _i78_np.random.default_rng(34)
            depth = rng.uniform(0.0, 0.3, bed.size)
            depth[depth < 0.1] = 0.0
            state = _i78_np.column_stack((depth, rng.uniform(-0.02, 0.02, (bed.size, 2)) * depth[:, None]))
            rhs, witness = _i78_shallow_water_rhs(state, bed, support=support, spacing=float(factor), gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=_i78_np.zeros(2 * sum(bed.shape)), roughness=0.035, dt=0.01)
            _i78_np.testing.assert_allclose(witness['bed_source'], 0.0, rtol=0.0, atol=1e-14)
            self.assertAlmostEqual(float(rhs[:, 0].sum()), 0.0, places=13)
            self.assertTrue(_i78_np.all((state + 0.01 * rhs)[:, 0] >= 0))
