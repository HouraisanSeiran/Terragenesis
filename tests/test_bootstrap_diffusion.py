"""Offline checks for the installer paths that protect downloaded assets."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from tools.bootstrap_diffusion import download, download_large, install_upstream, valid

TEST_ROOT = Path(__file__).resolve().parents[1] / "verification" / "bootstrap-tests"
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class BootstrapTest(unittest.TestCase):
    def test_large_curl_resume_and_verify(self):
        payload = b"large terrain wheel" * 4096
        seen_ranges = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                offset = int(self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
                seen_ranges.append(offset)
                self.send_response(206 if offset else 200)
                self.send_header("Content-Length", str(len(payload) - offset))
                if offset:
                    self.send_header("Content-Range", f"bytes {offset}-{len(payload) - 1}/{len(payload)}")
                self.end_headers()
                self.wfile.write(payload[offset:])

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
                path = Path(directory) / "wheel.whl"
                part = path.with_name(path.name + ".part")
                expected = hashlib.sha256(payload).hexdigest()
                url = f"http://127.0.0.1:{server.server_port}/wheel"

                part.write_bytes(payload[:1000])
                download_large(url, path, len(payload), expected)
                self.assertEqual([1000], seen_ranges)
                self.assertTrue(valid(path, len(payload), expected))

                path.unlink()
                part.write_bytes(payload)
                download_large(url, path, len(payload), expected)
                self.assertEqual([1000], seen_ranges)
                self.assertEqual(payload, path.read_bytes())

                path.unlink()
                part.write_bytes(b"x" * len(payload))
                download_large(url, path, len(payload), expected)
                self.assertEqual([1000, 0], seen_ranges)
                self.assertTrue(valid(path, len(payload), expected))
        finally:
            server.shutdown()
            server.server_close()

    def test_resume_and_verify(self):
        payload = b"terrain diffusion model" * 4096
        seen_ranges = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                offset = int(self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
                seen_ranges.append(offset)
                self.send_response(206 if offset else 200)
                self.send_header("Content-Length", str(len(payload) - offset))
                if offset:
                    self.send_header("Content-Range", f"bytes {offset}-{len(payload) - 1}/{len(payload)}")
                self.end_headers()
                self.wfile.write(payload[offset:])

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
                path = Path(directory) / "model.bin"
                path.with_name(path.name + ".part").write_bytes(payload[:1000])
                expected = hashlib.sha256(payload).hexdigest()
                download(f"http://127.0.0.1:{server.server_port}/model", path, len(payload), expected)
                self.assertEqual([1000], seen_ranges)
                self.assertTrue(valid(path, len(payload), expected))
                path.write_bytes(b"corrupt")
                download(f"http://127.0.0.1:{server.server_port}/model", path, len(payload), expected)
                self.assertEqual([1000, 0], seen_ranges)
                path.unlink()
                part = path.with_name(path.name + ".part")
                part.write_bytes(payload)
                download(f"http://127.0.0.1:{server.server_port}/model", path, len(payload), expected)
                self.assertEqual([1000, 0], seen_ranges)
                self.assertEqual(payload, path.read_bytes())
                path.unlink()
                part.write_bytes(b"x" * len(payload))
                download(f"http://127.0.0.1:{server.server_port}/model", path, len(payload), expected)
                self.assertEqual([1000, 0, 0], seen_ranges)
                self.assertEqual(payload, path.read_bytes())
        finally:
            server.shutdown()
            server.server_close()

    def test_bundled_upstream_copy(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
            home = Path(directory)
            install_upstream(home)
            upstream = home / "runtime" / "upstream.json"
            self.assertTrue(upstream.is_file())
            self.assertTrue((home / "vendor" / "terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230" / "terrain_diffusion" / "inference" / "world_pipeline.py").is_file())


if __name__ == "__main__":
    unittest.main()
