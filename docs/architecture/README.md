# Kaj的小房间架构设计总览

状态：需求与施工级架构设计已完成；原型作为视觉基线，路由/身份/状态以 `docs/prototype/page-state-matrix.md` 补齐。准确的实施阶段、任务状态与验收证据统一见 `docs/planning/implementation-todolist.md`，本架构入口不维护第二份进度账。

需求真值：`docs/planning/requirements-interview.md`。前端基线：`docs/prototype/page-state-matrix.md`、`docs/prototype/index.html` 与 `docs/prototype/README.md`。历史决策冲突先看 `reference/01-requirements-resolution.md`。

## 目标与范围

本架构服务于可长期维护的私人博客。它把认证、私密内容、不可变版本、评论审核、数据交换和异步任务放在可独立测试的稳定领域内；Django 页面层只承担 HTTP、表单、模板和局部交互编排。

产品主体仍是同源 Web 应用，不提供移动 App API、第三方登录、RSS 或社交平台直发。唯一外部接口例外是默认关闭的匿名题库只读 API；它使用独立 `/api/v1/question-banks` transport、精确 CORS 白名单和 fail-closed 限流，不把内部 HTMX 端点升级为公共合同。生产环境按版本化增量发布；Git 提交、推送、后续部署、迁移和服务重启仍需当前任务授权。已完成发布的运行 revision 见对应发布执行记录。

## 运行时

```text
Browser
  -> Host Nginx            正式公网入口与维护门禁
    -> Caddy                下游路由、静态资源与受控媒体交付
      -> Django / Gunicorn
          -> PostgreSQL       业务事实、正文、版本、权限、任务状态
          -> Redis            可丢失验证码、限流、冷却、公开缓存与任务 broker
          -> media filesystem 受控图片与导出包
          -> Outbox           提交后跨领域副作用
          -> Provider Gateway 受限调用管理员配置的模型 Endpoint
          -> Umami            管理员入口使用的数据分析服务

Celery Beat -> Redis broker -> Celery Worker -> 领域 service -> PostgreSQL
```

当前生产部署由宿主 Nginx 接收公网流量；2026-10-11 读回时 Caddy 位于 Nginx 后并使用下游配置，正式 TLS 由宿主入口处理。仓库 Compose 定义 `web`、`postgres`、`redis`、`worker`、`beat`、`caddy`、`umami`、`mailpit` 等服务；不同 profile 的端口和邮件配置以对应 Compose 与运行配置为准，不能把本地 Mailpit 当作生产邮件服务。

## 稳定所有权

| 类型 | 模块 | 责任 |
| --- | --- | --- |
| 领域事实 | accounts、content、media、comments、moderation、notifications、navigation、operations、exchange、analytics、opportunities、`apps/agents`、`apps/learning` | 唯一模型与写服务；agents 独占 Endpoint/Prompt/调用与 token ledger，learning 独占知识文档、题库、答题和个人学习数据 |
| 用户流编排 | discovery、authoring、administration | 页面/query 组合，不建立平行业务事实 |
| 技术基础 | core、config、docker | 错误、时间、事件协议、运行入口 |

## 核心原则

1. 每项稳定能力只有一个所有者；禁止第二套权限、媒体、通知、缓存、审计或重试体系。
2. View 调用 query/service；service 执行授权、事务、锁、审计和 outbox；task 只重入 service。
3. PostgreSQL 是唯一业务事实；文件系统只保存媒体/归档；Redis 丢失不能破坏正确性。
4. ArticleRevision 不可变，working/published/scheduled 指针分离；编辑和恢复不覆盖线上版本。
5. 发布、软删除、管理员隐藏和作者禁用是正交状态，恢复时逐层重算。
6. 私密内容和管理员例外由服务端策略裁决；前端 capability 只用于显示。
7. 外部文件、邮件与任务使用 outbox/幂等/补偿；不能假装跨存储单事务。
8. 管理员写操作永久审计；错误永久脱敏保存；普通用户只见通用提示和 trace code。
9. 文件按职责拆分；接近 800 行复核，超过 1,200 行新增行为前默认拆分。
10. 完成声明必须有当前的测试、数据读回、浏览器或运维证据。

## 文档地图

| 层次 | 文档 | 回答的问题 |
| --- | --- | --- |
| 总纲 | `01-system-directory.md` 到 `04-operations-testing.md` | 系统边界、视觉和运维原则 |
| 学习 | `05-architecture-study-guide.md` | 如何按架构师方式阅读和练习 |
| 模块 | `modules/` | 各交付模块的职责摘要，包括招聘、AGENT 运行时与知识学习 |
| 数据 | `data/` | 聚合、字段、约束、索引、存储和生命周期 |
| 流程 | `flows/` | 账户、文章、评论、导入导出状态与时序 |
| 契约 | `contracts/` | 服务、权限、页面、事件、错误和任务接口 |
| 决策 | `adr/` | 为什么采用当前架构，以及接受什么代价 |
| 交付 | `delivery/` | 实施顺序、验证矩阵和代码评审门禁 |
| 参考 | `reference/` | 冲突消歧和术语 |

## 推荐入口

- 想学习架构：先读 `05-architecture-study-guide.md`，再按其中五遍路线阅读。
- 想实现一个功能：从 `delivery/01-implementation-roadmap.md` 选切片，沿页面 → 权限 → service → 状态 → 数据 → task → 验收追踪。
- 想评审设计：先看 ADR 和 owner，再用 `delivery/03-code-review-checklist.md`。
- 想确认产品口径：先看需求真值；存在历史冲突时看 `reference/01-requirements-resolution.md`。
- 想实现页面：先看 `contracts/03-frontend-contract-map.md` 和 `docs/prototype/page-state-matrix.md`，再看原型截图；不要把原型内存假状态当作业务契约。

## 实施门禁

任何模块开始前必须确认：需求来源、唯一所有者、入口身份、服务/query、事务与锁、持久化约束、事件/任务、错误状态、测试层次和原型页面。架构文档完成不等于产品已实现；P0-P12 任务验收状态见实施清单，生产 migration、运行镜像、备份和健康读回等实际状态见带日期的发布执行记录。2026-10-11 的发布记录证明完成了该轮生产更新，但不代表完整恢复演练或 P0 负载金丝雀已通过。
