from __future__ import annotations

import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .config import DATA_DIR, DB_PATH


NODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    ssh_port INTEGER NOT NULL,
    ssh_user TEXT NOT NULL,
    ssh_password TEXT NOT NULL,
    protocol_type TEXT NOT NULL DEFAULT 'vless_reality_singbox',
    front_node_id TEXT,
    backend_node_id TEXT,
    chain_mode TEXT,
    public_port INTEGER NOT NULL,
    listen_port INTEGER NOT NULL,
    selected_reality_target TEXT,
    generated_uuid TEXT,
    generated_private_key TEXT,
    generated_public_key TEXT,
    generated_short_id TEXT,
    last_vless_link TEXT,
    cf_host TEXT,
    cf_tunnel_token TEXT,
    ws_port INTEGER NOT NULL DEFAULT 8080,
    ws_path TEXT NOT NULL DEFAULT '/',
    agent_token TEXT,
    status TEXT NOT NULL DEFAULT 'never_deployed',
    last_seen_at TEXT,
    last_report_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(front_node_id) REFERENCES nodes(node_id),
    FOREIGN KEY(backend_node_id) REFERENCES nodes(node_id)
);
"""

DEPLOY_SCHEMA = """
CREATE TABLE IF NOT EXISTS deployments (
    deploy_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    result TEXT NOT NULL,
    failure_stage TEXT,
    summary_log TEXT,
    raw_log TEXT,
    generated_vless_link TEXT,
    FOREIGN KEY(node_id) REFERENCES nodes(node_id)
);
"""

REPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    report_time TEXT NOT NULL,
    overall_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(node_id) REFERENCES nodes(node_id)
);
"""

SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

TAG_SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    tag_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#4c8dff',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

NODE_TAG_SCHEMA = """
CREATE TABLE IF NOT EXISTS node_tags (
    node_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    PRIMARY KEY (node_id, tag_id),
    FOREIGN KEY(node_id) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
);
"""


DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()



def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}



def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")



def migrate_db(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "nodes", "front_node_id", "TEXT")
    _ensure_column(conn, "nodes", "backend_node_id", "TEXT")
    _ensure_column(conn, "nodes", "chain_mode", "TEXT")
    _ensure_column(conn, "nodes", "manual_country_code", "TEXT")
    _ensure_column(conn, "nodes", "manual_region_label", "TEXT")
    _ensure_column(conn, "nodes", "cf_host", "TEXT")
    _ensure_column(conn, "nodes", "cf_tunnel_token", "TEXT")
    _ensure_column(conn, "nodes", "ws_port", "INTEGER NOT NULL DEFAULT 8080")
    _ensure_column(conn, "nodes", "ws_path", "TEXT NOT NULL DEFAULT '/'")



def init_db() -> None:
    with get_conn() as conn:
        conn.execute(NODE_SCHEMA)
        conn.execute(DEPLOY_SCHEMA)
        conn.execute(REPORT_SCHEMA)
        conn.execute(SETTINGS_SCHEMA)
        conn.execute(TAG_SCHEMA)
        conn.execute(NODE_TAG_SCHEMA)
        migrate_db(conn)



def list_nodes() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                nodes.*,
                front.name AS front_node_name,
                backend.name AS backend_node_name
            FROM nodes
            LEFT JOIN nodes AS front ON nodes.front_node_id = front.node_id
            LEFT JOIN nodes AS backend ON nodes.backend_node_id = backend.node_id
            ORDER BY nodes.updated_at DESC, nodes.created_at DESC
            """
        ).fetchall()



def list_direct_vless_nodes() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM nodes
            WHERE protocol_type = 'vless_reality_singbox'
              AND TRIM(COALESCE(ip, '')) != ''
              AND COALESCE(public_port, 0) > 0
              AND TRIM(COALESCE(last_vless_link, '')) != ''
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()


def list_chain_backend_nodes() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM nodes
            WHERE protocol_type = 'vless_reality_singbox'
              AND TRIM(COALESCE(ip, '')) != ''
              AND COALESCE(public_port, 0) > 0
              AND TRIM(COALESCE(last_vless_link, '')) != ''
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()


def list_subscribable_nodes() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM nodes
            WHERE TRIM(COALESCE(last_vless_link, '')) != ''
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()



def get_node(node_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                nodes.*,
                front.name AS front_node_name,
                backend.name AS backend_node_name
            FROM nodes
            LEFT JOIN nodes AS front ON nodes.front_node_id = front.node_id
            LEFT JOIN nodes AS backend ON nodes.backend_node_id = backend.node_id
            WHERE nodes.node_id = ?
            """,
            (node_id,),
        ).fetchone()



