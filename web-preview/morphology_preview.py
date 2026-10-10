"""Read-only real-TD morphology candidate package for the local review UI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.mountain_source_adapter import load_bundle
from terrain_pipeline.surface_rivers.metric_delta_product import load_delta_candidate_product

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "verification/td-morphology-candidates/td256-20261010-01"
MAX_BYTES = 128 * 1024 * 1024


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _path(name):
    path = (BASE / name).resolve()
    if not path.is_relative_to(BASE) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("morphology artifact outside fixed package")
    return path


def _read_bundle(name, pin):
    path = _path(name)
    if _sha256(path) != pin["sha256"]:
        raise ValueError("morphology artifact SHA256 mismatch: " + name)
    return load_bundle(path, expected_sha256=pin["sha256"], validator=lambda value: None)


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _generic(name, summary):
    return _read_bundle(summary["artifacts"][name]["path"], summary["artifacts"][name])


def _event(metadata):
    return _plain(metadata.get("event_record"))


def catalog():
    summary = _json(BASE / "summary.json")
    body = dict(summary)
    expected_body_sha = body.pop("summary_body_sha256", None)
    actual_body_sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                               indent=2, allow_nan=False).encode("utf-8")).hexdigest()
    if expected_body_sha != actual_body_sha or summary.get("schema") != "td-real-morphology-candidate-set-v1":
        raise ValueError("morphology summary identity mismatch")
    source = Path(summary["source"]["path"]).resolve()
    if not source.is_relative_to(ROOT) or _sha256(source) != summary["source"]["sha256"]:
        raise ValueError("TD source pin changed")
    return {
        "schema": "td-real-morphology-catalog-v1",
        "status": summary["status"],
        "package": "verification/td-morphology-candidates/td256-20261010-01",
        "source": summary["source"],
        "summary_body_sha256": expected_body_sha,
        "parent_graph_identity_sha256": summary["parent_graph_identity_sha256"],
        "parent_geometry_identity_sha256": summary["parent_geometry_identity_sha256"],
        "terrain_identity_sha256": summary["terrain_identity_sha256"],
        "interpretation": summary["interpretation"],
        "capabilities": summary["capabilities"],
        "candidates": ["delta", "cutoff", "bank_pointbar", "braided", "alluvial_fan", "floodplain"],
    }


def _candidate_paths(arrays, metadata):
    encoded = arrays["candidate_polylines"]
    lengths = arrays["candidate_lengths"]
    edge_ids = metadata["candidate_edge_ids"]
    return [{"edge_id": edge_ids[index], "polyline": encoded[index, :int(lengths[index])].tolist()}
            for index in range(len(edge_ids))]


def saved_case():
    summary_path = BASE / "summary.json"
    summary = _json(summary_path)
    body = dict(summary)
    expected_body_sha = body.pop("summary_body_sha256", None)
    actual_body_sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                               indent=2, allow_nan=False).encode("utf-8")).hexdigest()
    if expected_body_sha != actual_body_sha or summary.get("schema") != "td-real-morphology-candidate-set-v1":
        raise ValueError("morphology summary identity mismatch")
    source = Path(summary["source"]["path"]).resolve()
    if not source.is_relative_to(ROOT) or _sha256(source) != summary["source"]["sha256"]:
        raise ValueError("TD source pin changed")
    inputs = _generic("inputs", summary)
    input_arrays, input_metadata = inputs["arrays"], inputs["metadata"]
    candidates = {}
    delta_pin = summary["artifacts"]["delta"]
    delta = load_delta_candidate_product(_path(delta_pin["path"]), expected_sha256=delta_pin["sha256"])
    if delta["identity_sha256"] != delta_pin["identity_sha256"]:
        raise ValueError("delta candidate identity mismatch")
    delta_arrays, delta_metadata = delta["arrays"], delta["metadata"]
    candidates["delta"] = {
        "status": delta_metadata["status"], "height_delta_m": delta_arrays["height_delta_m"].tolist(),
        "deposit_mask": delta_arrays["deposit_mask"].tolist(),
        "water_component_mask": delta_arrays["water_component_mask"].tolist(),
        "distributary_candidates": _candidate_paths(delta_arrays, delta_metadata),
        "event": _plain(delta_metadata["event_record"]),
        "material_ledger": _plain(delta_metadata["material_ledger"]),
    }
    for name, output_name, array_names in (
        ("cutoff", "cutoff", ("shortcut_xz_m", "loop_xz_m")),
        ("bank_pointbar", "bank", ("height_delta_m", "erosion_mask", "deposit_mask")),
        ("braided", "braided", ("bar_mask", "height_delta_m", "flow_split")),
        ("alluvial_fan", "fan", ("height_delta_m", "deposit_mask", "footprint")),
        ("floodplain", "floodplain", ("inundation_mask", "height_delta_m")),
    ):
        bundle = _generic(name, summary)
        arrays, metadata = bundle["arrays"], bundle["metadata"]
        value = {"status": metadata["status"], "event": _event(metadata),
                 "capabilities": _plain(metadata.get("capabilities", {}))}
        for array_name in array_names:
            value[array_name] = arrays[array_name].tolist()
        for metadata_name in ("material_ledger", "storage_proxy_m3", "candidate_paths", "solid_ledger"):
            if metadata_name in metadata:
                value[metadata_name] = _plain(metadata[metadata_name])
        candidates[output_name] = value
    return {
        "schema": "td-real-morphology-frontend-v1", "status": summary["status"],
        "summary_body_sha256": expected_body_sha, "source": summary["source"],
        "terrain": {"height_m": input_arrays["terrain_elevation_m"].tolist(),
                     "valid_mask": input_arrays["terrain_valid_mask"].tolist(),
                     "origin_x_m": input_metadata["origin_x_m"], "origin_z_m": input_metadata["origin_z_m"],
                     "spacing_m": input_metadata["spacing_m"], "coordinates": input_metadata["coordinates"]},
        "land_mask": input_arrays["land_mask"].tolist(), "water_mask": input_arrays["water_mask"].tolist(),
        "delta_path_cells": input_arrays["delta_path_cells"].tolist(),
        "centerline_xz_m": input_arrays["centerline_xz_m"].tolist(),
        "parent_graph_identity_sha256": summary["parent_graph_identity_sha256"],
        "parent_geometry_identity_sha256": summary["parent_geometry_identity_sha256"],
        "terrain_identity_sha256": summary["terrain_identity_sha256"],
        "interpretation": summary["interpretation"], "capabilities": summary["capabilities"],
        "candidates": candidates,
    }
