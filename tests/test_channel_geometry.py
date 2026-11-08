"""Consolidated test_channel_geometry implementations; numeric expressions preserved."""
from __future__ import annotations
import tempfile as _i1_tempfile
import unittest as _i1_unittest
from pathlib import Path as _i1_Path
import numpy as _i1_np
import tempfile as _i0_tempfile
import unittest as _i0_unittest
from pathlib import Path as _i0_Path
import json as _i0_json
import numpy as _i0_np
import unittest as _i2_unittest
import numpy as _i2_np
import unittest as _i3_unittest
import numpy as _i3_np
import unittest as _i4_unittest
from copy import deepcopy as _i4_deepcopy
from pathlib import Path as _i4_Path
import tempfile as _i4_tempfile
import numpy as _i4_np
import json as _i5_json
import tempfile as _i5_tempfile
import unittest as _i5_unittest
from pathlib import Path as _i5_Path
from unittest.mock import patch as _i5_patch
import numpy as _i5_np
import unittest as _i6_unittest
import numpy as _i6_np
import unittest as _i7_unittest
from types import SimpleNamespace as _i7_SimpleNamespace
import numpy as _i7_np
import unittest as _i8_unittest
from dataclasses import replace as _i8_replace
import numpy as _i8_np
import unittest as _i9_unittest
import numpy as _i9_np
import unittest as _i10_unittest
from unittest.mock import patch as _i10_patch
import numpy as _i10_np
import unittest as _i11_unittest
from collections import Counter as _i11_Counter
from types import SimpleNamespace as _i11_SimpleNamespace
from unittest.mock import patch as _i11_patch
import numpy as _i11_np
from scipy.sparse import coo_matrix as _i11_coo_matrix
import tempfile as _i16_tempfile
import unittest as _i16_unittest
from copy import deepcopy as _i16_deepcopy
from pathlib import Path as _i16_Path
import numpy as _i16_np
import tempfile as _i15_tempfile
import unittest as _i15_unittest
from pathlib import Path as _i15_Path
import numpy as _i15_np
import tempfile as _i12_tempfile
import unittest as _i12_unittest
from copy import deepcopy as _i12_deepcopy
from pathlib import Path as _i12_Path
from unittest.mock import patch as _i12_patch
import numpy as _i12_np
import unittest as _i13_unittest
import numpy as _i13_np
import os as _i14_os
import json as _i14_json
from pathlib import Path as _i14_Path
import numpy as _i14_np
import pytest as _i14_pytest
import terrain_pipeline.channel_geometry as _i14_sampler
import copy as _i14_copy
import tempfile as _i17_tempfile
import unittest as _i17_unittest
from copy import deepcopy as _i17_deepcopy
from pathlib import Path as _i17_Path
from unittest.mock import patch as _i17_patch
import numpy as _i17_np
import tempfile as _i18_tempfile
import unittest as _i18_unittest
from copy import deepcopy as _i18_deepcopy
from pathlib import Path as _i18_Path
import numpy as _i18_np
import unittest as _i19_unittest
from unittest.mock import patch as _i19_patch
import numpy as _i19_np
import terrain_pipeline.lake as _i19_geometry
from terrain_pipeline import channel_geometry as _i19_fine
from terrain_pipeline import channel_geometry as _i19_storage
from tools.verify_mountain_rainfall import load_source as _i19_load_source
from copy import deepcopy as _i20_deepcopy
from pathlib import Path as _i20_Path
import unittest as _i20_unittest
import tempfile as _i20_tempfile
from unittest.mock import patch as _i20_patch
import numpy as _i20_np
from terrain_pipeline import channel_geometry as _i20_storage
import unittest as _i21_unittest
import numpy as _i21_np
from copy import deepcopy as _i22_deepcopy
from dataclasses import asdict as _i22_asdict
from dataclasses import replace as _i22_replace
import math as _i22_math
from pathlib import Path as _i22_Path
import tempfile as _i22_tempfile
import unittest as _i22_unittest
from unittest.mock import patch as _i22_patch
import numpy as _i22_np
import numpy as _i23_np
import json as _i24_json
from pathlib import Path as _i24_Path
import tempfile as _i24_tempfile
import unittest as _i24_unittest
from unittest.mock import patch as _i24_patch
import numpy as _i24_np
import unittest as _i25_unittest
import numpy as _i25_np
import numpy as _i26_np
import pytest as _i26_pytest
import tempfile as _i27_tempfile
import unittest as _i27_unittest
from pathlib import Path as _i27_Path
from unittest.mock import patch as _i27_patch
import numpy as _i27_np
from copy import deepcopy as _i28_deepcopy
import hashlib as _i28_hashlib
from pathlib import Path as _i28_Path
import tempfile as _i28_tempfile
import unittest as _i28_unittest
import numpy as _i28_np
import unittest as _i29_unittest
import numpy as _i29_np
from terrain_pipeline import channel_geometry as _i29_v2
from terrain_pipeline import channel_geometry as _i29_v3
from copy import deepcopy as _i30_deepcopy
import inspect as _i30_inspect
import unittest as _i30_unittest
import numpy as _i30_np
from tools import export_td_watershed_inspection as _i30_exporter
import copy as _i31_copy
import json as _i31_json
import tempfile as _i31_tempfile
import unittest as _i31_unittest
from pathlib import Path as _i31_Path
from copy import deepcopy as _i32_deepcopy
import hashlib as _i32_hashlib
import json as _i32_json
from pathlib import Path as _i32_Path
import tempfile as _i32_tempfile
import unittest as _i32_unittest
from unittest.mock import patch as _i32_patch
import numpy as _i32_np
import copy as _i33_copy
import tempfile as _i33_tempfile
from pathlib import Path as _i33_Path
import unittest as _i33_unittest
import numpy as _i33_np
import unittest as _i34_unittest
import numpy as _i34_np
import tempfile as _i35_tempfile
import unittest as _i35_unittest
from pathlib import Path as _i35_Path
import numpy as _i35_np
from tests.test_surface_hydraulics import confluence_plan as _x0_confluence_plan
from tests.test_surface_hydraulics import confluence_plan as _x1_confluence_plan
from tests.test_surface_hydraulics import confluence_plan as _x2_confluence_plan
CATEGORY = 'B'

def synthetic_plan(width=4.0, cap=10.0):
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i1_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i1_plan_channel
    height = _i1_np.full((5, 5), 10.0)
    outlet = _i1_np.ones((5, 5), dtype=bool)
    receiver = _i1_np.full(25, -1, dtype=_i1_np.int64)
    for donor, target in ((1, 6), (3, 8), (6, 11), (11, 12), (8, 12), (12, 17), (17, 22)):
        receiver[donor] = target
        outlet.flat[donor] = False
    order = _i1_np.array([cell for cell in range(25) if outlet.flat[cell]] + [17, 12, 11, 6, 8, 1, 3], dtype=_i1_np.int64)
    q = _i1_np.full((5, 5), 0.01)
    q.flat[[1, 3, 6, 8, 11, 12, 17, 22]] = 0.1
    return _i1_plan_channel(height, receiver, order, outlet, q, 10.0, 10.0, 0.0, 0.0, 0.0, 'synthetic', _i1_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=width, min_width_m=width, max_width_m=width, reference_depth_m=1.0, min_depth_m=1.0, max_depth_m=1.0, max_cut_m=cap))

