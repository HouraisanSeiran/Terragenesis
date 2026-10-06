"""Evidence gates for a natural river-to-sea outlet.

This module classifies evidence; it does not infer a natural outlet from an
engineering boundary, a DEM trace, or a named geographic relationship.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "td-natural-outlet-certification-v1"
REQUIRED_GATES = (
    "independent_outlet_coordinates",
    "continuous_river_sea_connection",
    "vertical_datum_and_uncertainty",
)
EXPECTED_SOURCE_SHA256 = {
    "official_pdf": "48ba1a0678dacf2de6a18961fb4c6a30de40e25cc9a6d1f89eb7fd92e9733057",
    "control": "c1af9c7915156d15e6a7caf7df50400430c310497f5ef113ce2c5456429508d5",
    "dem_trace": "35d986d581247a783a740fcdbe6f69c5e871e2bb494d5127e48229bfb60f2128",
}
FAILURE_REASONS = {
    "missing_independent_outlet_coordinates",
    "outlet_coordinate_is_upstream_reference",
    "dem_trace_is_candidate_only",
    "missing_continuous_river_sea_connection",
    "dem_trace_has_unresolved_height_rises",
    "missing_vertical_datum",
    "missing_vertical_uncertainty",
    "source_file_missing",
    "source_hash_mismatch",
    "invalid_evidence_shape",
    "natural_outlet_flag_mismatch",
}


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def _finite_coordinates(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return math.isfinite(float(value["lat"])) and math.isfinite(float(value["lon"]))
    except (KeyError, TypeError, ValueError):
        return False


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid evidence shape")
    return value


def _source_paths(geography_root: Path) -> dict[str, Path]:
    data = geography_root / "01-完整流域样本" / "data"
    return {
        "official_pdf": data / "ninghai_water_plan_ch3.pdf",
        "control": data / "funxi_control_section.json",
        "dem_trace": data / "funxi_mouth_trace.json",
    }


def _read_sources(geography_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    paths = _source_paths(Path(geography_root))
    sources: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        try:
            sources[name] = _file_record(path)
        except FileNotFoundError as error:
            raise ValueError("source_file_missing:" + name) from error
        if sources[name]["sha256"] != EXPECTED_SOURCE_SHA256[name]:
            raise ValueError("source_hash_mismatch:" + name)
    control = _load_json(paths["control"])
    trace = _load_json(paths["dem_trace"])
    return {"control": control, "trace": trace}, sources


def build_natural_outlet_certification(geography_root: str | Path,
                                       *, candidate: dict[str, Any] | None = None,
                                       optional_inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a conservative report from the frozen local evidence.

    ``candidate`` may provide independently acquired evidence, but it must
    explicitly carry source, coordinate uncertainty, continuity, and vertical
    datum fields before any gate can pass.
    """
    loaded, sources = _read_sources(Path(geography_root))
    control = loaded["control"]
    trace = loaded["trace"]
    outlet_reference = control.get("tidal_outlet", {})
    dem_mouth = trace.get("dem_derived_mouth", {})
    path = trace.get("path", [])
    candidate = dict(candidate or {})
    optional_inputs = dict(optional_inputs or {})
    reasons: list[str] = []

    named_supported = bool(control.get("source_of_official_value"))
    independent = candidate.get("independent_outlet")
    independent_ok = (_finite_coordinates(independent) and
                      isinstance(independent.get("source"), str) and
                      independent.get("source") not in {"control_section", "dem_trace", "tidal_reference"} and
                      math.isfinite(float(independent.get("uncertainty_m", math.nan))) and
                      float(independent.get("uncertainty_m")) >= 0.)
    if not independent_ok:
        reasons.append("missing_independent_outlet_coordinates")
    if independent is None or independent.get("source") in {"control_section", "dem_trace", "tidal_reference"}:
        reasons.append("outlet_coordinate_is_upstream_reference")

    continuity = candidate.get("continuous_connection", {})
    continuity_ok = bool(continuity.get("verified") is True and
                         continuity.get("from_river_to_coast") is True and
                         isinstance(continuity.get("source"), str) and
                         continuity.get("source") not in {"dem_trace", "engineering_boundary"})
    if not continuity_ok:
        reasons.append("missing_continuous_river_sea_connection")
    observations = []
    if dem_mouth:
        observations.append("dem_trace_is_candidate_only")
    rises = []
    if isinstance(path, list):
        for before, after in zip(path, path[1:]):
            try:
                rise = float(after["elev_m"]) - float(before["elev_m"])
            except (KeyError, TypeError, ValueError):
                reasons.append("invalid_evidence_shape")
                break
            if rise > 0:
                rises.append(rise)
    else:
        reasons.append("invalid_evidence_shape")
    if rises:
        observations.append("dem_trace_has_unresolved_height_rises")

    vertical = candidate.get("vertical_reference", {})
    vertical_ok = (isinstance(vertical.get("datum"), str) and bool(vertical.get("datum")) and
                   math.isfinite(float(vertical.get("uncertainty_m", math.nan))) and
                   float(vertical.get("uncertainty_m")) >= 0. and
                   isinstance(vertical.get("source"), str) and bool(vertical.get("source")))
    if not isinstance(vertical.get("datum"), str) or not vertical.get("datum"):
        reasons.append("missing_vertical_datum")
    if not (math.isfinite(float(vertical.get("uncertainty_m", math.nan))) and
            float(vertical.get("uncertainty_m", math.nan)) >= 0.):
        reasons.append("missing_vertical_uncertainty")

    # De-duplicate while preserving a stable diagnostic order.
    reasons = list(dict.fromkeys(reasons))
    gates = {
        "independent_outlet_coordinates": independent_ok,
        "continuous_river_sea_connection": continuity_ok,
        "vertical_datum_and_uncertainty": vertical_ok,
    }
    status = "verified" if all(gates.values()) else "pending"
    report = {
        "schema": SCHEMA,
        "status": status,
        "stages": {
            "named_relationship": "supported" if named_supported else "unconfirmed",
            "candidate": "present" if dem_mouth or candidate else "absent",
            "verified": status == "verified",
        },
        "gates": gates,
        "failure_reasons": reasons,
        "observations": observations,
        "natural_outlet_verified": status == "verified",
        "ocean_outlet_certified": status == "verified",
        "evidence": {
            "sources": sources,
            "named_relationship": {"supported": named_supported,
                                   "source": sources["official_pdf"]},
            "tidal_reference": {"value": outlet_reference, "classification": "candidate"},
            "dem_trace": {"value": dem_mouth, "classification": "candidate",
                          "path_points": len(path), "positive_height_edges": len(rises)},
            "independent_outlet": independent,
            "continuous_connection": continuity,
            "vertical_reference": vertical,
        },
        "optional_inputs": optional_inputs,
        "source_unchanged": True,
        "solver_called": False,
        "old_evidence_modified": False,
        "limitations": [
            "A named river-sea relationship does not locate a verified mouth.",
            "The local DEM trace is a candidate and contains unresolved height rises.",
            "No natural-outlet claim is allowed without independent coordinates, continuous connectivity, and a vertical uncertainty budget.",
        ],
    }
    report["identity_sha256"] = _digest(report)
    validate_natural_outlet_certification(report)
    return report


