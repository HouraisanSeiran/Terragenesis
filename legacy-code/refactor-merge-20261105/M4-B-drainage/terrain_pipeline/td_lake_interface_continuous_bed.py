"""Bounded lake to river continuous-bed candidate assembly.

This layer only joins accepted lake-anchor patches to shared channel ports.  A
missing or rejected anchor remains an explicit pending interface; no straight
line, lake-centre shortcut, or source-bed mutation is invented.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


SCHEMA = "td-lake-interface-continuous-bed-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def build_lake_interface_continuous_bed(geometry, patches):
    if geometry.get("schema") != "td-watershed-geometry-preparation-v1":
        raise ValueError("saved watershed geometry is required")
    if patches.get("schema") not in {
            "td-watershed-interface-patch-preparation-v2",
            "td-watershed-interface-patches-v1"}:
        raise ValueError("saved interface patches are required")
    lake = [patch for patch in patches.get("patches", [])
            if patch.get("kind") == "lake_anchor_transition"]
    accepted = [patch for patch in lake if patch.get("status") == "candidate"]
    rejected = [
        {"patch_id": patch.get("patch_id"),
         "rejection_reasons": list(patch.get("rejection_reasons", []))}
        for patch in lake if patch.get("status") != "candidate"
    ]
    result = {
        "schema": SCHEMA,
        "algorithm": "shared-port-lake-interface-continuous-bed-candidate-v1",
        "source_artifacts": {
            "geometry_identity_sha256": geometry.get("identity_sha256"),
            "patches_identity_sha256": patches.get("identity_sha256"),
        },
        "interfaces": [{
            "patch_id": patch["patch_id"],
            "vertices_xyz_m": patch["vertices_xyz_m"],
            "triangles": patch["triangles"],
            "boundary_edges": patch["boundary_edges"],
            "shared_bed_m": patch["shared_bed_m"],
            "required_cut_m": patch["required_cut_m"],
            "status": "candidate",
        } for patch in accepted],
        "rejected_interfaces": rejected,
        "summary": {
            "requested": len(lake), "accepted": len(accepted),
            "rejected": len(rejected), "triangle_count": sum(
                len(patch["triangles"]) for patch in accepted),
        },
        "status": "candidate" if accepted else "pending",
        "continuous_bed_ready": bool(accepted),
        "bed_changed": False,
        "hydraulic_solved": False,
        "natural_outlet_certified": False,
        "publish_ready": False,
        "source_bed_unchanged": True,
        "solver_calls": 0,
        "limitation": "accepted local interfaces are candidates with open ports; rejected lake anchors remain pending",
    }
    result["identity_sha256"] = _digest(result)
    validate_lake_interface_continuous_bed(result)
    return result


def validate_lake_interface_continuous_bed(result):
    if result.get("schema") != SCHEMA:
        raise ValueError("lake interface schema mismatch")
    if result.get("status") not in {"pending", "candidate"}:
        raise ValueError("invalid lake interface status")
    if result.get("continuous_bed_ready") != bool(result["interfaces"]):
        raise ValueError("continuous-bed status mismatch")
    if any(result.get(name) is not False for name in (
            "bed_changed", "hydraulic_solved", "natural_outlet_certified", "publish_ready")):
        raise ValueError("lake interface certification flags must remain false")
    if result.get("source_bed_unchanged") is not True or result.get("solver_calls") != 0:
        raise ValueError("lake interface source/solver contract mismatch")
    expected = {"requested": len(result["interfaces"]) + len(result["rejected_interfaces"]),
                "accepted": len(result["interfaces"]),
                "rejected": len(result["rejected_interfaces"]),
                "triangle_count": sum(len(item["triangles"]) for item in result["interfaces"])}
    if result.get("summary") != expected:
        raise ValueError("lake interface summary mismatch")
    identity = result.get("identity_sha256")
    unsigned = dict(result)
    unsigned.pop("identity_sha256", None)
    if identity != _digest(unsigned):
        raise ValueError("lake interface identity mismatch")
    return True


def save_lake_interface_continuous_bed(result, path):
    validate_lake_interface_continuous_bed(result)
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_lake_interface_continuous_bed(path):
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_lake_interface_continuous_bed(result)
    return result