class LocalChannelSectionsTests(_i1_unittest.TestCase):

    def test_enclosed_segment_has_zero_outer_cut(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i1_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i1_evaluate_sections
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i1_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i1_plan_channel
        height = _i1_np.full((7, 7), 10.0)
        outlet = _i1_np.ones((7, 7), dtype=bool)
        receiver = _i1_np.full(49, -1, dtype=_i1_np.int64)
        receiver[3 * 7 + 2] = 3 * 7 + 3
        outlet[3, 2] = False
        q = _i1_np.full((7, 7), 0.01)
        q[3, 2:4] = 0.1
        order = _i1_np.array([cell for cell in range(49) if outlet.flat[cell]] + [3 * 7 + 2])
        plan = _i1_plan_channel(height, receiver, order, outlet, q, 10.0, 10.0, 0.0, 0.0, 0.0, 'enclosed', _i1_ChannelRecipe(reference_width_m=4.0, min_width_m=4.0, max_width_m=4.0))
        section = _i1_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (61, 61), _i1_np.zeros((61, 61), bool), _i1_SectionRecipe())
        cut = section['arrays']['required_cut_m']
        self.assertFalse(section['summary']['requires_shared_fine_extension'])
        self.assertFalse(_i1_np.any(cut[0, :]) or _i1_np.any(cut[-1, :]) or _i1_np.any(cut[:, 0]) or _i1_np.any(cut[:, -1]))

    def test_adjacent_windows_match_whole_grid_and_shared_nodes(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i1_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i1_evaluate_sections
        plan = synthetic_plan()
        recipe = _i1_SectionRecipe(max_local_cut_m=10.0)
        whole = _i1_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (41, 41), _i1_np.zeros((41, 41), bool), recipe)
        left = _i1_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (41, 21), _i1_np.zeros((41, 21), bool), recipe)
        right = _i1_evaluate_sections(plan, 20.0, 0.0, 1.0, 1.0, (41, 21), _i1_np.zeros((41, 21), bool), recipe)
        for key in ('source_surface_m', 'required_cut_m', 'bounded_surface_m'):
            _i1_np.testing.assert_array_equal(left['arrays'][key], whole['arrays'][key][:, :21])
            _i1_np.testing.assert_array_equal(right['arrays'][key], whole['arrays'][key][:, 20:])
            _i1_np.testing.assert_array_equal(left['arrays'][key][:, -1], right['arrays'][key][:, 0])
        self.assertAlmostEqual(left['summary']['actual_cut_volume_m3'] + right['summary']['actual_cut_volume_m3'], whole['summary']['actual_cut_volume_m3'])

    def test_protection_budget_and_clipped_edge_are_diagnostic(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i1_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i1_evaluate_sections
        plan = synthetic_plan(cap=0.1)
        protect = _i1_np.zeros((21, 21), bool)
        protect[10, 10] = True
        section = _i1_evaluate_sections(plan, 10.0, 10.0, 1.0, 1.0, (21, 21), protect, _i1_SectionRecipe(max_local_cut_m=0.1))
        arrays = section['arrays']
        self.assertTrue(section['summary']['blocked_by_plan'])
        self.assertTrue(arrays['over_budget_mask'].any())
        self.assertTrue(arrays['protected_conflict_mask'].any())
        self.assertEqual(arrays['actual_cut_m'][10, 10], 0.0)
        self.assertTrue(section['summary']['requires_shared_fine_extension'])
        self.assertTrue(arrays['clipped_boundary_mask'].any())

    def test_outside_source_rejected_and_storage_round_trip(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i1_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i1_evaluate_sections
        from terrain_pipeline.channel_geometry import load_sections as _i1_load_sections
        from terrain_pipeline.channel_geometry import save_sections as _i1_save_sections
        plan = synthetic_plan()
        with self.assertRaises(ValueError):
            _i1_evaluate_sections(plan, -1.0, 0.0, 1.0, 1.0, (3, 3), _i1_np.zeros((3, 3), bool), _i1_SectionRecipe())
        section = _i1_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (41, 41), _i1_np.zeros((41, 41), bool), _i1_SectionRecipe())
        with _i1_tempfile.TemporaryDirectory() as directory:
            path = _i1_Path(directory) / 'section.npz'
            _i1_save_sections(section, path)
            reloaded = _i1_load_sections(path)
            self.assertEqual(section['identity_sha256'], reloaded['identity_sha256'])
            for name, value in section['arrays'].items():
                _i1_np.testing.assert_array_equal(value, reloaded['arrays'][name])
            with self.assertRaises(FileExistsError):
                _i1_save_sections(section, path)

    def test_cosine_cross_section_and_unchanged_exterior(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i1_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i1_evaluate_sections
        plan = synthetic_plan(width=4.0)
        original = plan['arrays']['source_height_m'].copy()
        section = _i1_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (41, 41), _i1_np.zeros((41, 41), bool), _i1_SectionRecipe(max_local_cut_m=10.0))
        cut = section['arrays']['required_cut_m']
        center_cut = 10.0 - 0.5 * (plan['arrays']['target_bed_m'].flat[12] + plan['arrays']['target_bed_m'].flat[17])
        self.assertAlmostEqual(cut[25, 20], center_cut, places=6)
        self.assertAlmostEqual(cut[25, 21], 0.5 * center_cut, places=6)
        self.assertAlmostEqual(cut[25, 22], 0.0, places=8)
        self.assertEqual(cut[40, 0], 0.0)
        _i1_np.testing.assert_array_equal(plan['arrays']['source_height_m'], original)

    def test_narrow_segment_reports_sampling_and_local_refinement(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i1_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i1_evaluate_sections
        plan = synthetic_plan(width=1.0)
        section = _i1_evaluate_sections(plan, 0.5, 0.5, 4.0, 5.0, (8, 8), _i1_np.zeros((8, 8), bool), _i1_SectionRecipe())
        self.assertGreater(section['summary']['potentially_unsampled_segments'], 0)
        whole = _i1_evaluate_sections(plan, 0.0, 0.0, 2.0, 4.0, (11, 21), _i1_np.zeros((11, 21), bool), _i1_SectionRecipe())
        self.assertGreater(whole['summary']['needs_refinement_nodes'], 0)

def corner_plan():
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i0_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i0_plan_channel
    height = _i0_np.full((4, 4), 10.0)
    outlet = _i0_np.ones((4, 4), bool)
    receiver = _i0_np.full(16, -1, dtype=_i0_np.int64)
    for cell, target in ((1, 5), (5, 6), (6, 10)):
        receiver[cell] = target
        outlet.flat[cell] = False
    order = _i0_np.array([cell for cell in range(16) if outlet.flat[cell]] + [6, 5, 1])
    q = _i0_np.full((4, 4), 0.01)
    q.flat[[1, 5, 6, 10]] = 0.1
    return _i0_plan_channel(height, receiver, order, outlet, q, 10.0, 10.0, 0.0, 0.0, 0.0, 'corner', _i0_ChannelRecipe(reference_depth_m=1.0, min_depth_m=1.0, max_depth_m=1.0, max_cut_m=10.0, min_bed_slope_m_per_m=0.0001))

class ChannelCenterlineTests(_i0_unittest.TestCase):

    def test_corner_moves_only_internal_nodes_and_zero_strength_is_legacy(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i0_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i0_build_centerline
        from terrain_pipeline.channel_geometry import SectionRecipe as _i0_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i0_evaluate_sections
        plan = corner_plan()
        original = plan['arrays']['source_height_m'].copy()
        zero = _i0_build_centerline(plan, _i0_SmoothingRecipe(strength=0.0))
        _i0_np.testing.assert_array_equal(zero['arrays']['node_world_xz_m'], zero['arrays']['original_world_xz_m'])
        smooth = _i0_build_centerline(plan, _i0_SmoothingRecipe(max_offset_m=10.0))
        arrays = smooth['arrays']
        self.assertGreater(smooth['summary']['moved_nodes'], 0)
        _i0_np.testing.assert_array_equal(arrays['node_world_xz_m'][arrays['anchor_mask']], arrays['original_world_xz_m'][arrays['anchor_mask']])
        self.assertLessEqual(smooth['summary']['max_offset_m'], 10.0)
        _i0_np.testing.assert_array_equal(plan['arrays']['source_height_m'], original)
        legacy = _i0_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (31, 31), _i0_np.zeros((31, 31), bool), _i0_SectionRecipe())
        explicit_zero = _i0_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (31, 31), _i0_np.zeros((31, 31), bool), _i0_SectionRecipe(), zero)
        _i0_np.testing.assert_array_equal(legacy['arrays']['required_cut_m'], explicit_zero['arrays']['required_cut_m'])

    def test_corridor_rejects_and_confluence_anchor_stays_fixed(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i0_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i0_build_centerline
        plan = corner_plan()
        with self.assertRaisesRegex(ValueError, 'corridor'):
            _i0_build_centerline(plan, _i0_SmoothingRecipe(max_offset_m=0.1))
        confluence = synthetic_plan()
        smooth = _i0_build_centerline(confluence, _i0_SmoothingRecipe(max_offset_m=10.0))
        arrays = smooth['arrays']
        junction = _i0_np.where(arrays['node_flat_index'] == 12)[0][0]
        self.assertTrue(arrays['anchor_mask'][junction])
        _i0_np.testing.assert_array_equal(arrays['node_world_xz_m'][junction], arrays['original_world_xz_m'][junction])

    def test_shared_smoothed_geometry_matches_adjacent_tiles_and_storage(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i0_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i0_build_centerline
        from terrain_pipeline.channel_geometry import load_centerline as _i0_load_centerline
        from terrain_pipeline.channel_geometry import save_centerline as _i0_save_centerline
        from terrain_pipeline.channel_geometry import validate_centerline_for_plan as _i0_validate_centerline_for_plan
        from terrain_pipeline.channel_geometry import SectionRecipe as _i0_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i0_evaluate_sections
        plan = corner_plan()
        smooth = _i0_build_centerline(plan, _i0_SmoothingRecipe(max_offset_m=10.0))
        recipe = _i0_SectionRecipe(max_local_cut_m=10.0)
        whole = _i0_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (31, 31), _i0_np.zeros((31, 31), bool), recipe, smooth)
        left = _i0_evaluate_sections(plan, 0.0, 0.0, 1.0, 1.0, (31, 16), _i0_np.zeros((31, 16), bool), recipe, smooth)
        right = _i0_evaluate_sections(plan, 15.0, 0.0, 1.0, 1.0, (31, 16), _i0_np.zeros((31, 16), bool), recipe, smooth)
        _i0_np.testing.assert_array_equal(left['arrays']['required_cut_m'], whole['arrays']['required_cut_m'][:, :16])
        _i0_np.testing.assert_array_equal(right['arrays']['required_cut_m'], whole['arrays']['required_cut_m'][:, 15:])
        with _i0_tempfile.TemporaryDirectory() as directory:
            path = _i0_Path(directory) / 'centerline.npz'
            _i0_save_centerline(smooth, path)
            loaded = _i0_load_centerline(path)
            self.assertTrue(_i0_validate_centerline_for_plan(loaded, plan))
            _i0_np.testing.assert_array_equal(loaded['arrays']['node_world_xz_m'], smooth['arrays']['node_world_xz_m'])
            with self.assertRaises(FileExistsError):
                _i0_save_centerline(smooth, path)

    def test_crossing_touch_overlap_and_separation_guards(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i0_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i0_build_centerline
        from terrain_pipeline.channel_geometry import _segments_cross as _i0__segments_cross
        from terrain_pipeline.channel_geometry import _shared_edge_overlap as _i0__shared_edge_overlap
        self.assertTrue(_i0__segments_cross(_i0_np.array([0.0, 0.0]), _i0_np.array([2.0, 2.0]), _i0_np.array([0.0, 2.0]), _i0_np.array([2.0, 0.0])))
        self.assertTrue(_i0__segments_cross(_i0_np.array([0.0, 0.0]), _i0_np.array([2.0, 0.0]), _i0_np.array([1.0, 0.0]), _i0_np.array([1.0, 2.0])))
        self.assertTrue(_i0__shared_edge_overlap(_i0_np.array([0.0, 0.0]), _i0_np.array([2.0, 0.0]), _i0_np.array([0.0, 0.0]), _i0_np.array([1.0, 0.0]), _i0_np.array([0.0, 0.0])))
        shifted = _i0_np.array([1000000.0, 1000000.0])
        self.assertFalse(_i0__shared_edge_overlap(shifted, shifted + [2.0, 0.0], shifted, shifted + [-1.0, 0.0], shifted))
        self.assertTrue(_i0__segments_cross(shifted, shifted + [2.0, 2.0], shifted + [0.0, 2.0], shifted + [2.0, 0.0]))
        with self.assertRaisesRegex(ValueError, 'separation'):
            _i0_build_centerline(synthetic_plan(), _i0_SmoothingRecipe(max_offset_m=10.0, min_separation_m=100.0))

    def test_new_length_slope_failure_is_reported(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i0_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i0_build_centerline
        plan = synthetic_plan()
        centerline = _i0_build_centerline(plan, _i0_SmoothingRecipe(max_offset_m=10.0))
        self.assertGreater(centerline['summary']['slope_failed_edges'], 0)
        self.assertTrue(centerline['arrays']['slope_failed_donor_mask'].any())

    def test_saved_geometry_tamper_and_wrong_plan_rejected(self):
        from terrain_pipeline.channel_geometry import SmoothingRecipe as _i0_SmoothingRecipe
        from terrain_pipeline.channel_geometry import build_centerline as _i0_build_centerline
        from terrain_pipeline.channel_geometry import load_centerline as _i0_load_centerline
        from terrain_pipeline.channel_geometry import save_centerline as _i0_save_centerline
        from terrain_pipeline.channel_geometry import validate_centerline_for_plan as _i0_validate_centerline_for_plan
        from terrain_pipeline.artifacts.contracts import array_hash as _i0_array_hash
        plan = corner_plan()
        centerline = _i0_build_centerline(plan, _i0_SmoothingRecipe(max_offset_m=10.0))
        with _i0_tempfile.TemporaryDirectory() as directory:
            path = _i0_Path(directory) / 'centerline.npz'
            _i0_save_centerline(centerline, path)
            with _i0_np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name].copy() for name in archive.files if name != 'manifest'}
                manifest = _i0_json.loads(str(archive['manifest'].item()))
            arrays['node_world_xz_m'][1, 0] += 0.1
            manifest['array_sha256']['node_world_xz_m'] = _i0_array_hash(arrays['node_world_xz_m'])
            _i0_np.savez_compressed(path, manifest=_i0_json.dumps(manifest), **arrays)
            with self.assertRaisesRegex(ValueError, 'geometry differs from identity'):
                _i0_load_centerline(path)
        with self.assertRaisesRegex(ValueError, 'source plan mismatch'):
            _i0_validate_centerline_for_plan(centerline, synthetic_plan())

    def test_default_sections_match_saved_v1_artifact_exactly(self):
        from terrain_pipeline.channel_geometry import SectionRecipe as _i0_SectionRecipe
        from terrain_pipeline.channel_geometry import evaluate_sections as _i0_evaluate_sections
        from terrain_pipeline.channel_geometry import load_sections as _i0_load_sections
        from terrain_pipeline.channel_geometry import load_plan as _i0_load_plan
        root = _i0_Path(__file__).resolve().parents[1]
        plan = _i0_load_plan(root / 'verification/metric-channel-plan/run-20260929T140629572001Z/normal_mountain-plan.npz')
        original = _i0_load_sections(root / 'verification/local-channel-sections/run-20260929T142543606808Z/normal-mountain-local-sections.npz')
        current = _i0_evaluate_sections(plan, 354240.0, 468420.0, 1.0, 1.0, (61, 61), _i0_np.zeros((61, 61), bool), _i0_SectionRecipe())
        self.assertEqual(current['identity_sha256'], original['identity_sha256'])
        for name in current['arrays']:
            _i0_np.testing.assert_array_equal(current['arrays'][name], original['arrays'][name])

class MetricBankBraidingTests(_i2_unittest.TestCase):

    def setUp(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
        height = _i2_np.zeros((9, 9), dtype=_i2_np.float64)
        self.terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, dtype=bool), 0.0, 0.0, 1.0, 1.0, 'diagnostic_dem_proxy', 'fixture', 'a' * 64)

    def test_curvature_signs_unknown_protection_and_conservation(self):
        from terrain_pipeline.channel_geometry import BankPointbarConfig as _i2_BankPointbarConfig
        from terrain_pipeline.channel_geometry import build_bank_pointbar_candidate as _i2_build_bank_pointbar_candidate
        positive = _i2_np.array([[2.0, 2.0], [3.0, 3.0], [4.0, 2.0], [5.0, 1.0]], dtype=_i2_np.float64)
        negative = _i2_np.array([[2.0, 2.0], [3.0, 1.0], [4.0, 2.0], [5.0, 3.0]], dtype=_i2_np.float64)
        config = _i2_BankPointbarConfig(max_erosion_depth_m=0.1, max_deposit_depth_m=0.1, porosity=0.0)
        first = _i2_build_bank_pointbar_candidate(self.terrain, positive, 'b' * 64, 'c' * 64, 2.0, config)
        second = _i2_build_bank_pointbar_candidate(self.terrain, negative, 'b' * 64, 'c' * 64, 2.0, config)
        self.assertTrue(_i2_np.any(first['erosion_mask']))
        self.assertTrue(_i2_np.any(second['erosion_mask']))
        self.assertFalse(_i2_np.array_equal(first['erosion_mask'], second['erosion_mask']))
        ledger = first['solid_ledger']
        self.assertAlmostEqual(ledger['input_solid_m3'] + ledger['eroded_solid_m3'], ledger['deposited_solid_m3'] + ledger['exported_solid_m3'] + ledger['unresolved_solid_m3'])

    def test_unknown_cells_are_untouched_and_event_is_deterministic(self):
        from terrain_pipeline.channel_geometry import build_bank_pointbar_candidate as _i2_build_bank_pointbar_candidate
        from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
        valid = self.terrain.valid_mask.copy()
        valid[3, 3] = False
        terrain = _i2_TerrainGrid(self.terrain.elevation_m.copy(), valid, 0.0, 0.0, 1.0, 1.0, 'diagnostic_dem_proxy', 'fixture', 'a' * 64)
        points = _i2_np.array([[2.0, 2.0], [3.0, 2.0], [4.0, 3.0], [5.0, 4.0]], dtype=_i2_np.float64)
        result = _i2_build_bank_pointbar_candidate(terrain, points, 'b' * 64, 'c' * 64, 1.0)
        self.assertFalse(_i2_np.any(result['height_delta_m'][~valid]))
        repeat = _i2_build_bank_pointbar_candidate(terrain, points, 'b' * 64, 'c' * 64, 1.0)
        self.assertEqual(result['event'].identity_sha256, repeat['event'].identity_sha256)
        self.assertEqual(result['event'].event_type, 'bank_migration')

    def test_braided_candidates_are_finite_and_do_not_write_graph(self):
        from terrain_pipeline.channel_geometry import BraidedConfig as _i2_BraidedConfig
        from terrain_pipeline.channel_geometry import build_braided_candidate as _i2_build_braided_candidate
        water = _i2_np.zeros((9, 9), dtype=bool)
        water[4, 1:8] = True
        water[3, 2:7] = True
        water[5, 2:7] = True
        path = tuple(((4, column) for column in range(1, 8)))
        result = _i2_build_braided_candidate(self.terrain, path, water, 'b' * 64, 'c' * 64, 10.0, 2.0, _i2_BraidedConfig(max_candidates=3, branch_fraction=0.2))
        self.assertIn(len(result['candidate_paths']), (2, 3))
        self.assertAlmostEqual(sum(result['flow_split']), 1.0)
        self.assertFalse(result['routing_graph_written'])
        ledger = result['solid_ledger']
        self.assertAlmostEqual(ledger['input_solid_m3'], ledger['deposited_solid_m3'] + ledger['unresolved_solid_m3'])
        self.assertEqual(result['event'].event_type, 'bifurcation')

    def test_invalid_inputs_rejected(self):
        from terrain_pipeline.channel_geometry import build_bank_pointbar_candidate as _i2_build_bank_pointbar_candidate
        from terrain_pipeline.channel_geometry import build_braided_candidate as _i2_build_braided_candidate
        water = _i2_np.ones((9, 9), dtype=bool)
        with self.assertRaises(ValueError):
            _i2_build_bank_pointbar_candidate(self.terrain, _i2_np.zeros((2, 2), dtype=_i2_np.float32), 'b' * 64, 'c' * 64, 1.0)
        with self.assertRaises(ValueError):
            _i2_build_braided_candidate(self.terrain, ((0, 0), (0, 2)), water, 'b' * 64, 'c' * 64, 1.0, 1.0)
        with self.assertRaises(ValueError):
            _i2_build_braided_candidate(self.terrain, ((0, 0), (0, 1)), water, 'bad', 'c' * 64, 1.0, 1.0)

def fixture(center_height=3.0, base=0.0, outlet=True):
    from terrain_pipeline.common_infra import BoundaryGrid as _i3_BoundaryGrid
    from terrain_pipeline.common_infra import TerrainGrid as _i3_TerrainGrid
    from terrain_pipeline.drainage import route_diagnostic as _i3_route_diagnostic
    height = _i3_np.array([[9.0, 9.0, 9.0, 9.0, 9.0], [9.0, 8.0, 7.0, 8.0, 9.0], [9.0, 5.0, center_height, 5.0, 9.0], [9.0, 4.0, 4.0, 4.0, 9.0], [9.0, 9.0, 2.0, 9.0, 9.0]]) + base
    terrain = _i3_TerrainGrid(height, _i3_np.ones(height.shape, bool), 0.0, 0.0, 30.0, 30.0, 'generated_terrain', 'bounded-test', 'a' * 64)
    kinds = _i3_np.full(height.shape, 'interior', dtype='U24')
    kinds[[0, -1], :] = 'closed_wall'
    kinds[:, [0, -1]] = 'closed_wall'
    if outlet:
        kinds[4, 2] = 'unknown_boundary'
    boundary = _i3_BoundaryGrid(kinds, _i3_np.zeros(height.shape, bool), 'test', 'b' * 64)
    baseline = _i3_route_diagnostic(terrain, boundary, flat_distance_strategy='metric_distance')
    return (terrain, boundary, baseline)

class BoundedConfluenceTests(_i3_unittest.TestCase):

    def test_unfilled_inclined_slope_uses_terrain_descent_instead_of_flood_tree(self):
        from terrain_pipeline.common_infra import BoundaryGrid as _i3_BoundaryGrid
        from terrain_pipeline.common_infra import TerrainGrid as _i3_TerrainGrid
        from terrain_pipeline.drainage import route_diagnostic as _i3_route_diagnostic
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        rows, columns = _i3_np.indices((7, 7))
        height = 100.0 - 5.0 * rows - 0.5 * columns
        terrain = _i3_TerrainGrid(height, _i3_np.ones(height.shape, bool), 0.0, 0.0, 30.0, 30.0, 'generated_terrain', 'inclined-test', 'a' * 64)
        kinds = _i3_np.full(height.shape, 'interior', dtype='U24')
        kinds[[0, -1], :] = 'unknown_boundary'
        kinds[:, [0, -1]] = 'unknown_boundary'
        boundary = _i3_BoundaryGrid(kinds, _i3_np.zeros(height.shape, bool), 'test', 'b' * 64)
        baseline = _i3_route_diagnostic(terrain, boundary)
        graph, work, metadata, _ = _i3_bounded_confluence_candidate(terrain, boundary, _i3_np.zeros(height.shape, _i3_np.int64), baseline_receiver=baseline.receiver)
        interior = _i3_np.arange(49).reshape(height.shape)[1:-1, 1:-1].ravel()
        from terrain_pipeline.drainage import strict_receivers as strict_receivers
        from terrain_pipeline.channel_geometry import _terrain_mesh
        expected = strict_receivers(terrain.elevation_m, _terrain_mesh(terrain))[0]
        _i3_np.testing.assert_array_equal(graph.receiver[interior], expected[interior])
        _i3_np.testing.assert_array_equal(work, height)
        self.assertEqual(metadata['backend'], 'irregular_graph')
        self.assertEqual(metadata['algorithm'], 'frozen_owner_bounded_confluence_candidate_v3_irregular')
        perimeter = _i3_np.r_[_i3_np.arange(7), _i3_np.arange(42, 49), _i3_np.arange(7, 42, 7), _i3_np.arange(13, 42, 7)]
        self.assertTrue(_i3_np.all(graph.receiver[perimeter] == -1))

    def test_shallow_pit_connects_both_branches_to_shared_outlet_without_source_edits(self):
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        terrain, boundary, baseline = fixture()
        original = terrain.elevation_m.copy()
        self.assertEqual(baseline.receiver[12], -1)
        graph, work, metadata, arrays = _i3_bounded_confluence_candidate(terrain, boundary, _i3_np.zeros(original.shape, _i3_np.int64), baseline_receiver=baseline.receiver, local_q_m3_s=_i3_np.ones(original.shape))
        for source in (6, 8, 12):
            path = []
            while source >= 0:
                path.append(source)
                source = graph.receiver[source]
            self.assertIn(12, path)
            self.assertEqual(path[-1], 22)
        self.assertEqual(work[2, 2], 4.0)
        self.assertEqual(metadata['maximum_fill_m'], 1.0)
        _i3_np.testing.assert_array_equal(terrain.elevation_m, original)
        self.assertEqual(arrays['contributing_area_m2'][22], 25 * 900.0)
        self.assertEqual(arrays['routed_q_m3_s'][22], 25.0)
        self.assertFalse(metadata['natural_outlet_verified'])

    def test_deep_pit_stays_unresolved_and_actual_fill_respects_limit(self):
        from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES as _i3_TERMINAL_STATUS_CODES
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        terrain, boundary, baseline = fixture(center_height=-3.0)
        graph, work, metadata, arrays = _i3_bounded_confluence_candidate(terrain, boundary, _i3_np.zeros(terrain.elevation_m.shape, _i3_np.int64), baseline_receiver=baseline.receiver)
        self.assertEqual(graph.receiver[12], -1)
        self.assertEqual(arrays['terminal_status'][12], _i3_TERMINAL_STATUS_CODES['unresolved_deep_depression'])
        self.assertEqual(work[2, 2], -3.0)
        self.assertLessEqual(metadata['maximum_fill_m'], 4.0)
        self.assertIn('no accepted lake', metadata['graph_lake_preserved_semantics'])

    def test_only_original_cross_domain_contact_becomes_unresolved_port(self):
        from terrain_pipeline.common_infra import BoundaryGrid as _i3_BoundaryGrid
        from terrain_pipeline.common_infra import TerrainGrid as _i3_TerrainGrid
        from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES as _i3_TERMINAL_STATUS_CODES
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        height = _i3_np.array([[12.0, 11.0, 10.0, 9.0, 8.0, 7.0], [8.0, 7.0, 6.0, 5.0, 4.0, 3.0], [12.0, 11.0, 10.0, 9.0, 8.0, 7.0]])
        terrain = _i3_TerrainGrid(height, _i3_np.ones(height.shape, bool), 0.0, 0.0, 30.0, 30.0, 'generated_terrain', 'contacts-test', 'a' * 64)
        kinds = _i3_np.full(height.shape, 'closed_wall', dtype='U24')
        kinds[1, 5] = 'unknown_boundary'
        boundary = _i3_BoundaryGrid(kinds, _i3_np.zeros(height.shape, bool), 'test', 'b' * 64)
        baseline = _i3_np.r_[_i3_np.arange(6, 12), _i3_np.arange(7, 12), -1, _i3_np.arange(6, 12)].astype(_i3_np.int64)
        owner = _i3_np.zeros(height.shape, _i3_np.int64)
        owner[:, 3:] = 2
        graph, _, metadata, arrays = _i3_bounded_confluence_candidate(terrain, boundary, owner, baseline_receiver=baseline)
        self.assertEqual(metadata['baseline_cross_owner_contact_count'], 1)
        self.assertEqual(graph.receiver[8], -1)
        self.assertEqual(graph.outlet_kind[8], 'unknown_boundary')
        self.assertEqual(arrays['terminal_status'][8], _i3_TERMINAL_STATUS_CODES['unresolved_domain_boundary'])
        self.assertGreaterEqual(graph.receiver[2], 0)
        self.assertGreaterEqual(graph.receiver[14], 0)
        sources = _i3_np.flatnonzero(graph.receiver >= 0)
        _i3_np.testing.assert_array_equal(owner.ravel()[sources], owner.ravel()[graph.receiver[sources]])

    def test_component_without_seed_retains_baseline_and_complete_order(self):
        from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES as _i3_TERMINAL_STATUS_CODES
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        terrain, boundary, baseline = fixture(outlet=False)
        graph, work, metadata, arrays = _i3_bounded_confluence_candidate(terrain, boundary, _i3_np.zeros(terrain.elevation_m.shape, _i3_np.int64), baseline_receiver=baseline.receiver)
        _i3_np.testing.assert_array_equal(graph.receiver, baseline.receiver)
        _i3_np.testing.assert_array_equal(work, terrain.elevation_m)
        _i3_np.testing.assert_array_equal(_i3_np.sort(graph.order_downstream_first), _i3_np.arange(25))
        self.assertEqual(metadata['component_records'][0]['seed_count'], 0)
        self.assertEqual(arrays['terminal_status'][12], _i3_TERMINAL_STATUS_CODES['unresolved_closed_domain'])

    def test_unseeded_component_preserves_a_nonsteepest_supplied_baseline(self):
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        terrain, boundary, baseline = fixture(outlet=False)
        receiver = baseline.receiver.copy()
        receiver[6] = 7
        graph, _, metadata, _ = _i3_bounded_confluence_candidate(terrain, boundary, _i3_np.zeros(terrain.elevation_m.shape, _i3_np.int64), baseline_receiver=receiver)
        _i3_np.testing.assert_array_equal(graph.receiver, receiver)
        self.assertEqual(metadata['steepest_descent_changed_edge_count'], 0)

    def test_negative_owner_keeps_routing_and_terminal_reason_without_ocean_claim(self):
        from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES as _i3_TERMINAL_STATUS_CODES
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        terrain, boundary, baseline = fixture(center_height=-3.0)
        owner = _i3_np.full(terrain.elevation_m.shape, -1, _i3_np.int64)
        graph, _, metadata, arrays = _i3_bounded_confluence_candidate(terrain, boundary, owner, baseline_receiver=baseline.receiver)
        self.assertGreater(_i3_np.count_nonzero(graph.receiver >= 0), 20)
        self.assertEqual(arrays['terminal_status'][12], _i3_TERMINAL_STATUS_CODES['unresolved_deep_depression'])
        self.assertFalse(arrays['terminal_owner_known'][12])
        self.assertEqual(graph.outlet_kind[12], 'unknown_boundary')
        self.assertGreater(metadata['unknown_owner_terminal_count'], 0)

    def test_float32_priority_rounding_cannot_raise_above_actual_four_meter_cap(self):
        from terrain_pipeline.channel_geometry import bounded_confluence_candidate as _i3_bounded_confluence_candidate
        terrain, boundary, baseline = fixture(center_height=0.001, base=134217728.0)
        graph, work, metadata, arrays = _i3_bounded_confluence_candidate(terrain, boundary, _i3_np.zeros(terrain.elevation_m.shape, _i3_np.int64), baseline_receiver=baseline.receiver)
        self.assertTrue(_i3_np.all(work - terrain.elevation_m <= 4.0))
        sources = _i3_np.flatnonzero(graph.receiver >= 0)
        self.assertTrue(_i3_np.all(work.ravel()[sources] >= work.ravel()[graph.receiver[sources]]))
        _i3_np.testing.assert_array_equal(work - terrain.elevation_m, arrays['working_raise_m'])
        self.assertLessEqual(metadata['maximum_fill_m'], 4.0)

def terrain():
    from terrain_pipeline.common_infra import TerrainGrid as _i4_TerrainGrid
    rows, cols = _i4_np.indices((9, 9))
    return _i4_TerrainGrid(20.0 - 0.1 * cols + 0.05 * rows, _i4_np.ones((9, 9), bool), x0_m=0.0, z0_m=0.0, dx_m=4.0, dz_m=4.0, source_kind='observed_dem', source_id='worked valley', source_sha256='a' * 64)

def build(*, owner=None, corridor=None, lake=None, config=None):
    from terrain_pipeline.channel_geometry import GeometryConfig as _i4_GeometryConfig
    from terrain_pipeline.channel_geometry import build_channel_geometry as _i4_build_channel_geometry
    source = terrain()
    shape = source.elevation_m.shape
    return _i4_build_channel_geometry(source, _i4_np.array([3 * 9 + 2, 3 * 9 + 5], _i4_np.int64), _i4_np.array([1, -1], _i4_np.int64), _i4_np.array([2.0, 2.0]), _i4_np.array([0.5, 0.5]), owner_grid=_i4_np.zeros(shape, _i4_np.int64) if owner is None else owner, corridor_mask=_i4_np.ones(shape, bool) if corridor is None else corridor, lake_mask=_i4_np.zeros(shape, bool) if lake is None else lake, anchor_mask=_i4_np.zeros(2, bool), config=config or _i4_GeometryConfig(fine_spacing_m=0.5))

class ChannelGeometryTests(_i4_unittest.TestCase):

    def test_nonlocal_continuous_bank_overlap_rejects_unsampled_lens(self):
        from terrain_pipeline.channel_geometry import _cut_overlap as _i4__cut_overlap
        points = _i4_np.array([[0.0, 0.0], [10.0, 0.0], [0.2, 1.9], [10.2, 1.9]])
        receiver = _i4_np.array([1, -1, 3, -1], _i4_np.int64)
        width = _i4_np.ones(4)
        depth = _i4_np.full(4, 0.25)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            _i4__cut_overlap(points, receiver, width, depth)

    def test_canonical_triangle_slope_rejects_local_hump(self):
        from terrain_pipeline.channel_geometry import _modified_bed_slope as _i4__modified_bed_slope
        arrays = build()['arrays']
        bed = arrays['bed_elevation_m'].copy()
        vertex = _i4_np.flatnonzero(_i4_np.all(_i4_np.isclose(arrays['vertices_xz_m'], [12.0, 12.0]), axis=1))[0]
        bed[vertex] += 2.0
        with self.assertRaisesRegex(ValueError, 'uphill'):
            _i4__modified_bed_slope(arrays['node_xz_m'], arrays['receiver'], arrays['vertices_xz_m'], arrays['triangles'], bed, 0.5)

    def test_mixed_wet_native_cells_have_zero_pl_cut(self):
        from terrain_pipeline.channel_geometry import build_channel_geometry as _i4_build_channel_geometry
        from terrain_pipeline.channel_geometry import _wet_guard as _i4__wet_guard
        from tools.verify_td_river_geometry import fixture
        source, ids, receiver, options = fixture('lake', 1.0)
        bundle = _i4_build_channel_geometry(source, ids, receiver, **options)
        arrays = bundle['arrays']
        guarded = _i4__wet_guard(arrays['vertices_xz_m'], options['lake_mask'], source)
        self.assertTrue(_i4_np.any(guarded))
        _i4_np.testing.assert_array_equal(arrays['cut_depth_m'][guarded], 0.0)
        self.assertEqual(bundle['metadata']['lake_cut_policy'], 'zero_on_native_cells_touching_known_wet_nodes')

    def test_single_reach_has_one_fan_mesh_and_exact_represented_cut_budget(self):
        from terrain_pipeline.channel_geometry import validate_channel_geometry as _i4_validate_channel_geometry
        bundle = build()
        arrays, meta = (bundle['arrays'], bundle['metadata'])
        self.assertTrue(_i4_validate_channel_geometry(bundle))
        self.assertTrue(meta['geometry_verified'])
        self.assertFalse(meta['hydraulic_ready'])
        self.assertGreater(meta['cut_volume_m3'], 0.0)
        self.assertEqual(meta['deposition_bulk_m3'], 0.0)
        self.assertAlmostEqual(meta['original_mesh_volume_m3'] - meta['final_mesh_volume_m3'], meta['cut_volume_m3'], places=8)
        _i4_np.testing.assert_allclose(arrays['bed_elevation_m'], arrays['source_elevation_m'] - arrays['cut_depth_m'])
        self.assertEqual(len(arrays['triangles']) % 4, 0)
        self.assertEqual(len(arrays['canonical_port_edge_node_indices']), 1)

    def test_turn_y_and_lake_use_one_mesh_with_zero_cut_on_wet_support(self):
        from terrain_pipeline.channel_geometry import build_channel_geometry as _i4_build_channel_geometry
        from tools.verify_td_river_geometry import fixture
        from tools.verify_td_river_geometry import mesh_evidence
        for name in ('turn', 'y', 'lake'):
            with self.subTest(name=name):
                source, ids, receiver, options = fixture(name, 1.0)
                bundle = _i4_build_channel_geometry(source, ids, receiver, **options)
                evidence = mesh_evidence(bundle)
                self.assertTrue(evidence['internal_edges_reversed'])
                self.assertTrue(evidence['shared_port_observations_verified'])
                if name == 'lake':
                    arrays = bundle['arrays']
                    grid = arrays['vertices_xz_m'] / 10.0
                    on_source_node = _i4_np.all(_i4_np.isclose(grid, _i4_np.round(grid)), axis=1)
                    source_ids = _i4_np.round(grid[:, 1]).astype(int) * 13 + _i4_np.round(grid[:, 0]).astype(int)
                    wet_vertex = on_source_node & arrays['lake_mask'].ravel()[source_ids]
                    self.assertTrue(_i4_np.any(wet_vertex))
                    self.assertTrue(_i4_np.all(arrays['cut_depth_m'][wet_vertex] <= 1e-10))
                    inside_wet_rectangle = (grid[:, 0] >= 5.0) & (grid[:, 0] <= 8.0) & (grid[:, 1] >= 3.0) & (grid[:, 1] <= 6.0)
                    self.assertTrue(_i4_np.any(inside_wet_rectangle))
                    self.assertTrue(_i4_np.all(arrays['cut_depth_m'][inside_wet_rectangle] <= 1e-10))

    def test_source_unknown_owner_divide_and_flat_route_reject(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i4_TerrainGrid
        from terrain_pipeline.channel_geometry import GeometryConfig as _i4_GeometryConfig
        from terrain_pipeline.channel_geometry import build_channel_geometry as _i4_build_channel_geometry
        source = terrain()
        ids = _i4_np.array([3 * 9 + 2, 3 * 9 + 5], _i4_np.int64)
        receiver = _i4_np.array([1, -1], _i4_np.int64)
        width = _i4_np.array([2.0, 2.0])
        depth = _i4_np.array([0.5, 0.5])
        good = dict(owner_grid=_i4_np.zeros((9, 9), _i4_np.int64), corridor_mask=_i4_np.ones((9, 9), bool), lake_mask=_i4_np.zeros((9, 9), bool), anchor_mask=_i4_np.zeros(2, bool), config=_i4_GeometryConfig(fine_spacing_m=0.5))
        unknown = source.valid_mask.copy()
        unknown[3, 4] = False
        bad_source = _i4_TerrainGrid(source.elevation_m.copy(), unknown, 0.0, 0.0, 4.0, 4.0, 'observed_dem', 'worked valley', 'a' * 64)
        with self.assertRaisesRegex(ValueError, 'unknown|footprint'):
            _i4_build_channel_geometry(bad_source, ids, receiver, width, depth, **good)
        owner = good['owner_grid'].copy()
        owner[3, 4] = 1
        with self.assertRaisesRegex(ValueError, 'divide|owner'):
            _i4_build_channel_geometry(source, ids, receiver, width, depth, **good | {'owner_grid': owner})
        flat = _i4_TerrainGrid(_i4_np.full((9, 9), 20.0), _i4_np.ones((9, 9), bool), 0.0, 0.0, 4.0, 4.0, 'observed_dem', 'flat', 'a' * 64)
        with self.assertRaisesRegex(ValueError, 'flat|uphill'):
            _i4_build_channel_geometry(flat, ids, receiver, width, depth, **good)

    def test_cold_validator_rejects_rehashed_cut_and_port_forgery(self):
        from terrain_pipeline.common_infra import identity as _i4_identity
        from terrain_pipeline.channel_geometry import validate_channel_geometry as _i4_validate_channel_geometry
        bundle = build()
        for field in ('cut_depth_m', 'canonical_port_cut_depth_m'):
            with self.subTest(field=field):
                forged = _i4_deepcopy(bundle)
                forged['arrays'][field] = forged['arrays'][field].copy()
                forged['arrays'][field].flat[0] += 0.01
                forged['identity_sha256'] = _i4_identity(forged['arrays'], forged['metadata'])
                with self.assertRaisesRegex(ValueError, 'cut|port'):
                    _i4_validate_channel_geometry(forged)

    def test_cold_roundtrip_keeps_source_and_represented_volume(self):
        from terrain_pipeline.common_infra import file_sha256 as _i4_file_sha256
        from terrain_pipeline.channel_geometry import load_channel_geometry as _i4_load_channel_geometry
        from terrain_pipeline.channel_geometry import save_channel_geometry as _i4_save_channel_geometry
        bundle = build()
        with _i4_tempfile.TemporaryDirectory() as folder:
            path = _i4_Path(folder) / 'channel-geometry.npz'
            _i4_save_channel_geometry(path, bundle)
            loaded = _i4_load_channel_geometry(path, expected_sha256=_i4_file_sha256(path), expected_identity=bundle['identity_sha256'])
        _i4_np.testing.assert_array_equal(loaded['arrays']['source_height_m'], terrain().elevation_m)
        self.assertEqual(loaded['metadata']['cut_volume_m3'], bundle['metadata']['cut_volume_m3'])

def make_plan(height, q, spacing=10.0, recipe=None):
    from terrain_pipeline.channel_geometry import ChannelRecipe as _i5_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _i5_plan_channel
    from terrain_pipeline.surface_rivers import route as _i5_route
    outlet = _i5_np.zeros(height.shape, dtype=bool)
    outlet[-1, -1] = True
    routing = _i5_route(height, outlet, spacing)
    return _i5_plan_channel(height, routing.receiver, routing.order, outlet, q, spacing, spacing, 0.0, 0.0, 0.0, 'test-source', recipe or _i5_ChannelRecipe())

class MetricChannelPlanTests(_i5_unittest.TestCase):

    def test_diagonal_uses_physical_length_and_confluence_stricter_bed(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i5_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i5_plan_channel
        from terrain_pipeline.drainage import grid_mesh as _i5_grid_mesh
        from terrain_pipeline.drainage import route_graph as _i5_route_graph
        height = _i5_np.full((2, 3), 10.0)
        outlet = _i5_np.zeros(height.shape, dtype=bool)
        outlet[1, 1] = True
        mesh = _i5_grid_mesh(height.shape, dx_m=3.0, dz_m=4.0)
        routing = _i5_route_graph(height, outlet, mesh)
        receiver, order = (routing.receiver, routing.order)
        q = _i5_np.full(height.shape, 0.1)
        recipe = _i5_ChannelRecipe(reference_width_m=1.0, reference_depth_m=1.0, min_depth_m=1.0, max_depth_m=1.0, max_cut_m=10.0, min_bed_slope_m_per_m=0.2)
        plan = _i5_plan_channel(height, receiver, order, outlet, q, 3.0, 4.0, 0.0, 0.0, 0.0, 'synthetic', recipe)
        path_lengths = []
        for start in range(height.size):
            length, node = (0.0, start)
            while receiver[node] >= 0:
                target = receiver[node]
                length += _i5_np.hypot(mesh.node_x_m[node] - mesh.node_x_m[target], mesh.node_z_m[node] - mesh.node_z_m[target])
                node = target
            path_lengths.append(length)
        expected = 9.0 - 0.2 * max(path_lengths)
        self.assertAlmostEqual(plan['arrays']['target_bed_m'][1, 1], expected)
        self.assertAlmostEqual(plan['arrays']['required_cut_m'][1, 1], 10.0 - expected)

    def test_threshold_and_spacing_do_not_set_nominal_dimensions(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i5_ChannelRecipe
        height = _i5_np.array([[10.0, 9.0, 8.0]])
        q = _i5_np.array([[0.05, 0.1, 0.2]])
        first = make_plan(height, q, 1.0, _i5_ChannelRecipe(start_discharge_m3_s=0.05))
        second = make_plan(height, q, 10.0, _i5_ChannelRecipe(start_discharge_m3_s=0.02))
        _i5_np.testing.assert_array_equal(first['arrays']['nominal_width_m'], second['arrays']['nominal_width_m'])
        _i5_np.testing.assert_array_equal(first['arrays']['nominal_depth_m'], second['arrays']['nominal_depth_m'])
        self.assertFalse(first['arrays']['needs_refinement_mask'].any())
        self.assertTrue(second['arrays']['needs_refinement_mask'].all())

    def test_threshold_does_not_change_shared_cell_nominal_dimensions(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i5_ChannelRecipe
        height = _i5_np.array([[10.0, 10.0, 10.0], [9.0, 9.0, 9.0], [8.0, 8.0, 8.0]])
        q = _i5_np.array([[0.01, 0.02, 0.01], [0.03, 0.05, 0.03], [0.04, 0.07, 0.1]])
        lower = make_plan(height, q, 1.0, _i5_ChannelRecipe(start_discharge_m3_s=0.01))
        higher = make_plan(height, q, 1.0, _i5_ChannelRecipe(start_discharge_m3_s=0.04))
        shared = higher['arrays']['channel_mask']
        _i5_np.testing.assert_array_equal(lower['arrays']['nominal_width_m'][shared], higher['arrays']['nominal_width_m'][shared])
        _i5_np.testing.assert_array_equal(lower['arrays']['nominal_depth_m'][shared], higher['arrays']['nominal_depth_m'][shared])

    def test_diagonal_length_and_budget_failure(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i5_ChannelRecipe
        height = _i5_np.array([[10.0, 10.0], [10.0, 10.0]])
        q = _i5_np.ones_like(height)
        plan = make_plan(height, q, 10.0, _i5_ChannelRecipe(max_cut_m=0.1, min_bed_slope_m_per_m=0.1, reference_depth_m=0.2, min_depth_m=0.2, max_depth_m=0.2))
        arrays = plan['arrays']
        self.assertTrue(arrays['over_budget_mask'].any())
        self.assertTrue(arrays['failed_slope_edge_donor_mask'].any())
        self.assertGreater(arrays['required_cut_m'].max(), 1.0)
        _i5_np.testing.assert_array_equal(height, _i5_np.full((2, 2), 10.0))

    def test_invalid_inputs_and_reproducible_storage(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i5_ChannelRecipe
        from terrain_pipeline.channel_geometry import load_plan as _i5_load_plan
        from terrain_pipeline.channel_geometry import plan_channel as _i5_plan_channel
        from terrain_pipeline.channel_geometry import save_plan as _i5_save_plan
        height = _i5_np.array([[2.0, 1.0]])
        q = _i5_np.array([[0.1, 0.2]])
        with self.assertRaises(ValueError):
            make_plan(height, q, recipe=_i5_ChannelRecipe(max_cut_m=-1.0))
        with self.assertRaises(ValueError):
            make_plan(height, _i5_np.array([[_i5_np.nan, 0.2]]))
        outlet = _i5_np.array([[False, True]])
        with self.assertRaises(ValueError):
            _i5_plan_channel(height, [1, 0], [0, 1], outlet, q, 1.0, 1.0, 0.0, 0.0, 0.0, 'test', _i5_ChannelRecipe())
        large = _i5_np.ones((3, 3))
        far_receiver = _i5_np.full(9, -1)
        far_receiver[0] = 8
        far_outlets = _i5_np.ones((3, 3), dtype=bool)
        far_outlets[0, 0] = False
        with self.assertRaises(ValueError):
            _i5_plan_channel(large, far_receiver, _i5_np.arange(9)[::-1], far_outlets, large, 1.0, 1.0, 0.0, 0.0, 0.0, 'test', _i5_ChannelRecipe())
        plan = make_plan(height, q)
        with _i5_tempfile.TemporaryDirectory() as directory:
            path = _i5_Path(directory) / 'plan.npz'
            _i5_save_plan(plan, path)
            reloaded = _i5_load_plan(path)
            self.assertEqual(plan['identity_sha256'], reloaded['identity_sha256'])
            for name, original in plan['arrays'].items():
                _i5_np.testing.assert_array_equal(original, reloaded['arrays'][name])
                self.assertFalse(reloaded['arrays'][name].flags.writeable)
            with self.assertRaises(FileExistsError):
                _i5_save_plan(plan, path)

    def test_plan_owns_inputs_and_rejects_channel_ending_before_outlet(self):
        height = _i5_np.array([[3.0, 2.0, 1.0]])
        q = _i5_np.array([[0.1, 0.1, 0.1]])
        plan = make_plan(height, q)
        identity = plan['identity_sha256']
        original_height = plan['arrays']['source_height_m'].copy()
        original_q = plan['arrays']['discharge_m3_s'].copy()
        height[0, 0] = 100.0
        q[0, 0] = 100.0
        _i5_np.testing.assert_array_equal(plan['arrays']['source_height_m'], original_height)
        _i5_np.testing.assert_array_equal(plan['arrays']['discharge_m3_s'], original_q)
        self.assertEqual(plan['identity_sha256'], identity)
        with self.assertRaisesRegex(ValueError, 'terminates before explicit outlet'):
            make_plan(_i5_np.array([[3.0, 2.0, 1.0]]), _i5_np.array([[0.1, 0.01, 0.01]]))

    def test_tampered_source_cannot_be_rehashed_without_identity_change(self):
        from terrain_pipeline.channel_geometry import load_plan as _i5_load_plan
        from terrain_pipeline.channel_geometry import save_plan as _i5_save_plan
        from terrain_pipeline.artifacts.contracts import array_hash as _i5_array_hash
        plan = make_plan(_i5_np.array([[3.0, 2.0, 1.0]]), _i5_np.array([[0.1, 0.1, 0.1]]))
        with _i5_tempfile.TemporaryDirectory() as directory:
            path = _i5_Path(directory) / 'plan.npz'
            _i5_save_plan(plan, path)
            with _i5_np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name].copy() for name in archive.files if name != 'manifest'}
                manifest = _i5_json.loads(str(archive['manifest'].item()))
            arrays['source_height_m'][0, 0] += 1.0
            manifest['array_sha256']['source_height_m'] = _i5_array_hash(arrays['source_height_m'])
            _i5_np.savez_compressed(path, manifest=_i5_json.dumps(manifest, sort_keys=True), **arrays)
            with self.assertRaisesRegex(ValueError, 'differs from identity'):
                _i5_load_plan(path)

    def test_failed_atomic_publication_leaves_no_destination_or_temp_file(self):
        from terrain_pipeline.channel_geometry import save_plan as _i5_save_plan
        plan = make_plan(_i5_np.array([[3.0, 2.0, 1.0]]), _i5_np.array([[0.1, 0.1, 0.1]]))
        with _i5_tempfile.TemporaryDirectory() as directory:
            path = _i5_Path(directory) / 'plan.npz'
            with _i5_patch('terrain_pipeline.channel_geometry.os.link', side_effect=OSError('link failed')):
                with self.assertRaisesRegex(OSError, 'link failed'):
                    _i5_save_plan(plan, path)
            self.assertFalse(path.exists())
            self.assertEqual(list(_i5_Path(directory).iterdir()), [])

def _test_metric_cutoff_terrain():
    from terrain_pipeline.common_infra import TerrainGrid as _i6_TerrainGrid
    height = _i6_np.zeros((15, 15), dtype=_i6_np.float64)
    return _i6_TerrainGrid(height, _i6_np.ones(height.shape, dtype=bool), 0.0, 0.0, 1.0, 1.0, 'diagnostic_dem_proxy', 'cutoff-test', 'a' * 64)

def centerline():
    return _i6_np.array([[2.0, 2.0], [2.0, 8.0], [5.0, 8.0], [8.0, 8.0], [8.0, 2.0], [10.0, 2.0]], dtype=_i6_np.float64)

class MetricCutoffTests(_i6_unittest.TestCase):

    def test_segment_filter_rejects_collinear_overlap_and_endpoint_touch(self):
        from terrain_pipeline.channel_geometry import _metric_cutoff_segments_intersect as _i6__segments_intersect
        shortcut_start = _i6_np.array([0.0, 0.0])
        shortcut_end = _i6_np.array([4.0, 0.0])
        self.assertTrue(_i6__segments_intersect(shortcut_start, shortcut_end, _i6_np.array([2.0, 0.0]), _i6_np.array([6.0, 0.0])))
        self.assertTrue(_i6__segments_intersect(shortcut_start, shortcut_end, _i6_np.array([4.0, 0.0]), _i6_np.array([4.0, 2.0])))
        self.assertFalse(_i6__segments_intersect(shortcut_start, shortcut_end, _i6_np.array([5.0, 0.0]), _i6_np.array([5.0, 2.0])))

    def test_only_shortcut_endpoint_incident_contacts_are_allowed(self):
        from terrain_pipeline.channel_geometry import _crosses_centerline as _i6__crosses_centerline
        centerline = _i6_np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]], dtype=_i6_np.float64)
        self.assertFalse(_i6__crosses_centerline(centerline[0], centerline[-1], centerline, 0, 4))
        self.assertTrue(_i6__crosses_centerline(_i6_np.array([0.0, 0.0]), _i6_np.array([0.5, 1.5]), centerline, 0, 4))

    def test_u_shape_success_and_event_contract(self):
        from terrain_pipeline.channel_geometry import CutoffConfig as _i6_CutoffConfig
        from terrain_pipeline.channel_geometry import find_cutoff_candidate as _i6_find_cutoff_candidate
        from terrain_pipeline.surface_rivers.metric_morphology_events import event_from_record as _i6_event_from_record
        result = _i6_find_cutoff_candidate(_test_metric_cutoff_terrain(), centerline(), tuple(('e%d' % i for i in range(5))), 'b' * 64, 'c' * 64, 3.0, 2.0, _i6_CutoffConfig(neck_distance_m=7.0, min_loop_length_m=5.0))
        self.assertEqual(result['status'], 'candidate')
        self.assertTrue(result['lake_candidate'])
        self.assertFalse(any(result['capabilities'].values()))
        event = result['event']
        self.assertEqual(event.event_type, 'cutoff')
        self.assertEqual(event.retired_edges, event.affected_edges)
        self.assertEqual(event.water_transfer_m3, 3.0)
        self.assertEqual(event.sediment_transfer_solid_m3, 2.0)
        self.assertEqual(_i6_event_from_record(event.to_record()).identity_sha256, event.identity_sha256)

    def test_no_legal_neck_and_unknown_or_ridge_are_rejected(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i6_TerrainGrid
        from terrain_pipeline.channel_geometry import CutoffConfig as _i6_CutoffConfig
        from terrain_pipeline.channel_geometry import find_cutoff_candidate as _i6_find_cutoff_candidate
        config = _i6_CutoffConfig(neck_distance_m=1.0, min_loop_length_m=5.0)
        self.assertEqual(_i6_find_cutoff_candidate(_test_metric_cutoff_terrain(), centerline(), tuple(('e%d' % i for i in range(5))), 'b' * 64, 'c' * 64, 0.0, 0.0, config)['status'], 'rejected')
        masked = _test_metric_cutoff_terrain().valid_mask.copy()
        masked[3, 5] = False
        unknown = _i6_TerrainGrid(_test_metric_cutoff_terrain().elevation_m, masked, 0.0, 0.0, 1.0, 1.0, 'diagnostic_dem_proxy', 'cutoff-test', 'a' * 64)
        self.assertEqual(_i6_find_cutoff_candidate(unknown, centerline(), tuple(('e%d' % i for i in range(5))), 'b' * 64, 'c' * 64, 0.0, 0.0, _i6_CutoffConfig(neck_distance_m=7.0, min_loop_length_m=5.0))['status'], 'rejected')
        ridge = _i6_np.zeros((15, 15), dtype=_i6_np.float64)
        ridge[2, 5] = 10.0
        ridge_terrain = _i6_TerrainGrid(ridge, _i6_np.ones(ridge.shape, dtype=bool), 0.0, 0.0, 1.0, 1.0, 'diagnostic_dem_proxy', 'cutoff-ridge', 'a' * 64)
        self.assertEqual(_i6_find_cutoff_candidate(ridge_terrain, centerline(), tuple(('e%d' % i for i in range(5))), 'b' * 64, 'c' * 64, 0.0, 0.0, _i6_CutoffConfig(neck_distance_m=7.0, min_loop_length_m=5.0))['status'], 'rejected')

    def test_deterministic_and_invalid_inputs(self):
        from terrain_pipeline.channel_geometry import CutoffConfig as _i6_CutoffConfig
        from terrain_pipeline.channel_geometry import find_cutoff_candidate as _i6_find_cutoff_candidate
        kwargs = dict(terrain=_test_metric_cutoff_terrain(), centerline_xz_m=centerline(), edge_ids=tuple(('e%d' % i for i in range(5))), parent_graph_identity_sha256='b' * 64, parent_geometry_identity_sha256='c' * 64, water_transfer_m3=0.0, sediment_transfer_solid_m3=0.0, config=_i6_CutoffConfig(neck_distance_m=7.0, min_loop_length_m=5.0, seed=7))
        first, second = (_i6_find_cutoff_candidate(**kwargs), _i6_find_cutoff_candidate(**kwargs))
        self.assertEqual(first['event'].identity_sha256, second['event'].identity_sha256)
        with self.assertRaises(ValueError):
            _i6_CutoffConfig(min_node_gap=1)
        with self.assertRaises(ValueError):
            _i6_find_cutoff_candidate(**{**kwargs, 'centerline_xz_m': centerline().astype(_i6_np.float32)})
        with self.assertRaises(ValueError):
            _i6_find_cutoff_candidate(**{**kwargs, 'water_transfer_m3': -1.0})

class ContinuousDesignBedTests(_i7_unittest.TestCase):

    def test_floor_clip_tolerance_does_not_extrapolate_triangle_edges(self):
        from terrain_pipeline.channel_geometry import _clip_floor_polygon
        polygon = _i7_np.array([[1.1e-10, 0.0], [9e-11, 1.0], [9e-11, 0.0]])
        clipped = _clip_floor_polygon(polygon, _i7_np.array([1.0, 0.0]), 0.0)
        self.assertGreaterEqual(len(clipped), 3)
        self.assertTrue(_i7_np.all(clipped >= polygon.min(axis=0)))
        self.assertTrue(_i7_np.all(clipped <= polygon.max(axis=0)))

    def test_four_arm_junction_floor_retains_every_arm(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i7_TerrainGrid
        from terrain_pipeline.channel_geometry import _sparse_mesh as _i7__sparse_mesh
        from terrain_pipeline.channel_geometry import continuous_center_floor_constraints
        from terrain_pipeline.channel_geometry import _edge_continuous_floor_constraints
        terrain = _i7_TerrainGrid(_i7_np.full((2, 2), 101.0), _i7_np.ones((2, 2), bool), 0.0, 0.0, 30.0, 30.0, 'observed_dem', 'four-arm', 'f' * 64)
        points = _i7_np.array([[15.0, 15.0], [5.0, 15.0], [15.0, 5.0], [15.0, 25.0], [25.0, 15.0]])
        receiver = _i7_np.array([4, 0, 0, 0, -1])
        width = _i7_np.full(5, 4.0)
        zz, xx = _i7_np.indices((30, 30))
        cells = _i7_np.column_stack((xx.ravel(), zz.ravel()))
        vertices, triangles = _i7__sparse_mesh(cells, terrain, 1.0, 10000)
        source, maximum = (_i7_np.full(len(vertices), 101.0), _i7_np.full(len(vertices), 4.0))
        ids, weights, rhs = continuous_center_floor_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, 1.0, maximum)
        counts = [len(_edge_continuous_floor_constraints(node, points, receiver, width, cells, vertices, triangles, source, terrain, 1.0, maximum, junction=0)[2]) for node in range(4)]
        self.assertTrue(all((count > 0 for count in counts)))
        self.assertEqual(len(rhs), sum(counts))
        _i7_np.testing.assert_allclose(_i7_np.sum(weights * _i7_np.full(len(vertices), 100.0)[ids], axis=1), 0.0, atol=1e-10)

    def test_explicit_support_radius_preserves_default_and_rejects_invalid_edges(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i7_TerrainGrid
        from terrain_pipeline.channel_geometry import _sparse_cells as _i7__sparse_cells
        terrain = _i7_TerrainGrid(_i7_np.full((2, 2), 10.0), _i7_np.ones((2, 2), bool), 0.0, 0.0, 30.0, 30.0, 'observed_dem', 'radius', 'e' * 64)
        points = _i7_np.array([[8.0, 15.0], [22.0, 15.0]])
        receiver, width = (_i7_np.array([1, -1]), _i7_np.full(2, 4.0))
        profile = (_i7_np.array([0, 2]), _i7_np.array([0.0, 1.0]), _i7_np.full(2, 10.0), _i7_np.array([9.5, 9.4999]))
        options = _i7_SimpleNamespace(fine_spacing_m=1.0, max_vertices=10000)
        default = _i7__sparse_cells(points, receiver, width, profile, options, terrain)
        explicit = _i7__sparse_cells(points, receiver, width, profile, options, terrain, support_radius_m=_i7_np.array([2.0 + 2.0 * 0.5001]))
        _i7_np.testing.assert_array_equal(default, explicit)
        for radius in (_i7_np.array([]), _i7_np.array([1.0, 2.0]), _i7_np.array([_i7_np.nan]), _i7_np.array([_i7_np.inf]), _i7_np.array([-1.0]), _i7_np.array([0.0]), 2.0):
            with self.subTest(radius=radius):
                with self.assertRaisesRegex(ValueError, 'support radius'):
                    _i7__sparse_cells(points, receiver, width, profile, options, terrain, support_radius_m=radius)

    def test_chunked_material_volume_matches_full_mesh_across_batch_boundary(self):
        from terrain_pipeline.channel_geometry import _mesh_volume_chunked as _i7__mesh_volume_chunked
        from terrain_pipeline.channel_geometry import _mesh_volume
        vertices = _i7_np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 2.0]])
        triangles = _i7_np.tile(_i7_np.array([[0, 1, 2]]), (200003, 1))
        cut = _i7_np.array([0.125, 0.375, 0.8125])
        for datum in (0.0, 0.25):
            expected = _mesh_volume(vertices, triangles, cut, datum=datum)
            actual = _i7__mesh_volume_chunked(vertices, triangles, cut, datum=datum)
            _i7_np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=0.0)

    def transverse_fixture(self, points, receiver, width=4.0):
        from terrain_pipeline.common_infra import TerrainGrid as _i7_TerrainGrid
        from terrain_pipeline.channel_geometry import build_design_geometry as _i7_build_design_geometry
        terrain = _i7_TerrainGrid(_i7_np.full((2, 2), 10.0), _i7_np.ones((2, 2), bool), 0.0, 0.0, 30.0, 30.0, 'observed_dem', 'shape', 'c' * 64)
        edges = _i7_np.flatnonzero(receiver >= 0)
        beds = 8.0 - points[:, 0] * 0.001
        profile = (_i7_np.arange(0, 2 * len(edges) + 1, 2), _i7_np.tile([0.0, 1.0], len(edges)), _i7_np.full(2 * len(edges), 10.0), _i7_np.column_stack((beds[edges], beds[receiver[edges]])).ravel())
        result = _i7_build_design_geometry(points, receiver, _i7_np.full(len(points), width), _i7_np.full(len(points), 0.5), profile, terrain, 1.0, 4.0, 1e-05)
        return (terrain, result)

    def test_actual_deep_profile_has_full_bottom_instead_of_center_slot(self):
        from terrain_pipeline.channel_geometry import _mesh_height as _i7__mesh_height
        points = _i7_np.array([[8.0, 15.0], [22.0, 15.0]])
        terrain, result = self.transverse_fixture(points, _i7_np.array([1, -1]))
        cells, vertices, triangles, source, _, cut, closure = result[:7]
        lookup = {tuple(cell): i for i, cell in enumerate(cells)}
        bed = source - cut
        for x in (10.0, 15.0, 20.0):
            center = _i7__mesh_height(_i7_np.array([x, 15.0]), lookup[int(x), 15], vertices, triangles, bed)
            for z in _i7_np.linspace(13.0, 17.0, 17):
                actual = _i7__mesh_height(_i7_np.array([x, z]), lookup[int(x), int(z)], vertices, triangles, bed)
                self.assertLessEqual(actual, center + abs(z - 15.0) * 0.02 + 1e-08)
        self.assertTrue(closure['transverse_bed_coupling'])
        self.assertLessEqual(closure['maximum_transverse_residual_m'], 1e-08)
        self.assertTrue(_i7_np.all(cut[result[-1]] == 0.0))
        self.assertLessEqual(float(cut.max()), 4.0)
        self.assertTrue(_i7_np.all(terrain.elevation_m == 10.0))

    def test_small_bend_and_shared_confluence_preserve_physical_limits(self):
        examples = ((_i7_np.array([[8.0, 14.0], [15.0, 15.0], [22.0, 15.0]]), _i7_np.array([1, 2, -1])), (_i7_np.array([[8.0, 12.0], [8.0, 18.0], [15.0, 15.0], [22.0, 15.0]]), _i7_np.array([2, 2, 3, -1])))
        for points, receiver in examples:
            with self.subTest(receiver=receiver):
                _, result = self.transverse_fixture(points, receiver)
                self.assertLessEqual(float(result[5].max()), 4.0)
                self.assertLessEqual(result[6]['maximum_gradient_residual_m_per_m'], 1e-08)
                self.assertLessEqual(result[6]['maximum_transverse_residual_m'], 1e-08)

    def test_outer_bend_wedge_and_source_terminal_caps_follow_actual_node_bed(self):
        from terrain_pipeline.channel_geometry import _mesh_height as _i7__mesh_height
        examples = ((_i7_np.array([[8.0, 12.0], [15.0, 15.0], [22.0, 15.0]]), _i7_np.array([1, 2, -1]), 6.0, ((1, _i7_np.array([14.5, 17.5])),)), (_i7_np.array([[8.0, 15.0], [22.0, 15.0]]), _i7_np.array([1, -1]), 4.0, ((0, _i7_np.array([7.0, 16.0])), (1, _i7_np.array([23.0, 16.0])))))
        for points, receiver, width, probes in examples:
            terrain, result = self.transverse_fixture(points, receiver, width)
            cells, vertices, triangles, source, _, cut = result[:6]
            lookup = {tuple(cell): i for i, cell in enumerate(cells)}
            bed = source - cut
            for node, probe in probes:
                center = _i7__mesh_height(points[node], lookup[tuple(points[node].astype(int))], vertices, triangles, bed)
                actual = _i7__mesh_height(probe, lookup[tuple(probe.astype(int))], vertices, triangles, bed)
                radius = float(_i7_np.linalg.norm(probe - points[node]))
                self.assertLessEqual(actual, center + radius * 0.02 + 1e-08)
            self.assertTrue(_i7_np.all(cut[result[-1]] == 0.0))
            self.assertLessEqual(float(cut.max()), 4.0)
            self.assertGreater(result[6]['transverse_node_cap_constraints'], 0)

    def test_wide_bottom_rejects_real_four_meter_budget_conflict(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i7_TerrainGrid
        from terrain_pipeline.channel_geometry import build_design_geometry as _i7_build_design_geometry
        terrain = _i7_TerrainGrid(_i7_np.array([[10.0, 10.0], [70.0, 70.0]]), _i7_np.ones((2, 2), bool), 0.0, 0.0, 30.0, 30.0, 'observed_dem', 'steep', 'd' * 64)
        points = _i7_np.array([[8.0, 15.0], [22.0, 15.0]])
        profile = (_i7_np.array([0, 2]), _i7_np.array([0.0, 1.0]), _i7_np.array([40.0, 40.0]), _i7_np.array([38.0, 37.999]))
        with self.assertRaisesRegex(ValueError, 'cut bounds or is infeasible'):
            _i7_build_design_geometry(points, _i7_np.array([1, -1]), _i7_np.full(2, 4.0), _i7_np.full(2, 0.5), profile, terrain, 1.0, 4.0, 1e-05)

    def test_mixed_global_keeps_legacy_cut_and_new_design_profile(self):
        from terrain_pipeline.channel_geometry import merge_design_bundles as _i7_merge_design_bundles
        terrain, cells, vertices, triangles = self.fixture(_i7_np.array([[10.0, 9.0], [10.0, 9.0]]))
        source = 10.0 - vertices[:, 0] / 4.0
        bundles = []
        for z, new in ((1.0, False), (3.0, True)):
            points = _i7_np.array([[0.5, z], [3.5, z]])
            a = dict(source_node_cell_ids=_i7_np.array([0, 1]), receiver=_i7_np.array([1, -1]), node_xz_m=points, width_m=_i7_np.ones(2), base_depth_m=_i7_np.ones(2), sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, cut_depth_m=_i7_np.full(len(vertices), 1.0 if new else 4.0), profile_offsets=_i7_np.array([0, 2]), profile_t=_i7_np.array([0.0, 1.0]), profile_source_m=10.0 - points[:, 0] / 4.0, profile_center_bed_m=9.0 - points[:, 0] / 4.0)
            if new:
                a.update(design_minimum_cut_m=_i7_np.full(len(vertices), 0.25), source_interpolation_padding_m=_i7_np.zeros(len(vertices)))
            bundles.append(dict(arrays=a))
        from terrain_pipeline.surface_rivers.metric_td_generated_rivers import GeneratedRiverConfig
        with self.assertRaisesRegex(ValueError, 'cut bounds or is infeasible'):
            _i7_merge_design_bundles(terrain, bundles, GeneratedRiverConfig(), _i7_np.array([0.25, 0.25]))
        config = GeneratedRiverConfig(transverse_bottom_slope_m_per_m=0.3)
        result = _i7_merge_design_bundles(terrain, bundles, config, _i7_np.array([0.25, 0.25]))
        a = result['arrays']
        self.assertTrue(_i7_np.all(a['cut_depth_m'] == 4.0))
        self.assertTrue(_i7_np.array_equal(a['design_constraint_node_mask'], [False, False, True, True]))
        self.assertTrue(_i7_np.array_equal(a['profile_offsets'], [0, 2, 4]))
        self.assertAlmostEqual(result['metadata']['cut_volume_m3'], 64.0)
        self.assertTrue(_i7_np.all(a['design_maximum_cut_m'] == 4.0))
        bundles[1]['arrays']['source_interpolation_padding_m'] = _i7_np.full(len(vertices), 0.001)
        with self.assertRaisesRegex(ValueError, 'ordered nonnegative cut bounds'):
            _i7_merge_design_bundles(terrain, bundles, config, _i7_np.array([0.25, 0.25]))

    def test_expanded_banks_reconnect_to_known_source(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i7_TerrainGrid
        from terrain_pipeline.channel_geometry import build_design_geometry as _i7_build_design_geometry
        terrain = _i7_TerrainGrid(_i7_np.full((2, 2), 10.0), _i7_np.ones((2, 2), bool), 0.0, 0.0, 40.0, 40.0, 'observed_dem', 'bank', 'b' * 64)
        points = _i7_np.array([[16.0, 20.0], [24.0, 20.0]])
        profile = (_i7_np.array([0, 2]), _i7_np.array([0.0, 1.0]), _i7_np.array([10.0, 10.0]), _i7_np.array([9.5, 9.4999]))
        result = _i7_build_design_geometry(points, _i7_np.array([1, -1]), _i7_np.array([1.0, 1.0]), _i7_np.array([0.5, 0.5]), profile, terrain, 1.0, 4.0, 1e-05)
        cut, boundary = (result[5], result[-1])
        self.assertGreater(len(boundary), 0)
        self.assertTrue(_i7_np.all(cut[boundary] == 0.0))

    def fixture(self, heights=None, spacing=1.0):
        from terrain_pipeline.common_infra import TerrainGrid as _i7_TerrainGrid
        from terrain_pipeline.channel_geometry import _sparse_mesh as _i7__sparse_mesh
        terrain = _i7_TerrainGrid(_i7_np.full((2, 2), 10.0) if heights is None else heights, _i7_np.ones((2, 2), bool), 0.0, 0.0, 4.0, 4.0, 'observed_dem', 'design', 'a' * 64)
        count = int(4.0 / spacing)
        cells = _i7_np.array([(x, z) for z in range(count) for x in range(count)], _i7_np.int64)
        vertices, triangles = _i7__sparse_mesh(cells, terrain, spacing, 10000)
        return (terrain, cells, vertices, triangles)

    def test_fan4_padding_bounds_bilinear_interpolation_error(self):
        from terrain_pipeline.channel_geometry import source_interpolation_padding as _i7_source_interpolation_padding
        terrain, cells, vertices, triangles = self.fixture(_i7_np.array([[10.0, 10.0], [10.0, 14.0]]), 0.5)
        source = 10.0 + vertices[:, 0] * vertices[:, 1] / 4.0
        padding = _i7_source_interpolation_padding(cells, vertices, triangles, terrain, 0.5)
        self.assertAlmostEqual(float(padding.max()), 0.25 * 0.5 ** 2 / 16.0)
        for face, ids in enumerate(triangles):
            for u in _i7_np.linspace(0.0, 1.0, 9):
                for v in _i7_np.linspace(0.0, 1.0 - u, 9):
                    weights = _i7_np.array([1.0 - u - v, u, v])
                    point = weights @ vertices[ids]
                    actual = 10.0 + point[0] * point[1] / 4.0
                    error = abs(actual - weights @ source[ids])
                    self.assertLessEqual(error, float(padding[ids].max()) + 1e-12)

    def test_conservative_bottom_preserves_depth_between_vertices(self):
        from terrain_pipeline.channel_geometry import design_cut_bounds as _i7_design_cut_bounds
        from terrain_pipeline.channel_geometry import _mesh_height as _i7__mesh_height
        terrain, cells, vertices, triangles = self.fixture(_i7_np.array([[10.0, 10.0], [10.0, 14.0]]), 0.5)
        points = _i7_np.array([[0.5, 2.0], [3.5, 2.0]])
        lower, _, _ = _i7_design_cut_bounds(points, _i7_np.array([1, -1]), _i7_np.array([0.7, 0.7]), _i7_np.array([0.3, 0.5]), cells, vertices, triangles, terrain, 0.5, 4.0)
        source = 10.0 + vertices[:, 0] * vertices[:, 1] / 4.0
        lookup = {tuple(cell): index for index, cell in enumerate(cells)}
        for t in _i7_np.linspace(0.0, 1.0, 21):
            for cross in _i7_np.linspace(-0.35, 0.35, 11):
                point = points[0] + t * (points[1] - points[0]) + _i7_np.array([0.0, cross])
                key = tuple(_i7_np.floor(point / 0.5).astype(int))
                bed = _i7__mesh_height(point, lookup[key], vertices, triangles, source - lower)
                raw = 10.0 + point[0] * point[1] / 4.0
                self.assertGreaterEqual(raw - bed, 0.3 + 0.2 * t - 1e-10)

    def test_profile_internal_knot_is_preserved_by_physical_bed(self):
        from terrain_pipeline.channel_geometry import solve_design_bed as _i7_solve_design_bed
        from terrain_pipeline.channel_geometry import _mesh_height as _i7__mesh_height
        terrain, cells, vertices, triangles = self.fixture()
        points = _i7_np.array([[0.5, 2.0], [3.5, 2.0]])
        receiver = _i7_np.array([1, -1])
        source = _i7_np.full(len(vertices), 10.0)
        profile = (_i7_np.array([0, 3]), _i7_np.array([0.0, 0.3, 1.0]), _i7_np.array([10.0, 10.0, 10.0]), _i7_np.array([9.5, 8.5, 8.49]))
        cut, metadata = _i7_solve_design_bed(points, receiver, cells, vertices, triangles, source, _i7_np.full(len(vertices), 0.25), _i7_np.full(len(vertices), 4.0), terrain, 1.0, profile, 1e-05)
        lookup = {tuple(cell): index for index, cell in enumerate(cells)}
        for t in _i7_np.linspace(0.0, 1.0, 101):
            point = points[0] + t * (points[1] - points[0])
            key = tuple(_i7_np.floor(point).astype(int))
            bed = _i7__mesh_height(point, lookup[key], vertices, triangles, source - cut)
            target = _i7_np.interp(t, profile[1], profile[3])
            self.assertLessEqual(bed, target + 1e-08)
        self.assertTrue(metadata['profile_mesh_breakpoint_union'])
        self.assertLess(float(cut.max()), 4.0)

class DischargeGeometryTests(_i8_unittest.TestCase):

    def fixture(self):
        source = _i8_np.full((9, 9), 100.0)
        channel = _i8_np.zeros(source.shape, bool)
        channel[4, :] = True
        monthly = _i8_np.ones((12, *source.shape))
        return (source, monthly, channel)

    def test_confluence_discharge_increases_both_dimensions(self):
        from terrain_pipeline.channel_geometry import build_discharge_geometry as _i8_build_discharge_geometry
        source, monthly, channel = self.fixture()
        monthly[:, 4, 4:] = 3.0
        original = source.copy()
        arrays = _i8_build_discharge_geometry(source, monthly, channel, 1.0)['arrays']
        self.assertGreater(arrays['channel_width_m'][4, 4], arrays['channel_width_m'][4, 3])
        self.assertGreater(arrays['channel_depth_m'][4, 4], arrays['channel_depth_m'][4, 3])
        _i8_np.testing.assert_array_equal(source, original)

    def test_hard_bed_soft_bank_widens_soft_bed_incises(self):
        from terrain_pipeline.channel_geometry import build_discharge_geometry as _i8_build_discharge_geometry
        source, monthly, channel = self.fixture()
        hard = _i8_build_discharge_geometry(source, monthly, channel, 1.0, bed_hardness=1.0, bank_hardness=0.0)['arrays']
        soft = _i8_build_discharge_geometry(source, monthly, channel, 1.0, bed_hardness=0.0, bank_hardness=0.0)['arrays']
        self.assertGreater(hard['channel_width_m'][4, 4], soft['channel_width_m'][4, 4])
        self.assertLess(hard['channel_depth_m'][4, 4], soft['channel_depth_m'][4, 4])
        bank = _i8_build_discharge_geometry(source, monthly, channel, 1.0, bed_hardness=1.0, bank_hardness=1.0)['arrays']
        self.assertLess(bank['channel_width_m'][4, 4], hard['channel_width_m'][4, 4])
        self.assertGreater(bank['channel_depth_m'][4, 4], hard['channel_depth_m'][4, 4])

    def test_profile_and_actual_raster_excavation_budget(self):
        from terrain_pipeline.channel_geometry import build_discharge_geometry as _i8_build_discharge_geometry
        from terrain_pipeline.channel_geometry import channel_section_cut as _i8_channel_section_cut
        _i8_np.testing.assert_allclose(_i8_channel_section_cut([-5.0, -3.0, 0.0, 3.0, 4.0, 5.0], 10.0, 2.0), [0.0, 2.0, 2.0, 2.0, 1.0, 0.0])
        source, monthly, channel = self.fixture()
        protected = _i8_np.zeros(source.shape, bool)
        protected[:, 0] = True
        result = _i8_build_discharge_geometry(source, monthly, channel, 1.0, protected_mask=protected)
        cut = result['arrays']['cut_depth_m']
        self.assertTrue((cut[:, 0] == 0.0).all())
        unprotected = _i8_build_discharge_geometry(source, monthly, channel, 1.0)['arrays']
        for key in ('channel_width_m', 'bottom_width_m', 'channel_depth_m'):
            _i8_np.testing.assert_array_equal(result['arrays'][key], unprotected[key])
            self.assertGreater(result['arrays'][key][4, 0], 0.0)
        entirely_protected = _i8_build_discharge_geometry(source, monthly, channel, 1.0, protected_mask=_i8_np.ones(source.shape, bool))['arrays']
        self.assertFalse(entirely_protected['cut_depth_m'].any())
        _i8_np.testing.assert_array_equal(entirely_protected['channel_width_m'], unprotected['channel_width_m'])
        _i8_np.testing.assert_allclose(result['arrays']['bed_elevation_m'], source - cut)
        ledger = result['metadata']['material_budget']
        self.assertAlmostEqual(ledger['removed_terrain_bulk_m3'], cut.sum())
        self.assertEqual(ledger['unplaced_excavated_bulk_m3'], ledger['removed_terrain_bulk_m3'])

    def test_zero_flow_exposure_and_four_metre_cap(self):
        from terrain_pipeline.channel_geometry import DischargeGeometryConfig as _i8_DischargeGeometryConfig
        from terrain_pipeline.channel_geometry import build_discharge_geometry as _i8_build_discharge_geometry
        source, monthly, channel = self.fixture()
        for q, exposure in ((0.0, 3.0), (1.0, 0.0)):
            monthly[:] = q
            arrays = _i8_build_discharge_geometry(source, monthly, channel, 1.0, config=_i8_replace(_i8_DischargeGeometryConfig(), generation_exposure=exposure))['arrays']
            self.assertFalse(arrays['cut_depth_m'].any())
            self.assertFalse(arrays['channel_width_m'].any())
        monthly[:] = 1000000.0
        arrays = _i8_build_discharge_geometry(source, monthly, channel, 1.0)['arrays']
        self.assertLessEqual(arrays['cut_depth_m'].max(), 4.0)
        with self.assertRaises(ValueError):
            _i8_DischargeGeometryConfig(max_incise_m=4.1)

    def test_duration_mean_determinism_and_input_rejection(self):
        from terrain_pipeline.channel_geometry import build_discharge_geometry as _i8_build_discharge_geometry
        source, monthly, channel = self.fixture()
        monthly[0] = 2.0
        a = _i8_build_discharge_geometry(source, monthly, channel, 1.0)
        b = _i8_build_discharge_geometry(source, monthly, channel, 1.0)
        self.assertGreater(a['arrays']['representative_q_m3_s'][0, 0], 1.0)
        for key in a['arrays']:
            _i8_np.testing.assert_array_equal(a['arrays'][key], b['arrays'][key])
        saved_mean = a['arrays']['representative_q_m3_s']
        direct = _i8_build_discharge_geometry(source, saved_mean, channel, 1.0)
        for key in a['arrays']:
            _i8_np.testing.assert_array_equal(a['arrays'][key], direct['arrays'][key])
        with self.assertRaises(ValueError):
            _i8_build_discharge_geometry(source, monthly[:1], channel, 1.0)
        with self.assertRaises(ValueError):
            _i8_build_discharge_geometry(source, monthly, channel, 1.0, bed_hardness=1.1)
        monthly[0, 0, 0] = _i8_np.nan
        with self.assertRaises(ValueError):
            _i8_build_discharge_geometry(source, monthly, channel, 1.0)

def inputs():
    from terrain_pipeline.channel_geometry import GeometryConfig as _i9_GeometryConfig
    source = terrain()
    shape = source.elevation_m.shape
    ids = _i9_np.array([29, 31, 32], _i9_np.int64)
    receiver = _i9_np.full(source.elevation_m.size, -1, _i9_np.int64)
    receiver[ids[:-1]] = ids[1:]
    topology = {'height_m': source.elevation_m, 'accepted': _i9_np.ones(shape, bool), 'owner_outlet_x_m': _i9_np.full(shape, 20.0), 'owner_outlet_z_m': _i9_np.full(shape, 12.0), 'ocean_terminal': _i9_np.ones(shape, bool), 'receiver': receiver.reshape(shape)}
    options = dict(node_cell_ids=ids, receiver=_i9_np.array([1, 2, -1]), width_m=_i9_np.full(3, 2.0), depth_m=_i9_np.full(3, 0.5), owner_xz_m=_i9_np.tile([20.0, 12.0], (3, 1)), owner_grid=_i9_np.zeros(shape, _i9_np.int64), corridor_mask=_i9_np.ones(shape, bool), lake_mask=_i9_np.zeros(shape, bool), anchor_mask=_i9_np.zeros(3, bool), outlet_x_m=20.0, outlet_z_m=12.0, terminal_kind='ocean', config=_i9_GeometryConfig(fine_spacing_m=0.5))
    return (source, topology, options)

class DomainChannelGeometryTests(_i9_unittest.TestCase):

    def test_three_node_chain_with_terminal_builds_and_validates(self):
        from terrain_pipeline.channel_geometry import build_domain_channel_geometry as _i9_build_domain_channel_geometry
        from terrain_pipeline.channel_geometry import validate_domain_channel_geometry as _i9_validate_domain_channel_geometry
        source, topology, options = inputs()
        record = _i9_build_domain_channel_geometry(source, topology, **options)
        self.assertTrue(_i9_validate_domain_channel_geometry(record))
        _i9_np.testing.assert_array_equal(record['arrays']['channel_receiver'], [1, 2, -1])
        self.assertEqual(record['metadata']['node_count'], 3)

    def test_actual_link_crossing_owner_is_refused(self):
        from terrain_pipeline.channel_geometry import build_domain_channel_geometry as _i9_build_domain_channel_geometry
        source, topology, options = inputs()
        options['owner_grid'].ravel()[31] = 1
        with self.assertRaisesRegex(ValueError, 'receiver crosses domain ownership'):
            _i9_build_domain_channel_geometry(source, topology, **options)

class LocalBedAssessmentTests(_i10_unittest.TestCase):

    def setUp(self):
        self.points = _i10_np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 0.0], [4.0, 0.0]])
        self.receiver = _i10_np.array([1, -1, 3, -1])
        self.width = _i10_np.full(4, 2.0)
        self.depth = _i10_np.full(4, 0.25)

    def test_exact_support_includes_overlap_ties_and_spacing_guard(self):
        from terrain_pipeline.channel_geometry import design_support_edges as _i10_design_support_edges
        point = _i10_np.array([2.0, 2.5])
        edges = _i10_design_support_edges(point, self.points, self.receiver, self.width, self.depth, 2.0, 0.26, 0.01)
        self.assertEqual([(source, target) for source, target, _ in edges], [(0, 1), (2, 3)])
        self.assertEqual(_i10_design_support_edges(point, self.points, self.receiver, self.width, self.depth, 0.5, 0.26, 0.01), [])

    def test_nonmatching_lower_bound_cannot_invent_support(self):
        from terrain_pipeline.channel_geometry import design_support_edges as _i10_design_support_edges
        self.assertEqual(_i10_design_support_edges(_i10_np.array([2.0, 0.0]), self.points, self.receiver, self.width, self.depth, 1.0, 0.5, 0.01), [])

    def test_adapter_uses_primitive_and_attributes_verified_dual_roots(self):
        from terrain_pipeline.channel_geometry import assess_local_bed as _i10_assess_local_bed
        model = dict(vertices=_i10_np.array([[2.0, 0.0]]), bounds=_i10_np.array([[0.26, 4.0]]), source_padding=_i10_np.array([0.01]), transverse_radius_policy='relaxation', boundary_policy='no artificial crop boundary')
        result = dict(status=2, outcome='infeasible', message='actual row conflict', variable_count=1, row_count=2, solver_calls=2, extra_cut=dict(certificate_valid=True, minimum_extra_ceiling_m=0.02, root_vertex_indices=[0], root_lower_bound_duals=[1.0]))
        with _i10_patch('terrain_pipeline.channel_geometry.build_local', return_value=model) as build:
            with _i10_patch('terrain_pipeline.channel_geometry.assess_local', return_value=result) as solve:
                assessment = _i10_assess_local_bed(self.points, self.receiver, self.width, self.depth, None, None, {}, spacing=2.0, max_cut=3.0, bottom_slope=0.03, minimum_slope=2e-05)
        self.assertEqual(assessment['contributing_edges'], [(0, 1), (2, 3)])
        self.assertEqual(assessment['solver_calls'], 2)
        self.assertEqual(build.call_args.kwargs, dict(spacing=2.0, max_cut=3.0, bottom_slope=0.03, minimum_slope=2e-05))
        self.assertEqual(solve.call_count, 1)

    def test_unverified_extra_cut_has_no_search_witness(self):
        from terrain_pipeline.channel_geometry import assess_local_bed as _i10_assess_local_bed
        model = dict(transverse_radius_policy='relaxation', boundary_policy='relaxation')
        result = dict(status=2, outcome='infeasible', message='conflict', variable_count=1, row_count=2, extra_cut=dict(certificate_valid=False))
        with _i10_patch('terrain_pipeline.channel_geometry.build_local', return_value=model):
            with _i10_patch('terrain_pipeline.channel_geometry.assess_local', return_value=result):
                assessment = _i10_assess_local_bed(self.points, self.receiver, self.width, self.depth, None, None, {}, spacing=1.0, max_cut=4.0, bottom_slope=0.02, minimum_slope=1e-05)
        self.assertNotIn('contributing_edges', assessment)
        self.assertNotIn('extra_cut', assessment)

