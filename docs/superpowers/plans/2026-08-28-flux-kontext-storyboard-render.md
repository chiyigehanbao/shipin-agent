# Flux Kontext Storyboard Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make selected casting portraits real Flux Kontext image conditions, produce reviewable storyboard candidates, and allow only accepted candidates to enter MiniMax H3 I2VA.

**Architecture:** A deep `StoryboardRenderModule` compiles immutable render requests from project facts and submits them through a real Adapter seam. `FluxKontextAdapter` is the formal path; `TextOnlyFluxAdapter` is reachable only through an explicit one-attempt degradation flag. A dedicated render worker owns ComfyUI upload, execution, persistence, and candidate state transitions.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, pytest, ComfyUI HTTP workflow interface, React 18, Ant Design, Vite.

---

## Scope and file map

This plan is one vertical feature slice. It includes persistence, request compilation, Kontext workflow execution, review state, H3 gating, and the minimum frontend needed to operate the new path.

**New backend files**

- `backend/app/db/repositories/storyboard_renders.py` — immutable request and attempt persistence plus legal status transitions.
- `backend/app/services/storyboard_render/__init__.py` — package exports.
- `backend/app/services/storyboard_render/types.py` — typed Interface models and stable error codes.
- `backend/app/services/storyboard_render/compiler.py` — deterministic Prompt IR to render-request compiler.
- `backend/app/services/storyboard_render/adapters.py` — formal Kontext and explicit text-only Adapters.
- `backend/app/services/storyboard_render/module.py` — orchestration Interface for compile, submit, accept, reject, and retry.
- `backend/app/services/storyboard_render/worker.py` — dedicated serial ComfyUI execution worker.
- `backend/app/services/workflows/flux_kontext_gguf.json` — one-reference API workflow; the Adapter adds the second reference chain when needed.
- `backend/app/api/storyboard_render.py` — render-state and review routes.
- `backend/tests/test_storyboard_render_repository.py`
- `backend/tests/test_storyboard_render_compiler.py`
- `backend/tests/test_storyboard_render_adapters.py`
- `backend/tests/test_storyboard_render_worker.py`
- `backend/tests/test_storyboard_render_api.py`

**Modified backend files**

- `backend/app/db/schema.py` — migration `010_storyboard_render`.
- `backend/app/db/repositories/assets.py` and `backend/app/services/asset_store.py` — `identity_json` round trip.
- `backend/app/db/repositories/scenes.py` — scene-level `look_states_json` round trip.
- `backend/app/api/scripts.py` — expose scene-level Look State through the existing scene Interface.
- `backend/app/db/repositories/frames.py` — accepted attempt reference.
- `backend/app/services/casting.py` and `backend/app/api/assets.py` — persist structured identity anchors for casting candidates.
- `backend/app/services/model_readiness.py` — `flux_kontext` readiness.
- `backend/app/services/comfyui_client.py` — read ComfyUI node inventory for Adapter preflight.
- `backend/app/services/runtime.py` and `backend/app/main.py` — instantiate/start/stop the render worker and recover interrupted attempts.
- `backend/app/api/storyboard.py` — compatibility generation delegates to the new Module; H3 I2VA requires an accepted frame.
- `backend/tests/test_db_schema.py`, `backend/tests/test_casting.py`, `backend/tests/test_model_readiness.py`, `backend/tests/test_storyboard_generate.py`, and `backend/tests/test_storyboard_generate_video.py`.

**Modified frontend files**

- `frontend/src/services/api.js` — render-state, submit, review, retry, and scene Look State calls.
- `frontend/src/pages/workbench/Storyboard.jsx` — identity references, Look State, candidate review, explicit degradation, and H3 gate.

## Task 1: Add immutable render persistence

**Files:**

- Modify: `backend/app/db/schema.py`
- Create: `backend/app/db/repositories/storyboard_renders.py`
- Modify: `backend/app/db/repositories/frames.py`
- Test: `backend/tests/test_db_schema.py`
- Create: `backend/tests/test_storyboard_render_repository.py`

- [ ] **Step 1: Write failing schema and repository tests**

Add these assertions to `test_db_schema.py` and create the repository test:

```python
def test_storyboard_render_schema(tmp_path):
    conn = connect(tmp_path / "render-schema.db")
    migrate(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "storyboard_render_requests" in tables
    assert "storyboard_render_attempts" in tables
    scene_cols = {r[1] for r in conn.execute("PRAGMA table_info(scenes)")}
    asset_cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)")}
    frame_cols = {r[1] for r in conn.execute("PRAGMA table_info(storyboard_frames)")}
    assert "look_states_json" in scene_cols
    assert "identity_json" in asset_cols
    assert "accepted_render_attempt_id" in frame_cols
    conn.close()
```

```python
import pytest

from app.db.repositories.storyboard_renders import (
    RenderAttemptRepository,
    RenderRequestRepository,
)


def test_request_is_immutable_and_attempt_transition_is_guarded(tmp_path):
    db = tmp_path / "render.db"
    requests = RenderRequestRepository(db)
    attempts = RenderAttemptRepository(db)
    request = requests.create(
        project_id="p1",
        frame_id="f1",
        source_hash="source-1",
        request={"compiled_prompt": "preserve identity"},
        validation={"valid": True, "issues": []},
    )
    attempt = attempts.create(
        request_id=request["id"],
        project_id="p1",
        frame_id="f1",
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf",
        seed=42,
        is_degraded=False,
    )
    running = attempts.transition(attempt["id"], "running")
    candidate = attempts.transition(
        running["id"], "candidate", image_url="/media/assets/p1/candidate.png"
    )
    assert candidate["status"] == "candidate"
    accepted = attempts.transition(candidate["id"], "accepted")
    assert accepted["status"] == "accepted"
    with pytest.raises(ValueError, match="invalid_attempt_transition"):
        attempts.transition(accepted["id"], "running")
```

