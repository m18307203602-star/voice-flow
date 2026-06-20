"""登录/注册对话框 — 手机号 + 密码，本地 SQLite 后端（后续可替换云端）"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QStackedWidget, QWidget,
    QCheckBox, QMessageBox,
)
from PySide6.QtCore import Qt, Signal


LOGIN_STYLE = """
QDialog {
    background-color: #0d0d14;
}
QLabel {
    color: #e4e4f0;
    font-size: 13px;
}
QLineEdit {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 14px;
    min-width: 260px;
}
QLineEdit:focus {
    border-color: #7c5cfc;
}
QPushButton#loginBtn {
    background-color: #7c5cfc;
    color: #0d0d14;
    font-weight: bold;
    font-size: 15px;
    padding: 10px 24px;
    border: none;
    border-radius: 6px;
}
QPushButton#loginBtn:hover {
    background-color: #9170ff;
}
QPushButton#switchBtn {
    background: transparent;
    color: #7c5cfc;
    border: none;
    font-size: 13px;
    text-decoration: underline;
}
QPushButton#switchBtn:hover {
    color: #9170ff;
}
QLabel#errorLabel {
    color: #f43f5e;
    font-size: 12px;
}
QLabel#successLabel {
    color: #4ade80;
    font-size: 12px;
}
QLabel#titleLabel {
    color: #e4e4f0;
    font-size: 22px;
    font-weight: bold;
}
QLabel#hintLabel {
    color: #8888a8;
    font-size: 11px;
}
"""


class LoginDialog(QDialog):
    """登录对话框：手机号 + 密码"""

    login_success = Signal(str)  # user_id

    def __init__(self, auth_backend, config=None, parent=None):
        super().__init__(parent)
        self._auth = auth_backend
        self._config = config

        self.setWindowTitle("Voice Flow — 登录")
        self.setFixedSize(420, 460)
        self.setStyleSheet(LOGIN_STYLE)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # 标题
        title = QLabel("Voice Flow")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("语音转文字 · 一键润色")
        subtitle.setObjectName("hintLabel")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # ── 手机号 ──
        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText("手机号（11 位）")
        self._phone_input.setMaxLength(11)
        # 自动填入上次保存的手机号
        if self._config and self._config.auth_phone:
            self._phone_input.setText(self._config.auth_phone)
        layout.addWidget(self._phone_input)

        # ── 密码 ──
        self._pwd_input = QLineEdit()
        self._pwd_input.setPlaceholderText("密码（至少 6 位）")
        self._pwd_input.setEchoMode(QLineEdit.Password)
        self._pwd_input.setMaxLength(32)
        self._pwd_input.returnPressed.connect(self._on_login)  # 回车登录
        layout.addWidget(self._pwd_input)

        # ── 记住密码 ──
        _svg = os.path.join(os.path.dirname(__file__), "checkmark.svg").replace("\\", "/")
        self._chk_remember = QCheckBox("记住密码（下次自动登录）")
        self._chk_remember.setStyleSheet(
            "QCheckBox { color: #8888a8; font-size: 12px; spacing: 6px; }"
            "QCheckBox:checked { color: #e4e4f0; }"
            "QCheckBox::indicator {"
            "  width: 16px; height: 16px;"
            "  border: 2px solid #333350; border-radius: 3px;"
            "  background: #1c1c2e;"
            "}"
            "QCheckBox::indicator:checked {"
            "  border-color: #4ade80;"
            "  background: #1c1c2e;"
            f"  image: url({_svg});"
            "}"
        )
        layout.addWidget(self._chk_remember)

        # ── 消息提示 ──
        self._msg_label = QLabel("")
        self._msg_label.setObjectName("errorLabel")
        self._msg_label.setAlignment(Qt.AlignCenter)
        self._msg_label.setWordWrap(True)
        layout.addWidget(self._msg_label)

        # ── 登录按钮 ──
        login_btn = QPushButton("登 录")
        login_btn.setObjectName("loginBtn")
        login_btn.clicked.connect(self._on_login)
        layout.addWidget(login_btn)

        # ── 切换注册 ──
        switch_row = QHBoxLayout()
        switch_row.addStretch()
        self._switch_label = QLabel("没有账号？")
        self._switch_label.setStyleSheet("color: #8888a8; font-size: 13px;")
        switch_row.addWidget(self._switch_label)

        self._switch_btn = QPushButton("注册")
        self._switch_btn.setObjectName("switchBtn")
        self._switch_btn.clicked.connect(self._toggle_mode)
        switch_row.addWidget(self._switch_btn)
        switch_row.addStretch()
        layout.addLayout(switch_row)

        # 状态
        self._is_login_mode = True

    def _toggle_mode(self):
        """切换登录/注册模式"""
        self._is_login_mode = not self._is_login_mode
        if self._is_login_mode:
            self.setWindowTitle("Voice Flow — 登录")
            self._switch_label.setText("没有账号？")
            self._switch_btn.setText("注册")
            self.findChild(QPushButton, "loginBtn").setText("登 录")
        else:
            self.setWindowTitle("Voice Flow — 注册")
            self._switch_label.setText("已有账号？")
            self._switch_btn.setText("登录")
            self.findChild(QPushButton, "loginBtn").setText("注 册")
        self._msg_label.setText("")

    def _find_login_btn(self):
        """查找登录/注册按钮"""
        for child in self.children():
            if isinstance(child, QPushButton) and child.objectName() == "loginBtn":
                return child
        return None

    def _on_login(self):
        """执行登录或注册"""
        phone = self._phone_input.text().strip()
        password = self._pwd_input.text().strip()

        if not phone or not password:
            self._show_error("请输入手机号和密码")
            return

        if self._is_login_mode:
            result = self._auth.login(phone, password)
        else:
            result = self._auth.register(phone, password)

        if result.success:
            self._show_success(result.message)
            # 记住密码 → 保存凭据到 config
            if self._chk_remember.isChecked() and self._config:
                token = self._auth.create_session(phone)
                self._config.auth_phone = phone
                self._config.auth_token = token
                self._config.auth_auto_login = True
                self._config.save()
            self.login_success.emit(result.user_id)
            self.accept()
        else:
            self._show_error(result.message)

    def _show_error(self, msg: str):
        self._msg_label.setObjectName("errorLabel")
        self._msg_label.setStyleSheet("")  # 刷新样式
        self._msg_label.setText(msg)

    def _show_success(self, msg: str):
        self._msg_label.setObjectName("successLabel")
        self._msg_label.setStyleSheet("")
        self._msg_label.setText(msg)
