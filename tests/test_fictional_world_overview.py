"""Contract tests for the finite fictional-world overview.

These tests exercise the module's *external* behaviour: the same request must
reproduce identical arrays, a different seed must change them, the exported land
must split into exactly three continents above the declared area gate plus
islands, the frame border must stay ocean, and the exported river paths must
afloat in a valid receiver graph.  Nothing here claims anything about the 30 m
Terrain Diffusion chain.
"""
import tempfile
from pathlib import Path
import unittest

import numpy as np
from scipy import ndimage

from terrain_pipeline.fictional_world_overview import (
    CONTINENT_COUNT,
    CONTINENT_MIN_AREA_FRACTION,
    ISLAND_COUNT_RANGE,
    MIN_STRAIT_KM,
    LayoutRefused,
    OutputExistsError,
    OverviewError,
    OverviewRequest,
    derive_subseed,
    generate_overview,
    write_overview,
)

#: A layout-attempt loop needs a few runs, so keep the test grid small but large
#: enough that the continents are many cells wide.
SMALL = dict(seed=20261020, extent_km=1600.0, grid_size=128)


def build(**overrides):
    parameters = dict(SMALL)
    parameters.update(overrides)
    return generate_overview(OverviewRequest(**parameters))


class RequestTests(unittest.TestCase):
    def test_defaults_are_the_declared_request(self):
        request = OverviewRequest()
        self.assertEqual(request.seed, 20261020)
        self.assertEqual(request.extent_km, 1600.0)
        self.assertEqual(request.grid_size, 1024)
        self.assertAlmostEqual(request.spacing_m, 1562.5)
        self.assertAlmostEqual(request.border_band_cells, round(0.03 * 1024))

    def test_grid_contract_separates_frame_span_from_sample_span(self):
        request = OverviewRequest(grid_size=1024)
        contract = request.grid_contract()
        self.assertAlmostEqual(contract["frame_edges_m"][1] - contract["frame_edges_m"][0],
                               1_600_000.0)
        self.assertAlmostEqual(contract["node_centre_span_m"], 1023 * 1562.5)
        self.assertAlmostEqual(contract["sample_count"], 1024 * 1024)
        self.assertNotAlmostEqual(contract["node_centre_span_m"], 1_600_000.0)

    def test_invalid_parameters_are_rejected(self):
        for parameters in ({'seed': -1}, {'seed': 2 ** 64}, {'seed': 1.5}, {'seed': True},
                           {'extent_km': 0.0}, {'extent_km': float('nan')},
                           {'extent_km': 10_000.0}, {'grid_size': 8}, {'grid_size': 4_000},
                           {'grid_size': 128.5}, {'min_strait_km': 0.0},
                           {'min_strait_km': float('inf')}):
            with self.subTest(parameters=parameters):
                with self.assertRaises(OverviewError):
                    OverviewRequest(**parameters)

    def test_non_request_is_rejected(self):
        with self.assertRaises(OverviewError):
            generate_overview(dict(SMALL))

    def test_subseed_is_stable_and_purpose_separated(self):
        first = derive_subseed(20261020, "layout", 0)
        self.assertEqual(first, derive_subseed(20261020, "layout", 0))
        self.assertNotEqual(first, derive_subseed(20261020, "layout", 1))
        self.assertNotEqual(first, derive_subseed(20261020, "mountain_belt", 0))
        self.assertNotEqual(first, derive_subseed(20261021, "layout", 0))
        self.assertTrue(0 <= first < 2 ** 64)
        for purpose, index in (("Layout", 0), ("", 0), ("layout", -1), ("layout", 1.5)):
            with self.subTest(purpose=purpose, index=index):
                with self.assertRaises(OverviewError):
                    derive_subseed(20261020, purpose, index)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_reproduces_every_array(self):
        first = build()
        second = build()
        self.assertEqual(sorted(first.arrays), sorted(second.arrays))
        for name in sorted(first.arrays):
            with self.subTest(array=name):
                np.testing.assert_array_equal(first.arrays[name], second.arrays[name])
        self.assertEqual(first.report["report_sha256"], second.report["report_sha256"])
        self.assertEqual(first.report["seeds"], second.report["seeds"])

    def test_different_seed_changes_the_arrays(self):
        first = build()
        second = build(seed=20261021)
        differing = [name for name in ("elevation_m", "land_mask", "component_id", "receiver_index")
                     if not np.array_equal(first.arrays[name], second.arrays[name])]
        self.assertIn("elevation_m", differing)
        self.assertIn("land_mask", differing)
        self.assertNotEqual(first.report["report_sha256"], second.report["report_sha256"])
        self.assertNotEqual(first.report["seeds"], second.report["seeds"])

    def test_report_names_its_own_seeds_and_hashes(self):
        result = build()
        seeds = result.report["seeds"]["values"]
        self.assertEqual(seeds["layout[0]"], derive_subseed(20261020, "layout", 0))
        self.assertIn("terrain_texture[0]", seeds)
        self.assertIn("terrain_uplift[0]", seeds)
        self.assertEqual(len([key for key in seeds if key.startswith("mountain_belt")]),
                         CONTINENT_COUNT)
        for name, record in result.report["arrays"].items():
            with self.subTest(array=name):
                self.assertEqual(record["shape"], list(result.arrays[name].shape))
                self.assertEqual(record["dtype"], str(result.arrays[name].dtype))


