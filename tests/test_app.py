from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAT_WEBUI_DB_PATH", f"/tmp/nat_webui_test_{uuid.uuid4().hex}.db")

from app import jobs, main
from app.db import create_node_record, get_node, init_db, list_nodes
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
    assert "复制 v2rayN 订阅 URL" in response.text
    assert "复制 Clash 订阅 URL" in response.text


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
    assert "title=\"复制链接\"" in after_reinstall.text

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


def test_create_chain_node_record_preserves_front_and_backend_references() -> None:
    front_id = create_node_record(
        {
            "name": "FRONT_FOR_CHAIN",
            "ip": "198.51.100.31",
            "ssh_port": 2231,
            "ssh_user": "root",
            "ssh_password": "front-pass",
            "public_port": 443,
            "listen_port": 443,
        }
    )
    backend_id = create_node_record(
        {
            "name": "BACKEND_FOR_CHAIN",
            "ip": "198.51.100.32",
            "ssh_port": 2232,
            "ssh_user": "root",
            "ssh_password": "backend-pass",
            "public_port": 443,
            "listen_port": 443,
        }
    )
    chain_id = create_node_record(
        {
            "name": "CHAIN_FRONT_TO_BACKEND",
            "ip": "198.51.100.31",
            "ssh_port": 2231,
            "ssh_user": "root",
            "ssh_password": "front-pass",
            "protocol_type": "vless_chain",
            "front_node_id": front_id,
            "backend_node_id": backend_id,
            "chain_mode": "vless_reality_to_vless_reality",
            "public_port": 443,
            "listen_port": 443,
        }
    )

    chain = get_node(chain_id)
    assert chain is not None
    assert chain["protocol_type"] == "vless_chain"
    assert chain["front_node_id"] == front_id
    assert chain["backend_node_id"] == backend_id
    assert chain["chain_mode"] == "vless_reality_to_vless_reality"
    assert chain["front_node_name"] == "FRONT_FOR_CHAIN"
    assert chain["backend_node_name"] == "BACKEND_FOR_CHAIN"

    listed = {node["node_id"]: node for node in list_nodes()}
    assert listed[chain_id]["front_node_name"] == "FRONT_FOR_CHAIN"
    assert listed[chain_id]["backend_node_name"] == "BACKEND_FOR_CHAIN"


def test_edit_chain_node_name_redirects_to_detail_and_updates() -> None:
    login()
    front_id = create_node_record(
        {
            "name": "FRONT_EDIT_CHAIN",
            "ip": "198.51.100.41",
            "ssh_port": 2241,
            "ssh_user": "root",
            "ssh_password": "front-pass",
            "public_port": 443,
            "listen_port": 443,
        }
    )
    backend_id = create_node_record(
        {
            "name": "BACKEND_EDIT_CHAIN",
            "ip": "198.51.100.42",
            "ssh_port": 2242,
            "ssh_user": "root",
            "ssh_password": "backend-pass",
            "public_port": 443,
            "listen_port": 443,
        }
    )
    chain_id = create_node_record(
        {
            "name": "CHAIN_OLD_NAME",
            "ip": "198.51.100.41",
            "ssh_port": 2241,
            "ssh_user": "root",
            "ssh_password": "front-pass",
            "protocol_type": "vless_chain",
            "front_node_id": front_id,
            "backend_node_id": backend_id,
            "chain_mode": "vless_reality_to_vless_reality",
            "public_port": 443,
            "listen_port": 443,
        }
    )

    response = client.post(
        f"/nodes/{chain_id}/edit",
        data={
            "name": "CHAIN_NEW_NAME",
            "protocol_type": "vless_chain",
            "front_node_id": front_id,
            "backend_node_id": backend_id,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/nodes/{chain_id}"
    assert get_node(chain_id)["name"] == "CHAIN_NEW_NAME"

    detail_response = client.get(f"/nodes/{chain_id}")
    assert detail_response.status_code == 200
    assert "CHAIN_NEW_NAME" in detail_response.text


def test_phase2_markdown_exists() -> None:
    with open("PHASE2.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "Phase 2 Development Constraints" in content
    assert "VLESS + Reality -> VLESS + Reality" in content
