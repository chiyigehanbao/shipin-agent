# AI Model Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **路径约定（重要）**：本计划用 `%MODELHUB_ROOT%` 表示模型根目录（环境变量 `MODELHUB_ROOT`），不写死盘符。
> 公司电脑 = `E:\ModelHub`；家里电脑 = `D:\ModelHub`。执行前先设好环境变量：
> ```powershell
> $env:MODELHUB_ROOT = "E:\ModelHub"   # 公司机；家里机换 D:\ModelHub
> ```
> 代码片段默认值取 `E:\ModelHub`（公司机），可被环境变量覆盖。仓库脚本路径用 `%REPO_ROOT%` 占位（即本仓库根目录，如 `D:\AAA\AIgc\aishipin-local`），不写死旧路径。

**Goal:** 在 `%MODELHUB_ROOT%` 部署 ComfyUI、必需自定义节点，并按设计文档下载图片/视频/TTS/RAG 模型，验证目录与 ComfyUI 可启动。

**Architecture:** Model 权重与 ComfyUI 引擎落在 `%MODELHUB_ROOT%`（与仓库分离）。仓库内仅新增可重复执行的安装/下载脚本与清单。本计划不改造后端 API；后端 `comfyui_client` / `models.py` 真实接入作为后续计划。

**Tech Stack:** Python 3.13、PyTorch 2.7+ (CUDA 12.8)、ComfyUI、huggingface_hub / hf_transfer、PowerShell、ollama（已装 qwen3.5:9b）

**Spec:** `docs/superpowers/specs/2026-08-09-ai-model-installation-design.md`

**范围边界（本计划完成后即可验收的部分）:**
- ✅ ModelHub 目录、ComfyUI、custom_nodes、全部模型落盘
- ✅ ComfyUI 能启动且节点加载无致命错误
- ❌ 后端 API / 前端端到端（另开计划）

---

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/modelhub/paths.py` | ModelHub 根路径与子目录常量（读 `MODELHUB_ROOT` 环境变量） |
| `scripts/modelhub/manifest.py` | 模型清单：repo、文件、目标目录 |
| `scripts/modelhub/hf_download.py` | 带镜像 fallback 的下载函数 |
| `scripts/modelhub/download_all.py` | CLI：按模块下载 |
| `scripts/modelhub/setup_dirs.ps1` | 创建 `%MODELHUB_ROOT%` 目录树 |
| `scripts/modelhub/setup_comfyui.ps1` | 克隆 ComfyUI、venv、torch、节点 |
| `scripts/modelhub/start_comfyui.ps1` | 以 `--lowvram --cpu-vae` 启动 |
| `scripts/modelhub/tests/test_paths.py` | 路径与清单单元测试 |
| `scripts/modelhub/tests/test_hf_download.py` | 镜像 fallback 逻辑测试（mock） |
| `%MODELHUB_ROOT%\...` | 实际引擎与权重（不进 git） |

---

### Task 0: 前置检查（HF Token + 磁盘）

**Files:** 无代码变更

- [ ] **Step 1: 确认 GPU 与磁盘**

Run:
```powershell
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
Get-PSDrive E | Select-Object Used,Free
```
Expected: RTX 5080 ~16GB；模型所在盘（公司机 E 盘）剩余 >> 100GB

- [ ] **Step 2: 确认 / 配置 HuggingFace Token**

若尚未登录，请用户在 https://huggingface.co/settings/tokens 创建 token，并接受 gated 模型协议：
- https://huggingface.co/black-forest-labs/FLUX.1-dev（Flux 相关）
- https://huggingface.co/Lightricks/LTX-2.3（若要求）

Run:
```powershell
pip install -U "huggingface_hub[cli]" hf_transfer
huggingface-cli login
huggingface-cli whoami
```
Expected: 打印用户名，无 401

- [ ] **Step 3: 记录环境变量（当前会话）**

```powershell
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"
# 直连失败时脚本会自动切镜像；也可手动：
# $env:HF_ENDPOINT = "https://hf-mirror.com"
```

---

### Task 1: ModelHub 路径模块与目录脚本

**Files:**
- Create: `scripts/modelhub/paths.py`
- Create: `scripts/modelhub/setup_dirs.ps1`
- Create: `scripts/modelhub/tests/test_paths.py`
- Create: `scripts/modelhub/__init__.py`

- [ ] **Step 1: 写失败测试**

```python
# scripts/modelhub/tests/test_paths.py
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modelhub.paths import MODELHUB_ROOT, REQUIRED_DIRS