- [ ] **Step 2: Run the tests and verify the red state**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_db_schema.py tests/test_storyboard_render_repository.py -v
```

Expected: collection fails because `storyboard_renders` does not exist, and schema assertions fail.

- [ ] **Step 3: Add migration `010_storyboard_render`**

Append this tuple to `MIGRATE_SQL` in `backend/app/db/schema.py`:

```python
(
    "010_storyboard_render",
    """
ALTER TABLE assets ADD COLUMN identity_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE scenes ADD COLUMN look_states_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE storyboard_frames ADD COLUMN accepted_render_attempt_id TEXT;

CREATE TABLE IF NOT EXISTS storyboard_render_requests (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  frame_id TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  request_json TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_storyboard_render_requests_frame
ON storyboard_render_requests(project_id, frame_id, created_at);

CREATE TABLE IF NOT EXISTS storyboard_render_attempts (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  frame_id TEXT NOT NULL,
  asset_id TEXT,
  job_id TEXT,
  adapter TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  model_fingerprint TEXT NOT NULL DEFAULT '',
  seed INTEGER NOT NULL,
  is_degraded INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  image_url TEXT,
  error_json TEXT NOT NULL DEFAULT '{}',
  rejection_reason TEXT,
  rejection_note TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_storyboard_render_attempts_frame
ON storyboard_render_attempts(project_id, frame_id, created_at);
""",
),
```

- [ ] **Step 4: Implement request and attempt repositories**

Create `storyboard_renders.py` with JSON decoding at the repository Interface and this transition table:

```python
LEGAL_TRANSITIONS = {
    "queued": {"running", "failed"},
    "running": {"candidate", "failed"},
    "candidate": {"accepted", "rejected"},
    "accepted": {"superseded"},
    "superseded": set(),
    "rejected": set(),
    "failed": set(),
}


def _assert_transition(current: str, target: str) -> None:
    if target not in LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid_attempt_transition:{current}->{target}")
```

`RenderRequestRepository` must expose `create`, `get`, and `latest_for_frame`; it must not expose a generic update. `RenderAttemptRepository` must expose `create`, `get`, `list_for_frame`, `transition`, `attach_job`, and `fail_inflight`. JSON columns must return as `request`, `validation`, and `error` dictionaries. Attempt creation requires `model_fingerprint` so historical executions identify the exact model file selected by the Adapter.

Update `FrameRepository._row_to_frame`, `create`, and `update` so `accepted_render_attempt_id` round-trips without changing the existing default frame behavior.

- [ ] **Step 5: Run focused persistence tests**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_db_schema.py tests/test_storyboard_render_repository.py tests/test_frames_lines.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit persistence**

```powershell
git add backend/app/db/schema.py backend/app/db/repositories/storyboard_renders.py backend/app/db/repositories/frames.py backend/tests/test_db_schema.py backend/tests/test_storyboard_render_repository.py
git commit -m "feat: persist storyboard render requests"
```

## Task 2: Persist Character Identity and scene Look State

**Files:**

- Modify: `backend/app/db/repositories/assets.py`
- Modify: `backend/app/services/asset_store.py`
- Modify: `backend/app/db/repositories/scenes.py`
- Modify: `backend/app/api/scripts.py`
- Modify: `backend/app/services/casting.py`
- Modify: `backend/app/api/assets.py`
- Modify: `backend/tests/test_casting.py`
- Modify: `backend/tests/test_scenes_repo.py`
- Modify: `backend/tests/test_scripts_expand_api.py`

- [ ] **Step 1: Write failing identity and Look State tests**

```python
def test_casting_candidate_persists_structured_identity(client, completed_character):
    response = client.post(
        f"/api/assets/p1/characters/{completed_character['id']}/cast"
    )
    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert candidate["identity"]["identity_anchor"]
    assert candidate["identity"]["stable_traits"] == [
        "facial_geometry",
        "age_impression",
        "stable_hairstyle",
        "body_build",
    ]
```

```python
def test_scene_look_states_round_trip(tmp_path):
    repo = SceneRepository(tmp_path / "scene.db")
    scene = repo.replace_all("p1", [{"name": "雨巷"}])[0]
    updated = repo.update(
        "p1",
        scene["id"],
        look_states={
            "asset_c_1": {
                "wardrobe": "dark wool coat",
                "wetness": "rain-soaked hair and shoulders",
            }
        },
    )
    assert updated["look_states"]["asset_c_1"]["wardrobe"] == "dark wool coat"
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_casting.py tests/test_scenes_repo.py -v
```

Expected: failures mention missing `identity_json` and `look_states`.

- [ ] **Step 3: Extend asset and scene repositories**

In `AssetRepository.create`, accept `identity: dict[str, Any] | None = None`, serialize it to `identity_json`, and decode `identity_json` as `identity` in every returned asset. Permit `identity` in `update` by mapping it to `identity_json` before SQL generation. Mirror the same parameter through `AssetStore.create`, and add `identity: dict[str, Any] = Field(default_factory=dict)` to the `Asset` response model in `backend/app/api/assets.py`.

In `SceneRepository`, decode `look_states_json` into `look_states`, initialize it to `{}` in `replace_all`, and map an update field named `look_states` back to `look_states_json`:

```python
if "look_states" in fields:
    updates["look_states_json"] = json.dumps(
        fields["look_states"] or {}, ensure_ascii=False, sort_keys=True
    )
