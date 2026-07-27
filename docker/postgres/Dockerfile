ARG POSTGRES_IMAGE=postgres:16-bookworm
FROM ${POSTGRES_IMAGE}

COPY --chmod=0755 docker/postgres/init-umami-database.sh /docker-entrypoint-initdb.d/20-umami-database.sh
