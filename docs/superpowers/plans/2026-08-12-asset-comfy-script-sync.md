# Asset Comfy Connectivity + Script Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 资产页去掉 mock 误导、Comfy 不可用时拦截并说清原因，再一键从剧本同步角色/场景草稿（风格化提示词），用户确认后才入队生图。

**Architecture:** 一期改 `assets` API 列表与 `generate` 前置 `client.health()`；前端状态条读 `/api/models/services`。二期新增 `asset_script_sync` 服务（聚合场景 → 幂等写资产 → 可选 `CinematicPolishService`），暴露 `POST .../sync-from-script`；前端同步 + 批量生成 pending。

**Tech Stack:** FastAPI, SQLite AssetStore, ComfyUIClient, CinematicPolishService, React/Ant Design

**Spec:** [docs/superpowers/specs/2026-08-12-asset-comfy-script-sync-design.md](../specs/2026-08-12-asset-comfy-script-sync-design.md)

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/api/assets.py` | 去掉 mock 合并；generate 前 health；sync 路由 |
| `backend/app/services/asset_store.py` | `create(..., status=)` 透传；按 name+type 查找 |
| `backend/app/db/repositories/assets.py` | `find_by_name_type`；create status 已有 |
| `backend/app/services/asset_script_sync.py` | 候选聚合、enrich、幂等 sync |
| `backend/tests/test_assets_list_no_mock.py` | 列表无种子 |
| `backend/tests/test_assets_generate_health.py` | health 失败不入队 |
| `backend/tests/test_asset_script_sync.py` | 聚合/幂等/fallback |
| `frontend/src/services/api.js` | `syncFromScript`、批量 generate 可复用现有 |
| `frontend/src/pages/workbench/AssetGeneration.jsx` | 状态条、文案、空态、同步、批量 |
| `README.md` | 资产页用法一行 |

---

### Task 1: 列表去掉 mock 种子

**Files:**
- Modify: `backend/app/api/assets.py`
- Create: `backend/tests/test_assets_list_no_mock.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_assets_list_no_mock.py
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_list_assets_empty_without_mock_seeds():
    with patch("app.api.assets.store.list", return_value=[]):
        r = client.get("/api/assets/proj_empty/assets")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_assets_list_no_mock.py -v`  
Expected: FAIL（当前仍返回张三等 mock）

- [ ] **Step 3: Minimal implementation**

In `backend/app/api/assets.py`:
- Delete `mock_characters` / `mock_scenes_assets` / `mock_props` 常量块（或移到 `tests/fixtures` 若别处无引用）。
- 改 `_list_assets`：

```python
def _list_assets(project_id: str, asset_type: str | None = None) -> list[dict]:
    items = store.list(project_id)
    if asset_type:
        items = [i for i in items if i["type"] == asset_type]
    return items
```

- `get_asset` 中「all_assets = mock_...」回退删除；找不到则 404。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_assets_list_no_mock.py tests/test_assets_negative.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/assets.py backend/tests/test_assets_list_no_mock.py
git commit -m "fix(assets): stop merging mock seeds into asset list"
```

---

### Task 2: generate 前 Comfy health 拦截

**Files:**
- Modify: `backend/app/api/assets.py`
- Create: `backend/tests/test_assets_generate_health.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_assets_generate_health.py
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)

PAYLOAD = {
    "name": "张三",
    "type": "character",
    "prompt_cn": "年轻男子",
    "prompt_en": "young man",
    "model": "sdxl",
}


def test_generate_rejects_when_comfy_unhealthy():
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = False
            with patch("app.api.assets.queue.enqueue") as enq:
                r = client.post("/api/assets/p1/generate", json=PAYLOAD)
    assert r.status_code == 503
    assert "comfyui_unavailable" in str(r.json().get("detail"))
    enq.assert_not_called()


def test_generate_enqueues_when_comfy_healthy():
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.client") as mock_client:
            mock_client.health.return_value = True
            with patch("app.api.assets.queue.enqueue") as enq:
                with patch("app.api.assets.store.create") as create:
                    create.return_value = {**PAYLOAD, "id": "asset_c_1", "status": "generating",
                                           "name_en": "张三", "created_at": "t", "image_url": None, "error": None}
                    with patch("app.services.runtime.job_repo") as jobs:
                        jobs.create.return_value = {"id": "job_1"}
                        r = client.post("/api/assets/p1/generate", json=PAYLOAD)
    assert r.status_code == 200
    enq.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_assets_generate_health.py::test_generate_rejects_when_comfy_unhealthy -v`  
