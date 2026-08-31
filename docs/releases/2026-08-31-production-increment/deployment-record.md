# 2026-08-31 正式增量执行记录

状态：待执行。请在获批的生产维护窗口内填写；不要在此记录密码、API Key、Cookie、连接串、正文或个人数据。

## 候选验证（2026-08-31，非生产）

- `uv run ruff check .`：通过。
- 受影响 Python 文件 `ruff format --check`：通过；`uv lock --check`、Python 编译、Django check 和 migration drift：通过。
- Agent/题库/审查/管理批量处置聚焦回归：`18 passed`；机会适配器、分页、状态恢复：`69 passed`；答题、LaTeX、交换：`17 passed`；架构合同：`5 passed`。
- 前端行为测试：`6 passed`；`npm run build`：通过。
- 全部 44 份来源清单可解析；`opportunity_sources.additions-2026-08-29.all.json` dry-run：`109` 条。仅执行 dry-run，没有执行 `--apply`、来源检查或 adapter 采集。
- Labs `kaj-labs.service` 与 Worker 保持 `active/running`，`https://labs.kajspace.cn/health/live` 返回 `200`。
- 验证使用隔离 PostgreSQL/Redis/Mailpit；临时测试库已定向清理。上述验证不代表正式数据库、镜像或服务已经更新。

## 发布身份

- 候选 Git 提交：
- 上一正式提交：`e5adc20`
- 候选 Web/Worker/Beat 镜像摘要：
- 候选 Caddy 镜像摘要：
- 执行窗口（Asia/Shanghai）：
- 执行人/复核人：

## 备份与迁移

- 生产数据库备份 ID、路径、大小、SHA-256：
- 媒体归档路径、大小、SHA-256：
- `pg_restore --list`：
- `migrate --plan`：
- 实际迁移 leaf 与退出码：

## 错误状态修复

- 恢复入口与批次：
- 回收/重新派发数量：
- 仍为 RUNNING 的过期租约：
- 活动运行与来源运行态读回：
- 安全错误码/通知去重读回：

## 来源配置

- dry-run 输出（109 条）：
- apply 输出（created/updated）：
- 启用/停用计数：
- 岗位、快照、TaskRun 导入前后计数：
- 未执行手动爬取确认：
- 下一次定时采集时间与观察负责人：

## 健康与回退

- `/health/live`：
- `/health/ready`：
- 关键页面/媒体读回：
- Web/Worker/Beat/Caddy 状态与 RestartCount：
- 日志 5xx/404/OOM 检查：
- 是否需要回退及原因：
- 旧镜像和备份保留位置：
