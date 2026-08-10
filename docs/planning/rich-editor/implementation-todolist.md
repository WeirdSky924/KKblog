# Kaj 富文本增强实施 Todo List

状态：实施完成；R0-R5 共 29 条 Todo 全部完成。

来源：[语雀式富文本编辑能力规划](yuque-inspired-feature-plan.md)。本清单是 P0-P12 完成后的独立增强包，不改写 `docs/planning/implementation-todolist.md` 的历史完成事实。

## 1. 目标与执行规则

- 目标：在现有 TipTap 3、`TIPTAP_JSON`、ArticleRevision、media owner 和统一安全渲染链路上，交付适合 Kaj 的 block 富文本编辑体验。
- 状态只使用：`待处理`、`进行中`、`阻塞`、`完成`；任何时刻只能有一条任务为 `进行中`。
- 顺序：严格按 R0 -> R5 推进；每项先满足前置，再执行聚焦 RED、最小完整实现、GREEN、相关回归和证据回写。
- 唯一事实：TipTap JSON 仍是富文本正文唯一编辑源；预览、发布、公开查看、历史版本和导出必须复用服务端 renderer/sanitizer。
- 非目标：实时多人协作、AI 写作、白板、思维导图、复杂数据库块、任意插件和任意 iframe。
- 授权：本清单不授权 Git 提交/推送、生产迁移、部署、服务重启、真实外发或数据清理；执行时仍以用户当前回合授权为准。

## 2. 阶段与依赖

| 阶段 | 范围 | Todo | 退出门禁 |
| --- | --- | ---: | --- |
| R0 | 契约与编辑器骨架 | 5 | 旧文兼容，非法 schema 明确拒绝，统一 command registry 可用 |
| R1 | 高频文字格式 | 4 | 文字格式跨编辑、预览、保存、发布和查看一致 |
| R2 | Block 操作与结构块 | 6 | Slash、block handle、拖拽和结构块可稳定撤销恢复 |
| R3 | 表格与媒体工作流 | 5 | 表格、图片、附件和上传状态形成权限与生命周期闭环 |
| R4 | 大纲、嵌入与阅读一致性 | 4 | 导航、嵌入和所有阅读出口语义一致 |
| R5 | 工作流增强与交付收口 | 5 | 草稿、冲突、版本、性能、安全和全用户流回归通过 |

合计：6 个阶段，29 条 Todo。

## 3. R0 契约与编辑器骨架

### RE-001 固化节点、Mark 与属性契约
- 元数据：状态 `完成`；阶段 R0；owner `media/rendering`，authoring 只消费；优先级 P0。
- 目标：建立当前与目标 node/mark/attrs/schema version 表，明确未知节点、非法属性、深度、节点数和文本长度的错误语义。
- 依赖：无；后续 `RE-002`、`RE-003`、`RE-004`。预计文件：`apps/media/rendering/tiptap.py`、内容 revision 契约、架构文档。
- 边界/影响：不接受任意 HTML，不在前端定义第二份服务端事实；若 schema version 需要数据字段或 migration，必须单独取得授权。
- 验收：契约表覆盖现有旧文章和 R1-R4 目标节点；依赖、默认值、兼容与拒绝策略无空项。风险/停止：无法确认旧 revision 兼容方式即停止。
- 证据：新增 `docs/architecture/contracts/06-tiptap-schema.md`，固定 v1 历史只读/v2 当前写入、21 个节点、6 个 Mark、12 个安全错误码、属性和容量限制、媒体/附件/嵌入边界及跨层同步门禁；同时把该合同链接回 media/rendering owner 文档。当前代码核对覆盖 `tiptap.py` 的 12 个历史节点、`10,000` 节点/`100` 深度限制、6 个 Mark 以及 Revision、preview/save/publish/read/export/cache 调用链。新鲜静态读回为 `nodes=21`、`marks=6`、`errors=12`、`todos=29`、`active=RE-001`，各命令退出 0；`git diff --check` 退出 0。本项只固化合同，不声称运行时代码已支持 v2 节点；未执行 migration、Labs 同步、Git 提交或推送。

### RE-002 实现 schema version 与规范化序列化
- 元数据：状态 `完成`；阶段 R0；owner `content`；优先级 P0。
- 目标：为富文本 revision 建立版本化、确定性的 JSON 规范化入口，保存前拒绝前后端未共同支持的节点。
- 依赖：前置 `RE-001`；后续 `RE-003`、`RE-004`、`RE-005`。预计文件：content model/service、authoring form/bridge。
- 边界/影响：旧 revision 无需破坏性回填即可读；不得把浏览器生成 HTML 当正文事实；缓存 key 必须包含渲染契约版本。
- 验收：等价输入产生稳定 JSON；旧版读、新版写、非法版本和并发保存均有测试与数据库读回。风险/停止：需要直接改写历史 revision 即停止重评。
- 当前证据：临时 RED 先以 `ModuleNotFoundError: apps.media.rendering.tiptap_schema` 退出 1，确认版本化 schema owner 缺失；实现 `tiptap_schema.py`、`ArticleRevision.tiptap_schema_version`、expand/backfill/constraint migration `0013`，并把 create/save、visibility clone、restore、preview、publish、public read、summary、cache identity 和 export 调用链接入显式版本。确定性探针读回 `schema_version=2 deterministic=ok input_immutable=ok invalid_versions=5 unknown_node=blocked legacy_read=ok current_write=strict`，退出 0。隔离 PostgreSQL 从 `0012` 插入历史 TipTap 后前进到 `0013`，读回 `legacy_version=1 markdown_version=null current_version=2 invalid_shapes_rejected=3 normalized_readback=ok`；migration 结束后不可变 trigger 为 `O`，约束同时含 `IN (1,2)` 与 `IS NOT NULL`。完成审计追加旧v1编辑页RED，先以 `preview_from_form() got an unexpected keyword argument 'tiptap_schema_version'` 退出 1；编辑会话版本传入初始预览后同一探针退出 0，历史未知代码语言可读而新输入仍按v2严格处理。`test_cnt002.py` 为 `10 passed`，media renderer 为 `22 passed`，完整 content 回归为 `68 passed`，migration contract 为 `5 passed`；目标 Ruff lint/format、Django check、migration drift 和 `git diff --check` 均退出 0。临时数据库与探针已定向清理。获得当前回合授权后，在 `resource_gate=yellow`、`concurrency=1` 下执行 Labs `content.0013`，迁移退出 0；共享测试库读回 `migration=1`、`MARKDOWN/NULL=13`、`TIPTAP_JSON/v1=3`、非法形状均为 0、约束完整且不可变 trigger 为 `O`。定向同步 22 个运行时文件并逐一核对 SHA-256 一致；`kaj-labs.service` 保持 `active/running`，live health、首页及一篇历史 TipTap v1 文章均为 HTTP 200，页面含渲染正文且近 10 分钟无 warning 日志。未执行生产 migration、服务重启、Git 提交或推送。

### RE-003 对齐 renderer、sanitizer 与错误合同
- 元数据：状态 `完成`；阶段 R0；owner `media/rendering`；优先级 P0。
- 目标：让解析、校验、渲染、sanitizer 和公开输出共享 node/mark/attrs 规则及稳定 422 错误码。
- 依赖：前置 `RE-001`、`RE-002`；后续全部功能节点。预计文件：`tiptap.py`、`html_policy.py`、preview/content service。
- 边界/影响：链接协议、媒体 ID、嵌入来源、代码语言均由服务端裁决；错误不得回显正文、原路径或秘密。
- 验收：预览 HTML 与发布/公开 renderer 一致；未知节点、危险链接和越权媒体明确失败而非静默丢弃。风险/停止：任一出口仍有独立渲染规则即停止。
- 当前证据：确认旧 renderer 仍维护第二份 v1 node/mark/attrs 白名单，v2 危险链接会被 sanitizer 静默移除 `href`，未授权图片会被静默删除。临时 RED 以 `expected media.tiptap.link_invalid.v1` 退出 1；改为 renderer 只消费 schema 规范化结果，安全 URL 与媒体 ID 规范化由 sanitizer owner 共享，补齐 v2 task/callout/table/image width/attachment/trusted embed 输出、固定 Mark 渲染优先级、严格/占位/纯文本省略三种明确资源投影，并以 `kaj-tiptap-renderer-v2`、`kaj-html-v3` 和 schema fingerprint 共同分隔缓存。GREEN 探针读回 `re003-render-contract=ok`、`re003-compat-errors=ok`，退出 0；覆盖危险 v2 链接、越权图片/附件、不受信 embed、未知 node 脱敏、v1 安全降级和三类 content 错误映射。隔离 PostgreSQL 临时集成用例 `1 passed`，读回合法 revision 为 schema v2，并证明终稿审查 HTML 与发布后公开读取 HTML 完全一致；危险链接在保存和预览均为 `content.body_invalid.v1`。当前最终代码相关回归合并为 `94 passed in 108.27s`（media renderer 22、完整 content 68、公开阅读 4）；目标 Ruff lint/format、Django check、migration drift 与 `git diff --check` 均退出 0，临时 PostgreSQL/Redis/探针已定向清理。`resource_gate=yellow`、`concurrency=1` 下定向同步 Labs 16 个运行时文件并逐一核对 SHA-256；服务保持 `active/running`，live health 和历史 TipTap v1 文章为 HTTP 200，无 warning 日志。`blog-playwright-cli` 以访客在 1440/390 打开该文章，语义 article/正文 region 可读，控制台 0 error/0 warning，390 下 `scrollWidth=375 <= clientWidth=390`，会话已关闭。Labs 没有可公开操作的新 v2 结构块入口，该浏览器生成流由后续对应功能 Todo 验收；未执行新 migration、服务重启、生产动作、Git 提交或推送。