Expected: FAIL（仍 200 或未 503）

- [ ] **Step 3: Minimal implementation**

In `backend/app/api/assets.py` top:

```python
from app.services.runtime import queue, store, client
```

（若已有 `from app.services.runtime import queue, store`，追加 `client`。）

In `generate_asset`，在 `check_model` 通过之后、`store.create` 之前：

```python
    if not client.health():
        raise HTTPException(
            status_code=503,
            detail="comfyui_unavailable",
        )
```

Also update `test_assets_negative.py` to patch `client.health` → `True`，否则 CI 本机 Comfy 挂掉会红：

```python
with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
    with patch("app.api.assets.client") as mock_client:
        mock_client.health.return_value = True
        with patch("app.api.assets.queue.enqueue"):
            ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_assets_generate_health.py tests/test_assets_negative.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/assets.py backend/tests/test_assets_generate_health.py backend/tests/test_assets_negative.py
git commit -m "fix(assets): reject generate when ComfyUI health fails"
```

---

### Task 3: 前端连通性状态条 + 错误映射 + 空态

**Files:**
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`
- Modify: `frontend/src/services/api.js`（若需导出错误辅助函数可内联在页面）

- [ ] **Step 1: Add helpers near top of AssetGeneration.jsx**

```javascript
const COMFY_HINT =
  '生成经本地 ComfyUI 串行队列自动提交内置工作流，无需在 Comfy 里手动跑图。'

function mapAssetError(err, comfyUrl = 'http://127.0.0.1:8188') {
  const msg = String(err?.message || err || '')
  if (msg.includes('comfyui_unavailable')) {
    return `ComfyUI 不可用：请启动服务并确认地址（当前：${comfyUrl}）。若界面能开但 API 返回 503，多为仍在加载，请稍后重试。`
  }
  if (msg.includes('model not ready')) {
    return `模型权重未就绪：${msg}`
  }
  return msg || '生成失败'
}
```

- [ ] **Step 2: State + probe on mount**

```javascript
const [comfyOnline, setComfyOnline] = useState(null) // null | true | false
const [comfyUrl, setComfyUrl] = useState('http://127.0.0.1:8188')

const refreshComfy = useCallback(async () => {
  setComfyOnline(null)
  try {
    const services = await modelsApi.services()
    const sd = (services || []).find((s) => s.id === 'sd')
    if (sd?.api_url) setComfyUrl(sd.api_url)
    setComfyOnline(sd?.status === 'online' || sd?.status === 'busy')
  } catch {
    setComfyOnline(false)
  }
}, [])

useEffect(() => { refreshComfy() }, [refreshComfy])
```

- [ ] **Step 3: Banner UI**（列表上方）

三态 Alert：检测中 / 在线（success + `COMFY_HINT`）/ 不可用（error + URL + 「重试」按钮调用 `refreshComfy`）。

- [ ] **Step 4: Gate regenerate**

在 `handleRegenerate` / `submitGenerate` 开头：若 `comfyOnline === false`，`message.error(mapAssetError({ message: 'comfyui_unavailable' }, comfyUrl))` 并 return。catch 里用 `mapAssetError(e, comfyUrl)`。

预览区失败文案：`mapAssetError({ message: currentAsset.error }, comfyUrl)`。

- [ ] **Step 5: Empty state**

当 `currentList.length === 0`：展示「暂无资产」+ 文案「请先从剧本同步角色/场景」（二期按钮先占位 `disabled` 或等 Task 7 接上；一期可用文字 CTA 指向说明）。

- [ ] **Step 6: Manual smoke**

前端刷新资产页：无张三种子；Comfy 挂时状态条红、点重新生成 toast 中文。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/workbench/AssetGeneration.jsx
git commit -m "feat(ui): Comfy status banner and clearer asset errors"
```

---

### Task 4: 剧本候选聚合（纯函数）

**Files:**
- Create: `backend/app/services/asset_script_sync.py`
- Create: `backend/tests/test_asset_script_sync.py`

- [ ] **Step 1: Failing tests for candidates**

```python
# backend/tests/test_asset_script_sync.py
from app.services.asset_script_sync import collect_candidates


def test_collect_characters_and_scenes():
    scenes = [
        {
            "number": 1,
            "name": "开场",
            "location": "竹林",
            "characters": ["张三", "李四", ""],
            "description": "晨雾中对峙",
            "description_en": "standoff in mist",
        },
        {
            "number": 2,
            "name": "客栈",
            "location": "客栈",
            "characters": ["张三", "神秘人"],
            "description": "酒桌上试探",
            "description_en": "",
        },
    ]
    chars, scns = collect_candidates(scenes)
    assert [c["name"] for c in chars] == ["张三", "李四", "神秘人"]
    assert chars[0]["related_descriptions"]  # 含相关场景摘要
    assert [s["name"] for s in scns] == ["竹林", "客栈"]
```

