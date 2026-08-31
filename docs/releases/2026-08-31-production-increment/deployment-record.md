# 2026-08-31 正式增量执行记录

状态：已完成（2026-08-31）。本记录不包含密码、API Key、Cookie、连接串、正文或个人数据。

## 候选验证（2026-08-31，非生产）

- `uv run ruff check .`：通过。
- 受影响 Python 文件 `ruff format --check`：通过；`uv lock --check`、Python 编译、Django check 和 migration drift：通过。
- Agent/题库/审查/管理批量处置聚焦回归：`18 passed`；机会适配器、分页、状态恢复：`69 passed`；答题、LaTeX、交换：`17 passed`；架构合同：`5 passed`。
- 前端行为测试：`6 passed`；`npm run build`：通过。
- 全部 44 份来源清单可解析；`opportunity_sources.additions-2026-08-29.all.json` dry-run：`109` 条。仅执行 dry-run，没有执行 `--apply`、来源检查或 adapter 采集。
- Labs `kaj-labs.service` 与 Worker 保持 `active/running`，`https://labs.kajspace.cn/health/live` 返回 `200`。
- 验证使用隔离 PostgreSQL/Redis/Mailpit；临时测试库已定向清理。上述验证不代表正式数据库、镜像或服务已经更新。

## 正式只读基线（2026-08-31）

- 正式数据库 migration 记录数为 `87`，现有招聘来源为 `41`。
- 发现 `1` 条活动的 `FULL/RUNNING` 检查运行：41 个来源中 25 个成功、1 个失败、1 个截断、14 个仍为待执行；关联 TaskRun 已是 `final_failed`（尝试 3），没有运行中来源或有效租约。这是历史异常状态，不在本轮读取时修改。
- 候选恢复任务现在会在租约回收前协调这类终态 TaskRun 与活动领域运行：未完成来源标记安全失败并重新汇总，释放活动运行互斥；正式窗口必须先执行并读回该恢复结果，再允许每日定时任务创建新运行。

## 发布身份

- 候选 Git 提交：`a7df26300e790505df07ff9d11305f540bcae7d4`
- 上一正式提交：`e5adc20`
- 候选 Web/Worker/Beat 镜像：`kaj-blog-web:a7df26300e`
- 候选镜像摘要：`sha256:5e1ead7584017f3a4afff73b80fb8362561431ef8feca2efba4fd4ba82a99d7a`
- 上一应用镜像保留：`kaj-blog-web:dbbe60c843ba`
- Caddy 未变更：`kaj-blog-caddy:2cbead0`
- 执行窗口（Asia/Shanghai）：`2026-08-31 17:08–17:40`
- 执行人/复核人：自动化发布流程 / Codex 读回

## 备份与迁移

- 生产数据库备份：`var/production/backups/pre-6bc43794-20260831T170816+0800.dump`，`79,160,650` 字节，SHA-256 `3f9707c670a93894bce2fbc7374089de92493b3ec3c375894bffe1e4a28df9ee`。
- 媒体归档：`var/production/backups/pre-6bc43794-20260831T170816+0800-media.tar.gz`，`5,102,000` 字节，SHA-256 `d2acc27c0eac5e74d82ec6391f1abd444c5df2fa74b9d76aef1090903bb5e6fe`；包含 296 个归档条目。
- `pg_restore --list`：候选镜像内 PostgreSQL 16 客户端校验成功，1005 行。
- `migrate --plan`：无待执行 migration；正式 leaf 保持 87。
- 实际迁移：跳过，退出码 0；未反向迁移。
- 编排备份：`var/production/compose.runtime.yaml.pre-a7df263-20260831T1715+0800`。

## 错误状态修复

- 恢复入口与批次：`apps.opportunities.recover_check_leases` 每分钟自动执行。
- 回收/重新派发数量：历史孤儿运行收口 1 条；过期租约回收 0；重新派发 0。
- 仍为 RUNNING 的过期租约：0。
- 活动运行与来源运行态读回：活动运行 0、运行中来源 0、running TaskRun 0；历史运行已转为 `PARTIAL`（25 成功、15 失败、1 截断）。
- 安全错误码/通知去重读回：失败来源保留安全错误码；恢复汇总经现有 Outbox 发布，无重复活动运行。

## 来源配置

- dry-run 输出：`sources=109 dry_run=true`。
- apply 输出：`sources=109 created=109 updated=0`。
- 启用/停用计数：新增来源启用 88、停用 21；全部 `publicly_visible=false/check_state=NEVER`。
- 岗位、快照、TaskRun 导入前后计数：岗位 11874，来源导入前后未增加；本窗口未创建来源检查运行。
- 未执行手动爬取确认：未调用 source check、adapter `collect()` 或浏览器 collector。
- 下一次定时采集：由 Beat 在下一个上海时间 18:00 窗口自动触发；本次不提前执行。

## 健康与回退

- `/health/live`：`200`；`/health/ready`：`200`。
- 关键页面/媒体读回：主页、文章、找工作、知识文档、答题入口均 `200`；版本化 CSS `200/468415` 字节，KaTeX 字体 `200/28076` 字节。
- Web/Worker/Beat/Caddy 状态：全部运行；Web/Worker healthy；本次 Beat 重建后 RestartCount 为 1，当前无 OOM。
- 静态资源：`collectstatic --noinput` 成功，164 copied、4 unmodified、64 post-processed。
- 日志 5xx/404/OOM 检查：未发现候选启动、迁移或 OOM 错误；公网异常 Host 请求被既有 `ALLOWED_HOSTS` 安全拒绝。
- 是否需要回退及原因：不需要；旧应用镜像和数据库保持可回退状态。
- 旧镜像和备份保留位置：旧镜像 `kaj-blog-web:dbbe60c843ba`、上述数据库/媒体备份均保留。
