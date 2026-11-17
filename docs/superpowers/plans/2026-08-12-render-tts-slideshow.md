# Render Slideshow + Dual TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让剧本扩写出结构化台词、分镜 LLM 把台词分到帧，并用 Edge/VoxCPM + ffmpeg 把已出图分镜拼成可下载成片（本轮不做真视频/BGM）。

**Architecture:** SQLite 扩展 `lines_json` / `scene_id` / `renders`；扩写与 `storyboard_breakdown` / `render_compose` 走现有 JobQueue；`TTSProvider` 抽象 Edge 与 VoxCPM；ffmpeg 静图+音轨（可选硬字幕）。

**Tech Stack:** FastAPI, SQLite, JobQueue, edge-tts, VoxCPM（本机权重）, ffmpeg, React/Ant Design

**Spec:** [docs/superpowers/specs/2026-08-12-render-tts-slideshow-design.md](../specs/2026-08-12-render-tts-slideshow-design.md)

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/db/schema.py` | migration `004_render_tts` |
| `backend/app/services/script_lines.py` | normalize / count lines |
| `backend/app/prompt_packs/script_expand_v1/system.md` | require `lines[]` |
| `backend/app/services/script_expand.py` | persist normalized lines |
| `backend/app/db/repositories/scenes.py` | lines_json CRUD |
| `backend/app/db/repositories/frames.py` | lines_json + scene_id |
| `backend/app/db/repositories/renders.py` | renders table CRUD |
| `backend/app/services/storyboard_breakdown.py` | LLM plan frames + assign lines |
| `backend/app/services/tts/base.py` | TTSProvider protocol + factory |
| `backend/app/services/tts/edge_provider.py` | Edge TTS |
| `backend/app/services/tts/voxcpm_provider.py` | VoxCPM |
| `backend/app/services/tts_settings_store.py` | default engine JSON |
| `backend/app/services/render_compose.py` | TTS per frame + ffmpeg |
| `backend/app/api/tts.py` | preview + settings |
| `backend/app/api/render.py` | episodes / thin job create / list renders |
| `backend/app/api/jobs.py` + `job_handlers.py` | new job types |
| `backend/app/main.py` | mount tts router |
| `frontend/src/services/api.js` | render/tts/jobs helpers |
| `frontend/src/pages/workbench/ScriptWorkshop.jsx` | show/edit lines |
| `frontend/src/pages/workbench/Storyboard.jsx` | breakdown button, drop fake seed as sole source |
| `frontend/src/pages/workbench/FinalRender.jsx` | real compose UX |
| `frontend/src/pages/admin/ModelConfig.jsx` | TTS test real |
| `README.md` | status |
| `backend/.env.example` | FFMPEG_PATH / VOXCPM path |

---

### Task 1: Schema migration `004_render_tts`

**Files:**
- Modify: `backend/app/db/schema.py`
- Modify: `backend/tests/test_db_schema.py`
- Test: `backend/tests/test_db_schema.py`

- [ ] **Step 1: Write failing assertion for new columns/table**

In `backend/tests/test_db_schema.py`, replace the migration-count assertion and add column checks:

```python
from pathlib import Path

from app.db.connection import connect
from app.db.schema import migrate


