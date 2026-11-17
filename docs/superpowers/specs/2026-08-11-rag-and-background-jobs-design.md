# RAG 真实化 + 工作台后台任务设计

**日期**: 2026-08-11  
**状态**: 待用户审阅规格  
**前置**:
- [工作台真实化：LLM + SQLite + 剧本扩写](./2026-08-11-workbench-persistence-llm-design.md)
- [管理运维真实化：监控 + 顶栏任务](./2026-08-11-admin-monitor-realtime-design.md)
- [电影感提示词润色融合](./2026-08-10-cinematic-prompt-polish-design.md)
- [AI 模型安装（含 bge-m3）](./2026-08-09-ai-model-installation-design.md)

**背景问题**:
1. RAG 管理页与 `/api/rag` 全程 mock，无向量库、无入库、无工作台引用。  
2. 剧本扩写 / 解析 / 电影感润色等 LLM 调用在前端页面内同步等待；切路由或关组件会中断体验（请求可能仍在飞，但 UI 状态丢失且无统一任务可见性）。  
3. 资产生成虽有 `AssetQueue`，但与 LLM 任务未统一到同一「任务中心」；顶栏任务目前主要来自资产 generating。  
4. 用户需要：点击生成后可去别的页面，任务在后端继续；回来能看到是否在生成；完成后有应用内提醒。

**决策（对话确认）**:
- 范围切分 **C**：同一规格、分 Phase——**先统一后台 Job，再 RAG 闭环**。  
- 后台覆盖 **工作台凡会转圈等待的生成**（扩写/解析/润色单场与批量/资产生成/分镜出图等）。  
- RAG 做完整闭环 **C**：管理页真实化 + 润色/扩写自动检索注入 + 满意结果可沉淀入库。  
- 提醒采用 **应用内**：顶栏任务角标/列表 + **页面常驻「进行中任务」条**；不做浏览器系统通知（本规格非目标）。  
- 架构采用 **统一 Job 表 + 短轮询**（不上 WebSocket/SSE）。

---

## 1. 目标与边界

### 1.1 目标
1. 工作台生成操作改为「提交即返回」；后端持久化任务并执行，与前端路由生命周期解耦。  
2. 任意页面可感知进行中任务；回到来源页可刷新结果；完成/失败有应用内提示。  
3. RAG：案例可持久、可语义检索；扩写/润色可注入相似案例；成功结果可入库沉淀。  

### 1.2 本规格做

| Phase | 交付 |
|---|---|
| **1 后台 Job** | SQLite `jobs` 表；Job API（创建/列表/详情）；LLM worker + 复用/桥接 AssetQueue；扩写、解析、润色、出图统一挂 Job；前端提交改异步 + 顶栏任务源切换为 jobs + 常驻进行中条 + 完成 toast |
| **2 RAG** | `rag_cases` 元数据 + 本地向量库（Chroma）+ bge-m3 embedding；管理页接真实 API；`search` 真实语义检索；扩写/润色 pipeline 注入 top-k；工作台「一键入库」+ 可选半自动建议入库 |

### 1.3 非目标
- 浏览器系统通知（Notification API）  
- WebSocket / SSE  
- Celery / Redis / 多机队列  
- 提示词模板库 DB 化（与 RAG 案例库分开；本规格不改模板管理页为真）  
- 成片 Render / TTS 真实化（若 UI 有假生成，可不接入 Job；接入则仅占位类型，不实现引擎）  
- 任务暂停/恢复完整调度；取消可选做「标记 cancel 请求」，不保证立即停 LLM  
- 多用户权限、跨设备同步  
- 自动全量把历史项目灌进 RAG（仅用户确认或明确触发的入库）  

### 1.4 成功标准
1. 点「AI 扩写」后立即离开剧本页，任务仍在跑；顶栏与常驻条显示进行中；完成后 toast，回页可见场景与完整剧本。  
2. 电影感拆解（单场/本集）同样不因切页丢失；结果写回场景后可刷新看到。  
3. 资产生成/分镜出图出现在同一任务列表，与 LLM 任务一致可见。  
4. 后端进程存活期间，刷新浏览器不丢进行中任务可见性（从 API 拉取）。  
5. RAG 管理页统计/列表/检索测试为真数据；空库时检索返回空而非假相似分。  
6. 扩写或润色请求中，若库中有相似案例，prompt 含注入片段；一键入库后可再次检索到。  

### 1.5 进程重启约定
- 后端启动时：将所有 `queued` / `running` 的 Job **标记为 `failed`**，`error=server_restarted`（不做断点续跑）。  
- 同步将对账：状态仍为 `generating` 的资产/分镜帧 **标为 `failed`**，`error=server_restarted`，避免顶栏永久悬挂；不尝试接管重启前已提交给 ComfyUI 的 prompt。

---

## 2. 架构与数据流

