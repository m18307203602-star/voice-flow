"""机器指纹生成 — 硬件绑定，换主板需重新激活"""
import hashlib
import platform
import subprocess
import sys
import uuid


def generate_machine_code() -> str:
    """
    生成稳定的硬件指纹。

    组合:
      1. 主板序列号 (wmic baseboard) — 最稳定，换主板才变
      2. MachineGUID (注册表) — Windows 安装时生成，换GPU/内存/驱动不受影响
      3. CPU ID
      4. 网卡 UUID (补充唯一性)

    Returns: 32 位 hex 字符串 (SHA-256 截断)
    """
    parts: list[str] = []

    # 1. 主板序列号（仅 Windows wmic）
    if sys.platform == 'win32':
        try:
            result = subprocess.run(
                ["wmic", "baseboard", "get", "serialnumber"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [
                l.strip()
                for l in result.stdout.splitlines()
                if l.strip() and l.strip() != "SerialNumber"
            ]
            if lines:
                parts.append(lines[0])
        except Exception:
            pass
    elif sys.platform == 'darwin':
        # macOS 用 system_profiler 获取硬件 UUID 作为主板替代
        try:
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "Hardware UUID" in line:
                    parts.append(line.strip().split(":")[-1].strip())
                    break
        except Exception:
            pass

    # 2. 操作系统级别标识
    if sys.platform == 'win32':
        # Windows MachineGUID (注册表)
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            parts.append(guid)
            winreg.CloseKey(key)
        except Exception:
            pass
    elif sys.platform == 'darwin':
        # macOS IOPlatformUUID（硬件唯一标识）
        try:
            result = subprocess.run(
                ["ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    uuid_str = line.strip().split('"')[-2]
                    parts.append(uuid_str)
                    break
        except Exception:
            pass

    # 3. CPU 标识
    parts.append(platform.processor() or "")

    # 4. 网卡 UUID
    parts.append(str(uuid.getnode()))

    # 如果收集的信息太少，使用随机回退
    raw = "|".join(parts)
    if len(raw.replace("|", "").strip()) < 20:
        import secrets
        raw = f"fallback-{secrets.token_hex(32)}"

    return hashlib.sha256(raw.encode()).hexdigest()[:32]
