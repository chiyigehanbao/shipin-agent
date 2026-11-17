# Attribution

Cinematic still workflow is originally inspired by
「造梦师：AI时代电影视觉指南」/ zy-cinematic-realism
(https://github.com/popopo-99/zy-cinematic-realism), licensed CC BY-NC 4.0.
This repository ships rewritten packs and does not redistribute that skill verbatim.

Character-lock, single-action, single-camera, and anti-filler rules are adapted from
Seedance 2.0 (https://github.com/Emily2040/seedance-2.0), MIT License,
Copyright (c) 2026 Iamemily2050. Runtime packs are rewritten for MiniMax I2V
and do not copy Seedance platform/API instructions.

## Craft refresh (2026-08-17)

Prompt ordering, natural-language Flux style, and camera/film-stock phrasing
were distilled from public prompting guides (rewritten; no long examples copied):

- Black Forest Labs — FLUX.2 Prompting Guide
  https://docs.bfl.ml/guides/prompting_guide_flux2
  (Subject + Action + Style + Context; early-token priority; camera/film descriptors)
- Community Flux character consistency notes
  https://artificial-intelligence-wiki.com/prompt-engineering/image-generation-prompts/flux-character-prompts/
  (repeat identity descriptors verbatim across shots)
- SDXL natural-language / photographic prompting practices
  https://neurocanvas.net/blog/sdxl-best-practices-guide/
  (sentence prompts over tag soup; lens/lighting language; lean negatives)

## MiniMax H3 prompt-writing guide (2026-08-28)

The H3 compiler vendors three files byte-for-byte from the official MiniMax-H3
repository for runtime prompt compilation and provenance:

- Repository: https://github.com/MiniMax-AI/MiniMax-H3
- Commit: `d21241f0a4b3acbb34c97dae47fa417b7065e438`
- Paths: `skills/h3-prompt-writing/SKILL.md`, `references/base-en.txt`,
  and `references/ref-en.txt`

At the pinned commit, no top-level LICENSE, COPYING, or NOTICE file was present.
The vendored files must not be described as original VisionForge content, and
upstream terms should be re-checked before redistribution. Exact hashes and the
copy record are in `h3_prompt_writing_d21241f/SOURCE.md`.
