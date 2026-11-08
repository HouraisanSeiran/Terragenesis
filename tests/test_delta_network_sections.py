"""Section behavior on small metric fixtures; frozen TD acceptance is separate."""

from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage as ndi

from terrain_pipeline.delta_network_sections import rasterize_channels


def _site(spacing=10.0, shape=(81, 61)):
    return SimpleNamespace(u0_m=0.0, v0_m=0.0, nu=shape[0], nv=shape[1], spacing_m=spacing)


def _graph(nodes, edges, widths, depths=None):
    paths = [np.asarray([nodes[start], nodes[end]], dtype=float) for start, end in edges]
    return SimpleNamespace(
        node_uv=np.asarray(nodes, dtype=float), edge_from=np.array([edge[0] for edge in edges]),
        edge_to=np.array([edge[1] for edge in edges]), edge_w=np.asarray(widths, dtype=float),
        edge_h=np.asarray(depths if depths is not None else np.full(len(edges), 3.0), dtype=float),
        pts_uv=np.vstack(paths), pt_off=np.arange(0, 2 * len(paths) + 1, 2),
        mouth_nodes=np.array(sorted(set(end for _, end in edges) - set(start for start, _ in edges))),
    )


def test_protected_source_hills_and_high_banks_are_not_excavated_or_wet():
    spec = _site()
    surface = np.full((spec.nu, spec.nv), 2.0)
    surface[30:48, 32:36] = 35.0
    surface[32:46, 36:42] = 65.0
    source = surface.copy()
    graph = _graph([(55, 305), (755, 305)], [(0, 1)], [110.0])
    result = rasterize_channels(spec, surface, source, np.zeros(surface.shape, bool), graph)
    hill = source >= 45.0
    high_bank = source >= 30.0
    assert np.array_equal(result["bed"][hill], source[hill])
    assert not result["chan"][high_bank].any()
    assert np.array_equal(result["bed"][high_bank], surface[high_bank])
    assert result["report"]["protected_source_cells_cut"] == 0
    assert result["report"]["contracted_section_count"] > 0
    assert result["report"]["blocked_centreline_cell_count"] == 0
    assert ndi.label(result["chan"])[1] == 1
    assert result["stage"][result["chan"]].max() <= 1.2 + 1e-10
    assert np.all(result["depth"][result["chan"]] > 0.0)
    assert np.isfinite(result["bed"]).all()


def test_subcell_channel_is_four_connected_without_inventing_physical_width():
    spec = _site(spacing=30.0, shape=(30, 30))
    surface = np.full((30, 30), 1.0)
    graph = _graph([(35, 48), (835, 823)], [(0, 1)], [4.0], [1.5])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    assert ndi.label(result["chan"])[1] == 1
    assert result["report"]["blocked_centreline_cell_count"] == 0
    assert result["report"]["subcell_coverage_cell_count"] > 0
    assert result["width"][result["chan"]].max() <= 4.0 + 1e-10
    assert result["width"][result["chan"]].min() > 0.0
    assert result["chan"][1, 1]
    assert result["chan"][27, 27]
    assert np.all(result["bed"][result["chan"]] < result["stage"][result["chan"]])


def test_30m_cliff_bank_is_not_included_by_a_minimum_raster_width():
    spec = _site(spacing=30.0, shape=(30, 20))
    surface = np.full((30, 20), 2.0)
    surface[:, 9:] = 50.0  # first high cell centre v=285 m
    graph = _graph([(45, 269), (825, 269)], [(0, 1)], [30.0])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    assert not result["chan"][:, 9:].any()
    assert np.array_equal(result["bed"][:, 9:], surface[:, 9:])
    assert result["report"]["blocked_centreline_cell_count"] == 0
    assert result["stage"][result["chan"]].max() <= 1.2 + 1e-10
    assert ndi.label(result["chan"])[1] == 1


def test_low_ridge_can_be_excavated_without_raising_channel_stage():
    spec = _site()
    surface = np.full((spec.nu, spec.nv), 2.0)
    surface[34:39, :] = 10.5
    graph = _graph([(55, 305), (755, 305)], [(0, 1)], [30.0])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    assert ndi.label(result["chan"])[1] == 1
    assert result["report"]["blocked_centreline_cell_count"] == 0
    assert result["stage"][result["chan"]].max() <= 1.2 + 1e-10
    assert result["chan"][35:38].any()
    assert result["report"]["lowland_excavation_ceiling_m"] == 12.0


def test_inaccessible_centreline_is_reported_instead_of_hidden_by_hill_mask():
    spec = _site()
    surface = np.full((spec.nu, spec.nv), 2.0)
    surface[38:43, :] = 60.0
    graph = _graph([(55, 305), (755, 305)], [(0, 1)], [40.0])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    protected = surface >= 45.0
    assert np.array_equal(result["bed"][protected], surface[protected])
    assert not result["chan"][protected].any()
    assert result["report"]["blocked_centreline_cell_count"] > 0
    assert result["report"]["channel_components_4_connected"] == 2
    assert result["report"]["detached_sweep_cells_removed"] == 0
    labels, _ = ndi.label(result["chan"])
    assert len(np.unique(labels[result["represented_centreline_mask"]])) == 2


