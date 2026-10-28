import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch as mock

from installed_patch import Asar, MARKER, patch, locate, load_payload


def make_archive(files):
    header = b'{"files":{}}'
    padding = b'\0' * (-len(header) % 4)
    size = 8 + len(header) + len(padding)
    empty = struct.pack('<IIII', 4, size, size - 4, len(header)) + header + padding
    return Asar(empty).rebuild(files)


class InstallerTests(unittest.TestCase):
    def test_linux_and_windows_apply_repeat_restore(self):
        for windows in (False, True):
            with self.subTest(windows=windows), tempfile.TemporaryDirectory() as d:
                resources = Path(d) / 'space in path' / 'resources'
                resources.mkdir(parents=True)
                original = make_archive({
                    'package.json': json.dumps({'version': '0.1.4-nightly.20261028.3824'}).encode(),
                    'apps/server/dist/bin.mjs': b'original runtime',
                    'apps/server/dist/obsolete.js': b'old chunk',
                    'native/keep': b'unchanged platform library'})
                app = resources / 'app.asar'
                app.write_bytes(original)
                target = resources / 'server.asar' if windows else app
                target.write_bytes(original)
                def payload(features):
                    return {'apps/server/dist/bin.mjs': ','.join(sorted(features)).encode()}
                with mock('installed_patch.load_payload', side_effect=payload):
                    patch('skill-toggle', resources.parent, check=True)
                    self.assertEqual(target.read_bytes(), original)
                    self.assertFalse(list(resources.glob('*.bak')))
                    patch('skill-toggle', resources)
                    first = target.read_bytes()
                    patch('skill-toggle', resources)
                    self.assertEqual(target.read_bytes(), first)
                    stale = Asar(target.read_bytes())
                    state = json.loads(stale.read(MARKER))
                    state['payload_revision'] = 'old'
                    target.write_bytes(stale.rebuild({MARKER: json.dumps(state).encode()}))
                    patch('skill-toggle', resources)
                    self.assertEqual(target.read_bytes(), first)
                    patch('show-all-usage', resources)
                    archive = Asar(target.read_bytes())
                    self.assertEqual(archive.read('native/keep'), b'unchanged platform library')
                    self.assertEqual(json.loads(archive.read(MARKER))['features'],
                                     ['show-all-usage', 'skill-toggle'])
                    with self.assertRaises(KeyError):
                        archive.read('apps/server/dist/obsolete.js')
                    if windows:
                        self.assertEqual(app.read_bytes(), original)
                        self.assertEqual(locate(app)[1], target)
                    patch('skill-toggle', resources, restore=True)
                    self.assertEqual(target.read_bytes(), original)

    def test_payload_variants(self):
        for features in ({'skill-toggle'}, {'show-all-usage'}, {'skill-toggle', 'show-all-usage'}):
            data = b'\n'.join(load_payload(features).values())
            self.assertEqual(b'Personal skills' in data, 'skill-toggle' in features)
            self.assertEqual(b'Usage limits unavailable for this provider' in data, 'show-all-usage' in features)
            self.assertEqual(b'reported cost' in data, 'show-all-usage' in features)
            self.assertEqual(b'antigravity/acp/1.3.0' in data, 'show-all-usage' in features)

    def test_invalid_archive_and_version(self):
        with self.assertRaises(ValueError):
            Asar(b'broken')
        with tempfile.TemporaryDirectory() as d:
            app = Path(d) / 'app.asar'
            original = make_archive({'package.json': b'{"version":"future"}'})
            app.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                patch('skill-toggle', app)
            self.assertEqual(app.read_bytes(), original)

    def test_unpack_and_link_metadata_preserved(self):
        archive = Asar(make_archive({'file': b'data'}))
        archive.tree['files']['native'] = {'size': 4, 'unpacked': True}
        archive.tree['files']['alias'] = {'link': 'file'}
        rebuilt = Asar(archive.rebuild({'file': b'changed'}))
        self.assertEqual(rebuilt.node('native'), {'size': 4, 'unpacked': True})
        self.assertEqual(rebuilt.node('alias'), {'link': 'file'})
        self.assertEqual(rebuilt.node('file')['integrity']['hash'],
                         hashlib.sha256(b'changed').hexdigest())


if __name__ == '__main__':
    unittest.main()
