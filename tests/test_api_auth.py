from fastapi.testclient import TestClient

from support_agent_lab.api.main import app


def test_chat_user_id_must_match_demo_actor():
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat/sessions",
        headers={"X-Demo-User": "user_guest"},
        json={"user_id": "user_demo"},
    )

    assert response.status_code == 403


def test_admin_endpoints_require_admin_role():
    client = TestClient(app)

    forbidden = client.get("/api/v1/admin/tools")
    allowed = client.get("/api/v1/admin/tools", headers={"X-Demo-Role": "admin"})

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_run_trace_requires_owner_or_admin():
    client = TestClient(app)
    session = client.post("/api/v1/chat/sessions", json={"user_id": "user_demo"}).json()
    message = client.post(
        "/api/v1/chat/messages",
        json={
            "conversation_id": session["conversation_id"],
            "user_id": "user_demo",
            "content": "\u6211\u8ba2\u5355 A1001 \u7684\u8033\u673a\u574f\u4e86\uff0c\u80fd\u9000\u5417\uff1f",
        },
    ).json()

    forbidden = client.get(
        f"/api/v1/agent/runs/{message['trace_id']}",
        headers={"X-Demo-User": "user_guest"},
    )
    owner = client.get(f"/api/v1/agent/runs/{message['trace_id']}")
    admin = client.get(
        f"/api/v1/agent/runs/{message['trace_id']}",
        headers={"X-Demo-User": "user_guest", "X-Demo-Role": "admin"},
    )

    assert forbidden.status_code == 403
    assert owner.status_code == 200
    assert admin.status_code == 200

