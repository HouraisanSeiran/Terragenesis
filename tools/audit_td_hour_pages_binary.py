"""Decode saved review shards independently and compare original native inventories."""

import argparse
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record

STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
LEDGERS = ("rain_volume_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3", "internal_net_m3", "storage_change_m3", "balance_residual_m3")


def json_shard(root, record):
    target = root / record["file"]
    if target.name != record["file"] or target.is_symlink() or target.stat().st_size > 8 * 1024 ** 2:
        raise ValueError("independent JSON shard path/budget mismatch")
    if target.stat().st_size != record["bytes"] or file_sha256(target) != record["expected_sha256"]:
        raise ValueError("independent JSON shard pin mismatch")
    payload = json.loads(target.read_text(encoding="utf-8"))
    for name in ("kind", "scenario", "step_s", "frame_index", "chunk_index"):
        if payload[name] != record[name]:
            raise ValueError("independent JSON descriptor mismatch")
    if len(payload["rows"]) != record["row_count"] or not 1 <= len(payload["rows"]) <= 2048:
        raise ValueError("independent JSON row coverage mismatch")
    return payload["rows"]


def decode(root, records, kind, expected, columns):
    pages = sorted(records, key=lambda record: record["chunk_index"])
    offset = 0
    for number, record in enumerate(pages):
        if (record["kind"] != kind or record["chunk_index"] != number or record["row_offset"] != offset or
                record["columns"] != list(columns) or record["format"] != "raw-le" or
                record["dtype"] != expected.dtype.str or record["shape"] != [record["row_count"], len(columns)] or
                not 1 <= record["row_count"] <= 2048):
            raise ValueError("independent binary descriptor or coverage mismatch")
        path = root / record["file"]
        if path.name != record["file"] or path.is_symlink() or path.stat().st_size > 8 * 1024 ** 2:
            raise ValueError("independent binary path/budget mismatch")
        payload = path.read_bytes()
        if file_sha256(path) != record["expected_sha256"] or len(payload) != record["bytes"] or len(payload) != math.prod(record["shape"]) * 8:
            raise ValueError("independent binary external SHA/byte count mismatch")
        values = np.frombuffer(payload, dtype=np.dtype(record["dtype"])).reshape(record["shape"])
        np.testing.assert_array_equal(values, expected[offset:offset + len(values)])
        offset += len(values)
    if offset != len(expected):
        raise ValueError("independent binary native row coverage incomplete")
    return offset * len(columns)


