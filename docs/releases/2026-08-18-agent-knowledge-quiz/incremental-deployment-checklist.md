# 增量部署清单

## 发布前

- 在隔离环境运行相关 pytest、Ruff、format、Django check、`makemigrations --check --dry-run`、前端 CSS/JS build 和 `git diff --check`；本次跨模块回归结果为 `156 passed in 631.58s (0:10:31)`。
- 读取生产 `WorkingDirectory`、当前 migration leaf、数据库备份状态、媒体容量和服务 health；确认生产数据库独立于 Labs。
- 真实生产执行前创建并验证最新数据库备份；本次候选没有新增 T18-T20 schema，T16 已需要 `learning.0010`、`learning.0011` 时才执行对应前向迁移。
- 确认 API 开关保持关闭、真实 Provider/邮件/外部网络调用没有被测试配置带入生产。
- 若启用云端 AGENT，先在服务器创建 `root:root 0600` 的专用 Provider 环境文件，并在生产环境变量中设置 `KAJ_AGENT_ENV_FILE`；文件只包含 `KAJ_AGENT_SECRET_<ALIAS>` 和必要的 `KAJ_AGENT_INTERNAL_ENDPOINT_ALLOWLIST`。

## 应用与数据库顺序

1. 发布兼容应用镜像/代码，保持旧入口可用。
2. 生产执行 `manage.py migrate --plan`；若只包含已执行 leaf，则跳过写迁移。
3. 若生产尚未到 `learning.0011_quiz_contract_completion`，先备份、再按 `learning.0010 -> 0011` 前向迁移；不得执行回退作为应用回滚策略。
4. 读回 migration leaf、答题三表、不可变触发器、通知/TaskRun 和关键约束。
5. 读回 `/health/live`、`/health/ready`、匿名 `/knowledge/quiz/` 登录跳转及登录态答题路径后再结束维护窗口。
6. 管理员在 Endpoint 页面确认密钥别名已加载、连接检查返回可读错误或成功；没有密钥文件时不得把云端 Endpoint 标记为可用。

## 回退与风险

- 应用启动或页面异常时只回退应用代码，数据库保持向前并临时关闭答题入口；不要反向删除不可变学习事实。
- 迁移失败保留数据库备份和失败日志，停止后续发布；不自动重试破坏性清理。
- 账户终局清理、题库/记录到期清理和媒体文件删除由有界任务继续重试，不能由发布脚本直接清空表或媒体目录。

本清单只描述增量候选，不授权生产迁移、备份、服务重启、真实 Provider 或 Git 提交/推送；这些动作仍需当前回合单独授权。当前回合已完成 Labs 运行态读回：`kaj-labs.service` 为 `active/running`，live/ready 为 `200`，匿名答题/错题本/记录入口为 `302` 登录跳转。
