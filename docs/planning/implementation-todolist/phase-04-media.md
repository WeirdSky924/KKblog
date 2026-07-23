# P4 媒体、安全渲染与个人资料（8）

退出门禁：媒体上传/绑定/读取/清理、安全渲染和头像/Logo/资料消费者完成真实文件读回。

### MED-001 建立 MediaAsset/Binding 与文件系统存储端口
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：以受控 ULID、owner、purpose、storage_key、真实格式、哈希、状态和注册目标绑定描述全部媒体；数据库永不保存绝对路径。
- 来源：访谈 Q042、Q115、Q265；`data/03-interaction-operations-fields.md` §Media；`data/05-storage-lifecycle.md` §服务器目录；ADR-006。
- 依赖：前置 `ACC-001`、`FND-006`；后续 `MED-002`、`MED-003`、`MED-006`、`QA-001`、`QA-006`。
- 文件：`apps/media/models/`、storage port/filesystem adapter、migrations/tests。
- 边界：不让 content/comments 拼路径或直接删文件；target_type 必须注册；不在数据库存二进制。
- 影响：数据：Asset/Binding/约束；权限：owner/target；审计：版本 ID；缓存/异步/通知无；媒体：唯一事实。
- 测试/验收：RED storage_key/size/绑定唯一、非法 target、路径不含邮箱昵称；migration+临时目录读回。
- 风险/停止：路径可由用户控制、符号链接越界或 DB/目录根不明确时停止。
- 证据：RED `/root/.local/bin/uv run pytest apps/media/tests/test_med001.py -q` 退出 2，收集期确认 `apps.media` owner 不存在。实现 `MediaAsset`/`MediaBinding`、固定用途与目标注册表、2 MiB/相对键/哈希/状态/绑定唯一约束，以及只接受服务键的文件系统 port；真实 PostgreSQL 聚焦、ACC-001/011 生命周期和架构回归退出 0，`28 passed`。隔离 migration 退出 0，catalog 读回 `media_asset`/`media_binding` 及全部命名约束；临时媒体目录读回 `safe-bytes`，删除重复执行返回不存在成功语义，绝对路径、`..`、反斜杠和符号链接越根均被拒绝。数据库只存相对 key/元数据，路径不含邮箱昵称且无二进制/绝对路径字段；未执行生产 migration、媒体写入或 Git 交付。
- 授权：`否`。

### MED-002 实现两阶段上传、真实格式验证与图像清洗
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：流式限制 2 MiB，真实签名+解码，去 EXIF；静态图最长边不超 `8192` 且总像素不超 `25 MP`，动图不超 `200` 帧且累计解码不超 `100 MP`；PNG/JPEG/GIF/WebP，Logo 另许 ICO；GIF 重编码仍动画。
- 来源：访谈 Q040-Q045、Q093、Q113-Q116、Q123-Q125、Q163-Q164、Q230、Q318；`modules/04-media-rendering.md` §统一规则；DEC-005。
- 依赖：前置 `MED-001`、`DEC-005`、`OBS-007`；后续 `MED-003`、`MED-005`、`EXC-001`、`QA-003`、`QA-006`。
- 文件：imaging/detect/sanitize/gif/ico、stage service、upload views/tests。
- 边界：不信 MIME/扩展名/Content-Length；显示分辨率不预设固定尺寸，但解码硬上限不可绕过；失败文件不得进入 ACTIVE，任何安全上限放宽需新决策。
- 影响：数据：STAGED 元数据；权限：上传 actor；审计：管理员站点资产；缓存无；异步：提交后移动；媒体核心；通知无。
- 测试/验收：RED 伪 MIME、双扩展、坏图、2MiB±1、`8192`/`25 MP` 边界、`200` 帧/`100 MP` 累计边界、EXIF、动画保留、ICO；浏览器失败保留表单。
- 风险/停止：清洗改变语义/动画、临时文件泄露或解码库漏洞未处理时停止。
- 证据：RED `/root/.local/bin/uv run pytest apps/media/tests/test_med002.py -q` 退出 2，准确报告统一 imaging owner 缺失。新增锁定 Pillow 12.3.0（MIT-CMU）、流式同盘暂存、真实签名/解码、统一维度/像素/帧门禁、无元数据重编码及提交后原子激活；最终媒体、CapacityPolicy、HTTP 安全与架构回归退出 0，`44 passed`，`uv lock --check`、Ruff、format、migration drift 与 `git diff --check` 均退出 0。真实文件读回证明伪 MIME/双扩展按 JPEG 处理且 storage key 不含原名，EXIF 为空、两帧 GIF 仍为两帧；坏图、2 MiB+1、8193 边、201 帧、100 MP+ 与非 Logo ICO 均稳定拒绝，2 MiB、8192、25 MP、200 帧/100 MP 精确边界通过。隔离上传端点成功只返回 ACTIVE asset；失败返回 422、安全中文和原文件名上下文，数据库/临时文件均无失败残留。阶段收口 RED `pytest apps/media/tests/test_med002.py::test_decoder_rejects_header_limits_before_loading_pixels -q` 退出 1，证明 8193 边 PNG 会在门禁前调用 `Image.load()`；修复后先检查总帧数并在逐帧像素加载前检查边长、单帧与累计像素，同一测试和 MED-002 全套分别 `1 passed`、`17 passed`，最终全量 `260 passed`。未执行生产媒体写入或 Caddy 重载。
- 授权：`否`。

