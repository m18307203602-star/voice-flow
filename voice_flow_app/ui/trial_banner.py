"""许可证状态底栏 — Typeless 风格，显示试用进度 / Pro 状态"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont


BANNER_STYLE = """
QWidget#licenseFooter {
    background-color: #12121a;
    border-top: 1px solid #1e1e30;
}
QLabel#footerLabel {
    color: #8888a8;
    font-size: 12px;
}
QLabel#footerStatus {
    color: #cdd6f4;
    font-size: 12px;
}
QPushButton#footerBtn {
    background-color: #7c5cfc;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#footerBtn:hover {
    background-color: #9170ff;
}
QProgressBar {
    background-color: #1e1e30;
    border: none;
    border-radius: 2px;
    height: 4px;
    max-height: 4px;
}
QProgressBar::chunk {
    background-color: #7c5cfc;
    border-radius: 2px;
}
"""

TRIAL_DAYS = 7


class LicenseBanner(QWidget):
    """Typeless 风格许可证底栏"""

    activate_clicked = Signal()

    def __init__(self, license_manager, parent=None):
        super().__init__(parent)
        self._lm = license_manager

        self.setObjectName("licenseFooter")
        self.setStyleSheet(BANNER_STYLE)
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # 左侧：标签
        self._tag = QLabel("Pro Trial")
        self._tag.setObjectName("footerLabel")
        self._tag.setFixedWidth(70)
        layout.addWidget(self._tag)

        # 中间：状态文字 + 进度条
        self._status = QLabel()
        self._status.setObjectName("footerStatus")
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, TRIAL_DAYS)
        self._progress.setValue(0)
        self._progress.setFixedWidth(100)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        layout.addStretch()

        # 右侧：升级按钮
        self._btn = QPushButton("升级Pro")
        self._btn.setObjectName("footerBtn")
        self._btn.clicked.connect(self.activate_clicked.emit)
        layout.addWidget(self._btn)

        self.refresh()

    def refresh(self):
        state = self._lm.get_state()

        if state.value == "trial_active":
            self._show_trial()
        elif state.value in ("activated", "permanent"):
            self._show_activated()
        elif state.value in ("expired", "trial_expired"):
            self._show_expired()
        elif state.value == "activated_offline":
            self._show_offline()
        else:
            self._show_locked()

    def _show_trial(self):
        self._tag.setText("Pro Trial")
        self._tag.setStyleSheet("color: #f59e0b; font-size: 12px; font-weight: 600;")
        remaining = max(0, self._lm.get_remaining_days())
        used = TRIAL_DAYS - remaining
        self._status.setText(f"已使用 {used} 天 / 共 {TRIAL_DAYS} 天")
        self._progress.setVisible(True)
        self._progress.setValue(used)
        self._btn.setVisible(True)

    def _show_activated(self):
        self._tag.setText("Pro")
        self._tag.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 600;")
        self._status.setText(self._lm.get_status_text())
        self._progress.setVisible(False)
        self._btn.setVisible(False)

    def _show_expired(self):
        self._tag.setText("已过期")
        self._tag.setStyleSheet("color: #f43f5e; font-size: 12px; font-weight: 600;")
        self._status.setText(self._lm.get_status_text())
        self._progress.setVisible(False)
        self._btn.setVisible(True)

    def _show_offline(self):
        self._tag.setText("离线")
        self._tag.setStyleSheet("color: #f59e0b; font-size: 12px; font-weight: 600;")
        self._status.setText("请连接网络验证许可证")
        self._progress.setVisible(False)
        self._btn.setVisible(False)

    def _show_locked(self):
        self._tag.setText("未激活")
        self._tag.setStyleSheet("color: #f43f5e; font-size: 12px; font-weight: 600;")
        self._status.setText("软件已锁定 — 需升级Pro")
        self._progress.setVisible(False)
        self._btn.setVisible(True)


# Backward-compatible alias
TrialBanner = LicenseBanner
