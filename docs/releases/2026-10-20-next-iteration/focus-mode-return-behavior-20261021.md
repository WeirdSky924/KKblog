# 专注模式边缘范围与焦点返回恢复（Labs 修正）

日期：2026-10-21
状态：代码已更新至 Labs 并完成真实 app bundle 的状态事件验证；没有截图像素验收。未提交、未推送、未部署生产。

## 修正内容

- 用户反馈边缘光效向内容区扩散得太远，并且离开后返回页面仍保留红色光效、计时没有继续。
- 缩小全屏边缘晕染：上下径向渐变高度由 `62%` 缩至 `22%`，左右宽度由 `76%` 缩至 `24%`；最大模糊从 `34px` 降至 `18px`，内阴影最大半径从 `144px` 降至 `56px`。黄/红提示仍保留循环脉动，但范围集中在视口边缘。
- 窗口失焦、页面进入后台或鼠标离开时，专注自动暂停并记录“返回后恢复”。页面重新获得焦点、重新可见或鼠标重新进入时，若暂停来自上述离开事件，就自动开始新的计时片段并清除边缘状态。
- 手动暂停、无操作超时和用户主动退出全屏仍保持暂停，需点击继续；自动返回不会增加手动暂停次数。

## Owner 与文件

- 状态与事件 owner：`static/src/article-focus.js`。
- 边缘效果 owner：`static/src/discovery.css`；生成产物 `static/dist/styles.css`。
- `templates/base.html` 静态资源版本更新为 `article-focus-return-20261021g`。
- 无数据库、配置、账户、文章内容或后台任务副作用。

## 验证

- `node --check static/src/article-focus.js`、`node --check static/dist/app.js`、`npm run build:css` 与 `npm run build:js` 均退出码 `0`。
- Labs 匿名主页实际加载 `article-focus-return-20261021g`。用临时 DOM 夹具和实际 app bundle 触发状态事件：
  - `window blur` 后读回 `auto-paused + warning`；`window focus` 后读回 `active`、计时可见、`body` 边缘状态已清除。
  - 鼠标 `pointerout` 后读回 `auto-paused + warning`；页面 `pointerover` 后读回 `active`、边缘状态清除。
  - 手动暂停后派发 focus 仍为 `manual-paused + paused`；结束专注后变为 `off` 且无边缘状态。
- 实际 computed style 读回上下渐变 `120% × 22%`、左右渐变 `24% × 120%`、动态 blur `7–18px`、内阴影 `12/30/56px`。这证明最终窄范围样式已加载，不代表完成截图级观感验收。
- 本地与 Labs 公网 SHA-256 一致：CSS `6feedc6d28ec5e4677c9d9d80eb9b8027da28832ad849da508119f8d6abff59d`；JS `dfbf689ad4ed6e7ea1d063a5f80bc7d8873a3b910aeab125144feb9c507a905a`。首页静态版本正确，`/health/live=200`，`kaj-labs.service` 为 `active/running` 且工作目录仍为 Labs worktree。
- 浏览器检查通过临时 DOM 和合成 window/pointer 事件验证 app bundle 的处理函数；没有认证态文章页面和操作系统级窗口切换。截图工具此前因字体等待超过 5 秒限时，本次没有重试，因此用户仍可在 Labs 上确认实际光晕观感。

## 边界

- 未执行 migration、生产操作、服务重启、真实邮件、招聘采集、Provider/AGENT 调用或 Git 写操作。
- 浏览器结束后已关闭；临时 DOM 留在该浏览器页面中但随会话关闭销毁，没有服务端数据变化。