def test_migrate_creates_tables(tmp_path: Path):
    db = tmp_path / "t.db"
    conn = connect(db)
    migrate(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "projects" in tables
    assert "scenes" in tables
    assert "assets" in tables
    assert "storyboard_frames" in tables
    assert "renders" in tables
    assert "schema_migrations" in tables
    migrate(conn)  # idempotent
    ids = {
        row[0]
        for row in conn.execute("SELECT id FROM schema_migrations").fetchall()
    }
    assert "001_init" in ids
    assert "004_render_tts" in ids
    cols_scenes = {
        r[1] for r in conn.execute("PRAGMA table_info(scenes)").fetchall()
    }
    assert "lines_json" in cols_scenes
    cols_frames = {
        r[1] for r in conn.execute("PRAGMA table_info(storyboard_frames)").fetchall()
    }
    assert "lines_json" in cols_frames
    assert "scene_id" in cols_frames
    conn.close()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_db_schema.py::test_migrate_creates_tables -v`

Expected: FAIL (`renders` missing and/or `004_render_tts` missing)

- [ ] **Step 3: Add migration**

Append to `MIGRATE_SQL` in `backend/app/db/schema.py`:

```python
    (
        "004_render_tts",
        """
ALTER TABLE scenes ADD COLUMN lines_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE storyboard_frames ADD COLUMN lines_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE storyboard_frames ADD COLUMN scene_id TEXT;
CREATE TABLE IF NOT EXISTS renders (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  scene_id TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  engine TEXT NOT NULL DEFAULT 'edge',
  output_url TEXT,
  duration_sec REAL,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_renders_project ON renders(project_id);
""",
    ),
```

Note: SQLite allows multiple statements in `executescript`. If a column already exists on a weird DB, migration fails once — acceptable for this project; do not add complex IF NOT EXISTS column helpers unless tests need them.

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_db_schema.py::test_migrate_creates_tables -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/schema.py backend/tests/test_db_schema.py
git commit -m "feat(db): add lines_json, scene_id, renders migration"
```

---

### Task 2: `script_lines` normalize helper

**Files:**
- Create: `backend/app/services/script_lines.py`
- Test: `backend/tests/test_script_lines.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_script_lines.py
from app.services.script_lines import normalize_lines, counts_from_lines


def test_normalize_fills_id_and_counts():
    lines = normalize_lines(
        [
            {"type": "dialogue", "speaker": "甲", "text": "你好", "emotion": "平静"},
            {"type": "narration", "text": "夜深了"},
            {"type": "dialogue", "speaker": "", "text": ""},  # drop empty
        ]
    )
    assert len(lines) == 2
    assert lines[0]["id"].startswith("line_")
    assert lines[0]["speaker"] == "甲"
    assert lines[1]["type"] == "narration"
    d, n = counts_from_lines(lines)
    assert d == 1 and n == 1


def test_normalize_keeps_stable_id():
    lines = normalize_lines(
        [{"id": "line_keep", "type": "dialogue", "speaker": "A", "text": "x"}]
    )
    assert lines[0]["id"] == "line_keep"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd backend && python -m pytest tests/test_script_lines.py -v`

Expected: FAIL import error

- [ ] **Step 3: Implement**

```python
# backend/app/services/script_lines.py
from __future__ import annotations

import uuid
from typing import Any


def normalize_lines(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        typ = str(item.get("type") or "dialogue").strip().lower()
        if typ not in ("dialogue", "narration"):
            typ = "dialogue"
        lid = str(item.get("id") or "").strip() or f"line_{uuid.uuid4().hex[:8]}"
        speaker = str(item.get("speaker") or "").strip()
        if typ == "narration" and not speaker:
            speaker = "旁白"
        out.append(
            {
                "id": lid,
                "type": typ,
                "speaker": speaker,
                "text": text,
                "emotion": str(item.get("emotion") or "").strip(),
            }
        )
    return out


def counts_from_lines(lines: list[dict[str, Any]]) -> tuple[int, int]:
    d = sum(1 for x in lines if x.get("type") == "dialogue")
    n = sum(1 for x in lines if x.get("type") == "narration")
    return d, n
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd backend && python -m pytest tests/test_script_lines.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/script_lines.py backend/tests/test_script_lines.py
git commit -m "feat(script): add lines normalize helper"
```

---

### Task 3: Expand pack + ScriptExpandService lines

**Files:**
- Modify: `backend/app/prompt_packs/script_expand_v1/system.md`
- Modify: `backend/app/services/script_expand.py`
- Modify: `backend/tests/test_script_expand.py`

- [ ] **Step 1: Update failing expand test to require lines**

```python
def test_expand_parses_scenes_with_lines():
    llm = MagicMock()
    llm.chat.return_value = (
        '{"scenes":[{"name":"A","location":"街","time":"夜","characters":["X"],"props":[],'
        '"description":"d","lines":[{"type":"dialogue","speaker":"X","text":"走","emotion":"急"}]}]}',
        "ollama",
    )
    svc = ScriptExpandService(llm=llm)
    scenes = svc.expand(text="创意", style="都市")
    assert len(scenes) == 1
    assert scenes[0]["dialogue_count"] == 1
    assert scenes[0]["lines"][0]["text"] == "走"
    assert scenes[0]["lines"][0]["id"]
```

Keep existing tests valid: when LLM omits `lines`, normalized result is `lines=[]` and counts from lines (0) **or** fall back to provided counts only if lines empty — **spec: counts derived from lines**. Update old fixtures:

```python
# For tests without lines, expect dialogue_count == 0 after normalize
```

- [ ] **Step 2: Run — expect FAIL** on missing `lines` key

- [ ] **Step 3: Update pack + normalize**

`system.md` — replace fields list so each scene includes:

```markdown
   - lines: 数组；每项 {type: dialogue|narration, speaker, text, emotion}
     dialogue 必须有 speaker 与 text；narration 的 speaker 可空
     emotion 短中文可空字符串
   - dialogue_count / narration_count: 可省略，服务端会按 lines 重算
```

Example JSON must include at least one line object.

In `script_expand.py` `_normalize_scenes`:

```python
from app.services.script_lines import normalize_lines, counts_from_lines

# inside loop:
lines = normalize_lines(s.get("lines"))
d_count, n_count = counts_from_lines(lines)
out.append({
    ...
    "lines": lines,
    "dialogue_count": d_count,
    "narration_count": n_count,
})
```

- [ ] **Step 4: Run**

Run: `cd backend && python -m pytest tests/test_script_expand.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/prompt_packs/script_expand_v1/system.md backend/app/services/script_expand.py backend/tests/test_script_expand.py
git commit -m "feat(script): expand outputs structured dialogue lines"
```

---

### Task 4: SceneRepository + scripts API persist lines

**Files:**
- Modify: `backend/app/db/repositories/scenes.py`
- Modify: `backend/app/api/scripts.py` (Scene model + update fields)
- Test: `backend/tests/test_scenes_repo.py` (extend)

- [ ] **Step 1: Failing repo test**

```python
def test_replace_all_persists_lines(tmp_path: Path):
    repo = SceneRepository(db_path=tmp_path / "s.db")
    out = repo.replace_all(
        "p1",
        [
            {
                "name": "S",
                "lines": [
                    {
                        "id": "line_1",
                        "type": "dialogue",
                        "speaker": "A",
                        "text": "hi",
                        "emotion": "",
                    }
                ],
            }
        ],
    )
    assert out[0]["lines"][0]["text"] == "hi"
    got = repo.get("p1", out[0]["id"])
    assert got["lines"][0]["id"] == "line_1"
    assert got["dialogue_count"] == 1
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Wire `lines_json` in `_row_to_scene`, `replace_all` INSERT, `update`**

- On read: `lines = json.loads(row.get("lines_json") or "[]")` then normalize.  
- On write: if `lines` in scene dict, normalize + set counts + `lines_json`.  
- `update`: if `lines` in fields → write `lines_json` and refresh counts.

Also extend Pydantic `Scene` / update body in `scripts.py` with `lines: list[dict] = []`.

- [ ] **Step 4: Run**

`cd backend && python -m pytest tests/test_scenes_repo.py tests/test_scripts_expand_api.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories/scenes.py backend/app/api/scripts.py backend/tests/test_scenes_repo.py
git commit -m "feat(db): persist scene dialogue lines"
```

---

### Task 5: ScriptWorkshop show lines

**Files:**
- Modify: `frontend/src/pages/workbench/ScriptWorkshop.jsx`
- Modify: `frontend/src/services/api.js` if scene update helper missing

- [ ] **Step 1: Map API → UI**

In scene mapper include:

```javascript
lines: Array.isArray(s.lines) ? s.lines : [],
```

Under the existing `💬 N条对话` row, render a compact list (max 4 + “还有 n 条”):

```jsx
{(scene.lines || []).slice(0, 4).map((line) => (
  <div key={line.id} style={{ fontSize: 12, color: 'var(--vf-text-secondary)' }}>
    {line.type === 'narration' ? '旁白' : (line.speaker || '角色')}：{line.text}
    {line.emotion ? `（${line.emotion}）` : ''}
  </div>
))}
```

If `lines.length === 0`, show tip:「重新扩写/解析以生成台词」.

- [ ] **Step 2: Manual check** — expand a project; lines appear after job completes (no automated frontend test required).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workbench/ScriptWorkshop.jsx
git commit -m "feat(ui): show scene dialogue lines in script workshop"
```

---

### Task 6: Frame repo lines + scene_id

**Files:**
- Modify: `backend/app/db/repositories/frames.py`
- Modify: `backend/app/api/storyboard.py` (response model fields)
- Test: `backend/tests/test_frames_lines.py` (create)

- [ ] **Step 1: Failing test**

```python
from pathlib import Path
from app.db.repositories.frames import FrameRepository


def test_frame_lines_and_scene_id(tmp_path: Path):
    repo = FrameRepository(db_path=tmp_path / "f.db")
    f = repo.create(
        "p1",
        scene_id="scene_x",
        description="shot",
        lines=[
            {
                "id": "line_1",
                "type": "dialogue",
                "speaker": "A",
                "text": "hi",
                "emotion": "",
            }
        ],
    )
    assert f["scene_id"] == "scene_x"
    assert f["lines"][0]["text"] == "hi"
    got = repo.get("p1", f["id"])
    assert got["lines"][0]["id"] == "line_1"
```

- [ ] **Step 2: Implement create/list/get/update for `lines_json` + `scene_id`**

Serialize/deserialize with `script_lines.normalize_lines`. Update INSERT column lists accordingly.

- [ ] **Step 3: Extend `StoryboardFrame` pydantic model** with `lines: list = []`, `scene_id: Optional[str] = None`

- [ ] **Step 4: pytest PASS + commit**

```bash
git add backend/app/db/repositories/frames.py backend/app/api/storyboard.py backend/tests/test_frames_lines.py
git commit -m "feat(db): store frame lines and scene_id"
```

---

### Task 7: `storyboard_breakdown` service + Job

**Files:**
- Create: `backend/app/services/storyboard_breakdown.py`
- Create: `backend/app/prompt_packs/storyboard_breakdown_v1/system.md`
- Modify: `backend/app/api/jobs.py` (TITLE/LINK/LLM types)
- Modify: `backend/app/services/job_handlers.py`
- Test: `backend/tests/test_storyboard_breakdown.py`

- [ ] **Step 1: Failing unit test with mock LLM**

```python
from unittest.mock import MagicMock
from pathlib import Path

from app.db.repositories.scenes import SceneRepository
from app.db.repositories.frames import FrameRepository
from app.services.storyboard_breakdown import StoryboardBreakdownService


def test_breakdown_assigns_all_line_ids(tmp_path: Path):
    db = tmp_path / "b.db"
    scenes = SceneRepository(db_path=db)
    frames = FrameRepository(db_path=db)
    sc = scenes.replace_all(
        "p1",
        [
            {
                "id": "scene_1",
                "name": "咖啡馆",
                "lines": [
                    {"id": "line_a", "type": "dialogue", "speaker": "甲", "text": "一", "emotion": ""},
                    {"id": "line_b", "type": "narration", "speaker": "旁白", "text": "二", "emotion": ""},
                ],
            }
        ],
    )[0]
    llm = MagicMock()
    # Intentionally omit line_b to exercise leftover append
    llm.chat.return_value = (
        '{"frames":[{"scene_id":"scene_1","description":"特写","shot_type":"近景",'
        '"duration":3,"line_ids":["line_a"]}]}',
        "ollama",
    )
    svc = StoryboardBreakdownService(llm=llm, scene_repo=scenes, frame_repo=frames)
    result = svc.run(project_id="p1", mode="replace_empty")
    assert result["frame_count"] >= 1
    all_ids = []
    for f in frames.list("p1"):
        all_ids.extend([x["id"] for x in f["lines"]])
    assert "line_a" in all_ids and "line_b" in all_ids
```

- [ ] **Step 2: Implement service**

Behavior:
- Load scenes (filter `scene_ids` if provided).  
- `replace_empty`: if project already has any frames and mode is replace_empty without scene filter, **no-op success** with `frame_count=existing` (or only fill scenes that have zero frames). Prefer: for each scene with zero frames, create frames from LLM.  
- Parse LLM JSON `{"frames":[...]}`.  
- Map `line_ids` → full line objects from scene.  
- Leftover line ids → append to last frame of that scene (create one frame if needed).  
- `assign_lines_only`: keep frames; clear then reassign lines by LLM `line_ids` per frame id (payload may include mapping); if too heavy, MVP: clear all frame lines for scene then apply LLM output referencing `frame_number`.  

MVP acceptable for `assign_lines_only`: same as rebuild without deleting images — update `lines`/`description` only on existing frames matched by order.

Prompt pack: ask for frames with `scene_id`, `description`, `shot_type`, `duration`, `line_ids`.

- [ ] **Step 3: Wire job**

In `jobs.py`:

```python
"storyboard_breakdown": "分镜规划",
# LINK:
"storyboard_breakdown": "/workbench/{pid}/storyboard",
# LLM_JOB_TYPES add storyboard_breakdown
```

In `dispatch_job`:

```python
if t == "storyboard_breakdown":
    from app.services.llm_provider import LLMProvider
    from app.services.storyboard_breakdown import StoryboardBreakdownService
    from app.db.repositories.scenes import SceneRepository
    from app.db.repositories.frames import FrameRepository
    svc = StoryboardBreakdownService(
        llm=LLMProvider(),
        scene_repo=SceneRepository(),
        frame_repo=FrameRepository(),
    )
    job_repo.update(jid, progress=40)
    return svc.run(
        project_id=pid,
        mode=p.get("mode") or "replace_empty",
        scene_ids=p.get("scene_ids"),
    )
```

- [ ] **Step 4: pytest PASS + commit**

```bash
git add backend/app/services/storyboard_breakdown.py backend/app/prompt_packs/storyboard_breakdown_v1/system.md backend/app/api/jobs.py backend/app/services/job_handlers.py backend/tests/test_storyboard_breakdown.py
git commit -m "feat(storyboard): LLM breakdown assigns lines to frames"
```

---

### Task 8: Storyboard UI — breakdown + drop seed-as-truth

**Files:**
- Modify: `frontend/src/pages/workbench/Storyboard.jsx`
- Modify: `frontend/src/services/api.js` (`jobsApi` already exists)

- [ ] **Step 1: Add button「从剧本生成分镜」**

```javascript
await jobsApi.create({
  type: 'storyboard_breakdown',
  project_id: projectId,
  payload: { mode: 'replace_empty', title: '分镜规划' },
})
message.success('已提交分镜规划任务')
```

On job complete (existing tracker / mount refetch): `storyboardApi.list(projectId)` and `setFrames`. Prefer API frames; if empty show empty state + CTA, **do not** treat SEED_FRAMES as synthesizable truth (keep SEED only if you must for layout demo — label as preview-only or remove from merge path when API returns []).

- [ ] **Step 2: Show frame lines snippet in detail panel**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workbench/Storyboard.jsx
git commit -m "feat(ui): wire storyboard breakdown job"
```

---

### Task 9: Edge TTS provider

**Files:**
- Create: `backend/app/services/tts/__init__.py`
- Create: `backend/app/services/tts/base.py`
- Create: `backend/app/services/tts/edge_provider.py`
- Modify: `backend/requirements.txt` — add `edge-tts>=6.1.0`
- Test: `backend/tests/test_tts_edge.py`

- [ ] **Step 1: Test with monkeypatch**

```python
from app.services.tts.edge_provider import EdgeTTSProvider


def test_edge_synthesize_returns_bytes(monkeypatch):
    async def fake_save(text, path, voice):
        from pathlib import Path
        Path(path).write_bytes(b"RIFF_FAKE_WAV")

    monkeypatch.setattr(
        "app.services.tts.edge_provider._edge_save",
        fake_save,
    )
    audio = EdgeTTSProvider(voice="zh-CN-XiaoxiaoNeural").synthesize(
        text="测试", emotion="平静"
    )
    assert audio.startswith(b"RIFF")
```

- [ ] **Step 2: Implement Edge provider**

Use tempfile + `edge_tts.Communicate(text, voice).save(path)` inside `asyncio.run` helper `_edge_save`. Emotion may be ignored.

- [ ] **Step 3: `get_tts_provider(engine: str)` in `base.py`**

```python
def get_tts_provider(engine: str = "edge", **kwargs):
    e = (engine or "edge").lower()
    if e == "edge":
        from app.services.tts.edge_provider import EdgeTTSProvider
        return EdgeTTSProvider(**kwargs)
    if e in ("voxcpm", "vox"):
        from app.services.tts.voxcpm_provider import VoxCPMProvider
        return VoxCPMProvider(**kwargs)
    raise ValueError(f"unknown tts engine: {engine}")
```

(VoxCPM class can be stub raising until Task 10.)

- [ ] **Step 4: pip install edge-tts in venv; pytest PASS; commit**

```bash
git add backend/app/services/tts backend/requirements.txt backend/tests/test_tts_edge.py
git commit -m "feat(tts): add Edge TTS provider"
```

---

### Task 10: VoxCPM provider + TTS settings

**Files:**
- Create: `backend/app/services/tts/voxcpm_provider.py`
- Create: `backend/app/services/tts_settings_store.py`
- Create: `backend/app/api/tts.py`
- Modify: `backend/app/main.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_tts_voxcpm.py`, `backend/tests/test_tts_settings.py`

- [ ] **Step 1: VoxCPM missing-weights test**

```python
from pathlib import Path
import pytest
from app.services.tts.voxcpm_provider import VoxCPMProvider, VoxCPMNotReady


def test_voxcpm_missing_dir(tmp_path: Path):
    p = VoxCPMProvider(model_dir=tmp_path / "nope")
    with pytest.raises(VoxCPMNotReady):
        p.synthesize(text="hi")
```

- [ ] **Step 2: Implement provider**

- Resolve `model_dir` from arg → `VOXCPM_MODEL_DIR` → `{MODELHUB_ROOT}/tts/VoxCPM2`.  
- Lazy-load; on failure raise `VoxCPMNotReady` with path in message.  
- Real `synthesize` calls library when present; unit tests mock `VoxCPM.from_pretrained`.

- [ ] **Step 3: Settings store** `backend/data/tts_settings.json` pattern like llm settings:

```python
{"engine": "edge", "edge_voice": "zh-CN-XiaoxiaoNeural"}
```

API:

- `GET /api/tts/settings`  
- `PUT /api/tts/settings`  
- `POST /api/tts/preview` body `{text, emotion?, engine?}` → save temp wav under media, return `{audio_url}`  
- `POST /api/tts/test` body `{engine}` — Edge short synth; VoxCPM check ready / short synth

Register router in `main.py`.

- [ ] **Step 4: pytest + commit**

```bash
git add backend/app/services/tts/voxcpm_provider.py backend/app/services/tts_settings_store.py backend/app/api/tts.py backend/app/main.py backend/tests/test_tts_voxcpm.py backend/tests/test_tts_settings.py backend/.env.example
git commit -m "feat(tts): VoxCPM provider, settings, preview API"
```

---

### Task 11: `render_compose` + ffmpeg

**Files:**
- Create: `backend/app/services/render_compose.py`
- Create: `backend/app/db/repositories/renders.py`
- Modify: `backend/app/services/job_handlers.py`, `backend/app/api/jobs.py`
- Test: `backend/tests/test_render_compose.py`

- [ ] **Step 1: Failing test with mocks**

```python
from pathlib import Path
from unittest.mock import MagicMock
from app.db.repositories.frames import FrameRepository
from app.db.repositories.renders import RenderRepository
from app.services.render_compose import RenderComposeService


def test_compose_builds_output(tmp_path: Path, monkeypatch):
    db = tmp_path / "r.db"
    media = tmp_path / "media"
    media.mkdir()
    frames = FrameRepository(db_path=db)
    # create two fake image files
    img1 = media / "a.png"
    img2 = media / "b.png"
    img1.write_bytes(b"\x89PNG\r\n\x1a\n")
    img2.write_bytes(b"\x89PNG\r\n\x1a\n")
    frames.create(
        "p1",
        scene_id="s1",
        image_url="/media/a.png",
        duration=1,
        lines=[{"id": "l1", "type": "narration", "speaker": "旁白", "text": "一", "emotion": ""}],
    )
    frames.create(
        "p1",
        scene_id="s1",
        image_url="/media/b.png",
        duration=1,
        lines=[],
    )
    tts = MagicMock()
    tts.synthesize.return_value = b"RIFF_FAKE"

    def fake_ffmpeg(cmd):
        # last arg is output path
        out = Path(cmd[-1])
        out.write_bytes(b"ftypisom")
        return 0

    monkeypatch.setattr(
        "app.services.render_compose.run_ffmpeg",
        fake_ffmpeg,
    )
    svc = RenderComposeService(
        frame_repo=frames,
        render_repo=RenderRepository(db_path=db),
        tts=tts,
        media_root=media,
        media_url_prefix="/media",
    )
    result = svc.compose(
        project_id="p1",
        episode_id="__all__",
        engine="edge",
        voice_enabled=True,
        subtitle_enabled=False,
    )
    assert result["output_url"]
    assert Path(str(media / Path(result["output_url"]).name)).exists() or result["output_url"].startswith("/media/")
```

Adjust paths to match how the app stores `/media/...` (read `settings` / existing media mount in `main.py`).

- [ ] **Step 2: Implement compose**

Algorithm per spec §7.1:
1. Select frames with `image_url`.  
2. Per frame: TTS lines → wav bytes to temp files; measure duration (if wav invalid, use `duration`).  
3. Build ffmpeg filter or per-segment then concat demuxer.  
4. Write mp4 under media dir; insert `renders` row; return dict for job result.

`run_ffmpeg(cmd: list[str]) -> int` uses `subprocess.run` with `FFMPEG_PATH` or `ffmpeg`.

- [ ] **Step 3: Job type `render_compose`**

Add to TITLE/LINK/handler; handler constructs service with real TTS from settings/payload engine.

- [ ] **Step 4: pytest PASS + commit**

```bash
git add backend/app/services/render_compose.py backend/app/db/repositories/renders.py backend/app/services/job_handlers.py backend/app/api/jobs.py backend/tests/test_render_compose.py
git commit -m "feat(render): compose slideshow video via ffmpeg + TTS"
```

---

### Task 12: Replace mock `render.py` API

**Files:**
- Modify: `backend/app/api/render.py`
- Test: `backend/tests/test_render_api.py`

- [ ] **Step 1: Episodes from scenes**

```python
@router.get("/{project_id}/episodes")
def get_episodes(project_id: str):
    scenes = SceneRepository().list_by_project(project_id)
    renders = RenderRepository().list_by_project(project_id)
    latest = renders[0] if renders else None
    items = [
        {
            "id": "__all__",
            "number": 0,
            "title": "整片",
            "title_en": "Full",
            "duration": "",
            "status": "completed" if latest else "pending",
            "frame_count": len(FrameRepository().list(project_id)),
            "video_url": latest.get("output_url") if latest else None,
        }
    ]
    for i, s in enumerate(scenes, start=1):
        items.append({
            "id": s["id"],
            "number": i,
            "title": s.get("name") or f"场景{i}",
            "title_en": "",
            "duration": "",
            "status": "pending",
            "frame_count": sum(
                1 for f in FrameRepository().list(project_id)
                if f.get("scene_id") == s["id"]
            ),
            "video_url": None,
        })
    return items
```

- [ ] **Step 2: `POST /{project_id}/render` creates job**

```python
@router.post("/{project_id}/render")
def start_render(project_id: str, request: RenderRequest):
    job = job_repo.create(
        type="render_compose",
        project_id=project_id,
        title="成片合成",
        payload={
            "episode_id": request.episode_id,
            "scene_id": None if request.episode_id == "__all__" else request.episode_id,
            "engine": getattr(request, "engine", None) or "edge",
            "voice_enabled": request.voice_enabled,
            "subtitle_enabled": request.subtitle_enabled,
            "resolution": request.resolution,
            "fps": request.fps,
        },
        link_path=f"/workbench/{project_id}/render",
    )
    job_queue.enqueue(job["id"])
    return {"task_id": job["id"], "job_id": job["id"], "status": "queued"}
```

Extend `RenderRequest` with `engine: str = "edge"`.

Status endpoint: read job by id, map progress.

- [ ] **Step 3: TestClient test create returns job_id; commit**

```bash
git add backend/app/api/render.py backend/tests/test_render_api.py
git commit -m "feat(api): real render episodes and compose job"
```

---

### Task 13: FinalRender + ModelConfig TTS UI

**Files:**
- Modify: `frontend/src/pages/workbench/FinalRender.jsx`
- Modify: `frontend/src/pages/admin/ModelConfig.jsx`
- Modify: `frontend/src/services/api.js`

- [ ] **Step 1: api helpers**

```javascript
export const renderApi = {
  episodes(projectId) {
    return request(`/api/render/${projectId}/episodes`)
  },
  start(projectId, body) {
    return request(`/api/render/${projectId}/render`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  renders(projectId) {
    return request(`/api/render/${projectId}/renders`)
  },
}

export const ttsApi = {
  settings() {
    return request('/api/tts/settings')
  },
  saveSettings(body) {
    return request('/api/tts/settings', { method: 'PUT', body: JSON.stringify(body) })
  },
  test(engine) {
    return request('/api/tts/test', {
      method: 'POST',
      body: JSON.stringify({ engine }),
    })
  },
}
```

- [ ] **Step 2: FinalRender**

- Load episodes on mount.  
- Engine Select: `edge` | `voxcpm`.  
- Start: `renderApi.start` or `jobsApi.create({type:'render_compose',...})`.  
- Remove fake `setInterval` progress; rely on jobs bar; on complete refetch episodes / set video `mediaUrl(output_url)`.  
- Disable BGM/SFX/advanced; tooltip「本轮未实现」.  
- Subtitle switch → `subtitle_enabled`.

- [ ] **Step 3: ModelConfig TTS tab** — call `ttsApi.test(engine)` instead of fake offline message where applicable.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api.js frontend/src/pages/workbench/FinalRender.jsx frontend/src/pages/admin/ModelConfig.jsx
git commit -m "feat(ui): wire final render compose and TTS test"
```

---

### Task 14: README + env docs

**Files:**
- Modify: `README.md`
- Modify: `backend/.env.example`

- [ ] **Step 1: Update README 当前状态**

- ✅ 成片：分镜静图 + Edge/VoxCPM TTS + ffmpeg 拼片（可选字幕）  
- ✅ 剧本台词 `lines` + 分镜规划分配  
- ⏳ 真视频 LTX/Wan、BGM/音效、提示词库、任务暂停、认证  

Add note: need `ffmpeg` on PATH; VoxCPM weights under `%MODELHUB_ROOT%\tts\VoxCPM2`.

- [ ] **Step 2: `.env.example`**

```
FFMPEG_PATH=ffmpeg
VOXCPM_MODEL_DIR=
# default: %MODELHUB_ROOT%/tts/VoxCPM2
```

- [ ] **Step 3: Commit**

```bash
git add README.md backend/.env.example
git commit -m "docs: note slideshow render and dual TTS status"
```

---

## Spec coverage checklist

| Spec item | Task |
|---|---|
| scenes.lines_json + expand lines+emotion | 1–5 |
| storyboard_breakdown + frame.lines | 6–8 |
| Edge + VoxCPM | 9–10 |
| render_compose Job + ffmpeg + optional subs | 11–13 |
| episodes from scenes / __all__ | 12–13 |
| BGM/SFX not implemented | 13 |
| No auth / no real video | (non-goals) |
| README | 14 |

## Self-review notes

- No TBD placeholders in tasks.  
- Job type names consistent: `storyboard_breakdown`, `render_compose`.  
- Counts always derived from normalized lines after Task 3.  
- VoxCPM may be unusable without weights; tests cover NotReady; manual verify when weights exist.
