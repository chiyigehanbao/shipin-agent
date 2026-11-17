# Flux Kontext 人物一致性分镜渲染设计

**日期**：2026-08-28

**状态**：已批准（用户逐节确认架构、数据流、失败处理与验收）

**上游设计**：[H3 原生提示词架构与 AI 选角设计](./2026-08-28-h3-prompt-architecture-design.md)

**模型资料**：[FLUX.1 Kontext](https://bfl.ai/models/flux-kontext)、[ComfyUI 官方 Kontext 工作流](https://docs.comfy.org/tutorials/flux/flux-1-kontext-dev)

## 1. 背景与诊断

第一阶段已经建立 Project Visual Bible、AI 四选一选角、MiniMax H3 编译器和编译产物生命周期，但 Flux 分镜静图仍是纯文本链路：

- `prompt_compose.py` 把人物锁、场景锁和镜头正文直接拼接。
- `workflows/__init__.py` 只向 `flux_gguf.json` 填写正负提示词、尺寸与采样参数。
- 选中的定妆图只作为元数据进入 H3 上下文，没有进入分镜静图的像素生成路径。
- 路由同时负责解析人物、拼提示词、检查模型、创建资产、创建任务与入队，复杂度分散且难以验证。

因此系统虽然知道“选中了哪位演员”，出图模型却从未真正看到该演员。继续增加形容词只能改善平均审美，无法可靠解决跨镜头身份、长相和气质一致性。

本期把定妆图作为 Flux Kontext 的真实图像条件，并将分散逻辑收进一个深层 Storyboard Render Module。

## 2. 已确认的产品决策

1. 人物身份与精致度优先于姿势和构图；发生冲突时允许 Shot Spec 小幅偏离。
2. Casting Reference 只锁定脸部身份、稳定发型、年龄感和体型。
3. 服装、妆容、淋雨、伤势、疲态和脏污由 Look State 控制，不能污染 Character Identity。
4. 第一版最多支持两个强锁角色；超过两个时只锁定排序最前的两个主要角色，其余角色是弱文本约束。
5. 正式生成必须具备 Kontext 模型、有效工作流和合法参考图。
6. 不允许静默退回纯文本 Flux。用户只能通过一次性的显式操作创建 Temporary Degradation。
7. 生成成功先成为 Candidate Frame，用户通过后才成为 Accepted Frame。
8. 第一版不引入未经验证的人脸识别评分；审美结论由结构化人工验收产生。

## 3. 方案比较与选择

### 3.1 方案 A：Kontext 原生参考图直出（采用）

一次请求同时提交定妆参考、Look State、Scene Spec 和 Shot Spec。链路最短，最符合本机已有 `flux1-kontext-dev-Q4_K_S.gguf`，身份一致性优先级最高。

### 3.2 方案 B：普通 Flux 构图后再用 Kontext 写入身份（暂缓）

复杂构图更容易控制，但生成两次会增加耗时、显存压力和二次退化风险。后续可作为复杂构图修复模式单独设计。

### 3.3 方案 C：Redux / SigLIP 持续视觉条件（不实施）

调节空间大，但节点依赖和参数 Interface 更复杂，当前身份收益不确定。本期只保留未来可替换的 Adapter Seam，不提前实现假想 Adapter。

## 4. 架构

### 4.1 Storyboard Render Module

新增深层 Storyboard Render Module。它的外部 Interface 只暴露以下行为：

- `compile(frame_id, render_policy) -> StoryboardRenderRequest`
- `submit(render_request_id) -> RenderAttempt`
- `retry(render_attempt_id, optional_overrides) -> RenderAttempt`
- `accept(render_attempt_id) -> AcceptedFrame`
- `reject(render_attempt_id, reason, note) -> RenderAttempt`

调用者不需要知道 ComfyUI 节点编号、参考图上传方式、提示词结构或模型文件名。Module 的 Implementation 负责：

1. 从 Visual Bible、选中资产、场景和分镜读取事实。
2. 构建并校验不可变 Storyboard Render Request。
3. 选择 Adapter，并把请求转换为具体 ComfyUI 工作流。
4. 创建任务与 Render Attempt，执行并记录结果。
5. 管理 Candidate Frame 到 Accepted Frame 的状态转换。

这个 Module 通过较小的 Interface 隐藏多处生成规则，提供 Depth；调用者获得 Leverage，工作流变化和故障定位集中在一处，获得 Locality。

### 4.2 Adapter Seam

工作流 Seam 上存在两个真实 Adapter：

- `FluxKontextAdapter`：正式路径，接受一到两张 Casting Reference，装配 Kontext 工作流。
- `TextOnlyFluxAdapter`：只接受带显式降级授权的请求，沿用现有普通 Flux 工作流。

两个 Adapter 满足同一个内部 Interface：

- `preflight(request) -> AdapterReadiness`
- `build(request, seed) -> WorkflowSubmission`
- `parse_result(history) -> RenderOutput`

Kontext 工作流 JSON 作为版本化仓库资源保存。Implementation 通过语义化节点映射填参，不允许业务调用者依赖节点编号。工作流文件和预期模型文件均计算版本或哈希并写入 Render Attempt。

### 4.3 现有代码收敛

- `prompt_compose.py` 不再承担正式分镜身份控制，只保留旧项目兼容和纯文本 Adapter 内部使用。
- `workflows/__init__.py` 不再是分镜路由直接调用的万能入口；普通 Flux 与 Kontext 分别进入对应 Adapter。
- `api/storyboard.py` 只负责解析请求、调用 Storyboard Render Module 和映射结构化错误。
- `AssetQueue` 的通用图像执行能力可以复用，但工作流构建应由 Render Attempt 携带或由 Adapter 选择，不能再次从 `model=flux` 猜测。

## 5. 数据契约

### 5.1 Character Identity

每个强锁人物包含：

- `character_asset_id`
- `character_name`
- `reference_asset_id`
- `reference_image_url`
- `reference_image_hash`
- `identity_anchors`：脸型、五官比例、稳定发型、年龄感、体型、辨识锚点
- `reference_order`：双人镜头中与工作流图像输入的稳定对应关系

只有 `selected` 且存在成功图片的选角资产可成为 Casting Reference。旧项目 `legacy` 资产若同时具备 `lock_en`、`completed` 和 `image_url`，作为兼容身份来源，但生成记录必须标记为 `legacy_reference=true`。

### 5.2 Look State

每个角色的可变状态包含：

- `wardrobe`
- `makeup`
- `hair_state`
- `injury`
- `wetness`
- `dirt`
- `fatigue`

字段可以为空。校验器拒绝 Look State 中试图修改脸型、五官、年龄感、体型或角色身份的内容。

### 5.3 Scene Spec 与 Shot Spec

Scene Spec 从关联 scene、场景资产和 Visual Bible 编译，包含地点、时间、天气、光源、色调、材质和连续性。

Shot Spec 从 storyboard frame 编译，包含动作、表情、景别、机位、焦段感、构图和镜头目的。原有 `prompt_en` 仅作为旧项目的补充创作意图，不能覆盖结构化身份与状态。

### 5.4 Render Policy

```json
{
  "mode": "identity_first",
  "max_strong_identities": 2,
  "allow_temporary_degradation": false,
  "identity_priority": ["face", "age", "hair", "body", "pose", "composition"]
}
```

临时降级不是切换全局配置，而是为单次 Render Attempt 创建 `allow_temporary_degradation=true` 的新请求。下一次生成恢复正式策略。

### 5.5 Storyboard Render Request

请求包含：

- `id`、`project_id`、`frame_id`
- `character_identities[]`
- `look_states[]`
- `scene_spec`
- `shot_spec`
- `render_policy`
- `compiled_prompt`
- `negative_prompt`
- `width`、`height`
- `source_hash`
- `validation_status: valid | invalid`
- 读取时根据当前事实计算的 `stale`
- `validation`
- `created_at`

Request 创建后不可原地修改。角色、参考图、Visual Bible、Look State、场景或镜头变化都会改变 `source_hash`。`stale` 是当前事实与快照对比后的计算结果，不回写并篡改旧请求。

### 5.6 Render Attempt

每次执行保存：

- Render Request 完整快照和 `source_hash`
- Adapter 名称、版本及是否降级
- 工作流版本、模型文件标识、参考图哈希
- seed、尺寸和执行任务 ID
- `queued | running | candidate | accepted | superseded | rejected | failed`
- 图片地址、结构化错误
- 驳回原因与备注
- 创建、开始和完成时间

重试创建新的 Attempt，不覆盖旧记录。每个 frame 同时最多有一个 Accepted Frame；接受新候选时，旧 Accepted Frame 降为 `superseded`，但历史记录和文件不删除。

## 6. 持久化设计

新增迁移，避免把快照塞回已有 `prompt_en`：

### 6.1 资产与分镜扩展

- `assets.identity_json TEXT NOT NULL DEFAULT '{}'`
- `scenes.look_states_json TEXT NOT NULL DEFAULT '{}'`，以角色资产 ID 为键保存本场 Look State
- `storyboard_frames.accepted_render_attempt_id TEXT`

Look State 以场次为事实来源，同一场中的所有分镜共享；修改后，该场旧 Render Request 全部变为 stale。Scene Spec 与 Shot Spec 第一版由现有 scenes、storyboard_frames 和 Visual Bible 编译，不重复存两份可变事实。

### 6.2 `storyboard_render_requests`

保存不可变请求 JSON、`source_hash`、校验结果和状态。Repository 不提供通用 update；只允许根据当前事实计算 stale 状态。

### 6.3 `storyboard_render_attempts`

保存执行追踪、快照、Adapter、工作流版本、种子、状态、图片和人工审核。Repository 只允许合法状态转换，禁止从 `failed/rejected` 直接变成 `accepted`。

已有 storyboard asset 继续作为媒体资产容器；Attempt 通过 `asset_id` 关联它。Accepted Frame 仍把当前 `image_url` 和 `asset_id` 镜像到 storyboard frame，保持 MiniMax H3 和旧界面兼容。

## 7. 编译与提示词规则

Kontext 提示词是以参考图为事实来源的编辑指令，不再重复堆叠完整人物锁：

1. 声明每张参考图对应的角色名和画面位置。
2. 明确保持脸部身份、年龄感、稳定发型与体型。
3. 只允许 Look State 指定的外观变化。
4. 描述 Scene Spec 和 Shot Spec。
5. 最后声明身份优先级：动作或构图冲突时保人物身份与精致度。

编译器使用确定性模板，不调用 LLM 临场改写身份。LLM 仍可在分镜拆解阶段生成 Shot Spec 的创作内容，但不能在 Render Request 编译阶段发明或改写 Character Identity。

双人镜头按照 `reference_order` 固定角色与参考图次序，并在提示词中用名字和空间位置重复绑定。第三位及之后的人物只写入背景群演描述，不注入强参考图。

## 8. 生成流程

```text
Prompt IR / 现有项目事实
    ↓
Storyboard Render Module.compile
    ↓
确定性校验 + source_hash
    ↓
有效且未过期的 Storyboard Render Request
    ↓
Adapter preflight
    ↓
创建 Render Attempt 与任务
    ↓
上传参考图 → 装配工作流 → ComfyUI 执行
    ↓
Candidate Frame
    ├── accept → Accepted Frame → 可进入 H3 I2VA
    ├── reject → 记录原因 → 按身份重试
    └── retry → 新 Render Attempt
```

正式生成入口默认选择 `FluxKontextAdapter`。TextOnlyFluxAdapter 只能由单次显式降级入口调用，且产物在界面和记录中始终展示“身份不可信”。

## 9. 错误处理

### 9.1 提交前阻断

- `casting_reference_missing`
- `render_request_stale`
- `too_many_strong_identities`
- `look_state_identity_conflict`
- `kontext_model_unavailable`
- `kontext_workflow_unavailable`
- `reference_upload_invalid`
- `comfyui_unavailable`

错误包含稳定错误码、中文说明、可执行修复建议和相关字段。预检失败不创建昂贵的生成任务。

### 9.2 运行失败

- 保留 Attempt、请求快照、ComfyUI 错误和已使用 seed。
- 支持按原 seed 重试，也支持创建新 seed 的重试。
- Kontext 失败绝不自动调用 TextOnlyFluxAdapter。
- 进程重启后，运行中的 Attempt 与现有 asset/job 一起恢复为可理解的失败状态。

### 9.3 质量驳回

固定原因：

- `identity_drift`：人物身份跑偏
- `appearance_unrefined`：长相不精致
- `wrong_temperament`：气质不符
- `wrong_look_state`：服装或状态错误
- `wrong_action`
- `wrong_composition`
- `other`

驳回原因进入后续质量分析，但第一版不自动修改 Character Identity，也不自动训练或选择模型。

## 10. Interface 与界面行为

保留现有分镜生成路径的兼容入口，但其 Implementation 改为调用 Storyboard Render Module。新增或扩展以下行为：

- 编译/预检当前 frame 的 Render Request。
- 提交正式 Kontext 生成。
- 查看 frame 的 Render Attempt 历史。
- 通过候选图。
- 驳回候选图并提交结构化原因。
- 使用原身份重试，可调整 Look State 或 Shot Spec。
- 显式执行一次 Temporary Degradation。

分镜界面展示：

- 当前强锁角色及参考缩略图
- Look State 摘要
- 正式/降级标记
- 请求是否 stale、阻断原因
- 候选图历史、seed、通过/驳回/重试操作
- 只有 Accepted Frame 才显示“可生成 H3 视频”

旧项目首次打开时按现有 frame 和 legacy 资产编译最小请求，不批量改写历史提示词或图片。

## 11. 测试设计

Interface 是主要测试面。

### 11.1 编译测试

- Identity、Look State、Scene Spec、Shot Spec 按固定顺序编译。
- Look State 不能覆盖永久身份。
- 单人、双人及三人以上镜头的强弱约束正确。
- 输入事实变化使旧请求 stale。
- 编译结果对相同输入稳定，`source_hash` 可复现。

### 11.2 策略测试

- 缺参考图、超过双强锁、请求 stale、Kontext 不可用时正式提交失败。
- 未显式授权时 TextOnlyFluxAdapter 从不被调用。
- 降级授权只对单次 Attempt 有效。
- rejected/failed Attempt 不能直接接受。
- 新 Accepted Frame 会 supersede 旧记录而不删除历史。

### 11.3 Adapter 契约测试

- 使用固定工作流样本验证一张和两张参考图的节点填充。
- 验证模型、正负提示词、seed、尺寸和输出解析。
- 验证参考图上传失败和 ComfyUI history 错误映射。
- 普通 Flux 现有工作流测试继续通过。

### 11.4 流程测试

- 编译 → 正式生成 → candidate → accept。
- candidate → reject（结构化原因）→ 按原身份重试。
- 正式失败后不会静默降级。
- 用户主动降级会产生清晰标记的新 Attempt。
- Accepted Frame 可进入 H3 I2VA，未接受候选不能进入。
- 前端生产构建通过，现有后端测试无回归。

## 12. 人工验收

使用同一位选中演员生成至少三张差异明显的分镜：

1. 室内近景、常规服装。
2. 户外雨夜中景、湿发换装。
3. 双人镜头、不同动作与构图。

通过条件：

- 三张图仍能明确识别为同一角色。
- 换装、湿发和场景状态不污染永久身份。
- 双人镜头不串脸、不交换身份。
- 系统不会为严格复制姿势而明显牺牲脸部与气质。
- 每次正式生成都能追溯参考图、请求快照、工作流版本和 seed。
- 用户能明确区分 Candidate Frame、Accepted Frame 和 Temporary Degradation。

人物“精致”属于项目审美目标，由人工验收决定；自动化测试只保证系统确实把正确身份、状态和策略送到正确 Adapter。

## 13. 实施顺序

1. 扩展 Prompt IR 与持久化模型，建立 Render Request / Attempt Repository。
2. 先写 Storyboard Render Module 的编译、策略与状态转换测试。
3. 引入版本化 Kontext 工作流并实现 FluxKontextAdapter。
4. 把现有普通 Flux 收进 TextOnlyFluxAdapter。
5. 改造任务执行与分镜入口，移除路由中的字符串拼接职责。
6. 增加 Candidate Frame 审核和临时降级界面。
7. 执行自动化回归与三镜头人工验收。

## 14. 非目标

- 不在本期实现两阶段复杂构图修复。
- 不安装或实现 Redux / IP-Adapter / PuLID 链路。
- 不以人脸识别分数自动批准图片。
- 不支持超过两个角色的强身份参考。
- 不自动删除旧图、旧 Attempt 或旧提示词。
- 不重写 MiniMax H3 编译器，只把 Accepted Frame 作为其合法首帧来源。
