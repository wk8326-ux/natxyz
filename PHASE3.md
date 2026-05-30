# Phase 3 — Tunnel 模式实现记录

## 目标

在 NAT WebUI 中增加独立的 `tunnel` 协议模式，用于没有公网端口或不想暴露端口的 NAT 节点。

`tunnel` 模式采用：

- 本机：`sing-box` 提供 `VLESS + WebSocket` 入站，默认监听 `127.0.0.1:8080`。
- 出口：`cloudflared` 使用 Cloudflare Tunnel token 主动连 Cloudflare。
- 客户端：连接 Cloudflare 应用路由域名 `cf_host:443`，传输为 `ws + tls`。

## 当前设计约束

- 协议下拉只显示：`vless` / `tunnel`。
- `tunnel` 是独立协议模式，不参与链式代理。
- `tunnel` 不要求公网业务端口。
- `tunnel` 不修改、不依赖 `nat-bootstrap` 仓库。
- Cloudflare Tunnel token 由用户从 Cloudflare 面板复制填写。
- 应用路由域名由用户提前在 Cloudflare Tunnel Public Hostname 中配置。

## 已实现

- 数据库新增 tunnel 字段：
  - `cf_host`
  - `cf_tunnel_token`
  - `ws_port`
  - `ws_path`
- 新建 / 编辑节点页支持 `tunnel`：
  - 显示应用路由域名
  - 显示 Cloudflare Tunnel token
  - 显示本地 WS 端口，默认 `8080`
  - 显示 WS 路径，默认 `/`
  - 隐藏公网端口与 Reality 监听端口
- 节点详情页支持 tunnel：
  - 显示应用路由域名
  - 显示本地 WS 端口
  - token 默认隐藏，仅提供复制值
  - 生成可导入 VLESS WS TLS 链接
- `deployer.py` 已新增：
  - `build_tunnel_singbox_config()`
  - `build_tunnel_node_meta()`
  - `build_tunnel_vless_link()`
  - `build_tunnel_remote_script()`
- `run_real_deploy()` 已按协议分支：
  - `vless`：沿用原 Reality 部署
  - `tunnel`：部署 `sing-box + cloudflared`

## Tunnel 远端部署行为

目标机执行：

- 安装基础依赖：`curl`、`ca-certificates`、`tar`、`gzip`、`coreutils`、`procps`。
- 按架构选择 `sing-box` release：`amd64` / `arm64` / `armv7`。
- 下载 `cloudflared` 对应架构二进制。
- 写入 `/etc/sing-box/config.json`。
- 写入 `/etc/cloudflared/token`，使用 token-file 方式启动。
- 写入 systemd 与 OpenRC 服务文件。
- 启动 / 重启 `sing-box` 与 `cloudflared-tunnel`。
- 检查本地 WS 监听端口，默认 `8080`。
- 保留原有 agent 上报 cron。

## 已验证

- `python3 -m compileall app/deployer.py` 通过。
- tunnel 配置生成 smoke test 通过。
- tunnel meta 生成 smoke test 通过。
- tunnel VLESS WS TLS 链接生成通过。
- tunnel 远端脚本通过 `bash -n` 语法检查。
- `_fetch_latest_singbox()` 可获取最新版本与多架构包，本轮结果为 `v1.13.12`，包含 `amd64` / `arm64` / `armv7`。
- 页面端 TestClient 回归通过：登录、新建 tunnel、详情、编辑、列表展示均正常。
- 单元测试通过：`10 passed, 2 warnings`。

## 未完成 / 待实机验证

- 还未用真实 Cloudflare Tunnel token 在实际 NAT / Alpine 节点上跑完整部署。
- 真实可用性仍需验证：Cloudflare Tunnel 在线、应用路由命中、客户端导入后可访问外网。
- 若目标机没有 `python3`，当前远端写文件步骤会失败；后续如要覆盖极简 Alpine，应把远端写文件改成 `cat` / `printf` 或先安装 `python3`。

## 版本管理

- 项目已初始化为独立 git 仓库：`/root/.nanobot/workspace/nat-webui-project/.git`。
- 初始提交：`f3bd215 Initial NAT WebUI with tunnel deployment`。
- 已忽略运行数据、数据库、日志、缓存与本地临时 JSON。
