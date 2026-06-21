"""嵌入式词典面板 — Typeless 风格三标签页：我的词典 + 纠错记录 + 高频建议"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QCheckBox, QFileDialog, QTabWidget,
    QStyle, QStyleOptionButton,
)
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QBrush


STYLE = """
QWidget#dictWidget { background-color: #0d0d14; }
QLabel#dictTitle { font-size: 20px; font-weight: bold; color: #e4e4f0; }
QTabWidget::pane {
    background-color: #0d0d14;
    border: 1px solid #2a2a3e;
    border-top: none;
    border-radius: 0 0 8px 8px;
}
QTabBar::tab {
    background-color: #1c1c2e;
    color: #8888a8;
    border: 1px solid #2a2a3e;
    border-bottom: none;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    margin-right: 2px;
    border-radius: 6px 6px 0 0;
}
QTabBar::tab:selected {
    background-color: #0d0d14;
    color: #e4e4f0;
    border-bottom: 2px solid #7c5cfc;
}
QTabBar::tab:hover:!selected {
    color: #cdd6f4;
    background-color: #252540;
}
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
QPushButton#promoteBtn { background-color: #4ade80; color: #0d0d14; border: none; font-weight: 600; }
QPushButton#promoteBtn:hover { background-color: #6ee7a0; }
QPushButton#adoptBtn { background-color: #4ade80; color: #0d0d14; border: none; font-weight: 600; }
QPushButton#adoptBtn:hover { background-color: #6ee7a0; }
QLabel#tabHint { color: #8888a8; font-size: 11px; }
QLabel#emptyLabel { color: #555570; font-size: 14px; }
QLabel#suggestionCount { color: #cdd6f4; font-size: 13px; }
"""


class _DarkCheckBox(QCheckBox):
    """深色主题复选框 — 自绘对号，放大指示器方便点击"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        from PySide6.QtGui import QFont
        font = QFont("Microsoft YaHei", 13)
        self.setFont(font)
        self.setMinimumHeight(28)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        opt = QStyleOptionButton()
        self.initStyleOption(opt)

        # ── 方框（手动放大到 22×22） ──
        box_size = 22
        box_x = 3
        box_y = (self.height() - box_size) // 2
        box = QRect(box_x, box_y, box_size, box_size)

        is_checked = self.isChecked()
        is_hover = opt.state & QStyle.State_MouseOver

        if is_checked:
            painter.setBrush(QBrush(QColor("#7c5cfc")))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(box, 5, 5)
        else:
            painter.setBrush(QBrush(QColor("#1c1c2e")))
            border_color = QColor("#7c5cfc") if is_hover else QColor("#3a3a58")
            painter.setPen(QPen(border_color, 2))
            painter.drawRoundedRect(box, 5, 5)

        # ── 对号 ✓ ──
        if is_checked:
            pen = QPen(QColor("#ffffff"), 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            cx, cy = box.center().x(), box.center().y()
            w, h = box.width(), box.height()
            x1 = int(cx - w * 0.30)
            y1 = int(cy)
            x2 = int(cx - w * 0.05)
            y2 = int(cy + h * 0.28)
            x3 = int(cx + w * 0.38)
            y3 = int(cy - h * 0.24)
            painter.drawLine(x1, y1, x2, y2)
            painter.drawLine(x2, y2, x3, y3)

        # ── 文字 ──
        painter.setPen(QColor("#cdd6f4"))
        text_x = box_x + box_size + 10
        text_rect = QRect(text_x, 0, self.width() - text_x, self.height())
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())


