# 管理运维真实化（监控快照 + 顶栏 + 多云 LLM）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 顶栏与监控共用真实系统/GPU/任务快照；LLM 设置支持本机 Ollama 模型列表与多云端 profile（单启用）；去掉假 GPU%/假任务角标。

**Architecture:** `GET /api/monitor/snapshot` 聚合 host（psutil）、GPU（nvidia-smi）、ComfyUI/Ollama 摘要、AssetStore 任务；`llm_settings.json` 升级为 `cloud_profiles` + `active_cloud_id`，`effective_llm_kwargs` 仍喂给现有 `LLMProvider`；前端短轮询 3–5s。

**Tech Stack:** FastAPI、psutil、subprocess nvidia-smi、httpx、pytest、React、Ant Design

**Spec:** `docs/superpowers/specs/2026-08-11-admin-monitor-realtime-design.md`

**强制顺序:** Phase M（监控）→ Phase L（LLM 多云）→ Phase U（前端接线与去假）。每阶段可独立验收。

工作目录：后端 `backend/`；前端 `frontend/`。PowerShell 提交勿用 bash heredoc。

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/requirements.txt` | 增加 `psutil` |
| `backend/app/services/gpu_info.py` | 解析 nvidia-smi → dict |
| `backend/app/services/host_info.py` | cpu/mem/disk 百分号 |
| `backend/app/db/repositories/assets.py` | `list_by_status(status, limit)` 跨项目 |
| `backend/app/services/asset_store.py` | 暴露 `list_by_status` |
| `backend/app/services/monitor_snapshot.py` | 组装 snapshot |
| `backend/app/api/monitor.py` | `GET /snapshot`；旧接口薄封装/501 |
| `backend/app/services/llm_settings_store.py` | profiles 迁移 + effective/public |
| `backend/app/services/llm_runtime.py` | 读 active profile |
| `backend/app/api/settings_llm.py` | ollama/models、paths；PUT 支持 profiles |
| `frontend/src/services/api.js` | `monitorApi`；扩展 `settingsApi` |
| `frontend/src/layouts/MainLayout.jsx` | GPU 文案 + 任务下拉 |
| `frontend/src/pages/monitor/MonitorDashboard.jsx` | 真实 snapshot，去抖动 |
| `frontend/src/pages/admin/SystemSettings.jsx` | Ollama Select + profiles + 路径只读 |
| `frontend/src/pages/admin/ModelConfig.jsx` | LLM Tab 同 API；去写死 GPU% |

---

# Phase M — 监控快照

### Task 1: psutil 依赖 + host_info

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/host_info.py`
- Create: `backend/tests/test_host_info.py`

- [ ] **Step 1: requirements.txt 增加一行** `psutil>=5.9.0`

- [ ] **Step 2: 写测试**（mock psutil）

```python
from unittest.mock import patch
from app.services.host_info import read_host_stats

def test_read_host_stats_ok():
    with patch("app.services.host_info.psutil") as p:
        p.cpu_percent.return_value = 12.5
        p.virtual_memory.return_value.percent = 48.0
        p.disk_usage.return_value.percent = 35.0
        h = read_host_stats()
    assert h["cpu_percent"] == 12.5
    assert h["memory_percent"] == 48.0
    assert h["disk_percent"] == 35.0

def test_read_host_stats_failure_returns_nulls():
    with patch("app.services.host_info.psutil") as p:
        p.cpu_percent.side_effect = RuntimeError("x")
        h = read_host_stats()
    assert h["cpu_percent"] is None
```

- [ ] **Step 3: 实现**

```python
# backend/app/services/host_info.py
from __future__ import annotations
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


def read_host_stats() -> dict[str, Any]:
    if psutil is None:
        return {"cpu_percent": None, "memory_percent": None, "disk_percent": None}
    try:
        return {
            "cpu_percent": float(psutil.cpu_percent(interval=0.0)),
            "memory_percent": float(psutil.virtual_memory().percent),
            "disk_percent": float(psutil.disk_usage("/").percent) if False else float(
                __import__("psutil").disk_usage(__import__("os").path.splitdrive(__import__("os").getcwd())[0] + "\\" if __import__("os").name == "nt" else "/").percent
            ),
        }
    except Exception:
        return {"cpu_percent": None, "memory_percent": None, "disk_percent": None}
```

