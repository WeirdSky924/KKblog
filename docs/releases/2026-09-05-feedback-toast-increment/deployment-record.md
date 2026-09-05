# 2026-09-05 正式增量部署记录

状态：已完成。

## 候选与切换

- 远端 `main` 最终提交：`e0c3bf1e62290b408e34f01e850c1ea81e2be9d8`。
- 关键补充提交：`c746c5b` 注册学习管理事件通知路由；`e0c3bf1` 修复工作机会默认筛选超长重定向。
- 应用镜像：`kaj-blog-web:e0c3bf1e6229`。
- 应用镜像摘要：`sha256:0899d493f05c6a974d99ce41b164bb1635068b62a658aba42f3cf6f03098803`。
- 旧应用镜像：`kaj-blog-web:82df3ccf689a`，仍保留用于应用级回退。
- Web、Worker、Beat 切换后均使用同一镜像摘要，重启计数为 0。

## 备份与数据库

- PostgreSQL 备份：`var/production/backups/pre-feedback-toast-20260905T024918Z.dump`。
- PostgreSQL 备份 SHA-256：`ff4f610400a2ac0bc8026b0849b58a84ed6294ae92e5667394b97394f181ce3a`。
- 媒体备份：`var/production/backups/pre-feedback-toast-20260905T024918Z-media.tar.gz`。
- 媒体备份 SHA-256：`03688acff0db6ce3ff402f5c79320ec6c7e4e5a54840b40609cce74ed07d912d`。
- 两份备份权限均为 `0600`；数据库 dump 可由 `pg_restore --list` 解析，媒体归档读回 346 个文件。
- 候选 `check --deploy`、`makemigrations --check --dry-run` 和 `migrate --plan` 均通过；本轮无待执行 migration，未运行实际 migration。
- 正式数据库和媒体目录原位保留，没有复制 Labs 数据或清理业务数据。

## 状态修复与通知

- 招聘租约恢复任务：`opportunity-recovery:0:0:0`。
- 恢复后过期 TaskRun 租约：`0`；活动 `OpportunityCheckRun`：`0`；运行中来源：`0`。
- 维护前 Outbox 待发布：`3`，其中学习文档管理事件 `1`、题库管理事件 `2`。
- 候选 Worker 发布后 3 条事件均为 `published`，租约为 `0`；对应通知消费者均为 `processed`，通知去重未产生重复记录。
- 当前待发布 Outbox：`0`。历史终态失败 TaskRun 保留为审计记录，没有直接删除或伪造成功。

## 线上验证

- Nginx 维护标记已关闭，公网 `/health/live`：`200`，`/health/ready`：`200`。
- 首页：`200`；登录页：`200`；匿名通知、知识文档、答题入口按权限返回登录跳转；匿名管理入口返回预期 `403`。
- 工作机会入口 `/opportunities/` 返回短重定向 `302`，目标 `/opportunities/?view=jobs&defaults=1` 返回 `200`。
- 修复前曾因默认筛选 ID 全量进入 `Location` 触发 Nginx `upstream sent too big header`；修复后无参数入口不再生成超长响应头。
- 新静态 CSS、JS 资源均可通过正式域名返回 `200`；当前 Web/Worker/Beat 均健康运行。
- Beat 已恢复周期发布 Outbox、招聘租约恢复和待处理检查任务；读回队列为空，没有新增 `core.outbox_transport_failed.v1`。

## 回退边界

- 旧镜像、数据库备份、媒体备份及切换前运行配置副本均保留。
- 本轮无 schema 变更，应用异常时只回退 Web、Worker、Beat 镜像，不执行反向 migration。
- 本轮未启动招聘全量抓取，不迁移或清理岗位、题库、文章、账户和通知历史。
