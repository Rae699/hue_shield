import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TvqaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/configure_tvqa.py'
        if not path.exists():
            raise AssertionError('The safe tvQuickActions merge builder must exist')
        spec = importlib.util.spec_from_file_location('tvqa', path)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def base(self):
        return {'intents': [{'a': 'intents', 'b': 'intents', 'c': json.dumps([
            {'id': 17, 'uid': 'existing-intent', 'uri': 'intent:#Intent;action=example.action;end'}])}],
            'trigger_actions': [{'a': 'trigger_actions', 'b': 'trigger_actions', 'c': json.dumps([
                {'id': 24, 'uid': 'trigger_actions_screen_on', 'isEnabled': True,
                 'title': 'Existing wake', 'constraintList': [],
                 'actions': {'1': {'a': 'intent', 'b': 'existing-intent', 'custom': 7}},
                 'customField': 'preserve'},
                {'id': 33, 'uid': 'other-macro', 'isEnabled': True,
                 'actions': {}, 'constraintList': []}])}],
            'unrelated': [{'secret': 'SYNTHETIC_TEST_ONLY'}]}

    def rows(self, obj, name):
        return json.loads(obj[name][0]['c'])

    def merged(self, base, patch):
        out = json.loads(json.dumps(base))
        for name in ('intents', 'trigger_actions'):
            old = {r['id']: r for r in self.rows(base, name)}
            old.update({r['id']: r for r in self.rows(patch, name)})
            out[name][0]['c'] = json.dumps(list(old.values()))
        return out

    def test_only_scoped_records_and_no_id_collisions(self):
        base = self.base()
        patch, report = self.mod.build_patch(base)
        self.assertEqual(set(patch), {'intents', 'trigger_actions'})
        self.assertEqual(len(self.rows(patch, 'intents')), 3)
        self.assertEqual(len(self.rows(patch, 'trigger_actions')), 3)
        self.assertNotIn(17, [r['id'] for r in self.rows(patch, 'intents')])
        self.assertNotIn(33, [r['id'] for r in self.rows(patch, 'trigger_actions')])
        self.assertNotIn('SYNTHETIC_TEST_ONLY', json.dumps(patch))
        self.assertEqual(report['lifecycleRules'], 3)

    def test_preserves_prior_wake_actions_and_fields(self):
        base = self.base()
        original = json.dumps(base, sort_keys=True)
        patch, _ = self.mod.build_patch(base)
        wake = next(r for r in self.rows(patch, 'trigger_actions') if r['uid'] == 'trigger_actions_screen_on')
        self.assertEqual(wake['actions']['1'], {'a': 'intent', 'b': 'existing-intent', 'custom': 7})
        self.assertEqual(wake['customField'], 'preserve')
        self.assertEqual(wake['id'], 24)
        self.assertTrue(wake['isEnabled'])
        self.assertEqual(len(wake['actions']), 2)
        self.assertEqual(json.dumps(base, sort_keys=True), original)

    def test_repeated_generation_does_not_duplicate_actions(self):
        base = self.base()
        first, _ = self.mod.build_patch(base)
        merged = self.merged(base, first)
        second, _ = self.mod.build_patch(merged)
        self.assertEqual(first, second)

    def test_rejects_constraints_without_changing_them(self):
        base = self.base()
        rows = self.rows(base, 'trigger_actions')
        rows[0]['constraintList'] = [{'type': 'example_time_constraint'}]
        base['trigger_actions'][0]['c'] = json.dumps(rows)
        with self.assertRaisesRegex(ValueError, 'constraint'):
            self.mod.build_patch(base)

    def test_duplicate_ids_rejected(self):
        base = self.base()
        rows = self.rows(base, 'intents')
        rows.append({'id': 17, 'uid': 'duplicate'})
        base['intents'][0]['c'] = json.dumps(rows)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.mod.build_patch(base)

    def test_disabled_saved_actions_are_not_silently_reenabled(self):
        base = self.base()
        records = self.rows(base, 'trigger_actions')
        records[0]['isEnabled'] = False
        base['trigger_actions'][0]['c'] = json.dumps(records)
        with self.assertRaisesRegex(ValueError, 'disabled'):
            self.mod.build_patch(base)

    def test_optional_scene_scope_and_emby_are_explicit(self):
        patch, _ = self.mod.build_patch(self.base(), scenes=True,
            media_apps=['example.player'], launcher='example.launcher', emby=True)
        macros = self.rows(patch, 'trigger_actions')
        self.assertEqual(len(macros), 9)
        playback = [r for r in macros if any(c['type'].startswith('playback_state_') for c in r['constraintList'])]
        self.assertEqual(len(playback), 3)
        self.assertTrue(all(r['constraintList'][0]['extras'][0]['data'] == 'example.player' for r in playback))
        uris = [r['uri'] for r in self.rows(patch, 'intents')]
        self.assertTrue(all('component=dev.huesync.relay/.SceneReceiver' in u for u in uris))
        self.assertTrue(any('.EMBY_ENTER;' in u for u in uris))
        with self.assertRaises(ValueError):
            self.mod.build_patch(self.base(), emby=True)

    def test_intent_uri_injection_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.build_patch(self.base(), scenes=True, media_apps=['example.player;end'])


if __name__ == '__main__':
    unittest.main()
