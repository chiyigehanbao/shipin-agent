# Reference-Informed Casting Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make neutral casting portraits more refined and individually attractive by absorbing the useful facial, hair, composition, and photography structure from the user's reference prompts without reintroducing glossy skin, beauty filtering, or scene styling.

**Architecture:** Keep the existing `CastingService` and deterministic fallback. Replace the current prompt contract with one ordered actor-comparison grammar, validate all LLM output against the same required and forbidden phrases, and keep the negative prompt focused on observed local facial failures. Casting history, identity metadata, API behavior, and frontend behavior do not change.

**Tech Stack:** Python 3.13, Pydantic, FastAPI, pytest, local Flux through ComfyUI, SQLite-backed asset store.

---

## File Map

- Modify `backend/app/services/casting.py`: required prompt phrases, fallback prompt builder, forbidden reference-style triggers, LLM instructions, and casting negative prompt.
- Modify `backend/tests/test_casting.py`: prompt-contract, fallback, unsafe-LLM, brief-sanitization, and negative-prompt regression coverage.
- No new production module is needed; the behavior remains one cohesive responsibility inside the existing casting service.

### Task 1: Build the Reference-Informed Actor Comparison Grammar

**Files:**
- Modify: `backend/tests/test_casting.py`
- Modify: `backend/app/services/casting.py`

- [ ] **Step 1: Write the failing structure test**

Replace the test helper with the desired contract and add a focused fallback test:

```python
REFERENCE_STRUCTURE_PHRASES = (
    "credible refined leading-actor presence with individual facial character",
    "clean natural brows and attentive eyes",
    "believable hairline, separated hair strands and a few flyaways",
    "faint natural under-eye texture and nasolabial structure",
    "continuous diffuse tonal response across forehead, nose bridge and cheeks",
    "3:4 vertical chest-up actor comparison portrait",
    "complete head and shoulders",
    "70mm lens at f/8",
    "natural facial perspective",
    "broad indirect daylight from above and to one side",
    "white bounce fill",
    "subtle fine photographic grain",
)


def realistic_prompt(anchor: str) -> str:
    return (
        "unretouched adult actor casting photograph, "
        f"permanent facial identity: {anchor}, believable age, "
        "credible refined leading-actor presence with individual facial character, "
        "graceful facial planes, clean natural brows and attentive eyes, "
        "stable natural hairstyle, believable hairline, separated hair strands and a few flyaways, "
        "neutral rested expression, matte skin response, visible natural pores and fine facial texture, "
        "subtle uneven skin tone, minor facial asymmetry, "
        "faint natural under-eye texture and nasolabial structure, "
        "bare-faced with naturally pigmented dry lips, visible fine facial hair and a few faint blemishes, "
        "dry low-reflectance skin surface, diffuse skin color with gentle tonal falloff, "
        "continuous diffuse tonal response across forehead, nose bridge and cheeks, "
        "plain medium-gray crew-neck cotton top with shoulders covered, "
        "3:4 vertical chest-up actor comparison portrait, complete head and shoulders, "
        "centered eye-level camera, 70mm lens at f/8, natural facial perspective, "
        "both eyes and all facial planes equally resolved, "
        "broad indirect daylight from above and to one side, white bounce fill, "
        "neutral gray background, normal exposure, neutral color response, restrained contrast, "
        "subtle fine photographic grain, "
        "identical camera distance, exposure, light placement and comparison framing"
    )


def test_fallback_uses_reference_informed_actor_comparison_structure():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief="凛冽冷艳 | mid-20s East Asian woman, slight build",
    )

    assert len(concepts) == 4
    for concept in concepts:
        prompt = concept.prompt_en.lower()
        assert all(phrase.lower() in prompt for phrase in REFERENCE_STRUCTURE_PHRASES)
        assert "50mm lens" not in prompt
        assert "large diffused key light" not in prompt
```

In `test_casting_service_accepts_four_distinct_unretouched_candidates`, replace the two affected assertions with:

```python
assert all("unretouched adult actor casting photograph" in c.prompt_en for c in concepts)
assert all("70mm lens at f/8" in c.prompt_en for c in concepts)
```

Replace `test_fallback_positive_prompt_uses_only_dry_diffuse_skin_language` with:

