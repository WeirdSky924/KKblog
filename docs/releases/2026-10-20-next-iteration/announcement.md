# Kajspace 下一轮 Labs 迭代公告台账（2026-10-20）

状态：正式基线与 Labs 环境已确认；ITER-004 手机版文章阅读模式已实现并完成 CSS/JS 构建，等待用户手机验收。ITER-003 专注模式的最终光效观感和全屏成功路径也仍待用户确认。本台账只记录 2026-10-20 起这一轮的基线、环境恢复和后续新增内容，不合并既有正式发布公告。

## 正式基线确认

- 正式 Web、Worker、Beat 当前均运行镜像 `kaj-blog-web:2c78cddf92ac`。
- OCI revision 为 `2c78cddf92acf6adf7f33f3c57affa32cada522e`。
- `origin/main` 与 Labs 当前分支均为 `d0407d6a17206296507f530fcea0537acf52ffb9`；生产 revision 是该提交的祖先。
- `2c78cddf92ac..origin/main` 在 `apps/`、`config/`、`docker/`、`static/`、`templates/` 下无差异，主线后续提交只包含交接与发布文档。

## Labs 分支与 worktree

- Labs worktree：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`。
- 当前分支：`codex/labs-next-20261020`，跟踪 `origin/main`，HEAD 与远端一致。
- 其他 worktree 已保留：主工作区、留言板历史 worktree、旧 Labs 归档和正式版本快照；没有删除、重置或覆盖其中的既有改动。
- 建立 Labs 基线时，账户/作者权限/留言板/通知测试文件按测试专用内容暂未提交；本次用户明确要求交付全部 Labs 改动，相关测试已一并纳入聚焦回归并修正两处旧断言，结果 `29 passed`。

## 运行环境恢复

- `kaj-labs.service`、`kaj-labs-worker.service`、`kaj-labs-beat.service` 均为 `active/running`，工作目录核验为当前 Labs worktree。
- `https://labs.kajspace.cn/health/live` 和 `/health/ready` 均返回 `200`。
- P12 PostgreSQL 接受连接，Redis 返回 `PONG`，Mailpit 容器为 `healthy` 且 API 返回 `200`。
- `kaj-labs-outbox.service` 的历史 `failed/timeout` 状态及 timer 的 `inactive/dead` 状态保持不变；本轮没有重置、清理或改写 Outbox 事件。

## 后续切片记录规则

每完成一个可观察行为切片，追加本文件一节，并新建同目录的独立记录文件。独立记录至少包含：用户入口和结果、唯一 owner、受影响文件与数据、聚焦验证命令及退出码、Labs 页面或安全用户流读回、迁移/通知/后台任务/外部副作用、正式发布所需准备和未验证项。

下一项产品功能尚未由用户指定；收到目标后从本分支开始，先确认 owner、调用方和测试，再按 Labs 优先的 RED/GREEN 与回归流程推进。

## ITER-003 登录用户文章专注模式（2026-10-21）

- 复用登录用户公开文章的既有阅读工具栏，增加全屏请求、活动时长、手动暂停/继续、失焦/页面隐藏/鼠标离开/无操作自动暂停和管理员可配置规则；第三次手动暂停结束会话。
- Labs 已应用并读回 `navigation.0009_focus_mode_settings`，配置默认 `3/3`、范围 `1–15` 分钟和 `1–10` 次；管理员保存、审计、权限和文章登录门槛聚焦回归 `11 passed`。
- Labs live/ready `200`，本地与公网 CSS/JS 哈希一致，390/768/1440 视口无横向溢出。Headless 浏览器拒绝全屏请求并报告缺少用户手势；普通页面继续逻辑保留，真实浏览器全屏成功路径待用户实机确认。
- 完整入口、owner、schema、测试、浏览器限制与正式发布边界记录在 [focus-mode-20261021.md](focus-mode-20261021.md)。
- 本轮没有生产 migration、部署、服务重启、Git 写入、真实邮件、招聘采集或 Provider/AGENT 调用。

