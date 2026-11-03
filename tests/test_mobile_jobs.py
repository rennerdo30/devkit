"""Contained Unity outputs and Android signing with disposable fake tools only."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from test_unity import FakeContext, kinds


def load_runner():
    loader = importlib.machinery.SourceFileLoader('mobile_runner_tests', str(Path(__file__).resolve().parents[1] / 'bin/devkit'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class UnityProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.ctx = FakeContext(self.base, {'method': 'Build.Export'})
        self.editor = self.base / 'editors/6000.0.23f1/Unity.app/Contents/MacOS/Unity'
        self.editor.parent.mkdir(parents=True)
        self.editor.touch()
        patch = mock.patch.object(kinds, 'UNITY_EDITORS', str(self.base / 'editors'))
        patch.start()
        self.addCleanup(patch.stop)

    def nested_project(self):
        project = Path(self.ctx.work, 'unity')
        (project / 'ProjectSettings').mkdir(parents=True)
        (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.23f1')
        self.ctx.p['project_dir'] = 'unity'
        return project

    def test_nested_project_collect_then_archive_input(self):
        project = self.nested_project()
        export = project / 'Builds/iOS/Unity-iPhone.xcodeproj'
        export.mkdir(parents=True)
        (export / 'project.pbxproj').write_text('example')
        self.ctx.p.update(collect=['unity/Builds/iOS'], args=['-gameVersion', '1.0.0'])
        with mock.patch.object(kinds.subprocess, 'run', return_value=mock.Mock(returncode=1)):
            kinds.k_unity(self.ctx)
        cmd = self.ctx.calls[0][0]
        self.assertEqual(cmd[cmd.index('-projectPath') + 1], str(project.resolve()))
        self.assertEqual(cmd[-2:], ['-gameVersion', '1.0.0'])
        self.ctx.inputs = self.ctx.art
        self.assertEqual(kinds.inside(self.ctx, 'iOS/Unity-iPhone.xcodeproj'), str(Path(self.ctx.art, 'iOS/Unity-iPhone.xcodeproj').resolve()))
        self.assertEqual(Path(self.ctx.art, 'iOS/Unity-iPhone.xcodeproj/project.pbxproj').read_text(), 'example')

    def test_nested_test_alias_and_file_collection(self):
        project = self.nested_project()
        (project / 'result.txt').write_text('result')
        self.ctx.p = {'project_dir': 'unity', 'test_platform': 'EditMode', 'collect': ['unity/result.txt']}
        kinds.k_unity_test(self.ctx)
        self.assertEqual(Path(self.ctx.art, 'result.txt').read_text(), 'result')
        self.assertTrue(Path(self.ctx.art, 'test-summary.json').exists())

    def test_project_dir_requires_marker_even_with_explicit_version(self):
        self.ctx.p.update(project_dir='empty', unity_version='6000.0.23f1')
        Path(self.ctx.work, 'empty').mkdir()
        with self.assertRaisesRegex(self.ctx.Fail, 'missing'):
            kinds.k_unity(self.ctx)
        self.assertEqual(self.ctx.calls, [])

    def test_root_project_dir_and_missing_default_marker(self):
        self.ctx.p['project_dir'] = '.'
        kinds.k_unity(self.ctx)
        self.assertEqual(self.ctx.calls[0][0][3], os.path.realpath(self.ctx.work))
        Path(self.ctx.work, 'ProjectSettings/ProjectVersion.txt').unlink()
        with self.assertRaises(self.ctx.Fail):
            kinds.k_unity(self.ctx)

    def test_path_syntax_rejected_before_execution(self):
        for field, values in [('project_dir', ['/tmp/example', '../unity', 'unity/../unity', 'unity\\project', '', 5]),
                              ('collect', [['/tmp/example'], ['../out'], ['a/../b'], ['.'], [3], 'out'])]:
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    kinds.validate_unity_params({'method': 'Build.Export', field: value})

    def test_project_and_marker_symlink_escapes(self):
        Path(self.ctx.work, 'external').symlink_to(self.base, target_is_directory=True)
        self.ctx.p['project_dir'] = 'external'
        with self.assertRaisesRegex(self.ctx.Fail, 'escapes'):
            kinds.k_unity(self.ctx)
        project = self.nested_project()
        marker = project / 'ProjectSettings/ProjectVersion.txt'
        marker.unlink()
        marker.symlink_to(self.base / 'outside.txt')
        (self.base / 'outside.txt').write_text('version')
        with self.assertRaisesRegex(self.ctx.Fail, 'escapes'):
            kinds.k_unity(self.ctx)

    def test_collect_missing_descendant_escape_cycle_and_collision(self):
        output = Path(self.ctx.work, 'out')
        output.mkdir()
        self.ctx.p['collect'] = ['missing']
        with self.assertRaisesRegex(self.ctx.Fail, 'missing'):
            kinds.k_unity(self.ctx)
        self.ctx.p['collect'] = ['out']
        link = output / 'link'
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(self.ctx.Fail, 'symlink escape'):
            kinds.k_unity(self.ctx)
        link.unlink()
        link.symlink_to(output, target_is_directory=True)
        with self.assertRaisesRegex(self.ctx.Fail, 'cycle'):
            kinds.k_unity(self.ctx)
        link.unlink()
        Path(self.ctx.art, 'out').write_text('existing')
        with self.assertRaisesRegex(self.ctx.Fail, 'already exists'):
            kinds.k_unity(self.ctx)
        self.assertEqual(Path(self.ctx.art, 'out').read_text(), 'existing')

    def test_collect_top_level_escape_and_dangling_link(self):
        Path(self.ctx.work, 'escape').symlink_to(self.base)
        self.ctx.p['collect'] = ['escape']
        with self.assertRaisesRegex(self.ctx.Fail, 'escapes'):
            kinds.k_unity(self.ctx)
        output = Path(self.ctx.work, 'out')
        output.mkdir()
        (output / 'missing').symlink_to(output / 'not-there')
        self.ctx.p['collect'] = ['out']
        with self.assertRaises(self.ctx.Fail):
            kinds.k_unity(self.ctx)

    def test_collect_not_run_on_failed_editor_or_failed_tests(self):
        self.ctx.p['collect'] = ['missing']
        self.ctx.code = 1
        with self.assertRaisesRegex(self.ctx.Fail, 'exited'):
            kinds.k_unity(self.ctx)
        self.ctx.code = 0
        self.ctx.p.update(mode='test', test_platform='EditMode')
        del self.ctx.p['method']
        self.ctx.xml = '<test-run result="Failed" total="1" failed="1" passed="0"/>'
        with self.assertRaisesRegex(self.ctx.Fail, 'not a passing'):
            kinds.k_unity(self.ctx)

    def test_clone_success_does_not_fallback(self):
        Path(self.ctx.work, 'out.txt').write_text('data')
        self.ctx.p['collect'] = ['out.txt']
        with mock.patch.object(kinds.subprocess, 'run', return_value=mock.Mock(returncode=0)) as cp, mock.patch.object(kinds.shutil, 'copy2') as copy:
            kinds.k_unity(self.ctx)
        self.assertEqual(cp.call_args[0][0][:2], ['/bin/cp', '-cRL'])
        copy.assert_not_called()

    def test_host_env_allowlist_only_and_secret_values_marked(self):
        self.ctx.cfg = {'unity_env': {'UNITY_TOOLS_PYTHON': '/path/to/venv/bin/python', 'UNITY_API_TOKEN': 'fixture-secret',
                                      'UNITY_PASSPHRASE': 'fixture-passphrase'}}
        kinds.k_unity(self.ctx)
        options = self.ctx.calls[0][1]
        self.assertEqual(options['env'], self.ctx.cfg['unity_env'])
        self.assertEqual(options['redact_values'], ['fixture-secret', 'fixture-passphrase'])
        with self.assertRaises(ValueError):
            kinds.validate_unity_params({'method': 'Build.Export', 'env': {'PATH': 'bad'}})
        for env in ([], {'BAD-NAME': 'value'}, {'UNITY_TEST': 3}, {'UNITY_TEST': 'a\nb'}):
            self.ctx.cfg = {'unity_env': env}
            with self.assertRaises(self.ctx.Fail):
                kinds.k_unity(self.ctx)

    def test_custom_args_reject_managed_credentials_and_unsafe_values(self):
        bad = [[flag] for flag in ('-projectPath', '-PROJECTPATH', '-logFile', '-batchmode', '-quit', '-executeMethod',
                                   '-buildTarget', '-username', '-password', '-serial', '-testResults', '-nographics', '-apiToken')]
        bad += [['-gameVersion=1'], ['$(example)'], ['/tmp/example'], ['a b'], ['https://example.test'], ['a' * 40], ['-' + 'a' * 128], [2], [''], None, '-gameVersion']
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                kinds.validate_unity_params({'method': 'Build.Export', 'args': args})
        kinds.validate_unity_params({'method': 'Build.Export', 'args': ['-gameVersion', '1.0.0', '-versionCode', '12']})


class AabSignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_runner()
        cls.kinds = cls.runner.devkit_kinds

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.password = 'fixture-signing-password'
        self.journal = self.base / 'argv.jsonl'
        self.tool('security', "print('fixture-signing-password')")
        self.tool('jarsigner', "import os\nif '-verify' in sys.argv:\n print('jar verified.')\nelse:\n print(os.environ['DEVKIT_AAB_PASSWORD'], flush=True)\n print('x' * 65530 + os.environ['DEVKIT_AAB_PASSWORD'], flush=True)\n sys.exit(int(os.environ.get('FAKE_SIGN_EXIT', '0')))\n")
        self.tool('keytool', "print('SHA256: ' + ':'.join(['AB'] * 32))")
        env = mock.patch.dict(os.environ, {'JAVA_HOME': str(self.base), 'PATH': str(self.bin), 'FAKE_SIGN_EXIT': '0'})
        env.start()
        self.addCleanup(env.stop)
        for patch in (mock.patch.object(self.runner, 'config', return_value={}), mock.patch.object(self.runner, 'save')):
            patch.start()
            self.addCleanup(patch.stop)
        self.art = self.base / 'artifacts'
        self.art.mkdir()
        self.inputs = self.base / 'inputs'
        self.inputs.mkdir()
        self.source = self.inputs / 'game.aab'
        with zipfile.ZipFile(self.source, 'w') as z:
            for name in ('META-INF/OLD.SF', 'META-INF/OLD.RSA', 'META-INF/old.ec', 'META-INF/OLD.DSA',
                         'META-INF/MANIFEST.MF', 'base/manifest/AndroidManifest.xml', 'base/assets/data', 'META-INF/keep.txt'):
                z.writestr(name, 'example')
        self.original = self.source.read_bytes()
        self.keystore = self.base / 'signing.keystore'
        self.keystore.touch()
        params = dict(from_job='source-job', aab='game.aab', keystore_path=str(self.keystore), alias='upload',
                      keychain_service='example-signing', keychain_account='upload')
        self.log = io.StringIO()
        self.ctx = self.runner.Ctx({'id': 'fixture', 'project': 'game', 'target': 'android', 'params': params}, self.log, str(self.art))
        self.ctx.work = str(self.base / 'checkout')
        self.ctx.inputs = str(self.inputs)
        self.ctx.cancel_file = str(self.base / 'cancel')

    def tool(self, name, code):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\nimport sys,json\n' +
                        'with open(' + repr(str(self.journal)) + ', "a") as f: f.write(json.dumps(sys.argv) + "\\n")\n' + code + '\n')
        path.chmod(0o755)

    def test_sign_strip_verify_and_report_without_password_leaks(self):
        self.kinds.k_aab_sign(self.ctx)
        dest = self.art / 'game.aab'
        with zipfile.ZipFile(dest) as z:
            self.assertEqual(set(z.namelist()), {'META-INF/MANIFEST.MF', 'base/manifest/AndroidManifest.xml', 'base/assets/data', 'META-INF/keep.txt'})
        self.assertEqual(self.source.read_bytes(), self.original)
        report = json.loads((self.art / 'aab-sign.json').read_text())
        self.assertEqual(report['sha256'], hashlib.sha256(dest.read_bytes()).hexdigest())
        self.assertEqual(report['size'], dest.stat().st_size)
        self.assertEqual(report['signer_cert_sha256'], 'ab' * 32)
        self.assertIn('bundletool is not installed', report['manifest_note'])
        argv = [json.loads(line) for line in self.journal.read_text().splitlines()]
        sign = next(a for a in argv if '-storepass:env' in a)
        self.assertIn('-keypass:env', sign)
        self.assertIn('SHA256withRSA', sign)
        self.assertTrue(any('-verify' in a and '-certs' in a for a in argv))
        for content in (self.journal.read_text(), self.log.getvalue(), json.dumps(self.ctx.st), *[p.read_bytes().decode('latin1') for p in self.art.iterdir()]):
            self.assertNotIn(self.password, content)
        self.assertIn('<redacted>', self.log.getvalue())
        self.assertNotIn('find-generic-password', self.log.getvalue())

    def test_sign_failure_masks_output_and_exception(self):
        with mock.patch.dict(os.environ, {'FAKE_SIGN_EXIT': '1'}), self.assertRaises(self.runner.Fail) as error:
            self.kinds.k_aab_sign(self.ctx)
        self.assertNotIn(self.password, str(error.exception))
        self.assertNotIn(self.password, self.log.getvalue())
        self.assertFalse((self.art / 'aab-sign.json').exists())

    def test_bundletool_manifest_metadata(self):
        self.tool('bundletool', "print('<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\" package=\"org.example.game\" android:versionCode=\"12\" android:versionName=\"1.0.0\"/>')")
        self.kinds.k_aab_sign(self.ctx)
        report = json.loads((self.art / 'aab-sign.json').read_text())
        self.assertEqual([report[k] for k in ('package', 'versionCode', 'versionName')], ['org.example.game', '12', '1.0.0'])

    def test_aab_path_escape_and_keystore_inside_work_rejected(self):
        for path in ('../game.aab', '/tmp/game.aab'):
            self.ctx.p['aab'] = path
            with self.assertRaises(self.runner.Fail):
                self.kinds.k_aab_sign(self.ctx)
        self.ctx.p['aab'] = 'game.aab'
        self.source.unlink()
        self.source.symlink_to(self.keystore)
        with self.assertRaisesRegex(self.runner.Fail, 'escapes'):
            self.kinds.k_aab_sign(self.ctx)
        self.source.unlink()
        self.source.write_bytes(self.original)
        Path(self.ctx.work).mkdir()
        internal = Path(self.ctx.work, 'signing.keystore')
        internal.touch()
        self.ctx.p['keystore_path'] = str(internal)
        with self.assertRaisesRegex(self.runner.Fail, 'outside'):
            self.kinds.k_aab_sign(self.ctx)
        internal.unlink()
        internal.symlink_to(self.keystore)
        self.ctx.p['keystore_path'] = str(Path(self.ctx.work))
        with self.assertRaisesRegex(self.runner.Fail, 'regular'):
            self.kinds.k_aab_sign(self.ctx)
        self.assertFalse(self.journal.exists())

    def test_keychain_error_output_never_logged(self):
        self.tool('security', "print('fixture-signing-password'); sys.exit(1)")
        with self.assertRaises(self.runner.Fail):
            self.kinds.k_aab_sign(self.ctx)
        self.assertNotIn(self.password, self.log.getvalue())
        self.assertNotIn(self.password, json.dumps(self.ctx.st))

    def test_missing_keystore_target_and_unknown_password_param(self):
        self.ctx.target = 'ios'
        with self.assertRaises(self.runner.Fail):
            self.kinds.k_aab_sign(self.ctx)
        self.ctx.target = 'android'
        self.ctx.p['password'] = self.password
        with self.assertRaises(self.runner.Fail):
            self.kinds.k_aab_sign(self.ctx)
        del self.ctx.p['password']
        self.keystore.unlink()
        with self.assertRaises(self.runner.Fail):
            self.kinds.k_aab_sign(self.ctx)
        self.assertFalse(self.journal.exists())

    def test_missing_signer_fingerprint_fails(self):
        self.tool('keytool', "print('No certificate')")
        with self.assertRaisesRegex(self.runner.Fail, 'certificate SHA-256'):
            self.kinds.k_aab_sign(self.ctx)
        self.assertFalse((self.art / 'aab-sign.json').exists())

    def test_redaction_across_read_and_bounded_output_chunks(self):
        self.tool('jarsigner', "import os,time\nif '-verify' in sys.argv:\n print('jar verified.')\nelse:\n secret=os.environ['DEVKIT_AAB_PASSWORD'].encode()\n os.write(1,b'x'*65530+secret[:10]); time.sleep(0.05)\n os.write(1,secret[10:]+b'x'*65536+secret[:10]); time.sleep(0.05)\n os.write(1,secret[10:])\n")
        self.kinds.k_aab_sign(self.ctx)
        self.assertNotIn(self.password, self.log.getvalue())
        self.assertGreaterEqual(self.log.getvalue().count('<redacted>'), 2)

    def test_invalid_optional_manifest_keeps_signed_report_with_note(self):
        self.tool('bundletool', "print('<invalid/>')")
        self.kinds.k_aab_sign(self.ctx)
        self.assertIn('skipped', json.loads((self.art / 'aab-sign.json').read_text())['manifest_note'])

    def test_xcode_kinds_do_not_admit_android_target(self):
        with self.assertRaisesRegex(self.runner.Fail, 'ios, ios-sim, macos'):
            self.kinds.need_target(self.ctx)


if __name__ == '__main__':
    unittest.main()
