"""Bootstrap regressions: interrupted HTTP streams, Range, cache and integrity."""
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).resolve().parents[1] / 'infra/model/start.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status, self.headers = status, headers or {}

class Interrupted(Response):
    def read(self, size=-1):
        if self.tell():
            raise OSError('connection dropped')
        return super().read(7)

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'model.gguf'
        self.data = b'valid pinned model'
        self.model = {'file': self.path.name, 'size_bytes': len(self.data), 'sha256': hashlib.sha256(self.data).hexdigest()}
        self.lock = {'model_files': [self.model], 'alias': 'test', 'quantization_repository': 'test/model', 'model_revision': 'fixed'}
        self.env = patch.dict(os.environ, {'MODEL_STATUS_FILE': str(Path(self.tmp.name) / 'status.json')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_existing_file_verified_once_and_cache_invalidated_on_change(self):
        self.path.write_bytes(self.data)
        self.assertTrue(b.verified(self.path, self.model))
        with patch.object(b, 'hash_file', side_effect=AssertionError('unchanged model must reuse verification')):
            self.assertTrue(b.verified(self.path, self.model))
        self.path.write_bytes(b'x' * len(self.data))
        self.assertFalse(b.verified(self.path, self.model))

    def test_invalid_stamp_rechecks_hash(self):
        self.path.write_bytes(self.data)
        self.path.with_suffix('.gguf.verified.json').write_text('broken')
        self.assertTrue(b.verified(self.path, self.model))

    def test_cached_weights_report_full_size_after_restart(self):
        self.path.write_bytes(self.data)
        with patch.object(b.urllib.request, 'urlopen', side_effect=AssertionError('no download for cached model')):
            self.assertEqual(b.ensure_weights(self.path, self.lock), 'verified_cache')
        status = json.loads(Path(os.environ['MODEL_STATUS_FILE']).read_text())
        self.assertEqual(status['phase'], 'weights_ready')
        self.assertEqual(status['downloaded_bytes'], len(self.data))
        self.assertEqual(status['total_bytes'], len(self.data))
        self.assertEqual(status['percent'], 100)

    def test_download_verified_during_stream_and_atomically_promoted(self):
        with patch.object(b.urllib.request, 'urlopen', return_value=Response(self.data)), patch.object(b, 'hash_file', side_effect=AssertionError('do not reread download')):
            self.assertEqual(b.ensure_weights(self.path, self.lock), 'downloaded_and_verified')
            self.assertTrue(b.verified(self.path, self.model))
        status = json.loads(Path(os.environ['MODEL_STATUS_FILE']).read_text())
        self.assertEqual(status['phase'], 'weights_ready')
        self.assertEqual(status['percent'], 100)

    def test_corrupt_download_never_promoted(self):
        with patch.object(b.urllib.request, 'urlopen', return_value=Response(b'x' * len(self.data))):
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                b.ensure_weights(self.path, self.lock)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_suffix('.part').exists())

    def test_interrupted_stream_resumes_without_duplicate_bytes(self):
        calls = []
        def open_response(request, timeout):
            calls.append(request.get_header('Range'))
            if len(calls) == 1:
                return Interrupted(self.data)
            return Response(self.data[7:], 206, {'Content-Range': f'bytes 7-{len(self.data)-1}/{len(self.data)}'})
        with patch.object(b.urllib.request, 'urlopen', side_effect=open_response), patch.object(b.time, 'sleep'):
            b.ensure_weights(self.path, self.lock)
        self.assertEqual(calls, [None, 'bytes=7-'])
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_server_ignoring_range_restarts_safely(self):
        self.path.with_suffix('.part').write_bytes(self.data[:7])
        with patch.object(b.urllib.request, 'urlopen', return_value=Response(self.data)):
            b.ensure_weights(self.path, self.lock)
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_completed_partial_verified_without_network(self):
        self.path.with_suffix('.part').write_bytes(self.data)
        with patch.object(b.urllib.request, 'urlopen', side_effect=AssertionError('no network needed')):
            b.ensure_weights(self.path, self.lock)
        self.assertEqual(self.path.read_bytes(), self.data)
        status = json.loads(Path(os.environ['MODEL_STATUS_FILE']).read_text())
        self.assertEqual(status['phase'], 'weights_ready')
        self.assertEqual(status['percent'], 100)

    def test_loading_keeps_completed_download_size(self):
        self.path.write_bytes(self.data)
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if str(path) == '/runtime/model-lock.json':
                return json.dumps(self.lock)
            return original_read(path, *args, **kwargs)
        # Point main at the existing test model without touching real /models.
        self.lock['model_files'][0]['file'] = str(self.path)
        with patch.object(Path, 'read_text', read), patch.object(b.os, 'execv') as execute:
            b.main()
        execute.assert_called_once()
        status = json.loads(Path(os.environ['MODEL_STATUS_FILE']).read_text())
        self.assertEqual(status['phase'], 'loading')
        self.assertEqual(status['downloaded_bytes'], len(self.data))
        self.assertEqual(status['total_bytes'], len(self.data))
        self.assertEqual(status['percent'], 100)

    def test_network_failure_is_bounded_and_reports_error(self):
        with patch.object(b.urllib.request, 'urlopen', side_effect=OSError('offline')) as request, patch.object(b.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'five attempts'):
                b.ensure_weights(self.path, self.lock)
        self.assertEqual(request.call_count, 5)
        status = json.loads(Path(os.environ['MODEL_STATUS_FILE']).read_text())
        self.assertEqual(status['phase'], 'error')
        self.assertFalse(self.path.exists())

    def test_real_http_disconnect_and_range_resume(self):
        data, ranges = self.data, []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                requested = self.headers.get('Range')
                ranges.append(requested)
                self.send_response(206 if requested else 200)
                if requested:
                    self.send_header('Content-Range', f'bytes 7-{len(data)-1}/{len(data)}')
                    self.send_header('Content-Length', str(len(data)-7))
                else:
                    self.send_header('Content-Length', str(len(data)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(data[7:] if requested else data[:7])
                self.wfile.flush()
                self.close_connection = True
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        real_open = b.urllib.request.urlopen
        def local_open(request, timeout):
            routed = b.urllib.request.Request(f'http://127.0.0.1:{server.server_port}/weights', headers=dict(request.header_items()))
            return real_open(routed, timeout=timeout)
        try:
            with patch.object(b.urllib.request, 'urlopen', side_effect=local_open), patch.object(b.time, 'sleep'):
                b.ensure_weights(self.path, self.lock)
            self.assertEqual(ranges, [None, 'bytes=7-'])
            self.assertEqual(self.path.read_bytes(), self.data)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

if __name__ == '__main__':
    unittest.main()