实现时把磁盘路径逻辑写清楚（Windows 用当前盘符根，POSIX 用 `/`），不要塞进一行三元式；上面伪代码仅示意「要平台分支」。推荐实现：

```python
import os
from pathlib import Path

def _disk_root() -> str:
    if os.name == "nt":
        return Path.cwd().anchor or "C:\\"
    return "/"
```

- [ ] **Step 4: pytest PASS + commit**

```powershell
pip install psutil
python -m pytest tests/test_host_info.py -v
git add backend/requirements.txt backend/app/services/host_info.py backend/tests/test_host_info.py
git commit -m "feat(monitor): add host_info via psutil"
```

---

### Task 2: gpu_info（nvidia-smi 解析）

**Files:**
- Create: `backend/app/services/gpu_info.py`
- Create: `backend/tests/test_gpu_info.py`

- [ ] **Step 1: 写测试**

```python
from app.services.gpu_info import parse_nvidia_smi_csv, read_gpu_stats

SAMPLE = "NVIDIA GeForce RTX 4070, 62, 78, 4200, 12282\n"

def test_parse_nvidia_smi_csv():
    g = parse_nvidia_smi_csv(SAMPLE)
    assert g["available"] is True
    assert g["temperature_c"] == 62
    assert g["utilization_percent"] == 78
    assert g["name"].startswith("NVIDIA")

def test_parse_empty_unavailable():
    g = parse_nvidia_smi_csv("")
    assert g["available"] is False
    assert g["temperature_c"] is None

def test_read_gpu_stats_uses_runner(monkeypatch):
    monkeypatch.setattr(
        "app.services.gpu_info._run_nvidia_smi",
        lambda: SAMPLE,
    )
    g = read_gpu_stats()
    assert g["available"] is True
```

- [ ] **Step 2: 实现**

```python
# backend/app/services/gpu_info.py
from __future__ import annotations
import subprocess
from typing import Any


def _unavailable(error: str) -> dict[str, Any]:
    return {
        "available": False,
        "name": None,
        "temperature_c": None,
        "utilization_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "error": error,
    }


def parse_nvidia_smi_csv(text: str) -> dict[str, Any]:
    line = (text or "").strip().splitlines()
    if not line:
        return _unavailable("nvidia-smi empty")
    parts = [p.strip() for p in line[0].split(",")]
    if len(parts) < 5:
        return _unavailable("nvidia-smi parse error")
    try:
        return {
            "available": True,
            "name": parts[0],
            "temperature_c": int(float(parts[1])),
            "utilization_percent": int(float(parts[2])),
            "memory_used_mb": int(float(parts[3])),
            "memory_total_mb": int(float(parts[4])),
            "error": None,
        }
    except ValueError:
        return _unavailable("nvidia-smi parse error")


def _run_nvidia_smi() -> str:
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "nvidia-smi failed").strip()[:200])
    return r.stdout


def read_gpu_stats() -> dict[str, Any]:
    try:
        return parse_nvidia_smi_csv(_run_nvidia_smi())
    except Exception as e:
        return _unavailable(str(e)[:200])
```

- [ ] **Step 3: pytest PASS + commit** `feat(monitor): parse nvidia-smi gpu stats`

---

### Task 3: AssetStore `list_by_status` + snapshot 服务

**Files:**
- Modify: `backend/app/db/repositories/assets.py`
- Modify: `backend/app/services/asset_store.py`
- Create: `backend/app/services/monitor_snapshot.py`
- Create: `backend/tests/test_monitor_snapshot.py`

- [ ] **Step 1: assets repo 增加**

```python
def list_by_status(self, status: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with self._conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM assets
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
        return [dict(r) for r in rows]
```

AssetStore 增加同名委托方法。

- [ ] **Step 2: monitor_snapshot.py**

