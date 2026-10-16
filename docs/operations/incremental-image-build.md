# 源码增量镜像构建

当 Python/Node 依赖锁文件和运行时系统包没有变化时，可从当前正式应用镜像构建轻量源码候选，避免重新下载和安装依赖。该方法复用基线镜像中的 Python、虚拟环境、系统库和运行入口，只覆盖应用源码、模板及前端构建产物。

先执行前端构建，再传入正式基线镜像与完整源码提交 SHA：

```bash
npm run build
docker build \
  --file docker/web/Dockerfile.incremental \
  --build-arg BASE_IMAGE=kaj-blog-web:<previous-release> \
  --build-arg SOURCE_REVISION=<full-git-sha> \
  --tag kaj-blog-web:<release-sha> \
  .
```

Dockerfile 复制 `apps/`、`config/`、根模板和 `static/dist/`，并设置 `org.opencontainers.image.revision` 标签。对应的 `.dockerignore` 排除凭据、`var/`、依赖目录、测试和文档，同时保留已构建的静态资源。构建记录应保存基线镜像 ID、源码 SHA、候选镜像 ID 和构建命令。

只有在 `pyproject.toml`、`uv.lock`、`package.json`、`package-lock.json`、系统包安装步骤和运行入口都与基线兼容时才能使用此方法；其中任一项变化时，改用完整 `docker/web/Dockerfile` 构建并重新验证依赖。

增量构建只生成候选镜像，不会迁移数据库、收集静态资源、切换 Compose 服务或部署。候选仍须完成 `check --deploy`、migration drift、正式 migration plan、`collectstatic --noinput`、健康检查与受影响请求读回。
