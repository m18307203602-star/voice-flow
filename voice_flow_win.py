"""Voice Flow Win — Windows 自带语音识别版

右 Shift 切换录音 → Windows 语音转写 → LLM 智能编排 → 格式化输出

STT: Windows SAPI (系统自带，零安装)
LLM 候选梯队: Qwen-Plus → DeepSeek-Chat → Gemini 2.0 Flash
"""

import asyncio
import sys
import time
import os
import io
import wave
import queue
import tempfile
import concurrent.futures
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd
from pynput import keyboard
import httpx

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'                   # SAPI 需要 int16
MIN_DURATION = 0.5

# 对比引擎（录音后并行转写）
COMPARE_ENGINES = ["tencent", "aliyun", "iflytek"]
COMPARE_ENGINE_NAMES = {"tencent": "腾讯", "aliyun": "阿里", "iflytek": "讯飞"}
VOSK_MODEL_PATH = r"G:\voice-workflow\vosk-model-small-cn-0.22"

# 百度语音识别
BAIDU_APP_ID = "YOUR_BAIDU_APP_ID"
BAIDU_API_KEY = "YOUR_BAIDU_API_KEY"
BAIDU_SECRET_KEY = "YOUR_BAIDU_SECRET_KEY"

# 腾讯云语音识别
TENCENT_SECRET_ID = "YOUR_TENCENT_SECRET_ID"
TENCENT_SECRET_KEY = "YOUR_TENCENT_SECRET_KEY"
TENCENT_APP_ID = "YOUR_TENCENT_APP_ID"  # 实时语音识别 WebSocket 用


# ═══════════════════════════════════════════════════════════════
# 腾讯实时语音识别（WebSocket 流式，边录边出字）
# ═══════════════════════════════════════════════════════════════

class TencentStreamingASR:
    """腾讯云实时语音识别 — WebSocket 流式传输音频，逐句返回文本"""

    def __init__(self, secret_id: str, secret_key: str, app_id: str):
        import hashlib as _hl
        import hmac as _hmac
        import base64 as _b64
        import json as _json
        import time as _time
        import ssl as _ssl
        import threading as _th
        import websocket as _ws

        self._hl = _hl; self._hmac = _hmac; self._b64 = _b64
        self._json = _json; self._time = _time; self._ssl = _ssl
        self._th = _th; self._ws = _ws

        self.secret_id = secret_id
        self.secret_key = secret_key
        self.app_id = app_id
        self._ws_app: Optional[_ws.WebSocketApp] = None
        self._text = ""
        self._error: Optional[str] = None
        self._ready = _th.Event()
        self._done = _th.Event()
        self._cur_sentence = ""      # 当前句子最新累积文本
        self._done_sentences = []    # 已完成句子列表

    def _build_url(self) -> str:
        import uuid as _uuid
        ts = int(self._time.time())
        params = {
            'secretid': self.secret_id,
            'engine_model_type': '16k_zh',
            'voice_format': 1,       # PCM
            'needvad': 1,
            'filter_dirty': 0,
            'filter_modal': 0,
            'filter_punc': 0,
            'convert_num_mode': 1,
            'word_info': 0,
            'voice_id': str(_uuid.uuid4()),
            'timestamp': str(ts),
            'expired': str(ts + 3600),
            'nonce': str(ts),
        }
        # 签名
        sign_str = f"asr.cloud.tencent.com/asr/v2/{self.app_id}?"
        sorted_keys = sorted(params.keys())
        sign_str += "&".join(f"{k}={params[k]}" for k in sorted_keys)
        sig = self._b64.b64encode(
            self._hmac.new(self.secret_key.encode(), sign_str.encode(), self._hl.sha1).digest()
        ).decode()

        url = f"wss://asr.cloud.tencent.com/asr/v2/{self.app_id}?"
        url += "&".join(f"{k}={params[k]}" for k in sorted_keys)
        # ⚠️ base64 签名含 +/= 特殊字符，必须 URL 编码
        from urllib.parse import quote as _url_quote
        url += f"&signature={_url_quote(sig, safe='')}"
        return url

    def _on_open(self, ws):
        self._connected_at = self._time.time()
        self._ready.set()

    def _on_message(self, ws, msg):
        try:
            data = self._json.loads(msg)
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
                        action = "NEW"
                    else:
                        self._cur_sentence = text
                        action = "CUM"
                    self._text = "".join(self._done_sentences) + self._cur_sentence
                    if slice_type == 2:
                        self._done.set()
                    # DEBUG: 临时日志，确认 v5 未误判
                    print(f"  [TENCENT] {action} done#={len(self._done_sentences)} cur_len={len(self._cur_sentence)} text={text[:50]!r}")
            else:
                self._error = f"[code={code}] {data.get('message', '')}"
                self._done.set()
        except Exception:
            pass

    def _on_error(self, ws, error):
        elapsed = self._time.time() - getattr(self, '_connected_at', 0)
        self._err_msg = f"[{elapsed:.1f}s] {str(error)[:200]}"
        # ⚠️ 不设置 _ready — 只有 on_open 表示真正连接成功

    def _on_close(self, ws, code, msg):
        elapsed = self._time.time() - getattr(self, '_connected_at', 0)
        self._close_info = f"[{elapsed:.1f}s] close code={code} msg={msg}"
        # 合并 error + close 信息
        parts = []
        if getattr(self, '_err_msg', None):
            parts.append(self._err_msg)
        if self._close_info:
            parts.append(self._close_info)
        self._error = " | ".join(parts)
        self._done.set()

    def _connect_once(self) -> bool:
        """单次连接尝试，返回是否成功"""
        self._ready.clear()
        self._done.clear()
        self._err_msg = None
        self._close_info = None
        url = self._build_url()
        self._ws_app = self._ws.WebSocketApp(url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close)
        t = self._th.Thread(
            target=lambda: self._ws_app.run_forever(
                sslopt={'cert_reqs': self._ssl.CERT_NONE}, ping_interval=0),
            daemon=True)
        t.start()
        if not self._ready.wait(timeout=10):
            return False
        # 连接后等 0.3s 看是否立即断开
        if self._done.wait(timeout=0.3):
            return False
        return True

    def start(self):
        # 第一次尝试
        if self._connect_once():
            return
        first_err = self._error
        # 等 0.5s 后重试一次
        self._time.sleep(0.5)
        if self._connect_once():
            return
        # 两次都失败，报告详细错误
        raise RuntimeError(f"腾讯流式连接失败 (2次): {first_err} → {self._error}")

    def feed(self, pcm_bytes: bytes):
        """喂入 PCM 音频数据 (16kHz, 16bit, mono)"""
        if self._ws_app and self._ready.is_set():
            try:
                self._ws_app.send(pcm_bytes, opcode=self._ws.ABNF.OPCODE_BINARY)
            except Exception as e:
                # 连接已断，不再尝试发送
                if not self._done.is_set():
                    self._error = f"feed() 发送失败: {e}"
                    self._done.set()

    def stop(self) -> str:
        """发送结束信号，等待最终结果，返回完整文本"""
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
                return self._text.strip()  # 有文本就返回，不抛异常
            raise RuntimeError(f"腾讯流式识别错误: {self._error}")
        return self._text.strip()


