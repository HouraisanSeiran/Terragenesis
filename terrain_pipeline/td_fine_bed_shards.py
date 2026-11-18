"""Append missing byte-refused triangle coverage to an immutable fine raster."""

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import publish_bytes
from terrain_pipeline.td_fine_bed_raster import (
    LEDGER_KEYS, MAX_BYTES, MAX_CELLS, _center_bounds, _context, _digest,
    _encoded, _sample, _weights)

SCHEMA = "td-fine-bed-shards-v1"
RAW_SCHEMA = "td-fine-bed-shard-raw-v1"
SHARD_SCHEMA = "td-fine-bed-transaction-shard-v1"
FLAGS = ("hydraulic_ready", "hydraulic_solved", "natural_outlet_certified",
         "publish_ready", "bed_changed", "cross_shard_hydraulics_verified")
BYTE_REASON = "raster_byte_reservation_exceeded"
MAX_SHARDS = 4096


def _seal(record):
    record["identity_sha256"] = _digest(record)
    return record


def _check_identity(record):
    if record.get("identity_sha256") != _digest({key: value for key, value in record.items()
                                               if key != "identity_sha256"}):
        raise ValueError("shard content identity mismatch")


def _cells(base):
    tile = base["grid"]["tile_cells"]
    result = {}
    for window in base["windows"]:
        row_base, column_base = window["global_origin_row_column"]
        for cell in window["cells"]:
            key = (row_base + cell["local_index"] // tile,
                   column_base + cell["local_index"] % tile)
            if key in result:
                raise ValueError("duplicate parent global cell")
            result[key] = cell
    return result


def _cut(cell, spacing):
    if cell is None or cell["status"] != "candidate":
        return 0.
    return max(0., cell["source_sample"]["height_m"] - cell["derived_bed_m"]) * spacing**2


def _ledger(cut):
    return {key: float(cut) if key in ("cut_rock_m3", "exported_excavated_rock_m3") else 0.
            for key in LEDGER_KEYS}


def _evaluate(source, proposals, index, parameters):
    tolerance = parameters["conflict_tolerance_m"]
    reasons = set(source["rejection_reasons"])
    targets = [item["bed_m"] for item in proposals]
    if max(targets) - min(targets) > tolerance:
        reasons.add("conflicting_triangle_overlap")
    height = source["height_m"]
    if height is not None:
        if height - min(targets) > parameters["max_cut_m"] + tolerance:
            reasons.add("cut_depth_exceeded")
        if max(targets) > height + tolerance:
            reasons.add("fill_without_material")
        if source["wet_source_support"] and height - min(targets) > tolerance:
            reasons.add("lake_wet_bed_cut_refused")
    derived = height
    if not reasons:
        derived = min(height, math.fsum(targets) / len(targets))
    return {"local_index": index, "source_sample": source, "derived_bed_m": derived,
            "status": "refused" if reasons else "candidate", "rejection_reasons": sorted(reasons),
            "triangle_sources": proposals}


def _shard(shard_id, base, raw_identity, transactions):
    delta = math.fsum(item["cut_delta_m3"] for item in transactions)
    inserted = math.fsum(item["after_cut_m3"] for item in transactions if item["operation"] == "insert")
    replaced = math.fsum(item["cut_delta_m3"] for item in transactions if item["operation"] == "replace")
    return _seal({"schema": SHARD_SCHEMA, "shard_id": shard_id,
                  "base_identity_sha256": base["identity_sha256"],
                  "raw_identity_sha256": raw_identity, "transactions": transactions,
                  "material_ledger_delta": _ledger(delta),
                  "insert_material_ledger": _ledger(inserted),
                  "replacement_material_ledger_delta": _ledger(replaced),
                  "summary": {"transaction_count": len(transactions),
                              "insert_count": sum(item["operation"] == "insert" for item in transactions),
                              "replace_count": sum(item["operation"] == "replace" for item in transactions)},
                  **{flag: False for flag in FLAGS}})


