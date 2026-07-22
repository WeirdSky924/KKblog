# D. 媒体与安全渲染

所有者：`apps/media` 负责媒体字节、元数据、绑定和访问；统一 sanitizer 可置于 `apps/media/rendering` 或独立受控包，但只能有一个实现中心。

## 内部目录

```text
apps/media/
  models/{asset,binding}.py
  services/{uploads,bindings,access,cleanup}.py
  storage/{port,filesystem}.py
  imaging/{detect,sanitize,gif,ico}.py
  rendering/{markdown,tiptap,html_policy,embeds}.py
  policies/{asset_access,capacity}.py
  queries/{asset_info,admin_media}.py
  tasks/{cleanup,staging}.py
  presentation/{upload_views,partials}.py
  tests/
```

## 统一规则

- 所有图片最大 2 MiB。静态图最长边不得超过 `8192`，总解码像素不得超过 `25 MP`；动图不得超过 `200` 帧，累计解码像素不得超过 `100 MP`。显示尺寸不预设固定分辨率，但这些解码硬上限不可绕过。
- 普通图片 PNG/JPEG/GIF/WebP；Logo 仅 PNG/ICO；依据真实签名和成功解码，不信任 MIME/扩展名。
- 去除 EXIF/相似元数据；GIF 安全重编码并保持动画。
- storage key 由服务生成，路径不得含邮箱、昵称、原文件目录或用户 `../`。
- Asset 先 STAGED，绑定与原子移动成功后 ACTIVE；私有/未绑定资产不可直接访问。

## 用途与数量

| 用途 | 格式 | 数量/归属 |
| --- | --- | --- |
| Avatar | 普通图片 | 每用户当前一个 |
| Article cover | 普通图片 | 每修订零或一个，空则默认封面 |
| Article body | 普通图片 | 多个，按用户/文章归属 |
| Comment | 普通图片 | 仅顶层评论最多三个 |
| Report/appeal evidence | 普通图片 | 每次提交最多三个，严格私有 |
| Site logo | PNG/ICO | 当前一个，兼作 favicon |
| Friend logo | 普通图片 | 每链接一个 |

仓库提供语义分离的本地品牌资产：`1600x900` 默认文章封面与 `800x450` 失效收藏图。资产由 media/brand 入口交付；本决策不表示当前文件已经制作或入库。

## 服务边界

`stage_upload`、`bind_assets`、`replace_bindings`、`authorize_asset_read`、`delete_unbound_assets`。目标领域传稳定对象和用途，media 调目标注册的 access port；双方不直接访问对方私有表/路径。

正文/TipTap 只保存 media ID，不保存任意服务器路径。外部链接不成为 MediaAsset；导入图片先暂存、确认文章成功后绑定。

## 安全渲染

- Markdown、TipTap、作者 HTML 和导入预览走同一 allowlist。
- 删除 script、事件属性、危险协议、任意 iframe/raw HTML 执行。
- 外链 `target=_blank` 且带安全隔离属性。
- Embed 只匹配管理员启用的主机/路径规则，初始仅 Bilibili；来源移除显示“来源不可用”。
- sanitizer 规则版本进入渲染缓存键；升级后旧缓存整体失效。

## 生命周期与失败

解除引用/评论删除提交后立即删文件，失败标 DELETE_PENDING 并重试。文章软删除期只禁止授权读取，不删文件；到期数据库先解除绑定，再幂等删文件。文件已不存在视为清理成功，数据库回滚前禁止先删文件。

磁盘低于 5% 拒图片；低于 2% 所有内容创建也拒绝。服务端 CapacityPolicy 是最终门禁，前端提示不是授权。

## UI

统一媒体选择器处理拖放/选择、格式与大小错误、上传进度、预览、移除和失败重试。用途页面可定制裁切预览，但不能绕过上传入口。移动端文件选择和长错误文案需可达。

## 验证

伪造 MIME/双扩展、坏图、超 2 MiB、静态图 `8192`/`25 MP` 边界、动图 `200` 帧/`100 MP` 累计边界、EXIF、GIF 动画、ICO；路径穿越/符号链接；他人/私人资产直接 URL；绑定数量；数据库提交与文件移动/删除崩溃；低磁盘自动限制/恢复。

施工依据：`data/03-interaction-operations-fields.md`、`data/05-storage-lifecycle.md`、`adr/ADR-006-filesystem-media.md`。
