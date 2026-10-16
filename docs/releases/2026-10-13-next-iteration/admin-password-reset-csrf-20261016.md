# 管理员重置链接 CSRF 提交修复（2026-10-16）

## 用户可见问题

打开管理员发送的重置链接可以正常显示密码表单，但提交后返回“禁止访问（403）/CSRF 验证失败”。

## 根因与修复

- Labs 服务日志记录拒绝原因为 `Origin checking failed - null does not match any trusted origins`。
- 页面同时设置了 `Referrer-Policy: no-referrer` 和同内容的 meta。当前浏览器从该页面提交密码表单时发送 `Origin: null`，Django 在进入重置 View 前拒绝请求。
- 将重置页响应头和 meta 改为 `same-origin`。Django 的 CSRF 中间件、隐藏 token、一次性重置令牌和服务端密码校验均保留。
- `same-origin` 只允许同站提交带来源信息；URL fragment 按 URL 规范不进入 Referer，因此不会把邮件中的重置令牌发送到请求头或外部站点。

## 验证

- `python -m compileall -q apps/accounts/presentation/admin_password_reset.py`：通过。
- `manage.py check --settings=config.settings.test`：通过，`0 issues`。
- `git diff --check`：通过。
- Labs 页面响应头：`Referrer-Policy: same-origin`，HTTP `200`。
- 使用同一个 Labs 页面取得的 CSRF cookie 和隐藏 token 做协议对比：`Origin: null` 返回 `403`；`Origin: https://labs.kajspace.cn` 返回 `422`；仅发送同站 `Referer` 也返回 `422`。后两者已越过 CSRF，进入不存在 UUID 重置令牌的正常业务错误路径。
- 浏览器真实复测在 GET 阶段两次遇到 Labs/Nginx `504 Gateway Time-out`，按运行规则只恢复一次后停止；没有使用真实重置令牌、没有改动账户密码、没有发送邮件。

## 范围与后续

- 修改文件：`apps/accounts/presentation/admin_password_reset.py`、`apps/accounts/templates/accounts/admin_password_reset.html`。
- 不需要 migration、服务重启或静态构建；Labs Web 热重载读取代码，健康检查和响应头已读回。
- 生产未修改。获得可授权的管理员/目标用户会话和隔离 Mailpit 后，再验证实际按钮提交、邮件链接兑换、密码登录和会话撤销。