### RE-004 建立 schema 兼容与安全回归基线
- 元数据：状态 `完成`；阶段 R0；owner `media/rendering` tests；优先级 P0。
- 目标：先用 RED 固化旧文章、未知 node/mark、非法 attrs、超限文档、XSS、媒体越权和版本漂移行为。
- 依赖：前置 `RE-001`；与 `RE-002`、`RE-003` 共同 GREEN；后续全部阶段。
- 边界/影响：使用隔离 PostgreSQL、临时媒体和项目原有测试入口；不连接生产或共享测试数据。
- 验收：失败原因准确，GREEN 后包含真实 revision 保存/读回和公开渲染；不得只靠 snapshot 或 mock。风险/停止：测试无法证明经过真实 owner 入口即重写测试。
- 当前证据：新增独立 `apps/media/tests/test_tiptap_contract.py` 与 `apps/content/tests/test_tiptap_contract.py`，并把 `article_revision_tiptap_schema_shape` 纳入既有 migration 合同；覆盖 v1 历史读取、未知 node/mark、非法 attrs、重复 Mark、深度/UTF-8 源大小、XSS、危险链接、媒体 capability、越权媒体、schema version 漂移、真实 revision 保存/文件读回/发布/公开渲染。持久安全基线首轮准确 RED：DEL 控制字符链接未抛 `TipTapSchemaError`，目标用例失败；另一个 alt 断言确认为已转义文本的测试误报并修正。实现安全 URL 对全部 Unicode `Cc` 控制字符的拒绝，并在 text/link/title/image/code/embed 属性边界把非法 UTF-8 映射到稳定 TipTap 错误，GREEN 新纯合同测试为 `21 passed`，新增未知 mark 后纳入最终回归。真实 PostgreSQL+临时媒体测试为 `2 passed`：v2 revision/schema、ACTIVE 文件、发布与公开 HTML、越权媒体回滚均读回；手工持久化 v1 revision 的危险链接安全降级、缺失媒体占位和数据库 v3 约束拒绝均成立。当前最终相关回归为 `118 passed in 115.25s`，空库/当前库 migration 合同为 `5 passed in 33.31s`；目标 Ruff lint/format、Django check、migration drift、`git diff --check` 均退出 0。隔离 PostgreSQL 基库、pytest 测试库、Redis DB 13 和临时媒体均定向清理读回为空。`resource_gate=yellow`、`concurrency=1` 下同步 Labs `html_policy.py`、`tiptap_schema.py` 并核对 SHA-256；目标端 DEL 探针返回 `media.tiptap.link_invalid.v1`，服务保持 `active/running`，live health 与历史 v1 文章为 HTTP 200，近 5 分钟无 warning。此项无新前端入口，未重复浏览器矩阵；未执行新 migration、服务重启、生产动作、Git 提交或推送。

### RE-005 重构 command registry 与响应式工具栏骨架
- 元数据：状态 `完成`；阶段 R0；owner `authoring`；优先级 P0。
- 目标：所有 toolbar、Bubble Menu、Slash Menu 和 block menu 共用 command registry、图标、状态、快捷键与权限元数据。
- 依赖：前置 `RE-002`；后续 R1-R3 全部 UI。预计文件：editor JS 模块、模板、样式、前端测试。
- 边界/影响：不把全部按钮平铺；390 宽度使用高频按钮加 More menu；按钮具有 active/disabled、tooltip、`aria-label` 和稳定尺寸。
- 验收：已有命令行为不回归，390/768/1440 无挤压或横向溢出，键盘焦点稳定。风险/停止：出现两套命令状态或 toolbar 直接拼 JSON 即停止。
- 当前证据：采用 `extract`，新增 `editor-commands.js` 作为 10 个现有命令的唯一元数据、状态、权限与执行入口，`editor-toolbar.js` 从同一 registry 生成文字/结构/历史分组及窄屏 More 菜单；原 editor bridge 和模板已移除重复命令分派与硬编码按钮。临时 RED 先因 `static/src/editor-commands.js` 缺失以退出 1，随后持久前端合同测试为 `3 passed`、退出 0；最终 `npm run build:js` 退出 0（`static/dist/app.js 579.1 KiB`），`npm run build:css`、Django check、`git diff --check` 均退出 0。隔离 PostgreSQL 中通过真实 content owner 创建 TipTap v2 revision，并由登录作者编辑页读回标题、正文和初始 active/disabled 状态；该任务不新增持久化合同。`blog-playwright-cli` 串行验证 1440/768/390 与浅色/深色/护眼三主题：1440/768 展示全部 10 个命令且隐藏 More，390 恰好展示粗体、斜体、H2、无序列表、撤销、重做并显示 More；页面和工具栏均无横向溢出。粗体点击后 `aria-pressed=true` 且输入同步到实时预览，撤销/重做禁用状态准确；More 可由 ArrowDown 直接进入首项，支持上下/Home/End，Escape 关闭并恢复触发器焦点，桌面隐藏按钮与菜单副本 active 状态一致。修正 Lucide `Ellipsis` 在局部和全局图标 owner 的登记后，最终浏览器为 0 error/0 warning。隔离数据库已定向删除、Redis DB 14 读回 0、临时媒体目录已移除。定向同步 Labs 8 个运行时文件并核对本地/目标 SHA-256 全部一致，公网 JS/CSS 哈希一致；服务保持 `active/running`，live health 为 200，作者入口未登录安全跳转且近 5 分钟无 warning。未执行生产动作、服务重启、Git 提交或推送。

## 4. R1 高频文字格式

### RE-101 扩展段落、H1-H6 与文字 Mark
- 元数据：状态 `完成`；阶段 R1；owner `media/rendering` + authoring adapter；优先级 P0。
- 目标：支持段落、H1-H6、粗体、斜体、删除线、下划线、行内代码、硬换行和清除格式。
- 依赖：前置 R0 全部；后续 `RE-102`、`RE-103`、`RE-401`。
- 边界/影响：每个 mark 必须同步 TipTap schema、服务端 renderer、sanitizer、active state 与旧文章兼容。
- 验收：组合格式、跨段选择、撤销/重做、保存/发布/历史/公开查看一致。风险/停止：服务端丢失浏览器可编辑格式即停止。
- 当前证据：采用 `extend`，TipTap StarterKit `3.28.0` 已以 MIT 许可提供 Paragraph、H1-H6、Underline、Code 与 HardBreak，无新增依赖；command registry 扩展到 20 个命令，正文/H1-H6 共用块类型菜单，桌面直接展示高频命令，390px 保留块类型、粗体、斜体、无序列表、撤销、重做和 More，清除格式由同一 registry 的 `unsetAllMarks + clearNodes` 驱动。持久前端合同初始 RED 为 `0/3`、退出 1，准确因文字命令缺失；最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `4 passed`、退出 0，并覆盖受编辑器裁切边界约束的菜单方向/高度计算。最终 `npm run build:js` 退出 0（`static/dist/app.js 585.2 KiB`），`npm run build:css`、Django check、migration drift、目标 Ruff lint/format 与 `git diff --check` 均退出 0；相关完整回归为 content TipTap `3 passed in 20.37s`、media TipTap `22 passed in 0.19s`。隔离 PostgreSQL 通过真实 revision/save/publish/public-read 链路读回 schema v2、sequence 2、working 指针命中，正文包含 H1-H6、bold/italic/strike/underline/code 与 hardBreak，终稿审查和公开 HTML 一致。`blog-playwright-cli` 串行验证 1440/768/390 与浅色/深色/护眼三主题：页面和工具栏无横向溢出，390 菜单在 8px 视口安全区内按编辑窗裁切边界限制高度；ArrowDown/Home/End/Escape 可达，内部滚动后标题 6/硬换行均可见且焦点恢复；受控键盘选区的顶部/菜单 active 状态同步，撤销/重做 `1→2→1→2→1`，刷新后 H1-H6 与五种 Mark、硬换行仍存在，最终干净会话为 0 error/0 warning。原尺寸工具栏/More 局部截图检查无按钮挤压、图标缺失、重叠或裁切。隔离数据库已删除，Redis DB 14 为 0，临时媒体、settings 与截图已精确移除。定向同步 Labs 4 个源码和 2 个构建产物并核对 SHA-256 全部一致，公网 JS/CSS 哈希一致；服务保持 `active/running`，live health 200，作者入口未登录安全跳转且近 10 分钟无 warning。未执行生产动作、服务重启、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning，不为本任务扩大 package 运行时语义。

