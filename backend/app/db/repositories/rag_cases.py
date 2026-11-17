from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.db.connection import connect
from app.db.schema import migrate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row(r) -> dict[str, Any]:
    d = dict(r)
    d["tags"] = json.loads(d.pop("tags_json") or "[]")
    return d


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(query: str) -> list[str]:
    """Split query into search tokens: ascii words + CJK bigrams.

    E.g. "霓虹雨夜 cyberpunk 街道" -> ["霓虹","虹雨","雨夜","cyberpunk","街道"].
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    tokens: list[str] = []
    # contiguous ascii/digit words
    for w in re.findall(r"[a-z0-9]+", q):
        tokens.append(w)
    # cjk bigrams over the whole stripped string
    cjk = "".join(_CJK_RE.findall(q))
    if len(cjk) <= 2:
        if cjk:
            tokens.append(cjk)
    else:
        tokens.extend(cjk[i : i + 2] for i in range(len(cjk) - 1))
    seen: list[str] = []
    for t in tokens:
        if t and t not in seen:
            seen.append(t)
    return seen


class RagCaseRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        conn = connect(self.db_path)
        migrate(conn)
        conn.close()

    def _conn(self):
        return connect(self.db_path)

    def create(
        self,
        *,
        title: str,
        type: str,
        description: str = "",
        style: str = "",
        tags: list | None = None,
        prompt_en: str = "",
        negative_prompt: str = "",
        source_project_id: str | None = None,
        source_ref: str | None = None,
        rating: float = 0,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        cid = case_id or f"case_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO rag_cases
                (id, title, type, style, description, tags_json, prompt_en, negative_prompt,
                 source_project_id, source_ref, rating, usage_count, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cid,
                    title,
                    type,
                    style,
                    description,
                    json.dumps(tags or [], ensure_ascii=False),
                    prompt_en,
                    negative_prompt,
                    source_project_id,
                    source_ref,
                    rating,
                    0,
                    now,
                    now,
                ),
            )
            conn.commit()
        got = self.get(cid)
        assert got is not None
        return got

    def get(self, case_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM rag_cases WHERE id=?", (case_id,)
            ).fetchone()
        return _row(row) if row else None

    def list(
        self,
        *,
        type: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM rag_cases WHERE 1=1"
        args: list[Any] = []
        if type:
            q += " AND type=?"
            args.append(type)
        if keyword:
            q += " AND (title LIKE ? OR description LIKE ?)"
            like = f"%{keyword}%"
            args.extend([like, like])
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        with self._conn() as conn:
            rows = conn.execute(q, args).fetchall()
        return [_row(r) for r in rows]

    def count(self, *, type: str | None = None) -> int:
        q = "SELECT COUNT(*) AS c FROM rag_cases"
        args: list[Any] = []
        if type:
            q += " WHERE type=?"
            args.append(type)
        with self._conn() as conn:
            row = conn.execute(q, args).fetchone()
        return int(row["c"])

    def search(
        self,
        *,
        query: str,
        type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Keyword search across title/description/prompt_en.

        Tokenizes the query (whitespace words + CJK bigrams), matches hits in
        Python, weights by field (title > description > prompt_en) and rating.
        Used as a vector-free fallback when no embedder is available.
        Returns repository rows (no similarity field).
        """
        tokens = _tokenize(query)
        if not tokens:
            return []
        rows = self.list(type=type, limit=100000)
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for r in rows:
            title = (r.get("title") or "").lower()
            desc = (r.get("description") or "").lower()
            prompt = (r.get("prompt_en") or "").lower()
            score = 0
            matched = 0
            for t in tokens:
                hit = False
                if t in title:
                    score += 5
                    hit = True
                if t in desc:
                    score += 2
                    hit = True
                if t in prompt:
                    score += 1
                    hit = True
                if hit:
                    matched += 1
            if matched == 0:
                continue
            # require at least half the tokens to match, else it is noise
            if matched < max(1, len(tokens) // 2):
                continue
            score += (r.get("rating") or 0) * 2
            scored.append((score, r["id"], r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[2] for item in scored[:limit]]

    def delete(self, case_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM rag_cases WHERE id=?", (case_id,))
            conn.commit()
            return cur.rowcount > 0

    def increment_usage(self, case_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE rag_cases SET usage_count = usage_count + 1, updated_at=? WHERE id=?",
                (_now(), case_id),
            )
            conn.commit()
