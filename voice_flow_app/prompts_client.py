"""提示词客户端 — 纯在线模式，不落盘（无反编译风险）

每次启动从服务器获取提示词，不缓存到本地。
"""

import logging
import hashlib as _hl

log = logging.getLogger("voice_flow.prompts_client")

# ── 响应数据完整性校验（XOR 混淆存储，防字符串搜索） ──
_GUARD = bytes([154, 84, 181, 219, 132, 42, 177, 160, 157, 79, 200, 120, 126, 236, 127, 252])
_K = 0xAA


def _validate(data: dict) -> bool:
    """校验提示词数据完整性（SHA256 前 16 字节 XOR 比对）"""
    h = _hl.sha256(repr(data).encode()).digest()
    for i, b in enumerate(_GUARD):
        if (h[i] ^ _K) != b:
            return False
    return True


async def get_prompts(
    machine_code: str,
    license_payload: str,
    server_url: str,
    cache_ttl_days: int = 7,
) -> dict:
    """从服务器获取提示词 dict（在线模式，不缓存本地）

    Args:
        machine_code: 机器指纹
        license_payload: 许可证 payload
        server_url: 服务器地址
        cache_ttl_days: 未使用（保留兼容旧签名）

    Returns:
        与旧 PROMPTS 兼容的 dict: {"1": {name, temperature, system}, ...}

    Raises:
        RuntimeError: 服务器不可达
    """
    from .license.client import fetch_prompts

    try:
        log.info("Fetching prompts from server (%s)...", server_url)
        result = await fetch_prompts(machine_code, license_payload)

        if result.get("success") and result.get("prompts"):
            prompts = result["prompts"]
            if not _validate(prompts):
                raise RuntimeError("服务器返回数据异常，请稍后重试")
            log.info("Prompts fetched from server (v%s, %d modes)",
                     result.get("version"), len(prompts))
            return prompts
        else:
            raise RuntimeError(
                f"服务器返回错误: {result.get('message', '未知错误')}"
            )

    except RuntimeError:
        raise
    except Exception as e:
        log.error("Failed to fetch prompts from server: %s", e)
        raise RuntimeError(
            "无法加载处理配置: 服务器不可达。\n"
            "请检查网络连接后重试。"
        ) from e
