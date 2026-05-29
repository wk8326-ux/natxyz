from __future__ import annotations

import json
import shlex
import subprocess
import textwrap
import urllib.request
import uuid
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .config import AGENT_REPORT_PATH, APP_DIR

REMOTE_APP_DIR = "/opt/natctl"
REMOTE_BIN_DIR = f"{REMOTE_APP_DIR}/bin"
REMOTE_AGENT_DIR = f"{REMOTE_APP_DIR}/agent"
REMOTE_STATE_DIR = f"{REMOTE_APP_DIR}/state"
REMOTE_LOG_DIR = f"{REMOTE_APP_DIR}/logs"
REMOTE_MARK_FILE = f"{REMOTE_STATE_DIR}/managed_by_natctl"
REMOTE_META_FILE = f"{REMOTE_STATE_DIR}/node_meta.json"
REMOTE_AGENT_SCRIPT = f"{REMOTE_AGENT_DIR}/report.sh"
REMOTE_SINGBOX_DIR = "/etc/sing-box"
REMOTE_SINGBOX_CONFIG = f"{REMOTE_SINGBOX_DIR}/config.json"
MARK_CONTENT = "managed_by=nat-webui-v1"
SINGBOX_RELEASE_API = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"


class DeployError(Exception):
    def __init__(self, stage: str, message: str, raw_log: str):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.raw_log = raw_log


@dataclass
class DeployResult:
    summary_log: str
    raw_log: str
    generated_vless_link: str
    generated_uuid: str
    generated_private_key: str
    generated_public_key: str
    generated_short_id: str
    selected_reality_target: str


class RemoteExecutor:
    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def run(self, script: str, *, timeout: int = 120) -> str:
        proc = subprocess.run(
            [
                "sshpass",
                "-p",
                self.password,
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ConnectTimeout=12",
                "-p",
                str(self.port),
                f"{self.user}@{self.host}",
                "sh",
                "-s",
            ],
            input=script,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, proc.args, output=output)
        return output.strip()



def shell_quote(value: str) -> str:
    return shlex.quote(value)



def choose_reality_target() -> str:
    return "www.microsoft.com"



def generate_reality_materials() -> tuple[str, str, str, str]:
    generated_uuid = str(uuid.uuid4())
    private_key_obj = X25519PrivateKey.generate()
    public_key_obj = private_key_obj.public_key()
    generated_private_key = urlsafe_b64encode(private_key_obj.private_bytes_raw()).decode().rstrip("=")
    generated_public_key = urlsafe_b64encode(public_key_obj.public_bytes_raw()).decode().rstrip("=")
    generated_short_id = uuid.uuid4().hex[:16]
    return generated_uuid, generated_private_key, generated_public_key, generated_short_id



def _fetch_latest_singbox() -> dict[str, Any]:
    req = urllib.request.Request(
        SINGBOX_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "nat-webui"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    assets = data.get("assets", []) or []
    chosen = None
    for asset in assets:
        name = str(asset.get("name", ""))
        if "linux" in name and "amd64" in name and name.endswith(".tar.gz"):
            if "musl" in name:
                chosen = asset
                break
            chosen = chosen or asset
    if not chosen:
        raise DeployError("download", "无法找到适合的 sing-box Linux amd64 发行包", json.dumps(data, ensure_ascii=False, indent=2)[:8000])
    return {
        "tag": str(data.get("tag_name", "")).strip(),
        "name": str(chosen.get("name", "")).strip(),
        "url": str(chosen.get("browser_download_url", "")).strip(),
    }



def build_singbox_config(node: dict, *, generated_uuid: str, generated_private_key: str, generated_short_id: str, selected_reality_target: str) -> str:
    config = {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "vless",
                "tag": "vless-reality-in",
                "listen": "::",
                "listen_port": int(node["listen_port"]),
                "users": [{"uuid": generated_uuid, "flow": "xtls-rprx-vision"}],
                "tls": {
                    "enabled": True,
                    "server_name": selected_reality_target,
                    "reality": {
                        "enabled": True,
                        "handshake": {
                            "server": selected_reality_target,
                            "server_port": 443,
                        },
                        "private_key": generated_private_key,
                        "short_id": [generated_short_id],
                    },
                },
            }
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }
    return json.dumps(config, ensure_ascii=False, indent=2)



