"""Explicit native identity binding and byte-bound validated solid views."""

from fractions import Fraction
import json
import math
import zipfile

import numpy as np

from tools.hybrid_cave_saved_audit import Solid
from tools.hybrid_exact_solid_saved_audit import SOLID_POLICY, SOLID_POLICY_SHA256
from tools.td_shared_channel_fine_saved_audit import (
    MAX_RSS, NativeSource, check_identity, check_memory, checked_path, compare, digest, require)


def load_native_bound(original_pin, expected_identity, selected_leaves, protection):
    require(isinstance(expected_identity, str) and len(expected_identity) == 64
            and all(character in "0123456789abcdef" for character in expected_identity),
            "invalid explicit sections hierarchy identity")
    if "identity_sha256" in original_pin:
        require(original_pin["identity_sha256"] == expected_identity, "optional hierarchy pin identity differs from sections")
    path = checked_path(original_pin)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        require(len(members) <= 128 and len({member.filename for member in members}) == len(members)
                and sum(member.file_size for member in members) <= MAX_RSS // 2,
                "native archive expansion exceeds original budget")
    names = ("height_m", "valid_mask", "protected_mask", "open_boundary_mask",
             "cell_owner", "contribution_owner", "node_unknown_contact")
    with np.load(path, allow_pickle=False) as bundle:
        manifest = json.loads(bytes(bundle["manifest"]))
        require(manifest.get("identity_sha256") == expected_identity, "native manifest/sections hierarchy identity differs")
        arrays = {name: bundle[name].copy() for name in names}
    check_memory()
    native = NativeSource(arrays, manifest["metadata"], set(selected_leaves), protection)
    return native, {"verified": True, "original_pin": dict(original_pin),
        "identity_source": "pinned_original_06_sections.hierarchy_identity_sha256",
        "expected_hierarchy_identity_sha256": expected_identity,
        "manifest_hierarchy_identity_sha256": manifest["identity_sha256"],
        "original_inputs_or_pin_modified": False, "archive_and_array_budgets_unchanged": True}


class ValidatedSolid(Solid):
    def __init__(self, mesh, evidence, label):
        check_identity(mesh)
        require(mesh["schema"] == "td-hybrid-local-solid-mesh-v1", label + ": unknown inherited solid schema")
        self.label = label
        self.vertices = np.asarray(mesh["vertices_local_xyz_m"], dtype=np.float64)
        raw_faces = np.asarray(mesh["triangles"])
        require(self.vertices.ndim == 2 and self.vertices.shape[1] == 3 and np.isfinite(self.vertices).all()
                and raw_faces.ndim == 2 and raw_faces.shape[1] == 3 and np.issubdtype(raw_faces.dtype, np.integer),
                label + ": malformed inherited arrays")
        self.triangles = raw_faces.astype(np.int64)
        require(len(self.vertices) == evidence["vertex_count"] and len(self.triangles) == evidence["triangle_count"]
                == evidence["retained_triangle_count"] and len(self.triangles) >= 4
                and self.triangles.min() >= 0 and self.triangles.max() < len(self.vertices),
                label + ": inherited mesh census differs")
        require(evidence["policy"] == SOLID_POLICY and evidence["policy_identity_sha256"] == SOLID_POLICY_SHA256
                and evidence["all_original_faces_retained"] is True and evidence["deleted_triangle_count"] == 0
                and evidence["exact_zero_triangle_count"] == 0
                and type(evidence["closed_oriented_edge_count"]) is int
                and evidence["closed_oriented_edge_count"] > 0
                and 2 * evidence["closed_oriented_edge_count"] == 3 * len(self.triangles)
                and type(evidence["surface_component_count"]) is int and evidence["surface_component_count"] > 0,
                label + ": incomplete closed/oriented/retained validation evidence")
        require(evidence["original_vertex_triangle_identity_sha256"] == digest({
            "vertices": self.vertices.tolist(), "triangles": self.triangles.tolist()}),
            label + ": original vertex/triangle digest differs")
        numerator, denominator = evidence["exact_signed_volume_m3"]
        require(isinstance(numerator, str) and isinstance(denominator, str)
                and int(denominator) > 0, label + ": invalid exact signed volume evidence")
        volume = Fraction(int(numerator), int(denominator))
        require(volume > 0 and math.isfinite(float(volume))
                and float(volume) == evidence["signed_volume_m3_approx"], label + ": inherited exact volume differs")
        compare(mesh["signed_volume_m3"], float(volume), label + ": original saved signed volume", atol=1e-7, rtol=1e-9)
        require(evidence["minimum_positive_area_m2_approx"] > 0
                and math.isfinite(evidence["sum_original_triangle_area_m2_approx"])
                and evidence["sum_original_triangle_area_m2_approx"] > 0,
                label + ": incomplete original positive-area evidence")
        self.signed_volume = float(volume)
        self.exact_signed_volume = volume
        self.edge_count = evidence["closed_oriented_edge_count"]
        self.validation_evidence = evidence
        self.points = self.vertices[self.triangles]
        self.normals = np.cross(self.points[:, 1] - self.points[:, 0], self.points[:, 2] - self.points[:, 0])
        check_memory()
