import hashlib
from pathlib import Path
import tempfile
import unittest
from reload_symbols import reload_symbols


class ReloadSymbolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.axf = Path(self.tmp.name) / 'file with spaces.axf'
        self.axf.write_bytes(b'firmware')
        self.digest = hashlib.sha256(b'firmware').hexdigest()

    def backend(self, stale, expected=True, changed=True):
        state = {'loaded': True, 'axf_path': str(self.axf if expected else self.axf.parent / 'other.axf'),
                 'stale': stale, 'generation': 4, 'fingerprint': {'sha256': self.digest}}
        calls = []
        def request(info, method, path, payload=None):
            calls.append((method, path))
            if method == 'POST':
                state['stale'] = False
                if changed: state['generation'] += 1
            return dict(state)
        return request, calls

    def test_stale_reloads_and_clean_skips(self):
        request, calls = self.backend(True)
        self.assertEqual(reload_symbols({}, request, self.axf)['status'], 'reloaded')
        self.assertIn(('POST', '/api/symbols/reload-sources'), calls)
        request, calls = self.backend(False)
        self.assertEqual(reload_symbols({}, request, self.axf)['status'], 'already_current')
        self.assertNotIn(('POST', '/api/symbols/reload-sources'), calls)

    def test_mismatched_source_is_not_changed(self):
        request, calls = self.backend(True, expected=False)
        with self.assertRaises(ValueError): reload_symbols({}, request, self.axf)
        self.assertNotIn(('POST', '/api/symbols/reload-sources'), calls)

    def test_generation_and_fingerprint_are_verified(self):
        request, _ = self.backend(True, changed=False)
        with self.assertRaises(RuntimeError): reload_symbols({}, request, self.axf)
        request, _ = self.backend(False)
        self.axf.write_bytes(b'new content')
        with self.assertRaises(RuntimeError): reload_symbols({}, request, self.axf)

    def test_busy_is_reported_without_retry(self):
        request, calls = self.backend(True)
        def busy(info, method, path, payload=None):
            if method == 'POST':
                calls.append((method, path))
                raise RuntimeError('busy')
            return request(info, method, path, payload)
        with self.assertRaisesRegex(RuntimeError, 'busy'): reload_symbols({}, busy, self.axf)
        self.assertEqual(calls.count(('POST', '/api/symbols/reload-sources')), 1)


if __name__ == '__main__': unittest.main()
