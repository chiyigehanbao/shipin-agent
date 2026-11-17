# 前端模型接线与就绪探测设计

**日期**: 2026-08-10  
**状态**: 已批准（对话确认）  
**前置**:
- [AI 模型安装设计](./2026-08-09-ai-model-installation-design.md)
- [AI 模型后端接入设计](./2026-08-09-ai-model-backend-integration-design.md)

**范围**: 收敛到一条 `master`，把已下载/已接入的图片模型接到前端；资产生成与模型配置页从假交互变为真实可用；未就绪模型不可选。

---

## 1. 目标与边界

### 1.1 目标
- 工作区收敛到一条 `master`（对齐 `origin/master` 上已有 ComfyUI 真实资产生成），不再平行维护多套接入实现。
- 前端真实调用后端：资产生成可选已就绪模型、轮询出图、展示真实图片、支持下载。
- 模型配置页真实探活 ComfyUI（默认 `http://127.0.0.1:8188`），服务状态/队列来自后端；图片模型选项与资产生成一致（`sdxl` | `sd15` | `flux`）。
- 按磁盘文件判断模型是否就绪；未就绪选项灰掉并给出简短原因。
- 本轮新增/改动的关键代码补充**必要注释**（见 §5）。

### 1.2 本规格做
- 合并/对齐已有后端接入成果到 `master`
- 后端：模型就绪探测（覆盖 `sdxl` / `sd15` / `flux` 必需文件）
- 前端：`AssetGeneration` 接线（选模型、生成、轮询、展示、下载）
- 前端：`ModelConfig` 接线（列表/探活/默认 8188/模型选择与 readiness 禁用）
- 未就绪模型禁用 + 可读提示；generate 对未就绪 model 返回 400（双保险）

### 1.3 非目标（本规格不做）
- storyboard / render / scripts / TTS / RAG / LTX / MiniMax 视频真实接入
- 采样步数 / CFG / 采样器 / LoRA 进入 API
- 历史版本、旋转/镜像、确认使用、本地上传、标签、试听
- Redis、数据库持久化、WebSocket 进度
- 模型下载进度 UI（下载仍走现有 ModelHub 脚本/进程）

### 1.4 成功标准
1. ComfyUI 在线时，已就绪模型能生成并显示可访问图片，且可下载
2. 未就绪模型不可选，并提示原因；强行调用 generate 返回 400
3. 模型配置「测试连接」反映真实 online/offline；默认地址 8188
4. 一条 `master` 可跑通，不依赖平行 feature / worktree 分支才能出图

---

## 2. 架构与数据流

```
浏览器
  ├─ ModelConfig ──► GET  /api/models/services
  │                  POST /api/models/services/{id}/test
  │                  GET  /api/models/readiness
  │
  └─ AssetGeneration ──► GET  /api/models/readiness
                         POST /api/assets/{project_id}/generate  { model, ... }
                         GET  /api/assets/{project_id}/{asset_id}  （轮询）
                         展示 image_url → /media/...
                         浏览器直接下载该 URL
                              │
                              ▼
后端（已有）AssetQueue → ComfyUIClient → ComfyUI:8188
                              │
新增 ModelReadiness：检查 MODELHUB / ComfyUI models 约定路径下的权重文件
  → { sdxl|sd15|flux: ready, missing_files[] }
```

要点：
- 生成链路复用已有 ComfyUI 接入与进程内串行队列，不新开并行实现。
- **连接**与**就绪**分离：连接 = ComfyUI 进程可达；就绪 = 该模型必需权重齐全。
- 前端新增薄 API 层（`frontend/src/api/`），页面去掉 `setTimeout` 假成功。
- `MODELHUB_ROOT`、`COMFYUI_BASE_URL` 一律走环境变量/settings，合并后消除 D:/E: 写死冲突。

---

## 3. 模块与 API

### 3.1 后端新增
| 路径 | 职责 |
|---|---|
| `backend/app/services/model_readiness.py` | 按模型检查必需文件；返回 ready / missing_files |
| `GET /api/models/readiness` | 暴露就绪状态，供前端 Select 禁用 |

就绪规则（与现有 workflow 文件名对齐）：
| 模型 | 必需文件（相对 ComfyUI `models/` 约定布局） |
|---|---|
| `sdxl` | `checkpoints/sd_xl_base_1.0.safetensors` |
| `sd15` | `checkpoints/v1-5-pruned-emaonly.safetensors` |
| `flux` | `unet/flux1-dev-Q4_K_S.gguf` + `text_encoders/t5-v1_1-xxl-encoder-Q4_K_S.gguf` + `clip/clip_l.safetensors` + `vae/ae.safetensors` |

缺任一文件 → 该模型 `ready=false`，并列出 `missing_files`。

