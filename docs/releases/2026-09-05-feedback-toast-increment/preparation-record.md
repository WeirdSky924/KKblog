# 2026-09-05 候选准备记录

状态：代码候选准备完成；正式生产动作未执行。

## 候选身份

- 远端默认分支基线：`origin/main=82df3ccf689a6e48633b9b28ae19ef840266f195`。
- 本地验证工作树：`/home/code/.codex-worktrees/personal-blog/feedback-release`。
- 本记录不替代最终 Git 提交、远端读回或正式部署记录。

## 本地验证

- 反馈 Toast 聚焦回归：`14 passed`，退出 0。
- 目标 Ruff check：退出 0。
- 目标 Ruff format check：退出 0。
- Python 目标文件编译：退出 0。
- `python manage.py check`：退出 0；仅提示验证工作树尚未生成 `static/dist` 的静态目录。
- `npm run build`：退出 0；CSS、JS、字体构建完成，生成物未纳入 Git。
- `git diff --check`：退出 0。

## 未执行

- 未连接或修改正式数据库，未执行 migration、备份、状态修正或 Outbox 重试。
- 未构建/替换生产镜像，未重启或停止生产服务，未发送真实邮件。
- 未抓取招聘来源，未复制 Labs 账号、文章、岗位、题库、媒体或任务数据。
- 新增的本地回归测试仅用于本次验证，按项目 Git 交付规则不作为提交文件；发布后应由 CI/隔离环境重新执行等价回归。

## 上线后补录

正式部署记录需要补充候选提交哈希、任务分支推送/fast-forward 结果、镜像 digest、数据库/媒体备份摘要、状态修正读回、Outbox 发布批次、健康检查、关键页面和回退结果。
