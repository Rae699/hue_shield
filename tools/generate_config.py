#!/usr/bin/env python3
"""Construct a PRIVATE HTTP Shortcuts ZIP from the user's local configuration.

No discovery, pairing, device communication or network operation is performed.
The generator has no dependency on an existing HTTP Shortcuts export.
"""
import argparse
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'contract.json').read_text(encoding='utf-8'))
PUBLIC_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, 'dev.huesync.relay')


def public_id(label):
    return str(uuid.uuid5(PUBLIC_NAMESPACE, label))


def object_fields(value, required, optional=(), label='configuration'):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(label + ': missing, unknown or invalid fields')


def validated_text(value, label):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 4096:
        raise ValueError(label + ': a nonempty value is required')
    if any(ord(c) < 33 or ord(c) > 126 for c in value) or any(c in value for c in '{}<>'):
        raise ValueError(label + ': unsafe characters are not allowed')
    if value.lower().startswith(('your_', 'your-', 'replace_', 'replace-')) or any(x in value.lower() for x in ('placeholder', 'changeme')):
        raise ValueError(label + ': replace the example value')
    return value


def host(value, label):
    value = validated_text(value, label)
    if len(value) > 253 or '%' in value or value.endswith('.') or value.lower().endswith('.invalid'):
        raise ValueError(label + ': enter the device hostname or IP address only')
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if re.fullmatch(r'[0-9.]+', value):
            raise ValueError(label + ': invalid IP address') from None
        if not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', part) for part in value.split('.')):
            raise ValueError(label + ': enter the device hostname or IP address only')
        return value.lower()
    if address.is_unspecified or address.is_multicast:
        raise ValueError(label + ': invalid device address')
    return '[' + str(address) + ']' if address.version == 6 else str(address)


