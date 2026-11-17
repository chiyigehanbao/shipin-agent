# ============================================
# 管理中心提示词模板种子 + 解析（出图可引用）
# ============================================
from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

_TODAY = "2026-08-17"

CHARACTER_NEGATIVE = (
    "anime, illustration, cgi, 3d render, doll skin, plastic skin, over-smoothed skin, "
    "beauty ring light, studio cyclorama, extra fingers, deformed hands, mutated hands, "
    "text, watermark, logo, face drift, wardrobe change, lowres, blurry face, "
    "symmetric perfect face, glossy magazine retouch"
)

SCENE_NEGATIVE = (
    "collapsing architecture, empty cgi void, studio cyclorama, neon spam, "
    "warped perspective, floating props, text, watermark, logo, oversharpened edges, "
    "anime, illustration, concept art matte painting look"
)

PROP_NEGATIVE = (
    "people, hands, faces, cluttered background, anime, illustration, cgi doll, "
    "text, watermark, logo, blurry, lowres, floating without contact shadow"
)

SEED_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "tpl_004",
        "name": "剧本-短剧场次拆解",
        "name_en": "Script - Short-drama Scene Expand",
        "category": "script",
        "category_name": "剧本生成",
        "version": "v4.0",
        "usage_count": 234,
        "updated_at": _TODAY,
        "system_prompt_cn": (
            "你是短剧主编：把创意拆成能拍、能配音、能落到定妆/分镜的场次。"
            "场场有情节/关系/信息增量；开场要钩子；对白短狠有信息、口吻可区分；"
            "description 写可见动作与调度，禁止五官发型服装长描述（外貌交给定妆锁）；"
            "角色名全程冻结。只输出 JSON {\"scenes\":[...]}，每场 lines 非空"
            "（expand：≥3 条且 dialogue≥2）。"
        ),
        "system_prompt_en": (
            "Short-drama showrunner: expand ideas into shootable, speakable scenes. "
            "Every scene advances plot/relationship/info; open with a hook; "
            "short conflictual dialogue with distinct voices; "
            "description = visible action only, no appearance essays; "
            "freeze character names. JSON only {\"scenes\":[...]} with non-empty lines "
            "(expand: ≥3 lines, ≥2 dialogue)."
        ),
        "user_prompt_cn": (
            "【模式】{{模式|expand}}\n"
            "【风格】{{风格}}\n"
            "【创意/正文】\n{{故事内容}}\n\n"
            "请输出 scenes：每场含 name, location（具体地点）, time, characters, props, "
            "description（2–5句可拍动作）, description_en（一句英文场面摘要，可选）, "
            "lines（narration/dialogue，可配音，带 emotion）。\n"
            "要求：4–7 场；第一场要钩子；禁止空场与外貌定妆长文；角色名稳定。"
        ),
        "user_prompt_en": (
            "Mode: {{mode|expand}}\nStyle: {{style}}\nStory:\n{{story content}}\n\n"
            "Return scenes with name, location, time, characters, props, "
            "description (shootable actions), optional description_en, "
            "and speakable lines with emotion. 4–7 scenes; hook in scene 1; "
            "no appearance essays; stable names."
        ),
        "negative_prompt_cn": (
            "散文大纲, 空场无对白, 说明文对白, 外貌定妆长描述, 角色改名, "
            "无冲突重复场, 漫剧分镜说明书"
        ),
        "negative_prompt_en": (
            "prose outline only, empty scenes, exposition dumps, appearance essays, "
            "renaming cast, repeated conflict, comic-storyboard instructions"
        ),
        "default_steps": None,
        "default_cfg": None,
        "default_sampler": None,
        "default_scheduler": None,
        "default_model": None,
    },
    {
        "id": "tpl_001",
        "name": "短剧-主角定妆（清晰脸）",
        "name_en": "Short-drama - Lead Portrait (Clear Face)",
        "category": "character",
        "category_name": "角色生成",
        "version": "v3.1",
        "usage_count": 156,
        "updated_at": _TODAY,
        "system_prompt_cn": (
            "短剧主角定妆专家。先写可冻结 lock_en（年龄段、脸型骨相、眼睛目光、发型、"
            "服装面料磨损、一件标志物），再写胸像/中近景出图段：景别、动机光、材质、"
            "50mm/85mm capture。脸必须清晰可认、情绪可读；可略美；禁止二次元/磨皮/白棚/空话质量词。"
            "中文名保留并给全拼；禁止截断拼音。"
        ),
        "system_prompt_en": (
            "Lead portrait lock expert. lock_en = appearance only with face cues; "
            "prompt staging = chest-up, motivated light, materials, 50mm/85mm. "
            "Clear readable face first; slight beauty OK; no anime/plastic/cyclorama/"
            "empty quality words. Keep full Chinese name + pinyin; never truncate."
        ),
        "user_prompt_cn": (
            "角色：{{角色名称}}｜{{性别}}｜约{{年龄}}岁｜风格{{风格}}\n"
            "已知外貌：{{外貌特征}}\n服装：{{服装}}\n姿势倾向：{{姿势}}\n"
            "请产出 lock_en + 胸像定妆 prompt（清晰脸、现场光）。"
        ),
        "user_prompt_en": (
            "Character: {{character name}} | {{gender}} | ~{{age}} | style {{style}}\n"
            "Looks: {{appearance features}}\nWardrobe: {{clothing}}\nPose: {{pose}}\n"
            "Write lock_en + chest-up clear-face portrait prompt with motivated light."
        ),
        "negative_prompt_cn": (
            "二次元, 插画, 塑料皮肤, 磨皮, 环形美容灯, 白棚, 多手指, 畸形手, "
            "文字水印, 糊脸, 换装, 对称假脸, 杂志精修光泽"
        ),
        "negative_prompt_en": CHARACTER_NEGATIVE,
        "default_steps": 24,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "default_model": "flux",
    },
    {
        "id": "tpl_002",
        "name": "短剧-配角定妆",
        "name_en": "Short-drama - Supporting Portrait",
        "category": "character",
        "category_name": "角色生成",
        "version": "v2.1",
        "usage_count": 89,
        "updated_at": _TODAY,
        "system_prompt_cn": (
            "配角定妆：脸仍清晰可认，但服装/光/标志物比主角克制，不抢戏。"
            "lock 与出图规则同主角；禁止二次元与磨皮假脸。"
        ),
        "system_prompt_en": (
            "Supporting portrait: face still clear; wardrobe/light more restrained than lead. "
            "Same lock rules; no anime or plastic skin."
        ),
        "user_prompt_cn": (
            "配角：{{角色名称}}｜身份{{身份}}｜{{外貌特征}}｜{{服装}}｜风格{{风格}}\n"
            "胸像定妆，克制现场光，短剧清晰脸，勿抢主角。"
        ),
        "user_prompt_en": (
            "Support: {{character name}} | role {{identity}} | {{appearance features}} | "
            "{{clothing}} | {{style}}. Chest-up, restrained light, clear face, no lead aura."
        ),
        "negative_prompt_cn": "二次元, 过度华丽, 磨皮, 多手指, 文字水印, 糊脸, 主角光环灯",
        "negative_prompt_en": CHARACTER_NEGATIVE + ", overly ornate costume, spotlight hero glow",
        "default_steps": 24,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "default_model": "flux",
    },
    {
        "id": "tpl_003",
        "name": "实拍-场景定场",
        "name_en": "Live-action - Establishing Scene",
        "category": "scene",
        "category_name": "场景生成",
        "version": "v2.1",
        "usage_count": 67,
        "updated_at": _TODAY,
        "system_prompt_cn": (
            "场景锁专家：空间近中远、材质与使用痕迹、主光从哪来、天气空气。"
            "宽景定场；极小远人仅作比例。自然语言；禁止 8K/masterpiece/霓虹轰炸。"
            "场景要能承接短剧人物调度（进出口、可站立对峙的位置）。"
        ),
        "system_prompt_en": (
            "Scene lock: near/mid/far layout, materials and wear, primary light, weather. "
            "Wide establishing; tiny figures for scale. Natural language; no 8K/neon spam. "
            "Space must support short-drama blocking (entries, stand-off spots)."
        ),
        "user_prompt_cn": (
            "地点：{{场景类型}}｜时间{{时间}}｜天气{{天气}}\n"
            "主光：{{主光}}｜材质痕迹：{{材质}}｜视角：{{视角}}\n"
            "请写 lock_en + 宽景定场 prompt_en（实拍短剧空间）。"
        ),
        "user_prompt_en": (
            "Place: {{scene type}} | {{time of day}} | {{weather}}\n"
            "Key light: {{key light}} | materials: {{materials}} | view: {{viewpoint}}\n"
            "Write lock_en + wide establishing prompt for lived-in short-drama space."
        ),
        "negative_prompt_cn": "建筑坍塌, 空CGI, 霓虹轰炸, 透视扭曲, 文字水印, 二次元, 概念图感",
        "negative_prompt_en": SCENE_NEGATIVE,
        "default_steps": 24,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "default_model": "flux",
    },
    {
        "id": "tpl_006",
        "name": "道具-戏眼特写",
        "name_en": "Prop - Story Object Close-up",
        "category": "prop",
        "category_name": "道具生成",
        "version": "v2.1",
        "usage_count": 45,
        "updated_at": _TODAY,
        "system_prompt_cn": (
            "戏眼道具特写：材质、磨损、反光、与台面的接触阴影要具体。"
            "干净背景；无人物抢戏；让后续分镜能认出同一物件。"
        ),
        "system_prompt_en": (
            "Story-prop close-up: materials, wear, reflections, contact shadows. "
            "Clean backdrop; no people; recognizable across later shots."
        ),
        "user_prompt_cn": (
            "道具：{{武器类型}}｜材质{{材质}}｜磨损/细节{{特效}}｜风格{{风格}}\n"
            "静物特写，自然光，无人物，保留可识别特征。"
        ),
        "user_prompt_en": (
            "Prop: {{weapon type}} | material {{material}} | wear {{special effects}} | "
            "{{style}}. Hero still, natural light, no people, keep identifying marks."
        ),
        "negative_prompt_cn": "人物, 手, 脸, 杂乱背景, 二次元, 文字水印, 悬空无投影",
        "negative_prompt_en": PROP_NEGATIVE,
        "default_steps": 24,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "default_model": "flux",
    },
    {
        "id": "tpl_005",
        "name": "分镜-静帧+运动",
        "name_en": "Storyboard - Still + Motion",
        "category": "storyboard",
        "category_name": "分镜生成",
        "version": "v3.1",
        "usage_count": 178,
        "updated_at": _TODAY,
        "system_prompt_cn": (
            "分镜师：每个 scene_id 至少 1 帧。"
            "prompt_en = 原文粘贴 character/scene lock + 本瞬间一个小动作 + 近景/中近景清晰脸"
            "+ 动机光 + 材质 + 50/85mm。"
            "motion_prompt_en = 一个动作终点 + 一个运镜或固定 + About 5s + 保脸句；禁止重写外貌。"
            "只输出 JSON frames。"
        ),
        "system_prompt_en": (
            "Storyboard: ≥1 frame per scene_id. "
            "prompt_en = verbatim locks + one instant action + clear-face MCU + light + materials. "
            "motion_prompt_en = one action + one camera + ~5s + preserve identity. JSON frames only."
        ),
        "user_prompt_cn": (
            "场景：{{场景内容}}\n角色：{{角色列表}}\n已有锁：{{身份锁}}\n镜头编号：{{镜头编号}}\n"
            "请为该场输出 frames（含 scene_id, prompt_en, motion_prompt_en, avoid, shot_type, line_ids）。"
        ),
        "user_prompt_en": (
            "Scene: {{scene content}}\nCast: {{character list}}\nLocks: {{identity locks}}\n"
            "Shot #: {{shot number}}\n"
            "Output frames with scene_id, prompt_en, motion_prompt_en, avoid, shot_type, line_ids."
        ),
        "negative_prompt_cn": (
            "漏场, 改写身份锁, 糊脸远景当对人镜头, 重写外貌, 多动作堆叠, 8K空话"
        ),
        "negative_prompt_en": (
            "missing scenes, paraphrased locks, blurry wide as dialogue coverage, "
            "appearance rewrite, stacked actions, empty quality words"
        ),
        "default_steps": None,
        "default_cfg": None,
        "default_sampler": None,
        "default_scheduler": None,
        "default_model": None,
    },
]