### RE-102 实现安全链接编辑与移除
- 元数据：状态 `完成`；阶段 R1；owner `media/rendering` policy；优先级 P0。
- 目标：通过选区小型对话框添加、修改、打开和移除链接，保留 URL、标题和清晰错误状态。
- 依赖：前置 `RE-101`；后续 `RE-104`。预计文件：Link extension、dialog、协议校验、renderer tests。
- 边界/影响：只允许 `http`、`https`、`mailto` 及明确认可的内部协议；外链统一安全属性，不接受用户 HTML。
- 验收：键盘提交/取消/返回焦点、危险 scheme 拒绝、粘贴 URL、链接跨保存发布一致。风险/停止：前端校验可绕过或外链安全属性分叉即停止。
- 当前证据：采用 `extend + extract`，显式引入 MIT 许可的 `@tiptap/extension-link@3.28.0`，关闭 StarterKit 内置 Link 后由共享 `EDITOR_LINK_OPTIONS` 同时约束手动链接、自动识别与粘贴；新增原生 dialog 负责 URL/标题添加、修改、打开、移除、选区保持和直接工具栏/More 菜单焦点归还，独立 `editor-link-dialog.css` 是唯一样式 owner。持久前端合同先因缺少 `EDITOR_LINK_OPTIONS` 导出准确 RED、退出 1；最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `5 passed`、退出 0，覆盖安全 URL 与危险 scheme、userinfo、显式端口拒绝。最终 `npm run build:js` 退出 0（`static/dist/app.js 591.6 KiB`），`npm run build:css`、Django check、migration drift、目标 Ruff lint/format 与 `git diff --check` 均退出 0；media TipTap 回归 `22 passed`，真实 content 保存/发布/公开读取集成 `1 passed`。隔离 PostgreSQL 读回 published schema v2 revision、sequence 3、工作/发布指针一致，链接 attrs 精确保留 href/title；公开外链统一 `_blank` 与 `noopener noreferrer`。`blog-playwright-cli` 已验证键盘选区、初始 URL 焦点、非法输入不改正文、Enter 应用、Escape 归还焦点、已有链接修改/移除、保存刷新、审查发布和公开查看；1440 浅色、768 护眼、390 深色无横向溢出或按钮挤压。最终 390px More 菜单复核中弹窗相对 375px 内容视口精确居中，Escape 后焦点为可见 `SUMMARY[aria-label="更多格式"]`，控制台 `0 error / 0 warning`。隔离数据库已定向删除，Redis DB 14 为 0，临时媒体、脚本、状态和浏览器产物均已清理。`resource_gate=yellow`、`concurrency=1` 下定向同步 Labs 11 个源码/依赖/构建文件并逐一核对 SHA-256；公网 JS/CSS 哈希一致，服务保持 `active/running`，live health 为 200，未登录编辑入口安全跳转登录且近 5 分钟无 warning。未执行生产动作、服务重启、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-103 实现 Markdown 输入规则与键盘快捷键
- 元数据：状态 `完成`；阶段 R1；owner `authoring`；优先级 P1。
- 目标：`# `、`- `、`1. `、`> `、代码围栏和任务标记可在空 block 转换，并提供一致快捷键。
- 依赖：前置 `RE-101`；后续 R2 结构块。
- 边界/影响：只改变当前 block，不把 Markdown 模式文章转换成 TipTap；输入规则可撤销且不吞普通文本。
- 验收：中英文输入法、撤销、连续回车、段首/段中、移动端键盘行为。风险/停止：规则导致文本丢失或模式串扰即停止。
- 当前证据：采用 `extract + reuse`，新增 `editor-input-behaviors.js` 作为富文本输入行为 owner；复用现有 StarterKit 对标题、无序/有序列表、引用和代码围栏的官方规则，把已由 StarterKit 锁定的 MIT `@tiptap/extension-list@3.28.0` 提升为显式直接依赖并配置其 TaskList/TaskItem（nested 与中文 a11y label），未新增下载或平行 parser。自定义快捷键只补齐 `Mod-k` 链接入口，registry 中代码块提示由错误的 `Mod-Shift-Alt-0` 对齐 TipTap 实际 `Mod-Alt-c`；Markdown 模式不初始化这些扩展。持久前端合同先因缺少输入行为模块准确以 `ERR_MODULE_NOT_FOUND` RED、退出 1；最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `6 passed`、退出 0，`npm ls @tiptap/extension-list --depth=0` 精确读回 `3.28.0`。最终 `npm run build:js` 退出 0（`static/dist/app.js 592.1 KiB`），`npm run build:css`、Django check、migration drift 与 `git diff --check` 均退出 0；结构块 renderer/sanitizer 目标回归 `1 passed`。`blog-playwright-cli` 以真实逐键输入生成 `heading/bulletList/orderedList/blockquote/codeBlock/taskList`，连续回车退出结构块；段中 `普通 # 内容` 不误触发，规则后立即 Backspace 恢复 `# 保留普通标记`，中文 IME 式 `insertText` 保持 paragraph。选区 `Mod-k` 打开链接框并聚焦 URL，Escape 后编辑器焦点与选区恢复；空选区 `Mod-k` 被安全消费且不跳浏览器地址栏。发现官方 TaskItem 默认点击区仅 `13x19px` 后提取 `editor-task-list.css` 为编辑/服务端输出共享样式 owner，最终 390 编辑态为 `44x44px`。真实保存、终稿审查、立即发布和公开查看完成；CLI 发布点击仅超过 5 秒导航等待，但随后明确读回发布完成页。隔离 PostgreSQL 读回 `PUBLISHED/schema=2/sequence=3/working=published`，两条 taskItem 与普通 `# ` 文本精确保留；数据库已删除、Redis DB 14 为 0，临时媒体、状态、截图和脚本均已清理。390 浅色、768 护眼、1440 深色无页面级横向溢出，任务结构在编辑、审查和公开页一致，最终控制台 `0 error / 0 warning`。`resource_gate=yellow`、`concurrency=1` 下定向同步 Labs 9 个运行时/依赖/构建文件并逐一核对 SHA-256；公网 JS/CSS 哈希一致，服务保持 `active/running`，live health 200，未登录编辑入口安全跳转登录且近 5 分钟无 warning。未执行生产动作、服务重启、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-104 实现选区浮动工具条
- 元数据：状态 `完成`；阶段 R1；owner `authoring`；优先级 P0。
- 目标：选中文字后提供粗体、斜体、删除线、下划线、行内代码、链接和清除格式。
- 依赖：前置 `RE-101`、`RE-102`；后续 R5 全流回归。
- 边界/影响：不遮挡选区、固定顶部栏或移动输入法；空选区和只读状态不展示；与顶部工具栏状态同步。
- 验收：鼠标、键盘、触控、Escape、滚动、跨 block 选区和 reduced-motion。风险/停止：浮窗抢焦点造成选区丢失即停止。
- 当前证据：采用 `new + reuse`，新增 `editor-selection-toolbar.js` 作为浮动表面唯一 owner，只消费 command registry 的 7 个 bubble 命令并复用 `editorCommandState/runEditorCommand` 与既有安全链接对话框；没有复制 Mark 状态或命令。纯位置函数同时约束 visual viewport、编辑窗裁切、固定顶部栏、8px 安全区与选区上下空间，空间不足自动翻转并横向夹取；选区为空、无文本、只读、失焦、Escape dismiss 或滚出编辑窗时隐藏。独立 `editor-selection-toolbar.css` 固定 44px 图标按钮、稳定 318px 总宽、主题 token 和无动画状态。持久前端合同先因 owner 模块缺失准确以 `ERR_MODULE_NOT_FOUND` RED、退出 1；最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `7 passed`、退出 0。最终 `npm run build:js` 退出 0（`static/dist/app.js 596.5 KiB`），`npm run build:css`、Django check、migration drift 与 `git diff --check` 均退出 0。`blog-playwright-cli` 真实验证键盘单段与跨段选区、鼠标拖选、Tab/Shift+Tab、Escape、失焦、编辑窗滚动隐藏和链接 dialog 返回；Bold/Italic 经浮动条应用后顶部/浮动 active 状态同步，链接取消后下一命令仍作用于原选区，证明 selection 未丢。390 深色下浮动条宽 318px、按钮 `44x44px`、不覆盖选区或横溢；768 护眼+reduced-motion、1440 浅色同样不覆盖选区且无页面级横向溢出，原尺寸截图确认层级、间距和图标正常。保存刷新后 Bold/Italic 仍存在，隔离 PostgreSQL 读回 `DRAFT/schema=2/sequence=2/marks=bold,italic`；最终控制台 `0 error / 0 warning`。隔离数据库已删除，Redis DB 14 为 0，临时媒体、脚本、截图和浏览器产物均已清理。`resource_gate=yellow`、`concurrency=1` 下定向同步 Labs 6 个源码/构建文件并核对 SHA-256；公网 JS/CSS 哈希一致，服务保持 `active/running`，live health 200，未登录编辑入口安全跳转登录且近 5 分钟无 warning。未执行生产动作、服务重启、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

## 5. R2 Block 操作与结构块