def find_node_by_endpoint(ip: str, ssh_port: int, exclude_node_id: str | None = None) -> sqlite3.Row | None:
    query = "SELECT * FROM nodes WHERE ip = ? AND ssh_port = ? AND protocol_type = 'vless_reality_singbox'"
    params: list[Any] = [ip, ssh_port]
    if exclude_node_id:
        query += " AND node_id != ?"
        params.append(exclude_node_id)
    with get_conn() as conn:
        return conn.execute(query, tuple(params)).fetchone()



def build_node_id() -> str:
    return f"node_{uuid.uuid4().hex[:12]}"



def build_agent_token() -> str:
    return secrets.token_urlsafe(24)



def build_subscription_token() -> str:
    return secrets.token_urlsafe(32)



def get_or_create_subscription_token() -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            ("subscription_token",),
        ).fetchone()
        if row and row["setting_value"]:
            return row["setting_value"]
        token = build_subscription_token()
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
            ("subscription_token", token, now_iso()),
        )
        return token



def validate_subscription_token(token: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            ("subscription_token",),
        ).fetchone()
        if not row:
            return False
        return secrets.compare_digest(token, row["setting_value"])



def create_node_record(payload: dict[str, Any]) -> str:
    node_id = build_node_id()
    ts = now_iso()
    protocol_type = payload.get("protocol_type") or "vless_reality_singbox"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nodes (
                node_id, name, ip, ssh_port, ssh_user, ssh_password,
                protocol_type, front_node_id, backend_node_id, chain_mode,
                public_port, listen_port,
                selected_reality_target, generated_uuid, generated_private_key,
                generated_public_key, generated_short_id, last_vless_link,
                cf_host, cf_tunnel_token, ws_port, ws_path,
                agent_token, status, last_seen_at, last_report_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                payload["name"],
                payload["ip"],
                payload["ssh_port"],
                payload["ssh_user"],
                payload["ssh_password"],
                protocol_type,
                payload.get("front_node_id"),
                payload.get("backend_node_id"),
                payload.get("chain_mode"),
                payload["public_port"],
                payload["listen_port"],
                payload.get("selected_reality_target"),
                payload.get("generated_uuid"),
                payload.get("generated_private_key"),
                payload.get("generated_public_key"),
                payload.get("generated_short_id"),
                payload.get("last_vless_link", ""),
                payload.get("cf_host"),
                payload.get("cf_tunnel_token"),
                payload.get("ws_port") or 8080,
                payload.get("ws_path") or "/",
                build_agent_token(),
                "never_deployed",
                None,
                None,
                ts,
                ts,
            ),
        )
    return node_id



