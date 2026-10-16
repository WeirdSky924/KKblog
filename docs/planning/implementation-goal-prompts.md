# Kaj的小房间分阶段一次性 Goal 提示词索引

目标项目：blog:/home/code/personal-blog/
来源清单：[implementation-todolist.md](implementation-todolist.md)
Todo 生成基线 SHA-256：3cd9ccf9d5702ef81d4c89697683a7ff81e09653e713b62b8151b6c98afd675b

## 使用规则

1. 13 个阶段各对应 1 份一次性 Goal；当前总任务数为 102，不创建 102 个 Goal。
2. 阶段编号已经按任务依赖闭合；Goal 不得跳过未完成前置任务。
3. 每阶段启动前必须满足 docs/planning/implementation-readiness.md 的 Definition of Ready，并读取 docs/prototype/page-state-matrix.md。
4. 每个 Goal 内任何时刻只能有一个进行中的 Todo；证据写回 Todo，Goal 文件不维护第二套进度。
5. 未授权的 Git、迁移、生产服务、真实外发邮件、备份清理和不可逆操作必须停止。

## 阶段提示词

| 文件 | 阶段 | Goal 数 | 覆盖 Todo |
| --- | --- | ---: | ---: |
| [phase-00-decisions.md](implementation-goal-prompts/phase-00-decisions.md) | P0 决策与范围锁定 | 1 | 5 |
| [phase-01-foundation.md](implementation-goal-prompts/phase-01-foundation.md) | P1 项目与质量骨架 | 1 | 6 |
| [phase-02-runtime.md](implementation-goal-prompts/phase-02-runtime.md) | P2 运行时与跨域基础 | 1 | 8 |
| [phase-03-accounts.md](implementation-goal-prompts/phase-03-accounts.md) | P3 账号、安全与基础通知审计 | 1 | 12 |
| [phase-04-media.md](implementation-goal-prompts/phase-04-media.md) | P4 媒体、安全渲染与个人资料 | 1 | 8 |
| [phase-05-content.md](implementation-goal-prompts/phase-05-content.md) | P5 文章、修订、分类与发布任务 | 1 | 11 |
| [phase-06-discovery.md](implementation-goal-prompts/phase-06-discovery.md) | P6 阅读与发现 | 1 | 8 |
| [phase-07-comments-moderation.md](implementation-goal-prompts/phase-07-comments-moderation.md) | P7 评论、留言、举报与申诉 | 1 | 11 |
| [phase-08-observability.md](implementation-goal-prompts/phase-08-observability.md) | P8 通知与可观测性集成 | 1 | 6 |
| [phase-09-exchange-operations.md](implementation-goal-prompts/phase-09-exchange-operations.md) | P9 导入导出、备份与 Umami | 1 | 7 |
| [phase-10-authoring.md](implementation-goal-prompts/phase-10-authoring.md) | P10 作者工作台 | 1 | 6 |
| [phase-11-administration.md](implementation-goal-prompts/phase-11-administration.md) | P11 管理后台、导航与站点设置 | 1 | 8 |
| [phase-12-regression-delivery.md](implementation-goal-prompts/phase-12-regression-delivery.md) | P12 跨模块回归与部署准备 | 1 | 6 |

## P12 后增量 Goal

P0-P12 阶段仍维持 13 份提示词与 102 个基础 Todo。后续新增需求使用单独的 post-P12 Goal，不改变阶段历史计数。

| 文件 | 增量任务 | Goal 数 | 覆盖 Todo |
| --- | --- | ---: | ---: |
| [post-p12-iter-001-author-permission.md](implementation-goal-prompts/post-p12-iter-001-author-permission.md) | 注册管理员通知与一次性作者权限申请 | 1 | 1 |

## 完整性门禁

- 13 份文件各有且只有一个主 Goal。
- Todo ID 并集与 102 个唯一任务完全相等，无重复、无缺失。
- 前置依赖无环、无反向阶段边，所有引用 ID 存在。
- 每个 Goal 要求重读规则/来源、依赖核验、RED/GREEN、真实读回、页面状态矩阵、停止条件、授权边界和阶段回写。
