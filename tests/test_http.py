"""Real HTTP authorization and local/one-hop artifact transfer contracts."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.servers = []
        for number in range(2):
            root = Path(self.tmp.name) / str(number)
            root.mkdir()
            loader = importlib.machinery.SourceFileLoader("http_fixture_%s" % number, str(Path(__file__).resolve().parents[1] / "bin/devkit-server"))
            module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
            with patch.dict(os.environ, DEVKIT_DATA=str(root)):
                loader.exec_module(module)
            (root / "jobs/artifact").mkdir(parents=True)
            art = root / "artifacts"
            art.mkdir()
            self.payload = b"abcdefgh" * (256 * 1024)
            (art / 'large-"雪.bin').write_bytes(self.payload)
            (art / "empty.txt").write_bytes(b"")
            (art / "escape").symlink_to(root.parent)
            module.dk.save(dict(id="artifact", seq=1, state="succeeded", artifact_dir=str(art)))
            module.tokens = module.auth.TokenStore(str(root / "tokens.json"), "fixture-owner")
            _, operator = module.tokens.create("operator", "operator", "test")
            _, viewer = module.tokens.create("viewer", "viewer", "test")
            module._name[:] = ["host%s" % number]
            http = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
            http.daemon_threads = True
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(http.server_close)
            self.addCleanup(thread.join, 2)
            self.addCleanup(http.shutdown)
            self.servers.append((module, "http://127.0.0.1:%d" % http.server_port, operator, viewer))
        module, _, _, _ = self.servers[0]
        peer, url, operator, _ = self.servers[1]
        module.peers = module.hosts.Peers(lambda: {"peers": [{"name": "peer", "url": url, "token": operator}]}, lambda c: None, "host0")
        self.addCleanup(module.peers.pool.shutdown)

    def request(self, path, token="fixture-owner", headers=None, method="GET", body=None):
        h = {"Authorization": "Bearer " + token} if token else {}
        h.update(headers or {})
        req = urllib.request.Request(self.servers[0][1] + path, headers=h, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            return response.status, response.headers, response.read()

    def test_authentication_roles_and_cleanup_admin_boundary(self):
        operator, viewer = self.servers[0][2:]
        self.assertEqual(self.request("/api/jobs", token="")[0], 401)
        self.assertEqual(self.request("/api/jobs", token=viewer)[0], 200)
        self.assertEqual(self.request("/api/jobs", token=viewer, method="POST", body={})[0], 403)
        self.assertEqual(self.request("/api/tokens", token=operator)[0], 403)
        self.assertEqual(self.request("/api/cleanup", token=operator, method="POST", body={})[0], 403)
        self.assertEqual(self.request("/api/screen", token=viewer)[0], 403)
        self.assertEqual(self.request("/api/hosts/peer/jobs", token=viewer, method="POST", body={})[0], 403)
        status, _, data = self.request("/api/cleanup", method="POST", body={})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["dry_run"])
        self.assertEqual(self.request("/api/cleanup", method="POST", body={"apply": "false"})[0], 400)

    def test_local_and_peer_ranges_headers_and_full_checksum(self):
        from hashlib import sha256
        from urllib.parse import quote
        for prefix in ("/api", "/api/hosts/peer"):
            path = prefix + '/jobs/artifact/artifacts/' + quote('large-"雪.bin')
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(sha256(body).digest(), sha256(self.payload).digest())
            self.assertIn("filename*=UTF-8", headers["Content-Disposition"])
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            for value, expected in (("bytes=2-8", self.payload[2:9]), ("bytes=-9", self.payload[-9:]),
                                    ("bytes=2097148-", self.payload[2097148:])):
                status, headers, body = self.request(path, headers={"Range": value})
                self.assertEqual(status, 206)
                self.assertEqual(body, expected)
                self.assertEqual(int(headers["Content-Length"]), len(expected))
                self.assertIn("bytes ", headers["Content-Range"])
            self.assertEqual(self.request(path, headers={"Range": "bytes=99999999-"})[0], 416)
            self.assertEqual(self.request(path, headers={"Range": "bytes=0-1,3-4"})[0], 200)

    def test_empty_traversal_and_one_hop_guard(self):
        self.assertEqual(self.request("/api/jobs/artifact/artifacts/empty.txt")[2], b"")
        self.assertEqual(self.request("/api/jobs/artifact/artifacts/../tokens.json")[0], 404)
        self.assertEqual(self.request("/api/jobs/artifact/artifacts/escape/0/tokens.json")[0], 404)
        self.assertEqual(self.request("/api/hosts/peer/jobs", headers={"X-Devkit-Hop": "1"})[0], 400)
