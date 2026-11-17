# VisionForge Studio AI 模型安装设计文档

**日期**: 2026-08-09  
**项目**: 幻帧工坊 VisionForge Studio  
**状态**: 已批准  
**引擎**: ComfyUI 统一承载图片/视频生成；后端独立调用 TTS / RAG / LLM  
**背景**: 从 mock 数据切换到真实 AI 模型推理  

> 本文档合并并取代已删除的 `2026-08-09-model-hub-install-design.md`。

> **路径约定（重要）**：本文档用占位符 `%MODELHUB_ROOT%` 表示模型根目录，**不写死盘符**。
> 每台机器通过环境变量 `MODELHUB_ROOT` 指向各自的本地实际位置：
> - 公司电脑：`E:\ModelHub`
> - 家里电脑：`D:\ModelHub`
>
> 所有安装脚本、后端配置都应读取 `MODELHUB_ROOT` 环境变量，默认值取公司机 `E:\ModelHub`，可被覆盖。

---

## 0. 硬件约束

- GPU: NVIDIA RTX 5080, 16GB VRAM, Blackwell (sm_120), CUDA 13.1
- 磁盘: 模型所在盘（公司机 `E:\ModelHub`，E 盘剩余约 1.6TB）
- 关键约束: 16GB 显存不足以同时加载两个大视频模型 + LLM + TTS，必须：
  - ComfyUI 使用 `--lowvram` + CPU offload
  - LTX 与 MiniMax 不同时加载
  - 后端任务队列串行化视频/图片生成，避免 OOM
- Blackwell 需 PyTorch >= 2.7 / CUDA >= 12.8；MiniMax 用 NVFP4 量化（Blackwell 原生支持）

---

## 1. 总体目录结构

```
%MODELHUB_ROOT%\
├── comfyui\                       # ComfyUI 引擎(全权承载图片+视频生成)
│   ├── models\
│   │   ├── checkpoints\           # SD 1.5, SDXL
│   │   ├── unet\                  # Flux/LTX/MiniMax 的 GGUF 主模型
│   │   ├── text_encoders\         # Gemma-3-12B、Qwen3VL-32B、T5-XXL 编码器
│   │   ├── vae\                   # LTX 视频/音频 VAE, MiniMax 视频/音频 VAE
│   │   ├── loras\                 # LTX 蒸馏 LoRA, MiniMax Turbo LoRA
│   │   ├── latent_upscale_models\ # LTX 空间放大器
│   │   └── clip\                  # Flux 的 CLIP-L
│   └── custom_nodes\              # ComfyUI-GGUF / -Manager / -LTXVideo / KJNodes
├── llm\                           # ollama 管理(qwen3.5:9b 已装)
├── tts\                           # VoxCPM2
└── embed\                         # bge-m3(RAG 向量模型)
```

---

## 2. 模型清单

| 模块 | 模型 | HuggingFace 源 | 约体积 | ComfyUI 目标目录 |
|---|---|---|---|---|
| 图片 | SD 1.5 (pruned emaonly) | stabilityai/stable-diffusion-1.5 | ~4GB | checkpoints/ |
| 图片 | SDXL base 1.0 | stabilityai/stable-diffusion-xl-base-1.0 | ~6.9GB | checkpoints/ |
| 图片 | Flux.1-dev GGUF Q4 + CLIP-L + T5-XXL GGUF | city96/FLUX.1-dev-gguf | ~10GB | unet/, text_encoders/, clip/ |
| 视频 | LTX-2.3 22B GGUF Q3_K_S + Gemma-3-12B-it 编码器 + 双 VAE + 空间放大器 + 蒸馏 LoRA | unsloth/LTX-2.3-GGUF / Lightricks/LTX-2.3 | ~25GB | unet/, text_encoders/, vae/, loras/, latent_upscale_models/ |
| 视频 | MiniMax-H3 FL2VA NVFP4 + Qwen3VL-32B 编码器 NVFP4/AWQ + 视频 VAE fp16 + 音频 VAE fp32 | Comfy-Org/MiniMax-H3 | ~18GB | unet/, text_encoders/, vae/ |
| TTS | VoxCPM2 (2B, 30 语言, 48kHz) | openbmb/VoxCPM2 | ~5GB | tts/ (后端直接调用,不进 ComfyUI) |
| RAG | bge-m3 多语言向量模型 | BAAI/bge-m3 | ~2.3GB | embed/ (后端 sentence-transformers 加载) |

---

## 3. 下载策略

- 安装 `huggingface_hub` + `hf_transfer` 加速
- 默认直连 HuggingFace
- 失败/超时自动切换镜像：`HF_ENDPOINT=https://hf-mirror.com`
- 使用 `hf download` 命令指定 `--local-dir` 精确落盘
- Flux.1-dev 等 gated 仓库需用户提供 HF token（`huggingface-cli login`）

---

## 4. ComfyUI 环境与自定义节点

| 组件 | 来源/安装方式 |
|---|---|
| ComfyUI 本体 | 克隆 `https://github.com/Comfy-Org/ComfyUI` 或使用便携版 |
| ComfyUI-GGUF | `https://github.com/city96/ComfyUI-GGUF` (必需，跑 GGUF 模型) |
| ComfyUI-Manager | `https://github.com/ltdrdata/ComfyUI-Manager` (管理节点/更新) |
| ComfyUI-LTXVideo | `https://github.com/Lightricks/ComfyUI-LTXVideo` (LTX 官方节点) |
| ComfyUI-KJNodes | `https://github.com/kijai/ComfyUI-KJNodes` (LTX 工作流依赖) |

