# 页面、身份与状态施工矩阵

状态：实现前端的唯一页面验收补充；不是第二套路由或业务契约。

## 使用规则

1. 路由、服务和权限以 `docs/architecture/contracts/03-frontend-contract-map.md`、`01-application-services.md` 和 `02-authorization-matrix.md` 为真值。
2. 原型 HTML/截图只提供视觉基线和复合页面示例；本矩阵补齐原型未单独展示的路由、身份、状态和视口。
3. 每个页面至少验证 390px、1440px；管理密集页面追加 768px。编辑器手机必须能在“编辑/预览”之间切换。
4. 所有写动作均需观察 pending、成功、422 字段错误、系统错误、权限/禁用、取消和恢复；异步动作必须观察真实 Job 状态。
5. 发生冲突时，需求最终口径 > 架构契约 > 本矩阵 > 原型视觉 > 原型演示代码。

## 通用状态配置

| 代码 | 必须可观察的行为 |
| --- | --- |
| `S0` | 首次加载或 HTMX pending，重复提交被禁用，焦点保持在触发动作 |
| `S1` | 有数据成功态，显示真实持久化读回和下一动作 |
| `S2` | 空态，说明对象状态并给出一个可用主动作；不伪造示例数据 |
| `S3` | 字段校验 422，错误紧邻字段并保留用户输入 |
| `S4` | 系统/依赖错误，显示安全文案和 trace；提供重试或返回路径 |
| `S5` | 无权、禁用、登录要求或隐私 404；不得泄露对象存在性 |
| `S6` | 确认弹窗、取消、成功反馈、焦点恢复和重复提交保护 |
| `S7` | 异步进行中、失败、最终失败、取消竞态或恢复后读回 |

## 公共、阅读与身份页面

| URL name | owner | 入口身份 | 必测状态 | 原型基线 |
| --- | --- | --- | --- | --- |
| `public:home` | discovery | 访客/用户/作者/管理员 | S0,S1,S2,S3,S4,S5；分页/筛选 | home |
| `public:section` | discovery | 全部 | S0,S1,S2,S4,S5；未知/删除分区 | home |
| `public:tag` | discovery | 全部 | S0,S1,S2,S4,S5；0/1/5 标签 OR | home |
| `public:search` | discovery | 全部 | S0,S1,S2,S3,S4,S5；文章/作者、空查询/分页；即时建议仅登录可用且最多五条 | home |
| `article:detail` | discovery | 全部 | S0,S1,S2,S4,S5；登录提醒/404/目录、右侧点赞、置顶评论 | article |
| `article:bookmark` | discovery | 用户/作者/管理员 | S0,S1,S3,S4,S5；重复点击 | account |
| `article:like` | discovery | 用户/作者/管理员 | S0,S1,S3,S4,S5；匿名跳登录、重复点击、计数同步 | article |
| `article:comment-pin` | comments | 文章作者/管理员 | S0,S1,S4,S5,S6；替换/取消、首屏重排、游标去重 | article |
| `public:profile` | discovery | 全部 | S0,S1,S2,S4,S5；禁用/删除账户 | account |
| `public:about` | navigation | 全部 | S1,S2,S4,S5；空页隐藏入口 | publicstates |
| `public:friend-links` | navigation | 全部 | S0,S1,S2,S4；缺图/恶意 URL | publicstates |
| `public:guestbook` | comments | 全部 | S0,S1,S2,S3,S4,S5,S6,S7；关闭/登录要求 | publicstates |
| `public:not-found` | core | 全部 | S4；统一 404、无内部对象差异 | publicstates |
| `accounts:login` | accounts | 访客 | S0,S1,S3,S4,S5,S6；密码/邮箱码/30 天/回跳 | auth |
| `accounts:register` | accounts | 访客 | S0,S1,S2,S3,S4,S5,S6；开关/邀请码/自动登录 | auth |
| `accounts:password-reset` | accounts | 访客 | S0,S1,S3,S4,S5,S6；第五次错误/每日限制 | auth |
| `accounts:settings` | accounts | 用户/作者/管理员 | S0,S1,S2,S3,S4,S5,S6；昵称/邮箱/密码/主题 | personalsettings |
| `accounts:sessions` | accounts | 用户/作者/管理员 | S0,S1,S2,S3,S4,S5,S6；指定退出/全退出 | account |
| `accounts:bookmarks` | discovery | 用户/作者/管理员 | S0,S1,S2,S4,S5；失效文章占位 | personalsettings |
| `notifications:list` | notifications | 用户/作者/管理员本人 | S0,S1,S2,S4,S5,S6；单条/全部已读 | account |
| `question-banks:index` | learning | 全部 | S0,S1,S2,S3,S4；搜索/筛选/四种排序/分页 | 新增 learning |
| `question-banks:detail` | learning | 全部 | S0,S1,S4,S5；隐藏/删除 404、题面/答案/解析、答题登录返回 | 新增 learning |
| `learning:documents` | learning | 有附件能力作者本人 | S0,S1,S2,S3,S4,S5,S6,S7；逐次声明、上传、审核终态、删除恢复 | 新增 learning |
| `learning:document-detail` | learning | owner/管理员受控例外 | S0,S1,S2,S3,S4,S5,S6,S7；原文、访问历史、申诉/重审 | 新增 learning |
| `learning:bank-generate` | learning | 有附件能力 owner | S0,S1,S2,S3,S4,S5,S6,S7；题型 Switch、完整/部分/失败 | 新增 learning |
| `learning:quiz-start` | learning | 登录用户 | S0,S1,S2,S3,S4,S5,S6；题型/题量/随机/计时 | 新增 learning |
| `learning:quiz-attempt` | learning | 登录本人 | S0,S1,S3,S4,S5,S6,S7；自动保存、跨设备、软超时、提交 | 新增 learning |
| `learning:wrong-book` | learning | 登录本人 | S0,S1,S2,S3,S4,S5,S6；掌握切换/错题练习 | 新增 learning |
| `learning:records` | learning | 登录本人 | S0,S1,S2,S3,S4,S5,S6,S7；详情/复选删除/清空/CSV | 新增 learning |

