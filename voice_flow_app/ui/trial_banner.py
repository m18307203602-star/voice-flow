"""Status banner — displays license status (locked / trial / activated / expired)"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal

BANNER_STYLE = """
QWidget#trialBanner {
    background-color: #2a273f;
    border-bottom: 1px solid #f59e0b;
}
QWidget#activeBanner {
    background-color: #1a2a1f;
    border-bottom: 1px solid #4ade80;
}
QWidget#expiredBanner {
    background-color: #2a1f1f;
    border-bottom: 1px solid #f43f5e;
}
QWidget#lockedBanner {
    background-color: #1f1f2a;
    border-bottom: 1px solid #f43f5e;
}
QLabel {
    font-size: 12px;
}
QLabel#trialLabel { color: #f59e0b; }
QLabel#activeLabel { color: #4ade80; }
QLabel#expiredLabel { color: #f43f5e; }
QLabel#lockedLabel { color: #f43f5e; }
QPushButton#activateBtn {
    background-color: #7c5cfc;
    color: #0d0d14;
    padding: 4px 16px;
    border: none;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
}
QPushButton#activateBtn:hover {
    background-color: #9170ff;
}
"""


class LicenseBanner(QWidget):
    """Banner showing license status at top of MainWindow"""

    activate_clicked = Signal()

    def __init__(self, license_manager, parent=None):
        super().__init__(parent)
        self._lm = license_manager

        self.setObjectName("trialBanner")
        self.setStyleSheet(BANNER_STYLE)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self._label = QLabel()
        layout.addWidget(self._label)

        layout.addStretch()

        self._btn = QPushButton("升级Pro")
        self._btn.setObjectName("activateBtn")
        self._btn.clicked.connect(self.activate_clicked.emit)
        layout.addWidget(self._btn)

        self.refresh()

    def refresh(self):
        state = self._lm.get_state()

        if state.value == "activated":
            self._show_activated()
        elif state.value == "permanent":
            self._show_activated()
        elif state.value == "locked":
            self._show_locked()
        elif state.value in ("expired", "trial_expired", "activated_offline"):
            self._show_expired()
        else:
            self._show_trial()

    def _show_locked(self):
        self.setObjectName("lockedBanner")
        self._label.setObjectName("lockedLabel")
        self._label.setText("[未升级] 软件已锁定 — 需升级Pro")
        self._btn.setVisible(True)
        self._restyle()

    def _show_trial(self):
        self.setObjectName("trialBanner")
        self._label.setObjectName("trialLabel")
        self._label.setText(f"[试用] {self._lm.get_status_text()}")
        self._btn.setVisible(True)
        self._restyle()

    def _show_activated(self):
        self.setObjectName("activeBanner")
        self._label.setObjectName("activeLabel")
        self._label.setText(f"[Pro] {self._lm.get_status_text()}")
        self._btn.setVisible(False)
        self._restyle()

    def _show_expired(self):
        self.setObjectName("expiredBanner")
        self._label.setObjectName("expiredLabel")
        self._label.setText(f"[已过期] {self._lm.get_status_text()}")
        self._btn.setVisible(True)
        self._restyle()

    def _restyle(self):
        self.setStyleSheet(BANNER_STYLE)


# Backward-compatible alias
TrialBanner = LicenseBanner
