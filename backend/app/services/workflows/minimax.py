"""Build MiniMax-H3 ComfyUI API workflows (T2V / I2V)."""
from __future__ import annotations

import random
from typing import Any, Optional

UNET_NAME = "minimax_h3_fl2va_pruned_fp8_scaled.safetensors"
TE_NAME = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VAE_VIDEO = "minimax_h3_video_vae_fp16.safetensors"
VAE_AUDIO = "minimax_h3_audio_vae_fp32.safetensors"

DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 544
DEFAULT_LENGTH = 124
DEFAULT_STEPS = 20
DEFAULT_SAMPLER = "res_multistep"
DEFAULT_SCHEDULER = "simple"
DEFAULT_FPS = 24.0


def _align32(n: int) -> int:
    n = max(32, int(n))
    return n - (n % 32)


def _snap_length(length: int) -> int:
    """Snap up toward MiniMax 17k+5 frame grid (default trained ~124)."""
    length = max(5, int(length))
    # trained grid: 5 + 17*k ; 124 = 5 + 17*7
    base = 5
    step = 17
    if (length - base) % step == 0:
        return length
    k = max(0, (length - base + step - 1) // step)
    return base + k * step


def build_minimax_workflow(
    prompt: str,
    *,
    mode: str = "t2v",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    length: int = DEFAULT_LENGTH,
    seed: Optional[int] = None,
    steps: int = DEFAULT_STEPS,
    first_frame_name: Optional[str] = None,
    filename_prefix: str = "vf_minimax",
) -> dict[str, Any]:
    """Return ComfyUI API-format prompt graph for MiniMax-H3.

    mode=t2v: no first_frame. mode=i2v: requires first_frame_name (LoadImage).
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    mode = (mode or "t2v").lower()
    if mode not in ("t2v", "i2v"):
        raise ValueError(f"unknown mode: {mode}")
    if mode == "i2v" and not first_frame_name:
        raise ValueError("first_frame_name is required for i2v")

    w, h = _align32(width), _align32(height)
    length = _snap_length(length)
    seed = int(seed) if seed is not None else random.randint(0, 2**31 - 1)

    g: dict[str, Any] = {}
    nid = 0

    def add(class_type: str, **inputs: Any) -> str:
        nonlocal nid
        nid += 1
        key = str(nid)
        g[key] = {"class_type": class_type, "inputs": inputs}
        return key

    unet = add("UNETLoader", unet_name=UNET_NAME, weight_dtype="default")
    model = add(
        "MiniMaxH3SigmaShift",
        model=[unet, 0],
        shift_video=12.0,
        shift_audio=3.0,
    )
    clip = add(
        "CLIPLoader",
        clip_name=TE_NAME,
        type="minimax",
        device="default",
    )
    vvae = add("VAELoader", vae_name=VAE_VIDEO)
    avae = add("VAELoader", vae_name=VAE_AUDIO)

    i2v_kwargs: dict[str, Any] = {}
    if mode == "i2v":
        img = add("LoadImage", image=first_frame_name)
        i2v_kwargs["first_frame"] = [img, 0]

    cond = add(
        "MiniMaxH3ImageToVideo",
        clip=[clip, 0],
        vae=[vvae, 0],
        prompt=prompt,
        width=w,
        height=h,
        length=length,
        **i2v_kwargs,
    )

    noise = add("RandomNoise", noise_seed=seed)
    sampler = add("KSamplerSelect", sampler_name=DEFAULT_SAMPLER)
    sigmas = add(
        "BasicScheduler",
        model=[model, 0],
        scheduler=DEFAULT_SCHEDULER,
        steps=int(steps),
        denoise=1.0,
    )
    guider = add("BasicGuider", model=[model, 0], conditioning=[cond, 0])
    sampled = add(
        "SamplerCustomAdvanced",
        noise=[noise, 0],
        guider=[guider, 0],
        sampler=[sampler, 0],
        sigmas=[sigmas, 0],
        latent_image=[cond, 1],
    )
    frames = add("VAEDecode", samples=[sampled, 0], vae=[vvae, 0])
    audio = add("VAEDecodeAudio", samples=[sampled, 0], vae=[avae, 0])
    video = add(
        "CreateVideo",
        images=[frames, 0],
        fps=DEFAULT_FPS,
        audio=[audio, 0],
    )
    add(
        "SaveVideo",
        video=[video, 0],
        filename_prefix=filename_prefix,
        format="mp4",
        codec="h264",
    )
    return g
