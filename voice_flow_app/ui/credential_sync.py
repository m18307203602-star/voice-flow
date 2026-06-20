"""一键凭证同步 — 剪贴板检测版

分步引导用户逐项复制密钥，正则匹配自动识别填入。

支持平台：腾讯云 / 阿里云百炼 / 讯飞开放平台 / LLM 模型
"""

from __future__ import annotations

import re
import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QLineEdit,
    QFrame, QApplication,
)

# ── 平台定义 ──
PLATFORMS: dict = {
    "阿里云百炼": {
        "url": "https://bailian.console.aliyun.com/",
        "steps": [
            {
                "label": "开通百炼服务",
                "field": None,
                "action": "confirm",
                "hint": (
                    "点「打开页面」→ 点击「免费体验」开通百炼平台\n"
                    "→ 同意协议 → 领取免费额度 → 完成后回来点「已完成」"
                ),
                "url": "https://bailian.console.aliyun.com/cn-beijing?spm=5176.29619931.J_gskoo9IcCWEOwPmyvhNFm.1.74cd10d702TBuW&tab=demohouse#/api-key",
            },
            {
                "label": "API Key",
                "field": "aliyun_key",
                "pattern": r"^sk-[a-zA-Z0-9]{20,}$",
                "hint": "控制台右上角 → API-Key 管理 → 创建 → 复制（sk- 开头）",
            },
        ],
    },
    "腾讯云": {
        "url": "https://console.cloud.tencent.com/cam/capi",
        "steps": [
            {
                "label": "开通 ASR 服务",
                "field": None,
                "action": "confirm",
                "hint": (
                    "新账号需先开通语音识别服务。\n"
                    "点击「打开页面」→ 搜索「语音识别」→ 点击开通"
                    "（按量付费，每月有 5 小时免费额度）"
                ),
                "url": "https://console.cloud.tencent.com/asr",
            },
            {
                "label": "复制三组密钥",
                "action": "tencent_bulk",
                "hint": (
                    "服务开通后，在控制台依次复制以下三组密钥：\n"
                    "① Secret ID（AKID 开头）\n"
                    "② Secret Key（长串字母数字）\n"
                    "③ App ID（纯数字）\n"
                    "支持逐个复制或全选一起复制，自动识别匹配。"
                ),
            },
        ],
    },
    "讯飞": {
        "url": "https://console.xfyun.cn/app/myapp",
        "steps": [
            {
                "label": "创建应用并开通语音转写",
                "field": None,
                "action": "confirm",
                "button_text": "🌐 1. 创建新应用",
                "hint": (
                    "「1. 创建新应用」→   创建应用后   →  回到此页面   → 点击「下一步」"
                ),
                "url": "https://console.xfyun.cn/app/myapp",
            },
            {
                "label": "一键复制全部密钥",
                "action": "bulk",
                "button_text": "🌐 2. 密钥提取",
                "pattern": r"APPID\s*\n\s*(\S+)\s*\n\s*APISecret\s*\n\s*(\S+)\s*\n\s*APIKey\s*\n\s*(\S+)",
                "fields": {"if_app_id": 1, "if_api_secret": 2, "if_api_key": 3},
                "hint": (
                    "点击「密钥提取」→ 右上角【三个 AP 开头 + 三个密钥】→\n"
                    "【一起选中复制】→ 然后回到原页面"
                ),
                "url": "https://console.xfyun.cn/services/uts",
            },
        ],
    },
    "小米 MiMo": {
        "url": "https://platform.xiaomimimo.com/#/console/api-keys",
        "steps": [
            {
                "label": "注册/登录小米开放平台",
                "field": None,
                "action": "confirm",
                "hint": (
                    "点「打开页面」→ 注册小米账号（手机号即可）\n"
                    "→ 登录后进入控制台 → 完成后回来点「已完成」"
                ),
                "url": "https://platform.xiaomimimo.com/",
            },
            {
                "label": "MiMo API Key",
                "field": "llm_mimo",
                "pattern": r"^(sk|tp)-[a-zA-Z0-9]{20,}$",
                "hint": "控制台 → API Keys → 创建新密钥 → 复制（tp- 或 sk- 开头）",
            },
        ],
    },
    "千问 (百炼)": {
        "url": "https://bailian.console.aliyun.com/#/api-key",
        "steps": [
            {
                "label": "Qwen-Plus Key",
                "field": "llm_qwen",
                "pattern": r"^sk-[a-zA-Z0-9]{20,}$",
                "hint": "以 sk- 开头，百炼 API Key",
            },
            {
                "label": "Qwen3.5-Flash Key",
                "field": "llm_qwen_flash",
                "pattern": r"^sk-[a-zA-Z0-9]{20,}$",
                "hint": "可与上方 Qwen-Plus 共用同一 Key（留空自动复用）",
            },
            {
                "label": "DeepSeek Key",
                "field": "llm_deepseek",
                "pattern": r"^sk-[a-zA-Z0-9]{20,}$",
                "hint": "以 sk- 开头",
                "url": "https://platform.deepseek.com/api_keys",
            },
            {
                "label": "Gemini Key",
                "field": "llm_gemini",
                "pattern": r"^AIza[a-zA-Z0-9_-]{20,}$",
                "hint": "以 AIza 开头",
                "url": "https://aistudio.google.com/app/apikey",
            },
            {
                "label": "MiMo Key (小米)",
                "field": "llm_mimo",
                "pattern": r"^(sk|tp)-[a-zA-Z0-9]{20,}$",
                "hint": "以 sk- 或 tp- 开头，(OpenAI 兼容)",
                "url": "https://platform.xiaomimimo.com/#/console/api-keys",
            },
        ],
    },
}

