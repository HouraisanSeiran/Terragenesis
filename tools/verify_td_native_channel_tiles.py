"""Bounded four-tile prototype and expression-sampling review of pinned geometry."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_native_channel_geometry import load_channel_geometry
from terrain_pipeline.td_native_channel_tiles import TileRecipe, audit_tile_geometry, build_channel_tile, load_channel_tile, save_channel_tile, split_window_2x2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry-report", type=Path, required=True)
    parser.add_argument("--geometry-report-sha256", required=True)
    args = parser.parse_args()
    if file_sha256(args.geometry_report) != args.geometry_report_sha256:
        raise ValueError("geometry report SHA mismatch")
    record = json.loads(args.geometry_report.read_text(encoding="utf-8"))["geometry"]
    geometry = load_channel_geometry(**record)
    arrays, metadata = geometry["arrays"], geometry["metadata"]
    indices = np.searchsorted(arrays["node_cell_ids"], arrays["edge_cell_ids"])
    active = arrays["edge_geometry_active"]
    incoming = np.bincount(indices[active, 1], minlength=len(arrays["node_cell_ids"]))
    q_mean = arrays["node_receiver_interval_mean_q_m3_s"][indices[:, 0]]
    selected = np.flatnonzero(active & (incoming[indices[:, 1]] >= 2))
    if not len(selected):
        selected = np.flatnonzero(active)
    if not len(selected):
        raise ValueError("no active prototype edge")
    selected_edge = int(selected[np.argmax(q_mean[selected])])
    center = arrays["node_world_xyz_m"][indices[selected_edge, 1], [0, 2]] - metadata["origin_m_xz"]
    extent = (np.array(metadata["grid_shape"])[::-1] - 1) * metadata["spacing_m"]
    width_m = 254
    if np.any(extent < width_m):
        raise ValueError("native extent too small for bounded prototype")
    first = np.maximum(0, np.minimum(np.floor(center / 2.) * 2. - 128., np.floor((extent - width_m) / 2.) * 2.)).astype(int)
    window = (int(first[0]), int(first[0]) + width_m, int(first[1]), int(first[1]) + width_m)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / "verification" / "td-native-channel-tiles" / ("A-prototype-" + stamp)
    samples = {}
    for spacing in (.5, 1., 2.):
        lattice_window = tuple(int(value / spacing) for value in window)
        samples[spacing] = build_channel_tile(geometry, window=lattice_window, recipe=TileRecipe(spacing))
    parts = [build_channel_tile(geometry, window=part) for part in split_window_2x2(window)]
    pins = []
    for index, tile in enumerate(parts):
        path = destination / ("tile-" + str(index) + ".npz")
        save_channel_tile(path, tile)
        pins.append(dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=tile["identity_sha256"]))
    loaded = [load_channel_tile(**pin, geometry=geometry) for pin in pins]
    reverse = [load_channel_tile(**pin, geometry=geometry) for pin in reversed(pins)]
    for tile in loaded:
        audit_tile_geometry(tile, geometry)
    if [tile["identity_sha256"] for tile in loaded] != [tile["identity_sha256"] for tile in reversed(reverse)]:
        raise ValueError("load order changed tiles")
    for name in ("native_bilinear_bed_m", "candidate_cut_m", "candidate_bed_m"):
        if not np.array_equal(parts[0]["arrays"][name][:, -1], parts[1]["arrays"][name][:, 0]) or not np.array_equal(parts[0]["arrays"][name][-1], parts[2]["arrays"][name][0]):
            raise ValueError("shared boundary differs")
        for part in parts:
            first_x, last_x, first_z, last_z = part["metadata"]["window"]
            if not np.array_equal(part["arrays"][name], samples[1.]["arrays"][name][first_z-window[2]:last_z-window[2]+1, first_x-window[0]:last_x-window[0]+1]):
                raise ValueError("tile differs from global window")
    reviews = []
    for spacing in (1., 2.):
        fine = samples[.5]["arrays"]["candidate_bed_m"]
        coarse = samples[spacing]["arrays"]["candidate_bed_m"]
        stride = int(spacing / .5)
        common = float(np.max(np.abs(fine[::stride, ::stride] - coarse)))
        coordinates = np.arange(fine.shape[0]) / stride
        coarse_axis = np.arange(coarse.shape[0])
        along_x = np.array([np.interp(coordinates, coarse_axis, row) for row in coarse])
        reconstructed = np.array([np.interp(coordinates, coarse_axis, column) for column in along_x.T]).T
        reviews.append(dict(spacing_m=spacing, common_world_max_difference_m=common,
                            bilinear_reconstruction_max_difference_m=float(np.max(np.abs(reconstructed-fine))),
                            interpretation="expression sampling difference, not physical spatial convergence"))
        if common != 0.:
            raise ValueError("shared global points changed with spacing")
    if file_sha256(record["path"]) != record["expected_sha256"] or file_sha256(args.geometry_report) != args.geometry_report_sha256:
        raise ValueError("source pins changed during tile generation")
    report = dict(schema="td-native-channel-tiles-prototype-v1", geometry=record, tiles=pins,
                  selected_edge_id=selected_edge, selected_edge_cell_ids=arrays["edge_cell_ids"][selected_edge].tolist(),
                  selected_target_active_incoming_edges=int(incoming[indices[selected_edge, 1]]),
                  window_1m_global_lattice=window, physical_width_m=width_m,
                  shared_boundaries_exact=True, global_window_match=True, loading_order_independent=True,
                  explicit_geometry_audit_passed=True, cold_load_derives_geometry=False,
                  sampling_review=reviews, max_sample_shape=list(samples[.5]["arrays"]["candidate_bed_m"].shape),
                  max_sample_array_bytes=max(sum(values.nbytes for values in tile["arrays"].values()) for tile in samples.values()),
                  scope="native 30m bed bilinear derived expression only; no added TD landform information or water surface",
                  hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                  code_sha256={name: file_sha256(ROOT / name) for name in (
                      "terrain_pipeline/td_native_channel_tiles.py", "tests/test_td_native_channel_tiles.py", "tools/verify_td_native_channel_tiles.py")})
    publish_bytes(destination / "report.json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
