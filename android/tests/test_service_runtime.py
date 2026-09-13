"""Execute actual RelayService lifecycle behavior without Android, an SDK or devices."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest

ANDROID = Path(__file__).resolve().parents[1]


class ServiceRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("relay_build_runtime", ANDROID / "build.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        cls.java = build.java_tool("java")
        javac = build.java_tool("javac")
        cls.folder = tempfile.TemporaryDirectory(prefix="relay-service-runtime-")
        cls.addClassCleanup(cls.folder.cleanup)
        # Keep fixture sources out of build.py's independent pure-controller Java glob.
        fixtures = ANDROID / "tests" / "runtime_fixtures"
        sources = []
        for fixture in fixtures.rglob("*.java.fixture"):
            source = Path(cls.folder.name) / "sources" / fixture.relative_to(fixtures).with_suffix("")
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(fixture.read_text())
            sources.append(source)
        sources += [ANDROID / "src" / "dev" / "huesync" / "relay" / name
                    for name in ("NativeController.java", "EmbyAudioGate.java", "RelayService.java")]
        compiled = subprocess.run([javac, "--release", "8", "-d", cls.folder.name, *map(str, sources)],
                                  text=True, capture_output=True)
        if compiled.returncode:
            raise AssertionError("Runtime fixture did not compile:\n" + compiled.stderr)

    def run_scenario(self, name):
        result = subprocess.run([self.java, "-cp", self.folder.name,
                                 "dev.huesync.relay.RelayServiceRuntimeTest", name],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_read_callback_guard_and_recall_work_in_fixture(self):
        self.run_scenario("nativeReadCallbacks")

    def test_boot_keeps_20_second_probe_delay(self):
        self.run_scenario("bootDelay")

    def test_fresh_emby_event_still_applies_debounced_cinema(self):
        self.run_scenario("freshEmby")

    def test_null_intent_reconciles_awake_and_remains_sticky(self):
        self.run_scenario("awakeRestart")

    def test_current_sleep_overrides_remembered_awake_state(self):
        self.run_scenario("asleepRestart")

    def test_first_read_event_also_reconciles_sync(self):
        self.run_scenario("freshRead")

    def test_restart_does_not_replay_remembered_emby_scene(self):
        self.run_scenario("rememberedEmby")

    def test_persisted_dispatch_lease_serializes_recreation_and_rejects_stale_callback(self):
        self.run_scenario("outstandingLease")

    def test_failed_dispatch_clears_lease_before_shutdown(self):
        self.run_scenario("failedDispatchCleanup")

    def test_old_completion_releases_restart_lease_for_awake_probe(self):
        self.run_scenario("completedAwakeLease")

    def test_old_completion_releases_restart_lease_for_current_sleep(self):
        self.run_scenario("completedAsleepLease")

    def test_healthy_idle_has_one_minute_callback_without_idle_spin(self):
        self.run_scenario("idleMinute")

    def test_sleep_cancels_recurring_maintenance(self):
        self.run_scenario("sleepCancelsMinute")
