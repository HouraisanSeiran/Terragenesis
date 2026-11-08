"""Two bounded behavior cases; no TD package generation or solver."""

import json
import unittest

import numpy as np

from terrain_pipeline.hybrid_geometry import Parameters, build_charts, build_rock, manifold_from_record, mesh_record, cell_record, closed_rock_section, portal_knots, seal, signed_volume, void_witnesses
from terrain_pipeline.hybrid_hydraulics import Model


def port_at(z_m):
    profile = [[2., 0., z_m], [1., 0., z_m], [-1., 0., z_m], [-2., 0., z_m]]
    segments = []
    for ordinal, (first, second) in enumerate(zip(profile, profile[1:])):
        segments.append({"profile_segment_index": ordinal, "points_xyz_m": [first, second],
            "native_pieces": [{"interval_t01": [0., 1.], "start_xz_m": [first[0], z_m],
                "end_xz_m": [second[0], z_m], "depth_coefficients_m_t01": [0., 0.],
                "source": {"source_coefficients_m_t012": [0., 0., 0.]}}]})
    return {"status": "candidate", "rejection_reasons": [], "flow_unit_xz": [0., 1.],
        "profile": {"profile_xyz_m": profile, "profile_segments": segments}}


def flat_sampler(point):
    return {"derived_bed_m": 0., "cut_depth_m": 0., "fan_keys": [],
        "source_sample": {"height_m": 0., "wet_source_support": False, "rejection_reasons": []}}


class CaveGeometryTests(unittest.TestCase):
    def test_boolean_two_real_openings_closed_rock_and_immutable_charts(self):
        parameters = Parameters(stations=9, crop_margin_m=4.)
        vdm = build_charts(port_at(0.), port_at(60.), [0., 0., 0.], [0., 0., 60.], parameters)
        origin = np.array([0., 0., 0.])
        rock_record, sampling = build_rock(vdm, flat_sampler, parameters, origin)
        before = manifold_from_record(rock_record)
        vertices = np.array([station["derived_ring_xyz_m"] for station in vdm["stations"]]).reshape(-1, 3)
        cutter = manifold_from_record(mesh_record(vertices, vdm["triangles"], origin, "cutter"))
        after, removed = before - cutter, before ^ cutter
        path, segments, openings = void_witnesses(before, after, removed, vdm, origin, flat_sampler)
        self.assertEqual(set(openings), {"sink", "spring"})
        self.assertEqual(len(path), 9)
        self.assertTrue(all(not segment["rock_after_hits"] for segment in segments))
        self.assertAlmostEqual(before.volume() - after.volume(), removed.volume(), places=8)
        self.assertGreater(removed.volume(), 0)
        self.assertGreater(signed_volume(vertices, vdm["triangles"]), 0)
        for station in vdm["stations"]:
            np.testing.assert_array_equal(np.array(station["reference_ring_xyz_m"]) + np.array(station["displacement_ring_xyz_m"]), station["derived_ring_xyz_m"])
        for station in (vdm["stations"][0], vdm["stations"][-1]):
            self.assertFalse(np.any(station["displacement_ring_xyz_m"]))
        self.assertLess(sampling["top_vertex_count"], 300000)
        cells = [cell_record(station, "underground", "engineered:underground", 7.5, parameters,
            {"vdm_station_index": ordinal}, closed_rock=2 <= ordinal <= 6) for ordinal, station in enumerate(vdm["stations"])]
        links = []
        for ordinal, (first, second) in enumerate(zip(cells, cells[1:])):
            kind = {("surface", "surface"): "surface_half_arm", ("surface", "underground"): "sink_exchange",
                ("underground", "underground"): "conduit", ("underground", "surface"): "spring_exchange"}[(first["kind"], second["kind"])]
            links.append({"link_id": str(ordinal), "from_cell_id": first["cell_id"], "to_cell_id": second["cell_id"], "kind": kind, "length_m": 7.5})
        model = Model.from_geometry({"hydraulic_cells": cells, "hydraulic_links": links})
        self.assertEqual(model.cells[0].section.kind, "open_polyline")
        self.assertEqual(model.cells[2].section.kind, "closed_polygon")
        self.assertEqual(cells[0]["route_region"], "underground")
        classifications = [closed_rock_section([{"actual_sampled_top_cover_m": -point[1]}
            for point in np.array(station["derived_ring_xyz_m"])]) for station in vdm["stations"]]
        self.assertTrue(all(type(value) is bool for value in classifications))
        self.assertTrue(any(classifications))
        self.assertFalse(all(classifications))
        saved = seal({"station_source_cover_witnesses": [{"physical_closed_rock_section": value}
            for value in classifications], "hydraulic_cells": cells, "hydraulic_links": links})
        self.assertEqual(json.loads(json.dumps(saved, allow_nan=False)), saved)
        self.assertTrue(closed_rock_section([{"actual_sampled_top_cover_m": np.float64(.5)}] * 4))
        self.assertFalse(closed_rock_section([{"actual_sampled_top_cover_m": np.nextafter(.5, 0.)}] * 4))
        with self.assertRaises(TypeError):
            seal({"unsupported_numpy_bool": np.bool_(True)})

    def test_refused_negative_quadratic_profile_and_bounded_parameters(self):
        port = port_at(0.)
        port["profile"]["profile_segments"][0]["native_pieces"][0]["depth_coefficients_m_t01"] = [-1e-16, 0.]
        with self.assertRaises(ValueError):
            portal_knots(port)
        port = port_at(0.)
        port["profile"]["profile_segments"][1]["native_pieces"][0]["source"]["source_coefficients_m_t012"][2] = .01
        with self.assertRaises(ValueError):
            portal_knots(port)
        port = port_at(0.)
        port["rejection_reasons"] = ["protected_source"]
        with self.assertRaises(ValueError):
            portal_knots(port)
        with self.assertRaises(ValueError):
            Parameters(rock_spacing_m=.01)


if __name__ == "__main__":
    unittest.main()
