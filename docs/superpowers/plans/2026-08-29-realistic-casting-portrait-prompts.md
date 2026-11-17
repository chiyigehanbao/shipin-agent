# Realistic Casting Portrait Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace beauty-retouched AI casting portraits with physically believable, unretouched actor casting photographs while preserving prior casting rounds for A/B comparison.

**Architecture:** Keep the change inside the existing casting boundary. `casting.py` owns the positive realism contract, deterministic fallbacks, LLM validation, legacy-brief cleanup, and secondary negative prompt; `assets.py` owns candidate persistence and makes every recast a new immutable round. Existing API schemas, database columns, frontend grouping, identity references, storyboard rendering, and MiniMax H3 remain unchanged.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, unittest.mock, SQLite asset repository, local ComfyUI Flux workflow.

---

## File map

- Modify `backend/app/services/casting.py`: define the casting-photography prompt contract, sanitize legacy briefs, validate LLM output, build deterministic realistic fallbacks, and expose the shared negative prompt.
- Modify `backend/app/api/assets.py`: apply the shared negative prompt, create an immutable candidate group on recast, and enforce one selected casting identity across all same-name history.
- Modify `backend/tests/test_casting.py`: cover realism acceptance, beauty-trigger rejection, legacy-brief cleanup, immutable recast history, and cross-round selection.
- Read only `frontend/src/pages/workbench/AssetGeneration.jsx`: confirm that existing same-name grouping displays all historical versions; no frontend edit is planned.

### Task 1: Define and enforce the realistic casting prompt contract

**Files:**
- Modify: `backend/tests/test_casting.py:1-63`
- Modify: `backend/app/services/casting.py:1-104`

- [ ] **Step 1: Add a test helper and a failing acceptance test for realistic LLM output**

Add this helper near `FakeLLM` and replace `test_casting_service_returns_four_distinct_polished_candidates` with the following test:

```python
def realistic_prompt(anchor: str) -> str:
    return (
        "unretouched actor casting photograph, "
        f"{anchor}, believable age, stable natural hairstyle, neutral rested expression, "
        "matte skin response, visible natural pores and fine facial texture, "
        "subtle uneven skin tone, minor facial asymmetry, faint natural under-eye texture, "
        "restrained specular highlights on the nose and lower lip only, "
        "soft highlight roll-off without facial glow, minimal colorless grooming, "
        "plain medium-gray crew-neck cotton top with shoulders covered, "
        "chest-up eye-level framing, 50mm lens at f/8, "
        "both eyes and facial planes equally resolved, "
        "large diffused key light placed 45 degrees off camera, "
        "neutral gray background, neutral color response, restrained microcontrast, "
        "identical camera distance, exposure and comparison framing"
    )


def test_casting_service_accepts_four_distinct_unretouched_candidates():
    candidates = [
        {
            "label": f"真实方案{i}",
            "identity_anchor": f"distinct permanent facial geometry {i}",
            "prompt_en": realistic_prompt(f"distinct permanent facial geometry {i}"),
        }
        for i in range(1, 5)
    ]
    concepts = CastingService(llm=FakeLLM(json.dumps({"candidates": candidates}))).generate(
        name="苏遥",
        brief="都市悬疑剧女主，28岁，聪明克制",
    )

    assert [item.label for item in concepts] == [f"真实方案{i}" for i in range(1, 5)]
    assert len({item.identity_anchor for item in concepts}) == 4
    assert all("unretouched actor casting photograph" in item.prompt_en for item in concepts)
    assert all("matte skin response" in item.prompt_en for item in concepts)
    assert all("50mm lens at f/8" in item.prompt_en for item in concepts)
```

- [ ] **Step 2: Run the acceptance test and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_casting_service_accepts_four_distinct_unretouched_candidates -q -p no:cacheprovider --basetemp=backend/data/pytest-real-casting-red-1
```

Expected: FAIL because the current `_valid` requires `commercial short-drama` and rejects the new contract, so fallback labels are returned instead of `真实方案1` through `真实方案4`.

- [ ] **Step 3: Add failing tests for beauty triggers and legacy-brief contamination**

Add:

```python
@pytest.mark.parametrize(
    "beauty_trigger",
    [
        "polished commercial",
        "pale skin",
        "flawless skin",
        "perfect skin",
        "beauty lighting",
        "soft frontal studio light",
        "harmonious distinctive features",
        "85mm portrait",
    ],
)
def test_casting_service_rejects_beauty_retouched_llm_prompts(beauty_trigger):
    candidates = [
        {
            "label": f"污染方案{i}",
            "identity_anchor": f"face geometry {i}",
            "prompt_en": f"{realistic_prompt(f'face geometry {i}')}, {beauty_trigger}",
        }
        for i in range(1, 5)
    ]
    concepts = CastingService(llm=FakeLLM(json.dumps({"candidates": candidates}))).generate(
        name="苏遥",
        brief="女主",
    )

    assert all(item.label != "污染方案1" for item in concepts)
    assert all(beauty_trigger not in item.prompt_en.lower() for item in concepts)


