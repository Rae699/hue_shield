#!/usr/bin/env python3
"""Build a checked public archive using only files inside this package."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'contract.json').read_text())['version']
APK = f'releases/hue-sync-relay-{VERSION}.apk'
TOP = {'README.md', 'LICENSE', 'NOTICE', 'contract.json', 'config.example.json', '.gitignore', 'SHA256SUMS',
       'AGENTS.md', 'AI_SETUP.md', 'CONTRIBUTING.md', 'SECURITY.md', 'llms.txt'}
ANDROID = {'android/AndroidManifest.xml', 'android/build.py', 'android/BUILDING.md', 'android/.gitignore'}
GITHUB = {'.github/workflows/ci.yml', '.github/ISSUE_TEMPLATE/bug_report.yml',
          '.github/PULL_REQUEST_TEMPLATE.md'}
GITHUB_DIRECTORIES = {'.github', '.github/workflows', '.github/ISSUE_TEMPLATE'}
RULES = {'android/src': {'.java'}, 'android/tests': {'.java', '.py'}, 'tools': {'.py'},
         'tests': {'.py', '.mjs', '.js'}, 'templates': {'.js', '.json'}, 'docs': {'.md', '.json'}}
LIMIT, TOTAL = 8 * 1024 * 1024, 50 * 1024 * 1024
PATTERNS = {
    'private-key': rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----',
    'jwt': rb'\beyJ[A-Za-z0-9_+/=-]{8,}\.[A-Za-z0-9_+/=-]{8,}\.[A-Za-z0-9_+/=-]{8,}',
    'user-path': rb'/' + rb'Users/[^\s/\x22\x27<>]+',
    'mac-address': rb'(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])',
}


class ReleaseError(ValueError):
    pass


def reject(kind, name):
    raise ReleaseError(f'{kind}: {name}')


def safe_name(name):
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and not re.match(r'^[A-Za-z]:', name) and '\\' not in name and not any(x in {'..', '.'} for x in name.split('/'))


def forbidden(name):
    parts = PurePosixPath(name).parts
    return any(p.lower() in {'private', 'generated', 'backup', 'backups', 'ownbackups', 'config.local.json'}
               or p.lower().startswith('.env') for p in parts) or PurePosixPath(name).suffix.lower() in {'.pem', '.jks', '.keystore', '.p12'}


def allowed(name, directory=False):
    if forbidden(name):
        return False
    if directory:
        return name in {'android', 'releases'} | GITHUB_DIRECTORIES or any(name == p or name.startswith(p + '/') for p in RULES)
    runtime_fixture = name.startswith('android/tests/runtime_fixtures/') and name.endswith('.java.fixture')
    return runtime_fixture or name in TOP | ANDROID | GITHUB | {APK} or any(name.startswith(p + '/') and PurePosixPath(name).suffix in ext for p, ext in RULES.items())


def scan(data, name, budget, depth=0):
    budget[0] += len(data)
    if len(data) > LIMIT or budget[0] > TOTAL:
        reject('size-limit', name)
    text = data.replace(b'\0', b'')
    for kind, pattern in PATTERNS.items():
        if re.search(pattern, text):
            reject(kind, name)
    for match in re.finditer(rb'(?i)\bBearer[ \t]+([A-Za-z0-9._~+/=-]{8,})', text):
        value = match[1].upper()
        if not value.startswith((b'REPLACE', b'YOUR_', b'EXAMPLE', b'PLACEHOLDER')) and value not in {b'ACCESS_TOKEN', b'AUTHENTICATION', b'AUTHORIZATION', b'CREDENTIALS'}:
            reject('bearer-token', name)
    for match in re.finditer(rb'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', text):
        a, b, c, d = map(int, match[0].split(b'.'))
        if max(a, b, c, d) < 256 and (a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)):
            reject('private-ip', name)
    if data.startswith(b'PK') or name.lower().endswith(('.zip', '.apk')):
        if depth >= 3:
            reject('archive-depth', name)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                seen = set()
                for item in z.infolist():
                    child = name + '!' + item.filename
                    if not safe_name(item.filename.rstrip('/')) or forbidden(item.filename) or item.filename in seen:
                        reject('archive-path', child)
                    seen.add(item.filename)
                    if stat.S_ISLNK(item.external_attr >> 16):
                        reject('symlink', child)
                    if item.file_size > LIMIT or budget[0] + item.file_size > TOTAL:
                        reject('size-limit', child)
                    scan(z.read(item), child, budget, depth + 1)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            reject('invalid-archive', name)


def check_example(data):
    try:
        obj = json.loads(data)
        own = obj['ownSyncBox']
        if not all(k in own for k in ('host', 'token', 'certificateFingerprint')):
            raise ValueError()
        def visit(value):
            if isinstance(value, dict):
                for key, val in value.items():
                    if key == 'host' and (not isinstance(val, str) or not val.endswith('.invalid') or '/' in val):
                        raise ValueError()
                    if key in {'token', 'applicationKey', 'certificateFingerprint'} and (not isinstance(val, str) or not val.startswith('REPLACE_')):
                        raise ValueError()
                    visit(val)
            elif isinstance(value, list):
                for val in value:
                    visit(val)
        visit(obj)
    except (ValueError, KeyError, TypeError):
        reject('example-config', 'config.example.json')


def verify_archive(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or any(not safe_name(n) for n in names):
                raise ValueError()
            manifest = {}
            for line in z.read('SHA256SUMS').decode('ascii').splitlines():
                digest, name = line.split('  ', 1)
                if not re.fullmatch('[0-9a-f]{64}', digest) or name in manifest:
                    raise ValueError()
                manifest[name] = digest
            if set(manifest) != set(names) - {'SHA256SUMS'}:
                raise ValueError()
            for name, digest in manifest.items():
                if hashlib.sha256(z.read(name)).hexdigest() != digest:
                    raise ValueError()
    except (ValueError, KeyError, UnicodeError, zipfile.BadZipFile):
        reject('checksum-verification', 'release.zip')


def build_release(root=ROOT, output=None, source_only=False):
    root = Path(root)
    if root.is_symlink():
        reject('symlink', 'package-root')
    root = root.resolve()
    default_name = f'hue-sync-relay-source-{VERSION}.zip' if source_only else f'hue-sync-community-{VERSION}.zip'
    output = Path(output) if output else root.parent / default_name
    try:
        output.resolve().relative_to(root)
        inside_root = True
    except ValueError:
        inside_root = False
    if output.is_symlink() or inside_root:
        reject('output-path', 'release.zip')
    payload, budget = {}, [0]
    for base, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                reject('symlink', rel)
            # A Git checkout or worktree pointer may contain private remotes and
            # history. Skip it before reading or traversing; links still reject.
            if rel == '.git' or name in {'__pycache__', '.DS_Store'} or path.suffix == '.pyc':
                if name in directories:
                    directories.remove(name)
                continue
            if not allowed(rel, path.is_dir()):
                reject('path', rel)
            if path.is_dir():
                continue
            if not stat.S_ISREG(path.stat().st_mode):
                reject('path', rel)
            if source_only and rel == APK:
                continue
            if path.stat().st_size > LIMIT:
                reject('size-limit', rel)
            data = path.read_bytes()
            if source_only:
                try:
                    data.decode('utf-8')
                except UnicodeDecodeError:
                    reject('binary-source-file', rel)
                if b'\0' in data:
                    reject('binary-source-file', rel)
            scan(data, rel, budget)
            payload[rel] = data
    required = {'config.example.json'}
    if source_only:
        required.update({'README.md', 'contract.json', 'android/AndroidManifest.xml'})
        has_java = any(name.startswith('android/src/') and name.endswith('.java') for name in payload)
    else:
        required.add(APK)
        has_java = True
    if not required.issubset(payload) or not has_java:
        reject('missing-required-file', 'package-root')
    check_example(payload['config.example.json'])
    payload.pop('SHA256SUMS', None)
    payload['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(payload.items())).encode()
    with tempfile.NamedTemporaryFile(prefix='.hue-release-', suffix='.zip', dir=output.parent, delete=False) as f:
        temporary = Path(f.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(payload.items()):
                z.writestr(name, data)
        verify_archive(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source-only', action='store_true',
                        help='Package repository source and documentation; omit the optional release APK.')
    args = parser.parse_args()
    try:
        build_release(output=args.output, source_only=args.source_only)
    except (ReleaseError, OSError) as error:
        parser.exit(1, f'Release rejected: {error if isinstance(error, ReleaseError) else "filesystem-error"}\n')
    print('Release archive created; member checksums verified.')
