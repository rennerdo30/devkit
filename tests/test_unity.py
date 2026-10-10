"""Unity argument and artifact contracts, using a dummy editor and no Unity process."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("unity_kinds_tests", Path(__file__).resolve().parents[1] / "lib/devkit_kinds.py")
kinds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kinds)

PASS_XML = '<test-run result="Passed" total="2" passed="2" failed="0" skipped="0" />'


class FakeContext:
    class Fail(Exception):
        pass

    def __init__(self, base, params, xml=PASS_XML, code=0):
        self.p = params
        self.work = str(base / "checkout")
        self.art = str(base / "artifacts")
        self.derived = str(base / "derived")
        self.inputs = None
        self.xml, self.code, self.calls = xml, code, []
        Path(self.work, "ProjectSettings").mkdir(parents=True)
        Path(self.work, "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.23f1\n")
        Path(self.art).mkdir()

    def run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if "-testResults" in cmd and self.xml is not None:
            Path(cmd[cmd.index("-testResults") + 1]).write_text(self.xml)
        if self.code and kwargs.get("check", True):
            raise self.Fail("process exited with code %s" % self.code)
        return self.code

    def write(self, name, text):
        Path(self.art, name).write_text(text)


class UnityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        editor = self.base / "editors/6000.0.23f1/Unity.app/Contents/MacOS/Unity"
        editor.parent.mkdir(parents=True)
        editor.touch()
        patch = mock.patch.object(kinds, "UNITY_EDITORS", str(self.base / "editors"))
        patch.start()
        self.addCleanup(patch.stop)

    def context(self, params, **kwargs):
        return FakeContext(self.base, params, **kwargs)

    def test_legacy_build_method_default_quit(self):
        ctx = self.context({"build_target": "iOS", "method": "Build.Export"})
        kinds.k_unity(ctx)
        cmd, options = ctx.calls[0]
        for flag in ("-batchmode", "-quit", "-executeMethod", "-logFile"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("-buildTarget") + 1], "iOS")
        self.assertEqual(cmd[cmd.index("-logFile") + 1], "-")
        self.assertEqual(options["timeout"], kinds.UNITY_MAX_TIMEOUT)

    def test_inconsistent_nunit_counts_fail(self):
        ctx = self.context({"mode": "test", "test_platform": "EditMode"},
                           xml='<test-run result="Passed" total="2" passed="0" failed="0"/>')
        with self.assertRaisesRegex(ctx.Fail, "inconsistent NUnit"):
            kinds.k_unity(ctx)
        self.assertTrue(Path(ctx.art, "TestResults.xml").exists())

    def test_negative_nunit_counts_fail(self):
        ctx = self.context({"mode": "test", "test_platform": "EditMode"},
                           xml='<test-run result="Passed" total="2" passed="3" failed="-1"/>')
        with self.assertRaisesRegex(ctx.Fail, "inconsistent NUnit"):
            kinds.k_unity(ctx)

    def test_compile_gate_omits_target_and_quit(self):
        ctx = self.context({"method": "Gate.Compile", "quit": False, "timeout": 30})
        kinds.k_unity(ctx)
        cmd, options = ctx.calls[0]
        self.assertNotIn("-quit", cmd)
        self.assertNotIn("-buildTarget", cmd)
        self.assertNotIn("-nographics", cmd)
        self.assertEqual(options["timeout"], 30)

    def test_nographics_opt_in(self):
        ctx = self.context({"method": "Gate.Compile", "nographics": True})
        kinds.k_unity(ctx)
        self.assertIn("-nographics", ctx.calls[0][0])

    def test_editmode_results_and_summary(self):
        self.check_test_run("EditMode", kinds.k_unity)

    def test_playmode_results_and_summary(self):
        self.check_test_run("PlayMode", kinds.k_unity)

    def test_unity_test_alias(self):
        self.assertIs(kinds.KINDS["unity-test"], kinds.k_unity_test)
        self.check_test_run("EditMode", kinds.k_unity_test, alias=True)

    def check_test_run(self, platform, function, alias=False):
        params = {"test_platform": platform}
        if not alias:
            params["mode"] = "test"
        ctx = self.context(params)
        function(ctx)
        cmd, options = ctx.calls[0]
        self.assertIn("-batchmode", cmd)
        self.assertIn("-runTests", cmd)
        self.assertNotIn("-quit", cmd)
        self.assertNotIn("-executeMethod", cmd)
        self.assertEqual(cmd[cmd.index("-testPlatform") + 1], platform)
        self.assertEqual(cmd[cmd.index("-testResults") + 1], str(Path(ctx.art, "TestResults.xml")))
        self.assertFalse(options["check"])
        summary = json.loads(Path(ctx.art, "test-summary.json").read_text())
        self.assertEqual((summary["platform"], summary["result"], summary["total"]), (platform, "Passed", 2))

    def test_allowlisted_extra_arguments(self):
        extra = ["-accept-apiupdate", "-force-metal", "-testFilter", "Suite.Test", "-testCategory", "Smoke", "-assemblyNames", "EditorTests", "-runSynchronously"]
        ctx = self.context({"mode": "test", "test_platform": "EditMode", "extra": extra})
        kinds.k_unity(ctx)
        self.assertEqual(ctx.calls[0][0][-len(extra):], extra)

    def test_rejects_managed_credentials_unknown_and_malformed_extra(self):
        extras = [[flag] for flag in ("-quit", "-batchmode", "-projectPath", "-logFile", "-runTests", "-testResults", "-executeMethod", "-buildTarget", "-nographics", "-username", "-password", "-serial", "-unknown")]
        extras += [["-testFilter"], ["-testFilter", "-quit"], ["-force-metal", "-force-metal"], ["-force-metal", "-force-glcore"], [""], [1], ["\x00"], "-force-metal", None]
        for extra in extras:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                kinds.validate_unity_params({"mode": "test", "test_platform": "EditMode", "extra": extra})

    def test_rejects_invalid_param_types_and_modes(self):
        bad = [{"quit": "false"}, {"nographics": 1}, {"method": "Compile"}, {"method": 3}, {"build_target": "../iOS"}, {"unity_version": "../../outside"}, {"unity_version": "6000.0.23f1/evil"}, {"mode": "compile"}, {"extra_args": []}, {"test_platform": "EditMode"}, {"timeout": True}, {"timeout": 0}, {"timeout": -1}, {"timeout": float("inf")}, {"timeout": float("nan")}, {"timeout": 14401}]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(ValueError):
                kinds.validate_unity_params({"method": "Gate.Compile", **override})
        for params in ([], None, "bad"):
            with self.subTest(params=params), self.assertRaises(ValueError):
                kinds.validate_unity_params(params)

    def test_test_mode_rejects_method_quit_platform_and_playmode_sync(self):
        for override in ({"method": "Gate.Compile"}, {"quit": False}, {"test_platform": "Standalone"}, {"test_platform": "PlayMode", "extra": ["-runSynchronously"]}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                kinds.validate_unity_params({"mode": "test", "test_platform": "EditMode", **override})
        with self.assertRaises(ValueError):
            kinds.validate_unity_params({"method": "Gate.Compile"}, test_only=True)

    def test_nonzero_execute_method_fails(self):
        ctx = self.context({"method": "Gate.Compile"}, code=1)
        with self.assertRaises(ctx.Fail):
            kinds.k_unity(ctx)

    def test_nonzero_test_exit_preserves_artifacts(self):
        ctx = self.context({"mode": "test", "test_platform": "EditMode"}, code=2)
        with self.assertRaises(ctx.Fail):
            kinds.k_unity(ctx)
        self.assertEqual(Path(ctx.art, "TestResults.xml").read_text(), PASS_XML)
        self.assertEqual(json.loads(Path(ctx.art, "test-summary.json").read_text())["exit_code"], 2)

    def test_missing_results_fail_with_summary(self):
        self.check_bad_results(None)

    def test_invalid_results_fail_with_original_and_summary(self):
        self.check_bad_results("<broken")

    def test_failed_results_fail_with_original_and_summary(self):
        self.check_bad_results('<test-run result="Failed" total="2" passed="1" failed="1" />')

    def test_empty_results_fail_with_original_and_summary(self):
        self.check_bad_results('<test-run result="Passed" total="0" passed="0" failed="0" />')

    def test_wrong_xml_root_fails(self):
        self.check_bad_results('<testsuite tests="2" failures="0" />')

    def test_invalid_count_fails(self):
        self.check_bad_results('<test-run result="Passed" total="invalid" />')

    def check_bad_results(self, xml):
        ctx = self.context({"mode": "test", "test_platform": "EditMode"}, xml=xml)
        with self.assertRaises(ctx.Fail):
            kinds.k_unity(ctx)
        summary = json.loads(Path(ctx.art, "test-summary.json").read_text())
        self.assertIn("error", summary)
        if xml is not None:
            self.assertEqual(Path(ctx.art, "TestResults.xml").read_text(), xml)

    def test_project_version_path_escape_rejected(self):
        ctx = self.context({"method": "Gate.Compile"})
        Path(ctx.work, "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: ../../outside")
        with self.assertRaisesRegex(ctx.Fail, "invalid Unity editor version"):
            kinds.k_unity(ctx)
        self.assertEqual(ctx.calls, [])

    def test_schema_contains_only_supported_params(self):
        self.assertEqual(set(kinds.UNITY_PARAMS), {"mode", "method", "build_target", "unity_version", "quit", "nographics", "test_platform", "timeout", "extra"})
        self.assertEqual(kinds.UNITY_PARAMS["mode"]["enum"], ["executeMethod", "test"])
        self.assertEqual(kinds.UNITY_PARAMS["test_platform"]["enum"], ["EditMode", "PlayMode"])
        self.assertEqual(kinds.UNITY_PARAMS["quit"]["type"], "boolean")


if __name__ == "__main__":
    unittest.main()
