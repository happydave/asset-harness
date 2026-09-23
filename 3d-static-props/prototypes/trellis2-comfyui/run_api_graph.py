#!/usr/bin/env python3
"""Queue an API-format graph (from template_to_api.py) on a ComfyUI server and wait for it.

    run_api_graph.py GRAPH.json [BASE=http://127.0.0.1:7121] [TIMEOUT_S=7200]

Exit 0 on success, 1 on an execution error (the failing node and its message are printed), 2 on a
validation refusal, 3 on timeout.
"""
import json, sys, time, urllib.error, urllib.request

graph = json.load(open(sys.argv[1]))
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:7121"
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 7200

req = urllib.request.Request(f"{base}/prompt", method="POST",
                             data=json.dumps({"prompt": graph, "client_id": "run_api_graph"}).encode(),
                             headers={"Content-Type": "application/json"})
try:
    pid = json.load(urllib.request.urlopen(req, timeout=60))["prompt_id"]
except urllib.error.HTTPError as e:
    print("VALIDATION FAILED:", json.dumps(json.loads(e.read().decode()), indent=1)[:4000])
    sys.exit(2)
print("PROMPT_ID", pid, flush=True)
t0 = time.time()
while time.time() - t0 < timeout:
    time.sleep(10)
    h = json.load(urllib.request.urlopen(f"{base}/history/{pid}", timeout=30))
    if pid not in h:
        continue
    st = h[pid]["status"]
    print(f"DONE status={st.get('status_str')} elapsed={time.time() - t0:.0f}s", flush=True)
    for node, out in h[pid].get("outputs", {}).items():
        print("OUTPUT", node, json.dumps(out)[:300], flush=True)
    for kind, msg in st.get("messages", []):
        if kind == "execution_error":
            print("ERROR node", msg.get("node_id"), msg.get("node_type"), "-", msg.get("exception_message", "")[:800])
    sys.exit(0 if st.get("status_str") == "success" else 1)
print(f"TIMEOUT after {timeout:.0f}s", flush=True)
sys.exit(3)