### RE-201 实现可搜索 Slash Menu
- 元数据：状态 `完成`；阶段 R2；owner `authoring`；优先级 P0。
- 目标：空 block 输入 `/` 打开可搜索插入菜单，方向键选择、Enter 执行、Escape 关闭。
- 依赖：前置 R1 全部、`RE-005`；后续 `RE-202`、`RE-204`、`RE-205`。
- 边界/影响：菜单消费 command registry，不维护第二份能力列表；无权命令显示真实禁用/说明或不注册。
- 验收：查询过滤、无结果、中文输入法、滚动定位、焦点返回、命令失败不改正文。风险/停止：菜单文本残留正文或插入失败破坏 selection 即停止。
- 当前证据：采用 `new + reuse`，新增 `editor-slash-menu.js/.css` 作为 Slash 浮层唯一 owner，只消费 command registry 的 11 个块命令；registry 增加中文/英文搜索别名、用途说明及 prepared-chain 执行能力，正文内仅空 paragraph、末尾光标和单个 `/查询` 触发。命令以同一 TipTap transaction 删除查询并转换 block；Escape、无结果、IME composing 和失败路径不吞正文。初始持久前端合同因 owner 模块缺失以 `ERR_MODULE_NOT_FOUND` 精确 RED、退出 1；真实浏览器随后发现当前 paragraph 的“正文”仍 disabled，补充回归准确以 `disabled: true` RED、退出 1，根因为同类型 `setParagraph` 返回 false。最终 active 块类型在 Slash 上下文只运行 prepared transaction，聚焦用例与完整合同分别为 `1 passed`、`9 passed`，均退出 0。`npm run build:js` 退出 0（`static/dist/app.js 604.3 KiB`），`npm run build:css`、Django check、migration drift 与 `git diff --check` 均退出 0。`blog-playwright-cli` 真实验证 `/` 展示 11 项，中文“三级”与英文 `code` 单项过滤，Enter 转换、单次 undo 恢复完整 `/三级`、redo 重做，Escape 保留查询，无结果 Enter 不吞字，段中 `/` 不触发，鼠标点击引用与正文 active no-op 均成功；Home/End/方向键、`aria-expanded/controls/activedescendant` 一致。1440 浅色、768 护眼、390 深色均无页面级横向溢出，菜单保持视口/编辑窗/固定顶部栏边界内，选项最小高度 `61.75px`，reduced-motion 无动画，控制台 `0 error / 0 warning`。保存后隔离 PostgreSQL 读回 `TIPTAP_JSON/schema=2/sequence=3`，H3、codeBlock、blockquote 均存在且独立 `/` 不存在；专用数据库已删除、Redis DB 14 为 0，临时媒体、状态、脚本和浏览器产物均已清理。`resource_gate=yellow`、`concurrency=1` 下定向同步 Labs 7 个运行时/构建文件并逐一核对 SHA-256；公网 JS/CSS 哈希一致，服务保持 `active/running`，live health 200，未登录编辑入口安全跳转登录且近 10 分钟无 warning。未执行生产动作、服务重启、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-202 实现 block handle 与上下文菜单
- 元数据：状态 `完成`；阶段 R2；owner `authoring`；优先级 P0。
- 目标：当前/悬停 block 左侧显示拖拽手柄和独立菜单入口，支持转换、复制、删除、上移、下移。
- 依赖：前置 `RE-201`；后续 `RE-203`、`RE-206`。
- 边界/影响：拖动和菜单命中区域分离；只读、窄屏和触控有可操作替代；删除最后 block 后保留可编辑段落。
- 验收：嵌套列表、表格邻接、首尾 block、键盘菜单、取消和恢复焦点。风险/停止：菜单操作绕过 editor transaction 即停止。
- 当前证据：采用 `new + reuse`，新增 `editor-block-operations.js` 作为复制、删除、上移、下移及后续拖拽共同复用的单 transaction owner，`editor-block-menu.js/.css` 只消费该 owner 与 command registry；左侧选择手柄和菜单入口独立且均为 `44x44px`。持久前端合同先因菜单模块缺失以 `ERR_MODULE_NOT_FOUND` 精确 RED；浏览器验收又复现连续列表操作被陈旧 `hoveredIndex` 抢占、列表误标“正文”，补充标签合同后因缺少 `blockTypeLabelForDescriptor` 导出以退出 1 RED。最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `10 passed`、退出 0，覆盖真实 ProseMirror 顶层识别、嵌套列表整体移动/复制、selection 回落、唯一块删除和 390 菜单边界；文档 transaction 后清除陈旧 hover，顶层 node 从同一 registry 解析类型。`npm run build:js` 退出 0（`static/dist/app.js 615.9 KiB`），`npm run build:css`、Django check、migration drift 均退出 0。`blog-playwright-cli` 真实验证 ArrowUp/Down、Home/End、ArrowRight/Left、两级 Escape 与焦点恢复，正文转 H3 及 undo/redo，首尾 disabled、段落/标题/列表/引用/代码邻接、复制/移动/删除；列表复制后一次下移稳定跨过引用块，不再来回争夺。1440 浅色、768 护眼、390 深色均无页面横溢，菜单保持固定顶部栏、编辑窗和 viewport 边界内，reduced-motion 生效，控制台 `0 error / 0 warning`。保存后隔离 PostgreSQL 读回 `TIPTAP_JSON/schema=2/sequence=2`，顶层顺序为 `H3/H2/bulletList/blockquote/codeBlock/paragraph`；专用数据库已删除、Redis DB 14 为 0，临时媒体和浏览器产物已清理。定向同步 Labs 7 个运行时文件并逐一核对 SHA-256，公网 JS/CSS 哈希一致；服务保持 `active/running`，live health 200，未登录作者入口安全跳转登录且近 5 分钟无 warning。表格扩展尚未在编辑器 schema 中启用，表格邻接真实流在前置 `RE-301` 完成时使用同一 operation owner 补验；当前支持节点与任意顶层节点的纯 transaction 算法已覆盖。未执行生产动作、服务重启、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-203 实现稳定的 block 拖拽排序
- 元数据：状态 `完成`；阶段 R2；owner `authoring`；优先级 P0。
- 目标：拖动卡片浮起，其他 block 实时让位，使用稳定中线/滞回判断消除占位框闪烁和上下争夺。
- 依赖：前置 `RE-202`；后续 `RE-206`。
- 边界/影响：不采用反复删除/重建 placeholder 的双判定方案；自动滚动有界；取消拖拽恢复原位置。
- 验收：长文、快速跨多 block、边界停留、滚动容器、触控/键盘替代、撤销/重做。风险/停止：正文或 selection 丢失、位置振荡即停止。
- 当前证据：采用 `new + reuse`，新增 `editor-block-drag.js` 作为 PointerEvent、稳定中线/12px 滞回、单占位镜像预览、浮动块和每帧最大 16px 有界自动滚动 owner，放下时只调用 `editor-block-operations.js` 的 `moveTopLevelBlock()` 一次；拖动期间不写 ProseMirror 顶层 DOM 或 document transaction。聚焦 RED 先因 owner 模块缺失以 `ERR_MODULE_NOT_FOUND` 退出 1；最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `11 passed`、退出 0，覆盖中线、滞回、快速跨块顺序和滚动速度上限。`npm run build:js` 退出 0（`static/dist/app.js 622.4 KiB`），`npm run build:css`、Django check、migration drift 与 `git diff --check` 均退出 0。真实浏览器先发现直接给 ProseMirror 子节点写 class/order 会被 DOMObserver 重建，改为外部镜像层后同一原始节点在整个拖动中保持连接且身份不变；1440 浅色、768 护眼 reduced-motion、390 深色均无页面横溢，拖拽控件 `44x44px`，镜像/占位/浮块始终各 1 个且保持编辑窗、固定顶部栏和 viewport 边界。鼠标快速把首块移动到第 8 位，触控型 PointerEvent 把首块移动到第 3 位，均可一次 undo 完整恢复、一次 redo 完整重做；键盘块菜单下移及 undo 通过。真实边界 ±5px 往复 6 次占位不动，越过 16px 后才切换；320ms 边缘停留自动滚动 135px，Escape/pointercancel 后顺序恢复、预览节点清零并把焦点恢复到可见手柄或编辑器。保存并刷新后隔离 PostgreSQL 读回 `sequence=2/TIPTAP_JSON/schema=2/count=24`，前 12 块顺序与浏览器一致；控制台 `0 error / 0 warning`。专用数据库、Redis DB 14、Django/浏览器会话、临时媒体/状态/截图均已定向清理。定向同步 Labs 5 个运行时/构建文件并逐一核对 SHA-256，公网 JS/CSS 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200，未登录作者入口安全 302 且近 5 分钟无 warning。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-204 实现任务列表、提示块与分隔线
- 元数据：状态 `完成`；阶段 R2；owner `media/rendering`；优先级 P0。
- 目标：新增 taskList/taskItem、受控 callout 类型和 horizontalRule，并接入所有编辑入口与渲染出口。
- 依赖：前置 `RE-201`、R0 契约；后续 `RE-206`。
- 边界/影响：任务勾选是文章正文编辑，不在公开只读页产生写请求；callout 只使用受控类型/图标，不保存任意样式。
- 验收：嵌套、回车退出、退格合并、勾选、保存发布、sanitizer 和旧版兼容。风险/停止：公开阅读可修改 revision 即停止。
- 当前证据：采用 `reuse + new`，TaskList/TaskItem 继续复用现有 TipTap extension-list，HorizontalRule 复用 StarterKit，新增 `editor-structure-blocks.js/.css` 仅拥有受控 `info/success/warning` callout node、命令与跨编辑/阅读样式；全部入口消费既有 command registry，服务端继续复用 v2 schema、renderer 和 sanitizer。聚焦 RED 先因结构块 owner 缺失以 `ERR_MODULE_NOT_FOUND` 退出 1；最终前端合同 `12 passed`，media TipTap 安全回归 `22 passed`，JS/CSS build、Django check、migration drift 和 `git diff --check` 均退出 0。真实作者流通过 Slash 插入分隔线、创建两项任务并勾选第一项，连续两次 Enter 正确退出任务列表；三种提示块可原位切换类型且无嵌套，block 菜单可在同一 chain 中解除提示块，undo 恢复。保存、终稿审查、立即发布和公开查看成功；隔离 PostgreSQL published revision 读回 `sequence=3/schema=2/types=taskList,horizontalRule,callout,callout,callout,paragraph`、任务状态 `[true,false]`、callout 顺序 `[info,success,warning]`。公开页 checkbox 全部 disabled，强制 click 捕获到 `0` 个写请求；1440 浅色、768 护眼、390 深色均无横溢且三种提示块在 viewport 内，最终浏览器 `0 error / 0 warning`。专用数据库、Redis DB 13、Django/浏览器、临时媒体与状态均已清理。定向同步 Labs 11 个运行时/构建文件，公网 JS/CSS 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200 且近 5 分钟无 warning。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-205 增强代码块语言与复制能力
- 元数据：状态 `完成`；阶段 R2；owner `media/rendering`；优先级 P1。
- 目标：代码块支持受控语言选择、纯文本渲染和复制按钮，行内代码与代码块语义分离。
- 依赖：前置 `RE-201`、R0 契约；后续 `RE-206`。
- 边界/影响：不执行代码，不加载远程脚本；语言值来自受控枚举，未知值降级为纯文本。
- 验收：长代码、宽代码、特殊字符、复制 toast、语言切换和公开页一致。风险/停止：高亮路径可注入 HTML 即停止。
- 当前证据：采用 `extend + new`，显式锁定 MIT 许可的 `@tiptap/extension-code-block@3.28.0`，关闭 StarterKit 内置 CodeBlock 后由新增 `editor-code-block.js/.css` 统一拥有 12 种受控语言、NodeView、编辑/审查/公开页纯文本复制和共享 `kaj:feedback` 反馈；未引入高亮器、远程脚本或代码执行路径。聚焦 RED 因 owner 模块缺失以 `ERR_MODULE_NOT_FOUND` 退出 1；最终 `node --test tests/frontend/editor-command-registry.test.mjs` 为 `13 passed`、退出 0，`npm run build:js` 退出 0（`static/dist/app.js 629.1 KiB`），CSS build、Django check、migration drift 和 `git diff --check` 均退出 0，media/content TipTap 安全回归为 `25 passed`。真实浏览器先发现 NodeView 的无效 `updateAttributes` 回调使语言只视觉变化、JSON 未更新，改为通过 `getPos()` 和单个 `setNodeMarkup` transaction 后，`text -> python -> undo text -> redo python` 与隐藏 JSON 完全一致；编辑、终稿审查和公开页复制同一段 240 字符纯文本，`<script>` 保持文字且未生成脚本节点，长代码只在 block 内横向滚动。1440 浅色、768 护眼、390 深色均无页面级横溢，语言选择器与 `44x44px` 复制按钮可用，反馈为“代码已复制。”，最终控制台 `0 error / 0 warning`。隔离 PostgreSQL 读回 published revision `sequence=3/schema=2/language=python/text_length=240/literal_script=true`；v1 未知语言既有回归证明只按转义纯文本降级且不改写来源。专用数据库、Redis、临时媒体、服务和浏览器产物均已定向清理。定向同步 Labs 9 个源码/依赖/构建文件并逐一核对 SHA-256，公网 JS/CSS 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200，未登录作者入口安全 302 且近 5 分钟无 warning。离线 lock-only 复核因无关可选 Tailwind WASM 未缓存以 `ENOTCACHED` 退出 1，但锁文件根依赖、现有安装版本和生产 JS 构建均已证明 CodeBlock 依赖可解析；未为该缓存缺失执行在线安装。未执行生产动作、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-206 闭合 block 光标、事务与历史行为
- 元数据：状态 `完成`；阶段 R2；owner `authoring`；优先级 P0。
- 目标：统一回车、退格、合并、拆分、转换、拖拽、复制、删除后的 selection 与 undo/redo 语义。
- 依赖：前置 `RE-202`、`RE-203`、`RE-204`、`RE-205`；后续 R3-R5。
- 边界/影响：不以 DOM 查询代替 TipTap transaction；失败不产生空历史步骤。
- 验收：建立组合编辑状态机测试和真实浏览器长文流；刷新前后 JSON 与视觉顺序一致。风险/停止：任一命令产生不可撤销正文丢失即阻断后续阶段。
- 当前证据：采用 `reuse + new`，新增 `editor-history.js` 作为 history 分组边界 owner，块移动/复制/删除继续只由 `editor-block-operations.js` 产生正文 transaction，command registry 统一标记结构命令，Enter/Backspace 继续委托 TipTap 原生拆分、合并、列表和代码规则；成功结构动作与前后输入分组隔离，后置边界 transaction 不改正文且 `addToHistory=false`，失败 no-op 不派发 transaction。第一条聚焦 RED 在原有 `13 passed / 1 failed` 中证明一次 undo 会同时撤掉前置输入、移动和后置输入；第二条 RED 为原子分隔线复制后没有 `NodeSelection`；第三条真实浏览器 RED 证明默认 TrailingNode 与任务列表退出共同留下两个空段落，自动化合同又因缺少受控配置导出以 SyntaxError 退出 1。最终改为原子 block 使用 NodeSelection，普通/容器 block 使用最近可编辑 selection，并把标题、引用、三类列表、提示块和代码块列入受控 trailing-node 排除集合，只为需要兜底的原子块保留自动尾段落。`node --test tests/frontend/editor-command-registry.test.mjs` 最终 `17 passed`、退出 0，覆盖前置输入/结构动作/后置输入逐步 undo/redo、split/join、失败 no-op、原子 selection、中线拖拽和受控 trailing 配置；`npm run build:js` 退出 0（`static/dist/app.js 630.2 KiB`），media/content TipTap 安全回归 `25 passed in 16.14s`，Django check、migration drift 与 `git diff --check` 均退出 0。真实作者流验证 paragraph Enter/Backspace、正文转 H3、上下移动、复制、删除、任务列表两次 Enter 退出、任务勾选、callout 两次 Enter 退出、代码三次 Enter 退出、代码语言切换、分隔线复制及鼠标拖拽；所有结构动作都可一次 undo 和一次 redo，紧邻输入保持独立历史步骤，复制分隔线后真实 DOM 第 5 个顶层节点持有 `ProseMirror-selectednode`。保存并刷新后编辑 JSON 与 DOM 同为 `taskList/codeBlock/callout/horizontalRule/paragraph`，隔离 PostgreSQL 读回 `TIPTAP_JSON/schema=2/sequence=1/working_pointer=true/task_items=2/code_language=text/callout_kind=info/trailing_paragraphs=1`。1440 浅色、768 护眼、390 深色均无页面/编辑区横溢；390 下代码语言选择器 176px、复制和块控件均为 `44x44px`，键盘焦点可见，固定顶部栏保留，控制台 `0 error / 0 warning`。定向同步 Labs 7 个源码/构建文件并逐一核对 SHA-256，公网 `app.js` 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200，未登录编辑入口安全 302 且近 5 分钟无 warning。专用 PostgreSQL、Redis DB 11、临时媒体、脚本、状态、截图、浏览器和 Django 服务均已定向清理。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