```

Add `look_states: dict[str, dict[str, str]] = Field(default_factory=dict)` to the `Scene` response model and `look_states: Optional[dict[str, dict[str, str]]] = None` to `SceneUpdate` in `backend/app/api/scripts.py`. The existing update route must pass the field through `model_dump(exclude_unset=True)`.

- [ ] **Step 4: Persist casting identity facts**

Keep `CastingConcept.identity_anchor` as the source but save this structure for every candidate in `cast_character`:

```python
"identity": {
    "identity_anchor": concept.identity_anchor,
    "stable_traits": [
        "facial_geometry",
        "age_impression",
        "stable_hairstyle",
        "body_build",
    ],
    "source": "casting_v1",
},
```

Legacy selected assets with empty `identity_json` remain valid; the render compiler will derive a compatibility anchor from `lock_en` and mark it `legacy_reference`.

- [ ] **Step 5: Run identity and scene tests**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_casting.py tests/test_scenes_repo.py tests/test_scripts_expand_api.py tests/test_prompt_lock_schema.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit identity facts**

```powershell
git add backend/app/db/repositories/assets.py backend/app/services/asset_store.py backend/app/db/repositories/scenes.py backend/app/services/casting.py backend/app/api/assets.py backend/app/api/scripts.py backend/tests/test_casting.py backend/tests/test_scenes_repo.py backend/tests/test_scripts_expand_api.py
git commit -m "feat: separate identity from scene look state"
```

## Task 3: Build the deterministic render-request compiler

**Files:**

- Create: `backend/app/services/storyboard_render/__init__.py`
- Create: `backend/app/services/storyboard_render/types.py`
- Create: `backend/app/services/storyboard_render/compiler.py`
- Create: `backend/tests/test_storyboard_render_compiler.py`

- [ ] **Step 1: Write compiler tests first**

Cover identity priority, scene state, dual identity ordering, third-person weak constraint, conflict rejection, and stable hashes:

```python
def selected_asset(asset_id: str, name: str) -> dict:
    return {
        "id": asset_id,
        "name": name,
        "type": "character",
        "status": "completed",
        "selection_status": "selected",
        "image_url": f"/media/assets/p1/{asset_id}.png",
        "reference_image_hash": f"sha256:{asset_id}",
        "lock_en": "balanced oval face, almond eyes, natural age impression",
        "identity": {
            "identity_anchor": "balanced oval face, almond eyes, natural age impression"
        },
    }


def visual_bible() -> ProjectVisualBible:
    return ProjectVisualBible(
        casting_aesthetic="polished commercial short-drama actor",
        realism_policy=["natural skin"],
        identity_policy=["stable face and body only"],
        state_policy=["wardrobe and weather are mutable"],
        cinematography=["restrained live action"],
        negative_defaults=["plastic skin"],
    )


def test_compile_preserves_identity_and_applies_look_state():
    result = compile_render_request(
        project_id="p1",
        frame={
            "id": "f1",
            "character": "苏遥",
            "description_en": "Su Yao runs across the alley",
            "shot_type": "medium shot",
            "angle": "eye level",
            "scene_id": "s1",
        },
        scene={
            "id": "s1",
            "location": "rain alley",
            "time": "night",
            "look_states": {
                "asset_suyao": {
                    "wardrobe": "dark wool coat",
                    "wetness": "wet hair ends",
                }
            },
        },
        assets=[selected_asset("asset_suyao", "苏遥")],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )
    assert result.validation.valid is True
    assert result.character_identities[0].reference_asset_id == "asset_suyao"
    assert "preserve the same facial identity" in result.compiled_prompt.lower()
    assert "dark wool coat" in result.compiled_prompt
    assert "wet hair ends" in result.compiled_prompt
```

```python
def test_compile_rejects_identity_terms_inside_look_state():
    scene = {
        "id": "s1",
        "look_states": {"asset_suyao": {"makeup": "change her face shape"}},
    }
    result = compile_render_request(
        project_id="p1",
        frame={"id": "f1", "character": "苏遥", "scene_id": "s1"},
        scene=scene,
        assets=[selected_asset("asset_suyao", "苏遥")],
        visual_bible=visual_bible(),
        policy=RenderPolicy(),
    )
    assert result.validation.valid is False
    assert result.validation.issues[0].code == "look_state_identity_conflict"
```

```python
def test_third_character_is_text_only_and_hash_is_stable():
    facts = {
        "project_id": "p1",
        "frame": {"id": "f3", "character": "苏遥,林默,路人", "scene_id": "s1"},
        "scene": {"id": "s1", "look_states": {}},
        "assets": [
            selected_asset("asset_suyao", "苏遥"),
            selected_asset("asset_linmo", "林默"),
            selected_asset("asset_extra", "路人"),
        ],
        "visual_bible": visual_bible(),
        "policy": RenderPolicy(),
    }
    first = compile_render_request(**facts)
    second = compile_render_request(**facts)
    assert len(first.character_identities) == 2
    assert first.weak_characters == ["路人"]
    assert first.source_hash == second.source_hash
```

- [ ] **Step 2: Run compiler tests and verify failure**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_compiler.py -v
```

Expected: import failure for the new package.

- [ ] **Step 3: Define typed Interface models and errors**

In `types.py`, define Pydantic models with these exact names:

```python
class RenderIssue(BaseModel):
    code: str
    message: str
    field: str = ""


class RenderValidation(BaseModel):
    valid: bool
    issues: list[RenderIssue] = Field(default_factory=list)


class CharacterIdentity(BaseModel):
    character_asset_id: str
    character_name: str
    reference_asset_id: str
    reference_image_url: str
    reference_image_hash: str
    identity_anchor: str
    reference_order: int
    legacy_reference: bool = False


class LookState(BaseModel):
    character_asset_id: str
    wardrobe: str = ""
    makeup: str = ""
    hair_state: str = ""
    injury: str = ""
    wetness: str = ""
    dirt: str = ""
    fatigue: str = ""


class RenderPolicy(BaseModel):
    mode: Literal["identity_first"] = "identity_first"
    max_strong_identities: int = 2
    allow_temporary_degradation: bool = False
    identity_priority: list[str] = Field(
        default_factory=lambda: ["face", "age", "hair", "body", "pose", "composition"]
    )


class StoryboardRenderRequest(BaseModel):
    project_id: str
    frame_id: str
    character_identities: list[CharacterIdentity]
    look_states: list[LookState]
    weak_characters: list[str]
    scene_spec: dict[str, Any]
    shot_spec: dict[str, Any]
    render_policy: RenderPolicy
    compiled_prompt: str
    negative_prompt: str
    width: int
    height: int
    source_hash: str
    validation: RenderValidation
```

