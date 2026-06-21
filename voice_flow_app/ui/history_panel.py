"""历史面板 — 滚动列表 + 详情视图

📌 暂存：今日分析 20 维度规划（待后续实施）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
一、时间节奏类（SQL）
 1. 时间线 — 全天活动流
 2. 工作时段分布 — 上/下/晚 次数+时长
 3. 工作脉冲 — 连续录音的高密度时段
 4. 平均间隔 — 两次录音间隔时间
 5. 单次产出 — 时长+LLM字数

二、内容主线类（LLM）
 6. 🔴 主线逻辑 — 一条连贯故事线
 7. 🟡 次要线索 — 与主线无关的穿插话题
 8. 🔗 交叉关联 — 看似无关话题的内在联系
 9. 🏷️ 关键标签 — 每条 2-3 个标签
10. 🧭 思考方向 — 指向的大方向

三、决策与行动类（LLM）
11. ✅ 已做决策
12. ❓ 待决策
13. 📝 待办提取
14. 🔄 持续推进 — 跨天话题追踪

四、模式与习惯类（SQL+LLM）
15. 🧠 思维模式 — 整理/文采/情感比例
16. 📈 深度趋势 — 对比前几日深浅变化
17. 🔤 高频词云

五、上位框架映射（LLM）
18. 🗺️ 知识地图 — 定位到更大知识框架
19. 🌳 思维导图 — XMind JSON 输出

六、跨日洞察
20. 📅 周报/月报
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
当前已实施: 维度 1-7,9,11,13,18（6段 Prompt 一条 LLM 调用）
待实施: 维度 8,10,12,14-17,19-20
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QSplitter, QLineEdit, QDialog, QDialogButtonBox,
    QScrollArea, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from datetime import date, datetime, timedelta
import json
import re
import difflib

ANALYSIS_PROMPT = """你是工作日志分析师。以下是用户今天的所有语音录音内容（共 {count} 条），请严格按以下格式输出分析报告：

━━━━━━━━━━━━━━━━━━━━
📋 一、流程主线
━━━━━━━━━━━━━━━━━━━━
按时间顺序串联今天的主要工作流，从早到晚一条逻辑主线走到尾。每条标注时间点和模式。

━━━━━━━━━━━━━━━━━━━━
🔗 二、次要线索
━━━━━━━━━━━━━━━━━━━━
与主线无关的穿插话题，独立列出。

━━━━━━━━━━━━━━━━━━━━
🏷️ 三、关键标签
━━━━━━━━━━━━━━━━━━━━
5-8 个标签概括今天的内容（如 #bug修复 #UI优化）。

━━━━━━━━━━━━━━━━━━━━
✅ 四、已做决策
━━━━━━━━━━━━━━━━━━━━
今天明确拍板了哪些事。

━━━━━━━━━━━━━━━━━━━━
📝 五、待办事项
━━━━━━━━━━━━━━━━━━━━
从对话中提取的行动项。

━━━━━━━━━━━━━━━━━━━━
🧭 六、上位框架
━━━━━━━━━━━━━━━━━━━━
将今天的工作映射到更大的方向下。如「桌面工具开发」→「个人生产力系统」。

━━━━━━━━━━━━━━━━━━━━
📊 [DATA]
━━━━━━━━━━━━━━━━━━━━
在报告最后输出一行 JSON（不要 markdown 代码块，纯文本），包含以下字段：
- tags: 字符串数组，5-8个标签（去掉#号，如 ["bug修复", "UI优化"]）
- decision_count: 整数，今天明确拍板的决策数量
- todo_count: 整数，提取的待办事项数量
- main_thread: 字符串，主线一句话概括（15字以内）
- framework: 字符串，上位框架映射（如 "个人生产力系统"）

严格只输出这一行 JSON，格式如下：
{{"tags": ["xx","xx"], "decision_count": N, "todo_count": N, "main_thread": "xx", "framework": "xx"}}

