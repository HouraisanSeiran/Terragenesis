"""A3 acceptance: a declared unknown upstream spreads everywhere downstream and nowhere else.

Fixture
-------
One 15x15 pure-synthetic window (no saved page, no generation): a descending ring
ramp that leaves the window through one ``unknown_boundary`` cut, plus two
independent strict-downhill cones with two ``retained`` interior terminals. The
cones give the graph what a degenerate single chain cannot: confluences of up to
eight donors, a real divide between two branches, and -- once a hole is dug -- a
non-empty contaminated set *plus* a disjoint, untouched branch.

Three windows are built by the production entry ``build_strict_topology``:

``clean``      every cell resolved;
``headwater``  one interior cell unresolved, and *no* resolved cell drains into it;
``donor``      one interior cell unresolved that three resolved cells dropped into.

The second and third are what A3 asks for: a ``valid_mask=False`` hole dug in the
middle of an otherwise known graph.

Independence of every expected answer
-------------------------------------
No expectation in this file is computed with the code under test. The expected
incompleteness comes from three independent steps: (1) the unknown seeds are
derived from the validity mask by an eight-neighbour count written here, (2) each
seed's downstream cone is obtained by walking the production receiver **forward**
one cell at a time, and (3) each cell's own catchment is obtained by walking it
**backward** through a donor map built here. ``accumulate_network_discharge`` and
the private ``_complete`` helper of ``tools.native_30m_query`` are deliberately
not imported: reusing them would let a single direction bug agree with itself.
The gates are exercised only as black boxes through ``require_available``,
``query_point``, ``census`` and the diagnostic product's own gate.

Closing the hole legally, instead of feeding an illegal graph
-------------------------------------------------------------
Digging a hole makes the *previous* receiver of that cell stale. This file never
hands such a graph to production and then calls the outcome an unknown-propagation
bug. Instead, every window is rebuilt from its own validity mask, so what reaches
production is the legal irregular graph of that window. ``test_hole_is_closed_
legally_and_never_reached_by_a_receiver`` additionally proves the closure is
explicit: no receiver of a resolved cell is the hole, the hole's former donors
are re-targeted onto resolved cells (the changed set is exactly the hole plus
those donors), and the illegal clean-receiver/holed-mask combination is refused
outright by the production builder -- so "the hole is a hole" can never be
reported as "unknown propagated wrongly". The hole's unknown inflow is declared
through the very ``upstream_unknown_mask`` array the topology stage emits; the
zero stored at the hole in ``local_q_m3_s`` is the storage convention for a
non-participating cell, not a claim that no water entered.

Q is a synthetic field of exact multiples of 1/8, so every catchment sum is exact
in float64 and "bit-identical" below is a real statement, not a tolerance.

What this file does not claim
-----------------------------
That the graph-receiver kernel itself is right (other tests own that), that the
diagnostic product authenticates its inputs, or that any number here is
hydraulically usable: ``hydraulic_ready`` and ``publishable`` stay false.
"""
import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
    build_discharge_product, require_complete_discharge)
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from tools.native_30m_query import ScopeRefusal, census, query_point, require_available


SIDE = 15
MAIN_PIT = (10, 5)
SIDE_PIT = (4, 10)
HEADWATER_HOLE = (12, 5)        # no resolved donor: nothing drains into it
DONOR_HOLE = (8, 3)             # three resolved donors: the legalisation case
ORIGIN_XZ = (100, 200)
WORLD_SEED = 20261020           # CONTRIBUTING.md: the fixed continuous baseline
SOURCE_SHA = 'a' * 64           # placeholder identity for a synthetic window
DIAGNOSTIC_INTERVAL = (3600.0, 7200.0)


def _flat(cell):
    return cell[0] * SIDE + cell[1]


MAIN_FLAT = _flat(MAIN_PIT)
SIDE_FLAT = _flat(SIDE_PIT)
HEADWATER_FLAT = _flat(HEADWATER_HOLE)
DONOR_FLAT = _flat(DONOR_HOLE)