Define `StoryboardRenderError(code, message, status_code=422)` and stable codes from the design document.

- [ ] **Step 4: Implement pure deterministic compilation**

`compile_render_request` must accept plain project facts and return `StoryboardRenderRequest`. Before calling it, the Module resolves every reference media file and injects a SHA-256 content hash as `reference_image_hash`; the pure compiler never reads the filesystem. Use canonical sorted JSON plus SHA-256 for `source_hash`. Build prompts in this fixed order:

```python
parts = [
    reference_binding_text(identities),
    identity_preservation_text(identities),
    allowed_look_changes_text(look_states),
    scene_text(scene_spec),
    shot_text(shot_spec),
    (
        "Identity and refined natural appearance take priority. "
        "If pose or composition conflicts with identity preservation, allow a small pose "
        "or framing deviation while keeping the same face, age impression, hairstyle, and build."
    ),
]
compiled_prompt = "\n\n".join(part for part in parts if part.strip())
```

Use explicit deny tokens for identity conflicts: `face shape`, `facial geometry`, `different age`, `younger`, `older`, `different person`, `body type`, and their Chinese equivalents. Do not call an LLM in this Module.

- [ ] **Step 5: Run compiler tests**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_compiler.py -v
```

Expected: all compiler tests pass.

- [ ] **Step 6: Commit the compiler**

```powershell
git add backend/app/services/storyboard_render backend/tests/test_storyboard_render_compiler.py
git commit -m "feat: compile identity-first storyboard requests"
```

## Task 4: Add the Kontext and text-only Adapters

**Files:**

- Create: `backend/app/services/workflows/flux_kontext_gguf.json`
- Create: `backend/app/services/storyboard_render/adapters.py`
- Modify: `backend/app/services/model_readiness.py`
- Modify: `backend/app/services/comfyui_client.py`
- Create: `backend/tests/test_storyboard_render_adapters.py`
- Modify: `backend/tests/test_model_readiness.py`
- Modify: `backend/tests/test_comfyui_client.py`

- [ ] **Step 1: Write Adapter contract tests**

```python
def valid_request(identity_count: int = 1) -> StoryboardRenderRequest:
    identities = [
        CharacterIdentity(
            character_asset_id=f"asset_{index}",
            character_name=f"角色{index}",
            reference_asset_id=f"asset_{index}",
            reference_image_url=f"/media/assets/p1/asset_{index}.png",
            reference_image_hash=f"sha256:asset_{index}",
            identity_anchor="balanced face and stable age impression",
            reference_order=index,
        )
        for index in range(1, identity_count + 1)
    ]
    return StoryboardRenderRequest(
        project_id="p1",
        frame_id="f1",
        character_identities=identities,
        look_states=[],
        weak_characters=[],
        scene_spec={"location": "rain alley"},
        shot_spec={"shot_type": "medium"},
        render_policy=RenderPolicy(),
        compiled_prompt="Preserve identity and change the background to a rain alley.",
        negative_prompt="plastic skin",
        width=1216,
        height=832,
        source_hash="source-1",
        validation=RenderValidation(valid=True),
    )


def ready_model_dir(tmp_path):
    models = tmp_path / "models"
    for relative in (
        "unet/flux1-kontext-dev-Q4_K_S.gguf",
        "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        "clip/clip_l.safetensors",
        "vae/ae.safetensors",
    ):
        path = models / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-model")
    return models


def test_kontext_adapter_fills_one_reference():
    workflow = FluxKontextAdapter().build(
        request=valid_request(identity_count=1),
        uploaded_images=["suyao.png"],
        seed=42,
    )
    assert workflow["4"]["inputs"]["image"] == "suyao.png"
    assert workflow["7"]["inputs"]["text"] == valid_request(1).compiled_prompt
    assert workflow["3"]["inputs"]["seed"] == 42
    assert workflow["10"]["inputs"]["unet_name"] == "flux1-kontext-dev-Q4_K_S.gguf"


def test_kontext_adapter_chains_second_reference():
    workflow = FluxKontextAdapter().build(
        request=valid_request(identity_count=2),
        uploaded_images=["suyao.png", "linmo.png"],
        seed=43,
    )
    assert workflow["20"]["class_type"] == "LoadImage"
    assert workflow["23"]["class_type"] == "ReferenceLatent"
    assert workflow["23"]["inputs"]["conditioning"] == ["8", 0]
    assert workflow["9"]["inputs"]["conditioning"] == ["23", 0]


def test_text_adapter_requires_explicit_degradation():
    request = valid_request(identity_count=1)
    with pytest.raises(StoryboardRenderError, match="degradation_not_authorized"):
        TextOnlyFluxAdapter().build(request=request, uploaded_images=[], seed=44)


def test_kontext_preflight_reports_missing_core_node(tmp_path):
    readiness = FluxKontextAdapter().preflight(
        request=valid_request(),
        models_dir=ready_model_dir(tmp_path),
        available_node_types={"LoadImage", "VAEEncode", "KSampler"},
    )
    assert readiness.ready is False
    assert "ReferenceLatent" in readiness.missing_nodes
```

- [ ] **Step 2: Run Adapter tests and verify failure**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_adapters.py tests/test_model_readiness.py -v
```

Expected: import and readiness failures.

- [ ] **Step 3: Add the one-reference API workflow**

Create a submit-ready JSON workflow with these nodes and links:

```json
{
  "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux1-kontext-dev-Q4_K_S.gguf"}},
  "13": {"class_type": "DualCLIPLoaderGGUF", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5-v1_1-xxl-encoder-Q4_K_S.gguf", "type": "flux"}},
  "15": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
  "4": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
  "5": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["4", 0]}},
  "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["15", 0]}},
  "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["13", 0]}},
  "8": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}},
  "9": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["8", 0], "guidance": 2.5}},
  "11": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
  "14": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1216, "height": 832, "batch_size": 1}},
  "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0, "model": ["10", 0], "positive": ["9", 0], "negative": ["11", 0], "latent_image": ["14", 0]}},
  "16": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["15", 0]}},
  "17": {"class_type": "SaveImage", "inputs": {"filename_prefix": "vf_flux_kontext", "images": ["16", 0]}}
}
```

