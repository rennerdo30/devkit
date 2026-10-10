"""MCP admission and full Unity artifact flow using a disposable editor executable."""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
from http.server import ThreadingHTTPServer


@unittest.skipUnless(os.name == "posix", "host uses POSIX flock and process groups")
class McpUnityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"DEVKIT_DATA": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        loader = importlib.machinery.SourceFileLoader("mcp_test_server", str(Path(__file__).resolve().parents[1] / "bin/devkit-server"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.server = importlib.util.module_from_spec(spec)
        loader.exec_module(self.server)
        self.dk = self.server.dk
        Path(self.dk.JOBS).mkdir()
        self.server._name[:] = ["fixture-host"]
        self.version = "6000.6.0f1"
        editors = self.root / "editors"
        editor = editors / self.version / "Unity.app/Contents/MacOS/Unity"
        editor.parent.mkdir(parents=True)
        editor.write_text("#!" + sys.executable + "\n" +
                          "import pathlib,sys\n"
                          "print('fixture Unity output', flush=True)\n"
                          "print('argv=' + repr(sys.argv[1:]), flush=True)\n"
                          "if '-runTests' in sys.argv:\n"
                          "    pathlib.Path(sys.argv[sys.argv.index('-testResults')+1]).write_text('<test-run result=\"Passed\" total=\"2\" passed=\"2\" failed=\"0\" skipped=\"0\"/>')\n")
        editor.chmod(0o755)
        for mock in (patch.object(self.dk, "config", return_value={}),
                     patch.object(self.dk, "keep_awake", return_value=None),
                     patch.object(self.dk, "UNITY_SLOT", str(self.root / "host-unity.lock")),
                     patch.object(self.dk.devkit_kinds, "UNITY_EDITORS", str(editors))):
            mock.start()
            self.addCleanup(mock.stop)

    def rpc(self, method, params=None):
        return self.server.mcp({"id": 1, "method": method, "params": params or {}}, "fixture", "operator", ("fixture", "mcp"))["result"]

    def call(self, name, args):
        return self.rpc("tools/call", {"name": "devkit_" + name, "arguments": args})

    def test_schema_and_version(self):
        self.assertEqual(self.rpc("initialize")["serverInfo"]["version"], "0.6.0")
        tools = self.rpc("tools/list")["tools"]
        queue = next(t["inputSchema"] for t in tools if t["name"] == "devkit_queue")
        self.assertIn("unity-test", queue["properties"]["kind"]["enum"])
        props = queue["properties"]["params"]["properties"]
        self.assertEqual(props["quit"]["type"], "boolean")
        self.assertEqual(props["extra"]["type"], "array")
        self.assertEqual(props["test_platform"]["enum"], ["EditMode", "PlayMode"])
        self.assertEqual(len(queue["allOf"]), 2)

    def test_invalid_jobs_rejected_before_worker(self):
        for params in ({}, {"method": "Gate.Run", "quit": "false"},
                       {"mode": "test", "test_platform": "invalid"},
                       {"method": "Gate.Run", "extra": ["-projectPath", "/foreign"]},
                       {"method": "Gate.Run", "timeout": 14401}):
            with self.subTest(params=params), patch.object(self.dk.subprocess, "Popen") as process:
                result = self.call("queue", {"project": "fixture", "commit": "none", "kind": "unity", "params": params})
                self.assertTrue(result["isError"])
                process.assert_not_called()
        self.assertEqual(os.listdir(self.dk.JOBS), [])

    def test_execute_and_test_artifacts_via_mcp(self):
        class FixtureHandler(self.server.Handler):
            def authorize(self, *args):
                return "fixture", "operator"

        http = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(http.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(http.shutdown)
        origin = "http://127.0.0.1:%d" % http.server_port
        for kind, params in (("unity", {"method": "CompileGate.Run", "quit": False}),
                             ("unity", {"mode": "test", "test_platform": "EditMode"}),
                             ("unity-test", {"test_platform": "PlayMode"})):
            with self.subTest(kind=kind, params=params):
                params = dict(params, unity_version=self.version, timeout=10)
                with patch.object(self.dk.subprocess, "Popen"):
                    queued = self.call("queue", {"project": "fixture", "commit": "none", "kind": kind, "params": params})
                self.assertFalse(queued["isError"], queued)
                jid = queued["structuredContent"]["id"]
                self.dk.execute(self.dk.load(jid))
                status = self.call("status", {"id": jid})["structuredContent"]
                self.assertEqual(status["state"], "succeeded", status)
                files = self.call("artifacts", {"id": jid})["structuredContent"]["files"]
                expected = {"job.log"} | ({"TestResults.xml", "test-summary.json"} if "test_platform" in params else set())
                self.assertEqual({f["path"] for f in files}, expected)
                for file in files:
                    read = self.call("read_artifact", {"id": jid, "path": file["path"]})["structuredContent"]
                    payload = read["text"].encode()
                    self.assertEqual(len(payload), file["bytes"])
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), file["sha256"])
                    self.assertEqual(Path(self.server.artifact_path(jid, file["path"])).read_bytes(), payload)
                    url = origin + "/api/jobs/" + jid + "/artifacts/" + file["path"]
                    with urllib.request.urlopen(url, timeout=3) as response:
                        self.assertEqual(response.read(), payload)
                    request = urllib.request.Request(url, headers={"Range": "bytes=0-3"})
                    with urllib.request.urlopen(request, timeout=3) as response:
                        self.assertEqual(response.status, 206)
                        self.assertEqual(response.read(), payload[:4])
                log = self.call("log", {"id": jid})["structuredContent"]["text"]
                self.assertIn("fixture Unity output", log)
                self.assertIn("'-batchmode'", log)
                self.assertNotIn("'-quit'", log)
                if "test_platform" in params:
                    summary = json.loads(self.call("read_artifact", {"id": jid, "path": "test-summary.json"})["structuredContent"]["text"])
                    self.assertEqual(summary["passed"], 2)


if __name__ == "__main__":
    unittest.main()
