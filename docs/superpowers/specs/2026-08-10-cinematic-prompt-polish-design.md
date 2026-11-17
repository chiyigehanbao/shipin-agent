# 电影感提示词润色融合设计

**日期**: 2026-08-10  
**状态**: 已批准（对话确认）  
**前置**:
- [AI 模型后端接入设计](./2026-08-09-ai-model-backend-integration-design.md)
- [前端模型接线与就绪探测设计](./2026-08-10-frontend-model-wiring-design.md)

**灵感来源**（非原文嵌入）: [造梦师 / zy-cinematic-realism](https://github.com/popopo-99/zy-cinematic-realism)（CC BY-NC 4.0）。本规格采用**自研提示词包**借鉴其工作流与字段契约，不整包复制原文进入运行时发行物。

**范围**: 凡「设计视觉提示词」的入口，统一走共享电影感润色服务；按 **剧本 → 资产 → 分镜 → 生成** 接通；本地 Ollama 优先、失败自动降级云 API；正/负向提示词注入 ComfyUI；分镜帧可复用资产生成队列出图。

---

## 1. 目标与边界

### 1.1 目标
- 产品内嵌「电影感」规则：不单靠模型自由发挥，用自研 prompt pack + LLM 约束输出。
- 剧本拆解、资产生成、分镜帧三处共用同一润色契约与服务。
- LLM：本地 Ollama 优先；超时/不可达时自动降级到已配置的云 API；响应标明实际 `provider`。
- 生成链路：`prompt_en` + `avoid`（`negative_prompt`）写入实体，并注入 ComfyUI workflow 负向节点；分镜一键出图复用 `AssetQueue`。

### 1.2 本规格做
- 后端：`CinematicPolishService`、`LLMProvider`（Ollama → Cloud failover）、`POST /api/prompts/polish`
- 自研 prompt pack：`backend/app/prompt_packs/cinematic_v1/` + `ATTRIBUTION.md`
- 实体补齐：Asset / StoryboardFrame 增加 `negative_prompt`
- `build_workflow(model, prompt, negative_prompt)` 注入负向（替换写死负向）
- 前端：剧本 / 资产 / 分镜调用 polish；显式「应用」或「润色并生成」
- 分镜帧生成：复用 AssetQueue + 轮询展示 `image_url`

### 1.3 非目标（本规格不做）
- 整包嵌入造梦师原文或完整导演库上线（`options.director` 仅预留，默认 `null`）
- RAG 案例检索与润色联动
- 视频模型（LTX / MiniMax 等）提示词
- 多用户权限、提示词云端版本历史
- 自动将整部短剧拆成成片时间轴 / 剪辑工程
- 将 `.cursor/skills/zy-cinematic-realism` 作为运行时依赖打进发行包

### 1.4 成功标准
1. 剧本、资产、分镜三处均能对同一套规则得到 `prompt_en` + `avoid`
2. Ollama 不可用时自动走云 API，且响应含 `provider`
3. 资产与分镜出图使用注入后的 `negative_prompt`
4. 运行时不依赖造梦师原文文件即可润色与出图

---

## 2. 架构与数据流

```
剧本页 / 资产页 / 分镜页
        │  POST /api/prompts/polish  { stage, input, options }
        ▼
┌───────────────────────────────────────────┐
│  CinematicPolishService                   │
│  - 按 stage 加载 cinematic_v1 pack        │
│  - 调用 LLMProvider                       │
│  - 校验并返回统一结构                       │
└───────────────────────────────────────────┘
        │
        ▼
┌─────────────────┐    失败/超时
│ LLMProvider     │ ──────────────────► Cloud API
│ Ollama（优先）   │
└─────────────────┘
        │
        ▼ 用户确认后写回实体 prompt_en / negative_prompt
生成：AssetQueue → build_workflow(prompt_en, negative_prompt) → ComfyUI
      分镜帧出图复用同一队列
```

要点：
- 规则集中在 pack，页面只传 `stage` 与上下文。
- Cursor 侧 skill 可继续服务开发写稿；产品运行时只读自研 pack。

---

## 3. API 与数据契约

### 3.1 `POST /api/prompts/polish`

请求：

```json
{
  "stage": "script_scene | asset | storyboard_frame",
  "project_id": "...",
  "input": {
    "text_cn": "场景或资产中文描述",
    "text_en": "可选已有英文",
    "context": {
      "title": "可选",
      "type": "character|scene|prop|shot",
      "era_place_mood": "可选固定事实",
      "aspect_ratio": "可选",
      "model": "可选 sdxl|sd15|flux"
    }
  },
  "options": {
    "director": null,
    "return_interpretation": true
  }
}
```

响应：

```json
{
  "interpretation_cn": "画面理解（可关）",
  "prompt_en": "Final Prompt",
  "avoid": "comma-separated negative terms",
  "prompt_cn": "可选短中文摘要",
  "provider": "ollama|cloud",
  "pack_version": "cinematic-v1"
}
```

### 3.2 Stage 差异

| stage | 输入侧重 | 写回 |
|---|---|---|
| `script_scene` | 场戏文/简述 | 画面理解 + `prompt_en` / `avoid` |
| `asset` | 角色/场景/道具 | `prompt_en` + `negative_prompt` |
| `storyboard_frame` | 镜头描述 + 景别/运镜 | 同上 |

首版不提供 `POST /polish/batch`；剧本页若需「本集全部润色」，由前端对每个场景串行调用 `POST /polish`。

剧本页持久化：若 `/api/scripts` 仍为 mock，润色结果先写回前端场景状态（与现 ScriptWorkshop 本地状态一致）；当 scripts API 真实化时，增加场景字段 `prompt_en` / `negative_prompt` / `interpretation_cn` 并对齐写回。资产与分镜必须落后端字段（资产已有真实存储；分镜需将帧模型补上 `negative_prompt` 并持久化到现有分镜存储实现）。

### 3.3 生成相关字段与行为
- Asset / StoryboardFrame 增加 `negative_prompt`（英文，对应 Avoid）
- `build_workflow(model, prompt, negative_prompt)`：正向写入既有节点；负向写入原写死 `"bad quality, blurry"` 的节点（或模板等价位）
- 分镜出图端点固定为：`POST /api/storyboard/{project_id}/frames/{frame_id}/generate`  
  行为：读取该帧 `prompt_en`（必填）与 `negative_prompt`，入 `AssetQueue`（可复用资产队列或同进程等价队列），帧状态 `generating` → `completed|failed`，用现有或对齐资产的轮询方式取 `image_url`

### 3.4 LLM 配置
- 环境变量 / 设置：`OLLAMA_BASE_URL`、本地模型名、`CLOUD_LLM_BASE_URL`、`CLOUD_LLM_API_KEY`、云模型名、超时毫秒
- 降级策略：Ollama 连接失败或超时 → 自动改打云 API；二者皆失败 → 返回可读错误（禁止静默假成功）
- 响应必须带实际使用的 `provider`

---

## 4. 自研 Prompt Pack（商用安全）

- 路径：`backend/app/prompt_packs/cinematic_v1/`
- 内容（自行改写，禁止整文件拷贝造梦师原文）：
  - 工作流步骤（叙事节拍 → 空间 → 机位 → 有动机的光 → 质感 → 场景向 Avoid）
  - 输出契约（与 §3 响应对齐）
  - 负向词选取规则与反「塑料 AI 味」检查要点
- 仓库保留简短 `ATTRIBUTION.md`：说明灵感来源、许可证、未嵌入原文
- 开发用 skill 目录可保留在 `.cursor/skills/`，但不作为运行时必依赖

---

## 5. 前端触点

| 页面 | 交互 | 行为 |
|---|---|---|
| 剧本 | 「电影感拆解」；可选本集批量 | 调 polish；结果进编辑区，用户确认后写回 |
| 资产 | 「润色」；「润色并生成」 | 写回 `promptEn` + `negativePrompt`；生成带负向 |
| 分镜 | 「润色」；「生成此帧」 | 同上；出图轮询对齐资产生成 |

约定：
- 润色结果默认进入可编辑预览，**不静默覆盖**用户原文；需「应用」或「润色并生成」显式确认。
- UI 展示本次 `provider`（本地/云）便于排查。

接通顺序（实现与验收顺序）：**剧本 → 资产 → 分镜 → 生成**。

---

## 6. 错误处理

- LLM 输出缺少 `prompt_en` 或 `avoid`：校验失败；允许自动重试一次；仍失败则报错，不写半截字段覆盖原文。
- Ollama / Cloud 均不可用：HTTP 错误 + 明确文案（如「本地与云端 LLM 均不可用」）。
- 分镜/资产生成：沿用现有队列失败态；负向为空时可用最小安全默认负向（并在日志标明），但润色成功路径应始终带上 Avoid。

---

## 7. 测试要点

- 单元：pack 加载；polish 响应校验；`build_workflow` 负向注入
- 单元：LLMProvider —— mock Ollama 失败后调用云端
- API：`POST /polish` 三种 `stage` 契约
- 集成（无 LLM 环境可 skip）：资产润色后 generate；分镜帧 generate 入队并出图

---

## 8. 注释与实现约定
- 新增关键模块（PolishService、LLMProvider、pack 加载、负向注入）补充必要注释，说明 stage 差异与降级策略。
- 不在本规格引入与润色无关的大范围重构。

---

## 9. 后续可扩展（非本规格）
- `options.director` 强导演模式与按需导演模块
- `POST /polish/batch` 整集场景批量
- RAG 相似案例注入 context
- 视频关键帧 / 运镜提示词 stage
