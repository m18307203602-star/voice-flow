"""腾讯云实时语音识别 — WebSocket 流式"""
import hashlib
import hmac
import base64
import json
import time
import ssl
import threading
import uuid
from typing import Optional, Callable
from urllib.parse import quote as url_quote

import websocket


class TencentStreamingASR:
    """腾讯云实时语音识别 — WebSocket 流式传输音频，逐句返回文本"""

    def __init__(self, secret_id: str, secret_key: str, app_id: str,
                 status_callback: Optional[Callable[[str], None]] = None):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.app_id = app_id
        self._cb = status_callback
        self._ws_app: Optional[websocket.WebSocketApp] = None
        self._text = ""
        self._error: Optional[str] = None
        self._ready = threading.Event()
        self._done = threading.Event()
        self._cur_sentence = ""
        self._done_sentences: list = []

    def _log(self, msg: str):
        if self._cb:
            self._cb(msg)

    def _build_url(self) -> str:
        ts = int(time.time())
        params = {
            'secretid': self.secret_id,
            'engine_model_type': '16k_zh',
            'voice_format': 1,
            'needvad': 1,
            'filter_dirty': 0,
            'filter_modal': 0,
            'filter_punc': 0,
            'convert_num_mode': 1,
            'word_info': 0,
            'voice_id': str(uuid.uuid4()),
            'timestamp': str(ts),
            'expired': str(ts + 3600),
            'nonce': str(ts),
        }
        sign_str = f"asr.cloud.tencent.com/asr/v2/{self.app_id}?"
        sorted_keys = sorted(params.keys())
        sign_str += "&".join(f"{k}={params[k]}" for k in sorted_keys)
        sig = base64.b64encode(
            hmac.new(self.secret_key.encode(), sign_str.encode(), hashlib.sha1).digest()
        ).decode()

        url = f"wss://asr.cloud.tencent.com/asr/v2/{self.app_id}?"
        url += "&".join(f"{k}={params[k]}" for k in sorted_keys)
        url += f"&signature={url_quote(sig, safe='')}"
        return url

    def _on_open(self, ws):
        self._connected_at = time.time()
        self._ready.set()

    def _on_message(self, ws, msg):
        try:
            data = json.loads(msg)
            code = data.get('code', -1)
            if code == 0:
                res = data.get('result', {})
                text = res.get('voice_text_str', '')
                slice_type = res.get('slice_type', 0)
                if text:
                    cur = self._cur_sentence
                    if cur and len(cur) >= 10 and len(text) <= len(cur) * 0.4:
                        self._done_sentences.append(cur)
                        self._cur_sentence = text
                    else:
                        self._cur_sentence = text
                    self._text = "".join(self._done_sentences) + self._cur_sentence
                    if slice_type == 2:
                        self._done.set()
            else:
                self._error = f"[code={code}] {data.get('message', '')}"
                self._done.set()
        except Exception:
            pass

    def _on_error(self, ws, error):
        elapsed = time.time() - getattr(self, '_connected_at', 0)
        self._err_msg = f"[{elapsed:.1f}s] {str(error)[:200]}"

    def _on_close(self, ws, code, msg):
        elapsed = time.time() - getattr(self, '_connected_at', 0)
        self._close_info = f"[{elapsed:.1f}s] close code={code} msg={msg}"
        parts = []
        if getattr(self, '_err_msg', None):
            parts.append(self._err_msg)
        if self._close_info:
            parts.append(self._close_info)
        self._error = " | ".join(parts)
        self._done.set()

    def _connect_once(self) -> bool:
        self._ready.clear()
        self._done.clear()
        self._err_msg = None
        self._close_info = None
        url = self._build_url()
        self._ws_app = websocket.WebSocketApp(url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close)
        t = threading.Thread(
            target=lambda: self._ws_app.run_forever(
                sslopt={'cert_reqs': ssl.CERT_NONE}, ping_interval=0),
            daemon=True)
        t.start()
        if not self._ready.wait(timeout=10):
            return False
        if self._done.wait(timeout=0.05):  # 快速检测连接是否立即断开（原来 0.3s 没必要）
            return False
        return True

    def start(self):
        # ★ 防御性重置：确保不会残留上一次的识别文本
        self._text = ""
        self._cur_sentence = ""
        self._done_sentences = []
        self._error = None
        self._log("腾讯: 连接中...")
        if self._connect_once():
            self._log("腾讯: 已连接")
            return
        first_err = self._error
        time.sleep(0.05)  # 快速重试（原 0.5s 无必要）
        if self._connect_once():
            self._log("腾讯: 重连成功")
            return
        raise RuntimeError(f"腾讯流式连接失败 (2次): {first_err} → {self._error}")

    def feed(self, pcm_bytes: bytes):
        if self._ws_app and self._ready.is_set():
            try:
                self._ws_app.send(pcm_bytes, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception as e:
                if not self._done.is_set():
                    self._error = f"feed() 发送失败: {e}"
                    self._done.set()

    def stop(self) -> str:
        if self._ws_app and self._ready.is_set():
            try:
                self._ws_app.send('{"type":"end"}')
            except Exception:
                pass
        self._done.wait(timeout=30)
        if self._ws_app:
            try:
                self._ws_app.close()
            except Exception:
                pass
        if self._error:
            if self._text.strip():
                return self._text.strip()
            raise RuntimeError(f"腾讯流式识别错误: {self._error}")
        return self._text.strip()