### MED-003 实现用途绑定、替换与跨域读取授权
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：`bind_assets/replace_bindings/authorize_asset_read` 校验 owner、用途、目标、slot、数量；正文只引用 media ID，私有/未绑定资产直接 URL 不可读。
- 来源：`contracts/01-application-services.md` §media；`modules/04-media-rendering.md` §服务边界；`contracts/02-authorization-matrix.md`。
- 依赖：前置 `MED-001`、`MED-002`；后续 `MED-004`、`MED-005`、`MED-006`、`MED-007`、`CNT-002`、`CMT-002`、`CMT-008`、`EXC-003`、`QA-003`、`QA-006`。
- 文件：media services/policies/target access registry/queries/tests。
- 边界：media 调目标公开 access port，不导入私有模型；capability 不能替代请求时重判；证据图严格私有。
- 影响：数据：Binding/state；权限：用途/对象；审计：asset ID；缓存：授权结果不缓存；异步/通知无；媒体：绑定。
- 测试/验收：RED 他人头像/文章/证据、用途错配、数量超限、目标删除；直接 URL 与服务读回。
- 风险/停止：跨 app 循环、万能 target 字符串或授权仅靠隐藏 URL 即停止。
- 证据：RED `/root/.local/bin/uv run pytest apps/media/tests/test_med003.py -q` 退出 2，准确报告绑定/读取服务 owner 缺失。实现固定 target/purpose/slot/数量规则、可注入且默认注册的 `TargetAccessRegistry`、事务行锁下的 `bind_assets`/`replace_bindings` 与每次重判的 `authorize_asset_read`；accounts 只经 `media.public` 注册公开资料 access port，media 不导入账户私有模型。真实 PostgreSQL 媒体、ACC-001/011 生命周期及架构回归退出 0，`49 passed`；Ruff、format、Django check、migration drift 和 `git diff --check` 均退出 0。读回证明他人头像绑定、错用途/槽位、第四张证据、已绑定资产复用均拒绝；头像替换后新资产 ACTIVE、旧资产 DELETE_PENDING；未绑定资产、已禁用目标、目标删除和私有证据非参与者统一不可读，公开头像仅在目标当前有效时给出不可变公开授权。未缓存授权结果，未执行生产媒体/账户动作。
- 授权：`否`。