def test_modelhub_root():
    # 默认取公司机 E:\ModelHub；也可用环境变量 MODELHUB_ROOT 覆盖
    assert MODELHUB_ROOT == Path(os.environ.get("MODELHUB_ROOT", r"E:\ModelHub"))


def test_required_dirs_include_comfy_model_folders():
    names = {p.name for p in REQUIRED_DIRS}
    for need in {
        "checkpoints", "unet", "text_encoders", "vae",
        "loras", "latent_upscale_models", "clip",
        "custom_nodes", "tts", "embed", "llm",
    }:
        assert need in names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest scripts/modelhub/tests/test_paths.py -v`  
Expected: FAIL（`module modelhub` / `paths` 不存在）

- [ ] **Step 3: 实现 paths 与空 init**

```python
# scripts/modelhub/__init__.py
"""ModelHub install helpers."""

# scripts/modelhub/paths.py
import os
from pathlib import Path

MODELHUB_ROOT = Path(os.environ.get("MODELHUB_ROOT", r"E:\ModelHub"))

COMFYUI_ROOT = MODELHUB_ROOT / "comfyui"
COMFY_MODELS = COMFYUI_ROOT / "models"

REQUIRED_DIRS = [
    COMFYUI_ROOT / "custom_nodes",
    COMFY_MODELS / "checkpoints",
    COMFY_MODELS / "unet",
    COMFY_MODELS / "text_encoders",
    COMFY_MODELS / "vae",
    COMFY_MODELS / "loras",
    COMFY_MODELS / "latent_upscale_models",
    COMFY_MODELS / "clip",
    MODELHUB_ROOT / "llm",
    MODELHUB_ROOT / "tts",
    MODELHUB_ROOT / "embed",
]


def ensure_dirs() -> list[Path]:
    created: list[Path] = []
    for d in REQUIRED_DIRS:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(d)
        else:
            d.mkdir(parents=True, exist_ok=True)
    return created
```

```powershell
# scripts/modelhub/setup_dirs.ps1
$ErrorActionPreference = "Stop"
python -c "from pathlib import Path; import sys; sys.path.insert(0, r'%REPO_ROOT%\scripts'); from modelhub.paths import ensure_dirs, MODELHUB_ROOT; ensure_dirs(); print('OK', MODELHUB_ROOT)"
Get-ChildItem -Recurse "$env:MODELHUB_ROOT" -Directory | Select-Object FullName
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest scripts/modelhub/tests/test_paths.py -v`  
Expected: PASS

- [ ] **Step 5: 创建目录**

Run: `powershell -ExecutionPolicy Bypass -File scripts/modelhub/setup_dirs.ps1`  
Expected: 打印 `OK E:\ModelHub`（或环境变量覆盖后的路径）及子目录列表

- [ ] **Step 6: Commit**

```powershell
git add scripts/modelhub/__init__.py scripts/modelhub/paths.py scripts/modelhub/setup_dirs.ps1 scripts/modelhub/tests/test_paths.py
git commit -m "feat(modelhub): add ModelHub path constants and dir setup"
```

---

### Task 2: 模型清单 + HF 下载（镜像 fallback）

**Files:**
- Create: `scripts/modelhub/manifest.py`
- Create: `scripts/modelhub/hf_download.py`
- Create: `scripts/modelhub/download_all.py`
- Create: `scripts/modelhub/tests/test_hf_download.py`

- [ ] **Step 1: 写 fallback 失败测试**

```python
# scripts/modelhub/tests/test_hf_download.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modelhub.hf_download import download_file