def validate_natural_outlet_certification(report: dict[str, Any]) -> None:
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("invalid certification schema")
    if report.get("status") not in {"pending", "verified"}:
        raise ValueError("invalid certification status")
    gates = report.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(REQUIRED_GATES) or not all(isinstance(v, bool) for v in gates.values()):
        raise ValueError("invalid certification gates")
    reasons = report.get("failure_reasons")
    if not isinstance(reasons, list) or len(set(reasons)) != len(reasons) or any(item not in FAILURE_REASONS for item in reasons):
        raise ValueError("invalid fixed failure reasons")
    if (not isinstance(report.get("observations"), list) or
            len(set(report["observations"])) != len(report["observations"]) or
            any(item not in {"dem_trace_is_candidate_only", "dem_trace_has_unresolved_height_rises"}
                for item in report["observations"])):
        raise ValueError("invalid evidence observations")
    expected_verified = all(gates.values())
    if report["status"] != ("verified" if expected_verified else "pending"):
        raise ValueError("status does not match gates")
    if report.get("natural_outlet_verified") is not expected_verified or report.get("ocean_outlet_certified") is not expected_verified:
        raise ValueError("natural_outlet_flag_mismatch")
    unsigned = dict(report)
    identity = unsigned.pop("identity_sha256", None)
    if not isinstance(identity, str) or identity != _digest(unsigned):
        raise ValueError("certification identity mismatch")


def save_natural_outlet_certification(report: dict[str, Any], path: str | Path) -> None:
    validate_natural_outlet_certification(report)
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_canonical(report))


def load_natural_outlet_certification(path: str | Path) -> dict[str, Any]:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_natural_outlet_certification(report)
    return report
