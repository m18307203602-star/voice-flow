# Voice Flow 侧边栏导航 + 统计模块 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前上下堆叠的单页布局改为左侧 QListWidget 导航 + 右侧 QStackedWidget 四页切换（首页/历史/词典/统计）

**Architecture:** 新建 Sidebar 和 StatsPage 两个组件，将 DictionaryDialog 内容提取为可嵌入 Widget，重构 MainWindow._setup_ui() 的布局结构。业务逻辑（session/engine/config）不变，只改 UI 层。

**Tech Stack:** PySide6 Qt Widgets, QPainter 手绘图表, SQLite (HistoryDB)

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `ui/main_window.py` | 重构 | 布局从 QVBoxLayout → QHBoxLayout(sidebar + stack)，首页内容嵌入 page 0，菜单栏"词库管理"改为切换到词典页 |
| `ui/sidebar.py` | **新建** | `SidebarWidget(QListWidget)` — 封装导航项样式、选中交互、current_changed 信号 |
| `ui/stats_page.py` | **新建** | `StatsPage(QWidget)` — 指标卡片 + 扇形图(Canvas) + 柱状图(Canvas) |
| `ui/dictionary_widget.py` | **新建** | `DictionaryWidget(QWidget)` — 嵌入式词库管理面板 |
| `ui/history_panel.py` | 微调 | 新增 `jump_to_item(entry_id)` 方法 + `entry_clicked` Signal |

---

### Task 1: 创建侧边栏组件 `ui/sidebar.py`

**Files:**
- Create: `G:\voice-workflow\voice_flow_app\ui\sidebar.py`

- [ ] **Step 1: 编写 SidebarWidget 类**

```python
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
```

- [ ] **Step 2: 语法检查**

```bash
cd "G:\voice-workflow" && python -c "import ast; ast.parse(open('voice_flow_app/ui/sidebar.py', encoding='utf-8').read()); print('OK')"
```

---

### Task 2: 创建统计页面 `ui/stats_page.py`

**Files:**
- Create: `G:\voice-workflow\voice_flow_app\ui\stats_page.py`

- [ ] **Step 1: 在 HistoryDB 中添加统计查询方法**

在 `G:\voice-workflow\voice_flow_app\storage\history_db.py` 末尾 `close()` 方法之前新增：

```python
def get_stats_all_time(self) -> dict:
    """全时段统计数据：总时长、总次数、总字数、STT引擎分布
    
    Returns:
        {"total_duration": float, "total_count": int, "total_chars": int,
         "engines": {name: {"calls": int, "duration": float}}}
    """
    row = self._conn.execute(
        "SELECT COALESCE(SUM(duration), 0) as dur, COUNT(*) as cnt, "
        "COALESCE(SUM(LENGTH(result)), 0) as chars "
        "FROM recordings WHERE status = 'success'"
    ).fetchone()
    
    eng_rows = self._conn.execute(
        "SELECT stt_engine, COUNT(*) as cnt, COALESCE(SUM(duration), 0) as dur "
        "FROM recordings WHERE status = 'success' AND stt_engine != '' "
        "GROUP BY stt_engine"
    ).fetchall()
    
    engines = {}
    for r in eng_rows:
        engines[r["stt_engine"] or "unknown"] = {
            "calls": r["cnt"],
            "duration": round(r["dur"] or 0, 1),
        }
    
    return {
        "total_duration": round(row["dur"] or 0, 1),
        "total_count": row["cnt"] or 0,
        "total_chars": row["chars"] or 0,
        "engines": engines,
    }

def get_daily_stats(self, days: int = 7) -> list[dict]:
    """最近 N 天每日统计：日期、次数、时长
    
    Returns:
        [{"date": "2026-06-21", "count": 5, "duration": 120.5}, ...]
    """
    rows = self._conn.execute(
        "SELECT date(created_at) as d, COUNT(*) as cnt, "
        "COALESCE(SUM(duration), 0) as dur "
        "FROM recordings WHERE status = 'success' "
        "AND created_at >= datetime('now', 'localtime', ?) "
        "GROUP BY d ORDER BY d ASC",
        (f"-{days} days",),
    ).fetchall()
    return [
        {"date": r["d"], "count": r["cnt"], "duration": round(r["dur"] or 0, 1)}
        for r in rows
    ]
```

