"""设置对话框 — API 密钥输入 · 左侧导航 + 右侧内容"""
import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTabWidget, QWidget,
    QFormLayout, QMessageBox, QListWidget, QListWidgetItem,
    QStackedWidget, QSplitter, QScrollArea, QFrame,
    QComboBox, QMenu,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QColor

from .credential_sync import CredentialSyncWidget

# VK 码 → 显示名称
VK_NAMES = {
    0xA1: "右 Shift", 0xA0: "左 Shift", 0x10: "Shift",
    0xA5: "右 Alt", 0xA4: "左 Alt", 0x12: "Alt",
    0x20: "空格",
    0xBF: "/", 0xBE: ".", 0xBC: ",", 0xBD: "-", 0xBB: "=",
    0xDB: "[", 0xDD: "]", 0xBA: ";", 0xDE: "'", 0xC0: "`", 0xDC: "\\",
    0x11: "Ctrl", 0x5B: "Win",
    0x1B: "Esc", 0x09: "Tab", 0x0D: "Enter",
    0x2E: "Delete", 0x08: "Backspace",
    0x21: "PageUp", 0x22: "PageDown", 0x23: "End", 0x24: "Home",
    0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
}
for i in range(0x30, 0x3A):   # 0-9
    VK_NAMES[i] = chr(i)
for i in range(0x41, 0x5B):   # A-Z
    VK_NAMES[i] = chr(i)
for i in range(0x70, 0x7C):   # F1-F12
    VK_NAMES[i] = f"F{i - 0x6F}"

# Qt 修饰键 → Windows VK
_QT_MOD_TO_VK = {
    Qt.ControlModifier: 0x11,
    Qt.AltModifier: 0x12,
    Qt.ShiftModifier: 0x10,
    Qt.MetaModifier: 0x5B,
}


class _SmartKeyEdit(QLineEdit):
    """智能密钥输入框 — 粘贴时智能提取密钥值

    支持场景：
      1. 同分行:  "Secret_ID: AKIDxxxxx"       → "AKIDxxxxx"
      2. 标签+值分行:
           SecretId
           AKIDocGm6GpDQTM6lvzt...
           SecretKey
           qZ8oQuFTXUdxGQh...
         → 各字段自动提取对应值
      3. 纯密钥:  "AKID1234567890abcdef"      → 原样保留
    """

    # ── 标签别名映射：每个字段定义自己关心的标签名 ──
    _LABEL_ALIASES = {
        "secret_id":  ["secretid", "secret_id", "secret id", "secret-id", "secretId", "SecretId", "SecretID"],
        "secret_key": ["secretkey", "secret_key", "secret key", "secret-key", "secretKey", "SecretKey", "SecretKEY"],
        "app_id":     ["appid", "app_id", "app id", "app-id", "appId", "AppId", "AppID"],
        "api_key":    ["apikey", "api_key", "api key", "api-key", "accesskey", "access_key", "access key", "dashscope"],
        "api_secret": ["apisecret", "api_secret", "api secret", "api-secret", "accesssecret", "access_secret"],
        "qwen":       ["qwen", "qwenkey", "qwen_key", "qwen key", "bailian", "百炼", "qwen-plus", "qwen plus"],
        "qwen_flash": ["qwen_flash", "qwenflash", "qwen flash", "qwen3", "qwen3.5", "qwen 3.5", "qwen3.5-flash", "qwen3.5 flash"],
        "deepseek":   ["deepseek", "deepseekkey", "deepseek_key", "deepseek key"],
        "gemini":     ["gemini", "geminikey", "gemini_key", "gemini key"],
    }

    # 判断一行是否是标签行（容忍前后垃圾字符，如 ghghSecretId）
    _IS_LABEL_LINE = re.compile(
        r'^\s*.*?(?:secret[_\s]?(?:id|key)|app[_\s]?id|'
        r'api[_\s]?(?:key|secret)|access[_\s]?(?:key|secret|id)|'
        r'qwen|deepseek|gemini|dashscope|bailian|百炼)\S*\s*$',
        re.IGNORECASE
    )

    def __init__(self, target_role: str = "", parent=None):
        """target_role: 字段角色，如 'secret_id' / 'secret_key' / 'api_key' 等"""
        super().__init__(parent)
        self._aliases = self._LABEL_ALIASES.get(target_role, [])

    def insertFromMimeData(self, source):
        """拦截粘贴事件，智能提取密钥值"""
        if source.hasText():
            raw = source.text()
            cleaned = self._extract_key(raw)
            if cleaned:
                self.setText(cleaned)
                return
        super().insertFromMimeData(source)

    def _match_label(self, text: str) -> bool:
        """判断一行文本是否包含本字段的标签别名（支持前缀/后缀垃圾字符）"""
        t = text.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        for alias in self._aliases:
            a = alias.lower().replace(" ", "").replace("_", "").replace("-", "")
            if a in t:  # 包含匹配，容忍如 "ghghSecretId" 中的 "ghgh"
                return True
        return False

    def _extract_key(self, text: str) -> str | None:
        """从粘贴文本中提取纯密钥值"""
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]

        # 单行直接粘贴 → 尝试同分行解析 "label: value"
        if len(lines) == 1:
            return self._parse_inline(lines[0])

        # 多行 → 扫描标签-值对
        for i, line in enumerate(lines):
            if self._match_label(line):
                # 找到匹配的标签行，下一行就是值
                if i + 1 < len(lines):
                    val = lines[i + 1]
                    # 验证：值行不能是另一个标签
                    if not self._IS_LABEL_LINE.match(val) and len(val) >= 6:
                        return self._parse_inline(val)
                # 也可能取再下一行（跳过空行）
                for j in range(i + 1, min(i + 4, len(lines))):
                    if not self._IS_LABEL_LINE.match(lines[j]) and len(lines[j]) >= 6:
                        return self._parse_inline(lines[j])

        return None

    def _parse_inline(self, text: str) -> str | None:
        """解析同一行内的 '标签: 值' 格式"""
        # 尝试 "标签: 值" 或 "标签：值" 格式
        m = re.match(r'^[\s]*[A-Za-z_一-鿿][\w\s_一-鿿]*?\s*[:：=→>]+\s*(.+)$', text)
        if m:
            val = m.group(1).strip()
            if len(val) >= 6:
                return val
        # 纯密钥（无标签前缀）
        if len(text) >= 6 and not self._IS_LABEL_LINE.match(text):
            return text
        return None


