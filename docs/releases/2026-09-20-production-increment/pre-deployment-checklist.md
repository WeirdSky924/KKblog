# 2026-09-20 正式增量更新检查清单

状态：已完成；证据见 `deployment-record.md`。

## 候选与质量

- [x] 远端 `main` 包含候选提交，任务分支已 fast-forward 集成并清理。
- [x] 暂存/提交未包含测试文件、环境文件、`var/`、媒体、日志、缓存或原有 P0 文档。
- [x] 候选镜像构建成功，记录源码 revision 和镜像 ID。
- [x] `check --deploy`、`makemigrations --check --dry-run`、`migrate --plan` 通过；无待执行 migration。

## 正式基线与备份

- [x] 旧 Web/Worker/Beat 均为 `451bc9f`、healthy、RestartCount 0。
- [x] 变更前 live/ready 和岗位搜索均为 HTTP 200。
- [x] PostgreSQL dump、媒体归档和 Compose 快照已新鲜创建、校验并设为 `0600`。
- [x] PostgreSQL dump `pg_restore --list` 读回 1043 个 TOC 条目；媒体归档读回 410 个成员。

## 切换与验收

- [x] Beat/Worker 先停止；Web 健康后按 Web → Worker → Beat 顺序切换。
- [x] Web、Worker、Beat 均使用候选镜像且 RestartCount 为 0。
- [x] live/ready、默认岗位列表、关键词、招聘类型筛选、分页、JS/CSS 均返回 200。
- [x] 未执行生产 migration、招聘采集、Provider/AGENT 调用、状态修复或 Outbox 补偿。
