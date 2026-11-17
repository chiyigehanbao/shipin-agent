# 前端模型接线与就绪探测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将本地 `master` 对齐到已有 ComfyUI 真实出图能力，并补齐模型就绪探测、资产生成页未就绪禁用、ModelConfig 真探活与必要注释。

**Architecture:** 以 `origin/master` 为唯一主干合并；新增 `model_readiness` 扫 `MODELHUB_ROOT/comfyui/models` 下必需权重；`GET /api/models/readiness` 供前端禁用选项，`generate` 对未就绪 model 返回 400；前端沿用已有 `frontend/src/services/api.js`（不新建 `src/api/`）。

**Tech Stack:** FastAPI、pytest、React 18、Ant Design、Vite proxy（`/api` + `/media`）

**Spec:** `docs/superpowers/specs/2026-08-10-frontend-model-wiring-design.md`

**范围边界:**
- ✅ merge 到 `master`、readiness、generate 400、AssetGeneration 禁用/下载确认、ModelConfig 接线、必要注释
- ❌ storyboard/render/TTS/RAG、采样参数/LoRA API、确认使用/上传/历史版本

---

## File Structure

| Path | Responsibility |
|---|---|
| （merge）`backend/app/**` from `origin/master` | 已有 ComfyUI client / queue / workflows / assets / models 探活 |
| `backend/app/core/settings.py` | 增加 `comfyui_models_dir` 属性（注释说明路径约定） |
| `backend/app/services/model_readiness.py` | 按模型检查必需文件；返回 ready / missing_files |
| `backend/app/api/models.py` | 新增 `GET /readiness`；保持 sd 探活 |
| `backend/app/api/assets.py` | generate 前校验 readiness，未就绪 → 400 |
| `backend/tests/test_model_readiness.py` | 临时目录齐全/缺文件单测 |
| `frontend/src/services/api.js` | 扩展 `modelsApi.readiness` / `testConnection` |
| `frontend/src/pages/workbench/AssetGeneration.jsx` | readiness 禁用 Option；轮询注释；下载已有则核验 |
| `frontend/src/pages/admin/ModelConfig.jsx` | services + test + readiness；默认 8188 |

工作目录约定：
- 后端命令在 `backend/` 下执行（`cd backend`）
- 前端命令在 `frontend/` 下执行

路径约定（与安装规格一致）：
- 权重根目录 = `{MODELHUB_ROOT}/comfyui/models/`
- 例：`sdxl` → `checkpoints/sd_xl_base_1.0.safetensors`

---

### Task 1: 对齐 master 到 origin/master

**Files:**
- Merge: 整个工作区（保留本地规格文档 commits）

- [ ] **Step 1: 确认分支状态**

Run:

```powershell
git status
git log --oneline -5
git log --oneline origin/master -5
```

Expected: 本地 `master` 与 `origin/master` 已 diverge（本地有规格 commits，远程有 backend/frontend 接线 commits）。

- [ ] **Step 2: 拉取并合并 origin/master**

Run:

```powershell
git pull origin master --no-edit
```

若有冲突：
- **优先保留** `docs/superpowers/specs/2026-08-10-frontend-model-wiring-design.md`（本地）
- **优先采用** `origin/master` 的 `backend/` 与 `frontend/src/services/`、`AssetGeneration.jsx`
- 解决后：

```powershell
git add -A
git commit -m "merge: integrate origin/master ComfyUI wiring into local master"
```

- [ ] **Step 3: 验证合并后关键文件存在**

Run:

```powershell
Test-Path backend/app/services/comfyui_client.py
Test-Path backend/app/services/asset_queue.py
Test-Path frontend/src/services/api.js
Select-String -Path frontend/src/pages/workbench/AssetGeneration.jsx -Pattern "assetsApi"
```

Expected: 均为 `True` / 有匹配；本地不再依赖平行 worktree 才能看到真实 generate。

- [ ] **Step 4: 跑已有后端单测（基线）**

Run:

```powershell
cd backend
python -m pytest tests/ -q
```

Expected: PASS（或记录已有失败，本计划后续任务不得引入新失败）。