def build_fine_bed_shards(base, hierarchy, *, input_pins=None, max_cells=MAX_CELLS,
                          max_shard_bytes=MAX_BYTES, max_transactions_per_shard=4096,
                          resource_check=None):
    """Only retry byte-refused triangles; old samples and coverage are reused."""
    if base.get("schema") != "td-fine-bed-raster-v1":
        raise ValueError("immutable fine raster v1 required")
    if (type(max_cells) is not int or not 1 <= max_cells <= MAX_CELLS
            or type(max_shard_bytes) is not int or not 4096 <= max_shard_bytes <= MAX_BYTES
            or type(max_transactions_per_shard) is not int or not 1 <= max_transactions_per_shard <= 4096):
        raise ValueError("invalid shard resource bounds")
    if any(base.get(name) is not False for name in (
            "hydraulic_ready", "hydraulic_solved", "natural_outlet_certified", "publish_ready", "bed_changed")):
        raise ValueError("parent must remain an uncertified candidate")
    context = _context(hierarchy, base["selected_leaf_ids"], base["wet_protection"])
    grid, parameters = base["grid"], base["parameters"]
    spacing, origin, tile = grid["spacing_m"], np.asarray(grid["origin_m_xz"], float), grid["tile_cells"]
    if (hierarchy["identity_sha256"] != base["hierarchy_identity_sha256"]
            or hierarchy["metadata"]["source_identity_sha256"] != base["source_identity_sha256"]
            or origin.tolist() != context["origin"].tolist()
            or grid["native_spacing_m"] != context["spacing"]):
        raise ValueError("parent/native hierarchy linkage mismatch")
    old_cells = _cells(base)
    if len(old_cells) > max_cells:
        raise MemoryError("parent already exceeds total unique-cell budget")
    if resource_check is not None:
        resource_check()
    tasks, additions, new_keys = [], {}, set()
    visits, visit_limit, point_visits = 0, max_cells * 16, 0
    for triangle_number, original in enumerate(base["triangles"]):
        if original["status"] != "refused" or original["rejection_reasons"] != [BYTE_REASON]:
            continue
        if resource_check is not None and triangle_number % 128 == 0:
            resource_check()
        triangle = deepcopy(original)
        triangle["parent_status"] = original["status"]
        triangle["parent_rejection_reasons"] = list(original["rejection_reasons"])
        vertices = np.asarray(triangle["vertices_xyz_m"], float)
        bounds = _center_bounds(vertices, origin, spacing)
        count = max(0, bounds[2] - bounds[0] + 1) * max(0, bounds[3] - bounds[1] + 1)
        if visits + count > visit_limit:
            triangle.update(status="refused", rejection_reasons=["shard_visit_budget_exceeded"])
            tasks.append(triangle)
            continue
        visits += count
        covered, new_triangle_keys = [], set()
        for row in range(bounds[1], bounds[3] + 1):
            for column in range(bounds[0], bounds[2] + 1):
                point_visits += 1
                if resource_check is not None and point_visits % 16384 == 0:
                    resource_check()
                x_m, z_m = origin + (np.array([column, row]) + .5) * spacing
                weights = _weights(vertices, float(x_m), float(z_m))
                if weights is None:
                    continue
                key = (row, column)
                covered.append((key, {"triangle_id": triangle["triangle_id"],
                                      "weights": weights.tolist(), "bed_m": float(weights @ vertices[:, 1])}))
                if key not in old_cells and key not in new_keys:
                    new_triangle_keys.add(key)
        if len(old_cells) + len(new_keys) + len(new_triangle_keys) > max_cells:
            triangle.update(status="refused", rejection_reasons=["shard_unique_cell_budget_exceeded"])
            tasks.append(triangle)
            continue
        new_keys.update(new_triangle_keys)
        triangle.update(status="rasterized" if covered else "no_center_coverage",
                        rejection_reasons=[], covered_centers=len(covered))
        tasks.append(triangle)
        for key, proposal in covered:
            additions.setdefault(key, []).append(proposal)
    raw = _seal({"schema": RAW_SCHEMA, "base_identity_sha256": base["identity_sha256"],
                 "inputs": dict(input_pins or {}), "grid": deepcopy(grid),
                 "selection": deepcopy(base["selection"]), "selected_leaf_ids": list(base["selected_leaf_ids"]),
                 "wet_protection": deepcopy(base["wet_protection"]),
                 "source_identity_sha256": base["source_identity_sha256"],
                 "hierarchy_identity_sha256": base["hierarchy_identity_sha256"],
                 "sections_identity_sha256": base["sections_identity_sha256"],
                 "transitions_identity_sha256": base["transitions_identity_sha256"],
                 "parameters": dict(parameters), "triangles": tasks,
                 "summary": {"retried_triangles": len(tasks),
                             "rasterized_triangles": sum(item["status"] == "rasterized" for item in tasks),
                             "no_center_triangles": sum(item["status"] == "no_center_coverage" for item in tasks),
                             "still_refused_triangles": sum(item["status"] == "refused" for item in tasks),
                             "center_visits": visits},
                 "semantics": "original triangle indices unchanged; retry only byte-refused coverage; no mesh repair",
                 **{flag: False for flag in FLAGS}})
    if len(_encoded(raw)) > MAX_BYTES:
        raise MemoryError("raw original triangle provenance exceeds 64MiB")
    groups = {}
    task_map = {item["triangle_id"]: item for item in tasks}
    for cell_number, (key, proposed) in enumerate(sorted(additions.items())):
        if resource_check is not None and cell_number % 4096 == 0:
            resource_check()
        row, column = key
        before = old_cells.get(key)
        source = before["source_sample"] if before is not None else _sample(context, *(
            origin + (np.array([column, row]) + .5) * spacing).tolist())
        old_proposals = before["triangle_sources"] if before is not None else []
        seen = {item["triangle_id"] for item in old_proposals}
        if seen.intersection(item["triangle_id"] for item in proposed):
            raise ValueError("missing triangle already contributed to saved parent")
        proposals = list(old_proposals) + sorted(proposed, key=lambda item: item["triangle_id"])
        after = _evaluate(source, proposals, (row % tile) * tile + column % tile, parameters)
        owners = []
        for proposal in proposed:
            triangle = task_map[proposal["triangle_id"]]
            owners.append((triangle["source_package"], triangle.get("source_entry_index", -1)))
        group = min(owners)
        transaction = {"global_key_row_column": [row, column],
                       "operation": "replace" if before is not None else "insert",
                       "before_sha256": _digest(before) if before is not None else None,
                       "logical_owner": "shard0" if before is not None else None,
                       "cell": after, "before_cut_m3": _cut(before, spacing),
                       "after_cut_m3": _cut(after, spacing)}
        transaction["cut_delta_m3"] = transaction["after_cut_m3"] - transaction["before_cut_m3"]
        groups.setdefault(group, []).append(transaction)
    shards = []
    for group, transactions in sorted(groups.items()):
        chunk = []
        chunk_bytes = 0
        for transaction in transactions:
            transaction_bytes = len(_encoded(transaction)) + 128
            if chunk and (len(chunk) >= max_transactions_per_shard or chunk_bytes + transaction_bytes + 4096 > max_shard_bytes):
                shard_id = "shard-" + str(len(shards) + 1).zfill(4)
                shards.append(_shard(shard_id, base, raw["identity_sha256"], chunk))
                chunk, chunk_bytes = [], 0
            if transaction_bytes + 4096 > max_shard_bytes:
                raise MemoryError("single full-provenance transaction exceeds shard byte budget")
            shard_id = "shard-" + str(len(shards) + 1).zfill(4)
            if transaction["operation"] == "insert":
                transaction["logical_owner"] = shard_id
            transaction["source_group"] = {"source_package": group[0], "source_entry_index": group[1]}
            chunk.append(transaction)
            chunk_bytes += transaction_bytes
        if chunk:
            shard_id = "shard-" + str(len(shards) + 1).zfill(4)
            shards.append(_shard(shard_id, base, raw["identity_sha256"], chunk))
    if len(shards) > MAX_SHARDS:
        raise MemoryError("transaction shard count exceeds 4096")
    if any(len(_encoded(shard)) > max_shard_bytes for shard in shards):
        raise MemoryError("encoded transaction shard exceeds byte budget")
    delta = {key: math.fsum(shard["material_ledger_delta"][key] for shard in shards) for key in LEDGER_KEYS}
    merged = {key: base["material_ledger"][key] + delta[key] for key in LEDGER_KEYS}
    if any(value < -1e-8 for value in merged.values()):
        raise ValueError("negative merged material ledger")
    transitions = [item for shard in shards for item in shard["transactions"]]
    old_statuses = Counter(cell["status"] for cell in old_cells.values())
    for transaction in transitions:
        if transaction["operation"] == "replace":
            old_statuses[old_cells[tuple(transaction["global_key_row_column"])]["status"]] -= 1
        old_statuses[transaction["cell"]["status"]] += 1
    manifest = _seal({"schema": SCHEMA, "base_identity_sha256": base["identity_sha256"],
                      "raw_identity_sha256": raw["identity_sha256"],
                      "shard_identities": [shard["identity_sha256"] for shard in shards],
                      "ownership_semantics": "shard0 owns parent cells; one atomic before-hash replacement per overlapping key; one insertion owner per new key",
                      "merge_semantics": "append all missing proposals then re-evaluate once; parent ledger + signed replacement delta + unique insert ledger",
                      "summary": {"base_cells": len(old_cells), "new_cells": len(new_keys),
                                  "merged_cells": len(old_cells) + len(new_keys),
                                  "replace_transactions": sum(item["operation"] == "replace" for item in transitions),
                                  "insert_transactions": sum(item["operation"] == "insert" for item in transitions),
                                  "shard_count": len(shards), "candidate_cells": old_statuses["candidate"],
                                  "refused_cells": old_statuses["refused"],
                                  "base_coverage_triangles_preserved": sum(item["status"] != "refused" for item in base["triangles"])},
                      "material_ledger_base": dict(base["material_ledger"]),
                      "material_ledger_delta": delta, "material_ledger_merged": merged,
                      "budgets": {"max_unique_cells": max_cells, "max_shard_bytes": max_shard_bytes,
                                  "max_raw_bytes": MAX_BYTES, "max_shards": MAX_SHARDS},
                      "missing_coverage_complete": raw["summary"]["still_refused_triangles"] == 0,
                      **{flag: False for flag in FLAGS}})
    package = {"manifest": manifest, "raw": raw, "shards": shards}
    validate_fine_bed_shards(package, base)
    if resource_check is not None:
        resource_check()
    return package


