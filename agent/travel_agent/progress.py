"""Ephemeral local progress channel. Opaque tokens come from the trusted Core."""
import json
import re
import threading
import time
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class ProgressStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}

    def put(self, token, **event):
        if not re.fullmatch(r'[a-f0-9]{64}', token):
            return
        with self.lock:
            now=time.monotonic()
            self.events={k:v for k,v in self.events.items() if now-v[0]<360}
            self.events[token]=(now,event)
            if len(self.events)>512:
                self.events.pop(next(iter(self.events)))

    def get(self, token):
        with self.lock:
            item=self.events.get(token)
            return item[1] if item and time.monotonic()-item[0]<360 else {'stage':'waiting'}

progress_store=ProgressStore()

def serve_progress(port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            token=self.path.lstrip('/')
            if not re.fullmatch(r'[a-f0-9]{64}',token):
                self.send_error(404);return
            data=json.dumps(progress_store.get(token)).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer((os.getenv('AGENT_PROGRESS_HOST','127.0.0.1'),port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