```python
from datetime import datetime
from app.services.host_info import read_host_stats
from app.services.gpu_info import read_gpu_stats
from app.services.runtime import store, queue
from app.services.llm_runtime import effective_llm_kwargs
import httpx

def _task_row(a: dict) -> dict:
    return {
        "id": a["id"],
        "project_id": a["project_id"],
        "name": a.get("name") or a["id"],
        "type": a.get("type") or "",
        "status": a["status"],
        "model": a.get("model") or "",
        "error": a.get("error"),
        "created_at": a.get("created_at") or "",
    }

def build_snapshot(*, comfy_online: bool | None = None) -> dict:
    generating = [_task_row(a) for a in store.list_by_status("generating", limit=50)]
    failed = [_task_row(a) for a in store.list_by_status("failed", limit=20)]
    # comfy: 调用方可注入；默认尝试 runtime client.health
    if comfy_online is None:
        try:
            from app.services.runtime import client
            comfy_online = bool(client.health())
        except Exception:
            comfy_online = False
    kw = effective_llm_kwargs()
    ollama_online = False
    try:
        base = (kw.get("ollama_base_url") or "").rstrip("/")
        if base:
            r = httpx.get(f"{base}/api/tags", timeout=2.0)
            ollama_online = r.status_code == 200
    except Exception:
        ollama_online = False
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "host": read_host_stats(),
        "gpu": read_gpu_stats(),
        "services": {
            "comfyui": {
                "online": comfy_online,
                "queue": store.queue_depth() + queue.pending_count(),
            },
            "ollama": {
                "online": ollama_online,
                "model": kw.get("ollama_model") or "",
            },
        },
        "tasks": {
            "badge_count": len(generating) + len(failed),
            "generating": generating,
            "failed_recent": failed,
        },
    }
```

- [ ] **Step 3: 测试用 tmp AssetStore**

```python
def test_snapshot_badge_counts(tmp_path, monkeypatch):
    from app.services.asset_store import AssetStore
    from app.services import monitor_snapshot as ms
    store = AssetStore(tmp_path / "t.db")
    a = store.create(project_id="p1", name="A", type="character", prompt_cn="x", prompt_en="", model="sdxl")
    store.update("p1", a["id"], status="failed", error="boom")
    b = store.create(project_id="p1", name="B", type="scene", prompt_cn="y", prompt_en="", model="sdxl")
    monkeypatch.setattr(ms, "store", store)
    class Q:
        def pending_count(self): return 0
    monkeypatch.setattr(ms, "queue", Q())
    monkeypatch.setattr(ms, "read_host_stats", lambda: {"cpu_percent": 1, "memory_percent": 2, "disk_percent": 3})
    monkeypatch.setattr(ms, "read_gpu_stats", lambda: {"available": True, "temperature_c": 50, "utilization_percent": 10, "name": "X", "memory_used_mb": 1, "memory_total_mb": 2, "error": None})
    monkeypatch.setattr(ms, "effective_llm_kwargs", lambda: {"ollama_base_url": "", "ollama_model": "m"})
    snap = ms.build_snapshot(comfy_online=True)
    assert snap["tasks"]["badge_count"] == 2  # 1 failed + 1 generating
    assert len(snap["tasks"]["failed_recent"]) == 1
```

- [ ] **Step 4: commit** `feat(monitor): build snapshot from store and gpu/host`

---

### Task 4: `/api/monitor/snapshot` + 旧接口

**Files:**
- Modify: `backend/app/api/monitor.py`
- Create: `backend/tests/test_monitor_api.py`

- [ ] **Step 1: 重写 monitor router**

```python
from fastapi import APIRouter, HTTPException
from app.services.monitor_snapshot import build_snapshot

router = APIRouter()

@router.get("/snapshot")
async def get_snapshot():
    return build_snapshot()

@router.get("/system")
async def get_system_stats():
    s = build_snapshot()
    gpu = s["gpu"]
    return {
        "cpu": s["host"].get("cpu_percent") or 0,
        "memory": s["host"].get("memory_percent") or 0,
        "gpu": gpu.get("utilization_percent") or 0,
        "disk": s["host"].get("disk_percent") or 0,
    }

@router.get("/tasks")
async def get_tasks():
    s = build_snapshot()
    return s["tasks"]["generating"] + s["tasks"]["failed_recent"]

@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    raise HTTPException(status_code=501, detail="任务暂停未实现")

@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    raise HTTPException(status_code=501, detail="任务恢复未实现")

@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    raise HTTPException(status_code=501, detail="任务取消未实现")
```

- [ ] **Step 2: TestClient** patch `build_snapshot` 返回固定 dict，断言 `/snapshot` 200 且含 `gpu`/`tasks`

- [ ] **Step 3: commit** `feat(api): add monitor snapshot endpoint`

---

# Phase L — LLM 多云 + Ollama 列表

### Task 5: llm_settings_store profiles 迁移

