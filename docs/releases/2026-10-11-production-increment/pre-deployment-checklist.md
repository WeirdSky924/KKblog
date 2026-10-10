# 2026-10-11 正式增量更新检查清单

## Labs 与候选

- [x] 答题模式聚焦回归和相关记录回归通过。
- [x] 招聘适配器、Worker socket 与部署维护路由聚焦回归通过。
- [x] `manage.py check`、migration drift、目标 Ruff/format、JavaScript 语法、前端完整构建和 `git diff --check` 通过。
- [x] Labs 应用 `learning.0015_quiz_attempt_mode_db_default`，读回 `mode` 数据库默认值 `'EXAM'`。
- [x] 生产只读基线：Web/Worker/Beat 为 `42adeb4ceb74`，Caddy 为 `2cbead0`；live/ready 为 `200`。
- [x] 生产 learning migration leaf 为 `0013_generation_batches`。
- [x] 生产共有 35 条启用的 `STALE` 来源；26 个浏览器 socket 错误、8 个响应契约错误、1 个超时；没有活动来源检查运行。
- [x] Nginx 维护片段只读核验；临时标记验证公网 `503` 和维护响应头，Web loopback health 在正式代理头下返回 `200`。

## Git 与生产

- [x] 远端 `main=d06af75` 包含本轮最终有效提交，任务分支 fast-forward 后已清理。
- [x] Web 候选 `kaj-blog-web:d06af75a9c31` 构建成功，源码 revision 和镜像 ID 已读回；Caddy 保持基线 `2cbead0`。
- [x] 候选 `check --deploy`、migration drift、正式 migration plan 通过；plan 包含 `learning.0014/0015`。
- [x] PostgreSQL、媒体和 Compose runtime/database 新鲜备份完成，均为 `0600`，摘要与可读性已读回。
- [x] Nginx maintenance、`0014+0015` migration、Web/Worker/Beat 切换、browser sandbox 更新和 `collectstatic` 完成。
- [x] 35 条来源逐条检查：30 成功、1 截断、4 失败；未运行每日全量检查或 Provider/AGENT 调用。
- [x] 根页、岗位页、CSS/JS、live/ready 均 `200`；答题匿名入口按权限 `302` 到登录；维护模式已关闭。
- [x] Labs Web 及 P12 PostgreSQL/Redis/Mailpit 已停止，测试数据与卷保留。

## 剩余事项

- 3 条来源仍因 `opportunities.adapter_response_invalid.v1` 保持 `STALE`（2 Hotjob、1 Meituan）；Qcraft 来源超时也保留 `STALE`。
- ByteDance 返回截断结果，来源状态保留 `DEGRADED`。
- PostgreSQL backend 两次以 exit-code 2 退出并自动恢复，容器无 restart/OOM；根因未知，需单独调查。