def test_fallback_removes_legacy_beauty_phrases_from_source_brief():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief=(
            "polished commercial short-drama actor | pale skin | "
            "harmonious distinctive features | soft frontal studio light | 85mm portrait"
        ),
    )
    combined = " ".join(item.prompt_en.lower() for item in concepts)

    assert "polished" not in combined
    assert "pale skin" not in combined
    assert "soft frontal studio light" not in combined
    assert "85mm" not in combined
    assert all("visible natural pores and fine facial texture" in item.prompt_en for item in concepts)
    assert all("soft highlight roll-off without facial glow" in item.prompt_en for item in concepts)
```

Add `import json` and `import pytest` at the top of the test file and remove the function-local `import json`.

- [ ] **Step 4: Run the new rejection tests and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_casting_service_rejects_beauty_retouched_llm_prompts backend/tests/test_casting.py::test_fallback_removes_legacy_beauty_phrases_from_source_brief -q -p no:cacheprovider --basetemp=backend/data/pytest-real-casting-red-2
```

Expected: FAIL because the current validator accepts beauty language when `commercial short-drama` is present, and the current fallback itself emits `polished`, `harmonious`, `85mm`, and frontal studio lighting.

- [ ] **Step 5: Implement the positive realism contract and secondary negative prompt**

In `backend/app/services/casting.py`, replace the current word tuples and fallback definitions with:

```python
FORBIDDEN_STATE_WORDS = ("rain", "wet", "blood", "mud", "exhausted", "sweat", "injury")

BEAUTY_TRIGGER_PHRASES = (
    "polished",
    "pale skin",
    "flawless",
    "perfect skin",
    "beauty lighting",
    "soft frontal studio light",
    "harmonious distinctive features",
    "85mm portrait",
    "85mm lens",
)

REQUIRED_REALISM_PHRASES = (
    "unretouched actor casting photograph",
    "matte skin response",
    "visible natural pores and fine facial texture",
    "subtle uneven skin tone",
    "minor facial asymmetry",
    "soft highlight roll-off without facial glow",
    "50mm lens at f/8",
    "both eyes and facial planes equally resolved",
    "large diffused key light placed 45 degrees off camera",
    "identical camera distance, exposure and comparison framing",
)

CASTING_NEGATIVE_PROMPT = (
    "waxy skin, plastic skin, porcelain skin, wet glossy skin, oily facial highlights, "
    "facial glow, beauty retouching, skin smoothing, airbrushed skin, "
    "over-sharpening halos, HDR microcontrast, excessive clarity, glassy eyes, "
    "enlarged eyes, tiny nose, pointed chin, generic influencer face, doll face, "
    "heavy makeup, shallow depth of field, one eye out of focus, bare shoulders, "
    "lingerie straps, text, watermark"
)

_FALLBACKS = (
    (
        "温润克制",
        "softly rectangular oval face, medium cheekbone width, gently broad jaw, "
        "almond eyes with slightly unequal lid height, straight medium-width nose, full lower lip",
    ),
    (
        "清醒知性",
        "heart-shaped face, broad temples, tapered jaw, horizontal brows, "
        "close-set hooded almond eyes, low straight nasal bridge, narrow upper lip",
    ),
    (
        "疏离沉静",
        "long oval face, high narrow cheekbones, slim lower face, deep-set narrow eyes, "
        "long straight nose, small asymmetrical mouth",
    ),
    (
        "冷静果断",
        "angular oval face, pronounced jaw corners, low straight brows, wide-set focused eyes, "
        "defined nasal tip, balanced medium lips",
    ),
)
```

Add these helpers below `_clean_json`:

```python
def _sanitize_brief(brief: str) -> str:
    text = brief or ""
    for phrase in (*BEAUTY_TRIGGER_PHRASES, *FORBIDDEN_STATE_WORDS):
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" |,.;")


def _realistic_prompt(*, context: str, anchor: str) -> str:
    role_context = f"Role context: {context}, " if context else ""
    return (
        "unretouched actor casting photograph, "
        f"{role_context}permanent facial identity: {anchor}, believable age, "
        "stable natural hairstyle, neutral rested expression, matte skin response, "
        "visible natural pores and fine facial texture, subtle uneven skin tone, "
        "minor facial asymmetry, faint natural under-eye texture, "
        "restrained specular highlights on the nose and lower lip only, "
        "soft highlight roll-off without facial glow, minimal colorless grooming, "
        "plain medium-gray crew-neck cotton top with shoulders covered, "
        "chest-up eye-level framing, 50mm lens at f/8, "
        "both eyes and facial planes equally resolved, "
        "large diffused key light placed 45 degrees off camera, neutral gray background, "
        "neutral color response, restrained microcontrast, "
        "identical camera distance, exposure and comparison framing"
    )
```

Rewrite `_fallback_concepts` and `_valid`:

```python
def _fallback_concepts(name: str, brief: str) -> list[CastingConcept]:
    clean_brief = _sanitize_brief(brief)
    context = ". ".join(part for part in (f"Character: {name}", clean_brief) if part)
    return [
        CastingConcept(
            label=label,
            identity_anchor=anchor,
            prompt_en=_realistic_prompt(context=context, anchor=anchor),
        )
        for label, anchor in _FALLBACKS
    ]


def _valid(concepts: list[CastingConcept]) -> bool:
    if len(concepts) != 4:
        return False
    anchors = {item.identity_anchor.strip().lower() for item in concepts}
    if len(anchors) != 4 or "" in anchors:
        return False
    for item in concepts:
        anchor_low = item.identity_anchor.lower()
        prompt_low = item.prompt_en.lower()
        combined = f"{anchor_low} {prompt_low}"
        if any(phrase not in prompt_low for phrase in REQUIRED_REALISM_PHRASES):
            return False
        if any(phrase in combined for phrase in BEAUTY_TRIGGER_PHRASES):
            return False
        if any(word in combined for word in FORBIDDEN_STATE_WORDS):
            return False
    return True
```

- [ ] **Step 6: Rewrite the LLM casting-director instruction**

Replace the system-message content in `CastingService.generate` with:

```python
"content": (
    "You are a casting director preparing unretouched actor comparison photographs. "
    "Return JSON only as "
    '{"candidates":[{"label":"Chinese label","identity_anchor":"stable English facial identity","prompt_en":"English Flux portrait prompt"}]}. '
    "Create exactly four credible working-actor options with clearly different, non-idealized "
    "permanent facial geometry. Each option must differ in at least two of face shape, brow and eye "
    "geometry, nose geometry, lip geometry, cheekbones, or jaw. Do not create four variants of one "
    "generic influencer face. Identity anchors contain permanent geometry and age impression only. "
    "Every prompt must contain these exact phrases: "
    + "; ".join(REQUIRED_REALISM_PHRASES)
    + ". Use a stable natural hairstyle, neutral rested expression, minimal colorless grooming, "
    "a plain medium-gray crew-neck cotton top with shoulders covered, neutral gray background, and "
    "the same camera distance, exposure, light position and framing for all four options. "
    "Treat any photography, beauty, lighting, skin-finish or lens wording already present in the user "
    "brief as obsolete source material. Never use polished, pale skin, flawless, perfect skin, beauty "
    "lighting, soft frontal studio light, harmonious distinctive features, 85mm portrait or 85mm lens. "
    "Never encode rain, wetness, blood, mud, exhaustion, sweat, injury, plot emotion, weather, "
    "wardrobe damage, makeup changes or pose changes."
),
```

Keep the user message and public method signature unchanged.

