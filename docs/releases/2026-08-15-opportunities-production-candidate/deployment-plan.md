# 2026-08-15 增量生产候选部署方案

## 状态与不可越界范围

- 状态：候选准备中；本文不代表生产备份、迁移、镜像替换、服务重启或爬取已经执行。
- 当前正式 Git/镜像基线：`2cbead0794ece4f07e290ed982f5b05c4736ed56` / `kaj-blog-web:2cbead0`。
- 候选：部署窗口从 `origin/main` 读回的完整 SHA；禁止使用可变 `latest`。
- 正式 Compose 项目：`kaj-production`，工作目录 `/home/code/personal-blog/var/production`。
- 正式 Compose 文件：`compose.database.yaml`、`compose.runtime.yaml`。
- 本次只新建并替换 Web、Worker、Beat 共用的应用镜像。PostgreSQL、Redis、Umami、Caddy、数据库目录、媒体目录、静态目录和备份目录原地保留，不重建、不复制、不清空。
- 本次不把 Labs 的岗位、筛选观测、审核、收藏、检查记录、快照、状态变更、任务历史、通知或默认筛选选择复制到生产。

## 候选变更范围

- 统一文章/管理页面的动作布局、标签选择、局部刷新和移动端快捷操作。
- 增加无链接导航分组、默认展开、视窗翻页、分区封面及首页 Hero 图片/视频。
- 增加文章发布历史、管理预览、首次终稿审查和新建页导入入口。
- 友情链接移除 Logo，并改为统一列表与弹窗编辑。
- 新增“找工作”公开页、管理端、来源、岗位、筛选、审核、书签、检查任务、历史与通知链路。
- 新增 41 个招聘来源、适配器实现及版本化来源清单；生产岗位在发布后重新采集。
- 新增 `pymediainfo`，候选镜像提供 `libmediainfo`。5 个浏览器型来源经受控 Unix socket 调用独立宿主服务；通用 Worker 不内置 Chromium、不获得 `SYS_ADMIN`，也不关闭浏览器沙箱。

## 数据库迁移

从正式基线到候选只允许出现以下 12 条 migration：

1. `content.0016_article_publication_history`
2. `media.0005_remove_mediabinding_media_binding_target_registered_and_more`
3. `media.0006_remove_mediaasset_media_asset_size_range_and_more`
4. `navigation.0004_navigation_group_nodes`
5. `navigation.0005_navigation_default_expanded`
6. `navigation.0006_site_hero_media`
7. `navigation.0007_retire_friend_link_logos`
8. `operations.0007_task_run_cancelled`
9. `opportunities.0001_initial`
10. `opportunities.0002_opportunity_check_runtime`
11. `opportunities.0003_opportunity_composite_identity`
12. `opportunities.0004_opportunity_default_filters`

`content.0016` 会根据既有发布事件和当前已发布修订回填文章发布历史；部署前记录文章、修订、发布事件数量并估算窗口。`navigation.0007` 会解除旧友情链接 Logo 媒体绑定并清空旧 Logo ID，不能通过反向 migration 恢复旧绑定。数据库应用迁移后保持前向，不自动反向迁移。

## 来源清单边界

候选文件 `config/opportunity_sources.v1.json` 固定为 schema `kaj.opportunity-source-config.v1`，当前包含 41 个来源、48 个允许域名，SHA-256 为 `12c89e1a83ca9f8d8583f4ec5e10ccb1991b9783f7a222d031fe0081dc2cf934`。当前 41 个 `adapter_config` 均为空。

清单只允许：来源 UUID、企业名、来源类型、官方 HTTPS URL、备注、适配器 key、无凭据适配器配置、启用状态、robots 约束、采集限额和允许域名。导入命令拒绝额外字段、未注册适配器、非 HTTPS URL、越权域名和带 password/secret/token/cookie/API key 等键的配置。

导入统一重置：`publicly_visible=false`、`check_state=NEVER`、失败数为 0、最近成功/检查时间为空、错误码为空、筛选状态为初始值、`row_version=1`。因此来源在首次成功采集前不公开。

## 增量更新操作

### 1. 取得部署授权并冻结候选

当前回合必须明确授权生产备份、维护切换、迁移、来源导入、镜像替换、服务重启和一次全量外部采集。记录执行人、复核人、开始时间和停止条件。

```bash
cd /home/code/personal-blog
git fetch --prune origin
KAJ_RELEASE_BASE=2cbead0794ece4f07e290ed982f5b05c4736ed56
KAJ_RELEASE_CANDIDATE=$(git rev-parse origin/main)
git merge-base --is-ancestor "$KAJ_RELEASE_BASE" "$KAJ_RELEASE_CANDIDATE"
git show --no-patch --format='%H %s' "$KAJ_RELEASE_CANDIDATE"
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$KAJ_RELEASE_CANDIDATE"
```

