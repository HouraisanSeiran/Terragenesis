"""Consolidated test_surface_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
import unittest as _i36_unittest
import numpy as _i36_np
import tempfile as _i36_tempfile
from pathlib import Path as _i36_Path
import tempfile as _i37_tempfile
import unittest as _i37_unittest
from pathlib import Path as _i37_Path
import numpy as _i37_np
from dataclasses import fields as _i38_fields
from dataclasses import replace as _i38_replace
import hashlib as _i38_hashlib
import io as _i38_io
import json as _i38_json
from pathlib import Path as _i38_Path
import tempfile as _i38_tempfile
import unittest as _i38_unittest
from unittest.mock import patch as _i38_patch
import warnings as _i38_warnings
import zipfile as _i38_zipfile
import numpy as _i38_np
from terrain_pipeline import surface_hydraulics as _i38_hydro
import unittest as _i39_unittest
import numpy as _i39_np
from scipy.integrate import solve_ivp as _i39_solve_ivp
from copy import deepcopy as _i40_deepcopy
import hashlib as _i40_hashlib
import math as _i40_math
import subprocess as _i40_subprocess
import sys as _i40_sys
from pathlib import Path as _i40_Path
import tempfile as _i40_tempfile
import unittest as _i40_unittest
import numpy as _i40_np
from dataclasses import replace as _i41_replace
from copy import deepcopy as _i41_deepcopy
import unittest as _i41_unittest
import numpy as _i41_np
from terrain_pipeline import surface_hydraulics as _i41_surface
from dataclasses import replace as _i42_replace
import unittest as _i42_unittest
import numpy as _i42_np
from terrain_pipeline import surface_hydraulics as _i42_base
from terrain_pipeline import surface_hydraulics as _i42_accelerated
import json as _i43_json
from pathlib import Path as _i43_Path
import tempfile as _i43_tempfile
import unittest as _i43_unittest
import numpy as _i43_np
from tools.verify_surface_hydraulics import compare as _i43_compare
import unittest as _i44_unittest
import unittest as _i45_unittest
import numpy as _i45_np
import unittest as _i46_unittest
import numpy as _i46_np
CATEGORY = 'B'

def conservative_plan():
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i36_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i36_plan_channel
    shape = (5, 5)
    height = _i36_np.full(shape, 10.0)
    receiver = _i36_np.full(25, -1, dtype=_i36_np.int64)
    for source, target in ((6, 11), (8, 13), (11, 12), (13, 12), (12, 17), (17, 22)):
        receiver[source] = target
    outlets = (receiver == -1).reshape(shape)
    order = []
    seen = set()

    def visit(cell):
        if cell in seen:
            return
        if receiver[cell] >= 0:
            visit(int(receiver[cell]))
        seen.add(cell)
        order.append(cell)
    for cell in range(25):
        visit(cell)
    q = _i36_np.zeros(25)
    q[[6, 8]] = 0.1
    for cell in order[::-1]:
        if receiver[cell] >= 0:
            q[receiver[cell]] += q[cell]
    return _i36_plan_channel(height, receiver, _i36_np.array(order, dtype=_i36_np.int64), outlets, q.reshape(shape), 1.0, 1.0, 0.0, 0.0, 0.0, 'conservative-reroute', _i36_ChannelRecipe(start_discharge_m3_s=0.05, reference_discharge_m3_s=0.1, reference_width_m=2.0, min_width_m=2.0, max_width_m=2.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, max_cut_m=4.0))

class ChannelRerouteTests(_i36_unittest.TestCase):

    def test_explicit_reroute_recomputes_graph_and_q(self):
        from terrain_pipeline.surface_hydraulics import RerouteRecipe as _i36_RerouteRecipe
        from terrain_pipeline.surface_hydraulics import reroute_channel as _i36_reroute_channel
        plan = conservative_plan()
        domain = _i36_np.ones((5, 5), bool)
        protected = _i36_np.zeros((5, 5), bool)
        protected[1, 2] = True
        result = _i36_reroute_channel(plan, (1, 1), (3, 2), domain, protected, _i36_RerouteRecipe(max_path_cells=10))
        path = result['path_grid_zx']
        self.assertEqual(path[0], [1, 1])
        self.assertEqual(path[-1], [3, 2])
        self.assertNotIn([1, 2], path)
        self.assertEqual(result['plan']['arrays']['discharge_m3_s'][3, 2], 0.2)
        self.assertNotEqual(result['plan']['identity_sha256'], plan['identity_sha256'])

    def test_protected_end_and_no_path_rejected(self):
        from terrain_pipeline.surface_hydraulics import reroute_channel as _i36_reroute_channel
        plan = conservative_plan()
        domain = _i36_np.ones((5, 5), bool)
        protected = _i36_np.zeros((5, 5), bool)
        protected[1, 1] = True
        with self.assertRaises(ValueError):
            _i36_reroute_channel(plan, (1, 1), (3, 2), domain, protected)

    def test_rerouted_plan_runs_joint_diagnostic(self):
        from terrain_pipeline.surface_hydraulics import reroute_channel as _i36_reroute_channel
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i36_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import prepare_surface_network as _i36_prepare_surface_network
        from terrain_pipeline.surface_domain import save_surface_network as _i36_save_surface_network
        from terrain_pipeline.surface_domain import load_surface_network as _i36_load_surface_network
        from terrain_pipeline.channel_geometry import SectionRecipe as _i36_SectionRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i36_StageRecipe
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i36_InundationRecipe
        plan = conservative_plan()
        domain = _i36_np.ones((5, 5), bool)
        protected = _i36_np.zeros((5, 5), bool)
        protected[1, 2] = True
        rerouted = _i36_reroute_channel(plan, (1, 1), (3, 2), domain, protected)
        fine_shape = (9, 9)
        fine_domain = _i36_np.ones(fine_shape, bool)
        fine_protected = _i36_np.zeros(fine_shape, bool)
        fine_protected[2, 4] = True
        legal = _i36_np.zeros(fine_shape, bool)
        legal[-1, 3:6] = True
        result = _i36_prepare_surface_network(rerouted['plan'], 0.0, 0.0, 0.5, 0.5, fine_shape, fine_domain, fine_protected, legal, _i36_np.array([9.8]), _i36_SectionRecipe(), _i36_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i36_InundationRecipe(max_lateral_reach_m=5.0), _i36_SurfaceNetworkBudget(4.0, 100.0, 100.0))
        self.assertIn('joint_blockers', result['summary'])
        self.assertEqual(result['summary']['inundation']['channel_seed_nodes'], int(result['arrays']['channel_seed_mask'].sum()))
        self.assertEqual(result['status'], 'prepared')
        self.assertFalse(any(result['summary']['joint_blockers'].values()))
        with _i36_tempfile.TemporaryDirectory() as directory:
            path = _i36_Path(directory) / 'rerouted.npz'
            _i36_save_surface_network(result, path)
            self.assertEqual(_i36_load_surface_network(path)['identity_sha256'], result['identity_sha256'])
        protected[1, 1] = False
        domain[2, :] = False
        with self.assertRaises(ValueError):
            _i36_reroute_channel(plan, (1, 1), (3, 2), domain, protected)

def confluence_plan(isolated_basin=False):
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i37_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i37_plan_channel
    from terrain_pipeline.drainage import grid_mesh as _i37_grid_mesh
    from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import graph_connection as _i37_graph_connection
    height = _i37_np.full((7, 7), 10.0)
    height[1:6, 2:5] = 5.0
    height[0, 3] = 10.0
    height[6, 3] = 4.0
    if isolated_basin:
        height[4, 1] = 3.0
        height[4, 2] = 10.0
    receiver = _i37_np.full(49, -1, dtype=_i37_np.int64)
    outlets = _i37_np.ones((7, 7), bool)
    mesh = _i37_grid_mesh(height.shape, dx_m=10.0)
    for donor, target in ((9, 17), (11, 17), (17, 24), (24, 31), (31, 38), (38, 45)):
        path = _i37_graph_connection(donor, target, 7, shape=height.shape, mesh=mesh)
        for first, second in zip(path, path[1:]):
            receiver[first[0] * 7 + first[1]] = second[0] * 7 + second[1]
    outlets[:] = (receiver < 0).reshape(height.shape)
    order = list(_i37_np.flatnonzero(outlets))
    position = 0
    while position < len(order):
        order.extend(_i37_np.flatnonzero(receiver == order[position]).tolist())
        position += 1
    order = _i37_np.asarray(order, _i37_np.int64)
    q = _i37_np.full((7, 7), 0.01)
    q.ravel()[receiver >= 0] = 0.1
    q.flat[45] = 0.1
    plan = _i37_plan_channel(height, receiver, order, outlets, q, 10.0, 10.0, 0.0, 0.0, 0.0, 'synthetic-confluence-basin' if isolated_basin else 'synthetic-confluence', _i37_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=8.0, min_width_m=8.0, max_width_m=8.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, max_cut_m=4.0, min_bed_slope_m_per_m=1e-05))
    return plan

def full_sections(plan):
    from terrain_pipeline.channel_geometry import SectionRecipe as _i37_SectionRecipe
    from terrain_pipeline.channel_geometry import evaluate_sections as _i37_evaluate_sections
    return _i37_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (61, 61), _i37_np.zeros((61, 61), bool), _i37_SectionRecipe())

class StageInundationTests(_i37_unittest.TestCase):

    def test_full_confluence_and_lowland_success(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i37_InundationRecipe
        from terrain_pipeline.surface_hydraulics import evaluate_inundation as _i37_evaluate_inundation
        from terrain_pipeline.surface_hydraulics import slice_inundation as _i37_slice_inundation
        from terrain_pipeline.surface_hydraulics import assess_joint as _i37_assess_joint
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i37_StageRecipe
        from terrain_pipeline.surface_hydraulics import solve_stage as _i37_solve_stage
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = _i37_solve_stage(plan, _i37_np.array([5.2]), _i37_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0))
        domain = _i37_np.ones((61, 61), bool)
        protected = _i37_np.zeros((61, 61), bool)
        legal = _i37_np.zeros((61, 61), bool)
        legal[-1, 27:34] = True
        flood = _i37_evaluate_inundation(plan, sections, stage, domain, protected, legal, _i37_InundationRecipe(max_lateral_reach_m=15.0))
        self.assertTrue(stage['summary']['stage_feasible'])
        self.assertGreater(flood['summary']['wet_nodes'], 0)
        self.assertGreater(flood['summary']['overbank_nodes'], 0)
        self.assertTrue(flood['summary']['legal_outlet_wet'])
        self.assertTrue(_i37_assess_joint(plan, sections, stage, flood)['pass'])
        left = _i37_slice_inundation(flood, slice(None), slice(0, 31))
        _i37_np.testing.assert_array_equal(left['wet_mask'], flood['arrays']['wet_mask'][:, :31])

    def test_fixed_outlet_and_depth_limit_fail_without_raising_unbounded_water(self):
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i37_StageRecipe
        from terrain_pipeline.surface_hydraulics import solve_stage as _i37_solve_stage
        plan = confluence_plan()
        stage = _i37_solve_stage(plan, _i37_np.array([20.0]), _i37_StageRecipe(max_depth_m=2.0))
        self.assertFalse(stage['summary']['stage_feasible'])
        self.assertGreater(stage['summary']['invalid_depth_nodes'], 0)
        self.assertEqual(stage['arrays']['stage_m'][6, 3], 20.0)

    def test_protection_and_high_ground_are_not_wet(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i37_InundationRecipe
        from terrain_pipeline.surface_hydraulics import evaluate_inundation as _i37_evaluate_inundation
        from terrain_pipeline.surface_hydraulics import assess_joint as _i37_assess_joint
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i37_StageRecipe
        from terrain_pipeline.surface_hydraulics import solve_stage as _i37_solve_stage
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = _i37_solve_stage(plan, _i37_np.array([4.2]), _i37_StageRecipe(max_depth_m=3.0))
        domain = _i37_np.ones((61, 61), bool)
        protected = _i37_np.zeros((61, 61), bool)
        protected[30, 30] = True
        legal = _i37_np.zeros((61, 61), bool)
        legal[-1, 30] = True
        flood = _i37_evaluate_inundation(plan, sections, stage, domain, protected, legal, _i37_InundationRecipe(max_lateral_reach_m=5.0))
        self.assertFalse(flood['arrays']['wet_mask'][30, 30])
        self.assertGreater(flood['summary']['protected_conflict_nodes'], 0)
        self.assertFalse(flood['arrays']['wet_mask'][0, 0])
        self.assertFalse(_i37_assess_joint(plan, sections, stage, flood)['pass'])

    def test_isolated_low_basin_behind_ridge_stays_dry(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i37_InundationRecipe
        from terrain_pipeline.surface_hydraulics import evaluate_inundation as _i37_evaluate_inundation
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i37_StageRecipe
        from terrain_pipeline.surface_hydraulics import solve_stage as _i37_solve_stage
        plan = confluence_plan(isolated_basin=True)
        sections = full_sections(plan)
        stage = _i37_solve_stage(plan, _i37_np.array([5.2]), _i37_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0))
        domain = _i37_np.ones((61, 61), bool)
        empty = _i37_np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        flood = _i37_evaluate_inundation(plan, sections, stage, domain, empty, legal, _i37_InundationRecipe(max_lateral_reach_m=30.0))
        self.assertLess(sections['arrays']['bounded_surface_m'][40, 10], stage['arrays']['stage_m'][4, 3])
        self.assertFalse(flood['arrays']['wet_mask'][40, 10])
        self.assertTrue(flood['arrays']['wet_mask'][30, 30])

    def test_save_reload_and_missing_legal_outlet(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i37_InundationRecipe
        from terrain_pipeline.surface_hydraulics import evaluate_inundation as _i37_evaluate_inundation
        from terrain_pipeline.surface_hydraulics import load_inundation as _i37_load_inundation
        from terrain_pipeline.surface_hydraulics import save_inundation as _i37_save_inundation
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i37_StageRecipe
        from terrain_pipeline.surface_hydraulics import load_stage as _i37_load_stage
        from terrain_pipeline.surface_hydraulics import save_stage as _i37_save_stage
        from terrain_pipeline.surface_hydraulics import solve_stage as _i37_solve_stage
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = _i37_solve_stage(plan, _i37_np.array([4.2]), _i37_StageRecipe())
        domain = _i37_np.ones((61, 61), bool)
        empty = _i37_np.zeros((61, 61), bool)
        flood = _i37_evaluate_inundation(plan, sections, stage, domain, empty, empty, _i37_InundationRecipe(max_lateral_reach_m=5.0))
        self.assertFalse(flood['summary']['coverage_complete'])
        with _i37_tempfile.TemporaryDirectory() as directory:
            stage_path = _i37_Path(directory) / 'stage.npz'
            flood_path = _i37_Path(directory) / 'flood.npz'
            _i37_save_stage(stage, stage_path)
            _i37_save_inundation(flood, flood_path)
            self.assertEqual(_i37_load_stage(stage_path)['identity_sha256'], stage['identity_sha256'])
            self.assertEqual(_i37_load_inundation(flood_path)['identity_sha256'], flood['identity_sha256'])

    def test_joint_rejects_tampered_section_and_flood_summary(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i37_InundationRecipe
        from terrain_pipeline.surface_hydraulics import evaluate_inundation as _i37_evaluate_inundation
        from terrain_pipeline.surface_hydraulics import assess_joint as _i37_assess_joint
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i37_StageRecipe
        from terrain_pipeline.surface_hydraulics import solve_stage as _i37_solve_stage
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = _i37_solve_stage(plan, _i37_np.array([5.2]), _i37_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0))
        full = _i37_np.ones((61, 61), bool)
        empty = _i37_np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        flood = _i37_evaluate_inundation(plan, sections, stage, full, empty, legal, _i37_InundationRecipe(max_lateral_reach_m=15.0))
        changed = dict(sections)
        changed['arrays'] = dict(sections['arrays'])
        changed['arrays']['bounded_surface_m'] = sections['arrays']['bounded_surface_m'].copy()
        changed['arrays']['bounded_surface_m'][20, 30] -= 0.1
        with self.assertRaisesRegex(ValueError, 'section arrays differ'):
            _i37_assess_joint(plan, changed, stage, flood)
        with self.assertRaisesRegex(ValueError, 'bounded surface differs'):
            _i37_evaluate_inundation(plan, changed, stage, full, empty, legal, _i37_InundationRecipe(max_lateral_reach_m=15.0))
        changed_flood = dict(flood)
        changed_flood['summary'] = dict(flood['summary'])
        changed_flood['summary']['coverage_complete'] = False
        with self.assertRaisesRegex(ValueError, 'coverage summary mismatch'):
            _i37_assess_joint(plan, sections, stage, changed_flood)

def graph_case(steps=3, upstream_q=1.0, tailwater=0.0):
    local = _i38_np.zeros((steps, 3))
    local[:, 0] = upstream_q
    boundary = _i38_np.zeros((steps + 1, 3))
    boundary[:, 2] = tailwater
    return _i38_hydro.HydraulicsInput(bed_m=_i38_np.zeros(3), area_m2=_i38_np.full(3, 10.0), initial_stage_m=_i38_np.array([0.0, 0.0, tailwater]), edges=_i38_np.array([[0, 1], [1, 2]], dtype=_i38_np.int64), conductance_m2_s=_i38_np.ones(2), local_q_m3_s=local, boundary_mask=_i38_np.array([False, False, True]), boundary_stage_m=boundary, dt_s=1.0, max_depth_m=10.0, valid_mask=_i38_np.ones(3, dtype=bool), protected_mask=_i38_np.zeros(3, dtype=bool), coords_m=_i38_np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]), source='engineered-independent-three-node-benchmark', datum='local-bed-zero-metres', coords='local Cartesian (x,z), metres')

def rewrite_bundle(path, *, metadata=None, array_name=None, payload=None, extra=None):
    with _i38_zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    if metadata is not None:
        members['metadata.json'] = metadata
    if array_name is not None:
        members[array_name] = payload
    with _i38_zipfile.ZipFile(path, 'w', compression=_i38_zipfile.ZIP_STORED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
        if extra is not None:
            with _i38_warnings.catch_warnings():
                _i38_warnings.simplefilter('ignore', UserWarning)
                archive.writestr(*extra)

class DynamicSurfaceHydraulicsTests(_i38_unittest.TestCase):

    def test_two_reach_delay_independent_analytic(self):
        result = _i38_hydro.evaluate(graph_case())
        _i38_np.testing.assert_allclose(result.stage_m, [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.19, 0.01, 0.0], [0.272, 0.027, 0.0]])
        _i38_np.testing.assert_allclose(result.qedges_m3_s, [[0.0, 0.0], [0.1, 0.0], [0.18, 0.01]])
        _i38_np.testing.assert_allclose(result.storage_m3.sum(axis=1), [0.0, 1.0, 2.0, 2.99])
        _i38_np.testing.assert_allclose(result.ledger_m3[:, 2], [0.0, 0.0, -0.01])
        self.assertEqual(result.committed_steps, 3)

    def test_tailwater_reverse_signed_flux_independent_analytic(self):
        result = _i38_hydro.evaluate(graph_case(upstream_q=0.0, tailwater=1.0))
        _i38_np.testing.assert_allclose(result.stage_m, [[0.0, 0.0, 1.0], [0.0, 0.1, 1.0], [0.01, 0.18, 1.0], [0.027, 0.245, 1.0]])
        _i38_np.testing.assert_allclose(result.qedges_m3_s, [[0.0, -1.0], [-0.1, -0.9], [-0.17, -0.82]])
        _i38_np.testing.assert_allclose(result.storage_m3.sum(axis=1), [0.0, 1.0, 1.9, 2.72])
        _i38_np.testing.assert_allclose(result.ledger_m3[:, 2], [1.0, 0.9, 0.82])
        _i38_np.testing.assert_array_equal(result.storage_m3[:, 2], 0.0)

    def test_tailwater_two_metres_and_n_next_index(self):
        result = _i38_hydro.evaluate(graph_case(upstream_q=0.0, tailwater=2.0))
        _i38_np.testing.assert_allclose(result.stage_m[:, :2], [[0.0, 0.0], [0.0, 0.2], [0.02, 0.36], [0.054, 0.49]])
        inputs = graph_case(upstream_q=0.0)
        boundary = inputs.boundary_stage_m.copy()
        boundary[1:, 2] = 2.0
        changed = _i38_hydro.evaluate(_i38_replace(inputs, boundary_stage_m=boundary))
        _i38_np.testing.assert_allclose(changed.qedges_m3_s[0], [0.0, 0.0])
        _i38_np.testing.assert_allclose(changed.stage_m[1], [0.0, 0.0, 2.0])
        _i38_np.testing.assert_allclose(changed.qedges_m3_s[1], [0.0, -2.0])

    def test_steady_analytic(self):
        inputs = _i38_replace(graph_case(steps=12), initial_stage_m=_i38_np.array([2.0, 1.0, 0.0]))
        result = _i38_hydro.evaluate(inputs)
        _i38_np.testing.assert_allclose(result.stage_m, _i38_np.tile([2.0, 1.0, 0.0], (13, 1)))
        _i38_np.testing.assert_allclose(result.qedges_m3_s, 1.0)
        _i38_np.testing.assert_allclose(result.ledger_m3[:, 1:3], _i38_np.tile([1.0, -1.0], (12, 1)))

    def test_zero_q_equilibrium(self):
        inputs = _i38_replace(graph_case(upstream_q=0.0, tailwater=1.0), initial_stage_m=_i38_np.ones(3))
        result = _i38_hydro.evaluate(inputs)
        _i38_np.testing.assert_array_equal(result.qedges_m3_s, 0.0)
        _i38_np.testing.assert_array_equal(result.stage_m, 1.0)
        _i38_np.testing.assert_array_equal(result.ledger_m3[:, 4:], 0.0)

    def test_volume_conservation_closed_and_signed_local(self):
        inputs = _i38_replace(graph_case(steps=25, upstream_q=0.0), boundary_mask=_i38_np.zeros(3, dtype=bool), initial_stage_m=_i38_np.array([2.0, 1.0, 0.5]))
        local = inputs.local_q_m3_s.copy()
        local[:, 0] = 0.2
        local[:, 2] = -0.1
        result = _i38_hydro.evaluate(_i38_replace(inputs, local_q_m3_s=local))
        _i38_np.testing.assert_allclose(result.storage_m3.sum(axis=1), 35.0 + 0.1 * _i38_np.arange(26))
        _i38_np.testing.assert_allclose(result.ledger_m3[:, 2], 0.0)
        _i38_np.testing.assert_allclose(result.ledger_m3[:, 5], 0.0, atol=1e-12)

    def test_different_beds_negative_storage_rejects_original_step(self):
        inputs = _i38_replace(graph_case(upstream_q=0.0), bed_m=_i38_np.array([2.0, 0.0, 0.0]), initial_stage_m=_i38_np.array([2.0, 0.0, 0.0]))
        result = _i38_hydro.evaluate(inputs)
        self.assertEqual((result.status, result.committed_steps), ('failed', 0))
        self.assertEqual(result.failed_step.reason, 'negative_depth')
        _i38_np.testing.assert_array_equal(result.storage_m3, [[0.0, 0.0, 0.0]])
        _i38_np.testing.assert_allclose(result.failed_step.next_storage_m3, [-2.0, 2.0, 0.0])
        self.assertEqual(result.ledger_m3.shape, (0, 6))
        self.assertTrue(_i38_hydro.validate(result)['valid'])

    def test_signed_withdrawal_failure_retains_prefix_and_failed_ledger(self):
        inputs = graph_case()
        local = inputs.local_q_m3_s.copy()
        local[1, 0] = -20.0
        result = _i38_hydro.evaluate(_i38_replace(inputs, local_q_m3_s=local))
        self.assertEqual((result.status, result.committed_steps), ('failed', 1))
        self.assertEqual(result.failed_step.step_n, 1)
        self.assertEqual(len(result.ledger_m3), 1)
        self.assertEqual(result.failed_step.ledger_m3[1], -20.0)
        _i38_np.testing.assert_array_equal(result.failed_step.previous_stage_m, result.stage_m[-1])
        self.assertLess(result.failed_step.next_storage_m3[0], 0.0)

    def test_maxdepth_rejects_without_clamp_or_dt_change(self):
        inputs = _i38_replace(graph_case(), max_depth_m=0.15)
        result = _i38_hydro.evaluate(inputs)
        self.assertEqual((result.status, result.committed_steps), ('failed', 1))
        self.assertEqual(result.failed_step.reason, 'max_depth')
        self.assertAlmostEqual(result.failed_step.next_stage_m[0], 0.19)
        self.assertEqual(result.inputs.dt_s, 1.0)

    def test_boundary_future_depth_failure_preserves_prefix(self):
        inputs = graph_case(upstream_q=0.0)
        boundary = inputs.boundary_stage_m.copy()
        boundary[2:, 2] = 11.0
        result = _i38_hydro.evaluate(_i38_replace(inputs, boundary_stage_m=boundary))
        self.assertEqual((result.status, result.committed_steps), ('failed', 1))
        self.assertEqual(result.failed_step.reason, 'max_depth')

    def test_terminal_boundary_stage_rejects_original_step(self):
        for terminal, reason in ((-0.1, 'negative_depth'), (11.0, 'max_depth')):
            inputs = graph_case(upstream_q=0.0)
            boundary = inputs.boundary_stage_m.copy()
            boundary[-1, 2] = terminal
            result = _i38_hydro.evaluate(_i38_replace(inputs, boundary_stage_m=boundary))
            with self.subTest(terminal=terminal):
                self.assertEqual((result.status, result.committed_steps), ('failed', 2))
                self.assertEqual(result.failed_step.reason, reason)
                self.assertEqual(result.failed_step.next_stage_m[2], terminal)
                _i38_np.testing.assert_array_equal(result.stage_m, _i38_np.zeros((3, 3)))

    def test_dt_diffusive_bound(self):
        with self.assertRaisesRegex(ValueError, 'diffusive stability'):
            _i38_replace(graph_case(), dt_s=5.01)
        self.assertEqual(_i38_hydro.evaluate(_i38_replace(graph_case(upstream_q=0.0), dt_s=5.0)).status, 'completed')

    def test_unknown_protection_rejected(self):
        for name, mask in (('valid_mask', [True, False, True]), ('protected_mask', [False, True, False])):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unknown or protected'):
                _i38_replace(graph_case(), **{name: _i38_np.array(mask)})

    def test_resource_preflight_before_freezing(self):
        inputs = graph_case()
        variants = [_i38_hydro.ResourceLimits(max_nodes=2), _i38_hydro.ResourceLimits(max_edges=1), _i38_hydro.ResourceLimits(max_steps=2), _i38_hydro.ResourceLimits(max_work=14), _i38_hydro.ResourceLimits(max_retained_bytes=100)]
        for limits in variants:
            with self.subTest(limits=limits), _i38_patch.object(_i38_hydro, '_immutable', side_effect=AssertionError('freeze too soon')):
                with self.assertRaisesRegex(ValueError, 'resource cap'):
                    _i38_replace(inputs, limits=limits)
        with self.assertRaises(ValueError):
            _i38_hydro.ResourceLimits(max_nodes=4097)

    def test_cancel_keeps_committed_prefix_only(self):
        calls = iter([False, True])
        result = _i38_hydro.evaluate(graph_case(), cancel=lambda: next(calls))
        self.assertEqual((result.status, result.committed_steps), ('cancelled', 1))
        self.assertIsNone(result.failed_step)
        self.assertEqual(result.stage_m.shape, (2, 3))
        self.assertEqual(result.ledger_m3.shape, (1, 6))
        self.assertTrue(_i38_hydro.validate(result)['valid'])
        immediate = _i38_hydro.evaluate(graph_case(), cancel=lambda: True)
        self.assertEqual(immediate.committed_steps, 0)

    def test_source_immutability_and_irreversible_bytes_freeze(self):
        inputs = graph_case()
        raw = _i38_np.array([0.0, 0.0, 0.0])
        inputs = _i38_replace(inputs, bed_m=raw)
        raw[:] = -10.0
        _i38_np.testing.assert_array_equal(inputs.bed_m, 0.0)
        before = {field.name: getattr(inputs, field.name).tobytes() for field in _i38_fields(inputs) if isinstance(getattr(inputs, field.name), _i38_np.ndarray)}
        result = _i38_hydro.evaluate(inputs)
        for field in _i38_fields(inputs):
            value = getattr(inputs, field.name)
            if isinstance(value, _i38_np.ndarray):
                self.assertEqual(value.tobytes(), before[field.name])
        for array in _i38_hydro._arrays(result).values():
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_rehash_does_not_bypass_static_proof(self):
        result = _i38_hydro.evaluate(graph_case())
        for name in ('stage_m', 'storage_m3', 'qedges_m3_s', 'ledger_m3', 'time_s'):
            changed = getattr(result, name).copy()
            changed.flat[-1] += 0.5
            forged = _i38_replace(result, **{name: changed}, identity_sha256='')
            self.assertEqual(forged.identity_sha256, _i38_hydro.fingerprint(forged))
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i38_hydro.validate(forged)
        failed = _i38_hydro.evaluate(_i38_replace(graph_case(), max_depth_m=0.15))
        forged_failure = _i38_replace(failed.failed_step, reason='negative_depth')
        with self.assertRaisesRegex(ValueError, 'failed reason'):
            _i38_hydro.validate(_i38_replace(failed, failed_step=forged_failure, identity_sha256=''))

    def test_roundtrip_load_never_calls_evaluate(self):
        results = [_i38_hydro.evaluate(graph_case()), _i38_hydro.evaluate(_i38_replace(graph_case(), max_depth_m=0.15)), _i38_hydro.evaluate(graph_case(), cancel=lambda: True)]
        with _i38_tempfile.TemporaryDirectory() as directory:
            for index, result in enumerate(results):
                path = _i38_Path(directory) / (str(index) + '.npz')
                _i38_hydro.save(result, path)
                with _i38_patch.object(_i38_hydro, 'evaluate', side_effect=AssertionError('load advanced time')):
                    loaded = _i38_hydro.load(path)
                self.assertEqual(loaded.identity_sha256, result.identity_sha256)
                self.assertEqual(loaded.status, result.status)
                for name, array in _i38_hydro._arrays(loaded).items():
                    _i38_np.testing.assert_array_equal(array, _i38_hydro._arrays(result)[name])
                    with self.assertRaises(ValueError):
                        array.setflags(write=True)

    def test_atomic_nooverwrite_and_fd_cleanup(self):
        result = _i38_hydro.evaluate(graph_case())
        with _i38_tempfile.TemporaryDirectory() as directory:
            path = _i38_Path(directory) / 'bundle.npz'
            _i38_hydro.save(result, path)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                _i38_hydro.save(result, path)
            self.assertEqual(path.read_bytes(), original)
            with _i38_patch.object(_i38_hydro.os, 'link', side_effect=OSError('publication failed')):
                with self.assertRaisesRegex(OSError, 'publication failed'):
                    _i38_hydro.save(result, _i38_Path(directory) / 'failed.npz')
            self.assertEqual([member.name for member in _i38_Path(directory).iterdir()], ['bundle.npz'])
            path.unlink()

    def test_reject_selfloop_duplicate_and_boundary_localq(self):
        inputs = graph_case()
        for edges in (_i38_np.array([[0, 0], [1, 2]]), _i38_np.array([[0, 1], [1, 0]])):
            with self.assertRaises(ValueError):
                _i38_replace(inputs, edges=edges)
        local = inputs.local_q_m3_s.copy()
        local[0, 2] = 1.0
        with self.assertRaisesRegex(ValueError, 'only supported on internal'):
            _i38_replace(inputs, local_q_m3_s=local)

    def test_invalid_finite_shape_units_provenance(self):
        inputs = graph_case()
        for changes in ({'bed_m': _i38_np.array([0.0, _i38_np.nan, 0.0])}, {'dt_s': 0.0}, {'area_m2': _i38_np.array([10.0, 0.0, 10.0])}, {'max_depth_m': float('inf')}, {'edges': _i38_np.array([[0.0, 1.0], [1.0, 2.0]])}, {'source': ''}, {'coords_m': _i38_np.zeros((3, 3))}, {'boundary_mask': _i38_np.ones(3, dtype=bool)}, {'valid_mask': _i38_np.ones(3)}, {'geometry_mode': 'validated-recovery'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _i38_replace(inputs, **changes)

    def test_empty_edges_is_supported(self):
        result = _i38_hydro.evaluate(_i38_replace(graph_case(), edges=_i38_np.empty((0, 2), dtype=_i38_np.int64), conductance_m2_s=_i38_np.empty(0)))
        _i38_np.testing.assert_allclose(result.stage_m[:, 0], [0.0, 0.1, 0.2, 0.3])
        self.assertEqual(result.qedges_m3_s.shape, (3, 0))

    def test_archive_duplicate_json_members_and_member_cap(self):
        with _i38_tempfile.TemporaryDirectory() as directory:
            for index, mode in enumerate(('json', 'zip', 'extra')):
                path = _i38_Path(directory) / (str(index) + '.npz')
                _i38_hydro.save(_i38_hydro.evaluate(graph_case()), path)
                if mode == 'json':
                    with _i38_zipfile.ZipFile(path) as archive:
                        meta = archive.read('metadata.json')
                    rewrite_bundle(path, metadata=meta[:-1] + b',"dt_s":1}')
                elif mode == 'zip':
                    rewrite_bundle(path, extra=('stage_m.npy', b'duplicate'))
                else:
                    rewrite_bundle(path, extra=('unexpected.npy', b'extra'))
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    _i38_hydro.load(path)

    def test_archive_header_payload_and_caps(self):
        with _i38_tempfile.TemporaryDirectory() as directory:
            for mode in ('huge_shape', 'object', 'trailing', 'truncated', 'metadata', 'dimensions'):
                path = _i38_Path(directory) / (mode + '.npz')
                _i38_hydro.save(_i38_hydro.evaluate(graph_case()), path)
                with _i38_zipfile.ZipFile(path) as archive:
                    raw = archive.read('stage_m.npy')
                    meta = _i38_json.loads(archive.read('metadata.json'))
                if mode in ('huge_shape', 'object'):
                    stream = _i38_io.BytesIO()
                    _i38_np.lib.format.write_array_header_1_0(stream, {'descr': '|O' if mode == 'object' else '<f8', 'fortran_order': False, 'shape': (1000000000,) if mode == 'huge_shape' else (4, 3)})
                    rewrite_bundle(path, array_name='stage_m.npy', payload=stream.getvalue())
                elif mode in ('trailing', 'truncated'):
                    rewrite_bundle(path, array_name='stage_m.npy', payload=raw + b'X' if mode == 'trailing' else raw[:-1])
                elif mode == 'metadata':
                    rewrite_bundle(path, metadata=b' ' * (_i38_hydro.MAX_METADATA_BYTES + 1))
                else:
                    meta['nodes'] = 1000000000
                    rewrite_bundle(path, metadata=_i38_json.dumps(meta).encode())
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    _i38_hydro.load(path)

    def test_archive_header_member_file_and_hash_caps(self):
        with _i38_tempfile.TemporaryDirectory() as directory:
            for mode in ('header', 'members', 'hash', 'file'):
                path = _i38_Path(directory) / (mode + '.npz')
                _i38_hydro.save(_i38_hydro.evaluate(graph_case()), path)
                if mode == 'header':
                    payload = b'\x93NUMPY\x01\x00' + 65535 .to_bytes(2, 'little')
                    rewrite_bundle(path, array_name='stage_m.npy', payload=payload)
                elif mode == 'members':
                    with _i38_zipfile.ZipFile(path, 'a') as archive:
                        for index in range(_i38_hydro.MAX_MEMBERS):
                            archive.writestr(str(index), b'')
                elif mode == 'hash':
                    with _i38_zipfile.ZipFile(path) as archive:
                        metadata = _i38_json.loads(archive.read('metadata.json'))
                    metadata['identity_sha256'] = ''
                    rewrite_bundle(path, metadata=_i38_json.dumps(metadata).encode())
                if mode == 'file':
                    with _i38_patch.object(_i38_hydro, 'MAX_FILE_BYTES', 10), self.assertRaisesRegex(ValueError, 'file cap'):
                        _i38_hydro.load(path)
                else:
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        _i38_hydro.load(path)

    def test_saved_rehashed_flux_rejected_with_evaluate_disabled(self):
        result = _i38_hydro.evaluate(graph_case())
        flux = result.qedges_m3_s.copy()
        flux[1, 0] += 0.5
        forged = _i38_replace(result, qedges_m3_s=flux, identity_sha256='')
        with _i38_tempfile.TemporaryDirectory() as directory:
            path = _i38_Path(directory) / 'forged.npz'
            _i38_hydro.save(result, path)
            with _i38_zipfile.ZipFile(path) as archive:
                metadata = _i38_json.loads(archive.read('metadata.json'))
            metadata['identity_sha256'] = forged.identity_sha256
            payload = _i38_io.BytesIO()
            _i38_np.lib.format.write_array(payload, forged.qedges_m3_s, version=(1, 0), allow_pickle=False)
            rewrite_bundle(path, metadata=_i38_json.dumps(metadata).encode(), array_name='qedges_m3_s.npy', payload=payload.getvalue())
            with _i38_patch.object(_i38_hydro, 'evaluate', side_effect=AssertionError('load advanced')):
                with self.assertRaisesRegex(ValueError, 'edge conductance'):
                    _i38_hydro.load(path)

    def test_verifier_failure_retains_utc_evidence(self):
        import sys
        from tools import verify_dynamic_surface_hydraulics as verifier
        with _i38_tempfile.TemporaryDirectory() as directory:
            argv = ['verify', '--skip-tests', '--output-root', directory]
            with _i38_patch.object(sys, 'argv', argv), _i38_patch.object(verifier, 'run_cases', side_effect=RuntimeError('injected failure')):
                self.assertEqual(verifier.main(), 1)
            run_directory = next(_i38_Path(directory).iterdir())
            report = _i38_json.loads((run_directory / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'failed')
            self.assertIn('injected failure', report['error'])
            self.assertTrue(report['started_utc'].endswith('+00:00'))
            self.assertTrue(report['finished_utc'].endswith('+00:00'))
            self.assertTrue((run_directory / 'started.json').is_file())
            self.assertTrue((run_directory / 'failure-traceback.log').is_file())
            self.assertEqual(len(report['source_files']), 4)
            self.assertTrue(report['source_files_unchanged'])
            for name, evidence in report['evidence_files'].items():
                self.assertEqual(evidence['file_sha256'], _i38_hashlib.sha256((run_directory / name).read_bytes()).hexdigest())

    def test_verifier_binds_source_and_bundle_file_sha256(self):
        from tools import verify_dynamic_surface_hydraulics as verifier
        for record in verifier.source_file_hashes().values():
            self.assertEqual(record['file_sha256'], _i38_hashlib.sha256(_i38_Path(record['path']).read_bytes()).hexdigest())
        with _i38_tempfile.TemporaryDirectory() as directory:
            record = verifier.record_case(_i38_Path(directory), 'fixed', graph_case())
            self.assertEqual(record['bundle_file_sha256'], _i38_hashlib.sha256(_i38_Path(record['bundle']).read_bytes()).hexdigest())
            self.assertTrue(record['bundle_file_unchanged_after_reload'])
            self.assertNotEqual(record['bundle_file_sha256'], record['identity_sha256'])

    def test_arithmetic_failure_roundtrip_nonfinite_evidence(self):
        inputs = _i38_replace(graph_case(steps=1), dt_s=5.0, local_q_m3_s=_i38_np.array([[1e+308, 0.0, 0.0]]))
        result = _i38_hydro.evaluate(inputs)
        self.assertEqual((result.status, result.committed_steps), ('failed', 0))
        self.assertEqual(result.failed_step.reason, 'arithmetic_nonfinite')
        with _i38_tempfile.TemporaryDirectory() as directory:
            path = _i38_Path(directory) / 'nonfinite-candidate.npz'
            _i38_hydro.save(result, path)
            loaded = _i38_hydro.load(path)
            self.assertEqual(loaded.identity_sha256, result.identity_sha256)
            self.assertTrue(_i38_np.isinf(loaded.failed_step.next_storage_m3[0]))

def network(receiver=(-1,), kind=('open_outflow',), slope=(0.01,)):
    from terrain_pipeline.channel_geometry import ChannelNetwork as _i39_ChannelNetwork
    n = len(receiver)
    bed = _i39_np.zeros(n)
    for _ in range(n):
        for node, target in enumerate(receiver):
            if target >= 0:
                bed[node] = bed[target] + slope[node] * 10.0
    return _i39_ChannelNetwork(receiver=_i39_np.array(receiver, _i39_np.int64), length_m=_i39_np.full(n, 10.0), width_m=_i39_np.full(n, 2.0), bed_elevation_m=bed, bed_slope=_i39_np.array(slope, _i39_np.float64), roughness=_i39_np.full(n, 0.05), max_depth_m=_i39_np.full(n, 3.0), terminal_kind=_i39_np.array(kind), source_identity_sha256='a' * 64, section_source='test rectangular', roughness_source='test Manning')

class ChannelSolverTests(_i39_unittest.TestCase):

    def test_inconsistent_physical_edges_reject_before_solve(self):
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        from dataclasses import replace
        channel = network((1, -1), ('interior', 'open_outflow'), (0.1, 0.1))
        for bed, slope in (([0.0, 0.0], [0.1, 0.1]), ([0.0, 1.0], [0.1, 0.1]), ([1.0, 0.999], [1.0, 1.0]), ([1e-20, 0.0], [1e-13, 0.1])):
            with self.subTest(bed=bed), self.assertRaisesRegex(ValueError, 'downhill|inconsistent'):
                replace(channel, bed_elevation_m=_i39_np.array(bed), bed_slope=_i39_np.array(slope))
        with self.assertRaisesRegex(ValueError, 'downhill'):
            replace(channel, receiver=_i39_np.array([-1, 0], _i39_np.int64), terminal_kind=_i39_np.array(['open_outflow', 'interior']), receiver_distance_m=_i39_np.array([0.0, 10.0]))
        object.__setattr__(channel, 'bed_slope', _i39_np.array([1.0, 0.1]))
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 1.0]), _i39_np.zeros((1, 2)), 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            _i39_solve_channel(channel, forcing)

    def test_receiver_distance_is_independent_of_storage_length(self):
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        from dataclasses import replace
        channel = network((1, -1), ('interior', 'open_outflow'), (0.1, 0.1))
        channel = replace(channel, length_m=_i39_np.array([5.0, 5.0]), receiver_distance_m=_i39_np.array([10.0, 0.0]))
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 0.1]), _i39_np.zeros((1, 2)), 'b' * 64)
        result = _i39_solve_channel(channel, forcing, _i39_np.array([5.0, 5.0]))
        _i39_np.testing.assert_array_equal(result['arrays']['area_m2'][0], [1.0, 1.0])
        _i39_np.testing.assert_array_equal(channel.receiver_distance_m, [10.0, 0.0])
        with self.assertRaisesRegex(ValueError, 'zero at terminals'):
            replace(channel, receiver_distance_m=_i39_np.array([10.0, 10.0]))

    def test_single_channel_initial_manning_flux_and_continuity(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network()
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 0.1]), _i39_np.zeros((1, 1)), 'b' * 64)
        result = _i39_solve_channel(channel, forcing, initial_volume_m3=_i39_np.array([10.0]), config=_i39_ChannelConfig(max_dt_seconds=0.1))
        arrays = result['arrays']
        expected_q = 0.9614997135382722
        self.assertEqual(result['metadata']['status'], 'complete')
        self.assertAlmostEqual(arrays['outflow_end_q_m3_s'][0, 0], expected_q)
        self.assertAlmostEqual(arrays['volume_m3'][-1, 0], 10.0 - _i39_np.sum(arrays['boundary_outflow_volume_m3']), places=12)
        _i39_np.testing.assert_allclose(arrays['balance_residual_m3'], 0.0, atol=1e-12)

    def test_dry_pulse_reaches_downstream_after_storage_delay(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network(receiver=(1, -1), kind=('interior', 'open_outflow'), slope=(0.01, 0.01))
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 1.0, 2.0, 3.0]), _i39_np.array([[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]), 'b' * 64)
        arrays = _i39_solve_channel(channel, forcing, config=_i39_ChannelConfig(max_dt_seconds=1.0))['arrays']
        self.assertEqual(arrays['volume_m3'][1, 1], 0.0)
        self.assertEqual(arrays['outflow_q_m3_s'][0, 0], 0.0)
        self.assertGreater(arrays['volume_m3'][-1, 1], 0.0)
        self.assertEqual(arrays['boundary_outflow_volume_m3'][0, 1], 0.0)

    def test_single_volume_converges_to_independent_ode(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network()
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 5.0]), _i39_np.zeros((1, 1)), 'b' * 64)

        def ode(_, state):
            area = state[0] / 10.0
            depth = area / 2.0
            return [-area * (area / (2.0 + 2.0 * depth)) ** (2.0 / 3.0) * 0.1 / 0.05]
        reference = _i39_solve_ivp(ode, (0.0, 5.0), [10.0], rtol=1e-12, atol=1e-12).y[0, -1]
        coarse = _i39_solve_channel(channel, forcing, _i39_np.array([10.0]), _i39_ChannelConfig(max_dt_seconds=0.5))['arrays']['volume_m3'][-1, 0]
        fine = _i39_solve_channel(channel, forcing, _i39_np.array([10.0]), _i39_ChannelConfig(max_dt_seconds=0.02))['arrays']['volume_m3'][-1, 0]
        self.assertLess(abs(fine - reference) / reference, 0.005)
        self.assertLess(abs(fine - reference), abs(coarse - reference))

    def test_y_junction_conserves_water_and_respects_cfl(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network(receiver=(2, 2, -1), kind=('interior', 'interior', 'open_outflow'), slope=(0.01, 0.01, 0.01))
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 1.0, 2.0]), _i39_np.array([[1.0, 2.0, 0.0], [0.0, 0.0, 0.0]]), 'b' * 64)
        result = _i39_solve_channel(channel, forcing, config=_i39_ChannelConfig(max_dt_seconds=0.3, cfl=0.4))
        arrays = result['arrays']
        input_volume = _i39_np.sum(_i39_np.diff(arrays['time_seconds'])[:, None] * arrays['local_q_m3_s'])
        self.assertAlmostEqual(input_volume, 3.0)
        self.assertAlmostEqual(_i39_np.sum(arrays['volume_m3'][-1]) + _i39_np.sum(arrays['boundary_outflow_volume_m3']), 3.0, places=12)
        self.assertLessEqual(_i39_np.max(arrays['cfl_number']), 0.4 + 1e-12)
        _i39_np.testing.assert_allclose(arrays['inflow_q_m3_s'][:, 2], arrays['outflow_q_m3_s'][:, 0] + arrays['outflow_q_m3_s'][:, 1])

    def test_depth_failure_returns_only_committed_prefix(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network(kind=('closed_wall',), slope=(0.0,))
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 1.0, 2.0]), _i39_np.array([[0.0], [2.0]]), 'b' * 64)
        result = _i39_solve_channel(channel, forcing, initial_volume_m3=_i39_np.array([59.0]), config=_i39_ChannelConfig(max_dt_seconds=1.0))
        arrays = result['arrays']
        self.assertEqual(result['metadata']['status'], 'failed_prefix')
        self.assertIn('depth', result['metadata']['failure_reason'])
        self.assertEqual(result['metadata']['last_time_seconds'], 1.0)
        _i39_np.testing.assert_array_equal(arrays['time_seconds'], [0.0, 1.0])
        _i39_np.testing.assert_array_equal(arrays['volume_m3'][:, 0], [59.0, 59.0])
        self.assertEqual(arrays['local_q_m3_s'].shape, (1, 1))

    def test_closed_and_unknown_terminals_retain_all_input(self):
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network(receiver=(-1, -1), kind=('closed_wall', 'unknown_boundary'), slope=(0.0, 0.0))
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 1.0, 2.0]), _i39_np.array([[1.0, 2.0], [0.0, 0.0]]), 'b' * 64)
        arrays = _i39_solve_channel(channel, forcing)['arrays']
        _i39_np.testing.assert_array_equal(arrays['volume_m3'][-1], [1.0, 2.0])
        _i39_np.testing.assert_array_equal(arrays['outflow_end_q_m3_s'], 0.0)
        _i39_np.testing.assert_array_equal(arrays['boundary_outflow_volume_m3'], 0.0)

    def test_inputs_are_copied_and_zero_step_limit_is_a_prefix(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network()
        q = _i39_np.array([[1.0]])
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 2.0]), q, 'b' * 64)
        q[0, 0] = 100.0
        with self.assertRaises(ValueError):
            channel.width_m[0] = 7.0
        with self.assertRaises(ValueError):
            forcing.local_q_m3_s[0, 0] = 100.0
        self.assertEqual(forcing.local_q_m3_s[0, 0], 1.0)
        result = _i39_solve_channel(channel, forcing, config=_i39_ChannelConfig(max_dt_seconds=0.5, max_steps=1))
        self.assertEqual(result['metadata']['status'], 'failed_prefix')
        self.assertEqual(result['metadata']['last_time_seconds'], 0.5)
        self.assertEqual(result['arrays']['volume_m3'].shape, (2, 1))
        self.assertEqual(result['arrays']['inflow_q_m3_s'].shape, (1, 1))

    def test_invalid_topology_and_initial_depth_reject_before_solve(self):
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        with self.assertRaisesRegex(ValueError, 'acyclic'):
            network(receiver=(1, 0), kind=('interior', 'interior'), slope=(0.01, 0.01))
        channel = network()
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 1.0]), _i39_np.zeros((1, 1)), 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'initial volume'):
            _i39_solve_channel(channel, forcing, _i39_np.array([61.0]))

    def test_wave_speed_limits_internal_step_and_zero_step_failure_is_valid(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i39_ChannelConfig
        from terrain_pipeline.channel_geometry import ChannelForcing as _i39_ChannelForcing
        from terrain_pipeline.surface_hydraulics import solve_channel as _i39_solve_channel
        channel = network()
        forcing = _i39_ChannelForcing(_i39_np.array([0.0, 10.0]), _i39_np.zeros((1, 1)), 'b' * 64)
        result = _i39_solve_channel(channel, forcing, _i39_np.array([10.0]), _i39_ChannelConfig(max_dt_seconds=10.0, cfl=0.1))
        arrays = result['arrays']
        self.assertGreater(len(arrays['cfl_number']), 1)
        self.assertAlmostEqual(arrays['cfl_number'][0], 0.1, places=12)
        self.assertLessEqual(_i39_np.max(arrays['cfl_number']), 0.1 + 1e-12)
        closed = network(kind=('closed_wall',), slope=(0.0,))
        full = _i39_ChannelForcing(_i39_np.array([0.0, 1.0]), _i39_np.array([[2.0]]), 'b' * 64)
        prefix = _i39_solve_channel(closed, full, _i39_np.array([59.0]), _i39_ChannelConfig(max_dt_seconds=1.0))
        self.assertEqual(prefix['metadata']['status'], 'failed_prefix')
        self.assertEqual(prefix['metadata']['last_time_seconds'], 0.0)
        self.assertEqual(prefix['arrays']['volume_m3'].shape, (1, 1))
        self.assertEqual(prefix['arrays']['local_q_m3_s'].shape, (0, 1))

def fixture():
    from terrain_pipeline.common_infra import TerrainGrid as _i40_TerrainGrid
    height = _i40_np.array([[5.0, 3.0, 1.0], [6.0, 4.0, 2.0]])
    receiver = _i40_np.array([[1, 2, -1], [4, 1, 2]], _i40_np.int64)
    ocean = _i40_np.zeros(height.shape, bool)
    ocean[0, 2] = True
    accepted = ~ocean
    terminal = _i40_np.full(height.shape, 2, _i40_np.int64)
    topology = dict(height_m=height, receiver=receiver, terminal=terminal, ocean=ocean, ocean_terminal=_i40_np.ones(height.shape, bool), accepted=accepted, unresolved=_i40_np.zeros(height.shape, bool), in_core=_i40_np.ones(height.shape, bool), shape=height.shape, spacing_m=10.0, origin_x_m=0.0, origin_z_m=0.0)
    volume = _i40_np.zeros((2,) + height.shape)
    volume[0, accepted] = 0.2
    volume[1, accepted] = 0.6
    flow = dict(topology=topology, producing_flat=_i40_np.flatnonzero(accepted), released_per_interval_grid_m3=volume, released_grid_m3=volume.sum(axis=0), dt_s=2.0, interval_count=2)
    terrain = _i40_TerrainGrid(height, _i40_np.ones(height.shape, bool), 0.0, 0.0, 10.0, 10.0, 'diagnostic_dem_proxy', 'synthetic raw-face fixture', 'a' * 64)
    return (terrain, flow)

def arguments(ids=None, receiver=None):
    from terrain_pipeline.channel_geometry import ChannelConfig as _i40_ChannelConfig
    ids = _i40_np.arange(6, dtype=_i40_np.int64) if ids is None else _i40_np.array(ids, _i40_np.int64)
    receiver = _i40_np.array([1, 2, -1, 4, 1, 2] if receiver is None else receiver, _i40_np.int64)
    return dict(node_cell_ids=ids, receiver=receiver, width_m=_i40_np.full(ids.size, 2.0), control_length_m=_i40_np.full(ids.size, 10.0), max_depth_m=_i40_np.full(ids.size, 10.0), roughness=_i40_np.full(ids.size, 0.05), parameter_sources={name: 'explicit synthetic engineering scenario, uncalibrated' for name in ('width_m', 'control_length_m', 'max_depth_m', 'roughness')}, terminal_policy={'2': {'classification': 'ocean', 'kind': 'open_outflow', 'slope': 0.01, 'source': 'explicit engineering boundary gradient'}}, geometry_source='raw conditioning grid node bed; not carved geometry', coverage_note=None, config=_i40_ChannelConfig(max_dt_seconds=0.5))

def rehash(bundle):
    from terrain_pipeline.common_infra import identity as _i40_identity
    bundle['identity_sha256'] = _i40_identity(bundle['arrays'], bundle['metadata'])

class DomainChannelHydraulicsTests(_i40_unittest.TestCase):

    def test_receiver_slope_uses_irregular_metric_source_frame(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i40_TerrainGrid
        from terrain_pipeline.drainage import grid_mesh as _i40_grid_mesh
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        terrain = _i40_TerrainGrid(terrain.elevation_m, terrain.valid_mask, -135.0, 225.0, 10.0, 10.0, terrain.source_kind, terrain.source_id, terrain.source_sha256, generation_seed=20261020)
        flow['topology'].update(origin_x_m=-135.0, origin_z_m=225.0)
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        mesh = _i40_grid_mesh(terrain.elevation_m.shape, x0_m=-135.0, z0_m=225.0, dx_m=10.0, world_seed=20261020)
        receiver = arguments()['receiver']
        links = receiver >= 0
        distance = _i40_np.hypot(mesh.node_x_m[links] - mesh.node_x_m[receiver[links]], mesh.node_z_m[links] - mesh.node_z_m[receiver[links]])
        self.assertGreater(float(_i40_np.max(_i40_np.abs(distance - 10.0))), 1.0)
        _i40_np.testing.assert_allclose(product['arrays']['channel_network_receiver_distance_m'][links], distance, rtol=0.0, atol=1e-13)
        expected = (terrain.elevation_m.ravel()[links] - terrain.elevation_m.ravel()[receiver[links]]) / distance
        _i40_np.testing.assert_allclose(product['arrays']['channel_network_bed_slope'][links], expected, rtol=0.0, atol=1e-13)

    def test_local_interval_forcing_not_accumulated_or_time_averaged(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import validate_domain_channel_hydraulics as _i40_validate_domain_channel_hydraulics
        terrain, flow = fixture()
        flow['accumulated_q'] = _i40_np.full(terrain.elevation_m.shape, 9999.0)
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        q = product['arrays']['channel_forcing_local_q_m3_s']
        _i40_np.testing.assert_array_equal(q[:, 0], [0.1, 0.3])
        _i40_np.testing.assert_array_equal(q[:, 2], [0.0, 0.0])
        self.assertAlmostEqual(product['metadata']['channel_metadata']['water_budget_m3']['local_input'], 4.0)
        self.assertTrue(product['metadata']['coverage']['current_production_downstream_closure_complete'])
        self.assertTrue(_i40_validate_domain_channel_hydraulics(product))
        self.assertEqual(product['metadata']['source_face'], 'raw_conditioning')
        self.assertFalse(product['metadata']['r6_carving_consumed'])
        for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'):
            self.assertIs(product['metadata'][key], False)

    def test_missing_upstream_requires_explicit_coverage_and_remains_uncertified(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        kwargs = arguments([1, 2], [1, -1])
        with self.assertRaisesRegex(ValueError, 'coverage_note'):
            _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)
        kwargs['coverage_note'] = 'Only downstream pair; upstream producing branches omitted, no inflow supplied'
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)
        coverage = product['metadata']['coverage']
        self.assertEqual(coverage['missing_producing_cell_count'], 4)
        self.assertEqual(coverage['missing_upstream_contributing_cell_count'], 4)
        self.assertAlmostEqual(coverage['missing_upstream_contributing_release_m3'], 3.2)
        self.assertAlmostEqual(coverage['missing_producing_release_m3'], 3.2)
        self.assertEqual(coverage['upstream_contributions_status'], 'not_certified')
        self.assertFalse(coverage['current_production_downstream_closure_complete'])

    def test_omitted_receiver_is_never_an_outlet_even_with_note(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        kwargs = arguments([0], [-1])
        kwargs['coverage_note'] = 'explicit partial selection'
        with self.assertRaisesRegex(ValueError, 'omitted or changed receiver'):
            _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_internal_edge_must_match_original(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        kwargs = arguments()
        kwargs['receiver'][0] = 2
        with self.assertRaisesRegex(ValueError, 'omitted or changed receiver'):
            _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_terminal_policy_is_explicit_and_classification_checked(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        for mutation in ('missing', 'wrong_kind', 'zero_slope', 'no_source'):
            kwargs = arguments()
            if mutation == 'missing':
                kwargs['terminal_policy'] = {}
            elif mutation == 'wrong_kind':
                kwargs['terminal_policy']['2'].update(classification='closed_basin', kind='closed_wall', slope=0.0)
            elif mutation == 'zero_slope':
                kwargs['terminal_policy']['2']['slope'] = 0.0
            else:
                kwargs['terminal_policy']['2']['source'] = ''
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_closed_basin_explicit_wall_not_lake_model(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        flow['topology']['ocean'][:] = False
        flow['topology']['ocean_terminal'][:] = False
        kwargs = arguments()
        kwargs['terminal_policy']['2'].update(classification='closed_basin', kind='closed_wall', slope=0.0)
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)
        self.assertEqual(product['metadata']['channel_metadata']['water_budget_m3']['boundary_outflow'], 0.0)
        self.assertIn('no conservative floodplain inundation or lake evolution', product['metadata']['limitations'])

    def test_provenance_and_physical_arrays_required(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        for key, value in (('roughness', _i40_np.zeros(6)), ('width_m', _i40_np.full(6, _i40_np.nan)), ('control_length_m', _i40_np.full(6, -1.0)), ('max_depth_m', _i40_np.zeros(6)), ('geometry_source', ''), ('parameter_sources', {}), ('config', None), ('node_cell_ids', _i40_np.arange(6, dtype=_i40_np.float64))):
            kwargs = arguments()
            kwargs[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)

    def test_time_volume_and_source_support_must_match(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        for mutation in ('totals', 'ocean_release', 'producing', 'negative', 'terminal'):
            bad = _i40_deepcopy(flow)
            if mutation == 'totals':
                bad['released_grid_m3'][0, 0] += 1.0
            elif mutation == 'ocean_release':
                bad['released_per_interval_grid_m3'][0, 0, 2] = 1.0
                bad['released_grid_m3'][0, 2] = 1.0
            elif mutation == 'producing':
                bad['producing_flat'] = bad['producing_flat'][1:]
            elif mutation == 'negative':
                bad['released_per_interval_grid_m3'][0, 0, 0] = -1.0
            else:
                bad['topology']['terminal'][0, 0] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _i40_build_domain_channel_hydraulics(terrain, bad, **arguments())

    def test_identity_changes_with_parameter_provenance_and_hydrograph(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        original = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        changed = _i40_deepcopy(flow)
        changed['released_per_interval_grid_m3'] = changed['released_per_interval_grid_m3'][::-1].copy()
        swapped = _i40_build_domain_channel_hydraulics(terrain, changed, **arguments())
        self.assertNotEqual(original['identity_sha256'], swapped['identity_sha256'])
        kwargs = arguments()
        kwargs['parameter_sources']['width_m'] = 'different explicit source'
        other = _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)
        self.assertNotEqual(original['identity_sha256'], other['identity_sha256'])

    def test_rehashed_parent_cannot_forge_summary_or_child_binding(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import validate_domain_channel_hydraulics as _i40_validate_domain_channel_hydraulics
        terrain, flow = fixture()
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        for mutation in ('coverage', 'width', 'dt', 'receiver'):
            bad = _i40_deepcopy(product)
            if mutation == 'coverage':
                bad['metadata']['coverage']['selected_input_volume_m3'] = 1234.0
            elif mutation == 'width':
                bad['arrays']['width_m'] = _i40_np.full(6, 3.0)
            elif mutation == 'dt':
                bad['metadata']['dt_s'] = 3.0
            else:
                bad['arrays']['original_receiver_cell_ids'] = _i40_np.full(6, -1, _i40_np.int64)
            rehash(bad)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _i40_validate_domain_channel_hydraulics(bad)

    def test_valid_child_from_other_scenario_cannot_be_transplanted(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import validate_domain_channel_hydraulics as _i40_validate_domain_channel_hydraulics
        terrain, flow = fixture()
        original = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        for mutation in ('forcing', 'geometry'):
            other_flow = _i40_deepcopy(flow)
            kwargs = arguments()
            if mutation == 'forcing':
                other_flow['released_per_interval_grid_m3'] = other_flow['released_per_interval_grid_m3'][::-1].copy()
            else:
                kwargs['width_m'] = _i40_np.full(6, 3.0)
            other = _i40_build_domain_channel_hydraulics(terrain, other_flow, **kwargs)
            forged = _i40_deepcopy(original)
            for key in ('channel_metadata', 'channel_identity_sha256'):
                forged['metadata'][key] = other['metadata'][key]
            for key in other['arrays']:
                if key.startswith('channel_'):
                    forged['arrays'][key] = other['arrays'][key]
            rehash(forged)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'nested channel'):
                _i40_validate_domain_channel_hydraulics(forged)

    def test_cannot_upgrade_readiness_by_rehashing(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import validate_domain_channel_hydraulics as _i40_validate_domain_channel_hydraulics
        terrain, flow = fixture()
        original = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'r6_carving_consumed'):
            forged = _i40_deepcopy(original)
            forged['metadata'][key] = True
            rehash(forged)
            with self.subTest(key=key), self.assertRaises(ValueError):
                _i40_validate_domain_channel_hydraulics(forged)

    def test_missing_accessor_contract_is_rejected(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        terrain, flow = fixture()
        del flow['released_per_interval_grid_m3']
        with self.assertRaisesRegex(ValueError, 'domain_flow_topology'):
            _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())

    def test_failed_prefix_is_preserved(self):
        from terrain_pipeline.channel_geometry import ChannelConfig as _i40_ChannelConfig
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import validate_domain_channel_hydraulics as _i40_validate_domain_channel_hydraulics
        terrain, flow = fixture()
        kwargs = arguments()
        kwargs['config'] = _i40_ChannelConfig(max_steps=1, max_dt_seconds=0.5)
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **kwargs)
        self.assertEqual(product['metadata']['channel_metadata']['status'], 'failed_prefix')
        self.assertTrue(_i40_validate_domain_channel_hydraulics(product))

    def test_summary_sum_is_canonical_across_layouts(self):
        from terrain_pipeline.surface_hydraulics import _volume_sum as _i40__volume_sum
        values = _i40_np.array([[1e+16, 1.0, 1.0], [1.0, 1.0, 1.0]])
        expected = _i40_math.fsum((float(value) for value in values.ravel(order='C')))
        self.assertEqual(expected, 1.0000000000000004e+16)
        for candidate in (values, _i40_np.asfortranarray(values), values[:, ::-1][:, ::-1]):
            self.assertEqual(_i40__volume_sum(candidate), expected)
        self.assertEqual(_i40__volume_sum(_i40_np.empty((2, 0))), 0.0)

    def test_summary_one_ulp_tampering_is_not_tolerated(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import validate_domain_channel_hydraulics as _i40_validate_domain_channel_hydraulics
        terrain, flow = fixture()
        original = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        bad = _i40_deepcopy(original)
        coverage = bad['metadata']['coverage']
        coverage['selected_input_volume_m3'] = float(_i40_np.nextafter(coverage['selected_input_volume_m3'], _i40_np.inf))
        rehash(bad)
        with self.assertRaisesRegex(ValueError, 'coverage or geometry summary mismatch'):
            _i40_validate_domain_channel_hydraulics(bad)

    def test_cold_read_in_project_interpreter(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import save_domain_channel_hydraulics as _i40_save_domain_channel_hydraulics
        root = _i40_Path(__file__).resolve().parents[1]
        interpreter = root / 'runtime' / 'venv' / 'Scripts' / 'python.exe'
        if not interpreter.exists():
            interpreter = _i40_Path(_i40_sys.executable)
        terrain, flow = fixture()
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        with _i40_tempfile.TemporaryDirectory() as folder:
            path = _i40_Path(folder) / 'cross-environment.npz'
            _i40_save_domain_channel_hydraulics(path, product)
            sha = _i40_hashlib.sha256(path.read_bytes()).hexdigest()
            code = 'import sys; from terrain_pipeline.surface_hydraulics import load_domain_channel_hydraulics; load_domain_channel_hydraulics(sys.argv[1], expected_sha256=sys.argv[2], expected_identity=sys.argv[3])'
            result = _i40_subprocess.run([str(interpreter), '-c', code, str(path), sha, product['identity_sha256']], cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_save_load_and_external_identity(self):
        from terrain_pipeline.surface_hydraulics import build_domain_channel_hydraulics as _i40_build_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import save_domain_channel_hydraulics as _i40_save_domain_channel_hydraulics
        from terrain_pipeline.surface_hydraulics import load_domain_channel_hydraulics as _i40_load_domain_channel_hydraulics
        terrain, flow = fixture()
        product = _i40_build_domain_channel_hydraulics(terrain, flow, **arguments())
        with _i40_tempfile.TemporaryDirectory() as folder:
            path = _i40_Path(folder) / 'candidate.npz'
            _i40_save_domain_channel_hydraulics(path, product)
            sha = _i40_hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = _i40_load_domain_channel_hydraulics(path, expected_sha256=sha, expected_identity=product['identity_sha256'])
            self.assertEqual(loaded['identity_sha256'], product['identity_sha256'])
            with self.assertRaises(ValueError):
                _i40_load_domain_channel_hydraulics(path, expected_sha256=sha, expected_identity='f' * 64)

class RegionalHydraulicsTests(_i41_unittest.TestCase):

    def geometry(self, bed, kinds=None):
        return _i41_surface.prepare_surface_geometry(_i41_np.asarray(bed, _i41_np.float64), spacing_m=30.0, origin_m_xz=[0.0, 0.0], source_identity='test', boundary_kind=kinds)

    def run_case(self, geometry, initial, forcing=None, boundary=None, budget=None, duration=300.0):
        shape = geometry['arrays']['H0_m'].shape
        boundary_size = geometry['arrays']['boundary_cell'].size
        return _i41_surface.advance_inertial_surface(geometry, initial_depth_m=_i41_np.asarray(initial, _i41_np.float64), forcing_interval_s=duration, intervals=1, forcing_provider=lambda index: _i41_np.zeros(shape) if forcing is None else forcing, boundary_stage_provider=lambda index: _i41_np.zeros(boundary_size) if boundary is None else boundary, source_identity='test', forcing_identity='test', budget=budget or _i41_surface.SurfaceBudget(), snapshot_interval_s=duration)

    def test_dry_slope_and_partial_wet_static_equilibrium(self):
        geometry = self.geometry([[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]])
        dry = self.run_case(geometry, _i41_np.zeros((2, 3)))
        self.assertEqual(dry['metadata']['final_volume_m3'], 0.0)
        initial = _i41_np.maximum(0.5 - geometry['arrays']['H0_m'], 0.0)
        wet = self.run_case(geometry, initial)
        _i41_np.testing.assert_array_equal(wet['arrays']['depth_m'][-1], initial)

    def test_mound_spreads_without_lost_or_negative_water(self):
        geometry = self.geometry(_i41_np.zeros((5, 5)))
        initial = _i41_np.zeros((5, 5))
        initial[2, 2] = 0.5
        case = self.run_case(geometry, initial)
        self.assertEqual(case['metadata']['status'], 'completed')
        self.assertAlmostEqual(case['metadata']['final_volume_m3'], 450.0, places=8)
        self.assertGreater(case['arrays']['depth_m'][-1, 2, 1], 0.0)
        self.assertEqual(case['diagnostics']['negative_water_clip_count'], 0)

    def test_tailwater_backflows_into_region(self):
        kinds = _i41_np.zeros(12, _i41_np.int64)
        kinds[:3] = 2
        geometry = self.geometry(_i41_np.zeros((3, 3)), kinds)
        case = self.run_case(geometry, _i41_np.zeros((3, 3)), boundary=_i41_np.full(12, 0.1))
        self.assertGreater(case['metadata']['boundary_input_m3'], 0.0)
        self.assertLess(abs(case['metadata']['final_volume_m3'] - case['metadata']['boundary_input_m3']), 1e-07)

    def test_ridge_crest_blocks_until_wet_level_exceeds(self):
        geometry = self.geometry([[0.0, 1.0, 0.0]])
        flux, *_ = _i41_surface.inertial_face_flux(_i41_np.array([0.5, 1.0]), _i41_np.array([1.0, 0.0]), _i41_np.ones(2), _i41_np.zeros(2), 1.0, 30.0, 30.0, _i41_surface.SurfaceBudget())
        _i41_np.testing.assert_array_equal(flux, 0.0)
        flux, *_ = _i41_surface.inertial_face_flux(_i41_np.array([1.2, 1.0]), _i41_np.array([1.0, 0.0]), _i41_np.ones(2), _i41_np.zeros(2), 1.0, 30.0, 30.0, _i41_surface.SurfaceBudget())
        self.assertGreater(flux[0], 0.0)

    def test_two_pool_disconnected_fill_spill_and_recession(self):
        geometry = self.geometry([[0.0, 1.0, 0.0]])
        isolated = self.run_case(geometry, [[0.5, 0.0, 0.0]], duration=14400.0)
        _i41_np.testing.assert_array_equal(isolated['arrays']['depth_m'][-1], [[0.5, 0.0, 0.0]])
        fill = _i41_surface.advance_inertial_surface(geometry, initial_depth_m=_i41_np.array([[0.5, 0.0, 0.0]]), forcing_interval_s=3600.0, intervals=4, forcing_provider=lambda index: _i41_np.array([[0.4, 0.0, 0.0]]) if index == 0 else _i41_np.zeros((1, 3)), boundary_stage_provider=lambda index: _i41_np.zeros(8), source_identity='test', forcing_identity='test', snapshot_interval_s=900.0)
        self.assertEqual(fill['metadata']['status'], 'completed')
        self.assertAlmostEqual(fill['metadata']['supplied_m3'], 1440.0, places=7)
        self.assertAlmostEqual(fill['metadata']['final_volume_m3'], 1890.0, places=7)
        self.assertGreater(fill['arrays']['depth_m'][-1, 0, 2], 1.0)
        self.assertLess(_i41_np.abs(fill['arrays']['ledger'][:, 4]).max(), 1e-08)
        kinds = _i41_np.zeros(8, _i41_np.int64)
        kinds[1] = 2
        drainage = self.geometry([[0.0, 1.0, 0.0]], kinds)
        retreat = self.run_case(drainage, fill['arrays']['depth_m'][-1], duration=14400.0)
        self.assertGreater(retreat['metadata']['boundary_output_m3'], 900.0)
        self.assertGreater(retreat['arrays']['depth_m'][-1, 0, 0], 1.0)
        self.assertLess(retreat['arrays']['depth_m'][-1, 0, 2], 0.01)
        self.assertLess(_i41_np.abs(retreat['arrays']['ledger'][:, 4]).max(), 1e-08)
        self.assertEqual(retreat['diagnostics']['negative_water_clip_count'], 0)

    def test_max_depth_and_work_refusal_save_committed_prefix(self):
        geometry = self.geometry(_i41_np.zeros((2, 2)))
        budget = _i41_replace(_i41_surface.SurfaceBudget(), max_substeps=2)
        case = self.run_case(geometry, _i41_np.zeros((2, 2)), budget=budget)
        self.assertEqual(case['metadata']['status'], 'refused')
        self.assertEqual(case['metadata']['substeps'], 2)
        self.assertEqual(case['metadata']['committed_time_s'], 60.0)
        case = self.run_case(geometry, _i41_np.zeros((2, 2)), forcing=_i41_np.full((2, 2), 900.0), budget=_i41_replace(_i41_surface.SurfaceBudget(), max_depth_m=0.01))
        self.assertEqual(case['metadata']['status'], 'refused')
        self.assertEqual(case['metadata']['final_volume_m3'], 0.0)

    def test_half_dt_same_physical_mound(self):
        geometry = self.geometry(_i41_np.zeros((5, 5)))
        initial = _i41_np.zeros((5, 5))
        initial[2, 2] = 0.05
        coarse = self.run_case(geometry, initial, budget=_i41_replace(_i41_surface.SurfaceBudget(), max_dt_s=10.0))
        fine = self.run_case(geometry, initial, budget=_i41_replace(_i41_surface.SurfaceBudget(), max_dt_s=5.0))
        self.assertLess(_i41_np.abs(coarse['arrays']['depth_m'][-1] - fine['arrays']['depth_m'][-1]).max(), 0.001)

    def test_implicit_drag_uniform_slope_equilibrium(self):
        budget = _i41_surface.SurfaceBudget()
        for depth in (0.001, 0.01, 1.0, 20.0):
            expected = 30 * depth ** (5 / 3) / 0.035 * _i41_np.sqrt(10 / 30)
            actual, _ = _i41_surface.inertial_face_flux(_i41_np.array([1500.0 + depth]), _i41_np.array([1490.0 + depth]), _i41_np.array([1500.0]), _i41_np.array([expected]), 30.0, 30.0, 30.0, budget)
            self.assertAlmostEqual(actual[0] / expected, 1.0, places=9)

    def test_inertial_dry_static_mound_tailwater_and_limiter(self):
        for mode in ('dry', 'static', 'mound', 'tailwater'):
            kinds = _i41_np.zeros(12, _i41_np.int64)
            if mode == 'tailwater':
                kinds[:3] = 2
            bed = _i41_np.zeros((3, 3))
            if mode == 'static':
                bed[:, 2] = 2.0
            geometry = self.geometry(bed, kinds)
            initial = _i41_np.maximum(0.5 - bed, 0.0) if mode == 'static' else _i41_np.zeros((3, 3))
            if mode == 'mound':
                initial[1, 1] = 0.5
            saved = _i41_surface.advance_inertial_surface(geometry, initial_depth_m=initial, forcing_interval_s=300.0, intervals=1, forcing_provider=lambda index: _i41_np.zeros((3, 3)), boundary_stage_provider=lambda index: _i41_np.full(12, 0.1), source_identity='test', forcing_identity='test', snapshot_interval_s=300.0)
            self.assertEqual(saved['metadata']['status'], 'completed', mode)
            if mode in ('dry', 'static'):
                _i41_np.testing.assert_array_equal(saved['arrays']['depth_m'][-1], initial)
            if mode == 'tailwater':
                self.assertGreater(saved['metadata']['boundary_input_m3'], 0.0)
            error = saved['metadata']['final_volume_m3'] - saved['metadata']['initial_volume_m3'] - saved['metadata']['boundary_input_m3'] + saved['metadata']['boundary_output_m3']
            self.assertLess(abs(error), 1e-07)

    def test_inertial_real_stage_gradient_and_positive_limited_step(self):
        budget = _i41_surface.SurfaceBudget()
        q, _ = _i41_surface.inertial_face_flux(_i41_np.array([1500.01]), _i41_np.array([1490.01]), _i41_np.array([1500.0]), _i41_np.zeros(1), 0.1, 30.0, 30.0, budget)
        rhs = 9.81 * 0.01 * 0.1 * 10 / 30
        drag = 9.81 * 0.1 * 0.035 ** 2 / 0.01 ** (7 / 3)
        self.assertAlmostEqual(q[0] / 30 + drag * (q[0] / 30) ** 2, rhs, places=10)
        geometry = self.geometry([[0.0, 0.0]])
        depth = _i41_np.array([0.001, 0.0])
        internal, boundary, stats = _i41_surface.limited_inertial_fluxes(geometry, depth, _i41_np.array([100.0]), _i41_np.zeros(6), _i41_np.zeros(6), _i41_np.zeros(2), 30.0, _i41_replace(budget, roughness_s_m_third=1e-08))
        updated = depth + 30 * _i41_surface._net_flux(geometry, internal, boundary) / 900
        self.assertTrue((updated >= 0).all())
        self.assertGreater(stats['limited_donors'], 0)
        self.assertGreater(stats['removed_transfer_m3'], 0)

class RegionalAccelerationTests(_i42_unittest.TestCase):

    def test_random_faces_reverse_flow_and_active_limiter(self):
        generator = _i42_np.random.default_rng(42)
        geometry = _i42_base.prepare_surface_geometry(generator.uniform(1490.0, 1500.0, (8, 8)), spacing_m=30.0, origin_m_xz=[0.0, 0.0], source_identity='test', boundary_kind=_i42_np.full(32, 2, _i42_np.int64))
        for roughness in (0.035, 1e-08):
            budget = _i42_replace(_i42_base.SurfaceBudget(), roughness_s_m_third=roughness)
            args = (geometry, generator.uniform(0.0, 0.1, 64), generator.uniform(-100.0, 100.0, 112), generator.uniform(-100.0, 100.0, 32), _i42_np.full(32, 1495.0), generator.uniform(0.0, 0.01, 64), 30.0, budget)
            expected = _i42_base.limited_inertial_fluxes(*args)
            actual = _i42_accelerated.regional_surface_hydraulics_accelerated_limited_inertial_fluxes(*args)
            for index in (0, 1):
                _i42_np.testing.assert_allclose(actual[index], expected[index], rtol=2e-13, atol=1e-12)
            self.assertEqual(actual[2]['limited_donors'], expected[2]['limited_donors'])
            self.assertAlmostEqual(actual[2]['removed_transfer_m3'], expected[2]['removed_transfer_m3'], places=8)

    def test_multistep_same_status_states_and_ledgers(self):
        for mode in ('mound', 'backwater', 'refused'):
            kinds = _i42_np.zeros(20, _i42_np.int64)
            if mode == 'backwater':
                kinds[:5] = 2
            geometry = _i42_base.prepare_surface_geometry(_i42_np.zeros((5, 5)), spacing_m=30.0, origin_m_xz=[0.0, 0.0], source_identity='test', boundary_kind=kinds)
            initial = _i42_np.zeros((5, 5))
            if mode == 'mound':
                initial[2, 2] = 1.0
            budget = _i42_replace(_i42_base.SurfaceBudget(), max_substeps=2) if mode == 'refused' else _i42_base.SurfaceBudget()
            kwargs = dict(initial_depth_m=initial, forcing_interval_s=900.0, intervals=1, forcing_provider=lambda index: _i42_np.full((5, 5), 0.0001), boundary_stage_provider=lambda index: _i42_np.full(20, 0.2), source_identity='test', forcing_identity='test', budget=budget)
            expected = _i42_base.advance_inertial_surface(geometry, **kwargs)
            actual = _i42_accelerated.advance_accelerated_surface(geometry, **kwargs)
            self.assertEqual(actual['metadata']['status'], expected['metadata']['status'])
            for key in expected['arrays']:
                _i42_np.testing.assert_allclose(actual['arrays'][key], expected['arrays'][key], rtol=1e-11, atol=1e-09)

class RegionalComparisonTests(_i43_unittest.TestCase):

    def fixture(self, directory, *, forcing='same', forged=False):
        from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i43_prepare_surface_geometry
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i43_SurfaceBudget
        from terrain_pipeline.common_infra import file_sha256 as _i43_file_sha256
        directory.mkdir()
        budget = vars(_i43_SurfaceBudget())
        (directory / 'binding.json').write_text(_i43_json.dumps({'source_identity': 'test', 'height_source_identity': 'height', 'forcing_manifest_sha256': forcing, 'budget': budget}), encoding='utf-8')
        geometry = _i43_prepare_surface_geometry(_i43_np.zeros((256, 256)), spacing_m=30.0, origin_m_xz=[-184320.0, 61440.0], source_identity='test', boundary_kind=_i43_np.ones(1024, _i43_np.int64))
        if forged:
            geometry['arrays']['face_crest_m'][0] += 1.0
        _i43_np.savez(directory / 'geometry.npz', **geometry['arrays'])
        (directory / 'geometry.json').write_text(_i43_json.dumps(geometry['metadata']), encoding='utf-8')
        (directory / 'states.json').write_text(_i43_json.dumps({'metadata': {'status': 'completed', 'requested_time_s': 900.0, 'committed_time_s': 900.0, 'failure': None, 'wall_s': 1.0, 'substeps': 30, 'face_evaluations': 3947520}}), encoding='utf-8')
        _i43_np.savez_compressed(directory / 'states.npz', time_s=_i43_np.array([0.0, 900.0]), depth_m=_i43_np.zeros((2, 256, 256)), initial_depth_m=_i43_np.zeros((256, 256)), ledger=_i43_np.zeros((2, 5)), final_internal_q_m3_s=_i43_np.zeros(130560), final_boundary_q_m3_s=_i43_np.zeros(1024))
        artifacts = {path.name: _i43_file_sha256(path) for path in directory.iterdir()}
        (directory / 'manifest.json').write_text(_i43_json.dumps({'artifacts': artifacts}), encoding='utf-8')
        return _i43_file_sha256(directory / 'manifest.json')

    def test_dry_self_comparison_all_zero(self):
        with _i43_tempfile.TemporaryDirectory() as root:
            directory = _i43_Path(root) / 'base'
            digest = self.fixture(directory)
            result = _i43_compare(directory, directory, base_sha256=digest, other_sha256=digest)
            self.assertEqual(len(result['frames']), 2)
            self.assertEqual(result['frames'][-1]['volume_L1_difference_m3'], 0.0)
            self.assertNotIn('backwater', result['frames'][-1])

    def test_different_forcing_and_resigned_geometry_rejected(self):
        with _i43_tempfile.TemporaryDirectory() as root:
            base = _i43_Path(root) / 'base'
            base_sha = self.fixture(base)
            for name, options in (('forcing', {'forcing': 'other'}), ('geometry', {'forged': True})):
                other = _i43_Path(root) / name
                other_sha = self.fixture(other, **options)
                with self.assertRaises(ValueError):
                    _i43_compare(base, other, base_sha256=base_sha, other_sha256=other_sha)

def item(label, local, capacity, downstream=None, complete=True):
    return {'label': label, 'local_m3': local, 'capacity_m3': capacity, 'downstream': downstream, 'destination': 'lake' if downstream is not None else 'ocean', 'complete': complete}

class BasinTransferTest(_i44_unittest.TestCase):

    def test_partial_retention_and_global_balance(self):
        from terrain_pipeline.surface_hydraulics import transfer_basins as _i44_transfer_basins
        result = _i44_transfer_basins([item(1, 10.0, 4.0, 2), item(2, 2.0, 10.0)])
        self.assertEqual(result[1]['outflow_m3'], 6.0)
        self.assertEqual(result[2]['stored_m3'], 8.0)
        self.assertEqual(result[2]['outflow_m3'], 0.0)
        self.assertEqual(12.0, result[1]['stored_m3'] + result[2]['stored_m3'] + result[2]['outflow_m3'])

    def test_pending_target_keeps_known_upstream_input(self):
        from terrain_pipeline.surface_hydraulics import transfer_basins as _i44_transfer_basins
        result = _i44_transfer_basins([item(1, 10.0, 4.0, 2), item(2, 2.0, 10.0, complete=False)])
        self.assertEqual(result[2]['inflow_m3'], 8.0)
        self.assertIsNone(result[2]['stored_m3'])
        self.assertEqual(12.0, result[1]['stored_m3'] + result[2]['inflow_m3'])

    def test_cycle_does_not_affect_independent_basin(self):
        from terrain_pipeline.surface_hydraulics import transfer_basins as _i44_transfer_basins
        result = _i44_transfer_basins([item(1, 2.0, 1.0, 2), item(2, 3.0, 1.0, 1), item(3, 5.0, 2.0)])
        self.assertFalse(result[1]['complete'])
        self.assertFalse(result[2]['complete'])
        self.assertEqual(result[3]['stored_m3'], 2.0)
        self.assertEqual(result[3]['outflow_m3'], 3.0)
        self.assertEqual(10.0, result[1]['inflow_m3'] + result[2]['inflow_m3'] + result[3]['stored_m3'] + result[3]['outflow_m3'])

def solve(bed, ocean=None, side=8):
    from terrain_pipeline.surface_hydraulics import form_connected_region as _i45_form_connected_region
    if ocean is None:
        ocean = _i45_np.zeros(bed.shape, bool)
    composition = {'composed_elevation_m': bed, 'ocean_mask': ocean, 'valid_mask': _i45_np.ones(bed.shape, bool), 'metadata': {'origin_native_xz': [-5, 7], 'world_seed': 20261020}}
    return _i45_form_connected_region(composition, [-5, 7], runoff_m_per_year=1.0, duration_seconds=86400.0, channel_threshold_m3_s=1e-06, tile_side_cells=side, min_lake_area_m2=1000.0)

class ConnectedRegionTest(_i45_unittest.TestCase):

    def test_cross_tile_routing_q_and_unknown(self):
        bed = _i45_np.tile(_i45_np.arange(23, -1, -1, dtype=float), (24, 1))
        ocean = _i45_np.zeros(bed.shape, bool)
        ocean[:, -1] = True
        product = solve(bed, ocean)
        a = product['arrays']
        r = a['receiver'].ravel()
        q = a['known_q_m3_s'].ravel()
        local = 900.0 / (365.25 * 86400.0)
        sums = _i45_np.zeros(q.size)
        live = r >= 0
        _i45_np.add.at(sums, r[live], q[live])
        _i45_np.testing.assert_allclose(q[~ocean.ravel()], sums[~ocean.ravel()] + local)
        self.assertGreater(product['metadata']['statistics']['routing_cross_tile_edges'], 0)
        self.assertFalse(a['complete_mask'][10, -2])
        self.assertTrue(_i45_np.isnan(a['representative_q_m3_s'][10, -2]))
        for row, col in _i45_np.argwhere(a['receiver'] >= 0):
            target_row, target_col = divmod(int(a['receiver'][row, col]), bed.shape[1])
            self.assertEqual(a['receiver_native_x'][row, col], target_col - 5)
            self.assertEqual(a['receiver_native_z'][row, col], target_row + 7)
        for row, col in _i45_np.argwhere(a['spill_receiver'] >= 0):
            target_row, target_col = divmod(int(a['spill_receiver'][row, col]), bed.shape[1])
            self.assertEqual(a['spill_receiver_native_x'][row, col], target_col - 5)
            self.assertEqual(a['spill_receiver_native_z'][row, col], target_row + 7)
        self.assertEqual(product['metadata']['statistics']['active_spill_edges'], int(((a['spill_receiver'] >= 0) & (a['spill_edge_volume_m3'] > 0)).sum()))

    def test_spill_chain_destination_is_not_local_lake_terminal(self):
        from terrain_pipeline.surface_hydraulics import _spill_destinations as _i45__spill_destinations
        links = [{'source_label': 1, 'target_label': 2, 'destination': 'lake', 'volume_m3': 3.0}, {'source_label': 2, 'target_label': None, 'destination': 'ocean', 'volume_m3': 2.0}]
        self.assertEqual(_i45__spill_destinations(links)[0], {'source_label': 1, 'labels': [1, 2], 'destination': 'ocean'})
        links[1]['volume_m3'] = 0.0
        self.assertEqual(_i45__spill_destinations(links)[0]['destination'], 'retained')

    def test_basin_crosses_tiles_once_and_tile_size_does_not_change_solution(self):
        z, x = _i45_np.indices((41, 41))
        distance = _i45_np.hypot(x - 20, z - 20)
        bed = _i45_np.zeros((41, 41))
        basin = distance <= 7.0
        bed[basin] = -5.0 + distance[basin] * 2.0
        first = solve(bed, side=8)
        second = solve(bed, side=13)
        for name in first['arrays']:
            _i45_np.testing.assert_array_equal(first['arrays'][name], second['arrays'][name])
        lakes = [r for r in first['metadata']['formation']['basins'] if r['status'] == 'lake']
        self.assertEqual(len(lakes), 1)
        record = lakes[0]
        mask = first['arrays']['basin_label'] == record['label']
        self.assertGreater(_i45_np.unique((x[mask] - 5) // 8).size, 1)
        volume = _i45_np.maximum(record['water_surface_m'] - bed[mask], 0.0).sum() * 900.0
        self.assertAlmostEqual(volume, record['stored_m3'], places=7)
        rebuilt = _i45_np.empty_like(bed)
        slices = [(slice(r, min(r + 8, 41)), slice(c, min(c + 8, 41))) for r in range(0, 41, 8) for c in range(0, 41, 8)]
        for sl in reversed(slices):
            rebuilt[sl] = first['arrays']['final_bed_m'][sl]
        _i45_np.testing.assert_array_equal(rebuilt, first['arrays']['final_bed_m'])
from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i46_SurfaceBudget
FAST = _i46_SurfaceBudget(max_depth_m=40.0, max_snapshots=40, max_wall_s=120.0, max_dt_s=30.0)

def tilted_page(rows=24, columns=24, spacing=60.0):
    """A bowl with one low rim cell, so spilling is deterministic and inspectable."""
    ys, xs = _i46_np.mgrid[0:rows, 0:columns]
    height = 100.0 + 0.4 * (ys - rows / 2.0) ** 2 * spacing / 60.0 + 0.4 * (xs - columns / 2.0) ** 2 * spacing / 60.0
    return height.astype(_i46_np.float64)

def channel_mask(rows=24, columns=24, half=1):
    mask = _i46_np.zeros((rows, columns), bool)
    mask[:, columns // 2 - half:columns // 2 + half + 1] = True
    return mask

class AggregationTests(_i46_unittest.TestCase):

    def test_block_mean_reproduces_the_fine_page_when_block_is_one(self):
        from terrain_pipeline.surface_hydraulics import aggregate_fine_field as _i46_aggregate_fine_field
        page = _i46_np.arange(64.0, dtype=_i46_np.float64).reshape(8, 8)
        _i46_np.testing.assert_array_equal(_i46_aggregate_fine_field(page, 1), page)

    def test_block_mean_is_the_arithmetic_mean_not_the_minimum(self):
        from terrain_pipeline.surface_hydraulics import aggregate_fine_field as _i46_aggregate_fine_field
        page = _i46_np.array([[0.0, 2.0, 0.0, 0.0], [4.0, 6.0, 0.0, 0.0], [8.0, 10.0, 0.0, 0.0], [12.0, 14.0, 0.0, 0.0]])
        out = _i46_aggregate_fine_field(page, 2)
        self.assertEqual(out.shape, (2, 2))
        _i46_np.testing.assert_allclose(out[:, 0], [(0.0 + 2.0 + 4.0 + 6.0) / 4.0, (8.0 + 10.0 + 12.0 + 14.0) / 4.0])
        self.assertGreater(out[0, 0], 0.0)

    def test_trailing_partial_block_is_dropped_not_padded(self):
        from terrain_pipeline.surface_hydraulics import aggregate_fine_field as _i46_aggregate_fine_field
        page = _i46_np.zeros((5, 7), _i46_np.float64)
        out = _i46_aggregate_fine_field(page, 2)
        self.assertEqual(out.shape, (2, 3))

    def test_non_finite_fine_field_is_refused(self):
        from terrain_pipeline.surface_hydraulics import aggregate_fine_field as _i46_aggregate_fine_field
        page = _i46_np.zeros((4, 4), _i46_np.float64)
        page[1, 1] = _i46_np.nan
        with self.assertRaises(ValueError):
            _i46_aggregate_fine_field(page, 2)

    def test_zero_block_is_refused(self):
        from terrain_pipeline.surface_hydraulics import aggregate_fine_field as _i46_aggregate_fine_field
        with self.assertRaises(ValueError):
            _i46_aggregate_fine_field(_i46_np.zeros((4, 4), _i46_np.float64), 0)

class WindowTests(_i46_unittest.TestCase):

    def test_cell_centres_sit_half_a_cell_inside_the_origin(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import cell_centres as _i46_cell_centres
        window = _i46_FloodplainWindow((1000.0, 2000.0), 30.0, 3)
        xs, zs = _i46_cell_centres(window, (2, 2))
        _i46_np.testing.assert_allclose(xs, [1000.0 + 45.0, 1000.0 + 135.0])
        _i46_np.testing.assert_allclose(zs, [2000.0 + 45.0, 2000.0 + 135.0])

    def test_extent_is_the_outer_edge_not_the_centre(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import window_extent as _i46_window_extent
        window = _i46_FloodplainWindow((1000.0, 2000.0), 30.0, 3)
        self.assertEqual(_i46_window_extent(window, (2, 3)), (1000.0, 1000.0 + 3 * 90.0, 2000.0, 2000.0 + 2 * 90.0))

    def test_bad_window_parameters_are_refused(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        with self.assertRaises(ValueError):
            _i46_FloodplainWindow((0.0, 0.0), -1.0, 1).validate()
        with self.assertRaises(ValueError):
            _i46_FloodplainWindow((0.0, 0.0), 30.0, 0).validate()

class CrossingTests(_i46_unittest.TestCase):

    def test_edge_leaving_the_window_is_found_at_the_boundary_plane(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import crossing_edges as _i46_crossing_edges
        window = _i46_FloodplainWindow((0.0, 0.0), 10.0, 1)
        shape = (10, 10)
        nodes = _i46_np.array([[150.0, 50.0], [50.0, 50.0]])
        found = _i46_crossing_edges(window, shape, nodes, _i46_np.array([1, -1]))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['donor'], 0)
        self.assertTrue(found[0]['inflow'])
        self.assertAlmostEqual(found[0]['point_m_xz'][0], 100.0)

    def test_direction_of_travel_decides_the_inflow_flag(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import crossing_edges as _i46_crossing_edges
        window = _i46_FloodplainWindow((0.0, 0.0), 10.0, 1)
        shape = (10, 10)
        inward = _i46_crossing_edges(window, shape, _i46_np.array([[150.0, 50.0], [50.0, 50.0]]), _i46_np.array([1, -1]))
        outward = _i46_crossing_edges(window, shape, _i46_np.array([[50.0, 50.0], [150.0, 50.0]]), _i46_np.array([1, -1]))
        self.assertTrue(inward[0]['inflow'])
        self.assertFalse(outward[0]['inflow'])

    def test_edges_wholly_inside_or_wholly_outside_do_not_cross(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import crossing_edges as _i46_crossing_edges
        window = _i46_FloodplainWindow((0.0, 0.0), 10.0, 1)
        shape = (10, 10)
        inside = _i46_np.array([[20.0, 20.0], [80.0, 80.0]])
        self.assertEqual(_i46_crossing_edges(window, shape, inside, _i46_np.array([1, -1])), [])
        outside = _i46_np.array([[300.0, 300.0], [400.0, 400.0]])
        self.assertEqual(_i46_crossing_edges(window, shape, outside, _i46_np.array([1, -1])), [])

    def test_terminal_node_without_receiver_is_ignored(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import crossing_edges as _i46_crossing_edges
        window = _i46_FloodplainWindow((0.0, 0.0), 10.0, 1)
        nodes = _i46_np.array([[50.0, 50.0]])
        self.assertEqual(_i46_crossing_edges(window, (10, 10), nodes, _i46_np.array([-1])), [])

class SourceTests(_i46_unittest.TestCase):

    def window(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        return _i46_FloodplainWindow((0.0, 0.0), 10.0, 1)

    def test_width_controls_how_many_boundary_cells_receive_water(self):
        from terrain_pipeline.surface_hydraulics import source_locations as _i46_source_locations
        crossing = {'donor': 0, 'receiver': 1, 'inflow': True, 'axis': 'x', 'side': 'min', 'point_m_xz': (0.0, 50.0)}
        narrow = _i46_source_locations(self.window(), (10, 10), [crossing], _i46_np.array([20.0, 1.0]))
        wide = _i46_source_locations(self.window(), (10, 10), [crossing], _i46_np.array([80.0, 1.0]))
        self.assertLess(len(narrow[0]['cells']), len(wide[0]['cells']))
        for location in (narrow[0], wide[0]):
            self.assertAlmostEqual(float(location['weights'].sum()), 1.0)

    def test_every_source_cell_is_on_the_declared_boundary(self):
        from terrain_pipeline.surface_hydraulics import source_locations as _i46_source_locations
        crossing = {'donor': 0, 'receiver': 1, 'inflow': True, 'axis': 'z', 'side': 'max', 'point_m_xz': (50.0, 100.0)}
        location = _i46_source_locations(self.window(), (10, 10), [crossing], _i46_np.array([60.0, 1.0]))[0]
        rows = [cell[0] for cell in location['cells']]
        self.assertTrue(all((row == 9 for row in rows)), rows)

    def test_source_matrix_is_row_stochastic_and_lands_each_volume_once(self):
        from terrain_pipeline.surface_hydraulics import interval_forcing as _i46_interval_forcing
        from terrain_pipeline.surface_hydraulics import source_locations as _i46_source_locations
        from terrain_pipeline.surface_hydraulics import source_matrix as _i46_source_matrix
        crossings = [{'donor': 0, 'receiver': 1, 'inflow': True, 'axis': 'x', 'side': 'min', 'point_m_xz': (0.0, 30.0)}, {'donor': 1, 'receiver': 2, 'inflow': True, 'axis': 'z', 'side': 'max', 'point_m_xz': (70.0, 100.0)}]
        locations = _i46_source_locations(self.window(), (10, 10), crossings, _i46_np.array([40.0, 40.0]))
        matrix = _i46_source_matrix((10, 10), locations)
        _i46_np.testing.assert_allclose(matrix.sum(axis=1), _i46_np.ones(2))
        forcing = _i46_interval_forcing((10, 10), matrix, _i46_np.array([100.0, 300.0]))
        self.assertAlmostEqual(float(forcing.sum()), 400.0)

    def test_negative_discharge_is_refused_downstream(self):
        from terrain_pipeline.surface_hydraulics import hydrograph as _i46_hydrograph
        from terrain_pipeline.surface_hydraulics import interval_forcing as _i46_interval_forcing
        matrix = _i46_np.zeros((1, 4))
        matrix[0, 0] = 1.0
        forcing = _i46_interval_forcing((2, 2), matrix, _i46_np.array([-1.0]))
        self.assertLess(float(forcing.sum()), 0.0)
        with self.assertRaises(ValueError):
            _i46_hydrograph(_i46_np.array([[-1.0]]), 3600.0)

class BoundaryTests(_i46_unittest.TestCase):

    def test_rim_is_the_lowest_boundary_cell(self):
        from terrain_pipeline.surface_hydraulics import rim_outlet_cells as _i46_rim_outlet_cells
        height = tilted_page()
        height[-1, 5] = 90.0
        cells, rim, shares = _i46_rim_outlet_cells(height.shape, height, margin_cells=0)
        self.assertAlmostEqual(rim, 90.0)
        self.assertIn((height.shape[0] - 1, 5), cells)
        self.assertEqual(shares, [])

    def test_rim_never_lands_on_an_injection_receptor(self):
        from terrain_pipeline.surface_hydraulics import rim_outlet_cells as _i46_rim_outlet_cells
        height = tilted_page()
        height[-1, 5] = 90.0
        cells, rim, _ = _i46_rim_outlet_cells(height.shape, height, margin_cells=1, exclude={(height.shape[0] - 1, 5)})
        self.assertNotIn((height.shape[0] - 1, 5), cells)
        self.assertGreater(rim, 90.0)

    def test_everything_else_is_closed_and_crests_are_the_ground(self):
        from terrain_pipeline.surface_hydraulics import boundary_certificate as _i46_boundary_certificate
        height = tilted_page()
        kinds, crests, exterior = _i46_boundary_certificate(height.shape, height, outlet_cells=[(0, 0)])
        self.assertEqual(int((kinds == 0).sum()), exterior.size - 1)
        self.assertEqual(int((kinds == 1).sum()), 1)
        _i46_np.testing.assert_allclose(crests, height.ravel()[exterior])

    def test_outlet_off_the_boundary_is_refused(self):
        from terrain_pipeline.surface_hydraulics import boundary_certificate as _i46_boundary_certificate
        height = tilted_page()
        with self.assertRaises(ValueError):
            _i46_boundary_certificate(height.shape, height, outlet_cells=[(3, 3)])

    def test_boundary_coordinates_match_the_solver_ordering(self):
        from terrain_pipeline.surface_hydraulics import boundary_cell_coordinates as _i46_boundary_cell_coordinates
        from terrain_pipeline.surface_hydraulics import boundary_cells as _i46_boundary_cells
        shape = (4, 5)
        grid = _i46_np.arange(20).reshape(shape)
        self.assertTrue(_i46_np.array_equal(_i46_boundary_cells(shape), _i46_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]))
        coordinates = _i46_boundary_cell_coordinates(shape)
        self.assertEqual(len(coordinates), _i46_boundary_cells(shape).size)
        for cell, flat in zip(coordinates, _i46_boundary_cells(shape)):
            self.assertEqual(cell[0] * shape[1] + cell[1], int(flat))

class DomainRunTests(_i46_unittest.TestCase):
    """End-to-end behaviour of the frozen solver driven through the adapter."""

    def build(self):
        from terrain_pipeline.surface_hydraulics import FloodplainWindow as _i46_FloodplainWindow
        from terrain_pipeline.surface_hydraulics import build_domain as _i46_build_domain
        from terrain_pipeline.surface_hydraulics import source_locations as _i46_source_locations
        from terrain_pipeline.surface_hydraulics import source_matrix as _i46_source_matrix
        height = tilted_page(rows=16, columns=16, spacing=60.0)
        height[0, 0] = height.min() - 3.0
        window = _i46_FloodplainWindow((0.0, 0.0), 60.0, 1)
        domain = _i46_build_domain(window, height, source_identity='test', margin_cells=0)
        crossings = [{'donor': 0, 'receiver': 1, 'inflow': True, 'axis': 'x', 'side': 'min', 'point_m_xz': (0.0, 8 * 60.0 + 30.0)}]
        locations = _i46_source_locations(window, height.shape, crossings, _i46_np.array([180.0]))
        domain['source_matrix'] = _i46_source_matrix(height.shape, locations)
        return (window, domain, height, crossings, locations)

    def test_water_budget_closes_and_depth_stays_non_negative(self):
        from terrain_pipeline.surface_hydraulics import domain_ledger as _i46_domain_ledger
        from terrain_pipeline.surface_hydraulics import run_domain as _i46_run_domain
        window, domain, height, _, _ = self.build()
        rates = _i46_np.full((4, domain['source_matrix'].shape[0]), 25.0)
        result = _i46_run_domain(domain, initial_depth_m=_i46_np.zeros(height.shape), interval_s=900.0, intervals=4, discharge_per_interval=rates, source_identity='test', forcing_identity='f', budget=FAST, snapshot_interval_s=900.0)
        self.assertEqual(result['metadata']['status'], 'completed')
        depth = _i46_np.asarray(result['arrays']['depth_m'], _i46_np.float64)
        self.assertGreaterEqual(float(depth.min()), 0.0)
        ledger = _i46_domain_ledger(result, spacing_m=60.0, declared_injection_m3=float(rates.sum() * 900.0))
        self.assertLess(abs(ledger['residual_m3']), 1e-06 * max(ledger['initial_storage_m3'], 1.0))
        self.assertTrue(ledger['injection_matches_source'])

    def test_no_boundary_face_draws_water_in(self):
        from terrain_pipeline.surface_hydraulics import run_domain as _i46_run_domain
        window, domain, height, _, _ = self.build()
        rates = _i46_np.full((4, domain['source_matrix'].shape[0]), 25.0)
        result = _i46_run_domain(domain, initial_depth_m=_i46_np.zeros(height.shape), interval_s=900.0, intervals=4, discharge_per_interval=rates, source_identity='test', forcing_identity='f', budget=FAST, snapshot_interval_s=900.0)
        self.assertEqual(float(result['metadata']['boundary_input_m3']), 0.0)

    def test_residual_after_recession_cannot_exceed_what_was_supplied(self):
        from terrain_pipeline.surface_hydraulics import residual_wetland as _i46_residual_wetland
        from terrain_pipeline.surface_hydraulics import run_domain as _i46_run_domain
        window, domain, height, _, _ = self.build()
        rates = _i46_np.full((6, domain['source_matrix'].shape[0]), 20.0)
        result = _i46_run_domain(domain, initial_depth_m=_i46_np.zeros(height.shape), interval_s=900.0, intervals=6, discharge_per_interval=rates, source_identity='test', forcing_identity='f', budget=FAST, snapshot_interval_s=900.0)
        depth = _i46_np.asarray(result['arrays']['depth_m'], _i46_np.float64)
        supplied = float(result['metadata']['supplied_m3'])
        final_volume = float(depth[-1].sum() * 60.0 ** 2)
        self.assertLessEqual(final_volume, supplied * (1.0 + 1e-09))
        carved = channel_mask(*height.shape, half=0).astype(_i46_np.float64)
        residual = _i46_residual_wetland(depth[-1], spacing_m=60.0, carved_depth_m=carved)
        self.assertLessEqual(residual['residual_volume_m3'], supplied * (1.0 + 1e-09))

    def test_interval_count_mismatch_is_refused(self):
        from terrain_pipeline.surface_hydraulics import run_domain as _i46_run_domain
        window, domain, height, _, _ = self.build()
        rates = _i46_np.zeros((3, domain['source_matrix'].shape[0]))
        with self.assertRaises(ValueError):
            _i46_run_domain(domain, initial_depth_m=_i46_np.zeros(height.shape), interval_s=900.0, intervals=5, discharge_per_interval=rates, source_identity='test', forcing_identity='f', budget=FAST)

class StatisticsTests(_i46_unittest.TestCase):

    def test_wet_area_uses_the_threshold_and_the_cell_area(self):
        from terrain_pipeline.surface_hydraulics import extent_statistics as _i46_extent_statistics
        depth = _i46_np.zeros((4, 4), _i46_np.float64)
        depth[0, 0] = 0.5
        depth[0, 1] = 0.005
        stats = _i46_extent_statistics(depth, spacing_m=10.0, carved_depth_m=_i46_np.zeros((4, 4)))
        self.assertEqual(stats['wet_cells'], 1)
        self.assertAlmostEqual(stats['wet_area_m2'], 100.0)
        self.assertAlmostEqual(stats['max_depth_m'], 0.5)

    def test_overbank_area_excludes_the_carved_cross_section(self):
        from terrain_pipeline.surface_hydraulics import extent_statistics as _i46_extent_statistics
        depth = _i46_np.full((4, 4), 1.0, _i46_np.float64)
        carved = _i46_np.zeros((4, 4))
        carved[:, 1] = 0.4
        stats = _i46_extent_statistics(depth, spacing_m=10.0, carved_depth_m=carved)
        self.assertAlmostEqual(stats['channel_wet_area_m2'], 4 * 100.0)
        self.assertAlmostEqual(stats['overbank_wet_area_m2'], 12 * 100.0)

    def test_negative_depth_is_refused(self):
        from terrain_pipeline.surface_hydraulics import extent_statistics as _i46_extent_statistics
        depth = _i46_np.zeros((2, 2))
        depth[0, 0] = -1.0
        with self.assertRaises(ValueError):
            _i46_extent_statistics(depth, spacing_m=10.0, carved_depth_m=_i46_np.zeros((2, 2)))

    def test_residual_wetland_only_counts_outside_the_carve(self):
        from terrain_pipeline.surface_hydraulics import residual_wetland as _i46_residual_wetland
        depth = _i46_np.zeros((4, 4), _i46_np.float64)
        depth[1, 1] = 0.5
        depth[2, 2] = 0.3
        carved = _i46_np.zeros((4, 4))
        carved[1, 1] = 0.4
        residual = _i46_residual_wetland(depth, spacing_m=10.0, carved_depth_m=carved)
        self.assertEqual(residual['residual_cells'], 1)
        self.assertAlmostEqual(residual['residual_volume_m3'], 0.3 * 100.0)

class HydrographTests(_i46_unittest.TestCase):

    def test_volume_is_converted_by_dividing_by_the_interval(self):
        from terrain_pipeline.surface_hydraulics import hydrograph as _i46_hydrograph
        rates = _i46_hydrograph(_i46_np.array([[7200.0], [3600.0]]), 3600.0)
        _i46_np.testing.assert_allclose(rates[:, 0], [2.0, 1.0])
        self.assertGreater(rates[0, 0], 0.0)

    def test_wrong_rank_is_refused(self):
        from terrain_pipeline.surface_hydraulics import hydrograph as _i46_hydrograph
        with self.assertRaises(ValueError):
            _i46_hydrograph(_i46_np.array([1.0, 2.0]), 3600.0)

class ReachCouplingTests(_i46_unittest.TestCase):
    """The reach-side helpers the runner uses to build the injection hydrograph."""

    def test_substeps_are_binned_by_physical_time_not_by_step_count(self):
        from tools.run_floodplain_2d import aggregate_reach_outgoing
        seconds = _i46_np.array([0.0, 1200.0, 3000.0, 4200.0])
        outgoing = _i46_np.zeros((4, 2))
        outgoing[0, 0] = 10.0
        outgoing[1, 0] = 20.0
        outgoing[2, 0] = 30.0
        outgoing[3, 1] = 40.0
        volumes = aggregate_reach_outgoing(seconds, outgoing, [0, 1], interval_s=3600.0, intervals=3)
        _i46_np.testing.assert_allclose(volumes[:, 0], [60.0, 0.0, 0.0])
        _i46_np.testing.assert_allclose(volumes[:, 1], [0.0, 40.0, 0.0])
        dense = _i46_np.array([0.0, 300.0, 600.0, 900.0, 3000.0, 4200.0])
        spread = _i46_np.zeros((6, 2))
        for row, value in zip((0, 1, 2, 4), (10.0, 20.0, 15.0, 15.0)):
            spread[row, 0] = value
        spread[5, 1] = 40.0
        same = aggregate_reach_outgoing(dense, spread, [0, 1], interval_s=3600.0, intervals=3)
        _i46_np.testing.assert_allclose(same, volumes)

    def test_negative_transfer_is_refused(self):
        from tools.run_floodplain_2d import aggregate_reach_outgoing
        outgoing = _i46_np.zeros((2, 1))
        outgoing[0, 0] = -1.0
        with self.assertRaises(ValueError):
            aggregate_reach_outgoing(_i46_np.array([0.0, 100.0]), outgoing, [0], interval_s=3600.0, intervals=1)

class MergedLedgerTests(_i46_unittest.TestCase):
    """The merge must not count the injected volume twice."""

    def test_injected_volume_is_an_internal_transfer_not_an_input_or_export(self):
        from tools.run_floodplain_2d import merged_ledger
        two_d = {'initial_storage_m3': 100.0, 'injected_m3': 500.0, 'boundary_input_m3': 0.0, 'boundary_output_m3': 50.0, 'final_storage_m3': 550.0}
        sub = {'initial_storage_m3': 20.0, 'local_input_m3': 600.0, 'boundary_input_m3': 0.0, 'export_to_two_dimensional_m3': 500.0, 'final_storage_m3': 120.0}
        merged = merged_ledger(two_d, sub, local_runoff_inside_domain_m3=7.0)
        self.assertAlmostEqual(merged['input_m3'], 600.0)
        self.assertAlmostEqual(merged['export_m3'], 50.0)
        self.assertAlmostEqual(merged['initial_storage_m3'], 120.0)
        self.assertAlmostEqual(merged['final_storage_m3'], 670.0)
        self.assertAlmostEqual(merged['residual_m3'], 0.0)
        self.assertAlmostEqual(merged['cancelled_internal_transfer_m3'], 500.0)
        self.assertIn('local_runoff_on_two_dimensional_domain_m3', merged['declared_out_of_scope'])

    def test_the_subledger_export_equals_the_two_dimensional_injection(self):
        from tools.run_floodplain_2d import merged_ledger
        two_d = {'initial_storage_m3': 0.0, 'injected_m3': 123.5, 'boundary_input_m3': 0.0, 'boundary_output_m3': 0.0, 'final_storage_m3': 123.5}
        sub = {'initial_storage_m3': 0.0, 'local_input_m3': 200.0, 'boundary_input_m3': 0.0, 'export_to_two_dimensional_m3': 123.5, 'final_storage_m3': 76.5}
        merged = merged_ledger(two_d, sub, local_runoff_inside_domain_m3=0.0)
        self.assertAlmostEqual(merged['cancelled_internal_transfer_m3'], sub['export_to_two_dimensional_m3'])
        self.assertLess(abs(merged['residual_m3']), 1e-09)

    def test_boundary_input_is_required_or_the_subledger_is_left_open(self):
        """The reach's declared truncated-upstream inflow must be counted.

        Dropping it left the real 72 h merged ledger open by 1.56e8 m3 (58 %), which
        this test pins so it cannot silently come back.
        """
        from tools.run_floodplain_2d import closed_reach_subledger
        intervals = 2
        node_volume = _i46_np.array([[10.0, 5.0], [36010.0, 5.0]])
        receiver = _i46_np.array([1, -1])
        outgoing = _i46_np.zeros((2, 2))
        products = {'water_volume_m3': node_volume, 'receiver': receiver, 'outgoing_volume_m3': outgoing, 'local_bucket_q_m3_s': _i46_np.array([[1.0, 0.0], [1.0, 0.0]]), 'boundary_q_m3_s': _i46_np.array([[4.0, 0.0], [4.0, 0.0]])}
        sub = closed_reach_subledger(products, _i46_np.array([False, True]))
        interval = sub['interval_s']
        self.assertAlmostEqual(sub['local_input_m3'], 2.0 * interval)
        self.assertAlmostEqual(sub['boundary_input_m3'], 8.0 * interval)
        self.assertLess(abs(sub['residual_m3']), 1e-06)
        without = dict(products, boundary_q_m3_s=_i46_np.zeros((2, 2)))
        leaky = closed_reach_subledger(without, _i46_np.array([False, True]))
        self.assertAlmostEqual(leaky['residual_m3'], 8.0 * interval)

    def test_subledger_reports_which_nodes_it_excluded(self):
        from tools.run_floodplain_2d import closed_reach_subledger
        products = {'water_volume_m3': _i46_np.array([[1.0, 2.0], [1.0, 2.0]]), 'receiver': _i46_np.array([1, -1]), 'outgoing_volume_m3': _i46_np.zeros((2, 2)), 'local_bucket_q_m3_s': _i46_np.zeros((2, 2)), 'boundary_q_m3_s': _i46_np.zeros((2, 2))}
        sub = closed_reach_subledger(products, _i46_np.array([False, True]))
        self.assertEqual(sub['excluded_nodes_inside_window'], [1])
