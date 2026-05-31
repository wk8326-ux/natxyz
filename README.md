# NAT WebUI

轻量 NAT 节点管理面板原型。当前已打通：登录、节点列表、节点详情、新建/编辑/删除、单节点部署、部署详情、agent 上报回填、节点列表一键复制链接、基础订阅 URL、前置机/后端链式节点展示、DDNS 域名型家宽节点部署。

## 当前能力

- 管理员登录
- 节点 CRUD
- NAT 节点地址栏支持固定 IP 或 DDNS 域名
- 单节点 `开始部署 / 重新部署`
- VLESS Reality 部署：域名型节点会先解析 DDNS 当前 IP 用于 SSH，最终 VLESS 链接仍保留域名
- Alpine / Debian 基础依赖自动补装，包括 `python3`、`curl`、`ca-certificates`、`tar`、`gzip`、`coreutils`
- 部署详情页与结果回填
- agent 上报在线状态
- 节点列表一键复制 `VLESS` 导入链接
- 订阅 URL：返回当前全部有效节点的 Base64 订阅内容

## 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export NAT_WEBUI_SESSION_SECRET='your-session-secret'
export NAT_WEBUI_ADMIN_USERNAME='your-admin'
export NAT_WEBUI_ADMIN_PASSWORD='your-password'
uvicorn app.main:app --host 0.0.0.0 --port 8788
```

## 关键环境变量

- `NAT_WEBUI_SESSION_SECRET`
- `NAT_WEBUI_ADMIN_USERNAME`
- `NAT_WEBUI_ADMIN_PASSWORD`
- `NAT_WEBUI_DB_PATH`（可选）
- `NAT_WEBUI_STATUS_STALE_MINUTES`（可选）
- `NAT_WEBUI_AGENT_REPORT_PATH`（可选）

## VLESS / DDNS 节点说明

新建或编辑 VLESS Reality 节点时，`NAT IP / DDNS 域名` 字段可填写：

- 固定公网 IP，例如 `1.2.3.4`
- DDNS 域名，例如 `hinet.example.com`

如果填写域名：

- 面板会规范化输入值，例如去掉 `http://` / `https://`、路径和无意义端口
- 部署时先解析域名得到当前 IP，再用解析 IP 执行 SSH
- 远端安装流程仍使用原来的 VLESS Reality 脚本
- 最终生成的 `vless://` 导入链接使用原始域名作为 server，适合动态 IP 家宽节点

## 订阅说明

节点列表页顶部会生成当前系统的订阅 URL。

订阅接口返回：
- 当前所有有 `last_vless_link` 的节点
- 每条链接按换行拼接
- 整体 Base64 编码

适合直接导入 v2rayN / NekoBox 等客户端，并通过“更新订阅”同步新增或变更节点。

## 注意

- `data/*.db` 与 `logs/*.log` 已默认忽略，不应提交运行期数据
- `data/*.log`、`data/*.bak.*`、`*.bak.*` 为本地运行/备份产物，不应提交
- 仓库默认配置仅用于开发占位，正式环境请务必用环境变量覆盖管理员账号、密码与 session secret
