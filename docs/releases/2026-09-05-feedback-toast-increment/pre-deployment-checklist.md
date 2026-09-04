# 2026-09-05 正式增量更新前检查清单

状态：待正式部署回合逐项勾选；未授权生产写操作。

## Git 与候选

- [ ] 已重新读取远端默认分支和候选完整 SHA，候选是远端 `main` 的后代且无意外 merge。
- [ ] 暂存差异只包含本次 Toast/反馈计数修复和本目录文档。
- [ ] 差异不含凭据、`.env`、`.venv`、`var/`、媒体、日志、缓存、浏览器产物或临时测试文件。
- [ ] 任务分支已推送，远端 `main` fast-forward 读回与预期提交一致。

## 质量与构建

- [ ] `uv run ruff check .` 退出 0。
- [ ] `uv run ruff format --check .` 退出 0。
- [ ] `uv run python manage.py check` 退出 0。
- [ ] `uv run python manage.py makemigrations --check --dry-run` 无模型漂移。
- [ ] Toast 聚焦回归通过，覆盖真实计数、非法计数、缺失统计、批量总数一致性和 HTMX 标记消费。
- [ ] `npm run build` 退出 0，候选镜像能读取生成的 CSS/JS/字体。

## 正式只读基线

- [ ] 已记录 Web/Worker/Beat/Caddy/数据库/Redis 的镜像、工作目录、RestartCount、健康状态和 migration leaf。
- [ ] 已记录生产 Outbox、TaskRun、OpportunityCheckRun 关键状态计数及 `core.outbox_transport_failed.v1` 最近失败时间，不在本清单中暴露正文或凭据。
- [ ] `migrate --plan` 确认无待执行 migration；若有意外 migration，停止并重新评估。

## 状态修复与 Outbox

- [ ] 已完成只读快照和备份门禁，备份可读且 SHA-256/权限已记录。
- [ ] 已运行有界招聘租约恢复，过期租约为 0，无运行中的孤儿 TaskRun 或活动领域运行。
- [ ] 已确认每日 18:00 调度不会复用失效活动运行，恢复入口只产生预期一次派发。
- [ ] 已确认 Outbox transport 配置、SMTP/通知依赖和数据库连接正常。
- [ ] 已通过现有发布入口重试一小批失败 Outbox，读回 `published`/稳定失败结果；没有直接修改状态或重复发送。

## 应用切换与回退

- [ ] 候选 Web/Worker/Beat 使用同一不可变 SHA/digest。
- [ ] `collectstatic --noinput` 成功，未使用 `--clear`。
- [ ] `/health/live`、`/health/ready` 和主要页面/媒体读回通过。
- [ ] 整页与 HTMX Toast 动态数字正确，缺失统计显示不可用提示。
- [ ] 旧镜像、数据库备份、媒体备份和回退配置仍保留。
