# 电影感提示词润色融合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地共享电影感润色服务（自研 pack + Ollama 优先/云降级），接通剧本→资产→分镜→生成（含负向注入与分镜出图）。

**Architecture:** `CinematicPolishService` 按 stage 加载 `cinematic_v1` pack，经 `LLMProvider`（Ollama→Cloud）产出统一 JSON；资产/分镜写入 `prompt_en`+`negative_prompt`；`build_workflow` 注入节点 `7`；分镜出图创建关联 asset 入现有 `AssetQueue`。

**Tech Stack:** FastAPI、httpx、pytest、React 18、Ant Design、现有 ComfyUI workflow JSON

**Spec:** `docs/superpowers/specs/2026-08-10-cinematic-prompt-polish-design.md`

**范围边界:**
- ✅ polish API、自研 pack、LLM failover、负向注入、剧本/资产/分镜 UI、分镜 generate
- ❌ 造梦师原文嵌入、导演库、RAG、batch polish API、视频模型

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/prompt_packs/cinematic_v1/system.md` | 自研系统提示（工作流+输出契约） |
| `backend/app/prompt_packs/cinematic_v1/ATTRIBUTION.md` | 灵感来源与许可证说明 |
| `backend/app/core/settings.py` | Ollama / Cloud LLM 配置项 |
| `backend/app/services/llm_provider.py` | Ollama 优先，失败降级 Cloud |
| `backend/app/services/cinematic_polish.py` | 加载 pack、组消息、校验、重试一次 |
| `backend/app/api/prompts.py` | 新增 `POST /polish`（保留原模板 CRUD） |
| `backend/app/services/workflows/__init__.py` | `build_workflow(..., negative_prompt=)` 写节点 7 |
| `backend/app/services/asset_store.py` | `negative_prompt` 字段 |
| `backend/app/services/asset_queue.py` | 出图时传入 negative |
| `backend/app/api/assets.py` | 请求/响应带 `negative_prompt` |
| `backend/app/services/storyboard_store.py` | 进程内分镜帧存储（含 negative） |
| `backend/app/api/storyboard.py` | 帧 CRUD 对齐 store；`POST .../frames/{id}/generate` |
| `backend/app/services/runtime.py` | 如需挂 storyboard_store 单例 |
| `backend/tests/test_llm_provider.py` | failover 单测 |
| `backend/tests/test_cinematic_polish.py` | 校验/缺字段重试 |
| `backend/tests/test_workflows.py` | 负向注入 |
| `backend/tests/test_asset_queue.py` | build_workflow 新签名 |
| `backend/tests/test_prompts_polish_api.py` | polish API 契约 |
| `backend/tests/test_storyboard_generate.py` | 分镜入队 |
| `frontend/src/services/api.js` | `promptsApi` / `storyboardApi` |
| `frontend/src/pages/workbench/ScriptWorkshop.jsx` | 场景润色预览+应用 |
| `frontend/src/pages/workbench/AssetGeneration.jsx` | 润色 / 润色并生成 |
| `frontend/src/pages/workbench/Storyboard.jsx` | 润色 + 生成此帧轮询 |

工作目录：后端命令在 `backend/`；前端在 `frontend/`。

---

### Task 1: 自研 cinematic_v1 prompt pack

**Files:**
- Create: `backend/app/prompt_packs/cinematic_v1/system.md`
- Create: `backend/app/prompt_packs/cinematic_v1/ATTRIBUTION.md`
- Create: `backend/app/prompt_packs/__init__.py`（空即可）

- [ ] **Step 1: 写入 ATTRIBUTION**

```markdown
# Attribution

