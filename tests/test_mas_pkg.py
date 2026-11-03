"""App Store commands run only disposable fake tools; no real signing or Keychain access."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_mobile_jobs import load_runner
from test_unity import FakeContext, kinds


class ToolContext(FakeContext):
    class Cancelled(Exception):
        pass

    def run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                env=dict(os.environ, **kwargs.get('env', {})))
        for line in result.stdout.splitlines(keepends=True):
            if kwargs.get('parse_output'):
                kwargs['parse_output'](line)
            if kwargs.get('out') is not None:
                kwargs['out'].append(line)
        if result.returncode and kwargs.get('check', True):
            raise self.Fail('step failed: ' + Path(cmd[0]).name)
        return result.returncode

    def auth_args(self):
        return ['-allowProvisioningUpdates', '-authenticationKeyPath', '/fixture/AuthKey.p8',
                '-authenticationKeyID', 'EXAMPLEKEY', '-authenticationKeyIssuerID', 'EXAMPLEISSUER']


class MasPkgTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.journal = self.root / 'commands.jsonl'
        self.ctx = ToolContext(self.root, {'from_job': 'source-job', 'app': 'Example.app', 'profile': 'store.provisionprofile'})
        self.ctx.cfg = {'team_id': 'ABCDE12345', 'mas_profiles_dir': str(self.root / 'profiles')}
        self.ctx.cancel_file = str(self.root / 'cancel')
        self.ctx.target, self.ctx.device = 'macos', None
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.ctx.inputs = str(self.inputs)
        self.app = self.inputs / 'Example.app'
        (self.app / 'Contents/MacOS').mkdir(parents=True)
        with (self.app / 'Contents/Info.plist').open('wb') as f:
            plistlib.dump({'CFBundleIdentifier': 'com.example.game', 'CFBundleShortVersionString': '1.2.3',
                          'CFBundleVersion': '42', 'CFBundleExecutable': 'Example'}, f)
        (self.app / 'Contents/MacOS/Example').write_bytes(b'\xcf\xfa\xed\xfe' + b'example-main-code')
        framework = self.app / 'Contents/Frameworks/Example.framework/Versions/A'
        framework.mkdir(parents=True)
        (framework / 'Example').write_bytes(b'\xcf\xfa\xed\xfe' + b'example-framework-code')
        (framework.parent / 'Current').symlink_to('A', target_is_directory=True)
        (framework.parent.parent / 'Example').symlink_to('Versions/Current/Example')
        self.cert = b'fixture-apple-distribution-certificate'
        self.app_hash = hashlib.sha1(self.cert).hexdigest().upper()
        self.installer_hash = 'B' * 40
        self.identities = self.root / 'identities.txt'
        self.identity_lines = [f'  1) {self.app_hash} "Apple Distribution: Example Organization (ABCDE12345)"',
                               f'  2) {self.installer_hash} "3rd Party Mac Developer Installer: Example Organization (ABCDE12345)"',
                               '  3) ' + 'C' * 40 + ' "Developer ID Application: Example Organization (ABCDE12345)"']
        self.identities.write_text('\n'.join(self.identity_lines))
        self.profile = {'Name': 'Example Store Profile', 'UUID': '00000000-0000-0000-0000-000000000001',
                        'Platform': ['OSX'], 'TeamIdentifier': ['ABCDE12345'], 'ApplicationIdentifierPrefix': ['ABCDE12345'],
                        'ExpirationDate': datetime.datetime(2099, 1, 1), 'DeveloperCertificates': [self.cert],
                        'Entitlements': {'com.apple.application-identifier': 'ABCDE12345.com.example.game',
                                         'com.apple.developer.team-identifier': 'ABCDE12345', 'get-task-allow': False,
                                         'com.apple.security.app-sandbox': True,
                                         'com.apple.security.network.client': True,
                                         'com.apple.security.cs.allow-jit': True,
                                         'com.apple.developer.game-center': True}}
        Path(self.ctx.cfg['mas_profiles_dir']).mkdir()
        self.profile_file = Path(self.ctx.cfg['mas_profiles_dir']) / 'store.provisionprofile'
        self.save_profile()
        self.tool('security', """import shutil
if 'find-identity' in sys.argv:
 print(Path(IDENTITIES).read_text())
else:
 shutil.copyfile(sys.argv[sys.argv.index('-i')+1], sys.argv[sys.argv.index('-o')+1])
