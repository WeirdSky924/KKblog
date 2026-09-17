# Handoff Archive

This file stores compressed old history that should not be part of normal startup.

## 2026-07 to 2026-09 Project History (compressed)

- P0-P12 的 102 项基础实施任务已在历史实施清单中标记完成；其证据主要来自隔离 PostgreSQL/Redis/Mailpit、真实浏览器、worker、缓存、文件 Saga 和部署沙箱。完成状态不等于当前生产部署或真实生产数据已验证。
- 近期功能簇包括：知识文档审核与题库生成、AGENT/Endpoint/Prompt/Schema harness、找工作来源/适配器/分页筛选、文章导入与 LaTeX、通知/反馈 Toast、文章公开主页和划词解释工具。
- 生产发布历史已通过多个 Labs 候选提交进入远端 `main`；最近性能测试文档提交为 `0b700d4`。当前主工作区未跟随远端同步，详见 `snapshot.md` 与 `risks.md`。
- 近期重要运行事故经验：PostgreSQL 断连可能留下过期 TaskRun/租约并阻塞每日招聘运行；恢复必须协调 TaskRun、业务运行、来源状态并重新派发，不能只改状态。
- 近期 AGENT 经验：Endpoint 修改会使旧 schema capability check 失效；`SCHEMA_SUPPORTED` 必须按 profile schema 和 Endpoint row version 匹配，不能用其他 AGENT 的成功检查替代。
- 近期通知经验：业务事件先经 Outbox，Consumer 幂等创建 Notification/Receipt；Toast 只做瞬时操作反馈，不能代替持久通知。

## Archive Guidelines

- Do not use this file for current state.
- Move stale but potentially useful history here as concise summaries.
- Keep pointers to relevant decisions, validation entries, or source files.
