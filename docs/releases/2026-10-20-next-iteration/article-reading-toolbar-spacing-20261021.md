# 文章阅读工具栏按钮内边距调整（Labs 样式微调）

日期：2026-10-21
状态：此记录中的首次 padding 微调已被 [article-reading-toolbar-fit-20261021.md](article-reading-toolbar-fit-20261021.md) 取代；用户反馈视觉上没有变化，后续定位到胶囊宽度限制才是主因。未提交、未推送、未部署生产。

## 调整内容

- 用户反馈文章阅读工具栏胶囊内按钮文字两侧留白不足。
- 首次尝试将桌面按钮 `padding-inline` 从站内通用的 `1rem` 微增到 `1.125rem`；窄屏从 `0.4rem` 增到 `0.625rem`。
- 两个胶囊按钮共用同一规则，图标、文字、颜色、布局和交互不变。

## Owner 与文件

- 样式 owner：`static/src/discovery.css` 中 `.article-reading-tools__capsule .button`。
- 生成产物：`static/dist/styles.css`。
- `templates/base.html` 只更新 CSS 查询版本为 `article-reading-toolbar-spacing-20261021h`；JS 产物和查询版本不变。
- 无数据、账户、文章内容或后台任务副作用。

## 验证

- `npm run build:css` 退出码 `0`。
- 本地及 Labs 公网 CSS SHA-256 均为 `667432b02572ae5c26c18f2d870cc8cd05e85b159f3c4d091ee397d3c851abd6`。
- Labs `kaj-labs.service` 工作目录仍为当前 Labs worktree，状态 `active/running`；`/health/live` 返回 `200`。
- 按用户要求未继续进行浏览器或交互测试。浏览器导航尝试超过 CLI 的 60 秒等待并已关闭；用户将自行检查按钮观感和布局。
- 用户随后确认这些数值变化没有带来可见效果；根因是胶囊 `max-width: 12rem` 令两个按钮受 flex 收缩并被父容器裁切。实际修复与新构建证据见后续 correction 记录。

## 边界

- 没有执行生产操作、migration、服务重启、招聘采集、Provider/AGENT、真实邮件或 Git 写操作。
