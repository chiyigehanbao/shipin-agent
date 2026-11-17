# ============================================
# 开源提示词数据 → RAG 知识库种子脚本
# ============================================
# 数据源（backend/data/prompt_sources/）：
#   1. awesome-seedance2-cases.json   - Seedance 2.0 案例库（71 条）
#   2. ericgood-seedance-prompts.json - Seedance 2.0 提示词集（111 条）
#   3. lanshu-all-prompts.json        - 15 模型 433 条结构化提示词
# 用法：
#   python -m scripts.seed_rag_cases --dry-run
#   python -m scripts.seed_rag_cases            # 真实灌入
#   python -m scripts.seed_rag_cases --embed    # 灌入 + 补向量（需 bge-m3）
# ============================================
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.repositories.rag_cases import RagCaseRepository  # noqa: E402
from app.services.rag_retrieve import get_rag_repo, get_rag_store  # noqa: E402

SOURCES_DIR = ROOT / "data" / "prompt_sources"

# 关键词 → RAG type（前端分类展示用）
_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"portrait|character|avatar|actor|person|face|actor|lead", re.I), "character"),
    (re.compile(r"scene|environment|city|landscape|nature|interior|location|background", re.I), "scene"),
    (re.compile(r"product|prop|object|fashion|car|food|drink|phone|device", re.I), "prop"),
    (re.compile(r"storyboard|shot|sequence|multi|transition|camera", re.I), "storyboard"),
]

_CATEGORY_MAP = {
    "portrait": "character",
    "character": "character",
    "scene": "scene",
    "environment": "scene",
    "product": "prop",
    "prop": "prop",
    "storyboard": "storyboard",
    "camera": "storyboard",
    "motion": "storyboard",
    "cinematic": "technique",
    "sfx": "technique",
    "vfx": "technique",
    "style": "technique",
    "mood": "technique",
    "creative": "technique",
    "sci-fi": "technique",
    "adventure": "technique",
    "action": "technique",
    "documentary": "technique",
    "sports": "technique",
    "corporate": "technique",
    "social": "technique",
    "product": "prop",
}


def _norm_type(category: str | None, title: str, prompt: str) -> str:
    for src in (category or "", title, prompt[:600]):
        low = src.lower()
        for pat, typ in _TYPE_RULES:
            if pat.search(low):
                return typ
        for key, typ in _CATEGORY_MAP.items():
            if key in low:
                return typ
    return "technique"


def _parse_seedance_cases(data: dict) -> list[dict]:
    out = []
    for c in data.get("cases", []):
        prompt = (c.get("prompt") or "").strip()
        if not prompt:
            continue
        title = (c.get("title") or "").strip() or f"Seedance 案例 {c.get('id')}"
        src = (c.get("source") or "").strip()
        tags = list(c.get("category") or []) if isinstance(c.get("category"), list) else []
        cat = tags[0] if tags else c.get("category") or ""
        out.append(
            {
                "title": title,
                "type": _norm_type(cat, title, prompt),
                "style": cat,
                "description": title,
                "tags": [t for t in tags if t],
                "prompt_en": prompt,
                "source_ref": f"awesome-seedance2:{c.get('id')}",
                "source_url": src,
                "rating": 3.5,
            }
        )
    return out


def _parse_ericgood(data: list) -> list[dict]:
    out = []
    for p in data:
        prompt = (p.get("prompt") or "").strip()
        if not prompt:
            continue
        title = (p.get("title_zh") or p.get("title") or "Seedance prompt").strip()
        cat = p.get("category") or p.get("tag") or ""
        tags = [t for t in [cat, p.get("tag_zh") or ""] if t]
        out.append(
            {
                "title": title,
                "type": _norm_type(cat, title, prompt),
                "style": cat,
                "description": (p.get("description_zh") or p.get("description") or "").strip(),
                "tags": tags,
                "prompt_en": prompt,
                "source_ref": f"ericgood-seedance:{p.get('id')}",
                "source_url": p.get("source") or "",
                "rating": 4.0 if p.get("featured") else 3.5,
            }
        )
    return out


