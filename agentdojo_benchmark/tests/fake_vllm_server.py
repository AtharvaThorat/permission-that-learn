"""A stand-in for `vllm serve`, so phase 6 can be tested without a GPU.

Started the same way the real server is:  python fake_vllm_server.py serve <model_dir> --port N --served-model-name X ...
It serves a minimal OpenAI-compatible API on localhost:
  GET  /v1/models            -> lists the served model (used to detect "server ready")
  POST /v1/chat/completions  -> first turn: calls the first tool that needs no arguments;
                                after a tool result: replies "Done."
It also checks every request has the shape the real models need (no "developer" role, plain-string content)
and prints the highest number of requests it handled at the same time.
"""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

arguments = sys.argv[1:]
port = int(arguments[arguments.index("--port") + 1])
served_model_name = arguments[arguments.index("--served-model-name") + 1]

counter_lock = threading.Lock()
requests_in_progress = 0
most_requests_at_once = 0


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the server log short
        pass

    def send_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        self.send_json(200, {"object": "list", "data": [{"id": served_model_name, "object": "model"}]})

    def do_POST(self) -> None:
        global requests_in_progress, most_requests_at_once
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with counter_lock:
            requests_in_progress += 1
            most_requests_at_once = max(most_requests_at_once, requests_in_progress)
            print(f"most_requests_at_once={most_requests_at_once}", flush=True)
        try:
            time.sleep(0.2)  # a little delay, so parallel requests overlap
            messages = request["messages"]
            if any(m["role"] == "developer" or not isinstance(m.get("content"), (str, type(None))) for m in messages):
                self.send_json(400, {"error": {"message": "unsupported message format"}})
                return
            if messages[-1]["role"] == "user":
                tool = next(t for t in request.get("tools", []) if not t["function"]["parameters"].get("required"))
                reply = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": tool["function"]["name"], "arguments": "{}"},
                }]}
            else:
                reply = {"role": "assistant", "content": "Done."}
            self.send_json(200, {
                "id": "fake", "object": "chat.completion", "created": 0, "model": served_model_name,
                "choices": [{"index": 0, "finish_reason": "stop", "message": reply}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
        finally:
            with counter_lock:
                requests_in_progress -= 1


if __name__ == "__main__":
    time.sleep(1)  # pretend to load a model
    ThreadingHTTPServer(("127.0.0.1", port), FakeOpenAIHandler).serve_forever()