录音内容：
{content}"""


class _CorrectionDialog(QDialog):
    """纠错编辑对话框 — 编辑 LLM 输出，自动检测差异，一键加入词典

    布局：
      ┌──────────────────────────────────────┐
      │  📝 纠错编辑                          │
      │                                      │
      │  原始识别：(只读)                      │
      │  ┌──────────────────────────────────┐ │
      │  │ STT 原始转写文本...               │ │
      │  └──────────────────────────────────┘ │
      │                                      │
      │  输出结果：(可编辑)                    │
      │  ┌──────────────────────────────────┐ │
      │  │ LLM 输出文本（可修改）...          │ │
      │  └──────────────────────────────────┘ │
      │                                      │
      │  🔍 检测到 N 处修改：                  │
      │  ┌──────────────────────────────────┐ │
      │  │ 原文片段 → 修正片段   [加入词典]   │ │
      │  │ 原文片段2 → 修正片段2 [加入词典]   │ │
      │  └──────────────────────────────────┘ │
      │                                      │
      │  [全部加入词典]  [仅保存修改]  [取消]   │
      └──────────────────────────────────────┘
    """

    STYLE = """
    QDialog { background-color: #0d0d14; }
    QLabel { color: #e4e4f0; font-size: 13px; }
    QLabel#title { font-size: 16px; font-weight: bold; color: #e4e4f0; }
    QLabel#sectionLabel { color: #8888a8; font-size: 11px; font-weight: 600; }
    QLabel#diffLabel { color: #f59e0b; font-size: 12px; }
    QTextEdit {
        background-color: #151520; color: #e4e4f0;
        border: 1px solid #2a2a3e; border-radius: 6px;
        font-size: 12px; padding: 8px;
    }
    QPushButton {
        background-color: #222238; color: #e4e4f0;
        border: 1px solid #2a2a3e; border-radius: 6px;
        padding: 6px 14px; font-size: 12px;
    }
    QPushButton:hover { background-color: #2e2e48; }
    QPushButton#addToDictBtn {
        background-color: #4ade80; color: #0d0d14;
        border: none; font-weight: 600;
    }
    QPushButton#addToDictBtn:hover { background-color: #6ee7a0; }
    QPushButton#addAllBtn {
        background-color: #7c5cfc; color: #fff;
        border: none; font-weight: 600;
    }
    QPushButton#addAllBtn:hover { background-color: #9170ff; }
    QPushButton#saveBtn {
        background-color: #7c5cfc; color: #fff;
        border: none; font-weight: 600;
    }
    QPushButton#saveBtn:hover { background-color: #9170ff; }
    QFrame#diffFrame {
        background-color: #1c1c2e; border: 1px solid #2a2a3e;
        border-radius: 6px;
    }
    """

    def __init__(self, original_transcripts: dict, result_text: str, dictionary, parent=None):
        super().__init__(parent)
        self._dict = dictionary
        self._original_result = result_text
        self._diffs: list[tuple[str, str]] = []  # [(from_text, to_text), ...]

        self.setWindowTitle("纠错编辑")
        self.setMinimumSize(600, 520)
        self.resize(650, 580)
        self.setStyleSheet(self.STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel("📝 纠错编辑")
        title.setObjectName("title")
        layout.addWidget(title)

        # ── 原始识别（只读） ──
        trans_label = QLabel("原始识别：")
        trans_label.setObjectName("sectionLabel")
        layout.addWidget(trans_label)

        trans_text = QTextEdit()
        trans_text.setReadOnly(True)
        trans_text.setMaximumHeight(100)
        trans_lines = []
        for eng, text in original_transcripts.items():
            if text and not str(text).startswith("[错误]"):
                trans_lines.append(f"[{eng}] {text}")
        trans_text.setPlainText('\n'.join(trans_lines) if trans_lines else "(无原始识别)")
        layout.addWidget(trans_text)

        # ── 输出结果（可编辑） ──
        result_label = QLabel("输出结果：（可直接编辑修正）")
        result_label.setObjectName("sectionLabel")
        layout.addWidget(result_label)

        self._result_edit = QTextEdit()
        self._result_edit.setPlainText(result_text)
        self._result_edit.setMinimumHeight(120)
        layout.addWidget(self._result_edit, 1)

        # ── 差异检测区域 ──
        diff_label = QLabel("🔍 检测到修改：")
        diff_label.setObjectName("sectionLabel")
        layout.addWidget(diff_label)

        self._diff_container = QVBoxLayout()
        self._diff_container.setSpacing(4)
        diff_frame = QFrame()
        diff_frame.setObjectName("diffFrame")
        diff_frame.setLayout(self._diff_container)
        diff_frame.setMaximumHeight(140)
        layout.addWidget(diff_frame)

        self._diff_empty = QLabel("  编辑输出结果后点击「检测差异」")
        self._diff_empty.setStyleSheet("color: #555570; font-size: 12px;")
        self._diff_container.addWidget(self._diff_empty)

        # ── 按钮行 1：检测差异 ──
        detect_row = QHBoxLayout()
        detect_btn = QPushButton("🔍 检测差异")
        detect_btn.clicked.connect(self._detect_diffs)
        detect_row.addWidget(detect_btn)
        detect_row.addStretch()
        layout.addLayout(detect_row)

        # ── 按钮行 2：保存/取消 ──
        btn_row = QHBoxLayout()
        self._add_all_btn = QPushButton("📥 全部加入词典")
        self._add_all_btn.setObjectName("addAllBtn")
        self._add_all_btn.clicked.connect(self._add_all_to_dict)
        self._add_all_btn.setVisible(False)
        btn_row.addWidget(self._add_all_btn)

        btn_row.addStretch()

        self._save_btn = QPushButton("💾 仅保存修改")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.clicked.connect(self._save_only)
        btn_row.addWidget(self._save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _detect_diffs(self):
        """对比原始结果和当前编辑文本，检测差异"""
        new_text = self._result_edit.toPlainText()
        if new_text == self._original_result:
            self._clear_diffs()
            self._diff_empty = QLabel("  未检测到修改")
            self._diff_empty.setStyleSheet("color: #555570; font-size: 12px;")
            self._diff_container.addWidget(self._diff_empty)
            return

        # 用 SequenceMatcher 找出差异
        matcher = difflib.SequenceMatcher(
            None, self._original_result, new_text
        )
        ops = matcher.get_opcodes()

        self._clear_diffs()
        self._diffs = []

        diff_count = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                continue
            if tag in ('replace', 'delete', 'insert'):
                from_text = self._original_result[i1:i2].strip()
                to_text = new_text[j1:j2].strip()

                # 跳过空白变化
                if not from_text and not to_text:
                    continue
                if from_text == to_text:
                    continue

                # 只关注 2-20 字的修改（太短无意义，太长是整段重写）
                if len(from_text) < 2 and len(to_text) < 2:
                    continue
                if len(from_text) > 30 or len(to_text) > 30:
                    continue

                diff_count += 1
                self._diffs.append((from_text, to_text))

                # 添加差异行
                diff_row = QHBoxLayout()
                diff_row.setSpacing(8)

                from_lbl = QLabel(f"「{from_text or '(空)'}」 → 「{to_text or '(空)'}」")
                from_lbl.setStyleSheet("color: #f59e0b; font-size: 12px;")
                diff_row.addWidget(from_lbl)
                diff_row.addStretch()

                add_btn = QPushButton("加入词典")
                add_btn.setObjectName("addToDictBtn")
                add_btn.setFixedWidth(80)
                idx = diff_count - 1
                add_btn.clicked.connect(
                    lambda checked, i=idx: self._add_single_to_dict(i)
                )
                diff_row.addWidget(add_btn)

                diff_widget = QWidget()
                diff_widget.setLayout(diff_row)
                self._diff_container.addWidget(diff_widget)

        if diff_count == 0:
            self._diff_empty = QLabel("  未检测到需要纠错的修改（修改太小或太大）")
            self._diff_empty.setStyleSheet("color: #555570; font-size: 12px;")
            self._diff_container.addWidget(self._diff_empty)
            self._add_all_btn.setVisible(False)
        else:
            self._add_all_btn.setVisible(True)

    def _clear_diffs(self):
        """清除差异显示区域"""
        while self._diff_container.count():
            item = self._diff_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_single_to_dict(self, index: int):
        """将单个差异加入词典"""
        if 0 <= index < len(self._diffs):
            from_text, to_text = self._diffs[index]
            self._dict.add_correction(from_text, to_text)
            self._dict.add(from_text, to_text)  # 同时加入正式词典
            # 标记已添加
            self._diffs[index] = (from_text, to_text)  # 保持不变
            QMessageBox.information(
                self, "已添加",
                f"「{from_text}」→「{to_text}」已加入词典和纠错记录。"
            )

    def _add_all_to_dict(self):
        """将所有检测到的差异加入词典"""
        if not self._diffs:
            return
        count = 0
        for from_text, to_text in self._diffs:
            if from_text and to_text:
                self._dict.add_correction(from_text, to_text)
                self._dict.add(from_text, to_text)
                count += 1
        QMessageBox.information(
            self, "已添加",
            f"已将 {count} 条修改加入词典和纠错记录。"
        )

    def _save_only(self):
        """仅保存修改后的文本（不加入词典）"""
        new_text = self._result_edit.toPlainText()
        self._edited_text = new_text
        self.accept()

    def get_edited_text(self) -> str:
        """获取编辑后的文本"""
        return getattr(self, '_edited_text', self._result_edit.toPlainText())


class HistoryPanel(QWidget):
    """历史记录面板：左侧列表 + 右侧详情"""

    entry_selected = Signal(int)  # entry_id
    entry_clicked = Signal(int)   # entry_id — 首页最近记录点击跳转
    _analysis_ready = Signal(str)  # 分析完成信号（后台线程 → 主线程）
    correction_made = Signal()    # 用户完成纠错（通知外部刷新词典）

    def __init__(self, history_db, config=None, dictionary=None):
        super().__init__()
        self._db = history_db
        self._config = config
        self._dict = dictionary

        self._analysis_ready.connect(self._show_analysis)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 左侧：列表 ──
        left = QVBoxLayout()
        left.setSpacing(4)

        # ── 搜索框：独占整行 ──
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索...")
        self._search_input.setStyleSheet(
            "background: #1c1c2e; color: #e4e4f0; border: 1px solid #2a2a3e; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self._search_input.textChanged.connect(self._on_search)
        left.addWidget(self._search_input)

        # ── 按钮栏：搜索框下方，等宽铺满 ──
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(6)
        self._sort_asc = False  # 默认倒序：新→旧（更新问顶）
        self._btn_sort = QPushButton("↓ 更新问顶")
        self._btn_sort.setToolTip("点击切换时间排序方向")
        self._btn_sort.clicked.connect(self._toggle_sort)
        btn_bar.addWidget(self._btn_sort, 1)

        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._clear_all)
        btn_bar.addWidget(self._btn_clear, 1)
        left.addLayout(btn_bar)

        self._list = QListWidget()
        self._list.setSortingEnabled(False)  # 禁止隐式排序，严格按插入顺序
        self._list.setStyleSheet(
            "QListWidget { background: #1c1c2e; border: 1px solid #2a2a3e; border-radius: 6px; }"
            "QListWidget::item { color: #e4e4f0; padding: 8px; border-bottom: 1px solid #2a2a3e; }"
            "QListWidget::item:selected { background: #2a2a3e; }"
            "QListWidget::item:hover { background: #333350; }"
        )
        self._list.currentRowChanged.connect(self._on_select)
        left.addWidget(self._list, 1)

        left_widget = QWidget()
        left_widget.setLayout(left)

        # ── 右侧：详情 ──
        right = QVBoxLayout()
        right.setSpacing(6)

        self._detail_title = QLabel("选择一条记录查看详情")
        self._detail_title.setStyleSheet("color: #8888a8; font-size: 14px; font-weight: bold;")
        right.addWidget(self._detail_title)

        # ── 日期导航（分析模式） ──
        self._current_analysis_date = date.today().isoformat()
        date_nav = QHBoxLayout()
        date_nav.setSpacing(4)

        self._btn_prev_day = QPushButton("⟵")
        self._btn_prev_day.setToolTip("前一天")
        self._btn_prev_day.setFixedWidth(60)
        self._btn_prev_day.setFixedHeight(40)
        self._btn_prev_day.setStyleSheet(
            "QPushButton { font-size: 26px; font-weight: 900; color: #e4e4f0;"
            "background: #1c1c2e; border: 2px solid #333350; border-radius: 8px;"
            "padding: 0px 8px; }"
            "QPushButton:hover { background: #2a2a3e; border-color: #e4e4f0; }"
            "QPushButton:pressed { background: #333350; }"
        )
        self._btn_prev_day.clicked.connect(lambda: self._navigate_date(-1))
        date_nav.addWidget(self._btn_prev_day)

        self._lbl_analysis_date = QLabel("")
        self._lbl_analysis_date.setStyleSheet(
            "color: #e4e4f0; font-size: 13px; font-weight: bold;")
        self._lbl_analysis_date.setAlignment(Qt.AlignCenter)
        date_nav.addWidget(self._lbl_analysis_date, 1)

        self._btn_next_day = QPushButton("⟶")
        self._btn_next_day.setToolTip("后一天")
        self._btn_next_day.setFixedWidth(60)
        self._btn_next_day.setFixedHeight(40)
        self._btn_next_day.setStyleSheet(
            "QPushButton { font-size: 26px; font-weight: 900; color: #e4e4f0;"
            "background: #1c1c2e; border: 2px solid #333350; border-radius: 8px;"
            "padding: 0px 8px; }"
            "QPushButton:hover { background: #2a2a3e; border-color: #e4e4f0; }"
            "QPushButton:pressed { background: #333350; }"
        )
        self._btn_next_day.clicked.connect(lambda: self._navigate_date(1))
        date_nav.addWidget(self._btn_next_day)

        self._date_nav_widgets = [
            self._btn_prev_day, self._lbl_analysis_date,
            self._btn_next_day,
        ]
        for w in self._date_nav_widgets:
            w.hide()  # 默认隐藏，分析模式下才显示
        right.addLayout(date_nav)

        # ── 统计栏 ──
        self._lbl_stats = QLabel("")
        self._lbl_stats.setStyleSheet("color: #8888a8; font-size: 12px; padding: 2px 0;")
        self._lbl_stats.hide()
        right.addWidget(self._lbl_stats)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(
            "QTextEdit { background: #1c1c2e; color: #e4e4f0; border: 1px solid #2a2a3e; "
            "border-radius: 6px; padding: 8px; font-size: 13px; }"
        )
        right.addWidget(self._detail_text, 1)

        btn_row = QHBoxLayout()
        self._btn_copy = QPushButton("复制结果")
        self._btn_copy.clicked.connect(self._copy_result)
        btn_row.addWidget(self._btn_copy)

        self._btn_correct = QPushButton("✏️ 纠错")
        self._btn_correct.setToolTip("编辑修正 LLM 输出文本，自动检测差异并加入词典")
        self._btn_correct.clicked.connect(self._on_correct)
        btn_row.addWidget(self._btn_correct)

        self._btn_delete = QPushButton("删除")
        self._btn_delete.clicked.connect(self._delete_current)
        btn_row.addWidget(self._btn_delete)

        self._btn_analyze = QPushButton("📊 今日分析")
        self._btn_analyze.setToolTip("汇总今日所有录音，LLM 智能分析")
        self._btn_analyze.clicked.connect(self._analyze_today)
        btn_row.addWidget(self._btn_analyze)

        self._btn_browse = QPushButton("📋 历史分析")
        self._btn_browse.setToolTip("浏览所有历史分析记录")
        self._btn_browse.clicked.connect(self._on_browse_analyses)
        self._btn_browse.hide()
        btn_row.addWidget(self._btn_browse)

        self._btn_regenerate = QPushButton("🔄 重新生成")
        self._btn_regenerate.setToolTip("重新调用 LLM 生成当日分析")
        self._btn_regenerate.clicked.connect(self._regenerate_today)
        self._btn_regenerate.hide()
        btn_row.addWidget(self._btn_regenerate)

        btn_row.addStretch()
        right.addLayout(btn_row)

        right_widget = QWidget()
        right_widget.setLayout(right)

        # ── 分栏 ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self._current_entry_id: int = 0
        self._current_entry_date: str = ""  # 当前查看的消息所属日期
        self.refresh()
        # 自动加载今日已有分析
        self._try_load_today_analysis()

    def refresh(self):
        """刷新列表"""
        import logging
        _log = logging.getLogger("voice_flow.ui")
        self._list.clear()
        entries = list(self._db.get_all(limit=200, order_asc=self._sort_asc))
        _log.debug("历史刷新: %d 条, 排序=%s, 首条=%s, 末条=%s",
                   len(entries),
                   "ASC" if self._sort_asc else "DESC",
                   entries[0].created_at if entries else "N/A",
                   entries[-1].created_at if entries else "N/A")
        for entry in entries:
            preview = entry.result[:60].replace('\n', ' ') if entry.result else "(无结果)"
            label = f"{entry.created_at}  {entry.duration:.1f}s  [{entry.mode_name}]  {preview}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry.id)
            self._list.addItem(item)
        self._list.scrollToTop()

    def jump_to_item(self, entry_id: int):
        """从首页跳转到指定记录并高亮选中"""
        # 先刷新确保数据最新
        self.refresh()
        # 在列表中查找对应 entry_id
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == entry_id:
                self._list.setCurrentRow(i)
                self._list.scrollToItem(item)
                self._on_select(i)
                return

    def _toggle_sort(self):
        """切换排序方向"""
        self._sort_asc = not self._sort_asc
        self._btn_sort.setText("↑ 历史篡前" if self._sort_asc else "↓ 更新问顶")
        # 有搜索内容时重新搜索，否则刷新全部
        query = self._search_input.text().strip()
        if query:
            self._on_search(query)
        else:
            self.refresh()

    def _try_load_today_analysis(self):
        """启动时尝试加载今天的分析"""
        today_str = date.today().isoformat()
        row = self._db.get_daily_analysis(today_str)
        if row:
            self._load_analysis(today_str)

    def _on_select(self, row: int):
        if row < 0:
            return
        item = self._list.item(row)
        entry_id = item.data(Qt.UserRole)
        entry = self._db.get_by_id(entry_id)
        if not entry:
            return

        self._current_entry_id = entry_id

        # 记录该消息的日期，用于上下文感知的「当天分析」按钮
        entry_date = entry.created_at[:10]  # "2026-05-31 16:05:14" → "2026-05-31"
        self._current_entry_date = entry_date

        # 隐藏分析模式 UI
        for w in self._date_nav_widgets:
            w.hide()
        self._lbl_stats.hide()
        self._btn_regenerate.hide()
        self._btn_browse.hide()

        # 按钮文案：过去的消息 → 「当天分析」，今天的 → 「今日分析」
        today_str = date.today().isoformat()
        if entry_date != today_str:
            self._btn_analyze.setText(f"📊 {entry_date} 分析")
            self._btn_analyze.setToolTip(f"查看或生成 {entry_date} 的每日分析")
        else:
            self._btn_analyze.setText("📊 今日分析")
            self._btn_analyze.setToolTip("汇总今日所有录音，LLM 智能分析")

        # 实际使用的 STT 引擎（非配置偏好）
        _ENGINE_DISPLAY = {
            "tencent_sentence": "腾讯(短连接)", "tencent": "腾讯(流式)",
            "iflytek": "讯飞(流式)", "aliyun": "阿里(流式)",
        }
        actual_engine = _ENGINE_DISPLAY.get(entry.stt_engine, entry.stt_engine or "未知")

        # 构建详情
        lines = [
            f"时间: {entry.created_at}    时长: {entry.duration:.1f}s",
            f"模式: {entry.mode_name}    引擎: {actual_engine}    模型: {entry.model_used}",
            f"状态: {entry.status}",
            "",
            "─── 引擎转写 ───",
        ]
        for eng, text in entry.transcripts.items():
            lines.append(f"[{eng}] {text}")
        lines.append("")
        lines.append("─── LLM 输出 ───")
        lines.append(entry.result)

        self._detail_title.setText(
            f"{entry.created_at}  {entry.duration:.1f}s  [{entry.mode_name}]")
        self._detail_text.setPlainText('\n'.join(lines))

    def _on_search(self, query: str):
        if not query.strip():
            self.refresh()
            return
        self._list.clear()
        entries = list(self._db.search(query, limit=100, order_asc=self._sort_asc))
        for entry in entries:
            preview = entry.result[:60].replace('\n', ' ') if entry.result else "(无结果)"
            label = f"{entry.created_at}  {entry.duration:.1f}s  [{entry.mode_name}]  {preview}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry.id)
            self._list.addItem(item)

    def _analyze_today(self):
        """查看今日分析（优先加载已有结果，不自动重复生成）"""
        today_str = date.today().isoformat()

        # ★ 上下文感知：正在看过去的某条消息 → 加载当天的分析
        if self._current_entry_date and self._current_entry_date != today_str:
            self._load_analysis(self._current_entry_date)
            return

        # 今日：先查是否已有分析
        row = self._db.get_daily_analysis(today_str)
        if row:
            # 已有分析 → 直接展示，不重复生成
            self._display_analysis(
                today_str, row["result"], row["tags"],
                row["decision_count"], row["todo_count"],
                row["main_thread"], row["framework"],
            )
        else:
            # 无分析记录 → 显示空状态，用户可手动重新生成
            self._current_analysis_date = today_str
            self._current_entry_date = ""
            self._update_date_nav()
            self._detail_title.setText("📊 今日分析")
            self._lbl_stats.hide()
            self._detail_text.setPlainText("今日暂无内容分析生成")
            self._btn_regenerate.show()
            self._btn_browse.show()

    def _regenerate_today(self):
        """手动重新生成当前日期的分析（LLM 调用）"""
        # 确定目标日期
        target_date = getattr(self, '_current_analysis_date', None) or date.today().isoformat()

        entries = self._db.get_by_date(target_date)
        if not entries:
            self._detail_title.setText("📊 今日分析")
            self._detail_text.setPlainText("该日期暂无录音记录，无法生成分析。")
            return

        self._btn_regenerate.setEnabled(False)
        self._btn_regenerate.setText("⏳ 生成中...")
        self._detail_title.setText(f"📊 分析 — 生成中...")
        self._detail_text.setPlainText(f"正在汇总 {len(entries)} 条录音...")

        # 构建待分析文本
        lines = []
        for i, e in enumerate(entries, 1):
            lines.append(f"--- 录音 #{i} [{e.created_at}] {e.mode_name} {e.duration:.0f}s ---")
            lines.append(e.result)
            lines.append("")
        full_text = "\n".join(lines)

        import threading
        def _run():
            from ..engine.llm import LLMProcessor
            llm = LLMProcessor(
                qwen_key=self._config.qwen_key if self._config else "",
                qwen_flash_key=self._config.qwen_flash_key if self._config else "",
                deepseek_key=self._config.deepseek_key if self._config else "",
                gemini_key=self._config.gemini_key if self._config else "",
                mimo_key=self._config.mimo_key if self._config else "",
                proxy_url=self._config.proxy_url if self._config else "",
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
            self._analysis_ready.emit(result)

        threading.Thread(target=_run, daemon=True).start()

    def _on_browse_analyses(self):
        """打开历史分析浏览窗口"""
        from .analysis_browser import AnalysisBrowser
        dlg = AnalysisBrowser(self._db, config=self._config, parent=self)
        dlg.exec()

    async def _call_llm(self, llm, prompt: str) -> str:
        """LLM 三级降级"""
        candidates = [
            ("Qwen3.5-Flash", llm._call_qwen_flash),
            ("Qwen-Plus", llm._call_qwen),
            ("DeepSeek-Chat", llm._call_deepseek),
            ("Gemini 2.0 Flash", llm._call_gemini),
        ]
        for name, fn in candidates:
            try:
                result = await fn(prompt, temperature=0.5)
                # 处理 tuple[str, dict] 和 str 两种返回格式
                return result[0] if isinstance(result, tuple) else result
            except Exception:
                pass
        return "全部 LLM 不可用"

    # ── 每日分析（持久化 + 日期导航） ──

    @staticmethod
    def _parse_analysis_json(text: str) -> dict:
        """从 LLM 输出中提取结构化 JSON"""
        # 优先匹配含 tags 字段的 JSON 对象
        m = re.search(r'\{[^{}]*"tags"\s*:\s*\[[^\]]*\][^{}]*\}', text, re.DOTALL)
        if not m:
            # 兜底：取最后一个 JSON 对象
            for m in re.finditer(r'\{[^{}]+\}', text):
                pass
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {}

    def _show_analysis(self, text: str):
        """显示分析结果 → 解析 JSON → 落库"""
        target_date = getattr(self, '_current_analysis_date', None) or date.today().isoformat()

        # 解析结构化数据
        data = self._parse_analysis_json(text)
        tags = data.get("tags", [])
        decision_count = data.get("decision_count", 0)
        todo_count = data.get("todo_count", 0)
        main_thread = data.get("main_thread", "")
        framework = data.get("framework", "")

        # 落库
        self._db.save_daily_analysis(
            date=target_date,
            result=text,
            tags=tags,
            decision_count=decision_count,
            todo_count=todo_count,
            main_thread=main_thread,
            framework=framework,
        )

        # 显示
        self._btn_regenerate.setEnabled(True)
        self._btn_regenerate.setText("🔄 重新生成")
        self._display_analysis(target_date, text, tags, decision_count, todo_count,
                               main_thread, framework)

    def _load_analysis(self, date_str: str):
        """从 DB 加载某天的分析并显示"""
        row = self._db.get_daily_analysis(date_str)
        if row:
            self._display_analysis(
                date_str, row["result"], row["tags"],
                row["decision_count"], row["todo_count"],
                row["main_thread"], row["framework"],
            )
        else:
            # 无分析记录 → 检查是否有录音
            self._current_analysis_date = date_str
            self._current_entry_date = ""  # 清空消息上下文
            self._update_date_nav()
            self._detail_title.setText(f"📊 {date_str} — 暂无分析")
            self._lbl_stats.hide()
            # 检查当天是否有录音
            entries = list(self._db.get_all(limit=500))
            has_recordings = any(
                e.created_at.startswith(date_str) for e in entries
            )
            if has_recordings:
                self._detail_text.setPlainText(
                    f"{date_str} 有录音记录，但尚未生成分析。\n\n"
                    f"点击「🔄 重新生成」按钮即可创建该日分析报告。"
                )
                self._btn_regenerate.show()
                self._btn_browse.show()
            else:
                self._detail_text.setPlainText(
                    f"{date_str} 没有录音记录。"
                )
                self._btn_regenerate.hide()
                self._btn_browse.hide()

    def _display_analysis(self, date_str, text, tags, decision_count,
                          todo_count, main_thread, framework):
        """统一的显示逻辑"""
        self._current_analysis_date = date_str
        self._current_entry_date = ""  # 清空消息上下文，进入分析模式
        self._update_date_nav()

        # 标题
        today_str = date.today().isoformat()
        label = "📊 今日分析" if date_str == today_str else f"📊 {date_str} 分析"
        self._detail_title.setText(label)

        # 统计栏
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
        self._lbl_stats.show()

        # 正文
        self._detail_text.setPlainText(text)

        # 分析模式下才显示
        self._btn_regenerate.show()
        self._btn_browse.show()

    def _update_date_nav(self):
        """更新日期导航显示"""
        self._lbl_analysis_date.setText(self._current_analysis_date)
        for w in self._date_nav_widgets:
            w.show()

    def _navigate_date(self, delta_days: int):
        """切换日期"""
        try:
            d = datetime.strptime(self._current_analysis_date, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
        d += timedelta(days=delta_days)
        self._load_analysis(d.isoformat())

    def _copy_result(self):
        if not self._current_entry_id:
            return
        entry = self._db.get_by_id(self._current_entry_id)
        if entry and entry.result:
            import pyperclip
            pyperclip.copy(entry.result)

    def _on_correct(self):
        """打开纠错对话框，允许编辑 LLM 输出并检测差异"""
        if not self._current_entry_id:
            return
        entry = self._db.get_by_id(self._current_entry_id)
        if not entry or not entry.result:
            return

        dlg = _CorrectionDialog(
            original_transcripts=entry.transcripts,
            result_text=entry.result,
            dictionary=self._dict,
            parent=self,
        )
        if dlg.exec():
            # 用户点击了「仅保存修改」或「全部加入词典后保存」
            new_text = dlg.get_edited_text()
            if new_text != entry.result:
                # 更新数据库中的 result 字段
                self._db._conn.execute(
                    "UPDATE recordings SET result = ? WHERE id = ?",
                    (new_text, entry.id),
                )
                self._db._conn.commit()
                # 刷新详情显示
                self._on_select(self._list.currentRow())
                # 通知外部刷新词典
                self.correction_made.emit()

    def _delete_current(self):
        if not self._current_entry_id:
            return
        self._db.delete(self._current_entry_id)
        self._current_entry_id = 0
        self._detail_text.clear()
        self._detail_title.setText("选择一条记录查看详情")
        self.refresh()

    def _clear_all(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有历史记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._db.clear_all()
            self._current_entry_id = 0
            self._detail_text.clear()
            self._detail_title.setText("选择一条记录查看详情")
            self.refresh()
