# 工作台真实化：LLM 可运维 + SQLite 持久化 + 剧本扩写设计

**日期**: 2026-08-11  
**状态**: 已批准（对话确认：方案 1；顺序 C→A→B；SQLite；扩写后润色仍手动）  
**前置**:
- [AI 模型后端接入设计](./2026-08-09-ai-model-backend-integration-design.md)
- [前端模型接线与就绪探测设计](./2026-08-10-frontend-model-wiring-design.md)
- [电影感提示词润色融合设计](./2026-08-10-cinematic-prompt-polish-design.md)

**背景问题（用户反馈）**:
1. 新建项目不留存  
2. 剧本工坊「AI 扩写」仍是虚拟进度与写死场景  
3. 电影感拆解无法使用（环境/配置未接通）  
4. 误以为「全部真实接入」已完成——前几轮规格将项目 DB、剧本 LLM 列为非目标；本规格补齐这些缺口  

**范围**: 在已有 ComfyUI 出图与电影感润色 API 之上，按 **C 润色可运维可跑 → A SQLite 元数据持久化 → B 剧本真实扩写** 打通；图片仍落本地磁盘，库中只存路径与文本，刷新/重启后仍能看到项目、提示词与图片预览。

---

## 1. 目标与边界

### 1.1 目标
- **C**：电影感润色真正可用——Ollama/云配置可持久、可从管理页生效，失败有可读原因。  
- **A**：项目 / 场景 / 分镜帧 / 资产**元数据**写入 SQLite；`image_url` 指向已有 `/media/...` 文件，预览不丢。  
- **B**：剧本「AI 扩写 / 解析」调用真实 LLM（复用 `LLMProvider`），场景列表写入 SQLite；「电影感拆解」仍手动点。  

### 1.2 本规格做
| 阶段 | 交付 |
|---|---|
| C | `backend/.env.example`；LLM 配置读写 API；管理页 LLM 表单接线；模型名与文档对齐；润色失败文案可排查 |
| A | SQLite 库；Project/Scene/StoryboardFrame/Asset 表；替换内存 mock stores；前端 `projectsApi` + 列表/创建接线；去掉纯前端硬编码项目 seed 作为唯一真相 |
| B | `ScriptWorkshop` 去掉 `setTimeout` 假扩写；调用真实 `/api/scripts/expand`（及可选 analyze）；后端用 LLM 生成场景并落库 |

### 1.3 非目标
- 图片二进制入数据库（继续磁盘）  
- PostgreSQL / 多用户权限 / 云同步  
- 扩写后自动批量电影感润色  
- 成片 / TTS / RAG / 视频模型真实化  
- 一致性检测算法真实化（可保持 mock）  
- 导演库 / 造梦师原文嵌入  

### 1.4 成功标准
1. 配置好 Ollama 或云 Key 后，三页「电影感拆解/润色」返回 `prompt_en`+`avoid`，不再无配置时静默假成功。  
2. 新建项目 → 刷新浏览器 → 重启后端 → 项目仍在列表中。  
3. 剧本扩写得到 LLM 生成的场景并入库；刷新后场景与提示词字段仍在。  
4. 资产生成/分镜出图后，重启仍能通过元数据中的 `image_url` 预览磁盘图片（文件本身未被删）。  

---

## 2. 架构与数据流

```
浏览器
  ├─ 管理页 LLM 配置 ──► GET/PUT /api/settings/llm
  ├─ 项目列表/创建    ──► /api/projects（SQLite）
  ├─ 剧本扩写/解析  ──► /api/scripts/expand|analyze → LLMProvider → Scene 行
  ├─ 电影感润色     ──► /api/prompts/polish → LLMProvider → 写回 Scene/Asset/Frame
  ├─ 资产生成       ──► /api/assets/.../generate → AssetQueue → 磁盘 PNG + Asset 行
  └─ 分镜出图       ──► /api/storyboard/.../generate → 同上 + Frame 行更新 image_url
                              │
                    ┌─────────┴─────────┐
                    │ SQLite (元数据)    │
                    │ projects/scenes/   │
                    │ frames/assets      │
                    └─────────┬─────────┘
                              │ image_url 仅存路径
                    MODELHUB_ROOT/outputs/... (图片文件)
```

