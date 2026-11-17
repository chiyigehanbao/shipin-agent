# 分步提示词包与身份硬锁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按环节蒸馏提示词包，资产冻结 `lock_en`，分镜静图强制粘贴锁，I2V 改用 `motion_prompt_en`，让成片能认出同一角色和同一场戏。

**Architecture:** 无 LLM 的 `prompt_compose` 负责锁注入与 I2V 解析；`CinematicPolishService` 按 stage 换 pack；资产同步/分镜拆解写入新字段；`generate-video` 只吃运动句。Skill 原文不进运行时。

**Tech Stack:** FastAPI、SQLite、pytest、React 18、现有 LLMProvider / Comfy 队列

**Spec:** `docs/superpowers/specs/2026-08-17-stage-prompt-packs-design.md`

**范围边界:**
- ✅ compose、迁移、四 pack、polish 路由、sync、breakdown、I2V、前端锁/运动框、剧本两行约束
- ❌ skill 运行时整文件加载、造梦师原文、方案 B 镜头 JSON 编译、批量自动出视频

工作目录：后端命令在 `backend/`。

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/services/prompt_compose.py` | 收集 lock、粘贴静图、解析 I2V |
| `backend/tests/test_prompt_compose.py` | compose 行为 |
| `backend/app/db/schema.py` | `006_prompt_locks` |
| `backend/app/db/repositories/assets.py` | `lock_en` CRUD |
| `backend/app/db/repositories/frames.py` | `motion_prompt_en` CRUD |
| `backend/app/prompt_packs/ATTRIBUTION.md` | Seedance MIT + 造梦师 NC 说明 |
| `backend/app/prompt_packs/character_lock_v1/system.md` | 角色定妆 pack |
| `backend/app/prompt_packs/scene_lock_v1/system.md` | 场景定场 pack |
| `backend/app/prompt_packs/storyboard_still_v1/system.md` | 分镜静图 pack |
| `backend/app/prompt_packs/i2v_motion_v1/system.md` | MiniMax 运动 pack |
| `backend/app/prompt_packs/script_expand_v1/system.md` | 禁止自由定妆 |
| `backend/app/services/cinematic_polish.py` | stage→pack 路由与校验 |
| `backend/app/api/prompts.py` | 新 stage、响应可选字段 |
| `backend/app/services/asset_script_sync.py` | 正确 stage + 写 lock_en |
| `backend/app/services/asset_store.py` | create 透传 lock_en |
| `backend/app/api/assets.py` | Asset 模型含 lock_en |
| `backend/app/services/storyboard_breakdown.py` | 注入锁、写运动句 |
| `backend/app/api/storyboard.py` | I2V 用 resolve_i2v_prompt |
| `backend/app/services/job_handlers.py` | polish 写回 lock/motion |
| `frontend/src/pages/workbench/AssetGeneration.jsx` | 锁编辑与 stage |
| `frontend/src/pages/workbench/Storyboard.jsx` | 运动提示词框 |
| `backend/tests/test_cinematic_polish.py` | pack 路由 |
| `backend/tests/test_asset_script_sync.py` | lock_en |
| `backend/tests/test_storyboard_breakdown.py` | 锁粘贴 |
| `backend/tests/test_storyboard_generate_video.py` | payload 用运动句 |
| `backend/tests/test_prompts_polish_api.py` | 新 stage |

---

### Task 1: prompt_compose 纯函数

**Files:**
- Create: `backend/app/services/prompt_compose.py`
- Create: `backend/tests/test_prompt_compose.py`

- [ ] **Step 1: Write the failing test**

```python
from app.services.prompt_compose import (
    collect_lock_ens,
    compose_still_prompt,
    resolve_i2v_prompt,
)


def test_compose_prepends_lock_verbatim():
    lock = "A man, 30s, short black hair, grey linen shirt."
    body = "He waits at the rainy cafe window, 50mm, tungsten practical."
    out = compose_still_prompt(body, [lock])
    assert out.startswith(lock)
    assert "rainy cafe window" in out
    assert out.count(lock) == 1


def test_compose_does_not_duplicate_existing_lock():
    lock = "A man, 30s, short black hair, grey linen shirt."
    body = f"{lock}\nHe waits."
    assert compose_still_prompt(body, [lock]) == body


