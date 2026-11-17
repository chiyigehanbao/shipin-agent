from __future__ import annotations

from pathlib import Path
from typing import Protocol


class EmbedderProto(Protocol):
    def available(self) -> bool: ...
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class BgeEmbedder:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = Path(model_dir)
        self._model = None

    def available(self) -> bool:
        return self.model_dir.exists()

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            if not self.available():
                raise RuntimeError("bge-m3_not_found")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(str(self.model_dir))
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]


class FakeEmbedder:
    """Deterministic vectors for tests (no model download)."""

    def available(self) -> bool:
        return True

    def encode(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            # crude bag: length + char codes hashed into 8 dims
            dims = [0.0] * 8
            dims[0] = float(len(t)) / 100.0
            for i, ch in enumerate(t[:32]):
                dims[1 + (i % 7)] += (ord(ch) % 97) / 97.0
            # L2 normalize
            n = sum(x * x for x in dims) ** 0.5 or 1.0
            out.append([x / n for x in dims])
        return out