- [ ] **Step 2: 编写 StatsPage 类框架**

```python
"""统计页面 — 指标卡片 + 扇形图 + 柱状图"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
import math


STATS_STYLE = """
QWidget#statsPage { background-color: #0d0d14; }
QLabel#cardValue { color: #cba6f7; font-size: 28px; font-weight: bold; }
QLabel#cardLabel { color: #8888a8; font-size: 12px; }
QLabel#sectionTitle { color: #e4e4f0; font-size: 15px; font-weight: 600; }
"""


class _PieChart(QWidget):
    """扇形图 — QPainter 手绘"""
    
    COLORS = {
        "tencent": QColor("#7c5cfc"),
        "tencent_sentence": QColor("#7c5cfc"),
        "aliyun": QColor("#f97316"),
        "iflytek": QColor("#22c55e"),
    }
    _FALLBACK = QColor("#6b7280")
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict[str, float] = {}  # {label: value}
        self.setMinimumSize(220, 200)
    
    def set_data(self, data: dict[str, float]):
        """设置数据 {标签: 数值}"""
        self._data = data
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(10, 10, -10, -10)
        
        if not self._data or sum(self._data.values()) == 0:
            painter.setPen(QColor("#8888a8"))
            painter.drawText(rect, Qt.AlignCenter, "暂无数据")
            return
        
        total = sum(self._data.values())
        # 扇形图放在左上区域
        size = min(rect.width(), rect.height()) - 20
        pie_rect = rect.adjusted(0, 0, -(rect.width() - size), -(rect.height() - size))
        center = pie_rect.center()
        radius = size // 2
        
        start_angle = 90 * 16  # Qt 用 1/16 度
        labels = list(self._data.keys())
        values = list(self._data.values())
        
        for i, (label, val) in enumerate(zip(labels, values)):
            span = int(360 * 16 * val / total)
            color = self.COLORS.get(label.split("(")[0].strip(), self._FALLBACK)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPie(pie_rect, start_angle, span)
            start_angle += span
        
        # 图例在右侧
        legend_x = pie_rect.right() + 16
        y = pie_rect.top() + 8
        painter.setFont(QFont("Microsoft YaHei", 10))
        for i, (label, val) in enumerate(zip(labels, values)):
            pct = val / total * 100 if total > 0 else 0
            color = self.COLORS.get(label.split("(")[0].strip(), self._FALLBACK)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRect(legend_x, y, 12, 12)
            painter.setPen(QColor("#cdd6f4"))
            short_label = label[:8] if len(label) > 8 else label
            painter.drawText(legend_x + 18, y + 12, f"{short_label} {pct:.0f}%")
            y += 24


class _BarChart(QWidget):
    """柱状图 — QPainter 手绘，7 天趋势"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []  # [{"date": "06-15", "count": 3, "duration": 45.2}, ...]
        self.setMinimumSize(280, 200)
    
    def set_data(self, data: list[dict]):
        self._data = data
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(20, 30, -20, -30)
        
        if not self._data:
            painter.setPen(QColor("#8888a8"))
            painter.drawText(rect, Qt.AlignCenter, "暂无数据")
            return
        
        max_count = max((d.get("count", 0) for d in self._data), default=1)
        bar_w = max(24, (rect.width() - 20) // len(self._data) - 8)
        spacing = (rect.width() - bar_w * len(self._data)) // (len(self._data) + 1)
        
        bottom = rect.bottom()
        
        for i, d in enumerate(self._data):
            count = d.get("count", 0)
            bar_h = int((count / max_count) * rect.height() * 0.9) if max_count > 0 else 0
            
            x = rect.left() + spacing + i * (bar_w + spacing)
            
            # 紫色柱子
            painter.setBrush(QBrush(QColor("#7c5cfc")))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, bottom - bar_h, bar_w, bar_h, 4, 4)
            
            # 数值
            painter.setPen(QColor("#cdd6f4"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            painter.drawText(x - 4, bottom - bar_h - 6, bar_w + 8, 16,
                           Qt.AlignCenter, str(count))
            
            # 日期
            date_label = d.get("date", "")[-5:]  # "06-15"
            painter.setPen(QColor("#8888a8"))
            painter.drawText(x - 4, bottom + 16, bar_w + 8, 16,
                           Qt.AlignCenter, date_label)


class _StatCard(QFrame):
    """指标卡片 — 紫色数值 + 灰色标签"""
    
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background-color: #1c1c2e; border-radius: 10px; "
            "border: 1px solid #2a2a3e; }"
        )
        self.setFixedHeight(90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        
        self._value_lbl = QLabel("—")
        self._value_lbl.setObjectName("cardValue")
        self._value_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._value_lbl)
        
        lbl = QLabel(label)
        lbl.setObjectName("cardLabel")
        layout.addWidget(lbl)
    
    def set_value(self, text: str):
        self._value_lbl.setText(text)


class StatsPage(QWidget):
    """统计页面"""
    
    def __init__(self, history_db, parent=None):
        super().__init__(parent)
        self.setObjectName("statsPage")
        self.setStyleSheet(STATS_STYLE)
        self._db = history_db
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 标题
        title = QLabel("📊 使用统计")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        
        # ── 三张指标卡片 ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        
        self._card_duration = _StatCard("总口述时间")
        cards_row.addWidget(self._card_duration)
        
        self._card_speed = _StatCard("平均口述速度")
        cards_row.addWidget(self._card_speed)
        
        self._card_count = _StatCard("总录音次数")
        cards_row.addWidget(self._card_count)
        
        layout.addLayout(cards_row)
        
        # ── 图表区：扇形图 + 柱状图 ──
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)
        
        left = QVBoxLayout()
        left.setSpacing(8)
        chart_title1 = QLabel("STT 引擎用量分布")
        chart_title1.setObjectName("sectionTitle")
        left.addWidget(chart_title1)
        
        self._pie = _PieChart()
        left.addWidget(self._pie, 1)
        charts_row.addLayout(left, 1)
        
        right = QVBoxLayout()
        right.setSpacing(8)
        chart_title2 = QLabel("过去 7 天趋势")
        chart_title2.setObjectName("sectionTitle")
        right.addWidget(chart_title2)
        
        self._bar = _BarChart()
        right.addWidget(self._bar, 1)
        charts_row.addLayout(right, 1)
        
        layout.addLayout(charts_row, 1)
    
    def refresh(self):
        """从 HistoryDB 加载数据并刷新显示"""
        stats = self._db.get_stats_all_time()
        
        total_dur = stats["total_duration"]
        total_count = stats["total_count"]
        total_chars = stats["total_chars"]
        
        # 总口述时间
        h = int(total_dur // 3600)
        m = int((total_dur % 3600) // 60)
        self._card_duration.set_value(f"{h}h {m}min" if h > 0 else f"{m} 分钟")
        
        # 平均速度
        if total_dur > 0:
            spm = int(total_chars / (total_dur / 60))
            self._card_speed.set_value(f"{spm} 字/分钟")
        else:
            self._card_speed.set_value("—")
        
        # 总次数
        self._card_count.set_value(str(total_count))
        
        # 扇形图：按引擎聚合
        eng_data = {}
        eng_name_map = {
            "tencent": "腾讯(流式)", "tencent_sentence": "腾讯(短连)",
            "aliyun": "阿里云", "iflytek": "讯飞",
        }
        for eng, info in stats["engines"].items():
            label = eng_name_map.get(eng, eng)
            eng_data[label] = info["calls"]
        self._pie.set_data(eng_data)
        
        # 柱状图
        daily = self._db.get_daily_stats(days=7)
        self._bar.set_data(daily)
    
    def showEvent(self, event):
        """每次切换到统计页时自动刷新"""
        super().showEvent(event)
        self.refresh()
```

