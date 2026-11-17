"""Phase C smoke: POST /api/videos/.../generate and wait for mp4."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8010"
PROJECT = "proj_minimax_smoke"


def req(method: str, path: str, body: dict | None = None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload


def main() -> int:
    # ensure project exists (ignore errors)
    req(
        "POST",
        "/api/projects",
        {
            "name": "MiniMax smoke",
            "type": "drama",
            "description": "video smoke",
            "style": "cinematic",
        },
    )
    # use fixed id via list or create — prefer create response
    code, projects = req("GET", "/api/projects")
    pid = PROJECT
    if code == 200 and isinstance(projects, list):
        for p in projects:
            if p.get("name") == "MiniMax smoke":
                pid = p["id"]
                break
        else:
            code, created = req(
                "POST",
                "/api/projects",
                {
                    "name": "MiniMax smoke",
                    "type": "drama",
                    "description": "video smoke",
                    "style": "cinematic",
                },
            )
            if code == 200:
                pid = created["id"]

    print("project", pid)
    code, body = req(
        "POST",
        f"/api/videos/{pid}/generate",
        {
            "prompt_en": (
                "Cinematic rainy night dock, lone detective under streetlight, "
                "soft fog, subtle camera push-in, no text."
            ),
            "width": 640,
            "height": 384,
            "length": 39,
            "seed": 7,
        },
    )
    print("generate", code, body)
    if code != 200:
        return 1
    job_id = body["job_id"]
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(8)
        jc, job = req("GET", f"/api/jobs/{job_id}")
        status = (job or {}).get("status")
        print(
            "job",
            jc,
            status,
            (job or {}).get("progress"),
            (job or {}).get("error"),
            (job or {}).get("result"),
        )
        if status == "completed":
            url = ((job or {}).get("result") or {}).get("output_url")
            print("SUCCESS", url)
            if url:
                with urllib.request.urlopen(BASE + url, timeout=60) as resp:
                    print("media", resp.status, resp.headers.get("Content-Type"), resp.length)
            return 0
        if status == "failed":
            return 2
    print("TIMEOUT")
    return 3


if __name__ == "__main__":
    sys.exit(main())
