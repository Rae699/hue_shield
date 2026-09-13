"""Pairing safety checks using fake TLS connections; never contacts a device."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CERT = b"synthetic-leaf-certificate-for-unit-tests"
PIN = hashlib.sha256(CERT).hexdigest()
TOKEN = "synthetic-access-token-only-for-unit-tests"


class PairingTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "tools" / "pair_sync_box.py"
        self.assertTrue(path.is_file(), "Pinned local pairing helper is present")
        spec = importlib.util.spec_from_file_location("pairing_under_test", path)
        self.mod = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(ROOT / "tools")] + sys.path):
            spec.loader.exec_module(self.mod)
        self.events, self.calls, self.now = [], [], 0.0

    def tls(self, replies, cert=CERT):
        test = self
        sequence = iter(replies)

        class FakeSocket:
            def getpeercert(self, binary_form=False):
                test.assertTrue(binary_form)
                test.events.append("certificate")
                return cert

            def settimeout(self, timeout):
                test.assertGreater(timeout, 0)

            def close(self):
                test.events.append("closed")

        def connect(connection):
            test.events.append("connected")
            connection.sock = FakeSocket()

        def request(connection, method, url, body=None, headers=None):
            test.assertEqual(test.events[-1], "certificate")
            test.calls.append((method, url, json.loads(body), headers))
            test.events.append("request")

        def getresponse(connection):
            status, value = next(sequence)

            class Response:
                def read(self, limit):
                    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
                    return raw[:limit]

            response = Response()
            response.status = status
            return response

        return (patch.object(self.mod.http.client.HTTPSConnection, "connect", connect),
                patch.object(self.mod.http.client.HTTPSConnection, "request", request),
                patch.object(self.mod.http.client.HTTPSConnection, "getresponse", getresponse))

    def invoke(self, directory, replies, *, pin=PIN, device="syncbox.local", cert=CERT, extra=()):
        patches = self.tls(replies, cert)
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ["--host", device, "--fingerprint", pin, "--output", str(Path(directory) / "config.local.json"), *extra]
        with patches[0], patches[1], patches[2], redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.mod.main(args)
        return result, stdout.getvalue() + stderr.getvalue()

    def test_bad_pin_sends_no_http_request_and_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.invoke(directory, [], cert=b"different-synthetic-certificate")
            self.assertEqual(code, 1)
            self.assertEqual(self.calls, [])
            self.assertNotIn("request", self.events)
            self.assertFalse((Path(directory) / "config.local.json").exists())
            self.assertNotIn("different-synthetic-certificate", output)

    def test_success_writes_private_generator_compatible_config_without_printing_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.invoke(directory, [(200, {"accessToken": TOKEN})], extra=("--input", "4"))
            self.assertEqual(code, 0, output)
            path = Path(directory) / "config.local.json"
            config = json.loads(path.read_text())
            self.assertEqual(config, {"ownSyncBox": {"host": "syncbox.local", "token": TOKEN,
                "certificateFingerprint": PIN, "input": 4}, "optionalScenes": {"enabled": False}})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.mod.validate_config(config)
            self.assertNotIn(TOKEN, output)
            self.assertNotIn(PIN, output)
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(self.calls[0][:3], ("POST", "/api/v1/registrations",
                {"appName": "HueSyncRelay", "instanceName": "AndroidTV"}))
            self.assertEqual(self.calls[0][3], {"Content-Type": "application/json", "Connection": "close"})

    def test_existing_output_is_rejected_before_any_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.local.json"
            path.write_text("existing private configuration")
            code, _ = self.invoke(directory, [])
            self.assertEqual(code, 1)
            self.assertEqual(self.events, [])
            self.assertEqual(path.read_text(), "existing private configuration")

    def test_explicit_pending_code_retries_then_stores_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(self.mod.time, "sleep") as sleep:
            code, output = self.invoke(directory, [(403, {"code": 16}), (200, {"accessToken": TOKEN})])
            self.assertEqual(code, 0, output)
            self.assertEqual(sleep.call_args.args, (1,))
            self.assertEqual(len(self.calls), 2)
            self.assertIn("3 seconds", output)

    def test_pending_code_is_bounded_to_45_seconds(self):
        def sleep(seconds):
            self.now += seconds
        with tempfile.TemporaryDirectory() as directory, patch.object(self.mod.time, "monotonic", lambda: self.now), \
                patch.object(self.mod.time, "sleep", sleep):
            code, output = self.invoke(directory, [(403, {"code": 16})] * 46)
            self.assertEqual(code, 1)
            self.assertLessEqual(self.now, 45)
            self.assertEqual(len(self.calls), 45)
            self.assertFalse((Path(directory) / "config.local.json").exists())

    def test_unknown_error_and_http_failure_never_echo_response_or_retry(self):
        for status, reply in [(403, {"code": 99, "message": TOKEN}),
                              (500, {"accessToken": TOKEN}),
                              (200, {"code": "16", "message": TOKEN}),
                              (200, {"code": False, "accessToken": TOKEN}),
                              (200, TOKEN.encode()), (302, {"location": TOKEN})]:
            with self.subTest(status=status, reply_type=type(reply).__name__), tempfile.TemporaryDirectory() as directory, \
                    patch.object(self.mod.time, "sleep") as sleep:
                before = len(self.calls)
                code, output = self.invoke(directory, [(status, reply)])
                self.assertEqual(code, 1)
                self.assertEqual(len(self.calls), before + 1)
                self.assertFalse(sleep.called)
                self.assertNotIn(TOKEN, output)

    def test_invalid_host_or_pin_is_rejected_before_connection(self):
        for device in ("https://syncbox.local", "syncbox.local:443", "syncbox.local/path", "name@syncbox.local", "syncbox.local\r\nInjected:yes"):
            with self.subTest(device=device), tempfile.TemporaryDirectory() as directory:
                code, _ = self.invoke(directory, [], device=device)
                self.assertEqual(code, 1)
                self.assertEqual(self.events, [])
        with tempfile.TemporaryDirectory() as directory:
            code, _ = self.invoke(directory, [], pin="unverified")
            self.assertEqual(code, 1)
            self.assertEqual(self.events, [])

    def test_ipv6_output_remains_compatible_with_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.invoke(directory, [(200, {"accessToken": TOKEN})], device="2001:db8::10")
            self.assertEqual(code, 0, output)
            config = json.loads((Path(directory) / "config.local.json").read_text())
            self.assertEqual(config["ownSyncBox"]["host"], "2001:db8::10")
            self.mod.validate_config(config)

    def test_connection_error_and_deep_json_are_sanitized(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.mod.PinnedConnection, "connect", side_effect=OSError(TOKEN)):
            output = io.StringIO()
            with redirect_stdout(output):
                code = self.mod.main(["--host", "syncbox.local", "--fingerprint", PIN,
                                      "--output", str(Path(directory) / "config.local.json")])
            self.assertEqual(code, 1)
            self.assertNotIn(TOKEN, output.getvalue())
            self.assertFalse((Path(directory) / "config.local.json").exists())
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.invoke(directory, [(200, b"[" * 1500 + b"]" * 1500)])
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", output)

    def test_symlink_output_is_rejected_before_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "existing.json"
            target.write_text("existing private configuration")
            (Path(directory) / "config.local.json").symlink_to(target)
            code, _ = self.invoke(directory, [])
            self.assertEqual(code, 1)
            self.assertEqual(self.events, [])
            self.assertEqual(target.read_text(), "existing private configuration")


if __name__ == "__main__":
    unittest.main()
