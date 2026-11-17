# ============================================
# ComfyUI HTTP 客户端
# ============================================
# 负责提交 workflow、轮询结果、下载产物
# ============================================

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import httpx


class ComfyUIError(RuntimeError):
    pass


DEFAULT_PROBE_URLS = tuple(
    [f"http://127.0.0.1:{p}" for p in range(8000, 8021)]
    + [f"http://127.0.0.1:{p}" for p in (8188, 8189, 8190, 7860, 7861)]
)


class ComfyUIClient:
    """与本地 ComfyUI HTTP API 交互的轻量客户端。"""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        *,
        probe_urls: Sequence[str] | None = None,
        on_base_url_change: Callable[[str], None] | None = None,
        probe_timeout: float = 0.4,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.probe_timeout = probe_timeout
        # trust_env=False：避免系统 HTTP 代理把本机 127.0.0.1 打成 503
        self._client = httpx.Client(timeout=timeout, trust_env=False)
        self._prompt_origins: dict[str, str] = {}
        self._prompt_origins_lock = threading.Lock()
        urls = [self.base_url]
        for u in probe_urls if probe_urls is not None else DEFAULT_PROBE_URLS:
            u = u.rstrip("/")
            if u and u not in urls:
                urls.append(u)
        self.probe_urls = urls
        self.on_base_url_change = on_base_url_change

    def close(self) -> None:
        self._client.close()

    def set_base_url(self, url: str, *, persist: bool = True) -> str:
        url = url.rstrip("/")
        if url == self.base_url:
            return url
        self.base_url = url
        if url not in self.probe_urls:
            self.probe_urls.insert(0, url)
        if persist and self.on_base_url_change:
            self.on_base_url_change(url)
        return url

    def _probe(self, base: str) -> bool:
        try:
            r = self._client.get(
                f"{base.rstrip('/')}/system_stats",
                timeout=self.probe_timeout,
            )
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def health(self) -> bool:
        """探活：先当前地址，失败则并行探测常见端口并自动切换。"""
        if self._probe(self.base_url):
            return True
        others = [
            u for u in self.probe_urls if u.rstrip("/") != self.base_url.rstrip("/")
        ]
        if not others:
            return False
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=min(12, len(others))) as pool:
            futures = {pool.submit(self._probe, url): url for url in others}
            try:
                for fut in as_completed(futures, timeout=3.0):
                    url = futures[fut]
                    try:
                        ok = fut.result()
                    except Exception:
                        ok = False
                    if ok:
                        self.set_base_url(url, persist=True)
                        return True
            except FuturesTimeout:
                return False
        return False

    def submit_workflow(self, workflow: dict[str, Any]) -> str:
        """提交 workflow，返回 prompt_id。"""
        base_url = self.base_url
        r = self._client.post(
            f"{base_url}/prompt",
            json={"prompt": workflow},
        )
        if r.status_code >= 400:
            raise ComfyUIError(self._format_http_error(r))
        data = r.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"no prompt_id: {data}")
        with self._prompt_origins_lock:
            self._prompt_origins[str(prompt_id)] = base_url
        return prompt_id

    def available_node_types(self) -> set[str]:
        """Return the node class names advertised by the active ComfyUI server."""
        try:
            response = self._client.get(f"{self.base_url}/object_info")
            if response.status_code >= 400:
                raise ComfyUIError(self._format_http_error(response))
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, ComfyUIError):
                raise
            raise ComfyUIError(f"invalid object_info response: {exc}") from exc
        if not isinstance(payload, dict):
            raise ComfyUIError("invalid object_info response: expected object")
        return set(payload.keys())

    @staticmethod
    def _format_http_error(r: httpx.Response) -> str:
        try:
            body = r.json()
        except (json.JSONDecodeError, ValueError):
            return f"ComfyUI {r.status_code}: {(r.text or '')[:800]}"
        parts: list[str] = []
        err = body.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or err.get("type") or "").strip()
            if msg:
                parts.append(msg)
        elif isinstance(err, str) and err.strip():
            parts.append(err.strip())
        node_errors = body.get("node_errors") or {}
        if isinstance(node_errors, dict):
            for nid, info in node_errors.items():
                info = info or {}
                cls = str(info.get("class_type") or nid)
                for item in info.get("errors") or []:
                    details = (
                        (item or {}).get("details")
                        or (item or {}).get("message")
                        or str(item)
                    )
                    parts.append(f"{cls}: {details}")
        detail = "; ".join(parts) if parts else str(body)[:800]
        return f"ComfyUI {r.status_code}: {detail[:800]}"

    def poll_history(
        self,
        prompt_id: str,
        timeout_sec: float = 600.0,
        interval_sec: float = 1.5,
        *,
        media_kinds: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """轮询 /history/{id} 直到拿到输出媒体元数据。

        默认找 images；视频任务可传 media_kinds=(\"videos\", \"gifs\", \"images\").
        """
        kinds = tuple(media_kinds) if media_kinds else ("images",)
        with self._prompt_origins_lock:
            prompt_base_url = self._prompt_origins.get(prompt_id, self.base_url)
        deadline = time.monotonic() + timeout_sec
        try:
            while time.monotonic() < deadline:
                r = self._client.get(f"{prompt_base_url}/history/{prompt_id}")
                r.raise_for_status()
                hist = r.json()
                entry = hist.get(prompt_id)
                if entry:
                    status = entry.get("status") or {}
                    if status.get("status_str") == "error" or status.get("completed") is False:
                        err = self._format_execution_error(status)
                        if err:
                            raise ComfyUIError(err)
                    for node_out in (entry.get("outputs") or {}).values():
                        for kind in kinds:
                            items = node_out.get(kind) or []
                            if items:
                                meta = dict(items[0])
                                meta["_media_kind"] = kind
                                meta["_comfy_base_url"] = prompt_base_url
                                return meta
                    # 已落库但无目标媒体
                    if status.get("completed") is True or status.get("status_str") == "success":
                        err = self._format_execution_error(status)
                        raise ComfyUIError(err or f"history has no media ({','.join(kinds)})")
                time.sleep(interval_sec)
            raise ComfyUIError(f"poll timeout after {timeout_sec}s")
        finally:
            with self._prompt_origins_lock:
                self._prompt_origins.pop(prompt_id, None)

    @staticmethod
    def _format_execution_error(status: dict[str, Any]) -> str:
        msgs = status.get("messages") or []
        for item in msgs:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            kind, payload = item[0], item[1]
            if kind != "execution_error" or not isinstance(payload, dict):
                continue
            node = payload.get("node_type") or payload.get("node_id") or "?"
            exc = (payload.get("exception_message") or "").strip()
            et = payload.get("exception_type") or "Error"
            # 截断过长 CUDA 堆栈，保留首行关键信息
            first = exc.splitlines()[0] if exc else et
            return f"ComfyUI 执行失败（节点 {node}）：{first}"
        return ""

    def download_image(self, image_meta: dict[str, Any], dest: Path) -> Path:
        """按 /view 参数下载图片到 dest。"""
        return self.download_output(image_meta, dest)

    def download_output(self, media_meta: dict[str, Any], dest: Path) -> Path:
        """按 /view 参数下载任意输出（图/视频）到 dest。"""
        params = {
            "filename": media_meta["filename"],
            "subfolder": media_meta.get("subfolder") or "",
            "type": media_meta.get("type") or "output",
        }
        output_base_url = str(media_meta.get("_comfy_base_url") or self.base_url)
        r = self._client.get(f"{output_base_url}/view", params=params)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest

    def upload_image(self, path: Path, *, overwrite: bool = True) -> str:
        """上传本地图片到 ComfyUI，返回 LoadImage 可用的文件名。"""
        path = Path(path)
        with path.open("rb") as f:
            files = {"image": (path.name, f, "application/octet-stream")}
            data = {"overwrite": "true" if overwrite else "false"}
            r = self._client.post(
                f"{self.base_url}/upload/image",
                files=files,
                data=data,
            )
        r.raise_for_status()
        body = r.json()
        name = body.get("name")
        if not name:
            raise ComfyUIError(f"upload_image missing name: {body}")
        return str(name)
