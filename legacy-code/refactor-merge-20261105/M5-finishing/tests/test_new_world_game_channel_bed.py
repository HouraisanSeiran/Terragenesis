import numpy as np
from terrain_pipeline.channel_geometry import solve_shared_bed


def test_confluence_shares_downstream_bed():
    bed, component, reasons = solve_shared_bed([10, 9, 11, 10], [[0, 2], [1, 2], [2, 3]])
    np.testing.assert_allclose(bed, [10, 9, 9, 9])
    assert len(set(component)) == 1 and reasons == ['accepted']


def test_downstream_cap_rejects_whole_connected_path():
    bed, _, reasons = solve_shared_bed([10, 12, 15], [[0, 1], [1, 2]])
    assert np.isnan(bed).all() and reasons == ['downstream_cut_cap']


def test_crossing_geometry_cycle_does_not_change_original_flow():
    from terrain_pipeline.channel_geometry import solve_shared_bed_scc
    # Two source paths traverse the same two physical cells in opposite order.
    arcs = np.array([[0, 2], [2, 3], [3, 4], [1, 3], [3, 2], [2, 5]])
    bed, _, strong, bad = solve_shared_bed_scc([10, 10, 9, 9.5, 8, 8], arcs)
    assert strong[2] == strong[3]
    assert bed[2] == bed[3] == 9
    assert not bad.any()
    assert np.all(bed[arcs[:, 0]] >= bed[arcs[:, 1]])
    # The input retains its original arc list; SCC is only a bed constraint.
    assert len(arcs) == 6
