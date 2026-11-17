# ============================================
# LLM 调用：Ollama 优先，失败降级 OpenAI 兼容云端
# ============================================
from __future__ import annotations

import httpx


class LLMError(Exception):
    """本地与云端均不可用，或返回无法使用。"""


class LLMProvider:
    def __init__(
        self,
        *,
        ollama_base_url: str,
        ollama_model: str,
        cloud_llm_base_url: str,
        cloud_llm_api_key: str,
        cloud_llm_model: str,
        timeout_sec: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.ollama_model = ollama_model
        self.cloud_llm_base_url = (cloud_llm_base_url or "").rstrip("/")
        self.cloud_llm_api_key = cloud_llm_api_key or ""
        self.cloud_llm_model = cloud_llm_model
        self.timeout_sec = timeout_sec
        self._client = client or httpx.Client(timeout=timeout_sec)

    def chat(self, messages: list[dict[str, str]]) -> tuple[str, str]:
        """返回 (content, provider) provider in {ollama, cloud}。"""
        ollama_err: Exception | None = None
        try:
            return self._chat_ollama(messages), "ollama"
        except (httpx.HTTPError, LLMError) as e:
            ollama_err = e
            if not self.cloud_llm_base_url or not self.cloud_llm_api_key:
                raise LLMError(self._both_unavailable(ollama_err, None)) from None
            try:
                return self._chat_cloud(messages), "cloud"
            except (httpx.HTTPError, LLMError) as cloud_err:
                raise LLMError(self._both_unavailable(ollama_err, cloud_err)) from cloud_err

    def _both_unavailable(self, ollama_err: Exception | None, cloud_err: Exception | None) -> str:
        parts = ["本地与云端 LLM 均不可用"]
        if ollama_err is not None:
            parts.append(f"ollama({self.ollama_model}): {self._short_err(ollama_err)}")
        if cloud_err is not None:
            parts.append(f"cloud({self.cloud_llm_model}): {self._short_err(cloud_err)}")
        elif not self.cloud_llm_base_url or not self.cloud_llm_api_key:
            parts.append("cloud: 未配置")
        return "；".join(parts)

    @staticmethod
    def _short_err(e: Exception) -> str:
        if isinstance(e, httpx.HTTPStatusError):
            return f"HTTP {e.response.status_code}"
        return str(e)[:120]

    def _chat_ollama(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.ollama_base_url}/api/chat"
        r = self._client.post(
            url,
            json={
                "model": self.ollama_model,
                "messages": messages,
                "stream": False,
                "think": False,
                "temperature": 0.4,
            },
        )
        if r.status_code == 404:
            raise LLMError(f"模型未安装或不存在: {self.ollama_model}")
        r.raise_for_status()
        data = r.json()
        content = (data.get("message") or {}).get("content")
        if not content:
            raise LLMError("ollama empty content")
        return content

    def _chat_cloud(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.cloud_llm_base_url}/chat/completions"
        r = self._client.post(
            url,
            headers={"Authorization": f"Bearer {self.cloud_llm_api_key}"},
            json={"model": self.cloud_llm_model, "messages": messages, "temperature": 0.4},
        )
        r.raise_for_status()
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("cloud empty content") from e
        if not content:
            raise LLMError("cloud empty content")
        return content
