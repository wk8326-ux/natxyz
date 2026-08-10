# natxyz 项目交接文档

最后核验：2026-08-10

## 1. 项目定位

`natxyz` 是面向自用 NAT VPS / 月抛机器的轻量代理节点管理面板。

当前核心目标：

- 通过面板保存节点资产、SSH 信息、NAT 内外端口和地区标签；
- 由面板 SSH 推送部署 sing-box，而不是替换现有 SSH 推送体系；
- 管理直连节点、链式节点和仅导入 VLESS 节点；
- 输出 v2rayN/Xray、sing-box、Clash 订阅；
- 接收远端轻量 agent 上报，展示节点在线状态和部署记录；
- 逐步扩展多协议，但保持单用户、轻量、低复杂度。

项目不是通用多租户 SaaS。暂不引入 RBAC、复杂组织架构或重型 agent 平台。

## 2. 权威位置与 Git 状态

当前唯一应继续开发的仓库：

```text
/root/local/projects/github/natxyz
```

GitHub：

```text
https://github.com/wk8326-ux/natxyz
```

当前分支与基线：

```text
branch: main
HEAD: d37f738b6bbd100dc71810eca9cbf8c6dabd3f4e
remote: origin/main
```

2026-08-10 核验时工作树干净，`main` 与 `origin/main` 一致。

旧运行目录已不存在：

```text
/root/.nanobot/workspace/nat-webui-project
```

历史归档仅用于追溯，不得直接恢复为生产目录：

```text
/root/.nanobot/workspace/archive/nat-webui-project-retired-20260702084038
```

## 3. 当前运行状态

当前主 VPS 上没有运行 natxyz：

- 没有监听 `8788`；
- 没有 natxyz/nat-webui systemd 单元；
- 没有 `uvicorn` 或 `scripts/run-prod.sh` 进程；
- 当前仓库没有 `.env.runtime` 和 `.venv`。

因此当前状态是：**代码仓库可开发、可测试，但没有正式运行实例。**

仓库内存在一个被 Git 忽略的本地 SQLite 数据库：

```text
/root/local/projects/github/natxyz/data/nat-webui.db
```

该库只有 3 条重复的 `CCS_TEST` 测试节点，不能当作现行生产数据。历史归档数据库也不能未经核对直接迁回。

## 4. 技术栈与启动方式

技术栈：

- Python 3
- FastAPI
- Uvicorn
- Jinja2 模板
- SQLite
- Paramiko（SSH/SFTP）
- sing-box（远端节点代理核心）
- shell/cron（远端 agent 定时上报）

主要入口：

```text
app/main.py          FastAPI 路由、表单处理、订阅生成
app/db.py            SQLite schema、CRUD、token、日志脱敏
app/deployer.py      直连节点 SSH 部署与 agent 下发
app/chain_deployer.py 链式节点前置配置生成与部署
app/protocols/       协议处理器注册表与实现
app/templates/       Jinja2 页面
app/static/          CSS/JS/图标
scripts/run-prod.sh  正式启动入口
scripts/dev.sh       开发启动入口
scripts/install.sh   初始化依赖和运行环境
scripts/start.sh     兼容入口，转交 run-prod.sh
```

生产启动必须使用：

```bash
cd /root/local/projects/github/natxyz
./scripts/run-prod.sh
```

`run-prod.sh` 会加载 `.env.runtime`。不要直接运行：

```bash
uvicorn app.main:app
```

直接运行可能绕过 `.env.runtime`，退回不安全的默认登录配置。

生产基线环境变量至少包括：

```text
NAT_WEBUI_ADMIN_USER
NAT_WEBUI_ADMIN_PASSWORD
NAT_WEBUI_SESSION_SECRET
NAT_WEBUI_DB_PATH
NAT_WEBUI_HOST
NAT_WEBUI_PORT
NAT_WEBUI_STALE_AFTER_SECONDS
NAT_WEBUI_GEOIP_TIMEOUT_SECONDS
```

默认端口是 `8788`。若迁移到正式 Debian VPS，建议代码放 `/opt/nat-webui`，通过 systemd 调用该目录下的 `scripts/run-prod.sh`。

## 5. 当前数据模型

核心表：

```text
nodes
agent_reports
deployments
app_settings
tags
node_tags
```

`nodes` 同时保存：

- SSH 管理信息；
- `listen_port` 与 NAT `public_port`；
- 协议类型；
- Reality / HY2 / AnyTLS / Tunnel 扩展字段；
- 前置和后端节点关系；
- 生成后的分享链接；
- agent token、最后上报时间、系统指标；
- 手工地区与国家代码。

敏感字段可能存在 SQLite 中，包括 SSH 密码、Reality 私钥、Tunnel token 等。数据库、`.env.runtime`、订阅 token 和完整分享链接不得提交 Git，也不得写进公开 handoff。