def test_download_retries_with_mirror_on_failure(tmp_path):
    calls = []

    def fake_hf_hub_download(**kwargs):
        endpoint = kwargs.get("_endpoint") or "official"
        calls.append(endpoint)
        if len(calls) == 1:
            raise ConnectionError("timeout")
        return str(tmp_path / "file.bin")

    with patch("modelhub.hf_download.hf_hub_download", side_effect=fake_hf_hub_download):
        with patch.dict("os.environ", {}, clear=False):
            path = download_file(
                repo_id="org/model",
                filename="file.bin",
                local_dir=tmp_path,
            )
    assert Path(path).name == "file.bin"
    assert len(calls) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest scripts/modelhub/tests/test_hf_download.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 manifest + hf_download + CLI**

```python
# scripts/modelhub/manifest.py
from dataclasses import dataclass
from pathlib import Path
from .paths import COMFY_MODELS, MODELHUB_ROOT


@dataclass(frozen=True)
class ModelFile:
    module: str          # image | video-ltx | video-minimax | tts | embed
    repo_id: str
    filename: str        # HF 仓库内相对路径；空字符串表示整仓
    dest_dir: Path
    note: str = ""


MANIFEST: list[ModelFile] = [
    # --- Image: SD 1.5 ---
    ModelFile(
        "image",
        "Comfy-Org/stable-diffusion-v1-5-archive",
        "v1-5-pruned-emaonly.safetensors",
        COMFY_MODELS / "checkpoints",
        "SD 1.5 pruned",
    ),
    # --- Image: SDXL ---
    ModelFile(
        "image",
        "stabilityai/stable-diffusion-xl-base-1.0",
        "sd_xl_base_1.0.safetensors",
        COMFY_MODELS / "checkpoints",
        "SDXL base",
    ),
    # --- Image: Flux GGUF + encoders ---
    ModelFile(
        "image",
        "city96/FLUX.1-dev-gguf",
        "flux1-dev-Q4_K_S.gguf",
        COMFY_MODELS / "unet",
        "Flux.1-dev Q4_K_S",
    ),
    ModelFile(
        "image",
        "Comfy-Org/flux1-dev",
        "split_files/clip/clip_l.safetensors",
        COMFY_MODELS / "clip",
        "Flux CLIP-L",
    ),
    ModelFile(
        "image",
        "city96/t5-v1_1-xxl-encoder-gguf",
        "t5-v1_1-xxl-encoder-Q4_K_S.gguf",
        COMFY_MODELS / "text_encoders",
        "T5-XXL GGUF Q4",
    ),
    # --- Video: LTX-2.3 (主 GGUF；配套文件用整仓关键路径，执行时按 note 核对) ---
    ModelFile(
        "video-ltx",
        "unsloth/LTX-2.3-GGUF",
        "LTX-2.3-22b-Q3_K_S.gguf",
        COMFY_MODELS / "unet",
        "LTX-2.3 22B Q3_K_S — 若文件名在 HF 上不同，用 hf list 核对后改 manifest",
    ),
    ModelFile(
        "video-ltx",
        "Lightricks/LTX-2.3",
        "",
        COMFY_MODELS / "_staging_ltx23",
        "整仓下载后由 download_all 按后缀分发到 vae/loras/text_encoders/latent_upscale_models",
    ),
    # --- Video: MiniMax-H3 ---
    ModelFile(
        "video-minimax",
        "Comfy-Org/MiniMax-H3",
        "",
        COMFY_MODELS / "_staging_minimax",
        "整仓下载后按 NVFP4/VAE 文件名分发到 unet/text_encoders/vae",
    ),
    # --- TTS / RAG ---
    ModelFile(
        "tts",
        "openbmb/VoxCPM2",
        "",
        MODELHUB_ROOT / "tts" / "VoxCPM2",
        "VoxCPM2 整仓",
    ),
    ModelFile(
        "embed",
        "BAAI/bge-m3",
        "",
        MODELHUB_ROOT / "embed" / "bge-m3",
        "bge-m3 整仓",
    ),
]
```

