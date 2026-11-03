"""Contained Unity outputs and Android signing with disposable fake tools only."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
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
        self.editor_run = self.ctx.run
        self.copy_codes = [1, 0]
        self.before_copy = None
        self.ctx.run = self.fake_run

    def fake_run(self, cmd, **kwargs):
        if cmd[0] != '/bin/cp':
            return self.editor_run(cmd, **kwargs)
        self.ctx.calls.append((cmd, kwargs))
        if self.before_copy:
            self.before_copy()
            self.before_copy = None
        code = self.copy_codes.pop(0) if self.copy_codes else 0
        if code:
            if kwargs.get('check', True):
                raise self.ctx.Fail('copy failed')
            return code
        source, dest = cmd[-2:]
        if os.path.islink(source):
            os.symlink(os.readlink(source), dest)
        elif os.path.isdir(source):
            shutil.copytree(source, dest, symlinks=True)
        else:
            shutil.copy2(source, dest, follow_symlinks=False)
        return 0

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
        link.symlink_to('.', target_is_directory=True)
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
        self.copy_codes = [0]
        kinds.k_unity(self.ctx)
        copies = [cmd for cmd, _ in self.ctx.calls if cmd[0] == '/bin/cp']
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0][:4], ['/bin/cp', '-c', '-R', '-P'])
        self.assertEqual(Path(self.ctx.art, 'out.txt').read_text(), 'data')

    def test_collect_source_swap_preserves_links_then_rejects_copied_escape(self):
        output = Path(self.ctx.work, 'out')
        output.mkdir()
        source = output / 'payload'
        host_file = self.base / 'host-file'
        host_file.write_text('private-host-content')
        self.ctx.p['collect'] = ['out']
        validate = kinds.validate_collect_tree
        for codes in ([0], [1, 0]):
            with self.subTest(codes=codes):
                source.unlink(missing_ok=True)
                source.write_text('safe-content')
                self.copy_codes = list(codes)
                def swap():
                    source.unlink()
                    source.symlink_to(host_file)
                self.before_copy = swap
                def inspect(ctx, root, path, active=None):
                    self.assertEqual(root, str(Path(ctx.art, 'out')))
                    if active is None:
                        self.assertTrue(Path(path, 'payload').is_symlink())
                    return validate(ctx, root, path, active)
                with mock.patch.object(kinds, 'validate_collect_tree', side_effect=inspect), self.assertRaisesRegex(self.ctx.Fail, 'symlink escape'):
                    kinds.k_unity(self.ctx)
                self.assertFalse(Path(self.ctx.art, 'out').exists())
                self.assertEqual(host_file.read_text(), 'private-host-content')
        copies = [cmd for cmd, _ in self.ctx.calls if cmd[0] == '/bin/cp']
        self.assertTrue(all('-P' in cmd and '-L' not in cmd for cmd in copies))

    def test_collect_keeps_relative_internal_link_and_rejects_link_to_sibling(self):
        output = Path(self.ctx.work, 'out')
        output.mkdir()
        (output / 'data').write_text('data')
        (output / 'link').symlink_to('data')
        self.ctx.p['collect'] = ['out']
        kinds.k_unity(self.ctx)
        self.assertTrue(Path(self.ctx.art, 'out/link').is_symlink())
        self.assertEqual(Path(self.ctx.art, 'out/link').read_text(), 'data')
        shutil.rmtree(Path(self.ctx.art, 'out'))
        (output / 'link').unlink()
        Path(self.ctx.work, 'sibling').write_text('outside-copy')
        (output / 'link').symlink_to('../sibling')
        with self.assertRaisesRegex(self.ctx.Fail, 'symlink escape'):
            kinds.k_unity(self.ctx)
        self.assertFalse(Path(self.ctx.art, 'out').exists())

    def test_collect_reserves_runner_outputs_before_they_exist(self):
        for name in sorted(kinds.RESERVED_ARTIFACT_NAMES) + ['Job.Log', 'JOB.JSON']:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'reserved'):
                    kinds.validate_unity_params({'method': 'Build.Export', 'collect': ['out/' + name]})
                Path(self.ctx.work, name).write_text('untrusted')
                self.ctx.p['collect'] = [name]
                with self.assertRaisesRegex(self.ctx.Fail, 'reserved'):
                    kinds.collect_unity(self.ctx)
                self.assertFalse(Path(self.ctx.art, name).exists())
        self.assertEqual(self.ctx.calls, [])

    def test_collect_existing_artifact_collision_ignores_case(self):
        Path(self.ctx.work, 'out').write_text('new')
        Path(self.ctx.art, 'OUT').write_text('retained')
        self.ctx.p['collect'] = ['out']
        with self.assertRaisesRegex(self.ctx.Fail, 'already exists'):
            kinds.collect_unity(self.ctx)
        self.assertEqual(Path(self.ctx.art, 'OUT').read_text(), 'retained')

    def test_collect_rejects_absolute_root_link_to_checkout_file(self):
        source = Path(self.ctx.work, 'data')
        source.write_text('data')
        Path(self.ctx.work, 'export').symlink_to(source)
        self.ctx.p['collect'] = ['export']
        with self.assertRaisesRegex(self.ctx.Fail, 'absolute symlink'):
            kinds.collect_unity(self.ctx)
        self.assertFalse(os.path.lexists(Path(self.ctx.art, 'export')))

    def test_collect_clone_and_fallback_share_remaining_deadline(self):
        Path(self.ctx.work, 'out').write_text('data')
        self.ctx.p['collect'] = ['out']
        self.ctx.unity_deadline = 100
        with mock.patch.object(kinds.time, 'monotonic', side_effect=[40, 70]):
            kinds.collect_unity(self.ctx)
        copies = [(cmd, options) for cmd, options in self.ctx.calls if cmd[0] == '/bin/cp']
        self.assertEqual([options['timeout'] for _, options in copies], [60, 30])
        self.assertEqual(copies[1][0][:3], ['/bin/cp', '-R', '-P'])

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


class CollectRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_runner()

    def test_cancel_and_deadline_stop_clone_and_fallback_and_remove_partial_copy(self):
        for cancel in (False, True):
            for fallback in (False, True):
                with self.subTest(cancel=cancel, fallback=fallback), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    work, art = base / 'checkout', base / 'artifacts'
                    work.mkdir()
                    art.mkdir()
                    (work / 'out').mkdir()
                    cancel_file = base / 'cancel'
                    fake_cp = base / 'fake-cp'
                    fake_cp.write_text('#!' + sys.executable + '\n' +
                        'import pathlib,sys,time\n' +
                        'dest=pathlib.Path(sys.argv[-1]); dest.mkdir(); (dest / "partial").write_text("data")\n' +
                        ('if "-c" in sys.argv: sys.exit(1)\n' if fallback else '') +
                        ('pathlib.Path(' + repr(str(cancel_file)) + ').touch()\n' if cancel else '') +
                        'time.sleep(30)\n')
                    fake_cp.chmod(0o755)
                    popen = self.runner.subprocess.Popen
                    def launch(cmd, **kwargs):
                        if cmd[0] == '/bin/cp':
                            cmd = [str(fake_cp)] + cmd[1:]
                        return popen(cmd, **kwargs)
                    with mock.patch.object(self.runner, 'config', return_value={}), mock.patch.object(self.runner, 'save'), \
                            mock.patch.object(self.runner.subprocess, 'Popen', side_effect=launch):
                        ctx = self.runner.Ctx({'id': 'fixture', 'project': 'fixture', 'params': {'collect': ['out']}}, io.StringIO(), str(art))
                        ctx.work = str(work)
                        ctx.cancel_file = str(cancel_file)
                        ctx.unity_deadline = time.monotonic() + (10 if cancel else 0.4)
                        start = time.monotonic()
                        with self.assertRaises(self.runner.Cancelled if cancel else self.runner.Fail):
                            self.runner.devkit_kinds.collect_unity(ctx)
                        self.assertLess(time.monotonic() - start, 4)
                    self.assertFalse((art / 'out').exists())
                    self.assertIsNone(ctx.st['pid'])
                    self.assertIsNone(ctx.st['process_group'])
                    self.assertEqual(len(ctx.st['steps']), 2 if fallback else 1)


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
        self.tool('keytool', "print('SHA256: ' + ':'.join(['AB'] * 32)); print('Subject Public Key Algorithm: 2048-bit RSA key')")
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
        self.assertTrue(any('-verify' in a and '-strict' in a and '-certs' in a for a in argv))
        self.assertTrue(any('-printcert' in a and '-jarfile' in a and str(dest) in a for a in argv))
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

    def test_verify_rejects_nonzero_missing_marker_unsigned_and_disabled_signatures(self):
        cases = [('jar verified.', 4), ('jar is unsigned.', 0), ('verification finished', 0),
                 ('jar verified.\nWarning: unsigned entries in base/assets/data', 0),
                 ('jar verified.\nSignature algorithm is disabled', 0),
                 ('jar verified.\nThe signer key is weak', 0)]
        for output, code in cases:
            with self.subTest(output=output, code=code):
                (self.art / 'game.aab').unlink(missing_ok=True)
                self.tool('jarsigner', "if '-verify' in sys.argv:\n print(" + repr(output) + "); sys.exit(" + str(code) + ")")
                with self.assertRaises(self.runner.Fail):
                    self.kinds.k_aab_sign(self.ctx)
                self.assertFalse((self.art / 'aab-sign.json').exists())

    def test_strict_verification_rejects_unsigned_non_metadata_entry(self):
        self.tool('jarsigner', "if '-verify' in sys.argv:\n print('jar verified.'); print('Warning: unsigned entry base/assets/data'); sys.exit(16 if '-strict' in sys.argv else 0)")
        with self.assertRaisesRegex(self.runner.Fail, 'exit 16'):
            self.kinds.k_aab_sign(self.ctx)
        self.assertFalse((self.art / 'aab-sign.json').exists())

    def test_certificate_public_key_strength_comes_from_signed_bundle(self):
        for algorithm, bits, accepted in [('RSA', 1024, False), ('RSA', 2048, True), ('EC', 224, False),
                                          ('EC', 256, True), ('DSA', 2048, False), ('RSA', 4096, True)]:
            with self.subTest(algorithm=algorithm, bits=bits):
                (self.art / 'game.aab').unlink(missing_ok=True)
                (self.art / 'aab-sign.json').unlink(missing_ok=True)
                self.tool('keytool', "print('SHA256: ' + ':'.join(['AB'] * 32)); print(" +
                          repr('Subject Public Key Algorithm: %s-bit %s key' % (bits, algorithm)) + ")")
                if accepted:
                    self.kinds.k_aab_sign(self.ctx)
                    self.assertTrue((self.art / 'aab-sign.json').exists())
                else:
                    with self.assertRaisesRegex(self.runner.Fail, 'RSA 2048 or EC 256'):
                        self.kinds.k_aab_sign(self.ctx)
                    self.assertFalse((self.art / 'aab-sign.json').exists())

    def test_missing_certificate_public_key_size_fails_closed(self):
        self.tool('keytool', "print('SHA256: ' + ':'.join(['AB'] * 32))")
        with self.assertRaisesRegex(self.runner.Fail, 'RSA 2048 or EC 256'):
            self.kinds.k_aab_sign(self.ctx)
        self.assertFalse((self.art / 'aab-sign.json').exists())

    def test_password_matching_certificate_text_does_not_corrupt_private_parsing(self):
        for password in ('SHA256', 'AB'):
            with self.subTest(password=password):
                (self.art / 'game.aab').unlink(missing_ok=True)
                (self.art / 'aab-sign.json').unlink(missing_ok=True)
                self.log.seek(0)
                self.log.truncate()
                self.tool('security', 'print(' + repr(password) + ')')
                self.kinds.k_aab_sign(self.ctx)
                report = json.loads((self.art / 'aab-sign.json').read_text())
                self.assertEqual(report['signer_cert_sha256'], 'ab' * 32)
                self.assertNotIn(password, self.log.getvalue())
                self.assertNotIn(password, json.dumps(self.ctx.st))
                self.assertNotIn('SHA256: ' + ':'.join(['AB'] * 32), self.log.getvalue())

    def test_private_parser_leaves_captured_output_and_logs_redacted(self):
        parsed, captured = {}, []
        def inspect(line):
            if line.startswith('SHA256:'):
                parsed['fingerprint'] = line.split(': ', 1)[1].strip().replace(':', '').lower()
        result = self.ctx.run([str(self.bin / 'keytool')], out=captured, redact_values=['SHA256', 'AB'], parse_output=inspect)
        self.assertEqual(result, 0)
        self.assertEqual(parsed, {'fingerprint': 'ab' * 32})
        for output in (''.join(captured), self.log.getvalue(), json.dumps(self.ctx.st)):
            self.assertNotIn('SHA256', output)
            self.assertNotIn('AB', output)

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
