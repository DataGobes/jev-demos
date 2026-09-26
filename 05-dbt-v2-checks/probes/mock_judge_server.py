"""A mock judge over HTTP on 127.0.0.1, for probes that test whether check SQL can call out.

GET /judge?name=<column>&description=<text>  ->  {"ok": bool}
Every request is logged to stderr (and appended to $MOCK_JUDGE_LOG if set), so a probe can
show how many calls one query really made.

    uv run python probes/mock_judge_server.py 8765
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

CALLS: list[str] = []


def mock_verdict(name: str, description: str) -> bool:
    """True = description matches. False when the description's last word is not in the name."""
    words = description.lower().split()
    return not words or words[-1] in name.lower()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        CALLS.append(self.path)
        print(f"mock judge <- GET {self.path}", file=sys.stderr, flush=True)
        if log := os.environ.get("MOCK_JUDGE_LOG"):
            with open(log, "a") as f:
                f.write(self.path + "\n")
        body = json.dumps({"ok": mock_verdict(q.get("name", [""])[0], q.get("description", [""])[0])})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
