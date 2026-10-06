"""Read-only cross-domain and cross-resolution surface seam audit."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import hashlib
import json


VERSION = "surface-cross-domain-v1"
TOLERANCE_M = 1e-9


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be finite") from None
    if number != number or abs(number) == float("inf"):
        raise ValueError(f"{name} must be finite")
    return number


def _integer(value, name):
    number = _number(value, name)
    rounded = round(number)
    if abs(number - rounded) > TOLERANCE_M:
        raise ValueError(f"{name} must be integer aligned")
    return int(rounded)


def _coordinate_key(x, z):
    try:
        return (Decimal(str(x)).normalize(), Decimal(str(z)).normalize())
    except (InvalidOperation, ValueError):
        raise ValueError("node coordinate is not finite") from None


def _segment_parts(start, end, finest_x, finest_z, tolerance):
    start_x, start_z = start
    end_x, end_z = end
    delta_x = end_x - start_x
    delta_z = end_z - start_z
    if abs(delta_x) > tolerance and abs(delta_z) > tolerance:
        raise ValueError("cross-domain edges must be axis aligned")
    length = abs(delta_x) + abs(delta_z)
    if length <= tolerance:
        raise ValueError("edge has zero length")
    spacing = finest_x if abs(delta_x) > tolerance else finest_z
    steps = length / spacing
    if abs(steps - round(steps)) > tolerance:
        raise ValueError("edge endpoints are not aligned to finest grid")
    steps = int(round(steps))
    for index in range(steps):
        fraction_start = index / steps
        fraction_end = (index + 1) / steps
        first = (start_x + delta_x * fraction_start, start_z + delta_z * fraction_start)
        second = (start_x + delta_x * fraction_end, start_z + delta_z * fraction_end)
        yield _coordinate_key(*first), _coordinate_key(*second), 1.0 / steps


def _normalise_domain(domain):
    if not isinstance(domain, dict) or set(domain) != {"domain_id", "grid", "nodes", "edges"}:
        raise ValueError("domain requires domain_id, grid, nodes and edges")
    domain_id = domain["domain_id"]
    if not isinstance(domain_id, str) or not domain_id:
        raise ValueError("domain_id must be a non-empty string")
    grid = domain["grid"]
    if not isinstance(grid, dict) or set(grid) != {"origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m", "lod"}:
        raise ValueError("grid requires origin, spacing and lod")
    origin_x = _number(grid["origin_x_m"], "origin_x_m")
    origin_z = _number(grid["origin_z_m"], "origin_z_m")
    spacing_x = _number(grid["spacing_x_m"], "spacing_x_m")
    spacing_z = _number(grid["spacing_z_m"], "spacing_z_m")
    lod = _integer(grid["lod"], "lod")
    if spacing_x <= 0 or spacing_z <= 0 or lod < 0:
        raise ValueError("grid spacing and lod must be positive")
    nodes = []
    seen_local = set()
    for raw in domain["nodes"]:
        if not isinstance(raw, dict) or set(raw) != {"local_id", "x_m", "z_m", "h0_m", "unknown", "protected", "water_surface_m"}:
            raise ValueError("node fields are incomplete")
        local_id = _integer(raw["local_id"], "local_id")
        if local_id in seen_local:
            raise ValueError("duplicate local node id")
        seen_local.add(local_id)
        x = _number(raw["x_m"], "x_m")
        z = _number(raw["z_m"], "z_m")
        h0 = _number(raw["h0_m"], "h0_m")
        if type(raw["unknown"]) is not bool or type(raw["protected"]) is not bool:
            raise ValueError("unknown/protected must be boolean")
        water = raw["water_surface_m"]
        if water is not None:
            water = _number(water, "water_surface_m")
        nodes.append({"local_id": local_id, "x_m": x, "z_m": z, "h0_m": h0,
                      "unknown": raw["unknown"], "protected": raw["protected"],
                      "water_surface_m": water})
    local_ids = {node["local_id"] for node in nodes}
    edges = []
    seen_edges = set()
    for raw in domain["edges"]:
        allowed = {"local_id", "start", "end", "flux_m3_s", "boundary", "evidence"}
        if not isinstance(raw, dict) or not {"local_id", "start", "end", "flux_m3_s", "boundary"} <= set(raw) or set(raw) - allowed:
            raise ValueError("edge fields are incomplete")
        edge_id = _integer(raw["local_id"], "edge local_id")
        start = _integer(raw["start"], "edge start")
        end = _integer(raw["end"], "edge end")
        if edge_id in seen_edges or start == end or start not in local_ids or end not in local_ids:
            raise ValueError("invalid or duplicate local edge")
        seen_edges.add(edge_id)
        if type(raw["boundary"]) is not bool:
            raise ValueError("edge boundary must be boolean")
        evidence = raw.get("evidence")
        if evidence is not None and (not isinstance(evidence, dict) or not isinstance(evidence.get("adapter_version"), str) or not isinstance(evidence.get("face_index"), int)):
            raise ValueError("invalid edge evidence")
        edges.append({"local_id": edge_id, "start": start, "end": end,
                      "flux_m3_s": _number(raw["flux_m3_s"], "flux_m3_s"),
                      "boundary": raw["boundary"], "evidence": evidence})
    return {"domain_id": domain_id,
            "grid": {"origin_x_m": origin_x, "origin_z_m": origin_z,
                     "spacing_x_m": spacing_x, "spacing_z_m": spacing_z, "lod": lod},
            "nodes": nodes, "edges": edges}


def audit_cross_domain(domains, *, tolerance=TOLERANCE_M):
    """Audit saved domain records without generating geometry, routing or water."""
    if not isinstance(domains, (list, tuple)) or not domains:
        raise ValueError("at least one domain is required")
    if type(tolerance) is not float or not 0 < tolerance < float("inf"):
        raise ValueError("tolerance must be positive float")
    normalised = [_normalise_domain(domain) for domain in domains]
    if len({domain["domain_id"] for domain in normalised}) != len(normalised):
        raise ValueError("domain IDs must be unique")
    finest_x = min(domain["grid"]["spacing_x_m"] for domain in normalised)
    finest_z = min(domain["grid"]["spacing_z_m"] for domain in normalised)
    base_x = min(node["x_m"] for domain in normalised for node in domain["nodes"])
    base_z = min(node["z_m"] for domain in normalised for node in domain["nodes"])
    for domain in normalised:
        grid = domain["grid"]
        for axis, spacing, base in (("x", grid["spacing_x_m"], base_x), ("z", grid["spacing_z_m"], base_z)):
            ratio = spacing / (finest_x if axis == "x" else finest_z)
            if abs(ratio - round(ratio)) > tolerance:
                raise ValueError("spacing is not aligned to finest grid")
            offset = (grid[f"origin_{axis}_m"] - base) / (finest_x if axis == "x" else finest_z)
            if abs(offset - round(offset)) > tolerance:
                raise ValueError("domain origin is not aligned to finest grid")
    global_nodes = {}
    for domain in normalised:
        grid = domain["grid"]
        for node in domain["nodes"]:
            key = _coordinate_key(node["x_m"], node["z_m"])
            expected_x = grid["origin_x_m"] + round((node["x_m"] - grid["origin_x_m"]) / grid["spacing_x_m"]) * grid["spacing_x_m"]
            expected_z = grid["origin_z_m"] + round((node["z_m"] - grid["origin_z_m"]) / grid["spacing_z_m"]) * grid["spacing_z_m"]
            if abs(node["x_m"] - expected_x) > tolerance or abs(node["z_m"] - expected_z) > tolerance:
                raise ValueError("node is not on its declared grid")
            global_nodes.setdefault(key, {"x_m": node["x_m"], "z_m": node["z_m"], "members": []})["members"].append((domain["domain_id"], node))
    ordered_keys = sorted(global_nodes)
    node_ids = {key: "n:" + hashlib.sha256((str(key[0]) + ":" + str(key[1])).encode()).hexdigest() for key in ordered_keys}
    shared_nodes = []
    barriers = []
    water_conflicts = []
    for key in ordered_keys:
        record = global_nodes[key]
        members = record["members"]
        if len(members) > 1:
            reference = members[0][1]
            for domain_id, node in members[1:]:
                if abs(node["h0_m"] - reference["h0_m"]) > tolerance or node["unknown"] != reference["unknown"] or node["protected"] != reference["protected"]:
                    raise ValueError("shared node H0 or barrier mismatch")
                if reference["water_surface_m"] is not None and node["water_surface_m"] is not None and abs(node["water_surface_m"] - reference["water_surface_m"]) > tolerance:
                    water_conflicts.append({"node_id": node_ids[key], "domains": [members[0][0], domain_id]})
            shared_nodes.append(node_ids[key])
        if any(node["unknown"] or node["protected"] for _, node in members):
            barriers.append(node_ids[key])
    if water_conflicts:
        raise ValueError("shared node water surface mismatch")
    edge_records = {}
    boundary_flux = 0.0
    internal_evidence_edges = 0
    shared_edges = []
    internal_flux_residual = 0.0
    for domain in normalised:
        by_id = {node["local_id"]: node for node in domain["nodes"]}
        for edge in domain["edges"]:
            start = (by_id[edge["start"]]["x_m"], by_id[edge["start"]]["z_m"])
            end = (by_id[edge["end"]]["x_m"], by_id[edge["end"]]["z_m"])
            parts = tuple(_segment_parts(start, end, finest_x, finest_z, tolerance))
            for start_key, end_key, fraction in parts:
                start_id = node_ids.get(start_key)
                end_id = node_ids.get(end_key)
                if start_id is None or end_id is None:
                    raise ValueError("edge split point is missing from domain node registry")
                if (start_id in barriers or end_id in barriers) and abs(edge["flux_m3_s"] * fraction) > tolerance:
                    raise ValueError("nonzero flux crosses unknown/protected barrier")
                key = tuple(sorted((start_id, end_id)))
                directed = (start_id, end_id)
                record = edge_records.setdefault(key, [])
                record.append((domain["domain_id"], directed, edge["flux_m3_s"] * fraction, edge["boundary"], edge["evidence"]))
    unique_edges = []
    for key, records in sorted(edge_records.items()):
        if len(records) > 2:
            raise ValueError("edge belongs to more than two domains")
        if len(records) == 2:
            first, second = records
            if first[0] == second[0]:
                raise ValueError("duplicate geometric edge within one domain")
            if abs(first[2] + second[2]) > tolerance:
                raise ValueError("shared edge flux is not anti-symmetric")
            shared_edges.append({"edge_id": f"e{key[0]}-{key[1]}", "domains": sorted((first[0], second[0])), "flux_m3_s": 0.0})
            internal_flux_residual += first[2] + second[2]
        else:
            domain_id, directed, flux, boundary, evidence = records[0]
            if boundary:
                boundary_flux += flux
            else:
                internal_evidence_edges += 1
        unique_edges.append({"edge_id": f"e{key[0]}-{key[1]}", "global_start": key[0], "global_end": key[1], "record_count": len(records)})
    return {"schema": VERSION, "algorithm_version": VERSION, "flags": {
                "readonly": True, "geometry_generated": False, "water_generated": False,
                "unknown_barrier_preserved": True, "protected_barrier_preserved": True,
                "edge_evidence_complete": False,
                "hydraulic_ready": False, "natural_outlet_verified": False},
            "grid": {"finest_spacing_x_m": finest_x, "finest_spacing_z_m": finest_z,
                     "base_x_m": base_x, "base_z_m": base_z,
                     "lods": sorted({domain["grid"]["lod"] for domain in normalised})},
            "domains": [domain["domain_id"] for domain in normalised],
            "global_nodes": [{"global_id": node_ids[key], "x_m": global_nodes[key]["x_m"], "z_m": global_nodes[key]["z_m"], "member_count": len(global_nodes[key]["members"])} for key in ordered_keys],
            "shared_boundary_node_ids": shared_nodes,
            "barrier_node_ids": barriers,
            "global_edges": unique_edges,
            "shared_boundary_edges": shared_edges,
            "ledger": {"unique_boundary_flux_m3_s": boundary_flux,
                        "internal_shared_flux_residual_m3_s": internal_flux_residual,
                        "shared_edge_count": len(shared_edges),
                        "boundary_edge_count": len(unique_edges) - len(shared_edges) - internal_evidence_edges,
                        "internal_evidence_edge_count": internal_evidence_edges},
            "flux_semantics": "control-volume outward normal signed flux; endpoint order is geometric only; coarse face totals split by length",
            "water": {"surface_policy": "shared saved surfaces must match; no surface is generated", "surface_available": False},
            "limitations": "Read-only seam and ledger audit. It does not establish a complete river network, hydraulic connectivity, natural outlet, or observed channel geometry."}


def _saved_nodes(nodes):
    required = {"x_m", "z_m", "h0_m", "protected_mask"}
    if not isinstance(nodes, Mapping) or not required <= set(nodes):
        raise ValueError("saved mosaic lacks required node fields")
    count = len(nodes["x_m"])
    if any(len(nodes[name]) != count for name in required):
        raise ValueError("saved mosaic node fields have inconsistent lengths")
    water = nodes.get("water_surface_m")
    wet = nodes.get("wet_mask")
    if water is not None and len(water) != count:
        raise ValueError("saved mosaic water field has inconsistent length")
    if wet is not None and len(wet) != count:
        raise ValueError("saved mosaic wet field has inconsistent length")
    unknown = nodes.get("unknown_mask")
    if unknown is not None and len(unknown) != count:
        raise ValueError("saved mosaic unknown field has inconsistent length")
    records = []
    for index in range(count):
        water_value = None
        if water is not None and (wet is None or bool(wet[index])):
            water_value = float(water[index])
        records.append({"local_id": index, "x_m": float(nodes["x_m"][index]),
                        "z_m": float(nodes["z_m"][index]), "h0_m": float(nodes["h0_m"][index]),
                        "unknown": bool(unknown[index]) if unknown is not None else False,
                        "protected": bool(nodes["protected_mask"][index]),
                        "water_surface_m": water_value})
    return records


def adapt_saved_mosaics(mosaics):
    """Convert loaded saved mosaics into audit records without reconstruction.

    Domain mosaics expose their independently saved domain meshes. Fine mosaics
    expose one saved mesh. Neither format stores a complete river-edge graph;
    the returned diagnostic keeps edges empty and marks that omission explicitly.
    """
    if not isinstance(mosaics, (list, tuple)) or not mosaics:
        raise ValueError("at least one saved mosaic is required")
    domains = []
    diagnostics = []
    for entry in mosaics:
        if not isinstance(entry, dict) or set(entry) != {"mosaic", "domain_id"}:
            raise ValueError("saved mosaic entry requires mosaic and domain_id")
        mosaic = entry["mosaic"]
        domain_id = entry["domain_id"]
        if not isinstance(domain_id, str) or not domain_id:
            raise ValueError("domain_id must be a non-empty string")
        if mosaic.get("algorithm_version") == "surface-domain-mosaic-v1":
            meshes = mosaic.get("domain_meshes")
            if not meshes:
                raise ValueError("domain mosaic has no saved domain meshes")
            for mesh_index, mesh in enumerate(meshes):
                source_id = mesh["sources"][0]["domain_id"] if mesh.get("sources") else f"{domain_id}-{mesh_index}"
                grid = mesh["grid"]
                domains.append({"domain_id": str(source_id),
                                "grid": {"origin_x_m": grid["origin_x_m"], "origin_z_m": grid["origin_z_m"],
                                         "spacing_x_m": grid["spacing_x_m"], "spacing_z_m": grid["spacing_z_m"], "lod": 0},
                                "nodes": _saved_nodes(mesh["nodes"]), "edges": []})
                diagnostics.append({"domain_id": str(source_id), "source_kind": "saved_domain_mesh",
                                    "edge_evidence_complete": False, "water_source": "saved_node_water_surface"})
        elif mosaic.get("algorithm_version") == "surface-fine-mosaic-v1.1":
            grid = mosaic["grid"]
            domains.append({"domain_id": domain_id,
                            "grid": {"origin_x_m": grid["origin_x_m"], "origin_z_m": grid["origin_z_m"],
                                     "spacing_x_m": grid["spacing_x_m"], "spacing_z_m": grid["spacing_z_m"], "lod": 0},
                            "nodes": _saved_nodes(mosaic["nodes"]), "edges": []})
            diagnostics.append({"domain_id": domain_id, "source_kind": "saved_fine_mosaic",
                                "edge_evidence_complete": False, "water_source": "saved_node_water_surface"})
        else:
            raise ValueError("unsupported saved mosaic algorithm")
    report = audit_cross_domain(domains)
    report["adapter"] = {"version": "surface-cross-domain-saved-mosaic-adapter-v1",
                          "readonly": True, "prepare_called": False, "routing_called": False,
                          "water_generation_called": False, "diagnostics": diagnostics}
    report["flags"]["edge_evidence_complete"] = False
    report["limitations"] += " Saved mosaic adapter has no river-edge reconstruction; edge ledger is diagnostic only."
    return report


def save_cross_domain_report(report, path):
    """Atomically publish a report without overwriting an existing artifact."""
    if not isinstance(report, dict) or report.get("schema") != VERSION:
        raise ValueError("unsupported cross-domain report")
    from terrain_pipeline.mountain_source_adapter import publish_bytes
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    publish_bytes(path, payload)


def audit_td_partition(records, *, partition_column, storage_record=None):
    """Cold-read Gibbs face records; audit one explicit vertical control-volume cut."""
    import numpy as np
    from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
    from terrain_pipeline.td_basin_storage import load_basin_storage
    from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges

    def load(record, loader):
        if not isinstance(record, dict) or set(record) != {"path", "expected_sha256", "expected_identity"}:
            raise ValueError("TD input requires both external pins")
        return loader(record["path"], expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"])

    hierarchy = load(records, load_basin_hierarchy)
    storage = None if storage_record is None else load(storage_record, load_basin_storage)
    versioned = build_td_surface_river_edges(hierarchy, storage=storage)
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    rows, columns = arrays["height_m"].shape
    if type(partition_column) is not int or not 0 < partition_column < columns:
        raise ValueError("partition column outside grid")
    elapsed = None
    if storage is not None:
        elapsed = (storage["arrays"]["depth_m"].shape[0] - 1) * storage["metadata"]["dt_s"]
        if elapsed <= 0:
            raise ValueError("positive saved observation duration required")
    selected = [edge for edge in versioned["records"] if edge["kind"] == "d4_internal_face"
                and {cell % columns for cell in edge["cell_ids"]} == {partition_column - 1, partition_column}]
    domains = []
    for domain_id, sign in (("left", 1), ("right", -1)):
        nodes = []
        cell_ids = sorted({cell for edge in selected for cell in edge["cell_ids"]})
        spacing = metadata["spacing_m"]
        origin_x, origin_z = metadata["origin_m_xz"]
        for cell in cell_ids:
            row, column = divmod(cell, columns)
            depth = None if storage is None else float(storage["arrays"]["depth_m"][-1, cell])
            wet = depth is not None and depth > storage["metadata"]["parameters"]["wet_threshold_m"]
            nodes.append({"local_id": cell, "x_m": origin_x + column * spacing, "z_m": origin_z + row * spacing,
                          "h0_m": float(arrays["height_m"][row, column]), "unknown": not bool(arrays["valid_mask"][row, column]),
                          "protected": bool(arrays["protected_mask"][row, column]),
                          "water_surface_m": float(arrays["height_m"][row, column] + depth) if wet else None})
        edges = []
        for edge in selected:
            first, second = edge["cell_ids"]
            evidence = None
            if elapsed is not None:
                evidence = {"adapter_version": versioned["schema"], "face_index": edge["face_index"],
                            "hierarchy_identity_sha256": hierarchy["identity_sha256"], "hydro_identity_sha256": storage["identity_sha256"],
                            "forward_m3": edge["forward_volume_m3"], "reverse_m3": edge["reverse_volume_m3"], "elapsed_s": elapsed}
            edges.append({"local_id": edge["face_index"], "start": first, "end": second, "boundary": False,
                          "flux_m3_s": 0.0 if evidence is None else sign * (evidence["forward_m3"] - evidence["reverse_m3"]) / elapsed,
                          "evidence": evidence})
        domains.append({"domain_id": domain_id, "grid": {"origin_x_m": origin_x, "origin_z_m": origin_z,
                        "spacing_x_m": spacing, "spacing_z_m": spacing, "lod": 0}, "nodes": nodes, "edges": edges})
    report = audit_cross_domain(domains)
    report["flags"]["edge_evidence_complete"] = False
    report["flags"]["partition_flux_evidence_complete"] = elapsed is not None and len(selected) == rows
    report["flags"]["diagnostic_only"] = True
    report["td_evidence"] = {"schema": versioned["schema"], "hierarchy": records, "storage": storage_record,
                            "partition_column": partition_column, "elapsed_s": elapsed,
                            "face_ids": [edge["face_index"] for edge in selected],
                            "forward_m3": None if elapsed is None else sum(edge["forward_volume_m3"] for edge in selected),
                            "reverse_m3": None if elapsed is None else sum(edge["reverse_volume_m3"] for edge in selected)}
    report["td_evidence"]["nonzero_one_direction_face_count"] = None if elapsed is None else sum(
        (edge["forward_volume_m3"] > 0) != (edge["reverse_volume_m3"] > 0) for edge in selected)
    report["limitations"] += " TD faces are terrain control-volume exchanges, not observed channels. Only the named cut is audited; exterior per-face evidence and full river coverage are incomplete. No new spacing is synthesized."
    return report
