"""Consolidated test_surface_domain implementations; numeric expressions preserved."""
from __future__ import annotations
import unittest as _i47_unittest
import numpy as _i47_np
from concurrent.futures import ThreadPoolExecutor as _i48_ThreadPoolExecutor
from copy import deepcopy as _i48_deepcopy
import io as _i48_io
import json as _i48_json
import os as _i48_os
import tempfile as _i48_tempfile
import threading as _i48_threading
import unittest as _i48_unittest
from unittest.mock import patch as _i48_patch
import warnings as _i48_warnings
import zipfile as _i48_zipfile
from pathlib import Path as _i48_Path
import numpy as _i48_np
from numpy.lib import format as _i48_npy_format
from terrain_pipeline import surface_domain as _i48_preparation
from contextlib import ExitStack as _i49_ExitStack
from copy import deepcopy as _i49_deepcopy
from dataclasses import replace as _i49_replace
import hashlib as _i49_hashlib
import io as _i49_io
import json as _i49_json
from pathlib import Path as _i49_Path
import tempfile as _i49_tempfile
import unittest as _i49_unittest
from unittest.mock import patch as _i49_patch
import warnings as _i49_warnings
import zipfile as _i49_zipfile
import numpy as _i49_np
from terrain_pipeline import surface_domain as _i49_coast
import json as _i50_json
import tempfile as _i50_tempfile
import unittest as _i50_unittest
from pathlib import Path as _i50_Path
import copy as _i51_copy
import tempfile as _i51_tempfile
import unittest as _i51_unittest
from pathlib import Path as _i51_Path
from unittest.mock import patch as _i51_patch
import copy as _i52_copy
import json as _i52_json
import os as _i52_os
import stat as _i52_stat
import tempfile as _i52_tempfile
import unittest as _i52_unittest
from pathlib import Path as _i52_Path
from types import SimpleNamespace as _i52_SimpleNamespace
from unittest.mock import patch as _i52_patch
import numpy as _i52_np
from terrain_pipeline import surface_domain as _i52_readiness
from terrain_pipeline import surface_domain as _i52_surface_domain_prepare
from terrain_pipeline import surface_domain as _i52_surface_fine_mosaic
from terrain_pipeline import td_source as _i52_dem_domain
from terrain_pipeline import surface_domain as _i52_surface_coast_drop
from terrain_pipeline import surface_domain as _i52_surface_dynamic_prepare
from copy import deepcopy as _i53_deepcopy
from contextlib import ExitStack as _i53_ExitStack
from pathlib import Path as _i53_Path
import tempfile as _i53_tempfile
import unittest as _i53_unittest
from unittest.mock import patch as _i53_patch
import zipfile as _i53_zipfile
import io as _i53_io
import json as _i53_json
import numpy as _i53_np
from terrain_pipeline import surface_domain as _i53_mosaic
from terrain_pipeline import surface_domain as _i53_fine
from dataclasses import replace as _i54_replace
from contextlib import ExitStack as _i54_ExitStack
from copy import deepcopy as _i54_deepcopy
import json as _i54_json
import tempfile as _i54_tempfile
from pathlib import Path as _i54_Path
import unittest as _i54_unittest
import zipfile as _i54_zipfile
from unittest.mock import patch as _i54_patch
import numpy as _i54_np
from copy import deepcopy as _i63_deepcopy
from dataclasses import replace as _i63_replace
import json as _i63_json
from pathlib import Path as _i63_Path
import tempfile as _i63_tempfile
import unittest as _i63_unittest
from unittest.mock import patch as _i63_patch
import numpy as _i63_np
from builtins import ValueError as _i57__merged_mosaic_MosaicCoverageError
from contextlib import ExitStack as _i57_ExitStack
from copy import deepcopy as _i57_deepcopy
from dataclasses import replace as _i57_replace
import io as _i57_io
import json as _i57_json
from pathlib import Path as _i57_Path
import tempfile as _i57_tempfile
import unittest as _i57_unittest
from unittest.mock import patch as _i57_patch
import warnings as _i57_warnings
import zipfile as _i57_zipfile
import numpy as _i57_np
from terrain_pipeline import surface_domain as _i57_mosaic
from contextlib import ExitStack as _i55_ExitStack
from copy import deepcopy as _i55_deepcopy
from dataclasses import replace as _i55_replace
import io as _i55_io
import os as _i55_os
import json as _i55_json
from pathlib import Path as _i55_Path
import tempfile as _i55_tempfile
import unittest as _i55_unittest
from unittest.mock import patch as _i55_patch
import warnings as _i55_warnings
import zipfile as _i55_zipfile
import numpy as _i55_np
from terrain_pipeline import surface_hydraulics as _i55_hydraulics
from terrain_pipeline import surface_domain as _i55_adapter
from terrain_pipeline import surface_domain as _i55_mosaic
from contextlib import ExitStack as _i59_ExitStack
from copy import deepcopy as _i59_deepcopy
import io as _i59_io
from pathlib import Path as _i59_Path
import tempfile as _i59_tempfile
import unittest as _i59_unittest
from unittest.mock import patch as _i59_patch
import zipfile as _i59_zipfile
import numpy as _i59_np
from terrain_pipeline import surface_domain as _i59_mosaic
from terrain_pipeline import surface_domain as _i59_forest
from copy import deepcopy as _i56_deepcopy
from contextlib import ExitStack as _i56_ExitStack
from dataclasses import replace as _i56_replace
from functools import lru_cache as _i56_lru_cache
import hashlib as _i56_hashlib
import json as _i56_json
from pathlib import Path as _i56_Path
import tempfile as _i56_tempfile
import unittest as _i56_unittest
import zipfile as _i56_zipfile
from unittest.mock import patch as _i56_patch
import numpy as _i56_np
from terrain_pipeline import surface_domain as _i56_coast
from terrain_pipeline import surface_domain as _i56_engineering
from terrain_pipeline import surface_domain as _i56_mosaic
from terrain_pipeline import surface_domain as _i56_forest
from contextlib import ExitStack as _i58_ExitStack
from copy import deepcopy as _i58_deepcopy
from functools import lru_cache as _i58_lru_cache
import hashlib as _i58_hashlib
import json as _i58_json
from pathlib import Path as _i58_Path
import tempfile as _i58_tempfile
import unittest as _i58_unittest
import warnings as _i58_warnings
from unittest.mock import patch as _i58_patch
import zipfile as _i58_zipfile
import numpy as _i58_np
from terrain_pipeline import surface_domain as _i58_coast
from terrain_pipeline import surface_domain as _i58_engineering
from terrain_pipeline import surface_domain as _i58_coverage
from contextlib import ExitStack as _i60_ExitStack
from copy import deepcopy as _i60_deepcopy
from dataclasses import replace as _i60_replace
import json as _i60_json
import os as _i60_os
from pathlib import Path as _i60_Path
import tempfile as _i60_tempfile
import unittest as _i60_unittest
from unittest.mock import patch as _i60_patch
import numpy as _i60_np
import unittest as _i61_unittest
import numpy as _i61_np
import tempfile as _i62_tempfile
import unittest as _i62_unittest
from pathlib import Path as _i62_Path
import json as _i62_json
import numpy as _i62_np
import tempfile as _i64_tempfile
import json as _i64_json
from pathlib import Path as _i64_Path
import shutil as _i64_shutil
import unittest as _i64_unittest
import zipfile as _i64_zipfile
from unittest.mock import patch as _i64_patch
import numpy as _i64_np
from terrain_pipeline import surface_domain as _i64_tiles
from contextlib import ExitStack as _i65_ExitStack
from copy import deepcopy as _i65_deepcopy
from functools import lru_cache as _i65_lru_cache
import json as _i65_json
from pathlib import Path as _i65_Path
import tempfile as _i65_tempfile
import unittest as _i65_unittest
import zipfile as _i65_zipfile
from unittest.mock import patch as _i65_patch
import numpy as _i65_np
from terrain_pipeline import surface_domain as _i65_mosaic
from terrain_pipeline import surface_domain as _i65_forest
from terrain_pipeline import surface_domain as _i65_storage
from tests.test_surface_hydraulics import confluence_plan as _x3_confluence_plan
from tests.test_surface_hydraulics import confluence_plan as _x4_confluence_plan
CATEGORY = 'B'

class FineDomainMosaicTests(_i47_unittest.TestCase):

    def setUp(self):
        self.bed = _i47_np.zeros((4, 4), _i47_np.float64)
        self.depth = _i47_np.full((4, 4), 0.5, _i47_np.float64)
        self.owner = _i47_np.arange(16).reshape(4, 4)

    def mosaic(self):
        from terrain_pipeline.surface_domain import partition_saved_window as _i47_partition_saved_window
        return _i47_partition_saved_window(self.bed, self.depth, self.owner, row_cuts=(2,), column_cuts=(2,), version='t0')

    def test_four_domains_cover_inventory_and_unique_seams(self):
        from terrain_pipeline.surface_domain import audit_saved_mosaic as _i47_audit_saved_mosaic
        result = _i47_audit_saved_mosaic(self.mosaic(), self.bed, self.depth, spacing_m=1.0, version='t0')
        self.assertEqual(result['domain_volume_m3'], [2.0, 2.0, 2.0, 2.0])
        self.assertEqual(result['total_volume_m3'], 8.0)
        self.assertEqual(result['shared_face_segments'], 8)
        self.assertEqual(result['mosaic_volume_residual_m3'], 0.0)

    def test_signed_exchange_keeps_reverse_volume_and_global_balance(self):
        from terrain_pipeline.surface_domain import account_shared_transfers as _i47_account_shared_transfers
        mosaic = self.mosaic()
        transfers = _i47_np.zeros(8, _i47_np.float64)
        transfers[0] = 3.0
        transfers[2] = -2.0
        actual = _i47_account_shared_transfers(mosaic, transfers)
        _i47_np.testing.assert_array_equal(actual, [-3.0, 3.0, 2.0, -2.0])
        self.assertEqual(actual.sum(), 0.0)

    def test_halo_copies_cannot_change_after_source_mutation(self):
        from terrain_pipeline.surface_domain import audit_saved_mosaic as _i47_audit_saved_mosaic
        mosaic = self.mosaic()
        self.depth[:] = 1.0
        self.assertEqual(mosaic['windows'][0].depth_m[0, 0], 0.5)
        with self.assertRaises(ValueError):
            mosaic['windows'][0].depth_m.setflags(write=True)
        with self.assertRaisesRegex(ValueError, 'stale halo'):
            _i47_audit_saved_mosaic(mosaic, self.bed, self.depth, spacing_m=1.0, version='t0')

    def test_mixed_versions_and_cut_through_coarse_leaf_rejected(self):
        from terrain_pipeline.surface_domain import partition_saved_window as _i47_partition_saved_window
        from terrain_pipeline.surface_domain import audit_saved_mosaic as _i47_audit_saved_mosaic
        with self.assertRaisesRegex(ValueError, 'version'):
            _i47_audit_saved_mosaic(self.mosaic(), self.bed, self.depth, spacing_m=1.0, version='t1')
        with self.assertRaisesRegex(ValueError, 'splits'):
            _i47_partition_saved_window(self.bed, self.depth, _i47_np.zeros((4, 4), _i47_np.int64), column_cuts=(2,), version='t0')

    def test_invalid_cuts_and_nonfinite_source_rejected(self):
        from terrain_pipeline.surface_domain import partition_saved_window as _i47_partition_saved_window
        with self.assertRaises(ValueError):
            _i47_partition_saved_window(self.bed, self.depth, self.owner, row_cuts=(2, 2), version='t0')
        self.depth[0, 0] = _i47_np.nan
        with self.assertRaises(ValueError):
            self.mosaic()

    def fan(self):
        corners = []
        vertices = [[column, 0.0, row] for row in range(5) for column in range(5)]
        triangles = []
        for row in range(4):
            for column in range(4):
                ids = [row * 5 + column, (row + 1) * 5 + column, (row + 1) * 5 + column + 1, row * 5 + column + 1]
                center = len(vertices)
                vertices.append([column + 0.5, 0.0, row + 0.5])
                corners.append(ids)
                triangles.extend([[ids[index], ids[(index + 1) % 4], center] for index in range(4)])
        bed = _i47_np.array(vertices)
        water = bed.copy()
        water[:, 1] = 0.5
        return dict(cell_corner_vertex_ids=_i47_np.array(corners), bed_vertices_xyz_m=bed, water_vertices_xyz_m=water, bed_triangles=_i47_np.array(triangles), wet_cell_ids=_i47_np.arange(16), water_triangles=_i47_np.array(triangles))

    def test_independent_meshes_keep_shared_xyz_and_wet_triangles(self):
        from terrain_pipeline.surface_domain import partition_fan_geometry as _i47_partition_fan_geometry
        source = self.fan()
        meshes, report = _i47_partition_fan_geometry(self.mosaic(), source)
        self.assertEqual(report['shared_vertex_count'], 9)
        self.assertEqual(report['max_water_seam_error_m'], 0.0)
        self.assertEqual(report['bed_triangle_count'], 64)
        self.assertEqual(report['water_triangle_count'], 64)
        self.assertEqual(sum((len(mesh['wet_cell_ids']) for mesh in meshes)), 16)
        source['water_vertices_xyz_m'][:] = 99.0
        self.assertEqual(meshes[0]['water_vertices_xyz_m'][0, 1], 0.5)

    def test_missing_wet_triangles_and_nonfinite_geometry_rejected(self):
        from terrain_pipeline.surface_domain import partition_fan_geometry as _i47_partition_fan_geometry
        source = self.fan()
        source['water_triangles'] = source['water_triangles'][:-1]
        with self.assertRaises(ValueError):
            _i47_partition_fan_geometry(self.mosaic(), source)
        source = self.fan()
        source['bed_vertices_xyz_m'][0, 1] = _i47_np.nan
        with self.assertRaises(ValueError):
            _i47_partition_fan_geometry(self.mosaic(), source)

    def test_saved_face_coordinate_conversion_and_original_order(self):
        from terrain_pipeline.surface_domain import bind_saved_leaf_faces as _i47_bind_saved_leaf_faces
        mosaic = self.mosaic()
        order = _i47_np.arange(8)[::-1]
        axes = mosaic['face_axis'][order]
        geometry = dict(face_axis=axes, face_canonical_row=mosaic['face_row'][order] + (axes == 1), face_canonical_column=mosaic['face_column'][order] + (axes == 0))
        _i47_np.testing.assert_array_equal(_i47_bind_saved_leaf_faces(mosaic, geometry), order)
        geometry = {name: values[:-1] for name, values in geometry.items()}
        with self.assertRaises(ValueError):
            _i47_bind_saved_leaf_faces(mosaic, geometry)

def bent_plan():
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i48_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i48_plan_channel
    height = _i48_np.full((7, 7), 10.0)
    height[1:6, 2:5] = 5.0 + _i48_np.arange(5, 0, -1)[:, None] * 0.1
    height[6, 3] = 4.0
    height.flat[[10, 16]] = 5.45
    receiver = _i48_np.full(49, -1, _i48_np.int64)
    outlet = _i48_np.ones((7, 7), bool)
    for donor, target in ((9, 16), (16, 17), (11, 10), (10, 17), (17, 25), (25, 31), (31, 38), (38, 45)):
        receiver[donor] = target
        outlet.flat[donor] = False
    order = _i48_np.array([cell for cell in range(49) if outlet.flat[cell]] + [38, 31, 25, 17, 16, 10, 9, 11], dtype=_i48_np.int64)
    discharge = _i48_np.full((7, 7), 0.01)
    discharge.flat[[9, 11, 17, 25, 31, 38, 45]] = 0.2
    discharge.flat[[9, 11]] = 0.1
    discharge.flat[[10, 16]] = 0.1
    recipe = _i48_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=8.0, min_width_m=8.0, max_width_m=8.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, max_cut_m=4.0, min_bed_slope_m_per_m=1e-05)
    return _i48_plan_channel(height, receiver, order, outlet, discharge, 10.0, 10.0, 0.0, 0.0, 0.0, 'bent-confluence', recipe)

def prepare_case(plan=None, centerline=None, budget=None, domain=None, protected=None, legal=None, spacing=1.0):
    from terrain_pipeline.channel_geometry import SmoothingRecipe as _i48_SmoothingRecipe
    from terrain_pipeline.channel_geometry import build_centerline as _i48_build_centerline
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _i48_InundationRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _i48_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _i48_SectionRecipe
    from terrain_pipeline.surface_domain import prepare_surface_centerline as _i48_prepare_surface_centerline
    from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i48_SurfaceNetworkBudget
    plan = bent_plan() if plan is None else plan
    centerline = _i48_build_centerline(plan, _i48_SmoothingRecipe(max_offset_m=10.0)) if centerline is None else centerline
    shape = (int(60 / spacing) + 1,) * 2
    domain = _i48_np.ones(shape, bool) if domain is None else domain
    protected = _i48_np.zeros(shape, bool) if protected is None else protected
    if legal is None:
        legal = _i48_np.zeros(shape, bool)
        legal[-1, int(27 / spacing):int(33 / spacing) + 1] = True
    budget = _i48_SurfaceNetworkBudget(4.0, 5000.0, 5000.0) if budget is None else budget
    return _i48_prepare_surface_centerline(plan, centerline, 0.0, 0.0, spacing, spacing, shape, domain, protected, legal, _i48_np.array([5.2]), _i48_SectionRecipe(), _i48_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i48_InundationRecipe(max_lateral_reach_m=15.0), budget)

def rehash_result(result):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i48_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i48_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i48_digest
    record = result['identity']
    record['parameters']['arrays_sha256'] = _i48_digest({name: _i48_array_hash(value) for name, value in result['arrays'].items()})
    record['parameters']['summary_sha256'] = _i48_digest(result['summary'])
    record['parameters']['component_sha256'] = {name: value['identity_sha256'] for name, value in result['components'].items()}
    identity = _i48_ArtifactIdentity(**record)
    result.update(identity=identity.record(), identity_sha256=identity.sha256)

def write_package(result, path):
    manifest = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'components', 'summary')}
    manifest['format_version'] = 1
    _i48_np.savez_compressed(path, manifest=_i48_json.dumps(manifest, sort_keys=True), **result['arrays'])

def replace_member(source, destination, name, contents, duplicate=False):
    with _i48_zipfile.ZipFile(source) as original, _i48_zipfile.ZipFile(destination, 'w') as rewritten:
        for member in original.infolist():
            rewritten.writestr(member.filename, contents if member.filename == name else original.read(member))
        if duplicate:
            with _i48_warnings.catch_warnings():
                _i48_warnings.simplefilter('ignore', UserWarning)
                rewritten.writestr(name, contents)

