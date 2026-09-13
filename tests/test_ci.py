"""Check CI boundaries and exercise its build orchestration without SDK/network."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/ci.yml'


class CiTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), 'Read-only CI workflow is present')
        self.workflow = WORKFLOW.read_text()

    def program(self):
        block = self.workflow.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        return textwrap.dedent(block)

    def test_workflow_uses_read_only_permissions_and_pinned_official_actions(self):
        self.assertRegex(self.workflow, r'(?m)^permissions:\n  contents: read\n')
        self.assertNotIn('pull_request_target', self.workflow)
        self.assertNotRegex(self.workflow, r'\$\{\{\s*secrets\.')
        self.assertNotIn('upload-artifact', self.workflow)
        self.assertNotIn('contents: write', self.workflow)
        self.assertIn('persist-credentials: false', self.workflow)
        self.assertIn('submodules: false', self.workflow)
        actions = re.findall(r'uses:\s*(\S+)', self.workflow)
        self.assertEqual(len(actions), 4)
        for action in actions:
            self.assertRegex(action, r'^actions/(checkout|setup-python|setup-java|setup-node)@[0-9a-f]{40}$')

    def test_workflow_runs_full_python_suite_and_orchestration_compiles(self):
        self.assertIn("python3 -B -m unittest discover -s tests -p 'test_*.py'", self.workflow)
        compile(self.program(), str(WORKFLOW), 'exec')

    def exercise_build(self, fail=False):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            environment = {'RUNNER_TEMP': folder, 'ANDROID_HOME': str(Path(folder) / 'sdk')}

            def run(command, **kwargs):
                calls.append((command, kwargs))
                if len(calls) == 2 and fail:
                    raise subprocess.CalledProcessError(1, command)

            with patch.dict(os.environ, environment), patch.object(subprocess, 'run', run), redirect_stdout(io.StringIO()):
                if fail:
                    with self.assertRaises(subprocess.CalledProcessError):
                        exec(compile(self.program(), str(WORKFLOW), 'exec'), {})
                else:
                    exec(compile(self.program(), str(WORKFLOW), 'exec'), {})
            self.assertEqual(len(calls), 2)
            sdk_command, sdk_options = calls[0]
            self.assertIn('platforms;android-34', sdk_command)
            self.assertIn('build-tools;34.0.0', sdk_command)
            self.assertTrue(sdk_options['check'])
            self.assertIn('y\n', sdk_options['input'])
            build, options = calls[1]
            self.assertIn('android/build.py', build)
            self.assertIn('--generate-key', build)
            key = Path(build[build.index('--keystore') + 1])
            apk = Path(build[build.index('--output') + 1])
            self.assertEqual(key.parent, apk.parent)
            self.assertTrue(key.relative_to(Path(folder)).parts)
            with self.assertRaises(ValueError):
                key.relative_to(ROOT)
            self.assertFalse(key.parent.exists(), 'Temporary signing key and APK are removed even after failure')
            password_name = build[build.index('--password-env') + 1]
            password = options['env'][password_name]
            self.assertGreaterEqual(len(password), 32)
            self.assertNotIn(password, build)
            self.assertTrue(options['check'])

    def test_build_uses_declared_sdk_and_temporary_signing_inputs(self):
        self.exercise_build()

    def test_build_failure_still_removes_temporary_signing_directory(self):
        self.exercise_build(fail=True)


if __name__ == '__main__':
    unittest.main()