def signatures(matrix, kinds, limits, vertices):
    result = []
    for row in range(matrix.shape[0]):
        lo, hi = matrix.indptr[row:row + 2]
        ids, weights = (matrix.indices[lo:hi], matrix.data[lo:hi])
        order = _i11_np.lexsort((vertices[ids, 0], vertices[ids, 1]))
        result.append((str(kinds[row]), tuple(map(tuple, vertices[ids[order]])), tuple(weights[order]), float(limits[row])))
    return _i11_Counter(result)

class LocalDesignBedTests(_i11_unittest.TestCase):

    def fixture(self, points, receiver):
        from terrain_pipeline.channel_geometry import _metric_channel_geometry_sample as _i11__sample
        from terrain_pipeline.common_infra import TerrainGrid as _i11_TerrainGrid
        x, z = _i11_np.meshgrid(_i11_np.arange(9.0), _i11_np.arange(9.0))
        terrain = _i11_TerrainGrid(20.0 - 0.1 * x + 0.003 * x * z, _i11_np.ones((9, 9), bool), 0.0, 0.0, 10.0, 10.0, 'observed_dem', 'local-model', 'a' * 64)
        edges = _i11_np.flatnonzero(receiver >= 0)
        source = _i11__sample(terrain.elevation_m, points, terrain)[0]
        bed = source - 1.0
        profile = (_i11_np.arange(0, 2 * len(edges) + 1, 2), _i11_np.tile([0.0, 1.0], len(edges)), _i11_np.column_stack((source[edges], source[receiver[edges]])).ravel(), _i11_np.column_stack((bed[edges], bed[receiver[edges]])).ravel())
        return (terrain, _i11_np.full(len(points), 4.0), _i11_np.full(len(points), 0.5), profile)

    def full_model(self, points, receiver, terrain, width, depth, profile, parameters):
        from terrain_pipeline.channel_geometry import _metric_channel_geometry_sample as _i11__sample
        from terrain_pipeline.channel_geometry import bed_constraints as _i11_bed_constraints
        from terrain_pipeline.channel_geometry import design_cut_bounds as _i11_design_cut_bounds
        from terrain_pipeline.channel_geometry import interior_support_boundary_vertices as _i11_interior_support_boundary_vertices
        from terrain_pipeline.channel_geometry import transverse_bed_constraints as _i11_transverse_bed_constraints
        from terrain_pipeline.channel_geometry import _sparse_cells as _i11__sparse_cells
        from terrain_pipeline.channel_geometry import _sparse_mesh as _i11__sparse_mesh
        spacing, max_cut = (parameters['spacing'], parameters['max_cut'])
        edges = _i11_np.flatnonzero(receiver >= 0)
        radius = _i11_np.maximum(width[edges], width[receiver[edges]]) / 2.0 + (_i11_np.sqrt(2.0) + 1.0) * spacing + 2.0 * max_cut
        cells = _i11__sparse_cells(points, receiver, width, profile, _i11_SimpleNamespace(fine_spacing_m=spacing, max_vertices=100000), terrain, support_radius_m=radius)
        vertices, triangles = _i11__sparse_mesh(cells, terrain, spacing, 100000)
        source = _i11__sample(terrain.elevation_m, vertices, terrain)[0]
        lower, upper, padding = _i11_design_cut_bounds(points, receiver, width, depth, cells, vertices, triangles, terrain, spacing, max_cut)
        upper[_i11_interior_support_boundary_vertices(cells, vertices, terrain, spacing)] = 0.0
        base = _i11_bed_constraints(points, receiver, cells, vertices, triangles, source, terrain, spacing, profile, parameters['minimum_slope'])
        transverse = _i11_transverse_bed_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, spacing, upper, None, parameters['bottom_slope'])
        strips = len(transverse[2]) - transverse[3]
        rows = base + [(ids, weights, limit, 'strip' if i < strips else 'cap') for i, (ids, weights, limit) in enumerate(zip(*transverse[:3]))]
        rr, cc, vv = ([], [], [])
        for row, (ids, weights, _, _) in enumerate(rows):
            rr.extend([row] * len(ids))
            cc.extend(ids)
            vv.extend(weights)
        matrix = _i11_coo_matrix((vv, (rr, cc)), shape=(len(rows), len(vertices))).tocsr()
        matrix.eliminate_zeros()
        return dict(matrix=matrix, vertices=vertices, source=source, bounds=_i11_np.column_stack((lower, upper)), source_padding=padding, limits=_i11_np.array([row[2] for row in rows]), kinds=_i11_np.array([row[3] for row in rows]))

    def test_cropped_bend_and_confluence_have_exact_full_rows_and_bounds(self):
        from terrain_pipeline.channel_geometry import build_local as _i11_build_local
        examples = ((_i11_np.array([[4.0, 8.0], [22.0, 18.0], [40.0, 32.0], [68.0, 32.0]]), _i11_np.array([1, 2, 3, -1]), [22.0, 18.0]), (_i11_np.array([[4.0, 18.0], [4.0, 26.0], [25.0, 22.0], [45.0, 22.0], [68.0, 22.0]]), _i11_np.array([2, 2, 3, 4, -1]), [25.0, 22.0]))
        parameters = dict(spacing=0.5, max_cut=3.0, bottom_slope=0.03, minimum_slope=2e-05)
        for points, receiver, center in examples:
            with self.subTest(receiver=receiver):
                terrain, width, depth, profile = self.fixture(points, receiver)
                full = self.full_model(points, receiver, terrain, width, depth, profile, parameters)
                window = dict(center_xz_m=center, side_m=12.0)
                maximum = float(full['bounds'][:, 1].max())
                local = _i11_build_local(points, receiver, width, depth, profile, terrain, window, **parameters, maximum_depth=maximum)
                self.assertLess(local['selected_edges'], _i11_np.count_nonzero(receiver >= 0))
                inside = _i11_np.all(_i11_np.abs(full['vertices'] - center) <= 6.0, axis=1)
                keep = _i11_np.array([_i11_np.all(inside[full['matrix'].indices[lo:hi]]) for lo, hi in zip(full['matrix'].indptr[:-1], full['matrix'].indptr[1:])])
                expected = signatures(full['matrix'][keep], full['kinds'][keep], full['limits'][keep], full['vertices'])
                actual = signatures(local['matrix'], local['kinds'], local['limits'], local['vertices'])
                self.assertEqual(actual, expected)
                self.assertTrue({'gradient', 'profile', 'strip'}.issubset(set(local['kinds'])))
                if len(receiver) == 4:
                    self.assertIn('cap', local['kinds'])
                lookup = {tuple(vertex): i for i, vertex in enumerate(full['vertices'])}
                mapping = _i11_np.array([lookup[tuple(vertex)] for vertex in local['vertices']])
                for key in ('source', 'bounds', 'source_padding'):
                    _i11_np.testing.assert_array_equal(local[key], full[key][mapping])
                relaxed = _i11_build_local(points, receiver, width, depth, profile, terrain, window, **parameters)
                self.assertLessEqual(relaxed['transverse_maximum_depth'], maximum)
                relaxed_rows = signatures(relaxed['matrix'], relaxed['kinds'], relaxed['limits'], relaxed['vertices'])
                self.assertFalse(relaxed_rows - expected)
                self.assertTrue(_i11_np.all(relaxed['bounds'][:, 1] > 0.0))

    def test_duplicate_cancellation_uses_actual_nonzero_support(self):
        from terrain_pipeline.channel_geometry import _row_inside as _i11__row_inside
        retained = _i11_np.array([True, False])
        self.assertTrue(_i11__row_inside(_i11_np.array([0, 1, 1]), _i11_np.array([1.0, 2.0, -2.0]), retained))
        self.assertFalse(_i11__row_inside(_i11_np.array([0, 1, 1]), _i11_np.array([1.0, 2.0, -1.0]), retained))

    def test_assessment_never_promotes_local_feasibility_or_time_limit(self):
        from terrain_pipeline.channel_geometry import assess_local as _i11_assess_local
        model = dict(matrix=_i11_coo_matrix([[1.0]]).tocsr(), limits=_i11_np.array([1.0]), bounds=_i11_np.array([[0.0, 1.0]]))
        for status, expected in ((0, 'clear'), (2, 'infeasible'), (1, 'unknown')):
            with self.subTest(status=status), _i11_patch('terrain_pipeline.channel_geometry._i33_linprog', return_value=_i11_SimpleNamespace(status=status, message='test', x=_i11_np.array([0.0]))):
                self.assertEqual(_i11_assess_local(model)['outcome'], expected)

    def test_actual_extra_cut_certificate_identifies_lower_bound_root(self):
        from terrain_pipeline.channel_geometry import assess_local as _i11_assess_local
        model = dict(matrix=_i11_coo_matrix([[-1.0, 1.0]]).tocsr(), limits=_i11_np.array([-0.5]), bounds=_i11_np.array([[0.0, 1.0], [0.8, 1.0]]), source_padding=_i11_np.zeros(2), vertices=_i11_np.array([[0.0, 0.0], [1.0, 0.0]]))
        result = _i11_assess_local(model)
        self.assertEqual(result['outcome'], 'infeasible')
        self.assertEqual(result['solver_calls'], 2)
        extra = result['extra_cut']
        self.assertTrue(extra['certificate_valid'])
        self.assertTrue(extra['dual_finite'])
        self.assertAlmostEqual(extra['minimum_extra_ceiling_m'], 0.3)
        self.assertEqual(extra['root_vertex_indices'], [1])
        self.assertEqual(extra['root_lower_bound_duals'], [1.0])
        self.assertNotIn('lower_bound_duals', extra)

    def test_status_zero_needs_finite_feasible_primal_solution(self):
        from terrain_pipeline.channel_geometry import assess_local as _i11_assess_local
        model = dict(matrix=_i11_coo_matrix([[1.0]]).tocsr(), limits=_i11_np.array([0.5]), bounds=_i11_np.array([[0.0, 1.0]]))
        for solution in (None, _i11_np.array([_i11_np.nan]), _i11_np.array([_i11_np.inf]), _i11_np.array([1.1]), _i11_np.array([0.6])):
            with self.subTest(solution=solution), _i11_patch('terrain_pipeline.channel_geometry._i33_linprog', return_value=_i11_SimpleNamespace(status=0, message='test', x=solution)):
                self.assertEqual(_i11_assess_local(model)['outcome'], 'unknown')

