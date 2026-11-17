# H3 Prompt Architecture Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-safe Prompt IR foundation, four-way AI casting gate, and validated MiniMax H3 T2VA/I2VA compiler that replaces raw motion prompts at video submission.

**Architecture:** Persist model-independent visual specifications and versioned compiled prompts in SQLite. Assemble deterministic project/frame context, let the configured local-first LLM rewrite it with the vendored official H3 guide, validate/repair the result, and require a fresh compiled artifact before enqueueing MiniMax. Preserve current fields and routes as compatibility surfaces while introducing explicit compile, edit, lock, stale, casting, and selection APIs.

**Tech Stack:** Python 3.12+/FastAPI/Pydantic 2/SQLite/httpx/pytest; React 18/Ant Design/Vite; ComfyUI Flux and MiniMax H3 workflows.

---

## File map

### New backend resources and services

- `backend/app/prompt_packs/h3_prompt_writing_d21241f/SKILL.md` — upstream skill overview.
- `backend/app/prompt_packs/h3_prompt_writing_d21241f/references/base-en.txt` — canonical T2VA/I2VA/FL2VA/L2VA guide.
- `backend/app/prompt_packs/h3_prompt_writing_d21241f/references/ref-en.txt` — reserved Ref2VA guide.
- `backend/app/prompt_packs/h3_prompt_writing_d21241f/SOURCE.md` — URL, commit, provenance, and license caveat.
- `backend/app/services/prompt_ir.py` — typed Visual Bible and compile-source contracts.
- `backend/app/services/visual_bible.py` — defaults, validation, and persistence facade.
- `backend/app/services/h3_guide.py` — immutable guide loader and version metadata.
- `backend/app/services/h3_validator.py` — deterministic H3 structure/timing/dialogue validation.
- `backend/app/services/h3_compiler.py` — context assembly, LLM rewrite, one repair, persistence.
- `backend/app/services/casting.py` — four distinct commercial-short-drama casting concepts.
- `backend/app/db/repositories/visual_specs.py` — project Visual Bible storage.
- `backend/app/db/repositories/compiled_prompts.py` — compiled artifact lifecycle.
- `backend/app/api/prompt_architecture.py` — Visual Bible and H3 compile/edit/read routes.

### Modified backend surfaces

- `backend/tests/conftest.py` — unique test DB and ModelHub before app imports.
- `backend/app/db/schema.py` — migration 009 for specifications, compiled prompts, and casting metadata.
- `backend/app/db/repositories/assets.py` — casting columns and selection queries.
- `backend/app/services/asset_readiness.py` — selected-candidate gate plus legacy compatibility.
- `backend/app/api/assets.py` — cast and select endpoints.
- `backend/app/api/storyboard.py` — compile-aware I2VA generation and 5-second default.
- `backend/app/api/videos.py` — T2VA compile-aware submission.
- `backend/app/main.py` — register prompt architecture router.
- `backend/app/services/runtime.py` — shared new repositories only if needed by existing dependency style.

### Frontend

- `frontend/src/services/api.js` — Visual Bible, casting, compile, edit, latest API clients.
- `frontend/src/pages/workbench/AssetGeneration.jsx` — generate four candidates and select actor.
- `frontend/src/pages/workbench/Storyboard.jsx` — H3 preview/editor/lock/stale panel and compiled submission.

### Tests

- `backend/tests/test_test_isolation.py`
- `backend/tests/test_visual_bible.py`
- `backend/tests/test_compiled_prompts.py`
- `backend/tests/test_h3_guide.py`
- `backend/tests/test_h3_validator.py`
- `backend/tests/test_h3_compiler.py`
- `backend/tests/test_prompt_architecture_api.py`
- `backend/tests/test_casting.py`
- modify `backend/tests/test_storyboard_generate_video.py`
- modify `backend/tests/test_videos_generate_api.py`

