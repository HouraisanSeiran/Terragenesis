"""P6.2 tests: the on-demand river domain pipeline's contracts.

`metric_domain_closure` proves window-independent *functions*; this module turns
them into *products*. These tests hold the products to the two things the
contract makes testable (`.scratch/river-infinite-world/pipeline-spec.md` 5 and 7):

1. repeatability -- the same coordinate answers with the same `identity_sha256`
   in the same process, in another order, after `clear_cache()`, and after a
   write/reload round trip through a real file;
2. refusal bookkeeping -- `accepted + refused == requested`, every refusal's
   `reason` is one of `ClosureRegion.classify`'s five labels verbatim, and
   `resolved` is False exactly for `unresolved_border` / `out_of_tile`.

Everything is measured end to end on a handful of world coordinates: the closure
module's tile is 4L = 1280 km wide, so any small neighbourhood of points shares
one tile and a run stays fast.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig, coarse_condition_field
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    clear_cache, eligible_owner_at, resolve_points, territory_of,
)
from terrain_pipeline.surface_rivers.metric_domain_pipeline import (
    ACCEPTED_REASONS,
    INDEX_SCHEMA,
    LIMITATIONS,
    REASON_ORDER,
    SCHEMA,
    UNRESOLVED_REASONS,
    config_identity,
    domain_product_name,
    load_domain_product,
    node_spacing_m,
    resolve_domain_products,
)

SEED = 20261020
CONFIG = PlanningConfig()
SPACING_M = CONFIG.macro_span_m / CONFIG.samples_per_span
ROOT = Path(__file__).resolve().parents[1]

# Three land points and two sea points. All five share the
# closure tile that contains them, so the batch builds exactly once.
POINTS = (
    (0.0, 30000.0),
    (0.0, 40000.0),
    (40000.0, 0.0),
    (0.0, 0.0),          # ocean  (resolved, no domain)
    (20000.0, 0.0),      # ocean  (resolved, no domain)
)
# A point whose drainage ends at an inland minimum (a legitimate finite domain)
# and one inside that domain's outlet cell itself.
INLAND_POINTS = ((280000.0, 310000.0), (280001.0, 310001.0))
INLAND_OUTLET = (280000.0, 310000.0)

CLI = ROOT / "tools" / "generate_river_domains.py"


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


class MetricDomainPipelineTests(unittest.TestCase):
    """A whole batch costs one tile build, so `setUpClass` builds it once."""

    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.batch = resolve_domain_products(SEED, POINTS, config=CONFIG)

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    def temp_dir(self, name):
        root = Path(tempfile.mkdtemp(prefix="p62-%s-" % name))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def rerun(self, points, spacing_m=None, output_dir=None):
        """Re-run with a cold closure cache, so nothing is answered from memory."""
        clear_cache()
        try:
            return resolve_domain_products(SEED, points, config=CONFIG,
                                           spacing_m=spacing_m, output_dir=output_dir)
        finally:
            clear_cache()

    # ------------------------------------------- 5.1 same coordinate, rerun
    def test_same_points_rerun_keep_the_same_identity(self):
        """Contract 5.1: the digest is a pure function of the world coordinate."""
        again = self.rerun(POINTS)
        self.assertEqual(again.outlet_keys, self.batch.outlet_keys)
        self.assertEqual(again.product_set_sha256, self.batch.product_set_sha256)
        for key in self.batch.outlet_keys:
            self.assertEqual(again.domains[key].identity_sha256,
                             self.batch.domains[key].identity_sha256,
                             "domain %s changed its identity between runs" % (key,))
            self.assertNotEqual(self.batch.domains[key].identity_sha256, "")
            self.assertEqual(len(self.batch.domains[key].identity_sha256), 64)

    def test_identity_survives_clear_cache(self):
        """Contract 5.4: the in-memory tile cache speeds things up, nothing else."""
        clear_cache()
        try:
            after = self.batch  # built before the clear above
            third = resolve_domain_products(SEED, list(reversed(POINTS)), config=CONFIG)
        finally:
            clear_cache()
        for key in self.batch.outlet_keys:
            self.assertEqual(third.domains[key].identity_sha256,
                             after.domains[key].identity_sha256)

    def test_another_process_reproduces_the_identity(self):
        """Contract 5.3: no `hash()`, no `id()`, no time, no path in the digest.

        A fresh interpreter imports the module and rebuilds the *same* batch; the
        product-set digest and every domain digest must match this process's. This
        is the only honest way to hold 'cross process' -- a second in-process call
        shares `PYTHONHASHSEED` with the first.
        """
        script = (
            "import sys; sys.path.insert(0, r'%s')\n"
            "from terrain_pipeline.hydrology_planning import PlanningConfig\n"
            "from terrain_pipeline.surface_rivers.metric_domain_pipeline import "
            "resolve_domain_products\n"
            "points = [%s]\n"
            "batch = resolve_domain_products(%d, points, config=PlanningConfig())\n"
            "print('OK', batch.product_set_sha256)\n"
        ) % (ROOT, ", ".join("(%r, %r)" % point for point in POINTS), SEED)
        for key in self.batch.outlet_keys:
            script += "print('OK', batch.domains[(%r, %r)].identity_sha256)\n" % key
        probe = self.temp_dir("cross-process") / "probe.py"
        probe.write_text(script, encoding="utf-8")
        result = subprocess.run([sys.executable, str(probe)], cwd=str(ROOT),
                                capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = [line.split(" ", 1)[1] for line in result.stdout.splitlines()
                 if line.startswith("OK ")]
        self.assertEqual(len(lines), 1 + self.batch.domain_count,
                         result.stdout + result.stderr)
        self.assertEqual(lines[0], self.batch.product_set_sha256)
        for position, key in enumerate(self.batch.outlet_keys):
            self.assertEqual(lines[1 + position], self.batch.domains[key].identity_sha256)

    # ------------------------------------------------- 5.2 shuffled input
    def test_shuffled_input_changes_no_product(self):
        """Contract 5.2: products and the domain list are input-order independent.

        Only `refusals` follows the caller's order (contract 4.2); `domains` -- and
        every product in it -- must be sorted by outlet coordinate and identical.
        """
        shuffled = self.rerun(list(reversed(POINTS)))
        self.assertEqual(shuffled.outlet_keys, self.batch.outlet_keys)
        self.assertEqual(shuffled.product_set_sha256, self.batch.product_set_sha256)
        self.assertEqual(shuffled.accepted_points, self.batch.accepted_points)
        self.assertEqual(shuffled.refused_points, self.batch.refused_points)
        for key in self.batch.outlet_keys:
            one, two = shuffled.domains[key], self.batch.domains[key]
            self.assertEqual(one.identity_sha256, two.identity_sha256)
            np.testing.assert_array_equal(one.cells_x_m, two.cells_x_m)
            np.testing.assert_array_equal(one.cells_z_m, two.cells_z_m)
            np.testing.assert_array_equal(one.territory_raster, two.territory_raster)
            np.testing.assert_array_equal(one.base_height_m, two.base_height_m)
            np.testing.assert_array_equal(one.ocean_mask, two.ocean_mask)
        # The refusal list is the input order of the refused points, so reversing
        # the input reverses it -- and nothing else.
        self.assertEqual([(r.x_m, r.z_m) for r in shuffled.refusals],
                         [(r.x_m, r.z_m) for r in self.batch.refusals][::-1])
        self.assertEqual(shuffled.refusal_records()[0]["reason"], "ocean")

    def test_chunked_input_produces_the_same_products(self):
        """Contract 7: different chunking of the same points is the same answer.

        Two calls, half the points each, must agree with the one-call batch domain
        by domain -- the identity is per coordinate, not per invocation.
        """
        first = self.rerun(POINTS[:3])
        second = self.rerun(POINTS[3:])
        merged = {**first.domains, **second.domains}
        self.assertEqual(tuple(sorted(merged)), self.batch.outlet_keys)
        for key in self.batch.outlet_keys:
            self.assertEqual(merged[key].identity_sha256,
                             self.batch.domains[key].identity_sha256)

    # ------------------------------------- 4/5. memory <-> disk round trip
    def test_memory_and_disk_batches_share_the_identity(self):
        """Contract 5.1/7: write, reload, re-derive -- one digest, three times."""
        root = self.temp_dir("round-trip")
        written = self.rerun(POINTS, output_dir=root)
        self.assertEqual(written.product_set_sha256, self.batch.product_set_sha256)
        index_path = root / "river-domain-index-v1.json"
        self.assertTrue(index_path.is_file(), "batch index JSON is missing")
        index = read_json(index_path)
        self.assertEqual(index["schema"], INDEX_SCHEMA)
        self.assertEqual(index["requested_points"], len(POINTS))
        self.assertEqual(index["accepted_points"], self.batch.accepted_points)
        self.assertEqual(index["refused_points"], self.batch.refused_points)
        self.assertEqual(index["accepted_points"] + index["refused_points"], len(POINTS))
        self.assertEqual(index["product_set_sha256"], self.batch.product_set_sha256)
        # `domains` is sorted by outlet coordinate; refusals keep input order.
        outlets = [(entry["outlet_x_m"], entry["outlet_z_m"]) for entry in index["domains"]]
        self.assertEqual(outlets, sorted(outlets))
        self.assertEqual([(entry["x_m"], entry["z_m"]) for entry in index["refusals"]],
                         [(r.x_m, r.z_m) for r in self.batch.refusals])
        self.assertEqual(len(index["domains"]), self.batch.domain_count)
        for entry in index["domains"]:
            key = (entry["outlet_x_m"], entry["outlet_z_m"])
            product = self.batch.domains[key]
            self.assertEqual(entry["product"], domain_product_name(*key))
            self.assertEqual(entry["territory_cells"], product.cell_count)
            self.assertEqual(entry["identity_sha256"], product.identity_sha256)
            path = root / entry["product"]
            self.assertTrue(path.is_file(), "product file missing: %s" % path)
            reloaded = load_domain_product(path)
            self.assertEqual(reloaded.identity_sha256, product.identity_sha256)
            invalidation = load_domain_product(path, expected_identity_sha256=entry["identity_sha256"])
            self.assertEqual(invalidation.outlet_xz_m, key)
            np.testing.assert_array_equal(reloaded.cells_x_m, product.cells_x_m)
            np.testing.assert_array_equal(reloaded.cells_z_m, product.cells_z_m)
            np.testing.assert_array_equal(reloaded.territory_raster, product.territory_raster)
            np.testing.assert_array_equal(reloaded.base_height_m, product.base_height_m)
            np.testing.assert_array_equal(reloaded.ocean_mask, product.ocean_mask)
            self.assertEqual(reloaded.kind, product.kind)
            self.assertEqual(reloaded.area_m2, product.area_m2)
            self.assertEqual(reloaded.config_id, config_identity(CONFIG))

    def test_publish_refuses_to_overwrite_an_existing_product(self):
        """Contract 5.1: an existing destination is refused, never silently replaced."""
        root = self.temp_dir("exclusive")
        self.rerun(POINTS, output_dir=root)
        key = self.batch.outlet_keys[0]
        victim = root / domain_product_name(*key)
        before = victim.read_bytes()
        with self.assertRaises(FileExistsError):
            self.rerun(POINTS, output_dir=root)
        self.assertEqual(victim.read_bytes(), before, "a refused publish clobbered a product")
        self.assertEqual(len(list(root.glob("*.npz"))), self.batch.domain_count)

    def test_reloaded_product_refuses_a_wrong_expected_identity(self):
        """A reload is an integrity check, not a blind read."""
        root = self.temp_dir("integrity")
        self.rerun(POINTS, output_dir=root)
        key = self.batch.outlet_keys[0]
        path = root / domain_product_name(*key)
        with self.assertRaises(ValueError):
            load_domain_product(path, expected_identity_sha256="0" * 64)

    # ------------------------------------------------- schema 4.1 / 4.2
    def test_product_carries_the_contract_schema(self):
        """Every key of contract 4.1, and the declared vocabulary verbatim."""
        expected = {"outlet_xz_m", "kind", "cells_x_m", "cells_z_m", "area_m2",
                    "bbox_origin_xz_m", "spacing_m", "territory_raster", "base_height_m",
                    "ocean_mask", "seed", "config_id", "identity_sha256", "schema",
                    "limitations"}
        for key in self.batch.outlet_keys:
            product = self.batch.domains[key]
            arrays = product.arrays()
            self.assertEqual(set(arrays), expected, "contract 4.1 key set drifted")
            self.assertEqual(str(np.asarray(arrays["schema"]).item()), SCHEMA)
            self.assertEqual(SCHEMA, "river-domain-product-v1")
            self.assertEqual(tuple(np.asarray(arrays["limitations"]).tolist()), LIMITATIONS)
            self.assertIn("plane sample only; no claim about the whole infinite world",
                          list(product.limitations))
            self.assertEqual(product.kind, "marine")
            self.assertEqual(int(np.asarray(arrays["seed"]).item()), SEED)
            self.assertEqual(float(np.asarray(arrays["spacing_m"]).item()), SPACING_M)
            self.assertFalse("receiver" in arrays)
            # The scattered cells are the authority: the derived raster must hold
            # exactly them, on the tight bounding box.
            self.assertEqual(product.cell_count, int(product.territory_raster.sum()))
            self.assertEqual(product.raster_shape, product.territory_raster.shape)
            self.assertEqual(product.area_m2, product.cell_count * SPACING_M ** 2)
            index_x = np.rint((product.cells_x_m - product.bbox_origin_x_m) / SPACING_M)
            index_z = np.rint((product.cells_z_m - product.bbox_origin_z_m) / SPACING_M)
            self.assertTrue(product.territory_raster[index_z.astype(int), index_x.astype(int)].all())
            self.assertEqual(product.raster_shape[0], int(index_z.max()) + 1)
            self.assertEqual(product.raster_shape[1], int(index_x.max()) + 1)

    def test_base_height_is_the_raw_pure_field_on_the_raster_box(self):
        """The published surface is the base field, not a filled/raised face."""
        for key in self.batch.outlet_keys:
            product = self.batch.domains[key]
            nz, nx = product.raster_shape
            axis_x = product.bbox_origin_x_m + np.arange(nx) * product.spacing_m
            axis_z = product.bbox_origin_z_m + np.arange(nz) * product.spacing_m
            grid_x, grid_z = np.meshgrid(axis_x, axis_z)
            base, _, _ = coarse_condition_field(SEED, grid_x, grid_z, CONFIG)
            np.testing.assert_array_equal(product.base_height_m, np.asarray(base).reshape(nz, nx))

    def test_products_agree_with_metric_domain_closure(self):
        """Contract 4.0: every published quantity comes from the closure module.

        A product that disagreed with `territory_of` would be a second truth, which
        is exactly what the contract forbids.
        """
        for key in self.batch.outlet_keys:
            product = self.batch.domains[key]
            territory = territory_of(SEED, key[0], key[1], CONFIG)
            self.assertEqual(tuple(territory["outlet_xz_m"]), key)
            self.assertEqual(product.kind, territory["kind"])
            self.assertEqual(product.cell_count, int(territory["cell_count"]))
            self.assertEqual(product.area_m2, float(territory["area_m2"]))
            np.testing.assert_array_equal(product.cells_x_m, np.asarray(territory["cells_x_m"]))
            np.testing.assert_array_equal(product.cells_z_m, np.asarray(territory["cells_z_m"]))

    # ---------------------------------------------------- 3/5/7. refusals
    def test_every_unaccepted_point_is_refused_verbatim(self):
        """Contract 3 and 7: the tally adds up and the vocabulary is verbatim."""
        missing = self.batch.accepted_points + self.batch.refused_points
        self.assertEqual(missing, len(POINTS))
        self.assertEqual(self.batch.refused_points, len(self.batch.refusals))
        self.assertEqual(self.batch.requested_points, len(POINTS))
        # Count domains from distinct actual owners, independent of a retired graph.
        self.assertEqual(self.batch.accepted_points, 3)
        accepted, owners = eligible_owner_at(SEED, [p[0] for p in POINTS],
                                            [p[1] for p in POINTS], CONFIG)
        expected = {(float(x), float(z)) for x, z, ok in
                    zip(owners[0].ravel(), owners[1].ravel(), accepted.ravel()) if ok}
        self.assertEqual(self.batch.domain_count, len(expected))
        self.assertEqual(sum(self.batch.reason_tally.values()), len(POINTS))
        self.assertEqual(tuple(self.batch.reason_tally), REASON_ORDER)
        self.assertEqual(self.batch.reason_tally["ocean"], 2)
        self.assertEqual(self.batch.reason_tally["coastal"], 3)
        self.assertEqual([(r.x_m, r.z_m) for r in self.batch.refusals],
                         [(0.0, 0.0), (20000.0, 0.0)])
        for refusal in self.batch.refusals:
            self.assertIn(refusal.reason, REASON_ORDER)
            self.assertEqual(refusal.resolved, refusal.reason not in UNRESOLVED_REASONS)
            self.assertTrue(refusal.resolved, "a sea point is resolved: the world is known there")
            # The reason is the closure module's own answer for that coordinate.
            answer = resolve_points(SEED, refusal.x_m, refusal.z_m, CONFIG)
            self.assertEqual(str(answer["reason"].reshape(-1)[0]), refusal.reason)
            self.assertEqual(bool(answer["resolved"].reshape(-1)[0]), refusal.resolved)
            with self.assertRaises(KeyError):
                self.batch.domain(refusal.x_m, refusal.z_m)
        self.assertEqual(self.batch.reason_tally["unresolved_border"], 0)
        self.assertEqual(self.batch.reason_tally["out_of_tile"], 0)

    def test_refusals_mirror_the_closure_module_point_for_point(self):
        """Contract 3/7: each refusal is the closure module's own answer, verbatim.

        A line of points that runs from the sea across the coast onto land: the
        batch must refuse exactly the points `resolve_points` refuses, keep the
        input order, and keep `resolved` False only for the two border labels.
        """
        clear_cache()
        try:
            samples = [(x, 0.0) for x in range(0, 200_001, 10_000)]
            batch = resolve_domain_products(SEED, samples, config=CONFIG)
            direct = resolve_points(SEED, [p[0] for p in samples],
                                    [p[1] for p in samples], CONFIG)
        finally:
            clear_cache()
        reasons = [str(value) for value in np.asarray(direct["reason"], object).reshape(-1)]
        flags = [bool(value) for value in np.asarray(direct["resolved"], bool).reshape(-1)]
        self.assertEqual(len(reasons), len(samples))
        for reason, flag in zip(reasons, flags):
            self.assertIn(reason, REASON_ORDER)
            self.assertEqual(flag, reason not in UNRESOLVED_REASONS)
        self.assertTrue(set(reasons) & set(ACCEPTED_REASONS), "no land point sampled")
        self.assertIn("ocean", reasons)
        expected_tally = {name: reasons.count(name) for name in REASON_ORDER}
        self.assertEqual(batch.reason_tally, expected_tally)
        self.assertEqual(len(batch.refusals),
                         sum(1 for reason in reasons if reason not in ACCEPTED_REASONS))
        pointer = 0
        for position, (x_m, z_m) in enumerate(samples):
            if reasons[position] in ACCEPTED_REASONS:
                continue
            refusal = batch.refusals[pointer]
            pointer += 1
            self.assertEqual((refusal.x_m, refusal.z_m), (x_m, z_m),
                             "refusals must keep the input order (contract 4.2)")
            self.assertEqual(refusal.reason, reasons[position])
            self.assertEqual(refusal.resolved, flags[position])
        self.assertEqual(pointer, len(batch.refusals))
        self.assertEqual(batch.accepted_points + batch.refused_points, len(samples))
        self.assertEqual(batch.accepted_points, len(samples) - len(batch.refusals))

    def test_inland_domain_is_a_legitimate_finite_domain(self):
        """`closed_basin` is not a refusal: it is a domain with no surface outlet."""
        clear_cache()
        try:
            batch = resolve_domain_products(SEED, INLAND_POINTS, config=CONFIG)
            reasons = resolve_points(SEED, [p[0] for p in INLAND_POINTS],
                                     [p[1] for p in INLAND_POINTS], CONFIG)
        finally:
            clear_cache()
        self.assertEqual(batch.refused_points, 0)
        self.assertEqual(batch.accepted_points, len(INLAND_POINTS))
        self.assertEqual(list(np.asarray(reasons["reason"], object).reshape(-1)),
                         ["closed_basin"] * len(INLAND_POINTS))
        self.assertEqual(batch.outlet_keys, (INLAND_OUTLET,))
        product = batch.domains[INLAND_OUTLET]
        self.assertEqual(product.kind, "inland")
        territory = territory_of(SEED, *INLAND_OUTLET, CONFIG)
        self.assertEqual(product.cell_count, np.asarray(territory["cells_x_m"]).size)
        self.assertGreater(product.cell_count, 0)
        # The outlet's own cell is land here (a lake spill terminal), so it is part
        # of its own territory -- unlike a marine mouth.
        landed = any((float(x), float(z)) == INLAND_OUTLET
                     for x, z in zip(product.cells_x_m, product.cells_z_m))
        self.assertTrue(landed, "an inland outlet cell must belong to its territory")

    # ------------------------------------------------------------ input guards
    def test_owner_outlet_and_products_are_the_same_domains(self):
        """The batch keys are exactly `eligible_owner_at`'s accepted outlets."""
        xs = [point[0] for point in POINTS]
        zs = [point[1] for point in POINTS]
        accepted, outlet = eligible_owner_at(SEED, xs, zs, CONFIG)
        accepted = np.asarray(accepted, bool).reshape(-1)
        owners = {(float(outlet[0].reshape(-1)[i]), float(outlet[1].reshape(-1)[i]))
                  for i in range(accepted.size) if accepted[i]}
        self.assertEqual(owners, set(self.batch.outlet_keys))
        self.assertEqual(self.batch.accepted_points, int(accepted.sum()))

    def test_unknown_reason_is_a_breach_not_a_new_label(self):
        """Contract 3: an unfamiliar rejection label must not be absorbed silently."""
        for reason in REASON_ORDER:
            self.assertIn(reason, ("ocean", "coastal", "closed_basin",
                                   "unresolved_border", "out_of_tile"))
        with self.assertRaises(ValueError):
            resolve_domain_products(SEED, "not-a-point", config=CONFIG)
        with self.assertRaises(ValueError):
            resolve_domain_products(SEED, [(0.0, float("nan"))], config=CONFIG)
        with self.assertRaises(ValueError):
            resolve_domain_products(SEED, POINTS, config=CONFIG, spacing_m=-1.0)
        with self.assertRaises(ValueError):
            # 15 km against 10 km nodes would rasterise a cell between two nodes.
            resolve_domain_products(SEED, POINTS, config=CONFIG, spacing_m=15000.0)
        with self.assertRaises(ValueError):
            resolve_domain_products(SEED, POINTS, config=CONFIG, cache={})

    def test_finer_spacing_is_an_equivalent_view_of_the_same_domain(self):
        """A finer `--spacing-m` is legal: it subdivides the node lattice exactly.

        The authority (the scattered cells) must be untouched, so only the digest of
        the derived view moves -- and it moves repeatably.
        """
        fine = self.rerun(POINTS, spacing_m=SPACING_M / 2)
        self.assertEqual(fine.spacing_m, SPACING_M / 2)
        again = self.rerun(POINTS, spacing_m=SPACING_M / 2)
        self.assertEqual(fine.outlet_keys, self.batch.outlet_keys)
        for key in fine.outlet_keys:
            self.assertEqual(fine.domains[key].identity_sha256,
                             again.domains[key].identity_sha256)
            np.testing.assert_array_equal(fine.domains[key].cells_x_m,
                                          self.batch.domains[key].cells_x_m)
            np.testing.assert_array_equal(fine.domains[key].cells_z_m,
                                          self.batch.domains[key].cells_z_m)
            self.assertNotEqual(fine.domains[key].identity_sha256,
                                self.batch.domains[key].identity_sha256)
            raster = fine.domains[key].territory_raster
            self.assertEqual(int(raster.sum()), fine.domains[key].cell_count)
            # The same bounding box on a lattice twice as fine holds twice as many
            # nodes, so the view grows; the cells it holds do not.
            want_z, want_x = self.batch.domains[key].raster_shape
            self.assertEqual(raster.shape, (2 * (want_z - 1) + 1, 2 * (want_x - 1) + 1))
            self.assertEqual(fine.domains[key].bbox_origin_x_m,
                             self.batch.domains[key].bbox_origin_x_m)
            self.assertEqual(fine.domains[key].bbox_origin_z_m,
                             self.batch.domains[key].bbox_origin_z_m)
        self.assertEqual(node_spacing_m(CONFIG), SPACING_M)

    def test_coarser_than_the_node_spacing_is_refused(self):
        """A coarser lattice cannot hold node-aligned cells, so it is not offered.

        Measured: at 2 x the node spacing the fixture domain's cell at z = 30000 m
        sits between two nodes. Rounding it would silently move a territory cell 10
        km, so the value is refused instead of published as a plausible raster.
        """
        with self.assertRaises(ValueError):
            resolve_domain_products(SEED, POINTS, config=CONFIG, spacing_m=2 * SPACING_M)
        with self.assertRaises(ValueError):
            resolve_domain_products(SEED, POINTS, config=CONFIG, spacing_m=1.5 * SPACING_M)


