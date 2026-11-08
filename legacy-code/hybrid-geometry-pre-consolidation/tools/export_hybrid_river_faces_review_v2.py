"""Read-only polygon and source-role review for exact coupled link faces."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PolygonPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_memory, digest, file_sha256, read, read_audit, require)


def export(faces_pin, audit_pin, output):
    started = time.monotonic()
    faces, audit = read(faces_pin), read_audit(audit_pin)
    require(faces["schema"] == "td-hybrid-river-faces-v2"
            and audit["schema"] == "td-hybrid-river-faces-independent-audit-v2"
            and audit["faces_pin"]["sha256"] == faces_pin["sha256"]
            and Path(audit["faces_pin"]["path"]).resolve() == Path(faces_pin["path"]).resolve()
            and audit["inputs"] == faces["inputs"]
            and audit["composition_identity_sha256"] == faces["composition_identity_sha256"]
            and faces["face_count"] == len(faces["faces"]) == 18,
            "face/audit/source linkage differs")
    for parent in (faces, audit):
        for group in ("code_sha256", "readonly_dependency_code_sha256"):
            for name, sha in parent.get(group, {}).items():
                require(file_sha256(ROOT / name) == sha, "saved face or audit code changed")
    accepted = {item["face_id"] for item in audit["reports"]}
    require(len(accepted) == audit["verified_face_count"]
            and audit["status"] == ("passed" if not audit["errors"] else "refused"), "audit census differs")
    output = Path(output).resolve()
    require(not output.exists() and output.parent == (ROOT / "verification/natural-river-network").resolve(),
            "new face review package required")
    figure, axes = plt.subplots(3, 6, figsize=(22, 11), constrained_layout=True)
    summary = []
    for face, axis in zip(faces["faces"], axes.flat):
        slices = face["solid_slices"]
        require(slices["cutter"]["polygons_uv_m"], "missing actual polygon display evidence")
        bounds = np.concatenate([np.asarray(polygon, float) for polygon in slices["cutter"]["polygons_uv_m"]])
        require(np.isfinite(bounds).all() and bounds.shape[1] == 2, "invalid polygon display coordinates")
        for role, color in (("rock_after", "#bfc3c7"), ("removed", "#cc8850"), ("cutter", "#1b8d91")):
            for polygon, holes in zip(slices[role]["polygons_uv_m"], slices[role]["holes_uv_m"]):
                axis.add_patch(PolygonPatch(polygon, closed=True, facecolor="none" if role == "cutter" else color,
                                            edgecolor=color, linewidth=1., alpha=.65))
                if role != "cutter":
                    for hole in holes:
                        axis.add_patch(PolygonPatch(hole, closed=True, facecolor="white", edgecolor=color, linewidth=.5))
        for piece in face.get("aperture", {}).get("boundary_pieces", []):
            points = np.asarray(piece["points_uv_m"])
            wall = piece["category"] == "actual_rock_wet_wall"
            color = "#24272a" if wall else "#347cb4" if piece["source_role"] == "lateral" else "#1b8d91"
            axis.plot(points[:, 0], points[:, 1], color=color, linewidth=2. if wall else 1.,
                      linestyle="-" if wall else "--")
        passed = face["face_id"] in accepted
        require(not passed or (face["status"] == "candidate" and not face["rejection_reasons"]),
                "refused geometry promoted by review")
        axis.set_title(face["face_id"] + (" | slice passed" if passed else " | REFUSED"),
                       fontsize=10, color="#146c55" if passed else "#b42428")
        axis.set_xlim(bounds[:, 0].min() - .5, bounds[:, 0].max() + .5)
        axis.set_ylim(bounds[:, 1].min() - .5, bounds[:, 1].max() + .5)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(alpha=.15)
        axis.set_xlabel("transverse u (m)", fontsize=8)
        axis.set_ylabel("common local Y (m)", fontsize=8)
        summary.append({"face_id": face["face_id"], "link_id": face["link_id"], "local_slice_verified": passed,
                        "kind": face.get("aperture", {}).get("kind"), "rejection_reasons": face["rejection_reasons"],
                        "hydraulic_certified": False, "no_whole_link_control_sill_claim": True})
        check_memory()
    figure.suptitle("Exact saved mesh-plane traces; remaining rock grey, removed material orange, actual rock walls black\n"
                   "Dashed blue: engineering lateral boundaries; teal: cutter/free top; no water or discharge",
                   fontsize=12)
    with tempfile.TemporaryDirectory(prefix=".exact-face-review-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        figure.savefig(staging / "faces.png", dpi=130)
        plt.close(figure)
        require((staging / "faces.png").stat().st_size <= MAX_BYTES, "review image exceeds file budget")
        report = {"schema": "td-hybrid-river-faces-review-v2", "status": "saved_geometry_review",
                  "inputs": {"faces": faces_pin, "audit": audit_pin}, "audit_status": audit["status"],
                  "composition_identity_sha256": faces["composition_identity_sha256"], "faces": summary,
                  "verified_face_count": len(accepted), "water_mesh": None,
                  "hydraulic_certified": False, "integration_performed": False,
                  "whole_link_sill_verified": False, "frontend_integrated": False,
                  "image": {"path": str(output / "faces.png"), "sha256": file_sha256(staging / "faces.png")},
                  "code_sha256": {"tools/export_hybrid_river_faces_review_v2.py": file_sha256(Path(__file__))},
                  "resource": {"wall_seconds": time.monotonic() - started,
                               "peak_rss_bytes": check_memory(), "solver_calls": 0}}
        report["identity_sha256"] = digest(report)
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        require(len(payload) <= MAX_BYTES, "review metadata exceeds file budget")
        (staging / "review.json").write_bytes(payload)
        staging.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faces", type=Path, required=True)
    parser.add_argument("--faces-sha256", required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = export({"path": str(args.faces.resolve()), "sha256": args.faces_sha256},
                    {"path": str(args.audit.resolve()), "sha256": args.audit_sha256}, args.output)
    print(json.dumps({"status": report["status"], "verified_face_count": report["verified_face_count"],
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
