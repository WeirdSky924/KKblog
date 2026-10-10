# M. 知识学习与题库

所有者：`apps/learning`。本模块独占知识文档业务状态、审核/生成运行、题库系列与不可变修订、题库标签、公开投影、答题、错题本、记录和题库只读 API 策略。

## 责任与非责任

负责从知识 Markdown 到审核、题库生成、公开检索、登录答题和个人学习数据的完整状态机。它通过 `apps.agents.public` 调用稳定 AGENT，通过 `apps.media.public` 读取/绑定文件，通过现有 Outbox 接入通知，并将后台执行关联到 operations TaskRun。

不复制附件权限、媒体存储、Markdown sanitizer、通知/Outbox、审计、重试器或账户资料；不复用 content 的文章标签。HTML 与 JSON transport 复用同一 public query/projection，View 和 Task 不直读私有表。

## 内部目录

```text
apps/learning/
  models/{documents,reviews,banks,questions,appeals,quiz,wrong_book}.py
  services/{documents,reviews,generation,banks,quiz,records,cleanup}.py
  queries/{documents,banks,quiz,administration,public}.py
  policies/{access,quota,api}.py
  events/{schemas,consumers}.py
  tasks/{review,generation,cleanup}.py
  presentation/{public,account,administration,api}.py
  public.py
```

目录只随对应 Todo 建立，不预建空骨架。

## 核心聚合

- KnowledgeDocument：owner、`KNOWLEDGE_DOCUMENT` media 绑定、安全元数据、声明事实、内容摘要、审核状态、删除/保留期限。
- Review/GenerationRun：输入配置快照、源知识单元分批摘要、分批 AGENT invocation/TaskRun 引用、状态、稳定原因码与安全计数，不保存完整 Prompt 或模型原始响应。
- QuestionBankSeries/QuestionBank/QuestionBankRevision：系列可变元数据、最多两卷、不可变完整修订、按源顺序的细粒度知识点及其来源定位、知识点覆盖/遗漏和独立题库标签。
- LearningAppeal/KnowledgeDocumentAccess：正式申诉和管理员成功原文读取历史；前者 Markdown 安全渲染，后者不保存正文或路径。
- QuizAttempt/QuizResponse/WrongQuestion：固定题库 revision、考试/刷题模式、题目/选项顺序与历史快照、严格判分、个人掌握状态和软删除记录。
- `cleanup_learning_expired`：有界到期清理、学习/AGENT reservation 恢复和账户终局学习数据清理；不绕过媒体、通知或 operations owner。

## 权限和状态边界

- 知识文档上传、整理和转题库要求登录账户当前具有 accounts 的附件能力；答题只要求登录；公开题库 HTML 与启用后的 JSON API 可匿名读取。
- 原文只允许 owner 与管理员读取。只有 owner 可从本人 APPROVED 文档生成；管理员不能代生成。
- 审核/生成 AGENT 成功且确定性校验通过后直接进入终态，不增加发布前人工审核；管理员保留事后隐藏、恢复、删除和申诉处理。
- owner 隐藏与 admin 隐藏正交；owner 不能解除 admin 锁。用户删除统一 7 天冷静期，失败材料 30 天后清为无正文 tombstone。
- 删除源文档不删除既有题库；删除题库阻止公开/API/新答题，但本人历史和错题保留自包含只读快照。
- 考试模式只在整套 attempt 提交后释放全部正确答案和解析；刷题模式仅在本人显式提交某个 response 后释放该题答案和解析，未提交的其他 response 继续由 query 投影隐藏。自动保存始终不判分、不更新错题本、不揭晓答案；已揭晓 response 不可继续修改。

## 公开查询和 API

`public_question_bank_page/detail` 是 HTML 与 API 的唯一公开事实来源，统一处理可见性、搜索、筛选、排序和稳定分页。站内 HTML 始终可用；独立 `/api/v1/question-banks` transport 默认关闭，只提供匿名 GET/HEAD 列表与详情。

API gate 在对象查询前执行。关闭返回 `404/api_disabled`；Redis 限流不可用时在 query 前返回 `503/rate_limiter_unavailable`。开启后使用可信客户端 IP 双层限流、精确 HTTPS Origin 白名单、无 credentials、ETag 与版本化 JSON envelope；首版不提供写 API、API key 或 `ANY_ORIGIN`。

## 威胁边界

- Markdown 是不可信输入：编码、NUL、大小、结构和链接先走确定性门禁；模型不得执行文档指令或访问文档链接。
- Prompt injection 或模型“通过”不能放宽附件权限、容量、配额、schema、题目答案一致性或公开安全渲染。
- 公开投影不得包含源文档、Prompt、模型输出、内部原因、路径、密钥或个人数据；详情公开题目、答案和解析仅来自已发布不可变 revision。
- 所有 owner 查询必须先限定 owner，摘要冲突文案不得泄露跨账户相同内容。
- 每日业务配额、同时运行配额与未清理题库数由 PostgreSQL 原子裁决；前端计数只是投影。管理员可在全站配额配置处二次确认清零当天所有账户的题库生成计数，不改变上限、不取消运行中的任务，并写入审计。

## 依赖方向

`learning -> accounts public / agents public / media public / operations public / core`。通知只消费 learning 的版本化 Outbox 事件；账户删除由 learning 在启动时注册 accounts 的清理端口，由 accounts 在删除事务内调用，不跨模块导入 learning 私有模型。`agents`、`media`、`notifications` 和 `operations` 不反向导入 learning 私有实现。

## 验证

附件权限与原文隔离、文档去重/状态/清理、完整分块审核、最多两卷与覆盖统计、不可变修订、公开投影等价、API gate/CORS/限流 fail closed、考试与刷题模式隔离、逐题提交和答案投影、答题快照/自动保存/严格判分、错题手动掌握、账户删除匿名化，以及四身份、三视口、三主题和键盘真实流。

施工依据：`contracts/01-application-services.md` 到 `05-background-tasks.md`、`data/01-er-model.md`、`data/05-storage-lifecycle.md`、`delivery/02-module-verification-matrix.md`。
