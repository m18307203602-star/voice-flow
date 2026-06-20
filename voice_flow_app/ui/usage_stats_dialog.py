"""用量统计对话框 — STT + LLM 月度使用量 + 费用明细"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QFrame, QScrollArea, QWidget, QPushButton, QGridLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


# ═══════════════════════════════════════════════════════════════
# 定价数据（单一来源，所有显示由此驱动）
# ═══════════════════════════════════════════════════════════════

STT_PRICING = {
    "tencent_sentence": {
        "label": "腾讯云 · 短连接",
        "color": "#7c5cfc",
        "unit": "次",
        "free_quota": 5_000,
        "free_label": "5,000 次/月",
        "paid_unit": "千次",
        "paid_price": 3.5,
        "paid_label": "¥3.5/千次",
    },
    "tencent": {
        "label": "腾讯云 · 流式",
        "color": "#7c5cfc",
        "unit": "小时",
        "free_quota": 5,
        "free_label": "5 小时/月",
        "paid_unit": "小时",
        "paid_price": 3.5,
        "paid_label": "¥3.5/小时",
    },
    "aliyun": {
        "label": "阿里云 · 流式",
        "color": "#f59e0b",
        "unit": "小时",
        "free_quota": 5,
        "free_label": "5 小时/月",
        "paid_unit": "小时",
        "paid_price": 3.5,
        "paid_label": "¥3.5/小时",
    },
    "iflytek": {
        "label": "讯飞 · 流式",
        "color": "#4ade80",
        "unit": "小时",
        "free_quota": 5,
        "free_label": "5 小时/月",
        "paid_unit": "小时",
        "paid_price": 3.5,
        "paid_label": "¥3.5/小时",
    },
}

LLM_PRICING = {
    "Qwen3.5-Flash": {
        "color": "#7c5cfc",
        "price_in": 0.2,
        "price_out": 0.4,
        "label_in": "¥0.2/百万",
        "label_out": "¥0.4/百万",
        "free_note": "百万 token 免费",
    },
    "Qwen-Plus": {
        "color": "#7c5cfc",
        "price_in": 0.8,
        "price_out": 2.0,
        "label_in": "¥0.8/百万",
        "label_out": "¥2/百万",
        "free_note": "百万 token 免费试用 → 付费",
    },
    "MiMo Flash": {
        "color": "#7c5cfc",
        "price_in": 0.7,
        "price_out": 2.0,
        "label_in": "¥0.7/百万",
        "label_out": "¥2/百万",
        "free_note": "",
    },
    "DeepSeek-Chat": {
        "color": "#4ade80",
        "price_in": 1.0,
        "price_out": 2.0,
        "label_in": "¥1/百万",
        "label_out": "¥2/百万",
        "free_note": "",
    },
    "Gemini 2.0 Flash": {
        "color": "#f59e0b",
        "price_in": 0,
        "price_out": 0,
        "label_in": "免费",
        "label_out": "免费",
        "free_note": "完全免费",
    },
}


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def _fmt_price(yuan: float) -> str:
    if yuan == 0:
        return "¥0"
    if yuan < 0.01:
        return f"¥{yuan:.4f}"
    if yuan < 1:
        return f"¥{yuan:.2f}"
    return f"¥{yuan:.2f}"


class BarWidget(QFrame):
    """单条数据：标签 + 进度条 + 数值"""

    def __init__(self, label: str, value: float, max_val: float,
                 unit: str, color: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(60)
        lbl.setStyleSheet("color: #8888a8; font-size: 11px;")
        layout.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 1000)
        pct = min(100, value / max_val * 100) if max_val > 0 else 0
        bar.setValue(int(pct * 10))
        bar.setTextVisible(False)
        bar.setFixedHeight(12)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1c1c2e;
                border: 1px solid #2a2a3e;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(bar, 1)

        if unit in ("次", "小时"):
            val_text = f"{value}/{max_val}{unit}" if max_val > 0 else f"{value}{unit}"
        else:
            val_text = _fmt_tokens(value) + unit
        num = QLabel(val_text)
        num.setFixedWidth(80)
        num.setStyleSheet("color: #bac2de; font-size: 11px;")
        num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(num)


class UsageStatsDialog(QDialog):
    """月度用量 + 费用明细对话框"""

    LLM_ORDER = ["MiMo Flash", "Qwen3.5-Flash", "Qwen-Plus", "DeepSeek-Chat", "Gemini 2.0 Flash"]

    def __init__(self, history_db, parent=None):
        super().__init__(parent)
        self._db = history_db
        self.setWindowTitle("用量统计 — 本月")
        self.setMinimumSize(520, 600)
        self.setStyleSheet("QDialog { background-color: #0d0d14; }")
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # ── 标题栏 ──
        title_row = QHBoxLayout()
        self._lbl_title = QLabel("本月用量统计")
        self._lbl_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self._lbl_title.setStyleSheet("color: #e4e4f0;")
        title_row.addWidget(self._lbl_title)
        title_row.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setFixedWidth(60)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #1c1c2e; color: #e4e4f0;
                border: 1px solid #2a2a3e; border-radius: 4px; padding: 4px 12px;
            }
            QPushButton:hover { background-color: #2a2a3e; }
        """)
        btn_refresh.clicked.connect(self.refresh)
        title_row.addWidget(btn_refresh)
        root.addLayout(title_row)

        # ── 滚动区域 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(10)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll)

    # ═══════════════════════════════════════════════
    # 刷新入口
    # ═══════════════════════════════════════════════

    def refresh(self):
        # 清除旧内容
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        usage = self._db.get_monthly_usage()
        llm_by_model = self._db.get_monthly_llm_by_model()

        # ── STT 用量 ──
        self._build_stt_section(usage)

        # ── LLM 用量 ──
        self._build_llm_section(llm_by_model)

        # ── 定价参考 ──
        self._build_pricing_reference()

        # ── 底部汇总 ──
        self._build_summary(usage, llm_by_model)

        self._scroll_layout.addStretch()

    # ═══════════════════════════════════════════════
    # STT 用量区块
    # ═══════════════════════════════════════════════

    def _build_stt_section(self, usage: dict):
        self._scroll_layout.addWidget(self._section_header("🎤 STT 引擎用量"))
        container = QVBoxLayout()
        container.setContentsMargins(16, 8, 16, 8)
        container.setSpacing(6)

        for engine_key in ["tencent_sentence", "tencent", "aliyun", "iflytek"]:
            pricing = STT_PRICING.get(engine_key)
            if not pricing:
                continue
            card = self._stt_card(engine_key, pricing, usage)
            container.addWidget(card)
        self._scroll_layout.addLayout(container)

    def _stt_card(self, engine_key: str, pricing: dict, usage: dict) -> QFrame:
        """单条 STT 引擎卡片：用量条 + 费用预估"""
        data = usage.get(engine_key, {"calls": 0, "total_duration": 0})
        free_quota = pricing["free_quota"]
        color = pricing["color"]

        card = QFrame()
        card.setStyleSheet("""
            QFrame { background-color: #181825; border: 1px solid #1c1c2e;
                     border-radius: 6px; }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        # 第一行：引擎名 + 用量值 + 免费额度
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        name_lbl = QLabel(pricing["label"])
        name_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        row1.addWidget(name_lbl)

        if pricing["unit"] == "次":
            used = data.get("calls", 0)
            max_val = free_quota
            unit = "次"
        else:
            used = round(data.get("total_duration", 0) / 3600, 2)
            max_val = free_quota
            unit = "小时"

        row1.addStretch()
        free_lbl = QLabel(f"免费额度: {pricing['free_label']}")
        free_lbl.setStyleSheet("color: #8888a8; font-size: 11px;")
        row1.addWidget(free_lbl)
        layout.addLayout(row1)

        # 用量进度条
        bar = BarWidget("用量", used, max_val, unit, color)
        layout.addWidget(bar)

        # 费用预估
        pct = (used / max_val * 100) if max_val > 0 else 0
        if pct <= 100:
            cost_text = "本月费用: ¥0（免费额度内）"
            cost_color = "#4ade80"
        else:
            over = used - max_val
            if pricing["unit"] == "次":
                cost = over / 1000 * pricing["paid_price"]
            else:
                cost = over * pricing["paid_price"]
            cost_text = f"本月费用: {_fmt_price(cost)}（超出 {pricing['free_label']}，{pricing['paid_label']}）"
            cost_color = "#fab387"

        cost_lbl = QLabel(cost_text)
        cost_lbl.setStyleSheet(f"color: {cost_color}; font-size: 11px; padding-left: 16px;")
        layout.addWidget(cost_lbl)

        return card

    # ═══════════════════════════════════════════════
    # LLM 用量区块
    # ═══════════════════════════════════════════════

    def _build_llm_section(self, llm_by_model: dict):
        self._scroll_layout.addWidget(self._section_header("🧠 LLM 模型用量"))
        container = QVBoxLayout()
        container.setContentsMargins(16, 8, 16, 8)
        container.setSpacing(6)

        for name in self.LLM_ORDER:
            data = llm_by_model.get(name, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            pricing = LLM_PRICING.get(name)
            if not pricing:
                continue
            card = self._llm_card(name, data, pricing)
            container.addWidget(card)
        self._scroll_layout.addLayout(container)

    def _llm_card(self, name: str, data: dict, pricing: dict) -> QFrame:
        """单条 LLM 模型卡片：输入/输出 token + 单价 + 费用预估"""
        color = pricing["color"]
        pin = pricing["price_in"]
        pout = pricing["price_out"]
        label_in = pricing["label_in"]
        label_out = pricing["label_out"]
        prompt_t = data.get("prompt_tokens", 0)
        completion_t = data.get("completion_tokens", 0)
        calls = data.get("calls", 0)
        total_t = prompt_t + completion_t

        card = QFrame()
        card.setStyleSheet("""
            QFrame { background-color: #181825; border: 1px solid #1c1c2e;
                     border-radius: 6px; }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        # 第一行：模型名 + 调用次数
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        row1.addWidget(name_lbl)
        calls_lbl = QLabel(f"({calls} 次调用)")
        calls_lbl.setStyleSheet("color: #8888a8; font-size: 11px;")
        row1.addWidget(calls_lbl)
        row1.addStretch()
        if pricing["free_note"]:
            free_note = QLabel(pricing["free_note"])
            free_note.setStyleSheet("color: #4ade80; font-size: 10px;")
            row1.addWidget(free_note)
        layout.addLayout(row1)

        # 输入 token 行
        in_row = QHBoxLayout()
        in_row.setSpacing(6)
        in_bar = BarWidget("  输入", prompt_t, 1_000_000, " tokens", "#7c5cfc")
        in_row.addWidget(in_bar, 1)
        in_price = QLabel(label_in)
        in_price.setFixedWidth(70)
        in_price.setStyleSheet("color: #8888a8; font-size: 10px;")
        in_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        in_row.addWidget(in_price)
        layout.addLayout(in_row)

        # 输出 token 行
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_bar = BarWidget("  输出", completion_t, 1_000_000, " tokens", "#4ade80")
        out_row.addWidget(out_bar, 1)
        out_price = QLabel(label_out)
        out_price.setFixedWidth(70)
        out_price.setStyleSheet("color: #8888a8; font-size: 10px;")
        out_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        out_row.addWidget(out_price)
        layout.addLayout(out_row)

        # 合计 + 费用预估
        total_row = QHBoxLayout()
        total_row.setSpacing(6)
        total_bar = BarWidget("  合计", total_t, 1_000_000, " tokens", color)
        total_row.addWidget(total_bar, 1)

        # 费用计算
        cost = (prompt_t / 1_000_000) * pin + (completion_t / 1_000_000) * pout
        cost_lbl = QLabel(f"预估 {_fmt_price(cost)}")
        cost_lbl.setFixedWidth(70)
        cost_lbl.setStyleSheet("color: #fab387; font-size: 10px; font-weight: bold;")
        cost_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        total_row.addWidget(cost_lbl)
        layout.addLayout(total_row)

        return card

    # ═══════════════════════════════════════════════
    # 定价参考表
    # ═══════════════════════════════════════════════

    def _build_pricing_reference(self):
        self._scroll_layout.addWidget(self._section_header("📊 定价参考"))

        ref = QFrame()
        ref.setStyleSheet("""
            QFrame { background-color: #181825; border: 1px solid #1c1c2e;
                     border-radius: 6px; }
        """)
        ref_layout = QVBoxLayout(ref)
        ref_layout.setContentsMargins(12, 8, 12, 8)
        ref_layout.setSpacing(4)

        # STT 定价表
        stt_title = QLabel("🎤 STT 引擎")
        stt_title.setStyleSheet("color: #7c5cfc; font-weight: bold; font-size: 11px;")
        ref_layout.addWidget(stt_title)

        stt_grid = QGridLayout()
        stt_grid.setSpacing(4)
        stt_grid.addWidget(self._grid_header("引擎"), 0, 0)
        stt_grid.addWidget(self._grid_header("免费额度"), 0, 1)
        stt_grid.addWidget(self._grid_header("超出单价"), 0, 2)

        for i, (key, p) in enumerate(STT_PRICING.items(), 1):
            stt_grid.addWidget(self._grid_cell(p["label"][:12], p["color"]), i, 0)
            stt_grid.addWidget(self._grid_cell(p["free_label"], "#4ade80"), i, 1)
            stt_grid.addWidget(self._grid_cell(p["paid_label"], "#fab387"), i, 2)
        ref_layout.addLayout(stt_grid)

        ref_layout.addSpacing(8)

        # LLM 定价表
        llm_title = QLabel("🧠 LLM 模型")
        llm_title.setStyleSheet("color: #7c5cfc; font-weight: bold; font-size: 11px;")
        ref_layout.addWidget(llm_title)

        llm_grid = QGridLayout()
        llm_grid.setSpacing(4)
        llm_grid.addWidget(self._grid_header("模型"), 0, 0)
        llm_grid.addWidget(self._grid_header("输入/百万"), 0, 1)
        llm_grid.addWidget(self._grid_header("输出/百万"), 0, 2)
        llm_grid.addWidget(self._grid_header("备注"), 0, 3)

        for i, (name, p) in enumerate(LLM_PRICING.items(), 1):
            llm_grid.addWidget(self._grid_cell(name, p["color"]), i, 0)
            llm_grid.addWidget(self._grid_cell(p["label_in"], "#7c5cfc"), i, 1)
            llm_grid.addWidget(self._grid_cell(p["label_out"], "#4ade80"), i, 2)
            llm_grid.addWidget(self._grid_cell(p.get("free_note", "") or "—", "#8888a8"), i, 3)
        ref_layout.addLayout(llm_grid)

        self._scroll_layout.addWidget(ref)

    def _grid_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #585b70; font-size: 10px; font-weight: bold;")
        return lbl

    def _grid_cell(self, text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: 10px;")
        return lbl

    # ═══════════════════════════════════════════════
    # 底部汇总
    # ═══════════════════════════════════════════════

    def _build_summary(self, usage: dict, llm_by_model: dict):
        # STT 汇总
        total_stt_calls = sum(u.get("calls", 0) for u in usage.values())

        # STT 费用
        stt_cost = 0.0
        for eng_key, data in usage.items():
            pricing = STT_PRICING.get(eng_key)
            if not pricing:
                continue
            if pricing["unit"] == "次":
                used = data.get("calls", 0)
            else:
                used = round(data.get("total_duration", 0) / 3600, 2)
            over = used - pricing["free_quota"]
            if over > 0:
                if pricing["unit"] == "次":
                    stt_cost += over / 1000 * pricing["paid_price"]
                else:
                    stt_cost += over * pricing["paid_price"]

        # LLM 汇总
        total_llm_calls = 0
        total_llm_tokens = 0
        llm_cost = 0.0
        for name, data in llm_by_model.items():
            if name not in LLM_PRICING:
                continue
            pricing = LLM_PRICING[name]
            p = data.get("prompt_tokens", 0)
            c = data.get("completion_tokens", 0)
            total_llm_calls += data.get("calls", 0)
            total_llm_tokens += p + c
            llm_cost += (p / 1_000_000) * pricing["price_in"] + (c / 1_000_000) * pricing["price_out"]

        total_cost = stt_cost + llm_cost

        # 三行汇总
        usage_line = QLabel(
            f"本月用量：STT {total_stt_calls} 次  |  "
            f"LLM {total_llm_calls} 次，{_fmt_tokens(total_llm_tokens)} token"
        )
        usage_line.setStyleSheet("color: #8888a8; font-size: 11px; padding: 4px 16px;")

        cost_line = QLabel(f"本月预估总费用：{_fmt_price(total_cost)}")
        cost_line.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: bold; padding: 4px 16px;")

        note_line = QLabel("⚠️ 费用为估算值，以各平台实际账单为准")
        note_line.setStyleSheet("color: #8888a8; font-size: 10px; padding: 0 16px;")

        self._scroll_layout.addWidget(usage_line)
        self._scroll_layout.addWidget(cost_line)
        self._scroll_layout.addWidget(note_line)

    # ═══════════════════════════════════════════════
    # 工具
    # ═══════════════════════════════════════════════

    def _section_header(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: #181825; border-radius: 6px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        lbl = QLabel(title)
        lbl.setFont(QFont("Microsoft YaHei", 12))
        lbl.setStyleSheet("color: #e4e4f0; font-weight: bold;")
        layout.addWidget(lbl)
        return frame
