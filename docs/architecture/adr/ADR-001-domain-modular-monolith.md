# ADR-001：领域模块化单体

状态：Accepted

## Context

首版部署在一台服务器，团队和流量规模不需要微服务；但认证、私密文章、媒体、评论审核、通知和运维具有不同所有权与生命周期。把全部行为塞进 Django app 会快速形成巨型 views/models/service，把每个名词拆成服务又会制造网络、事务和部署复杂度。

## Decision

采用一个 Django 进程与一个 PostgreSQL 的模块化单体。稳定事实所有者是 `accounts`、`content`、`media`、`comments`、`moderation`、`notifications`、`navigation`、`operations`、`exchange`、`analytics`。

`authoring`、`administration`、`discovery` 是面向用户流的编排/展示模块，不拥有平行业务事实。跨模块只调用公开 service/query/event，禁止直接修改私有模型。

## Consequences

- 单事务仍能保证核心一致性，部署与本地调试简单。
- 模块边界可用 import 纪律、服务 API 和测试强制，而不是靠网络隔离。
- Django admin 不能绕过服务直接修改高风险模型；业务管理界面走正式命令。
- 若将来拆服务，事件与公开契约提供候选边界，但当前不为未来网络化预付复杂度。

## Rejected alternatives

- 单一 `blog` app：短期文件少，长期所有权、测试和权限混杂。
- 首版微服务：跨服务事务、身份、部署和可观测成本远超收益。
- 按页面拆 app：页面变化比领域事实快，会复制同一业务规则。

## Revisit when

某模块需要独立扩缩容/部署、合规隔离或数据所有权，并且模块化单体已经通过调用指标证明边界稳定时再评估拆分。
