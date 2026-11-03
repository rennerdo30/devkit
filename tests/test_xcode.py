"""Xcode command contracts; no builds, signing credentials, devices, or uploads."""
import plistlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import devkit_kinds as kinds


class XcodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ctx = Mock()
        self.ctx.Fail = ValueError
        self.ctx.work = str(self.root / "work")
        self.ctx.art = str(self.root / "art")
        self.ctx.derived = str(self.root / "derived")
        self.ctx.inputs = None
        for folder in (self.ctx.work, self.ctx.art, self.ctx.derived):
            Path(folder).mkdir()
        Path(self.ctx.work, "Game.xcodeproj").mkdir()
        self.ctx.target, self.ctx.device = "ios", "phone"
        self.ctx.p = {"scheme": "Game", "project": "Game.xcodeproj"}
        self.ctx.auth_args.return_value = ["-allowProvisioningUpdates"]

    def test_test_job_uses_requested_device_and_result_bundle(self):
        kinds.k_test(self.ctx)
        cmd = self.ctx.run.call_args.args[0]
        self.assertIn("id=phone", cmd)
        self.assertEqual(cmd[-3:], ["test", "-resultBundlePath", str(Path(self.ctx.art) / "Tests.xcresult")])

    def test_archive_export_stays_local_unless_explicit_upload(self):
        kinds.export(self.ctx, "/fixture/App.xcarchive", "app-store-connect")
        plist = Path(self.ctx.art) / "ExportOptions.plist"
        self.assertEqual(plistlib.loads(plist.read_bytes())["destination"], "export")
        kinds.export(self.ctx, "/fixture/App.xcarchive", "app-store-connect", upload=True)
        self.assertEqual(plistlib.loads(plist.read_bytes())["destination"], "upload")

    def test_deploy_existing_app_does_not_rebuild(self):
        Path(self.ctx.work, "Game.app").mkdir()
        self.ctx.p["app"] = "Game.app"
        kinds.k_deploy(self.ctx)
        cmd = self.ctx.run.call_args.args[0]
        self.assertEqual(cmd[:5], ["xcrun", "devicectl", "device", "install", "app"])
        self.assertIn("phone", cmd)
        self.assertEqual(self.ctx.run.call_count, 1)

    def test_paths_cannot_escape_checkout_or_artifacts(self):
        (self.root / "outside").write_text("outside")
        with self.assertRaises(ValueError):
            kinds.inside(self.ctx, "../outside")
