"""系统托盘 — 托盘图标 + 右键菜单（显示/隐藏/退出）"""
import sys
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PySide6.QtCore import Qt


def _make_tray_icon() -> QIcon:
    """用 QPainter 绘制一个 32x32 的托盘图标（无需外部文件）"""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 圆形背景
    painter.setBrush(QColor("#7c5cfc"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)

    # "V" 字
    painter.setPen(QColor("#0d0d14"))
    font = QFont("Microsoft YaHei", 16, QFont.Bold)
    painter.setFont(font)
    painter.drawText(2, 2, 28, 28, Qt.AlignCenter, "V")

    painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    """系统托盘：右键菜单、双击恢复窗口"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._window = main_window

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[VoiceFlow] 系统托盘不可用，关闭窗口将直接退出", file=sys.stderr)
            self._available = False
            return
        self._available = True

        self.setIcon(_make_tray_icon())
        self.setToolTip("Voice Flow — 语音转文字")

        # 右键菜单
        menu = QMenu()

        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

        # 左键/双击 → 显示窗口
        self.activated.connect(self._on_activated)

        self.show()

    def _on_activated(self, reason):
        """托盘图标被点击"""
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self):
        """显示并激活主窗口"""
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _quit_app(self):
        """退出应用"""
        from PySide6.QtWidgets import QApplication
        self._window.force_quit()  # 强制退出，不最小化到托盘
        QApplication.instance().quit()
