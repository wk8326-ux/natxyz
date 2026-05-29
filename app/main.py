from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import login_required, verify_login
from .config import AGENT_REPORT_PATH, APP_DIR, APP_NAME, SESSION_COOKIE, SESSION_SECRET, STATUS_STALE_MINUTES
from .db import (
    create_demo_node,
    create_deployment_record,
    create_node_record,
    delete_node_record,
    find_node_by_endpoint,
    get_deployment,
    get_node,
    get_or_create_subscription_token,
    ingest_agent_report,
    init_db,
    list_deployments_for_node,
    list_nodes,
    list_subscribable_nodes,
    mark_node_deployed_from_report,
    update_node_record,
    validate_subscription_token,
)
from .jobs import is_deploy_running, submit_reinstall_job

app = FastAPI(title=APP_NAME)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE,
)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    create_demo_node()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("auth"):
        return RedirectResponse(url="/nodes", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "title": "登录", "error": None},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not verify_login(username, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "title": "登录", "error": "用户名或密码错误"},
            status_code=401,
        )
    request.session["auth"] = True
    return RedirectResponse(url="/nodes", status_code=303)


@app.post(AGENT_REPORT_PATH)
async def agent_report_ingest(request: Request):
    payload = await request.json()
    node_id = str(payload.get("node_id", "")).strip()
    agent_token = str(payload.get("agent_token", "")).strip()
    if not node_id or not agent_token:
        return JSONResponse({"ok": False, "error": "missing_node_id_or_token"}, status_code=400)

    node = get_node(node_id)
    if not node:
        return JSONResponse({"ok": False, "error": "node_not_found"}, status_code=404)
    if agent_token != (node["agent_token"] or ""):
        return JSONResponse({"ok": False, "error": "invalid_agent_token"}, status_code=403)

    overall_status = str(payload.get("overall_status", "online")).strip() or "online"
    report_time = str(payload.get("report_time", "")).strip() or datetime.now(timezone.utc).isoformat()
    ingest_agent_report(node_id, overall_status, json.dumps(payload, ensure_ascii=False), report_time=report_time)
    mark_node_deployed_from_report(node_id, payload)
    return JSONResponse({"ok": True})


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


REQUIRED_FIELDS = [
    "name",
    "ip",
    "ssh_port",
    "ssh_user",
    "ssh_password",
    "public_port",
    "listen_port",
]



def clean_node_form(form: dict[str, str]) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    cleaned: dict[str, object] = {}

    for key in REQUIRED_FIELDS:
        value = str(form.get(key, "")).strip()
        if not value:
            errors.append(f"{key} 不能为空")
        cleaned[key] = value

    for int_key in ["ssh_port", "public_port", "listen_port"]:
        value = str(cleaned.get(int_key, ""))
        if value:
            try:
                number = int(value)
                if number <= 0 or number > 65535:
                    errors.append(f"{int_key} 必须在 1-65535 之间")
                else:
                    cleaned[int_key] = number
            except ValueError:
                errors.append(f"{int_key} 必须是数字")

    return cleaned, errors



def render_node_form(
    request: Request,
    *,
    title: str,
    mode: str,
    form_values: dict[str, object],
    errors: list[str] | None = None,
    node_id: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "node-form.html",
        {
            "request": request,
            "title": title,
            "mode": mode,
            "form_values": form_values,
            "errors": errors or [],
            "node_id": node_id,
        },
    )



def compute_badge(node) -> tuple[str, str]:
    status = node["status"]
    last_seen_at = node["last_seen_at"]
    if status == "online" and last_seen_at:
        try:
            seen = datetime.fromisoformat(last_seen_at)
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - seen > timedelta(minutes=STATUS_STALE_MINUTES):
                return "offline", "离线"
        except ValueError:
            return "offline", "离线"
    mapping = {
        "online": ("online", "在线"),
        "offline": ("offline", "离线"),
        "deploy_failed": ("failed", "部署失败"),
        "never_deployed": ("pending", "未部署"),
        "deploying": ("pending", "部署中"),
    }
    return mapping.get(status, ("pending", status))



def build_install_command(node: dict | object) -> str:
    if isinstance(node, dict):
        node_id = node["node_id"]
        ip = node["ip"]
        ssh_port = node["ssh_port"]
        public_port = node["public_port"]
        listen_port = node["listen_port"]
    else:
        node_id = node["node_id"]
        ip = node["ip"]
        ssh_port = node["ssh_port"]
        public_port = node["public_port"]
        listen_port = node["listen_port"]
    return (
        f"ssh root@{ip} -p {ssh_port} '"
        f"echo deploy-node {node_id} public:{public_port} listen:{listen_port}'"
    )



