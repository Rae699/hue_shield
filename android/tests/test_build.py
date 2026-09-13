"""Portable build configuration and signing boundary tests; no SDK is needed."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class BuildTest(unittest.TestCase):
    def setUp(self):
        path = ROOT / "build.py"
        self.assertTrue(path.is_file(), "portable build script is present")
        spec = importlib.util.spec_from_file_location("relay_build", path)
        self.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.build)

    def test_help_is_available_without_sdk_or_signing_key(self):
        result = subprocess.run([sys.executable, str(ROOT / "build.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in ("--sdk", "--test-only", "--keystore", "--password-env", "--generate-key"):
            self.assertIn(option, result.stdout)

    def test_sdk_resolves_standard_android_34_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sdk_tools = root / "build-tools" / "34.0.0"
            sdk_tools.mkdir(parents=True)
            jar = root / "platforms" / "android-34" / "android.jar"
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"fixture")
            for name in ("aapt2", "d8", "zipalign", "apksigner"):
                (sdk_tools / name).touch(mode=0o755)
            self.assertEqual(self.build.resolve_sdk(root), (jar.resolve(), sdk_tools.resolve()))
            (sdk_tools / "d8").unlink()
            with self.assertRaisesRegex(ValueError, "d8"):
                self.build.resolve_sdk(root)

    def test_missing_sdk_reports_actionable_requirement(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Android.*34"):
                self.build.resolve_sdk(Path(folder))

    def test_signing_key_must_be_outside_shipped_tree_even_through_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "package"
            package.mkdir()
            key = package / "local.jks"
            with self.assertRaisesRegex(ValueError, "outside"):
                self.build.validate_keystore(key, package)
            link = Path(folder) / "linked"
            link.symlink_to(package, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "outside"):
                self.build.validate_keystore(link / "local.jks", package)
            self.assertEqual(self.build.validate_keystore(Path(folder) / "private" / "local.jks", package),
                             (Path(folder) / "private" / "local.jks").resolve())

    def test_password_is_only_passed_as_environment_reference(self):
        with patch.dict(os.environ, {"RELAY_TEST_PASSWORD": "test-password-with-spaces"}):
            self.assertEqual(self.build.password_reference("RELAY_TEST_PASSWORD"), "env:RELAY_TEST_PASSWORD")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "RELAY_TEST_PASSWORD"):
                self.build.password_reference("RELAY_TEST_PASSWORD")
        with self.assertRaisesRegex(ValueError, "environment variable"):
            self.build.password_reference("not a variable")

    def test_java_version_accepts_11_and_newer_and_rejects_older_or_unknown(self):
        for text in ('javac 11.0.27', 'javac 17.0.15', 'javac 25-ea'):
            self.build.validate_java_version(text)
        for text in ('javac 1.8.0_401', 'javac 10', 'unknown'):
            with self.assertRaisesRegex(ValueError, "Java 11"):
                self.build.validate_java_version(text)


if __name__ == "__main__":
    unittest.main()