def iter_merged_cells(base, shards):
    """Yield (global row/column, final cell, logical owner), without double count."""
    replacements, insertions = {}, {}
    for shard in shards:
        for transaction in shard["transactions"]:
            key = tuple(transaction["global_key_row_column"])
            if key in replacements or key in insertions:
                raise ValueError("duplicate transaction global key")
            target = replacements if transaction["operation"] == "replace" else insertions
            target[key] = transaction
    for key, cell in sorted(_cells(base).items()):
        transaction = replacements.pop(key, None)
        if transaction is not None:
            if _digest(cell) != transaction["before_sha256"]:
                raise ValueError("replacement before hash mismatch")
            cell = transaction["cell"]
        if key in insertions:
            raise ValueError("insertion collides with parent")
        yield key, cell, "shard0"
    if replacements:
        raise ValueError("replacement target absent from parent")
    for key, transaction in sorted(insertions.items()):
        yield key, transaction["cell"], transaction["logical_owner"]


def validate_fine_bed_shards(package, base=None, hierarchy=None):
    """Validate saved transaction/census/ledger contracts without rerasterizing."""
    manifest, raw, shards = package["manifest"], package["raw"], package["shards"]
    for record, schema in ((manifest, SCHEMA), (raw, RAW_SCHEMA)):
        _check_identity(record)
        if record["schema"] != schema or any(record.get(flag) is not False for flag in FLAGS):
            raise ValueError("shard schema/certification mismatch")
    if (manifest["raw_identity_sha256"] != raw["identity_sha256"]
            or manifest["base_identity_sha256"] != raw["base_identity_sha256"]
            or manifest["shard_identities"] != [item["identity_sha256"] for item in shards]):
        raise ValueError("shard parent identity chain mismatch")
    budgets = manifest["budgets"]
    if (not 1 <= budgets["max_unique_cells"] <= MAX_CELLS
            or not 4096 <= budgets["max_shard_bytes"] <= MAX_BYTES
            or len(shards) > MAX_SHARDS or len(_encoded(raw)) > MAX_BYTES):
        raise ValueError("shard resource bounds mismatch")
    raw_map = {item["triangle_id"]: item for item in raw["triangles"]}
    if len(raw_map) != len(raw["triangles"]):
        raise ValueError("duplicate retried triangle")
    for triangle in raw_map.values():
        if (triangle["status"] not in {"rasterized", "no_center_coverage", "refused"}
                or triangle["parent_status"] != "refused"
                or triangle["parent_rejection_reasons"] != [BYTE_REASON]):
            raise ValueError("invalid missing-triangle status/origin")
    old_cells = _cells(base) if base is not None else {}
    if base is not None:
        if (base["identity_sha256"] != manifest["base_identity_sha256"] or base["grid"] != raw["grid"]
                or base["selection"] != raw["selection"] or base["wet_protection"] != raw["wet_protection"]):
            raise ValueError("immutable parent lattice/selection mismatch")
        for name in ("source_identity_sha256", "hierarchy_identity_sha256", "sections_identity_sha256",
                     "transitions_identity_sha256", "selected_leaf_ids", "parameters"):
            if base[name] != raw[name]:
                raise ValueError("immutable parent source/parameter chain mismatch")
        if (manifest["material_ledger_base"] != base["material_ledger"]
                or manifest["summary"]["base_cells"] != len(old_cells)):
            raise ValueError("shard0 ledger/cell census mismatch")
        expected = {item["triangle_id"]: item for item in base["triangles"]
                    if item["status"] == "refused" and item["rejection_reasons"] == [BYTE_REASON]}
        if set(expected) != set(raw_map):
            raise ValueError("missing byte-refused triangle census mismatch")
        for identifier, item in raw_map.items():
            for name in ("source_package", "source_triangle_index", "source_vertex_indices", "vertices_xyz_m"):
                if item[name] != expected[identifier][name]:
                    raise ValueError("original triangle provenance changed")
            if item.get("source_entry_index") != expected[identifier].get("source_entry_index"):
                raise ValueError("original entry index changed")
    context = _context(hierarchy, raw["selected_leaf_ids"], raw["wet_protection"]) if hierarchy is not None else None
    if context is not None and hierarchy["identity_sha256"] != raw["hierarchy_identity_sha256"]:
        raise ValueError("cold native hierarchy mismatch")
    spacing, tile = raw["grid"]["spacing_m"], raw["grid"]["tile_cells"]
    origin = np.asarray(raw["grid"]["origin_m_xz"], float)
    keys, census, operations = set(), Counter(), Counter()
    for shard in shards:
        _check_identity(shard)
        if (shard["schema"] != SHARD_SCHEMA or shard["base_identity_sha256"] != manifest["base_identity_sha256"]
                or shard["raw_identity_sha256"] != raw["identity_sha256"]
                or any(shard.get(flag) is not False for flag in FLAGS)
                or len(_encoded(shard)) > budgets["max_shard_bytes"]):
            raise ValueError("transaction shard schema/pin/budget mismatch")
        delta, inserted, replaced = [], [], []
        for transaction in shard["transactions"]:
            key = tuple(transaction["global_key_row_column"])
            if len(key) != 2 or any(type(index) is not int for index in key) or key in keys:
                raise ValueError("duplicate/invalid transaction global key")
            keys.add(key)
            operation = transaction["operation"]
            if operation not in {"insert", "replace"}:
                raise ValueError("invalid transaction operation")
            operations[operation] += 1
            cell = transaction["cell"]
            if cell["local_index"] != (key[0] % tile) * tile + key[1] % tile:
                raise ValueError("transaction center changed lattice")
            before = old_cells.get(key)
            if base is not None:
                if (operation == "replace") != (before is not None):
                    raise ValueError("transaction insertion/replacement target mismatch")
                if transaction["before_sha256"] != (_digest(before) if before is not None else None):
                    raise ValueError("transaction before hash mismatch")
                if before is not None and cell["source_sample"] != before["source_sample"]:
                    raise ValueError("replacement altered original source sample")
            if transaction["logical_owner"] != ("shard0" if operation == "replace" else shard["shard_id"]):
                raise ValueError("shared cell owner mismatch")
            proposals = cell["triangle_sources"]
            if len({item["triangle_id"] for item in proposals}) != len(proposals):
                raise ValueError("duplicate center proposal")
            before_map = {item["triangle_id"]: item for item in before["triangle_sources"]} if before is not None else {}
            if before is not None and any(item not in proposals for item in before_map.values()):
                raise ValueError("parent proposal dropped by replacement")
            x_m, z_m = origin + (np.array([key[1], key[0]]) + .5) * spacing
            for proposal in proposals:
                identifier = proposal["triangle_id"]
                if identifier in before_map:
                    continue
                if base is None and operation == "replace" and identifier not in raw_map:
                    continue
                triangle = raw_map.get(identifier)
                if triangle is None or triangle["status"] != "rasterized":
                    raise ValueError("nonmissing/refused triangle appended")
                points = np.asarray(triangle["vertices_xyz_m"], float)
                weights = _weights(points, float(x_m), float(z_m))
                if (weights is None or not np.allclose(weights, proposal["weights"], atol=1e-9, rtol=0)
                        or abs(float(weights @ points[:, 1]) - proposal["bed_m"]) > 1e-9):
                    raise ValueError("appended triangle interpolation mismatch")
                census[identifier] += 1
            if context is not None and operation == "insert" and cell["source_sample"] != _sample(context, float(x_m), float(z_m)):
                raise ValueError("new center source sample mismatch")
            expected_cell = _evaluate(cell["source_sample"], proposals, cell["local_index"], raw["parameters"])
            if cell != expected_cell:
                raise ValueError("merged proposal/refusal/bed mismatch")
            before_cut = _cut(before, spacing) if base is not None else transaction["before_cut_m3"]
            after_cut = _cut(cell, spacing)
            cut_delta = after_cut - before_cut
            if any(abs(transaction[name] - value) > 1e-9 for name, value in (
                    ("before_cut_m3", before_cut), ("after_cut_m3", after_cut), ("cut_delta_m3", cut_delta))):
                raise ValueError("transaction material delta mismatch")
            delta.append(cut_delta)
            (inserted if operation == "insert" else replaced).append(after_cut if operation == "insert" else cut_delta)
        for name, values in (("material_ledger_delta", delta), ("insert_material_ledger", inserted),
                             ("replacement_material_ledger_delta", replaced)):
            expected_ledger = _ledger(math.fsum(values))
            if any(abs(shard[name][key] - expected_ledger[key]) > 1e-9 for key in LEDGER_KEYS):
                raise ValueError("shard signed material ledger mismatch")
    for identifier, triangle in raw_map.items():
        if triangle["status"] == "rasterized" and triangle["covered_centers"] != census[identifier]:
            raise ValueError("missing triangle coverage count mismatch")
        if triangle["status"] != "rasterized" and census[identifier]:
            raise ValueError("nonrasterized triangle contributed coverage")
    if (raw["summary"]["retried_triangles"] != len(raw_map)
            or raw["summary"]["rasterized_triangles"] != sum(item["status"] == "rasterized" for item in raw_map.values())
            or raw["summary"]["no_center_triangles"] != sum(item["status"] == "no_center_coverage" for item in raw_map.values())
            or raw["summary"]["still_refused_triangles"] != sum(item["status"] == "refused" for item in raw_map.values())):
        raise ValueError("raw coverage summary mismatch")
    merged_count = manifest["summary"]["base_cells"] + operations["insert"]
    if (merged_count != manifest["summary"]["merged_cells"] or merged_count > budgets["max_unique_cells"]
            or operations["replace"] != manifest["summary"]["replace_transactions"]
            or operations["insert"] != manifest["summary"]["insert_transactions"]
            or operations["insert"] != manifest["summary"]["new_cells"]
            or len(shards) != manifest["summary"]["shard_count"]):
        raise ValueError("unique merged-cell summary mismatch")
    for key in LEDGER_KEYS:
        delta = math.fsum(shard["material_ledger_delta"][key] for shard in shards)
        if (abs(delta - manifest["material_ledger_delta"][key]) > 1e-8
                or abs(manifest["material_ledger_base"][key] + delta - manifest["material_ledger_merged"][key]) > 1e-8):
            raise ValueError("merged material ledger double-count/mismatch")
    return package