```python
def test_fallback_positive_prompt_keeps_skin_dry_diffuse_and_facial_detail_visible():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief="凛冽冷艳 | mid-20s East Asian woman, slight build",
    )

    for concept in concepts:
        prompt = concept.prompt_en.lower()
        assert "bare-faced with naturally pigmented dry lips" in prompt
        assert "dry low-reflectance skin surface" in prompt
        assert "diffuse skin color with gentle tonal falloff" in prompt
        assert "faint natural under-eye texture and nasolabial structure" in prompt
        assert "specular" not in prompt
        assert "highlight" not in prompt
        assert "glow" not in prompt
        assert "grooming" not in prompt
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_fallback_uses_reference_informed_actor_comparison_structure -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-structure-red
```

Expected: FAIL because the fallback still uses `50mm lens at f/8`, the former light description, and lacks the new reference-informed phrases.

- [ ] **Step 3: Implement the ordered fallback grammar**

In `backend/app/services/casting.py`, replace `REQUIRED_REALISM_PHRASES` with:

```python
REQUIRED_REALISM_PHRASES = (
    "unretouched adult actor casting photograph",
    "credible refined leading-actor presence with individual facial character",
    "clean natural brows and attentive eyes",
    "believable hairline, separated hair strands and a few flyaways",
    "matte skin response",
    "visible natural pores and fine facial texture",
    "subtle uneven skin tone",
    "minor facial asymmetry",
    "faint natural under-eye texture and nasolabial structure",
    "bare-faced with naturally pigmented dry lips",
    "dry low-reflectance skin surface",
    "diffuse skin color with gentle tonal falloff",
    "continuous diffuse tonal response across forehead, nose bridge and cheeks",
    "3:4 vertical chest-up actor comparison portrait",
    "complete head and shoulders",
    "70mm lens at f/8",
    "natural facial perspective",
    "both eyes and all facial planes equally resolved",
    "broad indirect daylight from above and to one side",
    "white bounce fill",
    "subtle fine photographic grain",
    "identical camera distance, exposure, light placement and comparison framing",
)
```

Replace `_realistic_prompt` with:

```python
def _realistic_prompt(*, context: str, anchor: str) -> str:
    role_context = f"Role context: {context}, " if context else ""
    return (
        "unretouched adult actor casting photograph, "
        f"{role_context}permanent facial identity: {anchor}, believable age, "
        "credible refined leading-actor presence with individual facial character, "
        "graceful facial planes, clean natural brows and attentive eyes, "
        "stable natural hairstyle, believable hairline, separated hair strands and a few flyaways, "
        "neutral rested expression, matte skin response, visible natural pores and fine facial texture, "
        "subtle uneven skin tone, minor facial asymmetry, "
        "faint natural under-eye texture and nasolabial structure, "
        "bare-faced with naturally pigmented dry lips, visible fine facial hair and a few faint blemishes, "
        "dry low-reflectance skin surface, diffuse skin color with gentle tonal falloff, "
        "continuous diffuse tonal response across forehead, nose bridge and cheeks, "
        "plain medium-gray crew-neck cotton top with shoulders covered, "
        "3:4 vertical chest-up actor comparison portrait, complete head and shoulders, "
        "centered eye-level camera, 70mm lens at f/8, natural facial perspective, "
        "both eyes and all facial planes equally resolved, "
        "broad indirect daylight from above and to one side, white bounce fill, "
        "neutral gray background, normal exposure, neutral color response, restrained contrast, "
        "subtle fine photographic grain, "
        "identical camera distance, exposure, light placement and comparison framing"
    )
```

