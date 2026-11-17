# Identity Reference Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local identity-reference purification and similarity-warning layer so Flux Kontext preserves the selected face without inheriting the source portrait's old wardrobe or background.

**Architecture:** Keep image preparation and face scoring outside the prompt compiler. `IdentityReferenceService` owns versioned reference candidates and confirmation; `IdentityEvaluationService` scores rendered candidates without changing review state. The compiler snapshots the confirmed purified reference, while the worker uploads that snapshot and records a best-effort evaluation after image generation.

**Tech Stack:** FastAPI, Pydantic 2, SQLite, Pillow, optional OpenCV contrib (YuNet + SFace), React 18, Ant Design, pytest, Vite.

**Design spec:** `docs/superpowers/specs/2026-08-28-identity-reference-pipeline-design.md`

**Primary model sources:**

- YuNet: `https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet`
- SFace: `https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface`

---

## File map

### New backend files

- `backend/app/services/identity_reference/__init__.py` — stable public exports.
- `backend/app/services/identity_reference/types.py` — crop, candidate, readiness, detection, and evaluation contracts.
- `backend/app/services/identity_reference/face_backend.py` — optional OpenCV adapter and unavailable fallback.
- `backend/app/services/identity_reference/service.py` — media validation, deterministic crop, candidate lifecycle, and confirmation.
- `backend/app/services/identity_reference/evaluation.py` — single/two-person matching and risk labels.
- `backend/app/services/identity_reference/generation.py` — standard identity portrait Kontext job.
- `backend/app/api/identity_references.py` — identity-reference HTTP endpoints.
- `backend/scripts/install_face_identity_models.py` — explicit official model installation and manifest generation.
- `backend/tests/test_identity_reference_crop.py`
- `backend/tests/test_identity_reference_service.py`
- `backend/tests/test_identity_evaluation.py`
- `backend/tests/test_identity_reference_api.py`
- `backend/tests/test_identity_reference_generation.py`

### New frontend files

- `frontend/src/components/IdentityReferencePanel.jsx` — original/reference comparison and crop controls.
- `frontend/src/components/IdentityRiskPanel.jsx` — per-character score, risk, and face comparison.

### Existing files to modify

- `backend/requirements.txt`
- `backend/app/core/settings.py`
- `backend/app/db/schema.py`
- `backend/app/db/repositories/storyboard_renders.py`
- `backend/app/services/model_readiness.py`
- `backend/app/services/storyboard_render/types.py`
- `backend/app/services/storyboard_render/compiler.py`
- `backend/app/services/storyboard_render/module.py`
- `backend/app/services/storyboard_render/worker.py`
- `backend/app/services/job_handlers.py`
- `backend/app/services/runtime.py`
- `backend/app/api/models.py`
- `backend/app/main.py`
- `backend/tests/test_db_schema.py`
- `backend/tests/test_model_readiness.py`
- `backend/tests/test_storyboard_render_compiler.py`
- `backend/tests/test_storyboard_render_worker.py`
- `frontend/src/services/api.js`
- `frontend/src/pages/workbench/AssetGeneration.jsx`
- `frontend/src/pages/workbench/Storyboard.jsx`

---

### Task 1: Persist evaluation and extend immutable request contracts

**Files:**
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/repositories/storyboard_renders.py`
- Modify: `backend/app/services/storyboard_render/types.py`
- Test: `backend/tests/test_db_schema.py`
- Test: `backend/tests/test_storyboard_render_repository.py`

- [ ] **Step 1: Write failing migration and repository tests**

Add assertions that migration `011_identity_reference` creates `identity_evaluation_json`, repository rows deserialize it as `identity_evaluation`, and an update round-trips structured data:

```python
def test_storyboard_attempt_identity_evaluation_roundtrip(tmp_path):
    repo = RenderAttemptRepository(tmp_path / "evaluation.db")
    attempt = repo.create(
        request_id="rr_1",
        project_id="p1",
        frame_id="f1",
        adapter="flux_kontext",
        workflow_version="kontext-gguf-v1",
        model_fingerprint="unet/flux1-kontext-dev-Q4_K_S.gguf",
        seed=42,
        is_degraded=False,
    )
    result = repo.set_identity_evaluation(
        attempt["id"],
        {
            "status": "scored",
            "model_fingerprint": "opencv-sface-2021dec",
            "characters": [{"character_asset_id": "a1", "similarity": 0.57, "risk": "stable"}],
            "warnings": [],
        },
    )
    assert result["identity_evaluation"]["characters"][0]["risk"] == "stable"
