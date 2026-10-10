# Task Backlog

- [x] `B-001` 新 Labs worktree 已从 `origin/main=631253f` 建立；正式应用 revision `42adeb4` 的运行时代码与该基线一致。
- [ ] `B-002` 在外部机器按 P0 文档执行正式环境低风险只读测试；本轮优化已部署，仍需填写对应执行结果。
- [ ] `B-003` 对生产 Endpoint 执行 `knowledge-review.v1` 严格 capability check，确认 `SUCCEEDED + SCHEMA_SUPPORTED + 当前 row_version` 后重试知识文档审核。
- [x] `B-004` 旧 Labs 中未提交的代码、测试、公告和 handoff 已随旧 worktree 原样归档到 `labs-test-environment-archive-20261009`，未混入新迭代分支。
- [x] `B-005` 用户明确 Git 交付后，从 Labs 任务分支提交 handoff 文件；已完成推送、fast-forward 集成和临时分支清理。
- [ ] `B-006` 更新或审查仍写着旧远端提交号的历史实施清单，避免把文档旧事实当作当前 Git 真值；先记录影响再决定是否修订。
- [x] `B-007` Labs 服务已恢复为 `active/running`；当前服务工作目录正确，`/health/live=200`，本轮静态产物已完成远端哈希读回。
- [x] `B-008` 提交并推送 `docs/releases/2026-09-20-production-increment/` 发布记录；未混入原有未跟踪 P0 文档，提交为 `6f59ed8`。
- [x] `B-009` 用户已明确下一轮产品切片为答题刷题模式；实施过程继续逐切片更新 `docs/releases/2026-10-09-next-iteration/announcement.md`。
- [x] `B-010` 实现考试/刷题模式：配置页默认考试；刷题逐题提交即时揭晓并锁题，自动保存不揭晓，整套提交不重复累计；隔离 migration、owner/兼容回归和本地真实浏览器流完成，Labs 测试库 schema 已同步。
- [x] `B-011` 按当前 Labs 数据库引用恢复 11 个非删除媒体文件，并确认头像、Hero、封面、正文图片和附件媒体可读。
- [x] `B-012` 已在 Labs 测试库应用 `learning.0014` 与 `learning.0015`；模式约束、migration 记录和数据库级 `EXAM` 默认值已读回。
- [ ] `B-013` 获得明确授权后，通过 `apps.learning` 管理服务恢复至少一个 `ADMIN_HIDDEN/security_review` 题库卷；保留审计和可回退状态。
- [x] `B-014` Labs 答题开始 500 已通过应用缺失的 `learning.0014_quizattempt_mode_and_more` 修复；用户后续已进入并提交答题，未再报告 500。
- [x] `B-015` 统一答题提交入口：考试模式提交整卷，刷题模式提交当前题；移除题目内重复按钮，解析栏按当前题揭晓状态展开/收起，切回已提交题自动恢复。
- [x] `B-016` 用户已手动确认刷题解析面板回到原右侧栏位置。
- [x] `B-017` 首页导航分区链接在 HTMX 成功替换文章列表后平滑定位至 `data-home-articles` 顶部；390/768/1440 与桌面深处滚动路径均通过 Labs 浏览器读回。
- [ ] `B-018` 本轮正式发布时，在浏览器 Unix socket 已就绪后重建 `kaj-production-worker-1`，读回容器内 socket 与宿主 inode 一致，并确认 Worker healthy。
- [x] `B-019` 在 Labs 用有界 SafeHttpClient/robots 请求和聚焦回归确认 Hotjob、Getui、Dahua、Beisen 响应契约，修复相应 parser；Meituan 五页只读解析未复现响应错误。生产数据未写入。
- [ ] `B-020` 当前用户已授权本轮提交/推送和生产增量更新；五个代码提交已在 `codex/labs-production-increment` 本地形成，待推送、fast-forward、候选构建与正式切换。
- [ ] `B-021` 应用 `learning.0014`/`0015`、部署答题/导航/招聘修复，按受影响来源检查流程重查固定 35 条 `STALE` 来源，并按用户要求关闭 Labs Web 与 P12 测试依赖。

## Backlog Guidelines

- Keep tasks actionable.
- Remove completed or obsolete items.
- Link items to risks, decisions, or files when useful.
