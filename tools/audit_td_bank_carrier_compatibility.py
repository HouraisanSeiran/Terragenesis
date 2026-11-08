"""Saved-effects-only comparison of a frozen bank overlay and the prepare03 carrier."""

import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, publish_bytes

BANK_INDEX = ROOT / "verification/natural-river-network/source-conforming-banks-v3-entry-20261006-01/index.json"
BANK_SHA = "8f9ef4d8190a637fc5c46ad165fb48c680f3cf5b2b5b834c90929e5bf4384654"
CARRIER_PARENT = ROOT / "verification/natural-river-network/entry-shallow-water-prepare-20261005-03"
CARRIER_INDEX_SHA = "232c9d1d378b02a7abc76670a8989fa97c58d7201b0ec3b323876ceaf5aedc56"
CARRIER_AUDIT_SHA = "fc0f18c09656ceefeffa5453f67a7f6a5f483e919273da993d32020b1ff38539"
CARRIER_SHA = "8c1fc0d0013cf99ca4dfe50d911aee654d3dee8c6b84999df6af4581d1faf70d"
MAX_CHUNK_BYTES = 64 * 1024**2
MAX_REPORT_BYTES = 1024**2
MAX_RSS_BYTES = 1024**3


def _pin(path):
    return {"path": str(path.resolve()), "sha256": file_sha256(path), "bytes": path.stat().st_size}


def _read(pin):
    path = Path(pin["path"]).resolve(strict=True)
    if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_CHUNK_BYTES
            or file_sha256(path) != pin["sha256"]
            or ("bytes" in pin and path.stat().st_size != pin["bytes"])):
        raise ValueError("saved input path/SHA/size mismatch: " + str(path))
    record = json.loads(path.read_bytes())
    if "identity_sha256" in pin and record.get("identity_sha256") != pin["identity_sha256"]:
        raise ValueError("saved input identity pin mismatch")
    return record


def _check_identity(record):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(",", ":"))
    for fragment in encoder.iterencode({key: value for key, value in record.items() if key != "identity_sha256"}):
        digest.update(fragment.encode("utf-8"))
    if digest.hexdigest() != record["identity_sha256"]:
        raise ValueError("saved content identity mismatch")


