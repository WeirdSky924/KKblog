# Kajspace 正式增量更新公告

发布时间：2026 年 9 月 7 日

本次正式版本基于提交 `5053a67804ee3a3cd4bb17c827bec04ad99a958a`，采用增量切换方式，仅更新 Web、Worker 和 Beat 应用镜像；账户、文章、评论、通知、招聘、题库、媒体和既有业务数据均原位保留。

主要更新：

- Endpoint Provider 请求超时上限提升至 1800 秒（30 分钟），LangChain transport 与管理端配置共用该边界。
- 题库生成按固定源单元批次执行；批次成功后保存 checkpoint，重试跳过已成功批次，从失败批次继续。
- 全部批次完成后才合并、去重、组卷和发布；最终失败会清理遗留批次结果，不发布半成品。
- 每批模型额度独立申请并在 checkpoint 提交时原子释放，降低 Worker 崩溃后额度卡死风险。
- 修复相关配置、通知、媒体上传和任务状态回归，并补充生产部署所需迁移与状态恢复流程。

本次执行了 `agents.0009_endpoint_timeout_thirty_minutes` 与 `learning.0013_generation_batches` 两条兼容迁移，未导入 Labs 数据，未手动触发招聘全量抓取。

详细备份、校验、回退和状态读回见本目录 `deployment-record.md`。