class _KeyCaptureLineEdit(QLineEdit):
    """捕获按键组合（修饰键 + 主键）并显示

    支持右 Alt (AltGr)：通过 nativeEvent 拦截 Windows 菜单激活，
    通过 nativeScanCode 区分左右 Alt。
    """

    # Alt 的区分：nativeVirtualKey 返回 0x12，用 scan code 区分左右
    _SCAN_LALT = 0x38    # 左 Alt
    _SCAN_RALT = 0xE038  # 右 Alt（扩展键）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vk_list = [0xA1]  # 默认 [右 Shift]
        self._listening = False
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处，然后按目标组合键...")
        self.setStyleSheet(
            "QLineEdit { background: #1c1c2e; color: #4ade80; "
            "border: 2px dashed #585b70; border-radius: 4px; "
            "padding: 8px 12px; font-size: 14px; font-weight: bold; }"
            "QLineEdit:focus { border-color: #7c5cfc; }"
        )
        self.mousePressEvent = self._on_click
        self._update_display()

    def _on_click(self, event):
        self._listening = True
        self.setText("⏳ 请按组合键...")
        self.setStyleSheet(
            "QLineEdit { background: #1c1c2e; color: #f59e0b; "
            "border: 2px solid #7c5cfc; border-radius: 4px; "
            "padding: 8px 12px; font-size: 14px; font-weight: bold; }"
        )
        super().mousePressEvent(event)

    def _resolve_vk(self, event: QKeyEvent) -> int:
        """从 QKeyEvent 解析真实的 Windows VK 码（区分左右 Alt）"""
        vk = event.nativeVirtualKey()
        if vk == 0:
            vk = event.key() if event.key() < 0x100 else 0xA1
        # 区分左右 Alt：nativeVirtualKey 都返回 0x12，靠 scan code 区分
        if vk == 0x12:
            scan = event.nativeScanCode()
            if scan == self._SCAN_RALT:
                vk = 0xA5  # VK_RMENU
            elif scan == self._SCAN_LALT:
                vk = 0xA4  # VK_LMENU
        return vk

    def _commit_hotkey(self, main_vk: int, event):
        """保存捕获的组合键（event 可为 None — nativeEvent 调用时）"""
        self._listening = False
        combo = [main_vk]  # Alt 作为独立键时直接使用
        if event is not None:
            # 如果还有其他修饰键按下，也加入组合
            modifiers = event.modifiers()
            extra = []
            for qt_mod, vk in _QT_MOD_TO_VK.items():
                if modifiers & qt_mod and vk != main_vk:
                    extra.append(vk)
            combo = extra + [main_vk]
        self._vk_list = combo
        self._update_display()
        self.clearFocus()

    def nativeEvent(self, eventType, message):
        """拦截 WM_SYSKEYDOWN — 防止 Windows 菜单栏激活吞掉 Alt 键（仅 Windows）"""
        import sys
        if sys.platform != 'win32':
            return False, 0
        if eventType != b"windows_generic_MSG":
            return False, 0
        import ctypes
        from ctypes import wintypes

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]
        msg = ctypes.cast(message, ctypes.POINTER(MSG)).contents
        # WM_SYSKEYDOWN = 0x0104
        if msg.message == 0x0104 and self._listening:
            # 从 lParam 提取 scan code
            lparam = msg.lParam
            scan = (lparam >> 16) & 0xFF
            if lparam & (1 << 24):
                scan |= 0xE000
            if scan == self._SCAN_RALT:
                self._commit_hotkey(0xA5, None)
                return True, 0
            elif scan == self._SCAN_LALT:
                self._commit_hotkey(0xA4, None)
                return True, 0
        return False, 0

    def keyPressEvent(self, event: QKeyEvent):
        if self._listening:
            main_vk = self._resolve_vk(event)

            # 跳过纯修饰键（Ctrl/Shift/Win — 但 Alt 现在已被正确解析为 0xA4/0xA5，不会被跳过）
            _PURE_MODS = (0x11, 0x10, 0x5B, 0xA0, 0xA1)
            if main_vk in _PURE_MODS:
                return

            self._commit_hotkey(main_vk, event)
            return
        super().keyPressEvent(event)

    def _update_display(self):
        names = [VK_NAMES.get(vk, f"VK:{vk}") for vk in self._vk_list]
        label = " + ".join(names)
        self.setText(f"🔑 {label}")
        self.setStyleSheet(
            "QLineEdit { background: #1c1c2e; color: #4ade80; "
            "border: 2px solid #585b70; border-radius: 4px; "
            "padding: 8px 12px; font-size: 14px; font-weight: bold; }"
            "QLineEdit:focus { border-color: #7c5cfc; }"
        )

    def vk_list(self) -> list:
        return self._vk_list

    def set_vk_list(self, vk_list: list):
        self._vk_list = vk_list if vk_list else [0xA1]
        self._update_display()


SETTINGS_STYLE = """
QDialog {
    background-color: #0d0d14;
}
QLabel {
    color: #e4e4f0;
    font-size: 13px;
}
QLineEdit {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    min-width: 280px;
}
QLineEdit:focus {
    border-color: #7c5cfc;
}
QTabWidget::pane {
    border: 1px solid #2a2a3e;
    border-radius: 12px;
    background-color: #0d0d14;
}
QTabBar::tab {
    background-color: #1c1c2e;
    color: #8888a8;
    padding: 8px 20px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #2e2e48;
    color: #e4e4f0;
}
QListWidget {
    background-color: #151520;
    border: 1px solid #2a2a3e;
    border-radius: 12px;
    outline: none;
}
QListWidget::item {
    color: #8888a8;
    padding: 10px 16px;
    border-bottom: 1px solid #2a2a3e;
    font-size: 13px;
}
QListWidget::item:selected {
    background-color: #2e2e48;
    color: #e4e4f0;
}
QListWidget::item:hover {
    background-color: #222238;
}
"""


