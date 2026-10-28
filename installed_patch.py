"""Install the captured T3 server/UI bundles while retaining platform native files."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
MARKER = 't3-local-features.json'
SUPPORTED = {'0.1.4-nightly.20261028.3824'}
BLOCK = 4194304


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Asar:
    def __init__(self, data):
        self.data = data
        if len(data) < 16:
            raise ValueError('Truncated ASAR archive.')
        magic, size, payload, length = struct.unpack('<IIII', data[:16])
        if magic != 4 or size != payload + 4 or length > size - 8 or 8 + size > len(data):
            raise ValueError('Invalid ASAR header.')
        self.offset = 8 + size
        self.tree = json.loads(data[16:16 + length])

    def node(self, path):
        node = self.tree
        for part in path.split('/'):
            node = node['files'][part]
        return node

    def read(self, path):
        meta = self.node(path)
        if 'offset' not in meta or meta.get('unpacked'):
            raise ValueError(f'Expected a packed file: {path}')
        start = self.offset + int(meta['offset'])
        end = start + meta['size']
        if start < self.offset or end > len(self.data):
            raise ValueError(f'Invalid ASAR file range: {path}')
        return self.data[start:end]

    def rebuild(self, replacements):
        tree = copy.deepcopy(self.tree)
        for path, data in replacements.items():
            node = tree
            for part in path.split('/')[:-1]:
                node = node.setdefault('files', {}).setdefault(part, {'files': {}})
            node['files'][path.split('/')[-1]] = {'size': len(data)}
        chunks = []
        offset = 0
        def walk(node, prefix=''):
            nonlocal offset
            for name, meta in node['files'].items():
                path = prefix + name
                if 'files' in meta:
                    walk(meta, path + '/')
                elif not meta.get('unpacked') and 'link' not in meta:
                    data = replacements[path] if path in replacements else self.read(path)
                    meta['offset'] = str(offset)
                    meta['size'] = len(data)
                    if path in replacements:
                        meta['integrity'] = {'algorithm': 'SHA256', 'hash': digest(data),
                            'blockSize': BLOCK,
                            'blocks': [digest(data[i:i + BLOCK]) for i in range(0, len(data), BLOCK)]}
                    offset += len(data)
                    chunks.append(data)
        walk(tree)
        header = json.dumps(tree, separators=(',', ':'), ensure_ascii=False).encode()
        padding = b'\0' * (-len(header) % 4)
        size = 8 + len(header) + len(padding)
        return struct.pack('<IIII', 4, size, size - 4, len(header)) + header + padding + b''.join(chunks)


def locate(path):
    path = path.expanduser().resolve()
    if path.is_file() and path.name in ('app.asar', 'server.asar'):
        resources = path.parent
    else:
        resources = path if (path / 'app.asar').is_file() else path / 'resources'
    app = resources / 'app.asar'
    if not app.is_file():
        raise ValueError('Pass the installed app folder, its resources folder, or app.asar.')
    server = resources / 'server.asar'
    return app, server if server.is_file() else app


def replace_atomic(path, data):
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, name)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_payload(features):
    manifest_bytes = (ROOT / 'payload/manifest.json').read_bytes()
    expected = (ROOT / 'payload/manifest.sha256').read_text().strip()
    if digest(manifest_bytes) != expected:
        raise ValueError('Payload manifest checksum mismatch.')
    manifest = json.loads(manifest_bytes)
    variant = '+'.join(sorted(features))
    files = manifest['variants'][variant]
    replacements = {}
    with zipfile.ZipFile(ROOT / 'payload/runtime.zip') as archive:
        for name, sha in files.items():
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Invalid payload path.')
            data = archive.read(sha)
            if digest(data) != sha:
                raise ValueError(f'Payload checksum mismatch: {name}')
            replacements['apps/server/dist/' + name] = data
    return replacements


def patch(feature, install, check=False, restore=False):
    app_path, target = locate(install)
    data = target.read_bytes()
    archive = Asar(data)
    try:
        state = json.loads(archive.read(MARKER))
    except KeyError:
        state = None
    if restore:
        if state is None:
            raise ValueError('No installer backup is recorded in this archive.')
        name = state['backup']
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Invalid backup filename.')
        backup = target.parent / name
        original = backup.read_bytes()
        if digest(original) != state['original_sha256']:
            raise ValueError('Backup checksum mismatch; archive left unchanged.')
        if not check:
            replace_atomic(target, original)
        print(('Would restore: ' if check else 'Restored: ') + str(backup))
        return
    package = json.loads(Asar(app_path.read_bytes()).read('package.json'))
    # shortcut: captured builds only; rebuild and revalidate payloads for newer T3 releases.
    known_local = (ROOT / 'payload/local-original.sha256').read_text().strip()
    if package.get('version') not in SUPPORTED and digest(data) != known_local and not (
        state and state.get('original_sha256') == known_local
    ):
        raise ValueError('Unsupported T3 version: ' + str(package.get('version')) +
                         '. Supported release: ' + ', '.join(sorted(SUPPORTED)))
    archive.node('apps/server/dist/bin.mjs')
    if state:
        features = set(state['features'])
        if not features <= {'skill-toggle', 'show-all-usage'}:
            raise ValueError('Unknown feature state.')
    else:
        features = set()
        # Preserve features already installed on the captured local app.
        if digest(data) == known_local:
            features = {'skill-toggle', 'show-all-usage'}
    revision = (ROOT / 'payload/manifest.sha256').read_text().strip()
    if feature in features and state and state.get('payload_revision') == revision:
        print(f'{feature}: already installed.')
        return
    features.add(feature)
    replacements = load_payload(features)
    original_sha = digest(data)
    if state is None:
        state = {'backup': target.name + '.original-' + original_sha[:16] + '.bak',
                 'original_sha256': original_sha}
    state['features'] = sorted(features)
    state['payload_revision'] = revision
    replacements[MARKER] = (json.dumps(state, indent=2) + '\n').encode()
    # Remove obsolete hashed bundles; preserve every other archive subtree and native sidecar.
    archive.node('apps/server')['files']['dist'] = {'files': {}}
    output = archive.rebuild(replacements)
    verified = Asar(output)
    for name, content in replacements.items():
        if verified.read(name) != content:
            raise ValueError('Rebuilt archive failed verification.')
    if check:
        print('Compatible. Would install ' + ', '.join(sorted(features)) + ' into ' + str(target))
        return
    backup = target.parent / state['backup']
    if backup.exists():
        if digest(backup.read_bytes()) != state['original_sha256']:
            raise ValueError('Existing backup does not match; archive left unchanged.')
    else:
        if state['original_sha256'] != original_sha:
            raise ValueError('Original backup is missing; archive left unchanged.')
        with backup.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    if target.read_bytes() != data:
        raise ValueError('The app changed during patching; retry with T3 and its updater closed.')
    replace_atomic(target, output)
    print('Installed: ' + ', '.join(sorted(features)) + '\nBackup: ' + str(backup) +
          '\nRestart T3 Code to load the changes.')


def main(feature):
    parser = argparse.ArgumentParser(description='Patch the installed T3 Code desktop app. Close T3 first.')
    parser.add_argument('install', type=Path, help='Installed app folder or resources folder')
    parser.add_argument('--check', action='store_true', help='Validate without changing the installation')
    parser.add_argument('--restore', action='store_true', help='Restore the original archive (undo both features)')
    args = parser.parse_args()
    try:
        patch(feature, args.install, args.check, args.restore)
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile) as error:
        print('Error: ' + str(error), file=sys.stderr)
        sys.exit(1)
