"""Independent exact-zero saved binary64 solid validation; no mesh repairs."""

from collections import defaultdict
from fractions import Fraction
import math

import numpy as np

from tools.hybrid_cave_saved_audit import MAX_FACES, MAX_VERTICES, Solid
from tools.td_shared_channel_fine_saved_audit import check_memory, digest, require

SOLID_POLICY = {
    "version": "saved_binary64_exact_zero_solid-v1",
    "degeneracy": "exact_rational_cross_zero_of_original_saved_binary64_vertices",
    "mesh": "all_original_vertex_ids_and_oriented_triangles_retained_no_delete_no_snap",
    "topology": "closed_two_opposite_uses_per_original_edge_duplicate_faces_and_unused_vertices_refused",
    "volume": "exact_rational_signed_volume_all_original_triangles_positive_total",
    "geometry_gates": "original_boolean_material_and_whole_port_thresholds_unchanged"}
SOLID_POLICY_SHA256 = digest(SOLID_POLICY)


def rational_cross(first, second):
    return [first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0]]


class ExactSolid(Solid):
    def __post_init__(self):
        self.vertices = np.asarray(self.vertices, dtype=np.float64)
        faces = np.asarray(self.triangles)
        require(self.vertices.ndim == 2 and self.vertices.shape[1] == 3
                and 4 <= len(self.vertices) <= MAX_VERTICES and np.isfinite(self.vertices).all(),
                self.label + ": invalid saved vertices")
        require(faces.ndim == 2 and faces.shape[1] == 3 and np.issubdtype(faces.dtype, np.integer)
                and 4 <= len(faces) <= MAX_FACES and faces.min() >= 0 and faces.max() < len(self.vertices),
                self.label + ": invalid saved triangle references")
        self.triangles = faces.astype(np.int64)
        require(len(set(map(tuple, np.sort(self.triangles, axis=1)))) == len(self.triangles),
                self.label + ": duplicate saved triangles")
        require(len(np.unique(self.triangles)) == len(self.vertices), self.label + ": unreferenced saved vertices")
        self.points = self.vertices[self.triangles]
        self.normals = np.cross(self.points[:, 1] - self.points[:, 0], self.points[:, 2] - self.points[:, 0])
        exact_vertices = [[Fraction.from_float(float(value)) for value in point] for point in self.vertices]
        anchor = exact_vertices[0]
        volume = Fraction(0)
        minimum_squared, minimum_id = None, None
        small_area_ids, old_guard_ids = [], []
        float_zero_count = 0
        areas = []
        threshold = (2 * Fraction.from_float(1e-14)) ** 2
        edges = defaultdict(list)
        for ordinal, face in enumerate(self.triangles.tolist()):
            own = [exact_vertices[index] for index in face]
            first = [end - start for start, end in zip(own[0], own[1])]
            second = [end - start for start, end in zip(own[0], own[2])]
            normal = rational_cross(first, second)
            squared = sum(value * value for value in normal)
            require(squared > 0, self.label + ": exact-zero triangle " + str(ordinal))
            if minimum_squared is None or squared < minimum_squared:
                minimum_squared, minimum_id = squared, ordinal
            if squared <= threshold:
                small_area_ids.append(ordinal)
            area = math.hypot(*(float(value) for value in normal)) / 2
            areas.append(area)
            floating = self.normals[ordinal]
            float_zero_count += int(bool(np.all(floating == 0)))
            if np.linalg.norm(floating) <= 1e-14:
                old_guard_ids.append(ordinal)
            local = [[value - base for value, base in zip(point, anchor)] for point in own]
            normal_local = rational_cross(local[1], local[2])
            volume += sum(value * other for value, other in zip(local[0], normal_local)) / 6
            for first_id, second_id in zip(face, face[1:] + face[:1]):
                require(first_id != second_id, self.label + ": repeated triangle index")
                edges[tuple(sorted((first_id, second_id)))].append((ordinal, first_id, second_id))
        require(volume > 0 and math.isfinite(float(volume)), self.label + ": nonpositive exact oriented volume")
        adjacency = defaultdict(set)
        for uses in edges.values():
            require(len(uses) == 2 and uses[0][1:] == uses[1][1:][::-1],
                    self.label + ": boundary/nonmanifold/inconsistent edge orientation")
            adjacency[uses[0][0]].add(uses[1][0])
            adjacency[uses[1][0]].add(uses[0][0])
        remaining, components = set(range(len(self.triangles))), []
        while remaining:
            frontier, component = [remaining.pop()], []
            while frontier:
                current = frontier.pop()
                component.append(current)
                for neighbor in adjacency[current]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        frontier.append(neighbor)
            components.append(component)
        self.components = components
        self.edge_count = len(edges)
        self.signed_volume = float(volume)
        self.exact_signed_volume = volume
        self.validation_evidence = {
            "policy": SOLID_POLICY, "policy_identity_sha256": SOLID_POLICY_SHA256,
            "vertex_count": len(self.vertices), "triangle_count": len(self.triangles),
            "retained_triangle_count": len(self.triangles), "deleted_triangle_count": 0,
            "exact_zero_triangle_count": 0, "float_cross_zero_triangle_count": float_zero_count,
            "triangle_area_le_1e_minus14_m2_ids": small_area_ids,
            "old_cross_norm_guard_le_1e_minus14_ids": old_guard_ids,
            "minimum_positive_triangle_index": minimum_id,
            "minimum_positive_area_m2_approx": min(areas),
            "minimum_exact_cross_norm_squared": [str(minimum_squared.numerator), str(minimum_squared.denominator)],
            "sum_original_triangle_area_m2_approx": math.fsum(areas),
            "exact_signed_volume_m3": [str(volume.numerator), str(volume.denominator)],
            "signed_volume_m3_approx": self.signed_volume,
            "original_vertex_triangle_identity_sha256": digest({"vertices": self.vertices.tolist(), "triangles": self.triangles.tolist()}),
            "closed_oriented_edge_count": self.edge_count, "surface_component_count": len(components),
            "all_original_faces_retained": True, "area_and_volume_reports_are_not_port_acceptance": True}
        check_memory()
