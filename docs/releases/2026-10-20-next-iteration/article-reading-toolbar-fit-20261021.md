# 文章阅读工具栏按钮留白与胶囊宽度修正（Labs）

日期：2026-10-21
状态：CSS 已重新构建并同步至 Labs。按用户要求未进行浏览器测试，待用户自行验收。未提交、未推送、未部署生产。

## 根因与修正

- 用户反馈此前 padding 微调后按钮仍紧贴边框，视觉没有变化。
- 根因是 `.article-reading-tools__capsule` 最大宽度仅 `12rem` 且 `overflow:hidden`；胶囊内有两个文字按钮，空间不足时按钮被 flex 收缩，溢出内容又被裁切，因而看不出单独增加 padding 的效果。
- 桌面胶囊最大宽度扩为 `22rem`；按钮设置 `flex: 0 0 auto`，不再被压缩；水平内边距加到 `1.5rem`。
- 窄屏胶囊上限按视口设为 `calc(100vw - 4.5rem)`，按钮水平内边距为 `0.75rem`，同时保留触屏宽度约束。
- 更新 CSS 查询版本为 `article-reading-toolbar-fit-20261021i`，确保重新请求新产物。

## Owner 与文件

- 样式 owner：`static/src/discovery.css` 的文章阅读工具栏胶囊与按钮规则。
- 生成文件：`static/dist/styles.css`；CSS cache key 位于 `templates/base.html`。
- 不涉及 JavaScript、数据、账户、文章正文或后台任务。

## 验证与限制

- `npm run build:css` 退出码 `0`。
- 本地和 Labs 公网 CSS SHA-256 均为 `72a614c68a55c316160b79a8c5bc7532d833eb18d9a05b6ee056173bee1a87e6`。
- Labs Web 工作目录正确且 `active/running`；`/health/live=200`。
- 用户明确表示自行测试，因此未进行浏览器/交互验收。先前浏览器启动导航超时后已关闭会话；此修正仅做本地构建、静态文件 hash 和服务健康读回。实际视觉确认由用户完成。

## 边界

- 未执行生产操作、migration、服务重启、真实邮件、招聘采集、Provider/AGENT 或 Git 写入。
