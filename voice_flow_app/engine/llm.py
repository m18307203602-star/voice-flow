"""LLM 调用链 — MiMo Flash → Qwen3.5-Flash → Qwen-Plus → DeepSeek-Chat → Gemini 2.0 Flash 五级降级"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional
import httpx

log = logging.getLogger("voice_flow.llm")


@dataclass
class LLMResult:
    text: str
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProcessor:
    """四级 LLM 降级调用链，支持代理"""

    def __init__(self, qwen_key: str, deepseek_key: str, gemini_key: str,
                 mimo_key: str = "", qwen_flash_key: str = "", proxy_url: str = "",
                 status_callback=None, enabled: dict = None):
        self.qwen_key = qwen_key
        self.qwen_flash_key = qwen_flash_key or qwen_key  # 空则复用 qwen_key
        self.deepseek_key = deepseek_key
        self.gemini_key = gemini_key
        self.mimo_key = mimo_key
        self.proxy_url = proxy_url
        self._cb = status_callback
        self._enabled = enabled or {}  # {"qwen": True, "qwen_flash": True, ...}

    def _log(self, msg: str):
        log.debug(msg)
        if self._cb:
            self._cb(msg)

    @property
    def available_models(self) -> list:
        """返回已启用且有密钥的模型列表 [(name, call_fn), ...]

        条件：1) Key 非空  2) 开关已启用（默认 True）
        """
        models = []
        if self.mimo_key and self.mimo_key.strip() and self._enabled.get("mimo", True):
            models.append(("MiMo Flash", self._call_mimo))
        if self.qwen_flash_key and self.qwen_flash_key.strip() and self._enabled.get("qwen_flash", True):
            models.append(("Qwen3.5-Flash", self._call_qwen_flash))
        if self.qwen_key and self.qwen_key.strip() and self._enabled.get("qwen", True):
            models.append(("Qwen-Plus", self._call_qwen))
        if self.deepseek_key and self.deepseek_key.strip() and self._enabled.get("deepseek", True):
            models.append(("DeepSeek-Chat", self._call_deepseek))
        if self.gemini_key and self.gemini_key.strip() and self._enabled.get("gemini", True):
            models.append(("Gemini 2.0 Flash", self._call_gemini))
        return models

    async def _call_mimo(self, user_text: str, temperature: float) -> tuple[str, dict]:
        """小米 MiMo Flash — OpenAI 兼容，¥0.7/百万in + ¥2/百万out"""
        url = "https://api.xiaomimimo.com/v1/chat/completions"
        headers = {"api-key": self.mimo_key, "Content-Type": "application/json"}
        body = {
            "model": "mimo-v2-flash",
            "messages": [{"role": "user", "content": user_text}],
            "temperature": temperature,
            "max_tokens": 2048,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            return (data["choices"][0]["message"]["content"].strip(),
                    {"prompt_tokens": usage.get("prompt_tokens", 0),
                     "completion_tokens": usage.get("completion_tokens", 0)})

    async def _call_gemini(self, user_text: str, temperature: float) -> tuple[str, dict]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}"
        body = {
            "contents": [{"parts": [{"text": user_text}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
        }
        proxy = self.proxy_url if self.proxy_url else None
        async with httpx.AsyncClient(proxy=proxy, timeout=15.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            meta = data.get("usageMetadata", {})
            return (data["candidates"][0]["content"]["parts"][0]["text"].strip(),
                    {"prompt_tokens": meta.get("promptTokenCount", 0),
                     "completion_tokens": meta.get("candidatesTokenCount", 0)})

    async def _call_qwen(self, user_text: str, temperature: float) -> tuple[str, dict]:
        """通义千问 Plus — ¥0.8/百万入 + ¥2/百万出（已关闭思考模式）"""
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.qwen_key}", "Content-Type": "application/json"}
        body = {
            "model": "qwen-plus",
            "messages": [{"role": "user", "content": user_text}],
            "temperature": temperature,
            "max_tokens": 2048,
            "enable_thinking": False,  # 语音润色无需推理，避免输出按 ¥8/百万 计费
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            return (data["choices"][0]["message"]["content"].strip(),
                    {"prompt_tokens": usage.get("prompt_tokens", 0),
                     "completion_tokens": usage.get("completion_tokens", 0)})

    async def _call_qwen_flash(self, user_text: str, temperature: float) -> tuple[str, dict]:
        """通义千问 3.5 Flash — 新一代轻量模型，¥0.2/百万入 + ¥0.4/百万出"""
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.qwen_flash_key}", "Content-Type": "application/json"}
        body = {
            "model": "qwen3.5-flash",
            "messages": [{"role": "user", "content": user_text}],
            "temperature": temperature,
            "max_tokens": 2048,
            "enable_thinking": False,  # 语音润色场景无需深度推理，关掉省 token
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            return (data["choices"][0]["message"]["content"].strip(),
                    {"prompt_tokens": usage.get("prompt_tokens", 0),
                     "completion_tokens": usage.get("completion_tokens", 0)})

    async def _call_deepseek(self, user_text: str, temperature: float) -> tuple[str, dict]:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.deepseek_key}", "Content-Type": "application/json"}
        body = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": user_text}],
            "temperature": temperature,
            "max_tokens": 2048,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            return (data["choices"][0]["message"]["content"].strip(),
                    {"prompt_tokens": usage.get("prompt_tokens", 0),
                     "completion_tokens": usage.get("completion_tokens", 0)})

    @staticmethod
    def _clean_output(text: str) -> str:
        """清理 LLM 输出中残留的引擎标签和三段式重复"""
        # 1. 去除引擎标签行（如 "[腾讯]"、"转写 #1" 等）
        text = re.sub(r'^\s*\[(?:腾讯|阿里|讯飞|tencent|aliyun|iflytek)\]\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*转写\s*#\d+\s*$', '', text, flags=re.MULTILINE)
        # 2. 去除引擎标签前缀（如 "腾讯："、"阿里："）
        text = re.sub(r'(?:腾讯|阿里|讯飞)[:：]\s*', '', text)
        # 3. 去除编号前缀（如 "转写 #1："）
        text = re.sub(r'转写\s*#\d+[:：]\s*', '', text)
        # 4. 压缩多余空行（最多保留连续两个换行）
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    async def process(self, text: str, system_prompt: str, temperature: float) -> LLMResult:
        full_prompt = f"{system_prompt}\n\n输入内容：\n{text}"

        candidates = self.available_models
        if not candidates:
            self._log("LLM: 无可用模型（所有 Key 为空）")
            return LLMResult(text=text, model_used="无可用模型")

        for name, fn in candidates:
            try:
                self._log(f"LLM: 尝试 {name}...")
                result, usage = await fn(full_prompt, temperature)
                cleaned = self._clean_output(result)
                self._log(f"LLM: {name} 成功")
                return LLMResult(text=cleaned, model_used=name,
                                 prompt_tokens=usage.get("prompt_tokens", 0),
                                 completion_tokens=usage.get("completion_tokens", 0))
            except Exception as e:
                err_msg = str(e)[:80]
                self._log(f"LLM: {name} 不可用 ({err_msg})")

        self._log("LLM: 全部候选不可用，返回原文")
        return LLMResult(text=text, model_used="全部候选不可用")

    async def process_parallel(self, text: str, system_prompt: str, temperature: float,
                                model_names: list) -> dict:
        """并行调用多个模型，返回 {name: {text, elapsed_ms, error}}

        Args:
            text: 输入文本
            system_prompt: 系统提示词
            temperature: 温度参数
            model_names: 模型名列表，如 ["MiMo Flash", "Qwen-Plus"]

        Returns:
            {model_name: {"text": str, "elapsed_ms": float, "error": str|None}}
        """
        full_prompt = f"{system_prompt}\n\n输入内容：\n{text}"

        # 只取有 Key 的模型
        available = {name: fn for name, fn in self.available_models}
        valid_models = [n for n in model_names if n in available]

        if not valid_models:
            self._log("对比: 请求的模型均无可用 Key，跳过")
            return {}

        async def _call_one(name, fn):
            t0 = time.time()
            try:
                self._log(f"对比: 调用 {name} ...")
                result, usage = await fn(full_prompt, temperature)
                elapsed = round((time.time() - t0) * 1000)
                cleaned = self._clean_output(result)
                self._log(f"对比: {name} 完成 ({elapsed}ms)")
                return name, {"text": cleaned, "elapsed_ms": elapsed, "error": None,
                              "prompt_tokens": usage.get("prompt_tokens", 0),
                              "completion_tokens": usage.get("completion_tokens", 0)}
            except Exception as e:
                elapsed = round((time.time() - t0) * 1000)
                self._log(f"对比: {name} 失败 ({elapsed}ms): {e}")
                return name, {"text": "", "elapsed_ms": elapsed, "error": str(e)[:100],
                              "prompt_tokens": 0, "completion_tokens": 0}

        tasks = [_call_one(name, available[name]) for name in valid_models]

        results = {}
        for name, data in await asyncio.gather(*tasks):
            results[name] = data
        return results
