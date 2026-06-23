#!/usr/bin/env python3
"""Mini HTTP receiver — receives updated source files, then restarts voiceflow-server.
Paste this file to /opt/voice-flow-server/mini_receiver.py on the Alibaba Cloud server.

Usage on server:
  sudo python3 /opt/voice-flow-server/mini_receiver.py

Then from local, send files:
  curl -X POST --data-binary @database.py http://39.105.108.173:8000/database.py
  curl -X POST --data-binary @prompts_api.py http://39.105.108.173:8000/prompts_api.py
  curl -X POST http://39.105.108.173:8000/__done__
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from subprocess import run
import os, sys, threading

BASE = '/opt/voice-flow-server'
EXPECTED = {'database.py', 'prompts_api.py'}
received = set()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        name = self.path[1:]  # strip leading /
        if name == '__done__':
            self._finish()
            return
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        dest = os.path.join(BASE, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)
        received.add(name)
        print(f'[OK] {name} ({len(data)} bytes)')
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
        # Auto-restart once all expected files are received
        if EXPECTED.issubset(received):
            self._finish()

    def _finish(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'DONE - restarting service')
        print('[DONE] Restarting voiceflow-server...')
        run(['systemctl', 'restart', 'voiceflow-server'])
        threading.Thread(target=self.server.shutdown, daemon=True).start()


print('Stopping voiceflow-server...')
run(['systemctl', 'stop', 'voiceflow-server'])
print(f'Receiver on :8000, base={BASE}')
HTTPServer(('', 8000), Handler).serve_forever()
run(['systemctl', 'restart', 'voiceflow-server'])
print('Exited.')
