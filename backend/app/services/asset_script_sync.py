# ============================================
# 从剧本同步角色/场景资产草稿
# ============================================
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

_MAX_ENRICH_WORKERS = 3


def default_aspect(asset_type: str) -> str:
    """角色/场景默认为竖幅（短剧构图），道具默认方形。"""
    return "portrait" if asset_type in ("character", "scene") else "square"


def collect_candidates(scenes: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    char_map: dict[str, dict[str, Any]] = {}
    scene_assets: list[dict[str, Any]] = []
    for sc in scenes:
        loc = (sc.get("location") or "").strip()
        name = (sc.get("name") or "").strip()
        scene_name = loc or name or f"场景{sc.get('number') or len(scene_assets) + 1}"
        desc = (sc.get("description") or "").strip()
        desc_en = (sc.get("description_en") or "").strip()
        summary = desc or desc_en
        scene_assets.append(
            {
                "type": "scene",
                "name": scene_name,
                "seed_cn": summary or scene_name,
                "related_descriptions": [summary] if summary else [],
            }
        )
        for raw in sc.get("characters") or []:
            cname = str(raw).strip()
            if not cname:
                continue
            slot = char_map.setdefault(
                cname,
                {
                    "type": "character",
                    "name": cname,
                    "seed_cn": cname,
                    "related_descriptions": [],
                },
            )
            if summary and summary not in slot["related_descriptions"]:
                slot["related_descriptions"].append(summary)
            slot["related_descriptions"] = slot["related_descriptions"][:3]
    return list(char_map.values()), scene_assets


def fallback_prompts(
    *, name: str, style: str, related: list[str], type: str
) -> dict[str, str]:
    bits = [name]
    if style:
        bits.append(f"{style} style")
    bits.extend(related[:2])
    kind = "character portrait" if type == "character" else "establishing scene"
    cn = "，".join([x for x in [name, style, *related[:2]] if x])
    en = f"{kind}, " + ", ".join(bits)
    avoid = "blurry, low quality, watermark, text"
    if type == "character":
        lock = f"{name}, {style or 'live-action'} character, consistent face and wardrobe"
    else:
        lock = f"{name}, {style or 'live-action'} location, consistent architecture and lighting"
    return {
        "prompt_cn": cn or name,
        "prompt_en": en,
        "negative_prompt": avoid,
        "lock_en": lock,
    }


def _first_sentence(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    for sep in (". ", "。"):
        if sep in raw:
            return (raw.split(sep, 1)[0] + ("." if sep == ". " else "。")).strip()
    return raw


def _lock_en_from(data: dict[str, Any], prompt_en: str) -> str:
    lock = str(data.get("lock_en") or "").strip()
    if lock:
        return lock
    return _first_sentence(prompt_en)


def _enrich_one(
    *,
    polish_svc: Any,
    stage: str,
    name: str,
    style: str,
    related: list[str],
    asset_type: str,
) -> dict[str, str]:
    ctx = {
        "project_style": style,
        "asset_name": name,
        "type": asset_type,
        "scene_summaries": related[:3],
    }
    seed = (
        f"角色名必须保留：{name}。"
        f"这是角色定妆，不是整场戏。风格：{style or '未指定'}。"
        f"场次只作为气质与光线参考：{'；'.join(related[:3])}"
        if asset_type == "character"
        else (
            f"场景名必须保留：{name}。风格：{style or '未指定'}。"
            f"空间参考：{'；'.join(related[:3])}"
        )
    )
    data = polish_svc.polish(
        stage=stage,
        text_cn=seed,
        text_en="",
        context=ctx,
        return_interpretation=False,
    )
    prompt_en = data["prompt_en"]
    return {
        "prompt_cn": data.get("prompt_cn") or seed,
        "prompt_en": prompt_en,
        "negative_prompt": data.get("avoid") or "blurry, low quality",
        "lock_en": _lock_en_from(data, prompt_en),
    }


def sync_from_script(
    *,
    project: dict[str, Any],
    scenes: list[dict[str, Any]],
    store: Any,
    types: tuple[str, ...] = ("character", "scene"),
    enrich: bool = True,
    default_model: str = "flux",
    polish_svc: Any | None = None,
) -> dict[str, Any]:
    if not scenes:
        raise ValueError("no_scenes")
    style = (project.get("style") or "").strip()
    chars, scns = collect_candidates(scenes)
    candidates: list[dict[str, Any]] = []
    if "character" in types:
        candidates.extend(chars)
    if "scene" in types:
        candidates.extend(scns)

    created = updated = skipped = 0
    enrich_fallback = False
    out_assets: list[dict] = []

    def resolve_prompts(cand: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """返回 (prompts, used_fallback)。enrich 失败或不可用时走降级模板。"""
        nonlocal enrich_fallback
        prompts = None
        if enrich and polish_svc is not None:
            try:
                stage = (
                    "character_lock" if cand["type"] == "character" else "scene_lock"
                )
                prompts = _enrich_one(
                    polish_svc=polish_svc,
                    stage=stage,
                    name=cand["name"],
                    style=style,
                    related=cand.get("related_descriptions") or [],
                    asset_type=cand["type"],
                )
            except Exception:
                enrich_fallback = True
                prompts = None
        if prompts is None:
            if enrich:
                enrich_fallback = True
            prompts = fallback_prompts(
                name=cand["name"],
                style=style,
                related=cand.get("related_descriptions") or [],
                type=cand["type"],
            )
        return prompts, prompts is not None

    enrich_candidates = []
    if enrich and polish_svc is not None:
        enrich_candidates = [
            c for c in candidates if c.get("type") in ("character", "scene")
        ]

    prompts_map: dict[tuple[str, str], tuple[dict[str, Any], bool]] = {}
    if enrich_candidates:
        with ThreadPoolExecutor(max_workers=_MAX_ENRICH_WORKERS) as pool:
            futures = {
                pool.submit(resolve_prompts, cand): (cand["type"], cand["name"])
                for cand in enrich_candidates
            }
            from concurrent.futures import as_completed

            for fut in as_completed(futures):
                try:
                    prompts_map[futures[fut]] = fut.result()
                except Exception:
                    enrich_fallback = True

    for cand in candidates:
        existing = store.find_by_name_type(project["id"], cand["type"], cand["name"])
        if existing and existing.get("status") == "completed" and existing.get("image_url"):
            skipped += 1
            out_assets.append(existing)
            continue

        key = (cand["type"], cand["name"])
        if enrich and key in prompts_map:
            prompts, _ = prompts_map[key]
        else:
            prompts = None
            if enrich:
                enrich_fallback = True
            prompts = fallback_prompts(
                name=cand["name"],
                style=style,
                related=cand.get("related_descriptions") or [],
                type=cand["type"],
            )

        if existing:
            asset = store.update(
                project["id"],
                existing["id"],
                prompt_cn=prompts["prompt_cn"],
                prompt_en=prompts["prompt_en"],
                negative_prompt=prompts["negative_prompt"],
                lock_en=prompts.get("lock_en") or "",
                model=default_model,
                aspect=default_aspect(cand["type"]),
                status="pending",
                error=None,
            )
            updated += 1
        else:
            asset = store.create(
                project_id=project["id"],
                name=cand["name"],
                type=cand["type"],
                prompt_cn=prompts["prompt_cn"],
                prompt_en=prompts["prompt_en"],
                model=default_model,
                negative_prompt=prompts["negative_prompt"],
                lock_en=prompts.get("lock_en") or "",
                aspect=default_aspect(cand["type"]),
                status="pending",
            )
            created += 1
        out_assets.append(asset)

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "enrich_fallback": enrich_fallback,
        "assets": out_assets,
    }