Python 环境：Python 3.10+，PyTorch 2.7+ (Blackwell/sm_120 支持)，CUDA 12.8+

下载 LTX / MiniMax 官方 workflow JSON 作为模板，供后端参数化提交。

---

## 5. 显存与并发策略 (RTX 5080 16GB)

- ComfyUI 启动参数：`--lowvram --cpu-vae` 强制 CPU offload
- 单次仅加载一个视频模型 (LTX 或 MiniMax)，后端任务队列串行
- 图片生成 (SD/SDXL/Flux) 与视频生成时分复用，不同时驻留
- VoxCPM2 (2B) 与 RAG(bge-m3) 在后端独立推理，不占 ComfyUI 显存
- 监控面板 (backend/monitor.py) 增加显存/队列状态上报

---

## 6. 后端接入改造

### 6.1 models.py 更新
- 将 mock 服务的 `api_url` 全部指向真实服务：
  - sd / flux / ltx / minimax → `http://127.0.0.1:8188` (ComfyUI API)，靠 workflow 区分
  - llm → `http://localhost:11434` (ollama)
  - tts → 后端内部 voxcpm 进程

### 6.2 新增 `comfyui_client.py`
```python
# 核心职责
- submit_workflow(workflow_json, inputs) -> prompt_id
- poll_history(prompt_id) -> output_paths
- download_output(filename) -> bytes
```

### 6.3 API 模块调用点
| 业务 API | 调用方式 |
|---|---|
| `assets.py` (资产生成) | 选 SD/SDXL/Flux workflow，填 prompt + 分辨率 + LoRA |
| `storyboard.py` (分镜) | 同上，批量跨关键帧 |
| `render.py` (成片合成) | 选 LTX/MiniMax workflow，填 prompt/首尾帧/时长/FPS |
| `models.py` (模型配置) | 读取 `%MODELHUB_ROOT%\comfyui\models` 目录扫描可用 checkpoint |

### 6.4 TTS 与 RAG 独立集成
```python
# TTS (backend/tts_client.py)
from voxcpm import VoxCPM
model = VoxCPM.from_pretrained(os.path.join(os.environ.get("MODELHUB_ROOT", r"E:\ModelHub"), "tts", "VoxCPM2"), load_denoiser=False)

# RAG (backend/rag/embedder.py)
from sentence_transformers import SentenceTransformer
embedder = SentenceTransformer(os.path.join(os.environ.get("MODELHUB_ROOT", r"E:\ModelHub"), "embed", "bge-m3"))
```

---

## 7. 磁盘预算

| 类别 | 预估占用 |
|---|---|
| 图片模型 | ~21GB |
| 视频模型 (LTX + MiniMax) | ~43GB |
| TTS + RAG | ~7.5GB |
| ComfyUI 本体 + 节点 + 缓存 | ~5GB |
| **合计** | **~76GB**（不含 ollama 已装的 ~6.6GB） |

D 盘剩余 1 TB，充足。

---

## 8. 实施步骤概览 (供 writing-plans 细化)

1. 准备 %MODELHUB_ROOT% 目录结构
2. 安装 Python 环境 + PyTorch 2.7 + CUDA 12.8
3. 部署 ComfyUI + 必需 custom_nodes
4. 编写下载脚本 (hf download + 镜像 fallback)，逐模型落盘
5. 验证每个模型能在 ComfyUI 加载并跑通基础 workflow
6. 改造 backend/models.py + 新增 comfyui_client.py
7. 改造 assets/storyboard/render 调用 comfyui_client
8. 集成 VoxCPM2 (pip install) + bge-m3 (sentence-transformers)
9. 端到端测试：文本 → 剧本 → 资产图 → 分镜视频 → 成片
10. 文档化常用 workflow JSON 与参数映射

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Flux/MiniMax gated 下载失败 | 提前准备 HF token，配置 `.netrc` 或环境变量 |
| 16GB 显存 OOM | CPU offload + 串行队列；必要时降分辨率/帧数 |
| MiniMax 官方无 GGUF，社区版不稳定 | 优先用 NVFP4 原生 safetensors（Blackwell 支持） |
| ComfyUI 节点版本不兼容 | 锁定 custom_nodes 到已验证 commit，记录在 requirements |
| 视频生成极慢 | 明确接受，用低量化档 |
| VoxCPM2 推理慢 | 支持 Nano-vLLM / vLLM-Omni 加速，后续可接入 |

---

## 10. 验收标准

- [ ] %MODELHUB_ROOT% 目录结构与清单一致
- [ ] ComfyUI 启动无报错，所有 custom_nodes 加载成功
- [ ] 每个模型能独立跑通最小 workflow (txt2img / img2img / txt2video / i2video)
- [ ] 后端 API 能提交 workflow 并拿回产物路径
- [ ] 前端「资产生成/分镜/成片」三步流程端到端通
- [ ] TTS 生成中文语音可播放，RAG 向量检索返回相关文档
