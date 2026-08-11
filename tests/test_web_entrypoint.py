"""内置 Web 控制台入口测试。"""

from fastapi.testclient import TestClient

from prompt_engine.api.rest import app


def test_web_root_redirects_to_embedded_console():
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/web/"
