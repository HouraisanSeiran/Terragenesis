"""Acquire bounded USGS channel measurements and audit explicit SI conversions."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes

BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/channel-measurements"
UNITS = dict(channel_flow=("ft^3/s", .3048 ** 3, "m3/s"), channel_width=("ft", .3048, "m"),
             channel_area=("ft^2", .3048 ** 2, "m2"), channel_velocity=("ft/s", .3048, "m/s"))


def reduce_measurements(collection, station):
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise ValueError("USGS original FeatureCollection required")
    rows, omitted = [], []
    for feature in collection["features"]:
        values = feature.get("properties", {})
        if values.get("monitoring_location_id") != station:
            raise ValueError("USGS station filter not respected")
        coordinates = feature.get("geometry", {}).get("coordinates")
        if (feature.get("geometry", {}).get("type") != "Point" or not isinstance(coordinates, list) or
                len(coordinates) != 2 or any(type(value) not in (float, int) or not math.isfinite(value) for value in coordinates) or
                not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90):
            raise ValueError("USGS located point geometry required")
        number = values.get("measurement_number")
        time = values.get("time")
        if not isinstance(time, str) or not time or not isinstance(number, str):
            raise ValueError("USGS dated measurement identity required")
        measured = {}
        missing = []
        for field, (unit, factor, target_unit) in UNITS.items():
            raw = values.get(field)
            if raw is None or raw == "":
                missing.append(field)
                continue
            if values.get(field + "_unit") != unit:
                raise ValueError("USGS unexpected original unit: " + field)
            try:
                numeric = float(raw)
            except (TypeError, ValueError) as error:
                raise ValueError("USGS nonnumeric measured value") from error
            if not math.isfinite(numeric):
                raise ValueError("USGS nonfinite measurement")
            measured[field] = numeric * factor
        if missing or any(value <= 0 for value in measured.values()):
            omitted.append(dict(measurement_number=number, time=time,
                                reason="missing or nonpositive hydraulic quantity", missing_fields=missing))
            continue
        mean_depth = measured["channel_area"] / measured["channel_width"]
        ratio = measured["channel_area"] * measured["channel_velocity"] / measured["channel_flow"]
        rows.append(dict(measurement_number=number, time=time, channel_name=values.get("channel_name"),
                         station=station, coordinate_lon_lat=coordinates, measured_si=measured,
                         derived_mean_depth_m=mean_depth, derived_area_velocity_to_discharge_ratio=ratio,
                         channel_material=values.get("channel_material"), channel_stability=values.get("channel_stability"),
                         original_record_id=values.get("id"), original_field_visit_id=values.get("field_visit_id")))
    groups = Counter(row["channel_name"] for row in rows)
    return dict(station=station, retained_measurements=rows, omitted_measurements=omitted,
                channel_groups=dict(groups), units_si={field: value[2] for field, value in UNITS.items()},
                mean_depth_semantics="measured area / measured width; no cross-section shape or bed elevation",
                balance_ratio_semantics="reported average velocity and rounded measurements can differ; no data alteration",
                calibration_performed=False, recipe_parameters_changed=False,
                limitations="Station/channel groups and dates must be reviewed before fitting; no bankfull identification, measured bed slope, roughness or surveyed section point cloud.")


def fetch_bounded(url, max_bytes=4 * 1024 * 1024):
    with requests.get(url, timeout=(10, 30), stream=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type:
            raise ValueError("USGS returned non-JSON primary resource")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("USGS primary resource budget exceeded")
            chunks.append(chunk)
        payload = b"".join(chunks)
        value = json.loads(payload)
        return payload, value, dict(requested_url=url, retrieved_url=response.url,
            retrieved_utc=datetime.now(timezone.utc).isoformat(), status_code=response.status_code,
            content_type=content_type, bytes=len(payload), response_date=response.headers.get("Date"))


def acquire(station="USGS-06719505", limit=100):
    if re.fullmatch(r"USGS-[0-9]{8,15}", station) is None or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("bounded USGS station and limit required")
    dictionary_bytes, dictionary, dictionary_provenance = fetch_bounded(BASE + "/queryables?f=json")
    properties = dictionary.get("properties", {})
    required = set(UNITS) | {name + "_unit" for name in UNITS} | {"time", "monitoring_location_id", "channel_name"}
    if not required.issubset(properties):
        raise ValueError("USGS official field dictionary changed")
    url = BASE + f"/items?monitoring_location_id={station}&limit={limit}&f=json"
    measurement_bytes, measurements, measurement_provenance = fetch_bounded(url)
    reduced = reduce_measurements(measurements, station)
    if len(measurements["features"]) > limit:
        raise ValueError("USGS response exceeded requested bounded sample")
    directory = ROOT / "verification/usgs-channel-reference" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    publish_bytes(directory / "queryables.json", dictionary_bytes)
    publish_bytes(directory / "measurements.json", measurement_bytes)
    sources = []
    for filename, provenance in (("queryables.json", dictionary_provenance), ("measurements.json", measurement_provenance)):
        sources.append(dict(path=str(directory / filename), sha256=file_sha256(directory / filename), **provenance))
    report = dict(schema="usgs-channel-primary-reference-v1", sources=sources, **reduced,
                  requested_limit=limit, original_feature_count=len(measurements["features"]),
                  pagination_links=measurements.get("links", []), complete_station_history_claimed=False,
                  auditor_sha256=file_sha256(__file__))
    publish_bytes(directory / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return directory / "report.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", default="USGS-06719505")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    output = acquire(args.station, args.limit)
    print(json.dumps(dict(path=str(output), sha256=file_sha256(output))))
