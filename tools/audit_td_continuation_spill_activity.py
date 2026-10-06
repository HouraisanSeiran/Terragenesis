"""Independent saved-frame wet connectivity and actual cross-catchment volume audit."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def audit(report_path, expected_sha256):
    path = Path(report_path).resolve(strict=True)
    if file_sha256(path) != expected_sha256:
        raise ValueError("external continuation audit pin mismatch")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("checkpoint_chain_checked") is not True or report.get("saved_frames") != 25:
        raise ValueError("complete independently checked saved state series required")
    selection_path = Path(report["comparison_path"])
    if file_sha256(selection_path) != report["comparison_sha256"]:
        raise ValueError("saved series selection pin mismatch")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    inputs = json.loads((selection_path.parent / "run-inputs.json").read_text(encoding="utf-8"))
    source = inputs["hierarchy"]
    topology, unused_metadata = read_record({"path": source["path"], "expected_sha256": source["sha256"],
                                            "expected_identity": source["identity"]})
    owners = topology["contribution_owner"].ravel()
    owners_unique, labels = np.unique(owners[topology["valid_mask"].ravel()], return_inverse=True)
    owner_index = np.full(owners.shape, -1, dtype=np.int64)
    owner_index[topology["valid_mask"].ravel()] = labels
    faces = topology["face_cells"]
    first, second = faces.T
    cross = owners[first] != owners[second]
    summaries = {}
    for step in report["substeps_s"]:
        pages = selection["pages"][str(step)]
        if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
            raise ValueError("saved hourly activity coverage mismatch")
        frames = []
        intervals = []
        for hour, page in enumerate(pages):
            arrays, metadata = read_record(page["storage"])
            for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
                np.testing.assert_array_equal(arrays[name], topology[name])
            if metadata["hierarchy_identity_sha256"] != source["identity"]:
                raise ValueError("activity topology identity mismatch")
            bed = arrays["height_m"].ravel()
            threshold = metadata["parameters"]["wet_threshold_m"]
            for frame in ((0, 1) if hour == 0 else (1,)):
                depth = arrays["depth_m"][frame]
                wet = depth > threshold
                head = bed + depth
                connected = wet[first] & wet[second] & (np.minimum(head[first], head[second]) > np.maximum(bed[first], bed[second]) + threshold)
                wet_cells = np.flatnonzero(wet)
                index = np.full(len(wet), -1, dtype=np.int64)
                index[wet_cells] = np.arange(len(wet_cells))
                graph = coo_matrix((np.ones(int(connected.sum()), dtype=np.int8),
                                    (index[first[connected]], index[second[connected]])),
                                   shape=(len(wet_cells), len(wet_cells))).tocsr()
                count, component_labels = connected_components(graph, directed=False)
                if count != int(arrays["wet_pool_count"][frame]):
                    raise ValueError("independent sparse wet connectivity differs from saved pool count")
                memberships = np.unique(np.column_stack((component_labels, owners[wet_cells])), axis=0)
                span = np.bincount(memberships[:, 0], minlength=count)
                depth_bands = {str(value): {"cell_count": int(np.count_nonzero(depth >= value)),
                    "surface_volume_m3": float(depth[depth >= value].sum() * metadata["spacing_m"] ** 2)}
                    for value in (.0001, .001, .01, .1, 1., 5., 10.)}
                frames.append({"frame": hour + frame, "time_s": (hour + frame) * metadata["dt_s"],
                               "wet_cells": len(wet_cells), "wet_components": int(count),
                               "components_spanning_multiple_static_catchments": int(np.count_nonzero(span > 1)),
                               "largest_component_cells": int(np.bincount(component_labels).max(initial=0)),
                               "open_cross_catchment_faces": int(np.count_nonzero(connected & cross)),
                               "depth_bands_display_diagnostic_only": depth_bands})
            forward = arrays["face_forward_m3"]
            reverse = arrays["face_reverse_m3"]
            net = forward - reverse
            leaf_net = np.bincount(owner_index[second[cross]], weights=net[cross], minlength=len(owners_unique))
            leaf_net -= np.bincount(owner_index[first[cross]], weights=net[cross], minlength=len(owners_unique))
            saved_leaf_net = np.bincount(owner_index[topology["valid_mask"].ravel()],
                                        weights=arrays["internal_net_m3"][0, topology["valid_mask"].ravel()],
                                        minlength=len(owners_unique))
            if np.any(abs(leaf_net - saved_leaf_net) > 1e-6 + 1e-10 * abs(saved_leaf_net)):
                raise ValueError("actual cross-catchment face exchange differs from native leaf ledger")
            intervals.append({"hour": hour, "start_s": hour * metadata["dt_s"],
                              "end_s": (hour + 1) * metadata["dt_s"],
                              "forward_cross_catchment_m3": float(forward[cross].sum()),
                              "reverse_cross_catchment_m3": float(reverse[cross].sum()),
                              "cross_faces_with_actual_exchange": int(np.count_nonzero(cross & ((forward > 0) | (reverse > 0)))),
                              "faces_with_both_direction_integrals": int(np.count_nonzero(cross & (forward > 0) & (reverse > 0))),
                              "largest_leaf_ledger_error_m3": float(abs(leaf_net - saved_leaf_net).max(initial=0))})
            del arrays
        summaries[str(step)] = {"frames": frames, "intervals": intervals,
                                "final_wet_components": frames[-1]["wet_components"]}
    return {"schema": "td-independent-saved-spill-activity-v1", "audit_path": str(path),
            "audit_sha256": expected_sha256, "hierarchy": source, "series": summaries,
            "static_catchments": len(owners_unique), "cross_catchment_faces": int(cross.sum()),
            "native_pool_count_independently_verified": True, "native_leaf_flux_divergence_verified": True,
            "solver_advanced": False, "hydraulic_ready": False, "natural_outlet_verified": False,
            "auditor_sha256": file_sha256(__file__),
            "limitations": "Hourly observations of wet connectivity and integrated D4 exchange, not exact spill event timing, common lake stages, flow momentum or natural mouths."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    result = audit(arguments.audit, arguments.expected_sha256)
    output = ROOT / "verification/td-basin-generation" / ("independent-spill-activity-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(output), "series": {step: {"initial_components": value["frames"][0]["wet_components"],
        "rain_end_components": value["frames"][6]["wet_components"], "final_components": value["frames"][-1]["wet_components"]}
        for step, value in result["series"].items()}}))