## Task 1: Isolate tests from production data

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_test_isolation.py`

- [ ] **Step 1: Add a failing isolation assertion**

```python
from pathlib import Path

from app.core.settings import settings


def test_test_runtime_never_uses_production_database():
    production = Path(__file__).resolve().parents[1] / "data" / "shipin-agent.db"
    assert settings.resolved_sqlite_path.resolve() != production.resolve()
    assert "pytest" in settings.resolved_sqlite_path.name
```

- [ ] **Step 2: Verify the assertion fails against the current conftest**

Run: `python -m pytest backend/tests/test_test_isolation.py -q --basetemp=backend/.pytest-tmp`
Expected: FAIL because `settings.resolved_sqlite_path` is `backend/data/shipin-agent.db`.

- [ ] **Step 3: Set unique test paths before importing application modules**

At module import time in `backend/tests/conftest.py`, create a UUID-based path under `backend/data/` and set both environment values before any `app.*` import:

```python
import atexit
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_RUN_ID = f"pytest-{os.getpid()}-{uuid4().hex}"
_TEST_ROOT = ROOT / "data" / _RUN_ID
_TEST_DB = ROOT / "data" / f"{_RUN_ID}.db"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
(_TEST_ROOT / "outputs" / "assets").mkdir(parents=True, exist_ok=True)
os.environ["MODELHUB_ROOT"] = str(_TEST_ROOT)
os.environ["SQLITE_PATH"] = str(_TEST_DB)


def _cleanup_test_runtime() -> None:
    _TEST_DB.unlink(missing_ok=True)


atexit.register(_cleanup_test_runtime)
```

Do not recursively delete the ModelHub directory during interpreter shutdown; individual pytest fixtures own their temporary outputs.

- [ ] **Step 4: Run the new test and complete backend suite**

Run: `python -m pytest backend/tests/test_test_isolation.py -q --basetemp=backend/.pytest-tmp`
Expected: `1 passed`.

Run: `python -m pytest backend/tests -q --basetemp=backend/.pytest-tmp`
Expected: `191 passed` or more.

- [ ] **Step 5: Commit isolation**

```powershell
git add backend/tests/conftest.py backend/tests/test_test_isolation.py
git commit -m "test: isolate runtime database"
```

## Task 2: Vendor and validate the official H3 guide

**Files:**
- Create: `backend/app/prompt_packs/h3_prompt_writing_d21241f/SKILL.md`
- Create: `backend/app/prompt_packs/h3_prompt_writing_d21241f/references/base-en.txt`
- Create: `backend/app/prompt_packs/h3_prompt_writing_d21241f/references/ref-en.txt`
- Create: `backend/app/prompt_packs/h3_prompt_writing_d21241f/SOURCE.md`
- Create: `backend/app/services/h3_guide.py`
- Create: `backend/tests/test_h3_guide.py`

- [ ] **Step 1: Write guide provenance tests**

```python
from app.services.h3_guide import GUIDE_COMMIT, load_base_guide, load_ref_guide


def test_official_h3_guides_are_loaded_from_vendored_resources():
    assert GUIDE_COMMIT == "d21241f0a4b3acbb34c97dae47fa417b7065e438"
    assert "integrated_multimodal_description" in load_base_guide()
    assert "subject_definitions" in load_ref_guide()


def test_base_guide_contains_exact_i2va_alignment_instruction():
    assert (
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced."
    ) in load_base_guide()
```

- [ ] **Step 2: Confirm the loader test fails**

Run: `python -m pytest backend/tests/test_h3_guide.py -q --basetemp=backend/.pytest-tmp`
Expected: FAIL with missing `app.services.h3_guide`.

- [ ] **Step 3: Copy the sparse-checked upstream files byte-for-byte and add provenance**

`SOURCE.md` must state the repository URL, exact commit, retrieval date, copied paths, no bundled top-level license found at that commit, and that the files are kept unchanged for provenance.

- [ ] **Step 4: Implement a focused loader**

```python
from functools import lru_cache
from pathlib import Path