- [ ] **Step 3: 语法检查**

```bash
cd "G:\voice-workflow" && python -c "import ast; ast.parse(open('voice_flow_app/ui/stats_page.py', encoding='utf-8').read()); print('OK')"
```

---

### Task 3: 创建嵌入式词典组件 `ui/dictionary_widget.py`

**Files:**
- Create: `G:\voice-workflow\voice_flow_app\ui\dictionary_widget.py`

- [ ] **Step 1: 编写 DictionaryWidget 类**

将 `dictionary_dialog.py` 的表格和按钮逻辑复制为可嵌入 QWidget，移除 QDialog 的 `exec()`/`accept()`/`reject()` 模式，保存按钮改为即时保存不关闭。

```python
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
```

- [ ] **Step 2: 语法检查**

```bash
cd "G:\voice-workflow" && python -c "import ast; ast.parse(open('voice_flow_app/ui/dictionary_widget.py', encoding='utf-8').read()); print('OK')"
```

---

### Task 4: 微调 `ui/history_panel.py` — 新增跳转方法

**Files:**
- Modify: `G:\voice-workflow\voice_flow_app\ui\history_panel.py`

- [ ] **Step 1: 新增 `entry_clicked` Signal 和 `jump_to_item` 方法**

在 `HistoryPanel` 类中：