```python
# scripts/modelhub/hf_download.py
from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

MIRROR = "https://hf-mirror.com"


def download_file(repo_id: str, filename: str, local_dir: Path) -> str:
    """下载单文件；直连失败则切 hf-mirror 重试一次。"""
    local_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
    )
    try:
        return hf_hub_download(**kwargs)
    except Exception as first:
        os.environ["HF_ENDPOINT"] = MIRROR
        try:
            return hf_hub_download(**kwargs)
        except Exception:
            raise first


def download_repo(repo_id: str, local_dir: Path) -> str:
    """整仓 snapshot；直连失败则切镜像重试。"""
    local_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        repo_id=repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
    )
    try:
        return snapshot_download(**kwargs)
    except Exception as first:
        os.environ["HF_ENDPOINT"] = MIRROR
        try:
            return snapshot_download(**kwargs)
        except Exception:
            raise first
```

```python
# scripts/modelhub/download_all.py
"""Usage:
  python -m modelhub.download_all --module image
  python -m modelhub.download_all --module video-ltx
  python -m modelhub.download_all --module all
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .hf_download import download_file, download_repo
from .manifest import MANIFEST, ModelFile
from .paths import COMFY_MODELS, ensure_dirs


def _dispatch_ltx_staging(staging: Path) -> None:
    """按扩展名/关键词把 LTX 配套文件拷到 ComfyUI 标准目录。"""
    mapping = [
        (("vae", ".safetensors"), COMFY_MODELS / "vae"),
        (("lora", ".safetensors"), COMFY_MODELS / "loras"),
        (("upscale",), COMFY_MODELS / "latent_upscale_models"),
        (("gemma", "text_encoder", "encoder"), COMFY_MODELS / "text_encoders"),
    ]
    for path in staging.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        for keys, dest in mapping:
            if any(k in name for k in keys):
                dest.mkdir(parents=True, exist_ok=True)
                target = dest / path.name
                if not target.exists():
                    shutil.copy2(path, target)
                break


def _dispatch_minimax_staging(staging: Path) -> None:
    for path in staging.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if "vae" in name:
            dest = COMFY_MODELS / "vae"
        elif any(x in name for x in ("qwen", "text_encoder", "encoder")):
            dest = COMFY_MODELS / "text_encoders"
        elif any(x in name for x in ("nvfp4", "unet", "diffusion", "fl2va", ".safetensors")):
            dest = COMFY_MODELS / "unet"
        else:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / path.name
        if not target.exists():
            shutil.copy2(path, target)


def download_one(item: ModelFile) -> None:
    print(f"==> [{item.module}] {item.repo_id} :: {item.filename or '(snapshot)'} -> {item.dest_dir}")
    if item.filename:
        download_file(item.repo_id, item.filename, item.dest_dir)
    else:
        download_repo(item.repo_id, item.dest_dir)
        if item.dest_dir.name == "_staging_ltx23":
            _dispatch_ltx_staging(item.dest_dir)
        if item.dest_dir.name == "_staging_minimax":
            _dispatch_minimax_staging(item.dest_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--module",
        default="all",
        choices=["all", "image", "video-ltx", "video-minimax", "tts", "embed"],
    )
    args = parser.parse_args()
    ensure_dirs()
    items = [
        m for m in MANIFEST
        if args.module == "all" or m.module == args.module
    ]
    for item in items:
        download_one(item)
    print("DONE", args.module)


if __name__ == "__main__":
    main()
```

修复测试以匹配真实签名（`download_file` 在第二次调用前设置 `HF_ENDPOINT`）：

```python
# scripts/modelhub/tests/test_hf_download.py （最终版）
from pathlib import Path
from unittest.mock import patch
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modelhub import hf_download


def test_download_retries_with_mirror_on_failure(tmp_path):
    calls = {"n": 0}

    def fake_hf_hub_download(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("timeout")
        return str(tmp_path / "file.bin")

    with patch.object(hf_download, "hf_hub_download", side_effect=fake_hf_hub_download):
        # 清掉可能残留的 endpoint
        os.environ.pop("HF_ENDPOINT", None)
        path = hf_download.download_file("org/model", "file.bin", tmp_path)
    assert Path(path).name == "file.bin"
    assert calls["n"] == 2
    assert os.environ.get("HF_ENDPOINT") == hf_download.MIRROR
```

