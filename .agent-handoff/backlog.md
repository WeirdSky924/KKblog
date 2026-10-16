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
- [x] `B-018` 本轮重建生产 Worker；容器 socket 与宿主设备/inode 一致、权限 `0660`、UID/GID `999:10001`，Worker healthy。
- [x] `B-019` 在 Labs 用有界 SafeHttpClient/robots 请求和聚焦回归确认 Hotjob、Getui、Dahua、Beisen 响应契约，修复相应 parser；Meituan 五页只读解析未复现响应错误。生产数据未写入。
- [x] `B-020` 本轮最终有效代码与公告已推送并 fast-forward 到远端 `main=d06af75`；临时任务分支已清理。
- [x] `B-021` 生产应用 `learning.0014/0015`，切换 Web/Worker/Beat、收集静态资源，通过现有 service 检查 35 个来源，恢复公网并关闭 Labs Web/P12 测试服务；保留真实失败状态。
- [x] `B-022` 正式维护入口归宿主 Nginx；Caddy 保持既有基线，没有重复 Caddy marker。
- [ ] `B-023` 调查生产 PostgreSQL backend 两次 exit-code 2 自动恢复的根因；在 Labs 校准并修复 3 个 HTTP parser stale 来源和 Qcraft source timeout 后再做定向复查。
- [x] `B-024` 确认 Labs 已从当前远端主线建立 `codex/labs-next-20261013`，且运行时代码与正式 `d06af75` 基线一致。
- [x] `B-025` 重启 Labs P12 PostgreSQL/Redis/Mailpit 及 Web/Worker/Beat，并读回公网 health；Outbox timer/service 启动超时已记录并停止。
- [x] `B-026` 已接收并完成答题 UI 下一轮切片；实现、验证和发布边界记录在 `docs/releases/2026-10-13-next-iteration/quiz-ui-20261013.md`。
- [ ] `B-027` 调查 Labs Outbox 对两条历史 `apps.operations.weekly_backup` 的 `task.final_failed.v1` 事件持续 transport failure 的根因；事件未删除或清零，不得直接改写状态。
- [x] `B-028` 修复答题选项展示标签与刷题最终提交按钮：按当前顺序显示 `A/B/C/D`，全部题目揭晓后提交整张试卷；聚焦回归和 Labs 静态读回通过。
- [x] `B-029` 完成首页匿名留言板：独立首页发布入口、注册/纯文本/2/20 配额、10 条 keyset 加载、滚动收起/重开、管理员隐藏/删除/阅否毕标记；迁移仅应用到 Labs 并完成真实页面读回。
- [x] `B-030` 调整留言板到 Hero 上下中心，补齐留言输入浮窗的标题栏/表单/操作区布局，并完成桌面、390px 和成员态结构回归。
- [ ] `B-031` 浏览器状态可用后验收留言板二次展示：390/768px 边界、手动收起后侧边入口展开、管理员留言卡片和单页统一分页；本轮桌面只完成几何读回。
- [ ] `B-032` 用可授权的作者态浏览器验证图片四档宽度按编辑列计算：检查自然尺寸小于列宽的图片在 25/50/75/100% 时的实际宽度及比例；CSS 默认选择器修复已构建并同步 Labs。
- [x] `B-033` 将留言板布局变量移至 HTMX 不替换的首页容器，并让主页吸附 wheel listener 跳过留言板；桌面替换前后尺寸一致、滚轮只滚留言列表，390px 边界读回通过。真实认证 POST 未执行。
- [ ] `B-034` 在可授权的 Labs 登录态成功发布一条留言，确认真实 POST 后面板尺寸保持；不创建或借用账户。
- [x] `B-035` 用户明确授权后，已对 Labs `kaj_test_production_clone` 应用 `accounts.0010_account_author_permission_requested_at`，读回 schema/migration、迁移后计划和匿名作者入口；登录普通用户申请页面仍待可授权 session 验证，不创建或借用真实账户。
- [x] `B-036` 修复 Labs 注册/作者申请管理员通知未到达：重启 10 月 13 日启动的旧 Celery Worker；两类 Outbox 事件均发布、consumer 均处理，活跃管理员各有一条未读通知回执。没有发送邮件或调用 Provider/AGENT。
- [ ] `B-037` 在隔离 PostgreSQL/Redis/Mailpit 环境运行 `apps/accounts/tests/test_admin_password_reset.py`；当前四项 `KAJ_TEST_*` 环境变量缺失，不得用共享 Labs 数据库/Mailpit。
- [x] `B-038` 用户明确授权后，仅在 Labs `kaj_test_production_clone` 应用 `accounts.0011_admin_password_reset`；读回表字段、主键/外键、摘要唯一、有效期检查约束、migration 记录和迁移后空计划，health/live 与 ready 均为 200。没有生产操作、邮件发送或服务重启。
- [ ] `B-039` 获得隔离 PostgreSQL/Redis/Mailpit 环境和可授权 Labs 管理员/目标用户 session 后，验证重置邮件按钮、测试邮箱投递、链接兑换和密码登录；不得发送到真实用户邮箱或使用共享 Labs DB/Mailpit 执行测试。
- [x] `B-040` 修复管理员重置页因 `Referrer-Policy: no-referrer` 导致 `Origin: null` 的 CSRF 403；改为 `same-origin`，保留 CSRF 校验，并完成响应头/同站协议对比。修复后的浏览器复测受 Labs 504 阻断，待稳定后补一次真实页面读回。
- [x] `B-041` 修复全局右上角通知遮挡顶部栏悬浮菜单：`.global-feedback` 从 `z-index: 80` 降为 `25`，低于 `.site-header: 30`；CSS 构建、公网版本和真实层级读回通过。认证态通知中心仍待有授权 session 后验收。
- [x] `B-042` 账户配额覆盖弹窗复用留言输入窗口的 `confirm-dialog-panel` 样式；共享标题栏、遮罩、内容间距、关闭按钮和窄屏单列规则已构建并在 Labs 读回。真实管理员入口和保存操作仍待授权 session。

## Backlog Guidelines

- Keep tasks actionable.
- Remove completed or obsolete items.
- Link items to risks, decisions, or files when useful.
