"""讯飞流式语音识别 — WebSocket 实时传输音频"""
import hashlib
import hmac
import base64
import json
import time
import ssl
import threading
from typing import Optional, Callable
from urllib.parse import quote as url_quote
from datetime import datetime, timezone

import websocket


class IflytekStreamingASR:
    """讯飞流式语音识别 — WebSocket 实时传输音频，边录边出文本"""

    def __init__(self, app_id: str, api_key: str, api_secret: str,
                 status_callback: Optional[Callable[[str], None]] = None):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self._cb = status_callback
        self._ws: Optional[websocket.WebSocket] = None
        self._lock = threading.Lock()
        self._recv_thread: Optional[threading.Thread] = None
        self._done = threading.Event()
        self._segments: list = []
        self._text = ""
        self._error: Optional[str] = None
        self._first_frame = True
        self._CHUNK = 1280  # 40ms @ 16kHz int16 mono
        self._buffer = bytearray()

    def _log(self, msg: str):
        if self._cb:
            self._cb(msg)

    def _build_url(self) -> str:
        host = "iat-api.xfyun.cn"
        date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        signature_origin = f"host: {host}\ndate: {date}\nGET /v2/iat HTTP/1.1"
        signature_sha = hmac.new(
            self.api_secret.encode(), signature_origin.encode(), hashlib.sha256
        ).digest()
        signature_b64 = base64.b64encode(signature_sha).decode()
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_b64}"'
        )
        authorization_b64 = base64.b64encode(authorization_origin.encode()).decode()
        return (f'wss://{host}/v2/iat'
                f'?authorization={url_quote(authorization_b64)}'
                f'&date={url_quote(date)}&host={host}')

    def _recv_loop(self):
        while not self._done.is_set():
            try:
                self._ws.settimeout(0.5)
                resp = self._ws.recv()
                data = json.loads(resp)
                code = data.get('code', -1)
                if code == 0:
                    result = data.get('data', {}).get('result', {})
                    ws_list = result.get('ws', [])
                    text = ''.join(c.get('w', '') for w in ws_list for c in w.get('cw', []))
                    ls = result.get('ls', False)
                    d_status = data.get('data', {}).get('status', -1)
                    if text:
                        self._segments.append(text)
                        self._text = ''.join(self._segments)
                    if ls or d_status == 2:
                        self._done.set()
                else:
                    self._error = data.get('message', f'code={code}')
                    self._done.set()
            except Exception as e:
                err_str = str(e)
                if 'timed out' in err_str.lower() or 'timeout' in err_str.lower():
                    continue
                self._done.set()
                break

    def start(self):
        # ★ 防御性重置：确保不会残留上一次的识别文本
        self._segments = []
        self._text = ""
        self._buffer = bytearray()
        self._first_frame = True
        self._error = None
        self._done.clear()
        self._log("讯飞: 连接中...")
        url = self._build_url()
        self._ws = websocket.create_connection(
            url, timeout=10,
            sslopt={'cert_reqs': ssl.CERT_NONE})
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        # 心跳线程：长录音时每25秒 ping 一次，防止被服务端断开
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()
        self._log("讯飞: 已连接")

    def _ping_loop(self):
        """每25秒发送 WebSocket ping 帧保持连接活跃"""
        while not self._done.is_set():
            self._done.wait(timeout=25)
            if self._done.is_set():
                break
            try:
                with self._lock:
                    if self._ws:
                        self._ws.ping()
            except Exception:
                self._done.set()
                break

    def feed(self, pcm_bytes: bytes):
        if self._ws is None:
            return
        self._buffer.extend(pcm_bytes)
        while len(self._buffer) >= self._CHUNK:
            chunk = bytes(self._buffer[:self._CHUNK])
            self._buffer = self._buffer[self._CHUNK:]
            self._send_frame(chunk)

    def _send_frame(self, chunk: bytes):
        audio_b64 = base64.b64encode(chunk).decode()
        with self._lock:
            if self._first_frame:
                frame = {
                    "common": {"app_id": self.app_id},
                    "business": {
                        "language": "zh_cn", "domain": "iat", "accent": "mandarin",
                        "vad_eos": 5000, "ptt": 1,
                    },
                    "data": {
                        "status": 0, "format": "audio/L16;rate=16000",
                        "encoding": "raw", "audio": audio_b64,
                    },
                }
                self._first_frame = False
            else:
                frame = {
                    "data": {
                        "status": 1, "format": "audio/L16;rate=16000",
                        "encoding": "raw", "audio": audio_b64,
                    }
                }
            try:
                self._ws.send(json.dumps(frame, ensure_ascii=False))
            except Exception as e:
                self._error = str(e)[:200]
                self._done.set()

    def stop(self) -> str:
        if len(self._buffer) > 0:
            chunk = bytes(self._buffer) + b'\x00' * (self._CHUNK - len(self._buffer))
            self._send_frame(chunk)
            self._buffer.clear()

        if self._ws:
            with self._lock:
                try:
                    end_frame = json.dumps({"data": {"status": 2}}, ensure_ascii=False)
                    self._ws.send(end_frame)
                except Exception as e:
                    if not self._error:  # 不覆盖 _send_frame 中的原始错误
                        self._error = str(e)[:200]

        ok = self._done.wait(timeout=5)
        if not ok:
            self._done.set()

        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._error:
            if self._text.strip():
                return self._text.strip()
            raise RuntimeError(f"讯飞流式识别错误: {self._error}")
        return self._text.strip()
