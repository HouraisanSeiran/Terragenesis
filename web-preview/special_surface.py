"""Read-only special-terrain surface bundles for the local review UI.

A chart in this package is a *synthetic analytic* landform study, not a georeferenced
landscape: the four bundles are pinned by a manifest that carries each archive's digest
and identity, and the reader refuses to touch a file whose digest or identity has moved.
Nothing here advances physics, writes a routing graph or certifies a channel -- the four
capability flags stay false, and the display is an illustration of stored arrays.

The manifest is pinned by its own SHA256 as well, so a *metadata* edit to a bundle entry
cannot quietly re-point a case at a different archive: adding a form means re-pinning the
manifest constant, which is a deliberate source change rather than a silent one.  This is
the same shape as ``saved_surface.ACCEPTANCE_SHA``, one level down.

Mesh arrays are shipped as one JSON descriptor plus separate binary bodies, following
``saved_surface``: the vertex blob is the stored ``vertices_xyz_m`` minus its own AABB
minimum, and the triangle index blob is the stored ``triangles``.  Topology is therefore
*reused*, never rebuilt, and the frontend can hand both straight to ``THREE.BufferAttribute``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.special_terrain import load_special_form_surface

MANIFEST = ROOT / ".scratch/special-terrain/surface-20261020/manifest-report.json"
MANIFEST_SHA = "d1f12249cbde88004d17059c81192ea6978693307766e69eb1ffe9db237d5bb9"
BUNDLE_DIR = ROOT / ".scratch/special-terrain/surface-20261020"
SCHEMA = "metric-special-terrain-surface-v2"
MAX_BYTES = 268435456
KINDS = ("inselberg", "karst_tower_field", "sandstone_pillar_field", "volcanic_plug")
LOCK = threading.RLock()
CONTEXTS = {}
CACHED = None


def manifest():
    """The pinned bundle index, re-verified on every read."""
    if file_sha256(MANIFEST) != MANIFEST_SHA:
        raise ValueError("special-terrain manifest changed")
    record = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if record.get("schema") != SCHEMA:
        raise ValueError("special-terrain manifest schema mismatch")
    if record.get("status") != "candidate":
        raise ValueError("special-terrain manifest is not a candidate package")
    forms = record.get("forms")
    if not isinstance(forms, dict) or set(forms) != set(KINDS):
        raise ValueError("special-terrain manifest form set changed")
    return record


def context(kind):
    """Resolve one form's archive and provenance from the pinned manifest."""
    if kind not in KINDS:
        raise ValueError("unknown special-terrain form")
    with LOCK:
        if kind in CONTEXTS:
            return CONTEXTS[kind]
        entry = manifest()["forms"][kind]
        path = (BUNDLE_DIR / entry["file"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("special-terrain bundle outside allowed scope")
        if file_sha256(path) != entry["sha256"]:
            raise ValueError("special-terrain bundle digest changed")
        CONTEXTS[kind] = entry
        return entry


def catalog():
    """Declared label/grid for every form; carries no measured quantity."""
    with LOCK:
        record = manifest()
        forms = {}
        for kind in KINDS:
            entry = context(kind)
            forms[kind] = dict(file=entry["file"], label=kind,
                               spacing_m=entry["spacing_m"],
                               chart_shape=[entry["chart_rows"], entry["chart_cols"]],
                               relief_reference_m=entry["relief_reference_m"],
                               roughened_relief_reference_m=entry["roughened_relief_reference_m"],
                               target_count=entry["target_count"],
                               bundle_sha256=entry["sha256"], identity_sha256=entry["identity_sha256"],
                               relaxation_converged=entry["ledger"]["relaxation_converged"])
        return dict(schema="special-surface-catalog-v1", algorithm=record["algorithm"],
                    manifest_sha256=MANIFEST_SHA, status=record["status"], forms=forms,
                    hydraulic_ready=False, natural_outlet_verified=False,
                    publishable=False, self_intersection_verified=False)


def frame(kind):
    """One stored surface as descriptor + binary buffers, cached in memory."""
    global CACHED
    entry = context(kind)
    with LOCK:
        if CACHED is not None and CACHED[0] == kind:
            return CACHED[1]
        path = BUNDLE_DIR / entry["file"]
        bundle = load_special_form_surface(path, expected_sha256=entry["sha256"],
                                           expected_identity=entry["identity_sha256"])
        arrays, metadata = bundle["arrays"], bundle["metadata"]
        vertices = arrays["vertices_xyz_m"]
        origin = np.array([vertices[:, 0].min(), vertices[:, 1].min(), vertices[:, 2].min()])
        rows, cols = arrays["surface_xyz_m"].shape[:2]
        buffers = {
            "surface_vertices": np.ascontiguousarray(vertices - origin, dtype="<f4"),
            "surface_triangles": np.ascontiguousarray(arrays["triangles"], dtype="<u4"),
            "reference_vertices": np.ascontiguousarray(arrays["reference_xyz_m"].reshape(-1, 3) - origin,
                                                       dtype="<f4"),
            "change": np.ascontiguousarray(arrays["erosion_change_m"], dtype="<f4"),
            "protected": np.ascontiguousarray(arrays["protected_mask"].astype(np.uint8).ravel(), dtype="<u1"),
        }
        if metadata["parent_identity_sha256"] != entry["parent_identity_sha256"]:
            raise ValueError("special-terrain parent identity changed")
        relief = np.asarray(arrays["surface_xyz_m"], dtype="float64")[:, :, 1]
        descriptor = dict(schema="special-surface-case-v1", kind=kind, label=kind,
                          identity=bundle["identity_sha256"],
                          parent_identity=metadata["parent_identity_sha256"],
                          algorithm=metadata["algorithm"],
                          manifest_sha256=MANIFEST_SHA, bundle_sha256=entry["sha256"],
                          origin_xyz_m=origin.tolist(), spacing_m=float(entry["spacing_m"]),
                          chart_shape=[int(rows), int(cols)],
                          relief_m=[float(relief.min()), float(relief.max())],
                          relief_reference_m=entry["relief_reference_m"],
                          change_m=[float(arrays["erosion_change_m"].min()),
                                    float(arrays["erosion_change_m"].max())],
                          protected_cells=int(np.count_nonzero(arrays["protected_mask"])),
                          relaxation_converged=bool(entry["ledger"]["relaxation_converged"]),
                          net_change_m3=entry["net_change_m3_recomputed"],
                          status=record_status(entry), target_count=entry["target_count"],
                          semantics="synthetic analytic landform study; not a georeferenced "
                                    "landscape and not a surface-hydraulics result",
                          full_resolution_geometry=True, solver_advanced=False,
                          hydraulic_ready=False, natural_outlet_verified=False,
                          publishable=False, self_intersection_verified=False,
                          arrays={name: dict(dtype=str(value.dtype), shape=list(value.shape),
                                             bytes=int(value.nbytes),
                                             url=f"/api/special/array/{kind}/{name}")
                                  for name, value in buffers.items()})
        CACHED = kind, (descriptor, buffers)
        return CACHED[1]


def record_status(entry):
    """Never report a convergence the bundle's own numbers deny."""
    ledger = entry["ledger"]
    converged = (ledger["relaxation_maximum_excess_m"] <= ledger["relaxation_tolerance_m"])
    if converged != ledger["relaxation_converged"]:
        raise ValueError("special-terrain convergence flag disagrees with its operands")
    return "bounded_relaxation_converged" if converged else "bounded_relaxation_finite_stop"


def descriptor(kind):
    with LOCK:
        return frame(kind)[0]


def binary(kind, name):
    with LOCK:
        _, buffers = frame(kind)
        if name not in buffers:
            raise ValueError("special-terrain array outside allowlist")
        return buffers[name].tobytes()


def digest(value):
    return hashlib.sha256(value).hexdigest()
