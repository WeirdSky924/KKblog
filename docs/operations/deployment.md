# 部署状态机骨架

`docker/scripts/deploy` 是部署顺序的 fail-closed 规划器和模拟器。当前版本没有生产命令适配器，不会构建镜像、创建备份、切换维护页、执行迁移、切换服务、访问健康端点或重启容器。

## 安全边界

- 禁止自动部署；Git 提交、推送和部署分别授权。
- 真实部署、生产备份、迁移、服务切换和重启只在用户当前回合明确授权后执行。
- 存在待执行迁移时，必须先取得同轮新鲜备份，再启用维护页和执行迁移。
- 迁移失败时不切换候选应用；候选健康失败时只恢复旧应用，不回滚数据库。
- 维护页没有固定超时。只有候选应用或恢复后的旧应用验证健康，才能关闭维护页。
- 生产缺少真实域名、管理员邮箱、已认证 Resend 发件身份或密钥时仍拒绝启动；决策基线不是生产配置。

## Dry-run

Dry-run 只把计划作为 JSON Lines 写到标准输出，不创建状态目录或日志：

```bash
docker/scripts/deploy \
  --dry-run \
  --migration-state current \
  --deployment-id example-current \
  --state-root var/deployments
```

`--migration-state pending` 会在计划中加入 `create_backup` 和 `apply_migrations`，且备份严格早于维护和迁移。

## 本地模拟

模拟使用预定义结果，不执行 shell 子命令或网络请求：

```bash
docker/scripts/deploy \
  --simulate success-pending \
  --deployment-id example-pending \
  --state-root var/deployments
```

可用场景为 `success-current`、`success-pending`、`migration-failure`、`health-failure` 和 `rollback-health-failure`。每一步输出 `step`、`outcome` 和 `exit_code`，并以原子替换写入权限为 `0600` 的 `<deployment-id>.json`。

成功 ID 再次运行只返回 `already_succeeded`，不重复模拟步骤。失败 ID 同样不自动重放；未完成或损坏的日志拒绝继续，需人工判断状态后使用新的部署 ID。部署 ID 仅允许 ASCII 字母、数字、点、下划线和连字符，不能用于路径穿越。

退出码：`0` 成功，`30` 迁移失败且旧应用健康，`40` 候选健康失败后旧应用恢复健康，`50` 恢复后的旧应用也不健康且维护页保持启用，`64` 参数或状态日志不安全，`70` 模拟器内部错误，`74` 状态日志 I/O 失败。错误输出不包含命令输出、凭据或状态路径。

## 后续接线

真实命令适配器必须由后续交付任务单独实现和验证，并复用 `/health/ready`、Caddy 维护路由、operations 部署记录和 `EXC-006` 的备份 owner。不得把本模拟器的成功结果解释为已完成生产备份、迁移、部署、恢复演练或可恢复性验证。
