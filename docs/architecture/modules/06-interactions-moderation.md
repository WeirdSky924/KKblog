# F. 评论、留言与举报

所有者：`apps/comments` 拥有讨论线程和评论树；`apps/moderation` 拥有举报、申诉、文章管理案件和裁决。两个 app 通过公开服务协作。

## 内部目录

```text
apps/comments/
  models/{thread,comment}.py
  services/{posting,replies,deletion,publication}.py
  policies/{thread_access,comment_commands}.py
  queries/{public_thread,author_management,admin_management}.py
  tasks/publication.py
apps/moderation/
  models/{report,report_appeal,article_case,article_appeal}.py
  services/{reports,report_appeals,article_actions}.py
  policies/{case_access,appeal_eligibility}.py
  queries/{review_queues,case_detail}.py
```

## 评论聚合

DiscussionThread 的目标仅 ARTICLE/GUESTBOOK。Comment 保存 parent/root/depth、author kind、状态、visible_at、reply_count 和受限 IP。评论正文最多 100 字；顶层最多三图，回复无图。

状态 BUFFERED → VISIBLE → DELETED；所有评论创建后缓冲 10 分钟。删除清空公开正文、立即删图片、保留节点和子回复；文章物理删除才物理删整个线程。

## 权限与冷却

- 访客在文章/留言板允许且无需登录时只能发顶层评论，显示名固定“访客”。
- 登录用户可顶层、回复、举报和删除自己评论，不能编辑。
- 文章作者可管理自己文章评论；管理员管理全站和留言板。
- 访客 5 分钟、登录用户 1 分钟冷却；IP Block 拒绝所有互动。
- 关闭评论区只阻止新建，既有缓冲评论仍按时公开，既有评论继续显示。

## 排序和加载

默认顶层/回复最早在前；可选最新、最热门（reply_count）。顶层每批 20 自动触底加载；每个回复链先 10，每次展开再 10。排序偏好只存浏览器。深度无限，超过 100 对拥有者只告警一次。

## 举报与申诉

首次举报要求登录、每人每目标一次：必选标签、可选 200 字、最多三图。初审成立对外删除占位并通知两方；失败通知举报人。举报人身份永不提供给被举报方。

初审失败只有举报人可申诉一次；成立只有被举报用户可申诉一次。申诉 200 字/三图，复审终局。初审删除到终局前，恢复所需内容只在 moderation 私有快照保存；终局成立后销毁正文快照，案件元数据永久。

管理员直接删除任何评论为终局，无申诉；可填原因，通知已登录评论作者/文章作者并去重，访客不通知，永久审计。

## 文章管理案件

管理员隐藏或删除他人文章创建 ArticleModerationCase；作者可申诉一次。准许时委托 content 恢复原状态，拒绝为终局。moderation 不直接更新 Article 私有字段。

## 留言板

留言板复用 DiscussionThread，owner 是管理员。默认开启且访客可顶层留言；管理员配置关闭/登录要求并接收深层提醒。禁止复制第二套 GuestbookComment 模型或审核规则。

## UI

文章/留言板评论树、作者缓冲 tab/按文章管理、管理员评论管理、举报审核、证据详情、申诉和直接删除弹窗。所有列表保护举报人/IP，详情按权限揭示。

## 验证

缓冲不提前公开、双 Worker 幂等、关闭后既有缓冲公开、删除占位/子回复、树深告警、冷却、访客限制、举报唯一/隐私、申诉 eligibility/终局、初审恢复快照、管理员通知去重、账户/文章删除收敛。

施工依据：`data/03-interaction-operations-fields.md`、`flows/03-comment-moderation-state-machine.md`、`contracts/02-authorization-matrix.md`。