- [ ] **Step 5: Commit（仅当 Step 2 未自动产生 merge commit 且有未提交解决文件时）**

若 working tree 干净则跳过。否则：

```powershell
git add -A
git commit -m "chore: finish merge of origin/master ComfyUI wiring"
```

---

### Task 2: settings 增加 ComfyUI models 目录属性

**Files:**
- Modify: `backend/app/core/settings.py`
- Test: `backend/tests/test_settings.py`（已有则扩展；没有则创建断言）

- [ ] **Step 1: 写/扩展失败断言（TDD）**

在 `backend/tests/test_settings.py` 增加（若文件已有其它测试则追加）：

```python
from pathlib import Path

from app.core.settings import Settings


def test_comfyui_models_dir_under_modelhub(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELHUB_ROOT", str(tmp_path))
    s = Settings()
    assert s.comfyui_models_dir == tmp_path / "comfyui" / "models"
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```powershell
cd backend
python -m pytest tests/test_settings.py::test_comfyui_models_dir_under_modelhub -v
```

Expected: FAIL（`Settings` 无 `comfyui_models_dir`）或收集失败。

- [ ] **Step 3: 实现属性 + 必要注释**

在 `backend/app/core/settings.py` 的 `Settings` 类中，于 `media_mount_dir` 旁增加：

```python
    @property
    def comfyui_models_dir(self) -> Path:
        # 安装规格约定：权重落在 {MODELHUB_ROOT}/comfyui/models/（相对 checkpoints|unet|...）
        return self.modelhub_root / "comfyui" / "models"
```

确认文件顶部/字段处已有对 `MODELHUB_ROOT`、`COMFYUI_BASE_URL`（即 `comfyui_base_url`）用途的注释；若缺失则补一句，勿写废话。

- [ ] **Step 4: 跑测试确认通过**

Run:

```powershell
cd backend
python -m pytest tests/test_settings.py::test_comfyui_models_dir_under_modelhub -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/app/core/settings.py backend/tests/test_settings.py
git commit -m "feat(backend): expose comfyui_models_dir from MODELHUB_ROOT"
```

---

### Task 3: model_readiness 服务（TDD）

**Files:**
- Create: `backend/app/services/model_readiness.py`
- Create: `backend/tests/test_model_readiness.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_model_readiness.py
from pathlib import Path

from app.services.model_readiness import REQUIRED_FILES, check_model, check_all_models


