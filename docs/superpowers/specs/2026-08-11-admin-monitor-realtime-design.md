# 管理运维真实化：监控快照 + 顶栏 GPU/任务 + LLM 多云配置

**日期**: 2026-08-11  
**状态**: 已批准（对话确认 ok）；实现计划见 `docs/superpowers/plans/2026-08-11-admin-monitor-realtime.md`  
**前置**:
- [AI 模型后端接入设计](./2026-08-09-ai-model-backend-integration-design.md)
- [前端模型接线与就绪探测设计](./2026-08-10-frontend-model-wiring-design.md)
- [工作台真实化：LLM 可运维 + SQLite 持久化 + 剧本扩写设计](./2026-08-11-workbench-persistence-llm-design.md)

**背景问题**:
1. 监控面板完全用本地假数据抖动，不请求 `/api/monitor`；后端 `monitor.py` 亦为 mock。  
2. 顶栏硬编码 `GPU 78%` 与任务角标 `2`，无温度、无真实队列。  
3. ModelConfig 中 GPU/队列等仍有写死装饰；Ollama 模型名靠手填，未列本机已装模型。  
4. 云端 LLM 仅单组 base_url/key/model；用户需要先配 DeepSeek，并可新建、切换多条云端配置。  

**决策（对话确认）**:
- 范围 = **监控面板 + 顶栏** + **管理运维面**（ModelConfig 去假 / SystemSettings 精简）；提示词持久化与 RAG **另开规格**。  
- 顶栏 GPU 展示 **`温度 · 占用率`**（如 `62°C · 78%`）；无卡时明确「不可用」，不假装数值。  
- 任务提醒 = **生成队列（进行中/排队）+ 失败任务**；可看列表与错误摘要，并可跳转工作台。  
- 存储根目录沿用 **`MODELHUB_ROOT`**（输出 `{MODELHUB_ROOT}/outputs`）；设置页展示生效路径，本轮不另开第三套根目录写接口。  
- Ollama：真实列出本机模型，可选中写入生效配置。  
- 云端：多条 profile + **一条当前启用**；调用顺序 **Ollama → 当前云端**。  
- 并发控制、界面设置、日志与数据：**保留现状**（不接真、不扩写）。  
- 架构方案 **A**：统一 Monitor 快照 API + 扩展现有 `llm_settings`；短轮询，不上 WebSocket。

---

## 1. 目标与边界

### 1.1 目标
1. 顶栏与监控页共用真实 **系统/GPU/服务/任务** 快照。  
2. 任务角标反映真实进行中/排队/失败数；下拉可查看并跳转。  
3. SystemSettings / ModelConfig 的 LLM 区：本机 Ollama 模型列表 + 多云端 profile CRUD 与「当前启用」。  
4. 路径区只读展示 `MODELHUB_ROOT`、输出目录、SQLite 路径（便于确认机器配置）。  

### 1.2 本规格做
| 区域 | 交付 |
|---|---|
| 后端 Monitor | `GET /api/monitor/snapshot`（可保留旧 `/system` `/tasks` 作薄封装或弃用并改指向）；GPU 经 `nvidia-smi`；任务来自 AssetStore/队列 |
| 前端 Header | 轮询快照；展示 `°C · %`；任务 Badge + Dropdown |
| 前端 MonitorDashboard | 去掉假 `setInterval` 抖动；接 `monitorApi.snapshot` |
| LLM 配置 | `cloud_profiles` + `active_cloud_id`；兼容迁移旧单云字段；`GET` Ollama tags |
| ModelConfig | SD 队列/状态继续用已有 models API；去掉写死 GPU%；LLM Tab 接多 profile + Ollama 列表 |
| SystemSettings | LLM 同上；路径只读；并发/界面/日志保持装饰性现状 |

### 1.3 非目标
- 提示词模板 DB 持久化、RAG 真实化  
- WebSocket / SSE 推送  
- 改写 `MODELHUB_ROOT` 的 GUI 写接口（仍用 `.env` / 环境变量改根目录）  
- 并发上限真正限制 `AssetQueue` worker 数（保留 UI 摆设）  
- 视频模型（LTX/Wan）真实队列与 GPU 分卡调度  
- 暂停/恢复/取消任意历史任务的完整调度器（本轮失败任务以列表展示为主；进行中任务不强制实现 pause）  
- 多用户权限、远程 Agent 上报  

### 1.4 成功标准
1. 有 NVIDIA 驱动时，顶栏显示真实温度与占用；监控页 GPU 卡片一致；无 GPU 或 `nvidia-smi` 失败时显示「不可用」且不伪造 78%。  
2. 资产生成排队/进行中时，顶栏角标与监控「实时任务」同步增加；失败资产出现在失败列表且含 `error` 摘要。  
3. `ollama list` 有的模型出现在设置下拉中，选中并保存后润色/扩写使用该模型名。  
4. 可新增 DeepSeek 与其它 OpenAI 兼容 profile，切换「当前启用」后，Ollama 不可用时降级到该 profile。  
5. 并发/界面/日志区块行为与现网一致（可继续假保存 toast），不引入半真半假写接口。  

