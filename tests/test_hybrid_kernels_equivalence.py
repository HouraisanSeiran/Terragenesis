"""R3 step 1: the new shallow/hybrid/special-terrain/surface kernels equal every old entry point bit for bit.

Old modules are only imported, never modified.  Arrays are compared with np.array_equal,
everything else with ==.  Volatile wall-clock/RSS fields are dropped.
"""
from terrain_pipeline.surface_identity import _plain as _merged_coast__plain
from terrain_pipeline.surface_identity import _plain as _merged_prepare__plain
from terrain_pipeline.surface_identity import _plain as _merged_mosaic__plain
from terrain_pipeline.surface_identity import _freeze as _merged_coast__freeze
from terrain_pipeline.surface_identity import _freeze as _merged_mosaic__freeze
from terrain_pipeline.surface_identity import geometry_identity as _merged_geometry_adaptive_geometry_identity
from terrain_pipeline.surface_identity import geometry_identity as _merged_io_geometry_identity
from builtins import ValueError as _merged_radau_HydraulicDiagnosticStop
from builtins import ValueError as _merged_radau_HydraulicExecutionFailure
from builtins import ValueError as _merged_hk_HydraulicDiagnosticStop
from builtins import ValueError as _merged_hk_HydraulicExecutionFailure
import collections
import hashlib
import inspect
import unittest
import numpy as np
from terrain_pipeline import hybrid_hydraulics as hk
from terrain_pipeline import shallow_water as sk
from terrain_pipeline import special_terrain as tk
from terrain_pipeline import surface_identity as fk
from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment
from terrain_pipeline.hybrid_hydraulics import accelerate_model
from tests.hybrid_hydraulics_fixtures import tiny_model as _plain_tiny_model
VOLATILE = frozenset(('elapsed_wall_seconds', 'actual_peak_rss_bytes', 'wall_seconds', 'wall_s'))

def tiny_model():
    """The radau/v5/v6/v7 section_slopes need FastSection bands, as the v8 driver provides."""
    return accelerate_model(_plain_tiny_model())

