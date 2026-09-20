# Kajspace 正式增量更新公告（2026-09-20）

本轮将公开岗位列表/搜索的查询优化发布到正式环境。岗位筛选选项查询由三次合并为一次，摘要复用已加载来源数量，HTMX 岗位 fragment 跳过未使用的完整页摘要查询；不改变岗位字段、权限、分页或数据语义。

- 正式提交：`42adeb4ceb74ec5823df70a66144b21b80b0f275`。
- 候选镜像：`kaj-blog-web:42adeb4ceb74`。
- Web、Worker、Beat 已切换并健康；Caddy、PostgreSQL、Redis、Umami、Mailpit 和既有数据卷未替换。
- 本轮无待执行 migration，未执行 migration；未触发招聘采集、Provider/AGENT 或生产数据修复。
- 发布前备份、健康检查、岗位列表/搜索/筛选/分页和静态资源读回记录在 `deployment-record.md`。
