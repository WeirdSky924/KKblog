# 测试环境与固定命令

项目只有一套 pytest、Ruff 和 Playwright 入口。测试数据不得连接生产或共享服务，也不得写入项目 `var/`。

## 当前阶段 Labs 默认同步

当前优化阶段把 Labs 作为每个已完成修改切片的默认测试交付目标。聚焦验证通过后，Agent 应自动完成 Labs 同步和读回，不等待用户再次说“更新到 Labs”；半成品、仍在 RED 的代码或猜测性修复不得同步。

同步前必须运行 `systemctl show kaj-labs.service -p WorkingDirectory -p ActiveState -p SubState` 读回真实目标，不使用记忆中的路径。目标目录必须是本项目的非生产 Labs worktree，不得是默认分支工作树、生产目录或其他任务 worktree。

截至 `2026-08-07`，Labs 由宿主机 `kaj-labs.service` 运行，`WorkingDirectory` 是 `/home/code/.codex-worktrees/personal-blog/labs-test-environment`，公网入口是 `https://labs.kajspace.cn`。因此当前 worktree 内的 Python、模板和已生成静态文件直接供 Labs 读取，无需再次复制；Django 源码和模板依赖开发服务器热重载，前端源码必须先按资源门禁运行受影响的 `npm run build:*` 生成 `static/dist/` 产物。

若以后服务目标与当前开发 worktree 不同，只允许按本任务已完成的运行时文件清单单向同步；不得复制或删除 `.git`、`.env`、`.venv`、`var/`、数据库、媒体、备份、日志、缓存、测试产物、`node_modules` 或无关改动，也不得使用会清空目标的宽泛同步命令。

每次同步后的最小读回包括：

1. `kaj-labs.service` 仍为 `active/running`，且工作目录未漂移。
2. `https://labs.kajspace.cn/health/live` 返回 `200`；涉及数据库或缓存时追加 readiness 或目标只读请求。
3. 前端产物的公网 SHA-256 与开发 worktree 的 `static/dist/` 文件一致；后端或模板变更检查一个直接受影响页面或安全的代表性用户流。
4. 记录同步范围、构建命令、HTTP 状态、文件哈希、未验证的登录态或数据态以及停止条件。

Labs 默认同步是本机非生产测试环境更新，不等于生产发布。它不授权服务/容器重启、镜像构建或替换、migration、数据修复、真实邮件、备份、Git 写操作或生产变更；这些动作需要各自规则要求的明确授权。热重载或 smoke 失败时停止并报告，不自动重启服务、重建容器、修改共享数据或回退用户工作。

## 按改动风险控制验证

| 改动范围 | 默认验证上限 |
| --- | --- |
| 复用现有组件的提示、文案、图标或局部样式 | 目标静态/构建检查 + 一个代表性成功路径 + Labs 读回 |
| 新的局部布局或输入交互，存在明确窄屏风险 | 目标检查 + 一个桌面和一个手机路径 |
| 权限、持久化、迁移、跨模块契约或共享基础交互 | 聚焦 RED/GREEN、相关数据读回及受影响用户流 |

轻量任务先做最小完整实现，不主动增加与请求无关的抽象或状态策略，也不得因为“可能还有问题”逐步膨胀验证。用户报告和明确调用链可以作为行为缺失证据；复用组件已有的主题、响应式、键盘和可访问性验证不机械重跑。代表性成功路径通过、相关控制台/HTTP 无错误且 Labs 读回成功后即达到停止条件。

轻量任务以 10 分钟为进度提醒线，不是质量豁免。超过提醒线时必须说明是实现问题还是环境问题，并删除与请求无直接关系的验证项。测试服务或身份状态等环境故障最多恢复一次；第二次出现时停止切换环境，保留已完成证据并报告未验证项。连续保存、自动消失、悬停暂停、手动关闭、失败不误报等组合矩阵，只有需求明确包含或实现直接修改相应状态机时才执行。

## 后端与基础设施

运行完整测试前，提供以下隔离值：

```text
KAJ_TEST_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:<port>/kaj_test_<name>
KAJ_TEST_REDIS_URL=redis://127.0.0.1:<port>/<1..15>
KAJ_TEST_MAILPIT_SMTP_URL=smtp://127.0.0.1:<port>
KAJ_TEST_MAILPIT_API_URL=http://127.0.0.1:<port>
KAJ_TEST_UMAMI_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:<port>/kaj_test_<name>_umami
```

前四项是完整 pytest 的固定依赖；`KAJ_TEST_UMAMI_DATABASE_URL` 只用于 Umami schema/保留集成测试。解析器拒绝非 loopback、默认 Redis DB 0、数据库名/用户不匹配、URL 凭据和 query。pytest 为 Django 数据库建立 `test_kaj_test_*`，媒体 fixture 使用 pytest `/tmp` 并自动清理；Umami 集成库由测试调用方独立创建和定向删除。

固定命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`scripts/test` 先核对四项隔离环境，再执行同一 `uv run pytest`；它不提供 SQLite、mock 或共享服务 fallback。

## 浏览器

固定命令：

```bash
npx playwright test
```

测试 runner 启动本地 Django fixture server；真实浏览器动作统一经 `/usr/local/bin/blog-playwright-cli`，由 `blog-browser` 用户运行。禁止 root Chrome 和 `--no-sandbox`。

Playwright 固定 visitor、user、author、admin 四个 project。账户功能建立后，三种登录身份从以下环境变量读取 storage state：

```text
KAJ_E2E_USER_STATE
KAJ_E2E_AUTHOR_STATE
KAJ_E2E_ADMIN_STATE
```

状态文件必须位于 `/tmp`、权限为 `0600`，不得写入仓库。账户功能完成前，基础错误流只执行 visitor；已登录项目明确跳过，不能把空 state 当真实身份。
