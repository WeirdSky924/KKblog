# P4 媒体、安全渲染与个人资料（8）

退出门禁：媒体上传/绑定/读取/清理、安全渲染和头像/Logo/资料消费者完成真实文件读回。

### MED-001 建立 MediaAsset/Binding 与文件系统存储端口
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：以受控 ULID、owner、purpose、storage_key、真实格式、哈希、状态和注册目标绑定描述全部媒体；数据库永不保存绝对路径。
- 来源：访谈 Q042、Q115、Q265；`data/03-interaction-operations-fields.md` §Media；`data/05-storage-lifecycle.md` §服务器目录；ADR-006。
- 依赖：前置 `ACC-001`、`FND-006`；后续 `MED-002`、`MED-003`、`MED-006`、`QA-001`、`QA-006`。
- 文件：`apps/media/models/`、storage port/filesystem adapter、migrations/tests。
- 边界：不让 content/comments 拼路径或直接删文件；target_type 必须注册；不在数据库存二进制。
- 影响：数据：Asset/Binding/约束；权限：owner/target；审计：版本 ID；缓存/异步/通知无；媒体：唯一事实。
- 测试/验收：RED storage_key/size/绑定唯一、非法 target、路径不含邮箱昵称；migration+临时目录读回。
- 风险/停止：路径可由用户控制、符号链接越界或 DB/目录根不明确时停止。
- 授权：`否`。

### MED-002 实现两阶段上传、真实格式验证与图像清洗
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：流式限制 2 MiB，真实签名+解码，去 EXIF；静态图最长边不超 `8192` 且总像素不超 `25 MP`，动图不超 `200` 帧且累计解码不超 `100 MP`；PNG/JPEG/GIF/WebP，Logo 另许 ICO；GIF 重编码仍动画。
- 来源：访谈 Q040-Q045、Q093、Q113-Q116、Q123-Q125、Q163-Q164、Q230、Q318；`modules/04-media-rendering.md` §统一规则；DEC-005。
- 依赖：前置 `MED-001`、`DEC-005`、`OBS-007`；后续 `MED-003`、`MED-005`、`EXC-001`、`QA-003`、`QA-006`。
- 文件：imaging/detect/sanitize/gif/ico、stage service、upload views/tests。
- 边界：不信 MIME/扩展名/Content-Length；显示分辨率不预设固定尺寸，但解码硬上限不可绕过；失败文件不得进入 ACTIVE，任何安全上限放宽需新决策。
- 影响：数据：STAGED 元数据；权限：上传 actor；审计：管理员站点资产；缓存无；异步：提交后移动；媒体核心；通知无。
- 测试/验收：RED 伪 MIME、双扩展、坏图、2MiB±1、`8192`/`25 MP` 边界、`200` 帧/`100 MP` 累计边界、EXIF、动画保留、ICO；浏览器失败保留表单。
- 风险/停止：清洗改变语义/动画、临时文件泄露或解码库漏洞未处理时停止。
- 授权：`否`。

### MED-003 实现用途绑定、替换与跨域读取授权
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：`bind_assets/replace_bindings/authorize_asset_read` 校验 owner、用途、目标、slot、数量；正文只引用 media ID，私有/未绑定资产直接 URL 不可读。
- 来源：`contracts/01-application-services.md` §media；`modules/04-media-rendering.md` §服务边界；`contracts/02-authorization-matrix.md`。
- 依赖：前置 `MED-001`、`MED-002`；后续 `MED-004`、`MED-005`、`MED-006`、`MED-007`、`CNT-002`、`CMT-002`、`CMT-008`、`EXC-003`、`QA-003`、`QA-006`。
- 文件：media services/policies/target access registry/queries/tests。
- 边界：media 调目标公开 access port，不导入私有模型；capability 不能替代请求时重判；证据图严格私有。
- 影响：数据：Binding/state；权限：用途/对象；审计：asset ID；缓存：授权结果不缓存；异步/通知无；媒体：绑定。
- 测试/验收：RED 他人头像/文章/证据、用途错配、数量超限、目标删除；直接 URL 与服务读回。
- 风险/停止：跨 app 循环、万能 target 字符串或授权仅靠隐藏 URL 即停止。
- 授权：`否`。

### MED-004 实现受控媒体交付与公开/私人缓存边界
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：公开不可变资产可受控发送；私人、草稿、冷静期、证据和导出必须先经 Django 授权再由 Caddy internal 传输。
- 来源：`data/05-storage-lifecycle.md` §服务器目录/缓存；ADR-006 §Consequences；`RUN-003` 约定。
- 依赖：前置 `MED-003`、`RUN-003`；后续 `DSC-005`、`EXC-005`、`QA-002`、`QA-003`、`QA-006`。
- 文件：authorized media view、response headers/internal redirect、cache policy/tests。
- 边界：不生成公开签名长链或暴露 storage_key；未授权对象存在性按策略 404；Caddy 不遍历目录。
- 影响：数据无写；权限：每次读取；缓存：仅明确公开不可变；异步无；媒体：传输；审计/通知无。
- 测试/验收：RED 访客/用户/作者/管理员×用途矩阵、Range/缓存头、路径穿越；真实 HTTP 请求验证。
- 风险/停止：代理配置绕过 Django、缓存私人响应或下载头注入即停止。
- 授权：配置/隔离测试 `否`；重载真实 Caddy `是`。