def build_subscription_url(request: Request) -> str:
    token = get_or_create_subscription_token()
    return str(request.url_for("subscription_feed", token=token))



def build_subscription_payload() -> str:
    links = []
    for node in list_subscribable_nodes():
        link = (node["last_vless_link"] or "").strip()
        if link:
            links.append(link)
    plain = "\n".join(links)
    return base64.b64encode(plain.encode("utf-8")).decode("ascii")



@app.get("/nodes", response_class=HTMLResponse)
@login_required
async def nodes_page(request: Request):
    raw_nodes = list_nodes()
    nodes = []
    for node in raw_nodes:
        badge_class, badge_text = compute_badge(node)
        nodes.append({
            "node_id": node["node_id"],
            "name": node["name"],
            "ip": node["ip"],
            "protocol_type": node["protocol_type"],
            "badge_class": badge_class,
            "badge_text": badge_text,
            "last_vless_link": node["last_vless_link"] or "",
            "can_reinstall": True,
        })
    subscription_url = build_subscription_url(request)
    return templates.TemplateResponse(
        request,
        "nodes.html",
        {
            "request": request,
            "title": "节点列表",
            "nodes": nodes,
            "subscription_url": subscription_url,
        },
    )


@app.get("/sub/{token}", response_class=PlainTextResponse, name="subscription_feed")
async def subscription_feed(token: str):
    if not validate_subscription_token(token):
        return PlainTextResponse("forbidden", status_code=403)
    payload = build_subscription_payload()
    return PlainTextResponse(
        payload,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="nat-subscription.txt"',
        },
    )


@app.get("/nodes/new", response_class=HTMLResponse)
@login_required
async def node_create_page(request: Request):
    return render_node_form(
        request,
        title="新建节点",
        mode="create",
        form_values={
            "name": "",
            "ip": "",
            "ssh_port": 22,
            "ssh_user": "root",
            "ssh_password": "",
            "public_port": "",
            "listen_port": "",
        },
    )


@app.post("/nodes/new", response_class=HTMLResponse)
@login_required
async def node_create_submit(
    request: Request,
    name: str = Form(...),
    ip: str = Form(...),
    ssh_port: str = Form(...),
    ssh_user: str = Form(...),
    ssh_password: str = Form(...),
    public_port: str = Form(...),
    listen_port: str = Form(...),
):
    payload, errors = clean_node_form(
        {
            "name": name,
            "ip": ip,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "ssh_password": ssh_password,
            "public_port": public_port,
            "listen_port": listen_port,
        }
    )

    if not errors:
        exists = find_node_by_endpoint(str(payload["ip"]), int(payload["ssh_port"]))
        if exists:
            errors.append("已存在相同 IP + SSH 端口 的节点记录")

    if errors:
        return render_node_form(
            request,
            title="新建节点",
            mode="create",
            form_values=payload,
            errors=errors,
        )

    node_id = create_node_record(payload)
    return RedirectResponse(url=f"/nodes/{node_id}", status_code=303)


@app.get("/nodes/{node_id}", response_class=HTMLResponse)
@login_required
async def node_detail_page(request: Request, node_id: str):
    node = get_node(node_id)
    if not node:
        return templates.TemplateResponse(
            request,
            "not-found.html",
            {"request": request, "title": "未找到节点", "message": "节点不存在"},
            status_code=404,
        )

    deployments = list_deployments_for_node(node_id)
    badge_class, badge_text = compute_badge(node)
    report = None
    if node["last_report_json"]:
        try:
            report = json.loads(node["last_report_json"])
        except json.JSONDecodeError:
            report = {"raw": node["last_report_json"]}

    latest_deploy_id = deployments[0]["deploy_id"] if deployments else None

    return templates.TemplateResponse(
        request,
        "node-detail.html",
        {
            "request": request,
            "title": node["name"],
            "node": node,
            "deployments": deployments,
            "badge_class": badge_class,
            "badge_text": badge_text,
            "report": report,
            "latest_deploy_id": latest_deploy_id,
        },
    )