def build_node_meta(node: dict, *, generated_uuid: str, generated_public_key: str, generated_short_id: str, selected_reality_target: str) -> str:
    payload = {
        "node_id": node["node_id"],
        "protocol_type": node["protocol_type"],
        "public_port": node["public_port"],
        "listen_port": node["listen_port"],
        "selected_reality_target": selected_reality_target,
        "generated_uuid": generated_uuid,
        "generated_public_key": generated_public_key,
        "generated_short_id": generated_short_id,
        "agent_token": node["agent_token"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)



def build_agent_script(node: dict) -> str:
    report_url = f"http://64.188.29.195:8788{AGENT_REPORT_PATH}"
    return textwrap.dedent(
        f"""\
        #!/bin/sh
        set -eu
        meta_file={shell_quote(REMOTE_META_FILE)}
        if [ ! -f "$meta_file" ]; then
          echo "missing meta file" >&2
          exit 1
        fi
        if ! command -v curl >/dev/null 2>&1; then
          apk add --no-cache curl >/dev/null
        fi
        hostname_val=$(hostname 2>/dev/null || echo unknown)
        report_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        python3 - <<'PYEOF' > /tmp/natctl-agent-report.json
import json
from pathlib import Path
meta = json.loads(Path({REMOTE_META_FILE!r}).read_text())
payload = {{
    "node_id": meta["node_id"],
    "agent_token": meta["agent_token"],
    "overall_status": "online",
    "report_time": {"__REPORT_TIME__"!r},
    "hostname": {"__HOSTNAME__"!r},
    "public_ip": {node['ip']!r},
    "public_port": meta.get("public_port"),
    "listen_port": meta.get("listen_port"),
    "protocol_type": meta.get("protocol_type"),
    "generated_uuid": meta.get("generated_uuid"),
    "generated_public_key": meta.get("generated_public_key"),
    "generated_short_id": meta.get("generated_short_id"),
    "selected_reality_target": meta.get("selected_reality_target"),
}}
print(json.dumps(payload, ensure_ascii=False))
PYEOF
        sed -i "s/__REPORT_TIME__/$report_time/g; s/__HOSTNAME__/$hostname_val/g" /tmp/natctl-agent-report.json
        curl -fsS -H 'Content-Type: application/json' --data @/tmp/natctl-agent-report.json {shell_quote(report_url)}
        """
    )



def build_remote_script(node: dict, *, singbox_config: str, node_meta: str, agent_script: str, singbox_archive_url: str, singbox_archive_name: str) -> str:
    cron_block = "*/5 * * * * /opt/natctl/agent/report.sh >> /opt/natctl/logs/agent.log 2>&1"
    openrc_script = textwrap.dedent(
        """\
        #!/sbin/openrc-run
        description="sing-box NAT WebUI service"
        command="/usr/local/bin/sing-box"
        command_args="run -c /etc/sing-box/config.json"
        command_background="yes"
        pidfile="/run/sing-box.pid"
        depend() {
          need net
        }
        """
    )
    return textwrap.dedent(
        f"""\
        set -eu
        mkdir -p {shell_quote(REMOTE_BIN_DIR)} {shell_quote(REMOTE_AGENT_DIR)} {shell_quote(REMOTE_STATE_DIR)} {shell_quote(REMOTE_LOG_DIR)} {shell_quote(REMOTE_SINGBOX_DIR)} /tmp/natctl-singbox
        if ! command -v curl >/dev/null 2>&1; then
          apk add --no-cache curl >/dev/null
        fi
        if ! command -v sing-box >/dev/null 2>&1; then
          echo 'INFO: sing-box missing, downloading release package'
          rm -rf /tmp/natctl-singbox/*
          curl -fsSL {shell_quote(singbox_archive_url)} -o /tmp/natctl-singbox/{shell_quote(singbox_archive_name)}
          tar -xzf /tmp/natctl-singbox/{shell_quote(singbox_archive_name)} -C /tmp/natctl-singbox
          bin_path=$(find /tmp/natctl-singbox -type f -name sing-box | head -n 1)
          if [ -z "$bin_path" ]; then
            echo 'ERROR: sing-box binary not found in archive'
            exit 1
          fi
          install -m 0755 "$bin_path" /usr/local/bin/sing-box
        fi
        python3 - <<'PYEOF'
from pathlib import Path
Path({REMOTE_MARK_FILE!r}).write_text({(MARK_CONTENT + chr(10))!r})
Path({REMOTE_SINGBOX_CONFIG!r}).write_text({(singbox_config + chr(10))!r})
Path({REMOTE_META_FILE!r}).write_text({(node_meta + chr(10))!r})
Path({REMOTE_AGENT_SCRIPT!r}).write_text({agent_script!r})
Path('/etc/init.d/sing-box').write_text({openrc_script!r})
PYEOF
        chmod +x {shell_quote(REMOTE_AGENT_SCRIPT)} /etc/init.d/sing-box
        if command -v rc-service >/dev/null 2>&1; then
          rc-update add sing-box default >/dev/null 2>&1 || true
          rc-service sing-box restart >/dev/null 2>&1 || rc-service sing-box start >/dev/null 2>&1
        else
          /usr/local/bin/sing-box run -c /etc/sing-box/config.json >/opt/natctl/logs/sing-box.log 2>&1 &
        fi
        (crontab -l 2>/dev/null | grep -v 'NAT-WEBUI-AGENT' | grep -v '/opt/natctl/agent/report.sh'; \
          echo '# BEGIN NAT-WEBUI-AGENT'; \
          echo {shell_quote(cron_block)}; \
          echo '# END NAT-WEBUI-AGENT') | crontab -
        echo 'OK: deploy finished'
        """
    )



def build_vless_link(node: dict, *, generated_uuid: str, generated_public_key: str, generated_short_id: str, selected_reality_target: str) -> str:
    return (
        f"vless://{generated_uuid}@{node['ip']}:{node['public_port']}"
        f"?security=reality&sni={selected_reality_target}&pbk={generated_public_key}"
        f"&sid={generated_short_id}&type=tcp&flow=xtls-rprx-vision#{node['name']}"
    )



def run_real_deploy(node: dict) -> DeployResult:
    logs: list[str] = []

    def add(stage: str, content: str) -> None:
        content = (content or "").strip()
        logs.append(f"[stage] {stage}")
        if content:
            logs.append(content)

    executor = RemoteExecutor(
        host=str(node["ip"]),
        port=int(node["ssh_port"]),
        user=str(node["ssh_user"]),
        password=str(node["ssh_password"]),
    )

    selected_reality_target = choose_reality_target()
    generated_uuid, generated_private_key, generated_public_key, generated_short_id = generate_reality_materials()
    singbox_config = build_singbox_config(
        node,
        generated_uuid=generated_uuid,
        generated_private_key=generated_private_key,
        generated_short_id=generated_short_id,
        selected_reality_target=selected_reality_target,
    )
    node_meta = build_node_meta(
        node,
        generated_uuid=generated_uuid,
        generated_public_key=generated_public_key,
        generated_short_id=generated_short_id,
        selected_reality_target=selected_reality_target,
    )
    agent_script = build_agent_script(node)
    singbox_release = _fetch_latest_singbox()

    try:
        add("ssh_probe", executor.run("echo CONNECTED", timeout=25))
    except Exception as exc:
        raw = "\n".join(logs + [f"SSH probe failed: {exc}"])
        raise DeployError("ssh_probe", "SSH 连接失败", raw)

    try:
        add("system_probe", executor.run("uname -a && cat /etc/alpine-release", timeout=30))
    except Exception as exc:
        raw = "\n".join(logs + [f"System probe failed: {exc}"])
        raise DeployError("system_probe", "系统探测失败", raw)

    try:
        add(
            "deploy",
            executor.run(
                build_remote_script(
                    node,
                    singbox_config=singbox_config,
                    node_meta=node_meta,
                    agent_script=agent_script,
                    singbox_archive_url=singbox_release["url"],
                    singbox_archive_name=singbox_release["name"],
                ),
                timeout=360,
            ),
        )
    except Exception as exc:
        raw = "\n".join(logs + [f"Deploy failed: {exc}"])
        raise DeployError("deploy", "远端部署失败", raw)

    generated_vless_link = build_vless_link(
        node,
        generated_uuid=generated_uuid,
        generated_public_key=generated_public_key,
        generated_short_id=generated_short_id,
        selected_reality_target=selected_reality_target,
    )
    summary = textwrap.dedent(
        f"""\
        真实部署已完成
        目标节点：{node['ip']}:{node['ssh_port']}
        监听端口：{node['listen_port']}
        公网端口：{node['public_port']}
        Reality 目标：{selected_reality_target}
        sing-box：{singbox_release['name']}
        """
    ).strip()
    return DeployResult(
        summary_log=summary,
        raw_log="\n".join(logs),
        generated_vless_link=generated_vless_link,
        generated_uuid=generated_uuid,
        generated_private_key=generated_private_key,
        generated_public_key=generated_public_key,
        generated_short_id=generated_short_id,
        selected_reality_target=selected_reality_target,
    )
