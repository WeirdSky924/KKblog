# I. 通知、任务与可观测性

所有者：`apps/notifications` 拥有通知/收件回执；`apps/operations` 拥有审计、运行错误、任务记录、容量/健康状态和告警。业务领域只发安全事件，不直接拼通知或日志。

## 内部目录

```text
apps/notifications/
  models/{notification,receipt}.py
  services/{delivery,read,broadcast,visibility}.py
  templates_registry/{schemas,renderers}.py
  queries/{popover,inbox,broadcast_readback}.py
apps/operations/
  models/{audit,runtime_error,task_run,capacity,backup_record}.py
  services/{audit,errors,tasks,capacity,health,alerts}.py
  redaction/{policy,schemas}.py
  queries/{audit,error,task,health}.py
  tasks/{health,capacity,cleanup,outbox}.py
```

## 通知模型

Notification 是模板化消息，Receipt 是每个接收者已读状态。最新五条进入 Header 浮层；通知页列出全部，支持逐条/全部已读。用户不能删除通知。

管理员群发固定面向所有注册用户，可查看每人已读/未读；隐藏对全体不可见且可恢复，删除对全体不可见且不提供恢复，但审计永久。个人业务通知按事件创建。

## 通知事件

标签审核、作者角色变更、举报/申诉结果、管理员文章查看/隐藏/恢复/删除、管理员直接删评论、导出他人内容、导出完成/失败、深层评论、后台任务最终失败和运维告警。

管理员查看按作者+文章+上海日期最多一条；导出他人内容按作者+上海日期最多一条；同一用户兼任评论作者/文章作者时删除通知去重。

业务通知不发邮件。验证码由 accounts/mail 发送；健康、磁盘、备份和最终任务失败额外发管理员邮箱，一小时同持续故障最多一封，不发恢复邮件。

## 审计

所有管理员状态/权限写操作与业务事务同成败，永久保存 actor、目标、动作、trace、完整 IP、safe before/after。正文/媒体只记版本 ID/asset ID，不复制大字段。只读页面不审计；管理员查看他人内容通过通知事件单独追踪。

AuditSchema 默认拒绝未知字段；密码、码、token、Cookie、连接串、`.env`、正文、原文件绝不进入审计。

## 运行错误

未预期异常生成用户可查的 trace code，脱敏堆栈/上下文永久保存。相同 fingerprint 可聚合首次/最近时间和次数。管理员按 trace/错误码/关键字/时间搜索；普通用户只见通用提示。

正文渲染性能使用 `apps.operations.services.performance` 的窄日志入口，不新建第二个正文或指标事实表。每次 content projection 记录格式、模式、schema、字节/节点/深度/表格计数、耗时、结果、稳定错误码和 trace；超过 250 ms 或被拒绝使用 warning，其余使用 info。入口拒绝自由文本和无界数值，绝不接收正文、URL、文件名、媒体 ID、对象 ID、路径或异常消息。

## TaskRun 与告警

每个 Celery 执行记录 task、业务幂等键、attempt、状态、时序和最终错误。三次递增延迟后最终失败，写 RuntimeError、站内通知；运维类再发邮件。网页只查看，不提供手动重试。

容量检查产生 NORMAL/WARN/NO_IMAGE/READ_ONLY 状态，所有写服务读取同一 policy。低于 10% 告警、5% 禁图、2% 禁全部创建，回升自动解除。

## UI

通知浮层/完整 overlay/通知页；管理员群发与读回；审计搜索/详情；错误搜索/脱敏详情；任务列表/尝试；健康/磁盘/备份状态；Umami 入口由 analytics 提供。

## 验证

事件重复不重复通知；Receipt 并发全读；群发生成全体回执；隐藏/恢复/删除；举报人 payload 不泄露；audit schema 拒绝秘密；异常各 sink 脱敏；任务三次/最终失败；邮件一小时去重；容量阈值自动限制和恢复。

施工依据：`contracts/04-events-errors.md`、`contracts/05-background-tasks.md`、`data/03-interaction-operations-fields.md`。
