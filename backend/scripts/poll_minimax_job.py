import json
import time
import urllib.request

pid = "cd047715-dbbc-44d8-966e-8d55875c96d2"
for i in range(180):
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=30) as r:
        hist = json.load(r)
    entry = hist.get(pid)
    if entry:
        status = entry.get("status") or {}
        outs = entry.get("outputs") or {}
        keys = [(nid, list(o.keys())) for nid, o in outs.items()]
        print(
            f"[{i}] status={status.get('status_str')} "
            f"completed={status.get('completed')} outs={keys}"
        )
        if status.get("status_str") == "error":
            print(json.dumps(status, ensure_ascii=False)[:2500])
            break
        if outs:
            print(json.dumps(outs, ensure_ascii=False)[:2500])
            break
    else:
        print(f"[{i}] waiting")
    time.sleep(10)
else:
    print("TIMEOUT")