Cinematic prompt workflow in this pack is originally inspired by
「造梦师：AI时代电影视觉指南」/ zy-cinematic-realism
(https://github.com/popopo-99/zy-cinematic-realism), licensed CC BY-NC 4.0.

This repository ships a **rewritten** runtime prompt pack for commercial-friendly use.
It does **not** redistribute the upstream skill source verbatim.
```

- [ ] **Step 2: 写入自研 system.md（完整原文如下，勿改成拷贝造梦师文件）**

```markdown
# Cinematic Visual Prompt Pack v1

You convert scene or asset briefs into grounded live-action frame prompts.

## Workflow
1. Keep user-fixed facts (era, place, characters, event, mood, time, weather, aspect, model limits).
2. Choose one story beat: anticipation, waiting, aftermath, departure, private observation, or interrupted routine (not a poster climax unless asked).
3. Give characters small concrete actions; show emotion via posture, distance, gaze, objects, silence — never pose for camera.
4. Build physical space: foreground / midground / background with 2–4 causal traces of use.
5. Place a real camera (height, distance/shot size); add obstruction only if the position implies it.
6. Motivate every important light from the location (primary, secondary, shadows, highlights, restrained color).
7. Add capture texture last (natural exposure, soft roll-off, mild grain) only if scene-supported.
8. Build 10–20 scene-specific Avoid terms (failure modes only; no generic praise spam).

## Output (JSON only, no markdown fences)
{
  "interpretation_cn": "brief Chinese production summary",
  "prompt_en": "one fluent English final prompt",
  "avoid": "comma-separated English negatives",
  "prompt_cn": "optional short Chinese summary"
}

Rules: no masterpiece/8K/photorealistic badges; no unmotivated neon/rim/fog; prefer observed film frame language.
If options.return_interpretation is false, still return interpretation_cn as empty string.
Stage hints: script_scene = keyframe for a script beat; asset = character/scene/prop still; storyboard_frame = single shot with given shot_type/angle/movement when provided.
```

- [ ] **Step 3: Commit**

```powershell
git add backend/app/prompt_packs
git commit -m "feat(prompts): add rewritten cinematic_v1 prompt pack"
```

---

### Task 2: Settings — LLM 配置

**Files:**
- Modify: `backend/app/core/settings.py`
- Test: 手动读 settings 即可；无强制新测文件

- [ ] **Step 1: 在 `Settings` 中增加字段**

```python
    # LLM：电影感润色（Ollama 优先，失败降级云端 OpenAI 兼容接口）
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    cloud_llm_base_url: str = ""  # 例 https://api.openai.com/v1
    cloud_llm_api_key: str = ""
    cloud_llm_model: str = "gpt-4o-mini"
    llm_timeout_sec: float = 60.0
```

- [ ] **Step 2: Commit**

```powershell
git add backend/app/core/settings.py
git commit -m "feat(settings): add Ollama and cloud LLM config"
```

---

### Task 3: LLMProvider（Ollama → Cloud）

**Files:**
- Create: `backend/app/services/llm_provider.py`
- Create: `backend/tests/test_llm_provider.py`

- [ ] **Step 1: 写失败测（failover）**

```python
from unittest.mock import MagicMock
import httpx
from app.services.llm_provider import LLMProvider, LLMError


def test_ollama_success_returns_provider_ollama():
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "message": {"content": '{"prompt_en":"a","avoid":"b","interpretation_cn":"c","prompt_cn":""}'}
    }
    resp.raise_for_status = MagicMock()
    client.post.return_value = resp
    p = LLMProvider(
        ollama_base_url="http://ollama",
        ollama_model="qwen",
        cloud_llm_base_url="http://cloud/v1",
        cloud_llm_api_key="k",
        cloud_llm_model="m",
        timeout_sec=5,
        client=client,
    )
    text, provider = p.chat([{"role": "user", "content": "hi"}])
    assert provider == "ollama"
    assert "prompt_en" in text
    assert client.post.call_args.args[0].startswith("http://ollama/")


def test_ollama_fail_falls_back_to_cloud():
    client = MagicMock()

    def post(url, **kwargs):
        if "ollama" in url:
            raise httpx.ConnectError("down", request=MagicMock())
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": "cloud-ok"}}]
        }
        resp.raise_for_status = MagicMock()
        return resp

    client.post.side_effect = post
    p = LLMProvider(
        ollama_base_url="http://ollama",
        ollama_model="qwen",
        cloud_llm_base_url="http://cloud/v1",
        cloud_llm_api_key="k",
        cloud_llm_model="m",
        timeout_sec=5,
        client=client,
    )
    text, provider = p.chat([{"role": "user", "content": "hi"}])
    assert provider == "cloud"
    assert text == "cloud-ok"


