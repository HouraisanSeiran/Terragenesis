"""Two tiny tests for actual solid openings and forged saved evidence."""

import unittest
from io import BytesIO
from types import SimpleNamespace

import numpy as np

from tools.hybrid_cave_saved_audit import (
    Solid, air_path_evidence, boolean_evidence, manifold_library, vdm_mapping)
from tools.hybrid_cave_saved_audit import sampled_top_height


def saved_solid(manifold, label):
    mesh = manifold.to_mesh64()
    return Solid(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), label)


class CaveSavedAuditTests(unittest.TestCase):
    def test_actual_boolean_openings_volume_and_air_route(self):
        library = manifold_library()
        rock = library.Manifold.cube([4., 4., 4.], center=True)
        cutter = library.Manifold.cube([6., 1., 1.], center=True)
        actual = rock-cutter
        source, void, saved = (saved_solid(value, label) for value, label in ((rock, "source"), (cutter, "cutter"), (actual, "actual")))
        evidence = boolean_evidence(source, void, saved)
        self.assertAlmostEqual(evidence["excavated_volume_m3"], 4.)
        self.assertAlmostEqual(evidence["actual_rock_volume_m3"], 60.)
        route = air_path_evidence(source, void, saved, [[-1.5, 0., 0.], [0., 0., 0.], [1.5, 0., 0.]], [[-3., 0., 0.], [3., 0., 0.]])
        self.assertTrue(route["actual_air_polyline_verified"])
        self.assertEqual(len(route["portal_original_exterior_face_hits"]), 2)
        mapping = vdm_mapping(void.vertices, np.zeros_like(void.vertices), void.vertices, void.triangles, [0, 1])
        self.assertTrue(mapping["immutable_portals_verified"])
        sampled = SimpleNamespace(vertices=np.array([[0., 10., 0.], [1., 12., 0.], [0., 13., 1.], [1., 17., 1.]]))
        height = sampled_top_height(sampled, {"rows": 2, "columns": 2, "origin_xz_m": [0., 0.], "spacing_m": 1.}, np.zeros(3), [.25, .75])
        self.assertEqual(height, 13.25)
        from tools.export_hybrid_cave_review import caseartifact, render_figures
        from PIL import Image
        records = {name: {"vertices_local_xyz_m": solid.vertices.tolist(), "triangles": solid.triangles.tolist(), "local_origin_xyz_m": [0., 0., 0.]}
                   for name, solid in (("rock_before", source), ("cutter", void), ("rock_after", saved), ("removed", saved_solid(rock ^ cutter, "removed")))}
        review = {"geometry_identity_sha256": "tiny", "meshes": records,
            "coordinates": {"plot_origin_xyz_m": [0., 0., 0.], "native_origin_m_xz": [-2., -2.], "native_spacing_m": 4.},
            "native_terrain": {"height_m": [[2., 2.], [2., 2.]], "valid_mask": [[True, True], [True, True]]},
            "portals": {"sink": {"xyz_m": [-2., 0., 0.]}, "spring": {"xyz_m": [2., 0., 0.]}},
            "stations": [{"origin_xyz_m": [coordinate, 0., 0.], "derived_ring_xyz_m": [[coordinate, -.5, -.5], [coordinate, -.5, .5], [coordinate, .5, .5], [coordinate, .5, -.5]]} for coordinate in (-2., 2.)],
            "actual_closed_core_station_indices": [0, 1], "surface_attachments": {}, "pins": {},
            "independent_audit_reference": {"binding_status": "not_supplied"}, "limitations": ["tiny fixture"]}
        artifact = caseartifact(review)
        self.assertIsNone(artifact["mesh"]["water"])
        self.assertEqual(artifact["mesh"]["triangles"], saved.triangles.tolist())
        figures = render_figures(review)
        self.assertEqual(set(figures), {"overview.png", "profile.png", "oblique-3d.png"})
        for payload in figures.values():
            picture = Image.open(BytesIO(payload)).convert("RGB")
            self.assertTrue(any(low != high for low, high in picture.getextrema()))

    def test_unopened_rock_and_invalid_mesh_are_not_accepted(self):
        library = manifold_library()
        source = saved_solid(library.Manifold.cube([4., 4., 4.], center=True), "source")
        void = saved_solid(library.Manifold.cube([6., 1., 1.], center=True), "void")
        with self.assertRaises(ValueError):
            boolean_evidence(source, void, source)
        with self.assertRaises(ValueError):
            air_path_evidence(source, void, source, [[-1., 0., 0.], [1., 0., 0.]], [[-3., 0., 0.], [3., 0., 0.]])
        with self.assertRaises(ValueError):
            Solid(source.vertices, source.triangles[:-1], "open fake solid")
        forged = source.triangles.copy()
        forged[0, 0] = len(source.vertices)
        with self.assertRaises(ValueError):
            Solid(source.vertices, forged, "bad geometry reference")
        displacement = np.zeros_like(void.vertices)
        displacement[0, 1] = .01
        with self.assertRaises(ValueError):
            vdm_mapping(void.vertices, displacement, void.vertices+displacement, void.triangles, [0, 1])


if __name__ == "__main__":
    unittest.main()