- [ ] **Step 4: Implement both Adapters**

`FluxKontextAdapter.preflight` must require one or two identities, the `flux_kontext` model readiness result, and all nodes in this exact set: `LoadImage`, `FluxKontextImageScale`, `VAEEncode`, `ReferenceLatent`, `FluxGuidance`, `ConditioningZeroOut`, `EmptySD3LatentImage`, `KSampler`, `UnetLoaderGGUF`, and `DualCLIPLoaderGGUF`. `build` deep-copies the JSON, fills prompt, dimensions, seed, and uploaded image names. For two identities, add nodes `20` to `23`: `LoadImage`, `FluxKontextImageScale`, `VAEEncode`, then `ReferenceLatent`; point `FluxGuidance` at node `23`.

`TextOnlyFluxAdapter.build` must first enforce:

```python
if not request.render_policy.allow_temporary_degradation:
    raise StoryboardRenderError(
        "degradation_not_authorized",
        "纯文本临时降级必须由用户对本次生成显式授权",
        status_code=409,
    )
```

It then delegates to existing `build_workflow("flux", ...)` and never receives reference images.

- [ ] **Step 5: Add Kontext readiness**

Add this key to `REQUIRED_FILES`:

```python
"flux_kontext": [
    "unet/flux1-kontext-dev-Q4_K_S.gguf",
    "text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf",
    "clip/clip_l.safetensors",
    "vae/ae.safetensors",
],
```

Add `ComfyUIClient.available_node_types()` using `GET /object_info`; return `set(response.json().keys())` and raise `ComfyUIError` on an invalid response. `StoryboardRenderModule.submit` must call this during formal preflight and return `kontext_workflow_unavailable` with the sorted missing-node list before creating an asset, attempt, or job.

- [ ] **Step 6: Run Adapter tests**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_adapters.py tests/test_model_readiness.py tests/test_comfyui_client.py tests/test_workflows.py -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the Adapter seam**

```powershell
git add backend/app/services/workflows/flux_kontext_gguf.json backend/app/services/storyboard_render/adapters.py backend/app/services/model_readiness.py backend/app/services/comfyui_client.py backend/tests/test_storyboard_render_adapters.py backend/tests/test_model_readiness.py backend/tests/test_comfyui_client.py
git commit -m "feat: add Flux Kontext storyboard adapter"
```

## Task 5: Implement orchestration and the dedicated render worker

**Files:**

- Create: `backend/app/services/storyboard_render/module.py`
- Create: `backend/app/services/storyboard_render/worker.py`
- Modify: `backend/app/services/runtime.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_storyboard_render_worker.py`
- Modify: `backend/tests/test_test_isolation.py`

- [ ] **Step 1: Write worker and lifecycle tests**

```python
from unittest.mock import MagicMock

from app.services.comfyui_client import ComfyUIError
from app.services.storyboard_render.worker import StoryboardRenderWorker


def build_worker_fixture(tmp_path):
    reference = tmp_path / "media" / "assets" / "p1" / "suyao.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"reference-image")
    attempt = {
        "id": "attempt_1",
        "request_id": "request_1",
        "project_id": "p1",
        "frame_id": "f1",
        "asset_id": "asset_output",
        "job_id": "job_1",
        "adapter": "flux_kontext",
        "seed": 42,
        "status": "queued",
    }
    request = {
        "id": "request_1",
        "request": {
            "project_id": "p1",
            "frame_id": "f1",
            "character_identities": [
                {
                    "character_asset_id": "asset_suyao",
                    "character_name": "苏遥",
                    "reference_asset_id": "asset_suyao",
                    "reference_image_url": "/media/assets/p1/suyao.png",
                    "reference_image_hash": "sha256:suyao",
                    "identity_anchor": "balanced oval face and almond eyes",
                    "reference_order": 1,
                    "legacy_reference": False,
                }
            ],
            "look_states": [],
            "weak_characters": [],
            "scene_spec": {"location": "rain alley"},
            "shot_spec": {"shot_type": "medium"},
            "render_policy": {
                "mode": "identity_first",
                "max_strong_identities": 2,
                "allow_temporary_degradation": False,
                "identity_priority": ["face", "age", "hair", "body", "pose", "composition"],
            },
            "compiled_prompt": "Preserve Su Yao's identity.",
            "negative_prompt": "plastic skin",
            "width": 1216,
            "height": 832,
            "source_hash": "source-1",
            "validation": {"valid": True, "issues": []},
        },
    }
    requests = MagicMock()
    requests.get.return_value = request
    attempts = MagicMock()
    attempts.get.return_value = attempt
    assets = MagicMock()
    frames = MagicMock()
    jobs = MagicMock()
    client = MagicMock()
    client.upload_image.return_value = "suyao.png"
    client.submit_workflow.return_value = "prompt_1"
    client.poll_history.return_value = {"filename": "out.png", "type": "output"}
    client.download_image.side_effect = lambda meta, dest: dest.write_bytes(b"candidate")
    adapter = MagicMock()
    adapter.build.return_value = {"4": {"inputs": {"image": "suyao.png"}}}
    worker = StoryboardRenderWorker(
        requests=requests,
        attempts=attempts,
        assets=assets,
        frames=frames,
        jobs=jobs,
        client=client,
        adapters={"flux_kontext": adapter},
        output_root=tmp_path / "outputs",
        media_root=tmp_path / "media",
        poll_timeout_sec=5,
        poll_interval_sec=0.01,
    )
    return worker, attempts, client, adapter, reference


def test_worker_uploads_reference_and_marks_candidate(tmp_path):
    worker, attempts, client, adapter, reference = build_worker_fixture(tmp_path)
    worker.process("attempt_1")
    client.upload_image.assert_called_once_with(reference)
    adapter.build.assert_called_once()
    candidate_calls = [
        call for call in attempts.transition.call_args_list if call.args[1] == "candidate"
    ]
    assert len(candidate_calls) == 1
    assert candidate_calls[0].kwargs["image_url"].endswith("/attempt_1.png")


def test_worker_failure_never_calls_text_adapter(tmp_path):
    worker, attempts, client, kontext_adapter, reference = build_worker_fixture(tmp_path)
    text_adapter = MagicMock()
    worker.adapters["text_only_flux"] = text_adapter
    client.submit_workflow.side_effect = ComfyUIError("node_missing: ReferenceLatent")
    worker.process("attempt_1")
    text_adapter.build.assert_not_called()
    failed_calls = [
        call for call in attempts.transition.call_args_list if call.args[1] == "failed"
    ]
    assert len(failed_calls) == 1
    assert "ReferenceLatent" in failed_calls[0].kwargs["error"]["message"]
```