# 列表展示顺序：剧本优先
_SEED_ORDER = ("tpl_004", "tpl_001", "tpl_002", "tpl_003", "tpl_006", "tpl_005")
SEED_TEMPLATES.sort(key=lambda t: _SEED_ORDER.index(t["id"]) if t["id"] in _SEED_ORDER else 99)

_CATEGORY_DEFAULT = {
    "character": "tpl_001",
    "scene": "tpl_003",
    "prop": "tpl_006",
    "script": "tpl_004",
    "storyboard": "tpl_005",
}


def _persisted_map() -> dict[str, dict[str, Any]]:
    """读取已持久化（用户增改）的模板，按 id 索引；为空时返回 {}。"""
    try:
        from app.db.repositories.prompt_templates import PromptTemplateRepository

        repo = PromptTemplateRepository()
        return {t["id"]: t for t in repo.list_all()}
    except Exception:
        return {}


def list_templates(
    *, category: str | None = None, keyword: str | None = None
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for t in SEED_TEMPLATES:
        merged[t["id"]] = deepcopy(t)
    # 用户新增/改写的模板覆盖同名种子（key 相同则以 .pop 保留种子顺序位置）
    for tid, t in _persisted_map().items():
        if tid in merged:
            merged[tid].update({k: v for k, v in t.items() if v is not None})
        else:
            merged[tid] = deepcopy(t)
    rows = list(merged.values())
    if category:
        rows = [t for t in rows if t["category"] == category]
    if keyword:
        key = keyword.lower()
        rows = [
            t
            for t in rows
            if key in t["name"].lower() or key in (t.get("name_en") or "").lower()
        ]
    # 种子顺序优先，新模板排前面
    seed_order = {t["id"]: i for i, t in enumerate(SEED_TEMPLATES)}
    rows.sort(key=lambda t: (-1 if t["id"] not in seed_order else 0, seed_order.get(t["id"], 0)))
    return rows


def get_template(template_id: str) -> Optional[dict[str, Any]]:
    persisted = _persisted_map().get(template_id)
    if persisted is not None:
        return deepcopy(persisted)
    for t in SEED_TEMPLATES:
        if t["id"] == template_id:
            return deepcopy(t)
    return None


def template_for_asset_type(asset_type: str) -> Optional[dict[str, Any]]:
    tid = _CATEGORY_DEFAULT.get(asset_type)
    return get_template(tid) if tid else None


def sampler_overrides_for_model(
    template: dict[str, Any] | None, model: str
) -> dict[str, Any]:
    """Return steps/cfg/sampler_name/scheduler to inject into the flux sampler."""
    if not template:
        return {}
    out: dict[str, Any] = {}
    if template.get("default_steps") is not None:
        out["steps"] = int(template["default_steps"])
    if template.get("default_cfg") is not None:
        out["cfg"] = float(template["default_cfg"])
    if template.get("default_sampler"):
        out["sampler_name"] = str(template["default_sampler"])
    if template.get("default_scheduler"):
        out["scheduler"] = str(template["default_scheduler"])
    return out
