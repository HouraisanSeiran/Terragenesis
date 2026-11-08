"""`metric_domain_sediment`: the domain sediment ledger's contracts.

What is held to account here (and nothing more):

1. repeatability -- the same points and yield parameters answer with the same
   `identity_sha256`, before and after `clear_cache()`, and through a real
   write/reload round trip;
2. both ledgers close -- per-domain `weathered = entrained + store_change` and
   `entrained = deposited + delivered`, and the tile residual `entrained =
   deposited + delivered + stranded` are exact to the accumulator tolerance, with
   the *reported* totals recomputed from the arrays rather than trusted;
3. the source and the initial mobile inventory exist **only** on the producing
   cells -- the regression that matters, because a tile-wide initial store used to
   open the tile ledger by exactly its own volume (`initial_mobile_m > 0` was a
   guaranteed `ValueError`);
4. the delivered volume is attributed to the domains that claim the terminals, so
   `stranded_on_refused_m3` is the *unclaimed* remainder, not the whole delivery --
   checked against an **independently written** upstream-first routing push, so the
   module's own group-by-terminal shortcut is not marking its own homework;
5. refusals stay refusals -- a second tile is an explicit error, the ocean and the
   refused set receive no source, and the ledger writes no terrain.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    clear_cache, domain_topology, eligible_owner_at,
)
from terrain_pipeline.surface_rivers.metric_domain_sediment import (
    ALGORITHM,
    MAX_INTERVALS,
    PRODUCT_KEYS,
    SEDIMENT_SCHEMA,
    SedimentYieldParameters,
    load_domain_sediment,
    save_domain_sediment,
    solve_domain_sediment,
    validate_domain_sediment,
)

SEED = 20261020
CONFIG = PlanningConfig()
SPACING_M = CONFIG.macro_span_m / CONFIG.samples_per_span

# Shared with `test_metric_domain_flow`: these four points live in one tile, and
# two of them in one coastal domain.
POINTS = (
    (0.0, 30000.0),
    (0.0, 40000.0),
    (40000.0, 0.0),
    (20000.0, 0.0),
)
INTERVALS = 4


def independent_push(height, receiver, load_flat):
    """Independent oracle: push each cell's load downstream, upstream first.

    Processes cells in **descending height** order, which is a valid topological
    order for a strictly-downhill receiver: when a cell is processed, every cell
    that drains into it has already been processed, so one push per cell
    propagates the whole upstream chain. Written differently from the module's
    loop-and-group shortcut on purpose -- two implementations agreeing is
    evidence, one implementation agreeing with itself is not.
    """
    flat_height = np.asarray(height, np.float64).reshape(-1)
    flat_receiver = np.asarray(receiver, np.int64).reshape(-1)
    load = np.array(load_flat, np.float64).copy()
    for cell in np.argsort(-flat_height, kind="stable"):
        target = flat_receiver[cell]
        if target >= 0:
            load[target] += load[cell]
            load[cell] = 0.0
    # Every non-terminal cell has now emptied into its downstream chain, so the
    # volume still sitting somewhere is on terminal cells (receiver == -1).
    return load


class DomainSedimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.record = solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                           intervals=INTERVALS)
        cls.topology = domain_topology(SEED, POINTS[0][0], POINTS[0][1], CONFIG)

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    def temp_dir(self, name):
        root = Path(tempfile.mkdtemp(prefix="domain-sediment-%s-" % name))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    # ------------------------------------------------ repeatability
    def test_same_scenario_reruns_to_the_same_identity(self):
        clear_cache()
        try:
            again = solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                          intervals=INTERVALS)
        finally:
            clear_cache()
        self.assertEqual(again["identity_sha256"], self.record["identity_sha256"])

    def test_identity_survives_a_write_and_reload(self):
        root = self.temp_dir("reload")
        path = root / "sediment.npz"
        save_domain_sediment(path, self.record)
        reloaded = load_domain_sediment(path, expected_sha256=_file_sha256(path),
                                        expected_identity=self.record["identity_sha256"])
        self.assertEqual(reloaded["identity_sha256"], self.record["identity_sha256"])
        for key in PRODUCT_KEYS:
            self.assertTrue(np.array_equal(np.asarray(reloaded["arrays"][key]),
                                           np.asarray(self.record["arrays"][key])), key)

    def test_tampered_product_is_refused(self):
        root = self.temp_dir("tamper")
        path = root / "sediment.npz"
        save_domain_sediment(path, self.record)
        digest = _file_sha256(path)
        with path.open("r+b") as handle:
            handle.seek(path.stat().st_size // 2)
            handle.write(b"\x00")
        with self.assertRaises(ValueError):
            load_domain_sediment(path, expected_sha256=digest)

    def test_saving_never_overwrites(self):
        root = self.temp_dir("exists")
        path = root / "sediment.npz"
        save_domain_sediment(path, self.record)
        with self.assertRaises(Exception):
            save_domain_sediment(path, self.record)

    # ------------------------------------------------ both ledgers close
    def test_every_domain_source_ledger_closes(self):
        arrays = self.record["arrays"]
        weathered = np.asarray(arrays["weathered_m3"], np.float64)
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        store = np.asarray(arrays["store_change_m3"], np.float64)
        scale = np.maximum(weathered + entrained + np.abs(store), 1.0)
        worst = (np.max(np.abs(weathered - entrained - store) / scale)
                 if weathered.size else 0.0)
        self.assertLess(worst, 1e-9)

    def test_every_domain_routing_ledger_closes(self):
        arrays = self.record["arrays"]
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        deposited = np.asarray(arrays["deposited_m3"], np.float64)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        scale = np.maximum(entrained + deposited + delivered, 1.0)
        worst = (np.max(np.abs(entrained - deposited - delivered) / scale)
                 if entrained.size else 0.0)
        self.assertLess(worst, 1e-9)

    def test_tile_routing_ledger_closes(self):
        totals = self.record["metadata"]["totals"]
        tolerance = 1e-6 * max(abs(totals["entrained_total_m3"]), 1.0)
        self.assertLess(abs(totals["routing_residual_m3"]), tolerance)
        self.assertGreaterEqual(totals["stranded_on_refused_m3"], 0.0)

    def test_tile_source_ledger_closes(self):
        totals = self.record["metadata"]["totals"]
        tolerance = 1e-6 * max(abs(totals["weathered_total_m3"]), 1.0)
        self.assertLess(abs(totals["source_residual_m3"]), tolerance)

    def test_reported_totals_are_recomputed_from_the_arrays(self):
        arrays = self.record["arrays"]
        totals = self.record["metadata"]["totals"]
        kind = np.asarray(arrays["kind"]).astype(str)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        for name, array in (("weathered_total_m3", "weathered_m3"),
                            ("entrained_total_m3", "entrained_m3"),
                            ("deposited_total_m3", "deposited_m3"),
                            ("delivered_total_m3", "delivered_m3"),
                            ("store_change_total_m3", "store_change_m3")):
            self.assertAlmostEqual(totals[name], float(np.sum(arrays[array])), places=3)
        self.assertAlmostEqual(totals["delivered_to_sea_m3"],
                               float(np.sum(delivered[kind == "marine"])), places=3)
        self.assertAlmostEqual(totals["delivered_to_basins_m3"],
                               float(np.sum(delivered[kind == "inland"])), places=3)
        self.assertAlmostEqual(totals["delivered_to_sea_m3"] + totals["delivered_to_basins_m3"],
                               totals["delivered_total_m3"], places=3)

    def test_a_forged_totals_block_is_caught(self):
        for key, delta in (("delivered_total_m3", 1.0),
                           ("source_residual_m3", 1.0),
                           ("routing_residual_m3", 1.0),
                           ("delivered_to_sea_m3", 1.0)):
            forged = _deep_copy_bundle(self.record)
            forged["metadata"]["totals"][key] += delta
            with self.assertRaises(ValueError):
                validate_domain_sediment(forged)

    def test_a_forged_ledger_array_is_caught(self):
        # Rewriting an array without re-deriving the identity must be refused, so a
        # silently edited ledger cannot pass as a product.
        forged = _deep_copy_bundle(self.record)
        forged["arrays"]["delivered_m3"] = np.asarray(
            forged["arrays"]["delivered_m3"], np.float64) * 1.5
        with self.assertRaises(ValueError):
            validate_domain_sediment(forged)

    # ------------------------------------------------ the store is core-only
    def test_a_nonzero_initial_store_is_not_leaked_outside_the_core(self):
        """Regression: a tile-wide initial store used to open the tile ledger.

        Before the fix the whole tile carried `initial_mobile_m`, including the
        margin and the ocean, and those cells entrained and routed the inventory.
        The tile residual came out at `1.38e10 m3` at `initial_mobile_m = 0.05`
        while the per-domain entrainment sums fell `9.45e10 m3` short of the tile
        total -- i.e. the product the module now rejects by construction used to be
        unforgeable but wrong.
        """
        clear_cache()
        try:
            seeded = solve_domain_sediment(
                SEED, POINTS, config=CONFIG, intervals=INTERVALS,
                parameters=SedimentYieldParameters(initial_mobile_m=0.05))
        finally:
            clear_cache()
        validate_domain_sediment(seeded)
        totals = seeded["metadata"]["totals"]
        arrays = seeded["arrays"]
        # The declared initial inventory must show up in the totals, and the store
        # must run DOWN (entrainment strips an inventory that is not replenished
        # beyond the weathering input).
        self.assertGreater(totals["initial_mobile_total_m3"], 0.0)
        self.assertLess(totals["store_change_total_m3"], 0.0)
        self.assertLess(abs(totals["routing_residual_m3"]),
                        1e-6 * max(abs(totals["entrained_total_m3"]), 1.0))
        # A seeded ledger must entrain strictly more than the unseeded one, and the
        # per-domain sums must match the tile totals.
        self.assertGreater(totals["entrained_total_m3"],
                           self.record["metadata"]["totals"]["entrained_total_m3"])
        for name in ("entrained_m3", "deposited_m3", "delivered_m3"):
            self.assertAlmostEqual(
                float(np.sum(arrays[name])),
                {"entrained_m3": totals["entrained_total_m3"],
                 "deposited_m3": totals["deposited_total_m3"],
                 "delivered_m3": totals["delivered_total_m3"]}[name], places=3)

    def test_the_margin_carries_no_source(self):
        # `weathered_m3` is the declared weathering on the producing cells only; a
        # margin cell has no source, exactly as it receives no rainfall in the
        # water ledger. The check is that the tile weathered total equals the sum of
        # the published per-domain figures (nothing outside the core contributed).
        arrays = self.record["arrays"]
        totals = self.record["metadata"]["totals"]
        self.assertAlmostEqual(float(np.sum(arrays["weathered_m3"])),
                               totals["weathered_total_m3"], places=3)
        self.assertGreater(totals["weathered_total_m3"], 0.0)

    def test_excluded_cells_contribute_nothing(self):
        topology = self.topology
        margin = topology["margin"]
        core = topology["core_cells"]
        arrays = self.record["arrays"]
        totals = self.record["metadata"]["totals"]
        excluded_ocean = totals["excluded_ocean_core_cells"]
        excluded_refused = totals["excluded_unresolved_core_cells"]
        self.assertEqual(totals["accepted_cells"], int(np.sum(arrays["cell_count"])))
        core_total = int(np.count_nonzero(
            topology["accepted"][margin:margin + core + 1, margin:margin + core + 1])
            + np.count_nonzero(
                topology["ocean"][margin:margin + core + 1, margin:margin + core + 1]
                & ~topology["unresolved"][margin:margin + core + 1, margin:margin + core + 1])
            + np.count_nonzero(
                topology["unresolved"][margin:margin + core + 1, margin:margin + core + 1]))
        self.assertEqual(totals["accepted_cells"] + excluded_ocean + excluded_refused,
                         core_total)

    # ------------------------------------------------ routing correctness
    def test_producing_cells_are_exactly_the_accepted_core_cells(self):
        topology = self.topology
        margin = topology["margin"]
        core = topology["core_cells"]
        accepted_core = topology["accepted"][margin:margin + core + 1, margin:margin + core + 1]
        arrays = self.record["arrays"]
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        self.assertEqual(cells_x.size, int(np.count_nonzero(accepted_core)))

    def test_published_cells_belong_to_the_claimed_domain(self):
        arrays = self.record["arrays"]
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        cells_z = np.asarray(arrays["cells_z_m"], np.float64)
        outlet_x = np.asarray(arrays["outlet_x_m"], np.float64)
        outlet_z = np.asarray(arrays["outlet_z_m"], np.float64)
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            accepted, (owner_x, owner_z) = eligible_owner_at(
                SEED, cells_x[start:stop], cells_z[start:stop], CONFIG)
            self.assertTrue(bool(np.all(np.asarray(accepted, bool))))
            self.assertTrue(np.allclose(owner_x, outlet_x[index], atol=1e-9))
            self.assertTrue(np.allclose(owner_z, outlet_z[index], atol=1e-9))

    def test_delivery_and_deposition_are_attributed_to_the_right_domain(self):
        """Attribution, checked against an independently derived oracle.

        The tile ledger proves the totals close; this proves *where* they land. The
        oracle is deliberately not the module's loop: with `intervals = 1` and a
        uniform source the per-cell entrainment has a closed form
        (`clip(gain * slope, 0, 1) * source_depth`), so the auditor re-derives the
        slope from the published raw face, re-derives the deposited/landed split
        with a different traversal, and compares both the per-domain delivery and
        the per-domain deposition. A uniform source is the only injection for which
        the closed form is exact without replaying the store recurrence.
        """
        topology = self.topology
        spacing = topology["spacing_m"]
        rows, columns = topology["shape"]
        height = np.asarray(topology["height_m"], np.float64)
        receiver = np.asarray(topology["receiver"], np.int64).reshape(-1)
        accepted = np.asarray(topology["accepted"], bool).reshape(-1)
        terminal = np.asarray(topology["terminal"], np.int64).reshape(-1)
        margin = int(topology["margin"])
        core = int(topology["core_cells"])

        source = 0.0002  # m per interval, the declared default weathering depth
        gain = 150.0     # the declared default slope gain
        retention = 0.3  # the declared default deposit fraction

        clear_cache()
        try:
            record = solve_domain_sediment(
                SEED, POINTS, config=CONFIG, intervals=1,
                parameters=SedimentYieldParameters(
                    weathered_m_per_interval=source, slope_gain=gain,
                    deposit_fraction=retention))
        finally:
            clear_cache()

        # --- the oracle: re-derive the slope on the raw face, then push with retention
        dh_dz, dh_dx = np.gradient(height, spacing, spacing)
        slope = np.hypot(dh_dx, dh_dz)
        load = np.zeros(rows * columns, np.float64)
        core_slice = np.s_[margin:margin + core + 1, margin:margin + core + 1]
        accepted_core = accepted.reshape(rows, columns)[core_slice]
        producing_rows, producing_columns = np.nonzero(accepted_core)
        producing_flat = (producing_rows + margin) * columns + (producing_columns + margin)
        fraction = np.clip(gain * slope[core_slice][accepted_core], 0.0, 1.0)
        np.add.at(load, producing_flat, fraction * source * spacing * spacing)

        landed = np.zeros(rows * columns, np.float64)
        deposited = np.zeros(rows * columns, np.float64)
        landed_flat = np.zeros(rows * columns, np.float64)
        flat_height = height.reshape(-1)
        for cell in np.argsort(-flat_height, kind="stable"):
            value = load[cell]
            if value <= 0.0 and receiver[cell] < 0:
                landed_flat[cell] += value
                continue
            if accepted[cell]:
                settle = retention * value
                deposited[cell] += settle
                value -= settle
            if receiver[cell] >= 0:
                load[receiver[cell]] += value
            else:
                landed_flat[cell] += value

        # landed/deposited are accumulated on the PUBLISHED cells only; the oracle's
        # margin contributions are compared at tile level below.
        arrays = record["arrays"]
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        cells_z = np.asarray(arrays["cells_z_m"], np.float64)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        deposited_published = np.asarray(arrays["deposited_m3"], np.float64)
        entrained = np.asarray(arrays["entrained_m3"], np.float64)

        # The per-cell entrainment must match the closed form, so the oracle's own
        # input is not the module's output re-used.
        self.assertAlmostEqual(float(np.sum(entrained)),
                               float(np.sum(fraction * source * spacing * spacing)),
                               places=3)

        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            column = np.rint((cells_x[start:stop] - topology["origin_x_m"]) / spacing).astype(np.int64)
            row = np.rint((cells_z[start:stop] - topology["origin_z_m"]) / spacing).astype(np.int64)
            flat = row * columns + column
            # One physical terminal per domain, so any published cell identifies it.
            target = int(terminal[flat[0]])
            self.assertTrue(np.all(terminal[flat] == target))
            self.assertAlmostEqual(float(landed_flat[target]), float(delivered[index]), places=3)
            # Deposition is summed over every accepted cell that drains to this
            # domain's terminal -- including the tile margin, which the product
            # attributes by terminal for exactly this reason.
            self.assertAlmostEqual(float(np.sum(deposited[accepted & (terminal == target)])),
                                   float(deposited_published[index]), places=3)

        # No domain's load may land on a terminal it does not claim.
        claimed = np.zeros(rows * columns, bool)
        for index in range(offsets.size - 1):
            start = int(offsets[index])
            if start == int(offsets[index + 1]):
                continue
            column = np.rint((cells_x[start] - topology["origin_x_m"]) / spacing).astype(np.int64)
            row = np.rint((cells_z[start] - topology["origin_z_m"]) / spacing).astype(np.int64)
            claimed[int(terminal[row * columns + column])] = True
        stranded = float(np.sum(landed_flat[~claimed]))
        totals = record["metadata"]["totals"]
        self.assertAlmostEqual(stranded, totals["stranded_on_refused_m3"], places=3)
        # And the oracle's own atlas closes: entrained = deposited + delivered + stranded.
        self.assertAlmostEqual(totals["entrained_total_m3"],
                               float(np.sum(deposited)) + float(np.sum(landed_flat)),
                               places=3)
        self.assertAlmostEqual(totals["deposited_total_m3"], float(np.sum(deposited)), places=3)
        self.assertAlmostEqual(totals["delivered_total_m3"], float(np.sum(landed_flat)), places=3)

    def test_deposition_is_attributed_to_the_terminals_domain(self):
        # Deposition happens on every accepted cell along the chain, INCLUDING the
        # margin. Those margin cells belong to no published domain, so summing
        # deposition over published cells alone would leak it. The gate is that the
        # tile total is not below the published per-domain sum.
        arrays = self.record["arrays"]
        totals = self.record["metadata"]["totals"]
        self.assertGreaterEqual(totals["deposited_total_m3"],
                                float(np.sum(arrays["deposited_m3"])) - 1e-6)
        self.assertAlmostEqual(totals["deposited_total_m3"],
                               float(np.sum(arrays["deposited_m3"])), places=3)

    # ------------------------------------------------ refusals stay refusals
    def test_second_tile_is_an_input_error(self):
        far = CONFIG.macro_span_m * 4 * 10  # ten core spans away
        with self.assertRaises(ValueError):
            solve_domain_sediment(SEED, [POINTS[0], (far, far)], config=CONFIG,
                                  intervals=INTERVALS)

    def test_no_points_is_an_input_error(self):
        with self.assertRaises(ValueError):
            solve_domain_sediment(SEED, [], config=CONFIG, intervals=INTERVALS)

    def test_interval_budget_is_stated_and_enforced(self):
        for bad in (0, MAX_INTERVALS + 1, 2.5, True):
            with self.assertRaises(ValueError):
                solve_domain_sediment(SEED, POINTS, config=CONFIG, intervals=bad)

    def test_parameter_bounds_are_enforced(self):
        for bad in (dict(weathered_m_per_interval=-1.0),
                    dict(slope_gain=-1.0),
                    dict(deposit_fraction=1.5),
                    dict(deposit_fraction=-0.1),
                    dict(initial_mobile_m=-1.0),
                    dict(weathered_m_per_interval=float("nan")),
                    dict(slope_gain=float("inf"))):
            with self.assertRaises(ValueError):
                SedimentYieldParameters(**bad)

    def test_misshaped_source_injection_is_refused_not_broadcast(self):
        # A mis-shaped source field would quietly move the whole sediment budget, so
        # it is an input error rather than a silent broadcast.
        for bad in (np.zeros(3), np.zeros((2, 2)), np.zeros((5, 5, 5)), True):
            with self.assertRaises(ValueError):
                solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                      intervals=INTERVALS, source_m_per_interval=bad)

    def test_a_scalar_or_grid_source_injection_is_accepted(self):
        topology = self.topology
        core = topology["core_cells"]
        clear_cache()
        try:
            grid = solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                         intervals=INTERVALS,
                                         source_m_per_interval=np.full(
                                             (core + 1, core + 1), 0.0002))
            scalar = solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                           intervals=INTERVALS,
                                           source_m_per_interval=0.0002)
        finally:
            clear_cache()
        # A uniform grid with exactly the default depth must reproduce the default
        # run byte for byte -- the injection point is the parameter, not a new truth.
        self.assertEqual(grid["identity_sha256"], self.record["identity_sha256"])
        self.assertEqual(scalar["identity_sha256"], self.record["identity_sha256"])

    def test_product_carries_the_contract_schema(self):
        arrays = self.record["arrays"]
        self.assertEqual(set(arrays), set(PRODUCT_KEYS))
        self.assertEqual(self.record["metadata"]["schema"], SEDIMENT_SCHEMA)
        self.assertEqual(self.record["metadata"]["algorithm"], ALGORITHM)
        claims = self.record["metadata"]["claims"]
        self.assertTrue(all(claims[key] is False for key in claims))

    def test_nonzero_yield_produces_and_routes_sediment(self):
        totals = self.record["metadata"]["totals"]
        self.assertGreater(totals["weathered_total_m3"], 0.0)
        self.assertGreater(totals["entrained_total_m3"], 0.0)
        self.assertGreater(totals["deposited_total_m3"], 0.0)
        self.assertGreater(totals["delivered_total_m3"], 0.0)
        self.assertGreater(totals["entrainment_saturated_fraction"], 0.0)

    def test_zero_yield_still_closes_a_null_ledger(self):
        # With no weathering and no initial inventory there is nothing to move: the
        # honest answer is an all-zero ledger that still closes, not a silent skip.
        clear_cache()
        try:
            null = solve_domain_sediment(
                SEED, POINTS, config=CONFIG, intervals=INTERVALS,
                parameters=SedimentYieldParameters(weathered_m_per_interval=0.0))
        finally:
            clear_cache()
        totals = null["metadata"]["totals"]
        self.assertEqual(totals["weathered_total_m3"], 0.0)
        self.assertEqual(totals["entrained_total_m3"], 0.0)
        self.assertEqual(totals["deposited_total_m3"], 0.0)
        self.assertEqual(totals["delivered_total_m3"], 0.0)
        self.assertEqual(totals["stranded_on_refused_m3"], 0.0)
        self.assertEqual(null["arrays"]["delivered_m3"].size,
                         self.record["arrays"]["delivered_m3"].size)
        validate_domain_sediment(null)

    def test_custom_parameters_change_the_ledger_but_not_the_contract(self):
        clear_cache()
        try:
            other = solve_domain_sediment(
                SEED, POINTS, config=CONFIG, intervals=INTERVALS,
                parameters=SedimentYieldParameters(deposit_fraction=0.6))
        finally:
            clear_cache()
        self.assertNotEqual(other["identity_sha256"], self.record["identity_sha256"])
        # A larger deposit fraction must retain more and deliver less, not merely
        # answer with different bytes.
        self.assertGreater(other["metadata"]["totals"]["deposited_total_m3"],
                           self.record["metadata"]["totals"]["deposited_total_m3"])
        self.assertLess(other["metadata"]["totals"]["delivered_total_m3"],
                        self.record["metadata"]["totals"]["delivered_total_m3"])
        validate_domain_sediment(other)

    def test_domains_are_keyed_by_outlet_world_coordinate(self):
        arrays = self.record["arrays"]
        outlet_x = np.asarray(arrays["outlet_x_m"], np.float64)
        outlet_z = np.asarray(arrays["outlet_z_m"], np.float64)
        keys = np.stack([outlet_x, outlet_z], axis=1)
        self.assertEqual(np.unique(keys, axis=0).shape[0], keys.shape[0])
        self.assertEqual(outlet_x.size, int(self.record["metadata"]["domain_count"]))

    def test_kind_is_marine_or_inland_only(self):
        kind = np.asarray(self.record["arrays"]["kind"]).astype(str)
        self.assertTrue(set(kind.tolist()).issubset({"marine", "inland"}))
        self.assertGreater(int(np.count_nonzero(kind == "inland")), 0)

    def test_the_ledger_writes_no_terrain(self):
        # The module reports volumes; it must not publish a bed change or a derived
        # surface. The observable contract is the claims block plus the absence of
        # any bed/height key in the array set.
        self.assertTrue(all(key not in PRODUCT_KEYS for key in
                            ("bed_change_m", "height_m", "base_height_m", "surface_m")))
        self.assertIs(self.record["metadata"]["claims"]["terrain_feedback_applied"], False)


class DomainSedimentInputIndependenceTests(unittest.TestCase):
    """The ledger must depend on the world coordinate, not on the point list."""

    def test_a_superset_of_points_answers_with_the_same_domains(self):
        clear_cache()
        try:
            base = solve_domain_sediment(SEED, POINTS[:1], config=CONFIG,
                                         intervals=INTERVALS)
            more = solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                          intervals=INTERVALS)
        finally:
            clear_cache()
        self.assertEqual(base["arrays"]["outlet_x_m"].size,
                         more["arrays"]["outlet_x_m"].size)
        # Same tile, same seed: the domain set must be a property of the tile.
        base_keys = np.stack([base["arrays"]["outlet_x_m"],
                              base["arrays"]["outlet_z_m"]], axis=1)
        more_keys = np.stack([more["arrays"]["outlet_x_m"],
                              more["arrays"]["outlet_z_m"]], axis=1)
        self.assertTrue(np.array_equal(base_keys, more_keys))

    def test_reversed_point_order_answers_identically(self):
        clear_cache()
        try:
            forward = solve_domain_sediment(SEED, POINTS, config=CONFIG,
                                             intervals=INTERVALS)
            backward = solve_domain_sediment(SEED, tuple(reversed(POINTS)), config=CONFIG,
                                              intervals=INTERVALS)
        finally:
            clear_cache()
        self.assertEqual(forward["identity_sha256"], backward["identity_sha256"])


class DomainSedimentParameterIdentityTests(unittest.TestCase):
    def test_parameter_identity_is_reported_and_sensitive(self):
        base = SedimentYieldParameters()
        other = SedimentYieldParameters(deposit_fraction=0.31)
        self.assertNotEqual(base, other)
        self.assertEqual(base, SedimentYieldParameters())


class DomainSedimentProductNameTests(unittest.TestCase):
    def test_product_name_encodes_the_outlet_identity(self):
        from terrain_pipeline.surface_rivers.metric_domain_sediment import (
            domain_sediment_name,
        )
        self.assertIn("1200000", domain_sediment_name(1200000.0, 400000.0))
        self.assertIn("400000", domain_sediment_name(1200000.0, 400000.0))
        self.assertIn(SEDIMENT_SCHEMA, domain_sediment_name(1200000.0, 400000.0))


class DomainSedimentConfigIdentityTests(unittest.TestCase):
    def test_cache_argument_is_refused_rather_than_silently_ignored(self):
        # The contract's discipline: an argument that does not participate in the
        # identity must not be silently ignored, because a caller would then believe
        # their cache is in effect.
        clear_cache()
        try:
            with self.assertRaises(TypeError):
                solve_domain_sediment(SEED, POINTS, config=CONFIG, intervals=INTERVALS,
                                      cache={})
        finally:
            clear_cache()


def _file_sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _deep_copy_bundle(record):
    arrays = {key: np.array(value, copy=True) for key, value in record["arrays"].items()}
    metadata = json.loads(json.dumps(record["metadata"]))
    return {"arrays": arrays, "metadata": metadata,
            "identity_sha256": record["identity_sha256"]}


if __name__ == "__main__":
    unittest.main()