### MED-004 实现受控媒体交付与公开/私人缓存边界
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：公开不可变资产可受控发送；私人、草稿、冷静期、证据和导出必须先经 Django 授权再由 Caddy internal 传输。
- 来源：`data/05-storage-lifecycle.md` §服务器目录/缓存；ADR-006 §Consequences；`RUN-003` 约定。
- 依赖：前置 `MED-003`、`RUN-003`；后续 `DSC-005`、`EXC-005`、`QA-002`、`QA-003`、`QA-006`。
- 文件：authorized media view、response headers/internal redirect、cache policy/tests。
- 边界：不生成公开签名长链或暴露 storage_key；未授权对象存在性按策略 404；Caddy 不遍历目录。
- 影响：数据无写；权限：每次读取；缓存：仅明确公开不可变；异步无；媒体：传输；审计/通知无。
- 测试/验收：RED 访客/用户/作者/管理员×用途矩阵、Range/缓存头、路径穿越；真实 HTTP 请求验证。
- 风险/停止：代理配置绕过 Django、缓存私人响应或下载头注入即停止。
- 证据：RED `/root/.local/bin/uv run pytest apps/media/tests/test_med004.py -q` 退出 1，`4 failed`，准确报告内部授权 URL 与 Caddy 头隔离合同缺失。新增只接受 Caddy 内部标识和精确 `/_kaj/media/<ULID>` 原始 URI 的无正文授权端点；它每次调用 media owner 重判绑定/目标/actor，以统一 404 隐藏未知、未绑定、越权及穿越请求，并仅向 Caddy 返回服务端 storage key、公开标识和缓存策略。Caddy 先删除客户端伪造的内部/storage/cache/public 头，`forward_auth` 显式注入内部标识，授权后才以内置 `file_server` 发送文件；外部 `/internal/*` 被开发和生产路由直接 404，私人使用 `private, no-store`，仅明确公开资产使用一年 immutable，内部 storage key 不进入响应。聚焦 GREEN `4 passed`；媒体、架构、HTTP 安全与前端基础回归退出 0，`46 passed`，Django check、Ruff、format、`git diff --check` 及开发/生产 Caddy validate 均退出 0。隔离临时 Django+Caddy+PostgreSQL+真实媒体目录 HTTP 读回退出 0：公共 200、Range 206、私人访客/其他用户 404、owner 200/no-store、伪造头仍发送正确文件、未知/穿越/外部 internal 均 404；临时进程、容器和目录已精确清理，未重载真实 Caddy、未写生产媒体。
- 授权：配置/隔离测试 `否`；重载真实 Caddy `是`。

### MED-005 交付统一媒体选择器及头像/Logo/友情链接消费者
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P1。
- 目标/行为：统一选择/拖放、进度、预览、错误、移除、重试组件，供头像、站点 Logo/favicon、友情链接 Logo 使用；建立默认 K 标志，并交付仓库自有 `1600x900` 默认封面与 `800x450` 失效图。
- 来源：访谈 Q038-Q039、Q075、Q093-Q096、Q161-Q165、Q239；`modules/04-media-rendering.md` §UI/用途；`03-frontend-design-system.md` §组件；DEC-005。
- 依赖：前置 `MED-002`、`MED-003`、`RUN-005`、`DEC-005`；后续 `ACC-007`、`DSC-001`、`AUT-002`、`ADM-007`、`QA-003`、`QA-006`。
- 文件：media picker partial/JS、avatar/logo/friend adapters、brand assets、Playwright tests。
- 边界：消费者不能绕过 media 服务；不做通用文件管理器；默认 K 用 CSS/矢量，上传 Logo 仅 PNG/ICO；默认封面和失效图是不同语义的本地资产，不下载许可不明素材。
- 影响：数据：当前资产引用；权限：本人/管理员；审计：站点资产变更；缓存：favicon；媒体：多用途；异步：清理；通知无。
- 测试/验收：RED pending/失败/移除后引用；资产尺寸/引用检查；Playwright 1440/390 键盘/触控、错误长文案、GIF预览、Logo/favicon读回，并在三主题核对默认封面与失效图不混用。
- 风险/停止：组件把失败显示成功、手机文件控件不可达或焦点丢失即停止消费者上线。
- 证据：RED `/root/.local/bin/uv run pytest apps/media/tests/test_med005.py -q` 退出 1，`4 failed`，准确报告统一用途入口、picker partial 和品牌资产缺失。新增由 consumer owner 注册、media owner 执行的固定上传适配器：本人头像与仅管理员可用的站点 Logo/友情链接 Logo 都复用同一 `stage_upload`，返回受控 asset ID 而不提前建立下游模型或绕过后续绑定；站点 Logo 只许 PNG/ICO，友情链接/头像保持普通图片格式。统一 picker 提供编号式“选择→校验→可用”状态轨道、选择/真实拖放、浏览器预览、真实进度、pending 禁用与 `aria-busy`、服务端 422 长错误、重试、移除清空引用/恢复焦点、GIF 动画和 favicon 即时预览/默认 K 恢复；隐藏原生 file input 不形成第二键盘/读屏入口。仓库新增 CSS/矢量 K 标志，以及由可复现 Pillow 脚本原创生成的 `1600x900` 默认封面和语义独立的 `800x450` 失效收藏图；图像逐张视觉读回后移除了默认封面中可能与失效 X 混淆的构图。聚焦 GREEN `4 passed`；最终隔离 PostgreSQL/Redis/Mailpit 媒体、账户、管理、架构与 HTTP/前端回归退出 0，`116 passed`，Ruff 212 文件、完整 npm build、`uv lock --check`、Django check、migration drift 和 `git diff --check` 均退出 0。规定 `/usr/local/bin/blog-playwright-cli` 在 1440/light、768/eye-care、390/dark 实测 3 个 consumer：真实 422 保留长文件名且坏图不污染预览，重试产生第二次真实 POST；延迟真实响应时引用为空、控件禁用、进度可见，完成后才写 26 位 ID；键盘 Enter、焦点环、移除焦点恢复、拖放、ICO favicon/恢复及 GIF 10 次像素截图多帧均通过，无横溢出。PostgreSQL+临时媒体根读回本轮 9 个 AVATAR/LOGO/FRIEND_LOGO 均 ACTIVE、未绑定且文件存在。阶段收口 RED `pytest apps/media/tests/test_med005.py::test_picker_partial_has_stable_state_track_and_consumer_contract -q` 退出 1，定位上传中保存会误锁表单且拖放仍可二次选择；修复后聚焦 `1 passed`，真实延迟响应浏览器读回上传中引用为空、文件/拖放禁用、保存提示后表单未锁死，响应后写入 26 位 ID 并可再次保存。临时浏览器、服务、目录和截图已清理，未写生产媒体或提前绑定未来 navigation 对象。
- 授权：`否`；新外部视觉素材需用户确认许可。

