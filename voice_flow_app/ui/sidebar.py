"""侧边栏导航 — QListWidget 实现"""
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QPen


SIDEBAR_STYLE = """
QListWidget {
    background-color: #12121a;
    border: none;
    border-right: 1px solid #1e1e30;
    outline: none;
}
QListWidget::item {
    color: #8888a8;
    padding: 14px 18px;
    font-size: 14px;
    border: none;
    border-left: 3px solid transparent;
}
QListWidget::item:hover {
    color: #cdd6f4;
    background-color: #1a1a2e;
}
QListWidget::item:selected {
    color: #e4e4f0;
    background-color: #1e1e32;
    border-left: 3px solid #7c5cfc;
}
"""


class SidebarWidget(QListWidget):
    """侧边栏导航 — 选中项紫色左边框，hover 高亮"""

    current_changed = Signal(int)  # 选中的 page index

    NAV_ITEMS = [
        ("🏠  首页", "home"),
        ("📋  历史记录", "history"),
        ("📖  词典", "dictionary"),
        ("📊  统计", "stats"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setSpacing(0)
        self.setStyleSheet(SIDEBAR_STYLE)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        font = QFont("Microsoft YaHei", 13)
        for text, key in self.NAV_ITEMS:
            item = QListWidgetItem(text)
            item.setFont(font)
            item.setData(Qt.UserRole, key)
            self.addItem(item)

        self.setCurrentRow(0)

        # 连接信号
        self.currentRowChanged.connect(self._on_row_changed)

    def _on_row_changed(self, row: int):
        self.current_changed.emit(row)

    def switch_to(self, page_key: str):
        """按 key 切换到指定页面（供外部调用，如首页最近记录点击跳转到历史）"""
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == page_key:
                self.setCurrentRow(i)
                return
