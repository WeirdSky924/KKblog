# 2026-09-02 正式增量候选执行记录

状态：候选已提交并推送，正式生产备份、迁移、状态修复、镜像替换和服务重启尚未执行。

## 候选身份

- 任务分支：`codex/labs-next-iteration`
- 候选提交：`2fee4ca32621314bf3ab201f89db3829163a5997`
- 远端默认分支：`origin/main` 已 fast-forward 至同一提交。
- 上一正式应用镜像：`kaj-blog-web:a7df26300e`，镜像 revision `a7df26300e790505df07ff9d11305f540bcae7d4`（只读读回）。
- 当前正式 Caddy 镜像：`kaj-blog-caddy:2cbead0`（只读读回）。
- 候选 Web/Worker/Beat 镜像：待正式部署窗口使用候选完整 SHA 构建并记录 digest。

## 本地/隔离验证

- `uv run ruff check .`：通过。
- 目标变更文件 `uv run ruff format --check`：通过。
- `uv run ruff format --check .`：未全通过，8 个历史基线文件需要格式化；未修改这些无关文件，正式候选需单独处理该门禁。
- `uv run python manage.py check`：通过。
- `uv run python manage.py makemigrations --check --dry-run`：通过，无模型漂移。
- `npm run build`：通过，已生成 CSS、JS、字体产物。
- 前端行为回归 `npm run test:frontend`：`6 passed`；仅有 Node 的既有模块类型提示，不影响退出码。
- 隔离 PostgreSQL/Redis/Mailpit 受影响回归：招聘恢复/架构/operations `27 passed`；阅读书签 `5 passed`。
- `git diff --cached --check`：通过；提交前未发现环境文件、数据库、媒体、日志、缓存或凭据。

## Labs 读回

- `kaj-labs.service` 工作目录：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`。
- 服务状态：`active/running`。
- `https://labs.kajspace.cn/health/live`：HTTP `200`。
- Labs 页面加载 `styles.css?v=notify-height-20260902`。
- Labs 远程 `static/dist/styles.css` SHA-256 与候选 worktree 一致：`6a0d378d637907828c90f5195721da750cc39445b10da5f843b358d9560b2acd`。
- 未登录浏览器可读回首页；通知浮窗的登录态展开未完成，原因是当前主机资源紧张导致点击后的浏览器动作超时；浏览器会话已关闭。

## 正式部署待执行

以下动作必须在另一次明确的生产部署授权回合执行并逐项读回：

1. 从远端 `main` 构建 Web、Worker、Beat 候选镜像，记录不可变 digest，并完成全量格式门禁。
2. 读取正式 `migrate --plan`；有待执行迁移时先创建并校验新鲜数据库 custom dump 与媒体归档。
3. 启用维护窗口，静默 Web/Worker/Beat 写入，执行 `content.0017` 与 `notifications.0002` 前向迁移（若 plan 确有待执行项）。
4. 启动候选 Web、Worker、Beat，运行有界 `apps.opportunities.recover_check_leases`，收口过期租约及终态 TaskRun 关联的活动孤儿运行。
5. 读回无过期租约、无运行中 TaskRun、无孤儿活动检查、失败错误码和通知去重事实完整。
6. 执行 `collectstatic --noinput`（禁止 `--clear`），验证 CSS/JS、KaTeX、头像、封面、正文图片和附件。
7. 依次验收主页、文章、作者公开页、通知中心、登录、答题、找工作公开页/收藏页和管理导航；观察每日 18:00 调度，不手动抓取新增来源。

## 明确未执行

- 未连接或修改正式数据库，未执行 migration、数据状态修复或备份。
- 未替换生产镜像，未重启或停止生产 Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami。
- 未导入或抓取招聘来源，未复制 Labs 岗位、任务历史、账号、媒体或收藏。
- 未提交 `tests/frontend/authoring-import-entry.test.mjs`；该路径匹配项目规则禁止暂存的 `*.test.*` 临时测试文件，仍保留在 Labs worktree 供本地验证。
