"""Automatic routing must not select a shorter, incompatible queue."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from devkit_hosts import Peers, PeerError


class HostTests(unittest.TestCase):
    def setUp(self):
        self.peers = Peers(lambda: {}, lambda c: None, "local")
        self.addCleanup(self.peers.pool.shutdown)
        self.local = dict(name="local", platform="macos", queue_len=2, kinds=["unity", "unity-test", "build"],
                          targets=["ios", "ios-sim", "macos"], unity_editors=["6000.0.1f1"],
                          capabilities={"xcode_version": "26.0", "sdks": ["iphoneos26.0"],
                                        "devices": ["phone"], "simulators": [], "simulator_runtimes": []})
        self.remote = dict(self.local, name="remote", queue_len=0, unity_editors=["6000.0.2f1"], online=True)
        self.peers.status = lambda: [self.remote]

    def test_unity_version_overrides_shorter_queue(self):
        self.assertIsNone(self.peers.route(None, self.local, {"kind": "unity", "params": {"unity_version": "6000.0.1f1"}}))
        self.assertEqual(self.peers.route(None, self.local, {"kind": "unity-test"}), "remote")

    def test_missing_kind_disk_and_device_exclude_hosts(self):
        self.remote["kinds"] = []
        self.assertIsNone(self.peers.route("ios", self.local, {"kind": "build", "device": "phone"}))
        self.local["disk"] = {"ready": False}
        with self.assertRaises(PeerError):
            self.peers.route("ios", self.local, {"kind": "build"})
        self.remote["kinds"] = ["build"]
        with self.assertRaises(PeerError):
            self.peers.route("ios", self.local, {"kind": "build", "device": "unavailable"})

    def test_explicit_requirements_and_unknown_fields_fail_closed(self):
        for requirements in ({"sdk": "missing"}, {"xcode": "25.0"}, {"simulator_runtime": "iOS-26-0"},
                             {"unexpected": "yes"}, {"sdk": 123}):
            with self.subTest(requirements=requirements), self.assertRaises(PeerError):
                self.peers.route("ios", self.local, {"kind": "build", "requires": requirements})
        self.assertEqual(self.peers.route("ios", self.local, {"kind": "build", "requires": {"sdk": "iphoneos26.0"}}), "remote")

    def test_conflicting_versions_and_malformed_params_are_rejected(self):
        for job in ({"requires": []}, {"params": []},
                    {"kind": "unity", "requires": {"unity_version": "6000.0.1f1"}, "params": {"unity_version": "6000.0.2f1"}}):
            with self.subTest(job=job), self.assertRaises(PeerError):
                self.peers.route(None, self.local, job)