@app.get("/nodes/{node_id}/edit", response_class=HTMLResponse)
@login_required
async def node_edit_page(request: Request, node_id: str):
    node = get_node(node_id)
    if not node:
        return templates.TemplateResponse(
            request,
            "not-found.html",
            {"request": request, "title": "未找到节点", "message": "节点不存在"},
            status_code=404,
        )

    return render_node_form(
        request,
        title=f"编辑节点 · {node['name']}",
        mode="edit",
        node_id=node_id,
        form_values={
            "name": node["name"],
            "ip": node["ip"],
            "ssh_port": node["ssh_port"],
            "ssh_user": node["ssh_user"],
            "ssh_password": node["ssh_password"],
            "public_port": node["public_port"],
            "listen_port": node["listen_port"],
        },
    )


@app.post("/nodes/{node_id}/edit", response_class=HTMLResponse)
@login_required
async def node_edit_submit(
    request: Request,
    node_id: str,
    name: str = Form(...),
    ip: str = Form(...),
    ssh_port: str = Form(...),
    ssh_user: str = Form(...),
    ssh_password: str = Form(...),
    public_port: str = Form(...),
    listen_port: str = Form(...),
):
    node = get_node(node_id)
    if not node:
        return templates.TemplateResponse(
            request,
            "not-found.html",
            {"request": request, "title": "未找到节点", "message": "节点不存在"},
            status_code=404,
        )

    payload, errors = clean_node_form(
        {
            "name": name,
            "ip": ip,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "ssh_password": ssh_password,
            "public_port": public_port,
            "listen_port": listen_port,
        }
    )

    if not errors:
        exists = find_node_by_endpoint(
            str(payload["ip"]),
            int(payload["ssh_port"]),
            exclude_node_id=node_id,
        )
        if exists:
            errors.append("已存在相同 IP + SSH 端口 的节点记录")

    if errors:
        return render_node_form(
            request,
            title=f"编辑节点 · {node['name']}",
            mode="edit",
            node_id=node_id,
            form_values=payload,
            errors=errors,
        )

    update_node_record(node_id, payload)
    return RedirectResponse(url=f"/nodes/{node_id}", status_code=303)


@app.post("/nodes/{node_id}/reinstall")
@login_required
async def node_reinstall_submit(request: Request, node_id: str):
    node = get_node(node_id)
    if not node:
        return templates.TemplateResponse(
            request,
            "not-found.html",
            {"request": request, "title": "未找到节点", "message": "节点不存在"},
            status_code=404,
        )

    deploy_id = create_deployment_record(node_id=node_id, action_type="reinstall")
    submit_reinstall_job(deploy_id=deploy_id, node=dict(node))
    return RedirectResponse(url=f"/deployments/{deploy_id}", status_code=303)


@app.get("/deployments/{deploy_id}", response_class=HTMLResponse)
@login_required
async def deployment_detail_page(request: Request, deploy_id: str):
    deployment = get_deployment(deploy_id)
    if not deployment:
        return templates.TemplateResponse(
            request,
            "not-found.html",
            {"request": request, "title": "未找到任务", "message": "部署任务不存在"},
            status_code=404,
        )

    node = get_node(deployment["node_id"])
    return templates.TemplateResponse(
        request,
        "deployment-detail.html",
        {
            "request": request,
            "title": f"部署任务 · {deploy_id}",
            "deployment": deployment,
            "node": node,
            "auto_refresh": deployment["result"] in {"pending", "running"} or is_deploy_running(deploy_id),
        },
    )


@app.get("/api/deployments/{deploy_id}")
@login_required
async def deployment_status_api(request: Request, deploy_id: str):
    deployment = get_deployment(deploy_id)
    if not deployment:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(
        {
            "deploy_id": deployment["deploy_id"],
            "node_id": deployment["node_id"],
            "result": deployment["result"],
            "failure_stage": deployment["failure_stage"],
            "summary_log": deployment["summary_log"],
            "raw_log": deployment["raw_log"],
            "generated_vless_link": deployment["generated_vless_link"],
            "started_at": deployment["started_at"],
            "ended_at": deployment["ended_at"],
            "running": is_deploy_running(deploy_id),
        }
    )


@app.post("/nodes/{node_id}/delete")
@login_required
async def node_delete_submit(request: Request, node_id: str):
    node = get_node(node_id)
    if not node:
        return templates.TemplateResponse(
            request,
            "not-found.html",
            {"request": request, "title": "未找到节点", "message": "节点不存在"},
            status_code=404,
        )
    delete_node_record(node_id)
    return RedirectResponse(url="/nodes", status_code=303)
