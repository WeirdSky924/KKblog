# 如何学习与使用这套架构文档

这套文档不是按文件名从头背到尾的教材。正确读法是围绕一个行为反复追问：需求是什么、谁拥有事实、状态怎么变、谁能做、失败怎么收敛、用什么证据证明。

## 第一遍：建立全局地图（约 1 小时）

按以下顺序只理解结论，不钻字段：

1. `README.md`：知道系统边界、运行时和文档分层。
2. `01-system-directory.md`：画出稳定领域 owner 与依赖方向。
3. `adr/README.md` 和六份 ADR：理解为什么没有 SPA/微服务/文件正文。
4. `reference/02-glossary.md`：查清陌生术语。

第一遍结束后，尝试不看文档回答：文章是谁拥有、管理后台是否拥有业务、Redis 丢失会不会丢文章、管理员为什么能看私人文章却不能编辑。答不出就回到对应 ADR，而不是继续往后读。

## 第二遍：沿数据生命线阅读（约 2 小时）

顺序：

1. `data/01-er-model.md`：只看关系和聚合写边界。
2. `data/02-identity-content-fields.md`：关注 Article/Revision 的三个指针。
3. `flows/02-article-state-machine.md`：把字段放回创建、发布、恢复、删除流程。
4. `data/04-indexes-constraints.md`：判断哪些规则由数据库兜底。
5. `data/05-storage-lifecycle.md`：理解数据库、Redis、文件各自保存什么。

练习：拿一篇已发布文章，模拟作者编辑但不重发、管理员隐藏、作者被禁用、7 天软删除四件事。每一步写出 `working_revision`、`published_revision`、publication state、三个遮罩是否变化。这个练习能检验你是否真的理解“状态正交”。

## 第三遍：沿一次用户请求阅读（约 2 小时）

选择“访客发表评论”或“作者发布文章”，按这条链追踪：

```text
原型/页面
  -> frontend contract
  -> authorization matrix
  -> application service
  -> state machine
  -> database constraint
  -> outbox/task/notification
  -> verification matrix
```

以“定时发布”为例：

- 页面：`contracts/03-frontend-contract-map.md` 的终稿审查。
- 权限：`contracts/02-authorization-matrix.md` 的发布/排期。
- 命令：`contracts/01-application-services.md` 的 `schedule_article`。
- 状态：`flows/02-article-state-machine.md` 的 Draft/Published → Scheduled。
- 数据：Article 的 `scheduled_revision_id` 与 `scheduled_for`。
- 任务：`contracts/05-background-tasks.md` 的二次条件检查和幂等键。
- 证据：`delivery/02-module-verification-matrix.md` 的双 Worker 场景。

如果一条链在某处断掉，这就是施工前需要补的设计缺口。

## 第四遍：学习失败思维（约 1.5 小时）

重点读：`contracts/04-events-errors.md`、`contracts/05-background-tasks.md`、`flows/04-import-export-sequences.md`。

每个流程都问五个问题：

1. 数据库提交前进程崩溃会怎样？
2. 提交后、发通知前崩溃会怎样？
3. 同一消息执行两次会怎样？
4. 两个用户/Worker 同时操作会怎样？
5. 外部文件、邮件或 Redis 不可用会怎样？

架构师的重要习惯不是只画成功路径，而是先找到不可原子完成的边界，再设计幂等、锁、outbox、补偿和可观测性。

## 第五遍：从设计进入实现

读 `delivery/01-implementation-roadmap.md`，每次只取一个可观察切片。开始编码前填写：

```text
行为：
需求来源：
唯一 owner：
入口身份与对象状态：
命令/query：
事务与锁：
持久化约束：
事件/任务/通知：
失败与用户文案：
RED 测试：
数据库读回：
Playwright 路径：
```

实现后用 `delivery/03-code-review-checklist.md` 反查。不要先按目录批量造空壳；目录只是边界的结果，能闭环一个行为比“所有 app 都有 service.py”更重要。

## 按角色的阅读路线

| 目标 | 最短路线 |
| --- | --- |
| 学产品 | requirements resolution → 页面映射 → 三个状态机 |
| 学后端 | ER → 字段 → 约束/锁 → 服务 → 任务 |
| 学权限 | 权限矩阵 → Admin ADR → 状态机 → 高风险验收 |
| 学前端 | 视觉架构 → 页面映射 → 错误契约 → Playwright 验收 |
| 学运维 | 存储生命周期 → 任务 → 交换/部署时序 → 运维验收 |
| 做代码评审 | ADR/owner → service contract → 数据约束 → review checklist |

## 架构师的工作习惯

### 1. 先找事实所有者

页面不是所有者，表也不天然是所有者。先问“这条规则由谁负责长期保持”。例如管理员页面可以禁用用户，但账户状态仍由 accounts 服务写；否则普通页面、任务和管理页会形成三套行为。

### 2. 把状态拆成正交维度

不要为了方便把所有情况塞入一个 `status`。文章的发布、软删除、管理员隐藏和作者禁用互相独立；压成一个枚举会产生组合爆炸和错误恢复。

### 3. 区分事实与投影

ArticleRevision 是事实，ArticleTag/缓存是读取投影。投影能重建、能失效；事实不能依赖投影存在。这样缓存或索引损坏不会变成正文丢失。

### 4. 把权限放在可信边界

隐藏按钮只改善体验，不能授权。任何 URL、HTMX、任务或脚本最终都要进入同一 policy/service。权限矩阵是测试输入，不是 UI 说明。

### 5. 先定义失败再写异步

只写“丢给 Celery”不是设计。必须定义幂等键、重试次数、最终失败、重复消费、取消、租约、通知和读回。

### 6. 记录代价，而不是假装完美

本地媒体适合当前单机，但阻碍多实例；本地未加密备份简单，但风险明确；SSR 降低 API 复杂度，但不适合离线 App。ADR 让未来变化有依据。

### 7. 用证据关闭问题

“代码看起来对”不等于完成。数据库约束要并发读回，权限要伪造直接请求，页面要真实点击，任务要重复/崩溃测试，部署要健康检查和回退证据。

## 推荐学习笔记格式

每读一份文档只记四列：

| 规则/决策 | 它防止的失败 | 实现位置 | 证明方式 |
| --- | --- | --- | --- |
| 发布/工作修订分离 | 编辑误覆盖线上版本 | content Article/Revision service | 已发布编辑后读者仍见旧版 |
| 邀请码行锁+唯一 | 并发注册一号多用 | accounts register service/DB | 两并发请求仅一成功 |
| Outbox | DB 成功但通知丢失 | core/operations publisher | 提交后崩溃仍补发一次 |

这种笔记会训练你把架构名词还原成风险、所有权和证据，而不是背目录。

## 每周复盘问题

- 本周是否出现同一规则在两个地方实现？
- 哪个文件增长是职责增长，哪个只是正常同职责增长？
- 是否新增了未经 ADR 说明的公共契约或存储事实？
- 哪个失败只能靠日志猜，缺少 trace/状态/读回？
- 哪项测试只断言调用发生，没有证明真实结果？
- 新需求是否让某个旧决策失效，需要新 ADR？

## 文档维护规则

- 产品改变：先追加需求决策和消歧，再更新状态/权限/契约/验收。
- 架构改变：新建 ADR 取代旧 ADR，不抹去历史理由。
- 代码与文档不一致：以最新明确需求和真实测试为证据，不能静默选一方。
- 文档链接、模型名和事件版本在实现阶段应进入静态检查。
- 每完成一个切片，回写实际命令、迁移和验收证据；设计文档不等于产品已实现。
