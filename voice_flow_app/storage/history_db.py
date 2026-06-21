"""历史记录 — SQLite 存储录音和转写结果"""
import json
import sqlite3
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


DB_DIR = Path.home() / ".voice_flow"
DB_PATH = DB_DIR / "history.db"


@dataclass
class HistoryEntry:
    id: int = 0
    created_at: str = ""
    duration: float = 0.0
    engines: list = field(default_factory=list)
    mode: str = ""
    mode_name: str = ""
    transcripts: dict = field(default_factory=dict)
    result: str = ""
    model_used: str = ""
    status: str = "success"
    stt_engine: str = ""    # 实际使用的 STT 引擎名: "tencent_sentence" / "iflytek" / "tencent" / "aliyun"
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0


class HistoryDB:
    """SQLite 历史记录管理器"""

    def __init__(self):
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                duration REAL NOT NULL,
                engines TEXT NOT NULL DEFAULT '[]',
                mode TEXT NOT NULL DEFAULT '1',
                mode_name TEXT NOT NULL DEFAULT '',
                transcripts TEXT DEFAULT '{}',
                result TEXT DEFAULT '',
                model_used TEXT DEFAULT '',
                status TEXT DEFAULT 'success'
            )
        """)
        # 迁移：给旧表加 stt_engine 列（兼容已有数据库）
        try:
            self._conn.execute("ALTER TABLE recordings ADD COLUMN stt_engine TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 列已存在
        try:
            self._conn.execute("ALTER TABLE recordings ADD COLUMN llm_prompt_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE recordings ADD COLUMN llm_completion_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        # FTS5 全文索引 — 毫秒级搜索
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS recordings_fts USING fts5(
                result,
                content='recordings',
                content_rowid='id'
            )
        """)
        # 触发器：自动同步 FTS 索引
        self._conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS recordings_fts_ai AFTER INSERT ON recordings BEGIN
                INSERT INTO recordings_fts(rowid, result) VALUES (new.id, new.result);
            END;
            CREATE TRIGGER IF NOT EXISTS recordings_fts_ad AFTER DELETE ON recordings BEGIN
                INSERT INTO recordings_fts(recordings_fts, rowid, result) VALUES ('delete', old.id, old.result);
            END;
            CREATE TRIGGER IF NOT EXISTS recordings_fts_au AFTER UPDATE ON recordings BEGIN
                INSERT INTO recordings_fts(recordings_fts, rowid, result) VALUES ('delete', old.id, old.result);
                INSERT INTO recordings_fts(rowid, result) VALUES (new.id, new.result);
            END;
        """)
        # ── 每日分析表 ──
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_analyses (
                date TEXT PRIMARY KEY,
                result TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                decision_count INTEGER NOT NULL DEFAULT 0,
                todo_count INTEGER NOT NULL DEFAULT 0,
                main_thread TEXT NOT NULL DEFAULT '',
                framework TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self._conn.commit()
        self._rebuild_fts()

    def add(self, entry: HistoryEntry) -> int:
        """添加一条记录，返回自增 ID"""
        cursor = self._conn.execute(
            "INSERT INTO recordings (duration, engines, mode, mode_name, transcripts, result, model_used, status, stt_engine, llm_prompt_tokens, llm_completion_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.duration,
                json.dumps(entry.engines, ensure_ascii=False),
                entry.mode,
                entry.mode_name,
                json.dumps(entry.transcripts, ensure_ascii=False),
                entry.result,
                entry.model_used,
                entry.status,
                entry.stt_engine,
                entry.llm_prompt_tokens,
                entry.llm_completion_tokens,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_all(self, limit: int = 100, offset: int = 0, order_asc: bool = True) -> list[HistoryEntry]:
        """获取最近的记录列表。order_asc=True=早→晚，False=晚→早"""
        order = "ASC" if order_asc else "DESC"
        rows = self._conn.execute(
            f"SELECT * FROM recordings ORDER BY id {order} LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_today(self) -> list[HistoryEntry]:
        """获取今天的记录（按时间升序）"""
        rows = self._conn.execute(
            "SELECT * FROM recordings WHERE date(created_at) = date('now', 'localtime') "
            "ORDER BY id ASC"
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_by_id(self, entry_id: int) -> Optional[HistoryEntry]:
        """按 ID 获取单条记录"""
        row = self._conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (entry_id,)
        ).fetchone()
        if row:
            return self._row_to_entry(row)
        return None

    def get_by_date(self, date_str: str) -> list[HistoryEntry]:
        """获取指定日期的所有录音记录（按时间升序）"""
        rows = self._conn.execute(
            "SELECT * FROM recordings WHERE date(created_at) = ? ORDER BY id ASC",
            (date_str,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, query: str, limit: int = 50, order_asc: bool = False) -> list[HistoryEntry]:
        """双保险搜索：FTS5 全文索引 + LIKE 兜底，确保不遗漏"""
        order = "ASC" if order_asc else "DESC"
        safe = query.replace('"', '""')

        # 第一层：FTS5 全文索引（毫秒级）
        fts_rows = self._conn.execute(
            f"""SELECT r.* FROM recordings r
               INNER JOIN recordings_fts fts ON r.id = fts.rowid
               WHERE recordings_fts MATCH ?
               ORDER BY r.id {order} LIMIT ?""",
            (f'"{safe}"', limit),
        ).fetchall()

        # 第二层：LIKE 兜底 — 补齐 FTS 可能遗漏的结果
        like_rows = self._conn.execute(
            f"""SELECT * FROM recordings
               WHERE result LIKE ? AND id NOT IN (
                   SELECT rowid FROM recordings_fts WHERE recordings_fts MATCH ?
               )
               ORDER BY id {order} LIMIT ?""",
            (f"%{query}%", f'"{safe}"', max(0, limit - len(fts_rows))),
        ).fetchall()

        all_rows = list(fts_rows) + list(like_rows)
        return [self._row_to_entry(r) for r in all_rows]

    def delete(self, entry_id: int):
        """删除一条记录"""
        self._conn.execute("DELETE FROM recordings WHERE id = ?", (entry_id,))
        self._conn.commit()

    def clear_all(self):
        """清空所有记录"""
        self._conn.execute("DELETE FROM recordings")
        self._conn.commit()

    def count(self) -> int:
        """记录总数"""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM recordings").fetchone()
        return row["cnt"] if row else 0

    def get_monthly_usage(self) -> dict:
        """本月各 STT 引擎的用量统计

        Returns:
            {engine_name: {"calls": int, "total_duration": float}}
            "tencent_sentence" 按次数计费，只看 calls
            "iflytek"/"tencent"/"aliyun" 按时长计费，看 total_duration
        """
        rows = self._conn.execute(
            "SELECT stt_engine, COUNT(*) as cnt, SUM(duration) as dur "
            "FROM recordings "
            "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime') "
            "AND status = 'success' "
            "AND stt_engine != '' "
            "GROUP BY stt_engine"
        ).fetchall()
        usage = {}
        for row in rows:
            engine = row["stt_engine"] or "unknown"
            usage[engine] = {
                "calls": row["cnt"],
                "total_duration": round(row["dur"] or 0, 1),
            }
        return usage

    def get_monthly_llm_tokens(self) -> dict:
        """本月 LLM token 用量统计

        Returns:
            {"total_prompt": int, "total_completion": int, "calls": int}
        """
        row = self._conn.execute(
            "SELECT COALESCE(SUM(llm_prompt_tokens), 0) as p, "
            "COALESCE(SUM(llm_completion_tokens), 0) as c, "
            "COUNT(*) as cnt "
            "FROM recordings "
            "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime') "
            "AND status = 'success'"
        ).fetchone()
        return {
            "total_prompt": row["p"] if row else 0,
            "total_completion": row["c"] if row else 0,
            "calls": row["cnt"] if row else 0,
        }

    def get_monthly_llm_by_model(self) -> dict:
        """本月各 LLM 模型的用量（按 model_used 分组）

        Returns:
            {model_name: {"calls": int, "prompt_tokens": int, "completion_tokens": int}}
        """
        rows = self._conn.execute(
            "SELECT model_used, COUNT(*) as cnt, "
            "COALESCE(SUM(llm_prompt_tokens), 0) as p, "
            "COALESCE(SUM(llm_completion_tokens), 0) as c "
            "FROM recordings "
            "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime') "
            "AND status = 'success' "
            "AND model_used != '' "
            "GROUP BY model_used"
        ).fetchall()
        result = {}
        for row in rows:
            model = row["model_used"] or "unknown"
            result[model] = {
                "calls": row["cnt"],
                "prompt_tokens": row["p"],
                "completion_tokens": row["c"],
            }
        return result

    def _rebuild_fts(self):
        """重建 FTS 索引（首次创建或数据不一致时）"""
        fts_cnt = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM recordings_fts").fetchone()["cnt"]
        real_cnt = self.count()
        if fts_cnt != real_cnt:
            self._conn.execute("INSERT OR IGNORE INTO recordings_fts(rowid, result) "
                               "SELECT id, result FROM recordings")
            self._conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> HistoryEntry:
        try:
            engines = json.loads(row["engines"])
        except (json.JSONDecodeError, TypeError):
            engines = []
        try:
            transcripts = json.loads(row["transcripts"])
        except (json.JSONDecodeError, TypeError):
            transcripts = {}

        return HistoryEntry(
            id=row["id"],
            created_at=row["created_at"],
            duration=row["duration"],
            engines=engines,
            mode=row["mode"],
            mode_name=row["mode_name"],
            transcripts=transcripts,
            result=row["result"],
            model_used=row["model_used"],
            status=row["status"],
            stt_engine=row["stt_engine"] if "stt_engine" in row.keys() else "",
            llm_prompt_tokens=row["llm_prompt_tokens"] if "llm_prompt_tokens" in row.keys() else 0,
            llm_completion_tokens=row["llm_completion_tokens"] if "llm_completion_tokens" in row.keys() else 0,
        )

    # ── 每日分析 ──

    def save_daily_analysis(self, date: str, result: str, tags: list,
                            decision_count: int, todo_count: int,
                            main_thread: str, framework: str):
        """保存或更新某天的分析结果"""
        self._conn.execute(
            """INSERT OR REPLACE INTO daily_analyses
               (date, result, tags, decision_count, todo_count, main_thread, framework, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
            (date, result, json.dumps(tags, ensure_ascii=False),
             decision_count, todo_count, main_thread, framework),
        )
        self._conn.commit()

    def get_daily_analysis(self, date: str) -> Optional[dict]:
        """获取某天的分析结果，无记录返回 None"""
        row = self._conn.execute(
            "SELECT * FROM daily_analyses WHERE date = ?", (date,)
        ).fetchone()
        if not row:
            return None
        try:
            tags = json.loads(row["tags"])
        except (json.JSONDecodeError, TypeError):
            tags = []
        return {
            "date": row["date"],
            "result": row["result"],
            "tags": tags,
            "decision_count": row["decision_count"],
            "todo_count": row["todo_count"],
            "main_thread": row["main_thread"],
            "framework": row["framework"],
            "created_at": row["created_at"],
        }

    def get_all_analysis_dates(self) -> list[str]:
        """返回所有有分析记录的日期（降序）"""
        rows = self._conn.execute(
            "SELECT date FROM daily_analyses ORDER BY date DESC"
        ).fetchall()
        return [r["date"] for r in rows]

    def get_all_recording_dates(self) -> list[str]:
        """返回所有有录音记录的日期（降序，去重）"""
        rows = self._conn.execute(
            "SELECT DISTINCT date(created_at) as d FROM recordings ORDER BY d DESC"
        ).fetchall()
        return [r["d"] for r in rows]

    def delete_daily_analysis(self, date: str):
        """删除某天的分析"""
        self._conn.execute("DELETE FROM daily_analyses WHERE date = ?", (date,))
        self._conn.commit()

    def search_analyses(self, keyword: str) -> list[dict]:
        """按关键词搜索 daily_analyses.result（LIKE 即可，数据量极小）"""
        rows = self._conn.execute(
            "SELECT * FROM daily_analyses WHERE result LIKE ? ORDER BY date DESC",
            (f"%{keyword}%",),
        ).fetchall()
        results = []
        for row in rows:
            try:
                tags = json.loads(row["tags"])
            except (json.JSONDecodeError, TypeError):
                tags = []
            results.append({
                "date": row["date"], "result": row["result"], "tags": tags,
                "decision_count": row["decision_count"],
                "todo_count": row["todo_count"],
                "main_thread": row["main_thread"],
                "framework": row["framework"],
                "created_at": row["created_at"],
            })
        return results

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

    def close(self):
        self._conn.close()
