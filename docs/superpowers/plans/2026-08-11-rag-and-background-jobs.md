# RAG + 工作台后台任务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 工作台生成改为后端 Job 异步执行（切页不断、顶栏+常驻条可见、完成 toast）；RAG 用 Chroma+bge-m3 真实检索、注入扩写/润色，并支持一键入库。

**Architecture:** SQLite `jobs` + 进程内 JobWorker（LLM 串行）；出图继续 AssetQueue 并关联 Job；监控 `tasks` 改读 jobs。RAG：`rag_cases` 元数据 + `{MODELHUB_ROOT}/rag/chroma`；expand/polish 前 retrieve 注入；入库走 `/api/rag/ingest`。

**Tech Stack:** FastAPI、SQLite、threading Queue、pytest、chromadb、sentence-transformers（bge-m3）、React、Ant Design

**Spec:** `docs/superpowers/specs/2026-08-11-rag-and-background-jobs-design.md`

**强制顺序:** Phase J（后台 Job）→ Phase R（RAG）。每阶段可独立验收。

工作目录：后端 `backend/`；前端 `frontend/`。PowerShell 提交：`git commit -m "..."`（勿用 bash heredoc）。

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/db/schema.py` | 迁移 `002_jobs`、`003_rag_cases` |
| `backend/app/db/repositories/jobs.py` | jobs CRUD / list active / fail_stale |
| `backend/app/db/repositories/rag_cases.py` | rag_cases CRUD |
| `backend/app/services/job_queue.py` | 内存队列 + JobWorker 线程 |
| `backend/app/services/job_handlers.py` | 按 type 执行 expand/analyze/polish/资产桥接 |
| `backend/app/api/jobs.py` | POST/GET/cancel |
| `backend/app/services/runtime.py` | 挂载 `job_queue`；startup 对账 |
| `backend/app/services/monitor_snapshot.py` | tasks 来自 jobs |
| `backend/app/services/asset_queue.py` | 完成/失败时回调更新关联 Job |
| `backend/app/api/assets.py` / `storyboard.py` | generate 时创建关联 Job |
| `backend/app/core/settings.py` | rag_chroma_dir、embed_model_path |
| `backend/app/services/rag_embedder.py` | bge-m3 懒加载 encode |
| `backend/app/services/rag_store.py` | Chroma upsert/query/delete |
| `backend/app/services/rag_retrieve.py` | top_k 检索 + 格式化注入文本 |
| `backend/app/api/rag.py` | 真实 stats/cases/search/ingest |
| `backend/app/services/script_expand.py` / `cinematic_polish.py` | 可选注入 RAG context |
| `frontend/src/services/api.js` | `jobsApi`、`ragApi` |
| `frontend/src/hooks/useJobTracker.js` | 轮询 active + 完成 notification |
| `frontend/src/components/ActiveJobsBar.jsx` | 常驻进行中条 |
| `frontend/src/layouts/MainLayout.jsx` | 挂载 Bar + tracker；tasks 已来自 snapshot |
| `frontend/src/pages/workbench/ScriptWorkshop.jsx` | 改走 jobs |
| `frontend/src/pages/workbench/*` | 润色/出图改走 jobs 或依赖已有 generate+Job |
| `frontend/src/pages/admin/RAGKnowledge.jsx` | 接真实 API |

---

# Phase J — 后台 Job

### Task 1: jobs 表迁移 + JobRepository

**Files:**
- Modify: `backend/app/db/schema.py`
- Create: `backend/app/db/repositories/jobs.py`
- Create: `backend/tests/test_job_repository.py`

- [ ] **Step 1: 在 `MIGRATE_SQL` 追加迁移**

```python
(
    "002_jobs",
    """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  project_id TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  link_path TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
""",
),
```

- [ ] **Step 2: 写失败测试** `backend/tests/test_job_repository.py`

```python
import json
from pathlib import Path

from app.db.connection import connect
from app.db.schema import migrate
from app.db.repositories.jobs import JobRepository


def test_create_and_list_active(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(lambda: connect(db))
    j = repo.create(
        type="script_expand",
        project_id="p1",
        title="剧本扩写",
        payload={"text": "hi"},
        link_path="/workbench/p1/script",
    )
    assert j["status"] == "queued"
    assert j["id"]
    active = repo.list_active(limit=10)
    assert len(active) == 1
    assert active[0]["id"] == j["id"]


def test_fail_stale_marks_queued_and_running(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(lambda: connect(db))
    a = repo.create(type="script_expand", project_id="p1", title="a", payload={})
    b = repo.create(type="script_expand", project_id="p1", title="b", payload={})
    repo.update(b["id"], status="running", progress=10)
    n = repo.fail_stale(error="server_restarted")
    assert n == 2
    assert repo.get(a["id"])["status"] == "failed"
    assert repo.get(b["id"])["error"] == "server_restarted"
```

对齐现有测试写法：`migrate(connect(db))`（`app.db.schema.migrate`），勿自创 `migrate_db`。

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend; python -m pytest tests/test_job_repository.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 `JobRepository`**

```python
# backend/app/db/repositories/jobs.py
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Callable
import sqlite3


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    d["result"] = json.loads(d.pop("result_json") or "{}")
    return d


class JobRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect

    def create(
        self,
        *,
        type: str,
        project_id: str | None,
        title: str,
        payload: dict,
        link_path: str | None = None,
    ) -> dict[str, Any]:
        jid = f"job_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs
                (id, type, project_id, status, progress, title, payload_json, result_json, error, link_path, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    jid,
                    type,
                    project_id,
                    "queued",
                    0,
                    title,
                    json.dumps(payload, ensure_ascii=False),
                    "{}",
                    None,
                    link_path,
                    now,
                ),
            )
            conn.commit()
        return self.get(jid)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row(row) if row else None

    def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "status",
            "progress",
            "title",
            "error",
            "link_path",
            "started_at",
            "finished_at",
        }
        cols = []
        vals = []
        if "payload" in fields:
            cols.append("payload_json=?")
            vals.append(json.dumps(fields.pop("payload"), ensure_ascii=False))
        if "result" in fields:
            cols.append("result_json=?")
            vals.append(json.dumps(fields.pop("result"), ensure_ascii=False))
        for k, v in fields.items():
            if k not in allowed:
                continue
            cols.append(f"{k}=?")
            vals.append(v)
        if not cols:
            return self.get(job_id)
        vals.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(cols)} WHERE id=?", vals)
            conn.commit()
        return self.get(job_id)

    def list_active(self, *, project_id: str | None = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM jobs WHERE status IN ('queued','running')"
        args: list[Any] = []
        if project_id:
            q += " AND project_id=?"
            args.append(project_id)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(q, args).fetchall()
        return [_row(r) for r in rows]

    def list_recent_failed(self, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status='failed' ORDER BY finished_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row(r) for r in rows]

    def fail_stale(self, *, error: str = "server_restarted") -> int:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE jobs SET status='failed', error=?, finished_at=?
                   WHERE status IN ('queued','running')""",
                (error, now),
            )
            conn.commit()
            return cur.rowcount
```

对齐 `connection.py` 的 `connect`/`migrate` 实际函数名；测试里同样调用。

- [ ] **Step 5: 跑测试通过**

Run: `cd backend; python -m pytest tests/test_job_repository.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/schema.py backend/app/db/repositories/jobs.py backend/tests/test_job_repository.py
git commit -m "feat(jobs): add jobs table and repository"
```

---

### Task 2: JobQueue worker 骨架 + 启动对账

**Files:**
- Create: `backend/app/services/job_queue.py`
- Create: `backend/app/services/job_handlers.py`（先放 stub `dispatch`）
- Modify: `backend/app/services/runtime.py`
- Modify: `backend/app/main.py`（startup/shutdown）
- Create: `backend/tests/test_job_queue.py`

- [ ] **Step 1: 写测试**

```python
import time
from pathlib import Path
from unittest.mock import MagicMock

from app.db.connection import connect
from app.db.schema import migrate
from app.db.repositories.jobs import JobRepository
from app.services.job_queue import JobQueue


def test_worker_runs_handler_and_completes(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(lambda: connect(db))
    calls = []

    def handler(job):
        calls.append(job["id"])
        return {"ok": True}

    q = JobQueue(repo=repo, dispatch=handler)
    q.start()
    job = repo.create(type="script_expand", project_id="p1", title="t", payload={})
    q.enqueue(job["id"])
    for _ in range(50):
        j = repo.get(job["id"])
        if j["status"] == "completed":
            break
        time.sleep(0.05)
    q.stop()
    assert repo.get(job["id"])["status"] == "completed"
    assert calls == [job["id"]]


def test_handler_error_marks_failed(tmp_path: Path):
    db = tmp_path / "t.db"
    migrate(connect(db))
    repo = JobRepository(lambda: connect(db))

    def handler(job):
        raise RuntimeError("boom")

    q = JobQueue(repo=repo, dispatch=handler)
    q.start()
    job = repo.create(type="script_expand", project_id="p1", title="t", payload={})
    q.enqueue(job["id"])
    for _ in range(50):
        if repo.get(job["id"])["status"] == "failed":
            break
        time.sleep(0.05)
    q.stop()
    assert "boom" in (repo.get(job["id"])["error"] or "")
```

- [ ] **Step 2: 实现 `JobQueue`**

```python
# backend/app/services/job_queue.py
from __future__ import annotations

import queue
import threading
from datetime import datetime
from typing import Any, Callable

from app.db.repositories.jobs import JobRepository


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class JobQueue:
    def __init__(
        self,
        *,
        repo: JobRepository,
        dispatch: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> None:
        self.repo = repo
        self.dispatch = dispatch
        self._q: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cancel: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._q.put("")
        if self._thread:
            self._thread.join(timeout=5)

    def enqueue(self, job_id: str) -> None:
        self._q.put(job_id)

    def request_cancel(self, job_id: str) -> None:
        self._cancel.add(job_id)

    def bootstrap_fail_stale(self) -> int:
        return self.repo.fail_stale(error="server_restarted")

    def _run(self) -> None:
        while not self._stop.is_set():
            job_id = self._q.get()
            if not job_id:
                continue
            self._process(job_id)

    def _process(self, job_id: str) -> None:
        job = self.repo.get(job_id)
        if not job or job["status"] not in ("queued", "running"):
            return
        if job_id in self._cancel:
            self._cancel.discard(job_id)
            self.repo.update(
                job_id, status="cancelled", finished_at=_now(), error="cancelled"
            )
            return
        self.repo.update(job_id, status="running", progress=5, started_at=_now())
        try:
            result = self.dispatch(self.repo.get(job_id)) or {}
            if job_id in self._cancel:
                self._cancel.discard(job_id)
                self.repo.update(
                    job_id, status="cancelled", finished_at=_now(), error="cancelled"
                )
                return
            self.repo.update(
                job_id,
                status="completed",
                progress=100,
                result=result,
                finished_at=_now(),
            )
        except Exception as e:
            self.repo.update(
                job_id,
                status="failed",
                error=str(e)[:500],
                finished_at=_now(),
            )
```

- [ ] **Step 3: stub `dispatch`**

```python
# backend/app/services/job_handlers.py
from __future__ import annotations
from typing import Any

def dispatch_job(job: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError(f"unhandled job type: {job.get('type')}")
```

- [ ] **Step 4: `runtime.py` 增加 job_repo + job_queue；`main.py` lifespan 调用 `bootstrap_fail_stale` + `job_queue.start()`，shutdown `stop()`。并对 `assets`/`frames` 中 `generating` 标 failed（复用 AssetStore / Frame repo 的 update 批量或 list_by_status）。**

```python
# runtime.py 末尾概念 — JobRepository 与 SceneRepository 一样内部用 connect()，或注入 lambda: connect()
from app.db.repositories.jobs import JobRepository
from app.services.job_handlers import dispatch_job
from app.services.job_queue import JobQueue

job_repo = JobRepository(connect)
job_queue = JobQueue(repo=job_repo, dispatch=dispatch_job)
```

（`connect` 来自 `app.db.connection`；无 `get_connection` 别名。）

- [ ] **Step 5: pytest 通过后 Commit**

```bash
git commit -m "feat(jobs): add in-process job worker and startup reconcile"
```

---

### Task 3: Jobs HTTP API

**Files:**
- Create: `backend/app/api/jobs.py`
- Modify: `backend/app/main.py`（`include_router`）
- Create: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: API**

```python
# backend/app/api/jobs.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from app.services.runtime import job_queue, job_repo

router = APIRouter()

TITLE_BY_TYPE = {
    "script_expand": "剧本扩写",
    "script_analyze": "剧本解析",
    "prompt_polish": "电影感润色",
    "prompt_polish_batch": "本集全部润色",
    "asset_generate": "资产生成",
    "storyboard_generate": "分镜出图",
}

LINK_BY_TYPE = {
    "script_expand": "/workbench/{pid}/script",
    "script_analyze": "/workbench/{pid}/script",
    "prompt_polish": "/workbench/{pid}/script",
    "prompt_polish_batch": "/workbench/{pid}/script",
    "asset_generate": "/workbench/{pid}/assets",
    "storyboard_generate": "/workbench/{pid}/storyboard",
}


class CreateJobBody(BaseModel):
    type: str
    project_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("")
def create_job(body: CreateJobBody):
    if body.type not in TITLE_BY_TYPE:
        raise HTTPException(400, f"unknown type: {body.type}")
    link = LINK_BY_TYPE[body.type].format(pid=body.project_id)
    job = job_repo.create(
        type=body.type,
        project_id=body.project_id,
        title=TITLE_BY_TYPE[body.type],
        payload=body.payload,
        link_path=link,
    )
    # 出图类：handler 内 enqueue AssetQueue；此处一律入 JobQueue
    job_queue.enqueue(job["id"])
    return job


@router.get("")
def list_jobs(status: str = "active", project_id: Optional[str] = None, limit: int = 50):
    if status == "active":
        return job_repo.list_active(project_id=project_id, limit=limit)
    # status=all → 简单：active + 近期 failed（够用）
    active = job_repo.list_active(project_id=project_id, limit=limit)
    failed = job_repo.list_recent_failed(limit=limit)
    if project_id:
        failed = [j for j in failed if j.get("project_id") == project_id]
    return active + failed


@router.get("/{job_id}")
def get_job(job_id: str):
    job = job_repo.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    job = job_repo.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] == "queued":
        job_repo.update(job_id, status="cancelled", error="cancelled")
        return job_repo.get(job_id)
    if job["status"] == "running":
        job_queue.request_cancel(job_id)
        return {"ok": True, "message": "cancel requested"}
    return job
```

`main.py`: `app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])`

- [ ] **Step 2: API 测试用 TestClient；mock dispatch 立即返回。跑通 create→get active。**

- [ ] **Step 3: Commit** `feat(jobs): add /api/jobs endpoints`

---

### Task 4: script_expand / script_analyze handlers

**Files:**
- Modify: `backend/app/services/job_handlers.py`
- Modify: `backend/app/api/scripts.py`（保持同步函数供 handler 调用，抽 `_run_expand`）
- Create: `backend/tests/test_job_handlers_script.py`

- [ ] **Step 1: 从 `scripts.py` 抽出可调用函数**（示例）

```python
def run_expand_persist(project_id: str, text: str, style: str) -> dict:
    raw = _expand_service().expand(text=text, style=style)
    scenes = _persist_scenes(project_id, raw)
    return _stats(scenes)
```

analyze 同理。

- [ ] **Step 2: `dispatch_job`**

```python
def dispatch_job(job: dict) -> dict:
    t = job["type"]
    p = job.get("payload") or {}
    pid = job["project_id"]
    if t == "script_expand":
        from app.api.scripts import run_expand_persist
        from app.services.runtime import job_repo
        job_repo.update(job["id"], progress=30)
        stats = run_expand_persist(pid, p.get("text") or "", p.get("style") or "")
        return {"scene_count": stats["scene_count"]}
    if t == "script_analyze":
        from app.api.scripts import run_analyze_persist
        stats = run_analyze_persist(pid, p.get("text") or "", p.get("style") or "")
        return {"scene_count": stats["scene_count"]}
    # ... 其他 type 后续 Task
    raise NotImplementedError(t)
```

- [ ] **Step 3: 集成测试**（可 mock ScriptExpandService）创建 job → completed → scenes 表有行。

- [ ] **Step 4: Commit** `feat(jobs): handle script expand/analyze`

---

### Task 5: prompt_polish / batch handlers

**Files:**
- Modify: `backend/app/services/job_handlers.py`
- Modify: `backend/app/api/prompts.py`（导出 `run_polish(request_dict) -> dict`）
- 写回：handler 内按 payload.`target`（scene|asset|frame）+ id 更新对应 repo（与现前端 apply 逻辑一致：可把「润色+写回」放进 payload.`apply=true`）

**payload 约定:**
```json
{
  "stage": "script_scene",
  "text_cn": "...",
  "text_en": "",
  "context": {},
  "target": "scene",
  "target_id": "scn_xxx",
  "apply": true
}
```

batch:
```json
{ "items": [ { /* 同上单条 */ } ] }
```

- [ ] **Step 1: 实现单条与 batch；progress 按 index 更新。**
- [ ] **Step 2: 测试 mock polish 返回固定 prompt_en，断言 scene 行更新。**
- [ ] **Step 3: Commit** `feat(jobs): handle cinematic polish jobs`

---

### Task 6: 资产生成 / 分镜出图关联 Job

**Files:**
- Modify: `backend/app/api/assets.py`（generate 后 `job_repo.create` type=`asset_generate`，payload 含 `asset_id`，status 可先 `running`，`job_queue` **不要**再走 LLM handler 重入队出图——改：`dispatch` 对 `asset_generate` 只 `queue.enqueue` 并返回特殊标记 **或** create 时不入 JobQueue、由 AssetQueue 回调完成 Job）

**推荐（写死）:**
1. `generate_asset`：创建资产 generating → `job = job_repo.create(..., status 默认 queued)` → 立即 `job_repo.update(running)` → `queue.enqueue` → **不** `job_queue.enqueue`。  
2. `AssetQueue._process` 结束时：查 `payload.asset_id == asset_id` 且 status running 的 job，标 completed/failed。

```python
# asset_queue.py 成功分支末尾
def _complete_linked_job(self, project_id, asset_id, ok: bool, error: str | None):
    from app.services.runtime import job_repo
    # repo 增加 find_running_by_asset(asset_id) 或扫描 list_active
    ...
