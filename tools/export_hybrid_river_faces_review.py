"""Export source-bound accepted and refused face slices without running a solver."""

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
    require(faces["schema"] == "td-hybrid-river-faces-v1"
            and audit["schema"] == "td-hybrid-river-faces-independent-audit-v1"
            and audit["faces_pin"]["sha256"] == faces_pin["sha256"]
            and Path(audit["faces_pin"]["path"]).resolve() == Path(faces_pin["path"]).resolve()
            and audit["status"] in ("passed", "refused")
            and len(faces["faces"]) == faces["face_count"] == 18,
            "wrong saved face/audit linkage or scope")
    accepted = {item["face_id"] for item in audit["reports"]}
    require(len(accepted) == audit["verified_face_count"]
            and all(item["status"] == "candidate" for item in faces["faces"] if item["face_id"] in accepted),
            "face acceptance census differs")
    output = Path(output).resolve()
    require(not output.exists() and output.parent == (ROOT / "verification/natural-river-network").resolve(),
            "new local face review package required")
    colors = {"rock_after": "#c1c4c8", "removed": "#cc8850", "cutter": "#1b8d91"}
    figure, axes = plt.subplots(3, 6, figsize=(22, 11), constrained_layout=True)
    summary = []
    for face, axis in zip(faces["faces"], axes.flat):
        slices = face.get("solid_slices", {})
        cutter = slices.get("cutter", {}).get("polygons_uv_m", [])
        require(cutter, "saved refused face lacks diagnostic slice evidence")
        bounds = np.concatenate([np.asarray(loop, float) for loop in cutter])
        require(np.isfinite(bounds).all() and bounds.shape[1] == 2, "invalid slice display coordinates")
        for role in ("rock_after", "removed", "cutter"):
            record = slices[role]
            for polygon, holes in zip(record["polygons_uv_m"], record["holes_uv_m"]):
                axis.add_patch(PolygonPatch(polygon, closed=True, facecolor=colors[role] if role != "cutter" else "none",
                                            edgecolor=colors[role], linewidth=1., alpha=.7))
                if role != "cutter":
                    for hole in holes:
                        axis.add_patch(PolygonPatch(hole, closed=True, facecolor="white", edgecolor=colors[role], linewidth=.5))
        for piece in face.get("aperture", {}).get("boundary_pieces", []):
            if piece["category"] == "actual_rock_wet_wall":
                points = np.asarray(piece["points_uv_m"])
                axis.plot(points[:, 0], points[:, 1], color="#24272a", linewidth=2.)
        passed = face["face_id"] in accepted
        axis.set_title(face["face_id"] + (" | geometry passed" if passed else " | REFUSED"),
                       fontsize=10, color="#146c55" if passed else "#b42428")
        axis.set_xlim(bounds[:, 0].min() - .5, bounds[:, 0].max() + .5)
        axis.set_ylim(bounds[:, 1].min() - .5, bounds[:, 1].max() + .5)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(alpha=.15)
        axis.set_xlabel("transverse u (m)", fontsize=8)
        axis.set_ylabel("common local Y (m)", fontsize=8)
        reasons = face["rejection_reasons"] if not passed else []
        summary.append({"face_id": face["face_id"], "link_id": face["link_id"], "geometry_passed": passed,
                        "rejection_reasons": reasons, "plane": face["plane"],
                        "kind": face.get("aperture", {}).get("kind"), "hydraulic_certified": False})
        check_memory()
    figure.suptitle("Saved actual link slices: grey remaining rock, orange removed rock, teal cutter, black verified wet wall\n"
                   "Local slice geometry only; refused faces retained; no water, discharge, or whole-link sill certification", fontsize=12)
    with tempfile.TemporaryDirectory(prefix=".face-review-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        figure.savefig(staging / "faces.png", dpi=130)
        plt.close(figure)
        require((staging / "faces.png").stat().st_size <= MAX_BYTES, "face image exceeds file budget")
        report = {"schema": "td-hybrid-river-faces-review-v1", "status": "saved_geometry_review",
                  "inputs": {"faces": faces_pin, "audit": audit_pin},
                  "audit_status": audit["status"], "verified_face_count": len(accepted), "faces": summary,
                  "image": {"path": str(output / "faces.png"), "sha256": file_sha256(staging / "faces.png")},
                  "hydraulic_certified": False, "integration_performed": False, "water_mesh": None,
                  "whole_link_sill_verified": False, "frontend_integrated": False,
                  "code_sha256": {"tools/export_hybrid_river_faces_review.py": file_sha256(Path(__file__))},
                  "resource": {"wall_seconds": time.monotonic() - started,
                               "peak_rss_bytes": check_memory(), "solver_calls": 0}}
        report["identity_sha256"] = digest(report)
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        require(len(payload) <= MAX_BYTES, "face review exceeds file budget")
        (staging / "review.json").write_bytes(payload)
        staging.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faces", required=True, type=Path)
    parser.add_argument("--faces-sha256", required=True)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = export({"path": str(args.faces.resolve()), "sha256": args.faces_sha256},
                    {"path": str(args.audit.resolve()), "sha256": args.audit_sha256}, args.output)
    print(json.dumps({"status": report["status"], "audit_status": report["audit_status"],
                      "verified_face_count": report["verified_face_count"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