def update_node_record(node_id: str, payload: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE nodes
            SET name = ?,
                ip = ?,
                ssh_port = ?,
                ssh_user = ?,
                ssh_password = ?,
                protocol_type = COALESCE(?, protocol_type),
                front_node_id = ?,
                backend_node_id = ?,
                chain_mode = ?,
                public_port = ?,
                listen_port = ?,
                manual_country_code = ?,
                manual_region_label = ?,
                last_vless_link = ?,
                cf_host = ?,
                cf_tunnel_token = ?,
                ws_port = ?,
                ws_path = ?,
                updated_at = ?
            WHERE node_id = ?
            """,
            (
                payload["name"],
                payload["ip"],
                payload["ssh_port"],
                payload["ssh_user"],
                payload["ssh_password"],
                payload.get("protocol_type"),
                payload.get("front_node_id"),
                payload.get("backend_node_id"),
                payload.get("chain_mode"),
                payload["public_port"],
                payload["listen_port"],
                payload.get("manual_country_code"),
                payload.get("manual_region_label"),
                payload.get("last_vless_link"),
                payload.get("cf_host"),
                payload.get("cf_tunnel_token"),
                payload.get("ws_port") or 8080,
                payload.get("ws_path") or "/",
                now_iso(),
                node_id,
            ),
        )



def extract_vless_uuid(vless_link: str | None) -> str:
    link = str(vless_link or "").strip()
    if not link.startswith("vless://"):
        return ""
    try:
        parsed = urlparse(link)
    except ValueError:
        return ""
    return parsed.username or ""


def rebuild_tunnel_vless_link(*, uuid_value: str, cf_host: str, ws_path: str, name: str) -> str:
    safe_path = ws_path or "/"
    return (
        f"vless://{uuid_value}@{cf_host}:443"
        f"?encryption=none&security=tls&type=ws&host={cf_host}&path={safe_path}&sni={cf_host}"
        f"#{name}"
    )


def backfill_tunnel_generated_fields() -> list[dict[str, str]]:
    updated: list[dict[str, str]] = []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT node_id, name, cf_host, ws_path, generated_uuid, last_vless_link
            FROM nodes
            WHERE protocol_type = 'cf_vless_ws'
            """
        ).fetchall()
        for row in rows:
            cf_host = str(row["cf_host"] or "").strip()
            current_uuid = str(row["generated_uuid"] or "").strip()
            link_uuid = extract_vless_uuid(row["last_vless_link"])
            uuid_value = current_uuid or link_uuid
            if not (cf_host and uuid_value):
                continue
            last_vless_link = str(row["last_vless_link"] or "").strip()
            if not last_vless_link:
                last_vless_link = rebuild_tunnel_vless_link(
                    uuid_value=uuid_value,
                    cf_host=cf_host,
                    ws_path=str(row["ws_path"] or "/").strip() or "/",
                    name=str(row["name"] or row["node_id"]),
                )
            if current_uuid == uuid_value and str(row["last_vless_link"] or "").strip() == last_vless_link:
                continue
            conn.execute(
                """
                UPDATE nodes
                SET generated_uuid = ?,
                    last_vless_link = ?,
                    updated_at = ?
                WHERE node_id = ?
                """,
                (uuid_value, last_vless_link, now_iso(), row["node_id"]),
            )
            updated.append({
                "node_id": row["node_id"],
                "name": row["name"] or row["node_id"],
                "generated_uuid": uuid_value,
            })
    return updated

def list_tags() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()


def create_tag(name: str, color: str) -> str:
    tag_id = f"tag_{uuid.uuid4().hex[:10]}"
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tags (tag_id, name, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (tag_id, name, color, ts, ts),
        )
    return tag_id


def delete_tag(tag_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM node_tags WHERE tag_id = ?", (tag_id,))
        conn.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))


