"""Validate the actual tools/list payload and Claude-compatible schema shape."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator


class McpSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        loader = importlib.machinery.SourceFileLoader(
            "mcp_schema_server", str(Path(__file__).resolve().parents[1] / "bin/devkit-server"))
        cls.server = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        # Windows can inspect schemas; it never executes the POSIX job runner.
        modules = {} if os.name == "posix" else {"fcntl": types.ModuleType("fcntl")}
        with patch.dict(os.environ, DEVKIT_DATA=cls.tmp.name), patch.dict(sys.modules, modules):
            loader.exec_module(cls.server)

    def tools(self, role="operator"):
        response = self.server.mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                   "schema-fixture", role, ("fixture", "schema"))
        return json.loads(json.dumps(response))["result"]["tools"]

    def test_all_roles_advertise_all_tools_including_queue(self):
        expected = {"devkit_" + name for name in (
            "hosts", "ping", "system", "kinds", "projects", "devices", "simulators", "device_apps",
            "signing", "queue", "list", "status", "log", "cancel", "artifacts", "read_artifact")}
        for role in ("viewer", "operator", "admin"):
            with self.subTest(role=role):
                tools = self.tools(role)
                self.assertEqual(len(tools), 16)
                self.assertEqual({t["name"] for t in tools}, expected)

    def test_every_wire_schema_is_draft202012_valid_and_client_compatible(self):
        for tool in self.tools():
            with self.subTest(tool=tool["name"]):
                schema = tool["inputSchema"]
                Draft202012Validator.check_schema(schema)
                self.assertEqual(schema["type"], "object")
                self.assertIsInstance(schema["properties"], dict)
                self.assertFalse({"allOf", "oneOf", "anyOf"} & schema.keys())

    def test_queue_enums_are_nonempty_unique_strings(self):
        queue = next(t["inputSchema"] for t in self.tools() if t["name"] == "devkit_queue")
        for key, expected in (("kind", list(self.server.dk.KINDS)),
                              ("target", list(self.server.dk.devkit_kinds.TARGETS))):
            enum = queue["properties"][key]["enum"]
            self.assertTrue(enum)
            self.assertTrue(all(isinstance(value, str) for value in enum))
            self.assertEqual(len(enum), len(set(enum)))
            self.assertEqual(enum, expected)

    def test_host_parameter_does_not_leak_into_hosts_or_templates(self):
        tools = {name: schema for name, _, schema in self.server.MCP_TOOLS}
        self.assertNotIn("host", tools["hosts"]["properties"])
        self.assertEqual(self.server.O, {"type": "object", "properties": {}})
        self.assertNotIn("host", self.server.ID_ONLY["properties"])
        for name, schema in tools.items():
            if name != "hosts":
                self.assertEqual(schema["properties"]["host"], self.server.HOST)
                self.assertIsNot(schema["properties"]["host"], self.server.HOST)

    def test_tool_schemas_have_no_shared_mutable_nodes(self):
        owners = {}

        def visit(value, owner):
            if isinstance(value, (dict, list)):
                previous = owners.setdefault(id(value), owner)
                self.assertEqual(previous, owner, "schema node shared between tools")
                for child in value.values() if isinstance(value, dict) else value:
                    visit(child, owner)

        for name, _, schema in self.server.MCP_TOOLS:
            visit(schema, name)
        params = next(
            schema["properties"]["params"] for name, _, schema in self.server.MCP_TOOLS if name == "queue")
        self.assertIsNot(params["properties"], self.server.dk.devkit_kinds.UNITY_PARAMS)

    def test_startup_guard_rejects_root_combinators_and_missing_queue(self):
        for keyword in ("allOf", "oneOf", "anyOf"):
            with self.subTest(keyword=keyword), self.assertRaisesRegex(ValueError, "root combinators"):
                self.server.prepare_mcp_tools([("queue", "fixture", {"type": "object", keyword: [{}]})])
        with self.assertRaisesRegex(ValueError, "devkit_queue must be advertised"):
            self.server.prepare_mcp_tools([("hosts", "fixture", self.server.O)])

    def test_queue_accepts_documented_kind_specific_params(self):
        schema = next(t["inputSchema"] for t in self.tools() if t["name"] == "devkit_queue")
        validator = Draft202012Validator(schema)
        for kind, params in (("build", {"scheme": "Game", "configuration": "Debug"}),
                             ("unity", {"method": "Gate.Run", "quit": False}),
                             ("unity", {"mode": "test", "test_platform": "EditMode"}),
                             ("unity-test", {"test_platform": "PlayMode"}),
                             ("echo", {"from_job": "fixture"})):
            with self.subTest(kind=kind):
                validator.validate({"project": "fixture", "commit": "none", "kind": kind,
                                    "params": params, "host": "auto"})
        for field in ("project", "commit", "kind"):
            value = {"project": "fixture", "commit": "none", "kind": "echo"}
            del value[field]
            self.assertFalse(validator.is_valid(value))
        self.assertFalse(validator.is_valid({"project": "fixture", "commit": "none", "kind": "echo", "params": []}))


if __name__ == "__main__":
    unittest.main()
