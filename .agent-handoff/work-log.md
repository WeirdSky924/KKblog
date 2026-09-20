# Current Work Log

## 2026-09-17

- Objective: 按 Labs-first 规则提交并推送 handoff。
- Changed files: `AGENT_HANDOFF.md`、`AGENT_SESSION_PROMPTS.md`、`.agent-handoff/*.md`、`AGENTS.md` 的 handoff protocol。
- Result: handoff 初始内容和状态收口均由 Labs 任务分支推送并 fast-forward 到远端 `main`；临时分支已删除；Labs 保留在集成后的 detached 快照。
- Remaining risks: 主工作区仍为 `e5adc20`、落后远端 23 个提交且保留原有脏改动，未执行同步或覆盖。

## 2026-09-20

- Objective: 按 P0 `03-backend-performance.md` 定位 Kajspace 公开岗位性能，先形成 SQL/模板/响应传输证据，再做最小优化和聚焦回归。
- Evidence: 正式公网三个岗位 GET 均 `200`；未压缩响应 `394–420 KB`，Nginx gzip 后 `60–62 KB`。隔离 PostgreSQL 探针显示筛选选项 owner SQL `5→3`，完整岗位请求 `17→14`；岗位查询本身保持 count/page/prefetch 三条，无模板 N+1。
- Changed files: `apps/opportunities/queries/public.py`、`apps/opportunities/views.py`；临时回归文件仅用于本轮验证，已清理。
- Result: 合并筛选选项查询、复用来源计数、HTMX 跳过未使用摘要；聚焦测试 `6 passed`，既有岗位回归 `9 passed`，合并 `15 passed`；Ruff/format/Django check/diff check 通过。
- Labs: 三个已完成文件已定向同步并 `cmp` 验证；Labs 服务仍 `inactive/dead`，`health/live=502`，未启动/重启；本任务未执行 Git add/commit/push、生产 migration、部署或 P0 外部复测。

## 2026-09-20（正式增量发布）

- Objective: 将岗位性能优化提交 `42adeb4` 增量更新到正式环境。
- Preflight: 构建 `kaj-blog-web:42adeb4ceb74` 成功；候选 `check --deploy`、migration drift 和正式 `migrate --plan` 通过且无待执行 migration。
- Safety: 新鲜 PostgreSQL dump、媒体归档和 Compose 快照均为 `0600` 并完成 SHA-256/TOC/成员校验；未执行 migration、招聘采集、Provider/AGENT、恢复或 Outbox 补偿。
- Result: Web/Worker/Beat 按顺序切换，均为候选镜像、healthy/running、RestartCount 0；健康、岗位默认/搜索/筛选/分页及 JS/CSS 均 HTTP 200。
- Remaining: Labs 仍 inactive/dead；外部 P0 并发复测仍待执行；发布记录已由 `6f59ed8` 推送并 fast-forward 到远端 `main`。

## 2026-09-16

- Objective: 为 `/home/code/personal-blog` 建立完整的 repository-local multi-document handoff。
- Changed files:
  - `AGENT_HANDOFF.md`: 保留索引和恢复顺序。
  - `.agent-handoff/*.md`: 写入当前快照、工作区地图、决策、验证、backlog、风险和归档入口。
  - `AGENT_SESSION_PROMPTS.md`: 写入新窗口、继续、收口和质量复核提示词。
  - `AGENTS.md`: 追加标记的多文档 handoff protocol，保留既有项目规则。
- Result: handoff 已按当前主工作区、Labs、正式快照、Git 和服务状态填充；未创建 `.claude/CLAUDE.md`，因为项目当前没有 Claude Code 项目规则文件。
- Remaining risks: 主工作区脏且落后远端；handoff 文件当时尚未提交，后续已在 2026-09-17 完成交付。

## 2026-09-15

- Objective: 将性能测试任务文档从 Labs 提交并推送，保留当前正式快照，准备外部机器远程 P0。
- Changed files: `docs/operations/README.md`、`docs/operations/performance-testing/`（P0/P1/P2 任务及执行日志）。
- Result: Labs 任务提交 `0b700d4`，fast-forward 集成远端 `main`；临时分支已删除；未部署、未重启生产。
- Remaining risks: 外部 P0 尚未执行；执行日志仍为“未执行”。

## 2026-09-15（工作区审计）

- Objective: 核对 Labs-first 提交路径和主工作区漂移。
- Result: `origin/main`/Labs 为 `0b700d4`；主工作区 `e5adc20` 落后 21 个提交，存在 69 个 tracked 修改和 12 个 untracked 路径；未执行 reset、pull、merge 或覆盖。
- Remaining risks: 主工作区改动需要逐文件分类，不能整体迁移或丢弃。

## 2026-09-15（生产审核诊断）

- Objective: 诊断知识文档审核 `agents.profile_capability_unverified.v1`。
- Result: 生产只读读回显示知识审核 profile 需要 `knowledge-review.v1`；当前 Endpoint row version 为 8，但匹配的严格检查只有其他 schema，旧审核检查对应旧 row version。失败发生在 AGENT 外呼之前。
- Next action: 管理员对当前 Endpoint 选择知识文档审核 profile 执行严格 capability check，成功后重试审核。

## Work Log Guidelines

- Keep only recent, still-operationally-useful work here.
- Move stale or long history to `archive.md` as a compressed summary.
- Prefer file paths and concrete outcomes over prose summaries.