class DictionaryWidget(QWidget):
    """嵌入式词库管理面板 — Typeless 三合一"""

    # 当词库有变更时发出，供外部刷新
    dictionary_changed = Signal()

    def __init__(self, dictionary, parent=None):
        super().__init__(parent)
        self.setObjectName("dictWidget")
        self.setStyleSheet(STYLE)
        self._dict = dictionary

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("📖 个性化词典")
        title.setObjectName("dictTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        self._chk_enabled = _DarkCheckBox("启用词库替换")
        self._chk_enabled.setChecked(self._dict.enabled)
        self._chk_enabled.toggled.connect(self._on_toggle)
        title_row.addWidget(self._chk_enabled)
        layout.addLayout(title_row)

        # 提示
        hint = QLabel("STT 识别完成后自动替换。长词优先匹配，不区分大小写。")
        hint.setObjectName("tabHint")
        layout.addWidget(hint)

        # ── 标签页 ──
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._tab_dict = self._create_dict_tab()
        self._tab_corrections = self._create_corrections_tab()
        self._tab_suggestions = self._create_suggestions_tab()

        self._tabs.addTab(self._tab_dict, "📖 我的词典")
        self._tabs.addTab(self._tab_corrections, "🔧 纠错记录")
        self._tabs.addTab(self._tab_suggestions, "💡 高频建议")

        layout.addWidget(self._tabs, 1)

    # ═══════════════════════════════════════════════
    # Tab 1: 我的词典
    # ═══════════════════════════════════════════════

    def _create_dict_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._dict_table = QTableWidget(0, 2)
        self._dict_table.setHorizontalHeaderLabels(["查找文本", "替换为"])
        self._dict_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._dict_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._dict_table.verticalHeader().setVisible(False)
        self._dict_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._dict_table, 1)

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

        import_btn = QPushButton("📥 导入...")
        import_btn.clicked.connect(self._import)
        btn_row.addWidget(import_btn)

        export_btn = QPushButton("📤 导出...")
        export_btn.clicked.connect(self._export)
        btn_row.addWidget(export_btn)

        btn_row.addSpacing(12)

        save_btn = QPushButton("💾 保存")
        save_btn.setStyleSheet("QPushButton { font-weight: 600; }")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        self._load_dict_table()
        return tab

    def _load_dict_table(self):
        self._dict_table.setRowCount(0)
        for find, replace in self._dict.entries.items():
            self._add_dict_row(find, replace)

    def _add_dict_row(self, find: str = "", replace: str = ""):
        row = self._dict_table.rowCount()
        self._dict_table.insertRow(row)
        self._dict_table.setItem(row, 0, QTableWidgetItem(find))
        self._dict_table.setItem(row, 1, QTableWidgetItem(replace))

    def _add_row(self):
        self._add_dict_row()
        row = self._dict_table.rowCount() - 1
        self._dict_table.editItem(self._dict_table.item(row, 0))

    def _del_row(self):
        rows = set(i.row() for i in self._dict_table.selectedIndexes())
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行。")
            return
        for row in sorted(rows, reverse=True):
            self._dict_table.removeRow(row)

    def _on_toggle(self, checked: bool):
        self._dict.enabled = checked

    def _save(self):
        entries = {}
        for row in range(self._dict_table.rowCount()):
            find_item = self._dict_table.item(row, 0)
            replace_item = self._dict_table.item(row, 1)
            find = find_item.text().strip() if find_item else ""
            replace = replace_item.text().strip() if replace_item else ""
            if find:
                entries[find] = replace
        self._dict.set_entries(entries)
        self.dictionary_changed.emit()
        QMessageBox.information(self, "保存完成", f"已保存 {len(entries)} 条规则。")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入词库", "", "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "entries" not in data:
                entries = data
            else:
                entries = data.get("entries", {})
            for find, replace in entries.items():
                self._dict.add(find, replace)
            self._load_dict_table()
            self.dictionary_changed.emit()
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
        for row in range(self._dict_table.rowCount()):
            find_item = self._dict_table.item(row, 0)
            replace_item = self._dict_table.item(row, 1)
            find = find_item.text().strip() if find_item else ""
            replace = replace_item.text().strip() if replace_item else ""
            if find:
                entries[find] = replace
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出完成", f"已导出 {len(entries)} 条规则到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ═══════════════════════════════════════════════
    # Tab 2: 纠错记录
    # ═══════════════════════════════════════════════

    def _create_corrections_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        desc = QLabel("你手动修正过的词条。点击「升级」将其加入正式词典。")
        desc.setObjectName("tabHint")
        layout.addWidget(desc)

        self._corr_table = QTableWidget(0, 4)
        self._corr_table.setHorizontalHeaderLabels(["日期", "原文", "修正为", "操作"])
        self._corr_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._corr_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._corr_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._corr_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self._corr_table.setColumnWidth(0, 130)
        self._corr_table.setColumnWidth(3, 140)
        self._corr_table.verticalHeader().setVisible(False)
        self._corr_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._corr_table, 1)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("清空纠错记录")
        clear_btn.clicked.connect(self._clear_corrections)
        btn_row.addWidget(clear_btn)

        promote_all_btn = QPushButton("全部升级到词典")
        promote_all_btn.setObjectName("promoteBtn")
        promote_all_btn.clicked.connect(self._promote_all_corrections)
        btn_row.addWidget(promote_all_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._load_corrections_table()
        return tab

    def _load_corrections_table(self):
        self._corr_table.setRowCount(0)
        corrs = self._dict.get_corrections(limit=100)
        for i, c in enumerate(corrs):
            self._corr_table.insertRow(i)
            self._corr_table.setItem(i, 0, QTableWidgetItem(c["date"]))
            self._corr_table.setItem(i, 1, QTableWidgetItem(c["from"]))
            self._corr_table.setItem(i, 2, QTableWidgetItem(c["to"]))

            # 操作按钮容器
            btn_w = QWidget()
            btn_layout = QHBoxLayout(btn_w)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            promote_btn = QPushButton("升级")
            promote_btn.setObjectName("promoteBtn")
            promote_btn.setFixedWidth(50)
            promote_btn.clicked.connect(lambda checked, idx=i: self._promote_correction(idx))
            btn_layout.addWidget(promote_btn)

            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(50)
            del_btn.clicked.connect(lambda checked, idx=i: self._remove_correction(idx))
            btn_layout.addWidget(del_btn)

            self._corr_table.setCellWidget(i, 3, btn_w)

    def _promote_correction(self, index: int):
        self._dict.promote_correction(index)
        self._load_corrections_table()
        self._load_dict_table()
        self.dictionary_changed.emit()
        self._tabs.setCurrentIndex(0)  # 切回词典页

    def _remove_correction(self, index: int):
        self._dict.remove_correction(index)
        self._load_corrections_table()

    def _clear_corrections(self):
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有纠错记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._dict.clear_corrections()
            self._load_corrections_table()

    def _promote_all_corrections(self):
        corrs = self._dict.get_corrections(limit=200)
        if not corrs:
            QMessageBox.information(self, "提示", "没有纠错记录可升级。")
            return
        count = 0
        for c in reversed(corrs):
            self._dict.add(c["from"], c["to"])
            count += 1
        self._dict.clear_corrections()
        self._load_corrections_table()
        self._load_dict_table()
        self.dictionary_changed.emit()
        QMessageBox.information(self, "完成", f"已将 {count} 条纠错记录升级到词典。")
        self._tabs.setCurrentIndex(0)

    # ═══════════════════════════════════════════════
    # Tab 3: 高频建议
    # ═══════════════════════════════════════════════

    def _create_suggestions_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        desc = QLabel("基于历史记录自动分析的高频专有名词，建议加入词典以提高识别准确率。")
        desc.setObjectName("tabHint")
        layout.addWidget(desc)

        info_row = QHBoxLayout()
        self._sugg_count_lbl = QLabel("")
        self._sugg_count_lbl.setObjectName("suggestionCount")
        info_row.addWidget(self._sugg_count_lbl)
        info_row.addStretch()

        refresh_btn = QPushButton("🔄 重新分析")
        refresh_btn.clicked.connect(self._refresh_suggestions)
        info_row.addWidget(refresh_btn)
        layout.addLayout(info_row)

        self._sugg_table = QTableWidget(0, 4)
        self._sugg_table.setHorizontalHeaderLabels(["高频词", "出现次数", "预览", "操作"])
        self._sugg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._sugg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._sugg_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._sugg_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self._sugg_table.setColumnWidth(1, 80)
        self._sugg_table.setColumnWidth(3, 80)
        self._sugg_table.verticalHeader().setVisible(False)
        self._sugg_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._sugg_table, 1)

        self._sugg_empty = QLabel("暂无高频词建议\n使用一段时间后，系统会自动分析常用词汇")
        self._sugg_empty.setObjectName("emptyLabel")
        self._sugg_empty.setAlignment(Qt.AlignCenter)
        self._sugg_empty.setVisible(False)
        layout.addWidget(self._sugg_empty, 1)

        return tab

    def _refresh_suggestions(self):
        """调用 DictionaryManager 生成高频建议"""
        # 需要通过外部注入 history_db，这里先留空
        # 由 main_window 在初始化时设置
        if hasattr(self, '_history_db') and self._history_db:
            suggestions = self._dict.generate_suggestions(self._history_db)
            self._display_suggestions(suggestions)
        else:
            self._sugg_count_lbl.setText("⚠️ 未连接数据库")
            self._sugg_table.setRowCount(0)
            self._sugg_empty.setVisible(True)

    def _display_suggestions(self, suggestions: list[dict]):
        self._sugg_table.setRowCount(0)
        if not suggestions:
            self._sugg_count_lbl.setText("未发现高频专有名词")
            self._sugg_table.setVisible(False)
            self._sugg_empty.setVisible(True)
            return

        self._sugg_count_lbl.setText(f"发现 {len(suggestions)} 个高频专有名词")
        self._sugg_table.setVisible(True)
        self._sugg_empty.setVisible(False)

        for i, s in enumerate(suggestions):
            self._sugg_table.insertRow(i)
            self._sugg_table.setItem(i, 0, QTableWidgetItem(s["word"]))
            self._sugg_table.setItem(i, 1, QTableWidgetItem(str(s["count"])))
            self._sugg_table.setItem(i, 2, QTableWidgetItem(f"出现 {s['count']} 次"))

            adopt_btn = QPushButton("采用")
            adopt_btn.setObjectName("adoptBtn")
            adopt_btn.setFixedWidth(60)
            adopt_btn.clicked.connect(lambda checked, idx=i: self._adopt_suggestion(idx))
            self._sugg_table.setCellWidget(i, 3, adopt_btn)

    def _adopt_suggestion(self, index: int):
        """将建议词加入词典（自动生成替换文本）"""
        word = self._sugg_table.item(index, 0).text()
        self._dict.add(word, word)  # 查找=替换，即保留原文不做替换，仅增强识别
        self._load_dict_table()
        self.dictionary_changed.emit()
        # 从建议列表中移除
        self._sugg_table.removeRow(index)
        if self._sugg_table.rowCount() == 0:
            self._sugg_table.setVisible(False)
            self._sugg_empty.setVisible(True)

    def set_history_db(self, history_db):
        """注入 HistoryDB 引用（用于生成高频建议）"""
        self._history_db = history_db

    # ═══════════════════════════════════════════════
    # 刷新 & 切换
    # ═══════════════════════════════════════════════

    def refresh_all(self):
        """刷新所有标签页"""
        self._load_dict_table()
        self._load_corrections_table()

    def _on_tab_changed(self, index: int):
        """切换到高频建议标签时自动刷新"""
        if index == 2:  # 高频建议
            self._refresh_suggestions()
        elif index == 1:  # 纠错记录
            self._load_corrections_table()

    def showEvent(self, event):
        """页面显示时刷新"""
        super().showEvent(event)
        self._load_dict_table()
        self._load_corrections_table()
