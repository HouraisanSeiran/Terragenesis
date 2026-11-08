"""Behavior checks on the immutable TD bay, with no inference or game runtime."""

import json

import networkx as nx
import numpy as np
import pytest

from terrain_pipeline import delta_network_site as site
from terrain_pipeline import delta_network_morphology as morph
from terrain_pipeline import delta_network_skeleton_v3 as sk
from tools import run_delta_network_v5 as runner


@pytest.fixture(scope="module")
def source():
    spec = runner.source_site(100.0)
    bed, ocean, valid = site.sample_td(spec)
    assert valid.all()
    return spec, bed, ocean


@pytest.fixture(scope="module")
def cases(source):
    spec, bed, ocean = source
    return {name: morph.build(spec, bed, ocean, name) for name in morph.VARIANTS}


def test_actual_dag_conservation_and_distinct_loop_controls(source, cases):
    loop_counts = {}
    for name, (graph, terrain, tp) in cases.items():
        directed = nx.DiGraph(zip(graph.edge_from, graph.edge_to))
        assert nx.is_directed_acyclic_graph(directed)
        assert nx.is_weakly_connected(directed)
        assert sk.validate_graph(graph)["ok"]
        metrics = sk.skeleton_metrics_v3(graph)
        assert metrics["max_level"] >= 3
        assert metrics["n_mouths"] >= 6
        assert metrics["n_confluences"] >= 1
        assert graph.node_q[graph.mouth_nodes].sum() == pytest.approx(graph.params.q_total)
        loop_counts[name] = metrics["loops"]
    assert loop_counts["few_loops"] < loop_counts["base"] < loop_counts["many_loops"]


def test_source_hills_and_unconstructed_cells_survive(source, cases):
    spec, bed, ocean = source
    for graph, terrain, tp in cases.values():
        hills = (bed >= morph.PlainParameters().landward_elevation_limit_m) & ~ocean
        assert np.array_equal(terrain["bed"][hills], bed[hills])
        # The displayed support mask has a 1 cm / 1% diagnostic threshold.
        # Exact untouched cells have neither reconstruction nor deposition.
        plain = terrain["whole_plain"]
        untouched = (plain["landward_weight"] == 0.0) & (plain["deposit"] == 0.0) & ~terrain["chan"]
        assert np.array_equal(terrain["bed"][untouched], bed[untouched])
        assert np.isfinite(terrain["bed"]).all()


def test_wide_plain_is_independent_of_the_channel_graph(source, cases):
    spec, bed, ocean = source
    base = cases["base"][1]["whole_plain"]["bed"]
    for graph, terrain, tp in cases.values():
        assert np.array_equal(terrain["whole_plain"]["bed"], base)
        metrics = morph.whole_plain_metrics(spec, graph, terrain, ocean)
        assert metrics["source_landward_plain_area_km2"] > 50.0
        assert metrics["source_marine_plain_area_km2"] > 150.0
        assert metrics["plain_2km_interior_core_area_km2"] > 20.0
        mouth_station = next(item for item in metrics["alongstream_lateral_widths"] if item["u_m"] == 0.0)
        assert min(mouth_station["left_plain_width_m"], mouth_station["right_plain_width_m"]) > 2500.0


def test_actual_coast_mouths_have_no_added_marine_geometry(source, cases):
    spec, bed, ocean = source
    for graph, terrain, tp in cases.values():
        audit = morph.geometry_audit(spec, graph, terrain, tp)
        assert audit["ok"]
        assert audit["xz_forbidden_turns"] == 0
        assert len(graph.construction_profiles) == len(graph.mouth_nodes)
        for node in graph.mouth_nodes:
            edge = int(np.flatnonzero(graph.edge_to == node)[0])
            profile = graph.construction_profiles[edge]
            assert profile["has_marine_extension"] is False
            assert profile["final_extension_m"] == 0.0
            assert np.array_equal(sk.edge_points(graph, edge)[-1], graph.node_uv[node])
        assert all(
            item["connected_to_open_water"] and item["raster_depth_m"] > 0.0 for item in audit["mouths"]
        )


def test_geological_stock_is_finite_and_separate_from_event_supply(source, cases):
    spec, bed, ocean = source
    for graph, terrain, tp in cases.values():
        ledger = terrain["geological_ledger"]
        used = (
            ledger["landward_fill_solid_m3"]
            + ledger["marine_retained_solid_m3"]
            + ledger["marine_unplaced_solid_m3"]
        )
        assert used == pytest.approx(ledger["declared_geological_solid_m3"], abs=0.01)
        assert ledger["marine_unplaced_solid_m3"] >= 0.0
        assert ledger["physical_event_input_solid_m3"] == 0.0
        assert ledger["physical_elapsed_seconds"] == 0.0
        expected = np.maximum(terrain["z_plain"] - terrain["bed"], 0.0).sum() * spec.spacing_m**2 * 0.6
        assert ledger["channel_excavated_solid_m3"] == pytest.approx(expected)


def test_zero_supply_does_not_invent_geological_fill(source):
    spec, bed, ocean = source
    plain = morph.whole_plain(spec, bed, ocean, morph.PlainParameters(denudation_m=0.0))
    assert plain["ledger"]["landward_fill_solid_m3"] == 0.0
    assert plain["ledger"]["marine_retained_solid_m3"] == 0.0
    assert plain["ledger"]["marine_unplaced_solid_m3"] == 0.0
    assert np.all(plain["bed"] <= bed)


def test_seeded_outputs_are_repeatable(source, cases):
    spec, bed, ocean = source
    graph, terrain, tp = morph.build(spec, bed, ocean)
    first_graph, first_terrain, _ = cases["base"]
    assert np.array_equal(graph.pts_uv, first_graph.pts_uv)
    assert np.array_equal(graph.edge_from, first_graph.edge_from)
    assert np.array_equal(terrain["bed"], first_terrain["bed"])
    assert graph.params.algorithm_world_seed == 20260903
    assert site.WORLD_SEED == 20261020


@pytest.mark.parametrize(
    "parameters", [{"porosity": 1.0}, {"front_transition_m": 0.0}, {"delivery_fraction": -1.0}]
)
def test_invalid_material_and_transition_parameters_are_rejected(source, parameters):
    spec, bed, ocean = source
    with pytest.raises(ValueError):
        morph.whole_plain(spec, bed, ocean, morph.PlainParameters(**parameters))


def test_runner_paths_and_explicit_construction_reference_contract():
    assert not any(char in str(runner.DEFAULT_FIGS.relative_to(runner.ROOT)) for char in '<>:"|?*')
    directory = runner.ROOT / ".scratch/delta-completion-20261107/source-controlled-v5-100m-r3/base"
    if not directory.exists():
        pytest.skip("saved acceptance product is not required for source unit checks")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf8"))
    reference = manifest["construction_reference"]
    assert reference["file"] == "construction_reference_bed_m.npy"
    assert np.array_equal(
        np.load(directory / reference["file"]), np.load(directory / "td_original_bed_m.npy")
    )
    assert manifest["world_seed"] == 20260903
    assert manifest["source_world_seed"] == 20261020
