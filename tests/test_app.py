from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("NAT_WEBUI_DB_PATH", f"/tmp/nat_webui_test_{uuid.uuid4().hex}.db")

from app import jobs, main
from app.db import init_db
from app.main import app

init_db()


client = TestClient(app)


def login() -> None:
    response = client.post(
        "/login",
        data={"username": "admin", "password": "change-me-before-production"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_login_page() -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "管理员登录" in response.text


def test_login_success_redirects_to_nodes() -> None:
    response = client.post(
        "/login",
        data={"username": "admin", "password": "change-me-before-production"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/nodes"


def test_nodes_requires_login() -> None:
    fresh = TestClient(app)
    response = fresh.get("/nodes", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_nodes_page_after_login() -> None:
    login()
    response = client.get("/nodes")
    assert response.status_code == 200
    assert "节点列表" in response.text
    assert "新建节点" in response.text


def test_create_reinstall_and_delete_node_flow(monkeypatch) -> None:
    login()

    unique_suffix = "35222"
    create_response = client.post(
        "/nodes/new",
        data={
            "name": "NAT_TEST",
            "ip": "198.51.100.20",
            "ssh_port": unique_suffix,
            "ssh_user": "root",
            "ssh_password": "test-pass",
            "public_port": "44321",
            "listen_port": "2443",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303
    detail_url = create_response.headers["location"]
    assert detail_url.startswith("/nodes/node_")

    detail_response = client.get(detail_url)
    assert detail_response.status_code == 200
    assert "NAT_TEST" in detail_response.text
    assert "198.51.100.20" in detail_response.text

    node_id = detail_url.rsplit("/", 1)[-1]
    edit_response = client.post(
        f"/nodes/{node_id}/edit",
        data={
            "name": "NAT_TEST_EDITED",
            "ip": "198.51.100.20",
            "ssh_port": unique_suffix,
            "ssh_user": "root",
            "ssh_password": "test-pass-2",
            "public_port": "44322",
            "listen_port": "2444",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 303
    assert edit_response.headers["location"] == detail_url

    edited_detail = client.get(detail_url)
    assert "NAT_TEST_EDITED" in edited_detail.text
    assert "44322" in edited_detail.text
    assert "2444" in edited_detail.text

    class FakeDeployResult:
        summary_log = "真实部署已完成"
        raw_log = "[stage] ssh_probe\nCONNECTED\n[stage] deploy\nOK: deploy finished"
        generated_vless_link = "vless://fake-uuid@198.51.100.20:44322?security=reality#NAT_TEST_EDITED"
        generated_uuid = "fake-uuid"
        generated_private_key = "fake-private"
        generated_public_key = "fake-public"
        generated_short_id = "fake-short-id"
        selected_reality_target = "www.microsoft.com"

    monkeypatch.setattr(jobs, "run_real_deploy", lambda node: FakeDeployResult())

    submitted: list[tuple[str, dict]] = []

    def fake_submit(*, deploy_id: str, node: dict) -> None:
        submitted.append((deploy_id, node))
        jobs._run_reinstall_job(deploy_id, node)

    monkeypatch.setattr(main, "submit_reinstall_job", fake_submit)

    reinstall_response = client.post(f"/nodes/{node_id}/reinstall", follow_redirects=False)
    assert reinstall_response.status_code == 303
    deploy_url = reinstall_response.headers["location"]
    assert deploy_url.startswith("/deployments/deploy_")
    assert submitted

    deploy_detail = client.get(deploy_url)
    assert deploy_detail.status_code == 200
    assert "部署任务" in deploy_detail.text
    assert "success" in deploy_detail.text
    assert "OK: deploy finished" in deploy_detail.text

    api_response = client.get(deploy_url.replace("/deployments/", "/api/deployments/"))
    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["result"] == "success"
    assert payload["running"] is False

    after_reinstall = client.get(detail_url)
    assert "vless://fake-uuid@198.51.100.20:44322" in after_reinstall.text

    delete_response = client.post(f"/nodes/{node_id}/delete", follow_redirects=False)
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == "/nodes"

    missing = client.get(detail_url)
    assert missing.status_code == 404
    assert "节点不存在" in missing.text


def test_create_node_rejects_duplicate_ip_and_ssh_port() -> None:
    login()
    first = client.post(
        "/nodes/new",
        data={
            "name": "NAT_DUP_FIRST",
            "ip": "203.0.113.10",
            "ssh_port": "22",
            "ssh_user": "root",
            "ssh_password": "dup-pass",
            "public_port": "44443",
            "listen_port": "44443",
        },
        follow_redirects=False,
    )
    assert first.status_code == 303

    response = client.post(
        "/nodes/new",
        data={
            "name": "NAT_DUP_SECOND",
            "ip": "203.0.113.10",
            "ssh_port": "22",
            "ssh_user": "root",
            "ssh_password": "dup-pass",
            "public_port": "44443",
            "listen_port": "44443",
        },
    )
    assert response.status_code == 200
    assert "已存在相同 IP + SSH 端口 的节点记录" in response.text