在 `entry_selected` Signal 下面新增一个 Signal：
```python
entry_clicked = Signal(int)  # entry_id — 首页最近记录点击跳转
```

在 `refresh()` 方法内部，为每个 `QListWidgetItem` 的点击事件连接：

把 `refresh()` 方法中的 `self._list.addItem(item)` 之后加上单击连接：
```python
# 在 for entry in entries: 循环内部，self._list.addItem(item) 之后
# （原代码已有点击事件 _on_select，不需要额外连接——用 list 的 currentRowChanged 即可）
```

实际上 `_on_select` 已经通过 `self._list.currentRowChanged.connect(self._on_select)` 连接了，不需要额外改。

新增 `jump_to_item` 方法，在 `refresh()` 方法之后：
```python
def jump_to_item(self, entry_id: int):
    """从首页跳转到指定记录并高亮选中"""
    # 先刷新确保数据最新
    self.refresh()
    # 在列表中查找对应 entry_id
    for i in range(self._list.count()):
        item = self._list.item(i)
        if item.data(Qt.UserRole) == entry_id:
            self._list.setCurrentRow(i)
            self._list.scrollToItem(item, QListWidget.PositionAtCenter)
            self._on_select(i)
            return
```

- [ ] **Step 2: 确保 `QListWidget` 导入**

在 `history_panel.py` 顶部确认已导入 `QListWidget`（已有，在 `QTextEdit, QListWidget, QListWidgetItem` 中）。

---

### Task 5: 重构 `ui/main_window.py` — 布局改为侧边栏+StackedWidget

**Files:**
- Modify: `G:\voice-workflow\voice_flow_app\ui\main_window.py`

这是最大的改动。需要：
1. `_setup_ui()` 改成 `QHBoxLayout` + 侧边栏 + `QStackedWidget`
2. 首页内容作为 `QWidget`（page 0）包含所有现有控件 + 最近记录预览
3. 历史面板作为 page 1
4. 词典面板作为 page 2
5. 统计页作为 page 3
6. `add_license_menu()` 中的"词库管理"从弹窗改为切换到词典页
7. 首页最近记录的 `QListWidget` 点击时跳转到历史页

- [ ] **Step 1: 在文件顶部新增导入**

```python
from .sidebar import SidebarWidget
from .stats_page import StatsPage
from .dictionary_widget import DictionaryWidget
```

- [ ] **Step 2: 重写 `_setup_ui()` 方法**