def test_both_fail_raises():
    client = MagicMock()
    client.post.side_effect = httpx.ConnectError("down", request=MagicMock())
    p = LLMProvider(
        ollama_base_url="http://ollama",
        ollama_model="qwen",
        cloud_llm_base_url="http://cloud/v1",
        cloud_llm_api_key="k",
        cloud_llm_model="m",
        timeout_sec=5,
        client=client,
    )
    try:
        p.chat([{"role": "user", "content": "hi"}])
        assert False, "expected LLMError"
    except LLMError as e:
        assert "均不可用" in str(e) or "unavailable" in str(e).lower()
```

- [ ] **Step 2: Run 确认失败**

```powershell
cd backend
python -m pytest tests/test_llm_provider.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `llm_provider.py`**

```python
# ============================================
# LLM 调用：Ollama 优先，失败降级 OpenAI 兼容云端
# ============================================
from __future__ import annotations

from typing import Any

import httpx


class LLMError(Exception):
    """本地与云端均不可用，或返回无法使用。"""


class LLMProvider:
    def __init__(
        self,
        *,
        ollama_base_url: str,
        ollama_model: str,
        cloud_llm_base_url: str,
        cloud_llm_api_key: str,
        cloud_llm_model: str,
        timeout_sec: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.ollama_model = ollama_model
        self.cloud_llm_base_url = (cloud_llm_base_url or "").rstrip("/")
        self.cloud_llm_api_key = cloud_llm_api_key or ""
        self.cloud_llm_model = cloud_llm_model
        self.timeout_sec = timeout_sec
        self._client = client or httpx.Client(timeout=timeout_sec)

    def chat(self, messages: list[dict[str, str]]) -> tuple[str, str]:
        """返回 (content, provider) provider in {ollama, cloud}。"""
        try:
            return self._chat_ollama(messages), "ollama"
        except (httpx.HTTPError, LLMError):
            if not self.cloud_llm_base_url or not self.cloud_llm_api_key:
                raise LLMError("本地与云端 LLM 均不可用") from None
            try:
                return self._chat_cloud(messages), "cloud"
            except (httpx.HTTPError, LLMError) as e:
                raise LLMError("本地与云端 LLM 均不可用") from e

    def _chat_ollama(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.ollama_base_url}/api/chat"
        r = self._client.post(
            url,
            json={"model": self.ollama_model, "messages": messages, "stream": False},
        )
        r.raise_for_status()
        data = r.json()
        content = (data.get("message") or {}).get("content")
        if not content:
            raise LLMError("ollama empty content")
        return content

    def _chat_cloud(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.cloud_llm_base_url}/chat/completions"
        r = self._client.post(
            url,
            headers={"Authorization": f"Bearer {self.cloud_llm_api_key}"},
            json={"model": self.cloud_llm_model, "messages": messages, "temperature": 0.4},
        )
        r.raise_for_status()
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("cloud empty content") from e
        if not content:
            raise LLMError("cloud empty content")
        return content
```

- [ ] **Step 4: Run 确认通过**

```powershell
cd backend
python -m pytest tests/test_llm_provider.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/llm_provider.py backend/tests/test_llm_provider.py
git commit -m "feat(llm): add Ollama-first provider with cloud failover"
```

---

### Task 4: CinematicPolishService

**Files:**
- Create: `backend/app/services/cinematic_polish.py`
- Create: `backend/tests/test_cinematic_polish.py`

- [ ] **Step 1: 写校验与重试测**

