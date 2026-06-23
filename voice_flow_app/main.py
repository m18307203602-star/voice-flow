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
    from .ui.settings_dialog import SettingsPage
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
    from voice_flow_app.ui.settings_dialog import SettingsPage
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

    # ── 全局调色板 ──
    app.setStyle("Fusion")
    from PySide6.QtGui import QPalette, QColor

    def _dark_palette() -> QPalette:
        p = QPalette()
        p.setColor(QPalette.Window, QColor("#1e1e2e"))
        p.setColor(QPalette.WindowText, QColor("#cdd6f4"))
        p.setColor(QPalette.Base, QColor("#313244"))
        p.setColor(QPalette.AlternateBase, QColor("#45475a"))
        p.setColor(QPalette.ToolTipBase, QColor("#1e1e2e"))
        p.setColor(QPalette.ToolTipText, QColor("#cdd6f4"))
        p.setColor(QPalette.Text, QColor("#cdd6f4"))
        p.setColor(QPalette.Button, QColor("#45475a"))
        p.setColor(QPalette.ButtonText, QColor("#cdd6f4"))
        p.setColor(QPalette.BrightText, QColor("#f38ba8"))
        p.setColor(QPalette.Highlight, QColor("#cba6f7"))
        p.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
        return p

    def _light_palette() -> QPalette:
        p = QPalette()
        p.setColor(QPalette.Window, QColor("#f5f5f5"))
        p.setColor(QPalette.WindowText, QColor("#1e1e2e"))
        p.setColor(QPalette.Base, QColor("#ffffff"))
        p.setColor(QPalette.AlternateBase, QColor("#e8e8e8"))
        p.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        p.setColor(QPalette.ToolTipText, QColor("#1e1e2e"))
        p.setColor(QPalette.Text, QColor("#1e1e2e"))
        p.setColor(QPalette.Button, QColor("#e0e0e0"))
        p.setColor(QPalette.ButtonText, QColor("#1e1e2e"))
        p.setColor(QPalette.BrightText, QColor("#d20f39"))
        p.setColor(QPalette.Highlight, QColor("#7c5cfc"))
        p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        return p

    def apply_theme(app, theme: str):
        """应用主题调色板: 'dark' | 'light'"""
        palette = _dark_palette() if theme == "dark" else _light_palette()
        app.setPalette(palette)
        # QToolTip 是顶层弹窗，setStyleSheet 无法穿透，必须用 setPalette
        from PySide6.QtWidgets import QToolTip
        from PySide6.QtGui import QPalette, QColor
        tp = QToolTip.palette()
        if theme == "dark":
            tp.setColor(QPalette.ToolTipText, QColor("#ffffff"))
            tp.setColor(QPalette.ToolTipBase, QColor("#1c1c2e"))
        else:
            tp.setColor(QPalette.ToolTipText, QColor("#1e1e2e"))
            tp.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        QToolTip.setPalette(tp)
        # 同时设字体大小
        app.setStyleSheet("QToolTip { font-size: 12px; padding: 8px 12px; border-radius: 8px; }")

    # ── 加载配置（在调色板之前，以便读取用户偏好）──
    config = Config()
    is_first = not config.load()
    apply_theme(app, config.theme)

    # ── 开机自启动：首次安装默认开启，后续根据配置自动同步注册表 ──
    from .system.autostart import is_enabled as autostart_is_enabled
    from .system.autostart import set_enabled as autostart_set_enabled

    if config.autostart_enabled and not autostart_is_enabled():
        autostart_set_enabled(True)
        log.info("开机自启动已启用（首次/配置同步）")
    elif not config.autostart_enabled and autostart_is_enabled():
        autostart_set_enabled(False)
        log.info("开机自启动已关闭（配置同步）")

    # ── 应用图标（任务栏 + 标题栏） ──
    from PySide6.QtGui import QIcon
    _icon_path = Path(__file__).parent / "resources" / "icon.png"
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))

    # 设置许可证服务器地址（在许可证请求之前）
    from .license.client import set_server_url
    set_server_url(config.server_url)

    # ── 历史数据库（提前创建，许可证管理器需要读取历史上报） ──
    history_db = HistoryDB()

    # ── 许可证检查（在登录之前） ──
    license_mgr = LicenseManager(config, history_db=history_db)
    license_state = license_mgr.load_state()
    log.info("许可证状态: %s", license_state.value)

    # LOCKED / EXPIRED / TRIAL_EXPIRED → must activate, cannot skip
    if license_state in (LicenseState.LOCKED, LicenseState.EXPIRED, LicenseState.TRIAL_EXPIRED):
        if license_state == LicenseState.EXPIRED:
            QMessageBox.warning(None, "许可证已过期",
                "您的 Voice Flow 许可证已过期。\n请续费获取新的许可证密钥。")
        elif license_state == LicenseState.TRIAL_EXPIRED:
            QMessageBox.warning(None, "试用已过期",
                "您的 3 天试用期已结束。\n请升级Pro以继续使用 Voice Flow。")
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

    # ── 提示词加载：先用本地元数据启动，服务器提示词后台加载 ──
    # ponytail: 同步网络调用阻塞窗口 show()，开机时网络未就绪造成超长等待
    from .prompts import PROMPTS as _local_prompts

    prompts = dict(_local_prompts)  # 本地副本（system 为空，仅有元数据）

    def _load_prompts_background():
        """后台线程：从服务器拉取提示词，成功则更新 session"""
        import asyncio
        from .prompts_client import get_prompts

        machine_code = license_mgr.get_machine_code()
        license_payload = license_mgr.license_payload
        if not machine_code or not license_payload:
            return  # 已在 _load_prompts_safe 中处理，这里静默跳过

        server_prompts = None
        loop = asyncio.new_event_loop()
        try:
            server_prompts = loop.run_until_complete(
                get_prompts(machine_code, license_payload, config.server_url)
            )
        except Exception as e:
            log.error("后台提示词加载失败: %s", e)
        finally:
            loop.close()

        if server_prompts and _verify_prompts(server_prompts, logger=log):
            log.info("后台提示词加载成功")
            session._prompts = server_prompts
        elif server_prompts:
            log.error("后台提示词哈希校验失败")
        else:
            log.error("后台提示词：服务器返回空数据")

    # ── 初始化各组件 ──
    audio_muter = AudioMuter()
    audio_muter.enabled = config.audio_mute_enabled
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

    # ── 后台加载服务器提示词（不阻塞窗口显示） ──
    threading.Thread(target=_load_prompts_background, daemon=True).start()

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

    # 嵌入 SettingsPage 到独立对话框（首次启动引导用）
    from PySide6.QtWidgets import QDialog, QVBoxLayout
    dlg = QDialog(parent)
    dlg.setWindowTitle("设置")
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    page = SettingsPage(config, dlg)
    page.theme_changed.connect(lambda t: apply_theme(QApplication.instance(), t))
    layout.addWidget(page)
    dlg.resize(900, 700)
    dlg.exec()


if __name__ == "__main__":
    main()
