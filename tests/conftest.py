import io, json, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "engine"))
from api.core import Store
from api.server import App

@pytest.fixture(scope="session")
def data():
    return json.loads((ROOT / "data" / "scope.json").read_text())

@pytest.fixture()
def app():
    return App(Store())

class Client:
    def __init__(self, app): self.app = app
    def call(self, method, path, token=None, purpose=None, body=None):
        p, _, qs = path.partition("?")
        raw = json.dumps(body).encode() if body is not None else b""
        env = {"REQUEST_METHOD": method, "PATH_INFO": p, "QUERY_STRING": qs, "wsgi.input": io.BytesIO(raw), "CONTENT_LENGTH": str(len(raw))}
        if token: env["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        if purpose: env["HTTP_X_PURPOSE_OF_USE"] = purpose
        box = {}
        def sr(status, headers): box["status"] = int(status.split()[0]); box["headers"] = dict(headers)
        out = b"".join(self.app(env, sr))
        return box["status"], json.loads(out), box["headers"]

@pytest.fixture()
def client(app):
    return Client(app)
