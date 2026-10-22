# 登录用户文章专注模式（Labs 迭代记录）

日期：2026-10-21
状态：功能已实现并同步至 Labs；未提交、未推送、未部署生产。

## 用户入口与行为

- 只在登录用户查看公开文章时，沿用现有 `article-reading-tools` 工具栏及胶囊增加“专注模式”；不改匿名页面可见性或工具栏外层结构。
- 开启后请求浏览器全屏，左下角显示无背景的累计计时；计时用单调时钟累计活动片段，不保存用户级历史或遥测。
- 用户可以手动暂停/继续。每次开始新的活动片段后恢复计时；第三次手动暂停结束本次专注并隐藏计时。
- 页面失焦、进入后台、鼠标离开页面或达到无操作阈值时自动暂停并提醒；自动暂停不计入手动次数。退出全屏会自动暂停，用户可继续或结束。
- 若浏览器拒绝全屏，专注计时仍可在普通页面继续并给出提示。网页不强抢其他标签页或操作系统焦点。

## 管理配置与数据

- 管理员在“内容与互动 → 文章阅读设置”配置无操作阈值（默认 3 分钟，范围 1–15 分钟）和单次手动暂停上限（默认 3 次，范围 1–10 次）。配置使用既有 `SiteConfiguration` 版本校验、权限检查和审计 owner。
- 新增 `navigation.0009_focus_mode_settings`。Labs `kaj_test_production_clone` 已应用迁移；本次只读读回确认 migration 记录、`site_configuration` 两列、默认值 `3/3` 及 `1–15`、`1–10` 范围约束。本次未执行 migration。
- 页面计时状态仅存在当前页面内存中。刷新或离开页面结束本次会话；新设置在重新打开文章页面后生效。

## Owner 与实现文件

- 配置 owner：`apps/navigation` 的 SiteConfiguration、query/service、审计 schema；管理入口由 `apps/administration` 承载。
- 文章入口 owner：`apps/discovery` 页面查询、上下文和模板；客户端状态集中在 `static/src/article-focus.js`，阅读工具样式在 `static/src/discovery.css`。
- 相关契约、管理页面矩阵和 P12 后迭代清单已同步更新；独立台账见 `announcement.md`。

## 验证

- 聚焦回归：

  ```text
  KAJ_TEST_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:57432/kaj_test_focus_mode_e2e \
    .venv/bin/pytest --reuse-db -q apps/navigation/tests/test_nav005_focus_mode_settings.py apps/discovery/tests/test_article_focus_toolbar.py
  ```

  结果：`11 passed in 199.74s`，退出码 `0`。覆盖默认值、范围、非管理员拒绝、版本冲突、审计、管理保存读回、匿名不显示工具及登录文章配置注入。
- Ruff 对 13 个相关 Python 文件的 check 和 format check 均通过；`node --check static/src/article-focus.js`、`npm run build:css`、`npm run build:js` 均退出码 `0`。Django 本地隔离服务启动检查报告 `0 issues`。
- 管理员浏览器页和隔离文章页均返回 `200`；默认配置读回 `3/3`。专注开始后计时在 3 分钟无操作时进入自动暂停并显示 `03:00`；状态机读回 `1/3`、`2/3`、第三次手动暂停结束会话。状态机后半段通过页面 DOM 事件验证，因为 CLI 定位点击持续超时。
- 390、768、1440 视口下工具栏无横向溢出。Headless 浏览器报告 `requestFullscreen` 需要用户手势，未能验证真实浏览器成功全屏；全屏拒绝时普通页面继续的代码路径保留。管理员设置页的浏览器输入操作也因 CLI 可见/稳定等待超时未完成；Django 客户端保存和数据库读回通过。
- Labs service 工作目录仍为本 Labs worktree，状态 `active/running`；公网 `/health/live` 与 `/health/ready` 均为 `200`。CSS SHA-256 `615b20fc91c5405d08fe8c89b85fbab90036aeae87f8bf97f69e092d458df2ca`，JS SHA-256 `8e17c4e03a08df89b60ae0e7eabfafb5b25fe9dc1fba0d930900d1a37c081634`；公网文件哈希与本地构建产物一致。
- 验收后关闭 `focus-mode` 浏览器会话及本地 `8766` 服务；删除本次创建的 `/tmp` 会话状态与 seed 脚本。临时隔离数据库 `test_kaj_test_focus_mode_e2e`、`kaj_test_focus_mode_e2e` 在核对 owner 与连接数后删除；`kaj_test_production_clone` 保留。

## 发布与副作用边界

- 本轮没有生产 migration、部署、重启、真实邮件、招聘采集、Provider/AGENT 调用或 Git 写操作。
- Labs Web/Worker/Beat 保持运行；Outbox 历史状态未改变。正式发布需要独立授权和本轮正式公告。