- [ ] **Step 4: Run the casting tests and verify GREEN**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-structure-green
```

Expected: all casting tests PASS with the reference-informed helper and fallback assertions shown above.

- [ ] **Step 5: Commit the grammar**

```powershell
git add -- backend/app/services/casting.py backend/tests/test_casting.py
git commit -m "feat: refine actor casting prompt structure"
```

### Task 2: Reject Beauty and Glow Triggers from the Supplied Examples

**Files:**
- Modify: `backend/tests/test_casting.py`
- Modify: `backend/app/services/casting.py`

- [ ] **Step 1: Write failing unsafe-reference tests**

Add these tests:

```python
@pytest.mark.parametrize(
    "trigger",
    [
        "porcelain skin",
        "translucent skin",
        "water-gloss lips",
        "wet lips",
        "bloom",
        "halation",
        "beauty filter",
        "soft-focus beauty",
        "strong rim light",
        "extremely shallow depth of field",
        "8K",
        "HDR",
    ],
)
def test_casting_service_rejects_reference_style_surface_triggers(trigger):
    candidates = [
        {
            "label": f"污染方案{i}",
            "identity_anchor": f"distinct permanent facial geometry {i}",
            "prompt_en": f"{realistic_prompt(f'distinct permanent facial geometry {i}')}, {trigger}",
        }
        for i in range(1, 5)
    ]

    concepts = CastingService(
        llm=FakeLLM(json.dumps({"candidates": candidates}))
    ).generate(name="苏晚", brief="女主")

    assert all(item.label != "污染方案1" for item in concepts)
    assert all(trigger.lower() not in item.prompt_en.lower() for item in concepts)


def test_fallback_sanitizes_chinese_reference_beauty_language():
    concepts = CastingService(llm=FakeLLM("not json")).generate(
        name="苏晚",
        brief="清冷女主 冷白瓷肌 水光唇 柔焦美颜 强轮廓光 极浅景深 | mid-20s East Asian woman",
    )
    combined = " ".join(item.prompt_en.lower() for item in concepts)

    assert "冷白瓷肌" not in combined
    assert "水光唇" not in combined
    assert "柔焦美颜" not in combined
    assert "强轮廓光" not in combined
    assert "极浅景深" not in combined
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_casting_service_rejects_reference_style_surface_triggers backend/tests/test_casting.py::test_fallback_sanitizes_chinese_reference_beauty_language -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-filter-red
```

Expected: FAIL for triggers not currently rejected and for Chinese beauty language still present in role context.

- [ ] **Step 3: Add the trigger contract and brief sanitation**

In `backend/app/services/casting.py`, replace `FORBIDDEN_POSITIVE_SURFACE_WORDS` with:

```python
FORBIDDEN_POSITIVE_PHRASES = (
    "specular",
    "highlight",
    "glow",
    "grooming",
    "porcelain skin",
    "translucent skin",
    "water-gloss lips",
    "wet lips",
    "bloom",
    "halation",
    "beauty filter",
    "soft-focus beauty",
    "strong rim light",
    "extremely shallow depth of field",
    "8k",
    "hdr",
)

REFERENCE_BEAUTY_PHRASES = (
    "冷白瓷肌",
    "水光唇",
    "柔焦美颜",
    "强轮廓光",
    "极浅景深",
)
```

Update `_sanitize_brief` so both legacy and supplied-reference beauty phrases are removed:

```python
def _sanitize_brief(brief: str) -> str:
    text = brief or ""
    for phrase in (*BEAUTY_TRIGGER_PHRASES, *REFERENCE_BEAUTY_PHRASES):
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    for word in FORBIDDEN_STATE_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" |,.;")
```

In `_valid`, replace the former surface-word check with:

```python
if any(phrase in prompt_low for phrase in FORBIDDEN_POSITIVE_PHRASES):
    return False
```

At the start of `CastingService.generate`, build both instruction lists:

```python
required_phrases = "; ".join(REQUIRED_REALISM_PHRASES)
forbidden_positive_phrases = "; ".join(FORBIDDEN_POSITIVE_PHRASES)
```

Replace the existing beauty/surface sentence in the system message with:

```python
"Treat any photography, beauty, lighting, skin-finish or lens wording already "
"present in the user brief as obsolete source material. "
"Never use polished, pale skin, flawless, perfect skin, beauty lighting, soft "
"frontal studio light, harmonious distinctive features, 85mm portrait or 85mm lens. "
f"Never include any of these terms in a positive prompt: {forbidden_positive_phrases}. "
```

Do not put forbidden concepts into `_realistic_prompt`, even in a negated sentence.

- [ ] **Step 4: Run the casting tests and verify GREEN**

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-filter-green
```

Expected: all casting tests PASS.

- [ ] **Step 5: Commit the safety contract**

```powershell
git add -- backend/app/services/casting.py backend/tests/test_casting.py
git commit -m "fix: reject beauty artifacts in casting prompts"
```

### Task 3: Target the Observed Local Facial Failures

**Files:**
- Modify: `backend/tests/test_casting.py`
- Modify: `backend/app/services/casting.py`

- [ ] **Step 1: Write the failing negative-prompt test**

