"""应用配置 — JSON 文件读写，存储 API 密钥和偏好"""
import json
import os
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".voice_flow"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "version": 1,
    "engines": {
        "tencent": {"secret_id": "", "secret_key": "", "app_id": ""},
        "aliyun": {"api_key": ""},
        "iflytek": {"app_id": "", "api_key": "", "api_secret": ""},
    },
    "llm": {
        "qwen_key": "",
        "qwen_flash_key": "",
        "deepseek_key": "",
        "gemini_key": "",
        "mimo_key": "",
        "proxy_url": "",
        "enabled": {
            "qwen": True,
            "qwen_flash": True,
            "deepseek": True,
            "gemini": True,
            "mimo": True,
        },
    },
    "preferences": {
        "selected_engines": ["tencent", "aliyun", "iflytek"],
        "selected_mode": "1",
        "recording_mode": "toggle",  # "toggle" | "hold"
        "recording_hotkey": [161],    # VK 码列表，默认 [右 Shift]；支持组合如 [17, 32] = Ctrl+Space
        "primary_model": "Qwen3.5-Flash",   # 主模型名称（用户可自主选择）
        "comparison_enabled": False,  # 多模型对比开关
        "comparison_models": ["Qwen-Plus"],  # 对比的模型列表（不含主模型）
        "update_url": "http://39.105.108.173:8000/api/version",  # 更新检查 URL
        "audio_capture_mode": "mic_only",  # "mic_only" | "loopback" | "both"
        "stt_mode": "short_first",   # STT 策略: "short_first"（短连接优先+流式兜底）| "streaming_only"（仅流式）
        "server_url": "http://39.105.108.173:8000",  # 提示词服务器地址
        "prompts_cache_ttl_days": 7,   # 提示词本地缓存有效期（天）
    },
    "auth": {
        "phone": "",
        "token": "",
        "auto_login": False,
    },
    "license": {
        "first_launch": 0.0,       # 首次启动 unix timestamp (0=未启动)
        "accepted_tos": False,      # 是否已同意服务条款
    },
}