**Files:**
- Modify: `backend/app/services/llm_settings_store.py`
- Modify: `backend/tests/test_llm_settings_store.py`

- [ ] **Step 1: 扩展行为**

`_normalize(file_cfg)`：
- 若存在 `cloud_profiles` 列表则用之；
- 否则若有旧 `cloud_llm_base_url` 或 key/model，生成 `[{id:"legacy", name:"Legacy", base_url, api_key, model}]`，`active_cloud_id="legacy"`。
- 默认预置模板（仅当 profiles 空且无旧字段）：`[{id:"deepseek", name:"DeepSeek", base_url:"https://api.deepseek.com/v1", api_key:"", model:"deepseek-chat"}]`，`active_cloud_id="deepseek"`。

`get_effective(**defaults)`：
- 合并 ollama_* / timeout；
- 取 active profile → 填 `cloud_llm_base_url/api_key/model`；
- `api_key_set` 看 active key。

`get_public(**defaults)`：
```python
{
  "ollama_base_url", "ollama_model", "llm_timeout_sec",
  "active_cloud_id",
  "cloud_profiles": [
     {"id","name","base_url","model","api_key_set","api_key_masked"}
  ],
  # 兼容旧前端字段（从 active 导出）：
  "cloud_llm_base_url", "cloud_llm_model", "api_key_set", "cloud_llm_api_key_masked"
}
```

`save(data)`：
- 支持 `cloud_profiles` 整表替换；每个 profile 若 `api_key` 为 `""` 或不传，保留文件中同 id 旧 key；
- 支持 `active_cloud_id`、ollama_*、timeout。

- [ ] **Step 2: 测试**

```python
def test_migrate_legacy_flat(tmp_path):
    path = tmp_path / "llm_settings.json"
    path.write_text('{"cloud_llm_base_url":"https://x","cloud_llm_api_key":"sk-ab","cloud_llm_model":"m"}', encoding="utf-8")
    store = LlmSettingsStore(path)
    pub = store.get_public(ollama_base_url="http://o", ollama_model="q", cloud_llm_base_url="", cloud_llm_api_key="", cloud_llm_model="", llm_timeout_sec=60)
    assert pub["active_cloud_id"] == "legacy"
    assert pub["cloud_profiles"][0]["api_key_set"] is True
    assert "sk-ab" not in str(pub)

def test_active_profile_in_effective(tmp_path):
    store = LlmSettingsStore(tmp_path / "s.json")
    store.save({
        "active_cloud_id": "deepseek",
        "cloud_profiles": [
            {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-ds", "model": "deepseek-chat"}
        ],
    })
    eff = store.get_effective(ollama_base_url="http://o", ollama_model="q", cloud_llm_base_url="", cloud_llm_api_key="", cloud_llm_model="", llm_timeout_sec=60)
    assert eff["cloud_llm_base_url"].startswith("https://api.deepseek")
    assert eff["cloud_llm_api_key"] == "sk-ds"
```

- [ ] **Step 3: 确认 `llm_runtime.effective_llm_kwargs` 无需改签名**（仍调 get_effective）— 若 get_effective 已填 cloud_* 则 runtime 不动。

- [ ] **Step 4: commit** `feat(llm): multi cloud profiles with legacy migration`

---

### Task 6: settings API — ollama models + paths + PUT profiles

**Files:**
- Modify: `backend/app/api/settings_llm.py`
- Modify: `backend/tests/test_settings_llm_api.py`

- [ ] **Step 1: 增加路由**

```python
@router.get("/paths")
async def get_paths():
    return {
        "modelhub_root": str(settings.modelhub_root),
        "outputs_dir": str(settings.media_mount_dir),
        "sqlite_path": str(settings.resolved_sqlite_path),
    }

@router.get("/llm/ollama/models")
async def list_ollama_models():
    kw = effective_llm_kwargs()
    base = (kw.get("ollama_base_url") or "").rstrip("/")
    if not base:
        raise HTTPException(400, detail="ollama_base_url 未配置")
    try:
        r = httpx.get(f"{base}/api/tags", timeout=5.0)
        r.raise_for_status()
        models = [{"name": m.get("name")} for m in (r.json().get("models") or []) if m.get("name")]
        return {"models": models}
    except Exception as e:
        raise HTTPException(502, detail=f"无法连接 Ollama: {e}") from e
```

