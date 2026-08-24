# Labs AGENT 真实测试准备记录

日期：2026-08-21

## 测试配置

- Labs 唯一 Endpoint：`68923b06-9ce1-4595-a7f3-24d48ac9391b`
- 两个测试 profile：`knowledge-review`、`question-generation`
- 两个 profile 均绑定上述 Endpoint，Prompt sequence 均为 `1`，当前保持禁用。
- 测试材料来自管理员已有文章的 Markdown 附件；通过正式知识文档上传与绑定服务复制，创建待审核 `KnowledgeDocument` 和 `KnowledgeReviewRun`，没有修改原文章附件。
- 测试材料正文、密钥、Prompt 和 Provider 原始响应均未写入本记录。

## 执行顺序与结果

1. 幂等校准两个 profile，结果为 `created=none repaired=none`。
2. 执行 `CONNECTIVITY_ONLY`。修复后的连接探针使用 LangChain 普通消息，不发送 schema 或 tool；管理检查读回 `SUCCEEDED` 和 `langchain-openai-1.5.2`。
3. 两个 profile 的 native schema capability probe 均读回 `SCHEMA_SUPPORTED` 和 `langchain-openai-1.5.2`。
4. 诊断发现本地 Provider schema projection 和文档 token 预算问题：OpenAI 不支持的约束关键字已移出生成 schema，测试 Endpoint context 调整为 `512000`、per-run limit 调整为 `1200000`；文档估算改为保守 `318624`。
5. 知识审核真实运行成功：文档状态 `APPROVED`，Invocation/Attempt 读回成功终态。
6. 题库生成经过一次超时、两次语义失败和一次额度保护后，最终使用新幂等 series 成功发布一卷 5 题，覆盖状态 `COMPLETE`。

## 读回

- Labs service：`active/running`
- `/health/live`：`200`
- `/health/ready`：`200`
- `active Endpoint reservation`：`0`
- 测试知识文档：`APPROVED`；题库 series：`PUBLISHED / COMPLETE`；生成卷数 `1`、题目数 `5`。
- 成功 invocation usage：输入 `190080`、输出 `1003`、合计 `191083`；attempt phase=`ACCEPTED`。

## 验收结论

纯连接、两个 schema capability、知识审核和题库生成四条链路均已读回成功终态；两个 profile 已通过正式启用服务启用。失败尝试和额度重置均保留安全审计事实，没有发布半成品或遗留 active reservation。
