import threading

import pytest
from werkzeug.serving import WSGIRequestHandler, make_server

import app as notes_app

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=()",
}


class QuietHandler(WSGIRequestHandler):
    """Dev-server handler that neither logs nor advertises its version."""

    def version_string(self):
        return "test"

    def log_request(self, *args, **kwargs):
        pass


def _serve(wsgi_app, handler=WSGIRequestHandler):
    server = make_server("127.0.0.1", 0, wsgi_app, request_handler=handler, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


@pytest.fixture
def service_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "validation")
    monkeypatch.setenv("RELEASE_VERSION", "1.8.3")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(service_env):
    return notes_app.create_app().test_client()


@pytest.fixture
def bare_service(service_env):
    """The app served directly, with nothing in front of it."""
    server, url = _serve(notes_app.create_app())
    yield url
    server.shutdown()


@pytest.fixture
def hardened_service(service_env):
    """The app with the headers the edge proxy adds in the real stack."""
    flask_app = notes_app.create_app()

    @flask_app.after_request
    def add_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    server, url = _serve(flask_app, QuietHandler)
    yield url
    server.shutdown()
