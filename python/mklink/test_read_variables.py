import unittest
from read_variables import read_variables


class Tests(unittest.TestCase):
    def backend(self, state='running', stale=False):
        calls = []
        channels = ['old']
        def request(info, method, path, data=None):
            calls.append((method, path, data))
            if path == '/api/symbols/status': return {'loaded': True, 'stale': stale}
            if path == '/api/dash/superwatch/status': return {'state': state, 'items': [{'name': n} for n in channels]}
            if path == '/api/dash/superwatch/add': channels.append(data['name']); return {}
            if path == '/api/dash/superwatch/latest':
                return {'running': True, 'age_seconds': .01, 'sample': {'sequence': 1,
                    'channels': [{'name': n} for n in channels], 'values': [42] * len(channels)}}
            if path == '/api/device/watch': return {'rows': [{'name': n, 'value': 42} for n in data['names']]}
            raise AssertionError(path)
        return request, calls

    def test_running_uses_shared_snapshot_and_adds_missing(self):
        request, calls = self.backend()
        result = read_variables({}, request, ['old', 'FOC.Vbus'])
        self.assertEqual(result['values'], {'old': 42, 'FOC.Vbus': 42})
        self.assertEqual([c[2]['name'] for c in calls if c[1].endswith('/add')], ['FOC.Vbus'])
        self.assertNotIn('/api/device/watch', [c[1] for c in calls])

    def test_stopped_uses_watch(self):
        request, calls = self.backend(state='stopped')
        self.assertEqual(read_variables({}, request, ['FOC.Vbus'])['source'], 'watch')
        self.assertNotIn('/api/dash/superwatch/add', [c[1] for c in calls])

    def test_stale_symbols_do_not_read(self):
        request, calls = self.backend(stale=True)
        with self.assertRaisesRegex(RuntimeError, 'reload_symbols'): read_variables({}, request, ['FOC.Vbus'])
        self.assertEqual(len(calls), 1)

    def test_unexpected_state_and_bad_names(self):
        request, _ = self.backend(state='paused')
        with self.assertRaises(RuntimeError): read_variables({}, request, ['FOC.Vbus'])
        with self.assertRaises(ValueError): read_variables({}, request, ['x', 'x'])


if __name__ == '__main__': unittest.main()