class Config:
    """JSON 配置管理器"""

    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.loaded = False

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """深度合并两个字典，override 覆盖 base"""
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def load(self) -> bool:
        """加载配置，返回是否成功"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self.data = self._deep_merge(DEFAULT_CONFIG, saved)
                self.loaded = True
                return True
            except (json.JSONDecodeError, KeyError):
                pass
        self.data = DEFAULT_CONFIG.copy()
        self.loaded = True
        return False

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ---- 引擎密钥 ----

    def get_tencent_keys(self) -> tuple:
        e = self.data["engines"]["tencent"]
        return e["secret_id"], e["secret_key"], e["app_id"]

    def set_tencent_keys(self, secret_id: str, secret_key: str, app_id: str):
        self.data["engines"]["tencent"] = {
            "secret_id": secret_id, "secret_key": secret_key, "app_id": app_id
        }

    def get_aliyun_key(self) -> str:
        return self.data["engines"]["aliyun"]["api_key"]

    def set_aliyun_key(self, api_key: str):
        self.data["engines"]["aliyun"]["api_key"] = api_key

    def get_iflytek_keys(self) -> tuple:
        e = self.data["engines"]["iflytek"]
        return e["app_id"], e["api_key"], e["api_secret"]

    def set_iflytek_keys(self, app_id: str, api_key: str, api_secret: str):
        self.data["engines"]["iflytek"] = {
            "app_id": app_id, "api_key": api_key, "api_secret": api_secret
        }

    # ---- LLM 密钥 ----

    @property
    def qwen_key(self) -> str:
        return self.data["llm"]["qwen_key"]

    @qwen_key.setter
    def qwen_key(self, v: str):
        self.data["llm"]["qwen_key"] = v

    @property
    def deepseek_key(self) -> str:
        return self.data["llm"]["deepseek_key"]

    @deepseek_key.setter
    def deepseek_key(self, v: str):
        self.data["llm"]["deepseek_key"] = v

    @property
    def gemini_key(self) -> str:
        return self.data["llm"]["gemini_key"]

    @gemini_key.setter
    def gemini_key(self, v: str):
        self.data["llm"]["gemini_key"] = v

    @property
    def mimo_key(self) -> str:
        """小米 MiMo 大模型 API Key (OpenAI 兼容)"""
        return self.data["llm"]["mimo_key"]

    @mimo_key.setter
    def mimo_key(self, v: str):
        self.data["llm"]["mimo_key"] = v

    @property
    def qwen_flash_key(self) -> str:
        """通义千问 3.5 Flash Key（为空时复用 qwen_key）"""
        k = self.data["llm"].get("qwen_flash_key", "")
        return k if k.strip() else self.data["llm"]["qwen_key"]

    @qwen_flash_key.setter
    def qwen_flash_key(self, v: str):
        self.data["llm"]["qwen_flash_key"] = v

    @property
    def proxy_url(self) -> str:
        return self.data["llm"]["proxy_url"]

    @proxy_url.setter
    def proxy_url(self, v: str):
        self.data["llm"]["proxy_url"] = v

    def _ensure_llm_enabled(self):
        """兼容旧配置：确保 llm.enabled 字段存在"""
        if "enabled" not in self.data["llm"]:
            self.data["llm"]["enabled"] = {
                "qwen": True, "qwen_flash": True, "deepseek": True, "gemini": True, "mimo": True,
            }

    def is_llm_enabled(self, name: str) -> bool:
        """检查指定 LLM 是否启用（name: qwen/deepseek/gemini/mimo）"""
        self._ensure_llm_enabled()
        return self.data["llm"]["enabled"].get(name, True)

    def set_llm_enabled(self, name: str, enabled: bool):
        """设置指定 LLM 启用状态"""
        self._ensure_llm_enabled()
        self.data["llm"]["enabled"][name] = enabled

    # ---- 偏好 ----

    @property
    def selected_engines(self) -> list:
        return self.data["preferences"]["selected_engines"]

    @selected_engines.setter
    def selected_engines(self, v: list):
        self.data["preferences"]["selected_engines"] = v

    @property
    def selected_mode(self) -> str:
        return self.data["preferences"]["selected_mode"]

    @selected_mode.setter
    def selected_mode(self, v: str):
        self.data["preferences"]["selected_mode"] = v

    @property
    def recording_mode(self) -> str:
        return self.data["preferences"]["recording_mode"]

    @recording_mode.setter
    def recording_mode(self, v: str):
        assert v in ("toggle", "hold")
        self.data["preferences"]["recording_mode"] = v

    @property
    def recording_hotkey(self) -> list:
        """录音快捷键 VK 码列表，默认 [161] (右 Shift)；支持组合如 [17, 32] = Ctrl+Space"""
        v = self.data["preferences"].get("recording_hotkey", [161])
        if isinstance(v, int):
            return [v]  # 兼容旧版 int 格式
        return v

    @recording_hotkey.setter
    def recording_hotkey(self, vk_list: list):
        self.data["preferences"]["recording_hotkey"] = vk_list

    @property
    def comparison_enabled(self) -> bool:
        """多模型对比开关"""
        return self.data["preferences"].get("comparison_enabled", False)

    @comparison_enabled.setter
    def comparison_enabled(self, v: bool):
        self.data["preferences"]["comparison_enabled"] = v

    @property
    def primary_model(self) -> str:
        """主模型名称（用户可自主选择）"""
        return self.data["preferences"].get("primary_model", "Qwen3.5-Flash")

    @primary_model.setter
    def primary_model(self, v: str):
        self.data["preferences"]["primary_model"] = v

    @property
    def comparison_models(self) -> list:
        """对比的模型列表（不含主模型）"""
        return self.data["preferences"].get("comparison_models", ["Qwen-Plus"])

    @comparison_models.setter
    def comparison_models(self, v: list):
        self.data["preferences"]["comparison_models"] = v

    @property
    def update_url(self) -> str:
        """更新检查 URL，空字符串 = 不检查"""
        return self.data["preferences"].get("update_url", "")

    @update_url.setter
    def update_url(self, v: str):
        self.data["preferences"]["update_url"] = v

    @property
    def audio_capture_mode(self) -> str:
        """音频采集模式: "mic_only" | "loopback" | "both" """
        return self.data["preferences"].get("audio_capture_mode", "mic_only")

    @audio_capture_mode.setter
    def audio_capture_mode(self, v: str):
        self.data["preferences"]["audio_capture_mode"] = v

    @property
    def stt_mode(self) -> str:
        """STT 策略: "short_first"（短连接优先+流式兜底）| "streaming_only"（仅流式）"""
        return self.data["preferences"].get("stt_mode", "short_first")

    @stt_mode.setter
    def stt_mode(self, v: str):
        assert v in ("short_first", "streaming_only")
        self.data["preferences"]["stt_mode"] = v

    @property
    def server_url(self) -> str:
        """提示词服务器地址"""
        return self.data["preferences"].get("server_url", "http://39.105.108.173:8000")

    @server_url.setter
    def server_url(self, v: str):
        self.data["preferences"]["server_url"] = v

    @property
    def prompts_cache_ttl_days(self) -> int:
        """提示词本地缓存有效期（天）"""
        return self.data["preferences"].get("prompts_cache_ttl_days", 7)

    @prompts_cache_ttl_days.setter
    def prompts_cache_ttl_days(self, v: int):
        self.data["preferences"]["prompts_cache_ttl_days"] = v

    # ---- 认证 ----

    @property
    def auth_phone(self) -> str:
        return self.data["auth"]["phone"]

    @auth_phone.setter
    def auth_phone(self, v: str):
        self.data["auth"]["phone"] = v

    @property
    def auth_token(self) -> str:
        return self.data["auth"]["token"]

    @auth_token.setter
    def auth_token(self, v: str):
        self.data["auth"]["token"] = v

    @property
    def auth_auto_login(self) -> bool:
        return self.data["auth"]["auto_login"]

    @auth_auto_login.setter
    def auth_auto_login(self, v: bool):
        self.data["auth"]["auto_login"] = v

    def clear_auth(self):
        """清除登录凭据（退出登录时调用）"""
        self.data["auth"]["phone"] = ""
        self.data["auth"]["token"] = ""
        self.data["auth"]["auto_login"] = False
        self.save()

    # ---- 许可证 ----

    @property
    def license_first_launch(self) -> float:
        return self.data["license"].get("first_launch", 0.0)

    @license_first_launch.setter
    def license_first_launch(self, v: float):
        self.data["license"]["first_launch"] = v

    @property
    def license_accepted_tos(self) -> bool:
        return self.data["license"].get("accepted_tos", False)

    @license_accepted_tos.setter
    def license_accepted_tos(self, v: bool):
        self.data["license"]["accepted_tos"] = v

    # ---- 便利方法 ----

    def has_engine_keys(self, engine_name: str) -> bool:
        """检查某个引擎的密钥是否已填写"""
        e = self.data["engines"].get(engine_name, {})
        return any(v.strip() for v in e.values())

    def has_llm_keys(self) -> bool:
        """检查是否至少有一个 LLM 密钥"""
        llm = self.data["llm"]
        return bool(llm["qwen_key"].strip() or llm["qwen_flash_key"].strip() or llm["deepseek_key"].strip() or llm["gemini_key"].strip() or llm["mimo_key"].strip())

    def is_first_launch(self) -> bool:
        """是否首次启动（无任何引擎或 LLM 密钥）"""
        has_engine = any(self.has_engine_keys(e) for e in ["tencent", "aliyun", "iflytek"])
        return not has_engine and not self.has_llm_keys()