def uphill_source():
    from terrain_pipeline.common_infra import TerrainGrid as _i16_TerrainGrid
    height = _i16_np.full((9, 9), 11.0, _i16_np.float64)
    height[3, 3], height[3, 4] = (10.0, 15.0)
    height[4, 3], height[4, 4] = (15.0, 9.0)
    return _i16_TerrainGrid(height, _i16_np.ones_like(height, bool), 0.0, 0.0, 4.0, 4.0, 'observed_dem', 'quadratic inside-cell hill', 'a' * 64)

def _test_metric_valley_incision_build(source=None, *, config=None, owner=None, lake=None):
    from terrain_pipeline.channel_geometry import GeometryConfig as _i16_GeometryConfig
    from terrain_pipeline.channel_geometry import build_valley_incision as _i16_build_valley_incision
    source = source or uphill_source()
    shape = source.elevation_m.shape
    return _i16_build_valley_incision(source, _i16_np.array([3 * 9 + 3, 4 * 9 + 4], _i16_np.int64), _i16_np.array([1, -1], _i16_np.int64), _i16_np.array([2.0, 2.0]), _i16_np.array([0.25, 0.25]), owner_grid=_i16_np.zeros(shape, _i16_np.int64) if owner is None else owner, corridor_mask=_i16_np.ones(shape, bool), lake_mask=_i16_np.zeros(shape, bool) if lake is None else lake, config=config or _i16_GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0))

class ValleyIncisionTests(_i16_unittest.TestCase):

    def test_varying_base_depth_shifts_quadratic_extremum(self):
        from terrain_pipeline.channel_geometry import _profile
        terrain = uphill_source()
        points = _i16_np.array([[12.0, 12.0], [16.0, 16.0]])
        profile = _profile(points, _i16_np.array([1, -1], _i16_np.int64), _i16_np.array([0.25, 1.0]), terrain, 4.0)
        t = profile[1]
        source = profile[2]
        tilted = source - (0.25 + 0.75 * t) + 1e-05 * _i16_np.sqrt(32.0) * t
        self.assertTrue(_i16_np.any((t > 0.0) & (t < 1.0)))
        self.assertAlmostEqual(float(t[_i16_np.argmax(tilted)]), 0.42045, delta=0.001)
        self.assertTrue(_i16_np.all(_i16_np.diff(profile[3]) < 0.0))

    def test_bilinear_interior_cut_controls_footprint_radius(self):
        from terrain_pipeline.channel_geometry import _profile
        from terrain_pipeline.channel_geometry import _profile_max_cut_per_edge
        terrain = uphill_source()
        points = _i16_np.array([[12.0, 12.0], [16.0, 16.0]])
        receiver = _i16_np.array([1, -1], _i16_np.int64)
        profile = _profile(points, receiver, _i16_np.array([0.25, 1.0]), terrain, 4.0)
        knot_maximum = float(_i16_np.max(profile[2] - profile[3]))
        continuous_maximum = float(_profile_max_cut_per_edge(points, receiver, profile, terrain)[0])
        self.assertGreater(continuous_maximum, knot_maximum + 0.01)
        self.assertAlmostEqual(continuous_maximum, 2.52275299, places=6)

    def test_original_quadratic_rises_but_final_canonical_bed_descends(self):
        from terrain_pipeline.channel_geometry import validate_valley_incision as _i16_validate_valley_incision
        bundle = _test_metric_valley_incision_build()
        self.assertTrue(_i16_validate_valley_incision(bundle))
        a = bundle['arrays']
        self.assertEqual(a['node_xz_m'].tolist(), [[12.0, 12.0], [16.0, 16.0]])
        self.assertGreater(a['profile_source_m'].max(), a['profile_source_m'][0])
        self.assertTrue(_i16_np.all(_i16_np.diff(a['profile_center_bed_m']) < 0.0))
        self.assertTrue(_i16_np.all(a['cut_depth_m'] >= 0.0))
        self.assertLessEqual(a['cut_depth_m'].max(), 4.0)
        self.assertTrue(bundle['metadata']['original_bed_may_rise_within_edge'])
        self.assertFalse(bundle['metadata']['hydraulic_ready'])

    def test_source_owner_lake_and_depth_gate_reject(self):
        from terrain_pipeline.channel_geometry import GeometryConfig as _i16_GeometryConfig
        source = uphill_source()
        owner = _i16_np.zeros(source.elevation_m.shape, _i16_np.int64)
        owner[3, 4] = 1
        with self.assertRaisesRegex(ValueError, 'divide|footprint'):
            _test_metric_valley_incision_build(owner=owner)
        lake = _i16_np.zeros(source.elevation_m.shape, bool)
        lake[4, 4] = True
        with self.assertRaisesRegex(ValueError, 'wet'):
            _test_metric_valley_incision_build(lake=lake)
        with self.assertRaisesRegex(ValueError, 'maximum|depth'):
            _test_metric_valley_incision_build(config=_i16_GeometryConfig(fine_spacing_m=0.5, max_cut_m=1.0, smoothing_iterations=0))

    def test_cold_roundtrip_and_rehashed_cut_reject(self):
        from terrain_pipeline.common_infra import file_sha256 as _i16_file_sha256
        from terrain_pipeline.common_infra import identity as _i16_identity
        from terrain_pipeline.channel_geometry import load_valley_incision as _i16_load_valley_incision
        from terrain_pipeline.channel_geometry import save_valley_incision as _i16_save_valley_incision
        from terrain_pipeline.channel_geometry import validate_valley_incision as _i16_validate_valley_incision
        bundle = _test_metric_valley_incision_build()
        with _i16_tempfile.TemporaryDirectory() as folder:
            path = _i16_Path(folder) / 'incision.npz'
            _i16_save_valley_incision(path, bundle)
            loaded = _i16_load_valley_incision(path, expected_sha256=_i16_file_sha256(path), expected_identity=bundle['identity_sha256'])
        self.assertEqual(loaded['identity_sha256'], bundle['identity_sha256'])
        forged = _i16_deepcopy(bundle)
        forged['arrays']['cut_depth_m'] = forged['arrays']['cut_depth_m'].copy()
        forged['arrays']['cut_depth_m'][100] += 0.01
        forged['identity_sha256'] = _i16_identity(forged['arrays'], forged['metadata'])
        with self.assertRaisesRegex(ValueError, 'incision'):
            _i16_validate_valley_incision(forged)

    def test_junction_uses_one_shared_mesh_cut_and_port(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i16_TerrainGrid
        from terrain_pipeline.channel_geometry import GeometryConfig as _i16_GeometryConfig
        from terrain_pipeline.channel_geometry import build_valley_incision as _i16_build_valley_incision
        rows, cols = _i16_np.indices((13, 13))
        height = 30.0 - 0.3 * cols + 0.01 * rows
        terrain = _i16_TerrainGrid(height.astype(_i16_np.float64), _i16_np.ones(height.shape, bool), 0.0, 0.0, 4.0, 4.0, 'observed_dem', 'Y valley', 'a' * 64)
        ids = _i16_np.array([4 * 13 + 4, 6 * 13 + 4, 5 * 13 + 6, 5 * 13 + 8], _i16_np.int64)
        result = _i16_build_valley_incision(terrain, ids, _i16_np.array([2, 2, 3, -1], _i16_np.int64), _i16_np.full(4, 2.0), _i16_np.full(4, 0.25), owner_grid=_i16_np.zeros(height.shape, _i16_np.int64), corridor_mask=_i16_np.ones(height.shape, bool), lake_mask=_i16_np.zeros(height.shape, bool), config=_i16_GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0))
        a = result['arrays']
        self.assertEqual(len(a['canonical_port_edge_node_indices']), 3)
        self.assertEqual(_i16_np.count_nonzero(_i16_np.all(a['vertices_xz_m'] == a['node_xz_m'][2], axis=1)), 1)
        faces = a['triangles']
        xy = a['vertices_xz_m'][faces]
        area = abs((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1]) - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1])) / 2.0
        self.assertAlmostEqual(float(_i16_np.sum(area * a['cut_depth_m'][faces].mean(axis=1))), result['metadata']['cut_volume_m3'], places=7)

def _test_metric_valley_centerline_fixture():
    from terrain_pipeline.channel_geometry import GeometryConfig as _i15_GeometryConfig
    from terrain_pipeline.common_infra import TerrainGrid as _i15_TerrainGrid
    rows, cols = _i15_np.indices((13, 13))
    height = (50.0 - 0.3 * cols - 0.2 * rows).astype(_i15_np.float64)
    terrain = _i15_TerrainGrid(height, _i15_np.ones(height.shape, bool), 0.0, 0.0, 4.0, 4.0, 'observed_dem', 'linear valley', 'a' * 64)
    ids = _i15_np.array([3 * 13 + 3, 4 * 13 + 4, 4 * 13 + 5, 5 * 13 + 6], _i15_np.int64)
    receiver = _i15_np.array([1, 2, 3, -1], _i15_np.int64)
    options = dict(owner_grid=_i15_np.zeros(height.shape, _i15_np.int64), corridor_mask=_i15_np.ones(height.shape, bool), lake_mask=_i15_np.zeros(height.shape, bool), source_plan_identity_sha256='b' * 64, config=_i15_GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0))
    return (terrain, ids, receiver, options)

class ValleyCenterlineTests(_i15_unittest.TestCase):

    def test_anchored_shape_decreases_turn_and_roundtrips(self):
        from terrain_pipeline.common_infra import file_sha256 as _i15_file_sha256
        from terrain_pipeline.channel_geometry import build_valley_centerline as _i15_build_valley_centerline
        from terrain_pipeline.channel_geometry import load_valley_centerline as _i15_load_valley_centerline
        from terrain_pipeline.channel_geometry import save_valley_centerline as _i15_save_valley_centerline
        from terrain_pipeline.channel_geometry import validate_valley_centerline as _i15_validate_valley_centerline
        terrain, ids, receiver, options = _test_metric_valley_centerline_fixture()
        result = _i15_build_valley_centerline(terrain, ids, receiver, _i15_np.full(4, 2.0), _i15_np.full(4, 0.25), **options)
        self.assertTrue(_i15_validate_valley_centerline(result))
        self.assertGreater(result['metadata']['moved_nodes'], 0)
        self.assertLess(result['metadata']['final_turn_energy'], result['metadata']['initial_turn_energy'])
        a = result['arrays']
        _i15_np.testing.assert_array_equal(a['node_xz_m'][a['anchor_mask']], a['original_node_xz_m'][a['anchor_mask']])
        with _i15_tempfile.TemporaryDirectory() as folder:
            path = _i15_Path(folder) / 'centerline.npz'
            _i15_save_valley_centerline(path, result)
            loaded = _i15_load_valley_centerline(path, expected_sha256=_i15_file_sha256(path), expected_identity=result['identity_sha256'])
        self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])

class MonotoneUnionTests(_i12_unittest.TestCase):

    def test_shaped_centerline_generates_cold_loadable_monotone_bed(self):
        from terrain_pipeline.common_infra import file_sha256 as _i12_file_sha256
        from terrain_pipeline.common_infra import identity as _i12_identity
        from terrain_pipeline.channel_geometry import build_monotone_union as _i12_build_monotone_union
        from terrain_pipeline.channel_geometry import load_monotone_union as _i12_load_monotone_union
        from terrain_pipeline.channel_geometry import save_monotone_union as _i12_save_monotone_union
        from terrain_pipeline.channel_geometry import validate_monotone_union as _i12_validate_monotone_union
        from terrain_pipeline.channel_geometry import build_valley_centerline as _i12_build_valley_centerline
        terrain, ids, receiver, options = _test_metric_valley_centerline_fixture()
        width, depth = (_i12_np.full(4, 2.0), _i12_np.full(4, 0.25))
        centerline = _i12_build_valley_centerline(terrain, ids, receiver, width, depth, **options)
        product = _i12_build_monotone_union(terrain, ids, receiver, width, depth, centerline=centerline, **options)
        _i12_np.testing.assert_array_equal(product['arrays']['node_xz_m'], centerline['arrays']['node_xz_m'])
        self.assertGreater(centerline['metadata']['moved_nodes'], 0)
        with _i12_tempfile.TemporaryDirectory() as folder:
            path = _i12_Path(folder) / 'shaped.npz'
            _i12_save_monotone_union(path, product)
            with _i12_patch('terrain_pipeline.channel_geometry._i34_linprog', side_effect=AssertionError('cold validator ran optimizer')):
                loaded = _i12_load_monotone_union(path, expected_sha256=_i12_file_sha256(path), expected_identity=product['identity_sha256'])
        self.assertTrue(_i12_validate_monotone_union(loaded))
        forged = _i12_deepcopy(product)
        points = forged['arrays']['node_xz_m'].copy()
        points[0, 0] += 0.1
        forged['arrays']['node_xz_m'] = points
        forged['identity_sha256'] = _i12_identity(forged['arrays'], forged['metadata'])
        with self.assertRaisesRegex(ValueError, 'anchor moved'):
            _i12_validate_monotone_union(forged)

    def test_mesh_centerline_closure_repairs_uphill_without_fill(self):
        from terrain_pipeline.common_infra import TerrainGrid as _i12_TerrainGrid
        from terrain_pipeline.channel_geometry import _close_bed as _i12__close_bed
        from terrain_pipeline.channel_geometry import _sparse_mesh as _i12__sparse_mesh
        from terrain_pipeline.channel_geometry import _sparse_slope as _i12__sparse_slope
        rows, cols = _i12_np.indices((3, 3))
        height = (10.0 - 0.1 * cols).astype(_i12_np.float64)
        terrain = _i12_TerrainGrid(height, _i12_np.ones(height.shape, bool), 0.0, 0.0, 1.0, 1.0, 'observed_dem', 'linear', 'a' * 64)
        cells = _i12_np.array([[0, 0], [1, 0]], _i12_np.int64)
        vertices, triangles = _i12__sparse_mesh(cells, terrain, 1.0, 100)
        source = 10.0 - 0.1 * vertices[:, 0]
        cut = _i12_np.zeros(len(vertices))
        cut[_i12_np.flatnonzero(_i12_np.all(vertices == [0.5, 0.5], axis=1))[0]] = 1.0
        points = _i12_np.array([[0.0, 0.5], [2.0, 0.5]])
        receiver = _i12_np.array([1, -1], _i12_np.int64)
        with self.assertRaisesRegex(ValueError, 'uphill'):
            _i12__sparse_slope(points, receiver, cells, vertices, triangles, source - cut, 1.0, terrain)
        closed, ledger = _i12__close_bed(points, receiver, cells, vertices, triangles, source, cut, terrain, 1.0, 4.0)
        self.assertTrue(_i12_np.all(closed >= cut))
        self.assertGreater(ledger['extra_cut_vertices'], 0)
        _i12__sparse_slope(points, receiver, cells, vertices, triangles, source - closed, 1.0, terrain)

    def test_product_cold_roundtrip_and_cut_tamper(self):
        from terrain_pipeline.common_infra import file_sha256 as _i12_file_sha256
        from terrain_pipeline.common_infra import identity as _i12_identity
        from terrain_pipeline.channel_geometry import GeometryConfig as _i12_GeometryConfig
        from terrain_pipeline.channel_geometry import build_monotone_union as _i12_build_monotone_union
        from terrain_pipeline.channel_geometry import load_monotone_union as _i12_load_monotone_union
        from terrain_pipeline.channel_geometry import save_monotone_union as _i12_save_monotone_union
        from terrain_pipeline.channel_geometry import validate_monotone_union as _i12_validate_monotone_union
        terrain = uphill_source()
        shape = terrain.elevation_m.shape
        product = _i12_build_monotone_union(terrain, _i12_np.array([30, 40], _i12_np.int64), _i12_np.array([1, -1], _i12_np.int64), _i12_np.array([2.0, 2.0]), _i12_np.array([0.25, 0.25]), owner_grid=_i12_np.zeros(shape, _i12_np.int64), corridor_mask=_i12_np.ones(shape, bool), lake_mask=_i12_np.zeros(shape, bool), source_plan_identity_sha256='b' * 64, config=_i12_GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0))
        self.assertTrue(_i12_validate_monotone_union(product))
        with _i12_tempfile.TemporaryDirectory() as folder:
            path = _i12_Path(folder) / 'monotone.npz'
            _i12_save_monotone_union(path, product)
            with _i12_patch('terrain_pipeline.channel_geometry._i34_linprog', side_effect=AssertionError('cold validator ran optimizer')), _i12_patch('terrain_pipeline.channel_geometry.build_monotone_union', side_effect=AssertionError('cold validator ran builder')):
                loaded = _i12_load_monotone_union(path, expected_sha256=_i12_file_sha256(path), expected_identity=product['identity_sha256'])
        self.assertEqual(loaded['identity_sha256'], product['identity_sha256'])
        forged = _i12_deepcopy(product)
        forged['arrays']['cut_depth_m'] = forged['arrays']['cut_depth_m'].copy()
        forged['arrays']['cut_depth_m'][20] += 0.01
        forged['identity_sha256'] = _i12_identity(forged['arrays'], forged['metadata'])
        with self.assertRaisesRegex(ValueError, 'field mismatch'):
            _i12_validate_monotone_union(forged)

class NetworkGeometryPlanTests(_i13_unittest.TestCase):

    def test_resealed_continuous_edge_length_tamper_is_rejected(self):
        from terrain_pipeline.common_infra import identity as _i13_identity
        from terrain_pipeline.common_infra import BoundaryGrid as _i13_BoundaryGrid
        from terrain_pipeline.drainage import route_diagnostic as _i13_route_diagnostic
        from terrain_pipeline.channel_geometry import build_network_geometry_plan as _i13_build_network_geometry_plan
        from terrain_pipeline.channel_geometry import validate_network_geometry_plan as _i13_validate_network_geometry_plan
        from dataclasses import replace
        from tools.verify_td_river_geometry import fixture
        terrain, _, _, _ = fixture('single')
        outlet = _i13_np.zeros(terrain.valid_mask.shape, bool)
        outlet[-1, -1] = True
        boundary = _i13_BoundaryGrid.from_outlet_mask(terrain, outlet, source_id='edge', source_sha256='b' * 64)
        graph = _i13_route_diagnostic(terrain, boundary)
        plan = _i13_build_network_geometry_plan(terrain, graph)
        lengths = graph.edge_length_m.copy()
        lengths[_i13_np.flatnonzero(graph.receiver >= 0)[0]] *= 1.1
        forged = replace(graph, edge_length_m=lengths)
        arrays = {key: value.copy() for key, value in plan['arrays'].items()}
        arrays['graph_edge_length_m'] = lengths
        metadata = dict(plan['metadata'], graph_identity_sha256=forged.identity_sha256)
        bad = dict(arrays=arrays, metadata=metadata, identity_sha256=_i13_identity(arrays, metadata))
        with self.assertRaisesRegex(ValueError, 'continuous metric node'):
            _i13_validate_network_geometry_plan(bad)

    def test_complete_edge_partition_monotone_sections_and_native_area(self):
        from terrain_pipeline.common_infra import BoundaryGrid as _i13_BoundaryGrid
        from terrain_pipeline.common_infra import TerrainGrid as _i13_TerrainGrid
        from terrain_pipeline.drainage import route_diagnostic as _i13_route_diagnostic
        from terrain_pipeline.channel_geometry import NetworkGeometryConfig as _i13_NetworkGeometryConfig
        from terrain_pipeline.channel_geometry import build_network_geometry_plan as _i13_build_network_geometry_plan
        from terrain_pipeline.channel_geometry import validate_network_geometry_plan as _i13_validate_network_geometry_plan
        row, col = _i13_np.indices((7, 7))
        terrain = _i13_TerrainGrid((100.0 - row - 0.4 * col).astype(_i13_np.float64), _i13_np.ones((7, 7), bool), 0.0, 0.0, 10.0, 10.0, 'observed_dem', 'plane', 'a' * 64)
        mask = _i13_np.zeros((7, 7), bool)
        mask[-1, -1] = True
        boundary = _i13_BoundaryGrid.from_outlet_mask(terrain, mask, source_id='edge', source_sha256='b' * 64)
        graph = _i13_route_diagnostic(terrain, boundary)
        plan = _i13_build_network_geometry_plan(terrain, graph, _i13_NetworkGeometryConfig(min_contributing_area_m2=100.0, max_patch_edges=2))
        a = plan['arrays']
        self.assertEqual(len(a['selected_edge_source_ids']), int((graph.receiver >= 0).sum()))
        self.assertEqual(len(_i13_np.unique(a['patch_edge_source_ids'])), len(a['patch_edge_source_ids']))
        self.assertTrue(_i13_np.all(_i13_np.diff(a['patch_offsets']) <= 2))
        self.assertAlmostEqual(a['contributing_area_m2'][-1], 4900.0)
        for i, j in zip(a['selected_edge_source_ids'], a['selected_edge_target_ids']):
            self.assertGreaterEqual(a['contributing_area_m2'][j], a['contributing_area_m2'][i])
        self.assertTrue(_i13_validate_network_geometry_plan(plan))
        self.assertFalse(plan['metadata']['geometry_verified'])

    def test_resigned_duplicate_edge_is_rejected(self):
        from terrain_pipeline.common_infra import identity as _i13_identity
        from terrain_pipeline.common_infra import BoundaryGrid as _i13_BoundaryGrid
        from terrain_pipeline.drainage import route_diagnostic as _i13_route_diagnostic
        from terrain_pipeline.channel_geometry import NetworkGeometryConfig as _i13_NetworkGeometryConfig
        from terrain_pipeline.channel_geometry import build_network_geometry_plan as _i13_build_network_geometry_plan
        from terrain_pipeline.channel_geometry import validate_network_geometry_plan as _i13_validate_network_geometry_plan
        from tools.verify_td_river_geometry import fixture
        terrain, _, _, _ = fixture('single')
        outlet = _i13_np.zeros(terrain.valid_mask.shape, bool)
        outlet[-1, -1] = True
        boundary = _i13_BoundaryGrid.from_outlet_mask(terrain, outlet, source_id='edge', source_sha256='b' * 64)
        graph = _i13_route_diagnostic(terrain, boundary)
        plan = _i13_build_network_geometry_plan(terrain, graph, _i13_NetworkGeometryConfig(min_contributing_area_m2=100.0))
        arrays = {k: v.copy() for k, v in plan['arrays'].items()}
        arrays['patch_edge_source_ids'][1] = arrays['patch_edge_source_ids'][0]
        bad = dict(arrays=arrays, metadata=plan['metadata'], identity_sha256=_i13_identity(arrays, plan['metadata']))
        with self.assertRaisesRegex(ValueError, 'catalogue mismatch'):
            _i13_validate_network_geometry_plan(bad)

    def test_other_source_graph_is_rejected_even_with_same_validity(self):
        from terrain_pipeline.common_infra import BoundaryGrid as _i13_BoundaryGrid
        from terrain_pipeline.common_infra import TerrainGrid as _i13_TerrainGrid
        from terrain_pipeline.drainage import route_diagnostic as _i13_route_diagnostic
        from terrain_pipeline.channel_geometry import build_network_geometry_plan as _i13_build_network_geometry_plan
        from tools.verify_td_river_geometry import fixture
        terrain, _, _, _ = fixture('single')
        outlet = _i13_np.zeros(terrain.valid_mask.shape, bool)
        outlet[-1, -1] = True
        boundary = _i13_BoundaryGrid.from_outlet_mask(terrain, outlet, source_id='edge', source_sha256='b' * 64)
        graph = _i13_route_diagnostic(terrain, boundary)
        other = _i13_TerrainGrid(terrain.elevation_m + 1.0, terrain.valid_mask, terrain.x0_m, terrain.z0_m, terrain.dx_m, terrain.dz_m, terrain.source_kind, 'other-source', 'c' * 64)
        with self.assertRaisesRegex(ValueError, 'terrain identity'):
            _i13_build_network_geometry_plan(other, graph)
_i14_os.environ.setdefault('OMP_NUM_THREADS', '1')
_i14_os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
_i14_os.environ.setdefault('MKL_NUM_THREADS', '1')
ROOT = _i14_Path(__file__).resolve().parents[1]
REAL_REPORT = ROOT / 'verification/hydrological-planning-domain/full-edges-v5-20261014-03' / 'edge-8470-8600-v7-shared-sections-owned-halo2/report.json'

def _bed(x, z):
    return 2.0 * x - 3.0 * z + 7.0

def _sparse_fan4():
    origin = [-10.0, -20.0]
    spacing = 1.0
    cells = _i14_np.array([[0, 0], [2, 0]], dtype=_i14_np.int64)
    verts = []
    tris = []
    tri_local = _i14_np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], dtype=_i14_np.int64)
    for ci, (cx, cz) in enumerate(cells):
        x0 = origin[0] + cx * spacing
        z0 = origin[1] + cz * spacing
        corners = _i14_np.array([[x0, z0], [x0 + spacing, z0], [x0 + spacing, z0 + spacing], [x0, z0 + spacing], [x0 + 0.5 * spacing, z0 + 0.5 * spacing]], dtype=_i14_np.float64)
        base = 5 * ci
        verts.append(corners)
        tris.append(tri_local + base)
    vertices = _i14_np.concatenate(verts, axis=0)
    triangles = _i14_np.concatenate(tris, axis=0)
    bed = _bed(vertices[:, 0], vertices[:, 1])
    node_xz = _i14_np.array([[-10.0, -20.0], [-7.0, -20.0]], dtype=_i14_np.float64)
    node_source_edges = _i14_np.array([[12, 34], [12, 34]], dtype=_i14_np.int64)
    node_edge_fractions = _i14_np.array([0.0, 1.0], dtype=_i14_np.float64)
    receiver = _i14_np.array([1, -1], dtype=_i14_np.int64)
    return {'identity': 'piece0', 'parent_detail_identity': 'detail0', 'frozen_plan_identity': 'plan0', 'fine_spacing_m': spacing, 'mesh_origin_xz_m': _i14_np.array(origin, dtype=_i14_np.float64), 'shared_sections': [], 'source_path': 'test.npz', 'archive_sha256': '0' * 64, 'arrays': {'cells': cells, 'vertices_xz_m': vertices, 'triangles': triangles, 'bed_elevation_m': bed, 'node_xz_m': node_xz, 'node_source_edges': node_source_edges, 'node_edge_fractions': node_edge_fractions, 'receiver': receiver}}

@_i14_pytest.fixture()
def raw():
    return _sparse_fan4()

@_i14_pytest.fixture()
def piece(raw):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    return _i14__piece_geometry(raw)

def test_piece_geometry_identity_and_plan(piece, raw):
    assert piece['identity'] == 'piece0'
    assert piece['parent_detail_identity'] == 'detail0'
    assert piece['frozen_plan_identity'] == 'plan0'
    assert piece['shared_sections'] == []
    assert piece['spacing_m'] == _i14_pytest.approx(raw['fine_spacing_m'])
    _i14_np.testing.assert_allclose(piece['origin_xz_m'], raw['mesh_origin_xz_m'])

def test_piece_geometry_arrays_and_bbox(piece):
    assert piece['cells'].shape == (2, 2)
    assert piece['triangles'].shape == (8, 3)
    assert piece['vertices_xz_m'].shape == (10, 2)
    _i14_np.testing.assert_allclose(piece['bbox_min_xz_m'], [-10.0, -20.0])
    _i14_np.testing.assert_allclose(piece['bbox_max_xz_m'], [-7.0, -19.0])

def test_piece_geometry_lookup_edges_and_bed(piece):
    lookup = piece['lookup']
    assert lookup is not None
    bed = piece['bed_elevation_m']
    assert bed.shape == (10,)
    _i14_np.testing.assert_allclose(bed, _bed(piece['vertices_xz_m'][:, 0], piece['vertices_xz_m'][:, 1]))
    for key in ('node_xz_m', 'node_source_edges', 'node_edge_fractions', 'receiver'):
        assert key in piece

def test_piece_geometry_no_input_mutation(raw):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    snap = {k: v.copy() if isinstance(v, _i14_np.ndarray) else v for k, v in raw.items()}
    snap_arrays = {k: v.copy() for k, v in raw['arrays'].items()}
    _i14__piece_geometry(raw)
    for k, v in snap.items():
        if isinstance(v, _i14_np.ndarray):
            _i14_np.testing.assert_array_equal(raw[k], v)
        else:
            assert raw[k] == v
    for k, v in snap_arrays.items():
        _i14_np.testing.assert_array_equal(raw['arrays'][k], v)

def _sample(piece, *pts):
    from terrain_pipeline.channel_geometry import _sample_piece_points as _i14__sample_piece_points
    return _i14__sample_piece_points(piece, _i14_np.array(pts, dtype=_i14_np.float64))

def test_sample_vertices(piece):
    vx, vz = (piece['vertices_xz_m'][:, 0], piece['vertices_xz_m'][:, 1])
    vals, mask = _sample(piece, *[[x, z] for x, z in zip(vx, vz)])
    assert mask.all()
    _i14_np.testing.assert_allclose(vals, _bed(vx, vz), atol=1e-10)

def test_sample_triangle_interiors_and_center(piece):
    pts = []
    verts = piece['vertices_xz_m']
    for tri in piece['triangles']:
        cx = verts[tri, 0].mean()
        cz = verts[tri, 1].mean()
        pts.append([cx, cz])
        a = verts[tri[0]]
        pts.append([0.6 * cx + 0.4 * a[0], 0.6 * cz + 0.4 * a[1]])
    vals, mask = _sample(piece, *pts)
    assert mask.all()
    _i14_np.testing.assert_allclose(vals, _bed(_i14_np.array(pts)[:, 0], _i14_np.array(pts)[:, 1]), atol=1e-10)

def test_sample_edge_and_boundary_supported(piece):
    pts = [[-10.0, -20.0], [-9.5, -20.0], [-7.0, -20.0], [-7.0, -19.0]]
    vals, mask = _sample(piece, *pts)
    assert mask.all()
    _i14_np.testing.assert_allclose(vals, _bed(_i14_np.array(pts)[:, 0], _i14_np.array(pts)[:, 1]), atol=1e-10)

def test_sample_unsupported_hole_and_outside(piece):
    vals, mask = _sample(piece, [-8.5, -19.5], [-6.0, -19.0])
    assert not mask.any()
    assert _i14_np.isnan(vals).all()

def test_sample_empty(piece):
    from terrain_pipeline.channel_geometry import _sample_piece_points as _i14__sample_piece_points
    vals, mask = _i14__sample_piece_points(piece, _i14_np.empty((0, 2), dtype=_i14_np.float64))
    assert vals.shape == (0,)
    assert mask.shape == (0,)
    assert mask.dtype == bool

def test_sample_agrees_with_analytic_plane(piece):
    pts = [[-9.5, -19.5], [-8.0, -19.5], [-7.6, -19.2]]
    vals, mask = _sample(piece, *pts)
    assert mask.all()
    expected = _bed(_i14_np.array(pts)[:, 0], _i14_np.array(pts)[:, 1])
    _i14_np.testing.assert_allclose(vals, expected, atol=1e-10)

def test_sample_rejects_nonfinite_and_bad_shape(piece):
    from terrain_pipeline.channel_geometry import _sample_piece_points as _i14__sample_piece_points
    with _i14_pytest.raises((ValueError, _i14_np.linalg.LinAlgError)):
        _i14__sample_piece_points(piece, _i14_np.array([[_i14_np.nan, -19.0]]))
    with _i14_pytest.raises((ValueError, _i14_np.linalg.LinAlgError)):
        _i14__sample_piece_points(piece, _i14_np.array([[_i14_np.inf, -19.0]]))
    with _i14_pytest.raises((ValueError, IndexError, _i14_np.linalg.LinAlgError)):
        _i14__sample_piece_points(piece, _i14_np.array([[-9.0, -19.0, -19.0]]))

@_i14_pytest.mark.parametrize('bad', [True, '1', 0])
def test_invalid_spacing(raw, bad):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    raw['fine_spacing_m'] = bad
    with _i14_pytest.raises((TypeError, ValueError)):
        _i14__piece_geometry(raw)

def test_float_cells_rejected(raw):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    raw['arrays']['cells'] = raw['arrays']['cells'].astype(_i14_np.float64)
    with _i14_pytest.raises((TypeError, ValueError)):
        _i14__piece_geometry(raw)

def test_parent_missing_rejected(raw):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    raw.pop('parent_detail_identity')
    with _i14_pytest.raises((KeyError, TypeError, ValueError)):
        _i14__piece_geometry(raw)

def test_bad_source_edge_rows_rejected(raw):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    raw['arrays']['node_source_edges'] = _i14_np.zeros((1, 2), dtype=_i14_np.int64)
    with _i14_pytest.raises((ValueError, IndexError, KeyError)):
        _i14__piece_geometry(raw)

def test_degenerate_ids_rejected(raw):
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    raw['arrays']['node_source_edges'] = _i14_np.array([[12, 12], [12, 12]], dtype=_i14_np.int64)
    with _i14_pytest.raises((ValueError, KeyError, TypeError)):
        _i14__piece_geometry(raw)

def test_corrupt_piece_triangles_raises_linalg(piece):
    from terrain_pipeline.channel_geometry import _sample_piece_points as _i14__sample_piece_points
    bad = dict(piece)
    bad['triangles'] = _i14_np.zeros_like(piece['triangles'])
    with _i14_pytest.raises(_i14_np.linalg.LinAlgError):
        _i14__sample_piece_points(bad, _i14_np.array([[-9.5, -19.5]]))

def test_lookup_valueerror_propagates(piece, monkeypatch):
    from terrain_pipeline.channel_geometry import _sample_piece_points as _i14__sample_piece_points

    def boom(point, lookup, origin, spacing):
        raise ValueError('corrupt lookup')
    monkeypatch.setattr(_i14_sampler, '_cell_at_point', boom, raising=True)
    with _i14_pytest.raises(ValueError, match='corrupt lookup'):
        _i14__sample_piece_points(piece, _i14_np.array([[-9.5, -19.5]]))

