"""notes-api: the stand-in release candidate for the validation environment.

It is deliberately small. What matters is that it behaves like a real service
at deploy time: it needs configuration, it needs a writable data directory,
and it tells you through /readyz when either of those is wrong.
"""

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, request

REQUIRED_SETTINGS = ("APP_ENV", "RELEASE_VERSION")
ALLOWED_ENVS = ("dev", "validation", "staging", "production")
MAX_NOTE_LENGTH = 500
MAX_NOTES = 200

log = logging.getLogger("notes-api")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


def _notes_file() -> Path:
    return _data_dir() / "notes.json"


def _load_notes() -> list:
    try:
        return json.loads(_notes_file().read_text())
    except FileNotFoundError:
        return []


def _save_notes(notes: list) -> None:
    # write to a temp file and rename so a crash never leaves half a file behind
    fd, tmp = tempfile.mkstemp(dir=_data_dir(), suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(notes, fh)
    os.replace(tmp, _notes_file())


def readiness_problems() -> list:
    """Return a list of human-readable reasons the service cannot take traffic."""
    problems = []

    for key in REQUIRED_SETTINGS:
        if not os.environ.get(key, "").strip():
            problems.append(f"{key} is not set")

    app_env = os.environ.get("APP_ENV", "").strip()
    if app_env and app_env not in ALLOWED_ENVS:
        problems.append(f"APP_ENV '{app_env}' is not one of {', '.join(ALLOWED_ENVS)}")

    data_dir = _data_dir()
    if not data_dir.is_dir():
        problems.append(f"data directory {data_dir} does not exist")
    else:
        try:
            with tempfile.NamedTemporaryFile(dir=data_dir):
                pass
        except OSError as exc:
            problems.append(f"data directory {data_dir} is not writable: {exc.strerror}")

    return problems


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/readyz")
    def readyz():
        problems = readiness_problems()
        if problems:
            log.warning("not ready: %s", "; ".join(problems))
            return jsonify(status="not ready", problems=problems), 503
        return jsonify(status="ready")

    @app.get("/api/version")
    def version():
        return jsonify(
            service="notes-api",
            version=os.environ.get("RELEASE_VERSION") or "unknown",
            environment=os.environ.get("APP_ENV") or "unknown",
        )

    @app.get("/api/notes")
    def list_notes():
        return jsonify(notes=_load_notes())

    @app.post("/api/notes")
    def add_note():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="request body must be a JSON object"), 400

        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="'text' is required"), 400
        if len(text) > MAX_NOTE_LENGTH:
            return jsonify(error=f"'text' must be at most {MAX_NOTE_LENGTH} characters"), 400

        notes = _load_notes()
        if len(notes) >= MAX_NOTES:
            return jsonify(error="note limit reached"), 409

        note = {"id": uuid.uuid4().hex, "text": text.strip()}
        notes.append(note)
        try:
            _save_notes(notes)
        except OSError as exc:
            log.error("could not persist note: %s", exc)
            return jsonify(error="storage unavailable"), 503
        return jsonify(note), 201

    @app.after_request
    def no_store(response):
        # nothing this API returns should sit in a shared cache
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.errorhandler(404)
    def not_found(_exc):
        return jsonify(error="not found"), 404

    @app.errorhandler(405)
    def method_not_allowed(_exc):
        return jsonify(error="method not allowed"), 405

    @app.errorhandler(413)
    def too_large(_exc):
        return jsonify(error="request body too large"), 413

    @app.errorhandler(Exception)
    def unhandled(exc):
        # full detail goes to the log, never to the client
        log.exception("unhandled error: %s", exc)
        return jsonify(error="internal error"), 500

    return app


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
app = create_app()
