# TipTap 正文 Schema 与渲染合同

状态：富文本增强 R0 的跨层合同。实现事实由 `apps/media/rendering` 持有；`content` 保存 schema version 并调用稳定入口；`authoring` 只配置同一合同对应的 TipTap extensions 和 commands。

## 1. 版本与兼容

| 版本 | 用途 | 写入策略 | 读取策略 |
| --- | --- | --- | --- |
| `1` | 当前历史 TipTap revision | 不再由新保存产生 | 原样校验并按 v1 渲染，无需改写历史 revision |
| `2` | 富文本增强后的当前版本 | 新建或保存 TipTap revision 时规范化后写入 | 按 v2 严格校验并渲染 |

- Markdown revision 不使用 TipTap schema version，数据库值必须为空。
- 打开 v1 revision 时编辑器使用兼容 extensions；首次保存产生新的 v2 revision，旧 revision 保持不可变。
- 未知版本关闭失败，不尝试按最新版本猜测。
- schema version 是 revision 元数据，不写进 TipTap `doc` 顶层 attrs，也不根据节点内容猜测。
- renderer/sanitizer/schema 版本共同进入公开正文缓存身份；任一合同变化都不能复用旧 HTML。
- 当前统一实现版本为 `kaj-tiptap-renderer-v7` 与 `kaj-html-v7`；renderer 只消费 schema owner 的规范化结果，不维护第二份 node/mark/attrs 校验白名单。

## 2. 全局结构限制

| 限制 | v1 | v2 | 失败码 |
| --- | ---: | ---: | --- |
| UTF-8 规范化 JSON 最大值 | 2 MiB | 2 MiB | `media.tiptap.source_limit.v1` |
| 节点总数 | 10,000 | 10,000 | `media.tiptap.structure_limit.v1` |
| 最大嵌套深度 | 100 | 100 | `media.tiptap.structure_limit.v1` |
| 单个 text 长度 | 2 MiB 总量内 | 2 MiB 总量内 | `media.tiptap.text_invalid.v1` |
| 单节点重复 mark | 禁止 | 禁止 | `media.tiptap.mark_invalid.v1` |
| 未声明字段/属性 | 禁止 | 禁止 | `media.tiptap.attributes_invalid.v1` |

规范化 JSON 固定使用 UTF-8、`ensure_ascii=false`、紧凑分隔符和对象键排序。规范化不重排 block、list item、table row、mark 或用户文字；只删除合同明确允许省略且值为空的可选属性。

### 性能与可观测预算

- 上表 2 MiB、10,000 节点、100 层深度与表格 50 行/20 列/1,000 单元格均是服务端硬门禁；边界值接受，超过任一值返回对应稳定 422，不截断、不依赖浏览器提示。
- 当前低内存单实例的正文投影目标为 250 ms。该值是慢渲染告警预算，不是假装可取消的事后超时；输入仍先受硬容量限制，超过预算的成功渲染保持正确结果并记录 warning。
- `apps/content/rendering.py` 计时但不自行拼日志，统一调用 operations 的稳定指标入口。每条只包含 content format、render mode、schema version、规范化 source bytes、node count、max depth、table cells、duration、outcome、稳定 error code 和当前 trace code。
- 指标不得接受或记录正文、剪贴板内容、URL、标题、文件名、媒体 ID、用户 ID、数据库 ID、路径或异常消息。成功与拒绝都记录，因而可从同一维度计算失败率；非法或无界指标字段由 operations 拒绝。

## 3. 节点合同

符号：`block*` 表示零个或多个 block；`inline*` 表示零个或多个 inline；`text+` 表示一个或多个 text 节点。

