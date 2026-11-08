"""Pin saved coastal terrain and debit witnessed regional packets into FV delta."""

import copy

import numpy as np

from terrain_pipeline.common_infra import identity
from .environment_coastal_delta import prepare_coastal_delta
from .environment_regional_hydraulics import validate_packet
from . import environment_delta_fv as fv


def prepare(store):
    return prepare_coastal_delta(store)


def _packet(packet, source):
    validate_packet(packet)
    if packet["source_world_identity"] != source["source_world_identity"]:
        raise ValueError("packet belongs to another source world")
    if (packet["target_node"] != source["target_node"] or
            packet["source_node"] not in source["inlet_donor_nodes"]):
        raise ValueError("packet is not an actual saved mouth receiver edge")
    cols = source["source_shape_zx"][1]
    origin = source["source_origin_native_xz"]
    for key in ("source", "target"):
        row, col = divmod(packet[key + "_node"], cols)
        if packet[key + "_native_xz"] != [origin[0] + col, origin[1] + row]:
            raise ValueError("packet native coordinates differ from saved source frame")
    start, end = packet["time_start_s"], packet["time_end_s"]
    if (not np.isfinite([start, end, packet["water_m3"], packet["solid_m3"]]).all()
            or start < 0. or end <= start or min(packet["water_m3"], packet["solid_m3"]) < 0.):
        raise ValueError("positive finite physical packet interval required")


def initialize(prepared, first_packet, *, bounds=None, config=fv.FVDeltaConfig(), erodible_cover_m=0.):
    """Crop native cells without resampling or excavating the immutable source bed.

    Bounds are source-local [left, top, right, bottom]; cut marine edges are
    artificial open boundaries. The default is at most 64 columns by 48 rows.
    """
    if prepared["identity_sha256"] != identity(prepared["arrays"], prepared["metadata"]):
        raise ValueError("prepared coastal source identity mismatch")
    a, m = prepared["arrays"], prepared["metadata"]
    rows, cols = a["bed_m"].shape
    target = first_packet["target_node"]
    if type(target) is not int or not 0 <= target < rows * cols:
        raise ValueError("target node outside saved coastal source")
    row, col = divmod(target, cols)
    if not a["ocean_mask"][row, col]:
        raise ValueError("packet target must be actual saved ocean mouth")
    if bounds is None:
        left = min(max(0, col - 46), max(0, cols - 64))
        top = min(max(0, row - 17), max(0, rows - 48))
        bounds = (left, top, min(cols, left + 64), min(rows, top + 48))
    if (len(bounds) != 4 or any(type(v) is not int for v in bounds)):
        raise ValueError("four integer native crop bounds required")
    left, top, right, bottom = bounds
    if not (0 <= left <= col < right <= cols and 0 <= top <= row < bottom <= rows):
        raise ValueError("crop must contain actual mouth within saved source")
    source = {"prepared_identity_sha256": prepared["identity_sha256"],
              "source_world_identity": m["source_world_identity"],
              "source_shape_zx": [rows, cols], "source_origin_native_xz": m["origin_native_xz"],
              "target_node": target, "inlet_donor_nodes": np.flatnonzero(a["receiver"] == target).tolist(),
              "crop_bounds_native": list(bounds), "prepared_source": copy.deepcopy(m),
              "boundary_semantics": "cropped ocean perimeter is artificial fixed-stage marine boundary; other perimeter closed",
              "bed_semantics": "unchanged saved native30m source; declared finite erodible cover below original bed",
              "erodible_cover_m": float(erodible_cover_m),
              "heat_semantics": "upstream packets carry no heat stock; no heat transport claimed"}
    _packet(first_packet, source)
    origin = [(m["origin_native_xz"][0] + left) * 30., (m["origin_native_xz"][1] + top) * 30.]
    sl = np.s_[top:bottom, left:right]
    product = fv.initialize(a["bed_m"][sl], a["ocean_mask"][sl],
        np.array([(row - top) * (right - left) + col - left], dtype=np.int64),
        origin_m_xz=origin, source_world_identity=m["source_world_identity"],
        source_identity=prepared["identity_sha256"], spacing_m=30.,
        initial_time_s=first_packet["time_start_s"], config=config, erodible_cover_m=erodible_cover_m)
    product["metadata"]["coastal_source"] = source
    product["identity_sha256"] = identity(product["arrays"], product["metadata"])
    fv.validate(product)
    return product


def advance(product, packets):
    """Verify the original receiver only at the inlet, then use FV face fluxes."""
    fv.validate(product)
    if product["metadata"].get("diagnostic_control"):
        raise ValueError("diagnostic control cannot continue as an actual world receiver")
    if not isinstance(packets, (list, tuple)) or not packets:
        raise ValueError("nonempty actual source packets required")
    source = product["metadata"]["coastal_source"]
    records, seen = [], set(product["metadata"]["consumed_forcing_ids"])
    time = product["metadata"]["physical_time_s"]
    for packet in packets:
        _packet(packet, source)
        if packet["packet_id"] in seen:
            raise ValueError("duplicate packet would consume source export twice")
        if packet["time_start_s"] != time:
            raise ValueError("packet physical time intervals must be contiguous")
        seen.add(packet["packet_id"])
        time = packet["time_end_s"]
        records.append({"id": packet["packet_id"], "time_start_s": packet["time_start_s"],
                        "time_end_s": time, "water_m3": packet["water_m3"], "solid_m3": packet["solid_m3"],
                        "source": "already-debited actual saved regional mouth export",
                        "source_packet": copy.deepcopy(packet)})
    return fv.advance(product, records)