GUIDE_COMMIT = "d21241f0a4b3acbb34c97dae47fa417b7065e438"
GUIDE_VERSION = f"minimax-h3@{GUIDE_COMMIT[:7]}"
_ROOT = Path(__file__).resolve().parents[1] / "prompt_packs" / "h3_prompt_writing_d21241f"


@lru_cache(maxsize=1)
def load_base_guide() -> str:
    text = (_ROOT / "references" / "base-en.txt").read_text(encoding="utf-8").strip()
    if "integrated_multimodal_description" not in text:
        raise RuntimeError("invalid MiniMax H3 base guide")
    return text


@lru_cache(maxsize=1)
def load_ref_guide() -> str:
    text = (_ROOT / "references" / "ref-en.txt").read_text(encoding="utf-8").strip()
    if "subject_definitions" not in text:
        raise RuntimeError("invalid MiniMax H3 reference guide")
    return text
```

- [ ] **Step 5: Run and commit**

Run: `python -m pytest backend/tests/test_h3_guide.py -q --basetemp=backend/.pytest-tmp`
Expected: `2 passed`.

```powershell
git add backend/app/prompt_packs/h3_prompt_writing_d21241f backend/app/services/h3_guide.py backend/tests/test_h3_guide.py
git commit -m "feat: vendor official H3 prompt guide"
```

## Task 3: Add Visual Bible and compiled artifact persistence

**Files:**
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/repositories/assets.py`
- Create: `backend/app/db/repositories/visual_specs.py`
- Create: `backend/app/db/repositories/compiled_prompts.py`
- Create: `backend/app/services/prompt_ir.py`
- Create: `backend/app/services/visual_bible.py`
- Create: `backend/tests/test_visual_bible.py`
- Create: `backend/tests/test_compiled_prompts.py`

- [ ] **Step 1: Write persistence and default-aesthetic tests**

```python
from app.db.repositories.compiled_prompts import CompiledPromptRepository
from app.db.repositories.visual_specs import VisualSpecRepository
from app.services.visual_bible import default_visual_bible


def test_default_visual_bible_is_polished_without_permanent_distress():
    bible = default_visual_bible()
    text = bible.model_dump_json().lower()
    assert "commercial short-drama" in text
    for forbidden in ("grit", "cold sweat", "exhausted", "mud-stained"):
        assert forbidden not in text


def test_visual_spec_roundtrip(tmp_path):
    db = tmp_path / "spec.db"
    repo = VisualSpecRepository(db)
    saved = repo.upsert("p1", default_visual_bible().model_dump())
    assert repo.get("p1")["spec_json"]["version"] == saved["spec_json"]["version"]


def test_compiled_prompt_roundtrip_and_latest(tmp_path):
    db = tmp_path / "compiled.db"
    repo = CompiledPromptRepository(db)
    row = repo.create(
        project_id="p1", source_type="frame", source_id="f1", target_model="minimax-h3",
        mode="i2va", source_hash="abc", guide_version="g1", content="body",
        validation={"valid": True, "issues": []}, provider="ollama",
    )
    assert repo.latest("p1", "frame", "f1", "i2va")["id"] == row["id"]
```

- [ ] **Step 2: Run tests and confirm missing types/repositories**

Run: `python -m pytest backend/tests/test_visual_bible.py backend/tests/test_compiled_prompts.py -q --basetemp=backend/.pytest-tmp`
Expected: collection FAIL for missing modules.

- [ ] **Step 3: Add migration 009**

Create `project_visual_specs` and `compiled_prompts`; add nullable `candidate_group_id`, integer `candidate_index`, and non-null `selection_status DEFAULT 'legacy'` to assets. Add indexes on compiled source lookup and asset candidate groups. Store JSON as text and decode in repositories.

- [ ] **Step 4: Implement typed contracts and repositories**

