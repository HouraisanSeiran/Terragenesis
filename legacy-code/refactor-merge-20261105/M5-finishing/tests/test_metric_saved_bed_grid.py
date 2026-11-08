import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import json
from pathlib import Path

import numpy as np
import pytest

import terrain_pipeline.channel_geometry as sampler
from terrain_pipeline.channel_geometry import _piece_geometry, _sample_piece_points

ROOT = Path(__file__).resolve().parents[1]
REAL_REPORT = (
    ROOT
    / "verification/hydrological-planning-domain/full-edges-v5-20261014-03"
    / "edge-8470-8600-v7-shared-sections-owned-halo2/report.json"
)


def _bed(x, z):
    return 2.0 * x - 3.0 * z + 7.0


def _sparse_fan4():
    # sparse fan of 4 triangles across cells [[0,0],[2,0]] (hole at cell 1)
    origin = [-10.0, -20.0]
    spacing = 1.0
    cells = np.array([[0, 0], [2, 0]], dtype=np.int64)

    verts = []
    tris = []
    tri_local = np.array(
        [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], dtype=np.int64
    )
    for ci, (cx, cz) in enumerate(cells):
        x0 = origin[0] + cx * spacing
        z0 = origin[1] + cz * spacing
        corners = np.array(
            [
                [x0, z0],
                [x0 + spacing, z0],
                [x0 + spacing, z0 + spacing],
                [x0, z0 + spacing],
                [x0 + 0.5 * spacing, z0 + 0.5 * spacing],
            ],
            dtype=np.float64,
        )
        base = 5 * ci
        verts.append(corners)
        tris.append(tri_local + base)
    vertices = np.concatenate(verts, axis=0)
    triangles = np.concatenate(tris, axis=0)
    bed = _bed(vertices[:, 0], vertices[:, 1])

    # node endpoints along x, arbitrary (unused by sampling here) source edges
    node_xz = np.array([[-10.0, -20.0], [-7.0, -20.0]], dtype=np.float64)
    node_source_edges = np.array([[12, 34], [12, 34]], dtype=np.int64)
    node_edge_fractions = np.array([0.0, 1.0], dtype=np.float64)
    receiver = np.array([1, -1], dtype=np.int64)

    return {
        "identity": "piece0",
        "parent_detail_identity": "detail0",
        "frozen_plan_identity": "plan0",
        "fine_spacing_m": spacing,
        "mesh_origin_xz_m": np.array(origin, dtype=np.float64),
        "shared_sections": [],
        "source_path": "test.npz",
        "archive_sha256": "0" * 64,
        "arrays": {
            "cells": cells,
            "vertices_xz_m": vertices,
            "triangles": triangles,
            "bed_elevation_m": bed,
            "node_xz_m": node_xz,
            "node_source_edges": node_source_edges,
            "node_edge_fractions": node_edge_fractions,
            "receiver": receiver,
        },
    }


@pytest.fixture()
def raw():
    return _sparse_fan4()


@pytest.fixture()
def piece(raw):
    return _piece_geometry(raw)


def test_piece_geometry_identity_and_plan(piece, raw):
    assert piece["identity"] == "piece0"
    assert piece["parent_detail_identity"] == "detail0"
    assert piece["frozen_plan_identity"] == "plan0"
    assert piece["shared_sections"] == []
    assert piece["spacing_m"] == pytest.approx(raw["fine_spacing_m"])
    np.testing.assert_allclose(piece["origin_xz_m"], raw["mesh_origin_xz_m"])


def test_piece_geometry_arrays_and_bbox(piece):
    assert piece["cells"].shape == (2, 2)
    assert piece["triangles"].shape == (8, 3)
    assert piece["vertices_xz_m"].shape == (10, 2)
    np.testing.assert_allclose(
        piece["bbox_min_xz_m"], [-10.0, -20.0]
    )
    np.testing.assert_allclose(
        piece["bbox_max_xz_m"], [-7.0, -19.0]
    )


def test_piece_geometry_lookup_edges_and_bed(piece):
    lookup = piece["lookup"]
    assert lookup is not None
    bed = piece["bed_elevation_m"]
    assert bed.shape == (10,)
    np.testing.assert_allclose(
        bed, _bed(piece["vertices_xz_m"][:, 0], piece["vertices_xz_m"][:, 1])
    )
    for key in ("node_xz_m", "node_source_edges", "node_edge_fractions",
                "receiver"):
        assert key in piece


