"""Cross-component checks against the public release contract."""
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ANDROID = "{http://schemas.android.com/apk/res/android}"


class PublicContractTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT.parent / "contract.json").read_text())

    def test_every_shortcut_resolves_to_the_public_id_and_name(self):
        source = ROOT / "src" / Path(*self.contract["package"].split("."))
        self.assertTrue(source.is_dir(), "public Java source is present")
        policy = (source / "RelayPolicy.java").read_text()
        helpers = (source / "NativeShortcutIds.java").read_text()
        for kind, shortcut in self.contract["shortcuts"].items():
            with self.subTest(kind=kind):
                if kind in ("CINEMA", "PAUSE", "READ", "CYCLE"):
                    block = re.search(
                        r'case "' + re.escape(self.contract["actionPrefix"] + kind)
                        + r'":\s*id = "([^"]+)";\s*name = "([^"]+)";', policy)
                    self.assertIsNotNone(block, "scene is explicitly whitelisted")
                    self.assertEqual(block.groups(), (shortcut["id"], shortcut["name"]))
                else:
                    values = re.findall(r'if \("' + kind + r'".equals\(kind\)\) return "([^"]+)";', helpers)
                    self.assertEqual(values, [shortcut["id"], shortcut["name"]])
        all_source = "\n".join(p.read_text() for p in source.glob("*.java"))
        uuids = set(re.findall(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', all_source))
        self.assertEqual(uuids, {s["id"] for s in self.contract["shortcuts"].values()})

    def test_callback_and_nonce_are_consistent(self):
        source = ROOT / "src" / Path(*self.contract["package"].split("."))
        self.assertTrue(source.is_dir(), "public Java source is present")
        dispatch = (source / "TaskerDispatch.java").read_text()
        service = (source / "RelayService.java").read_text()
        self.assertIn('input.putString("' + self.contract["nonceVariable"] + '",request.nonce)', dispatch)
        self.assertIn('"' + self.contract["callbackScheme"] + '://complete/"+request.nonce', dispatch)
        self.assertIn('"' + self.contract["callbackScheme"] + '".equals(uri.getScheme())', service)
        self.assertIn('"' + self.contract["actionPrefix"] + 'COMPLETE"', dispatch)
        for path in source.glob("*.java"):
            self.assertTrue(path.read_text().startswith("package " + self.contract["package"] + ";"))

    def test_manifest_keeps_explicit_receivers_and_no_network_or_activity(self):
        path = ROOT / "AndroidManifest.xml"
        self.assertTrue(path.is_file(), "public manifest is present")
        manifest = ET.parse(path).getroot()
        self.assertEqual(manifest.get("package"), self.contract["package"])
        self.assertEqual(manifest.get(ANDROID + "versionName"), self.contract["version"])
        self.assertEqual(manifest.get(ANDROID + "versionCode"), "1")
        self.assertEqual(manifest.find("application").get(ANDROID + "label"), "Hue Sync Relay Community")
        self.assertEqual([p.get(ANDROID + "name") for p in manifest.findall("uses-permission")],
                         ["android.permission.FOREGROUND_SERVICE"])
        self.assertEqual(manifest.findall(".//activity"), [])
        receivers = manifest.findall(".//receiver")
        self.assertEqual({r.get(ANDROID + "name") for r in receivers}, {".SceneReceiver", ".CompletionReceiver"})
        for receiver in receivers:
            self.assertEqual(receiver.get(ANDROID + "exported"), "true")
            self.assertEqual(receiver.findall("intent-filter"), [])
        self.assertEqual(manifest.find(".//service").get(ANDROID + "exported"), "false")
        self.assertEqual(manifest.find("uses-sdk").get(ANDROID + "minSdkVersion"), "26")
        self.assertEqual(manifest.find("uses-sdk").get(ANDROID + "targetSdkVersion"), "30")
        self.assertEqual(manifest.find("uses-feature").get(ANDROID + "required"), "false")
        self.assertEqual([p.get(ANDROID + "name") for p in manifest.findall("./queries/package")],
                         ["ch.rmy.android.http_shortcuts"])


if __name__ == "__main__":
    unittest.main()
