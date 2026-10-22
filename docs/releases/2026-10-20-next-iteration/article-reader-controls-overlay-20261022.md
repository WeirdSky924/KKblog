# 手机版阅读模式设置浮层不挤压正文（Labs 修正）

日期：2026-10-22

状态：已构建并在 Labs 读回；等待用户手机验收。未提交、未推送、未部署生产。

## 修改内容

- 左右和上下分页模式的标题栏和设置栏改为覆盖正文上方的浮层，显示时不再参与正文视口的 flex 尺寸计算；显示设置不会压缩正文、改变可见页尺寸或触发重新分页。
- 左右模式继续由中间区域切换设置；上下模式单击正文切换设置，上下滑动仍一次翻一页。滑动翻页后隐藏设置，正文视口维持同一尺寸；连续滚动模式继续使用原有纵向控件布局。
- 控件沿用阅读器已有的面板背景和交互样式，不改变字号、主题或设置内容。

## Owner 与影响面

- 结构：`apps/discovery/templates/discovery/article_detail.html`。
- 覆盖层定位、层级与点击穿透：`static/src/discovery.css`。
- 产品契约：`docs/architecture/modules/05-discovery-reading.md` 与 post-P12 ITER-004。
- 静态版本：`article-reader-overlay-20261022c`。前端增加上下模式单击切换设置；没有 API、数据库、迁移或后台任务改动。

## 验证

- `npm run build:css`、`git diff --check`：退出码均为 `0`。
- Labs 文章页响应 `200`，读回覆盖层模板 class 和静态版本 `article-reader-overlay-20261022c`；`/health/live=200`。`kaj-labs.service` 仍为 `active/running`，工作目录指向当前 Labs worktree，没有重启服务。
- 本地及 Labs 公网 CSS SHA-256 一致：`8c44cd23089754bfe7be42cede38623f3e5822a200b883266b764c00274472b6`；app JS SHA-256 一致：`f3e262fc7a6aea25afdcff3e29c95f8749940d0271839d14b64176c34b3e97ee`。
- `node --check static/src/article-reader-mode.js` 退出码 `0`；`npm run build:css`、`npm run build:js`、`git diff --check` 均退出码 `0`。
- 按用户偏好没有启动浏览器；设置浮层实际遮挡范围、正文可读性和手机分页观感由用户验收。

## 边界

- 未执行生产操作、migration、服务重启、Git 写入、招聘采集、真实邮件或 Provider/AGENT 调用。
