# J. 数据交换、分析与维护

所有者：`apps/exchange` 管导入/导出 Job；`apps/analytics` 管 Umami 集成/保留；`apps/operations` 管备份、部署记录和健康。三者不拥有文章正文或媒体字节。

## 内部目录

```text
apps/exchange/
  models/{import_job,import_item,export_job,export_selection}.py
  services/{package_reader,preview,importer,exporter,downloads}.py
  formats/{front_matter,manifest,markdown,archive}.py
  policies/{import_access,export_access}.py
  tasks/{import_job,export_job,cleanup}.py
apps/analytics/
  services/{access,retention}.py
  presentation/admin_view.py
  tasks/retention.py
apps/operations/
  services/{backup,deployment}.py
  tasks/{backup,backup_cleanup}.py
```

## Markdown 导入

所有作者可导入，分解析预览和确认写入。压缩包安全上限为 `64 MiB` 压缩大小、`256 MiB` 总展开量、`1000` 项、`8` 层嵌套和 `100:1` 压缩比；安全解包、Front Matter 白名单、媒体统一校验后，逐篇分类：新建、ID 重复、同标题警告、跨作者冲突、无效。

作者逐篇选 SKIP/UPDATE/CREATE、分区/标签映射和是否纳入；确认后每篇独立事务，部分成功保留。已有 ID 是唯一更新依据；标题相同只警告。跨作者 ID 禁止更新/新建，文章归属永远是导入者。

更新创建新修订并保留历史；Markdown 覆盖富文本是显式格式例外。未知分区进入空分区；新标签进入待审并立即显示。`job + item` 幂等，重复确认不重复写。

## 管理员导出

仅唯一管理员，可选全站、作者、分区或文章；包含草稿、定时、私人、冷静期、完整历史和媒体。ZIP 含 manifest/JSON、Markdown 便利副本、TipTap 原始 JSON 和媒体，不能把格式转换宣称无损。

全站最多一个 RUNNING，已有任务时拒绝而非排队。取消删除 `.part` 并保留 Job/审计；完成包只经管理员鉴权下载，三天删除，无公开链接。导出他人内容按作者/上海日通知。

## 备份

PostgreSQL 与全部媒体在 `Asia/Shanghai` 每周一 03:00（`0 3 * * 1`）同轮备份，本地保留 30 天、不加密、不自动校验 dump、不做恢复演练。网页无下载/恢复，恢复由服务器人工执行。失败三次后站内+管理员邮件告警。

扩展边界可保留 destination port，但首版 DTO/UI 只能显示和保存 `local`，不出现不可用外部选项；未来目标凭据也只能在服务器 `.env`。

## Umami

自托管 Umami 统计公共、登录、私人、个人和管理所有页面；只有管理员经博客同源入口访问，容器不暴露公网端口。每日删除一个月以前分析数据。Umami 不承载产品浏览量、审计或错误事实。

## 部署

仅用户明确授权后执行：构建 → 检测 migration → 有迁移先新备份 → 维护页 → 迁移/切应用 → 健康检查 → 成功关闭；失败则回滚应用，不自动回滚数据库。migration 必须向前兼容旧应用。

项目当前没有网页部署按钮。`.env` 只直接编辑文件；Git 提交/推送与部署是分别授权的动作。

## UI

作者导入上传/预览/结果；管理员导出筛选/运行/取消/下载/过期；备份只读记录；任务和错误入口；Umami 内嵌/代理入口。后台 Job 接受只显示“进行中”，完成/失败依真实状态更新。

## 验证

zip-slip、`64/256 MiB`、`1000` 项、`8` 层、`100:1` 与边界超限、YAML 类型、坏图跳过、ID/标题/归属、格式转换历史、重复确认、部分成功；导出全局唯一/取消完成竞态/下载授权/三天清理；备份命令失败告警；Umami 未授权/公网不可达/一月清理；部署 migration 失败和健康失败应用回滚模拟。

施工依据：`flows/04-import-export-sequences.md`、`contracts/05-background-tasks.md`、`delivery/02-module-verification-matrix.md`。