def same(a, b, path='root'):
    """Strict recursive equality: np.array_equal for arrays (dtype and shape too), == otherwise."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        assert isinstance(a, np.ndarray) and isinstance(b, np.ndarray), path
        assert a.dtype == b.dtype and a.shape == b.shape, path
        assert np.array_equal(a, b, equal_nan=True), path
    elif isinstance(a, dict) or hasattr(a, 'keys'):
        ka = {k for k in a if k not in VOLATILE}
        kb = {k for k in b if k not in VOLATILE}
        assert ka == kb, (path, ka ^ kb)
        for key in ka:
            same(a[key], b[key], path + '.' + str(key))
    elif isinstance(a, (list, tuple)):
        assert type(a) is type(b) and len(a) == len(b), path
        for index, (x, y) in enumerate(zip(a, b)):
            same(x, y, path + '[%d]' % index)
    elif isinstance(a, float) and a != a:
        assert b != b, path
    else:
        assert a == b, (path, a, b)

def body(function):
    """Source of a function without its (possibly renamed) def line."""
    return inspect.getsource(function).split('\n', 1)[1]

def experiment(scenario):
    return Experiment(scenario, 0.2, 0.05 if scenario == 'pulse' else 0, 0.05 if scenario == 'pulse' else 0, 0.1, (0.2,) * 3, (0, 0.05, 0.1, 0.2), max_step_s=0.02)

class HydraulicsKernelTests(unittest.TestCase):
    """make_run_experiment bound to radau / v5 / v6 identities == the three old 271-line run_experiment bodies."""

    def check(self, old, **overrides):
        kwargs = dict(schema=old.SCHEMA, numerical_version=old.NUMERICAL_VERSION, model_version=old.MODEL_VERSION, build_system=old.build_system, jacobian_policy=old.jacobian_policy, inventory_policy=old.inventory_policy, positivity_violation=old.positivity_violation, inventory_snapshot=old.inventory_snapshot, flux_snapshot=old.flux_snapshot, NonpositiveWaterTrial=old.NonpositiveWaterTrial, HydraulicExecutionFailure=old.HydraulicExecutionFailure, HydraulicDiagnosticStop=old.HydraulicDiagnosticStop)
        kwargs.update(overrides)
        run = hk.make_run_experiment(**kwargs)
        for scenario in ('pulse', 'reverse_tailwater'):
            for width in (0.0, 0.02):
                with self.subTest(old=old.__name__, scenario=scenario, width=width):
                    expected = old.run_experiment(tiny_model(), experiment(scenario), width)
                    actual = run(tiny_model(), experiment(scenario), width)
                    same(actual, expected)
        return run

    def test_radau_v5_v6_run_experiment(self):
        from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay
        replay = HydraulicsLegacyReplay()
        self.addCleanup(replay.close)
        for version in ('v6', 'v5'):
            self.check(replay.load('terrain_pipeline.hybrid_river_hydraulics_' + version))

    def test_kernel_defaults_equal_current_radau_policy(self):
        from terrain_pipeline import hybrid_hydraulics as radau
        run = hk.make_run_experiment(schema=radau.RADAU_SCHEMA, numerical_version=radau.NUMERICAL_VERSION, model_version=radau.MODEL_VERSION)
        same(run(tiny_model(), experiment('pulse'), 0.02), radau.radau_run_experiment(tiny_model(), experiment('pulse'), 0.02))

    def test_diagnostic_stop_and_guard_failure(self):
        from dataclasses import replace
        from terrain_pipeline import hybrid_hydraulics as radau
        run = hk.make_run_experiment(schema=radau.RADAU_SCHEMA, numerical_version=radau.NUMERICAL_VERSION, model_version=radau.MODEL_VERSION)
        for diagnostic, limit in ((0.075, 200000), (None, 1)):
            case = replace(experiment('pulse'), max_rhs_evaluations=limit)
            with self.assertRaises((_merged_radau_HydraulicDiagnosticStop, _merged_radau_HydraulicExecutionFailure)) as before:
                radau.radau_run_experiment(tiny_model(), case, 0.02, diagnostic)
            with self.assertRaises((_merged_hk_HydraulicDiagnosticStop, _merged_hk_HydraulicExecutionFailure)) as after:
                run(tiny_model(), case, 0.02, diagnostic)
            self.assertEqual(type(after.exception).__name__, type(before.exception).__name__)
            self.assertEqual(str(after.exception), str(before.exception))

    def test_helper_bodies_identical_to_every_old_copy(self):
        from terrain_pipeline import hybrid_hydraulics as radau
        from terrain_pipeline import hybrid_hydraulics as v4
        from terrain_pipeline import hybrid_hydraulics as v5
        from terrain_pipeline import hybrid_hydraulics as v6
        from terrain_pipeline import hybrid_hydraulics as v7
        copies = {'section_slopes': (radau, v6, v7), 'signed_flow_slopes': (radau, v6, v7), 'positivity_violation': (radau, v5, v6, v7), 'dense_positivity_violation': (radau, v5, v6), 'roof_contact_length': (radau, v4, v5, v6, v7), 'friction_state': (radau, v4, v5, v6, v7), 'inventory_snapshot': (radau, v5, v6, v7), 'flux_snapshot': (radau, v5, v6, v7), 'validate_transition': (radau, v4, v5, v6, v7), 'effective_conveyance': (radau, v4, v5, v6, v7), 'build_system': (radau, v6)}
        for name, modules in copies.items():
            for module in modules:
                with self.subTest(name=name, module=module.__name__):
                    self.assertEqual(inspect.getsource(getattr(hk, name)), inspect.getsource(getattr(module, name)))

    def test_helper_numeric_equality(self):
        from terrain_pipeline import hybrid_hydraulics as v6
        from terrain_pipeline import hybrid_hydraulics as v7
        model = tiny_model()
        heads = (0.2, 0.35, 0.05)
        for cell, head in zip(model.cells, heads):
            roof = hk.roof_contact_length(cell.section)
            self.assertEqual(roof, v6.roof_contact_length(cell.section))
            for width in (0.0, 0.02):
                same(hk.friction_state(cell, head, width, roof), v6.friction_state(cell, head, width, roof))
                new_work, old_work = (collections.defaultdict(int), collections.defaultdict(int))
                same(hk.section_slopes(cell, head, width, roof, new_work), v7.section_slopes(cell, head, width, roof, old_work))
                same(dict(new_work), dict(old_work))
                self.assertEqual(hk.effective_conveyance(cell, head, width), v6.effective_conveyance(cell, head, width))
        same(hk.signed_flow_slopes(0.3, 0.01, 1.0, 0.05), v7.signed_flow_slopes(0.3, 0.01, 1.0, 0.05))

class ShallowWaterKernelTests(unittest.TestCase):

    def geometry(self, canonical, factor):
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry
        from terrain_pipeline.fine_subgrid import coarsen_cell_field, prepare_subgrid_support
        coarse = canonical if factor == 1 else coarsen_cell_field(canonical, factor=factor)
        bed = dict(arrays=dict(canonical_bed_center_m=canonical, H2_m=coarse), metadata=dict(spacing_m=float(factor)))
        support, datum = prepare_subgrid_support(bed)
        geometry = prepare_surface_geometry(coarse, spacing_m=float(factor), origin_m_xz=[0.0, 0.0], source_identity='synthetic')
        geometry['arrays'].update(support)
        geometry['metadata']['hydraulic_datum_m'] = datum
        return (geometry, support, datum, bed)

    def case(self, seed, factor=2, dry=True):
        canonical = np.random.default_rng(seed).uniform(0.0, 2.0, (12, 16))
        geometry, support, datum, bed = self.geometry(canonical, factor)
        coarse = geometry['arrays']['H2_m']
        rng = np.random.default_rng(seed + 1)
        depth = rng.uniform(0.0, 0.6, coarse.size)
        if dry:
            depth[depth < 0.2] = 0.0
        state = np.column_stack((depth, rng.uniform(-0.02, 0.02, (coarse.size, 2)) * depth[:, None]))
        kind = rng.integers(0, 3, 2 * sum(coarse.shape)).astype(np.int64)
        kind[:5] = 2
        args = dict(spacing=float(factor), gravity=9.81, boundary_kind=kind, tailwater=rng.uniform(0.0, 1.0, len(kind)), roughness=0.035, dt=0.01)
        return (geometry, support, datum, bed, coarse, state, args)

    def test_face_reconstruction_v5_v6(self):
        from terrain_pipeline import shallow_water as s5
        from terrain_pipeline import shallow_water as s6
        from terrain_pipeline.fine_subgrid import storage_stages
        for seed in (3, 11):
            geometry, support, datum, bed, coarse, state, args = self.case(seed)
            stage = storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
            velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            for new, old in ((sk.reconstruct_independent, s5._single_domain_shallow_water_support_mechanism_5_reconstruct), (sk.reconstruct_dry_neighbor, s6._single_domain_shallow_water_support_mechanism_6_reconstruct)):
                same(new(stage, velocity, state[:, 0], coarse, support, args['boundary_kind'], args['tailwater']), old(stage, velocity, state[:, 0], coarse, support, args['boundary_kind'], args['tailwater']))

    def test_segmented_rhs_v5_v6(self):
        from terrain_pipeline import shallow_water as s5
        from terrain_pipeline import shallow_water as s6
        for seed in (4, 12):
            for factor in (1, 2):
                geometry, support, datum, bed, coarse, state, args = self.case(seed, factor)
                for reconstruct, old in ((sk.reconstruct_independent, s5), (sk.reconstruct_dry_neighbor, s6)):
                    rhs = sk.make_segmented_rhs(reconstruct)
                    same(rhs(state, coarse - datum, support=support, **args), old.shallow_water_rhs(state, coarse - datum, support=support, **args))

    def test_linear_stage_v8_v9(self):
        from terrain_pipeline import shallow_water as r8
        from terrain_pipeline import shallow_water as r9
        from terrain_pipeline import shallow_water as s8
        from terrain_pipeline import shallow_water as s9
        for seed in (5, 13):
            for factor in (1, 2):
                canonical = np.random.default_rng(seed).uniform(0.0, 2.0, (12, 16))
                geometry, _, datum_unused, bed_dict = self.geometry(canonical, factor)
                coarse = geometry['arrays']['H2_m']
                for old_r, old_s, independent in ((r8, s8, True), (r9, s9, False)):
                    support_old, datum_old = old_r.prepare_support(bed_dict)
                    support_new, datum_new = sk.prepare_support(bed_dict)
                    same(support_new, support_old)
                    self.assertEqual(datum_new, datum_old)
                    boundary_kind = geometry['arrays']['boundary_kind']
                    rng = np.random.default_rng(seed + 7)
                    depth = rng.uniform(0.0, 0.3, coarse.size)
                    depth[depth < 0.1] = 0.0
                    state = np.column_stack((depth, rng.uniform(-0.02, 0.02, (coarse.size, 2)) * depth[:, None]))
                    tail = rng.uniform(0.0, 1.0, len(boundary_kind))
                    inner = sk.reconstruct_independent if independent else sk.reconstruct_dry_neighbor
                    new_reconstruct = sk.make_reconstruct(inner)
                    same(new_reconstruct(state, coarse - datum_old, support_old, boundary_kind, tail), old_r.reconstruct(state, coarse - datum_old, support_old, boundary_kind, tail))
                    reconstruction = old_r.reconstruct(state, coarse - datum_old, support_old, boundary_kind, tail)
                    cells = np.arange(coarse.size)
                    same(sk.face_fields(reconstruction, cells, 0, 1, factor), old_r.face_fields(reconstruction, cells, 0, 1, factor))
                    same(sk.internal_bed_pressure(reconstruction, support_old, spacing=float(factor), gravity=9.81), old_r.internal_bed_pressure(reconstruction, support_old, spacing=float(factor), gravity=9.81))
                    rhs = sk.make_linear_stage_rhs(new_reconstruct, sk.face_fields, sk.internal_bed_pressure)
                    args = dict(support=support_old, spacing=float(factor), gravity=9.81, boundary_kind=boundary_kind, tailwater=tail, roughness=0.035, dt=0.01)
                    same(rhs(state, coarse - datum_old, **args), old_s.shallow_water_rhs(state, coarse - datum_old, **args))

    def test_advance_shallow_water_v5_v6(self):
        from terrain_pipeline import shallow_water as s5
        from terrain_pipeline import shallow_water as s6
        from terrain_pipeline import shallow_water as w5
        from terrain_pipeline import shallow_water as w6
        from terrain_pipeline.surface_hydraulics import SurfaceBudget
        for old_w, old_s, reconstruct in ((w5, s5, sk.reconstruct_independent), (w6, s6, sk.reconstruct_dry_neighbor)):
            advance = sk.make_advance_shallow_water(old_s.MODEL, sk.make_segmented_rhs(reconstruct))
            results = []
            for function in (old_w.advance_shallow_water, advance):
                geometry = self.geometry(np.zeros((8, 40)), 2)[0]
                bed = geometry['arrays']['H2_m']
                rows, columns = bed.shape
                geometry['arrays']['boundary_kind'][rows:2 * rows] = 2
                tail = np.ones(2 * (rows + columns))
                tail[rows:2 * rows] = 1.5
                results.append(function(geometry, initial_depth_m=np.ones_like(bed), forcing_interval_s=1.0, intervals=1, forcing_provider=lambda i: np.zeros_like(bed), boundary_stage_provider=lambda i: tail, source_identity='synthetic', forcing_identity='reservoir-pulse', budget=SurfaceBudget(max_dt_s=0.025, max_snapshots=3, max_duration_s=1.0), snapshot_interval_s=1.0, interval_observer=lambda packet: None, momentum_observer=lambda packet: None))
            same(results[1], results[0])

class SpecialTerrainKernelTests(unittest.TestCase):

    def test_origin_normalizers(self):
        from terrain_pipeline import hybrid_geometry as rock
        from terrain_pipeline import special_terrain as sink
        from terrain_pipeline import special_terrain as uluru
        from terrain_pipeline import special_terrain as pillars
        good = [(1, 2, 3), np.array([4.0, 5.0, 6.0]), [0, 0, 0]]
        bad = [(1, 2), (np.nan, 0, 0), (0, 0, np.inf), [[1, 2, 3]]]
        for old in (rock._origin, sink.as_origin, tk.as_origin):
            for value in good:
                same(old(value), tk.as_origin(value))
            for value in bad:
                with self.assertRaises(ValueError) as expected:
                    old(value)
                with self.assertRaises(ValueError) as actual:
                    tk.as_origin(value)
                self.assertEqual(str(actual.exception), str(expected.exception))
        for module in (uluru, pillars):
            new = tk.make_origin_normalizer(module.DEFAULT_ORIGIN)
            same(new(None), module._origin(None))
            for value in good:
                same(new(value), module._origin(value))
            for value in bad:
                with self.assertRaises(ValueError) as expected:
                    module._origin(value)
                with self.assertRaises(ValueError) as actual:
                    new(value)
                self.assertEqual(str(actual.exception), str(expected.exception))

    def test_inside_by_winding(self):
        from terrain_pipeline import special_terrain as uluru
        from terrain_pipeline import special_terrain as pillars
        vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        triangles = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
        record = {'vertices_local_xyz_m': vertices, 'triangles': triangles}
        origin = np.zeros(3)
        for module in (uluru, pillars):
            new = tk.make_inside_by_winding(module.winding_number)
            for point in ((0.1, 0.1, 0.1), (2.0, 2.0, 2.0), (-1.0, 0.2, 0.2), (0.2, 0.2, 0.2)):
                self.assertEqual(new(record, np.array(point), origin), module.inside_by_winding(record, np.array(point), origin))

class SurfaceKernelTests(unittest.TestCase):

    def test_plain_freeze(self):
        from types import MappingProxyType
        from terrain_pipeline import surface_domain as coast
        from terrain_pipeline import surface_domain as prepare
        from terrain_pipeline import surface_domain as mosaic
        value = {'a': (1, [2, {'b': MappingProxyType({'c': (3,)})}]), 'd': np.arange(6.0).reshape(2, 3), 'e': 'x'}
        for old in (_merged_coast__plain, _merged_prepare__plain, _merged_mosaic__plain):
            same(fk._plain(value), old(value))
        for old in (_merged_coast__freeze, _merged_mosaic__freeze):
            frozen_old, frozen_new = (old(value), fk._freeze(value))
            self.assertEqual(type(frozen_old), type(frozen_new))
            same(fk._plain(frozen_new), fk._plain(frozen_old))
            self.assertFalse(frozen_new['d'].flags.writeable)
            same(frozen_new['d'], frozen_old['d'])

    def test_geometry_identity(self):
        from terrain_pipeline import adaptive_mesh as geometry
        from terrain_pipeline import adaptive_mesh as io
        rng = np.random.default_rng(1)
        arrays = {'b': rng.normal(size=(3, 4)), 'a': np.arange(5, dtype=np.int32), 'c': rng.integers(0, 9, (2, 2))}
        metadata = {'spacing_m': 2.0, 'name': 'x', 'nested': {'k': [1, 2]}}
        expected = hashlib.sha256()
        for function in (_merged_geometry_adaptive_geometry_identity, _merged_io_geometry_identity, fk.geometry_identity):
            self.assertEqual(function(arrays, metadata), _merged_geometry_adaptive_geometry_identity(arrays, metadata))

    def test_source_grid(self):
        from terrain_pipeline.surface_rivers import metric_domain_coupled as coupled
        from terrain_pipeline.surface_rivers import metric_domain_sediment as sediment
        good = [None, 0.0, 2, 1.5, np.full((5, 5), 3.0), np.arange(25.0).reshape(5, 5), [[1.0] * 5] * 5]
        bad = [True, np.bool_(True), -1.0, float('nan'), np.inf, np.ones((4, 5)), np.full((5, 5), -2.0), np.full((5, 5), np.nan)]
        for old in (coupled._source_grid, sediment._source_grid):
            for value in good:
                same(fk.source_grid(value, 0.25, 4), old(value, 0.25, 4))
            for value in bad:
                try:
                    old(value, 0.25, 4)
                except Exception as error:
                    with self.assertRaises(type(error)) as raised:
                        fk.source_grid(value, 0.25, 4)
                    self.assertEqual(str(raised.exception), str(error))
                else:
                    self.fail('old implementation accepted %r' % (value,))
if __name__ == '__main__':
    unittest.main()
