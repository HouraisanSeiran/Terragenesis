"""Differential tests: terrain_pipeline.drainage_kernels vs every older entry point.

Each assertion uses exact equality (np.array_equal / ==), because the kernels are
verbatim moves and must not change any number in existing products.
"""

from terrain_pipeline.drainage import route_pool_interval as _merged_WA_route_pool_interval
import json
import unittest
from pathlib import Path

import numpy as np

import terrain_pipeline.drainage as K
import terrain_pipeline.drainage as ID
from terrain_pipeline import new_world_stage1 as S1
import terrain_pipeline.drainage as FP

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / '.scratch' / 'river-upgrade-20261101'


def _quantized_bed(rng, shape, levels):
    """Few distinct heights, so plateaus force the tie rules to matter."""
    return rng.integers(0, levels, size=shape).astype(np.float64) * 0.5 + rng.random(shape) * (levels <= 0)


def _outlets(rng, shape, count):
    out = np.zeros(shape, dtype=bool)
    flat = out.ravel()
    flat[rng.choice(flat.size, size=count, replace=False)] = True
    return out


class FloodRouteEquivalence(unittest.TestCase):
    def test_vs_irregular_drainage_route(self):
        for seed, shape, levels in [(1, (18, 21), 4), (2, (25, 25), 40), (3, (16, 30), 2), (4, (30, 17), 1000)]:
            with self.subTest(seed=seed):
                rng = np.random.default_rng(seed)
                mesh = ID.build_mesh(shape, origin_native_xz=(int(rng.integers(-500, 500)), int(rng.integers(-500, 500))),
                                     world_seed=int(rng.integers(1, 10**9)))
                bed = _quantized_bed(rng, shape, levels)
                outlets = _outlets(rng, shape, 3)
                old = ID._route(bed.ravel(), outlets.ravel(), mesh.indptr, mesh.indices, mesh.edge_length_m)
                new = K.flood_route_arrays(bed, outlets, mesh.node_x_m, mesh.node_z_m, mesh.indptr, mesh.indices)
                for name, a, b in zip(('filled', 'order', 'rank', 'receiver'), old, new):
                    self.assertTrue(np.array_equal(a, b), name)

    def test_vs_mapped_route_with_valid_mask(self):
        checked = 0
        for seed in range(6):
            rng = np.random.default_rng(100 + seed)
            shape = (22, 26)
            mesh = ID.build_mesh(shape, world_seed=7 + seed)
            bed = _quantized_bed(rng, shape, 6)
            valid = rng.random(shape) > 0.03
            outlets = _outlets(rng, shape, 4) & valid
            if not outlets.any():
                continue
            n = bed.size
            def run(fn):
                arrays = [np.empty(n, dtype=t) for t in (np.float64, np.int64, np.int64, np.int64, np.bool_, np.float64, np.int64)]
                try:
                    fn(bed.ravel(), outlets.ravel(), valid.ravel(), mesh.node_x_m, mesh.node_z_m,
                       mesh.indptr, mesh.indices, *arrays)
                except ValueError as exc:
                    return str(exc)
                return arrays
            old, new = run(S1._mapped_route), run(K.flood_route)
            if isinstance(old, str) or isinstance(new, str):
                self.assertEqual(old, new)   # both must refuse with the same message
                continue
            checked += 1
            for name, a, b in zip(('filled', 'order', 'rank', 'receiver'), old[:4], new[:4]):
                self.assertTrue(np.array_equal(a, b), name)
        self.assertGreater(checked, 0)

    def test_vs_flood_phases_split(self):
        rng = np.random.default_rng(55)
        shape = (24, 24)
        mesh = ID.build_mesh(shape, world_seed=99)
        bed = _quantized_bed(rng, shape, 5)
        outlets = _outlets(rng, shape, 3)
        valid = np.ones(shape, dtype=bool)
        n = bed.size

        def phases(flood, select):
            filled, order, rank, disc = (np.empty(n, dtype=t) for t in (np.float64, np.int64, np.int64, np.bool_))
            hl, hn, receiver = np.empty(n, np.float64), np.empty(n, np.int64), np.empty(n, np.int64)
            flood(bed.ravel(), outlets.ravel(), valid.ravel(), mesh.indptr, mesh.indices, filled, order, rank, disc, hl, hn)
            select(outlets.ravel(), valid.ravel(), mesh.node_x_m, mesh.node_z_m, mesh.indptr, mesh.indices,
                   filled, order, rank, receiver)
            return filled, order, rank, receiver

        for a, b in zip(phases(FP.flood_order, FP.select_receivers), phases(K.flood_order, K.select_receivers)):
            self.assertTrue(np.array_equal(a, b))

    def test_real_bed_slice(self):
        bed_path = SAVED / 'terrain-v3' / 'bed_m.npy'
        if not bed_path.exists():
            self.skipTest('saved terrain-v3 not present')
        bed = np.array(np.load(bed_path, mmap_mode='r')[1500:1564, 1300:1364], dtype=np.float64)
        shape = bed.shape
        outlets = np.zeros(shape, dtype=bool)
        outlets[0, :] = outlets[-1, :] = outlets[:, 0] = outlets[:, -1] = True
        mesh = ID.build_mesh(shape, origin_native_xz=(1300, 1500))
        old = ID._route(bed.ravel(), outlets.ravel(), mesh.indptr, mesh.indices, mesh.edge_length_m)
        new = K.flood_route_arrays(bed, outlets, mesh.node_x_m, mesh.node_z_m, mesh.indptr, mesh.indices)
        for a, b in zip(old, new):
            self.assertTrue(np.array_equal(a, b))


