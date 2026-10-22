# 2026-10-22 正式增量更新前检查

状态：已完成；执行证据见 `deployment-record.md`。

- [x] 远端默认分支与 production baseline 新鲜读回；Labs 所有纳入范围的改动已审查并提交。
- [x] 本轮任务分支已推送并 fast-forward 集成到远端 `main`；提交 SHA 与公告一致。
- [x] `npm run build`、前端测试、聚焦 PostgreSQL 回归、Ruff、`git diff --check` 通过。
- [x] 候选基于当前生产镜像，`check --deploy`、migration drift、Compose、`collectstatic` 检查通过。
- [x] `.dockerignore` 未丢弃 `static/dist/`；增量镜像实际复制本轮构建的 CSS/JS bundle。
- [x] 候选 `migrate --plan` 只含 `navigation.0009_focus_mode_settings`；生产当前迁移状态已读回。
- [x] 维护前 PostgreSQL dump、媒体归档、Compose 快照新鲜、权限 `0600`、摘要和可读性验证通过。
- [x] 生产岗位运行异常已只读复核；没有新的异常，因此没有数据写修复或招聘采集。
- [x] 维护窗口中 migration、Web/Worker/Beat 切换、镜像 revision、health、restart count、静态资源与页面读回全部通过。
- [x] 维护标记关闭后公网 live/ready、首页和目标文章页均正常。
- [x] Labs Web/Worker/Beat/Outbox 与 P12 PostgreSQL/Redis/Mailpit 已停止；生产和其他 worktree 服务保持原状态。
- [x] 本轮正式公告仅包含当前代码提交与本次结果；历史公告保持各自独立。