Import `CASTING_NEGATIVE_PROMPT` and add:

```python
def test_casting_negative_prompt_targets_observed_face_failures():
    negative = CASTING_NEGATIVE_PROMPT.lower()
    required = (
        "broad forehead sheen",
        "white nose bridge stripe",
        "glossy cheek patches",
        "foundation-covered pores",
        "obvious blush",
        "lipstick",
        "lip gloss",
        "facial contouring",
        "perfect facial symmetry",
        "cropped head",
        "cropped shoulders",
    )

    assert all(phrase in negative for phrase in required)
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py::test_casting_negative_prompt_targets_observed_face_failures -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-negative-red
```

Expected: FAIL because the current negative prompt lacks the localized forehead, nose, cheek, makeup, symmetry, and crop failures.

- [ ] **Step 3: Extend only the shared casting negative prompt**

Replace `CASTING_NEGATIVE_PROMPT` with:

```python
CASTING_NEGATIVE_PROMPT = (
    "waxy skin, plastic skin, porcelain skin, wet glossy skin, oily facial highlights, "
    "facial glow, broad forehead sheen, white nose bridge stripe, glossy cheek patches, "
    "foundation-covered pores, beauty retouching, skin smoothing, airbrushed skin, "
    "obvious blush, lipstick, lip gloss, facial contouring, heavy makeup, "
    "over-sharpening halos, HDR microcontrast, excessive clarity, glassy eyes, "
    "perfect facial symmetry, enlarged eyes, tiny nose, pointed chin, "
    "generic influencer face, doll face, shallow depth of field, one eye out of focus, "
    "cropped head, cropped shoulders, bare shoulders, lingerie straps, "
    "bad anatomy, text, logo, watermark"
)
```

- [ ] **Step 4: Run the casting tests and verify GREEN**

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests/test_casting.py -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-negative-green
```

Expected: all casting tests PASS.

- [ ] **Step 5: Commit the localized failure controls**

```powershell
git add -- backend/app/services/casting.py backend/tests/test_casting.py
git commit -m "fix: target casting portrait surface failures"
```

### Task 4: Full Regression and Real Four-Image Acceptance

**Files:**
- Verify: `backend/app/services/casting.py`
- Verify: `backend/tests/test_casting.py`
- Runtime images: `D:\ModelHub\outputs\assets\proj_6d3b085b06\asset_c_a3d743d2.png`
- Runtime images: `D:\ModelHub\outputs\assets\proj_6d3b085b06\asset_c_311d5865.png`
- Runtime images: `D:\ModelHub\outputs\assets\proj_6d3b085b06\asset_c_f537134d.png`
- Runtime images: `D:\ModelHub\outputs\assets\proj_6d3b085b06\asset_c_6640b959.png`

- [ ] **Step 1: Run the full backend suite**

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-full
```

Expected: all tests PASS; existing framework deprecation warnings may remain unchanged.

- [ ] **Step 2: Restart the worktree backend against the real project database**

Stop only the process currently listening on port 8010:

```powershell
$listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  Stop-Process -Id $listener.OwningProcess
}
```

Then run:

```powershell
$env:SQLITE_PATH='D:\XiangMu\shipin-agent\backend\data\shipin-agent.db'
Start-Process -FilePath 'D:\AI\python3.13.14\python.exe' `
  -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8010','--env-file','D:\XiangMu\shipin-agent\backend\.env' `
  -WorkingDirectory 'D:\XiangMu\shipin-agent\.worktrees\realistic-casting-prompts\backend' `
  -WindowStyle Hidden `
  -RedirectStandardOutput 'D:\XiangMu\shipin-agent\.worktrees\realistic-casting-prompts\backend\data\uvicorn-reference-casting.out.log' `
  -RedirectStandardError 'D:\XiangMu\shipin-agent\.worktrees\realistic-casting-prompts\backend\data\uvicorn-reference-casting.err.log'
```

