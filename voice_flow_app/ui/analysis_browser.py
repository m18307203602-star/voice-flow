"""历史分析浏览器 — 独立弹窗：日期列表 + 搜索 + 日历跳转 + 详情"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QSplitter, QLineEdit, QDateEdit, QCalendarWidget,
    QMessageBox, QWidget,
)
from PySide6.QtCore import Qt, QDate, Signal
from datetime import date, datetime


ANALYSIS_BROWSER_STYLE = """
QDialog {
    background-color: #0d0d14;
}
QLabel {
    color: #e4e4f0;
    font-size: 13px;
}
QPushButton {
    background-color: #2a2a3e;
    color: #e4e4f0;
    border: 1px solid #333350;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #333350;
}
QPushButton:pressed {
    background-color: #8888a8;
}
QPushButton#deleteBtn {
    background-color: #6c3a3a;
    color: #f43f5e;
    border: 1px solid #8b4a4a;
}
QPushButton#deleteBtn:hover {
    background-color: #8b4a4a;
}
QLineEdit, QTextEdit, QListWidget {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    padding: 6px;
    font-size: 13px;
}
QListWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid #2a2a3e;
}
QListWidget::item:selected {
    background-color: #2a2a3e;
}
QListWidget::item:hover {
    background-color: #333350;
}
QDateEdit {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}
QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #2a2a3e;
}
QDateEdit::down-arrow {
    width: 10px;
    height: 10px;
}
QCalendarWidget {
    background-color: #0d0d14;
    color: #e4e4f0;
}
QCalendarWidget QToolButton {
    color: #e4e4f0;
    background-color: #2a2a3e;
    border-radius: 4px;
    padding: 4px 8px;
}
QCalendarWidget QToolButton:hover {
    background-color: #333350;
}
QCalendarWidget QMenu {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
}
QCalendarWidget QSpinBox {
    background-color: #1c1c2e;
    color: #e4e4f0;
    border: 1px solid #2a2a3e;
    padding: 2px;
}
QCalendarWidget QTableView {
    background-color: #1c1c2e;
    alternate-background-color: #333350;
    selection-background-color: #7c5cfc;
    selection-color: #0d0d14;
}
QCalendarWidget QAbstractItemView:enabled {
    color: #e4e4f0;
}
QSplitter::handle {
    background-color: #2a2a3e;
    width: 2px;
}
"""


class AnalysisBrowser(QDialog):
    """历史分析浏览对话框"""

    _regenerate_done = Signal(str)  # LLM 生成完成（后台线程 → 主线程）

    def __init__(self, history_db, config=None, parent=None):
        super().__init__(parent)
        self._db = history_db
        self._config = config
        self._search_keyword = ""
        self._date_from = ""
        self._date_to = ""
        self._current_date = ""
        self._cached_rows = {}  # date_str → row dict

        self.setWindowTitle("历史分析")
        self.setMinimumSize(750, 500)
        self.resize(850, 600)
        self.setStyleSheet(ANALYSIS_BROWSER_STYLE)
        self._setup_ui()
        self._regenerate_done.connect(self._on_regenerate_done)
        self._refresh_date_list()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # ── 顶部标题 ──
        title = QLabel("📊 历史分析")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e4e4f0;")
        root.addWidget(title)

        # ── 主内容：左列表 + 右详情 ──
        splitter = QSplitter(Qt.Horizontal)

        # --- 左侧栏 ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索分析...")
        self._search_input.textChanged.connect(self._on_search)
        left_layout.addWidget(self._search_input)

        self._btn_calendar = QPushButton("📅 日历跳转")
        self._btn_calendar.clicked.connect(self._on_calendar)
        left_layout.addWidget(self._btn_calendar)

        self._date_list = QListWidget()
        self._date_list.setMinimumWidth(170)
        self._date_list.currentRowChanged.connect(self._on_date_selected)
        left_layout.addWidget(self._date_list, 1)

        splitter.addWidget(left)

        # --- 右侧详情 ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._detail_title = QLabel("选择日期查看分析")
        self._detail_title.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #e4e4f0;")
        right_layout.addWidget(self._detail_title)

        self._lbl_stats = QLabel("")
        self._lbl_stats.setStyleSheet(
            "color: #8888a8; font-size: 12px; padding: 2px 0;")
        right_layout.addWidget(self._lbl_stats)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(
            "QTextEdit { background: #1c1c2e; color: #e4e4f0; "
            "border: 1px solid #2a2a3e; border-radius: 6px; "
            "padding: 8px; font-size: 13px; }"
        )
        right_layout.addWidget(self._detail_text, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # ── 底部：日期范围 + 操作 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        bottom.addWidget(QLabel("从:"))
        self._edit_from = QDateEdit()
        self._edit_from.setCalendarPopup(True)
        self._edit_from.setDate(QDate.currentDate().addMonths(-1))
        self._edit_from.setDisplayFormat("yyyy-MM-dd")
        bottom.addWidget(self._edit_from)

        bottom.addWidget(QLabel("到:"))
        self._edit_to = QDateEdit()
        self._edit_to.setCalendarPopup(True)
        self._edit_to.setDate(QDate.currentDate())
        self._edit_to.setDisplayFormat("yyyy-MM-dd")
        bottom.addWidget(self._edit_to)

        btn_apply = QPushButton("应用")
        btn_apply.clicked.connect(self._on_range_apply)
        bottom.addWidget(btn_apply)

        btn_reset = QPushButton("重置")
        btn_reset.clicked.connect(self._on_reset)
        bottom.addWidget(btn_reset)

        bottom.addStretch()

        self._btn_delete = QPushButton("🗑 删除此分析")
        self._btn_delete.setObjectName("deleteBtn")
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete.setEnabled(False)  # 初始无选中，禁用
        bottom.addWidget(self._btn_delete)

        self._btn_regenerate = QPushButton("🔄 重新生成")
        self._btn_regenerate.setToolTip("用该日录音数据重新生成分析")
        self._btn_regenerate.clicked.connect(self._on_regenerate)
        bottom.addWidget(self._btn_regenerate)

        root.addLayout(bottom)

    # ── 核心逻辑 ──

    def _refresh_date_list(self):
        """按当前过滤条件重新填充日期列表（合并录音日期 + 分析日期）"""
        self._date_list.blockSignals(True)
        self._date_list.clear()
        self._cached_rows.clear()

        # 1. 获取数据
        if self._search_keyword:
            # 搜索仅限已有分析的日期（search_analyses 查的是 daily_analyses）
            rows = self._db.search_analyses(self._search_keyword)
        else:
            # ★ 合并录音日期 + 分析日期，即使无预生成分析也能显示
            recording_dates = set(self._db.get_all_recording_dates())
            analysis_dates = set(self._db.get_all_analysis_dates())
            all_dates = sorted(recording_dates | analysis_dates, reverse=True)

            rows = []
            for d in all_dates:
                analysis = self._db.get_daily_analysis(d)
                if analysis:
                    rows.append(analysis)
                else:
                    # 有录音但无分析：构造最小行数据
                    rows.append({"date": d, "result": "", "tags": [],
                                 "decision_count": 0, "todo_count": 0,
                                 "main_thread": "", "framework": "",
                                 "has_analysis": False})

        # 2. 日期范围过滤
        if self._date_from:
            rows = [r for r in rows if r["date"] >= self._date_from]
        if self._date_to:
            rows = [r for r in rows if r["date"] <= self._date_to]

        # 3. 填充列表
        if not rows:
            item = QListWidgetItem("(无匹配结果)")
            item.setFlags(Qt.NoItemFlags)
            self._date_list.addItem(item)
        else:
            for r in rows:
                label = r["date"]
                if r.get("has_analysis") is False:
                    label += "  (未分析)"
                elif r.get("main_thread"):
                    label += f"  —  {r['main_thread']}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, r)
                self._date_list.addItem(item)
                self._cached_rows[r["date"]] = r

        self._date_list.blockSignals(False)
        self._date_list.scrollToTop()

    def _on_date_selected(self, row: int):
        if row < 0:
            return
        item = self._date_list.item(row)
        data = item.data(Qt.UserRole)
        if not data:
            return

        if data.get("has_analysis") is False:
            # 有录音但无分析 → 显示提示，允许直接重新生成
            self._current_date = data["date"]
            entry_count = len(self._db.get_by_date(self._current_date))
            self._detail_title.setText(f"📊 {self._current_date}  — 未分析")
            self._lbl_stats.setText(
                f"<span style='color:#8888a8;'>该日期有 {entry_count} 条录音，尚未生成分析。</span>"
            )
            self._detail_text.setPlainText(
                f"{self._current_date} 有 {entry_count} 条语音记录，"
                f"但尚未生成每日分析。\n\n点击「🔄 重新生成」按钮即可创建该日分析报告。"
            )
            self._btn_delete.setEnabled(False)
        else:
            self._display_analysis(data)
            self._btn_delete.setEnabled(True)

    def _display_analysis(self, row: dict):
        """渲染分析详情"""
        date_str = row["date"]
        tags = row.get("tags", [])
        decision_count = row.get("decision_count", 0)
        todo_count = row.get("todo_count", 0)
        framework = row.get("framework", "")
        text = row.get("result", "")

        today_str = date.today().isoformat()
        label = "📊 今日分析" if date_str == today_str else f"📊 {date_str} 分析"
        self._detail_title.setText(label)

        # 统计栏 HTML
        tag_spans = "  ".join(
            f"<span style='background:#2a2a3e;color:#7c5cfc;padding:1px 6px;"
            f"border-radius:3px;font-size:11px;'>#{t}</span>"
            for t in tags
        )
        stats_parts = []
        if tag_spans:
            stats_parts.append(tag_spans)
        stats_parts.append(
            f"<span style='color:#4ade80;'>✅ 决策: {decision_count}</span>"
        )
        stats_parts.append(
            f"<span style='color:#f59e0b;'>📝 待办: {todo_count}</span>"
        )
        if framework:
            stats_parts.append(
                f"<span style='color:#7c5cfc;'>🧭 {framework}</span>"
            )
        self._lbl_stats.setText("  |  ".join(stats_parts))

        self._detail_text.setPlainText(text)
        self._current_date = date_str

    def _on_search(self, text: str):
        self._search_keyword = text.strip()
        self._refresh_date_list()

    def _on_calendar(self):
        """日历弹窗 → 跳转到选中日期"""
        popup = QDialog(self)
        popup.setWindowTitle("选择日期")
        popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        popup.setStyleSheet(ANALYSIS_BROWSER_STYLE)

        cal = QCalendarWidget()
        cal.setGridVisible(True)
        cal.setNavigationBarVisible(True)
        cal.clicked.connect(lambda d: self._on_calendar_date(d, popup))

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(cal)
        popup.resize(350, 300)

        # 定位到按钮下方
        pos = self._btn_calendar.mapToGlobal(self._btn_calendar.rect().bottomLeft())
        popup.move(pos)
        popup.exec()

    def _on_calendar_date(self, qdate: QDate, popup: QDialog):
        """日历选中某天"""
        date_str = qdate.toString("yyyy-MM-dd")
        popup.accept()

        # 查找该日期是否在列表中
        found = False
        for i in range(self._date_list.count()):
            item = self._date_list.item(i)
            data = item.data(Qt.UserRole)
            if data and data.get("date") == date_str:
                self._date_list.setCurrentRow(i)
                found = True
                break

        if not found:
            # 检查是否有录音（可能有录音但被日期范围过滤掉了）
            entries = self._db.get_by_date(date_str)
            if entries:
                # 有录音但被过滤了 → 重置范围后重试
                self._search_keyword = ""
                self._date_from = ""
                self._date_to = ""
                self._search_input.clear()
                self._refresh_date_list()
                for i in range(self._date_list.count()):
                    item = self._date_list.item(i)
                    data = item.data(Qt.UserRole)
                    if data and data.get("date") == date_str:
                        self._date_list.setCurrentRow(i)
                        found = True
                        break
                if not found:
                    QMessageBox.information(self, "提示", f"{date_str} 暂无分析记录")
            else:
                QMessageBox.information(self, "提示", f"{date_str} 无录音记录")

    def _on_range_apply(self):
        """应用日期范围过滤"""
        self._date_from = self._edit_from.date().toString("yyyy-MM-dd")
        self._date_to = self._edit_to.date().toString("yyyy-MM-dd")
        self._refresh_date_list()

    def _on_reset(self):
        """重置所有过滤条件"""
        self._search_keyword = ""
        self._date_from = ""
        self._date_to = ""
        self._search_input.clear()
        self._edit_from.setDate(QDate.currentDate().addMonths(-1))
        self._edit_to.setDate(QDate.currentDate())
        self._refresh_date_list()

    def _on_delete(self):
        """删除当前选中的分析"""
        if not self._current_date:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {self._current_date} 的分析记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._db.delete_daily_analysis(self._current_date)
        self._current_date = ""
        self._detail_title.setText("选择日期查看分析")
        self._lbl_stats.setText("")
        self._detail_text.clear()
        self._btn_delete.setEnabled(False)
        self._refresh_date_list()

    def _on_regenerate(self):
        """重新生成当前日期的分析"""
        if not self._current_date:
            QMessageBox.information(self, "提示", "请先从左侧列表选择一条分析记录。")
            return

        if not self._config:
            QMessageBox.warning(self, "错误", "缺少配置，无法调用 LLM。")
            return

        entries = self._db.get_by_date(self._current_date)
        if not entries:
            QMessageBox.information(self, "提示", f"{self._current_date} 没有录音记录，无法生成分析。")
            return

        reply = QMessageBox.question(
            self, "确认重新生成",
            f"将使用 {self._current_date} 的 {len(entries)} 条录音重新生成分析，覆盖原有结果。确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 构建待分析文本
        lines = []
        for i, e in enumerate(entries, 1):
            lines.append(f"--- 录音 #{i} [{e.created_at}] {e.mode_name} {e.duration:.0f}s ---")
            lines.append(e.result)
            lines.append("")
        full_text = "\n".join(lines)

        self._btn_regenerate.setEnabled(False)
        self._btn_regenerate.setText("⏳ 生成中...")
        self._detail_title.setText(f"📊 {self._current_date} 分析 — 重新生成中...")
        self._detail_text.setPlainText(f"正在汇总 {self._current_date} 的 {len(entries)} 条录音...")

        import threading
        from .history_panel import ANALYSIS_PROMPT

        def _run():
            from ..engine.llm import LLMProcessor
            llm = LLMProcessor(
                qwen_key=self._config.qwen_key,
                qwen_flash_key=self._config.qwen_flash_key,
                deepseek_key=self._config.deepseek_key,
                gemini_key=self._config.gemini_key,
                mimo_key=self._config.mimo_key,
                proxy_url=self._config.proxy_url,
            )
            prompt = ANALYSIS_PROMPT.format(count=len(entries), content=full_text)
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self._call_llm(llm, prompt))
            except Exception as e:
                result = f"分析失败: {e}"
            finally:
                loop.close()
            self._regenerate_done.emit(result)

        threading.Thread(target=_run, daemon=True).start()

    async def _call_llm(self, llm, prompt: str) -> str:
        """LLM 三级降级（与 history_panel 一致）"""
        candidates = [
            ("Qwen3.5-Flash", llm._call_qwen_flash),
            ("Qwen-Plus", llm._call_qwen),
            ("DeepSeek-Chat", llm._call_deepseek),
            ("Gemini 2.0 Flash", llm._call_gemini),
        ]
        for name, fn in candidates:
            try:
                result = await fn(prompt, temperature=0.5)
                return result[0] if isinstance(result, tuple) else result
            except Exception:
                pass
        return "全部 LLM 不可用"

    def _on_regenerate_done(self, text: str):
        """LLM 返回后的处理"""
        import re
        import json

        # 解析 JSON
        m = re.search(r'\{[^{}]*"tags"\s*:\s*\[[^\]]*\][^{}]*\}', text, re.DOTALL)
        if not m:
            for m in re.finditer(r'\{[^{}]+\}', text):
                pass
        data = {}
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                pass

        # 落库
        import os
        self._db.save_daily_analysis(
            date=self._current_date,
            result=text,
            tags=data.get("tags", []),
            decision_count=data.get("decision_count", 0),
            todo_count=data.get("todo_count", 0),
            main_thread=data.get("main_thread", ""),
            framework=data.get("framework", ""),
        )

        # 刷新显示
        self._btn_regenerate.setEnabled(True)
        self._btn_regenerate.setText("🔄 重新生成")
        self._btn_delete.setEnabled(True)
        self._refresh_date_list()

        # 定位并选中刚生成的日期
        for i in range(self._date_list.count()):
            item = self._date_list.item(i)
            d = item.data(Qt.UserRole)
            if d and d.get("date") == self._current_date:
                self._date_list.setCurrentRow(i)
                break