### MED-005 交付统一媒体选择器及头像/Logo/友情链接消费者
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P1。
- 目标/行为：统一选择/拖放、进度、预览、错误、移除、重试组件，供头像、站点 Logo/favicon、友情链接 Logo 使用；建立默认 K 标志，并交付仓库自有 `1600x900` 默认封面与 `800x450` 失效图。
- 来源：访谈 Q038-Q039、Q075、Q093-Q096、Q161-Q165、Q239；`modules/04-media-rendering.md` §UI/用途；`03-frontend-design-system.md` §组件；DEC-005。
- 依赖：前置 `MED-002`、`MED-003`、`RUN-005`、`DEC-005`；后续 `ACC-007`、`DSC-001`、`AUT-002`、`ADM-007`、`QA-003`、`QA-006`。
- 文件：media picker partial/JS、avatar/logo/friend adapters、brand assets、Playwright tests。
- 边界：消费者不能绕过 media 服务；不做通用文件管理器；默认 K 用 CSS/矢量，上传 Logo 仅 PNG/ICO；默认封面和失效图是不同语义的本地资产，不下载许可不明素材。
- 影响：数据：当前资产引用；权限：本人/管理员；审计：站点资产变更；缓存：favicon；媒体：多用途；异步：清理；通知无。
- 测试/验收：RED pending/失败/移除后引用；资产尺寸/引用检查；Playwright 1440/390 键盘/触控、错误长文案、GIF预览、Logo/favicon读回，并在三主题核对默认封面与失效图不混用。
- 风险/停止：组件把失败显示成功、手机文件控件不可达或焦点丢失即停止消费者上线。
- 授权：`否`；新外部视觉素材需用户确认许可。

### MED-006 实现解除引用、暂存过期与幂等删除 Saga
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：解除正文引用/删除评论后立即标待删并提交后删文件；失败重试；文章软删除保留，到期/账户删除幂等清理；缺文件视为成功。
- 来源：访谈 Q045-Q047、Q116、Q282-Q283、Q315；`data/05-storage-lifecycle.md` §删除协议；`contracts/05-background-tasks.md`。
- 依赖：前置 `MED-001`、`MED-003`、`FND-005`、`OBS-006`；后续 `CNT-008`、`CMT-006`、`EXC-005`、`QA-004`、`QA-006`。
- 文件：cleanup services/tasks、staging expiry、outbox consumers、TaskRun hooks/tests。
- 边界：永不先删文件再提交 DB；软删除期不物理删；案件/审计不随资产删；任务只重入服务。
- 影响：数据：DELETE_PENDING/DELETED；权限：解绑后不可读；审计：ID；异步：清理/重试；媒体：文件；缓存失效；通知仅终败后。
- 测试/验收：RED 提交前/后崩溃、重复任务、文件已缺、软删恢复、并发替换；真实临时目录读回。
- 风险/停止：误删共享/活跃资产、计算路径出根目录或清理无幂等键即停止。
- 授权：隔离目录 `否`；生产媒体清理 `是`。

### MED-007 建立 Markdown/TipTap/作者 HTML/嵌入统一安全渲染
- 元数据：状态 `待处理`；阶段 P4；owner `media`；优先级 P0。
- 目标/行为：所有保存、预览、阅读、导入路径使用同一 allowlist；外链安全新标签；初始仅 Bilibili 受信嵌入，来源移除显示“来源不可用”。
- 来源：访谈 Q036-Q037、Q231-Q233、Q263、Q316；`modules/04-media-rendering.md` §安全渲染；`reference/01-requirements-resolution.md`。
- 依赖：前置 `MED-003`、`FND-006`；后续 `CNT-002`、`CNT-003`、`DSC-005`、`EXC-001`、`AUT-002`、`ADM-007`、`QA-003`、`QA-006`。
- 文件：rendering/markdown/tiptap/html_policy/embeds、sanitizer version/cache key、fixtures/tests。
- 边界：禁止 script、事件属性、危险协议、任意 iframe/raw执行；预览不例外；不为每编辑器建第二 sanitizer。
- 影响：数据：保存 source/规则版本；权限：可信来源管理员配置；审计：来源变更；缓存：规则版本失效；媒体 ID；异步/通知无。
- 测试/验收：RED XSS/URL/iframe/属性/DOM clobbering、来源移除、外链 rel；浏览器确认脚本未执行且内容可读。
- 风险/停止：任一输入路径绕过、sanitizer 升级不失效旧缓存或原始 HTML 执行即停止发布。
- 授权：`否`。

### ACC-007 实现昵称、主题、头像与公开资料
- 元数据：状态 `待处理`；阶段 P4；owner `accounts`；优先级 P1。
- 目标/行为：用户可设置昵称（中文2/英文1、预算16、7天冷却），以 Unicode `casefold` 规范值大小写不敏感唯一且展示保留原大小写；用户还可设账户主题和统一媒体头像；无头像生成圆形首字符；公开主页不暴露邮箱。
- 来源：访谈 Q015、Q088-Q103、Q295；`data/02-identity-content-fields.md` §Account；`contracts/03-frontend-contract-map.md` §个人页面。
- 依赖：前置 `ACC-001`、`DEC-003`、`MED-005`；后续 `DSC-001`、`DSC-007`、`ADM-002`、`QA-003`、`QA-006`。
- 文件：profile service/query/forms/templates、avatar bridge、nickname history/tests。
- 边界：不展示完整邮箱/私有资料；头像字节由 media 所有；主题同步不覆盖访客本地选择直到登录。
- 影响：数据：Account/NicknameHistory；权限：本人修改/公开 DTO；审计：安全资料变更摘要；缓存：浏览器/账户主题；媒体：头像；通知/异步无。
- 测试/验收：RED Unicode 预算、casefold 大小写变体/并发冲突、原展示值、冷却、删除后复用但 UUID 不复用；Playwright 字段冲突、头像/主题跨设备与空公开主页。
- 风险/停止：casefold 函数不唯一、唯一性只在表单层、历史评论重新关联新账户或头像越权即停止。
- 授权：`否`。

[返回总索引](../implementation-todolist.md)
