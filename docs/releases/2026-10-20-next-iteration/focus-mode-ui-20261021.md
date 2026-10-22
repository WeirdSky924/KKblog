# 专注模式左下计时区与状态流光（Labs UI 调整）

日期：2026-10-21
状态：已更新至 Labs，并完成浏览器状态与布局读回；初版光效强度经用户反馈不足，已在 [focus-mode-edge-burn-20261021.md](focus-mode-edge-burn-20261021.md) 补强。两轮截图均未完成像素级检查；未提交、未推送、未部署生产。

## 当前交互

- 文章阅读工具栏内只保留“专注模式/结束专注”入口。专注开始后，左下角计时区以单行显示时长、圆形暂停/继续图标和手动暂停次数；时间和 `已暂停次数/上限` 是无背景纯文本，圆形按钮只显示 Lucide 图标。
- 手动暂停显示黄色边界流光；失焦、页面进入后台、鼠标离开或无操作等自动暂停警告显示红色边界流光；正常计时、结束会话时无流光。结束后清除页面状态，流光不拦截点击。
- 使用站点 warning/danger token 与明黄/鲜红混色，保证浅色、深色、护眼主题中颜色仍符合黄色/红色语义。减少动态效果时停止流动动画并保留状态边缘标记。
- 更正：此前只有状态、颜色和布局读回，没有成功截图；这些证据不能证明光效足够明显。用户实测后反馈光效短暂且偏弱，已改为更宽的全页燃烧式晕染，详见独立修正记录。

## Owner 与文件

- `static/src/article-focus.js`：暂停图标/继续图标显隐及页面状态信号。
- `apps/discovery/templates/discovery/article_detail.html`：工具栏专注入口与工具栏外左下计时区 DOM。
- `static/src/discovery.css`：左下单行控件、窄屏工具栏避让、圆形图标控件、页面边缘流光与响应式规则。
- `templates/base.html`：更新 CSS/JS 静态缓存版本。

## 验证

- `node --check static/src/article-focus.js`、Django `check --settings=config.settings.test`、文章详情模板编译、`git diff --check` 通过。
- `npm run build:css` 与 `npm run build:js` 均退出码 `0`。Labs `/health/live=200`；最终 CSS SHA-256 `24dbce7bfc59401431c31e95781e18946fb701c41104790d54d3d93c2a99e1a7`，JS SHA-256 `0ac8319063bbdbb156b1b155e0845d0209afef055f417e25b40e0df535339cba`，本地和公网读回一致，HTML 静态版本为 `article-focus-toolbar-20261021c`。
- 固定浏览器在 Labs 公开文章中挂载临时 DOM 夹具并触发实际 bundle 的 `htmx:load` 初始化。通过 DOM click 事件读回手动暂停 `1/3`、继续图标、`50%` 圆形按钮、黄色流光；失焦事件读回自动暂停和红色流光；结束后控件隐藏且边缘 opacity 为 `0`。这不是认证态鼠标用户流。
- 390/768/1440 视口几何读回中计时区分别位于左下 `x=12..101`、`20..119`、`20..119`；工具栏与计时区均无重叠；文档宽度分别为 `375/753/1425`，未横向溢出。暂停按钮焦点可见样式读回 `:focus-visible=true`；浅色、深色、护眼主题均读回黄色/红色混色值。
- `blog-playwright-cli screenshot` 两次均在 `5s` 截图门限超时，没有生成截图；因此未完成原尺寸截图的像素级视觉检查。验收结束已关闭浏览器。
- 浏览器使用匿名公开文章和临时 DOM 夹具，没有认证态工具栏入口或真实用户手势全屏成功路径；全屏成功仍待用户实机确认。

## 边界

- Labs 服务保持 `active/running`；未进行 schema/data 写入、生产操作、服务重启、真实邮件、招聘采集、Provider/AGENT 调用或 Git 写入。
- 完整全屏成功路径仍待用户在正常登录浏览器中确认；headless 环境先前因浏览器用户手势策略拒绝全屏，降级为普通页面继续的行为不变。