- [ ] **Step 4: 安装依赖并跑测试**

Run:
```powershell
pip install -U pytest huggingface_hub hf_transfer
cd %REPO_ROOT%\scripts
python -m pytest modelhub/tests -v
```
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```powershell
git add scripts/modelhub/manifest.py scripts/modelhub/hf_download.py scripts/modelhub/download_all.py scripts/modelhub/tests/test_hf_download.py
git commit -m "feat(modelhub): add HF download helper with mirror fallback"
```

---

### Task 3: 部署 ComfyUI + PyTorch（Blackwell）

**Files:**
- Create: `scripts/modelhub/setup_comfyui.ps1`

- [ ] **Step 1: 编写 setup 脚本**

```powershell
# scripts/modelhub/setup_comfyui.ps1
$ErrorActionPreference = "Stop"
$Root = "$env:MODELHUB_ROOT\comfyui"

if (-not (Test-Path $Root)) {
  git clone https://github.com/Comfy-Org/ComfyUI.git $Root
}

Set-Location $Root
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1

python -m pip install -U pip wheel
# Blackwell / sm_120：使用官方 CUDA 12.8 轮子（若索引变更，以 pytorch.org 当前命令为准）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt

python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
```

- [ ] **Step 2: 执行安装（耗时，允许 10–30 分钟）**

Run: `powershell -ExecutionPolicy Bypass -File scripts/modelhub/setup_comfyui.ps1`  
Expected: 打印 torch 版本、`True`、含 `5080` 的设备名

若 `torch.cuda.is_available()` 为 False：停止，检查 CUDA 驱动 / 重装 cu128 轮子，不要继续下模型验证。

- [ ] **Step 3: Commit 脚本**

```powershell
git add scripts/modelhub/setup_comfyui.ps1
git commit -m "feat(modelhub): add ComfyUI and PyTorch setup script"
```

---

### Task 4: 安装 Custom Nodes

**Files:**
- Modify: `scripts/modelhub/setup_comfyui.ps1`（追加节点克隆段）或新建 `scripts/modelhub/setup_nodes.ps1`

- [ ] **Step 1: 创建节点安装脚本**

```powershell
# scripts/modelhub/setup_nodes.ps1
$ErrorActionPreference = "Stop"
$Nodes = "$env:MODELHUB_ROOT\comfyui\custom_nodes"
New-Item -ItemType Directory -Force -Path $Nodes | Out-Null

$repos = @{
  "ComfyUI-GGUF"     = "https://github.com/city96/ComfyUI-GGUF.git"
  "ComfyUI-Manager"  = "https://github.com/ltdrdata/ComfyUI-Manager.git"
  "ComfyUI-LTXVideo" = "https://github.com/Lightricks/ComfyUI-LTXVideo.git"
  "ComfyUI-KJNodes"  = "https://github.com/kijai/ComfyUI-KJNodes.git"
}

foreach ($name in $repos.Keys) {
  $dest = Join-Path $Nodes $name
  if (-not (Test-Path $dest)) {
    git clone $repos[$name] $dest
  } else {
    Write-Host "skip existing $name"
  }
  $req = Join-Path $dest "requirements.txt"
  if (Test-Path $req) {
    & "$env:MODELHUB_ROOT\comfyui\.venv\Scripts\pip.exe" install -r $req
  }
}

Get-ChildItem $Nodes | Select-Object Name
```

- [ ] **Step 2: 执行**

Run: `powershell -ExecutionPolicy Bypass -File scripts/modelhub/setup_nodes.ps1`  
Expected: 列出四个节点目录名

- [ ] **Step 3: Commit**

```powershell
git add scripts/modelhub/setup_nodes.ps1
git commit -m "feat(modelhub): add ComfyUI custom nodes installer"
```

---

### Task 5: 下载图片模型（SD / SDXL / Flux）

**Files:** 使用已有 `download_all.py`

- [ ] **Step 1: 核对 Flux GGUF 实际文件名**