- [ ] **Step 2: Run — expect FAIL (import error)**

Run: `python -m pytest tests/test_asset_script_sync.py::test_collect_characters_and_scenes -v`

- [ ] **Step 3: Implement `collect_candidates`**

```python
# backend/app/services/asset_script_sync.py
from __future__ import annotations

from typing import Any


def collect_candidates(scenes: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    char_map: dict[str, dict[str, Any]] = {}
    scene_assets: list[dict[str, Any]] = []
    for sc in scenes:
        loc = (sc.get("location") or "").strip()
        name = (sc.get("name") or "").strip()
        scene_name = loc or name or f"场景{sc.get('number') or len(scene_assets) + 1}"
        desc = (sc.get("description") or "").strip()
        desc_en = (sc.get("description_en") or "").strip()
        summary = desc or desc_en
        scene_assets.append(
            {
                "type": "scene",
                "name": scene_name,
                "seed_cn": summary or scene_name,
                "related_descriptions": [summary] if summary else [],
            }
        )
        for raw in sc.get("characters") or []:
            cname = str(raw).strip()
            if not cname:
                continue
            slot = char_map.setdefault(
                cname,
                {"type": "character", "name": cname, "seed_cn": cname, "related_descriptions": []},
            )
            if summary and summary not in slot["related_descriptions"]:
                slot["related_descriptions"].append(summary)
            slot["related_descriptions"] = slot["related_descriptions"][:3]
    return list(char_map.values()), scene_assets
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/asset_script_sync.py backend/tests/test_asset_script_sync.py
git commit -m "feat(assets): collect character/scene candidates from script"
```

---

### Task 5: sync 幂等 + enrich fallback

**Files:**
- Modify: `backend/app/services/asset_script_sync.py`
- Modify: `backend/app/services/asset_store.py`（`create` 透传 `status`；`find_by_name_type`）
- Modify: `backend/app/db/repositories/assets.py`（`find_by_name_type`）
- Modify: `backend/tests/test_asset_script_sync.py`

- [ ] **Step 1: Repo finder + store passthrough**

`AssetRepository.find_by_name_type(self, project_id, type, name) -> dict | None`：

```python
    def find_by_name_type(self, project_id: str, type: str, name: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE project_id = ? AND type = ? AND name = ? LIMIT 1",
                (project_id, type, name),
            ).fetchone()
            return dict(row) if row else None
```

`AssetStore.create` 增加 `status: str = "generating"` 并传给 repo。  
`AssetStore.find_by_name_type` 代理 repo。

- [ ] **Step 2: Tests for sync_project**

```python
def test_sync_creates_pending_and_skips_completed_with_image(tmp_path, monkeypatch):
    from app.services.asset_store import AssetStore
    from app.services import asset_script_sync as mod

    store = AssetStore(tmp_path / "t.db")
    store.create(
        project_id="p",
        name="张三",
        type="character",
        prompt_cn="old",
        prompt_en="old",
        model="sdxl",
        status="completed",
    )
    # force image_url
    a = store.find_by_name_type("p", "character", "张三")
    store.update("p", a["id"], image_url="/media/assets/p/x.png")

    scenes = [{
        "number": 1, "name": "开场", "location": "竹林",
        "characters": ["张三", "李四"], "description": "对峙", "description_en": "",
    }]
    project = {"id": "p", "style": "古风武侠", "name": "测"}

    def boom(**kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(mod, "_enrich_one", boom)
    result = mod.sync_from_script(
        project=project,
        scenes=scenes,
        store=store,
        types=("character", "scene"),
        enrich=True,
        default_model="sdxl",
    )
    assert result["skipped"] >= 1
    assert result["created"] >= 1  # 李四 + 场景
    assert result["enrich_fallback"] is True
    li = store.find_by_name_type("p", "character", "李四")
    assert li["status"] == "pending"
    assert "古风武侠" in (li["prompt_cn"] + li["prompt_en"])
```

- [ ] **Step 3: Implement sync helpers**