### MED-006 实现解除引用、暂存过期与幂等删除 Saga
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：解除正文引用/删除评论后立即标待删并提交后删文件；失败重试；文章软删除保留，到期/账户删除幂等清理；缺文件视为成功。
- 来源：访谈 Q045-Q047、Q116、Q282-Q283、Q315；`data/05-storage-lifecycle.md` §删除协议；`contracts/05-background-tasks.md`。
- 依赖：前置 `MED-001`、`MED-003`、`FND-005`、`OBS-006`；后续 `CNT-008`、`CMT-006`、`EXC-005`、`QA-004`、`QA-006`。
- 文件：cleanup services/tasks、staging expiry、outbox consumers、TaskRun hooks/tests。
- 边界：永不先删文件再提交 DB；软删除期不物理删；案件/审计不随资产删；任务只重入服务。
- 影响：数据：DELETE_PENDING/DELETED；权限：解绑后不可读；审计：ID；异步：清理/重试；媒体：文件；缓存失效；通知仅终败后。
- 测试/验收：RED 提交前/后崩溃、重复任务、文件已缺、软删恢复、并发替换；真实临时目录读回。
- 风险/停止：误删共享/活跃资产、计算路径出根目录或清理无幂等键即停止。
- 证据：RED `uv run pytest apps/media/tests/test_med006.py -q` 退出 2，收集期准确报告 cleanup owner 缺失。新增单一清理状态机：只有已提交的 `DELETE_PENDING` 且无 Binding 资产可触碰文件，缺文件视为成功并写 `DELETED/deleted_at`，边界/IO 失败仅暴露 `media.file_delete_failed.v1` 并保持待删；`replace_bindings` 与 owner 释放都在外层事务 `on_commit` 后立即尝试，失败由周期任务补偿。24 小时可配置的未绑定 ACTIVE/STAGED 过期、固定 ULID `.staging/*.part` mtime 扫描、未知文件/符号链接 fail-closed；文章软删期由目标 access port 拒绝读取但保留 ACTIVE/Binding/文件，恢复后无需重建即可再读。账户正式删除在同一事务先解除全部媒体引用并标待删，owner FK 删除后可空；PostgreSQL `media_asset_owner_lifecycle` 约束要求 owner 为空时状态只能待删/已删，直接绕过 service 删除账户被拒绝，正式提交后 owner 置空、Binding/文件删除且 DELETED 事实保留，外层回滚则账户/绑定/文件完整恢复。四个 Celery 入口复用 operations `TaskRun`：逐资产固定 `asset:<id>:delete|staged-expiry` 幂等键、1/5/30 分钟安全重试，以及每分钟 pending/每小时 staged dispatcher；部分排队重试也只会产生幂等逐资产任务。聚焦故障/并发回归退出 0，`11 passed`：文件删除后进程硬崩可从缺文件恢复，重复/两 worker 只删一次，并发同槽替换仅一个 ACTIVE winner；真实临时目录逐字节读回、旧 part 删除/新 part 保留。最终隔离全量 pytest 退出 0，`219 passed`；Ruff 220 文件、format、`uv lock --check`、Django check、migration drift 和 `git diff --check` 均退出 0。隔离 migration `0002/0003` 成功，catalog 读回 `owner_id` nullable 与 owner 生命周期 CHECK；Celery autodiscovery 读回 4 个任务和 2 条 Beat 配置。未执行生产 migration、生产媒体清理或真实 worker/beat 重启。
- 授权：隔离目录 `否`；生产媒体清理 `是`。