```

分镜 `storyboard_generate` 同理（payload.`frame_id` / `asset_id`）。

- [ ] **Step 1: 实现桥接 + 单测**（mock comfy 成功路径更新 job）。
- [ ] **Step 2: Commit** `feat(jobs): link asset/storyboard generate to jobs`

---

### Task 7: monitor snapshot 改读 jobs

**Files:**
- Modify: `backend/app/services/monitor_snapshot.py`
- Modify: `backend/tests/test_monitor_api.py`（fixtures）

```python
def _job_task_row(j: dict) -> dict:
    return {
        "id": j["id"],
        "project_id": j.get("project_id") or "",
        "name": j.get("title") or j["id"],
        "type": j.get("type") or "",
        "status": j["status"],
        "model": "",
        "error": j.get("error"),
        "created_at": j.get("created_at") or "",
        "link_path": j.get("link_path"),
        "progress": j.get("progress") or 0,
    }

# tasks.generating ← list_active
# tasks.failed_recent ← list_recent_failed
# badge_count = len(active) + len(failed)  # 与现 MainLayout 语义对齐；若现网仅计 generating，则 badge=len(active)
```

与现前端约定：优先 **badge = active 数量**；failed 仍在列表展示。实现时读 `MainLayout.jsx` 保持兼容字段名 `generating`/`failed_recent`/`badge_count`。

- [ ] **Step 1: 改 snapshot + 修测试**
- [ ] **Step 2: Commit** `feat(monitor): surface jobs in snapshot tasks`

---

### Task 8: 前端 jobsApi + useJobTracker + ActiveJobsBar

**Files:**
- Modify: `frontend/src/services/api.js`
- Create: `frontend/src/hooks/useJobTracker.js`
- Create: `frontend/src/components/ActiveJobsBar.jsx`
- Modify: `frontend/src/layouts/MainLayout.jsx`

- [ ] **Step 1: api**

```javascript
export const jobsApi = {
  create(body) {
    return request('/api/jobs', { method: 'POST', body: JSON.stringify(body) })
  },
  list(params = {}) {
    const q = new URLSearchParams(params).toString()
    return request(`/api/jobs?${q}`)
  },
  get(id) {
    return request(`/api/jobs/${id}`)
  },
  cancel(id) {
    return request(`/api/jobs/${id}/cancel`, { method: 'POST' })
  },
}
```

- [ ] **Step 2: `useJobTracker`**

```javascript
import { useEffect, useRef, useState } from 'react'
import { notification } from 'antd'
import { useNavigate } from 'react-router-dom'
import { jobsApi } from '../services/api.js'

