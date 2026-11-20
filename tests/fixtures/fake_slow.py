import json, http.server, time, sys
LOG = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); req = json.loads(self.rfile.read(n) or b"{}")
        model = req.get("model", "")
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        base = {"id": "c1", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
        def send(o): self.wfile.write(b"data: " + json.dumps(o).encode() + b"\n\n"); self.wfile.flush()
        def delta(t, fin=None): send({**base, "choices": [{"index": 0, "delta": {"content": t}, "finish_reason": fin}]})
        try:
            if model == "silent":
                time.sleep(40); return
            delta("Here is part one. ")
            if model == "ok":
                delta("And part two.", "stop"); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush(); return
            for i in range(300):
                time.sleep(0.1); delta(f"word{i} ")
        except (BrokenPipeError, ConnectionResetError, OSError):
            open(LOG, "a").write(model + "\n")
http.server.ThreadingHTTPServer(("0.0.0.0", 7889), H).serve_forever()