## 6. 已实现功能

### 6.1 面板与资产管理

已实现：

- 单用户登录和 session；
- 节点新增、编辑、重命名、删除；
- 标签新增、绑定、删除；
- 节点详情和部署记录；
- SSH 密码框默认隐藏并带查看按钮；
- 列表页 IP 部分遮盖；
- 部署日志敏感信息脱敏；
- 中国地区/多国旗和手工地区覆盖。

### 6.2 三类节点

节点列表有三类视图：

```text
直连
链式
仅导入
```

仅导入节点：

- 支持批量粘贴 VLESS 链接；
- 解析并保存地址、端口、UUID、Reality 参数和名称；
- 可修改名称和地区；
- 不支持 SSH 重装；
- 可进入订阅；
- 可作为链式节点后端。

### 6.3 订阅

已实现：

```text
/sub/{token}
/sub/{token}?scope=direct
/sub/{token}?scope=chain
/sub/{token}?scope=imported
/sub/{token}/clash?scope=...
```

输出类型：

- v2rayN/Xray URI；
- sing-box JSON；
- Clash Meta YAML。

订阅 token 支持轮换：

- 新 token 立即生效；
- 旧 token 保留 24 小时；
- 避免客户端订阅瞬间全部失效。

### 6.4 直连部署与 agent

现有正确主流程是：

```text
面板保存 SSH 信息
→ Paramiko/SFTP 推送远端配置
→ 安装或更新 sing-box
→ 写入 OpenRC 或 systemd 服务
→ 安装 cron
→ 每 5 分钟执行远端 report.sh
→ agent 回传状态
```

不要用“自注册一键命令”替代该流程。自注册仅可作为未来补充。

已兼容：

- Alpine/OpenRC；
- Debian/Ubuntu/systemd；
- systemd `sing-box.service`；
- 清理旧 `/etc/init.d/sing-box` 冲突；
- 安装 cron 并生成定时上报；
- NAT 内部监听端口与公网映射端口分离。

### 6.5 链式节点

当前链式模型：

```text
前置节点 sing-box
→ 为每条链生成独立 VLESS 用户
→ route 规则按用户选择后端 VLESS outbound
→ 后端可为直连 VLESS 或仅导入 VLESS
```

已修复的关键问题：sing-box `1.13.12` 的用户路由字段必须是：

```json
{"auth_user": ["chain-user"]}
```

不能使用：

```json
{"user": ["chain-user"]}
```

错误字段会使流量落到 `final: direct`，表现为链式节点出口仍是前置机 IP。

## 7. 协议状态

### 7.1 VLESS + Reality

状态：当前主要稳定协议。

协议值：

```text
vless_reality_singbox
```

已覆盖：配置生成、SSH 部署、分享链接、订阅、链式前置与后端。

### 7.2 Cloudflare Tunnel + VLESS WS

状态：已有历史实现。

协议值：

```text
cf_vless_ws
```

涉及 cloudflared token 和 tunnel 配置。后续改动应先核对真实部署路径，不要仅凭旧文档判断可用性。

### 7.3 Hysteria2

状态：代码已接入，自动化测试通过，但未在当前正式运行实例上做端到端验收。

协议值：

```text
hysteria2
```

已实现：

- 协议注册；
- sing-box inbound 生成；
- `hy2://` 分享链接；
- sing-box 订阅；
- Clash Meta 订阅；
- SSH 部署接线；
- 生成或使用证书字段。

上线前必须在真实 NAT 节点验证：

- UDP 公网映射；
- 内部监听端口与公网端口；
- 证书/SNI；
- 服务启动；
- v2rayN/sing-box 实际联网；
- agent 回填和订阅导入。

不要默认使用 `443`。HY2 内部端口和公网端口必须由用户明确填写。

### 7.4 AnyTLS

状态：**仅有骨架，不可视为完成。**

协议值：

```text
anytls
```

当前 `app/protocols/anytls.py` 的 `build_inbound()` 与 `build_share_link()` 仍抛出 `NotImplementedError`。虽然页面、常量和注册表已有 AnyTLS 入口，但不能据此宣称已支持部署或订阅。

继续开发时应先决定：完成实现，或在 UI 暂时隐藏 AnyTLS，避免用户进入不可用流程。

## 8. 路由与页面

核心页面/API：

```text
GET/POST /login
GET /nodes
GET/POST /nodes/new
GET/POST /nodes/new-chain
GET/POST /nodes/import
GET/POST /nodes/new-import
GET /nodes/{node_id}
GET/POST /nodes/{node_id}/edit
POST /nodes/{node_id}/reinstall
POST /nodes/{node_id}/delete
POST /subscriptions/rotate-token
GET /sub/{token}
GET /sub/{token}/clash
POST /api/agent/report
GET /api/deployments/{deploy_id}
```

