# 导入、导出、备份与部署时序

## Markdown 导入

导入分为“解析预览”和“确认写入”两个阶段，预览不得写文章、标签或媒体正式目录。

```mermaid
sequenceDiagram
    actor A as 作者
    participant W as 导入界面
    participant X as exchange service
    participant M as media service
    participant C as content service
    participant P as PostgreSQL

    A->>W: 上传 ZIP/Markdown
    W->>X: create_import_preview
    X->>M: 安全暂存并扫描文件
    X->>X: 解析 Front Matter/Markdown/图片引用
    X->>P: 查询 ID、标题、分区、标签冲突
    X-->>A: 逐篇预览与 SKIP/UPDATE/CREATE 选择
    A->>W: 调整映射并确认
    W->>X: confirm_import(job, expected_preview_version)
    loop 每个选中条目
      X->>C: import_article_item(idempotency_key)
      C->>M: 绑定验证后的图片
      C->>P: 独立事务创建新修订/文章
    end
    X-->>A: 成功、跳过、失败逐项结果
```

## 导入判定表

| 输入情况 | 默认判定 | 可选动作 |
| --- | --- | --- |
| 有 ID，属于导入者 | ID 重复 | 跳过、更新、另建 |
| 有 ID，属于他人 | 外部归属冲突 | 只能跳过；禁止更新/另建 |
| 无 ID，无同标题 | 新文章 | 新建或跳过 |
| 无 ID，有同标题且属于自己 | 疑似重复提示 | 跳过或新建；标题不作为更新键 |
| 无 ID，有同标题且属于他人 | 跨作者警告 | 可坚持新建；发布时通知管理员 |
| Markdown/引用图无效 | 无效项 | 跳过，继续其他条目 |

导入文章一律归属导入者。无法映射分区且作者未重选时进入未知分区。新标签创建为待审并立即关联。更新创建新修订并保留历史；覆盖富文本文章时允许把当前格式改为 Markdown，旧富文本仍在历史中。

`job_id + item_path/hash` 是幂等键。作者重复点击确认时，已成功项读回原结果，不再创建第二篇文章或第二个版本。导入不提供整批撤销。

## 导入包安全

- 解压前及流式解压时同时限制：压缩包不超 `64 MiB`、总展开量不超 `256 MiB`、项目数不超 `1000`、嵌套不超 `8` 层、任一条目和全包实际压缩比不超 `100:1`；超出即拒绝，不继续消耗剩余包内容。
- 使用结构化 ZIP API，解析后路径必须留在该 Job 暂存目录，拒绝 `..`、绝对路径、链接和设备文件。
- Front Matter 使用安全 YAML loader，只接受白名单字段和标量/列表类型。
- 图片必须经过统一 2 MiB、真实格式、解码、静态图 `8192`/`25 MP`、动图 `200` 帧/`100 MP` 累计解码和 EXIF 清理；正文也必须满足 `64 KiB` 至 `2 MiB` 的站点配置。
- Markdown HTML 仍走全站 sanitizer；预览也不能执行原始 HTML。

## 管理员导出

```mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Running: 获得全局唯一运行资格
    Requested --> Rejected: 已有 Running
    Running --> Completed: ZIP 原子完成
    Running --> Cancelled: 管理员取消
    Running --> Failed: 三次任务失败
    Completed --> Expired: 三天到期
    Cancelled --> [*]: 删除未完成 ZIP，保留记录
    Expired --> [*]: 删除 ZIP，保留记录
```

导出范围可为全站、作者、分区或选中文章；允许草稿、定时、私人和 7 天冷静期文章。包包含 JSON 元数据、Markdown 正文、全部历史版本和关联媒体。TipTap 历史版本需提供可逆、带格式标记的 JSON 源文件，另生成 Markdown 只作为便捷副本，不能伪装成无损转换。

下载通过管理员鉴权视图并校验 Job 状态/过期时间，再使用受控内部文件发送；不生成公开或可转发 URL。导出他人内容按作者和上海自然日通知，每位作者每天最多一条。

## 备份

调度固定为 `Asia/Shanghai` 每周一 03:00（`0 3 * * 1`），首版 destination 只能为 `local`。

```mermaid
sequenceDiagram
    participant B as Celery Beat
    participant O as operations service
    participant DB as PostgreSQL
    participant FS as 媒体目录
    participant N as 通知/邮件

    B->>O: start_weekly_backup
    O->>DB: pg_dump 到临时归档
    O->>FS: 同轮媒体快照/归档
    O->>O: 原子改名并记录字节数
    alt 命令成功
      O->>O: BackupRecord=COMPLETED
    else 失败
      O->>O: 三次重试后记录 RuntimeError
      O->>N: 管理员站内+邮件告警
    end
```

备份保留 30 天、本地、不加密，不自动校验 dump 可读性、不做恢复演练。首版不展示或保存未实现的外部目标。文档必须诚实区分“命令返回成功”和“已验证可恢复”；本项目当前只承诺前者。恢复只能由服务器人工操作。

## 部署门禁

部署、迁移和服务重启只有用户当前明确唤起时才执行。批准后的顺序：

```mermaid
flowchart TD
    A["用户明确授权部署"] --> B["构建候选镜像与静态检查"]
    B --> C{"存在待执行迁移?"}
    C -- 否 --> F["启用维护页并切换应用"]
    C -- 是 --> D["创建迁移前数据库备份"]
    D --> E{"备份与迁移成功?"}
    E -- 否 --> X["中止，保留当前应用"]
    E -- 是 --> F
    F --> G["健康检查和关键请求"]
    G -- 通过 --> H["关闭维护页，记录成功"]
    G -- 失败 --> I["回滚应用镜像，不回滚数据库"]
    I --> J["验证旧应用健康后关闭维护页"]
```

迁移必须向前兼容旧应用，否则应用自动回滚承诺无法成立。维护页从切换开始持续到新版本健康或旧版本回滚健康，不能用固定超时假装完成。

## 失败与取消语义

| 流程 | 部分结果 | 用户可重试 | 记录 |
| --- | --- | --- | --- |
| 导入 | 成功条目保留 | 可新建导入 Job；同 Job 确认幂等 | Job/Item 永久 |
| 导出 | 只暴露原子完成 ZIP | 运行中不能新建；失败需修 BUG 后新建 | Job/审计永久 |
| 备份 | 临时包不算成功 | 任务自动三次；无网页重试 | BackupRecord 永久 |
| 部署 | 迁移失败不切应用；健康失败回滚应用 | 由用户重新授权 | 部署/错误日志永久 |
