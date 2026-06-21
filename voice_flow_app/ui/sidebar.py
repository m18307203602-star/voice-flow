"""侧边栏导航 — QListWidget + 底部许可证横幅"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


SIDEBAR_STYLE = """
QListWidget#navList {
    background-color: #12121a;
    border: none;
    border-right: 1px solid #1e1e30;
    outline: none;
}
QListWidget#navList::item {
    color: #8888a8;
    padding: 14px 18px;
    font-size: 14px;
    border: none;
    border-left: 3px solid transparent;
}
QListWidget#navList::item:hover {
    color: #cdd6f4;
    background-color: #1a1a2e;
}
QListWidget#navList::item:selected {
    color: #e4e4f0;
    background-color: #1e1e32;
    border-left: 3px solid #7c5cfc;
}
"""


class SidebarWidget(QWidget):
    """侧边栏 — 导航列表 + 底部许可证横幅

    结构：
      ┌──────────────┐
      │  导航列表     │ ← QListWidget (stretch)
      │              │
      │  首页        │
      │  历史记录    │
      │  词典        │
      │  统计        │
      │              │
      ├──────────────┤
      │  PRO TRIAL   │ ← SidebarLicenseBanner (fixed 60-90px)
      └──────────────┘
    """

    current_changed = Signal(int)  # 选中的 page index

    NAV_ITEMS = [
        ("🏠  首页", "stats"),
        ("🚀  控制台", "home"),
        ("📋  历史记录", "history"),
        ("📖  词典", "dictionary"),
    ]

    def __init__(self, license_manager=None, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 导航列表 ──
        self._nav_list = QListWidget()
        self._nav_list.setObjectName("navList")
        self._nav_list.setStyleSheet(SIDEBAR_STYLE)
        self._nav_list.setSpacing(0)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        font = QFont("Microsoft YaHei", 13)
        for text, key in self.NAV_ITEMS:
            item = QListWidgetItem(text)
            item.setFont(font)
            item.setData(Qt.UserRole, key)
            self._nav_list.addItem(item)

        self._nav_list.setCurrentRow(1)  # 默认选中"控制台"（第 2 项）
        self._nav_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._nav_list, 1)  # stretch=1，占满剩余空间

        # ── 底部许可证横幅 ──
        from .trial_banner import SidebarLicenseBanner
        self._banner = SidebarLicenseBanner(license_manager)
        self._banner.activate_clicked.connect(self._on_activate)
        layout.addWidget(self._banner)  # 固定高度，紧贴底部

    def _on_row_changed(self, row: int):
        self.current_changed.emit(row)

    def _on_activate(self):
        """升级按钮点击 — 通过 parent 链传递到主窗口"""
        pass  # 信号由外部连接处理

    def switch_to(self, page_key: str):
        """按 key 切换到指定页面"""
        for i in range(self._nav_list.count()):
            if self._nav_list.item(i).data(Qt.UserRole) == page_key:
                self._nav_list.setCurrentRow(i)
                return

    def refresh_banner(self):
        """刷新底部许可证状态"""
        if hasattr(self, '_banner') and self._banner:
            self._banner.refresh()

    @property
    def banner(self):
        return self._banner
