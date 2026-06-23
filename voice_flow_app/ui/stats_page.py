"""统计页面 — 指标卡片 + 扇形图 + 柱状图"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QSizePolicy, QPushButton
from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath, QLinearGradient
import math


STATS_STYLE = """
QWidget#statsPage { background-color: #0d0d14; }
QLabel#cardValue { color: #cba6f7; font-size: 24px; font-weight: bold; }
QLabel#cardLabel { color: #8888a8; font-size: 11px; }
QLabel#sectionTitle { color: #e4e4f0; font-size: 15px; font-weight: 600; }
"""


class _PieChart(QWidget):
    """扇形图 — QPainter 手绘"""

    COLORS = {
        # 英文 key（数据源）→ 颜色（腾讯流式/短连各不同色）
        "tencent": QColor("#7c5cfc"),           # 腾讯流式 → 紫色
        "tencent_sentence": QColor("#5b8def"),   # 腾讯短连 → 蓝色
        "aliyun": QColor("#f97316"),             # 阿里云 → 橙色
        "iflytek": QColor("#22c55e"),            # 讯飞 → 绿色
        # 中文 key（含后缀精确匹配 + 基础回退）
        "腾讯(流式)": QColor("#7c5cfc"),
        "腾讯(短连)": QColor("#5b8def"),
        "腾讯": QColor("#7c5cfc"),
        "阿里云": QColor("#f97316"),
        "讯飞": QColor("#22c55e"),
    }
    _FALLBACK = QColor("#6b7280")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict[str, float] = {}  # {label: value}
        self.setMinimumWidth(220)  # 高度由外部布局控制，对齐卡片

    def set_data(self, data: dict[str, float]):
        """设置数据 {标签: 数值}"""
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(10, 2, -10, -2)  # 上下极小边距，饼圆尽量撑满

        if not self._data or sum(self._data.values()) == 0:
            painter.setPen(QColor("#8888a8"))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(rect, Qt.AlignCenter, "暂无数据")
            return

        total = sum(self._data.values())

        # ── 布局：左边饼图，右边图例 ──
        # 饼图占左侧 55%，图例占右侧 45%
        pie_w = int((rect.width() - 10) * 0.55)
        side = min(pie_w, rect.height())
        pie_left = rect.left()
        pie_top = rect.top()  # 贴顶部，与卡片对齐
        pie_rect = QRect(pie_left, pie_top, side, side)
        base_center = pie_rect.center()
        base_radius = side // 2

        # ── 按值降序排列（大扇区在视觉底层） ──
        items = sorted(self._data.items(), key=lambda x: -x[1])
        labels = [it[0] for it in items]
        values = [it[1] for it in items]

        # ── 绘制爆炸扇形（占比越大外推越远） ──
        max_explode = int(base_radius * 0.15)  # 最大外推 = 半径的 15%
        start_angle = 90 * 16  # Qt: 1/16 度，从 12 点方向开始
        colors_used = []

        painter.setPen(Qt.NoPen)
        for label, val in zip(labels, values):
            span = int(360 * 16 * val / total)
            share = val / total if total > 0 else 0
            explode = int(max_explode * share)

            # 先精确匹配完整标签（如"腾讯(流式)"），再回退到基础名
            color = self.COLORS.get(label) or self.COLORS.get(label.split("(")[0].strip(), self._FALLBACK)
            colors_used.append(color)

            # 计算外推方向（扇区中心角）
            mid_angle_deg = (start_angle + span / 2) / 16
            mid_angle_rad = math.radians(mid_angle_deg)
            cx = base_center.x() + int(explode * math.cos(mid_angle_rad))
            cy = base_center.y() - int(explode * math.sin(mid_angle_rad))

            offset_rect = QRect(
                cx - base_radius, cy - base_radius,
                base_radius * 2, base_radius * 2,
            )

            painter.setBrush(QBrush(color))
            painter.drawPie(offset_rect, start_angle, span)

            start_angle += span

        # ── 右侧图例（色块 + 名称 + 比例 + 进度条）──
        legend_x = pie_rect.right() + 16
        legend_y = pie_rect.top() + 6
        row_h = 52  # 每行高度（4行×52=208px）
        painter.setFont(QFont("Microsoft YaHei", 9))

        for label, val, color in zip(labels, values, colors_used):
            pct = val / total * 100 if total > 0 else 0

            # 色块 10×10（贴行顶，居中偏上）
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(legend_x, legend_y + 4, 10, 10, 2, 2)

            # 名称（色块右侧，留足够间距）
            painter.setPen(QColor("#e4e4f0"))
            painter.drawText(legend_x + 18, legend_y + 12, label)

            # 比例 + 调用次数（名称下方，行高内的中间位置）
            painter.setPen(QColor("#a8a8c0"))
            pct_text = f"{pct:.1f}%"
            painter.drawText(legend_x + 18, legend_y + 28,
                           f"占比 {pct_text}  |  {int(val)} 次")

            # 细进度条（行底附近）
            bar_x = legend_x + 18
            bar_y = legend_y + 42
            bar_w = 90
            bar_h = 2
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#2a2a3e"))
            painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 1, 1)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(bar_x, bar_y, int(bar_w * pct / 100), bar_h, 1, 1)

            legend_y += row_h


class _BarChart(QWidget):
    """柱状图 — QPainter 手绘，7 天趋势"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []  # [{"date": "06-15", "count": 3, "duration": 45.2}, ...]
        self.setMinimumSize(280, 300)

    def set_data(self, data: list[dict]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # ── 留出左侧 Y 轴标注空间 + 顶部柱上文字空间 ──
        left_margin = 44    # 加大，给竖排标签足够空间
        top_margin = 12     # 柱顶标注文字空间（压缩以拉伸纵轴）
        bottom_margin = 70  # 底部：柱底→日期标签→"日期"，三层无重叠
        right_margin = 20   # 右侧留白
        rect = self.rect().adjusted(left_margin, top_margin, -right_margin, -bottom_margin)

        if not self._data:
            painter.setPen(QColor("#8888a8"))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            return

        max_count = max((d.get("count", 0) for d in self._data), default=1)
        # Y 轴刻度：紧凑头部空间（8%），5 档刻度充分利用纵向空间
        y_max = max(5, int(max_count * 1.08))
        y_step = max(1, max(1, y_max // 5))

        chart_left = rect.left()
        chart_right = rect.right()
        chart_top = rect.top()
        chart_bottom = rect.bottom()
        chart_h = chart_bottom - chart_top

        # ── Y 轴刻度 + 水平网格线 ──
        painter.setFont(QFont("Microsoft YaHei", 8))
        for tick_val in range(0, y_max + y_step, y_step):
            if tick_val > y_max:
                continue
            y_frac = tick_val / y_max if y_max > 0 else 0
            y = chart_bottom - int(y_frac * chart_h)

            # 网格线
            painter.setPen(QPen(QColor("#1e1e30"), 1))
            painter.drawLine(chart_left, y, chart_right, y)

            # Y 轴标签（白色，清晰可读）
            painter.setPen(QColor("#ffffff"))
            painter.drawText(2, y - 8, left_margin - 8, 16,
                           Qt.AlignRight | Qt.AlignVCenter, str(tick_val))

        # ── 柱子和数据 ──
        n = len(self._data)
        bar_w = min(20, (chart_right - chart_left) // n - 14)
        spacing = ((chart_right - chart_left) - bar_w * n) // (n + 1)

        painter.setPen(Qt.NoPen)
        for i, d in enumerate(self._data):
            count = d.get("count", 0)
            bar_h = int((count / y_max) * chart_h) if y_max > 0 else 0

            x = chart_left + spacing + i * (bar_w + spacing)
            bar_top_y = chart_bottom - bar_h

            # 柱子（渐变紫）
            grad = QLinearGradient(x, bar_top_y, x, chart_bottom)
            grad.setColorAt(0, QColor("#9170ff"))
            grad.setColorAt(1, QColor("#5a3fc0"))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(x, bar_top_y, bar_w, bar_h, 4, 4)

            # ── 柱顶上方标注：次数（大字）+ 时长（小字） ──
            # 文本区域加宽，防止 "14min" / "14分钟" 等被裁切
            label_w = bar_w + 20  # 确保足够宽

            # 次数 — 柱子上方留足够间距（白色加粗）
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            painter.drawText(x - 10, bar_top_y - 30, label_w, 16,
                           Qt.AlignCenter, str(count))

            # 时长 — 次数下方，远离柱子色块
            dur = d.get("duration", 0)
            dur_text = f"{int(dur)}s" if dur < 60 else f"{dur/60:.0f}min"
            painter.setPen(QColor("#c8c8d8"))
            painter.setFont(QFont("Microsoft YaHei", 8))
            painter.drawText(x - 10, bar_top_y - 14, label_w, 12,
                           Qt.AlignCenter, dur_text)

            # 日期标签
            date_label = d.get("date", "")
            if len(date_label) >= 10:
                date_label = date_label[5:]  # "06-15"
            elif len(date_label) >= 5:
                date_label = date_label[-5:]
            painter.setPen(QColor("#e8e8f0"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            # 中文日期（六月十六）至少需要 48px 宽才能完整显示
            date_rect_w = max(bar_w + 24, 48)
            painter.drawText(x - (date_rect_w - bar_w) // 2, chart_bottom + 14,
                           date_rect_w, 16, Qt.AlignCenter, date_label)

        # ── 底部标注：横轴含义（白色加粗，字间距） ──
        painter.setPen(QColor("#ffffff"))
        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        ch1_w = fm.horizontalAdvance("日")
        ch2_w = fm.horizontalAdvance("期")
        gap = 6  # 字间距
        total_w = ch1_w + gap + ch2_w
        start_x = rect.left() + (rect.width() - total_w) // 2
        base_y = self.rect().bottom() - 26
        painter.drawText(start_x, base_y, ch1_w, 16, Qt.AlignCenter, "日")
        painter.drawText(start_x + ch1_w + gap, base_y, ch2_w, 16, Qt.AlignCenter, "期")

        # ── 左侧标注：纵轴含义（竖排，留足左边距不被裁剪） ──
        painter.save()
        # 在 left_margin 区域内居中书写
        label_text = "录音次数"
        fm = QFontMetrics(QFont("Microsoft YaHei", 10))
        text_w = fm.horizontalAdvance(label_text)
        text_h = fm.height()
        # 旋转中心在左边缘中间
        painter.translate(18, rect.center().y() + text_w // 2)
        painter.rotate(-90)
        painter.setPen(QColor("#555570"))
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.drawText(-text_w // 2, 0, label_text)
        painter.restore()


class _StatCard(QFrame):
    """指标卡片 — 紫色数值 + 灰色标签"""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background-color: #1c1c2e; border-radius: 10px; "
            "border: 1px solid #2a2a3e; }"
        )
        self.setFixedHeight(74)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)

        self._value_lbl = QLabel("—")
        self._value_lbl.setObjectName("cardValue")
        self._value_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._value_lbl)

        lbl = QLabel(label)
        lbl.setObjectName("cardLabel")
        layout.addWidget(lbl)

    def set_value(self, text: str):
        self._value_lbl.setText(text)


class StatsPage(QWidget):
    """统计页面"""

    settings_clicked = Signal()

    def __init__(self, history_db, parent=None):
        super().__init__(parent)
        self.setObjectName("statsPage")
        self.setStyleSheet(STATS_STYLE)
        self._db = history_db

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 28)
        layout.setSpacing(12)

        # 标题行：左标题 + 右设置按钮
        title_row = QHBoxLayout()
        title = QLabel("📊 使用统计")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        title_row.addWidget(title)
        title_row.addStretch()
        btn_settings = QPushButton("⚙ 设置")
        btn_settings.setFixedSize(80, 28)
        btn_settings.setStyleSheet(
            "QPushButton { background: #7c5cfc; color: #fff; border: none; "
            "border-radius: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #9477ff; }"
        )
        btn_settings.setCursor(Qt.PointingHandCursor)
        btn_settings.clicked.connect(self.settings_clicked.emit)
        title_row.addWidget(btn_settings)
        layout.addLayout(title_row)

        # ── 节标题（独立行，上移对齐侧边栏"控制台"上边缘） ──
        _breath = QWidget()
        _breath.setFixedHeight(4)
        _breath.setStyleSheet("background: transparent;")
        layout.addWidget(_breath)

        section_header = QHBoxLayout()
        section_header.setContentsMargins(0, 0, 0, 0)
        section_header.setSpacing(6)

        pie_title = QLabel("STT 引擎用量分布")
        pie_title.setObjectName("sectionTitle")
        section_header.addWidget(pie_title, 3)

        cards_title = QLabel("关键指标")
        cards_title.setObjectName("sectionTitle")
        section_header.addWidget(cards_title, 2)

        layout.addLayout(section_header)

        # ═══════════════════════════════════════════════════
        # 上半部分：左扇形图 + 右田字卡片（网格对齐，不含标题）
        # ═══════════════════════════════════════════════════
        top_grid = QGridLayout()
        top_grid.setSpacing(6)
        top_grid.setColumnStretch(0, 3)
        top_grid.setColumnStretch(1, 2)

        # ── 扇形图（左）──
        self._pie = _PieChart()
        top_grid.addWidget(self._pie, 0, 0, Qt.AlignTop)

        cards_grid = QGridLayout()
        cards_grid.setSpacing(8)
        cards_grid.setColumnStretch(0, 1)
        cards_grid.setColumnStretch(1, 1)
        cards_grid.setRowStretch(0, 0)
        cards_grid.setRowStretch(1, 0)

        self._card_duration = _StatCard("总口述时间")
        cards_grid.addWidget(self._card_duration, 0, 0)

        self._card_speed = _StatCard("平均口述速度")
        cards_grid.addWidget(self._card_speed, 0, 1)

        self._card_chars = _StatCard("口述字数")
        cards_grid.addWidget(self._card_chars, 1, 0)

        self._card_saved = _StatCard("节省时间")
        cards_grid.addWidget(self._card_saved, 1, 1)

        # 卡片外包裹——与饼图等高，靠上放置
        card_area = QVBoxLayout()
        card_area.setContentsMargins(0, 0, 0, 0)
        card_area.setSpacing(0)
        card_area.addLayout(cards_grid)
        card_area.addStretch()
        top_grid.addLayout(card_area, 0, 1, Qt.AlignTop)

        # 饼图高度 = 卡片区总高（2卡 + 间距）
        card_grid_height = 2 * 74 + 8  # 156px（卡片区高度）
        # 饼图最低高度需容纳图例（4行×52px + 边距 ≈ 220px）
        self._pie.setMinimumHeight(max(card_grid_height, 220))
        self._pie.setMaximumHeight(max(card_grid_height, 220) * 2)

        layout.addLayout(top_grid, 2)  # 上半部分占比（给柱状图更多空间）

        # 柱状图与上方内容之间的呼吸间距
        _bar_breath = QWidget()
        _bar_breath.setFixedHeight(14)
        _bar_breath.setStyleSheet("background: transparent;")
        layout.addWidget(_bar_breath)

        # ═══════════════════════════════════════════════════
        # 下半部分：柱状图（左半）+ 留空（右半）
        # ═══════════════════════════════════════════════════
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        bar_layout = QVBoxLayout()
        bar_layout.setSpacing(6)
        self._chart_title2 = QLabel("过去 7 天趋势")
        self._chart_title2.setObjectName("sectionTitle")
        bar_layout.addWidget(self._chart_title2)
        self._bar = _BarChart()
        self._bar.setMinimumHeight(300)
        self._bar.setMaximumHeight(380)
        bar_layout.addWidget(self._bar, 1)
        bottom_row.addLayout(bar_layout, 1)

        # 右半留空（占位）
        placeholder = QLabel("")
        placeholder.setStyleSheet("color: #333350; font-size: 12px;")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bottom_row.addWidget(placeholder, 1)

        layout.addLayout(bottom_row, 1)

    def refresh(self):
        """从 HistoryDB 加载数据并刷新显示"""
        stats = self._db.get_stats_all_time()

        total_dur = stats["total_duration"]
        total_count = stats["total_count"]
        total_chars = stats["total_chars"]

        # 总口述时间
        h = int(total_dur // 3600)
        m = int((total_dur % 3600) // 60)
        self._card_duration.set_value(f"{h}h {m}min" if h > 0 else f"{m} 分钟")

        # 平均速度
        if total_dur > 0:
            spm = int(total_chars / (total_dur / 60))
            self._card_speed.set_value(f"{spm} 字/分钟")
        else:
            self._card_speed.set_value("—")

        # ── 口述字数 ──
        if total_chars >= 10000:
            wan = total_chars / 10000
            self._card_chars.set_value(f"{wan:.1f} 万字")
        else:
            self._card_chars.set_value(f"{total_chars:,} 字")

        # ── 节省时间（相比手打） ──
        # 假设手打速度 40 字/分钟，节省时间 = 手打耗时 - 口述耗时
        TYPING_SPEED = 40  # 字/分钟（中文平均手打速度）
        if total_chars > 0 and total_dur > 0:
            typing_minutes = total_chars / TYPING_SPEED
            voice_minutes = total_dur / 60
            saved_minutes = max(0, typing_minutes - voice_minutes)
            if saved_minutes >= 60:
                h = int(saved_minutes // 60)
                m = int(saved_minutes % 60)
                self._card_saved.set_value(f"{h}h {m}min" if h > 0 else f"{m} 分钟")
            else:
                self._card_saved.set_value(f"{saved_minutes:.0f} 分钟")
        else:
            self._card_saved.set_value("—")

        # 扇形图：按引擎聚合
        eng_data = {}
        eng_name_map = {
            "tencent": "腾讯(流式)", "tencent_sentence": "腾讯(短连)",
            "aliyun": "阿里云", "iflytek": "讯飞",
        }
        for eng, info in stats["engines"].items():
            label = eng_name_map.get(eng, eng)
            eng_data[label] = info["calls"]
        self._pie.set_data(eng_data)

        # 柱状图
        daily = self._db.get_daily_stats(days=7)
        self._bar.set_data(daily)
        self._chart_title2.setText(f"过去 7 天趋势（共 {total_count} 次录音）")

    def showEvent(self, event):
        """每次切换到统计页时自动刷新"""
        super().showEvent(event)
        self.refresh()