def _parse_lanshu(data: dict) -> list[dict]:
    out = []
    for p in data.get("prompts", []):
        prompt = (p.get("prompt") or "").strip()
        if not prompt:
            continue
        title = (p.get("title") or "AI 视频提示词").strip()
        model = p.get("model") or ""
        cat = p.get("category") or ""
        src_info = p.get("source") or {}
        tags = list(p.get("tags") or [])
        if model:
            tags.insert(0, model)
        out.append(
            {
                "title": title,
                "type": _norm_type(cat, title, prompt),
                "style": f"{model} · {cat}" if model else cat,
                "description": title,
                "tags": [t for t in tags if t],
                "prompt_en": prompt,
                "source_ref": f"lanshu:{p.get('id')}",
                "source_url": src_info.get("url") or "",
                "rating": 3.5,
            }
        )
    return out


def collect_cases() -> list[dict]:
    cases: list[dict] = []
    seen: set[str] = set()

    def add(src: dict) -> None:
        ref = src.get("source_ref") or ""
        if ref in seen:
            return
        seen.add(ref)
        cases.append(src)

    files = {
        "awesome-seedance2-cases.json": _parse_seedance_cases,
        "ericgood-seedance-prompts.json": _parse_ericgood,
        "lanshu-all-prompts.json": _parse_lanshu,
    }
    for fname, parser in files.items():
        path = SOURCES_DIR / fname
        if not path.exists():
            print(f"[skip] {fname} 不存在")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cases" in data:
            parsed = parser(data)
        elif isinstance(data, dict):
            parsed = parser(data)
        else:
            parsed = parser(data)
        for c in parsed:
            add(c)
        print(f"[load] {fname}: {len(parsed)} 条")
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="灌入开源提示词到 RAG 知识库")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写入")
    ap.add_argument("--embed", action="store_true", help="灌入后补向量索引（需 bge-m3）")
    args = ap.parse_args()

    cases = collect_cases()
    print(f"\n共收集 {len(cases)} 条提示词")
    from collections import Counter

    print("类型分布:", dict(Counter(c["type"] for c in cases)))

    repo: RagCaseRepository = get_rag_repo()
    store = get_rag_store() if args.embed else None

    if args.dry_run:
        print("\n[dry-run] 未写入任何数据")
        return 0

    existing: set[str] = set()
    try:
        for row in repo.list(limit=100000):
            ref = row.get("source_ref") or ""
            if ref:
                existing.add(ref)
    except Exception:
        pass

    inserted = skipped = 0
    for c in cases:
        ref = c["source_ref"]
        if ref in existing:
            skipped += 1
            continue
        repo.create(
            title=c["title"],
            type=c["type"],
            style=c["style"],
            description=c["description"],
            tags=c["tags"],
            prompt_en=c["prompt_en"],
            negative_prompt="",
            source_project_id=None,
            source_ref=ref,
            rating=c.get("rating", 3.5),
        )
        inserted += 1

    print(f"\n完成：新增 {inserted} 条，跳过已存在 {skipped} 条")

    if args.embed:
        if not store or not store.embedder.available():
            print("[warn] bge-m3 未安装，跳过向量索引（检索暂时用 JSON 回退）")
            return 0
        by_ref: dict[str, dict] = {}
        for row in repo.list(limit=100000):
            ref = row.get("source_ref") or ""
            if ref:
                by_ref[ref] = row
        missing: list[str] = []
        items = []
        for c in cases:
            case = by_ref.get(c["source_ref"])
            if not case:
                missing.append(c["source_ref"])
                continue
            doc = "\n".join(
                p for p in [case.get("title"), case.get("description"), case.get("prompt_en") or ""] if p
            )
            items.append(
                {
                    "case_id": case["id"],
                    "document": doc,
                    "metadata": {"type": case["type"], "title": case["title"]},
                }
            )
        store.upsert_many(items=items)
        if missing:
            print(f"[warn] {len(missing)} 条未在库中找到对应的 case，跳过嵌入")
        print(f"向量索引写入 {len(items)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
