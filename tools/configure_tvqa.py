#!/usr/bin/env python3
"""Create a minimal tvQuickActions 3.7 Merge import from YOUR fresh export.

Never installs anything. Existing lifecycle actions are preserved. The output
can contain those existing actions, so it is private, like the input backup.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'contract.json').read_text())
MAX_EXPORT = 8 * 1024 * 1024
LIFECYCLE = [('trigger_actions_screen_on', 'SYNC_START'),
             ('trigger_actions_screen_off', 'SYNC_STOP'),
             ('trigger_actions_power_on', 'SYNC_BOOT')]
DEFAULT_APPS = ['org.moonfin.androidtv', 'tv.emby.embyatv',
                'com.google.android.youtube.tv', 'ar.tvplayer.tv', 'org.siloserver.silo']


def public_uid(kind):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
        'https://hue-sync-relay.example.invalid/community/v1/tvqa/' + kind))


def rows(base, name):
    if name not in base:
        return []
    wrapped = base[name]
    if not isinstance(wrapped, list) or len(wrapped) != 1 or not isinstance(wrapped[0], dict):
        raise ValueError('Unsupported tvQuickActions export section: ' + name)
    value = json.loads(wrapped[0].get('c', 'null'))
    if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
        raise ValueError('Unsupported tvQuickActions row schema: ' + name)
    ids, uids = set(), set()
    for row in value:
        rid, uid = row.get('id'), row.get('uid')
        if type(rid) is not int or rid < 1 or not isinstance(uid, str) or not uid:
            raise ValueError('Invalid tvQuickActions ID: ' + name)
        if rid in ids or uid in uids:
            raise ValueError('Refusing duplicate tvQuickActions IDs: ' + name)
        ids.add(rid)
        uids.add(uid)
    return value


def action(uid):
    return {'a': 'intent', 'b': uid, 'e': 0, 'f': '', 'g': '', 'h': 0,
            'i': -1, 'j': 0, 'k': 300, 'l': 300}


def package_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', value):
        raise ValueError('Invalid Android package name')
    return value


def constraint(kind, package):
    return {'type': kind, 'extras': [{'id': 'extra_package_name', 'data': package_name(package)}]}


def build_patch(base, scenes=False, media_apps=None, launcher=None, emby=False):
    if not isinstance(base, dict):
        raise ValueError('Expected a tvQuickActions export object')
    if emby and not scenes:
        raise ValueError('Emby scene fallback requires scenes to be enabled')
    if (media_apps or launcher) and not scenes:
        raise ValueError('Media/launcher scene options require --scenes')
    apps = [package_name(p) for p in (media_apps or DEFAULT_APPS)] if scenes else []
    if launcher:
        package_name(launcher)
    old_intents, old_macros = rows(base, 'intents'), rows(base, 'trigger_actions')
    by_intent = {r['uid']: r for r in old_intents}
    by_macro = {r['uid']: r for r in old_macros}
    next_intent = max([r['id'] for r in old_intents] + [0])
    next_macro = max([r['id'] for r in old_macros] + [0])
    intents, macros = [], []
    kinds = ['SYNC_START', 'SYNC_STOP', 'SYNC_BOOT']
    if scenes:
        kinds += ['CINEMA', 'PAUSE', 'READ', 'CYCLE']
    if emby:
        kinds += ['EMBY_ENTER', 'EMBY_EXIT']
    for kind in kinds:
        uid = public_uid('intent/' + kind)
        existing = by_intent.get(uid)
        if existing:
            expected = CONTRACT['actionPrefix'] + kind
            if expected not in existing.get('uri', ''):
                raise ValueError('Existing community intent identity has incompatible content')
            rid = existing['id']
        else:
            next_intent += 1
            rid = next_intent
        intents.append({'id': rid, 'uid': uid, 'title': 'Hue Relay - ' + kind.replace('_', ' ').title(),
            'icon': 'gmd_lightbulb_outline', 'target': 'BROADCAST_RECEIVER',
            'uri': 'intent:#Intent;action=' + CONTRACT['actionPrefix'] + kind +
                   ';launchFlags=0x20;component=' + CONTRACT['receiver'] + ';end',
            'non_exported': False, 'sendToRemote': False, 'remoteAddress': '', 'templateType': 'NONE'})

    def make_macro(uid, kind, title='', constraints=None, lifecycle=False):
        nonlocal next_macro
        existing = by_macro.get(uid)
        if existing:
            macro = deepcopy(existing)
            if lifecycle and macro.get('constraintList'):
                raise ValueError('Existing lifecycle rule has constraints; review it manually before generating this patch')
            if lifecycle and macro.get('isEnabled') is not True and macro.get('actions'):
                raise ValueError('Existing lifecycle rule is disabled with saved actions; review and enable or clear it manually')
            if not lifecycle and macro.get('constraintList') != (constraints or []):
                raise ValueError('Existing community scene scope differs; review or remove that community rule before regenerating')
        else:
            next_macro += 1
            macro = {'id': next_macro, 'uid': uid, 'title': title,
                     'icon': '' if lifecycle else 'gmd_lightbulb_outline',
                     'constraintList': constraints or [], 'actions': {}}
        actions = macro.setdefault('actions', {})
        if not isinstance(actions, dict) or any(not re.fullmatch(r'[1-9][0-9]*', k) for k in actions):
            raise ValueError('Unsupported lifecycle action map; configure manually')
        target = public_uid('intent/' + kind)
        if not any(isinstance(a, dict) and a.get('a') == 'intent' and a.get('b') == target for a in actions.values()):
            index = str(max([int(k) for k in actions] + [0]) + 1)
            actions[index] = action(target)
        macro['isEnabled'] = True
        macros.append(macro)

    for uid, kind in LIFECYCLE:
        make_macro(uid, kind, lifecycle=True)
    if scenes:
        for state, kind in [('playing', 'CINEMA'), ('paused', 'PAUSE'), ('stopped', 'PAUSE')]:
            make_macro(public_uid('macro/' + state), kind, 'Hue Relay - Video ' + state,
                       [constraint('playback_state_' + state, p) for p in dict.fromkeys(apps)])
        if launcher:
            make_macro(public_uid('macro/launcher'), 'READ', 'Hue Relay - Launcher Read',
                       [constraint('constraint_app_foreground', launcher)])
    if emby:
        for state, kind in [('foreground', 'EMBY_ENTER'), ('not_foreground', 'EMBY_EXIT')]:
            make_macro(public_uid('macro/emby/' + state), kind, 'Hue Relay - Emby ' + state,
                       [constraint('constraint_app_' + state, 'tv.emby.embyatv')])
    patch = {name: [{'a': name, 'b': name, 'c': json.dumps(content, separators=(',', ':'))}]
             for name, content in [('intents', intents), ('trigger_actions', macros)]}
    report = {'lifecycleRules': 3, 'intents': len(intents), 'optionalSceneRules': len(macros) - 3,
              'preservesExistingLifecycleActions': True, 'requiresMerge': True}
    return patch, report


def read_export(path):
    with zipfile.ZipFile(path) as archive:
        matches = [i for i in archive.infolist() if i.filename == 'data.json']
        if len(matches) != 1 or matches[0].file_size > MAX_EXPORT:
            raise ValueError('Expected one reasonably sized data.json in the native tvQuickActions ZIP')
        value = json.loads(archive.read(matches[0]))
    if not isinstance(value, dict):
        raise ValueError('Invalid tvQuickActions export')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True, help='Your fresh native tvQuickActions export ZIP')
    parser.add_argument('--output', type=Path, default=ROOT / 'generated/tvqa-community-merge.zip')
    parser.add_argument('--scenes', action='store_true')
    parser.add_argument('--media-app', action='append')
    parser.add_argument('--launcher-package')
    parser.add_argument('--emby-fallback', action='store_true')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Output already exists; choose a new --output name')
        patch, report = build_patch(read_export(args.base), scenes=args.scenes,
            media_apps=args.media_app, launcher=args.launcher_package, emby=args.emby_fallback)
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(prefix='.tvqa-', dir=args.output.parent)
        try:
            os.close(fd)
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('data.json', json.dumps(patch, separators=(',', ':')))
            os.chmod(temp, 0o600)
            os.replace(temp, args.output)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        print('Created private Merge import:', args.output)
        print(json.dumps(report))
        print('Review existing competing Hue automations. Restore with Merge, never Overwrite all.')
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError):
        # Never dump input records or exception payloads that might contain secrets.
        print('Could not generate patch. Check the export schema, duplicate IDs, lifecycle constraints, '
              'disabled lifecycle rules with saved actions, community rule scope, package names, '
              'and output path. See docs/SETUP.md.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
