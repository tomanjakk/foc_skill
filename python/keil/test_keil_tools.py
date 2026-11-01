import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import keil_build
from keil_common import build_result, ihex, run_keil
import keil_flash
from keil_flash import flash_result


class KeilTools(unittest.TestCase):
    def test_log_terminal_and_errors(self):
        self.assertIsNone(build_result('compiling...'))
        self.assertEqual(build_result('"Objects/one.axf" - 2 Error(s), 1 Warning(s).')[1:], ('2', '1'))
        self.assertIsNone(flash_result('Erase Done. Programming Done.'))
        self.assertEqual(flash_result('Erase Done. Programming Done. Verify OK. Flash Load finished'), 'success')
        self.assertEqual(flash_result('Erase Failed'), 'failed')

    def test_hex_checksum_and_address(self):
        with tempfile.TemporaryDirectory(prefix='keil test ') as tmp:
            p = Path(tmp) / 'test file.hex'
            p.write_text(':020000040800F2\n:020000000102FB\n:00000001FF\n')
            self.assertEqual(ihex(p), {0x08000000: 1, 0x08000001: 2})
            p.write_text(':020000040800F2\n:020000000102FA\n:00000001FF\n')
            with self.assertRaises(ValueError): ihex(p)

    def test_build_failure_does_not_flash(self):
        with patch.object(keil_flash, 'config', return_value={}), \
             patch.object(keil_flash, 'build', side_effect=RuntimeError('build failed')), \
             patch.object(keil_flash, 'run_keil') as download:
            with self.assertRaisesRegex(RuntimeError, 'build failed'):
                keil_flash.flash()
            download.assert_not_called()

    def test_flash_uses_existing_keil_settings(self):
        image = {'start': 0x08019000, 'end_exclusive': 0x08020000}
        with patch.object(keil_flash, 'config', return_value={}), \
             patch.object(keil_flash, 'build', return_value={'image': image}), \
             patch.object(keil_flash, 'run_keil', return_value=('success', 'flash.log')) as download:
            keil_flash.flash()
            download.assert_called_once_with({}, '-f', 'flash', flash_result)

    def test_timeout_and_paths_with_spaces(self):
        class FakeProcess:
            returncode = 0
            def __init__(self, command, **kwargs):
                self.command = command
                self.asserted = command[0].endswith('UV 4.exe') and command[2].endswith('project x.uvprojx')
                if not self.asserted: raise AssertionError(command)
            def poll(self): return 0
            def communicate(self): return (b'', None)
        with tempfile.TemporaryDirectory(prefix='keil test ') as tmp:
            p = Path(tmp); c = {'log_dir':p, 'uv4_executable':p/'UV 4.exe',
                               'project':p/'project x.uvprojx', 'target':'Target A', 'timeout_seconds':0.01}
            with patch('keil_common.subprocess.Popen', FakeProcess):
                with self.assertRaisesRegex(RuntimeError, '超时'): run_keil(c, '-r', 'build', build_result)

    def test_existing_axf_cannot_pass_failed_build(self):
        with tempfile.TemporaryDirectory(prefix='keil test ') as tmp:
            p=Path(tmp); axf=p/'old.axf';axf.write_bytes(b'old');axf.with_suffix('.hex').write_bytes(b'old')
            c={'log_dir':p,'project':p/'project.uvprojx','target':'T','axf':axf,'object_dir':p}
            (p/'last_success.json').write_text('{}')
            with patch.object(keil_build,'config',return_value=c), patch.object(keil_build,'project_info',return_value={}), \
                 patch.object(keil_build,'run_keil',return_value=(('old.axf','1','0'),p/'build.log')):
                with self.assertRaisesRegex(RuntimeError,'编译失败'): keil_build.build()
            self.assertFalse((p/'last_success.json').exists())


if __name__ == '__main__': unittest.main()
