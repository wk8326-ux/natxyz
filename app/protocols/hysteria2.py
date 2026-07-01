from __future__ import annotations

import urllib.parse
from typing import Any

from .models import ProtocolBuildContext
from .registry import register_protocol


class Hysteria2Protocol:
    protocol_type = "hysteria2"
    aliases = ("hy2",)
    display_name = "Hysteria2"
    category = "direct"
    supports_deploy = True
    supports_subscription = True
    supports_chain_backend = False

    def build_inbound(self, context: ProtocolBuildContext) -> dict[str, Any]:
        node = context.node
        password = str(context.materials.get("generated_uuid") or "").strip()
        server_name = str(context.materials.get("selected_reality_target") or "www.example.com").strip() or "www.example.com"
        node_id = str(node.get("node_id") or "node")
        return {
            "type": "hysteria2",
            "tag": f"hysteria2-{node_id}",
            "listen": "::",
            "listen_port": int(node["listen_port"]),
            "users": [{"password": password}],
            "tls": {
                "enabled": True,
                "server_name": server_name,
                "certificate_path": "/etc/sing-box/hysteria2-cert.pem",
                "key_path": "/etc/sing-box/hysteria2-key.pem",
            },
        }

    def build_share_link(self, context: ProtocolBuildContext) -> str:
        node = context.node
        password = urllib.parse.quote(str(context.materials.get("generated_uuid") or ""), safe="")
        host = str(node.get("ip") or "").strip()
        port = int(node.get("public_port") or node.get("listen_port") or 443)
        server_name = str(context.materials.get("selected_reality_target") or "www.example.com").strip() or "www.example.com"
        remark = urllib.parse.quote(str(context.materials.get("remark") or node.get("name") or "Hysteria2"), safe="")
        query = urllib.parse.urlencode({"sni": server_name, "insecure": "1"})
        return f"hy2://{password}@{host}:{port}?{query}#{remark}"


register_protocol(Hysteria2Protocol())