`ProjectVisualBible` contains the approved policies. `H3SourceContext` contains mode, duration, project, subjects, scene, shot, dialogue, soundscape, music, and source hash inputs. Repositories must own serialization and return dictionaries consistent with existing repositories.

- [ ] **Step 5: Run schema and new tests**

Run: `python -m pytest backend/tests/test_db_schema.py backend/tests/test_visual_bible.py backend/tests/test_compiled_prompts.py -q --basetemp=backend/.pytest-tmp`
Expected: all pass.

- [ ] **Step 6: Commit persistence foundation**

```powershell
git add backend/app/db backend/app/services/prompt_ir.py backend/app/services/visual_bible.py backend/tests/test_visual_bible.py backend/tests/test_compiled_prompts.py
git commit -m "feat: persist prompt specifications and artifacts"
```

## Task 4: Implement deterministic H3 validation

**Files:**
- Create: `backend/app/services/h3_validator.py`
- Create: `backend/tests/test_h3_validator.py`

- [ ] **Step 1: Write validator behavior tests**

Cover one valid T2VA prompt, one valid I2VA prompt, missing field order, wrong alignment, a cut after duration, non-consecutive shots, unresolved `<Picture 2>`, and altered dialogue. The public interface is:

```python
report = validate_h3_prompt(
    content,
    mode="i2va",
    duration_sec=5.17,
    expected_dialogue=["别回头。"],
)
assert report.valid is True
assert report.issues == []
```

Each issue uses `code`, `message`, and `severity="error"`.

- [ ] **Step 2: Verify failure before implementation**

Run: `python -m pytest backend/tests/test_h3_validator.py -q --basetemp=backend/.pytest-tmp`
Expected: FAIL with missing validator.

- [ ] **Step 3: Implement field, shot, timing, label, and dialogue validation**

Use exact field-line regexes and parse `At MM:SS.mmm`. T2VA must not start with the I2VA instruction; I2VA must. Permit `<Picture 1>` only in phase one. Reject duration outside 4–15 seconds before examining content.

- [ ] **Step 4: Run and commit**

Run: `python -m pytest backend/tests/test_h3_validator.py -q --basetemp=backend/.pytest-tmp`
Expected: all cases pass.

```powershell
git add backend/app/services/h3_validator.py backend/tests/test_h3_validator.py
git commit -m "feat: validate H3 prompt structure"
```

## Task 5: Build and expose the H3 compiler

**Files:**
- Create: `backend/app/services/h3_compiler.py`
- Create: `backend/app/api/prompt_architecture.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_h3_compiler.py`
- Create: `backend/tests/test_prompt_architecture_api.py`

- [ ] **Step 1: Write compiler tests with a fake LLM**

Test valid first output, invalid-then-repaired output, invalid twice, exact dialogue preservation, deterministic hash, latest stale calculation, manual edit, and lock. Construct with dependency injection:

```python
compiler = H3PromptCompiler(
    llm=fake_llm,
    compiled_repo=CompiledPromptRepository(db),
    visual_repo=VisualSpecRepository(db),
    project_repo=ProjectRepository(db),
    scene_repo=SceneRepository(db),
    asset_repo=AssetRepository(db),
    frame_repo=FrameRepository(db),
)
result = compiler.compile_frame("p1", "f1", mode="i2va", duration_sec=5.17)
assert result["validation"]["valid"] is True
```

- [ ] **Step 2: Verify tests fail for missing compiler**

Run: `python -m pytest backend/tests/test_h3_compiler.py -q --basetemp=backend/.pytest-tmp`
Expected: collection FAIL.

- [ ] **Step 3: Implement source assembly and LLM rewrite**

The system message embeds the complete base guide and a short non-negotiable instruction. The user message is deterministic JSON from `H3SourceContext`. Strip Markdown fences from the LLM response. Validate once, then send a repair message containing the original output and exact issues. Persist only the final response, including invalid final responses for diagnosis.

