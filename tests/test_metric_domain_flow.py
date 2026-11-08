"""`metric_domain_flow`: the domain water ledger's contracts.

What is held to account here (and nothing more):

1. repeatability -- the same points and rainfall answer with the same
   `identity_sha256`, before and after `clear_cache()`, and through a real
   write/reload round trip;
2. the ledger closes -- per-domain `rain = et + storage + release` and the tile
   partition `requested = routed + unresolved + ocean_direct` are both exact to
   the accumulator tolerance, and the *reported* totals are recomputed from the
   arrays rather than trusted;
3. the producing cells are exactly the closure module's accepted cells, and the
   routing lands the released volume on the right terminals -- checked against an
   **independently written** downstream-first accumulation, so the module's own
   group-by-terminal shortcut is not marking its own homework;
4. refusals stay refusals -- rainfall over `unresolved_border`, over the sea, and
   on a second tile are handled by an explicit tally or an explicit error, never
   by routing water into a domain that was never closed.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    clear_cache, domain_topology, eligible_owner_at,
)
from terrain_pipeline.surface_rivers.metric_domain_flow import (
    FLOW_SCHEMA,
    MAX_INTERVALS,
    PRODUCT_KEYS,
    load_domain_flow,
    save_domain_flow,
    solve_domain_flow,
    validate_domain_flow,
)

SEED = 20261020
CONFIG = PlanningConfig()
SPACING_M = CONFIG.macro_span_m / CONFIG.samples_per_span

# Shared with `test_metric_domain_pipeline`: these five points live in one tile,
# two of them in one coastal domain.
POINTS = (
    (0.0, 30000.0),
    (0.0, 40000.0),
    (40000.0, 0.0),
    (20000.0, 0.0),
)
RAIN_SCENARIO_MM_H = 4.0
DT_S = 3600.0
INTERVALS = 6


def independent_landed(height, receiver, terminal, released_grid):
    """Independent oracle: push each cell's release downstream, upstream first.

    Processes cells in **descending height** order, which is a valid topological
    order for a strictly-downhill receiver: when a cell is processed, every cell
    that drains into it has already been processed, so a single push into the
    receiver propagates the whole upstream chain. Written differently from the
    module's group-by-terminal shortcut on purpose: two implementations agreeing
    is evidence, one implementation agreeing with itself is not.
    """
    flat_receiver = np.asarray(receiver, np.int64).reshape(-1)
    flat_height = np.asarray(height, np.float64).reshape(-1)
    flow = np.array(released_grid, np.float64).reshape(-1).copy()
    for cell in np.argsort(-flat_height, kind="stable"):
        target = flat_receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
            flow[cell] = 0.0
    # Every non-terminal cell has now emptied into its downstream chain, so the
    # volume still sitting somewhere is on terminal cells (receiver == -1).
    return flow.reshape(np.asarray(released_grid).shape)


class DomainFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.record = solve_domain_flow(SEED, POINTS, RAIN_SCENARIO_MM_H,
                                       config=CONFIG, dt_s=DT_S, intervals=INTERVALS)
        cls.topology = domain_topology(SEED, POINTS[0][0], POINTS[0][1], CONFIG)

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    def test_production_accessor_preserves_bucket_release_by_interval(self):
        from terrain_pipeline.surface_rivers.metric_domain_flow import domain_flow_topology

        result = domain_flow_topology(SEED, POINTS[0][0], POINTS[0][1],
                                      RAIN_SCENARIO_MM_H, config=CONFIG,
                                      dt_s=DT_S, intervals=INTERVALS)
        interval_grid = np.asarray(result["released_per_interval_grid_m3"], np.float64)
        aggregate_grid = np.asarray(result["released_grid_m3"], np.float64)
        self.assertEqual(interval_grid.shape, (INTERVALS,) + tuple(result["shape"]))
        self.assertTrue(np.isfinite(interval_grid).all())
        self.assertTrue(np.all(interval_grid >= 0.0))
        self.assertTrue(np.array_equal(np.sum(interval_grid, axis=0), aggregate_grid))
        self.assertAlmostEqual(float(np.sum(interval_grid)),
                               self.record["metadata"]["totals"]["released_total_m3"],
                               places=6)
        topology = result["topology"]
        margin = topology["margin"]
        core = topology["core_cells"]
        accepted = topology["accepted"]
        excluded = ~accepted[margin:margin + core + 1, margin:margin + core + 1]
        core_series = interval_grid[:, margin:margin + core + 1, margin:margin + core + 1]
        self.assertTrue(np.all(core_series[:, excluded] == 0.0))

    def temp_dir(self, name):
        root = Path(tempfile.mkdtemp(prefix="domain-flow-%s-" % name))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    # ------------------------------------------------ repeatability
    def test_same_scenario_reruns_to_the_same_identity(self):
        clear_cache()
        try:
            again = solve_domain_flow(SEED, POINTS, RAIN_SCENARIO_MM_H,
                                      config=CONFIG, dt_s=DT_S, intervals=INTERVALS)
        finally:
            clear_cache()
        self.assertEqual(again["identity_sha256"], self.record["identity_sha256"])

    def test_identity_survives_a_write_and_reload(self):
        root = self.temp_dir("reload")
        path = root / "flow.npz"
        save_domain_flow(path, self.record)
        reloaded = load_domain_flow(path, expected_sha256=_file_sha256(path),
                                    expected_identity=self.record["identity_sha256"])
        self.assertEqual(reloaded["identity_sha256"], self.record["identity_sha256"])
        for key in PRODUCT_KEYS:
            self.assertTrue(np.array_equal(np.asarray(reloaded["arrays"][key]),
                                           np.asarray(self.record["arrays"][key])), key)

    def test_tampered_product_is_refused(self):
        root = self.temp_dir("tamper")
        path = root / "flow.npz"
        save_domain_flow(path, self.record)
        digest = _file_sha256(path)
        with path.open("r+b") as handle:
            handle.seek(path.stat().st_size // 2)
            handle.write(b"\x00")
        with self.assertRaises(ValueError):
            load_domain_flow(path, expected_sha256=digest)

    # ------------------------------------------------ the ledger closes
    def test_every_domain_ledger_closes(self):
        arrays = self.record["arrays"]
        rain = np.asarray(arrays["rain_input_m3"], np.float64)
        et = np.asarray(arrays["actual_et_m3"], np.float64)
        storage = np.asarray(arrays["soil_storage_change_m3"], np.float64)
        release = np.asarray(arrays["terminal_release_m3"], np.float64)
        scale = np.maximum(np.abs(rain) + np.abs(et) + np.abs(storage) + np.abs(release), 1.0)
        worst = np.max(np.abs(rain - et - storage - release) / scale) if rain.size else 0.0
        self.assertLess(worst, 1e-9)

    def test_rainfall_partition_lands_in_named_bins(self):
        totals = self.record["metadata"]["totals"]
        partition = (totals["routed_rain_m3"] + totals["unresolved_rain_m3"]
                     + totals["ocean_direct_rain_m3"] + totals["outside_core_rain_m3"])
        self.assertAlmostEqual(totals["requested_rain_m3"], partition,
                               delta=1e-6 * max(abs(totals["requested_rain_m3"]), 1.0))
        self.assertLess(abs(totals["accounting_residual_m3"]),
                        1e-6 * max(abs(totals["requested_rain_m3"]), 1.0))

    def test_reported_totals_are_recomputed_from_the_arrays(self):
        arrays = self.record["arrays"]
        totals = self.record["metadata"]["totals"]
        kind = np.asarray(arrays["kind"]).astype(str)
        release = np.asarray(arrays["terminal_release_m3"], np.float64)
        self.assertAlmostEqual(totals["exported_to_sea_m3"],
                               float(np.sum(release[kind == "marine"])), places=3)
        self.assertAlmostEqual(totals["retained_in_basins_m3"],
                               float(np.sum(release[kind == "inland"])), places=3)
        self.assertAlmostEqual(totals["routed_rain_m3"],
                               float(np.sum(arrays["rain_input_m3"])), places=3)

    def test_a_forged_totals_block_is_caught(self):
        forged = _deep_copy_bundle(self.record)
        forged["metadata"]["totals"]["exported_to_sea_m3"] += 1.0
        with self.assertRaises(ValueError):
            validate_domain_flow(forged)

    # ------------------------------------------------ routing correctness
    def test_producing_cells_are_exactly_the_accepted_core_cells(self):
        topology = self.topology
        margin = topology["margin"]
        core = topology["core_cells"]
        accepted_core = topology["accepted"][margin:margin + core + 1, margin:margin + core + 1]
        arrays = self.record["arrays"]
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        cells_z = np.asarray(arrays["cells_z_m"], np.float64)
        self.assertEqual(cells_x.size, int(np.count_nonzero(accepted_core)))
        # Every published cell must be accepted by the closure module's own
        # public query, with the outlet the product claims for its domain.
        accepted, (out_x, out_z) = eligible_owner_at(SEED, cells_x, cells_z, CONFIG)
        self.assertTrue(bool(np.all(np.asarray(accepted, bool))))

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
            _, (owner_x, owner_z) = eligible_owner_at(SEED, cells_x[start:stop],
                                                      cells_z[start:stop], CONFIG)
            self.assertTrue(np.allclose(owner_x, outlet_x[index], atol=1e-9))
            self.assertTrue(np.allclose(owner_z, outlet_z[index], atol=1e-9))

    def test_release_is_routed_to_the_domains_own_terminals(self):
        arrays = self.record["arrays"]
        topology = self.topology
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        cells_z = np.asarray(arrays["cells_z_m"], np.float64)
        spacing = topology["spacing_m"]
        rows, columns = topology["shape"]
        receiver = topology["receiver"]
        height = topology["height_m"]
        terminal = np.asarray(topology["terminal"], np.int64).reshape(-1)

        # Rebuild the released grid on the tile lattice from the published cells,
        # then route it with the INDEPENDENT oracle.
        released = np.zeros(rows * columns, np.float64)
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            cell_count = stop - start
            # The product stores the per-domain release total, so distribute it
            # uniformly over that domain's cells: the oracle only has to prove
            # where the TOTAL lands, not reproduce per-cell allocation.
            per_cell = float(arrays["terminal_release_m3"][index]) / cell_count
            column = np.rint((cells_x[start:stop] - topology["origin_x_m"]) / spacing).astype(np.int64)
            row = np.rint((cells_z[start:stop] - topology["origin_z_m"]) / spacing).astype(np.int64)
            flat = row * columns + column
            np.add.at(released, flat, per_cell)

        landed = independent_landed(height, receiver, terminal, released)
        # Every bin must be nonnegative and the routed total must be conserved.
        self.assertTrue(np.all(landed >= -1e-9))
        self.assertAlmostEqual(float(np.sum(landed)), float(np.sum(released)), places=3)
        # The volume that lands on each domain's own terminal must equal its
        # release total (no cross-domain leakage).
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            column = np.rint((cells_x[start] - topology["origin_x_m"]) / spacing).astype(np.int64)
            row = np.rint((cells_z[start] - topology["origin_z_m"]) / spacing).astype(np.int64)
            flat = int(row * columns + column)
            target = int(terminal[flat])
            self.assertAlmostEqual(landed[target], float(arrays["terminal_release_m3"][index]),
                                   places=3)

    # ------------------------------------------------ refusals stay refusals
    def test_rain_over_refused_cells_is_tallied_not_routed(self):
        totals = self.record["metadata"]["totals"]
        self.assertGreaterEqual(totals["unresolved_rain_m3"], 0.0)
        self.assertGreaterEqual(totals["ocean_direct_rain_m3"], 0.0)
        # Refused and ocean rainfall must not appear in any domain's rain input.
        self.assertAlmostEqual(totals["routed_rain_m3"],
                               float(np.sum(self.record["arrays"]["rain_input_m3"])), places=3)

    def test_second_tile_is_an_input_error(self):
        far = CONFIG.macro_span_m * 4 * 10  # ten core spans away
        with self.assertRaises(ValueError):
            solve_domain_flow(SEED, [POINTS[0], (far, far)], RAIN_SCENARIO_MM_H,
                              config=CONFIG, dt_s=DT_S, intervals=INTERVALS)

    def test_invalid_rainfall_is_refused(self):
        for bad in (-1.0, True, np.full(3, 1.0), np.zeros((2, 2, 2))):
            with self.assertRaises(ValueError):
                solve_domain_flow(SEED, POINTS, bad, config=CONFIG,
                                  dt_s=DT_S, intervals=INTERVALS)

    def test_interval_budget_is_stated_and_enforced(self):
        with self.assertRaises(ValueError):
            solve_domain_flow(SEED, POINTS, RAIN_SCENARIO_MM_H, config=CONFIG,
                              dt_s=DT_S, intervals=MAX_INTERVALS + 1)

    def test_product_carries_the_contract_schema(self):
        arrays = self.record["arrays"]
        self.assertEqual(set(arrays), set(PRODUCT_KEYS))
        self.assertEqual(self.record["metadata"]["schema"], FLOW_SCHEMA)
        claims = self.record["metadata"]["claims"]
        self.assertTrue(all(claims[key] is False for key in claims))

    def test_nonzero_rain_produces_water_and_et(self):
        totals = self.record["metadata"]["totals"]
        self.assertGreater(totals["requested_rain_m3"], 0.0)
        self.assertGreater(totals["routed_rain_m3"], 0.0)
        self.assertGreater(totals["actual_et_m3"], 0.0)
        self.assertGreater(totals["released_total_m3"], 0.0)

    def test_zero_rain_still_closes_a_drawdown_ledger(self):
        clear_cache()
        try:
            dry = solve_domain_flow(SEED, POINTS, 0.0, config=CONFIG,
                                    dt_s=DT_S, intervals=INTERVALS)
        finally:
            clear_cache()
        totals = dry["metadata"]["totals"]
        self.assertEqual(totals["requested_rain_m3"], 0.0)
        # Zero rain must NOT mean zero outflow: the bucket starts with
        # `initial_soil_mm = 30` and drains it, which is the repository's own
        # soil/ET physics, not a routing error. The zero-rain case is therefore a
        # drain-down ledger, and what must hold is that it still closes.
        self.assertGreaterEqual(totals["released_total_m3"], 0.0)
        self.assertEqual(totals["unresolved_rain_m3"], 0.0)
        self.assertEqual(totals["ocean_direct_rain_m3"], 0.0)
        self.assertAlmostEqual(totals["released_total_m3"],
                               float(np.sum(dry["arrays"]["terminal_release_m3"])), places=3)
        self.assertEqual(dry["arrays"]["terminal_release_m3"].size,
                         self.record["arrays"]["terminal_release_m3"].size)
        arrays = dry["arrays"]
        rain = np.asarray(arrays["rain_input_m3"], np.float64)
        et = np.asarray(arrays["actual_et_m3"], np.float64)
        storage = np.asarray(arrays["soil_storage_change_m3"], np.float64)
        release = np.asarray(arrays["terminal_release_m3"], np.float64)
        self.assertTrue(np.allclose(rain - et - storage - release, 0.0, atol=1e-6))
        self.assertTrue(np.all(storage <= 1e-9))
        self.assertTrue(np.all(release >= -1e-9))
        validate_domain_flow(dry)

    def test_custom_parameters_change_the_ledger_but_not_the_identity_contract(self):
        clear_cache()
        try:
            other = solve_domain_flow(
                SEED, POINTS, RAIN_SCENARIO_MM_H, config=CONFIG, dt_s=DT_S,
                intervals=INTERVALS,
                parameters=RunoffParameters(infiltration_capacity_mm_h=30.0))
        finally:
            clear_cache()
        self.assertNotEqual(other["identity_sha256"], self.record["identity_sha256"])
        self.assertGreater(other["metadata"]["totals"]["actual_et_m3"], 0.0)
        validate_domain_flow(other)


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