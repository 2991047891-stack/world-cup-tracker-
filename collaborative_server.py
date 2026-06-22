#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "shared-predictions.json"
SEED_FILE = ROOT / "shared-predictions.json"
FALLBACK_STATIC_DIR = ROOT / "github-upload"
BACKUP_DIR = DATA_DIR / "state-backups"
MAX_BACKUPS = 20


def filled(value):
    return value is not None and value != ""


def fixture_key(match):
    return "|".join(str(match.get(field, "")).strip().lower() for field in ("date", "group", "home", "away"))


def merge_tracker_state(existing, incoming):
    if not isinstance(existing, dict):
        return incoming

    merged = dict(incoming)

    existing_friends = existing.get("friends")
    if isinstance(existing_friends, list) and existing_friends:
        merged["friends"] = existing_friends

    existing_matches = existing.get("matches") if isinstance(existing.get("matches"), list) else []
    incoming_matches = incoming.get("matches") if isinstance(incoming.get("matches"), list) else []
    existing_by_id = {match.get("id"): match for match in existing_matches if match.get("id")}
    incoming_ids = {match.get("id") for match in incoming_matches if match.get("id")}

    for match in incoming_matches:
        old = existing_by_id.get(match.get("id"))
        if not old:
            continue
        for side in ("actualHome", "actualAway"):
            if not filled(match.get(side)) and filled(old.get(side)):
                match[side] = old.get(side)
        for field in ("time", "city"):
            if not filled(match.get(field)) and filled(old.get(field)):
                match[field] = old.get(field)

    existing_by_signature = {fixture_key(match): match for match in existing_matches}
    incoming_signatures = {fixture_key(match) for match in incoming_matches}
    for match in existing_matches:
        if match.get("id") not in incoming_ids and fixture_key(match) not in incoming_signatures:
            incoming_matches.append(match)
    merged["matches"] = incoming_matches

    predictions = dict(incoming.get("predictions") or {})
    for key, old_prediction in (existing.get("predictions") or {}).items():
        incoming_prediction = predictions.get(key)
        if not incoming_prediction or not filled(incoming_prediction.get("home")) or not filled(incoming_prediction.get("away")):
            predictions[key] = old_prediction
    merged["predictions"] = predictions

    bonus_questions = list(incoming.get("bonusQuestions") or [])
    existing_questions = {question.get("id"): question for question in existing.get("bonusQuestions", []) if question.get("id")}
    question_ids = {question.get("id") for question in bonus_questions}
    for question in bonus_questions:
        old = existing_questions.get(question.get("id"))
        if old and not filled(question.get("correctAnswer")) and filled(old.get("correctAnswer")):
            question["correctAnswer"] = old.get("correctAnswer")
    for question_id, question in existing_questions.items():
        if question_id not in question_ids:
            bonus_questions.append(question)
    merged["bonusQuestions"] = bonus_questions

    bonus_answers = dict(incoming.get("bonusAnswers") or {})
    for key, answer in (existing.get("bonusAnswers") or {}).items():
        if not filled(bonus_answers.get(key)):
            bonus_answers[key] = answer
    merged["bonusAnswers"] = bonus_answers

    return merged


def backup_state():
    if not STATE_FILE.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = BACKUP_DIR / f"shared-predictions-{stamp}.json"
    backup.write_text(STATE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    backups = sorted(BACKUP_DIR.glob("shared-predictions-*.json"), reverse=True)
    for old_backup in backups[MAX_BACKUPS:]:
        old_backup.unlink(missing_ok=True)


class CollaborativeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in ("null", "https://world-cup-prediction-tracker.onrender.com"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

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
            payload = merge_tracker_state(existing, payload)

        backup_state()
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
