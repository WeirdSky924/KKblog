# 生产增量更新准备证据

记录时间：`2026-08-15T03:09:53+08:00`

## 候选冻结

- 正式基线：`2cbead0794ece4f07e290ed982f5b05c4736ed56`
- 候选提交：`395893118e981c50525039e1f807b23153e1d728`
- 候选冻结时的远端 `main`：`395893118e981c50525039e1f807b23153e1d728`
- 候选镜像：`kaj-blog-web:395893118e98`
- 候选镜像 ID：`sha256:5cf942570a44f722faed5ebd4a5d00678bdba804e1e07818cb2832706a1a2e21`
- 候选镜像 revision：`395893118e981c50525039e1f807b23153e1d728`

本证据文档属于候选冻结后的 docs-only 提交，不改变上述应用源码与镜像内容。

## 已完成门禁

- 全量 pytest：`737 passed, 1 skipped`，退出码 0。跳过项仅为未配置隔离 Umami 数据库的既有留存测试。
- 工作机会模块 pytest：`115 passed`，退出码 0。
- 来源清单命令测试：`4 passed`，退出码 0。
- 浏览器 socket 与容器契约测试：`13 passed`，退出码 0。
- Ruff lint：`All checks passed!`，退出码 0。
- Ruff format：`821 files already formatted`，退出码 0。
- Django system check：无问题，退出码 0。
- migration drift：`No changes detected`，退出码 0。
- 前端正式构建：通过，退出码 0。
- 前端 Node 契约：`6 passed`，退出码 0。
- `git diff --check` 与提交前暂存差异检查：通过，退出码 0。
- `systemd-analyze verify`：新浏览器服务单元通过；输出只包含宿主既有 `cloudmonitor.service` 警告。

## 镜像运行时证据

- 应用以 `uid=10001(kaj) gid=10001(kaj)` 运行。
- `pymediainfo` 能加载镜像内的 `libmediainfo`。
- 来源清单可由应用用户读取，SHA-256 为 `12c89e1a83ca9f8d8583f4ec5e10ccb1991b9783f7a222d031fe0081dc2cf934`。
- `static/dist/app.js` 与 `static/dist/styles.css` 已生成。
- 通用应用镜像不包含 Node、Playwright、Chromium 或 Google Chrome。
- 独立宿主浏览器服务已通过真实 Chrome 沙箱、Unix socket 权限和应用 UID 调用 smoke。

## 来源迁移边界

- 版本化清单包含 `41` 个来源、`48` 个允许主机、`0` 个 adapter secret/config key。
- 只迁移来源名称、入口、适配器、允许主机、请求和调度参数等配置。
- 不迁移 Labs 的岗位、筛选项、收藏、审核、快照、任务历史、检查状态或错误状态。
- 导入后来源统一重置为未公开、从未检查；岗位和运行时事实表在正式重爬前保持为空。
- 正式切换通过 smoke 后，只启动一次受控全量抓取，从官方来源重新生成岗位数据。

## 正式环境未变更

读回时正式 Web、Worker、Beat 仍使用 `kaj-blog-web:2cbead0`，不可变镜像 ID 均为 `sha256:4f682010cf1381217dea1114cac58e6c7f68dc3c947624cf68ef3029ed7f83f8`，状态为 running，RestartCount 均为 0。

本轮未执行正式数据库或媒体备份、维护页切换、migration、来源导入、collectstatic、Compose 镜像切换、服务重启、全量抓取或数据清理。正式执行顺序、停止条件和回滚边界以同目录 `deployment-plan.md` 与 `pre-deployment-checklist.md` 为准。
