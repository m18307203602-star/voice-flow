"""阿里云 DashScope 实时语音识别 — WebSocket 流式，Bear Token 鉴权"""
import json
import time
import ssl
import threading
import uuid
from typing import Optional, Callable

import websocket


class AliyunStreamingASR:
    """阿里云 DashScope 实时语音识别 — WebSocket 流式，Bear Token 鉴权"""

    def __init__(self, api_key: str,
                 status_callback: Optional[Callable[[str], None]] = None):
        self.api_key = api_key
        self._cb = status_callback
        self._ws: Optional[websocket.WebSocket] = None
        self._lock = threading.Lock()
        self._recv_thread: Optional[threading.Thread] = None
        self._done = threading.Event()
        self._text = ""
        self._error: Optional[str] = None
        self._task_id = uuid.uuid4().hex

    def _log(self, msg: str):
        if self._cb:
            self._cb(msg)

    def _recv_loop(self):
        while not self._done.is_set():
            try:
                self._ws.settimeout(0.5)
                resp = self._ws.recv()
                if isinstance(resp, bytes):
                    continue
                data = json.loads(resp)
                header = data.get("header", {})
                event = header.get("event", "")

                if event == "result-generated":
                    payload = data.get("payload", {})
                    output = payload.get("output", {})
                    sentence = output.get("sentence", {})
                    text = sentence.get("text", "")
                    is_end = sentence.get("sentence_end", False)
                    if is_end and text:
                        self._text += text
                elif event == "task-finished":
                    self._done.set()
                elif event == "task-failed":
                    payload = data.get("payload", {})
                    self._error = f"task-failed: {payload.get('code', '')} {payload.get('message', '')}"
                    self._done.set()
            except Exception as e:
                err_str = str(e)
                if 'timed out' in err_str.lower() or 'timeout' in err_str.lower():
                    continue
                self._done.set()
                break

    def start(self):
        self._log("阿里: 连接中...")
        url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        self._ws = websocket.create_connection(
            url, timeout=10,
            header={"Authorization": f"Bearer {self.api_key}"},
            sslopt={'cert_reqs': ssl.CERT_NONE})

        run_task = {
            "header": {
                "action": "run-task",
                "task_id": self._task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": "paraformer-realtime-v2",
                "parameters": {
                    "format": "pcm",
                    "sample_rate": 16000,
                    "language_hints": ["zh"],
                    "disfluency_removal_enabled": True,
                    "punctuation_prediction_enabled": True,
                },
                "input": {},
            },
        }
        self._ws.send(json.dumps(run_task, ensure_ascii=False))
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        # 心跳线程：长录音时每30秒 ping 一次，防止被服务端断开
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()
        self._log("阿里: 已连接")

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
        with self._lock:
            try:
                self._ws.send(pcm_bytes, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception as e:
                if not self._done.is_set():
                    self._error = str(e)[:200]
                    self._done.set()

    def stop(self) -> str:
        if self._ws:
            with self._lock:
                try:
                    finish = {
                        "header": {
                            "action": "finish-task",
                            "task_id": self._task_id,
                            "streaming": "duplex",
                        },
                        "payload": {"input": {}},
                    }
                    self._ws.send(json.dumps(finish, ensure_ascii=False))
                except Exception as e:
                    # 不要覆盖 feed() 中记录的原始错误
                    if not self._error:
                        self._error = str(e)[:200]

        self._done.wait(timeout=8)
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._error:
            if self._text.strip():
                return self._text.strip()
            raise RuntimeError(f"阿里流式识别错误: {self._error}")
        return self._text.strip()