- [ ] **Step 7: Run the casting service tests and verify GREEN**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py -q -p no:cacheprovider --basetemp=backend/data/pytest-real-casting-green-1
```

Expected: all tests in `test_casting.py` PASS. If an old test still asserts `commercial short-drama`, update it to assert `unretouched actor casting photograph`; do not loosen the new validator.

- [ ] **Step 8: Commit the prompt contract**

```powershell
git add -- backend/app/services/casting.py backend/tests/test_casting.py
git commit -m "feat: make casting portraits physically realistic"
```

### Task 2: Preserve immutable casting rounds and one selected identity

**Files:**
- Modify: `backend/tests/test_casting.py:64-205`
- Modify: `backend/app/api/assets.py:226-333`

- [ ] **Step 1: Add a failing API test for immutable recasting history**

Add a test using the existing `client`, patch layout, and `realistic_prompt` helper:

```python
def test_recasting_existing_candidate_creates_new_group_without_overwriting_history():
    source = {
        "id": "asset_old_1",
        "project_id": "p_recast",
        "name": "苏晚",
        "name_en": "Su Wan",
        "type": "character",
        "status": "completed",
        "prompt_cn": "旧方案1",
        "prompt_en": "legacy portrait",
        "negative_prompt": "",
        "lock_en": "old anchor 1",
        "model": "flux",
        "aspect": "portrait",
        "image_url": "/media/old-1.png",
        "error": None,
        "created_at": "t",
        "candidate_group_id": "cast_old",
        "candidate_index": 1,
        "selection_status": "selected",
    }
    old_group = [
        {**source, "id": f"asset_old_{i}", "candidate_index": i}
        for i in range(1, 5)
    ]
    concepts = [
        type(
            "Concept",
            (),
            {
                "label": f"新方案{i}",
                "identity_anchor": f"new anchor {i}",
                "prompt_en": realistic_prompt(f"new anchor {i}"),
            },
        )()
        for i in range(1, 5)
    ]

    with patch("app.api.assets.store.get", return_value=source), \
         patch("app.api.assets.store.list", return_value=old_group), \
         patch("app.api.assets.check_model", return_value={"ready": True, "missing_files": []}), \
         patch("app.api.assets.client.health", return_value=True), \
         patch("app.api.assets.get_casting_service") as factory, \
         patch("app.api.assets.store.update") as update, \
         patch("app.api.assets.store.create") as create, \
         patch("app.api.assets.queue.enqueue"), \
         patch("app.api.assets.job_repo") as jobs:
        factory.return_value.generate.return_value = concepts
        create.side_effect = lambda **fields: {
            **source,
            "id": f"asset_new_{fields['candidate_index']}",
            **fields,
        }
        jobs.create.side_effect = lambda **kw: {"id": f"job_{kw['payload']['asset_id']}"}
        response = client.post("/api/assets/p_recast/characters/asset_old_1/cast")

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_group_id"] != "cast_old"
    assert [item["id"] for item in body["candidates"]] == [
        "asset_new_1", "asset_new_2", "asset_new_3", "asset_new_4"
    ]
    assert create.call_count == 4
    update.assert_not_called()
```

- [ ] **Step 2: Run the recast-history test and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_recasting_existing_candidate_creates_new_group_without_overwriting_history -q -p no:cacheprovider --basetemp=backend/data/pytest-casting-history-red-1
```

Expected: FAIL because the current endpoint reuses `cast_old`, updates candidate 1, and reuses the old group rather than creating four new records.

- [ ] **Step 3: Add a failing selection test covering historical groups**

Extend `test_select_endpoint_requires_completed_image_and_rejects_siblings` by adding:

```python
historical = {
    **selected,
    "id": "asset_old_selected",
    "candidate_group_id": "cast_old",
    "candidate_index": 1,
    "selection_status": "selected",
}
all_versions = [historical, *siblings]
```

Return `all_versions` from `store.list`, update the side effect to search `all_versions`, and add:

```python
assert statuses["asset_old_selected"] == "rejected"
assert list(statuses.values()).count("selected") == 1
```

- [ ] **Step 4: Run the cross-round selection test and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_select_endpoint_requires_completed_image_and_rejects_siblings -q -p no:cacheprovider --basetemp=backend/data/pytest-casting-history-red-2
```

Expected: FAIL because the current select endpoint only updates siblings whose `candidate_group_id` matches the newly selected group.

- [ ] **Step 5: Make recasting create a new immutable group**

In `cast_character`, replace group and existing-record setup with:

```python
is_recast = bool(source.get("candidate_group_id"))
group_id = f"cast_{uuid.uuid4().hex[:12]}"
siblings = [] if is_recast else [
    item
    for item in store.list(project_id)
    if item.get("candidate_group_id") == group_id and item.get("type") == "character"
]
existing = {
    int(item["candidate_index"]): item
    for item in siblings
    if item.get("candidate_index")
}
if not is_recast:
    existing.setdefault(1, source)
```

This intentionally creates four records for recasts and keeps first-cast compatibility for a legacy source asset.

Import the shared negative prompt:

```python
from app.services.casting import CASTING_NEGATIVE_PROMPT, CastingService
```

Replace the inline `negative` string with:

```python
negative = CASTING_NEGATIVE_PROMPT
```

- [ ] **Step 6: Enforce one selected candidate across same-name history**

In `select_character_candidate`, replace the group-only sibling filter with:

```python
candidate_name = str(candidate.get("name") or "").strip()
for sibling in store.list(project_id):
    if sibling.get("type") != "character":
        continue
    if str(sibling.get("name") or "").strip() != candidate_name:
        continue
    if not sibling.get("candidate_group_id"):
        continue
    status = "selected" if sibling["id"] == asset_id else "rejected"
    updated = store.update(
        project_id,
        sibling["id"],
        selection_status=status,
    )
    if sibling["id"] == asset_id:
        selected = updated
