"""Saved fill-refusal geometry diagnosis, never a mesh or tolerance repair."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_fine_bed_raster import _context, _digest, _sample

BASE = ROOT / "verification/natural-river-network/fine-bed-raster-lake-entry-20261005-01"
INDEX_SHA = "113f3990de828f25f4b766afffa58c948a5d5aea12b9e2de05d383486795f759"
BASE_SHA = "ad414151aa9b2cede4f47b95fc5011f81ebc6ec1666f2ef01d333828e9ad295c"


def _distance(point, profile):
    distances = []
    for first, second in zip(profile[:-1], profile[1:]):
        displacement = second[[0, 2]] - first[[0, 2]]
        denominator = float(displacement @ displacement)
        fraction = float(np.clip((point - first[[0, 2]]) @ displacement / denominator, 0., 1.)) if denominator else 0.
        distances.append(float(np.linalg.norm(point - (first[[0, 2]] + fraction * displacement))))
    return min(distances)


def _port_diagnostic(context, profile):
    def evaluate(points):
        maximum_chord_error, minimum_clearance = 0., math.inf
        for first, second in zip(points[:-1], points[1:]):
            source_first = _sample(context, float(first[0]), float(first[2]))["height_m"]
            source_second = _sample(context, float(second[0]), float(second[2]))["height_m"]
            if source_first is None or source_second is None:
                raise ValueError("unknown source along saved port")
            for fraction in np.linspace(0., 1., 33):
                point = first + fraction * (second - first)
                source = _sample(context, float(point[0]), float(point[2]))["height_m"]
                if source is None:
                    raise ValueError("unknown port-interior source")
                chord = source_first + fraction * (source_second - source_first)
                maximum_chord_error = max(maximum_chord_error, abs(chord - source))
                minimum_clearance = min(minimum_clearance, source - float(point[1]))
        return {"sampled_max_source_relative_port_deviation_m": maximum_chord_error,
                "sampled_min_actual_source_minus_original_port_m": minimum_clearance}

    expanded = np.insert(profile, 2, (profile[1] + profile[2]) / 2., axis=0) if len(profile) == 4 else profile
    return {"original_profile_xyz_m": profile.tolist(), "original_profile": evaluate(profile),
            "collinear_center_inserted_profile": evaluate(expanded),
            "semantics": "33 probes per original/center-split segment; diagnostic only, not proof of edge continuity",
            "v2_port_continuity_certified": False}


def diagnose_saved_fill(base, hierarchy, sections, transitions):
    context = _context(hierarchy, base["selected_leaf_ids"], base["wet_protection"])
    if hierarchy["identity_sha256"] != base["hierarchy_identity_sha256"]:
        raise ValueError("diagnostic native parent mismatch")
    triangle_map = {triangle["triangle_id"]: triangle for triangle in base["triangles"]}
    entries = transitions["entries"]
    port_entries = {}
    for entry_index, entry in enumerate(entries):
        if entry["status"] == "candidate":
            port_entries.setdefault(entry["accepted_port_arc_id"], []).append(entry_index)
    grid, tile = base["grid"], base["grid"]["tile_cells"]
    origin, spacing = np.asarray(grid["origin_m_xz"], float), grid["spacing_m"]
    records, ports = [], {}
    packages = Counter()
    for window in base["windows"]:
        for cell in window["cells"]:
            if "fill_without_material" not in cell["rejection_reasons"]:
                continue
            row = window["global_origin_row_column"][0] + cell["local_index"] // tile
            column = window["global_origin_row_column"][1] + cell["local_index"] % tile
            xz = origin + (np.array([column, row]) + .5) * spacing
            actual = _sample(context, float(xz[0]), float(xz[1]))
            if actual != cell["source_sample"]:
                raise ValueError("saved refused cell source differs from actual native DEM")
            proposals = []
            for proposal in cell["triangle_sources"]:
                triangle = triangle_map[proposal["triangle_id"]]
                package = triangle["source_package"]
                if package == "09":
                    entry_indices = [triangle["source_entry_index"]]
                    parent = entries[entry_indices[0]]
                else:
                    entry_indices = port_entries.get(triangle["source_arc_id"], [])
                    parent = sections["mesh"]
                indices = parent["triangles"][triangle["source_triangle_index"]]
                points = np.asarray([parent["vertices_xyz_m"][index] for index in indices], float)
                if points.tolist() != triangle["vertices_xyz_m"] or indices != triangle["source_vertex_indices"]:
                    raise ValueError("saved refused triangle differs from pinned parent")
                native_vertices = [_sample(context, float(point[0]), float(point[2]))["height_m"] for point in points]
                if any(value is None for value in native_vertices):
                    raise ValueError("unknown source at diagnostic triangle vertex")
                weights = np.asarray(proposal["weights"], float)
                vertex_cut = np.asarray(native_vertices) - points[:, 1]
                source_chord = float(weights @ native_vertices)
                source_error = source_chord - actual["height_m"]
                interpolated_cut = float(weights @ vertex_cut)
                fill = proposal["bed_m"] - actual["height_m"]
                residual = fill - (source_error - interpolated_cut)
                if abs(residual) > 1e-9:
                    raise ValueError("fill/source-chord decomposition mismatch")
                interfaces = []
                for entry_index in entry_indices:
                    entry = entries[entry_index]
                    profile = np.asarray(entry["accepted_port_xyz_m"], float)
                    if entry_index not in ports:
                        ports[entry_index] = _port_diagnostic(context, profile)
                    interfaces.append({"entry_index": entry_index, "entry_id": entry["entry_id"],
                                       "accepted_port_arc_id": entry["accepted_port_arc_id"],
                                       "distance_to_upstream_port_m": _distance(xz, profile),
                                       "distance_to_anchor_profile_m": _distance(xz, np.asarray(entry["anchor_source_profile_xyz_m"], float))})
                packages[package] += 1
                proposals.append({"triangle_id": triangle["triangle_id"], "source_package": package,
                                  "source_entry_index": triangle.get("source_entry_index"),
                                  "source_triangle_index": triangle["source_triangle_index"],
                                  "source_vertex_indices": indices, "triangle_xyz_m": points.tolist(),
                                  "barycentric_weights": proposal["weights"],
                                  "station_columns": [index % 5 for index in indices] if package == "09" else None,
                                  "actual_native_vertex_height_m": native_vertices,
                                  "vertex_cut_m": vertex_cut.tolist(), "interpolated_cut_m": interpolated_cut,
                                  "source_chord_error_m": source_error, "fill_above_source_m": fill,
                                  "decomposition_residual_m": residual, "interfaces": interfaces})
            records.append({"global_key_row_column": [row, column], "center_xz_m": xz.tolist(),
                            "source_sample": actual, "saved_rejection_reasons": cell["rejection_reasons"],
                            "proposals": proposals})
    fills = [proposal["fill_above_source_m"] for cell in records for proposal in cell["proposals"]]
    result = {"schema": "td-entry-bank-fill-diagnosis-v1", "base_identity_sha256": base["identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "sections_identity_sha256": sections["identity_sha256"],
              "transitions_identity_sha256": transitions["identity_sha256"],
              "parameters": {"unchanged_fill_tolerance_m": base["parameters"]["conflict_tolerance_m"]},
              "cells": records, "ports": [{"entry_index": index, **value} for index, value in sorted(ports.items())],
              "summary": {"saved_fill_cells": len(records), "by_source_package_proposals": dict(packages),
                          "affected_entry_count": len(ports), "minimum_fill_m": min(fills) if fills else 0.,
                          "maximum_fill_m": max(fills) if fills else 0.},
              "root_cause": "absolute planar triangle target versus bilinear native DEM curvature; source chord minus remaining taper cut",
              "v2_status": "pending_full_port_and_coverage_contract; no mesh replacement or clipping performed",
              "hydraulic_ready": False, "natural_outlet_certified": False, "publish_ready": False}
    result["identity_sha256"] = _digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "verification/natural-river-network").resolve()) or output.exists():
        raise ValueError("new bounded verification diagnostic output required")

    def read(path, expected_sha):
        if path.stat().st_size > 64 * 1024**2 or file_sha256(path) != expected_sha:
            raise ValueError("diagnostic input file SHA/budget mismatch")
        return json.loads(path.read_text(encoding="utf-8"))

    index = read(BASE / "index.json", INDEX_SHA)
    base = read(Path(index["raster"]["path"]), BASE_SHA)
    pins = index["inputs"]
    sections = read(Path(pins["06_sections"]["path"]), pins["06_sections"]["sha256"])
    transitions = read(Path(pins["09_transitions"]["path"]), pins["09_transitions"]["sha256"])
    path = Path(pins["hierarchy"]["path"])
    if file_sha256(path) != pins["hierarchy"]["sha256"]:
        raise ValueError("diagnostic hierarchy SHA mismatch")
    with np.load(path, allow_pickle=False) as archive:
        manifest = json.loads(archive["manifest"].tobytes())
        hierarchy = {"arrays": {name: archive[name] for name in archive.files if name != "manifest"},
                     "metadata": manifest["metadata"], "identity_sha256": manifest["identity_sha256"]}
    record = diagnose_saved_fill(base, hierarchy, sections, transitions)
    record["input_pins"] = {"base": index["raster"], **pins}
    record["identity_sha256"] = _digest({key: value for key, value in record.items() if key != "identity_sha256"})
    payload = json.dumps(record, sort_keys=True, allow_nan=False, indent=2).encode("utf-8")
    if len(payload) > 64 * 1024**2:
        raise MemoryError("diagnostic output exceeds 64MiB")
    publish_bytes(output, payload)
    print(json.dumps(record["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
