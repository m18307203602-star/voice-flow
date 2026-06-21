"""Voice Flow 桌面应用入口 — QApplication + 全局热键 + 窗口启动"""
import sys
import os
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtCore import Qt, QTimer

from .logger import setup_logging

# 支持两种运行方式：python -m voice_flow_app / python voice_flow_app/main.py
try:
    from .config import Config
    from .prompts import PROMPTS
    from .logger import setup_logging
    from .storage.history_db import HistoryDB
    from .audio.audio_muter import AudioMuter
    from .output.text_detector import TextFieldDetector
    from .output.text_injector import TextInjector
    from .engine.session import VoiceFlowSession
    from .ui.main_window import MainWindow
    from .ui.settings_dialog import SettingsDialog
    from .ui.system_tray import SystemTray
    from .ui.activation_dialog import ActivationDialog
    from .ui.trial_banner import TrialBanner
    from .dictionary import DictionaryManager
    from .license.manager import LicenseManager, LicenseState
except ImportError:
    _parent = Path(__file__).parent.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))
    from voice_flow_app.config import Config
    from voice_flow_app.prompts import PROMPTS
    from voice_flow_app.logger import setup_logging
    from voice_flow_app.storage.history_db import HistoryDB
    from voice_flow_app.audio.audio_muter import AudioMuter
    from voice_flow_app.output.text_detector import TextFieldDetector
    from voice_flow_app.output.text_injector import TextInjector
    from voice_flow_app.engine.session import VoiceFlowSession
    from voice_flow_app.ui.main_window import MainWindow
    from voice_flow_app.ui.settings_dialog import SettingsDialog
    from voice_flow_app.ui.system_tray import SystemTray
    from voice_flow_app.ui.activation_dialog import ActivationDialog
    from voice_flow_app.ui.trial_banner import TrialBanner
    from voice_flow_app.dictionary import DictionaryManager
    from voice_flow_app.license.manager import LicenseManager, LicenseState


class _MacHotkeyListener:
    """Mac 全局热键 — 使用 pynput.keyboard.Listener 监听按键

    热键：
      - 自定义录音组合键（默认右 Shift）→ 按下后释放 = 切换录音
      - ESC → 取消当前录音
    """

    def __init__(self, on_rshift_down, on_record, on_cancel, parent=None, config=None):
        self._on_rshift_down = on_rshift_down
        self._on_record = on_record
        self._on_cancel = on_cancel
        self._config = config

        self._pressed: set = set()         # 当前按下的键
        self._hot_held = False             # 热键组合已触发
        self._escape_held = False

        import threading
        from pynput.keyboard import Key, KeyCode, Listener

        # 默认热键：右 Shift（可配置）
        # 注意：pynput 使用 Key.shift_r，不是 VK 码
        self._hot_keys = {Key.shift_r}
        if config and config.recording_hotkey:
            # 尝试从 VK 码映射到 pynput Key
            pass  # 保持默认右 Shift，配置复杂映射暂不处理

        self._esc_key = Key.esc

        def _on_press(key):
            self._pressed.add(key)
            # ESC 优先级最高 — 按下立即取消录音
            if key == self._esc_key and not self._escape_held:
                self._escape_held = True
                self._on_cancel()
            # 热键全部按下
            if self._hot_keys.issubset(self._pressed):
                if not self._hot_held:
                    self._hot_held = True
                    # 提前 Ctrl+C 复制选中文字
                    self._on_rshift_down()

        def _on_release(key):
            self._pressed.discard(key)
            # ESC 释放
            if key == self._esc_key:
                self._escape_held = False
            # 热键释放 → 切换录音
            if self._hot_held and not self._hot_keys.issubset(self._pressed):
                self._hot_held = False
                self._on_record()

        self._listener = Listener(on_press=_on_press, on_release=_on_release)
        self._listener_thread = threading.Thread(target=self._listener.start, daemon=True)
        self._listener_thread.start()

    def stop(self):
        try:
            self._listener.stop()
        except Exception:
            pass


