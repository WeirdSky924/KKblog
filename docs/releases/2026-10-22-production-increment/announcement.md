# 2026-10-22 Kajspace 正式增量更新公告

状态：已完成（2026-10-22）。本公告只记录本轮正式增量更新。

## 本轮变更

- 上线文章专注模式：登录用户可在文章工具栏启停专注计时、暂停/继续并接收失焦提醒；管理员可配置无操作阈值和手动暂停上限。
- 上线手机版文章阅读模式：支持连续滚动、左右分页和上下逐屏翻页，提供主题、字号、目录及页码；分页设置浮于正文上方，不改变正文视口尺寸。
- 修复专注提示和阅读器交互中的反馈、分页与设置显隐问题。
- 数据核查：正式环境终态岗位运行遗留活动来源、活动父运行、活动来源和运行中的岗位 TaskRun 均为 `0`；本轮没有需要写入修复的异常状态。

## 提交

- 本轮唯一运行时代码提交：`e179693d48157aea613f5604bf10058de6849f16`（`feat: add article focus and mobile reader modes`）。
- 任务分支 `codex/production-increment-20261022` 已推送，远端 `main` 已 fast-forward 至该提交。

## 更新范围

- 正式镜像以当前生产镜像为基础构建，应用迁移 `navigation.0009_focus_mode_settings`。
- 详细构建、备份、切换、健康读回和测试服务收尾结果见同目录 `deployment-record.md`。

## 验证与发布结果

- 完整前端构建通过；前端测试 `5 passed`；隔离 PostgreSQL/Redis/Mailpit 聚焦回归 `29 passed`；Ruff、JS 语法和差异检查通过。
- 候选 `check --deploy` 无问题，migration drift 无变化；正式 migration plan 只含 `navigation.0009_focus_mode_settings`，应用后计划为空。
- Web/Worker 使用本轮镜像且健康，Beat 运行，restart count 均为 `0`；公网 live/ready、首页、公开文章与静态 CSS/JS 均返回 `200`。
- 已完成 DB、媒体与 Compose 快照，并于更新后关闭 Labs Web/Worker/Beat/Outbox 和 P12 PostgreSQL/Redis/Mailpit 测试服务；数据卷保留。
- 本轮没有新错误状态需要数据库写修复；生产岗位状态审计为 `0/0/0/0`。未运行招聘采集、Provider、AGENT 或真实邮件。
- 按用户此前要求未启动浏览器；手机阅读器/专注模式视觉和手势由用户实机验收。
