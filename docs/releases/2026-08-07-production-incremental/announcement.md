# 2026-08-07 正式环境增量更新公告

## 发布信息

- 发布时间：2026-08-07 17:34（Asia/Shanghai）
- 上次正式应用版本：`kaj-blog-web:284997d`
- 上次正式 Caddy 版本：`kaj-blog-caddy:media-host-fix-20260806`
- 本次应用版本：`kaj-blog-web:d53ebe0`
- 本次 Caddy 版本：`kaj-blog-caddy:d53ebe0`
- 应用源码 revision：`d53ebe0480f96eec0fb206f50c86f3dbed70d856`
- Web 镜像摘要：`sha256:f5dc47a4db1fe5b48441828ad05f554f37053f91eeccd153c3ba3cba1236fd48`
- Caddy 镜像摘要：`sha256:a7e319617678eba53482566fe6049f920faa0f9fe3814c6a459b1e7f0b5a4071`

## 相对上次正式版本的变化

本次发布包含 `aef1ee9` 和 `d53ebe0` 两个提交中的应用改动，主要包括：

- 文章阅读与账户交互：文章点赞、阅读书签、收藏和复制入口的统一交互，搜索分类与登录后的即时建议，文章和列表中的作者信息，以及编辑器预览定位优化。
- 评论审核：作者或管理员可以置顶或取消置顶文章评论；评论通知保留完整的举报上下文。
- 账户流程：注册用户名真实保存并校验；邮箱验证码登录只对已注册且可用的账户发起，不再为不存在或停用账户发信或创建登录挑战。
- Markdown 与媒体：恢复完整 Markdown 正文渲染能力，修正 Caddy 对媒体路径的代理与静态媒体读取，保留附件与文章图片的现有访问路径。
- 管理与主页：分区、标签、导航、主页筛选和文章列表的交互及布局优化随应用版本一并更新。

## 数据库变更

在新鲜生产备份完成后，仅增量应用以下三条迁移：

- `comments.0005_comment_pin`
- `discovery.0003_reading_bookmark`
- `discovery.0004_article_like`

这些迁移只新增评论置顶、账户文章阅读书签和账户文章点赞所需的表、索引与约束，没有删除或回填既有文章、账户、评论、媒体或其他业务记录。迁移后 `makemigrations --check --dry-run` 无漂移，全部 migration leaf 已应用。

## 备份与数据保护

迁移前生成了本地生产备份：

- BackupRecord：`01KZDRFDY0SHZREP1C5B404Q40`
- 周标识：`2026-W32`
- 状态：`COMPLETED/local`
- 归档大小：`5,421,747` bytes
- 数据库 dump：`5,166,054` bytes
- 媒体文件：`13` 个，共 `1,311,063` bytes
- SHA-256：`20cad234a382e1d17ebc8ce97a8d622f4d77303e97761782a983f9092cb0c4ca`
- `pg_restore --list`：通过

本次是应用层增量切换：数据库、Redis、Umami、Mailpit 容器和生产数据卷未重建、未清空、未替换；媒体目录、静态文件目录和备份目录仍使用原生产挂载路径。只暂停了后台 worker/beat 完成迁移窗口，随后使用候选镜像恢复运行。

## 发布后验证

- `https://kajspace.cn/health/live`：HTTP 200，`{"status":"live"}`
- `https://kajspace.cn/health/ready`：HTTP 200，`{"status":"ready"}`
- Web、Worker、Beat、Caddy：均运行 `d53ebe0` 候选镜像并通过容器状态检查。
- 公开主页、文章正文、登录页和搜索页：HTTP 200。
- 真实文章封面媒体：HTTP 200，`image/png`，Caddy 静态媒体代理可读。
- 静态 JS/CSS：HTTP 200。
- 未登录文章页：点赞、收藏、阅读书签按钮保留登录跳转，不向匿名用户开放写入。
- 生产数据库账户、文章、修订、媒体和评论记录仍可正常读回；新功能表初始为空，等待用户正常使用产生记录。

本公告记录的是一次不影响现有生产内容的增量发布，不代表已执行生产数据恢复演练；备份归档的 `restore_verified` 仍按系统策略保持为 `false`。
