"""声纹浮动窗口 — 镜面对称柱形图，固定柱位随机升降"""
import math, random
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
)

BG_COLOR = QColor(24, 24, 37, 225)
BORDER_COLOR = QColor(69, 71, 90, 110)


class _MirrorBars(QWidget):
    """固定柱位镜面对称 — 每柱独立随机高度，中间向上下对称"""

    BAR_COUNT = 40
    DECAY_UP = 1.0     # 上升瞬时到位
    DECAY_DOWN = 0.82  # 下降有衰减（避免机械感）
    SENSITIVITY = 0.65 # 柱间随机差异度

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.setMaximumHeight(30)
        self._bars = [0.0] * self.BAR_COUNT  # 上半部高度
        self._mirror = [0.0] * self.BAR_COUNT  # 下半部（独立衰减）
        self._level = 0.0

    def set_level(self, v: float):
        self._level = max(0.0, min(1.0, v))
        # 每柱独立设置目标高度，加随机抖动
        for i in range(self.BAR_COUNT):
            # 离中心越近越活跃（中间柱更灵敏）
            dist = abs(i - self.BAR_COUNT / 2) / (self.BAR_COUNT / 2)
            weight = 0.3 + 0.7 * (1.0 - dist)
            jitter = 0.4 + 0.6 * random.random()
            target = self._level * weight * jitter * self.SENSITIVITY * 2.0
            target = min(1.0, target)  # 硬上限
            self._bars[i] = max(self._bars[i], target)

        # 衰减
        for i in range(self.BAR_COUNT):
            self._bars[i] *= self.DECAY_DOWN
            if self._bars[i] < 0.003:
                self._bars[i] = 0.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w < 10:
            p.end()
            return

        cy = h / 2.0
        max_amp = h * 0.42  # 单侧最大振幅
        n = self.BAR_COUNT
        total_w = w - 6
        bar_w = max(2.0, total_w / n - 0.5)
        gap = (total_w - bar_w * n) / (n - 1) if n > 1 else 0

        for i in range(n):
            val = self._bars[i]
            if val < 0.004:
                continue

            x = 3 + i * (bar_w + gap)
            half_h = val * max_amp

            # 颜色：中间薰衣草 → 外侧偏粉
            dist = abs(i - n / 2) / (n / 2)
            t = val ** 0.6
            r = int(180 + (245 - 180) * (t * 0.6 + dist * 0.4))
            g = int(155 + (194 - 155) * t)
            b = int(240 + (220 - 240) * dist * 0.5)

            # 上半
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(r, g, b, int(150 + 90 * t)))
            upper = QRectF(x, cy - half_h, bar_w, half_h)
            p.drawRoundedRect(upper, 1.2, 1.2)

            # 下半（稍暗镜像）
            p.setBrush(QColor(r, g, b, int(80 + 70 * t)))
            lower = QRectF(x, cy, bar_w, half_h)
            p.drawRoundedRect(lower, 1.2, 1.2)

        p.end()

    def reset(self):
        self._bars = [0.0] * self.BAR_COUNT
        self._mirror = [0.0] * self.BAR_COUNT
        self.update()


class VoiceprintWidget(QWidget):
    """桌面浮动声纹 HUD — 镜面对称柱形图"""

    def __init__(self, config=None):
        super().__init__()
        self._config = config
        self.setObjectName("VoiceprintHUD")
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(220, 56)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 4, 14, 4)
        root.setSpacing(1)

        self._canvas = _MirrorBars()
        root.addWidget(self._canvas)

        self._lbl_info = QLabel("● 录音中  00:00")
        self._lbl_info.setAlignment(Qt.AlignCenter)
        self._lbl_info.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self._lbl_info.setStyleSheet(
            "color: #e4e4f0; background: transparent; font-size: 11px; font-weight: bold;"
        )
        root.addWidget(self._lbl_info)

        self._seconds = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._dot_phase = 0.0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._pulse_dot)

        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_opacity = 0.0

        self._drag_pos: QPoint | None = None
        self._position_above_taskbar()
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        radius = 12.0
        alpha = None if self._fade_opacity > 0.98 else int(230 * self._fade_opacity)

        bg = BG_COLOR if alpha is None else QColor(
            BG_COLOR.red(), BG_COLOR.green(), BG_COLOR.blue(), alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        shine = QLinearGradient(0, 0, 0, h * 0.38)
        shine.setColorAt(0.0, QColor(255, 255, 255, 14))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(shine)
        p.drawRoundedRect(QRectF(0, 0, w, h * 0.38), radius, radius)

        border_alpha = BORDER_COLOR.alpha() if alpha is None else int(
            BORDER_COLOR.alpha() * self._fade_opacity)
        pen = QPen(QColor(BORDER_COLOR.red(), BORDER_COLOR.green(),
                          BORDER_COLOR.blue(), border_alpha), 1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)

        p.end()

    def _position_above_taskbar(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            screen = app.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = geo.center().x() - self.width() // 2
                y = geo.bottom() - self.height() - 4
                self.move(x, y)

    def _fade_step(self):
        self._fade_opacity += 0.1
        if self._fade_opacity >= 1.0:
            self._fade_opacity = 1.0
            self._fade_timer.stop()
        self.update()

    def _pulse_dot(self):
        self._dot_phase += 0.12
        if self._dot_phase > 6.283:
            self._dot_phase -= 6.283
        v = 0.35 + 0.65 * abs(math.sin(self._dot_phase))
        r = int(166 + (203 - 166) * (1 - v))
        g = int(227 - (227 - 166) * (1 - v))
        b_val = int(161 + (247 - 161) * (1 - v))
        self._lbl_info.setStyleSheet(
            f"color: #{r:02x}{g:02x}{b_val:02x}; "
            "background: transparent; font-size: 11px; font-weight: bold;"
        )

    def start(self):
        self._seconds = 0
        self._lbl_info.setText("● 录音中  00:00")
        self._timer.start(1000)
        self._dot_phase = 0.0
        self._dot_timer.start(50)
        self._fade_opacity = 0.0
        self._fade_timer.start(18)
        self._position_above_taskbar()
        self.show()

    def stop(self):
        self._timer.stop()
        self._dot_timer.stop()
        self._canvas.reset()
        self._fade_opacity = 0.0
        self.hide()

    def set_level(self, level: float):
        self._canvas.set_level(level)

    def set_spectrum(self, bins: list):
        # 频谱压缩为单值驱动波形
        lo = len(bins) // 4
        hi = len(bins) * 3 // 4
        mids = bins[lo:hi]
        avg = sum(mids) / (len(mids) + 1e-8)
        v = math.tanh(avg * 3.0)
        self._canvas.set_level(v)

    def processing(self):
        self._timer.stop()
        self._dot_timer.stop()
        self._canvas.reset()
        self._lbl_info.setText("⏳ 正在分析...")
        self._lbl_info.setStyleSheet(
            "color: #f59e0b; background: transparent; font-size: 11px; font-weight: bold;"
        )

    def _tick(self):
        self._seconds += 1
        m, s = divmod(self._seconds, 60)
        self._lbl_info.setText(f"● 录音中  {m:02d}:{s:02d}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