def test_piece_geometry_no_input_mutation(raw):
    snap = {k: (v.copy() if isinstance(v, np.ndarray) else v)
            for k, v in raw.items()}
    snap_arrays = {k: v.copy() for k, v in raw["arrays"].items()}
    _piece_geometry(raw)
    for k, v in snap.items():
        if isinstance(v, np.ndarray):
            np.testing.assert_array_equal(raw[k], v)
        else:
            assert raw[k] == v
    for k, v in snap_arrays.items():
        np.testing.assert_array_equal(raw["arrays"][k], v)


def _sample(piece, *pts):
    return _sample_piece_points(piece, np.array(pts, dtype=np.float64))


def test_sample_vertices(piece):
    vx, vz = piece["vertices_xz_m"][:, 0], piece["vertices_xz_m"][:, 1]
    vals, mask = _sample(piece, *[[x, z] for x, z in zip(vx, vz)])
    assert mask.all()
    np.testing.assert_allclose(vals, _bed(vx, vz), atol=1e-10)


def test_sample_triangle_interiors_and_center(piece):
    pts = []
    verts = piece["vertices_xz_m"]
    for tri in piece["triangles"]:
        cx = verts[tri, 0].mean()
        cz = verts[tri, 1].mean()
        pts.append([cx, cz])
        # small off-center point
        a = verts[tri[0]]
        pts.append([0.6 * cx + 0.4 * a[0], 0.6 * cz + 0.4 * a[1]])
    vals, mask = _sample(piece, *pts)
    assert mask.all()
    np.testing.assert_allclose(
        vals, _bed(np.array(pts)[:, 0], np.array(pts)[:, 1]), atol=1e-10
    )


def test_sample_edge_and_boundary_supported(piece):
    pts = [[-10.0, -20.0], [-9.5, -20.0], [-7.0, -20.0], [-7.0, -19.0]]
    vals, mask = _sample(piece, *pts)
    assert mask.all()
    np.testing.assert_allclose(
        vals, _bed(np.array(pts)[:, 0], np.array(pts)[:, 1]), atol=1e-10
    )


def test_sample_unsupported_hole_and_outside(piece):
    vals, mask = _sample(piece, [-8.5, -19.5], [-6.0, -19.0])
    assert not mask.any()
    assert np.isnan(vals).all()


def test_sample_empty(piece):
    vals, mask = _sample_piece_points(piece, np.empty((0, 2), dtype=np.float64))
    assert vals.shape == (0,)
    assert mask.shape == (0,)
    assert mask.dtype == bool


def test_sample_agrees_with_analytic_plane(piece):
    pts = [[-9.5, -19.5], [-8.0, -19.5], [-7.6, -19.2]]
    vals, mask = _sample(piece, *pts)
    assert mask.all()
    expected = _bed(np.array(pts)[:, 0], np.array(pts)[:, 1])
    np.testing.assert_allclose(vals, expected, atol=1e-10)

def test_sample_rejects_nonfinite_and_bad_shape(piece):
    with pytest.raises((ValueError, np.linalg.LinAlgError)):
        _sample_piece_points(piece, np.array([[np.nan, -19.0]]))
    with pytest.raises((ValueError, np.linalg.LinAlgError)):
        _sample_piece_points(piece, np.array([[np.inf, -19.0]]))
    with pytest.raises((ValueError, IndexError, np.linalg.LinAlgError)):
        _sample_piece_points(piece, np.array([[-9.0, -19.0, -19.0]]))


@pytest.mark.parametrize("bad", [True, "1", 0])
def test_invalid_spacing(raw, bad):
    raw["fine_spacing_m"] = bad
    with pytest.raises((TypeError, ValueError)):
        _piece_geometry(raw)


def test_float_cells_rejected(raw):
    raw["arrays"]["cells"] = raw["arrays"]["cells"].astype(np.float64)
    with pytest.raises((TypeError, ValueError)):
        _piece_geometry(raw)


def test_parent_missing_rejected(raw):
    raw.pop("parent_detail_identity")
    with pytest.raises((KeyError, TypeError, ValueError)):
        _piece_geometry(raw)


def test_bad_source_edge_rows_rejected(raw):
    raw["arrays"]["node_source_edges"] = np.zeros((1, 2), dtype=np.int64)
    with pytest.raises((ValueError, IndexError, KeyError)):
        _piece_geometry(raw)


def test_degenerate_ids_rejected(raw):
    raw["arrays"]["node_source_edges"] = np.array(
        [[12, 12], [12, 12]], dtype=np.int64
    )
    with pytest.raises((ValueError, KeyError, TypeError)):
        _piece_geometry(raw)


def test_corrupt_piece_triangles_raises_linalg(piece):
    bad = dict(piece)
    bad["triangles"] = np.zeros_like(piece["triangles"])
    with pytest.raises(np.linalg.LinAlgError):
        _sample_piece_points(bad, np.array([[-9.5, -19.5]]))


