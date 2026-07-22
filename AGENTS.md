# Kaj 的小房间项目规则

本文件适用于仓库内全部文件。修改子目录前继续查找更近的 `AGENTS.md`；更近规则可以补充但不能削弱本文件的安全、测试和授权边界。

## 真值与入口

1. 当前用户指令。
2. `docs/planning/implementation-todolist.md` 及对应阶段文件。
3. `docs/planning/implementation-readiness.md`。
4. `docs/architecture/README.md` 指向的 owner、服务、数据、权限、事件和任务契约。
5. `docs/prototype/page-state-matrix.md`。

原型截图和演示代码不是业务真值。发现冲突时停止实现并记录来源与影响，不创建平行口径。

## 实施纪律

- 每次只保留一条 Todo 为 `进行中`，按前置关系顺序完成。
- 修改前先查找调用方与复用点，稳定能力只能有一个 owner。
- 有意义的行为变更执行聚焦 RED、最小完整实现、GREEN 和相关回归。
- View、Task 和模板只调用 owner 的稳定 service/query/event，不复制领域规则。
- PostgreSQL 是持久事实；Redis、缓存和锁不能成为最终裁决。
- 外部副作用在事务提交后执行，或由版本化 Outbox 驱动。
- 错误、日志、事件和审计不得包含密码、验证码、token、Cookie、连接串、正文、原路径或其他秘密。

## Git 与交付

- 首次项目写入前必须从已核验远端默认分支创建 `codex/<task>`；空仓以 `main` 初始化后再建任务分支。
- 不直接在默认分支开发，不覆盖或隐藏用户改动。
- 除非用户在当前回合明确要求，不执行 `git add`、commit、push、merge、release 或 deploy。
- 部署、生产迁移、真实邮件、生产备份和服务重启也需要当前回合明确授权。
- 完成报告必须给出新鲜命令、退出码、读回证据、未执行项和残余风险。

## 数据与环境

- 开发和测试只使用 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 与 Mailpit。
- 生产缺少真实域名、管理员邮箱、Resend 发件身份、密钥或其他必需秘密时必须拒绝启动。
- `.env`、`var/`、数据库、媒体、备份、日志和凭据不得进入 Git。
- 测试必须使用隔离 PostgreSQL、Redis、临时媒体和邮件环境，不能连接生产或共享数据。

## 用户界面

- 页面状态遵循 `docs/prototype/page-state-matrix.md`，覆盖角色、加载、空、422、系统错误、禁用、无权、成功和恢复。
- 用户可见改动使用 `/usr/local/bin/blog-playwright-cli` 验证 390、768（适用时）和 1440 视口、三主题、键盘与焦点。
- 不以静态截图、DOM 存在或 mock 代替真实点击和持久化读回。
