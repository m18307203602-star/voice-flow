# -*- mode: python ; coding: utf-8 -*-
"""Voice Flow macOS PyInstaller spec — .app bundle"""

import sys
import os
from pathlib import Path

_PROJECT = Path(os.path.abspath(SPECPATH)).parent  # SPECPATH = build_tools/, parent = 项目根
_APP = _PROJECT / "voice_flow_app"

# ── PySide6 插件收集 ──
import PySide6
_PYSIDE6 = Path(PySide6.__file__).parent

block_cipher = None  # macOS 不需要字节码加密

a = Analysis(
    [str(_PROJECT / "build_tools" / "launcher.py")],
    pathex=[str(_PROJECT)],
    binaries=[],
    datas=[
        # PySide6 Qt 插件
        (_PYSIDE6 / "plugins" / "platforms", "PySide6/plugins/platforms"),
        (_PYSIDE6 / "plugins" / "styles", "PySide6/plugins/styles"),
        (_PYSIDE6 / "plugins" / "imageformats", "PySide6/plugins/imageformats"),
        (_PYSIDE6 / "plugins" / "tls", "PySide6/plugins/tls"),
        # 音频资源
        (str(_APP / "resources" / "sounds" / "start.wav"), "voice_flow_app/resources/sounds"),
        (str(_APP / "resources" / "sounds" / "stop.wav"), "voice_flow_app/resources/sounds"),
    ],
    hiddenimports=[
        # PySide6
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtNetwork", "PySide6.QtMultimedia",
        # numpy (sounddevice/recorder 依赖)
        "numpy", "numpy._core", "numpy._core._exceptions",
        "numpy._core._methods", "numpy.core._methods",
        "numpy._core.multiarray", "numpy._core.umath",
        # sounddevice
        "sounddevice", "_sounddevice_data",
        # httpx
        "httpx", "httpcore",
        # websocket
        "websocket",
        # sqlite3 (C 扩展，PyInstaller 可能漏掉)
        "sqlite3", "_sqlite3", "sqlite3.dbapi2",
        # 标准库
        "wave", "ssl", "uuid", "queue", "webbrowser",
        "tempfile", "subprocess", "base64", "hmac",
        "secrets", "hashlib", "re", "json", "typing",
        "urllib", "urllib.parse", "datetime", "pathlib",
        "logging", "threading", "os", "sys", "time",
        "abc", "enum", "math", "ctypes",
        "concurrent", "concurrent.futures",
        # 第三方库（跨平台）
        "pyautogui", "pyperclip", "psutil",
        "pynput", "pynput.keyboard", "pynput.keyboard._darwin",
        "cryptography", "cryptography.hazmat",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.hashes",
        "cryptography.hazmat.primitives.asymmetric",
        "cryptography.hazmat.primitives.asymmetric.padding",
        "cryptography.hazmat.primitives.serialization",
        "cryptography.exceptions",
        "paramiko",
        # ── voice_flow_app 模块 ──
        "voice_flow_app",
        "voice_flow_app.__init__",
        "voice_flow_app.__main__",
        "voice_flow_app.config",
        "voice_flow_app.dictionary",
        "voice_flow_app.logger",
        "voice_flow_app.main",
        "voice_flow_app.prompts",
        "voice_flow_app.prompts_client",
        "voice_flow_app.updater",
        "voice_flow_app.version",
        "voice_flow_app.audio",
        "voice_flow_app.audio.__init__",
        "voice_flow_app.audio.audio_muter",
        "voice_flow_app.auth",
        "voice_flow_app.auth.__init__",
        "voice_flow_app.auth.backend",
        "voice_flow_app.engine",
        "voice_flow_app.engine.__init__",
        "voice_flow_app.engine.llm",
        "voice_flow_app.engine.recorder",
        "voice_flow_app.engine.session",
        "voice_flow_app.engine.stt_aliyun",
        "voice_flow_app.engine.stt_iflytek",
        "voice_flow_app.engine.stt_tencent",
        "voice_flow_app.engine.stt_tencent_sentence",
        "voice_flow_app.engine.translator",
        "voice_flow_app.license",
        "voice_flow_app.license.__init__",
        "voice_flow_app.license.client",
        "voice_flow_app.license.crypto",
        "voice_flow_app.license.fingerprint",
        "voice_flow_app.license.manager",
        "voice_flow_app.license.public_key",
        "voice_flow_app.license.sysinfo",
        "voice_flow_app.output",
        "voice_flow_app.output.__init__",
        "voice_flow_app.output.text_detector",
        "voice_flow_app.output.text_injector",
        "voice_flow_app.storage",
        "voice_flow_app.storage.__init__",
        "voice_flow_app.storage.history_db",
        "voice_flow_app.system",
        "voice_flow_app.system.__init__",
        "voice_flow_app.system.autostart",
        "voice_flow_app.ui",
        "voice_flow_app.ui.__init__",
        "voice_flow_app.ui.activation_dialog",
        "voice_flow_app.ui.analysis_browser",
        "voice_flow_app.ui.credential_sync",
        "voice_flow_app.ui.dictionary_dialog",
        "voice_flow_app.ui.dictionary_widget",
        "voice_flow_app.ui.history_panel",
        "voice_flow_app.ui.login_dialog",
        "voice_flow_app.ui.main_window",
        "voice_flow_app.ui.settings_dialog",
        "voice_flow_app.ui.sidebar",
        "voice_flow_app.ui.stats_page",
        "voice_flow_app.ui.system_tray",
        "voice_flow_app.ui.translate_dialog",
        "voice_flow_app.ui.trial_banner",
        "voice_flow_app.ui.usage_stats_dialog",
        "voice_flow_app.ui.voiceprint_widget",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pandas",
        "PIL", "cv2", "torch", "tensorflow",
        "jupyter", "ipython", "notebook",
        "pip", "setuptools", "pkg_resources",
        "test", "tests", "unittest",
        # Windows 专用（Mac 构建不安装这些）
        "pycaw", "win32api", "win32con", "win32gui",
        "win32process", "win32com", "pythoncom", "comtypes",
        "winsound", "winreg", "wintypes", "wmi",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VoiceFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_APP / "resources" / "icon.ico") if (_APP / "resources" / "icon.ico").exists() else None,
)

# macOS .app Bundle
app = BUNDLE(
    exe,
    name="VoiceFlow.app",
    icon=str(_APP / "resources" / "icon.ico") if (_APP / "resources" / "icon.ico").exists() else None,
    bundle_identifier="com.voiceflow.app",
    info_plist={
        "CFBundleShortVersionString": "3.0.0",
        "CFBundleVersion": "3.0.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Voice Flow needs microphone access for speech recognition.",
        "NSAppleEventsUsageDescription": "Voice Flow needs Accessibility access to detect text fields and inject text.",
    },
)
