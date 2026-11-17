import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8010"
PID = "proj_3eeceb7089"


def req(method, path, body=None):
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


def main():
    code, frames = req("GET", f"/api/storyboard/{PID}/frames")
    print("list", code, len(frames) if isinstance(frames, list) else frames)
    target = None
    for f in frames or []:
        if f.get("image_url"):
            target = f
            break
    if not target:
        print("NO_IMAGE_FRAME")
        return 1
    fid = target["id"]
    print("frame", fid, target.get("image_url"))
    code, body = req(
        "POST",
        f"/api/storyboard/{PID}/frames/{fid}/generate-video",
        {"width": 640, "height": 384, "length": 39, "seed": 3},
    )
    print("submit", code, body)
    if code != 200:
        return 2
    job_id = body.get("video_job_id")
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(8)
        jc, fr = req("GET", f"/api/storyboard/{PID}/frames/{fid}")
        print(
            "poll",
            jc,
            fr.get("video_status"),
            fr.get("video_url"),
            fr.get("video_error"),
        )
        if fr.get("video_status") == "completed" and fr.get("video_url"):
            print("SUCCESS", fr["video_url"])
            return 0
        if fr.get("video_status") == "failed":
            if job_id:
                _, job = req("GET", f"/api/jobs/{job_id}")
                print("job", job)
            return 3
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
