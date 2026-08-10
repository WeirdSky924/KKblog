# B. 账号与访问控制

所有者：`apps/accounts`。它拥有账户身份、角色、会话、邀请码、认证流程、永久 IP 封禁和安全事件。

## 边界

accounts 不知道文章如何发布；禁用/启用账户后只发领域事件，由 content 更新文章遮罩/排期。通知文案由 notifications 消费事件。验证码短期状态通过 Redis port，邮件通过 mail port 发送，并从 navigation 的只读配置端口取得当前站名与已校验模板。

## 内部目录

```text
apps/accounts/
  models/{account,role,session,invite,ip_block,security_event}.py
  services/{registration,authentication,credentials,sessions,roles,restrictions}.py
  policies/{account_access,admin_management}.py
  queries/{profile,sessions,admin_users,ip_blocks}.py
  presentation/{forms,views,presenters}.py
  events/{schemas,handlers}.py
  tests/{models,services,policies,queries,flows}/
```

## 数据与不变量

- Account UUID 永不复用；邮箱大小写不敏感唯一；昵称允许安全可见字符，按汉字 2、其他字符 1 的 16 单位预算，以 Unicode `casefold` 规范值执行大小写不敏感全站唯一，展示保留原始大小写。
- 角色只有 AUTHOR/ADMINISTRATOR；管理员最多一个且必须同时是作者。
- `attachment_upload_enabled` 是作者角色之上的独立能力，默认关闭；撤销作者角色时同步关闭。
- Session 只存 token 摘要；12 小时默认或 30 天 remembered。
- 邀请码 16 位 Crockford Base32、一次使用、1/3/7/30 天；原码只显示一次。
- IpBlock 永久有效到管理员解除；完整 IP 只在管理详情可见。
- 验证码、登录失败和发送计数可随 Redis 重启丢失；SecurityEvent 永久追溯。

## 公开服务与查询

命令：验证码请求、注册、密码/邮箱码登录、密码重置、登录态改密/改邮箱、资料/头像/主题、会话撤销、作者角色、附件能力、禁用/启用、删除账户、IP 封禁/解除。

查询：本人设置/会话、公开作者资料、管理员用户搜索/状态筛选、邀请码状态列表、IP 列表/详情。查询 DTO 默认掩码邮箱/IP。

## 关键流程

- 注册关闭时页面仍支持邀请码；邀请码先校验再允许发码，账户事务成功才消费。
- 六位验证码 10 分钟；1 分钟重发；新码覆盖旧码；第五次错误失效。
- 验证码邮件主题为“当前站名 · 邮箱验证码”，发件人显示名跟随站名，同时发送纯文本和 HTML；邮件失败时回滚新 challenge 与发送计数预留。
- 每邮箱/IP 每上海自然日各 20 次，次日 00:00 重置；管理员可清账户/IP 限制。
- 连续五次密码失败限制一小时，期间密码/码登录和密码重置均禁止；管理员可提前解除。
- 改密撤销其他会话并旋转当前；重置密码撤销全部；禁用立即撤销全部。

## 页面

登录（密码/验证码 tabs）、注册（直接/邀请码）、忘记密码、个人设置、设备会话、公开主页、管理员用户/角色、邀请码和 IP 管理。所有表单有字段错误、限制、禁用、成功和重复提交状态。

## 事件

生产：AccountRegistered、AuthorRoleChanged、AccountDisabled、AccountEnabled、AccountDeleted、CredentialChanged。消费者不得从事件 payload 获取密码、码、token 或完整邮箱。

## 验证

- 两个并发注册只允许一个消费邀请码/邮箱。
- 昵称 Unicode 计数、casefold 并发冲突、7 天冷却、删除后立即复用但 UUID 不复用。
- 五次登录、验证码五次错误、每日 20 次、Redis 清空后的安全退化。
- 唯一管理员、不可自删/撤销作者；普通作者不能进管理入口。
- 会话旋转/撤销真实 Cookie 流、IP 封禁对已登录请求也生效。

施工依据：`data/02-identity-content-fields.md`、`flows/01-account-access-state-machine.md`、`contracts/02-authorization-matrix.md`。