要点：
- **单一真相**：项目与工作台实体以 SQLite 为准；前端 Zustand 只做当前会话缓存，不再用硬编码列表冒充项目库。  
- **LLM**：继续 Ollama 优先、失败降级云；扩写与润色共用 `LLMProvider`。  
- **图片**：只存路径；不把 PNG 写入 SQLite。  

### 2.1 实现与验收顺序（强制）
1. **Phase C** — 润色可运维可跑  
2. **Phase A** — SQLite + 项目/资产/分镜元数据 + 前端项目接线  
3. **Phase B** — 剧本扩写/解析真实化并写场景表  

---

## 3. Phase C：润色可运维

### 3.1 配置源
- 环境变量 / `.env`（已有 `settings.py` 字段）为底。  
- 新增可写配置文件（建议 `backend/data/llm_settings.json` 或 SQLite `app_settings` 表），**覆盖**同名 settings 默认值（进程内热更新或下次请求读取）。  
- 提供 `backend/.env.example`，写明：
  - `OLLAMA_BASE_URL`、`OLLAMA_MODEL`（与本机 `ollama list` 对齐，文档默认改为可配置，避免写死与安装文档不一致的模型名）  
  - `CLOUD_LLM_BASE_URL`、`CLOUD_LLM_API_KEY`、`CLOUD_LLM_MODEL`、`LLM_TIMEOUT_SEC`  

### 3.2 API
- `GET /api/settings/llm` → 当前生效配置（**不回传完整 api_key**，可回传 `api_key_set: bool` 与掩码）  
- `PUT /api/settings/llm` → 更新本地可写配置并立即对后续 `LLMProvider` 生效  
- 可选：`POST /api/settings/llm/test` → 发一条极短 chat，返回 `provider` 与成功/失败原因  

### 3.3 前端
- `SystemSettings` / `ModelConfig` 中 LLM 相关表单改为读写上述 API，不再是装饰性输入。  
- 润色失败时展示后端 `detail`（如「本地与云端 LLM 均不可用」）。  

### 3.4 验收
- 仅启 Ollama 且模型存在 → 润色 `provider=ollama`  
- 停 Ollama、配好云 → `provider=cloud`  
- 都不可用 → 502 + 可读文案；UI 不假成功  

---

## 4. Phase A：SQLite 持久化

### 4.1 库位置
- 默认：`{MODELHUB_ROOT}/shipin-agent.db` 或 `backend/data/shipin-agent.db`（settings 可配 `database_url` / `sqlite_path`）。  
- 启动时建表：使用标准库 `sqlite3` + 薄 repository 层（不引入 SQLAlchemy，降低依赖面）；schema 版本用单表 `schema_migrations` 记录。  

### 4.2 表（最小字段）

**projects**  
`id, name, type, description, style, status, progress, episode_count, current_step, created_at, updated_at`

**scenes**（剧本场景）  
`id, project_id, number, name, location, time, characters_json, props_json, description, description_en, prompt_cn, prompt_en, negative_prompt, interpretation_cn, dialogue_count, narration_count, created_at, updated_at`

**assets**  
`id, project_id, name, name_en, type, status, prompt_cn, prompt_en, negative_prompt, model, image_url, error, created_at, updated_at`

**storyboard_frames**  
`id, project_id, number, description, description_en, character, scene, shot_type, angle, movement, duration, prompt_cn, prompt_en, negative_prompt, status, image_url, asset_id, model, error, created_at, updated_at`

说明：
- `characters_json` / `props_json` 存 JSON 数组字符串即可。  
- `image_url` 为相对媒体路径（如 `/media/assets/{project_id}/{asset_id}.png`），文件在 `MODELHUB_ROOT/outputs`。  

### 4.3 后端改造
- 用 SQLite repository 替换：
  - `projects.py` 的 `mock_projects`  
  - `AssetStore` 内存 dict（或 store 底层改为 DB）  
  - `StoryboardStore` 内存 dict  
  - scripts 场景列表改为读 `scenes` 表  
- 启动时**不再依赖**前端硬编码 seed 作为唯一数据；可选提供「空库时插入一条演示项目」开关，默认关闭或明确标注演示。  
- 资产生成 / 分镜出图成功后 **UPDATE DB** 中 `status`、`image_url`、`error`。  

