# 分步提示词包与身份硬锁设计

**日期**: 2026-08-17  
**状态**: 已批准（对话确认方案 1，直接出规格 + 计划并实施）  
**前置**:
- [电影感提示词润色融合](./2026-08-10-cinematic-prompt-polish-design.md)
- [MiniMax-H3 视频接入](./2026-08-13-minimax-video-integration-design.md)

**决策（对话确认）**:
- 质量问题按整条链路重规划（人物漂移、故事不清、AI 海报感、I2V 运动崩）
- 锁定：**文字硬锁 + 定妆/定场图**（A+C）
- 字段：分镜拆 `prompt_en`（静图）与 `motion_prompt_en`（I2V）
- Skill **蒸馏**进 `backend/app/prompt_packs/`，不把 skill 原文当运行时 system
- 造梦师 `zy-cinematic-realism`（CC BY-NC）**禁止原文进发行包**；继续用已改写的 `cinematic_v1`
- Seedance 2.0（MIT）只吸收人物锁 / 单动作 / 单运镜 / 去空话，口径改成 MiniMax I2V，不保留即梦平台指令

---

## 1. 目标与边界

### 1.1 目标
1. 每一步只写自己该写的提示词，下游不再复用上游的「万能一句英文」。
2. 角色/场景资产产出**冻结锚点** `lock_en`；分镜静图必须原样粘贴；I2V 主要靠首帧图，文字只写动作和运镜。
3. 静图走 SDXL `prompt_en`；镜头视频走 MiniMax `motion_prompt_en` + `image_url`。
4. 运行时只读自研 pack；Cursor skill 仍给开发用。

### 1.2 本规格做
- 新 pack：`character_lock_v1`、`scene_lock_v1`、`storyboard_still_v1`、`i2v_motion_v1`
- 轻改 `script_expand_v1`：角色名稳定，不自由发明外貌
- 无 LLM 的拼装层：`prompt_compose.py`（锁注入、I2V 解析）
- 资产字段 `lock_en`；分镜字段 `motion_prompt_en`
- polish 按 stage 选 pack；资产同步走锁 pack；分镜拆解带入锁并产出运动句
- 出图仍用 `prompt_en`；`generate-video` 改用 `motion_prompt_en`
- 前端：资产展示/编辑 `lock_en`；分镜增加运动提示词编辑框

### 1.3 本规格不做
- 把 `.agents/skills/**` 在运行时整文件加载
- 造梦师原文、导演库、Seedance 全量 OS
- 一份 JSON 镜头说明书再编译（方案 B，下一轮）
- 自动批量全部分镜出视频
- LTX / 替换 ffmpeg slideshow 成片主路径
- 多角色参考图 R2V（本期仍是「定妆图 → 分镜静图 → 首帧 I2V」）

### 1.4 成功标准
1. 有 `lock_en` 的角色出现在分镜静图时，`prompt_en` **包含该段原文**（子串相等，不是同义改写）。
2. `POST .../generate-video` 的 job payload 使用 `motion_prompt_en`，不再把静图长描述当 I2V 主提示词。
3. `POST /api/prompts/polish` 的 `character_lock` / `scene_lock` / `storyboard_frame` / `i2v_motion` 各加载对应 pack。
4. 资产同步 enrich 时 stage 为 `character_lock` 或 `scene_lock`，并写入 `lock_en`。
5. 运行时目录不含造梦师 skill 原文。

---

## 2. 分步职责

```
剧本扩写          → 场次、台词、稳定角色名（不写定妆）
     │
     ▼
角色锁 / 场景锁    → lock_en（冻结）+ prompt_en（定妆/定场图）+ 出图
     │
     ▼
分镜静图          → 粘贴 lock_en + 本镜构图/光/情绪 → prompt_en → SDXL
     │
     ▼
镜头 I2V          → 首帧图 + motion_prompt_en（动作+一个运镜+时长）→ MiniMax
```

| 步骤 | Pack | 允许写 | 禁止写 |
|---|---|---|---|
| 剧本 | `script_expand_v1` | 情节、对白、地点、角色名 | 五官/发型/衣服长描述 |
| 角色锁 | `character_lock_v1` | 年龄段、轮廓、发型、服饰、气质；定妆姿势 | 剧情高潮、多镜头、运镜 |
| 场景锁 | `scene_lock_v1` | 空间结构、时代痕迹、主光来源 | 具体角色表演 |
| 分镜静图 | `storyboard_still_v1` | 本镜动作瞬间、机位、光、质感 | 改写 lock；不要写 5 秒运镜长句 |
| I2V | `i2v_motion_v1` | 一个可见动作及终点、一个运镜、约 5s | 重写外貌/换装；8K/masterpiece |

---

## 3. 数据契约