class AccumulateEquivalence(unittest.TestCase):
    def _routing(self, seed, shape=(30, 30)):
        rng = np.random.default_rng(seed)
        mesh = ID.build_mesh(shape, world_seed=seed)
        bed = _quantized_bed(rng, shape, 8)
        outlets = _outlets(rng, shape, 2)
        filled, order, rank, receiver = K.flood_route_arrays(bed, outlets, mesh.node_x_m, mesh.node_z_m,
                                                             mesh.indptr, mesh.indices)
        return rng, order, receiver

    def test_accumulate_flow_vs_irregular(self):
        for seed in (1, 2, 3):
            rng, order, receiver = self._routing(seed)
            local = rng.random(order.size) * 10.0 ** rng.integers(-3, 6, size=order.size)  # summation-order sensitive
            self.assertTrue(np.array_equal(ID._accumulate(receiver, order, local), K.accumulate_flow(receiver, order, local)))

    def test_accumulate_inplace_vs_native_lowland(self):
        import terrain_pipeline.drainage as NL
        for seed in (1, 2, 3):
            rng, order, receiver = self._routing(seed)
            for dtype in (np.int32, np.float64):
                area = (rng.integers(0, 2, size=order.size)).astype(dtype)
                a, b = area.copy(), area.copy()
                NL.accumulate_inplace(order, receiver, a)
                K.accumulate_inplace(order, receiver, b)
                self.assertTrue(np.array_equal(a, b))

    def test_accumulate_inplace_equals_copying(self):
        rng, order, receiver = self._routing(9)
        local = rng.random(order.size)
        b = local.copy()
        K.accumulate_inplace(order, receiver, b)
        self.assertTrue(np.array_equal(b, K.accumulate_flow(receiver, order, local)))

    def test_pool_route_vs_route_pool_interval(self):
        from terrain_pipeline import environment_product as WA
        for seed in (1, 2, 3):
            rng, order, receiver = self._routing(seed)
            n = order.size
            labels = np.full(n, -1, np.int64)
            pools = 5
            members = rng.choice(n, size=n // 3, replace=False)
            labels[members] = rng.integers(0, pools, size=members.size)
            anchors = np.full(pools, -1, np.int64)
            for p in range(pools):
                cells = np.flatnonzero(labels == p)
                if cells.size:   # anchor = member latest in flood order
                    rank = np.empty(n, np.int64)
                    rank[order] = np.arange(n)
                    anchors[p] = cells[np.argmax(rank[cells])]
            capacity = rng.random(pools) * 5
            local = rng.random(n)
            s1, s2 = rng.random(pools), None
            s2 = s1.copy()
            s1 = s1.copy()
            f1, r1 = _merged_WA_route_pool_interval(local, order, receiver, labels, anchors, capacity, s1)
            f2, r2 = K.accumulate_with_pools(local, order, receiver, labels, anchors, capacity, s2)
            self.assertTrue(np.array_equal(f1, f2))
            self.assertEqual(r1, r2)
            self.assertTrue(np.array_equal(s1, s2))

    def test_no_pool_path_equals_plain_accumulation(self):
        rng, order, receiver = self._routing(4)
        local = rng.random(order.size)
        labels = np.full(order.size, -1, np.int64)
        flow, retained = K.accumulate_with_pools(local, order, receiver, labels, np.empty(0, np.int64),
                                                 np.empty(0), np.empty(0))
        self.assertEqual(retained, 0.0)
        self.assertTrue(np.array_equal(flow, K.accumulate_flow(receiver, order, local)))

    def test_real_routing_order(self):
        order_path = SAVED / 'native-final-routing-v1' / 'routing' / 'order.npy'
        receiver_path = SAVED / 'native-final-routing-v1' / 'routing' / 'receiver.npy'
        if not (order_path.exists() and receiver_path.exists()):
            self.skipTest('saved native-final-routing-v1 not present')
        order = np.load(order_path, mmap_mode='r')
        receiver = np.load(receiver_path, mmap_mode='r')
        # accumulation reads order from the far end, so a tail slice of the order is a valid sub-problem
        # only when every cell it drains into is inside it; use the full arrays on a thinned local field.
        rng = np.random.default_rng(3)
        local = np.zeros(order.size)
        picks = rng.choice(order.size, size=200000, replace=False)
        local[picks] = rng.random(picks.size) * 1e4
        order, receiver = np.asarray(order), np.asarray(receiver)
        self.assertTrue(np.array_equal(ID._accumulate(receiver, order, local), K.accumulate_flow(receiver, order, local)))


class SectionAndMaskEquivalence(unittest.TestCase):
    def test_native_section(self):
        from terrain_pipeline.new_world_native_network import section
        rng = np.random.default_rng(8)
        q = np.concatenate((np.array([-1.0, 0.0, 1e-9, 1.0, 1e9]), rng.random(500) * 10.0 ** rng.integers(-4, 5, 500)))
        w0, d0 = section(q)
        w1, d1 = K.native_section(q)
        self.assertTrue(np.array_equal(w0, w1))
        self.assertTrue(np.array_equal(d0, d1))

    def test_lake_wet_window_vs_saved_masks(self):
        # (network version, the pool-level product that version reads)
        pairs = [('v2', 'native-event-v1'), ('v3', 'native-event-v2'), ('v4', 'native-event-v3'), ('v5', 'native-event-v3')]
        labels_path = SAVED / 'native-final-routing-v1' / 'derived' / 'pool_index.npy'
        if not labels_path.exists():
            self.skipTest('saved products not present')
        labels = np.load(labels_path, mmap_mode='r').reshape(4096, 4096)
        bed = np.load(SAVED / 'terrain-v3' / 'bed_m.npy', mmap_mode='r')
        ocean = np.load(SAVED / 'terrain-v3' / 'ocean_mask.npy', mmap_mode='r')
        for version, event in pairs:
            saved_path = SAVED / f'native-network-{version}' / 'lake_wet_mask.npy'
            if not saved_path.exists():
                continue
            with self.subTest(version=version):
                levels = np.asarray(np.load(SAVED / event / 'pool_level_m.npy', mmap_mode='r')[2])
                self.assertTrue(np.array_equal(K.lake_wet_window(labels, bed, levels, ocean), np.load(saved_path)))

    def test_lake_wet_window_random_vs_inline_expression(self):
        rng = np.random.default_rng(5)
        labels = rng.integers(-1, 6, size=(40, 40))
        bed = rng.random((40, 40)) * 10
        ocean = rng.random((40, 40)) < 0.2
        levels = rng.random(6) * 10
        levels[2] = np.nan
        z0, z1, x0, x1 = 3, 33, 5, 37
        pool, heights = labels[z0:z1, x0:x1], bed[z0:z1, x0:x1]   # expression copied from native_network_v2.build
        wet = np.zeros(pool.shape, bool)
        present = pool >= 0
        wet[present] = np.isfinite(levels[pool[present]]) & (heights[present] < levels[pool[present]])
        wet &= ~ocean[z0:z1, x0:x1]
        self.assertTrue(np.array_equal(wet, K.lake_wet_window(labels, bed, levels, ocean, window=(z0, z1, x0, x1))))


class DigestEquivalence(unittest.TestCase):
    """The digests live in ``common_infra`` now; this pins them against the modules that still carry one."""

    def test_file_sha256(self):
        import tempfile
        from terrain_pipeline import common_infra as CI
        import terrain_pipeline.drainage as NL
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'blob.bin'
            path.write_bytes(np.random.default_rng(1).bytes(3 * 1024 * 1024 + 17))
            expected = CI.file_sha256(path)
            self.assertEqual(expected, S1._digest(path))
            self.assertEqual(expected, FP.flood_phase_digest(path))
            self.assertEqual(expected, NL.lowland_digest(path))
            empty = Path(tmp) / 'empty.bin'
            empty.write_bytes(b'')
            self.assertEqual(CI.file_sha256(empty), S1._digest(empty))

    def test_canonical_json_digests(self):
        from terrain_pipeline import common_infra as CI
        from terrain_pipeline import hydrology_detail as HD, hydrology_detail_projection as HP
        from terrain_pipeline import hydrology_detail_tributaries as HR
        from terrain_pipeline import td_source as HT
        record = {'b': [1, 2.5, None, True], 'a': {'z': '山川', 'y': -0.0}, 'c': 'x'}
        expected = CI.canonical_json_digest_default(record)
        for module in (HD, HP, HT):
            self.assertEqual(expected, module._digest(record))
        self.assertEqual(CI.json_sha256(record), HR._digest(record))
        self.assertNotEqual(expected, CI.json_sha256(record))

    def test_stage1_identity_json_style_is_not_default_style(self):
        # new_world_stage1._identity uses compact separators; document it matches the compact digest
        from terrain_pipeline import common_infra as CI
        record = {'k': 1, 'identity': 'skip', 'terrain_path': 'skip', 'v': [1, 2]}
        trimmed = {k: v for k, v in record.items() if k not in ('identity', 'terrain_path')}
        self.assertEqual(S1._identity(record), CI.json_sha256(trimmed))


if __name__ == '__main__':
    unittest.main()