### 4.4 前端改造
- 新增 `projectsApi`（list/create/get/update/delete）。  
- `ProjectCreate` / 项目列表页改为调 API，成功后再写入 Zustand 当前项目缓存。  
- `projectStore.projects` 改为从 API 加载，删除「永远存在的假项目」作为权威来源。  
- 剧本页场景、分镜帧、资产列表以项目 ID 为维度从后端拉取；本地 seed 仅作 API 失败时的临时降级（并 toast 提示）。  

### 4.5 验收
- 创建项目 → F5 → 仍在。  
- 重启后端 → 仍在。  
- 生成一张资产图 → 重启 → 列表仍显示，点击可预览磁盘图。  
- 分镜帧同理。  

---

## 5. Phase B：剧本真实扩写

### 5.1 行为
- 「AI 扩写剧本」：前端 `POST /api/scripts/expand`（或带 `project_id` 的项目作用域端点），body 含创意文本、风格等。  
- 后端用 `LLMProvider` + **自研剧本扩写 system prompt**（非造梦师整包拷贝），要求模型返回严格 JSON 场景数组。  
- 校验后 **写入 `scenes` 表**（可先删该项目旧场景或按策略替换），返回场景列表。  
- 「解析剧本」：`/analyze` 对上传/粘贴长文本做同样落库（可与 expand 共用解析器，input 类型不同）。  
- **不**在扩写成功后自动调用 polish；用户仍点「电影感拆解」再写 `prompt_en` / `negative_prompt`。  

### 5.2 前端
- 删除 `handleGenerateScript` / `handleParseScript` 的假 `setInterval` 进度作为唯一实现。  
- 改为真实请求 + loading；成功后 `setScenes` 来自 API，并与 DB 一致。  
- 保留进度 UI 可以改为不确定进度条或真实阶段文案（「正在调用本地模型…」）。  

### 5.3 验收
- 输入创意 → 得到多场非写死场景 → 刷新后仍在。  
- 对某场点电影感拆解 → 应用后 `prompt_en`/`negative_prompt` 入库 → 刷新仍在。  
- LLM 不可用时错误可见，不假装扩写成功。  

---

## 6. API 契约摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/PUT | `/api/settings/llm` | LLM 配置 |
| POST | `/api/settings/llm/test` | 可选探活 |
| GET/POST | `/api/projects` | 列表/创建 |
| GET/PUT/DELETE | `/api/projects/{id}` | 详情/更新/删除 |
| GET | `/api/scripts/{project_id}/scenes` | 场景列表 |
| POST | `/api/scripts/expand` | 扩写并落库（需 `project_id`） |
| POST | `/api/scripts/analyze` | 解析并落库 |
| 已有 | `/api/prompts/polish` | 润色（写回由前端/后续 PUT 场景接口完成） |
| PUT | `/api/scripts/{project_id}/scenes/{scene_id}` | 应用润色字段 |
| 已有 | `/api/assets/...`、`/api/storyboard/...` | 改为读写 SQLite |

（精确字段在实现计划中与现有 Pydantic 模型对齐；本规格要求 `project_id` 贯穿场景/资产/分镜。）

---

## 7. 错误处理
- LLM 双端失败：502 + 明确文案；前端 `message.error`。  
- SQLite 写入失败：500 + 不破坏已落盘图片。  
- 扩写 JSON 非法：自动重试一次（同 polish 模式），仍失败则 502，不写半截场景。  
- 图片文件缺失但 DB 有 `image_url`：列表仍显示记录，预览处显示「文件缺失」而非整页崩溃。  

---

## 8. 测试要点
- Phase C：settings 读写；mock LLMProvider 的 test 端点；polish 在无 key 时 502。  
- Phase A：projects CRUD 重启后仍在（临时 DB 文件）；asset/frame 更新 image_url 持久。  
- Phase B：expand mock LLM 返回固定 JSON → 场景行写入；前端不再依赖假 setTimeout（可用组件/契约测或 API 测）。  
- 回归：既有 polish / workflow negative / storyboard generate / assets negative 单测保持通过。  

---

## 9. 注释与实现约定
- 新增 DB 访问层、settings 覆盖、scripts LLM 扩写处补充必要注释。  
- 不借机重做成片/RAG/监控页。  
- README「全部 mock」描述需在实现后改为与真实能力一致的简短说明（可作本规格附带文档任务）。  

---

## 10. 后续可扩展（非本规格）
- 扩写后一键批量润色  
- 多用户与云端 DB  
- WebSocket 进度  
- 成片/TTS/视频管线  
