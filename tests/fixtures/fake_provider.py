import json, http.server, time
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); req = json.loads(self.rfile.read(n) or b"{}")
        model = req.get("model", "")
        if model == "m429":
            body = json.dumps({"error": {"message": "Provider returned error", "code": 429, "metadata": {"provider_name": "FakeProv", "raw": "slow down please"}}}).encode()
            self.send_response(429); self.send_header("Content-Type", "application/json"); self.send_header("Retry-After", "17")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if model == "m522":
            body = b"<!DOCTYPE html><html><head><title>fake.example | 522: Connection timed out</title></head><body><h1>Connection timed out</h1></body></html>"
            self.send_response(522); self.send_header("Content-Type", "text/html; charset=UTF-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        base = {"id": "c1", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
        def send(obj): self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n"); self.wfile.flush()
        send({**base, "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}]})
        if model == "mid":
            send({**base, "error": {"code": 429, "message": "Rate limit exceeded"}, "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "error"}]})
        else:
            send({**base, "choices": [{"index": 0, "delta": {"content": " done"}, "finish_reason": "stop"}]})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
http.server.ThreadingHTTPServer(("127.0.0.1", 7898), H).serve_forever()
