"""Independent saved topology, shared-bed and material-ledger checks."""

import numpy as np

from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_natural_river_network import load_natural_river_network


def _require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def audit_saved_network(*, network_record, hierarchy_record, geometry_record=None,
                        window_record=None):
    from terrain_pipeline.channel_geometry import load_natural_channel_geometry, load_natural_channel_window

    network = load_natural_river_network(**network_record)
    hierarchy = load_basin_hierarchy(**hierarchy_record)
    source, saved = hierarchy["arrays"], network["arrays"]
    metadata = network["metadata"]
    _require(metadata["hierarchy_identity_sha256"] == hierarchy["identity_sha256"],
             "network/hierarchy identity mismatch")
    for key, source_key in (("source_height_m", "height_m"), ("valid_mask", "valid_mask"),
                            ("protected_mask", "protected_mask"), ("open_boundary_mask", "open_boundary_mask")):
        _require(np.array_equal(saved[key], source[source_key]), "source differs: " + key)
    usable = saved["valid_mask"].ravel() & ~saved["protected_mask"].ravel()
    receiver = source["receiver"].copy()
    receiver[~usable] = -1
    donors = np.flatnonzero(usable & (receiver >= 0))
    receiver[donors[~usable[receiver[donors]]]] = -1
    _require(np.array_equal(saved["receiver"], receiver), "saved routing differs from protected source")
    order = saved["routing_order"]
    _require(np.array_equal(np.sort(order), np.arange(receiver.size)), "routing order is not a full permutation")
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    edges_all = np.flatnonzero(receiver >= 0)
    _require(np.all(rank[receiver[edges_all]] < rank[edges_all]), "routing order or DAG invalid")
    area = np.where(usable, float(metadata["spacing_m"]) ** 2, 0.)
    terminals = np.full(receiver.size, -1, np.int64)
    for cell in order:
        if usable[cell]:
            terminals[cell] = cell if receiver[cell] < 0 else terminals[receiver[cell]]
    for cell in order[::-1]:
        if usable[cell] and receiver[cell] >= 0:
            area[receiver[cell]] += area[cell]
    _require(np.allclose(saved["contributing_area_m2"], area, rtol=0, atol=1e-9),
             "saved contribution area differs from source accumulation")
    physical_recipe = metadata["recipe"]
    for index, scenario in enumerate(metadata["forcing"]):
        density = scenario["rainfall_mm"] / 1000. * physical_recipe["runoff_coefficient"] / scenario["duration_s"]
        density += physical_recipe["baseflow_mm_per_day"] / 1000. / 86400.
        local_q = np.where(usable, metadata["spacing_m"] ** 2 * density, 0.)
        expected_q = local_q.copy()
        for cell in order[::-1]:
            if usable[cell] and receiver[cell] >= 0:
                expected_q[receiver[cell]] += expected_q[cell]
        _require(np.allclose(saved["local_q_m3_s"][index], local_q, rtol=1e-12, atol=1e-14),
                 "saved rainfall local discharge differs")
        _require(np.allclose(saved["routed_q_m3_s"][index], expected_q, rtol=1e-12, atol=1e-14),
                 "saved rainfall accumulation differs")
    mask = saved["selected_basin_mask"].ravel()
    _require(mask.any() and not np.any(mask & ~usable), "invalid selected basin coverage")
    chosen_terminal = np.unique(terminals[mask])
    _require(chosen_terminal.size == 1 and chosen_terminal[0] >= 0, "selected basin splices distinct terminal basins")
    _require(np.array_equal(mask, usable & (terminals == chosen_terminal[0])), "selected basin is incomplete")
    nodes = saved["node_cell_ids"]
    edges = saved["edge_cell_ids"]
    _require(edges.size > 0, "selected natural river network is empty")
    _require(np.all(mask[nodes]), "river nodes leave selected basin")
    _require(np.array_equal(receiver[edges[:, 0]], edges[:, 1]), "selected edges differ from source topology")
    _require(len(set(edges[:, 0].tolist())) == len(edges), "duplicate outgoing channel edge")
    out = dict(edges.tolist())
    for node in nodes:
        _require(node in out or node == chosen_terminal[0], "river ends early before basin terminal")
    _require(chosen_terminal[0] in nodes, "river misses explicit basin terminal")
    covered = []
    for start, stop in zip(saved["reach_offsets"][:-1], saved["reach_offsets"][1:]):
        cells = saved["reach_cell_ids"][start:stop]
        _require(cells.size >= 2, "reach has no edge")
        covered.extend(zip(cells[:-1].tolist(), cells[1:].tolist()))
    _require(sorted(covered) == sorted(map(tuple, edges.tolist())), "reach coverage lost or duplicated edges")
    native = saved["node_native_xyz_m"]
    _require(np.array_equal(native[:, 1], source["height_m"].ravel()[nodes]), "native node elevation differs")
    normal_q = saved["node_representative_q_m3_s"]
    _require(np.isfinite(normal_q).all() and np.all(normal_q >= 0), "invalid representative discharge")
    node_indices = np.searchsorted(nodes, edges)
    incoming_q = np.zeros(nodes.size)
    np.add.at(incoming_q, node_indices[:, 1], normal_q[node_indices[:, 0]])
    _require(np.all(normal_q + 1e-12 >= incoming_q), "junction representative Q is not conservative")
    checks = {"source_unchanged": True, "routing_dag": True, "single_complete_contribution_basin": True,
              "downstream_closed": True, "reach_edge_coverage": True, "junction_nonnegative_local_supply": True,
              "independent_area_accumulation": True, "independent_four_scenario_discharge": True}
    report = {"schema": "td-natural-river-independent-audit-v1", "scope": "static candidate geometry only",
              "checks": checks, "network_identity_sha256": network["identity_sha256"],
              "selected_terminal_cell_id": int(chosen_terminal[0]), "selected_area_m2": float(area[chosen_terminal[0]]),
              "selected_nodes": int(nodes.size), "selected_edges": int(len(edges)),
              "solver_advanced": False, "hydraulic_ready": False, "natural_outlet_verified": False,
              "publishable": False}
    if geometry_record is not None:
        geometry = load_natural_channel_geometry(**geometry_record)
        bed = geometry["arrays"]
        _require(geometry["metadata"]["network_identity_sha256"] == network["identity_sha256"], "geometry network mismatch")
        _require(np.array_equal(bed["node_cell_ids"], nodes) and np.array_equal(bed["edge_cell_ids"], edges), "geometry graph mismatch")
        expected = bed["node_world_xyz_m"][node_indices]
        _require(np.array_equal(bed["edge_centerline_xyz_m"], expected), "confluence does not share exact bed endpoints")
        _require(np.all(expected[:, 1, 1] <= expected[:, 0, 1] + 1e-9), "candidate centerline is uphill")
        sections = bed["edge_sections_xyz_m"].reshape(-1, 2, 3, 3)
        _require(np.array_equal(sections[:, :, 1], expected), "section centers differ from shared bed")
        checks.update(shared_bed_endpoints=True, nonascending_bed=True, section_centers_bound_to_bed=True)
        report["geometry_identity_sha256"] = geometry["identity_sha256"]
    if window_record is not None:
        window = load_natural_channel_window(**window_record)
        samples = window["arrays"]
        cut = samples["actual_cut_m"]
        _require(np.array_equal(samples["bounded_surface_m"], samples["source_surface_m"] - cut), "window bed/cut relation differs")
        _require(np.all(cut >= 0) and not np.any(cut[samples["protected_mask"]] > 0), "negative/protected cut")
        weights = np.ones(cut.shape)
        weights[[0, -1], :] *= .5
        weights[:, [0, -1]] *= .5
        spacing = window["metadata"]["spacing_m"]
        origin = window["metadata"]["origin_m_xz"]
        x_coordinates = origin[0] + np.arange(cut.shape[1]) * spacing
        z_coordinates = origin[1] + np.arange(cut.shape[0]) * spacing
        source_x = (x_coordinates - metadata["origin_m_xz"][0]) / metadata["spacing_m"]
        source_z = (z_coordinates - metadata["origin_m_xz"][1]) / metadata["spacing_m"]
        _require(source_x.min() >= 0 and source_z.min() >= 0 and
                 source_x.max() <= source["height_m"].shape[1] - 1 and
                 source_z.max() <= source["height_m"].shape[0] - 1,
                 "saved fine window leaves source domain")
        lower_x = np.floor(source_x).astype(np.int64)
        lower_z = np.floor(source_z).astype(np.int64)
        upper_x = np.minimum(lower_x + 1, source["height_m"].shape[1] - 1)
        upper_z = np.minimum(lower_z + 1, source["height_m"].shape[0] - 1)
        fraction_x = source_x - lower_x
        fraction_z = source_z - lower_z
        north = source["height_m"][np.ix_(lower_z, lower_x)] * (1 - fraction_x)
        north += source["height_m"][np.ix_(lower_z, upper_x)] * fraction_x
        south = source["height_m"][np.ix_(upper_z, lower_x)] * (1 - fraction_x)
        south += source["height_m"][np.ix_(upper_z, upper_x)] * fraction_x
        independent_source = north * (1 - fraction_z[:, None]) + south * fraction_z[:, None]
        _require(np.allclose(samples["source_surface_m"], independent_source, rtol=0, atol=1e-8),
                 "fine sample source differs from original TD bilinear surface")
        volume = float(np.sum(weights * cut) * spacing ** 2)
        reported = window["metadata"]["summary"]["actual_cut_volume_m3"]
        _require(np.isclose(volume, reported, rtol=1e-12, atol=1e-9), "window material ledger differs")
        if geometry_record is not None:
            _require(window["metadata"]["geometry_identity_sha256"] == report["geometry_identity_sha256"], "window geometry mismatch")
        _require(window["metadata"]["network_identity_sha256"] == network["identity_sha256"], "window network mismatch")
        checks.update(window_cut_relation=True, protected_cut_zero=True, window_material_ledger=True,
                      window_source_sampling=True)
        report["window_material_cut_m3"] = volume
    return report