class SurfaceCenterlinePrepareTests(_i48_unittest.TestCase):

    def test_active_flow_conserves_at_confluence(self):
        arrays = bent_plan()['arrays']
        discharge = arrays['discharge_m3_s'].ravel()
        self.assertEqual(discharge[9], 0.1)
        self.assertEqual(discharge[11], 0.1)
        for target in (17, 25, 31, 38, 45):
            donors = _i48_np.flatnonzero(arrays['receiver'] == target)
            self.assertAlmostEqual(float(_i48_np.sum(discharge[donors])), discharge[target])

    def test_arrays_are_hard_readonly(self):
        from terrain_pipeline.surface_domain import load_surface_centerline as _i48_load_surface_centerline
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        from terrain_pipeline.surface_domain import slice_surface_centerline as _i48_slice_surface_centerline
        result = prepare_case()
        with _i48_tempfile.TemporaryDirectory() as directory:
            path = _i48_Path(directory) / 'result.npz'
            _i48_save_surface_centerline(result, path)
            for surface in (result, _i48_load_surface_centerline(path)):
                window = _i48_slice_surface_centerline(surface, slice(0, 30), slice(0, 30))
                for array in (*surface['arrays'].values(), *window['arrays'].values()):
                    with self.assertRaises(ValueError):
                        array.setflags(write=True)
                    ancestor = array.base
                    while isinstance(ancestor, _i48_np.ndarray):
                        with self.assertRaises(ValueError):
                            ancestor.setflags(write=True)
                        ancestor = ancestor.base

    def test_exact_sample_ignores_zero_weight_unknown(self):
        from terrain_pipeline.surface_domain import _sample
        field = _i48_np.array([[5.0, _i48_np.nan], [_i48_np.nan, _i48_np.nan]])
        value, valid = _sample(field, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0)
        self.assertTrue(valid)
        self.assertEqual(value, 5.0)

    def test_bent_confluence_replays_and_changes_actual_cut(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i48_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i48_build_centerline
        from terrain_pipeline.channel_geometry import SectionRecipe as _i48_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i48_evaluate_sections
        from terrain_pipeline.surface_domain import load_surface_centerline as _i48_load_surface_centerline
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        from terrain_pipeline.surface_domain import slice_surface_centerline as _i48_slice_surface_centerline
        plan = bent_plan()
        centerline = _i48_build_centerline(plan, _i48_SmoothingRecipe(max_offset_m=10.0))
        self.assertGreater(centerline['summary']['moved_nodes'], 0)
        geometry = centerline['arrays']
        _i48_np.testing.assert_array_equal(geometry['node_world_xz_m'][geometry['anchor_mask']], geometry['original_world_xz_m'][geometry['anchor_mask']])
        result = prepare_case(plan, centerline)
        self.assertEqual(result['status'], 'prepared', result['summary'])
        legacy = _i48_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (61, 61), _i48_np.zeros((61, 61), bool), _i48_SectionRecipe())
        moved = result['arrays']['section__actual_cut_m']
        self.assertFalse(_i48_np.array_equal(moved, legacy['arrays']['actual_cut_m']))
        self.assertEqual(result['summary']['max_stage_bed_error_m'], 0.0)
        self.assertGreater(result['summary']['max_edge_bed_error_m'], 0.0)
        self.assertTrue(_i48_preparation._outlet_connected(result['arrays']['flood__wet_mask'], result['arrays']['legal_outlet_mask']))
        weights = _i48_np.ones((61, 61))
        weights[[0, -1], :] *= 0.5
        weights[:, [0, -1]] *= 0.5
        self.assertAlmostEqual(float(_i48_np.sum(moved * weights)), result['summary']['cut_volume_m3'])
        self.assertEqual(float(_i48_np.sum((moved > 1e-09) * weights)), result['summary']['area_m2'])
        _i48_np.testing.assert_array_equal(plan['arrays']['source_height_m'], bent_plan()['arrays']['source_height_m'])
        with _i48_tempfile.TemporaryDirectory() as directory:
            path = _i48_Path(directory) / 'prepared.npz'
            _i48_save_surface_centerline(result, path)
            loaded = _i48_load_surface_centerline(path)
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])
            with self.assertRaises(FileExistsError):
                _i48_save_surface_centerline(result, path)
            first = _i48_slice_surface_centerline(loaded, slice(0, 40), slice(0, 40))
            second = _i48_slice_surface_centerline(loaded, slice(20, 61), slice(20, 61))
            for name in first['arrays']:
                _i48_np.testing.assert_array_equal(first['arrays'][name][20:40, 20:40], second['arrays'][name][:20, :20])
                self.assertFalse(first['arrays'][name].flags.writeable)

    def test_budget_and_masks_fail(self):
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i48_SurfaceNetworkBudget
        self.assertTrue(prepare_case(budget=_i48_SurfaceNetworkBudget(4.0, 1.0, 1.0))['summary']['budget_failures']['area'])
        domain = _i48_np.ones((61, 61), bool)
        domain[20, 30] = False
        self.assertEqual(prepare_case(domain=domain)['status'], 'diagnostic_not_publishable')
        protected = _i48_np.zeros((61, 61), bool)
        protected[20, 30] = True
        self.assertEqual(prepare_case(protected=protected)['status'], 'diagnostic_not_publishable')
        legal = _i48_np.zeros((61, 61), bool)
        self.assertEqual(prepare_case(legal=legal)['status'], 'diagnostic_not_publishable')

    def test_nonconservative_discharge_is_rejected_before_sections(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i48_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i48_build_centerline
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i48_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i48_plan_channel
        plan = bent_plan()
        params = plan['identity']['parameters']
        discharge = plan['arrays']['discharge_m3_s'].copy()
        discharge.flat[[9, 11]] = 0.2
        recipe = _i48_ChannelRecipe(**{name: params[name] for name in _i48_ChannelRecipe.__dataclass_fields__})
        plan = _i48_plan_channel(plan['arrays']['source_height_m'], plan['arrays']['receiver'], plan['arrays']['order'], plan['arrays']['outlet_mask'], discharge, 10.0, 10.0, 0.0, 0.0, 0.0, 'nonconservative', recipe)
        centerline = _i48_build_centerline(plan, _i48_SmoothingRecipe(max_offset_m=10.0))
        with _i48_patch.object(_i48_preparation, 'evaluate_sections') as sections:
            with self.assertRaisesRegex(ValueError, 'discharge conservation'):
                prepare_case(plan, centerline)
            sections.assert_not_called()

    def test_all_donors_including_inactive_are_counted(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i48_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i48_plan_channel
        plan = bent_plan()
        params = plan['identity']['parameters']
        receiver = plan['arrays']['receiver'].copy()
        receiver[18] = 17
        outlet = plan['arrays']['outlet_mask'].copy()
        outlet.flat[18] = False
        order = _i48_np.array([cell for cell in range(49) if outlet.flat[cell]] + [38, 31, 25, 17, 16, 10, 9, 11, 18], dtype=_i48_np.int64)
        recipe = _i48_ChannelRecipe(**{name: params[name] for name in _i48_ChannelRecipe.__dataclass_fields__})
        plan = _i48_plan_channel(plan['arrays']['source_height_m'], receiver, order, outlet, plan['arrays']['discharge_m3_s'], 10.0, 10.0, 0.0, 0.0, 0.0, 'inactive-donor', recipe)
        with self.assertRaisesRegex(ValueError, 'discharge conservation'):
            prepare_case(plan)

    def test_positive_local_inflow_is_allowed(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i48_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i48_plan_channel
        plan = bent_plan()
        params = plan['identity']['parameters']
        discharge = plan['arrays']['discharge_m3_s'].copy()
        discharge.flat[[17, 25, 31, 38, 45]] = 0.25
        recipe = _i48_ChannelRecipe(**{name: params[name] for name in _i48_ChannelRecipe.__dataclass_fields__})
        plan = _i48_plan_channel(plan['arrays']['source_height_m'], plan['arrays']['receiver'], plan['arrays']['order'], plan['arrays']['outlet_mask'], discharge, 10.0, 10.0, 0.0, 0.0, 0.0, 'local-inflow', recipe)
        self.assertEqual(prepare_case(plan)['status'], 'prepared')

    def test_positive_weight_support_cannot_cross_masks_unknown_or_dry(self):
        field = _i48_np.full((2, 2), 5.0)
        for name in ('domain', 'protected', 'dry', 'unknown'):
            with self.subTest(name=name):
                sampled = field.copy()
                support = _i48_np.ones((2, 2), bool)
                if name == 'unknown':
                    sampled[0, 1] = _i48_np.nan
                else:
                    support[0, 1] = False
                diagnostics = {key: 0 for key in ('outside_grid', 'domain', 'protected', 'dry', 'unknown')}
                value, valid = _i48_preparation._sample(sampled, 1e-14, 0.0, 0.0, 0.0, 1.0, 1.0, (support,), diagnostics, (name,))
                self.assertFalse(valid)
                self.assertIsNone(value)
                self.assertEqual(diagnostics[name], 1)
        self.assertEqual(_i48_preparation._sample(field, -1.0, 0.0, 0.0, 0.0, 1.0, 1.0), (None, False))

    def test_subgrid_domain_and_protection_are_diagnostic(self):
        domain = _i48_np.ones((61, 61), bool)
        domain[11, 21] = False
        protected = _i48_np.zeros((61, 61), bool)
        protected[11, 21] = True
        for reason, result in (('domain', prepare_case(domain=domain)), ('protected', prepare_case(protected=protected))):
            self.assertEqual(result['status'], 'diagnostic_not_publishable')
            self.assertGreater(result['summary']['support_failures'][reason], 0)
            self.assertTrue(result['summary']['budget_failures']['edge_support'])

    def test_actual_water_depth_and_dry_unknown_support_gate(self):
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i48_StageRecipe
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i48_SurfaceNetworkBudget
        result = prepare_case()
        components = {group: {**metadata, 'arrays': {name.split('__', 1)[1]: value.copy() for name, value in result['arrays'].items() if name.startswith(group + '__')}} for group, metadata in result['components'].items()}
        budget = _i48_SurfaceNetworkBudget(4.0, 5000.0, 5000.0)
        stage_recipe = _i48_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0)
        final = components['section']['arrays']['bounded_surface_m']
        for depth, expected in ((0.1, 'edge_clearance'), (4.1, 'edge_max_depth')):
            flood = _i48_deepcopy(components['flood'])
            wet = flood['arrays']['wet_mask']
            flood['arrays']['water_surface_m'][wet] = final[wet] + depth
            failures, _ = _i48_preparation._geometry_gate(components['plan'], components['centerline'], components['section'], components['stage'], flood, budget, stage_recipe)
            self.assertTrue(failures[expected])
        for reason in ('dry', 'unknown'):
            flood = _i48_deepcopy(components['flood'])
            if reason == 'dry':
                flood['arrays']['wet_mask'][11, 21] = False
            else:
                flood['arrays']['water_surface_m'][11, 21] = _i48_np.nan
            failures, metrics = _i48_preparation._geometry_gate(components['plan'], components['centerline'], components['section'], components['stage'], flood, budget, stage_recipe)
            self.assertTrue(failures['edge_support'])
            self.assertGreater(metrics['support_failures'][reason], 0)

    def test_resolution_failure_keeps_original_tolerance_and_diagnostic_roundtrip(self):
        from terrain_pipeline.surface_domain import load_surface_centerline as _i48_load_surface_centerline
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        from terrain_pipeline.surface_domain import slice_surface_centerline as _i48_slice_surface_centerline
        result = prepare_case(spacing=2.0)
        self.assertEqual(result['status'], 'diagnostic_not_publishable')
        self.assertTrue(result['summary']['needs_finer_grid'])
        self.assertTrue(result['summary']['budget_failures']['stage_bed_mismatch'])
        self.assertEqual(result['identity']['parameters']['budget']['bed_match_tolerance_m'], 1e-06)
        with _i48_tempfile.TemporaryDirectory() as directory:
            path = _i48_Path(directory) / 'diagnostic.npz'
            with self.assertRaises(ValueError):
                _i48_save_surface_centerline(result, path)
            self.assertFalse(path.exists())
            _i48_save_surface_centerline(result, path, allow_diagnostic=True)
            with self.assertRaises(ValueError):
                _i48_load_surface_centerline(path)
            loaded = _i48_load_surface_centerline(path, allow_diagnostic=True)
            self.assertEqual(loaded['summary'], result['summary'])
            with self.assertRaises(ValueError):
                _i48_slice_surface_centerline(loaded, slice(0, 10), slice(0, 10))

    def test_plan_and_centerline_identity_status_geometry_and_summary_replay(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i48_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i48_build_centerline
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i48_ArtifactIdentity
        for group, mutation in (('plan', 'identity'), ('plan', 'status'), ('plan', 'geometry'), ('centerline', 'identity'), ('centerline', 'status'), ('centerline', 'geometry'), ('centerline', 'summary')):
            with self.subTest(group=group, mutation=mutation):
                plan = bent_plan()
                centerline = _i48_build_centerline(plan, _i48_SmoothingRecipe(max_offset_m=10.0))
                component = _i48_deepcopy(plan if group == 'plan' else centerline)
                if mutation == 'identity':
                    component['identity']['backend'] = 'other-backend'
                    identity = _i48_ArtifactIdentity(**component['identity'])
                    component.update(identity=identity.record(), identity_sha256=identity.sha256)
                elif mutation == 'status':
                    component['status'] = 'prepared'
                elif mutation == 'summary':
                    component['summary']['moved_nodes'] = 0
                elif group == 'plan':
                    component['arrays']['bounded_bed_m'].flat[17] += 0.2
                else:
                    component['arrays']['node_world_xz_m'][3, 0] += 0.2
                with self.assertRaises(ValueError):
                    prepare_case(component if group == 'plan' else plan, component if group == 'centerline' else centerline)

    def test_rehashed_package_geometry_summary_status_and_extra_fields_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_centerline as _i48_load_surface_centerline
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i48_ArtifactIdentity
        original = prepare_case()
        for mutation in ('bed', 'wet', 'summary', 'status', 'component-status', 'component-summary', 'component-identity', 'extra-array', 'dtype'):
            with self.subTest(mutation=mutation), _i48_tempfile.TemporaryDirectory() as directory:
                result = _i48_deepcopy(original)
                if mutation == 'bed':
                    result['arrays']['section__bounded_surface_m'][30, 38] += 0.1
                elif mutation == 'wet':
                    result['arrays']['flood__wet_mask'][11, 21] = False
                elif mutation == 'summary':
                    result['summary']['area_m2'] += 1.0
                elif mutation == 'status':
                    result['status'] = 'diagnostic_not_publishable'
                elif mutation == 'component-status':
                    result['components']['stage']['status'] = 'prepared'
                elif mutation == 'component-summary':
                    result['components']['section']['summary']['actual_cut_volume_m3'] += 1.0
                elif mutation == 'component-identity':
                    record = result['components']['flood']['identity']
                    record['backend'] = 'other-backend'
                    identity = _i48_ArtifactIdentity(**record)
                    result['components']['flood'].update(identity=identity.record(), identity_sha256=identity.sha256)
                elif mutation == 'extra-array':
                    result['arrays']['unused'] = _i48_np.zeros(1)
                else:
                    result['arrays']['domain_mask'] = result['arrays']['domain_mask'].astype(_i48_np.uint8)
                rehash_result(result)
                path = _i48_Path(directory) / 'rehashed.npz'
                write_package(result, path)
                with self.assertRaises(ValueError):
                    _i48_load_surface_centerline(path, allow_diagnostic=True)
                with self.assertRaises(ValueError):
                    _i48_save_surface_centerline(result, _i48_Path(directory) / 'saved.npz', allow_diagnostic=True)

    def test_resource_limits_precede_expensive_preparation(self):
        for constant, limit, options in (('MAX_FINE_NODES', 100, {}), ('MAX_FINE_NODES', 40, {'spacing': 10.0}), ('MAX_GRAPH_NODES', 6, {}), ('MAX_EDGE_SAMPLES', 10, {})):
            with self.subTest(constant=constant, options=options):
                with _i48_patch.object(_i48_preparation, constant, limit), _i48_patch.object(_i48_preparation, 'evaluate_sections') as sections:
                    with self.assertRaisesRegex(ValueError, 'resource limit'):
                        prepare_case(**options)
                    sections.assert_not_called()
        for options in ({'domain': _i48_np.ones((61, 61))}, {'protected': _i48_np.zeros((2, 2), bool)}, {'spacing': float('inf')}, {'spacing': -1.0}):
            with self.assertRaises((ValueError, OverflowError)):
                prepare_case(**options)

    def test_zip_and_npy_preflight_before_numpy_load(self):
        from terrain_pipeline.surface_domain import load_surface_centerline as _i48_load_surface_centerline
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        result = prepare_case()
        with _i48_tempfile.TemporaryDirectory() as directory:
            source = _i48_Path(directory) / 'source.npz'
            _i48_save_surface_centerline(result, source)
            with _i48_zipfile.ZipFile(source) as archive:
                original = archive.read('domain_mask.npy')
            oversized = _i48_io.BytesIO()
            _i48_npy_format.write_array_header_1_0(oversized, {'descr': '<f8', 'fortran_order': False, 'shape': (_i48_preparation.MAX_FINE_NODES * 20 + 1,)})
            objects = _i48_io.BytesIO()
            _i48_np.save(objects, _i48_np.array([object()], dtype=object), allow_pickle=True)
            for name, contents, duplicate in (('truncated', original[:-1], False), ('extra-bytes', original + b'extra', False), ('oversized', oversized.getvalue(), False), ('object', objects.getvalue(), False), ('duplicate', original, True)):
                with self.subTest(name=name):
                    path = _i48_Path(directory) / (name + '.npz')
                    replace_member(source, path, 'domain_mask.npy', contents, duplicate)
                    with _i48_patch.object(_i48_preparation.np, 'load') as loader:
                        with self.assertRaises(ValueError):
                            _i48_load_surface_centerline(path)
                        loader.assert_not_called()
            for constant, limit in (('MAX_PACKAGE_BYTES', 100), ('MAX_ARCHIVE_MEMBERS', 2), ('MAX_MANIFEST_BYTES', 100)):
                with _i48_patch.object(_i48_preparation, constant, limit), _i48_patch.object(_i48_preparation.np, 'load') as loader:
                    with self.assertRaises(ValueError):
                        _i48_load_surface_centerline(source)
                    loader.assert_not_called()

    def test_atomic_save_race_has_one_winner_and_no_partial_files(self):
        from terrain_pipeline.surface_domain import load_surface_centerline as _i48_load_surface_centerline
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        result = prepare_case()
        barrier = _i48_threading.Barrier(2)
        real_link = _i48_os.link

        def contested_link(source, destination):
            barrier.wait(timeout=10)
            return real_link(source, destination)
        with _i48_tempfile.TemporaryDirectory() as directory:
            destination = _i48_Path(directory) / 'winner.npz'
            with _i48_patch.object(_i48_preparation.os, 'link', side_effect=contested_link):
                with _i48_ThreadPoolExecutor(max_workers=2) as workers:
                    futures = [workers.submit(_i48_save_surface_centerline, result, destination) for _ in range(2)]
                    successes, conflicts = (0, 0)
                    for future in futures:
                        try:
                            self.assertEqual(future.result(timeout=15), destination)
                            successes += 1
                        except FileExistsError:
                            conflicts += 1
            self.assertEqual((successes, conflicts), (1, 1))
            self.assertEqual(list(_i48_Path(directory).iterdir()), [destination])
            self.assertEqual(_i48_load_surface_centerline(destination)['identity_sha256'], result['identity_sha256'])

    def test_failed_save_cleans_temporary_and_preserves_existing_target(self):
        from terrain_pipeline.surface_domain import save_surface_centerline as _i48_save_surface_centerline
        result = prepare_case()
        with _i48_tempfile.TemporaryDirectory() as directory:
            destination = _i48_Path(directory) / 'result.npz'
            with _i48_patch.object(_i48_preparation.np, 'savez_compressed', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    _i48_save_surface_centerline(result, destination)
            self.assertEqual(list(_i48_Path(directory).iterdir()), [])
            _i48_save_surface_centerline(result, destination)
            contents = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                _i48_save_surface_centerline(result, destination)
            self.assertEqual(contents, destination.read_bytes())

    def test_slices_are_bounded_and_do_not_generate(self):
        from terrain_pipeline.surface_domain import slice_surface_centerline as _i48_slice_surface_centerline
        result = prepare_case()
        with _i48_patch.object(_i48_preparation, 'prepare_surface_centerline', side_effect=AssertionError('must not generate')):
            window = _i48_slice_surface_centerline(result, slice(20, 40), slice(10, 30))
        self.assertEqual((window['origin_x_m'], window['origin_z_m']), (10.0, 20.0))
        for selection in (slice(None, 10), slice(-1, 10), slice(1, 62), slice(1, 10, 2), slice(2, 2), 1):
            with self.assertRaises(ValueError):
                _i48_slice_surface_centerline(result, selection, slice(0, 10))
ROOT = _i49_Path(__file__).resolve().parents[1]
SAVED_PREPARED = ROOT / 'verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz'
SAVED_PREPARED_SHA256 = 'dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af'

def fixed_drop_inputs(prepared=None):
    from terrain_pipeline.surface_domain import load_surface_domains as _i49_load_surface_domains
    from terrain_pipeline.surface_domain import _payload as _i49__payload
    if prepared is None:
        prepared = _i49_load_surface_domains(SAVED_PREPARED)
    datum = prepared['candidate']['inputs']['vertical_datum']
    section = _i49_np.column_stack((_i49_np.arange(38.0, 42.0), _i49_np.full(4, 70.0)))
    attachment = _i49_coast.RiverAttachment(prepared, 1, section, 2, datum)
    recovery = next((entry['recovery'] for entry in prepared['domains'] if entry['domain_id'] == 1))
    payload = _i49__payload(recovery)
    bed_start = payload['final_surface_m'][60, 28:32]
    water_start = payload['water_surface_m'][60, 28:32]
    h0_start = payload['source_surface_m'][60, 28:32]
    stations = _i49_np.arange(70.0, 91.0)
    fraction = _i49_np.linspace(0.0, 1.0, len(stations))[:, None]
    bed = (1 - fraction) * bed_start + fraction * -0.5
    water = (1 - fraction) * water_start
    h0 = (1 - fraction) * h0_start + fraction * -0.25
    shape = bed.shape
    corridor = _i49_coast.EngineeringSource('corridor', 'explicit-new-engineering-coastal-strip-not-original-dem', datum, 38.0, 70.0, 1.0, 1.0, h0, bed, water, _i49_np.ones(shape, bool), _i49_np.zeros(shape, bool), _i49_np.zeros(shape, bool), _i49_np.ones(shape, bool), _i49_np.zeros(shape, bool), 0.0)
    sea_shape = (2, 4)
    sea = _i49_coast.EngineeringSource('sea', 'explicit-new-engineering-sea-patch-not-observed-coast', datum, 38.0, 90.0, 1.0, 1.0, _i49_np.full(sea_shape, -0.25), _i49_np.full(sea_shape, -0.5), _i49_np.zeros(sea_shape), _i49_np.ones(sea_shape, bool), _i49_np.zeros(sea_shape, bool), _i49_np.zeros(sea_shape, bool), _i49_np.ones(sea_shape, bool), _i49_np.ones(sea_shape, bool), 0.0)
    return (attachment, corridor, sea, stations, _i49_coast.DropBudget(4.0, 100.0))

def reseal(result):
    from terrain_pipeline.surface_identity import _plain as _i49__merged_coast__plain
    from terrain_pipeline.surface_identity import _freeze as _i49__merged_coast__freeze
    plain = _i49__merged_coast__plain(result)
    plain.pop('identity_sha256', None)
    plain['identity_sha256'] = _i49_coast.fingerprint(plain)
    return _i49__merged_coast__freeze(plain)

def changed_source(source, **changes):
    return _i49_replace(source, **changes)

def rehash_artifact(artifact):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i49_ArtifactIdentity
    identity = artifact['identity']
    updated = _i49_ArtifactIdentity(**identity)
    artifact['identity'] = updated.record()
    artifact['identity_sha256'] = updated.sha256

def coherent_source_forgery(result, mode):
    from terrain_pipeline.surface_identity import _plain as _i49__merged_coast__plain
    from terrain_pipeline.artifacts.contracts import array_hash as _i49_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i49_digest
    forged = _i49_deepcopy(_i49__merged_coast__plain(result))
    prepared = forged['inputs']['attachment']['prepared']
    proof = prepared['domains'][0]['recovery']
    surface = proof['surface']
    if mode == 'water':
        surface['arrays']['water_surface_m'][60, 28] += 0.01
        surface['identity']['parameters']['output_sha256'] = _i49_digest({name: _i49_array_hash(array) for name, array in surface['arrays'].items()})
        surface['identity']['parameters']['summary_sha256'] = _i49_digest(surface['summary'])
        rehash_artifact(surface)
        ledger = proof['fine_ledger']
        if ledger is not None:
            ledger['identity']['parameters']['surface_identity_sha256'] = surface['identity_sha256']
            rehash_artifact(ledger)
        forged['proof_support']['payload']['water_surface_m'][60, 28] += 0.01
        fraction = _i49_np.linspace(1.0, 0.0, 21)
        forged['arrays']['water_xyz_m'][::4, 1] += 0.01 * fraction
        forged['attachment']['river_water_xyz_m'] = forged['arrays']['water_xyz_m'][:4].copy()
        corridor = forged['inputs']['corridor']
        corridor['water_m'][:, 0] += 0.01 * fraction
        corridor['identity_sha256'] = _i49_coast.fingerprint({key: value for key, value in corridor.items() if key != 'identity_sha256'})
    elif mode in ('Q', 'H0'):
        plan = proof['inputs']['plan']
        name = 'discharge_m3_s' if mode == 'Q' else 'source_height_m'
        plan['arrays'][name] += 0.001
        parameter = 'source_discharge_sha256' if mode == 'Q' else 'source_height_sha256'
        plan['identity']['parameters'][parameter] = _i49_array_hash(plan['arrays'][name])
        rehash_artifact(plan)
    elif mode == 'grid':
        proof['inputs']['fine']['origin_x_m'] += 1.0
        prepared['configurations']['1']['fine']['origin_x_m'] += 1.0
        plan = proof['inputs']['plan']
        plan['identity']['parameters']['origin_x_m'] += 1.0
        rehash_artifact(plan)
    else:
        raise ValueError(mode)
    proof['identity_sha256'] = _i49_coast._fingerprint({key: value for key, value in proof.items() if key != 'identity_sha256'})
    prepared['identity_sha256'] = _i49_coast._hash({key: value for key, value in prepared.items() if key != 'identity_sha256'})
    forged['attachment']['recovery_sha256'] = proof['identity_sha256']
    return reseal(forged)

class SurfaceCoastDropTests(_i49_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.surface_domain import load_surface_domains as _i49_load_surface_domains
        if _i49_hashlib.sha256(SAVED_PREPARED.read_bytes()).hexdigest() != SAVED_PREPARED_SHA256:
            raise AssertionError('fixed saved prepared source file changed')
        cls.prepared = _i49_load_surface_domains(SAVED_PREPARED)
        cls.inputs = fixed_drop_inputs(cls.prepared)
        cls.result = _i49_coast.prepare_coast_drop(*cls.inputs)

    def test_actual_full_width_river_attachment_and_centerline(self):
        result = self.result
        bed = result['attachment']['river_bed_xyz_m']
        water = result['attachment']['river_water_xyz_m']
        _i49_np.testing.assert_allclose(bed[:, 1], [4.041177288138214, 3.626589853601033, 3.5, 3.661091270347399])
        _i49_np.testing.assert_allclose(water[:, 1], [4.275, 4.2375, 4.2, 4.2])
        _i49_np.testing.assert_allclose(bed[:, 0], [38.0, 39.0, 40.0, 41.0])
        _i49_np.testing.assert_array_equal(bed[:, 2], 70.0)
        centerline = result['arrays']['centerline_xyz_m']
        _i49_np.testing.assert_allclose(centerline[:, 0], 40.0)
        _i49_np.testing.assert_allclose(centerline[:, 1], _i49_np.linspace(4.2, 0.0, 21))
        _i49_np.testing.assert_allclose(centerline[:, 2], _i49_np.arange(70.0, 91.0))
        self.assertIs(result['natural_outlet_certified'], False)

    def test_actual_terminal_cut_q_not_sum_accumulated_nodes(self):
        self.assertAlmostEqual(self.result['attachment']['terminal_q_m3_s'], 0.200049)
        discharge = self.result['proof_support']['payload']['discharge_m3_s']
        self.assertGreater(float(discharge.sum()), 0.200049)

    def test_full_sea_attachment_positive_depth_and_source_identity(self):
        result = self.result
        _i49_np.testing.assert_allclose(result['attachment']['sea_bed_xyz_m'][:, 1], -0.5)
        _i49_np.testing.assert_allclose(result['attachment']['sea_water_xyz_m'][:, 1], 0.0)
        _i49_np.testing.assert_allclose(result['attachment']['sea_water_xyz_m'][:, 2], 90.0)
        self.assertEqual(result['inputs']['sea']['source_kind'], 'engineering_synthetic')
        self.assertEqual(result['inputs']['corridor']['surface_model'], _i49_coast.SOURCE_MODEL)

    def test_all_source_nodes_cells_and_triangles_covered(self):
        arrays = self.result['arrays']
        _i49_np.testing.assert_array_equal(arrays['corridor_support_cells'], _i49_np.arange(84))
        self.assertEqual(arrays['triangles'].shape, (120, 3))
        _i49_np.testing.assert_array_equal(arrays['corridor_source_triangles'], arrays['triangles'])
        self.assertEqual(len(_i49_np.unique(arrays['triangles'])), 84)
        for name, values in (('h0_m', arrays['h0_m']), ('h2_m', arrays['bed_xyz_m'][:, 1]), ('water_m', arrays['water_xyz_m'][:, 1])):
            source = self.result['inputs']['corridor'][name]
            _i49_np.testing.assert_allclose(source.ravel()[arrays['corridor_source_triangles']], values[arrays['triangles']])

    def test_cut_integral_matches_actual_source_triangle_affine(self):
        source = self.result['inputs']['corridor']
        cut = source['h0_m'] - source['h2_m']
        volume = 0.0
        for row in range(20):
            for column in range(3):
                volume += 0.5 * (cut[row, column] + cut[row, column + 1] + cut[row + 1, column]) / 3
                volume += 0.5 * (cut[row, column + 1] + cut[row + 1, column + 1] + cut[row + 1, column]) / 3
        self.assertAlmostEqual(self.result['ledger']['cut_volume_m3'], volume)
        self.assertAlmostEqual(float(self.result['ledger']['triangle_plan_area_m2'].sum()), 60.0)
        _i49_np.testing.assert_allclose(self.result['ledger']['cut_m'], cut.ravel())

    def test_unknown_protected_dry_invalid_interior_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for name, value in (('unknown_mask', True), ('protected_mask', True), ('wet_mask', False), ('valid_mask', False)):
            mask = getattr(corridor, name).copy()
            mask[10, 1] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i49_coast.prepare_coast_drop(attachment, _i49_replace(corridor, **{name: mask}), sea, stations, budget)

    def test_hidden_interior_ridge_and_negative_depth_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for height in (3.0, 20.0):
            bed = corridor.h2_m.copy()
            h0 = corridor.h0_m.copy()
            bed[10, 1] = height
            h0[10, 1] = max(height, h0[10, 1])
            with self.subTest(height=height), self.assertRaises(ValueError):
                _i49_coast.prepare_coast_drop(attachment, _i49_replace(corridor, h2_m=bed, h0_m=h0), sea, stations, budget)

    def test_no_skipping_station_or_cross_section_source_nodes(self):
        attachment, corridor, sea, stations, budget = self.inputs
        with self.assertRaisesRegex(ValueError, 'exact.*spacing'):
            _i49_coast.prepare_coast_drop(attachment, corridor, sea, stations[::2], budget)
        section = attachment.cross_section_xz_m[[0, 2, 3]]
        with self.assertRaisesRegex(ValueError, 'contiguous.*fine'):
            _i49_coast.prepare_coast_drop(_i49_replace(attachment, cross_section_xz_m=section, center_index=1), corridor, sea, stations, budget)

    def test_sea_unknown_protected_nonwet_nonocean_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for name, value in (('unknown_mask', True), ('protected_mask', True), ('wet_mask', False), ('ocean_mask', False)):
            mask = getattr(sea, name).copy()
            mask[0, 1] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i49_coast.prepare_coast_drop(attachment, corridor, _i49_replace(sea, **{name: mask}), stations, budget)

    def test_missing_sea_high_sea_and_datum_rejected(self):
        attachment, corridor, sea, stations, budget = self.inputs
        for bad_sea in (None, _i49_replace(sea, datum='other-datum'), _i49_replace(sea, sea_level_m=5.0, water_m=_i49_np.full_like(sea.water_m, 5.0))):
            with self.subTest(sea=bad_sea), self.assertRaises(ValueError):
                _i49_coast.prepare_coast_drop(attachment, corridor, bad_sea, stations, budget)

    def test_budget_depth_and_volume_original_caps(self):
        attachment, corridor, sea, stations, _ = self.inputs
        for budget in (_i49_coast.DropBudget(0.0, 100.0), _i49_coast.DropBudget(4.0, 0.0)):
            with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, 'budget exceeded'):
                _i49_coast.prepare_coast_drop(attachment, corridor, sea, stations, budget)

    def test_resources_preflight_rejection(self):
        for resources in (_i49_coast.DropResources(max_vertices=83), _i49_coast.DropResources(max_triangles=119), _i49_coast.DropResources(max_source_cells=90), _i49_coast.DropResources(max_work=1007), _i49_coast.DropResources(max_retained_bytes=1000)):
            with self.subTest(resources=resources), self.assertRaises(ValueError):
                _i49_coast.prepare_coast_drop(*self.inputs, resources=resources)

    def test_rehash_mesh_support_source_ledger_q_rejected(self):
        from terrain_pipeline.surface_identity import _plain as _i49__merged_coast__plain
        for name in ('bed_xyz_m', 'water_xyz_m', 'centerline_xyz_m', 'h0_m', 'corridor_weights', 'river_indices', 'corridor_source_triangles'):
            plain = _i49__merged_coast__plain(self.result)
            changed = plain['arrays'][name].copy()
            changed.flat[len(changed.ravel()) // 2] += 1
            plain['arrays'][name] = changed
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i49_coast.validate_coast_drop(reseal(plain))
        for mode in ('source', 'q', 'ledger'):
            plain = _i49__merged_coast__plain(self.result)
            if mode == 'source':
                source = plain['inputs']['corridor']
                array = source['h0_m'].copy()
                array[10, 1] += 1.0
                source['h0_m'] = array
                source['identity_sha256'] = _i49_coast.fingerprint({key: value for key, value in source.items() if key != 'identity_sha256'})
            elif mode == 'q':
                plain['attachment']['terminal_q_m3_s'] += 1.0
            else:
                plain['ledger']['cut_volume_m3'] += 1.0
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                _i49_coast.validate_coast_drop(reseal(plain))

    def test_default_load_query_no_mapping_sampling_or_generation(self):
        import terrain_pipeline.surface_domain as consumer
        import terrain_pipeline.surface_domain as recovery
        with _i49_tempfile.TemporaryDirectory() as directory:
            path = _i49_Path(directory) / 'coast.npz'
            _i49_coast.save_coast_drop(self.result, path)
            with _i49_ExitStack() as stack:
                for name in ('prepare_coast_drop', '_attachment', '_stencil', '_triangles', '_corridor_cells', '_source_triangles', '_proof_gate', 'validate_surface_domains', '_sample'):
                    stack.enter_context(_i49_patch.object(_i49_coast, name, side_effect=AssertionError('default load generated ' + name)))
                stack.enter_context(_i49_patch.object(consumer, '_fine_source', side_effect=AssertionError('resampled old source')))
                stack.enter_context(_i49_patch.object(consumer, '_proof_gate', side_effect=AssertionError('old proof regenerated')))
                stack.enter_context(_i49_patch.object(recovery, 'recover_surface_network', side_effect=AssertionError('recovered')))
                loaded = _i49_coast.load_coast_drop(path)
                queried = _i49_coast.query_coast_drop(loaded)
            self.assertEqual(loaded['identity_sha256'], self.result['identity_sha256'])
            _i49_np.testing.assert_array_equal(queried['arrays']['bed_xyz_m'], self.result['arrays']['bed_xyz_m'])

    def test_coherent_transverse_source_water_full_chain_rehash_rejected(self):
        from terrain_pipeline.surface_identity import _plain as _i49__merged_coast__plain
        forged = coherent_source_forgery(self.result, 'water')
        self.assertEqual(forged['identity_sha256'], _i49_coast.fingerprint({key: value for key, value in forged.items() if key != 'identity_sha256'}))
        self.assertAlmostEqual(forged['attachment']['river_water_xyz_m'][0, 1], 4.285)
        self.assertAlmostEqual(forged['attachment']['river_water_xyz_m'][2, 1], 4.2)
        proof = forged['inputs']['attachment']['prepared']['domains'][0]['recovery']
        self.assertEqual(proof['identity_sha256'], _i49_coast._fingerprint(_i49__merged_coast__plain({key: value for key, value in proof.items() if key != 'identity_sha256'})))
        with self.assertRaisesRegex(ValueError, 'wet water stage lacks original graph support'):
            _i49_coast.validate_coast_drop(forged)
        with _i49_tempfile.TemporaryDirectory() as directory:
            path = _i49_Path(directory) / 'coherent-forgery.npz'
            arrays = {}
            tree = _i49_coast._tree(forged, arrays)
            with _i49_zipfile.ZipFile(path, 'w', compression=_i49_zipfile.ZIP_STORED) as archive:
                archive.writestr('metadata.json', _i49_coast._json({'format': _i49_coast.SURFACE_COAST_DROP_VERSION + '-npy-v1', 'tree': tree}).encode('ascii'))
                for name, array in arrays.items():
                    stream = _i49_io.BytesIO()
                    _i49_np.lib.format.write_array(stream, array, version=(1, 0), allow_pickle=False)
                    archive.writestr(name, stream.getvalue())
            with _i49_ExitStack() as stack:
                for name in ('prepare_coast_drop', '_stencil', '_triangles', '_corridor_cells', '_proof_gate', 'validate_surface_domains'):
                    stack.enter_context(_i49_patch.object(_i49_coast, name, side_effect=AssertionError('generation forbidden')))
                with self.assertRaisesRegex(ValueError, 'wet water stage lacks original graph support'):
                    _i49_coast.load_coast_drop(path)

    def test_coherent_original_source_q_h0_grid_rehash_rejected(self):
        for mode in ('Q', 'H0', 'grid'):
            forged = coherent_source_forgery(self.result, mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'candidate original'):
                _i49_coast.validate_coast_drop(forged)

    def test_immutable_input_result_and_no_source_mutation(self):
        before = _i49_coast.fingerprint(self.inputs[0].prepared)
        _i49_coast.prepare_coast_drop(*self.inputs)
        self.assertEqual(_i49_coast.fingerprint(self.inputs[0].prepared), before)
        arrays = {}
        _i49_coast._tree(self.result, arrays)
        for array in arrays.values():
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_atomic_nooverwrite_and_failed_publication_cleanup(self):
        with _i49_tempfile.TemporaryDirectory() as directory:
            path = _i49_Path(directory) / 'coast.npz'
            _i49_coast.save_coast_drop(self.result, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                _i49_coast.save_coast_drop(self.result, path)
            self.assertEqual(path.read_bytes(), before)
            with _i49_patch.object(_i49_coast.os, 'link', side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):
                    _i49_coast.save_coast_drop(self.result, _i49_Path(directory) / 'failed.npz')
            self.assertEqual([path.name for path in _i49_Path(directory).iterdir()], ['coast.npz'])

    def test_archive_headers_unique_members_json_and_payload_caps(self):
        with _i49_tempfile.TemporaryDirectory() as directory:
            baseline = _i49_Path(directory) / 'base.npz'
            _i49_coast.save_coast_drop(self.result, baseline)
            with _i49_zipfile.ZipFile(baseline) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            first_array = next((name for name in members if name.endswith('.npy')))
            for mode in ('duplicate', 'json', 'header', 'trailing', 'truncated', 'extra'):
                path = _i49_Path(directory) / (mode + '.npz')
                payloads = dict(members)
                if mode == 'json':
                    payloads['metadata.json'] = payloads['metadata.json'][:-1] + b',"format":"duplicate"}'
                elif mode == 'header':
                    payloads[first_array] = b'\x93NUMPY\x01\x00' + 65535 .to_bytes(2, 'little')
                elif mode == 'trailing':
                    payloads[first_array] += b'extra'
                elif mode == 'truncated':
                    payloads[first_array] = payloads[first_array][:-1]
                elif mode == 'extra':
                    payloads['extra.npy'] = b'extra'
                with _i49_zipfile.ZipFile(path, 'w') as archive:
                    for name, payload in payloads.items():
                        archive.writestr(name, payload)
                    if mode == 'duplicate':
                        with _i49_warnings.catch_warnings():
                            _i49_warnings.simplefilter('ignore', UserWarning)
                            archive.writestr(first_array, members[first_array])
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    _i49_coast.load_coast_drop(path)

def domain(water=3.0, *, reverse=False, unknown=False, protected=False):
    nodes = [{'local_id': 0, 'x_m': 0.0, 'z_m': 0.0, 'h0_m': 10.0, 'unknown': unknown, 'protected': protected, 'water_surface_m': water}, {'local_id': 1, 'x_m': 1.0, 'z_m': 0.0, 'h0_m': 9.0, 'unknown': False, 'protected': False, 'water_surface_m': water}, {'local_id': 2, 'x_m': 1.0, 'z_m': 1.0, 'h0_m': 8.0, 'unknown': False, 'protected': False, 'water_surface_m': water}]
    edges = [{'local_id': 0, 'start': 0, 'end': 1, 'flux_m3_s': -0.25 if reverse else 0.25, 'boundary': True}, {'local_id': 1, 'start': 1, 'end': 2, 'flux_m3_s': 0.1 if reverse else -0.1, 'boundary': True}]
    return {'domain_id': 'B' if reverse else 'A', 'grid': {'origin_x_m': 0.0, 'origin_z_m': 0.0, 'spacing_x_m': 1.0, 'spacing_z_m': 1.0, 'lod': 0}, 'nodes': nodes, 'edges': edges}

class SurfaceCrossDomainTests(_i50_unittest.TestCase):

    def test_saved_domain_mosaic_fixture_is_adapted_readonly_without_edge_fabrication(self):
        from terrain_pipeline.surface_domain import adapt_saved_mosaics as _i50_adapt_saved_mosaics
        from terrain_pipeline.surface_domain import load_domain_mosaic
        path = _i50_Path(__file__).resolve().parents[1] / 'verification/surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz'
        if not path.exists():
            self.skipTest('saved domain mosaic fixture not available')
        mosaic = load_domain_mosaic(path)
        report = _i50_adapt_saved_mosaics([{'domain_id': 'saved-domain', 'mosaic': mosaic}])
        self.assertEqual(report['adapter']['prepare_called'], False)
        self.assertEqual(report['adapter']['routing_called'], False)
        self.assertFalse(report['flags']['edge_evidence_complete'])
        self.assertFalse(report['flags']['water_generated'])
        self.assertEqual(len(report['adapter']['diagnostics']), 2)

    def test_saved_fine_mosaic_fixture_is_adapted_without_water_reconstruction(self):
        from terrain_pipeline.surface_domain import adapt_saved_mosaics as _i50_adapt_saved_mosaics
        from terrain_pipeline.surface_domain import load_fine_mosaic
        path = _i50_Path(__file__).resolve().parents[1] / 'verification/surface-fine-mosaic/run-20260930T123659.258177Z/wet-cross-precision.npz'
        if not path.exists():
            self.skipTest('saved fine mosaic fixture not available')
        mosaic = load_fine_mosaic(path)
        report = _i50_adapt_saved_mosaics([{'domain_id': 'saved-fine', 'mosaic': mosaic}])
        self.assertEqual(report['adapter']['water_generation_called'], False)
        self.assertFalse(report['flags']['edge_evidence_complete'])
        self.assertFalse(report['water']['surface_available'])

    def test_stable_global_ids_shared_nodes_and_unique_edges(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i50_audit_cross_domain
        first = domain()
        second = domain(reverse=True)
        second['domain_id'] = 'B'
        for edge in second['edges']:
            edge['start'], edge['end'] = (edge['end'], edge['start'])
        report = _i50_audit_cross_domain([second, first])
        self.assertEqual(len(report['shared_boundary_node_ids']), 3)
        self.assertEqual(report['grid']['lods'], [0])
        self.assertEqual(report['ledger']['shared_edge_count'], 2)
        self.assertEqual(_i50_audit_cross_domain([first, second])['global_nodes'], report['global_nodes'])

    def test_shared_edge_is_counted_once_and_flux_cancels(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i50_audit_cross_domain
        first = domain()
        second = domain(reverse=True)
        second['domain_id'] = 'B'
        for edge in second['edges']:
            edge['start'], edge['end'] = (edge['end'], edge['start'])
        for edge in second['edges']:
            edge['boundary'] = False
        first['edges'][0]['boundary'] = False
        report = _i50_audit_cross_domain([first, second])
        self.assertEqual(report['ledger']['shared_edge_count'], 2)
        self.assertAlmostEqual(report['ledger']['internal_shared_flux_residual_m3_s'], 0.0)

    def test_spacing_misalignment_and_surface_mismatch_rejected(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i50_audit_cross_domain
        first, second = (domain(), domain(reverse=True))
        second['domain_id'] = 'B'
        second['nodes'][1]['water_surface_m'] = 4.0
        with self.assertRaisesRegex(ValueError, 'water surface'):
            _i50_audit_cross_domain([first, second])
        second['nodes'][1]['water_surface_m'] = 3.0
        second['nodes'][1]['x_m'] = 1.5
        with self.assertRaisesRegex(ValueError, 'grid'):
            _i50_audit_cross_domain([first, second])

    def test_unknown_protected_barrier_rejects_flux(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i50_audit_cross_domain
        first = domain(unknown=True)
        with self.assertRaisesRegex(ValueError, 'barrier'):
            _i50_audit_cross_domain([first])
        first = domain(protected=True)
        with self.assertRaisesRegex(ValueError, 'barrier'):
            _i50_audit_cross_domain([first])

    def test_edge_direction_and_partial_publication(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i50_audit_cross_domain
        from terrain_pipeline.surface_domain import save_cross_domain_report as _i50_save_cross_domain_report
        first, second = (domain(), domain(reverse=True))
        second['domain_id'] = 'B'
        for edge in second['edges']:
            edge['start'], edge['end'] = (edge['end'], edge['start'])
        second['edges'][0]['flux_m3_s'] = 0.25
        with self.assertRaisesRegex(ValueError, 'anti-symmetric'):
            _i50_audit_cross_domain([first, second])
        with _i50_tempfile.TemporaryDirectory() as directory:
            path = _i50_Path(directory) / 'report.json'
            with self.assertRaises(ValueError):
                _i50_save_cross_domain_report({'schema': 'bad'}, path)
            self.assertFalse(path.exists())
            report = _i50_audit_cross_domain([domain()])
            _i50_save_cross_domain_report(report, path)
            self.assertEqual(_i50_json.loads(path.read_text())['schema'], 'surface-cross-domain-v1')
            self.assertFalse(report['flags']['water_generated'])
            with self.assertRaises(FileExistsError):
                _i50_save_cross_domain_report(report, path)

    def test_coarse_edge_is_split_against_fine_domain(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i50_audit_cross_domain
        coarse = domain()
        coarse['domain_id'] = 'coarse'
        coarse['grid']['spacing_x_m'] = 2.0
        coarse['nodes'] = [{'local_id': 0, 'x_m': 0.0, 'z_m': 0.0, 'h0_m': 10.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}, {'local_id': 1, 'x_m': 2.0, 'z_m': 0.0, 'h0_m': 9.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}]
        coarse['edges'] = [{'local_id': 0, 'start': 0, 'end': 1, 'flux_m3_s': 1.0, 'boundary': False}]
        fine = {'domain_id': 'fine', 'grid': {'origin_x_m': 0.0, 'origin_z_m': 0.0, 'spacing_x_m': 1.0, 'spacing_z_m': 1.0, 'lod': 1}, 'nodes': [{'local_id': 0, 'x_m': 0.0, 'z_m': 0.0, 'h0_m': 10.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}, {'local_id': 1, 'x_m': 1.0, 'z_m': 0.0, 'h0_m': 9.5, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}, {'local_id': 2, 'x_m': 2.0, 'z_m': 0.0, 'h0_m': 9.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}], 'edges': [{'local_id': 0, 'start': 1, 'end': 0, 'flux_m3_s': -0.5, 'boundary': False}, {'local_id': 1, 'start': 2, 'end': 1, 'flux_m3_s': -0.5, 'boundary': False}]}
        report = _i50_audit_cross_domain([coarse, fine])
        self.assertEqual(report['ledger']['shared_edge_count'], 2)
        self.assertAlmostEqual(report['ledger']['internal_shared_flux_residual_m3_s'], 0.0)

def frozen_pins():
    base = ROOT / 'verification/td-basin-generation'
    hierarchy = {'path': str(base / 'A-20261001T184113155960Z/hierarchy.npz'), 'expected_sha256': '36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422', 'expected_identity': 'cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998'}
    storage = {'path': str(base / 'A-storage-v2-20261001T193000Z/ordinary.npz'), 'expected_sha256': '8ec55ed5cf750f93f821e97a0abf5fd74b2fe870f20ce1785a70f84097382dd2', 'expected_identity': '3c19fe7ab54b0373051fb25d59733130d3117a105b3d905a68f389687983a49b'}
    return (hierarchy, storage)

class TDPartitionTests(_i51_unittest.TestCase):

    def test_actual_frozen_flux_without_generation(self):
        from terrain_pipeline.surface_domain import audit_td_partition as _i51_audit_td_partition
        hierarchy, storage = frozen_pins()
        with _i51_patch('terrain_pipeline.basin_topology.build_basin_hierarchy', side_effect=AssertionError('generation')), _i51_patch('terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError('solve')):
            report = _i51_audit_td_partition(hierarchy, partition_column=128, storage_record=storage)
        self.assertEqual(report['ledger']['shared_edge_count'], 256)
        self.assertEqual(report['ledger']['internal_shared_flux_residual_m3_s'], 0)
        self.assertEqual(report['ledger']['unique_boundary_flux_m3_s'], 0)
        self.assertGreater(report['td_evidence']['forward_m3'] + report['td_evidence']['reverse_m3'], 0)
        self.assertGreater(report['td_evidence']['nonzero_one_direction_face_count'], 0)
        self.assertEqual(report['td_evidence']['elapsed_s'], 86400)
        self.assertTrue(report['flags']['partition_flux_evidence_complete'])
        self.assertFalse(report['flags']['edge_evidence_complete'])
        self.assertFalse(report['flags']['hydraulic_ready'])

    def test_hierarchy_only_is_diagnostic(self):
        from terrain_pipeline.surface_domain import audit_td_partition as _i51_audit_td_partition
        hierarchy, _ = frozen_pins()
        report = _i51_audit_td_partition(hierarchy, partition_column=128)
        self.assertFalse(report['flags']['partition_flux_evidence_complete'])
        self.assertIsNone(report['td_evidence']['forward_m3'])

    def test_bad_external_pin_no_publication(self):
        from terrain_pipeline.surface_domain import audit_td_partition as _i51_audit_td_partition
        from terrain_pipeline.surface_domain import save_cross_domain_report as _i51_save_cross_domain_report
        hierarchy, storage = frozen_pins()
        storage['expected_sha256'] = '0' * 64
        with _i51_tempfile.TemporaryDirectory() as temporary:
            output = _i51_Path(temporary) / 'report.json'
            with self.assertRaises(ValueError):
                report = _i51_audit_td_partition(hierarchy, partition_column=128, storage_record=storage)
                _i51_save_cross_domain_report(report, output)
            self.assertFalse(output.exists())

    def test_ids_survive_extra_domain(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i51_audit_cross_domain
        first = domain()
        before = _i51_audit_cross_domain([first])
        third = domain()
        third['domain_id'] = 'third'
        third['grid']['origin_x_m'] = -10.0
        for node in third['nodes']:
            node['x_m'] -= 10.0
        after = _i51_audit_cross_domain([third, first])
        ids = {(node['x_m'], node['z_m']): node['global_id'] for node in after['global_nodes']}
        self.assertTrue(all((ids[node['x_m'], node['z_m']] == node['global_id'] for node in before['global_nodes'])))

    def test_same_domain_duplicate_and_nonfinite_tolerance(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i51_audit_cross_domain
        first = domain()
        extra = _i51_copy.deepcopy(first['edges'][0])
        extra.update(local_id=99, flux_m3_s=-extra['flux_m3_s'])
        first['edges'].append(extra)
        with self.assertRaisesRegex(ValueError, 'one domain'):
            _i51_audit_cross_domain([first])
        for tolerance in (float('nan'), float('inf'), -1.0):
            with self.assertRaises(ValueError):
                _i51_audit_cross_domain([domain()], tolerance=tolerance)

    def test_normal_sign_is_independent_of_endpoint_order(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i51_audit_cross_domain
        first, second = (domain(), domain(reverse=True))
        report = _i51_audit_cross_domain([first, second])
        self.assertEqual(report['ledger']['shared_edge_count'], 2)
        self.assertFalse(report['flags']['edge_evidence_complete'])

    def test_nan_report_fails_before_directory_creation(self):
        from terrain_pipeline.surface_domain import audit_cross_domain as _i51_audit_cross_domain
        from terrain_pipeline.surface_domain import save_cross_domain_report as _i51_save_cross_domain_report
        report = _i51_audit_cross_domain([domain()])
        report['bad'] = float('nan')
        with _i51_tempfile.TemporaryDirectory() as temporary:
            output = _i51_Path(temporary) / 'absent/report.json'
            with self.assertRaises(ValueError):
                _i51_save_cross_domain_report(report, output)
            self.assertFalse(output.parent.exists())
EVIDENCE = ROOT / 'verification'
PATHS = {'dem': EVIDENCE / 'dem-domain/run-20260930T062026836139Z/dem-candidate.npz', 'domain': EVIDENCE / 'surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz', 'mosaic': EVIDENCE / 'surface-fine-mosaic/run-20260930T123659.258177Z/old-two-domain-gap.npz', 'drop': EVIDENCE / 'surface-coast-drop/run-20260930T125523.932019Z/actual-river-engineering-coast.npz', 'dynamic': EVIDENCE / 'surface-dynamic-prepare/run-20260930T130638.804119Z/saved-old-prepared-domain1.npz'}

class ReadinessTests(_i52_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.manifest = _i52_readiness.prepare_readiness(PATHS, dynamic_scope='lumped_storage_linear_conductance')

    def test_actual_bundles_are_diagnostic(self):
        diagnosis = self.manifest['diagnosis']
        self.assertFalse(diagnosis['ready'])
        self.assertEqual(diagnosis['facts']['dem_unknown_cells'], 33454)
        self.assertEqual(diagnosis['facts']['mosaic_missing_cells'], 600)
        self.assertIn('dynamic_partial_graph_not_full_mosaic', diagnosis['blockers'])
        self.assertTrue(diagnosis['facts']['dynamic_mosaic_artifact_different'])
        self.assertEqual(len(diagnosis['facts']['dynamic_embedded_proof_ids']), 1)
        self.assertNotIn('dynamic_and_mosaic_proof_graph_mismatch', diagnosis['blockers'])
        self.assertIn('coastline_and_natural_outlet_not_certified', diagnosis['blockers'])

    def test_identity_difference_alone_is_not_partial(self):
        proof = 'a' * 64
        products = {'mosaic': {'cell_owner': _i52_np.zeros((1, 1), dtype=int), 'source_identity': 'source', 'proofs': {proof: {}}, 'identity_sha256': 'b' * 64, 'status': 'prepared', 'full_domain_mosaic_prepared': True}, 'dynamic': {'binding': {'area_semantics': 'constant_area', 'source_proof_sha256': proof, 'source_mosaic': {'identity_sha256': 'c' * 64, 'proofs': {proof: {}}}}, 'full_dynamic_wave_prepared': False}}
        diagnosis = _i52_readiness._diagnose(products, 'lumped_storage_linear_conductance')
        self.assertTrue(diagnosis['facts']['dynamic_mosaic_artifact_different'])
        self.assertNotIn('dynamic_partial_graph_not_full_mosaic', diagnosis['blockers'])

    def test_saved_static_load_with_generation_disabled(self):
        with _i52_tempfile.TemporaryDirectory() as directory:
            path = _i52_Path(directory) / 'readiness.json'
            _i52_readiness.save_readiness(self.manifest, path)
            with _i52_patch.object(_i52_readiness, 'prepare_readiness', side_effect=AssertionError('generation called')), _i52_patch.object(_i52_dem_domain, 'prepare_dem_candidate', create=True, side_effect=AssertionError('DEM generation called')), _i52_patch.object(_i52_surface_domain_prepare, 'evaluate_surface_domains', side_effect=AssertionError('domain generation called')), _i52_patch.object(_i52_surface_fine_mosaic, 'prepare_fine_mosaic', side_effect=AssertionError('mosaic generation called')), _i52_patch.object(_i52_surface_coast_drop, 'prepare_coast_drop', side_effect=AssertionError('drop generation called')), _i52_patch.object(_i52_surface_dynamic_prepare, 'prepare_surface_dynamic', side_effect=AssertionError('dynamic advance called')):
                self.assertEqual(_i52_readiness.load_readiness(path), self.manifest)

    def test_save_failure_leaves_no_target_or_prefix(self):
        with _i52_tempfile.TemporaryDirectory() as directory:
            target = _i52_Path(directory) / 'readiness.json'
            with _i52_patch.object(_i52_readiness.os, 'link', side_effect=OSError('publish failed')):
                with self.assertRaises(OSError):
                    _i52_readiness.save_readiness(self.manifest, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(_i52_Path(directory).iterdir()), [])

    def test_rehashed_conclusion_and_identity_bypass_rejected(self):
        for change in (lambda value: value['diagnosis'].update(ready=True), lambda value: value['diagnosis'].update(blockers=[]), lambda value: value['bundles']['mosaic'].update(sha256='0' * 64), lambda value: value['bundles']['dem'].update(identity_sha256='0' * 64)):
            modified = _i52_copy.deepcopy(self.manifest)
            change(modified)
            with self.subTest(modified=modified['diagnosis']['ready']):
                with self.assertRaises(ValueError):
                    _i52_readiness.load_readiness_dict(modified)

    def test_bad_bundle_and_missing_input(self):
        with _i52_tempfile.TemporaryDirectory() as directory:
            invalid = _i52_Path(directory) / 'bad.npz'
            invalid.write_bytes(b'not a bundle')
            with self.assertRaises((ValueError, OSError)):
                _i52_readiness.prepare_readiness({'mosaic': invalid})
            diagnostic = _i52_readiness.prepare_readiness({'dem': PATHS['dem']})
            self.assertIn('mosaic_bundle_missing', diagnostic['diagnosis']['blockers'])

    def test_strict_json_types_rejected(self):
        changes = {'ready_integer': lambda value: value['diagnosis'].update(ready=0), 'unknown_float': lambda value: value['diagnosis']['facts'].update(dem_unknown_cells=33454.0), 'bytes_boolean': lambda value: value['bundles']['dem'].update(bytes=True), 'bytes_float': lambda value: value['bundles']['dem'].update(bytes=float(value['bundles']['dem']['bytes'])), 'artifact_integer': lambda value: value['diagnosis']['facts'].update(dynamic_mosaic_artifact_different=1)}
        with _i52_tempfile.TemporaryDirectory() as directory:
            path = _i52_Path(directory) / 'typed-forgery.json'
            for name, change in changes.items():
                modified = _i52_copy.deepcopy(self.manifest)
                change(modified)
                path.write_text(_i52_json.dumps(modified), encoding='utf-8')
                with self.subTest(change=name):
                    with self.assertRaises(ValueError):
                        _i52_readiness.load_readiness(path)

    def test_json_key_order_is_irrelevant(self):
        reordered = dict(reversed(list(self.manifest.items())))
        reordered['diagnosis'] = dict(reversed(list(reordered['diagnosis'].items())))
        self.assertEqual(_i52_readiness.load_readiness_dict(reordered), self.manifest)

    def test_ancestor_reparse_input_rejected(self):
        ancestor = PATHS['dem'].parent
        original_lstat = _i52_os.lstat

        def reparse_lstat(path, *args, **kwargs):
            actual = original_lstat(path, *args, **kwargs)
            if _i52_Path(path) == ancestor:
                fields = {name: getattr(actual, name) for name in dir(actual) if name.startswith('st_')}
                fields['st_file_attributes'] = getattr(actual, 'st_file_attributes', 0) | _i52_stat.FILE_ATTRIBUTE_REPARSE_POINT
                return _i52_SimpleNamespace(**fields)
            return actual
        with _i52_patch.object(_i52_readiness.os, 'lstat', side_effect=reparse_lstat):
            with self.assertRaisesRegex(ValueError, 'linked or reparse'):
                _i52_readiness.prepare_readiness({'dem': PATHS['dem']})

    def test_linked_input_rejected(self):
        with _i52_tempfile.TemporaryDirectory() as directory:
            linked = _i52_Path(directory) / 'linked.npz'
            try:
                linked.symlink_to(PATHS['dem'])
            except OSError as error:
                self.skipTest('Windows symlink privilege unavailable: ' + str(error))
            with self.assertRaisesRegex(ValueError, 'linked or reparse'):
                _i52_readiness.prepare_readiness({'dem': linked})

    def test_json_forgery_and_scope(self):
        with _i52_tempfile.TemporaryDirectory() as directory:
            path = _i52_Path(directory) / 'forged.json'
            path.write_text('{"format":1,"format":2}', encoding='utf-8')
            with self.assertRaises(ValueError):
                _i52_readiness.load_readiness(path)
        with self.assertRaises(ValueError):
            _i52_readiness.prepare_readiness(PATHS, dynamic_scope='anything')
SOURCE = _i53_Path(__file__).resolve().parents[1] / 'verification/surface-domain-prepare' / 'run-20260930T103111870204Z/two-domain-prepared.npz'

def mutable(value):
    from terrain_pipeline.surface_identity import _plain as _i53__merged_fine__plain
    return _i53_deepcopy(_i53__merged_fine__plain(value))

def rehash(value):
    value.pop('identity_sha256', None)
    value['identity_sha256'] = _i53_fine._identity(value)
    return value

class SurfaceDomainMosaicTests(_i53_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.surface_domain import load_surface_domains as _i53_load_surface_domains
        cls.evaluation = _i53_load_surface_domains(SOURCE)
        cls.result = _i53_mosaic.prepare_domain_mosaic(cls.evaluation)

    def test_fixed_coverage_seam_and_q(self):
        result = self.result
        self.assertEqual(result['extension_cell_count'], 600)
        self.assertEqual(result['cells'].shape, (7800, 4))
        self.assertEqual(result['triangles'].shape, (15600, 3))
        self.assertEqual(len(result['nodes']['x_m']), 7991)
        self.assertEqual([int(_i53_np.sum(result['hydrologic_domain_owner'] == domain)) for domain in (1, 2)], [3900, 3900])
        self.assertEqual([int(_i53_np.sum((result['cell_owner'] == 2) & (result['hydrologic_domain_owner'] == domain))) for domain in (1, 2)], [300, 300])
        self.assertTrue(_i53_np.all(result['nodes']['h0_m'][result['nodes']['x_m'] == 75] == 10.0))
        self.assertAlmostEqual(result['summary']['q_outgoing_m3_s'], 0.400098)
        self.assertAlmostEqual(result['summary']['unique_cut_volume_m3'], 576.8710544290026)
        self.assertAlmostEqual(result['summary']['actual_wet_water_volume_m3'], 236.01507098278893)
        self.assertTrue(_i53_mosaic.validate_domain_mosaic(result))

    def test_static_reload_readonly_and_no_generation(self):
        with _i53_tempfile.TemporaryDirectory() as directory:
            path = _i53_Path(directory) / 'mosaic.npz'
            _i53_mosaic.save_domain_mosaic(self.result, path)
            with _i53_patch.object(_i53_mosaic, 'prepare_domain_mosaic', side_effect=AssertionError('prepared')), _i53_patch.object(_i53_mosaic, '_assemble', side_effect=AssertionError('assembled')), _i53_patch.object(_i53_fine, '_mesh', side_effect=AssertionError('mesh generated')), _i53_patch.object(_i53_fine, '_h0_support', side_effect=AssertionError('support generated')):
                loaded = _i53_mosaic.load_domain_mosaic(path)
            self.assertEqual(loaded['identity_sha256'], self.result['identity_sha256'])
            with self.assertRaises(ValueError):
                loaded['nodes']['h0_m'][0] = 1.0
            with self.assertRaises(FileExistsError):
                _i53_mosaic.save_domain_mosaic(self.result, path)

    def test_saved_mosaic_full_static_guard_and_coherent_proof_rejection(self):
        static_disabled = static_disabled
        frozen = SOURCE.parents[2] / 'surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz'
        with _i53_ExitStack() as stack:
            static_disabled(stack)
            stack.enter_context(_i53_patch.object(_i53_mosaic, '_assemble', side_effect=AssertionError('assembly')))
            loaded = _i53_mosaic.load_domain_mosaic(frozen)
            self.assertTrue(_i53_mosaic.validate_domain_mosaic(loaded))
            changed = mutable(loaded)
            domain_mesh = changed['domain_meshes'][0]
            proof_id = next(iter(domain_mesh['proofs']))
            domain_mesh['proof_h0_support'][proof_id]['weights'][0, 0] += 0.2
            rehash(domain_mesh)
            with self.assertRaises(ValueError):
                _i53_mosaic.validate_domain_mosaic(rehash(changed))

    def test_coherent_rehash_attacks(self):
        for change in (lambda value: value['nodes']['h2_m'].__setitem__(75, 9.0), lambda value: value['contributors']['weights'].__setitem__((3600, 0, 0), 0.5), lambda value: value['cell_owner'].__setitem__((0, 0), 2), lambda value: value['hydrologic_domain_owner'].__setitem__((0, 0), 2), lambda value: value['grid']['bbox_xz_m'].__setitem__(1, 130.0), lambda value: value['domain_meshes'][0]['sources'][0]['window_zx'].__setitem__(3, 60)):
            with self.subTest(change=change):
                value = mutable(self.result)
                change(value)
                with self.assertRaises(ValueError):
                    _i53_mosaic.validate_domain_mosaic(rehash(value))
        value = mutable(self.result)
        value['domain_meshes'][0]['sources'][0]['window_zx'][3] = 60
        rehash(value['domain_meshes'][0])
        with self.assertRaises(ValueError):
            _i53_mosaic.validate_domain_mosaic(rehash(value))
        value = mutable(self.result)
        extension_cell = int(_i53_np.flatnonzero(value['cell_owner'].ravel() == 2)[0])
        value['contributors']['weights'][extension_cell, 1, 0] += 0.1
        value['contributors']['weights'][extension_cell, 1, 1] -= 0.1
        with self.assertRaises(ValueError):
            _i53_mosaic.validate_domain_mosaic(rehash(value))
        value = mutable(self.result)
        extension_node = int(value['cells'][extension_cell, 1])
        value['nodes']['h0_m'][extension_node] += 1.0
        value['nodes']['h2_m'][extension_node] += 1.0
        with self.assertRaises(ValueError):
            _i53_mosaic.validate_domain_mosaic(rehash(value))

    def test_resource_cancel_and_original_support(self):
        with self.assertRaises(ValueError):
            _i53_mosaic.prepare_domain_mosaic(self.evaluation, resources=_i53_fine.MosaicResources(max_cells=7799))
        with self.assertRaises(InterruptedError):
            _i53_mosaic.prepare_domain_mosaic(self.evaluation, cancel=lambda: True)
        value = mutable(self.result)
        candidate = value['evaluation']['candidate']
        candidate['inputs']['land_mask'][1, 7] = False
        column = 60
        row = 0
        cell_id = row * 130 + column
        with self.assertRaises(ValueError):
            _i53_mosaic._extension_value(candidate, 71.0, 10.0, value['contributors']['indices'][cell_id, 1], value['contributors']['weights'][cell_id, 1])
        for mask in ('valid_mask', 'land_mask'):
            candidate = mutable(self.evaluation['candidate'])
            candidate['inputs'][mask][1, 7] = False
            with self.assertRaises(ValueError):
                _i53_mosaic._extension_value(candidate, 71.0, 10.0, value['contributors']['indices'][cell_id, 1], value['contributors']['weights'][cell_id, 1])

    def test_protection_and_wet_seam_rejection(self):
        value = mutable(self.result)
        extension_cell = int(_i53_np.flatnonzero(value['cell_owner'].ravel() == 2)[0])
        indices = value['contributors']['indices'][extension_cell, 1]
        weights = value['contributors']['weights'][extension_cell, 1]
        candidate = value['evaluation']['candidate']
        candidate['inputs']['protected_mask'][1, 7] = True
        height, protected = _i53_mosaic._extension_value(candidate, 71.0, 10.0, indices, weights)
        self.assertEqual(height, 10.0)
        self.assertTrue(protected)
        with self.assertRaises(ValueError):
            _i53_mosaic.validate_domain_mosaic(rehash(value))
        value = mutable(self.result)
        shared = int(_i53_np.flatnonzero((value['nodes']['x_m'] == 70.0) & (value['nodes']['z_m'] == 10.0))[0])
        value['domain_meshes'][0]['nodes']['wet_mask'][-1] = True
        value['domain_meshes'][0]['nodes']['water_surface_m'][-1] = 11.0
        rehash(value['domain_meshes'][0])
        with self.assertRaises(ValueError):
            _i53_mosaic.validate_domain_mosaic(rehash(value))

    def test_archive_gate_and_atomic_failure(self):
        with _i53_tempfile.TemporaryDirectory() as directory:
            path = _i53_Path(directory) / 'valid.npz'
            _i53_mosaic.save_domain_mosaic(self.result, path)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                _i53_mosaic.save_domain_mosaic(self.result, path)
            self.assertEqual(path.read_bytes(), original)
            for name, payload in (('extra.npy', b'not an NPY'), ('array_object.npy', self._object_npy())):
                attack = _i53_Path(directory) / name.replace('.npy', '.npz')
                with _i53_zipfile.ZipFile(path) as source, _i53_zipfile.ZipFile(attack, 'w') as output:
                    for member in source.namelist():
                        output.writestr(member, source.read(member))
                    output.writestr(name, payload)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    _i53_mosaic.load_domain_mosaic(attack)

    @staticmethod
    def _object_npy():
        stream = _i53_io.BytesIO()
        _i53_np.save(stream, _i53_np.array(['bad'], dtype=object), allow_pickle=True)
        return stream.getvalue()

def complete_two_domain_inputs():
    from terrain_pipeline.surface_domain import SurfaceDomainResources as _i54_SurfaceDomainResources
    shape = (9, 16)
    height = _i54_np.zeros(shape)
    labels = _i54_np.zeros(shape, _i54_np.int64)
    external = _i54_np.zeros(shape)
    for domain_id, first_column in ((1, 1), (2, 8)):
        labels[1:8, first_column:first_column + 7] = domain_id
        local = _i54_np.full((7, 7), 10.0)
        for row in range(1, 7):
            local[row, 2:5] = 5.0 - row * 0.01
        local[6, :] = 10.0
        local[6, 3] = 4.0
        height[1:8, first_column:first_column + 7] = local
        external[2, first_column + 2] = 0.1
        external[2, first_column + 4] = 0.1
    land = labels > 0
    return dict(height_m=height, valid_mask=_i54_np.ones(shape, bool), domain_labels=labels, land_mask=land, ocean_mask=~land, protected_mask=_i54_np.zeros(shape, bool), coastal_outlets=[(1, 7 * 16 + 4, 8 * 16 + 4), (2, 7 * 16 + 11, 8 * 16 + 11)], runoff_m_s=_i54_np.where(land, 1e-08, 0.0), external_q_m3_s=external, spacing_x_m=10.0, spacing_z_m=10.0, origin_x_m=0.0, origin_z_m=0.0, sea_level_elevation_m=0.0, vertical_datum='engineering-metres-relative-sea-zero', source_identity='engineered-complete-two-domain-grid', source_kind='engineering_synthetic', boundary_complete=True, scope='complete_grid', outlet_evidence='engineering_declared', resources=_i54_SurfaceDomainResources())

def fine_configurations(candidate):
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _i54_InundationRecipe
    from terrain_pipeline.surface_hydraulics import RerouteRecipe as _i54_RerouteRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _i54_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _i54_SectionRecipe
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i54_ChannelRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i54_NetworkValleyRecipe
    from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i54_SurfaceNetworkBudget
    from terrain_pipeline.surface_domain import RecoveryRecipe as _i54_RecoveryRecipe
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i54_ValleyGeometryRecipe
    from terrain_pipeline.surface_domain import DomainFineConfiguration as _i54_DomainFineConfiguration
    from terrain_pipeline.surface_domain import bind_surface_domain_fine as _i54_bind_surface_domain_fine
    channel = _i54_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=8.0, min_width_m=8.0, max_width_m=8.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, max_cut_m=4.0, min_bed_slope_m_per_m=1e-05)
    return {domain_id: _i54_DomainFineConfiguration(_i54_bind_surface_domain_fine(candidate, domain_id, 1.0, 1.0), _i54_np.array([4.2]), channel, _i54_SectionRecipe(), _i54_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i54_InundationRecipe(max_lateral_reach_m=15.0), _i54_SurfaceNetworkBudget(4.0, 5000.0, 5000.0), _i54_NetworkValleyRecipe(3.75, 30.0, 30.0, 1e-05), _i54_ValleyGeometryRecipe(4.0, 10000.0, 100000.0, 100000.0), _i54_RerouteRecipe(), _i54_RecoveryRecipe(max_attempts=4)) for domain_id in (1, 2)}

def _test_surface_domain_prepare_rehash(result):
    from terrain_pipeline.surface_domain import _hash as _i54__hash
    result.pop('identity_sha256', None)
    result['identity_sha256'] = _i54__hash(result)
    return result

def write_rehashed_bundle(result, path):
    from terrain_pipeline.surface_domain import _encode as _i54__encode
    from terrain_pipeline.artifacts.contracts import digest as _i54_digest
    arrays = {}
    tree = _i54__encode(result, arrays)
    with _i54_Path(path).open('wb') as stream:
        _i54_np.savez_compressed(stream, manifest=_i54_json.dumps({'format_version': 1, 'tree': tree, 'tree_sha256': _i54_digest(tree)}), **arrays)

class SurfaceDomainPrepareTests(_i54_unittest.TestCase):

    def test_archived_domain_identity_is_readonly_and_cannot_generate(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import load_surface_domains as _i54_load_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        from terrain_pipeline.surface_domain import _hash as _i54__hash
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        import hashlib
        SOURCE = SOURCE
        before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        saved = _i54_load_surface_domains(SOURCE)
        self.assertEqual(saved['algorithm_version'], 'surface-domain-prepare-v1')
        self.assertEqual(saved['status'], 'prepared')
        self.assertEqual(saved['identity_sha256'], _i54__hash({key: value for key, value in saved.items() if key != 'identity_sha256'}))
        with self.assertRaisesRegex(ValueError, 'read-only'):
            _i54_evaluate_surface_domains(saved['candidate'], {})
        changed = _i54_deepcopy(_i54__plain(saved))
        changed['candidate']['arrays']['discharge_m3_s'].flat[0] += 1.0
        with self.assertRaises(ValueError):
            _i54_validate_surface_domains(changed)
        candidate = _i54_deepcopy(_i54__plain(saved['candidate']))
        routed = _i54_np.flatnonzero(candidate['arrays']['receiver'] >= 0)
        node = int(routed[0])
        candidate['arrays']['receiver'][node] = node
        _test_surface_domain_prepare_rehash(candidate)
        with self.assertRaisesRegex(ValueError, 'cyclic route'):
            _i54_validate_surface_domains(candidate, allow_unprepared=True)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), before)

    def test_saved_support_preserves_evaluation_constraints_without_sampling(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        from terrain_pipeline.surface_domain import _hash as _i54__hash
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        import hashlib
        from terrain_pipeline.surface_domain import _h0_support
        static_disabled = static_disabled
        root = _i54_Path(__file__).resolve().parents[1]
        archive = root / 'verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz'
        before = hashlib.sha256(archive.read_bytes()).hexdigest()
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        evaluation = _i54_evaluate_surface_domains(candidate, fine_configurations(candidate))
        support = {entry['recovery']['identity_sha256']: _h0_support(entry['recovery']) for entry in evaluation['domains']}
        with _i54_ExitStack() as stack:
            static_disabled(stack)
            self.assertIs(_i54_validate_surface_domains(evaluation, saved_support=support), evaluation)
            with self.assertRaises(ValueError):
                _i54_validate_surface_domains(evaluation['candidate'], allow_unprepared=True, saved_support=support)
            for mode in ('missing', 'support', 'swapped', 'charged', 'usage', 'config'):
                changed = _i54_deepcopy(_i54__plain(evaluation))
                saved = _i54_deepcopy(_i54__plain(support))
                if mode == 'missing':
                    saved.pop(next(iter(saved)))
                elif mode == 'support':
                    saved[next(iter(saved))]['weights'][0, 0] += 0.2
                elif mode == 'swapped':
                    first, second = list(saved)
                    saved[first], saved[second] = (saved[second], saved[first])
                    saved[first]['indices'][0, 0] += 1
                elif mode == 'charged':
                    changed['domains'][0]['charged_fine_cells'] += 1
                elif mode == 'usage':
                    changed['usage']['fine_work_cells'] += 1
                else:
                    changed['configurations']['1']['outlet_stage_m'] += 1.0
                changed['identity_sha256'] = _i54__hash({key: value for key, value in changed.items() if key != 'identity_sha256'})
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    _i54_validate_surface_domains(changed, saved_support=saved)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before)

    def test_complete_two_domains_prepare_reload_readonly(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import load_surface_domains as _i54_load_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import query_surface_domain as _i54_query_surface_domain
        from terrain_pipeline.surface_domain import save_surface_domains as _i54_save_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        inputs = complete_two_domain_inputs()
        candidate = _i54_plan_surface_domains(**inputs)
        self.assertEqual(candidate['status'], 'candidate')
        _i54_validate_surface_domains(candidate, allow_unprepared=True)
        result = _i54_evaluate_surface_domains(candidate, fine_configurations(candidate))
        self.assertEqual(result['status'], 'prepared', [(item['domain_id'], item['reason']) for item in result['domains']])
        _i54_validate_surface_domains(result)
        with _i54_tempfile.TemporaryDirectory() as directory:
            path = _i54_Path(directory) / 'complete.npz'
            _i54_save_surface_domains(result, path)
            with _i54_patch('terrain_pipeline.channel_geometry.plan_channel', side_effect=AssertionError('load planned')), _i54_patch('terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError('load recovered')), _i54_patch('terrain_pipeline.surface_domain._flood', side_effect=AssertionError('load routed')):
                loaded = _i54_load_surface_domains(path)
                window = _i54_query_surface_domain(loaded, 1, slice(None), slice(None))
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])
            self.assertGreater(int(window['wet_mask'].sum()), 0)
            self.assertGreater(float(window['total_cut_m'].sum()), 0.0)
            with self.assertRaises(ValueError):
                window['final_surface_m'].flags.writeable = True
            with self.assertRaises(TypeError):
                loaded['usage']['attempts'] = 0

    def test_complete_land_q_and_coastal_transfer_two_tributaries(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        result = _i54_plan_surface_domains(**inputs)
        receiver = result['arrays']['receiver']
        labels = inputs['domain_labels'].ravel()
        donors = _i54_np.flatnonzero(receiver >= 0)
        _i54_np.testing.assert_array_equal(labels[donors], labels[receiver[donors]])
        self.assertEqual(int(_i54_np.count_nonzero(receiver >= -1)), int(inputs['land_mask'].sum()))
        self.assertEqual(int(_i54_np.count_nonzero(receiver == -1)), 2)
        local = result['arrays']['local_discharge_m3_s']
        self.assertAlmostEqual(sum((item['discharge_m3_s'] for item in result['coastal_transfers'])), float(local.sum()))
        self.assertEqual(result['unrouted_local_discharge_m3_s'], 0.0)
        for transfer in result['coastal_transfers']:
            self.assertEqual(labels[transfer['ocean_cell']], 0)
            self.assertGreater(transfer['discharge_m3_s'], 0.2)
        paths = []
        for source in (2 * 16 + 3, 2 * 16 + 5):
            path_cells = []
            while source >= 0:
                path_cells.append(source)
                source = int(receiver[source])
            paths.append(path_cells)
        self.assertNotEqual(paths[0][0], paths[1][0])
        self.assertTrue(set(paths[0][1:]) & set(paths[1][1:]))

    def test_deterministic_and_original_height_unchanged(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.artifacts.contracts import array_hash as _i54_array_hash
        inputs = complete_two_domain_inputs()
        before = _i54_array_hash(inputs['height_m'])
        first = _i54_plan_surface_domains(**inputs)
        second = _i54_plan_surface_domains(**inputs)
        self.assertEqual(first['identity_sha256'], second['identity_sha256'])
        self.assertEqual(_i54_array_hash(inputs['height_m']), before)
        self.assertFalse(_i54_np.shares_memory(inputs['height_m'], first['arrays']['working_fill_m']))

    def test_unknown_unassigned_preserves_nonzero_local_water(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['domain_labels'][1, 1] = -1
        result = _i54_plan_surface_domains(**inputs)
        self.assertEqual(result['status'], 'diagnostic')
        self.assertIn('unknown_or_unassigned_cells', result['failures'])
        self.assertGreater(result['unrouted_local_discharge_m3_s'], 0.4)
        _i54_validate_surface_domains(result, allow_unprepared=True)

    def test_label_contract_invalid(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['domain_labels'][0, 0] = 1
        with self.assertRaises(ValueError):
            _i54_plan_surface_domains(**inputs)

    def test_false_ocean_above_sea(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['height_m'][8, 4] = 100.0
        with self.assertRaisesRegex(ValueError, 'sea level'):
            _i54_plan_surface_domains(**inputs)

    def test_false_coast_interior_ocean_not_boundary_connected(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['domain_labels'][4, 4] = 0
        inputs['land_mask'][4, 4] = False
        inputs['ocean_mask'][4, 4] = True
        inputs['height_m'][4, 4] = 0.0
        inputs['runoff_m_s'][4, 4] = 0.0
        inputs['coastal_outlets'][0] = (1, 4 * 16 + 3, 4 * 16 + 4)
        with self.assertRaisesRegex(ValueError, 'false coast'):
            _i54_plan_surface_domains(**inputs)

    def test_domain_without_outlet_is_diagnostic(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['coastal_outlets'] = inputs['coastal_outlets'][:1]
        result = _i54_plan_surface_domains(**inputs)
        self.assertEqual(result['status'], 'diagnostic')
        self.assertEqual(result['domains'][0]['status'], 'routed')
        self.assertEqual(result['domains'][1]['status'], 'diagnostic')
        self.assertGreater(result['unrouted_local_discharge_m3_s'], 0.2)
        _i54_validate_surface_domains(result, allow_unprepared=True)

    def test_protected_land_nonzero_and_zero_are_explicit_failures(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        for zero in (False, True):
            inputs = complete_two_domain_inputs()
            inputs['protected_mask'][1, 1] = True
            if zero:
                inputs['runoff_m_s'][1, 1] = 0.0
            result = _i54_plan_surface_domains(**inputs)
            self.assertEqual(result['status'], 'diagnostic')
            self.assertTrue(any(('protected_land' in reason for reason in result['failures'])))
            self.assertGreater(result['unrouted_local_discharge_m3_s'], 0.4)

    def test_graph_diagonal_requires_both_orthogonal_supports(self):
        from terrain_pipeline.surface_domain import _edge_ok as _i54__edge_ok
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        allowed = _i54_np.ones((3, 3), bool)
        mesh = grid_mesh(allowed.shape)
        self.assertTrue(_i54__edge_ok(0, 4, allowed.shape, allowed, mesh))
        allowed[0, 1] = False
        self.assertFalse(_i54__edge_ok(0, 4, allowed.shape, allowed, mesh))
        allowed[0, 1] = True
        allowed[1, 0] = False
        self.assertFalse(_i54__edge_ok(0, 4, allowed.shape, allowed, mesh))

    def test_corner_only_land_component_cannot_drain(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        for cell in ((1, 1), (1, 2), (2, 1)):
            inputs['domain_labels'][cell] = 0
            inputs['land_mask'][cell] = False
            inputs['ocean_mask'][cell] = True
            inputs['height_m'][cell] = 0.0
            inputs['runoff_m_s'][cell] = 0.0
        inputs['domain_labels'][1, 1] = 1
        inputs['land_mask'][1, 1] = True
        inputs['ocean_mask'][1, 1] = False
        inputs['height_m'][1, 1] = 10.0
        result = _i54_plan_surface_domains(**inputs)
        self.assertEqual(result['status'], 'diagnostic')
        self.assertIn('supported route', result['domains'][0]['reason'])

    def test_coarse_resource_rejected_before_flood(self):
        from terrain_pipeline.surface_domain import SurfaceDomainResources as _i54_SurfaceDomainResources
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['resources'] = _i54_SurfaceDomainResources(max_coarse_cells=10)
        with _i54_patch('terrain_pipeline.surface_domain._flood', side_effect=AssertionError('routed')):
            result = _i54_plan_surface_domains(**inputs)
        self.assertIn('coarse_resource_limit', result['failures'])

    def test_retained_resource_preflight_before_normalization(self):
        from terrain_pipeline.surface_domain import SurfaceDomainResources as _i54_SurfaceDomainResources
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['resources'] = _i54_SurfaceDomainResources(max_retained_bytes=100)
        with _i54_patch('terrain_pipeline.surface_domain._normalize_inputs', side_effect=AssertionError('copied')):
            with self.assertRaisesRegex(ValueError, 'resource preflight'):
                _i54_plan_surface_domains(**inputs)

    def test_joint_fine_preflight_no_partial_recovery(self):
        from terrain_pipeline.surface_domain import SurfaceDomainResources as _i54_SurfaceDomainResources
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['resources'] = _i54_SurfaceDomainResources(max_fine_cells=5000)
        candidate = _i54_plan_surface_domains(**inputs)
        with _i54_patch('terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError('recovered')):
            result = _i54_evaluate_surface_domains(candidate, fine_configurations(candidate))
        self.assertEqual(result['status'], 'diagnostic')
        self.assertEqual(result['usage']['fine_cells'], 0)
        _i54_validate_surface_domains(result, allow_unprepared=True)

    def test_joint_attempt_finework_bytes_preflight(self):
        from terrain_pipeline.surface_domain import SurfaceDomainResources as _i54_SurfaceDomainResources
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        for limits in ({'max_attempts': 1}, {'max_fine_work_cells': 5000}, {'max_retained_bytes': 1000000}):
            inputs = complete_two_domain_inputs()
            inputs['resources'] = _i54_SurfaceDomainResources(**limits)
            candidate = _i54_plan_surface_domains(**inputs)
            with _i54_patch('terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError('recovered')):
                result = _i54_evaluate_surface_domains(candidate, fine_configurations(candidate))
            self.assertEqual(result['status'], 'diagnostic')
            self.assertEqual(result['usage']['attempts'], 0)

    def test_missing_fine_domain_cannot_be_ignored(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        configs = fine_configurations(candidate)
        configs.pop(2)
        with self.assertRaisesRegex(ValueError, 'every land domain'):
            _i54_evaluate_surface_domains(candidate, configs)

    def test_fine_mask_domain_coast_protection_binding(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'):
            configs = fine_configurations(candidate)
            fine = configs[1].fine
            mask = getattr(fine, name).copy()
            mask[20, 20] = not mask[20, 20]
            configs[1] = _i54_replace(configs[1], fine=_i54_replace(fine, **{name: mask}))
            with _i54_patch('terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError('recovered')):
                result = _i54_evaluate_surface_domains(candidate, configs)
            self.assertEqual(result['status'], 'diagnostic')
            self.assertTrue(any(('masks disagree' in reason for reason in result['failures'])))

    def test_actual_fine_budget_failure_preserved(self):
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i54_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import RecoveryRecipe as _i54_RecoveryRecipe
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import load_surface_domains as _i54_load_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import save_surface_domains as _i54_save_surface_domains
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        configs = fine_configurations(candidate)
        configs = {key: _i54_replace(value, budget=_i54_SurfaceNetworkBudget(4.0, 0.0, 0.0), recovery_recipe=_i54_RecoveryRecipe(max_attempts=1)) for key, value in configs.items()}
        result = _i54_evaluate_surface_domains(candidate, configs)
        self.assertEqual(result['status'], 'diagnostic')
        self.assertTrue(result['domains'][0]['recovery']['attempts'][0]['failures']['area'])
        with _i54_tempfile.TemporaryDirectory() as directory:
            path = _i54_Path(directory) / 'budget.npz'
            _i54_save_surface_domains(result, path)
            with self.assertRaises(ValueError):
                _i54_load_surface_domains(path)
            _i54_load_surface_domains(path, allow_unprepared=True)

    def test_cancel_flood_retains_completed_domain_prefix(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains

        def cancel():
            cancel.calls += 1
            return cancel.calls > 50
        cancel.calls = 0
        result = _i54_plan_surface_domains(**complete_two_domain_inputs(), cancel=cancel)
        self.assertEqual(result['status'], 'diagnostic')
        self.assertEqual(result['domains'][0]['status'], 'routed')
        self.assertEqual(result['domains'][1]['status'], 'pending')
        _i54_validate_surface_domains(result, allow_unprepared=True)

    def test_cancel_prepare_retains_actual_fine_prefix_never_publish(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import query_surface_domain as _i54_query_surface_domain
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())

        def cancel():
            cancel.calls += 1
            return cancel.calls > 1
        cancel.calls = 0
        result = _i54_evaluate_surface_domains(candidate, fine_configurations(candidate), cancel=cancel)
        self.assertEqual(result['status'], 'diagnostic')
        self.assertEqual(result['domains'][0]['status'], 'prepared')
        self.assertEqual(result['domains'][1]['status'], 'pending')
        _i54_validate_surface_domains(result, allow_unprepared=True)
        with self.assertRaises(ValueError):
            _i54_query_surface_domain(result, 1, slice(None), slice(None))

    def test_subdomain_or_unverified_boundary_never_system_prepared(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        for change in ({'scope': 'subdomain'}, {'boundary_complete': False}):
            inputs = complete_two_domain_inputs()
            inputs.update(change)
            candidate = _i54_plan_surface_domains(**inputs)
            result = _i54_evaluate_surface_domains(candidate, fine_configurations(candidate))
            self.assertEqual(result['status'], 'candidate')
            self.assertTrue(all((item['status'] == 'prepared' for item in result['domains'])))
            with self.assertRaises(ValueError):
                _i54_validate_surface_domains(result)

    def test_rehashed_cross_domain_route_rejected(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        result = _i54__plain(_i54_plan_surface_domains(**complete_two_domain_inputs()))
        result['arrays']['receiver'] = result['arrays']['receiver'].copy()
        result['arrays']['receiver'][3 * 16 + 7] = 3 * 16 + 8
        with self.assertRaises(ValueError):
            _i54_validate_surface_domains(_test_surface_domain_prepare_rehash(result), allow_unprepared=True)

    def test_rehashed_nonconservative_q_transfer_fill_rejected(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        for field in ('discharge_m3_s', 'working_fill_m', 'coastal_transfers'):
            result = _i54__plain(_i54_plan_surface_domains(**complete_two_domain_inputs()))
            if field == 'coastal_transfers':
                result[field][0]['discharge_m3_s'] = 0.0
            else:
                result['arrays'][field] = result['arrays'][field].copy()
                result['arrays'][field][3, 4] += 1.0
            with self.assertRaises(ValueError):
                _i54_validate_surface_domains(_test_surface_domain_prepare_rehash(result), allow_unprepared=True)

    def test_rehashed_usage_zero_cannot_hide_actual_fine_work(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        result = _i54__plain(_i54_evaluate_surface_domains(candidate, fine_configurations(candidate)))
        for item in result['domains']:
            item['charged_coarse_cells'] = 0
            item['charged_fine_cells'] = 0
        result['usage']['coarse_work_cells'] = 0
        result['usage']['fine_cells'] = 0
        with self.assertRaisesRegex(ValueError, 'charged'):
            _i54_validate_surface_domains(_test_surface_domain_prepare_rehash(result))

    def test_rehashed_original_attempt_cap_cannot_be_relaxed(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import validate_surface_domains as _i54_validate_surface_domains
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        result = _i54__plain(_i54_evaluate_surface_domains(candidate, fine_configurations(candidate)))
        result['configurations']['1']['recovery_recipe']['max_attempts'] = 1
        with self.assertRaisesRegex(ValueError, 'recovery.*bounds'):
            _i54_validate_surface_domains(_test_surface_domain_prepare_rehash(result))

    def test_rehashed_fine_geometry_and_publication_rejected(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i54_evaluate_surface_domains
        from terrain_pipeline.surface_domain import load_surface_domains as _i54_load_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_identity import _plain as _i54__plain
        from terrain_pipeline.artifacts.contracts import array_hash as _i54_array_hash
        from terrain_pipeline.artifacts.contracts import digest as _i54_digest
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        result = _i54__plain(_i54_evaluate_surface_domains(candidate, fine_configurations(candidate)))
        surface = result['domains'][0]['recovery']['surface']
        surface['arrays']['final_surface_m'] = surface['arrays']['final_surface_m'].copy()
        surface['arrays']['final_surface_m'][30, 30] -= 100.0
        surface['identity']['parameters']['output_sha256'] = _i54_digest({name: _i54_array_hash(value) for name, value in surface['arrays'].items()})
        surface['identity_sha256'] = _i54_digest(surface['identity'])
        _test_surface_domain_prepare_rehash(result['domains'][0]['recovery'])
        _test_surface_domain_prepare_rehash(result)
        with _i54_tempfile.TemporaryDirectory() as directory:
            path = _i54_Path(directory) / 'rehash.npz'
            write_rehashed_bundle(result, path)
            with self.assertRaises(ValueError):
                _i54_load_surface_domains(path)

    def test_candidate_default_load_and_duplicate_member_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_domains as _i54_load_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        from terrain_pipeline.surface_domain import save_surface_domains as _i54_save_surface_domains
        candidate = _i54_plan_surface_domains(**complete_two_domain_inputs())
        with _i54_tempfile.TemporaryDirectory() as directory:
            path = _i54_Path(directory) / 'candidate.npz'
            _i54_save_surface_domains(candidate, path)
            with self.assertRaises(ValueError):
                _i54_load_surface_domains(path)
            _i54_load_surface_domains(path, allow_unprepared=True)
            with self.assertRaises(FileExistsError):
                _i54_save_surface_domains(candidate, path)
            with _i54_zipfile.ZipFile(path, 'a') as archive:
                archive.writestr('manifest.npy', archive.read('manifest.npy'))
            with self.assertRaises(ValueError):
                _i54_load_surface_domains(path, allow_unprepared=True)

    def test_nonfinite_valid_source_rejected(self):
        from terrain_pipeline.surface_domain import plan_surface_domains as _i54_plan_surface_domains
        inputs = complete_two_domain_inputs()
        inputs['height_m'][1, 1] = _i54_np.nan
        with self.assertRaises(ValueError):
            _i54_plan_surface_domains(**inputs)

def recovery_case(kind='baseline'):
    from terrain_pipeline.surface_hydraulics import RerouteRecipe as _i63_RerouteRecipe
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i63_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i63_plan_channel
    from terrain_pipeline.surface_domain import FineGrid as _i63_FineGrid
    from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _i63_InundationRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _i63_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _i63_SectionRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i63_NetworkValleyRecipe
    from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i63_SurfaceNetworkBudget
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i63_ValleyGeometryRecipe
    base = _x4_confluence_plan()
    arrays = base['arrays']
    height = arrays['source_height_m'].copy()
    discharge = arrays['discharge_m3_s'].copy()
    discharge.flat[[17, 24, 31, 38, 45]] = 0.2
    receiver, order, outlets = (arrays['receiver'], arrays['order'], arrays['outlet_mask'])
    params = base['identity']['parameters']
    channel = _i63_ChannelRecipe(**{name: params[name] for name in _i63_ChannelRecipe.__dataclass_fields__})
    if kind == 'valley':
        height[3, 3] += 3.5
    if kind == 'reroute':
        height[:] = 10.0
        receiver = _i63_np.full(49, -1, dtype=_i63_np.int64)
        for row in range(1, 6):
            receiver[row * 7 + 3] = (row + 1) * 7 + 3
        outlets = (receiver == -1).reshape((7, 7))
        order = _i63_np.array(list(_i63_np.flatnonzero(outlets.ravel())) + [38, 31, 24, 17, 10], dtype=_i63_np.int64)
        discharge[:] = 0.0
        discharge[1:, 3] = 0.1
        channel = _i63_replace(channel, reference_width_m=2.0, min_width_m=2.0, max_width_m=2.0)
    plan = _i63_plan_channel(height, receiver, order, outlets, discharge, 10.0, 10.0, 0.0, 0.0, 0.0, 'recovery-synthetic-' + kind, channel)
    coarse_domain = _i63_np.ones((7, 7), bool)
    coarse_protected = _i63_np.zeros((7, 7), bool)
    empty = _i63_np.zeros((61, 61), bool)
    protected = empty.copy()
    legal = empty.copy()
    legal[-1, 27:34] = True
    outlet_stage = _i63_np.array([5.2])
    network = _i63_NetworkValleyRecipe(3.75, 30.0, 30.0, 1e-05)
    if kind == 'reroute':
        coarse_protected[3, 3] = True
        protected[30, 30] = True
        outlet_stage = _i63_np.array([9.8])
        network = _i63_NetworkValleyRecipe(1.0, 2.0, 2.0, 1e-05)
    return dict(plan=plan, coarse_domain=coarse_domain, coarse_protected=coarse_protected, fine=_i63_FineGrid(0.0, 0.0, 1.0, 1.0, (61, 61), ~empty, protected, legal), outlet_stage_m=outlet_stage, section_recipe=_i63_SectionRecipe(), stage_recipe=_i63_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), inundation_recipe=_i63_InundationRecipe(max_lateral_reach_m=15.0), budget=_i63_SurfaceNetworkBudget(4.0, 5000.0, 5000.0), network_recipe=network, valley_recipe=_i63_ValleyGeometryRecipe(4.0, 10000.0, 100000.0, 100000.0), reroute_recipe=_i63_RerouteRecipe(), recovery_recipe=_i63_RecoveryRecipe(max_attempts=20))

def mountain_coast_case():
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i63_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i63_plan_channel
    from terrain_pipeline.surface_domain import FineGrid as _i63_FineGrid
    from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _i63_InundationRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i63_NetworkValleyRecipe
    shape = (17, 17)
    height = _i63_np.full(shape, 135.0)
    for row in range(1, 17):
        height[row, 7:10] = 1.4 - row * 0.02
    for row in range(2, 6):
        for column in (row + 2, 14 - row):
            height[row, column - 1:column + 2] = 1.4 - row * 0.02
    height[1, 3:6] = 1.36
    height[1, 11:14] = 1.36
    height[15, 7:10] = 1.08
    height[16, 7:10] = 1.06
    valley = height < 2.0
    for row, column in _i63_np.argwhere(valley):
        for rr in range(max(1, row - 1), min(7, row + 2)):
            for cc in range(max(0, column - 1), min(17, column + 2)):
                if not valley[rr, cc]:
                    height[rr, cc] = 1.4 - rr * 0.02
    receiver = _i63_np.full(height.size, -1, dtype=_i63_np.int64)
    for row in range(2, 6):
        for column in (row + 2, 14 - row):
            target = 8 if row == 5 else column + (1 if column < 8 else -1)
            receiver[row * 17 + column] = (row + 1) * 17 + target
    for row in range(6, 15):
        receiver[row * 17 + 8] = (row + 1) * 17 + 8
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import graph_connection
    mesh = grid_mesh(shape, dx_m=10.0)
    intended = receiver.copy()
    receiver[:] = -1
    for donor in _i63_np.flatnonzero(intended >= 0):
        path = graph_connection(int(donor), int(intended[donor]), 17, shape=shape, mesh=mesh)
        for first, second in zip(path, path[1:]):
            receiver[first[0] * 17 + first[1]] = second[0] * 17 + second[1]
    outlets = (receiver == -1).reshape(shape)
    order = []
    seen = set()
    for start in range(height.size):
        chain = []
        cell = start
        while cell >= 0 and cell not in seen:
            seen.add(cell)
            chain.append(cell)
            cell = int(receiver[cell])
        order.extend(reversed(chain))
    discharge = _i63_np.zeros(height.size)
    discharge[[2 * 17 + 4, 2 * 17 + 12]] = 0.1
    for cell in reversed(order):
        if receiver[cell] >= 0:
            discharge[receiver[cell]] += discharge[cell]
    channel = _i63_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=4.0, min_width_m=4.0, max_width_m=4.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, min_bed_slope_m_per_m=1e-05, max_cut_m=4.0)
    plan = _i63_plan_channel(height, receiver, _i63_np.array(order, dtype=_i63_np.int64), outlets, discharge.reshape(shape), 10.0, 10.0, 0.0, 0.0, 1.08, 'engineered-mountain-coast-not-real', channel)
    empty = _i63_np.zeros((161, 161), bool)
    legal = empty.copy()
    legal[150:, 70:91] = True
    case = recovery_case()
    case.update(plan=plan, coarse_domain=_i63_np.ones(shape, bool), coarse_protected=_i63_np.zeros(shape, bool), fine=_i63_FineGrid(0.0, 0.0, 1.0, 1.0, (161, 161), ~empty, empty, legal), outlet_stage_m=_i63_np.array([1.3]), inundation_recipe=_i63_InundationRecipe(max_lateral_reach_m=35.0), network_recipe=_i63_NetworkValleyRecipe(1.0, 4.0, 4.0, 1e-05), recovery_recipe=_i63_RecoveryRecipe(max_attempts=2))
    ocean = _i63_np.zeros(shape, bool)
    ocean[15:, 7:10] = True
    ocean.flags.writeable = False
    land = ~ocean
    land.flags.writeable = False
    return (case, land, ocean)

def rewrite_bundle(path, transform):
    from terrain_pipeline.artifacts.contracts import digest as _i63_digest
    with _i63_np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files if name != 'manifest'}
        manifest = _i63_json.loads(str(archive['manifest'].item()))
    transform(manifest, arrays)
    manifest['tree_sha256'] = _i63_digest(manifest['tree'])
    _i63_np.savez_compressed(path, manifest=_i63_json.dumps(manifest, sort_keys=True), **arrays)

class SurfaceNetworkRecoveryTests(_i63_unittest.TestCase):

    def test_baseline_conservative_success(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case()
        original = case['plan']['arrays']['source_height_m'].copy()
        result = _i63_recover_surface_network(**case)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['selected_method'], 'baseline')
        _i63_np.testing.assert_array_equal(original, case['plan']['arrays']['source_height_m'])
        self.assertEqual(result['surface']['status'], 'prepared')

    def test_valley_requires_actual_fine_ledger(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        result = _i63_recover_surface_network(**recovery_case('valley'))
        self.assertTrue(result['accepted'])
        self.assertEqual(result['selected_method'], 'network_valley')
        self.assertFalse(result['attempts'][0]['accepted'])
        self.assertEqual(result['fine_ledger']['status'], 'prepared')
        self.assertGreater(result['fine_ledger']['summary']['valley_cut_volume_m3'], 0.0)

    def test_automatic_protection_reroute_uses_upstream_donor(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case('reroute')
        result = _i63_recover_surface_network(**case)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['selected_method'], 'reroute_bed')
        chosen = result['attempts'][-1]
        self.assertNotEqual(chosen['source_grid_zx'], [3, 3])
        self.assertLess(chosen['source_grid_zx'][0], 3)
        self.assertGreater(chosen['anchor_grid_zx'][0], 3)
        self.assertNotIn([3, 3], chosen['path_grid_zx'])
        self.assertFalse(_i63_np.any(result['final_plan']['arrays']['channel_mask'] & case['coarse_protected']))
        self.assertEqual(result['final_plan']['arrays']['discharge_m3_s'][6, 3], 0.1)

    def test_budget_failure_has_trace_and_never_relaxes(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i63_SurfaceNetworkBudget
        case = recovery_case()
        case['budget'] = _i63_SurfaceNetworkBudget(4.0, 0.0, 0.0)
        result = _i63_recover_surface_network(**case)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['attempts'][0]['failures']['volume'])
        self.assertEqual(result['inputs']['budget']['max_cut_volume_m3'], 0.0)

    def test_fine_ledger_total_budget_rejects_surface_prepared(self):
        from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case('valley')
        case['valley_recipe'] = _i63_replace(case['valley_recipe'], max_total_cut_volume_m3=0.0)
        case['recovery_recipe'] = _i63_RecoveryRecipe(max_attempts=2)
        result = _i63_recover_surface_network(**case)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['surface']['status'], 'prepared')
        self.assertTrue(result['attempts'][1]['failures']['ledger_total_volume'])

    def test_coarse_fine_mask_mismatch_rejected(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        for mask in ('domain_mask', 'protected_mask'):
            case = recovery_case()
            changed = getattr(case['fine'], mask).copy()
            changed[30, 30] = not changed[30, 30]
            case['fine'] = _i63_replace(case['fine'], **{mask: changed})
            with self.subTest(mask=mask), self.assertRaisesRegex(ValueError, 'disagree'):
                _i63_recover_surface_network(**case)

    def test_domain_blocks_coarse_route_and_fine_cut(self):
        from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case()
        domain = case['fine'].domain_mask.copy()
        domain[30, 30] = False
        case['fine'] = _i63_replace(case['fine'], domain_mask=domain)
        case['coarse_domain'][3, 3] = False
        case['recovery_recipe'] = _i63_RecoveryRecipe(max_attempts=2)
        result = _i63_recover_surface_network(**case)
        self.assertFalse(result['accepted'])
        self.assertTrue(result['attempts'][0]['failures']['coarse_domain'])

    def test_nonconservative_q_rejected_before_attempts(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i63_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i63_plan_channel
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case()
        arrays = case['plan']['arrays']
        discharge = arrays['discharge_m3_s'].copy()
        discharge[2, 3] = 0.1
        case['plan'] = _i63_plan_channel(arrays['source_height_m'], arrays['receiver'], arrays['order'], arrays['outlet_mask'], discharge, 10.0, 10.0, 0.0, 0.0, 0.0, 'bad-q', _i63_ChannelRecipe(**{name: case['plan']['identity']['parameters'][name] for name in _i63_ChannelRecipe.__dataclass_fields__}))
        with self.assertRaisesRegex(ValueError, 'conservative'):
            _i63_recover_surface_network(**case)

    def test_all_derived_plan_fields_recomputed(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        for field in ('bounded_bed_m', 'channel_mask', 'nominal_width_m'):
            case = recovery_case()
            case['plan'] = _i63_deepcopy(case['plan'])
            case['plan']['arrays'][field] = case['plan']['arrays'][field].copy()
            case['plan']['arrays'][field].flat[9] = 0
            with self.subTest(field=field), self.assertRaises(ValueError):
                _i63_recover_surface_network(**case)

    def test_reroute_pairs_strict_integer_and_bed_bound(self):
        from terrain_pipeline.surface_hydraulics import RerouteRecipe as _i63_RerouteRecipe
        from terrain_pipeline.surface_hydraulics import reroute_channel as _i63_reroute_channel
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case('reroute')
        for endpoint in ((1.1, 3), (True, 3), (1,), (1, 3, 4)):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                _i63_reroute_channel(case['plan'], endpoint, (4, 3), case['coarse_domain'], case['coarse_protected'])
        case['reroute_recipe'] = _i63_RerouteRecipe(max_extra_cut_m=4.1)
        with self.assertRaisesRegex(ValueError, 'original allowed bed'):
            _i63_recover_surface_network(**case)

    def test_search_attempt_exhaustion_is_deterministic(self):
        from terrain_pipeline.surface_hydraulics import RerouteRecipe as _i63_RerouteRecipe
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case('reroute')
        case['reroute_recipe'] = _i63_RerouteRecipe(max_expansions=1)
        first = _i63_recover_surface_network(**case)
        second = _i63_recover_surface_network(**case)
        self.assertFalse(first['accepted'])
        self.assertEqual(first['identity_sha256'], second['identity_sha256'])
        self.assertTrue(any(('expansion bound' in attempt.get('error', '') for attempt in first['attempts'])))
        self.assertLessEqual(len(first['attempts']), case['recovery_recipe'].max_attempts)

    def test_fine_work_exhaustion_preserves_diagnostic(self):
        from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case('valley')
        case['recovery_recipe'] = _i63_RecoveryRecipe(max_total_fine_cells=61 * 61)
        result = _i63_recover_surface_network(**case)
        self.assertEqual(len(result['attempts']), 1)
        self.assertFalse(result['accepted'])
        self.assertTrue(result['summary']['fine_work_limit_reached'])

    def test_cell_memory_and_recipe_bounds_rejected(self):
        from terrain_pipeline.surface_domain import FineGrid as _i63_FineGrid
        from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        for recipe in (_i63_RecoveryRecipe(max_fine_cells=100), _i63_RecoveryRecipe(max_coarse_cells=10), _i63_RecoveryRecipe(max_working_bytes=100)):
            case = recovery_case()
            case['recovery_recipe'] = recipe
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                _i63_recover_surface_network(**case)
        with self.assertRaises(ValueError):
            _i63_RecoveryRecipe(max_attempts=True)
        with self.assertRaises(ValueError):
            _i63_FineGrid(0.0, 0.0, 0.0, 1.0, (3, 3), _i63_np.ones((3, 3), bool), _i63_np.zeros((3, 3), bool), _i63_np.zeros((3, 3), bool))

    def test_outlet_stage_and_source_identity_invalid(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case()
        case['outlet_stage_m'] = _i63_np.array([_i63_np.nan])
        with self.assertRaises(ValueError):
            _i63_recover_surface_network(**case)

    def test_legal_outlet_elsewhere_cannot_replace_active_outlet(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case = recovery_case()
        legal = case['fine'].legal_outlet_mask.copy()
        legal[60, 30] = False
        case['fine'] = _i63_replace(case['fine'], legal_outlet_mask=legal)
        with self.assertRaisesRegex(ValueError, 'active plan outlets'):
            _i63_recover_surface_network(**case)
        case = recovery_case()
        case['plan']['identity']['parameters']['source_identity'] = ''
        with self.assertRaises(ValueError):
            _i63_recover_surface_network(**case)

    def test_success_and_failure_bundles_readonly_no_overwrite(self):
        from terrain_pipeline.surface_domain import RecoveryRecipe as _i63_RecoveryRecipe
        from terrain_pipeline.surface_domain import load_surface_network_recovery as _i63_load_surface_network_recovery
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import save_surface_network_recovery as _i63_save_surface_network_recovery
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i63_SurfaceNetworkBudget
        with _i63_tempfile.TemporaryDirectory() as directory:
            for kind in ('baseline', 'valley', 'reroute', 'failed'):
                case = recovery_case('baseline' if kind == 'failed' else kind)
                if kind == 'failed':
                    case['budget'] = _i63_SurfaceNetworkBudget(4.0, 0.0, 0.0)
                    case['recovery_recipe'] = _i63_RecoveryRecipe(max_attempts=2)
                original = _i63_recover_surface_network(**case)
                path = _i63_Path(directory) / (kind + '.npz')
                _i63_save_surface_network_recovery(original, path)
                loaded = _i63_load_surface_network_recovery(path)
                self.assertEqual(loaded['identity_sha256'], original['identity_sha256'])
                with self.assertRaises(ValueError):
                    loaded['final_plan']['arrays']['source_height_m'].flags.writeable = True
                with self.assertRaises(FileExistsError):
                    _i63_save_surface_network_recovery(original, path)

    def test_rehashed_summary_status_and_surface_forgery_rejected(self):
        from terrain_pipeline.surface_domain import _fingerprint as _i63__fingerprint
        from terrain_pipeline.surface_domain import load_surface_network_recovery as _i63_load_surface_network_recovery
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import save_surface_network_recovery as _i63_save_surface_network_recovery
        from terrain_pipeline.surface_domain import validate_surface_network_recovery as _i63_validate_surface_network_recovery
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i63_SurfaceNetworkBudget
        result = _i63_recover_surface_network(**recovery_case('valley'))
        with _i63_tempfile.TemporaryDirectory() as directory:
            path = _i63_Path(directory) / 'forged.npz'
            _i63_save_surface_network_recovery(result, path)
            rewrite_bundle(path, lambda manifest, arrays: manifest['tree']['attempts'][0].update(accepted=True))
            with self.assertRaisesRegex(ValueError, 'semantic replay'):
                _i63_load_surface_network_recovery(path)
        case = recovery_case()
        case['budget'] = _i63_SurfaceNetworkBudget(4.0, 0.0, 0.0)
        forged = _i63_recover_surface_network(**case)
        forged.update(status='accepted', accepted=True, selected_method='baseline')
        forged['identity_sha256'] = _i63__fingerprint({key: value for key, value in forged.items() if key != 'identity_sha256'})
        with self.assertRaises(ValueError):
            _i63_validate_surface_network_recovery(forged)

    def test_hash_tamper_and_load_garbage_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_recovery as _i63_load_surface_network_recovery
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import save_surface_network_recovery as _i63_save_surface_network_recovery
        with _i63_tempfile.TemporaryDirectory() as directory:
            path = _i63_Path(directory) / 'tampered.npz'
            _i63_save_surface_network_recovery(_i63_recover_surface_network(**recovery_case()), path)

            def corrupt(manifest, arrays):
                arrays[next(iter(arrays))] = arrays[next(iter(arrays))].copy()
                arrays[next(iter(arrays))].flat[0] += 1
            rewrite_bundle(path, corrupt)
            with self.assertRaises(ValueError):
                _i63_load_surface_network_recovery(path)
            path.write_bytes(b'not a bundle')
            with self.assertRaises(ValueError):
                _i63_load_surface_network_recovery(path)

    def test_atomic_save_failure_leaves_no_destination(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import save_surface_network_recovery as _i63_save_surface_network_recovery
        result = _i63_recover_surface_network(**recovery_case())
        with _i63_tempfile.TemporaryDirectory() as directory:
            path = _i63_Path(directory) / 'never.npz'
            with _i63_patch('terrain_pipeline.surface_domain.os.link', side_effect=OSError('no link')):
                with self.assertRaises(OSError):
                    _i63_save_surface_network_recovery(result, path)
            self.assertEqual(list(_i63_Path(directory).iterdir()), [])

    def test_legacy_explicit_reroute_interface_still_accepted(self):
        from terrain_pipeline.surface_domain import prepare_with_reroute as _i63_prepare_with_reroute
        case = recovery_case('reroute')
        fine = case['fine']
        result = _i63_prepare_with_reroute(case['plan'], (1, 3), (4, 3), case['coarse_domain'], case['coarse_protected'], fine.origin_x_m, fine.origin_z_m, fine.spacing_x_m, fine.spacing_z_m, fine.shape_zx, fine.domain_mask, fine.protected_mask, fine.legal_outlet_mask, case['outlet_stage_m'], case['section_recipe'], case['stage_recipe'], case['inundation_recipe'], case['budget'])
        self.assertTrue(result['accepted'])

    def test_rehashed_actual_surface_array_cannot_load(self):
        from terrain_pipeline.surface_domain import load_surface_network_recovery as _i63_load_surface_network_recovery
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import save_surface_network_recovery as _i63_save_surface_network_recovery
        result = _i63_recover_surface_network(**recovery_case())
        with _i63_tempfile.TemporaryDirectory() as directory:
            path = _i63_Path(directory) / 'surface_forged.npz'
            _i63_save_surface_network_recovery(result, path)

            def corrupt(manifest, arrays):
                from terrain_pipeline.artifacts.contracts import array_hash
                reference = manifest['tree']['surface']['arrays']['final_surface_m']
                array = arrays[reference['$array']].copy()
                array[30, 30] -= 0.1
                arrays[reference['$array']] = array
                reference['sha256'] = array_hash(array)
            rewrite_bundle(path, corrupt)
            with self.assertRaisesRegex(ValueError, 'semantic replay'):
                _i63_load_surface_network_recovery(path)

    def test_manifest_duplicate_keys_and_nonfinite_constants_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_recovery as _i63_load_surface_network_recovery
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        from terrain_pipeline.surface_domain import save_surface_network_recovery as _i63_save_surface_network_recovery
        result = _i63_recover_surface_network(**recovery_case())
        with _i63_tempfile.TemporaryDirectory() as directory:
            path = _i63_Path(directory) / 'strict_json.npz'
            _i63_save_surface_network_recovery(result, path)
            with _i63_np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != 'manifest'}
                encoded = str(archive['manifest'].item())
            for invalid, reason in (('{"format_version":0,' + encoded[1:], 'duplicate'), ('{"extra":NaN,' + encoded[1:], 'nonfinite'), ('{"extra":Infinity,' + encoded[1:], 'nonfinite')):
                _i63_np.savez_compressed(path, manifest=invalid, **arrays)
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                    _i63_load_surface_network_recovery(path)

    def test_manifest_scalar_unicode_header_required(self):
        from terrain_pipeline.surface_domain import load_surface_network_recovery as _i63_load_surface_network_recovery
        with _i63_tempfile.TemporaryDirectory() as directory:
            path = _i63_Path(directory) / 'wrong_manifest.npz'
            for manifest in (_i63_np.array(['{}']), _i63_np.array(1), _i63_np.array(b'{}')):
                _i63_np.savez_compressed(path, manifest=manifest)
                with self.subTest(dtype=manifest.dtype), self.assertRaisesRegex(ValueError, 'Unicode scalar'):
                    _i63_load_surface_network_recovery(path)

    def test_mountain_coast_has_frozen_evidence_and_actual_gate(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i63_recover_surface_network
        case, land, ocean = mountain_coast_case()
        height = case['plan']['arrays']['source_height_m']
        self.assertGreaterEqual(float(height.max() - height.min()), 100.0)
        self.assertFalse(land.flags.writeable)
        self.assertFalse(ocean.flags.writeable)
        result = _i63_recover_surface_network(**case)
        self.assertTrue(result['accepted'], result['attempts'])
        self.assertEqual(result['summary']['outlet_evidence'], 'caller_supplied_not_naturally_certified')

def engineering_proofs():
    from terrain_pipeline.surface_domain import FineGrid as _i57_FineGrid
    from terrain_pipeline.surface_domain import recover_surface_network as _i57_recover_surface_network
    first_case = recovery_case()
    second_case = recovery_case()
    empty = _i57_np.zeros((31, 31), bool)
    legal = empty.copy()
    legal[-1, 14:17] = True
    second_case['fine'] = _i57_FineGrid(0.0, 0.0, 2.0, 2.0, (31, 31), ~empty, empty, legal)
    first = _i57_recover_surface_network(**first_case)
    second = _i57_recover_surface_network(**second_case)
    if not first['accepted'] or not second['accepted']:
        raise AssertionError('actual recovery fixture not accepted')
    return (first, second)

def positive_sources(proofs):
    return (_i57_mosaic.DomainFineSource(proofs[0], 1, (0, 61, 0, 7)), _i57_mosaic.DomainFineSource(proofs[1], 2, (0, 31, 3, 7)))

def wet_sources(proofs):
    return (_i57_mosaic.DomainFineSource(proofs[0], 1, (20, 61, 20, 31)), _i57_mosaic.DomainFineSource(proofs[1], 2, (10, 31, 15, 21)))

def build(sources, **kwargs):
    return _i57_mosaic.prepare_fine_mosaic(sources, metric_grid={'coordinate_system': 'metric-xz-m'}, vertical_datum='engineering-relative-sea-zero', source_identity='accepted-recovery-cross-precision-slice', sea_level_elevation_m=0.0, **kwargs)

def rehash_surface(proof):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i57_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i57_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i57_digest
    from terrain_pipeline.surface_domain import _fingerprint as _i57__fingerprint
    surface = proof['surface']
    params = surface['identity']['parameters']
    params['output_sha256'] = _i57_digest({name: _i57_array_hash(array) for name, array in surface['arrays'].items()})
    params['summary_sha256'] = _i57_digest(surface['summary'])
    surface['identity_sha256'] = _i57_ArtifactIdentity(**surface['identity']).sha256
    proof['identity_sha256'] = _i57__fingerprint({key: child for key, child in proof.items() if key != 'identity_sha256'})

def _test_surface_fine_mosaic_write_bundle(result, path):
    arrays = {}
    tree = _i57_mosaic._surface_fine_mosaic_tree(result, arrays)
    manifest = {'format_version': 2, 'tree': tree, 'tree_sha256': _i57_mosaic._identity(tree)}
    with _i57_zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', _i57_mosaic._surface_fine_mosaic_json(manifest))
        for name, array in arrays.items():
            with _i57_io.BytesIO() as stream:
                _i57_np.save(stream, _i57_np.ascontiguousarray(array), allow_pickle=False)
                archive.writestr(name, stream.getvalue())

class SurfaceFineMosaicTests(_i57_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.proofs = engineering_proofs()
        cls.sources = positive_sources(cls.proofs)
        cls.result = build(cls.sources)

    def test_continuous_cross_precision_cells_shared_nodes(self):
        result = self.result
        self.assertEqual(result['grid']['spacing_x_m'], 1.0)
        self.assertEqual(result['cells'].shape, (720, 4))
        self.assertEqual(result['triangles'].shape, (1440, 3))
        self.assertEqual(len(result['nodes']['x_m']), 793)
        self.assertEqual(len(set(zip(result['nodes']['x_m'], result['nodes']['z_m']))), 793)
        _i57_np.testing.assert_array_equal(result['cells'][5, [1, 2]], result['cells'][6, [0, 3]])
        self.assertFalse(result['full_domain_mosaic_prepared'])
        self.assertEqual(result['summary']['unique_cell_area_m2'], 720.0)
        self.assertTrue(_i57_np.any(result['contributors']['weights'] == 0.5))
        self.assertAlmostEqual(result['summary']['q_local_m3_s'], 0.14)
        self.assertEqual(len(result['q_cuts']), 1)

    def test_independent_proof_inactive_nonzero_seam_q_rejected(self):
        from terrain_pipeline.surface_domain import recover_surface_network as _i57_recover_surface_network
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i57_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i57_plan_channel
        case = recovery_case()
        plan = case['plan']
        arrays, params = (plan['arrays'], plan['identity']['parameters'])
        discharge = arrays['discharge_m3_s'].copy()
        discharge[0, 0] += 0.001
        case['plan'] = _i57_plan_channel(arrays['source_height_m'], arrays['receiver'], arrays['order'], arrays['outlet_mask'], discharge, 10.0, 10.0, 0.0, 0.0, 0.0, 'independent-Q-proof', _i57_ChannelRecipe(**{name: params[name] for name in _i57_ChannelRecipe.__dataclass_fields__}))
        proof = _i57_recover_surface_network(**case)
        self.assertTrue(proof['accepted'])
        with self.assertRaisesRegex(ValueError, 'duplicate nonzero Q'):
            build((_i57_replace(self.sources[0], window_zx=(0, 61, 0, 11)), _i57_replace(self.sources[1], proof=proof, window_zx=(0, 61, 10, 13))))

    def test_same_graph_shared_nonzero_inactive_q_counted_once(self):
        positions = _i57_np.column_stack((_i57_np.arange(13), _i57_np.zeros(13)))
        arrays = {'receiver': _i57_np.full(13, -1, _i57_np.int64), 'order': _i57_np.arange(13), 'world_xz_m': positions, 'discharge_m3_s': _i57_np.full(13, 0.01), 'local_discharge_m3_s': _i57_np.full(13, 0.01), 'active_mask': _i57_np.zeros(13, bool), 'outlet_mask': _i57_np.ones(13, bool), 'node_stage_m': _i57_np.zeros(13)}
        fine = {'origin_x_m': 0.0, 'origin_z_m': 0.0, 'spacing_x_m': 1.0, 'spacing_z_m': 1.0}
        result = {'grid': {'bbox_xz_m': [0.0, 12.0, 0.0, 1.0]}, 'q_tolerance_m3_s': 1e-08, 'proofs': {'first': {'inputs': {'fine': fine}}, 'second': {'inputs': {'fine': fine}}}, 'sources': [{'proof_sha256': 'first', 'window_zx': [0, 2, 0, 7]}, {'proof_sha256': 'second', 'window_zx': [0, 2, 6, 13]}]}
        cuts, summary = _i57_mosaic._q_cut(result, {'first': arrays, 'second': arrays})
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(summary['q_local_m3_s'], 0.13)
        changed = {name: array.copy() for name, array in arrays.items()}
        changed['local_discharge_m3_s'][0] += 0.001
        changed['discharge_m3_s'][0] += 0.001
        with self.assertRaisesRegex(ValueError, 'duplicate nonzero Q'):
            _i57_mosaic._q_cut(result, {'first': arrays, 'second': changed})

    def test_terminal_q_not_all_accumulated_nodes(self):
        from terrain_pipeline.surface_identity import _plain as _i57__merged_mosaic__plain
        result = build((_i57_mosaic.DomainFineSource(self.proofs[0], 1),))
        graph = _i57_mosaic._payload(_i57__merged_mosaic__plain(self.proofs[0]))
        terminal = float(graph['discharge_m3_s'][graph['receiver'] < 0].sum())
        self.assertAlmostEqual(result['summary']['q_outgoing_m3_s'], terminal)
        self.assertAlmostEqual(result['summary']['q_local_m3_s'], terminal)
        self.assertGreater(float(graph['discharge_m3_s'].sum()), terminal)

    def test_real_wet_cross_precision_seam_and_unique_local_cut(self):
        from terrain_pipeline.surface_identity import _plain as _i57__merged_mosaic__plain
        result = build(wet_sources(self.proofs))
        self.assertEqual(result['cells'].shape, (800, 4))
        self.assertEqual(int(result['wet_cells'].sum()), 645)
        self.assertEqual(int((result['nodes']['wet_mask'] & (result['nodes']['x_m'] == 30)).sum()), 41)
        self.assertGreater(result['summary']['unique_cut_volume_m3'], 90.0)
        self.assertGreater(result['summary']['actual_wet_water_volume_m3'], 220.0)
        graph = _i57_mosaic._payload(_i57__merged_mosaic__plain(self.proofs[0]))
        selected = _i57_np.array([row * 7 + col for row in range(2, 7) for col in range(2, 5)])
        local = float(graph['local_discharge_m3_s'][selected].sum())
        self.assertAlmostEqual(local, 0.09)
        self.assertAlmostEqual(result['summary']['q_local_m3_s'], local)
        self.assertAlmostEqual(result['summary']['q_outgoing_m3_s'], 0.2 + local)
        self.assertAlmostEqual(result['summary']['q_incoming_m3_s'], 0.2)
        self.assertEqual(len(result['q_cuts']), 1)
        self.assertTrue(_i57_mosaic.validate_fine_mosaic(result))

    def test_real_wet_cross_precision_nonmatching_seam_rejected(self):
        with self.assertRaisesRegex(ValueError, 'seam conflict'):
            build((_i57_mosaic.DomainFineSource(self.proofs[0], 1, (0, 61, 20, 31)), _i57_mosaic.DomainFineSource(self.proofs[1], 2, (0, 31, 15, 21))))

    def test_explicit_proof_bound_gap_extension(self):
        first, second = self.sources
        second = _i57_replace(second, window_zx=(0, 31, 4, 7))
        with self.assertRaises(_i57__merged_mosaic_MosaicCoverageError):
            build((first, second))
        extension = _i57_mosaic.DomainFineSource(self.proofs[0], 3, (0, 61, 6, 9), role='extension')
        result = build((first, second), source_extensions=(extension,))
        self.assertEqual(int((result['cell_owner'] == 2).sum()), 120)

    def test_actual_wet_sloping_stage_is_interpolated(self):
        arrays = {'source_surface_m': _i57_np.full((2, 2), 5.0), 'final_surface_m': _i57_np.full((2, 2), 3.0), 'total_cut_m': _i57_np.full((2, 2), 2.0), 'domain_mask': _i57_np.ones((2, 2), bool), 'wet_mask': _i57_np.ones((2, 2), bool), 'water_surface_m': _i57_np.array([[4.0, 4.1], [4.2, 4.3]])}
        source = {'unknown_mask': _i57_np.zeros((2, 2), bool), 'protected_mask': _i57_np.zeros((2, 2), bool)}
        values = _i57_mosaic._evaluate_support(source, arrays, _i57_np.arange(4), _i57_np.full(4, 0.25), 1e-08)
        self.assertTrue(values[2])
        self.assertAlmostEqual(values[3], 4.15)
        arrays['water_surface_m'][1, :] = _i57_np.nan
        arrays['wet_mask'][1, :] = False
        values = _i57_mosaic._evaluate_support(source, arrays, _i57_np.arange(4), _i57_np.array([0.5, 0.5, 0.0, 0.0]), 1e-08)
        self.assertTrue(values[2])
        self.assertAlmostEqual(values[3], 4.05)

    def test_real_old_domain_gap_rejected_and_retained(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i57_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i57_plan_surface_domains
        candidate = _i57_plan_surface_domains(**complete_two_domain_inputs())
        prepared = _i57_evaluate_surface_domains(candidate, fine_configurations(candidate))
        with self.assertRaises(_i57__merged_mosaic_MosaicCoverageError) as caught:
            build(prepared)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic['missing_cell_count'], 600)
        self.assertEqual(diagnostic['status'], 'diagnostic')
        with _i57_tempfile.TemporaryDirectory() as directory:
            path = _i57_Path(directory) / 'gap.npz'
            _i57_mosaic.save_fine_mosaic(diagnostic, path, allow_unprepared=True)
            with self.assertRaises(ValueError):
                _i57_mosaic.load_fine_mosaic(path)
            loaded = _i57_mosaic.load_fine_mosaic(path, allow_unprepared=True)
            self.assertEqual(loaded['missing_cell_count'], 600)

    def test_plain_source_self_certification_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cannot self-certify'):
            build(({'h0_m': _i57_np.ones((2, 2)), 'status': 'prepared'},))

    def test_unknown_positive_weight_support_rejected(self):
        unknown = _i57_np.zeros((61, 61), bool)
        unknown[1, 1] = True
        with self.assertRaisesRegex(ValueError, 'unknown'):
            build((_i57_replace(self.sources[0], unknown_mask=unknown), self.sources[1]))

    def test_protection_on_modified_actual_wet_support_rejected(self):
        from terrain_pipeline.surface_identity import _plain as _i57__merged_mosaic__plain
        protected = _i57_np.zeros((61, 61), bool)
        graph = _i57_mosaic._payload(_i57__merged_mosaic__plain(self.proofs[0]))
        protected[tuple(_i57_np.argwhere(graph['wet_mask'])[0])] = True
        with self.assertRaisesRegex(ValueError, 'protected'):
            build((_i57_mosaic.DomainFineSource(self.proofs[0], 1, protected_mask=protected),))

    def test_overlap_and_seam_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            build((self.sources[0], _i57_replace(self.sources[0], domain_id=2)))
        restriction = _i57_np.zeros((31, 31), bool)
        restriction[:, 3] = True
        with self.assertRaisesRegex(ValueError, 'seam conflict'):
            build((self.sources[0], _i57_replace(self.sources[1], protected_mask=restriction)))

    def test_cancel_and_retained_resource_preflight(self):
        with self.assertRaises(InterruptedError):
            build(self.sources, cancel=lambda: True)
        with _i57_patch.object(_i57_mosaic, '_source', side_effect=AssertionError('proof allocation before preflight')):
            with self.assertRaisesRegex(ValueError, 'preflight'):
                build(self.sources, resources=_i57_mosaic.MosaicResources(max_retained_bytes=100))
        with self.assertRaisesRegex(ValueError, 'cell resource'):
            build(self.sources, resources=_i57_mosaic.MosaicResources(max_cells=10))

    def test_load_readonly_no_generation_or_recovery(self):
        with _i57_tempfile.TemporaryDirectory() as directory:
            path = _i57_Path(directory) / 'cells.npz'
            _i57_mosaic.save_fine_mosaic(self.result, path)
            with _i57_ExitStack() as stack:
                for name in ('_assemble', '_mesh', '_h0_support', '_stencil', '_grid', '_ownership', 'prepare_fine_mosaic', '_proof_gate'):
                    stack.enter_context(_i57_patch.object(_i57_mosaic, name, side_effect=AssertionError('load generated: ' + name)))
                for target in ('terrain_pipeline.surface_domain._fine_source', 'terrain_pipeline.surface_domain.recover_surface_network', 'terrain_pipeline.surface_domain.evaluate_surface_domains', 'terrain_pipeline.surface_domain.prepare_surface_network'):
                    stack.enter_context(_i57_patch(target, side_effect=AssertionError('load generated')))
                loaded = _i57_mosaic.load_fine_mosaic(path)
                query = _i57_mosaic.query_fine_mosaic(loaded)
            self.assertEqual(loaded['identity_sha256'], self.result['identity_sha256'])
            with self.assertRaises(ValueError):
                query['h0_m'].flags.writeable = True
            with self.assertRaises(TypeError):
                loaded['status'] = 'other'

    def test_atomic_no_overwrite_and_fd_cleanup(self):
        with _i57_tempfile.TemporaryDirectory() as directory:
            path = _i57_Path(directory) / 'cells.npz'
            descriptors = []
            original = _i57_tempfile.mkstemp

            def track(*args, **kwargs):
                result = original(*args, **kwargs)
                descriptors.append(result[0])
                return result
            with _i57_patch.object(_i57_mosaic.tempfile, 'mkstemp', side_effect=track):
                _i57_mosaic.save_fine_mosaic(self.result, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                _i57_mosaic.save_fine_mosaic(self.result, path)
            self.assertEqual(before, path.read_bytes())
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    __import__('os').fstat(descriptor)
            failed = _i57_Path(directory) / 'failed.npz'
            with _i57_patch.object(_i57_mosaic.os, 'link', side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):
                    _i57_mosaic.save_fine_mosaic(self.result, failed)
            self.assertFalse(failed.exists())
            self.assertEqual(list(_i57_Path(directory).glob('*.tmp')), [])

    def test_rehashed_contributors_mesh_q_unknown_rejected(self):
        for kind in ('weights', 'mesh', 'q', 'unknown', 'height'):
            record = mutable(self.result)
            if kind == 'weights':
                record['contributors']['weights'][0, 0] = [0.5, 0.5, 0.0, 0.0]
            elif kind == 'mesh':
                record['triangles'][0, 0] = 2
            elif kind == 'q':
                record['summary']['q_local_m3_s'] += 1.0
            elif kind == 'unknown':
                record['sources'][0]['unknown_mask'][0, 0] = True
            else:
                record['nodes']['h2_m'][0] -= 0.1
            with self.subTest(kind=kind), _i57_tempfile.TemporaryDirectory() as directory:
                path = _i57_Path(directory) / 'tampered.npz'
                _test_surface_fine_mosaic_write_bundle(rehash(record), path)
                with self.assertRaises(ValueError):
                    _i57_mosaic.load_fine_mosaic(path)

    def test_npy_payload_duplicate_zip_json_preflight(self):
        with _i57_tempfile.TemporaryDirectory() as directory:
            good = _i57_Path(directory) / 'good.npz'
            _i57_mosaic.save_fine_mosaic(self.result, good)
            with _i57_zipfile.ZipFile(good) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for kind in ('truncated', 'trailing', 'duplicate_zip', 'duplicate_json', 'raw_header'):
                path = _i57_Path(directory) / (kind + '.npz')
                modified = dict(members)
                name = next((name for name in modified if name.endswith('.npy')))
                if kind == 'truncated':
                    modified[name] = modified[name][:-1]
                elif kind == 'trailing':
                    modified[name] += b'extra'
                elif kind == 'duplicate_json':
                    modified['manifest.json'] = modified['manifest.json'].replace(b'{', b'{"format_version":2,', 1)
                elif kind == 'raw_header':
                    modified[name] = b'\x93NUMPY\x01\x00\xff\xff' + b' ' * 65535
                with _i57_warnings.catch_warnings(), _i57_zipfile.ZipFile(path, 'w') as archive:
                    _i57_warnings.simplefilter('ignore')
                    for entry, payload in modified.items():
                        archive.writestr(entry, payload)
                    if kind == 'duplicate_zip':
                        archive.writestr(name, modified[name])
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    _i57_mosaic.load_fine_mosaic(path)

    def test_manifest_resource_gate_precedes_numpy_allocation(self):
        for name in ('max_retained_bytes', 'max_working_bytes'):
            record = mutable(self.result)
            record['resources'][name] = 100
            with self.subTest(name=name), _i57_tempfile.TemporaryDirectory() as directory:
                path = _i57_Path(directory) / 'resource.npz'
                _test_surface_fine_mosaic_write_bundle(rehash(record), path)
                with _i57_patch.object(_i57_mosaic.np, 'load', side_effect=AssertionError('allocated before resource gate')):
                    with self.assertRaisesRegex(ValueError, 'resource preflight'):
                        _i57_mosaic.load_fine_mosaic(path)

    def test_coherently_rehashed_original_budget_and_source_stage_rejected(self):
        for kind in ('area', 'volume', 'depth', 'stage'):
            record = mutable(self.result)
            old_identity = record['sources'][0]['proof_sha256']
            proof = record['proofs'].pop(old_identity)
            support = record['proof_h0_support'].pop(old_identity)
            if kind == 'stage':
                wet = proof['surface']['arrays']['wet_mask']
                proof['surface']['arrays']['water_surface_m'][wet] += 0.01
            else:
                name = {'area': 'max_area_m2', 'volume': 'max_cut_volume_m3', 'depth': 'max_bed_cut_m'}[kind]
                proof['inputs']['budget'][name] = 0.0
                proof['surface']['identity']['parameters'][name] = 0.0
            rehash_surface(proof)
            new_identity = proof['identity_sha256']
            record['proofs'][new_identity], record['proof_h0_support'][new_identity] = (proof, support)
            record['sources'][0]['proof_sha256'] = new_identity
            with self.subTest(kind=kind), _i57_tempfile.TemporaryDirectory() as directory:
                path = _i57_Path(directory) / 'coherent.npz'
                _test_surface_fine_mosaic_write_bundle(rehash(record), path)
                with self.assertRaises(ValueError):
                    _i57_mosaic.load_fine_mosaic(path)
SAVED_DOMAIN_PATH = ROOT / 'verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz'
SAVED_DOMAIN_SHA256 = 'dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af'

def source_binding():
    from terrain_pipeline.surface_domain import recover_surface_network as _i55_recover_surface_network
    proof = _i55_recover_surface_network(**recovery_case())
    if not proof['accepted']:
        raise AssertionError('engineering source recovery not accepted')
    return _i55_adapter.bind_surface_dynamic_source(proof, vertical_datum='engineering-relative-sea-zero')

def forcing(binding, steps=80, pulse=False, raised=False):
    count = len(binding['node_flat_ids'])
    local = _i55_np.zeros((steps, count))
    if pulse:
        local[:10, 0] = 1.0
    tailwater = _i55_np.tile(binding['initial_stage_m'][binding['boundary_mask']], (steps + 1, 1))
    if raised:
        tailwater[1:] += 0.5
    return {'conductance_m2_s': _i55_np.full(len(binding['edges']), 2.0), 'local_q_m3_s': local, 'tailwater_m': tailwater, 'dt_s': 1.0, 'max_depth_m': 4.0}

def _test_surface_dynamic_prepare_rehash(record):
    record.pop('identity_sha256', None)
    record['identity_sha256'] = _i55_mosaic._identity(record)
    return record

def rewrite_dynamic(record):
    dynamic = record['dynamic']
    dynamic['identity_sha256'] = _i55_hydraulics.fingerprint(_i55_adapter._unpack_dynamic(dynamic))
    return _test_surface_dynamic_prepare_rehash(record)

def rewrite_binding(record):
    _test_surface_dynamic_prepare_rehash(record['binding'])
    record['dynamic']['inputs']['source'] = record['binding']['identity_sha256']
    return rewrite_dynamic(record)

def write_bundle(result, path):
    arrays = {}
    tree = _i55_mosaic._surface_fine_mosaic_tree(result, arrays)
    manifest = {'format_version': 1, 'tree': tree, 'tree_sha256': _i55_mosaic._identity(tree)}
    with _i55_zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', _i55_mosaic._surface_fine_mosaic_json(manifest))
        for name, array in arrays.items():
            with _i55_io.BytesIO() as stream:
                _i55_np.save(stream, _i55_np.ascontiguousarray(array), allow_pickle=False)
                archive.writestr(name, stream.getvalue())

def generation_disabled(stack):
    for target in ('terrain_pipeline.surface_domain.bind_surface_dynamic_source', 'terrain_pipeline.surface_domain.prepare_surface_dynamic', 'terrain_pipeline.surface_domain._source_mosaic', 'terrain_pipeline.surface_hydraulics.evaluate', 'terrain_pipeline.surface_domain.recover_surface_network', 'terrain_pipeline.surface_domain._replay', 'terrain_pipeline.surface_domain.evaluate_surface_domains', 'terrain_pipeline.surface_domain.prepare_surface_network', 'terrain_pipeline.surface_domain._fine_source', 'terrain_pipeline.surface_domain.prepare_fine_mosaic', 'terrain_pipeline.surface_domain._h0_support', 'terrain_pipeline.surface_domain._surface_fine_mosaic_stencil', 'terrain_pipeline.surface_domain._surface_fine_mosaic_assemble', 'terrain_pipeline.surface_domain._mesh', 'terrain_pipeline.surface_domain._surface_fine_mosaic_grid', 'terrain_pipeline.surface_domain._ownership', 'terrain_pipeline.surface_domain._proof_gate'):
        stack.enter_context(_i55_patch(target, side_effect=AssertionError('static read generated: ' + target)))

class SurfaceDynamicPrepareTests(_i55_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.binding = source_binding()
        cls.pulse = _i55_adapter.prepare_surface_dynamic(cls.binding, **forcing(cls.binding, pulse=True))
        cls.raised = _i55_adapter.prepare_surface_dynamic(cls.binding, **forcing(cls.binding, raised=True))

    def test_actual_source_cells_unique_area_graph_bed_stage(self):
        binding = self.binding
        self.assertEqual(binding['node_flat_ids'].tolist(), [9, 10, 11, 16, 17, 24, 31, 38, 45])
        _i55_np.testing.assert_array_equal(binding['area_m2'], [33.0, 57.0, 48.0, 72.0, 135.0, 185.0, 200.0, 130.0, 20.0])
        _i55_np.testing.assert_array_equal(binding['edges'], [[0, 3], [1, 4], [2, 1], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8]])
        self.assertEqual(len(set(binding['wet_cell_ids'].tolist())), 880)
        self.assertEqual(float(binding['area_m2'].sum()), 880.0)
        self.assertEqual(float(binding['area_m2'][~binding['boundary_mask']].sum()), 860.0)
        source = binding['source_mosaic']
        _i55_np.testing.assert_array_equal(binding['bed_m'], source['nodes']['h2_m'][binding['fine_node_ids']])
        _i55_np.testing.assert_array_equal(binding['initial_stage_m'], source['nodes']['water_surface_m'][binding['fine_node_ids']])
        self.assertFalse(binding['full_dynamic_wave_prepared'])

    def test_pulse_propagates_delayed_and_qv_closes(self):
        dynamic = self.pulse['dynamic']
        edges = self.binding['edges']
        pulse_edge = int(_i55_np.flatnonzero(edges[:, 0] == 0)[0])
        downstream = int(edges[pulse_edge, 1])
        terminal_edge = int(_i55_np.flatnonzero(self.binding['boundary_mask'][edges[:, 1]])[0])
        last_internal = int(edges[terminal_edge, 0])
        self.assertEqual(dynamic['status'], 'completed')
        self.assertGreater(dynamic['stage_m'][1, 0], dynamic['stage_m'][0, 0])
        self.assertEqual(dynamic['stage_m'][1, downstream], dynamic['stage_m'][0, downstream])
        self.assertGreater(dynamic['stage_m'][2, downstream], dynamic['stage_m'][1, downstream])
        self.assertEqual(dynamic['qedges_m3_s'][0, pulse_edge], 0.0)
        self.assertGreater(dynamic['qedges_m3_s'][1, pulse_edge], 0.0)
        self.assertGreater(dynamic['stage_m'][-1, last_internal], dynamic['stage_m'][0, last_internal])
        ledger = dynamic['ledger_m3']
        self.assertAlmostEqual(float(ledger[:, 1].sum()), 10.0)
        self.assertLess(float(_i55_np.abs(ledger[:, 5]).max()), 1e-10)
        self.assertAlmostEqual(float(dynamic['storage_m3'][-1].sum() - dynamic['storage_m3'][0].sum()), float(ledger[:, 1:3].sum()), places=9)

    def test_tailwater_raise_reverses_flow_then_upstream_responds(self):
        dynamic = self.raised['dynamic']
        edges = self.binding['edges']
        terminal_edge = int(_i55_np.flatnonzero(self.binding['boundary_mask'][edges[:, 1]])[0])
        last_internal = int(edges[terminal_edge, 0])
        self.assertEqual(dynamic['status'], 'completed')
        self.assertTrue(_i55_np.all(dynamic['qedges_m3_s'][0] == 0))
        self.assertEqual(dynamic['stage_m'][1, last_internal], dynamic['stage_m'][0, last_internal])
        self.assertLess(dynamic['qedges_m3_s'][1, terminal_edge], 0.0)
        self.assertGreater(dynamic['stage_m'][2, last_internal], dynamic['stage_m'][1, last_internal])
        self.assertGreater(dynamic['stage_m'][-1, 0], dynamic['stage_m'][0, 0])
        self.assertGreater(float(dynamic['ledger_m3'][:, 2].sum()), 0.0)

    def test_real_prepared_old_domain_source_without_filling_gap(self):
        from terrain_pipeline.surface_domain import evaluate_surface_domains as _i55_evaluate_surface_domains
        from terrain_pipeline.surface_domain import plan_surface_domains as _i55_plan_surface_domains
        candidate = _i55_plan_surface_domains(**complete_two_domain_inputs())
        prepared = _i55_evaluate_surface_domains(candidate, fine_configurations(candidate))
        binding = _i55_adapter.bind_surface_dynamic_source(prepared, domain_id=1, vertical_datum=candidate['inputs']['vertical_datum'])
        self.assertEqual(binding['source_mosaic']['sources'][0]['domain_id'], 1)
        self.assertFalse(binding['source_mosaic']['full_domain_mosaic_prepared'])
        result = _i55_adapter.prepare_surface_dynamic(binding, **forcing(binding, steps=3))
        self.assertEqual(result['status'], 'completed')
        with self.assertRaisesRegex(ValueError, 'select exactly one'):
            _i55_adapter.bind_surface_dynamic_source(prepared, vertical_datum=candidate['inputs']['vertical_datum'])

    def test_actual_saved_prepared_domain_fixed_positive(self):
        from terrain_pipeline.surface_domain import load_surface_domains as _i55_load_surface_domains
        import hashlib
        self.assertEqual(hashlib.sha256(SAVED_DOMAIN_PATH.read_bytes()).hexdigest(), SAVED_DOMAIN_SHA256)
        source = _i55_load_surface_domains(SAVED_DOMAIN_PATH)
        binding = _i55_adapter.bind_surface_dynamic_source(source, domain_id=1, vertical_datum=source['candidate']['inputs']['vertical_datum'])
        _i55_np.testing.assert_array_equal(binding['node_flat_ids'], [9, 11, 16, 17, 23, 30, 37, 45])
        _i55_np.testing.assert_array_equal(binding['area_m2'], [22.0, 40.0, 48.0, 84.0, 55.0, 40.0, 33.0, 16.0])
        params = forcing(binding, steps=5)
        params['conductance_m2_s'][:] = 0.01
        params['dt_s'] = 0.1
        params['local_q_m3_s'][:, 0] = 0.1
        result = _i55_adapter.prepare_surface_dynamic(binding, **params)
        self.assertEqual(result['status'], 'completed')
        self.assertAlmostEqual(float(result['dynamic']['storage_m3'][0].sum()), 161.0)
        self.assertEqual(len(binding['wet_cell_ids']), 338)
        self.assertEqual(float(binding['area_m2'][binding['boundary_mask']].sum()), 16.0)

    def test_plain_or_unaccepted_source_rejected(self):
        with self.assertRaises(ValueError):
            _i55_adapter.bind_surface_dynamic_source({'status': 'prepared'}, vertical_datum='engineering-zero')
        proof = mutable(next(iter(self.binding['source_mosaic']['proofs'].values())))
        proof['accepted'] = False
        with self.assertRaises(ValueError):
            _i55_adapter.bind_surface_dynamic_source(proof, vertical_datum='engineering-zero')

    def test_source_domain_fine_dataclass_supported(self):
        proof = next(iter(self.binding['source_mosaic']['proofs'].values()))
        source = _i55_mosaic.DomainFineSource(proof, 7)
        binding = _i55_adapter.bind_surface_dynamic_source(source, vertical_datum='engineering-relative-sea-zero')
        self.assertEqual(binding['source_mosaic']['sources'][0]['domain_id'], 7)

    def test_A0_rejected_and_nearest_tie_cannot_reassign(self):
        proof = next(iter(self.binding['source_mosaic']['proofs'].values()))
        with _i55_patch.object(_i55_np, 'argmin', return_value=0):
            with self.assertRaisesRegex(ValueError, 'A0'):
                _i55_adapter.bind_surface_dynamic_source(proof, vertical_datum='engineering-relative-sea-zero')
        record = mutable(self.pulse)
        record['binding']['area_m2'][0] = 0.0
        rewrite_binding(record)
        with self.assertRaises(ValueError):
            _i55_adapter.validate_surface_dynamic(record)

    def test_explicit_boundary_q_tailwater_and_k_gates(self):
        for kind in ('boundary_q', 'initial_tailwater', 'bad_k', 'bad_local_shape', 'bad_tailwater_shape', 'unstable'):
            params = forcing(self.binding, steps=3)
            if kind == 'boundary_q':
                params['local_q_m3_s'][0, -1] = 1.0
            elif kind == 'initial_tailwater':
                params['tailwater_m'][0, 0] += 0.1
            elif kind == 'bad_k':
                params['conductance_m2_s'][0] = 0.0
            elif kind == 'bad_local_shape':
                params['local_q_m3_s'] = _i55_np.zeros((3, 2))
            elif kind == 'bad_tailwater_shape':
                params['tailwater_m'] = _i55_np.zeros((3, 1))
            else:
                params['dt_s'] = 1000.0
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _i55_adapter.prepare_surface_dynamic(self.binding, **params)

    def test_cancellation_and_failure_keep_only_committed_prefix(self):
        cancelled = _i55_adapter.prepare_surface_dynamic(self.binding, **forcing(self.binding, steps=3), cancel=lambda: True)
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertEqual(cancelled['dynamic']['committed_steps'], 0)
        params = forcing(self.binding, steps=4)
        params['tailwater_m'][2:, 0] = 100.0
        failed = _i55_adapter.prepare_surface_dynamic(self.binding, **params)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['dynamic']['committed_steps'], 1)
        self.assertTrue(_i55_adapter.validate_surface_dynamic(failed))

    def test_load_query_no_generation_readonly(self):
        with _i55_tempfile.TemporaryDirectory() as directory:
            path = _i55_Path(directory) / 'pulse.npz'
            _i55_adapter.save_surface_dynamic(self.pulse, path)
            with _i55_ExitStack() as stack:
                generation_disabled(stack)
                loaded = _i55_adapter.load_surface_dynamic(path)
                queried = _i55_adapter.query_surface_dynamic(loaded, state_index=2)
            self.assertEqual(loaded['identity_sha256'], self.pulse['identity_sha256'])
            with self.assertRaises(ValueError):
                queried['stage_m'].flags.writeable = True
            with self.assertRaises(TypeError):
                loaded['status'] = 'completed'
            with self.assertRaises(ValueError):
                _i55_adapter.query_surface_dynamic(loaded, state_index=1000)

    def test_coherently_rehashed_area_owner_duplicate_cell_and_bed_rejected(self):
        for kind in ('area', 'owner', 'duplicate', 'bed', 'stage', 'edge', 'fine_node'):
            record = mutable(self.pulse)
            binding = record['binding']
            if kind == 'area':
                binding['area_m2'][0] += 1.0
            elif kind == 'owner':
                binding['wet_cell_owner'][0] = (binding['wet_cell_owner'][0] + 1) % len(binding['area_m2'])
                binding['area_m2'] = _i55_np.bincount(binding['wet_cell_owner'], minlength=len(binding['area_m2'])).astype(float)
            elif kind == 'duplicate':
                binding['wet_cell_ids'][1] = binding['wet_cell_ids'][0]
            elif kind == 'bed':
                binding['bed_m'][0] -= 0.01
            elif kind == 'stage':
                binding['initial_stage_m'][0] += 0.01
            elif kind == 'edge':
                binding['edges'][0, 1] = (binding['edges'][0, 1] + 1) % len(binding['area_m2'])
            else:
                binding['fine_node_ids'][0] += 1
            rewrite_binding(record)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _i55_adapter.validate_surface_dynamic(record)

    def test_rehashed_unknown_protection_and_source_stage_rejected(self):
        for kind in ('unknown', 'protection', 'source_stage', 'coarse_support'):
            record = mutable(self.pulse)
            binding = record['binding']
            source = binding['source_mosaic']
            source_node = int(binding['fine_node_ids'][0])
            fine_shape = next(iter(source['proofs'].values()))['inputs']['fine']['shape_zx']
            row, column = divmod(source_node, fine_shape[1])
            if kind in ('unknown', 'protection'):
                name = 'unknown_mask' if kind == 'unknown' else 'protected_mask'
                source['sources'][0][name][row, column] = True
            elif kind == 'coarse_support':
                next(iter(source['proof_h0_support'].values()))['weights'][0] = [0.5, 0.5, 0.0, 0.0]
            else:
                old_identity = binding['source_proof_sha256']
                proof = source['proofs'].pop(old_identity)
                proof['surface']['arrays']['water_surface_m'][row, column] += 0.01
                rehash_surface(proof)
                new_identity = proof['identity_sha256']
                source['proofs'][new_identity] = proof
                source['proof_h0_support'][new_identity] = source['proof_h0_support'].pop(old_identity)
                source['sources'][0]['proof_sha256'] = new_identity
                binding['source_proof_sha256'] = new_identity
            _test_surface_dynamic_prepare_rehash(source)
            rewrite_binding(record)
            with self.subTest(kind=kind), _i55_tempfile.TemporaryDirectory() as directory:
                path = _i55_Path(directory) / 'source-tampered.npz'
                write_bundle(record, path)
                with self.assertRaises(ValueError):
                    _i55_adapter.load_surface_dynamic(path)

    def test_dynamic_rehashed_stage_storage_flux_ledger_rejected(self):
        for name in ('stage_m', 'storage_m3', 'qedges_m3_s', 'ledger_m3'):
            record = mutable(self.pulse)
            record['dynamic'][name][1, 0] += 0.01
            rewrite_dynamic(record)
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i55_adapter.validate_surface_dynamic(record)

    def test_resources_preflight_before_generation_or_payload_allocation(self):
        proof = next(iter(self.binding['source_mosaic']['proofs'].values()))
        with _i55_patch.object(_i55_adapter, '_source_mosaic', side_effect=AssertionError('source generation before cap')):
            with self.assertRaisesRegex(ValueError, 'resource preflight'):
                _i55_adapter.bind_surface_dynamic_source(proof, vertical_datum='zero', resources=_i55_adapter.DynamicPrepareResources(max_retained_bytes=100))
        record = mutable(self.pulse)
        record['resources']['max_working_bytes'] = 100
        record['binding']['resources']['max_working_bytes'] = 100
        rewrite_binding(record)
        with _i55_tempfile.TemporaryDirectory() as directory:
            path = _i55_Path(directory) / 'resource.npz'
            write_bundle(record, path)
            with _i55_patch.object(_i55_np, 'load', side_effect=AssertionError('allocated before preflight')):
                with self.assertRaisesRegex(ValueError, 'resource preflight'):
                    _i55_adapter.load_surface_dynamic(path)

    def test_archive_payload_and_duplicate_json_rejected(self):
        with _i55_tempfile.TemporaryDirectory() as directory:
            path = _i55_Path(directory) / 'good.npz'
            _i55_adapter.save_surface_dynamic(self.pulse, path)
            with _i55_zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for kind in ('truncated', 'trailing', 'header', 'json', 'duplicate'):
                changed = dict(members)
                array_name = next((name for name in changed if name.endswith('.npy')))
                if kind == 'truncated':
                    changed[array_name] = changed[array_name][:-1]
                elif kind == 'trailing':
                    changed[array_name] += b'trailing'
                elif kind == 'header':
                    changed[array_name] = b'\x93NUMPY\x01\x00\xff\xff' + b' ' * 65535
                elif kind == 'json':
                    changed['manifest.json'] = changed['manifest.json'].replace(b'{', b'{"format_version":1,', 1)
                target = _i55_Path(directory) / (kind + '.npz')
                with _i55_warnings.catch_warnings(), _i55_zipfile.ZipFile(target, 'w') as archive:
                    _i55_warnings.simplefilter('ignore')
                    for name, payload in changed.items():
                        archive.writestr(name, payload)
                    if kind == 'duplicate':
                        archive.writestr(array_name, changed[array_name])
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    _i55_adapter.load_surface_dynamic(target)

    def test_save_nooverwrite_atomic_cleanup(self):
        with _i55_tempfile.TemporaryDirectory() as directory:
            path = _i55_Path(directory) / 'good.npz'
            _i55_adapter.save_surface_dynamic(self.pulse, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                _i55_adapter.save_surface_dynamic(self.pulse, path)
            self.assertEqual(path.read_bytes(), before)
            failed = _i55_Path(directory) / 'failed.npz'
            with _i55_patch.object(_i55_os, 'link', side_effect=OSError('failed publish')):
                with self.assertRaises(OSError):
                    _i55_adapter.save_surface_dynamic(self.pulse, failed)
            self.assertFalse(failed.exists())
            self.assertEqual(list(_i55_Path(directory).glob('*.tmp')), [])

def _test_surface_multidomain_dynamic_forcing(steps=8, pulse=False, raised=False):
    local = _i59_np.zeros((steps, 16))
    if pulse:
        local[0, 0] = 1.0
        local[0, 8] = 2.0
    tailwater = _i59_np.full((steps + 1, 2), 4.2)
    if raised:
        tailwater[1:, 1] = 5.1
    return dict(conductance_m2_s=_i59_np.full(14, 0.01), local_q_m3_s=local, tailwater_m=tailwater, dt_s=0.1, max_depth_m=4.0)

def propagation_forcing(raised=False):
    values = _test_surface_multidomain_dynamic_forcing(steps=80, pulse=True, raised=raised)
    values['conductance_m2_s'][:] = 1.0
    values['dt_s'] = 1.0
    return values

def _test_surface_multidomain_dynamic_mutable(record):
    from terrain_pipeline.surface_identity import _plain as _i59__merged_mosaic__plain
    return _i59_deepcopy(_i59__merged_mosaic__plain(record))

def write_archive(record, path):
    arrays = {}
    tree = _i59_mosaic._surface_fine_mosaic_tree(record, arrays)
    with _i59_zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', _i59_mosaic._surface_fine_mosaic_json({'format_version': 1, 'tree': tree, 'tree_sha256': _i59_mosaic._identity(tree)}))
        for name, array in arrays.items():
            stream = _i59_io.BytesIO()
            _i59_np.save(stream, array, allow_pickle=False)
            archive.writestr(name, stream.getvalue())

class SurfaceMultidomainDynamicTests(_i59_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.surface_domain import load_surface_domains as _i59_load_surface_domains
        cls.evaluation = _i59_load_surface_domains(SAVED_DOMAIN_PATH)

    def result(self, **overrides):
        values = _test_surface_multidomain_dynamic_forcing()
        values.update(overrides)
        return _i59_forest.prepare_surface_multidomain_dynamic(self.evaluation, **values)

    def test_complete_forest_and_independent_qv(self):
        result = self.result(**_test_surface_multidomain_dynamic_forcing(pulse=True))
        self.assertEqual(result['dynamic']['status'], 'completed')
        self.assertEqual(result['node_keys'].tolist(), [[domain, flat] for domain in (1, 2) for flat in (9, 11, 16, 17, 23, 30, 37, 45)])
        self.assertEqual(result['node_offsets'].tolist(), [0, 8, 16])
        self.assertEqual(result['edge_offsets'].tolist(), [0, 7, 14])
        self.assertEqual(sum((len(item['wet_cell_ids']) for item in result['bindings'])), 676)
        _i59_np.testing.assert_array_equal(result['dynamic']['storage_m3'][0, [7, 15]], 0)
        _i59_np.testing.assert_allclose(result['dynamic']['storage_m3'][0].sum(), 322)
        for step in range(result['dynamic']['committed_steps']):
            for index, start in enumerate((0, 8)):
                edge_start = index * 7
                edges = result['edges'][edge_start:edge_start + 7]
                before = result['dynamic']['stage_m'][step]
                flux = 0.01 * (before[edges[:, 0]] - before[edges[:, 1]])
                _i59_np.testing.assert_allclose(flux, result['dynamic']['qedges_m3_s'][step, edge_start:edge_start + 7])
                net = _i59_np.zeros(8)
                _i59_np.add.at(net, edges[:, 0] - start, -flux)
                _i59_np.add.at(net, edges[:, 1] - start, flux)
                before_storage = result['dynamic']['storage_m3'][step, start:start + 8]
                after_storage = result['dynamic']['storage_m3'][step + 1, start:start + 8]
                local = result['dynamic']['inputs']['local_q_m3_s'][step, start:start + 8]
                _i59_np.testing.assert_allclose(after_storage[:7], before_storage[:7] + 0.1 * (local[:7] + net[:7]), atol=1e-12)
                self.assertEqual(after_storage[7], 0)
                ledger = result['domain_ledger_m3'][step, index]
                _i59_np.testing.assert_allclose(ledger[:3], [before_storage.sum(), 0.1 * local[:7].sum(), -0.1 * net[7]], atol=1e-12)
            _i59_np.testing.assert_allclose(result['domain_ledger_m3'][step].sum(axis=0), result['dynamic']['ledger_m3'][step], atol=1e-12)

    def test_raised_tailwater_only_affects_second_domain(self):
        base = self.result(**_test_surface_multidomain_dynamic_forcing())
        raised = self.result(**_test_surface_multidomain_dynamic_forcing(raised=True))
        _i59_np.testing.assert_array_equal(base['dynamic']['stage_m'][:, :8], raised['dynamic']['stage_m'][:, :8])
        _i59_np.testing.assert_array_equal(base['dynamic']['qedges_m3_s'][:, :7], raised['dynamic']['qedges_m3_s'][:, :7])
        self.assertTrue(_i59_np.any(raised['dynamic']['qedges_m3_s'][:, 7:] < 0))

    def test_pulse_propagates_independently(self):
        base = self.result(**propagation_forcing())
        raised = self.result(**propagation_forcing(raised=True))
        _i59_np.testing.assert_array_equal(base['dynamic']['stage_m'][:, :8], raised['dynamic']['stage_m'][:, :8])
        _i59_np.testing.assert_array_equal(base['dynamic']['qedges_m3_s'][:, :7], raised['dynamic']['qedges_m3_s'][:, :7])
        self.assertGreater(abs(base['dynamic']['stage_m'][-1, 6] - self.result(**{**propagation_forcing(), 'local_q_m3_s': _i59_np.zeros((80, 16))})['dynamic']['stage_m'][-1, 6]), 1e-08)
        self.assertTrue(_i59_np.any(raised['dynamic']['qedges_m3_s'][:, 7:] < 0))

    def test_static_reload_and_no_overwrite(self):
        result = self.result()
        with _i59_tempfile.TemporaryDirectory() as directory:
            path = _i59_Path(directory) / 'forest.npz'
            _i59_forest.save_surface_multidomain_dynamic(result, path)
            with self.assertRaises(FileExistsError):
                _i59_forest.save_surface_multidomain_dynamic(result, path)
            with _i59_ExitStack() as stack:
                generation_disabled(stack)
                stack.enter_context(_i59_patch('terrain_pipeline.surface_domain.prepare_surface_multidomain_dynamic', side_effect=AssertionError('static read prepared')))
                stack.enter_context(_i59_patch('terrain_pipeline.surface_domain._input', side_effect=AssertionError('static read rebuilt inputs')))
                loaded = _i59_forest.load_surface_multidomain_dynamic(path)
                query = _i59_forest.query_surface_multidomain_dynamic(loaded, state_index=2)
            self.assertEqual(query['time_s'], 0.2)
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])

    def test_rehashed_mapping_and_binding_tamper(self):
        result = self.result()
        mutations = (lambda item: item['node_keys'].__setitem__((8, 0), 1), lambda item: item['node_offsets'].__setitem__(1, 7), lambda item: item['edges'].__setitem__((7, 1), 0), lambda item: item['bindings'].pop(), lambda item: item['bindings'].__setitem__(1, item['bindings'][0]), lambda item: item['bindings'][0]['area_m2'].__setitem__(0, 23.0), lambda item: item['domain_ledger_m3'].__setitem__((0, 0, 1), 1.0))
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = _test_surface_multidomain_dynamic_mutable(result)
                mutation(changed)
                _test_surface_dynamic_prepare_rehash(changed)
                with self.assertRaises(ValueError):
                    _i59_forest.validate_surface_multidomain_dynamic(changed)
        changed = _test_surface_multidomain_dynamic_mutable(result)
        changed['bindings'][0]['area_m2'][0] = 23.0
        _test_surface_dynamic_prepare_rehash(changed['bindings'][0])
        _test_surface_dynamic_prepare_rehash(changed)
        with self.assertRaises(ValueError):
            _i59_forest.validate_surface_multidomain_dynamic(changed)
        changed = _test_surface_multidomain_dynamic_mutable(result)
        changed['domain_ids'][0] = 1.0
        _test_surface_dynamic_prepare_rehash(changed)
        with self.assertRaises(ValueError):
            _i59_forest.validate_surface_multidomain_dynamic(changed)

    def test_bad_input_failure_cancel_resources(self):
        values = _test_surface_multidomain_dynamic_forcing()
        values['local_q_m3_s'][0, 0] = _i59_np.nan
        with self.assertRaises(ValueError):
            self.result(**values)
        with self.assertRaises(ValueError):
            self.result(**{**_test_surface_multidomain_dynamic_forcing(), 'dt_s': 1000000.0})
        with self.assertRaises(ValueError):
            self.result(**{**_test_surface_multidomain_dynamic_forcing(), 'resources': _i59_forest.ForestResources(max_wet_cells=500)})
        cancelled = self.result(**{**_test_surface_multidomain_dynamic_forcing(), 'cancel': lambda: False})
        self.assertEqual(cancelled['dynamic']['status'], 'completed')
        calls = iter([False, False, True])
        cancelled = self.result(**{**_test_surface_multidomain_dynamic_forcing(), 'cancel': lambda: next(calls)})
        self.assertEqual(cancelled['dynamic']['status'], 'cancelled')
        self.assertEqual(cancelled['dynamic']['committed_steps'], 0)
        with self.assertRaises(InterruptedError):
            self.result(**{**_test_surface_multidomain_dynamic_forcing(), 'cancel': lambda: True})
        values = _test_surface_multidomain_dynamic_forcing()
        values['tailwater_m'][2:, :] = 100.0
        failed = self.result(**values)
        self.assertEqual(failed['dynamic']['status'], 'failed')
        self.assertEqual(failed['dynamic']['committed_steps'], 1)
        self.assertEqual(failed['domain_ledger_m3'].shape[0], 1)
        with _i59_tempfile.TemporaryDirectory() as directory:
            for name, record in (('cancelled', cancelled), ('failed', failed)):
                path = _i59_Path(directory) / (name + '.npz')
                _i59_forest.save_surface_multidomain_dynamic(record, path)
                with _i59_ExitStack() as stack:
                    generation_disabled(stack)
                    loaded = _i59_forest.load_surface_multidomain_dynamic(path)
                self.assertEqual(loaded['dynamic']['committed_steps'], record['dynamic']['committed_steps'])

    def test_atomic_publish_failure_cleans_temporary(self):
        result = self.result()
        with _i59_tempfile.TemporaryDirectory() as directory:
            path = _i59_Path(directory) / 'forest.npz'
            with _i59_patch('terrain_pipeline.surface_domain.os.link', side_effect=OSError('publish failed')):
                with self.assertRaises(OSError):
                    _i59_forest.save_surface_multidomain_dynamic(result, path)
            self.assertFalse(path.exists())
            self.assertEqual(list(_i59_Path(directory).iterdir()), [])

    def test_archive_rejects_extra_and_object_array(self):
        result = self.result()
        with _i59_tempfile.TemporaryDirectory() as directory:
            path = _i59_Path(directory) / 'tampered.npz'
            write_archive(result, path)
            with _i59_zipfile.ZipFile(path, 'a') as archive:
                archive.writestr('extra.npy', b'extra')
            with self.assertRaises(ValueError):
                _i59_forest.load_surface_multidomain_dynamic(path)
            path2 = _i59_Path(directory) / 'object.npz'
            write_archive(result, path2)
            with _i59_zipfile.ZipFile(path2) as source:
                members = [(info.filename, source.read(info)) for info in source.infolist()]
            with _i59_zipfile.ZipFile(path2, 'w') as archive:
                for name, content in members:
                    if name == 'array_00000.npy':
                        stream = _i59_io.BytesIO()
                        _i59_np.save(stream, _i59_np.array([object()]), allow_pickle=True)
                        content = stream.getvalue()
                    archive.writestr(name, content)
            with self.assertRaises(ValueError):
                _i59_forest.load_surface_multidomain_dynamic(path2)
TEST_SURFACE_ENGINEERING_PREPARE_SOURCE = ROOT / 'verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz'
SOURCE_SHA256 = 'dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af'
VARIABLE_SOURCE = ROOT / 'verification/surface-variable-storage/run-20260930T192708.659151Z/pulse.npz'
VARIABLE_SHA256 = '392ea3fad66827fa8a3acd43301627b86ca6a4a186ea9994a2d34b32322e6c63'

def outlet_inputs(prepared, domain_id):
    from terrain_pipeline.surface_domain import _payload as _i56__payload
    datum = prepared['candidate']['inputs']['vertical_datum']
    left = 38.0 if domain_id == 1 else 108.0
    section = _i56_np.column_stack((_i56_np.arange(left, left + 4), _i56_np.full(4, 70.0)))
    attachment = _i56_coast.RiverAttachment(prepared, domain_id, section, 2, datum)
    recovery = next((item['recovery'] for item in prepared['domains'] if item['domain_id'] == domain_id))
    payload = _i56__payload(recovery)
    fine = recovery['inputs']['fine']
    row = round((70.0 - fine['origin_z_m']) / fine['spacing_z_m'])
    column = round((left - fine['origin_x_m']) / fine['spacing_x_m'])
    bed_start = payload['final_surface_m'][row, column:column + 4]
    water_start = payload['water_surface_m'][row, column:column + 4]
    h0_start = payload['source_surface_m'][row, column:column + 4]
    stations = _i56_np.arange(70.0, 91.0)
    fraction = _i56_np.linspace(0.0, 1.0, len(stations))[:, None]
    bed = (1 - fraction) * bed_start + fraction * -0.5
    water = (1 - fraction) * water_start
    h0 = (1 - fraction) * h0_start + fraction * -0.25
    shape = bed.shape
    corridor = _i56_coast.EngineeringSource('corridor', 'explicit-synthetic-domain-%d-corridor' % domain_id, datum, left, 70.0, 1.0, 1.0, h0, bed, water, _i56_np.ones(shape, bool), _i56_np.zeros(shape, bool), _i56_np.zeros(shape, bool), _i56_np.ones(shape, bool), _i56_np.zeros(shape, bool), 0.0)
    sea_shape = (2, 4)
    sea = _i56_coast.EngineeringSource('sea', 'explicit-synthetic-domain-%d-sea' % domain_id, datum, left, 90.0, 1.0, 1.0, _i56_np.full(sea_shape, -0.25), _i56_np.full(sea_shape, -0.5), _i56_np.zeros(sea_shape), _i56_np.ones(sea_shape, bool), _i56_np.zeros(sea_shape, bool), _i56_np.zeros(sea_shape, bool), _i56_np.ones(sea_shape, bool), _i56_np.ones(sea_shape, bool), 0.0)
    return {'attachment': attachment, 'corridor': corridor, 'sea': sea, 'stations_z_m': stations, 'budget': _i56_coast.DropBudget(4.0, 100.0)}

@_i56_lru_cache(maxsize=1)
def constant_fixture():
    from terrain_pipeline.surface_domain import load_surface_domains as _i56_load_surface_domains
    if _i56_hashlib.sha256(TEST_SURFACE_ENGINEERING_PREPARE_SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise AssertionError('fixed accepted source changed')
    evaluation = _i56_load_surface_domains(TEST_SURFACE_ENGINEERING_PREPARE_SOURCE)
    outlets = {domain_id: outlet_inputs(evaluation, domain_id) for domain_id in (1, 2)}
    result = _i56_engineering.prepare_surface_engineering(evaluation, outlets, **_test_surface_multidomain_dynamic_forcing(steps=80, pulse=True))
    return (evaluation, outlets, result)

class SurfaceEngineeringTests(_i56_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.evaluation, cls.outlets, cls.result = constant_fixture()

    def test_full_real_entrance_and_domains(self):
        from terrain_pipeline.surface_domain import _payload as _i56__payload
        result = self.result
        self.assertEqual(list(result['domain_ids']), [1, 2])
        self.assertEqual(result['domain_mosaic']['grid']['bbox_xz_m'], (10.0, 140.0, 10.0, 70.0))
        self.assertTrue(result['declared_node_envelope_complete'])
        for name in ('physical_footprint_complete', 'natural_outlets_certified', 'full_dynamic_wave_prepared', 'ready_for_3d'):
            self.assertFalse(result[name])
        self.assertEqual(len(result['dynamic_forest']['node_keys']), 16)
        self.assertEqual(len(result['dynamic_forest']['edges']), 14)
        self.assertEqual(int(result['dynamic_forest']['dynamic']['inputs']['boundary_mask'].sum()), 2)
        for domain_id, drop in zip((1, 2), result['drops']):
            self.assertEqual(drop['inputs']['attachment']['domain_id'], domain_id)
            self.assertAlmostEqual(drop['attachment']['terminal_q_m3_s'], 0.200049)
            _i56_np.testing.assert_allclose(drop['attachment']['river_water_xyz_m'][:, 1], _i56__payload(next((item['recovery'] for item in self.evaluation['domains'] if item['domain_id'] == domain_id)))['water_surface_m'][-1, 28:32])
        self.assertEqual(self.result['drops'][1]['attachment']['terminal_node'], self.result['drops'][0]['attachment']['terminal_node'])

    def test_missing_duplicate_mixed_and_wrong_outlet_rejected(self):
        with self.assertRaises(ValueError):
            _i56_engineering.prepare_surface_engineering(self.evaluation, {1: self.outlets[1]}, **_test_surface_multidomain_dynamic_forcing())
        with self.assertRaises(ValueError):
            _i56_engineering.compose_surface_engineering(self.evaluation, self.result['domain_mosaic'], [self.result['drops'][0]] * 2, self.result['dynamic_forest'])
        bad = dict(self.outlets)
        bad[2] = {**bad[2], 'attachment': self.outlets[1]['attachment']}
        with self.assertRaises(ValueError):
            _i56_engineering.prepare_surface_engineering(self.evaluation, bad, **_test_surface_multidomain_dynamic_forcing())
        for change in ('datum', 'sea', 'budget'):
            supplied = dict(self.outlets[2])
            if change == 'datum':
                supplied['sea'] = _i56_replace(supplied['sea'], datum='wrong')
            elif change == 'sea':
                supplied['sea'] = _i56_replace(supplied['sea'], sea_level_m=5.0, water_m=_i56_np.full((2, 4), 5.0))
            else:
                supplied['budget'] = _i56_coast.DropBudget(0.0, 0.0)
            with self.subTest(change=change), self.assertRaises(ValueError):
                _i56_engineering.prepare_surface_engineering(self.evaluation, {1: self.outlets[1], 2: supplied}, **_test_surface_multidomain_dynamic_forcing())

    def test_static_roundtrip_and_atomic_nooverwrite(self):
        with _i56_tempfile.TemporaryDirectory() as directory:
            path = _i56_Path(directory) / 'engineering.npz'
            _i56_engineering.save_surface_engineering(self.result, path)
            before = _i56_hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                _i56_engineering.save_surface_engineering(self.result, path)
            self.assertEqual(_i56_hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with _i56_patch.object(_i56_engineering, 'prepare_surface_engineering', side_effect=AssertionError('prepared')), _i56_patch.object(_i56_mosaic, 'prepare_domain_mosaic', side_effect=AssertionError('mosaic')), _i56_patch.object(_i56_coast, 'prepare_coast_drop', side_effect=AssertionError('drop')), _i56_patch.object(_i56_forest, 'prepare_surface_multidomain_dynamic', side_effect=AssertionError('advanced')), _i56_ExitStack() as stack:
                for target in ('terrain_pipeline.surface_domain.recover_surface_network', 'terrain_pipeline.surface_domain._replay', 'terrain_pipeline.surface_domain._fine_source', 'terrain_pipeline.surface_domain.evaluate_surface_domains', 'terrain_pipeline.surface_domain.bind_surface_dynamic_source', 'terrain_pipeline.surface_hydraulics.evaluate'):
                    stack.enter_context(_i56_patch(target, side_effect=AssertionError('generation')))
                for name in ('_assemble',):
                    stack.enter_context(_i56_patch.object(_i56_mosaic, name, side_effect=AssertionError('assembled')))
                for name in ('_attachment', '_sample', '_stencil'):
                    stack.enter_context(_i56_patch.object(_i56_coast, name, side_effect=AssertionError('sampled')))
                loaded = _i56_engineering.load_surface_engineering(path)
                queried = _i56_engineering.query_surface_engineering(loaded)
            self.assertEqual(loaded['identity_sha256'], self.result['identity_sha256'])
            self.assertEqual(len(queried['outlets']), 2)
            with self.assertRaises(ValueError):
                loaded['drops'][0]['arrays']['bed_xyz_m'].setflags(write=True)
            self.assertEqual(queried['node_graph']['edges'].shape, (14, 2))
            self.assertEqual(queried['surface_geometry']['triangles'].shape, (15600, 3))
            self.assertEqual(queried['dynamic']['stage_m'].shape, (81, 16))

    def test_strict_selectors_and_resources(self):
        for value in (True, 1.0, -1, 81):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _i56_engineering.query_surface_engineering(self.result, state_index=value)
        with self.assertRaises(ValueError):
            _i56_engineering.query_surface_engineering(self.result, variable_state_index=0)
        for value in (True, 1024.0):
            with self.assertRaises(ValueError):
                _i56_engineering.EngineeringResources(max_retained_bytes=value)

    def test_generated_resource_rejected_before_prepare(self):
        input_size = _i56_engineering._size({'evaluation': self.evaluation})
        with _i56_patch.object(_i56_mosaic, 'prepare_domain_mosaic', side_effect=AssertionError('allocated')), self.assertRaises(ValueError):
            _i56_engineering.prepare_surface_engineering(self.evaluation, self.outlets, resources=_i56_engineering.EngineeringResources(max_retained_bytes=input_size * 5), **_test_surface_multidomain_dynamic_forcing())

    def test_archive_preflight_rejects_before_array_load(self):
        with _i56_tempfile.TemporaryDirectory() as directory:
            original = _i56_Path(directory) / 'original.npz'
            _i56_engineering.save_surface_engineering(self.result, original)
            for mode in ('duplicate', 'compressed', 'object', 'shape', 'bool-shape'):
                path = _i56_Path(directory) / (mode + '.npz')
                with _i56_zipfile.ZipFile(original) as source, _i56_zipfile.ZipFile(path, 'w') as target:
                    metadata = _i56_json.loads(source.read('metadata.json'))

                    def reference(value):
                        if isinstance(value, dict):
                            if '$array' in value:
                                return value
                            for child in value.values():
                                found = reference(child)
                                if found is not None:
                                    return found
                        elif isinstance(value, list):
                            for child in value:
                                found = reference(child)
                                if found is not None:
                                    return found
                        return None
                    spec = reference(metadata['tree'])
                    if mode == 'shape':
                        spec['shape'] = [1000001]
                    elif mode == 'bool-shape':
                        spec['shape'] = [True]
                    elif mode == 'object':
                        spec['dtype'] = '|O'
                    target.writestr('metadata.json', _i56_json.dumps(metadata), compress_type=_i56_zipfile.ZIP_DEFLATED if mode == 'compressed' else _i56_zipfile.ZIP_STORED)
                    for name in source.namelist():
                        if name != 'metadata.json':
                            target.writestr(name, source.read(name))
                    if mode == 'duplicate':
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter('ignore', UserWarning)
                            target.writestr('metadata.json', '{}')
                with self.subTest(mode=mode), _i56_patch.object(_i56_np, 'load', side_effect=AssertionError('allocated')), self.assertRaises(ValueError):
                    _i56_engineering.load_surface_engineering(path)

    def test_strict_npy_headers_before_load(self):
        headers = ["{'descr':'<f8','fortran_order':False,'shape':(1.0,)}", "{'descr':'<f8','fortran_order':False,'shape':(True,)}", "{'descr':'<f8','fortran_order':0,'shape':(1,)}", "{'descr':'<f8','fortran_order':False,'shape':(1,),'shape':(1,)}"]
        with _i56_tempfile.TemporaryDirectory() as directory:
            for index, header in enumerate(headers):
                path = _i56_Path(directory) / (str(index) + '.npz')
                raw = header.encode('latin1') + b'\n'
                payload = b'\x93NUMPY\x01\x00' + len(raw).to_bytes(2, 'little') + raw + b'\x00' * 8
                spec = {'$array': 'array_0.npy', 'shape': [1], 'dtype': '<f8', 'sha256': '0' * 64}
                with _i56_zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('metadata.json', _i56_json.dumps({'format': _i56_engineering.SURFACE_ENGINEERING_PREPARE_VERSION + '-npy-v1', 'tree': {'resources': {}, 'array': spec}}))
                    archive.writestr('array_0.npy', payload)
                with self.subTest(header=header), _i56_patch.object(_i56_np, 'load', side_effect=AssertionError('allocated')), self.assertRaises(ValueError):
                    _i56_engineering.load_surface_engineering(path)

    def test_coherent_nested_outlet_forgery_rejected(self):
        from terrain_pipeline.surface_identity import _plain as _i56__merged_coast__plain
        from terrain_pipeline.surface_identity import _freeze as _i56__merged_coast__freeze
        for field, value in (('terminal_q_m3_s', 0.4), ('terminal_node', 45.0), ('terminal_node', True)):
            plain = _i56_deepcopy(_i56__merged_coast__plain(self.result))
            drop = plain['drops'][1]
            drop['attachment'][field] = value
            drop['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in drop.items() if key != 'identity_sha256'})
            plain['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in plain.items() if key != 'identity_sha256'})
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                _i56_engineering.validate_surface_engineering(_i56__merged_coast__freeze(plain))

    def test_static_saved_mosaic_coherent_forgery_rejected(self):
        from terrain_pipeline.surface_identity import _plain as _i56__merged_coast__plain
        from terrain_pipeline.surface_identity import _freeze as _i56__merged_coast__freeze
        static_disabled = static_disabled
        for field in ('h0_m', 'h2_m', 'weights', 'summary'):
            plain = _i56_deepcopy(_i56__merged_coast__plain(self.result))
            mesh = plain['domain_mosaic']
            if field in ('h0_m', 'h2_m'):
                mesh['nodes'][field][0] += 0.25
            elif field == 'weights':
                mesh['contributors']['weights'][0, 0, 0] += 0.25
            else:
                mesh['summary']['actual_wet_water_volume_m3'] += 1.0
            mesh['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in mesh.items() if key != 'identity_sha256'})
            plain['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in plain.items() if key != 'identity_sha256'})
            with self.subTest(field=field), _i56_ExitStack() as stack:
                static_disabled(stack)
                with self.assertRaises(ValueError):
                    _i56_engineering.validate_surface_engineering(_i56__merged_coast__freeze(plain))

    def test_frozen_bundle_static_full_generation_guard(self):
        static_disabled = static_disabled
        frozen = ROOT / 'verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz'
        before = _i56_hashlib.sha256(frozen.read_bytes()).hexdigest()
        with _i56_ExitStack() as stack:
            static_disabled(stack)
            stack.enter_context(_i56_patch.object(_i56_mosaic, '_assemble', side_effect=AssertionError('assembly')))
            loaded = _i56_engineering.load_surface_engineering(frozen)
            query = _i56_engineering.query_surface_engineering(loaded)
        self.assertEqual(loaded['identity_sha256'], '381e60743e03cee6859c5cce46cb6337c8ea601ed5eb4cc1258e18cf51092860')
        self.assertEqual(query['node_graph']['edges'].shape, (14, 2))
        self.assertEqual(_i56_hashlib.sha256(frozen.read_bytes()).hexdigest(), before)

    def test_nested_proof_coherent_forgery_under_generation_guard(self):
        from terrain_pipeline.surface_identity import _plain as _i56__merged_coast__plain
        from terrain_pipeline.surface_identity import _freeze as _i56__merged_coast__freeze
        static_disabled = static_disabled
        plain = _i56_deepcopy(_i56__merged_coast__plain(self.result))
        mesh = plain['domain_mosaic']['domain_meshes'][0]
        proof_id = next(iter(mesh['proofs']))
        mesh['proof_h0_support'][proof_id]['weights'][0, 0] += 0.2
        mesh['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in mesh.items() if key != 'identity_sha256'})
        mosaic_record = plain['domain_mosaic']
        mosaic_record['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in mosaic_record.items() if key != 'identity_sha256'})
        plain['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in plain.items() if key != 'identity_sha256'})
        with _i56_ExitStack() as stack:
            static_disabled(stack)
            with self.assertRaises(ValueError):
                _i56_engineering.validate_surface_engineering(_i56__merged_coast__freeze(plain))

    def test_none_variable_never_prepares_or_imports(self):
        import sys
        with _i56_patch.dict(sys.modules, {'terrain_pipeline.surface_domain': None}):
            composed = _i56_engineering.compose_surface_engineering(self.evaluation, self.result['domain_mosaic'], self.result['drops'], self.result['dynamic_forest'])
            self.assertIsNone(_i56_engineering.query_surface_engineering(composed)['variable_storage'])

    def test_frozen_variable_same_forest_independent_prefix(self):
        from terrain_pipeline.surface_identity import _plain as _i56__merged_coast__plain
        from terrain_pipeline.surface_identity import _freeze as _i56__merged_coast__freeze
        from terrain_pipeline import surface_domain as variable
        self.assertEqual(_i56_hashlib.sha256(VARIABLE_SOURCE.read_bytes()).hexdigest(), VARIABLE_SHA256)
        saved = variable.load_surface_variable_storage(VARIABLE_SOURCE)
        result = _i56_engineering.compose_surface_engineering(self.evaluation, self.result['domain_mosaic'], self.result['drops'], saved['source'], variable_storage=saved)
        with _i56_tempfile.TemporaryDirectory() as directory:
            path = _i56_Path(directory) / 'variable-engineering.npz'
            _i56_engineering.save_surface_engineering(result, path)
            with _i56_ExitStack() as stack:
                for name in ('_geometry', '_knots', '_advance', 'prepare_surface_variable_storage'):
                    stack.enter_context(_i56_patch.object(variable, name, side_effect=AssertionError('generated')))
                loaded = _i56_engineering.load_surface_engineering(path)
                query = _i56_engineering.query_surface_engineering(loaded, state_index=80, variable_state_index=1)
            self.assertEqual(query['dynamic']['stage_m'].shape, (16,))
            self.assertEqual(query['variable_storage']['stage_m'].shape, (16,))
            self.assertNotEqual(float(query['dynamic']['time_s']), float(query['variable_storage']['time_s']))
            self.assertAlmostEqual(float(saved['storage_m3'][0].sum()), 224.5721879136545)
        bad = _i56_deepcopy(_i56__merged_coast__plain(result))
        bad['dynamic_forest'] = _i56__merged_coast__plain(self.result['dynamic_forest'])
        bad['identity_sha256'] = _i56_coast.fingerprint({key: item for key, item in bad.items() if key != 'identity_sha256'})
        with self.assertRaises(ValueError):
            _i56_engineering.validate_surface_engineering(_i56__merged_coast__freeze(bad))

    def test_coherent_aggregate_rehash_cannot_hide_mixed_source(self):
        from terrain_pipeline.surface_identity import _plain as _i56__merged_coast__plain
        from terrain_pipeline.surface_identity import _freeze as _i56__merged_coast__freeze
        plain = _i56_deepcopy(_i56__merged_coast__plain(self.result))
        plain['drops'][1] = plain['drops'][0]
        plain['identity_sha256'] = _i56_coast.fingerprint({key: value for key, value in plain.items() if key != 'identity_sha256'})
        with self.assertRaises(ValueError):
            _i56_engineering.validate_surface_engineering(_i56__merged_coast__freeze(plain))

    def test_cancel_and_resource_preflight(self):
        with self.assertRaises(InterruptedError):
            _i56_engineering.prepare_surface_engineering(self.evaluation, self.outlets, cancel=lambda: True, **_test_surface_multidomain_dynamic_forcing())
        with self.assertRaises(ValueError):
            _i56_engineering.prepare_surface_engineering(self.evaluation, self.outlets, resources=_i56_engineering.EngineeringResources(max_working_bytes=1024), **_test_surface_multidomain_dynamic_forcing())
TEST_SURFACE_LAND_COVERAGE_SOURCE = ROOT / 'verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz'
TEST_SURFACE_LAND_COVERAGE_SOURCE_SHA256 = '30f011385e72d346475ec1f6f0c71f74da216a238f38628c4b0668741628097e'

@_i58_lru_cache(maxsize=1)
def fixture():
    if _i58_hashlib.sha256(TEST_SURFACE_LAND_COVERAGE_SOURCE.read_bytes()).hexdigest() != TEST_SURFACE_LAND_COVERAGE_SOURCE_SHA256:
        raise AssertionError('frozen source changed')
    source = _i58_engineering.load_surface_engineering(TEST_SURFACE_LAND_COVERAGE_SOURCE)
    return (source, _i58_coverage.prepare_surface_land_coverage(source))

class SurfaceLandCoverageTests(_i58_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source, cls.result = fixture()

    def test_unique_footprint_and_original_interior(self):
        record = self.result
        self.assertEqual(record['nodes']['xz_m'].shape, (10011, 2))
        self.assertEqual(record['triangles'].shape, (19600, 3))
        self.assertEqual(record['ledger']['land_area_m2'], 9800.0)
        _i58_np.testing.assert_array_equal(_i58_np.bincount(record['domain_owner'])[1:], [4900, 4900])
        self.assertEqual(int((record['nodes']['xz_m'][:, 0] == 75).sum()), 71)
        for name in self.source['domain_mosaic']['nodes']:
            if name in record['nodes']:
                _i58_np.testing.assert_array_equal(record['nodes'][name][record['audit']['interior_node_ids']], self.source['domain_mosaic']['nodes'][name])
        self.assertAlmostEqual(record['ledger']['outer_cut_volume_m3'], 70.77028762295504)
        self.assertAlmostEqual(record['ledger']['interior_cut_volume_m3'], 576.8710544290027)
        self.assertEqual(record['ledger']['land_static_wet_cells'], 706)
        self.assertEqual(record['ledger']['source_dynamic_wet_cells'], 676)

    def test_half_pixel_source_support_no_positive_ocean(self):
        audit = self.result['audit']
        self.assertFalse(_i58_np.any(audit['positive_mask'] & ~audit['valid_land_support']))
        _i58_np.testing.assert_allclose(audit['weights'].sum(axis=1), 1.0, atol=1e-14)
        for domain_id, drop in zip((1, 2), self.source['drops']):
            selected = self.result['audit']['engineering_strip_domain'] == domain_id
            self.assertEqual(int(selected.sum()), 24)
            h0 = self.result['nodes']['h0_m'][selected].reshape(6, 4)
            self.assertFalse(_i58_np.array_equal(h0, drop['arrays']['h0_m'][:24].reshape(6, 4)))

    def test_crop_and_shared_xyz_no_duplicate_area_or_q(self):
        for outlet in self.result['outside_outlets']:
            ids = outlet['shared_land_node_ids']
            nodes = self.result['nodes']
            _i58_np.testing.assert_array_equal(outlet['bed_xyz_m'][:4, 1], nodes['h2_m'][ids])
            _i58_np.testing.assert_array_equal(outlet['water_xyz_m'][:4, 1], nodes['water_surface_m'][ids])
            self.assertEqual(outlet['triangles'].shape, (90, 3))
            self.assertTrue(_i58_np.all(outlet['bed_xyz_m'][:, 2] >= 75))
            self.assertAlmostEqual(outlet['terminal_q_m3_s'], 0.200049)
        self.assertEqual(self.result['ledger']['outside_attachment_area_m2'], 90.0)

    def test_static_roundtrip_no_assembly_or_generation(self):
        with _i58_tempfile.TemporaryDirectory() as directory:
            path = _i58_Path(directory) / 'land.npz'
            _i58_coverage.save_surface_land_coverage(self.result, path)
            before = _i58_hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                _i58_coverage.save_surface_land_coverage(self.result, path)
            self.assertEqual(_i58_hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with _i58_ExitStack() as stack:
                for name in ('_algebra', '_topology', 'prepare_surface_land_coverage'):
                    stack.enter_context(_i58_patch.object(_i58_coverage, name, side_effect=AssertionError('assembly')))
                for target in ('terrain_pipeline.surface_domain.recover_surface_network', 'terrain_pipeline.surface_domain._assemble', 'terrain_pipeline.surface_domain._surface_coast_drop_sample', 'terrain_pipeline.surface_domain._attachment', 'terrain_pipeline.surface_domain.bind_surface_dynamic_source', 'terrain_pipeline.surface_hydraulics.evaluate', 'terrain_pipeline.surface_domain._advance', 'terrain_pipeline.surface_domain._surface_variable_storage_geometry'):
                    stack.enter_context(_i58_patch(target, side_effect=AssertionError('generation')))
                loaded = _i58_coverage.load_surface_land_coverage(path)
                query = _i58_coverage.query_surface_land_coverage(loaded)
            self.assertEqual(loaded['identity_sha256'], self.result['identity_sha256'])
            self.assertEqual(query['fixed_dynamic_wet_cells'], 676)
            with self.assertRaises(ValueError):
                query['nodes']['h2_m'].setflags(write=True)

    def test_coherent_hash_forgeries_rejected(self):
        from terrain_pipeline.surface_identity import _plain as _i58__merged_coast__plain
        from terrain_pipeline.surface_identity import _freeze as _i58__merged_coast__freeze
        for mode in ('stencil', 'owner', 'bed', 'water', 'crop', 'ledger', 'scope', 'shape'):
            record = _i58_deepcopy(_i58__merged_coast__plain(self.result))
            if mode == 'stencil':
                record['audit']['weights'][0, 0] += 0.1
            elif mode == 'owner':
                record['domain_owner'][0] = 2
            elif mode == 'bed':
                record['nodes']['h2_m'][-1] -= 0.2
            elif mode == 'water':
                record['nodes']['water_surface_m'][0] = 1.0
            elif mode == 'crop':
                record['outside_outlets'][0]['shared_land_node_ids'][0] += 1
            elif mode == 'ledger':
                record['ledger']['outer_cut_volume_m3'] = 0.0
            elif mode == 'scope':
                record['land_pixel_footprint_represented'] = 1
            else:
                record['grid']['shape_nodes_zx'][0] = 71.0
            record['identity_sha256'] = _i58_coast.fingerprint({key: value for key, value in record.items() if key != 'identity_sha256'})
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                _i58_coverage.validate_surface_land_coverage(_i58__merged_coast__freeze(record))

    def test_resource_and_cancellation_preflight(self):
        for value in (True, 1024.0):
            with self.assertRaises(ValueError):
                _i58_coverage.CoverageResources(max_working_bytes=value)
        with _i58_patch.object(_i58_coverage, '_algebra', side_effect=AssertionError('allocated')):
            with self.assertRaises(ValueError):
                _i58_coverage.prepare_surface_land_coverage(self.source, resources=_i58_coverage.CoverageResources(max_working_bytes=1024))
            with self.assertRaises(InterruptedError):
                _i58_coverage.prepare_surface_land_coverage(self.source, cancel=lambda: True)

    def test_archive_strict_headers_before_load(self):
        headers = ["{'descr':'<f8','fortran_order':False,'shape':(1.0,)}", "{'descr':'<f8','fortran_order':False,'shape':(True,)}", "{'descr':'<f8','fortran_order':0,'shape':(1,)}", "{'descr':'<f8','fortran_order':False,'shape':(1,),'shape':(1,)}"]
        with _i58_tempfile.TemporaryDirectory() as directory:
            for index, header in enumerate(headers):
                path = _i58_Path(directory) / (str(index) + '.npz')
                raw = header.encode('latin1') + b'\n'
                spec = {'$array': 'array_0.npy', 'shape': [1], 'dtype': '<f8', 'sha256': '0' * 64}
                with _i58_zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('metadata.json', _i58_json.dumps({'format': _i58_coverage.SURFACE_LAND_COVERAGE_VERSION + '-npy-v1', 'tree': {'resources': {}, 'array': spec}}))
                    archive.writestr('array_0.npy', b'\x93NUMPY\x01\x00' + len(raw).to_bytes(2, 'little') + raw + b'\x00' * 8)
                with self.subTest(header=header), _i58_patch.object(_i58_np, 'load', side_effect=AssertionError('allocated')), self.assertRaises(ValueError):
                    _i58_coverage.load_surface_land_coverage(path)

    def test_atomic_publication_race_preserves_winner_and_cleans_temporary(self):
        with _i58_tempfile.TemporaryDirectory() as directory:
            destination = _i58_Path(directory) / 'land.npz'
            winner = b"another writer's completed artifact"

            def competing_writer(temporary, target):
                self.assertTrue(_i58_Path(temporary).is_file())
                _i58_Path(target).write_bytes(winner)
                raise FileExistsError(target)
            with _i58_patch.object(_i58_coverage.os, 'link', side_effect=competing_writer), self.assertRaises(FileExistsError):
                _i58_coverage.save_surface_land_coverage(self.result, destination)
            self.assertEqual(destination.read_bytes(), winner)
            self.assertEqual(list(_i58_Path(directory).iterdir()), [destination])

    def test_final_prepare_cancel_leaves_source_immutable(self):
        calls = 0
        before = _i58_coast.fingerprint(self.source)

        def final_cancel():
            nonlocal calls
            calls += 1
            return calls == 3
        with _i58_tempfile.TemporaryDirectory() as directory, _i58_patch.object(_i58_coverage, 'save_surface_land_coverage', side_effect=AssertionError('published')), self.assertRaises(InterruptedError):
            _i58_coverage.prepare_surface_land_coverage(self.source, cancel=final_cancel)
            self.fail('final cancellation returned a product')
        self.assertEqual(calls, 3)
        self.assertEqual(_i58_coast.fingerprint(self.source), before)
        self.assertEqual(_i58_hashlib.sha256(TEST_SURFACE_LAND_COVERAGE_SOURCE.read_bytes()).hexdigest(), TEST_SURFACE_LAND_COVERAGE_SOURCE_SHA256)

    def test_archive_duplicate_compressed_unused_preflight(self):
        with _i58_tempfile.TemporaryDirectory() as directory:
            original = _i58_Path(directory) / 'original.npz'
            _i58_coverage.save_surface_land_coverage(self.result, original)
            for mode in ('duplicate', 'compressed', 'unused'):
                path = _i58_Path(directory) / (mode + '.npz')
                with _i58_zipfile.ZipFile(original) as source, _i58_zipfile.ZipFile(path, 'w') as target:
                    for name in source.namelist():
                        target.writestr(name, source.read(name), compress_type=_i58_zipfile.ZIP_DEFLATED if mode == 'compressed' and name == 'metadata.json' else _i58_zipfile.ZIP_STORED)
                    if mode == 'duplicate':
                        with _i58_warnings.catch_warnings():
                            _i58_warnings.simplefilter('ignore', UserWarning)
                            target.writestr('metadata.json', source.read('metadata.json'))
                    elif mode == 'unused':
                        target.writestr('unused.npy', b'not referenced')
                with self.subTest(mode=mode), _i58_patch.object(_i58_np, 'load', side_effect=AssertionError('allocated')), self.assertRaises(ValueError):
                    _i58_coverage.load_surface_land_coverage(path)
DECLARATION = 'Engineered synthetic terrain, local metre datum; not certified real geography'
DATUM = 'synthetic-local-metre'

def rewrite_delivery(path, change):
    from terrain_pipeline.artifacts.contracts import digest as _i60_digest
    from terrain_pipeline.surface_domain import _array_record as _i60__array_record
    from terrain_pipeline.surface_domain import _file_hash as _i60__file_hash
    manifest = _i60_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    with _i60_np.load(path / 'hydro.npz', allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    change(manifest, arrays)
    _i60_np.savez_compressed(path / 'hydro.npz', **arrays)
    manifest['arrays'] = _i60__array_record(arrays)
    manifest['files']['hydro.npz'] = _i60__file_hash(path / 'hydro.npz')
    manifest['content_id'] = _i60_digest({key: value for key, value in manifest.items() if key != 'content_id'})
    (path / 'manifest.json').write_text(_i60_json.dumps(manifest, sort_keys=True), encoding='utf-8')

def forbid_generation():
    stack = _i60_ExitStack()
    for target in ('terrain_pipeline.surface_domain.validate_surface_network_recovery', 'terrain_pipeline.surface_domain.recover_surface_network', 'terrain_pipeline.surface_domain._surface', 'terrain_pipeline.surface_domain.prepare_surface_network', 'terrain_pipeline.surface_domain.prepare_surface_network', 'terrain_pipeline.channel_geometry.prepare_network_valley', 'terrain_pipeline.surface_hydraulics.reroute_channel', 'terrain_pipeline.channel_geometry.plan_channel'):
        stack.enter_context(_i60_patch(target, side_effect=AssertionError('reader must not generate')))
    return stack

def rehash_surface_recovery(result):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i60_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i60_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i60_digest
    from terrain_pipeline.surface_domain import _fingerprint as _i60__fingerprint
    identity_record = _i60_deepcopy(result['surface']['identity'])
    identity_record['parameters']['output_sha256'] = _i60_digest({name: _i60_array_hash(value) for name, value in result['surface']['arrays'].items()})
    identity_record['parameters']['summary_sha256'] = _i60_digest(result['surface']['summary'])
    identity = _i60_ArtifactIdentity(**identity_record)
    result['surface']['identity'] = identity.record()
    result['surface']['identity_sha256'] = identity.sha256
    result['identity_sha256'] = _i60__fingerprint({key: value for key, value in result.items() if key != 'identity_sha256'})
    return result

def forge_delivery_proof(path, result):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i60_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import digest as _i60_digest
    from terrain_pipeline.surface_domain import _array_record as _i60__array_record
    from terrain_pipeline.surface_domain import _file_hash as _i60__file_hash
    from terrain_pipeline.surface_domain import _payload as _i60__payload
    from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
    from terrain_pipeline.surface_domain import _surface_network_recovery_tree as _i60__tree
    loaded = _i60_load_surface_network_delivery(path)
    base, derived = (loaded['base'], loaded['derived'])
    base_record = base.identity.record()
    base_record['parameters']['recovery_sha256'] = result['identity_sha256']
    base = _i60_replace(base, identity=_i60_ArtifactIdentity(**base_record))
    derived_record = derived.identity.record()
    derived_record['parameters'].update(recovery_sha256=result['identity_sha256'], base_content_id=base.content_id)
    derived = _i60_replace(derived, identity=_i60_ArtifactIdentity(**derived_record), source_artifact_id=base.content_id)
    for name, artifact in (('base', base), ('derived', derived)):
        (path / name / 'manifest.json').write_text(_i60_json.dumps({**artifact.content_record(), 'content_id': artifact.content_id}, sort_keys=True), encoding='utf-8')
    manifest = _i60_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    arrays = _i60__payload(result)
    proof_arrays = {}
    manifest['proof'] = _i60__tree(result, proof_arrays)
    arrays.update(proof_arrays)
    _i60_np.savez_compressed(path / 'hydro.npz', **arrays)
    manifest.update(base_content_id=base.content_id, derived_content_id=derived.content_id, recovery_sha256=result['identity_sha256'], arrays=_i60__array_record(arrays))
    manifest['files'] = {name: _i60__file_hash(path / name) for name in manifest['files']}
    manifest['content_id'] = _i60_digest({key: value for key, value in manifest.items() if key != 'content_id'})
    (path / 'manifest.json').write_text(_i60_json.dumps(manifest, sort_keys=True), encoding='utf-8')

class SurfaceNetworkConsumerTests(_i60_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.surface_domain import recover_surface_network as _i60_recover_surface_network
        cls.results = {kind: _i60_recover_surface_network(**recovery_case(kind)) for kind in ('baseline', 'valley', 'reroute')}

    def publish(self, directory, kind='baseline', name='delivery'):
        from terrain_pipeline.surface_domain import export_surface_network as _i60_export_surface_network
        path = _i60_Path(directory) / name
        _i60_export_surface_network(self.results[kind], DATUM, path, source_declaration=DECLARATION)
        return path

    def test_three_deliveries_generic_base_derived_and_hydrology(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            for kind in self.results:
                path = self.publish(directory, kind, kind)
                loaded = _i60_load_surface_network_delivery(path)
                source = self.results[kind]
                expected = source['surface']['arrays'] if source['fine_ledger'] is None else source['fine_ledger']['arrays']
                h0 = expected['source_surface_m']
                _i60_np.testing.assert_array_equal(loaded['base'].reference_elevation_m, h0)
                _i60_np.testing.assert_array_equal(loaded['derived'].reference_elevation_m, h0)
                _i60_np.testing.assert_allclose(loaded['derived'].reconstruct_positions_m()[1], expected['final_surface_m'])
                self.assertIsNone(loaded['base'].water)
                self.assertIsNone(loaded['derived'].water)
                loaded['derived'].verify_source(loaded['base'])

    def test_valley_base_is_h0_not_post_valley_h1(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        result = self.results['valley']
        h0 = result['fine_ledger']['arrays']['source_surface_m']
        h1 = result['surface']['arrays']['source_surface_m']
        self.assertGreater(float(_i60_np.max(h0 - h1)), 0.0)
        with _i60_tempfile.TemporaryDirectory() as directory:
            loaded = _i60_load_surface_network_delivery(self.publish(directory, 'valley'))
            _i60_np.testing.assert_array_equal(loaded['base'].reference_elevation_m, h0)
            self.assertFalse(_i60_np.array_equal(loaded['base'].reference_elevation_m, h1))

    def test_source_h0_unchanged_and_hard_immutable_loaded_payload(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        result = self.results['valley']
        before = result['inputs']['plan']['arrays']['source_height_m'].copy()
        with _i60_tempfile.TemporaryDirectory() as directory:
            loaded = _i60_load_surface_network_delivery(self.publish(directory, 'valley'))
            arrays = [loaded['base'].reference_elevation_m, loaded['derived'].displacement_m, *loaded['geometry'].values(), *loaded['centerline'].values()]
            for array in arrays:
                with self.assertRaises(ValueError):
                    array.flags.writeable = True
            with self.assertRaises(TypeError):
                loaded['manifest']['grid']['origin_x_m'] = 1
        _i60_np.testing.assert_array_equal(before, result['inputs']['plan']['arrays']['source_height_m'])

    def test_loader_sample_and_slices_never_generate(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        from terrain_pipeline.surface_domain import sample_surface_network as _i60_sample_surface_network
        from terrain_pipeline.surface_domain import slice_surface_network_world as _i60_slice_surface_network_world
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory, 'valley')
            with forbid_generation():
                loaded = _i60_load_surface_network_delivery(path)
                sample = _i60_sample_surface_network(loaded, 30.0, 30.0)
                window = _i60_slice_surface_network_world(loaded, (20.0, 20.0, 40.0, 40.0))
                self.assertEqual(sample['arrays']['final_surface_m'].shape, (1, 1))
                self.assertEqual(window['arrays']['final_surface_m'].shape, (21, 21))

    def test_overlapping_windows_load_order_and_exact_values(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        from terrain_pipeline.surface_domain import slice_surface_network_delivery as _i60_slice_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            first = _i60_load_surface_network_delivery(path)
            second = _i60_load_surface_network_delivery(path)
            for loaded in (second, first):
                right = _i60_slice_surface_network_delivery(loaded, slice(10, 51), slice(25, 61))
                left = _i60_slice_surface_network_delivery(loaded, slice(10, 51), slice(0, 41))
                for name in loaded['geometry']:
                    _i60_np.testing.assert_array_equal(left['arrays'][name][:, 25:41], right['arrays'][name][:, :16])
                    self.assertFalse(left['arrays'][name].flags.writeable)

    def test_world_coordinates_datum_and_invalid_queries(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        from terrain_pipeline.surface_domain import sample_surface_network as _i60_sample_surface_network
        from terrain_pipeline.surface_domain import slice_surface_network_delivery as _i60_slice_surface_network_delivery
        from terrain_pipeline.surface_domain import slice_surface_network_world as _i60_slice_surface_network_world
        with _i60_tempfile.TemporaryDirectory() as directory:
            loaded = _i60_load_surface_network_delivery(self.publish(directory))
            sample = _i60_sample_surface_network(loaded, 30.0, 40.0)
            self.assertEqual(sample['origin_x_m'], 30.0)
            self.assertEqual(sample['origin_z_m'], 40.0)
            self.assertEqual(sample['vertical_datum'], DATUM)
            self.assertEqual(sample['unit'], 'm')
            for coords in ((0.5, 0.0), (-1.0, 0.0), (61.0, 0.0), (True, 0.0), (_i60_np.nan, 0.0)):
                with self.subTest(coords=coords), self.assertRaises(ValueError):
                    _i60_sample_surface_network(loaded, *coords)
            with self.assertRaises(ValueError):
                _i60_slice_surface_network_world(loaded, (40.0, 40.0, 20.0, 20.0))
            with self.assertRaises(ValueError):
                _i60_slice_surface_network_delivery(loaded, slice(0, 10, 2), slice(0, 10))

    def test_q_stays_in_coarse_graph_not_wet_raster(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            loaded = _i60_load_surface_network_delivery(self.publish(directory))
            graph = loaded['centerline']
            self.assertEqual(graph['world_xz_m'].shape, (49, 2))
            self.assertEqual(graph['discharge_m3_s'].shape, (49,))
            self.assertNotIn('discharge_m3_s', loaded['geometry'])
            self.assertAlmostEqual(float(graph['local_discharge_m3_s'].sum()), float(graph['discharge_m3_s'][graph['outlet_mask']].sum()))
            self.assertEqual(loaded['manifest']['hydrology']['Q_semantics'], 'coarse_node_reach_discharge_not_additive_across_nodes')

    def test_dry_stage_is_finite_zero_with_explicit_mask(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        from terrain_pipeline.surface_domain import sample_surface_network as _i60_sample_surface_network
        with _i60_tempfile.TemporaryDirectory() as directory:
            loaded = _i60_load_surface_network_delivery(self.publish(directory))
            geometry = loaded['geometry']
            water, wet = (geometry['water_surface_m'], geometry['wet_mask'])
            self.assertTrue(_i60_np.isfinite(water).all())
            self.assertTrue(_i60_np.all(water[~wet] == 0))
            self.assertTrue(_i60_np.all(water[wet] > geometry['final_surface_m'][wet]))
            sample = _i60_sample_surface_network(loaded, 0.0, 0.0)
            self.assertFalse(sample['arrays']['wet_mask'][0, 0])
            self.assertEqual(sample['arrays']['water_depth_m'][0, 0], 0.0)

    def test_invalid_datum_or_source_declaration_early_rejected(self):
        from terrain_pipeline.surface_domain import export_surface_network as _i60_export_surface_network
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = _i60_Path(directory) / 'bad'
            for datum in (None, '', ' ', 'unknown', 'x\ny', True):
                with self.subTest(datum=datum), self.assertRaises(ValueError):
                    _i60_export_surface_network(self.results['baseline'], datum, path, source_declaration=DECLARATION)
            with self.assertRaises(ValueError):
                _i60_export_surface_network(self.results['baseline'], DATUM, path)
            self.assertFalse(path.exists())

    def test_failure_and_forged_surface_refuse_export(self):
        from terrain_pipeline.surface_domain import export_surface_network as _i60_export_surface_network
        from terrain_pipeline.surface_domain import recover_surface_network as _i60_recover_surface_network
        case = recovery_case('valley')
        case['valley_recipe'] = _i60_replace(case['valley_recipe'], max_total_cut_volume_m3=0.0)
        case['recovery_recipe'] = _i60_replace(case['recovery_recipe'], max_attempts=2)
        failed = _i60_recover_surface_network(**case)
        self.assertEqual(failed['surface']['status'], 'prepared')
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = _i60_Path(directory) / 'bad'
            with self.assertRaises(ValueError):
                _i60_export_surface_network(failed, DATUM, path, source_declaration=DECLARATION)
            forged = _i60_deepcopy(self.results['baseline'])
            forged['surface']['arrays']['final_surface_m'] = forged['surface']['arrays']['final_surface_m'].copy()
            forged['surface']['arrays']['final_surface_m'][30, 30] -= 0.1
            with self.assertRaises(ValueError):
                _i60_export_surface_network(forged, DATUM, path, source_declaration=DECLARATION)
            self.assertFalse(path.exists())

    def test_no_overwrite_and_atomic_rename_failure_cleanup(self):
        from terrain_pipeline.surface_domain import _file_hash as _i60__file_hash
        from terrain_pipeline.surface_domain import export_surface_network as _i60_export_surface_network
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            original_hash = _i60__file_hash(path / 'manifest.json')
            with self.assertRaises(FileExistsError):
                _i60_export_surface_network(self.results['valley'], DATUM, path, source_declaration=DECLARATION)
            self.assertEqual(_i60__file_hash(path / 'manifest.json'), original_hash)
            real_rename = _i60_os.rename

            def fail_outer(source, destination):
                if _i60_Path(destination).name == 'failed':
                    raise OSError('publish unavailable')
                return real_rename(source, destination)
            with _i60_patch('terrain_pipeline.surface_domain.os.rename', side_effect=fail_outer):
                with self.assertRaises(OSError):
                    _i60_export_surface_network(self.results['baseline'], DATUM, _i60_Path(directory) / 'failed', source_declaration=DECLARATION)
            self.assertEqual([item.name for item in _i60_Path(directory).iterdir()], ['delivery'])

    def test_windows_publish_race_cannot_replace_existing_directory(self):
        from terrain_pipeline.surface_domain import export_surface_network as _i60_export_surface_network
        if _i60_os.name != 'nt':
            self.skipTest('Windows directory rename race semantics')
        with _i60_tempfile.TemporaryDirectory() as directory:
            destination = _i60_Path(directory) / 'raced'
            real_rename = _i60_os.rename

            def race(source, target):
                if _i60_Path(target) == destination:
                    destination.mkdir()
                    (destination / 'sentinel').write_text('other writer', encoding='utf-8')
                return real_rename(source, target)
            with _i60_patch('terrain_pipeline.surface_domain.os.rename', side_effect=race):
                with self.assertRaises(FileExistsError):
                    _i60_export_surface_network(self.results['baseline'], DATUM, destination, source_declaration=DECLARATION)
            self.assertEqual((destination / 'sentinel').read_text(encoding='utf-8'), 'other writer')
            self.assertEqual([item.name for item in _i60_Path(directory).iterdir()], ['raced'])

    def test_rehashed_sidecar_corruption_rejected_for_each_semantic_field(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            changes = {'water_surface_m': (0, 0), 'source_surface_m': (30, 30), 'final_surface_m': (30, 30), 'discharge_m3_s': (17,), 'receiver': (9,)}
            for name, index in changes.items():
                path = self.publish(directory, name=name)

                def corrupt(manifest, arrays):
                    arrays[name] = arrays[name].copy()
                    arrays[name][index] += 1
                rewrite_delivery(path, corrupt)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    _i60_load_surface_network_delivery(path)

    def test_source_hash_and_proof_status_forgery_rejected(self):
        from terrain_pipeline.artifacts.contracts import array_hash as _i60_array_hash
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            for kind in ('hash', 'status'):
                path = self.publish(directory, name=kind)

                def corrupt(manifest, arrays):
                    if kind == 'hash':
                        ref = manifest['proof']['inputs']['plan']['arrays']['source_height_m']
                        arrays[ref['$array']] = arrays[ref['$array']].copy()
                        arrays[ref['$array']][0, 0] += 1
                        ref['sha256'] = _i60_array_hash(arrays[ref['$array']])
                    else:
                        manifest['proof']['surface']['summary']['publishable'] = False
                rewrite_delivery(path, corrupt)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    _i60_load_surface_network_delivery(path)

    def test_actual_geometry_gate_rejects_negative_cut_protection_domain_drywater(self):
        from terrain_pipeline.surface_domain import _surface_network_consumer_geometry_gate as _i60__geometry_gate
        from terrain_pipeline.surface_domain import _payload as _i60__payload
        result = self.results['baseline']
        for kind in ('negative', 'protected', 'domain', 'drywater', 'disconnected'):
            arrays = {name: array.copy() for name, array in _i60__payload(result).items()}
            wet_row, wet_column = _i60_np.argwhere(arrays['wet_mask'])[0]
            if kind == 'negative':
                arrays['total_cut_m'][30, 30] = -1.0
            if kind == 'protected':
                arrays['protected_mask'][wet_row, wet_column] = True
            if kind == 'domain':
                arrays['domain_mask'][wet_row, wet_column] = False
            if kind == 'drywater':
                arrays['water_surface_m'][0, 0] = 1.0
            if kind == 'disconnected':
                arrays['wet_mask'][0, 0] = True
                arrays['water_surface_m'][0, 0] = arrays['final_surface_m'][0, 0] + 0.2
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _i60__geometry_gate(arrays, result)

    def test_actual_geometry_gate_enforces_cumulative_ledger(self):
        from terrain_pipeline.surface_domain import _surface_network_consumer_geometry_gate as _i60__geometry_gate
        from terrain_pipeline.surface_domain import _payload as _i60__payload
        result = _i60_deepcopy(self.results['valley'])
        result['inputs']['valley_recipe']['max_total_cut_volume_m3'] = 0.0
        with self.assertRaisesRegex(ValueError, 'cumulative'):
            _i60__geometry_gate(_i60__payload(result), result)

    def test_graph_q_nonconservative_and_bad_order_rejected(self):
        from terrain_pipeline.surface_domain import _local_q as _i60__local_q
        arrays = {name: array.copy() for name, array in self.results['baseline']['final_plan']['arrays'].items()}
        arrays['discharge_m3_s'][2, 3] = 0.1
        with self.assertRaisesRegex(ValueError, 'nonconservative'):
            _i60__local_q(arrays)
        arrays['order'] = arrays['order'][::-1].copy()
        with self.assertRaises(ValueError):
            _i60__local_q(arrays)

    def test_strict_json_unexpected_files_and_broken_artifact_chain_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            manifest_path = path / 'manifest.json'
            encoded = manifest_path.read_text(encoding='utf-8')
            manifest_path.write_text('{"format_version":0,' + encoded[1:], encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                _i60_load_surface_network_delivery(path)
            manifest_path.write_text(encoded, encoding='utf-8')
            (path / 'unexpected').write_text('x', encoding='utf-8')
            with self.assertRaises(ValueError):
                _i60_load_surface_network_delivery(path)

    def test_rehashed_actual_stage_jump_rejected_by_loader(self):
        from terrain_pipeline.surface_domain import _payload as _i60__payload
        from terrain_pipeline.surface_domain import _proof_gate as _i60__proof_gate
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        forged = _i60_deepcopy(self.results['baseline'])
        water = forged['surface']['arrays']['water_surface_m'].copy()
        self.assertTrue(forged['surface']['arrays']['wet_mask'][9, 19])
        water[9, 19] += 2.0
        forged['surface']['arrays']['water_surface_m'] = water
        rehash_surface_recovery(forged)
        with self.assertRaisesRegex(ValueError, 'stage transition'):
            _i60__proof_gate(forged, _i60__payload(forged))
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            forge_delivery_proof(path, forged)
            with forbid_generation(), self.assertRaisesRegex(ValueError, 'stage transition'):
                _i60_load_surface_network_delivery(path)

    def test_rehashed_noncoarse_fine_domain_change_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        forged = _i60_deepcopy(self.results['baseline'])
        domain = forged['surface']['arrays']['domain_mask'].copy()
        domain[9, 19] = False
        forged['surface']['arrays']['domain_mask'] = domain
        rehash_surface_recovery(forged)
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            forge_delivery_proof(path, forged)
            with self.assertRaisesRegex(ValueError, 'domain'):
                _i60_load_surface_network_delivery(path)

    def test_rehashed_off_channel_fine_constraint_mismatch_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        forged = _i60_deepcopy(self.results['baseline'])
        protected = forged['surface']['arrays']['protected_mask'].copy()
        protected[1, 1] = True
        forged['surface']['arrays']['protected_mask'] = protected
        rehash_surface_recovery(forged)
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            forge_delivery_proof(path, forged)
            with self.assertRaisesRegex(ValueError, 'fine masks'):
                _i60_load_surface_network_delivery(path)

    def test_broken_artifact_source_and_hydrology_semantics_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)

            def corrupt(manifest, arrays):
                manifest['hydrology']['Q_semantics'] = 'sum_wet_cells'
            rewrite_delivery(path, corrupt)
            with self.assertRaisesRegex(ValueError, 'semantics'):
                _i60_load_surface_network_delivery(path)
            path = self.publish(directory, name='source_chain')
            manifest = _i60_json.loads((path / 'derived' / 'manifest.json').read_text(encoding='utf-8'))
            manifest['source_artifact_id'] = '0' * 64
            (path / 'derived' / 'manifest.json').write_text(_i60_json.dumps(manifest), encoding='utf-8')
            with self.assertRaises(ValueError):
                _i60_load_surface_network_delivery(path)

    def test_legal_repeated_proof_array_references_can_load(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)

            def deduplicate(manifest, arrays):
                seen = {}
                removed = set()

                def visit(value):
                    if isinstance(value, dict) and '$array' in value:
                        key = (value['sha256'], value['dtype'], tuple(value['shape']))
                        if key in seen:
                            removed.add(value['$array'])
                            value['$array'] = seen[key]
                        else:
                            seen[key] = value['$array']
                    elif isinstance(value, dict):
                        for child in value.values():
                            visit(child)
                    elif isinstance(value, list):
                        for child in value:
                            visit(child)
                visit(manifest['proof'])
                for name in removed:
                    arrays.pop(name)
            rewrite_delivery(path, deduplicate)
            with forbid_generation():
                loaded = _i60_load_surface_network_delivery(path)
            self.assertEqual(loaded['geometry']['final_surface_m'].shape, (61, 61))

    def test_combined_npz_uncompressed_and_metadata_bounds_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            with _i60_patch('terrain_pipeline.surface_domain._bounded_npz', return_value=100 * 1024 * 1024):
                with self.assertRaisesRegex(ValueError, 'total uncompressed'):
                    _i60_load_surface_network_delivery(path)
            with _i60_patch('terrain_pipeline.surface_domain.SURFACE_NETWORK_CONSUMER_MAX_BYTES', 100):
                with self.assertRaisesRegex(ValueError, 'total resource'):
                    _i60_load_surface_network_delivery(path)

    def test_parent_symlink_or_junction_chain_rejected(self):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i60_load_surface_network_delivery
        with _i60_tempfile.TemporaryDirectory() as directory:
            path = self.publish(directory)
            parent = _i60_Path(directory)
            original = _i60_Path.is_symlink

            def mark_parent(item):
                return item == parent or original(item)
            with _i60_patch.object(_i60_Path, 'is_symlink', mark_parent):
                with self.assertRaisesRegex(ValueError, 'symlinks or junctions'):
                    _i60_load_surface_network_delivery(path)

class LargeSurfaceNetworkBenchmarkTests(_i61_unittest.TestCase):

    def test_1024_static_tiles_crossings_and_outlets_are_deterministic(self):
        from terrain_pipeline.surface_domain import LargeBenchmarkBudget as _i61_LargeBenchmarkBudget
        from terrain_pipeline.surface_domain import prepare_large_static as _i61_prepare_large_static
        from terrain_pipeline.surface_domain import validate_large_static as _i61_validate_large_static
        rows = _i61_np.arange(1024, dtype=_i61_np.float64)[:, None]
        columns = _i61_np.arange(1024, dtype=_i61_np.float64)[None, :]
        height = rows + columns
        budget = _i61_LargeBenchmarkBudget(tile_cells=256, max_resident_bytes=256 * 1024 * 1024)
        first = _i61_prepare_large_static(height, spacing_m=30.0, origin_m_xz=[100.0, 200.0], budget=budget)
        second = _i61_prepare_large_static(height, spacing_m=30.0, origin_m_xz=[100.0, 200.0], budget=budget)
        for key in first['arrays']:
            _i61_np.testing.assert_array_equal(first['arrays'][key], second['arrays'][key])
        self.assertEqual(first['metadata']['tile_count'], 16)
        self.assertGreater(first['arrays']['crossing_donor'].size, 0)
        self.assertEqual(_i61_validate_large_static(first)['cells'], 1024 * 1024)

    def test_step_storage_is_tile_partitioned_and_bounded(self):
        from terrain_pipeline.surface_domain import LargeBenchmarkBudget as _i61_LargeBenchmarkBudget
        from terrain_pipeline.surface_domain import prepare_large_static as _i61_prepare_large_static
        from terrain_pipeline.surface_domain import run_one_step_storage as _i61_run_one_step_storage
        height = _i61_np.zeros((1024, 1024), _i61_np.float32)
        static = _i61_prepare_large_static(height, budget=_i61_LargeBenchmarkBudget(tile_cells=256))
        result = _i61_run_one_step_storage(static, forcing_m3_s=0.01, duration_s=900.0)
        self.assertEqual(result['arrays']['tile_input_volume_m3'].shape, (16,))
        self.assertAlmostEqual(float(result['arrays']['total_input_volume_m3']), 9437184.0, places=8)

    def test_rejects_non_terrain_diffusion_or_large_budget(self):
        from terrain_pipeline.surface_domain import LargeBenchmarkBudget as _i61_LargeBenchmarkBudget
        from terrain_pipeline.surface_domain import prepare_large_static as _i61_prepare_large_static
        with self.assertRaises(ValueError):
            _i61_prepare_large_static(_i61_np.zeros((512, 512), _i61_np.float64))
        with self.assertRaises(ValueError):
            _i61_prepare_large_static(_i61_np.zeros((1024, 1024), _i61_np.int16))
        with self.assertRaises(ValueError):
            _i61_prepare_large_static(_i61_np.zeros((1024, 1024), _i61_np.float64), budget=_i61_LargeBenchmarkBudget(max_cells=1024))

class SurfaceNetworkPrepareTests(_i62_unittest.TestCase):

    def make_result(self, budget):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i62_InundationRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i62_StageRecipe
        from terrain_pipeline.channel_geometry import SectionRecipe as _i62_SectionRecipe
        from terrain_pipeline.surface_domain import prepare_surface_network as _i62_prepare_surface_network
        plan = _x3_confluence_plan()
        domain = _i62_np.ones((61, 61), bool)
        protected = _i62_np.zeros((61, 61), bool)
        legal = _i62_np.zeros((61, 61), bool)
        legal[-1, 27:34] = True
        result = _i62_prepare_surface_network(plan, 0.0, 0.0, 1.0, 1.0, (61, 61), domain, protected, legal, _i62_np.array([5.2]), _i62_SectionRecipe(), _i62_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i62_InundationRecipe(max_lateral_reach_m=15.0), budget)
        return (plan, result)

    def test_confluence_prepared_and_reloaded(self):
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import load_surface_network as _i62_load_surface_network
        from terrain_pipeline.surface_domain import save_surface_network as _i62_save_surface_network
        plan, result = self.make_result(_i62_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        self.assertEqual(result['status'], 'prepared')
        self.assertGreater(result['summary']['cut_volume_m3'], 0)
        self.assertEqual(result['summary']['max_stage_bed_error_m'], 0)
        self.assertTrue(result['arrays']['wet_mask'].any())
        _i62_np.testing.assert_array_equal(plan['arrays']['source_height_m'], _x3_confluence_plan()['arrays']['source_height_m'])
        with _i62_tempfile.TemporaryDirectory() as directory:
            path = _i62_Path(directory) / 'surface.npz'
            _i62_save_surface_network(result, path)
            loaded = _i62_load_surface_network(path)
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])
            with _i62_np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != 'manifest'}
                manifest = archive['manifest'].item()
            arrays['bed_cut_m'] = arrays['bed_cut_m'].copy()
            arrays['bed_cut_m'][0, 0] += 1
            _i62_np.savez_compressed(path, manifest=manifest, **arrays)
            with self.assertRaises(ValueError):
                _i62_load_surface_network(path)

    def test_budget_failure_refuses_publication(self):
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import save_surface_network as _i62_save_surface_network
        _, result = self.make_result(_i62_SurfaceNetworkBudget(4.0, 10.0, 10.0))
        self.assertFalse(result['summary']['publishable'])
        self.assertTrue(result['summary']['budget_failures']['area'])
        with _i62_tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                _i62_save_surface_network(result, _i62_Path(directory) / 'failed.npz')

    def test_semantic_summary_tamper_rejected(self):
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import load_surface_network as _i62_load_surface_network
        from terrain_pipeline.surface_domain import save_surface_network as _i62_save_surface_network
        _, result = self.make_result(_i62_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        with _i62_tempfile.TemporaryDirectory() as directory:
            path = _i62_Path(directory) / 'surface.npz'
            _i62_save_surface_network(result, path)
            with _i62_np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != 'manifest'}
                manifest = _i62_json.loads(str(archive['manifest'].item()))
            manifest['summary']['joint_blockers']['stage'] = True
            _i62_np.savez_compressed(path, manifest=_i62_json.dumps(manifest), **arrays)
            with self.assertRaises(ValueError):
                _i62_load_surface_network(path)

    def test_reidentified_failed_result_cannot_publish(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i62_ArtifactIdentity
        from terrain_pipeline.artifacts.contracts import digest as _i62_digest
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import save_surface_network as _i62_save_surface_network
        _, result = self.make_result(_i62_SurfaceNetworkBudget(4.0, 10.0, 10.0))
        with _i62_tempfile.TemporaryDirectory() as directory:
            path = _i62_Path(directory) / 'forged.npz'
            summary = _i62_json.loads(_i62_json.dumps(result['summary']))
            summary['publishable'] = True
            identity_record = _i62_json.loads(_i62_json.dumps(result['identity']))
            identity_record['parameters']['summary_sha256'] = _i62_digest(summary)
            identity = _i62_ArtifactIdentity(**identity_record)
            forged = {**result, 'summary': summary, 'status': 'prepared', 'identity': identity.record(), 'identity_sha256': identity.sha256}
            with self.assertRaises(ValueError):
                _i62_save_surface_network(forged, path)

    def test_reidentified_isolated_wet_cell_rejected(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i62_ArtifactIdentity
        from terrain_pipeline.artifacts.contracts import array_hash as _i62_array_hash
        from terrain_pipeline.artifacts.contracts import digest as _i62_digest
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import save_surface_network as _i62_save_surface_network
        _, result = self.make_result(_i62_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        arrays = {name: value.copy() for name, value in result['arrays'].items()}
        arrays['wet_mask'][0, 0] = True
        arrays['water_surface_m'][0, 0] = arrays['final_surface_m'][0, 0] + 1
        summary = _i62_json.loads(_i62_json.dumps(result['summary']))
        summary['inundation']['wet_nodes'] += 1
        identity_record = _i62_json.loads(_i62_json.dumps(result['identity']))
        identity_record['parameters']['output_sha256'] = _i62_digest({name: _i62_array_hash(value) for name, value in arrays.items()})
        identity_record['parameters']['summary_sha256'] = _i62_digest(summary)
        identity = _i62_ArtifactIdentity(**identity_record)
        forged = {**result, 'arrays': arrays, 'summary': summary, 'identity': identity.record(), 'identity_sha256': identity.sha256}
        with _i62_tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                _i62_save_surface_network(forged, _i62_Path(directory) / 'isolated.npz')

    def test_outside_domain_cut_rejected(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i62_InundationRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i62_StageRecipe
        from terrain_pipeline.channel_geometry import SectionRecipe as _i62_SectionRecipe
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import prepare_surface_network as _i62_prepare_surface_network
        plan = _x3_confluence_plan()
        domain = _i62_np.ones((61, 61), bool)
        domain[20, 30] = False
        blank = _i62_np.zeros((61, 61), bool)
        legal = blank.copy()
        legal[-1, 27:34] = True
        result = _i62_prepare_surface_network(plan, 0.0, 0.0, 1.0, 1.0, (61, 61), domain, blank, legal, _i62_np.array([5.2]), _i62_SectionRecipe(), _i62_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i62_InundationRecipe(max_lateral_reach_m=15.0), _i62_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        self.assertTrue(result['summary']['budget_failures']['outside_domain_cut'])
        self.assertEqual(result['status'], 'diagnostic_not_publishable')

    def test_overlapping_world_slices_share_exact_values(self):
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i62_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import slice_surface_network as _i62_slice_surface_network
        _, result = self.make_result(_i62_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        first = _i62_slice_surface_network(result, slice(0, 40), slice(0, 40))
        second = _i62_slice_surface_network(result, slice(20, 61), slice(20, 61))
        self.assertEqual(second['origin_x_m'], 20.0)
        self.assertEqual(second['origin_z_m'], 20.0)
        for name in result['arrays']:
            _i62_np.testing.assert_array_equal(first['arrays'][name][20:40, 20:40], second['arrays'][name][0:20, 0:20])
            self.assertFalse(first['arrays'][name].flags.writeable)
CONSUMER = ROOT / 'verification/surface-network-consumer/run-20260930T080544.956105Z'
BASELINES = {'baseline': (169.508735962729, 518.5), 'valley': (1051.594182146892, 2930.0), 'reroute': (29.111269224638, 89.5)}

def write_manifest(path, manifest):
    from terrain_pipeline.artifacts.contracts import digest as _i64_digest
    manifest['content_id'] = _i64_digest({name: value for name, value in manifest.items() if name != 'content_id'})
    (path / 'manifest.json').write_text(_i64_json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

def mutate_tile(path, index, change, *, also_proof=False):
    from terrain_pipeline.surface_domain import _file_hash as _i64__file_hash
    manifest = _i64_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    tile = manifest['tiles'][index]
    file = path / tile['path']
    with _i64_np.load(file, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    change(arrays)
    _i64_np.savez(file, **arrays)
    tile['arrays'] = {name: _i64_tiles._surface_network_tiles_record(array) for name, array in arrays.items()}
    tile['sha256'] = _i64__file_hash(file)
    if also_proof:
        proof = path / 'proof' / f'{index:06d}.npz'
        _i64_np.savez(proof, **arrays)
        tile['proof_sha256'] = _i64__file_hash(proof)
        manifest['recipe']['source_windows'][index] = tile['arrays']
    write_manifest(path, manifest)

class SurfaceNetworkTilesTests(_i64_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.surface_domain import load_surface_network_delivery as _i64_load_surface_network_delivery
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        cls.workspace = _i64_tempfile.TemporaryDirectory()
        cls.root = _i64_Path(cls.workspace.name)
        cls.expected = {}
        cls.prepared = {}
        for kind in BASELINES:
            cls.expected[kind] = _i64_load_surface_network_delivery(CONSUMER / kind)
            cls.prepared[kind] = _i64_prepare_surface_network_tiles(CONSUMER / kind, cls.root / kind, tile_cells=13)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def copy_store(self, directory, kind='baseline'):
        destination = _i64_Path(directory) / 'copy'
        _i64_shutil.copytree(self.prepared[kind], destination)
        return destination

    def test_three_final_consumer_packages_nondivisible_square_span_and_integrals(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import verify_all_tiles as _i64_verify_all_tiles
        for kind, (volume, area) in BASELINES.items():
            with self.subTest(kind=kind), forbid_generation():
                store = _i64_load_surface_network_tiles(self.prepared[kind])
                audit = _i64_verify_all_tiles(store)
                self.assertEqual(audit['unique_nodes'], 61 * 61)
                self.assertEqual(audit['tile_count'], 25)
                self.assertEqual(store.manifest['tiles'][-1]['bounds'], (52, 61, 52, 61))
                self.assertAlmostEqual(audit['integrals']['total_cut_m']['volume_m3'], volume, places=10)
                self.assertEqual(audit['integrals']['total_cut_m']['area_m2'], area)
                for field in audit['integrals']:
                    for quantity in ('volume_m3', 'area_m2'):
                        self.assertAlmostEqual(audit['integrals'][field][quantity], audit['tile_weighted_integrals'][field][quantity], places=10)

    def test_every_seam_and_query_order_match_source(self):
        from terrain_pipeline.surface_domain import GEOMETRY as _i64_GEOMETRY
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import slice_surface_network_tiles as _i64_slice_surface_network_tiles
        for kind in BASELINES:
            store = _i64_load_surface_network_tiles(self.prepared[kind])
            for start in reversed((0, 12, 25, 38, 51)):
                window = _i64_slice_surface_network_tiles(store, slice(start, min(start + 10, 61)), slice(0, 61))
                for name in _i64_GEOMETRY:
                    _i64_np.testing.assert_array_equal(window['arrays'][name], self.expected[kind]['geometry'][name][start:min(start + 10, 61)])
            left = _i64_slice_surface_network_tiles(store, slice(0, 61), slice(0, 40))
            right = _i64_slice_surface_network_tiles(store, slice(0, 61), slice(25, 61))
            for name in _i64_GEOMETRY:
                _i64_np.testing.assert_array_equal(left['arrays'][name][:, 25:], right['arrays'][name][:, :15])

    def test_load_and_query_are_lazy_only_intersecting_tile_and_proof(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        with _i64_patch.object(_i64_tiles, 'load_surface_network_delivery', side_effect=AssertionError('no full source load')), forbid_generation():
            with _i64_patch.object(_i64_tiles, '_read_arrays', wraps=_i64_tiles._read_arrays) as reads:
                store = _i64_load_surface_network_tiles(self.prepared['baseline'])
                self.assertEqual([call.args[0].name for call in reads.call_args_list], ['graph.npz'])
                reads.reset_mock()
                _i64_sample_surface_network_tiles(store, 1.0, 1.0)
                self.assertEqual([call.args[0].relative_to(store.path).as_posix() for call in reads.call_args_list], ['tiles/000000.npz', 'proof/000000.npz'])
                reads.reset_mock()
                _i64_sample_surface_network_tiles(store, 1.0, 1.0)
                self.assertEqual(reads.call_count, 0)
                self.assertEqual(set(store._cache), {0})

    def test_irrelevant_corrupt_tile_is_not_read_but_its_query_and_audit_reject(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        from terrain_pipeline.surface_domain import verify_all_tiles as _i64_verify_all_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            path = self.copy_store(directory)
            (path / 'tiles/000024.npz').write_bytes(b'corrupt')
            store = _i64_load_surface_network_tiles(path)
            _i64_sample_surface_network_tiles(store, 1.0, 1.0)
            with self.assertRaises(ValueError):
                _i64_sample_surface_network_tiles(store, 59.0, 59.0)
            with self.assertRaises(ValueError):
                _i64_verify_all_tiles(store)

    def test_cached_tile_and_cached_proof_are_rehashed_each_access(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        for filename in ('tiles/000000.npz', 'proof/000000.npz'):
            with self.subTest(filename=filename), _i64_tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)
                store = _i64_load_surface_network_tiles(path)
                _i64_sample_surface_network_tiles(store, 1.0, 1.0)
                target = path / filename
                data = bytearray(target.read_bytes())
                data[-1] ^= 1
                target.write_bytes(data)
                with self.assertRaises(ValueError):
                    _i64_sample_surface_network_tiles(store, 1.0, 1.0)

    def test_cache_eviction_and_oversize_tile_hard_refusal(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        store = _i64_load_surface_network_tiles(self.prepared['baseline'])
        size = sum((math_record['shape'][0] * math_record['shape'][1] * _i64_np.dtype(math_record['dtype']).itemsize for math_record in store.manifest['tiles'][0]['arrays'].values()))
        with _i64_patch.object(_i64_tiles, 'MAX_CACHE_BYTES', size):
            _i64_sample_surface_network_tiles(store, 1.0, 1.0)
            self.assertEqual(store._cache_bytes, size)
            _i64_sample_surface_network_tiles(store, 14.0, 1.0)
            self.assertEqual(set(store._cache), {1})
            self.assertLessEqual(store._cache_bytes, size)
        store = _i64_load_surface_network_tiles(self.prepared['baseline'])
        with _i64_patch.object(_i64_tiles, 'MAX_CACHE_BYTES', size - 1):
            with self.assertRaisesRegex(ValueError, 'cache bound'):
                _i64_sample_surface_network_tiles(store, 1.0, 1.0)
            self.assertEqual(store._cache_bytes, 0)

    def test_window_hard_limit_before_tile_read_or_allocation(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import slice_surface_network_tiles as _i64_slice_surface_network_tiles
        store = _i64_load_surface_network_tiles(self.prepared['baseline'])
        with _i64_patch.object(_i64_tiles, 'MAX_WINDOW_CELLS', 4), _i64_patch.object(store, '_tile', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError, 'window cell bound'):
                _i64_slice_surface_network_tiles(store, slice(0, 3), slice(0, 2))
        for part in (slice(None, 2), slice(-1, 2), slice(0, 62), slice(0, 2, 2), slice(1, 1), slice(True, 2)):
            with self.assertRaises(ValueError):
                _i64_slice_surface_network_tiles(store, part, slice(0, 1))

    def test_world_sample_and_inclusive_world_window(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        from terrain_pipeline.surface_domain import slice_surface_network_tiles_world as _i64_slice_surface_network_tiles_world
        store = _i64_load_surface_network_tiles(self.prepared['baseline'])
        window = _i64_slice_surface_network_tiles_world(store, (12.0, 12.0, 14.0, 14.0))
        self.assertEqual(window['arrays']['wet_mask'].shape, (3, 3))
        _i64_np.testing.assert_array_equal(window['arrays']['final_surface_m'], self.expected['baseline']['geometry']['final_surface_m'][12:15, 12:15])
        for coordinates in ((-0.1, 0.0), (61.0, 0.0), (float('nan'), 0.0)):
            with self.assertRaises(ValueError):
                _i64_sample_surface_network_tiles(store, *coordinates)

    def test_arrays_cannot_reenable_write_and_nested_manifest_cannot_mutate(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        store = _i64_load_surface_network_tiles(self.prepared['baseline'])
        window = _i64_sample_surface_network_tiles(store, 1.0, 1.0)
        for array in (*store.centerline.values(), *window['arrays'].values(), *store._cache[0].values()):
            with self.assertRaises(ValueError):
                array.flags.writeable = True
            with self.assertRaises(ValueError):
                array.flat[0] = 0
        with self.assertRaises(TypeError):
            store.manifest['recipe']['grid']['origin_x_m'] = 1
        with self.assertRaises(TypeError):
            store.manifest['tiles'][0]['arrays']['wet_mask']['dtype'] = '<f8'
        with self.assertRaises(TypeError):
            store.manifest['recipe']['grid']['shape_zx'][0] = 1

    def test_source_directory_unavailable_still_load_query_and_full_audit(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        from terrain_pipeline.surface_domain import verify_all_tiles as _i64_verify_all_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            source = _i64_Path(directory) / 'source'
            _i64_shutil.copytree(CONSUMER / 'baseline', source)
            destination = _i64_Path(directory) / 'tiles'
            _i64_prepare_surface_network_tiles(source, destination, tile_cells=17)
            source.rename(_i64_Path(directory) / 'source-unavailable')
            store = _i64_load_surface_network_tiles(destination)
            _i64_sample_surface_network_tiles(store, 30.0, 30.0)
            self.assertTrue(_i64_verify_all_tiles(store)['source_replayed'])

    def test_cancel_and_budget_pause_resume_revalidate_and_do_not_overwrite(self):
        from terrain_pipeline.surface_domain import _file_hash as _i64__file_hash
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        from terrain_pipeline.surface_domain import verify_all_tiles as _i64_verify_all_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            destination = _i64_Path(directory) / 'tiles'
            self.assertIs(_i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, max_tiles=1), False)
            staging = destination.with_name('tiles.staging')
            before = _i64__file_hash(staging / 'tiles/000000.npz')
            with self.assertRaises(ValueError):
                _i64_load_surface_network_tiles(staging)
            self.assertIs(_i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True, cancel=lambda: True), False)
            self.assertEqual(before, _i64__file_hash(staging / 'tiles/000000.npz'))
            self.assertEqual(_i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True), destination)
            self.assertEqual(before, _i64__file_hash(destination / 'tiles/000000.npz'))
            self.assertTrue(_i64_verify_all_tiles(_i64_load_surface_network_tiles(destination))['verified'])
            with self.assertRaises(FileExistsError):
                _i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination)

    def test_resume_rejects_changed_source_recipe_and_written_tile_damage(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            destination = _i64_Path(directory) / 'tiles'
            _i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, max_tiles=1)
            for source, span in ((CONSUMER / 'valley', 13), (CONSUMER / 'baseline', 17)):
                with self.assertRaisesRegex(ValueError, 'resume source or recipe changed'):
                    _i64_prepare_surface_network_tiles(source, destination, tile_cells=span, resume=True)
            staging = destination.with_name('tiles.staging')
            (staging / 'tiles/000000.npz').write_bytes(b'damage')
            with self.assertRaisesRegex(ValueError, 'completed tile damaged'):
                _i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True, cancel=lambda: True)
            self.assertFalse(destination.exists())
            self.assertFalse((staging / 'manifest.json').exists())
            self.assertEqual((staging / 'tiles/000000.npz').read_bytes(), b'damage')

    def test_resume_rejects_staged_source_damage_and_completed_proof_damage(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        for relative in ('source/hydro.npz', 'proof/000000.npz'):
            with self.subTest(relative=relative), _i64_tempfile.TemporaryDirectory() as directory:
                destination = _i64_Path(directory) / 'tiles'
                _i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, max_tiles=1)
                staging = destination.with_name('tiles.staging')
                (staging / relative).write_bytes(b'damage')
                with self.assertRaises((ValueError, OSError, _i64_zipfile.BadZipFile)):
                    _i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True)
                self.assertFalse(destination.exists())

    def test_cancel_immediately_before_and_after_manifest_commit_never_publishes(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        for point in (25, 26, 27):
            with self.subTest(point=point), _i64_tempfile.TemporaryDirectory() as directory:
                destination = _i64_Path(directory) / 'tiles'
                calls = 0

                def cancel():
                    nonlocal calls
                    calls += 1
                    return calls > point
                self.assertIs(_i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, cancel=cancel), False)
                self.assertFalse(destination.exists())
                self.assertFalse((destination.with_name('tiles.staging') / 'manifest.json').exists())
                self.assertEqual(_i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True), destination)

    def test_missing_duplicate_and_changed_ranges_rejected_at_load(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        for operation in ('missing', 'duplicate', 'range'):
            with self.subTest(operation=operation), _i64_tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)
                manifest = _i64_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
                if operation == 'missing':
                    manifest['tiles'].pop()
                elif operation == 'duplicate':
                    manifest['tiles'][1] = manifest['tiles'][0]
                else:
                    manifest['tiles'][0]['bounds'][1] -= 1
                write_manifest(path, manifest)
                with self.assertRaises(ValueError):
                    _i64_load_surface_network_tiles(path)

    def test_rehashed_stage_new_wet_and_disconnected_wet_reject_on_query(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        for operation in ('stage', 'new-wet', 'disconnected-wet'):
            with self.subTest(operation=operation), _i64_tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)

                def change(arrays):
                    if operation == 'stage':
                        row, column = _i64_np.argwhere(arrays['wet_mask'])[0]
                        arrays['water_surface_m'][row, column] += 2.0
                    else:
                        row, column = (1, 1)
                        if operation == 'new-wet':
                            neighbors = _i64_np.zeros_like(arrays['wet_mask'])
                            neighbors[1:] |= arrays['wet_mask'][:-1]
                            neighbors[:-1] |= arrays['wet_mask'][1:]
                            neighbors[:, 1:] |= arrays['wet_mask'][:, :-1]
                            neighbors[:, :-1] |= arrays['wet_mask'][:, 1:]
                            row, column = _i64_np.argwhere(neighbors & ~arrays['wet_mask'])[0]
                        arrays['wet_mask'][row, column] = True
                        arrays['water_surface_m'][row, column] = arrays['final_surface_m'][row, column] + 0.1
                index = 0 if operation == 'disconnected-wet' else 1
                mutate_tile(path, index, change)
                with self.assertRaisesRegex(ValueError, 'validated source window'):
                    _i64_sample_surface_network_tiles(_i64_load_surface_network_tiles(path), 14.0 if index else 1.0, 1.0)

    def test_semantic_gate_rejects_depth_cut_domain_protection_even_with_rehashed_window_proof(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        for operation in ('depth', 'cut', 'domain', 'protected', 'stage-jump'):
            with self.subTest(operation=operation), _i64_tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)

                def change(arrays):
                    row, column = _i64_np.argwhere(arrays['wet_mask'])[0]
                    if operation == 'depth':
                        arrays['water_surface_m'][row, column] = arrays['final_surface_m'][row, column] + 0.001
                    elif operation == 'cut':
                        arrays['final_surface_m'][row, column] -= 5.0
                        arrays['bed_cut_m'][:] = arrays['valley_surface_m'] - arrays['final_surface_m']
                        arrays['total_cut_m'][:] = arrays['source_surface_m'] - arrays['final_surface_m']
                    elif operation == 'stage-jump':
                        arrays['water_surface_m'][row, column] += 2.0
                    else:
                        arrays[operation + '_mask'][row, column] = operation == 'protected'
                mutate_tile(path, 1, change, also_proof=True)
                with self.assertRaises(ValueError):
                    _i64_sample_surface_network_tiles(_i64_load_surface_network_tiles(path), 14.0, 1.0)

    def test_shared_seam_mismatch_rejects_query_and_audit(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import slice_surface_network_tiles as _i64_slice_surface_network_tiles
        from terrain_pipeline.surface_domain import verify_all_tiles as _i64_verify_all_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            path = self.copy_store(directory)

            def change(arrays):
                for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m'):
                    arrays[name][1, 0] += 0.1
            mutate_tile(path, 1, change, also_proof=True)
            store = _i64_load_surface_network_tiles(path)
            with self.assertRaisesRegex(ValueError, 'seam mismatch'):
                _i64_slice_surface_network_tiles(store, slice(1, 2), slice(13, 14))
            with self.assertRaises(ValueError):
                _i64_verify_all_tiles(store)

    def test_npz_aggregate_uncompressed_bound_and_header_preflight(self):
        with _i64_tempfile.TemporaryDirectory() as directory:
            path = _i64_Path(directory) / 'arrays.npz'
            arrays = {'first': _i64_np.zeros(1000), 'second': _i64_np.zeros(1000)}
            records = {name: _i64_tiles._surface_network_tiles_record(array) for name, array in arrays.items()}
            _i64_np.savez_compressed(path, **arrays)
            with self.assertRaisesRegex(ValueError, 'total uncompressed'):
                _i64_tiles._read_arrays(path, records, limit=16100)
            _i64_np.savez(path, **arrays)
            records['first']['shape'] = [999]
            with self.assertRaisesRegex(ValueError, 'header mismatch'):
                _i64_tiles._read_arrays(path, records)

    def test_graph_integer_indices_and_topology_reject_after_rehash(self):
        from terrain_pipeline.artifacts.contracts import digest as _i64_digest
        from terrain_pipeline.surface_domain import _file_hash as _i64__file_hash
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        for operation in ('float', 'order'):
            with self.subTest(operation=operation), _i64_tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)
                manifest = _i64_json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
                with _i64_np.load(path / 'graph.npz') as archive:
                    arrays = {name: archive[name] for name in archive.files}
                if operation == 'float':
                    arrays['receiver'] = arrays['receiver'].astype(float)
                else:
                    arrays['order'] = arrays['order'][::-1]
                _i64_np.savez(path / 'graph.npz', **arrays)
                records = {name: _i64_tiles._surface_network_tiles_record(array) for name, array in arrays.items()}
                manifest['graph']['arrays'] = records
                manifest['graph']['sha256'] = _i64__file_hash(path / 'graph.npz')
                manifest['recipe']['source_manifest']['arrays'].update(records)
                source = manifest['recipe']['source_manifest']
                source['content_id'] = _i64_digest({name: value for name, value in source.items() if name != 'content_id'})
                manifest['recipe']['source_content_id'] = source['content_id']
                write_manifest(path, manifest)
                with self.assertRaises(ValueError):
                    _i64_load_surface_network_tiles(path)

    def test_invalid_span_budget_and_resume_reject_before_source_load(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            destination = _i64_Path(directory) / 'tiles'
            with _i64_patch.object(_i64_tiles, 'load_surface_network_delivery', side_effect=AssertionError('must not load')):
                for span in (True, 0, -1, 256, (13, 17), 13.0):
                    with self.assertRaises(ValueError):
                        _i64_prepare_surface_network_tiles('unused', destination, tile_cells=span)
                for options in ({'max_tiles': 0}, {'max_tiles': True}, {'resume': 1}, {'cancel': 1}):
                    with self.assertRaises(ValueError):
                        _i64_prepare_surface_network_tiles('unused', destination, **options)
            self.assertFalse(destination.with_name('tiles.staging').exists())

    def test_copy_only_declared_source_files_not_extra_files_or_directories(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            source = _i64_Path(directory) / 'source'
            _i64_shutil.copytree(CONSUMER / 'baseline', source)
            (source / 'undeclared.bin').write_bytes(b'must not be copied')
            (source / 'extras').mkdir()
            (source / 'extras/nested.bin').write_bytes(b'must not be copied')
            destination = _i64_Path(directory) / 'tiles'
            with self.assertRaisesRegex(ValueError, 'directory layout'):
                _i64_prepare_surface_network_tiles(source, destination, tile_cells=13, max_tiles=1)
            self.assertFalse(destination.exists())
            self.assertFalse((destination.with_name('tiles.staging') / 'manifest.json').exists())
            staging = destination.with_name('tiles.staging')
            staging.mkdir(exist_ok=True)
            manifest = _i64_json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
            copied = _i64_tiles._source_files(source, staging, manifest)
            self.assertFalse((copied / 'undeclared.bin').exists())
            self.assertFalse((copied / 'extras').exists())
            self.assertEqual({file.relative_to(copied).as_posix() for file in copied.rglob('*') if file.is_file()}, _i64_tiles.SOURCE_FILES)

    def test_entire_window_proof_rehash_is_not_publisher_authentication_full_audit_rejects(self):
        from terrain_pipeline.surface_domain import load_surface_network_tiles as _i64_load_surface_network_tiles
        from terrain_pipeline.surface_domain import sample_surface_network_tiles as _i64_sample_surface_network_tiles
        from terrain_pipeline.surface_domain import verify_all_tiles as _i64_verify_all_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            path = self.copy_store(directory)

            def change(arrays):
                arrays['wet_mask'][1, 1] = True
                arrays['water_surface_m'][1, 1] = arrays['final_surface_m'][1, 1] + 0.1
            mutate_tile(path, 0, change, also_proof=True)
            store = _i64_load_surface_network_tiles(path)
            self.assertTrue(_i64_sample_surface_network_tiles(store, 1.0, 1.0)['arrays']['wet_mask'][0, 0])
            with self.assertRaisesRegex(ValueError, 'validated source'):
                _i64_verify_all_tiles(store)

    def test_exception_leaves_unpublished_staging_and_owner_unlocks(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            destination = _i64_Path(directory) / 'tiles'

            def cancel():
                raise RuntimeError('caller cancellation failure')
            with self.assertRaisesRegex(RuntimeError, 'caller cancellation failure'):
                _i64_prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, cancel=cancel)
            staging = destination.with_name('tiles.staging')
            self.assertFalse(destination.exists())
            self.assertFalse((staging / '.prepare.lock').exists())
            self.assertFalse((staging / 'manifest.json').exists())

    def test_destination_cannot_be_inside_immutable_source(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            source = _i64_Path(directory) / 'source'
            source.mkdir()
            with self.assertRaises(ValueError):
                _i64_prepare_surface_network_tiles(source, source / 'tiles')
            self.assertEqual(list(source.iterdir()), [])

class SurfaceNetworkTilesLockTests(_i64_unittest.TestCase):

    def test_failed_contender_does_not_unlock_owner_or_admit_third_call(self):
        from terrain_pipeline.surface_domain import prepare_surface_network_tiles as _i64_prepare_surface_network_tiles
        with _i64_tempfile.TemporaryDirectory() as directory:
            destination = _i64_Path(directory) / 'tiles'
            staging = destination.with_name(destination.name + '.staging')

            def owner(*args, **kwargs):
                with self.assertRaises(FileExistsError):
                    _i64_prepare_surface_network_tiles('unused', destination)
                self.assertTrue((staging / '.prepare.lock').exists())
                with self.assertRaises(FileExistsError):
                    _i64_prepare_surface_network_tiles('unused', destination)
                return False
            with _i64_patch('terrain_pipeline.surface_domain._prepare_unlocked', side_effect=owner) as work:
                self.assertIs(_i64_prepare_surface_network_tiles('unused', destination), False)
                self.assertEqual(work.call_count, 1)
            self.assertFalse((staging / '.prepare.lock').exists())
TEST_SURFACE_VARIABLE_STORAGE_SOURCE = _i65_Path(__file__).resolve().parents[1] / 'verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/pulse.npz'

def _test_surface_variable_storage_propagation_forcing(*, pulse=False, raised=False):
    values = _test_surface_multidomain_dynamic_forcing(steps=80, pulse=pulse, raised=raised)
    values['conductance_m2_s'][:] = 1.0
    return values

@_i65_lru_cache(maxsize=1)
def _test_surface_variable_storage_fixture():
    source = _i65_forest.load_surface_multidomain_dynamic(TEST_SURFACE_VARIABLE_STORAGE_SOURCE)
    base = _i65_storage.prepare_surface_variable_storage(source, **_test_surface_variable_storage_propagation_forcing())
    pulse = _i65_storage.prepare_surface_variable_storage(source, **_test_surface_variable_storage_propagation_forcing(pulse=True))
    raised = _i65_storage.prepare_surface_variable_storage(source, **_test_surface_variable_storage_propagation_forcing(pulse=True, raised=True))
    return (source, base, pulse, raised)

def rehashed(record):
    record.pop('identity_sha256', None)
    record['identity_sha256'] = _i65_mosaic._identity(record)
    return record

def static_disabled(stack):
    generation_disabled(stack)
    for name in ('_geometry', '_knots', '_advance', 'prepare_surface_variable_storage'):
        stack.enter_context(_i65_patch.object(_i65_storage, name, side_effect=AssertionError('generation on read')))

class SurfaceVariableStorageTests(_i65_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source, cls.base, cls.pulse, cls.raised = _test_surface_variable_storage_fixture()

    def test_source_triangles_and_nonconstant_storage(self):
        result = self.base
        self.assertEqual(result['support_offsets'][-1], 676 * 6)
        self.assertEqual(len(result['source']['node_keys']), 16)
        self.assertEqual(len(result['source']['edges']), 14)
        self.assertEqual(result['source']['dynamic']['inputs']['boundary_mask'].sum(), 2)
        self.assertAlmostEqual(result['storage_m3'][0].sum(), 224.5721879136545)
        self.assertNotAlmostEqual(result['storage_m3'][0].sum(), 322.0)
        for index in range(16):
            start, stop = result['support_offsets'][index:index + 2]
            beds = result['support_bed_m'][start:stop]
            weights = result['support_weight_m2'][start:stop]
            first, last = result['knot_offsets'][index:index + 2]
            _i65_np.testing.assert_allclose(result['knot_volume_m3'][first:last], [_i65_storage.volume(stage, beds, weights) for stage in result['knot_stage_m'][first:last]])
            self.assertEqual(_i65_storage._invert(0.0, beds, weights), beds.min())
            for amount in (0.1, 1.0, 10.0):
                self.assertAlmostEqual(_i65_storage.volume(_i65_storage._invert(amount, beds, weights), beds, weights), amount)

    def test_ledger_and_domain_independence(self):
        raised = self.raised
        _i65_np.testing.assert_array_equal(self.pulse['stage_m'][:, :8], raised['stage_m'][:, :8])
        _i65_np.testing.assert_array_equal(self.pulse['qedges_m3_s'][:, :7], raised['qedges_m3_s'][:, :7])
        self.assertTrue(_i65_np.any(raised['qedges_m3_s'][:, 7:] < 0))
        _i65_np.testing.assert_allclose(raised['ledger_m3'], raised['domain_ledger_m3'].sum(axis=1), atol=1e-12)
        self.assertLess(_i65_np.abs(raised['ledger_m3'][:, 5]).max(), 1e-10)
        self.assertEqual(self.pulse['committed_steps'], 80)
        self.assertEqual(self.pulse['time_s'][-1], 8.0)
        self.assertGreater(abs(self.pulse['stage_m'][-1, 6] - self.base['stage_m'][-1, 6]), 1e-12)

    def test_failed_cancelled_and_negative_storage(self):
        from terrain_pipeline.surface_identity import _plain as _i65__merged_mosaic__plain
        values = _test_surface_multidomain_dynamic_forcing()
        values['tailwater_m'][2:] = 100.0
        failed = _i65_storage.prepare_surface_variable_storage(self.source, **values)
        self.assertEqual((failed['status'], failed['committed_steps']), ('failed', 1))
        values = _test_surface_multidomain_dynamic_forcing()
        values['local_q_m3_s'][0, 0] = -1000000.0
        negative = _i65_storage.prepare_surface_variable_storage(self.source, **values)
        self.assertEqual((negative['status'], negative['committed_steps'], negative['failed_step']['reason']), ('failed', 0, 'negative_storage'))
        calls = iter([True])
        cancelled = _i65_storage.prepare_surface_variable_storage(self.source, **_test_surface_multidomain_dynamic_forcing(), cancel=lambda: next(calls))
        self.assertEqual((cancelled['status'], cancelled['committed_steps']), ('cancelled', 0))
        with _i65_ExitStack() as stack:
            static_disabled(stack)
            for record in (failed, negative, cancelled):
                _i65_storage.validate_surface_variable_storage(record)
                _i65_storage.query_surface_variable_storage(record)
        for record in (failed, cancelled):
            changed = _i65_deepcopy(_i65__merged_mosaic__plain(record))
            changed['committed_steps'] += 1
            with self.assertRaises(ValueError):
                _i65_storage.validate_surface_variable_storage(rehashed(changed))
        changed = _i65_deepcopy(_i65__merged_mosaic__plain(failed))
        changed['failed_step']['reason'] = 'negative_storage'
        with self.assertRaises(ValueError):
            _i65_storage.validate_surface_variable_storage(rehashed(changed))
        with self.assertRaises(ValueError):
            _i65_storage.prepare_surface_variable_storage(self.source, **{**_test_surface_multidomain_dynamic_forcing(), 'dt_s': 1000000.0})

    def test_static_read_and_rehashed_forgery(self):
        from terrain_pipeline.surface_identity import _plain as _i65__merged_mosaic__plain
        with _i65_tempfile.TemporaryDirectory() as directory:
            path = _i65_Path(directory) / 'storage.npz'
            _i65_storage.save_surface_variable_storage(self.base, path)
            with self.assertRaises(FileExistsError):
                _i65_storage.save_surface_variable_storage(self.base, path)
            with _i65_ExitStack() as stack:
                static_disabled(stack)
                _i65_storage.validate_surface_variable_storage(self.base)
                loaded = _i65_storage.load_surface_variable_storage(path)
                query = _i65_storage.query_surface_variable_storage(loaded, state_index=1)
            self.assertEqual(query['time_s'], 0.1)
            self.assertEqual(loaded['identity_sha256'], self.base['identity_sha256'])
        for name in ('support_bed_m', 'support_weight_m2', 'knot_volume_m3', 'stage_m', 'storage_m3', 'qedges_m3_s', 'ledger_m3', 'domain_ledger_m3'):
            changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
            changed[name].flat[0] += 1
            changed.pop('identity_sha256')
            changed['identity_sha256'] = _i65_mosaic._identity(changed)
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i65_storage.validate_surface_variable_storage(changed)

    def test_resources_before_geometry_or_source_validation(self):
        from terrain_pipeline.surface_identity import _plain as _i65__merged_mosaic__plain
        for resources in (_i65_storage.StorageResources(max_work=1), _i65_storage.StorageResources(max_wet_cells=1), _i65_storage.StorageResources(max_retained_bytes=1), _i65_storage.StorageResources(max_working_bytes=1)):
            with _i65_patch.object(_i65_storage, '_surface_variable_storage_geometry', side_effect=AssertionError('geometry before budget')), _i65_patch.object(_i65_forest, 'validate_surface_multidomain_dynamic', side_effect=AssertionError('source validation before budget')):
                with self.assertRaises(ValueError):
                    _i65_storage.prepare_surface_variable_storage(self.source, **_test_surface_multidomain_dynamic_forcing(), resources=resources)
                changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
                changed['resources'] = vars(resources)
                with self.assertRaises(ValueError):
                    _i65_storage.validate_surface_variable_storage(rehashed(changed))

    def test_scalar_dtype_stage_and_prefix_rejections(self):
        from terrain_pipeline.surface_identity import _plain as _i65__merged_mosaic__plain
        for name, value in (('committed_steps', 80.0), ('committed_steps', True), ('dt_s', True), ('max_depth_m', 4), ('natural_outlets_certified', 0), ('full_dynamic_wave_prepared', 0)):
            changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
            changed[name] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                _i65_storage.validate_surface_variable_storage(rehashed(changed))
        for name in ('storage_m3', 'support_offsets', 'support_owner', 'stage_m'):
            changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
            changed[name] = changed[name].astype(_i65_np.float32)
            with self.subTest(name=name), self.assertRaises(ValueError):
                _i65_storage.validate_surface_variable_storage(rehashed(changed))
        for amount in (-1.0, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                _i65_storage._invert(amount, _i65_np.array([0.0]), _i65_np.array([1.0]))
        for value in (True, _i65_np.bool_(True), _i65_np.float64(0.1), '0.1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _i65_storage.prepare_surface_variable_storage(self.source, **{**_test_surface_multidomain_dynamic_forcing(), 'dt_s': value})
        changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
        changed['storage_m3'][1, 0] = -1e-15
        with self.assertRaises(ValueError):
            _i65_storage.validate_surface_variable_storage(rehashed(changed))
        changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
        changed['stage_m'][1, 0] = -100.0
        with self.assertRaises(ValueError):
            _i65_storage.validate_surface_variable_storage(rehashed(changed))
        changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
        minimum = changed['support_bed_m'][:changed['support_offsets'][1]].min()
        changed['stage_m'][1, 0] = minimum + 1e-14
        changed['storage_m3'][1, 0] = 0.0
        with self.assertRaises(ValueError):
            _i65_storage.validate_surface_variable_storage(rehashed(changed))
        for name in ('local_q_m3_s', 'tailwater_m', 'stage_m', 'ledger_m3'):
            changed = _i65_deepcopy(_i65__merged_mosaic__plain(self.base))
            changed[name].flat[0] = float('inf')
            with self.subTest(nonfinite=name), self.assertRaises(ValueError):
                _i65_storage.validate_surface_variable_storage(changed)
        with self.assertRaises(ValueError):
            _i65_storage.query_surface_variable_storage(self.base, state_index=True)

    def test_strict_archive_rejections(self):
        with _i65_tempfile.TemporaryDirectory() as directory:
            original = _i65_Path(directory) / 'original.npz'
            _i65_storage.save_surface_variable_storage(self.base, original)
            with _i65_zipfile.ZipFile(original) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for mutation in ('version_float', 'version_bool', 'shape_float', 'shape_bool', 'header_bool', 'header_float', 'fortran_int', 'duplicate_header', 'unused'):
                payloads = dict(members)
                manifest = _i65_json.loads(payloads['manifest.json'])
                reference = manifest['tree']['support_bed_m']
                if mutation.startswith('version'):
                    manifest['format_version'] = True if mutation == 'version_bool' else 1.0
                elif mutation.startswith('shape'):
                    reference['shape'][0] = True if mutation == 'shape_bool' else float(reference['shape'][0])
                elif mutation == 'unused':
                    payloads['array_unused.npy'] = payloads[reference['$array']]
                else:
                    name = reference['$array']
                    raw = payloads[name]
                    header_length = int.from_bytes(raw[8:10], 'little')
                    header = raw[10:10 + header_length].decode('latin1').strip()
                    if mutation == 'fortran_int':
                        header = header.replace('False', '0')
                    elif mutation == 'duplicate_header':
                        header = header.replace('{', "{'fortran_order': False, ", 1)
                    else:
                        size = reference['shape'][0]
                        header = header.replace(f'({size},)', '(True,)' if mutation == 'header_bool' else f'({size}.0,)')
                    encoded = (header + '\n').encode('latin1')
                    payloads[name] = raw[:8] + len(encoded).to_bytes(2, 'little') + encoded + raw[10 + header_length:]
                manifest['tree_sha256'] = _i65_mosaic._identity(manifest['tree'])
                payloads['manifest.json'] = _i65_mosaic._surface_fine_mosaic_json(manifest).encode('utf8')
                path = _i65_Path(directory) / (mutation + '.npz')
                with _i65_zipfile.ZipFile(path, 'w') as archive:
                    for name, payload in payloads.items():
                        archive.writestr(name, payload)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    _i65_storage.load_surface_variable_storage(path)

    def test_atomic_race_does_not_overwrite_or_leave_temporary(self):
        with _i65_tempfile.TemporaryDirectory() as directory:
            destination = _i65_Path(directory) / 'race.npz'
            original_link = _i65_storage.os.link

            def race(source, target):
                _i65_Path(target).write_bytes(b'other writer')
                return original_link(source, target)
            with _i65_patch.object(_i65_storage.os, 'link', side_effect=race), self.assertRaises(FileExistsError):
                _i65_storage.save_surface_variable_storage(self.base, destination)
            self.assertEqual(destination.read_bytes(), b'other writer')
            self.assertEqual(list(_i65_Path(directory).iterdir()), [destination])