### 3.2 后端小改（已有接口）
- `GET/POST /api/models/services*`：图片相关 `api_url` 默认 `COMFYUI_BASE_URL`（8188）；`sd` 的 status/queue 来自真实 health + 队列深度；`test` 真实探活
- `POST /api/assets/{project_id}/generate`：若 `model` 未就绪 → HTTP 400，不入队
- 合并后统一 settings 中的 `MODELHUB_ROOT` 环境变量读取

### 3.3 前端
| 路径 | 职责 |
|---|---|
| `frontend/src/api/client.js` | axios 实例，走 Vite `/api` 代理 |
| `frontend/src/api/assets.js` | generate / getAsset |
| `frontend/src/api/models.js` | listServices / testConnection / getReadiness |
| `pages/workbench/AssetGeneration.jsx` | readiness → 模型 Select；generate + 轮询；展示图；下载 |
| `pages/admin/ModelConfig.jsx` | services + test；默认 8188；模型选项与 readiness 对齐 |

**下载**：不新增后端接口；对已完成资产的 `image_url` 用浏览器下载（`<a download>` 或 fetch blob）。

### 3.4 readiness 响应示例
```json
{
  "models": {
    "sdxl": { "ready": true, "missing_files": [] },
    "sd15": { "ready": true, "missing_files": [] },
    "flux": { "ready": false, "missing_files": ["vae/ae.safetensors"] }
  },
  "comfyui_online": true
}
```

---

## 4. 错误处理

| 情况 | 行为 |
|---|---|
| ComfyUI 未启动 | `sd` status=offline；测试连接失败；generate 任务 `failed`（如 `comfyui_unavailable`） |
| 模型文件未齐 | readiness `ready=false` + `missing_files`；前端禁用；generate → 400 |
| 生成超时 / ComfyUI 执行失败 | 资产 `failed` + 简短 `error`；前端停止轮询并提示 |
| 轮询中刷新页面 | 用 `asset_id` 再拉详情；进程内状态，后端重启后旧任务可能丢失（沿用后端接入规格） |
| ltx / llm / tts | 本轮仍可展示条目，但不伪装为已真实接入视频/LLM/TTS（探活与状态不误导） |

---

## 5. 代码注释约定

本轮新增与关键改动代码须加**必要注释**，要求：
- **注释写「为什么 / 约定」**，不写复述代码的废话。
- 必须注释的位置：
  1. `model_readiness`：每个模型的文件清单来源（对应哪个 workflow）、路径如何相对 `MODELHUB_ROOT` / ComfyUI `models/`
  2. 前端轮询：间隔、停止条件（completed/failed）、超时
  3. 合并相关的 settings / 环境变量：`MODELHUB_ROOT`、`COMFYUI_BASE_URL` 的用途与默认值
  4. 未就绪禁用与 generate 400 双保险的意图（一句话即可）
- 不要求给每个函数每行加注释；不新增与本规格无关的大段文档字符串噪音。

---

## 6. 分支合并策略

1. 本地 `master` 对齐 `origin/master`（已有真实 generate + 部分 `AssetGeneration` 接线）。
2. 本规格增量只在 `master` 上开发与提交。
3. 以 `master` 为唯一权威；平行 worktree / feature 接入分支完成合并后不再作为第二套实现维护，避免再分叉。

---

## 7. 测试与验收

### 7.1 自动化
- 单测：`model_readiness`（临时目录分别造「文件齐全」与「缺文件」场景）

### 7.2 手工冒烟
1. 启动 ComfyUI（`--lowvram --cpu-vae`）与后端（`MODELHUB_ROOT` 指向本机 ModelHub）
2. 打开模型配置：测试连接反映真实状态；默认 URL 为 8188
3. 资产生成：仅已就绪模型可选；默认/选择 `sdxl` 生成 → 出图 → 下载
4. 人为制造/确认 Flux 缺 `ae.safetensors` 时选项禁用且有原因
5. 关闭 ComfyUI → offline；生成失败可读

### 7.3 验收清单
- [ ] 工作区以 `master` 可跑通，不依赖平行 feature 分支
- [ ] 已就绪模型：生成 → 可访问图片 → 可下载
- [ ] 未就绪模型：Select 禁用 + 原因；generate 返回 400
- [ ] ModelConfig 测试连接真实；默认 8188
- [ ] 关键新代码含 §5 要求的必要注释

---

## 8. 与既有规格的关系

| 既有能力 | 本规格 |
|---|---|
| ComfyUI 资产生成（sdxl/sd15/flux） | 复用，不重写队列/client |
| `/media` 静态输出 | 复用，前端直接展示/下载 |
| storyboard / render / TTS / RAG | 仍非目标 |
| 模型安装 / 下载脚本 | 不改；本规格只**读**磁盘判断就绪 |

---

## 9. 后续（预留，本规格不做）
1. 采样参数 / LoRA 进 workflow
2. 资产确认使用、本地上传、历史版本
3. 分镜批量出图、视频链路
4. 任务持久化与 WebSocket 进度
