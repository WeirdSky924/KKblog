# Kaj 的小房间

Kaj 的小房间是一个面向中文用户、支持移动端的私人博客项目，采用 Django 模块化单体、服务端模板与 HTMX 局部增强。

## 当前状态

需求、原型基线、施工级架构和 P0 决策已经完成。P1 项目与质量骨架及 P2 运行时与跨域基础已在当前未提交工作区完成隔离验证；P3 及后续业务阶段尚未实施。P2 只提供可验证的本地运行入口、健康/任务/容量基础和部署模拟，不代表存在生产配置、生产数据库、备份、已认证邮件身份或已部署服务。

禁止自动部署。迁移、提交、推送、部署、生产邮件和生产备份只在用户当前回合明确授权后执行。

## 技术方向

- Python 3.12、Django、PostgreSQL、Redis、Celery。
- Django Templates、HTMX、Alpine.js、Tailwind CSS、TipTap。
- `uv` 管理 Python 依赖；pytest、Ruff、Playwright 提供质量门禁。
- Docker Compose、Gunicorn、Celery、Caddy、Mailpit 和 Umami 的运行时入口已建立；Umami 业务集成、生产配置与部署仍属于后续阶段或显式授权动作。

## 项目真值

- [实施总清单](docs/planning/implementation-todolist.md)
- [阶段执行契约](docs/planning/implementation-readiness.md)
- [架构总览](docs/architecture/README.md)
- [页面状态矩阵](docs/prototype/page-state-matrix.md)
- [贡献指南](CONTRIBUTING.md)
- [运维入口](docs/operations/README.md)
- [测试环境与固定命令](docs/operations/testing.md)

不要从原型假数据推断业务已完成，也不要在 README 维护第二份任务进度。

## 环境边界

开发和测试固定使用 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 与 Mailpit。生产必须提供真实域名、管理员邮箱、已认证 Resend 发件身份、密钥及其他必需秘密，缺少任一值时安全失败。

`.env`、`var/`、数据库、媒体、备份和日志不进入 Git。仓库只会提供无秘密的 `.env.example`；在其建立前，不应自行猜测环境变量或生产默认值。

## 开发入口

要求 Python 3.12、`uv`、Node 22 和 npm 10。依赖与基础入口使用：

```bash
uv sync --locked
npm ci
uv run python manage.py check
npm run build
```

完整 pytest 需要隔离的 loopback PostgreSQL、Redis 与 Mailpit，配置边界和固定命令见[测试环境与固定命令](docs/operations/testing.md)。这些测试入口不代表生产服务或部署已经建立。
