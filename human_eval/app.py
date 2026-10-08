"""Loopback-only annotation server; Python standard library, no API keys."""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import secrets
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .common import read_tasks, HERE, read_jsonl, verify_run
from .storage import Store


class Audit:
    def __init__(self, run):
        self.run = Path(run).resolve()
        self.manifest = verify_run(self.run)
        self.tasks = {t["id"]: t for t in read_tasks(self.run)}
        self.store = Store(self.run / "annotations.sqlite", list(self.tasks.values()))
        self.token = secrets.token_urlsafe(32)

    def index(self, annotator, kind=None):
        if kind not in {None, "qa", "judge"}:
            raise ValueError("Unknown task")
        state = self.store.state(annotator)
        items = []
        for t in self.tasks.values():
            if kind and t["kind"] != kind:
                continue
            stage = "answer" if t["kind"] == "qa" else "judge"
            items.append({"id": t["id"], "group": t["group"], "kind": t["kind"],
                          "errors": len(t["errors"]), "model": None,
                          "done": (t["id"], stage) in state})
        return {"items": items, "inventory": self.manifest["inventory"], "token": self.token, "run": self.run.name}

    def task(self, task_id, annotator):
        self.store.check_annotator(annotator)
        t = self.tasks[task_id]
        stage = "answer" if t["kind"] == "qa" else "judge"
        submission = self.store.state(annotator).get((task_id, stage))
        result = {"id": t["id"], "kind": t["kind"], "group": t["group"], "stage": stage,
                  "errors": t["errors"], "warnings": t["warnings"] if t["kind"] == "qa" else [],
                  "draft": self.store.draft(annotator, task_id, stage), "submission": submission,
                  "has_video": t["kind"] == "qa" and bool(t["media"]["asset"]) and
                      t["qa_input"]["input_mode"] == "video"}
        if t["kind"] == "judge":
            result["judge_input"] = t["judge_input"]
        else:
            result["qa_input"] = t["qa_input"]
        # QA references never become a second human annotation stage.
        return result

    def media(self, task_id, annotator):
        self.store.check_annotator(annotator)
        t = self.tasks[task_id]
        if t["kind"] == "judge":
            raise ValueError("Judge uses the same text-only materials as the LLM judge")
        if t["qa_input"]["input_mode"] != "video":
            raise ValueError("This question uses text input")
        asset = t["media"]["asset"]
        if not asset:
            raise ValueError("Video is missing")
        return self.run / asset


class Handler(BaseHTTPRequestHandler):
    server_version = "HumanAudit/1"

    def __init__(self, *args, audit, **kwargs):
        self.audit = audit
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):
        # Media polling and autosaves would otherwise flood the terminal.
        if args and isinstance(args[0], str) and (' 400' in args[0] or ' 500' in args[0]):
            super().log_message(fmt, *args)

    def response_headers(self, status, kind, size, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; frame-ancestors 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.response_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def params(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        return url.path, {k: v[0] for k, v in query.items()}

    def check_host(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") not in {expected, f"localhost:{self.server.server_port}"}:
            raise ValueError("Only local Host headers are allowed")

    def serve_media(self, path, head=False):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        value = self.headers.get("Range")
        if value:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
            if not match or not any(match.groups()):
                self.response_headers(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), end) if last else end
            else:
                start = max(0, size - int(last))
            if start > end or start >= size:
                self.response_headers(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            status = 206
        extra = {"Accept-Ranges": "bytes"}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.response_headers(status, mimetypes.guess_type(path.name)[0] or "application/octet-stream", end-start+1, extra)
        if not head:
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = stream.read(min(1024*256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        try:
            self.check_host()
            path, query = self.params()
            if path in {"/", "/qa", "/judge", "/app.js", "/style.css"}:
                filename = "index.html" if path in {"/", "/qa", "/judge"} else path[1:]
                data = (HERE / "web" / filename).read_bytes()
                self.response_headers(200, mimetypes.guess_type(filename)[0] + "; charset=utf-8", len(data))
                if not head:
                    self.wfile.write(data)
            elif path == "/api/index":
                self.send_json(self.audit.index(query["annotator"], query.get("kind")))
            elif path == "/api/task":
                self.send_json(self.audit.task(query["id"], query["annotator"]))
            elif path.startswith("/media/"):
                self.serve_media(self.audit.media(path.split("/")[-1], query["annotator"]), head)
            else:
                self.send_json({"error": "Not found"}, 404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (ValueError, KeyError, OSError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_POST(self):
        try:
            self.check_host()
            if self.headers.get("X-Audit-Token") != self.audit.token:
                raise ValueError("Invalid session token; reload the page")
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 300000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Request body must be an object")
            path, _ = self.params()
            who = data["annotator"]
            if path == "/api/rename":
                self.audit.store.rename(who, data["new_annotator"])
            elif path in {"/api/draft", "/api/submit"}:
                self.audit.store.write(who, data["task_id"], data["stage"], data["data"], draft=path.endswith("draft"))
            else:
                raise ValueError("Unknown action")
            self.send_json({"ok": True})
        except (ValueError, KeyError, OSError) as exc:
            self.send_json({"error": str(exc)}, 400)


def make_server(audit, port):
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, audit=audit))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    audit = Audit(args.run)
    server = make_server(audit, args.port)
    print(f"Human audit: http://127.0.0.1:{server.server_port}\nRun: {audit.run}\nPress Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
