# 留言提交后保留留言板尺寸（2026-10-15）

## 问题

首页留言板提交留言后通过 HTMX 替换整个留言板 shell。放大后的宽高保存在旧面板的 CSS 自定义属性中，新节点如果没有及时重新接收这组属性，就会回落到基础面板尺寸，导致中间留言内容区域被压缩；重新触发展开流程后才可能恢复。

## 修复

- `static/src/home-guestbook.js`：提交前记录当前留言板宽高变量和视口尺寸；outerHTML 替换后定位真实的新 target，先重新计算安全边界，再在同一视口恢复原有宽高。
- 只对留言表单保存待恢复状态，加载更多请求不会覆盖提交状态。
- `templates/base.html`：更新 JS 资源版本为 `guestbook-board-post-submit-layout-20261015`，避免继续使用旧缓存。

## 验证

- `node --check static/src/home-guestbook.js`、留言板模板解析、`git diff --check` 通过；`npm run build:js` 成功。
- 浏览器模拟真实 HTMX 链路：提交前触发 `htmx:beforeRequest`，替换整个 shell，再触发 `htmx:afterSwap`。1440/1280 桌面读回替换前后均为 `576×411.4px`；390×844 窄屏替换前后均为 `355×465.4px`。
- 窄屏 `scrollWidth=375`、`clientWidth=390`，无横向溢出；控制台错误和警告均为 `0`。
- Labs `active/running`，`/health/live=200`；本地与公网 `app.js?v=guestbook-board-post-submit-layout-20261015` SHA-256 均为 `a4b3d7c621411c2b7cdc1d87d9049cdeda2250d970aa58f75052a5442511df9a`。
- 本轮未使用真实登录账号提交留言，未执行数据库变更、生产操作、服务重启、招聘采集、Provider/AGENT 调用或 Git 交付。

## 后续复现补充（2026-10-15）

用户随后通过真实发布入口复测，留言板仍会缩小。因此，上述浏览器事件模拟只能证明当时构造的事件顺序下尺寸一致，不能证明真实认证发布流程已经修复。此前关于具体 HTMX target 事件时序的判断没有真实请求 trace 支持；后续实现直接消除对被替换节点及其恢复事件的依赖，见 [`guestbook-board-scroll-stable-layout-20261015.md`](./guestbook-board-scroll-stable-layout-20261015.md)。
