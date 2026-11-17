# 资产生成可用性：Comfy 连通性 + 从剧本同步

**日期**: 2026-08-12  
**状态**: 已确认（规格 OK）  
**前置**:
- [工作台真实化：LLM + SQLite + 剧本扩写](./2026-08-11-workbench-persistence-llm-design.md)
- [前端模型接线](./2026-08-10-frontend-model-wiring-design.md)
- [电影感提示词润色](./2026-08-10-cinematic-prompt-polish-design.md)

**背景问题**:
1. 用户进入资产页不知如何生图；不清楚是否自动关联 ComfyUI 工作流。  
2. 列表混入 mock 种子（张三/李四等），状态显示「生成完成」但无图，造成「一直在生成/已完成」的错觉。  
3. 点「重新生成」失败：`comfyui_unavailable`；探活要求 `/system_stats` 返回 200，本机 Comfy 曾返回 **503**，任务从未提交到 Comfy 队列。  
4. 资产提示词过短，未结合项目 `style` 与剧本场景描述，不利于出图。

**决策（对话确认）**:
- 范围：**A + 先做连通性**——先修连通性与用法误导，再实现从剧本同步角色/场景并生成丰富提示词。  
- 生图链路保持现状：内置 workflow 模板（sdxl/sd15/flux）+ 串行 `AssetQueue` + ComfyUI HTTP；用户无需在 Comfy 里手动搭图。  
- 同步只产生草稿资产（`pending`），**不**自动排队生图；由用户点「重新生成」或后续「批量生成」再入队。  
- **不做**：改 Comfy 节点图、真视频模型、进页自动全量开画、认证。

---

## 1. 目标与边界

### 1.1 目标
1. 资产页一眼能判断 Comfy 是否可用；不可用时拦截生成并给出可操作说明。  
2. 列表只展示真实项目资产；去掉 mock 种子对状态的污染。  
3. 一键从剧本抽出角色/场景草稿，提示词结合项目风格与场景上下文，达到可出图丰富度。  
4. 用户理解操作路径：同步 →（可选润色）→ 重新生成 → Comfy 出图 → 预览确认。

### 1.2 本规格做
- 一期：连通性状态条、中文错误映射、生成前健康检查、移除 mock 种子、简短用法提示。  
- 二期：`从剧本同步` API + 前端按钮；LLM 丰富中英提示词与 negative；幂等合并（按名称+类型）。

### 1.3 本规格不做
- Comfy Desktop / 端口自动发现与改写（可在 UI 展示当前 `comfyui_base_url`，改 URL 走既有设置）。  
- 道具（prop）从剧本自动抽取（可预留类型，二期默认只做 character + scene）。  
- 分镜帧图、成片、TTS。  
- 提示词模板库后台管理。

---

## 2. 一期：连通性与去误导

### 2.1 Comfy 状态
- 资产页加载时与「重新生成」前调用现有探活（`client.health()` 或 `/api/models/services` 中 sd 状态）。  
- 顶部状态条三态：
  - **在线**：可生成。  
  - **不可用**：展示当前 base URL（默认 `http://127.0.0.1:8188`）、简短原因（连接失败 / HTTP 非 200，含 503）、操作建议（启动 ComfyUI、确认端口、重试）。  
  - **检测中**：短暂 loading。

### 2.2 生成拦截
- `POST .../generate`：若 `client.health()` 为 false，直接 **503/503-equivalent 业务错误**（建议 HTTP 503 或 400 + 稳定 `detail` 码 `comfyui_unavailable`），**不**创建 generating 资产、**不**入队。  
- 队列 worker 内现有 `comfyui_unavailable` 逻辑保留作兜底（探活在入队后变挂）。  
- 前端将 `comfyui_unavailable` 映射为中文说明，禁用主生成按钮或点击后 toast，避免 silent fail。

### 2.3 移除 mock 种子
- `_list_assets` **不再合并** `mock_characters` / `mock_scenes_assets` / `mock_props`。  
- 空列表展示空态 + CTA：「从剧本同步」或「新建资产」（若已有新建入口则保留）。  
- 删除或降级为测试夹具：mock 常量若仅被列表使用可删；单测若依赖 mock 改为 fixture。

### 2.4 用法提示（轻量）
- 资产页右侧或状态条旁一行说明：生成经本地 ComfyUI 串行队列；点「重新生成」会自动提交内置工作流，无需在 Comfy 手动操作。  
- 底部「生成中 N 个」仅统计真实 `generating` / 队列中资产，与 mock 脱钩。

---

