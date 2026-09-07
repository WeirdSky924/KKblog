# 2026-09-07 正式增量更新检查清单

状态：已完成；证据见 `deployment-record.md`。

## 候选与质量

- [x] 远端 `main` 已核验，候选已提交、推送并 fast-forward 集成。
- [x] 暂存内容排除 `.env`、`.venv`、`var/`、媒体、日志、缓存和一次性 `*.test.mjs`。
- [x] 目标回归、Ruff、Django check、迁移漂移和 `git diff --check` 已通过。
- [x] 候选 Web 镜像构建成功并记录不可变 manifest。

## 正式窗口

- [x] PostgreSQL dump、媒体归档和 Compose 快照已创建、校验并保留。
- [x] Beat/Worker 停止后执行两条迁移，Web/Worker/Beat 使用同一候选镜像恢复。
- [x] `collectstatic --noinput` 成功且未使用 `--clear`。
- [x] 招聘租约恢复、Outbox 和运维告警补偿入口已执行。

## 用户流与回退

- [x] live/ready、首页、登录页、CSS、JS 和生产容器健康读回通过。
- [x] 活动任务、招聘运行、Outbox 和消费者状态均无异常积压。
- [x] 旧镜像、备份和 Compose 快照仍保留；未复制 Labs 数据、未手动抓取招聘来源。