# ── 平台分类 ──
PLATFORM_CATEGORIES = {
    "STT": {
        "label": "🎤 STT 引擎",
        "accent": "#7c5cfc",
        "platforms": ["阿里云百炼", "腾讯云", "讯飞"],
    },
    "LLM": {
        "label": "🧠 LLM 大模型",
        "accent": "#7c5cfc",
        "platforms": ["小米 MiMo", "千问 Plus"],
    },
}

# ── 样式表 ──
SYNC_STYLE = """
QWidget { background-color: #0d0d14; }
QLabel { color: #e4e4f0; font-size: 13px; }
QLabel#stepTitle { font-size: 15px; font-weight: bold; color: #7c5cfc; }
QLabel#stepHint { font-size: 12px; color: #8888a8; }
QLineEdit {
    background-color: #1c1c2e; color: #e4e4f0;
    border: 2px dashed #2a2a3e; border-radius: 6px;
    padding: 10px 14px; font-size: 14px; font-family: "Consolas", monospace;
}
QLineEdit:focus { border-color: #7c5cfc; }
QComboBox {
    background-color: #1c1c2e; color: #e4e4f0;
    border: 1px solid #2a2a3e; border-radius: 4px;
    padding: 6px 10px; font-size: 13px;
}
QComboBox:hover { border-color: #7c5cfc; }
QComboBox QAbstractItemView {
    background-color: #1c1c2e; color: #e4e4f0;
    selection-background-color: #2a2a3e;
}
QProgressBar {
    border: 1px solid #2a2a3e; border-radius: 4px;
    background-color: #1c1c2e; height: 6px; text-align: center;
}
QProgressBar::chunk { background-color: #4ade80; border-radius: 3px; }
QPushButton {
    background-color: #2a2a3e; color: #e4e4f0;
    border: 1px solid #333350; border-radius: 6px;
    padding: 8px 16px; font-size: 13px;
}
QPushButton:hover { background-color: #333350; }
QPushButton#btnOpen {
    background-color: #7c5cfc; color: #0d0d14; font-weight: bold;
}
QPushButton#btnOpen:hover { background-color: #9170ff; }
"""


