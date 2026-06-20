"""腾讯云一句话识别 — HTTP 短连接（≤60s 音频）

比 WebSocket 流式更简单、更快：
- 无需建连/握手，直接 POST
- 免费额度：5,000 次/月（vs 流式 5 小时/月）
- 签名方式：腾讯云 API 3.0 TC3-HMAC-SHA256
"""

import hashlib
import hmac
import base64
import json
import time
import struct
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

import httpx

log = logging.getLogger("voice_flow.stt.tencent_sentence")


def _sign_tc3(secret_id: str, secret_key: str, service: str, host: str,
              action: str, version: str, region: str, payload: str) -> dict:
    """腾讯云 API 3.0 TC3-HMAC-SHA256 签名，返回请求头"""
    algorithm = "TC3-HMAC-SHA256"
    timestamp = str(int(time.time()))
    date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m-%d")

    # ── 1. CanonicalRequest ──
    http_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\nx-tc-action:{action.lower()}\n"
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"{http_method}\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    )

    # ── 2. StringToSign ──
    credential_scope = f"{date}/{service}/tc3_request"
    hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical}"

    # ── 3. Signature ──
    def _hmac_sha256(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()

    # ── 4. Authorization ──
    authorization = (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": timestamp,
        "X-TC-Region": region,
    }


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000,
                channels: int = 1, bits: int = 16) -> bytes:
    """给 PCM 裸数据加 WAV 头"""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    data_len = len(pcm_bytes)
    wav = bytearray()
    # RIFF header
    wav += b"RIFF"
    wav += struct.pack("<I", 36 + data_len)
    wav += b"WAVE"
    # fmt chunk
    wav += b"fmt "
    wav += struct.pack("<I", 16)          # chunk size
    wav += struct.pack("<H", 1)           # PCM
    wav += struct.pack("<H", channels)
    wav += struct.pack("<I", sample_rate)
    wav += struct.pack("<I", byte_rate)
    wav += struct.pack("<H", block_align)
    wav += struct.pack("<H", bits)
    # data chunk
    wav += b"data"
    wav += struct.pack("<I", data_len)
    wav += pcm_bytes
    return bytes(wav)


class TencentSentenceASR:
    """腾讯云一句话识别 — HTTP POST 短连接

    接口兼容流式 STT（start / feed / stop），但实际在 stop() 时一次性发送。
    """

    API_HOST = "asr.tencentcloudapi.com"
    API_SERVICE = "asr"
    API_VERSION = "2019-06-14"
    API_REGION = "ap-guangzhou"

    def __init__(self, secret_id: str, secret_key: str, app_id: str,
                 status_callback: Optional[Callable[[str], None]] = None):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.app_id = app_id
        self._cb = status_callback
        self._buffer: bytearray = bytearray()
        self._started = False

    def _log(self, msg: str):
        if self._cb:
            self._cb(msg)
        log.debug(msg)

    # ── 流式兼容接口 ──

    def start(self):
        """无需建连，仅重置缓冲区"""
        self._buffer = bytearray()
        self._started = True
        self._log("腾讯短连接: 就绪")

    def feed(self, pcm_bytes: bytes):
        """累积音频（不发送，等 stop 时一次性 POST）"""
        if self._started:
            self._buffer.extend(pcm_bytes)

    def stop(self) -> str:
        """发送 HTTP POST，返回识别文本"""
        self._started = False

        if len(self._buffer) == 0:
            raise RuntimeError("腾讯短连接: 无音频数据")

        # PCM → WAV
        wav_bytes = _pcm_to_wav(bytes(self._buffer))
        data_b64 = base64.b64encode(wav_bytes).decode()
        data_len = len(wav_bytes)

        # 构造请求
        payload = json.dumps({
            "ProjectId": 0,
            "SubServiceType": 2,       # 2=一句话识别
            "EngSerViceType": "16k_zh", # 引擎模型类型（16k中文通用）
            "SourceType": 1,            # 1=Base64音频数据
            "VoiceFormat": "wav",
            "Data": data_b64,
            "DataLen": data_len,
        })

        headers = _sign_tc3(
            self.secret_id, self.secret_key,
            self.API_SERVICE, self.API_HOST,
            "SentenceRecognition", self.API_VERSION, self.API_REGION,
            payload,
        )

        self._log("腾讯短连接: 发送请求...")
        t0 = time.time()

        try:
            resp = httpx.post(
                f"https://{self.API_HOST}/",
                headers=headers,
                content=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            elapsed = time.time() - t0
            raise RuntimeError(f"腾讯短连接请求失败 ({elapsed:.1f}s): {e}")

        elapsed_ms = (time.time() - t0) * 1000

        # 解析响应
        if "Response" not in result:
            raise RuntimeError(f"腾讯短连接: 无效响应 {json.dumps(result, ensure_ascii=False)[:200]}")

        resp_data = result["Response"]
        if "Error" in resp_data:
            err = resp_data["Error"]
            raise RuntimeError(
                f"腾讯短连接 [{err.get('Code')}]: {err.get('Message', '未知错误')}"
            )

        text = resp_data.get("Result", "").strip()
        audio_dur = resp_data.get("AudioDuration", 0) / 1000
        self._log(f"腾讯短连接: {len(text)} 字, {elapsed_ms:.0f}ms, 音频 {audio_dur:.1f}s")
        log.info("腾讯短连接识别完成: %d 字, %.0fms", len(text), elapsed_ms)

        if not text:
            raise RuntimeError("腾讯短连接: 识别结果为空（可能太短或静音）")

        return text
