import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from ydl_server.middleware import APIKeyMiddleware


async def _ok(request):
    return JSONResponse({"success": True})


def _make_app(api_key):
    app = Starlette(
        routes=[
            Route("/api/thing", _ok),
            Route("/", _ok),
        ],
        middleware=[Middleware(APIKeyMiddleware, api_key=api_key)],
    )
    return app


@pytest.fixture
def client():
    app = _make_app("secret123")
    with TestClient(app) as c:
        yield c


def test_api_route_without_key_is_rejected(client):
    resp = client.get("/api/thing")
    assert resp.status_code == 401
    assert resp.json()["success"] is False


def test_api_route_with_wrong_key_is_rejected(client):
    resp = client.get("/api/thing", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_api_route_with_correct_header_key_is_allowed(client):
    resp = client.get("/api/thing", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_api_route_with_correct_query_param_key_is_allowed(client):
    resp = client.get("/api/thing?api_key=secret123")
    assert resp.status_code == 200


def test_non_api_route_is_never_gated(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_middleware_not_applied_when_no_key_configured():
    app = Starlette(routes=[Route("/api/thing", _ok)])
    with TestClient(app) as c:
        resp = c.get("/api/thing")
        assert resp.status_code == 200
