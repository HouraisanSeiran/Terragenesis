"""Read-only global valley geometry coverage and scope-exclusion review."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from terrain_pipeline.common_infra import file_sha256

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "verification/td-valley-global-tiled/td1024-20261008-01"
PLAN = ROOT / "verification/td-river-network-expansion/td1024-20261008-01/network-plan.npz"
FAILURE = BASE / "failure-prefix.json"
EXCLUSION = ROOT / "verification/td-valley-global-tiled/td1024-20261011-01/scope-exclusion.json"


def _pin(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": file_sha256(path)}


def _edge_points(source, target, columns, terrain):
    points = []
    for left, right in zip(source, target):
        lr, lc = divmod(int(left), columns)
        rr, rc = divmod(int(right), columns)
        points.append([[terrain['x0_m'] + lc * terrain['dx_m'], terrain['z0_m'] + lr * terrain['dz_m']],
                       [terrain['x0_m'] + rc * terrain['dx_m'], terrain['z0_m'] + rr * terrain['dz_m']]])
    return points


def saved_case() -> dict:
    failure = json.loads(FAILURE.read_text(encoding="utf-8"))
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    diagnostic = json.loads((BASE / 'refusal-diagnostic.json').read_text(encoding='utf-8'))
    if (file_sha256(BASE / 'refusal-diagnostic.json') != exclusion['diagnostic_sha256']
            or file_sha256(FAILURE) != exclusion['failure_report_sha256']):
        raise ValueError('scope exclusion evidence checksum mismatch')
    plan_pin = _pin(PLAN)
    if plan_pin['sha256'] != failure['parent_network_plan']['sha256']:
        raise ValueError('global geometry plan checksum mismatch')
    if exclusion["source_sha256"] != failure["source"]["sha256"]:
        raise ValueError("scope exclusion source does not match global geometry source")
    if exclusion["refused_count"] != exclusion["unresolved_count"]:
        raise ValueError("scope exclusion contains accepted refused edges")
    with np.load(PLAN, allow_pickle=False) as archive:
        manifest = json.loads(archive['manifest'].tobytes())
        terrain = manifest['metadata']['terrain_metadata']
        if manifest['identity_sha256'] != exclusion['plan_identity_sha256']:
            raise ValueError('scope exclusion plan mismatch')
        source = archive["selected_edge_source_ids"]
        target = archive["selected_edge_target_ids"]
        height = archive['source_elevation_m']
        columns = int(height.shape[1])
        display_rows = np.unique(np.r_[np.arange(0, height.shape[0], 8), height.shape[0]-1])
        display_cols = np.unique(np.r_[np.arange(0, columns, 8), columns-1])
        sampled = height[np.ix_(display_rows, display_cols)]
        valid = archive['source_valid_mask'][np.ix_(display_rows, display_cols)]
    refused = {(int(edge["source_cell_id"]), int(edge["target_cell_id"]))
               for edge in exclusion["edge_ids"]}
    edges = [(int(left), int(right)) for left, right in zip(source, target)]
    accepted_ids = {int(edge) for record in failure['component_records'].values()
                    if record['status'] == 'accepted_connected_component' for edge in record['source_edge_ids']}
    accepted_edges = [edge for edge in edges if edge[0] in accepted_ids]
    refused_edges = [edge for edge in edges if edge in refused]
    if (len(set(edges)) != failure['declared_selected_edges']
            or len(accepted_edges) != failure['accepted_global_edges']
            or set(refused_edges) != refused or {e[0] for e in refused} & accepted_ids
            or len(accepted_edges) + len(refused_edges) != len(edges)):
        raise ValueError('global accepted and excluded coverage mismatch')
    diagnostic_rows = {row['source_cell_id']: row for row in diagnostic['rows']}
    return {
        "schema": "terragenesis-global-valley-geometry-frontend-v1",
        "case_id": "td-global-valley-geometry",
        "label": "全域谷地河槽 · 覆盖与排除",
        "status": failure["status"],
        "publishable": False,
        "source": {**plan_pin, "identity_sha256": manifest['identity_sha256'], "kind": "Terrain Diffusion network plan", "terrain": terrain},
        "evidence": {"coverage": _pin(FAILURE), "exclusion": _pin(EXCLUSION), "diagnostic": _pin(BASE / 'refusal-diagnostic.json')},
        "terrain": {"x_m": (terrain['x0_m'] + display_cols * terrain['dx_m']).tolist(),
                    "z_m": (terrain['z0_m'] + display_rows * terrain['dz_m']).tolist(),
                    "height_m": np.where(valid, sampled, 0).tolist(), "valid_mask": valid.tolist(),
                    "sampling": "raw TD samples every 8 cells plus boundary; display only"},
        "global_geometry": {
            "declared_edges": int(failure["declared_selected_edges"]),
            "accepted_edges": int(failure["accepted_global_edges"]),
            "refused_edges": int(exclusion["refused_count"]),
            "coverage_fraction": float(failure["coverage_fraction"]),
            "component_count": len(failure["component_records"]),
            "accepted_edge_points_xz_m": _edge_points(np.asarray([edge[0] for edge in accepted_edges]),
                                                      np.asarray([edge[1] for edge in accepted_edges]), columns, terrain),
            "refused_edge_points_xz_m": _edge_points(np.asarray([edge[0] for edge in refused_edges]),
                                                     np.asarray([edge[1] for edge in refused_edges]), columns, terrain),
            "accepted_edge_ids": accepted_edges,
            "refused_edge_ids": refused_edges,
            "refusal_reasons": [diagnostic_rows[edge[0]] for edge in refused_edges],
        },
        "scope_exclusion": {
            **exclusion,
            "artifact": _pin(EXCLUSION),
            "diagnostic": _pin(ROOT / exclusion["diagnostic_path"]),
        },
        "ledger": failure["unique_material_ledger"],
        "source_accounting": failure["native_local_source_accounting"],
        "shape_statistics": failure["shape_statistics"],
        "limitations": failure["limitations"],
    }