### 左下计时区呈现跟进（2026-10-21）

- 工具栏只保留专注开始/结束入口；计时、圆形暂停/继续图标与 `次数/上限` 在页面左下角计时区单行显示，时间和次数为无背景纯文本。
- 手动暂停显示黄色页面边缘流光，自动失焦/无操作警告显示红色流光，活动和结束状态无流光；三种主题、390/768/1440 视口均读回通过。
- Lucide 替换 SVG 后的图标显隐已修正；Labs CSS/JS hash 一致、live `200`，计时区与展开工具栏无重叠。截图工具两次超时，未完成像素级截图检查。完整记录见 [focus-mode-ui-20261021.md](focus-mode-ui-20261021.md)。
- 未执行生产操作、服务重启或 Git 写入。正常登录浏览器的全屏成功路径仍待用户实机确认。

### 页面边缘灼烧光晕补强（2026-10-21）

- 根据用户反馈，将初版低透明度边缘渐变调整为从全屏四边向内扩散的宽幅黄色/红色虚影；以 2.4 秒呼吸脉冲反复播放，不再呈现醒目的细边线。
- CSS 构建通过；浏览器 computed-style 曾读回版本 `...20261021e` 的宽幅光晕，最终又移除 1px 描边并构建为 `article-focus-edge-burn-20261021f`。最终本地/公网 CSS SHA-256 均为 `521417e20bbd4b9daa5071e4e96a8a8f66edb84a33e61bc7f156649771985a3d`，Labs 首页引用 `...21f`、health `200`，服务未重启。
- 截图仍受浏览器 5 秒字体等待限制，未完成像素检查；记录明确保留该限制，增强后视觉强度待用户在 Labs 实测确认。细节见 [focus-mode-edge-burn-20261021.md](focus-mode-edge-burn-20261021.md)。
- 未执行 migration、生产发布、服务重启或 Git 写操作。

### 光晕范围收窄与返回焦点自动恢复（2026-10-21）

- 将上下渐变高度收至 `22%`、左右渐变宽度收至 `24%`，最大模糊 `18px`、内阴影 `56px`；保持黄/红循环脉动并限制在页面边缘附近。
- 窗口失焦、页面隐藏和鼠标离开后，重新聚焦、返回前台或鼠标进入时自动恢复计时并清除警示光效。手动暂停、无操作超时、退出全屏仍需手动继续。
- Labs app bundle 验证 window blur/focus、pointerout/pointerover、手动暂停保持及结束清理；CSS/JS 构建和语法检查通过。本地/公网 CSS 与 JS hash 一致，health `200`，服务未重启。未生成截图，实际光晕仍待用户确认。
- 详情见 [focus-mode-return-behavior-20261021.md](focus-mode-return-behavior-20261021.md)。没有生产操作、migration、服务重启或 Git 写入。

### 文章阅读工具栏按钮内边距（2026-10-21）

- 首次仅增加 padding 的改动被用户确认没有可见变化；原因是胶囊 `max-width: 12rem` 把两个按钮挤压并裁切。首次尝试及限制见 [article-reading-toolbar-spacing-20261021.md](article-reading-toolbar-spacing-20261021.md)。
- 修正后桌面胶囊上限 `22rem`、按钮不收缩且水平内边距 `1.5rem`；窄屏胶囊上限 `calc(100vw - 4.5rem)`、内边距 `0.75rem`。新缓存版本 `article-reading-toolbar-fit-20261021i`。
- `npm run build:css` 通过；Labs CSS 与本地 SHA-256 均为 `72a614c68a55c316160b79a8c5bc7532d833eb18d9a05b6ee056173bee1a87e6`，服务 `active/running`、health `200`。
- 按用户要求不做浏览器测试，按钮观感和窄屏布局由用户自行验收。完整根因与改动见 [article-reading-toolbar-fit-20261021.md](article-reading-toolbar-fit-20261021.md)。
- 未执行生产操作、migration、服务重启或 Git 写入。