```
浏览器
  ├─ 工作台操作 ──► POST /api/jobs  (type, project_id, payload)
  │                    └─► 立即 200 { id, status: queued, ... }
  ├─ MainLayout / 常驻条 ──► GET /api/jobs?status=active  (轮询 2–5s)
  ├─ 完成检测 ──► 本地已知 job 变 completed/failed → antd notification/message
  └─ 回页 ──► 既有 listScenes / listAssets / frames API 拉最新结果

JobWorker(s)
  ├─ script_expand / script_analyze → ScriptExpandService → SceneRepository
  ├─ prompt_polish / prompt_polish_batch → polish service → 写回 Scene/Asset/Frame
  └─ asset_generate / storyboard_generate → 入队 AssetQueue（Job 状态跟随资产）

Monitor snapshot.tasks
  └─ 以 jobs 表为准：active（queued+running）+ 近期 failed（含 title/error/link_path）

RAG
  ├─ 管理页 ──► /api/rag/cases|stats|search
  ├─ Embedder(bge-m3) + Chroma collection
  ├─ expand/polish 执行前 retrieve(query) → 注入 LLM context
  └─ POST /api/rag/ingest  ← 工作台一键入库
```

要点：
- **真相在后端**：Job 与业务实体（scenes/assets）均持久化；前端不把「进行中」只存在组件 state。  
- **提交与执行分离**：HTTP 只负责入队；耗时在 worker 线程/异步任务中。  
- **轮询统一**：复用现有顶栏短轮询习惯；常驻条共用同一 jobs 列表。  
- **RAG 只读注入、写要确认**：检索可自动；入库需用户动作（一键），避免污染知识库。  

### 2.1 实现顺序（强制）
1. **Phase 1** — jobs 表 + API + worker + 前端异步与 UI  
2. **Phase 2** — embedder + Chroma + RAG API + 管理页 + 注入 + 入库  

---

## 3. Phase 1：后台 Job

### 3.1 数据模型 `jobs`

| 字段 | 说明 |
|---|---|
| id | 主键 |
| type | 见下表 |
| project_id | 可空（全局任务极少；本规格均带项目） |
| status | `queued` \| `running` \| `completed` \| `failed` \| `cancelled` |
| progress | 0–100，可选 |
| title | 展示用短标题（如「剧本扩写」「场景3 电影感拆解」） |
| payload_json | 创建时入参 |
| result_json | 成功摘要（如 scene_count、asset_id），非完整大文本 |
| error | 失败信息 |
| link_path | 前端跳转路径，如 `/workbench/{id}/script` |
| created_at / started_at / finished_at | 时间戳 |

**type 枚举（本规格必须支持）**:
- `script_expand`
- `script_analyze`
- `prompt_polish`（单目标：scene/asset/frame + id）
- `prompt_polish_batch`（本集全部等）
- `asset_generate`
- `storyboard_generate`

### 3.2 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/jobs` | 创建任务并入队；body: `{ type, project_id, payload }` |
| GET | `/api/jobs` | 列表；query: `status=active\|all`、`project_id`、`limit`；`active` = queued+running |
| GET | `/api/jobs/{id}` | 详情 |
| POST | `/api/jobs/{id}/cancel` | 尽力取消：queued 可直接 cancelled；running 设 cancel 标志，worker 检查点退出（LLM 可能仍跑完当前调用，结果可丢弃不写库） |

兼容策略：
- 现有 `POST /api/scripts/expand|analyze`、`POST /api/prompts/polish` 保留为 **可供 worker 调用的同步实现**；前端工作台 **只走 Job API**，不再长时间 await 同步接口。  
- 资产生成：现有 generate 接口在创建/更新资产为 generating 后 **同时创建/关联 Job**，避免两套互不知晓。

### 3.3 Worker
- 进程内守护线程（与 `AssetQueue` 同模式）：`POST /api/jobs` 写 SQLite 后推入内存队列；worker 只消费内存队列。启动时先执行 §1.5 对账，不把旧 queued 重新入队。  
- LLM 类任务：**串行 1**（避免本机 Ollama 打爆）；出图仍走现有单 worker `AssetQueue`，Job 状态随资产完成/失败更新。  
- Job `running` 时更新 progress（扩写可用阶段性进度 10→30→90，完成 100；出图可映射队列位置）。  
- 成功：写业务表 + `completed` + result 摘要。  
- 失败：`failed` + error；不吞异常。  

### 3.4 前端 UX
1. **提交**：按钮 loading 仅到「已入队」；随后依赖任务条/顶栏。  
2. **常驻条**：主布局 **内容区顶部** 固定一条（无 active job 时隐藏）：标题、状态、简要进度、点击跳转 `link_path`。  
3. **顶栏任务**：继续轮询 snapshot，但 `tasks` 已来自 jobs；保留跳转 `link_path`。  
4. **完成提醒**：前端维护「已知 active ids」集合；轮询发现变为 completed/failed → `notification`（成功/失败文案 + 可选「前往查看」）。  
5. **回页刷新**：剧本/资产/分镜页在挂载时拉列表；该页所属 `project_id` 若有 job 刚变为 completed，触发一次强制 refetch。  