class CredentialSyncWidget(QWidget):
    """一键凭证同步向导 — 剪贴板自动检测"""

    completed = Signal(dict, str)  # 同步完成时发射 (结果 dict, 平台名称)

    # 七彩渐变：红→橙→黄→绿→青→蓝→紫
    RAINBOW = [
        "#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c",
        "#3bc9db", "#4dabf7", "#b197fc",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(SYNC_STYLE)

        self._results: dict = {}
        self._step_index = 0
        self._last_clipboard = ""
        self._current_platform = None
        self._detected = False

        # Qt 原生剪贴板（事件驱动，无阻塞）
        self._clipboard = QApplication.clipboard()
        self._clipboard.dataChanged.connect(self._on_clipboard_change)

        self._hint_blink = QTimer(self)
        self._hint_blink.timeout.connect(self._blink_hint)
        self._hint_blink.setInterval(420)
        self._rainbow_i = 0

        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._reset)

        # 实名认证提示动画：上下平移 15 秒后消失
        self._auth_hint_timer = QTimer(self)
        self._auth_hint_timer.setSingleShot(True)
        self._auth_hint_timer.timeout.connect(self._hide_auth_hint)

        self._auth_anim_timer = QTimer(self)
        self._auth_anim_timer.setInterval(40)
        self._auth_anim_timer.timeout.connect(self._animate_auth_hint)
        self._auth_dir = 1
        self._auth_y = 0
        self._auth_start_y = 0

        # 手势引导动画：👆 指向按钮，5 秒后消失
        self._gesture_label = None  # created in _setup_ui
        self._gesture_timer = QTimer(self)
        self._gesture_timer.setInterval(50)
        self._gesture_timer.timeout.connect(self._animate_gesture)
        self._gesture_elapsed = 0
        self._gesture_start_x = 0
        self._gesture_start_y = 0
        self._gesture_target = None

        self._setup_ui()
        self._setup_done = True
        # 初始化首个平台数据（动画由 showEvent → _refresh_on_show 触发）
        self._begin_sync(self._combo_platform.currentText())

    # ── 可见性 ──

    def showEvent(self, event):
        """Widget 变为可见时刷新动画状态（处理 QStackedWidget 切换）"""
        super().showEvent(event)
        if self._current_platform is None:
            return
        # 重新触发视觉元素（布局此时已就绪）
        QTimer.singleShot(0, self._refresh_on_show)

    def _refresh_on_show(self):
        """布局就绪后统一启动/刷新所有动态视觉元素"""
        if self._current_platform is None:
            return

        # 1) 彩虹闪烁（_lbl_hint 颜色渐变）
        self._rainbow_i = 0
        if not self._hint_blink.isActive():
            self._hint_blink.start()

        # 2) 实名认证提示：定位 + 上下平移动画
        self._lbl_auth_hint.show()
        self._lbl_auth_hint.adjustSize()
        sg = self._lbl_status.geometry()
        if sg.width() > 0:
            w = self.width() - sg.x() - 16
            self._lbl_auth_hint.setGeometry(sg.x(), sg.bottom() + 4, w, 24)
            self._auth_start_y = sg.bottom() + 4
            self._auth_y = self._auth_start_y
            self._auth_dir = 1
            if not self._auth_anim_timer.isActive():
                self._auth_anim_timer.start()
            if self._auth_hint_timer.remainingTime() <= 0:
                self._auth_hint_timer.start(10000)

        # 3) 手势引导：指向按钮，5 秒后消失（仅步骤一）
        if self._step_index == 0 and self._btn_open.isVisible():
            self._hide_gesture()
            self._gesture_target = self._btn_open
            QTimer.singleShot(300, self._run_gesture_animation)

    # ── UI ──

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)

        # ── 分类切换（STT / LLM 两个入口） ──
        cat_row = QHBoxLayout()
        self._btn_cat_stt = QPushButton("🎤 STT 引擎")
        self._btn_cat_stt.setCheckable(True)
        self._btn_cat_stt.setChecked(True)
        self._btn_cat_stt.clicked.connect(lambda: self._on_category_changed("STT"))
        cat_row.addWidget(self._btn_cat_stt)

        self._btn_cat_llm = QPushButton("🧠 LLM 大模型")
        self._btn_cat_llm.setCheckable(True)
        self._btn_cat_llm.clicked.connect(lambda: self._on_category_changed("LLM"))
        cat_row.addWidget(self._btn_cat_llm)

        cat_row.addStretch()
        root.addLayout(cat_row)

        self._cat_on_style_tpl = (
            "QPushButton {"
            "  background-color: __ACCENT__; color: #0d0d14;"
            "  border: none; border-radius: 6px;"
            "  padding: 8px 16px; font-size: 13px; font-weight: bold;"
            "}"
        )
        self._cat_off_style = (
            "QPushButton {"
            "  background-color: #1c1c2e; color: #8888a8;"
            "  border: 1px solid #2a2a3e; border-radius: 6px;"
            "  padding: 8px 16px; font-size: 13px;"
            "}"
            "QPushButton:hover { background-color: #2a2a3e; color: #e4e4f0; }"
        )

        # ── 平台选择（根据分类动态变化） ──
        plat_row = QHBoxLayout()
        plat_row.addWidget(QLabel("选择平台:"))
        self._combo_platform = QComboBox()
        self._combo_platform.setFixedWidth(160)
        self._combo_platform.currentIndexChanged.connect(self._on_platform_changed)
        plat_row.addWidget(self._combo_platform)
        plat_row.addStretch()
        root.addLayout(plat_row)

        self._current_category = "STT"
        self._populate_platform_combo("STT")
        self._update_category_buttons()

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #2a2a3e; max-height: 1px;")
        root.addWidget(sep)

        # ── 步骤区 ──
        self._lbl_step = QLabel("")
        self._lbl_step.setObjectName("stepTitle")
        root.addWidget(self._lbl_step)

        # 提示文字
        self._lbl_hint = QLabel("")
        self._lbl_hint.setObjectName("stepHint")
        self._lbl_hint.setWordWrap(True)
        root.addWidget(self._lbl_hint)

        self._txt_preview = QLineEdit()
        self._txt_preview.setReadOnly(True)
        self._txt_preview.setPlaceholderText("")
        root.addWidget(self._txt_preview)

        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("font-size: 12px; color: #f59e0b;")
        root.addWidget(self._lbl_status)

        self._lbl_auth_hint = QLabel("新注册用户需登录并完成实名认证", self)
        self._lbl_auth_hint.setStyleSheet(
            "font-size: 12px; color: #f59e0b; background-color: #1c1c2e; "
            "border-radius: 4px; padding: 4px 8px;")
        self._lbl_auth_hint.setWordWrap(True)
        self._lbl_auth_hint.hide()

        # ── 腾讯云一体化视图（三个密钥框 + 同时检测）──
        self._tencent_view = QWidget()
        self._tencent_view.hide()
        tv_layout = QVBoxLayout(self._tencent_view)
        tv_layout.setContentsMargins(0, 0, 0, 0)
        tv_layout.setSpacing(8)

        self._tc_hint = QLabel(
            "开通 RIS 语音识别服务后，在腾讯云控制台依次复制以下三组密钥：\n"
            "支持逐个复制或全选一起复制，系统自动识别匹配。"
        )
        self._tc_hint.setObjectName("stepHint")
        self._tc_hint.setWordWrap(True)
        tv_layout.addWidget(self._tc_hint)

        field_style = (
            "QLineEdit { background-color: #1c1c2e; color: #e4e4f0; "
            "border: 2px dashed #2a2a3e; border-radius: 6px; "
            "padding: 10px 14px; font-size: 14px; font-family: Consolas, monospace; }"
            "QLineEdit:focus { border-color: #7c5cfc; }"
        )
        filled_style = (
            "QLineEdit { background-color: #1a3028; color: #4ade80; "
            "border: 2px solid #4ade80; border-radius: 6px; "
            "padding: 10px 14px; font-size: 14px; font-family: Consolas, monospace; }"
        )

        lbl_sid = QLabel("Secret ID（AKID 开头）：")
        lbl_sid.setStyleSheet("color: #7c5cfc; font-size: 12px; font-weight: bold;")
        tv_layout.addWidget(lbl_sid)
        self._tc_sid = QLineEdit()
        self._tc_sid.setReadOnly(True)
        self._tc_sid.setPlaceholderText("等待复制 Secret ID ...")
        self._tc_sid.setStyleSheet(field_style)
        tv_layout.addWidget(self._tc_sid)

        lbl_skey = QLabel("Secret Key：")
        lbl_skey.setStyleSheet("color: #7c5cfc; font-size: 12px; font-weight: bold;")
        tv_layout.addWidget(lbl_skey)
        self._tc_skey = QLineEdit()
        self._tc_skey.setReadOnly(True)
        self._tc_skey.setPlaceholderText("等待复制 Secret Key ...")
        self._tc_skey.setStyleSheet(field_style)
        tv_layout.addWidget(self._tc_skey)

        lbl_appid = QLabel("App ID（纯数字）：")
        lbl_appid.setStyleSheet("color: #7c5cfc; font-size: 12px; font-weight: bold;")
        tv_layout.addWidget(lbl_appid)
        self._tc_appid = QLineEdit()
        self._tc_appid.setReadOnly(True)
        self._tc_appid.setPlaceholderText("等待复制 App ID ...")
        self._tc_appid.setStyleSheet(field_style)
        tv_layout.addWidget(self._tc_appid)

        tv_layout.addStretch()

        self._tc_count = QLabel("0/3 已填充")
        self._tc_count.setStyleSheet("font-size: 12px; color: #8888a8;")
        tv_layout.addWidget(self._tc_count)

        self._tc_status = QLabel("")
        self._tc_status.setStyleSheet("font-size: 12px; color: #f59e0b;")
        tv_layout.addWidget(self._tc_status)

        root.addWidget(self._tencent_view)

        root.addStretch()

        # ── 按钮行 ──
        btn_row = QHBoxLayout()

        self._btn_open = QPushButton("🌐 手动打开该页面")
        self._btn_open.setObjectName("btnOpen")
        self._btn_open.clicked.connect(self._open_url)
        btn_row.addWidget(self._btn_open)

        self._btn_next = QPushButton("✅ 已完成，下一步")
        self._btn_next.clicked.connect(self._manual_next)
        btn_row.addWidget(self._btn_next)

        self._btn_prev = QPushButton("⬅ 回到上一步")
        self._btn_prev.clicked.connect(self._prev_step)
        btn_row.addWidget(self._btn_prev)

        btn_row.addStretch()

        root.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        # 手势引导标签（绝对定位，漂浮在按钮上方）
        self._gesture_label = QLabel("👆", self)
        self._gesture_label.setStyleSheet("font-size: 32px; background: transparent;")
        self._gesture_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._gesture_label.hide()

    # ── 腾讯云三字段检测 ──

    _TC_PATTERNS = [
        ("tx_secret_id",  re.compile(r"^AKID[a-zA-Z0-9]{15,}$")),
        ("tx_secret_key", re.compile(r"^[a-zA-Z0-9]{25,}$")),
        ("tx_app_id",     re.compile(r"^\d{8,12}$")),
    ]
    _TC_FIELD_STYLE = (
        "QLineEdit { background-color: #1c1c2e; color: #e4e4f0; "
        "border: 2px dashed #2a2a3e; border-radius: 6px; "
        "padding: 10px 14px; font-size: 14px; font-family: Consolas, monospace; }"
    )
    _TC_FILLED_STYLE = (
        "QLineEdit { background-color: #1a3028; color: #4ade80; "
        "border: 2px solid #4ade80; border-radius: 6px; "
        "padding: 10px 14px; font-size: 14px; font-family: Consolas, monospace; }"
    )

    # 行内 label: value 分隔符（与 _SmartKeyEdit 一致）
    _INLINE_SEP = re.compile(r'^[A-Za-z_一-鿿][\w\s_一-鿿]*?\s*[:：=→>/]\s*(.+)')

    def _tencent_check_clipboard(self, text: str):
        """逐行扫描剪贴板，同时匹配三种腾讯云密钥格式（支持多行批量粘贴 + 行内 label:value）"""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        matched_fields = []

        for line in lines:
            # 跳过明显的标签行（长度 < 6）
            if len(line) < 6:
                continue
            # 先尝试从 "SecretId: AKIDxxx" 中提取纯值
            m = self._INLINE_SEP.match(line)
            value = m.group(1).strip() if m else line

            for field_name, pattern in self._TC_PATTERNS:
                if pattern.match(value):
                    widget = {
                        "tx_secret_id":  self._tc_sid,
                        "tx_secret_key": self._tc_skey,
                        "tx_app_id":     self._tc_appid,
                    }[field_name]
                    widget.setText(value)
                    widget.setStyleSheet(self._TC_FILLED_STYLE)
                    widget.setToolTip(value)
                    self._results[field_name] = value
                    matched_fields.append(field_name)
                    break  # 同一行只匹配一种格式，继续扫描下一行

        if matched_fields:
            names = {"tx_secret_id": "SecretId", "tx_secret_key": "SecretKey", "tx_app_id": "AppId"}
            labels = [names[f] for f in matched_fields]
            self._tc_status.setText(f"✅ 已检测到：{', '.join(labels)}")
            self._tc_status.setStyleSheet("font-size: 13px; color: #4ade80; font-weight: bold;")
        else:
            self._tc_status.setText("❌ 格式不符，请检查复制内容")
            self._tc_status.setStyleSheet("font-size: 12px; color: #f43f5e;")

        self._update_tencent_buttons()
        return bool(matched_fields)  # 通知调用方本次是否命中

    def _update_tencent_buttons(self):
        """更新计数器；三字段齐备时自动完成"""
        filled = sum(1 for f, _ in self._TC_PATTERNS if f in self._results)
        self._tc_count.setText(f"{filled}/3 已填充")

        if filled == 3:
            self._tc_count.setStyleSheet("font-size: 13px; color: #4ade80; font-weight: bold;")
            # 自动跳转（与讯飞/阿里云行为一致：检测到所有密钥即自动完成）
            if not self._tc_auto_done:
                self._tc_auto_done = True
                QTimer.singleShot(500, self._finish_tencent)
        elif filled > 0:
            self._tc_count.setStyleSheet("font-size: 12px; color: #f59e0b;")
        else:
            self._tc_count.setStyleSheet("font-size: 12px; color: #8888a8;")

    def _finish_tencent(self):
        """三字段全部填完 → 自动发射完成信号（与讯飞/阿里行为一致）"""
        self.completed.emit(dict(self._results), self._current_platform_name)
        self._tc_status.setText("✅ 同步完成！密钥已自动填入")
        self._tc_status.setStyleSheet("font-size: 13px; color: #4ade80; font-weight: bold;")
        self._reset_timer.start(3000)

    def _reset_tencent_fields(self):
        """重置腾讯云三字段（保留已在 _results 中检测到的字段）"""
        field_map = [
            ("tx_secret_id", self._tc_sid),
            ("tx_secret_key", self._tc_skey),
            ("tx_app_id", self._tc_appid),
        ]
        for field_name, edit in field_map:
            if field_name in self._results:
                edit.setText(self._results[field_name])
                edit.setStyleSheet(self._TC_FILLED_STYLE)
                edit.setToolTip(self._results[field_name])
            else:
                edit.clear()
                edit.setStyleSheet(self._TC_FIELD_STYLE)
                edit.setToolTip("")
        self._tc_status.setText("")
        self._tc_status.setStyleSheet("")

    # ── 公共接口 ──

    def results(self) -> dict:
        return self._results

    # ── 启动 ──

    def _begin_sync(self, platform_name: str):
        """开始/重新开始同步（平台切换时调用）— 仅设置数据状态"""
        self._reset_timer.stop()  # 取消上一次 _finish() 的延迟重置
        self._current_platform = PLATFORMS[platform_name]
        self._current_platform_name = platform_name
        self._step_index = 0
        self._results = {}
        self._last_clipboard = ""
        self._detected = False
        self._tc_auto_done = False  # 防止三字段自动完成重复触发

        # ── 腾讯云：分步向导（第1步=开通ASR，第2步=三框一体化）──
        # ── 其他平台：分步向导 ──
        self._tencent_view.hide()
        self._lbl_step.show()
        self._lbl_hint.show()
        self._txt_preview.show()
        self._lbl_status.show()
        self._progress.show()
        self._btn_prev.show()

        self._progress.setRange(0, len(self._current_platform["steps"]))
        self._show_step(0)

        # 动画由 _refresh_on_show 统一触发（showEvent / 平台切换后调用）

    def _on_category_changed(self, category: str):
        """切换 STT / LLM 分类"""
        if self._current_category == category:
            return
        self._current_category = category
        self._populate_platform_combo(category)
        self._update_category_buttons()
        # 切换到该分类的第一个平台
        self._begin_sync(PLATFORM_CATEGORIES[category]["platforms"][0])

    def _populate_platform_combo(self, category: str):
        """根据分类填充下拉框（仅填充，不触发同步）"""
        self._combo_platform.blockSignals(True)
        self._combo_platform.clear()
        platforms = PLATFORM_CATEGORIES[category]["platforms"]
        self._combo_platform.addItems(platforms)
        self._combo_platform.setCurrentIndex(0)
        self._combo_platform.blockSignals(False)

    def _update_category_buttons(self):
        """更新分类按钮样式"""
        for cat_key, btn, accent in [
            ("STT", self._btn_cat_stt, "#7c5cfc"),
            ("LLM", self._btn_cat_llm, "#7c5cfc"),
        ]:
            active = (self._current_category == cat_key)
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(self._cat_on_style_tpl.replace("__ACCENT__", accent))
            else:
                btn.setStyleSheet(self._cat_off_style)

    def _on_platform_changed(self):
        """用户切换平台 → 重新开始"""
        self._hint_blink.stop()
        self._hide_gesture()
        self._begin_sync(self._combo_platform.currentText())
        if getattr(self, '_setup_done', False):
            self._refresh_on_show()  # 布局已就绪，直接刷新动画

    # ── 步骤展示 ──

    def _show_step(self, idx: int):
        steps = self._current_platform["steps"]
        if idx >= len(steps):
            return

        step = steps[idx]
        total = len(steps)
        is_confirm = step.get("action") == "confirm"
        is_bulk = step.get("action") == "bulk"

        # ── 腾讯云第 2 步：三框一体化 ──
        if self._current_platform_name == "腾讯云" and idx == 1:
            self._lbl_step.setText(f"步骤 {idx + 1}/{total}：{step['label']}")
            self._lbl_hint.setText("📋 请在腾讯云控制台依次复制三组密钥（支持逐个或全选一起复制）：")
            self._lbl_hint.setStyleSheet("font-size: 12px; color: #f59e0b; font-weight: bold;")
            self._txt_preview.hide()
            self._lbl_status.hide()
            self._reset_tencent_fields()
            self._tencent_view.show()
            self._btn_open.setText("🌐 打开腾讯云控制台")
            self._btn_open.show()
            self._btn_prev.setEnabled(True)
            self._btn_next.hide()  # 三框视图无需手动按钮，系统自动检测并跳转
            self._progress.setValue(idx)
            self._detected = False
            self._hint_blink.stop()
            self._update_tencent_buttons()  # 恢复提前检测到的字段按钮状态
            return

        # ── 普通步骤（含腾讯云第 1 步）──
        self._tencent_view.hide()
        self._txt_preview.show()
        self._lbl_status.show()

        self._lbl_step.setText(f"步骤 {idx + 1}/{total}：{step['label']}")
        self._btn_open.setText(step.get("button_text") or f"🌐 打开页面 {'①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'[idx]}")
        self._lbl_hint.setText(f"{'📋 ' if is_confirm else '📦 批量格式：' if is_bulk else '格式要求：'}{step['hint']}")
        self._txt_preview.setText("")
        self._txt_preview.setPlaceholderText(
            "请按上方提示操作，完成后点击「已完成」" if is_confirm
            else "请全选复制 APPID + APISecret + APIKey 三条密钥 ..." if is_bulk
            else f"请复制 {step['label']} ..."
        )
        self._lbl_status.setText("⏳ 等待确认..." if is_confirm else "⏳ 等待检测...")
        self._lbl_status.setStyleSheet("font-size: 12px; color: #f59e0b;")
        self._progress.setValue(idx)
        self._detected = False

        # 「回到上一步」仅在第一步之后可用
        self._btn_prev.setEnabled(idx > 0)
        # 确保「已完成，下一步」可见且可用（上一个 _finish() 可能已禁用它）
        self._btn_next.show()
        self._btn_next.setEnabled(True)

        # 七彩闪烁
        self._rainbow_i = 0
        if not self._hint_blink.isActive():
            self._hint_blink.start()

    # ── 剪贴板检测（事件驱动） ──

    def _on_clipboard_change(self):
        """Qt 原生剪贴板变化信号 — 非阻塞，任意步骤检测任意密钥"""
        if self._current_platform is None:
            return

        text = self._clipboard.text().strip()
        if not text or text == self._last_clipboard:
            return
        self._last_clipboard = text

        # ── 腾讯云：始终检测三框（无论第几步）──
        if self._current_platform_name == "腾讯云":
            hit = self._tencent_check_clipboard(text)
            # 第 0 步检测到任意密钥 → 自动跳转到三框视图
            if hit and self._step_index == 0:
                self._step_index = 1
                self._show_step(1)
            return

        # ── 全局检测：扫描所有步骤，任意匹配即填入 ──
        if self._detected:
            return

        steps = self._current_platform["steps"]

        preview = text if len(text) <= 80 else text[:77] + "..."
        self._txt_preview.setText(preview)

        # 扫描所有步骤（不只是当前步骤），任意步骤匹配均可填入
        for i, step in enumerate(steps):
            if step.get("action") == "confirm":
                continue  # 确认步骤没有密钥格式

            # ── 批量检测（action: bulk）──
            if step.get("action") == "bulk":
                pattern = step.get("pattern", r".+")
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    self._detected = True
                    fields = step["fields"]
                    for field_name, group_idx in fields.items():
                        self._results[field_name] = m.group(group_idx)
                    count = len(fields)
                    self._lbl_status.setText(f"✅ 已检测到 {count} 个密钥字段！")
                    self._lbl_status.setStyleSheet(
                        "font-size: 13px; color: #4ade80; font-weight: bold;"
                    )
                    if i != self._step_index:
                        self._step_index = i  # 跳到匹配步骤
                    QTimer.singleShot(600, self._next_step)
                    return

            # ── 单字段检测 ──
            pattern = step.get("pattern", r".+")
            if re.match(pattern, text):
                self._detected = True
                self._results[step["field"]] = text
                self._lbl_status.setText(f"✅ 已检测到 {step['label']}！")
                self._lbl_status.setStyleSheet(
                    "font-size: 13px; color: #4ade80; font-weight: bold;"
                )
                if i != self._step_index:
                    self._step_index = i  # 跳到匹配步骤
                QTimer.singleShot(600, self._next_step)
                return

        # ── 无匹配：在当前步骤显示错误（确认步骤除外）──
        if self._step_index < len(steps):
            current_step = steps[self._step_index]
            if current_step.get("action") not in ("confirm",):
                self._lbl_status.setText(f"❌ 格式不符，期望：{current_step['hint']}")
                self._lbl_status.setStyleSheet("font-size: 12px; color: #f43f5e;")

    # ── 按钮动作 ──

    def _open_url(self):
        steps = self._current_platform["steps"]
        if self._step_index < len(steps):
            step = steps[self._step_index]
            url = step.get("url", self._current_platform["url"])
        else:
            url = self._current_platform["url"]
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _next_step(self):
        self._step_index += 1
        steps = self._current_platform["steps"]
        if self._step_index >= len(steps):
            self._finish()
        else:
            self._show_step(self._step_index)

    def _manual_next(self):
        """用户手动点击「已完成，下一步」/「完成」"""
        # ── 腾讯云第 1 步（确认）：进入第 2 步 ──
        if self._current_platform_name == "腾讯云" and self._step_index == 0:
            self._last_clipboard = ""
            self._detected = False
            self._next_step()
            return

        # ── 腾讯云第 2 步（三框一体化）：「完成」→ 发射信号 ──
        if self._current_platform_name == "腾讯云" and self._step_index == 1:
            if self._tc_auto_done:
                return  # 自动完成已触发，防止重复发射
            self._tc_auto_done = True
            self.completed.emit(dict(self._results), self._current_platform_name)
            self._btn_next.setEnabled(False)
            self._tc_status.setText("✅ 同步完成！密钥已自动填入")
            self._tc_status.setStyleSheet("font-size: 13px; color: #4ade80; font-weight: bold;")
            self._reset_timer.start(3000)
            return

        self._last_clipboard = ""
        self._detected = False
        self._next_step()

    def _prev_step(self):
        """回到上一步"""
        if self._step_index > 0:
            self._last_clipboard = ""
            self._detected = False
            self._step_index -= 1
            self._show_step(self._step_index)

    def _blink_hint(self):
        """提示文字七彩渐变循环"""
        self._rainbow_i = (self._rainbow_i + 1) % len(self.RAINBOW)
        c = self.RAINBOW[self._rainbow_i]
        self._lbl_hint.setStyleSheet(f"font-size: 12px; color: {c}; font-weight: bold;")

    def _hide_auth_hint(self):
        """隐藏实名认证提示"""
        self._auth_anim_timer.stop()
        self._lbl_auth_hint.hide()

    def _animate_auth_hint(self):
        """实名认证提示上下平移动画"""
        self._auth_y += 1 * self._auth_dir

        # 底部边界：按钮行顶部（留 4px 间距）
        btn_top = self._btn_next.y() - self._lbl_auth_hint.height() - 4

        if self._auth_dir == 1 and self._auth_y >= btn_top:
            self._auth_dir = -1
        elif self._auth_dir == -1 and self._auth_y <= self._auth_start_y:
            self._auth_dir = 1

        self._lbl_auth_hint.move(self._lbl_auth_hint.x(), self._auth_y)

    # ── 手势引导动画 ──

    def _run_gesture_animation(self):
        """启动手势引导动画：👆 从按钮下方伸出 → 向上连点三下 → 消失"""
        if self._gesture_target is None:
            return
        btn = self._gesture_target
        bx, by = btn.x(), btn.y()
        bw, bh = btn.width(), btn.height()
        cx = bx + bw // 2 - 16
        # 手指起始：按钮正下方 6px，直接可见，不被任何控件遮挡
        self._gesture_start_x = cx
        self._gesture_start_y = by + bh + 6
        self._gesture_label.move(cx, self._gesture_start_y)
        self._gesture_label.show()
        self._gesture_label.raise_()  # 确保在最顶层，不被按钮/进度条遮盖
        self._gesture_elapsed = 0
        self._gesture_timer.start()

    def _animate_gesture(self):
        """手势动画帧（50ms/帧，10 秒，从下往上连点三下）"""
        self._gesture_elapsed += 50
        t = self._gesture_elapsed  # ms

        if self._gesture_target is None:
            self._gesture_timer.stop()
            self._gesture_label.hide()
            return

        btn = self._gesture_target
        btn_top = btn.y()
        sx, sy = self._gesture_start_x, self._gesture_start_y
        rest_y = sy                              # 静止位（按钮下方 6px）
        tap_y = btn_top + btn.height() // 2       # 点击位（标签顶在按钮中心，指尖落在中下段不超文字）

        # ── 三击节奏：1400ms一击 + 1000ms间隔，总长 10 秒 ──
        TAP, GAP = 1400, 1000
        if t < TAP:                              # 第一击：向上按
            phase = t / TAP
            y = rest_y + (tap_y - rest_y) * self._ease_out_back(phase)
        elif t < TAP + GAP:                      # 弹回下方
            phase = (t - TAP) / GAP
            y = tap_y + (rest_y - tap_y) * self._ease_out(phase)
        elif t < 2*TAP + GAP:                    # 第二击
            phase = (t - TAP - GAP) / TAP
            y = rest_y + (tap_y - rest_y) * self._ease_out_back(phase)
        elif t < 2*(TAP + GAP):                  # 弹回
            phase = (t - 2*TAP - GAP) / GAP
            y = tap_y + (rest_y - tap_y) * self._ease_out(phase)
        elif t < 3*TAP + 2*GAP:                  # 第三击
            phase = (t - 2*TAP - 2*GAP) / TAP
            y = rest_y + (tap_y - rest_y) * self._ease_out_back(phase)
        elif t < 3*(TAP + GAP):                  # 弹回
            phase = (t - 3*TAP - 2*GAP) / GAP
            y = tap_y + (rest_y - tap_y) * self._ease_out(phase)
        elif t < 10000:                          # 静止停留
            y = rest_y
        else:                                    # 消失
            self._gesture_timer.stop()
            self._gesture_label.hide()
            self._gesture_target = None
            return

        self._gesture_label.move(sx, int(y))
        self._gesture_label.raise_()  # 每帧确保顶层

    @staticmethod
    def _ease_out(t: float) -> float:
        """缓出：1-(1-t)²"""
        return 1.0 - (1.0 - t) ** 2

    @staticmethod
    def _ease_out_back(t: float) -> float:
        """缓出+回弹：先冲过目标再弹回，模拟手指点击的干脆感"""
        c1 = 1.70158
        t -= 1.0
        return t * t * ((c1 + 1.0) * t + c1) + 1.0

    def _hide_gesture(self):
        """隐藏手势引导"""
        self._gesture_timer.stop()
        self._gesture_label.hide()
        self._gesture_target = None

    def _finish(self):
        self._hint_blink.stop()
        self._lbl_hint.setStyleSheet("")
        total = len(self._current_platform["steps"])
        self._progress.setValue(total)
        self._lbl_step.setText("✅ 同步完成！")
        self._lbl_hint.setText(f"已获取 {len(self._results)} 个凭证字段，密钥已自动填入")
        self._lbl_hint.setStyleSheet("font-size: 13px; color: #4ade80; font-weight: bold;")
        self._txt_preview.setPlaceholderText("可切换到「密钥管理」标签页查看")
        self._lbl_status.setText("")
        self._lbl_status.setStyleSheet("")
        self._btn_next.setEnabled(False)
        self._btn_prev.setEnabled(False)

        # 发射信号通知外部（SettingsDialog）填入密钥，携带平台名用于定位子标签
        self.completed.emit(dict(self._results), self._current_platform_name)

        # 3 秒后自动重置，方便继续同步其他平台
        self._reset_timer.start(3000)

    def _reset(self):
        """重置向导，回到初始状态（仅在 _finish 触发后有效）"""
        self._reset_timer.stop()
        self._begin_sync(self._combo_platform.currentText())
        self._refresh_on_show()
