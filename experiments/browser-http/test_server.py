"""Small protocol and access-control tests; no browser required."""
import http.client
import json
import threading
import unittest

from server import Bridge, make_server


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge()
        self.server = make_server(self.bridge)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, *, method='GET', data=None, authenticated=True, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        request_headers = {'X-Session-Token': self.bridge.token} if authenticated else {}
        request_headers.update(headers or {})
        connection.request(method, path, body=json.dumps(data) if data is not None else None, headers=request_headers)
        reply = connection.getresponse()
        body = reply.read()
        connection.close()
        return reply.status, body

    def test_token_host_origin_and_asset_allowlist(self):
        self.assertEqual(self.request('/heads', authenticated=False)[0], 403)
        self.assertEqual(self.request('/heads', headers={'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('/heads', headers={'Host': 'example.com'})[0], 403)
        self.assertEqual(self.request('/assets/../../server.py')[0], 404)
        self.assertEqual(self.request('/assets/jsapi.js')[0], 200)
        self.assertEqual(self.request('/heads')[0], 200)

    def test_single_client_and_reply_correlation(self):
        self.assertEqual(self.request('/ready', method='POST', data={'client': 'first'})[0], 200)
        self.assertEqual(self.request('/ready', method='POST', data={'client': 'second'})[0], 409)
        self.assertEqual(self.request('/task', headers={'X-Client-Id': 'second'})[0], 409)
        result = []
        thread = threading.Thread(target=lambda: result.append(self.bridge.rpc('call', timeout=2, name='veuszDescribe', payload='')))
        thread.start()
        status, body = self.request('/task', headers={'X-Client-Id': 'first'})
        self.assertEqual(status, 200)
        task = json.loads(body)
        reply = {'id': task['id'], 'value': 'result', 'elapsed_ms': 1}
        self.assertEqual(self.request('/reply', method='POST', data=reply, headers={'X-Client-Id': 'second'})[0], 409)
        self.assertEqual(self.request('/reply', method='POST', data=reply, headers={'X-Client-Id': 'first'})[0], 200)
        thread.join(3)
        self.assertEqual(result, [('result', 1)])
        self.assertEqual(self.request('/reply', method='POST', data=reply, headers={'X-Client-Id': 'first'})[0], 409)

    def test_browser_failure_reaches_python(self):
        self.assertEqual(self.request('/fatal', method='POST', data={'error': 'script failed'})[0], 200)
        self.assertTrue(self.bridge.ready.is_set())
        with self.assertRaisesRegex(RuntimeError, 'script failed'):
            self.bridge.rpc('call')

    def test_timeout_and_malformed_reply(self):
        with self.assertRaises(TimeoutError):
            self.bridge.rpc('call', timeout=0.01)
        self.assertFalse(self.bridge.pending)
        self.bridge.accept_client('first', 'test')
        self.assertEqual(self.request('/reply', method='POST', data={'id': []}, headers={'X-Client-Id': 'first'})[0], 400)


if __name__ == '__main__':
    unittest.main()
