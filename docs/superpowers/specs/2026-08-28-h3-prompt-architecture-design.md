# H3 原生提示词架构与 AI 选角设计

**日期**：2026-08-28
**状态**：已批准（用户确认方案二并要求直接实施）
**上游**：`https://github.com/MiniMax-AI/MiniMax-H3`，提交 `d21241f0a4b3acbb34c97dae47fa417b7065e438`

## 1. 背景与诊断

现有“剧本 → 资产 → 分镜 → 视频”流程是正确的，问题在于各阶段把自然语言提示词当成跨阶段数据模型：角色、场景、镜头动作与模型语法混在 `prompt_en` / `motion_prompt_en` 中，下游只能复制、拼接或自由改写。

真实项目“全链路走查·雨巷”暴露出以下问题：

- 角色锁把疲态、污渍、尖锐骨相、冷汗等剧情状态固化为永久身份，人物精致度和气质失控。
- 角色图使用相同的居中胸像、浅景深背景套路，角色与叙事空间脱离。
- 场景锁中英混杂，分镜静图直接拼接整段角色锁与场景锁，模型重点被稀释。
- 部分分镜回退成通用句，动作、状态终点与镜头目的缺失。
- I2V 只使用简短运动句，没有 MiniMax H3 的三段式声画结构、首帧对齐语句或有效时长检查。
- 前端用 39 帧提交 I2V，却在提示词中写“约 5 秒”，时间条件互相冲突。
- pytest 运行时使用正式 SQLite 默认路径，测试记录污染生产项目、RAG 和任务统计。

## 2. 决策

采用“统一视觉规格 + 模型编译器”，保留现有产品流程，不重写整个应用：

1. 模型无关的 Prompt IR 是事实来源。
2. Flux/SDXL 与 MiniMax H3 分别拥有自己的编译器。
3. 提示词是带来源指纹、版本和状态的编译产物，不再反向定义项目事实。
4. MiniMax 官方 `h3-prompt-writing` 原文作为有出处的运行时参考资源，不对其内容冒充自研或悄悄改写。
5. H3 编译采用“确定性上下文组装 → 本地 LLM 改写 → 确定性校验 → 一次自动修复”。
6. 生成前可预览、编辑和锁定；输入变化后旧产物变为 stale，人工内容不被静默覆盖。
7. 默认角色审美为“精致商业短剧演员感”：五官协调、有辨识度、上镜、真实年龄和自然皮肤；拒绝塑料网红脸，也不主动添加疲态、脏污、凹陷或攻击性骨相。
8. 主要角色先产生四个选角候选，用户选中后才建立可进入分镜的身份参考。

## 3. 总体架构

```text
剧本与创作意图
    ↓
Project Visual Bible（项目视觉圣经）
    ↓
Character Identity / Look-State / Scene Spec / Shot Spec
    ↓
Compiler Registry
    ├── Casting / Image Compiler（第一期薄切片，第二期全面迁移）
    └── MiniMax H3 Compiler（第一期 T2VA + I2VA）
    ↓
Validation Report
    ↓
Draft → Edited → Locked / Stale
    ↓
ComfyUI workflow
```

现有 `prompt_en`、`motion_prompt_en` 暂时保留为兼容缓存。新代码只能从规格编译到这些字段或直接使用 `compiled_prompts.content`，不得从提示词反推并覆盖规格。

## 4. 第一期范围

### 4.1 数据隔离

- pytest 在导入应用前设置唯一测试 SQLite 路径，禁止触碰 `backend/data/shipin-agent.db`。
- 测试 ModelHub 使用仓库内可写的唯一临时目录，测试退出时清理；生产默认保持不变。
- 现有已污染生产库不自动删除，避免破坏用户数据。后续另提供只读审计与显式清理工具。

### 4.2 Project Visual Bible

每个项目可保存一份 JSON 规格，第一期字段包括：

- `casting_aesthetic`：默认精致商业短剧演员感。
- `realism_policy`：自然皮肤、可信材质、真实年龄，禁止塑料皮肤和过度磨皮。
- `identity_policy`：永久身份只包含稳定面部、体型与辨识锚点。
- `state_policy`：淋雨、伤势、疲惫、妆容和服装属于 Look/State。
- `cinematography`：摄影、色彩、构图和镜头密度约束。
- `negative_defaults`：项目级禁止项。
- `version`：规格版本。

缺少持久化规格的旧项目自动得到默认规格，不要求迁移后才能打开。

### 4.3 AI 选角薄切片

- 角色候选以现有 asset 为载体，新增候选组、候选序号和选择状态。
- 本地 LLM根据角色剧情功能与 Visual Bible 生成四份有区分度的候选身份方案。
- 候选提示词统一使用中性光、统一景别和干净背景，让用户比较脸、年龄、气质与辨识度，而不是比较场景特效。
- 永久身份禁止出现雨、血、泥、疲态、冷汗、伤势、剧情动作和镜头语言。
- 四个候选可沿用现有 Flux 队列并行排队、串行出图。
- 用户选择一个候选后，该候选成为 `selected`，同组其余候选成为 `rejected`；只有 selected 且已有图片的角色满足分镜 readiness。
- 旧项目中的已完成角色资产视为 `legacy_selected`，避免破坏现有项目。