```python
import json
from unittest.mock import MagicMock
from app.services.cinematic_polish import CinematicPolishService, PolishError


def test_parse_and_validate_ok(tmp_path):
    pack = tmp_path / "system.md"
    pack.write_text("sys", encoding="utf-8")
    llm = MagicMock()
    payload = {
        "interpretation_cn": "理解",
        "prompt_en": "a quiet frame",
        "avoid": "hdr look, plastic skin",
        "prompt_cn": "安静画面",
    }
    llm.chat.return_value = (json.dumps(payload), "ollama")
    svc = CinematicPolishService(pack_path=pack, llm=llm)
    out = svc.polish(
        stage="asset",
        text_cn="旧卫衣程序员",
        text_en="",
        context={},
        return_interpretation=True,
    )
    assert out["prompt_en"] == "a quiet frame"
    assert out["provider"] == "ollama"
    assert out["pack_version"] == "cinematic-v1"


def test_missing_prompt_en_retries_then_errors(tmp_path):
    pack = tmp_path / "system.md"
    pack.write_text("sys", encoding="utf-8")
    llm = MagicMock()
    llm.chat.return_value = (json.dumps({"avoid": "x"}), "ollama")
    svc = CinematicPolishService(pack_path=pack, llm=llm)
    try:
        svc.polish(stage="asset", text_cn="a", text_en="", context={})
        assert False
    except PolishError:
        pass
    assert llm.chat.call_count == 2
```

- [ ] **Step 2: Run 确认失败**

```powershell
cd backend
python -m pytest tests/test_cinematic_polish.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现 service**

```python
# ============================================
# 电影感润色：加载 pack + LLM + JSON 校验（缺字段重试一次）
# ============================================
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.llm_provider import LLMProvider

PACK_VERSION = "cinematic-v1"
DEFAULT_PACK = (
    Path(__file__).resolve().parent.parent / "prompt_packs" / "cinematic_v1" / "system.md"
)


class PolishError(Exception):
    pass


class CinematicPolishService:
    def __init__(self, *, pack_path: Path | None = None, llm: LLMProvider) -> None:
        self.pack_path = pack_path or DEFAULT_PACK
        self.llm = llm

    def polish(
        self,
        *,
        stage: str,
        text_cn: str,
        text_en: str = "",
        context: dict[str, Any] | None = None,
        return_interpretation: bool = True,
    ) -> dict[str, Any]:
        system = self.pack_path.read_text(encoding="utf-8")
        user = self._user_message(stage, text_cn, text_en, context or {}, return_interpretation)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err: Exception | None = None
        for _ in range(2):
            raw, provider = self.llm.chat(messages)
            try:
                data = self._parse_json(raw)
                self._validate(data)
                if not return_interpretation:
                    data["interpretation_cn"] = data.get("interpretation_cn") or ""
                data["provider"] = provider
                data["pack_version"] = PACK_VERSION
                data.setdefault("prompt_cn", "")
                return data
            except (PolishError, json.JSONDecodeError, KeyError, TypeError) as e:
                last_err = e
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "Return ONLY valid JSON with non-empty prompt_en and avoid.",
                    }
                )
        raise PolishError(f"invalid polish output: {last_err}")

    def _user_message(
        self,
        stage: str,
        text_cn: str,
        text_en: str,
        context: dict[str, Any],
        return_interpretation: bool,
    ) -> str:
        return (
            f"stage={stage}\n"
            f"return_interpretation={return_interpretation}\n"
            f"text_cn={text_cn}\n"
            f"text_en={text_en}\n"
            f"context={json.dumps(context, ensure_ascii=False)}"
        )

    def _parse_json(self, raw: str) -> dict[str, Any]:
        raw = raw.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence:
            raw = fence.group(1).strip()
        return json.loads(raw)

    def _validate(self, data: dict[str, Any]) -> None:
        if not str(data.get("prompt_en") or "").strip():
            raise PolishError("missing prompt_en")
        if not str(data.get("avoid") or "").strip():
            raise PolishError("missing avoid")
