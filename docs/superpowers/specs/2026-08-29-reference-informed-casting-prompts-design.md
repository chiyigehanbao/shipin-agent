# Reference-Informed Casting Portrait Prompt Design

## Status

Approved in conversation on 2026-08-29. This document refines only the portrait-language portion of `2026-08-29-realistic-casting-portrait-prompts-design.md`. The existing casting-round history, candidate selection, identity-lock, and asset-generation behavior remain unchanged.

## Problem

The current casting prompts produce more credible skin texture than the legacy prompts, but the faces are not consistently refined and still show broad glossy regions on the forehead, nose bridge, and cheeks. The user supplied several prompts whose generated portraits have desirable facial refinement, composition, hair detail, material specificity, and photography structure.

Those examples cannot be copied wholesale. They also contain porcelain-skin language, glossy lips, bloom, halation, strong rim light, shallow depth of field, exaggerated body specifications, revealing wardrobe, and scene-specific styling. Those elements would conflict with neutral actor comparison photographs and could reintroduce the oily, over-retouched AI appearance.

## Goal

Use the transferable strengths of the supplied examples to make the four casting candidates look more refined, attractive, and individually recognizable while preserving physically believable skin and a controlled comparison setup.

Success means:

- refined facial proportions without converging on one influencer face;
- clear, individual eye, brow, nose, lip, cheekbone, jaw, and face-shape geometry;
- visible pores, fine facial hair, under-eye texture, nasolabial structure, and mild skin-tone variation;
- no broad glossy patch on the forehead, nose bridge, or cheeks;
- natural dry lip color without lipstick or water-gloss styling;
- separated hair strands and a believable hairline without salon-like shine;
- four candidates photographed with identical framing, distance, exposure, wardrobe, and light placement.

## Scope

### In scope

- restructure the casting prompt into stable semantic sections;
- improve facial refinement and restrained actor presence;
- change the comparison lens description from 50mm to 70mm at f/8;
- refine skin, hair, expression, composition, light, exposure, and capture-texture wording;
- reject LLM output that reintroduces known beauty-retouching or glow triggers;
- extend the casting negative prompt with localized facial-surface failures;
- add automated prompt-contract tests and rerun a four-image visual acceptance round.

### Out of scope

- ancient costume, jewelry, headdress, Dunhuang scenery, dreamcore atmosphere, bedroom styling, or cosplay UI;
- bust-size or revealing-wardrobe instructions;
- changes to casting history, selection, identity storage, or frontend layout;
- changes to ComfyUI sampler, guidance, VAE, denoising, or workflow topology in this iteration.

If this prompt-only iteration still fails the visual acceptance threshold, workflow calibration will remain a separately approved change so that prompt and inference variables are not changed simultaneously.

## Prompt Architecture

The positive prompt uses the following fixed order:

1. **Capture intent** — an unretouched adult actor casting photograph, not a beauty campaign.
2. **Role context** — sanitized role summary plus age, ethnicity, gender, and build only.
3. **Permanent identity** — candidate-specific face, brow, eye, nose, lip, cheekbone, and jaw geometry.
4. **Refined presence** — credible leading-actor refinement, graceful facial planes, attentive eyes, and restrained individual character; attractiveness must not be expressed as a tiny nose, pointed chin, enlarged eyes, perfect symmetry, or generic influencer styling.
5. **Expression and hair** — neutral rested expression, clean natural brows, stable hairstyle, believable hairline, separated strands, and a few flyaways.
6. **Skin and grooming state** — bare face, no foundation, blush, lipstick, or contouring; natural dry lips; pores, fine facial hair, minor blemishes, subtle uneven tone, under-eye texture, and nasolabial structure remain visible.
7. **Surface response** — dry low-reflectance skin, diffuse skin color, gentle tonal falloff, and no concentrated bright patches on the forehead, nose bridge, or cheeks.
8. **Wardrobe and framing** — plain medium-gray crew-neck cotton top, shoulders covered, 3:4 vertical chest-up portrait, complete head and shoulders, centered eye-level camera.
9. **Lens and focus** — 70mm lens at f/8, natural facial perspective, both eyes and all facial planes resolved.
10. **Light and capture** — broad indirect side-above light with white bounce fill, neutral exposure and color response, restrained contrast, subtle fine grain, neutral gray background, and identical comparison conditions.

