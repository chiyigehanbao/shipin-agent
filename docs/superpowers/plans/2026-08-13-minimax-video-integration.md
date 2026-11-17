# MiniMax-H3 Video Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 阶段 C 用 MiniMax-H3 异步出可播 mp4；阶段 A 把 I2V 接到分镜帧。

**Architecture:** 程序化构建 Comfy API graph（对齐官方 H3 节点：UNETLoader + CLIPLoader(type=minimax) + MiniMaxH3ImageToVideo + SamplerCustomAdvanced + VAEDecode/VAEDecodeAudio + CreateVideo + SaveVideo）。`video_generate` 走现有 JobQueue 串行；扩展 ComfyUIClient 解析/下载视频输出。

**Tech Stack:** FastAPI、现有 JobQueue、ComfyUI HTTP、pytest

**Spec:** `docs/superpowers/specs/2026-08-13-minimax-video-integration-design.md`

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/services/model_readiness.py` | 增加 `minimax` 必查文件 |
| `backend/app/services/workflows/minimax.py` | `build_minimax_workflow(...)` 程序化构图 |
| `backend/app/services/comfyui_client.py` | poll 视频产物 + download_output |
| `backend/app/services/video_generate.py` | 提交/轮询/落盘 mp4 |
| `backend/app/services/job_handlers.py` | 处理 `video_generate` |
| `backend/app/api/videos.py` | `POST /api/videos/{pid}/generate` |
| `backend/app/api/models.py` | 服务列表增加 minimax |
| `backend/app/api/jobs.py` | 注册 job 类型文案 |
| `backend/app/main.py` | 挂载 videos router |
| `backend/app/api/storyboard.py` + frames schema | 阶段 A：generate-video + video_* 字段 |
| `frontend/.../Storyboard.jsx` + `api.js` | 阶段 A 按钮与预览 |

---

### Task 1: minimax readiness

**Files:**
- Modify: `backend/app/services/model_readiness.py`
- Modify: `backend/tests/test_model_readiness.py`

- [ ] 增加 REQUIRED_FILES["minimax"] 四文件
- [ ] 测试：齐则 ready；缺 VAE 则 missing
- [ ] 跑 pytest 通过

### Task 2: build_minimax_workflow

**Files:**
- Create: `backend/app/services/workflows/minimax.py`
- Create: `backend/tests/test_minimax_workflow.py`

- [ ] 实现 T2V 图（无 first_frame）；I2V 带 LoadImage
- [ ] 默认 960×544、length=124、steps=20、sampler=res_multistep（若不存在则 euler）、scheduler=simple
- [ ] 测试：节点类型齐全、prompt/尺寸写入、I2V 含 LoadImage

### Task 3: ComfyUIClient 视频输出

**Files:**
- Modify: `backend/app/services/comfyui_client.py`
- Create/Modify: `backend/tests/test_comfyui_client_video.py`

- [ ] `poll_history` 支持 images / gifs / videos；或新增 `poll_history_media`
- [ ] `download_output` 通用 /view 下载
- [ ] 测试用假 history 覆盖视频键

### Task 4: video_generate 服务 + job + API（阶段 C）

**Files:**
- Create: `backend/app/services/video_generate.py`
- Create: `backend/app/api/videos.py`
- Modify: `job_handlers.py`, `jobs.py`, `main.py`, `models.py`
- Test: `backend/tests/test_videos_generate_api.py`

- [ ] API：校验 prompt、readiness、health → 入队
- [ ] handler：build → submit → poll(长超时) → 写 `{media}/videos/{pid}/{job_id}.mp4`
- [ ] models 列表加 minimax；ltx 保持未接入
- [ ] 单测 mock client/health

### Task 5: 阶段 C 实机冒烟

- [ ] readiness minimax ready
- [ ] POST generate → job completed → GET /media/videos/... 200
- [ ] 记录耗时/是否 OOM；失败则降分辨率或 length 再试

### Task 6: 阶段 A 分镜 I2V

**Files:**
- frames repo/schema + storyboard API + FE
- Test: generate-video 无图 400；有图入队

- [ ] 帧字段 video_url/status/error
- [ ] upload 首帧到 Comfy → I2V workflow
- [ ] 前端按钮 + video 预览

---

## Defaults

- width=960, height=544, length=124, fps=24, steps=20
- poll timeout_sec=3600
- filename_prefix=`vf_minimax`
