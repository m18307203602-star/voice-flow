"""Activation dialog — enter license key to activate software"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, Signal

from ..license.manager import LicenseState

ACTIVATION_STYLE = """
QDialog {
    background-color: #0d0d14;
}
QLabel {
    color: #e4e4f0;
    font-size: 13px;
}
QLabel#titleLabel {
    color: #e4e4f0;
    font-size: 22px;
    font-weight: bold;
}
QLabel#infoLabel {
    color: #8888a8;
    font-size: 12px;
}
QLabel#errorLabel {
    color: #f43f5e;
    font-size: 12px;
}
QLabel#successLabel {
    color: #4ade80;
    font-size: 12px;
}
QLineEdit {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 14px;
}
QLineEdit:focus {
    border-color: #7c5cfc;
}
QPushButton#activateBtn {
    background-color: #4ade80;
    color: #0d0d14;
    font-weight: bold;
    font-size: 15px;
    padding: 10px 24px;
    border: none;
    border-radius: 6px;
}
QPushButton#activateBtn:hover {
    background-color: #b4e4b1;
}
QPushButton#activateBtn:disabled {
    background-color: #333350;
    color: #8888a8;
}
"""


class ActivationDialog(QDialog):
    """License activation dialog"""

    activation_completed = Signal()
    _allow_close = True

    def __init__(self, license_manager, parent=None, force_activate=False):
        super().__init__(parent)
        self._lm = license_manager
        self._force_activate = force_activate  # True = cannot close without activation

        self.setWindowTitle("Voice Flow — 升级Pro")
        self.setFixedSize(440, 420)
        self.setStyleSheet(ACTIVATION_STYLE)
        flags = Qt.Dialog | Qt.WindowTitleHint
        if not force_activate:
            flags |= Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # Title
        title = QLabel("Voice Flow")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Machine code
        mc = self._lm.get_machine_code()
        mc_edit = QLineEdit(mc)
        mc_edit.setReadOnly(True)
        mc_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        mc_edit.customContextMenuRequested.connect(self._on_context_menu)
        mc_edit.setStyleSheet(
            "QLineEdit { background: #151520; color: #7c5cfc; "
            "border: 1px solid #2a2a3e; border-radius: 4px; "
            "padding: 8px 10px; font-size: 11px; font-family: Consolas, monospace; }"
        )
        layout.addWidget(QLabel("机器码（发送给供应商获取升级码）："))
        layout.addWidget(mc_edit)

        copy_btn = QPushButton("复制机器码")
        copy_btn.setStyleSheet(
            "QPushButton { background: #2a2a3e; color: #e4e4f0; padding: 4px 12px; "
            "border: none; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #333350; }"
        )
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(mc))
        layout.addWidget(copy_btn, 0, Qt.AlignCenter)

        layout.addSpacing(4)

        # License key input
        instr = QLabel("输入升级码（正式 Key 或 3 天试用卡）：")
        instr.setObjectName("infoLabel")
        layout.addWidget(instr)

        self._key_input = QLineEdit()
        self._key_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self._key_input.customContextMenuRequested.connect(self._on_context_menu)
        self._key_input.setPlaceholderText("VF-XXXX-XXXX-XXXX-XXXX  or  VF-TRIAL-XXXX-XXXX")
        self._key_input.setMaxLength(23)
        self._key_input.returnPressed.connect(self._on_activate)
        self._key_input.textChanged.connect(self._on_key_text_changed)
        layout.addWidget(self._key_input)

        # Message
        self._msg_label = QLabel("")
        self._msg_label.setObjectName("errorLabel")
        self._msg_label.setAlignment(Qt.AlignCenter)
        self._msg_label.setWordWrap(True)
        layout.addWidget(self._msg_label)

        # Activate button
        self._activate_btn = QPushButton("升 级  P r o")
        self._activate_btn.setObjectName("activateBtn")
        self._activate_btn.setEnabled(False)
        self._activate_btn.clicked.connect(self._on_activate)
        layout.addWidget(self._activate_btn)

        self._key_input.setFocus()

    def _on_key_text_changed(self, text: str):
        parts = text.strip().split("-")
        # Support both VF-XXXX-XXXX-XXXX-XXXX and VF-TRIAL-XXXX-XXXX
        valid = False
        if len(parts) == 5 and parts[0] == "VF" and all(len(p) == 4 for p in parts[1:]):
            valid = True  # standard key
        elif len(parts) == 4 and parts[0] == "VF" and parts[1] == "TRIAL" and all(len(p) == 4 for p in parts[2:]):
            valid = True  # trial card
        self._activate_btn.setEnabled(valid)

    def _on_activate(self):
        license_key = self._key_input.text().strip()

        self._activate_btn.setEnabled(False)
        self._activate_btn.setText("升级中...")
        self._msg_label.setText("")

        result = self._lm.activate(license_key)

        if result["success"]:
            self._show_success("升级Pro 成功！")
            self._activate_btn.setText("升 级  P r o")
            self._activate_btn.setEnabled(True)
            self.activation_completed.emit()
            QMessageBox.information(self, "升级Pro 成功", result["message"])
            self._allow_close = True
            self.accept()
        else:
            self._show_error(result["message"])
            self._activate_btn.setText("升 级  P r o")
            self._activate_btn.setEnabled(True)

    def _show_error(self, msg: str):
        self._msg_label.setObjectName("errorLabel")
        self._msg_label.setStyleSheet("")
        self._msg_label.setText(msg)

    def _show_success(self, msg: str):
        self._msg_label.setObjectName("successLabel")
        self._msg_label.setStyleSheet("")
        self._msg_label.setText(msg)

    _MENU_MAP = {
        "Undo": "撤销(&U)", "Redo": "重做(&R)",
        "Cut": "剪切(&T)", "Copy": "复制(&C)",
        "Paste": "粘贴(&P)", "Delete": "删除(&D)",
        "Select All": "全选(&A)",
    }

    def _on_context_menu(self, pos):
        """右键菜单 — 替换为标准 Qt 菜单的中文版"""
        widget = self.sender()
        menu = widget.createStandardContextMenu()
        for action in menu.actions():
            for en, zh in self._MENU_MAP.items():
                if en in action.text():
                    action.setText(zh)
                    break
        menu.exec(widget.mapToGlobal(pos))

    def closeEvent(self, event):
        if not self._allow_close:
            event.ignore()
        else:
            event.accept()