def test_collect_lock_ens_matches_names():
    assets = [
        {"type": "character", "name": "张三", "lock_en": "CHAR LOCK"},
        {"type": "scene", "name": "咖啡馆", "lock_en": "SCENE LOCK"},
        {"type": "character", "name": "李四", "lock_en": ""},
    ]
    locks = collect_lock_ens(assets, character_name="张三", scene_name="咖啡馆")
    assert locks == ["CHAR LOCK", "SCENE LOCK"]


def test_resolve_i2v_prefers_motion():
    frame = {
        "prompt_en": "LOCK TEXT plus a still description with wardrobe",
        "motion_prompt_en": "He turns to the door. Slow push-in. About 5s.",
        "movement": "推进",
        "duration": 5,
        "description_en": "turns",
    }
    assert resolve_i2v_prompt(frame) == frame["motion_prompt_en"]


def test_resolve_i2v_does_not_use_still_prompt_as_fallback():
    frame = {
        "prompt_en": "A man, 30s, short black hair, grey linen shirt. Cafe window still.",
        "motion_prompt_en": "",
        "movement": "固定",
        "duration": 3,
        "description_en": "He lowers the cup.",
        "description": "他放下杯子",
    }
    out = resolve_i2v_prompt(frame)
    assert "short black hair" not in out
    assert "He lowers the cup" in out
    assert "first frame" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompt_compose.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Write implementation**

```python
from __future__ import annotations

from typing import Any, Optional


def collect_lock_ens(
    assets: list[dict[str, Any]],
    *,
    character_name: str = "",
    scene_name: str = "",
) -> list[str]:
    wanted: list[tuple[str, str]] = []
    if (character_name or "").strip():
        wanted.append(("character", character_name.strip()))
    if (scene_name or "").strip():
        wanted.append(("scene", scene_name.strip()))
    locks: list[str] = []
    for kind, name in wanted:
        for asset in assets:
            if asset.get("type") == kind and (asset.get("name") or "").strip() == name:
                lock = (asset.get("lock_en") or "").strip()
                if lock:
                    locks.append(lock)
                break
    return locks


def compose_still_prompt(shot_body: str, locks: list[str]) -> str:
    body = (shot_body or "").strip()
    parts: list[str] = []
    for raw in locks or []:
        lock = (raw or "").strip()
        if not lock:
            continue
        if lock in body or lock in "\n\n".join(parts):
            continue
        parts.append(lock)
    if not parts:
        return body
    if not body:
        return "\n\n".join(parts)
    return "\n\n".join(parts + [body])


def _fallback_motion(frame: dict[str, Any]) -> str:
    action = (
        (frame.get("description_en") or "").strip()
        or (frame.get("description") or "").strip()
        or "The subject makes one small, complete action."
    )
    movement = (frame.get("movement") or "固定").strip() or "固定"
    duration = frame.get("duration")
    try:
        seconds = float(duration) if duration is not None else 5.0
    except (TypeError, ValueError):
        seconds = 5.0
    seconds = max(2.0, min(seconds, 8.0))
    return (
        f"{action} Camera: {movement}. About {seconds:.0f}s. "
        "Keep identity and wardrobe unchanged from the first frame."
    )


def resolve_i2v_prompt(frame: dict[str, Any]) -> str:
    motion = (frame.get("motion_prompt_en") or "").strip()
    if motion:
        return motion
    return _fallback_motion(frame)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prompt_compose.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prompt_compose.py backend/tests/test_prompt_compose.py
git commit -m "feat: add prompt compose for identity lock and i2v motion"
```

---

### Task 2: SQLite 迁移与仓库字段

**Files:**
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/repositories/assets.py`
- Modify: `backend/app/db/repositories/frames.py`
- Modify: `backend/app/services/asset_store.py`
- Test: `backend/tests/test_asset_script_sync.py`（本任务先保证 create/update 不丢字段；完整 sync 在 Task 5）

- [ ] **Step 1: 在 `MIGRATE_SQL` 追加**

```python
    (
        "006_prompt_locks",
        """
ALTER TABLE assets ADD COLUMN lock_en TEXT NOT NULL DEFAULT '';
ALTER TABLE storyboard_frames ADD COLUMN motion_prompt_en TEXT NOT NULL DEFAULT '';
""",
    ),
