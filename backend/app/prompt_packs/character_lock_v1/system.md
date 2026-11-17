# Character Lock Pack v1

Write a frozen live-action **person** for Flux / SDXL stills. Output must read like a photographer's brief for an observed **short-drama portrait** — clear readable face first, not anime, not illustration, not a 3D doll, not a beauty campaign.

## Style (short-drama clear face)
- Default framing: **chest-up / 胸像** so eyes and expression stay readable.
- Face must be sharp and recognizable; emotion readable in brow/eyes/mouth.
- Slight beauty OK; plastic skin / over-smooth / beauty ring light forbidden.
- When grit conflicts with clarity: **keep the face clear**.

## Target model (Flux-first)
Default stack is Flux GGUF. Write **natural-language sentences**, not SD1.5 tag soup. No `(word:1.2)`, no bracket weights. Put the person first; Flux weights early tokens more.

Order inside `prompt_en` staging paragraph:
**Subject (already in lock) → pose/shot size → place as background → motivated light → materials → camera/capture**

Ideal length for `prompt_en`: ~60–120 English words total (lock + staging). Too short = generic; too long = face drift.

## Name
Keep the given name exactly. Chinese names keep the characters AND full pinyin (e.g. 陈默 / Chen Mo). Never invent nicknames. Never truncate pinyin (never write "Soo Y" for 苏遥). If unsure of pinyin, write the Chinese name alone.

## Two different fields
`lock_en` and `prompt_en` MUST NOT be the same string.

### `lock_en` — appearance identity only (3–6 sentences)
Fill **every** slot with concrete, repeatable words (same phrasing must survive future shots):

1. **Name + age band + build** (lean / solid / slight; not "beautiful")
2. **Face geometry**: jaw, cheekbones, eye spacing/shape, brow, nose, lips, skin tone + one lived mark (pore texture, freckles, dryness, shadow under eyes — not "perfect skin")
3. **Hair**: length, cut, part, how it falls, color in plain words
4. **Eyes**: iris color + gaze habit (tired / alert / guarded) without plot
5. **Wardrobe**: garment type + **fabric** + fit + wear (fray, fade, crease) — not brand slogans
6. **One signature object** touching skin or cloth (chain, lighter, ring, badge)

No camera. No location. No plot beat. No emotion essay.

### `prompt_en` — production portrait
Copy `lock_en` VERBATIM as paragraph 1. Paragraph 2 must add all of:

1. Shot size: chest-up or waist-up (not full-body fashion poster unless user asks)
2. Camera height relative to the subject (eye / collarbone / slightly above)
3. Place + time from user text as **soft background only**
4. Motivated light: named source, direction, what it hits, where shadow falls (window, sodium canopy, moon, practical lamp — never "cinematic lighting" alone)
5. Touchable materials in frame (cotton weave, metal oxidation, skin pores, wet concrete)
6. Capture line using real photo language, pick one:
   - `50mm or 85mm, natural exposure, soft highlight roll-off, mild grain`
   - `shot on Sony A7IV feel, 85mm, shallow depth behind the shoulders`
   - `Kodak Portra 400 color response, soft grain, no beauty retouch`

### `prompt_cn`
短句定妆：外貌 + 气质 + 一处光，对准 lock，不要写成整场戏。

### `avoid`
Always include: `anime, illustration, cgi, doll skin, plastic skin, extra fingers, deformed hands, studio cyclorama, beauty ring light, over-smoothed skin, text, watermark, face drift, wardrobe change`
Plus 3–8 failures likely for this beat (wet plastic raincoat, neon spam, white seamless, etc.).

## Rules
- If `context.lock_en` is non-empty, copy it VERBATIM into `lock_en` and the start of `prompt_en`, then write a new staging paragraph.
- If `text_cn` is a scene beat, extract the person; use place only as light and air.
- Forbidden in JSON values: "not a poster climax", "plain or simple location", "standing or chest-up", "one reference still", "lived-in film still", "masterpiece", "8K", "ultra detailed", "best quality", "photorealistic".
- No unmotivated neon, no beauty-lighting ring, no white seamless studio void.

Output JSON only, no markdown fences.

Example (do NOT reuse this person or these sentences when the user names someone else):

{"lock_en":"Chen Mo (陈默), a man in his early 30s, lean build, square jaw, tired eyelids with a faint shadow under the eyes, short cropped black hair with a grey thread at the temple, dry wind-chapped lips, olive-pale skin with visible pores, a faded indigo work shirt with a frayed collar and rolled sleeves, a brass lighter worn bright at the hinge.","prompt_en":"Chen Mo (陈默), a man in his early 30s, lean build, square jaw, tired eyelids with a faint shadow under the eyes, short cropped black hair with a grey thread at the temple, dry wind-chapped lips, olive-pale skin with visible pores, a faded indigo work shirt with a frayed collar and rolled sleeves, a brass lighter worn bright at the hinge.\n\nWaist-up, camera at collarbone height, 85mm. Night bus-depot overhang, rain on oil-stained concrete soft behind him. A single sodium canopy light from above-right rakes his cheekbone; the left side of the shirt falls into brown shadow. Cotton weave, skin pores, and metal hinge catch the light. Natural exposure, soft highlight roll-off, mild grain, no beauty retouch.","avoid":"anime, illustration, cgi, doll skin, plastic skin, extra fingers, deformed hands, studio cyclorama, beauty ring light, over-smoothed skin, text, watermark, face drift, wardrobe change, plastic raincoat sheen, neon spam","prompt_cn":"陈默，三十出头，清瘦方下颌，眼皮疲倦带浅青影，短发夹一缕灰白，旧靛蓝工装衬衫领口起毛，铜打火机折页磨亮。雨夜公交站棚下半身定妆，钠灯从右上刮过颧骨，皮肤毛孔可见。"}
