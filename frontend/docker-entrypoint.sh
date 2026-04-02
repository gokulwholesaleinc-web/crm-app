#!/bin/sh
# Extract the first nameserver from resolv.conf
RAW_RESOLVER=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)

# Wrap IPv6 addresses in brackets for nginx, leave IPv4 as-is
if echo "$RAW_RESOLVER" | grep -q ':'; then
  RESOLVER="[$RAW_RESOLVER]"
else
  RESOLVER="${RAW_RESOLVER:-8.8.8.8}"
fi
export RESOLVER

# Substitute variables in nginx config
envsubst '${BACKEND_HOST} ${BACKEND_PORT} ${RESOLVER}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/conf.d/default.conf.template
exec nginx -g 'daemon off;'
