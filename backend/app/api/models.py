# ============================================
# 模型配置 API
# ============================================
# 提供模型服务配置和状态查询接口
# ============================================

from fastapi import APIRouter
from typing import Optional
from pydantic import BaseModel

from app.core.settings import settings
from app.services.model_readiness import check_all_models, check_face_identity_models
from app.services.runtime import client, queue, store

router = APIRouter()

# ============================================
# 数据模型
# ============================================

class ModelService(BaseModel):
    """模型服务模型"""
    id: str
    name: str
    name_en: str
    type: str               # image / video / llm / tts
    status: str             # online / busy / offline
    gpu_usage: int
    queue: int
    model: str
    api_url: str


# ============================================
# Mock 数据
# ============================================

mock_services = {
    "sd": {
        "id": "sd",
        "name": "Stable Diffusion",
        "name_en": "SD",
        "type": "image",
        "status": "online",
        "gpu_usage": 45,
        "queue": 2,
        "model": "Flux.1 Dev",
        "api_url": "http://127.0.0.1:7860",
    },
    "ltx": {
        "id": "ltx",
        "name": "LTX Video",
        "name_en": "LTX",
        "type": "video",
        "status": "offline",
        "gpu_usage": 0,
        "queue": 0,
        "model": "LTX 2.3（权重已装，产品链路未接入）",
        "api_url": "",
    },
    "llm": {
        "id": "llm",
        "name": "LLM 大脑",
        "name_en": "LLM Brain",
        "type": "llm",
        "status": "online",
        "gpu_usage": 0,
        "queue": 0,
        "model": "Qwen2.5-72B",
        "api_url": "https://api.openai.com/v1",
    },
    "tts": {
        "id": "tts",
        "name": "TTS 配音",
        "name_en": "TTS Voice",
        "type": "tts",
        "status": "online",
        "gpu_usage": 0,
        "queue": 0,
        "model": "Edge TTS",
        "api_url": "",
    },
    "minimax": {
        "id": "minimax",
        "name": "MiniMax H3",
        "name_en": "MiniMax",
        "type": "video",
        "status": "offline",
        "gpu_usage": 0,
        "queue": 0,
        "model": "MiniMax-H3 pruned_fp8",
        "api_url": "",
    },
}


mock_services["sd"]["api_url"] = settings.comfyui_base_url
mock_services["sd"]["model"] = "flux"
mock_services["ltx"]["api_url"] = settings.comfyui_base_url
mock_services["minimax"]["api_url"] = settings.comfyui_base_url


def _sync_sd_url() -> None:
    mock_services["sd"]["api_url"] = client.base_url
    mock_services["ltx"]["api_url"] = client.base_url
    mock_services["minimax"]["api_url"] = client.base_url


def _mark_video_unwired() -> None:
    # LTX：权重可在 ModelHub，但后端尚无 LTX generate 产品接口
    mock_services["ltx"]["status"] = "offline"
    mock_services["ltx"]["gpu_usage"] = 0
    mock_services["ltx"]["queue"] = 0
    mock_services["ltx"]["model"] = "LTX 2.3（权重已装，产品链路未接入）"


def _sync_minimax_status(*, online: bool) -> None:
    from app.services.model_readiness import check_model

    ready = check_model("minimax", settings.comfyui_models_dir)["ready"]
    mock_services["minimax"]["status"] = "online" if (online and ready) else "offline"
    mock_services["minimax"]["gpu_usage"] = 0
    mock_services["minimax"]["queue"] = 0
    mock_services["minimax"]["model"] = (
        "MiniMax-H3 pruned_fp8"
        if ready
        else "MiniMax-H3（权重不齐）"
    )


# ============================================
# API 接口
# ============================================

@router.get("/readiness", summary="图片模型权重就绪状态")
async def get_model_readiness():
    # 连接 ≠ 就绪：comfyui_online 探进程；models.*.ready 探磁盘文件
    online = client.health()
    _sync_sd_url()
    return {
        "models": check_all_models(settings.comfyui_models_dir),
        "face_identity": check_face_identity_models(
            settings.face_identity_models_dir
        ),
        "comfyui_online": online,
        "comfyui_base_url": client.base_url,
    }


@router.get("/services", summary="获取所有模型服务状态")
async def get_all_services():
    """获取所有模型服务的状态"""
    online = client.health()
    depth = store.queue_depth() + queue.pending_count()
    _sync_sd_url()
    _mark_video_unwired()
    _sync_minimax_status(online=online)
    for sid in ("sd",):
        mock_services[sid]["status"] = "online" if online else "offline"
        mock_services[sid]["queue"] = depth
    return list(mock_services.values())


@router.get("/services/{service_id}", response_model=ModelService, summary="获取单个服务状态")
async def get_service(service_id: str):
    """获取单个模型服务的状态"""
    _sync_sd_url()
    _mark_video_unwired()
    _sync_minimax_status(online=client.health())
    return mock_services.get(service_id, {"error": "服务不存在"})


@router.post("/services/{service_id}/test", summary="测试连接")
async def test_connection(service_id: str):
    """测试模型服务连接"""
    if service_id == "ltx":
        ok = client.health()
        _sync_sd_url()
        return {
            "status": "failed",
            "message": (
                f"视频生成产品链路未接入（ComfyUI {'在线' if ok else '离线'}: {client.base_url}）"
            ),
            "latency": None,
            "api_url": client.base_url,
        }
    if service_id == "minimax":
        ok = client.health()
        _sync_sd_url()
        _sync_minimax_status(online=ok)
        ready = check_all_models(settings.comfyui_models_dir).get("minimax", {})
        if not ok:
            return {
                "status": "failed",
                "message": f"ComfyUI unreachable (tried {', '.join(client.probe_urls)})",
                "latency": None,
                "api_url": client.base_url,
            }
        if not ready.get("ready"):
            return {
                "status": "failed",
                "message": f"minimax weights missing: {', '.join(ready.get('missing_files') or [])}",
                "latency": None,
                "api_url": client.base_url,
            }
        return {
            "status": "success",
            "message": f"MiniMax ready ({client.base_url})",
            "latency": None,
            "api_url": client.base_url,
        }
    if service_id in ("sd", "flux"):
        ok = client.health()
        _sync_sd_url()
        return {
            "status": "success" if ok else "failed",
            "message": (
                f"ComfyUI OK ({client.base_url})"
                if ok
                else f"ComfyUI unreachable (tried {', '.join(client.probe_urls)})"
            ),
            "latency": None,
            "api_url": client.base_url,
        }
    return {
        "status": "success",
        "message": "连接成功",
        "latency": "120ms",
    }


@router.post("/services/{service_id}/config", summary="更新配置")
async def update_config(service_id: str, config: dict):
    """更新模型服务配置（sd 可改 api_url，并持久化）。"""
    if service_id in ("sd", "flux", "ltx"):
        url = (config.get("api_url") or config.get("base_url") or "").strip()
        if url:
            client.set_base_url(url, persist=True)
            _sync_sd_url()
            ok = client.health()
            return {
                "message": "配置已更新",
                "service_id": service_id,
                "api_url": client.base_url,
                "online": ok,
            }
    return {
        "message": "配置已更新",
        "service_id": service_id,
        "api_url": client.base_url,
    }
