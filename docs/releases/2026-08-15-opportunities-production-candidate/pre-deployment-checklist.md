# 2026-08-15 增量生产更新检查清单

状态：待执行。所有勾选项必须在正式部署回合新鲜读回，当前均不表示已完成。

## 授权与候选

- [ ] 当前回合已明确授权生产备份、维护、migration、来源导入、镜像替换、服务重启和一次全量采集。
- [ ] 已记录执行人、复核人、窗口起止和停止条件。
- [ ] `origin/main` 候选完整 SHA 是 `2cbead0794ece4f07e290ed982f5b05c4736ed56` 的后代。
- [ ] `/home/code/personal-blog` 干净且 `HEAD` 等于获批候选 SHA。
- [ ] 没有把 Labs `.env`、数据库、媒体、任务历史、岗位或凭据纳入候选。

## 质量与镜像

- [ ] Ruff、format check、Django check、migration drift、相关 pytest、前端测试和正式 build 全绿。
- [ ] 空 PostgreSQL 可从零完成全部 migration。
- [ ] 候选镜像串行构建，完整 SHA 标签和不可变镜像 ID 已记录。
- [ ] 旧 `kaj-blog-web:2cbead0` 标签和镜像 ID 仍存在。
- [ ] 候选内 `pymediainfo` 与 `libmediainfo` 可用。
- [ ] 通用应用镜像不包含 Chromium/Playwright，Worker 未获得 `SYS_ADMIN` 且未关闭沙箱。
- [ ] 宿主 Node、Playwright 和 `/opt/google/chrome/chrome` 版本已记录。
- [ ] `kaj-opportunity-browser.service` 以 `blog-browser`、NNP、零 capability、512/768 MiB 运行。
- [ ] socket 为 `blog-browser:<gid 10001> 0660`，只允许应用 UID 10001。
- [ ] 应用 UID 经 socket 完成一个实际浏览器来源 smoke，沙箱保持启用。
- [ ] 候选内来源清单 SHA 为 `12c89e1a83ca9f8d8583f4ec5e10ccb1991b9783f7a222d031fe0081dc2cf934`。

## 正式只读基线

- [ ] `kaj-production` 的 Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami 状态、镜像和 RestartCount 已记录。
- [ ] live、ready、主页、文章、搜索、登录、静态和真实媒体在变更前正常。
- [ ] 数据库版本、大小、migration leaf 和关键表计数已记录。
- [ ] PostgreSQL、媒体、静态和备份路径均为 `/home/code/personal-blog/var/production` 下既有目录。
- [ ] 候选 `check --deploy` 和 migration drift 在正式配置下只读通过。
- [ ] `migrate --plan` 只出现部署方案列出的 12 条 migration。

## 备份与维护

- [ ] 本窗口创建了新的 PostgreSQL custom dump 和媒体归档，不借用旧周备份。
- [ ] 备份文件存在，大小、权限和 SHA-256 已记录。
- [ ] `pg_restore --list` 成功，媒体文件数和总字节数符合基线。
- [ ] Nginx 维护响应已经过 `nginx -t`、reload 和公网读回验证。
- [ ] Beat、Worker、Web 停止，PostgreSQL、Redis、Umami、Caddy 和 bind 目录保持原位。
- [ ] 没有运行中的工作机会检查或其他应用写进程。

## 迁移与来源

- [ ] 12 条 migration 全部退出 0 并读回 applied。
- [ ] 文章发布历史回填数量合理，同文章修订约束存在。
- [ ] 旧友情链接 Logo 绑定清理结果和影响数量已记录。
- [ ] opportunities 表在来源导入前为空。
- [ ] 来源清单 dry-run 返回 41 条且无未注册适配器或敏感配置。
- [ ] 显式导入返回 created+updated=41。
- [ ] 读回来源 41、允许域名 48，全部 `publicly_visible=false/check_state=NEVER`。
- [ ] 岗位、筛选观测、审核、收藏、检查、快照、状态和任务历史仍为 0。

## 应用切换

- [ ] `collectstatic --noinput` 成功且未使用 `--clear`。
- [ ] Web/Worker/Beat 指向同一候选镜像 ID。
- [ ] Worker 保持 `pool=solo/concurrency=1`、只读根、cap drop 和 NNP，并只读挂载浏览器 socket 目录。
- [ ] Web 先健康，之后单 Worker 健康，最后单 Beat 启动。
- [ ] PostgreSQL、Redis、Umami、Caddy 未重建，既有卷和目录未替换。

## 发布 Smoke

- [ ] live/ready、主页、文章、搜索、账户、管理、CSS/JS 均正常。
- [ ] 头像、封面、正文图、附件及 Hero 图片/视频可读。
- [ ] Markdown、TipTap、文章发布历史和管理预览正常。
- [ ] 导航分组、默认展开、上下翻页和分区封面正常。
- [ ] 找工作公开页和管理页在无岗位阶段显示正确空态。
- [ ] 日志无持续 5xx、404、migration 错误、OOM 或循环重启。
- [ ] 维护关闭后公网关键路径再次读回成功。

## 重新采集

- [ ] 只发起一次全来源检查并记录 run ID。
- [ ] 任务等待到终态，没有一直停留在 waiting，取消入口状态正确。
- [ ] 41 个来源逐项记录成功、失败、截断和岗位新增数。
- [ ] 浏览器型来源无 `adapter_browser_unavailable` 或沙箱错误。
- [ ] 失败来源不从 Labs 搬运岗位，按重试/隐藏策略处理。
- [ ] 公开岗位、筛选项、审核队列和任务历史计数已读回。
- [ ] 公开找工作筛选、分页、岗位名称和来源展示通过。

## 完成与保留

- [ ] 已记录候选/旧镜像 ID、备份摘要、迁移时间、41/48 导入结果、run ID 和终态计数。
- [ ] 已记录所有 smoke 的 URL/状态，不记录 Cookie、token、连接串或个人数据。
- [ ] 旧镜像、旧静态指纹和新鲜备份继续保留。
- [ ] 没有执行反向 migration、生产数据清理或 Labs 岗位复制。

一票否决：候选不是基线后代、出现额外 migration、备份不可验证、维护无法生效、写入无法静默、导入前岗位表非空、来源计数不是 41/48、浏览器沙箱不可用、媒体路径漂移、候选与旧应用均不健康。
