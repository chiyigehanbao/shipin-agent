# 资产生成 + 分镜：清晰脸质量闸门设计

**日期**: 2026-08-17  
**状态**: 已批准并已实施（对话确认方案 1；用户要求写完整规格+计划后直接实施）  
**前置**:
- [分步提示词包与身份硬锁](./2026-08-17-stage-prompt-packs-design.md)
- [电影感提示词润色融合](./2026-08-10-cinematic-prompt-polish-design.md)

**决策（对话确认）**:
- 范围：**资产生成页 + 分镜页**
- 主痛点：**提示词 / 出图质量**（不是单纯按钮多）
- 风格：短剧清晰脸 + 实拍底子；冲突时 **保脸 > 保糙感**（脸清楚、可认、情绪可读；光可略好看）
- 做法：**方案 1 硬门槛流水线** — 加强文字规则，且 **定妆图必经**；不做字段编译表单、不做 IP-Adapter

---

## 1. 目标与边界

### 1.1 目标
1. 角色必须先完成「可用定妆」：合格 `lock_en` + 至少一张成功定妆图，再进入分镜。
2. 定妆 / 分镜静图提示词统一「短剧清晰脸」口径，减少二次元、磨皮假脸、海报空话。
3. 分镜静图强制粘贴身份锁，景别默认脸可读；I2V 仍只写运动。
4. 失败可理解：不可用角色在分镜侧被拦截，并指向资产页补齐。

### 1.2 本规格做
- 风格口径写入 `character_lock_v1` / `scene_lock_v1` / `storyboard_still_v1`（及 breakdown pack 相关句）
- 资产「可用」判定：`is_character_ready(asset)` / 项目级 `list_unready_characters`
- 分镜规划 API 与静图出图：出场角色未就绪则 400，文案明确
- 前端资产列表展示就绪态；分镜规划/出图前校验并提示
- 定妆润色校验略加强：`lock_en` 须含脸部可读线索（眼睛或脸型一词 + 非空 staging）

### 1.3 本规格不做
- 定妆卡表单字段编译（方案 2）
- Comfy IP-Adapter / PuLID（方案 3）
- 整站 UI 换皮、删除历史版本清理工具（可后续）
- 自动批量全片出视频
- 改 MiniMax / Flux 工作流拓扑（除提示词与闸门）

### 1.4 成功标准
1. 角色无定妆图时，分镜 `breakdown` 与帧 `generate` 返回明确错误（含角色名）。
2. 角色有 `lock_en` + `completed` + `image_url` 时可通过闸门。
3. 润色后 `lock_en` 仍原文注入分镜静图（既有 compose 行为保持）。
4. 资产页能看出每个角色是否「可用」。
5. Pack 文本含清晰脸 / 短剧口径关键字；单测可断言。

---

## 2. 风格口径（全链路同一套）

写入各 pack 的硬规则（中英混排指令，产出仍以英文 `lock_en`/`prompt_en` 为主）：

| 要 | 不要 |
|---|---|
| 清晰可认的脸、眼神可读 | 半脸糊在阴影里、过远全景当定妆 |
| 近景 / 中近景 / 胸像定妆 | 全身时尚大片当默认定妆 |
| 现场动机光，可略美 | 磨皮假脸、beauty ring、二次元、插画 |
| 情绪靠眉眼与口型倾向 | 空洞「beautiful cinematic masterpiece」 |
| 皮肤可有轻微质感 | 塑料皮肤、CGI 人偶 |

场景锁：空间清楚即可，不抢角色脸。  
分镜静图：有角色出场时默认 `近景`/`中近景`，除非用户/场次明确要求全景。

---

## 3. 数据与判定

### 3.1 不新增 DB 列（YAGNI）
沿用：
- `assets.lock_en`、`assets.status`、`assets.image_url`、`assets.type`、`assets.name`
- `storyboard_frames.prompt_en`、`motion_prompt_en`

「可用角色」纯函数（放 `prompt_compose.py` 或小模块 `asset_readiness.py`）：

```text
is_character_ready(asset) :=
  type == "character"
  AND lock_en.strip() 非空
  AND status == "completed"
  AND image_url 非空
```

场景资产本期不做硬闸门（可提示但不定妆必过）；分镜闸门只卡 **character**。

