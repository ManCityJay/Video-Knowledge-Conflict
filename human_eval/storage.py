"""Store one answer per task. QA and judge have no cross-task dependencies."""
from __future__ import annotations
import json
import re
import sqlite3
from contextlib import contextmanager
from .common import LABELS, now

class Store:
    def __init__(self, path, tasks):
        self.path = str(path)
        self.tasks = {t["id"]: t for t in tasks}
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS submissions (
                  annotator TEXT NOT NULL, task_id TEXT NOT NULL, stage TEXT NOT NULL,
                  data TEXT NOT NULL, created_at TEXT NOT NULL,
                  PRIMARY KEY (annotator, task_id, stage));
                CREATE TABLE IF NOT EXISTS drafts (
                  annotator TEXT NOT NULL, task_id TEXT NOT NULL, stage TEXT NOT NULL,
                  data TEXT NOT NULL, updated_at TEXT NOT NULL,
                  PRIMARY KEY (annotator, task_id, stage));
                CREATE TABLE IF NOT EXISTS qa_scores (
                  annotator TEXT NOT NULL, task_id TEXT NOT NULL, answer_hash TEXT NOT NULL,
                  data TEXT NOT NULL, created_at TEXT NOT NULL,
                  PRIMARY KEY (annotator, task_id, answer_hash));
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def check_annotator(annotator):
        if not isinstance(annotator, str) or annotator in (".", "..") or not re.fullmatch(r"[\w.-]{1,64}", annotator):
            raise ValueError("Invalid annotator ID")

    def rename(self, old, new):
        self.check_annotator(old)
        self.check_annotator(new)
        if old == new:
            return
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for table in ("submissions", "drafts", "qa_scores"):
                if db.execute(f"SELECT 1 FROM {table} WHERE annotator=? LIMIT 1", (new,)).fetchone():
                    raise ValueError("该编号已有进度，请使用“使用此编号”切换；不能覆盖或合并。")
            for table in ("submissions", "drafts", "qa_scores"):
                db.execute(f"UPDATE {table} SET annotator=? WHERE annotator=?", (new, old))

    def state(self, annotator):
        self.check_annotator(annotator)
        with self.connection() as db:
            return {(r["task_id"], r["stage"]): json.loads(r["data"])
                    for r in db.execute("SELECT * FROM submissions WHERE annotator=?", (annotator,))}

    def draft(self, annotator, task_id, stage):
        with self.connection() as db:
            row = db.execute("SELECT data FROM drafts WHERE annotator=? AND task_id=? AND stage=?",
                             (annotator, task_id, stage)).fetchone()
        return json.loads(row[0]) if row else {}

    def write(self, annotator, task_id, stage, data, *, draft=False):
        self.check_annotator(annotator)
        task = self.tasks[task_id]
        expected = "answer" if task["kind"] == "qa" else "judge"
        if stage != expected:
            raise ValueError("这里只提交 answer")
        if not isinstance(data, dict) or set(data) != {"answer"}:
            raise ValueError("只需要 answer")
        answer = data["answer"]
        if not isinstance(answer, str) or len(answer) > 50000:
            raise ValueError("Invalid answer")
        answer = answer.strip()
        if task["errors"]:
            raise ValueError("该样本材料缺失，保留在抽样清单中，无需填写答案")
        if not draft:
            if not answer:
                raise ValueError("请填写 answer")
            if task["kind"] == "judge" and answer not in LABELS:
                raise ValueError("请选择一个判定答案")
        clean = {"answer": answer}
        if task["kind"] == "judge":
            # Record the input scope without relabeling historical submissions.
            clean["material_scope"] = "llm_judge_text_only"
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT 1 FROM submissions WHERE annotator=? AND task_id=? AND stage=?",
                                  (annotator, task_id, stage)).fetchone()
            if existing:
                raise ValueError("这条答案已提交")
            values = (annotator, task_id, stage, json.dumps(clean, ensure_ascii=False), now())
            if draft:
                db.execute("INSERT INTO drafts VALUES (?,?,?,?,?) ON CONFLICT(annotator,task_id,stage) "
                           "DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at", values)
            else:
                db.execute("INSERT INTO submissions VALUES (?,?,?,?,?)", values)
                db.execute("DELETE FROM drafts WHERE annotator=? AND task_id=? AND stage=?",
                           (annotator, task_id, stage))
        return clean