```

- [ ] **Step 2: `AssetRepository.create` 增加 `lock_en: str = ""`，INSERT 列包含 `lock_en`。`update` 的 `allowed` 加入 `lock_en`。**

- [ ] **Step 3: `FrameRepository._row_to_frame` / `create` 默认 / `update.allowed` / INSERT 列加入 `motion_prompt_en`。**

- [ ] **Step 4: `AssetStore.create` 增加 `lock_en: str = ""` 并传给 repo。**

- [ ] **Step 5: 写回归测试（可放 `backend/tests/test_prompt_lock_schema.py`）**

```python
from app.db.repositories.assets import AssetRepository
from app.db.repositories.frames import FrameRepository


def test_asset_lock_en_roundtrip(tmp_path):
    repo = AssetRepository(tmp_path / "a.db")
    item = repo.create(
        project_id="p",
        name="张三",
        type="character",
        prompt_cn="x",
        prompt_en="y",
        model="sdxl",
        lock_en="LOCK",
        status="pending",
    )
    assert item["lock_en"] == "LOCK"
    updated = repo.update("p", item["id"], lock_en="LOCK2")
    assert updated["lock_en"] == "LOCK2"


def test_frame_motion_prompt_roundtrip(tmp_path):
    repo = FrameRepository(tmp_path / "f.db")
    fr = repo.create(project_id="p", description="d", prompt_en="still", motion_prompt_en="move")
    assert fr["motion_prompt_en"] == "move"
    updated = repo.update("p", fr["id"], motion_prompt_en="move2")
    assert updated["motion_prompt_en"] == "move2"
```

Run: `pytest tests/test_prompt_lock_schema.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/schema.py backend/app/db/repositories/assets.py backend/app/db/repositories/frames.py backend/app/services/asset_store.py backend/tests/test_prompt_lock_schema.py
git commit -m "feat: persist asset lock_en and frame motion_prompt_en"
```

---

### Task 3: 四个 pack + ATTRIBUTION

**Files:**
- Create: `backend/app/prompt_packs/ATTRIBUTION.md`
- Create: `backend/app/prompt_packs/character_lock_v1/system.md`
- Create: `backend/app/prompt_packs/scene_lock_v1/system.md`
- Create: `backend/app/prompt_packs/storyboard_still_v1/system.md`
- Create: `backend/app/prompt_packs/i2v_motion_v1/system.md`
- Modify: `backend/app/prompt_packs/script_expand_v1/system.md`（规则区追加两条）

- [ ] **Step 1: ATTRIBUTION.md**

```markdown
# Attribution

