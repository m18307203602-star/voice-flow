"""嵌入式词典面板 — 主窗口右侧内容区使用"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QCheckBox, QFileDialog,
)
from PySide6.QtCore import Qt
from ..dictionary import DictionaryManager


STYLE = """
QWidget#dictWidget { background-color: #0d0d14; }
QLabel#dictTitle { font-size: 20px; font-weight: bold; color: #e4e4f0; }
QTableWidget {
    background-color: #151520; color: #e4e4f0;
    gridline-color: #2a2a3e; border: 1px solid #2a2a3e;
    border-radius: 8px; font-size: 13px;
}
QTableWidget::item { padding: 6px 10px; }
QTableWidget::item:selected { background-color: #2e2e48; }
QHeaderView::section {
    background-color: #1c1c2e; color: #8888a8;
    border: none; border-bottom: 1px solid #2a2a3e;
    padding: 8px 10px; font-weight: 600; font-size: 12px;
}
QPushButton {
    background-color: #222238; color: #e4e4f0;
    border: 1px solid #2a2a3e; border-radius: 6px;
    padding: 6px 16px; font-size: 12px;
}
QPushButton:hover { background-color: #2e2e48; border-color: #3a3a58; }
QPushButton#addBtn { background-color: #7c5cfc; color: #fff; border: none; }
QPushButton#addBtn:hover { background-color: #9170ff; }
QPushButton#delBtn { background-color: #f43f5e; color: #fff; border: none; }
QPushButton#delBtn:hover { background-color: #fb7185; }
QCheckBox { color: #8888a8; font-size: 12px; }
"""


class DictionaryWidget(QWidget):
    """嵌入式词库管理面板"""

    def __init__(self, dictionary: DictionaryManager, parent=None):
        super().__init__(parent)
        self.setObjectName("dictWidget")
        self.setStyleSheet(STYLE)
        self._dict = dictionary

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("📖 用户词库")
        title.setObjectName("dictTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        self._chk_enabled = QCheckBox("启用词库替换")
        self._chk_enabled.setChecked(self._dict.enabled)
        self._chk_enabled.toggled.connect(self._on_toggle)
        title_row.addWidget(self._chk_enabled)
        layout.addLayout(title_row)

        # 提示
        hint = QLabel("STT 识别完成后自动替换。长词优先匹配，不区分大小写。")
        hint.setStyleSheet("color: #8888a8; font-size: 11px;")
        layout.addWidget(hint)

        # 表格
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["查找文本", "替换为"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._table, 1)

        # 按钮行
        btn_row = QHBoxLayout()

        add_btn = QPushButton("＋ 添加")
        add_btn.setObjectName("addBtn")
        add_btn.clicked.connect(self._add_row)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("🗑 删除选中")
        del_btn.setObjectName("delBtn")
        del_btn.clicked.connect(self._del_row)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()

        import_btn = QPushButton("导入...")
        import_btn.clicked.connect(self._import)
        btn_row.addWidget(import_btn)

        export_btn = QPushButton("导出...")
        export_btn.clicked.connect(self._export)
        btn_row.addWidget(export_btn)

        btn_row.addSpacing(12)

        save_btn = QPushButton("💾 保存")
        save_btn.setStyleSheet("QPushButton { font-weight: 600; }")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        self._load_table()

    def _load_table(self):
        self._table.setRowCount(0)
        for find, replace in self._dict.entries.items():
            self._add_table_row(find, replace)

    def _add_table_row(self, find: str = "", replace: str = ""):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(find))
        self._table.setItem(row, 1, QTableWidgetItem(replace))

    def _add_row(self):
        self._add_table_row()
        row = self._table.rowCount() - 1
        self._table.editItem(self._table.item(row, 0))

    def _del_row(self):
        rows = set(i.row() for i in self._table.selectedIndexes())
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行。")
            return
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)

    def _on_toggle(self, checked: bool):
        self._dict.enabled = checked

    def _save(self):
        """保存到文件"""
        entries = {}
        for row in range(self._table.rowCount()):
            find_item = self._table.item(row, 0)
            replace_item = self._table.item(row, 1)
            find = find_item.text().strip() if find_item else ""
            replace = replace_item.text().strip() if replace_item else ""
            if find:
                entries[find] = replace
        self._dict.set_entries(entries)
        QMessageBox.information(self, "保存完成", f"已保存 {len(entries)} 条规则。")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入词库", "", "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "entries" not in data:
                entries = data
            else:
                entries = data.get("entries", {})
            for find, replace in entries.items():
                self._dict.add(find, replace)
            self._load_table()
            QMessageBox.information(self, "导入完成", f"已导入 {len(entries)} 条规则。")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"文件格式错误：{e}")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出词库", "dictionary.json", "JSON 文件 (*.json)",
        )
        if not path:
            return
        entries = {}
        for row in range(self._table.rowCount()):
            find_item = self._table.item(row, 0)
            replace_item = self._table.item(row, 1)
            find = find_item.text().strip() if find_item else ""
            replace = replace_item.text().strip() if replace_item else ""
            if find:
                entries[find] = replace
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出完成", f"已导出 {len(entries)} 条规则到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
