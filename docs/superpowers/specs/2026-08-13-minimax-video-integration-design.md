# MiniMax-H3 视频接入设计（C → A）

**日期**: 2026-08-13  
**状态**: 已批准（对话确认继续）  
**前置**:
- [AI 模型安装设计](./2026-08-09-ai-model-installation-design.md)
- [AI 模型后端接入（图片优先）](./2026-08-09-ai-model-backend-integration-design.md)
- [成片合成：TTS + 分镜静图 slideshow](./2026-08-12-render-tts-slideshow-design.md)

**决策（对话确认）**:
- 路径：**C（后端冒烟出 mp4）→ A（分镜帧图生视频）**
- 引擎：仅 **MiniMax-H3**（本轮不接 LTX）
- 权重档：已落盘的 16GB squeeze 包（`pruned_fp8` + `nvfp4` TE + 双 VAE）
- Comfy 启动保持 `--lowvram`（可选后续加 `--cache-none`）

---

## 1. 目标与边界

### 1.1 目标
1. **阶段 C**：后端能提交 MiniMax T2V workflow，异步出一条可播放 mp4（curl / job 可验收）。  
2. **阶段 A**：分镜已有静图的帧，可一键 I2V（首帧 + `prompt_en`）生成镜头短视频并回写帧状态。  
3. readiness 真实反映 MiniMax 文件是否齐全；模型页不再用假 busy 冒充视频能力。

### 1.2 本规格做
- MiniMax 文件 readiness、workflow 模板、视频产物下载、job 类型 `video_generate`
- `POST /api/videos/{project_id}/generate`（T2V 冒烟入口）
- `POST /api/storyboard/{project_id}/frames/{frame_id}/generate-video`（I2V）
- 与现有图片任务**串行**（同一 worker 或互斥锁），避免 16GB OOM
- 前端分镜：有 `image_url` 时显示「生成镜头视频」+ 轮询（阶段 A）

### 1.3 本规格不做
- LTX / 多视频引擎切换 / Turbo LoRA（可选后续）
- 用 MiniMax 替换 ffmpeg 成片主路径（slideshow 成片仍保留）
- 批量全部分镜自动出视频、视觉一致性比对
- 官方默认满血分辨率（1344×768）作为默认值（16GB 风险高）

---

## 2. 环境前提（已核实）

| 项 | 值 |
|---|---|
| 主模型 | `diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors` |
| 文本编码 | `text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| 视频 VAE | `vae/minimax_h3_video_vae_fp16.safetensors` |
| 音频 VAE | `vae/minimax_h3_audio_vae_fp32.safetensors` |
| 原生节点 | ComfyUI 已暴露 `MiniMaxH3ImageToVideo`、`EmptyMiniMaxH3LatentAV`、`MiniMaxH3SigmaShift`、`SaveVideo` 等 |
| T2V/I2V | 同一节点：不接 `first_frame` → T2V；接分镜图 → I2V |
| length | 帧数，24fps；默认 **124 ≈ 5s**（节点文档网格 17k+5） |

缺任一关键文件 → `minimax.ready=false`，生成接口 400。

---

## 3. 架构与数据流

### 3.1 阶段 C（T2V）

```
POST /api/videos/{project_id}/generate
  { prompt_en, width?, height?, length?, seed? }
       │
       ▼
  readiness(minimax) + Comfy health
       │
       ▼
  job_repo.create(type=video_generate) → job_queue
       │
       ▼
  handler: build_minimax_workflow(mode=t2v)
       → ComfyUIClient.submit → poll history
       → download video bytes → outputs/videos/{pid}/{job_id}.mp4
       → job.result.output_url = /media/videos/...
```

### 3.2 阶段 A（分镜 I2V）

```
POST /api/storyboard/{pid}/frames/{fid}/generate-video
       │
       ▼
  要求 frame.image_url 存在；prompt 用 resolve_frame_prompt_en(frame)
       │
       ▼
  job type=video_generate, payload={frame_id, mode=i2v, first_frame_path, ...}
       │
       ▼
  成功：frame.video_url / video_status=completed
  失败：video_status=failed + error
```

### 3.3 队列与显存
- **图片与视频互斥**：沿用进程内单 job worker；`video_generate` 与 `asset_generate` / `storyboard_generate` 不得并行跑 Comfy。  
- 视频任务超时显著加长（建议默认轮询上限 **30–60 分钟**，可配置）。  
- 生成前可选：若近期刚跑过大图模型，依赖 Comfy `--lowvram` 卸载；不做跨进程强制卸载（第一期）。

---

## 4. API 契约

### 4.1 视频生成（C）

```
POST /api/videos/{project_id}/generate
```

| 字段 | 类型 | 说明 |
|---|---|---|
| prompt_en | string | 必填 |
| width | int | 默认 **960**（32 对齐） |
| height | int | 默认 **544** |
| length | int | 默认 **124**（约 5s）；须符合节点步进 |
| seed | int | 可选 |

响应：
```json
{
  "job_id": "job_...",
  "status": "queued",
  "model": "minimax",
  "mode": "t2v"
}
```

查询：现有 `GET /api/jobs/{job_id}`；`result.output_url` 为 mp4。

错误：
- 400 `model not ready: minimax; missing: ...`
- 400 `prompt_en is required`
- 503 `comfyui_unavailable`

### 4.2 分镜镜头视频（A）

```
POST /api/storyboard/{project_id}/frames/{frame_id}/generate-video
```

| 字段 | 类型 | 说明 |
|---|---|---|
| width/height/length | int | 可选，默认同 C |
| model | string | 固定/仅允许 `minimax`（第一期） |

前置：`image_url` 非空，否则 400 `frame image required`。

帧字段扩展（SQLite / store）：
- `video_url: string | null`
- `video_status: pending | generating | completed | failed`
- `video_error: string | null`
- `video_job_id: string | null`（可选）

### 4.3 readiness

`GET /api/models/readiness` 增加：

```json
"models": {
  "sdxl": ...,
  "sd15": ...,
  "flux": ...,
  "minimax": { "ready": true, "missing_files": [] }
}
```

必查相对 `comfyui/models/`：
- `diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors`
- `text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- `vae/minimax_h3_video_vae_fp16.safetensors`
- `vae/minimax_h3_audio_vae_fp32.safetensors`

