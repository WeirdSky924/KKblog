# 2026-10-22 正式增量更新记录

状态：执行中。

## Git 与候选

- 远端默认分支：`main`。
- 任务分支：`codex/production-increment-20261022`。
- 本轮代码提交：待提交。
- 本轮发布文档提交：待部署完成后记录。
- 生产基线镜像：`kaj-blog-web:2c78cddf92ac`；当前运行 revision 与镜像 ID 待部署前读回。
- 候选镜像、镜像 ID、OCI revision：待构建后填写。
- 增量构建上下文预检发现 `.dockerignore` 同时排除了 `static/dist/`，与 `Dockerfile.incremental` 的 `COPY static/dist/` 冲突；已增加精确例外，候选 Docker 构建待验证。

## 验证

- `npm run build`：退出码 `0`，CSS、导航、主题、字体和 app bundle 均构建成功。
- `npm run test:frontend`：`5 passed`、退出码 `0`；有仓库既有的 Node module-type 性能提示。
- 隔离 PostgreSQL/Redis/Mailpit 聚焦回归：`29 passed in 200.71s`、退出码 `0`；测试数据库运行后自动清理。
- Ruff check/format：目标 16 个 Python 源码和测试文件全部通过；`node --check` 的专注/阅读模块和 app bundle、`git diff --check` 均通过。
- `makemigrations --check --dry-run`：`No changes detected`、退出码 `0`；测试库已自动清理，命令同时给出无法连接不存在临时 DB 的一致性历史 warning。候选镜像还须执行 migration drift 与生产 plan 复核。
- `manage.py check --deploy`：待候选镜像执行。
- 候选 `migrate --plan`、`collectstatic --noinput` 和 Compose 读回：待执行。
- 用户可见流程以 Labs 已有证据和本轮构建/HTTP 读回为准；最新手机浮层布局未进行浏览器复测，等待用户实机验收。

## 生产数据与备份

- 发布前岗位状态核查：终态父运行活动来源 `0`、活动父运行 `0`、活动来源 `0`、运行中的岗位 TaskRun `0`。本次没有新的状态记录需要修复；没有运行招聘 adapter。
- 聚焦回归只连接 Labs P12 PostgreSQL 的独立测试库、Redis DB `15` 和 Labs Mailpit；测试库在命令结束后自动删除，共享 Labs clone 未作为测试数据库。
- PostgreSQL、媒体与 Compose 备份：待维护窗口生成并读回。
- migration plan 与应用结果：待执行。

## 切换与读回

- 维护标记、公网维护响应、旧应用快照与候选 loopback health：待执行。
- Web/Worker/Beat 镜像 revision、容器 health、restart count：待执行。
- `/health/live`、`/health/ready`、首页、文章详情与配置入口：待执行。
- 维护标记关闭和生产路由恢复：待执行。

## Labs 收尾

- `kaj-labs.service`、Worker、Beat、Outbox service/timer 与 P12 PostgreSQL/Redis/Mailpit 停止状态：待执行。
- 仅停止本项目 Labs 测试服务；数据卷、媒体、日志、备份和生产服务保留。