| node | 版本 | 允许父节点 | content | attrs |
| --- | --- | --- | --- | --- |
| `doc` | v1/v2 | root | `block*` | 无 |
| `paragraph` | v1/v2 | block 容器 | `inline*` | 无 |
| `heading` | v1/v2 | block 容器 | `inline*` | `level: int`，`1..6`；v2 可选唯一 `anchor: kaj-h-<UUID>` |
| `text` | v1/v2 | inline/codeBlock | 无 | `text: str`；可含 marks |
| `hardBreak` | v1/v2 | inline 容器 | 无 | 无 |
| `blockquote` | v1/v2 | block 容器 | `block*` | 无 |
| `bulletList` | v1/v2 | block 容器 | `listItem+` | 无 |
| `orderedList` | v1/v2 | block 容器 | `listItem+` | 可选 `start: int >= 1`，默认 `1` |
| `listItem` | v1/v2 | bulletList/orderedList | `block+` | 无 |
| `codeBlock` | v1/v2 | block 容器 | `text*` | 可选 `language`；v2 仅受控枚举 |
| `horizontalRule` | v1/v2 | block 容器 | 无 | 无 |
| `image` | v1/v2 | block/inline 容器 | 无 | `src: media:<ULID>`；可选 `alt/title`；v2 可选 `width` |
| `taskList` | v2 | block 容器 | `taskItem+` | 无 |
| `taskItem` | v2 | taskList | `block+` | `checked: bool` |
| `callout` | v2 | block 容器 | `block+` | `kind: info/warning/success` |
| `table` | v2 | block 容器 | `tableRow+` | 无 |
| `tableRow` | v2 | table | `tableHeader/tableCell+` | 无 |
| `tableHeader` | v2 | tableRow | `block+` | 无 |
| `tableCell` | v2 | tableRow | `block+` | 无 |
| `attachment` | v2 | block 容器 | 无 | `src: media:<ULID>`；无客户端路径/文件名 |
| `embed` | v2 | block 容器 | 无 | `source` 与 `url`；必须匹配服务端可信来源策略 |
| `latexBlock` | v2 | block 容器 | 无 | `formula: str`；仅块级公式源码，浏览器 KaTeX 渲染，禁止自定义宏 |

`block` 集合为 paragraph、heading、blockquote、bulletList、orderedList、codeBlock、horizontalRule、image，以及 v2 的 taskList、callout、table、attachment、embed、latexBlock。列表和 callout 可包含普通 block，但 table、attachment、embed 和 latexBlock 不允许递归嵌入自身。

`latexBlock.formula` 只做 UTF-8、控制字符、单块 `16 KiB` 和单文档 `200` 块限制；服务端不执行公式语法校验，因此错误公式仍可保存。公开 HTML 输出带有转义后的原始 `$$...$$` 回退文本和源码属性。浏览器端使用 KaTeX 的 `throwOnError`、`trust: false`、`strict: "error"` 配置渲染；渲染失败或检测到 `newcommand`、`def`、`DeclareMathOperator` 等自定义宏时，保持原始公式文本，不生成部分 HTML。

### 标题锚点与大纲

- v2 heading 的持久锚点只允许小写 `kaj-h-<UUID>`，同一 document 内不得重复；v1 不接受该属性。
- 编辑器为缺失、非法或因复制而重复的锚点生成新值。改名、拖动和撤销/重做保留节点已有锚点；锚点不由标题文字 slug 化。
- 未带锚点的历史 v1/v2 revision 不回填数据库。renderer 按规范化 heading 节点和文档顺序生成确定性的 `kaj-h-legacy-<digest>`，同一不可变 revision 每次输出一致。
- H1-H6 大纲由规范化 JSON projection 生成；空标题的 projection 保留空文本，编辑器显示安全占位，公开 H2 目录可省略空条目但不能移除正文锚点。
- sanitizer 仅在 H1-H6 上保留上述两类安全 `id`，任意用户 `id`、事件属性和其他 HTML 属性仍被移除。公开 TipTap 页面不得解析 HTML 后重新编号标题。

### 图片宽度

v2 `image.width` 只允许 `25`、`50`、`75`、`100`，默认 `100`，表示编辑/阅读内容列的百分比。服务端输出受控数值属性；CSS 仍使用 `max-width: 100%` 和 `height: auto`。不得保存像素尺寸、任意 CSS、class 或 style。

### 代码语言

v2 首批允许：`text`、`bash`、`css`、`diff`、`html`、`javascript`、`json`、`markdown`、`python`、`sql`、`typescript`、`yaml`。空值规范化为 `text`；未知值保存时拒绝，历史 v1 未知值按纯文本降级且不得加载远程高亮脚本。

### 表格限制

- 最多 50 行、20 列、1,000 个单元格。
- 每行单元格数量必须一致；首行可以全部是 `tableHeader`，其余行只能是 `tableCell`。
- 首版没有 colspan、rowspan、嵌套 table 或数据库语义；公式只支持独立块，不支持行内 `$...$`。
- 超限或畸形结构返回 `media.tiptap.table_invalid.v1`，不自动补齐或截断。

## 4. Mark 合同

