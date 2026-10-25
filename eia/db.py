"""SQLite persistence. Tables are derived from the pydantic schema; list/dict fields are stored as JSON.

calc_inputs(calc_id, fact_id) makes every calculation's input facts queryable with plain SQL.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Type, TypeVar

from pydantic import BaseModel

from .schema import (Calculation, Company, Fact, Hypothesis, Relationship, ResearchEvent, Run, Source)

T = TypeVar("T", bound=BaseModel)

TABLES: dict[str, Type[BaseModel]] = {
    "sources": Source,
    "facts": Fact,
    "calculations": Calculation,
    "hypotheses": Hypothesis,
    "relationships": Relationship,
    "events": ResearchEvent,
}


def _sql_type(annotation: Any) -> str:
    s = str(annotation)
    if "float" in s:
        return "REAL"
    if "int" in s and "list" not in s:
        return "INTEGER"
    if "bool" in s:
        return "INTEGER"
    return "TEXT"


def _encode(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    if isinstance(v, BaseModel):
        return v.model_dump_json()
    if isinstance(v, bool):
        return int(v)
    return v


class Store:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY")
        self._init()

    # -- schema -----------------------------------------------------------------------
    def _init(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, company_name TEXT, company_json TEXT, mode TEXT, started_at TEXT,
                finished_at TEXT, status TEXT, settings TEXT, rounds_completed INTEGER)""")
            for table, model in TABLES.items():
                cols = []
                for name, f in model.model_fields.items():
                    t = _sql_type(f.annotation)
                    cols.append(f"{name} {t}" + (" PRIMARY KEY" if name == "id" else ""))
                cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)})")
                cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_run ON {table}(run_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS calc_inputs (
                calc_id TEXT, fact_id TEXT, run_id TEXT, PRIMARY KEY (calc_id, fact_id))""")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_facts_metric ON facts(run_id, metric)")
            cur.execute("""CREATE TABLE IF NOT EXISTS doc_pages (
                run_id TEXT, source_id TEXT, page INTEGER, text TEXT, PRIMARY KEY (source_id, page))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS peer_profiles (
                run_id TEXT, symbol TEXT, data TEXT, PRIMARY KEY (run_id, symbol))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS module_results (
                run_id TEXT, key TEXT, round INTEGER, data TEXT, PRIMARY KEY (run_id, key))""")
            self.conn.commit()

    # -- runs ---------------------------------------------------------------------------
    def save_run(self, run: Run) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
                (run.id, run.company.name, run.company.model_dump_json(), run.mode, run.started_at,
                 run.finished_at, run.status, json.dumps(run.settings, default=str), run.rounds_completed))
            self.conn.commit()

    def get_run(self, run_id: str) -> Optional[Run]:
        with self._lock:
            r = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._row_to_run(r) if r else None

    def list_runs(self) -> list[Run]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()
        return [self._row_to_run(r) for r in rows]

    @staticmethod
    def _row_to_run(r: sqlite3.Row) -> Run:
        return Run(id=r["id"], company=Company.model_validate_json(r["company_json"]), mode=r["mode"],
                   started_at=r["started_at"], finished_at=r["finished_at"], status=r["status"],
                   settings=json.loads(r["settings"] or "{}"), rounds_completed=r["rounds_completed"] or 0)

    def delete_run(self, run_id: str) -> None:
        with self._lock:
            for t in list(TABLES) + ["calc_inputs", "module_results", "doc_pages"]:
                self.conn.execute(f"DELETE FROM {t} WHERE run_id=?", (run_id,))
            self.conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
            self.conn.commit()

    # -- generic upsert / fetch -----------------------------------------------------------
    def _write(self, obj: BaseModel) -> None:
        table = next(t for t, m in TABLES.items() if isinstance(obj, m))
        cols = list(type(obj).model_fields)
        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [_encode(getattr(obj, c)) for c in cols])
        if isinstance(obj, Calculation):
            self.conn.execute("DELETE FROM calc_inputs WHERE calc_id=?", (obj.id,))
            self.conn.executemany("INSERT OR IGNORE INTO calc_inputs VALUES (?,?,?)",
                                  [(obj.id, fid, obj.run_id) for fid in obj.input_fact_ids])

    def upsert(self, obj: BaseModel) -> None:
        with self._lock:
            self._write(obj)
            self.conn.commit()

    def upsert_many(self, objs: Iterable[BaseModel]) -> None:
        """Single transaction for bulk writes."""
        with self._lock:
            for o in objs:
                self._write(o)
            self.conn.commit()

    def delete_hypotheses(self, run_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM hypotheses WHERE run_id=?", (run_id,))
            self.conn.commit()

    def _load(self, table: str, where: str = "", params: tuple = ()) -> list[BaseModel]:
        model = TABLES[table]
        with self._lock:  # research runs in a background thread; reads and writes share one connection
            rows = self.conn.execute(f"SELECT * FROM {table} {where}", params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for name, f in model.model_fields.items():
                ann = str(f.annotation)
                if (ann.startswith("list") or ann.startswith("dict")) and isinstance(d.get(name), str):
                    d[name] = json.loads(d[name])
                if "bool" in ann and d.get(name) is not None:
                    d[name] = bool(d[name])
            out.append(model.model_validate(d))
        return out

    def sources(self, run_id: str) -> list[Source]:
        return self._load("sources", "WHERE run_id=? ORDER BY round, retrieved_at", (run_id,))  # type: ignore

    def facts(self, run_id: str, metric: Optional[str] = None) -> list[Fact]:
        if metric:
            return self._load("facts", "WHERE run_id=? AND metric=?", (run_id, metric))  # type: ignore
        return self._load("facts", "WHERE run_id=?", (run_id,))  # type: ignore

    def calculations(self, run_id: str) -> list[Calculation]:
        return self._load("calculations", "WHERE run_id=?", (run_id,))  # type: ignore

    def hypotheses(self, run_id: str) -> list[Hypothesis]:
        return self._load("hypotheses", "WHERE run_id=? ORDER BY score DESC", (run_id,))  # type: ignore

    def relationships(self, run_id: str) -> list[Relationship]:
        return self._load("relationships", "WHERE run_id=?", (run_id,))  # type: ignore

    def events(self, run_id: str) -> list[ResearchEvent]:
        return self._load("events", "WHERE run_id=? ORDER BY ts, rowid", (run_id,))  # type: ignore

    def calc_input_facts(self, calc_id: str) -> list[str]:
        with self._lock:
            return [r[0] for r in self.conn.execute("SELECT fact_id FROM calc_inputs WHERE calc_id=?", (calc_id,))]

    def clear_derived(self, run_id: str) -> None:
        """Remove calculations and analysis edges before modules re-run (facts/sources are kept)."""
        with self._lock:
            self.conn.execute("DELETE FROM calculations WHERE run_id=?", (run_id,))
            self.conn.execute("DELETE FROM calc_inputs WHERE run_id=?", (run_id,))
            self.conn.execute("DELETE FROM relationships WHERE run_id=? AND relation NOT IN ('extracted_from')",
                              (run_id,))
            self.conn.commit()

    # -- module results (summaries/rows for the UI; series are rebuilt from facts) -----------------
    def save_module_results(self, run_id: str, results: dict, round_no: int) -> None:
        with self._lock:
            for key, r in results.items():
                data = {"key": r.key, "name": r.name, "status": r.status, "summary": r.summary, "rows": r.rows,
                        "missing": r.missing, "notes": list(dict.fromkeys(r.notes)),
                        "calc_ids": [c.id for c in r.calcs], "signal_keys": [s.key for s in r.signals]}
                self.conn.execute("INSERT OR REPLACE INTO module_results VALUES (?,?,?,?)",
                                  (run_id, key, round_no, json.dumps(data, default=str)))
            self.conn.commit()

    def module_results(self, run_id: str) -> dict[str, dict]:
        with self._lock:
            rows = self.conn.execute("SELECT key, data FROM module_results WHERE run_id=?", (run_id,)).fetchall()
        return {r["key"]: json.loads(r["data"]) for r in rows}

    # -- peer comparison ---------------------------------------------------------------------------------
    def save_peers(self, run_id: str, peers: list) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM peer_profiles WHERE run_id=?", (run_id,))
            self.conn.executemany("INSERT OR REPLACE INTO peer_profiles VALUES (?,?,?)",
                                  [(run_id, p.symbol, json.dumps(p.as_dict(), default=str)) for p in peers])
            self.conn.commit()

    def peers(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT data FROM peer_profiles WHERE run_id=? ORDER BY rowid", (run_id,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    # -- document text (powers the in-app document viewer for every source, online or not) -----------
    def save_pages(self, run_id: str, source_id: str, pages: list[tuple[int, str]]) -> None:
        with self._lock:
            self.conn.executemany("INSERT OR REPLACE INTO doc_pages VALUES (?,?,?,?)",
                                  [(run_id, source_id, n, t[:60000]) for n, t in pages])
            self.conn.commit()

    def pages(self, source_id: str) -> list[tuple[int, str]]:
        with self._lock:
            return [(r[0], r[1]) for r in self.conn.execute(
                "SELECT page, text FROM doc_pages WHERE source_id=? ORDER BY page", (source_id,))]
