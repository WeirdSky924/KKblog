# 2026-09-14 正式增量更新准备记录

状态：准备中。

- 正式旧镜像：`kaj-blog-web:8cfe880`。
- 当前 Labs 服务工作目录：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`。
- 本轮数据库模型没有新增 migration；生产部署前仍执行 `migrate --plan` 作为门禁，不执行无计划迁移。
- 本轮准备范围：文章解释配置入口、招聘筛选提交与排序、划词解释按钮定位、静态缓存版本和对应发布文档。
- 测试文件只用于本地回归，不纳入正式提交；正式镜像由源代码重新构建静态产物。
- 正式备份、候选镜像、状态读回和部署结果待执行后补充到 `deployment-record.md`。
