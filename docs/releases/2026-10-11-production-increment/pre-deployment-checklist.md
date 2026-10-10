# 2026-10-11 正式增量更新检查清单

## Labs 与候选

- [x] 答题模式聚焦回归和相关记录回归通过。
- [x] 招聘适配器、Worker socket 与部署维护路由聚焦回归通过。
- [x] `manage.py check`、migration drift、目标 Ruff/format、JavaScript 语法、前端完整构建和 `git diff --check` 通过。
- [x] Labs 应用 `learning.0015_quiz_attempt_mode_db_default`，读回 `mode` 数据库默认值 `'EXAM'`。
- [x] 生产只读基线：Web/Worker/Beat 为 `42adeb4ceb74`，Caddy 为 `2cbead0`；live/ready 为 `200`。
- [x] 生产 learning migration leaf 为 `0013_generation_batches`。
- [x] 生产共有 35 条启用的 `STALE` 来源；26 个浏览器 socket 错误、8 个响应契约错误、1 个超时；没有活动来源检查运行。
- [x] 正式 Caddy 维护候选基于现有 Caddy 镜像构建，Caddy `adapt --validate` 退出 `0`。

## Git 与生产

- [ ] 远端默认分支包含全部本轮提交，任务分支已完成 fast-forward 集成和清理。
- [ ] Web/Caddy 候选镜像构建成功，源码 revision 与镜像 ID 已记录。
- [ ] 候选 `check --deploy`、`makemigrations --check --dry-run` 与正式 `migrate --plan` 通过。
- [ ] PostgreSQL、媒体和 Compose 新鲜备份完成，权限 `0600`，摘要和可读性已读回。
- [ ] Caddy 维护开关、`0014+0015` migration、Web/Worker/Beat 顺序切换和 `collectstatic` 完成。
- [ ] 35 条来源逐条重新检查并按实际终态读回；未执行全量招聘检查或 Provider/AGENT 调用。
- [ ] 正式页面/静态/健康读回完成，维护模式关闭。
- [ ] Labs Web 及本轮相关测试服务停止，测试数据与卷保留。