Agent 默认上报路径来自：

```text
NAT_WEBUI_AGENT_REPORT_PATH=/api/agent/report
```

## 9. 测试与当前质量基线

2026-08-10 在干净临时 venv 中执行：

```bash
python3 -m py_compile app/main.py app/db.py app/deployer.py app/chain_deployer.py app/protocols/*.py
PYTHONPATH=. pytest -q tests/test_app.py
```

结果：

```text
48 passed
```

覆盖内容包括：

- Hysteria2 协议处理器、链接和订阅；
- AnyTLS 未实现行为；
- VLESS/链式配置；
- `auth_user` 路由回归；
- 导入节点；
- scope 分类订阅；
- token 轮换；
- IP 遮盖、密码输入和日志脱敏；
- OpenRC/systemd 部署脚本片段。

测试通过仅证明当前单元/应用测试基线，没有替代真实远端部署验收。

## 10. 已知风险与不一致

1. 当前没有生产实例，不能从页面现状推断运行状态。
2. 仓库本地数据库只有重复测试数据，不是生产数据库。
3. `README.md` 和 `PHASE2.md` 部分描述落后于当前代码；本 handoff 优先级更高。
4. AnyTLS UI/常量已出现，但协议实现未完成。
5. Hysteria2 已通过测试，但缺真实 NAT + UDP 端到端验收。
6. `app/main.py` 体积较大，路由、表单校验、订阅生成混在一起；不要在没有测试保护时大拆重构。
7. SQLite 保存管理凭据，正式部署必须限制文件权限并做好离线备份。
8. 当前登录默认值不安全，生产必须通过 `.env.runtime` 显式覆盖。
9. agent 依赖 cron 和面板可达地址；面板若只监听本机或内网，外部 NAT 节点无法上报。
10. 旧归档库包含历史节点状态，可能与真实远端配置不一致，不能直接当真。

## 11. 明确未实现/待办

### 高优先级

1. 选择正式 Debian/Ubuntu 服务器重新部署面板，路径建议 `/opt/nat-webui`。
2. 建立 `.env.runtime`、systemd、数据库备份和访问入口。
3. 用一个小范围真实节点完成 VLESS 全链路回归。
4. 用真实 UDP NAT 节点完成 Hysteria2 验收。
5. 隐藏 AnyTLS 或补完其实现与真实验收。
6. 清理仓库内重复的 `CCS_TEST` 测试数据，生产数据库从空库开始。

### 中优先级

1. 自注册一键安装作为 SSH 推送的补充，不替代原流程。
2. 自注册第一版仅支持直连节点，可作为链式后端，不作为链式前置。
3. 建议新增字段：

```text
enroll_method=ssh/self_install
agent_version
manage_capability=ssh/agent/readonly
has_ssh
last_report_at
```

4. 自注册 NAT 节点生成命令前仍需用户填写 `public_port`，可选公网地址/DDNS。
5. 更新 README，使协议状态、运行路径和三类节点与当前代码一致。
6. 增加数据库迁移/备份文档，避免复制旧 SQLite 后出现 schema 与代码不一致。

## 12. 继续开发规则

1. 开工前先读本文件，再读目标模块和对应测试。
2. 先确认是在改仓库还是正式运行目录；目前只有仓库，没有正式运行目录。
3. 现有“面板 SSH 推送部署”体系是主路径，不得被整体替换。
4. NAT 节点必须区分 `listen_port` 和 `public_port`。
5. HY2 不得默认 `443`，两个端口都必须明确输入。
6. 链式路由必须使用 `auth_user`。
7. 仅导入节点不得要求 SSH，也不得出现重装操作。
8. 修改配置、订阅或部署行为后，必须补测试并做真实小范围验收。
9. 运行生产服务必须使用 `scripts/run-prod.sh`。
10. 不提交 `.env.runtime`、SQLite 数据库、日志、密钥、密码、token 和完整节点链接。
11. 有意义的代码或文档修改完成后必须 push 到 GitHub。
12. 真实切换遵循：先加新、测试通过、再停旧。

## 13. 推荐下一步

下一次接手建议按以下顺序：

```text
1. 选定正式部署服务器与外部访问方式
2. 从空数据库部署当前 main
3. 创建一个测试 VLESS 节点并验证 SSH 推送、订阅、agent 上报
4. 创建一个测试导入节点并作为链式后端验证出口 IP
5. 用一台有真实 UDP 映射的 NAT 节点验收 Hysteria2
6. 决定 AnyTLS 是补完还是暂时隐藏
7. 验收后更新 README 和本 handoff
```

完成判据不是“页面能打开”，而是：

```text
面板启动正常
+ SSH 部署成功
+ 远端服务自启
+ agent 持续上报
+ 各类订阅可导入
+ 客户端真实联网
+ 链式出口 IP 正确
+ 重启后仍正常
```
