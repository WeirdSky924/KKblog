# 增量发布前检查清单

状态：待正式部署回合逐项勾选。本清单不授权生产写操作，也不表示任何项目已经在正式环境执行。

## 候选与质量

- [ ] 任务提交已从远端 `main` 的 `e5adc20` 后代创建，远端读回无意外 merge。
- [ ] 候选差异已检查，无密钥、Cookie、连接串、真实账号数据、`.env`、`var/`、媒体、日志或浏览器产物。
- [ ] 相关 pytest、Ruff、format、Django check、migration drift 和前端构建退出 0；失败项已区分为本次回归或环境限制。
- [ ] Web、Worker、Beat、Caddy 候选镜像使用同一完整 SHA，镜像摘要已记录。
- [ ] `docker/scripts/deploy --dry-run` 顺序和停止条件符合部署方案。

## 正式只读基线

- [ ] 正式 Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami 状态、镜像、RestartCount、工作目录和 migration leaf 已记录。
- [ ] live/ready、主页、文章、登录、找工作、答题、静态资源和既有媒体在变更前正常。
- [ ] 正式数据库、媒体和静态目录位于生产专用路径，Labs 数据库和媒体没有被引用。
- [ ] `migrate --plan` 已读回；无待执行项则记录跳过迁移，有待执行项则进入备份门禁。

## 备份与状态

- [ ] 有待迁移时已创建新鲜 PostgreSQL custom dump 和媒体归档，大小、权限、SHA-256、manifest 与 `pg_restore --list` 已记录。
- [ ] 维护窗口已生效，Web/Worker/Beat 写入已静默，数据库和媒体卷未替换。
- [ ] 租约恢复入口使用健康的新数据库连接执行，过期 TaskRun、来源明细和 OpportunityCheckRun 已协调。
- [ ] 活动运行、来源运行态、TaskRun 租约、终态和失败错误码不变量读回通过。

## 来源导入（仅配置）

- [ ] `config/opportunity_sources.additions-2026-08-29.all.json` dry-run 返回 109 条且适配器全部已注册。
- [ ] `--apply` 返回新增/更新计数符合预期，新增来源启用 88、停用 21，公开状态为 false、检查状态为 NEVER。
- [ ] 岗位、采集快照、审核、收藏和任务历史行数未因导入而增加或覆盖。
- [ ] 本窗口没有调用 source check、adapter collect、浏览器 collector 或手动全量采集。
- [ ] 已记录下一次 Celery 定时采集的观察项；等待定时任务，不提前触发新来源抓取。

## 应用切换与验收

- [ ] `collectstatic --noinput` 成功且未使用 `--clear`，Caddy 可读新静态指纹和既有媒体。
- [ ] Web 健康后再启动 Worker、Beat；三者健康检查、队列和日志无持续错误。
- [ ] 公开主页、文章渲染、登录、答题、工作机会、管理导航、通知中心和来源配置真实读回通过。
- [ ] 旧镜像和本次备份仍保留；失败时只回退应用，不反向迁移数据库。
- [ ] 执行记录已填写候选摘要、备份摘要、migration leaf、状态修复、来源导入和健康检查结果。