```python
def _setup_ui(self):
    central = QWidget()
    self.setCentralWidget(central)
    self._root = QHBoxLayout(central)
    self._root.setContentsMargins(0, 0, 0, 0)
    self._root.setSpacing(0)

    # ── 左侧导航栏 ──
    self._sidebar = SidebarWidget()
    self._sidebar.current_changed.connect(self._on_sidebar_changed)
    self._root.addWidget(self._sidebar)

    # ── 右侧内容区（QStackedWidget） ──
    self._stack = QStackedWidget()
    self._root.addWidget(self._stack, 1)

    # ── Page 0: 首页 ──
    self._home_page = self._create_home_page()
    self._stack.addWidget(self._home_page)

    # ── Page 1: 历史记录 ──
    self._history_panel = HistoryPanel(self._history_db, self._config)
    self._stack.addWidget(self._history_panel)

    # ── Page 2: 词典 ──
    self._dict_widget = DictionaryWidget(self._dictionary)
    self._stack.addWidget(self._dict_widget)

    # ── Page 3: 统计 ──
    self._stats_page = StatsPage(self._history_db)
    self._stack.addWidget(self._stats_page)
```

- [ ] **Step 3: 新增 `_create_home_page()` 方法**

将原 `_setup_ui()` 中到 `_connect_signals()` 之前的所有控件创建逻辑提取到 `_create_home_page()`，额外加入底部"最近记录"列表：