### MED-007 建立 Markdown/TipTap/作者 HTML/嵌入统一安全渲染
- 元数据：状态 `完成`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：所有保存、预览、阅读、导入路径使用同一 allowlist；外链安全新标签；初始仅 Bilibili 受信嵌入，来源移除显示“来源不可用”。
- 来源：访谈 Q036-Q037、Q231-Q233、Q263、Q316；`modules/04-media-rendering.md` §安全渲染；`reference/01-requirements-resolution.md`。
- 依赖：前置 `MED-003`、`FND-006`；后续 `CNT-002`、`CNT-003`、`DSC-005`、`EXC-001`、`AUT-002`、`ADM-007`、`QA-003`、`QA-006`。
- 文件：rendering/markdown/tiptap/html_policy/embeds、sanitizer version/cache key、fixtures/tests。
- 边界：禁止 script、事件属性、危险协议、任意 iframe/raw执行；预览不例外；不为每编辑器建第二 sanitizer。
- 影响：数据：保存 source/规则版本；权限：可信来源管理员配置；审计：来源变更；缓存：规则版本失效；媒体 ID；异步/通知无。
- 测试/验收：RED XSS/URL/iframe/属性/DOM clobbering、来源移除、外链 rel；浏览器确认脚本未执行且内容可读。
- 风险/停止：任一输入路径绕过、sanitizer 升级不失效旧缓存或原始 HTML 执行即停止发布。
- 证据：RED `/root/.local/bin/uv run pytest apps/media/tests/test_med007.py -q` 收集期退出 2，准确报告统一 rendering owner 缺失。新增锁定 `nh3 0.3.6` 与 `markdown-it-py 4.2.0`（均 MIT）的单一渲染管线：Markdown、严格有界 TipTap JSON、作者 HTML 与导入预览先生成候选 HTML，再统一经语义标签/属性/协议 allowlist 和结构化后处理；script/style/form/SVG/MathML/DOM clobber 属性、危险协议、协议相对 URL、远程图片及任意 iframe 均被移除，正文图片只接受调用方明确授权的 `media:<ULID>`。绝对 HTTP(S) 外链拒绝凭据并固定 `_blank`/`noopener noreferrer`，站内相对链接与 mailto 保持同页；初始策略只把精确 `www.bilibili.com/video/<BV>` 转成固定 player URL 和 sandbox/referrer/lazy 属性，原始 iframe 永不保留，来源禁用或不匹配显示“来源不可用”。sanitizer 版本、格式、可信来源指纹及媒体能力集合全部进入缓存键。聚焦 GREEN 退出 0，`21 passed`；隔离 PostgreSQL 媒体与架构回归退出 0，`73 passed`，Ruff/format 与锁文件检查通过。规定 `/usr/local/bin/blog-playwright-cli` 由低权限浏览器在 1440/768/390 真实执行输出：`window.__kaj_xss` 始终未定义、script/事件/style/clobber 属性计数 0、可读 Markdown/TipTap/HTML 正文保留，外链/站内链接属性分流正确，恶意 iframe 为 0、受控 Bilibili iframe 恰为 1 且 sandbox 固定、禁用来源占位可见，三视口横溢出均为 0；临时浏览器、HTTP 服务与 harness 已精确清理，未写生产内容或缓存。
- 授权：`否`。