### 3.5 与监控面板
- `GET /api/monitor/snapshot` 的 `tasks` **切换**为 jobs 视角（active + 近期 failed）。  
- 监控页「实时任务」用 snapshot.tasks。  
- 常驻进行中条与完成检测统一用 `GET /api/jobs?status=active`（以及必要时按 id 查详情）；不与另一套资产列表混源。

---

## 4. Phase 2：RAG

### 4.1 存储
- **元数据**：SQLite `rag_cases`（id, title, type, style, description, tags_json, prompt_en, negative_prompt, source_project_id, source_ref, rating, usage_count, created_at, updated_at）。  
- **向量**：本地 Chroma 持久目录固定为 `{MODELHUB_ROOT}/rag/chroma`；collection 名固定 `vf_cases`。  
- **Embedding**：`bge-m3`，路径遵循安装规格（`%MODELHUB_ROOT%/embed/...`）；启动懒加载；缺失时 RAG search/ingest 返回明确错误，不假装相似度。  

### 4.2 API（替换 mock）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/rag/stats` | 真实计数 |
| GET | `/api/rag/cases` | 筛选/分页 |
| POST | `/api/rag/cases` | 手动新增（管理页） |
| DELETE | `/api/rag/cases/{id}` | 删元数据 + 向量 |
| POST | `/api/rag/search` | body: `{ query, top_k, type? }` → 真实相似度 |
| POST | `/api/rag/ingest` | 从工作台实体入库：`{ source_type, project_id, ref_id, title?, tags? }` |

### 4.3 检索注入
- **触发点**：`script_expand` / `script_analyze` / `prompt_polish*` 在调用 LLM 前。  
- **query**：用户创意文本、场面 description、或中英提示词拼接（截断到合理长度）。  
- **top_k**：默认 3；无结果则不注入、不打断主流程。  
- **注入格式**：系统或 user 附加「参考案例（仅风格与结构，勿照抄）」+ 案例 title/description/prompt 摘要。  
- **usage_count**：被注入选用时 +1（可选，简单实现即可）。  

### 4.4 入库（沉淀）
- 工作台在场景/资产「用户满意」路径提供 **「存入知识库」** 按钮（一键调用 ingest）。  
- 半自动：任务 `completed` 的 notification 可带「存入知识库」次要按钮（仅对 polish/资产类有意义时显示）。  
- **不做**静默全自动入库。  
- 入库文本：优先 `prompt_en` + `interpretation_cn` / description；type 映射 character/scene/prop/storyboard/technique。  

### 4.5 管理页
- `RAGKnowledge.jsx` 去掉写死 cases；接真实 API。  
- 检索测试区调用真实 `search`。  
- 空状态文案：说明「完成创作后可一键入库」。  

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| Ollama/云不可用 | Job `failed`，error 含现有 LLMProvider 可读信息 |
| ComfyUI 不可用 | 出图 Job/资产 failed，与现网一致 |
| bge-m3 未安装 | ingest/search 返回 **503** + 明确文案；扩写/润色降级为无 RAG 注入并打日志 |
| Chroma 损坏 | 启动或首次访问报错；提供文档级「删除 chroma 目录重建」（实现可不做 GUI 一键修复） |
| 重复提交扩写 | 允许新 Job；前端若发现同 project 同 type 已有 active，先 `Modal.confirm` 提示「已有进行中任务，仍要再提交？」再 POST |

---

## 6. 测试要点

**Phase 1**
- 创建 expand job → 轮询至 completed → DB 中 scenes 已更新。  
- 创建后不 wait，直接 GET jobs active 可见。  
- 模拟 worker 内异常 → failed + error。  
- 重启后 queued/running → failed `server_restarted`。  
- 前端：mock 轮询状态变化触发 notification（单测或手工清单）。  

**Phase 2**
- ingest 两条 → search 命中且 similarity 合理排序。  
- 空库 search → `[]`。  
- polish/expand 在有案例时 prompt 含参考块（单测 mock retrieve）。  
- 删除 case 后 search 不再命中。  

---

## 7. 文档与 README
- 更新根 README / backend README「当前状态」：后台 Job + RAG 已真实；成片/TTS/系统通知仍非目标。  
- `.env.example` 增加 RAG 路径/模型名（若需要）。  

---

## 8. 非目标回顾（防范围蔓延）
本规格不借机：重做成片流水线、TTS、WebSocket、提示词模板中心、多用户、浏览器推送、自动全库灌数。

---

## 9. 对话决策摘要
| 项 | 选择 |
|---|---|
| 规格切分 | C：同规格，先 Job 后 RAG |
| 后台覆盖面 | 工作台所有转圈生成 |
| RAG 深度 | 管理 + 注入 + 一键沉淀 |
| 提醒形态 | 顶栏 + 常驻进行中条 + 完成 toast（无系统通知） |
| 架构 | Job 表 + 轮询；Chroma + bge-m3 |