## 3. 二期：从剧本同步（方案 A）

### 3.1 数据源
- 项目：`style`、`name`、`type`（drama/comic/video）。  
- 场景表：`characters_json`、`description` / `description_en`、可选 `location`。  
- 聚合：
  - **角色**：跨场景 `characters` 去重（trim、忽略空串）。  
  - **场景**：每个 scene 一条资产候选（名称优先 location / 场景标题字段；若无则用描述截断或 `场景{n}`）。

### 3.2 API
- `POST /api/assets/{project_id}/sync-from-script`  
  - Body 可选：`types: ["character","scene"]`（默认两者）、`enrich: true`（默认 true，走 LLM 丰富提示词）。  
  - 行为：
    1. 读项目与场景；无场景则 400，提示先完成剧本扩写。  
    2. 对每个候选：若同项目已存在同 `type` + 同 `name` 的资产则 **跳过或更新提示词**（推荐：已有 `completed` 且有 `image_url` 则跳过；`pending`/`failed` 可刷新提示词）。  
    3. `enrich=true` 时调用润色服务（复用 `CinematicPolishService`），`stage` 区分 character/scene，`context` 注入 `project.style`、相关场景描述摘要。  
    4. 创建/更新资产：`status=pending`，写入 `prompt_cn` / `prompt_en` / `negative_prompt`。  
  - 返回：`{ created, updated, skipped, assets: [...] }`。  
- 同步本身可为同步 HTTP（LLM 可能较慢）；若角色/场景很多（>8）可后续改为 Job——**本规格默认同步请求内完成**，前端显示 loading；超时与现有 LLM timeout 对齐。

### 3.3 提示词质量
- 输入：角色名或场景名 + 项目 style + 最多 2～3 条相关场景描述摘要。  
- 输出：可出图的 `prompt_en`（主）、`prompt_cn`、`avoid`/`negative_prompt`；禁止只回短标签句。  
- LLM 不可用时：降级为模板拼接（style + 名称 + 场景摘要），仍写入 pending，并在响应中标记 `enrich_fallback: true`。

### 3.4 前端
- 按钮：**「从剧本同步」**（角色/场景 Tab 附近或空态主 CTA）。  
- 同步成功后刷新列表；默认选中第一条新建/更新项。  
- 保留「润色」「润色并生成」「重新生成」；同步后的文案应已足够，润色为二次加工。  
- 可选轻量：**「批量生成 pending」**——仅对当前 Tab 的 pending 且 Comfy 在线时入队；本规格列为 **应做**（小成本，减少逐个点生成）。

---

## 4. 错误与状态文案

| 内部码 / 条件 | 用户可见 |
|---------------|----------|
| `comfyui_unavailable` / health false | ComfyUI 不可用：请启动服务并确认地址（当前：{url}）。若页面打开但 API 返回 503，多为 Comfy 仍在加载，请稍后重试。 |
| 模型未就绪 | 模型权重未就绪：缺少 {files}… |
| 无场景可同步 | 请先在剧本工坊完成扩写/解析。 |
| 同步成功 | 已同步：新建 x，更新 y，跳过 z。 |

---

## 5. 验收标准

### 一期
1. 关闭 Comfy 或 `/system_stats` 非 200 时：状态条为不可用；点重新生成不入队，提示中文原因。  
2. Comfy 正常且模型就绪时：重新生成后 Comfy 队列出现任务，完成后预览有图。  
3. 新项目资产列表默认为空，不再出现张三/李四等无图「已完成」。

### 二期
1. 有扩写场景的项目点「从剧本同步」后，角色/场景列表出现真实草稿，提示词明显长于单句标签，且含风格相关信息。  
2. 再次同步不产生大量重复同名资产（幂等规则符合 3.2）。  
3. 批量生成（若实现）仅在 Comfy 在线时入队 pending。

---

## 6. 风险与注意
- Comfy 返回 503：属运行时问题，产品侧以文案+拦截为主，不在本规格内「修好 Comfy」。  
- LLM 同步耗时：角色多时体验变慢；超限可后续 Job 化。  
- 与旧 mock 依赖的手工测试习惯变化：以空态 + 同步为准。

---

## 7. 实现顺序
1. 一期后端：去掉 mock 合并、generate 前 health 检查、错误码稳定。  
2. 一期前端：状态条、文案映射、空态。  
3. 二期：sync API + enrich + 幂等。  
4. 二期前端：同步按钮、批量生成 pending、刷新列表。  
5. 测试：列表无 mock、health 失败不入队、sync 幂等与 enrich fallback。