| mark | 版本 | attrs | 输出语义 |
| --- | --- | --- | --- |
| `bold` | v1/v2 | 无 | `strong` |
| `italic` | v1/v2 | 无 | `em` |
| `strike` | v1/v2 | 无 | `s` |
| `underline` | v1/v2 | 无 | `u` |
| `code` | v1/v2 | 无 | 行内 `code` |
| `link` | v1/v2 | `href: str`；可选 `title: str` | 安全 `a` |

- 同一 text node 的 mark 类型不得重复。
- 规范化保持 mark 数组的用户语义顺序；renderer 使用固定优先级产生确定 HTML。
- `link.href` 只允许站内相对地址，以及 `http`、`https`、`mailto`；拒绝协议相对 URL、反斜线开头、控制字符、用户信息和显式端口。
- 外部 HTTP(S) 链接由 sanitizer 添加 `target="_blank"` 与 `rel="noopener noreferrer"`。
- v2 保存、预览和发布遇到危险链接返回 `media.tiptap.link_invalid.v1`；历史 v1 的同类链接只保留可读文字并移除 `href`，不执行、不回填旧 revision。

## 5. 媒体、附件与嵌入

- `image.src` 和 `attachment.src` 只保存规范化 `media:<ULID>`；renderer 还必须接收对应 revision 的允许 ID 集合。
- 上传中的 pending/progress/error/cancel/retry 仅是编辑器临时状态；临时节点和 `kaj-upload:` 引用不得进入 ArticleSnapshot 或 revision。
- 图片 ID 必须属于 revision 的 BODY bindings；附件 ID 必须等于 revision 的唯一 ATTACHMENT binding。两个集合不能互换。
- 未知、非 ACTIVE、未绑定或越权 ID 使保存/发布失败；只读历史内容遇到后来不可用资产时输出一致的安全降级，不泄露 storage key。
- attachment node 不保存文件名、绝对路径、MIME 或大小；公开展示通过 media owner 的授权元数据组装。
- 同一 TipTap document 最多一个 attachment node；重复节点返回 `media.tiptap.attachment_invalid.v1`。卡片文件名、类型和大小只从当前 revision 的授权附件绑定注入，不能由正文 attrs 覆盖。
- embed 仅保存 source/url，renderer 调用 `TrustedEmbedPolicy`；不接受任意 iframe、HTML 或服务器无界抓取。
- 首批唯一来源是 `bilibili`：只接受无凭据、无显式端口、无 query/fragment 的 `https://www.bilibili.com/video/BV...`，策略规范化尾部斜线并自行生成 `player.bilibili.com` 地址。编辑器不加载 iframe，预览与阅读出口才消费策略生成的 sandboxed iframe 和规范化站外链接。
- 严格入口（新保存、作者预览、终稿审查和发布）要求正文图片属于允许 BODY 集合、附件等于允许 ATTACHMENT，且 embed 当前受信；不匹配时返回稳定错误，sanitizer 不再静默删除后宣称成功。
- 公开历史读取对后来失效的图片/附件输出不含 ID 或路径的安全占位；已认可来源的合法历史 embed 降级为策略规范化的站外链接，未知来源与非法 URL 不回显。纯文本摘要和 TipTap 便利导出显式使用非文本资源省略投影。所有策略都复用同一规范化、renderer 和 sanitizer，不改变 revision 事实。

### 文章出口投影

`apps/content/rendering.py` 统一返回 sanitized HTML、纯文本、sanitizer version、底层 cache key 与 Markdown block start lines。content 内只有该文件可以调用 media 的正文 renderer；各出口必须显式选择以下模式：

| 模式 | 出口 | 资源语义 |
| --- | --- | --- |
| `STRICT` | 新保存校验、作者预览、终稿审查与发布 | 图片、附件或 embed 不满足当前允许策略时拒绝 |
| `READER` | 公开文章与历史版本 | 可用资源正常输出；失效图片/附件为不泄露 ID 的占位，已认可 embed 为规范安全链接 |
| `SUMMARY` | 自动摘要与搜索列表 | 图片、附件和 embed 不进入纯文本摘要 |
| `EXPORT` | TipTap `body.md` 便利副本 | 保留原 `body.tiptap.json`，便利纯文本省略非文本资源 |

公开正文缓存继续使用 revision ID、generation 与 `content_rendering_version()`；该版本组合 sanitizer、TipTap schema fingerprint、renderer version 和 embed policy fingerprint。任何一项变化都使旧正文缓存身份失效。