class _HotkeyPoller:
    """使用 win32api.GetAsyncKeyState 轮询热键（Qt 定时器驱动，无需 admin）

    热键：
      - 自定义录音组合键（默认右 Shift）→ 全部按下后释放 = 切换录音
      - ESC → 取消当前录音
    """

    VK_RSHIFT = 0xA1
    VK_ESCAPE = 0x1B

    def __init__(self, on_rshift_down, on_record, on_cancel, parent, config=None):
        self._on_rshift_down = on_rshift_down   # RShift 刚按下（提前 Ctrl+C）
        self._on_record = on_record
        self._on_cancel = on_cancel   # ESC → 取消录音
        self._config = config

        self._hot_held = False        # 录音热键全部按下
        self._escape_held = False
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._poll)
        self._timer.start(40)  # 40ms 轮询（~25次/秒）

    def _poll(self):
        try:
            import win32api
            hot_vk_list = self._config.recording_hotkey if self._config else [self.VK_RSHIFT]
            # 组合键：全部按下才算 hot
            hot = all((win32api.GetAsyncKeyState(vk) & 0x8000) != 0 for vk in hot_vk_list)
            escape = (win32api.GetAsyncKeyState(self.VK_ESCAPE) & 0x8000) != 0

            # ESC 优先级最高 — 按下立即取消录音
            if escape:
                if not self._escape_held:
                    self._escape_held = True
                    self._on_cancel()
            else:
                self._escape_held = False

            # 录音热键：全部按下 → 全部释放 = 切换录音
            if hot:
                if not self._hot_held:
                    self._hot_held = True
                    # 录音键包含 RShift 时，提前 Ctrl+C 复制选中文字
                    has_rshift = any(vk == self.VK_RSHIFT for vk in hot_vk_list)
                    if has_rshift:
                        self._on_rshift_down()
            else:
                if self._hot_held:
                    self._on_record()
                self._hot_held = False
        except ImportError:
            pass  # pywin32 未安装时静默忽略

    def stop(self):
        self._timer.stop()


# ── 提示词完整性校验 ──
# 正确版本 SHA256 指纹（硬编码，不与本地 stripped PROMPTS 挂钩）
# 本地 PROMPTS 已剥离 system 字段，此哈希对应服务器完整版本
import hashlib as _hashlib
_PROMPTS_CORRECT_HASH = "30fe1f712e801b0a37e562d2d446d55670dbd0d8d94bb1c408b98a2d99d567ce"


def _verify_prompts(server_prompts: dict, logger=None) -> bool:
    """校验服务器提示词与硬编码指纹是否一致"""
    server_hash = _hashlib.sha256(repr(server_prompts).encode()).hexdigest()
    if server_hash != _PROMPTS_CORRECT_HASH:
        if logger:
            logger.error(
                "服务器提示词哈希不匹配！server=%s, expected=%s — 可能被篡改",
                server_hash[:12], _PROMPTS_CORRECT_HASH[:12],
            )
        return False
    return True