# Spatial scopes answered through the joint graph, i.e. every scope that a declared
# unknown upstream has to gate. ``terrain_surface`` is deliberately absent: an
# unknown upstream says nothing about a known elevation.
GRAPH_SCOPES = ('d8_topology', 'local_runoff', 'diagnostic_discharge', 'design_discharge',
                'channel_section', 'hydraulics', 'bed_change', 'solid_inventory')


# --------------------------------------------------------------------------- #
# independent helpers: nothing below calls the module under test
# --------------------------------------------------------------------------- #
def _ring_seeds(valid):
    """A resolved cell with an unresolved neighbour declares an unknown upstream."""
    valid = np.asarray(valid, bool)
    rows, columns = valid.shape
    neighbours = np.zeros(valid.shape, np.int8)
    for drow in (-1, 0, 1):
        for dcolumn in (-1, 0, 1):
            if (drow, dcolumn) == (0, 0):
                continue
            shifted = np.zeros(valid.shape, bool)
            top, bottom = max(0, drow), rows + min(0, drow)
            left, right = max(0, dcolumn), columns + min(0, dcolumn)
            shifted[top:bottom, left:right] = valid[top - drow:bottom - drow,
                                                   left - dcolumn:right - dcolumn]
            neighbours += shifted
    return valid & (neighbours != 8)


def _neighbour_points(cell):
    """The eight cells around ``cell`` that lie inside the window."""
    result = np.zeros((SIDE, SIDE), bool)
    for drow in (-1, 0, 1):
        for dcolumn in (-1, 0, 1):
            if (drow, dcolumn) == (0, 0):
                continue
            row, column = cell[0] + drow, cell[1] + dcolumn
            if 0 <= row < SIDE and 0 <= column < SIDE:
                result[row, column] = True
    return result


def _downstream_union(receiver, seed_ids):
    """Every cell reachable from a seed by following ``receiver`` forward.

    A deliberately separate traversal from the production wave walk: this one
    starts at each seed and follows one path at a time, so a direction mistake in
    the module cannot agree with itself here.
    """
    flat = np.asarray(receiver).ravel()
    reached = np.zeros(flat.size, bool)
    for start in seed_ids:
        cell = int(start)
        while cell >= 0 and not reached[cell]:
            reached[cell] = True
            cell = int(flat[cell])
    return reached.reshape(np.asarray(receiver).shape)


def _donors(receiver):
    """receiver value -> donor cells, built from scratch."""
    flat = np.asarray(receiver).ravel()
    donors = {}
    for cell, target in enumerate(flat):
        if target >= 0:
            donors.setdefault(int(target), []).append(cell)
    return donors


def _upstream_union(receiver, root):
    """Every cell that drains into ``root``, including ``root`` itself."""
    flat = np.asarray(receiver).ravel()
    donors = _donors(receiver)
    reached = np.zeros(flat.size, bool)
    reached[root] = True
    stack = [root]
    while stack:
        for donor in donors.get(stack.pop(), ()):
            if not reached[donor]:
                reached[donor] = True
                stack.append(donor)
    return reached.reshape(np.asarray(receiver).shape)


def _bits(array):
    """Raw bytes of an array, so "unchanged" means bit-identical, not "close"."""
    return np.ascontiguousarray(array).tobytes()


def _points(ids):
    result = np.zeros((SIDE, SIDE), bool)
    result.ravel()[list(ids)] = True
    return result


# --------------------------------------------------------------------------- #
# synthetic field, validity windows and the query environment
# --------------------------------------------------------------------------- #
def _ring_ramp(side):
    """The window edge as one descending path, so the cut drains to one cell."""
    path = [(0, column) for column in range(side)]
    path += [(row, side - 1) for row in range(1, side)]
    path += [(side - 1, column) for column in range(side - 2, -1, -1)]
    path += [(row, 0) for row in range(side - 2, 0, -1)]
    return path