export function useJobTracker(pollMs = 3000) {
  const [active, setActive] = useState([])
  const known = useRef(new Map()) // id -> status
  const navigate = useNavigate()

  useEffect(() => {
    let dead = false
    const tick = async () => {
      try {
        const list = await jobsApi.list({ status: 'active', limit: 50 })
        if (dead) return
        const ids = new Set(list.map((j) => j.id))
        // 检测消失的 id → 拉详情看 completed/failed
        for (const [id, prev] of known.current.entries()) {
          if (!ids.has(id) && (prev === 'queued' || prev === 'running')) {
            try {
              const j = await jobsApi.get(id)
              if (j.status === 'completed') {
                notification.success({
                  message: `${j.title || '任务'}已完成`,
                  description: '点击查看',
                  btn: j.link_path ? undefined : undefined,
                  onClick: () => j.link_path && navigate(j.link_path),
                })
              } else if (j.status === 'failed') {
                notification.error({
                  message: `${j.title || '任务'}失败`,
                  description: j.error || '',
                })
              }
            } catch (_) {}
          }
        }
        const next = new Map()
        for (const j of list) next.set(j.id, j.status)
        known.current = next
        setActive(list)
      } catch (_) {}
    }
    tick()
    const t = setInterval(tick, pollMs)
    return () => {
      dead = true
      clearInterval(t)
    }
  }, [pollMs, navigate])

  return { activeJobs: active }
}
```

- [ ] **Step 3: `ActiveJobsBar`** — 无 active 返回 null；有则顶栏下一条：`进行中：{title} {progress}%`，点击 `navigate(link_path)`。

- [ ] **Step 4: MainLayout** 在 `<Content>` 内最上方渲染 `<ActiveJobsBar />`，并调用 `useJobTracker()`（或把 tracker 放在 Bar 内）。

- [ ] **Step 5: Commit** `feat(frontend): active jobs bar and completion toasts`

---

### Task 9: ScriptWorkshop 改异步 Job

**Files:**
- Modify: `frontend/src/pages/workbench/ScriptWorkshop.jsx`

- [ ] **Step 1: `handleExpand` / `handleParse`**

```javascript
const submit = async (type) => {
  // Modal.confirm 若已有同 type active（从 props/context 或 jobsApi.list）
  await jobsApi.create({
    type, // script_expand | script_analyze
    project_id: resolvedProjectId,
    payload: { text: storyIdea, style: selectedStyles.join(',') || '' },
  })
  message.success('已提交后台生成，可切换页面等待')
  setIsGenerating(false)
}
```

- [ ] **Step 2: 监听本项目 job 完成**：在 `useJobTracker` 外对本页 `useEffect` 轮询 `scriptsApi.listScenes`，或在 notification 后若仍在本页则 refetch。最简：`setInterval` 当 `scriptParsed` 或 always 每 5s listScenes（仅当有本项目 active script job 时）。

- [ ] **Step 3: 电影感拆解按钮改为 `jobsApi.create({ type:'prompt_polish', payload:{... apply:true }})`；本集全部 → `prompt_polish_batch`。**

- [ ] **Step 4: 手工验收清单写进 commit message 即可。Commit** `feat(script): submit expand/polish as background jobs`

---

### Task 10: 资产页 / 分镜页完成刷新（若尚未）

**Files:**
- Modify: 资产生成调用处、`Storyboard.jsx`（生成后依赖 job/资产状态轮询；若已有 generating 轮询可只确保 Job 已创建）

- [ ] **Step 1: 确认 `assetsApi.generate` 后端已建 Job；前端离开再回来 list 能看到结果。**
- [ ] **Step 2: Commit** `fix(workbench): refresh assets/storyboard when jobs complete`

---

### Task 11: Phase J README

- [ ] **Step 1:** 更新根 README / `backend/README`：后台 Job 已真实；RAG 仍下一阶段。  
- [ ] **Step 2: Commit** `docs: note background jobs in current status`

---

# Phase R — RAG

### Task 12: 依赖与 settings 路径

**Files:**
- Modify: `backend/requirements.txt` — 取消注释并钉版本：`chromadb==0.5.5`；增加 `sentence-transformers>=3.0.0`（若环境重，计划允许 CPU）
- Modify: `backend/app/core/settings.py`

```python
@property
def rag_chroma_dir(self) -> Path:
    return self.modelhub_root / "rag" / "chroma"