---

## 2. 架构与数据流

```
MainLayout (轮询 3–5s) ──┐
MonitorDashboard ────────┼──► GET /api/monitor/snapshot
                         │         │
                         │         ├─ host: cpu/mem/disk (psutil 或等价)
                         │         ├─ gpu: nvidia-smi 查询（失败 → available=false）
                         │         ├─ services: 复用 models 探活逻辑（ComfyUI / 可选 LLM ping 摘要）
                         │         └─ tasks: AssetStore 中 generating + 近期 failed
                         │
SystemSettings / ModelConfig LLM
  ├─ GET/PUT /api/settings/llm     （扩展 profiles）
  ├─ GET /api/settings/llm/ollama/models  → Ollama /api/tags
  └─ POST /api/settings/llm/test   （对当前生效配置探活）

润色 / 扩写
  └─ build_llm_provider() → effective: ollama_* + active cloud profile
```

要点：
- **单一快照真相**：顶栏与监控不各自拼装多接口。  
- **任务范围**：本机资产/分镜生成链路（`AssetStore` 状态）；不包含成片/TTS mock 任务。  
- **LLM 配置文件**：继续 `backend/data/llm_settings.json`（已在 gitignore 的 data 目录），不把 api_key 写入 git。  

---

## 3. Monitor 快照

### 3.1 响应形状（契约）

```json
{
  "ts": "2026-08-11T22:00:00",
  "host": {
    "cpu_percent": 12.5,
    "memory_percent": 48.0,
    "disk_percent": 35.0
  },
  "gpu": {
    "available": true,
    "name": "NVIDIA GeForce RTX 4070",
    "temperature_c": 62,
    "utilization_percent": 78,
    "memory_used_mb": 4200,
    "memory_total_mb": 12282,
    "error": null
  },
  "services": {
    "comfyui": { "online": true, "queue": 1 },
    "ollama": { "online": true, "model": "qwen2.5:7b" }
  },
  "tasks": {
    "badge_count": 3,
    "generating": [ { "id": "...", "project_id": "...", "name": "...", "type": "character", "status": "generating", "model": "sdxl", "error": null, "created_at": "..." } ],
    "pending_note": "本机资产队列串行；pending 体现在 generating 等待与 queue 深度",
    "failed_recent": [ { "id": "...", "project_id": "...", "name": "...", "type": "scene", "status": "failed", "model": "sdxl", "error": "comfyui_unavailable", "created_at": "..." } ]
  }
}
```

说明：
- `badge_count` = `len(generating)` + `len(failed_recent)`（`failed_recent` 默认最近 N 条，N=20，或仅「未确认」；本轮采用 **最近 20 条 failed**，简单可测）。  
- 若后续需要「已读」清除角标，另开规格；本轮角标随失败记录自然存在于近期窗口。  
- `pending_note` 为文档字段可选；前端可不展示。当前 `AssetQueue` 多为串行，`queue_depth()` 已有，快照中 `services.comfyui.queue` 使用现有 `store.queue_depth() + queue.pending_count()` 逻辑。

### 3.2 GPU 采集
- Windows/本机：调用 `nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits`（超时短，如 2s）。  
- 解析失败 / 未安装 / 非零退出 → `available=false`，`error` 可读短句，数值字段 `null`。  
- 多卡：本轮取 **第一张卡**（index 0）；不在 UI 做选卡。  

### 3.3 Host 采集
- 优先 `psutil`（若未在 requirements，本规格允许新增依赖）；失败则 host 百分号为 `null` 且不拖垮整个 snapshot。  

### 3.4 旧接口
- `GET /api/monitor/system`、`/tasks`、pause/resume/cancel：本轮可改为基于 snapshot 的兼容层，或返回 410/明确 mock 弃用。**推荐**：`/system` 映射 snapshot 的 host+gpu.utilization；`/tasks` 映射 generating+failed；pause/resume/cancel **保持 501 或「未实现」**，监控页去掉假装有效的暂停按钮，或按钮点击提示未实现。  

---

## 4. 顶栏与监控前端

### 4.1 MainLayout
- `monitorApi.snapshot()` 每 3–5s 轮询（页面可见时）；卸载清除 timer。  
- GPU 文案：  
  - 可用：`{temp}°C · {util}%`  
  - 不可用：`GPU 不可用`（status-dot 灰色/红色）  
- 「任务」：`Badge count={badge_count}`；点击 Dropdown/Popover 列出 generating 与 failed_recent；项可 `navigate(/workbench/{project_id}/assets)`（分镜失败可进 storyboard，若 `type` 不足以区分则统一进 assets，规格选定：**统一跳资产页**，简单）。  