- [ ] **Step 2: Run worker tests and verify failure**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_worker.py -v
```

Expected: import failure for `worker.py`.

- [ ] **Step 3: Implement `StoryboardRenderModule`**

The Module must:

- resolve frame, scene, selected/legacy assets, Visual Bible, and scene Look State;
- call the pure compiler;
- persist each immutable request;
- reject invalid or stale requests before creating a job;
- select `flux_kontext` unless `allow_temporary_degradation` is true;
- create an asset, attempt, linked job, and enqueue only the attempt ID;
- persist `workflow_version="kontext-gguf-v1"` and `model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf"` for formal attempts;
- accept one candidate while superseding a previous accepted attempt;
- reject only candidates with one of the seven fixed rejection codes;
- retry by creating a new request and attempt, optionally retaining the old seed.

The public methods must be named `compile`, `submit`, `get_state`, `accept`, `reject`, and `retry`. Their parameters are the project ID, frame ID, typed policy, optional seed, attempt ID, rejection data, and seed-reuse flag described below. Implement the rejection path with a complete guard rather than a generic update:

```python
REJECTION_REASONS = {
    "identity_drift",
    "appearance_unrefined",
    "wrong_temperament",
    "wrong_look_state",
    "wrong_action",
    "wrong_composition",
    "other",
}


def reject(
    self,
    project_id: str,
    frame_id: str,
    attempt_id: str,
    reason: str,
    note: str,
) -> dict:
    if reason not in REJECTION_REASONS:
        raise StoryboardRenderError(
            "invalid_rejection_reason", "未知的驳回原因", status_code=422
        )
    attempt = self.attempts.get(attempt_id)
    if (
        not attempt
        or attempt["project_id"] != project_id
        or attempt["frame_id"] != frame_id
    ):
        raise StoryboardRenderError(
            "render_attempt_not_found", "渲染尝试不存在", status_code=404
        )
    return self.attempts.transition(
        attempt_id,
        "rejected",
        rejection_reason=reason,
        rejection_note=note.strip(),
        finished_at=_now(),
    )
```

`get_state` must compile current facts without persisting a new request, compare its `source_hash` with the latest stored request, and return `stale=True` when they differ. `accept` must set the frame's `accepted_render_attempt_id`, `asset_id`, `image_url`, and `status="completed"`; it must transition any previous accepted attempt to `superseded` without deleting its image.

- [ ] **Step 4: Implement the dedicated worker**

The worker queue carries only `attempt_id`. `process` performs this exact order:

```python
attempts.transition(attempt_id, "running", started_at=_now())
request = requests.get(attempt["request_id"])
paths = [resolve_media_path(item["reference_image_url"]) for item in identities]
uploaded = [client.upload_image(path) for path in paths]
workflow = adapter.build(request_model, uploaded, attempt["seed"])
prompt_id = client.submit_workflow(workflow)
meta = client.poll_history(prompt_id, timeout_sec=poll_timeout, interval_sec=poll_interval)
client.download_image(meta, output_path)
attempts.transition(
    attempt_id,
    "candidate",
    image_url=public_url,
    finished_at=_now(),
)
assets.update(project_id, attempt["asset_id"], status="completed", image_url=public_url, error=None)
frames.update(project_id, attempt["frame_id"], status="candidate", error=None)
jobs.update(attempt["job_id"], status="completed", progress=100, result={"attempt_id": attempt_id}, finished_at=_now())
```

Every exception must transition the attempt, asset, frame, and job to failed with the same normalized error message. It must not select a different Adapter.

- [ ] **Step 5: Wire runtime lifecycle**

Instantiate `storyboard_render_worker` and `storyboard_render_module` in `runtime.py`. In `main.py`, start the worker at startup and stop it at shutdown. Extend `fail_generating_entities` with `RenderAttemptRepository.fail_inflight(error="server_restarted")`.