```

- [ ] **Step 4: Run 确认通过**

```powershell
cd backend
python -m pytest tests/test_cinematic_polish.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/cinematic_polish.py backend/tests/test_cinematic_polish.py
git commit -m "feat(prompts): add CinematicPolishService with validation retry"
```

---

### Task 5: `POST /api/prompts/polish`

**Files:**
- Modify: `backend/app/api/prompts.py`
- Create: `backend/tests/test_prompts_polish_api.py`

- [ ] **Step 1: 写 API 测（mock polish service）**

在 `prompts.py` 中允许依赖注入较麻烦时，用 `unittest.mock.patch`：

```python
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_polish_ok():
    fake = {
        "interpretation_cn": "理解",
        "prompt_en": "frame",
        "avoid": "hdr look",
        "prompt_cn": "画面",
        "provider": "ollama",
        "pack_version": "cinematic-v1",
    }
    with patch("app.api.prompts.get_polish_service") as g:
        g.return_value.polish.return_value = fake
        r = client.post(
            "/api/prompts/polish",
            json={
                "stage": "asset",
                "project_id": "p1",
                "input": {"text_cn": "角色", "text_en": "", "context": {"type": "character"}},
                "options": {"director": None, "return_interpretation": True},
            },
        )
    assert r.status_code == 200
    assert r.json()["prompt_en"] == "frame"
    assert r.json()["provider"] == "ollama"


