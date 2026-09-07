# 2026-09-05 合并正式部署记录

状态：已完成（Asia/Shanghai）。本记录不包含密码、API Key、Cookie、连接串、正文或个人数据。

## Git 与镜像

- 代码发布提交：`87621e82180242ec6b04aeb61e474d6774064daa`。
- 合并文档前远端 `main`：`02ea58b4eaa0b7d1c2728231c292f6e0a8df8a97`；该提交包含此前两套 9 月 5 日记录。
- 第一阶段 Toast/反馈计数部署使用的应用提交为 `e0c3bf1e62290b408e34f01e850c1ea81e2be9d8`；第二阶段在该版本上完成 Labs 全量增量并切换到最终提交。
- 最终应用镜像：`kaj-blog-web:87621e821802`。
- 镜像 manifest ID：`sha256:65716759c674ef528d3c6df6ac38313289318b8ee7d18a1457585247aa1f037`。
- 旧应用镜像：`kaj-blog-web:e0c3bf1e6229`，ID
  `sha256:0899d493f05c6a974d99ce41b164bb1635068b62a658aba42f3cf6f03098803`，仍保留回退。
- Caddy、PostgreSQL、Redis、Umami 和 Mailpit 镜像未替换。

## 验证与构建

- `ruff check .`：退出 0；`ruff format --check .`：退出 0。
- `python manage.py check --deploy`：退出 0，仅保留开发配置警告。
- `python manage.py makemigrations --check --dry-run`：退出 0，无模型漂移。
- 隔离 `tests/contracts`：64 passed；前端 Markdown 导入回归：6 passed。
- 完整隔离 pytest 在 68 个用例通过后因主机持续 I/O 等待无进展被定向中止，退出 2；无断言失败输出，临时测试库、Redis 和 Mailpit 已清理。
- Docker 构建成功，构建阶段完成 `npm run build`；`collectstatic --noinput` 复制 168 个静态文件并处理 4 个文件，未使用 `--clear`。
- 候选生产配置预检和正式数据库 `migrate --plan` 均退出 0，后者为 `No planned migration operations`。

## 备份与切换

- PostgreSQL dump：
  `var/production/backups/pre-deploy-87621e8-20260905T064445Z.dump`，106,796,926 字节，
  SHA-256 `42dd59208cf3037befe8c4d53caa5a70241e9db103153eea611c52252a81af9e`。
- 媒体归档：
  `var/production/backups/pre-deploy-87621e8-20260905T064445Z-media.tar.gz`，6,150,943 字节，
  SHA-256 `5e006f425ee4e0c2af22afc381f02170c527b2f0f7a4f7f939a8a1e1838d6a04`。
- 媒体源快照为 133 个文件、8,404,382 字节；归档含 347 个成员，路径安全检查通过。
- 两份备份权限均为 `0600`，dump 通过容器内 `pg_restore --list`。
- 运行配置副本：
  `var/production/backups/compose.runtime.yaml.pre-87621e8-20260905T064445Z`，
  SHA-256 `ccb0a15533226636d256b411991864911fedb902c3676b3c7c5053d6a83f2bbd`。
- Nginx 维护页先返回 503，完成应用切换、健康检查和静态收集后关闭。
- 第一阶段 Toast 部署的历史备份仍保留：数据库
  `var/production/backups/pre-feedback-toast-20260905T024918Z.dump`（SHA-256
  `ff4f610400a2ac0bc8026b0849b58a84ed6294ae92e5667394b97394f181ce3a`），媒体归档
  `var/production/backups/pre-feedback-toast-20260905T024918Z-media.tar.gz`（SHA-256
  `03688acff0db6ce3ff402f5c79320ec6c7e4e5a54840b40609cce74ed07d912d`）。

## 状态修复与线上读回

- 通过 `apps.opportunities.recover_check_leases` 执行恢复：`opportunity-recovery:0:0:0`；未调用 adapter 或手动抓取。
- 活动 `OpportunityCheckRun`、`RUNNING` 来源、`running`/过期 TaskRun、待发布 Outbox、过期 Outbox 租约和 `PROCESSING` consumer 均为 0。
- 第一阶段维护窗口读回 3 条学习管理 Outbox 事件已发布且对应消费者均为 `processed`；第二阶段再次读回待发布 Outbox 为 0，未产生重复通知。
- 候选 Worker 成功处理 `publish_outbox`；Beat 日志持续显示 Outbox、机会恢复、补偿和服务健康任务，未出现新的 `core.outbox_transport_failed.v1`。
- 公网 `/health/live`、`/health/ready`、首页、登录页、作者公开页和文章页均为 200；匿名通知、知识和找工作入口按权限返回 302。
- 新静态 CSS、JS、导航脚本、主题脚本均为 200；头像、正文图片和封面媒体均为 200。
- `/analytics/collect` 不再 404；空探测返回上游 400，非重复 `/analytics/analytics/collect` 路径。
- `blog-playwright-cli` 匿名生产烟测完成后已关闭浏览器且无会话残留。

## 保留与未执行项

- 旧镜像、数据库 dump、媒体归档、运行配置副本和旧静态文件均保留。
- 未导入 Labs 账户、文章、岗位、题库、媒体或任务历史；未手动启动招聘全量抓取。
- 完整 pytest 的资源性中止已记录；后续应在资源充足的隔离环境补跑全量回归。
