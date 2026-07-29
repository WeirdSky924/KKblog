# Kaj 的小房间

Kaj 的小房间是一个面向中文用户、支持移动端的私人博客项目，采用 Django 模块化单体、服务端模板与 HTMX 局部增强。

## 当前状态

当前源码是**可部署但未部署**的交付候选：需求、实现、测试和本地部署门禁已建立，准确的实施阶段、任务状态与验收证据统一见[实施总清单](docs/planning/implementation-todolist.md)，本 README 不维护第二份进度账。隔离环境验证不代表存在生产配置、生产数据库、生产备份、已认证邮件身份或已部署服务。

当前没有生产域名、管理员邮箱、已认证 Resend 发件身份或生产密钥；未执行生产 migration、生产备份、恢复演练、部署或服务重启。本轮仅创建本地 Git 提交，明确不推送、不集成远端默认分支；提交源码不表示已经部署。禁止自动部署；推送、集成和生产动作只在用户当前回合分别明确授权后执行。

## 技术方向

- Python 3.12、Django、PostgreSQL、Redis、Celery。
- Django Templates、HTMX、Alpine.js、Tailwind CSS、TipTap。
- `uv` 管理 Python 依赖；pytest、Ruff、Playwright 提供质量门禁。
- Docker Compose、Gunicorn、Celery、Caddy、Mailpit 和 Umami 的运行时入口已建立；Umami 同源管理员入口、全站 tracker 配置和一个月保留代码已集成。部署入口目前只有 fail-closed 规划器/模拟器，没有生产命令适配器；真实启动、首次配置、跟踪、清理和部署仍需当前回合明确授权。

## 项目真值

- [实施总清单](docs/planning/implementation-todolist.md)
- [阶段执行契约](docs/planning/implementation-readiness.md)
- [架构总览](docs/architecture/README.md)
- [页面状态矩阵](docs/prototype/page-state-matrix.md)
- [贡献指南](CONTRIBUTING.md)
- [运维入口](docs/operations/README.md)
- [测试环境与固定命令](docs/operations/testing.md)

不要从原型假数据推断业务已完成。

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
