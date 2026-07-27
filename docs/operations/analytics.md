# Umami 同源分析运行手册

本项目固定自托管 Umami `v2.19.0`。博客全局模板只在配置完整时注入 `/analytics/script.js`；Caddy 仅公开脚本与 `/analytics/collect`，其余 Umami 页面、资源和 API 都先用博客会话确认唯一管理员。Umami 不承载文章浏览量、审计或错误事实。

本文是人工运行边界，不表示 Umami 已启动、真实流量已采集或生产分析数据已清理。启动、首次配置、真实跟踪与真实清理都需要用户当前回合明确授权。

## 必需配置

production 在任何值缺失或无效时关闭失败：

```text
KAJ_UMAMI_DATABASE_URL=postgresql://<user>:<secret>@<host>:5432/umami
KAJ_UMAMI_APP_SECRET=<至少 32 字符的随机秘密>
KAJ_UMAMI_WEBSITE_ID=<Umami 中已创建网站的 UUID>
```

数据库必须与博客主库不同。值只保存在服务器 `.env`，不得写入日志、截图、差异或提交。`KAJ_UMAMI_WEBSITE_ID` 会出现在网页 tracker 属性中，不是秘密，但 production 仍要求真实已创建的网站 ID。

## 首次准备

1. 新 Postgres 数据目录由项目 Postgres 镜像初始化 `umami` 数据库。已有数据卷不会重新执行初始化脚本，必须在维护窗口人工创建同名独立库并核对 owner。
2. 在仅内部网络可达的条件下启动 Umami，等待 `/api/heartbeat` 健康。不得给 Umami 配置宿主 `ports`。
3. 立即更换 Umami 自带管理员凭据，不能用镜像默认凭据承载真实流量。
4. 在 Umami 创建本站网站记录，核对真实域名后，将读回的 UUID 写入 `KAJ_UMAMI_WEBSITE_ID`。不得猜测或复用测试 UUID。
5. 展开 production Compose，确认只有 Caddy 发布 80/443，Umami、PostgreSQL、Redis 和 Mailpit 无宿主端口。
6. 用访客、普通用户和管理员验证：脚本/采集端点可用；普通用户及未登录请求不能读取 dashboard/API；管理员只能经博客同源入口访问。

## 一个月保留

Celery Beat 每日 03:45（Asia/Shanghai）触发 `apps.analytics.expire_umami_data`。任务通过 PostgreSQL advisory lock 单例执行，先验证固定 `v2.19.0` 表结构，再在同一事务中按依赖顺序删除严格早于执行时刻 30 天的数据。等于边界的记录保留；重复执行应删除 0 行。

任务使用统一 TaskRun，最多三次；第三次失败生成脱敏 RuntimeError、管理员站内通知和运维邮件窗口。schema 不匹配时拒绝删除，升级 Umami 后必须先更新并验证 adapter，不能跳过 schema 门禁。

## 停止条件

- dashboard/API 绕过博客管理员认证；
- Umami 或数据服务出现任何宿主端口；
- 网站 UUID 不存在或域名不匹配；
- 默认管理员凭据未更换；
- 清理影响边界内数据、schema 门禁失败或事务不能原子提交；
- 请求包含会话 Cookie、密钥或数据库连接串的日志/截图。

出现任一情况即停止，不把配置存在、容器健康或 tracker 请求成功宣称为真实分析验收完成。
