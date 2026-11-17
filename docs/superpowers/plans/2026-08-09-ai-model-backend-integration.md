# AI Model Backend Integration (Image-First) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **路径约定（重要）**：模型根目录用环境变量 `MODELHUB_ROOT` 表示，不写死盘符。
> 公司电脑 = `E:\ModelHub`；家里电脑 = `D:\ModelHub`。后端 `settings.py` 默认值取公司机 `E:\ModelHub`，可被环境变量 `MODELHUB_ROOT` 覆盖。

**Goal:** 将 VisionForge `POST /api/assets/{project_id}/generate` 接到本地 ComfyUI，异步出图；默认 SDXL，可切换 SD1.5 / Flux GGUF。

**Architecture:** 进程内资产仓库 + 单 worker 串行队列；`ComfyUIClient` 负责 submit/poll/download；workflow JSON 模板填参后提交 `http://127.0.0.1:8188`；产物落到 `%MODELHUB_ROOT%\outputs\assets\` 并由 `/media` 静态挂载。

**Tech Stack:** FastAPI、httpx、pydantic-settings、pytest、ComfyUI HTTP API

**Spec:** `docs/superpowers/specs/2026-08-09-ai-model-backend-integration-design.md`

**范围边界:**
- ✅ settings / comfyui_client / workflows / asset_queue / assets API / models 探活 / `/media`
- ❌ storyboard、视频、TTS、RAG、Redis、持久化 DB

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/core/settings.py` | 环境配置 |
| `backend/app/core/__init__.py` | 包标记 |
| `backend/app/services/comfyui_client.py` | ComfyUI HTTP 客户端 |
| `backend/app/services/asset_store.py` | 进程内资产 dict |
| `backend/app/services/asset_queue.py` | 串行队列 + worker |
| `backend/app/services/workflows/__init__.py` | `build_workflow(model, prompt)` |
| `backend/app/services/workflows/sd15.json` | SD1.5 txt2img 图 |
| `backend/app/services/workflows/sdxl.json` | SDXL txt2img 图 |
| `backend/app/services/workflows/flux_gguf.json` | Flux GGUF txt2img 图 |
| `backend/app/api/assets.py` | 真实 generate + 详情读 store |
| `backend/app/api/models.py` | ComfyUI 探活 + queue |
| `backend/app/main.py` | `/media` 挂载 + 启动 worker |
| `backend/tests/test_comfyui_client.py` | client 单测 |
| `backend/tests/test_workflows.py` | 填参单测 |
| `backend/tests/test_asset_queue.py` | 队列状态机单测 |
| `backend/requirements-dev.txt` | pytest |

工作目录约定：所有命令在 `backend/` 下执行（`cd backend`），保证 `app` 包可导入。

---

### Task 1: Settings + pytest 脚手架

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/settings.py`
- Create: `backend/requirements-dev.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: 写 settings 模块**

```python
# backend/app/core/settings.py
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    comfyui_base_url: str = "http://127.0.0.1:8188"
    # 模型根目录：公司机默认 E:\ModelHub；家里机设 D:\ModelHub（通过环境变量 MODELHUB_ROOT 覆盖）
    modelhub_root: Path = Path(os.environ.get("MODELHUB_ROOT", r"E:\ModelHub"))
    poll_timeout_sec: float = 600.0
    poll_interval_sec: float = 1.5

    @property
    def assets_output_dir(self) -> Path:
        return self.modelhub_root / "outputs" / "assets"

    @property
    def media_mount_dir(self) -> Path:
        return self.modelhub_root / "outputs"


settings = Settings()
```

```python
# backend/app/core/__init__.py
from app.core.settings import settings

__all__ = ["settings"]
```

```text
# backend/requirements-dev.txt
pytest==8.3.3
pytest-asyncio==0.24.0
respx==0.21.1
```

