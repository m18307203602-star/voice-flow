"""版本更新模块 — 检查、下载、替换、重启

更新清单格式 (JSON, 托管在 update_url):
{
  "version": "1.0.1",
  "url": "https://example.com/VoiceFlow-1.0.1.exe",
  "size": 45678901,
  "notes": "更新说明（可选）"
}
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

import httpx

from .version import __version__

log = logging.getLogger("voice_flow.updater")


@dataclass
class UpdateInfo:
    version: str
    url: str
    size: int = 0
    notes: str = ""


def _parse_semver(version_str: str) -> tuple:
    """解析 "1.0.0" / "v1.0.0" → (1, 0, 0)"""
    v = version_str.lstrip("v")
    parts = v.split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except (ValueError, IndexError):
        return (0, 0, 0)


def _is_newer(remote: str, local: str) -> bool:
    """remote 版本是否比 local 新"""
    return _parse_semver(remote) > _parse_semver(local)


async def check_for_update(update_url: str) -> Optional[UpdateInfo]:
    """检查是否有新版本可用

    Args:
        update_url: 更新清单 JSON 的 URL

    Returns:
        UpdateInfo 如果有新版本, 否则 None
    """
    if not update_url or not update_url.strip():
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(update_url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("更新检查失败: %s", e)
        return None

    remote_version = data.get("version", "")
    if not remote_version:
        return None

    if not _is_newer(remote_version, __version__):
        log.info("当前已是最新版本 (%s)", __version__)
        return None

    log.info("发现新版本: %s → %s", __version__, remote_version)
    return UpdateInfo(
        version=remote_version,
        url=data.get("url", ""),
        size=data.get("size", 0),
        notes=data.get("notes", ""),
    )


async def download_update(info: UpdateInfo, progress_cb: Optional[Callable] = None) -> str:
    """下载新版本 .exe 到临时文件

    Args:
        info: 更新信息
        progress_cb: 进度回调 (downloaded_bytes, total_bytes) -> None

    Returns:
        下载的临时文件路径

    Raises:
        RuntimeError: 下载失败
    """
    if not info.url:
        raise RuntimeError("更新 URL 为空")

    # 下载到目标目录旁边的 .new 文件
    exe_dir = os.path.dirname(sys.executable)
    new_path = os.path.join(exe_dir, "VoiceFlow_new.exe")

    log.info("开始下载 %s → %s (%s 字节)", info.version, new_path, info.size or "未知")

    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        async with client.stream("GET", info.url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))

            downloaded = 0
            with open(new_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)

    # 校验
    if total > 0 and downloaded < total:
        os.remove(new_path)
        raise RuntimeError(f"下载不完整: {downloaded}/{total} 字节")

    if not os.path.exists(new_path) or os.path.getsize(new_path) == 0:
        raise RuntimeError("下载文件为空")

    log.info("下载完成: %s (%s 字节)", new_path, downloaded)
    return new_path


def install_and_restart(new_exe_path: str):
    """替换当前 exe 并重启

    写一个临时 .bat 脚本:
      1. 等待当前进程退出
      2. 用新 exe 覆盖旧 exe
      3. 启动新 exe
      4. 删除自身 .bat
    """
    old_exe = sys.executable

    if not os.path.exists(old_exe):
        log.error("找不到当前 exe: %s", old_exe)
        return

    # 写重启脚本
    pid = os.getpid()
    bat_content = f'''@echo off
chcp 65001 > nul
echo Voice Flow 正在更新...

:wait
timeout /t 1 /nobreak > nul
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if %errorlevel% equ 0 goto wait

move /y "{new_exe_path}" "{old_exe}"
if %errorlevel% neq 0 (
    echo 替换失败，请手动将 {new_exe_path} 覆盖到 {old_exe}
    pause
    exit /b 1
)

echo 更新完成，启动新版本...
start "" "{old_exe}"
del "%~f0"
'''

    bat_path = os.path.join(tempfile.gettempdir(), "voice_flow_update.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    log.info("执行更新脚本: %s", bat_path)
    if sys.platform == 'win32':
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
            shell=False,
        )
    elif sys.platform == 'darwin':
        # macOS: write bash script and execute detached
        sh_path = os.path.join(tempfile.gettempdir(), "voice_flow_update.sh")
        with open(sh_path, "w") as f:
            f.write(f'''#!/bin/bash
sleep 2
mv -f "{new_exe_path}" "{old_exe}"
open "{old_exe}"
rm -f "$0"
''')
        os.chmod(sh_path, 0o755)
        subprocess.Popen(["/bin/bash", sh_path], start_new_session=True)


def install_on_reboot(new_exe_path: str) -> str | None:
    """下载完成后，安排下次系统启动时自动替换并启动新版本

    原理:
      1. 把新 exe 复制到安装目录（VoiceFlow_new.exe）
      2. 写一个 .bat 替换脚本到安装目录
      3. 注册 HKCU RunOnce，系统重启后自动执行 .bat
      4. .bat 负责: 替换旧 exe → 启动新版本 → 清理自身

    Returns:
        安装目录路径（供显示用），失败返回 None
    """
    old_exe = sys.executable

    if not os.path.exists(old_exe):
        log.error("找不到当前 exe: %s", old_exe)
        return None

    install_dir = os.path.dirname(old_exe)
    dest_new = os.path.join(install_dir, "VoiceFlow_new.exe")

    # 1. 复制新 exe 到安装目录
    import shutil
    try:
        shutil.copy2(new_exe_path, dest_new)
        log.info("新版本已复制: %s", dest_new)
    except Exception as e:
        log.error("复制新版本失败: %s", e)
        return None

    # 2. 写替换脚本（系统启动时由 RunOnce 执行 — 仅 Windows）
    if sys.platform == 'win32':
        bat_path = os.path.join(install_dir, "voiceflow_update_onboot.bat")
        bat_content = f'''@echo off
chcp 65001 > nul
echo Voice Flow 正在更新至最新版本...

:: 等待系统完全就绪
timeout /t 5 /nobreak > nul

:: 替换旧 exe
move /y "{dest_new}" "{old_exe}"
if %errorlevel% neq 0 (
    echo 替换失败，请手动将 {dest_new} 覆盖到 {old_exe}
    pause
    exit /b 1
)

echo 更新完成，启动 Voice Flow...
start "" "{old_exe}"
del "%~f0"
'''

        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
            log.info("替换脚本已写入: %s", bat_path)
        except Exception as e:
            log.error("写入替换脚本失败: %s", e)
            return None

        # 3. 注册 HKCU RunOnce（系统启动时执行一次）
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "VoiceFlowUpdate", 0, winreg.REG_SZ, bat_path)
            winreg.CloseKey(key)
            log.info("已注册 RunOnce: %s", bat_path)
        except Exception as e:
            log.error("注册 RunOnce 失败: %s", e)
            # 清理已复制的文件
            try:
                os.remove(dest_new)
                os.remove(bat_path)
            except Exception:
                pass
            return None
    else:
        # macOS: 重启更新不适用，引导用户手动替换
        log.info("macOS: 新版本已复制到 %s，请手动替换 %s", dest_new, old_exe)

    return install_dir
