# ITER-001 Goal：注册通知与一次性作者权限申请

## 目标

闭合新账户注册通知、普通用户作者权限申请、管理员定位用户和作者原工作台兼容路径；最终在隔离测试库和经授权的 Labs schema 上验证。

## 完成条件

- `register_account` 只在账户事务成功时写入一个 `account.registered.v1` Outbox event；管理员收到幂等站内通知。
- 已登录普通用户从 `authoring:articles` 进入申请状态，提交一次后 Account 时间戳持久化，按钮替换为已通知文字；重复/并发提交不多写事件。
- 通知只包含稳定账户 ID，链接到管理员用户列表中唯一匹配的账户；现有管理员确认授予作者角色流程不变。
- 作者看到原有文章工作台，普通用户不能调用创建/编辑等其它作者命令，未登录仍跳登录。
- 目标 PostgreSQL 迁移、通知/Receipt 数据读回、受影响 Labs 页面与授权视口验证完成，或明确记录因缺少迁移授权而未完成。

## 范围和停止条件

只改 accounts、notifications、authoring、用户管理搜索、对应契约与本轮公告。不得发送邮件、调用 Provider/AGENT、执行招聘采集、生产 migration/deploy/restart 或 Git 交付。Labs migration 需用户在当前回合明确授权；Outbox 服务失败需另案修复，不得清理事件。