人物参考图真正接入 Flux 分镜工作流需要盘点本机 ComfyUI 节点和权重。第一期先建立数据契约与选角关卡；若现有工作流支持参考条件则直接绑定，否则在第二期加入经验证的身份参考节点。

### 4.4 H3 编译器

第一期支持：

- `T2VA`：由文本 brief、项目视觉规格和可选镜头数据编译完整声画时间线。
- `I2VA`：由分镜首帧、角色/场景规格、镜头动作、台词和声音编译完整 H3 提示词。

H3 输出必须遵循官方字段和顺序：

```text
[I2VA 固定首帧对齐语句，仅 I2VA]

integrated_multimodal_description: ...

overall_soundscape: ...

non_diegetic_music: ...
```

编译上下文必须包含：模式、有效时长、项目视觉规格、角色身份与当前状态、场景锚点、镜头构图、动作起止、摄影机运动、原文台词、环境声和配乐策略。LLM 不能翻译或改写台词。

校验器检查：

- 字段存在、顺序和空行结构。
- I2VA 固定首帧对齐语句逐字匹配。
- `[Shot N]` 连续，剪切时间严格递增且不超过有效时长。
- 对话只在 `<d>[Language] ...</d>` 内，原文保持不变。
- `overall_soundscape` 与 `non_diegetic_music` 分离。
- 4–15 秒范围与 Comfy 帧数一致。
- 不出现未解析引用标签。

首次输出不合法时，编译器把校验问题和原输出交给同一 LLM 修复一次；仍失败则返回 422，不提交昂贵的视频任务。

### 4.5 编译产物生命周期

`compiled_prompts` 保存：

- 项目、来源类型与来源 ID。
- 目标模型、模式与官方指南版本。
- 输入 `source_hash`。
- 编译正文与 validation JSON。
- provider、创建时间、更新时间。
- `draft | locked` 状态及 `is_user_edited`。

读取或生成时重新计算 source hash。不同则在 API 响应中标记 `stale=true`；stale 产物不能直接送入生成队列。用户编辑只更新产物，不修改 IR。

### 4.6 API 与界面

新增：

- `GET/PUT /api/prompts/visual-bible/{project_id}`
- `POST /api/prompts/h3/compile`
- `GET /api/prompts/h3/latest/{project_id}/{source_type}/{source_id}`
- `PUT /api/prompts/h3/{compiled_prompt_id}`
- `POST /api/assets/{project_id}/characters/{asset_id}/cast`
- `POST /api/assets/{project_id}/characters/{asset_id}/select`

分镜页增加 H3 编译面板，展示模式、有效时长、指南版本、校验结果、stale/locked 状态和可编辑正文。点击“生成镜头视频”时：

1. 没有有效产物则自动编译并展示，不直接提交。
2. 已有有效 draft/locked 产物则提交。
3. stale 或 invalid 产物阻止提交并提示重新编译。

默认 I2V 恢复到约 5 秒，不再硬编码 39 帧。

资产页增加“AI 选角 4 版”和“选定此演员”。候选未生成完时显示真实状态；选定后才能进入后续分镜。

## 5. 错误处理

- LLM 不可用：返回现有可读 LLM 错误，不降级为不合规的旧运动短句。
- H3 校验失败：返回逐项 issue，不创建视频 job。
- 官方规则文件缺失或哈希异常：服务启动/编译时明确失败，不使用内嵌旧副本。
- ComfyUI 或模型未就绪：编译仍可执行；只有生成阶段检查 readiness。
- 候选部分失败：保留已完成候选，可单独重试，不自动把失败候选选中。
- 旧项目：继续可读；首次编译时按旧字段构建最小 IR 并提示来源为 legacy。

## 6. 测试与验收

### 自动化

- pytest 运行后正式 DB 的字节和 mtime 不变化。
- 默认 Visual Bible 不包含疲态、污渍、冷汗等永久缺陷词。
- 四个选角候选具有不同的可观察面部/气质方案，且不含剧情状态词。
- 未选择候选不能通过角色 readiness；legacy completed 资产保持兼容。
- T2VA/I2VA 编译器覆盖合法输出、一次修复、最终失败、台词保持和时长边界。
- I2VA 生成 job 使用 `compiled_prompts.content`，不再使用 `motion_prompt_en`。
- source hash 变化后旧产物被标记 stale 并阻止生成。
- 前端生产构建通过。

### 人工验收

- “雨巷”角色可生成四位精致但真实、气质不同的候选，而不是四张相同的通用 AI 人像。
- 选定演员后，分镜页能看到完整 H3 I2VA 结构、首帧对齐语句、声景和配乐字段。
- 5 秒视频的描述与实际帧数一致。
- 修改角色、场景或镜头后，旧 H3 提示词明确显示已过期。

## 7. 第二期边界

第二期另写规格与计划，全面迁移 Flux/SDXL：角色参考条件、服装 Look、场景 plate、分镜构图编译、参考图绑定和像素级一致性评估。本期只做能支撑选角和 H3 I2V 的最小图片侧改造，不承诺仅靠提示词实现跨镜头身份一致。

## 8. 非目标

- 本期不接 FL2VA、L2VA、Ref2VA 生成入口，但数据模型与指南加载器不得阻止后续扩展。
- 不自动删除已污染的生产数据。
- 不下载 MiniMax 模型权重。
- 不用 H3 官方视频提示词规则编写 Flux/SDXL 静图提示词。
- 不把模型生成结果宣称为已通过人工审美验收。