```

Extend compiler fixtures to require the new immutable identity fields:

```python
assert identity.reference_source_type == "legacy_full_reference"
assert identity.reference_version == 0
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_db_schema.py tests/test_storyboard_render_repository.py tests/test_storyboard_render_compiler.py -q
```

Expected: failures for the missing migration column, missing repository method, and missing Pydantic fields.

- [ ] **Step 3: Add migration 011 and repository serialization**

Add this migration:

```sql
ALTER TABLE storyboard_render_attempts
ADD COLUMN identity_evaluation_json TEXT NOT NULL DEFAULT '{}';
```

Update `_attempt_row`:

```python
item["identity_evaluation"] = json.loads(
    item.pop("identity_evaluation_json", None) or "{}"
)
```

Add a compare-safe updater:

```python
def set_identity_evaluation(self, attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    with self._conn() as conn:
        cur = conn.execute(
            "UPDATE storyboard_render_attempts SET identity_evaluation_json = ?, updated_at = ? WHERE id = ?",
            (_json(evaluation), _now(), attempt_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise KeyError(attempt_id)
    return self.get(attempt_id)
```

Extend `CharacterIdentity` with defaults for old snapshots:

```python
reference_source_type: Literal[
    "auto_crop", "manual_crop", "upload", "generated", "legacy_full_reference"
] = "legacy_full_reference"
reference_version: int = 0
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/db/schema.py backend/app/db/repositories/storyboard_renders.py backend/app/services/storyboard_render/types.py backend/tests/test_db_schema.py backend/tests/test_storyboard_render_repository.py backend/tests/test_storyboard_render_compiler.py
git commit -m "feat: persist storyboard identity evaluations"
```

---

### Task 2: Add deterministic crop geometry and optional local face backend

**Files:**
- Create: `backend/app/services/identity_reference/__init__.py`
- Create: `backend/app/services/identity_reference/types.py`
- Create: `backend/app/services/identity_reference/face_backend.py`
- Create: `backend/tests/test_identity_reference_crop.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/app/services/model_readiness.py`
- Modify: `backend/app/api/models.py`
- Test: `backend/tests/test_model_readiness.py`

- [ ] **Step 1: Write failing crop and fallback tests**

Cover centered faces, edge faces, normalized bounds, primary-face selection, and unavailable dependencies:

```python
def test_expanded_face_crop_stays_square_and_inside_image():
    crop = expanded_face_crop(
        image_width=1024,
        image_height=1024,
        face=PixelBox(x=390, y=260, width=240, height=300),
    )
    assert crop.width == crop.height
    assert 0 <= crop.x < crop.x + crop.width <= 1024
    assert 0 <= crop.y < crop.y + crop.height <= 1024
    assert crop.y <= 260

def test_unavailable_backend_reports_without_throwing(tmp_path):
    backend = UnavailableFaceBackend("opencv_not_installed")
    assert backend.readiness().ready is False
    assert backend.detect(tmp_path / "portrait.png").status == "unavailable"
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_identity_reference_crop.py tests/test_model_readiness.py -q
```

Expected: import failures for the new package and missing readiness data.

- [ ] **Step 3: Implement pure types and crop math**

Define the shared contracts with these stable fields:

```python
class NormalizedCrop(BaseModel):
    x: float
    y: float
    width: float
    height: float

class PixelBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class DetectedFace(BaseModel):
    box: PixelBox
    landmarks: list[list[float]] = Field(default_factory=list)
    confidence: float = 1.0

class FaceDetection(BaseModel):
    status: Literal["detected", "no_face", "unavailable"]
    faces: list[DetectedFace] = Field(default_factory=list)
    reason: str = ""

class FaceReadiness(BaseModel):
    ready: bool
    reason: str = ""
    fingerprint: str = ""

@dataclass(frozen=True)
class EmbeddingFace:
    face_id: str
    box: NormalizedCrop
    embedding: list[float]
```

The protocol is shared by crop and evaluation services:

```python
class FaceBackend(Protocol):
    def readiness(self) -> FaceReadiness: ...
    def detect(self, image_path: Path) -> FaceDetection: ...
    def embedding(self, image_path: Path) -> list[float]: ...
    def embedding_faces(self, image_path: Path) -> list[EmbeddingFace]: ...
```

Implement `expanded_face_crop` as a pure function using 1.6× face width, 1.8× face height, upward bias, square clamping, and a minimum 96-pixel side.

The backend factory must import OpenCV lazily:

```python
def build_face_backend(models_dir: Path) -> FaceBackend:
    try:
        import cv2
    except ImportError:
        return UnavailableFaceBackend("opencv_not_installed")
    detector = models_dir / "face_detection_yunet_2023mar.onnx"
    recognizer = models_dir / "face_recognition_sface_2021dec.onnx"
    if not detector.is_file() or not recognizer.is_file():
        return UnavailableFaceBackend("face_model_files_missing")
    return OpenCVFaceBackend(cv2, detector, recognizer)
```

Do not import `cv2` at module import time. Do not download files at runtime.

- [ ] **Step 4: Add dependencies, paths, and readiness output**

Add:

```text
Pillow>=11.0,<13
opencv-contrib-python-headless>=4.12,<5
```

Add `settings.face_identity_models_dir = settings.modelhub_root / "face" / "models"`. Extend `/api/models/readiness` with a sibling `face_identity` object containing `ready`, `reason`, model paths, and model fingerprints; do not mix these paths into the ComfyUI model root.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass without OpenCV installed by exercising the unavailable backend.

- [ ] **Step 6: Commit**

```powershell
git add backend/requirements.txt backend/app/core/settings.py backend/app/services/model_readiness.py backend/app/api/models.py backend/app/services/identity_reference backend/tests/test_identity_reference_crop.py backend/tests/test_model_readiness.py
git commit -m "feat: add optional local face backend"
```

---

### Task 3: Build identity-reference candidate lifecycle and API

**Files:**
- Create: `backend/app/services/identity_reference/service.py`
- Create: `backend/app/api/identity_references.py`
- Create: `backend/tests/test_identity_reference_service.py`
- Create: `backend/tests/test_identity_reference_api.py`
- Modify: `backend/app/services/runtime.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing service tests**

Use a fake face backend and real temporary PNG files. Test auto extraction, manual crop, upload, confirmation, version increments, candidate retention rules, media traversal rejection, no-face behavior, and non-overwrite behavior:

```python
class FakeFaceBackend:
    def __init__(self, faces):
        self.faces = faces

    def readiness(self):
        return FaceReadiness(ready=True, reason="")

    def detect(self, _image_path):
        return FaceDetection(status="detected", faces=self.faces)

    def embedding(self, _image_path):
        return [1.0, 0.0]

    def embedding_faces(self, _image_path):
        return []

def test_confirm_candidate_promotes_version_without_mutating_source(tmp_path):
    source_path = tmp_path / "media" / "assets" / "p1" / "source.png"
    source_path.parent.mkdir(parents=True)
    Image.new("RGB", (1024, 1024), "#777777").save(source_path)
    store = AssetStore(tmp_path / "identity.db")
    source = store.create(
        project_id="p1", name="苏晚", type="character", prompt_cn="",
        prompt_en="portrait", model="flux", status="completed",
        selection_status="selected", image_url="/media/assets/p1/source.png",
        identity={"identity_anchor": "stable face"},
    )
    backend = FakeFaceBackend(
        faces=[DetectedFace(box=PixelBox(x=350, y=220, width=300, height=360), landmarks=[])]
    )
    service = IdentityReferenceService(
        assets=store,
        face_backend=backend,
        media_root=tmp_path / "media",
        output_root=tmp_path / "media" / "assets",
    )
    candidate = service.auto_extract("p1", source["id"])
    confirmed = service.confirm("p1", source["id"], candidate["id"])
    reference = confirmed["identity"]["reference"]
    assert reference["version"] == 1
    assert reference["source_type"] == "auto_crop"
    assert reference["image_hash"].startswith("sha256:")
    assert source["image_url"] != reference["image_url"]
```

- [ ] **Step 2: Run service tests and verify RED**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_identity_reference_service.py -q
```

Expected: missing `IdentityReferenceService`.

- [ ] **Step 3: Implement deterministic candidate lifecycle**

The service constructor and public methods are explicit and testable. `auto_extract` must refuse to overwrite the current reference and return a pending candidate:

```python
class IdentityReferenceService:
    def __init__(self, *, assets, face_backend, media_root: Path, output_root: Path):
        self.assets = assets
        self.face_backend = face_backend
        self.media_root = Path(media_root)
        self.output_root = Path(output_root)

    def auto_extract(self, project_id: str, asset_id: str) -> dict:
        asset = self._selected_character(project_id, asset_id)
        source = self.resolve_media_path(asset["image_url"])
        detection = self.face_backend.detect(source)
        if detection.status == "unavailable":
            raise IdentityReferenceError("face_model_unavailable")
        if not detection.faces:
            raise IdentityReferenceError("identity_face_missing")
        face = select_primary_face(detection.faces, source)
        crop = expanded_face_crop_from_image(source, face.box)
        return self._append_crop_candidate(
            asset=asset,
            source_type="auto_crop",
            source_path=source,
            crop=crop,
            detection=detection,
        )

    def confirm(self, project_id: str, asset_id: str, candidate_id: str) -> dict:
        asset = self._selected_character(project_id, asset_id)
        identity = dict(asset.get("identity") or {})
        candidates = list(identity.get("reference_candidates") or [])
        candidate = next((item for item in candidates if item["id"] == candidate_id), None)
        if candidate is None:
            raise IdentityReferenceError("identity_reference_candidate_missing")
        previous_version = int((identity.get("reference") or {}).get("version") or 0)
        identity["reference"] = {
            **candidate,
            "status": "ready",
            "version": previous_version + 1,
            "confirmed_at": now_text(),
        }
        identity["reference_candidates"] = [item for item in candidates if item["id"] != candidate_id]
        return self.assets.update(project_id, asset_id, identity=identity)
```

Implement `get_state`, `manual_crop`, and `register_upload` through the same `_append_crop_candidate` path. `manual_crop` validates normalized coordinates before image work. `register_upload` first writes a bounded temporary file below the project identity directory, validates it with Pillow, then creates a candidate from the full uploaded standard portrait. All error paths leave `identity.reference` unchanged.

Write candidate files below `outputs/assets/{project_id}/identity/`. Resolve and validate every source under `media_root`. Use Pillow to apply EXIF orientation, convert RGB, crop, resize with LANCZOS, and save PNG. Update `identity_json` atomically through `AssetStore.update`; never change `image_url` of the selected casting asset.

- [ ] **Step 4: Write failing API tests**

Override a `get_identity_reference_service` dependency and test these routes:

```text
GET  /api/assets/p1/a1/identity-reference
POST /api/assets/p1/a1/identity-reference/auto
POST /api/assets/p1/a1/identity-reference/crop
POST /api/assets/p1/a1/identity-reference/upload
POST /api/assets/p1/a1/identity-reference/confirm
```

Assert stable error mapping: 404 asset missing, 409 model unavailable, 422 no face/invalid crop, 400 invalid upload.

- [ ] **Step 5: Implement API router and runtime wiring**

Use Pydantic request models:

```python
class ManualCropRequest(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

class ConfirmIdentityReferenceRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
```

Register the router in `main.py` under `/api/assets`, after the existing assets router. Instantiate the service once in runtime with the optional face backend.

- [ ] **Step 6: Run service and API tests**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_identity_reference_service.py tests/test_identity_reference_api.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/identity_reference/service.py backend/app/api/identity_references.py backend/app/services/runtime.py backend/app/main.py backend/tests/test_identity_reference_service.py backend/tests/test_identity_reference_api.py
git commit -m "feat: manage purified identity references"
```

---

### Task 4: Compile and upload the confirmed purified reference

**Files:**
- Modify: `backend/app/services/storyboard_render/compiler.py`
- Modify: `backend/app/services/storyboard_render/module.py`
- Modify: `backend/app/services/storyboard_render/worker.py`
- Test: `backend/tests/test_storyboard_render_compiler.py`
- Test: `backend/tests/test_storyboard_render_module.py`
- Test: `backend/tests/test_storyboard_render_worker.py`

- [ ] **Step 1: Write failing reference-selection tests**

Add a selected asset with both a full casting image and confirmed purified reference:

```python
"identity": {
    "identity_anchor": "balanced oval face and almond eyes",
    "reference": {
        "status": "ready",
        "source_type": "manual_crop",
        "image_url": "/media/assets/p1/identity/a1-v2.png",
        "image_hash": "sha256:purified",
        "version": 2,
    },
}
```

Assert the compiled identity uses `a1-v2.png`, `manual_crop`, version `2`, and `legacy_reference is False`. Add a second test asserting old assets still use their full image with source type `legacy_full_reference`, version `0`, and `legacy_reference is True`.

Update worker test to create both files and assert only the purified path is uploaded.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_storyboard_render_compiler.py tests/test_storyboard_render_module.py tests/test_storyboard_render_worker.py -q
```

Expected: compiler still chooses the full asset image.

- [ ] **Step 3: Implement reference selection at the source**

Add one helper in the compiler:

```python
def _selected_reference(asset: dict[str, Any]) -> tuple[str, str, int, bool]:
    reference = (asset.get("identity") or {}).get("reference") or {}
    if reference.get("status") == "ready" and reference.get("image_url"):
        return (
            str(reference["image_url"]),
            str(reference.get("source_type") or "manual_crop"),
            int(reference.get("version") or 1),
            False,
        )
    return str(asset.get("image_url") or ""), "legacy_full_reference", 0, True
```

Make `module._assets_with_reference_hashes` resolve and hash the exact chosen reference URL, not always `asset.image_url`. The compiler must put the URL, content hash, source type, and version in `CharacterIdentity`, which automatically makes the request source hash stale after a confirmed reference changes.

Strengthen the prompt sentence to say that the reference constrains facial identity, age impression, and stable hair only; wardrobe, background, pose, and light come from the current request.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all pass and `client.upload_image` receives the purified file.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/storyboard_render/compiler.py backend/app/services/storyboard_render/module.py backend/app/services/storyboard_render/worker.py backend/tests/test_storyboard_render_compiler.py backend/tests/test_storyboard_render_module.py backend/tests/test_storyboard_render_worker.py
git commit -m "feat: render from purified identity references"
```

---

### Task 5: Score single and two-person candidates without changing review state

**Files:**
- Create: `backend/app/services/identity_reference/evaluation.py`
- Create: `backend/tests/test_identity_evaluation.py`
- Modify: `backend/app/services/storyboard_render/worker.py`
- Modify: `backend/tests/test_storyboard_render_worker.py`
- Modify: `backend/app/services/runtime.py`

- [ ] **Step 1: Write failing pure matching tests**

Keep assignment independent of OpenCV by passing detected faces and vectors:

```python
def test_two_person_matching_never_reuses_candidate_face():
    result = best_identity_assignment(
        references={"woman": [1.0, 0.0], "man": [0.0, 1.0]},
        candidates=[
            EmbeddingFace(
                face_id="left",
                box=NormalizedCrop(x=0.05, y=0.1, width=0.35, height=0.55),
                embedding=[0.95, 0.05],
            ),
            EmbeddingFace(
                face_id="right",
                box=NormalizedCrop(x=0.6, y=0.1, width=0.35, height=0.55),
                embedding=[0.02, 0.98],
            ),
        ],
    )
    assert result["woman"].face_id == "left"
    assert result["man"].face_id == "right"

@pytest.mark.parametrize(
    ("score", "risk"), [(0.50, "stable"), (0.49, "review"), (0.35, "review"), (0.34, "high_risk")]
)
def test_risk_thresholds(score, risk):
    assert identity_risk(score) == risk
```

- [ ] **Step 2: Run evaluation tests and verify RED**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_identity_evaluation.py -q
```

Expected: missing evaluation module.

- [ ] **Step 3: Implement evaluation service and one-to-one assignment**

Implement cosine similarity and assignment explicitly:

```python
def best_identity_assignment(
    references: dict[str, list[float]], candidates: list[EmbeddingFace]
) -> dict[str, IdentityMatch]:
    names = list(references)
    count = min(len(names), len(candidates))
    if count == 0:
        return {}
    best: tuple[float, tuple[str, ...], tuple[EmbeddingFace, ...]] | None = None
    for selected_names in combinations(names, count):
        for ordered in permutations(candidates, count):
            total = sum(
                cosine_similarity(references[name], face.embedding)
                for name, face in zip(selected_names, ordered, strict=True)
            )
            if best is None or total > best[0]:
                best = (total, selected_names, ordered)
    assert best is not None
    return {
        name: IdentityMatch(
            face_id=face.face_id,
            box=face.box,
            similarity=cosine_similarity(references[name], face.embedding),
        )
        for name, face in zip(best[1], best[2], strict=True)
    }

def identity_risk(score: float) -> str:
    if score >= 0.50:
        return "stable"
    if score >= 0.35:
        return "review"
    return "high_risk"
```

The service accepts snapshot identities and output image path:

```python
class IdentityEvaluationService:
    def evaluate(self, identities: list[CharacterIdentity], candidate_path: Path) -> dict:
        if not self.face_backend.readiness().ready:
            return {"status": "unscored", "characters": [], "warnings": ["face_model_unavailable"]}
        reference_vectors = {
            identity.character_asset_id: self.face_backend.embedding(
                self.resolve_media_path(identity.reference_image_url)
            )
            for identity in identities
        }
        candidate_faces = self.face_backend.embedding_faces(candidate_path)
        matches = best_identity_assignment(reference_vectors, candidate_faces)
        return self.serialize_matches(identities, matches)

    def serialize_matches(self, identities, matches):
        characters = []
        for identity in identities:
            match = matches.get(identity.character_asset_id)
            characters.append({
                "character_asset_id": identity.character_asset_id,
                "character_name": identity.character_name,
                "similarity": match.similarity if match else None,
                "risk": identity_risk(match.similarity) if match else "unscored",
                "candidate_face": match.box.model_dump(mode="json") if match else None,
            })
        return {
            "status": "scored" if any(item["similarity"] is not None for item in characters) else "unscored",
            "model_fingerprint": self.face_backend.readiness().fingerprint,
            "characters": characters,
            "warnings": [] if all(item["similarity"] is not None for item in characters) else ["candidate_face_missing"],
        }
```

Define `IdentityMatch` as a frozen dataclass in `evaluation.py`. For one or two identities, brute-force combinations/permutations are sufficient and deterministic. Never bind two identities to the same candidate face. Do not persist vectors.

- [ ] **Step 4: Write failing worker best-effort tests**

Add one test where evaluation returns scores and repository receives them, plus one where evaluation raises and the attempt remains `candidate` with `status: unscored`:

```python
assert attempts.set_identity_evaluation.call_args.args[1]["status"] == "unscored"
assert any(call.args[1] == "candidate" for call in attempts.transition.call_args_list)
```

- [ ] **Step 5: Integrate evaluation after the candidate transition**

Download the PNG, transition to `candidate`, update asset/frame, then evaluate inside its own `try/except`. On evaluation failure call `set_identity_evaluation` with `unscored` and a stable warning. Never enter the outer render-failure handler after candidate generation succeeded.

- [ ] **Step 6: Run evaluation and worker tests**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_identity_evaluation.py tests/test_storyboard_render_worker.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/identity_reference/evaluation.py backend/app/services/storyboard_render/worker.py backend/app/services/runtime.py backend/tests/test_identity_evaluation.py backend/tests/test_storyboard_render_worker.py
git commit -m "feat: warn on storyboard identity drift"
```

---

### Task 6: Generate standard identity portrait candidates as explicit jobs

**Files:**
- Create: `backend/app/services/identity_reference/generation.py`
- Create: `backend/tests/test_identity_reference_generation.py`
- Modify: `backend/app/services/job_handlers.py`
- Modify: `backend/app/api/identity_references.py`
- Modify: `backend/tests/test_identity_reference_api.py`

- [ ] **Step 1: Write failing generation tests**

Test that generation uses the selected character's current confirmed reference when available, otherwise its full image, uses the fixed neutral-portrait instruction, downloads a candidate PNG, and appends a `generated` reference candidate without confirming it:

```python
previous_reference = {
    "status": "ready",
    "image_url": "/media/assets/p1/identity/v1.png",
    "version": 1,
}
result = generator.run(project_id="p1", asset_id="a1", seed=42)
candidate = result["candidate"]
updated = store.get("p1", "a1")
assert candidate["source_type"] == "generated"
assert candidate["status"] == "pending"
assert updated["identity"]["reference"] == previous_reference
request = adapter.build.call_args.kwargs["request"]
assert "neutral expression" in request.compiled_prompt
assert "plain background" in request.compiled_prompt
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_identity_reference_generation.py tests/test_identity_reference_api.py -q
```

Expected: missing generator and `/generate` endpoint.

- [ ] **Step 3: Implement an `identity_reference_generate` JobQueue handler**

The endpoint creates a normal job and returns immediately:

```python
job = job_repo.create(
    type="identity_reference_generate",
    project_id=project_id,
    title=f"标准身份照 · {asset['name']}",
    payload={"asset_id": asset_id, "seed": body.seed},
    link_path=f"/workbench/{project_id}/assets",
)
job_queue.enqueue(job["id"])
return job
```

The job handler dynamically imports runtime dependencies, runs a dedicated Kontext workflow, polls ComfyUI, downloads to the identity candidate directory, and calls `IdentityReferenceService.register_generated`. It must not create a storyboard frame or `storyboard_render_attempt`.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/identity_reference/generation.py backend/app/services/job_handlers.py backend/app/api/identity_references.py backend/tests/test_identity_reference_generation.py backend/tests/test_identity_reference_api.py
git commit -m "feat: generate standard identity references"
```

---

### Task 7: Add the character identity-reference desk

**Files:**
- Create: `frontend/src/components/IdentityReferencePanel.jsx`
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/workbench/AssetGeneration.jsx`

- [ ] **Step 1: Add identity-reference API methods**

First make the existing `request` wrapper preserve JSON defaults while allowing the browser to set a multipart boundary:

```javascript
async function request(path, options = {}) {
  const isForm = options.body instanceof FormData
  const headers = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers || {}),
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    let body = {}
    try { body = await res.json() } catch (_error) { body = {} }
    const payload = typeof body.detail === 'object' && body.detail
      ? body.detail
      : { message: body.detail }
    const error = new Error(payload.message || `HTTP ${res.status}`)
    error.code = payload.code || ''
    error.field = payload.field || ''
    error.status = res.status
    throw error
  }
  return res.json()
}
```

Add methods with the existing `request` wrapper. Upload uses `FormData` and must not set a JSON content type:

```javascript
identityReference(projectId, assetId) { return request(`/api/assets/${projectId}/${assetId}/identity-reference`) },
autoIdentityReference(projectId, assetId) { return request(`/api/assets/${projectId}/${assetId}/identity-reference/auto`, { method: 'POST', body: '{}' }) },
cropIdentityReference(projectId, assetId, crop) { return request(`/api/assets/${projectId}/${assetId}/identity-reference/crop`, { method: 'POST', body: JSON.stringify(crop) }) },
uploadIdentityReference(projectId, assetId, file) {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/assets/${projectId}/${assetId}/identity-reference/upload`, { method: 'POST', body: form })
},
confirmIdentityReference(projectId, assetId, candidateId) { return request(`/api/assets/${projectId}/${assetId}/identity-reference/confirm`, { method: 'POST', body: JSON.stringify({ candidate_id: candidateId }) }) },
generateIdentityReference(projectId, assetId, seed = null) { return request(`/api/assets/${projectId}/${assetId}/identity-reference/generate`, { method: 'POST', body: JSON.stringify({ seed }) }) },
```

- [ ] **Step 2: Build the isolated panel component**

`IdentityReferencePanel` receives `projectId`, `asset`, `mediaUrl`, and `onChanged`. It displays the original and current reference side by side, then pending candidates. Implement a native pointer-driven square crop overlay with four normalized numbers; no new frontend dependency. Clamp the crop in one pure helper:

```javascript
export function clampSquareCrop({ x, y, size }) {
  const safeSize = Math.min(1, Math.max(0.1, size))
  return {
    x: Math.min(1 - safeSize, Math.max(0, x)),
    y: Math.min(1 - safeSize, Math.max(0, y)),
    width: safeSize,
    height: safeSize,
  }
}
```

Required states: model unavailable, no current reference, legacy full-reference warning, pending candidate, ready reference with version, busy/error, and generated job submitted.

- [ ] **Step 3: Mount only for the selected completed character**

In `AssetGeneration.jsx`, render the panel below Casting only when:

```javascript
activeTab === 'character' &&
currentAsset.selection_status === 'selected' &&
currentAsset.status === 'completed' &&
currentAsset.image_url
```

After confirm, reload assets so the compiler sees the new nested identity state.

- [ ] **Step 4: Run frontend production build**

```powershell
npm run build
```

Expected: Vite build succeeds; the existing large-chunk warning is acceptable.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/IdentityReferencePanel.jsx frontend/src/services/api.js frontend/src/pages/workbench/AssetGeneration.jsx
git commit -m "feat: review character identity references"
```

---

### Task 8: Show identity risk on storyboard candidates

**Files:**
- Create: `frontend/src/components/IdentityRiskPanel.jsx`
- Modify: `frontend/src/pages/workbench/Storyboard.jsx`

- [ ] **Step 1: Build a risk component with deterministic labels**

Use these mappings exactly:

```javascript
const RISK_META = {
  stable: { color: 'success', label: '身份稳定' },
  review: { color: 'warning', label: '需要复核' },
  high_risk: { color: 'error', label: '身份高风险' },
  unscored: { color: 'default', label: '未评分' },
}
```

For each character show reference version/source, score to three decimals, risk label, reference image, and candidate-face crop. Candidate crop can use the output image with CSS `object-position` derived from the normalized box; do not create or persist extra cropped biometric files.

- [ ] **Step 2: Integrate without changing acceptance behavior**

Render the panel when `candidateAttempt` exists. Pass `candidateAttempt.identity_evaluation`, `renderIdentities`, candidate URL, and character assets. Keep the existing Accept button enabled for all risk states because human review remains authoritative. If the current reference version differs from the snapshot, show “历史身份版本” rather than overwriting the displayed source.

- [ ] **Step 3: Run frontend production build**

```powershell
npm run build
```

Expected: Vite build succeeds with no new warnings beyond the existing chunk-size warning.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/components/IdentityRiskPanel.jsx frontend/src/pages/workbench/Storyboard.jsx
git commit -m "feat: surface storyboard identity risk"
```

---

### Task 9: Install official local models and perform real A/B acceptance

**Files:**
- Create: `backend/scripts/install_face_identity_models.py`
- Modify: `backend/tests/test_model_readiness.py`
- Verification artifact outside Git: `{MODELHUB_ROOT}/outputs/qa/identity-reference-acceptance/`

- [ ] **Step 1: Write the explicit installer**

Use only these official raw URLs:

```python
MODELS = {
    "face_detection_yunet_2023mar.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
```

The script requires an explicit `--target`, downloads to temporary sibling files, rejects Git LFS pointer text, atomically renames completed files, computes SHA-256, and writes `manifest.json` containing URL, size, and hash. It must not be imported or called by application startup.

- [ ] **Step 2: Add manifest-integrity readiness tests**

Test ready, missing, and post-install corruption states. Readiness compares current file size/hash with `manifest.json`; mismatch yields `face_model_hash_mismatch`.

- [ ] **Step 3: Run focused and full backend tests before installation**

```powershell
D:\AI\python3.13.14\python.exe -m pytest tests/test_model_readiness.py tests/test_identity_reference_crop.py tests/test_identity_reference_service.py tests/test_identity_evaluation.py tests/test_identity_reference_api.py tests/test_identity_reference_generation.py tests/test_storyboard_render_compiler.py tests/test_storyboard_render_worker.py -q
D:\AI\python3.13.14\python.exe -m pytest -q
```

Expected: all tests pass with the unavailable backend path.

- [ ] **Step 4: Install dependencies and official models explicitly**

Run with user-approved network/filesystem access:

```powershell
D:\AI\python3.13.14\python.exe -m pip install "Pillow>=11.0,<13" "opencv-contrib-python-headless>=4.12,<5"
D:\AI\python3.13.14\python.exe scripts/install_face_identity_models.py --target D:\ModelHub\face\models
```

Expected: readiness reports both files, sizes, SHA-256 values, model fingerprints, and `ready: true`.

- [ ] **Step 5: Run automatic extraction on the two existing selected characters**

Use the production API or an isolated QA database copied from the same character references. Confirm only visually correct identity crops. Record the original source URL, purified URL, crop, model fingerprints, hash, and reference version in the QA manifest.

- [ ] **Step 6: Generate controlled A/B candidates**

Use the same source images, seeds, scene descriptions, and Look States for both paths:

1. Indoor close-up.
2. Rainy-night medium shot with a tailored wool coat.
3. Two-person medium-wide shot with distinct blocking.

The A side uses `legacy_full_reference`; the B side uses confirmed purified references. Leave all six images as review candidates until visual inspection.

- [ ] **Step 7: Record structured human decisions**

For each B image record face geometry, age impression, hairstyle, wardrobe execution, composition, per-character SFace score, and final accept/reject reason. Acceptance is not forced by the score. Store the QA DB and JSON manifest under `D:\ModelHub\outputs\qa\identity-reference-acceptance\`.

- [ ] **Step 8: Run final verification**

```powershell
D:\AI\python3.13.14\python.exe -m pytest -q
npm run build
git diff --check
git status --short
```

Expected: all backend tests pass, frontend build succeeds, no whitespace errors, and only intentional plan/implementation files are changed.

- [ ] **Step 9: Commit installer and final test changes**

```powershell
git add backend/scripts/install_face_identity_models.py backend/tests/test_model_readiness.py
git commit -m "chore: install local identity models explicitly"
```

---

## Plan self-review checklist

- Every approved spec requirement maps to Tasks 1–9.
- Identity reference candidates and confirmed references use distinct fields.
- Historical request snapshots carry URL, content hash, source type, and version.
- Candidate scoring never changes candidate review state.
- Missing OpenCV/models never blocks the legacy rendering path.
- Runtime never downloads models silently.
- Single and two-person matching have deterministic tests.
- Standard identity generation does not create hidden storyboard frames.
- Frontend acceptance remains a human action at every risk level.
- Real acceptance compares identical seeds and scene inputs across A/B.
