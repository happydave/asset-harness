#!/usr/bin/env python3
"""Spike tool: run MediaPipe FaceLandmarker on still images in headless Chromium; write landmarks JSON.
The page POSTs its result back, because WASM start-up outlives Chromium's virtual-time budget."""
import functools, http.server, json, subprocess, sys, tempfile, threading, time
from pathlib import Path
HERE = Path(__file__).resolve().parent      # images and a `vendor` link to ../../obs_page/vendor are expected beside this file
result = {}
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        result["body"] = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(204); self.end_headers()
def main(images, out):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(HERE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/detect.html?images={','.join(images)}"
    with tempfile.TemporaryDirectory() as prof:
        p = subprocess.Popen(["chromium", "--headless=new", "--disable-gpu", "--use-angle=swiftshader",
                              "--enable-unsafe-swiftshader", f"--user-data-dir={prof}", "--remote-debugging-port=0", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while "body" not in result and time.time() - t0 < 240: time.sleep(0.25)
        p.terminate(); p.wait(timeout=20)
    srv.shutdown()
    if "body" not in result: raise SystemExit("no result from the page within 240 s")
    Path(out).write_bytes(result["body"])
    d = json.loads(result["body"])
    print(d.get("error") or {k: v["faces"] for k, v in d["res"].items()}, f"({time.time() - t0:.1f} s)")
if __name__ == "__main__":
    main(sys.argv[2:], sys.argv[1])