```python
def fallback_prompts(*, name: str, style: str, related: list[str], type: str) -> dict[str, str]:
    bits = [name]
    if style:
        bits.append(f"{style} style")
    bits.extend(related[:2])
    kind = "character portrait" if type == "character" else "establishing scene"
    cn = "，".join([name, style, *related[:2]]).strip("，")
    en = f"{kind}, " + ", ".join(bits)
    avoid = "blurry, low quality, watermark, text"
    return {"prompt_cn": cn or name, "prompt_en": en, "negative_prompt": avoid}


def _enrich_one(*, polish_svc, stage: str, name: str, style: str, related: list[str]) -> dict[str, str]:
    ctx = {"project_style": style, "asset_name": name, "scene_summaries": related[:3]}
    seed = f"{name}。风格：{style}。" + "；".join(related[:3])
    data = polish_svc.polish(
        stage=stage,
        text_cn=seed,
        text_en="",
        context=ctx,
        return_interpretation=False,
    )
    return {
        "prompt_cn": data.get("prompt_cn") or seed,
        "prompt_en": data["prompt_en"],
        "negative_prompt": data.get("avoid") or "blurry, low quality",
    }


def sync_from_script(
    *,
    project: dict[str, Any],
    scenes: list[dict[str, Any]],
    store: Any,
    types: tuple[str, ...] = ("character", "scene"),
    enrich: bool = True,
    default_model: str = "sdxl",
    polish_svc: Any | None = None,
) -> dict[str, Any]:
    if not scenes:
        raise ValueError("no_scenes")
    style = (project.get("style") or "").strip()
    chars, scns = collect_candidates(scenes)
    candidates = []
    if "character" in types:
        candidates.extend(chars)
    if "scene" in types:
        candidates.extend(scns)

    created = updated = skipped = 0
    enrich_fallback = False
    out_assets: list[dict] = []

    for cand in candidates:
        existing = store.find_by_name_type(project["id"], cand["type"], cand["name"])
        if existing and existing.get("status") == "completed" and existing.get("image_url"):
            skipped += 1
            out_assets.append(existing)
            continue

        prompts = None
        if enrich and polish_svc is not None:
            try:
                stage = "character" if cand["type"] == "character" else "scene"
                prompts = _enrich_one(
                    polish_svc=polish_svc,
                    stage=stage,
                    name=cand["name"],
                    style=style,
                    related=cand.get("related_descriptions") or [],
                )
            except Exception:
                enrich_fallback = True
                prompts = None
        if prompts is None:
            if enrich:
                enrich_fallback = True
            prompts = fallback_prompts(
                name=cand["name"],
                style=style,
                related=cand.get("related_descriptions") or [],
                type=cand["type"],
            )

        if existing:
            asset = store.update(
                project["id"],
                existing["id"],
                prompt_cn=prompts["prompt_cn"],
                prompt_en=prompts["prompt_en"],
                negative_prompt=prompts["negative_prompt"],
                status="pending",
                error=None,
            )
            updated += 1
        else:
            asset = store.create(
                project_id=project["id"],
                name=cand["name"],
                type=cand["type"],
                prompt_cn=prompts["prompt_cn"],
                prompt_en=prompts["prompt_en"],
                model=default_model,
                negative_prompt=prompts["negative_prompt"],
                status="pending",
            )
            created += 1
        out_assets.append(asset)

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "enrich_fallback": enrich_fallback,
        "assets": out_assets,
    }
```

- [ ] **Step 4: Run tests PASS**

Run: `python -m pytest tests/test_asset_script_sync.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/asset_script_sync.py backend/app/services/asset_store.py backend/app/db/repositories/assets.py backend/tests/test_asset_script_sync.py
git commit -m "feat(assets): sync-from-script with idempotent pending drafts"
```

---

### Task 6: `POST /api/assets/{project_id}/sync-from-script`

**Files:**
- Modify: `backend/app/api/assets.py`
- Create: `backend/tests/test_assets_sync_api.py`

- [ ] **Step 1: API test**

```python
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_sync_from_script_400_without_scenes():
    with patch("app.api.assets.ProjectRepository") as PR:
        with patch("app.api.assets.SceneRepository") as SR:
            PR.return_value.get.return_value = {"id": "p", "style": "古风"}
            SR.return_value.list_by_project.return_value = []
            r = client.post("/api/assets/p/sync-from-script", json={})
    assert r.status_code == 400
    assert "剧本" in str(r.json().get("detail")) or "scene" in str(r.json().get("detail")).lower()
```

（实现时 `detail` 固定为：`请先在剧本工坊完成扩写/解析。`）

- [ ] **Step 2: Wire endpoint**

