"""Contract tests for the shared terrain-map style layer.

The style module is the only place that decides what a map looks like, so these tests pin
the parts a future edit could silently break: the band declaration must stay consistent,
the degree graticule must refuse to guess a conversion, and the north arrow must point at
decreasing z on an inverted raster axis.

A separate group drives ``tools/render_terrain_map`` end to end on a tiny synthetic scene
and asserts that the figures it reports really exist and that it refuses the two things it
promises to refuse: writing under ``verification/`` and reading a bundle with no pinned
provenance.
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import terrain_map_style as style


class BandDeclarationTests(unittest.TestCase):
    def test_shipped_bands_are_consistent(self):
        edges = style.validate_band_edges(style.LAND_BANDS_M)
        palette = style.band_colors(edges, style.BAND_COLORS)
        self.assertEqual(palette.shape, (len(edges) - 1, 3))
        self.assertTrue(np.all((palette >= 0.0) & (palette <= 1.0)))

    def test_edges_must_start_at_the_sea_datum_and_increase(self):
        for bad in ((1.0, 10.0), (0.0, 10.0, 10.0), (0.0, 10.0, 5.0), (0.0, np.nan)):
            with self.assertRaises(ValueError):
                style.validate_band_edges(bad)

    def test_colour_count_must_match_the_band_count(self):
        with self.assertRaises(ValueError):
            style.band_colors((0.0, 10.0, 20.0), ("#fff",))
        with self.assertRaises(ValueError):
            style.band_colors((0.0, 10.0), ("#fff", "#000"))

    def test_banded_relief_uses_the_declared_palette_and_blend(self):
        edges = (0.0, 10.0, 20.0)
        colours = ("#000000", "#ffffff")
        height = np.array([[0.0, 5.0], [15.0, 25.0]])
        rgb = style.banded_relief_rgb(height, 1.0, band_edges=edges, colors=colours)
        shade = style.physical_hillshade(height, 1.0)
        # A black band stays exactly black whatever the shade is.
        self.assertTrue(np.all(rgb[0, 0, :] == 0.0))
        band = np.clip(np.searchsorted(np.asarray(edges), height, side="right") - 1, 0, 1)
        blend = style.HILLSHADE_BASE + style.HILLSHADE_WEIGHT * shade
        expected = np.clip(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])[band]
                           * blend[..., None], 0.0, 1.0)
        self.assertTrue(np.allclose(rgb, expected))
        # The declared blend saturates any band brighter than ~0.975 at full shade.  This
        # is the existing repository recipe, so the test records it instead of hiding it.
        self.assertGreater(style.HILLSHADE_BASE + style.HILLSHADE_WEIGHT, 1.0)
        self.assertTrue(np.all(rgb[1, :, :] == 1.0))


def _north_arrow_z(axis):
    """Tail and head z of the arrow drawn by ``draw_north_arrow``, in data coordinates.

    ``annotate`` keeps the arrow on the returned Annotation, not among the axes children,
    and it records both ends in data coordinates: ``xy`` is the head and ``xyann`` the tail.
    The attached FancyArrowPatch must *not* be used for this check -- its own path is built
    in the patch's private coordinate frame (measured span ~1.07 while the axes span 20),
    so reading it would compare two unrelated numbers.
    """
    annotations = [item for item in axis.texts if getattr(item, "arrow_patch", None)]
    if not annotations:
        return None
    annotation = annotations[-1]
    tail = annotation.get_position()
    head = annotation.xy
    if tail is None or head is None:
        return None
    return float(tail[1]), float(head[1])


class NorthArrowTests(unittest.TestCase):
    def test_arrow_points_at_decreasing_z_on_an_inverted_axis(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots()
        axis.set_xlim(0.0, 10.0)
        axis.set_ylim(20.0, 0.0)  # raster convention: south (larger z) at the bottom
        style.draw_north_arrow(axis)
        tip = _north_arrow_z(axis)
        figure.canvas.draw()
        plt.close(figure)
        self.assertIsNotNone(tip, "no arrow patch was drawn")
        tail, head = tip
        # With an inverted axis, screen-up is smaller z, so the arrow must gain z.
        self.assertGreater(tail, head, "north arrow points at increasing z on an inverted axis")


def _make_axis():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots()
    axis.set_xlim(0.0, 40.0)
    axis.set_ylim(0.0, 40.0)
    return figure, axis


class ScaleBarTests(unittest.TestCase):
    def test_scale_length_is_a_one_two_or_five_multiple(self):
        for span in (0.16, 0.49, 3.80, 38.37, 500.0):
            length = style.nice_scale_length_km(span)
            self.assertLessEqual(length, span / 4.0 + 1e-12)
            mantissa = length / 10.0 ** int(np.floor(np.log10(length)))
            self.assertIn(round(mantissa, 6), (1.0, 2.0, 5.0))

    def test_scale_length_rejects_a_nonpositive_span(self):
        for bad in (0.0, -3.0, float("nan")):
            with self.assertRaises(ValueError):
                style.nice_scale_length_km(bad)


def _bar_x_span(axis):
    """The scale bar is the one line whose two x values differ."""
    for line in axis.lines:
        xs = [float(value) for value in line.get_xdata()]
        if len(xs) == 2 and xs[1] != xs[0]:
            return xs[0], xs[1]
    return None


class ScaleBarRenderTests(unittest.TestCase):
    def test_bar_length_matches_the_request(self):
        figure, axis = _make_axis()
        style.draw_scale_bar(axis, 5.0)
        span = _bar_x_span(axis)
        figure.canvas.draw()
        plt_close(figure)
        self.assertIsNotNone(span, "no horizontal scale bar was drawn")
        self.assertAlmostEqual(span[1] - span[0], 5.0, places=6)

    def test_bar_sits_inside_an_inverted_frame(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots()
        axis.set_xlim(0.0, 40.0)
        axis.set_ylim(40.0, 0.0)  # raster convention: z increases southward
        style.draw_scale_bar(axis, 5.0)
        span = _bar_x_span(axis)
        bar = [line for line in axis.lines
               if [float(value) for value in line.get_xdata()] == list(span)][0]
        z = float(bar.get_ydata()[0])
        plt_close(figure)
        low, high = sorted((40.0, 0.0))
        self.assertTrue(low <= z <= high, f"scale bar at z={z} falls outside the sheet")


def plt_close(figure):
    import matplotlib.pyplot as plt
    plt.close(figure)


class DeclaredGraticuleTests(unittest.TestCase):
    def test_graticule_refuses_to_guess_a_conversion(self):
        for east, north in ((0.0, 110000.0), (90000.0, -1.0), (np.nan, 110000.0)):
            figure, axis = _make_axis()
            with self.assertRaises(ValueError):
                style.draw_declared_graticule(
                    axis, origin_xz_m=(0.0, 0.0), metres_per_degree_east=east,
                    metres_per_degree_north=north, origin_degrees=(120.0, 30.0),
                    step_degrees=0.5)
            plt_close(figure)

    def test_graticule_reports_that_it_is_not_a_projection(self):
        figure, axis = _make_axis()
        record = style.draw_declared_graticule(
            axis, origin_xz_m=(0.0, 0.0), metres_per_degree_east=97260.0,
            metres_per_degree_north=110900.0, origin_degrees=(120.0, 30.0),
            step_degrees=0.2)
        figure.canvas.draw()
        plt_close(figure)
        self.assertEqual(record["kind"], "declared_graticule_not_a_projection")
        self.assertEqual(record["metres_per_degree_east"], 97260.0)

    def test_metre_graticule_rejects_a_nonpositive_step(self):
        figure, axis = _make_axis()
        with self.assertRaises(ValueError):
            style.draw_metre_graticule(axis, step_km=0.0)
        plt_close(figure)

    def test_metre_graticule_reports_what_it_actually_drew(self):
        figure, axis = _make_axis()
        record = style.draw_metre_graticule(axis, step_km=10.0)
        plt_close(figure)
        self.assertEqual(record["kind"], "planar_kilometre_grid")
        self.assertEqual(record["step_km"], 10.0)
        # A 0..40 km frame steps at 0, 10, 20, 30 and 40, so five lines cross it.  The count is
        # reported rather than assumed: the same call on a 0.16 km chart would cross none.
        self.assertEqual((record["x_lines"], record["y_lines"]), (5, 5))

    def test_graticule_step_is_derived_from_the_span(self):
        self.assertEqual(style.nice_graticule_step_km(0.16), 0.02)
        self.assertEqual(style.nice_graticule_step_km(0.49), 0.05)
        self.assertEqual(style.nice_graticule_step_km(3.80), 0.5)
        self.assertEqual(style.nice_graticule_step_km(38.37), 5.0)
        for span in (0.16, 0.49, 3.80, 38.37, 500.0):
            step = style.nice_graticule_step_km(span)
            self.assertGreaterEqual(span / step, 4.0)
            self.assertLessEqual(span / step, 12.0)
        with self.assertRaises(ValueError):
            style.nice_graticule_step_km(0.0)


class HillshadeTests(unittest.TestCase):
    def test_flat_ground_has_a_fixed_shade(self):
        flat = np.zeros((5, 5))
        shade = style.physical_hillshade(flat, 30.0)
        self.assertTrue(np.allclose(shade, style.HILLSHADE_LIGHT[2]))

    def test_hillshade_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            style.physical_hillshade(np.zeros((3, 3, 3)), 30.0)
        with self.assertRaises(ValueError):
            style.physical_hillshade(np.full((3, 3), np.nan), 30.0)
        with self.assertRaises(ValueError):
            style.physical_hillshade(np.zeros((3, 3)), 0.0)

    def test_continuous_relief_is_shaded_and_bounded(self):
        height = np.linspace(0.0, 500.0, 100).reshape(10, 10)
        rgb = style.continuous_relief_rgb(height, 30.0, (0.0, 536.184))
        self.assertEqual(rgb.shape, (10, 10, 3))
        self.assertTrue(np.all((rgb >= 0.0) & (rgb <= 1.0)))
        self.assertFalse(np.allclose(rgb[0, 0], rgb[-1, -1]))


class RendererTests(unittest.TestCase):
    def _scene(self):
        from tools import render_terrain_map as renderer
        size = 24
        rows, cols = np.mgrid[0:size, 0:size]
        height = 100.0 + 20.0 * np.sin(rows / 3.0) * np.cos(cols / 4.0)
        receiver = np.full(size * size, -1, np.int64)
        flat_source = np.arange(size * (size - 1))
        receiver[flat_source] = flat_source + size
        permanent = np.zeros((size, size), bool)
        permanent[size // 2, 1:-1] = True
        seasonal = np.zeros((size, size), bool)
        seasonal[size // 3, 1:-1] = True
        metadata = {"spacing_m": 30.0, "origin_xz_m": [0.0, 0.0],
                    "source_identity": "0" * 64}
        return renderer, {
            "label": "synthetic", "kind": "routed_terrain_archive", "height": height,
            "receiver": receiver, "permanent": permanent, "seasonal": seasonal,
            "spacing_m": 30.0, "origin_xz_m": [0.0, 0.0], "metadata": metadata,
            "source_identity": "0" * 64, "chart_note": "synthetic test chart",
            "caveats": ["test fixture"]}

    def test_extent_and_rivers_agree_with_the_declared_grid(self):
        renderer, scene = self._scene()
        size = scene["height"].shape[1]
        extent = renderer.scene_extent_km(scene)
        self.assertAlmostEqual(extent[1] - extent[0], (size - 1) * 0.03)
        layers = renderer.river_segments(scene)
        self.assertEqual(layers["permanent"].shape, (size - 2, 2, 2))
        self.assertEqual(layers["seasonal"].shape[0], size - 2)

    def test_both_styles_write_figures_that_exist(self):
        renderer, scene = self._scene()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            figures, records, geometry = renderer.render_scene(
                scene, output, styles=["remote", "topo"], elevation_limits=[0.0, 200.0],
                graticule_step_km=0.2, declared_graticule=None,
                band_edges=style.LAND_BANDS_M, band_colours=style.BAND_COLORS, dpi=60)
            self.assertEqual(sorted(figures), ["remote", "topo"])
            for name, path in figures.items():
                self.assertTrue(path.is_file(), f"{name} figure missing")
                self.assertGreater(path.stat().st_size, 1000)
                self.assertEqual(records[name]["sha256"], renderer.sha256_file(path))
            self.assertEqual(records["topo"]["contour_levels_m"], [100.0])
            self.assertEqual(records["remote"]["contour_levels_m"], [])
            self.assertAlmostEqual(geometry["span_km"], 23 * 0.03)
            self.assertEqual(records["topo"]["graticule"]["step_km"], 0.2)
            # the kilometre grid is a printed-sheet device: the remote composite stays pure
            self.assertIsNone(records["remote"]["graticule"])

    def test_a_bundle_keeps_its_own_colour_range(self):
        """A 208 m chart must not be rendered on the 536 m large-TD scale."""
        from tools import render_terrain_map as renderer
        height = np.linspace(0.0, 208.0, 64).reshape(8, 8)
        limits = renderer.resolve_elevation_limits(height, None, label="chart")
        self.assertAlmostEqual(limits[0], 0.0)
        self.assertAlmostEqual(limits[1], 208.0)
        self.assertEqual(renderer.resolve_elevation_limits(height, [0.0, 500.0], label="chart"),
                         [0.0, 500.0])
        with self.assertRaises(ValueError):
            renderer.resolve_elevation_limits(height, [500.0, 0.0], label="chart")

    def test_graticule_step_defaults_to_the_map_span(self):
        from tools import render_terrain_map as renderer
        self.assertEqual(renderer.resolve_graticule_step(38.37, None, label="chart"), 5.0)
        self.assertEqual(renderer.resolve_graticule_step(0.16, None, label="chart"), 0.02)
        self.assertEqual(renderer.resolve_graticule_step(38.37, 10.0, label="chart"), 10.0)
        with self.assertRaises(ValueError):
            renderer.resolve_graticule_step(38.37, 0.0, label="chart")

    def test_output_guard_refuses_the_verification_tree(self):
        renderer, _scene = self._scene()
        with self.assertRaises(ValueError):
            renderer.guard_output(ROOT / "verification" / "terrain-map")

    def test_bundle_without_pinned_provenance_is_refused(self):
        renderer, _scene = self._scene()
        with tempfile.TemporaryDirectory() as folder:
            lonely = Path(folder) / "lonely.npz"
            with np.load(ROOT / ".scratch/special-terrain/surface-20261020/karst_tower_field.npz") as archive:
                np.savez_compressed(lonely, **{key: archive[key] for key in archive.files})
            with self.assertRaises(SystemExit):
                renderer.resolve_bundle_provenance(lonely)

    def test_bundle_provenance_resolves_from_the_sibling_manifest(self):
        renderer, _scene = self._scene()
        bundle = ROOT / ".scratch/special-terrain/surface-20261020/inselberg.npz"
        if not bundle.is_file():
            self.skipTest("no surface bundle available")
        digest, identity, origin = renderer.resolve_bundle_provenance(bundle)
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(identity), 64)
        record = json.loads(Path(origin).read_text(encoding="utf-8"))
        self.assertEqual(record["forms"]["inselberg"]["sha256"], digest)

    def test_loading_a_tampered_bundle_raises(self):
        renderer, _scene = self._scene()
        bundle = ROOT / ".scratch/special-terrain/surface-20261020/inselberg.npz"
        if not bundle.is_file():
            self.skipTest("no surface bundle available")
        digest, identity, _origin = renderer.resolve_bundle_provenance(bundle)
        with self.assertRaises(ValueError):
            renderer.load_bundle_scene(bundle, label="inselberg",
                                       sha256="0" * 64, identity_sha256=identity)


if __name__ == "__main__":
    unittest.main()