class IflytekStreamingASR:
    """讯飞流式语音识别 — WebSocket 实时传输音频，边录边出文本
    协议：JSON 帧内嵌 base64 音频，TEXT opcode
    参考：https://www.xfyun.cn/doc/asr/voicedictation/API.html
    """

    def __init__(self, app_id: str, api_key: str, api_secret: str):
        import hashlib as _hl
        import hmac as _hmac
        import base64 as _b64
        import json as _json
        import time as _time
        import ssl as _ssl
        import threading as _th
        from urllib.parse import quote as _quote

        self._hl = _hl; self._hmac = _hmac; self._b64 = _b64
        self._json = _json; self._time = _time; self._ssl = _ssl
        self._th = _th; self._quote = _quote

        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self._ws = None  # websocket.WebSocket (create_connection)
        self._lock = _th.Lock()
        self._recv_thread: Optional[_th.Thread] = None
        self._done = _th.Event()
        self._segments: list = []  # 收集所有分句文本
        self._text = ""
        self._error: Optional[str] = None
        self._first_frame = True  # 首帧需要 common + business
        self._CHUNK = 1280  # 40ms @ 16kHz int16 mono
        self._buffer = bytearray()  # 缓冲不满一帧的数据

    def _build_url(self) -> str:
        from datetime import datetime, timezone
        host = "iat-api.xfyun.cn"
        date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        signature_origin = f"host: {host}\ndate: {date}\nGET /v2/iat HTTP/1.1"
        signature_sha = self._hmac.new(
            self.api_secret.encode(), signature_origin.encode(), self._hl.sha256
        ).digest()
        signature_b64 = self._b64.b64encode(signature_sha).decode()
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_b64}"'
        )
        authorization_b64 = self._b64.b64encode(authorization_origin.encode()).decode()
        return (f'wss://{host}/v2/iat'
                f'?authorization={self._quote(authorization_b64)}'
                f'&date={self._quote(date)}&host={host}')

    def _recv_loop(self):
        """后台接收线程：持续读取 WebSocket 消息直到结束"""
        _msg_count = 0
        while not self._done.is_set():
            try:
                self._ws.settimeout(0.5)
                resp = self._ws.recv()
                data = self._json.loads(resp)
                code = data.get('code', -1)
                _msg_count += 1
                if code == 0:
                    result = data.get('data', {}).get('result', {})
                    ws_list = result.get('ws', [])
                    text = ''.join(c.get('w', '') for w in ws_list for c in w.get('cw', []))
                    ls = result.get('ls', False)
                    sn = result.get('sn', -1)
                    d_status = data.get('data', {}).get('status', -1)
                    print(f"  [IFLYTEK #{_msg_count}] code=0 sn={sn} ls={ls} d_status={d_status} text_len={len(text)} text='{text[:60]}'")
                    if text:
                        self._segments.append(text)
                        self._text = ''.join(self._segments)
                    # 最后一片 → 退出接收循环
                    if ls:
                        print(f"  [IFLYTEK] ls=true 检测到，退出接收")
                        self._done.set()
                    if d_status == 2:
                        print(f"  [IFLYTEK] data.status=2 检测到，退出接收")
                        self._done.set()
                else:
                    print(f"  [IFLYTEK #{_msg_count}] code={code} msg={data.get('message', '')[:80]}")
                    self._error = data.get('message', f'code={code}')
                    self._done.set()
            except Exception as e:
                err_str = str(e)
                if 'timed out' in err_str.lower() or 'timeout' in err_str.lower():
                    continue  # Timeout normal, keep waiting
                print(f"  [IFLYTEK] recv异常(#{_msg_count}msgs): {err_str[:80]}")
                self._done.set()
                break

    def start(self):
        url = self._build_url()
        self._ws = __import__('websocket').create_connection(
            url, timeout=10,
            sslopt={'cert_reqs': self._ssl.CERT_NONE})
        self._recv_thread = self._th.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def feed(self, pcm_bytes: bytes):
        """喂入 PCM 音频数据 (16kHz, 16bit, mono) — 内部缓冲到 1280B 再发送"""
        if self._ws is None:
            return
        self._buffer.extend(pcm_bytes)
        while len(self._buffer) >= self._CHUNK:
            chunk = bytes(self._buffer[:self._CHUNK])
            self._buffer = self._buffer[self._CHUNK:]
            self._send_frame(chunk)

    def _send_frame(self, chunk: bytes):
        """发送一帧 JSON + base64 音频"""
        audio_b64 = self._b64.b64encode(chunk).decode()
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
                self._ws.send(self._json.dumps(frame, ensure_ascii=False))
            except Exception as e:
                self._error = str(e)[:200]
                self._done.set()

    def stop(self) -> str:
        """发送结束信号，等待最终结果，返回完整文本"""
        # 刷新残留 buffer（不足 1280B 的尾部）
        if len(self._buffer) > 0:
            chunk = bytes(self._buffer) + b'\x00' * (self._CHUNK - len(self._buffer))
            self._send_frame(chunk)
            self._buffer.clear()

        if self._ws:
            with self._lock:
                try:
                    end_frame = self._json.dumps({"data": {"status": 2}}, ensure_ascii=False)
                    self._ws.send(end_frame)
                except Exception as e:
                    self._error = str(e)[:200]

        # 等待接收线程收集完最终结果（ls=true 或 status=2 会自动 set _done）
        ok = self._done.wait(timeout=5)
        if not ok:
            # 超时：强制结束（服务器可能没主动发 ls=true）
            print(f"  [DEBUG iflytek] _done 超时(5s), 强制结束, 已收集 {len(self._segments)} 段")
            self._done.set()
        else:
            print(f"  [DEBUG iflytek] _done 正常触发, 已收集 {len(self._segments)} 段")

        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._error:
            if self._text.strip():
                return self._text.strip()  # 有文本就返回，不抛异常
            raise RuntimeError(f"讯飞流式识别错误: {self._error}")
        return self._text.strip()


class AliyunStreamingASR:
    """阿里云 DashScope 实时语音识别 — WebSocket 流式，Bear Token 鉴权
    协议：run-task + 二进制音频帧 + result-generated 事件
    参考：https://www.alibabacloud.com/help/en/model-studio/websocket-for-paraformer-real-time-service
    凭证：复用 QWEN_KEY（DashScope API Key），零额外配置
    """

    def __init__(self, api_key: str):
        import json as _json
        import time as _time
        import ssl as _ssl
        import threading as _th
        import uuid as _uuid

        self._json = _json; self._time = _time; self._ssl = _ssl
        self._th = _th; self._uuid = _uuid

        self.api_key = api_key
        self._ws = None
        self._lock = _th.Lock()
        self._recv_thread: Optional[_th.Thread] = None
        self._done = _th.Event()
        self._text = ""
        self._error: Optional[str] = None
        self._task_id = _uuid.uuid4().hex  # 32位唯一任务ID

    def _recv_loop(self):
        """后台接收线程：解析 result-generated 事件"""
        while not self._done.is_set():
            try:
                self._ws.settimeout(0.5)
                resp = self._ws.recv()
                if isinstance(resp, bytes):
                    continue
                data = self._json.loads(resp)
                header = data.get("header", {})
                event = header.get("event", "")

                if event == "task-started":
                    pass  # 任务已启动，可以开始发音频
                elif event == "result-generated":
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
        url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        self._ws = __import__('websocket').create_connection(
            url, timeout=10,
            header={"Authorization": f"Bearer {self.api_key}"},
            sslopt={'cert_reqs': self._ssl.CERT_NONE})

        # 发送 run-task 启动识别
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
                    "disfluency_removal_enabled": False,
                    "punctuation_prediction_enabled": True,
                },
                "input": {},
            },
        }
        self._ws.send(self._json.dumps(run_task, ensure_ascii=False))
        self._recv_thread = self._th.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def feed(self, pcm_bytes: bytes):
        """喂入 PCM 音频数据 — BINARY 帧"""
        if self._ws is None:
            return
        with self._lock:
            try:
                self._ws.send(pcm_bytes, opcode=__import__('websocket').ABNF.OPCODE_BINARY)
            except Exception as e:
                if not self._done.is_set():
                    self._error = str(e)[:200]
                    self._done.set()

    def stop(self) -> str:
        """发送 finish-task，等待最终结果"""
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
                    self._ws.send(self._json.dumps(finish, ensure_ascii=False))
                except Exception as e:
                    self._error = str(e)[:200]

        self._done.wait(timeout=8)
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._error:
            if self._text.strip():
                return self._text.strip()  # 有文本就返回，不抛异常
            raise RuntimeError(f"阿里流式识别错误: {self._error}")
        return self._text.strip()