```python
from pydantic import BaseModel, Field
from app.db.repositories.projects import ProjectRepository
from app.db.repositories.scenes import SceneRepository
from app.services.asset_script_sync import sync_from_script
from app.api.prompts import get_polish_service  # or construct similarly


class SyncFromScriptRequest(BaseModel):
    types: list[str] = Field(default_factory=lambda: ["character", "scene"])
    enrich: bool = True


@router.post("/{project_id}/sync-from-script", summary="从剧本同步角色/场景资产草稿")
def sync_assets_from_script(project_id: str, body: SyncFromScriptRequest = SyncFromScriptRequest()):
    project = ProjectRepository().get(project_id)
    if not project:
        raise HTTPException(404, detail="项目不存在")
    scenes = SceneRepository().list_by_project(project_id)
    if not scenes:
        raise HTTPException(400, detail="请先在剧本工坊完成扩写/解析。")
    allowed = tuple(t for t in body.types if t in ("character", "scene"))
    polish = None
    if body.enrich:
        try:
            polish = get_polish_service()
        except Exception:
            polish = None
    try:
        result = sync_from_script(
            project=project,
            scenes=scenes,
            store=store,
            types=allowed or ("character", "scene"),
            enrich=body.enrich,
            polish_svc=polish,
        )
    except ValueError as e:
        if str(e) == "no_scenes":
            raise HTTPException(400, detail="请先在剧本工坊完成扩写/解析。")
        raise
    return result
```

注意：路由须注册在 `/{project_id}/{asset_id}` **之前**，避免 `sync-from-script` 被当成 asset_id。把 sync 与 list 类路由放在动态 `asset_id` 路由上面。

- [ ] **Step 3: Run**

`python -m pytest tests/test_assets_sync_api.py tests/test_asset_script_sync.py -v` → PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/assets.py backend/tests/test_assets_sync_api.py
git commit -m "feat(api): sync assets from script scenes"
```

---

### Task 7: 前端同步 + 批量生成 pending

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`

- [ ] **Step 1: api.js**

```javascript
  syncFromScript(projectId, payload = {}) {
    return request(`/api/assets/${projectId}/sync-from-script`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
```

（挂在 `assetsApi` 上。）

- [ ] **Step 2: Sync button**

- 列表头或空态主按钮「从剧本同步」：调用 `assetsApi.syncFromScript(projectId, { enrich: true })`，loading，成功 `message.success(\`已同步：新建 ${created}，更新 ${updated}，跳过 ${skipped}\`)`，若 `enrich_fallback` 则 `message.warning('部分提示词使用了降级模板（LLM 不可用）')`，然后 `refreshList` 并选中首个新建/更新项。  
- Comfy 是否在线不影响同步（只写草稿）。

- [ ] **Step 3: Batch generate pending**

按钮「批量生成待出图」：过滤当前 Tab `status === 'pending'`；若 `comfyOnline === false` 拦截；否则对每个调用现有 `submitGenerate` / `assetsApi.generate`（串行 await，避免一次打爆）；每成功一条刷新。

- [ ] **Step 4: Smoke checklist**

1. 空项目：无 mock。  
2. 有剧本场景：同步 → pending + 长提示词。  
3. Comfy 挂：状态条红，批量/重新生成被拦。  
4. Comfy 好：重新生成出现队列任务。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/pages/workbench/AssetGeneration.jsx
git commit -m "feat(ui): sync assets from script and batch generate pending"
```

---

### Task 8: README 一行用法

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** 在工作台/资产生成小节增加：

```markdown
资产生成：先启动 ComfyUI（默认 `http://127.0.0.1:8188`，`/system_stats` 需 200）→ 资产页「从剧本同步」→「重新生成」或「批量生成待出图」。提示词会结合项目风格；出图自动提交内置 workflow，无需在 Comfy 手动操作。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: asset page Comfy + script sync usage"
```

---

## Spec coverage check

| Spec 项 | Task |
|---------|------|
| 去掉 mock | T1 |
| generate health 拦截 | T2 |
| 状态条 / 中文错误 / 用法提示 / 空态 | T3 |
| 候选聚合 | T4 |
| 幂等 + enrich fallback | T5 |
| sync API | T6 |
| 同步按钮 + 批量 pending | T7 |
| 文档 | T8 |
| 道具自动抽 | 不做 |
| 自动进页全量开画 | 不做 |

## Placeholder scan

无 TBD/TODO；函数名 `sync_from_script` / `collect_candidates` / `find_by_name_type` 前后一致。
