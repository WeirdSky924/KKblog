# G. 作者工作台

所有者：`apps/authoring` 只拥有编辑会话、展示 DTO 和页面编排；文章/版本属于 content，媒体属于 media，评论属于 comments，导入 Job 属于 exchange。

## 内部目录

```text
apps/authoring/
  services/{editor_session,local_draft_contract}.py
  queries/{article_workspace,version_timeline,comment_workspace}.py
  presentation/{article_views,editor_views,comment_views,import_views}.py
  presenters/{editor,conflict,review,versions}.py
  templates/authoring/{articles,editor,review,versions,comments,import}/
  static/authoring/{editor_bridge,local_draft}.js
  tests/{presenters,flows}/
```

不创建 authoring Article/Draft/Comment 表。若编辑会话令牌需要服务端记录，它只保存短期会话元数据，不成为正文事实。

## 编辑器边界

- 新建时作者选择 Markdown 或 TipTap；普通编辑不可切换。
- 两种编辑器共用标题、摘要、封面、可见性、分区、标签、评论设置、媒体、单附件和终稿预览。
- 附件选择器只向拥有独立附件能力的作者显示；服务端保存重新裁决。能力撤销后可保留当前工作修订已有附件，但不能新增或更换。
- 桌面实时并列预览；手机编辑/预览分段切换。
- 预览调用与最终发布相同 sanitizer，不执行原始 HTML。

## 本地与云草稿

内容变化 debounce 后存浏览器，键含 user/article/base revision/format。只有点击“保存草稿”才调用 content `save_revision` 写云端。页面恢复先加载本地，没有再加载云 working revision，无需弹窗。

成功发布、手动删除对应云草稿或浏览器数据清除时删除本地稿。请求失败/异常退出不能删除。管理员可只读查看他人工作修订并通知作者，但 authoring 编辑入口永不授予管理员代编能力。

## 并发冲突

保存携带 base revision 与 row version。409 后停止继续编辑，展示当前工作版本、用户基线和历史元数据；作者选择新基线后覆盖编辑画布并取得新令牌。未解决冲突不能保存/发布，发布版本不受影响。

## 发布审查

实时预览不是终稿审查。作者从编辑器进入完整文章审查，可返回编辑；确认时必须选择立即或定时。退出未确认审查保留为草稿。恢复历史版本也先创建新工作修订，再走同一审查/发布。

“编辑已发布文章自动重发”是作者账户偏好：显式保存修订成功后可自动进入发布服务，但仍执行完整校验和版本创建；首次发布和历史恢复仍要求终稿审查。

## 作者评论管理

两个首版 tabs：10 分钟缓冲中的卡片、按文章分组的评论入口。作者可关闭自己文章评论区、删除任何评论/回复并保留占位，不可编辑评论。预留 tab 注册点但不显示空功能。

## 导入编排

上传、预览、逐篇 SKIP/UPDATE/CREATE、分区/标签映射、确认和结果均由 authoring 页面呈现，实际解析/Job 在 exchange、写文章在 content、图片在 media。跨作者 ID 禁止更新/新建；疑似同标题只警告。

## UI 状态

我的文章覆盖已发布、工作草稿、定时和删除冷静期。编辑页显示本地保存、云保存 pending/失败、格式、正文用量/当前配置上限（默认 2 MiB）、媒体限制、冲突和磁盘门禁。所有离开/发布/删除动作保留用户输入并有正确确认。

## 验证

两格式创建/预览；本地优先与云回退；保存失败不丢稿；成功发布清理；冲突选择基线；旧发布版本稳定；移动端键盘/工具栏；终稿返回/立即/排期；恢复新版本；评论 tabs；导入 partial success。

施工依据：`contracts/03-frontend-contract-map.md`、`flows/02-article-state-machine.md`、`flows/04-import-export-sequences.md`。