### 粘贴、导入与导出

- TipTap 编辑器中的 Markdown 粘贴使用项目锁定版本的官方 `@tiptap/markdown` parser，结果仍需通过当前 ProseMirror schema；不得用字符串替换维护第二套 Markdown 解析器。
- 剪贴板 HTML 必须在进入 schema 前执行显式 allowlist 清洗。脚本、iframe、可执行/表单类元素、事件属性、class、style、危险链接和未通过现有媒体 owner 上传的图片不得进入编辑文档；合法附件和 embed 也只能从本项目受控 data attrs 恢复并再次通过既有策略校验。
- 纯文本不含明确 Markdown 语法时保持普通文本粘贴。剪贴板含图片文件时由现有正文图片上传 owner 优先处理，HTML 中的远程图片不能绕过上传、权限、绑定和 revision 生命周期。
- TipTap revision 导出始终把 `body.tiptap.json` 作为唯一无损事实。并列 `body.md` 明确标记为 lossy convenience copy，保留标题、段落、列表、代码围栏和表格的可读边界，省略图片、附件和 embed 等非文本资源，也不得暴露内部媒体 ID。
- 便利 `body.md` 可以作为新的 Markdown 导入输入，但导入结果是显式的新 Markdown 文章内容，不承诺还原 TipTap 节点、marks、锚点或资源；原 revision 与原始 JSON 不被转换或覆盖。

## 6. 错误合同

| 错误码 | 含义 | content 映射 |
| --- | --- | --- |
| `media.tiptap.root_invalid.v1` | 根不是合法 doc | `content.body_invalid.v1` |
| `media.tiptap.version_invalid.v1` | schema version 未知或格式不匹配 | `content.body_invalid.v1` |
| `media.tiptap.node_invalid.v1` | node/type/content 形状错误 | `content.body_invalid.v1` |
| `media.tiptap.node_unsupported.v1` | 当前版本不支持 node | `content.body_invalid.v1` |
| `media.tiptap.attributes_invalid.v1` | 字段、attrs 或值非法 | `content.body_invalid.v1` |
| `media.tiptap.mark_invalid.v1` | mark 形状、重复或属性非法 | `content.body_invalid.v1` |
| `media.tiptap.structure_limit.v1` | 节点数、深度或表格结构超限 | `content.body_invalid.v1` |
| `media.tiptap.source_limit.v1` | 规范化 JSON 超正文上限 | `content.body_too_large.v1` |
| `media.tiptap.media_invalid.v1` | 图片/附件引用非法或未获允许 | `content.media_invalid.v1` |
| `media.tiptap.link_invalid.v1` | 链接协议或形状非法 | `content.body_invalid.v1` |
| `media.tiptap.embed_invalid.v1` | 嵌入来源或 URL 非法 | `content.body_invalid.v1` |
| `media.tiptap.table_invalid.v1` | 表格结构或容量非法 | `content.body_invalid.v1` |

浏览器只显示 content 层安全中文文案；日志、审计、事件、通知和指标最多记录错误码、schema version、节点计数和 trace code，不记录正文、URL、文件名或路径。

content owner 固定映射：`media.tiptap.source_limit.v1 -> content.body_too_large.v1`、`media.tiptap.media_invalid.v1 -> content.media_invalid.v1`，其余 TipTap 合同错误映射为 `content.body_invalid.v1`。作者预览以 HTTP 422 返回安全中文文案，并通过 `X-Kaj-Error-Code` 暴露对应 content 错误码；异常消息不得拼接 node 名、URL、媒体 ID 或正文片段。

## 7. 跨层同步门禁

新增或改变任何 node/mark/attr 时，必须在同一可验证切片中更新：

1. 本合同和 `apps/media/rendering` schema owner。
2. TipTap extension 与 command registry 的可用/激活/禁用状态。
3. JSON 规范化、ArticleSnapshot、ArticleRevision schema version 与不可变保存。
4. renderer、sanitizer、媒体/附件 allowlist、缓存身份和错误映射。
5. 编辑预览、终稿审查、发布、公开文章、历史版本、搜索摘要和导出。
6. 旧 v1、新 v2、非法输入、容量、权限、XSS、数据库读回和真实浏览器测试。

任何出口没有实现时，新节点不得由编辑器产生；不允许以静默删除、旧缓存或纯文本假降级宣称支持。