def _touch(root: Path, rel: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_sdxl_ready_when_checkpoint_exists(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["sdxl"]:
        _touch(models, rel)
    result = check_model("sdxl", models)
    assert result["ready"] is True
    assert result["missing_files"] == []


def test_flux_not_ready_when_vae_missing(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    for rel in REQUIRED_FILES["flux"]:
        if rel.endswith("ae.safetensors"):
            continue
        _touch(models, rel)
    result = check_model("flux", models)
    assert result["ready"] is False
    assert "vae/ae.safetensors" in result["missing_files"]


def test_check_all_models_keys(tmp_path: Path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    all_r = check_all_models(models)
    assert set(all_r.keys()) == {"sdxl", "sd15", "flux"}
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```powershell
cd backend
python -m pytest tests/test_model_readiness.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 model_readiness.py**

```python
# backend/app/services/model_readiness.py
"""模型权重就绪探测。

文件清单与 workflows/*.json / build_workflow 使用的文件名对齐；
路径相对于 {MODELHUB_ROOT}/comfyui/models/。
前端用 readiness 禁用选项；generate 再用同一检查返回 400（双保险）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 与 backend/app/services/workflows 中 checkpoint / unet / clip / vae 文件名一致
REQUIRED_FILES: dict[str, list[str]] = {
    "sdxl": ["checkpoints/sd_xl_base_1.0.safetensors"],
    "sd15": ["checkpoints/v1-5-pruned-emaonly.safetensors"],
    "flux": [
        "unet/flux1-dev-Q4_K_S.gguf",
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/clip_l.safetensors",
        "vae/ae.safetensors",
    ],
}


def check_model(model: str, models_dir: Path) -> dict[str, Any]:
    required = REQUIRED_FILES.get(model)
    if required is None:
        return {"ready": False, "missing_files": [f"unknown model: {model}"]}
    missing = [rel for rel in required if not (models_dir / rel).is_file()]
    return {"ready": len(missing) == 0, "missing_files": missing}


def check_all_models(models_dir: Path) -> dict[str, dict[str, Any]]:
    return {name: check_model(name, models_dir) for name in REQUIRED_FILES}
```

注意：若本机 Flux 的 T5 实际在 `clip/` 而非 `text_encoders/`，以 **workflow JSON 实际引用的路径/ComfyUI 搜索目录** 为准；实现前用 `git show`/`Read` 核对 `flux_gguf.json`。当前 workflow 中 T5 由 DualCLIPLoader 以文件名加载，ComfyUI 可能在 `clip/` 与 `text_encoders/` 均搜索——**探测时按安装规格路径 `text_encoders/` 检查**；若现场文件只在 `clip/`，在 `check_model` 内对 T5/clip 做「多候选路径任一存在即算有」的小扩展，并加注释说明原因。推荐实现：

```python
# 对个别文件允许候选相对路径（ComfyUI 多目录搜索）
_FILE_CANDIDATES: dict[str, list[str]] = {
    "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf": [
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
    ],
    "clip/clip_l.safetensors": [
        "clip/clip_l.safetensors",
    ],
}


def _exists(models_dir: Path, rel: str) -> bool:
    for cand in _FILE_CANDIDATES.get(rel, [rel]):
        if (models_dir / cand).is_file():
            return True
    return False
```

`check_model` 用 `_exists` 替代直接 `is_file()`；`missing_files` 仍报告规格主路径 `rel`。

- [ ] **Step 4: 跑测试确认通过**

Run:

```powershell
cd backend
python -m pytest tests/test_model_readiness.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/model_readiness.py backend/tests/test_model_readiness.py
git commit -m "feat(backend): add model weight readiness checks"
```

---

### Task 4: GET /api/models/readiness + generate 未就绪 400

**Files:**
- Modify: `backend/app/api/models.py`
- Modify: `backend/app/api/assets.py`
- Modify: `backend/tests/test_model_readiness.py`（或新建 `test_models_readiness_api.py`）

- [ ] **Step 1: 写 API 层单测（用临时 models_dir monkeypatch）**

```python
# 追加到 backend/tests/test_model_readiness.py 或新文件
from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import settings


def test_readiness_endpoint_reports_missing(monkeypatch, tmp_path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    monkeypatch.setattr(settings, "modelhub_root", tmp_path)

    client = TestClient(app)
    res = client.get("/api/models/readiness")
    assert res.status_code == 200
    body = res.json()
    assert body["models"]["sdxl"]["ready"] is False
    assert "comfyui_online" in body


def test_generate_rejects_unready_model(monkeypatch, tmp_path):
    models = tmp_path / "comfyui" / "models"
    models.mkdir(parents=True)
    monkeypatch.setattr(settings, "modelhub_root", tmp_path)

    client = TestClient(app)
    res = client.post(
        "/api/assets/proj_test/generate",
        json={
            "name": "t",
            "type": "character",
            "prompt_cn": "a",
            "prompt_en": "a",
            "model": "sdxl",
        },
    )
    assert res.status_code == 400
    assert "not ready" in res.json()["detail"].lower() or "missing" in res.json()["detail"].lower()
```

若 `TestClient` 启动会拉起 queue worker：确认 `runtime` 可安全启动；若 flaky，可只单测 `check_model` + 对 `generate_asset` 抽一层 helper 测，但优先走 HTTP 测。

- [ ] **Step 2: 跑测试确认失败**

Run:

```powershell
cd backend
python -m pytest tests/test_model_readiness.py -k "readiness_endpoint or generate_rejects" -v
```

Expected: FAIL（无 `/readiness` 或 generate 未校验文件）

- [ ] **Step 3: 实现 readiness 路由**

在 `backend/app/api/models.py` 增加：

```python
from app.services.model_readiness import check_all_models

@router.get("/readiness", summary="图片模型权重就绪状态")
async def get_model_readiness():
    # 连接 ≠ 就绪：comfyui_online 探进程；models.*.ready 探磁盘文件
    online = client.health()
    return {
        "models": check_all_models(settings.comfyui_models_dir),
        "comfyui_online": online,
    }
```

- [ ] **Step 4: generate 增加未就绪 400**

在 `backend/app/api/assets.py` 的 `generate_asset` 中，于 `SUPPORTED_MODELS` 检查之后：

```python
from app.core.settings import settings
from app.services.model_readiness import check_model

# ...
model = request.model or "sdxl"
if model not in SUPPORTED_MODELS:
    raise HTTPException(status_code=400, detail=f"unknown model: {model}")

# 双保险：前端应已禁用未就绪模型；此处再拦一层避免白跑队列
ready = check_model(model, settings.comfyui_models_dir)
if not ready["ready"]:
    missing = ", ".join(ready["missing_files"])
    raise HTTPException(
        status_code=400,
        detail=f"model not ready: {model}; missing: {missing}",
    )
```

- [ ] **Step 5: 跑测试确认通过**

Run:

```powershell
cd backend
python -m pytest tests/test_model_readiness.py -v
python -m pytest tests/ -q
```

Expected: PASS

- [ ] **Step 6: Commit**

```powershell
git add backend/app/api/models.py backend/app/api/assets.py backend/tests/test_model_readiness.py
git commit -m "feat(backend): expose readiness API and reject unready generate"
```

---

### Task 5: 前端 api.js 扩展 modelsApi

**Files:**
- Modify: `frontend/src/services/api.js`

- [ ] **Step 1: 扩展 modelsApi**

将 `export const modelsApi` 改为：

```javascript
export const modelsApi = {
  // 模型服务状态（sd 的 online/queue 来自后端真实探活）
  services() {
    return request('/api/models/services')
  },

  // 测试连接：后端对 sd/flux/ltx 打 ComfyUI health
  testConnection(serviceId) {
    return request(`/api/models/services/${serviceId}/test`, { method: 'POST', body: '{}' })
  },

  // 磁盘权重就绪：用于 Select 禁用未下载完的模型
  readiness() {
    return request('/api/models/readiness')
  },
}
```

- [ ] **Step 2: 手工确认语法**

Run:

```powershell
cd frontend
node -e "import('./src/services/api.js').then(m => console.log(Object.keys(m.modelsApi)))"
```

Expected: 打印含 `services`, `testConnection`, `readiness`（若 ESM 在 node 需 `"type":"module"`；失败则用浏览器/Vite 启动时验证，不阻塞）。

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/services/api.js
git commit -m "feat(frontend): add models readiness and testConnection API helpers"
```

---

### Task 6: AssetGeneration 接 readiness 禁用 + 注释

**Files:**
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`

说明：合并后该页已有 `assetsApi.generate`、轮询、`model` Select、`<a download>`。本任务只补 readiness 与注释，不重写整页。

- [ ] **Step 1: 增加 readiness 状态与加载**

在组件状态区增加：

```javascript
const [readiness, setReadiness] = useState({
  sdxl: { ready: true, missing_files: [] },
  sd15: { ready: true, missing_files: [] },
  flux: { ready: true, missing_files: [] },
})
```

在 import 中把 `modelsApi` 一并导入：

```javascript
import { assetsApi, mediaUrl, modelsApi } from '../../services/api.js'
```

挂载时拉取：

```javascript
useEffect(() => {
  let cancelled = false
  ;(async () => {
    try {
      const data = await modelsApi.readiness()
      if (!cancelled && data?.models) setReadiness(data.models)
    } catch (e) {
      // 拉不到 readiness 时不阻断页面；生成仍可能被后端 400
    }
  })()
  return () => {
    cancelled = true
  }
}, [])
```

- [ ] **Step 2: 给轮询补必要注释（若尚未写清）**

在 `pollAsset` 上方确保有类似注释：

```javascript
  // 轮询：每 1.5s 拉详情；completed/failed 停止；单次失败不中断
  // 超时依赖后端任务 failed，前端不另设硬超时（与 poll_timeout_sec 对齐由后端负责）
```

- [ ] **Step 3: Select Option 按 readiness 禁用**

将模型 Select 改为（保留现有布局/文案风格）：

```jsx
<Select value={model} onChange={setModel} style={{ width: '100%' }}>
  {['sdxl', 'sd15', 'flux'].map((id) => {
    const info = readiness[id] || { ready: false, missing_files: ['unknown'] }
    const label =
      id === 'sdxl'
        ? 'SDXL · 1024×1024（默认）'
        : id === 'sd15'
          ? 'SD 1.5 · 512×512（快）'
          : 'Flux GGUF · 1024×1024（高质量）'
    const title = info.ready
      ? undefined
      : `未就绪，缺少: ${(info.missing_files || []).join(', ')}`
    return (
      <Option key={id} value={id} disabled={!info.ready} title={title}>
        {label}
        {!info.ready ? '（未就绪）' : ''}
      </Option>
    )
  })}
</Select>
```

若当前选中 model 变为未就绪，在 readiness 更新后把 `model` 切到第一个 `ready` 的项：

```javascript
useEffect(() => {
  const order = ['sdxl', 'sd15', 'flux']
  if (readiness[model]?.ready) return
  const first = order.find((id) => readiness[id]?.ready)
  if (first) setModel(first)
}, [readiness, model])
```

- [ ] **Step 4: 确认下载按钮对 completed + image_url 可用**

核验已有类似结构（不要重复造按钮）：

```jsx
{currentAsset?.status === 'completed' && currentAsset.image_url && (
  <a href={mediaUrl(currentAsset.image_url)} download target="_blank" rel="noreferrer">
    <Button size="small" icon={<DownloadOutlined />} />
  </a>
)}
```

预览区应用 `<img src={mediaUrl(currentAsset.image_url)} ... />`（合并后应已有）；若仍是 emoji 占位且 `image_url` 存在，替换为真实图片。

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/pages/workbench/AssetGeneration.jsx
git commit -m "feat(frontend): disable unready models on AssetGeneration"
```

---

### Task 7: ModelConfig 真探活与模型选项对齐

**Files:**
- Modify: `frontend/src/pages/admin/ModelConfig.jsx`

- [ ] **Step 1: 引入 API 与状态**

```javascript
import { modelsApi } from '../../services/api.js'
```

将假的 `connectionStatus` 初始值改为加载中语义，例如：

```javascript
const [connectionStatus, setConnectionStatus] = useState({
  sd: 'offline',
  ltx: 'offline',
  llm: 'offline',
  tts: 'offline',
})
const [services, setServices] = useState([])
const [readiness, setReadiness] = useState({})
const [testing, setTesting] = useState(null) // serviceId | null
const [sdApiUrl, setSdApiUrl] = useState('http://127.0.0.1:8188')
const [sdModel, setSdModel] = useState('sdxl')
```

- [ ] **Step 2: 首屏拉取 services + readiness**

```javascript
useEffect(() => {
  let cancelled = false
  ;(async () => {
    try {
      const [list, ready] = await Promise.all([
        modelsApi.services(),
        modelsApi.readiness(),
      ])
      if (cancelled) return
      setServices(list)
      setReadiness(ready.models || {})
      const map = { sd: 'offline', ltx: 'offline', llm: 'offline', tts: 'offline' }
      for (const s of list) {
        map[s.id] = s.status || 'offline'
      }
      setConnectionStatus(map)
      const sd = list.find((s) => s.id === 'sd')
      if (sd?.api_url) setSdApiUrl(sd.api_url)
    } catch (e) {
      message.error(`加载模型服务失败: ${e.message}`)
    }
  })()
  return () => {
    cancelled = true
  }
}, [])
```

- [ ] **Step 3: 真实测试连接**

替换 `handleTestConnection`：

```javascript
const handleTestConnection = async (serviceId) => {
  setTesting(serviceId)
  try {
    const res = await modelsApi.testConnection(serviceId)
    const ok = res.status === 'success'
    setConnectionStatus((prev) => ({ ...prev, [serviceId]: ok ? 'online' : 'offline' }))
    if (ok) message.success(res.message || '连接成功')
    else message.error(res.message || '连接失败')
  } catch (e) {
    setConnectionStatus((prev) => ({ ...prev, [serviceId]: 'offline' }))
    message.error(`测试失败: ${e.message}`)
  } finally {
    setTesting(null)
  }
}
```

按钮：`loading={testing === 'sd'}`（各 tab 对应 serviceId）。

- [ ] **Step 4: SD Tab 默认 URL 与模型 Select**

- API 地址输入框：受控 `value={sdApiUrl}`；**默认/展示以后端返回为准（8188）**，本轮「保存」仍可 toast（规格未要求持久化 config）。
- 模型下拉改为 `sdxl|sd15|flux`，与资产生成一致，并用 readiness 禁用：

```jsx
<Select value={sdModel} onChange={setSdModel} style={{ width: '100%', marginTop: 4 }}>
  {['sdxl', 'sd15', 'flux'].map((id) => {
    const info = readiness[id] || { ready: true, missing_files: [] }
    return (
      <Option key={id} value={id} disabled={!info.ready} title={!info.ready ? `缺少: ${info.missing_files.join(', ')}` : undefined}>
        {id}
        {!info.ready ? '（未就绪）' : ''}
      </Option>
    )
  })}
</Select>
```

- ltx/llm/tts：保留 UI，但测试连接对非 ComfyUI 服务勿假装成功——`testConnection('llm'|'tts')` 后端仍可能返回假成功；**前端对 llm/tts 点击测试时**显示 `message.info('该服务尚未真实接入')` 且可不调用 API，或调用后若规格要求「不误导」则仅 sd 显示真实探活结果。推荐：仅 `sd`（及若 UI 有的图片相关）走真实 test；`llm`/`tts` 按钮提示未接入。

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/pages/admin/ModelConfig.jsx
git commit -m "feat(frontend): wire ModelConfig to real ComfyUI status and readiness"
```

---

### Task 8: 端到端冒烟与验收

**Files:** 无新文件（手工）

- [ ] **Step 1: 启动后端（设置 MODELHUB_ROOT）**

```powershell
$env:MODELHUB_ROOT = "D:\ModelHub"   # 按本机实际路径
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 启动 ComfyUI（另开终端）**

按安装规格：`--lowvram --cpu-vae`，端口 8188。

- [ ] **Step 3: 启动前端**

```powershell
cd frontend
npm run dev
```

- [ ] **Step 4: 验收清单（逐项勾选）**

- [ ] `GET http://127.0.0.1:8000/api/models/readiness` 返回各模型 ready/missing_files
- [ ] 模型配置页：测试连接反映 ComfyUI online/offline；SD API 地址为 8188
- [ ] 资产生成：未就绪模型 Option 禁用且有原因
- [ ] 已就绪模型（优先 sdxl）生成 → 出图 → 下载可用
- [ ] 对未就绪 model 直接 POST generate → 400
- [ ] 关闭 ComfyUI 后 status offline / 生成失败可读
- [ ] 关键关键/关键改代码含规格 §5 注释（readiness 清单来源、轮询、双保险、settings 路径）

- [ ] **Step 5: 最终测试与收尾 commit（若有修复）**

```powershell
cd backend
python -m pytest tests/ -q
```

有修复则：

```powershell
git add -A
git commit -m "fix: address readiness wiring smoke-test issues"
```

---

## Self-Review (plan vs spec)

| Spec 要求 | Task |
|---|---|
| 对齐 master / 少分支 | Task 1 |
| model_readiness + GET readiness | Task 2–4 |
| generate 未就绪 400 | Task 4 |
| AssetGeneration 选模型/生成/轮询/展示/下载 | Task 1（已有）+ Task 6 |
| ModelConfig 探活 / 8188 / 选项一致 | Task 5 + 7 |
| 必要注释 | Task 2–4、6 |
| 单测 readiness | Task 3–4 |
| 不做分镜/参数/上传等 | 无对应任务（刻意） |

**与规格路径差异（有意）：** 规格写 `frontend/src/api/*`；代码库已有 `frontend/src/services/api.js`，计划沿用后者，避免双 API 层。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-10-frontend-model-wiring.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 开新子代理，Task 之间做审查，迭代快  
2. **Inline Execution** — 本会话按 executing-plans 连续执行，设检查点  

选哪一种？
