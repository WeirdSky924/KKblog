# ADR-006：本地文件系统媒体与统一媒体服务

状态：Accepted

## Context

首版单服务器，媒体要求按用户和文章目录保存，备份本地。数据库保存大二进制会增大备份与查询负担；每个模块直接操作路径又会造成越权、孤儿文件和重复校验。

## Decision

媒体字节存 `/home/code/personal-blog/var/media`，数据库保存受控相对 storage key、真实格式、哈希、用途、归属和引用。所有上传、读取授权、绑定、解绑和删除由 `media` 唯一服务完成。

采用 staging → 解码/去元数据 → 数据库登记 → 原子移动 → active 的协议。全部图片最大 2 MiB，并执行 `DEC-005` 的静态/动图解码上限；普通图片 PNG/JPEG/GIF/WebP，Logo PNG/ICO。用户输入永不参与路径拼接。

## Consequences

- 简单、低成本，符合单服务器和本地备份。
- 数据库与文件系统删除需幂等 Saga，不能假装单事务。
- 横向扩展前需要共享对象存储或粘性媒体层。
- 私人媒体不能由 Caddy 任意静态公开，必须先经服务端授权。

## Rejected alternatives

- PostgreSQL bytea：一致性好，但数据库/备份膨胀且不符合当前存储要求。
- 各领域自建上传目录：校验、安全和清理逻辑重复。
- 首版对象存储：增加凭据、网络和费用，当前没有收益。

## Revisit when

增加多实例、跨地域、CDN 或本地磁盘容量成为实测瓶颈时，用 media storage port 替换实现，业务模块保持不变。
