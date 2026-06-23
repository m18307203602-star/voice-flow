"""词库管理对话框 — 添加/删除/编辑替换规则"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QCheckBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from ..dictionary import DictionaryManager


STYLE = """
QDialog { background-color: #0d0d14; }
QLabel { color: #e4e4f0; font-size: 13px; }
QLabel#title { font-size: 18px; font-weight: bold; color: #e4e4f0; }
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
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; }
"""


class DictionaryDialog(QDialog):
    """词库管理对话框"""

    def __init__(self, dictionary: DictionaryManager, parent=None):
        super().__init__(parent)
        self._dict = dictionary
        self.setWindowTitle("词库管理")
        self.setMinimumSize(560, 480)
        self.resize(620, 520)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("📖 用户词库")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()

        # 启用开关
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

        self._btn_add = QPushButton("＋ 添加")
        self._btn_add.setObjectName("addBtn")
        self._btn_add.clicked.connect(self._add_row)
        btn_row.addWidget(self._btn_add)

        self._btn_del = QPushButton("🗑 删除选中")
        self._btn_del.setObjectName("delBtn")
        self._btn_del.clicked.connect(self._del_row)
        btn_row.addWidget(self._btn_del)

        btn_row.addStretch()

        import_btn = QPushButton("导入...")
        import_btn.clicked.connect(self._import)
        btn_row.addWidget(import_btn)

        export_btn = QPushButton("导出...")
        export_btn.clicked.connect(self._export)
        btn_row.addWidget(export_btn)

        btn_row.addSpacing(12)

        save_btn = QPushButton("保存并关闭")
        save_btn.setStyleSheet("QPushButton { font-weight: 600; }")
        save_btn.clicked.connect(self._save_and_close)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        # 加载数据
        self._load_table()

    # ── 数据加载 ──

    def _load_table(self):
        """从 DictionaryManager 加载到表格"""
        self._table.setRowCount(0)
        for find, replace in self._dict.entries.items():
            self._add_table_row(find, replace)

    def _add_table_row(self, find: str = "", replace: str = ""):
        """在表格末尾添加一行"""
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(find))
        self._table.setItem(row, 1, QTableWidgetItem(replace))

    # ── 操作 ──

    def _add_row(self):
        self._add_table_row()
        # 聚焦新增行第一列
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

    def _save_and_close(self):
        """收集表格数据 → 保存 → 关闭"""
        entries = {}
        for row in range(self._table.rowCount()):
            find_item = self._table.item(row, 0)
            replace_item = self._table.item(row, 1)
            find = find_item.text().strip() if find_item else ""
            replace = replace_item.text().strip() if replace_item else ""
            if find:
                entries[find] = replace
        self._dict.set_entries(entries)
        self.accept()

    def _import(self):
        """从 JSON 文件导入"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入词库", "", "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # 直接是 {find: replace} 格式
                entries = data
            elif isinstance(data, dict) and "entries" in data:
                entries = data["entries"]
            else:
                raise ValueError("不支持的格式")
            for find, replace in entries.items():
                self._dict.add(find, replace)
            self._load_table()
            QMessageBox.information(self, "导入完成", f"已导入 {len(entries)} 条规则。")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"文件格式错误：{e}")

    def _export(self):
        """导出为 JSON 文件"""
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