Cinematic still workflow is originally inspired by
「造梦师：AI时代电影视觉指南」/ zy-cinematic-realism
(https://github.com/popopo-99/zy-cinematic-realism), licensed CC BY-NC 4.0.
This repository ships rewritten packs and does not redistribute that skill verbatim.

Character-lock, single-action, single-camera, and anti-filler rules are adapted from
Seedance 2.0 (https://github.com/Emily2040/seedance-2.0), MIT License,
Copyright (c) 2026 Iamemily2050. Runtime packs are rewritten for MiniMax I2V
and do not copy Seedance platform/API instructions.
```

- [ ] **Step 2: character_lock_v1/system.md** — 完整原文：

```markdown
# Character Lock Pack v1

You write a frozen character identity for live-action stills and later shots.

If context.lock_en is non-empty, copy it VERBATIM into lock_en and into prompt_en. Do not paraphrase.

Otherwise write lock_en as 2-4 English sentences: age range, silhouette, hair, wardrobe, one identifying object. No plot. No camera move. No multi-shot.

prompt_en = lock_en verbatim + one reference still: standing or chest-up, neutral practical light, plain or simple location, not a poster climax.

Output JSON only, no markdown fences:
{"lock_en":"...","prompt_en":"...","avoid":"comma-separated failure modes","prompt_cn":"short Chinese"}

No masterpiece, 8K, photorealistic badges. Avoid extra limbs, face drift, wardrobe change, text, watermark.
```

- [ ] **Step 3: scene_lock_v1/system.md**

```markdown
# Scene Lock Pack v1

You write a frozen location identity for establishing stills.

If context.lock_en is non-empty, copy it VERBATIM into lock_en and prompt_en.

Otherwise lock_en is 2-4 English sentences: spatial layout, era/use traces, where the primary light comes from. No named character performance.

prompt_en = lock_en verbatim + a wide establishing still with no hero performance (empty or tiny distant figures).

Output JSON only:
{"lock_en":"...","prompt_en":"...","avoid":"...","prompt_cn":"..."}

No masterpiece/8K. Avoid collapsing architecture, neon spam, empty CGI void.
```

- [ ] **Step 4: storyboard_still_v1/system.md**

```markdown
# Storyboard Still Pack v1

You write one live-action keyframe prompt for SDXL.

Copy every lock_en in context.character_locks and context.scene_lock VERBATIM at the start of prompt_en. Do not paraphrase locks. Then add only this instant: small concrete action, camera height and shot size, motivated light, physical texture.

Do not write a multi-second camera essay. Do not change face, hair, or wardrobe. No masterpiece/8K.

Output JSON only:
{"interpretation_cn":"...","prompt_en":"...","avoid":"10-20 scene-specific failures","prompt_cn":"..."}
```

- [ ] **Step 5: i2v_motion_v1/system.md**

```markdown
# MiniMax I2V Motion Pack v1

The first frame already shows identity. Write motion only for ~5 seconds.

motion_prompt_en must include: one visible action with an endpoint; one camera move (or locked-off); "Keep identity, face, hair, and wardrobe unchanged from the first frame."

Do not restate appearance, clothes, or location architecture. Multi-person: one verb per named person; no simultaneous large actions. No masterpiece/8K/cinematic masterpiece.

Output JSON only:
{"motion_prompt_en":"...","avoid":"identity drift, wardrobe change, extra limbs, morphing face"}
```

- [ ] **Step 6: script_expand_v1 在「规则」列表追加**

```
6. 同一人物全程使用同一个名字，不要改称谓导致对不上资产。
7. 不要写五官、发型、服饰的长描述；外貌由资产生成锁，剧本只写动作与台词。
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/prompt_packs
git commit -m "feat: add stage prompt packs distilled from craft skills"
```

---

### Task 4: Polish 按 stage 选 pack

**Files:**
- Modify: `backend/app/services/cinematic_polish.py`
- Modify: `backend/app/api/prompts.py`
- Modify: `backend/tests/test_cinematic_polish.py`
- Modify: `backend/tests/test_prompts_polish_api.py`

- [ ] **Step 1: 失败测试 — 不同 stage 读到不同 pack 关键字**

在 `test_cinematic_polish.py` 增加：用真实 pack 路径（不传 pack_path）mock LLM 返回合法 JSON。

```python
def test_character_lock_stage_uses_character_pack():
    llm = MagicMock()
    llm.chat.return_value = (
        json.dumps({
            "lock_en": "A woman, 40s, bun, navy coat.",
            "prompt_en": "A woman, 40s, bun, navy coat. Standing portrait, window light.",
            "avoid": "extra limbs, text",
            "prompt_cn": "定妆",
        }),
        "ollama",
    )
    svc = CinematicPolishService(llm=llm)
    out = svc.polish(stage="character_lock", text_cn="女医生", text_en="", context={})
    assert out["lock_en"].startswith("A woman")
    assert out["pack_version"] == "character-lock-v1"
    system = llm.chat.call_args[0][0][0]["content"]
    assert "frozen character identity" in system.lower() or "Character Lock" in system
```

对 `i2v_motion`：返回缺 `prompt_en` 但有 `motion_prompt_en` 必须通过。

- [ ] **Step 2: 实现路由**

`cinematic_polish.py`：

```python
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent.parent / "prompt_packs"
PACK_BY_STAGE = {
    "script_scene": (PACK_DIR / "cinematic_v1" / "system.md", "cinematic-v1"),
    "asset": (PACK_DIR / "cinematic_v1" / "system.md", "cinematic-v1"),
    "storyboard_frame": (PACK_DIR / "storyboard_still_v1" / "system.md", "storyboard-still-v1"),
    "character_lock": (PACK_DIR / "character_lock_v1" / "system.md", "character-lock-v1"),
    "scene_lock": (PACK_DIR / "scene_lock_v1" / "system.md", "scene-lock-v1"),
    "i2v_motion": (PACK_DIR / "i2v_motion_v1" / "system.md", "i2v-motion-v1"),
}

def _resolve_pack(stage: str, context: dict) -> tuple[Path, str]:
    if stage == "asset":
        kind = (context or {}).get("type") or ""
        if kind == "character":
            return PACK_BY_STAGE["character_lock"]
        if kind == "scene":
            return PACK_BY_STAGE["scene_lock"]
    return PACK_BY_STAGE.get(stage, PACK_BY_STAGE["script_scene"])
```

`polish()` 用 `_resolve_pack` 读 system；`pack_version` 用返回的版本名。  
`_validate`：`i2v_motion` 要求 `motion_prompt_en`；其它要求 `prompt_en`+`avoid`。`lock_en`/`motion_prompt_en` `setdefault` 为 `""`。  
若 context 已有 `lock_en`，user 消息追加 `Copy lock_en VERBATIM.`

- [ ] **Step 3: `prompts.py`**

`ALLOWED_STAGES` 加入 `character_lock`、`scene_lock`、`i2v_motion`。  
`PolishResponse` 增加 `lock_en: str = ""`、`motion_prompt_en: str = ""`。

- [ ] **Step 4: `test_prompts_polish_api.py` 增加合法新 stage 200；非法 stage 仍 400。**

- [ ] **Step 5: Run**

`pytest tests/test_cinematic_polish.py tests/test_prompts_polish_api.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/cinematic_polish.py backend/app/api/prompts.py backend/tests/test_cinematic_polish.py backend/tests/test_prompts_polish_api.py
git commit -m "feat: route polish stages to dedicated prompt packs"
```

---

### Task 5: 资产同步写入 lock_en

**Files:**
- Modify: `backend/app/services/asset_script_sync.py`
- Modify: `backend/tests/test_asset_script_sync.py`

- [ ] **Step 1: 失败测试**

```python
def test_sync_enrich_uses_character_lock_and_stores_lock_en(tmp_path):
    store = AssetStore(tmp_path / "t.db")
    class FakePolish:
        def polish(self, **kwargs):
            assert kwargs["stage"] == "character_lock"
            return {
                "lock_en": "LOCK ZS",
                "prompt_en": "LOCK ZS standing portrait",
                "prompt_cn": "张三",
                "avoid": "blurry",
            }
    sync_from_script(
        project={"id": "p", "style": "古风"},
        scenes=[{"name": "开场", "location": "竹林", "characters": ["张三"], "description": "对峙"}],
        store=store,
        types=("character",),
        enrich=True,
        polish_svc=FakePolish(),
    )
    item = store.find_by_name_type("p", "character", "张三")
    assert item["lock_en"] == "LOCK ZS"
    assert "LOCK ZS" in item["prompt_en"]
```

- [ ] **Step 2: `_enrich_one` 的 stage 用 `character_lock` / `scene_lock`（不要 `character`/`scene`）。返回 dict 含 `lock_en`。**  
`fallback_prompts` 增加 `lock_en`。  
`store.create` / `update` 传入 `lock_en`。

`lock_en` 取值：`data.get("lock_en")` 非空用之；否则 `prompt_en` 第一句（按 `. ` 或 `.` 切）。

- [ ] **Step 3: Run** `pytest tests/test_asset_script_sync.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/asset_script_sync.py backend/tests/test_asset_script_sync.py
git commit -m "fix: asset sync writes lock_en via character/scene lock packs"
```

---

### Task 6: 分镜拆解粘贴锁并写运动句

**Files:**
- Modify: `backend/app/services/storyboard_breakdown.py`
- Modify: `backend/tests/test_storyboard_breakdown.py`

- [ ] **Step 1: 失败测试** — 构造 scene 角色「张三」、传入带 `lock_en` 的 asset 列表（给 BreakdownService 增加可选 `assets` 或在 run 里 `AssetRepository().list(project_id)`）。

断言：写回 `prompt_en` 包含 `lock_en` 原文；`motion_prompt_en` 非空且不等于整段 `prompt_en`。

LLM mock 返回的 `prompt_en` **不要**含 lock，用来证明服务端 compose 补上。

- [ ] **Step 2: `_call_llm` payload 增加 location/time/characters 与 `character_locks`/`scene_lock`。**  
要求 JSON 含 `motion_prompt_en`。校验：`prompt_en` 仍须英文；`motion_prompt_en` 英文且 len>=20，否则重试。  
`_apply_plan`：`compose_still_prompt(prompt_en, locks)`；保存 `motion_prompt_en`。中文 description 不得写入 `prompt_en`。

- [ ] **Step 3: Run** `pytest tests/test_storyboard_breakdown.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/storyboard_breakdown.py backend/tests/test_storyboard_breakdown.py
git commit -m "feat: storyboard breakdown injects identity locks and motion prompts"
```

---

### Task 7: generate-video 使用运动提示词

**Files:**
- Modify: `backend/app/api/storyboard.py`
- Modify: `backend/app/api/assets.py`（Asset 模型加 `lock_en`）
- Modify: `backend/app/services/job_handlers.py`（polish 写回）
- Modify: `backend/tests/test_storyboard_generate_video.py`

- [ ] **Step 1: 失败测试** — 帧同时有长 `prompt_en` 和短 `motion_prompt_en`，`generate-video` 的 job payload[`prompt_en`] 必须等于运动句。

- [ ] **Step 2: `generate_frame_video` 改为 `from app.services.prompt_compose import resolve_i2v_prompt`；`prompt = resolve_i2v_prompt(frame)`。**  
出图路径：若能 `collect_lock_ens`，对 `prompt_en` 再 `compose_still_prompt`。  
`StoryboardFrame` / `FrameUpdateRequest` / `_UPDATABLE_FIELDS` 加 `motion_prompt_en`。  
`Asset` 模型加 `lock_en: str = ""`。  
`_apply_polish_result`：target asset 若有 `lock_en` 且现行为空则写入；target frame 若有 `motion_prompt_en` 则写入。

- [ ] **Step 3: Run**

`pytest tests/test_storyboard_generate_video.py tests/test_storyboard_generate.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/storyboard.py backend/app/api/assets.py backend/app/services/job_handlers.py backend/tests/test_storyboard_generate_video.py
git commit -m "feat: MiniMax i2v uses motion_prompt_en instead of still prompt"
```

---

### Task 8: 前端锁与运动框

**Files:**
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`
- Modify: `frontend/src/pages/workbench/Storyboard.jsx`

- [ ] **Step 1: 资产**  
列表/当前项读取 `lock_en`/`lockEn`。编辑框「身份锁（英文，后续镜头原样粘贴）」。  
润色：`stage: type==='character' ? 'character_lock' : type==='scene' ? 'scene_lock' : 'asset'`，context 带 `type` 与已有 `lock_en`。应用时 PUT/生成带上 `lock_en`。

- [ ] **Step 2: 分镜**  
`mapFrame` 增加 `motionPromptEn`。静图框标题改为「静图提示词」。在负面词上方增加「运动提示词（I2V）」TextArea，保存走现有 update（`motion_prompt_en`）。  
润色预览若有 `motion_prompt_en` 一并展示并可应用。

- [ ] **Step 3: 手动点资产页与分镜页确认字段能编辑（无独立前端单测则跳过 pytest）。**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/workbench/AssetGeneration.jsx frontend/src/pages/workbench/Storyboard.jsx
git commit -m "feat: expose identity lock and i2v motion prompts in workbench"
```

---

### Task 9: 全量回归

- [ ] **Step 1: Run**

```
pytest tests/test_prompt_compose.py tests/test_prompt_lock_schema.py tests/test_cinematic_polish.py tests/test_prompts_polish_api.py tests/test_asset_script_sync.py tests/test_storyboard_breakdown.py tests/test_storyboard_generate_video.py tests/test_storyboard_generate.py tests/test_cinematic_polish.py -v
```

Expected: PASS

- [ ] **Step 2: 再跑** `pytest tests -q --ignore=...` 若仓库习惯全量：`pytest tests -q`（跳过需 GPU/网络的）。  
Expected: 无新增失败