- [ ] **Step 6: Run worker and isolation tests**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_worker.py tests/test_job_repository.py tests/test_test_isolation.py -v
```

Expected: all selected tests pass and the production SQLite file remains untouched.

- [ ] **Step 7: Commit orchestration**

```powershell
git add backend/app/services/storyboard_render/module.py backend/app/services/storyboard_render/worker.py backend/app/services/runtime.py backend/app/main.py backend/tests/test_storyboard_render_worker.py backend/tests/test_test_isolation.py
git commit -m "feat: execute traceable storyboard render attempts"
```

## Task 6: Expose render review routes and enforce the accepted-frame gate

**Files:**

- Create: `backend/app/api/storyboard_render.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/storyboard.py`
- Create: `backend/tests/test_storyboard_render_api.py`
- Modify: `backend/tests/test_storyboard_generate.py`
- Modify: `backend/tests/test_storyboard_generate_video.py`

- [ ] **Step 1: Write route and H3 gate tests**

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.repositories.storyboard_renders import (
    RenderAttemptRepository,
    RenderRequestRepository,
)
from app.main import app
from app.services.runtime import storyboard_store

client = TestClient(app)


def test_formal_submit_returns_attempt():
    formal = {
        "id": "attempt_formal",
        "adapter": "flux_kontext",
        "status": "queued",
        "is_degraded": False,
    }
    with patch("app.api.storyboard_render.get_storyboard_render_module") as factory:
        factory.return_value.submit.return_value = formal
        response = client.post(
            "/api/storyboard/p1/frames/f1/render",
            json={"seed": 42, "temporary_degradation": False},
        )
    assert response.status_code == 202
    assert response.json()["adapter"] == "flux_kontext"
    assert response.json()["status"] == "queued"


def test_temporary_degradation_is_one_attempt_only():
    results = [
        {"id": "attempt_degraded", "adapter": "text_only_flux", "status": "queued", "is_degraded": True},
        {"id": "attempt_formal", "adapter": "flux_kontext", "status": "queued", "is_degraded": False},
    ]
    with patch("app.api.storyboard_render.get_storyboard_render_module") as factory:
        factory.return_value.submit.side_effect = results
        degraded = client.post(
            "/api/storyboard/p1/frames/f1/render",
            json={"temporary_degradation": True},
        )
        formal = client.post(
            "/api/storyboard/p1/frames/f1/render",
            json={"temporary_degradation": False},
        )
    assert degraded.json()["is_degraded"] is True
    assert formal.json()["is_degraded"] is False
    assert formal.json()["adapter"] == "flux_kontext"


def test_h3_video_requires_accepted_render():
    frame = storyboard_store.create(
        "p_candidate",
        description="candidate",
        image_url="/media/assets/p_candidate/old.png",
    )
    requests = RenderRequestRepository()
    attempts = RenderAttemptRepository()
    request = requests.create(
        project_id="p_candidate",
        frame_id=frame["id"],
        source_hash="candidate-source",
        request={"compiled_prompt": "candidate"},
        validation={"valid": True, "issues": []},
    )
    attempt = attempts.create(
        request_id=request["id"],
        project_id="p_candidate",
        frame_id=frame["id"],
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf",
        seed=42,
        is_degraded=False,
    )
    attempts.transition(attempt["id"], "running")
    attempts.transition(
        attempt["id"],
        "candidate",
        image_url="/media/assets/p_candidate/candidate.png",
    )
    response = client.post(
        f"/api/storyboard/p_candidate/frames/{frame['id']}/generate-video",
        json={},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "accepted_frame_required"
```

- [ ] **Step 2: Run route tests and verify failure**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_api.py tests/test_storyboard_generate.py tests/test_storyboard_generate_video.py -v
```

Expected: new routes return 404 and the old video endpoint still accepts an unreviewed image.

- [ ] **Step 3: Add render routes**

Register the new router under the existing `/api/storyboard` prefix and implement:

```text
GET  /{project_id}/frames/{frame_id}/render-state
POST /{project_id}/frames/{frame_id}/render
POST /{project_id}/frames/{frame_id}/render-attempts/{attempt_id}/accept
POST /{project_id}/frames/{frame_id}/render-attempts/{attempt_id}/reject
POST /{project_id}/frames/{frame_id}/render-attempts/{attempt_id}/retry
```

Use request models:

```python
class SubmitRenderBody(BaseModel):
    seed: int | None = None
    temporary_degradation: bool = False


class RejectRenderBody(BaseModel):
    reason: Literal[
        "identity_drift",
        "appearance_unrefined",
        "wrong_temperament",
        "wrong_look_state",
        "wrong_action",
        "wrong_composition",
        "other",
    ]
    note: str = ""


class RetryRenderBody(BaseModel):
    reuse_seed: bool = False
```

Map `StoryboardRenderError` to `{code, message, field}` without losing its HTTP status.

- [ ] **Step 4: Preserve compatibility and enforce H3 acceptance**

Change the existing `/generate` endpoint to delegate to `StoryboardRenderModule.submit` with formal policy, while keeping its legacy frame-shaped response for existing callers.

Before resolving `image_url` in `generate_frame_video`, require `accepted_render_attempt_id`. Legacy frames created before migration may pass only when they have an existing completed image and no render attempts; mark this path in the job payload as `legacy_accepted_frame=True`. Once any render attempt exists for the frame, only an accepted attempt is legal.

- [ ] **Step 5: Run route tests**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_api.py tests/test_storyboard_generate.py tests/test_storyboard_generate_video.py tests/test_videos_generate_api.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit routes and gate**

```powershell
git add backend/app/api/storyboard_render.py backend/app/api/storyboard.py backend/app/main.py backend/tests/test_storyboard_render_api.py backend/tests/test_storyboard_generate.py backend/tests/test_storyboard_generate_video.py
git commit -m "feat: review storyboard candidates before H3"
```

## Task 7: Add the render review experience to the storyboard page

**Files:**

- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/workbench/Storyboard.jsx`

- [ ] **Step 1: Add frontend request methods**

Update the shared `request` error path so structured backend details remain usable by the page:

```javascript
const payload = typeof body.detail === 'object' && body.detail ? body.detail : { message: body.detail }
const error = new Error(payload.message || `HTTP ${res.status}`)
error.code = payload.code || ''
error.field = payload.field || ''
error.status = res.status
throw error
```

Add these methods to `storyboardApi`:

```javascript
renderState(projectId, frameId) {
  return request(`/api/storyboard/${projectId}/frames/${frameId}/render-state`)
},
submitRender(projectId, frameId, payload = {}) {
  return request(`/api/storyboard/${projectId}/frames/${frameId}/render`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
},
acceptRender(projectId, frameId, attemptId) {
  return request(`/api/storyboard/${projectId}/frames/${frameId}/render-attempts/${attemptId}/accept`, {
    method: 'POST',
    body: '{}',
  })
},
rejectRender(projectId, frameId, attemptId, payload) {
  return request(`/api/storyboard/${projectId}/frames/${frameId}/render-attempts/${attemptId}/reject`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
},
retryRender(projectId, frameId, attemptId, reuseSeed = false) {
  return request(`/api/storyboard/${projectId}/frames/${frameId}/render-attempts/${attemptId}/retry`, {
    method: 'POST',
    body: JSON.stringify({ reuse_seed: reuseSeed }),
  })
},
```