def save_fine_bed_shards(package, directory, *, resource_check=None):
    """Validate and size all new files before publishing a new immutable package."""
    validate_fine_bed_shards(package)
    target = Path(directory)
    if target.exists():
        raise FileExistsError(target)
    files = {"raw.json": package["raw"], "manifest.json": package["manifest"]}
    files.update({"shards/" + shard["shard_id"] + ".json": shard for shard in package["shards"]})
    for name, record in files.items():
        if len(_encoded(record)) > MAX_BYTES:
            raise MemoryError("shard file exceeds 64MiB: " + name)
    for name, record in files.items():
        payload = _encoded(record)
        if resource_check is not None:
            resource_check()
        publish_bytes(target / name, payload)
    return target


def load_fine_bed_shards(directory, *, expected_manifest_sha256,
                         expected_manifest_identity, base=None, hierarchy=None):
    directory = Path(directory)

    def read(path, expected_sha=None):
        if path.stat().st_size > MAX_BYTES:
            raise MemoryError("saved shard file exceeds 64MiB")
        payload = path.read_bytes()
        if expected_sha is not None and hashlib.sha256(payload).hexdigest() != expected_sha:
            raise ValueError("saved shard manifest file SHA mismatch")
        record = json.loads(payload)
        _check_identity(record)
        return record

    manifest = read(directory / "manifest.json", expected_manifest_sha256)
    if manifest["identity_sha256"] != expected_manifest_identity:
        raise ValueError("external shard manifest identity mismatch")
    if len(manifest["shard_identities"]) > MAX_SHARDS:
        raise MemoryError("saved shard count exceeds 4096")
    raw = read(directory / "raw.json")
    shards = [read(directory / "shards" / ("shard-" + str(index + 1).zfill(4) + ".json"))
              for index in range(len(manifest["shard_identities"]))]
    return validate_fine_bed_shards({"manifest": manifest, "raw": raw, "shards": shards}, base, hierarchy)
