# 备份与人工恢复

当前备份能力每周将 PostgreSQL custom-format dump 和全部受管媒体打入同一个本地
`.tar.gz` 归档。调度为 `Asia/Shanghai` 每周一 03:00，归档保留 30 天。

## 能力边界

- 首版目标只有 `local`，归档不加密。
- `COMPLETED` 只表示 `pg_dump`、媒体读取、归档写入和原子改名成功。
- 当前归档**未验证可恢复**：系统不自动执行 `pg_restore`、dump 内容校验或恢复演练。
- 网页不提供备份下载、恢复或目标配置；这些动作只能由服务器管理员在获批的维护窗口人工完成。
- `.env`、私钥、凭据文件和备份目录本身不得进入媒体归档。

## 恢复前准备

1. 取得本次生产恢复的明确授权，进入维护窗口并停止所有会写数据库或媒体的应用、Worker 和 Beat。
2. 记录当前应用版本、数据库版本、迁移状态、目标归档的 `BackupRecord` ID、大小和 SHA-256。
3. 在受控临时目录中核对归档文件大小和 SHA-256；不要在项目媒体目录或备份目录内直接展开。
4. 检查归档只包含 `manifest.json`、`database.dump` 和 `media/`，且没有绝对路径、`..`、链接或设备文件。
5. 准备一个全新的隔离 PostgreSQL 数据库和空媒体目录。禁止直接覆盖仍在运行的生产数据库或媒体目录。

## 人工演练顺序

以下命令是操作模板，不包含真实连接串或凭据，也不表示已经执行过恢复：

```bash
tar -xzf <backup-id>.tar.gz -C <controlled-temporary-directory>
pg_restore --list <controlled-temporary-directory>/database.dump
pg_restore \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  --dbname=<isolated-restore-database> \
  <controlled-temporary-directory>/database.dump
```

随后把 `media/` 复制到新的空媒体目录，使用与归档匹配的应用版本连接隔离数据库，执行：

1. `python manage.py check` 和 `python manage.py migrate --check`。
2. `/health/ready` 健康检查。
3. 管理员登录、公开文章、私人文章权限和实际媒体读取抽查。
4. 核对数据库记录数、关键对象和媒体文件，不把仅能启动视为恢复成功。

只有上述隔离恢复与业务抽查全部通过，才能在独立审批下规划生产切换。任何失败都应保留原生产数据和原媒体目录，停止切换并记录安全错误码；不得自动回滚数据库。

## 保留与清理

到期任务只删除 30 天边界上的本地归档并将记录标为 `EXPIRED`，不会删除
`BackupRecord`。清理失败进入统一 TaskRun 重试；第三次失败产生运行错误、管理员站内通知和运维邮件。生产归档的手工删除或提前清理仍需当前回合明确授权。
