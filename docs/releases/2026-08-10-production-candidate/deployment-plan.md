# 2026-08-10 生产候选部署方案

## 状态与边界

- 状态：代码交付候选，尚未执行生产备份、迁移、镜像替换、服务重启或发布。
- 当前正式源码基线：`d53ebe0480f96eec0fb206f50c86f3dbed70d856`。
- 候选源码：以部署窗口从远端默认分支 `origin/main` 读回的完整 SHA 为准，并写入部署记录。
- 编排入口：`compose.yaml` 叠加 `docker/caddy/compose.production.yaml`。
- `docker/scripts/deploy` 只有规划和模拟能力，不得作为真实部署命令使用。
- 本次只替换 Web、Worker、Beat 使用的应用镜像。PostgreSQL、Redis、Umami、Caddy、数据库卷、媒体目录、静态目录和备份目录不重建、不清空。

## 变更范围

本候选在正式基线之后增加或调整：

- 富文本编辑器的结构化 TipTap 文档、工具栏、列表、任务列表、表格、代码块、链接、图片、附件、嵌入、块操作、大纲、撤销历史、粘贴上传和本地草稿能力。
- Markdown 与 TipTap 的统一安全渲染、标题投影、可信嵌入、引用解析和历史版本展示。
- 标签选择与申请、驳回后重提、同名标签身份归并、历史和通知关联修复。
- 管理通知多行 Markdown 输入、统一净化渲染及 `admin.broadcast.v2` 模板。
- 用户名允许安全可见符号，同时继续拒绝空白、控制字符和不可见字符。
- 搜索类型下拉箭头、内容安全策略及相关交互和性能保护。

## 数据库变更

生产当前基线之后只有以下三条新迁移：

1. `content.0013_articlerevision_tiptap_schema_version`
2. `content.0014_allow_rejected_tag_name_reproposal`
3. `content.0015_merge_duplicate_tag_identities`

`0015` 会归并同一规范名的标签，重写修订、文章投影、历史、审计和通知目标后删除重复行，并恢复规范名全局唯一约束。它是前向数据迁移，反向函数不恢复已归并身份。应用回退时数据库保持在新结构，不执行反向迁移。

## 部署前只读预检

在已检出候选 SHA 的干净生产发布工作树和明确的生产 env 文件下执行。下列占位路径必须先替换，不得依赖开发默认值：

```bash
cd <production-repository>
git fetch --prune origin
KAJ_RELEASE_BASE=d53ebe0480f96eec0fb206f50c86f3dbed70d856
KAJ_RELEASE_CANDIDATE=$(git rev-parse origin/main)
git merge-base --is-ancestor "$KAJ_RELEASE_BASE" "$KAJ_RELEASE_CANDIDATE"
git show --no-patch --format='%H %s' "$KAJ_RELEASE_CANDIDATE"
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$KAJ_RELEASE_CANDIDATE"

KAJ_RELEASE_COMPOSE=(
  docker compose
  --env-file <production-env-file>
  -f compose.yaml
  -f docker/caddy/compose.production.yaml
)
"${KAJ_RELEASE_COMPOSE[@]}" config --quiet
"${KAJ_RELEASE_COMPOSE[@]}" ps
"${KAJ_RELEASE_COMPOSE[@]}" exec -T web python manage.py check --deploy
"${KAJ_RELEASE_COMPOSE[@]}" exec -T web python manage.py showmigrations content
```

随后只读记录：

- 当前 Web、Worker、Beat、Caddy 的镜像标签和不可变镜像 ID。
- PostgreSQL 版本、数据库大小、`content_tag` 行数和规范名重复组数量。
- 当前 migration leaf 和候选 `migrate --plan`，结果只能包含上述三条迁移。
- 当前 `/health/live`、`/health/ready`、公开主页、文章正文和实际媒体 URL 状态。
- 数据库、媒体、静态文件和备份 bind 路径均指向既有正式目录。

任一结果不符、发布工作树不干净或没有检出候选、生产目录不明确、env 校验失败、候选不是基线后代或出现额外迁移时立即停止。

## 候选镜像准备

在生产切换前完成，串行构建并记录镜像 ID：