## 6. R3 表格与媒体工作流

### RE-301 实现基础表格编辑
- 元数据：状态 `完成`；阶段 R3；owner `media/rendering` + authoring adapter；优先级 P0。
- 目标：支持插入表格、表头、增删行列、单元格导航和表格复制粘贴。
- 依赖：前置 R2 全部；后续 `RE-302`、`RE-305`。
- 边界/影响：首版不承诺复杂合并、公式或数据库表格；窄屏表格在正文内部滚动，不撑破页面。
- 验收：空表、长内容、宽表、键盘导航、保存发布和 390/768/1440。风险/停止：表格使页面级横向溢出或 JSON 无界增长即停止。
- 当前证据：采用 `reuse + new`，显式锁定 MIT 许可的 `@tiptap/extension-table@3.28.0`，由官方 Table/Row/Header/Cell extensions 负责表格事务；新增 `editor-table.js/.css` 统一拥有默认 cell attrs 规范化、上下文工具栏、受限定位和内部滚动，插入入口复用 command registry 并同时出现在 More 与 Slash Menu。聚焦 RED 先因 table owner 缺失以 `ERR_MODULE_NOT_FOUND` 退出 1；宽表阅读 RED 又证明 10 列在 390px 被压为约 34px 后，renderer 改为输出 sanitizer 受控的 `data-table-scroll="true"` 容器，并以 `kaj-tiptap-renderer-v3`、`kaj-html-v4` 失效旧缓存。真实浏览器覆盖 3x3 表格插入、表头切换、增删行列、Tab/Shift+Tab、末格 Tab 新增行、键盘菜单、选区复制粘贴、删除表格及 undo/redo；保存、刷新、终稿审查、两次发布和公开页语义一致。10 列长内容在 390/768/1440 的阅读容器分别为 `328→1121px`、`690→1121px`、`705→1121px`，每列 112px 且页面 `scrollWidth == clientWidth`；编辑器 390/768/1440 同样只在 tableWrapper 内滚动。上下文工具栏为 `198x44px`，主控均为 `44x44px`，行列菜单不越界，双层 Escape 关闭菜单/工具栏并恢复编辑焦点，键盘焦点和 reduced-motion 均有效，最终控制台 `0 error / 0 warning`。隔离 PostgreSQL 发布修订读回 `PUBLISHED/sequence=5/schema=2/3x10`、首行全 `tableHeader`、行宽一致、默认 attrs 为 0 且工作/发布指针一致。最终前端合同 `18 passed`，media/content 渲染回归 `48 passed`，JS/CSS build、Django check、migration drift、目标 Ruff lint/format、依赖读回与 `git diff --check` 均退出 0；Node 仅保留既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。定向同步 Labs 14 个运行时/依赖/构建文件并逐一核对 SHA-256，公网 JS/CSS 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200，目标 renderer 直接读回 `kaj-tiptap-renderer-v3/kaj-html-v4/wrapper=true`，匿名作者入口安全 302 且近 10 分钟无 warning。隔离 PostgreSQL、Redis DB 12、临时脚本/截图、浏览器和 Django 会话均已定向清理。未执行生产动作、服务重启、Git 提交或推送。

### RE-302 建立表格约束与安全渲染
- 元数据：状态 `完成`；阶段 R3；owner `media/rendering`；优先级 P0。
- 目标：限制行列、嵌套、深度和文本量，服务端验证 table/row/header/cell 结构并安全输出。
- 依赖：前置 `RE-301`；后续 R4 阅读一致性。
- 边界/影响：非法结构明确 422；不自动修复为另一张表而掩盖错误。
- 验收：畸形 JSON、超限表、XSS、复制 HTML、旧文章及公开渲染测试。风险/停止：浏览器与服务端限制不一致即停止。
- 当前证据：采用 `extract + enforce`，新增 `editor-table-contract.js` 作为前端表格约束 owner，并在服务端 `tiptap_schema.py` 导出同值的 `50 行/20 列/1000 单元格` 上限；前端 transaction filter、HTML paste 与增行列命令共同拒绝超限、嵌套、合并、空结构和不等宽表格，统一通过既有 `kaj:feedback` 提醒，服务端则把 table shell 畸形稳定映射为 `media.tiptap.table_invalid.v1`。聚焦 RED 分别因缺少服务端常量和前端合同模块失败；最终前端合同 `19 passed`、media 合同 `40 passed`、隔离 PostgreSQL content 合同 `5 passed`，JS build、Django check、migration drift、目标 Ruff lint/format 与 `git diff --check` 均退出 0。真实浏览器验证合法 2x2 HTML paste、21 列/嵌套/colspan 拒绝且 JSON 不变；合法边界 50x20 paste 后增行列控制禁用，末格 Tab 不越界并保留焦点，390 编辑页只在表格内部滚动。保存、刷新、终稿审查、发布和公开阅读保持同一结构；390/1440 公开页表格分别 `328→2241px`、`705→2241px`，页面无横向溢出。隔离 PostgreSQL 发布修订读回 `PUBLISHED/sequence=3/schema=2/50x20/1000`、首行全 header、正文全 cell、默认 attrs 为 0，工作/发布指针一致；篡改提交真实返回 422、显示通用正文错误且修订数仍为 3。定向同步 Labs 6 个运行时/构建文件并逐一核对 SHA-256，公网 JS 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200，目标端直接读回限制与嵌套错误码，匿名作者入口安全 302 且近 5 分钟无 warning。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-303 完善图片 block 工作流
- 元数据：状态 `完成`；阶段 R3；owner `media`；优先级 P0。
- 目标：统一选择、粘贴、拖入、替换、删除、alt/title 和受控显示尺寸，保持图片完整预览。
- 依赖：前置 `RE-206`、R0 媒体契约；后续 `RE-305`、`RE-502`。
- 边界/影响：只保存 `media:<ULID>`；复用现有正文图片库、上传限制、归属、引用删除和服务器文件生命周期。
- 验收：成功/失败/取消/重试、重复粘贴、离线、越权媒体、引用中删除、公开显示和媒体读回。风险/停止：删除节点直接误删仍被其他 revision 引用的文件即停止。
- 当前证据：采用 `extract + reuse`，新增 `editor-image.js/.css` 作为富文本图片节点、选中态工具条、信息对话框与受控宽度的唯一前端 owner；图片只保存 `media:<ULID>`、alt/title 与 `25/50/75/100`，编辑和阅读共同消费 `data-width`，未引入像素/style attrs。图片库选择和现有粘贴链路保持不变，正文拖入与原位替换继续调用既有 `article-body` 上传端点；替换成功前保留旧图片，成功后以单个隔离 transaction 更新 src，alt/title/width 不丢且 undo/redo 精确恢复。正文删除只删除当前 node 并明确保留图片库资源，服务器文件仍由 media binding/cleanup owner 裁决。持久前端合同先因缺少 owner 模块准确以 `ERR_MODULE_NOT_FOUND` RED、退出 1；浏览器首轮又发现局部 Lucide 扫描范围过大产生 61 warning 和遗漏 pending import 触发 `ReferenceError`，均收窄 owner 后复验。最终前端合同 `20 passed`、media TipTap 合同 `40 passed`、隔离 PostgreSQL content 合同 `5 passed`，JS/CSS build、Django check、migration drift 与 `git diff --check` 均退出 0。真实作者流覆盖图片库插入、alt/title、50% 宽度、原位替换、替换 undo/redo、合法拖入、非法图片 422 降级、正文节点移除、保存、终稿审查、发布和公开阅读；移除后图片库仍为 3 项。390/1440 公开图片分别为 `171.5/343px`、`360/720px`，无页面级横向溢出；768 护眼主题工具条 `148x44px`、三控件均 `44x44px`，对话框初始焦点、Escape 关闭与图片选区恢复正确，最终干净会话 `0 error / 0 warning`。PostgreSQL 发布修订读回 `PUBLISHED/sequence=3/schema=2`、工作/发布指针一致、唯一 image attrs 精确保留，并存在唯一 `article_revision` BODY binding。定向同步 Labs 7 个源码/构建文件并逐一核对 SHA-256，公网 JS/CSS 哈希一致；服务保持既定 worktree 的 `active/running`，live health 200，匿名编辑入口安全 302 且近 5 分钟无 warning。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-304 实现附件卡片 block
- 元数据：状态 `完成`；阶段 R3；owner `media` + content policy；优先级 P1。
- 目标：授权作者可把文章唯一附件作为可读卡片插入/定位，展示文件名、类型、大小和下载操作。
- 依赖：前置 `RE-206`、现有附件权限；后续 `RE-305`、`RE-502`。
- 边界/影响：继续限制单文章一个附件、10 MiB、zip/7z/rar/md/txt；未授权用户服务端拒绝，公开页只暴露安全下载名。
- 验收：有权/无权、替换、删除、版本恢复、404/失效降级和数据库/文件读回。风险/停止：附件 node 成为第二附件事实或绕过下载授权即停止。
- 当前证据：采用 `extend + reuse`，新增 `editor-attachment.js/.css` 作为富文本附件节点和编辑卡片 owner，只消费既有 `article-attachment` picker、账户附件能力与 media 上传端点；JSON 仍只保存 `src: media:<ULID>`。上传成功 upsert 唯一节点，重复“插入正文”只选中已有卡片，picker 替换只更新 src；删除正文卡片保留文章附件，移除 picker 才同步清除未保存节点。服务端 schema 新增最多一个 attachment node 的约束，重复结构稳定返回 `media.tiptap.attachment_invalid.v1`；renderer 接收独立 `TipTapAttachmentMetadata`，由 publication/reader/preview 从 media 授权结果注入文件名、受控类型与大小，正文无法伪造，并以 `kaj-tiptap-renderer-v4/kaj-html-v5` 失效旧缓存。前后端持久合同分别先以缺少 attachment owner 和 metadata export 精确 RED；最终前端合同 `21 passed`、media TipTap 合同 `41 passed`、隔离 PostgreSQL content 合同 `6 passed`，目标 Ruff lint/format、JS/CSS build、Django check、migration drift 与 `git diff --check` 均退出 0。真实授权作者流覆盖 TXT 上传自动插入、重复定位、正文卡片移除/恢复、两次替换、picker 移除同步、保存、篡改重复节点 422、终稿审查、发布、公开下载 200；编辑/审查/公开均显示 `re304-guide.txt / TXT / 90 B`，公开正文只保留一个嵌入卡片且不再重复底部附件块。390 公开卡片 `343px`、下载控件 `309x44px`，768 编辑卡片删除/下载控件高均为 44px且无横溢；未授权作者页面 picker/插入入口均为 0，最终干净会话 `0 error / 0 warning`。PostgreSQL 发布修订读回 `PUBLISHED/sequence=4/schema=2`、工作/发布指针一致、attachment 字段与唯一 node src、唯一 `article_revision/attachment` binding 完全一致，正文 node 不含名称/MIME/大小；替换产生的未绑定测试资产仍由既有孤儿生命周期管理。定向同步 Labs 20 个运行时/模板/构建文件并逐一比对，公网 JS/CSS 哈希一致；目标端直接读回完整卡片与重复节点错误码，服务保持既定 worktree 的 `active/running`、live health 200、匿名编辑入口安全 302且近 5 分钟无 warning。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-305 统一上传临时状态与清理语义
- 元数据：状态 `完成`；阶段 R3；owner `media`；优先级 P0。
- 目标：图片和附件统一 pending/progress/success/error/cancel/retry UI，浮窗反馈不挤压编辑布局。
- 依赖：前置 `RE-301`、`RE-303`、`RE-304`；后续 `RE-502`、`RE-505`。
- 边界/影响：临时节点不能保存进 revision；失败保留正文与 selection；孤儿媒体按现有生命周期清理且幂等。
- 验收：并发上限、重复请求、取消、刷新、网络失败、保存竞争和文件/数据库读回。风险/停止：UI 显示成功但 revision 或文件未绑定即停止。
- 当前证据：采用 `extract + reuse`，新增 `editor-upload-state.js/.css` 作为编辑器表单唯一上传状态 owner，图片 picker、粘贴、拖入、原位替换和附件 picker 共享 `pending/success/error/cancelled`、进度、AbortSignal、取消、同文件重试、关闭和 pending count；固定上传浮窗不挤压编辑布局。保存与 Markdown 覆盖在 pending 时由同一 owner 阻断；TipTap 失败保留原位占位且重试后原位替换，Markdown 失败移除临时标记，任何序列化正文都不含 `kaj-upload:`。真实作者流覆盖 held request、保存竞争、取消/重试、失败拖入、图片替换、附件上传和两图串行批次；390px 浮窗边界为 `12..363/390px`，可见操作为 `44x44px`，页面无横向溢出，控制台 `0 error / 0 warning`。隔离 PostgreSQL 保存 revision 读回 schema v2、7 个 image node、1 个 attachment node、0 个临时 token，并与 8 条 `article_revision` binding 和 10 个实际文件一致；两个替换前未绑定 ACTIVE 资源继续由既有孤儿生命周期管理。最终前端合同 `22 passed`、media 合同 `41 passed`、content 合同 `6 passed`，JS/CSS build、Django check、migration drift、目标 Ruff lint/format 与 `git diff --check` 均退出 0。未执行 production、服务重启、migration、Git 提交或推送。