def test_lookup_valueerror_propagates(piece, monkeypatch):
    def boom(point, lookup, origin, spacing):
        raise ValueError("corrupt lookup")

    monkeypatch.setattr(sampler, "_cell_at_point", boom, raising=True)
    with pytest.raises(ValueError, match="corrupt lookup"):
        _sample_piece_points(piece, np.array([[-9.5, -19.5]]))


@pytest.mark.skipif(not REAL_REPORT.exists(), reason="real report not present")
def test_real_piece000_matches_saved_bed():
    from tools.prepare_hydrology_domains import _read_bed_piece

    report = json.loads(REAL_REPORT.read_text(encoding="utf-8"))
    rel = report["piece_paths"][0].replace("\\", "/")
    path = ROOT / rel
    import hashlib
    record = _read_bed_piece(path)
    record["source_path"] = str(path)
    record["archive_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    snap = {k: (v.copy() if isinstance(v, np.ndarray) else v)
            for k, v in record["arrays"].items()}
    piece = _piece_geometry(record)
    for k, v in snap.items():
        np.testing.assert_array_equal(record["arrays"][k], v)

    verts = piece["vertices_xz_m"]
    bed = piece["bed_elevation_m"]
    n = min(30, verts.shape[0])
    pts = verts[:n]
    vals, mask = _sample_piece_points(piece, pts)
    assert mask.all()
    np.testing.assert_allclose(vals, bed[:n], atol=1e-8)


def test_saved_bed_grid_sampling_two_piece_strip_near_shared_section():
    import copy, numpy as np

    left = copy.deepcopy(_sparse_fan4())
    right = copy.deepcopy(_sparse_fan4())
    left["identity"] = "left"
    left["source_path"] = "left.obj"
    right["identity"] = "right"
    right["source_path"] = "right.obj"
    left["arrays"] = dict(left["arrays"])
    right["arrays"] = dict(right["arrays"])
    left["arrays"]["node_xz_m"] = np.array([[-10, -19.5], [-9.5, -19.5]])
    left["arrays"]["node_edge_fractions"] = np.array([0.0, 0.5])
    right["arrays"]["node_xz_m"] = np.array([[-9.5, -19.5], [-9, -19.5]])
    right["arrays"]["node_edge_fractions"] = np.array([0.5, 1.0])
    left["shared_sections"] = [dict(parent_detail_identity="detail0", position_xz_m=[-9.5, -19.5], normal_xz=[0, 1], radius_m=0.5, offsets_m=[-0.5, 0.0, 0.5])]
    right["shared_sections"] = [dict(parent_detail_identity="detail0", position_xz_m=[-9.5, -19.5], normal_xz=[0, 1], radius_m=0.5, offsets_m=[-0.5, 0.0, 0.5])]

    origin = [-10, -20]
    shape_zx = (3, 3)
    spacing_m = 0.5
    for pieces in ([left, right], [right, left]):
        result = sampler.sample_saved_bed_grid(pieces, origin_xz_m=origin, shape_zx=shape_zx, spacing_m=spacing_m)
        xs = origin[0] + np.arange(shape_zx[1]) * spacing_m
        zs = origin[1] + np.arange(shape_zx[0]) * spacing_m
        xx, zz = np.meshgrid(xs, zs)
        expected = 2.0 * xx - 3.0 * zz + 7.0
        assert result["supported_mask"].shape == shape_zx
        assert result["supported_mask"].all()
        assert np.allclose(result["bed_m"], expected)
        assert np.array_equal(result["owner_piece_index"], np.tile([0, 1, 1], (3, 1)))


def test_saved_bed_grid_sampling_real_report_optional():
    import hashlib, json, os
    import numpy as np
    from tools.prepare_hydrology_domains import _read_bed_piece

    if REAL_REPORT is None or not os.path.exists(REAL_REPORT):
        import pytest
        pytest.skip("real report not available")

    report = json.loads(REAL_REPORT.read_text())
    root = ROOT
    records = []
    for rel in report["piece_paths"]:
        path = os.path.join(root, rel)
        record = _read_bed_piece(path)
        record = dict(record)
        record["source_path"] = str(path)
        with open(path, "rb") as f:
            record["archive_sha256"] = hashlib.sha256(f.read()).hexdigest()
        records.append(record)

    origin_xz_m = (records[0]["arrays"]["node_xz_m"][1] - 20).tolist()
    result = sampler.sample_saved_bed_grid(records, origin_xz_m=origin_xz_m, shape_zx=(41, 41), spacing_m=1.0)
    mask = np.asarray(result["supported_mask"])
    n_supported = int(mask.sum())
    assert 0 < n_supported < 1681
    assert len(result["provenance"]["canonical_pieces"]) == 29
    assert result["provenance"]["maximum_shared_section_difference_m"] <= 1e-6
    assert np.all(np.asarray(result["owner_piece_index"])[mask] >= 0)
    assert np.all(np.asarray(result["owner_piece_index"])[~mask] == -1)
    assert np.all(np.isnan(np.asarray(result["bed_m"])[~mask]))