```bash
KAJ_RELEASE_SHORT=$(printf '%s' "$KAJ_RELEASE_CANDIDATE" | cut -c1-12)
export KAJ_WEB_IMAGE="kaj-blog-web:${KAJ_RELEASE_SHORT}"
COMPOSE_PARALLEL_LIMIT=1 "${KAJ_RELEASE_COMPOSE[@]}" build web
docker image inspect "$KAJ_WEB_IMAGE" --format '{{.Id}}'
"${KAJ_RELEASE_COMPOSE[@]}" run --rm web python manage.py check --deploy
"${KAJ_RELEASE_COMPOSE[@]}" run --rm web python manage.py makemigrations --check --dry-run
"${KAJ_RELEASE_COMPOSE[@]}" run --rm web python manage.py migrate --plan
```

候选构建、检查和迁移计划必须全部通过。保存候选镜像 ID、旧应用镜像标签和旧镜像 ID，禁止用可变的 `latest` 作为回退依据。

## 新鲜备份

迁移前使用项目现有 operations 备份 owner 创建同一维护窗口的新鲜生产备份。必须读回：

- `BackupRecord.state=COMPLETED`，完成时间属于本次窗口。
- 归档存在且大小、SHA-256 与记录一致。
- 数据库 dump、媒体文件数和媒体大小均已记录。
- `pg_restore --list` 对归档内 `database.dump` 成功。

备份失败、复用了不属于本窗口的旧记录、归档缺失或摘要不一致时停止。`pg_restore --list` 不代表完整恢复演练已通过。

## 维护窗口与切换顺序

1. 通过生产环境既有的反向代理维护入口启用维护响应，并从公网读回维护页。仓库当前没有真实部署适配器；若现场没有经过验证的维护切换命令，不得开始迁移。
2. 停止 Worker、Beat 和旧 Web，确认没有应用写入进程；保留 PostgreSQL、Redis、Caddy、Umami 和数据卷。
3. 使用候选镜像运行 `python manage.py migrate --noinput`，只应用 `0013`、`0014`、`0015`。
4. 读回三条迁移均已应用，并核对标签规范名无重复、关键关联数量合理、约束存在。
5. 使用候选镜像运行 `python manage.py collectstatic --noinput`。不得使用 `--clear`，保留旧指纹资源供应用回退。
6. 以候选镜像启动 Web，等待容器健康并在内部读回 `/health/live` 和 `/health/ready`。
7. 启动 Worker 和 Beat，确认 Worker ping、Beat 单实例和任务队列无异常。
8. 执行发布后 smoke，通过后关闭维护页并从公网再次读回。

切换命令必须使用 `"${KAJ_RELEASE_COMPOSE[@]}"` 和已记录的 `KAJ_WEB_IMAGE`，不得重建或替换数据库、Redis、Umami、Caddy 及其卷。

## 发布后验证

- Web、Worker、Beat 均使用候选镜像 ID，Caddy 和数据服务仍为原版本。
- `/health/live`、`/health/ready` 返回 200。
- 公开主页、文章页、搜索页、登录页和静态 CSS/JS 返回 200。
- 真实封面、正文图片、头像和附件 URL 可读，Content-Type 正确。
- Markdown 文章和 TipTap 文章均正确渲染；表格、列表、代码块、标题目录和可信嵌入抽查通过。
- 管理员可打开富文本编辑器；保存草稿后版本、正文、图片、附件和标签读回一致。
- 标签驳回后可同名重提，通知详情可显示安全 Markdown。
- 用户名安全符号可保存，空白和不可见字符仍被拒绝。
- 日志无持续 5xx、迁移错误、静态资源 404、CSP 拦截关键资源或任务重复消费。

## 回退和停止条件

- 迁移前失败：保持旧应用和旧数据库，不进入切换。
- 迁移中失败：保持维护状态和旧应用停止，保存错误证据；不切候选，不反向迁移。
- 迁移成功但候选不健康：使用已记录的旧镜像恢复 Web、Worker、Beat，数据库保持前向，验证旧应用健康后再关闭维护页。
- 新版本已经产生 TipTap 修订或标签归并后，不得假设旧应用能无损理解所有新事实；超出维护窗口的回退必须重新评估兼容性。
- 旧应用恢复后也不健康、媒体或数据读回异常、关键关联计数异常时保持维护状态并停止。

实际部署完成后，另建正式公告记录候选完整 SHA、镜像 ID、备份记录、迁移结果、健康读回、维护窗口和残余风险。本文件本身不构成部署完成证明。
