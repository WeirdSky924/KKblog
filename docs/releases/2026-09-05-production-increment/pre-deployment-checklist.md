# 2026-09-05 合并正式增量更新检查清单

状态：已完成；详细证据见同目录 `deployment-record.md`。

## 候选与质量

- [x] 远端 `main` 已核验，候选从其祖先创建并 fast-forward 集成。
- [x] Toast/反馈计数阶段与 Labs 全量增量阶段已逐路径核对。
- [x] 无 `.env`、`.venv`、`var/`、媒体、日志、缓存、凭据或秘密进入提交。
- [x] Ruff、Django check、模型漂移检查、契约回归和 Docker 构建通过。
- [x] 完整 pytest 的资源性中止已记录，临时数据库、Redis 和 Mailpit 已清理。

## 正式窗口

- [x] 生产 Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami 状态和旧镜像已记录。
- [x] 正式 `migrate --plan` 无待执行迁移，未运行 migration。
- [x] 新鲜 PostgreSQL dump、媒体归档和 Compose 配置副本已创建并校验 SHA-256、权限和可读性。
- [x] 维护页已从公网读回 503；应用服务以候选镜像重新创建。
- [x] `collectstatic --noinput` 成功，未使用 `--clear`。
- [x] Worker 健康后执行招聘租约恢复和 Outbox 发布，Beat 最后恢复周期调度。
- [x] 维护页已关闭，Web/Worker/Beat 使用同一候选镜像且健康。

## 用户流与回退

- [x] 健康端点、首页、登录、作者页、文章页、静态、头像、正文图片和封面读回通过。
- [x] 匿名受保护入口返回预期登录跳转；分析采集路径不产生重复 `/analytics/analytics/collect`。
- [x] 旧镜像、备份和回退配置仍保留；未复制 Labs 数据、未手动抓取招聘来源。