任一命令失败即停止，不在脏工作树或未知 SHA 上构建。

### 2. 读回现有生产基线

```bash
cd /home/code/personal-blog/var/production
KAJ_PRODUCTION_COMPOSE=(docker compose -f compose.database.yaml -f compose.runtime.yaml)
"${KAJ_PRODUCTION_COMPOSE[@]}" config --quiet
"${KAJ_PRODUCTION_COMPOSE[@]}" ps
"${KAJ_PRODUCTION_COMPOSE[@]}" images
curl --fail --silent --show-error https://kajspace.cn/health/live
curl --fail --silent --show-error https://kajspace.cn/health/ready
```

记录 Web/Worker/Beat/Caddy/数据库镜像 ID、容器启动时间、RestartCount、migration leaf、数据库大小、关键表行数、媒体/静态/备份 bind 路径和公开页面状态。确认所有路径仍位于 `var/production`，且没有指向 Labs。

### 3. 执行候选质量门禁

在隔离 PostgreSQL、Redis、Mailpit 上串行执行 Ruff、format check、Django check、migration drift、相关 pytest、前端测试和正式静态构建。候选必须通过空 PostgreSQL 全量 migration，并确认生产 `migrate --plan` 只包含本文 12 条。

### 4. 串行构建不可变候选镜像

```bash
cd /home/code/personal-blog
KAJ_RELEASE_SHORT=$(printf '%s' "$KAJ_RELEASE_CANDIDATE" | cut -c1-12)
KAJ_CANDIDATE_IMAGE="kaj-blog-web:${KAJ_RELEASE_SHORT}"
DOCKER_BUILDKIT=1 docker build \
  --file docker/web/Dockerfile \
  --build-arg DEBIAN_MIRROR=https://mirrors.aliyun.com/debian \
  --build-arg DEBIAN_SECURITY_MIRROR=https://mirrors.aliyun.com/debian-security \
  --build-arg NODE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm-slim \
  --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim-bookworm \
  --build-arg UV_IMAGE=ghcr.nju.edu.cn/astral-sh/uv:0.11.30 \
  --label "org.opencontainers.image.revision=${KAJ_RELEASE_CANDIDATE}" \
  --tag "$KAJ_CANDIDATE_IMAGE" .
docker image inspect "$KAJ_CANDIDATE_IMAGE" --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
```

记录候选和旧镜像不可变 ID。候选容器内检查 Python 锁、静态产物、`libmediainfo` 和来源清单 SHA。通用应用镜像不得包含 Chromium 或 Playwright 运行时，也不得通过 `SYS_ADMIN` 或 `--no-sandbox` 扩权。

### 5. 准备独立浏览器沙箱服务

浏览器执行服务只运行版本化的 `browser_service.py` 和固定 `browser_runner.cjs`，不加载生产 env，不连接数据库或 Redis。它以 `blog-browser` 运行，按 socket peer UID `10001` 鉴权，限制 16 KiB 请求、8 MiB 响应、单请求串行和 600 秒超时；Chrome 保持 `chromiumSandbox=true`。

```bash
cd /home/code/personal-blog
npm ci
install -o root -g root -m 0644 \
  deploy/systemd/kaj-opportunity-browser.service \
  /etc/systemd/system/kaj-opportunity-browser.service
systemctl daemon-reload
systemctl enable --now kaj-opportunity-browser.service
systemctl show kaj-opportunity-browser.service \
  -p ActiveState -p SubState -p User -p Group -p MainPID
stat -c '%F %U:%G %a %n' /run/kaj-opportunity-browser/browser.sock
```

socket 必须为 `blog-browser:<gid 10001> 0660`。正式 `runtime-production.env` 增加 `KAJ_OPPORTUNITY_BROWSER_SOCKET=/run/kaj-opportunity-browser/browser.sock` 与 `KAJ_OPPORTUNITY_BROWSER_UID=999`；`compose.runtime.yaml` 只给 Worker 增加 `/run/kaj-opportunity-browser` 到同路径的只读 bind。使用应用 UID 10001 完成一次实际浏览器来源 socket smoke，且服务日志、请求和输出不得记录 URL、岗位正文或凭据。宿主服务失败、peer UID 不匹配、Chrome 沙箱失败或需要 `SYS_ADMIN`/关闭沙箱时停止部署。

### 6. 候选连接生产的只读预检

使用正式 `runtime-production.env`、`kaj-production_backend` 网络和既有只读配置挂载，运行候选镜像的 `check --deploy`、`makemigrations --check --dry-run`、`migrate --plan` 和来源清单 dry-run。禁止在此阶段添加 `--apply` 或执行 `migrate`。

