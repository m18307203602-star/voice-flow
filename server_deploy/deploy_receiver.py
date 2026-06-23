"""Mini HTTP receiver — run on server to receive updated source files.
Usage on server: sudo systemctl stop voiceflow-server && python3 deploy_receiver.py
Then from local: curl -X POST -F "file=@database.py" -F "path=database.py" http://39.105.108.173:8000/upload
"""
import os, sys, subprocess, json, cgi, tempfile, shutil
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = "/opt/voice-flow-server"
FILES = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/upload":
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                self.send_error(400, "Need multipart")
                return
            form = cgi.FieldStorage(
                fp=self.rfile, headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype}
            )
            path = form.getfirst("path", "")
            file_item = form["file"] if "file" in form else None
            if not path or not file_item:
                self.send_error(400, "Need path + file")
                return
            dest = os.path.join(BASE, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(file_item.file.read())
            FILES[path] = dest
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK " + path.encode())
            print(f"[RECEIVED] {path}")
        elif self.path == "/finish":
            print("=== All files received, restarting service ===")
            self.send_response(200)
            self.end_headers()
            # Restart voiceflow-server
            subprocess.run(["systemctl", "restart", "voiceflow-server"], check=False)
            print("Service restarted")
            self.wfile.write(b"DONE - service restarted")
            # Shutdown receiver
            import threading
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        print(f"[RECEIVER] {args[0]}")


print(f"Receiver on :8000, saving to {BASE}")
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