import copy

@pytest.fixture(scope='module')
def real_records():
    if not REAL_REPORT.exists():
        pytest.skip('missing real report')
    from tools.prepare_hydrology_domains import _read_bed_piece
    import hashlib
    report = json.loads(REAL_REPORT.read_text(encoding='utf-8'))
    records = []
    for rel in report['piece_paths']:
        path = ROOT / rel
        record = _read_bed_piece(path)
        record['source_path'] = str(path)
        record['archive_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(record)
    return records


def test_real_grid_shuffle_and_5m(real_records):

    first = real_records[0]
    node_xz = first["arrays"]["node_xz_m"]
    center = node_xz[1]
    origin = (center[0] - 20.0, center[1] - 20.0)

    kwargs = dict(pieces=real_records, origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0)
    res_a = sampler.sample_saved_bed_grid(**kwargs)
    res_b = sampler.sample_saved_bed_grid(pieces=list(reversed(real_records)), origin_xz_m=origin, shape_zx=(41,41),spacing_m=1.0)

    np.testing.assert_allclose(res_a["bed_m"], res_b["bed_m"], equal_nan=True)
    np.testing.assert_array_equal(res_a["supported_mask"], res_b["supported_mask"])
    np.testing.assert_array_equal(res_a["owner_piece_index"], res_b["owner_piece_index"])

    kwargs5 = dict(pieces=real_records, origin_xz_m=origin, shape_zx=(9, 9), spacing_m=5.0)
    res5 = sampler.sample_saved_bed_grid(**kwargs5)

    one_m = sampler.sample_saved_bed_grid(pieces=real_records, origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0)
    np.testing.assert_allclose(res5["bed_m"], one_m["bed_m"][::5, ::5], equal_nan=True)
    np.testing.assert_array_equal(res5["supported_mask"], one_m["supported_mask"][::5, ::5])
    np.testing.assert_array_equal(res5["owner_piece_index"], one_m["owner_piece_index"][::5, ::5])


@pytest.mark.parametrize(
    "case,expected_msg",
    [
        ("duplicate", "duplicate piece identity"),
        ("parent", "parent_detail_identity mismatch"),
        ("gap", "fraction gap or overlap"),
        ("conflict", "shared section beds differ beyond tolerance"),
    ],
)
def test_malformed_input_cases(real_records, case, expected_msg):

    records = list(real_records)
    first = copy.copy(records[0])
    first["arrays"] = dict(records[0]["arrays"])

    if case == "duplicate":
        records = records + [records[0]]
    elif case == "parent":
        first["parent_detail_identity"] = "wrong"
        records[0] = first
    elif case == "gap":
        first["arrays"]["node_edge_fractions"] = np.array([0.0, 1.0 / 30.0])
        first["arrays"]["node_xz_m"] = np.array([real_records[0]["arrays"]["node_xz_m"][0], real_records[0]["arrays"]["node_xz_m"][0]+(real_records[-1]["arrays"]["node_xz_m"][1]-real_records[0]["arrays"]["node_xz_m"][0])/30.])
        records[0] = first
    elif case == "conflict":
        bed = first["arrays"]["bed_elevation_m"]
        first["arrays"]["bed_elevation_m"] = np.asarray(bed) + 0.1
        records[0] = first

    node_xz = real_records[0]["arrays"]["node_xz_m"]
    center = node_xz[1]
    origin = (center[0] - 20.0, center[1] - 20.0)

    with pytest.raises(ValueError, match=expected_msg):
        sampler.sample_saved_bed_grid(
            pieces=records, origin_xz_m=origin, shape_zx=(41, 41), spacing_m=1.0
        )


def test_shared_line_beyond_radius(real_records):
    sec = real_records[0]["shared_sections"][0]
    origin = np.asarray(sec["position_xz_m"]) + np.asarray(sec["normal_xz"]) * (sec["radius_m"] + 1)
    res = sampler.sample_saved_bed_grid(
        real_records, origin_xz_m=origin, shape_zx=(1, 1), spacing_m=1.0
    )
    assert not res["supported_mask"][0, 0]
    assert res["owner_piece_index"][0, 0] == -1
    assert np.isnan(res["bed_m"][0, 0])
