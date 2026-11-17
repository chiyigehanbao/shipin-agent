# 工作台真实化（LLM 运维 + SQLite + 剧本扩写）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 C→A→B 打通：LLM 配置可运维使润色可用、SQLite 持久化项目/场景/分镜/资产元数据、剧本扩写接真实 LLM 并落库。

**Architecture:** `llm_settings.json` 覆盖 `settings` 供 `LLMProvider`；`sqlite3` 薄仓库替换内存 mock；scripts expand/analyze 复用 LLMProvider 写 `scenes` 表；前端项目与剧本去假数据。

**Tech Stack:** FastAPI、sqlite3、httpx、pytest、React、Zustand、Ant Design

**Spec:** `docs/superpowers/specs/2026-08-11-workbench-persistence-llm-design.md`

**强制顺序:** Phase C → Phase A → Phase B。每阶段结束应可独立验收。

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/.env.example` | LLM / MODELHUB 示例环境变量 |
| `backend/app/core/settings.py` | `sqlite_path`；保留既有 LLM 字段 |
| `backend/app/services/llm_settings_store.py` | 读写 `backend/data/llm_settings.json`，合并生效配置 |
| `backend/app/api/settings_llm.py` | GET/PUT/POST test `/api/settings/llm` |
| `backend/app/main.py` | 注册 settings 路由；startup 初始化 DB |
| `backend/app/db/schema.py` | DDL + migrate |
| `backend/app/db/connection.py` | sqlite 连接工厂 |
| `backend/app/db/repositories/*.py` | projects/scenes/assets/frames CRUD |
| `backend/app/api/projects.py` | 改用 ProjectRepo |
| `backend/app/services/asset_store.py` | 底层改 SQLite（保持方法签名） |
| `backend/app/services/storyboard_store.py` | 底层改 SQLite |
| `backend/app/api/scripts.py` | expand/analyze + scenes GET/PUT |
| `backend/app/prompt_packs/script_expand_v1/system.md` | 剧本扩写 system prompt |
| `frontend/src/services/api.js` | `settingsApi` / `projectsApi` / `scriptsApi` |
| `frontend/src/pages/admin/SystemSettings.jsx` | LLM 表单接线 |
| `frontend/src/pages/admin/ModelConfig.jsx` | LLM Tab 接线（或委托 SystemSettings 同一 API） |
| `frontend/src/store/projectStore.js` | 去硬编码权威列表 |
| `frontend/src/pages/workbench/ProjectCreate.jsx` | 调 API 创建 |
| `frontend/src/pages/...` 项目列表页 | 调 API 列表 |
| `frontend/src/pages/workbench/ScriptWorkshop.jsx` | 真实 expand/analyze + 拉场景 |

工作目录：后端 `backend/`；前端 `frontend/`。PowerShell 提交勿用 bash heredoc。

---

# Phase C — 润色可运维

### Task 1: `.env.example` + sqlite_path setting

**Files:**
- Create: `backend/.env.example`
- Modify: `backend/app/core/settings.py`

- [ ] **Step 1: 写入 `.env.example`**

```env
MODELHUB_ROOT=E:\ModelHub
COMFYUI_BASE_URL=http://127.0.0.1:8188
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
CLOUD_LLM_BASE_URL=
CLOUD_LLM_API_KEY=
CLOUD_LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SEC=60
SQLITE_PATH=
```

说明：`SQLITE_PATH` 空则默认 `backend/data/shipin-agent.db`（Task 5 使用）。

- [ ] **Step 2: settings.py 增加**

```python
    sqlite_path: Path | None = None  # 空则用 backend/data/shipin-agent.db

    @property
    def resolved_sqlite_path(self) -> Path:
        if self.sqlite_path:
            return Path(self.sqlite_path)
        return Path(__file__).resolve().parents[2] / "data" / "shipin-agent.db"
```

（`parents[2]` = `backend/`：`app/core/settings.py` → `app` → `backend`。）

- [ ] **Step 3: Commit**

```powershell
git add backend/.env.example backend/app/core/settings.py
git commit -m "chore: add env example and sqlite_path setting"
```

---

### Task 2: llm_settings_store + 合并生效配置

**Files:**
- Create: `backend/app/services/llm_settings_store.py`
- Create: `backend/tests/test_llm_settings_store.py`

- [ ] **Step 1: 写测试**

```python
from pathlib import Path
from app.services.llm_settings_store import LlmSettingsStore


def test_load_defaults_when_missing(tmp_path: Path):
    store = LlmSettingsStore(tmp_path / "llm_settings.json")
    cfg = store.get_effective(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        cloud_llm_base_url="",
        cloud_llm_api_key="",
        cloud_llm_model="gpt-4o-mini",
        llm_timeout_sec=60.0,
    )
    assert cfg["ollama_model"] == "qwen2.5:7b"
    assert cfg["api_key_set"] is False


def test_save_overrides_and_masks_key(tmp_path: Path):
    path = tmp_path / "llm_settings.json"
    store = LlmSettingsStore(path)
    store.save({
        "ollama_base_url": "http://ollama:11434",
        "ollama_model": "qwen3.5:9b",
        "cloud_llm_base_url": "https://api.openai.com/v1",
        "cloud_llm_api_key": "sk-secret",
        "cloud_llm_model": "gpt-4o-mini",
        "llm_timeout_sec": 30.0,
    })
    public = store.get_public(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        cloud_llm_base_url="",
        cloud_llm_api_key="",
        cloud_llm_model="gpt-4o-mini",
        llm_timeout_sec=60.0,
    )
    assert public["ollama_model"] == "qwen3.5:9b"
    assert public["api_key_set"] is True
    assert "sk-secret" not in str(public)
```

- [ ] **Step 2: pytest 期望 FAIL → 实现 store**

```python
# backend/app/services/llm_settings_store.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


class LlmSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read_file(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = self._read_file()
        for k, v in data.items():
            if v is None:
                continue
            if k == "cloud_llm_api_key" and v == "":
                continue  # 空字符串表示不改 key
            current[k] = v
        self.path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_effective(self, **defaults: Any) -> dict[str, Any]:
        file_cfg = self._read_file()
        out = dict(defaults)
        out.update({k: v for k, v in file_cfg.items() if v is not None and v != ""})
        # empty string cloud key in file still counts
        if "cloud_llm_api_key" in file_cfg:
            out["cloud_llm_api_key"] = file_cfg["cloud_llm_api_key"]
        out["api_key_set"] = bool(out.get("cloud_llm_api_key"))
        return out

    def get_public(self, **defaults: Any) -> dict[str, Any]:
        eff = self.get_effective(**defaults)
        key = eff.get("cloud_llm_api_key") or ""
        return {
            "ollama_base_url": eff["ollama_base_url"],
            "ollama_model": eff["ollama_model"],
            "cloud_llm_base_url": eff.get("cloud_llm_base_url") or "",
            "cloud_llm_model": eff.get("cloud_llm_model") or "",
            "llm_timeout_sec": eff.get("llm_timeout_sec") or 60.0,
            "api_key_set": bool(key),
            "cloud_llm_api_key_masked": ("***" + key[-4:]) if len(key) >= 4 else ("***" if key else ""),
        }
```

- [ ] **Step 3: pytest PASS + commit**

```powershell
cd backend
python -m pytest tests/test_llm_settings_store.py -v
git add backend/app/services/llm_settings_store.py backend/tests/test_llm_settings_store.py
git commit -m "feat(llm): add overridable llm_settings.json store"
```

---

### Task 3: `/api/settings/llm` + polish 使用生效配置

**Files:**
- Create: `backend/app/api/settings_llm.py`
- Modify: `backend/app/main.py`（include_router）
- Modify: `backend/app/api/prompts.py`（`get_polish_service` 读 store）
- Create: `backend/tests/test_settings_llm_api.py`

- [ ] **Step 1: 实现 router**

```python
# backend/app/api/settings_llm.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from app.core.settings import settings
from app.services.llm_settings_store import LlmSettingsStore
from app.services.llm_provider import LLMProvider, LLMError

router = APIRouter()
STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "llm_settings.json"


def llm_store() -> LlmSettingsStore:
    return LlmSettingsStore(STORE_PATH)


def effective_llm_kwargs() -> dict:
    store = llm_store()
    return store.get_effective(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        cloud_llm_base_url=settings.cloud_llm_base_url,
        cloud_llm_api_key=settings.cloud_llm_api_key,
        cloud_llm_model=settings.cloud_llm_model,
        llm_timeout_sec=settings.llm_timeout_sec,
    )


class LlmSettingsUpdate(BaseModel):
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    cloud_llm_base_url: Optional[str] = None
    cloud_llm_api_key: Optional[str] = None
    cloud_llm_model: Optional[str] = None
    llm_timeout_sec: Optional[float] = None


@router.get("/llm")
async def get_llm_settings():
    return llm_store().get_public(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        cloud_llm_base_url=settings.cloud_llm_base_url,
        cloud_llm_api_key=settings.cloud_llm_api_key,
        cloud_llm_model=settings.cloud_llm_model,
        llm_timeout_sec=settings.llm_timeout_sec,
    )


@router.put("/llm")
async def put_llm_settings(body: LlmSettingsUpdate):
    llm_store().save(body.model_dump(exclude_unset=True))
    return await get_llm_settings()


@router.post("/llm/test")
async def test_llm_settings():
    kw = effective_llm_kwargs()
    provider = LLMProvider(
        ollama_base_url=kw["ollama_base_url"],
        ollama_model=kw["ollama_model"],
        cloud_llm_base_url=kw.get("cloud_llm_base_url") or "",
        cloud_llm_api_key=kw.get("cloud_llm_api_key") or "",
        cloud_llm_model=kw.get("cloud_llm_model") or "",
        timeout_sec=float(kw.get("llm_timeout_sec") or 60),
    )
    try:
        text, name = provider.chat([{"role": "user", "content": "Reply with OK"}])
        return {"ok": True, "provider": name, "sample": text[:80]}
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
```

- [ ] **Step 2: main.py** `app.include_router(settings_llm.router, prefix="/api/settings", tags=["系统设置"])`

- [ ] **Step 3: prompts.get_polish_service 改为**

```python
from app.api.settings_llm import effective_llm_kwargs

def get_polish_service() -> CinematicPolishService:
    kw = effective_llm_kwargs()
    llm = LLMProvider(
        ollama_base_url=kw["ollama_base_url"],
        ollama_model=kw["ollama_model"],
        cloud_llm_base_url=kw.get("cloud_llm_base_url") or "",
        cloud_llm_api_key=kw.get("cloud_llm_api_key") or "",
        cloud_llm_model=kw.get("cloud_llm_model") or "",
        timeout_sec=float(kw.get("llm_timeout_sec") or 60),
    )
    return CinematicPolishService(llm=llm)
```

注意：避免循环导入——若有环，把 `effective_llm_kwargs` 挪到 `app/services/llm_runtime.py`。

- [ ] **Step 4: API 测试**（TestClient GET 默认；PUT 覆盖 model；patch LLMProvider for test endpoint）

- [ ] **Step 5: Commit** `feat(api): add LLM settings endpoints used by polish`

---

### Task 4: 前端 SystemSettings / ModelConfig LLM 接线

**Files:**
- Modify: `frontend/src/services/api.js` — 增加 `settingsApi`
- Modify: `frontend/src/pages/admin/SystemSettings.jsx`
- Modify: `frontend/src/pages/admin/ModelConfig.jsx`（LLM Tab 同步同一 API）

- [ ] **Step 1: api.js**

```javascript
export const settingsApi = {
  getLlm() {
    return request('/api/settings/llm')
  },
  putLlm(payload) {
    return request('/api/settings/llm', { method: 'PUT', body: JSON.stringify(payload) })
  },
  testLlm() {
    return request('/api/settings/llm/test', { method: 'POST', body: '{}' })
  },
}
```

- [ ] **Step 2: SystemSettings 挂载时 `getLlm` 填表；保存调 `putLlm`；「测试连接」调 `testLlm`；展示 `api_key_set` / masked；保存成功/失败用 message**

- [ ] **Step 3: ModelConfig LLM Tab 同样接线（或抽共享 hook，YAGNI 允许复制最小逻辑）**

- [ ] **Step 4: Commit** `feat(admin): wire LLM settings form to backend`

**Phase C 手验:** 配 Ollama → 资产页润色成功；清空配置 → 502 可见。

---

# Phase A — SQLite 持久化

### Task 5: schema + connection

**Files:**
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/connection.py`
- Create: `backend/app/db/schema.py`
- Create: `backend/tests/test_db_schema.py`

- [ ] **Step 1: connection.py**

```python
from __future__ import annotations
import sqlite3
from pathlib import Path
from app.core.settings import settings

def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or settings.resolved_sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

- [ ] **Step 2: schema.py — `MIGRATE_SQL` 列表创建 schema_migrations、projects、scenes、assets、storyboard_frames（字段对齐规格 §4.2）**

- [ ] **Step 3: `def migrate(conn):` 执行未应用的迁移**

- [ ] **Step 4: 测试用 tmp_path DB，migrate 后查表存在**

- [ ] **Step 5: main.py startup 调用 `migrate(connect())`**

- [ ] **Step 6: Commit** `feat(db): add sqlite schema and migrate on startup`

---

### Task 6: ProjectRepository + projects API

**Files:**
- Create: `backend/app/db/repositories/projects.py`
- Modify: `backend/app/api/projects.py`
- Create: `backend/tests/test_projects_persist.py`

- [ ] **Step 1: Repo 方法** `list_all, get, create, update, delete`（id 用 `proj_` + uuid hex）

- [ ] **Step 2: 重写 projects API 去掉 `mock_projects`，全部走 repo**

- [ ] **Step 3: 测试**

```python
def test_create_survives_reconnect(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))
    # re-import or pass path into connect — prefer inject path via settings override in test
    ...
```

实现时：测试直接 `migrate(connect(db))` + ProjectRepo(db)，不必起全应用；另加 TestClient 创建后用第二 connection 再 get。

- [ ] **Step 4: Commit** `feat(projects): persist projects in sqlite`

---

### Task 7: AssetStore / StoryboardStore → SQLite

**Files:**
- Create: `backend/app/db/repositories/assets.py`
- Create: `backend/app/db/repositories/frames.py`
- Modify: `backend/app/services/asset_store.py`
- Modify: `backend/app/services/storyboard_store.py`
- Modify: 相关 tests（asset_queue 等仍应通过）

- [ ] **Step 1: 保持 AssetStore 对外方法签名不变**（`create/get/update/list`），内部改 repo upsert。

- [ ] **Step 2: StoryboardStore 同理**；`ensure_seeded` 改为：若该 project 无帧则插入 0 行或可选演示帧（默认不插演示，空列表）。

- [ ] **Step 3: 回归** `pytest tests/test_asset_queue.py tests/test_assets_negative.py tests/test_storyboard_generate.py -v`

- [ ] **Step 4: Commit** `feat(db): persist assets and storyboard frames`

---

### Task 8: Scene repository + scripts scenes GET/PUT

**Files:**
- Create: `backend/app/db/repositories/scenes.py`
- Modify: `backend/app/api/scripts.py` — `GET /{project_id}/scenes`、`PUT /{project_id}/scenes/{scene_id}`
- Create: `backend/tests/test_scenes_repo.py`

- [ ] **Step 1: scenes repo：list_by_project, replace_all(project_id, scenes), update(scene_id, fields)**

- [ ] **Step 2: PUT 支持 `prompt_en/negative_prompt/interpretation_cn/prompt_cn`（润色应用）**

- [ ] **Step 3: Commit** `feat(scripts): scene list and update via sqlite`

---

### Task 9: 前端 projectsApi + 列表/创建接线

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/store/projectStore.js`
- Modify: `frontend/src/pages/workbench/ProjectCreate.jsx`
- Modify: 项目列表页（查找 `projects.map` / Workbench 入口，常见 `Workbench.jsx` 或 `ProjectList`）

- [ ] **Step 1: projectsApi list/create/get/update/delete**

- [ ] **Step 2: projectStore**：`fetchProjects`、`createProject` 改为 async API；移除硬编码 4 条作为权威源（可留空初始数组）

- [ ] **Step 3: ProjectCreate 等待 API 成功再 navigate**

- [ ] **Step 4: 列表页 mount 时 fetchProjects**

- [ ] **Step 5: Commit** `feat(frontend): wire project list and create to API`

**Phase A 手验:** 新建项目 → F5 → 仍在；重启后端 → 仍在。

---

# Phase B — 剧本真实扩写

### Task 10: script expand prompt pack + service

**Files:**
- Create: `backend/app/prompt_packs/script_expand_v1/system.md`
- Create: `backend/app/services/script_expand.py`
- Create: `backend/tests/test_script_expand.py`

- [ ] **Step 1: system.md** 要求输出 JSON：

```json
{
  "scenes": [
    {
      "name": "",
      "location": "",
      "time": "",
      "characters": [],
      "props": [],
      "description": "",
      "dialogue_count": 0,
      "narration_count": 0
    }
  ]
}
```

- [ ] **Step 2: ScriptExpandService** — 加载 pack、调 LLM、解析 JSON、缺字段重试一次（同 polish）

- [ ] **Step 3: mock LLM 单测**

- [ ] **Step 4: Commit** `feat(scripts): add ScriptExpandService`

---

### Task 11: scripts expand/analyze API 落库

**Files:**
- Modify: `backend/app/api/scripts.py`
- Create: `backend/tests/test_scripts_expand_api.py`

- [ ] **Step 1: POST /expand body**

```json
{ "project_id": "proj_xxx", "text": "创意...", "style": "可选" }
```

流程：校验 project 存在 → ScriptExpandService → `scenes.replace_all` → 返回场景列表。

- [ ] **Step 2: POST /analyze** 同样，user 为长剧本文本。

- [ ] **Step 3: 路由顺序** 静态路径 `/expand` `/analyze` 在 `/{project_id}/...` 之前。

- [ ] **Step 4: patch service 的 API 测 + Commit** `feat(api): real script expand/analyze with sqlite scenes`

---

### Task 12: ScriptWorkshop 真实接线

**Files:**
- Modify: `frontend/src/services/api.js` — `scriptsApi.expand/analyze/listScenes/updateScene`
- Modify: `frontend/src/pages/workbench/ScriptWorkshop.jsx`

- [ ] **Step 1: mount 时 `listScenes(projectId)` 填充 scenes**（映射后端字段到 UI：`promptEn`←`prompt_en` 等）

- [ ] **Step 2: 扩写/解析**：去掉假 setInterval；`scriptsApi.expand({ project_id, text: storyIdea, style })`；loading；成功 setScenes；失败 message.error

- [ ] **Step 3: 电影感「应用」**：除本地 state 外，调用 `scriptsApi.updateScene(projectId, sceneId, { prompt_en, negative_prompt, interpretation_cn })`

- [ ] **Step 4: Commit** `feat(script): wire expand/analyze and scene polish apply to API`

---

### Task 13: README 能力说明 + 回归

- [ ] **Step 1: 更新根 README 或 `backend/README` 中「全部 mock」段落**，改为：ComfyUI 出图 / 润色 / SQLite 项目与场景 / 剧本扩写已真实；成片/TTS/RAG 仍 mock。

- [ ] **Step 2: 回归**

```powershell
cd backend
python -m pytest tests/test_llm_settings_store.py tests/test_settings_llm_api.py tests/test_db_schema.py tests/test_projects_persist.py tests/test_scenes_repo.py tests/test_script_expand.py tests/test_scripts_expand_api.py tests/test_llm_provider.py tests/test_cinematic_polish.py tests/test_prompts_polish_api.py tests/test_workflows.py tests/test_asset_queue.py tests/test_assets_negative.py tests/test_storyboard_generate.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: Commit** `docs: update README for real workbench capabilities`

---

## Spec coverage

| Spec | Tasks |
|---|---|
| Phase C LLM 运维 | 1–4 |
| Phase A SQLite + 前端项目 | 5–9 |
| Phase B 剧本扩写 | 10–12 |
| README | 13 |
| 图片不入 DB | 全阶段遵守 image_url 路径 |
| 润色仍手动 | Task 12 不自动 polish |

## Placeholder scan
无 TBD；关键代码与命令已给出。前端页面若文件名与仓库略有差异，以 `frontend/src/pages` 实际列表页为准。