# 阿里云语音识别（复用 DashScope 密钥，即 QWEN_KEY）
# 无需额外申请！


# 科大讯飞语音识别（极速语音转写）
# 获取: https://console.xfyun.cn/
IFLYTEK_APP_ID = "YOUR_IFLYTEK_APP_ID"
IFLYTEK_API_KEY = "YOUR_IFLYTEK_API_KEY"
IFLYTEK_API_SECRET = "YOUR_IFLYTEK_API_SECRET"

# API Keys
GEMINI_KEY = "YOUR_GEMINI_KEY"
QWEN_KEY = "YOUR_QWEN_KEY"
DEEPSEEK_KEY = "YOUR_DEEPSEEK_KEY"
PROXY_URL = "http://127.0.0.1:7790"

# ═══════════════════════════════════════════════════════════════
# 提示词模板（与原版一致）
# ═══════════════════════════════════════════════════════════════

PROMPTS = {
    "1": {
        "name": "整理",
        "system": """你是一位语言优化高手。你会收到三份不同语音引擎的转写结果（[腾讯]、[讯飞]、[阿里]）。仅输出优化结果，不展现过程。

════════════════════════════
零、转录合成（最高优先级，先执行）
════════════════════════════
对比三份转录，按以下三层递进逻辑合成一份最准确的参考文本：

第一层：多数投票
- 同一位置，两份一致、一份不同 → 暂取多数派
- 三份都不同 → 暂取语义最通顺的那份

第二层：语义终审
- 检查多数派结果是否语义通顺、上下文合理
- 多数派不合理 → 检查少数派。少数派合理 → 采用少数派
- 多数派合理 → 直接采用

第三层：自行纠错
- 多数派和少数派都不合理 → 用你的中文理解能力推断最可能的原文
- 推断必须有上下文依据，严禁凭空编造

⚠️ 严禁输出评估过程、投票细节、对比分析。严禁输出引擎标签（[腾讯][阿里][讯飞]）。

合成参考文本后，对参考文本应用后续规则。输入可能包含 STT 识别带来的格式空格（如"我 跟 你 说"），必须先去掉空格还原为正常中文再处理。

⚠️ 铁律：你的输出必须是最终的结构化中文文本，不是评估、不是投票、不是分析。严禁任何元描述。

规则（按优先级）：
1. 【不编造】仅保留原始逻辑和语义，禁止编造无关内容。
2.【语法提示】基本语序和结构、动词、量词、虚词基本逻辑要链接齐全、主语不重复，上下文连贯。根据这些语法提示，发散思维去理解汉语语法（优先级高）
════════════════════════════
一、语言加工规范
════════════════════════════
1. 【标点强制】必须根据停顿补充逗号、句号、问号、感叹号，并删除不搭语境的异常符号。严禁大面积无标点"纯原文流"。
2. 【去噪边界】剔除 [嗯/啊/呃/那个/就是说/你知道吧/就是说/反正/然后（纯连接词）] 等口头禅和思维链重复。但必须保留带情感色彩的语气开头（如"哎你说这个人怎么这样啊"）。
3. 【八类信息不丢】动作、时间、数据、人名、地点、条件、结果、原因，一项不能少。
4. 【微调与补全】口语动词→书面语（打→预约），副词→准确（大概→预计），数字格式化（十点→10:00），同音错别字语境修正，语义模糊用括号标注（"皮里面包馅的那种（饺子或抄手）"），推断不了留白。
5. 【逆向标签】仅在用户明确表达时：例如：说"必须/不能"→【原则】，说"我觉得"→【观点】，说"建议"→【建议】。不硬套，根据示例逆向上位词总结分类标签，标签 2-4 字。
6.【语义补充】对于不通顺语句，提取语义和逻辑，整理成可读易理解内容。
7.【标签分类】不同类型物品混合，要归类物品，逆向上位词（比如苹果、香蕉上位词归类于水果）

════════════════════════════
二、分类决策引擎
════════════════════════════
分析输入文本，只要命中以下任一信号 → 判定为 B 类（用编号结构），均不满足 → A 类（纯分段）：
- 包括但不限于：列举（第一/第二/首先/然后/最后/几个/几件/几点/几方面）、分析（原因/方案/好处/坏处/优缺点/对比/区别/分析）、规划（计划/安排/准备/打算/步骤/流程/阶段）、总结（做了X件事/汇报/进展/总结）、指令（交办/待办/帮我把/要求）。其余未穷举的同类信号，发散思维类比识别。

【聚类铁律】B 类大类数量严格 1-3 个（2-4字），禁止单句话独立成类，子项用 (a)(b) 编号。
【B-指令特殊规则】若判定为指令/交办类，大类下方必须严格使用 - [ ] 待办清单格式（禁止用 (a)(b) 替代）。
【A类硬约束】灵感/想法类若未命中 B 类信号，严禁强行套用编号结构——纯分段处理。

════════════════════════════
三、输出格式
════════════════════════════
A 类（无逻辑结构 / 叙事 / 感想 / 陈述）：
- 纯段落文本，自然分段。无编号，无标题
B 类（有逻辑结构 / 计划 / 分析 / 总结 / 指令）：
- 开场句 + 桥接句（"具体如下"）+ 编号结构 + 简短收尾句
B-指令（交办/待办/帮我把/要求）：
- - [ ] 待办清单格式，每一项一个可执行动作。大类 1-3 个，子项用 - [ ] 缩进

════════════════════════════
四、示例
════════════════════════════
【A 类】输入："哎我今天想到一个点子就是我们可以做个APP帮人整理衣柜拍照后AI分类告诉哪些衣服该扔该留然后帮你搭配穿搭你觉得怎么样"
输出："哎，我今天想到一个点子，就是我们可以做个APP帮人整理衣柜。拍照后用AI进行分类，告诉用户哪些衣服该扔该留，然后帮你搭配穿搭。你觉得怎么样？"
——————————————————————————————————————————————————————————————————————
【B-计划】输入："我今天要安排几件事。因为我明天要去一趟武汉，坐车的话今天晚上七、八点的时候打个顺风车。然后明天上午十点出发，下午一点之前到去做个牙齿理疗。明天的安排就是这么多。"
输出："我今天要安排几件事。因为我明天要去一趟武汉，具体行程如下：
1. 交通安排
(a) 最好在今天晚上 19:00-20:00 左右预约一辆顺风车
(b) 明天上午 10:00 出发
2. 武汉行程
(a) 预计下午 13:00 之前到达
(b) 到达后去做牙齿理疗
明天安排大概就这么多。"

【B-指令】输入："你今天帮我把那几件事干了。首先把今天收到的发票报销一下，然后必须在五点前把PPT改好发我，不能迟到。"
输出："你今天帮我把这几件事处理一下。具体要求如下：

【原则】必须在 17:00 前完成 PPT 修改并发送，不得延误。

1. 日常事务处理
   - [ ] 报销今天收到的发票
   - [ ] 修改 PPT 并发送给主管"
════════════════════════════
五、输出拦截器（最高优先级）
════════════════════════════
0. 【疑问句拦截】输入为疑问句（包含"？/什么/怎么/为什么/哪/谁/多少/几/吗/呢/吧/是什么意思"等疑问特征）时，仅整理语法和标点，原样保留疑问句格式输出。严禁补充答案、严禁翻译解释、严禁提供任何未在原文中出现的信息。
1. 严禁输出任何提示词元叙述，包括但不限于："【B类格式】""输出：""类型A/B""第一步""第二步""我帮你整理了"。
2. 严禁在开头原样复述用户输入，必须直接从正文或分类标题开始。
3. 禁止编造用户没说的内容。结构化编号和分类标题提炼自用户原话，不属于编造。
4. 禁止补充用户没说过的技术规格、性能参数、数据指标（如温度阈值、内存型号、测试工具名）。微调限于措辞修正，不扩充信息。""",
        "temperature": 0.1,
    },
    "2": {
        "name": "待办",
        "system": """你是一个任务拆解助手。从用户的口语内容中提取所有待办事项。

要求：
1. 识别所有需要执行的事项，包括用户明确说的和隐含的
2. 按优先级或时间顺序排列
3. 如果事项之间有依赖关系，用缩进表示子任务
4. 每项写清楚要做什么，不要模糊表述
5. 如果用户说了时间节点，标注在事项后面

输出格式：
- [ ] 第一件事（时间/优先级说明）
  - [ ] 子任务或前置条件
- [ ] 第二件事
- [ ] 第三件事

如果没有待办事项，输出「无待办事项」。不要加任何额外解释。""",
        "temperature": 0.1,
    },
    "3": {
        "name": "笔记",
        "system": """你是一个信息结构化助手。将用户的口语内容整理成结构化笔记。

要求：
1. 用一个简短的标题概括主旨
2. 按主题或时间线分组
3. 每点用简洁的要点表述
4. 末尾提炼 2-3 个关键词

输出格式：
**{一句话标题}**

- 要点一
- 要点二
  - 补充细节
- 要点三

> 关键词：xxx、xxx

不要输出格式以外的内容。""",
        "temperature": 0.3,
    },
    "4": {
        "name": "原文",
        "system": "直接输出以下语音识别原文，不做任何修改。不要加任何解释。",
        "temperature": 0.0,
    },
    "6": {
        "name": "文采",
        "system": """你是一位汉语文学润色专家。在保留原文全部信息和逻辑的前提下，根据语义和语境从以下 32 类汉语语言形式中自动选用最合适的进行点缀替换，增强表达的文化底蕴和文学质感。仅输出润色后的最终文本，不展现过程。

【风格库 — 32 类】（按语境自动选用，宁缺毋滥）

固定短语：成语（画蛇添足）、惯用语（拍马屁）、歇后语（泥菩萨过江—自身难保）、谚语（种瓜得瓜）、俗语（不怕慢就怕站）、格言（学而不思则罔）
引用传承：典故（高山流水/伯牙子期）、名人名言（为中华之崛起而读书）、古训（勿以善小而不为）、家训（朱子家训）、箴言（满招损谦受益）、语录（论语）
文体篇章：文言文（师说/岳阳楼记）、诗词（唐诗宋词）、对联（天增岁月人增寿）、寓言（刻舟求剑）、神话（女娲补天）、经书（道德经）
民俗口头：绕口令（吃葡萄不吐葡萄皮）、谜语（麻屋子红帐子→花生）、顺口溜（一九二九不出手）、童谣（小老鼠上灯台）、打油诗（江山一笼统）、俚语（侃大山/忽悠）
铭刻点评：座右铭（天道酬勤）、墓志铭、题词、批语（金圣叹批水浒）
圈子专用：行话（望闻问切）、黑话（天王盖地虎）、禅语（本来无一物）、网络流行语（慎用，仅当原文语境匹配时）

【核心规则】
1. 语境优先：根据文本语境、情绪、正式程度自动选用，宁缺毋滥
2. 密度控制：常规文本每 100 字≤1 处点缀；正式演讲/文学场景可略高
3. 自然融入：替换而非堆砌，保持语句流畅度
4. 不编造：只从风格库选用，不确定的不加
5. 逆向选择：先从六大类中定位合语境的大类，再在类内选具体形式

【不加的场景（最高优先级）】
- 输入为疑问句 → 不加（仅可润色措辞，严禁作答或推断）
- 闲聊、日常寒暄、买菜砍价等生活口语 → 不加
- 紧急通知、警告、安全提示 → 不加
- 纯数据、报表、财经数字 → 不加
- 技术说明、操作步骤、代码讨论 → 不加
- 原文已有文学元素时不重复叠加
- 不确定该不该加 → 不加（宁可保守）

仅输出润色后的最终文本，不加任何解释或标注。""",
        "temperature": 0.2,
    },
    "7": {
        "name": "夫妻",
        "system": """你是一位语气转换器。将收到的原话改写成亲密关系中的口语风格——不指定性别，不加任何称呼或昵称。仅输出改写后的最终文本，不展现过程。

══════════════════════
第一步：场景识别（先判断再动手）
══════════════════════
根据原文情绪和内容，自动归入以下场景之一，严格按场景规则行事：

【严肃冲突】吵架、原则分歧、底线问题 → 齿轮用「台阶递送」。可带善意幽默化解紧张，但严禁自嘲降身段（显得演戏）、互怼（激化矛盾）、调侃对方（对方会觉得你不在乎）。幽默只能从善意出发，不能消解问题本身。
  例：「我不想再跟你吵了」→「我们停一下吧，吵赢了我又不发奖金」

【伤心委屈】受打击、被误解、失落、难过 → 齿轮仅限「示弱」。禁用互怼、调侃、邀功。给予温度但不强行搞笑。
  例：「今天被老板骂了，好难过」→「今天被老板骂了，真的好难过，我需要缓一缓」

【疲惫无力】累、困、加班、精力耗尽 → 齿轮用「示弱」或「撒娇」。工具箱可用叠词、程度夸张。传递"需要你"但不施加压力。
  例：「今天太累了不想做饭」→「今天真的累瘫了，眼睛都睁不开了，咱能不能不做了？」

【日常吐槽】抱怨工作、生活琐事、碎碎念 → 齿轮用「调侃」或「互怼」（带糖衣）。工具箱可用自嘲、反问钩子。
  例：「这个破网又卡了」→「这网又在表演慢动作了，你说它是不是跟我有仇？」

【求助商量】需要帮忙、征求意见、做决定 → 齿轮用「撒娇」或「留白试探」。工具箱可用拖音撒娇、反问钩子。
  例：「这个东西我不会弄」→「这个好难，我搞不定怎么办嘛」

【分享开心】好消息、做到了、好笑的事、小得意 → 齿轮用「邀功」或「仪式邀约」。工具箱可用自夸、叠词。
  例：「我今天跑步了」→「我今天居然跑步了！厉害吧厉害吧？」

【日常闲聊】吃了没、去哪、随便聊聊 → 齿轮用「调侃」或「留白试探」。工具箱可用反问钩子。轻量处理。
  例：「今天天气挺好的」→「今天天气真不错，是不是该出去走走？」

【歉意让步】认错、道歉、主动示好 → 齿轮用「台阶递送」。禁用自嘲（像在演苦情戏）、互怼（不真诚）、邀功（转移焦点）。诚恳为主，可带一丝善意幽默让气氛自然。
  例：「对不起是我不好」→「是我不好，话赶话了。给我个机会补救行不行？」

══════════════════
铁律（最高优先级，违反任一条即失败）
══════════════════
1. 信息零添加：原文说什么事，你就只说什么事。禁止编造原文没有的动作、物品、场景、方案。
2. 禁止替对方回应：单口改写，不生成对方的回复或反应。
3. 禁止加任何称呼或昵称：不要加"老公/老婆/宝/亲爱的/你呀/憨憨"等任何关系称谓。原文有称呼就保留，没有就不加。
4. 始终保持第一人称"我"的视角。
5. 场景错配即失败：严肃/冲突场景可用善意幽默缓解紧张，但禁用自嘲（降身段）、互怼和调侃；伤心/委屈场景禁用互怼和调侃。
6. 输入为疑问句时，仅按场景规则转换语气风格，严禁回答或解释疑问。

══════════════════
八齿轮定义
══════════════════
撒娇（"我不会嘛""你来好不好"——创造被需要感）
互怼（"就你能""行行行你厉害"——亲密调侃，必须带糖衣）
邀功（"我今天干了啥啥啥，你说吧"——正向寻求认可）
示弱（"今天真的不行了""让我瘫一会儿"——打开关怀通道）
调侃（"你跟那谁有得一拼"——制造共同笑点）
留白试探（"你猜我今天碰到谁了"——话说一半，用问句结尾）
仪式邀约（"好久没去那家了，走走走"——强化"我俩"）
台阶递送（"行吧算你对，但我保留上诉权"——降级冲突但保全体面）

══════════════════
趣味性工具箱
══════════════════
- 叠词强化：「烦」→「烦死了烦死了」
- 反问钩子：用"你说呢？""谁能懂？"结尾，制造互动入口
- 程度夸张：「饿」→「饿得能吃下一头牛」
- 自嘲/自夸：「我今天也太厉害了吧」
- 拖音撒娇：用"嘛""啦""好不好""行不行"
- 句式对仗：「你不来，我不去」

══════════════════
改写幅度
══════════════════
场景匹配齿轮 + 场景允许的工具箱手法 1-2 个。严肃/伤心场景从简。

反面示例（严禁）：
  输入：「工作没找到，好烦」
  输出：「老公，工作没找到，烦死了」
  ↑ 禁止！加了"老公"。

  输入：「我们分手吧」
  输出：「行行行分手就分手，谁怕谁～」
  ↑ 严肃场景用了互怼齿轮，严重错配！""",
        "temperature": 0.2,
    },
}

