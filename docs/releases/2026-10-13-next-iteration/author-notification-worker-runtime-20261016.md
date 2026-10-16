# Labs 注册与作者申请通知运行态修复（2026-10-16）

## 现象与根因

- 用户在 Labs 测试注册和作者权限申请后，管理员没有收到两条站内通知。
- Labs 数据库中已有 `account.registered.v1` 和 `account.author_permission_requested.v1` 各 1 条 Outbox 事件，但均为 `pending`，没有对应 consumer 记录或通知回执；数据库中存在 1 个启用管理员。
- Celery Worker 的进程于 `2026-10-13 18:15:32 CST` 启动；通知路由与 consumer 源文件在 `2026-10-16` 才更新。Django Web 热重载不会刷新长期运行的 Celery Worker 已导入的 Python 模块，Worker 因而没有加载新事件路由。

## 修复与读回

- 只温和重启 Labs `kaj-labs-worker.service`，让 Worker 从活动 Labs worktree 加载当前代码；没有重启 Web、Beat、PostgreSQL、Redis 或 Outbox timer。
- 新 Worker 于 `2026-10-16 13:35:04 CST` 进入 `active/running`。现有 Beat 按原有五秒调度继续调用 Outbox 发布任务。
- 数据库只读读回：两类账户事件均为 `published`；对应 consumer 各有 1 条 `processed` 记录；`account.registered.v1` 和 `account.author_permission_requested.v1` 各创建 1 条通知，并各有 1 条发给启用管理员的未读 `NotificationReceipt`。
- Labs 公网 `/health/live` 为 `200`。没有可用管理员浏览器 session，因此未执行通知铃铛/通知中心的真实 UI 读回；管理员刷新站内通知列表后应能看到这两条通知。

## 保留事项与边界

- `kaj-labs-outbox.service` 仍为 `failed/timeout`，`kaj-labs-outbox.timer` 仍为 `inactive/dead`。账户通知由当前 Celery Worker/Beat 路径完成消费。
- 队列中另外两条 `apps.operations.weekly_backup` 的 `task.final_failed.v1` 事件仍为 `pending`，没有 consumer 记录且重试次数很高。未删除、清零或改写这两条事件；其根因留在独立 backlog `B-027`。
- Outbox 运行入口强制 `KAJ_LABS_SMTP_ENABLED=false`；本轮未发送邮件、未调用 Provider/AGENT、未运行招聘采集，也未执行生产操作或 Git 写操作。
- 本轮没有代码变更，也没有重跑既有隔离测试；完成依据是 Worker 重新加载后的真实 Labs Outbox、consumer、Notification/Receipt 数据读回。