@property
def embed_model_dir(self) -> Path:
    return self.modelhub_root / "embed" / "bge-m3"
```

- [ ] **Step 1: 改文件 + `.env.example` 注释 MODELHUB_ROOT/rag**  
- [ ] **Step 2: Commit** `chore(rag): add chromadb deps and paths`

---

### Task 13: rag_cases 表 + repository

**Files:**
- Modify: `backend/app/db/schema.py` — `003_rag_cases`
- Create: `backend/app/db/repositories/rag_cases.py`
- Create: `backend/tests/test_rag_cases_repository.py`

迁移 SQL：

```sql
CREATE TABLE IF NOT EXISTS rag_cases (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  type TEXT NOT NULL,
  style TEXT,
  description TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  prompt_en TEXT,
  negative_prompt TEXT,
  source_project_id TEXT,
  source_ref TEXT,
  rating REAL NOT NULL DEFAULT 0,
  usage_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_cases_type ON rag_cases(type);
```

Repository：`create` / `get` / `list` / `delete` / `increment_usage`。

- [ ] **Step 1: TDD 同 Task 1 风格**  
- [ ] **Step 2: Commit** `feat(rag): add rag_cases table`

---

### Task 14: Embedder + Chroma store

**Files:**
- Create: `backend/app/services/rag_embedder.py`
- Create: `backend/app/services/rag_store.py`
- Create: `backend/tests/test_rag_store.py`

```python
# rag_embedder.py
class Embedder:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self._model = None

    def available(self) -> bool:
        return self.model_dir.exists()

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            if not self.available():
                raise RuntimeError("bge-m3_not_found")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(str(self.model_dir))
        return self._model.encode(texts, normalize_embeddings=True).tolist()
```

```python
# rag_store.py — chromadb PersistentClient(path=settings.rag_chroma_dir)
# collection vf_cases: upsert(id, embedding, document=description, metadatas=...)
# query(embedding, n_results, where type?)
```

测试：用 **假 embedder**（固定向量）注入，避免 CI 下载模型：

```python
class FakeEmbedder:
    def available(self): return True
    def encode(self, texts):
        return [[float(len(t)), 0.1, 0.2] for t in texts]
```

- [ ] **Step 1: upsert 两条 → query 命中**  
- [ ] **Step 2: Commit** `feat(rag): chroma store and embedder`

---

### Task 15: 真实 `/api/rag`

**Files:**
- Rewrite: `backend/app/api/rag.py`
- Create: `backend/tests/test_rag_api.py`

- stats / cases CRUD / search / ingest  
- ingest：读 scene/asset/frame → 写 rag_cases → chroma upsert  
- bge 不可用：search/ingest → HTTP 503 `{"detail":"bge-m3_not_found"}`

- [ ] **Step 1: 实现 + 测试（FakeEmbedder 依赖注入）**  
- [ ] **Step 2: Commit** `feat(rag): real rag API`

---

### Task 16: expand/polish 检索注入

**Files:**
- Create: `backend/app/services/rag_retrieve.py` — `format_rag_block(hits) -> str`
- Modify: `script_expand.py` / `cinematic_polish.py` — 调用 LLM 前 `retrieve(query, top_k=3)`，无结果跳过；失败吞掉并 log（主流程不失败）
- Create: `backend/tests/test_rag_inject.py`

```python
def build_rag_context(query: str, top_k: int = 3) -> str:
    try:
        hits = search_cases(query, top_k=top_k)
    except Exception:
        return ""
    if not hits:
        return ""
    # increment usage optional
    return "参考案例（仅风格与结构，勿照抄）:\n" + "\n---\n".join(...)
```

- [ ] **Step 1: 单测 mock retrieve 非空时 messages 含「参考案例」**  
- [ ] **Step 2: Commit** `feat(rag): inject retrieved cases into expand/polish`

---

### Task 17: 管理页 + 工作台「存入知识库」

**Files:**
- Modify: `frontend/src/services/api.js` — `ragApi`
- Modify: `frontend/src/pages/admin/RAGKnowledge.jsx` — 去掉写死数据；接 list/stats/search/delete/create
- Modify: `ScriptWorkshop.jsx`（及资产卡片若有）— 按钮「存入知识库」→ `ragApi.ingest({ source_type:'scene', project_id, ref_id })`
- 完成 notification 次要按钮可选：在 `useJobTracker` 对 `prompt_polish`/`asset_generate` completed 增加 `btn: 存入知识库`

- [ ] **Step 1: 接线**  
- [ ] **Step 2: Commit** `feat(rag): wire admin page and ingest button`

---

### Task 18: Phase R README + 总验收

- [ ] **Step 1: README** — Job + RAG 已真实；成片/TTS/系统通知仍非目标。  
- [ ] **Step 2: 手工清单**
  1. 扩写后立刻切监控页 → 常驻条仍在 → 完成后 toast → 回剧本页有场景  
  2. 空 RAG search → `[]`  
  3. 一键入库 → 管理页可见 → 再扩写日志/结果体现参考（或断点看 prompt）  
- [ ] **Step 3: Commit** `docs: mark RAG and background jobs as live`

---

## Spec coverage（自审）

| Spec 项 | Task |
|---|---|
| jobs 表 + API + worker | 1–3 |
| expand/analyze/polish/batch | 4–5 |
| asset/storyboard Job | 6 |
| 重启 fail_stale | 2 |
| monitor tasks←jobs | 7 |
| 常驻条 + toast + 顶栏 | 8–7 |
| ScriptWorkshop 异步 | 9 |
| Chroma+bge-m3+rag_cases | 12–14 |
| RAG API / 注入 / 入库 / 管理页 | 15–17 |
| 非目标（WS/系统通知/TTS） | 未排任务 |

## 类型一致性
- Job `type` 字符串与 `TITLE_BY_TYPE` / 前端 create 一致。  
- snapshot 仍暴露 `generating`/`failed_recent`/`badge_count` 字段名以兼容 MainLayout。  
- RAG ingest：`source_type` + `ref_id`。