def _base_field():
    """A descending ring ramp plus two independent cones with retained pits."""
    rows, columns = np.indices((SIDE, SIDE))
    border = np.minimum(np.minimum(rows, columns),
                        np.minimum(SIDE - 1 - rows, SIDE - 1 - columns))
    field = np.zeros((SIDE, SIDE), np.float64)
    for step, (row, column) in enumerate(_ring_ramp(SIDE)):
        field[row, column] = 40.0 - 0.5 * step
    field[border == 1] = 200.0          # a rim: the ring path can only drain outwards
    inside = border >= 2
    to_main = np.maximum(np.abs(rows - MAIN_PIT[0]), np.abs(columns - MAIN_PIT[1]))
    to_side = np.maximum(np.abs(rows - SIDE_PIT[0]), np.abs(columns - SIDE_PIT[1]))
    cones = np.minimum(to_main, to_side).astype(np.float64)
    field[inside] = 100.0 + 3.0 * cones[inside] + 0.13 * rows[inside] + 0.07 * columns[inside]
    return field


def _local_q(valid):
    """Exact multiples of 1/8, all positive, nineteen distinct magnitudes."""
    index = np.arange(valid.size).reshape(valid.shape)
    magnitude = ((index * 37) % 19 + 1) * 0.125
    return np.where(valid, magnitude, 0.0).astype(np.float64)


def _environment(hole=None):
    """One saved-window environment whose graph is the legal D8 graph of its mask."""
    field = _base_field()
    valid = np.ones((SIDE, SIDE), bool)
    if hole is not None:
        valid[hole] = False
        field[hole] = np.nan       # the unresolved cell carries no elevation
    topology = build_strict_topology(field, valid)
    receiver = topology['receiver']
    local = _local_q(valid)
    catchment = _upstream_union(receiver, MAIN_FLAT)
    event_cells = np.flatnonzero(valid)
    diagnostic = build_discharge_product(
        receiver, local, valid, topology['terminal_kind'], topology['upstream_unknown_mask'],
        origin_native_cells=list(ORIGIN_XZ), world_seed=WORLD_SEED,
        interval_seconds=list(DIAGNOSTIC_INTERVAL), source_sha256=SOURCE_SHA,
        forcing_semantics='synthetic unknown-cone acceptance window')
    return {
        'arrays': {
            'source.npz': {'field': field, 'resolved_mask': valid.copy(),
                           'origin_native_xz': np.array(ORIGIN_XZ, np.int64)},
            'topology.npz': {name: topology[name] for name in (
                'receiver', 'valid_mask', 'terminal_kind', 'upstream_unknown_mask')},
            'selection.npz': {
                'catchment_mask': catchment,
                'flowline_mask': _points([MAIN_FLAT]),
                'stem_flat_cells': np.array([MAIN_FLAT], np.int64)},
            'section.npz': {
                'node_cell_ids': np.array([MAIN_FLAT, SIDE_FLAT], np.int64),
                'width_m': np.array([30.0, 24.0]),
                'normal_depth_m': np.array([0.5, 0.25]),
                'source_slope_per_m': np.array([0.02, 0.03]),
                'design_q_m3_s': np.array([7.5, 6.0])},
            'reach_context.npz': {
                'node_slope_per_m': np.array([0.019, 0.029]),
                'lateral_cell_counts': np.array([1, 1], np.int64)},
            'event.npz': {
                'active_cells': event_cells,
                'local_q_m3_s': np.vstack([local.ravel()[event_cells],
                                           local.ravel()[event_cells] * 0.5]),
                'time_edges_s': np.array([0.0, 3600.0, 7200.0])},
        },
        'manifest': {
            'identity_sha256': SOURCE_SHA,
            'source_records': [{'native_origin_xz': list(ORIGIN_XZ),
                                'shape_zx': [SIDE, SIDE]}],
            'parameters': {'world_seed': WORLD_SEED},
            'stage_identities': {'source_assembly': SOURCE_SHA}},
        'json_records': {'selection.json': {'chosen': {
            'subwindow_rc': [0, SIDE, 0, SIDE],
            'terminal_flat_cell': MAIN_FLAT,
            'catchment_cells': int(catchment.sum())}}},
        'diagnostic': diagnostic,
        'dynamics': {'arrays': {
            'time_seconds': np.array([0.0, 3600.0]),
            'water_volume_m3': np.array([[0.0, 0.0], [750.0, 600.0]]),
            'node_bed_m': np.array([[2.0, 1.5], [1.99, 1.49]]),
            'mobile_solid_m3': np.array([[0.0, 0.0], [0.5, 0.25]]),
            'loose_solid_m3': np.array([[1.0, 2.0], [1.5, 2.5]]),
            'rock_removed_m3': np.array([[0.0, 0.0], [0.0, 0.0]])}},
    }


