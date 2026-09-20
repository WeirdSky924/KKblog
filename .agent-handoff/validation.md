# Validation History

| Date | Command/Check | Result | Notes |
| --- | --- | --- | --- |
| 2026-09-16 | `python3 /root/.codex/skills/agent-handoff/scripts/bootstrap_handoff.py --repo /home/code/personal-blog --platform codex --layout multi --session-prompts` | passed | 创建多文档 handoff、会话提示词和 AGENTS 标记块；未创建 Claude 项目规则。 |
| 2026-09-16 | `git status`, `git worktree list`, `git log`, `git rev-list HEAD...origin/main` | passed | 主工作区 `e5adc20`，远端 `0b700d4`，落后 21；Labs `0b700d4` detached；正式快照 `1f9d47c` detached。 |
| 2026-09-16 | `systemctl show kaj-labs*.service` | passed | Labs web/worker/beat/outbox 均为 `inactive/dead`；没有为 handoff 启动服务。 |
| 2026-09-16 | `docker ps --filter label=com.docker.compose.project=kaj-production` | passed | 正式 Web/Worker/Beat 及依赖容器保持运行；未重启或修改生产容器。 |
| 2026-09-16 | `curl https://kajspace.cn/health/live` / `health/ready` | passed | 正式环境读回均为 HTTP 200；仅做只读健康检查。 |
| 2026-09-16 | `file -bi`, `rg '[[:blank:]]+$'`, `git diff --check`（handoff 路径） | passed | 9 个 handoff 文本文件均为 UTF-8/ASCII，无尾随空白；AGENTS 仅新增标记协议块。 |
| 2026-09-16 | handoff 路径/索引/ignore 复核 | passed | `AGENT_HANDOFF.md` 链接的 8 个状态文件均存在、非空且未被忽略；随后由 Labs 提交 `3c34606` 纳入远端 `main`。 |
| 2026-09-17 | `git fetch origin`、远端提交读回 | passed | 本轮 handoff 任务分支均已推送、fast-forward 集成并删除；Labs 保留在集成后的 detached 快照，具体提交以当前读回为准。 |
| 2026-09-16 | pytest/Ruff/build/Playwright/P0 性能测试 | not run | 本轮只生成交接文件；不把历史验证或生产运行状态冒充本轮测试结果。 |
| 2026-09-15 | 性能文档提交/远端读回 | passed | Labs 提交 `0b700d4`，远端 `origin/main` 包含该提交，临时任务分支已删除。 |
| 2026-09-15 | 生产知识审核 capability 只读诊断 | passed | profile/Endpoint/检查版本和最近审核失败状态读回，未读取 API Key、正文或个人数据。 |
| 2026-09-20 | `/root/.local/bin/uv run pytest apps/opportunities/tests/test_opp001.py -q --reuse-db`（隔离 P12 PostgreSQL/Redis/Mailpit） | passed | `9 passed in 56.13s`；首次无隔离变量运行错误，SQLite 不支持项目 PostgreSQL 专用迁移 SQL，未作为产品结果。 |
| 2026-09-20 | 性能 RED：`test_public_query_uses_one_filter_option_query_and_no_n_plus_one` | passed as RED | 优化前筛选 owner 查询为 `5` 条，断言目标 `3` 条，准确复现重复筛选选项查询。 |
| 2026-09-20 | 优化前隔离性能探针（临时文件，已删除） | observed | 默认/搜索/筛选/分页完整页分别为 `22/17/17/17` 条 SQL、约 `175/55/35/31ms` SQL 总时长；根模板约 `322/55/64/73ms`；响应约 `70.4/70.4/70.8/42.6KB`。正式公网未压缩读回为 `419230/394019/419608B`，gzip 下载约 `61821/60207/60638B`。 |
| 2026-09-20 | `/root/.local/bin/uv run pytest apps/opportunities/tests/test_public_performance.py -q --reuse-db`（临时回归文件，已清理） | passed | `6 passed in 3.99s`；覆盖 4 条匿名岗位路径、筛选/分页固定 SQL 数量、无 N+1 和 HTMX 摘要跳过。 |
| 2026-09-20 | `/root/.local/bin/uv run pytest apps/opportunities/tests/test_public_performance.py apps/opportunities/tests/test_opp001.py -q --reuse-db` | passed | `15 passed in 6.78s`；优化后岗位聚焦回归。 |
| 2026-09-20 | P0 隔离性能探针（临时文件，已删除） | passed | 优化后四路径均 `200`；SQL `17→14`，岗位 owner 查询固定 `3` 条；隔离响应 `42.6–70.8 KB`，根模板约 `33–204ms`。 |
| 2026-09-20 | `ruff check`、`ruff format --check`、`git diff --check`、`python manage.py check` | passed | 目标 3 个代码/测试文件；Django `0 issues`。 |
| 2026-09-20 | 正式公网岗位只读传输读回 | observed | 默认列表/关键词/分页均 `200`；未压缩 `394–420 KB`，gzip 后 `60–62 KB`，`private, no-store`；未执行压测或生产写入。 |
| 2026-09-20 | Labs 定向同步与读回 | partial | 仅同步 `views.py`、`queries/public.py`、`test_public_performance.py` 并 `cmp` 成功；`kaj-labs.service=inactive/dead`，Labs `/health/live=502`，未启动/重启。 |
| 2026-09-20 | 最终轻量复核：目标 Ruff/format、`git diff --check`、临时测试文件清理、`git rev-list HEAD...origin/main`、`systemctl show kaj-labs.service` | passed/partial | 代码静态检查和差异检查退出 `0`；主工作区 `a06a94f` 与远端 `0/0`；两处临时测试文件均已清理；Labs 仍 `inactive/dead`。 |
| 2026-09-20 | 正式候选构建与预检 | passed | `docker build` 退出 `0`；候选 image `sha256:26caccd5272c9173252504d578846f1e21287700c9981a6b2814749fb7c0aaf8`；`check --deploy`、`makemigrations --check --dry-run`、`migrate --plan` 均退出 `0`，无待执行 migration。 |
| 2026-09-20 | 正式发布前备份 | passed | PostgreSQL dump `176670834` 字节、TOC `1043`；媒体归档 `7024193` 字节、成员 `410`；Compose 快照 `6413` 字节；三者权限均 `0600`，摘要见正式 deployment record。 |
| 2026-09-20 | 正式应用切换与只读 smoke | passed | Web/Worker/Beat 顺序切换到 `42adeb4ceb74`，healthy/running、RestartCount 0；live/ready、默认/搜索/筛选/分页和 JS/CSS 均 HTTP 200；未执行 migration、招聘采集、Provider/AGENT 或状态补偿。 |

## Validation Guidelines

- Record commands/checks that were run.
- Record failed checks with concise cause and next action.
- Record checks that were intentionally not run as `not run`, with the reason.
- Do not paste long logs; summarize and reference files when needed.
