import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def test_home_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Hello from myapp"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_readyz(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ready"
