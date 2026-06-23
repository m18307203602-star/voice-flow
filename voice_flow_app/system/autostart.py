"""开机自启动 — Windows 注册表 / Mac LaunchAgent"""
import sys
import os
from pathlib import Path


def _get_app_command() -> str | None:
    """返回注册到系统的启动命令字符串（供 Windows/Mac 使用）

    PyInstaller 打包后: sys.executable → VoiceFlow.exe
    开发模式: sys.executable → python.exe，构造 "pythonw.exe script.py"
    """
    exe = sys.executable

    # PyInstaller 打包检测
    if getattr(sys, 'frozen', False):
        return exe

    # 开发模式：用 pythonw（无控制台窗口），cd 到项目根再启动
    pythonw = exe.replace("python.exe", "pythonw.exe")
    project_dir = Path(__file__).resolve().parent.parent.parent  # voice_flow_app → G:\voice-workflow
    return f'cmd /c "cd /d {project_dir} && start "" "{pythonw}" -m voice_flow_app"'


def is_enabled() -> bool:
    """检查是否已设置开机自启动"""
    if sys.platform == 'win32':
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ,
            )
            try:
                value, _ = winreg.QueryValueEx(key, "VoiceFlow")
                return bool(value)
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    elif sys.platform == 'darwin':
        plist = Path.home() / "Library/LaunchAgents/com.voiceflow.app.plist"
        return plist.exists()

    return False


def enable() -> bool:
    """开启开机自启动"""
    cmd = _get_app_command()
    if not cmd:
        return False

    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, "VoiceFlow", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            return True

        elif sys.platform == 'darwin':
            plist_dir = Path.home() / "Library/LaunchAgents"
            plist_dir.mkdir(parents=True, exist_ok=True)
            plist = plist_dir / "com.voiceflow.app.plist"
            plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voiceflow.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>{cmd}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>""")
            return True

    except Exception:
        return False


def disable() -> bool:
    """关闭开机自启动"""
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, "VoiceFlow")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            return True

        elif sys.platform == 'darwin':
            plist = Path.home() / "Library/LaunchAgents/com.voiceflow.app.plist"
            if plist.exists():
                plist.unlink()
            return True

        return False
    except Exception:
        return False


def set_enabled(enabled: bool) -> bool:
    """统一接口：开启或关闭自启动"""
    return enable() if enabled else disable()
