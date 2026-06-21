"""统计页面 — 指标卡片 + 扇形图 + 柱状图"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
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
        "tencent": QColor("#7c5cfc"),
        "tencent_sentence": QColor("#7c5cfc"),
        "aliyun": QColor("#f97316"),
        "iflytek": QColor("#22c55e"),
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
            painter.drawText(rect, Qt.AlignCenter, "暂无数据")
            return

        total = sum(self._data.values())
        # 扇形图放在左上区域
        size = min(rect.width(), rect.height()) - 20
        pie_rect = rect.adjusted(0, 0, -(rect.width() - size), -(rect.height() - size))
        center = pie_rect.center()
        radius = size // 2

        start_angle = 90 * 16  # Qt 用 1/16 度
        labels = list(self._data.keys())
        values = list(self._data.values())

        for i, (label, val) in enumerate(zip(labels, values)):
            span = int(360 * 16 * val / total)
            color = self.COLORS.get(label.split("(")[0].strip(), self._FALLBACK)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPie(pie_rect, start_angle, span)
            start_angle += span

        # 图例在右侧
        legend_x = pie_rect.right() + 16
        y = pie_rect.top() + 8
        painter.setFont(QFont("Microsoft YaHei", 10))
        for i, (label, val) in enumerate(zip(labels, values)):
            pct = val / total * 100 if total > 0 else 0
            color = self.COLORS.get(label.split("(")[0].strip(), self._FALLBACK)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRect(legend_x, y, 12, 12)
            painter.setPen(QColor("#cdd6f4"))
            short_label = label[:8] if len(label) > 8 else label
            painter.drawText(legend_x + 18, y + 12, f"{short_label} {pct:.0f}%")
            y += 24


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
        rect = self.rect().adjusted(20, 30, -20, -30)

        if not self._data:
            painter.setPen(QColor("#8888a8"))
            painter.drawText(rect, Qt.AlignCenter, "暂无数据")
            return

        max_count = max((d.get("count", 0) for d in self._data), default=1)
        bar_w = max(24, (rect.width() - 20) // len(self._data) - 8)
        spacing = (rect.width() - bar_w * len(self._data)) // (len(self._data) + 1)

        bottom = rect.bottom()

        for i, d in enumerate(self._data):
            count = d.get("count", 0)
            bar_h = int((count / max_count) * rect.height() * 0.9) if max_count > 0 else 0

            x = rect.left() + spacing + i * (bar_w + spacing)

            # 紫色柱子
            painter.setBrush(QBrush(QColor("#7c5cfc")))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, bottom - bar_h, bar_w, bar_h, 4, 4)

            # 数值
            painter.setPen(QColor("#cdd6f4"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            painter.drawText(x - 4, bottom - bar_h - 6, bar_w + 8, 16,
                           Qt.AlignCenter, str(count))

            # 日期
            date_label = d.get("date", "")[-5:]  # "06-15"
            painter.setPen(QColor("#8888a8"))
            painter.drawText(x - 4, bottom + 16, bar_w + 8, 16,
                           Qt.AlignCenter, date_label)


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

        # ── 三张指标卡片 ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        self._card_duration = _StatCard("总口述时间")
        cards_row.addWidget(self._card_duration)

        self._card_speed = _StatCard("平均口述速度")
        cards_row.addWidget(self._card_speed)

        self._card_count = _StatCard("总录音次数")
        cards_row.addWidget(self._card_count)

        layout.addLayout(cards_row)

        # ── 第二行：口述字数 + 节省时间 ──
        cards_row2 = QHBoxLayout()
        cards_row2.setSpacing(12)

        self._card_chars = _StatCard("口述字数")
        cards_row2.addWidget(self._card_chars)

        self._card_saved = _StatCard("节省时间")
        cards_row2.addWidget(self._card_saved)

        # 占位撑满，保持卡片左对齐
        cards_row2.addStretch()

        layout.addLayout(cards_row2)

        # ── 图表区：扇形图 + 柱状图 ──
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(8)
        chart_title1 = QLabel("STT 引擎用量分布")
        chart_title1.setObjectName("sectionTitle")
        left.addWidget(chart_title1)

        self._pie = _PieChart()
        left.addWidget(self._pie, 1)
        charts_row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        chart_title2 = QLabel("过去 7 天趋势")
        chart_title2.setObjectName("sectionTitle")
        right.addWidget(chart_title2)

        self._bar = _BarChart()
        right.addWidget(self._bar, 1)
        charts_row.addLayout(right, 1)

        layout.addLayout(charts_row, 1)

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

        # 总次数
        self._card_count.set_value(str(total_count))

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

    def showEvent(self, event):
        """每次切换到统计页时自动刷新"""
        super().showEvent(event)
        self.refresh()
