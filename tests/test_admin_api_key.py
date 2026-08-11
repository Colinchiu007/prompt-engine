"""API Key 管理端点的认证测试。"""
import pytest
from fastapi.testclient import TestClient

from prompt_engine.api import rest


ADMIN_TOKEN = "test-admin-token-with-at-least-32-characters"


def _client(monkeypatch, tmp_path, token=ADMIN_TOKEN):
    monkeypatch.setattr(rest, "ENV_FILE", tmp_path / ".env")
    if token is None:
        monkeypatch.delenv("PROMPT_ENGINE_ADMIN_TOKEN", raising=False)
    else:
        monkeypatch.setenv("PROMPT_ENGINE_ADMIN_TOKEN", token)
    return TestClient(rest.app, raise_server_exceptions=False)


def test_api_key_write_is_disabled_without_admin_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, token=None)

    response = client.post(
        "/v1/config/api-key",
        json={"provider": "minimax", "api_key": "secret-value"},
    )

    assert response.status_code == 503
    assert client.get("/v1/config/api-key").status_code == 503
    assert not rest.ENV_FILE.exists()


@pytest.mark.parametrize("token", ["short-token", "replace_with_a_strong_admin_token"])
def test_api_key_write_is_disabled_for_weak_or_placeholder_admin_token(
    monkeypatch,
    tmp_path,
    token,
):
    client = _client(monkeypatch, tmp_path, token=token)

    response = client.post(
        "/v1/config/api-key",
        json={"provider": "minimax", "api_key": "secret-value"},
    )

    assert response.status_code == 503
    assert not rest.ENV_FILE.exists()


def test_api_key_endpoints_require_bearer_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    missing = client.get("/v1/config/api-key")
    wrong = client.get(
        "/v1/config/api-key",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert wrong.status_code == 403


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic credential",
        f"bearer {ADMIN_TOKEN}",
        "Bearer",
        f"Bearer  {ADMIN_TOKEN}",
        f"Bearer {ADMIN_TOKEN} extra",
    ],
)
def test_api_key_endpoints_reject_malformed_bearer_tokens(
    monkeypatch,
    tmp_path,
    authorization,
):
    client = _client(monkeypatch, tmp_path)

    response = client.get(
        "/v1/config/api-key",
        headers={"Authorization": authorization},
    )

    assert response.status_code == 401


def test_authorized_api_key_write_and_status(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    saved = client.post(
        "/v1/config/api-key",
        headers=headers,
        json={"provider": "minimax", "api_key": "secret-value"},
    )
    status = client.get("/v1/config/api-key", headers=headers)

    assert saved.status_code == 200
    assert "MINIMAX_API_KEY=secret-value" in rest.ENV_FILE.read_text(encoding="utf-8")
    assert status.status_code == 200
    assert "MINIMAX_API_KEY" in status.json()["configured"]


def test_authorized_ai_router_key_write_and_status(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    saved = client.post(
        "/v1/config/api-key",
        headers=headers,
        json={"provider": "ai_router", "api_key": "router-project-secret"},
    )
    status = client.get("/v1/config/api-key", headers=headers)

    assert saved.status_code == 200
    assert saved.json()["env_var"] == "AI_ROUTER_PROJECT_KEY"
    assert "AI_ROUTER_PROJECT_KEY=router-project-secret" in rest.ENV_FILE.read_text(
        encoding="utf-8"
    )
    assert "AI_ROUTER_PROJECT_KEY" in status.json()["configured"]


def test_api_key_status_ignores_example_values(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    rest.ENV_FILE.write_text(
        "MINIMAX_API_KEY=your_minimax_api_key_here\n"
        "AI_ROUTER_PROJECT_KEY=router-project-secret\n"
        f"PROMPT_ENGINE_ADMIN_TOKEN={ADMIN_TOKEN}\n",
        encoding="utf-8",
    )

    status = client.get(
        "/v1/config/api-key",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )

    assert status.status_code == 200
    assert status.json()["configured"] == ["AI_ROUTER_PROJECT_KEY"]


@pytest.mark.parametrize(
    "api_key",
    [
        "secret-value\nINJECTED_KEY=owned",
        "secret-value\rINJECTED_KEY=owned",
        "secret\tvalue",
        "secret-value\n",
        {"unexpected": "value"},
    ],
)
def test_api_key_write_rejects_control_characters_and_non_strings(
    monkeypatch,
    tmp_path,
    api_key,
):
    """管理端点不得允许注入额外的环境变量。"""
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/v1/config/api-key",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        json={"provider": "minimax", "api_key": api_key},
    )

    assert response.status_code == 400
    assert not rest.ENV_FILE.exists()


def test_api_key_write_rejects_non_string_provider(monkeypatch, tmp_path):
    """provider 类型错误时应返回受控的客户端错误。"""
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/v1/config/api-key",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        json={"provider": ["minimax"], "api_key": "secret-value"},
    )

    assert response.status_code == 400
    assert not rest.ENV_FILE.exists()


def test_settings_page_sends_admin_bearer_token():
    html = (rest.ENV_FILE.parent / "prompt_engine" / "web" / "index.html")
    if not html.exists():
        html = rest.ENV_FILE.parent / "web" / "index.html"
    content = html.read_text(encoding="utf-8")

    assert "adminToken" in content
    assert "sessionStorage" in content
    assert "Authorization: `Bearer ${adminToken.value.trim()}`" in content
    assert 'label="AI Router" value="ai_router"' in content