def test_detached_sweep_cap_is_restored_without_removing_the_actual_channel():
    spec = _site(shape=(101, 61))
    surface = np.full((spec.nu, spec.nv), 2.0)
    # A protected bank upstream of the frozen source clips the rounded
    # sweep cap into an isolated patch. No centreline traverses that patch.
    surface[35:39, :] = 50.0
    graph = _graph([(405, 305), (805, 305)], [(0, 1)], [200.0])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    report = result["report"]
    assert report["channel_components_before_sweep_cleanup_4_connected"] == 2
    assert report["detached_sweep_cells_removed"] > 0
    assert report["detached_sweep_components_removed"] == 1
    assert report["blocked_centreline_cell_count"] == 0
    assert report["channel_components_4_connected"] == 1
    assert not result["chan"][:39].any()
    assert np.array_equal(result["bed"][:39], surface[:39])
    for name in ("stage", "width", "depth"):
        assert not result[name][:39].any()
    assert result["chan"][40, 30]
    assert result["chan"][80, 30]
    assert np.all(result["chan"][result["represented_centreline_mask"]])


def test_junction_transitions_are_gradual_and_minor_arm_keeps_its_hierarchy():
    spec = _site(shape=(121, 101))
    surface = np.full((spec.nu, spec.nv), 2.0)
    graph = _graph([(55, 505), (505, 505), (1105, 305), (1105, 705)],
                   [(0, 1), (1, 2), (1, 3)], [180.0, 145.0, 20.0], [5.0, 4.0, 1.5])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    parent, major, minor = result["profiles"]
    assert minor["width_m"].max() <= 24.0
    assert major["width_m"].min() > minor["width_m"].max() * 5
    assert minor["width_m"][0] > minor["width_m"][len(minor["width_m"]) // 2]
    for profile in result["profiles"]:
        assert np.max(np.abs(np.diff(profile["width_m"]) / np.diff(profile["distance_m"]))) < 0.4
        assert np.all(np.diff(profile["stage_m"]) <= 1e-10)
    assert parent["stage_m"][-1] == pytest.approx(major["stage_m"][0])
    assert parent["stage_m"][-1] == pytest.approx(minor["stage_m"][0])
    assert ndi.label(result["chan"])[1] == 1


def test_longitudinal_profile_does_not_raise_water_over_an_interior_hill():
    spec = _site()
    surface = np.full((spec.nu, spec.nv), 2.0)
    surface[29:43, :] = 35.0
    graph = _graph([(55, 305), (755, 305)], [(0, 1)], [30.0])
    result = rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
    profile = result["profiles"][0]
    assert np.all(np.diff(profile["stage_m"]) <= 1e-10)
    assert profile["stage_m"].max() <= 1.2 + 1e-10
    assert not result["chan"][surface == 35.0].any()
    assert result["report"]["blocked_centreline_cell_count"] > 0


def test_graph_and_source_are_immutable_and_output_repeatable():
    spec = _site()
    surface = np.full((spec.nu, spec.nv), 2.0)
    ocean = np.zeros(surface.shape, bool)
    graph = _graph([(55, 305), (505, 305), (755, 155), (755, 455)],
                   [(0, 1), (1, 2), (1, 3)], [80.0, 55.0, 25.0])
    original = {name: value.copy() for name, value in vars(graph).items()}
    first = rasterize_channels(spec, surface, surface, ocean, graph)
    second = rasterize_channels(spec, surface, surface, ocean, graph)
    for name, value in original.items():
        assert np.array_equal(getattr(graph, name), value)
    assert np.array_equal(surface, np.full(surface.shape, 2.0))
    assert not ocean.any()
    for name in ("bed", "chan", "stage", "depth", "width"):
        assert np.array_equal(first[name], second[name])
    assert first["report"] == second["report"]


def test_width_transitions_match_at_shared_physical_points_across_resolutions():
    graph = _graph([(150, 500), (1250, 500), (2850, 200), (2850, 800)],
                   [(0, 1), (1, 2), (1, 3)], [140.0, 115.0, 18.0])
    results = []
    for spacing in (30.0, 100.0):
        spec = _site(spacing=spacing, shape=(int(3000 / spacing), int(1200 / spacing)))
        surface = np.full((spec.nu, spec.nv), 2.0)
        results.append(rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph))
    for fine, coarse in zip(results[0]["profiles"], results[1]["profiles"]):
        shared = np.linspace(0.0, fine["distance_m"][-1], 31)
        fine_width = np.interp(shared, fine["distance_m"], fine["width_m"])
        coarse_width = np.interp(shared, coarse["distance_m"], coarse["width_m"])
        assert np.max(np.abs(fine_width - coarse_width)) < 0.15


def test_invalid_source_or_dimensions_fail_before_modification():
    spec = _site()
    surface = np.full((spec.nu, spec.nv), 2.0)
    graph = _graph([(55, 305), (755, 305)], [(0, 1)], [20.0])
    graph.edge_w[0] = np.nan
    with pytest.raises(ValueError, match="dimensions"):
        rasterize_channels(spec, surface, surface, np.zeros(surface.shape, bool), graph)
