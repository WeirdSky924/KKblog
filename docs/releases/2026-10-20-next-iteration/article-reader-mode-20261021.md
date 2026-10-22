# 手机版文章阅读模式（Labs）

日期：2026-10-21

状态：功能已实现并完成静态资源构建，等待用户在手机上验收。未提交、未推送、未部署生产。

## 用户可见行为

- 手机版文章右侧快捷操作菜单新增“阅读模式”按钮；桌面视口不显示该入口。文章公开可读即可使用，无需登录。
- 阅读器提供连续滚动、左右翻页、上下逐屏三种方式；翻页模式支持触控手势、页码/屏幕进度和前后翻页按钮。
- 可切换文章目录、日间/护眼/深色主题，并将正文字号调整为 15–25px。默认 17px。
- 阅读器复用文章原正文节点。打开时以同高度占位保持原文布局，关闭时恢复原 DOM 和进入前的页面滚动位置；打开时根据当前阅读位置定位。
- 阅读方式、主题和字号只写当前浏览器 `localStorage`，不写账户偏好、服务端正文或遥测。

## Owner 与影响面

- 页面和按钮：`apps/discovery/templates/discovery/article_detail.html`。
- 模式、分页、锚点和恢复状态：`static/src/article-reader-mode.js`，由 `static/src/app.js` 生命周期管理。
- 阅读器布局及文章正文样式：`static/src/discovery.css`；手机操作栏入口：`static/src/bookmarks.css`。
- 阅读器主题映射复用站点 `light`、`eye-care`、`dark` token；静态资源缓存版本为 `article-reader-mode-20261021c`。
- 架构、页面状态和本轮公告台账同步记录；没有 API、数据库字段、migration、后台任务、邮件或第三方调用。

## 验证

- `node --check static/src/article-reader-mode.js`：退出码 `0`。
- `node --check static/src/app.js`：退出码 `0`。
- `npm run build:css`：退出码 `0`。
- `npm run build:js`：退出码 `0`。
- `git diff --check`：退出码 `0`；`kaj-labs.service` 保持 `active/running`，工作目录为当前 Labs worktree；`/health/live` 返回 `200`。
- Labs 公开文章页返回成功并读回缓存版本、阅读器入口、三种模式、字号控件和静默进度状态。生成 CSS SHA-256 `9471668285746ffb18d08e8dc96e55e4a498a530b80103b79819e919173a4f75`、JS SHA-256 `ef0320761b43cfbadbd028d0768dd08c355adc066b42efb257cb4310a9e2600c`；Labs 公网资源哈希分别与本地产物一致。
- 按用户此前的测试偏好，本轮不启动浏览器；入口显隐、三种阅读方式、字号/主题、旋转与位置恢复留给用户实机验收。

## 边界

- 本轮只更新当前 Labs worktree，未执行生产 migration、部署、服务重启、Git add/commit/push、真实邮件、招聘采集或 Provider/AGENT 调用。
- CSS 多列在长代码块、表格和嵌入内容上的分页观感尚待真实手机确认；如遇体验问题，按该切片继续修正并追加独立记录。
