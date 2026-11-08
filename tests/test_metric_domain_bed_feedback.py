"""`metric_domain_bed_feedback`: the derived bed-change product's contracts.

What is held to account here:

1. **conservation** -- the coupled ledger's deposited solid volume becomes a bulk
   volume through an explicit porosity conversion, and the per-cell bed change sums
   back to that bulk per domain and tile wide;
2. **parent binding** -- a coupled product that was edited after publication is
   refused; the parent's identity is recomputed, not trusted;
3. **accumulation only** -- the ledger's source is a declared weathering term, not
   bed erosion, so a zero-deposition run gives exactly zero change and no cell can
   show a negative change;
4. **the declarations** -- `terrain_feedback_applied` is true while every hydraulic
   claim stays false, and the product says its hydraulics need revalidation and that
   `bed_rejection` was not applied (the parent publishes no receiver, depth or rock
   floor);
5. replay through a write and a cold reload, tamper refusal, and the usual input
   refusals.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.surface_rivers.metric_domain_bed_feedback import (
    ALGORITHM,
    BED_FEEDBACK_SCHEMA,
    PRODUCT_KEYS,
    BedFeedbackParameters,
    load_domain_bed_feedback,
    save_domain_bed_feedback,
    solve_domain_bed_feedback,
    validate_domain_bed_feedback,
)
from terrain_pipeline.surface_rivers.metric_domain_closure import clear_cache
from terrain_pipeline.surface_rivers.metric_domain_coupled import (
    CoupledParameters,
    solve_domain_coupled,
)

SEED = 20261020
CONFIG = PlanningConfig()
POINTS = (
    (0.0, 30000.0),
    (0.0, 40000.0),
    (40000.0, 0.0),
    (20000.0, 0.0),
)
RAIN_MM_H = 4.0
INTERVALS = 4
POROSITY = 0.35


def _coupled(intervals=INTERVALS, parameters=None, rain=RAIN_MM_H):
    clear_cache()
    try:
        return solve_domain_coupled(SEED, POINTS, rain, config=CONFIG,
                                    parameters=parameters, intervals=intervals)
    finally:
        clear_cache()


class BedFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = _coupled()
        cls.record = solve_domain_bed_feedback(cls.parent)

    # ------------------------------------------------ conservation
    def test_solid_becomes_bulk_through_the_declared_porosity(self):
        arrays = self.record["arrays"]
        solid = np.asarray(arrays["deposited_solid_m3"], np.float64)
        bulk = np.asarray(arrays["deposited_bulk_m3"], np.float64)
        pore = np.asarray(arrays["pore_m3"], np.float64)
        self.assertTrue(np.allclose(bulk, solid / (1.0 - POROSITY), rtol=1e-12, atol=1e-9))
        self.assertTrue(np.allclose(pore, bulk - solid, rtol=1e-12, atol=1e-9))

    def test_the_published_solid_total_equals_the_parents_deposition(self):
        parent_total = float(self.parent["metadata"]["totals"]["deposited_total_m3"])
        totals = self.record["metadata"]["totals"]
        self.assertAlmostEqual(totals["deposited_solid_total_m3"], parent_total, places=3)

    def test_the_bed_change_sums_back_to_the_bulk_volume(self):
        arrays = self.record["arrays"]
        bed_change = np.asarray(arrays["bed_change_m"], np.float64)
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        bulk = np.asarray(arrays["deposited_bulk_m3"], np.float64)
        area = float(self.record["metadata"]["cell_area_m2"])
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            volume = float(np.sum(bed_change[start:stop], dtype=np.float64)) * area
            self.assertAlmostEqual(volume, float(bulk[index]), places=3)
        self.assertAlmostEqual(
            float(np.sum(bed_change, dtype=np.float64)) * area,
            float(self.record["metadata"]["totals"]["deposited_bulk_total_m3"]), places=3)

    def test_conservation_residual_is_zero(self):
        totals = self.record["metadata"]["totals"]
        self.assertLess(abs(totals["conservation_residual_m3"]),
                        1e-6 * max(abs(totals["deposited_bulk_total_m3"]), 1.0))

    # ------------------------------------------------ accumulation only
    def test_no_cell_loses_material(self):
        bed_change = np.asarray(self.record["arrays"]["bed_change_m"], np.float64)
        self.assertTrue(np.all(bed_change >= 0.0))

    def test_zero_deposition_gives_exactly_zero_change(self):
        # Zero weathering -> nothing entrained -> nothing deposited -> the product
        # must be exactly zero, not "nearly zero".
        dry = _coupled(parameters=CoupledParameters(weathered_m_per_interval=0.0))
        self.assertEqual(float(dry["metadata"]["totals"]["deposited_total_m3"]), 0.0)
        feedback = solve_domain_bed_feedback(dry)
        bed_change = np.asarray(feedback["arrays"]["bed_change_m"], np.float64)
        self.assertTrue(np.all(bed_change == 0.0))
        self.assertEqual(feedback["metadata"]["totals"]["changed_cells"], 0)
        self.assertEqual(feedback["metadata"]["totals"]["max_bed_change_m"], 0.0)
        validate_domain_bed_feedback(feedback)

    # ------------------------------------------------ parent binding
    def test_a_tampered_parent_is_refused(self):
        forged = _deep_copy_bundle(self.parent)
        forged["arrays"]["deposited_m3"] = (
            np.asarray(forged["arrays"]["deposited_m3"], np.float64) * 2.0)
        with self.assertRaises(ValueError):
            solve_domain_bed_feedback(forged)

    def test_a_wrong_parent_schema_is_refused(self):
        forged = _deep_copy_bundle(self.parent)
        forged["metadata"]["schema"] = "something-else"
        forged["identity_sha256"] = _identity(forged)
        with self.assertRaises(ValueError):
            solve_domain_bed_feedback(forged)

    def test_the_parent_identity_is_recorded(self):
        self.assertEqual(self.record["metadata"]["parent_identity_sha256"],
                         self.parent["identity_sha256"])
        self.assertEqual(self.record["metadata"]["parent_schema"],
                         self.parent["metadata"]["schema"])

    # ------------------------------------------------ the declarations
    def test_terrain_feedback_is_declared_and_hydraulics_are_not(self):
        claims = self.record["metadata"]["claims"]
        self.assertIs(claims["terrain_feedback_applied"], True)
        for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"):
            self.assertIs(claims[key], False)

    def test_revalidation_is_demanded_and_bed_rejection_is_declared_absent(self):
        revalidation = self.record["metadata"]["revalidation"]
        self.assertIs(revalidation["needs_geometry_and_hydraulic_revalidation"], True)
        self.assertIs(revalidation["bed_rejection_applied"], False)
        self.assertIn("receiver", revalidation["bed_rejection_reason"])

    def test_the_placement_rule_is_declared(self):
        self.assertEqual(self.record["metadata"]["placement_rule"],
                         "uniform_within_domain_over_published_cells")
        joined = " ".join(self.record["arrays"]["limitations"].tolist())
        self.assertIn("DECLARED uniform disaggregation", joined)
        self.assertIn("accumulation only", joined)
        self.assertIn("bed_rejection is NOT applied", joined)

    def test_the_product_carries_the_contract_surface(self):
        self.assertEqual(set(self.record["arrays"]), set(PRODUCT_KEYS))
        self.assertEqual(self.record["metadata"]["schema"], BED_FEEDBACK_SCHEMA)
        self.assertEqual(self.record["metadata"]["algorithm"], ALGORITHM)

    # ------------------------------------------------ alignment with the parent
    def test_the_cells_are_the_parents_cells_unchanged(self):
        for key in ("cells_x_m", "cells_z_m", "cell_offsets", "cell_count",
                    "outlet_x_m", "outlet_z_m", "kind"):
            self.assertTrue(np.array_equal(
                np.asarray(self.record["arrays"][key]),
                np.asarray(self.parent["arrays"][key])), key)

    def test_the_raster_marks_exactly_the_published_cells(self):
        arrays = self.record["arrays"]
        raster = np.asarray(arrays["bed_change_raster_m"], np.float64)
        rows, columns = (int(v) for v in self.record["metadata"]["tile_shape"])
        self.assertEqual(raster.shape, (rows * columns,))
        spacing = float(self.record["metadata"]["spacing_m"])
        origin_x, origin_z = (float(v) for v in self.record["metadata"]["tile_origin_m_xz"])
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        cells_z = np.asarray(arrays["cells_z_m"], np.float64)
        column = np.rint((cells_x - origin_x) / spacing).astype(np.int64)
        row = np.rint((cells_z - origin_z) / spacing).astype(np.int64)
        flat = row * columns + column
        self.assertTrue(np.array_equal(raster[flat], np.asarray(arrays["bed_change_m"])))
        # Nothing outside the published cells is marked.
        mask = np.zeros(rows * columns, bool)
        mask[flat] = True
        self.assertTrue(np.all(raster[~mask] == 0.0))

    # ------------------------------------------------ replay and refusal
    def test_the_same_parent_replays_to_the_same_identity(self):
        again = solve_domain_bed_feedback(self.parent)
        self.assertEqual(again["identity_sha256"], self.record["identity_sha256"])

    def test_identity_survives_a_write_and_a_cold_reload(self):
        root = Path(tempfile.mkdtemp(prefix="bed-feedback-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = root / "bed.npz"
        save_domain_bed_feedback(path, self.record)
        reloaded = load_domain_bed_feedback(
            path, expected_sha256=_file_sha256(path),
            expected_identity=self.record["identity_sha256"])
        self.assertEqual(reloaded["identity_sha256"], self.record["identity_sha256"])
        for key in PRODUCT_KEYS:
            self.assertTrue(np.array_equal(np.asarray(reloaded["arrays"][key]),
                                           np.asarray(self.record["arrays"][key])), key)

    def test_saving_never_overwrites(self):
        root = Path(tempfile.mkdtemp(prefix="bed-exists-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = root / "bed.npz"
        save_domain_bed_feedback(path, self.record)
        with self.assertRaises(Exception):
            save_domain_bed_feedback(path, self.record)

    def test_a_forged_totals_block_is_caught(self):
        for key in ("deposited_bulk_total_m3", "conservation_residual_m3",
                    "max_bed_change_m"):
            forged = _deep_copy_bundle(self.record)
            forged["metadata"]["totals"][key] += 1.0
            with self.assertRaises(ValueError):
                validate_domain_bed_feedback(forged)

    def test_a_forged_bed_change_array_is_caught(self):
        forged = _deep_copy_bundle(self.record)
        forged["arrays"]["bed_change_m"] = (
            np.asarray(forged["arrays"]["bed_change_m"], np.float64) * 1.5)
        with self.assertRaises(ValueError):
            validate_domain_bed_feedback(forged)

    def test_negative_bed_change_is_refused(self):
        # The product declares accumulation only; a negative change would be bed
        # erosion written back, which this module does not do.
        forged = _deep_copy_bundle(self.record)
        bed = np.asarray(forged["arrays"]["bed_change_m"], np.float64)
        bed[0] = -abs(bed[0]) - 1e-6 if bed[0] != 0 else -1e-6
        forged["arrays"]["bed_change_m"] = bed
        forged["identity_sha256"] = _identity(forged)
        with self.assertRaises(ValueError):
            validate_domain_bed_feedback(forged)

    def test_claims_must_declare_the_feedback(self):
        forged = _deep_copy_bundle(self.record)
        forged["metadata"]["claims"]["terrain_feedback_applied"] = False
        forged["identity_sha256"] = _identity(forged)
        with self.assertRaises(ValueError):
            validate_domain_bed_feedback(forged)

    def test_a_product_cannot_claim_publishable_hydraulics(self):
        forged = _deep_copy_bundle(self.record)
        forged["metadata"]["claims"]["hydraulic_ready"] = True
        forged["identity_sha256"] = _identity(forged)
        with self.assertRaises(ValueError):
            validate_domain_bed_feedback(forged)

    # ------------------------------------------------ parameters
    def test_porosity_changes_the_change_and_the_identity(self):
        looser = solve_domain_bed_feedback(
            self.parent, parameters=BedFeedbackParameters(porosity=0.5))
        solid = float(self.record["metadata"]["totals"]["deposited_solid_total_m3"])
        self.assertAlmostEqual(looser["metadata"]["totals"]["deposited_bulk_total_m3"],
                               solid / 0.5, places=3)
        self.assertGreater(looser["metadata"]["totals"]["max_bed_change_m"],
                           self.record["metadata"]["totals"]["max_bed_change_m"])
        self.assertNotEqual(looser["identity_sha256"], self.record["identity_sha256"])
        validate_domain_bed_feedback(looser)

    def test_porosity_bounds_are_enforced(self):
        for bad in (-0.1, 1.0, 1.5, float("nan"), True):
            with self.assertRaises(ValueError):
                BedFeedbackParameters(porosity=bad)

    def test_the_parameter_record_is_flat(self):
        self.assertEqual(self.record["metadata"]["parameters"], {"porosity": POROSITY})

    def test_a_wrong_parameters_object_is_refused(self):
        with self.assertRaises(ValueError):
            solve_domain_bed_feedback(self.parent, parameters={"porosity": 0.35})

    def test_a_non_bundle_parent_is_refused(self):
        for bad in ({}, {"arrays": {}}, self.parent["arrays"]):
            with self.assertRaises(ValueError):
                solve_domain_bed_feedback(bad)

    def test_an_interval_one_parent_also_works(self):
        single = _coupled(intervals=1)
        feedback = solve_domain_bed_feedback(single)
        validate_domain_bed_feedback(feedback)
        self.assertEqual(feedback["metadata"]["interval_count"], 1)
        self.assertGreater(feedback["metadata"]["totals"]["deposited_solid_total_m3"], 0.0)


class BedFeedbackScaleTests(unittest.TestCase):
    def test_the_bed_change_is_reported_at_its_real_magnitude(self):
        """The measured size of this feedback, so nobody mistakes it for terrain.

        Deposition over a 10 km x 10 km node is spread over 1e8 m2, so even a
        hundreds-of-millions-of-cubic-metres tile gives a millimetre-scale change.
        The test pins the order of magnitude: if a future change made this look like
        metres of deposition, the product would be misrepresenting the scale.
        """
        parent = _coupled()
        record = solve_domain_bed_feedback(parent)
        totals = record["metadata"]["totals"]
        self.assertGreater(totals["deposited_solid_total_m3"], 1e8)
        self.assertLess(totals["max_bed_change_m"], 1.0)
        self.assertGreater(totals["max_bed_change_m"], 0.0)


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


def _identity(bundle):
    from terrain_pipeline.common_infra import identity
    return identity(bundle["arrays"], bundle["metadata"])


if __name__ == "__main__":
    unittest.main()