- [ ] **Step 2: Add render state loading and polling**

Add `renderState`, `renderBusy`, and `rejectReason` state. On frame change, fetch `render-state`. While the newest attempt is `queued` or `running`, poll that state every 1.5 seconds. Stop when it becomes `candidate` or `failed`.

The state reset must be keyed by `currentFrameData.id`, just like the existing H3 artifact effect, so candidates cannot leak between frames.

- [ ] **Step 3: Replace static generation behavior**

`handleGenerateFrame` must save current frame fields, then call:

```javascript
const attempt = await storyboardApi.submitRender(projectId, currentFrameData.id, {
  temporary_degradation: false,
})
setRenderState((prev) => ({ ...prev, attempts: [attempt, ...(prev?.attempts || [])] }))
message.loading('已提交 Kontext 身份一致性生成…', 1)
```

If the error code is `kontext_model_unavailable`, `kontext_workflow_unavailable`, or `reference_upload_invalid`, show a modal with the exact reason and a secondary button labelled `忽略身份一致性，临时生成`. That button must call `submitRender` with `temporary_degradation: true`; it must not change a stored global preference.

- [ ] **Step 4: Add Look State and identity reference controls**

Import `scriptsApi`, load `scriptsApi.listScenes(projectId)` alongside the existing character and scene assets, and retain the full scene records instead of names only. Show strong identity reference thumbnails and names from `renderState.request.character_identities`. Add scene-level inputs for wardrobe, makeup, hair state, injury, wetness, dirt, and fatigue. Save them with `scriptsApi.updateScene(projectId, currentFrameData.sceneId, { look_states: nextLookStates })`, keyed by character asset ID.

After saving Look State, refresh render state and display `输入已变化·需重新生成` when the latest request is stale.

- [ ] **Step 5: Add candidate review controls**

For the newest `candidate` attempt:

- show its image rather than the accepted frame in a labelled candidate panel;
- show `Kontext 正式生成` or `临时降级·身份不可信`;
- provide `通过并设为正式分镜`;
- provide rejection reason selection with all seven fixed reasons and an optional note;
- provide `按原身份重试` and a `复用 seed` checkbox.

After accept, merge the returned frame into `frames`, refresh state, and enable `生成镜头视频`. Candidate-only frames must keep the video button disabled.

- [ ] **Step 6: Build the frontend**

Run:

```powershell
Set-Location frontend
npm run build
```

Expected: Vite production build succeeds. Existing chunk-size and Sass deprecation warnings are acceptable; JavaScript errors are not.

- [ ] **Step 7: Commit frontend operation**

```powershell
git add frontend/src/services/api.js frontend/src/pages/workbench/Storyboard.jsx
git commit -m "feat: review Kontext storyboard candidates"
```

## Task 8: Regression verification and real-model acceptance

**Files:**

- Modify only files required by failures found in this task.
- Verify: all backend and frontend files changed in Tasks 1–7.

- [ ] **Step 1: Run the complete backend suite**

Run:

```powershell
Set-Location backend
python -m pytest -q
```

Expected: the complete suite passes. Record the final passing test count in the implementation handoff.

- [ ] **Step 2: Run the frontend production build again**

Run:

```powershell
Set-Location frontend
npm run build
```

Expected: build succeeds with no new error.

- [ ] **Step 3: Verify no silent degradation through an automated probe**

Run:

```powershell
Set-Location backend
python -m pytest tests/test_storyboard_render_adapters.py tests/test_storyboard_render_worker.py tests/test_storyboard_render_api.py -q
```

Expected: all tests pass, including the assertions that Kontext failure never invokes the text-only Adapter.

- [ ] **Step 4: Run the local ComfyUI preflight**

Start the project's configured ComfyUI, then request `/api/models/readiness`. Confirm `flux_kontext.ready` is true and that ComfyUI recognizes these core nodes: `FluxKontextImageScale`, `ReferenceLatent`, `ConditioningZeroOut`, `UnetLoaderGGUF`, and `DualCLIPLoaderGGUF`.

Do not download replacement weights when the existing files are present. The expected local model is `D:\ModelHub\comfyui\models\unet\flux1-kontext-dev-Q4_K_S.gguf`.

- [ ] **Step 5: Perform the three-image manual acceptance**

Use one selected casting actor and generate:

1. indoor close-up with normal wardrobe;
2. outdoor rainy-night medium shot with wet hair and changed wardrobe;
3. two-person shot with distinct blocking.

Accept only if identity remains recognizable, Look State does not rewrite the person, and the two-person frame does not swap identities. Reject failures with their structured reason so the records prove the quality gate works.

- [ ] **Step 6: Review the final diff**

Run:

```powershell
git status --short
git diff --check
git diff --stat HEAD~7..HEAD
```

Expected: only planned files plus pre-existing user changes are present; `git diff --check` has no whitespace errors.

- [ ] **Step 7: Commit any verification-only fixes**

If Step 1–6 required fixes, stage only those exact files and commit:

```powershell
git commit -m "fix: complete Kontext storyboard verification"
```

If no files changed, do not create an empty commit.

## Implementation completion criteria

- Formal storyboard generation sends one or two selected casting images to Flux Kontext.
- Character Identity is separate from scene-level Look State.
- More than two people never become more than two strong image references.
- Missing Kontext prerequisites block formal submission with structured errors.
- Text-only fallback occurs only after an explicit one-attempt user action.
- Every attempt preserves request snapshot, reference hashes, Adapter, workflow version, seed, outcome, and review reason.
- Generated images remain candidates until user acceptance.
- MiniMax H3 I2VA consumes only an Accepted Frame, with a documented legacy exception for projects that predate render attempts.
- Full backend tests and frontend production build pass.
- The three-image real-model acceptance is recorded honestly; no automated test is presented as proof of subjective attractiveness.
