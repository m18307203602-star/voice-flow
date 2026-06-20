# -*- mode: python ; coding: utf-8 -*-
"""Voice Flow PyInstaller spec — 加密版（PyArmor + 单文件夹 + NSIS）"""

import sys
import os
from pathlib import Path

_SPEC_DIR = Path(os.path.abspath(SPECPATH)).parent
_PROJECT = Path(r"G:\voice-workflow")
_APP = _PROJECT / "voice_flow_app"
_BUILD_ENC = _PROJECT / "build" / "voice_flow_app_enc"
_RESOURCES = _APP / "resources"

# ── PySide6 插件收集 ──
import PySide6
_PYSIDE6 = Path(PySide6.__file__).parent

_block_cipher = None

a = Analysis(
    [str(_PROJECT / "build_tools" / "launcher_enc.py")],
    pathex=[
        str(_BUILD_ENC),           # 加密副本优先（必须在 _PROJECT 前面）
        str(_PROJECT),
    ],
    binaries=[
        # PyArmor 运行时解密引擎（原生 .pyd）
        (str(_BUILD_ENC / "pyarmor_runtime_000000" / "pyarmor_runtime.pyd"),
         "pyarmor_runtime_000000"),
    ],
    datas=[
        # PySide6 Qt 插件（窗口必须）
        (str(_PYSIDE6 / "plugins" / "platforms"), "PySide6/plugins/platforms"),
        (str(_PYSIDE6 / "plugins" / "styles"), "PySide6/plugins/styles"),
        (str(_PYSIDE6 / "plugins" / "imageformats"), "PySide6/plugins/imageformats"),
        (str(_PYSIDE6 / "plugins" / "tls"), "PySide6/plugins/tls"),
        # 音频资源
        (str(_RESOURCES / "sounds" / "start.wav"), "voice_flow_app/resources/sounds"),
        (str(_RESOURCES / "sounds" / "stop.wav"), "voice_flow_app/resources/sounds"),
    ],
    hiddenimports=[
        # PySide6
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        # numpy (sounddevice/recorder 依赖)
        "numpy", "numpy._core", "numpy.core._methods",
        # Windows-specific
        "win32api", "win32con", "win32gui", "win32process",
        "win32com", "pythoncom",
        # sounddevice
        "sounddevice", "_sounddevice_data",
        # httpx
        "httpx", "httpcore",
        # websocket
        "websocket",
        # pycaw
        "pycaw", "comtypes",
        # sqlite3 (C 扩展，PyInstaller 可能漏掉)
        "sqlite3", "_sqlite3", "sqlite3.dbapi2",
        # 标准库（PyArmor 加密后 PyInstaller 无法追踪导入）
        "wave", "ssl", "uuid", "queue", "webbrowser",
        "tempfile", "subprocess", "base64", "hmac",
        "secrets", "hashlib", "re", "json", "typing",
        "urllib", "urllib.parse", "datetime", "pathlib",
        "logging", "threading", "os", "sys", "time",
        "abc", "enum", "math", "platform", "ctypes",
        "concurrent", "concurrent.futures",
        # 第三方库（PyArmor 加密后无法追踪）
        "pyautogui", "pyperclip", "psutil",
        "cryptography", "cryptography.hazmat",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.hashes",
        "cryptography.hazmat.primitives.asymmetric",
        "cryptography.hazmat.primitives.asymmetric.padding",
        "cryptography.hazmat.primitives.serialization",
        "cryptography.exceptions",
        "win32api", "win32con", "win32gui", "win32process",
        "win32com", "pythoncom", "winsound", "winreg",
        "wintypes",
        # ── voice_flow_app (PyArmor 加密后 PyInstaller 无法静态分析导入，必须显式列出) ──
        "voice_flow_app",
        "voice_flow_app.__init__",
        "voice_flow_app.__main__",
        "voice_flow_app.config",
        "voice_flow_app.logger",
        "voice_flow_app.main",
        "voice_flow_app.prompts",
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
        "voice_flow_app.engine.translator",
        "voice_flow_app.license",
        "voice_flow_app.license.__init__",
        "voice_flow_app.license.client",
        "voice_flow_app.license.crypto",
        "voice_flow_app.license.fingerprint",
        "voice_flow_app.license.manager",
        "voice_flow_app.license.public_key",
        "voice_flow_app.output",
        "voice_flow_app.output.__init__",
        "voice_flow_app.output.text_detector",
        "voice_flow_app.output.text_injector",
        "voice_flow_app.storage",
        "voice_flow_app.storage.__init__",
        "voice_flow_app.storage.history_db",
        "voice_flow_app.ui",
        "voice_flow_app.ui.__init__",
        "voice_flow_app.ui.activation_dialog",
        "voice_flow_app.ui.analysis_browser",
        "voice_flow_app.ui.credential_sync",
        "voice_flow_app.ui.history_panel",
        "voice_flow_app.ui.login_dialog",
        "voice_flow_app.ui.main_window",
        "voice_flow_app.ui.settings_dialog",
        "voice_flow_app.ui.system_tray",
        "voice_flow_app.ui.translate_dialog",
        "voice_flow_app.ui.trial_banner",
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=_block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=_block_cipher)

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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceFlow",
)