class LandmassTests(unittest.TestCase):
    def test_exactly_three_continents_above_the_gate(self):
        result = build()
        request = result.request
        land = result.arrays["land_mask"]
        component_id = result.arrays["component_id"]
        labels, count = ndimage.label(land, structure=np.ones((3, 3), dtype=bool))
        self.assertEqual(count, int(component_id.max()) + 1)
        areas = np.asarray(ndimage.sum(land, labels, index=np.arange(1, count + 1))) \
            * request.cell_area_km2
        self.assertEqual(int(np.sum(areas >= request.continent_gate_km2)), CONTINENT_COUNT)
        self.assertEqual(len(areas), CONTINENT_COUNT + result.report["results"]["island_count"])
        gate = CONTINENT_MIN_AREA_FRACTION * 1600.0 ** 2
        for area in areas:
            self.assertTrue(area < gate or area >= gate)
        self.assertEqual(result.report["checks"]["components"]["continents"], CONTINENT_COUNT)

    def test_island_count_is_declared_and_all_below_the_gate(self):
        result = build()
        islands = [record for record in result.report["results"]["components"]
                   if not record["is_continent"]]
        self.assertGreaterEqual(len(islands), ISLAND_COUNT_RANGE[0])
        self.assertLessEqual(len(islands), ISLAND_COUNT_RANGE[1])
        for record in islands:
            self.assertFalse(record["above_continent_gate"])
            self.assertLess(record["area_km2"], result.request.continent_gate_km2)
        self.assertLess(max(record["area_km2"] for record in islands),
                        min(record["area_km2"]
                            for record in result.report["results"]["components"]
                            if record["is_continent"]))

    def test_every_landmass_is_its_own_component(self):
        result = build()
        land = result.arrays["land_mask"]
        component_id = result.arrays["component_id"].ravel()
        landmass_index = result.arrays["landmass_index"].ravel()
        pairs = {(int(component_id[cell]), int(landmass_index[cell]))
                 for cell in np.flatnonzero(land.ravel())}
        self.assertEqual(len(pairs), int(landmass_index.max()) + 1)
        self.assertEqual(len({pair[0] for pair in pairs}), len(pairs))
        self.assertEqual(len({pair[1] for pair in pairs}), len(pairs))

    def test_the_frame_border_is_ocean_on_all_four_sides(self):
        result = build()
        land = result.arrays["land_mask"]
        band = result.request.border_band_cells
        self.assertFalse(land[:band, :].any())
        self.assertFalse(land[-band:, :].any())
        self.assertFalse(land[:, :band].any())
        self.assertFalse(land[:, -band:].any())
        self.assertTrue(result.report["checks"]["border"]["border_is_all_ocean"])

    def test_no_two_landmasses_are_closer_than_the_declared_strait(self):
        result = build()
        landmasses = result.report["layout"]["landmasses"]
        strait_m = MIN_STRAIT_KM * 1000.0
        for first in range(len(landmasses)):
            for second in range(first + 1, len(landmasses)):
                a, b = landmasses[first], landmasses[second]
                distance = float(np.hypot(a["centre_km"][0] - b["centre_km"][0],
                                          a["centre_km"][1] - b["centre_km"][1])) * 1000.0
                with self.subTest(first=a["slot"], second=b["slot"]):
                    self.assertGreaterEqual(distance,
                                            a["extent_bound_km"] * 1000.0
                                            + b["extent_bound_km"] * 1000.0 + strait_m - 1e-6)

    def test_elevation_sign_agrees_with_the_land_mask_and_supports_negatives(self):
        result = build()
        elevation = result.arrays["elevation_m"].astype(np.float64)
        land = result.arrays["land_mask"]
        np.testing.assert_array_equal(elevation > 0.0, land)
        self.assertLess(float(elevation[~land].min()), -100.0)
        self.assertEqual(result.report["checks"]["nodes_disagreeing_between_mask_and_elevation_sign"], 0)
        measured = result.report["checks"]["elevation"]
        self.assertEqual(measured["elevation_min_m"], float(elevation.min()))
        self.assertEqual(measured["elevation_max_m"], float(elevation.max()))

    def test_mountains_form_continuous_belts(self):
        result = build()
        land = result.arrays["land_mask"]
        belt = result.arrays["mountain_belt"].astype(np.float64)
        lifted = result.arrays["mountain_height_m"].astype(np.float64)
        self.assertGreater(float(lifted.max()), 1500.0)
        self.assertFalse((lifted[~land] > 0.0).any())
        ridge_area = belt > 0.5
        self.assertGreater(int(ridge_area.sum()), 0)
        labels, count = ndimage.label(ridge_area, structure=np.ones((3, 3), dtype=bool))
        self.assertGreaterEqual(count, CONTINENT_COUNT)
        self.assertEqual(len(result.report["results"]["ridges"]), 3 * CONTINENT_COUNT)
        mainstems = [record for record in result.report["results"]["ridges"] if record["main"]]
        self.assertEqual(len(mainstems), CONTINENT_COUNT)