# ═══════════════════════════════════════════════════════════════
# LLM 候选梯队（与原版一致）
# ═══════════════════════════════════════════════════════════════

@dataclass
class LLMResult:
    text: str
    model_used: str

async def _call_gemini(user_text: str, temperature: float) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    body = {
        "contents": [{"parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
    }
    async with httpx.AsyncClient(proxy=PROXY_URL, timeout=15.0) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

async def _call_qwen(user_text: str, temperature: float) -> str:
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {QWEN_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": user_text}],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def _call_deepseek(user_text: str, temperature: float) -> str:
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": user_text}],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def process_with_llm(text: str, mode: str) -> LLMResult:
    cfg = PROMPTS[mode]
    full_prompt = f"{cfg['system']}\n\n输入内容：\n{text}"

    candidates: list[tuple[str, callable]] = [
        ("Qwen-Plus", _call_qwen),
        ("DeepSeek-Chat", _call_deepseek),
        ("Gemini 2.0 Flash", _call_gemini),
    ]

    for name, fn in candidates:
        try:
            result = await fn(full_prompt, cfg["temperature"])
            return LLMResult(text=result, model_used=name)
        except Exception as e:
            err_msg = str(e)
            if len(err_msg) > 80:
                err_msg = err_msg[:80] + "..."
            print(f"  [WARN] {name} unavailable: {err_msg}")

    return LLMResult(text=text, model_used="全部候选不可用，返回原文")

# ═══════════════════════════════════════════════════════════════
# 录音模块（保留原版，仅改为 int16 以兼容 SAPI）
# ═══════════════════════════════════════════════════════════════

class Recorder:
    def __init__(self):
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._start_time = 0.0
        self._last_duration = 0.0
        self._streaming_stts: list = []  # 流式 STT 实例列表（支持多引擎同时流式）

    def add_streaming_stt(self, stt):
        """添加流式识别器，录音时会同步喂 PCM 数据"""
        self._streaming_stts.append(stt)

    def clear_streaming_stts(self):
        self._streaming_stts.clear()

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            self._audio_queue.put(indata.copy())
            for stt in self._streaming_stts:
                try:
                    stt.feed(indata.tobytes())
                except Exception:
                    pass

    def start(self):
        self._audio_queue = queue.Queue()
        self._recording = True
        self._start_time = time.time()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> Optional[np.ndarray]:
        self._last_duration = time.time() - self._start_time if self._recording else 0.0
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        chunks = []
        while True:
            try:
                chunks.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_DURATION:
            return None
        return audio

    @property
    def duration(self) -> float:
        if self._recording:
            return time.time() - self._start_time
        return self._last_duration

# ═══════════════════════════════════════════════════════════════
# STT：Windows SAPI（系统自带，零安装）
# ═══════════════════════════════════════════════════════════════

def _transcribe_sapi(wav_path: str) -> str:
    """使用 Windows SAPI 语音识别（需要中文语言包，否则返回空）"""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        try:
            engine = win32com.client.gencache.EnsureDispatch("SAPI.SpInprocRecognizer")
        except Exception:
            # 回退到 Dispatch（无类型库时也能用）
            engine = win32com.client.Dispatch("SAPI.SpInprocRecognizer")

        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(wav_path)

        # 尝试多种设置音频输入的方式
        try:
            engine.AudioInputStream = stream
        except Exception:
            try:
                engine.SetInput(stream, True)
            except Exception:
                pass

        # 执行识别
        result = engine.Recognize(1)  # SRSInactive
        if result and engine.Recognizer:
            return engine.Recognizer.PhraseInfo.GetText(0, -1, True)
        return ""
    except Exception as e:
        print(f"  [WARN] SAPI 识别失败 ({type(e).__name__}): 可能未安装中文语音包")
        return ""
    finally:
        pythoncom.CoUninitialize()


def _transcribe_google(wav_path: str) -> str:
    """使用 Google Web Speech API（走代理，需联网）"""
    import urllib.request
    import speech_recognition as sr

    # 安装代理 opener，让 speech_recognition 走代理
    proxy_handler = urllib.request.ProxyHandler({
        "http": PROXY_URL,
        "https": PROXY_URL,
    })
    opener = urllib.request.build_opener(proxy_handler)
    urllib.request.install_opener(opener)

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio, language="zh-CN")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"  [WARN] Google STT 不可用: {e}")
        raise


def _transcribe_aliyun(wav_path: str) -> str:
    """使用阿里云 DashScope Paraformer 语音识别（复用 QWEN_KEY）"""
    from http import HTTPStatus
    import dashscope
    from dashscope.audio.asr import Recognition

    dashscope.api_key = QWEN_KEY  # 复用现有密钥

    recognition = Recognition(
        model="paraformer-realtime-v2",
        format="wav",
        sample_rate=SAMPLE_RATE,
        language_hints=["zh"],
        callback=None,
    )
    result = recognition.call(wav_path)

    if result.status_code == HTTPStatus.OK:
        sentence = result.get_sentence()
        if sentence:
            # sentence 可能是 dict 或 list
            if isinstance(sentence, dict):
                text = sentence.get("text", "")
                if text:
                    return text.strip()
            elif isinstance(sentence, list) and sentence:
                # 列表形式：每项是 {"text": "..."}
                texts = []
                for s in sentence:
                    if isinstance(s, dict) and "text" in s:
                        texts.append(s["text"])
                if texts:
                    return "".join(texts).strip()
        return ""
    else:
        raise RuntimeError(f"阿里云 ASR: {result.message}")


# ═══════════════════════════════════════════════════════════════
# 科大讯飞 极速语音转写（HMAC-SHA256 签名）
# ═══════════════════════════════════════════════════════════════

def _iflytek_sign(host: str, date_str: str, request_line: str, body: bytes) -> tuple:
    """生成讯飞 HMAC-SHA256 签名，返回 (authorization, digest_header)"""
    import hashlib as _hl
    import hmac as _hmac
    import base64 as _b64

    body_digest = _hl.sha256(body).digest()
    body_digest_b64 = _b64.b64encode(body_digest).decode()
    digest_header = f"SHA-256={body_digest_b64}"

    signature_origin = (
        f"host: {host}\n"
        f"date: {date_str}\n"
        f"{request_line}\n"
        f"digest: {digest_header}"
    )

    signature_sha = _hmac.new(
        IFLYTEK_API_SECRET.encode(),
        signature_origin.encode(),
        _hl.sha256,
    ).digest()
    signature = _b64.b64encode(signature_sha).decode()

    authorization = (
        f'api_key="{IFLYTEK_API_KEY}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line digest", '
        f'signature="{signature}"'
    )
    return authorization, digest_header


def _transcribe_iflytek(wav_path: str) -> str:
    """使用科大讯飞极速语音转写（HTTP HMAC-SHA256 签名）

    流程: 上传文件 → 创建任务 → 轮询结果
    接口: https://www.xfyun.cn/doc/asr/speedTranscription/API.html
    """
    import json as _json
    import time as _time
    import os as _os
    import uuid as _uuid
    import hashlib as _hl
    import requests as _requests
    from email.utils import formatdate as _formatdate

    request_id = str(_uuid.uuid4())

    # ── 1. 读取文件（转换为 raw PCM，讯飞对 WAV 头解析不稳定）──
    import wave as _wave
    with _wave.open(wav_path, "rb") as wf:
        pcm_data = wf.readframes(wf.getnframes())
    file_name = _os.path.basename(wav_path).rsplit(".", 1)[0] + ".pcm"

    # ── 2. 上传文件 → 获取 audio_url ──
    host = "upload-ost-api.xfyun.cn"
    request_line = "POST /file/upload HTTP/1.1"
    date_str = _formatdate(timeval=None, localtime=False, usegmt=True)

    # 构建 multipart/form-data：app_id + request_id + data（raw PCM）
    boundary = "----WebKitFormBoundary" + _hl.md5(str(_time.time()).encode()).hexdigest()[:16]
    body_parts = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="app_id"\r\n\r\n'
        f"{IFLYTEK_APP_ID}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="request_id"\r\n\r\n'
        f"{request_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="data"; filename="{file_name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + pcm_data + f"\r\n--{boundary}--\r\n".encode()

    authorization, digest_header = _iflytek_sign(host, date_str, request_line, body_parts)

    r = _requests.post(
        f"https://{host}/file/upload",
        headers={
            "Host": host,
            "Date": date_str,
            "Authorization": authorization,
            "Digest": digest_header,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        data=body_parts,
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"讯飞上传失败 [{r.status_code}]: {r.text[:300]}")
    up_resp = r.json()
    if up_resp.get("code") != 0:
        raise RuntimeError(f"讯飞上传失败: {up_resp.get('message', r.text[:200])}")
    audio_url = up_resp["data"]["url"]

    # ── 3. 创建转写任务 → 获取 task_id ──
    # 正确结构: common + business + data 三段
    host = "ost-api.xfyun.cn"
    request_line = "POST /v2/ost/pro_create HTTP/1.1"
    date_str = _formatdate(timeval=None, localtime=False, usegmt=True)

    create_body = _json.dumps({
        "common": {"app_id": IFLYTEK_APP_ID},
        "business": {
            "request_id": request_id,
            "language": "zh_cn",
            "domain": "pro_ost_ed",
            "accent": "mandarin",
        },
        "data": {
            "audio_url": audio_url,
            "audio_src": "http",
            "format": "audio/L16;rate=16000",
            "encoding": "raw",
        },
    }).encode()

    authorization, digest_header = _iflytek_sign(host, date_str, request_line, create_body)

    r = _requests.post(
        f"https://{host}/v2/ost/pro_create",
        headers={
            "Host": host,
            "Date": date_str,
            "Authorization": authorization,
            "Digest": digest_header,
            "Content-Type": "application/json",
        },
        data=create_body,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"讯飞创建任务失败 [{r.status_code}]: {r.text[:300]}")
    task_resp = r.json()
    if task_resp.get("code") != 0:
        raise RuntimeError(f"讯飞创建任务失败: {task_resp.get('message', r.text[:200])}")
    task_id = task_resp["data"]["task_id"]

    # ── 4. 轮询获取结果 ──
    # 正确结构: common + business
    request_line = "POST /v2/ost/query HTTP/1.1"
    query_body = _json.dumps({
        "common": {"app_id": IFLYTEK_APP_ID},
        "business": {"task_id": task_id},
    }).encode()

    for i in range(60):  # 最多轮询 60 次
        _time.sleep(2.0)
        date_str = _formatdate(timeval=None, localtime=False, usegmt=True)
        authorization, digest_header = _iflytek_sign(host, date_str, request_line, query_body)

        try:
            q = _requests.post(
                f"https://{host}/v2/ost/query",
                headers={
                    "Host": host,
                    "Date": date_str,
                    "Authorization": authorization,
                    "Digest": digest_header,
                    "Content-Type": "application/json",
                },
                data=query_body,
                timeout=15,
            )
        except Exception:
            continue

        # 无论 HTTP 状态码如何，都尝试解析 JSON（服务器可能在非 200 响应中返回 task_status）
        try:
            qr = q.json()
        except Exception:
            continue

        task_status = qr.get("data", {}).get("task_status", "")
        code = qr.get("code", -1)

        # 3=转写完成, 4=回调完成
        if task_status in ("3", "4"):
            # code==0 表示成功，否则可能是无语音/格式问题
            if code != 0:
                msg = qr.get("message", str(code))
                raise RuntimeError(f"讯飞识别失败(code={code}): {msg}（音频可能无有效语音或格式不匹配）")

            lattice = qr.get("data", {}).get("result", {}).get("lattice", [])
            if not lattice:
                order_result = qr.get("data", {}).get("order_result", {})
                lattice = order_result.get("lattice", [])

            texts = []
            for item in lattice:
                json_1best = item.get("json_1best", {})
                st = json_1best.get("st", {})
                for sentence in st.get("rt", []):
                    words = []
                    for w in sentence.get("ws", []):
                        cw = w.get("cw", [])
                        if cw:
                            words.append(cw[0].get("w", ""))
                    if words:
                        texts.append("".join(words))

            result_text = "".join(texts)
            if result_text.strip():
                return result_text.strip()
            else:
                raise RuntimeError("讯飞返回空文本（音频中可能无有效语音）")

    raise RuntimeError("讯飞识别超时（120s 内未完成）")


def _transcribe_tencent(wav_path: str) -> str:
    """使用腾讯云语音识别（微信同款引擎，免费 5000次/月）

    短音频(≤60s): SentenceRecognition（一句话识别，快）
    长音频(>60s): CreateRecTask + DescribeTaskStatus（录音文件识别）
    """
    import base64, wave as _wave, time as _time
    from tencentcloud.common import credential
    from tencentcloud.asr.v20190614 import asr_client, models

    cred = credential.Credential(TENCENT_SECRET_ID, TENCENT_SECRET_KEY)
    client = asr_client.AsrClient(cred, "")

    with open(wav_path, "rb") as f:
        audio_data = f.read()

    # 计算音频时长
    with _wave.open(wav_path, "rb") as wf:
        duration = wf.getnframes() / wf.getframerate()

    audio_b64 = base64.b64encode(audio_data).decode("utf-8")

    if duration <= 60:
        # 短音频：一句话识别
        req = models.SentenceRecognitionRequest()
        req.EngSerViceType = "16k_zh"
        req.SourceType = 1
        req.VoiceFormat = "wav"
        req.Data = audio_b64
        req.DataLen = len(audio_data)
        resp = client.SentenceRecognition(req)
        return resp.Result.strip() if resp.Result else ""
    else:
        # 长音频：录音文件识别
        req = models.CreateRecTaskRequest()
        req.EngineModelType = "16k_zh"
        req.ChannelNum = 1
        req.ResTextFormat = 3
        req.SourceType = 1
        req.Data = audio_b64
        req.DataLen = len(audio_data)

        resp = client.CreateRecTask(req)
        task_id = resp.Data.TaskId

        # 轮询结果
        for _ in range(120):  # 最多等 120 次
            _time.sleep(1.0)
            q_req = models.DescribeTaskStatusRequest()
            q_req.TaskId = task_id
            q = client.DescribeTaskStatus(q_req)
            status = q.Data.StatusStr
            if status == "success":
                return q.Data.Result.strip() if q.Data.Result else ""
            elif status == "failed":
                raise RuntimeError(f"腾讯云识别失败: {q.Data.ErrorMsg}")

        raise RuntimeError("腾讯云识别超时（120s 内未完成）")


def _transcribe_baidu(wav_path: str) -> str:
    """使用百度语音识别 API（免费 10万次/月，中文识别效果好）"""
    from aip import AipSpeech

    client = AipSpeech(BAIDU_APP_ID, BAIDU_API_KEY, BAIDU_SECRET_KEY)

    with open(wav_path, "rb") as f:
        audio_data = f.read()

    result = client.asr(audio_data, "wav", SAMPLE_RATE, {"dev_pid": 1537})
    # dev_pid: 1537=普通话, 1737=英语, 1936=粤语, 3074=中英混合

    if result.get("err_no") == 0 and result.get("result"):
        return result["result"][0].strip()
    elif result.get("err_no") != 0:
        err_msg = result.get("err_msg", "未知错误")
        raise RuntimeError(f"百度 ASR: {err_msg} (err_no={result['err_no']})")
    return ""


def _transcribe_vosk(wav_path: str) -> str:
    """使用 Vosk 离线语音识别（纯离线，不需系统语音包）"""
    import json
    import vosk

    if not os.path.exists(VOSK_MODEL_PATH):
        raise FileNotFoundError(
            f"Vosk 模型未找到: {VOSK_MODEL_PATH}\n"
            "请下载: https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip\n"
            f"解压到: {VOSK_MODEL_PATH}"
        )

    model = vosk.Model(VOSK_MODEL_PATH)
    rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)

    with wave.open(wav_path, "rb") as wf:
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            rec.AcceptWaveform(data)

    result = json.loads(rec.FinalResult())
    return result.get("text", "").strip()


def _save_wav(audio: np.ndarray, path: str):
    """保存 int16 numpy 数组为 WAV 文件"""
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


# ═══════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════

class VoiceFlow:
    def __init__(self):
        self.recorder = Recorder()
        self.current_mode = "1"
        self._processing = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._streaming_stts: dict = {}       # {"tencent": TencentStreamingASR, "iflytek": IflytekStreamingASR}
        self._streaming_results: dict = {}   # {"tencent": "text...", "iflytek": "text..."}

    def _run_engine(self, name: str, wav_path: str) -> tuple[str, str, float]:
        """跑单个引擎，返回 (名称, 结果文本, 耗时)"""
        t0 = time.time()
        try:
            if name == "tencent":
                if name in self._streaming_results:
                    text = self._streaming_results[name]
                else:
                    text = _transcribe_tencent(wav_path)
            elif name == "aliyun":
                if name in self._streaming_results:
                    text = self._streaming_results[name]
                else:
                    text = _transcribe_aliyun(wav_path)
            elif name == "iflytek":
                if name in self._streaming_results:
                    text = self._streaming_results[name]
                else:
                    text = _transcribe_iflytek(wav_path)
            else:
                text = ""
        except Exception as e:
            text = f"❌ {e}"
        elapsed = time.time() - t0
        return (name, text.strip(), elapsed)

    def _transcribe_all(self, wav_path: str) -> dict:
        """三引擎并行转写"""
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(self._run_engine, name, wav_path): name
                for name in COMPARE_ENGINES
            }
            for future in concurrent.futures.as_completed(futures):
                name, text, elapsed = future.result()
                results[name] = (text, elapsed)
        return results

    def _on_press(self, key):
        if key == keyboard.Key.shift_r:
            if self._processing:
                print("\r[BUSY] 正在处理上一条...")
                return

            if not self.recorder._recording:
                # 启动三引擎全流式 ASR（边录边识别）
                self._streaming_results.clear()
                self._streaming_stts.clear()
                self.recorder.clear_streaming_stts()

                # 腾讯流式
                try:
                    tencent_stt = TencentStreamingASR(
                        TENCENT_SECRET_ID, TENCENT_SECRET_KEY, TENCENT_APP_ID)
                    tencent_stt.start()
                    self._streaming_stts["tencent"] = tencent_stt
                    self.recorder.add_streaming_stt(tencent_stt)
                    print("\n[STREAM] 腾讯流式 ASR 已连接")
                except Exception as e:
                    print(f"\n[WARN] 腾讯流式启动失败: {e}")

                # 讯飞流式
                try:
                    iflytek_stt = IflytekStreamingASR(
                        IFLYTEK_APP_ID, IFLYTEK_API_KEY, IFLYTEK_API_SECRET)
                    iflytek_stt.start()
                    self._streaming_stts["iflytek"] = iflytek_stt
                    self.recorder.add_streaming_stt(iflytek_stt)
                    print("[STREAM] 讯飞流式 ASR 已连接")
                except Exception as e:
                    print(f"[WARN] 讯飞流式启动失败: {e}")

                # 阿里流式（DashScope，复用 QWEN_KEY）
                try:
                    aliyun_stt = AliyunStreamingASR(QWEN_KEY)
                    aliyun_stt.start()
                    self._streaming_stts["aliyun"] = aliyun_stt
                    self.recorder.add_streaming_stt(aliyun_stt)
                    print("[STREAM] 阿里流式 ASR 已连接")
                except Exception as e:
                    print(f"[WARN] 阿里流式启动失败: {e}")

                self.recorder.start()
                stream_count = len(self._streaming_stts)
                print(f"[REC] 录音中... ({stream_count}引擎流式, 再按右Shift结束)")
            else:
                self._finish_recording()

    def _finish_recording(self):
        audio = self.recorder.stop()
        duration = self.recorder.duration

        # 停止所有流式 ASR，收集结果
        for name, stt in self._streaming_stts.items():
            try:
                t0 = time.time()
                result = stt.stop()
                elapsed = time.time() - t0
                if result:
                    self._streaming_results[name] = result
                    label = {"tencent": "腾讯", "iflytek": "讯飞"}.get(name, name)
                    print(f"\r[STREAM] {label}流式完成 ({elapsed:.1f}s): {result[:50]}...")
            except Exception as e:
                print(f"\r[STREAM] {name}流式异常: {e}")
        self._streaming_stts.clear()
        self.recorder.clear_streaming_stts()

        if audio is None:
            dur_str = f"{duration:.1f}" if duration else "0"
            print(f"\r[SKIP] 录音太短 ({dur_str}s)")
            self._show_hint()
            return

        print(f"\r[DONE] 录音 {duration:.1f}s -> 三引擎并行转写...")
        self._processing = True
        t_start = time.time()

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            _save_wav(audio, tmp.name)
            tmp.close()

            # 三引擎并行转写
            results = self._transcribe_all(tmp.name)
            t_stt = time.time()

            # ── 对比结果输出（流式标记 ★）──
            print(f"\n{'─' * 55}")
            total_stt = t_stt - t_start
            print(f"  ⏱  STT 总计: {total_stt:.1f}s")
            for name in COMPARE_ENGINES:
                label = COMPARE_ENGINE_NAMES[name]
                text, elapsed = results.get(name, ("N/A", 0))
                stream_tag = " ★流式" if (name in self._streaming_results) else ""
                print(f"  [{label}{stream_tag}] ({elapsed:.1f}s) {text}")
            print(f"{'─' * 55}")

            # LLM：整理模式三份全发让 LLM 自选最优，其他模式选最佳
            mode_cfg = PROMPTS[self.current_mode]
            full_prompt = ""
            fallback_text = ""

            if self.current_mode == "1":
                # 整理模式：三份转录一起发给 LLM 选最优 + 编排
                all_parts = []
                for name in COMPARE_ENGINES:
                    label = COMPARE_ENGINE_NAMES[name]
                    text = results.get(name, ("", 0))[0]
                    if text.strip():
                        all_parts.append(f"[{label}] {text}")
                if all_parts:
                    full_prompt = f"{mode_cfg['system']}\n\n三份语音转写结果：\n\n" + "\n\n".join(all_parts)
                    fallback_text = all_parts[0]
                    print(f"[LLM] {mode_cfg['name']} 筛选+编排中...")
            else:
                best_text = results.get("tencent", ("", 0))[0]
                if not best_text:
                    for name in COMPARE_ENGINES:
                        if results[name][0]:
                            best_text = results[name][0]
                            break
                if best_text:
                    full_prompt = f"{mode_cfg['system']}\n\n输入内容：\n{best_text}"
                    fallback_text = best_text
                    print(f"[LLM] {mode_cfg['name']} 编排中...")

            if full_prompt:
                try:
                    result: Optional[LLMResult] = None
                    for model_name, fn in [
                        ("Qwen-Plus", _call_qwen),
                        ("DeepSeek-Chat", _call_deepseek),
                        ("Gemini 2.0 Flash", _call_gemini),
                    ]:
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                fn(full_prompt, mode_cfg["temperature"]), self._loop
                            )
                            text = future.result(timeout=35)
                            result = LLMResult(text=text, model_used=model_name)
                            break
                        except Exception as e:
                            print(f"  [WARN] {model_name} unavailable: {str(e)[:60]}")
                    if result is None:
                        result = LLMResult(text=fallback_text, model_used="全部候选不可用")
                except Exception as e:
                    print(f"[ERR] LLM 调用异常: {e}")
                    result = LLMResult(text="", model_used="异常")

                t_end = time.time()
                print(f"\n{'=' * 55}")
                print(f"  STT: {t_stt - t_start:.1f}s | LLM: {t_end - t_stt:.1f}s | 总计: {t_end - t_start:.1f}s")
                print(f"  模型: {result.model_used}")
                print(f"  结果:\n{result.text}")
                print(f"{'=' * 55}")
            else:
                print("[WARN] 三个引擎均未识别到文本")

        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            self._processing = False
            self._show_hint()

    def _on_release(self, key):
        if key == keyboard.Key.esc:
            print("\n[EXIT] 退出中...")
            self._loop.call_soon_threadsafe(self._loop.stop)
        else:
            try:
                if hasattr(key, 'char') and key.char in PROMPTS:
                    self.current_mode = key.char
                    print(f"\n[MODE] {PROMPTS[self.current_mode]['name']}")
                    self._show_hint()
            except AttributeError:
                pass

    def _show_hint(self):
        modes = " | ".join(f"[{k}]{v['name']}" for k, v in PROMPTS.items())
        print(f"\n{modes} | [右Shift]录音(三引擎对比) | [Esc]退出")

    def run(self):
        if sys.platform == "win32":
            sys.stdout.reconfigure(encoding="utf-8")

        print("\n" + "=" * 55)
        print("  Voice Flow — 三引擎对比模式")
        print("  腾讯 vs 阿里 vs 讯飞  同时转写 + LLM 编排")
        print("=" * 55)
        print("  [右Shift]录音(三引擎同时) [1-7]切换模式 [Esc]退出\n")
        self._show_hint()

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        listener.start()

        try:
            self._loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            listener.stop()
            print("\n[DONE] 已退出")


def main():
    VoiceFlow().run()

if __name__ == "__main__":
    main()
