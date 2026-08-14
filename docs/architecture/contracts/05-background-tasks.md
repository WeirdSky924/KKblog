# 后台任务、幂等、并发与调度契约

Celery 任务是薄入口：解析稳定 ID，建立 trace，调用可重入应用服务，记录 `TaskRun`。任务函数不得直接拼 ORM 事务、发送未审计通知或操作任意磁盘路径。

## 统一任务协议

```text
task(payload_id, idempotency_key)
  -> TaskRun.start_or_resume
  -> application_service.execute
  -> TaskRun.succeed(result_ref)
  -> retry on declared transient errors (max 3, increasing delay)
  -> on final failure: RuntimeError + admin in-site notification + alert email when operational
```

建议退避为 1 分钟、5 分钟、30 分钟并加随机抖动；第三次失败后终止。产品不提供网页手动重试按钮。修复 BUG 后通过新业务动作或运维命令生成新的幂等键，不复用失败执行伪装成成功。

主动安全取消是独立终态：领域运行写 `CANCELLED` 后抛出受控 `TaskCancelled`，通用 TaskRun 同步写 `cancelled`、清租约并保留结果引用，不进入重试或 `task.final_failed.v1`。

## 任务目录

| 任务 | 调度/触发 | 幂等键 | 并发控制 | 成功条件 |
| --- | --- | --- | --- | --- |
| `publish_due_comments` | 每分钟扫描 | `comment:{id}:visible` | 条件更新 + skip locked | 状态 visible 或已删除 |
| `publish_scheduled_articles` | 每分钟扫描 | `article:{id}:schedule:{revision}` | 锁 Article + 条件状态 | 指定修订已发布或排期已取消 |
| `purge_deleted_articles` | 每小时 | `article:{id}:purge:{deadline}` | 小批量 skip locked | DB 聚合删除且媒体均待删/已删 |
| `delete_pending_media` | 每分钟/事件 | `asset:{id}:delete` | asset 条件状态 | 文件不存在且记录 deleted |
| `cleanup_staged_media` | 每小时 | `asset:{id}:staged-expiry` | 条件领取 | 无绑定过期资产已清理 |
| `process_import_job` | 作者确认 | `import:{job}:{preview_version}` | Job 状态锁；逐 Item 幂等 | 所有选中项有终态结果 |
| `build_export` | 管理员请求 | `export:{job}` | DB 全局 running 唯一 | ZIP 原子改名且 job completed |
| `expire_exports` | 每小时 | `export:{job}:expire` | 条件状态 | ZIP 不存在且 job expired |
| `weekly_backup` | `Asia/Shanghai` 每周一 03:00（`0 3 * * 1`） | `backup:{week-id}` | 全局 backup lease | DB/媒体命令成功并原子归档 |
| `expire_backups` | 每日 | `backup:{id}:expire` | 条件领取 | 30 天到期包删除 |
| `check_capacity` | 每 5 分钟 | `capacity:{sample-time}` | 单例周期任务 | 新采样与门禁状态已写 |
| `check_service_health` | 每分钟 | `health:{service}:{window}` | 指纹聚合 | 状态/持续故障记录更新 |
| `send_outbox_events` | 高频轮询 | `outbox:{event}:{consumer}` | skip locked + consumer 去重 | 每个消费者确认 |
| `expire_umami_data` | 每日 | `umami-retention:{date}` | 单例 | 一个月前数据删除完成 |
| `schedule_daily_check` | 上海时间每日 18:00 | `opportunity-schedule:{utc-date}` | 活动运行数据库唯一 | 创建或复用一次全量检查 |
| `dispatch_pending_check_runs` | 每分钟 | `opportunity-dispatch:{utc-minute}` | 有界扫描 + 运行/TaskRun 双重幂等 | 所有选中 `PENDING` 运行已派发 |
| `run_check` | 手动/定时运行创建后 | `opportunity-run:{run-id}` | 全站活动运行唯一 + TaskRun 租约 | 来源串行完成、部分完成或安全取消 |
| `cleanup_check_history` | 上海时间每日 18:30 | `opportunity-cleanup:{utc-date}` | 每日单例 + 小批量删除 | 到期检查/快照已按上限清理 |
| `aggregate_notifications` | 事件触发/周期补偿 | 业务 dedupe key | DB 唯一键 | 通知/receipt 存在 |

## 定时发布判定

任务锁定 Article 后再次检查：作者仍启用、文章未删除、无管理员隐藏阻塞、state 仍 scheduled、scheduled revision 未变化、时间已到、修订仍满足正文/媒体/分类约束。任一业务条件不满足时转为明确取消/草稿或记录跳过原因；不能发布“任务入队时看起来有效”的过期快照。

作者禁用会同步取消排期并转草稿，任务再次执行应读到已取消并成功幂等退出。

## 评论公开扫描

批量查询 `state=BUFFERED AND visible_at<=now`，每批固定上限并 `FOR UPDATE SKIP LOCKED`。对每条使用条件更新；评论区后来关闭不影响已提交评论按时公开，只有删除状态阻止公开。这个规则与“关闭只阻止继续发评论”一致。

## 文章物理删除 Saga

物理删除跨 PostgreSQL 与文件系统，不可能用单一 ACID 事务：

1. 锁文章并确认 purge deadline。
2. 收集媒体资产，标 `DELETE_PENDING`，保留审计目标快照。
3. 删除文章聚合和评论聚合，提交事务。
4. 媒体任务逐个删除文件；不存在视为成功。
5. 全部完成后 TaskRun 成功；部分失败继续重试。

数据库删除后文件短暂残留不可被授权读取，因为媒体绑定已删除、asset 非 ACTIVE。相反顺序会导致不可恢复断图，因此禁止。

## 导出取消竞态

Worker 写 ZIP 到 `.part` 文件并周期检查 Job 状态。管理员取消使用行锁把 `RUNNING -> CANCEL_REQUESTED`。Worker 检测后关闭句柄、删除 `.part`、写 `CANCELLED`。若 Worker 已在同一锁内完成原子改名，则取消请求返回“已完成，无法取消”，不删除有效完成包。

## Lease 与异常释放

全局备份、导出等租约必须保存在 PostgreSQL 状态/约束中，不能只用 Redis 锁。Worker 崩溃后由 `heartbeat_at + lease_expires_at` 判断失联；恢复服务将失联执行标为失败并按任务政策处理。Redis 分布式锁只能降低争抢，不能成为正确性来源。

## 告警去重

最终任务失败、健康故障、磁盘低空间和备份失败都计算稳定 fingerprint。站内通知按故障实例创建；邮件用 Redis/数据库记录一小时窗口，同一持续故障最多每小时一封。不发送恢复邮件，恢复事件仍写 TaskRun/运维状态。

## Beat 可靠性

- 仅运行一个 Beat 实例，schedule 文件不作为业务事实。
- 每个周期任务扫描“所有到期且未完成”的数据库记录，因此漏一次 tick 后可以补偿。
- 不依赖 ETA 消息保存 7 天删除或很远的定时发布；数据库到期时间才是真值。
- 所有周期以 UTC 比较，上海 00:00 只用于每日验证码计数键和通知聚合日期。

## 任务测试

每项任务至少验证：第一次成功、重复执行、并发两个 Worker、前两次失败第三次成功、三次最终失败、Worker 在数据库提交前/后崩溃、外部文件已不存在、业务对象中途变更、最终通知只产生一次。

使用真实测试 PostgreSQL 与临时媒体目录读回；Celery eager 只验证局部服务，不足以证明 broker/worker 行为。容器验收至少运行一个真实 Worker 烟测任务。
