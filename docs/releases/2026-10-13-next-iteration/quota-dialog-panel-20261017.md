# 用户配额覆盖弹窗样式统一（2026-10-17）

## 用户可见问题

在用户管理中点击“配额覆盖”后，账户配额弹窗只显示基础确认框结构，标题区、关闭按钮区和内容间距没有沿用首页留言输入窗口的完整样式。

## 实现

- 在 `static/src/feedback.css` 增加共享 `confirm-dialog-panel` 外壳，统一处理弹窗宽度、遮罩、顶端强调线、标题栏、关闭按钮、内容表单间距、操作区和移动端内边距。
- 首页留言输入弹窗组合共享类并继续保留留言文本域、字符计数和帮助文案的专属样式。
- 用户配额覆盖弹窗组合同一共享类，保留既有账户信息、五项配额字段、版本字段和保存行为；更新 `templates/base.html` 的 CSS cache version。

## 验证

- `npm run build:css`：通过。
- `manage.py check --settings=config.settings.test`：通过，`0 issues`。
- `git diff --check`：通过。
- Labs service：`active/running`，公网 `/health/live=200`。
- Labs 公网 HTML 引用 `static/dist/styles.css?v=quota-dialog-panel-20261017`。
- 真实 Labs 页面加载新 CSS 后，以账户配额弹窗的实际 class/DOM 结构做浏览器布局读回：桌面视口下宽度 `512px`、顶端线 `4px`、标题区最小高度 `72px`、表单内边距 `20px`；390px 下宽度 `358px`、内边距 `16px`、五项配额字段单列，`body.scrollWidth=375`，无横向溢出。
- 当前没有可授权管理员 session，因此没有点击真实用户管理入口、提交真实配额或改变数据库；临时 DOM 已在读回后移除，浏览器已关闭。

## 范围

- 修改：`static/src/feedback.css`、`static/src/discovery-home.css`、`apps/discovery/templates/discovery/partials/home_guestbook.html`、`apps/administration/templates/administration/learning_question_banks.html`、`templates/base.html`、生成的 `static/dist/styles.css`。
- 未执行数据库迁移、服务重启、生产发布、真实配额写入、Provider/AGENT 调用、招聘采集或 Git 交付。
