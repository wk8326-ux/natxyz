# Phase 3 Development Guide

## Goal

Phase 3 adds one new node deployment protocol to NAT WebUI:

- UI label: `tunnel`
- Internal protocol key: `cf_vless_ws`
- Actual client protocol: `VLESS + WS + TLS` through Cloudflare Tunnel

This phase must not broaden into HY2, arbitrary protocol chains, Cloudflare API automation, or nat-bootstrap repository changes.

## User Decisions Confirmed

1. Protocol dropdown should be simple:
   - `vless` = current direct VLESS Reality node
   - `tunnel` = new Cloudflare Tunnel + VLESS WS node
2. For `tunnel` nodes, the panel should not ask for service/public port information.
   - Local service port defaults to `8080`.
   - This matches the Cloudflare Zero Trust public hostname route configured by the user.
3. The domain field should be named `应用路由域名`.
   - Backend/env meaning: `CF_HOST`
   - Example: `jp02.holdzywoo.top`
4. Tunnel token may be stored in the database.
   - It should be hidden by default in the UI.
   - It must be possible to reveal/copy it for reuse.
5. Do not modify `wk8326-ux/nat-bootstrap` for this phase.
   - Use its `cf_vless_ws_install.sh` only as a behavioral reference.
   - Implement project-specific install/reinstall logic inside `natxyz`.
6. The final export/import link should be:
   - `vless://UUID@CF_HOST:443?encryption=none&security=tls&type=ws&host=CF_HOST&path=/&sni=CF_HOST#NODE_NAME`
7. Deployment verification only needs to happen on the NAT host.
   - Verify expected local services are running.
   - Do not require external Cloudflare/client reachability validation in Phase 3.

## Important Architecture Decision

`tunnel` nodes are not valid front nodes for the current chain proxy design.

Why:

- Current chain front node must accept real client traffic directly and then forward to a backend.
- A Cloudflare Tunnel node does not expose a normal public TCP/Reality ingress.
- Its public entry is Cloudflare-managed HTTPS/WebSocket on a hostname.
- It is better treated as an egress/landing/backend style node.

Phase 3 selector behavior:

- `tunnel` nodes must not appear in the chain front-node dropdown.
- For the initial Phase 3 MVP, keep chain support unchanged and only allow `vless` nodes in both front and backend dropdowns.
- Future Phase 3.1 may allow `tunnel` as backend only, with a new mixed chain mode: `vless -> tunnel`.

Reason to defer backend-chain support:

- Existing Phase 2 chain logic supports only `VLESS Reality -> VLESS Reality`.
- Supporting tunnel backend requires front-node outbound generation for `VLESS + WS + TLS`:
  - address: `CF_HOST`
  - port: `443`
  - security: `tls`
  - transport: `ws`
  - host header: `CF_HOST`
  - path: `/`
- This is a separate chain mode and should not be mixed into the first tunnel node MVP.

## UI Requirements

### Node Form

Protocol dropdown values:

- `vless`
- `tunnel`

When `vless` is selected, preserve current fields and behavior.

When `tunnel` is selected, show:

- Node name
- SSH IP
- SSH port
- SSH user
- SSH password
- 应用路由域名
- Tunnel token

When `tunnel` is selected, hide or disable:

- public port
- listen port
- Reality target
- front/backend chain selectors

### Node Detail

For tunnel nodes, show:

- protocol: `tunnel`
- 应用路由域名
- local WS port: `8080`
- token status: configured / missing
- reveal/copy token action
- exported VLESS link

Token should not be displayed by default.

### Node List

Show tunnel nodes as normal nodes, but visually distinguish protocol as `tunnel`.

## Data Model Requirements

Add storage for tunnel-specific fields without breaking existing direct and chain nodes:

- `cf_host` or equivalent: application route hostname
- `cf_tunnel_token` or equivalent: Cloudflare Tunnel token
- optional fixed/default `ws_port`: default `8080`
- optional `ws_path`: default `/`

Do not store token in long-term memory or public docs.
Database storage is allowed for this project.

## Deployment Requirements

Implement project-local deployment logic by referencing the existing nat-bootstrap script behavior.

Do not shell out to the remote nat-bootstrap script as the only implementation if the project needs structured status and reinstall behavior.

Target runtime should prefer `sing-box` for the tunnel protocol unless inspection proves Xray is simpler and more reliable for this project.

Minimum remote deployment behavior:

1. SSH into target node.
2. Install required packages.
3. Install or update `sing-box`.
4. Install or update `cloudflared`.
5. Generate/reuse VLESS UUID.
6. Write local VLESS WS inbound on `127.0.0.1:8080` or `0.0.0.0:8080` depending on cloudflared route needs.
7. Store Cloudflare Tunnel token on the remote host as a root-readable token file.
8. Configure service manager:
   - systemd for Debian/Ubuntu
   - OpenRC only if later needed for Alpine
9. Start/restart services.
10. Verify local services are running:
    - `sing-box` active
    - `cloudflared` active
    - local `8080` listener exists
11. Save final generated VLESS link to `last_vless_link`.

## Reinstall Behavior

For tunnel nodes, reinstall should:

- reuse saved `cf_host`
- reuse saved `cf_tunnel_token`
- reuse or regenerate UUID according to existing project convention
- rewrite service/config files only for this node's tunnel deployment
- restart only the relevant services
- update exported link name to current node name

## Link Generation

Tunnel link must be generated from current node state, not stale initial node name.

Format:

```text
vless://UUID@CF_HOST:443?encryption=none&security=tls&type=ws&host=CF_HOST&path=/&sni=CF_HOST#NODE_NAME
```

Rules:

- Fragment `#NODE_NAME` must update when node name changes.
- Subscriptions must use current node name.
- Clash export must use current node name.

## Chain Interaction Rules

Initial Phase 3:

- Chain creation remains `vless -> vless` only.
- `tunnel` nodes are hidden from front-node dropdown.
- `tunnel` nodes are also hidden from backend dropdown until mixed chain support is explicitly implemented.

Future Phase 3.1:

- Add backend-only tunnel support if desired.
- New mode should be explicit, e.g. `vless -> tunnel`.
- Do not overload the existing Phase 2 `vless_reality_to_vless_reality` mode.

## Non-Goals

Phase 3 must not include:

- Creating Cloudflare Tunnel through Cloudflare API
- Creating DNS or Public Hostname route through Cloudflare API
- Editing `wk8326-ux/nat-bootstrap`
- HY2 support
- Generic protocol framework rewrite
- Allowing tunnel nodes as front chain nodes
- Mixed chain support in the first MVP
- External client handshake verification requirement

## Verification Checklist

Before declaring Phase 3 complete:

- Creating a `vless` node still works.
- Creating a `tunnel` node stores host/token and does not require service/public ports.
- Editing a `tunnel` node preserves and updates host/token correctly.
- Token is hidden by default but can be copied/revealed.
- Deploy/reinstall on a real Debian test node starts expected services.
- Local remote verification confirms:
  - `sing-box` service active
  - `cloudflared` service active
  - `8080` listener exists
- Exported VLESS link matches current node name.
- Subscription link matches current node name.
- Chain dropdowns exclude tunnel nodes in Phase 3 MVP.
- Test suite passes.
- GitHub is updated after verification.
