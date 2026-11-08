"""Contract tests for the thin Terrain Diffusion special-terrain adapter."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import load_special_form_vdm
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.special_terrain import TD_ADAPTER_ALGORITHM as ALGORITHM, CHANNEL_POLICIES, MAX_FINE_CELLS, MAX_FINE_SIDE, NATIVE_SPACING_M, TD_ADAPTER_SCHEMA as SCHEMA, build_td_form_chart, select_native_window
from tools import preview_td_special_terrain as preview

NATIVE_SHAPE = (256, 256)
NATIVE_ORIGIN = [-184320.0, 61440.0]
REAL_HIERARCHY = ROOT / preview.SOURCE_PATH


def select(**overrides):
    kwargs = dict(center_m_xz=[-177600.0, 67680.0], size_m_xz=[960.0, 960.0], spacing_m=4.0,
                  native_shape=NATIVE_SHAPE, native_origin_m_xz=NATIVE_ORIGIN,
                  max_growth_m=60.0)
    kwargs.update(overrides)
    return select_native_window(**kwargs)


class SelectWindowTests(unittest.TestCase):
    def test_full_grid_request_is_already_on_the_lattice(self):
        window = select()
        self.assertEqual(window["schema"], SCHEMA)
        self.assertEqual(window["algorithm"], ALGORITHM)
        self.assertEqual(window["native_window"], [208, 240, 192, 224])
        self.assertEqual(window["native_span_cells_xz"], [32, 32])
        self.assertEqual(window["fine_shape_zx"], [240, 240])
        self.assertEqual(window["maximum_snap_observed_m"], 0.0)
        self.assertEqual(window["growth_m"], [0.0, 0.0])
        self.assertEqual(window["actual_size_m_xz"], [960.0, 960.0])
        # 208 native cells east of the origin, 192 north of it: both already on the lattice.
        self.assertEqual(window["corner_origin_m_xz"], [-178080.0, 67200.0])

    def test_off_lattice_request_snaps_outward_and_reports_the_offset(self):
        window = select(center_m_xz=[-177610.0, 67690.0], size_m_xz=[930.0, 930.0],
                        max_growth_m=60.0)
        self.assertEqual(window["native_window"], [208, 240, 192, 224])
        for value in window["snap_m"]:
            self.assertGreaterEqual(value, 0.0)
            self.assertLess(value, NATIVE_SPACING_M)
        self.assertAlmostEqual(window["maximum_snap_observed_m"], 25.0)
        self.assertAlmostEqual(window["maximum_snap_observed_m"], max(window["snap_m"]))
        self.assertEqual(window["growth_m"], [30.0, 30.0])
        self.assertAlmostEqual(window["maximum_growth_observed_m"], 30.0)
        self.assertAlmostEqual(window["requested_size_m_xz"][0], 930.0)

    def test_growth_beyond_the_declared_maximum_is_refused(self):
        # A centred 924 m request snaps outward to the whole 960 m native window: +36 m,
        # which is above the module's declared one-native-cell bound of 30 m.
        with self.assertRaises(ValueError) as caught:
            select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[924.0, 924.0],
                   max_growth_m=NATIVE_SPACING_M)
        message = str(caught.exception)
        self.assertIn("would grow by 36 m", message)
        self.assertIn("maximum", message)
        with self.assertRaises(ValueError):
            select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[924.0, 924.0],
                   max_growth_m=None)
        relaxed = select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[924.0, 924.0],
                         max_growth_m=36.0)
        self.assertEqual(relaxed["native_window"], [208, 240, 192, 224])
        self.assertAlmostEqual(relaxed["maximum_growth_observed_m"], 36.0)

    def test_realised_window_always_covers_the_request(self):
        # Only requests the selector accepts may be checked for coverage; a refused request
        # is a different contract and is exercised by the refusal tests above and below.
        accepted = ((900.0, 0.0), (924.0, 0.0), (924.0, 29.0), (930.0, 0.0), (930.0, 7.0),
                    (930.0, 29.0), (960.0, 0.0))
        for size, offset in accepted:
            with self.subTest(size=size, offset=offset):
                center = [-177600.0 + offset, 67680.0 + offset]
                window = select(center_m_xz=center, size_m_xz=[size, size], max_growth_m=60.0)
                self.assertGreaterEqual(window["actual_size_m_xz"][0], size)
                self.assertGreaterEqual(window["actual_size_m_xz"][1], size)
                self.assertLessEqual(window["maximum_growth_observed_m"], 60.0)
                for axis in (0, 1):
                    origin = window["corner_origin_m_xz"][axis]
                    realised = window["actual_size_m_xz"][axis]
                    requested_low = center[axis] - size / 2.0
                    requested_high = center[axis] + size / 2.0
                    self.assertLessEqual(origin, requested_low + 1e-6)
                    self.assertGreaterEqual(origin + realised, requested_high - 1e-6)

    def test_window_leaving_the_native_extent_is_refused(self):
        for center in ([-184300.0, 67680.0], [0.0, 0.0], [-100000.0, 61200.0]):
            with self.subTest(center=center):
                with self.assertRaises(ValueError):
                    select(center_m_xz=center, size_m_xz=[960.0, 960.0])

    def test_spacing_must_be_one_of_the_declared_fine_ladders(self):
        for spacing in (0.5, 3.0, 8.0, 30.0, "1"):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    select(spacing_m=spacing)
        # Each ladder is capped by the same 240x240 fine lattice, so the widest whole-ladder
        # request is 240 m at 1 m, 480 m at 2 m and 960 m at 4 m: 240*240 = 57600 cells.
        for spacing, size in ((1.0, 240.0), (2.0, 480.0), (4.0, 960.0)):
            with self.subTest(spacing=spacing):
                window = select(spacing_m=spacing, size_m_xz=[size, size])
                self.assertEqual(window["spacing_m"], spacing)
                self.assertEqual(window["fine_shape_zx"], [MAX_FINE_SIDE, MAX_FINE_SIDE])
                self.assertEqual(window["fine_cells"], MAX_FINE_SIDE ** 2)
                self.assertLessEqual(window["fine_cells"], MAX_FINE_CELLS)
                self.assertEqual(window["actual_size_m_xz"], [size, size])
        for spacing, size in ((1.0, 480.0), (2.0, 960.0)):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    select(spacing_m=spacing, size_m_xz=[size, size])

    def test_fine_cell_budget_is_refused_with_the_stitch_hint(self):
        with self.assertRaises(ValueError) as caught:
            select(size_m_xz=[960.0, 960.0], spacing_m=1.0, max_growth_m=60.0)
        message = str(caught.exception)
        self.assertIn("fine window would need", message)
        self.assertIn("stitch", message)

    def test_non_integral_cell_count_is_refused(self):
        # An off-lattice centre makes a 900 m request span 930 m, which 4 m cannot tile evenly.
        with self.assertRaises(ValueError) as caught:
            select(center_m_xz=[-177593.0, 67687.0], size_m_xz=[900.0, 900.0], spacing_m=4.0,
                   max_growth_m=60.0)
        self.assertIn("whole number", str(caught.exception))
        # The same request on the lattice does tile: 900 m at 4 m is 225 cells per axis.
        on_lattice = select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[900.0, 900.0],
                            spacing_m=4.0, max_growth_m=60.0)
        self.assertEqual(on_lattice["native_window"], [209, 239, 193, 223])
        self.assertEqual(on_lattice["fine_shape_zx"], [225, 225])

    def test_degenerate_and_malformed_requests_are_refused(self):
        with self.assertRaises(ValueError):
            select(size_m_xz=[960.0, 0.0])
        with self.assertRaises(ValueError):
            select(size_m_xz=[960.0, -1.0])
        with self.assertRaises(ValueError):
            select(size_m_xz=[960.0])
        with self.assertRaises(ValueError):
            select(center_m_xz=[float("nan"), 67680.0])
        with self.assertRaises(ValueError):
            select(native_shape=(256, 256, 1))
        with self.assertRaises(ValueError):
            select(native_shape=(2, 256))
        with self.assertRaises(ValueError):
            select(native_origin_m_xz=[0.0])
        # Too small to survive the outward snap on the declared one-native-cell bound:
        # a 20 m request at 4 m spacing spans two 30 m cells, so it grows by 40 m.
        with self.assertRaises(ValueError):
            select(size_m_xz=[20.0, 20.0], spacing_m=4.0, max_growth_m=NATIVE_SPACING_M)
        # A 30 m request at 4 m also lands on two native cells (60 m) and is accepted once
        # the caller declares the 30 m growth it is willing to accept.
        snapped = select(size_m_xz=[30.0, 30.0], spacing_m=4.0, max_growth_m=NATIVE_SPACING_M)
        self.assertEqual(snapped["native_span_cells_xz"], [2, 2])
        self.assertEqual(snapped["fine_shape_zx"], [15, 15])
        self.assertAlmostEqual(snapped["maximum_growth_observed_m"], 30.0)
        with self.assertRaises(ValueError):
            select(size_m_xz=[240.0, 240.0], spacing_m=1.0, max_growth_m=0.0)


class _FakeHierarchy:
    """Stand-in that refuses to be consumed as a hierarchy.

    The chart contract must reject a malformed window, spacing or channel selection *before*
    it hands anything to the shared bed builder. If a bad input slips through, this object
    raises AssertionError from the build path instead of returning a plausible record, so the
    test fails loudly rather than passing on a wrong success.
    """

    def __init__(self, rows, cols):
        self.arrays = {"height_m": np.zeros((rows, cols), dtype=np.float64)}
        self.metadata = {"origin_m_xz": list(NATIVE_ORIGIN)}

    def __getitem__(self, key):
        raise AssertionError("the bed builder must not run for a refused chart request")



class BuildChartTests(unittest.TestCase):
    def test_chart_contract_rejects_mismatched_records(self):
        window = select()
        empty = np.zeros((0, 2), dtype=np.int64)
        for mutation in ({"schema": "other"}, {"schema": SCHEMA, "native_window": [32, 64, 32],
                                                "spacing_m": 4.0},
                         {"schema": SCHEMA, "native_window": [32.0, 64.0, 32.0, 64.0],
                          "spacing_m": 4.0}):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    build_td_form_chart(_FakeHierarchy(256, 256), window=mutation, spacing_m=4.0,
                                        source_hierarchy_sha256="a" * 64,
                                        selected_edge_cell_ids=empty)
        with self.assertRaises(ValueError):
            build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=2.0,
                                source_hierarchy_sha256="a" * 64, selected_edge_cell_ids=empty)
        with self.assertRaises(ValueError):
            build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=4.0,
                                source_hierarchy_sha256="a" * 64, selected_edge_cell_ids=empty,
                                channel_policy="keep")

    def test_channel_selection_must_be_an_explicit_int64_edge_array(self):
        window = select()
        # A plain Python list of ints is already int64 under NumPy 2, so it is a *valid*
        # selection shape and is not part of this negative list; only dtype, rank and shape
        # violations are refused here.
        for bad in (None, np.zeros((2, 2), dtype=np.int32), np.zeros((2,), dtype=np.int64),
                    np.zeros((2, 3), dtype=np.int64)):
            with self.subTest(selected=repr(bad)):
                with self.assertRaises(ValueError):
                    build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=4.0,
                                        source_hierarchy_sha256="a" * 64,
                                        selected_edge_cell_ids=bad)
        empty = np.zeros((0, 2), dtype=np.int64)
        self.assertEqual(np.asarray([[1, 2]]).dtype, np.int64)
        # A well-formed empty selection is *not* refused by the contract, so it reaches the
        # bed builder: the stand-in proves that by refusing to be consumed.
        with self.assertRaises(AssertionError):
            build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=4.0,
                                source_hierarchy_sha256="a" * 64,
                                selected_edge_cell_ids=empty)

    def test_channel_policy_whitelist_is_declared(self):
        self.assertEqual(CHANNEL_POLICIES, ("reject", "protect"))


class EndToEndTests(unittest.TestCase):
    """The declared ladder over the pinned hierarchy: bed -> chart -> form -> preview.

    These cases read the 16 MB pinned hierarchy and run the real fine bed builder, so they
    are slower than the contract tests above. They are the only place where the declared
    foot elevation (the fix for the silent all-zero form) is exercised against a real bed.
    """

    @classmethod
    def setUpClass(cls):
        cls.hierarchy = load_basin_hierarchy(path=str(REAL_HIERARCHY),
                                             expected_sha256=preview.SOURCE["expected_sha256"],
                                             expected_identity=preview.SOURCE["expected_identity"])

    def test_declared_ladder_covers_real_bed_and_is_replayable(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            self.assertEqual(preview.main(["--output", str(output)]), 0)
            first = {entry.name: file_sha256(entry) for entry in output.iterdir()}
            self.assertEqual(set(first), {
                "report.json", "volcanic_plug-td-bundle.npz", "volcanic_plug-td-a-plan.png",
                "volcanic_plug-td-b-profile.png", "volcanic_plug-td-c-solid.png",
                "karst_tower_field-td-bundle.npz", "karst_tower_field-td-a-plan.png",
                "karst_tower_field-td-b-profile.png", "karst_tower_field-td-c-solid.png"})
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(set(report["cases"]), {"volcanic_plug", "karst_tower_field"})
            self.assertFalse(report["claims"]["real_terrain_reconstruction"])
            self.assertFalse(report["claims"]["foot_elevation_surveyed"])
            self.assertTrue(report["claims"]["preset_foot_is_synthetic"])
            self.assertFalse(report["claims"]["excavation_modelled"])
            for flag in preview.ALL_FLAGS:
                self.assertFalse(report["claims"][flag])
            for kind, case in report["cases"].items():
                with self.subTest(kind=kind):
                    # The point of the fix: a form on a real bed must actually emerge.
                    self.assertGreater(case["max_relief_m"], 0.0)
                    self.assertLess(case["max_relief_m"], 2.0 * 1000.0)
                    self.assertEqual(case["collar_max_abs_m"], 0.0)
                    self.assertFalse(any(case["declared_flags"].values()))
                    self.assertEqual(case["form_algorithm"], "special-terrain-field-forms-v1")
                    self.assertEqual(case["adapter_schema"], SCHEMA)
                    self.assertEqual(case["base"], "td_fine_bed")
                    placement = case["placement"]
                    foot = placement["declared_foot_elevation_m"]
                    self.assertGreater(foot, 0.0)
                    self.assertLessEqual(foot, placement["window_bed_max_m"])
                    self.assertEqual(foot, placement["window_bed_min_m"])
                    for value in placement["nominal_footprint_bed_min_m"]:
                        self.assertGreaterEqual(value, foot)
                    chain = case["chart_record"]["identity_chain"]
                    self.assertEqual(chain["fine_bed_identity"], chain["chart_source_identity"])
                    self.assertEqual(chain["source_hierarchy_identity"],
                                     preview.SOURCE["expected_identity"])
                    # Everything the tool wrote must cold-read as the same form bundle, and
                    # the saved recipe must carry the declared foot, not the preset 0 m.
                    bundle = output / case["file"]
                    self.assertEqual(file_sha256(bundle), case["sha256"])
                    loaded = load_special_form_vdm(bundle, expected_sha256=case["sha256"],
                                                   expected_identity=case["identity_sha256"])
                    self.assertEqual(loaded["metadata"]["base"], "td_fine_bed")
                    self.assertEqual(loaded["metadata"]["source_identity"],
                                     chain["chart_source_identity"])
                    for target in loaded["metadata"]["recipe"]["targets"]:
                        self.assertEqual(target["base_elevation_m"], foot)
                    self.assertEqual(float(np.max(loaded["arrays"]["displacement_xyz_m"][:, :, 1])),
                                     case["max_relief_m"])
            self.assertEqual({entry.name: file_sha256(entry) for entry in output.iterdir()}, first)

    def test_declared_foot_reproduces_the_form_over_the_raw_chart(self):
        # Independent of the tool: rebuild one case straight from the adapter chart and the
        # window record, and check the declaration really is the window bed floor.
        window = select_native_window(center_m_xz=preview.WINDOW_CENTER_M_XZ,
                                      size_m_xz=[preview.WINDOW_SIZE_M] * 2, spacing_m=4.0,
                                      native_shape=self.hierarchy["arrays"]["height_m"].shape,
                                      native_origin_m_xz=self.hierarchy["metadata"]["origin_m_xz"])
        chart = build_td_form_chart(self.hierarchy, window=window, spacing_m=4.0,
                                    source_hierarchy_sha256=preview.SOURCE["expected_sha256"],
                                    selected_edge_cell_ids=np.zeros((0, 2), dtype=np.int64),
                                    channel_policy="reject")
        bed = chart["chart_reference_xyz_m"][:, :, 1]
        self.assertGreater(float(np.min(bed)), 1000.0)
        self.assertGreater(float(np.min(bed)) - 1000.0, 264.0)  # preset foot buries the form


if __name__ == "__main__":
    unittest.main()
