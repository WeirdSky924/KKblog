# 2026-09-14 正式增量更新检查清单

状态：已完成；证据见 `deployment-record.md`。

## 候选与 Git

- [x] 任务分支从远端 `main` 最新基线创建。
- [x] 提交仅包含本轮源代码、模板、架构文档和本目录发布文档；测试文件、缓存、环境文件、媒体和生成目录未提交。
- [x] 任务分支已推送，远端 `main` 已 fast-forward 包含候选提交。
- [x] 候选镜像从远端 `main` 对应提交构建并记录 manifest。

## 质量与兼容

- [x] 前端构建、前端回归、Ruff、compileall 和 `git diff --check` 通过。
- [x] `check --deploy`、`makemigrations --check --dry-run`、`migrate --plan` 和 Compose 配置校验通过；迁移计划为空。
- [x] Labs 服务保持 `active/running`，live/ready 返回 200，受影响页面和静态 JS 读回通过。

## 正式窗口

- [x] 生产 PostgreSQL dump、媒体归档和 Compose 快照已新鲜创建、校验并设为 0600。
- [x] Web/Worker/Beat 停止与启动顺序符合部署方案；未执行不必要 migration。
- [x] `collectstatic --noinput` 成功且未使用 `--clear`。
- [x] 既有错误状态按有界恢复入口读回；部署时无过期租约、待发布 Outbox 或处理中消费者。

## 发布后读回

- [x] Web/Worker/Beat 使用候选镜像，Caddy/数据库/Redis/Umami/Mailpit 未被替换。
- [x] live/ready、首页、登录页、招聘页、静态 JS/CSS 和文章页面通过。
- [x] Agent、文章解释没有新增卡死状态；18:00 定时招聘检查为有效运行，未手动抓取招聘来源。
- [x] 旧镜像、备份和 Compose 快照仍保留；失败时只回退应用镜像。
