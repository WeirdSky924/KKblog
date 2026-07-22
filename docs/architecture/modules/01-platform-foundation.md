# A. 平台基础

所有者：`config`、`apps/core`、`docker`。本模块只拥有技术协议和运行入口，不拥有任何业务规则。

## 责任与非责任

负责 settings 分层、环境变量 schema、时钟、trace/error、outbox 协议、分页值对象、健康检查、Django/Gunicorn/Celery 入口、Caddy 和开发邮件连接。

不负责账户权限、文章状态、媒体路径策略、通知模板、任务业务重试或站点可网页配置。`.env` 是部署配置；`SiteConfiguration` 是 navigation/平台的业务配置，二者不混用。

## 内部目录

```text
config/settings/{base,development,test,production}.py
config/{urls,celery,asgi,wsgi}.py
apps/core/
  errors/{codes,exceptions,handlers,redaction}.py
  events/{envelope,outbox,publisher}.py
  observability/{context,trace}.py
  time/{clock,shanghai}.py
  pagination/{offset,cursor}.py
docker/{web,caddy,scripts}/
```

文件可从小模块开始，只有职责真实增长才建立子包；禁止提前生成空目录。

## 公共契约

- `Clock.now()`：测试可注入，业务不直接散用 `timezone.now()`。
- `CommandContext`：actor、request/trace、IP、当前时间。
- `DomainError`：稳定错误码、字段映射和安全参数。
- `EventEnvelope` / `OutboxWriter`：版本化事件与提交后投递。
- `RedactionPolicy`：日志、审计、错误统一脱敏。
- `OffsetPage` / `CursorPage`：列表 DTO，不暴露 QuerySet。

## 启动门禁

- 缺失 `SECRET_KEY`、数据库、管理员初始化密码等必需变量时启动失败，错误不回显值。
- development/test 使用 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 和 Mailpit；这些值不得进入 production。
- production 缺真实域名、管理员邮箱、已认证 Resend 发件身份或密钥时关闭失败，不伪造 HTTPS 或外发成功。
- `/health/live` 只证明进程；`/health/ready` 检查数据库、必要 schema 和关键依赖。
- 健康端点不公开版本、堆栈、连接串或内部容器地址。

## 错误链

请求中间件建立 trace → View/service 抛稳定业务错误或未预期异常 → handler 映射 HTML/HTMX → 未预期错误经脱敏写 RuntimeError → 用户只见通用提示和 trace code。

## UI 表面

平台只提供基础 `base.html`、全局反馈区域、错误页、维护页和通用无障碍组件。品牌 Header、通知、导航和业务组件由对应领域拥有。

## 验证

- 每种 settings 能在隔离环境加载；缺失/非法变量明确失败。
- error/redaction 测试故意放入密码、验证码、Cookie、连接串并验证所有 sink 无泄露。
- outbox 重复发布与消费者去重。
- Compose 启动、依赖未就绪、进程退出重启、live/ready 真请求。
- 404/500/维护页在 1440 与 390、三主题和键盘路径可用。

施工依据：`contracts/04-events-errors.md`、`contracts/05-background-tasks.md`、`delivery/02-module-verification-matrix.md`。