## 7. R4 大纲、嵌入与阅读一致性

### RE-401 实现标题大纲与稳定锚点
- 元数据：状态 `完成`；阶段 R4；owner `authoring` + rendering projection；优先级 P0。
- 目标：从合法 H1-H6 节点实时生成大纲，点击定位，重复标题获得稳定且安全的锚点。
- 依赖：前置 `RE-101`、`RE-206`；后续 `RE-402`、`RE-404`。
- 边界/影响：不从渲染 HTML 反向解析正文；大纲只是 projection，不写第二份正文状态。
- 验收：重名/空标题、标题改名、拖拽、撤销、长大纲、键盘和移动折叠。风险/停止：锚点变化导致历史链接无策略失效即停止评审。
- 当前证据：采用 `extract + extend`，新增 `editor-outline.js/.css` 和显式 `@tiptap/extension-heading@3.28.0`；v2 heading 可保存唯一安全 `kaj-h-<UUID>`，缺失/非法/复制重复由同一 extension 修复，改名、移动和 undo/redo 保留锚点。服务端新增 JSON outline projection；旧 v1/v2 无锚点 revision 生成确定性 `kaj-h-legacy-<digest>`，renderer/sanitizer 升至 `kaj-tiptap-renderer-v5/kaj-html-v6` 并只在 H1-H6 保留安全 ID。发现并移除 discovery 对 TipTap sanitized HTML 的 H2 重编号，公开 TipTap 目录改为消费 content/media projection；Markdown H2 兼容路径不变。真实作者流覆盖 23 项长大纲、重名、空标题、改名、复制、真实拖动、undo/redo、保存和公开 fragment：复制后 24 个锚点仍唯一，redo 恢复同一新锚点，拖动后正文与大纲顺序一致；保存 revision 为 schema v2/sequence 2，数据库 24 个锚点、projection 和 rendered ID 完全一致。1440 浅色默认展开且 `516→1028px` 内部滚动；768 护眼和 390 深色默认折叠，展开高 192px，summary/条目均 44px，无页面横溢；Space/Enter/Tab 可达且定位后焦点回正文。公开 390 页面 24 个安全 ID、目录链接全部命中，fragment 目标位于粘性顶部栏下方；空正文显示“正文中暂无标题”，最终干净浏览器为 `0 error / 0 warning`。最终前端合同 `23 passed`、media/discovery `43 passed`、隔离 PostgreSQL content `6 passed`，JS/CSS build、Django check、migration drift、目标 Ruff lint/format、依赖读回与 `git diff --check` 均退出 0。定向同步 Labs 19 个运行时文件并逐一核对，公网 JS/CSS 哈希一致；服务保持规定 worktree 的 `active/running`，live health 和真实公开文章为 200，目标端读回 renderer/sanitizer 与重复标题 projection 正确；日志仅有热重载进程固有 development-server 提示。未执行 production、服务重启、migration、Git 提交或推送。

### RE-402 对齐编辑光标、预览和大纲定位
- 元数据：状态 `完成`；阶段 R4；owner `authoring`；优先级 P0。
- 目标：预览跟随当前编辑 block；内容不足以填充上方三分之一时从顶部开始，不产生顶部空白。
- 依赖：前置 `RE-401`；后续 `RE-505`。
- 边界/影响：使用文档位置映射而非文本模糊匹配；用户主动滚动预览时有明确暂停/恢复策略。
- 验收：首行、短文、长文、图片、表格、快速输入、撤销和不同视口。风险/停止：输入导致页面主体滚动或预览抖动即停止。
- 当前证据：采用 `extend + extract`，`editor-preview-scroll.js` 继续以 Markdown block start lines 或 TipTap selection/top-level block ratio 为唯一定位 owner，导出纯滚动数学与 `following/paused` 状态机合同；过滤 ProseMirror 浮动 block controls，不把 UI 当正文。目标位置为预览高度 2/3，scroll 始终 clamp 到 `0..maximum`；删除预览 `::before` 前置占位，内容不足时没有任何顶部伪留白。预览 wheel/touch/pointer/PageUp/PageDown 等主动操作切换为 paused，selection、快速输入、图片加载和预览 DOM 热更新都不隐式恢复，并按滚动比例保位；44px 定位图标显式恢复最新编辑位置，键盘激活后焦点回到预览 article。真实长文含 31 个标题、图片与 5x6 表格：首段及第 2 个标题分别在上方不足时保持 `scrollTop=0`；第 20 个标题、图片和表格当前单元格对 2/3 线误差分别 `0.13px/0.29px/命中单元格`。主动滚动后快速输入并完成预览请求仍保持 `scrollTop=2203`、页面 `scrollY=965` 不变，恢复后新标题误差 `0.06px`；undo/redo 不打断 following。768 分段预览命中目标误差 `0.14px`；390 下早期标题仍从顶部开始，PageDown 暂停后按钮 `44x44px`、顶部状态区无溢出，页面 `scrollWidth=375 <= 390`，恢复焦点正确；最终浏览器 `0 error / 0 warning`。最终前端合同 `24 passed`，JS/CSS build、Django check、migration drift 与 `git diff --check` 均退出 0。定向同步 Labs 6 个运行时文件并逐一核对；公网 JS/CSS 哈希一致，服务保持规定 worktree 的 `active/running`，live health 200，目标纯合同与恢复控件读回成功，匿名编辑入口安全 302且近 5 分钟无应用 warning。未执行 production、服务重启、migration、Git 提交或推送；Node 仍有既有 `MODULE_TYPELESS_PACKAGE_JSON` warning。

### RE-403 实现可信来源嵌入卡片
- 元数据：状态 `完成`；阶段 R4；owner `media/rendering` policy；优先级 P2。
- 目标：只为项目明确允许的来源提供卡片节点，并在来源不可用时展示安全降级链接。
- 依赖：前置 R0 契约、`RE-206`；后续 `RE-404`。
- 边界/影响：不允许任意 iframe、任意 HTML、带凭据 URL 或服务端无界抓取；新增来源必须单独登记策略与测试。
- 验收：allowlist、协议/主机混淆、失效、超时、只读、导出降级和 CSP。风险/停止：来源无法在无服务端抓取情况下安全呈现则延期而不兜底。
- 当前证据：采用 `extract + extend`，`TrustedEmbedPolicy` 成为来源解析、规范 URL、播放器地址、完整卡片和历史降级链接的唯一 owner；首批只接受无凭据/端口/query/fragment 的 `https://www.bilibili.com/video/BV...`，未知来源和非法 URL 从不回显用户输入。服务端不抓取远端；sanitizer 只在策略裁决后生成 sandbox/referrerpolicy/lazy iframe 与规范站外链接，并以 `kaj-tiptap-renderer-v6/kaj-html-v7` 失效旧缓存。新增窄 CSP middleware，在正常、403 与统一 500 响应固定 `frame-src 'self' https://player.bilibili.com`，不收紧现有 script/style。前端新增 `editor-embed.js/.css`：可拖动原子 card 只保存 `{source,url}`，More 菜单无选区可打开，插入/编辑/删除为独立可撤销事务；编辑器卡片不运行 iframe，停用来源历史卡片只读且可移除，命令禁用。聚焦 RED 为服务端 `17 failed` 与前端缺模块；最终 media/CSP `59 passed`、前端合同 `26 passed`、隔离 PostgreSQL content 合同 `7 passed`，JS/CSS build、Django check、migration drift、目标 Ruff lint/format 均退出 0。真实作者流覆盖恶意主机拒绝、尾斜线规范化、插入、编辑、删除、undo/redo、保存、终稿审查、发布和公开阅读；PostgreSQL 读回 `PUBLISHED/sequence=3/schema=2`、working/published 指针一致且 node 仅含规范 source/url。停用来源后公开页为 `0 iframe/1 fallback`、编辑卡片无编辑按钮且移除保留；便利导出省略嵌入而原 JSON 不变。1440/768/390 三主题无页面横溢，公开 iframe 维持 16:9；390 对话框边界为 `8.5..366.5/390px`，键盘 `ArrowDown→End→Enter` 可打开，Escape 回到 More summary。站内干净路径与停用降级均 `0 error/0 warning`；实际 Bilibili iframe 可播放但其自身 fingerprint 上报脚本产生第三方 console error，未归为本站错误。定向同步 Labs 17 个运行时文件并逐一核对 SHA-256；公网 JS/CSS 哈希一致，服务保持规定 worktree 的 `active/running`，live health `200`，匿名作者入口安全 `302` 且带精确 CSP，目标端 canonical/恶意主机/停用 fallback 与版本探针全部正确，近 10 分钟无 warning 日志。未执行 migration、production、服务重启、Git 提交或推送。

