#!/usr/bin/env python3
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "shared-predictions.json"
SEED_FILE = ROOT / "shared-predictions.json"
FALLBACK_STATIC_DIR = ROOT / "github-upload"


class CollaborativeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/api/state":
            if STATE_FILE.exists():
                payload = STATE_FILE.read_text(encoding="utf-8")
            elif SEED_FILE.exists():
                payload = SEED_FILE.read_text(encoding="utf-8")
            else:
                payload = "{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
            return

        requested_path = self.path.split("?", 1)[0].lstrip("/")
        if requested_path and not (ROOT / requested_path).exists():
            fallback_file = FALLBACK_STATIC_DIR / requested_path
            if fallback_file.is_file():
                self.path = f"/github-upload/{requested_path}"

        super().do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/state":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload.get("friends"), list) or not isinstance(payload.get("matches"), list):
                raise ValueError("Invalid tracker state")
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        if STATE_FILE.exists():
            try:
                existing = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
            for key, expected_type in (("bonusQuestions", list), ("bonusAnswers", dict)):
                if key not in payload and isinstance(existing.get(key), expected_type):
                    payload[key] = existing[key]

        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE_FILE)
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "4180"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CollaborativeHandler)
    print(f"Collaborative tracker: http://0.0.0.0:{port}/world-cup-prediction-tracker.html")
    server.serve_forever()
