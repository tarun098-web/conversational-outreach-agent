from fastapi.testclient import TestClient
from outreach_agent.main import create_app


def test_dashboard_demo_and_health(settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready").json()
        assert ready["background_polling"] is False
        demo = client.post("/api/v1/demo")
        assert demo.status_code == 200
        page = client.get("/", params={"conversation": demo.json()["conversation_id"]})
        assert page.status_code == 200
        assert "Outreach Flow" in page.text
        assert "Intent + risk" in page.text