PUT body 扩展可选字段：`active_cloud_id: Optional[str]`、`cloud_profiles: Optional[list[dict]]`。

- [ ] **Step 2: 测试** respx mock tags；PUT profiles 后 GET public 含两条且无明文 key

- [ ] **Step 3: commit** `feat(api): ollama model list, paths, and profile PUT`

---

# Phase U — 前端

### Task 7: monitorApi + MainLayout

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/layouts/MainLayout.jsx`

- [ ] **Step 1: api.js**

```javascript
export const monitorApi = {
  snapshot() {
    return request('/api/monitor/snapshot')
  },
}
```

settingsApi 增加：

```javascript
  getPaths() { return request('/api/settings/paths') },
  listOllamaModels() { return request('/api/settings/llm/ollama/models') },
```

- [ ] **Step 2: MainLayout**  
  - `useEffect` 每 4000ms 调 `monitorApi.snapshot`（document.visibilityState === 'visible' 时）；失败不回退假 78%。  
  - GPU：`available ? \`${temp}°C · ${util}%\` : 'GPU 不可用'`  
  - Badge：`tasks.badge_count`；Popover 列表 generating / failed_recent；点击 `navigate(\`/workbench/${project_id}/assets\`)`

- [ ] **Step 3: commit** `feat(ui): wire header GPU and task badge to snapshot`

---

### Task 8: MonitorDashboard 真实化

**Files:**
- Modify: `frontend/src/pages/monitor/MonitorDashboard.jsx`

- [ ] **Step 1: 删除假 setInterval 抖动与 mock 任务数组**  
- [ ] **Step 2: 挂载 + 轮询 snapshot，渲染 host/gpu/services/tasks**  
- [ ] **Step 3: 暂停/恢复按钮改为 disabled 或点击 message.info('尚未实现')**  
- [ ] **Step 4: commit** `feat(monitor): replace mock dashboard with snapshot polling`

---

### Task 9: SystemSettings + ModelConfig LLM UI

**Files:**
- Modify: `frontend/src/pages/admin/SystemSettings.jsx`
- Modify: `frontend/src/pages/admin/ModelConfig.jsx`

- [ ] **Step 1: SystemSettings**  
  - 路径卡：`getPaths()` 只读 Input  
  - Ollama 模型：`listOllamaModels()` → Select（`mode` 可手填：Ant `Select` + `showSearch`，options 来自 tags；无列表时仍可输入）  
  - 云端：表格/列表编辑 `cloud_profiles`；「设为当前」设 `active_cloud_id`；保存 `putLlm`；空 key 不覆盖  
  - 并发/界面/日志：不改逻辑  

- [ ] **Step 2: ModelConfig LLM Tab** 同步同一套字段与保存；SD Tab 去掉写死「GPU 45%」，可显示 snapshot.gpu 或文案「见监控面板」；queue 用 `modelsApi.services()` 返回值  

- [ ] **Step 3: commit** `feat(admin): ollama model select and multi-cloud profiles UI`

---

### Task 10: README + 回归

- [ ] **Step 1: README「当前状态」补一句**：监控快照/顶栏 GPU·任务/多云 LLM 已真实；暂停任务与 RAG/提示词库仍 mock  

- [ ] **Step 2: 回归**

```powershell
cd backend
python -m pytest tests/test_host_info.py tests/test_gpu_info.py tests/test_monitor_snapshot.py tests/test_monitor_api.py tests/test_llm_settings_store.py tests/test_settings_llm_api.py tests/test_prompts_polish_api.py tests/test_script_expand.py tests/test_scripts_expand_api.py tests/test_asset_queue.py tests/test_storyboard_generate.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: commit** `docs: note real monitor and multi-cloud LLM in README`

---

## Spec coverage

| Spec | Tasks |
|---|---|
| snapshot + nvidia-smi + host | 1–4 |
| 顶栏 °C·% + 任务角标下拉 | 7 |
| MonitorDashboard 去假 | 8 |
| cloud_profiles + 迁移 + DeepSeek 预置 | 5 |
| Ollama tags + paths | 6, 9 |
| ModelConfig 去写死 GPU | 9 |
| 并发/界面/日志不动 | 9（明确不改） |
| pause 501 | 4, 8 |
| 回归 | 10 |

## Placeholder scan
无 TBD；关键代码与命令已给出。`host_info` 磁盘路径用平台分支实现，勿照抄单行伪代码。