""".replace('IDENTITIES', repr(str(self.identities))))
        self.tool('codesign', "print('Apple Distribution: Example Organization (ABCDE12345)')")
        self.tool('productbuild', "Path(sys.argv[-1]).write_bytes(b'example-signed-pkg'); print('Example Organization')")
        self.tool('pkgutil', "print('Status: signed by a certificate trusted by Mac OS X'); print('Example Organization')")
        self.tool('xcodebuild', """import plistlib
if 'build' in sys.argv:
 derived = Path(sys.argv[sys.argv.index('-derivedDataPath')+1])
 (derived / 'Build/Products/Debug-appletvos/Example.app').mkdir(parents=True)
""")
        self.tool('ditto', "import shutil\nshutil.copytree(sys.argv[1], sys.argv[2])")
        env = patch.dict(os.environ, PATH=str(self.bin))
        env.start()
        self.addCleanup(env.stop)

    def tool(self, name, body):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\nimport sys,json\nfrom pathlib import Path\n' +
                        'with open(' + repr(str(self.journal)) + ', "a") as f: f.write(json.dumps(sys.argv) + "\\n")\n' + body)
        path.chmod(0o755)

    def save_profile(self):
        self.profile_file.write_bytes(plistlib.dumps(self.profile))

    def commands(self, name=None):
        commands = [json.loads(line) for line in self.journal.read_text().splitlines()] if self.journal.exists() else []
        return [cmd for cmd in commands if name is None or Path(cmd[0]).name == name]

    def test_package_inside_out_with_main_entitlements_profile_and_report(self):
        self.ctx.p['entitlement_values'] = {'com.apple.security.network.client': True, 'com.apple.developer.game-center': True}
        kinds.k_mas_pkg(self.ctx)
        art = Path(self.ctx.art)
        self.assertEqual((art / 'Example.app/Contents/embedded.provisionprofile').read_bytes(), self.profile_file.read_bytes())
        self.assertFalse((self.app / 'Contents/embedded.provisionprofile').exists())
        self.assertTrue((art / 'Example.app/Contents/Frameworks/Example.framework/Example').is_symlink())
        signs = self.commands('codesign')
        self.assertGreaterEqual(len(signs), 4)
        self.assertEqual(signs[-1][-1], str(art / 'Example.app'))
        self.assertTrue(signs[0][-1].endswith('Versions/A/Example'))
        self.assertEqual(sum('--entitlements' in cmd for cmd in signs), 1)
        self.assertTrue(all('--deep' not in cmd and '--options' not in cmd for cmd in signs))
        self.assertEqual(self.commands('productbuild')[0][1:5], ['--component', str(art / 'Example.app'), '/Applications', '--sign'])
        self.assertEqual(self.commands('productbuild')[0][-2], '3rd Party Mac Developer Installer: Example Organization (ABCDE12345)')
        self.assertEqual(self.commands('pkgutil')[0][1:], ['--check-signature', str(art / 'out.pkg')])
        self.assertEqual([cmd[-1] for cmd in self.commands('security')[:2]], ['codesigning', 'basic'])
        report = json.loads((art / 'mas-pkg.json').read_text())
        self.assertEqual(report, {'path': 'out.pkg', 'sha256': hashlib.sha256(b'example-signed-pkg').hexdigest(),
                         'size': len(b'example-signed-pkg'), 'bundle_id': 'com.example.game', 'version': '1.2.3', 'build': '42',
                         'app_signing_authority_type': 'Apple Distribution', 'installer_authority_type': '3rd Party Mac Developer Installer',
                         'team': 'ABCDE12345', 'profile_name': self.profile['Name'], 'profile_uuid': self.profile['UUID'],
                         'entitlement_keys': sorted(['com.apple.security.app-sandbox', 'com.apple.security.network.client',
                             'com.apple.developer.game-center', 'com.apple.application-identifier', 'com.apple.developer.team-identifier'])})
        for cmd, options in self.ctx.calls:
            if cmd[0] != 'xcodebuild':
                self.assertTrue(options['capture_only'])
                self.assertFalse(options['log_cmd'])
        self.assertNotIn('Example Organization', (art / 'mas-pkg.json').read_text())

    def test_reject_unknown_entitlements_debugging_sandbox_false_and_bad_values(self):
        for values in ({'get-task-allow': False}, {'com.apple.security.get-task-allow': True}, {'unknown': True},
                       {'com.apple.security.app-sandbox': False}, {'com.apple.security.network.client': 'true'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                kinds.validate_mas_pkg_params(dict(self.ctx.p, entitlement_values=values))
        self.assertEqual(self.commands(), [])

    def test_plist_input_checked_and_optional_runtime(self):
        values = {'com.apple.security.app-sandbox': True, 'com.apple.security.cs.allow-jit': True}
        (self.inputs / 'entitlements.plist').write_bytes(plistlib.dumps(values))
        self.ctx.p.update(entitlements='entitlements.plist', hardened_runtime=True)
        kinds.k_mas_pkg(self.ctx)
        self.assertTrue(all('--options' in cmd and 'runtime' in cmd for cmd in self.commands('codesign')))
        ent = plistlib.loads(Path(self.ctx.art, 'MAS-Entitlements.plist').read_bytes())
        self.assertTrue(ent['com.apple.security.cs.allow-jit'])

    def test_plist_unknown_or_identity_mismatch_fails_before_signing(self):
        (self.inputs / 'entitlements.plist').write_bytes(plistlib.dumps({'get-task-allow': False}))
        self.ctx.p['entitlements'] = 'entitlements.plist'
        with self.assertRaisesRegex(self.ctx.Fail, 'unknown or forbidden'):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(self.commands('codesign'), [])

    def test_plist_identity_mismatch_fails_before_signing(self):
        (self.inputs / 'entitlements.plist').write_bytes(plistlib.dumps({
            'com.apple.application-identifier': 'ABCDE12345.com.other.game'}))
        self.ctx.p['entitlements'] = 'entitlements.plist'
        with self.assertRaisesRegex(self.ctx.Fail, 'identity entitlements must match'):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(self.commands('codesign'), [])

    def test_real_context_keeps_identity_names_out_of_logs_and_step_labels(self):
        runner = load_runner()
        log = io.StringIO()
        with patch.object(runner, 'config', return_value=self.ctx.cfg), patch.object(runner, 'save'), \
                patch.object(runner, 'ProcessChildren') as children:
            children.return_value.alive.return_value = []  # no real ps in fake command tests
            children.return_value.group_owned = False
            ctx = runner.Ctx({'id': 'fixture', 'project': 'example', 'target': 'macos', 'params': self.ctx.p}, log, self.ctx.art)
            ctx.inputs, ctx.work = self.ctx.inputs, self.ctx.work
            ctx.cancel_file = str(self.root / 'cancel')
            kinds.k_mas_pkg(ctx)
        self.assertNotIn('Example Organization', log.getvalue())
        self.assertNotIn('Example Organization', json.dumps(ctx.st))

    def test_identity_requires_exactly_one_type_and_team(self):
        for lines in ([], [self.identity_lines[2]], [self.identity_lines[0].replace('ABCDE12345', 'ZZZZZ12345')],
                      [self.identity_lines[0], self.identity_lines[0].replace(self.app_hash, 'D' * 40)]):
            self.identities.write_text('\n'.join(lines))
            with self.subTest(lines=lines), self.assertRaisesRegex(self.ctx.Fail, 'exactly one valid Apple Distribution'):
                kinds.mas_identity(self.ctx, 'ABCDE12345')
        self.identities.write_text(self.identity_lines[1] + '\n' + self.identity_lines[1].replace(self.installer_hash, 'E' * 40))
        with self.assertRaisesRegex(self.ctx.Fail, 'exactly one valid Mac Installer Distribution'):
            kinds.mas_identity(self.ctx, 'ABCDE12345', installer=True)
        self.identities.write_text(self.identity_lines[1].replace('3rd Party Mac Developer Installer', 'Mac Installer Distribution'))
        self.assertEqual(kinds.mas_identity(self.ctx, 'ABCDE12345', installer=True)[1], 'Mac Installer Distribution')

    def test_profile_mismatches_fail_closed(self):
        original = plistlib.dumps(self.profile)
        mutations = [({'Platform': ['iOS']}, {}), ({'TeamIdentifier': ['ZZZZZ12345']}, {}),
                     ({'ExpirationDate': datetime.datetime(2000, 1, 1)}, {}), ({'DeveloperCertificates': [b'wrong']}, {}),
                     ({'ProvisionedDevices': []}, {}), ({'ProvisionsAllDevices': True}, {}),
                     ({}, {'get-task-allow': True}), ({}, {'com.apple.security.get-task-allow': True})]
        for fields, ent in mutations:
            self.profile = plistlib.loads(original)
            self.profile.update(fields)
            self.profile['Entitlements'].update(ent)
            self.save_profile()
            with self.subTest(fields=fields, ent=ent), self.assertRaisesRegex(self.ctx.Fail, 'invalid MAS profile'):
                kinds.mas_profile(self.ctx, str(self.profile_file), 'ABCDE12345', 'com.example.game', self.app_hash)
        self.assertEqual(self.commands('codesign'), [])

    def test_profile_wildcard_is_expanded_and_legacy_prefix_retained(self):
        self.profile['ApplicationIdentifierPrefix'] = ['FGHIJ12345']
        self.profile['Entitlements']['com.apple.application-identifier'] = 'FGHIJ12345.com.example.*'
        self.save_profile()
        kinds.k_mas_pkg(self.ctx)
        ent = plistlib.loads(Path(self.ctx.art, 'MAS-Entitlements.plist').read_bytes())
        self.assertEqual(ent['com.apple.application-identifier'], 'FGHIJ12345.com.example.game')

    def test_game_center_requires_profile_capability(self):
        self.profile['Entitlements'].pop('com.apple.developer.game-center')
        self.save_profile()
        self.ctx.p['entitlement_values'] = {'com.apple.developer.game-center': True}
        with self.assertRaisesRegex(self.ctx.Fail, 'authorize entitlement: com.apple.developer.game-center'):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(self.commands('codesign'), [])

    def test_every_effective_entitlement_requires_profile_authorization(self):
        for key, granted in (('com.apple.security.network.client', None),
                             ('com.apple.security.network.client', False),
                             ('com.apple.security.app-sandbox', None),
                             ('com.apple.security.app-sandbox', False),
                             ('com.apple.developer.team-identifier', 'ZZZZZ12345'),
                             ('com.apple.developer.team-identifier', None),
                             ('com.apple.application-identifier', None),
                             ('com.apple.application-identifier', 'ABCDE12345.com.other.game'),
                             ('com.apple.application-identifier', 'ABCDE12345.com.ex*')):
            with self.subTest(key=key, granted=granted):
                original = self.profile['Entitlements'].copy()
                if granted is None:
                    self.profile['Entitlements'].pop(key)
                else:
                    self.profile['Entitlements'][key] = granted
                self.save_profile()
                self.ctx.p['entitlement_values'] = {'com.apple.security.network.client': True}
                try:
                    with self.assertRaisesRegex(self.ctx.Fail, 'authorize entitlement: ' + key):
                        kinds.k_mas_pkg(self.ctx)
                    self.assertEqual(self.commands('codesign'), [])
                    self.assertFalse(Path(self.ctx.art, 'MAS-Entitlements.plist').exists())
                    self.assertEqual(list(Path(self.ctx.art).glob('mas-pkg-*')), [])
                finally:
                    self.profile['Entitlements'] = original
                    kinds.remove_collect_copy(str(Path(self.ctx.art, 'Example.app')))

    def test_authorization_checks_array_subset_and_boolean_types(self):
        key = 'example.array'
        kinds.mas_authorize_entitlements(self.ctx, {key: ['one']}, {key: ['one', 'two']})
        kinds.mas_authorize_entitlements(self.ctx, {'example.bool': False}, {'example.bool': True})
        for requested, allowed in ((['three'], ['one', 'two']), ([True], [1]), (['one'], 'one')):
            with self.subTest(requested=requested, allowed=allowed), self.assertRaisesRegex(self.ctx.Fail, key):
                kinds.mas_authorize_entitlements(self.ctx, {key: requested}, {key: allowed})
        with self.assertRaisesRegex(self.ctx.Fail, 'example.bool'):
            kinds.mas_authorize_entitlements(self.ctx, {'example.bool': True}, {'example.bool': 1})

    def test_profile_snapshot_embeds_exact_validated_bytes_after_source_replacement(self):
        self.profile['Entitlements']['com.apple.application-identifier'] = 'ABCDE12345.*'
        self.save_profile()
        expected = self.profile_file.read_bytes()
        validated, snapshots = [], []
        run = self.ctx.run

        def replace_source(cmd, **kwargs):
            result = run(cmd, **kwargs)
            if cmd[:3] == ['security', 'cms', '-D']:
                snapshot = Path(cmd[cmd.index('-i') + 1])
                self.assertNotEqual(snapshot, self.profile_file)
                self.assertEqual(snapshot.parent.parent, Path(self.ctx.art))
                self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
                validated.append(snapshot.read_bytes())
                snapshots.append(snapshot)
                self.profile_file.unlink()
                self.profile_file.write_bytes(b'replacement-not-validated')
            return result

        with patch.object(self.ctx, 'run', side_effect=replace_source):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(validated, [expected])
        self.assertEqual(Path(self.ctx.art, 'Example.app/Contents/embedded.provisionprofile').read_bytes(), validated[0])
        self.assertTrue(all(not path.exists() for path in snapshots))
        ent = plistlib.loads(Path(self.ctx.art, 'MAS-Entitlements.plist').read_bytes())
        self.assertEqual(ent['com.apple.application-identifier'], 'ABCDE12345.com.example.game')

    def test_intermediate_directory_swap_during_copy_never_reads_external_app(self):
        output = self.inputs / 'out'
        (output / 'build').mkdir(parents=True)
        self.app.rename(output / 'build/Example.app')
        self.ctx.p['app'] = 'out/build/Example.app'
        outside = self.root / 'outside'
        (outside / 'Example.app').mkdir(parents=True)
        (outside / 'Example.app/external').write_bytes(b'external-private-content')
        open_fd = os.open
        swapped = []

        def swap(name, flags, *args, **kwargs):
            if name == 'build' and 'dir_fd' in kwargs:
                self.assertTrue(flags & os.O_NOFOLLOW)
                self.assertTrue(flags & os.O_DIRECTORY)
                (output / 'build').rename(output / 'original-build')
                (output / 'build').symlink_to(outside, target_is_directory=True)
                swapped.append(name)
            return open_fd(name, flags, *args, **kwargs)

        with patch.object(kinds.os, 'open', side_effect=swap), \
                patch.object(kinds.os, 'read', wraps=os.read) as read, \
                self.assertRaisesRegex(self.ctx.Fail, 'MAS app source changed'):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(swapped, ['build'])
        read.assert_not_called()
        self.assertEqual(list(Path(self.ctx.art).iterdir()), [])
        self.assertEqual(self.commands(), [])
        self.assertEqual((outside / 'Example.app/external').read_bytes(), b'external-private-content')

    def test_cancel_and_timeout_mid_copy_remove_partial_app(self):
        payload = b'x' * (2 * 1024 * 1024)
        (self.app / 'Contents/MacOS/Example').write_bytes(payload)
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                clock, reads = [40], []
                read = os.read

                def stop_copy(fd, size):
                    chunk = read(fd, size)
                    if os.fstat(fd).st_size == len(payload):
                        reads.append(len(chunk))
                        if len(reads) == 2:
                            self.assertEqual(Path(self.ctx.art, 'Example.app/Contents/MacOS/Example').stat().st_size,
                                             1024 * 1024)
                            if cancel:
                                Path(self.ctx.cancel_file).touch()
                            else:
                                clock[0] += kinds.DEFAULT_STEP_TIMEOUT + 1
                    return chunk

                with patch.object(kinds.os, 'read', side_effect=stop_copy), \
                        patch.object(kinds.time, 'monotonic', side_effect=lambda: clock[0]), \
                        self.assertRaises(self.ctx.Cancelled if cancel else self.ctx.Fail) as failure:
                    kinds.k_mas_pkg(self.ctx)
                if not cancel:
                    self.assertIn('timed out', str(failure.exception))
                self.assertEqual(reads, [1024 * 1024, 1024 * 1024])
                self.assertEqual(list(Path(self.ctx.art).iterdir()), [])
                self.assertEqual(self.commands(), [])
                self.assertEqual((self.app / 'Contents/MacOS/Example').read_bytes(), payload)
                Path(self.ctx.cancel_file).unlink(missing_ok=True)

    def test_cancel_and_capped_deadline_during_tree_validation_clean_up(self):
        for cancel in (False, True):
            for relative in ('Contents/MacOS', 'Contents/MacOS/Example'):
                with self.subTest(cancel=cancel, relative=relative):
                    clock, checked = [40], []
                    self.ctx.unity_deadline = 100
                    validate = kinds.validate_collect_tree

                    def stop_validation(ctx, root, path, active=None, check=None):
                        self.assertIsNotNone(check)
                        if os.path.realpath(path) == os.path.realpath(os.path.join(root, relative)):
                            checked.append(path)
                            if cancel:
                                Path(ctx.cancel_file).touch()
                            else:
                                clock[0] = 101
                        return validate(ctx, root, path, active, check)

                    with patch.object(kinds, 'validate_collect_tree', side_effect=stop_validation), \
                            patch.object(kinds.time, 'monotonic', side_effect=lambda: clock[0]), \
                            self.assertRaises(self.ctx.Cancelled if cancel else self.ctx.Fail):
                        kinds.k_mas_pkg(self.ctx)
                    self.assertEqual(len(checked), 1)
                    self.assertEqual(list(Path(self.ctx.art).iterdir()), [])
                    self.assertEqual(self.commands(), [])
                    Path(self.ctx.cancel_file).unlink(missing_ok=True)

    def test_paths_stay_in_artifacts_and_configured_profiles_directory(self):
        for key in ('app', 'profile', 'entitlements'):
            for value in ('../outside', '/outside', 'a/../b'):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    kinds.validate_mas_pkg_params(dict(self.ctx.p, **{key: value}))
        self.profile_file.unlink()
        self.profile_file.symlink_to(self.inputs / 'outside')
        (self.inputs / 'outside').write_text('private')
        with self.assertRaisesRegex(self.ctx.Fail, 'escapes'):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(self.commands(), [])

    def test_bundle_symlink_escape_rejected_before_signing(self):
        (self.app / 'Contents/escape').symlink_to(self.root)
        with self.assertRaisesRegex(self.ctx.Fail, 'symlink escape'):
            kinds.k_mas_pkg(self.ctx)
        self.assertEqual(self.commands(), [])

    def test_tool_failure_never_publishes_report(self):
        self.tool('pkgutil', 'sys.exit(1)')
        with self.assertRaises(self.ctx.Fail):
            kinds.k_mas_pkg(self.ctx)
        self.assertFalse(Path(self.ctx.art, 'mas-pkg.json').exists())

    def test_tvos_build_archive_export_uses_auth_and_schema(self):
        self.ctx.target = 'tvos'
        project = self.inputs / 'tvOS/Unity-iPhone.xcodeproj'
        project.mkdir(parents=True)
        self.ctx.p = {'from_job': 'source-job', 'project': 'tvOS/Unity-iPhone.xcodeproj', 'scheme': 'Unity-iPhone',
                      'export_method': 'app-store-connect'}
        kinds.k_build(self.ctx)
        kinds.k_archive(self.ctx)
        commands = self.commands('xcodebuild')
        self.assertEqual(len(commands), 3)
        for cmd in commands:
            self.assertIn('-allowProvisioningUpdates', cmd)
            self.assertIn('-authenticationKeyID', cmd)
        for cmd in commands[:2]:
            self.assertEqual(cmd[cmd.index('-destination') + 1], 'generic/platform=tvOS')
            self.assertIn(str(project.resolve()), cmd)
        opts = plistlib.loads(Path(self.ctx.art, 'ExportOptions.plist').read_bytes())
        self.assertEqual(opts, {'method': 'app-store-connect', 'signingStyle': 'automatic', 'destination': 'export', 'teamID': 'ABCDE12345'})
        self.assertIn('tvos', kinds.TARGETS)
        from devkit_hosts import TARGET_PLATFORM
        self.assertEqual(TARGET_PLATFORM['tvos'], 'macos')

    def test_queue_validation_and_no_checkout(self):
        runner = load_runner()
        self.assertIn('mas-pkg', runner.NO_CHECKOUT_KINDS)
        args = type('Args', (), dict(project='example', commit='none', kind='mas-pkg', target='macos',
                                    params=dict(self.ctx.p, entitlement_values={'get-task-allow': True}), requires={}))()
        with patch.object(runner, 'disk_status', return_value={'ready': True}), \
                patch.object(runner, 'save') as save, patch.object(runner.subprocess, 'Popen') as process:
            with self.assertRaises(runner.Fail):
                runner.queue_locked(args)
            save.assert_not_called()
            process.assert_not_called()
