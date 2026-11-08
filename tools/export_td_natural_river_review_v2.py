"""Enrich a pinned v1 review with saved discharge priors and the actual fine bed."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.runoff import _strict_json as _strict_json
from terrain_pipeline.td_natural_bed_identity import natural_bed_shape_identity
from terrain_pipeline.channel_geometry import load_natural_channel_geometry, load_natural_channel_window
from terrain_pipeline.td_natural_river_network import load_natural_river_network
from tools.export_td_natural_river_review import MAX_REVIEW_BYTES


def _read(path, digest):
    path = Path(path)
    if path.stat().st_size > MAX_REVIEW_BYTES or file_sha256(path) != digest:
        raise ValueError("review input SHA or byte budget mismatch")
    return _strict_json(path.read_text(encoding="utf-8"))


def _artifact(directory, pin):
    relative = Path(pin["path"])
    candidate = directory / relative
    if (relative.is_absolute() or relative.drive or ".." in relative.parts or
            not candidate.resolve().is_relative_to(directory.resolve())):
        raise ValueError("delivery artifact must remain inside its index directory")
    return candidate


def export_review_v2(output, *, index_path, index_sha256, max_bytes=MAX_REVIEW_BYTES):
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_REVIEW_BYTES:
        raise ValueError("bounded review byte budget required")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    index_path = Path(index_path)
    index = _read(index_path, index_sha256)
    flags = ("hydraulic_ready", "natural_outlet_verified", "publishable", "solver_advanced")
    if index.get("schema") != "td-natural-river-delivery-v1" or any(
            index.get(flag) is not False for flag in flags):
        raise ValueError("natural delivery schema or certification mismatch")
    records = {}
    for name in ("network", "geometry", "window"):
        pin = index["artifacts"][name]
        records[name] = {"path": str(_artifact(index_path.parent, pin)),
                         "expected_sha256": pin["sha256"],
                         "expected_identity": pin["identity_sha256"]}
    previous_pin = index["artifacts"]["review.json"]
    previous_path = _artifact(index_path.parent, previous_pin)
    record = _read(previous_path, previous_pin["sha256"])
    if (record.get("schema") != "td-natural-river-review-v1" or
            any(record.get(flag) is not False for flag in flags[:-1]) or
            record.get("capabilities", {}).get("solver_advanced") is not False):
        raise ValueError("saved v1 review schema or certification mismatch")
    network = load_natural_river_network(**records["network"])
    geometry = load_natural_channel_geometry(**records["geometry"])
    window = load_natural_channel_window(**records["window"])
    if (record["network_identity_sha256"] != network["identity_sha256"] or
    record["geometry_identity_sha256"] != geometry["identity_sha256"] or
            geometry["metadata"]["network_identity_sha256"] != network["identity_sha256"] or
            window["metadata"]["network_identity_sha256"] != network["identity_sha256"] or
            window["metadata"]["geometry_identity_sha256"] != geometry["identity_sha256"]):
        raise ValueError("saved review, geometry or window belongs to another network")
    arrays = network["arrays"]
    nodes = arrays["node_cell_ids"]
    record["schema"] = "td-natural-river-review-v2"
    record["solver_advanced"] = False
    record["bed_shape_identity_sha256"] = natural_bed_shape_identity(network, geometry)
    record["stable_network_identity_sha256"] = network["metadata"]["stable_identity_sha256"]
    window_summary = window["metadata"]["summary"]
    record["layer_status"] = {"network": "diagnostic_not_publishable",
                              "geometry": geometry["metadata"]["status"],
                              "fine_bed_window": window["metadata"]["status"]}
    record["status"] = ("diagnostic_failure" if "diagnostic_failure" in record["layer_status"].values()
                        else "diagnostic_not_publishable")
    record["quality_gates"] = {
        "fine_bed_geometry_ready": window["metadata"]["status"] != "diagnostic_failure",
        "requires_shared_fine_extension": window_summary["requires_shared_fine_extension"],
        "fine_window_needs_refinement_nodes": window_summary["needs_refinement_nodes"],
        "fine_window_clipped_boundary_nodes": window_summary["clipped_boundary_nodes"],
        "network_needs_refinement_edges": network["metadata"]["summary"]["refinement_edge_count"],
        "minimum_edge_target_spacing_m": float(arrays["edge_target_spacing_m"].min()),
    }
    record["source_pins"] = records
    record["parent_review"] = {"path": str(previous_path), "sha256": previous_pin["sha256"]}
    record["delivery_index"] = {"path": str(index_path), "sha256": index_sha256}
    record["exporter_sha256"] = file_sha256(__file__)
    for name in ("node_representative_q_m3_s", "edge_contributing_area_m2",
                 "edge_q_normal_m3_s", "edge_q_strong_m3_s", "edge_slope_m_per_m",
                 "edge_valley_support", "edge_closure_mask", "edge_refinement_reason_bits",
                 "edge_target_spacing_m"):
        record["network"][name] = arrays[name].tolist()
    for name in ("ordinary_active_frequency_fraction", "ordinary_active_duration_fraction",
                 "supply_frequency_fraction", "supply_duration_fraction", "baseflow_year_round_mask"):
        record["network"]["node_" + name] = arrays[name][nodes].tolist()
    record["basin_statistics"] = {name: value.tolist() for name, value in arrays.items()
                                  if name.startswith("basin_")}
    record["basin_statistics"]["terminal_kind_codes"] = {
        "internal_basin": 0, "engineered_open": 1, "protected_barrier": 2, "unknown_contact": 3,
    }
    samples = window["arrays"]
    record["fine_bed_window"] = {
        "identity_sha256": window["identity_sha256"], "metadata": window["metadata"],
        "shape_zx": list(samples["bounded_surface_m"].shape),
        "arrays": {name: value.ravel().tolist() for name, value in samples.items()},
    }
    record["layer_semantics"].update({
        "fine_bed_window": "saved bounded local bed; not a full-domain fine mosaic or a water surface",
        "discharge_priors": "fixed-scenario constant-rate runoff priors; not instantaneous hydraulic Q",
        "supply_fractions": "assumed scenario frequency/duration and baseflow; not observed permanence",
        "basin_statistics": "all exclusive terminal basins; statistics do not connect their river graphs",
        "identities": "geometry bundle identity includes event provenance; stable bed shape identity excludes strong forcing",
        "capabilities": "renderable inspection data only; quality_gates and layer_status govern geometry readiness",
    })
    record["capabilities"].update(fine_bed_window_3d=True, river_inspection_fields=True,
                                  fine_bed_window_geometry_ready=record["quality_gates"]["fine_bed_geometry_ready"],
                                  solver_advanced=False, water_surface_3d=False, time_playback=False)
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > max_bytes:
        raise ValueError("natural review byte budget exceeded before publication")
    for path, digest in [(index_path, index_sha256), (previous_path, previous_pin["sha256"])] + [
            (Path(pin["path"]), pin["expected_sha256"]) for pin in records.values()]:
        if file_sha256(path) != digest:
            raise ValueError("natural review input pin changed while reading")
    publish_bytes(output, payload)
    return {"path": str(output), "sha256": file_sha256(output), "bytes": len(payload),
            "schema": record["schema"], "solver_advanced": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_review_v2(args.output, index_path=args.index,
                                      index_sha256=args.index_sha256), ensure_ascii=False))


if __name__ == "__main__":
    main()
