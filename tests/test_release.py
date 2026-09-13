"""Offline packaging tests; sensitive-looking fixtures are constructed at runtime."""
import ast
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/package_release.py'
spec = importlib.util.spec_from_file_location('release', SCRIPT) if SCRIPT.exists() else None
release = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(release)


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in entries.items():
            z.writestr(name, value)
    return output.getvalue()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(release, 'safe release packager is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'package'
        self.root.mkdir()
        self.output = self.root.parent / 'release.zip'
        self.config = {'ownSyncBox': {'host': 'sync.invalid', 'token': 'REPLACE_TOKEN',
                                    'certificateFingerprint': 'REPLACE_FINGERPRINT'}}
        self.put('config.example.json', json.dumps(self.config))
        self.put('README.md', 'Public instructions')
        self.put('contract.json', json.dumps({'version': release.VERSION}))
        self.put('android/AndroidManifest.xml', '<manifest/>')
        self.put('android/src/example/Relay.java', 'class Relay {}')
        self.put('tools/example.py', 'print("example")')
        self.put(release.APK, archive({'classes.dex': b'synthetic dex'}))

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        return path

    def reject(self, kind):
        with self.assertRaises(release.ReleaseError) as caught:
            release.build_release(self.root, self.output)
        self.assertIn(kind, str(caught.exception))
        self.assertFalse(self.output.exists())
        return str(caught.exception)

    def test_safe_archive_has_verified_exact_manifest_and_ignores_caches(self):
        self.put('tests/__pycache__/ignored.pyc', b'cache')
        self.put('.DS_Store', b'cache')
        self.put('docs/example.md', 'Documentation address: ' + '.'.join(map(str, [192, 0, 2, 8])))
        release.build_release(self.root, self.output)
        release.verify_archive(self.output)
        with zipfile.ZipFile(self.output) as z:
            self.assertIn('SHA256SUMS', z.namelist())
            self.assertNotIn('.DS_Store', z.namelist())
            self.assertFalse(any('__pycache__' in p for p in z.namelist()))
            sums = z.read('SHA256SUMS').decode().splitlines()
            self.assertEqual(len(sums), len(z.namelist()) - 1)

    def test_nested_apk_private_key_rejected_without_echo(self):
        secret = b'-----BEGIN ' + b'PRIVATE KEY-----'
        self.put(release.APK, archive({'assets/data.txt': secret}))
        message = self.reject('private-key')
        self.assertNotIn(secret.decode(), message)
        self.assertIn('assets/data.txt', message)

    def test_nested_zip_bearer_and_jwt_rejected_without_echo(self):
        values = [(b'Bear' + b'er ' + b'x9' * 24, 'bearer-token'),
                  (b'ey' + b'J' + b'a' * 20 + b'.' + b'b' * 20 + b'.' + b'c' * 20, 'jwt')]
        for secret, kind in values:
            with self.subTest(kind=kind):
                nested = archive({'credential.txt': secret})
                self.put(release.APK, archive({'assets/data.zip': nested}))
                self.assertNotIn(secret.decode(), self.reject(kind))

    def test_addresses_user_paths_and_mac_are_rejected(self):
        values = [('.'.join(map(str, [10, 7, 8, 9])), 'private-ip'),
                  ('.'.join(map(str, [172, 16, 4, 1])), 'private-ip'),
                  ('.'.join(map(str, [192, 168, 4, 1])), 'private-ip'),
                  ('/' + 'Users/' + 'fixture-person/file', 'user-path'),
                  (':'.join(['ab', 'cd', 'ef', '12', '34', '56']), 'mac-address')]
        for value, kind in values:
            with self.subTest(kind=kind):
                self.put('README.md', value)
                self.assertNotIn(value, self.reject(kind))

    def test_unknown_and_private_paths_rejected(self):
        for name in ['unexpected.txt', 'config.local.json', '.env', 'generated/output.json',
                     'private/data.txt', 'backups/own.zip', 'docs/key.pem', 'tools/key.jks', 'tools/key.p12']:
            with self.subTest(name=name):
                path = self.put(name, b'do not read')
                self.reject('path')
                path.unlink()
                while path.parent != self.root:
                    path = path.parent
                    if any(path.iterdir()):
                        break
                    path.rmdir()

    def test_unknown_empty_directory_is_rejected(self):
        (self.root / 'unknown').mkdir()
        self.reject('path')

    def test_symlink_file_and_directory_are_rejected(self):
        outside = self.root.parent / 'outside'
        outside.write_bytes(b'must not read target')
        for name, target in [('docs/link.md', outside), ('docs', self.root.parent)]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                path.rmdir()
            path.symlink_to(target)
            self.reject('symlink')
            path.unlink()

    def test_real_example_settings_rejected(self):
        for key, value in [('host', 'device.example.com'), ('token', 'synthetic-value'),
                           ('certificateFingerprint', 'ab' * 32)]:
            original = self.config['ownSyncBox'][key]
            self.config['ownSyncBox'][key] = value
            self.put('config.example.json', json.dumps(self.config))
            self.reject('example-config')
            self.config['ownSyncBox'][key] = original

    def test_output_inside_root_rejected(self):
        self.output = self.root / 'release.zip'
        self.reject('output-path')

    def test_packaging_without_python39_path_api(self):
        # Check our API usage, not pathlib internals: Python 3.12 implements
        # the Python 3.8-compatible relative_to() using is_relative_to().
        tree = ast.parse(SCRIPT.read_text())
        unsupported = [node.lineno for node in ast.walk(tree)
                       if isinstance(node, ast.Attribute) and node.attr == 'is_relative_to']
        self.assertEqual(unsupported, [], 'Packager uses Python 3.9-only Path API at lines ' + str(unsupported))
        release.build_release(self.root, self.output)
        release.verify_archive(self.output)

    def test_nested_traversal_and_expansion_limit_rejected(self):
        for name in ['../escape', '/absolute', 'C:/escape']:
            self.put(release.APK, archive({name: b'x'}))
            self.reject('archive-path')
        self.put(release.APK, archive({'assets/large': b'x' * (8 * 1024 * 1024 + 1)}))
        self.reject('size-limit')

    def test_nested_archive_depth_is_bounded(self):
        data = b'end'
        for _ in range(4):
            data = archive({'nested.zip' if data.startswith(b'PK') else 'end.txt': data})
        self.put(release.APK, data)
        self.reject('archive-depth')

    def test_existing_output_symlink_is_not_followed(self):
        target = self.root.parent / 'untouched'
        target.write_bytes(b'preserve')
        self.output.symlink_to(target)
        with self.assertRaises(release.ReleaseError):
            release.build_release(self.root, self.output)
        self.assertEqual(target.read_bytes(), b'preserve')

    def test_test_source_passes_its_own_content_scanner(self):
        release.scan(Path(__file__).read_bytes(), 'tests/test_release.py', [0])

    def test_hash_verification_detects_changed_member(self):
        release.build_release(self.root, self.output)
        with zipfile.ZipFile(self.output) as z:
            entries = {name: z.read(name) for name in z.namelist()}
        entries['README.md'] = b'changed after packaging'
        self.output.write_bytes(archive(entries))
        with self.assertRaises(release.ReleaseError):
            release.verify_archive(self.output)

    def test_source_archive_works_without_apk_and_checksums_all_members(self):
        (self.root / release.APK).unlink()
        result = release.build_release(self.root, source_only=True)
        self.assertEqual(result.name, f'hue-sync-relay-source-{release.VERSION}.zip')
        release.verify_archive(result)
        with zipfile.ZipFile(result) as z:
            self.assertIn('android/src/example/Relay.java', z.namelist())
            self.assertFalse(any(name.endswith('.apk') for name in z.namelist()))
            self.assertEqual(len(z.read('SHA256SUMS').decode().splitlines()), len(z.namelist()) - 1)
        with self.assertRaises(release.ReleaseError):
            release.build_release(self.root, self.output)

    def test_source_archive_excludes_existing_release_apk(self):
        self.put(release.APK, b'unread binary build output')
        release.build_release(self.root, self.output, source_only=True)
        with zipfile.ZipFile(self.output) as z:
            self.assertNotIn(release.APK, z.namelist())
            self.assertNotIn(release.APK, z.read('SHA256SUMS').decode())

    def test_source_archive_requires_core_documentation_contract_and_java(self):
        required = ['README.md', 'contract.json', 'config.example.json',
                    'android/AndroidManifest.xml', 'android/src/example/Relay.java']
        for name in required:
            with self.subTest(name=name):
                path = self.root / name
                data = path.read_bytes()
                path.unlink()
                with self.assertRaises(release.ReleaseError) as caught:
                    release.build_release(self.root, self.output, source_only=True)
                self.assertIn('missing-required-file', str(caught.exception))
                self.assertFalse(self.output.exists())
                self.put(name, data)

    def test_repository_metadata_allowlist(self):
        names = ['AGENTS.md', 'AI_SETUP.md', 'CONTRIBUTING.md', 'SECURITY.md', 'llms.txt',
                 'docs/ARCHITECTURE.md', '.github/workflows/ci.yml',
                 '.github/ISSUE_TEMPLATE/bug_report.yml', '.github/PULL_REQUEST_TEMPLATE.md']
        for name in names:
            self.put(name, 'Public repository instructions')
        release.build_release(self.root, self.output, source_only=True)
        with zipfile.ZipFile(self.output) as z:
            self.assertTrue(set(names).issubset(z.namelist()))

    def test_unknown_github_paths_rejected(self):
        for name in ['.github/workflows/private.yml', '.github/secret.txt', '.github/private/file.md']:
            with self.subTest(name=name):
                path = self.put(name, 'unexpected')
                self.reject('path')
                path.unlink()
                while path.parent != self.root:
                    path = path.parent
                    if any(path.iterdir()):
                        break
                    path.rmdir()

    def test_git_directory_and_worktree_file_excluded_before_reading(self):
        self.put('.git/config', b'Bear' + b'er ' + b'x9' * 24)
        self.put('.git/objects/private', b'-----BEGIN ' + b'PRIVATE KEY-----')
        release.build_release(self.root, self.output, source_only=True)
        with zipfile.ZipFile(self.output) as z:
            self.assertFalse(any(name.startswith('.git/') for name in z.namelist()))
        for child in (self.root / '.git').rglob('*'):
            if child.is_file():
                child.unlink()
        (self.root / '.git/objects').rmdir()
        (self.root / '.git').rmdir()
        self.put('.git', 'gitdir: private git storage')
        release.build_release(self.root, self.output, source_only=True)
        with zipfile.ZipFile(self.output) as z:
            self.assertNotIn('.git', z.namelist())

    def test_git_and_excluded_apk_symlinks_are_still_rejected(self):
        target = self.root.parent / 'outside'
        target.write_bytes(b'private')
        for name in ['.git', release.APK]:
            with self.subTest(name=name):
                path = self.root / name
                if path.exists():
                    path.unlink()
                path.symlink_to(target)
                with self.assertRaises(release.ReleaseError) as caught:
                    release.build_release(self.root, self.output, source_only=True)
                self.assertIn('symlink', str(caught.exception))
                path.unlink()

    def test_source_archive_rejects_binary_disguised_as_text(self):
        for data in [b'not text\x00payload', b'\xff\xfebinary']:
            with self.subTest(data=data):
                self.put('docs/binary.md', data)
                with self.assertRaises(release.ReleaseError) as caught:
                    release.build_release(self.root, self.output, source_only=True)
                self.assertIn('binary-source-file', str(caught.exception))

    def test_release_names_follow_repository_contract_version(self):
        contract = json.loads((SCRIPT.parent.parent / 'contract.json').read_text())
        self.assertEqual(release.VERSION, contract['version'])
        self.assertEqual(release.APK, f"releases/hue-sync-relay-{contract['version']}.apk")
        result = release.build_release(self.root)
        self.assertEqual(result.name, f"hue-sync-community-{contract['version']}.zip")

    def test_runtime_java_fixture_is_included_and_checksummed(self):
        name = 'android/tests/runtime_fixtures/android/app/Service.java.fixture'
        self.put(name, 'package android.app; public class Service {}')
        release.build_release(self.root, self.output, source_only=True)
        release.verify_archive(self.output)
        with zipfile.ZipFile(self.output) as z:
            self.assertIn(name, z.namelist())
            self.assertIn(name, z.read('SHA256SUMS').decode())

    def test_runtime_fixture_exception_is_limited_to_java_under_fixture_directory(self):
        for name in ['android/tests/Service.java.fixture',
                     'android/src/runtime_fixtures/Service.java.fixture',
                     'android/tests/runtime_fixtures_other/Service.java.fixture',
                     'android/tests/runtime_fixtures/config.json.fixture',
                     'android/tests/runtime_fixtures/Service.fixture']:
            with self.subTest(name=name):
                self.assertFalse(release.allowed(name))

    def test_runtime_java_fixture_still_gets_secret_scan(self):
        self.put('android/tests/runtime_fixtures/Service.java.fixture',
                 b'-----BEGIN ' + b'PRIVATE KEY-----')
        self.reject('private-key')

    def test_extra_apk_is_not_an_allowed_source_file(self):
        self.put('releases/other.apk', b'binary')
        with self.assertRaises(release.ReleaseError) as caught:
            release.build_release(self.root, self.output, source_only=True)
        self.assertIn('path', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
