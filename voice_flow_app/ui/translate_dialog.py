"""翻译预览窗口 — 独立弹窗，逐行对照中英翻译"""
import asyncio
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QComboBox, QFrame,
    QApplication, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from ..engine.translator import TranslationEngine

log = logging.getLogger("voice_flow.ui.translate")

STYLE = """
QDialog {
    background-color: #0d0d14;
}
QLabel {
    color: #e4e4f0;
    font-size: 13px;
}
QPushButton {
    background-color: #2a2a3e;
    color: #e4e4f0;
    border: 1px solid #333350;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #333350;
}
QPushButton:pressed {
    background-color: #8888a8;
}
QPushButton#translateBtn {
    background-color: #7c5cfc;
    color: #0d0d14;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 24px;
    border: none;
}
QPushButton#translateBtn:hover {
    background-color: #9170ff;
}
QPushButton#translateBtn:disabled {
    background-color: #2a2a3e;
    color: #8888a8;
}
QPushButton#langBox {
    background-color: #1c1c2e;
    color: #8888a8;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    text-align: center;
}
QPushButton#langBox:hover {
    border-color: #7c5cfc;
    color: #8888a8;
}
QComboBox {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #1c1c2e;
    color: #e4e4f0;
    selection-background-color: #2a2a3e;
}
QTextEdit {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
}
QFrame#advancedPanel {
    background-color: #151520;
    border: 1px solid #1c1c2e;
    border-radius: 8px;
}
"""

PRESET_LANGUAGES = [
    "中文", "English", "日本語", "Deutsch",
    "Français", "한국어", "Español", "Русский",
    "Italiano", "Português", "العربية", "हिन्दी",
    "粤语",
]


class LanguagePicker(QDialog):
    """语言选择弹窗 — 预设语言网格"""

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择语言")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(STYLE)
        self._selected = current

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        lbl = QLabel("选择目标语言：")
        layout.addWidget(lbl)

        # 2 列网格
        grid = QHBoxLayout()
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        for i, lang in enumerate(PRESET_LANGUAGES):
            btn = QPushButton(lang)
            btn.setStyleSheet(
                "QPushButton { background: #1c1c2e; color: #e4e4f0; border: 1px solid #2a2a3e; "
                "border-radius: 4px; padding: 6px 12px; }"
                "QPushButton:hover { background: #2a2a3e; border-color: #7c5cfc; }"
            )
            btn.clicked.connect(lambda checked, l=lang: self._select(l))
            (col1 if i % 2 == 0 else col2).addWidget(btn)
        grid.addLayout(col1)
        grid.addLayout(col2)
        layout.addLayout(grid)

    def _select(self, lang: str):
        self._selected = lang
        self.accept()

    @property
    def selected(self) -> str:
        return self._selected


