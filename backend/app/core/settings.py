# ============================================
# 环境配置
# ============================================

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用环境配置，支持 .env 与环境变量覆盖。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    comfyui_base_url: str = "http://127.0.0.1:8000"
    # 模型根目录：公司机默认 E:\ModelHub；家里机设 D:\ModelHub（通过环境变量 MODELHUB_ROOT 覆盖）
    modelhub_root: Path = Path(os.environ.get("MODELHUB_ROOT", r"E:\ModelHub"))
    poll_timeout_sec: float = 600.0
    poll_interval_sec: float = 1.5

    # LLM：电影感润色（Ollama 优先，失败降级云端 OpenAI 兼容接口）
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    cloud_llm_base_url: str = ""  # 例 https://api.openai.com/v1
    cloud_llm_api_key: str = ""
    cloud_llm_model: str = "gpt-4o-mini"
    llm_timeout_sec: float = 60.0
    sqlite_path: Path | None = None  # 空则用 backend/data/shipin-agent.db

    @property
    def resolved_sqlite_path(self) -> Path:
        if self.sqlite_path:
            return Path(self.sqlite_path)
        return Path(__file__).resolve().parents[2] / "data" / "shipin-agent.db"

    @property
    def assets_output_dir(self) -> Path:
        return self.modelhub_root / "outputs" / "assets"

    @property
    def media_mount_dir(self) -> Path:
        return self.modelhub_root / "outputs"

    @property
    def comfyui_models_dir(self) -> Path:
        # 安装规格约定：权重落在 {MODELHUB_ROOT}/comfyui/models/（相对 checkpoints|unet|...）
        return self.modelhub_root / "comfyui" / "models"

    @property
    def face_identity_models_dir(self) -> Path:
        return self.modelhub_root / "face" / "models"

    @property
    def rag_chroma_dir(self) -> Path:
        return self.modelhub_root / "rag" / "chroma"

    @property
    def embed_model_dir(self) -> Path:
        return self.modelhub_root / "embed" / "bge-m3"


settings = Settings()
