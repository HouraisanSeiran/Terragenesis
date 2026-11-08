"""The special-terrain review reader: pinned bundles, bounded routes, no geometry rebuild.

Two layers are checked.  First the adapter on its own -- a manifest whose digest moved must
be refused, and every declared array must arrive with exactly the byte count it advertised.
Then the real HTTP surface, because the routes are the contract the browser actually sees:
the kilometre of plumbing that decides whether a request is a payload, a 403 or a 404 is
worth exercising rather than trusting.
"""

import importlib.util
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web-preview"


def load(name):
    spec = importlib.util.spec_from_file_location(name, WEB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SURFACE = load("special_surface")
BRIDGE = load("bridge")


class SpecialSurfaceReaderTests(unittest.TestCase):
    def test_manifest_digest_and_form_set_are_pinned(self):
        record = SURFACE.manifest()
        self.assertEqual(record["schema"], SURFACE.SCHEMA)
        self.assertEqual(record["status"], "candidate")
        self.assertEqual(set(record["forms"]), set(SURFACE.KINDS))
        with patch.object(SURFACE, "MANIFEST_SHA", "0" * 64):
            with self.assertRaises(ValueError):
                SURFACE.manifest()
        SURFACE.CONTEXTS.clear()

    def test_catalog_carries_no_capability(self):
        catalog = SURFACE.catalog()
        self.assertEqual(catalog["schema"], "special-surface-catalog-v1")
        self.assertEqual(set(catalog["forms"]), set(SURFACE.KINDS))
        for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable",
                     "self_intersection_verified"):
            self.assertFalse(catalog[flag], flag)

    def test_every_declared_array_matches_its_binary_body(self):
        for kind in SURFACE.KINDS:
            descriptor, buffers = SURFACE.frame(kind)
            self.assertEqual(descriptor["schema"], "special-surface-case-v1")
            self.assertTrue(descriptor["full_resolution_geometry"])
            self.assertFalse(descriptor["solver_advanced"])
            rows, cols = descriptor["chart_shape"]
            self.assertEqual(descriptor["arrays"]["change"]["shape"], [rows, cols])
            for name, record in descriptor["arrays"].items():
                body = SURFACE.binary(kind, name)
                self.assertEqual(len(body), record["bytes"], (kind, name))
                self.assertEqual(len(body), buffers[name].nbytes, (kind, name))
                self.assertEqual(record["url"], f"/api/special/array/{kind}/{name}")

    def test_mesh_reuses_the_stored_topology(self):
        # A regular chart of r x c vertices carries exactly 2(r-1)(c-1) triangles; the
        # reader must pass the stored index array through untouched rather than rebuilding.
        for kind in SURFACE.KINDS:
            descriptor, buffers = SURFACE.frame(kind)
            rows, cols = descriptor["chart_shape"]
            triangles = buffers["surface_triangles"]
            self.assertEqual(triangles.shape, (2 * (rows - 1) * (cols - 1), 3))
            self.assertEqual(buffers["surface_vertices"].shape, (rows * cols, 3))
            self.assertLess(int(triangles.max()), rows * cols)

    def test_unknown_form_and_array_are_refused(self):
        with self.assertRaises(ValueError):
            SURFACE.context("no_such_form")
        with self.assertRaises(ValueError):
            SURFACE.binary("inselberg", "no_such_array")
        with self.assertRaises(ValueError):
            SURFACE.binary("no_such_form", "change")

    def test_convergence_claim_is_recomputed_not_trusted(self):
        entry = json.loads(SURFACE.MANIFEST.read_text(encoding="utf-8"))["forms"]["inselberg"]
        tampered = {**entry, "ledger": {**entry["ledger"], "relaxation_converged": True}}
        with self.assertRaises(ValueError):
            SURFACE.record_status(tampered)
        self.assertEqual(SURFACE.record_status(entry), "bounded_relaxation_finite_stop")


class SpecialSurfaceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def fetch(self, path):
        try:
            with urlopen(self.base + path, timeout=60) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    def test_catalog_route(self):
        status, headers, body = self.fetch("/api/special/catalog")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["schema"], "special-surface-catalog-v1")

    def test_frame_then_binary_route(self):
        for kind in SURFACE.KINDS:
            status, _, body = self.fetch(f"/api/special/frame/{kind}")
            self.assertEqual(status, 200)
            descriptor = json.loads(body)
            self.assertEqual(descriptor["kind"], kind)
            for name, record in descriptor["arrays"].items():
                status, headers, blob = self.fetch(record["url"])
                self.assertEqual(status, 200, (kind, name))
                self.assertEqual(headers["Content-Type"], "application/octet-stream")
                self.assertEqual(len(blob), record["bytes"], (kind, name))

    def test_query_strings_and_unknown_routes_are_refused(self):
        status, _, body = self.fetch("/api/special/frame/inselberg?path=elsewhere")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))
        status, _, body = self.fetch("/api/special/frame/no_such_form")
        self.assertEqual(status, 500)
        self.assertIn("unknown special-terrain form", json.loads(body)["error"])
        status, _, _ = self.fetch("/api/special/frame")
        self.assertEqual(status, 404)

    def test_script_is_allowlisted_and_neighbours_stay_closed(self):
        status, headers, body = self.fetch("/special-surface.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertIn(b"window.specialSurface", body)
        status, _, _ = self.fetch("/special-surface-nope.js")
        self.assertEqual(status, 403)

    def test_style_sheet_still_serves_the_new_canvas_class(self):
        status, _, body = self.fetch("/style.css")
        self.assertEqual(status, 200)
        self.assertIn(b".special-canvas", body)


if __name__ == "__main__":
    unittest.main()