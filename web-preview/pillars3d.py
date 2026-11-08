"""Read-only pillar-field true-3D bundles for the local review UI.

This is the volume-form companion of ``special_surface``.  The height-field study of
``kind == "sandstone_pillar_field"`` cannot express a multi-sided polygonal prism section,
a vertical wall, an outward-bulging iron cap or a wall alcove, so the L1 module
``terrain_pipeline.special_terrain_pillars3d`` supersedes those field values with a real
closed MESH64 solid.  Nothing here advances physics, writes a routing graph or certifies a
channel: the artifact's own ``status`` is ``candidate`` and all six capability flags stay
false.

Pinning follows ``special_surface`` exactly: the report is pinned by its own SHA256 *and*
its identity, and both mesh archives are pinned by digest, so a metadata edit cannot
quietly re-point the viewer at different bytes.

Mesh arrays ship as one JSON descriptor plus separate little-endian binary bodies: the
vertex blob is the stored local-frame vertices, and the triangle blob is the stored
``triangles``.  Topology is therefore *reused*, never rebuilt, and the frontend hands both
straight to ``THREE.BufferAttribute``.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import file_sha256

BUNDLE_DIR = ROOT / ".scratch/special-terrain/l1-preview-20261020/pillars3d"
REPORT = BUNDLE_DIR / "report.json"
CARVED = BUNDLE_DIR / "carved.npz"
PLAIN = BUNDLE_DIR / "plain.npz"
MAX_BYTES = 268435456
LOCK = threading.RLock()
CACHED = None

# Pinned after the artifact was generated; every read re-verifies all four — a moved byte is
# refused rather than displayed.  Re-pinning is a deliberate source change.
REPORT_SHA256 = "e00b359f0490f20fcad7321bd59599e51e0ed2d2d186bb5bc4cbac4f08582269"
REPORT_IDENTITY = "a44932dd5ba1fe83e66d352f84615632c14b74ae0352e7e30bd923cc6e365477"
CARVED_SHA256 = "2efaa0004d86b16b68e5bbf9e79a2fd341b2f400a9e3891b52f512c01fa8d2b0"
PLAIN_SHA256 = "51f2737b37d2e06f243975255a1ca33c8fe96583d29ff360b392474a085f5dd9"

SCHEMA = "special-pillars3d-case-v1"
SOURCE_SCHEMA = "td-special-terrain-l1-pillars3d-report-v1"


def _npz(path, expected_sha256, keys):
    if file_sha256(path) != expected_sha256:
        raise ValueError("pillars3d archive digest changed: " + path.name)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("pillars3d archive outside allowed size")
    with np.load(path, allow_pickle=False) as handle:
        missing = sorted(set(keys) - set(handle.files))
        if missing:
            raise ValueError("pillars3d archive is missing " + ",".join(missing))
        return {name: handle[name] for name in keys}


def source_report():
    """The pinned L1 report, re-verified on every read."""
    if file_sha256(REPORT) != REPORT_SHA256:
        raise ValueError("pillars3d report changed")
    record = json.loads(REPORT.read_text(encoding="utf-8"))
    if record.get("schema") != SOURCE_SCHEMA:
        raise ValueError("pillars3d report schema mismatch")
    if record.get("status") != "candidate":
        raise ValueError("pillars3d report is not a candidate package")
    if record.get("identity_sha256") != REPORT_IDENTITY:
        raise ValueError("pillars3d report identity changed")
    for name in ("solids", "pillar_footprints", "pillar_pins", "boolean", "volume_account",
                 "supersedes", "witnesses"):
        if name not in record:
            raise ValueError("pillars3d report is missing " + name)
    return record


def frame():
    """The two stored solids plus the plan-view footprints, cached in memory."""
    global CACHED
    with LOCK:
        if CACHED is not None:
            return CACHED
        record = source_report()
        carved = _npz(CARVED, CARVED_SHA256,
                      ("vertices_local_xyz_m", "triangles"))
        plain = _npz(PLAIN, PLAIN_SHA256,
                     ("vertices_local_xyz_m", "triangles"))
        solid = record["solids"]["pillar_field_rock"]
        carved_vertices = np.asarray(carved["vertices_local_xyz_m"], dtype="<f4")
        if carved_vertices.shape[0] != len(solid["vertices_local_xyz_m"]):
            raise ValueError("pillars3d carved archive disagrees with the report")
        if int(np.asarray(carved["triangles"]).max()) >= carved_vertices.shape[0]:
            raise ValueError("pillars3d carved archive index out of range")
        flat = np.asarray(plain["vertices_local_xyz_m"], dtype="float64")
        flat_triangles = np.asarray(plain["triangles"], dtype=np.int64)
        if int(flat_triangles.max()) >= flat.shape[0]:
            raise ValueError("pillars3d plain archive index out of range")
        buffers = {
            "solid_vertices": np.ascontiguousarray(carved_vertices),
            "solid_triangles": np.ascontiguousarray(np.asarray(carved["triangles"], dtype="<u4")),
            "plain_vertices": np.ascontiguousarray(flat, dtype="<f4"),
            "plain_triangles": np.ascontiguousarray(flat_triangles, dtype="<u4"),
        }
        origin = [float(value) for value in record["local_origin_xyz_m"]]
        footprints = record["pillar_footprints"]
        heights = [float(item["height_m"]) for item in footprints]
        scales = [float(item["carve_scale"]) for item in footprints]
        parameters = record["parameters"]
        # The declared height band is the *requested* band, which is not the same thing as the
        # drawn heights: a cell whose polygon is small may fold before reaching its draw.  The
        # report carries whichever spelling the L1 module uses, so read all three and fall back
        # to the measured range rather than inventing a band.
        if isinstance(parameters.get("height_band_m"), (list, tuple)):
            band = [float(value) for value in parameters["height_band_m"]]
        elif isinstance(parameters.get("height_min_m"), (int, float)) \
                and isinstance(parameters.get("height_max_m"), (int, float)):
            band = [float(parameters["height_min_m"]), float(parameters["height_max_m"])]
        else:
            band = [min(heights), max(heights)]
        descriptor = dict(
            schema=SCHEMA, caseId="pillars3d", label="\u77f3\u67f1\u7fa4 \u00b7 \u771f\u4e09\u7ef4\u95ed\u5408\u5b9e\u4f53",
            identity=record["identity_sha256"], algorithm=record["algorithm"],
            report_schema=record["schema"], report_sha256=REPORT_SHA256,
            carved_sha256=CARVED_SHA256, plain_sha256=PLAIN_SHA256,
            status=record["status"], origin_xyz_m=origin,
            pillar_count=len(footprints), full_depth_pillars=int(sum(1 for value in scales if value >= 1.)),
            carve_scales=[round(value, 3) for value in scales],
            height_m=[min(heights), max(heights)],
            height_band_m=band,
            assembled_volume_m3=float(solid["signed_volume_m3"]),
            plateau_volume_m3=float(record["solids"]["plateau"]["signed_volume_m3"]),
            volume_account=dict(record["volume_account"]),
            vertices=int(buffers["solid_vertices"].shape[0]),
            triangles=int(buffers["solid_triangles"].shape[0]),
            plain_vertices=int(buffers["plain_vertices"].shape[0]),
            plain_triangles=int(buffers["plain_triangles"].shape[0]),
            components=int(record["boolean"]["census"]["assembled_components"]),
            every_section_simple=bool(record["witnesses"]["every_horizontal_section_is_simple"]["verdict"]),
            witnesses={name: bool(witness["verdict"]) for name, witness in record["witnesses"].items()},
            pillar_footprints=[
                {
                    "index": int(item["index"]), "role": item["role"],
                    "height_m": float(item["height_m"]), "carve_scale": float(item["carve_scale"]),
                    "signed_volume_m3": float(item["signed_volume_m3"]),
                    "centre_xz_m": [float(value) for value in item["centre_xz_m"]],
                    "ring_area_m2": float(item["ring_area_m2"]),
                    "ring_xz_m": [[float(value) for value in point] for point in item["base_ring_xz_m"]],
                }
                for item in footprints
            ],
            plateau=dict(
                ring_xz_m=[[float(value) for value in point] for point in record["plateau_ring_xz_m"]],
                bottom_y_m=float(record["plateau_bottom_y_m"]),
                top_y_m=float(record["plateau_top_y_m"])),
            level_schedule=dict(record["level_schedule"]),
            supersedes=dict(record["supersedes"]),
            geology_note=record.get("geology_note", ""),
            semantics="\u771f\u4e09\u7ef4\u95ed\u5408\u5b9e\u4f53\uff1b\u5408\u6210\u5206\u6790\u51e0\u4f55\uff0c\u975e\u5730\u7406\u53c2\u7167\u3001\u975e\u6c34\u529b\u6210\u679c\u3001\u975e\u9a8c\u8bc1\u7ed3\u679c",
            hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
            self_intersection_verified=False,
            arrays={name: dict(dtype=str(value.dtype), shape=list(value.shape),
                               bytes=int(value.nbytes), url=f"/api/pillars3d/array/{name}")
                    for name, value in buffers.items()},
        )
        CACHED = descriptor, buffers
        return CACHED


def catalog():
    """Declared label and counts only; carries no measured quantity beyond the pinned report."""
    with LOCK:
        descriptor, _ = frame()
        return dict(
            schema="special-pillars3d-catalog-v1", algorithm=descriptor["algorithm"],
            status=descriptor["status"], report_sha256=REPORT_SHA256,
            identity=REPORT_IDENTITY, cases=[dict(caseId=descriptor["caseId"],
                                                 label=descriptor["label"],
                                                 pillar_count=descriptor["pillar_count"],
                                                 height_m=descriptor["height_m"])],
            supersedes=descriptor["supersedes"],
            hydraulic_ready=False, natural_outlet_verified=False,
            publishable=False, self_intersection_verified=False)


def descriptor():
    with LOCK:
        return frame()[0]


def binary(name):
    with LOCK:
        _, buffers = frame()
        if name not in buffers:
            raise ValueError("pillars3d array outside allowlist")
        return buffers[name].tobytes()


def digest(value):
    return hashlib.sha256(value).hexdigest()
