from fastapi.testclient import TestClient

from deepseek_all_in_one.api import create_app
from deepseek_all_in_one.config import load_config


def test_models_requires_auth():
    app = create_app(load_config("config.toml"))
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 401


def test_models_lists_six_with_auth():
    app = create_app(load_config("config.toml"))
    client = TestClient(app)
    resp = client.get("/v1/models", headers={"Authorization": "Bearer sk-dsfr-local-change-me"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 6
    assert {m["id"] for m in data} >= {"deepseek-v4-flash-es", "deepseek-v4-pro-de"}
