# 贡献指南

## 开始前

1. 阅读根 `AGENTS.md`。
2. 从 `docs/planning/implementation-todolist.md` 定位任务及全部前置 ID。
3. 阅读任务卡列出的来源章节、owner 契约和调用方。
4. 确认当前位于从已核验基线创建的 `codex/<task>` 分支。
5. 检查工作区并保留不属于当前任务的改动。

## 实施流程

每次只推进一条 Todo：

1. 将其标为 `进行中`。
2. 写出能证明目标缺失的聚焦 RED，并确认失败原因正确。
3. 在唯一 owner 内完成最小但闭合的实现。
4. 运行 GREEN、相关回归和真实数据或文件读回。
5. 对页面执行真实浏览器、视口、主题、键盘和焦点验证。
6. 回写命令、退出码、通过数、未执行项和风险，再开始下一条。

测试数据必须隔离，不得复制生产数据或秘密。临时探针、调试输出和一次性测试脚本完成后清理。

## 架构边界

- 跨 app 只使用公开 service、query 和 versioned event。
- `authoring`、`administration`、`discovery` 只做允许的编排或展示。
- 事务、权限、审计和 Outbox 由事实 owner 负责。
- Celery task 只重入可幂等 service；Redis 锁不是最终状态。
- 新公共 API 必须有真实消费者，不创建万能 repository、EventBus 或空包。

## 配置与秘密

只提交 `.env.example` 中的无秘密 schema。不要提交 `.env`、连接串、私钥、token、真实邮箱内容、数据库、媒体、日志或备份。任何生产必需值缺失都必须显式失败，不能使用测试身份或弱默认值兜底。

## Git 授权

实现授权只允许在安全任务分支修改工作区。`git add`、commit、push、默认分支集成、发布和部署需要用户在当前回合明确要求。获授权提交时使用中文 Conventional Commit 标题，并只包含本任务文件。