### 3.1 资产 `assets`
新增列：
- `lock_en TEXT NOT NULL DEFAULT ''`：冻结英文锚点。非空后，后续 LLM **不得改写**，只能原样引用。用户可在 UI 手动改。
- 现有 `prompt_en`：定妆/定场**出图**用，必须包含 `lock_en`（若已有）。
- 现有 `image_url`：定妆/定场图（图锁）。

不加 `lock_status`：`lock_en` 非空即视为已锁。

### 3.2 分镜 `storyboard_frames`
新增列：
- `motion_prompt_en TEXT NOT NULL DEFAULT ''`：MiniMax I2V 专用。

现有 `prompt_en` 只服务静图。

### 3.3 拼装（无 LLM）

`backend/app/services/prompt_compose.py`：

- `collect_lock_ens(assets, *, character_name, scene_name) -> list[str]`  
  按名字匹配 `type=character` / `type=scene` 的非空 `lock_en`。
- `compose_still_prompt(shot_body: str, locks: list[str]) -> str`  
  每个 lock 若尚未作为子串出现在 `shot_body` 中，则**前置**粘贴，用空行分隔。不改 lock 文本。
- `resolve_i2v_prompt(frame: dict) -> str`  
  优先 `motion_prompt_en`；否则用镜头字段合成短句（`description_en` 或 `description` 的动作 + `movement` + duration），并追加 `Keep identity and wardrobe unchanged from the first frame.`  
  **禁止**把完整 `prompt_en` 当作 I2V 主词（除非 `motion_prompt_en` 为空且没有可合成的镜头字段——此时仍只用合成句，不用静图锁段落）。
- `assert_locks_present(prompt_en, locks)`  
  每个非空 lock 必须是 `prompt_en` 的子串；供拆解写回与出图前校验。

### 3.4 Polish API
`ALLOWED_STAGES` 扩展为：

`script_scene | asset | character_lock | scene_lock | storyboard_frame | i2v_motion`

| stage | pack | 写回 |
|---|---|---|
| `script_scene` | `cinematic_v1`（保持） | 场景 `prompt_en` / `negative_prompt` |
| `asset` | 若 `context.type=character` → 角色锁 pack，否则若 `scene` → 场景锁 pack，否则 `cinematic_v1` | 资产 `prompt_en`；若返回 `lock_en` 且资产 `lock_en` 为空则写入 |
| `character_lock` | `character_lock_v1` | `lock_en`（仅当空）+ `prompt_en` + `avoid` |
| `scene_lock` | `scene_lock_v1` | 同上 |
| `storyboard_frame` | `storyboard_still_v1` | 帧 `prompt_en`（服务端再 `compose_still_prompt`）+ `avoid` |
| `i2v_motion` | `i2v_motion_v1` | 帧 `motion_prompt_en` |

响应在现有字段上增加可选 `lock_en`、`motion_prompt_en`（缺省空字符串）。`prompt_en` 对 `i2v_motion` 可空，但 `motion_prompt_en` 必填。

### 3.5 生成
- 静图：`resolve_frame_prompt_en` 不变（`prompt_en` → `description_en` → 拼装）。出图前若项目内匹配到 lock，则 `compose_still_prompt` 后再送 Comfy。
- I2V：`resolve_i2v_prompt(frame)` → job `payload.prompt_en`（MiniMax 节点仍吃一个字符串；值来自动词，不来自静图）。

---

## 4. 服务改造要点

### 4.1 `CinematicPolishService`
按 `stage`（及 asset `context.type`）选择 pack 路径。`pack_version` 返回实际 pack 名（如 `character-lock-v1`）。  
`i2v_motion` 校验 `motion_prompt_en` 非空；其它 stage 仍校验 `prompt_en` + `avoid`。  
若 context 已带 `lock_en`，user 消息必须写明：`Copy lock_en VERBATIM into prompt_en; do not paraphrase.`

### 4.2 `asset_script_sync`
- enrich stage：`character` → `character_lock`，`scene` → `scene_lock`（修复当前误传 `character`/`scene` 的问题）。
- 将 polish 的 `lock_en` 或（若模型只回了 `prompt_en`）把 `prompt_en` 中可独立成段的主体描述写入 `lock_en`。最低要求：`lock_en` 非空；若 LLM 未给 `lock_en`，则 `lock_en = prompt_en` 的第一句（到第一个句号）。
- `fallback_prompts` 必须带短 `lock_en`（角色：`"{name}, {style} character, consistent face and wardrobe"`；场景：`"{name}, {style} location, consistent architecture and lighting"`）。

### 4.3 `storyboard_breakdown`
- `_call_llm` 的 payload 增加每场：`location`、`time`、`characters`、以及匹配到的 `character_locks` / `scene_lock`。
- LLM 输出增加 `motion_prompt_en`（英文，≥20 字符，描述动作与运镜，**不要**重复 lock）。
- `_apply_plan`：`prompt_en = compose_still_prompt(llm_shot, locks)`；`motion_prompt_en` 原样存。缺运动句时用 `resolve_i2v_prompt` 的合成回退。
- 禁止再把中文 `description` 写入 `prompt_en`。

