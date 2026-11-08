"""M4 tests.test_drainage_equivalence; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from pathlib import Path as _m4_test_drainage_kernels_equivalence_Path
from terrain_pipeline import new_world_stage1 as _m4_test_drainage_kernels_equivalence_S1
from terrain_pipeline.drainage import route_pool_interval as _m4_test_drainage_kernels_equivalence_merged_WA_route_pool_interval
import numpy as _m4_test_drainage_kernels_equivalence_np
import terrain_pipeline.drainage as _m4_test_drainage_kernels_equivalence_FP
import terrain_pipeline.drainage as _m4_test_drainage_kernels_equivalence_ID
import terrain_pipeline.drainage as _m4_test_drainage_kernels_equivalence_K
import unittest as _m4_test_drainage_kernels_equivalence_unittest

# --- tests/test_drainage_kernels_equivalence.py:19 ---
test_drainage_kernels_equivalence_ROOT = _m4_test_drainage_kernels_equivalence_Path(__file__).resolve().parents[1]

# --- tests/test_drainage_kernels_equivalence.py:20 ---
test_drainage_kernels_equivalence_SAVED = test_drainage_kernels_equivalence_ROOT / '.scratch' / 'river-upgrade-20261101'

# --- tests/test_drainage_kernels_equivalence.py:23 ---
def _test_drainage_kernels_equivalence_quantized_bed(rng, shape, levels):
    """Few distinct heights, so plateaus force the tie rules to matter."""
    return rng.integers(0, levels, size=shape).astype(_m4_test_drainage_kernels_equivalence_np.float64) * 0.5 + rng.random(shape) * (levels <= 0)

# --- tests/test_drainage_kernels_equivalence.py:28 ---
def _test_drainage_kernels_equivalence_outlets(rng, shape, count):
    out = _m4_test_drainage_kernels_equivalence_np.zeros(shape, dtype=bool)
    flat = out.ravel()
    flat[rng.choice(flat.size, size=count, replace=False)] = True
    return out

# --- tests/test_drainage_kernels_equivalence.py:35 ---
class TestDrainageKernelsEquivalenceFloodRouteEquivalence(_m4_test_drainage_kernels_equivalence_unittest.TestCase):
    def test_vs_irregular_drainage_route(self):
        for seed, shape, levels in [(1, (18, 21), 4), (2, (25, 25), 40), (3, (16, 30), 2), (4, (30, 17), 1000)]:
            with self.subTest(seed=seed):
                rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(seed)
                mesh = _m4_test_drainage_kernels_equivalence_ID.build_mesh(shape, origin_native_xz=(int(rng.integers(-500, 500)), int(rng.integers(-500, 500))),
                                     world_seed=int(rng.integers(1, 10**9)))
                bed = _test_drainage_kernels_equivalence_quantized_bed(rng, shape, levels)
                outlets = _test_drainage_kernels_equivalence_outlets(rng, shape, 3)
                old = _m4_test_drainage_kernels_equivalence_ID._route(bed.ravel(), outlets.ravel(), mesh.indptr, mesh.indices, mesh.edge_length_m)
                new = _m4_test_drainage_kernels_equivalence_K.flood_route_arrays(bed, outlets, mesh.node_x_m, mesh.node_z_m, mesh.indptr, mesh.indices)
                for name, a, b in zip(('filled', 'order', 'rank', 'receiver'), old, new):
                    self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(a, b), name)

    def test_vs_mapped_route_with_valid_mask(self):
        checked = 0
        for seed in range(6):
            rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(100 + seed)
            shape = (22, 26)
            mesh = _m4_test_drainage_kernels_equivalence_ID.build_mesh(shape, world_seed=7 + seed)
            bed = _test_drainage_kernels_equivalence_quantized_bed(rng, shape, 6)
            valid = rng.random(shape) > 0.03
            outlets = _test_drainage_kernels_equivalence_outlets(rng, shape, 4) & valid
            if not outlets.any():
                continue
            n = bed.size
            def run(fn):
                arrays = [_m4_test_drainage_kernels_equivalence_np.empty(n, dtype=t) for t in (_m4_test_drainage_kernels_equivalence_np.float64, _m4_test_drainage_kernels_equivalence_np.int64, _m4_test_drainage_kernels_equivalence_np.int64, _m4_test_drainage_kernels_equivalence_np.int64, _m4_test_drainage_kernels_equivalence_np.bool_, _m4_test_drainage_kernels_equivalence_np.float64, _m4_test_drainage_kernels_equivalence_np.int64)]
                try:
                    fn(bed.ravel(), outlets.ravel(), valid.ravel(), mesh.node_x_m, mesh.node_z_m,
                       mesh.indptr, mesh.indices, *arrays)
                except ValueError as exc:
                    return str(exc)
                return arrays
            old, new = run(_m4_test_drainage_kernels_equivalence_S1._mapped_route), run(_m4_test_drainage_kernels_equivalence_K.flood_route)
            if isinstance(old, str) or isinstance(new, str):
                self.assertEqual(old, new)   # both must refuse with the same message
                continue
            checked += 1
            for name, a, b in zip(('filled', 'order', 'rank', 'receiver'), old[:4], new[:4]):
                self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(a, b), name)
        self.assertGreater(checked, 0)

    def test_vs_flood_phases_split(self):
        rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(55)
        shape = (24, 24)
        mesh = _m4_test_drainage_kernels_equivalence_ID.build_mesh(shape, world_seed=99)
        bed = _test_drainage_kernels_equivalence_quantized_bed(rng, shape, 5)
        outlets = _test_drainage_kernels_equivalence_outlets(rng, shape, 3)
        valid = _m4_test_drainage_kernels_equivalence_np.ones(shape, dtype=bool)
        n = bed.size

        def phases(flood, select):
            filled, order, rank, disc = (_m4_test_drainage_kernels_equivalence_np.empty(n, dtype=t) for t in (_m4_test_drainage_kernels_equivalence_np.float64, _m4_test_drainage_kernels_equivalence_np.int64, _m4_test_drainage_kernels_equivalence_np.int64, _m4_test_drainage_kernels_equivalence_np.bool_))
            hl, hn, receiver = _m4_test_drainage_kernels_equivalence_np.empty(n, _m4_test_drainage_kernels_equivalence_np.float64), _m4_test_drainage_kernels_equivalence_np.empty(n, _m4_test_drainage_kernels_equivalence_np.int64), _m4_test_drainage_kernels_equivalence_np.empty(n, _m4_test_drainage_kernels_equivalence_np.int64)
            flood(bed.ravel(), outlets.ravel(), valid.ravel(), mesh.indptr, mesh.indices, filled, order, rank, disc, hl, hn)
            select(outlets.ravel(), valid.ravel(), mesh.node_x_m, mesh.node_z_m, mesh.indptr, mesh.indices,
                   filled, order, rank, receiver)
            return filled, order, rank, receiver

        for a, b in zip(phases(_m4_test_drainage_kernels_equivalence_FP.flood_order, _m4_test_drainage_kernels_equivalence_FP.select_receivers), phases(_m4_test_drainage_kernels_equivalence_K.flood_order, _m4_test_drainage_kernels_equivalence_K.select_receivers)):
            self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(a, b))

    def test_real_bed_slice(self):
        bed_path = test_drainage_kernels_equivalence_SAVED / 'terrain-v3' / 'bed_m.npy'
        if not bed_path.exists():
            self.skipTest('saved terrain-v3 not present')
        bed = _m4_test_drainage_kernels_equivalence_np.array(_m4_test_drainage_kernels_equivalence_np.load(bed_path, mmap_mode='r')[1500:1564, 1300:1364], dtype=_m4_test_drainage_kernels_equivalence_np.float64)
        shape = bed.shape
        outlets = _m4_test_drainage_kernels_equivalence_np.zeros(shape, dtype=bool)
        outlets[0, :] = outlets[-1, :] = outlets[:, 0] = outlets[:, -1] = True
        mesh = _m4_test_drainage_kernels_equivalence_ID.build_mesh(shape, origin_native_xz=(1300, 1500))
        old = _m4_test_drainage_kernels_equivalence_ID._route(bed.ravel(), outlets.ravel(), mesh.indptr, mesh.indices, mesh.edge_length_m)
        new = _m4_test_drainage_kernels_equivalence_K.flood_route_arrays(bed, outlets, mesh.node_x_m, mesh.node_z_m, mesh.indptr, mesh.indices)
        for a, b in zip(old, new):
            self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(a, b))

# --- tests/test_drainage_kernels_equivalence.py:113 ---
class TestDrainageKernelsEquivalenceAccumulateEquivalence(_m4_test_drainage_kernels_equivalence_unittest.TestCase):
    def _routing(self, seed, shape=(30, 30)):
        rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(seed)
        mesh = _m4_test_drainage_kernels_equivalence_ID.build_mesh(shape, world_seed=seed)
        bed = _test_drainage_kernels_equivalence_quantized_bed(rng, shape, 8)
        outlets = _test_drainage_kernels_equivalence_outlets(rng, shape, 2)
        filled, order, rank, receiver = _m4_test_drainage_kernels_equivalence_K.flood_route_arrays(bed, outlets, mesh.node_x_m, mesh.node_z_m,
                                                             mesh.indptr, mesh.indices)
        return rng, order, receiver

    def test_accumulate_flow_vs_irregular(self):
        for seed in (1, 2, 3):
            rng, order, receiver = self._routing(seed)
            local = rng.random(order.size) * 10.0 ** rng.integers(-3, 6, size=order.size)  # summation-order sensitive
            self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(_m4_test_drainage_kernels_equivalence_ID._accumulate(receiver, order, local), _m4_test_drainage_kernels_equivalence_K.accumulate_flow(receiver, order, local)))

    def test_accumulate_inplace_vs_native_lowland(self):
        import terrain_pipeline.drainage as NL
        for seed in (1, 2, 3):
            rng, order, receiver = self._routing(seed)
            for dtype in (_m4_test_drainage_kernels_equivalence_np.int32, _m4_test_drainage_kernels_equivalence_np.float64):
                area = (rng.integers(0, 2, size=order.size)).astype(dtype)
                a, b = area.copy(), area.copy()
                NL.accumulate_inplace(order, receiver, a)
                _m4_test_drainage_kernels_equivalence_K.accumulate_inplace(order, receiver, b)
                self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(a, b))

    def test_accumulate_inplace_equals_copying(self):
        rng, order, receiver = self._routing(9)
        local = rng.random(order.size)
        b = local.copy()
        _m4_test_drainage_kernels_equivalence_K.accumulate_inplace(order, receiver, b)
        self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(b, _m4_test_drainage_kernels_equivalence_K.accumulate_flow(receiver, order, local)))

    def test_pool_route_vs_route_pool_interval(self):
        from terrain_pipeline import environment_product as WA
        for seed in (1, 2, 3):
            rng, order, receiver = self._routing(seed)
            n = order.size
            labels = _m4_test_drainage_kernels_equivalence_np.full(n, -1, _m4_test_drainage_kernels_equivalence_np.int64)
            pools = 5
            members = rng.choice(n, size=n // 3, replace=False)
            labels[members] = rng.integers(0, pools, size=members.size)
            anchors = _m4_test_drainage_kernels_equivalence_np.full(pools, -1, _m4_test_drainage_kernels_equivalence_np.int64)
            for p in range(pools):
                cells = _m4_test_drainage_kernels_equivalence_np.flatnonzero(labels == p)
                if cells.size:   # anchor = member latest in flood order
                    rank = _m4_test_drainage_kernels_equivalence_np.empty(n, _m4_test_drainage_kernels_equivalence_np.int64)
                    rank[order] = _m4_test_drainage_kernels_equivalence_np.arange(n)
                    anchors[p] = cells[_m4_test_drainage_kernels_equivalence_np.argmax(rank[cells])]
            capacity = rng.random(pools) * 5
            local = rng.random(n)
            s1, s2 = rng.random(pools), None
            s2 = s1.copy()
            s1 = s1.copy()
            f1, r1 = _m4_test_drainage_kernels_equivalence_merged_WA_route_pool_interval(local, order, receiver, labels, anchors, capacity, s1)
            f2, r2 = _m4_test_drainage_kernels_equivalence_K.accumulate_with_pools(local, order, receiver, labels, anchors, capacity, s2)
            self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(f1, f2))
            self.assertEqual(r1, r2)
            self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(s1, s2))

    def test_no_pool_path_equals_plain_accumulation(self):
        rng, order, receiver = self._routing(4)
        local = rng.random(order.size)
        labels = _m4_test_drainage_kernels_equivalence_np.full(order.size, -1, _m4_test_drainage_kernels_equivalence_np.int64)
        flow, retained = _m4_test_drainage_kernels_equivalence_K.accumulate_with_pools(local, order, receiver, labels, _m4_test_drainage_kernels_equivalence_np.empty(0, _m4_test_drainage_kernels_equivalence_np.int64),
                                                 _m4_test_drainage_kernels_equivalence_np.empty(0), _m4_test_drainage_kernels_equivalence_np.empty(0))
        self.assertEqual(retained, 0.0)
        self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(flow, _m4_test_drainage_kernels_equivalence_K.accumulate_flow(receiver, order, local)))

    def test_real_routing_order(self):
        order_path = test_drainage_kernels_equivalence_SAVED / 'native-final-routing-v1' / 'routing' / 'order.npy'
        receiver_path = test_drainage_kernels_equivalence_SAVED / 'native-final-routing-v1' / 'routing' / 'receiver.npy'
        if not (order_path.exists() and receiver_path.exists()):
            self.skipTest('saved native-final-routing-v1 not present')
        order = _m4_test_drainage_kernels_equivalence_np.load(order_path, mmap_mode='r')
        receiver = _m4_test_drainage_kernels_equivalence_np.load(receiver_path, mmap_mode='r')
        # accumulation reads order from the far end, so a tail slice of the order is a valid sub-problem
        # only when every cell it drains into is inside it; use the full arrays on a thinned local field.
        rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(3)
        local = _m4_test_drainage_kernels_equivalence_np.zeros(order.size)
        picks = rng.choice(order.size, size=200000, replace=False)
        local[picks] = rng.random(picks.size) * 1e4
        order, receiver = _m4_test_drainage_kernels_equivalence_np.asarray(order), _m4_test_drainage_kernels_equivalence_np.asarray(receiver)
        self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(_m4_test_drainage_kernels_equivalence_ID._accumulate(receiver, order, local), _m4_test_drainage_kernels_equivalence_K.accumulate_flow(receiver, order, local)))

# --- tests/test_drainage_kernels_equivalence.py:200 ---
class TestDrainageKernelsEquivalenceSectionAndMaskEquivalence(_m4_test_drainage_kernels_equivalence_unittest.TestCase):
    def test_native_section(self):
        from terrain_pipeline.new_world_native_network import section
        rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(8)
        q = _m4_test_drainage_kernels_equivalence_np.concatenate((_m4_test_drainage_kernels_equivalence_np.array([-1.0, 0.0, 1e-9, 1.0, 1e9]), rng.random(500) * 10.0 ** rng.integers(-4, 5, 500)))
        w0, d0 = section(q)
        w1, d1 = _m4_test_drainage_kernels_equivalence_K.native_section(q)
        self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(w0, w1))
        self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(d0, d1))

    def test_lake_wet_window_vs_saved_masks(self):
        # (network version, the pool-level product that version reads)
        pairs = [('v2', 'native-event-v1'), ('v3', 'native-event-v2'), ('v4', 'native-event-v3'), ('v5', 'native-event-v3')]
        labels_path = test_drainage_kernels_equivalence_SAVED / 'native-final-routing-v1' / 'derived' / 'pool_index.npy'
        if not labels_path.exists():
            self.skipTest('saved products not present')
        labels = _m4_test_drainage_kernels_equivalence_np.load(labels_path, mmap_mode='r').reshape(4096, 4096)
        bed = _m4_test_drainage_kernels_equivalence_np.load(test_drainage_kernels_equivalence_SAVED / 'terrain-v3' / 'bed_m.npy', mmap_mode='r')
        ocean = _m4_test_drainage_kernels_equivalence_np.load(test_drainage_kernels_equivalence_SAVED / 'terrain-v3' / 'ocean_mask.npy', mmap_mode='r')
        for version, event in pairs:
            saved_path = test_drainage_kernels_equivalence_SAVED / f'native-network-{version}' / 'lake_wet_mask.npy'
            if not saved_path.exists():
                continue
            with self.subTest(version=version):
                levels = _m4_test_drainage_kernels_equivalence_np.asarray(_m4_test_drainage_kernels_equivalence_np.load(test_drainage_kernels_equivalence_SAVED / event / 'pool_level_m.npy', mmap_mode='r')[2])
                self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(_m4_test_drainage_kernels_equivalence_K.lake_wet_window(labels, bed, levels, ocean), _m4_test_drainage_kernels_equivalence_np.load(saved_path)))

    def test_lake_wet_window_random_vs_inline_expression(self):
        rng = _m4_test_drainage_kernels_equivalence_np.random.default_rng(5)
        labels = rng.integers(-1, 6, size=(40, 40))
        bed = rng.random((40, 40)) * 10
        ocean = rng.random((40, 40)) < 0.2
        levels = rng.random(6) * 10
        levels[2] = _m4_test_drainage_kernels_equivalence_np.nan
        z0, z1, x0, x1 = 3, 33, 5, 37
        pool, heights = labels[z0:z1, x0:x1], bed[z0:z1, x0:x1]   # expression copied from native_network_v2.build
        wet = _m4_test_drainage_kernels_equivalence_np.zeros(pool.shape, bool)
        present = pool >= 0
        wet[present] = _m4_test_drainage_kernels_equivalence_np.isfinite(levels[pool[present]]) & (heights[present] < levels[pool[present]])
        wet &= ~ocean[z0:z1, x0:x1]
        self.assertTrue(_m4_test_drainage_kernels_equivalence_np.array_equal(wet, _m4_test_drainage_kernels_equivalence_K.lake_wet_window(labels, bed, levels, ocean, window=(z0, z1, x0, x1))))

# --- tests/test_drainage_kernels_equivalence.py:243 ---
class TestDrainageKernelsEquivalenceDigestEquivalence(_m4_test_drainage_kernels_equivalence_unittest.TestCase):
    """The digests live in ``common_infra`` now; this pins them against the modules that still carry one."""

    def test_file_sha256(self):
        import tempfile
        from terrain_pipeline import common_infra as CI
        import terrain_pipeline.drainage as NL
        with tempfile.TemporaryDirectory() as tmp:
            path = _m4_test_drainage_kernels_equivalence_Path(tmp) / 'blob.bin'
            path.write_bytes(_m4_test_drainage_kernels_equivalence_np.random.default_rng(1).bytes(3 * 1024 * 1024 + 17))
            expected = CI.file_sha256(path)
            self.assertEqual(expected, _m4_test_drainage_kernels_equivalence_S1._digest(path))
            self.assertEqual(expected, _m4_test_drainage_kernels_equivalence_FP.flood_phase_digest(path))
            self.assertEqual(expected, NL.lowland_digest(path))
            empty = _m4_test_drainage_kernels_equivalence_Path(tmp) / 'empty.bin'
            empty.write_bytes(b'')
            self.assertEqual(CI.file_sha256(empty), _m4_test_drainage_kernels_equivalence_S1._digest(empty))

    def test_canonical_json_digests(self):
        from terrain_pipeline import common_infra as CI
        from terrain_pipeline import hydrology_detail as HD
        from terrain_pipeline import hydrology_detail_projection as HP
        from terrain_pipeline import hydrology_detail_tributaries as HR
        from terrain_pipeline import td_source as HT
        record = {'b': [1, 2.5, None, True], 'a': {'z': '山川', 'y': -0.0}, 'c': 'x'}
        expected = CI.canonical_json_digest_default(record)
        for digest in (HD._digest, HP._digest, HT._hydrology_td_digest):
            self.assertEqual(expected, digest(record))
        self.assertEqual(CI.json_sha256(record), HR._digest(record))
        self.assertNotEqual(expected, CI.json_sha256(record))

    def test_stage1_identity_json_style_is_not_default_style(self):
        # new_world_stage1._identity uses compact separators; document it matches the compact digest
        from terrain_pipeline import common_infra as CI
        record = {'k': 1, 'identity': 'skip', 'terrain_path': 'skip', 'v': [1, 2]}
        trimmed = {k: v for k, v in record.items() if k not in ('identity', 'terrain_path')}
        self.assertEqual(_m4_test_drainage_kernels_equivalence_S1._identity(record), CI.json_sha256(trimmed))
