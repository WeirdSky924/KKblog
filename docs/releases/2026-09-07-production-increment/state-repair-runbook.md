# 正式状态修正记录与回退边界

本轮部署前已只读核对状态：运行中/等待重试 TaskRun、待发布 Outbox、处理中消费者、题库 GENERATING、Agent RUNNING、活动招聘运行和 RUNNING 来源均为 0，因此没有执行破坏性状态修正或手工标记成功。

部署后通过既有 `apps.opportunities.recover_check_leases` 入口执行一次有界恢复，结果为 `opportunity-recovery:0:0:0`；没有直接调用 adapter，也没有手动抓取招聘来源。Outbox 和运维告警补偿入口读回无待处理记录。

若后续发现新的孤儿租约，只能先记录稳定 ID/状态并使用既有恢复服务；不得宽泛 UPDATE、删除数据或强制成功。候选异常时仅回退 Web/Worker/Beat 到旧镜像，不反向迁移数据库。