```python
def _create_home_page(self) -> QWidget:
    """创建首页内容（所有现有控件 + 最近记录预览）"""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    # ── 顶部：模式 + 引擎 ──
    top_row = QHBoxLayout()

    # 模式选择
    self._mode_combo = _DropdownStyledCombo()
    self._mode_combo.setFixedWidth(120)
    mode_names = {"1": "中英文（推荐）", "2": "纯英文", "3": "纯中文", "4": "文采", "5": "情感", "6": "代码"}
    mode_tips = {
        "2": "中文语音 → 自动分类/编号/上位词 → 结构化英文",
        "3": "中英文混合语音 → 统一中文输出，英语自动翻译为中文",
    }
    for key, name in mode_names.items():
        self._mode_combo.addItem(name, key)
        if key in mode_tips:
            self._mode_combo.setItemData(self._mode_combo.count() - 1, mode_tips[key], Qt.ToolTipRole)
    top_row.addWidget(QLabel("模式:"))
    top_row.addWidget(self._mode_combo)
    top_row.addSpacing(12)

    # 模式下拉框七彩闪烁动画
    self._mode_gradient_timer = QTimer(self)
    self._mode_gradient_timer.timeout.connect(self._update_mode_combo_gradient)
    self._update_mode_combo_gradient()
    self._mode_gradient_timer.start(50)

    # 引擎选择
    self._eng_btn = QPushButton("全部(3)")
    self._eng_btn.setMinimumWidth(80)
    self._eng_btn.setMaximumHeight(26)
    self._eng_btn.setStyleSheet("""
        QPushButton {
            padding: 2px 8px;
            color: #7c5cfc;
            font-weight: 600;
            font-size: 12px;
        }
    """)
    self._eng_menu = QMenu(self._eng_btn)
    self._eng_actions = {}
    eng_map = {"tencent": "腾讯云", "aliyun": "阿里云", "iflytek": "讯飞"}
    for key, name in eng_map.items():
        action = QAction(name, self._eng_btn)
        action.setCheckable(True)
        action.setChecked(True)
        action.toggled.connect(lambda checked, k=key: self._on_engine_toggled(k, checked))
        self._eng_menu.addAction(action)
        self._eng_actions[key] = action
    self._eng_btn.setMenu(self._eng_menu)
    self._eng_btn.setToolTip("已选: 腾讯云, 阿里云, 讯飞")
    top_row.addWidget(QLabel("STT:"))
    top_row.addWidget(self._eng_btn)

    # STT 模式切换
    self._btn_stt_mode = QPushButton()
    self._btn_stt_mode.setCheckable(True)
    self._btn_stt_mode.setFixedWidth(86)
    self._btn_stt_mode.setMaximumHeight(26)
    self._btn_stt_mode.clicked.connect(self._on_stt_mode_toggled)
    top_row.addWidget(self._btn_stt_mode)

    # 主模型快速切换
    self._primary_combo = QComboBox()
    self._primary_combo.setItemDelegate(_PrimaryModelDelegate(self))
    self._primary_combo.setFixedWidth(130)
    self._primary_combo.setToolTip("选择注入输入框的主模型（对比模型仅展示不注入）\n切换后立即生效，无需重启")
    self._primary_combo.setStyleSheet("""
        QComboBox {
            color: #7c5cfc; font-weight: 600; font-size: 12px;
            background-color: #1c1c2e; border: 1px solid #2a2a3e;
            border-radius: 6px; padding: 3px 8px;
        }
        QComboBox:hover { border-color: #7c5cfc; }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox::down-arrow { image: none; }
        QComboBox QAbstractItemView {
            color: #FFD700; background: #151520;
            selection-background-color: #2e2e48; selection-color: #FFD700;
            outline: none; border: 1px solid #2a2a3e;
            border-radius: 8px; padding: 4px;
        }
    """)
    self._primary_combo.currentTextChanged.connect(self._on_primary_model_changed)
    top_row.addWidget(QLabel("主模型:"))
    top_row.addWidget(self._primary_combo)

    # 设置按钮
    top_row.addStretch()
    self._btn_settings = QPushButton("⚙ 设置")
    self._btn_settings.setFixedWidth(100)
    top_row.addWidget(self._btn_settings)

    layout.addLayout(top_row)

    # ── 控制栏 ──
    ctrl_row = QHBoxLayout()

    self._btn_record = QPushButton("🎤 开始录音")
    self._btn_record.setObjectName("recordBtn")
    self._btn_record.setFixedWidth(160)
    ctrl_row.addWidget(self._btn_record)

    self._btn_comparison = QPushButton("🔬 对比")
    self._btn_comparison.setFixedWidth(80)
    self._btn_comparison.setCheckable(True)
    self._btn_comparison.setToolTip("多模型对比 — 同一输入并行调用主模型+对比模型，对比结果和延迟")
    self._btn_comparison.clicked.connect(self._on_comparison_toggled)
    ctrl_row.addWidget(self._btn_comparison)

    self._lbl_status = QLabel("就绪")
    self._lbl_status.setStyleSheet("color: #4ade80; font-size: 14px; font-weight: 600;")
    ctrl_row.addWidget(self._lbl_status)

    ctrl_row.addStretch()

    self._level_bar = QProgressBar()
    self._level_bar.setRange(0, 100)
    self._level_bar.setValue(0)
    self._level_bar.setFixedWidth(120)
    self._level_bar.setFixedHeight(8)
    ctrl_row.addWidget(QLabel("电平"))
    ctrl_row.addWidget(self._level_bar)

    layout.addLayout(ctrl_row)

    # ── 引擎状态行 ──
    eng_status_row = QHBoxLayout()
    self._lbl_eng_status = {}
    for eng in ["tencent", "iflytek", "aliyun"]:
        lbl = QLabel("—")
        lbl.setStyleSheet("color: #8888a8; font-size: 11px; padding: 0 8px;")
        eng_status_row.addWidget(QLabel(f"{eng}:"))
        eng_status_row.addWidget(lbl)
        self._lbl_eng_status[eng] = lbl
    self._btn_usage_stats = QPushButton("用量统计 📊")
    self._btn_usage_stats.setFixedHeight(28)
    self._btn_usage_stats.setToolTip("查看 STT + LLM 完整用量统计")
    self._btn_usage_stats.setStyleSheet("""
        QPushButton {
            background-color: #1c1c2e;
            color: #8888a8;
            border: 1px solid #2a2a3e;
            border-radius: 6px;
            font-size: 12px;
            padding: 0 10px;
        }
        QPushButton:hover {
            background-color: #2e2e48;
            color: #e4e4f0;
        }
    """)
    self._btn_usage_stats.clicked.connect(self._show_usage_stats)
    eng_status_row.addWidget(self._btn_usage_stats)
    eng_status_row.addStretch()
    layout.addLayout(eng_status_row)

    # ── 模型对比面板（默认隐藏） ──
    self._comparison_panel = self._create_comparison_panel()
    self._comparison_panel.setVisible(False)
    layout.addWidget(self._comparison_panel)

    # ── 声纹浮动窗口 ──
    self._voiceprint = VoiceprintWidget()

    # ── 最近记录预览（5 条） ──
    recent_label = QLabel("📌 最近记录")
    recent_label.setStyleSheet("color: #8888a8; font-size: 12px; font-weight: 600;")
    layout.addWidget(recent_label)

    self._recent_list = QListWidget()
    self._recent_list.setMaximumHeight(200)
    self._recent_list.setStyleSheet("""
        QListWidget {
            background-color: #151520; border: 1px solid #2a2a3e;
            border-radius: 6px;
        }
        QListWidget::item {
            color: #cdd6f4; padding: 6px 10px;
            border-bottom: 1px solid #1e1e30;
        }
        QListWidget::item:hover {
            background-color: #1e1e32; color: #e4e4f0;
        }
        QListWidget::item:selected {
            background-color: #2a2a3e;
        }
    """)
    self._recent_list.itemClicked.connect(self._on_recent_clicked)
    layout.addWidget(self._recent_list)

    # ── 法律滚动字幕 ──
    self._marquee_text = "此软件已申请专利保护，违法使用将遭受刑事诉讼。"
    self._marquee_box = _MarqueeWidget(self._marquee_text, self)
    self._marquee_box.setFixedHeight(32)
    self._marquee_timer = QTimer(self)
    self._marquee_timer.timeout.connect(self._tick_marquee)
    self._marquee_timer.start(50)
    layout.addWidget(self._marquee_box)

    return page
```

