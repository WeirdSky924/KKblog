# 留言板展示与管理页调整（2026-10-14）

## 用户可见变化

- 首页大图留言板扩大可用宽高；字号保持既有大小，扩展空间主要由中间留言列表承接。布局按页眉下沿、Hero 黑幕上沿和页面横向安全边距限界。
- 标题栏增加“收起留言板”按钮。用户可手动收起并通过原侧边入口重新展开；滚动至文章区时仍自动收起。
- 管理留言页面改为留言概览与逐条审核卡片，清晰展示公开/隐藏/删除状态、“阅/否/毕”标记和对应操作；继续调用现有管理服务与删除确认表单。
- 管理留言分页改用全站 `components/navigation/pagination.html`，一页时也显示当前页和禁用的前后页控制。

## 实现范围

- `static/src/home-guestbook.js`：以独立宽高限制最大 2 倍尺寸；不再缩放整个面板和文字；保存手动收起状态并管理展开/收起时的键盘焦点。
- `static/src/discovery-home.css`、`apps/discovery/templates/discovery/partials/home_guestbook.html`：列表区域吸收增量高度，标题栏新增可访问的收起按钮。
- `apps/administration/templates/administration/guestbook.html`、`static/src/administration.css`：留言管理工作台和状态卡片布局；分页复用站点组件。
- `templates/base.html`：CSS 静态资源版本更新为 `editor-image-content-width-20261014`，同时保留 JavaScript 现有版本值。

## 验证与限制

- `node --check static/src/home-guestbook.js`、两个留言板模板解析、`git diff --check` 和 `npm run build:css`、`npm run build:js` 均退出 `0`。
- Labs 服务工作目录为当前 Labs worktree 且 `active/running`；公网 `/health/live` 为 `200`；CSS/JS 静态文件 SHA-256 与本地构建一致。
- 1440×900 浏览器读回：面板 `634×468px`，位于页眉底部 `y=81px` 与 Hero 黑幕上沿 `y≈672px` 之间；留言文字 `13.76px`；面板 z-index `20`，顶部栏 `30`；页面无横向溢出。
- 本轮后续浏览器打开文章页等待 `DOMContentLoaded` 超时 60 秒，快照超时 30 秒；未完成窄屏、手动收起/展开和管理员页视觉验收，浏览器会话已关闭。管理员真实登录态未在 Labs 创建或借用。
- 没有执行数据库变更、服务重启、生产操作、Provider/AGENT 调用或 Git 交付。
