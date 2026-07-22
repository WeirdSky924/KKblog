# 测试环境与固定命令

项目只有一套 pytest、Ruff 和 Playwright 入口。测试数据不得连接生产或共享服务，也不得写入项目 `var/`。

## 后端与基础设施

运行完整测试前，提供以下隔离值：

```text
KAJ_TEST_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:<port>/kaj_test_<name>
KAJ_TEST_REDIS_URL=redis://127.0.0.1:<port>/<1..15>
KAJ_TEST_MAILPIT_SMTP_URL=smtp://127.0.0.1:<port>
KAJ_TEST_MAILPIT_API_URL=http://127.0.0.1:<port>
```

解析器拒绝非 loopback、默认 Redis DB 0、数据库名/用户不匹配、URL 凭据和 query。pytest 为数据库建立 `test_kaj_test_*`，媒体 fixture 使用 pytest `/tmp` 并自动清理。

固定命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`scripts/test` 先核对四项隔离环境，再执行同一 `uv run pytest`；它不提供 SQLite、mock 或共享服务 fallback。

## 浏览器

固定命令：

```bash
npx playwright test
```

测试 runner 启动本地 Django fixture server；真实浏览器动作统一经 `/usr/local/bin/blog-playwright-cli`，由 `blog-browser` 用户运行。禁止 root Chrome 和 `--no-sandbox`。

Playwright 固定 visitor、user、author、admin 四个 project。账户功能建立后，三种登录身份从以下环境变量读取 storage state：

```text
KAJ_E2E_USER_STATE
KAJ_E2E_AUTHOR_STATE
KAJ_E2E_ADMIN_STATE
```

状态文件必须位于 `/tmp`、权限为 `0600`，不得写入仓库。账户功能完成前，基础错误流只执行 visitor；已登录项目明确跳过，不能把空 state 当真实身份。
