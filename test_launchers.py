"""Check launcher argument quoting and propagation of installer failures."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class LauncherTests(unittest.TestCase):
    def test_arguments_and_exit_status(self):
        extension = '.bat' if os.name == 'nt' else '.sh'
        for feature in ('skill-toggle', 'show-all-usage'):
            with self.subTest(feature=feature), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / 'scripts with spaces'
                folder.mkdir()
                launcher = folder / (feature + extension)
                shutil.copy2(ROOT / launcher.name, launcher)
                (folder / (feature + '.py')).write_text(
                    'import json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(37)\n')
                args = ['installation with spaces', '--check', '--restore']
                result = subprocess.run([str(launcher), *args], cwd=directory,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertEqual(json.loads(result.stdout), args)


if __name__ == '__main__':
    unittest.main()
