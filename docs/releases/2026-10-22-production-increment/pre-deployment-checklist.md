# 2026-10-22 正式增量更新前检查

状态：执行中；完成证据回填至 `deployment-record.md`。

- [ ] 远端默认分支与 production baseline 新鲜读回；Labs 所有纳入范围的改动已审查并提交。
- [ ] 本轮任务分支已推送并 fast-forward 集成到远端 `main`；提交 SHA 与公告一致。
- [ ] `npm run build`、前端测试、聚焦 PostgreSQL 回归、Ruff、`git diff --check` 通过。
- [ ] 候选基于当前生产镜像，`check --deploy`、migration drift、Compose、`collectstatic` 检查通过。
- [ ] `.dockerignore` 未丢弃 `static/dist/`；增量镜像实际复制本轮构建的 CSS/JS bundle。
- [ ] 候选 `migrate --plan` 只含 `navigation.0009_focus_mode_settings`；生产当前迁移状态已读回。
- [ ] 维护前 PostgreSQL dump、媒体归档、Compose 快照新鲜、权限 `0600`、摘要和可读性验证通过。
- [ ] 生产岗位运行异常已只读复核；若没有异常，不执行数据写修复或任何采集。
- [ ] 维护窗口中 migration、Web/Worker/Beat 切换、镜像 revision、health、restart count、静态资源与页面读回全部通过。
- [ ] 维护标记关闭后公网 live/ready、首页和目标文章页均正常。
- [ ] Labs Web/Worker/Beat/Outbox 与 P12 PostgreSQL/Redis/Mailpit 已停止；生产和其他 worktree 服务保持原状态。
- [ ] 本轮正式公告仅包含当前提交和本次结果；历史公告保持各自独立。
