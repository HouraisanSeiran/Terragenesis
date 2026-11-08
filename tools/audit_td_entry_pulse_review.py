"""Decode every exported pulse array and compare with the immutable saved NPZ."""

import argparse
import base64
import io
import json
from pathlib import Path
import sys
import zlib

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_entry_shallow_water import read_bundle, read_json, check_memory


def audit(index):
    review = read_json(index["review"])
    event = read_json(review["index_pin"])
    report = read_json(review["audit_pin"])
    if (review["input_index_sha256"] != report["index_sha256"] or report["status"] != "passed"
            or review["source_isolated_reception"] != report["source_isolated_reception"]
            or review["comparison"] != report["comparison"]):
        raise ValueError("lossless review no longer bound to event audit")
    count = 0

    def compare(packet, value):
        nonlocal count
        if packet["encoding"] != "npy-zlib-base64" or packet["order"] != "C":
            raise ValueError("unknown lossless array contract")
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(base64.b64decode(packet["data"], validate=True), value.nbytes+65536)
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError("lossless array compressed payload invalid or oversized")
        stream = io.BytesIO(decoded)
        actual = np.load(stream, allow_pickle=False)
        if (stream.tell() != len(decoded) or actual.dtype != value.dtype or actual.shape != value.shape
                or packet["dtype"] != actual.dtype.str or packet["shape"] != list(actual.shape)
                or not actual.flags.c_contiguous or actual.tobytes(order="C") != value.tobytes(order="C")):
            raise ValueError("exported pulse array is not an exact saved match")
        count += 1
        check_memory()

    for key, group in (("carrier", "arrays"), ("forcing", "upstream_Q_schedule"), ("geometry", "dry_drain")):
        bundle = read_bundle(event[key])
        for name, packet in review[group].items():
            if isinstance(packet, dict) and packet.get("encoding"):
                if name == "global_xyz_m":
                    arrays, metadata = bundle["arrays"], bundle["metadata"]
                    origin = metadata["global_lattice_origin_m_xz"]
                    value = np.stack((origin[0]+(arrays["global_column"]+.5)*metadata["spacing_m"], arrays["derived_bed_m"],
                                      origin[1]+(arrays["global_row"]+.5)*metadata["spacing_m"]), axis=-1)
                elif name == "interval_total_q_m3_s":
                    value = bundle["arrays"]["forcing_m3_s"].sum(axis=2)
                else:
                    value = bundle["arrays"][name]
                compare(packet, value)
        if key == "carrier":
            for name in ("chain_xyz_m", "chain_native_cell_ids"):
                compare(review["chain_90m"][name], bundle["arrays"][name])
        del bundle
    partial = index["schema"] == "td-entry-pulse-partial-review-export-v1"
    expected_levels = [0] if partial else [0, 1]
    formal = bool(report["time_refinement_verified"] and report["upstream_pulse_to_saved_source_wet_support_verified"])
    if ([case["level"] for case in event["cases"]] != expected_levels
            or len(review["frames"]) != len(expected_levels)
            or review["formal_consumption_allowed"] != formal or (partial and formal)):
        raise ValueError("lossless review omitted or promoted a time level")
    for frame, case in zip(review["frames"], event["cases"]):
        if frame["case_id"] != case["case_id"] or frame["state_pin"] != case["state"]:
            raise ValueError("lossless review changed frame identity")
        state = read_bundle(case["state"])
        for name in ("time_s", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s", "initial_depth_m", "ledger"):
            compare(frame[name], state["arrays"][name])
        del state
    return dict(schema="td-entry-pulse-lossless-review-audit-v1", status="passed", arrays_checked=count,
                saved_frames_checked=25*len(expected_levels), all_arrays_bitwise_equal=True, solver_calls=0, resampling_calls=0,
                review_sha256=index["review"]["sha256"], actual_peak_rss_bytes=check_memory())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new lossless audit path required")
    result = audit(read_json(dict(path=str(args.input.resolve()), sha256=args.sha256)))
    result.update(index_sha256=args.sha256, audit_code_sha256=file_sha256(Path(__file__)))
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    print(json.dumps(result))


if __name__ == "__main__":
    main()
