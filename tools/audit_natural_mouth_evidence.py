"""Read original local evidence without treating a DEM trace as a certified mouth."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import publish_bytes


PDF_SHA256 = "48ba1a0678dacf2de6a18961fb4c6a30de40e25cc9a6d1f89eb7fd92e9733057"
CONTROL_SHA256 = "c1af9c7915156d15e6a7caf7df50400430c310497f5ef113ce2c5456429508d5"
TRACE_SHA256 = "35d986d581247a783a740fcdbe6f69c5e871e2bb494d5127e48229bfb60f2128"


def read_pdf_page(path, page_index):
    try:
        from PyPDF2 import PdfReader
    except ModuleNotFoundError:
        runtime = ROOT / ".scratch/terrain-framework/pdf-runtime"
        if not runtime.is_dir():
            raise RuntimeError("PDF reader unavailable: install PyPDF2 or provide the bundled pdf-runtime")
        sys.path.insert(0, str(runtime))
        try:
            import pypdfium2
        except ModuleNotFoundError as error:
            raise RuntimeError("PDF reader unavailable: bundled pypdfium2 could not be imported") from error
        document = pypdfium2.PdfDocument(str(path))
        return document[page_index].get_textpage().get_text_range(), len(document), "pypdfium2"
    reader = PdfReader(str(path))
    return reader.pages[page_index].extract_text(), len(reader.pages), "PyPDF2"


def record(path, expected=None):
    source = Path(path).resolve(strict=True)
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if expected is not None and actual != expected:
        raise ValueError("primary evidence hash changed: " + str(source))
    return {"path": str(source), "sha256": actual, "bytes": source.stat().st_size}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       indent=2) + "\n").encode("utf-8")


def distance_m(first, second):
    first_lat, first_lon = map(math.radians, first)
    second_lat, second_lon = map(math.radians, second)
    haversine = (math.sin((second_lat - first_lat) / 2) ** 2
                 + math.cos(first_lat) * math.cos(second_lat)
                 * math.sin((second_lon - first_lon) / 2) ** 2)
    return 2 * 6371008.8 * math.asin(min(1., math.sqrt(haversine)))


def inspect(geography_root):
    data = Path(geography_root) / "01-完整流域样本/data"
    sources = {
        "government_plan": record(data / "ninghai_water_plan_ch3.pdf", PDF_SHA256),
        "area_selected_control": record(data / "funxi_control_section.json", CONTROL_SHA256),
        "dem_trace": record(data / "funxi_mouth_trace.json", TRACE_SHA256),
    }
    page, page_count, pdf_reader = read_pdf_page(sources["government_plan"]["path"], 10)
    normalized = "".join(page.split())
    expected = "折北经凫溪村又向东流入铁港出海"
    if expected not in normalized:
        raise ValueError("original PDF no longer supports the declared named relationship")
    control = json.loads(Path(sources["area_selected_control"]["path"]).read_text(encoding="utf-8"))
    trace = json.loads(Path(sources["dem_trace"]["path"]).read_text(encoding="utf-8"))
    tidal = control["tidal_outlet"]
    mouth = trace["dem_derived_mouth"]
    path = trace["path"]
    if not path or not all(math.isfinite(float(point[key])) for point in path
                           for key in ("lat", "lon", "elev_m")):
        raise ValueError("invalid original trace")
    rises = [float(after["elev_m"] - before["elev_m"])
             for before, after in zip(path, path[1:]) if after["elev_m"] > before["elev_m"]]
    separation = distance_m((tidal["lat"], tidal["lon"]), (mouth["lat"], mouth["lon"]))
    report = {
        "schema": "natural-mouth-geographic-evidence-v1",
        "reviewed_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "government_evidence": {
            "pdf_physical_page": 11, "printed_page": 4, "page_count": page_count,
            "page_text": page, "normalized_quote": expected,
            "source_url": "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web3575/site/attach/0/7698bd2994984fba8510f192bd61f997.pdf",
            "method": f"{pdf_reader} original text; page-image visual acceptance not performed",
            "named_river_sea_relationship_supported": True,
            "contains_downstream_yangmeiling_reservoir": "杨梅岭水库" in normalized,
        },
        "stages": {
            "named_relationship": "supported_by_original_government_plan",
            "mouth_position": "unconfirmed_candidates_only",
            "original_or_observed_connectivity": "unconfirmed",
        },
        "candidates": {
            "tidal_reference": {"lat": tidal["lat"], "lon": tidal["lon"],
                                "note": tidal["note"], "certified": False},
            "dem_derived_mouth": dict(mouth, certified=False),
            "candidate_separation_m": separation,
            "coordinate_system": "source coordinates labelled latitude/longitude; no independent survey",
        },
        "trace_diagnostics": {
            "points": len(path), "original_height_rising_edges": len(rises),
            "max_rising_edge_m": max(rises, default=0.),
            "total_positive_height_change_m": math.fsum(rises),
            "caveat": trace["caveat"],
            "geographic_candidate_is_not_hydraulic_bed": True,
        },
        "missing_evidence": [
            "Independent located mouth region or section with uncertainty and acquisition date",
            "Observed river-to-coast continuous geometry through reservoir and tidal reach",
            "Unknown/cropped coverage and dam/embankment/control-structure evidence",
        ],
        "natural_outlet_verified": False,
        "hydraulic_tailwater_certified": False,
        "engineering_connection_proves_original_connectivity": False,
    }
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [tidal["lon"], tidal["lat"]]},
         "properties": {"id": "tidal_reference", "certified": False, "note": tidal["note"]}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [mouth["lon"], mouth["lat"]]},
         "properties": {"id": "dem_candidate", "certified": False, "note": trace["caveat"]}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[point["lon"], point["lat"]] for point in path]},
         "properties": {"id": "original_dem_trace", "certified": False, "height_semantics": "original samples; rising edges retained"}},
    ]
    for source in sources.values():
        record(source["path"], source["sha256"])
    return report, {"type": "FeatureCollection", "features": features}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geography-root", type=Path, default=Path("D:/geography"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report, layer = inspect(args.geography_root)
    publish_bytes(args.output / "evidence.json", encode(report))
    publish_bytes(args.output / "candidate-locations.geojson", encode(layer))
    manifest = {"algorithm": report["schema"], "sources": report["sources"],
                "files": [record(args.output / name) for name in ("evidence.json", "candidate-locations.geojson")],
                "auditor": record(__file__), "natural_outlet_verified": False}
    publish_bytes(args.output / "manifest.json", encode(manifest))
    print(json.dumps({"output": str(args.output.resolve()), "stages": report["stages"],
                      "candidate_separation_m": report["candidates"]["candidate_separation_m"],
                      "trace": report["trace_diagnostics"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