@_i14_pytest.mark.skipif(not REAL_REPORT.exists(), reason='real report not present')
def test_real_piece000_matches_saved_bed():
    from terrain_pipeline.channel_geometry import _piece_geometry as _i14__piece_geometry
    from terrain_pipeline.channel_geometry import _sample_piece_points as _i14__sample_piece_points
    from tools.prepare_hydrology_domains import _read_bed_piece
    report = _i14_json.loads(REAL_REPORT.read_text(encoding='utf-8'))
    rel = report['piece_paths'][0].replace('\\', '/')
    path = ROOT / rel
    import hashlib
    record = _read_bed_piece(path)
    record['source_path'] = str(path)
    record['archive_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    snap = {k: v.copy() if isinstance(v, _i14_np.ndarray) else v for k, v in record['arrays'].items()}
    piece = _i14__piece_geometry(record)
    for k, v in snap.items():
        _i14_np.testing.assert_array_equal(record['arrays'][k], v)
    verts = piece['vertices_xz_m']
    bed = piece['bed_elevation_m']
    n = min(30, verts.shape[0])
    pts = verts[:n]
    vals, mask = _i14__sample_piece_points(piece, pts)
    assert mask.all()
    _i14_np.testing.assert_allclose(vals, bed[:n], atol=1e-08)

def test_saved_bed_grid_sampling_two_piece_strip_near_shared_section():
    import copy, numpy as np
    left = copy.deepcopy(_sparse_fan4())
    right = copy.deepcopy(_sparse_fan4())
    left['identity'] = 'left'
    left['source_path'] = 'left.obj'
    right['identity'] = 'right'
    right['source_path'] = 'right.obj'
    left['arrays'] = dict(left['arrays'])
    right['arrays'] = dict(right['arrays'])
    left['arrays']['node_xz_m'] = np.array([[-10, -19.5], [-9.5, -19.5]])
    left['arrays']['node_edge_fractions'] = np.array([0.0, 0.5])
    right['arrays']['node_xz_m'] = np.array([[-9.5, -19.5], [-9, -19.5]])
    right['arrays']['node_edge_fractions'] = np.array([0.5, 1.0])
    left['shared_sections'] = [dict(parent_detail_identity='detail0', position_xz_m=[-9.5, -19.5], normal_xz=[0, 1], radius_m=0.5, offsets_m=[-0.5, 0.0, 0.5])]
    right['shared_sections'] = [dict(parent_detail_identity='detail0', position_xz_m=[-9.5, -19.5], normal_xz=[0, 1], radius_m=0.5, offsets_m=[-0.5, 0.0, 0.5])]
    origin = [-10, -20]
    shape_zx = (3, 3)
    spacing_m = 0.5
    for pieces in ([left, right], [right, left]):
        result = _i14_sampler.sample_saved_bed_grid(pieces, origin_xz_m=origin, shape_zx=shape_zx, spacing_m=spacing_m)
        xs = origin[0] + np.arange(shape_zx[1]) * spacing_m
        zs = origin[1] + np.arange(shape_zx[0]) * spacing_m
        xx, zz = np.meshgrid(xs, zs)
        expected = 2.0 * xx - 3.0 * zz + 7.0
        assert result['supported_mask'].shape == shape_zx
        assert result['supported_mask'].all()
        assert np.allclose(result['bed_m'], expected)
        assert np.array_equal(result['owner_piece_index'], np.tile([0, 1, 1], (3, 1)))

def test_saved_bed_grid_sampling_real_report_optional():
    import hashlib, json, os
    import numpy as np
    from tools.prepare_hydrology_domains import _read_bed_piece
    if REAL_REPORT is None or not os.path.exists(REAL_REPORT):
        import pytest
        pytest.skip('real report not available')
    report = json.loads(REAL_REPORT.read_text())
    root = ROOT
    records = []
    for rel in report['piece_paths']:
        path = os.path.join(root, rel)
        record = _read_bed_piece(path)
        record = dict(record)
        record['source_path'] = str(path)
        with open(path, 'rb') as f:
            record['archive_sha256'] = hashlib.sha256(f.read()).hexdigest()
        records.append(record)
    origin_xz_m = (records[0]['arrays']['node_xz_m'][1] - 20).tolist()
    result = _i14_sampler.sample_saved_bed_grid(records, origin_xz_m=origin_xz_m, shape_zx=(41, 41), spacing_m=1.0)
    mask = np.asarray(result['supported_mask'])
    n_supported = int(mask.sum())
    assert 0 < n_supported < 1681
    assert len(result['provenance']['canonical_pieces']) == 29
    assert result['provenance']['maximum_shared_section_difference_m'] <= 1e-06
    assert np.all(np.asarray(result['owner_piece_index'])[mask] >= 0)
    assert np.all(np.asarray(result['owner_piece_index'])[~mask] == -1)
    assert np.all(np.isnan(np.asarray(result['bed_m'])[~mask]))

@_i14_pytest.fixture(scope='module')
def real_records():
    if not REAL_REPORT.exists():
        _i14_pytest.skip('missing real report')
    from tools.prepare_hydrology_domains import _read_bed_piece
    import hashlib
    report = _i14_json.loads(REAL_REPORT.read_text(encoding='utf-8'))
    records = []
    for rel in report['piece_paths']:
        path = ROOT / rel
        record = _read_bed_piece(path)
        record['source_path'] = str(path)
        record['archive_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(record)
    return records

def test_real_grid_shuffle_and_5m(real_records):
    first = real_records[0]
    node_xz = first['arrays']['node_xz_m']
    center = node_xz[1]
    origin = (center[0] - 20.0, center[1] - 20.0)
    kwargs = dict(pieces=real_records, origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0)
    res_a = _i14_sampler.sample_saved_bed_grid(**kwargs)
    res_b = _i14_sampler.sample_saved_bed_grid(pieces=list(reversed(real_records)), origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0)
    _i14_np.testing.assert_allclose(res_a['bed_m'], res_b['bed_m'], equal_nan=True)
    _i14_np.testing.assert_array_equal(res_a['supported_mask'], res_b['supported_mask'])
    _i14_np.testing.assert_array_equal(res_a['owner_piece_index'], res_b['owner_piece_index'])
    kwargs5 = dict(pieces=real_records, origin_xz_m=origin, shape_zx=(9, 9), spacing_m=5.0)
    res5 = _i14_sampler.sample_saved_bed_grid(**kwargs5)
    one_m = _i14_sampler.sample_saved_bed_grid(pieces=real_records, origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0)
    _i14_np.testing.assert_allclose(res5['bed_m'], one_m['bed_m'][::5, ::5], equal_nan=True)
    _i14_np.testing.assert_array_equal(res5['supported_mask'], one_m['supported_mask'][::5, ::5])
    _i14_np.testing.assert_array_equal(res5['owner_piece_index'], one_m['owner_piece_index'][::5, ::5])

@_i14_pytest.mark.parametrize('case,expected_msg', [('duplicate', 'duplicate piece identity'), ('parent', 'parent_detail_identity mismatch'), ('gap', 'fraction gap or overlap'), ('conflict', 'shared section beds differ beyond tolerance')])
def test_malformed_input_cases(real_records, case, expected_msg):
    records = list(real_records)
    first = _i14_copy.copy(records[0])
    first['arrays'] = dict(records[0]['arrays'])
    if case == 'duplicate':
        records = records + [records[0]]
    elif case == 'parent':
        first['parent_detail_identity'] = 'wrong'
        records[0] = first
    elif case == 'gap':
        first['arrays']['node_edge_fractions'] = _i14_np.array([0.0, 1.0 / 30.0])
        first['arrays']['node_xz_m'] = _i14_np.array([real_records[0]['arrays']['node_xz_m'][0], real_records[0]['arrays']['node_xz_m'][0] + (real_records[-1]['arrays']['node_xz_m'][1] - real_records[0]['arrays']['node_xz_m'][0]) / 30.0])
        records[0] = first
    elif case == 'conflict':
        bed = first['arrays']['bed_elevation_m']
        first['arrays']['bed_elevation_m'] = _i14_np.asarray(bed) + 0.1
        records[0] = first
    node_xz = real_records[0]['arrays']['node_xz_m']
    center = node_xz[1]
    origin = (center[0] - 20.0, center[1] - 20.0)
    with _i14_pytest.raises(ValueError, match=expected_msg):
        _i14_sampler.sample_saved_bed_grid(pieces=records, origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0)

def test_shared_line_beyond_radius(real_records):
    sec = real_records[0]['shared_sections'][0]
    origin = _i14_np.asarray(sec['position_xz_m']) + _i14_np.asarray(sec['normal_xz']) * (sec['radius_m'] + 1)
    res = _i14_sampler.sample_saved_bed_grid(real_records, origin_xz_m=origin, shape_zx=(1, 1), spacing_m=1.0)
    assert not res['supported_mask'][0, 0]
    assert res['owner_piece_index'][0, 0] == -1
    assert _i14_np.isnan(res['bed_m'][0, 0])

def make_union(budget=None, spacing=0.5):
    from terrain_pipeline.channel_geometry import GeometryConfig as _i17_GeometryConfig
    from terrain_pipeline.channel_geometry import build_tiled_monotone_union as _i17_build_tiled_monotone_union
    terrain = uphill_source()
    shape = terrain.elevation_m.shape
    return _i17_build_tiled_monotone_union(terrain, _i17_np.array([30, 40], _i17_np.int64), _i17_np.array([1, -1], _i17_np.int64), _i17_np.array([2.0, 2.0]), _i17_np.array([0.25, 0.25]), owner_grid=_i17_np.zeros(shape, _i17_np.int64), corridor_mask=_i17_np.ones(shape, bool), lake_mask=_i17_np.zeros(shape, bool), source_plan_identity_sha256='b' * 64, config=_i17_GeometryConfig(fine_spacing_m=spacing, smoothing_iterations=0), budget=budget)

class TiledValleyUnionTests(_i17_unittest.TestCase):

    def test_shared_field_is_partitioned_with_unique_cells(self):
        from terrain_pipeline.channel_geometry import TileBudget as _i17_TileBudget
        from terrain_pipeline.channel_geometry import validate_tiled_monotone_union as _i17_validate_tiled_monotone_union
        product = make_union(_i17_TileBudget(max_cells=2, max_vertices=64))
        self.assertGreater(product['metadata']['tile_count'], 1)
        self.assertTrue(_i17_validate_tiled_monotone_union(product))
        records = product['metadata']['tile_records']
        self.assertTrue(all((row['cell_count'] <= 2 for row in records)))
        self.assertEqual(product['metadata']['global_unique_cell_ownership'], True)

    def test_cold_validator_does_not_close_or_optimize(self):
        from terrain_pipeline.channel_geometry import validate_tiled_monotone_union as _i17_validate_tiled_monotone_union
        product = make_union()
        with _i17_patch('terrain_pipeline.channel_geometry._close_bed', side_effect=AssertionError('cold validator ran closure')), _i17_patch('terrain_pipeline.channel_geometry._i34_linprog', side_effect=AssertionError('cold validator ran optimizer')):
            self.assertTrue(_i17_validate_tiled_monotone_union(product))

    def test_saved_roundtrip_and_tile_tamper_are_rejected(self):
        from terrain_pipeline.common_infra import file_sha256 as _i17_file_sha256
        from terrain_pipeline.common_infra import identity as _i17_identity
        from terrain_pipeline.channel_geometry import TileBudget as _i17_TileBudget
        from terrain_pipeline.channel_geometry import load_tiled_monotone_union as _i17_load_tiled_monotone_union
        from terrain_pipeline.channel_geometry import save_tiled_monotone_union as _i17_save_tiled_monotone_union
        from terrain_pipeline.channel_geometry import validate_tiled_monotone_union as _i17_validate_tiled_monotone_union
        product = make_union(_i17_TileBudget(max_cells=2, max_vertices=64))
        with _i17_tempfile.TemporaryDirectory() as folder:
            path = _i17_Path(folder) / 'tiled.npz'
            _i17_save_tiled_monotone_union(path, product)
            loaded = _i17_load_tiled_monotone_union(path, expected_sha256=_i17_file_sha256(path), expected_identity=product['identity_sha256'])
        self.assertEqual(loaded['identity_sha256'], product['identity_sha256'])
        forged = _i17_deepcopy(product)
        forged['arrays']['tile_cut_depth_m'] = forged['arrays']['tile_cut_depth_m'].copy()
        forged['arrays']['tile_cut_depth_m'][0] += 0.01
        forged['identity_sha256'] = _i17_identity(forged['arrays'], forged['metadata'])
        with self.assertRaisesRegex(ValueError, 'shared corner|tile identity|global field'):
            _i17_validate_tiled_monotone_union(forged)

    def test_refinement_keeps_fixed_two_percent_gate(self):
        from terrain_pipeline.channel_geometry import GeometryConfig as _i17_GeometryConfig
        from terrain_pipeline.channel_geometry import TileBudget as _i17_TileBudget
        from terrain_pipeline.channel_geometry import build_tiled_refinement_pair as _i17_build_tiled_refinement_pair
        from terrain_pipeline.channel_geometry import validate_tiled_monotone_union as _i17_validate_tiled_monotone_union
        pair = _i17_build_tiled_refinement_pair(uphill_source(), _i17_np.array([30, 40], _i17_np.int64), _i17_np.array([1, -1], _i17_np.int64), _i17_np.array([2.0, 2.0]), _i17_np.array([0.25, 0.25]), owner_grid=_i17_np.zeros((9, 9), _i17_np.int64), corridor_mask=_i17_np.ones((9, 9), bool), lake_mask=_i17_np.zeros((9, 9), bool), source_plan_identity_sha256='b' * 64, config=_i17_GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0), budget=_i17_TileBudget(max_cells=64, max_vertices=1024))
        self.assertLessEqual(pair['spatial_refinement_relative'], 0.02)
        self.assertTrue(_i17_validate_tiled_monotone_union(pair['coarse']))
        self.assertTrue(_i17_validate_tiled_monotone_union(pair['fine']))

def union():
    from terrain_pipeline.channel_geometry import GeometryConfig as _i18_GeometryConfig
    from terrain_pipeline.channel_geometry import build_valley_union as _i18_build_valley_union
    source = uphill_source()
    return _i18_build_valley_union(source, _i18_np.array([30, 40], _i18_np.int64), _i18_np.array([1, -1], _i18_np.int64), _i18_np.array([2.0, 2.0]), _i18_np.array([0.25, 0.25]), owner_grid=_i18_np.zeros(source.elevation_m.shape, _i18_np.int64), corridor_mask=_i18_np.ones(source.elevation_m.shape, bool), lake_mask=_i18_np.zeros(source.elevation_m.shape, bool), source_plan_identity_sha256='b' * 64, config=_i18_GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0))

