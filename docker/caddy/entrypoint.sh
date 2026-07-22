#!/bin/sh
set -eu

runtime_env=${KAJ_RUNTIME_ENV:-development}

require_value() {
	name=$1
	value=$(printenv "$name" 2>/dev/null || true)
	if [ -z "$value" ]; then
		echo "missing required configuration: $name" >&2
		exit 78
	fi
}

case "$runtime_env" in
	development|test)
		exec caddy run --config /etc/caddy/Caddyfile.development --adapter caddyfile
		;;
	production)
		for name in \
			KAJ_PUBLIC_URL \
			KAJ_PUBLIC_HOST
		do
			require_value "$name"
		done
		case "$KAJ_PUBLIC_URL" in
			https://*) ;;
			*) echo "production KAJ_PUBLIC_URL must use https" >&2; exit 78 ;;
		esac
		case "$KAJ_PUBLIC_HOST" in
			*.*) ;;
			*) echo "production KAJ_PUBLIC_HOST must be a real domain" >&2; exit 78 ;;
		esac
		case "$KAJ_PUBLIC_HOST" in
			localhost|127.*|::1|*.test|*.invalid|*.localhost|.*|*.|*..*|*[!A-Za-z0-9.-]*)
				echo "production KAJ_PUBLIC_HOST must be a real domain" >&2
				exit 78
			;;
		esac
		case "$KAJ_PUBLIC_URL" in
			"https://$KAJ_PUBLIC_HOST"|"https://$KAJ_PUBLIC_HOST/") ;;
			*) echo "production URL and host must match" >&2; exit 78 ;;
		esac
		exec caddy run --config /etc/caddy/Caddyfile.production --adapter caddyfile
		;;
	*)
		echo "invalid KAJ_RUNTIME_ENV" >&2
		exit 78
		;;
esac
