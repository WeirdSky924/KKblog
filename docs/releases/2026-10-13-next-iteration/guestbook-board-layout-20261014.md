# 留言板居中与输入浮窗布局修正（2026-10-14）

## 用户可见变更

- 首页大图右侧留言板改为在 Hero 可视区域内上下居中，面板收起和右侧重开入口继续保持原有交互。
- 留言输入浮窗补齐独立标题栏、关闭按钮区、正文表单区和底部操作区；标题、关闭图标、取消按钮和发布图标按现有站内浮窗规范对齐。
- 窄屏下帮助文案允许换行，输入框和操作按钮保持可见，不产生横向溢出。

## 实现范围

- `static/src/discovery-home.css`：使用页眉以下 Hero 的可视高度计算面板中心；新增 `home-guestbook-dialog__header/form/actions` 布局和移动端规则。
- `apps/discovery/templates/discovery/partials/home_guestbook.html`：为浮窗增加明确的结构 class，保留既有 `confirm-dialog`、Lucide 图标和 HTMX 提交契约。
- `templates/base.html`：更新静态资源版本为 `guestbook-board-layout-20261014`。

## 验证

- 成员态模板结构回归：`apps/comments/tests/test_guestbook_board.py::test_home_guestbook_requires_member_and_publishes_plain_text`，`1 passed`；确认标题栏、表单容器和关闭图标存在。
- 目标 Ruff/format、Django check、`git diff --check` 通过；`npm run build:css` 成功。
- Labs CSS 本地与公网 SHA-256 均为 `fe65a2fdad856dc2ae657e4fe98f0d68fa32b2569531ffef375b57182baca627`，health `200`。
- Playwright 匿名首页真实读回：桌面 Hero 中心与面板中心均为 `400.5px`；390px 视口 Hero 中心与面板中心均为 `516.5px`，`scrollWidth=375`；控制台 0 error/0 warning。用当前 Labs CSS 结构化读回浮窗时，标题栏为 flex，桌面操作区横向排列，390px 弹窗宽 `358px`、操作区按既有规则纵向排列；匿名态不会渲染留言输入浮窗，浮窗内部结构由成员态回归覆盖。
- 本轮未执行生产 migration、部署、重启、招聘采集、Provider/AGENT、真实邮件或 Git 交付。