def test_polish_bad_stage():
    r = client.post(
        "/api/prompts/polish",
        json={"stage": "nope", "project_id": "p1", "input": {"text_cn": "x"}},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run 确认失败**

```powershell
cd backend
python -m pytest tests/test_prompts_polish_api.py -v
```

Expected: FAIL（无 /polish）

- [ ] **Step 3: 在 `prompts.py` 增加模型与端点**

在文件顶部补充 imports 与：

```python
from app.core.settings import settings
from app.services.cinematic_polish import CinematicPolishService, PolishError
from app.services.llm_provider import LLMProvider, LLMError

ALLOWED_STAGES = {"script_scene", "asset", "storyboard_frame"}


class PolishInput(BaseModel):
    text_cn: str
    text_en: str = ""
    context: dict = {}


class PolishOptions(BaseModel):
    director: Optional[str] = None
    return_interpretation: bool = True


class PolishRequest(BaseModel):
    stage: str
    project_id: str = ""
    input: PolishInput
    options: PolishOptions = PolishOptions()


class PolishResponse(BaseModel):
    interpretation_cn: str = ""
    prompt_en: str
    avoid: str
    prompt_cn: str = ""
    provider: str
    pack_version: str


def get_polish_service() -> CinematicPolishService:
    llm = LLMProvider(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        cloud_llm_base_url=settings.cloud_llm_base_url,
        cloud_llm_api_key=settings.cloud_llm_api_key,
        cloud_llm_model=settings.cloud_llm_model,
        timeout_sec=settings.llm_timeout_sec,
    )
    return CinematicPolishService(llm=llm)


@router.post("/polish", response_model=PolishResponse, summary="电影感提示词润色")
async def polish_prompt(body: PolishRequest):
    if body.stage not in ALLOWED_STAGES:
        raise HTTPException(status_code=400, detail=f"invalid stage: {body.stage}")
    svc = get_polish_service()
    try:
        return svc.polish(
            stage=body.stage,
            text_cn=body.input.text_cn,
            text_en=body.input.text_en,
            context=body.input.context,
            return_interpretation=body.options.return_interpretation,
        )
    except (PolishError, LLMError) as e:
        raise HTTPException(status_code=502, detail=str(e))
```

注意：FastAPI 路由顺序上，`POST /polish` 必须注册在 `GET /{template_id}` **之前**，否则 `polish` 会被当成 template_id。将 `/polish` 端点移到 `/{template_id}` 路由上面。

- [ ] **Step 4: Run 确认通过**

```powershell
cd backend
python -m pytest tests/test_prompts_polish_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/prompts.py backend/tests/test_prompts_polish_api.py
git commit -m "feat(api): add POST /api/prompts/polish"
```

---

### Task 6: Workflow 负向注入 + AssetStore/Queue

**Files:**
- Modify: `backend/app/services/workflows/__init__.py`
- Modify: `backend/app/services/asset_store.py`
- Modify: `backend/app/services/asset_queue.py`
- Modify: `backend/tests/test_workflows.py`
- Modify: `backend/tests/test_asset_queue.py`

- [ ] **Step 1: 扩展 workflow 测试**

```python
def test_sdxl_injects_negative_prompt():
    wf = build_workflow("sdxl", "a red apple", negative_prompt="hdr look, plastic skin")
    assert wf["6"]["inputs"]["text"] == "a red apple"
    assert wf["7"]["inputs"]["text"] == "hdr look, plastic skin"


def test_default_negative_when_empty():
    wf = build_workflow("sdxl", "x", negative_prompt="")
    assert "bad quality" in wf["7"]["inputs"]["text"]
```

- [ ] **Step 2: Run 确认失败**

```powershell
cd backend
python -m pytest tests/test_workflows.py::test_sdxl_injects_negative_prompt -v
```

Expected: FAIL（签名不匹配）

- [ ] **Step 3: 改 `build_workflow`**

```python
DEFAULT_NEGATIVE = "bad quality, blurry"


def build_workflow(model: str, prompt: str, negative_prompt: str = "") -> dict[str, Any]:
    """加载模板并填入 prompt / negative / checkpoint / 分辨率 / seed。"""
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"unknown model: {model}")
    cfg = _MODEL_DEFAULTS[model]
    wf = json.loads((_DIR / cfg["file"]).read_text(encoding="utf-8"))
    wf = copy.deepcopy(wf)
    if "6" in wf:
        wf["6"]["inputs"]["text"] = prompt
    neg = (negative_prompt or "").strip() or DEFAULT_NEGATIVE
    if "7" in wf:
        wf["7"]["inputs"]["text"] = neg
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

- [ ] **Step 4: AssetStore.create 增加 `negative_prompt: str = ""`，写入 item**

- [ ] **Step 5: AssetQueue**

- 类型：`build_workflow: Callable[..., dict[str, Any]]`（或 `Callable[[str, str, str], dict]`）
- `_process` 内：

```python
        prompt = asset["prompt_en"] or asset["prompt_cn"]
        negative = asset.get("negative_prompt") or ""
        workflow = self.build_workflow(asset["model"], prompt, negative)
```

- [ ] **Step 6: 更新 `test_asset_queue.py` 的 lambda 为 `lambda model, prompt, negative="": {"ok": True}`**

- [ ] **Step 7: Run**

```powershell
cd backend
python -m pytest tests/test_workflows.py tests/test_asset_queue.py -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```powershell
git add backend/app/services/workflows/__init__.py backend/app/services/asset_store.py backend/app/services/asset_queue.py backend/tests/test_workflows.py backend/tests/test_asset_queue.py
git commit -m "feat(comfy): inject negative_prompt into workflow node 7"
```

---

### Task 7: Assets API 带上 negative_prompt

**Files:**
- Modify: `backend/app/api/assets.py`

- [ ] **Step 1: 模型字段**

`Asset` 与 `AssetGenerateRequest` 增加：

```python
    negative_prompt: Optional[str] = None
```

`generate_asset` 里 `store.create(..., negative_prompt=request.negative_prompt or "")`。

- [ ] **Step 2: 快速测（可加在现有 assets 测或手动）**

若无现成 API 测，新增 `tests/test_assets_negative.py`：

```python
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_generate_accepts_negative_prompt():
    with patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.assets.queue.enqueue"):
            r = client.post(
                "/api/assets/p1/generate",
                json={
                    "name": "A",
                    "type": "character",
                    "prompt_cn": "猫",
                    "prompt_en": "a cat",
                    "negative_prompt": "hdr look",
                    "model": "sdxl",
                },
            )
    assert r.status_code == 200
    assert r.json().get("negative_prompt") == "hdr look"
```

- [ ] **Step 3: Run + Commit**

```powershell
cd backend
python -m pytest tests/test_assets_negative.py -v
git add backend/app/api/assets.py backend/tests/test_assets_negative.py
git commit -m "feat(assets): accept and store negative_prompt"
```

---

### Task 8: 分镜 Store + generate 复用 AssetQueue

**Files:**
- Create: `backend/app/services/storyboard_store.py`
- Modify: `backend/app/api/storyboard.py`
- Modify: `backend/app/services/runtime.py`（导出 `storyboard_store`）
- Create: `backend/tests/test_storyboard_generate.py`

**设计要点：**  
`POST /api/storyboard/{project_id}/frames/{frame_id}/generate` 用帧的 `prompt_en`/`negative_prompt` 在 `AssetStore` 创建 `type="storyboard"` 资产并 `queue.enqueue`；帧上记录 `asset_id`、`status=generating`。`GET` 帧时若有 `asset_id`，从 asset 同步 `status`/`image_url`/`error`。

- [ ] **Step 1: 实现 `StoryboardStore`**（内存 dict，seed 可拷现有 mock_frames 并加 `negative_prompt: ""`, `asset_id: None`, `error: None`, `model: "sdxl"`）

- [ ] **Step 2: 改 storyboard API**
  - `StoryboardFrame` 增加 `negative_prompt`, `asset_id`, `error`, `model`
  - `GET frames` / `GET frame` 走 store，GET 单帧时 `_sync_from_asset(frame)`
  - `PUT /{project_id}/frames/{frame_id}` 更新 description/prompts/negative（供润色应用）
  - `POST /{project_id}/frames/{frame_id}/generate`：校验 prompt_en、readiness、create asset、enqueue、更新 frame

生成核心逻辑：

```python
    asset = store.create(
        project_id=project_id,
        name=f"storyboard:{frame_id}",
        type="storyboard",
        prompt_cn=frame["prompt_cn"],
        prompt_en=frame["prompt_en"],
        model=model,
        negative_prompt=frame.get("negative_prompt") or "",
    )
    storyboard_store.update(project_id, frame_id, status="generating", asset_id=asset["id"], error=None, model=model)
    queue.enqueue(project_id, asset["id"])
    return storyboard_store.get(project_id, frame_id)
```

- [ ] **Step 3: 测试**

```python
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.services.runtime import storyboard_store

client = TestClient(app)


def test_frame_generate_enqueues_asset():
    # 确保有一帧
    frames = storyboard_store.list("p1")
    fid = frames[0]["id"]
    storyboard_store.update("p1", fid, prompt_en="wide shot test", negative_prompt="hdr look")
    with patch("app.api.storyboard.check_model", return_value={"ready": True, "missing_files": []}):
        with patch("app.api.storyboard.queue.enqueue") as enq:
            r = client.post(f"/api/storyboard/p1/frames/{fid}/generate", json={"model": "sdxl"})
    assert r.status_code == 200
    assert r.json()["status"] == "generating"
    assert r.json()["asset_id"]
    enq.assert_called_once()
```

- [ ] **Step 4: Run + Commit**

```powershell
cd backend
python -m pytest tests/test_storyboard_generate.py -v
git add backend/app/services/storyboard_store.py backend/app/api/storyboard.py backend/app/services/runtime.py backend/tests/test_storyboard_generate.py
git commit -m "feat(storyboard): persist frames and generate via AssetQueue"
```

---

### Task 9: 前端 API 封装

**Files:**
- Modify: `frontend/src/services/api.js`

- [ ] **Step 1: 追加**

```javascript
export const promptsApi = {
  polish(payload) {
    return request('/api/prompts/polish', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
}

export const storyboardApi = {
  list(projectId) {
    return request(`/api/storyboard/${projectId}/frames`)
  },
  get(projectId, frameId) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}`)
  },
  update(projectId, frameId, payload) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  generate(projectId, frameId, payload = {}) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/generate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
}
```

- [ ] **Step 2: Commit**

```powershell
git add frontend/src/services/api.js
git commit -m "feat(frontend): add promptsApi and storyboardApi"
```

---

### Task 10: 剧本页 — 电影感拆解（先前端状态）

**Files:**
- Modify: `frontend/src/pages/workbench/ScriptWorkshop.jsx`

- [ ] **Step 1: 场景对象增加字段**（若尚未有）：`promptEn`, `negativePrompt`, `interpretationCn`

- [ ] **Step 2: 选中场景旁加按钮「电影感拆解」**
  - 调用 `promptsApi.polish({ stage: 'script_scene', project_id, input: { text_cn: sceneText, context: { title } }, options: { return_interpretation: true } })`
  - 结果进入预览 state（`polishPreview`），展示 `interpretation_cn` / `prompt_en` / `avoid` / `provider`
  - 「应用」才写入该场景字段；禁止直接覆盖无确认

- [ ] **Step 3: 「本集全部润色」**：对场景列表 `for` 串行 `await polish`，每场写入预览队列或逐场确认（首版：串行自动写入预览并 toast 进度，仍需每场点应用 —— 或批量应用一键写入全部预览结果；选 **批量润色后一键「全部应用」**）

- [ ] **Step 4: 手动点验 + Commit**

```powershell
git add frontend/src/pages/workbench/ScriptWorkshop.jsx
git commit -m "feat(script): wire cinematic polish with explicit apply"
```

---

### Task 11: 资产页 — 润色 / 润色并生成

**Files:**
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`

