"""检测当前焦点窗口是否为文本输入框（Windows + macOS）"""
import logging
import os
import sys
from typing import Optional

log = logging.getLogger("voice_flow.detector")

try:
    import win32gui
    import win32process
    import win32api
    import psutil
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False
    log.warning("win32gui/psutil 未安装")


EDIT_CLASSES = {
    "Edit", "RichEditD2DPT", "RichEdit20W", "RichEdit20A",
    "RichEdit50W", "Scintilla", "TEdit", "TMemo",
    "TextEdit", "AceEditor", "CodeWindow",
}

BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe",
    "brave.exe", "opera.exe", "iexplore.exe",
}

# ── macOS 文本输入应用进程名 ──
MAC_TEXT_INPUT_APPS = {
    "Google Chrome", "Safari", "Firefox", "Brave Browser", "Opera",
    "Microsoft Edge", "Arc",
    "微信", "WeChat", "QQ", "钉钉", "DingTalk",
    "飞书", "Lark", "Telegram", "Slack", "Discord",
    "Visual Studio Code", "Code", "Sublime Text", "Sublime Merge",
    "Xcode", "IntelliJ IDEA", "PyCharm", "WebStorm",
    "TextEdit", "Pages", "Microsoft Word", "Word",
    "Terminal", "iTerm2", "Warp",
    "Obsidian", "Notion", "Notes",
    "Finder",
}

# 常见文本输入应用（Windows）
TEXT_INPUT_APPS = {
    "wechat.exe", "weixin.exe", "qq.exe", "dingtalk.exe",
    "feishu.exe", "lark.exe", "telegram.exe",
    "code.exe", "notepad++.exe", "sublime_text.exe",
    "devenv.exe", "idea64.exe", "pycharm64.exe", "webstorm64.exe",
    "notepad.exe", "wordpad.exe", "wps.exe", "winword.exe",
    "explorer.exe",
    "windows_terminal.exe", "conhost.exe", "obsidian.exe",
    "xmind.exe",
}