### RE-404 统一全部阅读与导出出口
- 元数据：状态 `完成`；阶段 R4；owner `content/media rendering`；优先级 P0。
- 目标：预览、终稿审查、公开文章、历史版本、搜索摘要和导出对同一 TipTap JSON 输出一致语义。
- 依赖：前置 `RE-302`、`RE-401`、`RE-403`；后续 R5 全部。
- 边界/影响：摘要可降级纯文本但不能运行独立 HTML sanitizer；renderer/schema 版本进入缓存失效合同。
- 验收：同一 revision 跨出口读回，旧缓存失效，媒体/附件/嵌入失败有一致降级。风险/停止：任一出口复制 node 规则即停止。
- 当前证据：采用 `extract + reuse`，新增 `apps/content/rendering.py` 作为文章正文出口投影唯一 owner，统一返回 sanitized HTML、纯文本、sanitizer version、底层 cache key 与 Markdown block lines；只由该 owner 调用 media renderer，并显式定义 `STRICT/READER/SUMMARY/EXPORT`。保存校验、作者预览、终稿审查与发布严格拒绝失效资源；公开和历史阅读输出不泄露 ID 的占位/可信 embed 安全降级；摘要与 TipTap 便利导出省略非文本资源且原 `body.tiptap.json` 不变。静态守卫禁止 content 其他模块直接调用 `render_markdown/render_tiptap`，纯文本解析也从 discovery 收归该 owner。聚焦 RED 为新 owner 不存在时收集失败（退出 2）；最终投影合同与同一 PostgreSQL revision 跨预览、审查、公开、历史、摘要、导出和缓存身份共 `9 passed`，content 全回归 `77 passed`，discovery/search/HTTP security `8 passed`。目标 Ruff lint/format、Django check、migration drift、`git diff --check` 均退出 0。真实浏览器验证同一 revision 在公开文章、终稿审查和历史版本保留 heading/callout/task list/table；1440/768/390 三主题的页面 `scrollWidth <= clientWidth`，控制台 `0 error / 0 warning`。定向同步 Labs 10 个运行时文件并逐一核对 SHA-256；服务保持规定 worktree 的 `active/running`，live health 200，公开 TipTap 文章 200 且 CSP 正确，近 5 分钟无 warning。隔离 PostgreSQL、Redis DB 12、浏览器、本地服务与临时 HTTP 文件已清理。未执行 production、共享 migration、服务重启、Git 提交或推送；固定 Playwright wrapper 因主机缺少 `runuser` 退出 127，验收以同一 `blog-browser` 无登录用户直接调用其固定 CLI 完成，未以 root 启动浏览器。

## 8. R5 工作流增强与交付收口

### RE-501 实现 block 级复制、删除与变更摘要
- 元数据：状态 `完成`；阶段 R5；owner `authoring` presentation；优先级 P1。
- 目标：版本和冲突界面能以安全元数据描述新增、删除、移动和类型变化，不记录或通知完整正文。
- 依赖：前置 `RE-404`；后续 `RE-502`、`RE-505`。
- 边界/影响：摘要不是第二 diff 事实；日志、审计和通知不得包含正文或粘贴内容。
- 验收：大文档有界计算、重复 block、媒体节点、冲突和隐私测试。风险/停止：摘要持久化泄露正文即停止。
- 当前证据：采用 `reuse + extract`；块复制/删除继续复用 RE-202/206 的 block menu 与独立可撤销 transaction，没有第二套按钮或历史 owner，既有前端合同 `26 passed`。新增 `content/block_changes.py` 仅对两份已授权 TipTap revision 生成瞬时计数，进程内 SHA-256 指纹按重复块出现次序配对，移动使用 LIS，最坏 `O(n log n)`；对外只含 available、before/after 及新增/删除/移动/类型变化/内容变化计数，不返回/持久化/记录正文、attrs、媒体 ID 或指纹。4000 块、重复块、媒体替换、跨格式和隐私聚焦 RED 先因模块缺失以退出 2 失败；最终纯投影/展示合同 `8 passed`，content+authoring 全回归 `86 passed`，TipTap 跨层 `7 passed`，架构合同 `3 passed`。隔离 PostgreSQL 查询验证 owner 授权、revision `sequence=[1,2]/schema=[2,2]` 不变，安全摘要为 `2 -> 2/moved=1/type_changed=1`；未新增表、字段、事件或审计内容。authoring presenter 统一中文标签和比较方向，版本与 409 冲突 partial 均不接收正文 diff。真实浏览器在冲突页验证焦点、冻结表单、安全计数与基线选择，解决冲突后版本页显示同一结构摘要；摘要 DOM 不含正文句子，1440/768/390 三主题无横溢，干净版本会话 `0 error / 0 warning`，冲突会话唯一 console error 为预期主文档 HTTP 409。CSS build、目标 Ruff lint/format、Django check、migration drift 与 `git diff --check` 均退出 0。定向同步 Labs 13 个运行时/构建文件并逐一核对 SHA-256，公网 CSS 哈希一致；目标安全探针为 `moved=1/type_changed=1/private=absent`，主页 200、匿名版本入口 302、服务保持规定 worktree 的 `active/running`、live health 200且近 5 分钟无 warning。隔离 PostgreSQL、Redis DB 12、浏览器、本地服务和 storage state 已清理。固定 Playwright wrapper 仍因缺少 `runuser` 不可用，继续以同一 `blog-browser` 无登录用户直接调用固定 CLI，未以 root 启动浏览器。未执行 production、共享 migration、服务重启、Git 提交或推送；既有 Node `MODULE_TYPELESS_PACKAGE_JSON` warning 不变。

### RE-502 闭合草稿、冲突、版本恢复与媒体生命周期
- 元数据：状态 `完成`；阶段 R5；owner `authoring/content/media` 各守边界；优先级 P0。
- 目标：本地草稿、云草稿、409 冲突、版本恢复和发布审查完整保存新节点，并正确处理媒体引用与孤儿清理。
- 依赖：前置 `RE-303`、`RE-304`、`RE-305`、`RE-501`；后续 `RE-505`。
- 边界/影响：authoring 只编排，不复制 revision/media 生命周期；冲突不得静默合并或覆盖。
- 验收：双浏览器冲突、本地恢复、历史恢复、附件替换、媒体引用计数和失败回滚的真实读回。风险/停止：恢复旧版导致仍被引用媒体被删除即停止。
- 当前证据：采用 `extend + extract`，确认云草稿、409、不可变 revision、恢复和媒体绑定继续分别复用 content/media owner，只修复本地草稿遗漏唯一附件 ID 的真实缺陷。新增 `authoring-local-draft-contract.js` 作为浏览器草稿附件合同：新草稿显式保存 `attachmentAssetId`；旧 v1 TipTap 草稿只允许从唯一合法 attachment node 推导，显式字段与 node 不同、重复节点、非法 ID 或畸形 JSON均拒绝恢复。恢复会同步 hidden field、picker、插入/移除控件和 TipTap node，未知文件元数据以“已恢复附件”安全展示。聚焦 RED 先证明本地稿不含附件字段且恢复后 picker/node 不一致；最终 `npm run test:frontend` 为 `34 passed`，content/authoring/media 聚焦回归为 `81 passed`。真实双浏览器作者流覆盖附件上传、本地刷新恢复、云保存、A 先保存/B 收到 409 且保留本地正文与附件、B 采用当前基线并保留本地输入、再次保存进入终稿审查，以及从界面恢复历史附件 revision；浏览器 A 最终 `0 error / 0 warning`，浏览器 B 只有预期主文档 HTTP 409。隔离 PostgreSQL 读回 `working_sequence=6`、`revision_count=6`、全部 `schema_version=2`、attachment 字段与 node 一致、`binding_count=5`、资产 `ACTIVE`、文件存在且开放冲突为 0；聚焦恢复用例进一步证明旧附件同时绑定 source/restored、替换附件继续绑定 current、两文件均保留，历史资产不可用时整笔回滚且不新增 revision。审查页在 1440/768/390 与三主题均无页面横溢。定向同步 Labs `authoring-local-draft-contract.js`、`authoring-local-draft.js` 和 `static/dist/app.js`，本地/目标 SHA-256 分别为 `70cbabc605991179f9226e97723b7ccf582fbe05cee4b3111e6b8ba80bf29299`、`c18dbe6b81a7130ea626454a67ec3a763879c96ec73cd696eb2c1f6766fae085`、`96bb2d3952ee702c04b4c886ef0e1995364af13138ec3cf5c0766f16445ebaf5`；目标合同探针为 `local_draft_attachment=ok legacy=derived mismatch=rejected`，服务保持规定 worktree 的 `active/running`，主页 200、匿名编辑入口 302、live health 200且无 warning。隔离数据库 `kaj_test_re502`、Redis DB 12、临时媒体/状态文件、浏览器和本地服务已定向清理并读回为空。未执行 production、共享 migration、服务重启、Git 提交或推送；既有 Node `MODULE_TYPELESS_PACKAGE_JSON` warning 不变。

