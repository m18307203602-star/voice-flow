"""用户词库 — STT 后替换 + 纠错学习 + 高频建议

Typeless 风格三合一：
  1. 手动词典（查找 → 替换，长词优先）
  2. 纠错记录（用户手动修正后自动记录）
  3. 高频建议（从历史记录分析高频专有名词）
"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


DICT_FILE = "dictionary.json"


class DictionaryManager:
    """管理用户自定义词库 + 纠错学习 + 高频建议"""

    def __init__(self, config_dir: Path = None):
        if config_dir is None:
            config_dir = Path.home() / ".voice_flow"
        self._path = config_dir / DICT_FILE
        self._entries: dict[str, str] = {}          # find_text → replace_text
        self._regex_entries: list[tuple[re.Pattern, str]] = []  # compiled patterns
        self._enabled: bool = True
        self._corrections: list[dict] = []           # [{"from": str, "to": str, "date": str}]
        self.load()

    # ── Public API: 基础词典 ──

    def load(self):
        """从磁盘加载词库 + 纠错记录"""
        if not self._path.exists():
            self._entries = {}
            self._enabled = True
            self._corrections = []
            self._compile_patterns()
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = data.get("entries", {})
            self._enabled = data.get("enabled", True)
            self._corrections = data.get("corrections", [])
        except (json.JSONDecodeError, IOError):
            self._entries = {}
            self._enabled = True
            self._corrections = []
        self._compile_patterns()

    def save(self):
        """持久化到磁盘"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "entries": self._entries,
                    "enabled": self._enabled,
                    "corrections": self._corrections,
                },
                f, ensure_ascii=False, indent=2,
            )

    def apply(self, text: str) -> str:
        """对文本应用所有替换规则，返回替换后的文本"""
        if not self._enabled or not self._entries:
            return text
        result = text
        for pattern, replacement in self._regex_entries:
            result = pattern.sub(replacement, result)
        return result

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool):
        self._enabled = v
        self.save()

    @property
    def entries(self) -> dict[str, str]:
        return dict(self._entries)

    def set_entries(self, entries: dict[str, str]):
        """批量替换全部词条"""
        self._entries = dict(entries)
        self._compile_patterns()
        self.save()

    def add(self, find: str, replace: str):
        """添加或更新一条规则"""
        find = find.strip()
        if not find:
            return
        self._entries[find] = replace
        self._compile_patterns()
        self.save()

    def remove(self, find: str):
        """删除一条规则"""
        self._entries.pop(find, None)
        self._compile_patterns()
        self.save()

    def clear(self):
        """清空全部规则"""
        self._entries.clear()
        self._compile_patterns()
        self.save()

    # ── Public API: 纠错学习 ──

    @property
    def corrections(self) -> list[dict]:
        return list(self._corrections)

    def add_correction(self, from_text: str, to_text: str):
        """记录一条纠错（用户手动修正某个词）

        Args:
            from_text: 原始识别/输出文本片段
            to_text: 用户修正后的文本片段
        """
        from_text = from_text.strip()
        to_text = to_text.strip()
        if not from_text or not to_text:
            return
        if from_text == to_text:
            return

        # 避免重复记录完全相同的纠错
        for c in reversed(self._corrections[-20:]):
            if c["from"] == from_text and c["to"] == to_text:
                return  # 最近 20 条中已有，去重

        self._corrections.append({
            "from": from_text,
            "to": to_text,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        # 限制纠错记录总数
        if len(self._corrections) > 200:
            self._corrections = self._corrections[-100:]
        self.save()

    def get_corrections(self, limit: int = 50) -> list[dict]:
        """获取最近纠错记录（倒序）"""
        return list(reversed(self._corrections))[:limit]

    def remove_correction(self, index: int):
        """删除一条纠错记录（按 get_corrections 的索引）"""
        # index 是倒序列表中的位置，需要映射回正序
        actual = len(self._corrections) - 1 - index
        if 0 <= actual < len(self._corrections):
            self._corrections.pop(actual)
            self.save()

    def promote_correction(self, index: int):
        """将纠错记录提升为正式词典条目"""
        corrs = self.get_corrections(limit=200)
        if 0 <= index < len(corrs):
            c = corrs[index]
            self.add(c["from"], c["to"])
            # 从纠错记录中移除（已升级为正式条目）
            actual = len(self._corrections) - 1 - index
            if 0 <= actual < len(self._corrections):
                self._corrections.pop(actual)
                self.save()

    def clear_corrections(self):
        """清空所有纠错记录"""
        self._corrections.clear()
        self.save()

    # ── Public API: 高频建议 ──

    def generate_suggestions(self, history_db, limit: int = 15) -> list[dict]:
        """从历史记录中分析高频专有名词，返回建议加入词典的词条

        算法：
          1. 取所有历史记录的 result 文本
          2. 用 jieba 分词（如果可用）或简单 2-4 字 n-gram
          3. 过滤掉常见停用词
          4. 找出高频但不在当前词典中的词
          5. 返回 top N 建议

        Returns:
            [{"word": str, "count": int}, ...]
        """
        try:
            import jieba
            _has_jieba = True
        except ImportError:
            _has_jieba = False

        # 从数据库获取所有结果文本
        entries = history_db.get_all(limit=500, order_asc=False)
        all_text = " ".join(e.result for e in entries if e.result)

        if not all_text.strip():
            return []

        # 停用词（中文常见无意义词）
        _stopwords = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
            "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
            "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
            "这个", "那个", "什么", "怎么", "哪", "为什么", "可以", "这个", "如果",
            "因为", "所以", "但是", "然后", "而且", "或者", "不过", "只是",
            "我们", "他们", "你们", "大家", "觉得", "可能", "应该", "需要",
            "没", "对", "做", "让", "用", "把", "给", "被", "吧", "吗", "呢",
            "啊", "哦", "嗯", "哈", "嘛", "呀", "呗", "了", "过", "还", "会",
            "能", "想", "知道", "比较", "还是", "就是", "这个", "这样", "那样",
            "现在", "今天", "昨天", "明天", "已经", "时候", "一下", "一点",
            "这么", "那么", "怎么", "其实", "真的", "然后", "最后", "之后",
            "之前", "主要", "基本", "大概", "一直", "等等", "而且",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "it", "its", "this", "that", "these", "those", "and", "or",
            "but", "not", "no", "if", "so", "as", "than", "then",
            "i", "you", "he", "she", "we", "they", "me", "him", "her",
            "us", "them", "my", "your", "his", "our", "their",
        }

        # 已知词汇集合（避免建议已有的）
        known_words = set()
        for k, v in self._entries.items():
            known_words.add(k.lower())
            known_words.add(v.lower())

        word_counts: dict[str, int] = {}

        if _has_jieba:
            # jieba 分词
            words = jieba.cut(all_text)
            for w in words:
                w = w.strip()
                if len(w) < 2 or len(w) > 8:
                    continue
                if w.lower() in _stopwords:
                    continue
                if w.lower() in known_words:
                    continue
                # 只保留中文词或中英混合词（排除纯标点/数字）
                if not any('一' <= c <= '鿿' or c.isalpha() for c in w):
                    continue
                word_counts[w] = word_counts.get(w, 0) + 1
        else:
            # Fallback: 2-4 字 n-gram（不需要 jieba）
            import unicodedata
            text = all_text
            # 提取中文 + 英文 + 数字连续段
            segments = []
            current = []
            for ch in text:
                cat = unicodedata.category(ch)
                if ('一' <= ch <= '鿿' or
                    '㐀' <= ch <= '䶿' or
                    ch.isalpha() or ch.isdigit()):
                    current.append(ch)
                else:
                    if current:
                        segments.append(''.join(current))
                        current = []
            if current:
                segments.append(''.join(current))

            for seg in segments:
                if len(seg) < 2:
                    continue
                # 2-gram
                for i in range(len(seg) - 1):
                    bigram = seg[i:i+2]
                    if bigram.lower() in known_words:
                        continue
                    word_counts[bigram] = word_counts.get(bigram, 0) + 1
                # 3-gram and 4-gram for longer segments
                if len(seg) >= 3:
                    for i in range(len(seg) - 2):
                        trigram = seg[i:i+3]
                        if trigram.lower() in known_words:
                            continue
                        word_counts[trigram] = word_counts.get(trigram, 0) + 1
                if len(seg) >= 4:
                    for i in range(len(seg) - 3):
                        quadgram = seg[i:i+4]
                        if quadgram.lower() in known_words:
                            continue
                        word_counts[quadgram] = word_counts.get(quadgram, 0) + 1

        # 过滤低频词（至少出现 3 次）
        word_counts = {k: v for k, v in word_counts.items() if v >= 3}

        # 按频率降序排序
        sorted_words = sorted(word_counts.items(), key=lambda x: -x[1])
        return [{"word": w, "count": c} for w, c in sorted_words[:limit]]

    # ── Internal ──

    def _compile_patterns(self):
        """预编译所有正则，按 key 长度降序（长词优先匹配）"""
        self._regex_entries.clear()
        for find in sorted(self._entries.keys(), key=len, reverse=True):
            replace = self._entries[find]
            try:
                pattern = re.compile(re.escape(find), re.IGNORECASE)
                self._regex_entries.append((pattern, replace))
            except re.error:
                pass
