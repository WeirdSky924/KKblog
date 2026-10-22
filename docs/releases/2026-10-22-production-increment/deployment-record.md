# 2026-10-22 正式增量更新记录

状态：已完成（2026-10-22，Asia/Singapore）。

## Git 与候选

- 远端默认分支：`main`。
- 任务分支：`codex/production-increment-20261022`。
- 本轮运行时代码提交：`e179693d48157aea613f5604bf10058de6849f16`，`feat: add article focus and mobile reader modes`。
- 任务分支推送成功；远端 `main` 从 `d0407d6a17206296507f530fcea0537acf52ffb9` fast-forward 到 `e179693d48157aea613f5604bf10058de6849f16`，读回一致。
- 生产基线镜像：`kaj-blog-web:2c78cddf92ac`，镜像 ID `sha256:029f2d458e4241813a0550bbfe8d5c6680e9cbf0cdd6384c9857e3f23c836a2e`，revision `2c78cddf92acf6adf7f33f3c57affa32cada522e`。
- 候选镜像：`kaj-blog-web:e179693d4815`，镜像 ID `sha256:d9701c9517cd24869fcc94d7cb693c1e54405e35245791b4c79a698fc1f0432c`，OCI revision `e179693d48157aea613f5604bf10058de6849f16`。
- 增量构建前修复 `.dockerignore` 与 `COPY static/dist/` 的冲突；实际构建成功并将 7.81 MB 构建上下文中的 `static/dist/` 复制进候选镜像。

## 验证

- `npm run build`：退出码 `0`，CSS、导航、主题、字体和 app bundle 均构建成功。
- `npm run test:frontend`：`5 passed`、退出码 `0`；有仓库既有的 Node module-type 性能提示。
- 隔离 PostgreSQL/Redis/Mailpit 聚焦回归：`29 passed in 200.71s`、退出码 `0`；测试数据库运行后自动清理。
- Ruff check/format：目标 16 个 Python 源码和测试文件全部通过；`node --check` 的专注/阅读模块和 app bundle、`git diff --check` 均通过。
- `makemigrations --check --dry-run`：`No changes detected`、退出码 `0`；测试库已自动清理，命令同时给出无法连接不存在临时 DB 的一致性历史 warning。候选镜像还须执行 migration drift 与生产 plan 复核。
- 候选镜像 `manage.py check --deploy`：`System check identified no issues`；候选 `makemigrations --check --dry-run`：`No changes detected`。
- 生产 migration plan 只包含 `navigation.0009_focus_mode_settings`；migration 成功后再次 plan 为 `No planned migration operations`。
- 候选 `collectstatic --noinput`：`165 static files copied, 3 unmodified, 4 post-processed`；生产 Compose `config --quiet` 通过，候选三服务镜像均读回同一 image tag。
- 用户可见流程以 Labs 已有证据和本轮构建/HTTP 读回为准；最新手机浮层布局未进行浏览器复测，等待用户实机验收。

## 生产数据与备份

- 发布前岗位状态核查：终态父运行活动来源 `0`、活动父运行 `0`、活动来源 `0`、运行中的岗位 TaskRun `0`。本次没有新的状态记录需要修复；没有运行招聘 adapter。
- 聚焦回归只连接 Labs P12 PostgreSQL 的独立测试库、Redis DB `15` 和 Labs Mailpit；测试库在命令结束后自动删除，共享 Labs clone 未作为测试数据库。
- PostgreSQL dump：`pre-deploy-e179693-20261022T075223Z.dump`，`316558986` bytes，权限 `0600`，SHA-256 `aade2216b10c959181e9d869b98c527a4dc7042366b8b9ff9db5adc364b88eff`；在只读 PostgreSQL utility container 中 `pg_restore --list` 退出码 `0`。
- 媒体归档：`pre-deploy-e179693-20261022T075223Z-media.tar.gz`，`7557123` bytes，权限 `0600`，SHA-256 `fa80631be70a8dbc7dc8b8babeefb2f47c1fc52bb3adca88dd331381ad777b48`；归档 `437` entries，无源 symlink、绝对路径或 `..` 成员。
- Compose runtime 快照：`compose.runtime.yaml.pre-e179693-20261022T075223Z`，`6418` bytes，权限 `0600`，SHA-256 `eb9f73efab0a1c514e0242493d14c7027bddc78b7436f956298ef362ad5d0e04`。
- 数据修正：迁移前后终态父运行活动来源 `0`、活动父运行 `0`、活动来源 `0`、运行中的岗位 TaskRun `0`。10 月 17 日孤儿来源修正保持正确，本轮无新错误记录可修；未调用恢复 service、dispatcher、adapter 或招聘采集。
- `navigation.0009_focus_mode_settings` 已应用；迁移记录与范围约束存在，站点单例值读回为 idle `3` 分钟、manual pause `3` 次。

## 切换与读回

- 维护窗口启用后，公网返回 `503`、`Cache-Control: no-store`、`Retry-After: 120`；旧应用保留，旧 Beat/Worker 在 `running TaskRun=0` 时优雅停止。
- Web/Worker/Beat 全部运行 `kaj-blog-web:e179693d4815`、revision `e179693d...`；Web/Worker `healthy`、Beat `running`，三个容器 restart count 均为 `0`。Caddy、PostgreSQL、Redis、Umami、生产 Mailpit 未重建。
- 候选 loopback health 带正式 Host 与 `X-Kaj-Client-IP` 代理头读回 `200/200`；初次探针遗漏受信代理头而返回 `500`，补齐头后 live/ready 均通过。
- 公网恢复后 `/health/live=200`、`/health/ready=200`、首页 `200`、公开文章 `200`。公开文章含阅读模式入口/浮层及 cache version `article-reader-overlay-20261022c`。
- 公网 CSS `styles.eafabd3d0f8f.css` 返回 `200`，SHA-256 `f9afd3a4e7949d40b8a40ea161e0dd25dbcf4765127147040c5218fbf0873b41`；app JS `app.e256985201a6.js` 返回 `200`，SHA-256 `f3e262fc7a6aea25afdcff3e29c95f8749940d0271839d14b64176c34b3e97ee`；均与 production staticfiles 候选一致。
- loopback、迁移、静态资源和目标公开页面通过后移除维护标记；随后公网 live/ready/home 保持 `200`。

## Labs 收尾

- `kaj-labs.service` inactive/dead；Worker、Beat、Outbox service 为 failed 且 `MainPID=0`；Outbox timer inactive/dead。未执行 `reset-failed`，保留其诊断状态。
- `kaj-p12-postgres`、`kaj-p12-redis`、`kaj-p12-mailpit` 均为 `Exited (0)`；仅停止容器，数据卷、媒体、日志和备份保留。生产容器继续健康运行。
- 按用户偏好未启动浏览器；手机版阅读模式与专注模式的真实手势/视觉验收由用户自行完成。
