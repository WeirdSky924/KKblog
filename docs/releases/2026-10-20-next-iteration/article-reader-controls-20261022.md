# 手机版阅读模式翻页与设置显隐（Labs 修正）

日期：2026-10-22

状态：交互已调整并完成静态资源构建和 Labs 读回；等待用户实机验收。未提交、未推送、未部署生产。

## 修改内容

- 左右翻页改为阅读视口三等分点击：左侧上一页、右侧下一页、中间切换顶部设置显隐。第一次侧区翻页后收起顶部标题和设置，点击中间区域可重新显示。
- 移除底部上一页/下一页按钮，页码独自居中。键盘焦点位于正文时，左右方向键翻页，Enter/空格切换顶部设置。
- 左右翻页内容在内层视口边界裁切，列宽和翻页步长使用同一可视内容宽度；翻页时不会露出相邻页边缘。
- 上下翻页改为整屏离散步进：上划前进一页、下划后退一页，正文不会跟随手指连续滚动；保留系统双指缩放。页码随每次手势更新。

## Owner 与影响面

- 状态和手势：`static/src/article-reader-mode.js`。
- 裁切、设置显隐和页码布局：`static/src/discovery.css`。
- 底部控件移除：`apps/discovery/templates/discovery/article_detail.html`。
- 静态版本：`article-reader-controls-20261022a`。
- 更新 discovery 架构、文章页面矩阵、post-P12 ITER-004 和本轮公告台账；无服务端状态、API、数据库或 migration 变化。

## 验证

- `node --check static/src/article-reader-mode.js`、`git diff --check`：退出码 `0`。
- `npm run build:css`、`npm run build:js`、`node --check static/src/article-reader-mode.js`、`git diff --check`：均退出码 `0`。
- Labs 文章页读回缓存版本 `article-reader-controls-20261022a`、阅读模式与页码控件；原有上一页/下一页按钮标记已从模板移除。`kaj-labs.service` 保持 `active/running` 且指向当前 Labs worktree，`/health/live=200`。
- CSS/JS 本地 SHA-256 分别为 `8718e90464ed6766e9d645d9e77836b777750ed7253f22d057f7d79e74da9c4f` 和 `5f22b729e48831c3f2a305b2f8fb7de8c1ef6622c5956120a84cb6b997e92610`；Labs 公网资源哈希完全一致。
- 按用户先前的测试偏好不启动浏览器；左右区域、设置显隐、上下单手势和邻页裁切由用户在手机上验收。

## 边界

- 仅同步 Labs 源码和静态资源，不重启服务；没有生产操作、migration、Git 写入、真实邮件、招聘采集或 Provider/AGENT 调用。
- 无浏览器实测，最终触控区域和不同文章内容类型的分页观感以用户验收为准。