### ACC-007 实现昵称、主题、头像与公开资料
- 元数据：状态 `完成`；阶段 P4；owner `accounts`；优先级 P1。
- 目标/行为：用户可设置昵称（中文2/英文1、预算16、7天冷却），以 Unicode `casefold` 规范值大小写不敏感唯一且展示保留原大小写；用户还可设账户主题和统一媒体头像；无头像生成圆形首字符；公开主页不暴露邮箱。
- 来源：访谈 Q015、Q088-Q103、Q295；`data/02-identity-content-fields.md` §Account；`contracts/03-frontend-contract-map.md` §个人页面。
- 依赖：前置 `ACC-001`、`DEC-003`、`MED-005`；后续 `DSC-001`、`DSC-007`、`ADM-002`、`QA-003`、`QA-006`。
- 文件：profile service/query/forms/templates、avatar bridge、nickname history/tests。
- 边界：不展示完整邮箱/私有资料；头像字节由 media 所有；主题同步不覆盖访客本地选择直到登录。
- 影响：数据：Account/NicknameHistory；权限：本人修改/公开 DTO；审计：安全资料变更摘要；缓存：浏览器/账户主题；媒体：头像；通知/异步无。
- 测试/验收：RED Unicode 预算、casefold 大小写变体/并发冲突、原展示值、冷却、删除后复用但 UUID 不复用；Playwright 字段冲突、头像/主题跨设备与空公开主页。
- 风险/停止：casefold 函数不唯一、唯一性只在表单层、历史评论重新关联新账户或头像越权即停止。
- 证据：新增共享 Unicode 昵称 validator、`NicknameHistory` 与 PostgreSQL 部分唯一索引，展示值保留原大小写，NFKC+`casefold` 规范值由数据库裁决；资料 service 在账户行锁和同一事务中处理 16 单位预算、7 天冷却、昵称历史、主题、媒体头像替换及安全审计，审计失败会回滚账户和 Binding。公开 DTO 只给 UUID、展示名、头像 URL/首字符与主页 URL，不暴露完整邮箱；设置页按资料/凭证/主题分栏，账户主题登录后覆盖并回写访客本地值，原生 radio 分段控件支持指针和键盘。收口 RED `pytest apps/accounts/tests/test_acc007.py::test_nickname_cooldown_message_uses_shanghai_time -q` 退出 1，读回提示误用 UTC `2026-07-30 18:30`；复用核心时区 owner 后 GREEN `1 passed`，上海时间为 `2026-07-31 02:30`，ACC-007 聚焦最终 `19 passed`。并发大小写变体仅一个事务成功；删除旧账户后昵称可复用但新 UUID 不同，旧昵称历史级联删除。隔离 migration 从零应用 `accounts.0006_nickname_history` 退出 0，catalog 读回 5 列、账户外键、`nickname_history_account_idx`，账户读回 `account_nickname_casefold_unique`；最终隔离全量 pytest `260 passed`、架构 `3 passed`，Ruff、235 文件 format、`uv lock --check`、Django check、migration drift、npm build/audit、开发/生产 Caddy validate 与 `git diff --check` 均退出 0。规定浏览器实测 casefold 冲突 422 保留字段、头像真实上传 201/保存、Caddy 头像 200 PNG+一年 immutable、空公开主页无完整邮箱/角色且显示真实头像；访客本地护眼主题登录后由账户深色替换并跨设备持久，1440/light、768/eye-care、390/dark 无横溢出，主题控件 48px、Space 可选、焦点环 3px。最终延迟上传恢复流写入 ACTIVE AVATAR 与 `account_profile/avatar` Binding，数据库大小/哈希和真实文件 SHA-256 一致；所有临时浏览器、端口、数据库和媒体目录已清理。未执行生产 migration、生产媒体/账户写入、真实 Caddy 重载或 Git 交付。
- 授权：`否`。

[返回总索引](../implementation-todolist.md)
