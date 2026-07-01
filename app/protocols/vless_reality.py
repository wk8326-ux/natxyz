from __future__ import annotations

from typing import Any

from .models import ProtocolBuildContext
from .registry import register_protocol


class VlessRealityProtocol:
    protocol_type = "vless_reality_singbox"
    aliases = ("vless_reality", "")
    display_name = "VLESS Reality"
    category = "direct"
    supports_deploy = True
    supports_subscription = True
    supports_chain_backend = True

    def build_inbound(self, context: ProtocolBuildContext) -> dict[str, Any]:
        node = context.node
        materials = context.materials
        selected_reality_target = str(materials["selected_reality_target"])
        node_id = str(node.get("node_id") or "node")
        return {
            "type": "vless",
            "tag": f"vless-reality-{node_id}",
            "listen": "::",
            "listen_port": int(node["listen_port"]),
            "users": [{"uuid": materials["generated_uuid"], "flow": "xtls-rprx-vision"}],
            "tls": {
                "enabled": True,
                "server_name": selected_reality_target,
                "reality": {
                    "enabled": True,
                    "handshake": {
                        "server": selected_reality_target,
                        "server_port": 443,
                    },
                    "private_key": materials["generated_private_key"],
                    "short_id": [materials["generated_short_id"]],
                },
            },
        }


register_protocol(VlessRealityProtocol())
