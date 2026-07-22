# C. 文章、版本与分类

所有者：`apps/content`。它拥有 Article、不可变 Revision、发布/删除状态、分区、标签和当前分类投影；不拥有文件字节、举报案件或管理页面。

## 内部目录

```text
apps/content/
  models/{article,revision,section,tag,projections}.py
  services/{articles,revisions,publication,deletion,classification}.py
  policies/{article_access,article_commands,admin_exception}.py
  queries/{reader,author,admin,classification}.py
  events/{schemas,handlers}.py
  tasks/{publication,purge}.py
  presentation/           # 仅内容自身的窄 HTTP 入口
  tests/
```

编辑器页面归 authoring，首页归 discovery，管理员表单归 administration；它们都委托 content service/query。

## 聚合设计

- Article 的 author 永不转移；公开 ID 为 ULID。
- working/published/scheduled revision 三指针分离；Revision 创建后不可更新。
- Revision 完整保存标题、正文、格式、封面、可见性、分区、标签和评论设置。
- publication、soft deletion、管理员隐藏、作者禁用是正交状态；后两者来自 moderation/account policy。
- 普通编辑格式不可改；Markdown 导入/历史恢复是记录原因的例外。

## 服务

新建、保存修订、终稿预览、立即/定时发布、取消排期、重发、可见性变更、恢复版本、软删除/恢复、到期清理准备、分区 CRUD、标签提议/审核/删除/恢复。

管理员隐藏/文章申诉案件由 moderation 拥有，但通过 content 服务应用/解除查询遮罩。管理员删除/恢复他人文章走 content 命令并强制通知/审计。

## 查询

- Reader query 只返回当前 published revision 且满足可见性/遮罩。
- Author query 返回本人工作、发布、排期和冷静期状态。
- Admin query 可返回任意状态，但策略生成他人查看事件。
- 分类 query 使用当前发布投影；未知分区不进入分区导航。

禁止提供不带 actor 的万能 Article QuerySet 给页面。

## 关键规则

- 默认大众、草稿、评论开启、评论查看/顶层发布无需登录。
- 标题最多 30 字可重复；正文序列化默认最大 `2 MiB`，管理员只能在 `64 KiB` 至 `2 MiB` 内配置。
- 发布普通文章必须一个分区；最多十标签；作者待审标签立即显示。
- 发布后编辑不改变读者版本；作者按设置显式或自动重发，但都创建新修订。
- 版本恢复先完整预览、创建新修订，再按普通发布流程。
- 软删除 7 天可恢复；到期正文/修订/媒体/评论物理清理，案件/审计保留。

## 事件与任务

ArticlePublished/VisibilityChanged/SoftDeleted/Restored/PurgeRequested/AdminViewed、TagReviewed、SectionDeleted。定时发布与到期清理扫描数据库事实，任务幂等，不依赖长期 ETA 消息。

## 页面/交互

模块提供 DTO 给我的文章、编辑/预览、发布审查、版本时间线、公共详情、分类列表和管理员文章管理。409 冲突返回版本选择 DTO；私人/草稿无权读取统一 404。

## 验证

- 编辑/恢复已发布文章时读者仍读旧 published revision。
- 两个同 row version 保存只有一个成功；冲突不改发布指针。
- 定时发布二次验证作者、修订、遮罩和状态；双 Worker 只发布一次。
- PUBLIC/AUTH/PRIVATE × 身份 × 对象状态完整矩阵。
- 分区删除转未知、标签删除/恢复关联、十标签并发约束。
- 管理员查看按日通知，不能伪造请求编辑/发布他人内容。

施工依据：`data/01-er-model.md`、`data/02-identity-content-fields.md`、`flows/02-article-state-machine.md`。