### 4.4 模型服务列表
- 新增或改写服务项 `minimax`：`type=video`；`status=online|offline` 跟 Comfy + ready。  
- 现有 `ltx` 保持「权重可装、产品未接入」offline 文案（本轮仍不接 LTX）。

---

## 5. Workflow 与客户端改造

### 5.1 模板来源
1. 在 ComfyUI 用官方 MiniMax H3 模板（或等价原生节点图）跑通一次 T2V。  
2. 导出 **API format** JSON，落入 `backend/app/services/workflows/minimax_t2v.json`。  
3. `build_minimax_workflow(mode, prompt, *, width, height, length, seed, first_frame_name?)` 填参。  
4. I2V：同一图，经 Comfy 上传图像 API（或 `LoadImage` 指向 media 目录可访问路径）接到 `first_frame`。

节点关键路径（以本机 object_info 为准，模板落地时锁定节点 ID）：
- 加载 diffusion / CLIP / 双 VAE  
- `MiniMaxH3ImageToVideo`（prompt + size + length ± first_frame）  
- 采样 + VAE 解码 + `CreateVideo` / `SaveVideo`

### 5.2 ComfyUIClient
现有客户端偏图片；扩展：
- `download_output(filename, subfolder, type)` 或 `download_video(...)`  
- `poll_history` 解析 outputs 中 **视频** 文件名（不只 `images`）  
- 视频任务使用更长的 poll timeout

### 5.3 媒体挂载
- 目录：`{MODELHUB_ROOT}/outputs/videos/`  
- URL：`/media/videos/...`（与现有 `/media` 挂载一致，根已是 `outputs`）

---

## 6. 前端（阶段 A）

- `storyboardApi.generateVideo(projectId, frameId, payload?)`  
- 分镜详情：当 `imageUrl` 存在时显示按钮；`videoStatus===generating` 轮询帧详情  
- 预览区可播 `videoUrl`（`<video controls>`）  
- 阶段 C **可不做前端**（curl + jobs 页即可验收）

---

## 7. 验收标准

### 阶段 C
- [ ] `readiness.models.minimax.ready === true`  
- [ ] `POST /api/videos/{pid}/generate` 返回 job_id  
- [ ] job → `completed`，`result.output_url` 可 `GET` 且 `Content-Type` 为视频，时长约 5s  
- [ ] Comfy 离线时 503；缺文件时 400  

### 阶段 A
- [ ] 有静图的帧可 I2V；无图 400  
- [ ] 成功后帧带 `video_url`，前端可播放  
- [ ] 视频任务与出图任务不会同时占用 Comfy（串行可观察）

### 非目标回归
- [ ] 现有 SDXL 资产/分镜出图与 ffmpeg 成片仍可用  

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 16GB OOM | 默认 960×544、length=124；Comfy `--lowvram --cache-none`；串行队列 |
| `--cpu-vae` 导致 VAEDecode `float != Half` | MiniMax **不要**开 `--cpu-vae`（已改 `start_comfyui.ps1`） |
| 单次极慢（十余分钟级） | 加长 poll；job 进度文案标明「视频生成中」；冒烟可用 length=39 |
| API workflow 节点 ID 漂移 | 模板与本机 Comfy 版本绑定；冒烟失败时先重导模板 |
| 音频 VAE 占用 | 保留官方双 VAE；若 OOM 再评估无声变体（后续） |
| I2V 上传路径 | 优先 Comfy `/upload/image`；失败再试本地 LoadImage |

---

## 9. 实施顺序建议

1. readiness + models 状态文案  
2. 导出并固化 `minimax_t2v.json` + `build_minimax_workflow`  
3. Client 视频下载 + `video_generate` handler + `/api/videos/.../generate`  
4. 阶段 C 冒烟  
5. 帧字段 + generate-video API + 前端按钮（阶段 A）  
6. 阶段 A 冒烟（用已有分镜静图）

---

## 10. 开放问题（默认已选）

| 问题 | 默认 |
|---|---|
| 默认分辨率 | 960×544 |
| 默认时长 | length=124（~5s） |
| 阶段 C 是否做前端页 | 否，API+job 即可 |
| 是否同轮接 LTX | 否 |