### 4.2 MonitorDashboard
- 挂载拉取 snapshot，同间隔刷新。  
- 系统概览：cpu/mem/disk/gpu（温度与占用分开展示或卡片副标题温度）。  
- 模型服务：以 `services` + 可选继续调 `modelsApi.services()` 补齐 SD/Flux 文案；**禁止**随机抖动假数据。  
- 任务队列：渲染 snapshot.tasks；去掉假 pause/resume 或改为 disabled+tooltip。  

### 4.3 api.js
- 新增 `monitorApi.snapshot()`。  

---

## 5. LLM 配置扩展

### 5.1 文件结构（`llm_settings.json`）

```json
{
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_model": "qwen2.5:7b",
  "llm_timeout_sec": 60,
  "active_cloud_id": "deepseek",
  "cloud_profiles": [
    {
      "id": "deepseek",
      "name": "DeepSeek",
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "...",
      "model": "deepseek-chat"
    }
  ]
}
```

### 5.2 迁移
- 若文件仍是旧扁平字段（`cloud_llm_base_url` / `cloud_llm_api_key` / `cloud_llm_model`）：读取时自动迁成一条 `id=legacy` profile，设为 `active_cloud_id`，写回新结构（或仅内存兼容、下次 save 固化）。  
- `get_effective()` 输出仍喂给现有 `LLMProvider`：从 active profile 填 `cloud_llm_*`。  
- `get_public()`：返回 ollama 字段、profiles（**key 掩码**）、`active_cloud_id`；不回传完整 key。  

### 5.3 API
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/settings/llm` | 公钥配置 + profiles 掩码 |
| PUT | `/api/settings/llm` | 更新 ollama_*、timeout、active_cloud_id、profiles（整表或增量；空 key 表示不改该 profile 的 key） |
| POST | `/api/settings/llm/test` | 当前生效配置探活 |
| GET | `/api/settings/llm/ollama/models` | 代理 Ollama `GET {base}/api/tags`，返回 `[{name}]`；Ollama 不可达 → 502 |

环境变量仍作**默认底**；JSON 覆盖。用户提供的 DeepSeek 作为默认预置 profile 模板（无 key 时 `api_key_set=false`），不把真实 key 写进仓库。

### 5.4 前端
- SystemSettings LLM 区：Ollama URL + 模型 **Select（来自 tags）** + 云端 profile 列表（新增/删除/设为当前）+ 测试连接。  
- ModelConfig LLM Tab：同一 API，避免两套状态长期分叉（允许复制最小逻辑，YAGNI 不强制抽 hook）。  
- 并发/界面/日志：不改行为。  
- 存储路径：只读展示 `MODELHUB_ROOT`、`outputs`、`resolved_sqlite_path`（需后端 GET 增加 `paths` 字段或小接口 `GET /api/settings/paths`）。**推荐**挂在 `GET /api/settings/llm` 旁：`GET /api/settings/paths` 返回只读路径，避免塞进 LLM 响应。  

---

## 6. ModelConfig 去假数据

- SD Tab：继续 `modelsApi.services/readiness/test`；展示的 queue 用接口返回值；**删除写死 GPU 45%**，可改为展示 snapshot.gpu 或「见监控面板」。  
- LTX/TTS：保持「尚未真实接入」提示，不假装 online。  
- 保存：LLM Tab 走 `settingsApi.putLlm`；其它 Tab 不假装写入后端路径。  

---

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| nvidia-smi 失败 | snapshot.gpu.available=false；顶栏「GPU 不可用」 |
| psutil 缺失/失败 | host 字段 null；前端显示 — |
| Ollama tags 失败 | 模型下拉空 + message；仍允许手填模型名（Input 兜底或 Select 可 mode=tags） |
| 无 active cloud 且 Ollama 挂 | test/润色 502，文案沿用「本地与云端 LLM 均不可用」 |
| snapshot 请求失败 | 顶栏保持上次成功值或显示离线；不回退到假 78% |

---

## 8. 测试

- **GPU 解析**：对固定 `nvidia-smi` stdout fixture 单测。  
- **snapshot**：mock host/gpu/store，断言 badge_count 与 failed 列表。  
- **LLM profiles**：迁移旧字段；active profile 进入 `effective_llm_kwargs`；public 不泄露 key。  
- **Ollama models API**：respx mock `/api/tags`。  
- **回归**：既有 polish / expand / asset_queue / settings_llm 测试仍通过。  

---

## 9. 实现顺序建议

1. GPU + host 采集纯函数与 snapshot API  
2. 前端 monitorApi + MonitorDashboard + MainLayout  
3. llm_settings profiles 迁移与 API / Ollama tags / paths  
4. SystemSettings + ModelConfig LLM UI  
5. 去掉监控假暂停与 ModelConfig 写死 GPU；README 一句更新  

---

## 10. 规格关系

本规格补齐「管理中心运维 + 监控」真实链路；**不撤销**工作台持久化与电影感润色已交付能力。提示词/RAG 真实化不在此文档范围。