### RE-503 补齐粘贴、导入和导出语义
- 元数据：状态 `完成`；阶段 R5；owner `authoring/exchange/media`；优先级 P1。
- 目标：纯文本、Markdown、受控富文本 HTML 和图片粘贴有明确规则；导出为 Markdown/可读格式时有稳定降级。
- 依赖：前置 `RE-404`、`RE-502`；后续 `RE-505`。
- 边界/影响：粘贴 HTML 先解析到允许 schema，不保存原 HTML；Markdown 文章与 TipTap 文章不在编辑时互换事实格式。
- 验收：跨浏览器粘贴、Word/网页噪声 HTML、图片、表格、危险标签、导出再导入和失败恢复。风险/停止：粘贴可绕过 schema/sanitizer 即停止。
- 当前证据：采用 `extend + reuse`，新增 `editor-paste-contract.js` 并使用官方 MIT `@tiptap/markdown@3.28.0`（包约 99.3 KiB、锁定依赖 `marked@17.0.1`），没有手写第二个 Markdown parser。图片剪贴板继续优先交给现有上传 owner；普通文本保持浏览器原生粘贴；明确 Markdown 经官方 parser 转为当前 TipTap JSON，块级/行内内容分别使用闭合/开放 Slice。受控 HTML 先经 DOM allowlist 删除脚本、iframe、表单/可执行元素、事件属性、class/style、危险 URL、Word wrapper 和远程图片，再由 ProseMirror schema 解析；本项目图片、附件和 embed 的受控 data attrs 仍需经过各自现有策略。聚焦 RED 为前端缺少 paste module 的 `ERR_MODULE_NOT_FOUND` 与后端缺少 `readable_markdown` 的 `AttributeError`；最终单 worker 前端合同 `36 passed`，渲染/TipTap 合同 `9 passed`，JS build 生成 `796.4 KiB` bundle，目标 Ruff lint/format、Django check、migration drift 和 `git diff --check` 均退出 0。Chrome 真实覆盖普通文本、行内/块级 Markdown、标题、列表、表格、安全链接、Word HTML、script/iframe/onclick/javascript URL 清理及 Canvas PNG 粘贴上传；保存后 PostgreSQL revision 节点为 `paragraph/heading/paragraph/table/image/paragraph`，媒体绑定、文件和直连 GET 200。Firefox 使用真实 Clipboard API 与 `Control+V` 覆盖 Markdown H3/列表和 HTML H3，危险脚本/URL 均删除；两浏览器最终均 `0 error / 0 warning`。1440 浅色、768 护眼、390 深色均无横溢，390 下反馈和 ProseMirror 焦点正确。真实导出 ZIP 读回 1 篇文章、2 个 revision、1 个媒体与 9 个 entry：manifest 标记 TipTap Markdown 为 lossy，原 `body.tiptap.json` 与数据库完全一致，媒体大小/SHA-256 一致，便利 `body.md` 不含内部 `media:` ID且可由现有 Markdown importer 重新导入。定向同步 9 个运行时文件到 Labs，本地/目标 SHA-256 逐一一致，公网 `app.js` 哈希为 `a425c1a21c17694557a11b5279ce77b098ce163263fc22f0fc1900afcff9fdc8`；服务保持规定 worktree 的 `active/running`，live health 200，匿名编辑入口安全 302。隔离数据库 `kaj_test_re503`、Redis DB 11、临时媒体、settings、浏览器状态与探针已清理并读回为空。未安装 WebKit；Chrome 与 Firefox 已满足本项跨浏览器门禁。未执行 production、共享 migration、服务重启、Git 提交或推送；既有 Node `MODULE_TYPELESS_PACKAGE_JSON` warning 不变。

### RE-504 建立性能、容量与可观测性门禁
- 元数据：状态 `完成`；阶段 R5；owner `authoring/media rendering`；优先级 P0。
- 目标：定义文档大小、节点数、表格规模、并发上传、渲染时间和前端交互预算，并记录不含正文的指标。
- 依赖：前置 `RE-404`；后续 `RE-505`。
- 边界/影响：错误/日志只记录类型、计数、版本和 correlation ID，不记录正文、URL 凭据、文件路径或剪贴板内容。
- 验收：上限边界、超限 422、长文编辑/渲染、失败率指标和资源门禁；不能靠提高服务器内存掩盖无界处理。风险/停止：指标需要采集正文才能成立即放弃该指标。
- 当前证据：采用 `reuse + extract`，保留 media schema owner 既有 2 MiB、10,000 节点、100 深度、50×20/1,000 单元格硬门禁和图片粘贴 10 张批次，不建立第二套限制；新增 operations 安全指标入口与浏览器 `editor-performance.js`。服务端每次 content projection 只记录 format/mode/schema/source bytes/node count/max depth/table cells/duration/outcome/稳定 error code/trace，250 ms 以上或拒绝为 warning；字段和数值有界，API 不接受正文、URL、文件名、媒体/对象 ID、路径或异常消息。media `RenderedContent/NormalizedTipTapDocument` 暴露安全计数；preview/save 复用已规范化对象，消除同一 TipTap JSON 二次校验，超限规范化拒绝也进入同一失败率指标。浏览器为 update 100 ms、preview request 2,500 ms、preview DOM 500 ms、upload queue 500 ms、upload request 60 s，只保留最近 100 条固定字段内存样本并发出 `kaj:editor-performance`；封面、正文图片与附件共用 FIFO、最多 2 个网络请求，排队仍计入 pending。聚焦 RED 分别为缺少前后端性能 owner 的 `ERR_MODULE_NOT_FOUND/ModuleNotFoundError`，以及预规范化文档仍被二次校验；最终单 worker 前端合同 `38 passed`，operations/content/media 合同 `62 passed`，架构合同 `3 passed`，JS build 为 `799.2 KiB`，目标 Ruff lint/format、Django check、migration drift 均退出 0。纯边界探针 10,000 节点/354,989 bytes 为 `150.0 ms < 250 ms`；重启后真实浏览器 preview 的 10,000 节点为 HTTP 200、总请求 381.8 ms、服务端投影 122.7 ms，10,001 节点为 HTTP 422/`content.body_invalid.v1`，44.8 ms 产生只含 `media.tiptap.structure_limit.v1` 的 rejection metric，页面原正文未改。1,000 段长文真实输入为 update `58.9 ms`、preview request `2145.8 ms`、DOM `22.9 ms`，均在校准预算内；真实正文图片上传的 queue `0 ms`、request `2256.7 ms`、后续 update `96.1 ms`，picker 回到 ready、pending=0，PostgreSQL 资产为 ACTIVE/BODY，96 bytes、文件存在且 SHA-256 一致。页面 `scrollWidth=1265 <= clientWidth=1280`；浏览器唯一 console error 为主动验证 422 的预期主请求。定向同步 15 个运行时/构建文件到 Labs并逐一核对 SHA-256，公网 `app.js` 哈希为 `ecc033caf20c0455d2b8be2abeb6c91c6e885fd07a7dca0df86381218905632e`；服务保持规定 worktree 的 `active/running`，live 200，匿名编辑 302，目标探针为 `250 ms/nodes=3/depth=2/cells=0`，近 5 分钟无 warning。隔离数据库 `kaj_test_re504`、Redis DB 11、媒体、浏览器、服务、状态、settings 与种子已清理并读回为空。未执行 production、共享 migration、Labs 重启、Git 提交或推送；既有 Node `MODULE_TYPELESS_PACKAGE_JSON` warning 不变。

### RE-505 完成跨层回归与 Labs 候选验收
- 元数据：状态 `完成`；阶段 R5；owner `authoring` 验收编排；优先级 P0。
- 目标：验证登录作者从创建到发布、查看、版本恢复的完整富文本流，以及无权、错误、恢复和旧文章兼容。
- 依赖：前置 `RE-402`、`RE-501`、`RE-502`、`RE-503`、`RE-504`；后续：用户授权的 Git/生产交付。
- 边界/影响：按资源门禁串行运行；Labs 同步只在每个通过聚焦验证的运行时切片后执行，生产动作仍需另行授权。
- 验收：相关 pytest、Django check、migration drift、前端 build；`blog-playwright-cli` 串行覆盖 390/768/1440、三主题、键盘/焦点、成功/422/系统错误/无权/恢复；数据库、文件、缓存读回一致。
- 风险/停止：存在正文丢失、越权、XSS、旧文章不可读、预览/发布分叉或媒体误删时不得进入交付。
- 当前证据：采用 `reuse + verify`，未新增产品实现中心；全仓 pytest 首轮只暴露两条已受跟踪旧断言，分别仍预期无 heading 锚点和旧嵌入降级文案，修正为当前稳定 `kaj-h-legacy-<20 hex>` 与安全 Bilibili fallback 后目标用例 `2 passed`。一次误用未监听的 Redis `127.0.0.1:6379/12` 导致连锁环境失败，确认根因后改回隔离容器映射 `127.0.0.1:56381/12`，代表用例 `2 passed`；最终隔离 PostgreSQL `kaj_test_re505`、Redis DB 12 与 Mailpit 上全仓 `535 passed, 1 skipped in 418.63s`，唯一跳过为未配置可选 `KAJ_TEST_UMAMI_DATABASE_URL`。真实 Chrome 作者流从页面选择富文本、输入 heading/paragraph/callout、上传封面/正文图/README.md 附件、创建及再次保存草稿、终稿审查、立即发布、公开阅读、版本时间线与历史恢复；服务器读回 5 个不可变 schema v2 revision，working sequence 5、published sequence 3、恢复 revision 带 `restore_source`，预期 422 与离线未保存文本均未进入数据库。封面/BODY/ATTACHMENT 三资产均为 ACTIVE，实际文件存在且大小与 SHA-256 同数据库一致，15 条 revision binding 保持有效；公开 Redis 缓存命中发布 revision 且 sanitizer version 包含 TipTap renderer 分区。服务端 422 在临时关闭浏览器原生 required 后真实返回，字段错误、正文、媒体、附件和本地稿均保留且错误区获得焦点；离线预览显示安全不可用态，恢复网络并继续输入后完整预览恢复；普通用户访问作者编辑页得到不泄露正文的 403。旧 Markdown 与旧 TipTap v1 均在公开页和作者编辑器可读，v1 标题读回确定性 legacy anchor。1440 浅色、768 护眼、390 深色均无页面横向溢出，顶部栏保持 sticky，正文图完整适配，主要操作至少 44px，reduced-motion 生效；More 菜单 ArrowDown/Escape 后焦点回到触发器。正常公开/兼容会话控制台 `0 error / 0 warning`，主动 422、403 与离线请求只产生对应预期网络错误。Labs 最终读回规定 worktree、`active/running`、live/home 200、匿名作者入口 302；本地、Labs worktree 与公网 `app.js`/`styles.css` SHA-256 完全一致。固定 `/usr/local/bin/blog-playwright-cli` 仍因主机缺少 `runuser` 退出 127，验收继续以同一 `blog-browser` UID/GID 直接调用固定 CLI，未以 root 启动浏览器或添加 `--no-sandbox`。隔离数据库、Redis DB、临时媒体/settings/浏览器状态和四个本任务临时前端合同测试均在最终检查前清理。未执行 production、共享 migration、Labs 重启、Git add/commit/push/merge；这些仍需用户当前回合另行授权。

## 9. 全局完成条件

- 29 个 Todo 全部为 `完成`，ID 唯一、前置存在、依赖无环且无反向阶段边。
- 所有新增 node/mark 在前端 schema、规范化、服务端校验、renderer、sanitizer、缓存和每个阅读出口中有且只有一份明确契约。
- 旧 Markdown 与旧 TipTap 文章无需破坏性回填即可编辑或阅读；未知/非法新内容明确拒绝，不静默删除。
- 草稿、冲突、版本、媒体、附件、粘贴、导入导出与发布形成真实持久化和文件生命周期闭环。
- 390/768/1440、三主题、键盘、焦点、触控目标和 reduced-motion 验收通过；无按钮挤压、页面级横向溢出或浮层遮挡。
- 所有命令、退出码、通过数、数据/文件/浏览器读回、未执行项与残余风险已回写对应任务。
- 完成此清单不自动表示已提交、推送、部署或生产迁移。
