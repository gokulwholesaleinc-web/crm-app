#!/bin/sh
# Extract IPv4 nameserver from resolv.conf (skip IPv6 to avoid nginx parser issues)
RESOLVER=$(awk '/^nameserver/{if($2 !~ /:/){print $2; exit}}' /etc/resolv.conf)
# Fallback to public DNS if no IPv4 nameserver found
RESOLVER=${RESOLVER:-8.8.8.8}
export RESOLVER

# Substitute variables in nginx config
envsubst '${BACKEND_HOST} ${BACKEND_PORT} ${RESOLVER}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/conf.d/default.conf.template
exec nginx -g 'daemon off;'
