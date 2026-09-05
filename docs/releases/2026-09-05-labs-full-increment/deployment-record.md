# 2026-09-05 正式增量部署记录

状态：已完成（Asia/Shanghai）。本记录不包含密码、API Key、Cookie、连接串、正文或个人数据。

## Git 与镜像

- 远端 `origin/main`：`87621e82180242ec6b04aeb61e474d6774064daa`。
- 任务提交：`87621e8`，提交信息为 `feat: 汇入 Labs 分页与管理交互更新`；任务分支已推送并 fast-forward 到远端 `main`。
- 候选镜像：`kaj-blog-web:87621e821802`。
- 镜像 manifest ID：`sha256:65716759c674ef528d3c6df6ac38313289318b8ee7d18a1457585247aa1f037`；镜像 label 的源码 revision 与 Git SHA 一致。
- 旧应用镜像：`kaj-blog-web:e0c3bf1e6229`，ID `sha256:0899d493f05c6a974d99ce41b164bb1635068b62a658aba42f3cf6f03098803`，仍保留回退。
- Caddy、PostgreSQL、Redis、Umami 和 Mailpit 镜像未替换。

## 验证与构建

- `ruff check .`：退出 0；`ruff format --check .`：退出 0。
- `python manage.py check --deploy`：退出 0，仅保留 4 条未配置 HSTS/SSL/CSRF/DEBUG 的开发提示。
- `python manage.py makemigrations --check --dry-run`：退出 0；无模型漂移。
- 隔离 `tests/contracts`：64 passed；前端 Markdown 导入回归：6 passed。
- 完整隔离 pytest 在 68 个用例通过后因主机持续 I/O 等待无进展被定向中止，退出 2；无断言失败输出。测试库已清理，Redis 临时 DB 和 Mailpit 均清零。
- Docker 构建成功，前端 `npm run build` 在构建阶段完成；`collectstatic --noinput` 复制 168 个静态文件并处理 4 个文件，未使用 `--clear`。
- 候选镜像生产配置预检和正式数据库 `migrate --plan` 均退出 0，后者显示 `No planned migration operations`。

## 备份与切换

- PostgreSQL dump：`var/production/backups/pre-deploy-87621e8-20260905T064445Z.dump`，106,796,926 字节，SHA-256 `42dd59208cf3037befe8c4d53caa5a70241e9db103153eea611c52252a81af9e`。
- 媒体归档：`var/production/backups/pre-deploy-87621e8-20260905T064445Z-media.tar.gz`，6,150,943 字节，SHA-256 `5e006f425ee4e0c2af22afc381f02170c527b2f0f7a4f7f939a8a1e1838d6a04`。
- 媒体源快照为 133 个文件、8,404,382 字节；归档含 347 个成员，路径安全检查通过。两份备份权限均为 `0600`，dump 通过容器内 `pg_restore --list`。
- 运行配置副本：`var/production/backups/compose.runtime.yaml.pre-87621e8-20260905T064445Z`，SHA-256 `ccb0a15533226636d256b411991864911fedb902c3676b3c7c5053d6a83f2bbd`。
- Nginx 维护页先返回 503，完成 Web/Worker/Beat 切换、健康检查和静态收集后关闭；生产 Compose 仅更新应用镜像和 Web `--timeout=120`。

## 状态修复与线上读回

- 通过现有 `apps.opportunities.recover_check_leases` 任务入口执行恢复：`opportunity-recovery:0:0:0`；未调用 adapter 或手动抓取。
- 维护前后活动 `OpportunityCheckRun`、`RUNNING` 来源、`running`/过期 TaskRun、待发布 Outbox、过期 Outbox 租约和 `PROCESSING` consumer 均为 0。
- 候选 Worker 成功处理 `publish_outbox`；Beat 日志持续显示 Outbox、机会恢复、补偿和服务健康任务，未出现新的 `core.outbox_transport_failed.v1`。
- 公网 `/health/live`、`/health/ready`、首页、登录页、作者公开页和文章页均为 200；匿名通知、知识和找工作入口按权限返回 302。
- 新静态 CSS、JS、导航脚本、主题脚本均为 200；头像、正文图片和封面媒体均为 200；`/analytics/collect` 不再 404，空探测返回上游 400。
- `blog-playwright-cli` 匿名生产烟测通过，检查结束已关闭浏览器且无浏览器会话残留。

## 回退与未执行项

- 旧应用镜像、数据库 dump、媒体归档、运行配置副本和旧静态文件均保留；本轮无 schema 变化，应用异常时只回退 Web/Worker/Beat，不反向迁移。
- 未导入 Labs 账户、文章、岗位、题库、媒体或任务历史；未手动启动招聘全量抓取。
- 完整 pytest 因资源性 I/O 无进展未完成，后续应在资源充足的隔离环境补跑全量回归；本次已用 64 项契约回归、候选生产预检和线上用户流作为替代证据。
