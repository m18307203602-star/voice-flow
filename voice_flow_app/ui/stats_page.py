"""统计页面 — 指标卡片 + 扇形图 + 柱状图"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QSizePolicy
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath, QLinearGradient
import math


STATS_STYLE = """
QWidget#statsPage { background-color: #0d0d14; }
QLabel#cardValue { color: #cba6f7; font-size: 28px; font-weight: bold; }
QLabel#cardLabel { color: #8888a8; font-size: 12px; }
QLabel#sectionTitle { color: #e4e4f0; font-size: 15px; font-weight: 600; }
"""


class _PieChart(QWidget):
    """扇形图 — QPainter 手绘"""

    COLORS = {
        # 英文 key（数据源）→ 颜色
        "tencent": QColor("#7c5cfc"),
        "tencent_sentence": QColor("#7c5cfc"),
        "aliyun": QColor("#f97316"),
        "iflytek": QColor("#22c55e"),
        # 中文 key（折分后的显示名）→ 同一颜色
        "腾讯": QColor("#7c5cfc"),
        "阿里云": QColor("#f97316"),
        "讯飞": QColor("#22c55e"),
    }
    _FALLBACK = QColor("#6b7280")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict[str, float] = {}  # {label: value}
        self.setMinimumSize(220, 200)

    def set_data(self, data: dict[str, float]):
        """设置数据 {标签: 数值}"""
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(10, 10, -10, -10)

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
        pie_top = rect.top() + (rect.height() - side) // 2
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

            color = self.COLORS.get(label.split("(")[0].strip(), self._FALLBACK)
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

        # ── 右侧图例（竖向排列，每行：色块 + 名称 + 占比 + 次数） ──
        legend_x = pie_rect.right() + 16
        legend_y = pie_rect.top() + 4
        line_h = 26
        painter.setFont(QFont("Microsoft YaHei", 10))

        for label, val, color in zip(labels, values, colors_used):
            pct = val / total * 100 if total > 0 else 0

            # 色块
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(legend_x, legend_y, 14, 14, 3, 3)

            # 名称
            painter.setPen(QColor("#e4e4f0"))
            painter.drawText(legend_x + 20, legend_y + 12, label)

            # 百分比
            painter.setPen(QColor("#8888a8"))
            pct_text = f"{pct:.1f}%"
            painter.drawText(legend_x + 20, legend_y + 26, f"占比 {pct_text}  |  调用 {int(val)} 次")

            # 细进度条（视觉化占比）
            bar_x = legend_x + 20
            bar_y = legend_y + 30
            bar_w = 100
            bar_h = 3
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#2a2a3e"))
            painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 1, 1)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(bar_x, bar_y, int(bar_w * pct / 100), bar_h, 1, 1)

            legend_y += line_h + 22  # 行高 + 进度条空间


class _BarChart(QWidget):
    """柱状图 — QPainter 手绘，7 天趋势"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []  # [{"date": "06-15", "count": 3, "duration": 45.2}, ...]
        self.setMinimumSize(280, 200)

    def set_data(self, data: list[dict]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # ── 留出左侧 Y 轴标注空间 + 顶部柱上文字空间 ──
        left_margin = 44    # 加大，给竖排标签足够空间
        top_margin = 22     # 柱顶标注文字的空间
        bottom_margin = 30
        right_margin = 12
        rect = self.rect().adjusted(left_margin, top_margin, -right_margin, -bottom_margin)

        if not self._data:
            painter.setPen(QColor("#8888a8"))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            return

        max_count = max((d.get("count", 0) for d in self._data), default=1)
        # Y 轴刻度范围：至少显示 5，且向上取整
        y_max = max(5, int(max_count * 1.2))
        y_step = max(1, y_max // 4)

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

            # Y 轴标签
            painter.setPen(QColor("#666680"))
            painter.drawText(2, y - 8, left_margin - 8, 16,
                           Qt.AlignRight | Qt.AlignVCenter, str(tick_val))

        # ── 柱子和数据 ──
        n = len(self._data)
        bar_w = min(28, (chart_right - chart_left) // n - 10)
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
            # 次数 — 柱子上方留足够间距
            painter.setPen(QColor("#cdd6f4"))
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            painter.drawText(x - 4, bar_top_y - 30, bar_w + 8, 16,
                           Qt.AlignCenter, str(count))

            # 时长 — 次数下方，远离柱子色块
            dur = d.get("duration", 0)
            dur_text = f"{int(dur)}s" if dur < 60 else f"{dur/60:.0f}min"
            painter.setPen(QColor("#777790"))
            painter.setFont(QFont("Microsoft YaHei", 8))
            painter.drawText(x - 4, bar_top_y - 14, bar_w + 8, 12,
                           Qt.AlignCenter, dur_text)

            # 日期标签
            date_label = d.get("date", "")
            if len(date_label) >= 10:
                date_label = date_label[5:]  # "06-15"
            elif len(date_label) >= 5:
                date_label = date_label[-5:]
            painter.setPen(QColor("#8888a8"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            painter.drawText(x - 4, chart_bottom + 10, bar_w + 8, 16,
                           Qt.AlignCenter, date_label)

        # ── 底部标注：横轴含义 ──
        painter.setPen(QColor("#555570"))
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.drawText(rect.left(), self.rect().bottom() - 4,
                        rect.width(), 16, Qt.AlignCenter, "日期")

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
        self.setFixedHeight(90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

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

    def __init__(self, history_db, parent=None):
        super().__init__(parent)
        self.setObjectName("statsPage")
        self.setStyleSheet(STATS_STYLE)
        self._db = history_db

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title = QLabel("📊 使用统计")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # ═══════════════════════════════════════════════════
        # 上半部分：左扇形图 + 右田字卡片
        # ═══════════════════════════════════════════════════
        top_row = QHBoxLayout()
        top_row.setSpacing(20)

        # ── 左：扇形图 ──
        pie_layout = QVBoxLayout()
        pie_layout.setSpacing(8)
        pie_title = QLabel("STT 引擎用量分布")
        pie_title.setObjectName("sectionTitle")
        pie_layout.addWidget(pie_title)
        self._pie = _PieChart()
        pie_layout.addWidget(self._pie, 1)
        top_row.addLayout(pie_layout, 3)

        # ── 右：田字形 2×2 卡片 ──
        cards_grid = QGridLayout()
        cards_grid.setSpacing(10)
        cards_grid.setColumnStretch(0, 1)
        cards_grid.setColumnStretch(1, 1)
        cards_grid.setRowStretch(0, 1)
        cards_grid.setRowStretch(1, 1)

        self._card_duration = _StatCard("总口述时间")
        cards_grid.addWidget(self._card_duration, 0, 0)

        self._card_speed = _StatCard("平均口述速度")
        cards_grid.addWidget(self._card_speed, 0, 1)

        self._card_chars = _StatCard("口述字数")
        cards_grid.addWidget(self._card_chars, 1, 0)

        self._card_saved = _StatCard("节省时间")
        cards_grid.addWidget(self._card_saved, 1, 1)

        top_row.addLayout(cards_grid, 2)
        layout.addLayout(top_row, 3)

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
        self._bar.setMinimumHeight(180)
        self._bar.setMaximumHeight(240)
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