### 7. 创建同窗口新鲜生产备份

备份必须覆盖 PostgreSQL custom dump 和完整正式媒体目录，并保存于正式备份目录。读回归档存在、权限、大小、SHA-256、数据库 dump 可被 `pg_restore --list` 解析、媒体文件数/字节数与基线相符。备份失败或只找到旧周备份时停止。

### 8. 开启维护并静默写入

在宿主 Nginx 启用已验证的 `kajspace.cn` 维护响应，公网读回后停止 Beat、Worker、Web；保留 PostgreSQL、Redis、Umami、Caddy 和全部目录。确认没有应用写入进程、运行中的工作机会检查或未消费写任务。维护入口没有经过同机验证时不得继续。

### 9. 使用候选镜像迁移数据库

运行 `python manage.py migrate --noinput`，只应用本文 12 条。读回所有 leaf、文章发布历史约束与数量、媒体/导航字段、TaskRun `CANCELLED` 状态及 opportunities 全部新表。异常时保持维护，不执行反向 migration。

### 10. 校验并导入来源配置

```bash
python manage.py import_opportunity_sources \
  --input /app/config/opportunity_sources.v1.json
python manage.py import_opportunity_sources \
  --input /app/config/opportunity_sources.v1.json \
  --apply
```

第一条必须返回 `sources=41 dry_run=true`；第二条必须返回 created/updated 总和 41。读回 `opportunity_source=41`、`opportunity_source_host=48`、全部来源未公开且检查状态为 `NEVER`。此时岗位、筛选观测、审核、书签、检查、快照和运行历史仍必须为 0；不满足即停止，禁止开始爬取。

### 11. 生成静态文件并切应用镜像

候选运行 `collectstatic --noinput`，不得使用 `--clear`。将正式运行 Compose 的 Web/Worker/Beat 镜像改为候选不可变标签，Worker 保留 `pool=solo/concurrency=1`、只读根、cap drop 与 `no-new-privileges`，并挂载只读 socket 目录。宿主浏览器服务负责 512/768 MiB soft/hard 内存门禁。先启动 Web 并等待健康，再启动单 Worker，最后启动单 Beat；不重建其余服务。

### 12. 发布前 smoke 与关闭维护

验证 live/ready、主页、文章、搜索、账户、管理页、CSS/JS、头像、封面、正文图、附件、Hero 图片/视频和旧友情链接。验证 Markdown/TipTap、文章发布历史、导航默认展开、管理弹窗及找工作空数据页。Web/Worker/Beat 必须使用同一候选镜像 ID，日志无持续 5xx、静态/媒体 404、迁移错误或循环重启。通过后关闭维护并从公网重新读回。

### 13. 生产重新爬取岗位

来源已导入且 Worker 健康后，只触发一次全来源检查。记录 `OpportunityCheckRun` ID，等待它进入终态；不得并发发起第二次全量检查。逐来源核对成功/失败/截断、岗位新增数、筛选项、审核队列和任务历史。失败来源按既有策略等待重试或人工检查，不从 Labs 补数据。

### 14. 爬取后业务验收

确认来源只在首次成功策略满足后公开；公开找工作页可按多选条件筛选，岗位标题、来源、城市、届别和分页正确。管理员可查看来源、岗位、审核队列和任务历史，历史任务查看后消息已读。浏览器型来源不得出现 `adapter_browser_unavailable`，普通来源不得持续返回 0 而误报成功。

### 15. 完成记录

记录候选 SHA、候选/旧镜像 ID、备份 ID/摘要、迁移起止、来源清单摘要、41/48 导入计数、全量检查 ID、各终态计数、公开岗位数、健康读回和维护窗口。未单独授权不得删除旧镜像、旧静态指纹、备份或任何正式数据。

## 回退与停止条件

- 迁移前失败：保持旧应用、旧数据库和旧镜像，不进入切换。
- 迁移失败：保持维护和应用停止，保存证据；不切候选、不反向 migration。
- 候选不健康：恢复已记录的旧 Web/Worker/Beat 镜像，数据库保持前向；旧应用健康后才能关闭维护。
- 来源导入失败：保持候选但不启动 Worker/Beat、不爬取；修正清单或代码后重新 dry-run。
- 全量爬取部分失败：不回滚站点或复制 Labs 岗位；保留失败来源不可见，按任务策略处理。
- 数据库/媒体路径漂移、备份校验失败、出现额外 migration、岗位表在导入前非空、浏览器沙箱不可用、候选与旧应用均不健康，均为一票否决。

本次是原地增量更新：现有账户、文章、评论、通知、媒体和设置保留在正式数据库及 bind 目录中；只有 schema 前向迁移、来源配置初始化、应用镜像替换和部署后的重新采集会产生新事实。