def compare(*, bank_audit=None, bank_audit_sha=None):
    bank_pin = {"path": str(BANK_INDEX), "sha256": BANK_SHA}
    index = _read(bank_pin)
    manifest = _read(index["manifest"])
    _check_identity(manifest)
    if (manifest["schema"] != "td-source-conforming-banks-v3"
            or manifest["policy_identity_sha256"] != index["policy_identity_sha256"]):
        raise ValueError("v3 manifest/schema/policy mismatch")
    parent_index_pin = {"path": str(CARRIER_PARENT / "index.json"), "sha256": CARRIER_INDEX_SHA}
    parent_audit_pin = {"path": str(CARRIER_PARENT / "independent-audit.json"), "sha256": CARRIER_AUDIT_SHA}
    parent = _read(parent_index_pin)
    parent_audit = _read(parent_audit_pin)
    if (parent_audit["status"] != "passed" or parent_audit["index_sha256"] != CARRIER_INDEX_SHA
            or parent["carrier"]["sha256"] != CARRIER_SHA
            or parent["inputs"]["fine"] != index["inputs"]["base_raster"]):
        raise ValueError("carrier parent audit/base binding mismatch")

    def validate_carrier(bundle):
        if (bundle["identity_sha256"] != parent["carrier"]["identity_sha256"]
                or bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])):
            raise ValueError("carrier saved array identity mismatch")

    carrier = load_bundle(Path(parent["carrier"]["path"]), expected_sha256=CARRIER_SHA,
                          validator=validate_carrier, max_bytes=MAX_CHUNK_BYTES)
    arrays, metadata = carrier["arrays"], carrier["metadata"]
    grid = manifest["grid"]
    if (metadata["spacing_m"] != grid["spacing_m"] or grid["center_offset_cells"] != .5
            or metadata["global_lattice_origin_m_xz"] != grid["origin_m_xz"]
            or metadata["parent_identities"]["fine"] != manifest["base_identity_sha256"]):
        raise ValueError("carrier/v3 global lattice or base mismatch")
    bed, overlay = arrays["derived_bed_m"], arrays["overlay_mask"]
    rows, columns = arrays["global_row"], arrays["global_column"]
    if (bed.size > 65536 or bed.dtype != np.dtype("float64") or overlay.dtype != bool or rows.dtype.kind not in "iu"
            or columns.dtype.kind not in "iu" or not np.isfinite(bed).all()
            or any(array.shape != bed.shape for array in (overlay, rows, columns))):
        raise ValueError("carrier finite bed/mask/global lattice shape mismatch")
    expected_rows, expected_columns = np.indices(bed.shape)
    first_row, first_column = metadata["global_origin_row_column"]
    if (not np.array_equal(rows, expected_rows + first_row)
            or not np.array_equal(columns, expected_columns + first_column)):
        raise ValueError("carrier global row/column coordinates inconsistent")
    locations = {(int(row), int(column)): local for local, (row, column) in enumerate(zip(rows.ravel(), columns.ravel()))}
    if len(locations) != bed.size:
        raise ValueError("duplicate carrier lattice ownership")
    after_saved_effects = bed.copy()
    components = {component["component_id"]: component for component in manifest["components"]}
    triangle_components = {triangle: component["component_id"] for component in manifest["components"]
                           for triangle in component["triangle_ids"]}
    seen, matched, matched_overlay, changed_overlay, changed_background = set(), 0, 0, 0, 0
    differences, cut_deltas, witnesses = [], [], []
    max_difference, peak_rss = 0., 0
    effect_pins = index["chunks"]["effects"]
    if ([pin["identity_sha256"] for pin in effect_pins] != manifest["chunk_identities"]["effects"]
            or len(effect_pins) > 4096):
        raise ValueError("effect chunk census mismatch")
    for pin in effect_pins:
        chunk = _read(pin)
        _check_identity(chunk)
        if (chunk["schema"] != "td-source-conforming-banks-v3-effects"
                or chunk["parent_identity_sha256"] != manifest["parent_identity_sha256"]
                or chunk["policy_identity_sha256"] != manifest["policy_identity_sha256"]):
            raise ValueError("effect chunk parent/policy mismatch")
        for effect in chunk["records"]:
            key = tuple(effect["global_key_row_column"])
            cell = effect["cell"]
            affected_components = {triangle_components[proposal["triangle_id"]]
                for proposal in cell["triangle_sources"] if proposal["triangle_id"] in triangle_components}
            if (len(key) != 2 or any(type(value) is not int for value in key) or key in seen
                    or effect["operation"] != "replace" or not effect["source_sample_reused"]
                    or effect["logical_owner"] is None or cell["status"] != "candidate"
                    or effect["policy_identity_sha256"] != manifest["policy_identity_sha256"]
                    or set(effect["component_ids"]) != affected_components or not affected_components
                    or any(components[name]["status"] != "candidate" for name in affected_components)):
                raise ValueError("effect unique ownership/accepted component/transaction mismatch")
            seen.add(key)
            if len(seen) > 2_000_000:
                raise MemoryError("effect unique-cell budget exceeded")
            delta_cut = effect["cut_delta_m3"]
            if (not math.isfinite(delta_cut) or not math.isfinite(cell["derived_bed_m"])
                    or abs(effect["after_cut_m3"] - effect["before_cut_m3"] - delta_cut) > 1e-10):
                raise ValueError("effect nonfinite/signed cut ledger mismatch")
            cut_deltas.append(delta_cut)
            local = locations.get(key)
            if local is None:
                continue
            matched += 1
            is_overlay = bool(overlay.ravel()[local])
            matched_overlay += int(is_overlay)
            before, after = float(bed.ravel()[local]), float(cell["derived_bed_m"])
            after_saved_effects.flat[local] = after
            bitwise_changed = np.float64(before).tobytes() != np.float64(after).tobytes()
            difference = after - before
            differences.append(difference)
            max_difference = max(max_difference, abs(difference))
            if difference != 0.:
                changed_overlay += int(is_overlay)
                changed_background += int(not is_overlay)
            if bitwise_changed:
                if len(witnesses) < 12:
                    witnesses.append({"global_key_row_column": list(key), "logical_owner": effect["logical_owner"],
                        "old_overlay_mask": is_overlay, "old_carrier_bed_m": before,
                        "v3_effect_bed_m": after, "signed_bed_delta_m": difference,
                        "bed_changed_bitwise": True})
        del chunk
        gc.collect()
        memory = psutil.Process().memory_info()
        peak_rss = max(peak_rss, memory.rss, getattr(memory, "peak_wset", 0))
        if peak_rss > MAX_RSS_BYTES:
            raise MemoryError("compatibility 1GiB RSS budget exceeded")
    if (len(seen) != manifest["summary"]["replace_cells"]
            or abs(math.fsum(cut_deltas) - manifest["material_ledger_delta"]["cut_rock_m3"]) > 1e-9):
        raise ValueError("effect census/material ledger mismatch")
    audit_pin, audit_status = None, "pending"
    if (bank_audit is None) != (bank_audit_sha is None):
        raise ValueError("bank audit path and SHA must be supplied together")
    if bank_audit is not None:
        audit_pin = {"path": str(bank_audit.resolve()), "sha256": bank_audit_sha}
        audit = _read(audit_pin)
        if (audit["status"] != "passed" or audit["index_sha256"] != BANK_SHA
                or audit["manifest_sha256"] != index["manifest"]["sha256"]):
            raise ValueError("v3 independent audit binding mismatch")
        audit_status = "passed"
    changed = changed_overlay + changed_background
    bitwise_changed_mask = np.any(
        np.ascontiguousarray(bed).view(np.uint8).reshape(*bed.shape, 8)
        != np.ascontiguousarray(after_saved_effects).view(np.uint8).reshape(*bed.shape, 8), axis=-1)
    bitwise_changed_count = int(bitwise_changed_mask.sum())
    return {"schema": "td-bank-carrier-compatibility-v1", "status": "completed_saved_effect_comparison",
        "inputs": {"v3_index": _pin(BANK_INDEX), "v3_manifest": index["manifest"], "v3_effects": effect_pins,
            "old_carrier": parent["carrier"], "source_parent_index": _pin(CARRIER_PARENT / "index.json"),
            "source_parent_audit": _pin(CARRIER_PARENT / "independent-audit.json"),
            "v3_independent_audit": audit_pin}, "v3_independent_audit_status": audit_status,
        "policy_identity_sha256": manifest["policy_identity_sha256"], "grid": grid,
        "carrier_entry_id": metadata["entry_id"], "carrier_cells": bed.size,
        "carrier_cells_checked": bed.size, "carrier_old_background_cells": int((~overlay).sum()),
        "comparison_filters_by_overlay_mask": False,
        "carrier_old_overlay_cells": int(overlay.sum()), "v3_replace_cells": len(seen),
        "effects_within_carrier": matched, "effects_outside_carrier": len(seen) - matched,
        "effects_on_old_overlay": matched_overlay, "effects_on_old_background": matched - matched_overlay,
        "changed_carrier_cells_strict": changed, "changed_old_overlay_cells_strict": changed_overlay,
        "changed_old_background_cells_strict": changed_background,
        "changed_carrier_cells_bitwise": bitwise_changed_count,
        "changed_old_overlay_cells_bitwise": int((bitwise_changed_mask & overlay).sum()),
        "changed_old_background_cells_bitwise": int((bitwise_changed_mask & ~overlay).sum()),
        "carrier_bed_bitwise_equal_after_saved_effects": bitwise_changed_count == 0,
        "bitwise_comparison_scope": "all carrier float64 cells after applying every overlapping accepted effect; unchanged parent not reaudited",
        "max_absolute_carrier_bed_delta_m": max_difference,
        "sum_absolute_carrier_bed_delta_m": math.fsum(abs(value) for value in differences),
        "signed_carrier_bed_delta_volume_m3": math.fsum(differences) * grid["spacing_m"]**2,
        "absolute_carrier_bed_delta_volume_m3": math.fsum(abs(value) for value in differences) * grid["spacing_m"]**2,
        "v3_material_cut_delta_m3": math.fsum(cut_deltas), "changed_cell_witnesses": witnesses,
        "same_bed": False, "same_bed_disproved_by_saved_effects": bitwise_changed_count > 0,
        "same_bed_reason": "nonzero_saved_effect_vs_carrier_bed_delta" if changed else
                           "bitwise_saved_effect_vs_carrier_bed_difference" if bitwise_changed_count else
                           "unchanged_parent_coverage_not_reaudited",
        "scope": "actual saved effects on the carrier global lattice; not a whole unchanged-parent overlay or hydraulic audit",
        "hydraulic_results_transferable_to_v3": False, "whole_v3_overlay_hydraulics_verified": False,
        "resource": {"actual_peak_rss_bytes": peak_rss, "max_rss_bytes": MAX_RSS_BYTES,
            "raw_chunks_loaded": 0, "effect_chunks_loaded_concurrently": 1,
            "source_resamples": 0, "solver_calls": 0, "max_report_bytes": MAX_REPORT_BYTES},
        "audit_code_sha256": file_sha256(Path(__file__))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bank-audit", type=Path)
    parser.add_argument("--bank-audit-sha256")
    args = parser.parse_args()
    output = args.output.resolve()
    verification = (ROOT / "verification/natural-river-network").resolve()
    if output.exists() or output == verification or not output.is_relative_to(verification):
        raise ValueError("new verification report directory required")
    report = compare(bank_audit=args.bank_audit, bank_audit_sha=args.bank_audit_sha256)
    payload = json.dumps(report, sort_keys=True, allow_nan=False, indent=2).encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise MemoryError("compatibility report exceeds 1MiB")
    publish_bytes(output / "compatibility.json", payload)
    print(json.dumps({key: report[key] for key in (
        "effects_within_carrier", "changed_carrier_cells_strict", "changed_old_overlay_cells_strict",
        "changed_old_background_cells_strict", "max_absolute_carrier_bed_delta_m",
        "absolute_carrier_bed_delta_volume_m3", "same_bed", "v3_independent_audit_status")}, sort_keys=True))


if __name__ == "__main__":
    main()