class SparseValleyUnionTests(_i18_unittest.TestCase):

    def test_unique_sparse_fan4_matches_dense_represented_volume(self):
        from terrain_pipeline.channel_geometry import validate_valley_union as _i18_validate_valley_union
        sparse = union()
        dense = _test_metric_valley_incision_build()
        self.assertTrue(_i18_validate_valley_union(sparse))
        self.assertLess(len(sparse['arrays']['vertices_xz_m']), len(dense['arrays']['vertices_xz_m']))
        self.assertAlmostEqual(sparse['metadata']['cut_volume_m3'], dense['metadata']['cut_volume_m3'], places=7)
        self.assertEqual(len(sparse['arrays']['port_cut_depth_m']), 1)
        faces = sparse['arrays']['triangles']
        edges = _i18_np.sort(_i18_np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
        _, count = _i18_np.unique(edges, axis=0, return_counts=True)
        self.assertTrue(_i18_np.all(count <= 2))

    def test_cold_roundtrip_and_rehashed_port_tamper(self):
        from terrain_pipeline.common_infra import file_sha256 as _i18_file_sha256
        from terrain_pipeline.common_infra import identity as _i18_identity
        from terrain_pipeline.channel_geometry import load_valley_union as _i18_load_valley_union
        from terrain_pipeline.channel_geometry import save_valley_union as _i18_save_valley_union
        from terrain_pipeline.channel_geometry import validate_valley_union as _i18_validate_valley_union
        bundle = union()
        with _i18_tempfile.TemporaryDirectory() as folder:
            path = _i18_Path(folder) / 'sparse-union.npz'
            _i18_save_valley_union(path, bundle)
            loaded = _i18_load_valley_union(path, expected_sha256=_i18_file_sha256(path), expected_identity=bundle['identity_sha256'])
        self.assertEqual(loaded['identity_sha256'], bundle['identity_sha256'])
        forged = _i18_deepcopy(bundle)
        forged['arrays']['port_cut_depth_m'] = forged['arrays']['port_cut_depth_m'].copy()
        forged['arrays']['port_cut_depth_m'][0, 0] += 0.01
        forged['identity_sha256'] = _i18_identity(forged['arrays'], forged['metadata'])
        with self.assertRaisesRegex(ValueError, 'port'):
            _i18_validate_valley_union(forged)

class MountainFineMeshTests(_i19_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        source = _i19_load_source('normal_mountain')
        cls.geometry = _i19_geometry.prepare_mountain_geometry(source['height_m'], spacing_m=30.0, origin_m_xz=source['origin_m_xz'], source_binding={'mountain': 'normal_mountain'}, boundary_mask=_i19_geometry.window_boundary(source['height_m'].shape), protected_mask=_i19_np.zeros(source['height_m'].shape, dtype=bool))
        cls.chain = _i19_fine.select_continuous_fine_geometry(cls.geometry)['accepted']
        support = _i19_storage.fine_storage_support(cls.chain)
        level = float(support['max_stage_m'].min() - 0.02)
        cls.saved = _i19_storage.prepare_fine_storage(cls.chain, cls.geometry, initial_stage_m=_i19_np.maximum(support['min_bed_m'], level), local_q_m3_s=_i19_np.zeros((8, 4)), upstream_stage_m=_i19_np.full(9, level), tailwater_stage_m=_i19_np.full(9, level), dt_s=10.0)

    def test_shared_vertices_nonzero_triangles_and_exact_original_positions(self):
        from terrain_pipeline.channel_geometry import export_fine_mesh as _i19_export_fine_mesh
        mesh = _i19_export_fine_mesh(self.chain, self.saved, self.geometry)
        arrays = mesh['arrays']
        self.assertEqual(arrays['triangles'].shape, (90 * 10 * 2, 3))
        self.assertEqual(arrays['vertices_H2_local_xyz_m'].shape, (91 * 11, 3))
        world = arrays['vertices_H0_local_xyz_m'] + arrays['origin_world_xyz_m']
        _i19_np.testing.assert_allclose(world[:, 1], self.chain['arrays']['H0_m'].ravel(), rtol=0.0, atol=1e-10)
        self.assertEqual(arrays['shared_section_vertex_ids'].shape, (2, 11))
        self.assertEqual(_i19_np.unique(arrays['shared_section_vertex_ids']).size, 22)
        vertices = arrays['vertices_H2_local_xyz_m']
        triangles = arrays['triangles']
        normals = _i19_np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
        self.assertTrue((normals[:, 1] > 0).all())

    def test_wet_support_depth_and_volume_match_solver_not_triangle_interpolation(self):
        from terrain_pipeline.channel_geometry import export_fine_mesh as _i19_export_fine_mesh
        mesh = _i19_export_fine_mesh(self.chain, self.saved, self.geometry)
        arrays = mesh['arrays']
        _i19_np.testing.assert_array_equal(arrays['wet_mask'], arrays['water_depth_m'] > 0)
        self.assertTrue((arrays['water_depth_m'] == 0).any())
        self.assertTrue((arrays['water_depth_m'] > 0).any())
        _i19_np.testing.assert_allclose(arrays['water_volume_m3'], arrays['solver_volume_m3'], atol=1e-09, rtol=0.0)
        self.assertEqual(arrays['time_s'].size, arrays['qedges_m3_s'].shape[0] + 1)

    def test_export_is_readonly_and_never_prepares_or_advances(self):
        from terrain_pipeline.channel_geometry import export_fine_mesh as _i19_export_fine_mesh
        before = self.chain['arrays']['H0_m'].copy()
        with _i19_patch.object(_i19_storage, 'prepare_fine_storage', side_effect=AssertionError('advance')), _i19_patch.object(_i19_storage, 'fine_storage_support', side_effect=AssertionError('assemble')), _i19_patch.object(_i19_fine, 'prepare_fine_segment', side_effect=AssertionError('prepare')):
            _i19_export_fine_mesh(self.chain, self.saved, self.geometry)
        _i19_np.testing.assert_array_equal(before, self.chain['arrays']['H0_m'])

class MountainManningTests(_i20_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from terrain_pipeline.lake import load_mountain_geometry as _i20_load_mountain_geometry
        from terrain_pipeline.channel_geometry import prepare_tributary_geometry as _i20_prepare_tributary_geometry
        from terrain_pipeline.common_infra import load_legacy_source as _i20_load_legacy_source
        source = _i20_load_legacy_source('pressure_mountain', boundary_policy='all_edges_open')
        path = _i20_Path('verification/mountain-lake-coupling/frozen-20261001-A-v3/pressure_mountain-geometry.npz')
        cls.geometry = _i20_load_mountain_geometry(path, trusted_height=source['arrays']['height_m'], source_binding={'source_identity': source['identity_sha256']})
        cls.record = _i20_prepare_tributary_geometry(cls.geometry)

    def run_case(self, q=0.0, tail_raise=0.0, dt=30.0, steps=20):
        initial = self.record['arrays']['min_bed_m'].copy()
        return _i20_storage.prepare_manning_storage(self.record, self.geometry, initial_stage_m=initial, inlet_q_m3_s=_i20_np.full(steps, q), lateral_q_m3_s=_i20_np.zeros((steps, 4)), tailwater_stage_m=_i20_np.full(steps + 1, initial[-1] + tail_raise), dt_s=dt)

    def test_analytical_v_section(self):
        from terrain_pipeline.channel_geometry import section_hydraulics as _i20_section_hydraulics
        result = _i20_section_hydraulics(_i20_np.array([-1.0, 0.0, 1.0]), _i20_np.array([1.0, 0.0, 1.0]), 0.5)
        self.assertAlmostEqual(result['area_m2'], 0.25)
        self.assertAlmostEqual(result['wetted_perimeter_m'], _i20_np.sqrt(2))
        self.assertAlmostEqual(result['top_width_m'], 1.0)

    def test_dry_no_creation_and_static_validation_no_solver(self):
        saved = self.run_case()
        self.assertEqual(saved['metadata']['status'], 'completed')
        self.assertEqual(saved['arrays']['storage_m3'].sum(), 0.0)
        with _i20_patch.object(_i20_storage, 'prepare_manning_storage', side_effect=AssertionError), _i20_patch.object(_i20_storage, '_i11_least_squares', side_effect=AssertionError):
            _i20_storage.validate_manning_storage(saved, self.record, self.geometry)

    def test_true_backflow(self):
        saved = self.run_case(tail_raise=0.08)
        self.assertEqual(saved['metadata']['status'], 'completed')
        self.assertLess(saved['arrays']['qedges_m3_s'][:, -1].sum(), 0.0)
        self.assertGreater(saved['arrays']['storage_m3'][-1].sum(), 0.0)

    def test_partial_wet_equilibrium_exact(self):
        level = float(self.record['arrays']['max_stage_m'].min() - 0.02)
        initial = _i20_np.maximum(level, self.record['arrays']['min_bed_m'])
        saved = _i20_storage.prepare_manning_storage(self.record, self.geometry, initial_stage_m=initial, inlet_q_m3_s=_i20_np.zeros(20), lateral_q_m3_s=_i20_np.zeros((20, 4)), tailwater_stage_m=_i20_np.full(21, level), dt_s=30.0)
        self.assertEqual(saved['metadata']['status'], 'completed')
        self.assertEqual(_i20_np.abs(saved['arrays']['qedges_m3_s']).sum(), 0.0)
        _i20_np.testing.assert_array_equal(saved['arrays']['stage_m'], _i20_np.tile(initial, (21, 1)))
        self.assertTrue((saved['arrays']['storage_m3'][0] == 0).any())
        self.assertTrue((saved['arrays']['storage_m3'][0] > 0).any())

    def test_bank_refusal_and_budget_prefix(self):
        saved = self.run_case(q=2.0)
        self.assertEqual(saved['metadata']['status'], 'refused')
        with _i20_patch.object(_i20_storage, 'MAX_EVALUATIONS', 10):
            saved = self.run_case()
            self.assertEqual(saved['metadata']['committed_steps'], 5)
            self.assertEqual(saved['metadata']['failure']['reason'], 'residual_evaluation_budget_exhausted')

    def test_forgeries_and_negative_forcing(self):
        saved = self.run_case()
        for mutate in (lambda item: item['metadata'].update(status='unknown'), lambda item: item['arrays']['inlet_q_m3_s'].fill(-1.0), lambda item: item['arrays']['qedges_m3_s'].fill(0.1)):
            forged = _i20_deepcopy(saved)
            mutate(forged)
            with self.assertRaises(ValueError):
                _i20_storage.validate_manning_storage(forged, self.record, self.geometry)

    def test_dt_sensitivity_same_input_volume(self):
        coarse = self.run_case(q=0.01, steps=40)
        fine = self.run_case(q=0.01, dt=15.0, steps=80)
        self.assertEqual(coarse['metadata']['status'], 'completed')
        self.assertEqual(fine['metadata']['status'], 'completed')
        self.assertLess(abs(coarse['arrays']['storage_m3'][-1].sum() - fine['arrays']['storage_m3'][-1].sum()), 0.01)

    def test_archive_cold_load_no_clobber_and_external_forcing(self):
        from terrain_pipeline.common_infra import file_sha256 as _i20_file_sha256
        saved = self.run_case(q=0.01)
        forcing = {key: saved['arrays'][key] for key in ('initial_stage_m', 'inlet_q_m3_s', 'lateral_q_m3_s', 'tailwater_stage_m')}
        forcing['dt_s'] = 30.0
        with _i20_tempfile.TemporaryDirectory() as folder:
            path = _i20_Path(folder) / 'state.npz'
            _i20_storage.save_manning_storage(path, saved, self.record, self.geometry)
            with self.assertRaises(FileExistsError):
                _i20_storage.save_manning_storage(path, saved, self.record, self.geometry)
            with _i20_patch.object(_i20_storage, 'prepare_manning_storage', side_effect=AssertionError), _i20_patch.object(_i20_storage, '_i11_least_squares', side_effect=AssertionError):
                _i20_storage.load_manning_storage(path, self.record, self.geometry, expected_sha256=_i20_file_sha256(path), trusted_forcing=forcing)
            changed = _i20_deepcopy(forcing)
            changed['inlet_q_m3_s'] *= 2
            with self.assertRaises(ValueError):
                _i20_storage.load_manning_storage(path, self.record, self.geometry, expected_sha256=_i20_file_sha256(path), trusted_forcing=changed)

    def test_mesh_saved_water_and_forgery(self):
        from terrain_pipeline.channel_geometry import export_manning_mesh
        from terrain_pipeline.channel_geometry import validate_manning_mesh
        saved = self.run_case(tail_raise=0.08)
        mesh = export_manning_mesh(self.record, saved, self.geometry)
        stats = validate_manning_mesh(mesh, self.record, saved, self.geometry)
        self.assertEqual(stats['minimum_normal_Y'], 1.0)
        forged = _i20_deepcopy(mesh)
        forged['arrays']['water_depth_m'] += 0.01
        with self.assertRaises(ValueError):
            validate_manning_mesh(forged, self.record, saved, self.geometry)

    def test_any_interval_capacity_detects_overload_after_early_dry_credit(self):
        initial = self.record['arrays']['min_bed_m']
        q = _i20_np.r_[_i20_np.zeros(30), _i20_np.full(30, 2.0)]
        limit = _i20_storage.capacity_bound(self.record, inlet_q_m3_s=q, lateral_q_m3_s=_i20_np.zeros((60, 4)), tailwater_stage_m=_i20_np.full(61, initial[-1]), dt_s=30.0)
        self.assertIsNotNone(limit['any_interval_first_exceed_step'])
        self.assertGreater(limit['any_interval_drawup_m3'].max(), limit['capacity_m3'].sum())

def make(q=1.0, params=None):
    from terrain_pipeline.channel_geometry import build_section as _i21_build_section
    h = _i21_np.array([[4.0, 3.0, 2.0, 1.0]], _i21_np.float64)
    selection = {'chosen': {'stem_flat_cells': _i21_np.array([0, 1, 2, 3], _i21_np.int64)}}
    return _i21_build_section(h, selection, q, origin_native_xz=(-3, 7), section_parameters={} if params is None else params)

class TestNative30mSection(_i21_unittest.TestCase):

    def test_default_section(self):
        out = make()
        a = out['arrays']
        _i21_np.testing.assert_array_equal(a['node_xz_m'], [[-90.0, 210.0], [0.0, 210.0]])
        self.assertTrue(_i21_np.all(a['width_m'] > 0))
        self.assertTrue(_i21_np.all(a['normal_depth_m'] > 0))
        W = a['width_m']
        d = a['normal_depth_m']
        R = W * d / (W + 2.0 * d)
        src = a['source_slope_per_m']
        Q = W * d * R ** (2.0 / 3.0) * _i21_np.sqrt(src) / 0.035
        _i21_np.testing.assert_allclose(a['design_q_m3_s'], Q, rtol=1e-08)
        m = out['metadata']
        self.assertEqual(m['full_stem_length_m'], 90)
        self.assertEqual(m['sampled_stem_length_m'], 90)
        self.assertTrue(m['normal_depth_not_bankfull'])

    def test_invalid_q(self):
        with self.assertRaises((TypeError, ValueError)):
            make(q=True)
        with self.assertRaises((TypeError, ValueError)):
            make(q='1')

    def test_depth_budget_exceeded(self):
        with self.assertRaises(ValueError) as ctx:
            make(params={'max_depth_m': 1e-12})
        self.assertIn('depth_budget_exceeded', str(ctx.exception))

    def test_resample_stride(self):
        from terrain_pipeline.channel_geometry import build_section as _i21_build_section
        out = make(params={'resample_stride': 1})
        a = out['arrays']
        self.assertEqual(len(a['node_xz_m']), 4)
        self.assertEqual(out['metadata']['actual_stride'], 1)
        h = _i21_np.array([[4.0, 3.0, 2.0, 1.0]], _i21_np.float64)
        h_before = h.copy()
        selection = {'chosen': {'stem_flat_cells': _i21_np.array([0, 1, 2, 3], _i21_np.int64)}}
        _i21_build_section(h, selection, 1.0, origin_native_xz=(-3, 7), section_parameters={'resample_stride': 1})
        _i21_np.testing.assert_array_equal(h, h_before)

class NetworkValleyTests(_i22_unittest.TestCase):

    def setUp(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i22_ChannelRecipe
        from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i22_NetworkValleyRecipe
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i22_ValleyGeometryRecipe
        self.base = _x0_confluence_plan()
        params = self.base['identity']['parameters']
        self.channel = _i22_ChannelRecipe(**{name: params[name] for name in _i22_ChannelRecipe.__dataclass_fields__})
        arrays = self.base['arrays']
        discharge = arrays['discharge_m3_s'].copy()
        discharge.flat[[17, 24, 31, 38, 45]] = 0.2
        self.base = self.replan(discharge=discharge)
        self.recipe = _i22_NetworkValleyRecipe(3.75, 30.0, 30.0, 1e-05)
        self.budget = _i22_ValleyGeometryRecipe(8.0, 10000.0, 100000.0, 100000.0)
        self.domain = _i22_np.ones((7, 7), bool)
        self.protected = _i22_np.zeros((7, 7), bool)

    def replan(self, height=None, discharge=None, channel=None, spacing=(10.0, 10.0)):
        from terrain_pipeline.channel_geometry import plan_channel as _i22_plan_channel
        arrays = self.base['arrays']
        return _i22_plan_channel(arrays['source_height_m'] if height is None else height, arrays['receiver'], arrays['order'], arrays['outlet_mask'], arrays['discharge_m3_s'] if discharge is None else discharge, *spacing, 0.0, 0.0, 0.0, 'network-test', channel or self.channel)

    def prepare(self, plan=None, recipe=None, budget=None, domain=None, protected=None, channel=None):
        from terrain_pipeline.channel_geometry import prepare_network_valley as _i22_prepare_network_valley
        return _i22_prepare_network_valley(self.base if plan is None else plan, self.domain if domain is None else domain, self.protected if protected is None else protected, recipe or self.recipe, budget or self.budget, channel or self.channel)

    def surface(self, valley, budget=None):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i22_InundationRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i22_StageRecipe
        from terrain_pipeline.channel_geometry import SectionRecipe as _i22_SectionRecipe
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i22_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import prepare_surface_network as _i22_prepare_surface_network
        domain = _i22_np.ones((61, 61), bool)
        empty = _i22_np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        return _i22_prepare_surface_network(valley['replanned_plan'], 0.0, 0.0, 1.0, 1.0, (61, 61), domain, empty, legal, _i22_np.array([5.2]), _i22_SectionRecipe(), _i22_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i22_InundationRecipe(max_lateral_reach_m=15.0), budget or _i22_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))

    def test_complete_real_edges_shared_floor_width_and_nominal_bed(self):
        from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i22_NetworkValleyRecipe
        discharge = self.base['arrays']['discharge_m3_s'].copy()
        discharge.flat[[9, 11, 17, 24, 31, 38, 45]] = [0.1, 0.2, 0.3, 0.3, 0.3, 0.3, 0.3]
        channel = _i22_replace(self.channel, min_depth_m=0.2, max_depth_m=3.0, depth_exponent=0.5, min_width_m=1.0, max_width_m=30.0, width_exponent=0.5)
        plan = self.replan(discharge=discharge, channel=channel, spacing=(6.0, 10.0))
        result = self.prepare(plan=plan, channel=channel, recipe=_i22_NetworkValleyRecipe(2.0, 1.0, 60.0, 0.02))
        network = result['network']
        edges = network['active_edges']
        donors = _i22_np.flatnonzero(plan['arrays']['channel_mask'].ravel() & (plan['arrays']['receiver'] >= 0))
        expected = _i22_np.column_stack((donors, plan['arrays']['receiver'][donors]))
        _i22_np.testing.assert_array_equal(edges, expected)
        self.assertEqual(len(edges), _i22_np.count_nonzero(plan['arrays']['channel_mask'].ravel() & (plan['arrays']['receiver'] >= 0)))
        floor = network['floor_elevation_m'].ravel()
        depth = plan['arrays']['nominal_depth_m'].ravel()
        for (donor, receiver), length in zip(edges, network['edge_length_m']):
            self.assertLessEqual(floor[receiver], floor[donor] - 0.02 * length + 1e-12)
            self.assertLessEqual(floor[receiver] - depth[receiver], floor[donor] - depth[donor] - channel.min_bed_slope_m_per_m * length + 1e-12)
        _i22_np.testing.assert_allclose(network['edge_length_m'], _i22_np.hypot((edges[:, 1] % 7 - edges[:, 0] % 7) * 6.0, (edges[:, 1] // 7 - edges[:, 0] // 7) * 10.0))
        _i22_np.testing.assert_array_equal(network['width_m'][network['active_mask']], plan['arrays']['nominal_width_m'][network['active_mask']] * 2.0)
        self.assertTrue(_i22_np.all(floor <= plan['arrays']['source_height_m'].ravel()))

    def test_decreasing_nominal_depth_requires_extra_floor_drop(self):
        discharge = self.base['arrays']['discharge_m3_s'].copy()
        discharge.flat[[9, 11]] = 1.0
        channel = _i22_replace(self.channel, min_depth_m=0.1, max_depth_m=3.0, depth_exponent=0.5)
        plan = self.replan(discharge=discharge, channel=channel)
        result = self.prepare(plan=plan, channel=channel)
        floor = result['network']['floor_elevation_m'].ravel()
        depth = plan['arrays']['nominal_depth_m'].ravel()
        for donor, target in result['network']['active_edges']:
            length = 10.0 * _i22_math.hypot(target % 7 - donor % 7, target // 7 - donor // 7)
            self.assertLessEqual(floor[target] - depth[target], floor[donor] - depth[donor] - channel.min_bed_slope_m_per_m * length + 1e-12)
        self.assertLess(floor[17], plan['arrays']['source_height_m'].flat[17])

    def test_width_bounds_and_threshold_independence(self):
        from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i22_NetworkValleyRecipe
        recipe = _i22_NetworkValleyRecipe(4.0, 12.0, 20.0, 0.001)
        first = self.prepare(recipe=recipe)
        channel = _i22_replace(self.channel, start_discharge_m3_s=0.08)
        second = self.prepare(plan=self.replan(channel=channel), recipe=recipe, channel=channel)
        _i22_np.testing.assert_array_equal(first['network']['width_m'], second['network']['width_m'])
        self.assertTrue(_i22_np.all(first['network']['width_m'][first['network']['active_mask']] == 20.0))
        lower = self.prepare(recipe=_i22_NetworkValleyRecipe(0.1, 12.0, 20.0, 0.001))
        self.assertTrue(_i22_np.all(lower['network']['width_m'][lower['network']['active_mask']] == 12.0))

    def test_bbox_matches_full_union_and_duplicate_edges_do_not_sum(self):
        from terrain_pipeline.channel_geometry import _rasterize_valley_edges as _i22__rasterize_valley_edges
        source = _i22_np.arange(99, dtype=float).reshape(9, 11) / 10.0 + 10.0
        params = {'origin_x_m': -20.0, 'origin_z_m': 7.0, 'spacing_x_m': 3.0, 'spacing_z_m': 7.0}
        points = _i22_np.array([[[-17.0, 14.0], [-14.0, 21.0]], [[-11.0, 42.0], [-11.0, 49.0]]])
        floors = _i22_np.array([[9.0, 8.0], [7.0, 6.0]])
        widths = _i22_np.array([[14.0, 19.0], [9.0, 11.0]])
        full = _i22__rasterize_valley_edges(source, params, points, floors, widths)
        local = _i22__rasterize_valley_edges(source, params, points, floors, widths, local_bounds=True)
        _i22_np.testing.assert_array_equal(local, full)
        repeated = _i22__rasterize_valley_edges(source, params, _i22_np.repeat(points, 2, axis=0), _i22_np.repeat(floors, 2, axis=0), _i22_np.repeat(widths, 2, axis=0), local_bounds=True)
        _i22_np.testing.assert_array_equal(repeated, full)

    def test_network_union_and_unrelated_tributaries_are_not_joined(self):
        from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _i22_NetworkValleyRecipe
        from terrain_pipeline.channel_geometry import _rasterize_valley_edges as _i22__rasterize_valley_edges
        result = self.prepare(recipe=_i22_NetworkValleyRecipe(1.0, 8.0, 8.0, 0.001))
        network = result['network']
        edges = network['active_edges']
        points = _i22_np.stack((edges % 7 * 10.0, edges // 7 * 10.0), axis=2)
        expected = _i22__rasterize_valley_edges(self.base['arrays']['source_height_m'], self.base['identity']['parameters'], points, network['floor_elevation_m'].ravel()[edges], network['width_m'].ravel()[edges])
        _i22_np.testing.assert_array_equal(result['arrays']['valley_cut_m'], expected)
        self.assertEqual(result['arrays']['valley_cut_m'][1, 0], 0.0)

    def test_rasterization_work_is_local_not_edge_times_domain(self):
        from terrain_pipeline.channel_geometry import _rasterize_valley_edges as _i22__rasterize_valley_edges
        source = _i22_np.full((487, 487), 10.0)
        params = {'origin_x_m': 0.0, 'origin_z_m': 0.0, 'spacing_x_m': 10.0, 'spacing_z_m': 10.0}
        points = _i22_np.array([[[100.0, 100.0], [110.0, 110.0]]])
        points = _i22_np.repeat(points, 2325, axis=0)
        floors = _i22_np.full((2325, 2), 8.0)
        widths = _i22_np.full((2325, 2), 30.0)
        meshgrid = _i22_np.meshgrid
        sizes = []

        def record_grid(grid_x, grid_z):
            sizes.append(len(grid_x) * len(grid_z))
            return meshgrid(grid_x, grid_z)
        with _i22_patch('terrain_pipeline.channel_geometry.np.meshgrid', side_effect=record_grid):
            cut = _i22__rasterize_valley_edges(source, params, points, floors, widths, local_bounds=True)
        self.assertEqual(len(sizes), 2325)
        self.assertLessEqual(max(sizes), 25)
        self.assertEqual(cut[10, 10], 2.0)

    def test_budget_failures_are_not_clipped(self):
        height = self.base['arrays']['source_height_m'].copy()
        height[3, 3] += 5.0
        plan = self.replan(height=height)
        generous = self.prepare(plan=plan)
        cases = [(_i22_replace(self.budget, max_valley_depth_m=0.1), 'valley_depth'), (_i22_replace(self.budget, max_valley_area_m2=0.0), 'valley_area'), (_i22_replace(self.budget, max_valley_volume_m3=0.0), 'valley_volume'), (_i22_replace(self.budget, max_total_cut_volume_m3=0.0), 'total_volume'), (_i22_replace(self.budget, max_total_cut_area_m2=0.0), 'total_area')]
        for budget, key in cases:
            with self.subTest(key=key):
                result = self.prepare(plan=plan, budget=budget)
                self.assertFalse(result['summary']['geometry_feasible'])
                self.assertTrue(result['summary']['failures'][key])
                _i22_np.testing.assert_array_equal(result['arrays']['valley_cut_m'], generous['arrays']['valley_cut_m'])
                self.assertEqual(result['status'], 'diagnostic_not_publishable')

    def test_domain_and_protection_failure_survive_fine_ledger(self):
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i22_evaluate_fine_valley_ledger
        for mask_name, key in (('domain', 'active_domain'), ('protected', 'active_protection')):
            with self.subTest(mask=mask_name):
                mask = self.domain.copy() if mask_name == 'domain' else self.protected.copy()
                mask.flat[9] = mask_name == 'protected'
                result = self.prepare(**{mask_name: mask})
                self.assertTrue(result['summary']['failures'][key])
                surface = self.surface(result)
                ledger = _i22_evaluate_fine_valley_ledger(result, surface)
                self.assertTrue(ledger['summary']['failures']['coarse_valley'])
                self.assertEqual(ledger['status'], 'diagnostic_not_publishable')

    def test_raised_ridge_fine_ledger_and_round_trip(self):
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i22_evaluate_fine_valley_ledger
        from terrain_pipeline.channel_geometry import load_fine_valley_ledger as _i22_load_fine_valley_ledger
        from terrain_pipeline.channel_geometry import save_fine_valley_ledger as _i22_save_fine_valley_ledger
        height = self.base['arrays']['source_height_m'].copy()
        height[3, 3] += 5.0
        plan = self.replan(height=height)
        self.assertTrue(plan['arrays']['over_budget_mask'].any())
        valley = self.prepare(plan=plan)
        self.assertTrue(valley['summary']['geometry_feasible'])
        surface = self.surface(valley)
        ledger = _i22_evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger['status'], 'prepared')
        _i22_np.testing.assert_allclose(ledger['arrays']['valley_cut_m'] + ledger['arrays']['bed_cut_m'], ledger['arrays']['total_cut_m'], rtol=0, atol=1e-08)
        with _i22_tempfile.TemporaryDirectory() as directory:
            path = _i22_Path(directory) / 'fine.npz'
            _i22_save_fine_valley_ledger(ledger, path)
            self.assertEqual(_i22_load_fine_valley_ledger(path)['identity_sha256'], ledger['identity_sha256'])
        for value in ledger['arrays'].values():
            with self.assertRaises(ValueError):
                value.flags.writeable = True

    def test_determinism_source_unchanged_and_hard_immutable_outputs(self):
        from terrain_pipeline.artifacts.contracts import array_hash as _i22_array_hash
        from terrain_pipeline.channel_geometry import validate_network_valley as _i22_validate_network_valley
        before = {name: _i22_array_hash(value) for name, value in self.base['arrays'].items()}
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first['identity_sha256'], second['identity_sha256'])
        self.assertEqual(before, {name: _i22_array_hash(value) for name, value in self.base['arrays'].items()})
        for collection in (first['arrays'], first['network'], first['replanned_plan']['arrays']):
            for value in collection.values():
                with self.assertRaises(ValueError):
                    value.flags.writeable = True
        _i22_validate_network_valley(first)

    def test_opt_in_identity_and_parent_change_with_parameters_and_masks(self):
        from terrain_pipeline.channel_geometry import PLANNING_VERSION as _i22_PLANNING_VERSION
        first = self.prepare()
        second = self.prepare(recipe=_i22_replace(self.recipe, min_floor_slope_m_per_m=2e-05))
        self.assertNotEqual(first['planning_identity_sha256'], second['planning_identity_sha256'])
        self.assertNotEqual(first['identity_sha256'], second['identity_sha256'])
        self.assertEqual(first['replanned_plan']['identity']['parameters']['source_identity'], first['planning_identity_sha256'])
        protected = self.protected.copy()
        protected[0, 0] = True
        third = self.prepare(protected=protected)
        self.assertNotEqual(first['planning_identity_sha256'], third['planning_identity_sha256'])
        self.assertEqual(first['planning_identity']['algorithm_version'], _i22_PLANNING_VERSION)

    def test_all_source_and_derived_plan_fields_are_validated(self):
        for name in self.base['arrays']:
            with self.subTest(field=name):
                altered = _i22_deepcopy(self.base)
                value = altered['arrays'][name].copy()
                value.flat[0] = not value.flat[0] if value.dtype == bool else value.flat[0] + 1
                altered['arrays'][name] = value
                with self.assertRaises(ValueError):
                    self.prepare(plan=altered)

    def test_invalid_topology_even_with_rehashed_sources(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i22_ArtifactIdentity
        from terrain_pipeline.artifacts.contracts import array_hash as _i22_array_hash
        for field in ('receiver', 'order'):
            altered = _i22_deepcopy(self.base)
            value = altered['arrays'][field].copy()
            if field == 'receiver':
                value[9] = 45
            else:
                value[[0, -1]] = value[[-1, 0]]
            altered['arrays'][field] = value
            params = altered['identity']['parameters']
            params['source_route_sha256' if field == 'receiver' else 'source_order_sha256'] = _i22_array_hash(value)
            altered['identity_sha256'] = _i22_ArtifactIdentity(**altered['identity']).sha256
            with self.assertRaises(ValueError):
                self.prepare(plan=altered)

    def test_recipe_mismatch_empty_network_and_invalid_masks(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.prepare(channel=_i22_replace(self.channel, start_discharge_m3_s=0.08))
        discharge = _i22_np.full((7, 7), 0.01)
        discharge.flat[45] = 0.1
        with self.assertRaisesRegex(ValueError, 'active graph edge'):
            self.prepare(plan=self.replan(discharge=discharge))
        for mask in (_i22_np.ones((7, 7), float), _i22_np.ones((2, 2), bool)):
            with self.assertRaises(ValueError):
                self.prepare(domain=mask)
        for field in _i22_asdict(self.recipe):
            for value in (True, 0.0, -1.0, float('inf'), float('nan')):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        _i22_replace(self.recipe, **{field: value})
        with self.assertRaises(ValueError):
            _i22_replace(self.recipe, min_width_m=31.0)

    def test_output_tampering_rejected_before_fine_ledger(self):
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i22_evaluate_fine_valley_ledger
        valley = self.prepare()
        surface = self.surface(valley)
        for collection in ('network', 'arrays'):
            for name in valley[collection]:
                with self.subTest(collection=collection, field=name):
                    changed = _i22_deepcopy(valley)
                    value = changed[collection][name].copy()
                    value.flat[0] = not value.flat[0] if value.dtype == bool else value.flat[0] + 1
                    changed[collection][name] = value
                    with self.assertRaises(ValueError):
                        _i22_evaluate_fine_valley_ledger(changed, surface)
        changed = _i22_deepcopy(valley)
        changed['summary']['geometry_feasible'] = False
        with self.assertRaises(ValueError):
            _i22_evaluate_fine_valley_ledger(changed, surface)
        changed = _i22_deepcopy(valley)
        changed['replanned_plan']['arrays']['nominal_depth_m'] = _i22_np.ones((7, 7))
        with self.assertRaises(ValueError):
            _i22_evaluate_fine_valley_ledger(changed, surface)
        changed = _i22_deepcopy(surface)
        changed['arrays']['final_surface_m'] = changed['arrays']['final_surface_m'].copy()
        changed['arrays']['final_surface_m'][0, 0] += 1.0
        with self.assertRaises(ValueError):
            _i22_evaluate_fine_valley_ledger(valley, changed)

    def test_rehashed_failed_valley_cannot_be_promoted_to_feasible(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i22_ArtifactIdentity
        from terrain_pipeline.artifacts.contracts import digest as _i22_digest
        from terrain_pipeline.channel_geometry import save_network_valley as _i22_save_network_valley
        from terrain_pipeline.channel_geometry import validate_network_valley as _i22_validate_network_valley
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i22_ValleyGeometryRecipe
        failed = self.prepare(budget=_i22_ValleyGeometryRecipe(0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertFalse(failed['summary']['geometry_feasible'])
        for erase_failures in (False, True):
            changed = _i22_deepcopy(failed)
            changed['summary']['geometry_feasible'] = True
            if erase_failures:
                changed['summary']['failures'] = dict.fromkeys(changed['summary']['failures'], False)
            changed['identity']['parameters']['summary_sha256'] = _i22_digest(changed['summary'])
            changed['identity_sha256'] = _i22_ArtifactIdentity(**changed['identity']).sha256
            with self.assertRaisesRegex(ValueError, 'semantics mismatch'):
                _i22_validate_network_valley(changed)
            with _i22_tempfile.TemporaryDirectory() as directory:
                path = _i22_Path(directory) / 'forged.npz'
                with self.assertRaises(ValueError):
                    _i22_save_network_valley(changed, path)
                self.assertEqual(list(_i22_Path(directory).iterdir()), [])

    def test_rehashed_failed_surface_cannot_make_fine_ledger_prepared(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i22_ArtifactIdentity
        from terrain_pipeline.artifacts.contracts import digest as _i22_digest
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i22_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import validate_surface_network as _i22_validate_surface_network
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i22_evaluate_fine_valley_ledger
        valley = self.prepare()
        failed = self.surface(valley, budget=_i22_SurfaceNetworkBudget(4.0, 0.0, 0.0))
        self.assertEqual(failed['status'], 'diagnostic_not_publishable')
        honest = _i22_evaluate_fine_valley_ledger(valley, failed)
        self.assertEqual(honest['status'], 'diagnostic_not_publishable')
        for erase_failures in (False, True):
            changed = _i22_deepcopy(failed)
            changed['status'] = 'prepared'
            changed['summary']['publishable'] = True
            if erase_failures:
                changed['summary']['budget_failures'] = dict.fromkeys(changed['summary']['budget_failures'], False)
                changed['summary']['joint_blockers'] = dict.fromkeys(changed['summary']['joint_blockers'], False)
            changed['identity']['parameters']['summary_sha256'] = _i22_digest(changed['summary'])
            changed['identity_sha256'] = _i22_ArtifactIdentity(**changed['identity']).sha256
            with self.assertRaises(ValueError):
                _i22_validate_surface_network(changed, allow_diagnostic=True)
            with self.assertRaises(ValueError):
                _i22_evaluate_fine_valley_ledger(valley, changed)

    def test_diagnostic_bundle_round_trip_immutable_and_no_overwrite(self):
        from terrain_pipeline.channel_geometry import load_network_valley as _i22_load_network_valley
        from terrain_pipeline.channel_geometry import save_network_valley as _i22_save_network_valley
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i22_ValleyGeometryRecipe
        for budget in (self.budget, _i22_ValleyGeometryRecipe(0.0, 0.0, 0.0, 0.0)):
            with self.subTest(budget=budget), _i22_tempfile.TemporaryDirectory() as directory:
                valley = self.prepare(budget=budget)
                path = _i22_Path(directory) / 'network.npz'
                self.assertEqual(_i22_save_network_valley(valley, path), path)
                loaded = _i22_load_network_valley(path)
                self.assertEqual(loaded['identity_sha256'], valley['identity_sha256'])
                self.assertEqual(loaded['planning_identity'], valley['planning_identity'])
                self.assertEqual(loaded['summary'], valley['summary'])
                for actual, original in ((loaded['arrays'], valley['arrays']), (loaded['network'], valley['network']), (loaded['replanned_plan']['arrays'], valley['replanned_plan']['arrays'])):
                    self.assertEqual(set(actual), set(original))
                    for name in actual:
                        _i22_np.testing.assert_array_equal(actual[name], original[name])
                        with self.assertRaises(ValueError):
                            actual[name].flags.writeable = True
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    _i22_save_network_valley(valley, path)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(len(list(_i22_Path(directory).iterdir())), 1)

    def test_diagnostic_archive_tampering_and_field_set_rejected(self):
        from terrain_pipeline.channel_geometry import _array_digest as _i22__array_digest
        from terrain_pipeline.channel_geometry import load_network_valley as _i22_load_network_valley
        from terrain_pipeline.channel_geometry import save_network_valley as _i22_save_network_valley
        valley = self.prepare()
        with _i22_tempfile.TemporaryDirectory() as directory:
            path = _i22_Path(directory) / 'valid.npz'
            _i22_save_network_valley(valley, path)
            with _i22_np.load(path, allow_pickle=False) as archive:
                manifest = str(archive['manifest'].item())
                payload = {name: archive[name].copy() for name in archive.files if name != 'manifest'}
            for action in ('mutate', 'extra', 'missing'):
                changed = {name: value.copy() for name, value in payload.items()}
                if action == 'mutate':
                    changed['network__width_m'].flat[17] += 1.0
                elif action == 'extra':
                    changed['network__unexpected'] = _i22_np.zeros(1)
                else:
                    del changed['replanned__target_bed_m']
                import json
                record = json.loads(manifest)
                record['payload_sha256'] = _i22__array_digest(changed)
                damaged = _i22_Path(directory) / f'{action}.npz'
                _i22_np.savez_compressed(damaged, manifest=json.dumps(record), **changed)
                with self.assertRaises(ValueError):
                    _i22_load_network_valley(damaged)

    def test_atomic_diagnostic_save_cleans_temporary_on_link_failure(self):
        from terrain_pipeline.channel_geometry import save_network_valley as _i22_save_network_valley
        with _i22_tempfile.TemporaryDirectory() as directory:
            path = _i22_Path(directory) / 'network.npz'
            with _i22_patch('terrain_pipeline.channel_geometry.os.link', side_effect=FileExistsError('race')):
                with self.assertRaises(FileExistsError):
                    _i22_save_network_valley(self.prepare(), path)
            self.assertEqual(list(_i22_Path(directory).iterdir()), [])

    def test_rehashed_source_h0_and_parent_mismatch_rejected(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i22_ArtifactIdentity
        from terrain_pipeline.channel_geometry import _array_digest as _i22__array_digest
        from terrain_pipeline.channel_geometry import validate_network_valley as _i22_validate_network_valley
        valley = self.prepare()
        changed = _i22_deepcopy(valley)
        changed['arrays']['source_height_m'] = changed['arrays']['source_height_m'].copy()
        changed['arrays']['source_height_m'][0, 0] += 1.0
        changed['identity']['parameters']['arrays_sha256'] = _i22__array_digest(changed['arrays'])
        changed['identity_sha256'] = _i22_ArtifactIdentity(**changed['identity']).sha256
        with self.assertRaises(ValueError):
            _i22_validate_network_valley(changed)
        changed = _i22_deepcopy(valley)
        changed['planning_identity']['parameters']['source_plan_sha256'] = 'wrong-parent'
        changed['planning_identity_sha256'] = _i22_ArtifactIdentity(**changed['planning_identity']).sha256
        with self.assertRaises(ValueError):
            _i22_validate_network_valley(changed)
        changed = _i22_deepcopy(valley)
        changed['identity']['parameters']['replanned_sha256'] = self.base['identity_sha256']
        changed['identity_sha256'] = _i22_ArtifactIdentity(**changed['identity']).sha256
        with self.assertRaises(ValueError):
            _i22_validate_network_valley(changed)

    def test_synthetic_fixture_discharge_conserves_at_confluence(self):
        arrays = self.base['arrays']
        discharge = arrays['discharge_m3_s']
        runoff = discharge.ravel().copy()
        for donor in _i22_np.flatnonzero(arrays['receiver'] >= 0):
            runoff[arrays['receiver'][donor]] -= discharge.flat[donor]
        self.assertTrue(_i22_np.all(runoff >= 0.0))
        self.assertAlmostEqual(float(runoff.sum()), float(discharge[arrays['outlet_mask']].sum()))
        self.assertEqual(discharge.flat[9] + discharge.flat[11], discharge.flat[17])

    def test_original_explicit_api_geometry_and_identity(self):
        from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i22_ArtifactIdentity
        from terrain_pipeline.artifacts.contracts import array_hash as _i22_array_hash
        from terrain_pipeline.artifacts.contracts import digest as _i22_digest
        from terrain_pipeline.channel_geometry import prepare_valley_geometry as _i22_prepare_valley_geometry
        points = _i22_np.array([[30.0, 10.0], [30.0, 60.0]])
        floors = _i22_np.array([4.7, 3.7])
        widths = _i22_np.array([30.0, 30.0])
        result = _i22_prepare_valley_geometry(self.base, points, floors, widths, self.domain, self.protected, self.budget, self.channel)
        grid_x, grid_z = _i22_np.meshgrid(_i22_np.arange(7) * 10.0, _i22_np.arange(7) * 10.0)
        fraction = _i22_np.clip((grid_z - 10.0) / 50.0, 0.0, 1.0)
        distance = _i22_np.hypot(grid_x - 30.0, grid_z - (10.0 + fraction * 50.0))
        floor = (1 - fraction) * 4.7 + fraction * 3.7
        cut = _i22_np.zeros((7, 7))
        inside = distance < 15.0
        cut[inside] = _i22_np.maximum(0.0, self.base['arrays']['source_height_m'][inside] - floor[inside]) * (0.5 * (1 + _i22_np.cos(_i22_np.pi * distance[inside] / 15.0)))
        _i22_np.testing.assert_array_equal(result['arrays']['valley_cut_m'], cut)
        identity = _i22_ArtifactIdentity('Terragenesis', 'valley-geometry', 'valley-geometry-v1', 0, {**_i22_asdict(self.budget), 'source_plan_sha256': self.base['identity_sha256'], 'replanned_sha256': result['replanned_plan']['identity_sha256'], 'centerline_sha256': _i22_array_hash(points), 'floor_sha256': _i22_array_hash(floors), 'width_sha256': _i22_array_hash(widths), 'domain_sha256': _i22_array_hash(self.domain), 'protected_sha256': _i22_array_hash(self.protected), 'arrays_sha256': _i22_digest({name: _i22_array_hash(value) for name, value in result['arrays'].items()}), 'summary_sha256': _i22_digest(result['summary'])})
        self.assertEqual(result['identity_sha256'], identity.sha256)
        self.assertEqual(result['replanned_plan']['identity']['parameters']['source_identity'], self.base['identity_sha256'])

def test_confluence_shares_downstream_bed():
    from terrain_pipeline.channel_geometry import solve_shared_bed as _i23_solve_shared_bed
    bed, component, reasons = _i23_solve_shared_bed([10, 9, 11, 10], [[0, 2], [1, 2], [2, 3]])
    _i23_np.testing.assert_allclose(bed, [10, 9, 9, 9])
    assert len(set(component)) == 1 and reasons == ['accepted']

def test_downstream_cap_rejects_whole_connected_path():
    from terrain_pipeline.channel_geometry import solve_shared_bed as _i23_solve_shared_bed
    bed, _, reasons = _i23_solve_shared_bed([10, 12, 15], [[0, 1], [1, 2]])
    assert _i23_np.isnan(bed).all() and reasons == ['downstream_cut_cap']

def test_crossing_geometry_cycle_does_not_change_original_flow():
    from terrain_pipeline.channel_geometry import solve_shared_bed_scc
    arcs = _i23_np.array([[0, 2], [2, 3], [3, 4], [1, 3], [3, 2], [2, 5]])
    bed, _, strong, bad = solve_shared_bed_scc([10, 10, 9, 9.5, 8, 8], arcs)
    assert strong[2] == strong[3]
    assert bed[2] == bed[3] == 9
    assert not bad.any()
    assert _i23_np.all(bed[arcs[:, 0]] >= bed[arcs[:, 1]])
    assert len(arcs) == 6
TEST_NEW_WORLD_NATIVE_WIDTH_ROOT = _i24_Path('.scratch/river-upgrade-20261101')
TASK = _i24_Path('.scratch/river-width-delta-20261102')

@_i24_unittest.skipUnless((TASK / 'width-reach.npz').exists(), 'saved source unavailable')
class NativeWidthIntegrationTest(_i24_unittest.TestCase):

    def test_published_network_uses_known_budget_and_preserves_water_anchors(self):
        from terrain_pipeline.channel_geometry import build_native_width_network as _i24_build_native_width_network
        with _i24_tempfile.TemporaryDirectory() as tmp:
            out = _i24_Path(tmp) / 'network'
            stale = _i24_Path(tmp) / 'node_velocity_m_s.npy'
            _i24_np.save(stale, _i24_np.array([123.0]))
            original_iterdir = _i24_Path.iterdir

            def source_files(path):
                files = list(original_iterdir(path))
                if path == TEST_NEW_WORLD_NATIVE_WIDTH_ROOT / 'native-network-v4':
                    files.append(stale)
                return iter(files)
            with _i24_patch.object(_i24_Path, 'iterdir', source_files):
                m = _i24_build_native_width_network(TEST_NEW_WORLD_NATIVE_WIDTH_ROOT, out, sediment_reach=TASK / 'width-reach.npz')
            self.assertFalse((out / 'node_velocity_m_s.npy').exists())
            self.assertIn('unavailable', m['velocity_policy'])
            for name in ('corridor_capacity_bound_m3.npy', 'sill_extra_storage_bound_m3.npy', 'sill_depth_m.npy'):
                self.assertFalse((out / name).exists())
                self.assertTrue((out / ('source_event_' + name)).exists())
                _i24_np.testing.assert_array_equal(_i24_np.load(out / ('source_event_' + name)), _i24_np.load(TEST_NEW_WORLD_NATIVE_WIDTH_ROOT / 'native-network-v4' / name))
            load = lambda name: _i24_np.load(out / (name + '.npy'))
            known = load('node_sediment_known')
            eligible = load('node_width_eligible')
            old = TEST_NEW_WORLD_NATIVE_WIDTH_ROOT / 'native-network-v4'
            self.assertEqual(known.sum(), 60)
            self.assertTrue(_i24_np.all(eligible[known]))
            self.assertTrue(_i24_np.isnan(load('node_sediment_incoming_solid_m3')[~known]).all())
            _i24_np.testing.assert_array_equal(load('node_stage_m'), _i24_np.load(old / 'node_stage_m.npy'))
            _i24_np.testing.assert_allclose(load('node_depth_m'), load('node_stage_m') - load('node_bed_m'))
            with _i24_np.load(TASK / 'width-reach.npz') as reach:
                indices = reach['network_index']
                _i24_np.testing.assert_allclose(load('node_width_m')[indices], reach['width_m'])
                _i24_np.testing.assert_allclose(load('node_bed_m')[indices], reach['bed_m'])
                _i24_np.testing.assert_allclose(load('node_sediment_final_loose_solid_m3')[indices], reach['sediment_trace_loose_solid_m3'][-1])
            nonriver = ~eligible
            _i24_np.testing.assert_array_equal(load('node_width_m')[nonriver], _i24_np.load(old / 'node_width_m.npy')[nonriver])
            self.assertEqual(m['committed_bed_new_edge_failures'], 0)

    def test_continuation_keeps_stocks_and_conserves(self):
        from terrain_pipeline.channel_geometry import continue_width_reach as _i24_continue_width_reach
        info = _i24_json.loads((TASK / 'width-reach.json').read_text(encoding='utf8'))
        with _i24_np.load(TASK / 'width-reach.npz') as source:
            a = {k: source[k] for k in source.files}
        water, sediment = _i24_continue_width_reach(a, info['final_geometry_sha256'], duration_s=10.0)
        h, s = (water['arrays'], sediment['arrays'])
        _i24_np.testing.assert_allclose(h['volume_m3'][0], a['storage_m3'])
        _i24_np.testing.assert_allclose(s['trace_bed_alluvium_solid_m3'][0], a['sediment_trace_loose_solid_m3'][-1])
        _i24_np.testing.assert_allclose(s['trace_mobile_solid_m3'][0], a['sediment_trace_mobile_solid_m3'][-1])
        _i24_np.testing.assert_allclose(s['domain_width_m'], a['width_m'])
        self.assertAlmostEqual(h['balance_residual_m3'].sum(), 0.0, places=8)
        self.assertAlmostEqual(s['step_balance_residual_m3'].sum(), 0.0, places=8)

class PreparationForwardingTest(_i24_unittest.TestCase):

    def test_formative_inputs_change_produced_geometry(self):
        from terrain_pipeline.new_world_rivers import prepare_rivers
        shape = (8, 8)
        channel = _i24_np.zeros(shape, bool)
        channel[3, 2] = True
        receiver = _i24_np.full(64, -1, dtype=_i24_np.int64)
        receiver[26] = 29
        empty = _i24_np.zeros(shape, bool)
        args = dict(bed_m=_i24_np.full(shape, 10.0), receiver=receiver, q_m3_s=_i24_np.ones(shape), channel_mask=channel, ocean_mask=empty, lake_mask=empty, unknown_mask=empty, protected_mask=empty, origin_native_xz=(0, 0), spacing_m=1.0, source_identity='scenario', bed_hardness=0.5, bank_hardness=0.5)
        narrow = prepare_rivers(**args, formative_section_inputs={'fracture': 0.0, 'bank_cohesion': 1.0})
        wide = prepare_rivers(**args, formative_section_inputs={'fracture': 1.0, 'bank_cohesion': 0.0})
        self.assertGreater(wide['graph']['node_width_m'][26], narrow['graph']['node_width_m'][26])
        self.assertGreater(wide['arrays']['cut_depth_m'].sum(), narrow['arrays']['cut_depth_m'].sum())

class RoutedWidthTest(_i25_unittest.TestCase):

    def test_committed_exchange_changes_width_without_second_debit(self):
        from terrain_pipeline.channel_geometry import section_from_routed_budget as _i25_section_from_routed_budget
        kw = dict(incoming_solid_m3=10.0, external_solid_m3=2.0, capacity_solid_m3=30.0, eroded_loose_solid_m3=3.0, eroded_rock_m3=1.0, deposited_solid_m3=1.0)
        section = _i25_section_from_routed_budget(5.0, 0.5, 0.5, 0.0, 0.2, **kw)
        self.assertGreater(section.width_m, section.baseline_width_m)
        self.assertEqual(section.eroded_solid_m3, 4.0)
        self.assertEqual(section.deposited_solid_m3, 1.0)
        kw['deposited_solid_m3'] = 8.0
        self.assertLess(_i25_section_from_routed_budget(5.0, 0.5, 0.5, 0.0, 0.2, **kw).width_m, section.baseline_width_m)
        kw['incoming_solid_m3'] = _i25_np.nan
        with self.assertRaises(ValueError):
            _i25_section_from_routed_budget(5.0, 0.5, 0.5, 0.0, 0.2, **kw)

    def test_reach_selection_follows_only_bounded_downhill_edges(self):
        from terrain_pipeline.channel_geometry import select_saved_reach as _i25_select_saved_reach
        edges = _i25_np.array([[0, 1], [1, 2], [2, 3], [4, 5]])
        status = _i25_np.array([0, 0, 1, 0])
        bed = _i25_np.array([5.0, 4.0, 3.0, 2.0, 5.0, 4.0])
        q = _i25_np.array([1.0, 1.5, 2.0, 3.0, 10.0, 10.0])
        _i25_np.testing.assert_array_equal(_i25_select_saved_reach(edges, status, bed, q, minimum_nodes=3), [0, 1, 2])

    def test_saved_reach_uses_committed_ledger_and_storage(self):
        from pathlib import Path
        from terrain_pipeline.channel_geometry import construct_saved_width_reach
        root = Path('.scratch/river-upgrade-20261101')
        if not (root / 'native-network-v4/manifest.json').exists():
            self.skipTest('saved native source unavailable')
        result = construct_saved_width_reach(root)
        a = result['arrays']
        self.assertGreaterEqual(len(a['receiver']), 60)
        _i25_np.testing.assert_array_equal(a['receiver'][:-1], _i25_np.arange(1, len(a['receiver'])))
        self.assertEqual(a['receiver'][-1], -1)
        _i25_np.testing.assert_allclose(a['bed_m'], a['sediment_trace_bed_m'][-1])
        _i25_np.testing.assert_allclose(a['storage_m3'], a['length_m'] * a['width_m'] * a['water_depth_m'])
        self.assertAlmostEqual(a['water_inflow_m3_s'].sum(), a['formative_q_m3_s'][-1])
        self.assertAlmostEqual(result['metadata']['sediment_metadata']['global_residual'], 0.0, places=8)
        self.assertGreater(a['sediment_eroded_loose_solid_m3'].sum(), 0.0)
        self.assertGreater(a['sediment_exported_solid_m3'].sum(), 0.0)

def heading(angle):
    return _i26_np.array([_i26_np.cos(_i26_np.radians(angle)), _i26_np.sin(_i26_np.radians(angle))])

def test_hyperbolic_turn_penalty_boundaries_and_growth():
    from terrain_pipeline.channel_geometry import turn_penalty as _i26_turn_penalty
    assert _i26_turn_penalty(heading(0), heading(45)) == _i26_pytest.approx(0.0, abs=1e-12)
    assert _i26_turn_penalty(heading(0), heading(20)) == 0.0
    multipliers = [1 + _i26_turn_penalty(heading(0), heading(a)) for a in (60, 75, 85, 89)]
    assert multipliers == _i26_pytest.approx([1.5, 3.0, 9.0, 45.0])
    assert _i26_np.all(_i26_np.diff(multipliers) > 0)
    assert _i26_np.isinf(_i26_turn_penalty(heading(0), heading(90)))
    assert _i26_np.isinf(_i26_turn_penalty(heading(0), heading(120)))
    assert _i26_turn_penalty(heading(0), heading(60), 2.0) == _i26_pytest.approx(1.0)
    for k in (-1.0, _i26_np.nan, _i26_np.inf):
        with _i26_pytest.raises(ValueError):
            _i26_turn_penalty(heading(0), heading(0), k)
    with _i26_pytest.raises(ValueError):
        _i26_turn_penalty([0.0, 0.0], [1.0, 0.0])

def test_edge_state_retains_more_expensive_arrival_for_legal_exit():
    from terrain_pipeline.channel_geometry import heading_path as _i26_heading_path
    points = _i26_np.array([[0.0, 0.0], [2.0, 0.0], [3.0, 1.0], [3.0, 2.0], [2.0, 3.0], [1.0, 3.0], [0.0, 3.0], [0.0, 1.0], [1.0, 4.0]])
    sources = _i26_np.array([0, 1, 2, 3, 4, 5, 0, 7, 6])
    ends = _i26_np.array([1, 2, 3, 4, 5, 6, 7, 6, 8])
    cost = _i26_np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 5.0, 5.0, 1.0])
    path = _i26_heading_path(sources, ends, cost, points, 0, [8], max_turn_deg=90.0)
    assert path.tolist() == [0, 7, 6, 8]
    assert _i26_heading_path(sources, ends, cost, points, 0, [8], max_turn_deg=90.0, end_directions=[[-1.0, 0.0]]) is None

def test_actual_irregular_path_enforces_endpoint_and_interior_turns():
    from terrain_pipeline.channel_geometry import turn_penalty as _i26_turn_penalty
    from terrain_pipeline.coastal_delta_routes import irregular_valley_path as _i26_irregular_valley_path
    bed = _i26_np.zeros((10, 10))
    valid = _i26_np.ones_like(bed, bool)
    cells, points = _i26_irregular_valley_path(bed, valid, (2, 2), (7, 7), 1.0, 100.0, world_seed=42, max_turn_deg=90.0, start_directions_xz=[[1.0, 0.0]], end_directions_xz=[[0.0, 1.0]])
    assert tuple(cells[0]) == (2, 2) and tuple(cells[-1]) == (7, 7)
    vectors = _i26_np.vstack(([1.0, 0.0], _i26_np.diff(points, axis=0), [0.0, 1.0]))
    assert all((_i26_np.isfinite(_i26_turn_penalty(a, b)) for a, b in zip(vectors, vectors[1:])))

def test_penalty_prefers_longer_gentle_legal_route():
    from terrain_pipeline.channel_geometry import heading_path as _i26_heading_path
    points = _i26_np.array([[0.0, 0.0], [1.0, 0.0], [1.0, -1.0], [1.0 + _i26_np.cos(_i26_np.radians(75)), _i26_np.sin(_i26_np.radians(75))], [1.0 + _i26_np.cos(_i26_np.radians(-15)), -1.0 + _i26_np.sin(_i26_np.radians(-15))]])
    sources = _i26_np.array([0, 1, 0, 2])
    ends = _i26_np.array([1, 3, 2, 4])
    cost = _i26_np.array([1.0, 1.0, 1.2, 1.2])
    without = _i26_heading_path(sources, ends, cost, points, 0, [3, 4], max_turn_deg=90.0, turn_penalty_k=0.0)
    penalized = _i26_heading_path(sources, ends, cost, points, 0, [3, 4], max_turn_deg=90.0, turn_penalty_k=1.0)
    assert without.tolist() == [0, 1, 3]
    assert penalized.tolist() == [0, 2, 4]

def network_fixture(*, protected=False, unknown=False):
    shape = (7, 7)
    height = _i27_np.fromfunction(lambda row, column: 25.0 - row + abs(column - 3), shape)
    edges = _i27_np.array(((9, 16), (16, 23), (23, 24), (11, 18), (18, 25), (25, 24), (24, 31), (31, 38)), _i27_np.int64)
    nodes = _i27_np.unique(edges)
    receiver = _i27_np.full(height.size, -1, _i27_np.int64)
    receiver[edges[:, 0]] = edges[:, 1]
    active_order = _i27_np.array((38, 31, 24, 23, 25, 16, 18, 9, 11), _i27_np.int64)
    inactive_order = _i27_np.setdiff1d(_i27_np.arange(height.size), nodes)
    order = _i27_np.concatenate((inactive_order, active_order))
    valid = _i27_np.ones(shape, bool)
    protection = _i27_np.zeros(shape, bool)
    if protected:
        protection[2, 1] = True
    if unknown:
        valid[2, 1] = False
    native = _i27_np.column_stack((nodes % shape[1] * 30.0, height.ravel()[nodes], nodes // shape[1] * 30.0))
    arrays = {'source_height_m': height, 'valid_mask': valid, 'protected_mask': protection, 'open_boundary_mask': _i27_np.zeros(shape, bool), 'receiver': receiver, 'routing_order': order, 'selected_basin_mask': valid & ~protection, 'edge_cell_ids': edges, 'node_cell_ids': nodes, 'node_native_xyz_m': native, 'node_width_m': _i27_np.full(len(nodes), 3.0), 'node_depth_m': _i27_np.full(len(nodes), 1.0), 'node_representative_q_m3_s': _i27_np.full(len(nodes), 0.1), 'edge_requires_refinement': _i27_np.ones(len(edges), bool)}
    metadata = {'grid_shape': list(shape), 'spacing_m': 30.0, 'origin_m_xz': [0.0, 0.0], 'recipe': {'reference_q_m3_s': 0.1, 'reference_width_m': 3.0, 'reference_depth_m': 1.0, 'width_exponent': 0.4, 'depth_exponent': 0.3, 'minimum_width_m': 1.0, 'maximum_width_m': 20.0, 'minimum_depth_m': 0.1, 'maximum_depth_m': 4.0}}
    return {'arrays': arrays, 'metadata': metadata, 'identity_sha256': 'fixture-network'}
from terrain_pipeline.channel_geometry import NaturalGeometryRecipe as _i27_NaturalGeometryRecipe

class NaturalChannelGeometryTests(_i27_unittest.TestCase):

    def build(self, network, recipe=_i27_NaturalGeometryRecipe()):
        from terrain_pipeline.channel_geometry import build_natural_channel_geometry as _i27_build_natural_channel_geometry
        with _i27_patch('terrain_pipeline.channel_geometry._i45_validate_natural_river_network'):
            return _i27_build_natural_channel_geometry(network, recipe)

    def window(self, geometry, network):
        from terrain_pipeline.channel_geometry import evaluate_natural_channel_window as _i27_evaluate_natural_channel_window
        with _i27_patch('terrain_pipeline.channel_geometry._i45_validate_natural_river_network'):
            return _i27_evaluate_natural_channel_window(geometry, network, window_origin_m_xz=(30.0, 30.0), spacing_m=1.0, shape_zx=(121, 121))

    def test_shared_junction_bed_sections_and_downhill_edges(self):
        from terrain_pipeline.channel_geometry import validate_natural_channel_geometry as _i27_validate_natural_channel_geometry
        geometry = self.build(network_fixture())
        arrays = geometry['arrays']
        self.assertTrue(_i27_validate_natural_channel_geometry(geometry))
        endpoints = arrays['node_world_xyz_m'][_i27_np.searchsorted(arrays['node_cell_ids'], arrays['edge_cell_ids'])]
        _i27_np.testing.assert_array_equal(arrays['edge_centerline_xyz_m'], endpoints)
        _i27_np.testing.assert_array_equal(arrays['edge_sections_xyz_m'][:, (1, 4)], endpoints)
        self.assertTrue(_i27_np.all(endpoints[:, 0, 1] > endpoints[:, 1, 1]))
        self.assertTrue(geometry['metadata']['summary']['moved_nodes'] > 0)

    def test_centerline_changes_actual_cut_and_preserves_source(self):
        from terrain_pipeline.channel_geometry import validate_natural_channel_window as _i27_validate_natural_channel_window
        network = network_fixture()
        original = network['arrays']['source_height_m'].copy()
        smooth = self.build(network)
        straight = self.build(network, _i27_NaturalGeometryRecipe(smoothing_strength=0.0))
        smooth_window = self.window(smooth, network)
        straight_window = self.window(straight, network)
        self.assertGreater(_i27_np.count_nonzero(smooth_window['arrays']['actual_cut_m'] != straight_window['arrays']['actual_cut_m']), 0)
        _i27_np.testing.assert_array_equal(network['arrays']['source_height_m'], original)
        self.assertTrue(_i27_validate_natural_channel_window(smooth_window))
        self.assertGreater(smooth_window['metadata']['summary']['actual_cut_volume_m3'], 0.0)

    def test_protected_unknown_anchor_and_budget_diagnostics(self):
        for network in (network_fixture(protected=True), network_fixture(unknown=True)):
            geometry = self.build(network, _i27_NaturalGeometryRecipe(max_cut_m=0.5))
            self.assertTrue(geometry['metadata']['summary']['over_budget_nodes'] > 0)
            window = self.window(geometry, network)
            self.assertTrue(_i27_np.all(window['arrays']['actual_cut_m'][window['arrays']['protected_mask']] == 0))
            self.assertTrue(window['arrays']['protected_mask'][30, 16])
            self.assertEqual(window['arrays']['unknown_mask'][30, 16], not network['arrays']['valid_mask'][2, 1])
            self.assertTrue(window['metadata']['summary']['blocked_by_plan'])
            self.assertFalse(window['metadata']['publishable'])

    def test_externally_pinned_cold_load(self):
        from terrain_pipeline.common_infra import file_sha256 as _i27_file_sha256
        from terrain_pipeline.channel_geometry import load_natural_channel_geometry as _i27_load_natural_channel_geometry
        from terrain_pipeline.channel_geometry import load_natural_channel_window as _i27_load_natural_channel_window
        from terrain_pipeline.channel_geometry import save_natural_channel_geometry as _i27_save_natural_channel_geometry
        from terrain_pipeline.channel_geometry import save_natural_channel_window as _i27_save_natural_channel_window
        network = network_fixture()
        geometry = self.build(network)
        window = self.window(geometry, network)
        with _i27_tempfile.TemporaryDirectory() as directory:
            geometry_path = _i27_Path(directory) / 'geometry.npz'
            window_path = _i27_Path(directory) / 'window.npz'
            _i27_save_natural_channel_geometry(geometry_path, geometry)
            _i27_save_natural_channel_window(window_path, window)
            with _i27_patch('terrain_pipeline.channel_geometry.build_natural_channel_geometry', side_effect=AssertionError('cold load rebuilt geometry')):
                loaded_geometry = _i27_load_natural_channel_geometry(geometry_path, expected_sha256=_i27_file_sha256(geometry_path), expected_identity=geometry['identity_sha256'])
                loaded_window = _i27_load_natural_channel_window(window_path, expected_sha256=_i27_file_sha256(window_path), expected_identity=window['identity_sha256'])
            self.assertFalse(loaded_geometry['arrays']['node_world_xyz_m'].flags.writeable)
            self.assertFalse(loaded_window['arrays']['actual_cut_m'].flags.writeable)
            with self.assertRaises(ValueError):
                _i27_load_natural_channel_window(window_path, expected_sha256='0' * 64, expected_identity=window['identity_sha256'])

    def test_rehashed_bank_and_budget_tampering_rejected(self):
        from terrain_pipeline.common_infra import identity as _i27_bundle_identity
        from terrain_pipeline.channel_geometry import validate_natural_channel_geometry as _i27_validate_natural_channel_geometry
        from terrain_pipeline.channel_geometry import validate_natural_channel_window as _i27_validate_natural_channel_window
        network = network_fixture()
        geometry = self.build(network)
        altered = {'metadata': geometry['metadata'], 'arrays': {key: value.copy() for key, value in geometry['arrays'].items()}}
        altered['arrays']['edge_sections_xyz_m'][0, 0, 0] += 1.0
        altered['identity_sha256'] = _i27_bundle_identity(altered['arrays'], altered['metadata'])
        with self.assertRaises(ValueError):
            _i27_validate_natural_channel_geometry(altered)
        window = self.window(geometry, network)
        altered_window = {'metadata': window['metadata'], 'arrays': {key: value.copy() for key, value in window['arrays'].items()}}
        altered_window['arrays']['actual_cut_m'][1, 1] += 0.1
        altered_window['identity_sha256'] = _i27_bundle_identity(altered_window['arrays'], altered_window['metadata'])
        with self.assertRaises(ValueError):
            _i27_validate_natural_channel_window(altered_window)

    def test_real_core_network_contract(self):
        from terrain_pipeline.basin_topology import build_basin_hierarchy as _i27_build_basin_hierarchy
        from terrain_pipeline.basin_storage import make_td_source as _i27_make_td_source
        from terrain_pipeline.channel_geometry import build_natural_channel_geometry as _i27_build_natural_channel_geometry
        from terrain_pipeline.channel_geometry import evaluate_natural_channel_window as _i27_evaluate_natural_channel_window
        from terrain_pipeline.td_natural_river_network import build_natural_river_network
        height = _i27_np.fromfunction(lambda row, column: 25.0 - row + abs(column - 3), (7, 7))
        source = _i27_make_td_source(height, spacing_m=30.0)
        hierarchy = _i27_build_basin_hierarchy(source)
        network = build_natural_river_network(hierarchy, expected_hierarchy_identity=hierarchy['identity_sha256'])
        geometry = _i27_build_natural_channel_geometry(network)
        self.assertEqual(geometry['metadata']['network_identity_sha256'], network['identity_sha256'])
        self.assertEqual(geometry['metadata']['summary']['edge_count'], network['metadata']['summary']['edge_count'])
        window = _i27_evaluate_natural_channel_window(geometry, network, window_origin_m_xz=(30.0, 30.0), spacing_m=1.0, shape_zx=(121, 121))
        self.assertGreater(window['metadata']['summary']['actual_cut_volume_m3'], 0.0)

def _test_td_source_conforming_banks_fixture():
    from terrain_pipeline.common_infra import identity as _i28_identity
    from terrain_pipeline.td_fine_bed_raster import build_fine_bed_raster as _i28_build_fine_bed_raster
    from terrain_pipeline.td_fine_bed_shards import build_fine_bed_shards as _i28_build_fine_bed_shards
    rows, columns = _i28_np.indices((5, 5))
    arrays = {'height_m': 10.0 - 0.5 * rows * columns, 'valid_mask': _i28_np.ones((5, 5), bool), 'protected_mask': _i28_np.zeros((5, 5), bool), 'open_boundary_mask': _i28_np.zeros((5, 5), bool), 'cell_owner': _i28_np.zeros((5, 5), _i28_np.int64), 'contribution_owner': _i28_np.zeros((5, 5), _i28_np.int64), 'node_unknown_contact': _i28_np.zeros(1, bool)}
    metadata = {'origin_m_xz': [0.0, 0.0], 'spacing_m': 1.0, 'source_identity_sha256': 'a' * 64}
    hierarchy = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i28_identity(arrays, metadata)}

    def profile(z_m, locations, cuts):
        return [[x_m, 10.0 - 0.5 * x_m * z_m - cut, z_m] for x_m, cut in zip(locations, cuts)]
    four = [0.5, 0.75, 1.25, 1.5]
    profiles = [profile(z_m, four, [0.0, 0.01, 0.01, 0.0]) for z_m in (0.0, 0.5, 1.5)]
    vertices = [point for row in profiles for point in row]
    triangles = []
    for strip in range(2):
        for column in range(3):
            first = strip * 4 + column
            triangles.extend([[first, first + 1, first + 4], [first + 1, first + 5, first + 4]])
    sections = {'schema': 'td-watershed-sections-v1', 'identity_sha256': 'b' * 64, 'source_identity_sha256': 'a' * 64, 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'selected_leaf_ids': [0], 'ordinary_identity_sha256': 'e' * 64, 'node_sections': [{'node_id': node, 'width_m': 0.5, 'representative_q_m3_s': 0.01} for node in ('upstream', 'port', 'anchor')], 'edge_sections': [{'arc_id': 'legacy', 'node_ids': ['upstream', 'port'], 'cross_section_xyz_m': profiles[:2], 'triangle_indices': list(range(6))}, {'arc_id': 'accepted', 'node_ids': ['port', 'anchor'], 'cross_section_xyz_m': profiles[1:], 'triangle_indices': list(range(6, 12))}], 'mesh': {'vertices_xyz_m': vertices, 'triangles': triangles, 'triangle_arc_ids': ['legacy'] * 6 + ['accepted'] * 6}}
    five = [0.5, 0.75, 1.0, 1.25, 1.5]
    taper_vertices = [point for z_m, depth in ((1.5, 0.01), (2.0, 0.005), (2.5, 0.0)) for point in profile(z_m, five, [0.0, depth, depth, depth, 0.0])]
    taper_triangles = []
    for strip in range(2):
        for column in range(4):
            first = strip * 5 + column
            taper_triangles.extend([[first, first + 1, first + 5], [first + 1, first + 6, first + 5]])
    transitions = {'identity_sha256': 'c' * 64, 'paths_identity_sha256': 'd' * 64, 'entries': [{'entry_id': 'entry', 'status': 'candidate', 'accepted_port_arc_id': 'accepted', 'accepted_port_xyz_m': profiles[-1], 'vertices_xyz_m': taper_vertices, 'triangles': taper_triangles, 'width_m': 0.5}, {'entry_id': 'refused', 'status': 'refused', 'rejection_reasons': ['missing_or_ambiguous_accepted_port']}]}
    paths = {'identity_sha256': 'd' * 64, 'nodes': [{'node_id': node, 'kinds': ['engineering'] if node == 'wet' else ['land_channel']} for node in ('anchor', 'middle', 'wet', 'isolated')], 'arcs': [{'arc_id': 'entry', 'node_ids': ['anchor', 'middle', 'wet']}, {'arc_id': 'refused', 'node_ids': ['isolated']}, {'arc_id': 'engineering_singleton', 'node_ids': ['wet']}]}
    base = _i28_build_fine_bed_raster(hierarchy, sections, transitions, fine_spacing_m=0.125, tile_cells=8, scope='lake-entry-neighborhood')
    shards = _i28_build_fine_bed_shards(base, hierarchy)
    readiness = {'requests': [{'entry_id': 'entry', 'status': 'pending', 'cell_refusals': {'fill_without_material': 1}}, {'entry_id': 'refused', 'status': 'parent_refused'}]}
    return (base, shards, hierarchy, sections, transitions, paths, readiness)

class SourceConformingBankTests(_i28_unittest.TestCase):

    def test_full_component_T_port_nonfill_signed_effects_and_roundtrip(self):
        from terrain_pipeline.td_fine_bed_shards import iter_merged_cells as _i28_iter_merged_cells
        from terrain_pipeline.channel_geometry import build_source_conforming_banks as _i28_build_source_conforming_banks
        from terrain_pipeline.channel_geometry import load_source_conforming_banks as _i28_load_source_conforming_banks
        from terrain_pipeline.channel_geometry import save_source_conforming_banks as _i28_save_source_conforming_banks
        from terrain_pipeline.channel_geometry import validate_source_conforming_banks as _i28_validate_source_conforming_banks
        arguments = _test_td_source_conforming_banks_fixture()
        base, shards, hierarchy, sections, transitions, paths, readiness = arguments
        original = _i28_deepcopy(base)
        package = _i28_build_source_conforming_banks(*arguments)
        self.assertGreater(package['manifest']['summary']['original_fill_refused_cells'], 0)
        self.assertEqual(package['manifest']['summary']['candidate_components'], 1, package['manifest']['components'])
        self.assertEqual(base, original)
        self.assertGreater(package['manifest']['summary']['replace_cells'], 0)
        self.assertEqual(package['manifest']['summary']['center_source_resamples'], 0)
        self.assertEqual(package['manifest']['summary']['affected_triangles'], len(base['triangles']))
        port = [proof for chunk in package['proofs'] for proof in chunk['records'] if proof['kind'] == 'port_function_proof'][0]
        self.assertEqual(port['status'], 'candidate', port)
        self.assertEqual(len(port['segment_ids']), 4)
        parent_cells = {key: cell for key, cell, owner in _i28_iter_merged_cells(base, shards['shards'])}
        effects = [effect for chunk in package['effects'] for effect in chunk['records']]
        self.assertEqual(len(effects), len({tuple(effect['global_key_row_column']) for effect in effects}))
        for effect in effects:
            after = effect['cell']
            self.assertEqual(after['source_sample'], parent_cells[tuple(effect['global_key_row_column'])]['source_sample'])
            self.assertLessEqual(after['derived_bed_m'], after['source_sample']['height_m'])
        self.assertAlmostEqual(sum((effect['cut_delta_m3'] for effect in effects)), package['manifest']['material_ledger_delta']['cut_rock_m3'])
        self.assertFalse(package['manifest']['hydraulic_ready'])
        self.assertEqual(package['queue']['parent_status_counts'], {'pending': 1, 'parent_refused': 1})
        self.assertTrue(package['queue']['requests'][0]['ordinary_flow_references'])
        queued = {row['entry_id']: row for row in package['queue']['requests']}
        connected = queued['entry']
        walk = connected['actual_support_path_to_engineering_node_ids']
        self.assertEqual(walk, ['anchor', 'middle', 'wet'])
        self.assertEqual(connected['actual_support_path_to_engineering_arc_ids'], ['entry', 'entry'])
        actual_arcs = {arc['arc_id']: arc for arc in paths['arcs']}
        self.assertEqual(len(walk), len(connected['actual_support_path_to_engineering_arc_ids']) + 1)
        for first, second, arc_id in zip(walk, walk[1:], connected['actual_support_path_to_engineering_arc_ids']):
            ordered_nodes = actual_arcs[arc_id]['node_ids']
            self.assertTrue(any(((first, second) in ((start, end), (end, start)) for start, end in zip(ordered_nodes, ordered_nodes[1:]))))
        self.assertIn('engineering', next((node for node in paths['nodes'] if node['node_id'] == walk[-1]))['kinds'])
        self.assertTrue(connected['undirected_support_reaches_engineering'])
        self.assertEqual(queued['refused']['actual_node_ids'], ['isolated'])
        self.assertEqual(queued['refused']['actual_support_path_to_engineering_node_ids'], [])
        self.assertEqual(queued['refused']['actual_support_path_to_engineering_arc_ids'], [])
        self.assertFalse(queued['refused']['undirected_support_reaches_engineering'])
        self.assertTrue(all((not row['directed_hydraulic_connection_proved'] for row in queued.values())))
        _i28_validate_source_conforming_banks(package, base=base, shard_package=shards, hierarchy=hierarchy)
        with _i28_tempfile.TemporaryDirectory() as directory:
            target = _i28_Path(directory) / 'candidate'
            _i28_save_source_conforming_banks(package, target)
            loaded = _i28_load_source_conforming_banks(target, expected_manifest_sha256=_i28_hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest(), expected_manifest_identity=package['manifest']['identity_sha256'], base=base, shard_package=shards, hierarchy=hierarchy)
            self.assertEqual(loaded, package)

    def test_quadratic_source_proof_and_strict_vertex_shared_knot_budget_refusal(self):
        from terrain_pipeline.td_fine_bed_raster import _context as _i28__context
        from terrain_pipeline.channel_geometry import _proof as _i28__proof
        from terrain_pipeline.channel_geometry import _segments as _i28__segments
        from terrain_pipeline.channel_geometry import _line_key as _i28__line_key
        from terrain_pipeline.channel_geometry import _function as _i28__function
        from terrain_pipeline.channel_geometry import build_source_conforming_banks as _i28_build_source_conforming_banks
        arguments = _test_td_source_conforming_banks_fixture()
        context = _i28__context(arguments[2], [0])
        endpoints = [[0.25, 10.0 - 0.5 * 0.25 ** 2 - 1.0, 0.25], [1.75, 10.0 - 0.5 * 1.75 ** 2 - 1.0, 1.75]]
        edges = [{'triangle_id': 'first', 'edge_index': 0, 'points_xyz_m': endpoints}, {'triangle_id': 'second', 'edge_index': 2, 'points_xyz_m': endpoints[::-1]}]
        groups = {_i28__line_key(_i28_np.asarray(endpoints)[:, [0, 2]]): edges}
        segments = _i28__segments(groups, context)
        self.assertEqual(len(segments), 2)
        proofs = [_i28__proof(segment, context) for segment in segments]
        self.assertTrue(all((proof['status'] == 'candidate' for proof in proofs)))
        self.assertTrue(all((abs(proof['source']['source_coefficients_m_t012'][2]) > 0 for proof in proofs)))
        for proof in proofs:
            start, end = (_i28_np.asarray(proof['start_xz_m']), _i28_np.asarray(proof['end_xz_m']))
            point = 0.7 * start + 0.3 * end
            polynomial = proof['source']['source_coefficients_m_t012']
            self.assertAlmostEqual(polynomial[0] + 0.3 * polynomial[1] + 0.3 ** 2 * polynomial[2], 10.0 - 0.5 * point[0] * point[1])
        mismatched = _i28_deepcopy(segments[0])
        mismatched['depth_support_knots'][0]['original_vertex_refs'][1]['xyz_m'] = list(mismatched['depth_support_knots'][0]['original_vertex_refs'][1]['xyz_m'])
        mismatched['depth_support_knots'][0]['original_vertex_refs'][1]['xyz_m'][1] += 0.001
        self.assertEqual(_i28__proof(mismatched, context)['status'], 'refused')
        with self.assertRaises(MemoryError):
            _i28_build_source_conforming_banks(*arguments, max_cells=1)
        with self.assertRaises(ValueError):
            _i28_build_source_conforming_banks(*arguments, max_shard_bytes=MAX_INVALID_BYTES)
        modified = list(_i28_deepcopy(arguments))
        modified[0]['triangles'][0]['vertices_xyz_m'][0][1] += 1.0
        with self.assertRaises(ValueError):
            _i28_build_source_conforming_banks(*modified)
        rejected = _i28__function(modified[0]['triangles'][0], [], context, arguments[0]['parameters'])
        self.assertEqual(rejected['status'], 'refused')
        self.assertIn('original_vertex_fill_or_unknown', rejected['rejection_reasons'])
MAX_INVALID_BYTES = 64 * 1024 ** 2 + 1

def context_for(height):
    from terrain_pipeline.common_infra import identity as _i29_identity
    from terrain_pipeline.td_fine_bed_raster import _context as _i29__context
    arrays = {'height_m': _i29_np.asarray(height, float), 'valid_mask': _i29_np.ones(_i29_np.shape(height), bool), 'protected_mask': _i29_np.zeros(_i29_np.shape(height), bool), 'open_boundary_mask': _i29_np.zeros(_i29_np.shape(height), bool), 'cell_owner': _i29_np.zeros(_i29_np.shape(height), _i29_np.int64), 'contribution_owner': _i29_np.zeros(_i29_np.shape(height), _i29_np.int64), 'node_unknown_contact': _i29_np.zeros(1, bool)}
    metadata = {'origin_m_xz': [0.0, 0.0], 'spacing_m': 1.0, 'source_identity_sha256': 'a' * 64}
    hierarchy = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i29_identity(arrays, metadata)}
    return _i29__context(hierarchy, [0])

def segments_for(triangles, context, legacy_edge):
    groups = {}
    for triangle in triangles:
        for edge_index in range(3):
            edge = _i29_v2._edge_record(triangle, edge_index)
            key = _i29_v2._line_key(_i29_np.asarray(edge['points_xyz_m'])[:, [0, 2]])
            groups.setdefault(key, []).append(edge)
    key = _i29_v2._line_key(_i29_np.asarray(legacy_edge['points_xyz_m'])[:, [0, 2]])
    groups[key].append(legacy_edge)
    for number, edges in enumerate(groups.values()):
        if len(edges) == 1:
            edges.append({**edges[0], 'triangle_id': 'legacy06:outer' + str(number)})
    return _i29_v2._segments(groups, context)

class SourceConformingBanksV3Tests(_i29_unittest.TestCase):

    def test_whole_native_linear_matching_and_adjacent_fan_vertex_unification(self):
        context = context_for(_i29_np.tile([10.0, 11.0, 10.0, 12.0, 12.0], (5, 1)))
        parameters = {'max_cut_m': 5.0, 'conflict_tolerance_m': 1e-08}
        triangles = [{'triangle_id': '06:0', 'vertices_xyz_m': [[0.25, 10.0, 0.25], [2.75, 10.0, 0.25], [0.25, 9.0, 2.25]]}, {'triangle_id': '06:1', 'vertices_xyz_m': [[0.25, 9.0, 2.25], [2.75, 10.0, 0.25], [2.75, 9.0, 2.25]]}]
        legacy = {'triangle_id': 'legacy06:2', 'edge_index': 0, 'points_xyz_m': triangles[0]['vertices_xyz_m'][:2]}
        segments = segments_for(triangles, context, legacy)
        old = [_i29_v2._proof(segment, context) for segment in segments]
        self.assertTrue(any(('unchanged_neighbor_quadratic_function_mismatch' in proof['rejection_reasons'] for proof in old)))
        proofs = _i29_v3.build_edge_proofs(segments, context, parameters)
        boundary = [proof for proof in proofs if any((side['triangle_id'].startswith('legacy06:') for side in proof['sides']))]
        for proof in boundary:
            self.assertEqual(proof['status'], 'candidate', proof['rejection_reasons'])
            source = proof['source']['source_coefficients_m_t012']
            depth = proof['depth_coefficients_m_t01']
            for neighbor in proof['v3proof']['unchanged_neighbor_polynomials']:
                bed = neighbor['bed_coefficients_m_t012']
                self.assertLessEqual(max((abs(value) for value in (source[0] - depth[0] - bed[0], source[1] - depth[1] - bed[1], source[2]))), 1e-09)
        functions = []
        for triangle in triangles:
            relevant = [proof for proof in proofs if any((side['triangle_id'] == triangle['triangle_id'] for side in proof['sides']))]
            function = _i29_v3.build_triangle_function(triangle, relevant, context, parameters)
            self.assertEqual(function['status'], 'candidate', function['rejection_reasons'])
            functions.append(function)
            vertices = {}
            for fan in function['fans']:
                for point, depth in zip(fan['vertices_xz_m'], fan['depth_at_vertices_m']):
                    key = tuple(point)
                    if key in vertices:
                        self.assertAlmostEqual(vertices[key], depth, places=9)
                    vertices[key] = depth
            if triangle['triangle_id'] == '06:0':
                self.assertAlmostEqual(vertices[1.0, 0.25], 1.0)
        for point in ([1.0, 0.25], [1.5, 1.25]):
            for function in functions:
                if point == [1.0, 0.25] and function['triangle_id'] != '06:0':
                    continue
                source = _i29_v2._source_sample(context, *point)['height_m']
                value = _i29_v3.td_source_conforming_banks_mechanism_3_evaluate_bank_function(function, *point, source)
                self.assertGreaterEqual(value['cut_depth_m'], 0.0)
        self.assertEqual(_i29_v2.TD_SOURCE_CONFORMING_BANKS_SCHEMA, 'td-source-conforming-banks-v2')

    def test_quadratic_or_negative_depth_legacy_boundary_is_refused(self):
        for quadratic in (True, False):
            if quadratic:
                rows, columns = _i29_np.indices((4, 4))
                context = context_for(10.0 - 0.5 * rows * columns)
                endpoints = [[0.25, 7.0, 0.25], [1.75, 7.0, 1.75]]
                reason = 'legacy_source_quadratic_requires_joint_version'
            else:
                context = context_for(_i29_np.tile([10.0, 8.0, 10.0, 10.0], (4, 1)))
                endpoints = [[0.25, 9.0, 0.25], [1.75, 9.0, 0.25]]
                reason = 'legacy_matching_negative_depth'
            edges = [{'triangle_id': name, 'edge_index': 0, 'points_xyz_m': endpoints} for name in ('06:0', 'legacy06:1')]
            key = _i29_v2._line_key(_i29_np.asarray(endpoints)[:, [0, 2]])
            proofs = _i29_v3.build_edge_proofs(_i29_v2._segments({key: edges}, context), context, {'max_cut_m': 5.0, 'conflict_tolerance_m': 1e-08})
            self.assertTrue(all((proof['status'] == 'refused' for proof in proofs)))
            self.assertTrue(all((reason in proof['rejection_reasons'] for proof in proofs)))
            self.assertTrue(all((proof['depth_coefficients_m_t01'] is None for proof in proofs)))

def _test_td_watershed_inspection_fixture():
    nodes = [{'node_id': 'cell:0', 'cell_id': 0, 'leaf_id': 1, 'xyz_m': [0.0, 2.0, 0.0]}, {'node_id': 'cell:1', 'cell_id': 1, 'leaf_id': 1, 'xyz_m': [1.0, 1.0, 0.0]}]
    arc = {'arc_id': 'receiver:0:1', 'kind': 'land_channel', 'channel_candidate': True, 'node_ids': [node['node_id'] for node in nodes], 'cell_ids': [0, 1], 'xyz_m': [node['xyz_m'] for node in nodes]}
    paths = {'schema': 'td-watershed-paths-v1', 'grid_shape': [1, 2], 'origin_m_xz': [0.0, 0.0], 'spacing_m': 1.0, 'nodes': nodes, 'arcs': [arc]}
    mesh = {'vertices_xyz_m': [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 1.0]], 'triangles': [[0, 1, 2]], 'triangle_arc_ids': [arc['arc_id']], 'node_vertex_indices': {'cell:0': [0]}}
    sections = {'schema': 'td-watershed-sections-v1', 'mesh': mesh, 'node_sections': [{'node_id': node['node_id'], 'source_xyz_m': node['xyz_m'], 'cross_section_xyz_m': [mesh['vertices_xyz_m'][0]]} for node in nodes], 'support_arcs': [], 'edge_sections': [{'arc_id': arc['arc_id'], 'node_ids': arc['node_ids'], 'triangle_indices': [0]}], 'reach_diagnostics': [{'arc_id': arc['arc_id'], 'status': 'geometry_candidate', 'rejection_reasons': []}]}
    arrays = {'height_m': _i30_np.array([[2.0, 1.0]]), 'valid_mask': _i30_np.ones((1, 2), dtype=bool), 'receiver': _i30_np.array([1, -1]), 'contribution_owner': _i30_np.array([[1, 1]])}
    return (paths, sections, arrays, {'origin_m_xz': [0.0, 0.0], 'spacing_m': 1.0})

class WatershedInspectionTest(_i30_unittest.TestCase):

    def test_illegal_graph_is_rejected(self):
        for change in ('missing_node', 'duplicate_node', 'fake_height', 'wrong_receiver', 'support_as_water'):
            with self.subTest(change=change):
                paths, sections, arrays, metadata = _test_td_watershed_inspection_fixture()
                if change == 'missing_node':
                    paths['arcs'][0]['node_ids'][1] = 'absent'
                elif change == 'duplicate_node':
                    paths['nodes'].append(_i30_deepcopy(paths['nodes'][0]))
                elif change == 'fake_height':
                    paths['nodes'][0]['xyz_m'][1] = 99.0
                elif change == 'wrong_receiver':
                    arrays['receiver'][0] = -1
                else:
                    paths['arcs'][0]['kind'] = 'lake_support'
                with self.assertRaises(ValueError):
                    _i30_exporter.validate_geometry(paths, sections, arrays, metadata)

    def test_saved_mesh_references_and_no_fabrication(self):
        paths, sections, arrays, metadata = _test_td_watershed_inspection_fixture()
        _i30_exporter.validate_geometry(paths, sections, arrays, metadata)
        before = _i30_deepcopy(sections)
        review = {'layers': {'saved_bed_mesh': sections['mesh']}, 'pins': {'sections': {}}, 'limitations': []}
        artifact = _i30_exporter.mesh_caseartifact(review)
        self.assertEqual(artifact['mesh']['vertices'], sections['mesh']['vertices_xyz_m'])
        self.assertEqual(artifact['mesh']['triangles'], sections['mesh']['triangles'])
        self.assertIsNone(artifact['mesh']['water'])
        self.assertEqual(sections, before)
        for change in ('vertex', 'owner', 'edge_index', 'duplicate_triangle'):
            with self.subTest(change=change):
                invalid = _i30_deepcopy(sections)
                if change == 'vertex':
                    invalid['mesh']['triangles'][0][2] = 99
                elif change == 'owner':
                    invalid['mesh']['triangle_arc_ids'][0] = 'invented'
                elif change == 'edge_index':
                    invalid['edge_sections'][0]['triangle_indices'] = [99]
                else:
                    invalid['edge_sections'][0]['triangle_indices'] = [0, 0]
                with self.assertRaises(ValueError):
                    _i30_exporter.validate_geometry(paths, invalid, arrays, metadata)
        source = _i30_inspect.getsource(_i30_exporter)
        self.assertNotIn('terrain_pipeline', source)
        self.assertNotIn('scipy', source)

def _fixture():
    nodes = []
    sections = []
    for cell, xyz in ((0, [0.0, 10.0, 0.0]), (1, [10.0, 9.0, 0.0]), (2, [0.0, 10.0, 10.0]), (3, [10.0, 9.0, 10.0])):
        node_id = f'cell:{cell}'
        nodes.append({'node_id': node_id, 'cell_id': cell, 'xyz_m': xyz, 'kinds': ['confluence'] if cell == 1 else [], 'leaf_id': 0})
        cross = [[xyz[0] - 2.0, xyz[1], xyz[2] - 2.0], [xyz[0] - 1.0, xyz[1] - 1.0, xyz[2] - 1.0], [xyz[0] + 1.0, xyz[1] - 1.0, xyz[2] + 1.0], [xyz[0] + 2.0, xyz[1], xyz[2] + 2.0]]
        sections.append({'node_id': node_id, 'source_xyz_m': xyz, 'bed_m': xyz[1] - (0.0 if cell == 0 else 0.5), 'width_m': 4.0, 'depth_m': 0.0 if cell == 0 else 0.5, 'cross_section_xyz_m': cross, 'anchor': cell == 0, 'junction': cell == 1, 'rejection_reasons': ['anchor_cut_conflict'] if cell == 0 else ['needs_junction_patch']})
    arcs = [{'arc_id': 'a0', 'kind': 'land_channel', 'node_ids': ['cell:0', 'cell:1'], 'cell_ids': [0, 1]}, {'arc_id': 'a1', 'kind': 'land_channel', 'node_ids': ['cell:2', 'cell:1'], 'cell_ids': [2, 1]}, {'arc_id': 'a2', 'kind': 'land_channel', 'node_ids': ['cell:3', 'cell:1'], 'cell_ids': [3, 1]}]
    paths = {'schema': 'td-watershed-paths-v1', 'source_identity_sha256': 'source', 'hierarchy_identity_sha256': 'hierarchy', 'topology_identity_sha256': 'topology', 'ordinary_identity_sha256': 'ordinary', 'identity_sha256': 'paths', 'nodes': nodes, 'arcs': arcs}
    record = {'schema': 'td-watershed-sections-v1', 'identity_sha256': 'sections', 'node_sections': sections}
    return (paths, record)

class WatershedInterfacePatchTests(_i31_unittest.TestCase):

    def test_build_has_explicit_candidates_and_rejections(self):
        from terrain_pipeline.channel_geometry import build_watershed_interface_patches as _i31_build_watershed_interface_patches
        from terrain_pipeline.channel_geometry import validate_watershed_interface_patches as _i31_validate_watershed_interface_patches
        paths, sections = _fixture()
        result = _i31_build_watershed_interface_patches(paths, sections)
        _i31_validate_watershed_interface_patches(result)
        self.assertTrue(result['patches'])
        self.assertTrue(all((item['parametric_only'] for item in result['patches'])))
        self.assertEqual(result['bed_changed'], False)

    def test_tampered_geometry_is_rejected(self):
        from terrain_pipeline.channel_geometry import build_watershed_interface_patches as _i31_build_watershed_interface_patches
        from terrain_pipeline.channel_geometry import validate_watershed_interface_patches as _i31_validate_watershed_interface_patches
        paths, sections = _fixture()
        result = _i31_build_watershed_interface_patches(paths, sections)
        result['patches'][0]['endpoint_xyz_m'][0][0] += 1.0
        with self.assertRaises(ValueError):
            _i31_validate_watershed_interface_patches(result)

    def test_save_load_hash(self):
        from terrain_pipeline.channel_geometry import build_watershed_interface_patches as _i31_build_watershed_interface_patches
        from terrain_pipeline.channel_geometry import load_watershed_interface_patches as _i31_load_watershed_interface_patches
        from terrain_pipeline.channel_geometry import save_watershed_interface_patches as _i31_save_watershed_interface_patches
        paths, sections = _fixture()
        result = _i31_build_watershed_interface_patches(paths, sections)
        with _i31_tempfile.TemporaryDirectory() as directory:
            target = _i31_Path(directory) / 'patches.json'
            _i31_save_watershed_interface_patches(result, target)
            loaded = _i31_load_watershed_interface_patches(target, expected_identity=result['identity_sha256'])
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])

def _test_td_watershed_paths_fixture():
    from terrain_pipeline.common_infra import identity as _i32_identity
    from terrain_pipeline.basin_topology import build_basin_hierarchy as _i32_build_basin_hierarchy
    from terrain_pipeline.basin_storage import _boundary_faces as _i32__boundary_faces
    from terrain_pipeline.basin_storage import _physical_faces as _i32__physical_faces
    from terrain_pipeline.basin_storage import make_td_source as _i32_make_td_source
    from terrain_pipeline.basin_topology import build_outlet_forest as _i32_build_outlet_forest
    from terrain_pipeline.basin_topology import trace_engineering_outlet as _i32_trace_engineering_outlet
    from terrain_pipeline.basin_topology import trace_spill_connection as _i32_trace_spill_connection
    from terrain_pipeline.basin_topology import digest as _i32_digest
    from terrain_pipeline.basin_topology import sampled_stage as _i32_sampled_stage
    from terrain_pipeline.channel_geometry import TD_WATERSHED_PATHS_FLAGS as _i32_FLAGS
    bed = _i32_np.array([[2.0, 3.0, 6.0, 4.0, 3.0, 1.0]])
    opened = _i32_np.array([[False, False, False, False, False, True]])
    hierarchy = _i32_build_basin_hierarchy(_i32_make_td_source(bed, spacing_m=2, origin_m_xz=(10, 20), open_boundary_mask=opened))
    owners = hierarchy['arrays']['contribution_owner'].ravel()
    leaves = _i32_np.unique(owners).tolist()
    lookup = {leaf: position for position, leaf in enumerate(leaves)}
    source, root = (int(owners[0]), int(owners[-1]))
    face = _i32__physical_faces(hierarchy, leaves, lookup)[0]
    boundary = _i32__boundary_faces(hierarchy, leaves, lookup)[0]
    direction = 1 if face['leaf_ids'][0] == source else -1
    stages = _i32_np.zeros((289, 2))
    stages[:, lookup[source]] = 6.0
    stages[:, lookup[root]] = 1.0
    stages[200, lookup[root]] = 2.0
    forward, reverse = (_i32_np.zeros((288, 1)), _i32_np.zeros((288, 1)))
    (forward if direction == 1 else reverse)[0, 0] = 1.0
    engineering = _i32_np.zeros((288, 1))
    engineering[0, 0] = 1.0
    metadata = {'schema': 'td-basin-runoff-exchange-v1', 'steps': 288, 'duration_s': 86400.0, 'timestep_s': 300.0, 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'source_identity_sha256': hierarchy['metadata']['source_identity_sha256'], 'topology_identity_sha256': 'a' * 64, 'hydraulic_ready': False, 'transient_converged': False, 'natural_outlet_verified': False, 'publishable': False}
    event_arrays = {'stage_m': stages, 'face_forward_m3': forward, 'face_reverse_m3': reverse, 'engineering_boundary_outflow_m3': engineering}
    ordinary = {'arrays': event_arrays, 'metadata': metadata, 'identity_sha256': _i32_identity(event_arrays, metadata)}
    source_sample = _i32_sampled_stage(ordinary, lookup[source], direction * (forward[:, 0] - reverse[:, 0]))
    root_sample = _i32_sampled_stage(ordinary, lookup[root], engineering[:, 0])
    edge = {**face, 'routing_eligible': True, 'source_leaf_id': source, 'receiver_leaf_id': root, 'ordinary': {'direction': direction, 'net_m3': float(direction)}, 'sampled_source_stage': source_sample, 'geometry': _i32_trace_spill_connection(hierarchy, face, source, root, source_stage_m=6.0)}
    outlet = {**boundary, 'routing_eligible': True, 'outflow_m3': 1.0, 'sampled_source_stage': root_sample, 'geometry': _i32_trace_engineering_outlet(hierarchy, boundary, source_stage_m=1.0)}
    nodes = []
    for leaf in leaves:
        cells = _i32_np.flatnonzero(owners == leaf)
        terminal = int(cells[hierarchy['arrays']['receiver'][cells] < 0][0])
        nodes.append({'leaf_id': leaf, 'terminal_cell_id': terminal, 'exclusive_area_m2': len(cells) * 4.0, 'blocked_reasons': [], 'ordinary_stage_max_m': float(stages[:, lookup[leaf]].max())})
    forest = _i32_build_outlet_forest(leaves, [node['exclusive_area_m2'] for node in nodes], [{'face_id': face['face_id'], 'source_leaf_id': source, 'receiver_leaf_id': root, 'net_m3': 1.0}], [{'leaf_id': root, 'cell_id': boundary['cell_id'], 'outflow_m3': 1.0}])
    graph = {'schema': 'td-lake-spill-graph-v1', 'nodes': nodes, 'edges': [edge], 'outlets': [outlet], 'routing_forest': forest, 'source_identity_sha256': metadata['source_identity_sha256'], 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'topology_identity_sha256': metadata['topology_identity_sha256'], 'event_identity_sha256': {'ordinary': ordinary['identity_sha256']}, **{name: False for name in _i32_FLAGS}}
    graph['identity_sha256'] = _i32_digest(graph)
    return (graph, hierarchy, ordinary)

class WatershedPathsTests(_i32_unittest.TestCase):

    def test_shared_continuous_typed_receiver_local_area_and_cold_roundtrip(self):
        from terrain_pipeline.channel_geometry import TD_WATERSHED_PATHS_FLAGS as _i32_FLAGS
        from terrain_pipeline.channel_geometry import build_watershed_paths as _i32_build_watershed_paths
        from terrain_pipeline.channel_geometry import load_watershed_paths as _i32_load_watershed_paths
        from terrain_pipeline.channel_geometry import save_watershed_paths as _i32_save_watershed_paths
        from terrain_pipeline.channel_geometry import validate_watershed_paths as _i32_validate_watershed_paths
        graph, hierarchy, ordinary = _test_td_watershed_paths_fixture()
        original_graph = _i32_deepcopy(graph)
        original_bed = hierarchy['arrays']['height_m'].copy()
        paths = _i32_build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.0)
        self.assertEqual(paths, _i32_build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.0))
        self.assertTrue(_i32_validate_watershed_paths(paths, graph, hierarchy, ordinary))
        nodes = {node['node_id']: node for node in paths['nodes']}
        self.assertEqual(len(nodes), len(paths['nodes']))
        land = [arc for arc in paths['arcs'] if arc['channel_candidate']]
        self.assertEqual([arc['cell_ids'] for arc in land], [[3, 4]])
        self.assertEqual(land[0]['local_upstream_area_m2'], 4.0)
        self.assertEqual(nodes['cell:4']['local_upstream_area_m2'], 8.0)
        self.assertEqual(nodes['cell:5']['local_upstream_area_m2'], 12.0)
        self.assertIn('lake_entry', nodes['cell:5']['kinds'])
        self.assertIn('lake_entry', nodes['cell:4']['kinds'])
        self.assertIn('lake_interface', nodes['cell:4']['lake_interfaces'])
        self.assertIn('engineering', nodes['cell:5']['lake_interfaces'])
        self.assertIn('spill', nodes['cell:3']['lake_interfaces'])
        for arc in paths['arcs']:
            if arc['kind'] != 'land_channel':
                self.assertFalse(arc['channel_candidate'])
            for node_id, xyz in zip(arc['node_ids'], arc['xyz_m']):
                self.assertEqual(xyz, nodes[node_id]['xyz_m'])
        wet = next((arc for arc in paths['arcs'] if arc['kind'] == 'source_lake_approach'))
        self.assertEqual(wet['cell_ids'], [0, 1, 2])
        self.assertEqual(wet['source_geometry']['source_stage_m'], 6.0)
        self.assertTrue(wet['source_geometry']['all_samples_stage_covered'])
        entry = next((arc for arc in paths['arcs'] if arc['arc_id'] == 'receiver:4:5'))
        self.assertEqual(entry['kind'], 'lake_entry_support')
        self.assertEqual(entry['lake_interface'], {'land_node_id': 'cell:4', 'wet_node_id': 'cell:5', 'support_arc_id': 'receiver:4:5'})
        self.assertTrue(all((paths[name] is False for name in _i32_FLAGS)))
        self.assertEqual(graph, original_graph)
        _i32_np.testing.assert_array_equal(hierarchy['arrays']['height_m'], original_bed)
        _i32_json.dumps(paths, allow_nan=False)
        with _i32_tempfile.TemporaryDirectory() as directory:
            path = _i32_Path(directory) / 'paths.json'
            _i32_save_watershed_paths(paths, path)
            loaded = _i32_load_watershed_paths(path, expected_sha256=_i32_hashlib.sha256(path.read_bytes()).hexdigest(), expected_identity=paths['identity_sha256'], graph=graph, hierarchy=hierarchy, ordinary=ordinary)
            self.assertEqual(loaded, paths)
            with self.assertRaises(FileExistsError):
                _i32_save_watershed_paths(paths, path)

    def test_stage_identity_geometry_protection_and_budget_rejections(self):
        from terrain_pipeline.common_infra import identity as _i32_identity
        from terrain_pipeline.basin_topology import digest as _i32_digest
        from terrain_pipeline.channel_geometry import build_watershed_paths as _i32_build_watershed_paths
        from terrain_pipeline.channel_geometry import validate_watershed_paths as _i32_validate_watershed_paths
        graph, hierarchy, ordinary = _test_td_watershed_paths_fixture()
        paths = _i32_build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.0)
        for case in ('source', 'parent', 'stage', 'geometry', 'unknown', 'protected', 'nan', 'flags'):
            with self.subTest(case=case):
                candidate_graph, candidate_hierarchy, candidate_event = _i32_deepcopy((graph, hierarchy, ordinary))
                if case == 'source':
                    candidate_graph['source_identity_sha256'] = 'b' * 64
                elif case == 'parent':
                    candidate_graph['routing_forest']['records'][1]['parent_face_id'] = 'wrong'
                elif case == 'stage':
                    candidate_event['arrays']['stage_m'][200, 0] += 1.0
                    candidate_event['identity_sha256'] = _i32_identity(candidate_event['arrays'], candidate_event['metadata'])
                elif case == 'geometry':
                    candidate_graph['edges'][0]['geometry']['downhill_terrain_approach']['xyz_m'][0][1] += 1.0
                elif case == 'unknown':
                    candidate_hierarchy['arrays']['node_unknown_contact'][0] = True
                elif case == 'protected':
                    candidate_hierarchy['arrays']['protected_mask'].ravel()[3] = True
                elif case == 'nan':
                    candidate_event['arrays']['stage_m'][0, 0] = float('nan')
                elif case == 'flags':
                    candidate_graph['publishable'] = True
                candidate_graph['identity_sha256'] = _i32_digest({key: value for key, value in candidate_graph.items() if key != 'identity_sha256'})
                with self.assertRaises(ValueError):
                    _i32_build_watershed_paths(candidate_graph, candidate_hierarchy, candidate_event, minimum_area_m2=4.0)
        with _i32_patch('terrain_pipeline.channel_geometry.MAX_ARCS', 1), self.assertRaises(MemoryError):
            _i32_build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.0)
        for minimum in (0.0, -1.0, float('inf'), float('nan'), True):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                _i32_build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=minimum)
        corrupted = _i32_deepcopy(paths)
        corrupted['arcs'][0]['xyz_m'][0][1] += 1.0
        corrupted['identity_sha256'] = _i32_digest({key: value for key, value in corrupted.items() if key != 'identity_sha256'})
        with self.assertRaises(ValueError):
            _i32_validate_watershed_paths(corrupted)
        with self.assertRaises(ValueError):
            _i32_validate_watershed_paths(paths, graph=graph)

def _test_td_watershed_sections_fixture():
    shape = (7, 7)
    height = _i33_np.full(shape, 100.0)
    height.ravel()[[23, 17, 24, 25]] = [90.0, 90.0, 85.0, 80.0]
    receiver = _i33_np.full(height.size, -1, dtype=_i33_np.int64)
    for first, second in ((22, 23), (16, 23), (30, 23), (23, 24), (9, 10), (11, 10), (10, 17), (17, 24), (24, 25)):
        receiver[first] = second
    owner = _i33_np.zeros(shape, dtype=_i33_np.int64)
    owner.ravel()[0] = 1
    hierarchy = {'identity_sha256': 'hierarchy', 'metadata': {'spacing_m': 30.0, 'origin_m_xz': [0.0, 0.0], 'source_identity_sha256': 'source'}, 'arrays': {'height_m': height, 'receiver': receiver, 'contribution_owner': owner, 'valid_mask': _i33_np.ones(shape, dtype=bool), 'protected_mask': _i33_np.zeros(shape, dtype=bool), 'open_boundary_mask': _i33_np.zeros(shape, dtype=bool), 'face_cells': _i33_np.array([[0, 1]])}}
    topology = {'identity_sha256': 'topology', 'arrays': {'leaf_ids': _i33_np.array([0, 1]), 'leaf_area_m2': _i33_np.array([48 * 900.0, 900.0])}, 'faces': [{'face_id': 'external', 'face_index': 0, 'leaf_ids': [0, 1], 'cell_ids': [0, 1]}]}
    ordinary = {'identity_sha256': 'ordinary', 'metadata': {'duration_s': 100.0}, 'arrays': {'outflow_volume_m3': _i33_np.array([[48.0, 1.0]]), 'stage_m': _i33_np.array([[0.0, 0.0], [0.0, 0.0]]), 'face_forward_m3': _i33_np.array([[2.0]]), 'face_reverse_m3': _i33_np.array([[5.0]])}}
    nodes = []
    for cell, area in ((23, 3600.0), (17, 3600.0), (24, 8100.0), (25, 9000.0), (1, 900.0)):
        nodes.append({'node_id': f'cell:{cell}', 'cell_id': cell, 'leaf_id': 0, 'xyz_m': [float(cell % 7 * 30), float(height.ravel()[cell]), float(cell // 7 * 30)], 'local_upstream_area_m2': area, 'kinds': ['land_channel'] if cell != 1 else ['spill']})
    lookup = {node['cell_id']: node for node in nodes}
    arcs = []
    for first, second in ((23, 24), (24, 25)):
        arcs.append({'arc_id': f'receiver:{first}:{second}', 'kind': 'land_channel', 'node_ids': [f'cell:{first}', f'cell:{second}'], 'cell_ids': [first, second], 'xyz_m': [lookup[first]['xyz_m'], lookup[second]['xyz_m']], 'leaf_id': 0, 'face_id': None, 'is_main_path': True, 'channel_candidate': True})
    arcs.append({'arc_id': 'support', 'kind': 'source_lake_approach', 'node_ids': ['cell:1'], 'cell_ids': [1], 'xyz_m': [lookup[1]['xyz_m']], 'leaf_id': 0, 'face_id': 'external', 'is_main_path': True, 'channel_candidate': False})
    paths = {'identity_sha256': 'paths', 'graph_identity_sha256': 'graph-with-strong', 'nodes': nodes, 'arcs': arcs, 'lakes': [], 'selected_leaf_ids': [0], 'parameters': {'minimum_area_m2': 3600.0}}
    return (paths, hierarchy, topology, ordinary)

class WatershedSectionsTests(_i33_unittest.TestCase):

    def test_shared_bank_mesh_actual_net_proxy_and_shape_identity(self):
        from terrain_pipeline.channel_geometry import build_watershed_sections as _i33_build_watershed_sections
        from terrain_pipeline.channel_geometry import load_watershed_sections as _i33_load_watershed_sections
        from terrain_pipeline.channel_geometry import save_watershed_sections as _i33_save_watershed_sections
        paths, hierarchy, topology, ordinary = _test_td_watershed_sections_fixture()
        original = hierarchy['arrays']['height_m'].copy()
        result = _i33_build_watershed_sections(paths, hierarchy, topology, ordinary)
        sections = {section['node_id']: section for section in result['node_sections']}
        self.assertAlmostEqual(sections['cell:1']['incoming_exchange_q_m3_s'], 0.03)
        self.assertEqual(result['exchange_injections'][0]['receiver_cell_id'], 1)
        self.assertEqual(result['exchange_injections'][0]['net_volume_m3'], 3.0)
        self.assertGreater(len(result['mesh']['triangles']), 0)
        self.assertEqual(len(result['mesh']['node_vertex_indices']['cell:24']), 4)
        shared = [edge for edge in result['edge_sections'] if 'cell:24' in edge['node_ids']]
        self.assertEqual(len(shared), 2)
        for edge in shared:
            index = edge['node_ids'].index('cell:24')
            self.assertEqual(edge['cross_section_xyz_m'][index], sections['cell:24']['cross_section_xyz_m'])
        self.assertEqual(result['support_arcs'], [paths['arcs'][-1]])
        self.assertEqual(sections['cell:1']['bed_m'], 100.0)
        for section in result['node_sections']:
            self.assertFalse(section['flow_regime_certified'])
        changed = _i33_copy.deepcopy(paths)
        changed['graph_identity_sha256'] = 'different-strong-only'
        changed['identity_sha256'] = 'different-composite'
        other = _i33_build_watershed_sections(changed, hierarchy, topology, ordinary)
        self.assertEqual(result['candidate_shape_identity_sha256'], other['candidate_shape_identity_sha256'])
        self.assertNotEqual(result['identity_sha256'], other['identity_sha256'])
        _i33_np.testing.assert_array_equal(hierarchy['arrays']['height_m'], original)
        with _i33_tempfile.TemporaryDirectory() as directory:
            path = _i33_Path(directory) / 'sections.json'
            _i33_save_watershed_sections(result, path)
            self.assertEqual(_i33_load_watershed_sections(path), result)

    def test_refusals_fine_resolution_and_tampered_or_nonfinite_json(self):
        from terrain_pipeline.channel_geometry import build_watershed_sections as _i33_build_watershed_sections
        from terrain_pipeline.channel_geometry import validate_watershed_sections as _i33_validate_watershed_sections
        paths, hierarchy, topology, ordinary = _test_td_watershed_sections_fixture()
        hierarchy['arrays']['protected_mask'][2, 4] = True
        topology['arrays']['leaf_area_m2'][0] -= 900.0
        ordinary['arrays']['outflow_volume_m3'][0, 0] -= 1.0
        result = _i33_build_watershed_sections(paths, hierarchy, topology, ordinary)
        self.assertTrue(any(('protected_source_coverage' in request['refusal_reasons'] for request in result['fine_requests'])))
        for request in result['fine_requests']:
            self.assertLessEqual(request['target_spacing_m'], request['width_m'] / 2)
            self.assertFalse(request['fine_dem_available'])
        anchored = _i33_copy.deepcopy(paths)
        anchored['nodes'][0]['kinds'].append('spill')
        refused = _i33_build_watershed_sections(anchored, hierarchy, topology, ordinary)
        self.assertTrue(any(('anchor_cut_conflict' in reach['rejection_reasons'] for reach in refused['reach_diagnostics'])))
        junction = _i33_copy.deepcopy(paths)
        lookup = {node['node_id']: node for node in junction['nodes']}
        junction['arcs'].append({'arc_id': 'receiver:17:24', 'kind': 'land_channel', 'node_ids': ['cell:17', 'cell:24'], 'cell_ids': [17, 24], 'xyz_m': [lookup['cell:17']['xyz_m'], lookup['cell:24']['xyz_m']], 'leaf_id': 0, 'face_id': None, 'is_main_path': False, 'channel_candidate': True})
        junction_result = _i33_build_watershed_sections(junction, hierarchy, topology, ordinary)
        self.assertTrue(all(('needs_junction_patch' in reach['rejection_reasons'] for reach in junction_result['reach_diagnostics'])))
        self.assertEqual(junction_result['mesh']['triangles'], [])
        for field, value in (('hydraulic_ready', True), ('ordinary_duration_s', float('nan')), ('identity_sha256', 'tampered')):
            damaged = _i33_copy.deepcopy(result)
            damaged[field] = value
            with self.assertRaises(ValueError):
                _i33_validate_watershed_sections(damaged)

class ValleyBudgetTests(_i34_unittest.TestCase):

    def test_allocator_preserves_source_and_respects_protection(self):
        from terrain_pipeline.channel_geometry import ValleyRecipe as _i34_ValleyRecipe
        from terrain_pipeline.channel_geometry import allocate_valley_budget as _i34_allocate_valley_budget
        plan = _x1_confluence_plan()
        source = plan['arrays']['source_height_m'].copy()
        protected = _i34_np.zeros(source.shape, bool)
        protected[3, 3] = True
        result = _i34_allocate_valley_budget(plan, protected, {'pass': False}, _i34_ValleyRecipe(total_area_cells=2, valley_cut_m=8.0, bed_cut_m=4.0))
        self.assertTrue(result['summary']['inherited_joint_blocker'])
        self.assertLessEqual(result['summary']['selected_nodes'], 2)
        self.assertEqual(result['arrays']['valley_allocation_m'][3, 3], 0.0)
        _i34_np.testing.assert_array_equal(plan['arrays']['source_height_m'], source)

    def test_recovery_selector_has_explicit_failure_fallback(self):
        from terrain_pipeline.channel_geometry import plan_recovery as _i34_plan_recovery
        blockers = {'stage': True, 'plan': True}
        plan = _x1_confluence_plan()
        result = _i34_plan_recovery(plan, blockers, candidate_routes=[{'id': 'blocked', 'crosses_protection': True, 'plan_identity_sha256': plan['identity_sha256']}, {'id': 'open', 'crosses_protection': False, 'plan_identity_sha256': plan['identity_sha256']}], lake_spills=[{'id': 'unlegal', 'legal_outlet': False, 'plan_identity_sha256': plan['identity_sha256']}])
        self.assertEqual(result['chosen']['kind'], 'reroute')
        self.assertEqual(result['chosen']['candidate']['id'], 'open')
        failed = _i34_plan_recovery(plan, blockers, lake_spills=[{'id': 'x', 'legal_outlet': False, 'plan_identity_sha256': plan['identity_sha256']}])
        self.assertEqual(failed['chosen']['kind'], 'failure')

    def test_invalid_recipe_rejected(self):
        from terrain_pipeline.channel_geometry import ValleyRecipe as _i34_ValleyRecipe
        with self.assertRaises(ValueError):
            _i34_ValleyRecipe(total_area_cells=0)

class ValleyGeometryTests(_i35_unittest.TestCase):

    def make_result(self, recipe=None, protected=None):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i35_ChannelRecipe
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i35_ValleyGeometryRecipe
        from terrain_pipeline.channel_geometry import prepare_valley_geometry as _i35_prepare_valley_geometry
        plan = _x2_confluence_plan()
        shape = plan['arrays']['source_height_m'].shape
        if protected is None:
            protected = _i35_np.zeros(shape, bool)
        result = _i35_prepare_valley_geometry(plan, _i35_np.array([[30.0, 10.0], [30.0, 60.0]]), _i35_np.array([4.7, 3.7]), _i35_np.array([30.0, 30.0]), _i35_np.ones(shape, bool), protected, recipe or _i35_ValleyGeometryRecipe(8.0, 10000.0, 100000.0, 100000.0), _i35_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=8.0, min_width_m=8.0, max_width_m=8.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, max_cut_m=4.0, min_bed_slope_m_per_m=1e-05))
        return (plan, result)

    def test_independent_valley_and_bed_ledger_round_trip(self):
        from terrain_pipeline.channel_geometry import load_valley_geometry as _i35_load_valley_geometry
        from terrain_pipeline.channel_geometry import save_valley_geometry as _i35_save_valley_geometry
        plan, result = self.make_result()
        self.assertTrue(result['summary']['geometry_feasible'])
        self.assertEqual(result['summary']['geometry_scope'], 'coarse_node_diagnostic_only')
        _i35_np.testing.assert_array_equal(plan['arrays']['source_height_m'], result['arrays']['source_height_m'])
        _i35_np.testing.assert_allclose(result['arrays']['valley_cut_m'] + result['arrays']['bed_cut_m'], result['arrays']['total_cut_m'], rtol=0, atol=1e-09)
        with _i35_tempfile.TemporaryDirectory() as directory:
            path = _i35_Path(directory) / 'valley.npz'
            _i35_save_valley_geometry(result, path)
            loaded = _i35_load_valley_geometry(path)
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])
            with _i35_np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != 'manifest'}
                manifest = archive['manifest'].item()
            arrays['total_cut_m'] = arrays['total_cut_m'].copy()
            arrays['total_cut_m'][0, 0] += 1
            _i35_np.savez_compressed(path, manifest=manifest, **arrays)
            with self.assertRaises(ValueError):
                _i35_load_valley_geometry(path)

    def test_valley_depth_area_volume_and_protection_fail_independently(self):
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i35_ValleyGeometryRecipe
        cases = [(_i35_ValleyGeometryRecipe(0.1, 10000.0, 100000.0, 100000.0), 'valley_depth'), (_i35_ValleyGeometryRecipe(8.0, 100.0, 100000.0, 100000.0), 'valley_area'), (_i35_ValleyGeometryRecipe(8.0, 10000.0, 10.0, 100000.0), 'valley_volume'), (_i35_ValleyGeometryRecipe(8.0, 10000.0, 100000.0, 10.0), 'total_volume')]
        for recipe, key in cases:
            with self.subTest(key=key):
                _, result = self.make_result(recipe)
                self.assertTrue(result['summary']['failures'][key])
                self.assertFalse(result['summary']['geometry_feasible'])
        protected = _i35_np.zeros((7, 7), bool)
        protected[3, 3] = True
        _, result = self.make_result(protected=protected)
        self.assertTrue(result['summary']['failures']['protection'])

    def test_fine_h0_h1_h2_with_joint_water(self):
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i35_evaluate_fine_valley_ledger
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i35_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import prepare_surface_network as _i35_prepare_surface_network
        from terrain_pipeline.channel_geometry import SectionRecipe as _i35_SectionRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i35_StageRecipe
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i35_InundationRecipe
        _, valley = self.make_result()
        domain = _i35_np.ones((61, 61), bool)
        empty = _i35_np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        surface = _i35_prepare_surface_network(valley['replanned_plan'], 0.0, 0.0, 1.0, 1.0, (61, 61), domain, empty, legal, _i35_np.array([5.2]), _i35_SectionRecipe(), _i35_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i35_InundationRecipe(max_lateral_reach_m=15.0), _i35_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        ledger = _i35_evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger['status'], 'prepared')
        arrays = ledger['arrays']
        _i35_np.testing.assert_allclose(arrays['valley_cut_m'] + arrays['bed_cut_m'], arrays['total_cut_m'], rtol=0, atol=1e-08)
        self.assertGreater(ledger['summary']['valley_cut_volume_m3'], 0)
        self.assertGreater(ledger['summary']['bed_cut_volume_m3'], 0)

    def test_coarse_protection_failure_survives_fine_joint(self):
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i35_evaluate_fine_valley_ledger
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i35_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import prepare_surface_network as _i35_prepare_surface_network
        from terrain_pipeline.channel_geometry import SectionRecipe as _i35_SectionRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i35_StageRecipe
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i35_InundationRecipe
        protected = _i35_np.zeros((7, 7), bool)
        protected[3, 3] = True
        _, valley = self.make_result(protected=protected)
        domain = _i35_np.ones((61, 61), bool)
        empty = _i35_np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        surface = _i35_prepare_surface_network(valley['replanned_plan'], 0.0, 0.0, 1.0, 1.0, (61, 61), domain, empty, legal, _i35_np.array([5.2]), _i35_SectionRecipe(), _i35_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i35_InundationRecipe(max_lateral_reach_m=15.0), _i35_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        ledger = _i35_evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger['status'], 'diagnostic_not_publishable')
        self.assertTrue(ledger['summary']['failures']['coarse_valley'])

    def test_blocked_bed_becomes_feasible_after_independent_valley(self):
        from terrain_pipeline.channel_geometry import ChannelRecipe as _i35_ChannelRecipe
        from terrain_pipeline.channel_geometry import plan_channel as _i35_plan_channel
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _i35_ValleyGeometryRecipe
        from terrain_pipeline.channel_geometry import prepare_valley_geometry as _i35_prepare_valley_geometry
        from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _i35_evaluate_fine_valley_ledger
        from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _i35_SurfaceNetworkBudget
        from terrain_pipeline.surface_domain import prepare_surface_network as _i35_prepare_surface_network
        from terrain_pipeline.channel_geometry import SectionRecipe as _i35_SectionRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _i35_StageRecipe
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _i35_InundationRecipe
        base = _x2_confluence_plan()
        arrays = base['arrays']
        raised = arrays['source_height_m'].copy()
        raised[3, 3] += 5.0
        params = base['identity']['parameters']
        recipe = _i35_ChannelRecipe(reference_discharge_m3_s=0.1, reference_width_m=8.0, min_width_m=8.0, max_width_m=8.0, reference_depth_m=0.5, min_depth_m=0.5, max_depth_m=0.5, max_cut_m=4.0, min_bed_slope_m_per_m=1e-05)
        blocked = _i35_plan_channel(raised, arrays['receiver'], arrays['order'], arrays['outlet_mask'], arrays['discharge_m3_s'], 10.0, 10.0, 0.0, 0.0, 0.0, 'raised-ridge', recipe)
        self.assertTrue(blocked['arrays']['over_budget_mask'].any())
        valley = _i35_prepare_valley_geometry(blocked, _i35_np.array([[30.0, 10.0], [30.0, 60.0]]), _i35_np.array([4.7, 3.7]), _i35_np.array([30.0, 30.0]), _i35_np.ones((7, 7), bool), _i35_np.zeros((7, 7), bool), _i35_ValleyGeometryRecipe(8.0, 10000.0, 100000.0, 100000.0), recipe)
        self.assertFalse(valley['replanned_plan']['arrays']['over_budget_mask'].any())
        self.assertTrue(valley['summary']['geometry_feasible'])
        self.assertEqual(valley['arrays']['source_height_m'][3, 3], 10.0)
        domain = _i35_np.ones((61, 61), bool)
        empty = _i35_np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        surface = _i35_prepare_surface_network(valley['replanned_plan'], 0.0, 0.0, 1.0, 1.0, (61, 61), domain, empty, legal, _i35_np.array([5.2]), _i35_SectionRecipe(), _i35_StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), _i35_InundationRecipe(max_lateral_reach_m=15.0), _i35_SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
        ledger = _i35_evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger['status'], 'prepared')
        self.assertFalse(any(ledger['summary']['failures'].values()))