class SettingsDialog(QDialog):
    """设置对话框 — 左侧纵向导航 + 右侧内容面板"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._comparison_models = []  # 对比模型列表，由 _load_values 填充
        self.setWindowTitle("设置")
        self.setStyleSheet(SETTINGS_STYLE)

        # 与主窗口同宽同位置，高度为 75%，不遮挡底部引擎/模式/录音控件
        if parent:
            pg = parent.geometry()
            self.setGeometry(pg.x(), pg.y(), pg.width(), int(pg.height() * 0.75))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e4e4f0;")
        root.addWidget(title)

        # ── 左右分栏：纵向导航列表 + 内容区 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左侧导航（纵向排列，文字横排）
        self._nav = QListWidget()
        self._nav.setFixedWidth(130)
        self._nav.addItem(QListWidgetItem("⚙️ 配置密钥"))
        self._nav.addItem(QListWidgetItem("🔑 密钥管理"))
        self._nav.addItem(QListWidgetItem("⌨️ 快捷键"))
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        splitter.addWidget(self._nav)

        # 右侧内容区
        self._stack = QStackedWidget()

        # 页面 0：配置密钥（嵌入 CredentialSyncWidget）
        self._sync_widget = CredentialSyncWidget()
        self._sync_widget.completed.connect(self._on_sync_completed)
        self._stack.addWidget(self._sync_widget)

        # 页面 1：密钥管理（Tab 模式 ↔ 总览模式切换）
        keys_page = QWidget()
        keys_layout = QVBoxLayout(keys_page)
        keys_layout.setContentsMargins(0, 0, 0, 0)

        self._key_view_stack = QStackedWidget()

        # ── 模式 0：Tab 编辑模式（每平台一个标签页，可编辑） ──
        self._keys_tabs = QTabWidget()
        self._keys_tabs.addTab(self._make_aliyun_tab(), "阿里云百炼")
        self._keys_tabs.addTab(self._make_tencent_tab(), "腾讯云")
        self._keys_tabs.addTab(self._make_iflytek_tab(), "讯飞")
        self._keys_tabs.addTab(self._make_llm_tab(), "⚡ LLM 模型")
        self._keys_tabs.tabBar().setTabTextColor(3, QColor("#7c5cfc"))
        # 保存原始标签名（不含 ✓）
        self._tab_labels = ["阿里云百炼", "腾讯云", "讯飞", "⚡ LLM 模型"]
        self._key_view_stack.addWidget(self._keys_tabs)

        # ── 模式 1：总览模式（占位，切换时动态构建） ──
        self._overview_placeholder = QWidget()
        self._key_view_stack.addWidget(self._overview_placeholder)

        keys_layout.addWidget(self._key_view_stack)
        self._stack.addWidget(keys_page)

        # 页面 2：快捷键
        self._stack.addWidget(self._make_prefs_tab())

        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_clear_all = QPushButton("清空全部")
        self._btn_clear_all.setStyleSheet(
            "background-color: #f43f5e; color: #0d0d14; font-weight: bold; "
            "padding: 8px 24px; border-radius: 6px;")
        self._btn_clear_all.clicked.connect(self._clear_all)
        btn_row.addWidget(self._btn_clear_all)

        self._btn_clear_page = QPushButton("清空此页")
        self._btn_clear_page.setStyleSheet(
            "background-color: #fab387; color: #0d0d14; font-weight: bold; "
            "padding: 8px 24px; border-radius: 6px;")
        self._btn_clear_page.clicked.connect(self._clear_current_page)
        btn_row.addWidget(self._btn_clear_page)

        self._btn_overview = QPushButton("📋 密钥总览")
        self._btn_overview.setStyleSheet(
            "background-color: #7c5cfc; color: #0d0d14; font-weight: bold; "
            "padding: 8px 24px; border-radius: 6px;")
        self._btn_overview.clicked.connect(self._toggle_key_view)
        btn_row.addWidget(self._btn_overview)

        self._btn_save = QPushButton("保存")
        self._btn_save.setStyleSheet(
            "background-color: #4ade80; color: #0d0d14; font-weight: bold; "
            "padding: 8px 24px; border-radius: 6px;")
        self._btn_save.clicked.connect(self._save)
        btn_row.addWidget(self._btn_save)

        root.addLayout(btn_row)

        self._nav.setCurrentRow(0)  # 默认选中配置密钥
        self._load_values()

    def _on_nav_changed(self, row: int):
        self._stack.setCurrentIndex(row)
        # 底部按钮按页面切换
        if row == 1:  # 密钥管理
            self._btn_clear_all.show()
            self._btn_clear_page.show()
            self._btn_overview.show()
            self._btn_save.show()
        elif row == 2:  # 快捷键 — 只需要保存
            self._btn_clear_all.hide()
            self._btn_clear_page.hide()
            self._btn_overview.hide()
            self._btn_save.show()
        else:  # 配置密钥 — 不需要底部按钮（自动保存）
            self._btn_clear_all.hide()
            self._btn_clear_page.hide()
            self._btn_overview.hide()
            self._btn_save.hide()

    def _on_sync_completed(self, results: dict, platform: str):
        """凭证同步完成 → 自动填入密钥字段并持久化 → 切到对应密钥管理子标签"""
        if results.get("tx_secret_id"):  self._tx_secret_id.setText(results["tx_secret_id"])
        if results.get("tx_secret_key"): self._tx_secret_key.setText(results["tx_secret_key"])
        if results.get("tx_app_id"):     self._tx_app_id.setText(results["tx_app_id"])
        if results.get("aliyun_key"):
            self._al_key.setText(results["aliyun_key"])
            self._llm_qwen.setText(results["aliyun_key"])  # 阿里云百炼 = Qwen LLM 同一套密钥
        if results.get("if_app_id"):     self._if_app_id.setText(results["if_app_id"])
        if results.get("if_api_key"):    self._if_api_key.setText(results["if_api_key"])
        if results.get("if_api_secret"): self._if_api_secret.setText(results["if_api_secret"])
        if results.get("llm_qwen"):      self._llm_qwen.setText(results["llm_qwen"])
        if results.get("llm_qwen_flash"): self._llm_qwen_flash.setText(results["llm_qwen_flash"])
        if results.get("llm_deepseek"):  self._llm_deepseek.setText(results["llm_deepseek"])
        if results.get("llm_gemini"):    self._llm_gemini.setText(results["llm_gemini"])
        if results.get("llm_mimo"):      self._llm_mimo.setText(results["llm_mimo"])
        # 自动持久化
        self._config.set_tencent_keys(
            self._tx_secret_id.text().strip(),
            self._tx_secret_key.text().strip(),
            self._tx_app_id.text().strip(),
        )
        self._config.set_aliyun_key(self._al_key.text().strip())
        self._config.set_iflytek_keys(
            self._if_app_id.text().strip(),
            self._if_api_key.text().strip(),
            self._if_api_secret.text().strip(),
        )
        self._config.qwen_key = self._llm_qwen.text().strip()
        self._config.qwen_flash_key = self._llm_qwen_flash.text().strip()
        self._config.deepseek_key = self._llm_deepseek.text().strip()
        self._config.gemini_key = self._llm_gemini.text().strip()
        self._config.mimo_key = self._llm_mimo.text().strip()
        self._config.save()
        # 切到密钥管理
        self._nav.setCurrentRow(1)

    def _make_tencent_tab(self) -> QWidget:
        """腾讯云密钥编辑标签页"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)

        info = QLabel("腾讯云语音识别服务密钥\n请到 腾讯云控制台 → 访问管理 → API密钥管理 获取")
        info.setStyleSheet("color: #8888a8; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self._tx_secret_id = _SmartKeyEdit("secret_id")
        self._tx_secret_id.setEchoMode(QLineEdit.Password)
        self._tx_secret_id.textChanged.connect(self._update_key_indicators)
        form.addRow("Secret ID:", self._tx_secret_id)
        self._tx_secret_key = _SmartKeyEdit("secret_key")
        self._tx_secret_key.setEchoMode(QLineEdit.Password)
        self._tx_secret_key.textChanged.connect(self._update_key_indicators)
        form.addRow("Secret Key:", self._tx_secret_key)
        self._tx_app_id = _SmartKeyEdit("app_id")
        self._tx_app_id.textChanged.connect(self._update_key_indicators)
        form.addRow("App ID:", self._tx_app_id)
        layout.addLayout(form)
        layout.addStretch()
        return w

    def _section_header(self, title: str, color: str) -> QWidget:
        """分区标题栏（用于总览模式）"""
        bar = QWidget()
        bar.setStyleSheet(f"background-color: #1c1c2e; border-radius: 6px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 8, 6)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold; background: transparent;")
        bar_layout.addWidget(lbl)
        bar_layout.addStretch()
        return bar

    def _make_aliyun_tab(self) -> QWidget:
        """阿里云百炼密钥编辑标签页"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)

        info = QLabel("阿里云百炼 API Key（原 DashScope）\n与 Qwen LLM 共用同一个 Key\n请到 阿里云百炼控制台 → API-KEY管理 获取")
        info.setStyleSheet("color: #8888a8; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self._al_key = _SmartKeyEdit("api_key")
        self._al_key.setEchoMode(QLineEdit.Password)
        self._al_key.textChanged.connect(self._update_key_indicators)
        form.addRow("API Key:", self._al_key)
        layout.addLayout(form)
        layout.addStretch()
        return w

    def _make_iflytek_tab(self) -> QWidget:
        """讯飞密钥编辑标签页"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)

        info = QLabel("讯飞语音识别服务密钥\n请到 讯飞开放平台控制台 获取")
        info.setStyleSheet("color: #8888a8; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self._if_app_id = _SmartKeyEdit("app_id")
        self._if_app_id.textChanged.connect(self._update_key_indicators)
        form.addRow("App ID:", self._if_app_id)
        self._if_api_key = _SmartKeyEdit("api_key")
        self._if_api_key.setEchoMode(QLineEdit.Password)
        self._if_api_key.textChanged.connect(self._update_key_indicators)
        form.addRow("API Key:", self._if_api_key)
        self._if_api_secret = _SmartKeyEdit("api_secret")
        self._if_api_secret.setEchoMode(QLineEdit.Password)
        self._if_api_secret.textChanged.connect(self._update_key_indicators)
        form.addRow("API Secret:", self._if_api_secret)
        layout.addLayout(form)
        layout.addStretch()
        return w

    def _make_llm_tab(self) -> QWidget:
        """LLM 模型密钥编辑标签页"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)

        info = QLabel("⚠️ LLM 降级链：Qwen-Plus → DeepSeek-Chat → Gemini 2.0 Flash\n"
                      "至少填写一个，否则软件无法工作\n"
                      "💡 点击右侧开关可临时禁用某个模型（不删 Key）")
        info.setStyleSheet(
            "color: #7c5cfc; font-size: 12px; font-weight: bold; "
            "background: transparent; padding: 4px 0;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        field_style = (
            "QLineEdit {"
            "  background-color: #1c1c2e; color: #e4e4f0;"
            "  border: 2px solid #7c5cfc; border-radius: 6px;"
            "  padding: 8px 12px; font-size: 13px;"
            "  min-width: 220px;"
            "}"
            "QLineEdit:focus {"
            "  border-color: #f5c2e7; background-color: #2a2740;"
            "}"
        )

        toggle_on_style = """
            QPushButton {
                background-color: #7c5cfc; color: #0d0d14;
                border: none; border-radius: 4px;
                padding: 6px 10px; font-size: 11px; font-weight: bold;
                min-width: 48px; max-width: 48px;
            }
            QPushButton:hover { background-color: #7c5cfc; }
        """
        toggle_off_style = """
            QPushButton {
                background-color: #2a2a3e; color: #9399b2;
                border: 1px solid #585b70; border-radius: 4px;
                padding: 6px 10px; font-size: 11px;
                min-width: 48px; max-width: 48px;
            }
            QPushButton:hover { background-color: #585b70; color: #e4e4f0; }
        """

        def _make_toggle_row(key_edit, model_name):
            """创建 [Key输入框 | 开关按钮] 行"""
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(key_edit)

            toggle = QPushButton()
            toggle.setCheckable(True)
            toggle.setChecked(True)  # 默认启用

            def _on_toggle(checked, btn=toggle, mn=model_name):
                if checked:
                    btn.setText("已开")
                    btn.setStyleSheet(toggle_on_style)
                else:
                    btn.setText("已关")
                    btn.setStyleSheet(toggle_off_style)

            toggle.toggled.connect(_on_toggle)
            # 初始样式
            _on_toggle(True, toggle, model_name)

            row_layout.addWidget(toggle)
            return row, toggle

        self._llm_qwen = _SmartKeyEdit("qwen")
        self._llm_qwen.setEchoMode(QLineEdit.Password)
        self._llm_qwen.setStyleSheet(field_style)
        self._llm_qwen.textChanged.connect(self._update_key_indicators)
        row, self._tgl_qwen = _make_toggle_row(self._llm_qwen, "qwen")
        qwen_lbl = QLabel("Qwen-Plus Key (百炼):")
        qwen_lbl.setStyleSheet("color: #7c5cfc; font-weight: bold; background: transparent;")
        form.addRow(qwen_lbl, row)

        self._llm_qwen_flash = _SmartKeyEdit("qwen_flash")
        self._llm_qwen_flash.setEchoMode(QLineEdit.Password)
        self._llm_qwen_flash.setStyleSheet(field_style)
        self._llm_qwen_flash.textChanged.connect(self._update_key_indicators)
        row, self._tgl_qwen_flash = _make_toggle_row(self._llm_qwen_flash, "qwen_flash")
        qf_lbl = QLabel("Qwen3.5-Flash Key (百炼):")
        qf_lbl.setStyleSheet("color: #7c5cfc; font-weight: bold; background: transparent;")
        form.addRow(qf_lbl, row)

        self._llm_deepseek = _SmartKeyEdit("deepseek")
        self._llm_deepseek.setEchoMode(QLineEdit.Password)
        self._llm_deepseek.setStyleSheet(field_style)
        self._llm_deepseek.textChanged.connect(self._update_key_indicators)
        row, self._tgl_deepseek = _make_toggle_row(self._llm_deepseek, "deepseek")
        ds_lbl = QLabel("DeepSeek Key:")
        ds_lbl.setStyleSheet("color: #7c5cfc; font-weight: bold; background: transparent;")
        form.addRow(ds_lbl, row)

        self._llm_gemini = _SmartKeyEdit("gemini")
        self._llm_gemini.setEchoMode(QLineEdit.Password)
        self._llm_gemini.setStyleSheet(field_style)
        self._llm_gemini.textChanged.connect(self._update_key_indicators)
        row, self._tgl_gemini = _make_toggle_row(self._llm_gemini, "gemini")
        gm_lbl = QLabel("Gemini Key:")
        gm_lbl.setStyleSheet("color: #7c5cfc; font-weight: bold; background: transparent;")
        form.addRow(gm_lbl, row)

        self._llm_mimo = _SmartKeyEdit("mimo")
        self._llm_mimo.setEchoMode(QLineEdit.Password)
        self._llm_mimo.setStyleSheet(field_style)
        self._llm_mimo.textChanged.connect(self._update_key_indicators)
        row, self._tgl_mimo = _make_toggle_row(self._llm_mimo, "mimo")
        mm_lbl = QLabel("MiMo Key (小米):")
        mm_lbl.setStyleSheet("color: #7c5cfc; font-weight: bold; background: transparent;")
        form.addRow(mm_lbl, row)

        proxy_style = (
            "QLineEdit {"
            "  background-color: #1c1c2e; color: #8888a8;"
            "  border: 1px solid #2a2a3e; border-radius: 4px;"
            "  padding: 6px 10px; font-size: 12px;"
            "  min-width: 280px;"
            "}"
            "QLineEdit:focus { border-color: #7c5cfc; }"
        )
        self._llm_proxy = QLineEdit()
        self._llm_proxy.setPlaceholderText("http://127.0.0.1:7790")
        self._llm_proxy.setStyleSheet(proxy_style)
        px_lbl = QLabel("代理 (可选):")
        px_lbl.setStyleSheet("color: #8888a8; font-size: 12px; background: transparent;")
        form.addRow(px_lbl, self._llm_proxy)
        layout.addLayout(form)
        layout.addStretch()
        return w

    # ── 密钥填写状态标识 ──

    def _update_key_indicators(self):
        """检查各云服务密钥填写状态，在标签页标题上显示 ✓"""
        # 阿里云百炼：API Key 非空即完成
        aliyun_ok = bool(self._al_key.text().strip())

        # 腾讯云：Secret ID + Secret Key + App ID 三者全部填写
        tencent_ok = all([
            self._tx_secret_id.text().strip(),
            self._tx_secret_key.text().strip(),
            self._tx_app_id.text().strip(),
        ])

        # 讯飞：App ID + API Key + API Secret 三者全部填写
        iflytek_ok = all([
            self._if_app_id.text().strip(),
            self._if_api_key.text().strip(),
            self._if_api_secret.text().strip(),
        ])

        # LLM：任一有效密钥即激活（Qwen / DeepSeek / Gemini 三选一）
        llm_ok = any([
            self._llm_qwen.text().strip(),
            self._llm_deepseek.text().strip(),
            self._llm_gemini.text().strip(),
            self._llm_mimo.text().strip(),
        ])

        statuses = [aliyun_ok, tencent_ok, iflytek_ok, llm_ok]
        for i, ok in enumerate(statuses):
            label = self._tab_labels[i]
            self._keys_tabs.setTabText(i, f"{label}  😊" if ok else label)

    # ── 总览模式（可编辑的滚动视图） ──

    def _overview_field(self, label_text: str, source_field: QLineEdit, accent_color: str = "#4ade80") -> QWidget:
        """总览模式下的单个字段行：标签 + 可编辑输入框"""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(8)

        lbl = QLabel(label_text)
        lbl.setStyleSheet(
            f"color: {accent_color}; font-size: 12px; font-weight: bold; "
            "background: transparent; min-width: 110px;"
        )
        row_layout.addWidget(lbl)

        edit = QLineEdit()
        edit.setText(source_field.text())
        edit.setEchoMode(source_field.echoMode())
        edit.setPlaceholderText("(未填写)")
        edit.setStyleSheet(
            "QLineEdit { background-color: #1c1c2e; color: #e4e4f0; "
            "border: 1px solid #2a2a3e; border-radius: 4px; "
            "padding: 4px 8px; font-size: 12px; font-family: Consolas, monospace; }"
            "QLineEdit:focus { border-color: #7c5cfc; }"
        )
        row_layout.addWidget(edit, 1)
        return row

    def _build_overview(self) -> QWidget:
        """动态构建可编辑总览视图（从 Tab 模式 QLineEdit 读取当前值）"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #2a2a3e; border-radius: 6px; background: #151520; }"
            "QScrollBar:vertical { background: #151520; width: 8px; }"
            "QScrollBar::handle:vertical { background: #2a2a3e; border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: #585b70; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
        )

        content = QWidget()
        content.setStyleSheet("background: #151520;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.setSpacing(12)

        # ── 阿里云百炼 ──
        content_layout.addWidget(self._section_header("阿里云百炼", "#f59e0b"))
        content_layout.addWidget(self._overview_field("API Key", self._al_key))

        # ── 腾讯云 ──
        content_layout.addWidget(self._section_header("腾讯云", "#7c5cfc"))
        content_layout.addWidget(self._overview_field("Secret ID", self._tx_secret_id))
        content_layout.addWidget(self._overview_field("Secret Key", self._tx_secret_key))
        content_layout.addWidget(self._overview_field("App ID", self._tx_app_id))

        # ── 讯飞 ──
        content_layout.addWidget(self._section_header("讯飞", "#4ade80"))
        content_layout.addWidget(self._overview_field("App ID", self._if_app_id))
        content_layout.addWidget(self._overview_field("API Key", self._if_api_key))
        content_layout.addWidget(self._overview_field("API Secret", self._if_api_secret))

        # ── LLM 模型 ──
        content_layout.addWidget(self._section_header("⚡ LLM 模型", "#7c5cfc"))
        content_layout.addWidget(self._overview_field("Qwen-Plus Key (百炼)", self._llm_qwen))
        content_layout.addWidget(self._overview_field("Qwen3.5-Flash Key (百炼)", self._llm_qwen_flash))
        content_layout.addWidget(self._overview_field("DeepSeek Key", self._llm_deepseek))
        content_layout.addWidget(self._overview_field("Gemini Key", self._llm_gemini))
        content_layout.addWidget(self._overview_field("MiMo Key (小米)", self._llm_mimo))
        content_layout.addWidget(self._overview_field("代理 URL", self._llm_proxy, "#8888a8"))

        content_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _toggle_key_view(self):
        """切换密钥管理模式：Tab 编辑 ↔ 可编辑总览"""
        current_idx = self._key_view_stack.currentIndex()
        if current_idx == 0:
            # ── Tab → 总览：构建总览视图（可编辑，从 Tab 读取值） ──
            self._overview_widget = self._build_overview()
            # 替换 index 1 处的旧 widget（首切是 placeholder，后续是旧总览）
            old = self._key_view_stack.widget(1)
            if old:
                self._key_view_stack.removeWidget(old)
                old.deleteLater()
            self._key_view_stack.addWidget(self._overview_widget)
            self._key_view_stack.setCurrentIndex(1)
            self._btn_overview.setText("↩ 返回编辑")
        else:
            # ── 总览 → Tab：同步 Edit 值回 Tab QLineEdit ──
            self._sync_overview_to_tabs()
            self._key_view_stack.setCurrentIndex(0)
            self._btn_overview.setText("📋 密钥总览")

    def _sync_overview_to_tabs(self):
        """将总览视图中的编辑值同步回 Tab 模式的 QLineEdit"""
        if not hasattr(self, '_overview_widget') or self._overview_widget is None:
            return
        # 递归查找所有 QLineEdit
        def _find_edits(widget):
            edits = []
            for child in widget.findChildren(QLineEdit):
                edits.append(child)
            return edits
        edits = _find_edits(self._overview_widget)
        if len(edits) == 0:
            return
        # 按照 _build_overview 中的添加顺序：
        # [0] al_key, [1] tx_secret_id, [2] tx_secret_key, [3] tx_app_id,
        # [4] if_app_id, [5] if_api_key, [6] if_api_secret,
        # [7] llm_qwen, [8] llm_qwen_flash, [9] llm_deepseek, [10] llm_gemini, [11] llm_mimo, [12] llm_proxy
        fields = [
            self._al_key, self._tx_secret_id, self._tx_secret_key, self._tx_app_id,
            self._if_app_id, self._if_api_key, self._if_api_secret,
            self._llm_qwen, self._llm_qwen_flash, self._llm_deepseek, self._llm_gemini, self._llm_mimo, self._llm_proxy,
        ]
        for i, field in enumerate(fields):
            if i < len(edits):
                field.setText(edits[i].text())

    # ── 模型名称常量（显示名 → config 键映射） ──
    _MODEL_DISPLAY_NAMES = ["MiMo Flash", "Qwen3.5-Flash", "Qwen-Plus", "DeepSeek-Chat", "Gemini 2.0 Flash"]
    _MODEL_KEY_MAP = {
        "MiMo Flash": "mimo",
        "Qwen3.5-Flash": "qwen_flash",
        "Qwen-Plus": "qwen",
        "DeepSeek-Chat": "deepseek",
        "Gemini 2.0 Flash": "gemini",
    }

    def _get_available_models(self) -> list:
        """返回当前已填写 Key 且已启用的模型显示名列表"""
        available = []
        for display_name in self._MODEL_DISPLAY_NAMES:
            cfg_key = self._MODEL_KEY_MAP.get(display_name)
            if not cfg_key:
                continue
            # 检查 Key 是否非空
            key_edit = getattr(self, f"_llm_{cfg_key}", None)
            has_key = bool(key_edit and key_edit.text().strip())
            if not has_key:
                continue
            # 检查开关是否启用
            toggle = getattr(self, f"_tgl_{cfg_key}", None)
            enabled = toggle.isChecked() if toggle else True
            if enabled:
                available.append(display_name)
        return available

    def _make_prefs_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        # ── 快捷键 ──
        info = QLabel("自定义快捷键。点击输入框后按下目标键即可捕获。")
        info.setStyleSheet("color: #8888a8; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        self._hotkey_input = _KeyCaptureLineEdit()
        form.addRow("录音快捷键:", self._hotkey_input)

        hint = QLabel("默认：右 Shift。支持单键（空格/A/@）或组合键（Ctrl+空格 / Alt+R / Ctrl+Shift+K）。")
        hint.setStyleSheet("color: #8888a8; font-size: 11px;")
        hint.setWordWrap(True)
        form.addRow(hint)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #2a2a3e; max-height: 1px;")
        form.addRow(sep)

        # ── 模型对比配置 ──
        section = QLabel("模型对比配置")
        section.setStyleSheet("color: #7c5cfc; font-weight: bold; font-size: 14px;")
        form.addRow(section)

        # 主模型下拉框
        self._combo_primary = QComboBox()
        self._combo_primary.setStyleSheet("""
            QComboBox {
                background-color: #1c1c2e; color: #e4e4f0;
                border: 2px solid #7c5cfc; border-radius: 6px;
                padding: 6px 12px; font-size: 13px; min-width: 200px;
            }
            QComboBox:hover { border-color: #f5c2e7; }
            QComboBox QAbstractItemView {
                background-color: #0d0d14; color: #e4e4f0;
                border: 1px solid #2a2a3e; selection-background-color: #2a2a3e;
            }
        """)
        self._combo_primary.currentTextChanged.connect(self._on_primary_changed)
        form.addRow("主模型:", self._combo_primary)

        # 对比模型列表容器
        self._comp_models_container = QWidget()
        self._comp_models_layout = QVBoxLayout(self._comp_models_container)
        self._comp_models_layout.setContentsMargins(0, 0, 0, 0)
        self._comp_models_layout.setSpacing(4)

        comp_header = QLabel("对比模型:")
        comp_header.setStyleSheet("color: #7c5cfc; font-weight: bold; font-size: 13px;")
        form.addRow(comp_header, self._comp_models_container)

        # 添加对比模型按钮
        add_row = QWidget()
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.setSpacing(0)

        self._btn_add_comp = QPushButton("＋ 添加对比模型")
        self._btn_add_comp.setStyleSheet("""
            QPushButton {
                background-color: #1c1c2e; color: #7c5cfc;
                border: 1px dashed #2a2a3e; border-radius: 4px;
                padding: 6px 12px; font-size: 12px;
            }
            QPushButton:hover { background-color: #2a2a3e; }
        """)
        self._btn_add_comp.clicked.connect(self._on_add_comparison_model)
        add_layout.addWidget(self._btn_add_comp)
        add_layout.addStretch()
        form.addRow("", add_row)

        # 无对比模型时的提示
        self._lbl_no_comp = QLabel("   （未添加对比模型，点击上方按钮添加）")
        self._lbl_no_comp.setStyleSheet("color: #8888a8; font-size: 11px; font-style: italic;")
        form.addRow("", self._lbl_no_comp)

        return w

    def _rebuild_comparison_rows(self):
        """重建对比模型行（清除旧控件，根据 _comparison_models 列表重建）"""
        # 清除旧控件
        while self._comp_models_layout.count():
            item = self._comp_models_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._comparison_models:
            self._lbl_no_comp.setVisible(True)
            return

        self._lbl_no_comp.setVisible(False)

        delete_style = """
            QPushButton {
                background-color: #f43f5e; color: #0d0d14;
                border: none; border-radius: 3px;
                padding: 2px 6px; font-size: 11px; font-weight: bold;
                min-width: 20px; max-width: 20px;
            }
            QPushButton:hover { background-color: #eba0ac; }
        """

        for model_name in self._comparison_models:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(6)

            label = QLabel(f"  {model_name}")
            label.setStyleSheet("color: #f59e0b; font-size: 13px;")
            row_layout.addWidget(label)
            row_layout.addStretch()

            btn_del = QPushButton("✕")
            btn_del.setStyleSheet(delete_style)
            btn_del.setToolTip(f"从对比列表移除 {model_name}")
            btn_del.clicked.connect(lambda checked=False, mn=model_name: self._on_remove_comparison_model(mn))
            row_layout.addWidget(btn_del)

            self._comp_models_layout.addWidget(row)

    def _on_primary_changed(self, _text):
        """主模型变更 → 从对比列表中移除同名模型"""
        primary = self._combo_primary.currentText()
        if primary and primary in self._comparison_models:
            self._comparison_models.remove(primary)
            self._rebuild_comparison_rows()

    def _on_add_comparison_model(self):
        """弹出菜单让用户选择要添加的对比模型"""
        available = self._get_available_models()
        primary = self._combo_primary.currentText()

        # 过滤：排除主模型、已在对比列表中的模型
        candidates = [m for m in available
                      if m != primary and m not in self._comparison_models]

        if not candidates:
            QMessageBox.information(self, "提示", "没有可添加的模型。\n请先在\"密钥管理\"中填写 API Key 并启用开关。")
            return

        # 弹出菜单
        menu = QMenu(self)
        for model in candidates:
            action = menu.addAction(model)
            action.triggered.connect(lambda checked=False, mn=model: self._do_add_comparison_model(mn))

        # 定位到按钮下方
        menu.exec(self._btn_add_comp.mapToGlobal(
            self._btn_add_comp.rect().bottomLeft()))

    def _do_add_comparison_model(self, name: str):
        """实际添加对比模型"""
        if name not in self._comparison_models:
            self._comparison_models.append(name)
            self._rebuild_comparison_rows()

    def _on_remove_comparison_model(self, name: str):
        """从对比列表移除模型"""
        if name in self._comparison_models:
            self._comparison_models.remove(name)
            self._rebuild_comparison_rows()

    def _load_values(self):
        # 腾讯云
        sid, skey, aid = self._config.get_tencent_keys()
        self._tx_secret_id.setText(sid)
        self._tx_secret_key.setText(skey)
        self._tx_app_id.setText(aid)

        # 阿里云
        self._al_key.setText(self._config.get_aliyun_key())

        # 讯飞
        aid, akey, asecret = self._config.get_iflytek_keys()
        self._if_app_id.setText(aid)
        self._if_api_key.setText(akey)
        self._if_api_secret.setText(asecret)

        # LLM
        self._llm_qwen.setText(self._config.qwen_key)
        self._llm_qwen_flash.setText(self._config.qwen_flash_key)
        self._llm_deepseek.setText(self._config.deepseek_key)
        self._llm_gemini.setText(self._config.gemini_key)
        self._llm_mimo.setText(self._config.mimo_key)
        self._llm_proxy.setText(self._config.proxy_url)

        # LLM 开关
        self._tgl_qwen.setChecked(self._config.is_llm_enabled("qwen"))
        self._tgl_qwen_flash.setChecked(self._config.is_llm_enabled("qwen_flash"))
        self._tgl_deepseek.setChecked(self._config.is_llm_enabled("deepseek"))
        self._tgl_gemini.setChecked(self._config.is_llm_enabled("gemini"))
        self._tgl_mimo.setChecked(self._config.is_llm_enabled("mimo"))

        # 偏好
        self._hotkey_input.set_vk_list(self._config.recording_hotkey)

        # 模型对比配置
        self._comparison_models = list(self._config.comparison_models)
        self._rebuild_comparison_rows()

        # 刷新主模型下拉（依赖 Key 状态）
        self._refresh_primary_combo()
        # 设置为当前主模型
        idx = self._combo_primary.findText(self._config.primary_model)
        if idx >= 0:
            self._combo_primary.setCurrentIndex(idx)

        # 更新密钥填写状态标识
        self._update_key_indicators()

    def _refresh_primary_combo(self):
        """根据当前 Key 状态刷新主模型下拉框"""
        current = self._combo_primary.currentText()
        self._combo_primary.blockSignals(True)
        self._combo_primary.clear()
        for m in self._MODEL_DISPLAY_NAMES:
            self._combo_primary.addItem(m)
        # 恢复选中
        if current:
            idx = self._combo_primary.findText(current)
            if idx >= 0:
                self._combo_primary.setCurrentIndex(idx)
        self._combo_primary.blockSignals(False)

    def _save(self):
        # 如果在总览模式，先同步值回 Tab QLineEdit
        if self._key_view_stack.currentIndex() == 1:
            self._sync_overview_to_tabs()

        self._config.set_tencent_keys(
            self._tx_secret_id.text().strip(),
            self._tx_secret_key.text().strip(),
            self._tx_app_id.text().strip(),
        )
        self._config.set_aliyun_key(self._al_key.text().strip())
        self._config.set_iflytek_keys(
            self._if_app_id.text().strip(),
            self._if_api_key.text().strip(),
            self._if_api_secret.text().strip(),
        )
        self._config.qwen_key = self._llm_qwen.text().strip()
        self._config.qwen_flash_key = self._llm_qwen_flash.text().strip()
        self._config.deepseek_key = self._llm_deepseek.text().strip()
        self._config.gemini_key = self._llm_gemini.text().strip()
        self._config.mimo_key = self._llm_mimo.text().strip()
        self._config.proxy_url = self._llm_proxy.text().strip()

        # LLM 开关
        self._config.set_llm_enabled("qwen", self._tgl_qwen.isChecked())
        self._config.set_llm_enabled("qwen_flash", self._tgl_qwen_flash.isChecked())
        self._config.set_llm_enabled("deepseek", self._tgl_deepseek.isChecked())
        self._config.set_llm_enabled("gemini", self._tgl_gemini.isChecked())
        self._config.set_llm_enabled("mimo", self._tgl_mimo.isChecked())

        # 偏好
        self._config.recording_hotkey = self._hotkey_input.vk_list()

        # 模型对比配置
        self._config.primary_model = self._combo_primary.currentText()
        self._config.comparison_models = list(self._comparison_models)

        self._config.save()
        QMessageBox.information(self, "保存", "配置已保存")
        # 不调用 accept()，保持对话框打开


    def _clear_current_page(self):
        """清空当前 Tab 页的密钥"""
        if self._key_view_stack.currentIndex() == 1:
            # 总览模式：清空全部（总览下无法区分"当前页"）
            self._clear_all()
            return

        tab_idx = self._keys_tabs.currentIndex()
        if tab_idx == 0:  # 阿里云
            self._al_key.clear()
        elif tab_idx == 1:  # 腾讯云
            self._tx_secret_id.clear()
            self._tx_secret_key.clear()
            self._tx_app_id.clear()
        elif tab_idx == 2:  # 讯飞
            self._if_app_id.clear()
            self._if_api_key.clear()
            self._if_api_secret.clear()
        elif tab_idx == 3:  # LLM
            self._llm_qwen.clear()
            self._llm_qwen_flash.clear()
            self._llm_deepseek.clear()
            self._llm_gemini.clear()
            self._llm_mimo.clear()
            self._llm_proxy.clear()

    def _clear_all(self):
        """清空全部密钥（二次确认）"""
        ok = QMessageBox.warning(
            self, "确认清空",
            "将清除所有平台的密钥（阿里云/腾讯云/讯飞/LLM），\n此操作不可撤销，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        for field in [self._al_key, self._tx_secret_id, self._tx_secret_key,
                      self._tx_app_id, self._if_app_id, self._if_api_key,
                      self._if_api_secret, self._llm_qwen, self._llm_qwen_flash, self._llm_deepseek,
                      self._llm_gemini, self._llm_mimo, self._llm_proxy]:
            field.clear()

    def _show_key_overview(self):
        """密钥总览 — 独立弹窗展示全部四类平台的已填密钥"""
        dlg = QDialog(self)
        dlg.setWindowTitle("密钥总览")
        dlg.setMinimumSize(520, 400)
        dlg.setStyleSheet(SETTINGS_STYLE)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("📋 密钥总览")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #7c5cfc;")
        root.addWidget(title)

        # ── 滚动区域（支持横向纵向滚动） ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #2a2a3e; border-radius: 6px; background: #151520; }"
            "QScrollBar:vertical { background: #151520; width: 8px; }"
            "QScrollBar::handle:vertical { background: #2a2a3e; border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: #585b70; }"
            "QScrollBar:horizontal { background: #151520; height: 8px; }"
            "QScrollBar::handle:horizontal { background: #2a2a3e; border-radius: 4px; min-width: 30px; }"
            "QScrollBar::handle:horizontal:hover { background: #585b70; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }"
        )

        content = QWidget()
        content.setStyleSheet("background: #151520;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.setSpacing(14)

        # ── 四组平台字段 ──
        sections = [
            ("阿里云百炼", "#f59e0b", [
                ("API Key", self._al_key.text()),
            ]),
            ("腾讯云", "#7c5cfc", [
                ("Secret ID", self._tx_secret_id.text()),
                ("Secret Key", self._tx_secret_key.text()),
                ("App ID", self._tx_app_id.text()),
            ]),
            ("讯飞", "#4ade80", [
                ("App ID", self._if_app_id.text()),
                ("API Key", self._if_api_key.text()),
                ("API Secret", self._if_api_secret.text()),
            ]),
            ("LLM 模型", "#7c5cfc", [
                ("Qwen-Plus Key (百炼)", self._llm_qwen.text()),
                ("Qwen3.5-Flash Key (百炼)", self._llm_qwen_flash.text()),
                ("DeepSeek Key", self._llm_deepseek.text()),
                ("Gemini Key", self._llm_gemini.text()),
                ("MiMo Key (小米)", self._llm_mimo.text()),
                ("代理 URL", self._llm_proxy.text()),
            ]),
        ]

        for section_name, accent_color, fields in sections:
            # 分区标题
            header = QLabel(f"─ {section_name} ─")
            header.setStyleSheet(
                f"font-size: 13px; font-weight: bold; color: {accent_color}; "
                "background: transparent; padding: 4px 0;"
            )
            content_layout.addWidget(header)

            for field_name, value in fields:
                row_widget = QWidget()
                row_widget.setStyleSheet("background: transparent;")
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 2, 0, 2)
                row_layout.setSpacing(8)

                lbl = QLabel(field_name)
                lbl.setStyleSheet(
                    "color: #8888a8; font-size: 12px; background: transparent; "
                    "min-width: 110px;"
                )
                row_layout.addWidget(lbl)

                val = QLabel(value if value else "(未填写)")
                if value:
                    masked = value[:8] + "***" + value[-4:] if len(value) > 16 else value
                    val.setText(masked)
                    val.setStyleSheet(
                        "color: #4ade80; font-size: 12px; font-family: Consolas, monospace; "
                        "background: #1c1c2e; border-radius: 3px; padding: 2px 6px;"
                    )
                else:
                    val.setStyleSheet(
                        "color: #8888a8; font-size: 12px; font-style: italic; "
                        "background: transparent; padding: 2px 6px;"
                    )
                val.setWordWrap(True)
                val.setTextInteractionFlags(Qt.TextSelectableByMouse)
                row_layout.addWidget(val, 1)
                content_layout.addWidget(row_widget)

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ── 关闭按钮 ──
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "background-color: #2a2a3e; color: #e4e4f0; "
            "padding: 8px 24px; border-radius: 6px; font-size: 13px;")
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        dlg.exec()