def fingerprint(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', value) or len(set(value.lower())) < 2:
        raise ValueError(label + ': a verified 64-hex SHA-256 certificate fingerprint is required')
    return value.lower()


def resource_id(value, label):
    value = validated_text(value, label)
    try:
        identifier = uuid.UUID(value)
    except ValueError:
        raise ValueError(label + ': a Hue v2 resource UUID is required') from None
    if str(identifier) != value.lower() or identifier.int == 0:
        raise ValueError(label + ': a Hue v2 resource UUID is required')
    return str(identifier)


def minute(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value):
        raise ValueError(label + ': expected HH:MM in 24-hour time')
    h, m = map(int, value.split(':'))
    return h * 60 + m


def validate(config):
    object_fields(config, ['ownSyncBox'], ['optionalScenes'])
    sync = config['ownSyncBox']
    object_fields(sync, ['host', 'token', 'certificateFingerprint', 'input'], label='ownSyncBox')
    if type(sync['input']) is not int or sync['input'] not in range(1, 5):
        raise ValueError('ownSyncBox.input: choose an integer from 1 through 4')
    settings = {'syncHost': host(sync['host'], 'ownSyncBox.host'),
                'token': validated_text(sync['token'], 'ownSyncBox.token'),
                'syncPin': fingerprint(sync['certificateFingerprint'], 'ownSyncBox.certificateFingerprint'),
                'input': 'input' + str(sync['input'])}
    optional = config.get('optionalScenes', {'enabled': False})
    object_fields(optional, ['enabled'], ['ownBridge', 'scenes', 'readGuard'], label='optionalScenes')
    if type(optional['enabled']) is not bool:
        raise ValueError('optionalScenes.enabled: expected true or false')
    settings['scenesEnabled'] = optional['enabled']
    if not optional['enabled']:
        return settings
    object_fields(optional, ['enabled', 'ownBridge', 'scenes', 'readGuard'], label='optionalScenes')
    bridge, scenes, guard = optional['ownBridge'], optional['scenes'], optional['readGuard']
    object_fields(bridge, ['host', 'applicationKey', 'certificateFingerprint'], label='optionalScenes.ownBridge')
    object_fields(scenes, ['cinema', 'pause', 'read'], label='optionalScenes.scenes')
    object_fields(guard, ['sensorResourceId', 'start', 'end', 'luxThreshold'], ['readFailOpen'], label='optionalScenes.readGuard')
    start, end = minute(guard['start'], 'readGuard.start'), minute(guard['end'], 'readGuard.end')
    if start == end:
        raise ValueError('readGuard: start and end must differ')
    threshold = guard['luxThreshold']
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 65535:
        raise ValueError('readGuard.luxThreshold: expected a finite Hue light_level value from 0 to 65535')
    fail_open = guard.get('readFailOpen', True)
    if type(fail_open) is not bool:
        raise ValueError('readGuard.readFailOpen: expected true or false')
    settings.update(bridgeHost=host(bridge['host'], 'ownBridge.host'),
                    bridgeKey=validated_text(bridge['applicationKey'], 'ownBridge.applicationKey'),
                    bridgePin=fingerprint(bridge['certificateFingerprint'], 'ownBridge.certificateFingerprint'),
                    sceneIds={k: resource_id(v, 'scenes.' + k) for k, v in scenes.items()},
                    sensorId=resource_id(guard['sensorResourceId'], 'readGuard.sensorResourceId'),
                    start=start, end=end, threshold=threshold, failOpen=fail_open)
    return settings


def template(name, **values):
    text = (ROOT / 'templates' / (name + '.js')).read_text(encoding='utf-8')
    for key, value in values.items():
        text = text.replace('@@' + key.upper() + '@@', str(value))
    if '@@' in text:
        raise ValueError('unresolved script template')
    return text.strip()


def result_code(kind, body='', ok=False):
    # The nonce is request-local input from the Tasker plugin, never persistent state.
    return "var nonce = '';\ntry { nonce = getVariable(" + json.dumps(CONTRACT['nonceVariable']) + "); } catch (error) {}\n" + \
        'var out = {kind:' + json.dumps(kind) + ',nonce:nonce,ok:' + str(ok).lower() + ',ready:false,active:false,video:false};\n' + \
        'try {\n' + body + '\n} catch (error) { out.ok = false; out.ready = false; }\nsetResult(JSON.stringify(out));'


def base_shortcut(kind):
    identity = CONTRACT['shortcuts'][kind]
    return dict(identity, hidden=True, launcherShortcut=False, executionType='app', method='GET',
                url='', bodyContent='', timeout=8000, delay=0, repetitionInterval=0,
                waitForInternet=False, runInForegroundService=True, followRedirects=False,
                acceptCookies=False, acceptAllCertificates=False, requestBodyType='custom',
                contentType='application/json', excludeFromHistory=True, excludeFromFileSharing=True,
                codeOnPrepare='', codeOnSuccess='', codeOnFailure='',
                responseHandling={'successOutput': 'none', 'failureOutput': 'none', 'uiType': 'toast'}, headers=[])


def scripting(kind, body, ok=False):
    s = base_shortcut(kind)
    s.update(executionType='scripting', codeOnPrepare=result_code(kind, body, ok))
    return s


def http_shortcut(kind, method, url, body, pin, success, failure='', **security):
    s = base_shortcut(kind)
    s.update(method=method, url=url, bodyContent=body, certificateFingerprint=pin,
             codeOnSuccess=result_code(kind, success), codeOnFailure=result_code(kind, failure), **security)
    return s


def window(settings):
    return template('window', start=settings['start'], end=settings['end'])


def build_import(config):
    settings = validate(config)
    origin = 'https://' + settings['syncHost']
    success = 'out.ok = !!(response && response.statusCode >= 200 && response.statusCode < 300);'
    security = {'authentication': 'bearer', 'authToken': settings['token']}
    requests = [http_shortcut('PROBE', 'GET', origin + '/api/v1/', '', settings['syncPin'],
                             template('probe', input=json.dumps(settings['input'])), **security),
                http_shortcut('START', 'PUT', origin + '/api/v1/execution',
                              json.dumps({'syncActive': True, 'mode': 'video', 'hdmiSource': settings['input']}),
                              settings['syncPin'], success, **security),
                http_shortcut('STOP', 'PUT', origin + '/api/v1/execution', '{"syncActive":false}',
                              settings['syncPin'], success, **security)]
    variables = []
    if not settings['scenesEnabled']:
        requests.extend(scripting(kind, '', ok=True) for kind in CONTRACT['shortcuts'] if kind not in ('PROBE', 'START', 'STOP'))
    else:
        bridge_origin = 'https://' + settings['bridgeHost'] + '/clip/v2/resource/'
        headers = [{'key': 'hue-application-key', 'value': settings['bridgeKey']}]
        scene_success = success + "\nif (out.ok && response.body && response.body.trim()) { var p = JSON.parse(response.body); if (Array.isArray(p.errors) && p.errors.length) out.ok = false; }"
        for index, scene in enumerate(('cinema', 'pause', 'read')):
            kind = 'READ_RECALL' if scene == 'read' else scene.upper()
            on_success = scene_success + "\nif (out.ok) { setVariable('hsr_scene_index', '" + str(index) + "');"
            if scene == 'cinema':
                on_success += " setVariable('hsr_last_cinema_ms', String(Date.now()));"
            on_success += ' }'
            recall = http_shortcut(kind, 'PUT', bridge_origin + 'scene/' + settings['sceneIds'][scene],
                                   '{"recall":{"action":"active"}}', settings['bridgePin'], on_success, headers=headers)
            if scene != 'read':
                # End the top-level request before I/O when outside the window.
                # HTTP Shortcuts completes the session on abort. Scene callbacks
                # are acknowledged by the relay even if no result is forwarded.
                recall['codeOnPrepare'] = window(settings) + '\nif (!inWindow) {\n' + result_code(kind, ok=True) + '\nabort();\n}'
            requests.append(recall)
        read_script = template('read-check', window=window(settings), threshold=json.dumps(settings['threshold']),
                               fail_open=json.dumps(settings['failOpen']))
        requests.append(http_shortcut('READ_CHECK', 'GET', bridge_origin + 'light_level/' + settings['sensorId'],
                                      '', settings['bridgePin'], read_script, read_script, headers=headers))
        # READ is routed by the native controller into READ_CHECK then READ_RECALL.
        # This reserved entry completes harmlessly if accidentally launched alone.
        read = scripting('READ', '', ok=True)
        read['description'] = 'Use the relay READ broadcast. The relay serializes the sensor check and scene recall.'
        requests.append(read)
        cycle = http_shortcut('CYCLE', 'PUT', bridge_origin + 'scene/{{hsr_cycle_target}}',
                              '{"recall":{"action":"active"}}', settings['bridgePin'],
                              scene_success + "\nif (out.ok) { var i = getVariable('hsr_cycle_index'); setVariable('hsr_scene_index', i); if (i === '0') setVariable('hsr_last_cinema_ms', String(Date.now())); }",
                              headers=headers)
        cycle['codeOnPrepare'] = "var current = parseInt(getVariable('hsr_scene_index'), 10);\n" + \
            'if (!Number.isFinite(current) || current < -1 || current > 2) current = -1;\n' + \
            'var targets = ' + json.dumps([settings['sceneIds'][x] for x in ('cinema', 'pause', 'read')]) + ';\n' + \
            "var next = (current + 1) % targets.length; setVariable('hsr_cycle_target', targets[next]); setVariable('hsr_cycle_index', String(next));"
        requests.append(cycle)
        # Double-curly named URL placeholders are local; prepare sets the Cycle
        # target and index for this execution. Only shared scene state persists.
        variables = [{'id': public_id('variable:' + key), 'key': key, 'value': value}
                     for key, value in [('hsr_scene_index', '-1'), ('hsr_last_cinema_ms', '0')]]
    return {'version': 91, 'compatibilityVersion': 90,
            'categories': [{'id': public_id('category:relay'), 'name': 'Hue Sync Relay', 'shortcuts': requests}],
            'variables': variables}


def write_import(document, config_path):
    output_dir = config_path.parent / 'generated'
    if output_dir.is_symlink():
        raise ValueError('generated directory must not be a symbolic link')
    output_dir.mkdir(mode=0o700, exist_ok=True)
    output_dir.chmod(0o700)
    output = output_dir / 'hue-relay-http-shortcuts.PRIVATE.zip'
    fd, temporary = tempfile.mkstemp(prefix='.hue-relay-', suffix='.zip', dir=output_dir)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w+b') as file:
            with zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('shortcuts.json', json.dumps(document, ensure_ascii=False, separators=(',', ':')))
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path, help='your config.local.json file; generated/ is created beside it')
    args = parser.parse_args()
    try:
        config_path = args.config.expanduser().resolve()
        config = json.loads(config_path.read_text(encoding='utf-8'))
        document = build_import(config)
        output = write_import(document, config_path)
    except (OSError, ValueError, TypeError):
        # Do not include exception values, paths, JSON snippets, hostnames or credentials.
        print('Configuration rejected or output unavailable. Check field names, host-only addresses, credentials, verified certificate pins and optional-scene settings.', file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
