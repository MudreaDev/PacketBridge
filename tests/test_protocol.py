import unittest
from packetbridge.protocol import control, decode, relay_url


class ProtocolTests(unittest.TestCase):
    def test_coordinates_are_normalized(self):
        data = {'type': 'pointer','window': '123','action': 'down','x': .5,'y': 1}
        self.assertEqual(control(data)['button'], 0)
        for bad in [-.1, 1.1, float('nan'), True, '0']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                control({**data,'x':bad})

    def test_arbitrary_commands_denied(self):
        for kind in ['shell','launch','message','clipboard','upload']:
            with self.assertRaises(ValueError):
                control({'type':kind,'window':'123'})

    def test_no_remote_native_handle_payload(self):
        self.assertEqual(control({'type':'release','hwnd':999}), {'type':'release'})
        with self.assertRaises(ValueError):
            control({'type':'select','window':123})

    def test_key_allowlist(self):
        self.assertEqual(control({'type':'key','window':'1','key':'Enter'})['key'],'Enter')
        with self.assertRaises(ValueError):
            control({'type':'key','window':'1','key':'Meta'})

    def test_text_limits(self):
        for text in ['', 'a'*2049, '\x00', 1]:
            with self.assertRaises(ValueError):
                control({'type':'text','window':'1','text':text})
        control({'type':'text','window':'1','text':'enable\nshow ip int brief'})

    def test_json_validation(self):
        for raw in ['[]','{}','null','a'*17000,b'{}']:
            with self.assertRaises(ValueError):
                decode(raw)

    def test_tls_required_outside_loopback(self):
        self.assertEqual(relay_url('https://example.org/'), 'https://example.org')
        relay_url('http://127.0.0.1:8765')
        for url in ['http://192.168.1.1','http://example.org','https://a/b','https://a#b','file:///tmp/a','https://u:p@a']:
            with self.assertRaises(ValueError):
                relay_url(url)