- [ ] **Step 1: state** `negativePrompt`, `polishPreview`, `polishing`

- [ ] **Step 2: 「润色」按钮**
  - `promptsApi.polish({ stage: 'asset', project_id: projectId, input: { text_cn: promptCn, text_en: promptEn, context: { type, name, model } } })`
  - 填入 `polishPreview`；显示 provider
  - 「应用」：`setPromptEn` / `setNegativePrompt` / 可选 `setPromptCn`

- [ ] **Step 3: 「润色并生成」**：polish → 应用 → 现有 `assetsApi.generate` 增加 `negative_prompt: negativePrompt`

- [ ] **Step 4: 提示词区增加 Negative 文本框**（受控 `negativePrompt`）

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/pages/workbench/AssetGeneration.jsx
git commit -m "feat(assets): cinematic polish and negative_prompt generate"
```

---

### Task 12: 分镜页 — 润色 + 生成此帧

**Files:**
- Modify: `frontend/src/pages/workbench/Storyboard.jsx`

- [ ] **Step 1: 挂载时 `storyboardApi.list(projectId)` 替换纯本地 mock（若 API 失败再回退本地 seed）**

- [ ] **Step 2: 「润色」** `stage: 'storyboard_frame'`，context 带 `shot_type/angle/movement`；预览后「应用」调用 `storyboardApi.update`

- [ ] **Step 3: 「生成此帧」**  
  - `storyboardApi.generate(projectId, frameId, { model })`  
  - 轮询 `storyboardApi.get` 直至 `completed|failed`（间隔与资产页类似 1.5s）  
  - 用 `mediaUrl(image_url)` 展示

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/pages/workbench/Storyboard.jsx
git commit -m "feat(storyboard): polish prompts and generate frames via queue"
```

