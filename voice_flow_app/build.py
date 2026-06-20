"""PyInstaller 打包脚本 — 生成单一 VoiceFlow.exe

使用方法:
    pip install pyinstaller
    python build.py

输出:
    dist/VoiceFlow.exe  ← 分发给用户的单文件
"""

import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "voice_flow_app"


def build():
    # 图标
    icon = APP_DIR / "resources" / "icon.ico"
    icon_arg = ["--icon", str(icon)] if icon.exists() else []

    # 数据文件（音效 + 图标）
    sounds_dir = APP_DIR / "resources" / "sounds"
    datas = []
    if sounds_dir.exists():
        datas.append(f"--add-data={sounds_dir}{os.pathsep}resources/sounds")
    if icon.exists():
        datas.append(f"--add-data={icon}{os.pathsep}resources/")

    # 隐藏导入（PyInstaller 可能检测不到的模块）
    hidden = [
        "--hidden-import=websocket",
        "--hidden-import=websocket._app",
        "--hidden-import=websocket._core",
        "--hidden-import=websocket._http",
        "--hidden-import=websocket._socket",
        "--hidden-import=win32gui",
        "--hidden-import=win32api",
        "--hidden-import=win32con",
        "--hidden-import=win32process",
        "--hidden-import=win32clipboard",
        "--hidden-import=pyperclip",
        "--hidden-import=sounddevice",
        "--hidden-import=numpy",
        "--hidden-import=httpx",
        "--hidden-import=cryptography",
        "--hidden-import=voice_flow_app.prompts_client",
    ]

    args = [
        str(APP_DIR / "__main__.py"),
        "--name=VoiceFlow",
        "--onefile",
        "--windowed",          # 不显示控制台窗口
        "--clean",
        "--noconfirm",
        f"--distpath={ROOT / 'dist'}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
        *icon_arg,
        *datas,
        *hidden,
    ]

    print(f"[BUILD] Starting VoiceFlow packaging...")
    print(f"   Source: {APP_DIR}")
    print(f"   Output: {ROOT / 'dist'}")

    PyInstaller.__main__.run(args)

    exe = ROOT / "dist" / "VoiceFlow.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"[DONE] Build complete: {exe} ({size_mb:.1f} MB)")
    else:
        print("[FAILED] Build failed: exe not generated")
        sys.exit(1)


if __name__ == "__main__":
    build()