class GenerateRiverDomainsCliTests(unittest.TestCase):
    """The CLI is the contract's entry 2.2; a refusal must never look like a failure."""

    def setUp(self):
        clear_cache()
        self.addCleanup(clear_cache)
        self.root = Path(tempfile.mkdtemp(prefix="p62-cli-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.outputs = self.root / "products"
        self.report = self.root / "report.json"

    def invoke(self, *extra, expect=0):
        command = [sys.executable, str(CLI), "--seed", str(SEED), "--report", str(self.report)]
        command.extend(extra)
        result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def test_end_to_end_with_a_refusal_still_exits_zero(self):
        """Exit 0 with rejections; every product reloads to the same digest."""
        result = self.invoke(
            "--point", "0", "30000", "--point", "0", "40000",
            "--point", "0", "0", "--point", "20000", "0",
            "--spacing-m", str(SPACING_M),
            "--output-dir", str(self.outputs))
        self.assertEqual(result.returncode, 0)
        self.assertIn("OK written:", result.stdout)
        self.assertIn("identity mismatches: 0", result.stdout)
        self.assertIn("reason=ocean", result.stdout)
        report = read_json(self.report)
        self.assertEqual(report["requested_points"], 4)
        self.assertEqual(report["accepted_points"], 2)
        self.assertEqual(report["refused_points"], 2)
        self.assertEqual(report["accepted_points"] + report["refused_points"], 4)
        accepted, owners = eligible_owner_at(SEED, [0., 0.], [30000., 40000.], CONFIG)
        expected = {(float(x), float(z)) for x, z, ok in
                    zip(owners[0].ravel(), owners[1].ravel(), accepted.ravel()) if ok}
        self.assertEqual(report["domain_count"], len(expected))
        self.assertEqual(report["reason_tally"]["ocean"], 2)
        self.assertEqual(report["refusals"][0]["reason"], "ocean")
        self.assertTrue(report["refusals"][0]["resolved"])
        self.assertIn("plane sample only; no claim about the whole infinite world",
                      report["limitations"])
        self.assertFalse(report["dry_run"])
        # Reload and compare against the report, independently of the CLI's own check.
        for entry in report["domains"]:
            product = load_domain_product(self.outputs / entry["product"],
                                          expected_identity_sha256=entry["identity_sha256"])
            self.assertEqual(product.identity_sha256, entry["identity_sha256"])
            self.assertEqual(product.outlet_xz_m,
                             (entry["outlet_x_m"], entry["outlet_z_m"]))
        self.assertEqual(len(report["reloaded_products"]), report["domain_count"])

    def test_points_file_and_dry_run(self):
        """`--points-file` works, and no `--output-dir` writes products nowhere."""
        points_file = self.root / "points.csv"
        points_file.write_text("# x,z\n0,30000\n0,40000\n0,0\n", encoding="utf-8")
        self.invoke("--points-file", str(points_file))
        report = read_json(self.report)
        self.assertEqual(report["requested_points"], 3)
        self.assertEqual(report["accepted_points"], 2)
        self.assertEqual(report["refused_points"], 1)
        accepted, owners = eligible_owner_at(SEED, [0., 0.], [30000., 40000.], CONFIG)
        expected = {(float(x), float(z)) for x, z, ok in
                    zip(owners[0].ravel(), owners[1].ravel(), accepted.ravel()) if ok}
        self.assertEqual(report["domain_count"], len(expected))
        self.assertTrue(report["dry_run"])
        self.assertIsNone(report["output_dir"])
        self.assertEqual(report["reloaded_products"], [])
        self.assertEqual(list(self.root.glob("*.npz")), [])

    def test_product_identity_matches_the_report(self):
        """The report's digest and a fresh reload agree, so the demo is reproducible."""
        self.invoke("--point", "0", "30000", "--point", "40000", "0",
                    "--output-dir", str(self.outputs))
        report = read_json(self.report)
        for entry in report["domains"]:
            path = self.outputs / entry["product"]
            self.assertTrue(path.is_file())
            reloaded = load_domain_product(path)
            self.assertEqual(reloaded.identity_sha256, entry["identity_sha256"])
        self.assertEqual([(entry["outlet_x_m"], entry["outlet_z_m"]) for entry in report["domains"]],
                         sorted((entry["outlet_x_m"], entry["outlet_z_m"])
                                for entry in report["domains"]))

    def test_invalid_input_is_a_non_zero_exit(self):
        """No point, a malformed point, a bad spacing, and a taken report path."""
        self.invoke(expect=2)  # no point at all
        self.invoke("--point", "not-a-number", expect=2)
        self.invoke("--point", "0", "30000", "--spacing-m", "-5", expect=2)
        self.invoke("--point", "0", "30000", "--spacing-m", "15000", expect=2)
        self.invoke("--point", "0", "30000")
        self.invoke("--point", "0", "30000", expect=3)  # report already exists

    def test_refuses_to_overwrite_an_existing_product(self):
        """Contract 5.1 through the CLI: a second run into the same dir fails."""
        self.invoke("--point", "0", "30000", "--output-dir", str(self.outputs))
        self.report.unlink()
        second = self.invoke("--point", "0", "30000", "--output-dir", str(self.outputs),
                             expect=3)
        self.assertIn("FAILED:", second.stdout)


if __name__ == "__main__":
    unittest.main()