def list_node_tag_ids(node_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT tag_id FROM node_tags WHERE node_id = ?", (node_id,)).fetchall()
        return [row["tag_id"] for row in rows]


def set_node_tags(node_id: str, tag_ids: list[str]) -> None:
    clean_ids = [tag_id for tag_id in dict.fromkeys(tag_ids) if tag_id]
    with get_conn() as conn:
        if clean_ids:
            placeholders = ",".join("?" for _ in clean_ids)
            rows = conn.execute(f"SELECT tag_id FROM tags WHERE tag_id IN ({placeholders})", clean_ids).fetchall()
            clean_ids = [row["tag_id"] for row in rows]
        conn.execute("DELETE FROM node_tags WHERE node_id = ?", (node_id,))
        for tag_id in clean_ids:
            conn.execute("INSERT OR IGNORE INTO node_tags (node_id, tag_id) VALUES (?, ?)", (node_id, tag_id))


def list_node_tags_map() -> dict[str, list[dict[str, str]]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT nt.node_id, t.tag_id, t.name, t.color
            FROM node_tags nt
            JOIN tags t ON nt.tag_id = t.tag_id
            ORDER BY t.name COLLATE NOCASE
            """
        ).fetchall()
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        result.setdefault(row["node_id"], []).append({"tag_id": row["tag_id"], "name": row["name"], "color": row["color"]})
    return result



def ingest_agent_report(node_id: str, overall_status: str, payload_json: str, *, report_time: str | None = None) -> None:
    report_time = report_time or now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_reports (node_id, report_time, overall_status, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (node_id, report_time, overall_status, payload_json, now_iso()),
        )
        conn.execute(
            """
            UPDATE nodes
            SET status = ?,
                last_seen_at = ?,
                last_report_json = ?,
                updated_at = ?
            WHERE node_id = ?
            """,
            (overall_status, report_time, payload_json, now_iso(), node_id),
        )



def delete_node_record(node_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM deployments WHERE node_id = ?", (node_id,))
        conn.execute("DELETE FROM agent_reports WHERE node_id = ?", (node_id,))
        conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))


def create_demo_node() -> None:
    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM nodes LIMIT 1").fetchone()
        if exists:
            return
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO nodes (
                node_id, name, ip, ssh_port, ssh_user, ssh_password,
                protocol_type, front_node_id, backend_node_id, chain_mode,
                public_port, listen_port,
                selected_reality_target, generated_uuid, generated_private_key,
                generated_public_key, generated_short_id, last_vless_link,
                cf_host, cf_tunnel_token, ws_port, ws_path,
                agent_token, status, last_seen_at, last_report_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "node_demo_001",
                "Demo NAT",
                "203.0.113.10",
                22,
                "root",
                "demo-password",
                "vless_reality_singbox",
                None,
                None,
                None,
                443,
                443,
                "www.microsoft.com",
                "11111111-1111-1111-1111-111111111111",
                "demo-private-key",
                "demo-public-key",
                "abcd1234",
                "",
                "demo-agent-token",
                "never_deployed",
                None,
                None,
                ts,
                ts,
            ),
        )



def list_deployments_for_node(node_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM deployments WHERE node_id = ? ORDER BY started_at DESC",
            (node_id,),
        ).fetchall()



def build_deploy_id() -> str:
    return f"deploy_{uuid.uuid4().hex[:12]}"



def create_deployment_record(*, node_id: str, action_type: str) -> str:
    deploy_id = build_deploy_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO deployments (
                deploy_id, node_id, action_type, started_at, ended_at,
                result, failure_stage, summary_log, raw_log, generated_vless_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deploy_id,
                node_id,
                action_type,
                ts,
                None,
                "pending",
                None,
                "任务已创建，等待执行",
                "[stage] created",
                None,
            ),
        )
        conn.execute(
            "UPDATE nodes SET status = ?, updated_at = ? WHERE node_id = ?",
            ("deploying", ts, node_id),
        )
    return deploy_id



def mark_deployment_running(deploy_id: str) -> None:
    with get_conn() as conn:
        deployment = conn.execute(
            "SELECT node_id FROM deployments WHERE deploy_id = ?",
            (deploy_id,),
        ).fetchone()
        if not deployment:
            return
        ts = now_iso()
        conn.execute(
            "UPDATE deployments SET result = ?, summary_log = ?, raw_log = ? WHERE deploy_id = ?",
            ("running", "任务执行中", "[stage] running", deploy_id),
        )
        conn.execute(
            "UPDATE nodes SET status = ?, updated_at = ? WHERE node_id = ?",
            ("deploying", ts, deployment["node_id"]),
        )



def mark_deployment_success(
    deploy_id: str,
    *,
    summary_log: str,
    raw_log: str,
    generated_vless_link: str,
) -> None:
    with get_conn() as conn:
        deployment = conn.execute(
            "SELECT node_id FROM deployments WHERE deploy_id = ?",
            (deploy_id,),
        ).fetchone()
        if not deployment:
            return
        ts = now_iso()
        conn.execute(
            """
            UPDATE deployments
            SET ended_at = ?, result = ?, failure_stage = ?,
                summary_log = ?, raw_log = ?, generated_vless_link = ?
            WHERE deploy_id = ?
            """,
            (ts, "success", None, summary_log, raw_log, generated_vless_link, deploy_id),
        )
        conn.execute(
            """
            UPDATE nodes
            SET status = ?, last_vless_link = ?, updated_at = ?
            WHERE node_id = ?
            """,
            ("offline", generated_vless_link, ts, deployment["node_id"]),
        )



def mark_deployment_failed(
    deploy_id: str,
    *,
    failure_stage: str,
    summary_log: str,
    raw_log: str,
) -> None:
    with get_conn() as conn:
        deployment = conn.execute(
            "SELECT node_id FROM deployments WHERE deploy_id = ?",
            (deploy_id,),
        ).fetchone()
        if not deployment:
            return
        ts = now_iso()
        conn.execute(
            """
            UPDATE deployments
            SET ended_at = ?, result = ?, failure_stage = ?, summary_log = ?, raw_log = ?
            WHERE deploy_id = ?
            """,
            (ts, "failed", failure_stage, summary_log, raw_log, deploy_id),
        )
        conn.execute(
            "UPDATE nodes SET status = ?, updated_at = ? WHERE node_id = ?",
            ("deploy_failed", ts, deployment["node_id"]),
        )



def update_node_generated_fields(
    node_id: str,
    *,
    selected_reality_target: str,
    generated_uuid: str,
    generated_private_key: str,
    generated_public_key: str,
    generated_short_id: str,
    last_vless_link: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE nodes
            SET selected_reality_target = ?,
                generated_uuid = ?,
                generated_private_key = ?,
                generated_public_key = ?,
                generated_short_id = ?,
                last_vless_link = ?,
                updated_at = ?
            WHERE node_id = ?
            """,
            (
                selected_reality_target,
                generated_uuid,
                generated_private_key,
                generated_public_key,
                generated_short_id,
                last_vless_link,
                now_iso(),
                node_id,
            ),
        )



def mark_node_deployed_from_report(node_id: str, payload: dict[str, Any]) -> None:
    generated_uuid = str(payload.get("generated_uuid") or "").strip()
    generated_public_key = str(payload.get("generated_public_key") or "").strip()
    generated_short_id = str(payload.get("generated_short_id") or "").strip()
    selected_reality_target = str(payload.get("selected_reality_target") or "").strip()
    public_ip = str(payload.get("public_ip") or "").strip()
    public_port = payload.get("public_port")
    node_name = ""

    if not (generated_uuid and generated_public_key and generated_short_id and public_ip and public_port):
        return

    try:
        public_port = int(public_port)
    except (TypeError, ValueError):
        return

    with get_conn() as conn:
        node = conn.execute("SELECT name, last_vless_link FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not node:
            return
        node_name = node["name"] or node_id
        last_vless_link = node["last_vless_link"] or ""
        if not selected_reality_target:
            selected_reality_target = "www.microsoft.com"
        if not last_vless_link:
            last_vless_link = (
                f"vless://{generated_uuid}@{public_ip}:{public_port}"
                f"?security=reality&sni={selected_reality_target}"
                f"&pbk={generated_public_key}&sid={generated_short_id}"
                f"&type=tcp&flow=xtls-rprx-vision#{node_name}"
            )
        conn.execute(
            """
            UPDATE nodes
            SET selected_reality_target = COALESCE(NULLIF(?, ''), selected_reality_target),
                generated_uuid = COALESCE(NULLIF(?, ''), generated_uuid),
                generated_public_key = COALESCE(NULLIF(?, ''), generated_public_key),
                generated_short_id = COALESCE(NULLIF(?, ''), generated_short_id),
                last_vless_link = COALESCE(NULLIF(?, ''), last_vless_link),
                status = CASE WHEN status = 'never_deployed' THEN 'online' ELSE status END,
                updated_at = ?
            WHERE node_id = ?
            """,
            (
                selected_reality_target,
                generated_uuid,
                generated_public_key,
                generated_short_id,
                last_vless_link,
                now_iso(),
                node_id,
            ),
        )



def get_deployment(deploy_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM deployments WHERE deploy_id = ?",
            (deploy_id,),
        ).fetchone()