class TextFieldDetector:
    """检测焦点窗口中是否有文本输入框"""

    def __init__(self):
        self._saved_hwnd: Optional[int] = None
        self._saved_app: Optional[str] = None  # macOS 保存的应用名
        self._my_pid: int = os.getpid()

    def save_foreground(self):
        """保存当前前台窗口（在录音开始/结束时调用）"""
        if sys.platform == 'darwin':
            self._mac_save_foreground()
            return
        if not _WIN32_AVAILABLE:
            return
        try:
            self._saved_hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(self._saved_hwnd)
            title = win32gui.GetWindowText(self._saved_hwnd)
            class_name = win32gui.GetClassName(self._saved_hwnd)
            log.info("保存前台: hwnd=%d pid=%d title='%s' class='%s'",
                     self._saved_hwnd, pid, title[:60], class_name)
        except Exception as e:
            log.error("save_foreground 失败: %s", e)
            self._saved_hwnd = None

    def _mac_save_foreground(self):
        """macOS: 用 AppleScript 获取最前面应用名"""
        import subprocess
        try:
            script = 'tell application "System Events" to get name of first process whose frontmost is true'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2,
            )
            self._saved_app = result.stdout.strip()
            log.info("Mac 保存前台: app='%s'", self._saved_app)
        except Exception as e:
            log.error("Mac save_foreground 失败: %s", e)
            self._saved_app = None

    def _mac_is_text_field_focused(self) -> bool:
        """macOS: 检查最前面应用是否支持文本输入"""
        import subprocess
        # 策略1: 使用保存的应用名
        if getattr(self, '_saved_app', None):
            app = self._saved_app
            log.info("Mac 策略1: 检查保存应用 '%s'", app)
            if app in MAC_TEXT_INPUT_APPS:
                log.info("✓ Mac 策略1 命中: %s", app)
                return True

        # 策略2: 重新获取当前最前面应用
        try:
            script = 'tell application "System Events" to get name of first process whose frontmost is true'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2,
            )
            app = result.stdout.strip()
            log.info("Mac 策略2: 当前前台 '%s'", app)
            if app in MAC_TEXT_INPUT_APPS:
                log.info("✓ Mac 策略2 命中: %s", app)
                return True
        except Exception as e:
            log.debug("Mac 策略2 异常: %s", e)

        # 策略3: 宽松模式 — 前台非自身即可注入
        try:
            my_name = "VoiceFlow"  # .app bundle 名
            script = 'tell application "System Events" to get name of first process whose frontmost is true'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2,
            )
            app = result.stdout.strip()
            if app and app != my_name:
                log.info("Mac 策略3(宽松): 前台非自身, app='%s'", app)
                return True
        except Exception as e:
            log.debug("Mac 策略3 异常: %s", e)

        log.info("✗ Mac 所有策略失败")
        return False

    def is_text_field_focused(self) -> bool:
        """多策略检测是否有文本输入框"""
        if sys.platform == 'darwin':
            return self._mac_is_text_field_focused()
        if not _WIN32_AVAILABLE:
            log.warning("Win32 API 不可用，跳过检测")
            return False

        # 策略1: 检查保存的窗口（录音开始/结束时捕获）
        if self._saved_hwnd:
            log.info("策略1: 检查保存窗口 hwnd=%d", self._saved_hwnd)
            if self._check_hwnd(self._saved_hwnd):
                log.info("✓ 策略1 命中")
                return True

        # 策略2: 检查当前前台窗口（排除自身）
        try:
            current = win32gui.GetForegroundWindow()
            if current:
                _, pid = win32process.GetWindowThreadProcessId(current)
                log.info("策略2: 当前前台 hwnd=%d pid=%d (my_pid=%d)", current, pid, self._my_pid)
                if pid != self._my_pid:
                    if self._check_hwnd(current):
                        log.info("✓ 策略2 命中")
                        return True
        except Exception as e:
            log.debug("策略2 异常: %s", e)

        # 策略3: 宽松模式 — 只要前台不是自己，就假定可以注入
        # （用户按 Ctrl+Z 即可撤销，比完全不注入好）
        try:
            current = win32gui.GetForegroundWindow()
            if current:
                _, pid = win32process.GetWindowThreadProcessId(current)
                if pid != self._my_pid:
                    cls = win32gui.GetClassName(current)
                    title = win32gui.GetWindowText(current)
                    log.info("策略3(宽松): 前台非自身, pid=%d class='%s' title='%s'", pid, cls, title[:60])
                    return True
        except Exception as e:
            log.debug("策略3 异常: %s", e)

        log.info("✗ 所有策略失败")
        return False

    def _check_hwnd(self, hwnd: int) -> bool:
        """检查窗口进程是否属于文本输入应用，或焦点控件是否为编辑控件"""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                log.debug("_check_hwnd: 无法获取 PID")
                return False

            if pid == self._my_pid:
                log.debug("_check_hwnd: 窗口属于自身进程，跳过")
                return False

            proc = psutil.Process(pid)
            name = proc.name().lower()
            log.debug("_check_hwnd: 进程=%s (pid=%d)", name, pid)

            # 检查已知文本应用进程
            if name in BROWSER_PROCESSES:
                log.info("  → 浏览器: %s", name)
                return True
            if name in TEXT_INPUT_APPS:
                log.info("  → 文本应用: %s", name)
                return True

            # 深入检查焦点控件类名
            target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            current_tid = win32api.GetCurrentThreadId()

            attached = False
            if target_tid != current_tid:
                attached = win32process.AttachThreadInput(current_tid, target_tid, True)

            try:
                focus_hwnd = win32gui.GetFocus()
                if focus_hwnd:
                    fc = win32gui.GetClassName(focus_hwnd)
                    log.debug("  焦点控件 class='%s'", fc)
                    for ec in EDIT_CLASSES:
                        if ec.lower() in fc.lower():
                            log.info("  → 编辑控件: %s", ec)
                            return True
                else:
                    log.debug("  GetFocus() → NULL")
            finally:
                if attached:
                    win32process.AttachThreadInput(current_tid, target_tid, False)

        except Exception as e:
            log.debug("_check_hwnd 异常: %s", e)

        return False
