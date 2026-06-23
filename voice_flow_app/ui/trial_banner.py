"""许可证状态底栏 — Typeless 风格，显示试用进度 / Pro 状态"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QProgressBar
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

TRIAL_DAYS = 3


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


# ═══════════════════════════════════════════════════════════════
# 侧边栏底部许可证横幅 — Typeless 风格
# ═══════════════════════════════════════════════════════════════

SIDEBAR_BANNER_STYLE = """
QWidget#sidebarBanner {
    background-color: #0e0e18;
    border-top: 1px solid #1e1e30;
}
QLabel#sbTrialTag {
    color: #f59e0b;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#sbStatus {
    color: #8888a8;
    font-size: 12px;
}
QProgressBar#sbProgress {
    background-color: #2a2a3e;
    border: 1px solid #3a3a50;
    border-radius: 3px;
    height: 6px;
    max-height: 6px;
    min-height: 6px;
}
QProgressBar#sbProgress::chunk {
    background-color: #7c5cfc;
    border-radius: 1px;
}
QPushButton#sbUpgradeBtn {
    background-color: transparent;
    color: #7c5cfc;
    border: 1px solid #7c5cfc;
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#sbUpgradeBtn:hover {
    background-color: #7c5cfc;
    color: #fff;
}
"""


class SidebarLicenseBanner(QWidget):
    """侧边栏底部许可证 — 紧凑竖版 Typeless 风格

    布局（从上到下）：
      - PRO TRIAL 标签（金色小字）
      - 已使用 X 天 / 共 Y 天
      - 细进度条
      - [升级Pro] 按钮（试用/过期时显示）
    """

    activate_clicked = Signal()

    def __init__(self, license_manager, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarBanner")
        self.setStyleSheet(SIDEBAR_BANNER_STYLE)
        self.setFixedHeight(90)
        self._lm = license_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # PRO TRIAL 标签
        self._tag = QLabel("PRO TRIAL")
        self._tag.setObjectName("sbTrialTag")
        layout.addWidget(self._tag)

        # 状态文字：已使用 X 天 / 共 Y 天
        self._status = QLabel()
        self._status.setObjectName("sbStatus")
        layout.addWidget(self._status)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setObjectName("sbProgress")
        self._progress.setRange(0, TRIAL_DAYS)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # 升级按钮
        self._btn = QPushButton("升级Pro")
        self._btn.setObjectName("sbUpgradeBtn")
        self._btn.clicked.connect(self.activate_clicked.emit)
        self._btn.setVisible(False)
        layout.addWidget(self._btn)

        layout.addStretch()

        self.refresh()

    def _set_progress(self, total: int, used: int):
        """设置进度条，确保即使比例极小也有最小可见宽度（~3%）"""
        self._progress.setRange(0, total)
        # 至少显示 total 的 3%，避免 2/364 完全不可见
        min_visible = max(1, int(total * 0.03))
        self._progress.setValue(max(used, min_visible))

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
        self._tag.setText("PRO TRIAL")
        self._tag.setStyleSheet(
            "color: #f59e0b; font-size: 12px; font-weight: 700; letter-spacing: 1px;"
        )
        remaining = max(0, self._lm.get_remaining_days())
        used = TRIAL_DAYS - remaining
        self._status.setText(f"已使用 {used} 天 / 共 {TRIAL_DAYS} 天")
        self._progress.setVisible(True)
        self._set_progress(TRIAL_DAYS, used)
        self._btn.setVisible(False)
        self.setFixedHeight(100)

    def _show_activated(self):
        self._tag.setText("PRO TRIAL")
        self._tag.setStyleSheet(
            "color: #4ade80; font-size: 12px; font-weight: 700; letter-spacing: 1px;"
        )
        usage = self._lm.get_license_usage()
        if usage:
            self._status.setText(f"已使用 {usage['used']} 天 / 共 {usage['total']} 天")
            self._progress.setVisible(True)
            self._set_progress(usage["total"], usage["used"])
        else:
            self._status.setText(self._lm.get_status_text())
            self._progress.setVisible(False)
        self._btn.setVisible(False)
        self.setFixedHeight(90)

    def _show_expired(self):
        self._tag.setText("已过期")
        self._tag.setStyleSheet(
            "color: #f43f5e; font-size: 12px; font-weight: 700; letter-spacing: 1px;"
        )
        self._status.setText(self._lm.get_status_text())
        self._progress.setVisible(False)
        self._btn.setVisible(True)
        self.setFixedHeight(100)

    def _show_offline(self):
        self._tag.setText("离线")
        self._tag.setStyleSheet(
            "color: #f59e0b; font-size: 12px; font-weight: 700; letter-spacing: 1px;"
        )
        self._status.setText("请连接网络验证")
        self._progress.setVisible(False)
        self._btn.setVisible(False)
        self.setFixedHeight(70)

    def _show_locked(self):
        self._tag.setText("未激活")
        self._tag.setStyleSheet(
            "color: #f43f5e; font-size: 12px; font-weight: 700; letter-spacing: 1px;"
        )
        self._status.setText("软件已锁定")
        self._progress.setVisible(False)
        self._btn.setVisible(True)
        self.setFixedHeight(100)
