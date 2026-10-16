# 全局通知与顶部栏悬浮层级修复（2026-10-16）

## 用户可见问题

右上角全局操作通知出现时，会盖住顶部栏的悬浮菜单，导致悬浮菜单中的选项无法选择。

## 根因与修复

- 全局通知容器 `.global-feedback` 原本使用 `z-index: 80`。
- 顶部栏 `.site-header` 使用 `z-index: 30`，其内部搜索建议、通知浮窗和个人菜单都属于这个 stacking context；即使通知浮窗自身设置 `z-index: 50`，仍会被外部的 `z-index: 80` 全局通知覆盖。
- 将 `.global-feedback` 调整为 `z-index: 25`，让整个顶部栏稳定高于全局通知。通知的位置、内容、指针事件和自动消失逻辑保持不变。

## 验证

- `npm run build:css`：通过，Tailwind CSS 生成成功。
- `git diff --check`：通过。
- Labs 服务：`active/running`，公网 `/health/live=200`。
- Labs 公网 HTML 引用 `static/dist/styles.css?v=feedback-header-layer-20261016`；生成 CSS 包含 `.global-feedback{z-index:25`。
- 真实匿名首页浏览器读回 computed `site-header=30`、`global-feedback=25`；在同一页面合成一个顶部栏浮窗与通知重叠点，`elementFromPoint` 命中顶部栏浮窗，证明顶部栏 stacking context 位于通知之上。
- 没有可授权登录态，因此未读取或写入真实通知中心数据，也未创建账户。

## 范围

- 修改：`static/src/feedback.css`、`templates/base.html`、生成的 `static/dist/styles.css`。
- 未执行数据库迁移、服务重启、生产发布、真实通知写入、Provider/AGENT 调用、招聘采集或 Git 交付。