---

### Task 13: 回归与规格对照

- [ ] **Step 1: 后端全量相关测**

```powershell
cd backend
python -m pytest tests/test_llm_provider.py tests/test_cinematic_polish.py tests/test_prompts_polish_api.py tests/test_workflows.py tests/test_asset_queue.py tests/test_assets_negative.py tests/test_storyboard_generate.py -v
```

Expected: 全部 PASS

- [ ] **Step 2: 对照 spec 成功标准手测清单**
  1. 三处 polish 均返回 `prompt_en` + `avoid`
  2. 停 Ollama 且配置云 Key 时 `provider=cloud`
  3. 资产/分镜出图 workflow 节点 7 为 Avoid（可在 ComfyUI 历史中确认）
  4. 运行时不依赖 `.cursor/skills/zy-cinematic-realism`

- [ ] **Step 3: 若手测通过，无需额外 commit；若有修复则按问题单独 commit**

---

## Spec coverage checklist

| Spec 项 | Task |
|---|---|
| 自研 pack + ATTRIBUTION | 1 |
| LLM settings / Ollama→Cloud | 2–3 |
| CinematicPolishService + 校验重试 | 4 |
| POST /api/prompts/polish | 5 |
| negative 注入 build_workflow | 6 |
| Asset negative 字段 | 6–7 |
| 分镜 generate + AssetQueue | 8 |
| 前端三页 + 显式应用 | 9–12 |
| 导演库/RAG/造梦师原文 | 明确不做 |

## Placeholder scan

无 TBD/TODO；关键代码与命令已写出。前端 Task 10–12 以交互契约为准（预览→应用），实现时保持与资产页相同的确认模式即可。
