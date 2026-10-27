"""Exercise the startup wait against an actual initially-unavailable HTTP service."""
import importlib.util
import os
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('agent_bootstrap', Path(__file__).resolve().parents[1]/'agent/bootstrap.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class AgentBootstrapTests(unittest.TestCase):
    def test_waits_through_download_before_starting_agent(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                calls.append(self.path)
                self.send_response(503 if len(calls) < 3 else 200)
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {'WAIT_FOR_MODEL':'1','LLM_PROVIDER':'llama_cpp','LLM_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1'}), patch.object(b.time,'sleep'), patch.object(b.os,'execv') as execute:
                b.main()
            self.assertEqual(calls, ['/health']*3)
            execute.assert_called_once_with(b.sys.executable,[b.sys.executable,'main.py'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_other_launchers_do_not_wait_for_docker_model(self):
        for values in ({'WAIT_FOR_MODEL':'','LLM_PROVIDER':'llama_cpp'}, {'WAIT_FOR_MODEL':'1','LLM_PROVIDER':'openai_compatible'}):
            with patch.dict(os.environ, values), patch.object(b.urllib.request,'build_opener',side_effect=AssertionError('unexpected local model dependency')), patch.object(b.os,'execv') as execute:
                b.main()
            execute.assert_called_once()

    def test_invalid_endpoint_fails_without_spinning(self):
        with patch.dict(os.environ, {'WAIT_FOR_MODEL':'1','LLM_PROVIDER':'llama_cpp','LLM_BASE_URL':'broken'}), patch.object(b.os,'execv') as execute:
            with self.assertRaisesRegex(RuntimeError,'endpoint'):
                b.main()
            execute.assert_not_called()

if __name__ == '__main__':
    unittest.main()
