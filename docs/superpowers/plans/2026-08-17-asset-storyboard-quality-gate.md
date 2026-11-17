# 资产生成 + 分镜清晰脸质量闸门 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 角色必须「身份锁 + 定妆图」就绪后才能分镜规划/出图；提示词口径改为短剧清晰脸，让资产页与分镜页质量可用。

**Architecture:** 纯函数判定角色就绪；breakdown 与帧 generate 前置闸门；pack 改写风格；前端展示就绪态与错误跳转。不新增 DB 列。

**Tech Stack:** FastAPI、pytest、React 18、现有 polish / compose / AssetQueue

**Spec:** `docs/superpowers/specs/2026-08-17-asset-storyboard-quality-gate-design.md`

**范围边界:**
- ✅ readiness 函数、API、breakdown/generate 闸门、pack 口径、资产/分镜前端提示
- ❌ 定妆表单编译、IP-Adapter、历史版本清理、整站换皮

工作目录：后端命令在 `backend/`。用户已要求写完文档后直接实施；提交仅在用户明确要求时做。

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/services/asset_readiness.py` | `is_character_ready` / `unready_characters` / `readiness_reasons` |
| `backend/tests/test_asset_readiness.py` | 就绪判定 |
| `backend/app/api/assets.py` | `GET .../readiness` |
| `backend/app/services/storyboard_breakdown.py` | 规划前闸门 |
| `backend/app/api/storyboard.py` | 帧 generate 闸门 |
| `backend/app/services/cinematic_polish.py` | lock 含脸线索校验（可选轻量） |
| `backend/app/prompt_packs/character_lock_v1/system.md` | 清晰脸口径 |
| `backend/app/prompt_packs/storyboard_still_v1/system.md` | 近景默认 |
| `backend/app/prompt_packs/storyboard_breakdown_v1/system.md` | 同上 |
| `backend/tests/test_storyboard_breakdown.py` | 未就绪不调 LLM |
| `backend/tests/test_storyboard_generate.py` | 未就绪 400 |
| `frontend/src/pages/workbench/AssetGeneration.jsx` | 就绪徽标 + 下一步警告 |
| `frontend/src/pages/workbench/Storyboard.jsx` | 规划/出图错误提示 |
| `frontend/src/services/api.js` | `assetsApi.readiness` |

---

### Task 1: asset_readiness 纯函数

**Files:**
- Create: `backend/app/services/asset_readiness.py`
- Create: `backend/tests/test_asset_readiness.py`

- [ ] **Step 1: Write failing tests**

```python
from app.services.asset_readiness import is_character_ready, readiness_reasons, unready_character_names


def test_ready_requires_lock_image_completed():
    assert is_character_ready({
        "type": "character",
        "lock_en": "A woman, late 20s, clear eyes.",
        "status": "completed",
        "image_url": "/media/x.png",
    })
    assert not is_character_ready({
        "type": "character",
        "lock_en": "A woman",
        "status": "failed",
        "image_url": "/media/x.png",
    })
    assert "missing_image" in readiness_reasons({
        "type": "character", "lock_en": "x", "status": "completed", "image_url": None
    })


def test_unready_names_from_scene_cast():
    assets = [
        {"type": "character", "name": "苏遥", "lock_en": "L", "status": "completed", "image_url": "/a.png"},
        {"type": "character", "name": "黑衣人", "lock_en": "", "status": "pending", "image_url": None},
    ]
    assert unready_character_names(assets, ["苏遥", "黑衣人", "路人"]) == ["黑衣人", "路人"]
```

- [ ] **Step 2: Implement module to pass**

- [ ] **Step 3: Run** `pytest tests/test_asset_readiness.py -q`

---

### Task 2: readiness API

**Files:**
- Modify: `backend/app/api/assets.py`
- Modify: `frontend/src/services/api.js`

- [ ] **Step 1: Add** `GET /{project_id}/readiness` returning characters + ready_count
- [ ] **Step 2: Add** `assetsApi.readiness(projectId)`
- [ ] **Step 3: Smoke** via TestClient or manual

---

### Task 3: Breakdown + generate gates

**Files:**
- Modify: `backend/app/services/storyboard_breakdown.py`
- Modify: `backend/app/api/storyboard.py`
- Modify: `backend/tests/test_storyboard_breakdown.py`
- Modify: `backend/tests/test_storyboard_generate.py`

- [ ] **Step 1: Test** breakdown with unready cast does not call `llm.chat`
- [ ] **Step 2: Gate** in `run` before `_call_llm`
- [ ] **Step 3: Gate** frame generate endpoint
- [ ] **Step 4: Run** related pytest

---

### Task 4: Pack + polish face cue

**Files:**
- Modify packs listed above
- Modify: `backend/app/services/cinematic_polish.py` + test

- [ ] **Step 1: Rewrite** character/storyboard packs for clear-face short-drama
- [ ] **Step 2: Optional** validate lock_en has eye/face/jaw/iris/gaze
- [ ] **Step 3: Assert** pack keywords in existing polish test

---

### Task 5: Frontend UX

**Files:**
- Modify: `AssetGeneration.jsx`, `Storyboard.jsx`

- [ ] **Step 1: Badge** 可用/待定妆 on character groups
- [ ] **Step 2: Confirm** on next if unready exist
- [ ] **Step 3: Surface** `characters_not_ready` errors on breakdown/generate

---

### Task 6: Verification

- [ ] **Step 1:** `pytest tests/test_asset_readiness.py tests/test_storyboard_breakdown.py tests/test_storyboard_generate.py tests/test_cinematic_polish.py -q`
- [ ] **Step 2:** Manual checklist in plan footer

---

## Manual test checklist
1. 新角色仅润色未出图 → 分镜规划失败并点名
2. 出图成功后 → 规划可通过
3. 资产列表显示可用/待定妆
4. 定妆润色英文含清晰脸/胸像口径