```

Keep the existing completed-image guard and final `selected` return contract unchanged.

- [ ] **Step 7: Run casting tests and verify GREEN**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py -q -p no:cacheprovider --basetemp=backend/data/pytest-casting-history-green
```

Expected: all casting tests PASS, including exactly four new records on recast and exactly one selected same-name candidate after selection.

- [ ] **Step 8: Run the complete backend regression suite**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=backend/data/pytest-real-casting-full
```

Expected: all backend tests PASS with zero failures. Existing dependency deprecation warnings may remain, but no new warning or error is accepted.

- [ ] **Step 9: Commit immutable casting history**

```powershell
git add -- backend/app/api/assets.py backend/tests/test_casting.py
git commit -m "feat: preserve casting round history"
```

### Task 3: Regenerate Su Wan and perform real visual acceptance

**Files:**
- No source-file changes expected.
- Runtime outputs: `D:\ModelHub\outputs\assets\proj_6d3b085b06\*.png`

- [ ] **Step 1: Restart the backend with external output-directory permission**

Stop only the process listening on port `8010`, then start:

```powershell
Start-Process -FilePath 'D:\AI\python3.13.14\python.exe' `
  -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'D:\XiangMu\shipin-agent\backend' `
  -RedirectStandardOutput 'D:\XiangMu\shipin-agent\backend\server-identity-elevated.out.log' `
  -RedirectStandardError 'D:\XiangMu\shipin-agent\backend\server-identity-elevated.err.log' `
  -WindowStyle Hidden
```

Run this outside the workspace sandbox so the worker can write `D:\ModelHub\outputs`. Expected: the API responds at `http://127.0.0.1:8010`.

- [ ] **Step 2: Record the old group and generate a new four-candidate round**

Call:

```powershell
$result = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8010/api/assets/proj_6d3b085b06/characters/asset_c_606e8de9/cast' `
  -ContentType 'application/json' -Body '{}'
$result | ConvertTo-Json -Depth 8
```

Expected: HTTP 200, a `candidate_group_id` different from `cast_2571c3c4061c`, and four new candidate IDs that do not equal the previous four IDs.

- [ ] **Step 3: Poll by condition until all four jobs reach a terminal state**

Query `GET /api/assets/proj_6d3b085b06/assets` every 5 seconds and filter by the returned new group ID. Stop only when the group contains four records and none has `status == "generating"`; do not use a fixed multi-minute sleep.

Expected: all four new candidates have `status == "completed"`, non-empty `image_url`, and `error == null`. If any fails, stop acceptance and report its exact error instead of selecting a candidate.

- [ ] **Step 4: Verify history and prompt payloads through the API**

Assert from the asset list:

```text
old group cast_2571c3c4061c: 4 records still present
new group: 4 new records
new prompts: contain every REQUIRED_REALISM_PHRASES item
new prompts: contain none of BEAUTY_TRIGGER_PHRASES
new negative prompts: contain oily facial highlights, over-sharpening halos, generic influencer face
```

Expected: eight same-name “苏晚” versions are available, with no old file path reused by the new group.

- [ ] **Step 5: Inspect all four new PNGs at full image detail**

Open each new local PNG and assess against the approved criteria:

```text
1. no broad wet or self-luminous forehead, cheek, or nose highlight
2. visible restrained pores and tonal variation without dirty or over-sharpened skin
3. both eyes and facial planes resolved without sharpening halos
4. credible minor asymmetry and four materially different facial structures
5. matched background, exposure, camera distance, covered shoulders, and neutral grooming
```

Record concrete failures per candidate. Do not call the result successful solely because jobs completed.

- [ ] **Step 6: Refresh the existing asset page for user review**

Reload `http://127.0.0.1:5173/workbench/proj_6d3b085b06/assets` and confirm the left-side “苏晚” group shows eight versions and zero generating tasks. Leave the first new candidate selected for comparison; do not click “选定此版长相与气质” on the user's behalf.

- [ ] **Step 7: Final repository and runtime verification**

Run:

```powershell
git diff --check
git status --short
git log -3 --oneline
```

Expected: the two planned implementation commits are present; no planned source file remains uncommitted. Pre-existing tracked bytecode changes, local skill directories, and runtime log files remain untouched and uncommitted.
