"""主窗口 — 所有控件和布局"""
import sys
import asyncio
import threading
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QRadioButton, QCheckBox, QGroupBox, QComboBox, QMenu,
    QProgressBar, QButtonGroup, QSplitter, QFrame, QStackedWidget,
    QListWidget, QListWidgetItem,
    QMessageBox, QApplication, QTextEdit, QScrollArea,
    QStyledItemDelegate, QStyle,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QFont, QPalette, QColor, QAction, QPainter
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl

from .history_panel import HistoryPanel
from .settings_dialog import SettingsDialog
from .voiceprint_widget import VoiceprintWidget
from .sidebar import SidebarWidget
from .stats_page import StatsPage
from .dictionary_widget import DictionaryWidget


MAIN_STYLE = """
/* === 基底 === */
QMainWindow {
    background-color: #0d0d14;
}
QWidget {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
}

/* === 标签 === */
QLabel {
    color: #e4e4f0;
    font-size: 13px;
}

/* === 按钮 === */
QPushButton {
    background-color: #222238;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-width: 80px;
}
QPushButton:hover {
    background-color: #2e2e48;
    border-color: #3a3a58;
}
QPushButton:pressed {
    background-color: #1a1a30;
}
QPushButton:disabled {
    background-color: #1a1a28;
    color: #555570;
}

/* === 录音按钮 === */
QPushButton#recordBtn {
    background-color: #7c5cfc;
    color: #ffffff;
    font-weight: 600;
    font-size: 15px;
    padding: 12px 32px;
    border: none;
    border-radius: 12px;
    min-width: 180px;
}
QPushButton#recordBtn:hover {
    background-color: #9170ff;
}
QPushButton#recordBtn:pressed {
    background-color: #6a4de0;
}
QPushButton#recordBtn.recording {
    background-color: #f43f5e;
    color: #ffffff;
}

/* === 复选框 / 单选框 === */
QRadioButton, QCheckBox {
    color: #e4e4f0;
    font-size: 13px;
    spacing: 8px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
}

/* === 分组框 === */
QGroupBox {
    color: #8888a8;
    font-weight: 600;
    border: 1px solid #2a2a3e;
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 18px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}

/* === 分割器 === */
QSplitter::handle {
    background-color: #2a2a3e;
    width: 2px;
}
QSplitter::handle:hover {
    background-color: #7c5cfc;
}

/* === 进度条 === */
QProgressBar {
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    background-color: #1c1c2e;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #4ade80;
    border-radius: 5px;
}

/* === 滚动条 === */
QScrollBar:vertical {
    width: 8px;
    background: transparent;
    margin: 4px 0;
}
QScrollBar::handle:vertical {
    background: #333350;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #7c5cfc;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    height: 8px;
    background: transparent;
}
QScrollBar::handle:horizontal {
    background: #333350;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #7c5cfc;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* === 工具提示 === */
QToolTip {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}

/* === 菜单 === */
QMenu {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 32px 8px 16px;
    border-radius: 6px;
    margin: 2px 4px;
}
QMenu::item:selected {
    background-color: #2e2e48;
}
QMenu::separator {
    height: 1px;
    background: #2a2a3e;
    margin: 4px 12px;
}
"""


class _MarqueeWidget(QWidget):
    """垂直滚动字幕控件 — 金色艺术字体从下往上滚动，中间暂停5秒，超出顶部后从底部重新出现"""

    _PAUSE_TICKS = 100  # 50ms × 100 = 5 秒暂停

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._y_offset = 0     # 文字基线距控件底部的偏移（px）
        self._pause_left = 0   # 剩余暂停 tick 数，0=不暂停
        self._has_paused = False  # 本次循环是否已暂停过（防止重复触发）
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # 艺术字体：华文行楷 → 楷体 → 微软雅黑 fallback
        self._font = QFont("华文行楷", 13)
        self._font.setBold(True)
        self._font.setStyleHint(QFont.Serif)

    def tick(self):
        """每帧调用：上移 → 到中间暂停5秒 → 继续上移 → 从底部重新出现"""
        if self._pause_left > 0:
            self._pause_left -= 1
        else:
            self._y_offset += 1

        # 文字到达控件中间时触发暂停（每轮循环只触发一次）
        center_y = self.height() * 0.35  # 偏下位置，视线不被遮挡
        if self._y_offset == int(center_y) and self._pause_left == 0 and not self._has_paused:
            self._pause_left = self._PAUSE_TICKS
            self._has_paused = True

        # 文字完全移出控件顶部 → 从底部重新进入，重置暂停标记
        if self._y_offset > self.height() + 40:
            self._y_offset = -10
            self._has_paused = False

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setFont(self._font)
        painter.setPen(QColor("#FFD700"))  # 金色
        # 文字从控件底部向上偏移 _y_offset px
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(self._text)
        x = (self.width() - text_w) // 2
        y = self.height() - self._y_offset
        painter.drawText(x, y, self._text)


