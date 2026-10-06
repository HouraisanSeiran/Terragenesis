"""Independent native saved-hour cut ledgers behind full continuation acceptance."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.publish_td_accepted_review import accepted_inputs


def cut_ledger(topology, storage, *, partition_row, partition_column, duration_s):
    shape = topology["height_m"].shape
    if (type(partition_row) is not int or type(partition_column) is not int or
            not 0 < partition_row < shape[0] or not 0 < partition_column < shape[1] or
            not math.isfinite(duration_s) or duration_s <= 0):
        raise ValueError("bounded native integer partition and duration required")
    valid = topology["valid_mask"].ravel()
    if not valid.all() or topology["protected_mask"].any():
        raise ValueError("complete unprotected native coverage required")
    np.testing.assert_array_equal(storage["height_m"], topology["height_m"])
    for name in ("valid_mask", "face_cells", "receiver"):
        np.testing.assert_array_equal(storage[name], topology[name])
    faces = topology["face_cells"]
    if faces.dtype != np.int64 or faces.ndim != 2 or faces.shape[1] != 2:
        raise ValueError("typed native D4 face mapping required")
    cell_ids = np.arange(valid.size).reshape(shape)
    expected = np.concatenate((np.column_stack((cell_ids[:, :-1].ravel(), cell_ids[:, 1:].ravel())),
                               np.column_stack((cell_ids[:-1].ravel(), cell_ids[1:].ravel()))))
    canonical = np.sort(faces, axis=1)
    if (len(faces) != len(expected) or np.any(canonical < 0) or np.any(canonical >= valid.size) or
            len(np.unique(canonical, axis=0)) != len(faces)):
        raise ValueError("incomplete or duplicated native face coverage")
    face_keys = canonical[:, 0] * valid.size + canonical[:, 1]
    expected_keys = expected[:, 0] * valid.size + expected[:, 1]
    np.testing.assert_array_equal(np.sort(face_keys), np.sort(expected_keys))
    fluxes = {}
    for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        values = storage[name]
        if values.dtype != np.float64 or values.shape != (len(faces),) or not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError("bounded finite nonnegative saved face evidence required")
        if name.startswith("active_") and np.any(values > duration_s + 1e-8):
            raise ValueError("saved face activity exceeds hour duration")
        fluxes[name] = values
    rows, columns = np.indices(shape)
    region = ((rows >= partition_row) * 2 + (columns >= partition_column)).ravel()
    first_region, second_region = region[faces[:, 0]], region[faces[:, 1]]
    shared = first_region != second_region
    net = fluxes["face_forward_m3"] - fluxes["face_reverse_m3"]
    divergence = np.bincount(faces[:, 0], weights=net, minlength=valid.size)
    divergence -= np.bincount(faces[:, 1], weights=net, minlength=valid.size)
    internal_net = storage["internal_net_m3"]
    if internal_net.dtype != np.float64 or internal_net.shape != (1, valid.size) or not np.isfinite(internal_net).all():
        raise ValueError("typed saved per-cell internal ledger required")
    difference = internal_net[0] + divergence
    if np.any(np.abs(difference) > 1e-6 + 1e-10 * np.abs(divergence)):
        raise ValueError("original saved internal water ledger differs from face divergence")
    if np.any(fluxes["active_forward_s"] + fluxes["active_reverse_s"] > duration_s + 1e-8):
        raise ValueError("combined face activity exceeds hour duration")
    boundary_net = []
    whole_divergence = []
    residuals = []
    for quadrant in range(4):
        exits = shared & (first_region == quadrant)
        entries = shared & (second_region == quadrant)
        boundary = math.fsum(float(value) for value in net[exits]) - math.fsum(float(value) for value in net[entries])
        actual = -math.fsum(float(value) for value in internal_net[0, region == quadrant])
        allowed = 1e-6 + 1e-10 * math.fsum(abs(float(value)) for value in net)
        if abs(boundary - actual) > allowed:
            raise ValueError("quadrant divergence differs from shared-face net ledger")
        boundary_net.append(boundary)
        whole_divergence.append(actual)
        residuals.append(actual - boundary)
    records = []
    for first in range(4):
        for second in range(first + 1, 4):
            selected = shared & (((first_region == first) & (second_region == second)) |
                                 ((first_region == second) & (second_region == first)))
            indices = np.flatnonzero(selected)
            if not len(indices):
                continue
            signs = np.where(first_region[indices] == first, 1., -1.)
            outward = math.fsum(float(sign * value) for sign, value in zip(signs, net[indices]))
            forward = math.fsum(float(value) for value in fluxes["face_forward_m3"][indices])
            reverse = math.fsum(float(value) for value in fluxes["face_reverse_m3"][indices])
            records.append(dict(regions=[first, second], shared_face_count=len(indices),
                face_indices=indices.tolist(), canonical_endpoint_sha256=hashlib.sha256(
                    np.ascontiguousarray(canonical[indices], dtype="<i8").tobytes()).hexdigest(),
                first_outward_m3=outward, second_outward_m3=-outward, paired_residual_m3=0.,
                saved_forward_m3=forward, saved_reverse_m3=reverse,
                both_directions_integrated_face_count=int(np.count_nonzero(
                    (fluxes["face_forward_m3"][indices] > 0) & (fluxes["face_reverse_m3"][indices] > 0)))))
    if abs(math.fsum(boundary_net)) > 1e-8 + 1e-12 * math.fsum(abs(value) for value in boundary_net):
        raise ValueError("four quadrant internal exchange fails cancellation")
    return dict(partition_row=partition_row, partition_column=partition_column,
        face_count=len(faces), unique_shared_face_count=int(shared.sum()),
        duplicated_boundary_evaluations=False, seams=records,
        quadrant_outward_m3=boundary_net, quadrant_divergence_m3=whole_divergence,
        quadrant_residual_m3=residuals, total_internal_residual_m3=math.fsum(boundary_net),
        scope="Native control-volume partition of one saved global solution; engineering exterior outflow is not a shared internal face.")


def audit(path, expected_sha256):
    accepted = accepted_inputs(path, expected_sha256)
    topology, grid = read_record(accepted["acceptance_arguments"]["hierarchy_record"])
    results = {}
    for scenario in ("ordinary", "strong"):
        comparison_record = accepted["comparison_records"][scenario]
        comparison_path = Path(comparison_record["path"])
        if file_sha256(comparison_path) != comparison_record["expected_sha256"]:
            raise ValueError("accepted hourly comparison pin mismatch")
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        pages = comparison["pages"]["1.25"]
        if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
            raise ValueError("complete fine hourly seam coverage required")
        hours = []
        for page in pages:
            storage, metadata = read_record(page["storage"])
            if (metadata["hierarchy_identity_sha256"] != accepted["acceptance_arguments"]["hierarchy_record"]["expected_identity"] or
                    metadata["spacing_m"] != grid["spacing_m"]):
                raise ValueError("saved seam input topology/grid identity mismatch")
            if (metadata["chunk_start_s"] != page["hour"] * 3600. or
                    metadata["chunk_end_s"] != (page["hour"] + 1) * 3600. or
                    metadata["dt_s"] != 3600. or storage["depth_m"].shape != (2, topology["height_m"].size)):
                raise ValueError("saved native seam physical time coverage mismatch")
            ledger = cut_ledger(topology, storage, partition_row=topology["height_m"].shape[0] // 2,
                                partition_column=topology["height_m"].shape[1] // 2, duration_s=3600.)
            ledger.update(hour=page["hour"], storage=page["storage"])
            hours.append(ledger)
        results[scenario] = hours
    if file_sha256(path) != expected_sha256:
        raise ValueError("independent continuation acceptance changed during seam audit")
    info = psutil.Process().memory_info()
    resource = dict(peak_rss_bytes=int(getattr(info, "peak_wset", info.rss)),
                    peak_private_bytes=getattr(info, "peak_pagefile", None))
    if resource["peak_private_bytes"] is None or max(resource.values()) > 1073741824:
        raise MemoryError("independent seam audit requires bounded RSS/private evidence")
    return dict(schema="td-independent-hourly-native-seams-v1", acceptance_path=str(Path(path).resolve()),
        acceptance_sha256=expected_sha256, cases=results, original_native_spacing_m=grid["spacing_m"],
        all_hourly_native_partition_ledgers_passed=True, spatial_refinement_checked=False,
        independently_solved_domains=False, solver_advanced=False, natural_outlet_verified=False,
        hydraulic_ready=False, publishable=False, auditor_sha256=file_sha256(__file__),
        resource=resource)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--acceptance-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.acceptance, args.acceptance_sha256)
    output = ROOT / "verification/surface-cross-domain" / ("hourly-native-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(output), sha256=file_sha256(output), passed=True), ensure_ascii=False))