```python
# backend/tests/__init__.py
# backend/tests/conftest.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 2: 安装 dev 依赖并冒烟 import**

```powershell
cd backend
pip install -r requirements-dev.txt
python -c "from app.core.settings import settings; print(settings.comfyui_base_url)"
```

Expected: `http://127.0.0.1:8188`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core backend/requirements-dev.txt backend/tests
git commit -m "feat(backend): add settings and pytest scaffolding"
```

---

### Task 2: ComfyUIClient（TDD）

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/comfyui_client.py`
- Create: `backend/tests/test_comfyui_client.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_comfyui_client.py
import httpx
import respx
import pytest
from app.services.comfyui_client import ComfyUIClient


@pytest.fixture
def client():
    return ComfyUIClient(base_url="http://127.0.0.1:8188", timeout=5.0)


@respx.mock
def test_health_ok(client):
    respx.get("http://127.0.0.1:8188/system_stats").mock(
        return_value=httpx.Response(200, json={"system": {}})
    )
    assert client.health() is True


@respx.mock
def test_health_down(client):
    respx.get("http://127.0.0.1:8188/system_stats").mock(
        side_effect=httpx.ConnectError("down")
    )
    assert client.health() is False


@respx.mock
def test_submit_returns_prompt_id(client):
    respx.post("http://127.0.0.1:8188/prompt").mock(
        return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
    )
    assert client.submit_workflow({"1": {}}) == "abc-123"


@respx.mock
def test_poll_history_completed(client):
    respx.get("http://127.0.0.1:8188/history/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "abc-123": {
                    "outputs": {
                        "9": {
                            "images": [
                                {"filename": "out.png", "subfolder": "", "type": "output"}
                            ]
                        }
                    }
                }
            },
        )
    )
    meta = client.poll_history("abc-123", timeout_sec=2.0, interval_sec=0.01)
    assert meta["filename"] == "out.png"


@respx.mock
def test_download_image(client, tmp_path):
    respx.get("http://127.0.0.1:8188/view").mock(
        return_value=httpx.Response(200, content=b"PNGDATA")
    )
    dest = tmp_path / "a.png"
    client.download_image({"filename": "out.png", "subfolder": "", "type": "output"}, dest)
    assert dest.read_bytes() == b"PNGDATA"
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd backend
pytest tests/test_comfyui_client.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现客户端**

```python
# backend/app/services/__init__.py
# empty