def audit(path, expected_sha256):
    path = Path(path).resolve(strict=True)
    if file_sha256(path) != expected_sha256 or path.stat().st_size > 8 * 1024 ** 2:
        raise ValueError("independent review manifest pin/budget mismatch")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["schema"] != "td-hour-pages-native-review-v2" or manifest["frames"] != 25:
        raise ValueError("independent review known complete schema required")
    root = path.parent
    records = manifest["pages"]
    files = [record["file"] for record in records]
    if len(set(files)) != len(files) or {entry.name for entry in root.iterdir()} != {"index.json", *files}:
        raise ValueError("independent review extra/missing/duplicate artifacts")
    topology, geometry = read_record(manifest["acceptance_arguments"]["hierarchy_record"])
    valid = topology["valid_mask"].ravel()
    cells = np.flatnonzero(valid)
    owner = topology["contribution_owner"].ravel()
    leaf_ids, labels = np.unique(owner[valid], return_inverse=True)
    area = geometry["spacing_m"] ** 2
    leaves = []
    leaf_records = sorted((record for record in records if record["kind"] == "leaves"), key=lambda record: record["chunk_index"])
    for number, record in enumerate(leaf_records):
        if record["chunk_index"] != number:
            raise ValueError("independent leaf descriptor order mismatch")
        leaves.extend(json_shard(root, record))
    if [row["leaf_id"] for row in leaves] != leaf_ids.tolist():
        raise ValueError("independent static leaf coverage mismatch")
    for leaf, leaf_id in zip(leaves, leaf_ids):
        members = cells[owner[cells] == leaf_id]
        terminals = members[topology["receiver"][members] < 0]
        if len(terminals) != 1:
            raise ValueError("independent leaf terminal is not unique")
        terminal = int(terminals[0])
        row, column = divmod(terminal, topology["height_m"].shape[1])
        xyz = [float(geometry["origin_m_xz"][0] + column * geometry["spacing_m"]),
            float(topology["height_m"].ravel()[terminal]), float(geometry["origin_m_xz"][1] + row * geometry["spacing_m"])]
        identity = hashlib.sha256(json.dumps([geometry["source_identity_sha256"], [value.hex() for value in xyz]], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        kind = "protected_terminal" if topology["protected_mask"].ravel()[terminal] else "unknown_contact" if topology["node_unknown_contact"][leaf_id] else "engineered_open" if topology["open_boundary_mask"].ravel()[terminal] else "internal_basin"
        if leaf != dict(leaf_id=int(leaf_id), stable_leaf_id="leaf:" + identity, terminal_cell_id=terminal,
                terminal_xyz_m=xyz, terminal_kind=kind, cell_count=len(members)):
            raise ValueError("independent leaf coordinates/identity/classification mismatch")
    membership = np.column_stack((cells, owner[cells], topology["receiver"][cells], topology["protected_mask"].ravel()[cells])).astype("<i8")
    checked = decode(root, [record for record in records if record["kind"] == "cell_membership"], "cell_membership",
        membership, ("cell_id", "leaf_id", "receiver_cell_id", "protected"))
    summaries = []
    used = {record["file"] for record in records if record["kind"] in ("cell_membership", "leaves")}
    if manifest["include_hour_flux"]:
        selected = [record for record in records if record["kind"] == "face_membership"]
        checked += decode(root, selected, "face_membership", topology["face_cells"].astype("<i8"), ("first_cell_id", "second_cell_id"))
        used.update(record["file"] for record in selected)
    for scenario in ("ordinary", "strong"):
        for step in manifest["selected_steps_s"]:
            previous = None
            for hour, page in enumerate(manifest["original_hour_pages"][scenario][str(step)]):
                water, metadata = read_record(page["storage"])
                for local in ((0, 1) if hour == 0 else (1,)):
                    frame = hour + local
                    selected = [record for record in records if record["scenario"] == scenario and record["step_s"] == step and record["frame_index"] == frame]
                    native = np.column_stack([water[name][local, valid] for name in STATES]).astype("<f8")
                    native_records = [record for record in selected if record["kind"] == "native_states"]
                    checked += decode(root, native_records, "native_states", native, STATES)
                    used.update(record["file"] for record in native_records)
                    inventories = np.column_stack([np.bincount(labels, weights=native[:, column] * area / (1 if column == 0 else 1000), minlength=len(leaf_ids)) for column in range(4)])
                    total = inventories.sum(axis=1)
                    rows = []
                    leaf_records = sorted((record for record in selected if record["kind"] == "leaf_states"), key=lambda record: record["chunk_index"])
                    for number, record in enumerate(leaf_records):
                        if record["chunk_index"] != number:
                            raise ValueError("independent leaf shard coverage/pin mismatch")
                        rows.extend(json_shard(root, record))
                        used.add(record["file"])
                    if [row["leaf_id"] for row in rows] != leaf_ids.tolist():
                        raise ValueError("independent leaf membership incomplete")
                    wet = native[:, 0] > metadata["parameters"]["wet_threshold_m"]
                    heads = topology["height_m"].ravel()[cells] + native[:, 0]
                    counts = np.bincount(labels[wet], minlength=len(leaf_ids))
                    minimum = np.full(len(leaf_ids), np.inf)
                    maximum = np.full(len(leaf_ids), -np.inf)
                    np.minimum.at(minimum, labels[wet], heads[wet])
                    np.maximum.at(maximum, labels[wet], heads[wet])
                    original_ledgers = None if frame == 0 else {name: np.bincount(labels, weights=water[name][0, valid], minlength=len(leaf_ids)) for name in LEDGERS}
                    for position, row in enumerate(rows):
                        if row["time_s"] != frame * 3600:
                            raise ValueError("independent leaf time changed")
                        np.testing.assert_array_equal(list(row["inventories_m3"][name] for name in STATES), inventories[position])
                        if (row["stable_leaf_id"] != leaves[position]["stable_leaf_id"] or row["wet_count"] != int(counts[position]) or
                                row["water_surface_min_m"] != (float(minimum[position]) if counts[position] else None) or
                                row["water_surface_max_m"] != (float(maximum[position]) if counts[position] else None)):
                            raise ValueError("independent leaf wet count/surface range mismatch")
                        if frame:
                            ledger = row["interval_ledger_m3"]
                            for name in LEDGERS:
                                expected_ledger = original_ledgers[name][position]
                                if ledger[name] != float(expected_ledger):
                                    raise ValueError("independent leaf original ledger mismatch")
                            expected_residual = ledger["rain_volume_m3"] + ledger["internal_net_m3"] - ledger["soil_et_m3"] - ledger["surface_et_m3"] - ledger["boundary_outflow_m3"] - (total[position] - previous[position])
                            if abs(row["leaf_budget"]["residual_m3"] - expected_residual) > 1e-9:
                                raise ValueError("independent leaf actual inventory budget mismatch")
                            allowed = 1e-6 + 1e-10 * (abs(total[position]) + abs(previous[position]))
                            if row["leaf_budget"]["allowed_m3"] != allowed or row["leaf_budget"]["passed"] is not bool(abs(expected_residual) <= allowed):
                                raise ValueError("independent leaf budget decision mismatch")
                        elif row["interval_ledger_m3"] is not None or row["leaf_budget"] is not None:
                            raise ValueError("initial leaf frame has interval account")
                    previous = total
                    summaries.append(dict(scenario=scenario, step_s=step, frame=frame,
                        four_store_volume_m3=math.fsum((native[:, 0] + native[:, 1:].sum(axis=1) / 1000).tolist()) * area))
                if manifest["include_hour_flux"]:
                    for kind, columns, mask in (("hour_faces", ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"), None),
                                                ("hour_receivers", ("routed_volume_m3", "wet_duration_s"), valid)):
                        expected = np.column_stack([water[name] if mask is None else water[name][mask] for name in columns]).astype("<f8")
                        selected = [record for record in records if record["kind"] == kind and record["scenario"] == scenario and record["step_s"] == step and record["frame_index"] == hour + 1]
                        checked += decode(root, selected, kind, expected, columns)
                        used.update(record["file"] for record in selected)
                del water
    if used != set(files) or len(summaries) != 2 * 25 * len(manifest["selected_steps_s"]):
        raise ValueError("independent review unexplained page/frame coverage")
    actual_bytes = path.stat().st_size + sum((root / name).stat().st_size for name in files)
    if actual_bytes != path.stat().st_size + manifest["artifact_bytes"] or actual_bytes > manifest["output_budget_bytes"]:
        raise ValueError("independent review whole output budget mismatch")
    memory = psutil.Process().memory_info()
    resource = dict(peak_rss_bytes=int(getattr(memory, "peak_wset", memory.rss)), peak_private_bytes=getattr(memory, "peak_pagefile", None))
    if resource["peak_private_bytes"] is None or max(resource.values()) > 1073741824:
        raise MemoryError("independent binary review resource evidence rejected")
    if file_sha256(path) != expected_sha256:
        raise ValueError("independent binary review index changed")
    return dict(schema="td-independent-native-binary-review-v1", input_index=str(path), expected_sha256=expected_sha256,
        decoded_values_exact=checked, series_frames=len(summaries), frames=summaries, output_bytes=actual_bytes,
        resource=resource, solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False,
        diagnostic_only=manifest["diagnostic_only"], auditor_sha256=file_sha256(__file__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    result = audit(arguments.index, arguments.expected_sha256)
    output = ROOT / "verification/td-hour-pages-review" / ("independent-binary-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(output=str(output), decoded_values_exact=result["decoded_values_exact"], output_bytes=result["output_bytes"])))
