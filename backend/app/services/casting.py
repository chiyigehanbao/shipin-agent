from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from app.services.llm_provider import LLMProvider
from app.services.visual_bible import VisualBibleService


FORBIDDEN_STATE_WORDS = (
    "rain",
    "wet",
    "blood",
    "mud",
    "exhausted",
    "sweat",
    "injury",
)

BEAUTY_TRIGGER_PHRASES = (
    "polished",
    "commercial short-drama actor",
    "pale skin",
    "natural skin",
    "flawless",
    "perfect skin",
    "beauty lighting",
    "soft frontal studio light",
    "harmonious distinctive features",
    "85mm portrait",
    "85mm lens",
)

REFERENCE_BEAUTY_PHRASES = (
    "冷白瓷肌",
    "水光唇",
    "柔焦美颜",
    "强轮廓光",
    "极浅景深",
)

DEMOGRAPHIC_PATTERNS = (
    r"\b(?:early|mid|late)[- ]?\d{2}s\b",
    r"\b\d{1,2}(?:-year-old| years? old)\b",
    (
        r"\b(?:(?:east|south|southeast) asian|chinese|korean|japanese|black|white|"
        r"latina?|middle eastern)?\s*(?:woman|man|female|male|girl|boy)\b"
    ),
    r"\b(?:slight|slim|lean|athletic|average|stocky|broad|petite) build\b",
)

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


class CastingConcept(BaseModel):
    label: str
    identity_anchor: str
    prompt_en: str


_FALLBACKS = (
    (
        "温润克制",
        "softly rectangular oval face, medium cheekbone width, gently broad jaw, "
        "almond eyes with slightly unequal lid height, straight medium-width nose, "
        "full lower lip",
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
        "angular oval face, pronounced jaw corners, low straight brows, "
        "wide-set focused eyes, defined nasal tip, balanced medium lips",
    ),
)


def _clean_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _sanitize_brief(brief: str) -> str:
    text = brief or ""
    for phrase in (*BEAUTY_TRIGGER_PHRASES, *REFERENCE_BEAUTY_PHRASES):
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    for word in FORBIDDEN_STATE_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" |,.;")


def _fallback_context(name: str, brief: str) -> str:
    role_summary = _sanitize_brief((brief or "").split("|", 1)[0])
    demographic_facts: list[str] = []
    seen: set[str] = set()
    for pattern in DEMOGRAPHIC_PATTERNS:
        for match in re.finditer(pattern, brief or "", flags=re.IGNORECASE):
            fact = re.sub(r"\s+", " ", match.group(0)).strip()
            key = fact.lower()
            if key and key not in seen:
                seen.add(key)
                demographic_facts.append(fact)
    parts = [f"Character: {name}"]
    if role_summary:
        parts.append(role_summary)
    if demographic_facts:
        parts.append(", ".join(demographic_facts))
    return ". ".join(parts)


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


def _fallback_concepts(name: str, brief: str) -> list[CastingConcept]:
    context = _fallback_context(name, brief)
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
        if any(phrase in prompt_low for phrase in FORBIDDEN_POSITIVE_PHRASES):
            return False
        if any(
            re.search(rf"\b{re.escape(word)}\b", combined)
            for word in FORBIDDEN_STATE_WORDS
        ):
            return False
    return True


class CastingService:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        visual_bible: VisualBibleService | None = None,
    ) -> None:
        self.llm = llm
        self.visual_bible = visual_bible or VisualBibleService()

    def generate(
        self,
        *,
        name: str,
        brief: str,
        project_id: str = "",
    ) -> list[CastingConcept]:
        bible = self.visual_bible.get(project_id)
        required_phrases = "; ".join(REQUIRED_REALISM_PHRASES)
        forbidden_positive_phrases = "; ".join(FORBIDDEN_POSITIVE_PHRASES)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a casting director preparing unretouched actor comparison "
                    "photographs. Return JSON only as "
                    '{"candidates":[{"label":"Chinese label","identity_anchor":"stable English facial identity","prompt_en":"English Flux portrait prompt"}]}. '
                    "Create exactly four credible working-actor options with clearly different, "
                    "non-idealized permanent facial geometry. Each option must differ in at least "
                    "two of face shape, brow and eye geometry, nose geometry, lip geometry, "
                    "cheekbones, or jaw. Do not create four variants of one generic influencer "
                    "face. Identity anchors contain permanent geometry and age impression only. "
                    f"Every prompt must contain these exact phrases: {required_phrases}. "
                    "Use a stable natural hairstyle, neutral rested expression, a bare face with "
                    "natural dry lips, a plain medium-gray crew-neck cotton top with shoulders covered, "
                    "neutral gray background, and the same camera distance, exposure, light "
                    "position and framing for all four options. Treat any photography, beauty, "
                    "lighting, skin-finish or lens wording already present in the user brief as "
                    "obsolete source material. Never use polished, pale skin, flawless, perfect "
                    "skin, beauty lighting, soft frontal studio light, harmonious distinctive "
                    "features, 85mm portrait or 85mm lens. "
                    f"Never include any of these terms in a positive prompt: "
                    f"{forbidden_positive_phrases}. "
                    "Never encode rain, wetness, blood, mud, "
                    "exhaustion, sweat, injury, plot emotion, weather, wardrobe damage, makeup "
                    "changes or pose changes."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Character: {name}\nBrief: {brief}\n"
                    f"Project casting aesthetic: {bible.casting_aesthetic}\n"
                    f"Identity policy: {'; '.join(bible.identity_policy)}"
                ),
            },
        ]
        try:
            raw, _provider = self.llm.chat(messages)
            payload = _clean_json(raw)
            concepts = [CastingConcept.model_validate(item) for item in payload["candidates"]]
            if _valid(concepts):
                return concepts
        except Exception:
            pass
        return _fallback_concepts(name, brief)
