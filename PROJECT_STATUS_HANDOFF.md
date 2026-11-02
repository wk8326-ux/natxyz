# natxyz 项目交接文档

最后核验：2026-11-02。

## 仓库与同步范围

- 项目仓库：`https://github.com/wk8326-ux/natxyz`，默认分支 `main`。
- 本次工程同步来源：`yun8811/natwebui` 的 `7fa01acc355fd642f4fdb3e1d021fff72b5a280d`。
- 同步范围：`app/`（含模板、静态资源、协议实现）、`scripts/`、`tests/`、`docs/`、依赖清单和安全目录占位。
- 保留本仓库身份和已有 Git 历史；README 与本交接文档按本仓库维护。
- 本文不记录生产主机、本地工作目录、部署凭据、节点记录或运行状态。部署实例状态应现场核验，不能由源码仓库推断。

## 当前功能

项目使用 FastAPI、Jinja2、SQLite 和 Paramiko 管理直连、链式及导入节点，提供远程 sing-box 部署、订阅输出和 Agent 上报。

导入节点支持多个分组：

- 使用 `node_import_groups` 关系表，保留旧 `nodes.import_group_id` 并迁移历史关系。
- 单节点导入及编辑支持多个 `import_group_ids`；批量导入支持默认分组。
- 分组订阅按关联关系筛选，不复制节点记录。

协议实现位于 `app/protocols/`。具体客户端支持与当前限制应同时核对源码、测试及上游官方文档。

## 主要代码入口

- `app/main.py`：页面、表单、订阅、部署与 Agent 路由。
- `app/db.py`：数据库初始化、迁移、节点与分组关系、日志脱敏。
- `app/deployer.py`：直连部署、远端配置和 Agent 生成。
- `app/chain_deployer.py`：链式配置生成；VLESS 用户路由使用 `auth_user`。
- `app/templates/`、`app/static/`：页面和主题资源。
- `scripts/run-prod.sh`：前台生产启动入口。
- `scripts/start.sh`：后台启动入口。
- `tests/test_app.py`：功能回归测试。

## 验证

在独立虚拟环境安装 `requirements.txt` 与 `pytest` 后运行：

```bash
PYTHONPATH=. python3 -m pytest -q
python3 -m compileall -q app tests
git diff --check
```

本次同步工作区测试结果：51 passed，2 条 FastAPI `on_event` 弃用警告。

## 部署与回退

部署前核验实际服务目录和 systemd 启动配置，备份代码、数据库、环境变量与服务定义。使用源码白名单增量更新，保留生产数据库、`.env.runtime` 和实例专有设置。数据库迁移后验证完整性、节点数量、页面、订阅和 Agent 上报。

回退时先停止服务，再按备份恢复匹配的代码与数据库，核对环境及服务配置后启动并验收。本次仓库同步本身不执行生产部署。

## 发布约束

运行数据仅留在部署环境。GitHub 中 `data/` 和 `logs/` 仅保留 `.gitkeep`。禁止提交数据库、日志、环境文件、备份、真实节点地址、密码、Token、密钥及完整真实代理链接；逐项检查范围见 README 的“GitHub 上传脱敏清单”。本地冻结记录和运维复盘不进入仓库。
