# 2026-10-17 正式增量更新前检查

状态：已完成；证据见同目录 `deployment-record.md`。

- [x] 远端默认分支确认、任务分支提交和 fast-forward 读回完成。
- [x] 候选镜像基于生产 `d06af75a9c31`，包含 `apps/`、`config/`、模板和 `static/dist/`。
- [x] `npm run build`、前端测试、Ruff、Django `check --deploy`、migration drift、候选 Compose 检查通过。
- [x] 候选 migration plan 只包含 `accounts.0010`、`accounts.0011`、`comments.0006`、`comments.0007`。
- [x] 生产数据库、媒体和 Compose 备份均为本次维护窗口新建且可读。
- [x] 生产维护入口、旧应用健康和候选 loopback health 已核验。
- [x] 迁移成功后 Web、Worker、Beat 使用同一候选 revision，restart count 为 `0`。
- [x] 招聘状态修正只通过恢复 service 完成；Provider/AGENT/采集未调用。
- [x] 公网 live/ready、首页和公开岗位入口读回通过。
- [x] Labs Web、Worker、Beat、Outbox service/timer 和临时测试容器均已停止；数据卷、媒体和备份保留。