class RiverTests(unittest.TestCase):
    def test_receiver_graph_is_acyclic_and_eight_connected(self):
        result = build()
        graph = result.report["checks"]["receiver_graph"]
        self.assertTrue(graph["receiver_graph_is_acyclic"])
        self.assertTrue(graph["receivers_are_graph_adjacent"])
        self.assertTrue(graph["receivers_have_larger_rank"])
        self.assertTrue(graph["every_ocean_node_is_an_outlet"])
        self.assertTrue(graph["no_land_node_acts_as_an_outlet"])
        self.assertEqual(graph["land_outlet_nodes"], 0)

        receiver = result.arrays["receiver_index"].ravel()
        land = result.arrays["land_mask"].ravel()
        solved = {}  # cell -> terminal cell, filled by following receivers
        for start in np.flatnonzero(receiver >= 0):
            trail = []
            cell = int(start)
            while True:
                if cell in solved:
                    terminal = solved[cell]
                    break
                if receiver[cell] < 0:
                    terminal = cell
                    break
                self.assertNotIn(cell, trail, "receiver cycle through cell %d" % cell)
                trail.append(cell)
                cell = int(receiver[cell])
            for node in trail:
                solved[node] = terminal
        for start in np.flatnonzero(receiver >= 0):
            self.assertFalse(land[solved[int(start)]])

    def test_every_continent_has_a_mainstem_of_nondegenerate_length(self):
        result = build()
        rivers = result.report["results"]["rivers"]
        per_continent = result.report["checks"]["rivers"]["per_continent"]
        self.assertTrue(result.report["checks"]["rivers"]["every_continent_has_a_river"])
        for continent in range(CONTINENT_COUNT):
            with self.subTest(continent=continent):
                self.assertGreaterEqual(per_continent[str(continent)], 1)
                self.assertLessEqual(per_continent[str(continent)], 3)
        for record in rivers:
            self.assertGreaterEqual(record["node_count"], 8)
            self.assertGreater(record["length_km"], 8 * result.request.spacing_m / 1000.0 - 1e-9)
            self.assertTrue(record["path_follows_receivers_monotonically"])
            self.assertTrue(record["all_nodes_are_land"])
            self.assertFalse(record["crosses_open_water"])
            self.assertTrue(record["mouth_is_land"])
            self.assertTrue(record["mouth_downstream_is_ocean"])
            self.assertLess(record["mouth_downstream_elevation_m"], 0.0)
            self.assertGreater(record["mouth_cells_from_frame_edge"],
                               result.request.border_band_cells)
            self.assertEqual(record["mouth_owner_component"], record["continent"])

    def test_mouth_catchment_is_an_independent_land_cell_census(self):
        result = build()
        checks = result.report["checks"]["rivers"]
        self.assertTrue(checks["catchment_cross_check_agrees"])
        self.assertLessEqual(checks["catchment_cross_check_max_abs_disagreement_m2"],
                             checks["catchment_cross_check_tolerance_m2"])
        area = result.arrays["contributing_area_m2"]
        land = result.arrays["land_mask"]
        spacing = result.request.spacing_m
        # Ocean cells carry no runoff: the only admissible ocean value is zero.
        self.assertEqual(float(area[~land].min()), 0.0)
        self.assertEqual(float(area[~land].max()), 0.0)
        # Every land node's area is a whole number of land cells.
        cells = area[land] / (spacing ** 2)
        np.testing.assert_allclose(cells, np.round(cells), atol=1e-6)
        self.assertGreaterEqual(float(cells.min()), 1.0)
        self.assertLessEqual(float(cells.max()), float(land.sum()))
        for record in result.report["results"]["rivers"]:
            self.assertAlmostEqual(record["mouth_catchment_km2_accumulated"],
                                   record["mouth_catchment_km2_independent_census"],
                                   places=9)
            self.assertGreater(record["mouth_catchment_km2_accumulated"], 0.0)

    def test_river_arrays_describe_the_reported_paths(self):
        result = build()
        nodes = result.arrays["river_nodes"]
        offsets = result.arrays["river_offsets"]
        river_id = result.arrays["river_id"]
        rivers = result.report["results"]["river_paths"]
        self.assertEqual(len(offsets), len(rivers) + 1)
        self.assertEqual(int(offsets[0]), 0)
        self.assertEqual(int(offsets[-1]), nodes.size)
        self.assertTrue(np.all(np.diff(offsets) > 0))
        for index, record in enumerate(rivers):
            cells = nodes[offsets[index]:offsets[index + 1]]
            self.assertEqual([int(cell) for cell in cells], record["nodes"])
            self.assertTrue((river_id.ravel()[cells] == index).all())
            # Consecutive nodes are 8-neighbour receiver pairs, head to mouth.
            cols = result.request.grid_size
            for first, second in zip(cells[:-1], cells[1:]):
                self.assertEqual(int(result.arrays["receiver_index"].ravel()[first]), int(second))
                i0, j0 = divmod(int(first), cols)
                i1, j1 = divmod(int(second), cols)
                self.assertNotEqual(first, second)
                self.assertLessEqual(float(result.arrays["routing_surface_m"].ravel()[second]),
                                     float(result.arrays["routing_surface_m"].ravel()[first]) + 1e-4)

    def test_filled_surface_is_reported_separately_from_elevation(self):
        result = build()
        filling = result.report["checks"]["filling"]
        land = result.arrays["land_mask"]
        filled = result.arrays["filled_depth_m"].astype(np.float64)
        routing = result.arrays["routing_surface_m"].astype(np.float64)
        elevation = result.arrays["elevation_m"].astype(np.float64)
        self.assertTrue(np.all(filled[land] >= -1e-3))
        np.testing.assert_allclose(routing[land] - elevation[land], filled[land], atol=1e-3)
        self.assertGreaterEqual(filling["filled_land_nodes"], 0)
        self.assertLessEqual(filling["filled_land_fraction"], 1.0)
        self.assertEqual(filling["routing_surface_minus_elevation"][:19], "filled depth of the")


