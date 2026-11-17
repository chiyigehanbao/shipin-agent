# AI 模型后端接入设计（图片优先）

**日期**: 2026-08-09  
**状态**: 已批准（对话确认）  
**前置**: [AI 模型安装设计](./2026-08-09-ai-model-installation-design.md)  
**范围**: VisionForge 后端将 mock 资产生成接到本地 ComfyUI；默认 SDXL，可切换 SD1.5 / Flux GGUF

---

## 1. 目标与边界

### 1.1 目标
- `POST /api/assets/{project_id}/generate` 真实调用 ComfyUI 出图
- 异步任务：立即返回 `generating`，轮询详情拿结果
- 模型可切换：`sdxl`（默认）| `sd15` | `flux`
- `models` 探活指向真实 ComfyUI（`http://127.0.0.1:8188`）

### 1.2 非目标（本规格不做）
- storyboard / render / LTX / MiniMax 视频接入
- TTS（VoxCPM2）/ RAG（bge-m3）/ Ollama 剧本分析
- Redis、多 worker、WebSocket 进度
- 持久化数据库（第一期进程内状态；重启可丢队列）

---

## 2. 架构与数据流

```
前端 / API
  POST /api/assets/{project_id}/generate  (model=sdxl|sd15|flux, 默认 sdxl)
       │
       ▼
  AssetService：建资产记录 status=generating，入队
       │
       ▼
  单 worker（进程内串行）──► ComfyUIClient ──► http://127.0.0.1:8188
       │                      submit / poll / download
       ▼
  写出 {MODELHUB_ROOT}/outputs/assets/{project_id}/{asset_id}.png
  更新 status=completed，image_url=/media/assets/...
  失败 → status=failed + error
```

要点：
- ComfyUI 为独立进程；后端仅 HTTP 调用
- 进程内单 worker 串行，避免 16GB 显存并行 OOM
- 配置项：`COMFYUI_BASE_URL`、`MODELHUB_ROOT`（环境变量，公司机默认 `E:\ModelHub`，家里机 `D:\ModelHub`，可被覆盖）

---

## 3. 模块拆分

| 路径 | 职责 |
|---|---|
| `backend/app/core/settings.py` | `COMFYUI_BASE_URL`、`MODELHUB_ROOT`、输出目录、轮询超时 |
| `backend/app/services/comfyui_client.py` | `health` / `submit_workflow` / `poll_history` / `download_image` |
| `backend/app/services/asset_queue.py` | 进程内队列 + 单 worker；状态机 generating→completed\|failed |
| `backend/app/services/workflows/` | `sd15.json` / `sdxl.json` / `flux_gguf.json` + 填参函数 |
| `backend/app/api/assets.py` | 接真实生成；列表可暂留 mock，详情读进程内仓库 |
| `backend/app/api/models.py` | 图片服务 `api_url→8188`；`test_connection` 探 ComfyUI；反映 queue 长度 |
| `backend/app/main.py` | 挂载 `/media` 静态目录服务生成图 |

可参考（勿整包迁入）：`OpenMontage-main/tools/_comfyui/client.py` 的 submit/poll/download 模式。

---

## 4. API 契约

### 4.1 生成资产
```
POST /api/assets/{project_id}/generate
```

请求体（在现有字段上扩展）：
| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | 资产名称 |
| type | string | character / scene / prop |
| prompt_cn | string | 中文提示词 |
| prompt_en | string | 英文提示词 |
| template_id | string? | 可选，第一期可忽略 |
| model | string? | `sdxl` \| `sd15` \| `flux`，默认 `sdxl` |

响应：`Asset`
- 立即：`status=generating`，`image_url=null`
- 未知 `model` → HTTP 400，不入队

### 4.2 查询资产
```
GET /api/assets/{project_id}/{asset_id}
```

| 字段 | 说明 |
|---|---|
| status | `generating` \| `completed` \| `failed` |
| image_url | `/media/assets/{project_id}/{asset_id}.png` 或 null |
| error | failed 时的简短原因（新增可选字段） |

### 4.3 模型服务
- 图片相关服务（sd / 可拆 flux）的 `api_url` → `http://127.0.0.1:8188`
- `test_connection`：请求 ComfyUI `/system_stats` 或等价健康检查
- `queue`：反映进程内待处理/进行中任务数

### 4.4 填参规则
- 提示词优先 `prompt_en`；为空则用 `prompt_cn`
- 默认分辨率：SDXL 1024、SD1.5 512、Flux 1024（第一期不暴露给 API）
- Workflow 内 checkpoint / unet / clip 文件名与 ModelHub 已落盘文件一致

---

## 5. 错误处理

| 情况 | 行为 |
|---|---|
| ComfyUI 未启动 / 探活失败 | 任务 `failed`，`error=comfyui_unavailable`；models 为 offline |
| 未知 model | HTTP 400 |
| ComfyUI 执行失败 / 超时（默认 10 min） | `failed` + 简短 error；释放 worker |
| 下载输出失败 | `failed`；ComfyUI 输出文件可保留排查 |
| 队列积压 | 仍接受 generate，返回 generating；queue 计数可见 |

---

## 6. 测试与验收

### 6.1 自动化
- 单测：`comfyui_client`（httpx mock）、workflow 填参、队列状态迁移

### 6.2 手工冒烟
1. 启动 ComfyUI：`--lowvram --cpu-vae`（与安装设计一致）
2. 启动后端
3. `POST generate`（默认 sdxl）→ 轮询详情至 `completed` 且图片可访问
4. 再测 `model=sd15`、`model=flux`（Flux 依赖已装 ComfyUI-GGUF）
5. 关掉 ComfyUI 后 generate → `failed` / models offline

### 6.3 验收清单
- [ ] 默认 SDXL 能生成并返回可访问 `image_url`
- [ ] `model=sd15|flux` 可切换
- [ ] ComfyUI 不可用时失败原因可读
- [ ] 同一时刻仅一个生成任务在跑

---

## 7. 与安装计划的关系

| 依赖 | 状态（截至设计时） |
|---|---|
| ComfyUI + GGUF/Manager 节点 | 已部署 |
| SD1.5 / SDXL / Flux 权重 | 已落盘 |
| LTX 全套 | 已落盘（本规格不接入） |
| MiniMax / TTS / RAG | 安装计划后续；本规格不接入 |

后端真实接入对应安装设计 §6，本文件为该后续计划的规格说明。

---

## 8. 后续规格（预留）

1. storyboard 批量出图（复用同一 client + 队列）
2. LTX / MiniMax 视频 workflow
3. TTS / RAG / Ollama 剧本链路
4. 资产与任务持久化