The identity anchor remains limited to permanent physical geometry and age impression. It must not contain capture, wardrobe, makeup, lighting, pose, weather, emotional state, or scene styling.

## Positive-Prompt Safety Contract

The generated prompt must include exact phrases representing the approved architecture. The validator rejects a response when it:

- omits a required comparison or realism phrase;
- contains legacy beauty triggers;
- contains surface triggers such as `porcelain skin`, `translucent skin`, `glowing skin`, `water-gloss lips`, `wet lips`, `bloom`, `halation`, `beauty filter`, `soft-focus beauty`, `strong rim light`, `extremely shallow depth of field`, `8K`, or `HDR`;
- introduces plot state, weather, injury, dirt, or temporary emotion;
- returns fewer or more than four candidates;
- returns duplicate identity anchors.

Invalid LLM output falls back to the deterministic local prompt builder. The fallback uses the same required phrases and safety contract, so failure does not change the portrait standard.

## Negative Prompt

The negative prompt remains compact and failure-specific. It will cover:

- waxy, plastic, porcelain, wet, or oily skin;
- broad forehead sheen, a white nose-bridge stripe, and glossy cheek patches;
- foundation-covered pores, obvious blush, lipstick, lip gloss, contouring, and beauty filtering;
- excessive symmetry, enlarged eyes, tiny nose, pointed chin, doll face, and generic influencer face;
- over-sharpening halos, HDR microcontrast, glassy eyes, and shallow-focus facial planes;
- cropped head or shoulders, bare shoulders, anatomy errors, text, logos, and watermarks.

Negative terms do not replace clear positive physical instructions. Known gloss-related words remain absent from the positive prompt even when negated.

## Data Flow

1. The casting endpoint receives a character name and legacy brief.
2. The service sanitizes the brief, retaining only role summary and demographic facts.
3. The LLM receives the structured prompt contract and returns exactly four candidates.
4. The validator checks candidate diversity, required phrases, and forbidden triggers.
5. Valid output is used; invalid or unavailable output falls back deterministically.
6. Existing asset APIs create or overwrite images exactly as before.
7. Candidate group, candidate index, selection status, and identity metadata remain unchanged.

## Testing

Automated tests will verify:

- the fallback prompt contains every new structural phrase;
- the prompt uses 70mm at f/8 and 3:4 chest-up comparison framing;
- refined-presence language does not use prohibited stereotyped beauty geometry;
- makeup, gloss, bloom, halation, shallow-depth, 8K, and HDR triggers are absent from positive prompts;
- unsafe LLM output is rejected and replaced by the fallback;
- safe LLM output with four distinct anchors is accepted;
- temporary scene state and legacy photography language remain excluded;
- existing casting history and selection tests continue to pass.

Visual acceptance uses four regenerated candidates for the same character and keeps identity anchors stable. Each original image is inspected at full resolution. A result passes only when the face is refined and individual, both eyes are resolved, hair and skin retain natural microstructure, and the forehead, nose bridge, and cheeks do not contain broad oily-looking reflections.

## Risks and Controls

- **Risk: refined becomes generic beauty.** Control: geometry diversity remains mandatory and stereotyped beauty shortcuts stay forbidden.
- **Risk: more detail creates longer, contradictory prompts.** Control: one ordered prompt builder and exact validation phrases replace ad hoc keyword accumulation.
- **Risk: the model ignores negative prompts at low guidance.** Control: prohibited concepts are removed from the positive prompt; negative terms are secondary protection.
- **Risk: prompt improvements cannot overcome workflow bias.** Control: complete prompt-only visual acceptance before proposing a separate workflow calibration.