def main():
    """Voice Flow 应用入口"""

    log = setup_logging()
    log.info("Voice Flow 启动")

    # ── QApplication（必须在单实例检查之前创建，QSharedMemory 需要） ──
    app = QApplication(sys.argv)
    app.setApplicationName("Voice Flow")
    app.setOrganizationName("VoiceFlow")

    # ── 单实例锁：防止多个 Voice Flow 同时运行导致重复注入 ──
    from PySide6.QtCore import QSharedMemory
    _singleton = QSharedMemory("VoiceFlow_SingleInstance")
    if not _singleton.create(1):
        # 已有实例在运行
        QMessageBox.warning(None, "Voice Flow", "Voice Flow 已在运行中。\n请查看系统托盘或任务栏。")
        log.warning("检测到已有实例运行，退出")
        sys.exit(0)

    # 全局暗色调色板（系统级别的 fallback）
    app.setStyle("Fusion")
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1e1e2e"))
    palette.setColor(QPalette.WindowText, QColor("#cdd6f4"))
    palette.setColor(QPalette.Base, QColor("#313244"))
    palette.setColor(QPalette.AlternateBase, QColor("#45475a"))
    palette.setColor(QPalette.ToolTipBase, QColor("#1e1e2e"))
    palette.setColor(QPalette.ToolTipText, QColor("#cdd6f4"))
    palette.setColor(QPalette.Text, QColor("#cdd6f4"))
    palette.setColor(QPalette.Button, QColor("#45475a"))
    palette.setColor(QPalette.ButtonText, QColor("#cdd6f4"))
    palette.setColor(QPalette.BrightText, QColor("#f38ba8"))
    palette.setColor(QPalette.Highlight, QColor("#cba6f7"))
    palette.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
    app.setPalette(palette)

    # ── 加载配置 ──
    config = Config()
    is_first = not config.load()

    # 设置许可证服务器地址（在许可证请求之前）
    from .license.client import set_server_url
    set_server_url(config.server_url)

    # ── 许可证检查（在登录之前） ──
    license_mgr = LicenseManager(config)
    license_state = license_mgr.load_state()
    log.info("许可证状态: %s", license_state.value)

    # LOCKED / EXPIRED / TRIAL_EXPIRED → must activate, cannot skip
    if license_state in (LicenseState.LOCKED, LicenseState.EXPIRED, LicenseState.TRIAL_EXPIRED):
        if license_state == LicenseState.EXPIRED:
            QMessageBox.warning(None, "许可证已过期",
                "您的 Voice Flow 许可证已过期。\n请续费获取新的许可证密钥。")
        elif license_state == LicenseState.TRIAL_EXPIRED:
            QMessageBox.warning(None, "试用已过期",
                "您的 7 天试用期已结束。\n请升级Pro以继续使用 Voice Flow。")
        elif license_state == LicenseState.LOCKED:
            pass  # No message needed for first launch

        dlg = ActivationDialog(license_mgr, force_activate=True)
        if dlg.exec() != QDialog.Accepted:
            log.info("用户取消升级Pro，退出")
            sys.exit(0)
        license_state = license_mgr.get_state()
        if not license_mgr.is_usable():
            QMessageBox.critical(None, "升级Pro 失败", "升级Pro 未成功，软件无法使用。")
            sys.exit(0)

    elif license_state == LicenseState.ACTIVATED_OFFLINE:
        QMessageBox.information(None, "离线状态",
            "许可证验证已超 7 天未联系服务器。\n请连接网络以继续使用。")
        license_mgr.validate()
        license_state = license_mgr.get_state()
        if not license_mgr.is_usable():
            dlg = ActivationDialog(license_mgr, force_activate=True)
            if dlg.exec() != QDialog.Accepted:
                sys.exit(0)
            if not license_mgr.is_usable():
                sys.exit(0)

    # ── 提示词加载（纯在线模式：失败即退出，绝无本地回退） ──
    def _load_prompts_safe(log):
        """从服务器拉取提示词。失败 = 程序不可用，禁止离线使用。"""
        import asyncio
        from .prompts_client import get_prompts
        from .license.client import set_server_url

        machine_code = license_mgr.get_machine_code()
        license_payload = license_mgr.license_payload
        if not machine_code or not license_payload:
            log.error("提示词：缺少机器码或许可证，无法从服务器获取")
            QMessageBox.critical(
                None, "启动失败",
                "无法获取处理配置：缺少许可证信息。\n"
                "请确认已激活 Pro 并连接网络后重试。"
            )
            sys.exit(1)

        set_server_url(config.server_url)

        server_prompts = None
        loop = asyncio.new_event_loop()
        try:
            server_prompts = loop.run_until_complete(
                get_prompts(machine_code, license_payload, config.server_url)
            )
        except Exception as e:
            log.error("提示词：服务器不可达（%s）", e)
            QMessageBox.critical(
                None, "启动失败",
                "无法连接服务器获取处理配置。\n\n"
                "Voice Flow 需要联网使用，请检查网络后重试。\n"
                f"错误详情：{e}"
            )
            sys.exit(1)
        finally:
            loop.close()

        if not server_prompts:
            log.error("提示词：服务器返回空数据")
            QMessageBox.critical(
                None, "启动失败",
                "服务器未返回有效配置，请稍后重试。"
            )
            sys.exit(1)

        if not _verify_prompts(server_prompts, logger=log):
            log.critical("提示词：哈希校验失败，配置可能被篡改！")
            QMessageBox.critical(
                None, "安全警告",
                "处理配置完整性校验失败！\n\n"
                "服务器上的配置可能已被篡改，为保护您的数据安全，\n"
                "程序已拒绝加载。请联系技术支持。"
            )
            sys.exit(1)

        log.info("提示词：服务器加载成功（哈希校验通过）")
        return server_prompts

    prompts = _load_prompts_safe(log)

    # ── 初始化各组件 ──
    history_db = HistoryDB()
    audio_muter = AudioMuter()
    dictionary = DictionaryManager()
    session = VoiceFlowSession(config, prompts, dictionary=dictionary)

    # ── 主窗口 ──
    text_detector = TextFieldDetector()
    window = MainWindow(
        config=config,
        session=session,
        history_db=history_db,
        audio_muter=audio_muter,
        text_detector=text_detector,
        text_injector=TextInjector,
        license_manager=license_mgr,
        dictionary=dictionary,
    )
    window.show()

    # ── 后台检查更新（启动后 3 秒，不阻塞 UI） ──
    QTimer.singleShot(3000, window.check_for_updates)

    # ── 许可证底栏已在首页内嵌（_create_home_page） ──
    window.add_license_menu()

    # ── 定期验证（每 3 天自动联系服务器） ──
    if license_mgr.needs_validation():
        def _bg_validate():
            result = license_mgr.validate()
            if not result.get("valid") and not result.get("offline"):
                QTimer.singleShot(0, window.show_license_expired_warning)
        threading.Thread(target=_bg_validate, daemon=True).start()

    # ── 心跳：每 5 分钟通知服务器在线状态 ──
    license_mgr.start_heartbeat()

    # ── 系统托盘 ──
    tray = SystemTray(window)
    window.set_tray(tray)

    # ── 首次启动：弹出设置对话框 ──
    if is_first or (not config.has_engine_keys("tencent") and not config.has_engine_keys("aliyun")
                    and not config.has_engine_keys("iflytek") and not config.has_llm_keys()):
        QTimer.singleShot(500, lambda: _show_first_launch_dialog(config, window))

    # ── 全局热键（自定义录音键 + ESC 取消）──
    if sys.platform == 'darwin':
        hotkey = _MacHotkeyListener(
            on_rshift_down=lambda: window.on_rshift_down(),
            on_record=lambda: window.trigger_recording(),
            on_cancel=lambda: window.trigger_cancel(),
            parent=window,
            config=config,
        )
    else:
        hotkey = _HotkeyPoller(
            on_rshift_down=lambda: window.on_rshift_down(),
            on_record=lambda: window.trigger_recording(),
            on_cancel=lambda: window.trigger_cancel(),
            parent=window,
            config=config,
        )

    # ── Qt 事件循环 ──
    try:
        exit_code = app.exec()
    finally:
        hotkey.stop()
        audio_muter.unmute_all()
        history_db.close()

    sys.exit(exit_code)


def _show_first_launch_dialog(config, parent):
    """首次启动或缺少密钥时弹出引导对话框"""
    msg = QMessageBox(parent)
    msg.setWindowTitle("欢迎使用 Voice Flow")
    msg.setIcon(QMessageBox.Information)
    msg.setText(
        "欢迎使用 Voice Flow！\n\n"
        "检测到您尚未配置 API 密钥。\n"
        "请先在设置中填写至少一个 STT 引擎密钥和至少一个 LLM 密钥。"
    )
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec()

    dlg = SettingsDialog(config, parent)
    dlg.exec()


if __name__ == "__main__":
    main()