- [ ] **Step 4: Add APIs**

Define typed request/response models and routes for Visual Bible get/update, H3 compile, latest, edit, and lock. Editing revalidates content. Latest compares current source hash and returns `stale` without mutating locked content.

- [ ] **Step 5: Register router and run tests**

Run: `python -m pytest backend/tests/test_h3_compiler.py backend/tests/test_prompt_architecture_api.py -q --basetemp=backend/.pytest-tmp`
Expected: all pass.

- [ ] **Step 6: Commit compiler vertical**

```powershell
git add backend/app/services/h3_compiler.py backend/app/api/prompt_architecture.py backend/app/main.py backend/tests/test_h3_compiler.py backend/tests/test_prompt_architecture_api.py
git commit -m "feat: compile versioned H3 prompts"
```

## Task 6: Require compiled prompts for MiniMax generation

**Files:**
- Modify: `backend/app/api/storyboard.py`
- Modify: `backend/app/api/videos.py`
- Modify: `backend/tests/test_storyboard_generate_video.py`
- Modify: `backend/tests/test_videos_generate_api.py`

- [ ] **Step 1: Change tests to require compiled content**

For I2VA, mock the compiler to return a fresh valid artifact and assert the job payload equals its `content`, includes `compiled_prompt_id`, uses default length 124, and excludes the old `motion_prompt_en`. Add stale and invalid cases that return 409/422 without enqueueing.

For T2VA, assert the raw request is treated as a brief, compiler mode is `t2va`, and the job uses compiled content.

- [ ] **Step 2: Verify the changed tests fail**

Run: `python -m pytest backend/tests/test_storyboard_generate_video.py backend/tests/test_videos_generate_api.py -q --basetemp=backend/.pytest-tmp`
Expected: failures showing raw motion/brief is still enqueued.

- [ ] **Step 3: Integrate compile-aware submission**

Add optional `compiled_prompt_id` and `auto_compile` request fields. Resolve a supplied artifact, reject stale/invalid content, or compile automatically. Do not require Comfy readiness for compile-only APIs; preserve readiness checks immediately before job creation. Persist artifact ID and guide version in the job payload.

- [ ] **Step 4: Run focused and regression tests**

Run: `python -m pytest backend/tests/test_storyboard_generate_video.py backend/tests/test_videos_generate_api.py backend/tests/test_minimax_workflow.py -q --basetemp=backend/.pytest-tmp`
Expected: all pass.

- [ ] **Step 5: Commit generation integration**

```powershell
git add backend/app/api/storyboard.py backend/app/api/videos.py backend/tests/test_storyboard_generate_video.py backend/tests/test_videos_generate_api.py
git commit -m "feat: generate MiniMax video from compiled H3 prompts"
```

## Task 7: Add four-way AI casting and selection gate

**Files:**
- Create: `backend/app/services/casting.py`
- Modify: `backend/app/api/assets.py`
- Modify: `backend/app/services/asset_readiness.py`
- Modify: `backend/app/db/repositories/assets.py`
- Create: `backend/tests/test_casting.py`
- Modify: `backend/tests/test_asset_readiness.py`

- [ ] **Step 1: Write casting concept and readiness tests**

Assert exactly four concepts, distinct `identity_anchor` values, commercial-short-drama aesthetic, absence of state words (`rain`, `wet`, `blood`, `mud`, `exhausted`, `sweat`), and neutral comparison framing. Assert candidate assets are unready until one completed image is selected; preserve legacy completed+lock behavior.

- [ ] **Step 2: Verify the tests fail**

Run: `python -m pytest backend/tests/test_casting.py backend/tests/test_asset_readiness.py -q --basetemp=backend/.pytest-tmp`
Expected: failures for missing casting service and selection semantics.

- [ ] **Step 3: Implement LLM generation with deterministic validation/fallback**