# backend/app/services/comfyui_client.py
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/system_stats", timeout=self.timeout)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def submit_workflow(self, workflow: dict[str, Any]) -> str:
        r = httpx.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"no prompt_id: {data}")
        return prompt_id

    def poll_history(
        self,
        prompt_id: str,
        timeout_sec: float = 600.0,
        interval_sec: float = 1.5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            r = httpx.get(f"{self.base_url}/history/{prompt_id}", timeout=self.timeout)
            r.raise_for_status()
            hist = r.json()
            entry = hist.get(prompt_id)
            if entry:
                for node_out in entry.get("outputs", {}).values():
                    images = node_out.get("images") or []
                    if images:
                        return images[0]
                raise ComfyUIError(f"history has no images: {entry}")
            time.sleep(interval_sec)
        raise ComfyUIError(f"poll timeout after {timeout_sec}s")

    def download_image(self, image_meta: dict[str, Any], dest: Path) -> Path:
        params = {
            "filename": image_meta["filename"],
            "subfolder": image_meta.get("subfolder") or "",
            "type": image_meta.get("type") or "output",
        }
        r = httpx.get(f"{self.base_url}/view", params=params, timeout=self.timeout)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
cd backend
pytest tests/test_comfyui_client.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services backend/tests/test_comfyui_client.py
git commit -m "feat(backend): add ComfyUI HTTP client"
```

---

### Task 3: Workflow 模板与填参（TDD）

**Files:**
- Create: `backend/app/services/workflows/__init__.py`
- Create: `backend/app/services/workflows/sd15.json`
- Create: `backend/app/services/workflows/sdxl.json`
- Create: `backend/app/services/workflows/flux_gguf.json`
- Create: `backend/tests/test_workflows.py`

节点 ID 约定（填参函数依赖这些 ID，勿改）：
- SD/SDXL：`3`=KSampler, `4`=CheckpointLoaderSimple, `6`=CLIPTextEncode(positive), `7`=CLIPTextEncode(negative), `5`=EmptyLatentImage, `8`=VAEDecode, `9`=SaveImage
- Flux：`10`=UnetLoaderGGUF, `11`=CLIPLoaderGGUF(t5), `12`=CLIPLoader(clip_l), `13`=DualCLIPLoader 或分开；实现时用下方 JSON 的固定 ID

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_workflows.py
import pytest
from app.services.workflows import SUPPORTED_MODELS, build_workflow


def test_supported_models():
    assert set(SUPPORTED_MODELS) == {"sdxl", "sd15", "flux"}


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="unknown model"):
        build_workflow("nope", "a cat")


def test_sdxl_injects_prompt_and_checkpoint():
    wf = build_workflow("sdxl", "a red apple")
    assert wf["6"]["inputs"]["text"] == "a red apple"
    assert wf["4"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"
    assert wf["5"]["inputs"]["width"] == 1024


def test_sd15_defaults():
    wf = build_workflow("sd15", "portrait")
    assert wf["4"]["inputs"]["ckpt_name"] == "v1-5-pruned-emaonly.safetensors"
    assert wf["5"]["inputs"]["width"] == 512


def test_flux_uses_gguf_names():
    wf = build_workflow("flux", "cyberpunk city")
    assert "flux1-dev-Q4_K_S.gguf" in str(wf)
    assert "t5-v1_1-xxl-encoder-Q4_K_S.gguf" in str(wf) or "clip_l.safetensors" in str(wf)
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd backend
pytest tests/test_workflows.py -v
```

Expected: FAIL

- [ ] **Step 3: 写入三个 JSON 模板**

`sd15.json` / `sdxl.json`（结构相同，仅默认 ckpt/尺寸不同；填参会覆盖）：

```json
{
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 0,
      "steps": 20,
      "cfg": 7.0,
      "sampler_name": "euler",
      "scheduler": "normal",
      "denoise": 1.0,
      "model": ["4", 0],
      "positive": ["6", 0],
      "negative": ["7", 0],
      "latent_image": ["5", 0]
    }
  },
  "4": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": { "ckpt_name": "PLACEHOLDER.safetensors" }
  },
  "5": {
    "class_type": "EmptyLatentImage",
    "inputs": { "width": 512, "height": 512, "batch_size": 1 }
  },
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "", "clip": ["4", 1] }
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "bad quality, blurry", "clip": ["4", 1] }
  },
  "8": {
    "class_type": "VAEDecode",
    "inputs": { "samples": ["3", 0], "vae": ["4", 2] }
  },
  "9": {
    "class_type": "SaveImage",
    "inputs": { "filename_prefix": "vf_asset", "images": ["8", 0] }
  }
}
```

`flux_gguf.json`（依赖 ComfyUI-GGUF 节点；若节点类名与本地安装不一致，手工冒烟时按 ComfyUI 报错微调 class_type，填参键名保持）：

```json
{
  "10": {
    "class_type": "UnetLoaderGGUF",
    "inputs": { "unet_name": "flux1-dev-Q4_K_S.gguf" }
  },
  "11": {
    "class_type": "CLIPLoaderGGUF",
    "inputs": { "clip_name": "t5-v1_1-xxl-encoder-Q4_K_S.gguf", "type": "flux" }
  },
  "12": {
    "class_type": "CLIPLoader",
    "inputs": { "clip_name": "clip_l.safetensors", "type": "flux" }
  },
  "13": {
    "class_type": "DualCLIPLoader",
    "inputs": {
      "clip_name1": "clip_l.safetensors",
      "clip_name2": "t5-v1_1-xxl-encoder-Q4_K_S.gguf",
      "type": "flux"
    }
  },
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "", "clip": ["13", 0] }
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "", "clip": ["13", 0] }
  },
  "14": {
    "class_type": "EmptySD3LatentImage",
    "inputs": { "width": 1024, "height": 1024, "batch_size": 1 }
  },
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 0,
      "steps": 8,
      "cfg": 1.0,
      "sampler_name": "euler",
      "scheduler": "simple",
      "denoise": 1.0,
      "model": ["10", 0],
      "positive": ["6", 0],
      "negative": ["7", 0],
      "latent_image": ["14", 0]
    }
  },
  "15": {
    "class_type": "VAELoader",
    "inputs": { "vae_name": "ae.safetensors" }
  },
  "8": {
    "class_type": "VAEDecode",
    "inputs": { "samples": ["3", 0], "vae": ["15", 0] }
  },
  "9": {
    "class_type": "SaveImage",
    "inputs": { "filename_prefix": "vf_flux", "images": ["8", 0] }
  }
}
```

注意：Flux 官方 VAE 文件名若本地为其他路径，在 Task 8 冒烟时按 `%MODELHUB_ROOT%\comfyui\models\vae` 实际文件改 `15.inputs.vae_name`。若缺少 Flux VAE，本计划允许 Flux 路径在冒烟中标记为「需补 VAE」而不阻塞 SDXL 验收。

- [ ] **Step 4: 实现 `build_workflow`**

```python
# backend/app/services/workflows/__init__.py
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

SUPPORTED_MODELS = ("sdxl", "sd15", "flux")

_DIR = Path(__file__).resolve().parent

_MODEL_DEFAULTS = {
    "sdxl": {
        "file": "sdxl.json",
        "ckpt": "sd_xl_base_1.0.safetensors",
        "width": 1024,
        "height": 1024,
    },
    "sd15": {
        "file": "sd15.json",
        "ckpt": "v1-5-pruned-emaonly.safetensors",
        "width": 512,
        "height": 512,
    },
    "flux": {
        "file": "flux_gguf.json",
        "ckpt": None,
        "width": 1024,
        "height": 1024,
    },
}


def build_workflow(model: str, prompt: str) -> dict[str, Any]:
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"unknown model: {model}")
    cfg = _MODEL_DEFAULTS[model]
    wf = json.loads((_DIR / cfg["file"]).read_text(encoding="utf-8"))
    wf = copy.deepcopy(wf)
    if "6" in wf:
        wf["6"]["inputs"]["text"] = prompt
    if model in ("sdxl", "sd15"):
        wf["4"]["inputs"]["ckpt_name"] = cfg["ckpt"]
        wf["5"]["inputs"]["width"] = cfg["width"]
        wf["5"]["inputs"]["height"] = cfg["height"]
    if "3" in wf:
        wf["3"]["inputs"]["seed"] = random.randint(0, 2**31 - 1)
    if model == "flux" and "14" in wf:
        wf["14"]["inputs"]["width"] = cfg["width"]
        wf["14"]["inputs"]["height"] = cfg["height"]
    return wf
```

将同一 JSON 内容分别存为 `sd15.json` 与 `sdxl.json`（填参会覆盖 ckpt/尺寸；模板内占位即可）。

- [ ] **Step 5: 跑测试确认通过**

```powershell
cd backend
pytest tests/test_workflows.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workflows backend/tests/test_workflows.py
git commit -m "feat(backend): add SD/SDXL/Flux workflow builders"
```

---

### Task 4: AssetStore + 串行队列（TDD）

**Files:**
- Create: `backend/app/services/asset_store.py`
- Create: `backend/app/services/asset_queue.py`
- Create: `backend/tests/test_asset_queue.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_asset_queue.py
import time
from pathlib import Path
from unittest.mock import MagicMock

from app.services.asset_store import AssetStore
from app.services.asset_queue import AssetQueue


def test_enqueue_sets_generating_then_completed(tmp_path):
    store = AssetStore()
    client = MagicMock()
    client.health.return_value = True
    client.submit_workflow.return_value = "pid-1"
    client.poll_history.return_value = {
        "filename": "x.png",
        "subfolder": "",
        "type": "output",
    }

    def fake_download(meta, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PNG")
        return dest

    client.download_image.side_effect = fake_download

    q = AssetQueue(
        store=store,
        client=client,
        output_root=tmp_path,
        build_workflow=lambda model, prompt: {"ok": True},
        poll_timeout_sec=5.0,
        poll_interval_sec=0.01,
    )
    q.start()
    asset = store.create(
        project_id="p1",
        name="A",
        type="character",
        prompt_cn="猫",
        prompt_en="a cat",
        model="sdxl",
    )
    q.enqueue(asset["id"])
    for _ in range(50):
        cur = store.get("p1", asset["id"])
        if cur["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    q.stop()
    cur = store.get("p1", asset["id"])
    assert cur["status"] == "completed"
    assert cur["image_url"].endswith(".png")
    assert Path(tmp_path / "p1" / f"{asset['id']}.png").exists()


def test_comfyui_down_fails_fast(tmp_path):
    store = AssetStore()
    client = MagicMock()
    client.health.return_value = False
    q = AssetQueue(
        store=store,
        client=client,
        output_root=tmp_path,
        build_workflow=lambda m, p: {},
    )
    q.start()
    asset = store.create(
        project_id="p1",
        name="B",
        type="scene",
        prompt_cn="x",
        prompt_en="",
        model="sdxl",
    )
    q.enqueue(asset["id"])
    for _ in range(50):
        cur = store.get("p1", asset["id"])
        if cur["status"] == "failed":
            break
        time.sleep(0.05)
    q.stop()
    assert store.get("p1", asset["id"])["error"] == "comfyui_unavailable"
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd backend
pytest tests/test_asset_queue.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现 store + queue**

```python
# backend/app/services/asset_store.py
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any, Optional


class AssetStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}

    def create(
        self,
        *,
        project_id: str,
        name: str,
        type: str,
        prompt_cn: str,
        prompt_en: str,
        model: str,
    ) -> dict[str, Any]:
        asset_id = f"asset_{type[:1]}_{uuid.uuid4().hex[:8]}"
        item = {
            "id": asset_id,
            "project_id": project_id,
            "name": name,
            "name_en": name,
            "type": type,
            "status": "generating",
            "prompt_cn": prompt_cn,
            "prompt_en": prompt_en,
            "model": model,
            "image_url": None,
            "error": None,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._lock:
            self._items[self._key(project_id, asset_id)] = item
        return dict(item)

    def get(self, project_id: str, asset_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._items.get(self._key(project_id, asset_id))
            return dict(item) if item else None

    def update(self, project_id: str, asset_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            key = self._key(project_id, asset_id)
            if key not in self._items:
                raise KeyError(asset_id)
            self._items[key].update(fields)
            return dict(self._items[key])

    def queue_depth(self) -> int:
        with self._lock:
            return sum(
                1
                for v in self._items.values()
                if v["status"] == "generating"
            )

    @staticmethod
    def _key(project_id: str, asset_id: str) -> str:
        return f"{project_id}:{asset_id}"
```

```python
# backend/app/services/asset_queue.py
from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, Callable

from app.services.asset_store import AssetStore
from app.services.comfyui_client import ComfyUIClient, ComfyUIError


class AssetQueue:
    def __init__(
        self,
        *,
        store: AssetStore,
        client: ComfyUIClient,
        output_root: Path,
        build_workflow: Callable[[str, str], dict[str, Any]],
        poll_timeout_sec: float = 600.0,
        poll_interval_sec: float = 1.5,
    ) -> None:
        self.store = store
        self.client = client
        self.output_root = output_root
        self.build_workflow = build_workflow
        self.poll_timeout_sec = poll_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self._q: queue.Queue[tuple[str, str]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="asset-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._q.put(("", ""))  # wake
        if self._thread:
            self._thread.join(timeout=5)

    def enqueue(self, asset_id: str, project_id: str | None = None) -> None:
        # project_id looked up from store if omitted: scan
        if project_id is None:
            project_id = self._find_project(asset_id)
        self._q.put((project_id, asset_id))

    def pending_count(self) -> int:
        return self._q.qsize()

    def _find_project(self, asset_id: str) -> str:
        # store keys are project:id — linear scan via private items under lock
        with self.store._lock:
            for key, item in self.store._items.items():
                if item["id"] == asset_id:
                    return item["project_id"]
        raise KeyError(asset_id)

    def _run(self) -> None:
        while not self._stop.is_set():
            project_id, asset_id = self._q.get()
            if not asset_id:
                continue
            self._process(project_id, asset_id)

    def _process(self, project_id: str, asset_id: str) -> None:
        asset = self.store.get(project_id, asset_id)
        if not asset:
            return
        if not self.client.health():
            self.store.update(
                project_id, asset_id, status="failed", error="comfyui_unavailable"
            )
            return
        prompt = asset["prompt_en"] or asset["prompt_cn"]
        try:
            workflow = self.build_workflow(asset["model"], prompt)
            prompt_id = self.client.submit_workflow(workflow)
            meta = self.client.poll_history(
                prompt_id,
                timeout_sec=self.poll_timeout_sec,
                interval_sec=self.poll_interval_sec,
            )
            dest = self.output_root / project_id / f"{asset_id}.png"
            self.client.download_image(meta, dest)
            url = f"/media/assets/{project_id}/{asset_id}.png"
            self.store.update(
                project_id,
                asset_id,
                status="completed",
                image_url=url,
                error=None,
            )
        except (ComfyUIError, OSError, httpx.HTTPError, Exception) as e:
            self.store.update(
                project_id, asset_id, status="failed", error=str(e)[:300]
            )


# fix: import httpx at top
import httpx  # noqa: E402 — move to top when implementing
```

实现时把 `import httpx` 放到文件顶部；`enqueue` 签名在 API 层调用时传 `(project_id, asset_id)` 更清晰——**最终实现请用**：

```python
def enqueue(self, project_id: str, asset_id: str) -> None:
    self._q.put((project_id, asset_id))
```

并相应改测试为 `q.enqueue("p1", asset["id"])`。

- [ ] **Step 4: 跑测试确认通过**

```powershell
cd backend
pytest tests/test_asset_queue.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/asset_store.py backend/app/services/asset_queue.py backend/tests/test_asset_queue.py
git commit -m "feat(backend): add in-memory asset store and serial queue"
```

---

### Task 5: 接线 assets API

**Files:**
- Modify: `backend/app/api/assets.py`
- Create: `backend/app/services/runtime.py`（单例 store/queue/client）

- [ ] **Step 1: 创建 runtime 单例**

```python
# backend/app/services/runtime.py
from app.core.settings import settings
from app.services.asset_queue import AssetQueue
from app.services.asset_store import AssetStore
from app.services.comfyui_client import ComfyUIClient
from app.services.workflows import build_workflow

store = AssetStore()
client = ComfyUIClient(settings.comfyui_base_url)
queue = AssetQueue(
    store=store,
    client=client,
    output_root=settings.assets_output_dir,
    build_workflow=build_workflow,
    poll_timeout_sec=settings.poll_timeout_sec,
    poll_interval_sec=settings.poll_interval_sec,
)
```

- [ ] **Step 2: 改 `assets.py`**

关键改动（保留原 mock 列表 GET；generate/get 走 store）：

```python
# 在 Asset 模型增加可选 error
class Asset(BaseModel):
    id: str
    name: str
    name_en: str
    type: str
    status: str
    prompt_cn: str
    prompt_en: str
    image_url: Optional[str] = None
    created_at: str
    error: Optional[str] = None
    model: Optional[str] = None


class AssetGenerateRequest(BaseModel):
    name: str
    type: str
    prompt_cn: str
    prompt_en: str
    template_id: Optional[str] = None
    model: Optional[str] = "sdxl"


# generate:
from fastapi import HTTPException
from app.services.runtime import queue, store
from app.services.workflows import SUPPORTED_MODELS

@router.post("/{project_id}/generate", response_model=Asset)
async def generate_asset(project_id: str, request: AssetGenerateRequest):
    model = request.model or "sdxl"
    if model not in SUPPORTED_MODELS:
        raise HTTPException(status_code=400, detail=f"unknown model: {model}")
    asset = store.create(
        project_id=project_id,
        name=request.name,
        type=request.type,
        prompt_cn=request.prompt_cn,
        prompt_en=request.prompt_en,
        model=model,
    )
    queue.enqueue(project_id, asset["id"])
    return asset


@router.get("/{project_id}/{asset_id}", response_model=Asset)
async def get_asset(project_id: str, asset_id: str):
    item = store.get(project_id, asset_id)
    if item:
        return item
    all_assets = mock_characters + mock_scenes_assets + mock_props
    for asset in all_assets:
        if asset["id"] == asset_id:
            return asset
    raise HTTPException(status_code=404, detail="资产不存在")
```

- [ ] **Step 3: 用 TestClient 快速手工验证契约（可选脚本）**

```powershell
cd backend
python -c "
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.services import runtime
client = MagicMock(); client.health.return_value=False
runtime.client = client
runtime.queue.client = client
tc = TestClient(app)
r = tc.post('/api/assets/p1/generate', json={'name':'t','type':'prop','prompt_cn':'x','prompt_en':'y','model':'nope'})
assert r.status_code==400
r = tc.post('/api/assets/p1/generate', json={'name':'t','type':'prop','prompt_cn':'x','prompt_en':'y'})
assert r.status_code==200 and r.json()['status']=='generating'
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/assets.py backend/app/services/runtime.py
git commit -m "feat(backend): wire assets generate to ComfyUI queue"
```

---

### Task 6: models 探活 + main 挂载 media / 启动 worker

**Files:**
- Modify: `backend/app/api/models.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 改 models.py 图片服务 URL 与 test**

```python
# mock_services["sd"] 更新：
#   api_url: settings.comfyui_base_url
#   model: "sd_xl_base_1.0 / flux1-dev-Q4 (switchable)"
# 可选新增 flux 条目指向同一 8188

from app.core.settings import settings
from app.services.runtime import client, store, queue

mock_services["sd"]["api_url"] = settings.comfyui_base_url
mock_services["sd"]["model"] = "sdxl|sd15|flux"

@router.get("/services")
async def get_all_services():
    online = client.health()
    depth = store.queue_depth() + queue.pending_count()
    for sid in ("sd",):
        mock_services[sid]["status"] = "online" if online else "offline"
        mock_services[sid]["queue"] = depth
    return list(mock_services.values())

@router.post("/services/{service_id}/test")
async def test_connection(service_id: str):
    if service_id in ("sd", "flux", "ltx"):
        ok = client.health()
        return {
            "status": "success" if ok else "failed",
            "message": "ComfyUI OK" if ok else "ComfyUI unreachable",
            "latency": None,
        }
    return {"status": "success", "message": "mock ok", "latency": "0ms"}
```

- [ ] **Step 2: 改 main.py**

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.core.settings import settings
from app.services.runtime import queue

# 在 include_router 之后：
settings.assets_output_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/media",
    StaticFiles(directory=str(settings.media_mount_dir)),
    name="media",
)

@app.on_event("startup")
async def startup_event():
    queue.start()
    print("asset worker started")
    # 保留原有打印

@app.on_event("shutdown")
async def shutdown_event():
    queue.stop()
```

- [ ] **Step 3: 全量单测**

```powershell
cd backend
pytest tests -v
```

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/models.py backend/app/main.py
git commit -m "feat(backend): ComfyUI health in models and /media mount"
```

---

### Task 7: 手工冒烟（验收）

**Files:** 无代码（除非 Flux VAE 文件名需微调 workflow）

- [ ] **Step 1: 启动 ComfyUI**

```powershell
# 使用安装计划中的 start 脚本，或：
cd %MODELHUB_ROOT%\comfyui
.\.venv\Scripts\python.exe main.py --lowvram --cpu-vae --listen 127.0.0.1 --port 8188
```

- [ ] **Step 2: 启动后端**

```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: 生成 SDXL**

```powershell
curl -X POST http://127.0.0.1:8000/api/assets/demo/generate -H "Content-Type: application/json" -d "{\"name\":\"测试\",\"type\":\"prop\",\"prompt_cn\":\"红苹果\",\"prompt_en\":\"a red apple on a table, product photo\",\"model\":\"sdxl\"}"
```

记下返回的 `id`，每 2s 查询：

```powershell
curl http://127.0.0.1:8000/api/assets/demo/<id>
```

Expected: `status=completed`，浏览器打开 `http://127.0.0.1:8000` + `image_url` 能看到图。

- [ ] **Step 4: 测 sd15；flux 尽力**

同样 POST `model=sd15`。Flux 若缺 VAE 或节点类名不匹配，记录到 `docs/superpowers/specs` 旁注或 commit message，不阻塞 SDXL 验收。

- [ ] **Step 5: 关掉 ComfyUI 再 generate**

Expected: 很快 `failed`，`error=comfyui_unavailable`；`POST /api/models/services/sd/test` 为 failed。

- [ ] **Step 6: 若有 workflow 微调，提交**

```bash
git add backend/app/services/workflows
git commit -m "fix(backend): align Flux/SD workflow with local ComfyUI nodes"
```

---

## Spec Coverage Check

| Spec 要求 | Task |
|---|---|
| settings / COMFYUI_BASE_URL / MODELHUB_ROOT | Task 1 |
| comfyui_client submit/poll/download/health | Task 2 |
| workflow sdxl/sd15/flux + 填参 | Task 3 |
| 串行队列 + 状态机 | Task 4 |
| assets generate/get + model 参数 | Task 5 |
| models 探活 + /media | Task 6 |
| 验收冒烟 | Task 7 |
| 非目标（视频/TTS/RAG…） | 未排任务（有意） |

## Placeholder Scan

无 TBD /「类似 Task N」占位。Flux VAE 文件名允许冒烟时微调（Task 3/7 已写明）。

## Type Consistency

- `SUPPORTED_MODELS = ("sdxl", "sd15", "flux")`
- `AssetQueue.enqueue(project_id, asset_id)`
- `error=comfyui_unavailable` 字符串固定
- `image_url=/media/assets/{project_id}/{asset_id}.png`

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-09-ai-model-backend-integration.md`.

**Two execution options:**

1. **Subagent-Driven（推荐）** — 每任务新开 subagent，任务间审查  
2. **Inline Execution** — 本会话按 executing-plans 连续做  

选哪个？
