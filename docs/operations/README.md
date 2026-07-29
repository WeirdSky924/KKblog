# 运维入口

本目录是部署、备份、恢复、健康检查和故障处置文档的唯一入口。当前源码是可部署但未部署的交付候选；项目已有本地运行、备份任务和部署状态机模拟代码，但没有生产命令适配器。本文不表示存在生产域名、凭据、数据库、备份产物、恢复演练或已部署服务。

## 当前边界

- 禁止自动部署。部署和服务重启只在用户当前回合明确授权后执行。
- 当前未执行生产 migration、生产备份、生产恢复演练、部署或服务重启；本轮仅创建本地 Git 提交，明确不推送、不集成远端默认分支。
- 生产迁移前必须有新鲜备份；迁移失败时停止并保留当前运行版本。
- 生产缺真实域名、管理员邮箱、已认证 Resend 发件身份、密钥或其他必需秘密时拒绝启动。
- 开发和测试只使用 localhost 身份与 Mailpit，不向真实收件人发信。
- 首版备份目标仅为 local，计划为 Asia/Shanghai 每周一 03:00（`0 3 * * 1`）；任务完成只代表命令与归档成功。隔离测试仅证明 custom dump 可列出，manifest 的 `restore_verified=false`，未执行完整恢复演练。

## 架构来源

- [测试环境与固定命令](testing.md)
- [Migration 验证与兼容记录](migrations.md)
- [备份与人工恢复](backups.md)
- [Umami 同源分析与保留](analytics.md)
- [部署状态机骨架](deployment.md)
- [容量保护门禁](capacity-policy.md)
- [运行、部署与验证架构](../architecture/04-operations-testing.md)
- [后台任务契约](../architecture/contracts/05-background-tasks.md)
- [交换与维护模块](../architecture/modules/10-exchange-analytics-maintenance.md)
- [实施总清单](../planning/implementation-todolist.md)

后续交付只能在本入口下补充可执行且已验证的部署、备份和恢复步骤，不能用建议命令或模拟成功伪装真实生产动作已经运行。