class OutputTests(unittest.TestCase):
    def test_write_creates_three_files_and_refuses_a_second_write(self):
        result = build(grid_size=96)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "run-01"
            written = write_overview(result, destination, render=False)
            self.assertEqual(sorted(written["files"]), ["overview-report.json", "overview.npz"])
            self.assertTrue((destination / "overview.npz").exists())
            self.assertTrue((destination / "overview-report.json").exists())
            with self.assertRaises(OutputExistsError):
                write_overview(result, destination, render=False)

            loaded = np.load(destination / "overview.npz")
            self.assertEqual(sorted(loaded.files), sorted(result.arrays))
            for name in sorted(result.arrays):
                with self.subTest(array=name):
                    np.testing.assert_array_equal(loaded[name], result.arrays[name])
            loaded.close()

    def test_written_report_hashes_its_arrays_and_names_its_source(self):
        import hashlib
        import json

        from terrain_pipeline.artifacts.contracts import array_hash, canonical_json

        result = build(grid_size=96)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "run-01"
            write_overview(result, destination, render=False)
            body = json.loads((destination / "overview-report.json").read_text(encoding="utf-8"))
            self.assertEqual(body["schema"], "fictional-world-overview-v2-irregular")
            self.assertIn("fictional_world_overview.py", body["sources"])
            self.assertIsNotNone(body["sources"]["fictional_world_overview.py"])
            claimed = body.pop("report_sha256")
            self.assertEqual(claimed,
                             hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest())
            for name, record in body["arrays"].items():
                with self.subTest(array=name):
                    self.assertEqual(record["sha256"],
                                     array_hash(np.ascontiguousarray(result.arrays[name])))
            self.assertFalse(body["capability"]["terrain_diffusion_product"])
            self.assertFalse(body["capability"]["stage_one_accepted"])
            self.assertFalse(body["capability"]["natural_outlet_certified"])
            self.assertTrue(body["limitations"])

    def test_report_declares_what_is_and_is_not_configurable(self):
        result = build(grid_size=96)
        surface = result.report["configuration_surface"]
        self.assertEqual(sorted(surface["already_parameterised"]),
                         sorted(result.request.parameters()))
        for name in ("layout", "landmass_shape", "elevation", "mountains", "rivers"):
            with self.subTest(section=name):
                self.assertIn(name, surface["hard_coded"])
        self.assertTrue(surface["safe_to_expose_later"])
        self.assertTrue(surface["unsafe_without_new_validation"])
        self.assertIn("refusal", surface["rule"])

    def test_impossible_layout_is_refused_not_relaxed(self):
        # A 200 km frame cannot hold three ~150 km-reach continents 80 km apart.
        with self.assertRaises(LayoutRefused) as caught:
            generate_overview(OverviewRequest(seed=20261020, extent_km=200.0, grid_size=96))
        self.assertTrue(caught.exception.attempts)
        for record in caught.exception.attempts:
            self.assertIn("attempt", record)
            self.assertIn("reason", record)

    def test_render_produces_a_png_and_never_overwrites(self):
        result = build(grid_size=96)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "run-01"
            written = write_overview(result, destination)
            png = destination / "overview.png"
            self.assertTrue(png.exists())
            self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertGreater(png.stat().st_size, 20_000)
            self.assertEqual(sorted(written["files"]),
                             ["overview-report.json", "overview.npz", "overview.png"])
            with self.assertRaises(OutputExistsError):
                write_overview(result, destination)


if __name__ == "__main__":
    unittest.main()
