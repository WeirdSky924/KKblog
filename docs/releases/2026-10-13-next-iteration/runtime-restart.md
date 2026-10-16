# Labs 运行资源重启记录（2026-10-13）

## 范围

本记录对应 `codex/labs-next-20261013` 分支和
`/home/code/.codex-worktrees/personal-blog/labs-test-environment` worktree。
运行时代码基线仍为正式 revision `d06af75`；`d06af75..origin/main` 在
`apps/`、`config/`、`docker/`、`static/`、`templates/` 下没有差异。

## 执行与结果

- 停止并重新启动了 Labs Web、Worker、Beat。
- 依次重启了 `kaj-p12-postgres`、`kaj-p12-redis`、`kaj-p12-mailpit`，保留原有数据卷，没有清空或重建数据。
- 首次 Web 重启后，systemd 进程仍存活但端口暂未监听；检查确认 Django autoreloader 子进程处于 `folio_wait_bit_common` 的 swap 等待。公网短暂返回 `502`，没有代码或配置改动。
- 在停止 Worker/Beat、让 Web 完成启动后，本地 health 恢复 `200`；随后按依赖顺序清除 Worker/Beat 的失败状态并启动，两者均恢复 `active/running`。

## 最终读回

- `https://labs.kajspace.cn/health/live`：`200`。
- `127.0.0.1:18082/health/live` 携带 `X-Kaj-Client-IP: 127.0.0.1`：`200`。
- PostgreSQL `pg_isready`：accepting connections；Redis：`PONG`；Mailpit API：`200`，容器 health：`healthy`。
- `kaj-labs.service`、`kaj-labs-worker.service`、`kaj-labs-beat.service`：`active/running`。
- `kaj-labs-outbox.service`：仍为 `failed/timeout`；`kaj-labs-outbox.timer`：`inactive/dead`。两条历史 `task.final_failed.v1` 事件未通过 SQL 删除、清零或改写。

本轮没有执行生产 migration、部署、生产重启、招聘采集、Provider/AGENT 调用、真实邮件发送或 Git 交付。下一轮开始前仍需单独调查 Outbox transport 失败原因。