class TranslateDialog(QDialog):
    """翻译预览窗口"""

    # 翻译完成信号（跨线程 → 主线程更新 UI）
    _result_ready = Signal(str)

    def __init__(self, config, text: str = "", parent=None, target_hwnd=None):
        super().__init__(parent)
        self._config = config
        self._engine = TranslationEngine(config)
        self._target_hwnd = target_hwnd  # 注入时激活的目标窗口

        self.setWindowTitle("🌐 翻译")
        self.setMinimumSize(600, 500)
        self.resize(650, 580)
        self.setStyleSheet(STYLE)
        self._advanced_visible = False

        self._setup_ui()
        self._connect_signals()

        # 如果传入了文字（从热键抓取的），填入输入区并自动翻译
        if text.strip():
            self._input_text.setPlainText(text)
            QTimer.singleShot(200, self._do_translate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── 第一行：方向选择 + 高级设置切换 ──
        top_row = QHBoxLayout()

        self._direction_combo = QComboBox()
        self._direction_combo.addItem("自动检测", "auto")
        self._direction_combo.addItem("中文 → English", "zh→en")
        self._direction_combo.addItem("English → 中文", "en→zh")
        self._direction_combo.setToolTip("翻译方向")
        top_row.addWidget(QLabel("方向:"))
        top_row.addWidget(self._direction_combo)

        top_row.addStretch()

        self._btn_advanced = QPushButton("⚙ 高级设置")
        self._btn_advanced.setFixedWidth(100)
        self._btn_advanced.clicked.connect(self._toggle_advanced)
        top_row.addWidget(self._btn_advanced)

        layout.addLayout(top_row)

        # ── 高级设置面板（默认隐藏） ──
        self._advanced_panel = QFrame()
        self._advanced_panel.setObjectName("advancedPanel")
        adv_layout = QVBoxLayout(self._advanced_panel)
        adv_layout.setContentsMargins(12, 12, 12, 12)
        adv_layout.setSpacing(8)

        adv_layout.addWidget(QLabel("语言配对设置："))

        pair_row = QHBoxLayout()
        self._src_lang_btn = QPushButton("中文")
        self._src_lang_btn.setObjectName("langBox")
        self._src_lang_btn.setToolTip("点击选择源语言")
        self._src_lang_btn.clicked.connect(lambda: self._pick_language(self._src_lang_btn))

        arrow = QLabel("⟷")
        arrow.setStyleSheet("color: #7c5cfc; font-size: 20px; font-weight: bold;")
        arrow.setAlignment(Qt.AlignCenter)

        self._tgt_lang_btn = QPushButton("English")
        self._tgt_lang_btn.setObjectName("langBox")
        self._tgt_lang_btn.setToolTip("点击选择目标语言")
        self._tgt_lang_btn.clicked.connect(lambda: self._pick_language(self._tgt_lang_btn))

        pair_row.addWidget(self._src_lang_btn, 1)
        pair_row.addWidget(arrow)
        pair_row.addWidget(self._tgt_lang_btn, 1)

        adv_layout.addLayout(pair_row)
        self._advanced_panel.setVisible(False)
        layout.addWidget(self._advanced_panel)

        # ── 输入区 ──
        layout.addWidget(QLabel("原文："))
        self._input_text = QTextEdit()
        self._input_text.setPlaceholderText("输入待翻译文字，或选中文字后按热键自动填入...")
        self._input_text.setMinimumHeight(100)
        layout.addWidget(self._input_text)

        # ── 翻译按钮 + 状态 ──
        btn_row = QHBoxLayout()
        self._btn_translate = QPushButton("🔄 翻译")
        self._btn_translate.setObjectName("translateBtn")
        self._btn_translate.setFixedWidth(130)
        self._btn_translate.clicked.connect(self._do_translate)
        btn_row.addWidget(self._btn_translate)

        self._lbl_status = QLabel("就绪")
        self._lbl_status.setStyleSheet("color: #4ade80; font-size: 13px;")
        btn_row.addWidget(self._lbl_status)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── 输出区 ──
        layout.addWidget(QLabel("译文（逐行对照）："))
        self._output_text = QTextEdit()
        self._output_text.setReadOnly(True)
        self._output_text.setMinimumHeight(180)
        self._output_text.setFont(QFont("Microsoft YaHei", 12))
        layout.addWidget(self._output_text, 1)

        # ── 底部按钮 ──
        bottom_row = QHBoxLayout()
        self._btn_copy = QPushButton("📋 复制译文")
        self._btn_copy.clicked.connect(self._copy_output)
        bottom_row.addWidget(self._btn_copy)

        bottom_row.addStretch()

        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.close)
        bottom_row.addWidget(self._btn_close)

        layout.addLayout(bottom_row)

    def _connect_signals(self):
        self._result_ready.connect(self._on_result)

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        self._advanced_panel.setVisible(self._advanced_visible)
        self._btn_advanced.setText("▼ 收起设置" if self._advanced_visible else "⚙ 高级设置")

    def _pick_language(self, target_btn: QPushButton):
        """弹出语言选择器"""
        dlg = LanguagePicker(target_btn.text(), self)
        if dlg.exec() == QDialog.Accepted:
            target_btn.setText(dlg.selected)

    def _do_translate(self):
        """执行翻译（在后台线程）"""
        text = self._input_text.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "请先输入待翻译的文字。")
            return

        self._btn_translate.setEnabled(False)
        self._btn_translate.setText("⏳ 翻译中...")
        self._lbl_status.setText("正在翻译...")
        self._lbl_status.setStyleSheet("color: #f59e0b; font-size: 13px;")
        QApplication.processEvents()

        # 确定翻译方向
        direction = self._direction_combo.currentData()
        if direction == "zh→en":
            src, tgt = "中文", "English"
        elif direction == "en→zh":
            src, tgt = "English", "中文"
        else:
            src, tgt = "auto", "auto"

        # 如果高级设置中有自定义语言，覆盖方向
        if self._advanced_visible:
            src_custom = self._src_lang_btn.text()
            tgt_custom = self._tgt_lang_btn.text()
            if src_custom not in ("中文", "English"):
                src = src_custom
            if tgt_custom not in ("中文", "English"):
                tgt = tgt_custom

        import threading
        def _run():
            try:
                result = self._engine.translate(text, src, tgt)
                self._result_ready.emit(result)
            except Exception as e:
                log.error("翻译异常: %s", e)
                self._result_ready.emit(f"[翻译失败] {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _on_result(self, result: str):
        """翻译完成，更新 UI（主线程）"""
        self._output_text.setPlainText(result)
        self._btn_translate.setEnabled(True)
        self._btn_translate.setText("🔄 翻译")
        self._lbl_status.setText("完成")
        self._lbl_status.setStyleSheet("color: #4ade80; font-size: 13px;")

    def _copy_output(self):
        """复制译文"""
        text = self._output_text.toPlainText()
        if text:
            import pyperclip
            pyperclip.copy(text)
            self._lbl_status.setText("已复制到剪贴板")

    # _inject_output 已移除（用户要求取消"注入光标"功能）
