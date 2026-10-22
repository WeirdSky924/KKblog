# Risks, Blockers, And Unknowns

## Current Blockers

- 本轮正式候选仍待构建、检查和切换；生产 migration、备份、服务健康、公告最终读回及 Labs Web/Worker/Beat/Outbox/P12 测试依赖关闭尚未完成。本轮尚未对生产作任何写入。
- ITER-004 手机版阅读器、翻页修正及分页设置浮层不挤压正文已构建并在 Labs 文章页读回，尚无真实手机交互证据；设置遮挡范围、上下单击显隐/滑动翻页、三分区点击、内层相邻页裁切、长代码块/表格/嵌入内容、旋转和关闭位置恢复的观感待用户实测。按用户测试偏好本轮未启动浏览器。
- ITER-003 专注模式和工具栏修正已完成 Labs CSS 构建/静态文件哈希读回；没有代码或 schema blocker。用户明确自行测试，本次工具栏交互/观感没有浏览器验收。
- Headless Chromium 拒绝 `requestFullscreen()`，提示缺少用户手势；真实浏览器中的全屏成功路径尚待用户实机确认。浏览器拒绝时普通页面继续的降级路径已实现。
- Labs Web/Worker/Beat 已恢复 `active/running`；Outbox service 仍保留历史 `failed/timeout` 状态、timer 为 `inactive/dead`，未通过 reset 或 SQL 清除诊断事实。
- 认证态留言板、作者权限申请、通知中心和管理员密码重置真实浏览器流仍缺少获授权 session；不创建或借用账户，不发送真实邮件。

## Current Risks

- 正式生产已经向前应用四项 migration；应用回退只允许恢复旧镜像，不反向迁移。数据库和媒体备份保存在 `/home/code/personal-blog/var/production/backups/`，不得进入 Git 或宽泛清理。
- 候选 Web 首次 readiness 探针受主机换页超时，但随后 Web/Worker health、Beat、loopback/public live/ready 均恢复正常，restart count 为 0；该主机资源约束仍要求重型操作串行。
- 生产岗位来源的 `DEGRADED/STALE` 事实没有被改写；本轮只修正了已证实的终态父运行孤儿来源明细。Provider、AGENT 和招聘采集均未调用。
- 外部 P0 公网并发复测尚未执行；本轮生产 health、页面和数据库读回不能替代 P0 低风险性能证据。
- Labs P12 测试容器保持运行且已完成健康读回；数据卷、媒体、备份和凭据均保留。测试文件未进入交付提交。
- 专注模式管理员设置页的浏览器输入动作受 CLI 可见/稳定等待超时影响，真实浏览器保存未读回；聚焦 Django 测试已覆盖保存与配置读回。当前 headless 页面上手动暂停次数序列末段通过 DOM click 事件读回，未把它描述为完整鼠标用户流。
- 专注边缘光晕最终收窄到 `article-focus-return-20261021g` 并在 Labs app bundle 中读回渐变尺寸和阴影值；本轮没有生成截图，最终颜色强度、边缘扩散观感和正文辨读仍待用户实测确认。
- 浏览器验证使用匿名首页上的临时 DOM 夹具和合成 blur/focus/pointer 事件，覆盖脚本状态转换与光效清除；未覆盖认证态工具栏实际用户点击、操作系统级窗口切换和全屏成功。

## Unknowns / Confirmations Needed

- UNKNOWN: 是否授权解除指定题库卷的 `security_review` 管理隐藏；必须通过 `apps.learning` 管理 service 并留下审计。
- UNKNOWN: 是否提供可授权管理员/普通用户浏览器状态和隔离 Mailpit，以完成认证态功能验收。
- UNKNOWN: 用户正常交互浏览器是否成功全屏，以及全屏拒绝提示在真实浏览器中的视觉呈现；`fullscreenEnabled=true`，但当前 headless 请求被用户手势策略拒绝。
- UNKNOWN: 用户是否确认收窄后的黄/红边缘光晕在实际文章阅读中范围适当、可见且不影响辨读。
- UNKNOWN: 用户是否确认工具栏胶囊扩宽及按钮禁止 flex 收缩后，按钮留白和窄屏布局符合预期；本轮由用户自行验收。
- UNKNOWN: 用户是否确认两种分页模式中单击显示设置时浮层遮挡适当、正文不改变视口尺寸，且上下滑动仍逐屏翻页；本轮按要求未启动浏览器。
- UNKNOWN: 外部 P0 测试机是否能取得 PostgreSQL、Redis、TaskRun、Outbox 和 Nginx timing 的只读快照。
- UNKNOWN: Labs Outbox 两条历史 `task.final_failed.v1` transport failure 的独立根因；不得直接改写、删除或清零事件。

## Risk Guidelines

- 继续维护真实失败状态，不用“成功”覆盖未经证据确认的结果。
- 生产数据写入必须复用领域 service；不得直接 SQL 改写业务状态。
- 下一代理先读取本文件和 `snapshot.md`，再以 `docs/releases/2026-10-20-next-iteration/announcement.md` 作为下一轮台账，以 `docs/releases/2026-10-17-production-increment/deployment-record.md` 作为上一轮生产事实来源。