## 作者工作台

| URL name | owner | 入口身份 | 必测状态 | 原型基线 |
| --- | --- | --- | --- | --- |
| `authoring:articles` | authoring | 作者 | S0,S1,S2,S4,S5；发布/草稿/定时/冷静期 | authorlist |
| `authoring:create` | authoring | 作者 | S0,S1,S3,S4,S5,S6；Markdown/富文本/导入三选一，空白格式一经选择不可改 | editor |
| `authoring:edit` | authoring | 作者 | S0,S1,S3,S4,S5,S6,S7；本地/云保存/磁盘/冲突 | editor |
| `authoring:review` | authoring | 作者 | S0,S1,S3,S4,S5,S6,S7；返回/立即/定时 | editor |
| `authoring:versions` | authoring | 作者 | S0,S1,S2,S4,S5,S6；预览/恢复新修订 | editor |
| `authoring:comments-buffer` | authoring | 作者 | S0,S1,S2,S4,S5,S6,S7；10 分钟倒计时 | authorops |
| `authoring:comments-article` | authoring | 作者 | S0,S1,S2,S3,S4,S5,S6；树/占位/关闭 | authorops |
| `authoring:import` | authoring | 作者/管理员作为作者 | S0,S1,S2,S3,S4,S5,S6,S7；创建入口、预览/部分成功、单篇进入编辑 | authorops/exchange |

`authoring:create/edit` 的 S7 同时覆盖剪贴板图片上传：单图/多图顺序、原光标位置替换、上传中保存与离页保护、Markdown/TipTap 撤销、失败清理、图片库刷新，以及普通文本粘贴不被拦截。临时 `kaj-upload:` 引用不得进入本地稿或提交内容。

## 管理页面

| URL name | owner | 入口身份 | 必测状态 | 原型基线 |
| --- | --- | --- | --- | --- |
| `admin:users` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；搜索/角色/禁用/删除 | users |
| `admin:ip-blocks` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；掩码/详情/解封 | users |
| `admin:articles` | administration | 管理员 | S0,S1,S2,S4,S5,S6,S7；查看通知/隐藏/删除/恢复 | moderation |
| `admin:comments` | administration | 管理员 | S0,S1,S2,S4,S5,S6,S7；缓冲/文章/直接删除 | moderation |
| `admin:reports` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6,S7；证据/隐私/终局 | interactive-report |
| `admin:tags` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；通过/驳回/恢复冲突 | adminrecords |
| `admin:sections` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；唯一/未知分区 | adminrecords |
| `admin:invites` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；1..1000/原码一次显示 | notifications |
| `admin:notifications` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6,S7；群发/回执/隐藏/删除 | notifications |
| `admin:navigation` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；三层拖拽/键盘替代/冲突 | settings |
| `admin:site-settings` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6；品牌/法律页/可信来源/留言 | settings |
| `admin:exchange` | administration | 管理员 | S0,S1,S2,S3,S4,S5,S6,S7；导出/取消/过期/下载 | exchange |
| `admin:audit` | administration | 管理员 | S0,S1,S2,S3,S4,S5；关键字/类型/目标/时间 | operations |
| `admin:errors` | administration | 管理员 | S0,S1,S2,S3,S4,S5；trace/脱敏/未找到 | operations |
| `admin:tasks` | administration | 管理员 | S0,S1,S2,S4,S5,S7；运行/成功/终败/无手动重试 | operations |
| `admin:analytics` | administration | 管理员 | S0,S1,S4,S5；同源代理/不可直连 | operations |
| `admin:agent-endpoints` | administration/ai-config | 管理员 | S0,S1,S2,S3,S4,S5,S6,S7；参数/启停/检查/token reset/秘密不回显 | 新增 learning-admin |
| `admin:agent-profiles` | administration/ai-config | 管理员 | S0,S1,S2,S3,S4,S5,S6；Prompt Markdown/历史/切换/409 | 新增 learning-admin |
| `admin:learning-documents` | administration/learning | 管理员 | S0,S1,S2,S3,S4,S5,S6,S7；分页/逐条原文/申诉/显式批量 | 新增 learning-admin |
| `admin:question-banks` | administration/learning | 管理员 | S0,S1,S2,S3,S4,S5,S6,S7；配额/运行/处置/显式批量 | 新增 learning-admin |
| `admin:question-bank-api` | administration/learning | 管理员 | S0,S1,S2,S3,S4,S5,S6；开关/限流/CORS/用量 | 新增 learning-admin |

## 原型收口

当前原型的 17 个复合视图和 21 张截图保留为视觉参考，不宣称覆盖本矩阵的 42 个路由。实现前必须处理以下已知差异：

- Header 访客/登录态互斥，补个人通知控件和独立管理员通知入口。
- 手机编辑器实现编辑/预览分段切换，不以隐藏预览代替功能。
- 弹窗实现焦点锁、Escape、触发点恢复和键盘提交。
- 三主题使用同一语义 token；暗色弹窗、表单和错误状态不得出现低对比度。
- 管理密集页补 768px 和手机横向导航可达性；不把截图中的空白或溢出当设计要求。