### 4.4 剧本 pack
`script_expand_v1` 增加两条：角色名全程一致；不要写五官/发型/服饰长描述（交给资产锁）。

---

## 5. Prompt packs（运行时原文）

包内规则从 skill **改写蒸馏**，禁止整文件拷贝。Seedance 出处在 `prompt_packs/ATTRIBUTION.md` 注明 MIT。

### 5.1 `character_lock_v1/system.md`
产出定妆锚点。JSON：`lock_en`、`prompt_en`、`avoid`、`prompt_cn`。  
`lock_en`：2–4 句，只含年龄段、轮廓、发型、服饰、标志物；无剧情、无镜头。  
`prompt_en`：`lock_en` 原文 + 单张定妆（站姿或半身、中性光、空白或简单背景）。  
禁止 masterpiece/8K；禁止改已提供的 `context.lock_en`。

### 5.2 `scene_lock_v1/system.md`
产出定场锚点。JSON 同上。  
`lock_en`：空间结构、时代/用途痕迹、主光从何处来。  
`prompt_en`：`lock_en` + 无人或极小人物的定场宽景。

### 5.3 `storyboard_still_v1/system.md`
单帧电影感静图（改写自 `cinematic_v1`，强调锁）。  
JSON：`prompt_en`、`avoid`、`prompt_cn`、`interpretation_cn`。  
`prompt_en` 必须先包含 context 里每段 `lock_en` 原文，再写：当下瞬间动作、机位/景别、有动机的光、真实质感。  
不要写多秒运镜；不要换装改脸。

### 5.4 `i2v_motion_v1/system.md`
MiniMax I2V，约 5 秒（length≈124）。首帧已提供外貌。  
JSON：`motion_prompt_en`、`avoid`（可短）。  
公式：一个主体动作及可见终点 + 一个运镜 + 时长暗示。  
多人时每人一个动词；默认禁止同时大动作。  
明确：`Keep identity, face, hair, and wardrobe unchanged from the first frame.`  
禁止重述五官衣服；禁止 8K/masterpiece/cinematic masterpiece。

---

## 6. 前端

| 页 | 改动 |
|---|---|
| 资产 | 展示并编辑 `lockEn`；润色 stage 按类型走 `character_lock` / `scene_lock`；应用时写回 `lock_en` |
| 分镜 | `promptEn` 标签改为「静图提示词」；新增「运动提示词」`motionPromptEn`；润色静图 / 运动可分两次或一次串行；「生成镜头视频」不覆盖静图字段 |

约定：锁与运动结果进可编辑框，不静默覆盖。

---

## 7. 错误处理
- polish：`i2v_motion` 缺 `motion_prompt_en` 则重试一次后失败；其它缺 `prompt_en`/`avoid` 同现网。
- 出图：有 lock 却未包含 → 服务端先 `compose_still_prompt` 补上，不报错打断。
- I2V：无图仍 400；无 `motion_prompt_en` 时用合成短句，不回退到整段静图。
- LLM 与云均不可用：现有 502 文案，禁止假成功。

---

## 8. 测试要点
- `compose_still_prompt` 前置 lock 且不改写；已包含则不重复。
- `resolve_i2v_prompt` 优先运动句；空则合成；合成结果不含 lock 长段。
- polish 各 stage 加载对应 pack（读到的 system 文本可断言关键字）。
- asset sync enrich 调用 `character_lock`/`scene_lock` 并写 `lock_en`。
- breakdown 写回的 `prompt_en` 含 lock 子串，且有 `motion_prompt_en`。
- generate-video job payload 的 `prompt_en` 等于运动句。
- 回归：无 lock 的旧帧仍能出图；slideshow 成片不依赖 `motion_prompt_en`。

---

## 9. 风险
| 风险 | 缓解 |
|---|---|
| LLM 仍改写 lock | 服务端 `compose_still_prompt` 强制前置原文 |
| I2V 提示过长导致运动崩 | motion pack 限制单动作+单运镜；短句回退 |
| 角色名对不上资产 | 按 `assets.name` 精确匹配；匹配失败则不加锁，不编造 |
| 16GB 出视频仍慢 | 不在本规格改分辨率；只改提示词质量 |

---

## 10. 实施顺序
1. `prompt_compose` + 单测  
2. 迁移 `lock_en` / `motion_prompt_en` + 仓库/API  
3. 四个 pack + polish 路由  
4. asset sync + breakdown + generate-video  
5. 前端资产锁与分镜运动框  
6. 剧本 pack 两行约束  
