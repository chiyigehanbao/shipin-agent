from functools import lru_cache
from pathlib import Path


GUIDE_COMMIT = "d21241f0a4b3acbb34c97dae47fa417b7065e438"
GUIDE_VERSION = f"minimax-h3@{GUIDE_COMMIT[:7]}"
_ROOT = (
    Path(__file__).resolve().parents[1]
    / "prompt_packs"
    / "h3_prompt_writing_d21241f"
)


def _read_guide(filename: str, required_marker: str) -> str:
    path = _ROOT / "references" / filename
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"MiniMax H3 guide missing: {path}") from exc
    if required_marker not in text:
        raise RuntimeError(f"invalid MiniMax H3 guide: {path}")
    return text


@lru_cache(maxsize=1)
def load_base_guide() -> str:
    return _read_guide("base-en.txt", "integrated_multimodal_description")


@lru_cache(maxsize=1)
def load_ref_guide() -> str:
    return _read_guide("ref-en.txt", "subject_definitions")