- [ ] **Step 4: 新增辅助方法**

```python
def _on_sidebar_changed(self, index: int):
    """左侧导航切换 → 右侧页面切换"""
    self._stack.setCurrentIndex(index)

def _on_recent_clicked(self, item: QListWidgetItem):
    """首页最近记录被点击 → 跳转到历史记录页并定位"""
    entry_id = item.data(Qt.UserRole)
    if entry_id:
        self._sidebar.switch_to("history")  # 切换到历史页
        self._history_panel.jump_to_item(entry_id)  # 定位到具体记录

def _refresh_recent_list(self):
    """刷新首页最近 5 条记录"""
    self._recent_list.clear()
    entries = self._history_db.get_all(limit=5, order_asc=False)
    for entry in entries:
        preview = entry.result[:50].replace('\n', ' ') if entry.result else "(无结果)"
        label = f"{entry.created_at}  [{entry.mode_name}]  {preview}"
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, entry.id)
        self._recent_list.addItem(item)
```

- [ ] **Step 5: 修改 `add_license_menu()` — "词库管理"改为切换到词典页**

```python
def add_license_menu(self):
    """添加许可证和词库菜单项"""
    from PySide6.QtGui import QAction
    menu_bar = self.menuBar()

    # 许可证菜单
    license_menu = menu_bar.addMenu("许可证")
    activate_action = QAction("升级Pro", self)
    activate_action.triggered.connect(self._on_activate_license)
    license_menu.addAction(activate_action)

    license_menu.addSeparator()
    dict_action = QAction("词库管理", self)
    dict_action.triggered.connect(lambda: self._sidebar.switch_to("dictionary"))
    license_menu.addAction(dict_action)
```

- [ ] **Step 6: 在 `_on_result` 末尾添加刷新最近记录**

