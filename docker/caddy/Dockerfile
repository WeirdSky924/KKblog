ARG CADDY_IMAGE=caddy:2-alpine

FROM ${CADDY_IMAGE}

COPY --chmod=0755 docker/caddy/entrypoint.sh /usr/local/bin/kaj-caddy-entrypoint
COPY docker/caddy/Caddyfile.development /etc/caddy/Caddyfile.development
COPY docker/caddy/Caddyfile.production /etc/caddy/Caddyfile.production
COPY docker/caddy/media-delivery.caddy /etc/caddy/media-delivery.caddy

ENTRYPOINT ["/usr/local/bin/kaj-caddy-entrypoint"]
