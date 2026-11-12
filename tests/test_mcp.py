import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scopereceipt.core import report, scan
from scopereceipt.mcp_server import PROTOCOL_VERSION, Server


def request(identifier, method, params=None):
    msg = {'jsonrpc': '2.0', 'id': identifier, 'method': method}
    if params is not None:
        msg['params'] = params
    return msg


def handshake():
    return [request(1, 'initialize', {
        'protocolVersion': PROTOCOL_VERSION, 'capabilities': {},
        'clientInfo': {'name': 'test-client', 'version': '1.0'},
    }), {'jsonrpc': '2.0', 'method': 'notifications/initialized'}]


def call(identifier, name, args=None):
    return request(identifier, 'tools/call', {'name': name, 'arguments': args or {}})


def payload(response):
    return json.loads(response['result']['content'][0]['text'])


class MCPTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.docs = self.root / 'docs'
        self.docs.mkdir()
        (self.docs / 'notes.md').write_bytes('你好\nsecond\nthird\n'.encode('utf-8'))
        self.state = self.root / 'receipts'
        scan(self.docs, self.state)

    def exchange(self, messages):
        wire = '\n'.join(json.dumps(m, ensure_ascii=False) for m in messages) + '\n'
        process = subprocess.run(
            [sys.executable, '-m', 'scopereceipt.mcp_server', '--state', str(self.state)],
            input=wire.encode('utf-8'), capture_output=True, timeout=15,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode('utf-8'))
        self.assertEqual(process.stderr, b'')
        return [json.loads(line) for line in process.stdout.splitlines()]

    def test_real_stdio_partial_to_complete(self):
        responses = self.exchange(handshake() + [
            request(2, 'tools/list'), call(3, 'scope_inventory'),
            call(4, 'scope_read', {'path': 'notes.md', 'start': 1, 'end': 1}),
            call(5, 'scope_report'),
            call(6, 'scope_read', {'path': 'notes.md', 'start': 2, 'end': 3}),
            call(7, 'scope_report'),
        ])
        self.assertEqual(responses[0]['result']['protocolVersion'], PROTOCOL_VERSION)
        self.assertEqual({t['name'] for t in responses[1]['result']['tools']},
                         {'scope_inventory', 'scope_read', 'scope_report'})
        self.assertNotIn('source_path', payload(responses[2]))
        self.assertEqual(payload(responses[3])['text'], '你好\n')
        self.assertEqual(payload(responses[4])['status'], 'INCOMPLETE')
        self.assertEqual(payload(responses[4])['files'][0]['missing_ranges'], [[2, 3]])
        self.assertEqual(payload(responses[6])['status'], 'COMPLETE')

    def test_invalid_calls_do_not_count(self):
        responses = self.exchange(handshake() + [
            call(2, 'scan', {'source': '.'}),
            call(3, 'scope_read', {'path': 'notes.md', 'start': True}),
            call(4, 'scope_read', {'path': '../secret.txt'}),
            call(5, 'scope_read', {'path': 'notes.md', 'state': 'elsewhere'}),
            call(6, 'scope_report'),
        ])
        self.assertEqual(responses[1]['error']['code'], -32602)
        self.assertEqual(responses[2]['error']['code'], -32602)
        self.assertTrue(responses[3]['result']['isError'])
        self.assertEqual(responses[4]['error']['code'], -32602)
        self.assertEqual(payload(responses[5])['covered_units'], 0)

    def test_notification_cannot_execute_read(self):
        notification = call(2, 'scope_read', {'path': 'notes.md'})
        del notification['id']
        responses = self.exchange(handshake() + [notification, call(3, 'scope_report')])
        self.assertEqual(len(responses), 2)
        self.assertEqual(payload(responses[1])['covered_units'], 0)

    def test_inventory_does_not_count_as_read(self):
        responses = self.exchange(handshake() + [call(2, 'scope_inventory'), call(3, 'scope_report')])
        self.assertEqual(payload(responses[2])['covered_units'], 0)

    def test_scope_change_requires_restart(self):
        server = Server(self.state)
        for message in handshake():
            server.handle(message)
        scan(self.docs, self.state)
        response, event = server.handle(call(2, 'scope_read', {'path': 'notes.md'}))
        self.assertTrue(response['result']['isError'])
        self.assertIsNone(event)

    def test_failed_transport_does_not_count(self):
        class FailedFlush(io.BytesIO):
            def flush(self):
                raise BrokenPipeError('closed client')
        server = Server(self.state)
        for message in handshake():
            server.handle(message)
        wire = json.dumps(call(2, 'scope_read', {'path': 'notes.md'})).encode() + b'\n'
        with self.assertRaises(BrokenPipeError):
            server.serve(io.BytesIO(wire), FailedFlush())
        self.assertEqual(report(self.state)['covered_units'], 0)

    def test_parse_error_recovers(self):
        server = Server(self.state)
        output = io.BytesIO()
        wire = b'not json\n' + json.dumps(request(2, 'ping')).encode() + b'\n'
        server.serve(io.BytesIO(wire), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[0]['error']['code'], -32700)
        self.assertEqual(responses[1]['result'], {})

    def test_no_tool_calls_before_handshake(self):
        response, event = Server(self.state).handle(call(1, 'scope_read', {'path': 'notes.md'}))
        self.assertEqual(response['error']['code'], -32600)
        self.assertIsNone(event)