### 3.2 出场角色解析
分镜规划：对每个 scene 的 `characters[]`，在项目 assets 中按 `type=character` 且 `name` 精确匹配。  
找不到资产 → 视为未就绪（需先同步剧本资产）。  
匹配到但未 ready → 未就绪列表。

帧静图出图：用帧上的 `character` 字段（逗号分隔）或关联 scene 的 characters；至少校验帧提及的角色名。

---

## 4. API 与服务

### 4.1 `GET /api/assets/{project_id}/readiness`（可选但推荐）
返回：
```json
{
  "characters": [
    {"id": "...", "name": "苏遥", "ready": false, "reasons": ["missing_image", "empty_lock"]}
  ],
  "ready_count": 1,
  "total_characters": 3
}
```
前端资产页可直接用；没有该端点时前端也可用列表字段本地算同样逻辑。

### 4.2 分镜 breakdown
在 `StoryboardBreakdownService.run` 开头（`replace_empty` / `rebuild_*` 真正调 LLM 前）：
- 收集相关 scenes 的全部角色名
- `unready = [...]`
- 若非空：`raise StoryboardBreakdownError` / HTTP 400：  
  `characters_not_ready: 苏遥, 黑衣人 — 请先在资产生成完成定妆图与身份锁`

`assign_lines_only` 不卡定妆图（只改台词分配）。

### 4.3 分镜帧静图 `generate`
出图前：解析帧角色 → 未就绪则 400，同上文案。  
通过后：现有 `compose_still_prompt` 仍强制粘贴 lock。

### 4.4 资产润色
保持 `character_lock` pack；加强 pack 与校验：
- `lock_en` 至少提到眼/脸/jaw/iris/gaze 之一（英文小写匹配），否则重试一次
- staging 仍要求与 lock 不同且足够长（已有 `character_portrait_split_error`）

### 4.5 Pack 改写要点
- `character_lock_v1`：默认胸像/中近景；「short-drama clear face」；略美允许；禁 anime/illustration/plastic
- `storyboard_still_v1` / `storyboard_breakdown_v1`：有角色时优先近景/中近景；锁原文；清晰脸
- `i2v_motion_v1`：不变原则（运动 only）

---

## 5. 前端

### 5.1 资产生成
- 角色组标题旁：`可用` / `待定妆`（绿/灰）
- 未就绪原因短文案：`缺身份锁` / `缺定妆图` / `生成失败`
- 「下一步：分镜」不强制拦截（避免卡死），但若存在未就绪角色，用 `Modal.confirm` 警告
- 定妆流程文案：先润色 → 再生成 → 看到图才算可用

### 5.2 分镜
- 「分镜规划」失败时展示后端 `characters_not_ready` 原文 + 按钮链到资产页
- 「生成此帧」同样处理 400
- 可选：页顶 Alert 列出未就绪角色（调 readiness 或资产 list）

---

## 6. 错误处理
| 情况 | 行为 |
|---|---|
| 未就绪角色进 breakdown | 400，不调 LLM |
| 未就绪角色帧出图 | 400，不入队 |
| 润色 lock 缺脸线索 | 重试一次；仍失败则 PolishError |
| 旧项目无 lock 的角色 | 视为未就绪，引导回资产润色+出图 |
| 场景无角色 | 不挡规划 |

---

## 7. 测试
- `is_character_ready` 真假表
- breakdown 在未就绪时不调用 LLM
- frame generate API mock：未就绪 400；就绪走原队列
- pack 含 `clear face` 或 `短剧`/`胸像` 等关键字
- 前端：不强制 E2E；逻辑函数若抽出可单测（可选）

---

## 8. 风险
| 风险 | 缓解 |
|---|---|
| 闸门过严导致「完全不能分镜」 | 文案指路；允许无角色空镜场景 |
| LLM 仍写糊脸远景 | pack + 校验眼/脸关键词；服务端 compose 保 lock |
| 用户只想跳过定妆试分镜 | 本期坚持硬闸；二期可加「开发者模式跳过」 |

---

## 9. 与既有规格关系
本规格是 [stage-prompt-packs](./2026-08-17-stage-prompt-packs-design.md) 的 **质量闸门增强**，不替换锁字段与 compose；实施时复用 `lock_en` / `compose_still_prompt` / polish stages。
