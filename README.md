# NAT WebUI

轻量 NAT 节点管理面板原型。当前已打通：登录、节点列表、节点详情、新建/编辑/删除、单节点部署、部署详情、agent 上报回填、节点列表一键复制链接、基础订阅 URL。

## 当前能力

- 管理员登录
- 节点 CRUD
- 单节点 `开始部署 / 重新部署`
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

## 订阅说明

节点列表页顶部会生成当前系统的订阅 URL。

订阅接口返回：
- 当前所有有 `last_vless_link` 的节点
- 每条链接按换行拼接
- 整体 Base64 编码

适合直接导入 v2rayN / NekoBox 等客户端，并通过“更新订阅”同步新增或变更节点。

## 注意

- `data/*.db` 与 `logs/*.log` 已默认忽略，不应提交运行期数据
- 仓库默认配置仅用于开发占位，正式环境请务必用环境变量覆盖管理员账号、密码与 session secret