Run:
```powershell
huggingface-cli repo-files city96/FLUX.1-dev-gguf | Select-String "Q4"
```
若无 `flux1-dev-Q4_K_S.gguf`，把 `manifest.py` 改成仓库中实际存在的 Q4 文件名后再继续。

- [ ] **Step 2: 下载 image 模块**

Run:
```powershell
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"
cd %REPO_ROOT%\scripts
python -m modelhub.download_all --module image
```
Expected: 结束打印 `DONE image`；无未捕获异常

- [ ] **Step 3: 验证落盘**

Run:
```powershell
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\checkpoints"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\unet"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\clip"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\text_encoders"
```
Expected: 至少有 SD1.5、SDXL、Flux GGUF、clip_l、T5 GGUF 各一份

- [ ] **Step 4: Commit（仅脚本/清单修正，不含权重）**

若改了 `manifest.py`：
```powershell
git add scripts/modelhub/manifest.py
git commit -m "fix(modelhub): align Flux GGUF filename with HF repo"
```

---

### Task 6: 下载 LTX-2.3 视频模型

**Files:** `scripts/modelhub/manifest.py`（按需修正文件名）

- [ ] **Step 1: 列出 unsloth GGUF 文件名**

Run:
```powershell
huggingface-cli repo-files unsloth/LTX-2.3-GGUF | Select-String "Q3"
```
把匹配的 Q3_K_S（或最接近的低显存档）写入 `manifest.py` 的 `filename`。

- [ ] **Step 2: 下载**

Run:
```powershell
cd %REPO_ROOT%\scripts
python -m modelhub.download_all --module video-ltx
```
Expected: `DONE video-ltx`

- [ ] **Step 3: 验证分发**

Run:
```powershell
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\unet" | Select-String -Pattern "LTX|ltx"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\vae"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\loras"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\text_encoders"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\latent_upscale_models"
```
Expected: unet 有 LTX GGUF；vae / loras / text_encoders / upscale 非空（若 staging 关键词未命中，手动 `Move-Item` 并回头收紧 `_dispatch_ltx_staging`）

- [ ] **Step 4: Commit 分发逻辑修正（如有）**

```powershell
git add scripts/modelhub/download_all.py scripts/modelhub/manifest.py
git commit -m "fix(modelhub): improve LTX staging file dispatch"
```

---

### Task 7: 下载 MiniMax-H3

**Files:** 同上

- [ ] **Step 1: 确认仓库可访问**

Run:
```powershell
huggingface-cli repo-files Comfy-Org/MiniMax-H3 | Select-Object -First 40
```
Expected: 能列出 NVFP4 / VAE 相关文件；若 401/403，先完成 HF 授权

- [ ] **Step 2: 下载**

Run:
```powershell
cd %REPO_ROOT%\scripts
python -m modelhub.download_all --module video-minimax
```
Expected: `DONE video-minimax`

- [ ] **Step 3: 验证**

Run:
```powershell
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\unet"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\vae"
Get-ChildItem "$env:MODELHUB_ROOT\comfyui\models\text_encoders"
```
Expected: MiniMax 主模型与编码器、VAE 已出现在对应目录

---

### Task 8: 下载 TTS（VoxCPM2）与 RAG（bge-m3）

**Files:** 无新文件

- [ ] **Step 1: 下载 TTS**

Run:
```powershell
cd %REPO_ROOT%\scripts
python -m modelhub.download_all --module tts
```
Expected: `%MODELHUB_ROOT%\tts\VoxCPM2` 含 `config` / 权重文件

- [ ] **Step 2: 下载 embed**

Run:
```powershell
python -m modelhub.download_all --module embed
```
Expected: `%MODELHUB_ROOT%\embed\bge-m3` 含 `config.json` 与模型文件

- [ ] **Step 3: 快速加载冒烟（后端 venv 可选）**

Run:
```powershell
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; import os; m=SentenceTransformer(os.path.join(os.environ.get('MODELHUB_ROOT', r'E:\ModelHub'), 'embed', 'bge-m3')); print(len(m.encode('你好')))"
```
Expected: 打印正整数向量维度（如 1024）