在 `_on_result` 方法的最后（`self._history_panel.refresh()` 之后）加入：
```python
# 刷新首页最近记录（_history_panel 在 page 1，不是 self._history_panel 了？不对，现在它本身就在 _stack 里）
# _on_result 中已经有 self._history_panel.refresh()，我们需要同步刷新首页最近记录
self._refresh_recent_list()
```

但注意：`_on_result` 里原本就有 `self._history_panel.refresh()`。由于现在 `self._history_panel` 已经在 `_setup_ui()` 中重新创建（在 page 1 里），这个引用路径仍然有效，且 `_refresh_recent_list()` 是首页的方法，也需要调用。需要把原来的 `self._history_panel.refresh()` 改为同时刷新两者。

查看当前 `_on_result` 末尾：
```python
# 找到 self._history_panel.refresh() 这行，改为：
if hasattr(self, '_history_panel') and self._history_panel:
    self._history_panel.refresh()
if hasattr(self, '_recent_list'):
    self._refresh_recent_list()
```

- [ ] **Step 7: 删除旧的 `_on_dict_manage` 方法**

之前添加的弹窗版 `_on_dict_manage` 不再需要（菜单栏已改为直接切换），删除之。

- [ ] **Step 8: 语法检查**

```bash
cd "G:\voice-workflow" && python -c "import ast; ast.parse(open('voice_flow_app/ui/main_window.py', encoding='utf-8').read()); print('OK')"
```

---

### Task 6: 语法检查 HistoryDB 修改

**Files:**
- Verify: `G:\voice-workflow\voice_flow_app\storage\history_db.py`

- [ ] **Step 1: 语法检查**

```bash
cd "G:\voice-workflow" && python -c "import ast; ast.parse(open('voice_flow_app/storage/history_db.py', encoding='utf-8').read()); print('OK')"
```

---

### Task 7: 全量语法检查 + 提交

- [ ] **Step 1: 检查所有改动文件**

```bash
cd "G:\voice-workflow" && python -c "
import ast
files = [
    'voice_flow_app/ui/sidebar.py',
    'voice_flow_app/ui/stats_page.py',
    'voice_flow_app/ui/dictionary_widget.py',
    'voice_flow_app/ui/history_panel.py',
    'voice_flow_app/ui/main_window.py',
    'voice_flow_app/storage/history_db.py',
]
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'OK  {f}')
    except SyntaxError as e:
        print(f'FAIL  {f}: {e}')
"
```

- [ ] **Step 2: 提交**

```bash
cd "G:\voice-workflow"
git add voice_flow_app/ui/sidebar.py voice_flow_app/ui/stats_page.py voice_flow_app/ui/dictionary_widget.py voice_flow_app/ui/main_window.py voice_flow_app/ui/history_panel.py voice_flow_app/storage/history_db.py
git commit -m "feat: 侧边栏导航 + 统计模块 + 嵌入式词典

- 左侧 QListWidget 导航栏（首页/历史/词典/统计）
- 右侧 QStackedWidget 四页切换
- 统计页：口述时间/速度/次数 + 引擎扇形图 + 7天柱状图
- HistoryDB 新增 get_stats_all_time / get_daily_stats 查询
- HistoryPanel 新增 jump_to_item 跳转定位方法
- 词典从弹窗改为嵌入式 Widget"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 验收清单

- [ ] 侧边栏四个导航项可点击切换，选中项紫色左边框
- [ ] 首页：模式选择、STT引擎、短连接、主模型、对比、声纹全部正常
- [ ] 首页：最近 5 条记录显示，点击跳转到历史记录页并定位
- [ ] 历史记录页：搜索、排序、详情、导入导出正常
- [ ] 词典页：增删改查、保存、导入导出、启用开关正常
- [ ] 统计页：三张卡片数值正确，扇形图颜色正确，柱状图显示 7 天数据
- [ ] 窗口 800x600 最小尺寸正常
- [ ] 全局热键录音 + ESC 取消不受影响
- [ ] 菜单栏"许可证 → 词库管理"切换到词典页
