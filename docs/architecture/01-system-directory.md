# 系统目录与依赖边界

## 建议目录

```text
personal-blog/
  config/                 # Django settings、ASGI/WSGI、URL 根入口、Celery 入口
  apps/
    core/                 # 纯技术基础：错误、时间、配置接口、通用类型
    accounts/             # 用户、认证、会话、验证码、角色、IP 封禁
    content/              # 文章、版本、草稿、分区、标签、发布和删除
    media/                # 上传、校验、存储、引用和清理
    discovery/            # 公开阅读、搜索、书签、SEO、主题偏好
    comments/             # 评论、留言板、树、缓冲、排序和删除占位
    moderation/           # 举报、申诉、管理员内容动作与终局裁决
    authoring/            # 编辑工作台、冲突、导入预览、作者评论管理
    administration/       # 管理员文章/用户/设置/导航/邀请码入口
    notifications/        # 通知投递、已读、聚合、群发
    navigation/           # 导航树、静态页、友情链接和公开站点结构
    operations/           # 审计、错误日志、磁盘、备份、部署状态
    exchange/             # ZIP 导出、Markdown 导入、归档清理
    analytics/            # Umami 管理入口与数据清理
  templates/              # 基础布局、共享片段；领域模板留在对应 app/templates/
  static/                 # Tailwind 输入、非用户上传资源
  tests/                  # 跨模块/端到端测试；模块内测试贴近实现
  docker/                 # Dockerfile、Caddy、启动脚本
  docs/architecture/
  var/                    # postgres、media、backups、logs；不入 Git
```

## 每个领域 app 的内部结构

```text
apps/<domain>/
  models/                 # 按聚合拆分，避免巨型 models.py
  services/               # 命令式应用服务和事务边界
  queries/                # 面向用例的读取与展示 DTO
  policies/               # 服务端权限与 capability
  events/                 # 本域事件 schema、handler 和 outbox consumer
  tasks/                  # 仅调用服务的 Celery 入口
  presentation/           # forms、views、presenters 与 HTTP 转换
  urls.py
  templates/<domain>/
  tests/
```

当领域很小，可暂用单个 `models.py`、`services.py` 或 `queries.py`；职责增长后按聚合拆分，不提前制造空目录。`public.py` 或包级显式导出定义跨 app 入口，内部模型不作为公共 API。

## 依赖规则

```text
presentation (templates/views/htmx)
  -> application services / queries
    -> domain models + policies
      -> infrastructure ports (storage, mail, cache, task enqueue)
```

- `accounts` 不依赖 `content`；内容只依赖账户公开的 actor/role 查询。
- `content` 拥有文章生命周期，`media` 拥有文件生命周期；内容不直接拼文件路径。
- `comments` 不直接修改文章；它只通过内容公开的讨论目标策略确认父对象。
- `moderation` 拥有案件和裁决，但通过 `comments`/`content` 服务执行目标删除或恢复。
- `notifications` 不读取业务表实现，只消费明确事件和接收者标识。
- `navigation` 拥有导航树与静态公开结构；`discovery` 只读取已发布视图。
- `authoring` 与 `administration` 是入口/编排层，不成为第二套业务实现；它们委托各领域服务。
- `operations` 可记录所有领域审计事件，但不得反向承载业务策略。

允许的高层依赖方向：

```text
authoring --------> content / media / comments / exchange
administration ---> accounts / content / comments / moderation / notifications / navigation / operations
discovery --------> content public queries / comments public queries / navigation public queries
content ----------> accounts public / media public / operations public
media/comments/moderation -------------> operations public
domain app -------> core protocols
domain event -----> outbox -----> other domain consumer
```

领域 app 之间出现同步循环时，先判断哪一方才是事实所有者；必须协作时通过窄 service port 或提交后事件，不建立共享万能 service。

## 共享能力

仅允许下列横切能力放入 `core`：错误编码、时钟、UTC/上海时间转换、请求上下文、事件/outbox 协议、可审计命令接口、通用分页值对象。不得将文章、权限、媒体、通知、重试策略或“万能 repository”塞入 `core`。

## 命名与契约

- 命令用动词：`publish_article`、`disable_account`、`review_report`。
- 查询用名词或问题：`visible_articles_for`、`unread_notifications_for`。
- 事件用过去式：`ArticlePublished`、`CommentDeleted`、`AccountDisabled`。
- 模板片段按用户动作命名，例如 `content/partials/article_card.html`，不使用 `common2` 或 `misc`。
- 跨 app 只暴露服务、查询和事件；不从外部导入另一个 app 的私有模型实现细节。

## 配置目录

```text
config/settings/
  base.py                  # 共用设置与必需环境变量 schema
  development.py           # Mailpit、debug toolbar（若采用）
  test.py                  # 隔离数据库、同步哈希优化、测试媒体
  production.py            # Secure Cookie、HTTPS、日志与主机
config/urls.py
config/celery.py
config/asgi.py
config/wsgi.py
```

生产值只来自服务器 `.env`；网页设置属于数据库 `SiteConfiguration`，两者不能混用。秘密不存在时启动明确失败，不读取默认弱密码。

## 测试布局

- `apps/<domain>/tests/`：模型、policy、query、service、task 的同域测试。
- `tests/contracts/`：事件 schema、跨域公开 API 和 import 边界测试。
- `tests/integration/`：真实 PostgreSQL、Redis、临时媒体和 worker 行为。
- `tests/e2e/`：Playwright 四身份关键用户流与视觉断言。
- `tests/fixtures/`：最小工厂/样本，禁止复制生产数据或真实秘密。
