ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG NODE_IMAGE=node:22-bookworm-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.30
ARG UV_DEFAULT_INDEX=https://pypi.org/simple

FROM ${NODE_IMAGE} AS frontend
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /build
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY scripts/copy-fonts.mjs ./scripts/copy-fonts.mjs
COPY static/src ./static/src
RUN npm run build

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS python-dependencies
ARG UV_DEFAULT_INDEX
ENV UV_DEFAULT_INDEX=${UV_DEFAULT_INDEX} \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 kaj \
    && useradd --uid 10001 --gid kaj --no-create-home --shell /usr/sbin/nologin kaj
COPY --from=python-dependencies /opt/venv /opt/venv
COPY apps ./apps
COPY config ./config
COPY templates ./templates
COPY manage.py ./manage.py
COPY --from=frontend --chown=kaj:kaj /build/static/dist ./static/dist
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--no-control-socket", "config.wsgi:application"]
