# 留言板尺寸稳定与滚轮归属（2026-10-15）

## 问题与根因

用户复测发现，发布留言后留言板仍会缩回基础尺寸；在留言区滚轮时，整页被主页滚动吸附逻辑带走。

发布接口会用 HTMX `outerHTML` 替换整个 `home-guestbook-shell`。放大宽高变量保存在将被替换的面板节点上，依赖提交前快照和 after-swap 恢复；用户通过真实入口复现说明这条恢复路径未能可靠保留布局状态。由于本轮没有认证请求 trace，无法确认具体在哪个 HTMX 事件时序丢失；修复让尺寸状态由不会被该响应替换的首页容器持有，消除对该时序的依赖。

`home-navigation.js` 在主页 Hero 区监听页面级 `wheel`，原来只跳过左侧导航。滚轮事件从留言列表冒泡后被主页吸附逻辑处理，因而列表的 `overflow-y:auto` 没有获得默认滚动；单靠 `overscroll-behavior: contain` 无法阻止祖先监听器主动拦截事件。

## 修复

- `static/src/home-guestbook.js`：把居中位置、宽度和高度 CSS 变量写到稳定的 `[data-home-page]`。重新测量基础尺寸时只临时移除页面宽高变量；测量无效时恢复旧值。HTMX 替换后的新面板直接继承页面变量，不再依赖节点快照。
- `static/src/home-navigation.js`：主页吸附滚轮监听忽略 `[data-home-guestbook-panel]` 内事件；留言列表继续由自己的滚动容器处理滚轮，CSS 保留 `overscroll-behavior: contain`。
- `templates/base.html`：将 app bundle 查询版本更新为 `guestbook-board-scroll-stable-layout-20261015`，让 Labs 页面读取新代码。

## 验证

- `node --check static/src/home-guestbook.js`、`node --check static/src/home-navigation.js`、`git diff --check`：均退出 `0`。
- `npm run build:js`：退出 `0`。
- Labs `kaj-labs.service` 为 `active/running`，`/health/live=200`。本地和公网 app bundle SHA-256 均为 `aa2e793006f3d077a006aa5ce20208ed7c09080f80b45b9867600fb2ab894ac2`。
- 访客态真实页面加载新 bundle；浏览器通过 `htmx:beforeRequest`、整块 shell 替换和 `htmx:afterSwap` 验证：1440×900 下替换前后均为 `634×468px`。
- 在留言内容上使用真实浏览器滚轮：列表 `scrollTop` 从 `0` 到 `23px`（当时可滚动最大值），`window.scrollY` 保持 `0`；捕获到的 wheel target 位于留言列表，事件未被阻止。
- 390×844 下留言板 `355×465.4px`，顶部 `189px` 与站点栏底部一致，底部 `654.4px` 与 Hero 内容边界一致；`documentElement.scrollWidth=375px`，无横向溢出。截图已按原始分辨率检查，临时截图已清理；浏览器控制台和 page error 均为 `0`。

## 边界

当前没有可授权的 Labs 登录态，本轮未实际提交认证留言；浏览器验证使用访客页面和等价 HTMX DOM 替换路径。正式生产未改动，未执行 migration、部署、服务重启、招聘采集、Provider/AGENT 调用、真实留言写入或 Git 操作。