## ITER-004 手机版文章阅读模式（2026-10-21）

- 文章右侧手机快捷操作栏新增“阅读模式”；仅 `48rem` 及以下视口显示，公开文章访客也可使用。
- 阅读器支持连续滚动、CSS 多列左右翻页、按屏高度吸附的上下翻页，另有目录跳转、阅读进度、15–25px 字号和日间/护眼/深色主题。偏好只存在浏览器 localStorage；打开时复用原正文节点，关闭后恢复原位置和页面滚动。
- 归属为 discovery 文章模板和独立 `static/src/article-reader-mode.js`；沿用站点主题 token，没有新增 API、数据库写入或 migration。
- CSS/JS 构建退出码均为 `0`，最终静态缓存版本为 `article-reader-mode-20261021c`。Labs 文章页与 `/health/live` 返回 `200`；CSS/JS 公网 SHA-256 分别为 `9471668285746ffb18d08e8dc96e55e4a498a530b80103b79819e919173a4f75` 和 `ef0320761b43cfbadbd028d0768dd08c355adc066b42efb257cb4310a9e2600c`，与本地构建产物一致。完整语法检查与 Labs 读回见 [article-reader-mode-20261021.md](article-reader-mode-20261021.md)。
- 按用户测试偏好未启动浏览器；三种阅读方式、方向旋转、目录、主题/字号和关闭恢复行为由用户在手机实测。
- 没有生产操作、服务重启或 Git 写入。

### 阅读器翻页与设置显隐修正（2026-10-22）

- 左右翻页采用左/中/右三分区点击：左右切换页码，中间显示或收起顶部设置；首次翻页自动收起设置。移除底部上一页/下一页按钮，只保留居中页码。
- 左右分页内容按内层视口宽度裁切，避免屏幕边缘露出邻页内容。
- 上下翻页改为单次固定一屏：上划下一页、下划上一页；不随手指连续滚动，并保留双指缩放。
- 静态资源版本 `article-reader-controls-20261022a`。CSS/JS 构建、语法检查、差异检查均退出码 `0`；Labs 文章页与 health 为 `200`，CSS/JS 公网哈希与本地完全一致。结果见 [article-reader-controls-20261022.md](article-reader-controls-20261022.md)。按用户测试偏好不启动浏览器，手机触控与视觉验收由用户完成。
- 没有生产操作、服务重启或 Git 写入。

### 设置浮层不挤压正文（2026-10-22）

- 左右和上下分页模式的标题栏和设置栏浮在正文上方显示，不再改变阅读视口高度或分页尺寸；上下模式单击切换设置，上下滑动照常单次翻页；连续滚动布局保持原样。
- 静态资源版本更新为 `article-reader-overlay-20261022c`。`node --check static/src/article-reader-mode.js`、CSS 构建、`git diff --check` 均通过；Labs 文章页与 health 为 `200`，CSS 本地/公网 SHA-256 一致。按用户偏好未启动浏览器，实际手机遮挡范围和分页观感由用户验收。详见 [article-reader-controls-overlay-20261022.md](article-reader-controls-overlay-20261022.md)。
- 未执行生产操作、服务重启或 Git 写入。

## 发布边界

- 本台账保存 Labs 功能迭代记录，不作为正式生产发布公告；正式生产结果只写入独立的 [2026-10-22 正式增量公告](../2026-10-22-production-increment/announcement.md) 及同目录部署记录。
- 各切片条目中的“未执行生产 migration/部署”等文字表示该切片完成时的状态；实际正式发布范围与结果以本轮独立部署记录为准。
- 正式公告只引用本次交付提交，不并入 10 月 17 日或其他历史发布记录。