class _ModeItemDelegate(QStyledItemDelegate):
    """手绘下拉项——艺术字体，白底黑字，选中紫底白字，绕过所有 stylesheet/palette"""
    _FONT = None

    @classmethod
    def _get_font(cls):
        if cls._FONT is None:
            cls._FONT = QFont("华文行楷", 13)
            cls._FONT.setBold(True)
            cls._FONT.setStyleHint(QFont.Serif)
        return cls._FONT

    def paint(self, painter, option, index):
        painter.save()
        painter.setFont(self._get_font())
        rect = option.rect
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, QColor("#7c5cfc"))
            painter.setPen(QColor("#ffffff"))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor("#e8e8f0"))
            painter.setPen(QColor("#1a1a2e"))
        else:
            painter.fillRect(rect, QColor("#ffffff"))
            painter.setPen(QColor("#1a1a2e"))
        text = index.data(Qt.DisplayRole)
        painter.drawText(rect.adjusted(14, 0, -14, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()


class _PrimaryModelDelegate(QStyledItemDelegate):
    """主模型下拉项——金色文字，深色背景"""
    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, QColor("#2e2e48"))
            painter.setPen(QColor("#FFD700"))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor("#252540"))
            painter.setPen(QColor("#FFD700"))
        else:
            painter.fillRect(rect, QColor("#151520"))
            painter.setPen(QColor("#FFD700"))
        text = index.data(Qt.DisplayRole)
        painter.drawText(rect.adjusted(12, 0, -12, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()


class _DropdownStyledCombo(QComboBox):
    """使用自定义 delegate 渲染下拉项，白底黑字一目了然"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_ModeItemDelegate(self))


class MainWindow(QMainWindow):
    """Voice Flow 主窗口"""

    def __init__(self, config, session, history_db, audio_muter, text_detector, text_injector, license_manager=None, dictionary=None):
        super().__init__()
        self._config = config
        self._session = session
        self._history_db = history_db
        self._audio_muter = audio_muter
        self._text_detector = text_detector
        self._text_injector = text_injector
        self._license_manager = license_manager
        self._dictionary = dictionary
        self._trial_banner = None

        self.setWindowTitle("Voice Flow")
        self.setMinimumSize(800, 600)
        self.resize(1000, 750)
        self.setStyleSheet(MAIN_STYLE)

        self._setup_ui()
        self._connect_signals()
        self._load_preferences()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self._root = QHBoxLayout(central)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        # ── 左侧导航栏 ──
        self._sidebar = SidebarWidget()
        self._sidebar.current_changed.connect(self._on_sidebar_changed)
        self._root.addWidget(self._sidebar)

        # ── 右侧内容区（QStackedWidget） ──
        self._stack = QStackedWidget()
        self._root.addWidget(self._stack, 1)

        # ── Page 0: 首页 ──
        self._home_page = self._create_home_page()
        self._stack.addWidget(self._home_page)

        # ── Page 1: 历史记录 ──
        self._history_panel = HistoryPanel(self._history_db, self._config)
        self._stack.addWidget(self._history_panel)

        # ── Page 2: 词典 ──
        self._dict_widget = DictionaryWidget(self._dictionary)
        self._stack.addWidget(self._dict_widget)

        # ── Page 3: 统计 ──
        self._stats_page = StatsPage(self._history_db)
        self._stack.addWidget(self._stats_page)

    def _create_home_page(self):
        """创建首页内容（所有现有控件 + 最近记录预览）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── 顶部：模式 + 引擎 ──
        top_row = QHBoxLayout()

        # 模式选择（下拉框，紧凑不占空间）
        self._mode_combo = _DropdownStyledCombo()
        self._mode_combo.setFixedWidth(120)
        mode_names = {"1": "中英文（推荐）", "2": "纯英文", "3": "纯中文", "4": "文采", "5": "情感", "6": "代码"}
        mode_tips = {
            "2": "中文语音 → 自动分类/编号/上位词 → 结构化英文",
            "3": "中英文混合语音 → 统一中文输出，英语自动翻译为中文",
        }
        for key, name in mode_names.items():
            self._mode_combo.addItem(name, key)
            if key in mode_tips:
                self._mode_combo.setItemData(self._mode_combo.count() - 1, mode_tips[key], Qt.ToolTipRole)
        top_row.addWidget(QLabel("模式:"))
        top_row.addWidget(self._mode_combo)
        top_row.addSpacing(12)

        # 模式下拉框七彩闪烁动画
        self._mode_gradient_timer = QTimer(self)
        self._mode_gradient_timer.timeout.connect(self._update_mode_combo_gradient)
        self._update_mode_combo_gradient()  # 立即应用首帧，避免闪黑
        self._mode_gradient_timer.start(50)  # 20fps

        # 引擎选择（多选下拉按钮，紧凑不占空间）
        self._eng_btn = QPushButton("全部(3)")
        self._eng_btn.setMinimumWidth(80)
        self._eng_btn.setMaximumHeight(26)
        self._eng_btn.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                color: #7c5cfc;
                font-weight: 600;
                font-size: 12px;
            }
        """)
        self._eng_menu = QMenu(self._eng_btn)
        self._eng_actions = {}
        eng_map = {"tencent": "腾讯云", "aliyun": "阿里云", "iflytek": "讯飞"}
        for key, name in eng_map.items():
            action = QAction(name, self._eng_btn)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda checked, k=key: self._on_engine_toggled(k, checked))
            self._eng_menu.addAction(action)
            self._eng_actions[key] = action
        self._eng_btn.setMenu(self._eng_menu)
        self._eng_btn.setToolTip("已选: 腾讯云, 阿里云, 讯飞")
        top_row.addWidget(QLabel("STT:"))
        top_row.addWidget(self._eng_btn)

        # STT 模式切换（短连接 / 流式）
        self._btn_stt_mode = QPushButton()
        self._btn_stt_mode.setCheckable(True)
        self._btn_stt_mode.setFixedWidth(86)
        self._btn_stt_mode.setMaximumHeight(26)
        self._btn_stt_mode.clicked.connect(self._on_stt_mode_toggled)
        top_row.addWidget(self._btn_stt_mode)

        # 主模型快速切换
        self._primary_combo = QComboBox()
        self._primary_combo.setItemDelegate(_PrimaryModelDelegate(self))
        self._primary_combo.setFixedWidth(130)
        self._primary_combo.setToolTip("选择注入输入框的主模型（对比模型仅展示不注入）\n切换后立即生效，无需重启")
        self._primary_combo.setStyleSheet("""
            QComboBox {
                color: #7c5cfc; font-weight: 600; font-size: 12px;
                background-color: #1c1c2e; border: 1px solid #2a2a3e;
                border-radius: 6px; padding: 3px 8px;
            }
            QComboBox:hover { border-color: #7c5cfc; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; }
            QComboBox QAbstractItemView {
                color: #FFD700; background: #151520;
                selection-background-color: #2e2e48; selection-color: #FFD700;
                outline: none; border: 1px solid #2a2a3e;
                border-radius: 8px; padding: 4px;
            }
        """)
        self._primary_combo.currentTextChanged.connect(self._on_primary_model_changed)
        top_row.addWidget(QLabel("主模型:"))
        top_row.addWidget(self._primary_combo)

        # 设置按钮
        top_row.addStretch()
        self._btn_settings = QPushButton("⚙ 设置")
        self._btn_settings.setFixedWidth(100)
        top_row.addWidget(self._btn_settings)

        layout.addLayout(top_row)

        # ── 控制栏 ──
        ctrl_row = QHBoxLayout()

        self._btn_record = QPushButton("🎤 开始录音")
        self._btn_record.setObjectName("recordBtn")
        self._btn_record.setFixedWidth(160)
        ctrl_row.addWidget(self._btn_record)

        self._btn_comparison = QPushButton("🔬 对比")
        self._btn_comparison.setFixedWidth(80)
        self._btn_comparison.setCheckable(True)
        self._btn_comparison.setToolTip("多模型对比 — 同一输入并行调用主模型+对比模型，对比结果和延迟")
        self._btn_comparison.clicked.connect(self._on_comparison_toggled)
        ctrl_row.addWidget(self._btn_comparison)

        self._lbl_status = QLabel("就绪")
        self._lbl_status.setStyleSheet("color: #4ade80; font-size: 14px; font-weight: 600;")
        ctrl_row.addWidget(self._lbl_status)

        ctrl_row.addStretch()

        self._level_bar = QProgressBar()
        self._level_bar.setRange(0, 100)
        self._level_bar.setValue(0)
        self._level_bar.setFixedWidth(120)
        self._level_bar.setFixedHeight(8)
        ctrl_row.addWidget(QLabel("电平"))
        ctrl_row.addWidget(self._level_bar)

        layout.addLayout(ctrl_row)

        # ── 引擎状态标签 ──
        eng_status_row = QHBoxLayout()
        self._lbl_eng_status = {}
        for eng in ["tencent", "iflytek", "aliyun"]:
            lbl = QLabel("—")
            lbl.setStyleSheet("color: #8888a8; font-size: 11px; padding: 0 8px;")
            eng_status_row.addWidget(QLabel(f"{eng}:"))
            eng_status_row.addWidget(lbl)
            self._lbl_eng_status[eng] = lbl
        # 用量统计按钮
        self._btn_usage_stats = QPushButton("用量统计 📊")
        self._btn_usage_stats.setFixedHeight(28)
        self._btn_usage_stats.setToolTip("查看 STT + LLM 完整用量统计")
        self._btn_usage_stats.setStyleSheet("""
            QPushButton {
                background-color: #1c1c2e;
                color: #8888a8;
                border: 1px solid #2a2a3e;
                border-radius: 6px;
                font-size: 12px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #2e2e48;
                color: #e4e4f0;
            }
        """)
        self._btn_usage_stats.clicked.connect(self._show_usage_stats)
        eng_status_row.addWidget(self._btn_usage_stats)
        eng_status_row.addStretch()
        layout.addLayout(eng_status_row)

        # ── 模型对比面板（默认隐藏） ──
        self._comparison_panel = self._create_comparison_panel()
        self._comparison_panel.setVisible(False)
        layout.addWidget(self._comparison_panel)

        # ── 声纹浮动窗口 ──
        self._voiceprint = VoiceprintWidget()

        # ── 最近记录预览（5 条） ──
        recent_label = QLabel("📌 最近记录")
        recent_label.setStyleSheet("color: #8888a8; font-size: 12px; font-weight: 600;")
        layout.addWidget(recent_label)

        self._recent_list = QListWidget()
        self._recent_list.setMaximumHeight(200)
        self._recent_list.setStyleSheet("""
            QListWidget {
                background-color: #151520; border: 1px solid #2a2a3e;
                border-radius: 6px;
            }
            QListWidget::item {
                color: #cdd6f4; padding: 6px 10px;
                border-bottom: 1px solid #1e1e30;
            }
            QListWidget::item:hover {
                background-color: #1e1e32; color: #e4e4f0;
            }
            QListWidget::item:selected {
                background-color: #2a2a3e;
            }
        """)
        self._recent_list.itemClicked.connect(self._on_recent_clicked)
        layout.addWidget(self._recent_list)

        # ── 许可证底栏（Typeless 风格） ──
        from .trial_banner import LicenseBanner
        self._trial_banner = LicenseBanner(self._license_manager)
        self._trial_banner.activate_clicked.connect(self._on_activate_license)
        layout.addWidget(self._trial_banner)

        # ── 法律声明滚动字幕 ──
        self._marquee_text = "此软件已申请专利保护，违法使用将遭受刑事诉讼。"
        self._marquee_box = _MarqueeWidget(self._marquee_text, self)
        self._marquee_box.setFixedHeight(32)
        self._marquee_timer = QTimer(self)
        self._marquee_timer.timeout.connect(self._tick_marquee)
        self._marquee_timer.start(50)  # ~20 fps
        layout.addWidget(self._marquee_box)

        return page

    def _connect_signals(self):
        # 按钮
        self._btn_record.clicked.connect(self._on_record_clicked)
        self._btn_settings.clicked.connect(self._on_settings)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)

        # 引擎切换已由 QAction.toggled 连接，无需额外处理

        # 会话信号
        self._session.state_changed.connect(self._on_state_changed)
        self._session.status_message.connect(self._lbl_status.setText)
        self._session.recording_level.connect(self._on_level)
        self._session.recording_level.connect(self._voiceprint.set_level)
        self._session.recording_spectrum.connect(self._voiceprint.set_spectrum)
        self._session.engine_status.connect(self._on_engine_status)
        self._session.result_ready.connect(self._on_result)
        self._session.comparison_ready.connect(self._on_comparison_result)
        self._session.error_occurred.connect(self._on_error)

        # 电平归零定时器
        self._level_timer = QTimer()
        self._level_timer.timeout.connect(lambda: self._level_bar.setValue(0))
        self._level_timer.setSingleShot(True)

    def _load_preferences(self):
        # 模式
        mode_key = self._config.selected_mode
        idx = self._mode_combo.findData(mode_key)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

        # 引擎
        engines = self._config.selected_engines
        for key, action in self._eng_actions.items():
            action.setChecked(key in engines)
        self._update_eng_btn_text()

        # 对比模式
        self._btn_comparison.setChecked(self._config.comparison_enabled)
        self._update_comparison_button()

        # STT 模式
        self._update_stt_mode_button()

        # 主模型快速切换
        self._refresh_primary_combo()

        # 首页最近记录
        self._refresh_recent_list()

    # ── 模型显示名映射 ──
    _MODEL_DISPLAY_NAMES = ["MiMo Flash", "Qwen3.5-Flash", "Qwen-Plus", "DeepSeek-Chat", "Gemini 2.0 Flash"]
    _MODEL_KEY_MAP = {
        "MiMo Flash": "mimo",
        "Qwen3.5-Flash": "qwen_flash",
        "Qwen-Plus": "qwen",
        "DeepSeek-Chat": "deepseek",
        "Gemini 2.0 Flash": "gemini",
    }

    def _refresh_primary_combo(self):
        """根据已填写的 Key + 启用开关刷新主模型下拉框"""
        current = self._primary_combo.currentText()
        self._primary_combo.blockSignals(True)
        self._primary_combo.clear()

        for display_name in self._MODEL_DISPLAY_NAMES:
            cfg_key = self._MODEL_KEY_MAP.get(display_name)
            if not cfg_key:
                continue
            # 检查 Key 是否非空
            key_attr = f"{cfg_key}_key"
            has_key = bool(getattr(self._config, key_attr, "").strip())
            if not has_key:
                continue
            # 检查开关是否启用
            if not self._config.is_llm_enabled(cfg_key):
                continue
            self._primary_combo.addItem(display_name)

        # 恢复选中
        idx = self._primary_combo.findText(current or self._config.primary_model)
        if idx >= 0:
            self._primary_combo.setCurrentIndex(idx)
        elif self._primary_combo.count() > 0:
            self._primary_combo.setCurrentIndex(0)

        self._primary_combo.blockSignals(False)

    def _on_primary_model_changed(self, model_name: str):
        """主模型切换 → 立即持久化到配置文件"""
        if not model_name or self._primary_combo.signalsBlocked():
            return
        self._config.primary_model = model_name
        self._config.save()
        self._lbl_status.setText(f"主模型已切换: {model_name}")
        self._lbl_status.setStyleSheet("color: #4ade80; font-size: 14px;")
        # 0.8s 后恢复默认样式
        QTimer.singleShot(800, lambda: self._lbl_status.setStyleSheet("color: #4ade80; font-size: 14px;"))

    # ── 事件处理 ──

    def _play_start_sound(self):
        """录音启动提示音（跨平台 QSoundEffect）"""
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'sounds', 'start.wav')
        self._play_sound(os.path.normpath(path))

    def _play_stop_sound(self):
        """录音停止提示音（跨平台 QSoundEffect）"""
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'sounds', 'stop.wav')
        self._play_sound(os.path.normpath(path))

    def _play_sound(self, wav_path: str):
        """跨平台播放 WAV 提示音"""
        import os
        if not os.path.exists(wav_path):
            return
        try:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(wav_path))
            effect.setVolume(0.8)
            effect.play()
        except Exception:
            pass  # 提示音失败不阻塞主流程

    def _on_record_clicked(self):
        state = self._session.state
        if state.value == "idle":
            self._play_start_sound()
            self._audio_muter.mute_all()
            self._session.start_recording()
        elif state.value == "recording":
            self._play_stop_sound()
            self._session.stop_recording()
            self._audio_muter.unmute_all()

    def _on_state_changed(self, state: str):
        if state == "connecting":
            self._btn_record.setText("🔄 连接中...")
            self._btn_record.setEnabled(False)
            self._lbl_status.setStyleSheet("color: #f59e0b; font-size: 14px;")
            self._lbl_status.setText("连接引擎中...")
            self._btn_settings.setEnabled(False)
        elif state == "recording":
            self._btn_record.setText("⏹ 停止录音")
            self._btn_record.setEnabled(True)
            self._btn_record.setProperty("class", "recording")
            self._btn_record.style().unpolish(self._btn_record)
            self._btn_record.style().polish(self._btn_record)
            self._lbl_status.setStyleSheet("color: #f43f5e; font-size: 14px;")
            self._btn_settings.setEnabled(False)
            self._voiceprint.start()
        elif state == "processing":
            self._btn_record.setText("⏳ 处理中...")
            self._btn_record.setEnabled(False)
            self._lbl_status.setStyleSheet("color: #f59e0b; font-size: 14px;")
            self._voiceprint.processing()
        else:  # idle
            self._btn_record.setText("🎤 开始录音")
            self._btn_record.setEnabled(True)
            self._btn_record.setProperty("class", "")
            self._btn_record.style().unpolish(self._btn_record)
            self._btn_record.style().polish(self._btn_record)
            self._lbl_status.setStyleSheet("color: #4ade80; font-size: 14px;")
            self._btn_settings.setEnabled(True)
            self._voiceprint.stop()

    def _on_level(self, level: float):
        self._level_bar.setValue(int(level * 100))
        self._level_timer.start(200)

    def _on_engine_status(self, engine: str, status: str):
        if engine in self._lbl_eng_status:
            color = "#4ade80" if "已连接" in status else "#f43f5e" if "失败" in status else "#f59e0b"
            self._lbl_eng_status[engine].setText(status)
            self._lbl_eng_status[engine].setStyleSheet(f"color: {color}; font-size: 11px;")

    def _on_result(self, transcript: str, output: str, model: str, engine_results: dict):
        import logging
        _log = logging.getLogger("voice_flow.ui")

        from ..storage.history_db import HistoryEntry

        # 确定实际使用的 STT 引擎（短连接优先取第一个成功的）
        stt_engine = ""
        for eng in ["tencent_sentence", "iflytek", "tencent", "aliyun"]:
            if eng in engine_results and not str(engine_results[eng]).startswith("[错误]"):
                stt_engine = eng
                break

        duration = self._session.last_duration if hasattr(self._session, 'last_duration') else 0.0
        tokens = getattr(self._session, 'last_llm_tokens', {})
        entry = HistoryEntry(
            duration=duration,
            engines=self._config.selected_engines,
            mode=self._config.selected_mode,
            mode_name=self._get_mode_name(),
            transcripts=engine_results,
            result=output,
            model_used=model,
            status="success",
            stt_engine=stt_engine,
            llm_prompt_tokens=tokens.get("prompt_tokens", 0),
            llm_completion_tokens=tokens.get("completion_tokens", 0),
        )
        self._history_db.add(entry)
        self._history_panel.refresh()
        if hasattr(self, '_recent_list'):
            self._refresh_recent_list()

        # 检测焦点：输入框→注入，否则→仅存历史
        focused = self._text_detector.is_text_field_focused()
        _log.info("文本注入检测: focused=%s, output_len=%d", focused, len(output))
        if focused:
            ok = self._text_injector.inject(output)
            _log.info("注入结果: ok=%s", ok)
            if ok:
                self._lbl_status.setText("已输入到焦点窗口")
            else:
                self._lbl_status.setText("注入失败，结果已保存到历史")
        else:
            _log.info("未检测到输入框，结果仅保存历史")
            self._lbl_status.setText("结果已保存（未检测到输入框）")

        # 文字已输出/保存 → 关闭声纹窗口
        self._voiceprint.stop()

    def _on_error(self, msg: str):
        self._audio_muter.unmute_all()
        QMessageBox.warning(self, "错误", msg)

    def _update_mode_combo_gradient(self):
        """七彩闪烁渐变 — 定时器驱动，颜色随时间平滑流动"""
        import time as _time
        speed = 0.35
        phase = (_time.time() * speed) % 1.0
        stops = [
            (0, (255, 23, 68)), (0.17, (255, 109, 0)), (0.33, (255, 171, 0)),
            (0.5, (255, 214, 0)), (0.67, (174, 234, 0)), (0.83, (0, 230, 118)),
            (1.0, (0, 200, 83)),
        ]
        shifted = sorted(
            (f"stop:{((p + phase) % 1.0):.3f} #{r:02X}{g:02X}{b:02X}")
            for p, (r, g, b) in stops
        )
        self._mode_combo.setStyleSheet(
            "QComboBox { color: qlineargradient(x1:0,y1:0,x2:1,y2:0, "
            + ", ".join(shifted)
            + "); font-weight: 600; }"
        )

    def _on_mode_combo_changed(self, index):
        key = self._mode_combo.itemData(index)
        if key:
            self._config.selected_mode = key
            self._config.save()

    def _on_engine_toggled(self, eng_key, checked):
        """单个引擎勾选变化 → 更新按钮文字 + 保存配置"""
        engines = [k for k, a in self._eng_actions.items() if a.isChecked()]
        if engines:
            self._config.selected_engines = engines
            self._config.save()
        self._update_eng_btn_text()

    def _update_eng_btn_text(self):
        """更新引擎按钮显示文字和 tooltip"""
        eng_names = {"tencent": "腾讯云", "aliyun": "阿里云", "iflytek": "讯飞"}
        selected = [k for k, a in self._eng_actions.items() if a.isChecked()]
        if len(selected) == 3:
            text = "全部(3)"
        elif len(selected) == 0:
            text = "未选择"
        else:
            text = ", ".join(eng_names[k] for k in selected)
        self._eng_btn.setText(text)
        self._eng_btn.adjustSize()
        if selected:
            self._eng_btn.setToolTip("已选: " + ", ".join(eng_names[k] for k in selected))
        else:
            self._eng_btn.setToolTip("未选择任何引擎")

    def _on_stt_mode_toggled(self):
        """切换 STT 模式：短连接优先 ↔ 仅流式"""
        if self._btn_stt_mode.isChecked():
            self._config.stt_mode = "streaming_only"
        else:
            self._config.stt_mode = "short_first"
        self._config.save()
        self._update_stt_mode_button()

    def _update_stt_mode_button(self):
        """更新短连接开关按钮：已开(蓝) / 已关(灰)，hover 显示说明"""
        is_on = self._config.stt_mode == "short_first"
        self._btn_stt_mode.blockSignals(True)
        self._btn_stt_mode.setChecked(not is_on)
        self._btn_stt_mode.blockSignals(False)
        if is_on:
            self._btn_stt_mode.setText("⚡ 短连接")
            self._btn_stt_mode.setStyleSheet("""
                QPushButton {
                    background-color: #1c1c2e;
                    color: #7c5cfc;
                    border: 1px solid #7c5cfc;
                    border-radius: 6px;
                    padding: 2px 8px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #2e2e48;
                }
            """)
            self._btn_stt_mode.setToolTip("短连接已开：腾讯一句话识别优先，失败自动切讯飞流式兜底")
        else:
            self._btn_stt_mode.setText("⚡ 关")
            self._btn_stt_mode.setStyleSheet("""
                QPushButton {
                    background-color: #1c1c2e;
                    color: #8888a8;
                    border: 1px solid #2a2a3e;
                    border-radius: 6px;
                    padding: 2px 8px;
                }
                QPushButton:hover {
                    color: #e4e4f0;
                }
            """)
            self._btn_stt_mode.setToolTip("短连接已关：使用流式引擎（多引擎并行）")

    def _show_usage_stats(self):
        """打开用量统计对话框"""
        from .usage_stats_dialog import UsageStatsDialog
        dlg = UsageStatsDialog(self._history_db, self)
        dlg.setModal(False)  # 非模态，不阻塞主窗口
        dlg.show()
        # 保持引用防止被 GC
        if not hasattr(self, '_usage_stats_dlg'):
            self._usage_stats_dlg = None
        self._usage_stats_dlg = dlg

    # ── 模型对比 ──

    def _create_comparison_panel(self):
        """创建模型对比面板（2 列网格 + 滚动保护 + 时间统计）"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame#comparisonPanel {
                background-color: #151520;
                border: 1px solid #2a2a3e;
                border-radius: 16px;
            }
        """)
        panel.setObjectName("comparisonPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 标题行
        title_row = QHBoxLayout()
        self._comp_title = QLabel("🔬 模型对比")
        self._comp_title.setStyleSheet("color: #7c5cfc; font-weight: 600; font-size: 13px;")
        title_row.addWidget(self._comp_title)
        title_row.addStretch()
        self._comp_timing = QLabel("")
        self._comp_timing.setStyleSheet("color: #8888a8; font-size: 11px;")
        title_row.addWidget(self._comp_timing)
        layout.addLayout(title_row)

        # ★ 滚动区域包裹网格，防止卡片过多时互相挤压
        self._comp_scroll = QScrollArea()
        self._comp_scroll.setWidgetResizable(True)
        self._comp_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._comp_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._comp_scroll.setMinimumHeight(300)
        self._comp_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
        """)

        # 2 列网格卡片容器
        self._comp_cards_container = QWidget()
        self._comp_cards_container.setStyleSheet("background: transparent;")
        self._comp_cards_layout = QGridLayout(self._comp_cards_container)
        self._comp_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._comp_cards_layout.setSpacing(6)
        self._comp_cards_layout.setColumnStretch(0, 1)
        self._comp_cards_layout.setColumnStretch(1, 1)

        self._comp_scroll.setWidget(self._comp_cards_container)
        layout.addWidget(self._comp_scroll, 1)

        return panel

    def _on_comparison_toggled(self):
        """对比开关切换"""
        enabled = self._btn_comparison.isChecked()
        self._config.comparison_enabled = enabled
        self._config.save()
        self._update_comparison_button()
        self._comparison_panel.setVisible(enabled)

    def _update_comparison_button(self):
        """更新对比按钮外观"""
        enabled = self._btn_comparison.isChecked()
        if enabled:
            self._btn_comparison.setText("🔬 对比:开")
            self._btn_comparison.setStyleSheet("""
                QPushButton {
                    background-color: #4ade80; color: #0d0d14; font-weight: 600;
                    border: none; border-radius: 8px; padding: 6px 12px;
                }
            """)
        else:
            self._btn_comparison.setText("🔬 对比")
            self._btn_comparison.setStyleSheet("")

    # 模型价格参考 (¥/百万token)
    _PRICING = {
        "MiMo Flash": "¥1/2M",
        "Qwen3.5-Flash": "¥0.2/0.4M",
        "Qwen-Plus": "¥0.8/2M",
        "DeepSeek-Chat": "¥1/2M",
        "Gemini 2.0 Flash": "免费",
    }

    def _clear_comparison_cards(self):
        """清除网格中所有旧卡片"""
        layout = self._comp_cards_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_comparison_result(self, comp_data: dict, stage1_elapsed: float, total_elapsed: float):
        """处理对比结果 — 为每个模型动态创建卡片"""
        if not comp_data:
            return

        primary_model = self._config.primary_model

        # 显示面板
        self._comparison_panel.setVisible(True)

        # 清除旧卡片
        self._clear_comparison_cards()

        # 更新标题：时间统计
        timing_parts = []
        if stage1_elapsed > 0:
            timing_parts.append(f"阶段一: {stage1_elapsed:.0f}ms")
        timing_parts.append(f"总计: {total_elapsed:.0f}ms")
        self._comp_timing.setText(" | ".join(timing_parts))

        # 找出最快模型（成功的）
        fastest_name = None
        fastest_ms = float('inf')
        for name, data in comp_data.items():
            ms = data.get("elapsed_ms", 0)
            err = data.get("error")
            if ms and not err and ms < fastest_ms:
                fastest_ms = ms
                fastest_name = name

        # 按顺序排列：主模型第一，其余按原顺序
        items = list(comp_data.items())
        primary_idx = next((i for i, (n, _) in enumerate(items) if n == primary_model), None)
        if primary_idx is not None:
            primary_item = items.pop(primary_idx)
            items.insert(0, primary_item)

        # 为每个模型创建卡片，2 列网格排列
        total = len(items)
        is_odd = (total % 2 == 1)
        for i, (name, data) in enumerate(items):
            is_primary = (name == primary_model)
            row, col = i // 2, i % 2
            card = self._make_model_card(name, data, is_primary, fastest_name, fastest_ms)
            # ★ 奇数最后一张跨 2 列，独占一行，不再挤压左列
            if is_odd and i == total - 1:
                self._comp_cards_layout.addWidget(card, row, 0, 1, 2)
            else:
                self._comp_cards_layout.addWidget(card, row, col)

    def _make_model_card(self, name: str, data: dict, is_primary: bool,
                         fastest_name: str, fastest_ms: float) -> QFrame:
        """创建单个模型结果卡片（2×2 网格版，带醒目滚动条）"""
        card = QFrame()
        card.setMinimumHeight(240)
        card.setObjectName(f"modelCard_{name.replace(' ', '_').replace('.', '_')}")
        border_color = "#4ade80" if is_primary else "#2a2a3e"
        card.setStyleSheet(f"""
            QFrame#modelCard_{name.replace(' ', '_').replace('.', '_')} {{
                background-color: #151520; border: 1px solid {border_color};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 10)
        card_layout.setSpacing(6)

        ms = data.get("elapsed_ms", 0)
        err = data.get("error")
        price = self._PRICING.get(name, "")

        # ── 标题行：模型名 + 速度 + 耗时/价格 ──
        title_row = QHBoxLayout()
        title_row.setSpacing(4)

        name_color = "#4ade80" if is_primary else "#f59e0b"
        primary_tag = " ★ 主模型" if is_primary else ""
        if err:
            label_text = f"⬤ {name}{primary_tag}"
            name_color = "#f43f5e"
        else:
            label_text = f"⬤ {name}{primary_tag}"

        name_lbl = QLabel(label_text)
        name_lbl.setStyleSheet(f"color: {name_color}; font-weight: 600; font-size: 12px;")
        title_row.addWidget(name_lbl)

        # 速度标记
        if ms and not err and fastest_name and fastest_ms > 0:
            if name == fastest_name:
                speed_lbl = QLabel("⚡ 最快")
                speed_lbl.setToolTip(f"最快 {fastest_ms:.0f}ms")
                speed_lbl.setStyleSheet("color: #4ade80; font-size: 10px; font-weight: 600;")
            else:
                diff = ms - fastest_ms
                speed_lbl = QLabel(f"+{diff:.0f}ms")
                speed_lbl.setStyleSheet("color: #8888a8; font-size: 10px;")
            title_row.addWidget(speed_lbl)

        title_row.addStretch()

        # 耗时 + 价格
        if ms and not err:
            info_lbl = QLabel(f"⏱ {ms:.0f}ms · {price}")
            info_lbl.setStyleSheet("color: #8888a8; font-size: 10px;")
            title_row.addWidget(info_lbl)

        card_layout.addLayout(title_row)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #2a2a3e; max-height: 1px;")
        card_layout.addWidget(sep)

        # ── 错误信息 ──
        if err:
            err_lbl = QLabel(f"❌ {err[:60]}")
            err_lbl.setStyleSheet("color: #f43f5e; font-size: 11px;")
            err_lbl.setWordWrap(True)
            card_layout.addWidget(err_lbl)

        # ── 输出文本（带醒目滚动条）──
        text = data.get("text", "") if not err else ""
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMinimumHeight(160)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #0d0d14; color: #e4e4f0;
                border: 1px solid #2a2a3e; border-radius: 8px;
                font-size: 12px; line-height: 1.6;
                padding: 8px;
            }
        """)
        text_edit.setPlainText(text)
        card_layout.addWidget(text_edit, 1)  # stretch=1 撑满剩余空间

        return card

    def _on_settings(self):
        dlg = SettingsDialog(self._config, self)
        dlg.exec()
        # 设置可能修改了 Key / 开关 / 主模型 → 刷新快速切换下拉框
        self._refresh_primary_combo()

    # ── 版本更新 ──

    def check_for_updates(self):
        """启动时静默检查并后台更新（无弹窗、无横幅）

        流程:
          1. 检查 /api/version
          2. 有新版本 → 后台静默下载
          3. 下载完成 → 安排重启时替换
          4. 托盘通知「已更新至最新版本」
        """
        update_url = self._config.update_url
        if not update_url or not update_url.strip():
            return

        from ..updater import (
            check_for_update as _check_update,
            download_update as _download_file,
            install_on_reboot,
        )

        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                info = loop.run_until_complete(_check_update(update_url))
                if not info:
                    loop.close()
                    return
                log = __import__("logging").getLogger("voice_flow.updater")
                log.info("后台下载更新 v%s ...", info.version)
                path = loop.run_until_complete(_download_file(info, progress_cb=None))
                loop.close()
                result_dir = install_on_reboot(path)
                if result_dir:
                    QTimer.singleShot(0, lambda: self._notify_update_done(info.version))
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _notify_update_done(self, new_version: str):
        """托盘通知：更新已就绪，重启后生效"""
        from ..version import __version__
        tray = getattr(self, '_tray', None)
        if tray:
            tray.showMessage(
                "Voice Flow 已更新",
                f"已更新至 v{new_version}（当前 v{__version__}）\n"
                "重启电脑后自动启用新版本。",
                QSystemTrayIcon.Information,
                5000,
            )

    # _show_update_banner 已废弃 — 静默更新模式不再需要 UI 横幅

    def _get_mode_name(self) -> str:
        mode_names = {"1": "中英文（推荐）", "2": "纯英文", "3": "纯中文", "4": "文采", "5": "情感", "6": "代码"}
        return mode_names.get(self._config.selected_mode, "")

    # ── 外部调用接口（供 pynput 热键线程） ──

    def trigger_recording(self):
        """由热键触发：保存前台窗口 → 开始/停止录音"""
        if self._session.state.value == "idle":
            self._play_start_sound()
            # 保存当前的焦点窗口（用户正在操作的应用）
            self._text_detector.save_foreground()
            self._audio_muter.mute_all()
            QTimer.singleShot(0, self._session.start_recording)
        elif self._session.state.value == "recording":
            self._play_stop_sound()
            # ★ 停止时也保存前台窗口（用户刚按Shift，目标应用大概率在前台）
            self._text_detector.save_foreground()
            QTimer.singleShot(0, self._session.stop_recording)
            self._audio_muter.unmute_all()

    def on_rshift_down(self):
        """右 Shift 刚按下：抢在 OS 之前，立即复制选中文字（Ctrl+C / Cmd+C）"""
        import sys
        import pyautogui
        try:
            mod_key = 'command' if sys.platform == 'darwin' else 'ctrl'
            pyautogui.hotkey(mod_key, 'c')
        except Exception:
            pass

    def trigger_cancel(self):
        """ESC 热键：取消当前录音（不保存、不处理）"""
        if self._session.state.value == "recording":
            self._session.cancel()
            self._audio_muter.unmute_all()

    # 翻译功能已移除

    def _tick_marquee(self):
        """垂直滚动法律声明字幕（从下往上，超出顶部后从底部重新出现）"""
        self._marquee_box.tick()

    def add_top_widget(self, widget):
        """在窗口顶部插入一个 widget（如试用横幅）"""
        self._root.insertWidget(0, widget)

    def add_license_menu(self):
        """添加许可证和词库菜单项"""
        from PySide6.QtGui import QAction
        menu_bar = self.menuBar()

        # 许可证菜单
        license_menu = menu_bar.addMenu("许可证")
        activate_action = QAction("升级Pro", self)
        activate_action.triggered.connect(self._on_activate_license)
        license_menu.addAction(activate_action)

        license_menu.addSeparator()
        dict_action = QAction("词库管理", self)
        dict_action.triggered.connect(lambda: self._sidebar.switch_to("dictionary"))
        license_menu.addAction(dict_action)

    def _on_activate_license(self):
        """打开升级Pro对话框"""
        from .activation_dialog import ActivationDialog
        dlg = ActivationDialog(self._license_manager, self)
        if dlg.exec():
            # 激活成功后刷新横幅状态
            if hasattr(self, '_trial_banner') and self._trial_banner:
                self._trial_banner.refresh()

    def _on_sidebar_changed(self, index: int):
        """左侧导航切换 → 右侧页面切换"""
        self._stack.setCurrentIndex(index)

    def _on_recent_clicked(self, item: QListWidgetItem):
        """首页最近记录被点击 → 跳转到历史记录页并定位"""
        entry_id = item.data(Qt.UserRole)
        if entry_id:
            self._sidebar.switch_to("history")  # 切换到历史页
            if hasattr(self, '_history_panel') and self._history_panel:
                self._history_panel.jump_to_item(entry_id)  # 定位到具体记录

    def _refresh_recent_list(self):
        """刷新首页最近 5 条记录"""
        self._recent_list.clear()
        entries = self._history_db.get_all(limit=5, order_asc=False)
        for entry in entries:
            preview = entry.result[:50].replace('\n', ' ') if entry.result else "(无结果)"
            label = f"{entry.created_at}  [{entry.mode_name}]  {preview}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry.id)
            self._recent_list.addItem(item)

    def show_license_expired_warning(self):
        """许可证过期警告"""
        QMessageBox.warning(
            self, "许可证已过期",
            "您的 Pro 许可证已过期，请续费后重新升级Pro。\n软件将退出。"
        )
        self.force_quit()

    def set_tray(self, tray):
        """关联系统托盘，关闭窗口时最小化到托盘而非退出"""
        self._tray = tray

    def closeEvent(self, event):
        # 如果有系统托盘且不是强制退出，则隐藏到托盘
        if hasattr(self, '_tray') and self._tray and not getattr(self, '_force_quit', False):
            event.ignore()
            self.hide()
        else:
            self._audio_muter.unmute_all()
            self._history_db.close()
            super().closeEvent(event)

    def force_quit(self):
        """强制退出（由托盘菜单触发）"""
        self._force_quit = True
        self.close()
