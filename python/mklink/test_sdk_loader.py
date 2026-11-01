import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SdkLoaderTests(unittest.TestCase):
    def test_configured_sdk_wins_over_installed_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('old', 'new'):
                package = root / name / 'mklink'
                package.mkdir(parents=True)
                (package / '__init__.py').write_text('', encoding='utf-8')
                (package / 'runtime.py').write_text(
                    f"version = '{name}'\ndef request(*args): pass\ndef selected_runtime(*args): pass\n", encoding='utf-8')
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "from sdk_loader import load_runtime; print(load_runtime(sys.argv[2]).version)")
            result = subprocess.run([sys.executable, '-c', code, str(root / 'old'), str(root / 'new')],
                                    cwd=Path(__file__).parent, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), 'new')

    def test_preloaded_conflict_fails_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('old', 'new'):
                package = root / name / 'mklink'
                package.mkdir(parents=True)
                (package / '__init__.py').write_text('', encoding='utf-8')
                (package / 'runtime.py').write_text('', encoding='utf-8')
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import mklink; "
                    "from sdk_loader import load_runtime; load_runtime(sys.argv[2])")
            result = subprocess.run([sys.executable, '-c', code, str(root / 'old'), str(root / 'new')],
                                    cwd=Path(__file__).parent, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('其他 MKLink', result.stderr)


if __name__ == '__main__': unittest.main()