class UnknownConeAcceptance(unittest.TestCase):
    """A3: the contaminated set is exactly everything downstream of a declared seed."""

    @classmethod
    def setUpClass(cls):
        cls.clean = _environment()
        cls.headwater = _environment(HEADWATER_HOLE)
        cls.donor = _environment(DONOR_HOLE)

    # -- shared reading of one window ---------------------------------------- #
    @staticmethod
    def _parts(env):
        topology = env['arrays']['topology.npz']
        valid = topology['valid_mask']
        seeds = topology['upstream_unknown_mask']
        receiver = topology['receiver']
        affected = _downstream_union(receiver, np.flatnonzero(seeds.ravel())) & valid
        return receiver, valid, seeds, affected

    def _refuse(self, env, scope, requested, reason, **kwargs):
        with self.assertRaises(ScopeRefusal) as caught:
            require_available(env, scope, requested, **kwargs)
        self.assertEqual(caught.exception.reason_code, reason)

    # -- guards: the fixture is not a degenerate chain ------------------------ #
    def test_fixture_forks_merges_and_keeps_an_untouched_branch(self):
        for label, env in (('clean', self.clean), ('headwater', self.headwater),
                           ('donor', self.donor)):
            with self.subTest(window=label):
                receiver, valid, seeds, affected = self._parts(env)
                kinds = env['arrays']['topology.npz']['terminal_kind']
                retained = sorted(np.flatnonzero(kinds.ravel() == 'retained').tolist())
                self.assertEqual(retained, sorted([MAIN_FLAT, SIDE_FLAT]))
                self.assertEqual(int((kinds.ravel() == 'open_outflow').sum()), 0)
                # confluences: many donors per node, not a single chain
                fan = np.array([len(v) for v in _donors(receiver).values()])
                self.assertGreaterEqual(int(fan.max()), 8)
                self.assertGreaterEqual(int((fan >= 3).sum()), 5)
                # two branches, each with a real catchment, and they do not overlap
                main_up = _upstream_union(receiver, MAIN_FLAT)
                side_up = _upstream_union(receiver, SIDE_FLAT)
                self.assertGreater(int(main_up.sum()), 20)
                self.assertGreater(int(side_up.sum()), 20)
                self.assertFalse(bool((main_up & side_up).any()))
                # the hole sits in the main branch and leaves the side branch alone
                if label != 'clean':
                    self.assertTrue(bool(affected.any()))
                    self.assertFalse(bool((affected & side_up).any()))

    def test_unknown_seeds_are_exactly_the_undeclared_ring(self):
        for label, env in (('clean', self.clean), ('headwater', self.headwater),
                           ('donor', self.donor)):
            with self.subTest(window=label):
                _, valid, seeds, _ = self._parts(env)
                self.assertGreater(int(seeds.sum()), 0)
                self.assertFalse(bool((seeds & ~valid).any()))
                np.testing.assert_array_equal(seeds, _ring_seeds(valid))
        for label, env, hole in (('headwater', self.headwater, HEADWATER_HOLE),
                                 ('donor', self.donor, DONOR_HOLE)):
            with self.subTest(hole=label):
                _, valid, seeds, _ = self._parts(env)
                _, _, clean_seeds, _ = self._parts(self.clean)
                added = seeds & ~clean_seeds
                # digging the hole adds a seed ring around it and removes none
                np.testing.assert_array_equal(added, _neighbour_points(hole) & valid)
                np.testing.assert_array_equal(seeds & clean_seeds, clean_seeds)
                self.assertEqual(int(seeds.sum()), int(clean_seeds.sum()) + int(added.sum()))

    # -- A3 (1): affected = exactly all, and only, the cells below a seed ----- #
    def test_unknown_reaches_every_downstream_cell_and_nothing_else(self):
        for label, env in (('clean', self.clean), ('headwater', self.headwater),
                           ('donor', self.donor)):
            with self.subTest(window=label):
                receiver, valid, seeds, affected = self._parts(env)
                complete = env['diagnostic']['arrays']['complete_mask']
                total = int(valid.sum())
                self.assertGreater(int(affected.sum()), 0)
                self.assertGreater(int((valid & ~affected).sum()), 0)
                np.testing.assert_array_equal(complete, valid & ~affected)
                self.assertEqual(int(complete.sum()) + int(affected.sum()), total)
                # nothing else: no cell that keeps a seed-free path is incomplete
                untouched = np.flatnonzero((valid & ~affected).ravel())
                for cell in untouched[::max(1, untouched.size // 8)]:
                    self.assertFalse(bool((_upstream_union(receiver, int(cell)) & seeds).any()))
                # the declared cut(s) are terminals, never zero-filled interior cells
                kinds = env['arrays']['topology.npz']['terminal_kind']
                cut = np.flatnonzero(kinds.ravel() == 'unknown_boundary')
                expected_cuts = 1 if label != 'donor' else 2
                self.assertEqual(cut.size, expected_cuts)
                self.assertTrue(bool((receiver.ravel()[cut] == -1).all()))
                self.assertTrue(bool(seeds.ravel()[cut].all()))
                self.assertTrue(bool(affected.ravel()[cut].all()))
                # every resolved cell that still drains is an interior cell, so the
                # only non-interior labels are the two retained pits and the cuts
                draining = valid.ravel() & (receiver.ravel() >= 0)
                self.assertTrue(bool((kinds.ravel()[draining] == 'interior').all()))
                self.assertFalse(bool((kinds.ravel() == 'open_outflow').any()))

    # -- A3 (2): the known answer excludes the unknown contribution ----------- #
    def test_known_discharge_is_a_partial_sum_never_the_complete_answer(self):
        receiver, valid, seeds, affected = self._parts(self.headwater)
        holed = self.headwater['diagnostic']['arrays']
        clean_arrays = self.clean['diagnostic']['arrays']
        holed_local = holed['local_q_m3_s']
        clean_local = clean_arrays['local_q_m3_s']
        known = holed['known_routed_q_m3_s']
        clean_known = clean_arrays['known_routed_q_m3_s']
        # guard: the synthetic Q is non-zero, non-constant, exact in float64
        self.assertGreater(float(holed_local[valid].min()), 0.0)
        self.assertGreater(np.unique(holed_local[valid]).size, 5)
        self.assertGreater(float(clean_local.ravel()[HEADWATER_FLAT]), 0.0)
        # the hole is the only cell whose receiver moved, so the arithmetic is exact
        differ = np.flatnonzero(receiver.ravel() != self.clean['arrays'][
            'topology.npz']['receiver'].ravel())
        np.testing.assert_array_equal(differ, np.array([HEADWATER_FLAT]))
        # the retained outlet of the contaminated branch carries a *partial* number
        self.assertTrue(bool(affected.ravel()[MAIN_FLAT]))
        self.assertGreater(float(known.ravel()[MAIN_FLAT]), 0.0)
        self.assertLess(float(known.ravel()[MAIN_FLAT]), float(clean_known.ravel()[MAIN_FLAT]))
        self.assertEqual(float(clean_known.ravel()[MAIN_FLAT]),
                         float(known.ravel()[MAIN_FLAT])
                         + float(clean_local.ravel()[HEADWATER_FLAT]))
        # and that number is exactly the sum over its own *known* catchment
        sample = [MAIN_FLAT, SIDE_FLAT] + np.flatnonzero(affected.ravel())[
            ::max(1, int(affected.sum()) // 4)].tolist()[:4]
        for cell in sample:
            closure = _upstream_union(receiver, int(cell))
            self.assertEqual(float(known.ravel()[cell]),
                             float(np.sum(holed_local[closure])))
        # the ledger still balances: the unknown part sits at the declared cut
        ledger = self.headwater['diagnostic']['metadata']['ledger']
        self.assertEqual(ledger['residual_m3_s'], 0.0)
        self.assertGreater(ledger['unknown_pending_m3_s'], 0.0)
        self.assertEqual(ledger['input_total_m3_s'],
                         float(np.sum(holed_local[valid])))

    def test_product_counts_agree_with_the_independent_cone(self):
        _, valid, seeds, affected = self._parts(self.headwater)
        meta = self.headwater['diagnostic']['metadata']
        self.assertEqual(meta['counts']['incomplete_valid_cells'], int(affected.sum()))
        self.assertEqual(meta['counts']['unknown_upstream_seed_cells'], int(seeds.sum()))
        self.assertEqual(meta['counts']['valid_cells'], int(valid.sum()))
        result = census(self.headwater)
        self.assertEqual(result['upstream_unknown_seed_cells'], int(seeds.sum()))
        self.assertEqual(result['incomplete_valid_cells'], int(affected.sum()))
        self.assertEqual(result['terminal_kind']['retained'], 2)
        self.assertEqual(result['terminal_kind']['unknown_boundary'], 1)

    # -- A3 (3): a whole request is refused, never partly zero-filled --------- #
    def test_affected_and_mixed_requests_are_refused_whole(self):
        _, valid, seeds, affected = self._parts(self.headwater)
        affected_ids = np.flatnonzero(affected.ravel())
        untouched_ids = np.flatnonzero((valid & ~affected).ravel())
        self.assertTrue(untouched_ids.size > 100)
        for cell in affected_ids:
            with self.subTest(cell=int(cell), scope='d8_topology'):
                self._refuse(self.headwater, 'd8_topology', _points([cell]), 'upstream_unknown')
                self._refuse(self.headwater, 'diagnostic_discharge', _points([cell]),
                             'upstream_unknown')
        for cell in affected_ids[::max(1, affected_ids.size // 3)]:
            for scope in GRAPH_SCOPES:
                with self.subTest(cell=int(cell), scope=scope):
                    self._refuse(self.headwater, scope, _points([cell]), 'upstream_unknown')
        # the whole contaminated set at once, and one mixed request, are refused whole
        self._refuse(self.headwater, 'diagnostic_discharge', affected, 'upstream_unknown')
        mixed = _points([int(untouched_ids[0]), int(affected_ids[0])])
        for scope in GRAPH_SCOPES:
            with self.subTest(scope=scope, request='mixed'):
                self._refuse(self.headwater, scope, mixed, 'upstream_unknown')
        # the product gate refuses the same requests, and never returns a partial array
        with self.assertRaisesRegex(ValueError, 'declared unknown upstream'):
            require_complete_discharge(self.headwater['diagnostic'], mixed)
        with self.assertRaisesRegex(ValueError, 'declared unknown upstream'):
            require_complete_discharge(self.headwater['diagnostic'], affected)
        with self.assertRaisesRegex(ValueError, 'not zero-filled'):
            require_complete_discharge(self.headwater['diagnostic'],
                                       _points([HEADWATER_FLAT]))
        # an unaffected request through the very same gates still answers
        answer = require_complete_discharge(self.headwater['diagnostic'],
                                           _points(untouched_ids[:3]))
        self.assertEqual(answer.size, 3)
        self.assertTrue(np.isfinite(answer).all())

    # -- A3 (4): upstream and the disjoint branch keep Q bit for bit ---------- #
    def test_unaffected_and_upstream_branches_keep_q_bit_for_bit(self):
        receiver, valid, seeds, affected = self._parts(self.headwater)
        clean_valid, clean_affected = self._parts(self.clean)[1], self._parts(self.clean)[3]
        side_up = _upstream_union(receiver, SIDE_FLAT)
        self.assertFalse(bool((affected & side_up).any()))
        untouched = valid & ~affected
        # every cell the independent cone keeps clean is clean in the clean window too
        self.assertFalse(bool((untouched & ~(clean_valid & ~clean_affected)).any()))
        mask = untouched
        holed_q = require_available(self.headwater, 'diagnostic_discharge', mask)
        clean_q = require_available(self.clean, 'diagnostic_discharge', mask)
        self.assertEqual(_bits(holed_q), _bits(clean_q))
        np.testing.assert_array_equal(holed_q,
                                      self.headwater['diagnostic']['arrays'][
                                          'known_routed_q_m3_s'][mask])
        # not merely "the same as production's other run": each answer must equal the
        # independent catchment sum over exactly the cells that drain into that cell
        holed_local = self.headwater['diagnostic']['arrays']['local_q_m3_s']
        order = np.flatnonzero(mask.ravel())
        expected = np.array([float(np.sum(holed_local[_upstream_union(receiver, int(cell))]))
                             for cell in order], np.float64)
        self.assertEqual(_bits(holed_q), _bits(expected))
        self.assertGreater(float(expected.min()), 0.0)
        self.assertGreater(np.unique(expected).size, 5)
        # the untouched branch answers end to end, and its outlet Q is unchanged
        self.assertEqual(_bits(require_available(self.headwater, 'diagnostic_discharge',
                                                 side_up)),
                         _bits(require_available(self.clean, 'diagnostic_discharge', side_up)))
        self.assertEqual(_bits(require_available(self.headwater, 'diagnostic_discharge',
                                                 _points([SIDE_FLAT]))),
                         _bits(require_available(self.clean, 'diagnostic_discharge',
                                                 _points([SIDE_FLAT]))))
        # the fields a caller also reads from a clean cell do not move either
        for scope in ('d8_topology', 'local_runoff'):
            with self.subTest(scope=scope):
                self.assertEqual(_bits(require_available(self.headwater, scope, mask)),
                                 _bits(require_available(self.clean, scope, mask)))
        # dynamics stay readable on the untouched node, and are the same numbers
        for scope in ('hydraulics', 'bed_change', 'solid_inventory', 'design_discharge',
                      'channel_section'):
            with self.subTest(scope=scope):
                self.assertEqual(_bits(require_available(self.headwater, scope,
                                                         _points([SIDE_FLAT]))),
                                 _bits(require_available(self.clean, scope,
                                                         _points([SIDE_FLAT]))))
        # the contaminated outlet is refused by the same scopes (no silent number)
        for scope in ('design_discharge', 'channel_section', 'hydraulics', 'bed_change',
                      'solid_inventory'):
            with self.subTest(scope=scope, cell='contaminated outlet'):
                self._refuse(self.headwater, scope, _points([MAIN_FLAT]), 'upstream_unknown')

    # -- terrain elevation is not part of the unknown ------------------------- #
    def test_terrain_surface_still_answers_known_elevation(self):
        _, valid, seeds, affected = self._parts(self.headwater)
        field = self.headwater['arrays']['source.npz']['field']
        known_cells = valid & ~affected
        for mask, label in ((affected, 'contaminated'), (known_cells, 'unaffected')):
            with self.subTest(cells=label):
                values = require_available(self.headwater, 'terrain_surface', mask)
                self.assertEqual(_bits(values), _bits(field[mask]))
                self.assertTrue(np.isfinite(values).all())
        # a contaminated point still answers its elevation, but not its discharge
        cell = int(np.flatnonzero(affected.ravel())[0])
        row, column = divmod(cell, SIDE)
        point = query_point(self.headwater, int(ORIGIN_XZ[0]) + column,
                            int(ORIGIN_XZ[1]) + row, native=True)
        self.assertEqual(point['elevation_m'], float(field[row, column]))
        self.assertEqual(point['values'], [float(field[row, column])])
        with self.assertRaises(ScopeRefusal) as caught:
            query_point(self.headwater, int(ORIGIN_XZ[0]) + column,
                        int(ORIGIN_XZ[1]) + row, native=True, scope='diagnostic_discharge')
        self.assertEqual(caught.exception.reason_code, 'upstream_unknown')
        # the hole itself is never invented into a terrain answer
        self.assertTrue(np.isnan(field[HEADWATER_HOLE]))
        self._refuse(self.headwater, 'terrain_surface', _points([HEADWATER_FLAT]),
                     'unresolved_border')

    # -- the hole is closed legally, never fed in as an illegal graph --------- #
    def test_hole_is_closed_legally_and_never_reached_by_a_receiver(self):
        clean_receiver = self.clean['arrays']['topology.npz']['receiver']
        for label, env, hole, hole_flat in (
                ('headwater', self.headwater, HEADWATER_HOLE, HEADWATER_FLAT),
                ('donor', self.donor, DONOR_HOLE, DONOR_FLAT)):
            with self.subTest(hole=label):
                receiver, valid, seeds, affected = self._parts(env)
                self.assertFalse(bool(valid.ravel()[hole_flat]))
                self.assertEqual(int(receiver.ravel()[hole_flat]), -1)
                live = valid.ravel() & (receiver.ravel() >= 0)
                targets = receiver.ravel()[live]
                self.assertFalse(bool((targets == hole_flat).any()))
                self.assertTrue(bool(valid.ravel()[targets].all()))
                # a resolved cell with no receiver is a declared terminal, never an
                # interior cell whose water silently vanished into the hole
                kinds = env['arrays']['topology.npz']['terminal_kind'].ravel()
                open_ended = valid.ravel() & (receiver.ravel() < 0)
                self.assertTrue(bool(open_ended.any()))
                self.assertFalse(bool((kinds[open_ended] == 'interior').any()))
                # explicit closure: exactly the hole and its former donors change target
                former_donors = set(_donors(clean_receiver).get(hole_flat, ()))
                changed = set(np.flatnonzero(
                    receiver.ravel() != clean_receiver.ravel()).tolist())
                self.assertEqual(changed, {hole_flat} | former_donors)
                self.assertFalse(bool((seeds & ~valid).any()))
                if label == 'donor':
                    self.assertEqual(len(former_donors), 3)
                else:
                    self.assertEqual(former_donors, set())
                # every former donor is legally closed: re-targeted onto a resolved
                # cell, or declared a cut -- never left pointing into the hole
                for donor in sorted(former_donors):
                    with self.subTest(donor=int(donor)):
                        self.assertTrue(bool(valid.ravel()[donor]))
                        target = int(receiver.ravel()[donor])
                        self.assertNotEqual(target, hole_flat)
                        if target < 0:
                            self.assertEqual(str(kinds[donor]), 'unknown_boundary')
                            self.assertTrue(bool(seeds.ravel()[donor]))
                        else:
                            self.assertTrue(bool(valid.ravel()[target]))
                            self.assertEqual(str(kinds[donor]), 'interior')
                adopted = [d for d in former_donors if int(receiver.ravel()[d]) >= 0]
                relabelled = [d for d in former_donors if str(kinds[d]) == 'unknown_boundary']
                self.assertEqual(len(adopted) + len(relabelled), len(former_donors))
        # the illegal combination is refused outright, not reinterpreted as unknown
        holed = self.headwater['arrays']['topology.npz']
        local = _local_q(holed['valid_mask'])
        with self.assertRaisesRegex(ValueError,
                                    'inactive cells must have zero local Q and receiver -1'):
            build_discharge_product(clean_receiver, local, holed['valid_mask'],
                                    holed['terminal_kind'], holed['upstream_unknown_mask'],
                                    origin_native_cells=list(ORIGIN_XZ), world_seed=WORLD_SEED,
                                    interval_seconds=list(DIAGNOSTIC_INTERVAL),
                                    source_sha256=SOURCE_SHA,
                                    forcing_semantics='illegal graph negative control')
        # and the hole asked for as a point is refused for what it is
        self._refuse(self.headwater, 'd8_topology', _points([HEADWATER_FLAT]),
                     'unresolved_border')


if __name__ == '__main__':
    unittest.main()
