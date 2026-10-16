# 2026-10-17 正式增量更新前检查

状态：执行中；每项以 `deployment-record.md` 的新鲜命令和读回为准。

- [ ] 远端默认分支确认、任务分支提交和 fast-forward 读回完成。
- [ ] 候选镜像基于生产 `d06af75a9c31`，包含 `apps/`、`config/`、模板和 `static/dist/`。
- [ ] `npm run build`、前端测试、Ruff、Django `check --deploy`、migration drift、候选 Compose 检查通过。
- [ ] 候选 migration plan 只包含 `accounts.0010`、`accounts.0011`、`comments.0006`、`comments.0007`（若实际读回不同则停止并记录）。
- [ ] 生产数据库、媒体和 Compose 备份均为本次维护窗口新建且可读。
- [ ] 生产维护入口、旧应用健康和候选 loopback health 已核验。
- [ ] 迁移成功后 Web、Worker、Beat 使用同一候选 revision，restart count 无异常。
- [ ] 招聘状态修正只通过恢复 service 完成；Provider/AGENT/采集未调用。
- [ ] 公网 live/ready、首页、公开岗位页、答题入口和重置页读回通过。
- [ ] Labs Web、Worker、Beat、Beat 依赖的测试资源和临时测试容器均按本轮收尾要求关闭，数据卷保留。