VoxCPM2 完整推理依赖较重，本计划仅验证目录存在即可：
```powershell
Test-Path "$env:MODELHUB_ROOT\tts\VoxCPM2"
Get-ChildItem "$env:MODELHUB_ROOT\tts\VoxCPM2" | Select-Object -First 10 Name
```

---

### Task 9: ComfyUI 启动冒烟 + 启动脚本

**Files:**
- Create: `scripts/modelhub/start_comfyui.ps1`

- [ ] **Step 1: 写启动脚本**

```powershell
# scripts/modelhub/start_comfyui.ps1
$ErrorActionPreference = "Stop"
Set-Location "$env:MODELHUB_ROOT\comfyui"
& .\.venv\Scripts\Activate.ps1
python main.py --listen 127.0.0.1 --port 8188 --lowvram --cpu-vae
```

- [ ] **Step 2: 启动并检查节点加载**

Run（另开终端，保留进程）:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/modelhub/start_comfyui.ps1
```

另开终端：
```powershell
curl http://127.0.0.1:8188/system_stats
```
Expected: HTTP 200 JSON；ComfyUI 日志中 GGUF / LTXVideo / KJNodes / Manager 无 ImportError

- [ ] **Step 3: 目录验收对照清单**

Run:
```powershell
@(
  "$env:MODELHUB_ROOT\comfyui\models\checkpoints",
  "$env:MODELHUB_ROOT\comfyui\models\unet",
  "$env:MODELHUB_ROOT\comfyui\models\text_encoders",
  "$env:MODELHUB_ROOT\comfyui\models\vae",
  "$env:MODELHUB_ROOT\comfyui\models\clip",
  "$env:MODELHUB_ROOT\tts\VoxCPM2",
  "$env:MODELHUB_ROOT\embed\bge-m3"
) | ForEach-Object {
  $n = (Get-ChildItem $_ -File -Recurse -ErrorAction SilentlyContinue | Measure-Object).Count
  "{0} => {1} files" -f $_, $n
}
```
Expected: 各路径 file count > 0

- [ ] **Step 4: Commit 启动脚本**

```powershell
git add scripts/modelhub/start_comfyui.ps1
git commit -m "feat(modelhub): add ComfyUI lowvram start script"
```

---

### Task 10: 记录安装结果（仓库内简短笔记）

**Files:**
- Create: `scripts/modelhub/INSTALL_STATUS.md`

- [ ] **Step 1: 写入实际落盘文件名与已知问题**

在文件中记录：
- 实际使用的 Flux / LTX GGUF 文件名
- `torch` 版本与 `cuda.is_available()` 结果
- 任何手动 `Move-Item` 的文件
- 未解决的 gated / 网络问题

- [ ] **Step 2: Commit**

```powershell
git add scripts/modelhub/INSTALL_STATUS.md
git commit -m "docs(modelhub): record install status and real filenames"
```

---

## Spec Coverage Self-Check

| Spec 项 | 对应 Task |
|---|---|
| §0 硬件 / lowvram | Task 9 启动参数 |
| §1 目录结构 | Task 1 |
| §2 模型清单 | Task 2 manifest + Task 5–8 |
| §3 下载策略 / 镜像 | Task 2 `hf_download.py` |
| §4 ComfyUI + 节点 | Task 3–4 |
| §5 显存策略 | Task 9（`--lowvram --cpu-vae`）；队列串行属后端后续计划 |
| §6 后端接入 | **本计划不做** → 后续 `ai-model-backend-integration` 计划 |
| §7 磁盘预算 | Task 0 / Task 9 验收 |
| §8 步骤 1–5 | Task 1–9；步骤 6–10 后续计划 |
| §10 验收（目录+ComfyUI） | Task 9；API/前端/TTS 播放属后续 |

## 后续计划（不在本次执行）

1. `comfyui_client.py` + `models.py` 改真实 URL  
2. assets / storyboard / render 接 workflow  
3. VoxCPM2 / bge-m3 后端集成与端到端测试  