Verify:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8010/' -TimeoutSec 10
```

Expected: `status` is `ok`.

- [ ] **Step 3: Overwrite the same four candidate assets**

Generate the exact fallback payload from production code and POST it over the existing four assets:

```powershell
$env:PYTHONIOENCODING='utf-8'
$conceptJson = & 'D:\AI\python3.13.14\python.exe' -c "import json; from app.services.casting import _fallback_concepts, CASTING_NEGATIVE_PROMPT; print(json.dumps({'concepts':[item.model_dump() for item in _fallback_concepts('苏晚','凛冽冷艳 | mid-20s, East Asian woman, slight build')], 'negative':CASTING_NEGATIVE_PROMPT}, ensure_ascii=False))"
$payload = $conceptJson | ConvertFrom-Json
$assetIds = @(
  'asset_c_a3d743d2',
  'asset_c_311d5865',
  'asset_c_f537134d',
  'asset_c_6640b959'
)

for ($index = 0; $index -lt 4; $index++) {
  $concept = $payload.concepts[$index]
  $body = @{
    name = '苏晚'
    type = 'character'
    prompt_cn = $concept.label
    prompt_en = $concept.prompt_en
    model = 'flux'
    negative_prompt = $payload.negative
    lock_en = $concept.identity_anchor
    asset_id = $assetIds[$index]
    aspect = 'portrait'
  } | ConvertTo-Json -Depth 4

  Invoke-RestMethod `
    -Uri 'http://127.0.0.1:8010/api/assets/proj_6d3b085b06/generate' `
    -Method Post `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($body))
}
```

Run this command from `D:\XiangMu\shipin-agent\.worktrees\realistic-casting-prompts\backend`. It preserves candidate group `cast_b97f91d8af5b`, does not create another history round, and does not select a candidate for the user.

- [ ] **Step 4: Poll until all four complete**

```powershell
$data = Invoke-RestMethod -Uri 'http://127.0.0.1:8010/api/assets/proj_6d3b085b06/assets'
$data | Where-Object { $_.candidate_group_id -eq 'cast_b97f91d8af5b' } |
  Sort-Object candidate_index |
  Select-Object id,candidate_index,status,error
```

Expected: all four rows report `completed` with empty errors.

- [ ] **Step 5: Inspect all four originals**

Open each runtime image at original detail. Check:

- forehead, nose bridge, and cheeks have no broad oily reflection;
- facial geometry is refined but differs across all four candidates;
- both eyes and facial planes are resolved;
- pores, under-eye structure, hairline, separated strands, and mild asymmetry remain visible;
- lips are naturally pigmented and not styled as glossy lipstick;
- head, shoulders, and gray crew-neck wardrobe are not cropped.

If the set fails only because surface gloss persists, stop the prompt iteration and report that prompt-only control has reached its limit. Do not change sampler, guidance, VAE, denoising, or workflow topology without separate approval.

- [ ] **Step 6: Refresh the asset page and confirm persisted prompt text**

Open `http://127.0.0.1:5173/workbench/proj_6d3b085b06/assets`, refresh the asset list, and confirm the selected display shows the new 70mm actor-comparison prompt and the expanded negative prompt. Do not click “选定此版长相与气质”.

### Task 5: Final Verification and Branch Handoff

**Files:**
- Verify: `backend/app/services/casting.py`
- Verify: `backend/tests/test_casting.py`
- Verify: `docs/superpowers/specs/2026-08-29-reference-informed-casting-prompts-design.md`
- Verify: `docs/superpowers/plans/2026-08-29-reference-informed-casting-prompts.md`

- [ ] **Step 1: Run final automated verification**

```powershell
D:\AI\python3.13.14\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=backend/data/pytest-reference-final
git diff --check -- backend/app/services/casting.py backend/tests/test_casting.py docs/superpowers/specs/2026-08-29-reference-informed-casting-prompts-design.md docs/superpowers/plans/2026-08-29-reference-informed-casting-prompts.md
```

Expected: all tests PASS and `git diff --check` emits no errors.

- [ ] **Step 2: Confirm only intended tracked changes remain**

```powershell
git status --short -- backend/app/services/casting.py backend/tests/test_casting.py docs/superpowers/specs/2026-08-29-reference-informed-casting-prompts-design.md docs/superpowers/plans/2026-08-29-reference-informed-casting-prompts.md
git log --oneline -8
```

Expected: no uncommitted production or test changes; the design, plan, and implementation commits are present.

- [ ] **Step 3: Use the branch-finishing workflow**

Invoke `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`. Present the verified test count, visual acceptance result, running preview URL, branch name `codex/realistic-casting-prompts`, and integration options. Preserve unrelated main-worktree changes and runtime logs.
