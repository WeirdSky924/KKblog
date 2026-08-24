# 2026-08-11 正式环境增量更新公告

## 发布信息

- 部署完成时间：2026-08-11 10:21（Asia/Shanghai）
- 上次正式源码：`d53ebe0480f96eec0fb206f50c86f3dbed70d856`
- 本次正式源码：`2cbead0794ece4f07e290ed982f5b05c4736ed56`
- 上次应用镜像：`kaj-blog-web:d53ebe0`
- 本次应用镜像：`kaj-blog-web:2cbead0`
- 应用镜像摘要：`sha256:4f682010cf1381217dea1114cac58e6c7f68dc3c947624cf68ef3029ed7f83f8`
- 上次 Caddy 镜像：`kaj-blog-caddy:d53ebe0`
- 本次 Caddy 镜像：`kaj-blog-caddy:2cbead0`
- Caddy 镜像摘要：`sha256:99002dff038d0ead4b5118dddcf56843f30da5465de32561418a9e999ac6a885`
- 数据策略：增量迁移，不重建数据库，不清空或替换既有内容、媒体和数据卷

## 相对上次正式版本的变化

### 文章编辑与渲染

- 富文本编辑器增加结构化 TipTap 文档、工具栏、列表、任务列表、表格、代码块、链接、图片、附件、嵌入、块拖动与操作、文档大纲和撤销恢复能力。
- 优化粘贴图片、上传状态、本地草稿、实时预览、编辑性能反馈和历史版本展示。
- Markdown 与富文本使用统一的安全渲染、标题投影、可信嵌入和媒体引用规则，编辑预览、历史版本和公开文章保持一致。
- 增加富文本内容安全策略、结构限制和渲染性能保护。

### 标签与通知

- 文章标签选择改为可搜索的浮动窗口，并支持申请当前不存在的标签。
- 被驳回的标签可以再次申请；同名标签的审核历史、文章关联、审计和通知保持在同一个标签身份下。
- 管理通知支持多行 Markdown 输入，列表显示摘要，详情显示经过统一净化的 Markdown 内容。
- 举报、标签审核和管理通知继续复用统一通知入口，没有新增平行通知链路。

### 账户与界面

- 用户名在原长度预算内支持数字、下划线、标点和普通 emoji，并继续拒绝空白、控制字符和不可见字符。
- 调整顶部搜索类型选择器的箭头占位，避免遮挡或挤压搜索文字。
- 完善文章作者、标签、媒体和正文结构在公开阅读页面中的展示。

## 数据库更新

迁移前进入维护状态并停止 Web、Worker 和 Beat 写入，只增量应用以下三条迁移：

- `content.0013_articlerevision_tiptap_schema_version`
- `content.0014_allow_rejected_tag_name_reproposal`
- `content.0015_merge_duplicate_tag_identities`

迁移结果：

- 三条迁移均成功应用，发布后 `migrate --plan` 无待执行操作。
- TipTap 修订增加明确的 schema 版本和正文形状约束。
- 同名标签身份及其文章、修订、历史、审计和通知关联按规范名归并，并恢复规范名全局唯一约束。
- 发布后标签共 13 条，重复规范名组为 0；文章标签关联 19 条，修订标签关联 52 条。
- 本次没有重建、清空或替换 PostgreSQL、Redis、Umami、媒体目录、静态目录及其数据卷。

## 备份与数据保护

本周定时备份已经存在，周备份 owner 对同一周保持幂等。为避免复用旧归档或伪造第二条周记录，本次在写入服务停止后额外创建了独立的部署前归档：

- 归档：`deploy-pre-migration-20260811T015226Z-2cbead0.tar.gz`
- 大小：`15,217,098` bytes
- SHA-256：`782df3d129bf725df5d9010efab4cb645433a7338aa21a34b0132945e4eb2910`
- 权限：`0600`
- 内容：`manifest.json`、PostgreSQL custom-format `database.dump` 和完整受管媒体目录
- 校验：归档 SHA-256 读回通过，从最终归档重新提取的 `database.dump` 通过 `pg_restore --list`

该归档没有覆盖既有周备份，也没有伪造新的 `BackupRecord`。本次未执行完整隔离恢复演练，manifest 中的 `restore_verified` 保持为 `false`。

## 发布后验证

- Web、Worker、Beat 均运行 `kaj-blog-web:2cbead0`；Web 和 Worker 健康检查通过，Worker 返回 Celery `pong`，Beat 保持单实例运行。
- Caddy 运行 `kaj-blog-caddy:2cbead0`；PostgreSQL、Redis、Umami 和 Mailpit 保持原服务与原数据挂载。
- `https://kajspace.cn/health/live` 和 `https://kajspace.cn/health/ready` 均返回 HTTP 200。
- 主页、搜索页、登录页、Markdown 文章和 TipTap 文章均返回 HTTP 200。
- 静态图片、Markdown 正文图片和 TipTap 正文图片均返回 HTTP 200，并带有正确的图片 Content-Type。
- 主页在 1440 x 900 和 390 x 844 视口下无横向溢出，18 篇公开文章完整出现，可见图片无裂图。
- Markdown 桌面文章和 TipTap 移动文章均显示正文、作者和媒体，且无横向溢出或可见裂图。
- 通知多行 Markdown、加粗、列表和脚本净化验证通过；用户名安全符号允许、空白字符拒绝验证通过。
- 发布后连续读回的 Web、Worker、Beat 和 Caddy 日志没有新增错误标记，本次没有执行应用回退。
- Labs 测试环境保持独立运行并返回 HTTP 200，没有被本次正式部署替换或合并。

## 已知限制

- Umami 采集请求仍会把路径拼接为 `/analytics/analytics/collect` 并返回 HTTP 404；该问题不影响页面、文章或媒体读取，需要单独修正分析配置。
- 一篇约 637 KB 的既有 Markdown 文章可以成功渲染，但耗时约 2.6 秒，超过 250 ms 的富文本性能预算，需要后续单独优化超大正文。
- 本公告记录的是增量部署与只读生产验收结果，不代表已经完成生产数据恢复演练或所有登录态写入流程的生产操作验证。
