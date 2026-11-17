# MiniMax I2V Motion Pack v1

The **first frame already shows identity**. Write motion-only language for ~4–6 seconds (MiniMax I2V). Do not re-describe face, hair, wardrobe, or architecture.

## Formula
**One visible action with an endpoint + one camera move (or locked-off) + preserve constraint**

Pattern:
`[Who] [does one concrete action ending in a clear state]. Camera: [one move or locked-off]. About Ns. Keep identity, face, hair, and wardrobe unchanged from the first frame.`

## Rules
- One verb chain per named person; no simultaneous large actions across people
- Prefer: turn, step, look, lower/raise an object, breathe/settle, push door, walk into midground
- Camera pick one: locked-off / slow push-in / gentle pan / slight tilt / follow at constant distance
- Timing: state About 5s (or the frame duration if provided)
- Always end with the preserve sentence above (or equivalent)
- No appearance essay, no clothing list, no location rebuild
- No masterpiece / 8K / cinematic masterpiece / ultra detailed

## avoid
`identity drift, face morph, wardrobe change, extra limbs, teleport, whip-pan spam, sudden cut, text overlay`

Output JSON only:
{"motion_prompt_en":"...","avoid":"identity drift, face morph, wardrobe change, extra limbs, teleport, whip-pan spam"}

Example:
{"motion_prompt_en":"She turns her head toward the stairwell, pauses, then takes one slow step forward. Camera: gentle push-in from chest-up. About 5s. Keep identity, face, hair, and wardrobe unchanged from the first frame.","avoid":"identity drift, face morph, wardrobe change, extra limbs, teleport, whip-pan spam"}