Require JSON `{ "candidates": [...] }` with four candidates. Validate stable identity only and reject state leakage. If the LLM response is unusable, use four clearly distinct, polished fallback archetypes rather than the old tired/gritty portrait template.

- [ ] **Step 4: Implement cast/select APIs**

`cast` creates or updates four same-name candidate assets with one group ID, indices 1–4, `selection_status="candidate"`, portrait aspect, and Flux model, then enqueues all four after normal readiness checks. `select` requires a completed image, marks one selected, marks siblings rejected, and leaves legacy assets untouched.

- [ ] **Step 5: Run and commit**

Run: `python -m pytest backend/tests/test_casting.py backend/tests/test_asset_readiness.py backend/tests/test_assets_generate_health.py -q --basetemp=backend/.pytest-tmp`
Expected: all pass.

```powershell
git add backend/app/services/casting.py backend/app/api/assets.py backend/app/services/asset_readiness.py backend/app/db/repositories/assets.py backend/tests/test_casting.py backend/tests/test_asset_readiness.py
git commit -m "feat: add AI casting selection gate"
```

## Task 8: Add casting and H3 control panels to the frontend

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`
- Modify: `frontend/src/pages/workbench/Storyboard.jsx`

- [ ] **Step 1: Add API clients**

Add `assetsApi.castCharacter`, `assetsApi.selectCharacter`, `promptArchitectureApi.compileH3`, `latestH3`, `updateH3`, `lockH3`, `getVisualBible`, and `updateVisualBible` using existing `request()`.

- [ ] **Step 2: Add casting controls**

For character groups, show “AI 选角 4 版”; show candidate numbers and selection status on takes; enable “选定此演员” only for completed images. Refresh the character list after actions and use backend error messages verbatim.

- [ ] **Step 3: Add the H3 compile panel**

Track the latest artifact per selected frame. Display mode, duration, guide version, provider, validation issues, locked/edited/stale tags, and editable compiled text. “编译 H3” calls I2VA with duration derived from 124/24. Saving edits calls update; locking calls lock. A stale/invalid artifact disables video generation.

- [ ] **Step 4: Remove the 39-frame contradiction**

Submit `length: 124`, `width: 960`, and `height: 544`, plus the selected compiled prompt ID. If no fresh artifact exists, compile and show it, then ask the user to click generation again; do not submit raw `motionPromptEn`.

- [ ] **Step 5: Build frontend**

Run: `npm run build` in `frontend/`
Expected: Vite production build succeeds; the existing bundle-size warning may remain.

- [ ] **Step 6: Commit frontend controls**

```powershell
git add frontend/src/services/api.js frontend/src/pages/workbench/AssetGeneration.jsx frontend/src/pages/workbench/Storyboard.jsx
git commit -m "feat: add casting and H3 prompt controls"
```

## Task 9: Full verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `backend/app/prompt_packs/ATTRIBUTION.md`

- [ ] **Step 1: Document behavior and provenance**

Explain Prompt IR authority, AI casting gate, H3 compile lifecycle, stale handling, default 5-second I2VA, test database isolation, upstream URL/commit, and the fact that phase two is required for reference-conditioned Flux storyboard identity.

- [ ] **Step 2: Run backend verification**

Run: `python -m pytest backend/tests -q --basetemp=backend/.pytest-tmp`
Expected: all tests pass with no writes to production DB.

- [ ] **Step 3: Run frontend verification**

Run: `npm run build` in `frontend/`
Expected: build succeeds.

- [ ] **Step 4: Inspect diff and source provenance**

Run: `git diff HEAD~8 --check`
Expected: no whitespace errors.

Run: `git status --short`
Expected: only ignored local test/build/upstream scratch paths; no uncommitted implementation files.

- [ ] **Step 5: Commit docs**

```powershell
git add README.md backend/app/prompt_packs/ATTRIBUTION.md
git commit -m "docs: explain H3 prompt architecture"
```
